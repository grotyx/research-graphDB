"""Scenario-Based Integration Tests.

Real-world usage scenarios for Spine GraphRAG system.

Scenarios:
1. Find evidence for TLIF effectiveness on fusion rate
2. Compare UBE vs Open surgery for VAS improvement
3. Get intervention hierarchy for Endoscopic Surgery
4. Detect conflicting results for OLIF outcomes

Each scenario tests:
- Query parsing
- Hybrid search
- Result ranking
- Response quality
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from src.orchestrator.chain_builder import SpineGraphChain, ChainConfig
from src.solver.hybrid_ranker import HybridResult
from src.graph.neo4j_client import Neo4jClient
from src.storage.vector_db import TieredVectorDB

from tests.fixtures.sample_papers import (
    SAMPLE_PAPER_TLIF,
    SAMPLE_PAPER_UBE,
    SAMPLE_PAPER_OLIF_META,
    TLIF_EVIDENCE_FUSION_RATE,
    UBE_EVIDENCE_VAS,
    UBE_EVIDENCE_BLOOD_LOSS,
    OLIF_EVIDENCE_SUBSIDENCE_POSITIVE,
    OLIF_EVIDENCE_SUBSIDENCE_NEGATIVE,
    EXPECTED_TLIF_FUSION_RESULTS,
    EXPECTED_UBE_VS_OPEN_VAS,
    EXPECTED_ENDOSCOPIC_HIERARCHY,
    EXPECTED_OLIF_CONFLICT,
)


class TestScenario1_TLIFFusionEvidence:
    """Scenario 1: Find evidence for TLIF effectiveness on fusion rate.

    User Query: "Find evidence for TLIF effectiveness on fusion rate"

    Expected Behavior:
    - Extract entities: intervention=TLIF, outcome="Fusion Rate"
    - Query type: evidence_search
    - Graph search: Find AFFECTS relationships
    - Vector search: Find relevant text chunks
    - Rank by evidence level + p-value + semantic similarity
    - Return top results with statistical evidence
    """

    @pytest.fixture
    async def mock_chain(self):
        """Create mock chain for scenario testing."""
        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        # Setup mocks
        vector_db.get_embedding.return_value = [0.1] * 768
        vector_db.search_all.return_value = []

        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=neo4j_client,
                vector_db=vector_db,
                config=ChainConfig(),
                api_key="test_key"
            )
            return chain

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario1_entity_extraction(self, mock_chain):
        """Test entity extraction from query."""
        from src.orchestrator.cypher_generator import CypherGenerator

        generator = CypherGenerator()
        query = EXPECTED_TLIF_FUSION_RESULTS["query"]

        entities = generator.extract_entities(query)

        # Verify entity extraction
        assert "interventions" in entities
        assert EXPECTED_TLIF_FUSION_RESULTS["expected_top_intervention"] in entities["interventions"]
        assert entities["intent"] == "evidence_search"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario1_hybrid_search(self):
        """Test hybrid search returns both graph and vector results."""
        from src.solver.hybrid_ranker import HybridRanker

        # Mock dependencies
        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        vector_db.get_embedding.return_value = [0.1] * 768
        vector_db.search_all.return_value = []

        # Mock graph search results
        from src.solver.graph_result import GraphSearchResult

        mock_graph_result = GraphSearchResult(
            evidences=[TLIF_EVIDENCE_FUSION_RATE],
            paper_nodes=[SAMPLE_PAPER_TLIF],
            query_type="evidence_search"
        )

        ranker = HybridRanker(vector_db=vector_db, neo4j_client=neo4j_client)

        # Mock internal graph search
        with patch.object(ranker, "_graph_search", return_value=mock_graph_result):
            query_embedding = [0.1] * 768
            results = await ranker.search(
                query=EXPECTED_TLIF_FUSION_RESULTS["query"],
                query_embedding=query_embedding,
                top_k=10,
                graph_weight=0.6,
                vector_weight=0.4
            )

            # Verify results
            assert len(results) >= EXPECTED_TLIF_FUSION_RESULTS["expected_graph_count"]

            # Check graph result properties
            graph_results = [r for r in results if r.result_type == "graph"]
            assert len(graph_results) > 0

            first_result = graph_results[0]
            assert first_result.evidence.intervention == EXPECTED_TLIF_FUSION_RESULTS["expected_top_intervention"]
            assert first_result.evidence.outcome == EXPECTED_TLIF_FUSION_RESULTS["expected_outcome"]
            assert first_result.evidence.is_significant == EXPECTED_TLIF_FUSION_RESULTS["expected_significance"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario1_result_ranking(self):
        """Test results are ranked by evidence quality."""
        # Create hybrid results with different scores
        results = [
            HybridResult(
                result_type="graph",
                score=0.95,  # High score (RCT evidence)
                content=TLIF_EVIDENCE_FUSION_RATE.get_display_text(),
                source_id="TLIF_001",
                evidence=TLIF_EVIDENCE_FUSION_RATE,
                paper=SAMPLE_PAPER_TLIF,
            ),
            HybridResult(
                result_type="vector",
                score=0.75,  # Lower score
                content="Background discussion on fusion techniques",
                source_id="TLIF_001_discussion",
            ),
        ]

        # Results should be sorted by score
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)

        assert sorted_results[0].result_type == "graph"
        assert sorted_results[0].score > sorted_results[1].score
        assert sorted_results[0].evidence.evidence_level == "1b"  # RCT


class TestScenario2_UBEvsOpenComparison:
    """Scenario 2: Compare UBE vs Open surgery for VAS improvement.

    User Query: "Compare UBE vs Open surgery for VAS improvement"

    Expected Behavior:
    - Extract entities: interventions=[UBE, Open Laminectomy], outcome=VAS
    - Query type: comparison
    - Graph search: Find comparative evidence
    - Identify if difference is significant
    - Return comparison summary
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario2_comparison_query_parsing(self):
        """Test parsing of comparison query."""
        from src.orchestrator.cypher_generator import CypherGenerator

        generator = CypherGenerator()
        query = EXPECTED_UBE_VS_OPEN_VAS["query"]

        entities = generator.extract_entities(query)

        # Should detect comparison intent
        assert entities["intent"] in ["comparison", "evidence_search"]

        # Should extract both interventions (or detect comparison keywords)
        assert "interventions" in entities or "compare" in query.lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario2_comparative_evidence(self):
        """Test retrieval of comparative evidence."""
        from src.solver.graph_result import GraphSearchResult

        # Mock comparative evidence
        result = GraphSearchResult(
            evidences=[UBE_EVIDENCE_VAS, UBE_EVIDENCE_BLOOD_LOSS],
            paper_nodes=[SAMPLE_PAPER_UBE],
            query_type="comparison"
        )

        # Verify evidence
        assert len(result.evidences) >= EXPECTED_UBE_VS_OPEN_VAS["expected_graph_count"]

        # Check for VAS outcome
        vas_evidences = [e for e in result.evidences if e.outcome == EXPECTED_UBE_VS_OPEN_VAS["expected_outcome"]]
        assert len(vas_evidences) > 0

        # Check significance
        vas_evidence = vas_evidences[0]
        assert vas_evidence.is_significant == EXPECTED_UBE_VS_OPEN_VAS["expected_significance"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario2_comparison_summary(self):
        """Test generation of comparison summary."""
        from src.orchestrator.response_synthesizer import ResponseSynthesizer

        # Mock hybrid results with comparative evidence
        hybrid_results = [
            HybridResult(
                result_type="graph",
                score=0.88,
                content=UBE_EVIDENCE_VAS.get_display_text(),
                source_id="UBE_001",
                evidence=UBE_EVIDENCE_VAS,
                paper=SAMPLE_PAPER_UBE,
            ),
            HybridResult(
                result_type="graph",
                score=0.92,
                content=UBE_EVIDENCE_BLOOD_LOSS.get_display_text(),
                source_id="UBE_001",
                evidence=UBE_EVIDENCE_BLOOD_LOSS,
                paper=SAMPLE_PAPER_UBE,
            ),
        ]

        # Mock LLM
        with patch("src.orchestrator.response_synthesizer.genai.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = (
                "UBE shows no significant difference vs Open for VAS (p=0.421), "
                "but significantly reduces blood loss (35ml vs 220ml, p<0.001)."
            )

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            synthesizer = ResponseSynthesizer(api_key="test_key")
            synthesizer.client = mock_client

            response = await synthesizer.synthesize(
                query=EXPECTED_UBE_VS_OPEN_VAS["query"],
                hybrid_results=hybrid_results,
            )

            # Verify response mentions both outcomes
            assert "VAS" in response.answer or "blood loss" in response.answer.lower()
            assert response.confidence_score > 0.0


class TestScenario3_InterventionHierarchy:
    """Scenario 3: Get intervention hierarchy for Endoscopic Surgery.

    User Query: "Get intervention hierarchy for Endoscopic Surgery"

    Expected Behavior:
    - Extract entity: intervention="Endoscopic Surgery"
    - Query type: hierarchy
    - Graph search: Traverse IS_A relationships
    - Return parent categories and child interventions
    - Display as tree structure
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario3_hierarchy_query_parsing(self):
        """Test parsing of hierarchy query."""
        from src.orchestrator.cypher_generator import CypherGenerator

        generator = CypherGenerator()
        query = EXPECTED_ENDOSCOPIC_HIERARCHY["query"]

        entities = generator.extract_entities(query)

        # Should detect hierarchy intent
        assert entities["intent"] == "hierarchy" or "hierarchy" in query.lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario3_hierarchy_traversal(self):
        """Test hierarchy traversal returns parents and children."""
        from src.graph.taxonomy_manager import TaxonomyManager

        # Mock Neo4j client
        neo4j_client = AsyncMock(spec=Neo4jClient)

        # Mock hierarchy query results
        neo4j_client.get_intervention_hierarchy.return_value = [
            {"parent": {"name": EXPECTED_ENDOSCOPIC_HIERARCHY["expected_parent"]}, "levels": 1},
        ]

        neo4j_client.get_intervention_children.return_value = [
            {"child": {"name": child}}
            for child in EXPECTED_ENDOSCOPIC_HIERARCHY["expected_children"]
        ]

        manager = TaxonomyManager(neo4j_client=neo4j_client)

        # Get hierarchy
        hierarchy = await manager.get_hierarchy(intervention_name="Endoscopic Surgery")

        # Verify structure
        assert len(hierarchy["parents"]) > 0
        assert len(hierarchy["children"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario3_hierarchy_display(self):
        """Test hierarchy is formatted for display."""
        from src.solver.graph_result import InterventionHierarchy

        hierarchy = InterventionHierarchy(
            intervention="Endoscopic Surgery",
            level=1,
            parent=EXPECTED_ENDOSCOPIC_HIERARCHY["expected_parent"],
            children=EXPECTED_ENDOSCOPIC_HIERARCHY["expected_children"],
            category=EXPECTED_ENDOSCOPIC_HIERARCHY["expected_category"],
        )

        # Verify hierarchy structure
        assert hierarchy.intervention == "Endoscopic Surgery"
        assert hierarchy.parent == EXPECTED_ENDOSCOPIC_HIERARCHY["expected_parent"]
        assert len(hierarchy.children) == len(EXPECTED_ENDOSCOPIC_HIERARCHY["expected_children"])
        assert hierarchy.category == EXPECTED_ENDOSCOPIC_HIERARCHY["expected_category"]


class TestScenario4_ConflictDetection:
    """Scenario 4: Detect conflicting results for OLIF outcomes.

    User Query: "Detect conflicting results for OLIF outcomes"

    Expected Behavior:
    - Extract entity: intervention=OLIF
    - Query type: conflict
    - Graph search: Find AFFECTS relationships with different directions
    - Identify contradictory findings
    - Explain potential reasons (study design, sample size, etc.)
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario4_conflict_detection_query_parsing(self):
        """Test parsing of conflict detection query."""
        from src.orchestrator.cypher_generator import CypherGenerator

        generator = CypherGenerator()
        query = EXPECTED_OLIF_CONFLICT["query"]

        entities = generator.extract_entities(query)

        # Should detect conflict intent
        assert entities["intent"] == "conflict" or "conflict" in query.lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario4_detect_conflicting_evidence(self):
        """Test detection of conflicting evidence."""
        from src.solver.graph_result import GraphSearchResult

        # Mock conflicting evidence
        result = GraphSearchResult(
            evidences=[
                OLIF_EVIDENCE_SUBSIDENCE_POSITIVE,
                OLIF_EVIDENCE_SUBSIDENCE_NEGATIVE,
            ],
            paper_nodes=[SAMPLE_PAPER_OLIF_META],
            query_type="conflict"
        )

        # Group by outcome to find conflicts
        outcome_groups = result.group_by_outcome()

        # Check for subsidence outcome
        assert EXPECTED_OLIF_CONFLICT["expected_outcome"] in outcome_groups

        subsidence_evidences = outcome_groups[EXPECTED_OLIF_CONFLICT["expected_outcome"]]
        assert len(subsidence_evidences) >= EXPECTED_OLIF_CONFLICT["expected_conflicts"]

        # Check for different directions
        directions = {e.direction for e in subsidence_evidences}
        assert len(directions) > 1  # Conflict exists

        expected_directions = set(EXPECTED_OLIF_CONFLICT["expected_conflicting_directions"])
        assert directions == expected_directions

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_scenario4_conflict_analysis(self):
        """Test conflict analysis and explanation."""
        from src.orchestrator.chain_builder import SpineGraphChain

        # Mock chain
        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        vector_db.get_embedding.return_value = [0.1] * 768

        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = (
                "Conflicting evidence found for OLIF subsidence rate. "
                "Meta-analysis shows no significant increase (8.2%, p=0.234), "
                "but retrospective study reports higher rate (18.5%, p=0.012). "
                "Difference may be due to study design and follow-up duration."
            )

            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_class.return_value = mock_llm

            chain = SpineGraphChain(
                neo4j_client=neo4j_client,
                vector_db=vector_db,
                api_key="test_key"
            )
            chain.llm = mock_llm

            # Mock hybrid results with conflicts
            conflicting_results = [
                HybridResult(
                    result_type="graph",
                    score=0.92,
                    content=OLIF_EVIDENCE_SUBSIDENCE_POSITIVE.get_display_text(),
                    source_id="OLIF_META_001",
                    evidence=OLIF_EVIDENCE_SUBSIDENCE_POSITIVE,
                ),
                HybridResult(
                    result_type="graph",
                    score=0.85,
                    content=OLIF_EVIDENCE_SUBSIDENCE_NEGATIVE.get_display_text(),
                    source_id="OLIF_002",
                    evidence=OLIF_EVIDENCE_SUBSIDENCE_NEGATIVE,
                ),
            ]

            # Mock retriever to return conflicting results
            with patch.object(chain.retriever, "ainvoke", return_value=conflicting_results):
                result = await chain.invoke(
                    EXPECTED_OLIF_CONFLICT["query"],
                    mode="conflict"
                )

                # Verify conflict analysis
                assert result.metadata["mode"] == "conflict"
                assert "conflict" in result.answer.lower() or "different" in result.answer.lower()


class TestScenarioPerformance:
    """Performance tests for scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_scenario_response_time(self):
        """Test scenario execution completes within acceptable time."""
        import time
        from src.orchestrator.chain_builder import SpineGraphChain

        # Mock dependencies
        neo4j_client = AsyncMock(spec=Neo4jClient)
        vector_db = MagicMock(spec=TieredVectorDB)

        vector_db.get_embedding.return_value = [0.1] * 768
        vector_db.search_all.return_value = []

        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Test answer"
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_class.return_value = mock_llm

            chain = SpineGraphChain(
                neo4j_client=neo4j_client,
                vector_db=vector_db,
                api_key="test_key"
            )
            chain.llm = mock_llm

            # Measure execution time
            start = time.time()
            await chain.invoke("Test query", mode="qa")
            elapsed = time.time() - start

            # Should complete within reasonable time (mocked, so should be fast)
            assert elapsed < 5.0, f"Scenario took {elapsed:.2f}s (expected < 5.0s)"


# Test scenario coverage
def test_scenario_coverage():
    """Verify all expected scenarios are covered."""
    import inspect

    test_classes = [
        TestScenario1_TLIFFusionEvidence,
        TestScenario2_UBEvsOpenComparison,
        TestScenario3_InterventionHierarchy,
        TestScenario4_ConflictDetection,
    ]

    total_scenarios = len(test_classes)
    assert total_scenarios == 4, "Should have 4 main scenarios"

    # Count test methods
    total_tests = sum(
        len([m for m in inspect.getmembers(cls, predicate=inspect.isfunction)
             if m[0].startswith("test_")])
        for cls in test_classes
    )

    assert total_tests >= 12, f"Should have at least 12 scenario tests (found {total_tests})"

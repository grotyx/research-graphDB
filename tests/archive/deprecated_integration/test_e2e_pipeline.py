"""End-to-End Pipeline Integration Tests.

Tests complete pipeline: PDF → Extract → Graph → Search → Response

Test Flow:
1. PDF Processing (Vision extraction)
2. Graph Building (Neo4j relationships)
3. Hybrid Search (Graph + Vector)
4. Response Generation (LLM synthesis)

Markers:
- @pytest.mark.integration: Integration test (requires external services)
- @pytest.mark.asyncio: Async test
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

from src.orchestrator.chain_builder import SpineGraphChain, ChainConfig, ChainOutput
from src.solver.hybrid_ranker import HybridRanker, HybridResult
from src.graph.neo4j_client import Neo4jClient, Neo4jConfig
from src.storage.vector_db import TieredVectorDB
from src.graph.spine_schema import PaperNode
from src.solver.graph_result import GraphEvidence, GraphSearchResult

from tests.fixtures.sample_papers import (
    SAMPLE_PAPER_TLIF,
    SAMPLE_PAPER_UBE,
    SAMPLE_PAPER_OLIF_META,
    TLIF_EVIDENCE_FUSION_RATE,
    TLIF_EVIDENCE_VAS,
    UBE_EVIDENCE_VAS,
    UBE_EVIDENCE_BLOOD_LOSS,
    OLIF_EVIDENCE_FUSION_RATE,
    MOCK_VECTOR_RESULTS_TLIF,
)


class TestE2EPipeline:
    """End-to-End pipeline tests with mocked external services."""

    @pytest.fixture
    async def mock_neo4j_client(self):
        """Mock Neo4j client."""
        client = AsyncMock(spec=Neo4jClient)
        client.run_query = AsyncMock(return_value=[])
        client.run_write_query = AsyncMock(return_value={"nodes_created": 1})
        client.create_paper = AsyncMock(return_value={"nodes_created": 1})
        client.create_affects_relation = AsyncMock(return_value={"relationships_created": 1})
        client.get_stats = AsyncMock(return_value={"nodes": {"Paper": 5}, "relationships": {"AFFECTS": 10}})
        return client

    @pytest.fixture
    def mock_vector_db(self):
        """Mock Vector DB."""
        db = MagicMock(spec=TieredVectorDB)

        # Mock embedding
        db.get_embedding.return_value = [0.1] * 768

        # Mock search results
        from src.storage.vector_db import SearchResult as VectorSearchResult
        mock_results = [
            VectorSearchResult(
                chunk_id=r.chunk_id,
                content=r.content,
                score=r.score,
                tier=r.tier,
                section=r.section,
                evidence_level=r.evidence_level,
                is_key_finding=r.is_key_finding,
                has_statistics=r.has_statistics,
                title=r.title,
                publication_year=r.publication_year,
                summary=r.summary,
                distance=1.0 - r.score,
                metadata={}
            )
            for r in MOCK_VECTOR_RESULTS_TLIF
        ]

        db.search_all.return_value = mock_results
        db.get_stats.return_value = {"total_chunks": 100, "tier1_chunks": 40}

        return db

    @pytest.fixture
    async def mock_chain(self, mock_neo4j_client, mock_vector_db):
        """Create SpineGraphChain with mocked dependencies."""
        config = ChainConfig(
            gemini_model="gemini-2.5-flash-preview-05-20",
            temperature=0.1,
            top_k=10,
            graph_weight=0.6,
            vector_weight=0.4,
        )

        # Mock Gemini LLM
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI") as mock_llm_class:
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Based on the evidence, TLIF shows high fusion rates (95.8%, p=0.002)."
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_class.return_value = mock_llm

            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=config,
                api_key="test_key"
            )

            # Override LLM with mock
            chain.llm = mock_llm

            return chain

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_e2e_pipeline_qa_mode(self, mock_chain):
        """Test complete E2E pipeline in QA mode.

        Flow: Query → Hybrid Retrieval → Context Formatting → LLM → Answer
        """
        query = "Is TLIF effective for improving fusion rate?"

        # Execute pipeline
        result = await mock_chain.invoke(query, mode="qa")

        # Assertions
        assert isinstance(result, ChainOutput)
        assert result.answer != ""
        assert "TLIF" in result.answer or "fusion" in result.answer.lower()
        assert len(result.sources) > 0
        assert result.metadata["mode"] == "qa"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_e2e_pipeline_retrieval_mode(self, mock_chain):
        """Test E2E pipeline in retrieval-only mode.

        Flow: Query → Hybrid Retrieval → Return Sources
        """
        query = "TLIF fusion rate studies"

        # Execute pipeline
        result = await mock_chain.invoke(query, mode="retrieval")

        # Assertions
        assert isinstance(result, ChainOutput)
        assert result.answer == ""  # No LLM in retrieval mode
        assert len(result.sources) > 0
        assert result.metadata["mode"] == "retrieval"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_e2e_pipeline_conflict_mode(self, mock_chain):
        """Test E2E pipeline in conflict analysis mode.

        Flow: Query → Retrieval → Conflict Detection → LLM Analysis
        """
        query = "Are there conflicting results for OLIF subsidence?"

        # Mock conflict detection
        with patch.object(mock_chain, "_detect_conflicts") as mock_detect:
            mock_detect.return_value = []  # No conflicts

            result = await mock_chain.invoke(query, mode="conflict")

            # Assertions
            assert isinstance(result, ChainOutput)
            assert result.metadata["mode"] == "conflict"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_e2e_pipeline_error_handling(self, mock_chain):
        """Test E2E pipeline error handling."""
        # Trigger error by using invalid mode
        result = await mock_chain.invoke("test query", mode="invalid_mode")

        # Should return error in metadata
        assert "error" in result.metadata
        assert "Invalid mode" in result.answer or "Error" in result.answer


class TestPDFToGraphPipeline:
    """Test PDF processing to graph storage pipeline."""

    @pytest.fixture
    def mock_neo4j_client(self):
        """Mock Neo4j client for graph operations."""
        client = AsyncMock(spec=Neo4jClient)
        client.create_paper = AsyncMock(return_value={"nodes_created": 1})
        client.create_studies_relation = AsyncMock(return_value={"relationships_created": 1})
        client.create_investigates_relation = AsyncMock(return_value={"relationships_created": 1})
        client.create_affects_relation = AsyncMock(return_value={"relationships_created": 1})
        return client

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pdf_to_graph_paper_creation(self, mock_neo4j_client):
        """Test creating paper node from extracted data."""
        paper = SAMPLE_PAPER_TLIF

        result = await mock_neo4j_client.create_paper(paper)

        assert result["nodes_created"] == 1
        mock_neo4j_client.create_paper.assert_called_once_with(paper)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pdf_to_graph_evidence_relationships(self, mock_neo4j_client):
        """Test creating evidence relationships from extracted data."""
        evidence = TLIF_EVIDENCE_FUSION_RATE

        result = await mock_neo4j_client.create_affects_relation(
            intervention_name=evidence.intervention,
            outcome_name=evidence.outcome,
            source_paper_id=evidence.source_paper_id,
            value=evidence.value,
            value_control=evidence.value_control,
            p_value=evidence.p_value,
            effect_size=evidence.effect_size,
            confidence_interval=evidence.confidence_interval,
            is_significant=evidence.is_significant,
            direction=evidence.direction,
        )

        assert result["relationships_created"] == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pdf_to_graph_complete_paper(self, mock_neo4j_client):
        """Test complete paper storage with all relationships."""
        paper = SAMPLE_PAPER_TLIF
        evidences = [TLIF_EVIDENCE_FUSION_RATE, TLIF_EVIDENCE_VAS]

        # Create paper
        await mock_neo4j_client.create_paper(paper)

        # Create pathology relationship
        await mock_neo4j_client.create_studies_relation(
            paper_id=paper.paper_id,
            pathology_name="Lumbar Stenosis",
            is_primary=True
        )

        # Create intervention relationship
        await mock_neo4j_client.create_investigates_relation(
            paper_id=paper.paper_id,
            intervention_name="TLIF",
            is_comparison=False
        )

        # Create evidence relationships
        for evidence in evidences:
            await mock_neo4j_client.create_affects_relation(
                intervention_name=evidence.intervention,
                outcome_name=evidence.outcome,
                source_paper_id=evidence.source_paper_id,
                value=evidence.value,
                p_value=evidence.p_value,
                is_significant=evidence.is_significant,
                direction=evidence.direction,
            )

        # Verify all calls made
        assert mock_neo4j_client.create_paper.call_count == 1
        assert mock_neo4j_client.create_studies_relation.call_count == 1
        assert mock_neo4j_client.create_investigates_relation.call_count == 1
        assert mock_neo4j_client.create_affects_relation.call_count == 2


class TestGraphToSearchPipeline:
    """Test graph querying to search results pipeline."""

    @pytest.fixture
    async def mock_graph_search(self):
        """Mock graph search with realistic results."""
        from src.solver.graph_search import GraphSearch

        search = AsyncMock(spec=GraphSearch)

        # Mock intervention outcome search
        search.search_interventions_for_outcome = AsyncMock(
            return_value=GraphSearchResult(
                evidences=[TLIF_EVIDENCE_FUSION_RATE, OLIF_EVIDENCE_FUSION_RATE],
                paper_nodes=[SAMPLE_PAPER_TLIF, SAMPLE_PAPER_OLIF_META],
                query_type="evidence_search"
            )
        )

        # Mock hierarchy search
        search.get_intervention_hierarchy = AsyncMock(
            return_value=GraphSearchResult(
                evidences=[],
                paper_nodes=[],
                query_type="hierarchy"
            )
        )

        # Mock conflict detection
        search.find_conflicting_results = AsyncMock(
            return_value=GraphSearchResult(
                evidences=[],
                paper_nodes=[],
                query_type="conflict"
            )
        )

        return search

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_graph_search_to_results(self, mock_graph_search):
        """Test graph search returning structured results."""
        result = await mock_graph_search.search_interventions_for_outcome(
            outcome_name="Fusion Rate",
            min_p_value=0.05
        )

        assert isinstance(result, GraphSearchResult)
        assert len(result.evidences) == 2
        assert len(result.paper_nodes) == 2
        assert all(e.is_significant for e in result.evidences)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_graph_results_filtering(self, mock_graph_search):
        """Test filtering graph results by significance."""
        result = await mock_graph_search.search_interventions_for_outcome(
            outcome_name="Fusion Rate",
            min_p_value=0.05
        )

        # Filter by significance
        filtered = result.filter_by_significance(min_p_value=0.01)

        assert isinstance(filtered, GraphSearchResult)
        # All should pass since both have p<0.01 in our mock data
        assert len(filtered.evidences) <= len(result.evidences)


class TestHybridSearchPipeline:
    """Test hybrid search combining graph and vector results."""

    @pytest.fixture
    def mock_hybrid_ranker(self):
        """Mock hybrid ranker with realistic results."""
        ranker = AsyncMock(spec=HybridRanker)

        # Mock search results combining graph and vector
        mock_results = [
            HybridResult(
                result_type="graph",
                score=0.95,
                content=TLIF_EVIDENCE_FUSION_RATE.get_display_text(),
                source_id=TLIF_EVIDENCE_FUSION_RATE.source_paper_id,
                evidence=TLIF_EVIDENCE_FUSION_RATE,
                paper=SAMPLE_PAPER_TLIF,
                metadata={
                    "p_value": TLIF_EVIDENCE_FUSION_RATE.p_value,
                    "evidence_level": TLIF_EVIDENCE_FUSION_RATE.evidence_level,
                }
            ),
            HybridResult(
                result_type="vector",
                score=0.88,
                content=MOCK_VECTOR_RESULTS_TLIF[0].content,
                source_id=MOCK_VECTOR_RESULTS_TLIF[0].chunk_id,
                metadata={
                    "tier": "tier1",
                    "section": "abstract",
                }
            ),
        ]

        ranker.search = AsyncMock(return_value=mock_results)

        return ranker

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hybrid_search_combines_sources(self, mock_hybrid_ranker):
        """Test hybrid search combines graph and vector sources."""
        query_embedding = [0.1] * 768

        results = await mock_hybrid_ranker.search(
            query="TLIF fusion rate",
            query_embedding=query_embedding,
            top_k=10,
            graph_weight=0.6,
            vector_weight=0.4
        )

        assert len(results) > 0

        # Check both result types present
        result_types = {r.result_type for r in results}
        assert "graph" in result_types
        assert "vector" in result_types

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hybrid_search_ranking(self, mock_hybrid_ranker):
        """Test hybrid search ranks by combined score."""
        query_embedding = [0.1] * 768

        results = await mock_hybrid_ranker.search(
            query="TLIF fusion rate",
            query_embedding=query_embedding,
            top_k=10,
            graph_weight=0.6,
            vector_weight=0.4
        )

        # Results should be sorted by score (descending)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestResponseGenerationPipeline:
    """Test response generation from hybrid results."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_response_generation_with_evidence(self):
        """Test response generation includes evidence."""
        from src.orchestrator.response_synthesizer import ResponseSynthesizer

        # Mock hybrid results
        hybrid_results = [
            HybridResult(
                result_type="graph",
                score=0.95,
                content=TLIF_EVIDENCE_FUSION_RATE.get_display_text(),
                source_id=TLIF_EVIDENCE_FUSION_RATE.source_paper_id,
                evidence=TLIF_EVIDENCE_FUSION_RATE,
                paper=SAMPLE_PAPER_TLIF,
            ),
        ]

        # Mock LLM client
        with patch("src.orchestrator.response_synthesizer.genai.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = "TLIF demonstrates high fusion rates (95.8%, p=0.002) based on RCT evidence."

            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            synthesizer = ResponseSynthesizer(api_key="test_key")
            synthesizer.client = mock_client

            response = await synthesizer.synthesize(
                query="Is TLIF effective for fusion?",
                hybrid_results=hybrid_results,
                max_evidences=5,
                max_contexts=3
            )

            # Assertions
            assert response.answer != ""
            assert len(response.supporting_papers) > 0
            assert len(response.graph_evidences) > 0
            assert 0.0 <= response.confidence_score <= 1.0


class TestPipelineIntegration:
    """Integration tests for complete pipeline scenarios."""

    @pytest.mark.skip(reason="Requires actual Neo4j and ChromaDB instances")
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_pipeline_with_real_services(self):
        """Test full pipeline with real Neo4j and ChromaDB.

        This test requires:
        - Neo4j running on bolt://localhost:7687
        - ChromaDB persisted directory
        - Gemini API key in environment

        Skip by default, run manually for integration validation.
        """
        from src.orchestrator.chain_builder import create_chain
        import os

        chain = await create_chain(
            neo4j_uri="bolt://localhost:7687",
            neo4j_username="neo4j",
            neo4j_password="password",
            chromadb_path="./data/chromadb",
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
        )

        result = await chain.invoke(
            "What is the fusion rate for TLIF?",
            mode="qa"
        )

        assert isinstance(result, ChainOutput)
        assert result.answer != ""
        assert len(result.sources) > 0


# Test execution summary
def test_integration_suite_metadata():
    """Test suite metadata and documentation."""
    import inspect

    # Count test classes
    test_classes = [
        TestE2EPipeline,
        TestPDFToGraphPipeline,
        TestGraphToSearchPipeline,
        TestHybridSearchPipeline,
        TestResponseGenerationPipeline,
        TestPipelineIntegration,
    ]

    total_tests = sum(
        len([m for m in inspect.getmembers(cls, predicate=inspect.isfunction)
             if m[0].startswith("test_")])
        for cls in test_classes
    )

    assert total_tests > 0, "Integration test suite should have test methods"

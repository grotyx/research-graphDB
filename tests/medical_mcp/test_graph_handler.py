"""Tests for GraphHandler.

This module tests graph-based operations including:
- Paper relations and evidence chains
- Topic clustering and statistics
- Intervention hierarchy and taxonomy
- Intervention comparison
- Inference rules
- Error handling and validation
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from medical_mcp.handlers.graph_handler import GraphHandler
from core.exceptions import Neo4jError, ValidationError


@pytest.fixture
def mock_neo4j_client():
    """Create a mock Neo4j client."""
    client = Mock()
    client._driver = Mock()
    client.get_paper = AsyncMock(
        return_value={
            "p": {
                "paper_id": "test_paper_1",
                "title": "Test Paper",
                "year": 2024,
                "evidence_level": "2b"
            }
        }
    )
    client.get_paper_relations = AsyncMock(return_value=[])
    client.get_supporting_papers = AsyncMock(return_value=[])
    client.get_contradicting_papers = AsyncMock(return_value=[])
    client.get_similar_papers = AsyncMock(return_value=[])
    client.run_query = AsyncMock(return_value=[])
    client.get_all_papers_with_relations = AsyncMock(return_value=[])
    client.create_paper_relation = AsyncMock(return_value=True)
    client.hybrid_search = AsyncMock(return_value=[])
    client.connect = AsyncMock()
    return client


@pytest.fixture
def mock_server(mock_neo4j_client):
    """Create a mock MedicalKAGServer instance."""
    server = Mock()
    server.neo4j_client = mock_neo4j_client
    server.graph_searcher = Mock()
    server.graph_searcher.get_intervention_hierarchy = AsyncMock(
        return_value={
            "full_name": "Transforaminal Lumbar Interbody Fusion",
            "category": "Fusion",
            "approach": "Posterior",
            "is_minimally_invasive": True,
            "parents": ["Lumbar Interbody Fusion"],
            "children": ["MIS-TLIF"]
        }
    )
    server.cypher_generator = Mock()
    server.taxonomy_manager = Mock()
    server.ranker = Mock()
    server.find_evidence = AsyncMock(
        return_value={
            "success": True,
            "evidence": []
        }
    )
    return server


@pytest.fixture
def graph_handler(mock_server):
    """Create a GraphHandler instance."""
    return GraphHandler(mock_server)


class TestGraphHandlerInit:
    """Test GraphHandler initialization."""

    def test_init(self, mock_server):
        """Test basic initialization."""
        handler = GraphHandler(mock_server)
        assert handler.server == mock_server
        assert handler.graph_searcher == mock_server.graph_searcher
        assert handler.cypher_generator == mock_server.cypher_generator
        assert handler.taxonomy_manager == mock_server.taxonomy_manager
        assert handler.ranker == mock_server.ranker


class TestGetPaperRelations:
    """Test get_paper_relations method."""

    @pytest.mark.asyncio
    async def test_get_relations_success(self, graph_handler, mock_neo4j_client):
        """Test successful retrieval of paper relations."""
        mock_neo4j_client.get_paper_relations = AsyncMock(
            return_value=[
                {
                    "target": {
                        "paper_id": "related_paper_1",
                        "title": "Related Paper"
                    },
                    "relation_type": "SUPPORTS",
                    "confidence": 0.85,
                    "evidence": "Both studies show similar outcomes"
                }
            ]
        )

        result = await graph_handler.get_paper_relations("test_paper_1")

        assert result["success"] is True
        assert result["paper"]["id"] == "test_paper_1"
        assert len(result["relations"]) == 1
        assert result["relations"][0]["type"] == "SUPPORTS"

    @pytest.mark.asyncio
    async def test_get_relations_with_filter(self, graph_handler, mock_neo4j_client):
        """Test relations retrieval with type filter."""
        result = await graph_handler.get_paper_relations(
            "test_paper_1",
            relation_type="SUPPORTS"
        )

        assert result["success"] is True
        mock_neo4j_client.get_paper_relations.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_relations_paper_not_found(self, graph_handler, mock_neo4j_client):
        """Test handling of non-existent paper."""
        mock_neo4j_client.get_paper = AsyncMock(return_value=None)

        result = await graph_handler.get_paper_relations("nonexistent_paper")

        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_relations_no_neo4j(self, graph_handler, mock_server):
        """Test error when Neo4j not available."""
        mock_server.neo4j_client = None

        result = await graph_handler.get_paper_relations("test_paper_1")

        assert result["success"] is False
        assert "Neo4j" in result["error"]

    @pytest.mark.asyncio
    async def test_get_relations_with_supporting_papers(self, graph_handler, mock_neo4j_client):
        """Test retrieval includes supporting papers."""
        mock_neo4j_client.get_supporting_papers = AsyncMock(
            return_value=[
                {
                    "target": {
                        "paper_id": "support_1",
                        "title": "Supporting Paper"
                    },
                    "confidence": 0.9
                }
            ]
        )

        result = await graph_handler.get_paper_relations("test_paper_1")

        assert result["success"] is True
        assert len(result["supporting_papers"]) == 1
        assert result["supporting_papers"][0]["id"] == "support_1"


class TestFindEvidenceChain:
    """Test find_evidence_chain method."""

    @pytest.mark.asyncio
    async def test_find_evidence_text_matching(self, graph_handler, mock_neo4j_client):
        """Test evidence chain using text matching."""
        mock_neo4j_client.run_query = AsyncMock(
            return_value=[
                {
                    "paper_id": "paper_1",
                    "title": "TLIF Study",
                    "year": 2024,
                    "evidence_level": "2b",
                    "evidence": [
                        {
                            "intervention": "TLIF",
                            "outcome": "VAS",
                            "direction": "improved",
                            "p_value": 0.01,
                            "is_significant": True
                        }
                    ]
                }
            ]
        )

        result = await graph_handler.find_evidence_chain(
            "TLIF improves pain outcomes",
            max_papers=5
        )

        assert result["success"] is True
        assert result["total_papers"] == 1
        assert len(result["supporting_papers"]) == 1

    @pytest.mark.asyncio
    async def test_find_evidence_vector_fallback(self, graph_handler, mock_neo4j_client):
        """Test fallback to vector search when text matching fails."""
        # First query returns empty
        mock_neo4j_client.run_query = AsyncMock(
            side_effect=[
                [],  # Initial text matching
                [{"paper_id": "vec_paper", "title": "Vector Match", "year": 2024, "evidence_level": "2b", "evidence": []}]  # Vector details
            ]
        )
        mock_neo4j_client.hybrid_search = AsyncMock(
            return_value=[{"paper_id": "vec_paper"}]
        )

        with patch('core.embedding.get_embedding_generator') as mock_emb:
            mock_gen = Mock()
            mock_gen.generate.return_value = [0.1] * 3072
            mock_emb.return_value = mock_gen

            result = await graph_handler.find_evidence_chain("test claim", max_papers=5)

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_find_evidence_classify_direction(self, graph_handler, mock_neo4j_client):
        """Test classification of papers by outcome direction."""
        mock_neo4j_client.run_query = AsyncMock(
            return_value=[
                {
                    "paper_id": "paper_improved",
                    "title": "Improved",
                    "year": 2024,
                    "evidence_level": "2b",
                    "evidence": [{"intervention": "TLIF", "outcome": "VAS", "direction": "improved"}]
                },
                {
                    "paper_id": "paper_worsened",
                    "title": "Worsened",
                    "year": 2024,
                    "evidence_level": "2b",
                    "evidence": [{"intervention": "TLIF", "outcome": "Complications", "direction": "worsened"}]
                }
            ]
        )

        result = await graph_handler.find_evidence_chain("test claim", max_papers=5)

        assert result["success"] is True
        assert len(result["supporting_papers"]) == 1
        assert len(result["refuting_papers"]) == 1


class TestGetTopicClusters:
    """Test get_topic_clusters method."""

    @pytest.mark.asyncio
    async def test_get_clusters_success(self, graph_handler, mock_neo4j_client):
        """Test successful topic clustering."""
        mock_neo4j_client.run_query = AsyncMock(
            side_effect=[
                # Sub-domain clusters
                [
                    {
                        "topic": "Degenerative",
                        "papers": [
                            {"id": "p1", "title": "Paper 1", "year": 2024, "evidence_level": "2b"}
                        ],
                        "count": 1
                    }
                ],
                # Similar topic count
                [{"similar_topic_count": 5}],
                # Unknown papers
                [{"papers": [], "count": 0}]
            ]
        )

        result = await graph_handler.get_topic_clusters()

        assert result["success"] is True
        assert "Degenerative" in result["clusters"]
        assert result["similar_topic_relations"] == 5

    @pytest.mark.asyncio
    async def test_get_clusters_with_unclassified(self, graph_handler, mock_neo4j_client):
        """Test clustering includes unclassified papers."""
        mock_neo4j_client.run_query = AsyncMock(
            side_effect=[
                # Sub-domain clusters
                [{"topic": "Degenerative", "papers": [{"id": "p1"}], "count": 1}],
                # Similar topic count
                [{"similar_topic_count": 0}],
                # Unknown papers
                [{"papers": [{"id": "p2", "title": "Unknown", "year": 2024}], "count": 1}]
            ]
        )

        result = await graph_handler.get_topic_clusters()

        assert result["success"] is True
        assert "Unclassified" in result["clusters"]
        assert result["clusters"]["Unclassified"]["count"] == 1


class TestGetInterventionHierarchy:
    """Test get_intervention_hierarchy method."""

    @pytest.mark.asyncio
    async def test_get_hierarchy_success(self, graph_handler):
        """Test successful hierarchy retrieval."""
        result = await graph_handler.get_intervention_hierarchy("TLIF")

        assert result["success"] is True
        assert result["intervention"] == "TLIF"
        assert result["full_name"] == "Transforaminal Lumbar Interbody Fusion"
        assert "Lumbar Interbody Fusion" in result["parents"]

    @pytest.mark.asyncio
    async def test_get_hierarchy_with_aliases(self, graph_handler):
        """Test hierarchy includes aliases."""
        with patch('graph.entity_normalizer.get_normalizer') as mock_norm:
            normalizer = Mock()
            normalizer.INTERVENTION_ALIASES = {
                "TLIF": "TLIF",
                "Transforaminal Fusion": "TLIF"
            }
            mock_norm.return_value = normalizer

            result = await graph_handler.get_intervention_hierarchy("TLIF")

            assert result["success"] is True
            assert len(result["aliases"]) >= 1

    @pytest.mark.asyncio
    async def test_get_hierarchy_no_graph_searcher(self, mock_server):
        """Test error when graph searcher not available."""
        mock_server.graph_searcher = None
        # Create new handler with modified server
        handler = GraphHandler(mock_server)

        result = await handler.get_intervention_hierarchy("TLIF")

        assert result["success"] is False
        assert "not available" in result["error"]


class TestBuildPaperRelations:
    """Test build_paper_relations method."""

    @pytest.mark.asyncio
    async def test_build_relations_all_papers(self, graph_handler, mock_neo4j_client):
        """Test building relations for all papers."""
        mock_neo4j_client.get_all_papers_with_relations = AsyncMock(
            return_value=[
                {
                    "paper_id": "p1",
                    "sub_domain": "Degenerative",
                    "sub_domains": ["Degenerative"],
                    "pathologies": ["Stenosis"],
                    "interventions": ["TLIF"],
                    "anatomy_levels": ["L4-L5"]
                },
                {
                    "paper_id": "p2",
                    "sub_domain": "Degenerative",
                    "sub_domains": ["Degenerative"],
                    "pathologies": ["Stenosis"],
                    "interventions": ["PLIF"],
                    "anatomy_levels": ["L4-L5"]
                }
            ]
        )

        result = await graph_handler.build_paper_relations(min_similarity=0.3)

        assert result["success"] is True
        assert result["papers_processed"] == 2
        assert result["relations_created"] >= 0

    @pytest.mark.asyncio
    async def test_build_relations_single_paper(self, graph_handler, mock_neo4j_client):
        """Test building relations for a single paper."""
        mock_neo4j_client.get_all_papers_with_relations = AsyncMock(
            return_value=[
                {"paper_id": "p1", "sub_domains": ["Degenerative"], "pathologies": ["Stenosis"], "interventions": ["TLIF"], "anatomy_levels": []},
                {"paper_id": "p2", "sub_domains": ["Degenerative"], "pathologies": ["Stenosis"], "interventions": ["PLIF"], "anatomy_levels": []}
            ]
        )

        result = await graph_handler.build_paper_relations(
            paper_id="p1",
            min_similarity=0.3
        )

        assert result["success"] is True
        assert result["papers_processed"] == 1

    @pytest.mark.asyncio
    async def test_build_relations_no_papers(self, graph_handler, mock_neo4j_client):
        """Test handling of empty database."""
        mock_neo4j_client.get_all_papers_with_relations = AsyncMock(return_value=[])

        result = await graph_handler.build_paper_relations()

        assert result["success"] is True
        assert result["relations_created"] == 0


class TestCalculatePaperSimilarity:
    """Test _calculate_paper_similarity method."""

    def test_similarity_identical_papers(self, graph_handler):
        """Test similarity of identical papers."""
        paper = {
            "sub_domains": ["Degenerative"],
            "pathologies": ["Stenosis"],
            "interventions": ["TLIF"],
            "anatomy_levels": ["L4-L5"]
        }

        similarity = graph_handler._calculate_paper_similarity(paper, paper)
        assert similarity == 1.0

    def test_similarity_no_overlap(self, graph_handler):
        """Test similarity of completely different papers."""
        paper1 = {
            "sub_domains": ["Degenerative"],
            "pathologies": ["Stenosis"],
            "interventions": ["TLIF"],
            "anatomy_levels": ["L4-L5"]
        }
        paper2 = {
            "sub_domains": ["Trauma"],
            "pathologies": ["Fracture"],
            "interventions": ["Instrumentation"],
            "anatomy_levels": ["T12-L1"]
        }

        similarity = graph_handler._calculate_paper_similarity(paper1, paper2)
        assert similarity == 0.0

    def test_similarity_partial_overlap(self, graph_handler):
        """Test similarity with partial overlap."""
        paper1 = {
            "sub_domains": ["Degenerative"],
            "pathologies": ["Stenosis"],
            "interventions": ["TLIF"],
            "anatomy_levels": ["L4-L5"]
        }
        paper2 = {
            "sub_domains": ["Degenerative"],
            "pathologies": ["Spondylolisthesis"],
            "interventions": ["PLIF"],
            "anatomy_levels": ["L4-L5"]
        }

        similarity = graph_handler._calculate_paper_similarity(paper1, paper2)
        assert 0.0 < similarity < 1.0

    def test_similarity_handles_nested_lists(self, graph_handler):
        """Test similarity calculation with nested list structures."""
        paper1 = {
            "sub_domains": [["Degenerative"]],
            "pathologies": ["Stenosis"],
            "interventions": ["TLIF"],
            "anatomy_levels": []
        }
        paper2 = {
            "sub_domains": ["Degenerative"],
            "pathologies": ["Stenosis"],
            "interventions": ["TLIF"],
            "anatomy_levels": []
        }

        similarity = graph_handler._calculate_paper_similarity(paper1, paper2)
        assert similarity > 0.5


class TestCompareInterventions:
    """Test compare_interventions method."""

    @pytest.mark.asyncio
    async def test_compare_interventions_success(self, graph_handler, mock_server):
        """Test successful intervention comparison."""
        mock_server.search_handler = MagicMock()
        mock_server.search_handler.find_evidence = AsyncMock(
            side_effect=[
                {
                    "success": True,
                    "evidence": [
                        {"p_value": 0.01, "is_significant": True},
                        {"p_value": 0.03, "is_significant": True}
                    ]
                },
                {
                    "success": True,
                    "evidence": [
                        {"p_value": 0.15, "is_significant": False}
                    ]
                }
            ]
        )

        result = await graph_handler.compare_interventions(
            "TLIF",
            "PLIF",
            "VAS"
        )

        assert result["success"] is True
        assert result["outcome"] == "VAS"
        assert result["comparison"]["intervention1"]["significant_studies"] == 2
        assert result["comparison"]["intervention2"]["significant_studies"] == 0
        assert "TLIF" in result["comparison"]["recommendation"]

    @pytest.mark.asyncio
    async def test_compare_interventions_equal_evidence(self, graph_handler, mock_server):
        """Test comparison with equal evidence levels."""
        mock_server.search_handler = MagicMock()
        mock_server.search_handler.find_evidence = AsyncMock(
            return_value={
                "success": True,
                "evidence": [{"p_value": 0.01, "is_significant": True}]
            }
        )

        result = await graph_handler.compare_interventions("TLIF", "PLIF", "VAS")

        assert result["success"] is True
        assert "similar evidence" in result["comparison"]["recommendation"]

    @pytest.mark.asyncio
    async def test_compare_interventions_no_graph_searcher(self, mock_server):
        """Test error when graph searcher not available."""
        mock_server.graph_searcher = None
        # Create new handler with modified server
        handler = GraphHandler(mock_server)

        result = await handler.compare_interventions("TLIF", "PLIF", "VAS")

        assert result["success"] is False


class TestGetComparableInterventions:
    """Test get_comparable_interventions method."""

    @pytest.mark.asyncio
    async def test_get_comparable_success(self, graph_handler, mock_neo4j_client):
        """Test retrieval of comparable interventions."""
        with patch('graph.taxonomy_manager.TaxonomyManager') as mock_tax:
            tax_instance = Mock()
            tax_instance.get_parent_interventions = AsyncMock(
                return_value=["Lumbar Interbody Fusion"]
            )
            tax_instance.get_child_interventions = AsyncMock(
                return_value=["TLIF", "PLIF", "ALIF"]
            )
            mock_tax.return_value = tax_instance

            result = await graph_handler.get_comparable_interventions("TLIF")

            assert result["success"] is True
            assert result["intervention"] == "TLIF"
            assert "PLIF" in result["comparable_interventions"]
            assert "TLIF" not in result["comparable_interventions"]

    @pytest.mark.asyncio
    async def test_get_comparable_no_parents(self, graph_handler, mock_neo4j_client):
        """Test handling when intervention has no parents."""
        with patch('graph.taxonomy_manager.TaxonomyManager') as mock_tax:
            tax_instance = Mock()
            tax_instance.get_parent_interventions = AsyncMock(return_value=[])
            mock_tax.return_value = tax_instance

            result = await graph_handler.get_comparable_interventions("TLIF")

            assert result["success"] is True
            assert result["comparable_interventions"] == []


class TestGetInterventionHierarchyWithDirection:
    """Test get_intervention_hierarchy_with_direction method."""

    @pytest.mark.asyncio
    async def test_hierarchy_both_directions(self, graph_handler, mock_neo4j_client):
        """Test hierarchy with both ancestors and descendants."""
        with patch('graph.taxonomy_manager.TaxonomyManager') as mock_tax:
            tax_instance = Mock()
            tax_instance.get_parent_interventions = AsyncMock(
                return_value=["Lumbar Interbody Fusion", "Spinal Fusion"]
            )
            tax_instance.get_child_interventions = AsyncMock(
                return_value=["MIS-TLIF"]
            )
            mock_tax.return_value = tax_instance

            result = await graph_handler.get_intervention_hierarchy_with_direction(
                "TLIF",
                direction="both"
            )

            assert result["success"] is True
            assert result["ancestor_count"] == 2
            assert result["descendant_count"] == 1

    @pytest.mark.asyncio
    async def test_hierarchy_ancestors_only(self, graph_handler, mock_neo4j_client):
        """Test hierarchy with ancestors only."""
        with patch('graph.taxonomy_manager.TaxonomyManager') as mock_tax:
            tax_instance = Mock()
            tax_instance.get_parent_interventions = AsyncMock(
                return_value=["Lumbar Interbody Fusion"]
            )
            mock_tax.return_value = tax_instance

            result = await graph_handler.get_intervention_hierarchy_with_direction(
                "TLIF",
                direction="ancestors"
            )

            assert result["success"] is True
            assert "ancestors" in result
            assert "descendants" not in result

    @pytest.mark.asyncio
    async def test_hierarchy_descendants_only(self, graph_handler, mock_neo4j_client):
        """Test hierarchy with descendants only."""
        with patch('graph.taxonomy_manager.TaxonomyManager') as mock_tax:
            tax_instance = Mock()
            tax_instance.get_child_interventions = AsyncMock(
                return_value=["MIS-TLIF"]
            )
            mock_tax.return_value = tax_instance

            result = await graph_handler.get_intervention_hierarchy_with_direction(
                "TLIF",
                direction="descendants"
            )

            assert result["success"] is True
            assert "descendants" in result
            assert "ancestors" not in result


class TestInferRelations:
    """Test infer_relations method."""

    @pytest.mark.asyncio
    async def test_infer_with_rule_name(self, graph_handler, mock_neo4j_client):
        """Test inference with specific rule."""
        with patch('graph.inference_rules.InferenceEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.execute_rule = AsyncMock(
                return_value=[{"result": "test"}]
            )

            @dataclass
            class MockRule:
                rule_type: Mock = Mock(value="transitive")
                confidence_weight: float = 0.8

            mock_engine.get_rule.return_value = MockRule()
            mock_engine_class.return_value = mock_engine

            result = await graph_handler.infer_relations(
                rule_name="transitive_affects",
                intervention="TLIF",
                outcome="VAS"
            )

            assert result["success"] is True
            assert result["rule_name"] == "transitive_affects"

    @pytest.mark.asyncio
    async def test_infer_with_intervention_and_outcome(self, graph_handler, mock_neo4j_client):
        """Test auto-selection with intervention and outcome."""
        with patch('graph.inference_rules.InferenceEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.aggregate_evidence = AsyncMock(return_value={"evidence": "aggregated"})
            mock_engine.detect_conflicts = AsyncMock(return_value={"conflicts": []})
            mock_engine_class.return_value = mock_engine

            result = await graph_handler.infer_relations(
                intervention="TLIF",
                outcome="VAS"
            )

            assert result["success"] is True
            assert "aggregate_evidence" in result["results"]
            assert "conflicts" in result["results"]

    @pytest.mark.asyncio
    async def test_infer_with_intervention_only(self, graph_handler, mock_neo4j_client):
        """Test auto-selection with intervention only."""
        with patch('graph.inference_rules.InferenceEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.get_ancestors = AsyncMock(return_value=["parent"])
            mock_engine.get_comparable_interventions = AsyncMock(return_value=["comparable"])
            mock_engine.infer_treatments = AsyncMock(return_value=["treatment"])
            mock_engine_class.return_value = mock_engine

            result = await graph_handler.infer_relations(intervention="TLIF")

            assert result["success"] is True
            assert "ancestors" in result["results"]

    @pytest.mark.asyncio
    async def test_infer_with_pathology_only(self, graph_handler, mock_neo4j_client):
        """Test auto-selection with pathology only."""
        with patch('graph.inference_rules.InferenceEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.find_indirect_treatments = AsyncMock(return_value=["indirect"])
            mock_engine_class.return_value = mock_engine

            result = await graph_handler.infer_relations(pathology="Stenosis")

            assert result["success"] is True
            assert "indirect_treatments" in result["results"]

    @pytest.mark.asyncio
    async def test_infer_no_parameters(self, graph_handler, mock_neo4j_client):
        """Test listing available rules when no parameters provided."""
        with patch('graph.inference_rules.InferenceEngine') as mock_engine_class:
            @dataclass
            class MockRule:
                name: str = "test_rule"
                rule_type: Mock = Mock(value="transitive")
                description: str = "Test rule"
                parameters: list = None
                confidence_weight: float = 1.0

            mock_engine = Mock()
            mock_engine.list_rules.return_value = [MockRule()]
            mock_engine_class.return_value = mock_engine

            result = await graph_handler.infer_relations()

            assert result["success"] is True
            assert "available_rules" in result
            assert len(result["available_rules"]) == 1

    @pytest.mark.asyncio
    async def test_infer_invalid_rule(self, graph_handler, mock_neo4j_client):
        """Test handling of invalid rule name."""
        with patch('graph.inference_rules.InferenceEngine') as mock_engine_class:
            mock_engine = Mock()
            mock_engine.execute_rule = AsyncMock(
                side_effect=ValueError("Invalid rule")
            )
            mock_engine_class.return_value = mock_engine

            result = await graph_handler.infer_relations(rule_name="invalid_rule")

            assert result["success"] is False
            assert "Invalid rule" in result["error"]

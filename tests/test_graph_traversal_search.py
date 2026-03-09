"""Tests for graph_traversal_search.py — multi-hop evidence chain search.

Tests cover:
- EvidenceChainResult / InterventionComparison / BestEvidenceResult dataclasses
- traverse_evidence_chain() with mocked Neo4j
- compare_interventions() with mocked Neo4j
- find_best_evidence() with mocked Neo4j
- is_a_depth clamping (1-5 safety)
- Error handling for Neo4j failures
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.solver.graph_traversal_search import (
    EvidenceChainLink,
    EvidenceChainResult,
    InterventionComparison,
    BestEvidenceResult,
    GraphTraversalSearch,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_neo4j():
    """Create a mock Neo4j client."""
    client = AsyncMock()
    client.run_query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def search(mock_neo4j):
    """Create a GraphTraversalSearch with mocked client."""
    return GraphTraversalSearch(neo4j_client=mock_neo4j)


# ---------------------------------------------------------------------------
# Dataclass Tests
# ---------------------------------------------------------------------------

class TestDataclasses:
    """Test dataclass construction and defaults."""

    def test_evidence_chain_link_defaults(self):
        link = EvidenceChainLink(
            source_node="TLIF",
            relationship="TREATS",
            target_node="Spinal Stenosis",
        )
        assert link.source_node == "TLIF"
        assert link.relationship == "TREATS"
        assert link.target_node == "Spinal Stenosis"
        assert link.properties == {}

    def test_evidence_chain_link_with_properties(self):
        link = EvidenceChainLink(
            source_node="TLIF",
            relationship="AFFECTS",
            target_node="ODI",
            properties={"p_value": 0.001, "direction": "improved"},
        )
        assert link.properties["p_value"] == 0.001

    def test_evidence_chain_result_defaults(self):
        result = EvidenceChainResult(intervention="TLIF", pathology="Stenosis")
        assert result.intervention == "TLIF"
        assert result.pathology == "Stenosis"
        assert result.outcomes == []
        assert result.direct_evidence == []
        assert result.related_evidence == []
        assert result.evidence_chain == []

    def test_intervention_comparison_defaults(self):
        comp = InterventionComparison(
            intervention1="TLIF",
            intervention2="PLIF",
            pathology="Stenosis",
        )
        assert comp.shared_outcomes == []
        assert comp.int1_only_outcomes == []
        assert comp.int2_only_outcomes == []
        assert comp.comparison_summary == ""

    def test_best_evidence_result_defaults(self):
        ber = BestEvidenceResult(paper_id="P001", title="Test Paper")
        assert ber.evidence_level == "5"
        assert ber.year == 0
        assert ber.interventions == []
        assert ber.outcomes == []
        assert ber.evidence_chain == []


# ---------------------------------------------------------------------------
# traverse_evidence_chain Tests
# ---------------------------------------------------------------------------

class TestTraverseEvidenceChain:
    """Test traverse_evidence_chain method."""

    @pytest.mark.asyncio
    async def test_empty_result(self, search, mock_neo4j):
        """No results from Neo4j → empty chain."""
        mock_neo4j.run_query.return_value = []

        result = await search.traverse_evidence_chain("TLIF", "Stenosis")

        assert isinstance(result, EvidenceChainResult)
        assert result.intervention == "TLIF"
        assert result.pathology == "Stenosis"
        assert len(result.direct_evidence) == 0
        assert len(result.related_evidence) == 0

    @pytest.mark.asyncio
    async def test_direct_evidence_populated(self, search, mock_neo4j):
        """Direct evidence rows are returned correctly."""
        direct_rows = [
            {
                "paper_id": "P001",
                "title": "TLIF for Stenosis",
                "year": 2024,
                "evidence_level": "2a",
                "outcome_name": "ODI",
                "value": "35.2",
                "p_value": 0.001,
                "direction": "improved",
                "effect_size": "0.8",
                "is_significant": True,
                "has_treats_link": True,
            },
        ]
        # First call = direct query, second call = related query
        mock_neo4j.run_query.side_effect = [direct_rows, []]

        result = await search.traverse_evidence_chain("TLIF", "Stenosis")

        assert len(result.direct_evidence) == 1
        assert result.direct_evidence[0]["paper_id"] == "P001"
        assert result.direct_evidence[0]["p_value"] == 0.001
        assert len(result.outcomes) == 1
        assert result.outcomes[0]["name"] == "ODI"

    @pytest.mark.asyncio
    async def test_related_evidence_populated(self, search, mock_neo4j):
        """Related evidence via IS_A is returned correctly."""
        related_rows = [
            {
                "related_intervention": "MIS-TLIF",
                "paper_id": "P002",
                "title": "MIS-TLIF Study",
                "year": 2023,
                "evidence_level": "2b",
                "outcome_name": "VAS",
                "direction": "improved",
                "p_value": 0.05,
            },
        ]
        mock_neo4j.run_query.side_effect = [[], related_rows]

        result = await search.traverse_evidence_chain("TLIF", "Stenosis")

        assert len(result.related_evidence) == 1
        assert result.related_evidence[0]["related_intervention"] == "MIS-TLIF"

    @pytest.mark.asyncio
    async def test_outcome_filter(self, search, mock_neo4j):
        """Outcome filter excludes non-matching outcomes."""
        rows = [
            {
                "paper_id": "P001",
                "title": "Test",
                "year": 2024,
                "evidence_level": "2a",
                "outcome_name": "ODI",
                "value": "35",
                "p_value": 0.01,
                "direction": "improved",
                "effect_size": "",
                "is_significant": True,
                "has_treats_link": True,
            },
            {
                "paper_id": "P001",
                "title": "Test",
                "year": 2024,
                "evidence_level": "2a",
                "outcome_name": "VAS",
                "value": "3.5",
                "p_value": 0.02,
                "direction": "improved",
                "effect_size": "",
                "is_significant": True,
                "has_treats_link": True,
            },
        ]
        mock_neo4j.run_query.side_effect = [rows, []]

        result = await search.traverse_evidence_chain(
            "TLIF", "Stenosis", outcome="ODI"
        )

        # Only ODI should be included
        assert len(result.direct_evidence) == 1
        assert result.direct_evidence[0]["outcome"] == "ODI"

    @pytest.mark.asyncio
    async def test_evidence_chain_links_built(self, search, mock_neo4j):
        """Evidence chain links are constructed for TREATS and AFFECTS."""
        rows = [
            {
                "paper_id": "P001",
                "title": "Test",
                "year": 2024,
                "evidence_level": "2a",
                "outcome_name": "ODI",
                "value": "35",
                "p_value": 0.01,
                "direction": "improved",
                "effect_size": "",
                "is_significant": True,
                "has_treats_link": True,
            },
        ]
        mock_neo4j.run_query.side_effect = [rows, []]

        result = await search.traverse_evidence_chain("TLIF", "Stenosis")

        # Should have TREATS and AFFECTS chain links
        treats_links = [
            c for c in result.evidence_chain if c.relationship == "TREATS"
        ]
        affects_links = [
            c for c in result.evidence_chain if c.relationship == "AFFECTS"
        ]
        assert len(treats_links) >= 1
        assert len(affects_links) >= 1
        assert treats_links[0].target_node == "Stenosis"
        assert affects_links[0].target_node == "ODI"

    @pytest.mark.asyncio
    async def test_outcome_deduplication(self, search, mock_neo4j):
        """Duplicate outcomes are deduplicated."""
        rows = [
            {
                "paper_id": "P001", "title": "Test", "year": 2024,
                "evidence_level": "2a", "outcome_name": "ODI",
                "value": "35", "p_value": 0.01, "direction": "improved",
                "effect_size": "", "is_significant": True, "has_treats_link": True,
            },
            {
                "paper_id": "P002", "title": "Test2", "year": 2023,
                "evidence_level": "2b", "outcome_name": "ODI",
                "value": "40", "p_value": 0.02, "direction": "improved",
                "effect_size": "", "is_significant": True, "has_treats_link": True,
            },
        ]
        mock_neo4j.run_query.side_effect = [rows, []]

        result = await search.traverse_evidence_chain("TLIF", "Stenosis")

        # ODI should appear only once in outcomes
        assert len(result.outcomes) == 1
        assert result.outcomes[0]["name"] == "ODI"

    @pytest.mark.asyncio
    async def test_neo4j_error_handled(self, search, mock_neo4j):
        """Neo4j errors are caught and logged, not raised."""
        mock_neo4j.run_query.side_effect = Exception("Connection lost")

        result = await search.traverse_evidence_chain("TLIF", "Stenosis")

        assert isinstance(result, EvidenceChainResult)
        assert len(result.direct_evidence) == 0


# ---------------------------------------------------------------------------
# is_a_depth Clamping Tests
# ---------------------------------------------------------------------------

class TestIsADepthClamping:
    """Test that is_a_depth is clamped to 1-5."""

    @pytest.mark.asyncio
    async def test_depth_clamped_low(self, search, mock_neo4j):
        """is_a_depth < 1 gets clamped to 1."""
        mock_neo4j.run_query.return_value = []

        await search.traverse_evidence_chain("TLIF", "Stenosis", is_a_depth=0)

        # Verify the related query uses depth 1
        calls = mock_neo4j.run_query.call_args_list
        assert len(calls) >= 2
        related_query = calls[1][0][0]  # second call's first positional arg
        assert "IS_A*1..1" in related_query

    @pytest.mark.asyncio
    async def test_depth_clamped_high(self, search, mock_neo4j):
        """is_a_depth > 5 gets clamped to 5."""
        mock_neo4j.run_query.return_value = []

        await search.traverse_evidence_chain("TLIF", "Stenosis", is_a_depth=100)

        calls = mock_neo4j.run_query.call_args_list
        assert len(calls) >= 2
        related_query = calls[1][0][0]
        assert "IS_A*1..5" in related_query

    @pytest.mark.asyncio
    async def test_depth_normal(self, search, mock_neo4j):
        """Normal is_a_depth=3 is used as-is."""
        mock_neo4j.run_query.return_value = []

        await search.traverse_evidence_chain("TLIF", "Stenosis", is_a_depth=3)

        calls = mock_neo4j.run_query.call_args_list
        assert len(calls) >= 2
        related_query = calls[1][0][0]
        assert "IS_A*1..3" in related_query

    @pytest.mark.asyncio
    async def test_find_best_evidence_depth_clamped(self, search, mock_neo4j):
        """find_best_evidence also clamps is_a_depth."""
        mock_neo4j.run_query.return_value = []

        await search.find_best_evidence("Stenosis", is_a_depth=0)

        calls = mock_neo4j.run_query.call_args_list
        query = calls[0][0][0]
        assert "IS_A*0..1" in query

    @pytest.mark.asyncio
    async def test_find_best_evidence_depth_clamped_high(self, search, mock_neo4j):
        """find_best_evidence clamps is_a_depth > 5."""
        mock_neo4j.run_query.return_value = []

        await search.find_best_evidence("Stenosis", is_a_depth=99)

        calls = mock_neo4j.run_query.call_args_list
        query = calls[0][0][0]
        assert "IS_A*0..5" in query


# ---------------------------------------------------------------------------
# compare_interventions Tests
# ---------------------------------------------------------------------------

class TestCompareInterventions:
    """Test compare_interventions method."""

    @pytest.mark.asyncio
    async def test_empty_comparison(self, search, mock_neo4j):
        """No results → empty comparison."""
        mock_neo4j.run_query.return_value = []

        result = await search.compare_interventions("TLIF", "PLIF", "Stenosis")

        assert isinstance(result, InterventionComparison)
        assert result.intervention1 == "TLIF"
        assert result.intervention2 == "PLIF"
        assert result.pathology == "Stenosis"

    @pytest.mark.asyncio
    async def test_shared_outcomes(self, search, mock_neo4j):
        """Shared outcomes are identified correctly."""
        mock_neo4j.run_query.return_value = [
            {
                "int1_outcomes": [
                    {"outcome": "ODI", "value": "35", "p_value": 0.01,
                     "direction": "improved", "effect_size": "0.8",
                     "paper_id": "P1", "evidence_level": "2a"},
                    {"outcome": "VAS", "value": "3.5", "p_value": 0.02,
                     "direction": "improved", "effect_size": "0.6",
                     "paper_id": "P1", "evidence_level": "2a"},
                ],
                "int2_outcomes": [
                    {"outcome": "ODI", "value": "38", "p_value": 0.02,
                     "direction": "improved", "effect_size": "0.7",
                     "paper_id": "P2", "evidence_level": "2b"},
                    {"outcome": "Fusion Rate", "value": "95%", "p_value": 0.05,
                     "direction": "positive", "effect_size": "",
                     "paper_id": "P2", "evidence_level": "2b"},
                ],
            }
        ]

        result = await search.compare_interventions("TLIF", "PLIF", "Stenosis")

        # ODI is shared
        assert len(result.shared_outcomes) == 1
        assert result.shared_outcomes[0]["outcome"] == "ODI"

        # VAS is TLIF-only, Fusion Rate is PLIF-only
        assert len(result.int1_only_outcomes) == 1
        assert result.int1_only_outcomes[0]["outcome"] == "VAS"
        assert len(result.int2_only_outcomes) == 1
        assert result.int2_only_outcomes[0]["outcome"] == "Fusion Rate"

        assert "1 shared" in result.comparison_summary

    @pytest.mark.asyncio
    async def test_neo4j_error_handled(self, search, mock_neo4j):
        """Neo4j errors are caught in compare_interventions."""
        mock_neo4j.run_query.side_effect = Exception("DB error")

        result = await search.compare_interventions("TLIF", "PLIF", "Stenosis")

        assert "failed" in result.comparison_summary.lower()


# ---------------------------------------------------------------------------
# find_best_evidence Tests
# ---------------------------------------------------------------------------

class TestFindBestEvidence:
    """Test find_best_evidence method."""

    @pytest.mark.asyncio
    async def test_empty_results(self, search, mock_neo4j):
        """No matching papers → empty list."""
        mock_neo4j.run_query.return_value = []

        results = await search.find_best_evidence("Stenosis")

        assert results == []

    @pytest.mark.asyncio
    async def test_results_populated(self, search, mock_neo4j):
        """Results are returned with correct fields."""
        mock_neo4j.run_query.return_value = [
            {
                "paper_id": "P001",
                "title": "TLIF for Stenosis Meta-analysis",
                "year": 2024,
                "evidence_level": "1a",
                "interventions": ["TLIF"],
                "outcomes": ["ODI", "VAS"],
                "outcome_details": [
                    {"outcome": "ODI", "direction": "improved", "p_value": 0.001},
                    {"outcome": "VAS", "direction": "improved", "p_value": 0.01},
                ],
            },
            {
                "paper_id": "P002",
                "title": "PLIF RCT",
                "year": 2023,
                "evidence_level": "1b",
                "interventions": ["PLIF"],
                "outcomes": ["ODI"],
                "outcome_details": [
                    {"outcome": "ODI", "direction": "improved", "p_value": 0.02},
                ],
            },
        ]

        results = await search.find_best_evidence("Stenosis")

        assert len(results) == 2
        assert results[0].paper_id == "P001"
        assert results[0].evidence_level == "1a"
        assert "TLIF" in results[0].interventions
        assert "ODI" in results[0].outcomes
        assert len(results[0].evidence_chain) > 0

    @pytest.mark.asyncio
    async def test_outcome_category_filter(self, search, mock_neo4j):
        """outcome_category filters results."""
        mock_neo4j.run_query.return_value = [
            {
                "paper_id": "P001",
                "title": "Test",
                "year": 2024,
                "evidence_level": "2a",
                "interventions": ["TLIF"],
                "outcomes": ["ODI", "VAS"],
                "outcome_details": [
                    {"outcome": "ODI", "direction": "improved", "p_value": 0.01},
                ],
            },
            {
                "paper_id": "P002",
                "title": "Test2",
                "year": 2023,
                "evidence_level": "2b",
                "interventions": ["PLIF"],
                "outcomes": ["Fusion Rate"],
                "outcome_details": [
                    {"outcome": "Fusion Rate", "direction": "positive", "p_value": 0.05},
                ],
            },
        ]

        results = await search.find_best_evidence(
            "Stenosis", outcome_category="ODI"
        )

        # Only P001 has ODI
        assert len(results) == 1
        assert results[0].paper_id == "P001"

    @pytest.mark.asyncio
    async def test_null_evidence_level_defaults(self, search, mock_neo4j):
        """Null evidence_level defaults to '5'."""
        mock_neo4j.run_query.return_value = [
            {
                "paper_id": "P001",
                "title": "Test",
                "year": 2024,
                "evidence_level": None,
                "interventions": ["TLIF"],
                "outcomes": ["ODI"],
                "outcome_details": [],
            },
        ]

        results = await search.find_best_evidence("Stenosis")

        assert results[0].evidence_level == "5"

    @pytest.mark.asyncio
    async def test_null_year_defaults(self, search, mock_neo4j):
        """Null year defaults to 0."""
        mock_neo4j.run_query.return_value = [
            {
                "paper_id": "P001",
                "title": "Test",
                "year": None,
                "evidence_level": "3",
                "interventions": ["TLIF"],
                "outcomes": [],
                "outcome_details": [],
            },
        ]

        results = await search.find_best_evidence("Stenosis")

        assert results[0].year == 0

    @pytest.mark.asyncio
    async def test_neo4j_error_handled(self, search, mock_neo4j):
        """Neo4j errors are caught in find_best_evidence."""
        mock_neo4j.run_query.side_effect = Exception("Query failed")

        results = await search.find_best_evidence("Stenosis")

        assert results == []


# ---------------------------------------------------------------------------
# Constructor Tests
# ---------------------------------------------------------------------------

class TestGraphTraversalSearchInit:
    """Test constructor."""

    def test_init_minimal(self, mock_neo4j):
        s = GraphTraversalSearch(neo4j_client=mock_neo4j)
        assert s.client is mock_neo4j
        assert s.taxonomy_manager is None

    def test_init_with_taxonomy(self, mock_neo4j):
        tm = MagicMock()
        s = GraphTraversalSearch(neo4j_client=mock_neo4j, taxonomy_manager=tm)
        assert s.taxonomy_manager is tm

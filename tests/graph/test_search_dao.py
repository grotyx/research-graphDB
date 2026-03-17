"""Tests for graph/search_dao.py module.

Tests cover:
- SearchDAO initialization
- vector_search_chunks() with various filter combinations
- hybrid_search() with graph filters and SNOMED codes
- Delegation methods (hierarchy, children, effective interventions, pathology, conflicts)
- Error handling (query failures return empty lists)
- Parameter validation and construction
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from graph.search_dao import SearchDAO


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_run_query():
    """Mock run_query callable."""
    return AsyncMock(return_value=[])


@pytest.fixture
def dao(mock_run_query):
    """SearchDAO with mocked query function."""
    return SearchDAO(run_query=mock_run_query)


@pytest.fixture
def sample_embedding():
    """Sample embedding vector (small for testing)."""
    return [0.1] * 10


# ===========================================================================
# Tests: Initialization
# ===========================================================================

class TestSearchDAOInit:
    """Test SearchDAO initialization."""

    def test_init_with_callable(self, mock_run_query):
        """Initialize with a callable run_query."""
        dao = SearchDAO(run_query=mock_run_query)
        assert dao._run_query is mock_run_query

    def test_init_stores_reference(self):
        """Stored reference is the same callable."""
        func = AsyncMock()
        dao = SearchDAO(run_query=func)
        assert dao._run_query is func


# ===========================================================================
# Tests: vector_search_chunks
# ===========================================================================

class TestVectorSearchChunks:
    """Test vector_search_chunks method."""

    @pytest.mark.asyncio
    async def test_basic_search(self, dao, mock_run_query, sample_embedding):
        """Basic vector search with defaults."""
        mock_run_query.return_value = [
            {"chunk_id": "c1", "content": "test", "score": 0.9}
        ]
        result = await dao.vector_search_chunks(sample_embedding)

        mock_run_query.assert_called_once()
        args = mock_run_query.call_args[0]
        params = args[1]
        assert params["embedding"] == sample_embedding
        assert params["min_score"] == 0.5
        assert params["limit"] == 10
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_with_tier_filter(self, dao, mock_run_query, sample_embedding):
        """Vector search with tier filter."""
        await dao.vector_search_chunks(sample_embedding, tier="tier1")

        params = mock_run_query.call_args[0][1]
        assert params["tier"] == "tier1"

    @pytest.mark.asyncio
    async def test_with_evidence_level(self, dao, mock_run_query, sample_embedding):
        """Vector search with single evidence level filter."""
        await dao.vector_search_chunks(sample_embedding, evidence_level="1b")

        params = mock_run_query.call_args[0][1]
        assert params["evidence_level"] == "1b"

    @pytest.mark.asyncio
    async def test_with_evidence_levels(self, dao, mock_run_query, sample_embedding):
        """Vector search with multiple evidence levels."""
        await dao.vector_search_chunks(
            sample_embedding, evidence_levels=["1a", "1b", "2a"]
        )

        params = mock_run_query.call_args[0][1]
        assert params["evidence_levels"] == ["1a", "1b", "2a"]

    @pytest.mark.asyncio
    async def test_evidence_level_singular_takes_precedence(self, dao, mock_run_query, sample_embedding):
        """Single evidence_level takes precedence over evidence_levels."""
        await dao.vector_search_chunks(
            sample_embedding, evidence_level="1b", evidence_levels=["2a", "2b"]
        )

        params = mock_run_query.call_args[0][1]
        assert params["evidence_level"] == "1b"
        assert "evidence_levels" not in params

    @pytest.mark.asyncio
    async def test_with_min_year(self, dao, mock_run_query, sample_embedding):
        """Vector search with min_year filter."""
        await dao.vector_search_chunks(sample_embedding, min_year=2020)

        params = mock_run_query.call_args[0][1]
        assert params["min_year"] == 2020

    @pytest.mark.asyncio
    async def test_custom_top_k(self, dao, mock_run_query, sample_embedding):
        """Custom top_k value."""
        await dao.vector_search_chunks(sample_embedding, top_k=5)

        params = mock_run_query.call_args[0][1]
        assert params["limit"] == 5
        # Internal top_k is multiplied by 3 for pre-filter
        assert params["top_k"] == 15

    @pytest.mark.asyncio
    async def test_custom_min_score(self, dao, mock_run_query, sample_embedding):
        """Custom min_score threshold."""
        await dao.vector_search_chunks(sample_embedding, min_score=0.8)

        params = mock_run_query.call_args[0][1]
        assert params["min_score"] == 0.8

    @pytest.mark.asyncio
    async def test_query_failure_returns_empty(self, dao, mock_run_query, sample_embedding):
        """Query failure returns empty list (not exception)."""
        mock_run_query.side_effect = RuntimeError("Connection failed")
        result = await dao.vector_search_chunks(sample_embedding)
        assert result == []

    @pytest.mark.asyncio
    async def test_query_contains_vector_index_call(self, dao, mock_run_query, sample_embedding):
        """Generated query uses chunk_embedding_index."""
        await dao.vector_search_chunks(sample_embedding)

        query = mock_run_query.call_args[0][0]
        assert "chunk_embedding_index" in query
        assert "ORDER BY score DESC" in query


# ===========================================================================
# Tests: hybrid_search
# ===========================================================================

class TestHybridSearch:
    """Test hybrid_search method."""

    @pytest.mark.asyncio
    async def test_basic_hybrid_search(self, dao, mock_run_query, sample_embedding):
        """Basic hybrid search without filters."""
        mock_run_query.return_value = [
            {"chunk_id": "c1", "final_score": 0.85}
        ]
        result = await dao.hybrid_search(sample_embedding)

        mock_run_query.assert_called_once()
        params = mock_run_query.call_args[0][1]
        assert params["graph_weight"] == 0.6
        assert params["vector_weight"] == 0.4
        assert params["limit"] == 10
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_with_intervention_filter(self, dao, mock_run_query, sample_embedding):
        """Hybrid search with single intervention filter."""
        await dao.hybrid_search(
            sample_embedding, graph_filters={"intervention": "UBE"}
        )

        query = mock_run_query.call_args[0][0]
        params = mock_run_query.call_args[0][1]
        assert params["intervention"] == "UBE"
        assert "INVESTIGATES" in query

    @pytest.mark.asyncio
    async def test_with_interventions_plural(self, dao, mock_run_query, sample_embedding):
        """Plural interventions list takes precedence over singular."""
        await dao.hybrid_search(
            sample_embedding,
            graph_filters={"interventions": ["UBE", "TLIF"], "intervention": "UBE"},
        )

        params = mock_run_query.call_args[0][1]
        assert params["interventions"] == ["UBE", "TLIF"]
        assert "intervention" not in params

    @pytest.mark.asyncio
    async def test_with_pathology_filter(self, dao, mock_run_query, sample_embedding):
        """Hybrid search with pathology filter."""
        await dao.hybrid_search(
            sample_embedding, graph_filters={"pathology": "Lumbar Stenosis"}
        )

        query = mock_run_query.call_args[0][0]
        params = mock_run_query.call_args[0][1]
        assert params["pathology"] == "Lumbar Stenosis"
        assert "STUDIES" in query

    @pytest.mark.asyncio
    async def test_with_pathologies_plural(self, dao, mock_run_query, sample_embedding):
        """Plural pathologies list takes precedence."""
        await dao.hybrid_search(
            sample_embedding,
            graph_filters={"pathologies": ["Stenosis", "DDD"]},
        )

        params = mock_run_query.call_args[0][1]
        assert params["pathologies"] == ["Stenosis", "DDD"]

    @pytest.mark.asyncio
    async def test_with_outcome_filter(self, dao, mock_run_query, sample_embedding):
        """Hybrid search with outcome filter."""
        await dao.hybrid_search(
            sample_embedding, graph_filters={"outcome": "VAS"}
        )

        query = mock_run_query.call_args[0][0]
        params = mock_run_query.call_args[0][1]
        assert params["outcome"] == "VAS"
        assert "AFFECTS" in query

    @pytest.mark.asyncio
    async def test_with_anatomy_filter(self, dao, mock_run_query, sample_embedding):
        """Hybrid search with anatomy filter."""
        await dao.hybrid_search(
            sample_embedding, graph_filters={"anatomy": "Lumbar"}
        )

        params = mock_run_query.call_args[0][1]
        assert params["anatomy"] == "Lumbar"

    @pytest.mark.asyncio
    async def test_with_evidence_levels(self, dao, mock_run_query, sample_embedding):
        """Hybrid search with evidence level WHERE filter."""
        await dao.hybrid_search(
            sample_embedding, graph_filters={"evidence_levels": ["1a", "1b"]}
        )

        query = mock_run_query.call_args[0][0]
        params = mock_run_query.call_args[0][1]
        assert params["evidence_levels"] == ["1a", "1b"]
        assert "evidence_level IN" in query

    @pytest.mark.asyncio
    async def test_with_min_year(self, dao, mock_run_query, sample_embedding):
        """Hybrid search with min_year WHERE filter."""
        await dao.hybrid_search(
            sample_embedding, graph_filters={"min_year": 2020}
        )

        params = mock_run_query.call_args[0][1]
        assert params["min_year"] == 2020

    @pytest.mark.asyncio
    async def test_custom_weights(self, dao, mock_run_query, sample_embedding):
        """Custom graph and vector weights."""
        await dao.hybrid_search(
            sample_embedding, graph_weight=0.7, vector_weight=0.3
        )

        params = mock_run_query.call_args[0][1]
        assert params["graph_weight"] == 0.7
        assert params["vector_weight"] == 0.3

    @pytest.mark.asyncio
    async def test_with_snomed_codes(self, dao, mock_run_query, sample_embedding):
        """Hybrid search with SNOMED codes enables IS_A expansion."""
        await dao.hybrid_search(
            sample_embedding, snomed_codes=["76107001", "18347007"]
        )

        query = mock_run_query.call_args[0][0]
        params = mock_run_query.call_args[0][1]
        assert params["snomed_codes"] == ["76107001", "18347007"]
        assert "IS_A" in query
        assert "snomed_boost" in query

    @pytest.mark.asyncio
    async def test_without_snomed_no_isa(self, dao, mock_run_query, sample_embedding):
        """Without SNOMED codes, no IS_A expansion in query."""
        await dao.hybrid_search(sample_embedding)

        query = mock_run_query.call_args[0][0]
        assert "snomed_boost" not in query

    @pytest.mark.asyncio
    async def test_query_failure_returns_empty(self, dao, mock_run_query, sample_embedding):
        """Query failure returns empty list."""
        mock_run_query.side_effect = RuntimeError("Neo4j down")
        result = await dao.hybrid_search(sample_embedding)
        assert result == []

    @pytest.mark.asyncio
    async def test_result_ordering(self, dao, mock_run_query, sample_embedding):
        """Results are ordered by final_score DESC."""
        await dao.hybrid_search(sample_embedding)

        query = mock_run_query.call_args[0][0]
        assert "ORDER BY final_score DESC" in query

    @pytest.mark.asyncio
    async def test_empty_graph_filters(self, dao, mock_run_query, sample_embedding):
        """Empty graph_filters dict works without errors."""
        await dao.hybrid_search(sample_embedding, graph_filters={})
        mock_run_query.assert_called_once()


# ===========================================================================
# Tests: Delegation Methods
# ===========================================================================

class TestDelegationMethods:
    """Test simple delegation methods that use CypherTemplates."""

    @pytest.mark.asyncio
    async def test_get_intervention_hierarchy(self, dao, mock_run_query):
        """get_intervention_hierarchy delegates to run_query."""
        mock_run_query.return_value = [{"name": "TLIF", "parent": "Fusion"}]
        result = await dao.get_intervention_hierarchy("TLIF")

        mock_run_query.assert_called_once()
        params = mock_run_query.call_args[0][1]
        assert params["intervention_name"] == "TLIF"
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_intervention_children(self, dao, mock_run_query):
        """get_intervention_children delegates to run_query."""
        mock_run_query.return_value = [{"name": "MIS-TLIF"}, {"name": "OLIF"}]
        result = await dao.get_intervention_children("Fusion")

        params = mock_run_query.call_args[0][1]
        assert params["intervention_name"] == "Fusion"
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_search_effective_interventions(self, dao, mock_run_query):
        """search_effective_interventions delegates to run_query."""
        mock_run_query.return_value = [{"intervention": "UBE", "score": 0.9}]
        result = await dao.search_effective_interventions("VAS")

        params = mock_run_query.call_args[0][1]
        assert params["outcome_name"] == "VAS"

    @pytest.mark.asyncio
    async def test_search_interventions_for_pathology(self, dao, mock_run_query):
        """search_interventions_for_pathology delegates to run_query."""
        mock_run_query.return_value = [{"intervention": "UBE"}]
        result = await dao.search_interventions_for_pathology("Lumbar Stenosis")

        params = mock_run_query.call_args[0][1]
        assert params["pathology_name"] == "Lumbar Stenosis"

    @pytest.mark.asyncio
    async def test_find_conflicting_results(self, dao, mock_run_query):
        """find_conflicting_results delegates to run_query."""
        mock_run_query.return_value = []
        result = await dao.find_conflicting_results("UBE")

        params = mock_run_query.call_args[0][1]
        assert params["intervention_name"] == "UBE"
        assert result == []


# ===========================================================================
# Tests: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_none_graph_filters_treated_as_empty(self, dao, mock_run_query, sample_embedding):
        """None graph_filters treated as empty dict."""
        await dao.hybrid_search(sample_embedding, graph_filters=None)
        mock_run_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_filter_types_combined(self, dao, mock_run_query, sample_embedding):
        """Multiple graph filter types can be combined."""
        await dao.hybrid_search(
            sample_embedding,
            graph_filters={
                "intervention": "UBE",
                "pathology": "Stenosis",
                "evidence_levels": ["1a", "1b"],
                "min_year": 2020,
            },
        )

        params = mock_run_query.call_args[0][1]
        assert params["intervention"] == "UBE"
        assert params["pathology"] == "Stenosis"
        assert params["evidence_levels"] == ["1a", "1b"]
        assert params["min_year"] == 2020

    @pytest.mark.asyncio
    async def test_vector_search_all_filters(self, dao, mock_run_query, sample_embedding):
        """Vector search with all filters simultaneously."""
        await dao.vector_search_chunks(
            sample_embedding,
            top_k=20,
            tier="tier1",
            evidence_level="1b",
            min_year=2020,
            min_score=0.7,
        )

        params = mock_run_query.call_args[0][1]
        assert params["tier"] == "tier1"
        assert params["evidence_level"] == "1b"
        assert params["min_year"] == 2020
        assert params["min_score"] == 0.7
        assert params["limit"] == 20


# ===========================================================================
# Tests: multi_vector_search
# ===========================================================================

class TestMultiVectorSearch:
    """Test multi_vector_search method."""

    @pytest.mark.asyncio
    async def test_basic_multi_vector_search(self, dao, mock_run_query, sample_embedding):
        """Basic multi-vector search merges chunk and paper results."""
        # First call: chunk search, second call: paper search
        mock_run_query.side_effect = [
            [
                {"chunk_id": "c1", "paper_id": "p1", "content": "chunk1", "tier": "tier1",
                 "section": "abstract", "evidence_level": "1b", "is_key_finding": True,
                 "paper_title": "Paper 1", "paper_year": 2023, "score": 0.95},
                {"chunk_id": "c2", "paper_id": "p2", "content": "chunk2", "tier": "tier1",
                 "section": "results", "evidence_level": "2a", "is_key_finding": False,
                 "paper_title": "Paper 2", "paper_year": 2022, "score": 0.85},
            ],
            [
                {"chunk_id": "c3", "paper_id": "p3", "content": "chunk3", "tier": "tier1",
                 "section": "abstract", "evidence_level": "2b", "is_key_finding": False,
                 "paper_title": "Paper 3", "paper_year": 2021, "score": 0.90},
                {"chunk_id": "c1", "paper_id": "p1", "content": "chunk1", "tier": "tier1",
                 "section": "abstract", "evidence_level": "1b", "is_key_finding": True,
                 "paper_title": "Paper 1", "paper_year": 2023, "score": 0.88},
            ],
        ]

        result = await dao.multi_vector_search(sample_embedding, top_k=10)

        assert mock_run_query.call_count == 2
        # c1 appears in both lists -> highest RRF score
        assert len(result) == 3
        assert result[0]["chunk_id"] == "c1"  # in both lists

    @pytest.mark.asyncio
    async def test_multi_vector_deduplicates(self, dao, mock_run_query, sample_embedding):
        """Duplicate chunk_ids are deduplicated with combined RRF score."""
        mock_run_query.side_effect = [
            [{"chunk_id": "c1", "paper_id": "p1", "content": "x", "score": 0.9,
              "tier": "tier1", "section": "abstract", "evidence_level": "1b",
              "is_key_finding": False, "paper_title": "T", "paper_year": 2023}],
            [{"chunk_id": "c1", "paper_id": "p1", "content": "x", "score": 0.8,
              "tier": "tier1", "section": "abstract", "evidence_level": "1b",
              "is_key_finding": False, "paper_title": "T", "paper_year": 2023}],
        ]

        result = await dao.multi_vector_search(sample_embedding, top_k=10)
        assert len(result) == 1
        # RRF score = 1/(60+0+1) + 1/(60+0+1) = 2/61
        expected_rrf = 2.0 / 61.0
        assert abs(result[0]["score"] - expected_rrf) < 1e-9

    @pytest.mark.asyncio
    async def test_multi_vector_chunk_query_failure_returns_paper_only(
        self, dao, mock_run_query, sample_embedding
    ):
        """If chunk query fails, paper results are still returned."""
        mock_run_query.side_effect = [
            RuntimeError("Chunk index error"),
            [{"chunk_id": "c1", "paper_id": "p1", "content": "x", "score": 0.8,
              "tier": "tier1", "section": "abstract", "evidence_level": "2a",
              "is_key_finding": False, "paper_title": "T", "paper_year": 2023}],
        ]

        result = await dao.multi_vector_search(sample_embedding, top_k=10)
        assert len(result) == 1
        assert result[0]["chunk_id"] == "c1"

    @pytest.mark.asyncio
    async def test_multi_vector_paper_query_failure_returns_chunks(
        self, dao, mock_run_query, sample_embedding
    ):
        """If paper query fails, chunk results are still returned."""
        mock_run_query.side_effect = [
            [{"chunk_id": "c1", "paper_id": "p1", "content": "x", "score": 0.9,
              "tier": "tier1", "section": "results", "evidence_level": "1a",
              "is_key_finding": True, "paper_title": "T", "paper_year": 2024}],
            RuntimeError("Paper index error"),
        ]

        result = await dao.multi_vector_search(sample_embedding, top_k=10)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_multi_vector_both_fail_returns_empty(
        self, dao, mock_run_query, sample_embedding
    ):
        """If both queries fail, returns empty list."""
        mock_run_query.side_effect = [
            RuntimeError("Chunk fail"),
            RuntimeError("Paper fail"),
        ]

        result = await dao.multi_vector_search(sample_embedding, top_k=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_multi_vector_empty_results(self, dao, mock_run_query, sample_embedding):
        """Both queries return empty -> empty result."""
        mock_run_query.side_effect = [[], []]
        result = await dao.multi_vector_search(sample_embedding, top_k=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_multi_vector_uses_both_indexes(self, dao, mock_run_query, sample_embedding):
        """Queries use chunk_embedding_index and paper_abstract_index."""
        mock_run_query.side_effect = [[], []]
        await dao.multi_vector_search(sample_embedding)

        assert mock_run_query.call_count == 2
        chunk_query = mock_run_query.call_args_list[0][0][0]
        paper_query = mock_run_query.call_args_list[1][0][0]
        assert "chunk_embedding_index" in chunk_query
        assert "paper_abstract_index" in paper_query

    @pytest.mark.asyncio
    async def test_multi_vector_respects_top_k(self, dao, mock_run_query, sample_embedding):
        """Result count respects top_k limit."""
        mock_run_query.side_effect = [
            [{"chunk_id": f"c{i}", "paper_id": f"p{i}", "content": f"x{i}", "score": 0.9 - i * 0.01,
              "tier": "tier1", "section": "abstract", "evidence_level": "2a",
              "is_key_finding": False, "paper_title": f"T{i}", "paper_year": 2023}
             for i in range(10)],
            [],
        ]

        result = await dao.multi_vector_search(sample_embedding, top_k=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_multi_vector_custom_rrf_k(self, dao, mock_run_query, sample_embedding):
        """Custom rrf_k changes scoring."""
        mock_run_query.side_effect = [
            [{"chunk_id": "c1", "paper_id": "p1", "content": "x", "score": 0.9,
              "tier": "tier1", "section": "abstract", "evidence_level": "1b",
              "is_key_finding": False, "paper_title": "T", "paper_year": 2023}],
            [],
        ]

        result = await dao.multi_vector_search(sample_embedding, top_k=10, rrf_k=10)
        # RRF with k=10: 1/(10+0+1) = 1/11
        expected = 1.0 / 11.0
        assert abs(result[0]["score"] - expected) < 1e-9

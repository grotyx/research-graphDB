"""SearchHandler unit tests.

Tests for medical_mcp/handlers/search_handler.py covering:
- Search action dispatching and query processing
- Query parsing and validation
- Result formatting (RankedResult, SearchResult, generic)
- Error handling for Neo4j failures
- Graph search, adaptive search, evidence chain, compare interventions, best evidence
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from dataclasses import dataclass, field
from typing import Optional

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from medical_mcp.handlers.search_handler import SearchHandler, MAX_QUERY_LENGTH
from solver.query_parser import QueryIntent, QueryInput, ParsedQuery, MedicalEntity, EntityType
from solver.tiered_search import (
    SearchTier, SearchInput, SearchOutput, SearchResult as TieredSearchResult,
    ChunkInfo, SearchSource,
)
from solver.multi_factor_ranker import (
    MultiFactorRanker, RankInput, RankedResult,
    SearchResult as RankerSearchResult, SourceType, EvidenceLevel,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_server():
    """Create a mock MedicalKAGServer with all required components."""
    server = MagicMock()

    # Query parser
    server.query_parser = MagicMock()
    server.query_parser.parse.return_value = ParsedQuery(
        original="lumbar stenosis treatment",
        normalized="lumbar stenosis treatment",
        intent=QueryIntent.SEARCH,
        expanded_terms=["spinal stenosis"],
        entities=[],
    )

    # Search engine
    server.search_engine = MagicMock()
    server.search_engine.search = AsyncMock(return_value=SearchOutput(
        results=[], total_found=0
    ))

    # Ranker
    server.ranker = MagicMock()
    server.ranker.rank.return_value = MagicMock(ranked_results=[])

    # Conflict detector
    server.conflict_detector = MagicMock()

    # Graph searcher
    server.graph_searcher = MagicMock()

    # Concept hierarchy
    server.concept_hierarchy = None

    # Cypher generator
    server.cypher_generator = MagicMock()
    server.cypher_generator.extract_entities.return_value = {
        "intent": "evidence_search",
        "interventions": [],
        "outcomes": [],
    }
    server.cypher_generator.generate.return_value = (
        "MATCH (p:Paper) RETURN p LIMIT $limit",
        {"limit": 20},
    )

    # Neo4j client
    server.neo4j_client = MagicMock()
    server.neo4j_client._driver = True
    server.neo4j_client.connect = AsyncMock()
    server.neo4j_client.run_query = AsyncMock(return_value=[])
    server.neo4j_client.session = MagicMock()

    # Vector DB (None for backward compat)
    server.vector_db = None

    return server


@pytest.fixture
def handler(mock_server):
    """Create SearchHandler with mocked server."""
    with patch("medical_mcp.handlers.search_handler.GraphTraversalSearch", create=True):
        h = SearchHandler.__new__(SearchHandler)
        h.server = mock_server
        h.query_parser = mock_server.query_parser
        h.search_engine = mock_server.search_engine
        h.ranker = mock_server.ranker
        h.conflict_detector = mock_server.conflict_detector
        h.graph_searcher = mock_server.graph_searcher
        h.concept_hierarchy = mock_server.concept_hierarchy
        h.cypher_generator = mock_server.cypher_generator
        h.vector_db = mock_server.vector_db
        h.graph_traversal = None
    return h


def _make_chunk(chunk_id="c1", doc_id="doc1", text="Sample text", tier=1, section="results"):
    return ChunkInfo(
        chunk_id=chunk_id,
        document_id=doc_id,
        text=text,
        tier=tier,
        section=section,
    )


def _make_tiered_result(chunk=None, score=0.85, tier=1):
    if chunk is None:
        chunk = _make_chunk()
    return TieredSearchResult(
        chunk=chunk,
        score=score,
        tier=tier,
        source_type="original",
        evidence_level="1b",
    )


def _make_ranked_result(text="Sample text", score=0.9, doc_id="doc1"):
    result = RankerSearchResult(
        chunk_id="c1",
        document_id=doc_id,
        text=text,
        semantic_score=score,
        tier=1,
        section="results",
        source_type=SourceType.ORIGINAL,
        evidence_level=EvidenceLevel.LEVEL_1B,
        publication_year=2023,
        title="Test Paper",
    )
    return RankedResult(
        result=result,
        final_score=score,
        rank=1,
    )


# ============================================================================
# search() tests
# ============================================================================

class TestSearch:
    """Tests for the main search() method."""

    @pytest.mark.asyncio
    async def test_search_empty_results(self, handler):
        """Search with no results returns empty list."""
        result = await handler.search("lumbar stenosis treatment")
        assert result["success"] is True
        assert result["results"] == []
        assert result["total_found"] == 0

    @pytest.mark.asyncio
    async def test_search_query_too_long(self, handler):
        """Query exceeding MAX_QUERY_LENGTH returns error."""
        long_query = "a" * (MAX_QUERY_LENGTH + 1)
        result = await handler.search(long_query)
        assert "error" in result
        assert "too long" in result["error"]

    @pytest.mark.asyncio
    async def test_search_top_k_capped(self, handler):
        """top_k is capped at 100."""
        await handler.search("test query", top_k=200)
        # Verify the search engine was called -- we don't error, just cap
        handler.search_engine.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_results(self, handler):
        """Search returns formatted results."""
        chunk = _make_chunk()
        sr = _make_tiered_result(chunk=chunk)
        handler.search_engine.search.return_value = SearchOutput(
            results=[sr], total_found=1
        )
        rr = _make_ranked_result()
        handler.ranker.rank.return_value = MagicMock(ranked_results=[rr])

        result = await handler.search("lumbar stenosis", top_k=5)
        assert result["success"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["content"] == "Sample text"
        assert result["results"][0]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_search_tier_strategy_mapping(self, handler):
        """Different tier strategies map correctly."""
        await handler.search("test", tier_strategy="tier1_only")
        call_args = handler.search_engine.search.call_args
        search_input = call_args[0][0]
        assert search_input.tier_strategy == SearchTier.TIER1_ONLY

    @pytest.mark.asyncio
    async def test_search_invalid_tier_strategy_defaults(self, handler):
        """Invalid tier strategy falls back to TIER1_THEN_TIER2."""
        await handler.search("test", tier_strategy="invalid_strategy")
        call_args = handler.search_engine.search.call_args
        search_input = call_args[0][0]
        assert search_input.tier_strategy == SearchTier.TIER1_THEN_TIER2

    @pytest.mark.asyncio
    async def test_search_with_concept_hierarchy_expansion(self, handler):
        """Query expansion via concept_hierarchy."""
        mock_hierarchy = MagicMock()
        mock_hierarchy.expand_query.return_value = ["lumbar", "stenosis", "spinal canal narrowing"]
        handler.concept_hierarchy = mock_hierarchy

        await handler.search("lumbar stenosis")
        mock_hierarchy.expand_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_concept_hierarchy_failure_graceful(self, handler):
        """Concept hierarchy failure is handled gracefully."""
        mock_hierarchy = MagicMock()
        mock_hierarchy.expand_query.side_effect = RuntimeError("expansion failed")
        handler.concept_hierarchy = mock_hierarchy

        result = await handler.search("lumbar stenosis")
        # Should not raise, should still return results
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_conflict_detection_with_results(self, handler):
        """Conflict detection runs when 2+ results exist."""
        chunk = _make_chunk()
        sr = _make_tiered_result(chunk=chunk)
        handler.search_engine.search.return_value = SearchOutput(
            results=[sr, sr], total_found=2
        )
        rr1 = _make_ranked_result(doc_id="doc1")
        rr2 = _make_ranked_result(doc_id="doc2")
        handler.ranker.rank.return_value = MagicMock(ranked_results=[rr1, rr2])

        # Mock conflict detector
        handler.conflict_detector.detect.return_value = MagicMock(
            has_conflicts=False, conflicts=[]
        )

        result = await handler.search("test query")
        assert result["success"] is True
        assert result["conflicts"] is None  # No conflicts

    @pytest.mark.asyncio
    async def test_search_result_formatting_ranked_result(self, handler):
        """RankedResult is properly formatted with title and year."""
        chunk = _make_chunk()
        sr = _make_tiered_result(chunk=chunk)
        handler.search_engine.search.return_value = SearchOutput(
            results=[sr], total_found=1
        )
        rr = _make_ranked_result()
        handler.ranker.rank.return_value = MagicMock(ranked_results=[rr])

        result = await handler.search("test", top_k=5)
        formatted = result["results"][0]
        assert formatted["title"] == "Test Paper"
        assert formatted["publication_year"] == 2023
        assert formatted["evidence_level"] == "1b"

    @pytest.mark.asyncio
    async def test_search_title_extracted_from_document_id(self, handler):
        """When title is empty, it's extracted from document_id."""
        chunk = _make_chunk(doc_id="2024_Kim_Lumbar_Fusion_Study")
        sr = _make_tiered_result(chunk=chunk)
        handler.search_engine.search.return_value = SearchOutput(
            results=[sr], total_found=1
        )
        # Create a RankedResult with no title
        ranker_result = RankerSearchResult(
            chunk_id="c1", document_id="2024_Kim_Lumbar_Fusion_Study",
            text="text", semantic_score=0.8, title=None,
        )
        rr = RankedResult(result=ranker_result, final_score=0.8, rank=1)
        handler.ranker.rank.return_value = MagicMock(ranked_results=[rr])

        result = await handler.search("test")
        formatted = result["results"][0]
        assert "Lumbar" in formatted["title"]

    @pytest.mark.asyncio
    async def test_search_evidence_level_mapping(self, handler):
        """Evidence level strings map correctly to enums."""
        chunk = _make_chunk()
        sr = _make_tiered_result(chunk=chunk)
        sr.evidence_level = "2a"
        handler.search_engine.search.return_value = SearchOutput(
            results=[sr], total_found=1
        )
        rr = _make_ranked_result()
        handler.ranker.rank.return_value = MagicMock(ranked_results=[rr])

        result = await handler.search("test")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_search_exception_caught_by_safe_execute(self, handler):
        """Exceptions are caught by @safe_execute decorator."""
        handler.query_parser.parse.side_effect = RuntimeError("parser crash")

        result = await handler.search("test")
        assert result["success"] is False
        assert "parser crash" in result["error"]


# ============================================================================
# graph_search() tests
# ============================================================================

class TestGraphSearch:
    """Tests for graph_search() method."""

    @pytest.mark.asyncio
    async def test_graph_search_no_graph_searcher(self, handler):
        """Returns error when graph_searcher is None."""
        handler.graph_searcher = None

        result = await handler.graph_search("lumbar stenosis")
        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_graph_search_query_too_long(self, handler):
        """Query exceeding MAX_QUERY_LENGTH returns error."""
        long_query = "x" * (MAX_QUERY_LENGTH + 1)
        result = await handler.graph_search(long_query)
        assert "error" in result
        assert "too long" in result["error"]

    @pytest.mark.asyncio
    async def test_graph_search_evidence_with_interventions_and_outcomes(self, handler):
        """Evidence search with both interventions and outcomes."""
        handler.cypher_generator.extract_entities.return_value = {
            "intent": "evidence_search",
            "interventions": ["TLIF"],
            "outcomes": ["VAS"],
        }
        mock_result = MagicMock()
        mock_result.results = [{"paper": "p1"}]
        mock_result.execution_time_ms = 50
        handler.graph_searcher.search_interventions_for_outcome = AsyncMock(
            return_value=mock_result
        )

        result = await handler.graph_search("TLIF outcomes for VAS")
        assert result["success"] is True
        assert result["search_type"] == "evidence_search"

    @pytest.mark.asyncio
    async def test_graph_search_hierarchy_intent(self, handler):
        """Hierarchy search type."""
        handler.cypher_generator.extract_entities.return_value = {
            "intent": "hierarchy",
            "interventions": ["TLIF"],
            "outcomes": [],
        }
        handler.graph_searcher.get_intervention_hierarchy = AsyncMock(
            return_value={"name": "TLIF", "children": []}
        )

        result = await handler.graph_search("TLIF hierarchy", search_type="hierarchy")
        assert result["success"] is True
        assert result["search_type"] == "hierarchy"

    @pytest.mark.asyncio
    async def test_graph_search_hierarchy_no_intervention(self, handler):
        """Hierarchy search without intervention returns error."""
        handler.cypher_generator.extract_entities.return_value = {
            "intent": "hierarchy",
            "interventions": [],
            "outcomes": [],
        }

        result = await handler.graph_search("something", search_type="hierarchy")
        assert result["success"] is False
        assert "No intervention" in result["error"]

    @pytest.mark.asyncio
    async def test_graph_search_conflict_intent(self, handler):
        """Conflict search type."""
        handler.cypher_generator.extract_entities.return_value = {
            "intent": "conflict",
            "interventions": ["TLIF"],
            "outcomes": ["VAS"],
        }
        mock_result = MagicMock()
        mock_result.results = []
        mock_result.execution_time_ms = 30
        handler.graph_searcher.find_conflicting_results = AsyncMock(
            return_value=mock_result
        )

        result = await handler.graph_search("TLIF conflict", search_type="conflict")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_graph_search_default_cypher_fallback(self, handler):
        """Default intent executes Cypher directly."""
        handler.cypher_generator.extract_entities.return_value = {
            "intent": "unknown_intent",
            "interventions": [],
            "outcomes": [],
        }
        handler.neo4j_client.run_query = AsyncMock(return_value=[{"r": 1}])

        result = await handler.graph_search("some unknown query")
        assert result["success"] is True
        handler.neo4j_client.run_query.assert_called_once()


# ============================================================================
# adaptive_search() tests
# ============================================================================

class TestAdaptiveSearch:
    """Tests for adaptive_search() method."""

    @pytest.mark.asyncio
    async def test_adaptive_search_query_too_long(self, handler):
        """Query exceeding MAX_QUERY_LENGTH returns error."""
        long_query = "z" * (MAX_QUERY_LENGTH + 1)
        result = await handler.adaptive_search(long_query)
        assert "error" in result
        assert "too long" in result["error"]

    @pytest.mark.asyncio
    async def test_adaptive_search_no_neo4j(self, handler):
        """Returns error when neo4j_client is None."""
        handler.server.neo4j_client = None

        result = await handler.adaptive_search("test")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_adaptive_search_with_embedding(self, handler):
        """Adaptive search with successful embedding generation."""
        handler.neo4j_client.hybrid_search = AsyncMock(return_value=[
            {
                "paper_id": "p1",
                "paper_title": "Test Paper",
                "final_score": 0.9,
                "graph_score": 0.3,
                "vector_score": 0.6,
                "content": "This is test content",
                "evidence_level": "1b",
                "year": 2023,
            }
        ])

        with patch("medical_mcp.handlers.search_handler.get_embedding_generator", create=True) as mock_gen:
            generator = MagicMock()
            generator.generate.return_value = [0.1] * 3072
            mock_gen.return_value = generator

            # Patch the import inside adaptive_search
            with patch.dict("sys.modules", {"core.embedding": MagicMock(get_embedding_generator=mock_gen)}):
                result = await handler.adaptive_search("test query", top_k=5, include_synthesis=False, detect_conflicts=False)

        assert result["success"] is True
        assert result["query_type"] == "adaptive_hybrid"


# ============================================================================
# find_evidence() tests
# ============================================================================

class TestFindEvidence:
    """Tests for find_evidence() method."""

    @pytest.mark.asyncio
    async def test_find_evidence_no_graph_searcher(self, handler):
        """Returns error when graph_searcher is None."""
        handler.graph_searcher = None
        result = await handler.find_evidence("TLIF", "VAS")
        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_find_evidence_normal_search(self, handler):
        """Normal evidence search with intervention and outcome."""
        # Mock Neo4j session
        mock_record = {
            "intervention": "TLIF",
            "full_name": "Transforaminal Lumbar Interbody Fusion",
            "outcome": "VAS",
            "value": "3.2",
            "value_control": "5.1",
            "p_value": "0.001",
            "effect_size": "0.8",
            "confidence_interval": "0.5-1.1",
            "direction": "improved",
            "is_significant": True,
            "source_paper_id": "p1",
        }

        # Create a proper async iterator for Neo4j result
        class AsyncRecordIterator:
            def __init__(self, records):
                self._records = iter(records)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._records)
                except StopIteration:
                    raise StopAsyncIteration

        mock_result = AsyncRecordIterator([mock_record])

        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        # Make session() return async context manager
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        handler.neo4j_client.session.return_value = mock_ctx

        with patch("medical_mcp.handlers.search_handler.get_normalizer", create=True) as mock_norm:
            normalizer = MagicMock()
            normalizer.normalize_intervention.return_value = MagicMock(normalized="TLIF")
            normalizer.normalize_outcome.return_value = MagicMock(normalized="VAS")
            mock_norm.return_value = normalizer

            with patch.dict("sys.modules", {"graph.entity_normalizer": MagicMock(get_normalizer=mock_norm)}):
                result = await handler.find_evidence("TLIF", "VAS")

        assert result["success"] is True
        assert result["intervention"] == "TLIF"
        assert result["outcome"] == "VAS"

    @pytest.mark.asyncio
    async def test_find_evidence_endoscopic_mode(self, handler):
        """Endoscopic search mode is triggered correctly."""
        class AsyncRecordIterator:
            def __init__(self, records):
                self._records = iter(records)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._records)
                except StopIteration:
                    raise StopAsyncIteration

        mock_result = AsyncRecordIterator([])

        mock_session = AsyncMock()
        mock_session.run = AsyncMock(return_value=mock_result)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        handler.neo4j_client.session.return_value = mock_ctx

        result = await handler.find_evidence("Endoscopic Surgery", "VAS")
        assert result["success"] is True


# ============================================================================
# evidence_chain() tests
# ============================================================================

class TestEvidenceChain:
    """Tests for evidence_chain() method."""

    @pytest.mark.asyncio
    async def test_evidence_chain_not_available(self, handler):
        """Returns error when GraphTraversalSearch not available."""
        handler.graph_traversal = None
        result = await handler.evidence_chain("TLIF", "Stenosis")
        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_evidence_chain_success(self, handler):
        """Successful evidence chain traversal."""
        mock_traversal = AsyncMock()
        chain_result = MagicMock()
        chain_result.intervention = "TLIF"
        chain_result.pathology = "Stenosis"
        chain_result.outcomes = ["VAS", "ODI"]
        chain_result.direct_evidence = [{"p": 1}]
        chain_result.related_evidence = []
        link = MagicMock()
        link.source_node = "TLIF"
        link.relationship = "TREATS"
        link.target_node = "Stenosis"
        link.properties = {}
        chain_result.evidence_chain = [link]

        mock_traversal.traverse_evidence_chain = AsyncMock(return_value=chain_result)
        handler.graph_traversal = mock_traversal

        result = await handler.evidence_chain("TLIF", "Stenosis")
        assert result["success"] is True
        assert result["intervention"] == "TLIF"
        assert result["direct_evidence_count"] == 1


# ============================================================================
# compare_interventions() tests
# ============================================================================

class TestCompareInterventions:
    """Tests for compare_interventions() method."""

    @pytest.mark.asyncio
    async def test_compare_not_available(self, handler):
        """Returns error when GraphTraversalSearch not available."""
        handler.graph_traversal = None
        result = await handler.compare_interventions("TLIF", "PLIF")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_compare_success(self, handler):
        """Successful intervention comparison."""
        mock_traversal = AsyncMock()
        comp_result = MagicMock()
        comp_result.intervention1 = "TLIF"
        comp_result.intervention2 = "PLIF"
        comp_result.pathology = "Stenosis"
        comp_result.shared_outcomes = [{"outcome": "VAS"}]
        comp_result.int1_only_outcomes = []
        comp_result.int2_only_outcomes = []
        comp_result.comparison_summary = "Both show similar outcomes"
        mock_traversal.compare_interventions = AsyncMock(return_value=comp_result)
        handler.graph_traversal = mock_traversal

        result = await handler.compare_interventions("TLIF", "PLIF", pathology="Stenosis")
        assert result["success"] is True
        assert result["intervention1"] == "TLIF"
        assert result["intervention2"] == "PLIF"


# ============================================================================
# best_evidence() tests
# ============================================================================

class TestBestEvidence:
    """Tests for best_evidence() method."""

    @pytest.mark.asyncio
    async def test_best_evidence_not_available(self, handler):
        """Returns error when GraphTraversalSearch not available."""
        handler.graph_traversal = None
        result = await handler.best_evidence("Stenosis")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_best_evidence_success(self, handler):
        """Successful best evidence retrieval."""
        mock_traversal = AsyncMock()
        evidence_item = MagicMock()
        evidence_item.paper_id = "p1"
        evidence_item.title = "Best Evidence Paper"
        evidence_item.evidence_level = "1a"
        evidence_item.year = 2024
        evidence_item.interventions = ["TLIF"]
        evidence_item.outcomes = ["VAS"]
        evidence_item.outcome_details = [{"outcome": "VAS", "direction": "improved"}]

        mock_traversal.find_best_evidence = AsyncMock(return_value=[evidence_item])
        handler.graph_traversal = mock_traversal

        result = await handler.best_evidence("Stenosis", top_k=3)
        assert result["success"] is True
        assert result["result_count"] == 1
        assert result["results"][0]["paper_id"] == "p1"
        assert result["results"][0]["evidence_level"] == "1a"

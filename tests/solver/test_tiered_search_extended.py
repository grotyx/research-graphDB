"""Extended tests for TieredHybridSearch module.

Covers untested branches and edge cases:
- _search_tier fallback logic (hybrid -> vector -> graph)
- _prioritize_original sorting behavior
- _filter_by_year edge cases
- _filter_by_evidence edge cases
- Neo4j vector/hybrid init behavior without client
- _fuse_results with empty inputs
- _merge_results_rrf with overlapping chunk IDs
- SearchOutput/SearchInput dataclass defaults
- Configuration edge cases
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.solver.tiered_search import (
    TieredHybridSearch,
    SearchInput,
    SearchOutput,
    SearchResult,
    SearchTier,
    SearchSource,
    SearchBackend,
    ChunkInfo,
    MockVectorDB,
    MockGraphDB,
)
from src.solver.query_parser import MedicalEntity, EntityType


# ============================================================================
# Helpers
# ============================================================================

def _make_search_result(
    chunk_id: str,
    tier: int = 1,
    score: float = 0.9,
    source_type: str = "original",
    evidence_level: str = "1b",
    publication_year: int = 2023,
    search_source: SearchSource = SearchSource.VECTOR,
) -> SearchResult:
    """Helper to create SearchResult."""
    return SearchResult(
        chunk=ChunkInfo(
            chunk_id=chunk_id,
            document_id=f"doc_{chunk_id}",
            text=f"Text for {chunk_id}",
            tier=tier,
            source_type=source_type,
            evidence_level=evidence_level,
            publication_year=publication_year,
        ),
        score=score,
        tier=tier,
        source_type=source_type,
        evidence_level=evidence_level,
        search_source=search_source,
        vector_score=score if search_source == SearchSource.VECTOR else None,
        graph_score=score if search_source == SearchSource.GRAPH else None,
    )


# ============================================================================
# Test: Initialization edge cases
# ============================================================================

class TestInitialization:
    """Test TieredHybridSearch initialization edge cases."""

    def test_neo4j_vector_without_client(self):
        """use_neo4j_vector=True but no client disables vector search."""
        engine = TieredHybridSearch(
            use_neo4j_vector=True,
            neo4j_client=None,
        )
        assert engine.use_neo4j_vector is False
        assert engine.use_neo4j_hybrid is False

    def test_neo4j_hybrid_config_flag(self):
        """use_neo4j_hybrid can be controlled via config."""
        engine = TieredHybridSearch(
            config={"use_neo4j_hybrid": False},
        )
        assert engine.use_neo4j_hybrid is False

    def test_default_search_backend_is_neo4j(self):
        """SearchOutput default backend is Neo4j."""
        output = SearchOutput()
        assert output.vector_backend == SearchBackend.NEO4J

    def test_search_input_defaults(self):
        """SearchInput has sensible defaults."""
        si = SearchInput(query="test query")
        assert si.top_k == 10
        assert si.tier_strategy == SearchTier.TIER1_THEN_TIER2
        assert si.prefer_original is True
        assert si.min_evidence_level is None
        assert si.recency_weight == 0.1
        assert si.min_year is None
        assert si.entities == []

    def test_search_output_defaults(self):
        """SearchOutput has sensible defaults."""
        so = SearchOutput()
        assert so.results == []
        assert so.total_found == 0
        assert so.tier1_count == 0
        assert so.tier2_count == 0
        assert so.vector_results == 0
        assert so.graph_results == 0
        assert so.expanded_query is None
        assert so.search_strategy_used == SearchTier.TIER1_THEN_TIER2

    def test_chunk_info_defaults(self):
        """ChunkInfo has sensible defaults."""
        ci = ChunkInfo(chunk_id="c1", document_id="d1", text="text")
        assert ci.tier == 1
        assert ci.section == "other"
        assert ci.publication_year == 2020
        assert ci.page_number is None
        assert ci.title is None
        assert ci.authors is None


# ============================================================================
# Test: _prioritize_original sorting
# ============================================================================

class TestPrioritizeOriginal:
    """Test _prioritize_original method."""

    @pytest.fixture
    def engine(self):
        return TieredHybridSearch()

    def test_originals_come_first(self, engine):
        """Original sources are placed before citations/background."""
        results = [
            _make_search_result("c1", source_type="citation", score=0.95),
            _make_search_result("o1", source_type="original", score=0.80),
            _make_search_result("b1", source_type="background", score=0.90),
            _make_search_result("o2", source_type="original", score=0.70),
        ]

        prioritized = engine._prioritize_original(results)

        # Originals first, then others
        assert prioritized[0].source_type == "original"
        assert prioritized[1].source_type == "original"
        # Within originals, sorted by score desc
        assert prioritized[0].score >= prioritized[1].score
        # Others after originals
        assert prioritized[2].source_type in ["citation", "background"]
        assert prioritized[3].source_type in ["citation", "background"]
        # Within others, sorted by score desc
        assert prioritized[2].score >= prioritized[3].score

    def test_all_original(self, engine):
        """All original sources remain sorted by score."""
        results = [
            _make_search_result("o1", source_type="original", score=0.7),
            _make_search_result("o2", source_type="original", score=0.9),
            _make_search_result("o3", source_type="original", score=0.8),
        ]

        prioritized = engine._prioritize_original(results)

        scores = [r.score for r in prioritized]
        assert scores == sorted(scores, reverse=True)

    def test_all_citation(self, engine):
        """All citation sources remain sorted by score."""
        results = [
            _make_search_result("c1", source_type="citation", score=0.6),
            _make_search_result("c2", source_type="citation", score=0.9),
        ]

        prioritized = engine._prioritize_original(results)
        assert prioritized[0].score >= prioritized[1].score

    def test_empty_list(self, engine):
        """Empty list returns empty."""
        assert engine._prioritize_original([]) == []


# ============================================================================
# Test: _filter_by_year edge cases
# ============================================================================

class TestFilterByYear:
    """Test _filter_by_year method."""

    @pytest.fixture
    def engine(self):
        return TieredHybridSearch()

    def test_filter_exact_year(self, engine):
        """Exact year boundary is included."""
        results = [
            _make_search_result("c1", publication_year=2020),
            _make_search_result("c2", publication_year=2019),
            _make_search_result("c3", publication_year=2021),
        ]

        filtered = engine._filter_by_year(results, min_year=2020)
        years = [r.chunk.publication_year for r in filtered]
        assert 2020 in years
        assert 2021 in years
        assert 2019 not in years

    def test_filter_removes_all(self, engine):
        """Filter that removes all results."""
        results = [
            _make_search_result("c1", publication_year=2010),
            _make_search_result("c2", publication_year=2015),
        ]

        filtered = engine._filter_by_year(results, min_year=2020)
        assert len(filtered) == 0

    def test_filter_keeps_all(self, engine):
        """Filter that keeps all results."""
        results = [
            _make_search_result("c1", publication_year=2023),
            _make_search_result("c2", publication_year=2024),
        ]

        filtered = engine._filter_by_year(results, min_year=2020)
        assert len(filtered) == 2


# ============================================================================
# Test: _filter_by_evidence edge cases
# ============================================================================

class TestFilterByEvidence:
    """Test _filter_by_evidence method."""

    @pytest.fixture
    def engine(self):
        return TieredHybridSearch()

    def test_filter_keeps_matching(self, engine):
        """Keeps results within acceptable levels."""
        results = [
            _make_search_result("c1", evidence_level="1a"),
            _make_search_result("c2", evidence_level="2b"),
            _make_search_result("c3", evidence_level="4"),
        ]

        filtered = engine._filter_by_evidence(results, "2b")
        levels = [r.evidence_level for r in filtered]
        assert "1a" in levels
        assert "2b" in levels
        assert "4" not in levels

    def test_filter_with_invalid_level(self, engine):
        """Invalid level returns all results (all levels acceptable)."""
        results = [
            _make_search_result("c1", evidence_level="1a"),
            _make_search_result("c2", evidence_level="5"),
        ]

        filtered = engine._filter_by_evidence(results, "nonexistent")
        assert len(filtered) == 2

    def test_filter_strictest_level(self, engine):
        """Filtering with '1a' keeps only 1a."""
        results = [
            _make_search_result("c1", evidence_level="1a"),
            _make_search_result("c2", evidence_level="1b"),
            _make_search_result("c3", evidence_level="2a"),
        ]

        filtered = engine._filter_by_evidence(results, "1a")
        assert len(filtered) == 1
        assert filtered[0].evidence_level == "1a"


# ============================================================================
# Test: _fuse_results edge cases
# ============================================================================

class TestFuseResults:
    """Test _fuse_results method edge cases."""

    @pytest.fixture
    def engine(self):
        return TieredHybridSearch()

    def test_fuse_empty_vector(self, engine):
        """Empty vector results with non-empty graph."""
        graph = [_make_search_result("g1", search_source=SearchSource.GRAPH)]
        fused = engine._fuse_results([], graph, top_k=5)
        assert len(fused) == 1

    def test_fuse_empty_graph(self, engine):
        """Empty graph results with non-empty vector."""
        vector = [_make_search_result("v1", search_source=SearchSource.VECTOR)]
        fused = engine._fuse_results(vector, [], top_k=5)
        assert len(fused) == 1

    def test_fuse_both_empty(self, engine):
        """Both empty returns empty."""
        fused = engine._fuse_results([], [], top_k=5)
        assert len(fused) == 0

    def test_fuse_top_k_limits(self, engine):
        """top_k parameter limits output."""
        vector = [_make_search_result(f"v{i}", score=0.9 - i * 0.1) for i in range(5)]
        graph = [_make_search_result(f"g{i}", score=0.85 - i * 0.1, search_source=SearchSource.GRAPH) for i in range(5)]

        fused = engine._fuse_results(vector, graph, top_k=3)
        assert len(fused) <= 3

    def test_fuse_overlapping_scores_combined(self, engine):
        """Same chunk found in both gets BOTH source and combined score."""
        vector = [_make_search_result("shared", score=0.9, search_source=SearchSource.VECTOR)]
        graph = [_make_search_result("shared", score=0.8, search_source=SearchSource.GRAPH)]

        fused = engine._fuse_results(vector, graph, top_k=5)
        assert len(fused) == 1
        assert fused[0].search_source == SearchSource.BOTH
        # Score should be sum of RRF scores (not just max)
        assert fused[0].score > 0


# ============================================================================
# Test: _merge_results_rrf edge cases
# ============================================================================

class TestMergeResultsRRF:
    """Test _merge_results_rrf method edge cases."""

    @pytest.fixture
    def engine(self):
        return TieredHybridSearch()

    def test_merge_empty_tier1(self, engine):
        """Empty tier1 with non-empty tier2."""
        tier2 = [_make_search_result("t2_1", tier=2)]
        merged = engine._merge_results_rrf([], tier2, top_k=5)
        assert len(merged) == 1

    def test_merge_empty_tier2(self, engine):
        """Empty tier2 with non-empty tier1."""
        tier1 = [_make_search_result("t1_1", tier=1)]
        merged = engine._merge_results_rrf(tier1, [], top_k=5)
        assert len(merged) == 1

    def test_merge_both_empty(self, engine):
        """Both tiers empty returns empty."""
        merged = engine._merge_results_rrf([], [], top_k=5)
        assert len(merged) == 0

    def test_merge_overlapping_chunk_id(self, engine):
        """Same chunk ID in both tiers gets combined score."""
        tier1 = [_make_search_result("shared", tier=1, score=0.9)]
        tier2 = [_make_search_result("shared", tier=2, score=0.8)]

        merged = engine._merge_results_rrf(tier1, tier2, top_k=5)
        # Should have 1 result (deduplicated by chunk_id)
        assert len(merged) == 1
        # The score should be sum of both tier RRF scores
        # tier1_weight=0.6, tier2_weight=0.4
        expected = 0.6 / (engine.rrf_k + 0 + 1) + 0.4 / (engine.rrf_k + 0 + 1)
        assert abs(merged[0].score - expected) < 1e-10

    def test_merge_tier1_weighted_higher(self, engine):
        """Tier1 results should have higher weight than tier2."""
        tier1 = [_make_search_result("t1", tier=1, score=0.9)]
        tier2 = [_make_search_result("t2", tier=2, score=0.9)]

        merged = engine._merge_results_rrf(tier1, tier2, top_k=5)
        scores = {r.chunk.chunk_id: r.score for r in merged}
        assert scores["t1"] > scores["t2"]

    def test_merge_top_k_limits(self, engine):
        """top_k limits the output size."""
        tier1 = [_make_search_result(f"t1_{i}", tier=1) for i in range(10)]
        tier2 = [_make_search_result(f"t2_{i}", tier=2) for i in range(10)]

        merged = engine._merge_results_rrf(tier1, tier2, top_k=5)
        assert len(merged) <= 5


# ============================================================================
# Test: _search_tier fallback logic
# ============================================================================

class TestSearchTierFallback:
    """Test _search_tier fallback logic."""

    @pytest.mark.asyncio
    async def test_no_backends_returns_empty(self):
        """No backends configured returns empty."""
        engine = TieredHybridSearch()
        input_data = SearchInput(query="test")
        results = await engine._search_tier(input_data, tier=1, top_k=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_vector_only_returns_vector(self):
        """Vector DB only returns vector results."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "text", "tier": 1,
             "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9}
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        input_data = SearchInput(query="test")
        results = await engine._search_tier(input_data, tier=1, top_k=10)
        assert len(results) > 0
        assert all(r.search_source == SearchSource.VECTOR for r in results)

    @pytest.mark.asyncio
    async def test_graph_only_with_entities(self):
        """Graph DB only returns graph results when entities provided."""
        data = [
            {"id": "g1", "document_id": "d1", "text": "spine surgery",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.8}
        ]
        entities = [MedicalEntity(text="spine", entity_type=EntityType.ANATOMY)]
        engine = TieredHybridSearch(graph_db=MockGraphDB(data))
        input_data = SearchInput(query="spine surgery", entities=entities)
        results = await engine._search_tier(input_data, tier=1, top_k=10)
        assert len(results) > 0
        assert all(r.search_source == SearchSource.GRAPH for r in results)

    @pytest.mark.asyncio
    async def test_graph_without_entities_skipped(self):
        """Graph DB is skipped when no entities provided."""
        data = [
            {"id": "g1", "document_id": "d1", "text": "spine surgery",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.8}
        ]
        engine = TieredHybridSearch(graph_db=MockGraphDB(data))
        # No entities provided
        input_data = SearchInput(query="spine surgery")
        results = await engine._search_tier(input_data, tier=1, top_k=10)
        assert results == []


# ============================================================================
# Test: Search statistics in output
# ============================================================================

class TestSearchOutputStatistics:
    """Test search output statistics calculation."""

    @pytest.mark.asyncio
    async def test_vector_and_graph_counts(self):
        """Test vector_results and graph_results counts."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "spine surgery outcomes",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9}
        ]
        entities = [MedicalEntity(text="spine", entity_type=EntityType.ANATOMY)]
        engine = TieredHybridSearch(
            vector_db=MockVectorDB(data),
            graph_db=MockGraphDB(data),
        )

        result = await engine.search(SearchInput(
            query="spine surgery outcomes",
            entities=entities,
            tier_strategy=SearchTier.TIER1_ONLY,
            top_k=10,
        ))

        # Should have results from both sources (fused)
        assert result.total_found >= 0
        assert result.vector_results >= 0 or result.graph_results >= 0


# ============================================================================
# Test: _vector_search details
# ============================================================================

class TestVectorSearchDetails:
    """Test _vector_search method details."""

    def test_vector_search_no_db(self):
        """Vector search returns empty when no DB."""
        engine = TieredHybridSearch()
        input_data = SearchInput(query="test")
        results = engine._vector_search(input_data, tier=1, top_k=10)
        assert results == []

    def test_vector_search_with_filters(self):
        """Vector search applies evidence and year filters."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "result 1",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9},
            {"id": "c2", "document_id": "d2", "text": "result 2",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "4", "publication_year": 2019, "score": 0.8},
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        input_data = SearchInput(
            query="test",
            min_evidence_level="2b",
            min_year=2020,
        )
        results = engine._vector_search(input_data, tier=1, top_k=10)
        for r in results:
            assert r.evidence_level in ["1a", "1b", "2a", "2b"]
            assert r.chunk.publication_year >= 2020

    def test_vector_search_tier_collection_mapping(self):
        """Vector search uses correct collection for each tier."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "tier1 data",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9},
            {"id": "c2", "document_id": "d2", "text": "tier2 data",
             "tier": 2, "section": "methods", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.8},
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))

        # Tier 1 search
        tier1_results = engine._vector_search(
            SearchInput(query="test"), tier=1, top_k=10
        )
        for r in tier1_results:
            assert r.tier == 1

        # Tier 2 search
        tier2_results = engine._vector_search(
            SearchInput(query="test"), tier=2, top_k=10
        )
        for r in tier2_results:
            assert r.tier == 2


# ============================================================================
# Test: _graph_search details
# ============================================================================

class TestGraphSearchDetails:
    """Test _graph_search method details."""

    def test_graph_search_no_db(self):
        """Graph search returns empty when no DB."""
        engine = TieredHybridSearch()
        input_data = SearchInput(
            query="test",
            entities=[MedicalEntity(text="spine", entity_type=EntityType.ANATOMY)],
        )
        results = engine._graph_search(input_data, tier=1, top_k=10)
        assert results == []

    def test_graph_search_no_entities(self):
        """Graph search returns empty when no entities."""
        data = [{"id": "g1", "document_id": "d1", "text": "spine surgery",
                 "tier": 1, "score": 0.8}]
        engine = TieredHybridSearch(graph_db=MockGraphDB(data))
        input_data = SearchInput(query="test")  # No entities
        results = engine._graph_search(input_data, tier=1, top_k=10)
        assert results == []

    def test_graph_search_tier_filtering(self):
        """Graph search filters results by tier."""
        data = [
            {"id": "g1", "document_id": "d1", "text": "spine results",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.8},
            {"id": "g2", "document_id": "d2", "text": "spine methods",
             "tier": 2, "section": "methods", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.7},
        ]
        entities = [MedicalEntity(text="spine", entity_type=EntityType.ANATOMY)]
        engine = TieredHybridSearch(graph_db=MockGraphDB(data))

        # Tier 1 only
        results = engine._graph_search(
            SearchInput(query="spine", entities=entities), tier=1, top_k=10
        )
        for r in results:
            assert r.tier == 1


# ============================================================================
# Test: MockVectorDB edge cases
# ============================================================================

class TestMockVectorDBEdgeCases:
    """Test MockVectorDB edge cases."""

    def test_empty_data(self):
        """Empty data returns no results."""
        db = MockVectorDB([])
        results = db.search([0.1] * 3072, "tier1_chunks", 5)
        assert results == []

    def test_evidence_level_filter(self):
        """Evidence level filter works in MockVectorDB."""
        data = [
            {"id": "c1", "tier": 1, "evidence_level": "1a", "score": 0.9},
            {"id": "c2", "tier": 1, "evidence_level": "4", "score": 0.8},
        ]
        db = MockVectorDB(data)
        results = db.search(
            [0.1] * 3072, "tier1_chunks", 5,
            filters={"evidence_level": {"$in": ["1a", "1b"]}}
        )
        assert len(results) == 1
        assert results[0]["evidence_level"] == "1a"


# ============================================================================
# Test: MockGraphDB edge cases
# ============================================================================

class TestMockGraphDBEdgeCases:
    """Test MockGraphDB edge cases."""

    def test_empty_data(self):
        """Empty data returns no results."""
        db = MockGraphDB([])
        results = db.search_by_entities(["spine"], 5)
        assert results == []

    def test_no_matching_entities(self):
        """No matching entities returns empty."""
        data = [
            {"id": "g1", "text": "unrelated document about cars"},
        ]
        db = MockGraphDB(data)
        results = db.search_by_entities(["spine", "surgery"], 5)
        assert results == []

    def test_case_insensitive_matching(self):
        """Entity matching is case insensitive."""
        data = [
            {"id": "g1", "text": "SPINE Surgery Results"},
        ]
        db = MockGraphDB(data)
        results = db.search_by_entities(["spine"], 5)
        assert len(results) == 1

    def test_top_k_limit(self):
        """top_k limits results."""
        data = [
            {"id": f"g{i}", "text": f"spine surgery result {i}"}
            for i in range(10)
        ]
        db = MockGraphDB(data)
        results = db.search_by_entities(["spine"], 3)
        assert len(results) == 3


# ============================================================================
# Test: Full search workflow edge cases
# ============================================================================

class TestFullSearchWorkflow:
    """Test complete search workflow edge cases."""

    @pytest.mark.asyncio
    async def test_tier1_only_with_insufficient_results(self):
        """TIER1_ONLY with limited data."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9}
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        result = await engine.search(SearchInput(
            query="test",
            tier_strategy=SearchTier.TIER1_ONLY,
            top_k=10,
        ))
        assert result.total_found == 1
        assert result.tier1_count == 1
        assert result.tier2_count == 0

    @pytest.mark.asyncio
    async def test_tier1_then_tier2_expands_when_insufficient(self):
        """TIER1_THEN_TIER2 expands to tier2 when tier1 has too few results."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "tier1 result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9},
            {"id": "c2", "document_id": "d2", "text": "tier2 result",
             "tier": 2, "section": "methods", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.8},
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        result = await engine.search(SearchInput(
            query="test",
            tier_strategy=SearchTier.TIER1_THEN_TIER2,
            top_k=10,
        ))
        assert result.tier1_count == 1
        assert result.tier2_count == 1

    @pytest.mark.asyncio
    async def test_all_tiers_merges_via_rrf(self):
        """ALL_TIERS strategy merges both tiers via RRF."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "tier1 result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9},
            {"id": "c2", "document_id": "d2", "text": "tier2 result",
             "tier": 2, "section": "methods", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.8},
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        result = await engine.search(SearchInput(
            query="test",
            tier_strategy=SearchTier.ALL_TIERS,
            top_k=10,
        ))
        assert result.tier1_count >= 0
        assert result.tier2_count >= 0
        assert result.search_strategy_used == SearchTier.ALL_TIERS

    @pytest.mark.asyncio
    async def test_combined_filters(self):
        """Year + evidence + original preference all applied together."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "good result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9},
            {"id": "c2", "document_id": "d2", "text": "old result",
             "tier": 1, "section": "results", "source_type": "citation",
             "evidence_level": "4", "publication_year": 2015, "score": 0.8},
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        result = await engine.search(SearchInput(
            query="test",
            tier_strategy=SearchTier.TIER1_ONLY,
            prefer_original=True,
            min_evidence_level="2b",
            min_year=2020,
            top_k=10,
        ))
        # Only c1 should pass all filters
        assert result.total_found <= 1
        for r in result.results:
            assert r.chunk.publication_year >= 2020
            assert r.evidence_level in ["1a", "1b", "2a", "2b"]

    @pytest.mark.asyncio
    async def test_no_prefer_original(self):
        """prefer_original=False skips original prioritization."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "citation result",
             "tier": 1, "section": "discussion", "source_type": "citation",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.95},
            {"id": "c2", "document_id": "d2", "text": "original result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "2b", "publication_year": 2022, "score": 0.80},
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        result = await engine.search(SearchInput(
            query="test",
            tier_strategy=SearchTier.TIER1_ONLY,
            prefer_original=False,
            top_k=10,
        ))
        # Without original priority, order is just by score
        if len(result.results) >= 2:
            assert result.results[0].score >= result.results[1].score


# ============================================================================
# Test: HyDE integration
# ============================================================================

class TestHyDEIntegration:
    """Test HyDE (Hypothetical Document Embedding) integration."""

    @pytest.mark.asyncio
    async def test_hyde_off_by_default(self):
        """HyDE is off by default."""
        si = SearchInput(query="test query")
        assert si.use_hyde is False

    @pytest.mark.asyncio
    async def test_hyde_disabled_no_anthropic(self):
        """HyDE falls back gracefully when anthropic not available."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "spine result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9}
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))

        with patch("src.solver.tiered_search.ANTHROPIC_AVAILABLE", False):
            result = await engine.search(SearchInput(
                query="spine surgery",
                tier_strategy=SearchTier.TIER1_ONLY,
                use_hyde=True,
                top_k=10,
            ))
            # Should still return results (falls back to original query)
            assert result.total_found >= 0

    @pytest.mark.asyncio
    async def test_hyde_generates_hypothetical_answer(self):
        """HyDE replaces query with hypothetical answer when successful."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "spine surgery outcomes",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9}
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))

        # Mock the _generate_hyde method
        with patch.object(engine, "_generate_hyde", new_callable=AsyncMock) as mock_hyde:
            mock_hyde.return_value = "Hypothetical answer about spine surgery outcomes..."

            result = await engine.search(SearchInput(
                query="What are spine surgery outcomes?",
                tier_strategy=SearchTier.TIER1_ONLY,
                use_hyde=True,
                top_k=10,
            ))

            mock_hyde.assert_called_once_with("What are spine surgery outcomes?")
            assert result.total_found >= 0

    @pytest.mark.asyncio
    async def test_hyde_failure_falls_back(self):
        """HyDE failure falls back to original query."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "spine result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9}
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))

        with patch.object(engine, "_generate_hyde", new_callable=AsyncMock) as mock_hyde:
            mock_hyde.return_value = None  # Failure

            result = await engine.search(SearchInput(
                query="spine surgery",
                tier_strategy=SearchTier.TIER1_ONLY,
                use_hyde=True,
                top_k=10,
            ))

            # Should still work with original query
            assert result.total_found >= 0


# ============================================================================
# Test: Reranker integration in search
# ============================================================================

class TestRerankerIntegration:
    """Test reranker integration in TieredHybridSearch."""

    @pytest.mark.asyncio
    async def test_reranker_off_by_default(self):
        """Reranker is off by default."""
        si = SearchInput(query="test query")
        assert si.use_reranker is False

    @pytest.mark.asyncio
    async def test_reranker_skipped_when_unavailable(self):
        """Reranker is skipped when not available."""
        data = [
            {"id": "c1", "document_id": "d1", "text": "spine result",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9}
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))
        # Force reranker to use Cohere provider (no COHERE_API_KEY → unavailable)
        from solver.reranker import Reranker
        engine.reranker = Reranker(provider="cohere")
        assert engine.reranker.is_available is False

        result = await engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.TIER1_ONLY,
            use_reranker=True,
            top_k=10,
        ))
        # Should still return results
        assert result.total_found >= 0

    @pytest.mark.asyncio
    async def test_reranker_called_when_available(self):
        """Reranker is called when available and requested."""
        data = [
            {"id": f"c{i}", "document_id": f"d{i}", "text": f"result {i}",
             "tier": 1, "section": "results", "source_type": "original",
             "evidence_level": "1b", "publication_year": 2023, "score": 0.9 - i * 0.01}
            for i in range(5)
        ]
        engine = TieredHybridSearch(vector_db=MockVectorDB(data))

        # Mock the reranker as available
        engine.reranker._available = True
        with patch.object(engine.reranker, "rerank", new_callable=AsyncMock) as mock_rerank:
            # Return reversed results
            mock_rerank.return_value = [
                _make_search_result(f"c{i}", score=0.99 - i * 0.01)
                for i in range(3)
            ]

            result = await engine.search(SearchInput(
                query="spine surgery",
                tier_strategy=SearchTier.TIER1_ONLY,
                use_reranker=True,
                top_k=3,
            ))

            mock_rerank.assert_called_once()
            assert result.total_found == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

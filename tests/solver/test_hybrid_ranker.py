"""Tests for HybridRanker v1.15 QC - _merge_results Immutability.

The v1.15 QC fixed _merge_results to avoid mutating input scores.
Previously, the method modified HybridResult.score in-place via
graph_results[i].score *= weight. After the fix, the method creates
new HybridResult copies with weighted scores.

This file tests:
1. _merge_results does NOT mutate input graph_results scores
2. _merge_results does NOT mutate input vector_results scores
3. _merge_results correctly applies graph_weight and vector_weight
4. Deduplication by source_id works (keeps highest score)
5. Empty input lists handled correctly
6. Helper scoring functions work correctly
"""

import pytest
import copy

from src.solver.hybrid_ranker import (
    HybridRanker,
    HybridResult,
    get_evidence_weight,
    get_study_design_weight,
    get_sample_size_boost,
    get_recency_boost,
    get_citation_boost,
    get_source_credibility,
    EVIDENCE_LEVEL_WEIGHTS,
    STUDY_DESIGN_WEIGHTS,
)
from src.solver.graph_result import GraphEvidence, PaperNode


@pytest.fixture
def ranker():
    """Create HybridRanker without real backends."""
    return HybridRanker(vector_db=None, neo4j_client=None)


def _make_graph_result(source_id: str, score: float, **kwargs) -> HybridResult:
    """Helper to create a graph-type HybridResult."""
    return HybridResult(
        result_type="graph",
        score=score,
        content=f"Graph content for {source_id}",
        source_id=source_id,
        metadata=kwargs.get("metadata", {}),
        evidence=kwargs.get("evidence"),
        paper=kwargs.get("paper"),
    )


def _make_vector_result(source_id: str, score: float, **kwargs) -> HybridResult:
    """Helper to create a vector-type HybridResult."""
    return HybridResult(
        result_type="vector",
        score=score,
        content=f"Vector content for {source_id}",
        source_id=source_id,
        metadata=kwargs.get("metadata", {}),
    )


class TestMergeResultsImmutability:
    """Core test: _merge_results must not mutate input HybridResult scores."""

    def test_graph_results_scores_unchanged(self, ranker):
        """After _merge_results, original graph_results scores are untouched."""
        graph_results = [
            _make_graph_result("paper_1", 0.95),
            _make_graph_result("paper_2", 0.80),
            _make_graph_result("paper_3", 0.60),
        ]
        original_scores = [r.score for r in graph_results]

        ranker._merge_results(graph_results, [], graph_weight=0.6, vector_weight=0.4)

        for i, result in enumerate(graph_results):
            assert result.score == original_scores[i], (
                f"graph_results[{i}].score was mutated from {original_scores[i]} "
                f"to {result.score}. _merge_results must not modify input objects."
            )

    def test_vector_results_scores_unchanged(self, ranker):
        """After _merge_results, original vector_results scores are untouched."""
        vector_results = [
            _make_vector_result("chunk_1", 0.92),
            _make_vector_result("chunk_2", 0.75),
            _make_vector_result("chunk_3", 0.55),
        ]
        original_scores = [r.score for r in vector_results]

        ranker._merge_results([], vector_results, graph_weight=0.6, vector_weight=0.4)

        for i, result in enumerate(vector_results):
            assert result.score == original_scores[i], (
                f"vector_results[{i}].score was mutated from {original_scores[i]} "
                f"to {result.score}. _merge_results must not modify input objects."
            )

    def test_both_inputs_unchanged_after_merge(self, ranker):
        """Both graph and vector inputs remain unchanged after merge."""
        graph_results = [
            _make_graph_result("paper_A", 0.9),
            _make_graph_result("paper_B", 0.7),
        ]
        vector_results = [
            _make_vector_result("chunk_X", 0.85),
            _make_vector_result("chunk_Y", 0.65),
        ]

        # Deep copy the scores for comparison
        graph_scores_before = [r.score for r in graph_results]
        vector_scores_before = [r.score for r in vector_results]

        ranker._merge_results(
            graph_results, vector_results,
            graph_weight=0.6, vector_weight=0.4
        )

        # Verify nothing changed
        for i, r in enumerate(graph_results):
            assert r.score == graph_scores_before[i]
        for i, r in enumerate(vector_results):
            assert r.score == vector_scores_before[i]

    def test_metadata_not_mutated(self, ranker):
        """Input metadata dicts should not be modified."""
        metadata = {"key": "original_value"}
        graph_results = [
            _make_graph_result("paper_1", 0.9, metadata=metadata),
        ]

        ranker._merge_results(graph_results, [], graph_weight=0.6, vector_weight=0.4)

        assert graph_results[0].metadata["key"] == "original_value"

    def test_repeated_calls_produce_same_result(self, ranker):
        """Calling _merge_results twice on the same inputs produces identical output."""
        graph_results = [_make_graph_result("p1", 0.9)]
        vector_results = [_make_vector_result("c1", 0.8)]

        merged1 = ranker._merge_results(
            graph_results, vector_results, graph_weight=0.6, vector_weight=0.4
        )
        merged2 = ranker._merge_results(
            graph_results, vector_results, graph_weight=0.6, vector_weight=0.4
        )

        # Both calls should produce the same scores
        scores1 = sorted([(r.source_id, r.score) for r in merged1])
        scores2 = sorted([(r.source_id, r.score) for r in merged2])
        assert scores1 == scores2


class TestMergeResultsWeighting:
    """Test that _merge_results correctly applies weights."""

    def test_graph_weight_applied(self, ranker):
        """Graph results have their score multiplied by graph_weight."""
        graph_results = [_make_graph_result("p1", 1.0)]

        merged = ranker._merge_results(
            graph_results, [], graph_weight=0.6, vector_weight=0.4
        )

        assert len(merged) == 1
        assert abs(merged[0].score - 0.6) < 1e-6

    def test_vector_weight_applied(self, ranker):
        """Vector results have their score multiplied by vector_weight."""
        vector_results = [_make_vector_result("c1", 1.0)]

        merged = ranker._merge_results(
            [], vector_results, graph_weight=0.6, vector_weight=0.4
        )

        assert len(merged) == 1
        assert abs(merged[0].score - 0.4) < 1e-6

    def test_custom_weights(self, ranker):
        """Custom weight values are applied correctly."""
        graph_results = [_make_graph_result("p1", 0.8)]
        vector_results = [_make_vector_result("c1", 0.9)]

        merged = ranker._merge_results(
            graph_results, vector_results,
            graph_weight=0.7, vector_weight=0.3
        )

        # Find each result
        merged_by_id = {r.source_id: r for r in merged}
        assert abs(merged_by_id["p1"].score - 0.8 * 0.7) < 1e-6
        assert abs(merged_by_id["c1"].score - 0.9 * 0.3) < 1e-6


class TestMergeResultsDeduplication:
    """Test deduplication by source_id in _merge_results."""

    def test_same_source_id_keeps_higher_score(self, ranker):
        """When graph and vector have same source_id, keep higher weighted score."""
        # Graph result for paper_1 with score 0.9 * 0.6 = 0.54
        graph_results = [_make_graph_result("paper_1", 0.9)]
        # Vector result for same paper_1 with score 0.8 * 0.4 = 0.32
        vector_results = [_make_vector_result("paper_1", 0.8)]

        merged = ranker._merge_results(
            graph_results, vector_results,
            graph_weight=0.6, vector_weight=0.4
        )

        # Should only have one result for paper_1
        assert len(merged) == 1
        assert merged[0].source_id == "paper_1"
        # Should keep the higher score (graph: 0.54 > vector: 0.32)
        assert abs(merged[0].score - 0.54) < 1e-6

    def test_different_source_ids_all_kept(self, ranker):
        """Results with different source_ids are all kept."""
        graph_results = [
            _make_graph_result("p1", 0.9),
            _make_graph_result("p2", 0.7),
        ]
        vector_results = [
            _make_vector_result("c1", 0.85),
            _make_vector_result("c2", 0.65),
        ]

        merged = ranker._merge_results(
            graph_results, vector_results,
            graph_weight=0.6, vector_weight=0.4
        )

        source_ids = {r.source_id for r in merged}
        assert source_ids == {"p1", "p2", "c1", "c2"}


class TestMergeResultsEdgeCases:
    """Test edge cases for _merge_results."""

    def test_empty_both(self, ranker):
        """Empty inputs return empty list."""
        merged = ranker._merge_results([], [], graph_weight=0.6, vector_weight=0.4)
        assert merged == []

    def test_empty_graph(self, ranker):
        """Empty graph with non-empty vector returns weighted vector results."""
        vector_results = [_make_vector_result("c1", 0.9)]

        merged = ranker._merge_results(
            [], vector_results, graph_weight=0.6, vector_weight=0.4
        )

        assert len(merged) == 1
        assert abs(merged[0].score - 0.9 * 0.4) < 1e-6

    def test_empty_vector(self, ranker):
        """Empty vector with non-empty graph returns weighted graph results."""
        graph_results = [_make_graph_result("p1", 0.8)]

        merged = ranker._merge_results(
            graph_results, [], graph_weight=0.6, vector_weight=0.4
        )

        assert len(merged) == 1
        assert abs(merged[0].score - 0.8 * 0.6) < 1e-6

    def test_zero_weights(self, ranker):
        """Zero weights produce zero scores but do not crash."""
        graph_results = [_make_graph_result("p1", 0.9)]
        vector_results = [_make_vector_result("c1", 0.8)]

        merged = ranker._merge_results(
            graph_results, vector_results,
            graph_weight=0.0, vector_weight=0.0
        )

        for result in merged:
            assert result.score == 0.0

    def test_single_item_each(self, ranker):
        """Single item in each list works correctly."""
        graph_results = [_make_graph_result("p1", 0.95)]
        vector_results = [_make_vector_result("c1", 0.85)]

        merged = ranker._merge_results(
            graph_results, vector_results,
            graph_weight=0.6, vector_weight=0.4
        )

        assert len(merged) == 2


class TestHelperScoringFunctions:
    """Test the helper scoring functions used by HybridRanker."""

    def test_evidence_weight_level_1a(self):
        """Level 1a (Meta-analysis) gets highest weight."""
        paper = PaperNode(paper_id="p1", title="Meta-analysis", evidence_level="1a")
        weight = get_evidence_weight(paper)
        assert weight == 1.0

    def test_evidence_weight_level_1b(self):
        """Level 1b (RCT) gets 0.9."""
        paper = PaperNode(paper_id="p1", title="RCT", evidence_level="1b")
        weight = get_evidence_weight(paper)
        assert weight == 0.9

    def test_evidence_weight_none(self):
        """No evidence level defaults to 0.50 for journal articles."""
        paper = PaperNode(paper_id="p1", title="Unknown")
        paper.evidence_level = None
        paper.document_type = "JOURNAL_ARTICLE"
        weight = get_evidence_weight(paper)
        assert weight == 0.50

    def test_study_design_weight_rct(self):
        """RCT study design gets 0.9 weight."""
        weight = get_study_design_weight(["Randomized Controlled Trial"])
        assert weight == 0.9

    def test_study_design_weight_multiple(self):
        """Multiple types use the highest weight."""
        weight = get_study_design_weight([
            "Case Reports", "Randomized Controlled Trial"
        ])
        assert weight == 0.9

    def test_study_design_weight_none(self):
        """None publication types default to 0.5."""
        assert get_study_design_weight(None) == 0.5

    def test_sample_size_boost_large(self):
        """Large sample (1000+) gets 1.3 boost."""
        assert get_sample_size_boost(1500) == 1.3

    def test_sample_size_boost_small(self):
        """Small sample (<10) gets no boost."""
        assert get_sample_size_boost(5) == 1.0

    def test_sample_size_boost_none(self):
        """None sample size gets no boost."""
        assert get_sample_size_boost(None) == 1.0

    def test_recency_boost_very_recent(self):
        """Publication within last 2 years gets 1.2."""
        assert get_recency_boost(2025, current_year=2026) == 1.2

    def test_recency_boost_old(self):
        """Publication >10 years old gets 0.9."""
        assert get_recency_boost(2010, current_year=2026) == 0.9

    def test_citation_boost_high(self):
        """100+ citations gets 1.3."""
        assert get_citation_boost(150) == 1.3

    def test_citation_boost_none(self):
        """No citations gets 1.0."""
        assert get_citation_boost(None) == 1.0

    def test_source_credibility_nih(self):
        """NIH source gets 1.0 credibility."""
        assert get_source_credibility("NIH") == 1.0

    def test_source_credibility_unknown(self):
        """Unknown source gets default (0.4)."""
        assert get_source_credibility("random-blog.com") == 0.4

    def test_source_credibility_none(self):
        """None source gets default."""
        assert get_source_credibility(None) == 0.4


class TestHybridRankerInit:
    """Test HybridRanker initialization."""

    def test_init_no_backends(self):
        """Initializing without backends works (graceful degradation)."""
        ranker = HybridRanker(vector_db=None, neo4j_client=None)
        assert ranker.vector_db is None
        assert ranker.neo4j_client is None
        assert ranker.use_neo4j_hybrid is False

    def test_init_neo4j_hybrid_requires_client(self):
        """use_neo4j_hybrid=True requires neo4j_client to be set."""
        ranker = HybridRanker(
            vector_db=None,
            neo4j_client=None,
            use_neo4j_hybrid=True
        )
        # Should be disabled since neo4j_client is None
        assert ranker.use_neo4j_hybrid is False

    def test_get_stats_no_backends(self):
        """get_stats works without backends."""
        ranker = HybridRanker(vector_db=None, neo4j_client=None)
        stats = ranker.get_stats()
        assert stats["graph_db_available"] is False
        assert stats["vector_db"] is None
        assert stats["ranking_version"] == "v1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

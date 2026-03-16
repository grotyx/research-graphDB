"""Tests for evaluation metrics."""

import math
import pytest
from evaluation.metrics import (
    precision_at_k,
    recall_at_k,
    dcg_at_k,
    ndcg_at_k,
    mrr,
    evidence_level_accuracy,
    evaluate_single_query,
    aggregate_metrics,
)


class TestPrecisionAtK:
    def test_perfect_precision(self):
        retrieved = ["a", "b", "c", "d", "e"]
        relevant = {"a", "b", "c", "d", "e"}
        assert precision_at_k(retrieved, relevant, 5) == 1.0

    def test_zero_precision(self):
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 3) == 0.0

    def test_partial_precision(self):
        retrieved = ["a", "x", "b", "y", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 5) == 0.6

    def test_precision_at_different_k(self):
        retrieved = ["a", "b", "x", "y", "z"]
        relevant = {"a", "b"}
        assert precision_at_k(retrieved, relevant, 2) == 1.0
        assert precision_at_k(retrieved, relevant, 5) == 0.4

    def test_empty_retrieved(self):
        assert precision_at_k([], {"a"}, 5) == 0.0

    def test_k_zero(self):
        assert precision_at_k(["a"], {"a"}, 0) == 0.0


class TestRecallAtK:
    def test_perfect_recall(self):
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, 3) == 1.0

    def test_partial_recall(self):
        retrieved = ["a", "x", "y"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, 3) == pytest.approx(1 / 3)

    def test_empty_relevant(self):
        assert recall_at_k(["a"], set(), 5) == 0.0

    def test_k_larger_than_retrieved(self):
        retrieved = ["a", "b"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, 10) == pytest.approx(2 / 3)


class TestNDCG:
    def test_perfect_ndcg(self):
        retrieved = ["a", "b", "c"]
        scores = {"a": 3.0, "b": 2.0, "c": 1.0}
        assert ndcg_at_k(retrieved, scores, 3) == pytest.approx(1.0)

    def test_reversed_ndcg(self):
        retrieved = ["c", "b", "a"]
        scores = {"a": 3.0, "b": 2.0, "c": 1.0}
        result = ndcg_at_k(retrieved, scores, 3)
        assert result < 1.0
        assert result > 0.0

    def test_no_relevant_results(self):
        retrieved = ["x", "y", "z"]
        scores = {"a": 1.0}
        assert ndcg_at_k(retrieved, scores, 3) == 0.0

    def test_empty_scores(self):
        assert ndcg_at_k(["a", "b"], {}, 2) == 0.0


class TestMRR:
    def test_first_position(self):
        assert mrr(["a", "b", "c"], {"a"}) == 1.0

    def test_second_position(self):
        assert mrr(["x", "a", "b"], {"a"}) == 0.5

    def test_third_position(self):
        assert mrr(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_no_relevant(self):
        assert mrr(["x", "y", "z"], {"a"}) == 0.0

    def test_empty_retrieved(self):
        assert mrr([], {"a"}) == 0.0


class TestEvidenceLevelAccuracy:
    def test_high_evidence(self):
        levels = ["1a", "1b", "1a"]
        result = evidence_level_accuracy(levels)
        assert result >= 6.0  # Average of 7, 6, 7

    def test_low_evidence(self):
        levels = ["4", "5", "5"]
        result = evidence_level_accuracy(levels)
        assert result <= 2.0

    def test_mixed_evidence(self):
        levels = ["1a", "3", "5"]
        result = evidence_level_accuracy(levels)
        expected = (7 + 3 + 1) / 3
        assert result == pytest.approx(expected)

    def test_empty(self):
        assert evidence_level_accuracy([]) == 0.0

    def test_none_values(self):
        levels = [None, None]
        result = evidence_level_accuracy(levels)
        assert result == 1.0  # Default to level 5 = score 1


class TestEvaluateSingleQuery:
    def test_full_evaluation(self):
        metrics = evaluate_single_query(
            query_id="test-001",
            retrieved_ids=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
            relevant_ids={"a", "c", "e"},
            evidence_levels=["1a", "2a", "1b", "3", "1a", "4", "5", "5", "3", "2b"],
        )
        assert metrics.query_id == "test-001"
        assert metrics.precision_at_5 == 0.6  # 3 of 5
        assert metrics.recall_at_10 == 1.0  # All 3 found in top 10
        assert metrics.mrr == 1.0  # First result is relevant
        assert metrics.num_results == 10
        assert metrics.num_relevant == 3


class TestAggregateMetrics:
    def test_aggregation(self):
        m1 = evaluate_single_query(
            "q1", ["a", "b"], {"a"}, ["1a", "2a"]
        )
        m2 = evaluate_single_query(
            "q2", ["x", "a"], {"a"}, ["3", "1b"]
        )
        agg = aggregate_metrics("test", [m1, m2])
        assert agg.num_queries == 2
        assert agg.mean_mrr == pytest.approx((1.0 + 0.5) / 2)

    def test_per_domain_breakdown(self):
        m1 = evaluate_single_query("q1", ["a"], {"a"}, ["1a"])
        m2 = evaluate_single_query("q2", ["a"], {"a"}, ["2a"])
        m3 = evaluate_single_query("q3", ["x"], {"a"}, ["3"])

        domains = {"q1": "degenerative", "q2": "degenerative", "q3": "trauma"}
        agg = aggregate_metrics("test", [m1, m2, m3], domains)

        assert "degenerative" in agg.per_domain
        assert "trauma" in agg.per_domain
        assert agg.per_domain["degenerative"]["num_queries"] == 2
        assert agg.per_domain["trauma"]["num_queries"] == 1

    def test_empty_aggregation(self):
        agg = aggregate_metrics("empty", [])
        assert agg.num_queries == 0
        assert agg.mean_ndcg_at_10 == 0.0

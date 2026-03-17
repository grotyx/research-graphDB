"""Tests for RAGAS End-to-End evaluator.

Tests each metric function independently with mock LLM responses,
edge cases, and the RAGASEvaluator class.
"""

import asyncio
import pytest
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

from evaluation.ragas_evaluator import (
    RAGASEvaluator,
    RAGASResult,
    RAGASScores,
    answer_relevancy,
    citation_fidelity,
    context_precision,
    context_recall,
    faithfulness,
    _extract_paper_ids,
    _numbered_list,
)


# ============================================================================
# Mock LLM
# ============================================================================

class MockLLM:
    """Mock LLM that returns pre-configured JSON responses."""

    def __init__(self, responses: Optional[list[dict]] = None):
        self._responses = list(responses) if responses else []
        self._call_index = 0

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        use_cache: bool = True,
    ) -> dict:
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        return {}

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        use_cache: bool = True,
    ) -> Any:
        @dataclass
        class FakeResponse:
            text: str = "mock response"
        return FakeResponse()


# ============================================================================
# Faithfulness Tests
# ============================================================================

class TestFaithfulness:
    """Tests for the faithfulness metric."""

    @pytest.mark.asyncio
    async def test_perfect_faithfulness(self):
        """All claims supported by context."""
        llm = MockLLM([
            {"claims": ["ACDF has good outcomes", "Fusion rate is 95%"]},
            {"verdicts": ["supported", "supported"]},
        ])
        score = await faithfulness(
            question="What are ACDF outcomes?",
            answer="ACDF has good outcomes. Fusion rate is 95%.",
            contexts=["ACDF shows 95% fusion rate with good clinical outcomes."],
            ground_truth="",
            llm=llm,
        )
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_partial_faithfulness(self):
        """Some claims not supported."""
        llm = MockLLM([
            {"claims": ["Claim A", "Claim B", "Claim C"]},
            {"verdicts": ["supported", "not_supported", "supported"]},
        ])
        score = await faithfulness(
            question="Q?",
            answer="A with three claims.",
            contexts=["Some context"],
            ground_truth="",
            llm=llm,
        )
        assert abs(score - 2.0 / 3.0) < 1e-6

    @pytest.mark.asyncio
    async def test_no_claims_extracted(self):
        """No claims extracted = vacuously faithful."""
        llm = MockLLM([{"claims": []}])
        score = await faithfulness(
            question="Q?",
            answer="Short answer.",
            contexts=["Context"],
            ground_truth="",
            llm=llm,
        )
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_empty_answer(self):
        """Empty answer returns 0."""
        llm = MockLLM()
        score = await faithfulness(
            question="Q?", answer="", contexts=["Context"],
            ground_truth="", llm=llm,
        )
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_empty_contexts(self):
        """No context returns 0."""
        llm = MockLLM()
        score = await faithfulness(
            question="Q?", answer="Some answer", contexts=[],
            ground_truth="", llm=llm,
        )
        assert score == 0.0


# ============================================================================
# Answer Relevancy Tests
# ============================================================================

class TestAnswerRelevancy:
    """Tests for the answer_relevancy metric."""

    @pytest.mark.asyncio
    async def test_high_relevancy(self):
        """Reverse questions very similar to original."""
        llm = MockLLM([
            {"questions": ["What are lumbar fusion outcomes?", "How does lumbar fusion perform?"]},
            {"similarity": 0.9},
            {"similarity": 0.85},
        ])
        score = await answer_relevancy(
            question="What are the outcomes of lumbar fusion?",
            answer="Lumbar fusion has good outcomes with 90% success rate.",
            contexts=[], ground_truth="", llm=llm,
        )
        assert abs(score - 0.875) < 1e-6

    @pytest.mark.asyncio
    async def test_low_relevancy(self):
        """Reverse questions dissimilar to original."""
        llm = MockLLM([
            {"questions": ["What is the weather?", "How to cook pasta?"]},
            {"similarity": 0.1},
            {"similarity": 0.05},
        ])
        score = await answer_relevancy(
            question="What are ACDF complications?",
            answer="Irrelevant answer about cooking.",
            contexts=[], ground_truth="", llm=llm,
        )
        assert score < 0.15

    @pytest.mark.asyncio
    async def test_empty_answer_relevancy(self):
        """Empty answer returns 0."""
        llm = MockLLM()
        score = await answer_relevancy(
            question="Q?", answer="", contexts=[], ground_truth="", llm=llm,
        )
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_no_reverse_questions(self):
        """LLM returns no reverse questions."""
        llm = MockLLM([{"questions": []}])
        score = await answer_relevancy(
            question="Q?", answer="Some answer.", contexts=[],
            ground_truth="", llm=llm,
        )
        assert score == 0.0


# ============================================================================
# Context Precision Tests
# ============================================================================

class TestContextPrecision:
    """Tests for the context_precision metric."""

    @pytest.mark.asyncio
    async def test_all_relevant(self):
        """All chunks relevant = perfect precision."""
        llm = MockLLM([
            {"relevance": ["relevant", "relevant", "relevant"]},
        ])
        score = await context_precision(
            question="Q?", answer="A.",
            contexts=["C1", "C2", "C3"],
            ground_truth="GT", llm=llm,
        )
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_first_relevant_rest_not(self):
        """Only first chunk relevant."""
        llm = MockLLM([
            {"relevance": ["relevant", "irrelevant", "irrelevant"]},
        ])
        score = await context_precision(
            question="Q?", answer="A.",
            contexts=["C1", "C2", "C3"],
            ground_truth="GT", llm=llm,
        )
        # precision@1 = 1/1 = 1.0, only 1 relevant, so score = 1.0/1 = 1.0
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_last_relevant_only(self):
        """Only last chunk relevant — worst ranking."""
        llm = MockLLM([
            {"relevance": ["irrelevant", "irrelevant", "relevant"]},
        ])
        score = await context_precision(
            question="Q?", answer="A.",
            contexts=["C1", "C2", "C3"],
            ground_truth="GT", llm=llm,
        )
        # precision@3 = 1/3, only 1 relevant, score = (1/3) / 1 = 0.333...
        assert abs(score - 1.0 / 3.0) < 1e-6

    @pytest.mark.asyncio
    async def test_no_relevant_chunks(self):
        """No relevant chunks."""
        llm = MockLLM([
            {"relevance": ["irrelevant", "irrelevant"]},
        ])
        score = await context_precision(
            question="Q?", answer="A.",
            contexts=["C1", "C2"],
            ground_truth="GT", llm=llm,
        )
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_empty_contexts_precision(self):
        """Empty contexts returns 0."""
        llm = MockLLM()
        score = await context_precision(
            question="Q?", answer="A.", contexts=[],
            ground_truth="GT", llm=llm,
        )
        assert score == 0.0


# ============================================================================
# Context Recall Tests
# ============================================================================

class TestContextRecall:
    """Tests for the context_recall metric."""

    @pytest.mark.asyncio
    async def test_full_recall(self):
        """All aspects covered."""
        llm = MockLLM([
            {"aspects": ["Aspect 1", "Aspect 2"]},
            {"coverage": ["covered", "covered"]},
        ])
        score = await context_recall(
            question="Q?", answer="A.",
            contexts=["Context covering everything"],
            ground_truth="Full ground truth.",
            llm=llm,
        )
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_partial_recall(self):
        """Half of aspects covered."""
        llm = MockLLM([
            {"aspects": ["A1", "A2", "A3", "A4"]},
            {"coverage": ["covered", "not_covered", "covered", "not_covered"]},
        ])
        score = await context_recall(
            question="Q?", answer="A.",
            contexts=["Partial context"],
            ground_truth="GT with 4 aspects.",
            llm=llm,
        )
        assert score == 0.5

    @pytest.mark.asyncio
    async def test_no_ground_truth(self):
        """Empty ground truth returns 0."""
        llm = MockLLM()
        score = await context_recall(
            question="Q?", answer="A.",
            contexts=["Context"],
            ground_truth="",
            llm=llm,
        )
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_no_aspects_extracted(self):
        """No aspects extracted = vacuously complete."""
        llm = MockLLM([{"aspects": []}])
        score = await context_recall(
            question="Q?", answer="A.",
            contexts=["Context"],
            ground_truth="GT",
            llm=llm,
        )
        assert score == 1.0


# ============================================================================
# Citation Fidelity Tests
# ============================================================================

class TestCitationFidelity:
    """Tests for the citation_fidelity metric (no LLM needed)."""

    def test_all_citations_correct(self):
        """All cited paper_ids are in context sources."""
        score = citation_fidelity(
            question="Q?",
            answer="According to [paper_id:abc123] and [paper_id:def456]...",
            contexts=[],
            ground_truth="",
            context_paper_ids=["abc123", "def456", "ghi789"],
        )
        assert score == 1.0

    def test_some_citations_wrong(self):
        """One of two citations not in context."""
        score = citation_fidelity(
            question="Q?",
            answer="See paper_id=abc123 and paper_id=unknown999.",
            contexts=[],
            ground_truth="",
            context_paper_ids=["abc123", "def456"],
        )
        assert score == 0.5

    def test_no_citations(self):
        """No citations in answer = vacuously correct."""
        score = citation_fidelity(
            question="Q?",
            answer="A general answer with no paper references.",
            contexts=[],
            ground_truth="",
            context_paper_ids=["abc123"],
        )
        assert score == 1.0

    def test_empty_answer_citation(self):
        """Empty answer returns 0."""
        score = citation_fidelity(
            question="Q?", answer="", contexts=[], ground_truth="",
        )
        assert score == 0.0

    def test_pmid_citations(self):
        """PMID-style citations extracted and matched."""
        score = citation_fidelity(
            question="Q?",
            answer="As shown in PMID:12345678 and PMID 87654321...",
            contexts=[],
            ground_truth="",
            context_paper_ids=["PMID12345678", "PMID87654321"],
        )
        assert score == 1.0

    def test_no_context_paper_ids(self):
        """No context paper_ids means all citations wrong."""
        score = citation_fidelity(
            question="Q?",
            answer="See paper_id=abc123.",
            contexts=[],
            ground_truth="",
            context_paper_ids=None,
        )
        assert score == 0.0


# ============================================================================
# Helper Function Tests
# ============================================================================

class TestHelpers:
    """Tests for pure helper functions."""

    def test_extract_paper_ids_mixed(self):
        """Extract various paper_id formats."""
        text = "See paper_id:abc123, also PMID:12345678 and doi 10.1234/test.2024"
        ids = _extract_paper_ids(text)
        assert "abc123" in ids
        assert "PMID12345678" in ids
        assert "10.1234/test.2024" in ids

    def test_extract_paper_ids_empty(self):
        """No paper_ids in text."""
        ids = _extract_paper_ids("A plain text answer with no references.")
        assert ids == []

    def test_numbered_list(self):
        """Format a numbered list."""
        result = _numbered_list(["A", "B", "C"])
        assert result == "1. A\n2. B\n3. C"


# ============================================================================
# RAGASScores Tests
# ============================================================================

class TestRAGASScores:
    """Tests for the RAGASScores dataclass."""

    def test_to_dict(self):
        """Scores serialized to dict with rounding."""
        scores = RAGASScores(
            faithfulness=0.8333333,
            answer_relevancy=0.75,
            context_precision=0.6667,
            context_recall=1.0,
            citation_fidelity=0.5,
        )
        d = scores.to_dict()
        assert d["faithfulness"] == 0.8333
        assert d["context_recall"] == 1.0

    def test_overall_harmonic_mean(self):
        """Overall score is harmonic mean of 4 core metrics."""
        scores = RAGASScores(
            faithfulness=1.0,
            answer_relevancy=1.0,
            context_precision=1.0,
            context_recall=1.0,
        )
        assert scores.overall == 1.0

    def test_overall_with_zeros(self):
        """Harmonic mean ignores zero scores."""
        scores = RAGASScores(
            faithfulness=0.0,
            answer_relevancy=0.8,
            context_precision=0.0,
            context_recall=0.8,
        )
        # HM of [0.8, 0.8] = 0.8
        assert abs(scores.overall - 0.8) < 1e-6

    def test_overall_all_zeros(self):
        """All zero scores returns 0."""
        scores = RAGASScores()
        assert scores.overall == 0.0


# ============================================================================
# RAGASEvaluator Class Tests
# ============================================================================

class TestRAGASEvaluator:
    """Tests for the RAGASEvaluator class."""

    @pytest.mark.asyncio
    async def test_evaluate_all_metrics(self):
        """Run all metrics on a sample query."""
        llm = MockLLM([
            # faithfulness: extract claims
            {"claims": ["Claim A"]},
            # faithfulness: verify claims
            {"verdicts": ["supported"]},
            # answer_relevancy: reverse questions
            {"questions": ["Reverse Q1?", "Reverse Q2?", "Reverse Q3?"]},
            # answer_relevancy: similarity x3
            {"similarity": 0.9},
            {"similarity": 0.8},
            {"similarity": 0.85},
            # context_precision: judge relevance
            {"relevance": ["relevant"]},
            # context_recall: extract aspects
            {"aspects": ["Aspect 1"]},
            # context_recall: check coverage
            {"coverage": ["covered"]},
        ])

        evaluator = RAGASEvaluator(llm=llm)
        result = await evaluator.evaluate(
            question="What is the best treatment for lumbar stenosis?",
            answer="Decompression surgery is effective. [paper_id:p001]",
            contexts=["Decompression shows 85% success rate for lumbar stenosis."],
            ground_truth="Decompression is the standard treatment.",
            context_paper_ids=["p001"],
            query_id="test_q1",
        )

        assert result.query_id == "test_q1"
        assert result.scores.faithfulness == 1.0
        assert abs(result.scores.answer_relevancy - 0.85) < 1e-6
        assert result.scores.context_precision == 1.0
        assert result.scores.context_recall == 1.0
        assert result.scores.citation_fidelity == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_selected_metrics(self):
        """Run only selected metrics."""
        llm = MockLLM([
            {"claims": ["Claim"]},
            {"verdicts": ["supported"]},
        ])

        evaluator = RAGASEvaluator(llm=llm, metrics=["faithfulness"])
        result = await evaluator.evaluate(
            question="Q?",
            answer="A. [paper_id:x]",
            contexts=["C"],
            ground_truth="GT",
            context_paper_ids=["x"],
        )

        assert result.scores.faithfulness == 1.0
        # Other metrics not run, should stay at default 0.0
        assert result.scores.answer_relevancy == 0.0
        assert result.scores.context_precision == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_batch(self):
        """Batch evaluation of multiple items."""
        llm = MockLLM([
            # Item 1: faithfulness
            {"claims": ["C1"]}, {"verdicts": ["supported"]},
            # Item 1: answer_relevancy
            {"questions": ["RQ?"]}, {"similarity": 0.9},
            # Item 1: context_precision
            {"relevance": ["relevant"]},
            # Item 1: context_recall
            {"aspects": ["A1"]}, {"coverage": ["covered"]},
            # Item 2: faithfulness
            {"claims": ["C2"]}, {"verdicts": ["not_supported"]},
            # Item 2: answer_relevancy
            {"questions": ["RQ2?"]}, {"similarity": 0.5},
            # Item 2: context_precision
            {"relevance": ["irrelevant"]},
            # Item 2: context_recall
            {"aspects": ["A2"]}, {"coverage": ["not_covered"]},
        ])

        evaluator = RAGASEvaluator(llm=llm)
        results = await evaluator.evaluate_batch([
            {
                "question": "Q1?", "answer": "A1.", "contexts": ["C1"],
                "ground_truth": "GT1", "query_id": "q1",
            },
            {
                "question": "Q2?", "answer": "A2.", "contexts": ["C2"],
                "ground_truth": "GT2", "query_id": "q2",
            },
        ])

        assert len(results) == 2
        assert results[0].query_id == "q1"
        assert results[1].query_id == "q2"

    @pytest.mark.asyncio
    async def test_aggregate_scores(self):
        """Aggregate scores across multiple results."""
        r1 = RAGASResult(
            query_id="q1", question="Q1?",
            scores=RAGASScores(
                faithfulness=1.0, answer_relevancy=0.8,
                context_precision=0.6, context_recall=1.0,
                citation_fidelity=1.0,
            ),
        )
        r2 = RAGASResult(
            query_id="q2", question="Q2?",
            scores=RAGASScores(
                faithfulness=0.5, answer_relevancy=0.6,
                context_precision=0.4, context_recall=0.5,
                citation_fidelity=0.0,
            ),
        )

        agg = RAGASEvaluator.aggregate_scores([r1, r2])
        assert agg["faithfulness"] == 0.75
        assert agg["answer_relevancy"] == 0.7
        assert agg["num_queries"] == 2

    @pytest.mark.asyncio
    async def test_aggregate_empty(self):
        """Aggregate with no results returns empty dict."""
        assert RAGASEvaluator.aggregate_scores([]) == {}

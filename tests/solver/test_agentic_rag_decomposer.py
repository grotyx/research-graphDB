"""Tests for ClinicalQueryDecomposer, ResultAggregator, and agentic_solve.

Tests cover:
    - Rule-based query decomposition for clinical queries
    - LLM-based decomposition (mocked)
    - Result aggregation and deduplication
    - Multi-aspect bonus scoring
    - agentic_solve pipeline (mocked)
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch

from src.solver.agentic_rag import (
    ClinicalQueryDecomposer,
    ResultAggregator,
    SubQuery,
    agentic_solve,
)


# =============================================================================
# Test ClinicalQueryDecomposer - Rule-based
# =============================================================================

class TestClinicalQueryDecomposerRules:
    """Test rule-based query decomposition."""

    def setup_method(self):
        self.decomposer = ClinicalQueryDecomposer(llm_client=None)

    @pytest.mark.asyncio
    async def test_simple_query_no_decomposition(self):
        """Simple query with single aspect should not decompose."""
        subs = await self.decomposer.decompose("What is TLIF?")
        assert len(subs) == 1
        assert subs[0].aspect == "general"

    @pytest.mark.asyncio
    async def test_complex_query_stenosis_dm(self):
        """Complex clinical query with pathology + comorbidity should decompose."""
        subs = await self.decomposer.decompose(
            "50 years old female, L4-5 stenosis with diabetes, best surgery?"
        )
        assert len(subs) >= 2
        aspects = {sq.aspect for sq in subs}
        # Should detect pathology+intervention and comorbidity at minimum
        assert len(aspects) >= 2

    @pytest.mark.asyncio
    async def test_comparison_query(self):
        """Comparison query should detect intervention aspects."""
        subs = await self.decomposer.decompose(
            "Compare TLIF vs OLIF for lumbar stenosis outcomes"
        )
        assert len(subs) >= 2

    @pytest.mark.asyncio
    async def test_anatomy_detection(self):
        """Anatomy terms in query should be incorporated."""
        subs = await self.decomposer.decompose(
            "L4 stenosis surgery decompression complication rate"
        )
        # Should detect pathology+intervention, outcome
        assert len(subs) >= 2

    @pytest.mark.asyncio
    async def test_demographics_detection(self):
        """Demographic terms should trigger demographics sub-query."""
        subs = await self.decomposer.decompose(
            "elderly female lumbar stenosis surgical outcome"
        )
        aspects = {sq.aspect for sq in subs}
        assert "demographics" in aspects or len(subs) >= 2

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """Sub-queries should have decreasing priority."""
        subs = await self.decomposer.decompose(
            "50 years old stenosis surgery with diabetes complication outcome"
        )
        if len(subs) > 1:
            for i in range(len(subs) - 1):
                assert subs[i].priority >= subs[i + 1].priority


# =============================================================================
# Test ClinicalQueryDecomposer - LLM-based
# =============================================================================

class TestClinicalQueryDecomposerLLM:
    """Test LLM-based query decomposition."""

    @pytest.mark.asyncio
    async def test_llm_decomposition(self):
        """LLM should produce structured sub-queries."""
        mock_llm = Mock()
        mock_llm.generate_json = AsyncMock(return_value={
            "sub_queries": [
                {"query": "L4-5 stenosis surgical options", "aspect": "pathology", "priority": 10},
                {"query": "diabetes spine surgery complications", "aspect": "comorbidity", "priority": 8},
            ]
        })

        decomposer = ClinicalQueryDecomposer(llm_client=mock_llm)
        subs = await decomposer.decompose("50yo, L4-5 stenosis, DM, best surgery?")

        assert len(subs) == 2
        assert subs[0].aspect == "pathology"
        assert subs[1].aspect == "comorbidity"
        assert mock_llm.generate_json.called

    @pytest.mark.asyncio
    async def test_llm_fallback_to_rules(self):
        """If LLM fails, should fall back to rule-based."""
        mock_llm = Mock()
        mock_llm.generate_json = AsyncMock(side_effect=Exception("LLM error"))

        decomposer = ClinicalQueryDecomposer(llm_client=mock_llm)
        subs = await decomposer.decompose(
            "lumbar stenosis surgery with diabetes complications"
        )

        # Should still produce results via rule-based fallback
        assert len(subs) >= 1

    @pytest.mark.asyncio
    async def test_llm_empty_result_fallback(self):
        """If LLM returns empty sub_queries, should return original query."""
        mock_llm = Mock()
        mock_llm.generate_json = AsyncMock(return_value={"sub_queries": []})

        decomposer = ClinicalQueryDecomposer(llm_client=mock_llm)
        subs = await decomposer.decompose("test query")

        assert len(subs) == 1
        assert subs[0].query == "test query"
        assert subs[0].aspect == "general"


# =============================================================================
# Test ResultAggregator
# =============================================================================

class TestResultAggregator:
    """Test result aggregation and deduplication."""

    def test_aggregate_single_source(self):
        """Single sub-query results should pass through."""
        sub_results = [
            {
                "aspect": "pathology",
                "results": [
                    {"paper_id": "P1", "title": "Paper 1", "score": 0.9},
                    {"paper_id": "P2", "title": "Paper 2", "score": 0.7},
                ],
            }
        ]

        aggregated = ResultAggregator.aggregate(sub_results)

        assert len(aggregated) == 2
        assert aggregated[0]["paper_id"] == "P1"
        assert aggregated[0]["final_score"] == 0.9  # No multi-aspect bonus

    def test_aggregate_deduplication(self):
        """Duplicate papers across sub-queries should be merged."""
        sub_results = [
            {
                "aspect": "pathology",
                "results": [
                    {"paper_id": "P1", "title": "Paper 1", "score": 0.8},
                ],
            },
            {
                "aspect": "comorbidity",
                "results": [
                    {"paper_id": "P1", "title": "Paper 1", "score": 0.7},
                ],
            },
        ]

        aggregated = ResultAggregator.aggregate(sub_results)

        assert len(aggregated) == 1
        assert aggregated[0]["paper_id"] == "P1"
        assert aggregated[0]["match_count"] == 2
        # Score = avg(0.8, 0.7) + 0.1 bonus = 0.75 + 0.1 = 0.85
        assert abs(aggregated[0]["final_score"] - 0.85) < 0.01

    def test_aggregate_multi_aspect_bonus(self):
        """Papers matching 3+ aspects should get higher bonus (capped at 0.2)."""
        sub_results = [
            {"aspect": "a1", "results": [{"paper_id": "P1", "title": "T", "score": 0.6}]},
            {"aspect": "a2", "results": [{"paper_id": "P1", "title": "T", "score": 0.6}]},
            {"aspect": "a3", "results": [{"paper_id": "P1", "title": "T", "score": 0.6}]},
        ]

        aggregated = ResultAggregator.aggregate(sub_results)

        assert len(aggregated) == 1
        # Score = avg(0.6, 0.6, 0.6) + min(0.2, 2*0.1) = 0.6 + 0.2 = 0.8
        assert abs(aggregated[0]["final_score"] - 0.8) < 0.01
        assert set(aggregated[0]["matched_aspects"]) == {"a1", "a2", "a3"}

    def test_aggregate_max_results(self):
        """Should respect max_results limit."""
        sub_results = [
            {
                "aspect": "general",
                "results": [
                    {"paper_id": f"P{i}", "title": f"Paper {i}", "score": 0.5}
                    for i in range(30)
                ],
            }
        ]

        aggregated = ResultAggregator.aggregate(sub_results, max_results=10)
        assert len(aggregated) == 10

    def test_aggregate_empty(self):
        """Empty input should return empty output."""
        assert ResultAggregator.aggregate([]) == []
        assert ResultAggregator.aggregate([{"aspect": "a", "results": []}]) == []

    def test_aggregate_sorting(self):
        """Results should be sorted by final_score descending."""
        sub_results = [
            {
                "aspect": "general",
                "results": [
                    {"paper_id": "P1", "title": "T1", "score": 0.3},
                    {"paper_id": "P2", "title": "T2", "score": 0.9},
                    {"paper_id": "P3", "title": "T3", "score": 0.6},
                ],
            }
        ]

        aggregated = ResultAggregator.aggregate(sub_results)

        assert aggregated[0]["paper_id"] == "P2"
        assert aggregated[1]["paper_id"] == "P3"
        assert aggregated[2]["paper_id"] == "P1"

    def test_aggregate_missing_paper_id_skipped(self):
        """Results without paper_id should be skipped."""
        sub_results = [
            {
                "aspect": "general",
                "results": [
                    {"paper_id": "", "title": "No ID", "score": 0.5},
                    {"paper_id": "P1", "title": "Has ID", "score": 0.5},
                ],
            }
        ]

        aggregated = ResultAggregator.aggregate(sub_results)
        assert len(aggregated) == 1
        assert aggregated[0]["paper_id"] == "P1"


# =============================================================================
# Test SubQuery dataclass
# =============================================================================

def test_sub_query_creation():
    """Test SubQuery dataclass creation."""
    sq = SubQuery(query="L4-5 stenosis", aspect="pathology", priority=10)
    assert sq.query == "L4-5 stenosis"
    assert sq.aspect == "pathology"
    assert sq.priority == 10


def test_sub_query_defaults():
    """Test SubQuery default values."""
    sq = SubQuery(query="test", aspect="general")
    assert sq.priority == 5


# =============================================================================
# Test agentic_solve pipeline (mocked)
# =============================================================================

@pytest.mark.asyncio
async def test_agentic_solve_returns_structure():
    """agentic_solve should return a dict with expected keys."""
    # No neo4j_client or llm_client means decompose only, no search results
    result = await agentic_solve("What is TLIF?", neo4j_client=None, llm_client=None)

    assert "sub_queries" in result
    assert "sub_results" in result
    assert "aggregated" in result
    assert "reasoning_chain" in result
    assert "metadata" in result
    assert isinstance(result["sub_queries"], list)
    assert len(result["sub_queries"]) >= 1


@pytest.mark.asyncio
async def test_agentic_solve_complex_query():
    """agentic_solve with complex query should produce multiple sub-queries."""
    result = await agentic_solve(
        "elderly female lumbar stenosis surgery diabetes complication",
        neo4j_client=None,
    )

    assert len(result["sub_queries"]) >= 2
    assert result["metadata"]["total_sub_queries"] >= 2

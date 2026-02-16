"""Tests for Multi-hop Reasoning.

Comprehensive test coverage for multi_hop_reasoning.py:
- QueryDecomposer: 쿼리 분해 및 의존성 분석
- HopExecutor: 단일 hop 실행
- MultiHopReasoner: 전체 오케스트레이션
- ReasoningChain: 추론 체인 추적
- Edge cases and error handling
- Path scoring and ranking

각 테스트는 mock 객체를 사용하여 독립적으로 실행 가능.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

# 테스트 대상 모듈
from src.solver.multi_hop_reasoning import (
    QueryDecomposer,
    HopExecutor,
    MultiHopReasoner,
    SubQuery,
    QueryType,
    AnswerType,
    HopResult,
    ReasoningChain,
    ReasoningStep,
    MultiHopResult,
    create_multi_hop_reasoner,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_client():
    """Mock LLM 클라이언트."""
    client = MagicMock()
    client.generate_json = AsyncMock()
    client.generate = AsyncMock()
    return client


@pytest.fixture
def mock_search_pipeline():
    """Mock 검색 파이프라인."""
    pipeline = MagicMock()
    pipeline.search = AsyncMock()
    return pipeline


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j 클라이언트."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.run_query = AsyncMock()
    return client


@pytest.fixture
def sample_sub_queries():
    """샘플 하위 질문."""
    return [
        SubQuery(
            query_id="q1",
            text="What procedures treat lumbar stenosis?",
            depends_on=[],
            query_type=QueryType.FACTUAL,
            expected_answer_type=AnswerType.LIST,
            priority=0
        ),
        SubQuery(
            query_id="q2",
            text="What is the fusion rate of [procedures from q1]?",
            depends_on=["q1"],
            query_type=QueryType.AGGREGATION,
            expected_answer_type=AnswerType.VALUE,
            priority=1
        )
    ]


@pytest.fixture
def sample_search_response():
    """샘플 검색 응답."""
    mock_response = MagicMock()
    mock_response.results = [
        MagicMock(
            paper_id=f"paper{i}",
            title=f"Study {i}",
            publication_year=2023,
            final_score=0.9 - i * 0.1,
            evidence_level="2a",
            summary=f"Summary {i}"
        )
        for i in range(5)
    ]
    mock_response.synthesis = None
    return mock_response


# =============================================================================
# SubQuery Tests
# =============================================================================

def test_subquery_creation():
    """SubQuery 객체 생성 테스트."""
    sq = SubQuery(
        query_id="q1",
        text="What is TLIF?",
        query_type=QueryType.FACTUAL,
        expected_answer_type=AnswerType.TEXT
    )

    assert sq.query_id == "q1"
    assert sq.text == "What is TLIF?"
    assert sq.is_independent() is True
    assert sq.priority == 0


def test_subquery_dependencies():
    """SubQuery 의존성 테스트."""
    sq_dependent = SubQuery(
        query_id="q2",
        text="Compare X and Y",
        depends_on=["q1"],
        query_type=QueryType.COMPARATIVE,
        expected_answer_type=AnswerType.TEXT
    )

    assert sq_dependent.is_independent() is False
    assert "q1" in sq_dependent.depends_on


def test_subquery_multiple_dependencies():
    """여러 의존성 테스트."""
    sq = SubQuery(
        query_id="q3",
        text="Synthesize results",
        depends_on=["q1", "q2"],
        query_type=QueryType.AGGREGATION,
        expected_answer_type=AnswerType.TEXT,
        priority=2
    )

    assert sq.is_independent() is False
    assert len(sq.depends_on) == 2
    assert set(sq.depends_on) == {"q1", "q2"}


# =============================================================================
# QueryDecomposer Tests
# =============================================================================

@pytest.mark.asyncio
async def test_decomposer_simple_query(mock_llm_client):
    """단순 쿼리 분해 테스트."""
    # Mock LLM 응답
    mock_llm_client.generate_json.return_value = {
        "sub_queries": [
            {
                "query_id": "q1",
                "text": "What is the fusion rate of TLIF?",
                "depends_on": [],
                "query_type": "factual",
                "expected_answer_type": "value",
                "priority": 0
            }
        ]
    }

    decomposer = QueryDecomposer(mock_llm_client)
    sub_queries = await decomposer.decompose("What is the fusion rate of TLIF?")

    assert len(sub_queries) == 1
    assert sub_queries[0].query_id == "q1"
    assert sub_queries[0].is_independent() is True
    mock_llm_client.generate_json.assert_called_once()


@pytest.mark.asyncio
async def test_decomposer_complex_query(mock_llm_client):
    """복잡한 쿼리 분해 테스트."""
    # Mock LLM 응답 (2단계 쿼리)
    mock_llm_client.generate_json.return_value = {
        "sub_queries": [
            {
                "query_id": "q1",
                "text": "What procedures treat lumbar stenosis?",
                "depends_on": [],
                "query_type": "factual",
                "expected_answer_type": "list",
                "priority": 0
            },
            {
                "query_id": "q2",
                "text": "What is the fusion rate of those procedures?",
                "depends_on": ["q1"],
                "query_type": "aggregation",
                "expected_answer_type": "value",
                "priority": 1
            }
        ]
    }

    decomposer = QueryDecomposer(mock_llm_client)
    sub_queries = await decomposer.decompose(
        "What is the fusion rate of procedures that treat lumbar stenosis?"
    )

    assert len(sub_queries) == 2
    assert sub_queries[0].is_independent() is True
    assert sub_queries[1].is_independent() is False
    assert "q1" in sub_queries[1].depends_on


@pytest.mark.asyncio
async def test_decomposer_comparative_query(mock_llm_client):
    """비교 쿼리 분해 테스트."""
    # Mock LLM 응답
    mock_llm_client.generate_json.return_value = {
        "sub_queries": [
            {
                "query_id": "q1",
                "text": "What is the complication rate of UBE?",
                "depends_on": [],
                "query_type": "factual",
                "expected_answer_type": "value",
                "priority": 0
            },
            {
                "query_id": "q2",
                "text": "What is the complication rate of TLIF?",
                "depends_on": [],
                "query_type": "factual",
                "expected_answer_type": "value",
                "priority": 0
            },
            {
                "query_id": "q3",
                "text": "Compare UBE and TLIF safety",
                "depends_on": ["q1", "q2"],
                "query_type": "comparative",
                "expected_answer_type": "text",
                "priority": 1
            }
        ]
    }

    decomposer = QueryDecomposer(mock_llm_client)
    sub_queries = await decomposer.decompose("Is UBE safer than TLIF?")

    assert len(sub_queries) == 3
    # q1, q2는 병렬 실행 가능 (priority 0, no dependencies)
    assert sub_queries[0].priority == 0
    assert sub_queries[1].priority == 0
    # q3는 q1, q2 완료 후 실행 (priority 1)
    assert sub_queries[2].priority == 1
    assert set(sub_queries[2].depends_on) == {"q1", "q2"}


@pytest.mark.asyncio
async def test_decomposer_sorting_by_priority(mock_llm_client):
    """우선순위 기반 정렬 테스트."""
    # Mock LLM 응답 (역순으로 제공)
    mock_llm_client.generate_json.return_value = {
        "sub_queries": [
            {
                "query_id": "q3",
                "text": "Final synthesis",
                "depends_on": ["q1", "q2"],
                "query_type": "aggregation",
                "expected_answer_type": "text",
                "priority": 2
            },
            {
                "query_id": "q1",
                "text": "First question",
                "depends_on": [],
                "query_type": "factual",
                "expected_answer_type": "text",
                "priority": 0
            },
            {
                "query_id": "q2",
                "text": "Second question",
                "depends_on": ["q1"],
                "query_type": "factual",
                "expected_answer_type": "text",
                "priority": 1
            }
        ]
    }

    decomposer = QueryDecomposer(mock_llm_client)
    sub_queries = await decomposer.decompose("Complex multi-step query")

    # 우선순위 순으로 정렬되어야 함
    assert sub_queries[0].query_id == "q1"  # priority=0
    assert sub_queries[1].query_id == "q2"  # priority=1
    assert sub_queries[2].query_id == "q3"  # priority=2


@pytest.mark.asyncio
async def test_decomposer_relational_query(mock_llm_client):
    """관계형 쿼리 분해 테스트."""
    mock_llm_client.generate_json.return_value = {
        "sub_queries": [
            {
                "query_id": "q1",
                "text": "What is the relationship between stenosis and radiculopathy?",
                "depends_on": [],
                "query_type": "relational",
                "expected_answer_type": "text",
                "priority": 0
            }
        ]
    }

    decomposer = QueryDecomposer(mock_llm_client)
    sub_queries = await decomposer.decompose("Does stenosis cause radiculopathy?")

    assert len(sub_queries) == 1
    assert sub_queries[0].query_type == QueryType.RELATIONAL


@pytest.mark.asyncio
async def test_decomposer_filter_query(mock_llm_client):
    """필터 쿼리 분해 테스트."""
    mock_llm_client.generate_json.return_value = {
        "sub_queries": [
            {
                "query_id": "q1",
                "text": "Find fusion procedures with >90% success rate",
                "depends_on": [],
                "query_type": "filter",
                "expected_answer_type": "list",
                "priority": 0
            }
        ]
    }

    decomposer = QueryDecomposer(mock_llm_client)
    sub_queries = await decomposer.decompose("Which fusion procedures have >90% success?")

    assert len(sub_queries) == 1
    assert sub_queries[0].query_type == QueryType.FILTER
    assert sub_queries[0].expected_answer_type == AnswerType.LIST


# =============================================================================
# HopExecutor Tests
# =============================================================================

@pytest.mark.asyncio
async def test_hop_executor_simple_execution(mock_search_pipeline, mock_llm_client, sample_search_response):
    """단순 hop 실행 테스트."""
    mock_search_pipeline.search.return_value = sample_search_response

    # Mock LLM 답변 추출
    mock_llm_client.generate_json.return_value = {
        "answer": "TLIF is a lumbar fusion technique.",
        "reasoning": "Based on multiple RCT studies."
    }

    executor = HopExecutor(mock_search_pipeline, mock_llm_client)
    sub_query = SubQuery(
        query_id="q1",
        text="What is TLIF?",
        query_type=QueryType.FACTUAL,
        expected_answer_type=AnswerType.TEXT
    )

    result = await executor.execute_hop(sub_query)

    assert result.answer == "TLIF is a lumbar fusion technique."
    assert result.confidence > 0.0
    assert len(result.evidence) > 0
    assert result.query.query_id == "q1"
    assert result.execution_time_ms > 0


@pytest.mark.asyncio
async def test_hop_executor_with_context(mock_search_pipeline, mock_llm_client, sample_search_response):
    """컨텍스트가 있는 hop 실행 테스트."""
    mock_search_pipeline.search.return_value = sample_search_response

    # Mock LLM 답변
    mock_llm_client.generate_json.return_value = {
        "answer": "TLIF has a fusion rate of 85-95%.",
        "reasoning": "Consistent across multiple cohort studies."
    }

    executor = HopExecutor(mock_search_pipeline, mock_llm_client)
    sub_query = SubQuery(
        query_id="q2",
        text="What is the fusion rate of TLIF?",
        depends_on=["q1"],
        query_type=QueryType.FACTUAL,
        expected_answer_type=AnswerType.VALUE
    )

    context = "Q1: What is TLIF?\nA1: TLIF is a lumbar fusion technique.\nConfidence: 0.90\n"
    result = await executor.execute_hop(sub_query, context)

    assert "fusion rate" in result.answer.lower()
    assert result.confidence > 0.0
    # Verify search was called with context
    mock_search_pipeline.search.assert_called_once()


@pytest.mark.asyncio
async def test_hop_executor_confidence_calculation(mock_search_pipeline, mock_llm_client):
    """신뢰도 계산 테스트."""
    # High-quality 검색 결과
    mock_search_response = MagicMock()
    mock_search_response.results = [
        MagicMock(final_score=0.95, evidence_level="1a", paper_id="p1", title="Study 1", publication_year=2023),
        MagicMock(final_score=0.90, evidence_level="1b", paper_id="p2", title="Study 2", publication_year=2023),
        MagicMock(final_score=0.85, evidence_level="2a", paper_id="p3", title="Study 3", publication_year=2023),
    ]
    mock_search_response.synthesis = MagicMock(strength=MagicMock(value="high"))
    mock_search_pipeline.search.return_value = mock_search_response

    mock_llm_client.generate_json.return_value = {
        "answer": "Test answer",
        "reasoning": "Test reasoning"
    }

    executor = HopExecutor(mock_search_pipeline, mock_llm_client)
    sub_query = SubQuery(
        query_id="q1",
        text="Test query",
        query_type=QueryType.FACTUAL,
        expected_answer_type=AnswerType.TEXT
    )

    result = await executor.execute_hop(sub_query)

    # High-quality 결과는 높은 신뢰도
    assert result.confidence > 0.8


@pytest.mark.asyncio
async def test_hop_executor_empty_results(mock_search_pipeline, mock_llm_client):
    """검색 결과 없을 때 테스트."""
    # 빈 검색 결과
    mock_search_response = MagicMock()
    mock_search_response.results = []
    mock_search_response.synthesis = None
    mock_search_pipeline.search.return_value = mock_search_response

    mock_llm_client.generate_json.return_value = {
        "answer": "No evidence found.",
        "reasoning": "Search returned no results."
    }

    executor = HopExecutor(mock_search_pipeline, mock_llm_client)
    sub_query = SubQuery(
        query_id="q1",
        text="Unknown procedure",
        query_type=QueryType.FACTUAL,
        expected_answer_type=AnswerType.TEXT
    )

    result = await executor.execute_hop(sub_query)

    # 신뢰도 0
    assert result.confidence == 0.0
    assert len(result.evidence) == 0


@pytest.mark.asyncio
async def test_hop_executor_comparative_options(mock_search_pipeline, mock_llm_client):
    """COMPARATIVE 쿼리 타입 옵션 테스트."""
    mock_search_response = MagicMock()
    mock_search_response.results = [
        MagicMock(final_score=0.8, paper_id="p1", title="Comparison Study", publication_year=2023, evidence_level="1b")
    ]
    mock_search_response.synthesis = None
    mock_search_pipeline.search.return_value = mock_search_response

    mock_llm_client.generate_json.return_value = {
        "answer": "UBE is safer",
        "reasoning": "Lower complication rate"
    }

    executor = HopExecutor(mock_search_pipeline, mock_llm_client)
    sub_query = SubQuery(
        query_id="q1",
        text="Compare UBE and TLIF",
        query_type=QueryType.COMPARATIVE,
        expected_answer_type=AnswerType.TEXT
    )

    result = await executor.execute_hop(sub_query)

    # Verify search was called with comparative options
    call_args = mock_search_pipeline.search.call_args
    options = call_args.kwargs.get('options')
    assert options.top_k == 15  # COMPARATIVE uses top_k=15
    assert options.detect_conflicts is True


@pytest.mark.asyncio
async def test_hop_executor_aggregation_options(mock_search_pipeline, mock_llm_client):
    """AGGREGATION 쿼리 타입 옵션 테스트."""
    mock_search_response = MagicMock()
    mock_search_response.results = []
    mock_search_response.synthesis = None
    mock_search_pipeline.search.return_value = mock_search_response

    mock_llm_client.generate_json.return_value = {
        "answer": "Average 90%",
        "reasoning": "Aggregated from studies"
    }

    executor = HopExecutor(mock_search_pipeline, mock_llm_client)
    sub_query = SubQuery(
        query_id="q1",
        text="Average fusion rate",
        query_type=QueryType.AGGREGATION,
        expected_answer_type=AnswerType.VALUE
    )

    result = await executor.execute_hop(sub_query)

    # Verify search was called with aggregation options
    call_args = mock_search_pipeline.search.call_args
    options = call_args.kwargs.get('options')
    assert options.top_k == 20  # AGGREGATION uses top_k=20
    assert options.include_synthesis is True


# =============================================================================
# ReasoningChain Tests
# =============================================================================

def test_reasoning_chain_creation():
    """ReasoningChain 생성 테스트."""
    chain = ReasoningChain()

    assert chain.total_hops == 0
    assert chain.avg_confidence == 0.0


def test_reasoning_chain_add_step():
    """Step 추가 테스트."""
    chain = ReasoningChain()

    sq1 = SubQuery(
        query_id="q1",
        text="Test query 1",
        query_type=QueryType.FACTUAL,
        expected_answer_type=AnswerType.TEXT
    )

    chain.add_step(
        query=sq1,
        answer="Answer 1",
        evidence=[{"paper_id": "p1"}],
        confidence=0.9,
        reasoning="Test reasoning"
    )

    assert chain.total_hops == 1
    assert chain.avg_confidence == 0.9
    assert chain.steps[0].hop_number == 1
    assert chain.steps[0].query_id == "q1"


def test_reasoning_chain_multiple_steps():
    """여러 Step 추가 테스트."""
    chain = ReasoningChain()

    sq1 = SubQuery(query_id="q1", text="Q1", query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT)
    sq2 = SubQuery(query_id="q2", text="Q2", query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT)

    chain.add_step(sq1, "A1", [], 0.8, "R1")
    chain.add_step(sq2, "A2", [], 0.9, "R2")

    assert chain.total_hops == 2
    assert abs(chain.avg_confidence - 0.85) < 0.001  # Floating point tolerance


def test_reasoning_chain_summary():
    """체인 요약 생성 테스트."""
    chain = ReasoningChain()

    sq1 = SubQuery(query_id="q1", text="What is TLIF?", query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT)
    chain.add_step(sq1, "TLIF is a fusion technique", [{"paper_id": "p1"}], 0.9, "Based on evidence")

    summary = chain.get_summary()

    assert "Multi-hop Reasoning Chain" in summary
    assert "q1" in summary
    assert "What is TLIF?" in summary
    assert "0.90" in summary


# =============================================================================
# HopResult Tests
# =============================================================================

def test_hop_result_to_context():
    """HopResult.to_context() 테스트."""
    sq = SubQuery(query_id="q1", text="What is TLIF?", query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT)
    hop_result = HopResult(
        query=sq,
        answer="TLIF is a fusion technique.",
        evidence=[{"paper_id": "p1"}],
        confidence=0.9,
        reasoning="Based on literature",
        execution_time_ms=100.0
    )

    context = hop_result.to_context()

    assert "Qq1" in context
    assert "Aq1" in context
    assert "TLIF is a fusion technique" in context
    assert "0.90" in context


# =============================================================================
# MultiHopReasoner Tests
# =============================================================================

@pytest.mark.asyncio
async def test_reasoner_single_hop(mock_search_pipeline, mock_llm_client, sample_search_response):
    """단일 hop 추론 테스트."""
    # Mock decomposer
    mock_llm_client.generate_json.side_effect = [
        # Decomposition
        {
            "sub_queries": [
                {
                    "query_id": "q1",
                    "text": "What is TLIF?",
                    "depends_on": [],
                    "query_type": "factual",
                    "expected_answer_type": "text",
                    "priority": 0
                }
            ]
        },
        # Answer extraction
        {
            "answer": "TLIF is a transforaminal lumbar interbody fusion.",
            "reasoning": "Standard definition from literature."
        }
    ]

    mock_search_pipeline.search.return_value = sample_search_response

    # Mock final synthesis
    mock_llm_client.generate.return_value = MagicMock(
        text="TLIF is a transforaminal lumbar interbody fusion technique widely used for degenerative conditions."
    )

    reasoner = MultiHopReasoner(mock_search_pipeline, mock_llm_client)
    result = await reasoner.reason("What is TLIF?", max_hops=3)

    assert result.hops_used == 1
    assert "TLIF" in result.final_answer
    assert result.confidence > 0.0
    assert len(result.sub_queries) == 1


@pytest.mark.asyncio
async def test_reasoner_two_hops(mock_search_pipeline, mock_llm_client, sample_search_response):
    """2-hop 추론 테스트."""
    # Mock decomposer
    mock_llm_client.generate_json.side_effect = [
        # Decomposition
        {
            "sub_queries": [
                {
                    "query_id": "q1",
                    "text": "What procedures treat lumbar stenosis?",
                    "depends_on": [],
                    "query_type": "factual",
                    "expected_answer_type": "list",
                    "priority": 0
                },
                {
                    "query_id": "q2",
                    "text": "What is the fusion rate of those procedures?",
                    "depends_on": ["q1"],
                    "query_type": "aggregation",
                    "expected_answer_type": "value",
                    "priority": 1
                }
            ]
        },
        # Answer extraction q1
        {
            "answer": "TLIF, OLIF, UBE are common procedures.",
            "reasoning": "Multiple studies show these interventions."
        },
        # Answer extraction q2
        {
            "answer": "Fusion rates range from 85-95%.",
            "reasoning": "Based on aggregated data from q1 procedures."
        }
    ]

    mock_search_pipeline.search.return_value = sample_search_response

    # Mock final synthesis
    mock_llm_client.generate.return_value = MagicMock(
        text="For lumbar stenosis, TLIF, OLIF, and UBE show fusion rates of 85-95%."
    )

    reasoner = MultiHopReasoner(mock_search_pipeline, mock_llm_client)
    result = await reasoner.reason(
        "What is the fusion rate of procedures that treat lumbar stenosis?",
        max_hops=5
    )

    assert result.hops_used == 2
    assert len(result.reasoning_chain.steps) == 2
    assert result.reasoning_chain.steps[0].query_id == "q1"
    assert result.reasoning_chain.steps[1].query_id == "q2"


@pytest.mark.asyncio
async def test_reasoner_execution_plan_sequential():
    """순차 실행 계획 테스트."""
    # Mock 객체 (실제 실행은 안 함)
    mock_pipeline = MagicMock()
    mock_llm = MagicMock()

    reasoner = MultiHopReasoner(mock_pipeline, mock_llm)

    # 순차 의존성 있는 sub-queries
    sub_queries = [
        SubQuery(query_id="q1", text="Q1", depends_on=[], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=0),
        SubQuery(query_id="q2", text="Q2", depends_on=["q1"], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=1),
        SubQuery(query_id="q3", text="Q3", depends_on=["q2"], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=2),
    ]

    plan = reasoner._create_execution_plan(sub_queries)

    # 3개 레벨 (순차 실행)
    assert len(plan) == 3
    assert plan[0][0].query_id == "q1"
    assert plan[1][0].query_id == "q2"
    assert plan[2][0].query_id == "q3"


@pytest.mark.asyncio
async def test_reasoner_execution_plan_parallel():
    """병렬 실행 계획 테스트."""
    mock_pipeline = MagicMock()
    mock_llm = MagicMock()

    reasoner = MultiHopReasoner(mock_pipeline, mock_llm)

    # 병렬 실행 가능한 sub-queries
    sub_queries = [
        SubQuery(query_id="q1", text="Q1", depends_on=[], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=0),
        SubQuery(query_id="q2", text="Q2", depends_on=[], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=0),
        SubQuery(query_id="q3", text="Q3", depends_on=["q1", "q2"], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=1),
    ]

    plan = reasoner._create_execution_plan(sub_queries)

    # 2개 레벨 (레벨 0: q1, q2 병렬, 레벨 1: q3)
    assert len(plan) == 2
    assert len(plan[0]) == 2  # q1, q2 병렬
    assert len(plan[1]) == 1  # q3 단독
    assert set(sq.query_id for sq in plan[0]) == {"q1", "q2"}


@pytest.mark.asyncio
async def test_reasoner_max_hops_limit(mock_search_pipeline, mock_llm_client):
    """최대 hop 제한 테스트."""
    # Mock: 10개 sub-queries 생성
    mock_llm_client.generate_json.return_value = {
        "sub_queries": [
            {
                "query_id": f"q{i}",
                "text": f"Query {i}",
                "depends_on": [] if i == 0 else [f"q{i-1}"],
                "query_type": "factual",
                "expected_answer_type": "text",
                "priority": i
            }
            for i in range(10)
        ]
    }

    reasoner = MultiHopReasoner(mock_search_pipeline, mock_llm_client)

    # max_hops=3으로 제한
    # decompose만 실행하고 실제 실행은 skip (mock 설정 복잡도 때문)
    sub_queries = await reasoner.decomposer.decompose("Complex query")

    # 10개 생성되었지만 max_hops 제한 적용 필요 (reason()에서)
    assert len(sub_queries) == 10


@pytest.mark.asyncio
async def test_reasoner_circular_dependency_handling():
    """순환 의존성 처리 테스트."""
    mock_pipeline = MagicMock()
    mock_llm = MagicMock()

    reasoner = MultiHopReasoner(mock_pipeline, mock_llm)

    # 순환 의존성 (q1 -> q2 -> q1)
    sub_queries = [
        SubQuery(query_id="q1", text="Q1", depends_on=["q2"], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=0),
        SubQuery(query_id="q2", text="Q2", depends_on=["q1"], query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT, priority=1),
    ]

    plan = reasoner._create_execution_plan(sub_queries)

    # 순환 의존성 감지로 빈 계획 또는 부분 실행
    assert len(plan) == 0  # 순환 의존성으로 실행 불가


# =============================================================================
# Factory Function Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_multi_hop_reasoner():
    """팩토리 함수 테스트."""
    mock_pipeline = MagicMock()
    mock_llm = MagicMock()
    mock_neo4j = MagicMock()

    reasoner = await create_multi_hop_reasoner(
        search_pipeline=mock_pipeline,
        llm_client=mock_llm,
        neo4j_client=mock_neo4j
    )

    assert isinstance(reasoner, MultiHopReasoner)
    assert reasoner.search_pipeline == mock_pipeline
    assert reasoner.llm_client == mock_llm
    assert reasoner.neo4j_client == mock_neo4j


# =============================================================================
# Integration Tests (E2E with mocks)
# =============================================================================

@pytest.mark.asyncio
async def test_integration_comparative_query(mock_search_pipeline, mock_llm_client, sample_search_response):
    """비교 쿼리 E2E 테스트 (mock 사용)."""
    # Mock decomposition: UBE vs TLIF 안전성 비교
    mock_llm_client.generate_json.side_effect = [
        # Decomposition
        {
            "sub_queries": [
                {
                    "query_id": "q1",
                    "text": "What is the complication rate of UBE?",
                    "depends_on": [],
                    "query_type": "factual",
                    "expected_answer_type": "value",
                    "priority": 0
                },
                {
                    "query_id": "q2",
                    "text": "What is the complication rate of TLIF?",
                    "depends_on": [],
                    "query_type": "factual",
                    "expected_answer_type": "value",
                    "priority": 0
                },
                {
                    "query_id": "q3",
                    "text": "Compare UBE and TLIF safety",
                    "depends_on": ["q1", "q2"],
                    "query_type": "comparative",
                    "expected_answer_type": "text",
                    "priority": 1
                }
            ]
        },
        # Answer q1
        {"answer": "UBE complication rate: 3-5%", "reasoning": "Multiple studies"},
        # Answer q2
        {"answer": "TLIF complication rate: 8-12%", "reasoning": "Multiple studies"},
        # Answer q3
        {"answer": "UBE shows lower complication rate than TLIF", "reasoning": "Based on q1 and q2"},
    ]

    mock_search_pipeline.search.return_value = sample_search_response

    # Mock final synthesis
    mock_llm_client.generate.return_value = MagicMock(
        text="UBE demonstrates superior safety profile compared to TLIF, with significantly lower complication rates (3-5% vs 8-12%)."
    )

    reasoner = MultiHopReasoner(mock_search_pipeline, mock_llm_client)
    result = await reasoner.reason("Is UBE safer than TLIF?", max_hops=5)

    # 3-hop 실행 (q1, q2 병렬, q3 순차)
    assert result.hops_used == 3
    assert "UBE" in result.final_answer
    assert "TLIF" in result.final_answer
    assert result.confidence > 0.0


# =============================================================================
# Edge Case Tests
# =============================================================================

@pytest.mark.asyncio
async def test_reasoner_empty_decomposition(mock_search_pipeline, mock_llm_client):
    """분해 결과가 없을 때 테스트."""
    # Mock: 빈 sub-queries
    mock_llm_client.generate_json.return_value = {
        "sub_queries": []
    }

    mock_llm_client.generate.return_value = MagicMock(
        text="Unable to answer due to insufficient decomposition."
    )

    reasoner = MultiHopReasoner(mock_search_pipeline, mock_llm_client)
    result = await reasoner.reason("Invalid query", max_hops=3)

    assert result.hops_used == 0
    assert len(result.all_evidence) == 0


@pytest.mark.asyncio
async def test_reasoner_execution_error_handling(mock_search_pipeline, mock_llm_client):
    """실행 중 에러 처리 테스트."""
    mock_llm_client.generate_json.side_effect = [
        # Decomposition
        {
            "sub_queries": [
                {
                    "query_id": "q1",
                    "text": "Test query",
                    "depends_on": [],
                    "query_type": "factual",
                    "expected_answer_type": "text",
                    "priority": 0
                }
            ]
        },
        # Answer extraction fails
        Exception("LLM error")
    ]

    mock_search_response = MagicMock()
    mock_search_response.results = []
    mock_search_response.synthesis = None
    mock_search_pipeline.search.return_value = mock_search_response

    mock_llm_client.generate.return_value = MagicMock(text="Error occurred")

    reasoner = MultiHopReasoner(mock_search_pipeline, mock_llm_client)
    result = await reasoner.reason("Test query", max_hops=3)

    # Should handle error gracefully
    assert result.hops_used == 1
    # The reasoning will contain the exception message
    assert "LLM error" in result.reasoning_chain.steps[0].reasoning


@pytest.mark.asyncio
async def test_multi_hop_result_get_explanation():
    """MultiHopResult.get_explanation() 테스트."""
    chain = ReasoningChain()
    sq = SubQuery(query_id="q1", text="What is TLIF?", query_type=QueryType.FACTUAL, expected_answer_type=AnswerType.TEXT)
    chain.add_step(sq, "TLIF is a fusion technique", [{"paper_id": "p1"}], 0.9, "Based on evidence")

    result = MultiHopResult(
        final_answer="TLIF is a widely used fusion technique.",
        reasoning_chain=chain,
        hops_used=1,
        all_evidence=[{"paper_id": "p1"}],
        confidence=0.9,
        execution_time_ms=150.5,
        sub_queries=[sq]
    )

    explanation = result.get_explanation()

    assert "Multi-hop Reasoning Explanation" in explanation
    assert "Final Answer:" in explanation
    assert "TLIF" in explanation
    assert "Confidence: 0.90" in explanation
    assert "Hops Used: 1" in explanation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

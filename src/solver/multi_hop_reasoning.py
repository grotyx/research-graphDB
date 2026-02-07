"""Multi-hop Reasoning for Spine GraphRAG.

복잡한 질문을 하위 질문으로 분해하고, 각 단계에서 검색 및 추론을 수행하여
최종 답변을 도출하는 다단계 추론 시스템.

주요 기능:
- 복잡한 쿼리를 하위 질문(sub-query)으로 분해
- 하위 질문 간 의존성 관리 (DAG)
- 각 hop에서 적절한 검색 전략 사용
- 병렬 및 순차 실행 지원
- 전체 추론 체인 추적 및 설명 가능성

사용 예:
    >>> reasoner = MultiHopReasoner(pipeline, llm_client)
    >>> result = await reasoner.reason(
    ...     "What is the fusion rate of procedures that treat lumbar stenosis?"
    ... )
    >>> print(result.final_answer)
    >>> print(f"Used {result.hops_used} hops")
    >>> for step in result.reasoning_chain.steps:
    ...     print(f"Hop {step.hop_number}: {step.query} -> {step.answer}")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Try to import dependencies
try:
    from .unified_pipeline import UnifiedSearchPipeline, SearchOptions, SearchResponse
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    UnifiedSearchPipeline = None
    SearchOptions = None
    SearchResponse = None

from typing import Union
try:
    from ..llm import LLMClient, LLMResponse, ClaudeClient, GeminiClient
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    LLMClient = None
    LLMResponse = None
    ClaudeClient = None
    GeminiClient = None

try:
    from ..graph.neo4j_client import Neo4jClient
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    Neo4jClient = None

# Logging
try:
    from ..core.logging_config import MedicalRAGLogger
    logger = MedicalRAGLogger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================

class QueryType(Enum):
    """하위 질문 유형."""
    FACTUAL = "factual"           # 단순 사실 조회 (What is X?)
    COMPARATIVE = "comparative"   # 비교 (X vs Y)
    RELATIONAL = "relational"     # 관계 탐색 (X causes Y?)
    AGGREGATION = "aggregation"   # 집계 (Average of X)
    FILTER = "filter"             # 필터링 (X that have Y)


class AnswerType(Enum):
    """예상 답변 유형."""
    ENTITY = "entity"             # 개체 (수술법, 질환 등)
    VALUE = "value"               # 수치 값
    BOOLEAN = "boolean"           # Yes/No
    LIST = "list"                 # 목록
    TEXT = "text"                 # 자연어 텍스트


@dataclass
class SubQuery:
    """하위 질문.

    Attributes:
        query_id: 고유 ID (예: "q1", "q2")
        text: 질문 텍스트
        depends_on: 의존하는 하위 질문 ID 리스트
        query_type: 질문 유형
        expected_answer_type: 예상 답변 유형
        priority: 우선순위 (낮을수록 먼저 실행)
    """
    query_id: str
    text: str
    depends_on: list[str] = field(default_factory=list)
    query_type: QueryType = QueryType.FACTUAL
    expected_answer_type: AnswerType = AnswerType.TEXT
    priority: int = 0

    def is_independent(self) -> bool:
        """독립 실행 가능 여부."""
        return len(self.depends_on) == 0


@dataclass
class HopResult:
    """단일 hop 실행 결과.

    Attributes:
        query: 실행한 하위 질문
        answer: 답변 텍스트
        evidence: 근거 문서/데이터
        confidence: 신뢰도 (0.0-1.0)
        reasoning: 추론 과정 설명
        search_response: 검색 응답 (선택적)
        execution_time_ms: 실행 시간
    """
    query: SubQuery
    answer: str
    evidence: list[dict]
    confidence: float
    reasoning: str
    search_response: Optional[SearchResponse] = None
    execution_time_ms: float = 0.0

    def to_context(self) -> str:
        """다음 hop을 위한 컨텍스트 생성.

        Returns:
            이전 결과를 요약한 컨텍스트 문자열
        """
        return (
            f"Q{self.query.query_id}: {self.query.text}\n"
            f"A{self.query.query_id}: {self.answer}\n"
            f"Confidence: {self.confidence:.2f}\n"
        )


@dataclass
class ReasoningStep:
    """추론 단계.

    Attributes:
        hop_number: hop 번호 (1부터 시작)
        query_id: 하위 질문 ID
        query: 질문 텍스트
        answer: 답변
        confidence: 신뢰도
        evidence_count: 근거 개수
        reasoning: 추론 설명
    """
    hop_number: int
    query_id: str
    query: str
    answer: str
    confidence: float
    evidence_count: int
    reasoning: str


@dataclass
class ReasoningChain:
    """추론 체인 (전체 경로 추적).

    Attributes:
        steps: 추론 단계 리스트
        total_hops: 총 hop 수
        avg_confidence: 평균 신뢰도
    """
    steps: list[ReasoningStep] = field(default_factory=list)

    @property
    def total_hops(self) -> int:
        """총 hop 수."""
        return len(self.steps)

    @property
    def avg_confidence(self) -> float:
        """평균 신뢰도."""
        if not self.steps:
            return 0.0
        return sum(s.confidence for s in self.steps) / len(self.steps)

    def add_step(
        self,
        query: SubQuery,
        answer: str,
        evidence: list[dict],
        confidence: float,
        reasoning: str
    ) -> None:
        """추론 단계 추가.

        Args:
            query: 하위 질문
            answer: 답변
            evidence: 근거
            confidence: 신뢰도
            reasoning: 추론 설명
        """
        step = ReasoningStep(
            hop_number=len(self.steps) + 1,
            query_id=query.query_id,
            query=query.text,
            answer=answer,
            confidence=confidence,
            evidence_count=len(evidence),
            reasoning=reasoning
        )
        self.steps.append(step)

    def get_summary(self) -> str:
        """체인 요약 생성.

        Returns:
            추론 과정 요약 문자열
        """
        lines = [f"Multi-hop Reasoning Chain ({self.total_hops} hops):"]
        for step in self.steps:
            lines.append(
                f"  Hop {step.hop_number} [{step.query_id}]: {step.query}"
            )
            lines.append(f"    -> {step.answer} (conf: {step.confidence:.2f})")
        return "\n".join(lines)


@dataclass
class MultiHopResult:
    """다단계 추론 최종 결과.

    Attributes:
        final_answer: 최종 답변
        reasoning_chain: 추론 체인
        hops_used: 사용한 hop 수
        all_evidence: 모든 근거 취합
        confidence: 전체 신뢰도
        execution_time_ms: 총 실행 시간
        sub_queries: 분해된 하위 질문 리스트
    """
    final_answer: str
    reasoning_chain: ReasoningChain
    hops_used: int
    all_evidence: list[dict]
    confidence: float
    execution_time_ms: float
    sub_queries: list[SubQuery] = field(default_factory=list)

    def get_explanation(self) -> str:
        """전체 추론 과정 설명 생성.

        Returns:
            사람이 읽을 수 있는 설명
        """
        lines = [
            "=== Multi-hop Reasoning Explanation ===",
            "",
            f"Final Answer: {self.final_answer}",
            f"Confidence: {self.confidence:.2f}",
            f"Hops Used: {self.hops_used}",
            f"Total Evidence: {len(self.all_evidence)} documents",
            "",
            "Reasoning Process:",
            self.reasoning_chain.get_summary(),
        ]
        return "\n".join(lines)


# =============================================================================
# Query Decomposition
# =============================================================================

class QueryDecomposer:
    """복잡한 쿼리를 하위 질문으로 분해.

    LLM을 사용하여 복잡한 질문을 여러 단계의 하위 질문으로 분해하고,
    각 하위 질문 간 의존성을 파악하여 실행 DAG를 생성.

    사용 예:
        >>> decomposer = QueryDecomposer(llm_client)
        >>> sub_queries = await decomposer.decompose(
        ...     "What is the fusion rate of procedures that treat lumbar stenosis?"
        ... )
        >>> # sub_queries:
        >>> # q1: "What procedures treat lumbar stenosis?" (no dependencies)
        >>> # q2: "What is the fusion rate of [procedures from q1]?" (depends on q1)
    """

    def __init__(self, llm_client: Union[LLMClient, ClaudeClient, GeminiClient]):
        """초기화.

        Args:
            llm_client: LLM 클라이언트 (Claude 또는 Gemini)
        """
        if not LLM_AVAILABLE:
            raise ImportError("LLMClient not available. Install anthropic or google-genai.")

        self.llm_client = llm_client

    async def decompose(self, complex_query: str) -> list[SubQuery]:
        """쿼리 분해.

        Args:
            complex_query: 복잡한 질문

        Returns:
            SubQuery 객체 리스트 (실행 순서대로 정렬)
        """
        # LLM에게 분해 요청
        prompt = self._build_decompose_prompt(complex_query)
        schema = self._get_decompose_schema()

        result = await self.llm_client.generate_json(
            prompt=prompt,
            schema=schema,
            system="You are a query decomposition expert for medical literature search.",
            use_cache=True
        )

        # SubQuery 객체 생성
        sub_queries = []
        for sq_data in result.get("sub_queries", []):
            sub_query = SubQuery(
                query_id=sq_data["query_id"],
                text=sq_data["text"],
                depends_on=sq_data.get("depends_on", []),
                query_type=QueryType(sq_data.get("query_type", "factual")),
                expected_answer_type=AnswerType(sq_data.get("expected_answer_type", "text")),
                priority=sq_data.get("priority", 0)
            )
            sub_queries.append(sub_query)

        # 우선순위와 의존성 기준 정렬
        sub_queries.sort(key=lambda sq: (sq.priority, len(sq.depends_on)))

        logger.info(f"Decomposed query into {len(sub_queries)} sub-queries")
        return sub_queries

    def _build_decompose_prompt(self, query: str) -> str:
        """분해 프롬프트 생성."""
        return f"""You are analyzing a complex medical research query in the spine surgery domain.
Break down the following complex query into a sequence of simpler sub-queries.

Complex Query: "{query}"

Guidelines:
1. Identify logical steps needed to answer the query
2. Create 1-5 sub-queries (avoid over-decomposition)
3. Mark dependencies: which sub-queries need results from previous ones
4. Assign priority: lower numbers execute first
5. Classify each sub-query type and expected answer type

Domain Context:
- Spine surgery interventions (UBE, TLIF, OLIF, etc.)
- Outcomes (VAS, ODI, fusion rate, complications, etc.)
- Pathologies (lumbar stenosis, spondylolisthesis, etc.)

Example 1:
Query: "What is the fusion rate of procedures that treat lumbar stenosis?"
Sub-queries:
- q1: "What procedures are used to treat lumbar stenosis?" (independent, priority=0)
- q2: "What is the fusion rate of [procedures from q1]?" (depends on q1, priority=1)

Example 2:
Query: "Is UBE safer than TLIF for elderly patients?"
Sub-queries:
- q1: "What are the complication rates of UBE in elderly patients?" (independent, priority=0)
- q2: "What are the complication rates of TLIF in elderly patients?" (independent, priority=0)
- q3: "Compare safety between UBE and TLIF based on q1 and q2" (depends on q1, q2, priority=1)

Now decompose the query: "{query}"
"""

    def _get_decompose_schema(self) -> dict:
        """JSON 스키마 반환."""
        return {
            "type": "OBJECT",
            "properties": {
                "sub_queries": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "query_id": {
                                "type": "STRING",
                                "description": "Unique ID like 'q1', 'q2', etc."
                            },
                            "text": {
                                "type": "STRING",
                                "description": "Sub-query text"
                            },
                            "depends_on": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                                "description": "List of query_ids this depends on"
                            },
                            "query_type": {
                                "type": "STRING",
                                "enum": ["factual", "comparative", "relational", "aggregation", "filter"],
                                "description": "Type of query"
                            },
                            "expected_answer_type": {
                                "type": "STRING",
                                "enum": ["entity", "value", "boolean", "list", "text"],
                                "description": "Expected answer type"
                            },
                            "priority": {
                                "type": "INTEGER",
                                "description": "Execution priority (0=first)"
                            }
                        },
                        "required": ["query_id", "text", "query_type", "expected_answer_type"]
                    }
                }
            },
            "required": ["sub_queries"]
        }


# =============================================================================
# Hop Executor
# =============================================================================

class HopExecutor:
    """단일 hop 실행.

    하위 질문에 대해 적절한 검색 전략을 선택하고 실행하여
    답변과 근거를 추출.
    """

    def __init__(
        self,
        search_pipeline: UnifiedSearchPipeline,
        llm_client: Union[LLMClient, ClaudeClient, GeminiClient]
    ):
        """초기화.

        Args:
            search_pipeline: 통합 검색 파이프라인
            llm_client: LLM 클라이언트 (Claude 또는 Gemini)
        """
        if not PIPELINE_AVAILABLE:
            raise ImportError("UnifiedSearchPipeline not available.")

        self.search_pipeline = search_pipeline
        self.llm_client = llm_client

    async def execute_hop(
        self,
        sub_query: SubQuery,
        context: str = ""
    ) -> HopResult:
        """Hop 실행.

        Args:
            sub_query: 하위 질문
            context: 이전 hop 결과 (컨텍스트)

        Returns:
            HopResult 객체
        """
        start_time = time.time()

        # 1. 컨텍스트 반영한 검색 쿼리 생성
        search_query = self._build_search_query(sub_query, context)

        # 2. 검색 수행
        search_options = self._get_search_options(sub_query)
        search_response = await self.search_pipeline.search(
            query=search_query,
            options=search_options
        )

        # 3. 답변 추출 (LLM 사용)
        answer, reasoning = await self._extract_answer(
            sub_query, search_response, context
        )

        # 4. 신뢰도 계산
        confidence = self._calculate_confidence(sub_query, search_response)

        # 5. 근거 수집
        evidence = self._collect_evidence(search_response)

        execution_time = (time.time() - start_time) * 1000

        logger.info(
            f"Hop executed: {sub_query.query_id} "
            f"({len(evidence)} evidence, conf={confidence:.2f}, {execution_time:.1f}ms)"
        )

        return HopResult(
            query=sub_query,
            answer=answer,
            evidence=evidence,
            confidence=confidence,
            reasoning=reasoning,
            search_response=search_response,
            execution_time_ms=execution_time
        )

    def _build_search_query(self, sub_query: SubQuery, context: str) -> str:
        """검색 쿼리 생성.

        Args:
            sub_query: 하위 질문
            context: 이전 결과 컨텍스트

        Returns:
            검색 쿼리 문자열
        """
        # 컨텍스트가 있으면 결합
        if context:
            return f"{context}\n\nCurrent Question: {sub_query.text}"
        return sub_query.text

    def _get_search_options(self, sub_query: SubQuery) -> SearchOptions:
        """검색 옵션 설정.

        Args:
            sub_query: 하위 질문

        Returns:
            SearchOptions 객체
        """
        # 질문 유형에 따라 옵션 조정
        if sub_query.query_type == QueryType.COMPARATIVE:
            return SearchOptions(
                top_k=15,
                include_synthesis=True,
                detect_conflicts=True,
                enable_adaptive=True
            )
        elif sub_query.query_type == QueryType.AGGREGATION:
            return SearchOptions(
                top_k=20,
                include_synthesis=True,
                detect_conflicts=False,
                enable_adaptive=True
            )
        else:
            return SearchOptions(
                top_k=10,
                include_synthesis=False,
                detect_conflicts=False,
                enable_adaptive=True
            )

    async def _extract_answer(
        self,
        sub_query: SubQuery,
        search_response: SearchResponse,
        context: str
    ) -> tuple[str, str]:
        """답변 추출.

        Args:
            sub_query: 하위 질문
            search_response: 검색 응답
            context: 이전 컨텍스트

        Returns:
            (답변, 추론 설명) 튜플
        """
        # 검색 결과 요약
        evidence_summary = self._summarize_evidence(search_response)

        # LLM에게 답변 요청
        prompt = f"""Based on the search results, answer the following question concisely.

Question: {sub_query.text}

{f"Previous Context:\n{context}\n" if context else ""}

Search Results:
{evidence_summary}

Provide:
1. A direct answer (1-3 sentences)
2. Brief reasoning explanation

Expected Answer Type: {sub_query.expected_answer_type.value}
"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "answer": {
                    "type": "STRING",
                    "description": "Direct answer to the question"
                },
                "reasoning": {
                    "type": "STRING",
                    "description": "Reasoning explanation"
                }
            },
            "required": ["answer", "reasoning"]
        }

        result = await self.llm_client.generate_json(
            prompt=prompt,
            schema=schema,
            system="You are a medical literature expert. Provide accurate, evidence-based answers.",
            use_cache=False  # 각 hop은 고유하므로 캐시 비활성화
        )

        return result["answer"], result["reasoning"]

    def _summarize_evidence(self, search_response: SearchResponse) -> str:
        """검색 결과 요약.

        Args:
            search_response: 검색 응답

        Returns:
            요약 문자열
        """
        lines = []
        for i, result in enumerate(search_response.results[:5], 1):
            lines.append(
                f"{i}. {result.title} ({result.publication_year}) - "
                f"Score: {result.final_score:.2f}"
            )
            # 주요 내용 추가 (있으면)
            if hasattr(result, 'summary') and result.summary:
                lines.append(f"   {result.summary[:150]}...")

        return "\n".join(lines) if lines else "No results found."

    def _calculate_confidence(
        self,
        sub_query: SubQuery,
        search_response: SearchResponse
    ) -> float:
        """신뢰도 계산.

        Args:
            sub_query: 하위 질문
            search_response: 검색 응답

        Returns:
            신뢰도 (0.0-1.0)
        """
        # 검색 결과가 없으면 신뢰도 0
        if not search_response.results:
            return 0.0

        # 평균 점수 기반
        avg_score = sum(r.final_score for r in search_response.results[:5]) / min(5, len(search_response.results))

        # Synthesis가 있으면 보정
        if search_response.synthesis:
            strength_boost = {
                "high": 1.2,
                "moderate": 1.0,
                "low": 0.8,
                "insufficient": 0.5
            }.get(search_response.synthesis.strength.value, 1.0)
            avg_score *= strength_boost

        return min(avg_score, 1.0)

    def _collect_evidence(self, search_response: SearchResponse) -> list[dict]:
        """근거 수집.

        Args:
            search_response: 검색 응답

        Returns:
            근거 딕셔너리 리스트
        """
        evidence = []
        for result in search_response.results[:10]:
            evidence.append({
                "paper_id": result.paper_id,
                "title": result.title,
                "year": result.publication_year,
                "score": result.final_score,
                "evidence_level": getattr(result, 'evidence_level', 'unknown')
            })
        return evidence


# =============================================================================
# Multi-hop Reasoner
# =============================================================================

class MultiHopReasoner:
    """다단계 추론 오케스트레이터.

    쿼리 분해 → 의존성 분석 → 순차/병렬 실행 → 결과 종합을 관리.

    사용 예:
        >>> reasoner = MultiHopReasoner(pipeline, llm_client)
        >>> result = await reasoner.reason(
        ...     "What is the fusion rate of procedures that treat lumbar stenosis?",
        ...     max_hops=5
        ... )
    """

    def __init__(
        self,
        search_pipeline: UnifiedSearchPipeline,
        llm_client: Union[LLMClient, ClaudeClient, GeminiClient],
        neo4j_client: Optional[Neo4jClient] = None
    ):
        """초기화.

        Args:
            search_pipeline: 통합 검색 파이프라인
            llm_client: LLM 클라이언트 (Claude 또는 Gemini)
            neo4j_client: Neo4j 클라이언트 (선택적, 그래프 탐색용)
        """
        self.search_pipeline = search_pipeline
        self.llm_client = llm_client
        self.neo4j_client = neo4j_client

        self.decomposer = QueryDecomposer(llm_client)
        self.executor = HopExecutor(search_pipeline, llm_client)

    async def reason(
        self,
        query: str,
        max_hops: int = 5
    ) -> MultiHopResult:
        """다단계 추론 수행.

        Args:
            query: 복잡한 질문
            max_hops: 최대 hop 수

        Returns:
            MultiHopResult 객체
        """
        start_time = time.time()

        logger.info(f"Starting multi-hop reasoning for: {query}")

        # 1. 쿼리 분해
        sub_queries = await self.decomposer.decompose(query)

        # 너무 많은 hop 방지
        if len(sub_queries) > max_hops:
            logger.warning(f"Too many sub-queries ({len(sub_queries)}), limiting to {max_hops}")
            sub_queries = sub_queries[:max_hops]

        # 2. 실행 계획 생성 (DAG)
        execution_plan = self._create_execution_plan(sub_queries)

        # 3. 단계별 실행
        reasoning_chain = ReasoningChain()
        all_evidence = []
        context_accumulator = ""

        for level in execution_plan:
            # 같은 레벨은 병렬 실행 가능
            hop_results = await self._execute_level(level, context_accumulator)

            # 결과를 chain에 추가
            for hop_result in hop_results:
                reasoning_chain.add_step(
                    query=hop_result.query,
                    answer=hop_result.answer,
                    evidence=hop_result.evidence,
                    confidence=hop_result.confidence,
                    reasoning=hop_result.reasoning
                )
                all_evidence.extend(hop_result.evidence)

                # 컨텍스트 누적
                context_accumulator += hop_result.to_context() + "\n"

        # 4. 최종 답변 종합
        final_answer = await self._synthesize_final_answer(
            query, reasoning_chain, context_accumulator
        )

        # 5. 전체 신뢰도 계산
        overall_confidence = reasoning_chain.avg_confidence

        execution_time = (time.time() - start_time) * 1000

        logger.info(
            f"Multi-hop reasoning complete: {reasoning_chain.total_hops} hops, "
            f"confidence={overall_confidence:.2f}, {execution_time:.1f}ms"
        )

        return MultiHopResult(
            final_answer=final_answer,
            reasoning_chain=reasoning_chain,
            hops_used=reasoning_chain.total_hops,
            all_evidence=all_evidence,
            confidence=overall_confidence,
            execution_time_ms=execution_time,
            sub_queries=sub_queries
        )

    def _create_execution_plan(self, sub_queries: list[SubQuery]) -> list[list[SubQuery]]:
        """실행 계획 생성 (DAG 레벨별).

        Args:
            sub_queries: 하위 질문 리스트

        Returns:
            레벨별 하위 질문 리스트 (외부 리스트는 순차, 내부는 병렬)
        """
        # 의존성 기반 레벨 계산
        levels: list[list[SubQuery]] = []
        remaining = sub_queries.copy()
        completed_ids = set()

        while remaining:
            # 현재 실행 가능한 질문 (의존성이 모두 해결된 것)
            current_level = [
                sq for sq in remaining
                if all(dep_id in completed_ids for dep_id in sq.depends_on)
            ]

            if not current_level:
                # 순환 의존성 또는 잘못된 의존성
                logger.error("Circular dependency detected or invalid dependencies")
                break

            levels.append(current_level)
            for sq in current_level:
                completed_ids.add(sq.query_id)
                remaining.remove(sq)

        logger.info(f"Execution plan created: {len(levels)} levels")
        return levels

    async def _execute_level(
        self,
        level: list[SubQuery],
        context: str
    ) -> list[HopResult]:
        """레벨 실행 (병렬).

        Args:
            level: 같은 레벨의 하위 질문 리스트
            context: 누적 컨텍스트

        Returns:
            HopResult 리스트
        """
        logger.info(f"Executing level with {len(level)} sub-queries")

        # 병렬 실행
        tasks = [
            self.executor.execute_hop(sq, context)
            for sq in level
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 에러 처리
        hop_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Hop execution failed for {level[i].query_id}: {result}")
                # 빈 결과 생성
                hop_results.append(HopResult(
                    query=level[i],
                    answer="Error occurred during execution",
                    evidence=[],
                    confidence=0.0,
                    reasoning=str(result),
                    execution_time_ms=0.0
                ))
            else:
                hop_results.append(result)

        return hop_results

    async def _synthesize_final_answer(
        self,
        original_query: str,
        reasoning_chain: ReasoningChain,
        context: str
    ) -> str:
        """최종 답변 종합.

        Args:
            original_query: 원본 질문
            reasoning_chain: 추론 체인
            context: 전체 컨텍스트

        Returns:
            최종 답변 문자열
        """
        prompt = f"""You are synthesizing the final answer to a complex medical question.

Original Question: {original_query}

Reasoning Process:
{context}

Based on the multi-step reasoning above, provide a comprehensive final answer to the original question.
The answer should:
1. Directly address the original question
2. Integrate insights from all reasoning steps
3. Cite evidence levels when relevant
4. Be concise but complete (3-5 sentences)
"""

        response = await self.llm_client.generate(
            prompt=prompt,
            system="You are a medical literature expert providing evidence-based answers.",
            use_cache=False
        )

        return response.text.strip()


# =============================================================================
# Helper Functions
# =============================================================================

async def create_multi_hop_reasoner(
    search_pipeline: UnifiedSearchPipeline,
    llm_client: GeminiClient,
    neo4j_client: Optional[Neo4jClient] = None
) -> MultiHopReasoner:
    """MultiHopReasoner 팩토리 함수.

    Args:
        search_pipeline: 통합 검색 파이프라인
        llm_client: LLM 클라이언트
        neo4j_client: Neo4j 클라이언트 (선택적)

    Returns:
        MultiHopReasoner 인스턴스
    """
    return MultiHopReasoner(search_pipeline, llm_client, neo4j_client)


# =============================================================================
# Example Usage
# =============================================================================

async def example_usage():
    """사용 예시."""
    from ..storage.vector_db import TieredVectorDB
    from ..llm import LLMClient, LLMConfig

    # 컴포넌트 초기화
    vector_db = TieredVectorDB(persist_directory="./data/chromadb")
    llm_client = LLMClient(config=LLMConfig())  # Claude 또는 Gemini (환경변수 기반)

    # Neo4j 클라이언트 (선택적)
    neo4j_client = None
    if NEO4J_AVAILABLE:
        from ..graph.neo4j_client import Neo4jClient
        neo4j_client = Neo4jClient()
        await neo4j_client.connect()

    # Pipeline 생성
    from .unified_pipeline import create_pipeline
    pipeline = create_pipeline(neo4j_client, vector_db)

    # Multi-hop Reasoner 생성
    reasoner = MultiHopReasoner(pipeline, llm_client, neo4j_client)

    # 복잡한 질문
    query = "What is the fusion rate of procedures that treat lumbar stenosis?"

    # 추론 수행
    result = await reasoner.reason(query, max_hops=5)

    # 결과 출력
    print(result.get_explanation())
    print("\n" + "="*60)
    print(f"Final Answer: {result.final_answer}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Evidence Documents: {len(result.all_evidence)}")

    # 정리
    if neo4j_client:
        await neo4j_client.close()


if __name__ == "__main__":
    asyncio.run(example_usage())

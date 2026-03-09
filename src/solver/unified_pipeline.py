"""Unified Search Pipeline for Spine GraphRAG.

통합 검색 파이프라인: 모든 검색 및 랭킹 모듈을 오케스트레이션.

이 모듈은 다음 컴포넌트들을 통합:
- AdaptiveHybridRanker: 쿼리 유형 기반 동적 가중치 조정
- HybridRanker: Graph + Vector 통합 검색
- EvidenceSynthesizer: GRADE 기반 근거 종합
- ConflictDetector: 상충 연구 탐지
- DirectionDeterminer: 결과 방향 해석
- GraphContextExpander: IS_A 계층 기반 쿼리 컨텍스트 확장 (v4.2)
- QueryPatternRouter: 쿼리 패턴 분류 및 Cypher 라우팅 (v4.2)

사용 예:
    >>> # 기본 설정으로 파이프라인 생성
    >>> pipeline = create_pipeline(neo4j_client)
    >>>
    >>> # 검색 수행
    >>> response = await pipeline.search(
    ...     query="TLIF vs OLIF for lumbar stenosis",
    ...     options=SearchOptions(top_k=10, include_synthesis=True)
    ... )
    >>>
    >>> # 결과 분석
    >>> print(f"Query type: {response.query_analysis.query_type}")
    >>> print(f"Found {len(response.results)} results")
    >>> if response.synthesis:
    ...     print(f"Evidence strength: {response.synthesis.strength}")
    >>> if response.conflicts:
    ...     print(f"Found {len(response.conflicts)} conflicts")
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .adaptive_ranker import (
    AdaptiveHybridRanker,
    QueryClassifier,
    QueryType,
    RankedResult
)
from .hybrid_ranker import HybridRanker, HybridResult
from .evidence_synthesizer import (
    EvidenceSynthesizer,
    SynthesisResult,
    EvidenceStrength
)
from .conflict_detector import ConflictDetector, ConflictResult, ConflictSeverity
from .direction_determiner import DirectionDeterminer, OutcomeDirection

from core.exceptions import ValidationError, ProcessingError, ErrorCode

# v4.2: Import GraphContextExpander for IS_A hierarchy expansion
try:
    from .graph_context_expander import GraphContextExpander, ExpandedContext
    CONTEXT_EXPANDER_AVAILABLE = True
except ImportError:
    CONTEXT_EXPANDER_AVAILABLE = False
    GraphContextExpander = None
    ExpandedContext = None

# SNOMED lookup for ontology-aware search
try:
    from ontology.spine_snomed_mappings import (
        get_snomed_for_intervention,
        get_snomed_for_pathology,
        get_snomed_for_outcome,
        get_snomed_for_anatomy,
    )
    SNOMED_LOOKUP_AVAILABLE = True
except ImportError:
    SNOMED_LOOKUP_AVAILABLE = False

# v4.2: Import QueryPatternRouter for advanced query classification
try:
    from ..orchestrator.query_pattern_router import (
        QueryPatternRouter,
        QueryPattern,
        ParsedQuery
    )
    PATTERN_ROUTER_AVAILABLE = True
except ImportError:
    PATTERN_ROUTER_AVAILABLE = False
    QueryPatternRouter = None
    QueryPattern = None
    ParsedQuery = None

# Try to import Neo4j
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
# Configuration Classes
# =============================================================================

@dataclass
class SearchOptions:
    """검색 옵션 설정.

    Attributes:
        top_k: 반환할 최대 결과 수 (기본값: 10)
        include_synthesis: 근거 종합 포함 여부 (기본값: True)
        detect_conflicts: 충돌 탐지 수행 여부 (기본값: True)
        min_evidence_level: 최소 근거 수준 (기본값: "3" = Case-control)
        graph_weight: Graph 검색 가중치 (기본값: None = 자동 조정)
        vector_weight: Vector 검색 가중치 (기본값: None = 자동 조정)
        enable_adaptive: Adaptive Ranker 사용 여부 (기본값: True)
        synthesis_min_papers: 종합 분석 최소 논문 수 (기본값: 2)
        conflict_min_severity: 충돌 최소 심각도 (기본값: MEDIUM)
        enable_context_expansion: IS_A 계층 확장 사용 여부 (기본값: True, v4.2)
        expansion_direction: 계층 확장 방향 ("up", "down", "both") (기본값: "both")
        expansion_max_depth: 계층 확장 최대 깊이 (기본값: 2)
        use_pattern_router: 패턴 라우터 사용 여부 (기본값: True, v4.2)
    """
    top_k: int = 10
    include_synthesis: bool = True
    detect_conflicts: bool = True
    min_evidence_level: str = "3"
    graph_weight: Optional[float] = None
    vector_weight: Optional[float] = None
    enable_adaptive: bool = True
    synthesis_min_papers: int = 2
    conflict_min_severity: str = "medium"
    # v4.2: Context expansion options
    enable_context_expansion: bool = True
    expansion_direction: str = "both"  # "up", "down", "both"
    expansion_max_depth: int = 2
    use_pattern_router: bool = True


@dataclass
class QueryAnalysis:
    """쿼리 분석 결과.

    Attributes:
        query_type: 쿼리 유형 (FACTUAL, COMPARATIVE, etc.)
        confidence: 분류 신뢰도 (0.0-1.0)
        detected_intervention: 탐지된 수술법 (선택적)
        detected_outcome: 탐지된 결과 변수 (선택적)
        suggested_weights: 권장 가중치 (graph, vector)
        query_pattern: QueryPattern (v4.2) - 고급 패턴 분류 결과
        extracted_entities: 추출된 엔티티 딕셔너리 (v4.2)
        expanded_context: IS_A 계층 확장 컨텍스트 (v4.2)
    """
    query_type: QueryType
    confidence: float
    detected_intervention: Optional[str] = None
    detected_outcome: Optional[str] = None
    suggested_weights: dict = field(default_factory=dict)
    # v4.2: Advanced pattern classification
    query_pattern: Optional[str] = None  # QueryPattern.value (for serialization)
    extracted_entities: dict = field(default_factory=dict)
    expanded_context: dict = field(default_factory=dict)


@dataclass
class SearchResponse:
    """통합 검색 응답.

    Attributes:
        results: 랭킹된 검색 결과 리스트
        synthesis: 근거 종합 결과 (선택적)
        conflicts: 충돌 탐지 결과 리스트 (선택적)
        query_analysis: 쿼리 분석 정보
        execution_time_ms: 총 실행 시간 (밀리초)
        graph_time_ms: Graph 검색 시간 (선택적)
        vector_time_ms: Vector 검색 시간 (선택적)
        synthesis_time_ms: 근거 종합 시간 (선택적)
        conflict_time_ms: 충돌 탐지 시간 (선택적)
    """
    results: list[RankedResult]
    synthesis: Optional[SynthesisResult]
    conflicts: Optional[list[ConflictResult]]
    query_analysis: QueryAnalysis
    execution_time_ms: float

    # Detailed timing
    graph_time_ms: Optional[float] = None
    vector_time_ms: Optional[float] = None
    synthesis_time_ms: Optional[float] = None
    conflict_time_ms: Optional[float] = None

    def get_summary(self) -> str:
        """검색 결과 요약 생성.

        Returns:
            사람이 읽을 수 있는 요약 문자열
        """
        lines = [
            f"Query Type: {self.query_analysis.query_type.value}",
            f"Results: {len(self.results)} documents",
            f"Execution Time: {self.execution_time_ms:.1f}ms",
        ]

        if self.synthesis:
            lines.append(
                f"Evidence Synthesis: {self.synthesis.direction} "
                f"({self.synthesis.strength.value}, GRADE {self.synthesis.grade_rating})"
            )

        if self.conflicts:
            lines.append(f"Conflicts Detected: {len(self.conflicts)}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """딕셔너리 변환 (JSON 직렬화용).

        Returns:
            딕셔너리 표현
        """
        return {
            "results": [
                {
                    "paper_id": r.paper_id,
                    "title": r.title,
                    "final_score": r.final_score,
                    "graph_score": r.graph_score,
                    "vector_score": r.vector_score,
                    "query_type": r.query_type.value,
                }
                for r in self.results
            ],
            "synthesis": self.synthesis.to_dict() if self.synthesis else None,
            "conflicts": [c.intervention + " → " + c.outcome for c in (self.conflicts or [])],
            "query_analysis": {
                "query_type": self.query_analysis.query_type.value,
                "confidence": self.query_analysis.confidence,
            },
            "execution_time_ms": self.execution_time_ms,
        }


# =============================================================================
# Unified Search Pipeline
# =============================================================================

class UnifiedSearchPipeline:
    """통합 검색 파이프라인.

    모든 검색 및 랭킹 모듈을 오케스트레이션하여 종합적인 검색 결과 제공.

    주요 기능:
        1. Adaptive Query Classification
        2. Hybrid Graph + Vector Search
        3. GRADE-based Evidence Synthesis
        4. Conflict Detection
        5. Outcome Direction Interpretation

    사용 예:
        >>> pipeline = UnifiedSearchPipeline(neo4j_client)
        >>> response = await pipeline.search(
        ...     query="What is the fusion rate of TLIF?",
        ...     options=SearchOptions(top_k=10)
        ... )
        >>> print(response.get_summary())
    """

    def __init__(
        self,
        neo4j_client: Optional["Neo4jClient"] = None,
        config: Optional[dict] = None
    ):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트 (선택적)
            config: 설정 딕셔너리 (선택적)
        """
        self.neo4j_client = neo4j_client
        self.config = config or {}

        # Component initialization
        self.query_classifier = QueryClassifier()
        self.adaptive_ranker = AdaptiveHybridRanker(self.query_classifier)
        self.direction_determiner = DirectionDeterminer()

        # v4.2: Pattern router (independent of Neo4j)
        if PATTERN_ROUTER_AVAILABLE and QueryPatternRouter:
            self.pattern_router = QueryPatternRouter()
            logger.info("QueryPatternRouter initialized")
        else:
            self.pattern_router = None
            logger.debug("QueryPatternRouter not available")

        # Neo4j-dependent components
        if neo4j_client:
            self.hybrid_ranker = HybridRanker(neo4j_client=neo4j_client)
            self.evidence_synthesizer = EvidenceSynthesizer(neo4j_client)
            self.conflict_detector = ConflictDetector(neo4j_client)

            # v4.2: GraphContextExpander (requires Neo4j)
            if CONTEXT_EXPANDER_AVAILABLE and GraphContextExpander:
                self.context_expander = GraphContextExpander(neo4j_client)
                logger.info("GraphContextExpander initialized")
            else:
                self.context_expander = None
                logger.debug("GraphContextExpander not available")
        else:
            self.hybrid_ranker = None
            self.evidence_synthesizer = None
            self.conflict_detector = None
            self.context_expander = None
            logger.warning(
                "Neo4j client not provided. Graph search, synthesis, conflict detection, "
                "and context expansion disabled."
            )

        logger.info("UnifiedSearchPipeline initialized (v4.2 with context expansion)")

    async def search(
        self,
        query: str,
        options: Optional[SearchOptions] = None
    ) -> SearchResponse:
        """통합 검색 수행.

        검색 파이프라인:
            1. Query Classification (쿼리 유형 분류)
            2. Hybrid Search (Graph + Vector 검색)
            3. Adaptive Ranking (동적 가중치 조정)
            4. Evidence Synthesis (근거 종합, 선택적)
            5. Conflict Detection (충돌 탐지, 선택적)

        Args:
            query: 검색 쿼리 (자연어)
            options: 검색 옵션 (기본값: SearchOptions())

        Returns:
            SearchResponse 객체

        Raises:
            ValidationError: Neo4j 클라이언트가 없는 경우
        """
        start_time = time.time()
        options = options or SearchOptions()

        # Validate
        if not self.neo4j_client:
            raise ValidationError(message="Neo4j client is required for search", error_code=ErrorCode.VAL_MISSING_FIELD)

        logger.info("Starting unified search", query=query[:100])

        # 1. Query Classification (with optional pattern router)
        query_type = self.query_classifier.classify(query)
        confidence = self.query_classifier.get_confidence(query, query_type)

        # v4.2: Enhanced pattern classification
        parsed_query = None
        extracted_entities = {}
        if options.use_pattern_router and self.pattern_router:
            parsed_query = self.pattern_router.parse_query(query)
            extracted_entities = {
                "interventions": parsed_query.interventions,
                "pathologies": parsed_query.pathologies,
                "outcomes": parsed_query.outcomes,
            }
            logger.info(
                "Pattern router classification",
                pattern=parsed_query.pattern.value,
                confidence=parsed_query.confidence,
                interventions=parsed_query.interventions
            )

        # v4.2: Context expansion (IS_A hierarchy traversal)
        expanded_context = {}
        if options.enable_context_expansion and self.context_expander and extracted_entities.get("interventions"):
            try:
                expanded = await self.context_expander.expand_query_context(
                    interventions=extracted_entities["interventions"],
                    pathologies=extracted_entities.get("pathologies", []),
                    outcomes=extracted_entities.get("outcomes", []),
                    direction=options.expansion_direction,
                    max_depth=options.expansion_max_depth
                )
                expanded_context = {
                    "original_interventions": expanded.original_interventions,
                    "expanded_interventions": expanded.expanded_interventions,
                    "original_pathologies": expanded.original_pathologies,
                    "expanded_pathologies": expanded.expanded_pathologies,
                    "original_outcomes": expanded.original_outcomes,
                    "expanded_outcomes": expanded.expanded_outcomes,
                    "original_anatomies": expanded.original_anatomies,
                    "expanded_anatomies": expanded.expanded_anatomies,
                    "intervention_hierarchy": expanded.intervention_hierarchy,
                }
                logger.info(
                    "Context expanded",
                    original_count=len(expanded.original_interventions),
                    expanded_count=len(expanded.expanded_interventions)
                )
            except Exception as e:
                logger.warning(f"Context expansion failed: {e}")

        query_analysis = QueryAnalysis(
            query_type=query_type,
            confidence=confidence,
            query_pattern=parsed_query.pattern.value if parsed_query else None,
            extracted_entities=extracted_entities,
            expanded_context=expanded_context
        )

        logger.info(
            "Query classified",
            query_type=query_type.value,
            confidence=confidence
        )

        # 2. Hybrid Search
        search_start = time.time()

        # Get query embedding (use expanded interventions if available)
        search_query = query
        if expanded_context.get("expanded_interventions"):
            # Optionally enhance search with expanded terms
            expanded_terms = expanded_context["expanded_interventions"][:5]  # Limit to avoid too long query
            if len(expanded_terms) > len(extracted_entities.get("interventions", [])):
                search_query = f"{query} {' '.join(expanded_terms)}"
                logger.debug(f"Enhanced search query with expansions: {search_query[:100]}")

        # Generate query embedding via Neo4j client
        query_embedding = await self.neo4j_client.get_embedding(search_query)

        # Extract SNOMED codes from entities for ontology-aware search
        snomed_codes: list[str] = []
        if SNOMED_LOOKUP_AVAILABLE and extracted_entities:
            for name in extracted_entities.get("interventions", []):
                mapping = get_snomed_for_intervention(name)
                if mapping:
                    snomed_codes.append(mapping.code)
            for name in extracted_entities.get("pathologies", []):
                mapping = get_snomed_for_pathology(name)
                if mapping:
                    snomed_codes.append(mapping.code)
            for name in extracted_entities.get("outcomes", []):
                mapping = get_snomed_for_outcome(name)
                if mapping:
                    snomed_codes.append(mapping.code)
            for name in extracted_entities.get("anatomies", []):
                mapping = get_snomed_for_anatomy(name)
                if mapping:
                    snomed_codes.append(mapping.code)
            if snomed_codes:
                logger.info(f"SNOMED codes for hybrid search: {snomed_codes}")

        # Build graph_filters from expanded context (IS_A hierarchy)
        graph_filters: Optional[dict] = None
        if expanded_context:
            graph_filters = {}
            # Use expanded entities (IS_A hierarchy included) when available, fallback to originals
            interventions = expanded_context.get("expanded_interventions") or extracted_entities.get("interventions", [])
            pathologies = expanded_context.get("expanded_pathologies") or extracted_entities.get("pathologies", [])
            outcomes = expanded_context.get("expanded_outcomes") or extracted_entities.get("outcomes", [])
            anatomies = expanded_context.get("expanded_anatomies") or extracted_entities.get("anatomies", [])
            if interventions:
                graph_filters["interventions" if len(interventions) > 1 else "intervention"] = interventions if len(interventions) > 1 else interventions[0]
            if pathologies:
                graph_filters["pathologies" if len(pathologies) > 1 else "pathology"] = pathologies if len(pathologies) > 1 else pathologies[0]
            if outcomes:
                graph_filters["outcomes" if len(outcomes) > 1 else "outcome"] = outcomes if len(outcomes) > 1 else outcomes[0]
            if anatomies:
                graph_filters["anatomies" if len(anatomies) > 1 else "anatomy"] = anatomies if len(anatomies) > 1 else anatomies[0]
            if not graph_filters:
                graph_filters = None

        # Perform hybrid search
        if self.hybrid_ranker and options.enable_adaptive:
            # Use HybridRanker for raw results
            hybrid_results = await self.hybrid_ranker.search(
                query=query,
                query_embedding=query_embedding,
                top_k=options.top_k * 2,  # Get more for ranking
                graph_weight=options.graph_weight or 0.6,
                vector_weight=options.vector_weight or 0.4,
                snomed_codes=snomed_codes or None,
                graph_filters=graph_filters,
            )

            # Convert HybridResult to format for AdaptiveRanker
            graph_results = []
            vector_results = []

            for hr in hybrid_results:
                if hr.result_type == "graph" and hr.evidence:
                    graph_results.append({
                        "paper_id": hr.source_id,
                        "title": hr.paper.title if hr.paper else "",
                        "score": hr.score,
                        "evidence": hr.evidence,
                        "paper": hr.paper,
                    })
                elif hr.result_type == "vector" and hr.vector_result:
                    vector_results.append(hr.vector_result)

            # Apply adaptive ranking
            ranked_results = self.adaptive_ranker.rank(
                query=query,
                graph_results=graph_results,
                vector_results=vector_results,
                override_weights=(
                    {"graph": options.graph_weight, "vector": options.vector_weight}
                    if options.graph_weight is not None
                    else None
                )
            )
        else:
            # Fallback: empty results (Neo4j hybrid ranker not available)
            ranked_results = []

        search_time = (time.time() - search_start) * 1000

        logger.info(
            "Hybrid search completed",
            search_time_ms=search_time,
            result_count=len(ranked_results)
        )

        # 3. Evidence Synthesis (optional)
        synthesis_result = None
        synthesis_time = None

        if options.include_synthesis and self.evidence_synthesizer:
            synthesis_start = time.time()

            # Extract intervention and outcome from query or results
            intervention, outcome = self._extract_intervention_outcome(
                query, ranked_results
            )

            if intervention and outcome:
                try:
                    synthesis_result = await self.evidence_synthesizer.synthesize(
                        intervention=intervention,
                        outcome=outcome,
                        min_papers=options.synthesis_min_papers
                    )
                    synthesis_time = (time.time() - synthesis_start) * 1000

                    logger.info(
                        "Evidence synthesis completed",
                        intervention=intervention,
                        outcome=outcome,
                        strength=synthesis_result.strength.value,
                        grade=synthesis_result.grade_rating,
                        synthesis_time_ms=synthesis_time
                    )
                except ProcessingError as e:
                    logger.error(
                        "Evidence synthesis processing error",
                        intervention=intervention,
                        outcome=outcome,
                        error=str(e),
                        exc_info=True
                    )
                except Exception as e:
                    logger.error(
                        "Evidence synthesis failed",
                        intervention=intervention,
                        outcome=outcome,
                        error=str(e),
                        exc_info=True
                    )

        # 4. Conflict Detection (optional)
        conflicts = None
        conflict_time = None

        if options.detect_conflicts and self.conflict_detector:
            conflict_start = time.time()

            intervention, outcome = self._extract_intervention_outcome(
                query, ranked_results
            )

            if intervention and outcome:
                try:
                    conflict = await self.conflict_detector.detect_conflicts(
                        intervention=intervention,
                        outcome=outcome
                    )

                    # Filter by severity
                    if conflict and self._check_conflict_severity(
                        conflict, options.conflict_min_severity
                    ):
                        conflicts = [conflict]

                    conflict_time = (time.time() - conflict_start) * 1000

                    logger.info(
                        "Conflict detection completed",
                        intervention=intervention,
                        outcome=outcome,
                        conflicts_found=len(conflicts) if conflicts else 0,
                        conflict_time_ms=conflict_time
                    )
                except ProcessingError as e:
                    logger.error(
                        "Conflict detection processing error",
                        intervention=intervention,
                        outcome=outcome,
                        error=str(e),
                        exc_info=True
                    )
                except Exception as e:
                    logger.error(
                        "Conflict detection failed",
                        intervention=intervention,
                        outcome=outcome,
                        error=str(e),
                        exc_info=True
                    )

        # 5. Build response
        total_time = (time.time() - start_time) * 1000

        response = SearchResponse(
            results=ranked_results[:options.top_k],
            synthesis=synthesis_result,
            conflicts=conflicts,
            query_analysis=query_analysis,
            execution_time_ms=total_time,
            graph_time_ms=search_time,  # Combined graph+vector search time
            vector_time_ms=search_time,  # Combined graph+vector search time
            synthesis_time_ms=synthesis_time,
            conflict_time_ms=conflict_time
        )

        logger.info(
            "Search completed",
            total_time_ms=total_time,
            result_count=len(response.results)
        )

        return response

    def _extract_intervention_outcome(
        self,
        query: str,
        results: list[RankedResult]
    ) -> tuple[Optional[str], Optional[str]]:
        """쿼리와 결과에서 Intervention, Outcome 추출.

        Args:
            query: 검색 쿼리
            results: 검색 결과 리스트

        Returns:
            (intervention, outcome) 튜플
        """
        intervention = None
        outcome = None

        # Extract from top result with evidence
        for result in results:
            if result.evidence:
                intervention = result.evidence.intervention
                outcome = result.evidence.outcome
                break

        # TODO: Implement NLP-based extraction from query
        # For now, return from results only

        return intervention, outcome

    def _check_conflict_severity(
        self,
        conflict: ConflictResult,
        min_severity: str
    ) -> bool:
        """충돌 심각도 확인.

        Args:
            conflict: ConflictResult 객체
            min_severity: 최소 심각도 문자열

        Returns:
            조건을 만족하면 True
        """
        severity_order = {
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }

        # ConflictSeverity is IntEnum, so use .name for string lookup
        # or use the integer value directly
        if hasattr(conflict.severity, 'name'):
            conflict_level = severity_order.get(conflict.severity.name.lower(), 0)
        elif hasattr(conflict.severity, 'value') and isinstance(conflict.severity.value, int):
            # IntEnum: value is the integer directly (1, 2, 3, 4)
            conflict_level = conflict.severity.value
        else:
            conflict_level = severity_order.get(str(conflict.severity).lower(), 0)

        min_level = severity_order.get(min_severity.lower(), 0)

        return conflict_level >= min_level


# =============================================================================
# Convenience Functions
# =============================================================================

def create_pipeline(
    neo4j_client: Optional["Neo4jClient"] = None,
    config: Optional[dict] = None
) -> UnifiedSearchPipeline:
    """파이프라인 생성 헬퍼 함수.

    Args:
        neo4j_client: Neo4j 클라이언트 (선택적)
        config: 설정 딕셔너리 (선택적)

    Returns:
        UnifiedSearchPipeline 인스턴스

    Example:
        >>> from src.graph.neo4j_client import Neo4jClient
        >>>
        >>> async with Neo4jClient() as client:
        ...     pipeline = create_pipeline(client)
        ...     response = await pipeline.search("TLIF vs OLIF")
    """
    return UnifiedSearchPipeline(neo4j_client, config)


async def quick_search(
    query: str,
    neo4j_client: Optional["Neo4jClient"] = None,
    top_k: int = 10
) -> SearchResponse:
    """빠른 검색 헬퍼 함수 (기본 설정).

    Args:
        query: 검색 쿼리
        neo4j_client: Neo4j 클라이언트 (선택적)
        top_k: 반환할 결과 수

    Returns:
        SearchResponse 객체

    Example:
        >>> response = await quick_search(
        ...     "What is the fusion rate of TLIF?",
        ...     neo4j_client=client
        ... )
        >>> print(response.get_summary())
    """
    pipeline = create_pipeline(neo4j_client)
    options = SearchOptions(
        top_k=top_k,
        include_synthesis=True,
        detect_conflicts=False  # 빠른 검색에서는 충돌 탐지 생략
    )
    return await pipeline.search(query, options)


# =============================================================================
# Example Usage
# =============================================================================

async def example_usage():
    """사용 예시."""
    print("=" * 80)
    print("Unified Search Pipeline Example")
    print("=" * 80)

    # Mock clients (실제로는 실제 클라이언트 사용)
    neo4j_client = None  # await Neo4jClient().__aenter__()

    # Create pipeline
    pipeline = create_pipeline(neo4j_client)

    # Example queries
    queries = [
        "What is the fusion rate of TLIF?",
        "TLIF vs OLIF for lumbar stenosis",
        "What treatments exist for cervical spondylosis?",
        "Is UBE effective for disc herniation?",
        "How is endoscopic spine surgery performed?",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        print("-" * 80)

        try:
            response = await pipeline.search(
                query=query,
                options=SearchOptions(
                    top_k=5,
                    include_synthesis=True,
                    detect_conflicts=True
                )
            )

            print(response.get_summary())
            print()

            # Show top results
            for i, result in enumerate(response.results[:3], 1):
                print(f"{i}. {result.title[:60]}...")
                print(f"   Score: {result.final_score:.3f} "
                      f"(Graph: {result.graph_score:.3f}, Vector: {result.vector_score:.3f})")

        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(example_usage())

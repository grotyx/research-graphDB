"""Adaptive Hybrid Ranker - Dynamic Weight Adjustment.

Graph + Vector 통합 랭커의 adaptive 버전.
쿼리 유형에 따라 Graph/Vector 가중치를 동적으로 조정하여
최적의 검색 결과를 제공.

Query Type별 최적 가중치:
    - FACTUAL: Graph 70%, Vector 30% (구조화된 사실 정보)
    - COMPARATIVE: Graph 80%, Vector 20% (비교 연구 근거)
    - EXPLORATORY: Graph 40%, Vector 60% (다양한 문서 탐색)
    - EVIDENCE: Graph 75%, Vector 25% (통계적 근거)
    - PROCEDURAL: Graph 30%, Vector 70% (절차/기술 설명)
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Try relative imports first, fall back to absolute
try:
    from .graph_result import GraphEvidence, PaperNode
except ImportError:
    from solver.graph_result import GraphEvidence, PaperNode

try:
    from ..storage import SearchResult as VectorSearchResult
except ImportError:
    try:
        from storage import SearchResult as VectorSearchResult
    except ImportError:
        # Define minimal stub if not available
        @dataclass
        class VectorSearchResult:
            """Minimal stub for standalone usage."""
            chunk_id: str = ""
            content: str = ""
            similarity: float = 0.0
            metadata: dict = field(default_factory=dict)

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """쿼리 유형 분류.

    각 쿼리 유형은 서로 다른 정보 요구사항을 가짐:
        - FACTUAL: 구체적인 수치/사실 (Graph 선호)
        - COMPARATIVE: 두 가지 이상 비교 (Graph 선호)
        - EXPLORATORY: 넓은 범위 탐색 (Vector 선호)
        - EVIDENCE: 통계적 근거 (Graph 선호)
        - PROCEDURAL: 절차/기술 설명 (Vector 선호)
    """
    FACTUAL = "factual"          # "What is the fusion rate of TLIF?"
    COMPARATIVE = "comparative"   # "TLIF vs OLIF for stenosis"
    EXPLORATORY = "exploratory"  # "What treatments exist for stenosis?"
    EVIDENCE = "evidence"         # "Is TLIF effective for disc herniation?"
    PROCEDURAL = "procedural"     # "How is UBE performed?"


# Query Type별 최적 가중치 설정
QUERY_TYPE_WEIGHTS = {
    QueryType.FACTUAL: {"graph": 0.7, "vector": 0.3},
    QueryType.COMPARATIVE: {"graph": 0.8, "vector": 0.2},
    QueryType.EXPLORATORY: {"graph": 0.4, "vector": 0.6},
    QueryType.EVIDENCE: {"graph": 0.75, "vector": 0.25},
    QueryType.PROCEDURAL: {"graph": 0.3, "vector": 0.7},
}


class QueryClassifier:
    """쿼리 유형 분류기.

    정규 표현식 패턴 매칭을 통해 쿼리를 5가지 유형으로 분류.
    여러 패턴이 매칭될 경우 우선순위 순으로 선택.

    우선순위:
        1. COMPARATIVE (가장 구체적)
        2. EVIDENCE
        3. FACTUAL
        4. PROCEDURAL
        5. EXPLORATORY (기본값)
    """

    # 패턴 정의 (대소문자 무시)
    PATTERNS = {
        QueryType.FACTUAL: [
            r"\bwhat\s+is\s+(the\s+)?(\w+\s+)?(rate|value|percentage|incidence|number|amount)",
            r"\bhow\s+(much|many|high|low)",
            r"\b(fusion|complication|success|improvement|recurrence)\s+rate\b",
            r"\bvalue\s+of\b",
            r"\bpercentage\s+of\b",
        ],
        QueryType.COMPARATIVE: [
            r"\bvs\.?\b",
            r"\bversus\b",
            r"\bcompare\b",
            r"\bcomparison\s+(of|between)\b",
            r"\bbetween\s+\w+\s+and\b",
            r"\b(\w+)\s+or\s+(\w+)\s+for\b",
            r"\bdifference\s+between\b",
        ],
        QueryType.EXPLORATORY: [
            r"\bwhat\s+(\w+\s+)?exist",
            r"\boptions\s+for\b",
            r"\btreatments?\s+for\b",
            r"\bapproaches\s+to\b",
            r"\btypes\s+of\b",
            r"\blist\s+(all|the)?\b",
            r"\bwhat\s+are\s+(the\s+)?(different|various)\b",
        ],
        QueryType.EVIDENCE: [
            r"\bis\s+\w+\s+(effective|beneficial|superior|inferior)",
            r"\bdoes\s+\w+\s+(work|improve|reduce|increase)",
            r"\bevidence\s+(for|of|supporting)\b",
            r"\bproven\s+to\b",
            r"\bstatistically\s+significant\b",
            r"\bp-value\b",
            r"\beffect\s+size\b",
        ],
        QueryType.PROCEDURAL: [
            r"\bhow\s+(is|to)\s+\w+\s+(performed|done)",
            r"\bhow\s+do\s+you\s+perform\b",
            r"\btechnique\s+(for|of)\b",
            r"\bsteps?\s+(of|for|to)\b",
            r"\bprocedure\s+(for|of)\b",
            r"\bmethod\s+(of|for)\b",
            r"\bsurgical\s+technique\b",
            r"\bapproach\s+(to|for)\s+performing\b",
        ],
    }

    # 패턴 우선순위 (높을수록 우선)
    PRIORITY = {
        QueryType.COMPARATIVE: 5,
        QueryType.EVIDENCE: 4,
        QueryType.FACTUAL: 3,
        QueryType.PROCEDURAL: 2,
        QueryType.EXPLORATORY: 1,
    }

    def __init__(self):
        """패턴 컴파일 및 초기화."""
        # 정규 표현식 미리 컴파일
        self.compiled_patterns: dict[QueryType, list[re.Pattern]] = {}
        for query_type, patterns in self.PATTERNS.items():
            self.compiled_patterns[query_type] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def classify(self, query: str) -> QueryType:
        """쿼리 유형 분류.

        Args:
            query: 검색 쿼리 문자열

        Returns:
            분류된 QueryType (기본값: EXPLORATORY)

        Examples:
            >>> classifier = QueryClassifier()
            >>> classifier.classify("What is the fusion rate of TLIF?")
            QueryType.FACTUAL
            >>> classifier.classify("TLIF vs OLIF for stenosis")
            QueryType.COMPARATIVE
            >>> classifier.classify("How is UBE performed?")
            QueryType.PROCEDURAL
        """
        # 각 유형별 매칭 여부 확인
        matches: dict[QueryType, bool] = {}

        for query_type, patterns in self.compiled_patterns.items():
            matches[query_type] = any(
                pattern.search(query) for pattern in patterns
            )

        # 매칭된 유형 중 우선순위가 가장 높은 것 선택
        matched_types = [qt for qt, matched in matches.items() if matched]

        if not matched_types:
            logger.debug(f"No pattern matched for query: {query[:50]}... -> EXPLORATORY")
            return QueryType.EXPLORATORY

        # 우선순위 기준 정렬
        matched_types.sort(key=lambda qt: self.PRIORITY[qt], reverse=True)
        selected_type = matched_types[0]

        logger.debug(
            f"Query classified as {selected_type.value}: {query[:50]}..."
        )

        return selected_type

    def get_confidence(self, query: str, query_type: QueryType) -> float:
        """분류 신뢰도 계산.

        Args:
            query: 검색 쿼리
            query_type: 분류된 쿼리 유형

        Returns:
            신뢰도 점수 (0~1)
        """
        patterns = self.compiled_patterns.get(query_type, [])
        matches = sum(1 for p in patterns if p.search(query))

        # 매칭된 패턴 수가 많을수록 높은 신뢰도
        if matches == 0:
            return 0.0
        elif matches == 1:
            return 0.7
        elif matches == 2:
            return 0.85
        else:
            return 0.95


@dataclass
class RankedResult:
    """Adaptive Ranker 결과.

    Graph와 Vector 검색 결과를 통합하여 쿼리 유형에 맞게
    가중치를 조정한 최종 결과.

    Attributes:
        paper_id: 논문 고유 ID
        title: 논문 제목
        graph_score: Graph 검색 점수 (정규화된 0~1)
        vector_score: Vector 검색 점수 (정규화된 0~1)
        final_score: 최종 통합 점수 (가중 평균)
        query_type: 적용된 쿼리 유형
        metadata: 추가 메타데이터 (evidence, paper, vector_result 등)
    """
    paper_id: str
    title: str
    graph_score: float
    vector_score: float
    final_score: float
    query_type: QueryType
    metadata: dict = field(default_factory=dict)

    # Optional detailed data
    evidence: Optional[GraphEvidence] = None
    paper: Optional[PaperNode] = None
    vector_result: Optional[VectorSearchResult] = None

    def get_display_text(self) -> str:
        """결과 표시용 텍스트 생성.

        Returns:
            사람이 읽을 수 있는 결과 설명
        """
        parts = [f"[{self.query_type.value}]"]

        if self.evidence:
            parts.append(self.evidence.get_display_text())
        elif self.vector_result and self.vector_result.summary:
            parts.append(self.vector_result.summary[:100])
        else:
            parts.append(self.title[:100])

        return " ".join(parts)

    def get_score_breakdown(self) -> str:
        """점수 분석 문자열 생성.

        Returns:
            점수 구성 요소 설명
        """
        return (
            f"Final: {self.final_score:.3f} "
            f"(Graph: {self.graph_score:.3f}, Vector: {self.vector_score:.3f})"
        )


class AdaptiveHybridRanker:
    """Adaptive Hybrid Ranker.

    쿼리 유형에 따라 Graph/Vector 가중치를 동적으로 조정하는 랭커.
    기존 HybridRanker의 확장 버전.

    주요 기능:
        1. 쿼리 유형 자동 분류 (QueryClassifier)
        2. 유형별 최적 가중치 적용
        3. 점수 정규화 (Min-Max Normalization)
        4. 중복 제거 및 병합

    사용 예시:
        >>> ranker = AdaptiveHybridRanker()
        >>> results = ranker.rank(
        ...     query="TLIF vs OLIF for stenosis",
        ...     graph_results=[...],
        ...     vector_results=[...]
        ... )
        >>> print(results[0].query_type)  # QueryType.COMPARATIVE
        >>> print(results[0].final_score)  # 0.85
    """

    def __init__(self, classifier: Optional[QueryClassifier] = None):
        """초기화.

        Args:
            classifier: QueryClassifier 인스턴스 (선택적)
        """
        self.classifier = classifier or QueryClassifier()

    def rank(
        self,
        query: str,
        graph_results: list[dict],
        vector_results: list[VectorSearchResult],
        override_weights: Optional[dict] = None
    ) -> list[RankedResult]:
        """Adaptive Hybrid Ranking 수행.

        Args:
            query: 검색 쿼리 (자연어)
            graph_results: Graph 검색 결과 (dict 형태)
                Expected keys: paper_id, score, evidence (optional), paper (optional)
            vector_results: Vector 검색 결과 (VectorSearchResult 리스트)
            override_weights: 가중치 강제 지정 (선택적)
                예: {"graph": 0.5, "vector": 0.5}

        Returns:
            final_score 기준 정렬된 RankedResult 리스트
        """
        # 1. 쿼리 유형 분류
        query_type = self.classifier.classify(query)
        logger.info(f"Query classified as: {query_type.value}")

        # 2. 가중치 결정
        if override_weights:
            weights = override_weights
            logger.info(f"Using override weights: {weights}")
        else:
            weights = QUERY_TYPE_WEIGHTS[query_type]
            logger.info(f"Using default weights for {query_type.value}: {weights}")

        # 3. Graph 결과 정규화
        normalized_graph = self._normalize_scores(
            graph_results, score_key="score"
        )

        # 4. Vector 결과 정규화
        normalized_vector = self._normalize_vector_results(vector_results)

        # 5. 결과 병합
        merged_results = self._merge_results(
            normalized_graph,
            normalized_vector,
            weights,
            query_type
        )

        # 6. 최종 점수 기준 정렬
        merged_results.sort(key=lambda r: r.final_score, reverse=True)

        logger.info(f"Ranked {len(merged_results)} results for {query_type.value} query")

        return merged_results

    def _normalize_scores(
        self,
        results: list[dict],
        score_key: str = "score"
    ) -> list[dict]:
        """점수 정규화 (Min-Max Normalization).

        Args:
            results: 결과 리스트
            score_key: 점수 키 이름

        Returns:
            정규화된 결과 리스트 (0~1)
        """
        if not results:
            return []

        # 점수 추출
        scores = [r.get(score_key, 0.0) for r in results]
        min_score = min(scores) if scores else 0.0
        max_score = max(scores) if scores else 1.0

        # Min-Max 정규화
        if max_score - min_score < 1e-6:  # 모든 점수가 같은 경우
            normalized_results = []
            for r in results:
                r_copy = r.copy()
                r_copy[score_key] = 1.0
                normalized_results.append(r_copy)
        else:
            normalized_results = []
            for r in results:
                r_copy = r.copy()
                original_score = r.get(score_key, 0.0)
                normalized_score = (original_score - min_score) / (max_score - min_score)
                r_copy[score_key] = normalized_score
                normalized_results.append(r_copy)

        return normalized_results

    def _normalize_vector_results(
        self,
        vector_results: list[VectorSearchResult]
    ) -> list[dict]:
        """Vector 검색 결과를 dict로 변환 및 정규화.

        Args:
            vector_results: VectorSearchResult 리스트

        Returns:
            정규화된 dict 리스트
        """
        # VectorSearchResult → dict 변환
        results_as_dict = [
            {
                "paper_id": vr.document_id,  # document_id를 paper_id로 매핑
                "title": vr.title,
                "score": vr.score,
                "vector_result": vr,
            }
            for vr in vector_results
        ]

        # 점수 정규화
        return self._normalize_scores(results_as_dict, score_key="score")

    def _merge_results(
        self,
        graph_results: list[dict],
        vector_results: list[dict],
        weights: dict,
        query_type: QueryType
    ) -> list[RankedResult]:
        """Graph + Vector 결과 병합.

        가중치 적용 및 중복 제거:
            - 같은 paper_id를 가진 결과는 하나로 병합
            - Graph와 Vector 점수를 가중 평균으로 계산
            - 하나만 있는 경우는 해당 점수만 사용

        Args:
            graph_results: 정규화된 Graph 결과
            vector_results: 정규화된 Vector 결과
            weights: 가중치 {"graph": float, "vector": float}
            query_type: 쿼리 유형

        Returns:
            병합된 RankedResult 리스트
        """
        graph_weight = weights["graph"]
        vector_weight = weights["vector"]

        # paper_id별로 결과 그룹화
        merged_dict: dict[str, dict] = {}

        # Graph 결과 추가
        for gr in graph_results:
            paper_id = gr["paper_id"]
            merged_dict[paper_id] = {
                "paper_id": paper_id,
                "title": gr.get("title", ""),
                "graph_score": gr["score"],
                "vector_score": 0.0,
                "evidence": gr.get("evidence"),
                "paper": gr.get("paper"),
                "vector_result": None,
            }

        # Vector 결과 병합
        for vr in vector_results:
            paper_id = vr["paper_id"]
            if paper_id in merged_dict:
                # 이미 있는 경우 업데이트
                merged_dict[paper_id]["vector_score"] = vr["score"]
                merged_dict[paper_id]["vector_result"] = vr.get("vector_result")
                if not merged_dict[paper_id]["title"]:
                    merged_dict[paper_id]["title"] = vr.get("title", "")
            else:
                # 새로 추가
                merged_dict[paper_id] = {
                    "paper_id": paper_id,
                    "title": vr.get("title", ""),
                    "graph_score": 0.0,
                    "vector_score": vr["score"],
                    "evidence": None,
                    "paper": None,
                    "vector_result": vr.get("vector_result"),
                }

        # 최종 점수 계산 및 RankedResult 생성
        ranked_results: list[RankedResult] = []

        for paper_id, data in merged_dict.items():
            # 가중 평균 계산
            graph_score = data["graph_score"]
            vector_score = data["vector_score"]

            # 둘 다 있는 경우: 가중 평균
            if graph_score > 0 and vector_score > 0:
                final_score = graph_weight * graph_score + vector_weight * vector_score
            # Graph만 있는 경우
            elif graph_score > 0:
                final_score = graph_score
            # Vector만 있는 경우
            else:
                final_score = vector_score

            ranked_results.append(RankedResult(
                paper_id=paper_id,
                title=data["title"],
                graph_score=graph_score,
                vector_score=vector_score,
                final_score=final_score,
                query_type=query_type,
                evidence=data["evidence"],
                paper=data["paper"],
                vector_result=data["vector_result"],
                metadata={
                    "graph_weight": graph_weight,
                    "vector_weight": vector_weight,
                }
            ))

        return ranked_results


# 사용 예시
def example_usage():
    """AdaptiveHybridRanker 사용 예시."""
    from .graph_result import GraphEvidence, PaperNode

    # 1. Ranker 초기화
    ranker = AdaptiveHybridRanker()

    # 2. Mock Graph 결과
    graph_results = [
        {
            "paper_id": "paper1",
            "title": "TLIF vs OLIF for Stenosis",
            "score": 0.85,
            "evidence": GraphEvidence(
                intervention="TLIF",
                outcome="Fusion Rate",
                value="92%",
                source_paper_id="paper1",
                evidence_level="1b",
                p_value=0.001,
                is_significant=True,
                direction="improved"
            ),
            "paper": PaperNode(
                paper_id="paper1",
                title="TLIF vs OLIF for Stenosis",
                authors=["Kim", "Lee"],
                year=2024
            )
        }
    ]

    # 3. Mock Vector 결과
    vector_results = [
        VectorSearchResult(
            chunk_id="chunk1",
            paper_id="paper1",
            title="TLIF vs OLIF for Stenosis",
            score=0.78,
            content="TLIF showed superior fusion rate...",
            tier=1,
            section="results",
            evidence_level="1b",
            is_key_finding=True,
            has_statistics=True,
            publication_year=2024,
            summary="TLIF superior to OLIF"
        )
    ]

    # 4. 다양한 쿼리 유형 테스트
    queries = [
        "What is the fusion rate of TLIF?",  # FACTUAL
        "TLIF vs OLIF for stenosis",  # COMPARATIVE
        "What treatments exist for stenosis?",  # EXPLORATORY
        "Is TLIF effective for disc herniation?",  # EVIDENCE
        "How is UBE performed?",  # PROCEDURAL
    ]

    for query in queries:
        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print(f"{'='*70}")

        results = ranker.rank(
            query=query,
            graph_results=graph_results,
            vector_results=vector_results
        )

        for i, result in enumerate(results, 1):
            print(f"{i}. {result.get_display_text()}")
            print(f"   {result.get_score_breakdown()}")
            print()


if __name__ == "__main__":
    example_usage()

"""Tiered Hybrid Search module for hierarchical document retrieval.

v5.3: Neo4j Vector Index 통합 지원
v1.14.12: Neo4j Vector Index가 유일한 벡터 저장소
v1.14.17: Neo4j hybrid_search 통합 - 그래프 필터링 + 벡터 검색 단일 쿼리
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, Any, TYPE_CHECKING

# Optional Neo4j import (v5.3)
try:
    from graph.neo4j_client import Neo4jClient
    NEO4J_AVAILABLE = True
except ImportError:
    try:
        from ..graph.neo4j_client import Neo4jClient
        NEO4J_AVAILABLE = True
    except ImportError:
        NEO4J_AVAILABLE = False
        Neo4jClient = None  # type: ignore

try:
    from builder.citation_detector import SourceType
    from builder.study_classifier import EvidenceLevel
except ImportError:
    from enum import Enum as _Enum

    class SourceType(_Enum):
        ORIGINAL = "original"
        CITATION = "citation"  # Fixed: CITED → CITATION to match builder.citation_detector
        BACKGROUND = "background"
        UNKNOWN = "unknown"

    class EvidenceLevel(_Enum):
        LEVEL_1A = "1a"
        LEVEL_1B = "1b"
        LEVEL_2A = "2a"
        LEVEL_2B = "2b"
        LEVEL_2C = "2c"
        LEVEL_3A = "3a"
        LEVEL_3B = "3b"
        LEVEL_4 = "4"
        LEVEL_5 = "5"
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None  # type: ignore

from .query_parser import MedicalEntity, ParsedQuery

logger = logging.getLogger(__name__)


class SearchTier(Enum):
    """검색 계층 전략."""
    TIER1_ONLY = "tier1_only"           # 핵심 섹션만 (Abstract, Results, Conclusion)
    TIER1_THEN_TIER2 = "tier1_then_tier2"  # 핵심 우선, 부족시 상세 확장
    ALL_TIERS = "all_tiers"             # 전체 검색


class SearchSource(Enum):
    """검색 소스."""
    VECTOR = "vector"
    GRAPH = "graph"
    BOTH = "both"


class SearchBackend(Enum):
    """벡터 검색 백엔드 (v1.14.12: Neo4j only)."""
    NEO4J = "neo4j"          # Neo4j Vector Index (유일한 백엔드)


@dataclass
class ChunkInfo:
    """청크 정보."""
    chunk_id: str
    document_id: str
    text: str
    tier: int = 1
    section: str = "other"
    source_type: SourceType = SourceType.ORIGINAL
    evidence_level: EvidenceLevel = EvidenceLevel.LEVEL_5
    publication_year: int = 2020
    page_number: Optional[int] = None

    # 문서 메타데이터
    title: Optional[str] = None
    authors: Optional[list[str]] = None


@dataclass
class SearchResult:
    """검색 결과."""
    chunk: ChunkInfo
    score: float
    tier: int
    source_type: str
    evidence_level: str
    search_source: SearchSource = SearchSource.VECTOR

    # 추가 점수
    vector_score: Optional[float] = None
    graph_score: Optional[float] = None


@dataclass
class SearchInput:
    """검색 입력."""
    query: str
    parsed_query: Optional[ParsedQuery] = None
    entities: list[MedicalEntity] = field(default_factory=list)
    top_k: int = 10
    tier_strategy: SearchTier = SearchTier.TIER1_THEN_TIER2
    prefer_original: bool = True
    min_evidence_level: Optional[str] = None
    recency_weight: float = 0.1
    min_year: Optional[int] = None


@dataclass
class SearchOutput:
    """검색 결과."""
    results: list[SearchResult] = field(default_factory=list)
    total_found: int = 0

    # 검색 통계
    tier1_count: int = 0
    tier2_count: int = 0
    vector_results: int = 0
    graph_results: int = 0

    # 확장된 검색어
    expanded_query: Optional[str] = None
    search_strategy_used: SearchTier = SearchTier.TIER1_THEN_TIER2

    # v1.14.12: 백엔드 정보 (Neo4j only)
    vector_backend: SearchBackend = SearchBackend.NEO4J


class VectorDBProtocol(Protocol):
    """벡터 DB 프로토콜."""

    def search(
        self,
        query_embedding: list[float],
        collection: str,
        top_k: int,
        filters: Optional[dict] = None
    ) -> list[dict]:
        """벡터 검색."""
        ...

    def get_embedding(self, text: str) -> list[float]:
        """텍스트 임베딩 생성."""
        ...


class GraphDBProtocol(Protocol):
    """그래프 DB 프로토콜."""

    def search_by_entities(
        self,
        entities: list[str],
        top_k: int,
        max_hops: int = 2
    ) -> list[dict]:
        """엔티티 기반 그래프 검색."""
        ...


class TieredHybridSearch:
    """계층적 하이브리드 검색 엔진.

    v5.3: Neo4j Vector Index 지원
    - use_neo4j_vector=True: Neo4j vector_search_chunks() 사용
    - use_neo4j_vector=False: 레거시 VectorDB 프로토콜 사용 (기본값)
    """

    # Tier별 컬렉션 매핑
    TIER_COLLECTIONS = {
        1: "tier1_chunks",  # Abstract, Results, Conclusion
        2: "tier2_chunks",  # Introduction, Methods, Discussion
    }

    # Evidence Level 순서 (필터링용)
    EVIDENCE_ORDER = ["1a", "1b", "2a", "2b", "2c", "3a", "3b", "4", "5"]

    def __init__(
        self,
        vector_db: Optional[VectorDBProtocol] = None,
        graph_db: Optional[GraphDBProtocol] = None,
        neo4j_client: Optional["Neo4jClient"] = None,
        config: Optional[dict[str, Any]] = None,
        use_neo4j_vector: bool = False
    ) -> None:
        """초기화.

        Args:
            vector_db: 벡터 DB 인스턴스 (VectorDBProtocol)
            graph_db: 그래프 DB 인스턴스 (엔티티 기반 검색)
            neo4j_client: Neo4j 클라이언트 (v5.3 - 벡터 검색용)
            config: 설정 딕셔너리
                - rrf_k: RRF 파라미터 (기본값: 60)
                - vector_weight: 벡터 검색 가중치 (기본값: 0.7)
                - graph_weight: 그래프 검색 가중치 (기본값: 0.3)
                - tier1_min_results: Tier1 최소 결과 수 (기본값: 3)
            use_neo4j_vector: Neo4j Vector Index 사용 여부 (v5.3)
            use_neo4j_hybrid: Neo4j hybrid_search (그래프+벡터 통합) 사용 여부 (v1.14.17)
        """
        self.vector_db: Optional[VectorDBProtocol] = vector_db
        self.graph_db: Optional[GraphDBProtocol] = graph_db
        self.neo4j_client: Optional["Neo4jClient"] = neo4j_client
        self.config: dict[str, Any] = config or {}
        self.use_neo4j_vector: bool = use_neo4j_vector and NEO4J_AVAILABLE
        # v1.14.17: Neo4j hybrid_search 사용 (그래프 필터링 + 벡터 검색 통합)
        self.use_neo4j_hybrid: bool = self.config.get("use_neo4j_hybrid", True) and NEO4J_AVAILABLE

        self.rrf_k: int = self.config.get("rrf_k", 60)
        self.vector_weight: float = self.config.get("vector_weight", 0.7)
        self.graph_weight: float = self.config.get("graph_weight", 0.3)
        self.tier1_min_results: int = self.config.get("tier1_min_results", 3)

        # GraphContextExpander for IS_A hierarchy expansion
        self.context_expander = None
        if self.neo4j_client:
            try:
                from solver.graph_context_expander import GraphContextExpander
                self.context_expander = GraphContextExpander(self.neo4j_client)
                logger.info("TieredHybridSearch: GraphContextExpander initialized")
            except ImportError:
                logger.debug("GraphContextExpander not available")

        # Lazy-initialized OpenAI client for embedding generation
        self._openai_client = None

        # v5.3: 백엔드 상태 로깅
        if self.use_neo4j_vector:
            if self.neo4j_client:
                if self.use_neo4j_hybrid:
                    logger.info("TieredHybridSearch: Using Neo4j Hybrid Search (Graph+Vector integrated)")
                else:
                    logger.info("TieredHybridSearch: Using Neo4j Vector Index backend")
            else:
                logger.warning("TieredHybridSearch: Neo4j Vector requested but client not provided, vector search disabled")
                self.use_neo4j_vector = False
                self.use_neo4j_hybrid = False
        else:
            logger.info("TieredHybridSearch: Neo4j Vector not enabled")

    def search(self, input_data: SearchInput) -> SearchOutput:
        """계층적 하이브리드 검색 수행.

        Args:
            input_data: 검색 입력

        Returns:
            검색 결과
        """
        results: list[SearchResult] = []
        tier1_count = 0
        tier2_count = 0

        # 검색 전략에 따라 실행
        if input_data.tier_strategy == SearchTier.TIER1_ONLY:
            results = self._search_tier(
                input_data, tier=1, top_k=input_data.top_k
            )
            tier1_count = len(results)

        elif input_data.tier_strategy == SearchTier.TIER1_THEN_TIER2:
            # Tier 1 먼저 검색
            tier1_results = self._search_tier(
                input_data, tier=1, top_k=input_data.top_k
            )
            tier1_count = len(tier1_results)
            results.extend(tier1_results)

            # 결과 부족시 Tier 2 검색
            if len(results) < input_data.top_k:
                remaining = input_data.top_k - len(results)
                tier2_results = self._search_tier(
                    input_data, tier=2, top_k=remaining
                )
                tier2_count = len(tier2_results)
                results.extend(tier2_results)

        else:  # ALL_TIERS
            # 양쪽 모두 검색 후 병합
            tier1_results = self._search_tier(
                input_data, tier=1, top_k=input_data.top_k
            )
            tier2_results = self._search_tier(
                input_data, tier=2, top_k=input_data.top_k
            )

            tier1_count = len(tier1_results)
            tier2_count = len(tier2_results)

            # RRF로 병합
            results = self._merge_results_rrf(
                tier1_results, tier2_results, input_data.top_k
            )

        # 원본 우선 정렬
        if input_data.prefer_original:
            results = self._prioritize_original(results)

        # Evidence Level 필터링
        if input_data.min_evidence_level:
            results = self._filter_by_evidence(
                results, input_data.min_evidence_level
            )

        # 연도 필터링
        if input_data.min_year:
            results = self._filter_by_year(results, input_data.min_year)

        # top_k 제한
        results = results[:input_data.top_k]

        # 벡터/그래프 결과 통계
        vector_count = sum(1 for r in results if r.search_source in [SearchSource.VECTOR, SearchSource.BOTH])
        graph_count = sum(1 for r in results if r.search_source in [SearchSource.GRAPH, SearchSource.BOTH])

        return SearchOutput(
            results=results,
            total_found=len(results),
            tier1_count=tier1_count,
            tier2_count=tier2_count,
            vector_results=vector_count,
            graph_results=graph_count,
            search_strategy_used=input_data.tier_strategy,
            vector_backend=SearchBackend.NEO4J
        )

    def _search_tier(
        self,
        input_data: SearchInput,
        tier: int,
        top_k: int
    ) -> list[SearchResult]:
        """단일 계층 검색.

        Args:
            input_data: 검색 입력
            tier: 검색할 계층 (1 또는 2)
            top_k: 반환할 결과 수

        Returns:
            검색 결과 목록
        """
        results: list[SearchResult] = []

        # v1.14.17: Neo4j Hybrid Search 우선 사용 (그래프 필터 + 벡터 검색 통합)
        if self.use_neo4j_hybrid and self.neo4j_client:
            hybrid_results = self._neo4j_hybrid_search(input_data, tier, top_k)
            if hybrid_results:
                return hybrid_results
            # Hybrid 검색 실패 시 벡터 검색으로 폴백
            logger.warning("Neo4j hybrid search returned no results, falling back to vector search")

        # 벡터 검색 (v5.3: Neo4j 또는 VectorDB)
        if self.use_neo4j_vector and self.neo4j_client:
            vector_results = self._neo4j_vector_search(input_data, tier, top_k)
        else:
            vector_results = self._vector_search(input_data, tier, top_k)

        # 그래프 검색 (엔티티가 있는 경우)
        graph_results = []
        if input_data.entities and self.graph_db:
            graph_results = self._graph_search(input_data, tier, top_k)

        # 결과 융합
        if vector_results and graph_results:
            results = self._fuse_results(vector_results, graph_results, top_k)
        elif vector_results:
            results = vector_results
        elif graph_results:
            results = graph_results

        return results

    def _vector_search(
        self,
        input_data: SearchInput,
        tier: int,
        top_k: int
    ) -> list[SearchResult]:
        """벡터 검색.

        Args:
            input_data: 검색 입력
            tier: 계층
            top_k: 반환할 결과 수

        Returns:
            벡터 검색 결과
        """
        if not self.vector_db:
            # DB가 없으면 빈 결과 반환 (테스트/개발용)
            return []

        # 쿼리 임베딩 생성
        query_embedding = self.vector_db.get_embedding(input_data.query)

        # 컬렉션 선택
        collection = self.TIER_COLLECTIONS.get(tier, "tier1_chunks")

        # 필터 구성
        filters = {}
        if input_data.min_evidence_level:
            filters["evidence_level"] = {"$in": self._get_acceptable_levels(
                input_data.min_evidence_level
            )}
        if input_data.min_year:
            filters["publication_year"] = {"$gte": input_data.min_year}

        # 검색 수행
        raw_results = self.vector_db.search(
            query_embedding=query_embedding,
            collection=collection,
            top_k=top_k,
            filters=filters if filters else None
        )

        # 결과 변환
        results = []
        for raw in raw_results:
            chunk = ChunkInfo(
                chunk_id=raw.get("id", ""),
                document_id=raw.get("document_id", ""),
                text=raw.get("text", ""),
                tier=tier,
                section=raw.get("section", "other"),
                source_type=SourceType(raw.get("source_type", "original")),
                evidence_level=EvidenceLevel(raw.get("evidence_level", "5")),
                publication_year=raw.get("publication_year", 2020),
                title=raw.get("title"),
                authors=raw.get("authors")
            )

            results.append(SearchResult(
                chunk=chunk,
                score=raw.get("score", 0.0),
                tier=tier,
                source_type=chunk.source_type.value,
                evidence_level=chunk.evidence_level.value,
                search_source=SearchSource.VECTOR,
                vector_score=raw.get("score", 0.0)
            ))

        return results

    def _neo4j_vector_search(
        self,
        input_data: SearchInput,
        tier: int,
        top_k: int
    ) -> list[SearchResult]:
        """Neo4j Vector Index 기반 벡터 검색 (v5.3).

        Neo4j의 HNSW 벡터 인덱스를 사용하여 청크 검색.

        Args:
            input_data: 검색 입력
            tier: 계층 (1 또는 2)
            top_k: 반환할 결과 수

        Returns:
            벡터 검색 결과
        """
        if not self.neo4j_client:
            logger.warning("Neo4j client not available for vector search")
            return []

        # 쿼리 임베딩 생성
        # v1.14.16: Neo4j Vector Index는 3072차원 OpenAI text-embedding-3-large 사용
        # (기존 MedTE 768차원에서 변경됨 - 저장된 임베딩과 일치시키기 위해)
        # v1.14.26: OpenAI 임베딩 필수 (Neo4j 인덱스가 3072d이므로 MedTE 768d는 사용 불가)
        try:
            if not OPENAI_AVAILABLE:
                logger.error("openai package not installed - required for vector search (3072d index)")
                return []
            if self._openai_client is None:
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    logger.error("OPENAI_API_KEY not set - required for vector search (3072d index)")
                    return []
                self._openai_client = openai.OpenAI(api_key=api_key)
            response = self._openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=input_data.query,
                dimensions=3072
            )
            query_embedding = response.data[0].embedding
            logger.debug(f"Generated OpenAI embedding ({len(query_embedding)} dims) for query")
        except Exception as e:
            logger.error(f"Failed to generate OpenAI embedding: {e}. Vector search disabled.", exc_info=True)
            return []

        # 필터 구성
        tier_str = "tier1" if tier == 1 else "tier2"
        evidence_levels = None
        if input_data.min_evidence_level:
            evidence_levels = self._get_acceptable_levels(input_data.min_evidence_level)

        # Neo4j 벡터 검색 수행 (동기 래퍼 사용)
        try:
            import asyncio
            # 이미 이벤트 루프가 있는지 확인
            try:
                loop = asyncio.get_running_loop()
                # 이벤트 루프가 있으면 run_until_complete 사용 불가
                # asyncio.create_task 또는 다른 방법 필요
                raw_results = asyncio.get_event_loop().run_until_complete(
                    self.neo4j_client.vector_search_chunks(
                        embedding=query_embedding,
                        top_k=top_k,
                        tier=tier_str,
                        evidence_levels=evidence_levels,
                        min_year=input_data.min_year,
                        min_score=0.5
                    )
                )
            except RuntimeError:
                # 이벤트 루프가 없으면 새로 생성
                raw_results = asyncio.run(
                    self.neo4j_client.vector_search_chunks(
                        embedding=query_embedding,
                        top_k=top_k,
                        tier=tier_str,
                        evidence_levels=evidence_levels,
                        min_year=input_data.min_year,
                        min_score=0.5
                    )
                )
        except Exception as e:
            logger.error(f"Neo4j vector search failed: {e}", exc_info=True)
            return []

        # 결과 변환
        results = []
        for raw in raw_results:
            # evidence_level 변환 (비표준 값은 LEVEL_5로 처리)
            try:
                evidence_level = EvidenceLevel(raw.get("evidence_level", "5"))
            except ValueError:
                evidence_level = EvidenceLevel.LEVEL_5

            chunk = ChunkInfo(
                chunk_id=raw.get("chunk_id", ""),
                document_id=raw.get("paper_id", ""),
                text=raw.get("content", ""),
                tier=tier,
                section=raw.get("section", "other"),
                source_type=SourceType.ORIGINAL,  # Neo4j Chunk는 기본적으로 original
                evidence_level=evidence_level,
                publication_year=raw.get("paper_year") or 2020,
                title=raw.get("paper_title"),
                authors=None
            )

            results.append(SearchResult(
                chunk=chunk,
                score=raw.get("score", 0.0),
                tier=tier,
                source_type=chunk.source_type.value,
                evidence_level=chunk.evidence_level.value,
                search_source=SearchSource.VECTOR,
                vector_score=raw.get("score", 0.0)
            ))

        logger.info(f"Neo4j vector search: {len(results)} results for tier{tier}")
        return results

    def _neo4j_hybrid_search(
        self,
        input_data: SearchInput,
        tier: int,
        top_k: int
    ) -> list[SearchResult]:
        """Neo4j 통합 하이브리드 검색 (v1.14.17).

        Neo4j의 hybrid_search() 메서드를 사용하여
        그래프 필터링 + 벡터 검색을 단일 Cypher 쿼리로 수행.

        Args:
            input_data: 검색 입력
            tier: 계층 (1 또는 2)
            top_k: 반환할 결과 수

        Returns:
            하이브리드 검색 결과
        """
        if not self.neo4j_client:
            logger.warning("Neo4j client not available for hybrid search")
            return []

        # 쿼리 임베딩 생성
        try:
            if not OPENAI_AVAILABLE:
                logger.error("openai package not installed - required for hybrid search (3072d index)")
                return []
            if self._openai_client is None:
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    logger.error("OPENAI_API_KEY not set - required for hybrid search (3072d index)")
                    return []
                self._openai_client = openai.OpenAI(api_key=api_key)
            response = self._openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=input_data.query,
                dimensions=3072
            )
            query_embedding = response.data[0].embedding
            logger.debug(f"Generated OpenAI embedding ({len(query_embedding)} dims) for hybrid search")
        except Exception as e:
            logger.error(f"Failed to generate OpenAI embedding for hybrid search: {e}", exc_info=True)
            return []

        # 그래프 필터 구성
        graph_filters: dict = {}

        # Evidence level 필터
        if input_data.min_evidence_level:
            graph_filters["evidence_levels"] = self._get_acceptable_levels(input_data.min_evidence_level)

        # 연도 필터
        if input_data.min_year:
            graph_filters["min_year"] = input_data.min_year

        # 엔티티에서 intervention, pathology, snomed_codes 추출
        snomed_codes: list[str] = []
        if input_data.entities:
            for entity in input_data.entities:
                if hasattr(entity, 'entity_type'):
                    entity_type = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
                    if entity_type in ['PROCEDURE', 'INTERVENTION', 'intervention', 'procedure']:
                        graph_filters.setdefault("_interventions_list", []).append(entity.text)
                        graph_filters["intervention"] = entity.text  # 단일값 폴백
                    elif entity_type in ['CONDITION', 'PATHOLOGY', 'pathology', 'disease']:
                        graph_filters.setdefault("_pathologies_list", []).append(entity.text)
                        graph_filters["pathology"] = entity.text
                    elif entity_type in ['SYMPTOM', 'OUTCOME', 'outcome', 'measurement', 'symptom']:
                        graph_filters.setdefault("_outcomes_list", []).append(entity.text)
                        graph_filters["outcome"] = entity.text
                    elif entity_type in ['ANATOMY', 'anatomy']:
                        graph_filters.setdefault("_anatomies_list", []).append(entity.text)
                        graph_filters["anatomy"] = entity.text
                # Collect SNOMED codes from entities for IS_A expansion
                if hasattr(entity, 'snomed_id') and entity.snomed_id:
                    snomed_codes.append(entity.snomed_id)

        # Also collect from ParsedQuery.snomed_codes dict (entity_text -> code)
        if not snomed_codes and input_data.parsed_query and input_data.parsed_query.snomed_codes:
            snomed_codes = list(input_data.parsed_query.snomed_codes.values())

        # 다중 entity 수집 리스트 → plural 필터로 승격 (IS_A 확장 전)
        for _list_key, _singular, _plural in [
            ("_interventions_list", "intervention", "interventions"),
            ("_pathologies_list", "pathology", "pathologies"),
            ("_outcomes_list", "outcome", "outcomes"),
            ("_anatomies_list", "anatomy", "anatomies"),
        ]:
            collected = graph_filters.pop(_list_key, None)
            if collected and len(collected) > 1:
                graph_filters[_plural] = collected
                graph_filters.pop(_singular, None)

        # IS_A hierarchy expansion via GraphContextExpander
        if self.context_expander:
            try:
                import asyncio
                _expand_tasks = []
                if graph_filters.get("intervention"):
                    _expand_tasks.append(("intervention", graph_filters["intervention"], "Intervention"))
                if graph_filters.get("pathology"):
                    _expand_tasks.append(("pathology", graph_filters["pathology"], "Pathology"))
                if graph_filters.get("outcome"):
                    _expand_tasks.append(("outcome", graph_filters["outcome"], "Outcome"))
                if graph_filters.get("anatomy"):
                    _expand_tasks.append(("anatomy", graph_filters["anatomy"], "Anatomy"))
                for _key, _name, _type in _expand_tasks:
                    try:
                        variants = asyncio.get_event_loop().run_until_complete(
                            self.context_expander.expand_by_ontology(_name, _type, depth=2)
                        )
                    except RuntimeError:
                        variants = asyncio.run(
                            self.context_expander.expand_by_ontology(_name, _type, depth=2)
                        )
                    if variants and len(variants) > 1:
                        plural_key = f"{_key[:-1]}ies" if _key.endswith("y") else f"{_key}s"
                        graph_filters[plural_key] = variants
                        del graph_filters[_key]
                        logger.info(f"IS_A expanded {_key} '{_name}' -> {len(variants)} variants: {variants[:5]}")
            except Exception as e:
                logger.warning(f"IS_A expansion failed, using original filters: {e}")

        # Neo4j hybrid_search 수행 (동기 래퍼)
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                raw_results = asyncio.get_event_loop().run_until_complete(
                    self.neo4j_client.hybrid_search(
                        embedding=query_embedding,
                        graph_filters=graph_filters if graph_filters else None,
                        top_k=top_k,
                        graph_weight=self.graph_weight,
                        vector_weight=self.vector_weight,
                        snomed_codes=snomed_codes or None,
                    )
                )
            except RuntimeError:
                raw_results = asyncio.run(
                    self.neo4j_client.hybrid_search(
                        embedding=query_embedding,
                        graph_filters=graph_filters if graph_filters else None,
                        top_k=top_k,
                        graph_weight=self.graph_weight,
                        vector_weight=self.vector_weight,
                        snomed_codes=snomed_codes or None,
                    )
                )
        except Exception as e:
            logger.error(f"Neo4j hybrid search failed: {e}", exc_info=True)
            return []

        # 결과 변환
        results = []
        for raw in raw_results:
            # Tier 필터링 (hybrid_search는 tier 필터가 없으므로 여기서 필터)
            chunk_tier = raw.get("tier", "tier1")
            tier_num = 1 if chunk_tier == "tier1" else 2
            if tier_num != tier:
                continue

            # evidence_level 변환
            try:
                evidence_level = EvidenceLevel(raw.get("evidence_level", "5"))
            except ValueError:
                evidence_level = EvidenceLevel.LEVEL_5

            chunk = ChunkInfo(
                chunk_id=raw.get("chunk_id", ""),
                document_id=raw.get("paper_id", ""),
                text=raw.get("content", ""),
                tier=tier,
                section=raw.get("section", "other"),
                source_type=SourceType.ORIGINAL,
                evidence_level=evidence_level,
                publication_year=raw.get("year") or 2020,
                title=raw.get("paper_title"),
                authors=None
            )

            # 벡터 점수와 그래프 점수가 모두 있으므로 BOTH로 표시
            results.append(SearchResult(
                chunk=chunk,
                score=raw.get("final_score", 0.0),
                tier=tier,
                source_type=chunk.source_type.value,
                evidence_level=chunk.evidence_level.value,
                search_source=SearchSource.BOTH,  # 그래프+벡터 통합
                vector_score=raw.get("vector_score", 0.0),
                graph_score=raw.get("graph_score", 0.0)
            ))

        logger.info(f"Neo4j hybrid search: {len(results)} results for tier{tier} (filters: {list(graph_filters.keys())})")
        return results

    def _graph_search(
        self,
        input_data: SearchInput,
        tier: int,
        top_k: int
    ) -> list[SearchResult]:
        """그래프 검색.

        Args:
            input_data: 검색 입력
            tier: 계층
            top_k: 반환할 결과 수

        Returns:
            그래프 검색 결과
        """
        if not self.graph_db or not input_data.entities:
            return []

        # 엔티티 텍스트 추출
        entity_texts = [e.text for e in input_data.entities]

        # 그래프 검색 수행
        raw_results = self.graph_db.search_by_entities(
            entities=entity_texts,
            top_k=top_k,
            max_hops=2
        )

        # Tier 필터링
        filtered_results = [r for r in raw_results if r.get("tier", 1) == tier]

        # 결과 변환
        results = []
        for raw in filtered_results[:top_k]:
            chunk = ChunkInfo(
                chunk_id=raw.get("id", ""),
                document_id=raw.get("document_id", ""),
                text=raw.get("text", ""),
                tier=tier,
                section=raw.get("section", "other"),
                source_type=SourceType(raw.get("source_type", "original")),
                evidence_level=EvidenceLevel(raw.get("evidence_level", "5")),
                publication_year=raw.get("publication_year", 2020),
                title=raw.get("title"),
                authors=raw.get("authors")
            )

            results.append(SearchResult(
                chunk=chunk,
                score=raw.get("score", 0.0),
                tier=tier,
                source_type=chunk.source_type.value,
                evidence_level=chunk.evidence_level.value,
                search_source=SearchSource.GRAPH,
                graph_score=raw.get("score", 0.0)
            ))

        return results

    def _fuse_results(
        self,
        vector_results: list[SearchResult],
        graph_results: list[SearchResult],
        top_k: int
    ) -> list[SearchResult]:
        """벡터와 그래프 검색 결과 융합 (Weighted RRF).

        Args:
            vector_results: 벡터 검색 결과
            graph_results: 그래프 검색 결과
            top_k: 반환할 결과 수

        Returns:
            융합된 결과
        """
        # 청크 ID로 점수 매핑
        scores: dict[str, float] = {}
        chunk_map: dict[str, SearchResult] = {}

        # 벡터 결과 RRF 점수
        for rank, result in enumerate(vector_results):
            chunk_id = result.chunk.chunk_id
            rrf_score = self.vector_weight / (self.rrf_k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score
            chunk_map[chunk_id] = result

        # 그래프 결과 RRF 점수
        for rank, result in enumerate(graph_results):
            chunk_id = result.chunk.chunk_id
            rrf_score = self.graph_weight / (self.rrf_k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score

            if chunk_id in chunk_map:
                # 양쪽에서 발견된 경우
                chunk_map[chunk_id].search_source = SearchSource.BOTH
                chunk_map[chunk_id].graph_score = result.graph_score
            else:
                chunk_map[chunk_id] = result

        # 점수순 정렬
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # 결과 구성
        results = []
        for chunk_id in sorted_ids[:top_k]:
            result = chunk_map[chunk_id]
            result.score = scores[chunk_id]
            results.append(result)

        return results

    def _merge_results_rrf(
        self,
        tier1_results: list[SearchResult],
        tier2_results: list[SearchResult],
        top_k: int
    ) -> list[SearchResult]:
        """Tier 1과 Tier 2 결과 병합 (RRF).

        Args:
            tier1_results: Tier 1 결과
            tier2_results: Tier 2 결과
            top_k: 반환할 결과 수

        Returns:
            병합된 결과
        """
        # Tier 1에 더 높은 가중치
        tier1_weight = 0.6
        tier2_weight = 0.4

        scores: dict[str, float] = {}
        chunk_map: dict[str, SearchResult] = {}

        for rank, result in enumerate(tier1_results):
            chunk_id = result.chunk.chunk_id
            rrf_score = tier1_weight / (self.rrf_k + rank + 1)
            scores[chunk_id] = rrf_score
            chunk_map[chunk_id] = result

        for rank, result in enumerate(tier2_results):
            chunk_id = result.chunk.chunk_id
            rrf_score = tier2_weight / (self.rrf_k + rank + 1)
            scores[chunk_id] = scores.get(chunk_id, 0) + rrf_score
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = result

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        results = []
        for chunk_id in sorted_ids[:top_k]:
            result = chunk_map[chunk_id]
            result.score = scores[chunk_id]
            results.append(result)

        return results

    def _prioritize_original(
        self,
        results: list[SearchResult]
    ) -> list[SearchResult]:
        """원본 콘텐츠 우선 정렬.

        Args:
            results: 검색 결과

        Returns:
            정렬된 결과
        """
        # 원본 vs 인용/배경 분리
        original = [r for r in results if r.source_type == "original"]
        others = [r for r in results if r.source_type != "original"]

        # 각 그룹 내에서 점수순 정렬
        original.sort(key=lambda x: x.score, reverse=True)
        others.sort(key=lambda x: x.score, reverse=True)

        # 원본 우선 결합 (같은 점수 범위면 원본이 먼저)
        return original + others

    def _filter_by_evidence(
        self,
        results: list[SearchResult],
        min_level: str
    ) -> list[SearchResult]:
        """Evidence Level 필터링.

        Args:
            results: 검색 결과
            min_level: 최소 레벨

        Returns:
            필터링된 결과
        """
        acceptable = self._get_acceptable_levels(min_level)
        return [r for r in results if r.evidence_level in acceptable]

    def _get_acceptable_levels(self, min_level: str) -> list[str]:
        """최소 레벨 이상의 허용 레벨 목록.

        Args:
            min_level: 최소 레벨

        Returns:
            허용 레벨 목록
        """
        try:
            idx: int = self.EVIDENCE_ORDER.index(min_level)
            return self.EVIDENCE_ORDER[:idx + 1]
        except ValueError:
            return self.EVIDENCE_ORDER

    def _filter_by_year(
        self,
        results: list[SearchResult],
        min_year: int
    ) -> list[SearchResult]:
        """연도 필터링.

        Args:
            results: 검색 결과
            min_year: 최소 연도

        Returns:
            필터링된 결과
        """
        return [r for r in results if r.chunk.publication_year >= min_year]


class MockVectorDB:
    """테스트용 Mock 벡터 DB."""

    def __init__(self, data: Optional[list[dict[str, Any]]] = None) -> None:
        """초기화."""
        self.data: list[dict[str, Any]] = data or []

    def search(
        self,
        query_embedding: list[float],
        collection: str,
        top_k: int,
        filters: Optional[dict[str, Any]] = None
    ) -> list[dict[str, Any]]:
        """Mock 검색."""
        # Tier 필터링
        tier: int = 1 if "tier1" in collection else 2
        filtered: list[dict[str, Any]] = [d for d in self.data if d.get("tier", 1) == tier]

        # 추가 필터링
        if filters:
            if "evidence_level" in filters:
                acceptable: list[str] = filters["evidence_level"].get("$in", [])
                filtered = [d for d in filtered if d.get("evidence_level") in acceptable]
            if "publication_year" in filters:
                min_year: int = filters["publication_year"].get("$gte", 0)
                filtered = [d for d in filtered if d.get("publication_year", 0) >= min_year]

        return filtered[:top_k]

    def get_embedding(self, text: str) -> list[float]:
        """Mock 임베딩 (v1.14.26: 3072d로 변경 - Neo4j 인덱스와 일치)."""
        return [0.1] * 3072  # 가상의 3072차원 임베딩 (OpenAI text-embedding-3-large)


class MockGraphDB:
    """테스트용 Mock 그래프 DB."""

    def __init__(self, data: Optional[list[dict[str, Any]]] = None) -> None:
        """초기화."""
        self.data: list[dict[str, Any]] = data or []

    def search_by_entities(
        self,
        entities: list[str],
        top_k: int,
        max_hops: int = 2
    ) -> list[dict[str, Any]]:
        """Mock 엔티티 검색."""
        # 간단히 엔티티와 매칭되는 결과 반환
        results: list[dict[str, Any]] = []
        for doc in self.data:
            text: str = doc.get("text", "").lower()
            for entity in entities:
                if entity.lower() in text:
                    results.append(doc)
                    break

        return results[:top_k]

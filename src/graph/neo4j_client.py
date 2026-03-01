"""Neo4j Client for Spine GraphRAG.

Neo4j 데이터베이스 연결 및 쿼리 관리.
- 연결 풀 관리
- 비동기 쿼리 지원
- 트랜잭션 관리
- 스키마 초기화
- Circuit breaker for connection resilience
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file automatically (v1.14.30)
try:
    from dotenv import load_dotenv
    # Find .env from project root
    _current_dir = Path(__file__).resolve().parent
    _project_root = _current_dir.parent.parent  # src/graph -> src -> project_root
    _env_path = _project_root / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # dotenv not installed, rely on system environment

# Neo4j driver (optional import)
try:
    from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
    from neo4j.exceptions import ServiceUnavailable, AuthError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    AsyncGraphDatabase = None
    AsyncDriver = None
    AsyncSession = None

try:
    from openai import OpenAI as _OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    _OpenAI = None  # type: ignore

from .spine_schema import SpineGraphSchema, PaperNode, ChunkNode, CypherTemplates
from .relationship_dao import RelationshipDAO
from .schema_manager import SchemaManager
from .search_dao import SearchDAO
from core.exceptions import ValidationError, ErrorCode

# Import error handling
try:
    from ..core.error_handler import (
        CircuitBreaker,
        CircuitBreakerConfig,
        Neo4jConnectionError,
        with_retry,
        RetryConfig,
    )
    ERROR_HANDLER_AVAILABLE = True
except ImportError:
    ERROR_HANDLER_AVAILABLE = False
    CircuitBreaker = None
    Neo4jConnectionError = Exception

logger = logging.getLogger(__name__)


@dataclass
class Neo4jConfig:
    """Neo4j 연결 설정."""
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = field(default="password", repr=False)
    database: str = "neo4j"
    max_connection_lifetime: int = 3600
    max_connection_pool_size: int = 50
    connection_timeout: int = 30

    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """환경변수에서 설정 로드."""
        return cls(
            uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            username=os.environ.get("NEO4J_USERNAME", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", "password"),
            database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        )


class Neo4jClient:
    """Neo4j 비동기 클라이언트.

    사용 예:
        async with Neo4jClient() as client:
            await client.initialize_schema()
            result = await client.run_query("MATCH (n) RETURN n LIMIT 10")
    """

    def __init__(self, config: Optional[Neo4jConfig] = None):
        """초기화.

        Args:
            config: Neo4j 연결 설정 (None이면 환경변수에서 로드)
        """
        if not NEO4J_AVAILABLE:
            logger.warning("neo4j package not installed. Running in mock mode.")
            self._mock_mode = True
            self._driver = None
            self.config = config or Neo4jConfig()
            self._circuit_breaker = None
            self._openai_client = None
            self.schema_mgr = SchemaManager(self.run_query, self.run_write_query)
            self.relationships = RelationshipDAO(self.run_query, self.run_write_query)
            self.search = SearchDAO(self.run_query)
            return

        self._mock_mode = False
        self.config = config or Neo4jConfig.from_env()
        self._driver: Optional[AsyncDriver] = None
        self._initialized = False
        self._openai_client = None  # Lazy-initialized OpenAI client for embeddings

        # Initialize circuit breaker if available
        if ERROR_HANDLER_AVAILABLE:
            self._circuit_breaker = CircuitBreaker(
                name="neo4j",
                config=CircuitBreakerConfig(
                    failure_threshold=5,
                    success_threshold=2,
                    timeout=30.0,  # 30 seconds before retry
                )
            )
        else:
            self._circuit_breaker = None

        # DAO delegates
        self.schema_mgr = SchemaManager(self.run_query, self.run_write_query)
        self.relationships = RelationshipDAO(self.run_query, self.run_write_query)
        self.search = SearchDAO(self.run_query)

    async def connect(self) -> None:
        """Neo4j 연결."""
        if self._mock_mode:
            logger.info("Neo4j mock mode - skipping connection")
            return

        if self._driver is not None:
            return

        try:
            self._driver = AsyncGraphDatabase.driver(
                self.config.uri,
                auth=(self.config.username, self.config.password),
                max_connection_lifetime=self.config.max_connection_lifetime,
                max_connection_pool_size=self.config.max_connection_pool_size,
                connection_timeout=self.config.connection_timeout,
            )

            # 연결 테스트
            async with self._driver.session(database=self.config.database) as session:
                result = await session.run("RETURN 1 as test")
                record = await result.single()
                if record and record["test"] == 1:
                    logger.info(f"Connected to Neo4j: {self.config.uri}")

        except AuthError as e:
            logger.error(f"Neo4j authentication failed: {e}", exc_info=True)
            raise
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Neo4j connection error: {e}", exc_info=True)
            raise

    async def close(self) -> None:
        """연결 종료."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    async def __aenter__(self) -> "Neo4jClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        """세션 컨텍스트 매니저.

        Properly handles exceptions to avoid masking the original error
        if session.close() also raises an exception.
        """
        if self._mock_mode:
            yield MockSession()
            return

        if self._driver is None:
            await self.connect()

        session = self._driver.session(database=self.config.database)
        exc_to_raise = None
        try:
            yield session
        except Exception as e:
            exc_to_raise = e
            raise
        finally:
            try:
                await session.close()
            except Exception as close_error:
                # Log close error but don't mask the original exception
                logger.warning(f"Error closing session: {close_error}")
                if exc_to_raise is None:
                    # Only raise close error if no other exception occurred
                    raise

    async def run_query(
        self,
        query: str,
        parameters: Optional[dict] = None,
        fetch_all: bool = True
    ) -> list[dict]:
        """쿼리 실행.

        Args:
            query: Cypher 쿼리
            parameters: 쿼리 파라미터
            fetch_all: 모든 결과 가져오기 (False면 첫 번째만)

        Returns:
            결과 레코드 목록

        Raises:
            Neo4jConnectionError: Connection or query failure
        """
        if self._mock_mode:
            logger.debug(f"Mock query: {query[:100]}...")
            return []

        async def _execute_query():
            async with self.session() as session:
                try:
                    result = await session.run(query, parameters or {})

                    if fetch_all:
                        records = await result.data()
                        return records
                    else:
                        record = await result.single()
                        return [dict(record)] if record else []

                except ServiceUnavailable as e:
                    if ERROR_HANDLER_AVAILABLE:
                        raise Neo4jConnectionError(f"Neo4j service unavailable: {e}")
                    raise
                except Exception as e:
                    logger.error(f"Query execution failed: {e}", exc_info=True)
                    raise

        # Use circuit breaker if available
        if self._circuit_breaker:
            try:
                return await self._circuit_breaker.call(_execute_query)
            except Exception as e:
                logger.error(f"Circuit breaker protected query failed: {e}", exc_info=True)
                raise
        else:
            return await _execute_query()

    async def run_write_query(
        self,
        query: str,
        parameters: Optional[dict] = None
    ) -> dict:
        """쓰기 쿼리 실행 (트랜잭션).

        Args:
            query: Cypher 쿼리
            parameters: 쿼리 파라미터

        Returns:
            쿼리 결과 요약
        """
        if self._mock_mode:
            logger.debug(f"Mock write query: {query[:100]}...")
            return {"mock": True}

        async with self.session() as session:
            async def _write_tx(tx):
                result = await tx.run(query, parameters or {})
                summary = await result.consume()
                return {
                    "nodes_created": summary.counters.nodes_created,
                    "nodes_deleted": summary.counters.nodes_deleted,
                    "relationships_created": summary.counters.relationships_created,
                    "relationships_deleted": summary.counters.relationships_deleted,
                    "properties_set": summary.counters.properties_set,
                }

            return await session.execute_write(_write_tx)

    async def initialize_schema(self) -> None:
        """스키마 초기화 (제약 조건, 인덱스)."""
        if self._mock_mode:
            logger.info("Mock mode - skipping schema initialization")
            return
        await self.schema_mgr.initialize_schema()
        self._initialized = self.schema_mgr._initialized

    # ========================================================================
    # Paper Operations
    # ========================================================================

    async def create_paper(
        self,
        paper: PaperNode,
        generate_embedding: bool = True
    ) -> dict:
        """논문 노드 생성.

        Args:
            paper: PaperNode 객체
            generate_embedding: True면 abstract_embedding 자동 생성 (기본 True)

        Returns:
            생성 결과
        """
        # Paper 노드 생성
        result = await self.run_write_query(
            CypherTemplates.MERGE_PAPER,
            {
                "paper_id": paper.paper_id,
                "properties": paper.to_neo4j_properties(),
            }
        )

        # Abstract 임베딩 자동 생성
        if generate_embedding and paper.abstract and len(paper.abstract.strip()) > 0:
            await self._generate_paper_abstract_embedding(paper.paper_id, paper.abstract)

        return result

    async def _generate_paper_abstract_embedding(
        self,
        paper_id: str,
        abstract: str
    ) -> bool:
        """Paper의 abstract 임베딩 생성 및 저장.

        Args:
            paper_id: Paper ID
            abstract: Abstract 텍스트

        Returns:
            성공 여부
        """
        try:
            if not OPENAI_AVAILABLE:
                logger.warning("OpenAI package not installed, skipping abstract embedding")
                return False

            if self._openai_client is None:
                self._openai_client = _OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            # OpenAI 임베딩 생성 (3072차원)
            response = self._openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=abstract[:8000],  # 최대 길이 제한
                dimensions=3072
            )

            embedding = response.data[0].embedding

            # Neo4j에 임베딩 저장
            await self.run_write_query(
                """
                MATCH (p:Paper {paper_id: $paper_id})
                SET p.abstract_embedding = $embedding
                """,
                {"paper_id": paper_id, "embedding": embedding}
            )

            logger.debug(f"Abstract embedding generated for {paper_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to generate abstract embedding for {paper_id}: {e}")
            return False

    async def get_paper(self, paper_id: str) -> Optional[dict]:
        """논문 조회.

        Args:
            paper_id: 논문 ID

        Returns:
            논문 정보 또는 None
        """
        results = await self.run_query(
            "MATCH (p:Paper {paper_id: $paper_id}) RETURN p",
            {"paper_id": paper_id},
            fetch_all=False
        )
        return results[0] if results else None

    async def list_papers(
        self,
        sub_domain: Optional[str] = None,
        evidence_level: Optional[str] = None,
        limit: int = 100
    ) -> list[dict]:
        """논문 목록 조회."""
        query = "MATCH (p:Paper) WHERE 1=1"
        params: dict[str, Any] = {"limit": limit}

        if sub_domain:
            query += " AND p.sub_domain = $sub_domain"
            params["sub_domain"] = sub_domain

        if evidence_level:
            query += " AND p.evidence_level = $evidence_level"
            params["evidence_level"] = evidence_level

        query += " RETURN p ORDER BY p.year DESC LIMIT $limit"

        return await self.run_query(query, params)

    async def get_all_papers(self, limit: int = 100) -> list[dict]:
        """모든 논문 조회 (list_papers alias).

        Args:
            limit: 최대 반환 개수

        Returns:
            논문 정보 목록
        """
        return await self.list_papers(limit=limit)

    async def get_all_papers_with_relations(self, limit: int = 100) -> list[dict]:
        """관계 정보를 포함한 모든 논문 조회 (SIMILAR_TOPIC 계산용).

        pathologies, interventions, anatomy_levels를 함께 반환하여
        유사도 계산에 사용할 수 있도록 함.

        Args:
            limit: 최대 반환 개수

        Returns:
            논문 정보 목록 (관계 정보 포함)
        """
        query = """
        MATCH (p:Paper)
        OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
        OPTIONAL MATCH (p)-[:INVESTIGATES]->(int:Intervention)
        OPTIONAL MATCH (p)-[:INVOLVES]->(anat:Anatomy)
        WITH p,
             collect(DISTINCT path.name) AS pathologies,
             collect(DISTINCT int.name) AS interventions,
             collect(DISTINCT anat.name) AS anatomy_levels
        RETURN p.paper_id AS paper_id,
               p.title AS title,
               p.sub_domain AS sub_domain,
               p.sub_domains AS sub_domains,
               p.surgical_approach AS surgical_approach,
               pathologies,
               interventions,
               anatomy_levels
        ORDER BY p.year DESC
        LIMIT $limit
        """
        results = await self.run_query(query, {"limit": limit})

        # null 값 처리
        papers = []
        for r in results:
            papers.append({
                "paper_id": r.get("paper_id"),
                "title": r.get("title"),
                "sub_domain": r.get("sub_domain") or "",
                "sub_domains": r.get("sub_domains") or [],
                "surgical_approach": r.get("surgical_approach") or [],
                "pathologies": [p for p in (r.get("pathologies") or []) if p],
                "interventions": [i for i in (r.get("interventions") or []) if i],
                "anatomy_levels": [a for a in (r.get("anatomy_levels") or []) if a],
            })
        return papers

    # ========================================================================
    # Chunk Operations (v5.3 - Neo4j Vector Index)
    # ========================================================================

    async def create_chunk(self, chunk: ChunkNode) -> dict:
        """청크 노드 생성.

        Args:
            chunk: ChunkNode 객체

        Returns:
            생성 결과
        """
        query = """
        MERGE (c:Chunk {chunk_id: $chunk_id})
        SET c += $properties
        RETURN c
        """
        return await self.run_write_query(
            query,
            {
                "chunk_id": chunk.chunk_id,
                "properties": chunk.to_neo4j_properties(),
            }
        )

    async def create_has_chunk_relation(
        self,
        paper_id: str,
        chunk_id: str,
        chunk_index: int = 0
    ) -> dict:
        """Paper → Chunk 관계 생성.

        Args:
            paper_id: 논문 ID
            chunk_id: 청크 ID
            chunk_index: 청크 순서

        Returns:
            생성 결과
        """
        query = """
        MATCH (p:Paper {paper_id: $paper_id})
        MATCH (c:Chunk {chunk_id: $chunk_id})
        MERGE (p)-[r:HAS_CHUNK]->(c)
        SET r.chunk_index = $chunk_index
        RETURN r
        """
        return await self.run_write_query(
            query,
            {
                "paper_id": paper_id,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
            }
        )

    async def create_chunks_batch(
        self,
        paper_id: str,
        chunks: list[ChunkNode]
    ) -> dict:
        """청크 일괄 생성 (트랜잭션).

        Args:
            paper_id: 논문 ID
            chunks: ChunkNode 리스트

        Returns:
            생성 결과 (created_count)
        """
        if not chunks:
            return {"created_count": 0}

        query = """
        UNWIND $chunks AS chunk_data
        MERGE (c:Chunk {chunk_id: chunk_data.chunk_id})
        SET c += chunk_data.properties
        WITH c, chunk_data
        MATCH (p:Paper {paper_id: $paper_id})
        MERGE (p)-[r:HAS_CHUNK]->(c)
        SET r.chunk_index = chunk_data.chunk_index
        RETURN count(c) as created_count
        """

        chunks_data = [
            {
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "properties": chunk.to_neo4j_properties(),
            }
            for chunk in chunks
        ]

        return await self.run_write_query(
            query,
            {"paper_id": paper_id, "chunks": chunks_data}
        )

    async def get_paper_chunks(
        self,
        paper_id: str,
        tier: Optional[str] = None,
        section: Optional[str] = None
    ) -> list[dict]:
        """논문의 청크 조회.

        Args:
            paper_id: 논문 ID
            tier: 필터링할 티어 ("tier1" | "tier2")
            section: 필터링할 섹션

        Returns:
            청크 정보 리스트
        """
        query = """
        MATCH (p:Paper {paper_id: $paper_id})-[:HAS_CHUNK]->(c:Chunk)
        WHERE 1=1
        """
        params: dict[str, Any] = {"paper_id": paper_id}

        if tier:
            query += " AND c.tier = $tier"
            params["tier"] = tier

        if section:
            query += " AND c.section = $section"
            params["section"] = section

        query += " RETURN c ORDER BY c.chunk_index"

        return await self.run_query(query, params)

    async def delete_chunk(self, chunk_id: str) -> dict:
        """청크 노드 삭제.

        Args:
            chunk_id: 청크 ID

        Returns:
            삭제 결과
        """
        query = """
        MATCH (c:Chunk {chunk_id: $chunk_id})
        DETACH DELETE c
        """
        return await self.run_write_query(query, {"chunk_id": chunk_id})

    async def delete_paper_chunks(self, paper_id: str) -> dict:
        """논문의 모든 청크 삭제.

        Args:
            paper_id: 논문 ID

        Returns:
            삭제 결과
        """
        query = """
        MATCH (p:Paper {paper_id: $paper_id})-[:HAS_CHUNK]->(c:Chunk)
        DETACH DELETE c
        """
        result = await self.run_write_query(query, {"paper_id": paper_id})
        logger.info(f"Deleted chunks for paper {paper_id}: {result.get('nodes_deleted', 0)} nodes")
        return result

    async def vector_search_chunks(
        self,
        embedding: list[float],
        top_k: int = 10,
        tier: Optional[str] = None,
        evidence_level: Optional[str] = None,
        evidence_levels: Optional[list[str]] = None,
        min_year: Optional[int] = None,
        min_score: float = 0.5
    ) -> list[dict]:
        """벡터 유사도 기반 청크 검색. Delegates to SearchDAO."""
        return await self.search.vector_search_chunks(
            embedding=embedding, top_k=top_k, tier=tier,
            evidence_level=evidence_level, evidence_levels=evidence_levels,
            min_year=min_year, min_score=min_score,
        )

    async def hybrid_search(
        self,
        embedding: list[float],
        graph_filters: Optional[dict] = None,
        top_k: int = 10,
        graph_weight: float = 0.6,
        vector_weight: float = 0.4,
        snomed_codes: Optional[list[str]] = None,
    ) -> list[dict]:
        """그래프 + 벡터 하이브리드 검색. Delegates to SearchDAO."""
        return await self.search.hybrid_search(
            embedding=embedding, graph_filters=graph_filters, top_k=top_k,
            graph_weight=graph_weight, vector_weight=vector_weight,
            snomed_codes=snomed_codes,
        )

    async def get_chunk_count(self, paper_id: Optional[str] = None) -> int:
        """청크 수 조회.

        Args:
            paper_id: 논문 ID (None이면 전체 청크)

        Returns:
            청크 수
        """
        if paper_id:
            query = """
            MATCH (p:Paper {paper_id: $paper_id})-[:HAS_CHUNK]->(c:Chunk)
            RETURN count(c) as count
            """
            params = {"paper_id": paper_id}
        else:
            query = "MATCH (c:Chunk) RETURN count(c) as count"
            params = {}

        result = await self.run_query(query, params, fetch_all=False)
        return result[0].get("count", 0) if result else 0

    # ========================================================================
    # Relationship Operations
    # ========================================================================

    async def create_studies_relation(
        self,
        paper_id: str,
        pathology_name: str,
        is_primary: bool = True,
        snomed_code: Optional[str] = None,
        snomed_term: Optional[str] = None
    ) -> dict:
        """논문 -> 질환 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_studies_relation(
            paper_id, pathology_name, is_primary, snomed_code, snomed_term
        )

    async def create_investigates_relation(
        self,
        paper_id: str,
        intervention_name: str,
        is_comparison: bool = False,
        category: Optional[str] = None,
        snomed_code: Optional[str] = None,
        snomed_term: Optional[str] = None
    ) -> dict:
        """논문 -> 수술법 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_investigates_relation(
            paper_id, intervention_name, is_comparison, category, snomed_code, snomed_term
        )

    async def create_affects_relation(
        self,
        intervention_name: str,
        outcome_name: str,
        source_paper_id: str,
        value: str = "",
        value_control: str = "",
        p_value: Optional[float] = None,
        effect_size: str = "",
        confidence_interval: str = "",
        is_significant: bool = False,
        direction: str = "",
        baseline: Optional[float] = None,
        final: Optional[float] = None,
        value_intervention: str = "",
        value_difference: str = "",
        category: str = "",
        timepoint: str = "",
        snomed_code: Optional[str] = None,
        snomed_term: Optional[str] = None
    ) -> dict:
        """수술법 -> 결과 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_affects_relation(
            intervention_name=intervention_name,
            outcome_name=outcome_name,
            source_paper_id=source_paper_id,
            value=value,
            value_control=value_control,
            p_value=p_value,
            effect_size=effect_size,
            confidence_interval=confidence_interval,
            is_significant=is_significant,
            direction=direction,
            baseline=baseline,
            final=final,
            value_intervention=value_intervention,
            value_difference=value_difference,
            category=category,
            timepoint=timepoint,
            snomed_code=snomed_code,
            snomed_term=snomed_term,
        )

    async def create_treats_relation(
        self,
        intervention_name: str,
        pathology_name: str,
        source_paper_id: str = "",
        indication: str = "",
        contraindication: str = "",
        indication_level: str = "",
    ) -> dict:
        """수술법 -> 질환 치료 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_treats_relation(
            intervention_name, pathology_name, source_paper_id,
            indication, contraindication, indication_level,
        )

    async def create_involves_relation(
        self,
        paper_id: str,
        anatomy_name: str,
        level: str = "",
        region: str = "",
        snomed_code: str | None = None,
        snomed_term: str | None = None,
    ) -> dict:
        """논문 -> 해부학 위치 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_involves_relation(
            paper_id, anatomy_name, level, region, snomed_code, snomed_term,
        )

    # ========================================================================
    # Paper-to-Paper Relationship Operations
    # ========================================================================

    async def create_paper_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str,
        confidence: float = 0.0,
        evidence: str = "",
        detected_by: str = ""
    ) -> bool:
        """논문 간 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_paper_relation(
            source_paper_id, target_paper_id, relation_type,
            confidence, evidence, detected_by,
        )

    async def create_supports_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        evidence: str = "",
        confidence: float = 0.0
    ) -> bool:
        """SUPPORTS 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_supports_relation(
            source_paper_id, target_paper_id, evidence, confidence,
        )

    async def create_contradicts_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        evidence: str = "",
        confidence: float = 0.0
    ) -> bool:
        """CONTRADICTS 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_contradicts_relation(
            source_paper_id, target_paper_id, evidence, confidence,
        )

    async def create_cites_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        citation_text: str = "",
        context: str = ""
    ) -> bool:
        """CITES 관계 생성. Delegates to RelationshipDAO."""
        return await self.relationships.create_cites_relation(
            source_paper_id, target_paper_id, citation_text, context,
        )

    async def get_paper_relations(
        self,
        paper_id: str,
        relation_types: Optional[list[str]] = None,
        direction: str = "both"
    ) -> list[dict]:
        """논문의 관계 조회. Delegates to RelationshipDAO."""
        return await self.relationships.get_paper_relations(
            paper_id, relation_types, direction,
        )

    async def get_related_papers(
        self,
        paper_id: str,
        relation_type: str,
        min_confidence: float = 0.0,
        limit: int = 10
    ) -> list[dict]:
        """특정 관계 유형의 관련 논문 조회. Delegates to RelationshipDAO."""
        return await self.relationships.get_related_papers(
            paper_id, relation_type, min_confidence, limit,
        )

    async def get_supporting_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """지지하는 논문들 조회. Delegates to RelationshipDAO."""
        return await self.relationships.get_supporting_papers(paper_id, limit)

    async def get_contradicting_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """상충하는 논문들 조회. Delegates to RelationshipDAO."""
        return await self.relationships.get_contradicting_papers(paper_id, limit)

    async def get_similar_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """유사 주제 논문들 조회. Delegates to RelationshipDAO."""
        return await self.relationships.get_similar_papers(paper_id, limit)

    async def get_citing_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """이 논문을 인용한 논문들 조회. Delegates to RelationshipDAO."""
        return await self.relationships.get_citing_papers(paper_id, limit)

    async def get_cited_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """이 논문이 인용한 논문들 조회. Delegates to RelationshipDAO."""
        return await self.relationships.get_cited_papers(paper_id, limit)

    async def delete_paper_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str
    ) -> bool:
        """논문 간 관계 삭제. Delegates to RelationshipDAO."""
        return await self.relationships.delete_paper_relation(
            source_paper_id, target_paper_id, relation_type,
        )

    async def update_paper_relation_confidence(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str,
        new_confidence: float
    ) -> bool:
        """관계 신뢰도 업데이트. Delegates to RelationshipDAO."""
        return await self.relationships.update_paper_relation_confidence(
            source_paper_id, target_paper_id, relation_type, new_confidence,
        )

    # ========================================================================
    # Search Operations
    # ========================================================================

    async def get_intervention_hierarchy(self, intervention_name: str) -> list[dict]:
        """수술법 계층 조회. Delegates to SearchDAO."""
        return await self.search.get_intervention_hierarchy(intervention_name)

    async def get_intervention_children(self, intervention_name: str) -> list[dict]:
        """수술법 하위 항목 조회. Delegates to SearchDAO."""
        return await self.search.get_intervention_children(intervention_name)

    async def search_effective_interventions(self, outcome_name: str) -> list[dict]:
        """효과적인 수술법 검색. Delegates to SearchDAO."""
        return await self.search.search_effective_interventions(outcome_name)

    async def search_interventions_for_pathology(self, pathology_name: str) -> list[dict]:
        """질환별 수술법 검색. Delegates to SearchDAO."""
        return await self.search.search_interventions_for_pathology(pathology_name)

    async def find_conflicting_results(self, intervention_name: str) -> list[dict]:
        """상충 결과 검색. Delegates to SearchDAO."""
        return await self.search.find_conflicting_results(intervention_name)

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_stats(self) -> dict:
        """그래프 통계."""
        if self._mock_mode:
            return {"mock": True, "nodes": 0, "relationships": 0}
        return await self.schema_mgr.get_stats()

    # ========================================================================
    # Delete Operations
    # ========================================================================

    async def delete_paper(self, paper_id: str) -> dict:
        """논문 노드 및 관련 관계 삭제.

        Args:
            paper_id: 삭제할 논문 ID

        Returns:
            삭제 결과 (nodes_deleted, relationships_deleted)
        """
        if self._mock_mode:
            logger.info(f"Mock mode - skipping paper deletion: {paper_id}")
            return {"nodes_deleted": 0, "relationships_deleted": 0}

        # 먼저 관련 Chunk 삭제 후 Paper 삭제 (v5.3)
        query = """
        MATCH (p:Paper {paper_id: $paper_id})
        OPTIONAL MATCH (p)-[:HAS_CHUNK]->(c:Chunk)
        DETACH DELETE c, p
        """

        try:
            result = await self.run_write_query(query, {"paper_id": paper_id})
            logger.info(
                f"Deleted paper {paper_id}: "
                f"{result.get('nodes_deleted', 0)} nodes, "
                f"{result.get('relationships_deleted', 0)} relationships"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to delete paper {paper_id}: {e}", exc_info=True)
            raise

    async def delete_all_papers(self) -> dict:
        """모든 논문 노드 삭제 (관련 관계 포함).

        Returns:
            삭제 결과
        """
        if self._mock_mode:
            logger.info("Mock mode - skipping all papers deletion")
            return {"nodes_deleted": 0, "relationships_deleted": 0}

        query = """
        MATCH (p:Paper)
        DETACH DELETE p
        """

        try:
            result = await self.run_write_query(query)
            logger.info(
                f"Deleted all papers: "
                f"{result.get('nodes_deleted', 0)} nodes, "
                f"{result.get('relationships_deleted', 0)} relationships"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to delete all papers: {e}", exc_info=True)
            raise

    async def clear_database(self) -> dict:
        """전체 데이터베이스 리셋 (모든 노드와 관계 삭제).

        Warning:
            이 작업은 되돌릴 수 없습니다!
            Taxonomy와 스키마는 유지되며, Paper와 관련 데이터만 삭제됩니다.

        Returns:
            삭제 결과
        """
        if self._mock_mode:
            logger.info("Mock mode - skipping database clear")
            return {"nodes_deleted": 0, "relationships_deleted": 0}
        return await self.schema_mgr.clear_database()

    async def clear_all_including_taxonomy(self) -> dict:
        """전체 데이터베이스 완전 리셋 (Taxonomy 포함).

        Warning:
            이 작업은 되돌릴 수 없습니다!
            모든 노드와 관계가 삭제되며, 스키마만 유지됩니다.
            재사용 전 initialize_schema()를 다시 호출해야 합니다.

        Returns:
            삭제 결과
        """
        if self._mock_mode:
            logger.info("Mock mode - skipping full database clear")
            return {"nodes_deleted": 0, "relationships_deleted": 0}
        result = await self.schema_mgr.clear_all_including_taxonomy()
        self._initialized = False  # 스키마 재초기화 필요
        return result


class MockSession:
    """Neo4j 없을 때 사용하는 Mock 세션."""

    async def run(self, query: str, parameters: Optional[dict] = None):
        return MockResult()

    async def execute_write(self, tx_func):
        return {"mock": True}


class MockResult:
    """Mock 결과."""

    async def data(self):
        return []

    async def single(self):
        return None

    async def consume(self):
        return MockSummary()


class MockSummary:
    """Mock 요약."""

    class Counters:
        nodes_created = 0
        nodes_deleted = 0
        relationships_created = 0
        relationships_deleted = 0
        properties_set = 0

    counters = Counters()


# 사용 예시
async def example_usage():
    """사용 예시."""
    async with Neo4jClient() as client:
        # 스키마 초기화
        await client.initialize_schema()

        # 논문 생성
        paper = PaperNode(
            paper_id="test_001",
            title="Test Paper",
            authors=["Author A", "Author B"],
            year=2024,
            sub_domain="Degenerative",
            evidence_level="2b",
        )
        await client.create_paper(paper)

        # 관계 생성
        await client.create_studies_relation("test_001", "Lumbar Stenosis")
        await client.create_investigates_relation("test_001", "UBE")
        await client.create_affects_relation(
            intervention_name="UBE",
            outcome_name="VAS",
            source_paper_id="test_001",
            value="2.3",
            value_control="4.5",
            p_value=0.001,
            is_significant=True,
            direction="improved"
        )

        # 논문 간 관계 생성
        # 두 번째 논문 생성
        paper2 = PaperNode(
            paper_id="test_002",
            title="Follow-up Study on UBE",
            authors=["Author C", "Author D"],
            year=2025,
            sub_domain="Degenerative",
            evidence_level="1b",
        )
        await client.create_paper(paper2)

        # SUPPORTS 관계 생성
        await client.create_paper_relation(
            source_paper_id="test_002",
            target_paper_id="test_001",
            relation_type="SUPPORTS",
            confidence=0.85,
            evidence="Follow-up study confirms UBE effectiveness",
            detected_by="manual"
        )

        # CITES 관계 생성
        await client.create_paper_relation(
            source_paper_id="test_002",
            target_paper_id="test_001",
            relation_type="CITES",
            confidence=1.0,
            evidence="Cited in introduction",
            detected_by="citation_parser"
        )

        # 관계 조회
        relations = await client.get_paper_relations("test_001", direction="both")
        print(f"Paper relations: {relations}")

        # 지지 논문 조회
        supporting = await client.get_supporting_papers("test_001")
        print(f"Supporting papers: {supporting}")

        # 인용 논문 조회
        citing = await client.get_citing_papers("test_001")
        print(f"Citing papers: {citing}")

        # 조회
        stats = await client.get_stats()
        print(f"Graph stats: {stats}")


if __name__ == "__main__":
    asyncio.run(example_usage())

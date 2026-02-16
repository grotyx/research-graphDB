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

        if self._initialized:
            return

        logger.info("Initializing Neo4j schema...")

        # 1. 제약 조건 생성
        for query in SpineGraphSchema.get_create_constraints_cypher():
            try:
                await self.run_write_query(query)
            except Exception as e:
                # 이미 존재하는 제약 조건은 무시
                if "already exists" not in str(e).lower():
                    logger.warning(f"Constraint creation warning: {e}")

        # 2. 인덱스 생성
        for query in SpineGraphSchema.get_create_indexes_cypher():
            try:
                await self.run_write_query(query)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Index creation warning: {e}")

        # 3. Paper relation indexes
        paper_relation_indexes = [
            """
            CREATE INDEX paper_relation_confidence IF NOT EXISTS
            FOR ()-[r:SUPPORTS]-() ON (r.confidence)
            """,
            """
            CREATE INDEX paper_relation_confidence_contradicts IF NOT EXISTS
            FOR ()-[r:CONTRADICTS]-() ON (r.confidence)
            """,
            """
            CREATE INDEX paper_relation_confidence_similar IF NOT EXISTS
            FOR ()-[r:SIMILAR_TOPIC]-() ON (r.confidence)
            """,
            """
            CREATE INDEX paper_relation_confidence_extends IF NOT EXISTS
            FOR ()-[r:EXTENDS]-() ON (r.confidence)
            """,
            """
            CREATE INDEX paper_relation_confidence_cites IF NOT EXISTS
            FOR ()-[r:CITES]-() ON (r.confidence)
            """,
            """
            CREATE INDEX paper_relation_confidence_replicates IF NOT EXISTS
            FOR ()-[r:REPLICATES]-() ON (r.confidence)
            """,
        ]

        for query in paper_relation_indexes:
            try:
                await self.run_write_query(query)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Paper relation index creation warning: {e}")

        # 4. Vector Index 생성 (v5.3 - Neo4j Vector Index)
        for query in SpineGraphSchema.get_create_vector_indexes_cypher():
            try:
                await self.run_write_query(query)
                logger.info("Vector index created successfully")
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Vector index creation warning: {e}")

        # 5. Taxonomy 초기화
        try:
            await self.run_write_query(SpineGraphSchema.get_init_taxonomy_cypher())
            logger.info("Intervention taxonomy initialized")
        except Exception as e:
            logger.warning(f"Taxonomy initialization warning: {e}")

        self._initialized = True
        logger.info("Neo4j schema initialization complete")

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
             collect(DISTINCT anat.level) AS anatomy_levels
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
        """벡터 유사도 기반 청크 검색.

        Neo4j 5.26 Vector Index 사용.

        Args:
            embedding: 쿼리 임베딩 (MedTE: 768d, OpenAI: 3072d)
            top_k: 반환할 청크 수
            tier: 필터링할 티어 ("tier1" | "tier2")
            evidence_level: 필터링할 근거 수준 (단일)
            evidence_levels: 필터링할 근거 수준 (복수)
            min_year: 최소 연도 (Paper 노드에서 필터링)
            min_score: 최소 유사도 점수

        Returns:
            청크 정보 리스트 (score 포함)
        """
        # 기본 벡터 검색 (HNSW index)
        query = """
        CALL db.index.vector.queryNodes('chunk_embedding_index', $top_k, $embedding)
        YIELD node as c, score
        WHERE score >= $min_score
        """
        params: dict[str, Any] = {
            "embedding": embedding,
            "top_k": top_k * 3,  # 필터링 후 충분한 결과 확보
            "min_score": min_score,
        }

        # 조건 필터링
        if tier:
            query += " AND c.tier = $tier"
            params["tier"] = tier

        if evidence_level:
            query += " AND c.evidence_level = $evidence_level"
            params["evidence_level"] = evidence_level
        elif evidence_levels:
            query += " AND c.evidence_level IN $evidence_levels"
            params["evidence_levels"] = evidence_levels

        # min_year 필터링은 Paper 노드와 조인 필요
        if min_year:
            query += """
        OPTIONAL MATCH (p:Paper {paper_id: c.paper_id})
        WITH c, score, p
        WHERE p IS NULL OR p.year >= $min_year
            """
            params["min_year"] = min_year

        query += """
        OPTIONAL MATCH (paper:Paper {paper_id: c.paper_id})
        RETURN c.chunk_id as chunk_id,
               c.paper_id as paper_id,
               c.content as content,
               c.tier as tier,
               c.section as section,
               c.evidence_level as evidence_level,
               c.is_key_finding as is_key_finding,
               paper.title as paper_title,
               paper.year as paper_year,
               score
        ORDER BY score DESC
        LIMIT $limit
        """
        params["limit"] = top_k

        return await self.run_query(query, params)

    async def hybrid_search(
        self,
        embedding: list[float],
        graph_filters: Optional[dict] = None,
        top_k: int = 10,
        graph_weight: float = 0.6,
        vector_weight: float = 0.4
    ) -> list[dict]:
        """그래프 + 벡터 하이브리드 검색.

        Args:
            embedding: 쿼리 임베딩 (MedTE: 768d, OpenAI: 3072d)
            graph_filters: 그래프 필터 조건
                - intervention: 수술법 이름
                - pathology: 질환 이름
                - evidence_levels: 근거 수준 리스트
                - min_year: 최소 연도
            top_k: 반환할 결과 수
            graph_weight: 그래프 점수 가중치
            vector_weight: 벡터 점수 가중치

        Returns:
            하이브리드 검색 결과
        """
        graph_filters = graph_filters or {}

        # 벡터 검색으로 시작
        query = """
        CALL db.index.vector.queryNodes('chunk_embedding_index', $top_k_vector, $embedding)
        YIELD node as c, score as vector_score
        """
        params: dict[str, Any] = {
            "embedding": embedding,
            "top_k_vector": top_k * 3,  # 필터링 전 더 많은 결과 검색
        }

        # Paper 조인
        query += """
        MATCH (p:Paper)-[:HAS_CHUNK]->(c)
        """

        # 그래프 필터 적용
        filters = []
        if graph_filters.get("intervention"):
            filters.append("(p)-[:INVESTIGATES]->(:Intervention {name: $intervention})")
            params["intervention"] = graph_filters["intervention"]

        if graph_filters.get("pathology"):
            filters.append("(p)-[:STUDIES]->(:Pathology {name: $pathology})")
            params["pathology"] = graph_filters["pathology"]

        if graph_filters.get("evidence_levels"):
            filters.append("p.evidence_level IN $evidence_levels")
            params["evidence_levels"] = graph_filters["evidence_levels"]

        if graph_filters.get("min_year"):
            filters.append("p.year >= $min_year")
            params["min_year"] = graph_filters["min_year"]

        if filters:
            query += " WHERE " + " AND ".join(filters)

        # 그래프 점수 계산 (evidence level 기반)
        query += """
        WITH c, p, vector_score,
             CASE p.evidence_level
                 WHEN '1a' THEN 1.0
                 WHEN '1b' THEN 0.9
                 WHEN '2a' THEN 0.8
                 WHEN '2b' THEN 0.7
                 WHEN '3' THEN 0.5
                 WHEN '4' THEN 0.3
                 ELSE 0.1
             END as graph_score
        WITH c, p, vector_score, graph_score,
             ($graph_weight * graph_score + $vector_weight * vector_score) as final_score
        """
        params["graph_weight"] = graph_weight
        params["vector_weight"] = vector_weight

        query += """
        RETURN c.chunk_id as chunk_id,
               c.paper_id as paper_id,
               c.content as content,
               c.tier as tier,
               c.section as section,
               p.title as paper_title,
               p.evidence_level as evidence_level,
               p.year as year,
               vector_score,
               graph_score,
               final_score
        ORDER BY final_score DESC
        LIMIT $limit
        """
        params["limit"] = top_k

        return await self.run_query(query, params)

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
        """논문 → 질환 관계 생성.

        Args:
            paper_id: 논문 ID
            pathology_name: 질환명
            is_primary: 주요 질환 여부
            snomed_code: SNOMED-CT 코드 (v1.9)
            snomed_term: SNOMED-CT 용어 (v1.9)

        Returns:
            생성된 관계 정보
        """
        return await self.run_write_query(
            CypherTemplates.CREATE_STUDIES_RELATION,
            {
                "paper_id": paper_id,
                "pathology_name": pathology_name,
                "is_primary": is_primary,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
            }
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
        """논문 → 수술법 관계 생성.

        Args:
            paper_id: 논문 ID
            intervention_name: 수술법 이름
            is_comparison: 비교군 수술법 여부
            category: 수술법 카테고리 (EntityNormalizer에서)
            snomed_code: SNOMED-CT 코드 (EntityNormalizer에서)
            snomed_term: SNOMED-CT 용어 (EntityNormalizer에서)

        Returns:
            생성된 관계 정보
        """
        return await self.run_write_query(
            CypherTemplates.CREATE_INVESTIGATES_RELATION,
            {
                "paper_id": paper_id,
                "intervention_name": intervention_name,
                "is_comparison": is_comparison,
                "category": category,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
            }
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
        # v4.0 추가 필드 (Claude/Gemini 통합 지원)
        baseline: Optional[float] = None,
        final: Optional[float] = None,
        value_intervention: str = "",
        value_difference: str = "",
        category: str = "",
        timepoint: str = "",
        # v1.9: SNOMED 지원
        snomed_code: Optional[str] = None,
        snomed_term: Optional[str] = None
    ) -> dict:
        """수술법 → 결과 관계 생성 (Unified Schema v4.0).

        Claude와 Gemini PDF 처리기 결과 모두 지원.
        v1.9: Outcome 노드에 SNOMED-CT 코드 지원 추가.

        Args:
            intervention_name: 수술법 이름
            outcome_name: 결과변수 이름
            source_paper_id: 출처 논문 ID
            ... (통계 파라미터들)
            snomed_code: Outcome의 SNOMED-CT 코드 (v1.9)
            snomed_term: Outcome의 SNOMED-CT 용어 (v1.9)

        Returns:
            생성된 관계 정보
        """
        return await self.run_write_query(
            CypherTemplates.CREATE_AFFECTS_RELATION,
            {
                "intervention_name": intervention_name,
                "outcome_name": outcome_name,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
                "properties": {
                    "source_paper_id": source_paper_id,
                    "value": value,
                    "value_control": value_control,
                    "p_value": p_value,
                    "effect_size": effect_size,
                    "confidence_interval": confidence_interval,
                    "is_significant": is_significant,
                    "direction": direction,
                    # v4.0 추가 필드
                    "baseline": baseline,
                    "final": final,
                    "value_intervention": value_intervention,
                    "value_difference": value_difference,
                    "category": category,
                    "timepoint": timepoint,
                },
            }
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
        """수술법 → 질환 치료 관계 생성 (Intervention → Pathology).

        v1.16.1: TREATS 관계 구현.

        Args:
            intervention_name: 수술법 이름
            pathology_name: 질환 이름
            source_paper_id: 출처 논문 ID
            indication: 적응증
            contraindication: 금기사항
            indication_level: 적응 수준 (strong/moderate/weak)

        Returns:
            생성된 관계 정보
        """
        return await self.run_write_query(
            CypherTemplates.CREATE_TREATS_RELATION,
            {
                "intervention_name": intervention_name,
                "pathology_name": pathology_name,
                "source_paper_id": source_paper_id,
                "indication": indication[:500] if indication else "",
                "contraindication": contraindication[:500] if contraindication else "",
                "indication_level": indication_level,
            }
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
        """논문 → 해부학 위치 관계 생성 (Paper → Anatomy).

        Args:
            paper_id: 논문 ID
            anatomy_name: 해부학적 위치 (예: "L4-5", "C5-6", "Lumbar")
            level: 척추 레벨 (예: "lumbar", "cervical", "thoracic")
            region: 상세 영역 (예: "L4-L5", "C5-C6")
            snomed_code: SNOMED-CT 코드 (v1.19.5)
            snomed_term: SNOMED-CT 용어 (v1.19.5)

        Returns:
            생성 결과
        """
        return await self.run_write_query(
            CypherTemplates.CREATE_INVOLVES_RELATION,
            {
                "paper_id": paper_id,
                "anatomy_name": anatomy_name,
                "level": level,
                "region": region,
                "snomed_code": snomed_code,
                "snomed_term": snomed_term,
            }
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
        """논문 간 관계 생성.

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            relation_type: 관계 유형 (SUPPORTS, CONTRADICTS, SIMILAR_TOPIC, EXTENDS, CITES, REPLICATES)
            confidence: 관계 신뢰도 (0.0-1.0)
            evidence: 근거 텍스트
            detected_by: 탐지 방법 (예: "manual", "llm", "citation_parser")

        Returns:
            성공 여부

        Raises:
            ValueError: Invalid relation_type or confidence
        """
        # Validate relation type
        valid_types = {"SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"}
        if relation_type not in valid_types:
            raise ValueError(f"Invalid relation_type: {relation_type}. Must be one of {valid_types}")

        # Validate confidence
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Invalid confidence: {confidence}. Must be between 0.0 and 1.0")

        query = f"""
        MATCH (a:Paper {{paper_id: $source_id}})
        MATCH (b:Paper {{paper_id: $target_id}})
        MERGE (a)-[r:{relation_type}]->(b)
        SET r.confidence = $confidence,
            r.evidence = $evidence,
            r.detected_by = $detected_by,
            r.created_at = datetime()
        RETURN r
        """

        try:
            result = await self.run_write_query(
                query,
                {
                    "source_id": source_paper_id,
                    "target_id": target_paper_id,
                    "confidence": confidence,
                    "evidence": evidence,
                    "detected_by": detected_by,
                }
            )
            return result.get("relationships_created", 0) > 0 or result.get("properties_set", 0) > 0
        except Exception as e:
            logger.error(f"Failed to create paper relation: {e}", exc_info=True)
            raise

    async def create_supports_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        evidence: str = "",
        confidence: float = 0.0
    ) -> bool:
        """SUPPORTS 관계 생성 (convenience wrapper).

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            evidence: 근거 텍스트
            confidence: 관계 신뢰도 (0.0-1.0)

        Returns:
            성공 여부
        """
        return await self.create_paper_relation(
            source_paper_id=source_paper_id,
            target_paper_id=target_paper_id,
            relation_type="SUPPORTS",
            confidence=confidence,
            evidence=evidence,
            detected_by="citation_parser"
        )

    async def create_contradicts_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        evidence: str = "",
        confidence: float = 0.0
    ) -> bool:
        """CONTRADICTS 관계 생성 (convenience wrapper).

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            evidence: 근거 텍스트
            confidence: 관계 신뢰도 (0.0-1.0)

        Returns:
            성공 여부
        """
        return await self.create_paper_relation(
            source_paper_id=source_paper_id,
            target_paper_id=target_paper_id,
            relation_type="CONTRADICTS",
            confidence=confidence,
            evidence=evidence,
            detected_by="citation_parser"
        )

    async def create_cites_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        citation_text: str = "",
        context: str = ""
    ) -> bool:
        """CITES 관계 생성 (convenience wrapper).

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            citation_text: 인용 텍스트
            context: 인용 컨텍스트

        Returns:
            성공 여부
        """
        evidence = f"{citation_text}\n\nContext: {context}" if context else citation_text
        return await self.create_paper_relation(
            source_paper_id=source_paper_id,
            target_paper_id=target_paper_id,
            relation_type="CITES",
            confidence=1.0,  # 인용은 명시적이므로 확실함
            evidence=evidence,
            detected_by="citation_parser"
        )

    async def get_paper_relations(
        self,
        paper_id: str,
        relation_types: Optional[list[str]] = None,
        direction: str = "both"
    ) -> list[dict]:
        """논문의 관계 조회.

        Args:
            paper_id: 논문 ID
            relation_types: 관계 유형 필터 (None이면 전체)
            direction: 관계 방향 ("outgoing", "incoming", "both")

        Returns:
            관계 목록 (각 항목: {relation_type, target_paper, confidence, evidence, detected_by, created_at})

        Raises:
            ValueError: Invalid direction
        """
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError(f"Invalid direction: {direction}. Must be 'outgoing', 'incoming', or 'both'")

        # Build relationship type filter
        rel_type_filter = ""
        if relation_types:
            rel_type_filter = f":{':'.join(relation_types)}"

        if direction == "outgoing":
            query = f"""
            MATCH (p:Paper {{paper_id: $paper_id}})-[r{rel_type_filter}]->(target:Paper)
            RETURN type(r) as relation_type, target, r.confidence as confidence,
                   r.evidence as evidence, r.detected_by as detected_by, r.created_at as created_at
            ORDER BY r.confidence DESC
            """
        elif direction == "incoming":
            query = f"""
            MATCH (source:Paper)-[r{rel_type_filter}]->(p:Paper {{paper_id: $paper_id}})
            RETURN type(r) as relation_type, source as target, r.confidence as confidence,
                   r.evidence as evidence, r.detected_by as detected_by, r.created_at as created_at
            ORDER BY r.confidence DESC
            """
        else:  # both
            query = f"""
            MATCH (p:Paper {{paper_id: $paper_id}})
            CALL {{
                WITH p
                MATCH (p)-[r{rel_type_filter}]->(target:Paper)
                RETURN type(r) as relation_type, target, r.confidence as confidence,
                       r.evidence as evidence, r.detected_by as detected_by,
                       r.created_at as created_at, 'outgoing' as direction
                UNION
                WITH p
                MATCH (source:Paper)-[r{rel_type_filter}]->(p)
                RETURN type(r) as relation_type, source as target, r.confidence as confidence,
                       r.evidence as evidence, r.detected_by as detected_by,
                       r.created_at as created_at, 'incoming' as direction
            }}
            RETURN relation_type, target, confidence, evidence, detected_by, created_at, direction
            ORDER BY confidence DESC
            """

        return await self.run_query(query, {"paper_id": paper_id})

    async def get_related_papers(
        self,
        paper_id: str,
        relation_type: str,
        min_confidence: float = 0.0,
        limit: int = 10
    ) -> list[dict]:
        """특정 관계 유형의 관련 논문 조회.

        Args:
            paper_id: 논문 ID
            relation_type: 관계 유형
            min_confidence: 최소 신뢰도
            limit: 최대 결과 수

        Returns:
            관련 논문 목록

        Raises:
            ValueError: Invalid relation_type
        """
        # Validate relation type to prevent Cypher injection
        valid_types = {"SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"}
        if relation_type not in valid_types:
            raise ValueError(f"Invalid relation_type: {relation_type}. Must be one of {valid_types}")

        query = f"""
        MATCH (p:Paper {{paper_id: $paper_id}})-[r:{relation_type}]->(target:Paper)
        WHERE r.confidence >= $min_confidence
        RETURN target, r.confidence as confidence, r.evidence as evidence
        ORDER BY r.confidence DESC
        LIMIT $limit
        """

        return await self.run_query(
            query,
            {"paper_id": paper_id, "min_confidence": min_confidence, "limit": limit}
        )

    async def get_supporting_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """지지하는 논문들 조회 (SUPPORTS 관계).

        Args:
            paper_id: 논문 ID
            limit: 최대 결과 수

        Returns:
            지지하는 논문 목록
        """
        return await self.get_related_papers(paper_id, "SUPPORTS", limit=limit)

    async def get_contradicting_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """상충하는 논문들 조회 (CONTRADICTS 관계).

        Args:
            paper_id: 논문 ID
            limit: 최대 결과 수

        Returns:
            상충하는 논문 목록
        """
        return await self.get_related_papers(paper_id, "CONTRADICTS", limit=limit)

    async def get_similar_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """유사 주제 논문들 조회 (SIMILAR_TOPIC 관계).

        Args:
            paper_id: 논문 ID
            limit: 최대 결과 수

        Returns:
            유사 논문 목록
        """
        return await self.get_related_papers(paper_id, "SIMILAR_TOPIC", limit=limit)

    async def get_citing_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """이 논문을 인용한 논문들 조회.

        Args:
            paper_id: 논문 ID
            limit: 최대 결과 수

        Returns:
            인용 논문 목록 (이 논문을 인용한 논문들)
        """
        query = """
        MATCH (source:Paper)-[r:CITES]->(p:Paper {paper_id: $paper_id})
        RETURN source, r.confidence as confidence, r.evidence as evidence
        ORDER BY source.year DESC
        LIMIT $limit
        """

        return await self.run_query(query, {"paper_id": paper_id, "limit": limit})

    async def get_cited_papers(self, paper_id: str, limit: int = 10) -> list[dict]:
        """이 논문이 인용한 논문들 조회.

        Args:
            paper_id: 논문 ID
            limit: 최대 결과 수

        Returns:
            피인용 논문 목록 (이 논문이 인용한 논문들)
        """
        return await self.get_related_papers(paper_id, "CITES", limit=limit)

    async def delete_paper_relation(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str
    ) -> bool:
        """논문 간 관계 삭제.

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            relation_type: 관계 유형

        Returns:
            성공 여부

        Raises:
            ValueError: Invalid relation_type
        """
        # Validate relation type to prevent Cypher injection
        valid_types = {"SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"}
        if relation_type not in valid_types:
            raise ValueError(f"Invalid relation_type: {relation_type}. Must be one of {valid_types}")

        query = f"""
        MATCH (a:Paper {{paper_id: $source_id}})-[r:{relation_type}]->(b:Paper {{paper_id: $target_id}})
        DELETE r
        """

        try:
            result = await self.run_write_query(
                query,
                {"source_id": source_paper_id, "target_id": target_paper_id}
            )
            return result.get("relationships_deleted", 0) > 0
        except Exception as e:
            logger.error(f"Failed to delete paper relation: {e}", exc_info=True)
            raise

    async def update_paper_relation_confidence(
        self,
        source_paper_id: str,
        target_paper_id: str,
        relation_type: str,
        new_confidence: float
    ) -> bool:
        """관계 신뢰도 업데이트.

        Args:
            source_paper_id: 원본 논문 ID
            target_paper_id: 대상 논문 ID
            relation_type: 관계 유형
            new_confidence: 새 신뢰도 (0.0-1.0)

        Returns:
            성공 여부

        Raises:
            ValueError: Invalid relation_type or confidence value
        """
        # Validate relation type to prevent Cypher injection
        valid_types = {"SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"}
        if relation_type not in valid_types:
            raise ValueError(f"Invalid relation_type: {relation_type}. Must be one of {valid_types}")

        if not 0.0 <= new_confidence <= 1.0:
            raise ValueError(f"Invalid confidence: {new_confidence}. Must be between 0.0 and 1.0")

        query = f"""
        MATCH (a:Paper {{paper_id: $source_id}})-[r:{relation_type}]->(b:Paper {{paper_id: $target_id}})
        SET r.confidence = $new_confidence,
            r.updated_at = datetime()
        RETURN r
        """

        try:
            result = await self.run_write_query(
                query,
                {
                    "source_id": source_paper_id,
                    "target_id": target_paper_id,
                    "new_confidence": new_confidence,
                }
            )
            return result.get("properties_set", 0) > 0
        except Exception as e:
            logger.error(f"Failed to update paper relation confidence: {e}", exc_info=True)
            raise

    # ========================================================================
    # Search Operations
    # ========================================================================

    async def get_intervention_hierarchy(self, intervention_name: str) -> list[dict]:
        """수술법 계층 조회."""
        return await self.run_query(
            CypherTemplates.GET_INTERVENTION_HIERARCHY,
            {"intervention_name": intervention_name}
        )

    async def get_intervention_children(self, intervention_name: str) -> list[dict]:
        """수술법 하위 항목 조회."""
        return await self.run_query(
            CypherTemplates.GET_INTERVENTION_CHILDREN,
            {"intervention_name": intervention_name}
        )

    async def search_effective_interventions(self, outcome_name: str) -> list[dict]:
        """효과적인 수술법 검색."""
        return await self.run_query(
            CypherTemplates.SEARCH_EFFECTIVE_INTERVENTIONS,
            {"outcome_name": outcome_name}
        )

    async def search_interventions_for_pathology(self, pathology_name: str) -> list[dict]:
        """질환별 수술법 검색."""
        return await self.run_query(
            CypherTemplates.SEARCH_INTERVENTIONS_FOR_PATHOLOGY,
            {"pathology_name": pathology_name}
        )

    # NOTE: get_paper_relations is defined at line 587 with full implementation
    # This duplicate simple version has been removed to avoid confusion

    async def find_conflicting_results(self, intervention_name: str) -> list[dict]:
        """상충 결과 검색."""
        return await self.run_query(
            CypherTemplates.FIND_CONFLICTING_RESULTS,
            {"intervention_name": intervention_name}
        )

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_stats(self) -> dict:
        """그래프 통계."""
        if self._mock_mode:
            return {"mock": True, "nodes": 0, "relationships": 0}

        stats_query = """
        MATCH (n)
        WITH labels(n) as label, count(n) as count
        RETURN label, count
        """
        label_counts = await self.run_query(stats_query)

        rel_query = """
        MATCH ()-[r]->()
        WITH type(r) as type, count(r) as count
        RETURN type, count
        """
        rel_counts = await self.run_query(rel_query)

        return {
            "nodes": {r["label"][0]: r["count"] for r in label_counts if r["label"]},
            "relationships": {r["type"]: r["count"] for r in rel_counts},
        }

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

        # Paper, Pathology, Outcome 노드만 삭제 (Intervention/Anatomy는 Taxonomy이므로 보존)
        query = """
        MATCH (n)
        WHERE n:Paper OR n:Pathology OR n:Outcome OR n:Chunk
        DETACH DELETE n
        """

        try:
            result = await self.run_write_query(query)
            logger.warning(
                f"Database cleared: "
                f"{result.get('nodes_deleted', 0)} nodes, "
                f"{result.get('relationships_deleted', 0)} relationships deleted"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to clear database: {e}", exc_info=True)
            raise

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

        query = """
        MATCH (n)
        DETACH DELETE n
        """

        try:
            result = await self.run_write_query(query)
            self._initialized = False  # 스키마 재초기화 필요
            logger.warning(
                f"Full database cleared (including taxonomy): "
                f"{result.get('nodes_deleted', 0)} nodes, "
                f"{result.get('relationships_deleted', 0)} relationships deleted"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to clear full database: {e}", exc_info=True)
            raise


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

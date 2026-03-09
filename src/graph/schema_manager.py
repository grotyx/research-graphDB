"""Schema Manager for Neo4j.

Neo4j 스키마 초기화, 통계 조회, 데이터베이스 리셋 관리.
Neo4jClient에서 추출된 DAO 클래스 (D-005).
"""

import logging
from typing import Callable, Awaitable

from .spine_schema import SpineGraphSchema

logger = logging.getLogger(__name__)


class SchemaManager:
    """Neo4j 스키마 및 데이터베이스 관리.

    Args:
        run_query: 읽기 쿼리 실행 callable
        run_write_query: 쓰기 쿼리 실행 callable
    """

    def __init__(
        self,
        run_query: Callable[..., Awaitable[list[dict]]],
        run_write_query: Callable[..., Awaitable[dict]],
    ) -> None:
        self._run_query = run_query
        self._run_write_query = run_write_query
        self._initialized = False

    async def initialize_schema(self) -> None:
        """스키마 초기화 (제약 조건, 인덱스)."""
        if self._initialized:
            return

        logger.info("Initializing Neo4j schema...")

        # 1. 제약 조건 생성
        for query in SpineGraphSchema.get_create_constraints_cypher():
            try:
                await self._run_write_query(query)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Constraint creation warning: {e}")

        # 2. 인덱스 생성
        for query in SpineGraphSchema.get_create_indexes_cypher():
            try:
                await self._run_write_query(query)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Index creation warning: {e}")

        # 3. Relationship property indexes (AFFECTS, STUDIES, INVESTIGATES, etc.)
        for query in SpineGraphSchema.get_create_relationship_indexes_cypher():
            try:
                await self._run_write_query(query)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Relationship index creation warning: {e}")

        # 3b. Paper relation indexes
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
                await self._run_write_query(query)
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Paper relation index creation warning: {e}")

        # 4. Vector Index 생성 (v5.3 - Neo4j Vector Index)
        for query in SpineGraphSchema.get_create_vector_indexes_cypher():
            try:
                await self._run_write_query(query)
                logger.info("Vector index created successfully")
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Vector index creation warning: {e}")

        # 5. Taxonomy 초기화 (Intervention)
        try:
            await self._run_write_query(SpineGraphSchema.get_init_taxonomy_cypher())
            logger.info("Intervention taxonomy initialized")
        except Exception as e:
            logger.warning(f"Taxonomy initialization warning: {e}")

        # 6. Entity Taxonomy 초기화 (Pathology, Outcome, Anatomy IS_A)
        entity_queries = SpineGraphSchema.get_init_entity_taxonomy_cypher()
        entity_success = 0
        for query, params in entity_queries:
            try:
                await self._run_write_query(query, params)
                entity_success += 1
            except Exception as e:
                logger.warning(
                    f"Entity taxonomy IS_A failed: "
                    f"{params.get('child_name', '?')} -> "
                    f"{params.get('parent_name', '?')}: {e}"
                )
        logger.info(
            f"Entity taxonomy initialized ({entity_success}/{len(entity_queries)} IS_A relationships)"
        )

        self._initialized = True
        logger.info("Neo4j schema initialization complete")

    async def get_stats(self) -> dict:
        """그래프 통계."""
        stats_query = """
        MATCH (n)
        WITH labels(n) as label, count(n) as count
        RETURN label, count
        """
        label_counts = await self._run_query(stats_query)

        rel_query = """
        MATCH ()-[r]->()
        WITH type(r) as type, count(r) as count
        RETURN type, count
        """
        rel_counts = await self._run_query(rel_query)

        return {
            "nodes": {r["label"][0]: r["count"] for r in label_counts if r["label"]},
            "relationships": {r["type"]: r["count"] for r in rel_counts},
        }

    async def clear_database(self) -> dict:
        """전체 데이터베이스 리셋 (모든 노드와 관계 삭제).

        Warning:
            이 작업은 되돌릴 수 없습니다!
            Taxonomy와 스키마는 유지되며, Paper와 관련 데이터만 삭제됩니다.

        Returns:
            삭제 결과
        """
        query = """
        MATCH (n)
        WHERE n:Paper OR n:Pathology OR n:Outcome OR n:Chunk
        DETACH DELETE n
        """

        try:
            result = await self._run_write_query(query)
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
        query = """
        MATCH (n)
        DETACH DELETE n
        """

        try:
            result = await self._run_write_query(query)
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

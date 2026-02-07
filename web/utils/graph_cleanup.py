"""Graph Cleanup Utilities.

Neo4j 그래프 데이터 정리 및 관리 유틸리티.
"""

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """정리 작업 결과."""
    success: bool
    deleted_nodes: int = 0
    deleted_relationships: int = 0
    message: str = ""
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class GraphCleanupManager:
    """Neo4j 그래프 정리 관리자."""

    def __init__(self, neo4j_client):
        """
        Args:
            neo4j_client: SyncNeo4jClient 인스턴스
        """
        self.client = neo4j_client

    def delete_paper_with_cleanup(self, paper_id: str) -> CleanupResult:
        """논문과 관련 데이터를 완전히 삭제.

        논문 노드와 연결된 관계를 삭제하고,
        고아 노드(연결이 없는 노드)도 정리합니다.

        Args:
            paper_id: 삭제할 논문 ID

        Returns:
            CleanupResult
        """
        try:
            # 1. 논문 존재 확인
            check_query = "MATCH (p:Paper {paper_id: $paper_id}) RETURN p"
            result = self.client.run_query(check_query, {"paper_id": paper_id})

            if not result:
                return CleanupResult(
                    success=False,
                    message=f"Paper not found: {paper_id}"
                )

            # 2. 관련 관계 수 확인
            rel_count_query = """
            MATCH (p:Paper {paper_id: $paper_id})-[r]-()
            RETURN count(r) as rel_count
            """
            rel_result = self.client.run_query(rel_count_query, {"paper_id": paper_id})
            rel_count = rel_result[0]["rel_count"] if rel_result else 0

            # 3. 논문과 모든 관계 삭제
            delete_query = """
            MATCH (p:Paper {paper_id: $paper_id})
            DETACH DELETE p
            RETURN 1 as deleted
            """
            self.client.run_query(delete_query, {"paper_id": paper_id})

            # 4. 고아 노드 정리
            orphan_result = self.cleanup_orphan_nodes()

            return CleanupResult(
                success=True,
                deleted_nodes=1 + orphan_result.deleted_nodes,
                deleted_relationships=rel_count,
                message=f"Paper '{paper_id}' deleted with {rel_count} relationships",
                details={
                    "paper_deleted": True,
                    "relationships_deleted": rel_count,
                    "orphan_nodes_cleaned": orphan_result.deleted_nodes
                }
            )

        except Exception as e:
            logger.error(f"Error deleting paper {paper_id}: {e}")
            return CleanupResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    def cleanup_orphan_nodes(self) -> CleanupResult:
        """연결이 없는 고아 노드 정리.

        Paper를 제외한 노드 중 아무 관계도 없는 노드를 삭제합니다.

        Returns:
            CleanupResult
        """
        try:
            deleted_counts = {}

            # Pathology 고아 노드
            pathology_query = """
            MATCH (p:Pathology)
            WHERE NOT (p)<-[:STUDIES]-() AND NOT (p)<-[:TREATS]-()
            WITH p, p.name as name LIMIT 500
            DELETE p
            RETURN count(*) as deleted
            """
            result = self.client.run_query(pathology_query, {})
            deleted_counts["Pathology"] = result[0]["deleted"] if result else 0

            # Anatomy 고아 노드
            anatomy_query = """
            MATCH (a:Anatomy)
            WHERE NOT (a)<-[:INVOLVES]-() AND NOT (a)<-[:TARGETS]-()
            WITH a LIMIT 500
            DELETE a
            RETURN count(*) as deleted
            """
            result = self.client.run_query(anatomy_query, {})
            deleted_counts["Anatomy"] = result[0]["deleted"] if result else 0

            # Outcome 고아 노드 (AFFECTS 관계도 없는 경우)
            outcome_query = """
            MATCH (o:Outcome)
            WHERE NOT (o)<-[:REPORTS]-() AND NOT (o)<-[:AFFECTS]-()
            WITH o LIMIT 500
            DELETE o
            RETURN count(*) as deleted
            """
            result = self.client.run_query(outcome_query, {})
            deleted_counts["Outcome"] = result[0]["deleted"] if result else 0

            total_deleted = sum(deleted_counts.values())

            return CleanupResult(
                success=True,
                deleted_nodes=total_deleted,
                message=f"Cleaned {total_deleted} orphan nodes",
                details=deleted_counts
            )

        except Exception as e:
            logger.error(f"Error cleaning orphan nodes: {e}")
            return CleanupResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    def cleanup_orphan_affects_relations(self) -> CleanupResult:
        """고아 AFFECTS 관계 정리.

        Paper와 연결되지 않은 AFFECTS 관계를 정리합니다.

        Returns:
            CleanupResult
        """
        try:
            # Paper와 연결되지 않은 Intervention의 AFFECTS 관계 삭제
            cleanup_query = """
            MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
            WHERE NOT EXISTS {
                MATCH (p:Paper)-[:INVESTIGATES]->(i)
            }
            DELETE r
            RETURN count(r) as deleted
            """
            result = self.client.run_query(cleanup_query, {})
            deleted = result[0]["deleted"] if result else 0

            return CleanupResult(
                success=True,
                deleted_relationships=deleted,
                message=f"Cleaned {deleted} orphan AFFECTS relationships"
            )

        except Exception as e:
            logger.error(f"Error cleaning orphan AFFECTS: {e}")
            return CleanupResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    def get_orphan_stats(self) -> dict:
        """고아 노드 통계 조회.

        Returns:
            노드 유형별 고아 노드 수
        """
        try:
            stats = {}

            # Pathology 고아 노드 수
            query = """
            MATCH (p:Pathology)
            WHERE NOT (p)<-[:STUDIES]-() AND NOT (p)<-[:TREATS]-()
            RETURN count(p) as count
            """
            result = self.client.run_query(query, {})
            stats["Pathology"] = result[0]["count"] if result else 0

            # Anatomy 고아 노드 수
            query = """
            MATCH (a:Anatomy)
            WHERE NOT (a)<-[:INVOLVES]-() AND NOT (a)<-[:TARGETS]-()
            RETURN count(a) as count
            """
            result = self.client.run_query(query, {})
            stats["Anatomy"] = result[0]["count"] if result else 0

            # Outcome 고아 노드 수
            query = """
            MATCH (o:Outcome)
            WHERE NOT (o)<-[:REPORTS]-() AND NOT (o)<-[:AFFECTS]-()
            RETURN count(o) as count
            """
            result = self.client.run_query(query, {})
            stats["Outcome"] = result[0]["count"] if result else 0

            # 연결 없는 AFFECTS 관계 수
            query = """
            MATCH (i:Intervention)-[r:AFFECTS]->(o:Outcome)
            WHERE NOT EXISTS {
                MATCH (p:Paper)-[:INVESTIGATES]->(i)
            }
            RETURN count(r) as count
            """
            result = self.client.run_query(query, {})
            stats["Orphan_AFFECTS"] = result[0]["count"] if result else 0

            stats["total"] = sum(stats.values())

            return stats

        except Exception as e:
            logger.error(f"Error getting orphan stats: {e}")
            return {"error": str(e)}

    def reset_all_paper_data(self) -> CleanupResult:
        """모든 Paper 관련 데이터 초기화.

        Paper 노드와 관련 관계를 모두 삭제합니다.
        Taxonomy(Intervention IS_A 계층)는 유지합니다.

        Returns:
            CleanupResult
        """
        try:
            # 1. Paper 노드 수 확인
            count_query = "MATCH (p:Paper) RETURN count(p) as count"
            result = self.client.run_query(count_query, {})
            paper_count = result[0]["count"] if result else 0

            if paper_count == 0:
                return CleanupResult(
                    success=True,
                    message="No papers to delete"
                )

            # 2. Paper와 모든 관계 삭제
            delete_query = """
            MATCH (p:Paper)
            DETACH DELETE p
            """
            self.client.run_query(delete_query, {})

            # 3. 고아 노드 정리
            orphan_result = self.cleanup_orphan_nodes()

            # 4. 고아 AFFECTS 관계 정리
            affects_result = self.cleanup_orphan_affects_relations()

            return CleanupResult(
                success=True,
                deleted_nodes=paper_count + orphan_result.deleted_nodes,
                deleted_relationships=affects_result.deleted_relationships,
                message=f"Reset complete: {paper_count} papers deleted",
                details={
                    "papers_deleted": paper_count,
                    "orphan_nodes_cleaned": orphan_result.deleted_nodes,
                    "orphan_affects_cleaned": affects_result.deleted_relationships
                }
            )

        except Exception as e:
            logger.error(f"Error resetting paper data: {e}")
            return CleanupResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    def reset_entire_database(self) -> CleanupResult:
        """전체 데이터베이스 초기화.

        모든 노드와 관계를 삭제합니다.
        스키마 재초기화가 필요합니다.

        Returns:
            CleanupResult
        """
        try:
            # 노드 수 확인
            count_query = "MATCH (n) RETURN count(n) as count"
            result = self.client.run_query(count_query, {})
            node_count = result[0]["count"] if result else 0

            # 관계 수 확인
            rel_query = "MATCH ()-[r]->() RETURN count(r) as count"
            result = self.client.run_query(rel_query, {})
            rel_count = result[0]["count"] if result else 0

            if node_count == 0:
                return CleanupResult(
                    success=True,
                    message="Database is already empty"
                )

            # 배치 삭제 (대용량 데이터 처리)
            batch_delete_query = """
            MATCH (n)
            WITH n LIMIT 1000
            DETACH DELETE n
            RETURN count(*) as deleted
            """

            total_deleted = 0
            while True:
                result = self.client.run_query(batch_delete_query, {})
                deleted = result[0]["deleted"] if result else 0
                total_deleted += deleted
                if deleted == 0:
                    break

            return CleanupResult(
                success=True,
                deleted_nodes=node_count,
                deleted_relationships=rel_count,
                message=f"Database reset: {node_count} nodes, {rel_count} relationships deleted",
                details={
                    "nodes_deleted": node_count,
                    "relationships_deleted": rel_count
                }
            )

        except Exception as e:
            logger.error(f"Error resetting database: {e}")
            return CleanupResult(
                success=False,
                message=f"Error: {str(e)}"
            )

    def get_database_stats(self) -> dict:
        """데이터베이스 통계 조회.

        Returns:
            노드/관계 유형별 통계
        """
        try:
            stats = {
                "nodes": {},
                "relationships": {},
                "orphans": self.get_orphan_stats()
            }

            # 노드 통계
            node_query = """
            MATCH (n)
            WITH labels(n)[0] as label, count(n) as count
            RETURN label, count
            ORDER BY count DESC
            """
            result = self.client.run_query(node_query, {})
            for r in result:
                stats["nodes"][r["label"]] = r["count"]

            # 관계 통계
            rel_query = """
            MATCH ()-[r]->()
            WITH type(r) as rel_type, count(r) as count
            RETURN rel_type, count
            ORDER BY count DESC
            """
            result = self.client.run_query(rel_query, {})
            for r in result:
                stats["relationships"][r["rel_type"]] = r["count"]

            # 총계
            stats["total_nodes"] = sum(stats["nodes"].values())
            stats["total_relationships"] = sum(stats["relationships"].values())

            return stats

        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {"error": str(e)}

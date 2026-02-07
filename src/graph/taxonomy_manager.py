"""Taxonomy Manager for Intervention Hierarchy.

수술법 계층 구조 관리.
- IS_A 관계를 통한 계층 탐색
- 공통 조상 찾기 (두 수술법의 유사성 판단)
- 동적 Taxonomy 확장
"""

import logging
from typing import Optional

from .neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


class TaxonomyManager:
    """수술법 계층 구조 관리자.

    사용 예:
        manager = TaxonomyManager(neo4j_client)
        parents = await manager.get_parent_interventions("TLIF")
        # parents = ["Interbody Fusion", "Fusion Surgery"]

        ancestor = await manager.find_common_ancestor("TLIF", "PLIF")
        # ancestor = "Interbody Fusion"
    """

    def __init__(self, neo4j_client: Neo4jClient):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
        """
        self.client = neo4j_client

    async def get_parent_interventions(self, intervention_name: str) -> list[str]:
        """수술법의 상위 항목 조회.

        IS_A 관계를 따라 상위로 이동하여 모든 조상 반환.

        Args:
            intervention_name: 수술법 이름

        Returns:
            상위 수술법 목록 (가까운 순서)
        """
        query = """
        MATCH (child:Intervention {name: $intervention_name})
        OPTIONAL MATCH path = (child)-[:IS_A*1..5]->(parent:Intervention)
        WITH child, collect(DISTINCT parent.name) as parents
        RETURN parents
        """

        try:
            results = await self.client.run_query(
                query,
                {"intervention_name": intervention_name},
                fetch_all=False
            )

            if results and results[0].get("parents"):
                return results[0]["parents"]
            else:
                logger.debug(f"No parents found for {intervention_name}")
                return []

        except Exception as e:
            logger.error(f"Failed to get parents for {intervention_name}: {e}")
            return []

    async def get_child_interventions(self, intervention_name: str) -> list[str]:
        """수술법의 하위 항목 조회.

        IS_A 관계를 역방향으로 탐색하여 모든 하위 항목 반환.

        Args:
            intervention_name: 수술법 이름

        Returns:
            하위 수술법 목록
        """
        try:
            results = await self.client.get_intervention_children(intervention_name)
            return [r["name"] for r in results]

        except Exception as e:
            logger.error(f"Failed to get children for {intervention_name}: {e}")
            return []

    async def find_common_ancestor(
        self,
        intervention1: str,
        intervention2: str
    ) -> Optional[str]:
        """두 수술법의 공통 조상 찾기.

        가장 가까운 공통 조상을 반환하여 두 수술법의 유사도 판단.
        path length를 계산하여 최단 거리의 공통 조상을 보장합니다.

        Args:
            intervention1: 첫 번째 수술법
            intervention2: 두 번째 수술법

        Returns:
            공통 조상 이름 또는 None
        """
        query = """
        MATCH (i1:Intervention {name: $intervention1})
        MATCH (i2:Intervention {name: $intervention2})

        // i1의 모든 조상과 거리
        OPTIONAL MATCH path1 = (i1)-[:IS_A*1..5]->(ancestor1:Intervention)
        WITH i1, i2, collect({name: ancestor1.name, dist: length(path1)}) as ancestors1_with_dist

        // i2의 모든 조상과 거리
        OPTIONAL MATCH path2 = (i2)-[:IS_A*1..5]->(ancestor2:Intervention)
        WITH i1, i2, ancestors1_with_dist, collect({name: ancestor2.name, dist: length(path2)}) as ancestors2_with_dist

        // 공통 조상 찾기 (이름 기준)
        WITH [a1 IN ancestors1_with_dist WHERE any(a2 IN ancestors2_with_dist WHERE a2.name = a1.name) |
              {
                name: a1.name,
                total_dist: a1.dist + [a2 IN ancestors2_with_dist WHERE a2.name = a1.name | a2.dist][0]
              }
        ] as common_ancestors_with_dist

        // 가장 가까운 공통 조상 (총 거리가 최소인 것)
        WITH common_ancestors_with_dist
        ORDER BY common_ancestors_with_dist[0].total_dist ASC
        UNWIND common_ancestors_with_dist as ca
        WITH ca ORDER BY ca.total_dist ASC LIMIT 1

        RETURN ca.name as common_ancestor, ca.total_dist as total_distance
        """

        try:
            results = await self.client.run_query(
                query,
                {
                    "intervention1": intervention1,
                    "intervention2": intervention2
                },
                fetch_all=False
            )

            if results and results[0].get("common_ancestor"):
                ancestor = results[0]["common_ancestor"]
                distance = results[0].get("total_distance", "unknown")
                logger.debug(
                    f"Common ancestor of {intervention1} and {intervention2}: "
                    f"{ancestor} (total distance: {distance})"
                )
                return ancestor
            else:
                logger.debug(f"No common ancestor for {intervention1} and {intervention2}")
                return None

        except Exception as e:
            logger.error(f"Failed to find common ancestor: {e}")
            return None

    async def add_intervention_to_taxonomy(
        self,
        intervention: str,
        parent: str
    ) -> bool:
        """Taxonomy에 새 수술법 추가.

        Args:
            intervention: 추가할 수술법 이름
            parent: 상위 수술법 이름

        Returns:
            성공 여부
        """
        query = """
        MERGE (child:Intervention {name: $intervention})
        MERGE (parent:Intervention {name: $parent})
        MERGE (child)-[:IS_A {level: 1}]->(parent)
        RETURN child, parent
        """

        try:
            await self.client.run_write_query(
                query,
                {
                    "intervention": intervention,
                    "parent": parent
                }
            )
            logger.info(f"Added {intervention} to taxonomy under {parent}")
            return True

        except Exception as e:
            logger.error(f"Failed to add {intervention} to taxonomy: {e}")
            return False

    async def get_full_taxonomy_tree(self) -> dict:
        """전체 Taxonomy 트리 조회.

        계층 구조를 딕셔너리로 반환.

        Returns:
            {
                "Fusion Surgery": {
                    "Interbody Fusion": ["TLIF", "PLIF", "ALIF", ...],
                    "Posterolateral Fusion": [...]
                },
                "Decompression Surgery": {...}
            }
        """
        query = """
        // 최상위 노드 (부모가 없는 노드)
        MATCH (root:Intervention)
        WHERE NOT (root)-[:IS_A]->(:Intervention)

        // 각 루트의 하위 계층 탐색
        OPTIONAL MATCH path = (root)<-[:IS_A*1..3]-(child:Intervention)
        WITH root, collect(DISTINCT {
            name: child.name,
            full_name: child.full_name,
            category: child.category,
            approach: child.approach
        }) as children

        RETURN root.name as root_name,
               root.category as category,
               children
        ORDER BY root.name
        """

        try:
            results = await self.client.run_query(query)

            tree = {}
            for record in results:
                root_name = record["root_name"]
                children = record.get("children", [])

                # 자식들을 카테고리별로 그룹화
                tree[root_name] = {
                    "category": record.get("category", ""),
                    "children": [c["name"] for c in children if c.get("name")]
                }

            logger.debug(f"Retrieved taxonomy tree with {len(tree)} root nodes")
            return tree

        except Exception as e:
            logger.error(f"Failed to get taxonomy tree: {e}")
            return {}

    async def get_intervention_level(self, intervention_name: str) -> int:
        """수술법의 계층 깊이 조회.

        Args:
            intervention_name: 수술법 이름

        Returns:
            계층 깊이 (0: root, 1: 1단계 하위, ...)
        """
        query = """
        MATCH (i:Intervention {name: $intervention_name})
        OPTIONAL MATCH path = (i)-[:IS_A*]->(root:Intervention)
        WHERE NOT (root)-[:IS_A]->(:Intervention)
        RETURN length(path) as level
        """

        try:
            results = await self.client.run_query(
                query,
                {"intervention_name": intervention_name},
                fetch_all=False
            )

            if results and results[0].get("level") is not None:
                return results[0]["level"]
            else:
                # Taxonomy에 없거나 root인 경우
                return 0

        except Exception as e:
            logger.error(f"Failed to get level for {intervention_name}: {e}")
            return 0

    async def get_similar_interventions(
        self,
        intervention_name: str,
        max_distance: int = 2
    ) -> list[dict]:
        """유사한 수술법 찾기.

        같은 부모를 가진 형제 노드 또는 가까운 친척 노드 반환.

        Args:
            intervention_name: 기준 수술법
            max_distance: 최대 거리 (기본 2)

        Returns:
            [{"name": str, "distance": int, "common_ancestor": str}]
        """
        query = """
        MATCH (i:Intervention {name: $intervention_name})

        // 공통 조상을 가진 다른 수술법 찾기
        MATCH (i)-[:IS_A*1..3]->(ancestor:Intervention)<-[:IS_A*1..3]-(similar:Intervention)
        WHERE i <> similar

        // 거리 계산 (공통 조상까지의 거리 합)
        WITH i, similar, ancestor,
             length((i)-[:IS_A*]->(ancestor)) as dist1,
             length((similar)-[:IS_A*]->(ancestor)) as dist2
        WITH similar, ancestor, (dist1 + dist2) as total_distance
        WHERE total_distance <= $max_distance

        RETURN DISTINCT similar.name as name,
               similar.full_name as full_name,
               total_distance as distance,
               ancestor.name as common_ancestor
        ORDER BY total_distance, similar.name
        """

        try:
            results = await self.client.run_query(
                query,
                {
                    "intervention_name": intervention_name,
                    "max_distance": max_distance
                }
            )

            similar = []
            for record in results:
                similar.append({
                    "name": record["name"],
                    "full_name": record.get("full_name", ""),
                    "distance": record["distance"],
                    "common_ancestor": record["common_ancestor"]
                })

            logger.debug(f"Found {len(similar)} similar interventions for {intervention_name}")
            return similar

        except Exception as e:
            logger.error(f"Failed to find similar interventions: {e}")
            return []

    async def validate_taxonomy(self) -> dict[str, list[str]]:
        """Taxonomy 유효성 검증.

        - 고아 노드 (IS_A 관계 없음)
        - 순환 참조
        - 잘못된 레벨

        Returns:
            {"orphans": [...], "cycles": [...], "warnings": [...]}
        """
        issues = {
            "orphans": [],
            "cycles": [],
            "warnings": []
        }

        try:
            # 1. 고아 노드 찾기 (root 제외)
            orphan_query = """
            MATCH (i:Intervention)
            WHERE i.category IN ['fusion', 'decompression', 'osteotomy']
              AND NOT (i)-[:IS_A]->(:Intervention)
              AND NOT (i)<-[:IS_A]-(:Intervention)
            RETURN i.name as orphan
            """

            orphans = await self.client.run_query(orphan_query)
            issues["orphans"] = [r["orphan"] for r in orphans]

            # 2. 순환 참조 감지 (간단한 버전)
            cycle_query = """
            MATCH path = (i:Intervention)-[:IS_A*]->(i)
            RETURN DISTINCT i.name as cycle_node
            """

            cycles = await self.client.run_query(cycle_query)
            issues["cycles"] = [r["cycle_node"] for r in cycles]

            # 3. 레벨 불일치 감지
            level_query = """
            MATCH (child:Intervention)-[r:IS_A]->(parent:Intervention)
            WHERE NOT exists(r.level)
            RETURN child.name as missing_level
            """

            missing_levels = await self.client.run_query(level_query)
            if missing_levels:
                issues["warnings"].extend([
                    f"{r['missing_level']}: missing level attribute"
                    for r in missing_levels
                ])

            if issues["orphans"]:
                logger.warning(f"Found {len(issues['orphans'])} orphan nodes")
            if issues["cycles"]:
                logger.error(f"Found {len(issues['cycles'])} cycles in taxonomy!")

        except Exception as e:
            logger.error(f"Taxonomy validation failed: {e}")
            issues["warnings"].append(f"Validation error: {e}")

        return issues


# 사용 예시
async def example_usage():
    """사용 예시."""
    from .neo4j_client import Neo4jClient

    async with Neo4jClient() as client:
        await client.initialize_schema()

        manager = TaxonomyManager(client)

        # 1. 상위 항목 조회
        parents = await manager.get_parent_interventions("TLIF")
        print(f"Parents of TLIF: {parents}")

        # 2. 하위 항목 조회
        children = await manager.get_child_interventions("Interbody Fusion")
        print(f"Children of Interbody Fusion: {children}")

        # 3. 공통 조상 찾기
        ancestor = await manager.find_common_ancestor("TLIF", "PLIF")
        print(f"Common ancestor of TLIF and PLIF: {ancestor}")

        # 4. 전체 트리 조회
        tree = await manager.get_full_taxonomy_tree()
        print(f"Taxonomy tree: {tree}")

        # 5. 유사 수술법 찾기
        similar = await manager.get_similar_interventions("TLIF", max_distance=2)
        print(f"Similar to TLIF: {similar}")

        # 6. Taxonomy 검증
        issues = await manager.validate_taxonomy()
        print(f"Taxonomy issues: {issues}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())

"""Taxonomy Manager for Multi-Entity Ontology Hierarchy.

엔티티 계층 구조 관리 (Intervention, Pathology, Outcome, Anatomy).
- IS_A 관계를 통한 계층 탐색
- 공통 조상 찾기 (두 엔티티의 유사성 판단)
- 동적 Taxonomy 확장
"""

import logging
from typing import Optional

from core.exceptions import Neo4jError, ValidationError, ErrorCode

from .neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

# Supported entity types for ontology hierarchy
VALID_ENTITY_TYPES = frozenset({"Intervention", "Pathology", "Outcome", "Anatomy"})


def _validate_entity_type(entity_type: str) -> str:
    """Validate and return entity type label for Cypher queries.

    Args:
        entity_type: Entity type name (case-sensitive).

    Returns:
        Validated entity type string.

    Raises:
        ValueError: If entity_type is not in VALID_ENTITY_TYPES.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValidationError(
            message=f"Invalid entity_type '{entity_type}'. "
            f"Must be one of: {sorted(VALID_ENTITY_TYPES)}",
            error_code=ErrorCode.VAL_INVALID_VALUE,
        )
    return entity_type


class TaxonomyManager:
    """엔티티 계층 구조 관리자.

    모든 엔티티 타입(Intervention, Pathology, Outcome, Anatomy)의
    IS_A 계층 구조를 통합 관리합니다.

    사용 예:
        manager = TaxonomyManager(neo4j_client)

        # Intervention (기존 호환)
        parents = await manager.get_parent_interventions("TLIF")

        # Generic (새 API)
        parents = await manager.get_parents("Spinal Stenosis", "Pathology")
        ancestor = await manager.find_common_ancestor_for(
            "VAS Back", "VAS Leg", "Outcome"
        )
    """

    def __init__(self, neo4j_client: Neo4jClient):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트
        """
        self.client = neo4j_client

    # ================================================================
    # GENERIC MULTI-ENTITY METHODS
    # ================================================================

    async def get_parents(
        self,
        entity_name: str,
        entity_type: str,
        max_depth: int = 5,
    ) -> list[str]:
        """엔티티의 상위 항목 조회 (모든 엔티티 타입 지원).

        IS_A 관계를 따라 상위로 이동하여 모든 조상 반환.

        Args:
            entity_name: 엔티티 이름
            entity_type: 엔티티 타입 (Intervention, Pathology, Outcome, Anatomy)
            max_depth: 최대 탐색 깊이

        Returns:
            상위 엔티티 목록 (가까운 순서)
        """
        label = _validate_entity_type(entity_type)
        query = f"""
        MATCH (child:{label} {{name: $entity_name}})
        OPTIONAL MATCH path = (child)-[:IS_A*1..{max_depth}]->(parent:{label})
        WITH child, collect(DISTINCT parent.name) as parents
        RETURN parents
        """

        try:
            results = await self.client.run_query(
                query,
                {"entity_name": entity_name},
                fetch_all=False,
            )

            if results and results[0].get("parents"):
                return results[0]["parents"]
            else:
                logger.debug(f"No parents found for {entity_type}:{entity_name}")
                return []

        except (Neo4jError, OSError) as e:
            logger.error(
                f"Failed to get parents for {entity_type}:{entity_name}: {e}",
                exc_info=True,
            )
            return []

    async def get_children(
        self,
        entity_name: str,
        entity_type: str,
    ) -> list[str]:
        """엔티티의 하위 항목 조회 (모든 엔티티 타입 지원).

        IS_A 관계를 역방향으로 탐색하여 직계 자식 반환.

        Args:
            entity_name: 엔티티 이름
            entity_type: 엔티티 타입

        Returns:
            하위 엔티티 이름 목록
        """
        label = _validate_entity_type(entity_type)

        # For Intervention, delegate to existing DAO method for backward compat
        if entity_type == "Intervention":
            try:
                results = await self.client.get_intervention_children(entity_name)
                return [r["name"] for r in results]
            except (Neo4jError, OSError) as e:
                logger.error(
                    f"Failed to get children for Intervention:{entity_name}: {e}",
                    exc_info=True,
                )
                return []

        # Generic query for other entity types
        query = f"""
        MATCH (parent:{label} {{name: $entity_name}})<-[:IS_A]-(child:{label})
        RETURN child.name as name
        ORDER BY child.name
        """

        try:
            results = await self.client.run_query(
                query, {"entity_name": entity_name}
            )
            return [r["name"] for r in results]

        except (Neo4jError, OSError) as e:
            logger.error(
                f"Failed to get children for {entity_type}:{entity_name}: {e}",
                exc_info=True,
            )
            return []

    async def find_common_ancestor_for(
        self,
        entity1: str,
        entity2: str,
        entity_type: str,
    ) -> Optional[str]:
        """두 엔티티의 공통 조상 찾기 (모든 엔티티 타입 지원).

        가장 가까운 공통 조상을 반환.

        Args:
            entity1: 첫 번째 엔티티
            entity2: 두 번째 엔티티
            entity_type: 엔티티 타입

        Returns:
            공통 조상 이름 또는 None
        """
        label = _validate_entity_type(entity_type)
        query = f"""
        MATCH (i1:{label} {{name: $entity1}})
        MATCH (i2:{label} {{name: $entity2}})

        // i1의 모든 조상과 거리
        OPTIONAL MATCH path1 = (i1)-[:IS_A*1..5]->(ancestor1:{label})
        WITH i1, i2, collect({{name: ancestor1.name, dist: length(path1)}}) as ancestors1_with_dist

        // i2의 모든 조상과 거리
        OPTIONAL MATCH path2 = (i2)-[:IS_A*1..5]->(ancestor2:{label})
        WITH i1, i2, ancestors1_with_dist, collect({{name: ancestor2.name, dist: length(path2)}}) as ancestors2_with_dist

        // 공통 조상 찾기 (이름 기준)
        WITH [a1 IN ancestors1_with_dist WHERE any(a2 IN ancestors2_with_dist WHERE a2.name = a1.name) |
              {{
                name: a1.name,
                total_dist: a1.dist + [a2 IN ancestors2_with_dist WHERE a2.name = a1.name | a2.dist][0]
              }}
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
                {"entity1": entity1, "entity2": entity2},
                fetch_all=False,
            )

            if results and results[0].get("common_ancestor"):
                ancestor = results[0]["common_ancestor"]
                distance = results[0].get("total_distance", "unknown")
                logger.debug(
                    f"Common ancestor of {entity_type}:{entity1} and "
                    f"{entity_type}:{entity2}: {ancestor} (distance: {distance})"
                )
                return ancestor
            else:
                logger.debug(
                    f"No common ancestor for {entity_type}:{entity1} "
                    f"and {entity_type}:{entity2}"
                )
                return None

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to find common ancestor: {e}", exc_info=True)
            return None

    async def add_to_taxonomy(
        self,
        entity_name: str,
        parent_name: str,
        entity_type: str,
    ) -> bool:
        """Taxonomy에 새 엔티티 추가 (모든 엔티티 타입 지원).

        Args:
            entity_name: 추가할 엔티티 이름
            parent_name: 상위 엔티티 이름
            entity_type: 엔티티 타입

        Returns:
            성공 여부
        """
        label = _validate_entity_type(entity_type)
        query = f"""
        MERGE (child:{label} {{name: $entity_name}})
        MERGE (parent:{label} {{name: $parent_name}})
        MERGE (child)-[:IS_A {{level: 1}}]->(parent)
        RETURN child, parent
        """

        try:
            await self.client.run_write_query(
                query,
                {"entity_name": entity_name, "parent_name": parent_name},
            )
            logger.info(
                f"Added {entity_type}:{entity_name} to taxonomy "
                f"under {parent_name}"
            )
            return True

        except (Neo4jError, OSError) as e:
            logger.error(
                f"Failed to add {entity_type}:{entity_name} to taxonomy: {e}",
                exc_info=True,
            )
            return False

    async def get_entity_level(
        self,
        entity_name: str,
        entity_type: str,
    ) -> int:
        """엔티티의 계층 깊이 조회.

        Args:
            entity_name: 엔티티 이름
            entity_type: 엔티티 타입

        Returns:
            계층 깊이 (0: root, 1: 1단계 하위, ...)
        """
        label = _validate_entity_type(entity_type)
        query = f"""
        MATCH (i:{label} {{name: $entity_name}})
        OPTIONAL MATCH path = (i)-[:IS_A*]->(root:{label})
        WHERE NOT (root)-[:IS_A]->(:{label})
        RETURN length(path) as level
        """

        try:
            results = await self.client.run_query(
                query,
                {"entity_name": entity_name},
                fetch_all=False,
            )

            if results and results[0].get("level") is not None:
                return results[0]["level"]
            else:
                return 0

        except (Neo4jError, OSError) as e:
            logger.error(
                f"Failed to get level for {entity_type}:{entity_name}: {e}",
                exc_info=True,
            )
            return 0

    async def get_similar_entities(
        self,
        entity_name: str,
        entity_type: str,
        max_distance: int = 2,
    ) -> list[dict]:
        """유사한 엔티티 찾기 (모든 엔티티 타입 지원).

        같은 부모를 가진 형제 노드 또는 가까운 친척 노드 반환.

        Args:
            entity_name: 기준 엔티티
            entity_type: 엔티티 타입
            max_distance: 최대 거리 (기본 2)

        Returns:
            [{"name": str, "distance": int, "common_ancestor": str}]
        """
        label = _validate_entity_type(entity_type)
        query = f"""
        MATCH (i:{label} {{name: $entity_name}})

        // 공통 조상을 가진 다른 엔티티 찾기
        MATCH (i)-[:IS_A*1..3]->(ancestor:{label})<-[:IS_A*1..3]-(similar:{label})
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
                    "entity_name": entity_name,
                    "max_distance": max_distance,
                },
            )

            similar = []
            for record in results:
                similar.append({
                    "name": record["name"],
                    "full_name": record.get("full_name", ""),
                    "distance": record["distance"],
                    "common_ancestor": record["common_ancestor"],
                })

            logger.debug(
                f"Found {len(similar)} similar entities for "
                f"{entity_type}:{entity_name}"
            )
            return similar

        except (Neo4jError, OSError) as e:
            logger.error(
                f"Failed to find similar entities: {e}", exc_info=True
            )
            return []

    async def get_taxonomy_tree(self, entity_type: str) -> dict:
        """특정 엔티티 타입의 전체 Taxonomy 트리 조회.

        Args:
            entity_type: 엔티티 타입

        Returns:
            {root_name: {"category": str, "children": [str, ...]}}
        """
        label = _validate_entity_type(entity_type)
        query = f"""
        // 최상위 노드 (부모가 없는 노드)
        MATCH (root:{label})
        WHERE NOT (root)-[:IS_A]->(:{label})

        // 각 루트의 하위 계층 탐색
        OPTIONAL MATCH path = (root)<-[:IS_A*1..3]-(child:{label})
        WITH root, collect(DISTINCT {{
            name: child.name,
            full_name: child.full_name,
            category: child.category,
            approach: child.approach
        }}) as children

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

                tree[root_name] = {
                    "category": record.get("category", ""),
                    "children": [c["name"] for c in children if c.get("name")],
                }

            logger.debug(
                f"Retrieved {entity_type} taxonomy tree with "
                f"{len(tree)} root nodes"
            )
            return tree

        except (Neo4jError, OSError) as e:
            logger.error(
                f"Failed to get {entity_type} taxonomy tree: {e}",
                exc_info=True,
            )
            return {}

    async def validate_entity_taxonomy(
        self, entity_type: str
    ) -> dict[str, list[str]]:
        """특정 엔티티 타입의 Taxonomy 유효성 검증.

        Args:
            entity_type: 엔티티 타입

        Returns:
            {"orphans": [...], "cycles": [...], "warnings": [...]}
        """
        label = _validate_entity_type(entity_type)
        issues: dict[str, list[str]] = {
            "orphans": [],
            "cycles": [],
            "warnings": [],
        }

        try:
            # 1. 고아 노드 찾기 (root 제외)
            orphan_query = f"""
            MATCH (i:{label})
            WHERE NOT (i)-[:IS_A]->(:{label})
              AND NOT (i)<-[:IS_A]-(:{label})
            RETURN i.name as orphan
            """

            orphans = await self.client.run_query(orphan_query)
            issues["orphans"] = [r["orphan"] for r in orphans]

            # 2. 순환 참조 감지
            cycle_query = f"""
            MATCH path = (i:{label})-[:IS_A*]->(i)
            RETURN DISTINCT i.name as cycle_node
            """

            cycles = await self.client.run_query(cycle_query)
            issues["cycles"] = [r["cycle_node"] for r in cycles]

            # 3. 레벨 불일치 감지
            level_query = f"""
            MATCH (child:{label})-[r:IS_A]->(parent:{label})
            WHERE r.level IS NULL
            RETURN child.name as missing_level
            """

            missing_levels = await self.client.run_query(level_query)
            if missing_levels:
                issues["warnings"].extend([
                    f"{r['missing_level']}: missing level attribute"
                    for r in missing_levels
                ])

            if issues["orphans"]:
                logger.warning(
                    f"Found {len(issues['orphans'])} orphan {entity_type} nodes"
                )
            if issues["cycles"]:
                logger.error(
                    f"Found {len(issues['cycles'])} cycles in "
                    f"{entity_type} taxonomy!"
                )

        except (Neo4jError, OSError) as e:
            logger.error(
                f"{entity_type} taxonomy validation failed: {e}",
                exc_info=True,
            )
            issues["warnings"].append(f"Validation error: {e}")

        return issues

    # ================================================================
    # BACKWARD-COMPATIBLE INTERVENTION-SPECIFIC METHODS
    # ================================================================

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

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to get parents for {intervention_name}: {e}", exc_info=True)
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

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to get children for {intervention_name}: {e}", exc_info=True)
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

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to find common ancestor: {e}", exc_info=True)
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

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to add {intervention} to taxonomy: {e}", exc_info=True)
            return False

    async def get_full_taxonomy_tree(self) -> dict:
        """전체 엔티티 Taxonomy 트리 조회 (Intervention, Pathology, Outcome, Anatomy).

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

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to get taxonomy tree: {e}", exc_info=True)
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

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to get level for {intervention_name}: {e}", exc_info=True)
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

        except (Neo4jError, OSError) as e:
            logger.error(f"Failed to find similar interventions: {e}", exc_info=True)
            return []

    async def validate_taxonomy(self) -> dict[str, list[str]]:
        """엔티티 Taxonomy 유효성 검증 (Intervention, Pathology, Outcome, Anatomy).

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
            WHERE r.level IS NULL
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

        except (Neo4jError, OSError) as e:
            logger.error(f"Taxonomy validation failed: {e}", exc_info=True)
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

        # === NEW: Multi-entity queries ===
        # 7. Pathology hierarchy
        path_parents = await manager.get_parents("Spinal Stenosis", "Pathology")
        print(f"Parents of Spinal Stenosis: {path_parents}")

        # 8. Outcome hierarchy
        outcome_similar = await manager.get_similar_entities(
            "VAS Back", "Outcome", max_distance=2
        )
        print(f"Similar outcomes to VAS Back: {outcome_similar}")

        # 9. Anatomy hierarchy
        anat_children = await manager.get_children("Cervical Spine", "Anatomy")
        print(f"Children of Cervical Spine: {anat_children}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())

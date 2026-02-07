"""Graph Search for Spine-specific Queries.

Neo4j 기반 그래프 검색.
- Intervention → Outcome 관계 검색
- 수술법 계층 탐색
- 질환별 수술법 검색
- 상충 결과 탐지

v7.14.11: Entity Normalization 적용
- 검색 쿼리 정규화로 동의어 매칭 지원
- IS_A hierarchy를 통한 하위 intervention 포함
"""

import logging
from dataclasses import dataclass
from typing import Optional

# Flexible imports for compatibility
try:
    from src.graph.neo4j_client import Neo4jClient
    from src.graph.spine_schema import CypherTemplates
except ImportError:
    from graph.neo4j_client import Neo4jClient
    from graph.spine_schema import CypherTemplates

# Entity normalizer for search term expansion
try:
    from graph.entity_normalizer import get_normalizer
    NORMALIZER_AVAILABLE = True
except ImportError:
    try:
        from src.graph.entity_normalizer import get_normalizer
        NORMALIZER_AVAILABLE = True
    except ImportError:
        NORMALIZER_AVAILABLE = False
        get_normalizer = None

logger = logging.getLogger(__name__)


@dataclass
class GraphSearchResult:
    """그래프 검색 결과."""
    query: str
    results: list[dict]
    cypher_query: str = ""
    execution_time_ms: float = 0.0


class GraphSearch:
    """Neo4j 기반 그래프 검색.

    척추 수술 관련 구조적 지식 검색.

    사용 예:
        async with GraphSearch() as search:
            results = await search.search_interventions_for_outcome("VAS", "improved")
    """

    def __init__(self, neo4j_client: Optional[Neo4jClient] = None):
        """초기화.

        Args:
            neo4j_client: Neo4j 클라이언트 (None이면 기본 설정 사용)
        """
        self.neo4j_client = neo4j_client or Neo4jClient()
        self._own_client = neo4j_client is None
        self._normalizer = None

    async def __aenter__(self) -> "GraphSearch":
        await self.neo4j_client.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._own_client:
            await self.neo4j_client.close()

    def _normalize_intervention(self, name: str) -> str:
        """Intervention 이름 정규화 (v7.14.11).

        Args:
            name: 원본 intervention 이름

        Returns:
            정규화된 이름 (또는 원본)
        """
        if not NORMALIZER_AVAILABLE or not get_normalizer:
            return name

        try:
            if self._normalizer is None:
                self._normalizer = get_normalizer()

            result = self._normalizer.normalize_intervention(name)
            if result and result.normalized:
                if result.normalized != name:
                    logger.info(f"Normalized intervention: '{name}' -> '{result.normalized}'")
                return result.normalized
        except Exception as e:
            logger.warning(f"Intervention normalization failed: {e}")

        return name

    def _normalize_outcome(self, name: str) -> str:
        """Outcome 이름 정규화 (v7.14.11).

        Args:
            name: 원본 outcome 이름

        Returns:
            정규화된 이름 (또는 원본)
        """
        if not NORMALIZER_AVAILABLE or not get_normalizer:
            return name

        try:
            if self._normalizer is None:
                self._normalizer = get_normalizer()

            result = self._normalizer.normalize_outcome(name)
            if result and result.normalized:
                if result.normalized != name:
                    logger.info(f"Normalized outcome: '{name}' -> '{result.normalized}'")
                return result.normalized
        except Exception as e:
            logger.warning(f"Outcome normalization failed: {e}")

        return name

    async def search_interventions_for_outcome(
        self,
        outcome_name: str,
        direction: str = "improved",
        limit: int = 20
    ) -> GraphSearchResult:
        """특정 결과변수에 효과적인 수술법 검색.

        v7.14.11: Entity Normalization 및 Fuzzy 매칭 지원
        - Outcome 이름 정규화
        - Fuzzy 검색으로 유사한 outcome도 포함

        Args:
            outcome_name: 결과변수 이름 (예: "VAS", "Fusion Rate")
            direction: 효과 방향 ("improved", "worsened", "unchanged")
            limit: 결과 개수 제한

        Returns:
            GraphSearchResult

        Example:
            결과: [
                {
                    "intervention": "TLIF",
                    "value": "2.3",
                    "value_control": "4.5",
                    "p_value": 0.001,
                    "source_paper_id": "paper_001"
                }
            ]
        """
        # 1. Normalize outcome name
        normalized_outcome = self._normalize_outcome(outcome_name)

        # 2. Exact match query
        cypher = """
        MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome {name: $outcome_name})
        WHERE a.is_significant = true AND a.direction = $direction
        RETURN i.name as intervention,
               i.full_name as full_name,
               i.category as category,
               a.value as value,
               a.value_control as value_control,
               a.p_value as p_value,
               a.effect_size as effect_size,
               a.confidence_interval as confidence_interval,
               a.source_paper_id as source_paper_id,
               o.name as matched_outcome
        ORDER BY a.p_value ASC
        LIMIT $limit
        """

        try:
            import time
            start = time.perf_counter()

            results = await self.neo4j_client.run_query(
                cypher,
                {
                    "outcome_name": normalized_outcome,
                    "direction": direction,
                    "limit": limit
                }
            )

            # 3. If no results, try fuzzy matching
            if not results:
                logger.info(f"No exact match for '{normalized_outcome}', trying fuzzy match")

                fuzzy_cypher = """
                MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
                WHERE a.is_significant = true AND a.direction = $direction
                  AND (
                    toLower(o.name) CONTAINS toLower($outcome_partial)
                    OR toLower($outcome_partial) CONTAINS toLower(o.name)
                  )
                RETURN i.name as intervention,
                       i.full_name as full_name,
                       i.category as category,
                       a.value as value,
                       a.value_control as value_control,
                       a.p_value as p_value,
                       a.effect_size as effect_size,
                       a.confidence_interval as confidence_interval,
                       a.source_paper_id as source_paper_id,
                       o.name as matched_outcome
                ORDER BY a.p_value ASC
                LIMIT $limit
                """

                # Extract key word from outcome
                outcome_partial = normalized_outcome.split()[0] if ' ' in normalized_outcome else normalized_outcome

                results = await self.neo4j_client.run_query(
                    fuzzy_cypher,
                    {
                        "outcome_partial": outcome_partial,
                        "direction": direction,
                        "limit": limit
                    }
                )

            execution_time = (time.perf_counter() - start) * 1000

            logger.info(
                f"Found {len(results)} interventions for outcome '{outcome_name}' "
                f"(normalized: '{normalized_outcome}') with direction '{direction}'"
            )

            return GraphSearchResult(
                query=f"interventions_for_outcome({outcome_name}, {direction})",
                results=results,
                cypher_query=cypher,
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Graph search error: {e}")
            return GraphSearchResult(
                query=f"interventions_for_outcome({outcome_name}, {direction})",
                results=[],
                cypher_query=cypher
            )

    async def search_interventions_for_pathology(
        self,
        pathology_name: str,
        limit: int = 20
    ) -> GraphSearchResult:
        """질환별 수술법 검색.

        Args:
            pathology_name: 질환명 (예: "Lumbar Stenosis", "AIS")
            limit: 결과 개수 제한

        Returns:
            GraphSearchResult

        Example:
            결과: [
                {
                    "intervention": "UBE",
                    "indication": "Central stenosis",
                    "outcomes": [
                        {"outcome": "VAS", "value": "2.3"}
                    ]
                }
            ]
        """
        cypher = CypherTemplates.SEARCH_INTERVENTIONS_FOR_PATHOLOGY + " LIMIT $limit"

        try:
            import time
            start = time.perf_counter()

            results = await self.neo4j_client.run_query(
                cypher,
                {
                    "pathology_name": pathology_name,
                    "limit": limit
                }
            )

            execution_time = (time.perf_counter() - start) * 1000

            logger.info(
                f"Found {len(results)} interventions for pathology '{pathology_name}'"
            )

            return GraphSearchResult(
                query=f"interventions_for_pathology({pathology_name})",
                results=results,
                cypher_query=cypher,
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Graph search error: {e}")
            return GraphSearchResult(
                query=f"interventions_for_pathology({pathology_name})",
                results=[],
                cypher_query=cypher
            )

    async def get_intervention_hierarchy(
        self,
        intervention_name: str
    ) -> dict:
        """수술법 계층 조회.

        Args:
            intervention_name: 수술법 이름 (예: "TLIF")

        Returns:
            계층 정보

        Example:
            {
                "name": "TLIF",
                "full_name": "Transforaminal Lumbar Interbody Fusion",
                "parents": ["Interbody Fusion", "Fusion Surgery"],
                "children": []
            }
        """
        # 1. 부모 계층 조회
        parent_cypher = CypherTemplates.GET_INTERVENTION_HIERARCHY

        # 2. 자식 계층 조회
        child_cypher = CypherTemplates.GET_INTERVENTION_CHILDREN

        try:
            # 부모 계층
            parent_results = await self.neo4j_client.run_query(
                parent_cypher,
                {"intervention_name": intervention_name}
            )

            # 자식 계층
            child_results = await self.neo4j_client.run_query(
                child_cypher,
                {"intervention_name": intervention_name}
            )

            # 결과 구성
            if not parent_results:
                logger.warning(f"Intervention not found: {intervention_name}")
                return {
                    "name": intervention_name,
                    "full_name": "",
                    "parents": [],
                    "children": []
                }

            # 기본 정보
            info = parent_results[0].get("i", {})
            hierarchy_nodes = parent_results[0].get("hierarchy", [])

            # 부모 목록 추출
            parents = []
            if hierarchy_nodes:
                for path in hierarchy_nodes:
                    for node in path:
                        if isinstance(node, dict) and node.get("name") != intervention_name:
                            parents.append(node.get("name"))

            # 자식 목록 추출
            children = [r.get("name", "") for r in child_results if r.get("name")]

            return {
                "name": info.get("name", intervention_name),
                "full_name": info.get("full_name", ""),
                "category": info.get("category", ""),
                "approach": info.get("approach", ""),
                "is_minimally_invasive": info.get("is_minimally_invasive", False),
                "parents": parents,
                "children": children
            }

        except Exception as e:
            logger.error(f"Error getting intervention hierarchy: {e}")
            return {
                "name": intervention_name,
                "full_name": "",
                "parents": [],
                "children": []
            }

    async def find_conflicting_results(
        self,
        intervention_name: str,
        outcome_name: Optional[str] = None
    ) -> GraphSearchResult:
        """상충 결과 검색.

        같은 수술법에 대해 서로 다른 방향의 결과를 보고한 연구 탐지.

        Args:
            intervention_name: 수술법 이름
            outcome_name: 결과변수 이름 (None이면 모든 결과변수)

        Returns:
            GraphSearchResult

        Example:
            결과: [
                {
                    "intervention1": "OLIF",
                    "intervention2": "TLIF",
                    "outcome": "Canal Area",
                    "dir1": "improved",
                    "dir2": "unchanged",
                    "paper1": "paper_001",
                    "paper2": "paper_002"
                }
            ]
        """
        if outcome_name:
            # 특정 결과변수에 대한 상충
            cypher = """
            MATCH (i:Intervention {name: $intervention_name})-[a1:AFFECTS]->(o:Outcome {name: $outcome_name})
            MATCH (i)-[a2:AFFECTS]->(o)
            WHERE a1.direction <> a2.direction
              AND a1.is_significant = true AND a2.is_significant = true
              AND a1.source_paper_id <> a2.source_paper_id
            RETURN i.name as intervention,
                   o.name as outcome,
                   a1.direction as direction1,
                   a2.direction as direction2,
                   a1.value as value1,
                   a2.value as value2,
                   a1.p_value as p_value1,
                   a2.p_value as p_value2,
                   a1.source_paper_id as paper1,
                   a2.source_paper_id as paper2
            """
            params = {
                "intervention_name": intervention_name,
                "outcome_name": outcome_name
            }
        else:
            # 모든 결과변수에 대한 상충
            cypher = """
            MATCH (i:Intervention {name: $intervention_name})-[a1:AFFECTS]->(o:Outcome)
            MATCH (i)-[a2:AFFECTS]->(o)
            WHERE a1.direction <> a2.direction
              AND a1.is_significant = true AND a2.is_significant = true
              AND a1.source_paper_id <> a2.source_paper_id
            RETURN i.name as intervention,
                   o.name as outcome,
                   a1.direction as direction1,
                   a2.direction as direction2,
                   a1.value as value1,
                   a2.value as value2,
                   a1.p_value as p_value1,
                   a2.p_value as p_value2,
                   a1.source_paper_id as paper1,
                   a2.source_paper_id as paper2
            """
            params = {"intervention_name": intervention_name}

        try:
            import time
            start = time.perf_counter()

            results = await self.neo4j_client.run_query(cypher, params)

            execution_time = (time.perf_counter() - start) * 1000

            logger.info(
                f"Found {len(results)} conflicting results for '{intervention_name}'"
            )

            return GraphSearchResult(
                query=f"conflicting_results({intervention_name}, {outcome_name})",
                results=results,
                cypher_query=cypher,
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Graph search error: {e}")
            return GraphSearchResult(
                query=f"conflicting_results({intervention_name}, {outcome_name})",
                results=[],
                cypher_query=cypher
            )

    async def get_paper_evidence(
        self,
        paper_id: str
    ) -> dict:
        """논문의 모든 근거 데이터 조회.

        Args:
            paper_id: 논문 ID

        Returns:
            논문 정보 및 관계

        Example:
            {
                "paper": {...},
                "pathologies": [...],
                "interventions": [...],
                "outcomes": [...]
            }
        """
        cypher = """
        MATCH (p:Paper {paper_id: $paper_id})
        OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
        OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
        OPTIONAL MATCH (i)-[a:AFFECTS]->(o:Outcome)
        WHERE a.source_paper_id = $paper_id
        RETURN p,
               collect(DISTINCT path.name) as pathologies,
               collect(DISTINCT i.name) as interventions,
               collect(DISTINCT {
                   outcome: o.name,
                   value: a.value,
                   p_value: a.p_value,
                   direction: a.direction
               }) as outcomes
        """

        try:
            results = await self.neo4j_client.run_query(
                cypher,
                {"paper_id": paper_id},
                fetch_all=False
            )

            if not results:
                logger.warning(f"Paper not found: {paper_id}")
                return {
                    "paper": None,
                    "pathologies": [],
                    "interventions": [],
                    "outcomes": []
                }

            result = results[0]
            return {
                "paper": result.get("p", {}),
                "pathologies": result.get("pathologies", []),
                "interventions": result.get("interventions", []),
                "outcomes": [o for o in result.get("outcomes", []) if o.get("outcome")]
            }

        except Exception as e:
            logger.error(f"Error getting paper evidence: {e}")
            return {
                "paper": None,
                "pathologies": [],
                "interventions": [],
                "outcomes": []
            }

    async def search_by_evidence_level(
        self,
        evidence_level: str,
        sub_domain: Optional[str] = None,
        limit: int = 50
    ) -> GraphSearchResult:
        """근거 수준별 논문 검색.

        Args:
            evidence_level: 근거 수준 ("1a", "1b", "2a", "2b", "3", "4")
            sub_domain: 척추 하위도메인 (선택)
            limit: 결과 개수 제한

        Returns:
            GraphSearchResult
        """
        cypher = """
        MATCH (p:Paper {evidence_level: $evidence_level})
        """

        params = {
            "evidence_level": evidence_level,
            "limit": limit
        }

        if sub_domain:
            cypher += " WHERE p.sub_domain = $sub_domain"
            params["sub_domain"] = sub_domain

        cypher += """
        RETURN p.paper_id as paper_id,
               p.title as title,
               p.year as year,
               p.journal as journal,
               p.sub_domain as sub_domain,
               p.study_design as study_design
        ORDER BY p.year DESC
        LIMIT $limit
        """

        try:
            import time
            start = time.perf_counter()

            results = await self.neo4j_client.run_query(cypher, params)

            execution_time = (time.perf_counter() - start) * 1000

            logger.info(
                f"Found {len(results)} papers with evidence level '{evidence_level}'"
            )

            return GraphSearchResult(
                query=f"papers_by_evidence_level({evidence_level}, {sub_domain})",
                results=results,
                cypher_query=cypher,
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Graph search error: {e}")
            return GraphSearchResult(
                query=f"papers_by_evidence_level({evidence_level}, {sub_domain})",
                results=[],
                cypher_query=cypher
            )


# 사용 예시
async def example_usage():
    """사용 예시."""
    async with GraphSearch() as search:
        # 1. VAS 개선에 효과적인 수술법 검색
        result = await search.search_interventions_for_outcome("VAS", "improved")
        print(f"Found {len(result.results)} interventions for VAS improvement")
        for r in result.results[:3]:
            print(f"  {r['intervention']}: {r['value']} (p={r['p_value']})")

        # 2. Lumbar Stenosis 치료 수술법 검색
        result = await search.search_interventions_for_pathology("Lumbar Stenosis")
        print(f"\nFound {len(result.results)} interventions for Lumbar Stenosis")

        # 3. TLIF 계층 구조 조회
        hierarchy = await search.get_intervention_hierarchy("TLIF")
        print(f"\nTLIF hierarchy:")
        print(f"  Parents: {hierarchy['parents']}")
        print(f"  Children: {hierarchy['children']}")

        # 4. 상충 결과 검색
        result = await search.find_conflicting_results("OLIF")
        print(f"\nFound {len(result.results)} conflicting results for OLIF")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())

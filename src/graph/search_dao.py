"""SearchDAO - Search operations extracted from Neo4jClient.

Handles vector search, hybrid search, intervention hierarchy,
and conflict detection queries.

Part of D-005: Neo4jClient God Object decomposition.
"""

import logging
from typing import Any, Callable, Optional

from .spine_schema import CypherTemplates

logger = logging.getLogger(__name__)


class SearchDAO:
    """Search-related data access operations.

    Extracted from Neo4jClient to reduce God Object complexity.
    Uses Composition + Delegation pattern.

    Args:
        run_query: Callable for executing read queries (Neo4jClient.run_query).
    """

    def __init__(self, run_query: Callable) -> None:
        self._run_query = run_query

    async def vector_search_chunks(
        self,
        embedding: list[float],
        top_k: int = 10,
        tier: Optional[str] = None,
        evidence_level: Optional[str] = None,
        evidence_levels: Optional[list[str]] = None,
        min_year: Optional[int] = None,
        min_score: float = 0.5,
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

        return await self._run_query(query, params)

    async def hybrid_search(
        self,
        embedding: list[float],
        graph_filters: Optional[dict] = None,
        top_k: int = 10,
        graph_weight: float = 0.6,
        vector_weight: float = 0.4,
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

        return await self._run_query(query, params)

    async def get_intervention_hierarchy(self, intervention_name: str) -> list[dict]:
        """수술법 계층 조회."""
        return await self._run_query(
            CypherTemplates.GET_INTERVENTION_HIERARCHY,
            {"intervention_name": intervention_name},
        )

    async def get_intervention_children(self, intervention_name: str) -> list[dict]:
        """수술법 하위 항목 조회."""
        return await self._run_query(
            CypherTemplates.GET_INTERVENTION_CHILDREN,
            {"intervention_name": intervention_name},
        )

    async def search_effective_interventions(self, outcome_name: str) -> list[dict]:
        """효과적인 수술법 검색."""
        return await self._run_query(
            CypherTemplates.SEARCH_EFFECTIVE_INTERVENTIONS,
            {"outcome_name": outcome_name},
        )

    async def search_interventions_for_pathology(self, pathology_name: str) -> list[dict]:
        """질환별 수술법 검색."""
        return await self._run_query(
            CypherTemplates.SEARCH_INTERVENTIONS_FOR_PATHOLOGY,
            {"pathology_name": pathology_name},
        )

    async def find_conflicting_results(self, intervention_name: str) -> list[dict]:
        """상충 결과 검색."""
        return await self._run_query(
            CypherTemplates.FIND_CONFLICTING_RESULTS,
            {"intervention_name": intervention_name},
        )

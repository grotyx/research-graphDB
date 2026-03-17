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

        Raises:
            Exception: Neo4j 쿼리 실패 시 로깅 후 빈 리스트 반환
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

        try:
            return await self._run_query(query, params)
        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []

    async def hybrid_search(
        self,
        embedding: list[float],
        graph_filters: Optional[dict] = None,
        top_k: int = 10,
        graph_weight: float = 0.6,
        vector_weight: float = 0.4,
        snomed_codes: Optional[list[str]] = None,
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
            snomed_codes: Optional SNOMED codes for IS_A hierarchy expansion

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

        # 그래프 필터 적용 (plural lists take precedence over singular)
        # MATCH 패턴 필터와 WHERE 스칼라 필터를 분리
        match_filters = []
        where_filters = []

        if graph_filters.get("interventions"):
            match_filters.append("MATCH (p)-[:INVESTIGATES]->(int:Intervention) WHERE int.name IN $interventions")
            params["interventions"] = graph_filters["interventions"]
        elif graph_filters.get("intervention"):
            match_filters.append("MATCH (p)-[:INVESTIGATES]->(:Intervention {name: $intervention})")
            params["intervention"] = graph_filters["intervention"]

        if graph_filters.get("pathologies"):
            match_filters.append("MATCH (p)-[:STUDIES]->(path:Pathology) WHERE path.name IN $pathologies")
            params["pathologies"] = graph_filters["pathologies"]
        elif graph_filters.get("pathology"):
            match_filters.append("MATCH (p)-[:STUDIES]->(:Pathology {name: $pathology})")
            params["pathology"] = graph_filters["pathology"]

        if graph_filters.get("outcomes"):
            match_filters.append("MATCH (p)-[:INVESTIGATES]->(:Intervention)-[:AFFECTS]->(out:Outcome) WHERE out.name IN $outcomes")
            params["outcomes"] = graph_filters["outcomes"]
        elif graph_filters.get("outcome"):
            match_filters.append("MATCH (p)-[:INVESTIGATES]->(:Intervention)-[:AFFECTS]->(:Outcome {name: $outcome})")
            params["outcome"] = graph_filters["outcome"]

        if graph_filters.get("anatomies"):
            match_filters.append("MATCH (p)-[:INVOLVES]->(anat:Anatomy) WHERE anat.name IN $anatomies")
            params["anatomies"] = graph_filters["anatomies"]
        elif graph_filters.get("anatomy"):
            match_filters.append("MATCH (p)-[:INVOLVES]->(:Anatomy {name: $anatomy})")
            params["anatomy"] = graph_filters["anatomy"]

        if graph_filters.get("evidence_levels"):
            where_filters.append("p.evidence_level IN $evidence_levels")
            params["evidence_levels"] = graph_filters["evidence_levels"]

        if graph_filters.get("min_year"):
            where_filters.append("p.year >= $min_year")
            params["min_year"] = graph_filters["min_year"]

        # MATCH 패턴은 별도 MATCH 절로, 스칼라 조건만 WHERE 절로
        for mf in match_filters:
            query += f"\n        {mf}"
        if where_filters:
            query += "\n        WHERE " + " AND ".join(where_filters)

        # SNOMED IS_A hierarchy expansion (optional ontology-aware filter)
        # Covers all 4 entity types:
        #   INVESTIGATES → Intervention, STUDIES → Pathology,
        #   INVOLVES → Anatomy, INVESTIGATES→AFFECTS → Outcome (via Intervention)
        if snomed_codes:
            snomed_subquery = """
        WITH c, p, vector_score
        OPTIONAL MATCH (p)-[:INVESTIGATES|STUDIES|INVOLVES]->(direct_target)
        WHERE direct_target.snomed_code IN $snomed_codes
           OR EXISTS {
               MATCH (direct_target)-[:IS_A*1..2]->(ancestor)
               WHERE ancestor.snomed_code IN $snomed_codes
           }
           OR EXISTS {
               MATCH (descendant)-[:IS_A*1..2]->(direct_target)
               WHERE descendant.snomed_code IN $snomed_codes
           }
        WITH c, p, vector_score, direct_target
        OPTIONAL MATCH (p)-[:INVESTIGATES]->(:Intervention)-[:AFFECTS]->(outcome_target:Outcome)
        WHERE outcome_target.snomed_code IN $snomed_codes
           OR EXISTS {
               MATCH (outcome_target)-[:IS_A*1..2]->(ancestor)
               WHERE ancestor.snomed_code IN $snomed_codes
           }
           OR EXISTS {
               MATCH (descendant)-[:IS_A*1..2]->(outcome_target)
               WHERE descendant.snomed_code IN $snomed_codes
           }
        WITH c, p, vector_score,
             CASE WHEN direct_target IS NOT NULL THEN direct_target ELSE outcome_target END as target
        WITH c, p, vector_score, target,
             CASE
                 WHEN target IS NULL THEN null
                 WHEN target.snomed_code IN $snomed_codes THEN 0
                 WHEN EXISTS { MATCH (target)-[:IS_A]->(a1) WHERE a1.snomed_code IN $snomed_codes } THEN 1
                 ELSE 2
             END as ontology_distance
        WITH c, p, vector_score, ontology_distance,
             CASE ontology_distance
                 WHEN 0 THEN 1.0
                 WHEN 1 THEN 0.85
                 WHEN 2 THEN 0.7
                 ELSE 0.5
             END as snomed_boost
            """
            query += snomed_subquery
            params["snomed_codes"] = snomed_codes

            # 그래프 점수 계산 with SNOMED boost
            query += """
        WITH c, p, vector_score, snomed_boost, ontology_distance,
             CASE p.evidence_level
                 WHEN '1a' THEN 1.0
                 WHEN '1b' THEN 1.0
                 WHEN '2a' THEN 0.9
                 WHEN '2b' THEN 0.75
                 WHEN '3' THEN 0.5
                 WHEN '4' THEN 0.3
                 ELSE 0.15
             END as evidence_score
        WITH c, p, vector_score, evidence_score * snomed_boost as graph_score,
             ($graph_weight * evidence_score * snomed_boost + $vector_weight * vector_score) as final_score,
             ontology_distance
            """
        else:
            # 그래프 점수 계산 (evidence level 기반)
            query += """
        WITH c, p, vector_score,
             CASE p.evidence_level
                 WHEN '1a' THEN 1.0
                 WHEN '1b' THEN 1.0
                 WHEN '2a' THEN 0.9
                 WHEN '2b' THEN 0.75
                 WHEN '3' THEN 0.5
                 WHEN '4' THEN 0.3
                 ELSE 0.15
             END as graph_score
        WITH c, p, vector_score, graph_score,
             ($graph_weight * graph_score + $vector_weight * vector_score) as final_score,
             null as ontology_distance
            """

        params["graph_weight"] = graph_weight
        params["vector_weight"] = vector_weight

        query += """
        RETURN c.chunk_id as chunk_id,
               c.paper_id as paper_id,
               c.content as content,
               c.tier as tier,
               c.section as section,
               c.is_key_finding as is_key_finding,
               p.title as paper_title,
               p.evidence_level as evidence_level,
               p.year as year,
               vector_score,
               graph_score,
               final_score,
               ontology_distance
        ORDER BY final_score DESC
        LIMIT $limit
        """
        params["limit"] = top_k

        try:
            return await self._run_query(query, params)
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            return []

    async def multi_vector_search(
        self,
        embedding: list[float],
        top_k: int = 10,
        min_score: float = 0.5,
        rrf_k: int = 60,
    ) -> list[dict]:
        """Multi-vector search using chunk + paper abstract embeddings with RRF fusion.

        Searches both the chunk_embedding_index and paper_abstract_index,
        then merges results using Reciprocal Rank Fusion (RRF) to produce a
        single ranked list. Paper-level results are mapped back to their
        chunks so the return format is consistent with vector_search_chunks().

        Args:
            embedding: Query embedding (3072d OpenAI).
            top_k: Number of results to return.
            min_score: Minimum cosine similarity threshold.
            rrf_k: RRF constant (default 60).

        Returns:
            Chunk result dicts ranked by combined RRF score.
        """
        # --- 1. Chunk-level vector search ---
        chunk_query = """
        CALL db.index.vector.queryNodes('chunk_embedding_index', $top_k_fetch, $embedding)
        YIELD node as c, score
        WHERE score >= $min_score
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
        chunk_params: dict[str, Any] = {
            "embedding": embedding,
            "top_k_fetch": top_k * 3,
            "min_score": min_score,
            "limit": top_k * 2,  # fetch extra for RRF merge
        }

        # --- 2. Paper abstract-level vector search ---
        paper_query = """
        CALL db.index.vector.queryNodes('paper_abstract_index', $top_k_fetch, $embedding)
        YIELD node as p, score as paper_score
        WHERE paper_score >= $min_score
        MATCH (p)-[:HAS_CHUNK]->(c:Chunk)
        RETURN c.chunk_id as chunk_id,
               c.paper_id as paper_id,
               c.content as content,
               c.tier as tier,
               c.section as section,
               c.evidence_level as evidence_level,
               c.is_key_finding as is_key_finding,
               p.title as paper_title,
               p.year as paper_year,
               paper_score as score
        ORDER BY paper_score DESC, c.tier ASC
        LIMIT $limit
        """
        paper_params: dict[str, Any] = {
            "embedding": embedding,
            "top_k_fetch": top_k * 2,
            "min_score": min_score,
            "limit": top_k * 2,
        }

        # Execute both queries
        try:
            chunk_results = await self._run_query(chunk_query, chunk_params)
        except Exception as e:
            logger.error(f"Multi-vector chunk search failed: {e}", exc_info=True)
            chunk_results = []

        try:
            paper_results = await self._run_query(paper_query, paper_params)
        except Exception as e:
            logger.warning(f"Multi-vector paper search failed (fallback to chunk only): {e}")
            paper_results = []

        # --- 3. RRF Fusion ---
        # Build rank maps keyed by chunk_id
        chunk_ranks: dict[str, int] = {}
        chunk_data: dict[str, dict] = {}
        for rank, row in enumerate(chunk_results):
            cid = row.get("chunk_id", "")
            if cid:
                chunk_ranks[cid] = rank
                chunk_data[cid] = row

        paper_ranks: dict[str, int] = {}
        for rank, row in enumerate(paper_results):
            cid = row.get("chunk_id", "")
            if cid:
                if cid not in paper_ranks:  # first occurrence = best rank
                    paper_ranks[cid] = rank
                if cid not in chunk_data:
                    chunk_data[cid] = row

        # Calculate RRF scores
        all_chunk_ids = set(chunk_ranks.keys()) | set(paper_ranks.keys())
        rrf_scores: dict[str, float] = {}
        for cid in all_chunk_ids:
            score = 0.0
            if cid in chunk_ranks:
                score += 1.0 / (rrf_k + chunk_ranks[cid] + 1)
            if cid in paper_ranks:
                score += 1.0 / (rrf_k + paper_ranks[cid] + 1)
            rrf_scores[cid] = score

        # Sort by RRF score and return top_k
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        results = []
        for cid in sorted_ids[:top_k]:
            row = chunk_data[cid]
            row = dict(row)  # copy to avoid mutating cached result
            row["score"] = rrf_scores[cid]
            results.append(row)

        logger.info(
            f"Multi-vector search: {len(chunk_results)} chunk + "
            f"{len(paper_results)} paper results -> {len(results)} merged"
        )
        return results

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

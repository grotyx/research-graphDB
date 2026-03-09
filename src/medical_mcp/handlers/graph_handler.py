"""Graph Handler for MCP Server.

Handles graph-related operations including:
- Paper relations and evidence chains
- Topic clustering
- Intervention hierarchy and taxonomy
- Intervention comparison

Extracted from medical_kag_server.py to improve modularity.
"""

import logging
from typing import Optional

from medical_mcp.handlers.base_handler import BaseHandler, safe_execute
from core.exceptions import ValidationError

# Configure logging
logger = logging.getLogger("medical-kag.graph-handler")


class GraphHandler(BaseHandler):
    """Handler for graph-based operations.

    Manages Neo4j graph queries including paper relations, evidence chains,
    topic clusters, and intervention taxonomy operations.
    """

    def __init__(self, server):
        """Initialize graph handler.

        Args:
            server: MedicalKAGServer instance providing access to:
                - neo4j_client: Neo4j database client
                - graph_searcher: Graph search functionality
                - cypher_generator: Cypher query generation
                - taxonomy_manager: Intervention taxonomy management
                - ranker: Evidence-based ranking
        """
        super().__init__(server)
        self.graph_searcher = server.graph_searcher
        self.cypher_generator = server.cypher_generator
        self.taxonomy_manager = server.taxonomy_manager
        self.ranker = server.ranker

    @safe_execute
    async def get_paper_relations(
        self,
        paper_id: str,
        relation_type: Optional[str] = None
    ) -> dict:
        """논문의 관계 정보 조회 (Neo4j 기반).

        Args:
            paper_id: 논문 ID
            relation_type: 관계 유형 필터 (SUPPORTS, CONTRADICTS, SIMILAR_TOPIC, CITES, EXTENDS, REPLICATES)

        Returns:
            관계 정보 딕셔너리
        """
        self._require_neo4j()

        # Ensure Neo4j is connected
        await self._ensure_connected()

        # 논문 정보 조회
        paper_result = await self.neo4j_client.get_paper(paper_id)
        if not paper_result:
            return {"success": False, "error": f"Paper not found: {paper_id}"}

        # Extract paper node from result
        paper = paper_result.get("p", {})

        # 관계 조회 (relation_type 필터 적용)
        relation_types = None
        if relation_type:
            # Validate and convert to uppercase
            valid_types = {"SUPPORTS", "CONTRADICTS", "SIMILAR_TOPIC", "EXTENDS", "CITES", "REPLICATES"}
            rel_type_upper = relation_type.upper()
            if rel_type_upper in valid_types:
                relation_types = [rel_type_upper]

        relations = await self.neo4j_client.get_paper_relations(
            paper_id,
            relation_types=relation_types,
            direction="both"
        )

        # 지지/상충/유사 논문 조회 (각각 최대 5개)
        supporting_results = await self.neo4j_client.get_supporting_papers(paper_id, limit=5)
        contradicting_results = await self.neo4j_client.get_contradicting_papers(paper_id, limit=5)
        similar_results = await self.neo4j_client.get_similar_papers(paper_id, limit=5)

        # Format results for UI compatibility
        supporting_papers = []
        for result in supporting_results:
            target = result.get("target", {})
            supporting_papers.append({
                "id": target.get("paper_id", ""),
                "title": target.get("title", ""),
                "confidence": result.get("confidence", 0.0)
            })

        contradicting_papers = []
        for result in contradicting_results:
            target = result.get("target", {})
            contradicting_papers.append({
                "id": target.get("paper_id", ""),
                "title": target.get("title", ""),
                "confidence": result.get("confidence", 0.0)
            })

        similar_papers = []
        for result in similar_results:
            target = result.get("target", {})
            similar_papers.append({
                "id": target.get("paper_id", ""),
                "title": target.get("title", ""),
                "similarity": result.get("confidence", 0.0)
            })

        # Format relations
        formatted_relations = []
        for rel in relations:
            target = rel.get("target", {})
            formatted_relations.append({
                "source": paper_id,
                "target": target.get("paper_id", ""),
                "type": rel.get("relation_type", ""),
                "confidence": rel.get("confidence", 0.0),
                "evidence": rel.get("evidence", ""),
            })

        return {
            "success": True,
            "paper": {
                "id": paper.get("paper_id", ""),
                "title": paper.get("title", ""),
                "year": paper.get("year", 0),
                "evidence_level": paper.get("evidence_level", ""),
            },
            "relations": formatted_relations,
            "supporting_papers": supporting_papers,
            "contradicting_papers": contradicting_papers,
            "similar_papers": similar_papers,
        }

    @safe_execute
    async def find_evidence_chain(
        self,
        claim: str,
        max_papers: int = 5
    ) -> dict:
        """주장을 뒷받침하는 논문 체인 찾기 (Neo4j 기반).

        claim에서 키워드를 추출하고 관련 논문과 AFFECTS 관계를 검색.
        v1.14.20: 벡터 유사도 검색 fallback 추가

        Args:
            claim: 검증할 주장
            max_papers: 최대 논문 수

        Returns:
            증거 체인 정보
        """
        self._require_neo4j()
        await self._ensure_connected()

        # 1. 먼저 텍스트 매칭으로 검색
        search_query = """
        CALL db.index.fulltext.queryNodes('paper_text_search', $claim)
        YIELD node AS p
        WITH p
        LIMIT $limit

        OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
        OPTIONAL MATCH (i)-[r:AFFECTS]->(o:Outcome)
        WHERE r.source_paper_id = p.paper_id

        RETURN p.paper_id AS paper_id,
               p.title AS title,
               p.year AS year,
               p.evidence_level AS evidence_level,
               collect(DISTINCT {
                   intervention: i.name,
                   outcome: o.name,
                   direction: r.direction,
                   p_value: r.p_value,
                   is_significant: r.is_significant
               }) AS evidence
        ORDER BY p.evidence_level, p.year DESC
        """

        results = await self.neo4j_client.run_query(
            search_query,
            {"claim": claim, "limit": max_papers * 2}
        )

        # 2. 텍스트 매칭 결과가 없으면 벡터 유사도 검색 시도
        if not results:
            logger.info(f"Text matching found no results, trying vector search for: {claim}")
            try:
                from core.embedding import get_embedding_generator
                generator = get_embedding_generator()
                claim_embedding = generator.generate(claim)

                if claim_embedding:
                    # Neo4j 벡터 검색
                    vector_results = await self.neo4j_client.hybrid_search(
                        embedding=claim_embedding,
                        top_k=max_papers * 2
                    )

                    if vector_results:
                        # 벡터 검색 결과에서 paper_id 추출 후 상세 정보 조회
                        paper_ids = [r.get("paper_id") for r in vector_results if r.get("paper_id")]
                        if paper_ids:
                            detail_query = """
                            UNWIND $paper_ids AS pid
                            MATCH (p:Paper {paper_id: pid})
                            OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
                            OPTIONAL MATCH (i)-[r:AFFECTS]->(o:Outcome)
                            WHERE r.source_paper_id = p.paper_id
                            RETURN p.paper_id AS paper_id,
                                   p.title AS title,
                                   p.year AS year,
                                   p.evidence_level AS evidence_level,
                                   collect(DISTINCT {
                                       intervention: i.name,
                                       outcome: o.name,
                                       direction: r.direction,
                                       p_value: r.p_value,
                                       is_significant: r.is_significant
                                   }) AS evidence
                            ORDER BY p.evidence_level, p.year DESC
                            """
                            results = await self.neo4j_client.run_query(
                                detail_query,
                                {"paper_ids": paper_ids[:max_papers * 2]}
                            )
                            logger.info(f"Vector search found {len(results)} papers")
            except Exception as vec_err:
                logger.warning(f"Vector search fallback failed: {vec_err}")

        supporting = []
        refuting = []
        neutral = []

        for result in results[:max_papers]:
            paper_info = {
                "paper_id": result.get("paper_id"),
                "title": result.get("title"),
                "year": result.get("year"),
                "evidence_level": result.get("evidence_level"),
                "evidence": [e for e in (result.get("evidence") or [])
                            if e.get("intervention")]
            }

            # 근거 분류 (direction 기반)
            directions = [e.get("direction") for e in paper_info["evidence"]
                         if e.get("direction")]
            if "improved" in directions or "decreased" in directions:
                supporting.append(paper_info)
            elif "worsened" in directions or "increased risk" in directions:
                refuting.append(paper_info)
            else:
                neutral.append(paper_info)

        return {
            "success": True,
            "claim": claim,
            "supporting_papers": supporting,
            "refuting_papers": refuting,
            "neutral_papers": neutral,
            "total_papers": len(supporting) + len(refuting) + len(neutral),
        }

    @safe_execute
    async def get_topic_clusters(self) -> dict:
        """주제별 논문 클러스터 조회 (Neo4j 기반).

        Sub-domain 기반으로 논문을 그룹화하고,
        SIMILAR_TOPIC 관계가 있는 경우 추가 정보를 제공.

        Returns:
            클러스터 정보
        """
        self._require_neo4j()
        await self._ensure_connected()

        # 1. Sub-domain 기반 클러스터링
        query = """
        MATCH (p:Paper)
        WHERE p.sub_domain IS NOT NULL AND p.sub_domain <> ''
        WITH p.sub_domain AS topic, collect({
            id: p.paper_id,
            title: p.title,
            year: p.year,
            evidence_level: p.evidence_level
        }) AS papers
        RETURN topic, papers, size(papers) AS count
        ORDER BY count DESC
        LIMIT 20
        """

        results = await self.neo4j_client.run_query(query)

        # 클러스터 정보 구성
        cluster_info = {}
        for result in results:
            topic = result.get("topic", "Unknown")
            papers = result.get("papers", [])
            count = result.get("count", 0)

            if topic and topic != "Unknown":
                cluster_info[topic] = {
                    "count": count,
                    "papers": papers[:10]  # 클러스터당 최대 10개 논문
                }

        # 2. SIMILAR_TOPIC 관계 통계 추가 (있는 경우)
        sim_query = """
        MATCH ()-[r:SIMILAR_TOPIC]->()
        RETURN count(r) AS similar_topic_count
        """
        sim_results = await self.neo4j_client.run_query(sim_query)
        similar_topic_count = 0
        if sim_results:
            similar_topic_count = sim_results[0].get("similar_topic_count", 0)

        # 3. Unknown sub_domain 논문 처리
        unknown_query = """
        MATCH (p:Paper)
        WHERE p.sub_domain IS NULL OR p.sub_domain = ''
        RETURN collect({
            id: p.paper_id,
            title: p.title,
            year: p.year
        })[0..10] AS papers, count(p) AS count
        """
        unknown_results = await self.neo4j_client.run_query(unknown_query)
        if unknown_results and unknown_results[0].get("count", 0) > 0:
            cluster_info["Unclassified"] = {
                "count": unknown_results[0].get("count", 0),
                "papers": unknown_results[0].get("papers", [])
            }

        return {
            "success": True,
            "cluster_count": len(cluster_info),
            "clusters": cluster_info,
            "similar_topic_relations": similar_topic_count,
        }

    @safe_execute
    async def get_intervention_hierarchy(
        self,
        intervention_name: str
    ) -> dict:
        """수술법 계층 구조 조회.

        Args:
            intervention_name: 수술법 이름 (예: "TLIF")

        Returns:
            계층 구조 정보 (부모, 자식, 동의어 포함)
        """
        # Check if required modules are available
        if not self.graph_searcher:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        # Ensure Neo4j connection is established
        await self._ensure_connected()

        hierarchy = await self.graph_searcher.get_intervention_hierarchy(intervention_name)

        # Add aliases from entity normalizer
        try:
            from graph.entity_normalizer import get_normalizer
            normalizer = get_normalizer()

            aliases = []
            for alias, normalized in normalizer.INTERVENTION_ALIASES.items():
                if normalized == intervention_name or alias == intervention_name:
                    aliases.append(alias)
        except Exception as e:
            logger.debug(f"Alias lookup failed: {e}")
            aliases = []

        return {
            "success": True,
            "intervention": intervention_name,
            "full_name": hierarchy.get("full_name", ""),
            "category": hierarchy.get("category", ""),
            "approach": hierarchy.get("approach", ""),
            "is_minimally_invasive": hierarchy.get("is_minimally_invasive", False),
            "parents": hierarchy.get("parents", []),
            "children": hierarchy.get("children", []),
            "aliases": list(set(aliases))
        }

    @safe_execute
    async def build_paper_relations(
        self,
        paper_id: Optional[str] = None,
        min_similarity: float = 0.4,
        max_papers: int = 100
    ) -> dict:
        """논문 간 관계 자동 구축 (SIMILAR_TOPIC).

        지정된 논문 또는 모든 논문에 대해 유사도 기반 관계를 자동 생성합니다.

        Args:
            paper_id: 특정 논문 ID (None이면 모든 논문 대상)
            min_similarity: 최소 유사도 임계값 (기본값 0.4)
            max_papers: 비교할 최대 논문 수

        Returns:
            생성된 관계 정보
        """
        self._require_neo4j()
        await self._ensure_connected()

        # 모든 논문 조회 (관계 정보 포함)
        all_papers = await self.neo4j_client.get_all_papers_with_relations(limit=max_papers)

        if not all_papers:
            return {
                "success": True,
                "message": "No papers found in database",
                "relations_created": 0
            }

        # 대상 논문 결정
        if paper_id:
            target_papers = [p for p in all_papers if p.get("paper_id") == paper_id]
            compare_papers = [p for p in all_papers if p.get("paper_id") != paper_id]
        else:
            target_papers = all_papers
            compare_papers = all_papers

        relations_created = 0
        similar_relations = []
        processed_pairs = set()

        for target in target_papers:
            target_id = target.get("paper_id")
            if not target_id:
                continue

            for other in compare_papers:
                other_id = other.get("paper_id")
                if not other_id or other_id == target_id:
                    continue

                # 이미 처리된 쌍 건너뛰기 (양방향 중복 방지)
                pair_key = tuple(sorted([target_id, other_id]))
                if pair_key in processed_pairs:
                    continue
                processed_pairs.add(pair_key)

                # 유사도 계산
                similarity = self._calculate_paper_similarity(target, other)

                if similarity >= min_similarity:
                    try:
                        # SIMILAR_TOPIC 관계 생성
                        success = await self.neo4j_client.create_paper_relation(
                            source_paper_id=target_id,
                            target_paper_id=other_id,
                            relation_type="SIMILAR_TOPIC",
                            confidence=similarity,
                            evidence=f"Auto-calculated similarity: {similarity:.2f}",
                            detected_by="auto_build_relations"
                        )
                        if success:
                            relations_created += 1
                            similar_relations.append({
                                "source": target_id,
                                "target": other_id,
                                "similarity": round(similarity, 3)
                            })
                    except Exception as e:
                        logger.warning(f"Failed to create relation {target_id} -> {other_id}: {e}")

        return {
            "success": True,
            "papers_processed": len(target_papers),
            "pairs_compared": len(processed_pairs),
            "relations_created": relations_created,
            "similar_relations": similar_relations[:20],
            "min_similarity_used": min_similarity
        }

    def _calculate_paper_similarity(self, paper1: dict, paper2: dict) -> float:
        """논문 간 유사도 계산.

        Args:
            paper1: 논문 1 메타데이터
            paper2: 논문 2 메타데이터

        Returns:
            0.0 ~ 1.0 범위의 유사도
        """
        score = 0.0

        def flatten_to_set(items) -> set:
            if not items:
                return set()
            result = set()
            if isinstance(items, str):
                result.add(items.lower())
            elif isinstance(items, (list, tuple)):
                for item in items:
                    if isinstance(item, str):
                        result.add(item.lower())
                    elif isinstance(item, (list, tuple)):
                        for sub in item:
                            if isinstance(sub, str):
                                result.add(sub.lower())
            return result

        # 1. Sub-domain 겹침 (25%)
        domains1 = flatten_to_set(paper1.get("sub_domains", []))
        domains2 = flatten_to_set(paper2.get("sub_domains", []))
        if not domains1 and paper1.get("sub_domain"):
            domains1 = {paper1["sub_domain"].lower()}
        if not domains2 and paper2.get("sub_domain"):
            domains2 = {paper2["sub_domain"].lower()}
        if domains1 and domains2:
            jaccard = len(domains1 & domains2) / len(domains1 | domains2)
            score += 0.25 * jaccard

        # 2. Pathology 겹침 (30%)
        path1 = flatten_to_set(paper1.get("pathologies", []))
        path2 = flatten_to_set(paper2.get("pathologies", []))
        if path1 and path2:
            jaccard = len(path1 & path2) / len(path1 | path2)
            score += 0.30 * jaccard

        # 3. Intervention 겹침 (30%)
        int1 = flatten_to_set(paper1.get("interventions", []))
        int2 = flatten_to_set(paper2.get("interventions", []))
        if int1 and int2:
            jaccard = len(int1 & int2) / len(int1 | int2)
            score += 0.30 * jaccard

        # 4. Anatomy 겹침 (15%)
        anat1 = flatten_to_set(paper1.get("anatomy_levels", []))
        anat2 = flatten_to_set(paper2.get("anatomy_levels", []))
        if anat1 and anat2:
            jaccard = len(anat1 & anat2) / len(anat1 | anat2)
            score += 0.15 * jaccard

        return round(score, 3)

    @safe_execute
    async def compare_interventions(
        self,
        intervention1: str,
        intervention2: str,
        outcome: str
    ) -> dict:
        """두 수술법의 효과 비교.

        Args:
            intervention1: 첫 번째 수술법
            intervention2: 두 번째 수술법
            outcome: 비교할 결과변수

        Returns:
            비교 결과 (통계적 유의성 포함)
        """
        if not self.graph_searcher:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        # Get evidence for both interventions via search_handler
        evidence1 = await self.server.search_handler.find_evidence(intervention1, outcome)
        evidence2 = await self.server.search_handler.find_evidence(intervention2, outcome)

        if not evidence1.get("success") or not evidence2.get("success"):
            return {
                "success": False,
                "error": "Failed to retrieve evidence for one or both interventions"
            }

        # Analyze comparison
        ev1_list = evidence1.get("evidence", [])
        ev2_list = evidence2.get("evidence", [])

        comparison = {
            "intervention1": {
                "name": intervention1,
                "evidence_count": len(ev1_list),
                "avg_p_value": sum(e.get("p_value", 1.0) for e in ev1_list) / len(ev1_list) if ev1_list else 1.0,
                "significant_studies": sum(1 for e in ev1_list if e.get("is_significant", False)),
                "studies": ev1_list
            },
            "intervention2": {
                "name": intervention2,
                "evidence_count": len(ev2_list),
                "avg_p_value": sum(e.get("p_value", 1.0) for e in ev2_list) / len(ev2_list) if ev2_list else 1.0,
                "significant_studies": sum(1 for e in ev2_list if e.get("is_significant", False)),
                "studies": ev2_list
            }
        }

        # Determine which has better evidence
        if comparison["intervention1"]["significant_studies"] > comparison["intervention2"]["significant_studies"]:
            comparison["recommendation"] = f"{intervention1} has more significant evidence"
        elif comparison["intervention2"]["significant_studies"] > comparison["intervention1"]["significant_studies"]:
            comparison["recommendation"] = f"{intervention2} has more significant evidence"
        else:
            comparison["recommendation"] = "Both interventions have similar evidence levels"

        return {
            "success": True,
            "outcome": outcome,
            "comparison": comparison
        }

    @safe_execute
    async def get_comparable_interventions(
        self,
        intervention: str
    ) -> dict:
        """비교 가능한 수술법 목록 조회 (Taxonomy 기반).

        Args:
            intervention: 수술법 이름

        Returns:
            같은 부모를 가진 sibling interventions
        """
        self._require_neo4j()
        await self._ensure_connected()

        # Use TaxonomyManager
        from graph.taxonomy_manager import TaxonomyManager
        taxonomy = TaxonomyManager(self.neo4j_client)

        # Get parents
        parents = await taxonomy.get_parent_interventions(intervention)

        if not parents:
            return {
                "success": True,
                "intervention": intervention,
                "comparable_interventions": [],
                "message": f"No parent category found for {intervention}"
            }

        # Get siblings (children of same parent)
        immediate_parent = parents[0] if parents else None
        if immediate_parent:
            siblings = await taxonomy.get_child_interventions(immediate_parent)
            # Remove the intervention itself
            comparable = [s for s in siblings if s != intervention]
        else:
            comparable = []

        return {
            "success": True,
            "intervention": intervention,
            "parent_category": immediate_parent,
            "all_parents": parents,
            "comparable_interventions": comparable,
            "count": len(comparable)
        }

    @safe_execute
    async def get_intervention_hierarchy_with_direction(
        self,
        intervention: str,
        direction: str = "both"
    ) -> dict:
        """수술법 계층 구조 조회 (방향 선택 가능).

        Args:
            intervention: 수술법 이름
            direction: "ancestors", "descendants", "both"

        Returns:
            계층 구조 정보 (부모/자식, 거리 포함)
        """
        self._require_neo4j()
        await self._ensure_connected()

        from graph.taxonomy_manager import TaxonomyManager
        taxonomy = TaxonomyManager(self.neo4j_client)

        result = {
            "success": True,
            "intervention": intervention
        }

        if direction in ["ancestors", "both"]:
            # Get all ancestors (parents)
            parents = await taxonomy.get_parent_interventions(intervention)
            result["ancestors"] = parents
            result["ancestor_count"] = len(parents)

        if direction in ["descendants", "both"]:
            # Get all descendants (children)
            children = await taxonomy.get_child_interventions(intervention)
            result["descendants"] = children
            result["descendant_count"] = len(children)

        # Get aliases from entity normalizer
        try:
            from graph.entity_normalizer import get_normalizer
            normalizer = get_normalizer()

            aliases = []
            for alias, normalized in normalizer.INTERVENTION_ALIASES.items():
                if normalized == intervention or alias == intervention:
                    aliases.append(alias)
            result["aliases"] = list(set(aliases))
        except Exception as e:
            logger.debug(f"Alias lookup failed: {e}")
            result["aliases"] = []

        return result

    @safe_execute
    async def infer_relations(
        self,
        rule_name: Optional[str] = None,
        intervention: Optional[str] = None,
        outcome: Optional[str] = None,
        pathology: Optional[str] = None,
        paper_id: Optional[str] = None,
    ) -> dict:
        """추론 기반 관계 탐색.

        InferenceEngine을 사용하여 그래프에서 추론된 관계를 탐색합니다.

        Args:
            rule_name: 추론 규칙 이름 (None이면 자동 선택)
            intervention: 수술법 이름
            outcome: 결과변수 이름
            pathology: 질환명
            paper_id: 논문 ID (현재 미사용, 확장용)

        Returns:
            추론 결과 딕셔너리
        """
        self._require_neo4j()
        await self._ensure_connected()

        try:
            from graph.inference_rules import InferenceEngine
        except ImportError as e:
            return {"success": False, "error": f"InferenceEngine not available: {e}"}

        engine = InferenceEngine(neo4j_client=self.neo4j_client)

        # If rule_name is specified, execute that rule directly
        if rule_name:
            params = {}
            if intervention:
                params["intervention"] = intervention
            if outcome:
                params["outcome"] = outcome
            if pathology:
                params["pathology"] = pathology

            try:
                results = await engine.execute_rule(rule_name, **params)
                rule = engine.get_rule(rule_name)
                return {
                    "success": True,
                    "rule_name": rule_name,
                    "rule_type": rule.rule_type.value if rule else "unknown",
                    "confidence_weight": rule.confidence_weight if rule else 1.0,
                    "result_count": len(results),
                    "results": results,
                }
            except (ValueError, ValidationError) as e:
                return {"success": False, "error": str(e)}

        # Auto-select rule based on provided parameters
        results = {}

        if intervention and outcome:
            evidence = await engine.aggregate_evidence(intervention, outcome)
            conflicts = await engine.detect_conflicts(intervention, outcome)
            results["aggregate_evidence"] = evidence
            results["conflicts"] = conflicts
        elif intervention:
            ancestors = await engine.get_ancestors(intervention)
            comparable = await engine.get_comparable_interventions(intervention)
            treatments = await engine.infer_treatments(intervention)
            results["ancestors"] = ancestors
            results["comparable_interventions"] = comparable
            results["inferred_treatments"] = treatments
        elif pathology:
            indirect = await engine.find_indirect_treatments(pathology)
            results["indirect_treatments"] = indirect
        else:
            # List available rules
            rules_list = engine.list_rules()
            return {
                "success": True,
                "message": "No parameters provided. Listing available rules.",
                "available_rules": [
                    {
                        "name": r.name,
                        "type": r.rule_type.value,
                        "description": r.description,
                        "parameters": r.parameters,
                        "confidence_weight": r.confidence_weight,
                    }
                    for r in rules_list
                ],
            }

        return {
            "success": True,
            "intervention": intervention,
            "outcome": outcome,
            "pathology": pathology,
            "results": results,
        }

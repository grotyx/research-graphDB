"""Search Handler for Medical KAG Server.

This module handles all search-related operations including hybrid search,
graph search, adaptive search, and evidence retrieval.
"""

import logging
from typing import Optional

from solver.query_parser import QueryParser, QueryInput
from solver.tiered_search import TieredHybridSearch, SearchInput, SearchTier
from solver.multi_factor_ranker import MultiFactorRanker, RankInput
from solver.conflict_detector import ConflictDetector, ConflictInput
from solver.multi_factor_ranker import SearchResult as RankerSearchResult, SourceType, EvidenceLevel

logger = logging.getLogger(__name__)


class SearchHandler:
    """Handler for search operations.

    Provides hybrid search, graph search, adaptive search, and evidence retrieval
    functionality for the Medical KAG server.
    """

    def __init__(self, server):
        """Initialize SearchHandler.

        Args:
            server: MedicalKAGServer instance to access components
        """
        self.server = server
        self.query_parser: QueryParser = server.query_parser
        self.search_engine: TieredHybridSearch = server.search_engine
        self.ranker: MultiFactorRanker = server.ranker
        self.conflict_detector: ConflictDetector = server.conflict_detector
        self.graph_searcher = server.graph_searcher
        self.neo4j_client = server.neo4j_client
        self.concept_hierarchy = server.concept_hierarchy
        self.cypher_generator = server.cypher_generator
        self.vector_db = server.vector_db

    async def search(
        self,
        query: str,
        top_k: int = 5,
        tier_strategy: str = "tier1_then_tier2",
        prefer_original: bool = True,
        min_evidence_level: Optional[str] = None
    ) -> dict:
        """검색 수행.

        Args:
            query: 검색 쿼리
            top_k: 결과 수
            tier_strategy: 검색 전략 (tier1_only, tier1_then_tier2, all_tiers)
            prefer_original: 원본 우선 여부
            min_evidence_level: 최소 근거 수준

        Returns:
            검색 결과 딕셔너리
        """
        try:
            # 0. Query expansion using SNOMED-CT concept hierarchy
            expanded_query = query
            expansion_terms = []
            if self.concept_hierarchy:
                try:
                    # Extract words and expand with medical synonyms
                    query_words = query.lower().split()
                    expanded = self.concept_hierarchy.expand_query(query_words)
                    expansion_terms = [t for t in expanded if t.lower() not in query.lower()]
                    if expansion_terms:
                        # Combine original query with expanded terms
                        expanded_query = f"{query} {' '.join(expansion_terms[:5])}"  # Limit to 5 expansion terms
                        logger.info(f"Query expanded: '{query}' -> added terms: {expansion_terms[:5]}")
                except Exception as e:
                    logger.warning(f"Query expansion failed: {e}")

            # 1. 쿼리 파싱
            parsed = self.query_parser.parse(QueryInput(
                query=expanded_query,
                expand_synonyms=True
            ))

            # 2. 검색 전략 설정
            strategy_map = {
                "tier1_only": SearchTier.TIER1_ONLY,
                "tier1_then_tier2": SearchTier.TIER1_THEN_TIER2,
                "all_tiers": SearchTier.ALL_TIERS
            }
            strategy = strategy_map.get(tier_strategy, SearchTier.TIER1_THEN_TIER2)

            # 3. 검색 수행
            search_input = SearchInput(
                query=expanded_query,
                entities=parsed.entities,
                tier_strategy=strategy,
                prefer_original=prefer_original,
                min_evidence_level=min_evidence_level,
                top_k=top_k
            )
            search_output = self.search_engine.search(search_input)

            # 4. 랭킹 (SearchResult 변환 필요)
            if search_output.results:
                # TieredHybridSearch SearchResult → MultiFactorRanker SearchResult 변환
                def str_to_source_type(s: str) -> SourceType:
                    try:
                        return SourceType(s)
                    except (ValueError, KeyError):
                        return SourceType.UNKNOWN

                def str_to_evidence_level(s: str) -> EvidenceLevel:
                    mapping = {
                        "1a": EvidenceLevel.LEVEL_1A,
                        "1b": EvidenceLevel.LEVEL_1B,
                        "2a": EvidenceLevel.LEVEL_2A,
                        "2b": EvidenceLevel.LEVEL_2B,
                        "2c": EvidenceLevel.LEVEL_2C,
                        "3a": EvidenceLevel.LEVEL_3A,
                        "3b": EvidenceLevel.LEVEL_3B,
                        "4": EvidenceLevel.LEVEL_4,
                        "5": EvidenceLevel.LEVEL_5,
                    }
                    return mapping.get(s, EvidenceLevel.LEVEL_5)

                converted_results = []
                for sr in search_output.results:
                    chunk = sr.chunk
                    source_type_enum = str_to_source_type(sr.source_type)
                    evidence_level_enum = str_to_evidence_level(sr.evidence_level)

                    converted = RankerSearchResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        text=chunk.text,
                        semantic_score=sr.score,
                        tier=sr.tier,
                        section=chunk.section,
                        source_type=source_type_enum,
                        evidence_level=evidence_level_enum,
                        publication_year=getattr(chunk, 'publication_year', 0),
                        title=getattr(chunk, 'title', None)  # v7.14.30: title 필드 추가
                    )
                    converted_results.append(converted)

                rank_input = RankInput(results=converted_results, query=query)
                ranked = self.ranker.rank(rank_input)
                results = ranked.ranked_results
            else:
                results = []

            # 5. 상충 감지 (선택적)
            conflicts = None
            if len(results) >= 2:
                try:
                    from solver.conflict_detector import StudyResult as CDStudyResult

                    # RankedResult를 StudyResult로 변환 시도
                    study_results = []
                    for r in results[:10]:  # 최대 10개만
                        result = r.result if hasattr(r, 'result') else r
                        study = CDStudyResult(
                            study_id=getattr(result, 'document_id', 'unknown'),
                            title=getattr(result, 'text', '')[:200],  # 최대 200자
                            evidence_level=getattr(result, 'evidence_level', EvidenceLevel.LEVEL_5),
                        )
                        study_results.append(study)

                    if study_results:
                        conflict_input = ConflictInput(
                            topic=query,
                            studies=study_results
                        )
                        conflict_output = self.conflict_detector.detect(conflict_input)
                        if conflict_output.has_conflicts:
                            conflicts = {
                                "topic": query,
                                "count": len(conflict_output.conflicts),
                                "conflicts": [
                                    {
                                        "study1": c.study1.study_id,
                                        "study2": c.study2.study_id,
                                        "type": c.conflict_type.value if hasattr(c.conflict_type, 'value') else str(c.conflict_type),
                                        "severity": c.severity.value if hasattr(c.severity, 'value') else str(c.severity)
                                    }
                                    for c in conflict_output.conflicts[:5]  # 최대 5개만
                                ]
                            }
                except Exception as e:
                    logger.warning(f"Conflict detection skipped: {e}")

            # 6. 결과 포맷 (v7.14.20: title, year 필드 추가)
            formatted_results = []
            for r in results[:top_k]:
                # RankedResult인 경우
                if hasattr(r, 'result') and hasattr(r, 'final_score'):
                    result = r.result
                    score = r.final_score
                    text = getattr(result, 'text', '')
                    tier = getattr(result, 'tier', 'unknown')
                    source_type = getattr(result, 'source_type', 'unknown')
                    evidence_level = getattr(result, 'evidence_level', 'unknown')
                    document_id = getattr(result, 'document_id', '')
                    title = getattr(result, 'title', '')
                    year = getattr(result, 'publication_year', 0)
                # SearchResult (tiered_search)인 경우
                elif hasattr(r, 'chunk'):
                    score = getattr(r, 'score', 0.5)
                    text = getattr(r.chunk, 'text', '')
                    tier = getattr(r, 'tier', 'unknown')
                    source_type = getattr(r, 'source_type', 'unknown')
                    evidence_level = getattr(r, 'evidence_level', 'unknown')
                    document_id = getattr(r.chunk, 'document_id', '')
                    title = getattr(r.chunk, 'title', '')
                    year = getattr(r.chunk, 'publication_year', 0)
                else:
                    # 기타
                    score = getattr(r, 'score', 0.5)
                    text = getattr(r, 'text', str(r))
                    tier = getattr(r, 'tier', 'unknown')
                    source_type = getattr(r, 'source_type', 'unknown')
                    evidence_level = getattr(r, 'evidence_level', 'unknown')
                    document_id = getattr(r, 'document_id', '')
                    title = getattr(r, 'title', '')
                    year = getattr(r, 'publication_year', 0)

                # source_type이 Enum인 경우 value 추출
                if hasattr(source_type, 'value'):
                    source_type = source_type.value
                if hasattr(evidence_level, 'value'):
                    evidence_level = evidence_level.value

                # title이 비어있으면 document_id에서 추출 시도
                if not title and document_id:
                    # document_id 형식: "2024_Author_Title_of_Paper" -> 제목 추출
                    parts = document_id.split('_')
                    if len(parts) > 2:
                        title = ' '.join(parts[2:]).replace('_', ' ')

                formatted_results.append({
                    "content": text,
                    "score": float(score) if score else 0.0,
                    "tier": tier,
                    "source_type": str(source_type),
                    "evidence_level": str(evidence_level),
                    "document_id": document_id,
                    "title": title,
                    "publication_year": year
                })

            return {
                "success": True,
                "query": query,
                "parsed_intent": parsed.intent.value,
                "expanded_terms": parsed.expanded_terms,
                "total_found": search_output.total_found,
                "results": formatted_results,
                "conflicts": conflicts
            }

        except Exception as e:
            logger.exception(f"Search error: {e}")
            return {"success": False, "error": str(e)}

    async def graph_search(
        self,
        query: str,
        search_type: str = "evidence",
        limit: int = 20
    ) -> dict:
        """Neo4j 그래프 기반 검색.

        Args:
            query: 자연어 검색 쿼리
            search_type: 검색 유형 (evidence|comparison|hierarchy|conflict)
            limit: 결과 개수 제한

        Returns:
            그래프 검색 결과
        """
        if not self.graph_searcher:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Extract entities and generate Cypher
            entities = self.cypher_generator.extract_entities(query)

            # Override intent if search_type is explicitly provided
            if search_type != "evidence":
                entities["intent"] = search_type

            cypher, cypher_params = self.cypher_generator.generate(query, entities)

            # Execute search based on intent
            intent = entities.get("intent", "evidence_search")

            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            if intent == "evidence_search":
                interventions = entities.get("interventions", [])
                outcomes = entities.get("outcomes", [])

                if interventions and outcomes:
                    result = await self.graph_searcher.search_interventions_for_outcome(
                        outcome_name=outcomes[0],
                        direction="improved",
                        limit=limit
                    )
                elif interventions and not outcomes:
                    # v7.14.18: Intervention만 있는 경우 → cypher_generator가 생성한 쿼리 사용
                    # IS_A 계층을 통해 하위 수술법도 포함하여 관련 논문 검색
                    results = await self.neo4j_client.run_query(cypher, cypher_params)
                    result = {
                        "query": query,
                        "results": results,
                        "cypher_query": cypher
                    }
                else:
                    # Fallback to general search with search_term
                    merged_params = {**cypher_params, "search_term": query, "limit": limit}
                    results = await self.neo4j_client.run_query(
                        cypher, merged_params
                    )
                    result = {
                        "query": query,
                        "results": results,
                        "cypher_query": cypher
                    }

            elif intent == "hierarchy":
                interventions = entities.get("interventions", [])
                if interventions:
                    hierarchy = await self.graph_searcher.get_intervention_hierarchy(interventions[0])
                    return {
                        "success": True,
                        "query": query,
                        "search_type": "hierarchy",
                        "result": hierarchy
                    }
                else:
                    return {
                        "success": False,
                        "error": "No intervention found in query"
                    }

            elif intent == "conflict":
                interventions = entities.get("interventions", [])
                outcomes = entities.get("outcomes", [])
                if interventions:
                    result = await self.graph_searcher.find_conflicting_results(
                        intervention_name=interventions[0],
                        outcome_name=outcomes[0] if outcomes else None
                    )
                else:
                    return {
                        "success": False,
                        "error": "No intervention found in query"
                    }

            else:
                # Default: execute generated Cypher with search_term parameter (v7.14.18)
                # 검색어를 파라미터로 전달하여 제목/초록 검색 지원
                results = await self.neo4j_client.run_query(
                    cypher,
                    {"search_term": query, "limit": limit}
                )
                result = {
                    "query": query,
                    "results": results,
                    "cypher_query": cypher
                }

            return {
                "success": True,
                "query": query,
                "search_type": intent,
                "entities": entities,
                "result_count": len(result.results) if hasattr(result, 'results') else len(result.get("results", [])),
                "results": result.results if hasattr(result, 'results') else result.get("results", []),
                "cypher_query": cypher,
                "execution_time_ms": result.execution_time_ms if hasattr(result, 'execution_time_ms') else 0
            }

        except Exception as e:
            logger.exception(f"Graph search error: {e}")
            return {"success": False, "error": str(e)}

    async def adaptive_search(
        self,
        query: str,
        top_k: int = 10,
        include_synthesis: bool = True,
        detect_conflicts: bool = True
    ) -> dict:
        """통합 검색 파이프라인 - Neo4j 하이브리드 검색 사용.

        v7.14.18+: ChromaDB 제거로 인해 Neo4j 내장 벡터 인덱스를 사용하는
        hybrid_search로 대체됩니다. 근거 종합 및 충돌 탐지를 포함합니다.

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            include_synthesis: 근거 종합 포함 여부
            detect_conflicts: 충돌 탐지 포함 여부

        Returns:
            Full search response with adaptive ranking, synthesis, conflicts
        """
        if not self.neo4j_client:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # v7.14.19: Use Neo4j's built-in hybrid search instead of UnifiedSearchPipeline
            # Since ChromaDB was removed, we use Neo4j's vector index directly
            import time
            start_time = time.time()

            # Generate query embedding for hybrid search
            query_embedding = None
            if self.vector_db and hasattr(self.vector_db, 'get_embedding'):
                try:
                    query_embedding = self.vector_db.get_embedding(query)
                except Exception as emb_err:
                    logger.warning(f"Embedding generation failed: {emb_err}")

            # Fallback: use EmbeddingGenerator directly if vector_db not available
            if query_embedding is None:
                try:
                    from core.embedding import get_embedding_generator
                    generator = get_embedding_generator()
                    query_embedding = generator.generate(query)
                except Exception as gen_err:
                    logger.warning(f"Fallback embedding generation failed: {gen_err}")

            # If embedding available, use hybrid search; otherwise fallback to regular search
            if query_embedding:
                search_results = await self.neo4j_client.hybrid_search(
                    embedding=query_embedding,
                    top_k=top_k
                )
            else:
                # Fallback to regular tiered search
                logger.info("Falling back to regular search (embedding unavailable)")
                fallback_result = await self.search(query, top_k=top_k)
                return fallback_result

            # Format results for adaptive response
            results = []
            for r in search_results:
                results.append({
                    "paper_id": r.get("paper_id", ""),
                    "title": r.get("title", ""),
                    "final_score": r.get("score", 0.0),
                    "graph_score": r.get("graph_score", 0.0),
                    "vector_score": r.get("vector_score", r.get("score", 0.0)),
                    "content": r.get("content", "")[:200] if r.get("content") else "",
                    "evidence_level": r.get("evidence_level", ""),
                    "year": r.get("year", 0)
                })

            execution_time_ms = (time.time() - start_time) * 1000

            result = {
                "success": True,
                "query": query,
                "query_type": "adaptive_hybrid",
                "result_count": len(results),
                "results": results,
                "execution_time_ms": round(execution_time_ms, 2)
            }

            # Add synthesis if requested and we have results
            if include_synthesis and results:
                from solver.evidence_synthesizer import EvidenceSynthesizer
                try:
                    synthesizer = EvidenceSynthesizer(neo4j_client=self.neo4j_client)
                    # Get paper IDs for synthesis
                    paper_ids = [r["paper_id"] for r in results if r.get("paper_id")]
                    if paper_ids:
                        synthesis = await synthesizer.synthesize_evidence(
                            paper_ids=paper_ids[:10],  # Limit to top 10
                            query=query
                        )
                        if synthesis:
                            result["synthesis"] = {
                                "direction": synthesis.get("direction", "mixed"),
                                "strength": synthesis.get("strength", "moderate"),
                                "grade_rating": synthesis.get("grade_rating", ""),
                                "paper_count": len(paper_ids),
                                "effect_summary": synthesis.get("effect_summary", ""),
                                "recommendation": synthesis.get("recommendation", "")
                            }
                except Exception as synth_error:
                    logger.warning(f"Synthesis failed: {synth_error}")

            # Add conflict detection if requested
            if detect_conflicts and results:
                from solver.conflict_detector import ConflictDetector
                try:
                    detector = ConflictDetector(neo4j_client=self.neo4j_client)
                    paper_ids = [r["paper_id"] for r in results if r.get("paper_id")]
                    if paper_ids:
                        conflicts = await detector.detect_conflicts_in_papers(paper_ids[:10])
                        if conflicts:
                            result["conflicts"] = [
                                {
                                    "intervention": c.get("intervention", ""),
                                    "outcome": c.get("outcome", ""),
                                    "severity": c.get("severity", "low"),
                                    "confidence": c.get("confidence", 0.0),
                                    "improved_count": c.get("improved_count", 0),
                                    "worsened_count": c.get("worsened_count", 0)
                                }
                                for c in conflicts
                            ]
                except Exception as conflict_error:
                    logger.warning(f"Conflict detection failed: {conflict_error}")

            return result

        except Exception as e:
            logger.exception(f"Adaptive search error: {e}")
            return {"success": False, "error": str(e)}

    async def find_evidence(
        self,
        intervention: str,
        outcome: str,
        direction: str = "improved"
    ) -> dict:
        """특정 수술법과 결과변수 관계의 근거 검색.

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름
            direction: 효과 방향 (improved|worsened|unchanged)

        Returns:
            근거 논문 목록 (p-value, effect size 포함)
        """
        if not self.graph_searcher:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # v7.14.12: Entity Normalization 적용
            normalized_intervention = intervention
            normalized_outcome = outcome
            try:
                from graph.entity_normalizer import get_normalizer
                normalizer = get_normalizer()

                int_result = normalizer.normalize_intervention(intervention)
                if int_result and int_result.normalized:
                    normalized_intervention = int_result.normalized
                    logger.info(f"Intervention normalized: '{intervention}' -> '{normalized_intervention}'")

                out_result = normalizer.normalize_outcome(outcome)
                if out_result and out_result.normalized:
                    normalized_outcome = out_result.normalized
                    logger.info(f"Outcome normalized: '{outcome}' -> '{normalized_outcome}'")
            except Exception as e:
                logger.warning(f"Entity normalization failed: {e}")

            # v7.14.12: 정규화된 이름으로 직접 Cypher 쿼리
            # "Endoscopic" 키워드 검색 시 모든 내시경 수술 포함
            is_endoscopic_search = 'endoscopic' in intervention.lower()

            async with self.neo4j_client.session() as session:
                if is_endoscopic_search:
                    # Endoscopic 계열 전체 검색 (UBE, BELIF, FESS, PELD, MED 등)
                    logger.info(f"Endoscopic search mode: searching all endoscopic interventions")
                    result = await session.run('''
                        MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome)
                        WHERE (i.name CONTAINS 'Endoscopic' OR i.name CONTAINS 'endoscopic'
                               OR i.name CONTAINS 'UBE' OR i.name CONTAINS 'BELIF'
                               OR i.name CONTAINS 'FESS' OR i.name CONTAINS 'PELD'
                               OR i.name CONTAINS 'MED' OR i.name CONTAINS 'FELD'
                               OR i.name CONTAINS 'BE-' OR i.name CONTAINS 'Biportal'
                               OR i.full_name CONTAINS 'Endoscopic' OR i.full_name CONTAINS 'endoscopic')
                          AND (o.name = $outcome OR toLower(o.name) CONTAINS toLower($outcome))
                        RETURN i.name AS intervention,
                               i.full_name AS full_name,
                               o.name AS outcome,
                               a.value AS value,
                               a.value_control AS value_control,
                               a.p_value AS p_value,
                               a.effect_size AS effect_size,
                               a.confidence_interval AS confidence_interval,
                               a.direction AS direction,
                               a.is_significant AS is_significant,
                               a.source_paper_id AS source_paper_id
                        ORDER BY a.p_value ASC
                        LIMIT 50
                    ''', outcome=normalized_outcome)
                else:
                    # IS_A hierarchy를 통해 하위 intervention도 포함
                    result = await session.run('''
                        MATCH (target:Intervention {name: $intervention})
                        OPTIONAL MATCH (child:Intervention)-[:IS_A*1..3]->(target)
                        WITH COLLECT(DISTINCT target) + COLLECT(DISTINCT child) AS interventions
                        UNWIND interventions AS i
                        MATCH (i)-[a:AFFECTS]->(o:Outcome)
                        WHERE o.name = $outcome OR toLower(o.name) CONTAINS toLower($outcome)
                        RETURN i.name AS intervention,
                               i.full_name AS full_name,
                               o.name AS outcome,
                               a.value AS value,
                               a.value_control AS value_control,
                               a.p_value AS p_value,
                               a.effect_size AS effect_size,
                               a.confidence_interval AS confidence_interval,
                               a.direction AS direction,
                               a.is_significant AS is_significant,
                               a.source_paper_id AS source_paper_id
                        ORDER BY a.p_value ASC
                        LIMIT 50
                    ''', intervention=normalized_intervention, outcome=normalized_outcome)

                evidence = []
                async for r in result:
                    p_val = r.get("p_value")
                    try:
                        p_val_float = float(p_val) if p_val else 1.0
                    except (ValueError, TypeError):
                        p_val_float = 1.0

                    evidence.append({
                        "intervention": r.get("intervention"),
                        "full_name": r.get("full_name"),
                        "outcome": r.get("outcome"),
                        "value": r.get("value"),
                        "value_control": r.get("value_control"),
                        "p_value": r.get("p_value"),
                        "effect_size": r.get("effect_size"),
                        "confidence_interval": r.get("confidence_interval"),
                        "direction": r.get("direction"),
                        "is_significant": r.get("is_significant") or p_val_float < 0.05,
                        "source_paper_id": r.get("source_paper_id")
                    })

            return {
                "success": True,
                "intervention": intervention,
                "normalized_intervention": normalized_intervention,
                "outcome": outcome,
                "normalized_outcome": normalized_outcome,
                "direction": direction,
                "evidence_count": len(evidence),
                "evidence": evidence
            }

        except Exception as e:
            logger.exception(f"Find evidence error: {e}")
            return {"success": False, "error": str(e)}

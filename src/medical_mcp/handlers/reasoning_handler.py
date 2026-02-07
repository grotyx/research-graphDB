"""Reasoning Handler for Medical KAG Server.

추론(reasoning) 관련 MCP 도구 핸들러.
- reason(): 추론 기반 답변 생성
- multi_hop_reason(): Multi-hop 추론 (deprecated)
- find_conflicts(): 연구 간 상충 탐지
- detect_conflicts(): 수술법의 상충 결과 탐지
- compare_papers(): 논문 비교 분석
- synthesize_evidence(): GRADE 방법론 기반 근거 종합
"""

import logging
from typing import Any, Optional

# Solver modules
from solver.reasoner import ReasonerInput
from solver.response_generator import GeneratorInput, ResponseFormat
from solver.conflict_detector import ConflictInput

logger = logging.getLogger("medical-kag.handlers.reasoning")


class ReasoningHandler:
    """추론 관련 도구를 처리하는 핸들러."""

    def __init__(self, server):
        """초기화.

        Args:
            server: MedicalKAGServer 인스턴스 (reasoner, conflict_detector, search 등 접근용)
        """
        self.server = server
        self.reasoner = server.reasoner
        self.conflict_detector = server.conflict_detector
        self.response_generator = server.response_generator
        self.neo4j_client = getattr(server, 'neo4j_client', None)

        # Check if Neo4j Graph modules are available
        try:
            from graph.neo4j_client import Neo4jClient
            self.graph_available = True
        except ImportError:
            self.graph_available = False
            logger.warning("Neo4j Graph modules not available")

    async def reason(
        self,
        question: str,
        max_hops: int = 3,
        include_conflicts: bool = True
    ) -> dict:
        """추론 기반 답변 생성.

        Args:
            question: 질문
            max_hops: 최대 추론 홉
            include_conflicts: 상충 포함 여부

        Returns:
            추론 결과 딕셔너리
        """
        try:
            # 1. 검색
            search_result = await self.server.search(question, top_k=10)
            if not search_result["success"]:
                return search_result

            results = search_result.get("results", [])

            # 2. 추론
            reasoner_input = ReasonerInput(
                query=question,
                search_results=results,
                max_hops=max_hops,
                include_explanation=True
            )
            reasoning_result = self.reasoner.reason(reasoner_input)

            # 3. 응답 생성
            generator_input = GeneratorInput(
                query=question,
                ranked_results=results,
                reasoning=reasoning_result,
                conflicts=search_result.get("conflicts") if include_conflicts else None,
                format=ResponseFormat.MARKDOWN
            )
            response = self.response_generator.generate(generator_input)

            return {
                "success": True,
                "question": question,
                "answer": reasoning_result.answer,
                "confidence": reasoning_result.confidence,
                "confidence_level": reasoning_result.confidence_level.value,
                "evidence_count": len(reasoning_result.evidence),
                "reasoning_steps": len(reasoning_result.reasoning_path),
                "markdown_response": response.markdown,
                "conflicts": search_result.get("conflicts")
            }

        except Exception as e:
            logger.exception(f"Reason error: {e}")
            return {"success": False, "error": str(e)}

    async def multi_hop_reason(
        self,
        question: str,
        start_paper_id: Optional[str] = None,
        max_hops: int = 3
    ) -> dict:
        """DEPRECATED: 여러 논문을 연결하는 Multi-hop 추론 (SQLite-based, removed).

        This method is no longer functional. Use Neo4j-based multi-hop reasoning instead.
        See src/solver/multi_hop_reasoning.py for Neo4j implementation.

        Args:
            question: 추론할 질문
            start_paper_id: 시작 논문 ID (None이면 전체에서 검색)
            max_hops: 최대 홉 수

        Returns:
            추론 결과
        """
        return {"success": False, "error": "Deprecated: Use Neo4j-based multi-hop reasoning (src/solver/multi_hop_reasoning.py)"}

    async def find_conflicts(
        self,
        topic: str,
        document_ids: Optional[list[str]] = None
    ) -> dict:
        """특정 주제에 대한 연구 간 상충 탐지.

        Args:
            topic: 분석할 주제
            document_ids: 분석할 문서 ID 목록 (None이면 전체 검색)

        Returns:
            상충 분석 결과
        """
        try:
            # Search for relevant documents
            if document_ids:
                # Filter by specific documents (not fully implemented yet)
                search_result = await self.server.search(query=topic, top_k=20)
            else:
                search_result = await self.server.search(query=topic, top_k=20)

            if not search_result.get("success"):
                return search_result

            results = search_result.get("results", [])
            if len(results) < 2:
                return {
                    "success": True,
                    "topic": topic,
                    "message": "Not enough studies found for conflict detection",
                    "conflicts": []
                }

            # Use conflict detector
            from solver.conflict_detector import StudyResult as CDStudyResult
            from solver.multi_factor_ranker import EvidenceLevel

            study_results = []
            for r in results[:15]:  # Max 15 studies
                study = CDStudyResult(
                    study_id=r.get("document_id", "unknown"),
                    title=r.get("content", "")[:200],
                    evidence_level=self._parse_evidence_level(r.get("evidence_level", "5")),
                )
                study_results.append(study)

            conflict_input = ConflictInput(
                topic=topic,
                studies=study_results
            )
            conflict_output = self.conflict_detector.detect(conflict_input)

            conflicts = []
            for c in conflict_output.conflicts:
                conflicts.append({
                    "study1": {
                        "id": c.study1.study_id,
                        "title": c.study1.title
                    },
                    "study2": {
                        "id": c.study2.study_id,
                        "title": c.study2.title
                    },
                    "conflict_type": c.conflict_type.value if hasattr(c.conflict_type, 'value') else str(c.conflict_type),
                    "severity": c.severity.value if hasattr(c.severity, 'value') else str(c.severity),
                    "description": c.description if hasattr(c, 'description') else ""
                })

            return {
                "success": True,
                "topic": topic,
                "studies_analyzed": len(study_results),
                "has_conflicts": conflict_output.has_conflicts,
                "conflict_count": len(conflicts),
                "conflicts": conflicts,
                "summary": conflict_output.summary if hasattr(conflict_output, 'summary') else ""
            }

        except Exception as e:
            logger.exception(f"Find conflicts error: {e}")
            return {"success": False, "error": str(e)}

    def _parse_evidence_level(self, level_str: str):
        """Evidence level 문자열을 Enum으로 변환."""
        from solver.multi_factor_ranker import EvidenceLevel
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
        return mapping.get(str(level_str).lower(), EvidenceLevel.LEVEL_5)

    async def detect_conflicts(
        self,
        intervention: str,
        outcome: Optional[str] = None
    ) -> dict:
        """수술법의 상충 결과 탐지 (ConflictDetector 사용).

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름 (None이면 모든 결과변수)

        Returns:
            상충 결과 요약 (severity, papers involved, differing directions)
        """
        if not self.graph_available or not self.neo4j_client:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # Use ConflictDetector from solver
            from solver.conflict_detector import ConflictDetector
            detector = ConflictDetector(self.neo4j_client)

            if outcome:
                # Detect conflicts for specific intervention-outcome pair
                conflict = await detector.detect_conflicts(intervention, outcome)

                if conflict:
                    return {
                        "success": True,
                        "intervention": intervention,
                        "outcome": outcome,
                        "has_conflicts": True,
                        "conflict": {
                            "severity": conflict.severity.value,
                            "confidence": conflict.confidence,
                            "paper_count": conflict.total_papers,
                            "papers_improved": [
                                {
                                    "paper_id": p.paper_id,
                                    "title": p.title,
                                    "evidence_level": p.evidence_level,
                                    "p_value": p.p_value,
                                    "is_significant": p.is_significant
                                }
                                for p in conflict.papers_improved
                            ],
                            "papers_worsened": [
                                {
                                    "paper_id": p.paper_id,
                                    "title": p.title,
                                    "evidence_level": p.evidence_level,
                                    "p_value": p.p_value,
                                    "is_significant": p.is_significant
                                }
                                for p in conflict.papers_worsened
                            ],
                            "papers_unchanged": [
                                {
                                    "paper_id": p.paper_id,
                                    "title": p.title,
                                    "evidence_level": p.evidence_level
                                }
                                for p in conflict.papers_unchanged
                            ],
                            "summary": conflict.summary
                        }
                    }
                else:
                    return {
                        "success": True,
                        "intervention": intervention,
                        "outcome": outcome,
                        "has_conflicts": False,
                        "summary": f"No conflicts found for {intervention} → {outcome}"
                    }
            else:
                # Find all conflicts for intervention (all outcomes)
                from solver.conflict_detector import ConflictSeverity
                all_conflicts = await detector.find_all_conflicts(
                    min_severity=ConflictSeverity.MEDIUM
                )

                # Filter by intervention
                intervention_conflicts = [
                    c for c in all_conflicts
                    if c.intervention == intervention
                ]

                return {
                    "success": True,
                    "intervention": intervention,
                    "has_conflicts": len(intervention_conflicts) > 0,
                    "conflict_count": len(intervention_conflicts),
                    "conflicts": [
                        {
                            "outcome": c.outcome,
                            "severity": c.severity.value,
                            "confidence": c.confidence,
                            "improved_count": len(c.papers_improved),
                            "worsened_count": len(c.papers_worsened)
                        }
                        for c in intervention_conflicts
                    ],
                    "summary": f"Found {len(intervention_conflicts)} conflicting outcomes for {intervention}"
                }

        except Exception as e:
            logger.exception(f"Detect conflicts error: {e}")
            return {"success": False, "error": str(e)}

    async def compare_papers(
        self,
        paper_ids: list[str]
    ) -> dict:
        """여러 논문 비교 분석 (Neo4j 기반).

        선택된 논문들의 메타데이터, Intervention, Outcome을 비교.

        Args:
            paper_ids: 비교할 논문 ID 목록

        Returns:
            비교 분석 결과
        """
        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j Graph Database not available"}

        if not paper_ids or len(paper_ids) < 2:
            return {"success": False, "error": "At least 2 paper IDs required for comparison"}

        try:
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # 각 논문의 상세 정보 조회
            query = """
            UNWIND $paper_ids AS pid
            MATCH (p:Paper {paper_id: pid})
            OPTIONAL MATCH (p)-[:STUDIES]->(path:Pathology)
            OPTIONAL MATCH (p)-[:INVESTIGATES]->(i:Intervention)
            OPTIONAL MATCH (p)-[:INVOLVES]->(a:Anatomy)
            OPTIONAL MATCH (i)-[r:AFFECTS]->(o:Outcome)
            WHERE r.source_paper_id = p.paper_id

            RETURN p.paper_id AS paper_id,
                   p.title AS title,
                   p.year AS year,
                   p.evidence_level AS evidence_level,
                   p.sub_domain AS sub_domain,
                   p.study_type AS study_type,
                   p.sample_size AS sample_size,
                   collect(DISTINCT path.name) AS pathologies,
                   collect(DISTINCT i.name) AS interventions,
                   collect(DISTINCT a.level) AS anatomy_levels,
                   collect(DISTINCT {
                       intervention: i.name,
                       outcome: o.name,
                       direction: r.direction,
                       p_value: r.p_value,
                       is_significant: r.is_significant,
                       effect_size: r.effect_size
                   }) AS outcomes
            """

            results = await self.neo4j_client.run_query(query, {"paper_ids": paper_ids})

            papers = []
            all_interventions = set()
            all_outcomes = set()
            all_pathologies = set()

            for result in results:
                paper_info = {
                    "paper_id": result.get("paper_id"),
                    "title": result.get("title"),
                    "year": result.get("year"),
                    "evidence_level": result.get("evidence_level"),
                    "sub_domain": result.get("sub_domain"),
                    "study_type": result.get("study_type"),
                    "sample_size": result.get("sample_size"),
                    "pathologies": [p for p in (result.get("pathologies") or []) if p],
                    "interventions": [i for i in (result.get("interventions") or []) if i],
                    "anatomy_levels": [a for a in (result.get("anatomy_levels") or []) if a],
                    "outcomes": [o for o in (result.get("outcomes") or [])
                                if o.get("intervention")]
                }
                papers.append(paper_info)

                all_interventions.update(paper_info["interventions"])
                all_pathologies.update(paper_info["pathologies"])
                for o in paper_info["outcomes"]:
                    if o.get("outcome"):
                        all_outcomes.add(o["outcome"])

            # 공통점 및 차이점 분석
            common_interventions = set(papers[0]["interventions"]) if papers else set()
            common_pathologies = set(papers[0]["pathologies"]) if papers else set()

            for paper in papers[1:]:
                common_interventions &= set(paper["interventions"])
                common_pathologies &= set(paper["pathologies"])

            return {
                "success": True,
                "papers": papers,
                "comparison": {
                    "total_papers": len(papers),
                    "all_interventions": list(all_interventions),
                    "all_pathologies": list(all_pathologies),
                    "all_outcomes": list(all_outcomes),
                    "common_interventions": list(common_interventions),
                    "common_pathologies": list(common_pathologies),
                },
            }

        except Exception as e:
            logger.exception(f"Compare papers error: {e}")
            return {"success": False, "error": str(e)}

    async def synthesize_evidence(
        self,
        intervention: str,
        outcome: str,
        min_papers: int = 2
    ) -> dict:
        """근거 종합 (GRADE 방법론 기반).

        Args:
            intervention: 수술법 이름
            outcome: 결과변수 이름
            min_papers: 최소 논문 수 (기본값: 2)

        Returns:
            GRADE rating, direction, strength, confidence interval, recommendation
        """
        if not self.graph_available or not self.neo4j_client:
            return {
                "success": False,
                "error": "Neo4j Graph modules not available"
            }

        try:
            # Ensure Neo4j connection is established
            if not self.neo4j_client._driver:
                await self.neo4j_client.connect()

            # Use EvidenceSynthesizer from solver
            from solver.evidence_synthesizer import EvidenceSynthesizer
            synthesizer = EvidenceSynthesizer(self.neo4j_client)

            result = await synthesizer.synthesize(
                intervention=intervention,
                outcome=outcome,
                min_papers=min_papers
            )

            return {
                "success": True,
                "intervention": intervention,
                "outcome": outcome,
                "direction": result.direction,
                "strength": result.strength.value,
                "grade_rating": result.grade_rating,
                "paper_count": result.paper_count,
                "effect_summary": result.effect_summary,
                "confidence_interval": result.confidence_interval,
                "heterogeneity": result.heterogeneity,
                "recommendation": result.recommendation,
                "supporting_papers": result.supporting_papers,
                "opposing_papers": result.opposing_papers
            }

        except Exception as e:
            logger.exception(f"Synthesize evidence error: {e}")
            return {"success": False, "error": str(e)}

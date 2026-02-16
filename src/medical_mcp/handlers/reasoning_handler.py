"""Reasoning Handler for Medical KAG Server.

추론(reasoning) 관련 MCP 도구 핸들러.
- reason(): 추론 기반 답변 생성
- multi_hop_reason(): Neo4j 기반 멀티홉 추론
- find_conflicts(): 연구 간 상충 탐지
- detect_conflicts(): 수술법의 상충 결과 탐지
- compare_papers(): 논문 비교 분석
- synthesize_evidence(): GRADE 방법론 기반 근거 종합
"""

import logging
from typing import Any, Optional

from medical_mcp.handlers.base_handler import BaseHandler, safe_execute

# Solver modules
from solver.reasoner import ReasonerInput
from solver.response_generator import GeneratorInput, ResponseFormat
from solver.conflict_detector import ConflictInput

logger = logging.getLogger("medical-kag.handlers.reasoning")


class ReasoningHandler(BaseHandler):
    """추론 관련 도구를 처리하는 핸들러."""

    def __init__(self, server):
        """초기화.

        Args:
            server: MedicalKAGServer 인스턴스 (reasoner, conflict_detector, search 등 접근용)
        """
        super().__init__(server)
        self.reasoner = server.reasoner
        self.conflict_detector = server.conflict_detector
        self.response_generator = server.response_generator

        # Check if Neo4j Graph modules are available
        try:
            from graph.neo4j_client import Neo4jClient
            self.graph_available = True
        except ImportError:
            self.graph_available = False
            logger.warning("Neo4j Graph modules not available")

    @safe_execute
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

    @safe_execute
    async def multi_hop_reason(
        self,
        question: str,
        start_paper_id: Optional[str] = None,
        max_hops: int = 3
    ) -> dict:
        """Neo4j 기반 멀티홉 추론.

        복잡한 질문을 하위 질문으로 분해하고, 각 단계에서 검색 및 추론을 수행.

        Args:
            question: 추론할 질문
            start_paper_id: 시작 논문 ID (None이면 전체에서 검색)
            max_hops: 최대 홉 수

        Returns:
            추론 결과 딕셔너리
        """
        try:
            from solver.multi_hop_reasoning import MultiHopReasoner
            from solver.unified_pipeline import UnifiedSearchPipeline
        except ImportError as e:
            return {"success": False, "error": f"MultiHopReasoner not available: {e}"}

        if not self.neo4j_client:
            return {"success": False, "error": "Neo4j client not available"}

        # LLM client from server
        llm_client = getattr(self.server, 'llm_client', None)
        if not llm_client:
            try:
                from llm import LLMClient, LLMConfig
                llm_client = LLMClient(config=LLMConfig(temperature=0.1))
            except ImportError:
                return {"success": False, "error": "LLM client not available"}

        # Search pipeline from server
        search_pipeline = getattr(self.server, 'search_pipeline', None)
        if not search_pipeline:
            try:
                search_pipeline = UnifiedSearchPipeline(neo4j_client=self.neo4j_client)
            except Exception as e:
                return {"success": False, "error": f"Search pipeline initialization failed: {e}"}

        reasoner = MultiHopReasoner(
            search_pipeline=search_pipeline,
            llm_client=llm_client,
            neo4j_client=self.neo4j_client
        )
        result = await reasoner.reason(query=question, max_hops=max_hops)

        return {
            "success": True,
            "question": question,
            "final_answer": result.final_answer,
            "hops_used": result.hops_used,
            "confidence": result.confidence,
            "execution_time_ms": result.execution_time_ms,
            "evidence_count": len(result.all_evidence),
            "reasoning_chain": {
                "total_hops": result.reasoning_chain.total_hops,
                "avg_confidence": result.reasoning_chain.avg_confidence,
                "steps": [
                    {
                        "hop_number": step.hop_number,
                        "query": step.query,
                        "answer": step.answer,
                        "confidence": step.confidence,
                        "evidence_count": step.evidence_count,
                    }
                    for step in result.reasoning_chain.steps
                ]
            },
            "explanation": result.get_explanation()
        }

    @safe_execute
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

    @safe_execute
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

        # Ensure Neo4j connection is established
        await self._ensure_connected()

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

    @safe_execute
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
        self._require_neo4j()

        if not paper_ids or len(paper_ids) < 2:
            return {"success": False, "error": "At least 2 paper IDs required for comparison"}

        await self._ensure_connected()

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

    @safe_execute
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

        # Ensure Neo4j connection is established
        await self._ensure_connected()

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

    @safe_execute
    async def clinical_recommend(
        self,
        patient_context: str,
        intervention: Optional[str] = None
    ) -> dict:
        """임상 치료 추천 with evidence.

        환자 정보를 파싱하고, 그래프에서 관련 근거를 검색하여
        ClinicalReasoningEngine으로 치료 추천을 생성.

        Args:
            patient_context: 환자 정보 텍스트 (예: '65세 남성, 당뇨, L4-5 Stenosis')
            intervention: 특정 수술법 필터 (None이면 전체 후보)

        Returns:
            치료 추천 결과 딕셔너리
        """
        if not patient_context:
            return {"success": False, "error": "patient_context is required"}

        try:
            from solver.patient_context_parser import PatientContextParser
            from solver.clinical_reasoning_engine import ClinicalReasoningEngine
        except ImportError as e:
            return {"success": False, "error": f"Clinical reasoning modules not available: {e}"}

        # 1. Parse patient context
        parser = PatientContextParser()
        patient = parser.parse(patient_context)

        # 2. Search for relevant evidence from Neo4j
        available_evidence = []
        if self.neo4j_client:
            try:
                await self._ensure_connected()
                # Search evidence by pathology
                if patient.pathology:
                    query = """
                    MATCH (p:Paper)-[:INVESTIGATES]->(i:Intervention)-[a:AFFECTS]->(o:Outcome)
                    MATCH (p)-[:STUDIES]->(path:Pathology)
                    WHERE toLower(path.name) CONTAINS toLower($pathology)
                    RETURN i.name as intervention, o.name as outcome,
                           a.direction as direction, a.p_value as p_value,
                           a.is_significant as is_significant, a.effect_size as effect_size,
                           p.evidence_level as evidence_level,
                           p.paper_id as paper_id, p.title as title
                    LIMIT 50
                    """
                    results = await self.neo4j_client.run_query(
                        query, {"pathology": patient.pathology}
                    )
                    available_evidence = [dict(r) for r in results] if results else []
            except Exception as e:
                logger.warning(f"Evidence search failed: {e}")

        # 3. Run clinical reasoning engine
        engine = ClinicalReasoningEngine()
        recommendation = engine.recommend_treatment(
            patient=patient,
            available_evidence=available_evidence
        )

        # 4. Format response
        return {
            "success": True,
            "patient_summary": recommendation.patient_summary,
            "confidence": recommendation.confidence.value,
            "confidence_reasons": recommendation.confidence_reasons,
            "recommended": [
                {
                    "intervention": r.intervention,
                    "total_score": round(r.total_score, 3),
                    "evidence_score": round(r.evidence_score, 3),
                    "safety_score": round(r.safety_score, 3),
                    "is_first_line": r.is_first_line,
                    "evidence_level": r.evidence_level,
                    "indication": r.indication,
                }
                for r in recommendation.recommended_interventions
            ],
            "alternatives": [
                {
                    "intervention": r.intervention,
                    "total_score": round(r.total_score, 3),
                    "relative_contraindications": [
                        {"condition": c.condition, "reason": c.reason}
                        for c in r.get_relative_contraindications()
                    ],
                }
                for r in recommendation.alternative_interventions
            ],
            "contraindicated": [
                {
                    "intervention": r.intervention,
                    "absolute_contraindications": [
                        {"condition": c.condition, "reason": c.reason}
                        for c in r.get_absolute_contraindications()
                    ],
                }
                for r in recommendation.contraindicated_interventions
            ],
            "considerations": recommendation.considerations,
            "warnings": recommendation.warnings,
            "evidence_count": recommendation.total_evidence_count,
            "significant_evidence_count": recommendation.significant_evidence_count,
        }

"""Response Synthesizer - Evidence-based Answer Generation.

Hybrid 검색 결과(Graph + Vector)를 통합하여
학술적/임상적 질문에 대한 근거 기반 답변을 생성하는 모듈.

주요 기능:
- Graph Evidence 포맷팅 (통계, p-value, effect size)
- Vector Context 포맷팅 (배경 정보, 논의 내용)
- Citation 생성 (APA 형식)
- 상충 결과 요약 (갈등 포인트 설명)
- Confidence Score 계산 (근거 품질 기반)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Union

from ..llm import LLMClient, LLMConfig, ClaudeClient, GeminiClient
from ..solver.graph_result import GraphEvidence, PaperNode
from ..solver.hybrid_ranker import HybridResult

logger = logging.getLogger(__name__)


# Evidence Level 설명
EVIDENCE_LEVEL_DESCRIPTIONS = {
    "1a": "Level 1a (Meta-analysis/Systematic Review) - Highest quality evidence",
    "1b": "Level 1b (RCT) - High quality evidence",
    "2a": "Level 2a (Cohort Study) - Moderate quality evidence",
    "2b": "Level 2b (Case-Control Study) - Moderate quality evidence",
    "3": "Level 3 (Case Series) - Low quality evidence",
    "4": "Level 4 (Expert Opinion) - Very low quality evidence",
    "5": "Level 5 (Ungraded) - Evidence level not assessed",
}


@dataclass
class SynthesizedResponse:
    """통합 응답 결과.

    Attributes:
        answer: 메인 답변 (자연어)
        evidence_summary: 핵심 통계 요약
        supporting_papers: 인용 논문 목록
        confidence_score: 신뢰도 (0~1)
        conflicts: 상충 결과 설명 목록
        graph_evidences: Graph에서 추출된 근거 목록
        vector_contexts: Vector에서 추출된 문맥 목록
        metadata: 추가 메타데이터
    """
    answer: str
    evidence_summary: str
    supporting_papers: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    conflicts: list[str] = field(default_factory=list)

    # 상세 정보
    graph_evidences: list[str] = field(default_factory=list)
    vector_contexts: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class ResponseSynthesizer:
    """응답 통합 생성기.

    Graph 근거와 Vector 문맥을 통합하여 학술적/임상적 질문에 대한
    근거 기반 답변을 생성.

    처리 흐름:
        1. Graph Evidence 포맷팅: 통계, p-value, effect size
        2. Vector Context 포맷팅: 배경 정보, 논의 내용
        3. Conflict Detection: 상충 결과 탐지
        4. Confidence Calculation: 근거 품질 평가
        5. LLM Synthesis: Gemini를 활용한 자연어 답변 생성
    """

    def __init__(
        self,
        llm_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None,
        use_llm_synthesis: bool = True
    ):
        """초기화.

        Args:
            llm_client: LLM 클라이언트 (Claude 또는 Gemini, 없으면 기본값 생성)
            use_llm_synthesis: LLM 기반 답변 생성 여부 (False면 템플릿만 사용)
        """
        self.llm_client = llm_client or LLMClient(config=LLMConfig())
        self.use_llm_synthesis = use_llm_synthesis

    async def synthesize(
        self,
        query: str,
        hybrid_results: list[HybridResult],
        max_evidences: int = 5,
        max_contexts: int = 3
    ) -> SynthesizedResponse:
        """Hybrid 검색 결과를 통합하여 답변 생성.

        Args:
            query: 원본 질문
            hybrid_results: HybridRanker에서 반환된 결과 목록
            max_evidences: 최대 Graph 근거 수
            max_contexts: 최대 Vector 문맥 수

        Returns:
            SynthesizedResponse 객체
        """
        # 1. Graph vs Vector 분리
        graph_results = [r for r in hybrid_results if r.result_type == "graph"]
        vector_results = [r for r in hybrid_results if r.result_type == "vector"]

        # 2. Graph Evidence 포맷팅
        graph_evidences = self.format_graph_evidence(
            graph_results[:max_evidences]
        )

        # 3. Vector Context 포맷팅
        vector_contexts = self.format_vector_context(
            vector_results[:max_contexts]
        )

        # 4. Citation 생성
        supporting_papers = self.generate_citations(hybrid_results)

        # 5. Conflict Detection
        conflicts = self.summarize_conflicts(graph_results)

        # 6. Confidence Score 계산
        confidence_score = self._calculate_confidence(hybrid_results)

        # 7. Evidence Summary 생성
        evidence_summary = self._create_evidence_summary(
            graph_results, vector_results
        )

        # 8. LLM 기반 답변 생성
        if self.use_llm_synthesis:
            answer = await self._synthesize_with_llm(
                query=query,
                graph_evidences=graph_evidences,
                vector_contexts=vector_contexts,
                conflicts=conflicts
            )
        else:
            # 템플릿 기반 답변
            answer = self._template_answer(
                query, graph_evidences, vector_contexts
            )

        return SynthesizedResponse(
            answer=answer,
            evidence_summary=evidence_summary,
            supporting_papers=supporting_papers,
            confidence_score=confidence_score,
            conflicts=conflicts,
            graph_evidences=graph_evidences,
            vector_contexts=vector_contexts,
            metadata={
                "graph_count": len(graph_results),
                "vector_count": len(vector_results),
                "total_papers": len(supporting_papers)
            }
        )

    def format_graph_evidence(
        self,
        graph_results: list[HybridResult]
    ) -> list[str]:
        """Graph 근거를 포맷팅.

        통계, p-value, effect size를 포함한 읽기 쉬운 형태로 변환.

        Args:
            graph_results: Graph 유형 HybridResult 목록

        Returns:
            포맷된 근거 문자열 목록

        Example:
            ["TLIF improved Fusion Rate to 92% vs 85% (p=0.001, Level 1b)",
             "OLIF improved VAS by 3.2 points (95% CI: 2.1-4.3, p<0.001)"]
        """
        formatted = []

        for result in graph_results:
            if not result.evidence:
                continue

            evidence = result.evidence
            parts = []

            # 1. Intervention → Outcome → Value
            parts.append(
                f"{evidence.intervention} {evidence.direction} "
                f"{evidence.outcome} to {evidence.value}"
            )

            # 2. Control 비교값 (있으면)
            if evidence.value_control:
                parts.append(f"vs {evidence.value_control}")

            # 3. 통계적 유의성
            stat_parts = []
            if evidence.p_value is not None:
                stat_parts.append(f"p={evidence.p_value:.3f}")
            elif evidence.is_significant:
                stat_parts.append("p<0.05")

            if evidence.effect_size:
                stat_parts.append(evidence.effect_size)

            if evidence.confidence_interval:
                stat_parts.append(evidence.confidence_interval)

            # 4. Evidence Level
            if evidence.evidence_level and evidence.evidence_level != "5":
                stat_parts.append(f"Level {evidence.evidence_level}")

            if stat_parts:
                parts.append(f"({', '.join(stat_parts)})")

            formatted.append(" ".join(parts))

        return formatted

    def format_vector_context(
        self,
        vector_results: list[HybridResult]
    ) -> list[str]:
        """Vector 문맥을 포맷팅.

        배경 정보와 논의 내용을 읽기 쉬운 형태로 변환.

        Args:
            vector_results: Vector 유형 HybridResult 목록

        Returns:
            포맷된 문맥 문자열 목록

        Example:
            ["Background: TLIF is a minimally invasive fusion technique...",
             "Discussion: Long-term outcomes show sustained improvement..."]
        """
        formatted = []

        for result in vector_results:
            if not result.vector_result:
                continue

            vr = result.vector_result

            # 1. Section 정보 포함
            section = vr.section.title() if vr.section else "Context"

            # 2. 요약 또는 내용
            if vr.summary:
                text = vr.summary
            else:
                # 긴 내용은 200자로 제한
                text = result.content[:200]
                if len(result.content) > 200:
                    text += "..."

            # 3. 통계 포함 표시
            if vr.has_statistics:
                text += " [Contains statistics]"

            formatted.append(f"{section}: {text}")

        return formatted

    def generate_citations(
        self,
        hybrid_results: list[HybridResult]
    ) -> list[str]:
        """논문 인용 생성.

        APA 형식의 인용 목록 생성 (중복 제거).

        Args:
            hybrid_results: 전체 Hybrid 결과 목록

        Returns:
            인용 문자열 목록

        Example:
            ["Kim et al. (2024). OLIF for ASD. Spine.",
             "Lee et al. (2023). TLIF outcomes. J Neurosurg."]
        """
        citations = []
        seen_papers = set()

        for result in hybrid_results:
            # Graph 결과
            if result.result_type == "graph" and result.paper:
                paper = result.paper
                if paper.paper_id not in seen_papers:
                    citations.append(paper.get_citation())
                    seen_papers.add(paper.paper_id)

            # Vector 결과
            elif result.result_type == "vector" and result.vector_result:
                vr = result.vector_result
                # paper_id를 기준으로 중복 제거
                paper_id = vr.metadata.get("paper_id", vr.chunk_id)
                if paper_id not in seen_papers:
                    citation = f"{vr.title} ({vr.publication_year})"
                    citations.append(citation)
                    seen_papers.add(paper_id)

        return citations

    def summarize_conflicts(
        self,
        graph_results: list[HybridResult]
    ) -> list[str]:
        """상충 결과 요약.

        같은 Intervention-Outcome 쌍에 대해 상반된 결과(direction)를 찾아 설명.

        Args:
            graph_results: Graph 유형 HybridResult 목록

        Returns:
            갈등 설명 문자열 목록

        Example:
            ["Conflicting results for TLIF → PJK: improved (Kim 2024) vs worsened (Lee 2023)"]
        """
        conflicts = []

        # Intervention-Outcome 쌍별로 그룹화
        evidence_groups: dict[tuple[str, str], list[GraphEvidence]] = {}
        for result in graph_results:
            if not result.evidence:
                continue

            key = (result.evidence.intervention, result.evidence.outcome)
            if key not in evidence_groups:
                evidence_groups[key] = []
            evidence_groups[key].append(result.evidence)

        # 각 그룹에서 direction이 다른 경우 탐지
        for (intervention, outcome), evidences in evidence_groups.items():
            directions = set(e.direction for e in evidences if e.direction)

            if len(directions) > 1:
                # 상충 발견
                conflict_parts = []
                for direction in directions:
                    matching = [e for e in evidences if e.direction == direction]
                    # 첫 번째 논문만 표시
                    if matching:
                        conflict_parts.append(
                            f"{direction} (Paper {matching[0].source_paper_id})"
                        )

                conflict_text = (
                    f"Conflicting results for {intervention} → {outcome}: "
                    f"{' vs '.join(conflict_parts)}"
                )
                conflicts.append(conflict_text)

        return conflicts

    def _calculate_confidence(
        self,
        hybrid_results: list[HybridResult]
    ) -> float:
        """신뢰도 점수 계산.

        근거 품질, 통계적 유의성, 결과 일관성을 고려.

        Args:
            hybrid_results: 전체 Hybrid 결과 목록

        Returns:
            0~1 사이의 신뢰도 점수
        """
        if not hybrid_results:
            return 0.0

        scores = []

        for result in hybrid_results:
            score = result.score  # Base score from HybridRanker

            # Evidence Level Boost
            if result.result_type == "graph" and result.evidence:
                evidence_level = result.evidence.evidence_level
                if evidence_level in ["1a", "1b"]:
                    score *= 1.2  # High quality boost
                elif evidence_level in ["2a", "2b"]:
                    score *= 1.0
                else:
                    score *= 0.8  # Low quality penalty

            # Statistical Significance Boost
            if result.result_type == "graph" and result.evidence:
                if result.evidence.is_significant:
                    score *= 1.1

            scores.append(score)

        # 평균 점수
        avg_score = sum(scores) / len(scores)

        # 0~1 범위로 정규화
        return min(avg_score, 1.0)

    def _create_evidence_summary(
        self,
        graph_results: list[HybridResult],
        vector_results: list[HybridResult]
    ) -> str:
        """근거 요약 생성.

        통계 정보를 포함한 핵심 요약.

        Args:
            graph_results: Graph 결과 목록
            vector_results: Vector 결과 목록

        Returns:
            요약 문자열
        """
        parts = []

        # 1. Graph 통계
        if graph_results:
            significant_count = sum(
                1 for r in graph_results
                if r.evidence and r.evidence.is_significant
            )
            parts.append(
                f"{len(graph_results)} graph evidences found, "
                f"{significant_count} statistically significant"
            )

            # Evidence Level 분포
            levels = [
                r.evidence.evidence_level
                for r in graph_results
                if r.evidence and r.evidence.evidence_level
            ]
            if levels:
                level_counts = {}
                for level in levels:
                    level_counts[level] = level_counts.get(level, 0) + 1
                level_str = ", ".join(
                    f"{count}×Level {level}"
                    for level, count in sorted(level_counts.items())
                )
                parts.append(f"Evidence levels: {level_str}")

        # 2. Vector 통계
        if vector_results:
            parts.append(f"{len(vector_results)} relevant contexts found")

        return ". ".join(parts) + "."

    async def _synthesize_with_llm(
        self,
        query: str,
        graph_evidences: list[str],
        vector_contexts: list[str],
        conflicts: list[str]
    ) -> str:
        """LLM을 활용한 답변 생성.

        Gemini를 사용하여 근거와 문맥을 통합한 자연어 답변 생성.

        Args:
            query: 원본 질문
            graph_evidences: 포맷된 Graph 근거 목록
            vector_contexts: 포맷된 Vector 문맥 목록
            conflicts: 상충 결과 목록

        Returns:
            자연어 답변
        """
        # 프롬프트 구성
        prompt = f"""You are a spine surgery research assistant. Answer the following question based on the provided evidence.

Question: {query}

=== Graph Evidence (Statistical Results) ===
{chr(10).join(f"- {e}" for e in graph_evidences) if graph_evidences else "No graph evidence found."}

=== Vector Context (Background Information) ===
{chr(10).join(f"- {c}" for c in vector_contexts) if vector_contexts else "No additional context."}

=== Conflicting Results ===
{chr(10).join(f"- {c}" for c in conflicts) if conflicts else "No conflicts detected."}

Please provide a concise, evidence-based answer that:
1. Directly addresses the question
2. Cites the specific evidence (with statistics when available)
3. Acknowledges any conflicting results
4. Uses academic/clinical language appropriate for medical professionals
5. Indicates evidence quality (e.g., "based on Level 1a evidence")

Answer:"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system="You are an expert spine surgery researcher. "
                       "Provide accurate, evidence-based answers with proper citations.",
                use_cache=True
            )
            return response.text.strip()

        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}", exc_info=True)
            # Fallback to template
            return self._template_answer(query, graph_evidences, vector_contexts)

    def _template_answer(
        self,
        query: str,
        graph_evidences: list[str],
        vector_contexts: list[str]
    ) -> str:
        """템플릿 기반 답변 생성.

        LLM 사용 불가 시 폴백용 템플릿.

        Args:
            query: 원본 질문
            graph_evidences: 포맷된 Graph 근거 목록
            vector_contexts: 포맷된 Vector 문맥 목록

        Returns:
            템플릿 기반 답변
        """
        parts = [f"Regarding your question: '{query}'"]

        if graph_evidences:
            parts.append("\n\nKey Evidence:")
            parts.extend(f"- {e}" for e in graph_evidences)

        if vector_contexts:
            parts.append("\n\nAdditional Context:")
            parts.extend(f"- {c}" for c in vector_contexts)

        if not graph_evidences and not vector_contexts:
            parts.append("\n\nNo direct evidence found in the knowledge base.")

        return "\n".join(parts)


# 사용 예시
async def example_usage():
    """Response Synthesizer 사용 예시."""
    from ..solver.hybrid_ranker import HybridRanker, HybridResult
    from ..solver.graph_result import GraphEvidence, PaperNode

    # Mock data 생성
    graph_evidence = GraphEvidence(
        intervention="TLIF",
        outcome="Fusion Rate",
        value="92%",
        value_control="85%",
        p_value=0.001,
        is_significant=True,
        direction="improved",
        source_paper_id="paper_001",
        evidence_level="1b",
        effect_size="Cohen's d=0.8",
        confidence_interval="95% CI: 88-96%"
    )

    paper = PaperNode(
        paper_id="paper_001",
        title="TLIF for Lumbar Degenerative Disease",
        authors=["Kim", "Lee", "Park"],
        year=2024,
        journal="Spine",
        evidence_level="1b"
    )

    hybrid_results = [
        HybridResult(
            result_type="graph",
            score=0.95,
            content=graph_evidence.get_display_text(),
            source_id="paper_001",
            evidence=graph_evidence,
            paper=paper
        )
    ]

    # Response Synthesizer 초기화
    synthesizer = ResponseSynthesizer(use_llm_synthesis=False)

    # 답변 생성
    response = await synthesizer.synthesize(
        query="Is TLIF effective for improving fusion rate?",
        hybrid_results=hybrid_results,
        max_evidences=5,
        max_contexts=3
    )

    # 결과 출력
    print("=== Answer ===")
    print(response.answer)
    print("\n=== Evidence Summary ===")
    print(response.evidence_summary)
    print(f"\n=== Confidence Score: {response.confidence_score:.2f} ===")
    print("\n=== Supporting Papers ===")
    for citation in response.supporting_papers:
        print(f"- {citation}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())

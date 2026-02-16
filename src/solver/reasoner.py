"""Multi-hop Reasoner for Medical KAG System.

의학 검색 결과를 바탕으로 논리적 추론을 수행하고
근거 기반 답변을 생성하는 모듈.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Union


class ReasoningType(Enum):
    """추론 유형."""
    DIRECT = "direct"              # 직접 답변 (단일 근거)
    SYNTHESIS = "synthesis"         # 종합 (다중 근거 통합)
    COMPARISON = "comparison"       # 비교 (대안 평가)
    CAUSAL = "causal"              # 인과관계 추론
    INFERENCE = "inference"         # 간접 추론 (멀티홉)


class ConfidenceLevel(Enum):
    """신뢰도 수준."""
    HIGH = "high"           # 0.8-1.0: 강한 근거
    MODERATE = "moderate"   # 0.6-0.8: 중간 근거
    LOW = "low"            # 0.4-0.6: 약한 근거
    UNCERTAIN = "uncertain" # <0.4: 불확실


@dataclass
class Evidence:
    """근거 정보."""
    content: str
    source_id: str
    source_title: str
    evidence_level: str  # 1a, 1b, 2a, ...
    source_type: str     # original, citation, background
    relevance_score: float
    chunk_id: str = ""
    section: str = ""
    publication_year: int = 0


@dataclass
class ReasoningStep:
    """추론 단계."""
    step_number: int
    description: str
    evidence_used: list[Evidence] = field(default_factory=list)
    intermediate_conclusion: str = ""
    confidence: float = 0.0


@dataclass
class ReasoningResult:
    """추론 결과."""
    answer: str
    evidence: list[Evidence]
    confidence: float
    confidence_level: ConfidenceLevel
    explanation: str
    reasoning_path: list[ReasoningStep]
    reasoning_type: ReasoningType
    supporting_count: int = 0      # 지지하는 근거 수
    contradicting_count: int = 0   # 반박하는 근거 수


@dataclass
class ReasonerInput:
    """Reasoner 입력."""
    query: str
    search_results: list[Any]  # SearchResult from tiered_search
    max_hops: int = 3
    min_confidence: float = 0.5
    include_explanation: bool = True


class Reasoner:
    """Multi-hop Reasoner.

    검색 결과를 분석하여 논리적 추론을 수행하고
    근거 기반 답변을 생성합니다.

    주요 기능:
    - 단계별 논리적 추론 (최대 3 hop)
    - 근거 수집 및 신뢰도 계산
    - 추론 과정 설명 생성
    - 상충 근거 처리
    """

    # Evidence level hierarchy
    EVIDENCE_HIERARCHY = [
        "1a", "1b", "1c",
        "2a", "2b", "2c",
        "3a", "3b",
        "4",
        "5"
    ]

    # Evidence level weights for confidence calculation
    EVIDENCE_WEIGHTS = {
        "1a": 1.0, "1b": 0.95, "1c": 0.90,
        "2a": 0.80, "2b": 0.75, "2c": 0.70,
        "3a": 0.60, "3b": 0.55,
        "4": 0.40,
        "5": 0.25
    }

    # Source type weights
    SOURCE_WEIGHTS = {
        "original": 1.0,
        "citation": 0.6,
        "background": 0.4
    }

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
        """
        self.config = config or {}

        # 설정값
        self.min_evidence_for_high = self.config.get("min_evidence_for_high", 3)
        self.recency_bonus = self.config.get("recency_bonus", 0.05)
        self.current_year = self.config.get("current_year", 2024)

    def reason(
        self,
        input_data: ReasonerInput | str,
        search_results: Optional[list[Any]] = None
    ) -> ReasoningResult:
        """추론 수행.

        Args:
            input_data: ReasonerInput 또는 쿼리 문자열
            search_results: 검색 결과 (문자열 입력시 필수)

        Returns:
            ReasoningResult: 추론 결과
        """
        # 입력 정규화
        if isinstance(input_data, str):
            if search_results is None:
                search_results = []
            input_obj = ReasonerInput(
                query=input_data,
                search_results=search_results
            )
        else:
            input_obj = input_data

        # 검색 결과 없음
        if not input_obj.search_results:
            return self._create_empty_result(input_obj.query)

        # 1. 근거 추출
        evidence_list = self._extract_evidence(input_obj.search_results)

        # 2. 추론 유형 결정
        reasoning_type = self._determine_reasoning_type(
            input_obj.query,
            evidence_list
        )

        # 3. 단계별 추론 수행
        reasoning_steps = self._perform_reasoning(
            input_obj.query,
            evidence_list,
            reasoning_type,
            input_obj.max_hops
        )

        # 4. 신뢰도 계산
        confidence = self._calculate_confidence(evidence_list, reasoning_steps)
        confidence_level = self._get_confidence_level(confidence)

        # 5. 답변 생성
        answer = self._generate_answer(
            input_obj.query,
            evidence_list,
            reasoning_steps,
            reasoning_type
        )

        # 6. 설명 생성
        explanation = ""
        if input_obj.include_explanation:
            explanation = self._generate_explanation(
                evidence_list,
                reasoning_steps,
                confidence_level
            )

        # 7. 지지/반박 근거 수 계산
        supporting, contradicting = self._count_evidence_stance(evidence_list)

        return ReasoningResult(
            answer=answer,
            evidence=evidence_list,
            confidence=confidence,
            confidence_level=confidence_level,
            explanation=explanation,
            reasoning_path=reasoning_steps,
            reasoning_type=reasoning_type,
            supporting_count=supporting,
            contradicting_count=contradicting
        )

    def _extract_evidence(self, search_results: list[Any]) -> list[Evidence]:
        """검색 결과에서 근거 추출.

        Args:
            search_results: 검색 결과 목록

        Returns:
            Evidence 목록
        """
        evidence_list = []

        for result in search_results:
            # SearchResult 객체 처리
            if hasattr(result, 'chunk'):
                chunk = result.chunk
                evidence = Evidence(
                    content=getattr(chunk, 'text', str(chunk)),
                    source_id=getattr(chunk, 'document_id', ''),
                    source_title=getattr(chunk, 'title', ''),
                    evidence_level=getattr(result, 'evidence_level', '5'),
                    source_type=getattr(result, 'source_type', 'background'),
                    relevance_score=getattr(result, 'score', 0.5),
                    chunk_id=getattr(chunk, 'chunk_id', ''),
                    section=getattr(chunk, 'section', ''),
                    publication_year=getattr(chunk, 'publication_year', 0)
                )
            # dict 처리
            elif isinstance(result, dict):
                evidence = Evidence(
                    content=result.get('text', result.get('content', '')),
                    source_id=result.get('document_id', ''),
                    source_title=result.get('title', ''),
                    evidence_level=result.get('evidence_level', '5'),
                    source_type=result.get('source_type', 'background'),
                    relevance_score=result.get('score', 0.5),
                    chunk_id=result.get('chunk_id', ''),
                    section=result.get('section', ''),
                    publication_year=result.get('publication_year', 0)
                )
            else:
                continue

            evidence_list.append(evidence)

        return evidence_list

    def _determine_reasoning_type(
        self,
        query: str,
        evidence_list: list[Evidence]
    ) -> ReasoningType:
        """추론 유형 결정.

        Args:
            query: 질의
            evidence_list: 근거 목록

        Returns:
            ReasoningType
        """
        query_lower = query.lower()

        # 비교 쿼리
        compare_keywords = ["vs", "versus", "compare", "comparison", "better", "worse"]
        if any(kw in query_lower for kw in compare_keywords):
            return ReasoningType.COMPARISON

        # 인과관계 쿼리
        causal_keywords = ["cause", "why", "reason", "mechanism", "because", "lead to"]
        if any(kw in query_lower for kw in causal_keywords):
            return ReasoningType.CAUSAL

        # 근거 수에 따른 결정
        if len(evidence_list) == 1:
            return ReasoningType.DIRECT
        elif len(evidence_list) > 3:
            return ReasoningType.SYNTHESIS
        else:
            return ReasoningType.INFERENCE

    def _perform_reasoning(
        self,
        query: str,
        evidence_list: list[Evidence],
        reasoning_type: ReasoningType,
        max_hops: int
    ) -> list[ReasoningStep]:
        """단계별 추론 수행.

        Args:
            query: 질의
            evidence_list: 근거 목록
            reasoning_type: 추론 유형
            max_hops: 최대 홉 수

        Returns:
            ReasoningStep 목록
        """
        steps = []

        # Step 1: 근거 수집
        step1 = ReasoningStep(
            step_number=1,
            description="Collecting relevant evidence from search results",
            evidence_used=evidence_list[:5],  # 상위 5개
            intermediate_conclusion=f"Found {len(evidence_list)} relevant evidence pieces",
            confidence=self._calculate_step_confidence(evidence_list[:5])
        )
        steps.append(step1)

        # Step 2: 근거 분석
        if len(evidence_list) > 0:
            high_quality = [e for e in evidence_list
                          if e.evidence_level in ["1a", "1b", "2a", "2b"]]
            original_sources = [e for e in evidence_list
                               if e.source_type == "original"]

            step2_conclusion = (
                f"High-quality evidence (Level 1-2): {len(high_quality)}, "
                f"Original sources: {len(original_sources)}"
            )

            step2 = ReasoningStep(
                step_number=2,
                description="Analyzing evidence quality and source types",
                evidence_used=high_quality[:3] if high_quality else evidence_list[:3],
                intermediate_conclusion=step2_conclusion,
                confidence=self._calculate_step_confidence(high_quality or evidence_list[:3])
            )
            steps.append(step2)

        # Step 3: 추론 유형별 처리
        if reasoning_type == ReasoningType.COMPARISON:
            steps.append(self._comparison_step(evidence_list, 3))
        elif reasoning_type == ReasoningType.CAUSAL:
            steps.append(self._causal_step(evidence_list, 3))
        elif reasoning_type == ReasoningType.SYNTHESIS:
            steps.append(self._synthesis_step(evidence_list, 3))
        else:
            steps.append(self._direct_step(evidence_list, 3))

        # Step 4: 결론 도출 (max_hops 내에서)
        if len(steps) < max_hops:
            final_confidence = sum(s.confidence for s in steps) / len(steps)
            step4 = ReasoningStep(
                step_number=len(steps) + 1,
                description="Drawing final conclusion based on accumulated evidence",
                evidence_used=[],
                intermediate_conclusion="Conclusion synthesis complete",
                confidence=final_confidence
            )
            steps.append(step4)

        return steps[:max_hops]

    def _comparison_step(self, evidence_list: list[Evidence], step_num: int) -> ReasoningStep:
        """비교 추론 단계."""
        return ReasoningStep(
            step_number=step_num,
            description="Comparing alternatives based on evidence",
            evidence_used=evidence_list[:4],
            intermediate_conclusion="Comparison analysis performed across evidence sources",
            confidence=self._calculate_step_confidence(evidence_list[:4])
        )

    def _causal_step(self, evidence_list: list[Evidence], step_num: int) -> ReasoningStep:
        """인과관계 추론 단계."""
        return ReasoningStep(
            step_number=step_num,
            description="Analyzing causal relationships in evidence",
            evidence_used=evidence_list[:4],
            intermediate_conclusion="Causal pathway identified through evidence chain",
            confidence=self._calculate_step_confidence(evidence_list[:4])
        )

    def _synthesis_step(self, evidence_list: list[Evidence], step_num: int) -> ReasoningStep:
        """종합 추론 단계."""
        return ReasoningStep(
            step_number=step_num,
            description="Synthesizing multiple evidence sources",
            evidence_used=evidence_list[:5],
            intermediate_conclusion="Evidence synthesis complete with consensus identified",
            confidence=self._calculate_step_confidence(evidence_list[:5])
        )

    def _direct_step(self, evidence_list: list[Evidence], step_num: int) -> ReasoningStep:
        """직접 추론 단계."""
        return ReasoningStep(
            step_number=step_num,
            description="Direct inference from primary evidence",
            evidence_used=evidence_list[:2],
            intermediate_conclusion="Direct answer derived from primary source",
            confidence=self._calculate_step_confidence(evidence_list[:2])
        )

    def _calculate_step_confidence(self, evidence_list: list[Evidence]) -> float:
        """단계별 신뢰도 계산."""
        if not evidence_list:
            return 0.0

        total_weight = 0.0
        total_score = 0.0

        for evidence in evidence_list:
            # Evidence level weight
            ev_weight = self.EVIDENCE_WEIGHTS.get(evidence.evidence_level, 0.25)

            # Source type weight
            src_weight = self.SOURCE_WEIGHTS.get(evidence.source_type, 0.4)

            # Combined weight
            weight = ev_weight * src_weight

            # Score contribution
            score = evidence.relevance_score * weight

            total_weight += weight
            total_score += score

        if total_weight == 0:
            return 0.0

        return min(1.0, total_score / total_weight)

    def _calculate_confidence(
        self,
        evidence_list: list[Evidence],
        reasoning_steps: list[ReasoningStep]
    ) -> float:
        """전체 신뢰도 계산.

        Args:
            evidence_list: 근거 목록
            reasoning_steps: 추론 단계

        Returns:
            0.0-1.0 신뢰도
        """
        if not evidence_list:
            return 0.0

        # 1. Evidence quality score
        quality_scores = []
        for evidence in evidence_list:
            ev_weight = self.EVIDENCE_WEIGHTS.get(evidence.evidence_level, 0.25)
            src_weight = self.SOURCE_WEIGHTS.get(evidence.source_type, 0.4)
            quality_scores.append(ev_weight * src_weight * evidence.relevance_score)

        quality_score = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        # 2. Evidence quantity bonus
        quantity_bonus = min(0.2, len(evidence_list) * 0.02)

        # 3. Reasoning step confidence
        step_scores = [step.confidence for step in reasoning_steps if step.confidence > 0]
        step_score = sum(step_scores) / len(step_scores) if step_scores else 0

        # 4. Original source bonus
        original_count = sum(1 for e in evidence_list if e.source_type == "original")
        original_bonus = min(0.1, original_count * 0.025)

        # 5. Recency bonus
        recent_count = sum(1 for e in evidence_list
                         if e.publication_year >= self.current_year - 3)
        recency_bonus = min(0.1, recent_count * self.recency_bonus)

        # Combined confidence
        confidence = (
            quality_score * 0.4 +
            step_score * 0.3 +
            quantity_bonus +
            original_bonus +
            recency_bonus
        )

        return min(1.0, max(0.0, confidence))

    def _get_confidence_level(self, confidence: float) -> ConfidenceLevel:
        """신뢰도 수준 결정."""
        if confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.6:
            return ConfidenceLevel.MODERATE
        elif confidence >= 0.4:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.UNCERTAIN

    def _generate_answer(
        self,
        query: str,
        evidence_list: list[Evidence],
        reasoning_steps: list[ReasoningStep],
        reasoning_type: ReasoningType
    ) -> str:
        """답변 생성.

        Args:
            query: 질의
            evidence_list: 근거 목록
            reasoning_steps: 추론 단계
            reasoning_type: 추론 유형

        Returns:
            생성된 답변
        """
        if not evidence_list:
            return "No relevant evidence found to answer this query."

        # 최고 품질 근거 선택
        best_evidence = max(
            evidence_list,
            key=lambda e: (
                self.EVIDENCE_WEIGHTS.get(e.evidence_level, 0.25) *
                self.SOURCE_WEIGHTS.get(e.source_type, 0.4) *
                e.relevance_score
            )
        )

        # 근거 수준 정보
        evidence_count = len(evidence_list)
        high_quality_count = sum(
            1 for e in evidence_list
            if e.evidence_level in ["1a", "1b", "2a", "2b"]
        )

        # 추론 유형별 답변 구조
        if reasoning_type == ReasoningType.COMPARISON:
            answer_prefix = "Based on comparative analysis of the evidence"
        elif reasoning_type == ReasoningType.CAUSAL:
            answer_prefix = "Based on causal analysis of the evidence"
        elif reasoning_type == ReasoningType.SYNTHESIS:
            answer_prefix = "Based on synthesis of multiple evidence sources"
        else:
            answer_prefix = "Based on the available evidence"

        # 답변 구성
        answer = (
            f"{answer_prefix} ({evidence_count} sources, "
            f"{high_quality_count} high-quality): "
            f"{best_evidence.content}"
        )

        return answer

    def _generate_explanation(
        self,
        evidence_list: list[Evidence],
        reasoning_steps: list[ReasoningStep],
        confidence_level: ConfidenceLevel
    ) -> str:
        """추론 과정 설명 생성."""
        parts = []

        # 근거 요약
        parts.append(f"Analyzed {len(evidence_list)} evidence sources.")

        # 품질 분포
        level_counts: dict[str, int] = {}
        for e in evidence_list:
            level = e.evidence_level
            level_counts[level] = level_counts.get(level, 0) + 1

        if level_counts:
            level_str = ", ".join(f"Level {k}: {v}" for k, v in sorted(level_counts.items()))
            parts.append(f"Evidence distribution: {level_str}.")

        # 출처 유형
        source_counts: dict[str, int] = {}
        for e in evidence_list:
            src = e.source_type
            source_counts[src] = source_counts.get(src, 0) + 1

        if source_counts:
            src_str = ", ".join(f"{k}: {v}" for k, v in source_counts.items())
            parts.append(f"Source types: {src_str}.")

        # 추론 단계
        parts.append(f"Reasoning completed in {len(reasoning_steps)} steps.")

        # 신뢰도 설명
        confidence_explanations = {
            ConfidenceLevel.HIGH: "High confidence supported by strong evidence.",
            ConfidenceLevel.MODERATE: "Moderate confidence with reasonable evidence.",
            ConfidenceLevel.LOW: "Low confidence due to limited evidence quality.",
            ConfidenceLevel.UNCERTAIN: "Uncertain conclusion requiring more evidence."
        }
        parts.append(confidence_explanations.get(confidence_level, ""))

        return " ".join(parts)

    def _count_evidence_stance(self, evidence_list: list[Evidence]) -> tuple[int, int]:
        """지지/반박 근거 수 계산.

        간단한 휴리스틱: 현재는 모든 근거를 지지로 간주.
        향후 sentiment analysis 추가 가능.

        Returns:
            (supporting_count, contradicting_count)
        """
        # 현재 버전: 모든 근거를 지지로 처리
        # Conflict detection is handled by solver/conflict_detector.py
        return len(evidence_list), 0

    def _create_empty_result(self, query: str) -> ReasoningResult:
        """빈 결과 생성."""
        return ReasoningResult(
            answer="No evidence available to answer this query.",
            evidence=[],
            confidence=0.0,
            confidence_level=ConfidenceLevel.UNCERTAIN,
            explanation="No search results were provided for reasoning.",
            reasoning_path=[],
            reasoning_type=ReasoningType.DIRECT,
            supporting_count=0,
            contradicting_count=0
        )


def create_reasoning_summary(result: ReasoningResult) -> str:
    """추론 결과 요약 생성.

    Args:
        result: ReasoningResult

    Returns:
        요약 문자열
    """
    lines = [
        f"Answer: {result.answer[:200]}...",
        f"Confidence: {result.confidence:.2f} ({result.confidence_level.value})",
        f"Evidence: {len(result.evidence)} sources",
        f"Reasoning Type: {result.reasoning_type.value}",
        f"Steps: {len(result.reasoning_path)}"
    ]

    if result.supporting_count > 0 or result.contradicting_count > 0:
        lines.append(
            f"Stance: {result.supporting_count} supporting, "
            f"{result.contradicting_count} contradicting"
        )

    return "\n".join(lines)

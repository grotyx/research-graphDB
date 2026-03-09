"""Study Type Detector v1.0.

MeSH Terms, Publication Types, Abstract 키워드를 기반으로
연구 유형을 무료로 사전 감지합니다 (LLM 호출 없음).

이 정보는 LLM이 적절한 효과 측정치(HR, OR, RR 등)를 선택하는 데 도움을 줍니다.

Usage:
    detector = StudyTypeDetector()
    result = detector.detect(
        mesh_terms=["Randomized Controlled Trial", "Spine"],
        publication_types=["Randomized Controlled Trial"],
        abstract="This randomized controlled trial compared..."
    )
    print(result.study_type)  # "RCT"
    print(result.recommended_measures)  # ["MD", "SMD", "Cohen_d", "RR"]
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StudyType(Enum):
    """연구 유형."""
    META_ANALYSIS = "meta-analysis"
    SYSTEMATIC_REVIEW = "systematic-review"
    RCT = "RCT"
    PROSPECTIVE_COHORT = "prospective-cohort"
    RETROSPECTIVE_COHORT = "retrospective-cohort"
    CASE_CONTROL = "case-control"
    CROSS_SECTIONAL = "cross-sectional"
    CASE_SERIES = "case-series"
    CASE_REPORT = "case-report"
    EXPERT_OPINION = "expert-opinion"
    UNKNOWN = "unknown"


@dataclass
class StudyTypeResult:
    """연구 유형 감지 결과."""
    study_type: StudyType
    confidence: float  # 0.0 ~ 1.0
    recommended_measures: list[str] = field(default_factory=list)
    detection_sources: list[str] = field(default_factory=list)  # 감지에 사용된 소스


# 연구 유형별 권장 효과 측정치
STUDY_TYPE_MEASURES = {
    StudyType.META_ANALYSIS: ["SMD", "MD", "OR", "RR", "HR", "I2"],
    StudyType.SYSTEMATIC_REVIEW: ["SMD", "MD", "OR", "RR", "HR"],
    StudyType.RCT: ["MD", "SMD", "Cohen_d", "RR", "NNT"],
    StudyType.PROSPECTIVE_COHORT: ["HR", "RR", "OR", "NNT"],
    StudyType.RETROSPECTIVE_COHORT: ["HR", "OR", "RR"],
    StudyType.CASE_CONTROL: ["OR"],
    StudyType.CROSS_SECTIONAL: ["OR", "PR"],  # PR = Prevalence Ratio
    StudyType.CASE_SERIES: ["descriptive"],
    StudyType.CASE_REPORT: ["descriptive"],
    StudyType.EXPERT_OPINION: ["descriptive"],
    StudyType.UNKNOWN: ["MD", "OR", "HR", "RR"],  # 일반적인 것들
}


# MeSH Terms → Study Type 매핑
MESH_TERM_MAPPING = {
    # Meta-analysis / Systematic Review
    "Meta-Analysis": StudyType.META_ANALYSIS,
    "Systematic Review": StudyType.SYSTEMATIC_REVIEW,
    "Meta-Analysis as Topic": StudyType.META_ANALYSIS,
    "Systematic Reviews as Topic": StudyType.SYSTEMATIC_REVIEW,

    # RCT
    "Randomized Controlled Trial": StudyType.RCT,
    "Randomized Controlled Trials as Topic": StudyType.RCT,
    "Random Allocation": StudyType.RCT,
    "Double-Blind Method": StudyType.RCT,
    "Single-Blind Method": StudyType.RCT,

    # Cohort
    "Cohort Studies": StudyType.PROSPECTIVE_COHORT,
    "Prospective Studies": StudyType.PROSPECTIVE_COHORT,
    "Follow-Up Studies": StudyType.PROSPECTIVE_COHORT,
    "Retrospective Studies": StudyType.RETROSPECTIVE_COHORT,
    "Longitudinal Studies": StudyType.PROSPECTIVE_COHORT,

    # Case-Control
    "Case-Control Studies": StudyType.CASE_CONTROL,

    # Cross-sectional
    "Cross-Sectional Studies": StudyType.CROSS_SECTIONAL,

    # Case Series/Report
    "Case Reports": StudyType.CASE_REPORT,
}


# Publication Types → Study Type 매핑
PUBLICATION_TYPE_MAPPING = {
    # Meta-analysis / Systematic Review
    "Meta-Analysis": StudyType.META_ANALYSIS,
    "Systematic Review": StudyType.SYSTEMATIC_REVIEW,
    "Review": StudyType.SYSTEMATIC_REVIEW,  # Could be narrative review too

    # RCT
    "Randomized Controlled Trial": StudyType.RCT,
    "Clinical Trial": StudyType.RCT,
    "Clinical Trial, Phase I": StudyType.RCT,
    "Clinical Trial, Phase II": StudyType.RCT,
    "Clinical Trial, Phase III": StudyType.RCT,
    "Clinical Trial, Phase IV": StudyType.RCT,
    "Controlled Clinical Trial": StudyType.RCT,
    "Pragmatic Clinical Trial": StudyType.RCT,

    # Others
    "Observational Study": StudyType.PROSPECTIVE_COHORT,
    "Comparative Study": StudyType.RETROSPECTIVE_COHORT,
    "Multicenter Study": StudyType.PROSPECTIVE_COHORT,
    "Case Reports": StudyType.CASE_REPORT,
    "Comment": StudyType.EXPERT_OPINION,
    "Editorial": StudyType.EXPERT_OPINION,
    "Letter": StudyType.EXPERT_OPINION,
    "Practice Guideline": StudyType.SYSTEMATIC_REVIEW,
}


# Abstract 키워드 패턴 → Study Type 매핑
KEYWORD_PATTERNS = [
    # Meta-analysis (highest priority)
    (r"\bmeta[\-\s]?analysis\b", StudyType.META_ANALYSIS, 0.9),
    (r"\bpooled\s+analysis\b", StudyType.META_ANALYSIS, 0.85),
    (r"\bsystematic\s+review\b", StudyType.SYSTEMATIC_REVIEW, 0.9),

    # RCT
    (r"\brandomized\s+controlled\s+trial\b", StudyType.RCT, 0.95),
    (r"\brandomised\s+controlled\s+trial\b", StudyType.RCT, 0.95),
    (r"\brandomized\s+trial\b", StudyType.RCT, 0.85),
    (r"\brandomised\s+trial\b", StudyType.RCT, 0.85),
    (r"\brandomly\s+assigned\b", StudyType.RCT, 0.8),
    (r"\brandomly\s+allocated\b", StudyType.RCT, 0.8),
    (r"\bdouble[\-\s]?blind\b", StudyType.RCT, 0.75),
    (r"\bplacebo[\-\s]?controlled\b", StudyType.RCT, 0.8),

    # Cohort
    (r"\bprospective\s+cohort\b", StudyType.PROSPECTIVE_COHORT, 0.9),
    (r"\bretrospective\s+cohort\b", StudyType.RETROSPECTIVE_COHORT, 0.9),
    (r"\blongitudinal\s+study\b", StudyType.PROSPECTIVE_COHORT, 0.75),
    (r"\bfollow[\-\s]?up\s+study\b", StudyType.PROSPECTIVE_COHORT, 0.7),
    (r"\bprospective(?:ly)?\s+(?:collected|enrolled|followed)\b", StudyType.PROSPECTIVE_COHORT, 0.8),
    (r"\bretrospective(?:ly)?\s+(?:reviewed|analyzed|collected)\b", StudyType.RETROSPECTIVE_COHORT, 0.8),

    # Case-Control
    (r"\bcase[\-\s]?control\s+study\b", StudyType.CASE_CONTROL, 0.9),
    (r"\bmatched\s+controls?\b", StudyType.CASE_CONTROL, 0.7),

    # Cross-sectional
    (r"\bcross[\-\s]?sectional\s+study\b", StudyType.CROSS_SECTIONAL, 0.9),
    (r"\bcross[\-\s]?sectional\s+analysis\b", StudyType.CROSS_SECTIONAL, 0.85),
    (r"\bprevalence\s+study\b", StudyType.CROSS_SECTIONAL, 0.75),

    # Case Series/Report
    (r"\bcase\s+series\b", StudyType.CASE_SERIES, 0.85),
    (r"\bcase\s+report\b", StudyType.CASE_REPORT, 0.85),
    (r"\bsingle\s+case\b", StudyType.CASE_REPORT, 0.7),

    # Survival analysis indicator (suggests cohort with HR)
    (r"\bhazard\s+ratio\b", StudyType.PROSPECTIVE_COHORT, 0.6),
    (r"\bkaplan[\-\s]?meier\b", StudyType.PROSPECTIVE_COHORT, 0.6),
    (r"\bcox\s+regression\b", StudyType.PROSPECTIVE_COHORT, 0.6),
    (r"\bsurvival\s+analysis\b", StudyType.PROSPECTIVE_COHORT, 0.6),

    # Odds ratio indicator (suggests case-control or cross-sectional)
    (r"\bodds\s+ratio\b", StudyType.CASE_CONTROL, 0.5),  # Lower confidence as OR is used in many study types
]


class StudyTypeDetector:
    """연구 유형 감지기 (규칙 기반, LLM 호출 없음)."""

    def detect(
        self,
        mesh_terms: Optional[list[str]] = None,
        publication_types: Optional[list[str]] = None,
        abstract: Optional[str] = None,
        title: Optional[str] = None,
    ) -> StudyTypeResult:
        """연구 유형을 감지합니다.

        Args:
            mesh_terms: MeSH Terms 리스트
            publication_types: Publication Types 리스트
            abstract: 초록 텍스트
            title: 제목 텍스트

        Returns:
            StudyTypeResult 객체
        """
        candidates: list[tuple[StudyType, float, str]] = []

        # 1. MeSH Terms에서 감지 (높은 신뢰도)
        if mesh_terms:
            for term in mesh_terms:
                normalized = term.strip()
                if normalized in MESH_TERM_MAPPING:
                    study_type = MESH_TERM_MAPPING[normalized]
                    candidates.append((study_type, 0.95, f"MeSH: {normalized}"))

        # 2. Publication Types에서 감지 (높은 신뢰도)
        if publication_types:
            for ptype in publication_types:
                normalized = ptype.strip()
                if normalized in PUBLICATION_TYPE_MAPPING:
                    study_type = PUBLICATION_TYPE_MAPPING[normalized]
                    candidates.append((study_type, 0.9, f"PubType: {normalized}"))

        # 3. Abstract/Title에서 키워드 감지
        text = ""
        if abstract:
            text += abstract + " "
        if title:
            text += title

        if text:
            text_lower = text.lower()
            for pattern, study_type, confidence in KEYWORD_PATTERNS:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    candidates.append((study_type, confidence, f"Keyword: {pattern}"))

        # 결과 결정
        if not candidates:
            return StudyTypeResult(
                study_type=StudyType.UNKNOWN,
                confidence=0.0,
                recommended_measures=STUDY_TYPE_MEASURES[StudyType.UNKNOWN],
                detection_sources=["No pattern matched"],
            )

        # 가장 높은 신뢰도의 연구 유형 선택
        # 동일 연구 유형이 여러 번 감지되면 신뢰도 보정
        type_scores: dict[StudyType, list[float]] = {}
        type_sources: dict[StudyType, list[str]] = {}

        for study_type, confidence, source in candidates:
            if study_type not in type_scores:
                type_scores[study_type] = []
                type_sources[study_type] = []
            type_scores[study_type].append(confidence)
            type_sources[study_type].append(source)

        # 각 유형별 최종 점수 계산 (최대값 + 추가 감지시 보너스)
        final_scores = {}
        for study_type, scores in type_scores.items():
            max_score = max(scores)
            bonus = min(0.05 * (len(scores) - 1), 0.1)  # 추가 감지당 +0.05, 최대 +0.1
            final_scores[study_type] = min(max_score + bonus, 1.0)

        # 최고 점수 연구 유형 선택
        best_type = max(final_scores, key=final_scores.get)
        best_confidence = final_scores[best_type]

        return StudyTypeResult(
            study_type=best_type,
            confidence=best_confidence,
            recommended_measures=STUDY_TYPE_MEASURES[best_type],
            detection_sources=type_sources[best_type],
        )

    def get_recommended_measures(self, study_type: StudyType | str) -> list[str]:
        """연구 유형에 권장되는 효과 측정치를 반환합니다."""
        if isinstance(study_type, str):
            try:
                study_type = StudyType(study_type)
            except ValueError:
                return STUDY_TYPE_MEASURES[StudyType.UNKNOWN]

        return STUDY_TYPE_MEASURES.get(study_type, STUDY_TYPE_MEASURES[StudyType.UNKNOWN])

    def enhance_prompt_with_study_type(
        self,
        base_prompt: str,
        study_type_result: StudyTypeResult,
    ) -> str:
        """프롬프트에 연구 유형 힌트를 추가합니다.

        Args:
            base_prompt: 기본 LLM 프롬프트
            study_type_result: 감지된 연구 유형 결과

        Returns:
            연구 유형 힌트가 추가된 프롬프트
        """
        if study_type_result.study_type == StudyType.UNKNOWN:
            return base_prompt

        hint = f"""

## STUDY TYPE HINT (Pre-detected)
Based on metadata analysis, this appears to be a **{study_type_result.study_type.value}** study.
Confidence: {study_type_result.confidence:.0%}
Sources: {', '.join(study_type_result.detection_sources[:3])}

**Recommended Effect Measures for this study type:**
{', '.join(study_type_result.recommended_measures)}

Please prioritize extracting these effect measures when analyzing the paper.
"""
        return base_prompt + hint

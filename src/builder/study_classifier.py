"""Study Classifier module for identifying study types and evidence levels."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StudyType(Enum):
    """연구 유형."""
    META_ANALYSIS = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    RCT = "rct"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    CASE_SERIES = "case_series"
    CASE_REPORT = "case_report"
    CROSS_SECTIONAL = "cross_sectional"
    EXPERT_OPINION = "expert_opinion"
    GUIDELINE = "guideline"
    UNKNOWN = "unknown"


class EvidenceLevel(Enum):
    """근거 수준 (Oxford CEBM 기반)."""
    LEVEL_1A = "1a"  # Systematic review of RCTs
    LEVEL_1B = "1b"  # Individual RCT
    LEVEL_2A = "2a"  # Systematic review of cohort studies
    LEVEL_2B = "2b"  # Individual cohort / low-quality RCT
    LEVEL_2C = "2c"  # Outcomes research
    LEVEL_3A = "3a"  # Systematic review of case-control studies
    LEVEL_3B = "3b"  # Individual case-control study
    LEVEL_4 = "4"    # Case series / poor quality cohort
    LEVEL_5 = "5"    # Expert opinion


@dataclass
class StudyInput:
    """연구 유형 분류 입력."""
    text: str
    title: Optional[str] = None
    abstract: Optional[str] = None


@dataclass
class StudyOutput:
    """연구 유형 분류 결과."""
    study_type: StudyType
    evidence_level: EvidenceLevel
    confidence: float                                    # 0.0 ~ 1.0
    evidence_keywords: list[str] = field(default_factory=list)
    quality_indicators: dict = field(default_factory=dict)


class StudyClassifier:
    """연구 유형 분류기."""

    # 연구 유형별 키워드
    STUDY_KEYWORDS: dict[StudyType, dict] = {
        StudyType.META_ANALYSIS: {
            "primary": ["meta-analysis", "meta analysis", "pooled analysis",
                       "quantitative synthesis"],
            "secondary": ["forest plot", "heterogeneity", "I²", "I-squared",
                         "I2", "fixed effect", "random effect", "publication bias",
                         "funnel plot", "egger", "begg"],
            "weight": 1.0
        },
        StudyType.SYSTEMATIC_REVIEW: {
            "primary": ["systematic review", "systematic literature review",
                       "scoping review"],
            "secondary": ["PRISMA", "search strategy", "inclusion criteria",
                         "exclusion criteria", "quality assessment", "bias assessment",
                         "risk of bias", "GRADE", "Newcastle-Ottawa"],
            "weight": 0.95
        },
        StudyType.RCT: {
            "primary": ["randomized controlled trial", "randomised controlled trial",
                       "RCT", "randomized trial", "randomised trial",
                       "randomized clinical trial"],
            "secondary": ["randomization", "randomisation", "double-blind",
                         "double blind", "single-blind", "triple-blind",
                         "placebo-controlled", "placebo controlled",
                         "intention-to-treat", "intention to treat", "ITT",
                         "per-protocol", "blinded", "allocation concealment",
                         "CONSORT", "block randomization"],
            "weight": 0.95
        },
        StudyType.COHORT: {
            "primary": ["cohort study", "cohort analysis", "prospective study",
                       "longitudinal study", "follow-up study", "prospective cohort",
                       "retrospective cohort"],
            "secondary": ["followed", "person-years", "incidence", "hazard ratio",
                         "survival analysis", "Kaplan-Meier", "Cox regression",
                         "Cox proportional", "time-to-event", "median follow-up"],
            "weight": 0.85
        },
        StudyType.CASE_CONTROL: {
            "primary": ["case-control", "case control", "case-referent"],
            "secondary": ["odds ratio", "matched", "controls", "cases",
                         "retrospective", "matching", "conditional logistic"],
            "weight": 0.8
        },
        StudyType.CROSS_SECTIONAL: {
            "primary": ["cross-sectional", "cross sectional", "survey",
                       "prevalence study"],
            "secondary": ["prevalence", "point-in-time", "questionnaire",
                         "at a single time point", "snapshot"],
            "weight": 0.7
        },
        StudyType.CASE_SERIES: {
            "primary": ["case series", "case report series", "consecutive cases"],
            "secondary": ["consecutive patients", "retrospective review",
                         "chart review"],
            "weight": 0.6
        },
        StudyType.CASE_REPORT: {
            "primary": ["case report", "case presentation", "clinical case"],
            "secondary": ["single patient", "rare case", "unusual presentation",
                         "we present a case", "we report a case"],
            "weight": 0.5
        },
        StudyType.GUIDELINE: {
            "primary": ["guideline", "clinical practice guideline",
                       "consensus statement", "position statement",
                       "recommendation"],
            "secondary": ["expert panel", "Delphi", "grade of recommendation",
                         "level of evidence"],
            "weight": 0.4
        },
        StudyType.EXPERT_OPINION: {
            "primary": ["expert opinion", "editorial", "commentary", "letter",
                       "perspective", "viewpoint"],
            "secondary": ["in our opinion", "we believe", "based on our experience"],
            "weight": 0.3
        }
    }

    # Evidence Level 매핑
    EVIDENCE_LEVEL_MAP: dict[StudyType, EvidenceLevel] = {
        StudyType.META_ANALYSIS: EvidenceLevel.LEVEL_1A,
        StudyType.SYSTEMATIC_REVIEW: EvidenceLevel.LEVEL_1A,
        StudyType.RCT: EvidenceLevel.LEVEL_1B,
        StudyType.COHORT: EvidenceLevel.LEVEL_2B,
        StudyType.CASE_CONTROL: EvidenceLevel.LEVEL_3B,
        StudyType.CROSS_SECTIONAL: EvidenceLevel.LEVEL_4,
        StudyType.CASE_SERIES: EvidenceLevel.LEVEL_4,
        StudyType.CASE_REPORT: EvidenceLevel.LEVEL_4,
        StudyType.GUIDELINE: EvidenceLevel.LEVEL_5,
        StudyType.EXPERT_OPINION: EvidenceLevel.LEVEL_5,
        StudyType.UNKNOWN: EvidenceLevel.LEVEL_5,
    }

    # RCT 품질 지표
    RCT_HIGH_QUALITY = [
        "double-blind", "double blind",
        "allocation concealment",
        "intention-to-treat", "intention to treat",
        "low attrition", "low dropout",
        "pre-registered", "preregistered",
        "adequately powered"
    ]

    RCT_LOW_QUALITY = [
        "single-blind", "single blind",
        "open-label", "open label",
        "per-protocol only",
        "high dropout", "high attrition",
        "small sample", "pilot study",
        "underpowered"
    ]

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
                - min_confidence: 최소 신뢰도 (기본값: 0.5)
                - require_quality_assessment: RCT 품질 평가 수행 여부
                - downgrade_low_quality_rct: 저품질 RCT를 Level 2b로 하향 여부
        """
        self.config = config or {}
        self.min_confidence = self.config.get("min_confidence", 0.5)
        self.require_quality_assessment = self.config.get("require_quality_assessment", True)
        self.downgrade_low_quality_rct = self.config.get("downgrade_low_quality_rct", True)

        # 정규식 패턴 컴파일
        self._compiled_patterns: dict[StudyType, dict[str, list[re.Pattern]]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """키워드 패턴을 정규식으로 컴파일."""
        for study_type, data in self.STUDY_KEYWORDS.items():
            self._compiled_patterns[study_type] = {
                "primary": [
                    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                    for kw in data["primary"]
                ],
                "secondary": [
                    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                    for kw in data["secondary"]
                ]
            }

    def classify(self, input_data: StudyInput) -> StudyOutput:
        """연구 유형 분류.

        Args:
            input_data: 분류 입력 데이터

        Returns:
            연구 유형 분류 결과
        """
        # 텍스트 결합 (title > abstract > text 순으로 가중치)
        full_text = self._combine_text(input_data)

        if not full_text.strip():
            return StudyOutput(
                study_type=StudyType.UNKNOWN,
                evidence_level=EvidenceLevel.LEVEL_5,
                confidence=0.0,
                evidence_keywords=[],
                quality_indicators={}
            )

        # 각 연구 유형별 점수 계산
        scores: dict[StudyType, float] = {}
        evidence_found: dict[StudyType, list[str]] = {}

        for study_type, patterns in self._compiled_patterns.items():
            score, evidence = self._calculate_score(full_text, patterns, input_data.title)
            weight = self.STUDY_KEYWORDS[study_type]["weight"]
            scores[study_type] = score * weight
            evidence_found[study_type] = evidence

        # 최고 점수 연구 유형 선택
        if not scores or max(scores.values()) == 0:
            return StudyOutput(
                study_type=StudyType.UNKNOWN,
                evidence_level=EvidenceLevel.LEVEL_5,
                confidence=0.0,
                evidence_keywords=[],
                quality_indicators={}
            )

        best_type = max(scores, key=lambda k: scores[k])
        confidence = self._normalize_confidence(scores[best_type], scores)

        # 신뢰도가 낮으면 UNKNOWN
        if confidence < self.min_confidence:
            best_type = StudyType.UNKNOWN

        # 품질 지표 추출
        quality = self._extract_quality_indicators(full_text, best_type)

        # Evidence Level 결정 (품질 고려)
        evidence_level = self._determine_evidence_level(best_type, quality)

        return StudyOutput(
            study_type=best_type,
            evidence_level=evidence_level,
            confidence=round(confidence, 3),
            evidence_keywords=evidence_found.get(best_type, []),
            quality_indicators=quality
        )

    def _combine_text(self, input_data: StudyInput) -> str:
        """입력 텍스트 결합.

        Args:
            input_data: 입력 데이터

        Returns:
            결합된 텍스트 (title이 2번 반복되어 가중치 부여)
        """
        parts = []

        # 제목에 높은 가중치 (2번 반복)
        if input_data.title:
            parts.extend([input_data.title, input_data.title])

        # 초록
        if input_data.abstract:
            parts.append(input_data.abstract)

        # 본문
        if input_data.text:
            parts.append(input_data.text)

        return " ".join(parts)

    def _calculate_score(
        self,
        text: str,
        patterns: dict[str, list[re.Pattern]],
        title: Optional[str] = None
    ) -> tuple[float, list[str]]:
        """연구 유형 점수 계산.

        Args:
            text: 분석할 텍스트
            patterns: 컴파일된 패턴
            title: 논문 제목

        Returns:
            (점수, 매칭된 키워드 목록) 튜플
        """
        score = 0.0
        evidence = []

        # Primary 키워드 (높은 가중치)
        for pattern in patterns["primary"]:
            matches = pattern.findall(text)
            if matches:
                score += len(matches) * 3.0  # Primary는 3배 가중치
                evidence.extend(matches)

                # 제목에 있으면 추가 보너스
                if title and pattern.search(title):
                    score += 5.0

        # Secondary 키워드 (낮은 가중치)
        for pattern in patterns["secondary"]:
            matches = pattern.findall(text)
            if matches:
                score += len(matches) * 1.0
                evidence.extend(matches)

        return score, list(set(evidence))

    def _normalize_confidence(
        self,
        best_score: float,
        all_scores: dict[StudyType, float]
    ) -> float:
        """신뢰도 정규화.

        Args:
            best_score: 최고 점수
            all_scores: 모든 점수

        Returns:
            정규화된 신뢰도 (0.0~1.0)
        """
        total = sum(all_scores.values())
        if total == 0:
            return 0.0

        # 최고 점수의 비율
        ratio = best_score / total

        # 점수 절대값도 고려 (점수가 낮으면 신뢰도도 낮음)
        absolute_factor = min(1.0, best_score / 10.0)

        return ratio * 0.7 + absolute_factor * 0.3

    def _extract_quality_indicators(
        self,
        text: str,
        study_type: StudyType
    ) -> dict:
        """품질 지표 추출.

        Args:
            text: 분석할 텍스트
            study_type: 연구 유형

        Returns:
            품질 지표 딕셔너리
        """
        quality: dict = {}

        if study_type == StudyType.RCT:
            # RCT 품질 지표 확인
            high_quality_count = 0
            low_quality_count = 0

            for indicator in self.RCT_HIGH_QUALITY:
                if re.search(r'\b' + re.escape(indicator) + r'\b', text, re.IGNORECASE):
                    quality[indicator.replace("-", "_").replace(" ", "_")] = True
                    high_quality_count += 1

            for indicator in self.RCT_LOW_QUALITY:
                if re.search(r'\b' + re.escape(indicator) + r'\b', text, re.IGNORECASE):
                    quality[indicator.replace("-", "_").replace(" ", "_")] = True
                    low_quality_count += 1

            quality["high_quality_indicators"] = high_quality_count
            quality["low_quality_indicators"] = low_quality_count
            quality["is_low_quality"] = low_quality_count > high_quality_count

        elif study_type == StudyType.SYSTEMATIC_REVIEW:
            # SR이 RCT를 포함하는지 확인
            includes_rcts = bool(re.search(
                r'\b(RCT|randomized|randomised)\b',
                text,
                re.IGNORECASE
            ))
            quality["includes_rcts"] = includes_rcts

        return quality

    def _determine_evidence_level(
        self,
        study_type: StudyType,
        quality: dict
    ) -> EvidenceLevel:
        """품질을 고려한 Evidence Level 결정.

        Args:
            study_type: 연구 유형
            quality: 품질 지표

        Returns:
            Evidence Level
        """
        base_level = self.EVIDENCE_LEVEL_MAP.get(study_type, EvidenceLevel.LEVEL_5)

        # RCT 품질 조정
        if study_type == StudyType.RCT and self.downgrade_low_quality_rct:
            if quality.get("is_low_quality", False):
                return EvidenceLevel.LEVEL_2B

        # Systematic review의 대상 연구 유형 확인
        if study_type == StudyType.SYSTEMATIC_REVIEW:
            if quality.get("includes_rcts", False):
                return EvidenceLevel.LEVEL_1A
            else:
                return EvidenceLevel.LEVEL_2A

        return base_level

    def classify_batch(self, inputs: list[StudyInput]) -> list[StudyOutput]:
        """여러 텍스트를 일괄 분류.

        Args:
            inputs: 입력 데이터 목록

        Returns:
            분류 결과 목록
        """
        return [self.classify(input_data) for input_data in inputs]

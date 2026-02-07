"""Section Classifier module for categorizing paper sections and assigning tiers."""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SectionInput:
    """섹션 분류 입력."""
    text: str
    context: Optional[str] = None
    source_position: Optional[float] = None  # 문서 내 위치 (0.0~1.0)


@dataclass
class SectionOutput:
    """섹션 분류 결과."""
    section: str          # abstract, introduction, methods, results, discussion, conclusion, other
    tier: int             # 1 (핵심) 또는 2 (상세)
    confidence: float     # 0.0 ~ 1.0
    evidence: list[str] = field(default_factory=list)  # 분류 근거 키워드


class SectionClassifier:
    """논문 섹션 분류기."""

    # 섹션별 키워드 (가중치 포함)
    SECTION_KEYWORDS: dict[str, dict] = {
        "abstract": {
            "keywords": [
                "abstract", "summary", "background and aims", "objective",
                "objectives", "purpose", "aim of study", "study aim"
            ],
            "weight": 1.0
        },
        "introduction": {
            "keywords": [
                "introduction", "background", "purpose", "rationale",
                "literature review", "theoretical framework"
            ],
            "weight": 0.9
        },
        "methods": {
            "keywords": [
                "methods", "methodology", "materials", "study design",
                "participants", "inclusion criteria", "exclusion criteria",
                "statistical analysis", "ethics", "data collection",
                "materials and methods", "patients and methods",
                "study population", "outcome measures"
            ],
            "weight": 0.95
        },
        "results": {
            "keywords": [
                "results", "findings", "outcomes", "we found",
                "table 1", "table 2", "figure 1", "figure 2",
                "showed that", "demonstrated", "revealed",
                "significant difference", "no significant", "p <", "p ="
            ],
            "weight": 1.0
        },
        "discussion": {
            "keywords": [
                "discussion", "limitations", "implications",
                "compared with previous", "consistent with", "in contrast",
                "strength", "weakness", "future research", "clinical implications"
            ],
            "weight": 0.9
        },
        "conclusion": {
            "keywords": [
                "conclusion", "conclusions", "in summary", "we conclude",
                "in conclusion", "to summarize", "overall", "taken together",
                "in summary", "concluding remarks"
            ],
            "weight": 1.0
        }
    }

    # Tier 매핑 (1=핵심, 2=상세)
    TIER_MAP: dict[str, int] = {
        "abstract": 1,
        "results": 1,
        "conclusion": 1,
        "introduction": 2,
        "methods": 2,
        "discussion": 2,
        "other": 2
    }

    # 위치 기반 섹션 추정
    POSITION_HINTS: dict[str, tuple[float, float]] = {
        "abstract": (0.0, 0.1),
        "introduction": (0.05, 0.25),
        "methods": (0.15, 0.45),
        "results": (0.35, 0.75),
        "discussion": (0.55, 0.90),
        "conclusion": (0.80, 1.0)
    }

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
                - min_confidence: 최소 신뢰도 (기본값: 0.3)
                - position_weight: 위치 가중치 (기본값: 0.2)
                - keyword_weight: 키워드 가중치 (기본값: 0.8)
        """
        self.config = config or {}
        self.min_confidence = self.config.get("min_confidence", 0.3)
        self.position_weight = self.config.get("position_weight", 0.2)
        self.keyword_weight = self.config.get("keyword_weight", 0.8)

        # 정규식 패턴 컴파일
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """키워드 패턴을 정규식으로 컴파일."""
        for section, data in self.SECTION_KEYWORDS.items():
            patterns = []
            for keyword in data["keywords"]:
                # 단어 경계를 사용하여 정확한 매칭
                pattern = re.compile(
                    r'\b' + re.escape(keyword) + r'\b',
                    re.IGNORECASE
                )
                patterns.append(pattern)
            self._compiled_patterns[section] = patterns

    def classify(self, input_data: SectionInput) -> SectionOutput:
        """텍스트를 섹션으로 분류.

        Args:
            input_data: 분류할 입력 데이터

        Returns:
            섹션 분류 결과
        """
        if not input_data.text or not input_data.text.strip():
            return SectionOutput(
                section="other",
                tier=2,
                confidence=0.0,
                evidence=[]
            )

        # 키워드 기반 점수 계산
        scores = self._calculate_keyword_scores(input_data.text)

        # 위치 기반 보너스 적용
        if input_data.source_position is not None:
            position_bonus = self._get_position_bonus(input_data.source_position)
            for section, bonus in position_bonus.items():
                if section in scores:
                    scores[section] = scores[section] * (1 - self.position_weight) + \
                                     scores[section] * bonus * self.position_weight

        # 점수가 모두 0인 경우
        total_score = sum(scores.values())
        if total_score == 0:
            return SectionOutput(
                section="other",
                tier=2,
                confidence=0.0,
                evidence=[]
            )

        # 최고 점수 섹션 선택
        best_section = max(scores, key=lambda k: scores[k])
        confidence = scores[best_section] / total_score if total_score > 0 else 0.0

        # 신뢰도가 낮으면 "other"
        if confidence < self.min_confidence:
            best_section = "other"
            confidence = 1.0 - confidence  # other에 대한 신뢰도로 변환

        # 근거 키워드 추출
        evidence = self._get_evidence(input_data.text, best_section)

        return SectionOutput(
            section=best_section,
            tier=self.TIER_MAP.get(best_section, 2),
            confidence=round(confidence, 3),
            evidence=evidence
        )

    def _calculate_keyword_scores(self, text: str) -> dict[str, float]:
        """키워드 기반 점수 계산.

        Args:
            text: 분석할 텍스트

        Returns:
            섹션별 점수 딕셔너리
        """
        scores: dict[str, float] = {section: 0.0 for section in self.SECTION_KEYWORDS}
        text_lower = text.lower()

        for section, patterns in self._compiled_patterns.items():
            weight = self.SECTION_KEYWORDS[section]["weight"]
            match_count = 0

            for pattern in patterns:
                matches = pattern.findall(text_lower)
                match_count += len(matches)

            # 매칭 수에 가중치 적용
            scores[section] = match_count * weight

        return scores

    def _get_position_bonus(self, position: float) -> dict[str, float]:
        """위치 기반 보너스 계산.

        Args:
            position: 문서 내 위치 (0.0~1.0)

        Returns:
            섹션별 보너스 딕셔너리
        """
        bonus: dict[str, float] = {}

        for section, (start, end) in self.POSITION_HINTS.items():
            if start <= position <= end:
                # 범위 중앙에 가까울수록 높은 보너스
                center = (start + end) / 2
                distance = abs(position - center)
                max_distance = (end - start) / 2
                bonus[section] = 1.0 - (distance / max_distance) if max_distance > 0 else 1.0
            else:
                # 범위 밖이면 거리에 따른 패널티
                if position < start:
                    distance = start - position
                else:
                    distance = position - end
                bonus[section] = max(0.0, 0.5 - distance)

        return bonus

    def _get_evidence(self, text: str, section: str) -> list[str]:
        """분류 근거가 된 키워드 추출.

        Args:
            text: 분석한 텍스트
            section: 분류된 섹션

        Returns:
            매칭된 키워드 목록
        """
        if section not in self._compiled_patterns:
            return []

        evidence = []
        text_lower = text.lower()

        for pattern in self._compiled_patterns[section]:
            matches = pattern.findall(text_lower)
            evidence.extend(matches)

        # 중복 제거 및 정렬
        return sorted(list(set(evidence)))

    def classify_batch(self, inputs: list[SectionInput]) -> list[SectionOutput]:
        """여러 텍스트를 일괄 분류.

        Args:
            inputs: 입력 데이터 목록

        Returns:
            분류 결과 목록
        """
        return [self.classify(input_data) for input_data in inputs]

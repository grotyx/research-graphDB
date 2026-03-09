"""Stats Parser module for extracting statistical results from text."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StatisticType(Enum):
    """통계 유형."""
    HAZARD_RATIO = "HR"
    ODDS_RATIO = "OR"
    RELATIVE_RISK = "RR"
    RISK_RATIO = "RR"
    MEAN_DIFFERENCE = "MD"
    ABSOLUTE_RISK_REDUCTION = "ARR"
    NUMBER_NEEDED_TO_TREAT = "NNT"
    CORRELATION = "r"
    PERCENTAGE = "percent"
    COUNT = "count"


class EffectDirection(Enum):
    """효과 방향."""
    POSITIVE = "positive"      # 중재가 유리 (HR<1, OR<1 등)
    NEGATIVE = "negative"      # 중재가 불리
    NEUTRAL = "neutral"        # 유의하지 않음
    UNKNOWN = "unknown"


@dataclass
class ConfidenceInterval:
    """신뢰구간."""
    lower: float
    upper: float
    level: float = 0.95        # 95% CI가 기본


@dataclass
class StatisticResult:
    """단일 통계 결과."""
    stat_type: StatisticType
    value: float
    ci: Optional[ConfidenceInterval] = None
    p_value: Optional[float] = None
    outcome: Optional[str] = None         # 관련 결과 변수
    comparison: Optional[str] = None      # 비교 설명
    effect_direction: EffectDirection = EffectDirection.UNKNOWN
    is_significant: Optional[bool] = None  # p < 0.05 여부
    raw_text: str = ""                     # 원본 텍스트


@dataclass
class StatsInput:
    """통계 파싱 입력."""
    text: str
    context: Optional[str] = None


@dataclass
class StatsOutput:
    """통계 파싱 결과."""
    statistics: list[StatisticResult] = field(default_factory=list)
    primary_result: Optional[StatisticResult] = None
    has_significant_results: bool = False
    summary: str = ""


class StatsParser:
    """통계 결과 파서."""

    # Hazard Ratio 패턴
    HR_PATTERNS = [
        # HR 0.86 (95% CI, 0.74-0.99)
        r'(?:a?HR|hazard\s+ratio)\s*[=:]?\s*(\d+\.?\d*)\s*\(?(?:95%?\s*)?CI[,:\s]*(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\)?',
        # HR, 0.86; 95% CI, 0.74-0.99
        r'(?:a?HR)\s*[,=:]\s*(\d+\.?\d*)\s*[;,]\s*(?:95%?\s*)?CI[,:\s]*(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)',
        # HR = 0.86 (without CI)
        r'(?:a?HR|hazard\s+ratio)\s*[=:]\s*(\d+\.?\d*)(?!\s*\()',
    ]

    # Odds Ratio 패턴
    OR_PATTERNS = [
        # OR 2.5 (95% CI: 1.5-4.2)
        r'(?:a?OR|odds\s+ratio)\s*[=:]?\s*(\d+\.?\d*)\s*\(?(?:95%?\s*)?CI[,:\s]*(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\)?',
        # OR = 2.5 (without CI)
        r'(?:a?OR|odds\s+ratio)\s*[=:]\s*(\d+\.?\d*)(?!\s*\()',
    ]

    # Relative Risk 패턴
    RR_PATTERNS = [
        # RR 0.75 (95% CI 0.60-0.95)
        r'(?:RR|relative\s+risk|risk\s+ratio)\s*[=:]?\s*(\d+\.?\d*)\s*\(?(?:95%?\s*)?CI[,:\s]*(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)\)?',
        # RR = 0.75 (without CI)
        r'(?:RR|relative\s+risk|risk\s+ratio)\s*[=:]\s*(\d+\.?\d*)(?!\s*\()',
    ]

    # P-value 패턴
    P_VALUE_PATTERNS = [
        # P = 0.001, p < 0.05, P value = 0.03
        r'[pP]\s*[-=<>]\s*(\d*\.?\d+)',
        r'[pP]\s*value\s*[=<>]\s*(\d*\.?\d+)',
        # P < .001 (without leading zero)
        r'[pP]\s*<\s*\.(\d+)',
        # significance at P
        r'(?:significant|significance)\s+(?:at\s+)?[pP]\s*[<=]\s*(\d*\.?\d+)',
    ]

    # Percentage 패턴
    PERCENTAGE_PATTERNS = [
        # 15%, 15.5%
        r'(\d+\.?\d*)\s*%',
        # reduced/increased by X%
        r'(?:reduced|increased|improved|decreased)\s+(?:by\s+)?(\d+\.?\d*)\s*%',
    ]

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
                - significance_threshold: 유의수준 (기본값: 0.05)
                - extract_percentages: 백분율 추출 여부 (기본값: True)
        """
        self.config = config or {}
        self.significance_threshold = self.config.get("significance_threshold", 0.05)
        self.extract_percentages = self.config.get("extract_percentages", True)

        # 정규식 패턴 컴파일
        self._hr_patterns = [re.compile(p, re.IGNORECASE) for p in self.HR_PATTERNS]
        self._or_patterns = [re.compile(p, re.IGNORECASE) for p in self.OR_PATTERNS]
        self._rr_patterns = [re.compile(p, re.IGNORECASE) for p in self.RR_PATTERNS]
        self._p_patterns = [re.compile(p, re.IGNORECASE) for p in self.P_VALUE_PATTERNS]
        self._pct_patterns = [re.compile(p, re.IGNORECASE) for p in self.PERCENTAGE_PATTERNS]

    def parse(self, input_data: StatsInput) -> StatsOutput:
        """텍스트에서 통계 결과 추출.

        Args:
            input_data: 파싱 입력 데이터

        Returns:
            통계 파싱 결과
        """
        if not input_data.text or not input_data.text.strip():
            return StatsOutput(
                statistics=[],
                primary_result=None,
                has_significant_results=False,
                summary="No text to parse"
            )

        text = input_data.text
        statistics: list[StatisticResult] = []

        # 1. 각 통계 유형별 추출
        statistics.extend(self._extract_hazard_ratios(text))
        statistics.extend(self._extract_odds_ratios(text))
        statistics.extend(self._extract_relative_risks(text))

        if self.extract_percentages:
            statistics.extend(self._extract_percentages(text))

        # 2. P-value 연결
        self._link_p_values(text, statistics)

        # 3. 효과 방향 및 유의성 결정
        for stat in statistics:
            stat.effect_direction = self._determine_effect_direction(stat)
            stat.is_significant = self._is_significant(stat)

        # 4. 중복 제거
        statistics = self._remove_duplicates(statistics)

        # 5. 주요 결과 식별
        primary = self._identify_primary_result(statistics, text)

        # 6. 요약 생성
        summary = self._generate_summary(statistics)

        return StatsOutput(
            statistics=statistics,
            primary_result=primary,
            has_significant_results=any(s.is_significant for s in statistics if s.is_significant is not None),
            summary=summary
        )

    def _extract_hazard_ratios(self, text: str) -> list[StatisticResult]:
        """Hazard Ratio 추출.

        Args:
            text: 분석할 텍스트

        Returns:
            HR 통계 결과 목록
        """
        results = []

        for pattern in self._hr_patterns:
            for match in pattern.finditer(text):
                groups = match.groups()

                value = float(groups[0])

                ci = None
                if len(groups) >= 3 and groups[1] and groups[2]:
                    ci = ConfidenceInterval(
                        lower=float(groups[1]),
                        upper=float(groups[2])
                    )

                results.append(StatisticResult(
                    stat_type=StatisticType.HAZARD_RATIO,
                    value=value,
                    ci=ci,
                    raw_text=match.group(0)
                ))

        return results

    def _extract_odds_ratios(self, text: str) -> list[StatisticResult]:
        """Odds Ratio 추출.

        Args:
            text: 분석할 텍스트

        Returns:
            OR 통계 결과 목록
        """
        results = []

        for pattern in self._or_patterns:
            for match in pattern.finditer(text):
                groups = match.groups()

                value = float(groups[0])

                ci = None
                if len(groups) >= 3 and groups[1] and groups[2]:
                    ci = ConfidenceInterval(
                        lower=float(groups[1]),
                        upper=float(groups[2])
                    )

                results.append(StatisticResult(
                    stat_type=StatisticType.ODDS_RATIO,
                    value=value,
                    ci=ci,
                    raw_text=match.group(0)
                ))

        return results

    def _extract_relative_risks(self, text: str) -> list[StatisticResult]:
        """Relative Risk 추출.

        Args:
            text: 분석할 텍스트

        Returns:
            RR 통계 결과 목록
        """
        results = []

        for pattern in self._rr_patterns:
            for match in pattern.finditer(text):
                groups = match.groups()

                value = float(groups[0])

                ci = None
                if len(groups) >= 3 and groups[1] and groups[2]:
                    ci = ConfidenceInterval(
                        lower=float(groups[1]),
                        upper=float(groups[2])
                    )

                results.append(StatisticResult(
                    stat_type=StatisticType.RELATIVE_RISK,
                    value=value,
                    ci=ci,
                    raw_text=match.group(0)
                ))

        return results

    def _extract_percentages(self, text: str) -> list[StatisticResult]:
        """백분율 추출.

        Args:
            text: 분석할 텍스트

        Returns:
            백분율 통계 결과 목록
        """
        results = []
        seen_values = set()

        for pattern in self._pct_patterns:
            for match in pattern.finditer(text):
                value = float(match.group(1))

                # 중복 방지
                if value in seen_values:
                    continue
                seen_values.add(value)

                # 0-100 범위만 유효
                if 0 <= value <= 100:
                    results.append(StatisticResult(
                        stat_type=StatisticType.PERCENTAGE,
                        value=value,
                        raw_text=match.group(0)
                    ))

        return results

    def _link_p_values(self, text: str, statistics: list[StatisticResult]) -> None:
        """P-value를 가장 가까운 통계에 연결.

        Args:
            text: 전체 텍스트
            statistics: 통계 결과 목록 (in-place 수정)
        """
        p_values: list[tuple[int, float]] = []  # (position, p_value)

        for pattern in self._p_patterns:
            for match in pattern.finditer(text):
                p_str = match.group(1)
                # .001 형식 처리
                if not p_str.startswith('0') and '.' not in p_str:
                    p_str = '0.' + p_str

                try:
                    p_value = float(p_str)
                    if 0 < p_value < 1:  # 유효한 p-value 범위
                        p_values.append((match.start(), p_value))
                except ValueError:
                    continue

        # 각 통계에 가장 가까운 p-value 연결
        for stat in statistics:
            if not stat.raw_text:
                continue

            stat_pos = text.find(stat.raw_text)
            if stat_pos == -1:
                continue

            # 가장 가까운 p-value 찾기 (100자 이내)
            closest_p = None
            min_distance = 100

            for p_pos, p_val in p_values:
                distance = abs(p_pos - stat_pos)
                if distance < min_distance:
                    min_distance = distance
                    closest_p = p_val

            if closest_p is not None:
                stat.p_value = closest_p

    def _determine_effect_direction(self, stat: StatisticResult) -> EffectDirection:
        """효과 방향 결정.

        Args:
            stat: 통계 결과

        Returns:
            효과 방향
        """
        # HR, OR, RR의 경우
        if stat.stat_type in [StatisticType.HAZARD_RATIO,
                              StatisticType.ODDS_RATIO,
                              StatisticType.RELATIVE_RISK]:
            if stat.value < 1:
                # CI가 1을 포함하지 않으면 유의미한 보호 효과
                if stat.ci and stat.ci.upper < 1:
                    return EffectDirection.POSITIVE
                elif stat.ci and stat.ci.lower > 1:
                    return EffectDirection.NEGATIVE
                elif stat.ci:
                    return EffectDirection.NEUTRAL  # CI가 1을 포함
                else:
                    return EffectDirection.POSITIVE  # CI 없이 값만으로 판단
            elif stat.value > 1:
                if stat.ci and stat.ci.lower > 1:
                    return EffectDirection.NEGATIVE
                elif stat.ci and stat.ci.upper < 1:
                    return EffectDirection.POSITIVE
                elif stat.ci:
                    return EffectDirection.NEUTRAL
                else:
                    return EffectDirection.NEGATIVE
            else:
                return EffectDirection.NEUTRAL

        return EffectDirection.UNKNOWN

    def _is_significant(self, stat: StatisticResult) -> Optional[bool]:
        """통계적 유의성 판단.

        Args:
            stat: 통계 결과

        Returns:
            유의성 여부 (판단 불가시 None)
        """
        # P-value 기반
        if stat.p_value is not None:
            return stat.p_value < self.significance_threshold

        # CI 기반 (1을 포함하지 않으면 유의)
        if stat.ci:
            if stat.stat_type in [StatisticType.HAZARD_RATIO,
                                  StatisticType.ODDS_RATIO,
                                  StatisticType.RELATIVE_RISK]:
                return not (stat.ci.lower <= 1 <= stat.ci.upper)

        return None

    def _remove_duplicates(self, statistics: list[StatisticResult]) -> list[StatisticResult]:
        """중복 통계 제거.

        Args:
            statistics: 통계 결과 목록

        Returns:
            중복 제거된 목록
        """
        seen = set()
        unique = []

        for stat in statistics:
            key = (stat.stat_type, stat.value, stat.ci.lower if stat.ci else None, stat.ci.upper if stat.ci else None)
            if key not in seen:
                seen.add(key)
                unique.append(stat)

        return unique

    def _identify_primary_result(
        self,
        statistics: list[StatisticResult],
        text: str
    ) -> Optional[StatisticResult]:
        """주요 결과 식별.

        Args:
            statistics: 통계 결과 목록
            text: 원본 텍스트

        Returns:
            주요 결과 (없으면 None)
        """
        if not statistics:
            return None

        # "primary outcome" 근처의 통계 찾기
        primary_pattern = re.compile(r'primary\s+(?:outcome|endpoint|end\s*point)', re.IGNORECASE)
        primary_match = primary_pattern.search(text)

        if primary_match:
            primary_pos = primary_match.start()

            # 가장 가까운 통계 찾기
            closest = None
            min_distance = float('inf')

            for stat in statistics:
                if stat.raw_text:
                    stat_pos = text.find(stat.raw_text)
                    if stat_pos != -1:
                        distance = abs(stat_pos - primary_pos)
                        if distance < min_distance:
                            min_distance = distance
                            closest = stat

            if closest and min_distance < 200:
                return closest

        # Primary를 찾지 못하면 첫 번째 HR/OR/RR 반환
        for stat in statistics:
            if stat.stat_type in [StatisticType.HAZARD_RATIO,
                                  StatisticType.ODDS_RATIO,
                                  StatisticType.RELATIVE_RISK]:
                return stat

        return statistics[0] if statistics else None

    def _generate_summary(self, statistics: list[StatisticResult]) -> str:
        """결과 요약 생성.

        Args:
            statistics: 통계 결과 목록

        Returns:
            요약 문자열
        """
        if not statistics:
            return "No statistical results found."

        significant = [s for s in statistics if s.is_significant]
        effect_measures = [s for s in statistics if s.stat_type in
                         [StatisticType.HAZARD_RATIO,
                          StatisticType.ODDS_RATIO,
                          StatisticType.RELATIVE_RISK]]

        parts = []
        parts.append(f"Found {len(statistics)} statistical results.")

        if effect_measures:
            parts.append(f"{len(effect_measures)} effect measures (HR/OR/RR).")

        if significant:
            parts.append(f"{len(significant)} statistically significant (p<0.05).")

        return " ".join(parts)

    def parse_batch(self, inputs: list[StatsInput]) -> list[StatsOutput]:
        """여러 텍스트를 일괄 파싱.

        Args:
            inputs: 입력 데이터 목록

        Returns:
            파싱 결과 목록
        """
        return [self.parse(input_data) for input_data in inputs]

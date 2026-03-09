"""Direction Determiner for Outcome Interpretation.

척추 수술 결과 변수의 변화 방향을 해석합니다.
"improved", "worsened", "unchanged" 판단을 위한 도메인 지식 기반 모듈.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class OutcomeDirection(Enum):
    """결과 변수 변화 방향."""
    IMPROVED = "improved"
    WORSENED = "worsened"
    UNCHANGED = "unchanged"
    UNKNOWN = "unknown"


# =============================================================================
# Outcome Direction Mapping
# =============================================================================

OUTCOME_DIRECTION_MAP = {
    # Higher is better (점수가 높을수록 좋음)
    "higher_is_better": {
        # 기능 점수
        "fusion_rate", "satisfaction", "success_rate", "rom",
        "sf-36", "sf36", "sf_36", "sf_36_pcs", "sf_36_mcs", "sf36_pcs", "sf36_mcs",
        "eq-5d", "eq5d", "eq_5d", "joa", "mjoa", "srs-22", "srs22", "srs_22",
        "return_to_work", "work_return_rate",

        # Neurological function
        "motor_strength", "sensory_intact", "sphincter_control",

        # 삶의 질
        "quality_of_life", "qol", "patient_satisfaction", "satisfaction_score",
    },

    # Lower is better (점수가 낮을수록 좋음)
    "lower_is_better": {
        # 통증 점수
        "vas", "vas_back", "vas_leg", "vas_arm", "vas_neck",
        "nrs", "nrs_back", "nrs_leg",

        # 장애 지수
        "odi", "ndi", "oswestry", "neck_disability",

        # 합병증 관련
        "complication_rate", "complication", "complications",
        "reoperation_rate", "reoperation", "revision_rate", "revision",
        "infection_rate", "infection",
        "dural_tear", "durotomy",
        "nerve_injury", "nerve_damage",
        "asd", "adjacent_segment_disease",
        "pjk", "proximal_junctional_kyphosis",
        "cage_subsidence", "subsidence",

        # 수술 관련 지표
        "blood_loss", "estimated_blood_loss", "ebl",
        "operation_time", "operative_time", "surgery_time",
        "hospital_stay", "length_of_stay", "los",
        "radiation_exposure", "fluoroscopy_time",

        # 척추 변형 (일부)
        "sva", "sagittal_vertical_axis",
        "pt", "pelvic_tilt",
        "pi-ll", "pi_ll_mismatch", "piminus_ll",
    },

    # Context dependent (맥락에 따라 다름)
    "context_dependent": {
        # 각도 측정 (목표값에 따라 다름)
        "lordosis", "lumbar_lordosis", "cervical_lordosis",
        "cobb_angle", "cobb", "scoliosis_angle",
        "kyphosis", "thoracic_kyphosis",

        # 높이 측정
        "disc_height", "foraminal_height", "spinal_canal_diameter",

        # 정렬 파라미터
        "sagittal_balance", "coronal_balance",
        "pelvic_incidence", "pi",
        "sacral_slope", "ss",
    },
}


# 정규화된 이름 매핑 (대소문자, 공백, 특수문자 무시)
def _normalize_outcome_name(name: str) -> str:
    """결과 변수 이름을 정규화.

    Examples:
        "VAS Back Pain" -> "vas_back"
        "Oswestry Disability Index (ODI)" -> "odi"
        "SF-36" -> "sf36"
    """
    # 소문자 변환
    normalized = name.lower()

    # 괄호 안 내용 추출 (약어 우선)
    paren_match = re.search(r'\(([^)]+)\)', normalized)
    if paren_match:
        abbr = paren_match.group(1).strip()
        # 약어가 있으면 약어 사용
        if len(abbr) <= 6:  # 약어는 보통 짧음
            normalized = abbr

    # 특수문자 제거/변환
    normalized = normalized.replace('-', '_')
    normalized = normalized.replace(' ', '_')
    normalized = re.sub(r'[^a-z0-9_]', '', normalized)

    # 중복 언더스코어 제거
    normalized = re.sub(r'_+', '_', normalized)
    normalized = normalized.strip('_')

    return normalized


def _is_higher_better(outcome_name: str) -> Optional[bool]:
    """결과 변수가 높을수록 좋은지 판단.

    Args:
        outcome_name: 결과 변수 이름 (정규화 전)

    Returns:
        True: 높을수록 좋음
        False: 낮을수록 좋음
        None: 맥락 의존적이거나 알 수 없음
    """
    normalized = _normalize_outcome_name(outcome_name)

    # 각 카테고리에서 매칭 확인
    if normalized in OUTCOME_DIRECTION_MAP["higher_is_better"]:
        return True

    if normalized in OUTCOME_DIRECTION_MAP["lower_is_better"]:
        return False

    if normalized in OUTCOME_DIRECTION_MAP["context_dependent"]:
        return None

    # 패턴 매칭 (예: "vas_", "odi_", 등으로 시작)
    for pattern in ["vas", "nrs", "odi", "ndi"]:
        if normalized.startswith(pattern):
            return False  # 통증/장애 지수는 낮을수록 좋음

    for pattern in ["sf36", "eq5d", "joa", "mjoa"]:
        if pattern in normalized:
            return True  # 기능 점수는 높을수록 좋음

    for pattern in ["complication", "infection", "blood_loss", "operation_time"]:
        if pattern in normalized:
            return False  # 부작용은 낮을수록 좋음

    # 알 수 없음
    return None


# =============================================================================
# Comparison Result
# =============================================================================

@dataclass
class ComparisonResult:
    """비교 결과 (Intervention vs Control)."""
    direction: OutcomeDirection
    difference: float  # intervention - control
    percent_change: float  # (difference / control) * 100
    favors: str  # "intervention" | "control" | "neither"
    confidence: float  # 0.0 - 1.0
    explanation: str = ""  # 판단 근거


# =============================================================================
# Direction Determiner
# =============================================================================

class DirectionDeterminer:
    """결과 변수의 변화 방향을 판단하는 클래스."""

    def __init__(self, unchanged_threshold: float = 0.05):
        """초기화.

        Args:
            unchanged_threshold: 변화 없음으로 간주할 임계값 (5% 기본)
        """
        self.unchanged_threshold = unchanged_threshold

    def determine_direction(
        self,
        outcome_name: str,
        baseline_value: float,
        final_value: float,
        outcome_type: Optional[str] = None,
    ) -> OutcomeDirection:
        """기저값과 최종값을 비교하여 방향 판단.

        Args:
            outcome_name: 결과 변수 이름
            baseline_value: 기저값 (치료 전)
            final_value: 최종값 (치료 후)
            outcome_type: 결과 변수 타입 (higher_is_better, lower_is_better)

        Returns:
            결과 방향

        Examples:
            >>> det = DirectionDeterminer()
            >>> det.determine_direction("VAS", 7.5, 3.2)
            OutcomeDirection.IMPROVED

            >>> det.determine_direction("JOA", 8.0, 14.0)
            OutcomeDirection.IMPROVED

            >>> det.determine_direction("Lordosis", 30.0, 35.0)
            OutcomeDirection.UNKNOWN  # context dependent
        """
        # 값 검증
        if baseline_value == 0:
            logger.warning(f"Baseline value is 0 for {outcome_name}, cannot determine percent change")
            return OutcomeDirection.UNKNOWN

        # 변화율 계산
        change = final_value - baseline_value
        percent_change = abs(change / baseline_value)

        # 변화가 임계값 이하 → UNCHANGED
        if percent_change < self.unchanged_threshold:
            return OutcomeDirection.UNCHANGED

        # 방향 판단 로직 결정
        higher_is_better = None

        if outcome_type:
            # 명시적으로 타입이 주어진 경우
            if outcome_type == "higher_is_better":
                higher_is_better = True
            elif outcome_type == "lower_is_better":
                higher_is_better = False
        else:
            # 이름 기반 추론
            higher_is_better = _is_higher_better(outcome_name)

        # 알 수 없는 경우
        if higher_is_better is None:
            logger.debug(f"Cannot determine direction for {outcome_name} (context-dependent)")
            return OutcomeDirection.UNKNOWN

        # 방향 판단
        if higher_is_better:
            # 높을수록 좋음 → 증가하면 improved
            return OutcomeDirection.IMPROVED if change > 0 else OutcomeDirection.WORSENED
        else:
            # 낮을수록 좋음 → 감소하면 improved
            return OutcomeDirection.IMPROVED if change < 0 else OutcomeDirection.WORSENED

    def is_higher_better(self, outcome_name: str) -> Optional[bool]:
        """결과 변수가 높을수록 좋은지 판단.

        Public interface for _is_higher_better.

        Args:
            outcome_name: 결과 변수 이름

        Returns:
            True: 높을수록 좋음
            False: 낮을수록 좋음
            None: 맥락 의존적이거나 알 수 없음
        """
        return _is_higher_better(outcome_name)

    def interpret_comparison(
        self,
        outcome_name: str,
        intervention_value: float,
        control_value: float,
        outcome_type: Optional[str] = None,
    ) -> ComparisonResult:
        """Intervention vs Control 비교.

        Args:
            outcome_name: 결과 변수 이름
            intervention_value: Intervention 그룹 값
            control_value: Control 그룹 값
            outcome_type: 결과 변수 타입

        Returns:
            비교 결과

        Examples:
            >>> det = DirectionDeterminer()
            >>> result = det.interpret_comparison("VAS", 3.2, 5.1)
            >>> result.direction
            OutcomeDirection.IMPROVED
            >>> result.favors
            'intervention'
        """
        # 차이 계산
        difference = intervention_value - control_value

        # Control이 0이면 퍼센트 계산 불가
        if control_value == 0:
            percent_change = 0.0
            confidence = 0.5
            logger.warning(f"Control value is 0 for {outcome_name}, cannot compute percent change")
        else:
            percent_change = (difference / control_value) * 100

            # 신뢰도: 차이가 클수록 높음 (10% 이상 차이 = 높은 신뢰도)
            confidence = min(abs(percent_change) / 10.0, 1.0)

        # 변화 없음 판단
        if abs(percent_change) < self.unchanged_threshold * 100:
            return ComparisonResult(
                direction=OutcomeDirection.UNCHANGED,
                difference=difference,
                percent_change=percent_change,
                favors="neither",
                confidence=confidence,
                explanation=f"Difference is within threshold ({self.unchanged_threshold*100:.1f}%)"
            )

        # 방향 판단
        higher_is_better = None

        if outcome_type:
            if outcome_type == "higher_is_better":
                higher_is_better = True
            elif outcome_type == "lower_is_better":
                higher_is_better = False
        else:
            higher_is_better = _is_higher_better(outcome_name)

        # 알 수 없는 경우
        if higher_is_better is None:
            return ComparisonResult(
                direction=OutcomeDirection.UNKNOWN,
                difference=difference,
                percent_change=percent_change,
                favors="unknown",
                confidence=0.0,
                explanation=f"{outcome_name} is context-dependent"
            )

        # 방향 및 favors 판단
        if higher_is_better:
            # 높을수록 좋음
            if intervention_value > control_value:
                direction = OutcomeDirection.IMPROVED
                favors = "intervention"
                explanation = f"{outcome_name} higher in intervention (better)"
            else:
                direction = OutcomeDirection.WORSENED
                favors = "control"
                explanation = f"{outcome_name} lower in intervention (worse)"
        else:
            # 낮을수록 좋음
            if intervention_value < control_value:
                direction = OutcomeDirection.IMPROVED
                favors = "intervention"
                explanation = f"{outcome_name} lower in intervention (better)"
            else:
                direction = OutcomeDirection.WORSENED
                favors = "control"
                explanation = f"{outcome_name} higher in intervention (worse)"

        return ComparisonResult(
            direction=direction,
            difference=difference,
            percent_change=percent_change,
            favors=favors,
            confidence=confidence,
            explanation=explanation
        )

    def batch_interpret_comparisons(
        self,
        comparisons: list[tuple[str, float, float, Optional[str]]],
    ) -> list[ComparisonResult]:
        """여러 결과 변수를 동시에 비교.

        Args:
            comparisons: [(outcome_name, intervention_value, control_value, outcome_type), ...]

        Returns:
            비교 결과 리스트
        """
        results = []
        for outcome_name, intervention_value, control_value, outcome_type in comparisons:
            result = self.interpret_comparison(
                outcome_name, intervention_value, control_value, outcome_type
            )
            results.append(result)
        return results

    def explain_outcome_type(self, outcome_name: str) -> str:
        """결과 변수 타입 설명.

        Args:
            outcome_name: 결과 변수 이름

        Returns:
            설명 텍스트
        """
        higher_is_better = _is_higher_better(outcome_name)
        normalized = _normalize_outcome_name(outcome_name)

        if higher_is_better is True:
            return f"{outcome_name} ({normalized}): Higher values indicate better outcomes"
        elif higher_is_better is False:
            return f"{outcome_name} ({normalized}): Lower values indicate better outcomes"
        else:
            return f"{outcome_name} ({normalized}): Context-dependent interpretation"


# =============================================================================
# Helper Functions
# =============================================================================

def parse_numeric_value(value_str: str) -> Optional[float]:
    """문자열에서 숫자 추출.

    Examples:
        "3.2±1.1" -> 3.2
        "85.2%" -> 85.2
        "12 points" -> 12.0
    """
    if not value_str:
        return None

    # 숫자 추출 (첫 번째 숫자만)
    match = re.search(r'[-+]?\d*\.?\d+', value_str)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None

    return None


def interpret_from_extracted_outcome(
    outcome: "ExtractedOutcome",  # Type hint for ExtractedOutcome from gemini_vision_processor
    determiner: Optional[DirectionDeterminer] = None,
) -> ComparisonResult:
    """ExtractedOutcome 객체에서 방향 판단.

    Args:
        outcome: gemini_vision_processor의 ExtractedOutcome 객체
        determiner: DirectionDeterminer 인스턴스 (없으면 생성)

    Returns:
        비교 결과
    """
    if determiner is None:
        determiner = DirectionDeterminer()

    # 값 파싱
    intervention_val = parse_numeric_value(outcome.value_intervention)
    control_val = parse_numeric_value(outcome.value_control)

    if intervention_val is None or control_val is None:
        logger.warning(
            f"Cannot parse values for {outcome.name}: "
            f"intervention={outcome.value_intervention}, control={outcome.value_control}"
        )
        return ComparisonResult(
            direction=OutcomeDirection.UNKNOWN,
            difference=0.0,
            percent_change=0.0,
            favors="unknown",
            confidence=0.0,
            explanation="Could not parse numeric values"
        )

    # 비교 수행
    result = determiner.interpret_comparison(
        outcome_name=outcome.name,
        intervention_value=intervention_val,
        control_value=control_val,
        outcome_type=None,  # 이름 기반 추론
    )

    return result


# =============================================================================
# Main (테스트용)
# =============================================================================

def main():
    """테스트 및 예제."""
    import sys

    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    determiner = DirectionDeterminer()

    print("=" * 80)
    print("Direction Determiner Test")
    print("=" * 80)

    # 테스트 케이스
    test_cases = [
        # (outcome_name, intervention, control, expected_direction, expected_favors)
        ("VAS", 3.2, 5.1, OutcomeDirection.IMPROVED, "intervention"),
        ("VAS Back Pain", 2.8, 6.5, OutcomeDirection.IMPROVED, "intervention"),
        ("ODI", 18.5, 35.2, OutcomeDirection.IMPROVED, "intervention"),
        ("JOA", 14.2, 9.8, OutcomeDirection.IMPROVED, "intervention"),
        ("Fusion Rate", 92.5, 85.3, OutcomeDirection.IMPROVED, "intervention"),
        ("Complication Rate", 8.2, 5.1, OutcomeDirection.WORSENED, "control"),
        ("Operation Time", 120.5, 95.3, OutcomeDirection.WORSENED, "control"),
        ("SF-36 PCS", 42.3, 38.1, OutcomeDirection.IMPROVED, "intervention"),
        ("Lordosis", 35.0, 40.0, OutcomeDirection.UNKNOWN, "unknown"),  # context-dependent
    ]

    print("\n1. Comparison Tests:")
    print("-" * 80)

    correct = 0
    for outcome_name, interv_val, ctrl_val, expected_dir, expected_fav in test_cases:
        result = determiner.interpret_comparison(outcome_name, interv_val, ctrl_val)

        is_correct = (result.direction == expected_dir and result.favors == expected_fav)
        correct += int(is_correct)

        status = "✓" if is_correct else "✗"
        print(f"{status} {outcome_name:20s} | I={interv_val:6.1f} C={ctrl_val:6.1f} | "
              f"{result.direction.value:10s} favors {result.favors:12s} | "
              f"Δ={result.difference:+6.1f} ({result.percent_change:+6.1f}%)")

    print(f"\nAccuracy: {correct}/{len(test_cases)} ({100*correct/len(test_cases):.1f}%)")

    # 이름 정규화 테스트
    print("\n2. Name Normalization Tests:")
    print("-" * 80)

    test_names = [
        "VAS Back Pain",
        "Oswestry Disability Index (ODI)",
        "SF-36 PCS",
        "Japanese Orthopaedic Association (JOA) Score",
        "PI-LL Mismatch",
    ]

    for name in test_names:
        normalized = _normalize_outcome_name(name)
        higher_better = determiner.is_higher_better(name)
        direction_type = "higher↑" if higher_better is True else "lower↓" if higher_better is False else "context"
        print(f"{name:50s} → {normalized:20s} [{direction_type}]")

    # Baseline vs Final 테스트
    print("\n3. Baseline vs Final Tests:")
    print("-" * 80)

    baseline_tests = [
        ("VAS", 7.5, 3.2),
        ("ODI", 45.3, 18.7),
        ("JOA", 8.2, 13.8),
        ("Fusion Rate", 0.0, 92.5),  # 수술 후에만 측정
    ]

    for outcome_name, baseline, final in baseline_tests:
        if baseline == 0:
            print(f"{outcome_name:20s} | Baseline=N/A Final={final:6.1f} | Skipped (no baseline)")
            continue

        direction = determiner.determine_direction(outcome_name, baseline, final)
        change = final - baseline
        print(f"{outcome_name:20s} | Baseline={baseline:6.1f} Final={final:6.1f} | "
              f"{direction.value:10s} (Δ={change:+6.1f})")

    print("\n" + "=" * 80)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

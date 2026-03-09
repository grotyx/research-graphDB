"""ExtractedOutcome Dataclass (v3.2 - Archived).

Archived on: 2025-12-18
Reason: Replaced by simplified v7.0 processing pipeline

This file contains the complex outcome extraction schema
used in v6. It supported structured effect measures per outcome.

v7.0 simplifies this to basic outcome values from analysis tools.
"""

from dataclasses import dataclass
from typing import Optional
from .effect_measure import EffectMeasure


@dataclass
class ExtractedOutcome:
    """추출된 결과 변수 (v3.2 다양한 연구 유형 지원).

    v3.2 변경사항:
    - effect_measure: 다양한 효과 측정치 지원 (기존 effect_size 대체)
    - effect_size 하위호환성 유지

    Fields:
    - name: 결과 변수 이름 (VAS, ODI, JOA, Fusion Rate, etc.)
    - category: 결과 유형 (pain, function, radiologic, complication, etc.)
    - value_intervention: 중재군 값
    - value_control: 대조군 값
    - value_difference: 차이값
    - p_value: 통계적 유의성
    - confidence_interval: 신뢰구간
    - effect_size: 효과 크기 (문자열, 하위호환)
    - effect_measure: 구조화된 효과 측정치 (v3.2)
    - timepoint: 측정 시점
    - is_significant: 통계적 유의성 여부
    - direction: 변화 방향 (improved, worsened, unchanged)

    Example:
        outcome = ExtractedOutcome(
            name="VAS",
            category="pain",
            value_intervention="2.1 ± 0.8",
            value_control="3.5 ± 1.2",
            value_difference="-1.4",
            p_value="0.001",
            confidence_interval="95% CI: -2.1 to -0.7",
            effect_measure=EffectMeasure(
                measure_type="MD",
                value="-1.4",
                ci_lower="-2.1",
                ci_upper="-0.7",
                label="MD -1.4 (95% CI: -2.1 to -0.7)"
            ),
            timepoint="1yr",
            is_significant=True,
            direction="improved"
        )
    """
    name: str  # VAS, ODI, JOA, Fusion Rate, etc.
    category: str = ""  # pain, function, radiologic, complication, satisfaction, quality_of_life, survival, event_rate

    # 결과값
    value_intervention: str = ""
    value_control: str = ""
    value_difference: str = ""

    # 통계 (v3.2 확장)
    p_value: str = ""
    confidence_interval: str = ""
    effect_size: str = ""  # 하위호환성 (e.g., "Cohen's d = 0.8")
    effect_measure: Optional[EffectMeasure] = None  # 구조화된 효과 측정치 (v3.2)

    # 시점
    timepoint: str = ""  # preop, postop, 1mo, 3mo, 6mo, 1yr, 2yr, final

    # 해석
    is_significant: bool = False
    direction: str = ""  # improved, worsened, unchanged


# Category definitions
OUTCOME_CATEGORIES = {
    "pain": ["VAS", "NRS", "back pain VAS", "leg pain VAS", "arm pain VAS", "neck pain VAS"],
    "function": ["ODI", "NDI", "JOA", "mJOA", "EQ-5D", "SF-36", "MacNab"],
    "radiologic": ["fusion rate", "Cobb angle", "lordosis", "SVA", "disc height", "canal diameter"],
    "complication": ["dural tear", "infection", "nerve injury", "reoperation", "pseudarthrosis"],
    "satisfaction": ["patient satisfaction", "return to work", "MacNab criteria"],
    "quality_of_life": ["EQ-5D", "SF-36", "SF-12", "WHOQOL"],
    "survival": ["overall survival", "progression-free survival", "disease-free survival"],
    "event_rate": ["recurrence rate", "revision rate", "mortality rate"],
}


def get_outcome_category(outcome_name: str) -> str:
    """결과 변수 이름에서 카테고리를 추론합니다."""
    outcome_lower = outcome_name.lower()
    for category, names in OUTCOME_CATEGORIES.items():
        for name in names:
            if name.lower() in outcome_lower:
                return category
    return "other"


# Parsing helpers (from v6)
def parse_outcome_v6(outcome_dict: dict) -> ExtractedOutcome:
    """v6 결과 딕셔너리를 ExtractedOutcome으로 변환."""
    # effect_measure 파싱
    outcome_effect_measure = None
    em_dict = outcome_dict.get("effect_measure")
    if em_dict and isinstance(em_dict, dict):
        outcome_effect_measure = EffectMeasure(
            measure_type=str(em_dict.get("measure_type", "")),
            value=str(em_dict.get("value", "")),
            ci_lower=str(em_dict.get("ci_lower", "")),
            ci_upper=str(em_dict.get("ci_upper", "")),
            label=str(em_dict.get("label", "")),
        )

    return ExtractedOutcome(
        name=outcome_dict.get("name", ""),
        category=outcome_dict.get("category", ""),
        value_intervention=str(outcome_dict.get("value_intervention", "")),
        value_control=str(outcome_dict.get("value_control", "")),
        value_difference=str(outcome_dict.get("value_difference", "")),
        p_value=str(outcome_dict.get("p_value", "")),
        confidence_interval=str(outcome_dict.get("confidence_interval", "")),
        effect_size=str(outcome_dict.get("effect_size", "")),
        effect_measure=outcome_effect_measure,
        timepoint=outcome_dict.get("timepoint", ""),
        is_significant=bool(outcome_dict.get("is_significant", False)),
        direction=outcome_dict.get("direction", ""),
    )


# Example Usage
if __name__ == "__main__":
    # Example 1: Pain outcome (VAS)
    vas_outcome = ExtractedOutcome(
        name="VAS",
        category="pain",
        value_intervention="2.1 ± 0.8",
        value_control="3.5 ± 1.2",
        value_difference="-1.4",
        p_value="0.001",
        confidence_interval="95% CI: -2.1 to -0.7",
        effect_measure=EffectMeasure(
            measure_type="MD",
            value="-1.4",
            ci_lower="-2.1",
            ci_upper="-0.7",
            label="MD -1.4 (95% CI: -2.1 to -0.7)"
        ),
        timepoint="1yr",
        is_significant=True,
        direction="improved"
    )
    print(f"VAS: {vas_outcome.effect_measure.label}, {vas_outcome.direction}, p={vas_outcome.p_value}")

    # Example 2: Fusion rate (radiologic)
    fusion_outcome = ExtractedOutcome(
        name="Fusion rate",
        category="radiologic",
        value_intervention="94%",
        value_control="89%",
        value_difference="5%",
        p_value="0.24",
        confidence_interval="95% CI: -3% to 13%",
        effect_measure=EffectMeasure(
            measure_type="RR",
            value="1.06",
            ci_lower="0.97",
            ci_upper="1.15",
            label="RR 1.06 (95% CI: 0.97-1.15)"
        ),
        timepoint="2yr",
        is_significant=False,
        direction="unchanged"
    )
    print(f"Fusion: {fusion_outcome.effect_measure.label}, {fusion_outcome.direction}, p={fusion_outcome.p_value}")

    # Example 3: Complication (dural tear)
    complication_outcome = ExtractedOutcome(
        name="Dural tear",
        category="complication",
        value_intervention="2.5%",
        value_control="4.1%",
        value_difference="-1.6%",
        p_value="0.35",
        confidence_interval="95% CI: -5% to 2%",
        effect_measure=EffectMeasure(
            measure_type="OR",
            value="0.60",
            ci_lower="0.20",
            ci_upper="1.80",
            label="OR 0.60 (95% CI: 0.20-1.80)"
        ),
        timepoint="postop",
        is_significant=False,
        direction="unchanged"
    )
    print(f"Dural tear: {complication_outcome.effect_measure.label}, {complication_outcome.direction}")

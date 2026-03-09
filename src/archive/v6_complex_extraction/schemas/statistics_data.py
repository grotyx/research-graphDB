"""StatisticsData Dataclass (v3.2 - Archived).

Archived on: 2025-12-18
Reason: Replaced by simplified v7.0 processing pipeline

This file contains the complex statistics extraction schema
used in v6. It supported structured effect measures from LLM.

v7.0 simplifies this to basic p-values from analysis tools.
"""

from dataclasses import dataclass
from typing import Optional
from .effect_measure import EffectMeasure


@dataclass
class StatisticsData:
    """통계 데이터 (v3.2 다양한 연구 유형 지원).

    v3.2 변경사항:
    - effect_measure: 다양한 효과 측정치 지원 (HR, OR, RR, I², NNT 등)
    - 기존 additional 필드 유지 (하위호환성)

    지원 효과 측정치:
    - HR (Hazard Ratio): 생존분석, 코호트 연구
    - OR (Odds Ratio): 케이스-컨트롤, 메타분석
    - RR (Relative Risk): 코호트, RCT
    - MD (Mean Difference): 연속형 결과 비교
    - SMD (Standardized Mean Difference): 메타분석
    - NNT (Number Needed to Treat): 임상적 해석
    - I² (I-squared): 메타분석 이질성
    - Cohen's d: 효과 크기

    Example:
        stats = StatisticsData(
            p_value="0.001",
            is_significant=True,
            effect_measure=EffectMeasure(
                measure_type="HR",
                value="2.35",
                ci_lower="1.42",
                ci_upper="3.89",
                label="HR 2.35 (95% CI: 1.42-3.89)"
            ),
            additional="Median survival: 24 months"
        )
    """
    p_value: str = ""           # 대표 p-value (e.g., "0.001", "<0.001")
    is_significant: bool = False  # p < 0.05 여부
    effect_measure: Optional[EffectMeasure] = None  # 효과 측정치 (v3.2)
    additional: str = ""         # 추가 통계 (e.g., "95% CI: 1.2-3.4")


# Parsing helpers (from v6)
def parse_statistics_v6(stats_dict: dict) -> StatisticsData:
    """v6 통계 딕셔너리를 StatisticsData로 변환."""
    if not stats_dict:
        return StatisticsData()

    effect_measure = None
    em_dict = stats_dict.get("effect_measure")
    if em_dict and isinstance(em_dict, dict):
        effect_measure = EffectMeasure(
            measure_type=str(em_dict.get("measure_type", "")),
            value=str(em_dict.get("value", "")),
            ci_lower=str(em_dict.get("ci_lower", "")),
            ci_upper=str(em_dict.get("ci_upper", "")),
            label=str(em_dict.get("label", "")),
        )

    return StatisticsData(
        p_value=str(stats_dict.get("p_value", "")),
        is_significant=bool(stats_dict.get("is_significant", False)),
        effect_measure=effect_measure,
        additional=str(stats_dict.get("additional", "")),
    )


# Example Usage
if __name__ == "__main__":
    # Example 1: RCT with Mean Difference
    rct_stats = StatisticsData(
        p_value="0.003",
        is_significant=True,
        effect_measure=EffectMeasure(
            measure_type="MD",
            value="-1.4",
            ci_lower="-2.1",
            ci_upper="-0.7",
            label="MD -1.4 (95% CI: -2.1 to -0.7)"
        ),
        additional="Cohen's d = 0.8"
    )
    print(f"RCT Result: {rct_stats.effect_measure.label}, p={rct_stats.p_value}")

    # Example 2: Cohort with Hazard Ratio
    cohort_stats = StatisticsData(
        p_value="0.001",
        is_significant=True,
        effect_measure=EffectMeasure(
            measure_type="HR",
            value="2.35",
            ci_lower="1.42",
            ci_upper="3.89",
            label="HR 2.35 (95% CI: 1.42-3.89)"
        ),
        additional="Median survival: 24 months"
    )
    print(f"Cohort Result: {cohort_stats.effect_measure.label}, p={cohort_stats.p_value}")

    # Example 3: Meta-analysis with SMD and I²
    meta_stats = StatisticsData(
        p_value="<0.001",
        is_significant=True,
        effect_measure=EffectMeasure(
            measure_type="SMD",
            value="-0.45",
            ci_lower="-0.67",
            ci_upper="-0.23",
            label="SMD -0.45 (95% CI: -0.67 to -0.23)"
        ),
        additional="I²=42%, heterogeneity: moderate"
    )
    print(f"Meta-analysis: {meta_stats.effect_measure.label}, {meta_stats.additional}")

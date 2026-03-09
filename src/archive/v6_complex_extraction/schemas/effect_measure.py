"""Effect Measure Dataclass (v3.2 - Archived).

Archived on: 2025-12-18
Reason: Replaced by simplified v7.0 processing pipeline

This file contains the complex effect measure extraction schema
used in v6. It supported diverse study types with specific effect
measures (HR, OR, RR, MD, SMD, NNT, I², Cohen's d, etc.).

v7.0 simplifies this to basic p-values and directions only.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EffectMeasure:
    """효과 측정치 (다양한 연구 유형 지원).

    v3.2 추가: HR, OR, RR, MD, SMD, NNT, I², Cohen's d 등 지원.

    Supported Measures:
    - HR (Hazard Ratio): 생존분석, 코호트 연구
    - OR (Odds Ratio): 케이스-컨트롤, 메타분석
    - RR (Relative Risk): 코호트, RCT
    - MD (Mean Difference): 연속형 결과 비교
    - SMD (Standardized Mean Difference): 메타분석
    - NNT (Number Needed to Treat): 임상적 해석
    - I² (I-squared): 메타분석 이질성
    - Cohen's d: 효과 크기
    - r (correlation coefficient): 상관분석
    - eta2 (eta-squared): 분산분석 효과 크기
    """
    measure_type: str = ""  # HR, OR, RR, MD, SMD, NNT, I2, Cohen_d, r, eta2, other
    value: str = ""         # 수치값 (e.g., "2.35", "0.82")
    ci_lower: str = ""      # 95% CI 하한 (e.g., "1.42")
    ci_upper: str = ""      # 95% CI 상한 (e.g., "3.89")
    label: str = ""         # 전체 표기 (e.g., "HR 2.35 (95% CI: 1.42-3.89)")


# Study Type to Recommended Effect Measures Mapping
STUDY_TYPE_MEASURES = {
    "meta-analysis": ["SMD", "MD", "OR", "RR", "HR", "I2"],
    "systematic-review": ["SMD", "MD", "OR", "RR", "HR"],
    "RCT": ["MD", "SMD", "Cohen_d", "RR", "NNT"],
    "prospective-cohort": ["HR", "RR", "OR", "NNT"],
    "retrospective-cohort": ["HR", "OR", "RR"],
    "case-control": ["OR"],
    "cross-sectional": ["OR", "PR"],  # PR = Prevalence Ratio
    "case-series": ["descriptive"],
    "case-report": ["descriptive"],
    "expert-opinion": ["descriptive"],
    "unknown": ["MD", "OR", "HR", "RR"],  # 일반적인 것들
}


def get_recommended_measures(study_type: str) -> list[str]:
    """연구 유형에 권장되는 효과 측정치를 반환합니다."""
    return STUDY_TYPE_MEASURES.get(study_type, STUDY_TYPE_MEASURES["unknown"])


# Example Usage
if __name__ == "__main__":
    # Hazard Ratio example
    hr = EffectMeasure(
        measure_type="HR",
        value="2.35",
        ci_lower="1.42",
        ci_upper="3.89",
        label="HR 2.35 (95% CI: 1.42-3.89)"
    )
    print(f"Effect measure: {hr.label}")

    # Meta-analysis example with I²
    i2 = EffectMeasure(
        measure_type="I2",
        value="42",
        ci_lower="",
        ci_upper="",
        label="I²=42%"
    )
    print(f"Heterogeneity: {i2.label}")

    # Get recommended measures
    print(f"RCT measures: {get_recommended_measures('RCT')}")
    print(f"Cohort measures: {get_recommended_measures('prospective-cohort')}")

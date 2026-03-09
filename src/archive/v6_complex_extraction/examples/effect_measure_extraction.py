"""Effect Measure Extraction Examples (v6 - Archived).

Archived on: 2025-12-18

This file shows how complex effect measures were extracted from LLM
in v6. It demonstrates the parsing and usage of EffectMeasure dataclass.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "schemas"))

from effect_measure import EffectMeasure, get_recommended_measures
from statistics_data import StatisticsData, parse_statistics_v6
from extracted_outcome import ExtractedOutcome, parse_outcome_v6, get_outcome_category


def example_hazard_ratio():
    """Example: Hazard Ratio from survival analysis."""
    print("=== Hazard Ratio (Cohort Study) ===")

    # Simulated LLM extraction result
    llm_result = {
        "p_value": "0.001",
        "is_significant": True,
        "effect_measure": {
            "measure_type": "HR",
            "value": "2.35",
            "ci_lower": "1.42",
            "ci_upper": "3.89",
            "label": "HR 2.35 (95% CI: 1.42-3.89)"
        },
        "additional": "Median survival: 24 months"
    }

    # Parse into dataclass
    stats = parse_statistics_v6(llm_result)

    print(f"P-value: {stats.p_value}")
    print(f"Significant: {stats.is_significant}")
    print(f"Effect Measure: {stats.effect_measure.label}")
    print(f"Additional Info: {stats.additional}")
    print()


def example_odds_ratio():
    """Example: Odds Ratio from case-control study."""
    print("=== Odds Ratio (Case-Control Study) ===")

    llm_result = {
        "p_value": "<0.001",
        "is_significant": True,
        "effect_measure": {
            "measure_type": "OR",
            "value": "3.2",
            "ci_lower": "1.8",
            "ci_upper": "5.6",
            "label": "OR 3.2 (95% CI: 1.8-5.6)"
        },
        "additional": "Adjusted for age, BMI, smoking"
    }

    stats = parse_statistics_v6(llm_result)

    print(f"P-value: {stats.p_value}")
    print(f"Significant: {stats.is_significant}")
    print(f"Effect Measure: {stats.effect_measure.label}")
    print(f"Additional Info: {stats.additional}")
    print()


def example_mean_difference():
    """Example: Mean Difference from RCT."""
    print("=== Mean Difference (RCT) ===")

    llm_result = {
        "p_value": "0.003",
        "is_significant": True,
        "effect_measure": {
            "measure_type": "MD",
            "value": "-1.4",
            "ci_lower": "-2.1",
            "ci_upper": "-0.7",
            "label": "MD -1.4 (95% CI: -2.1 to -0.7)"
        },
        "additional": "Cohen's d = 0.8"
    }

    stats = parse_statistics_v6(llm_result)

    print(f"P-value: {stats.p_value}")
    print(f"Significant: {stats.is_significant}")
    print(f"Effect Measure: {stats.effect_measure.label}")
    print(f"Additional Info: {stats.additional}")
    print()


def example_standardized_mean_difference():
    """Example: SMD from meta-analysis."""
    print("=== Standardized Mean Difference (Meta-Analysis) ===")

    llm_result = {
        "p_value": "<0.001",
        "is_significant": True,
        "effect_measure": {
            "measure_type": "SMD",
            "value": "-0.45",
            "ci_lower": "-0.67",
            "ci_upper": "-0.23",
            "label": "SMD -0.45 (95% CI: -0.67 to -0.23)"
        },
        "additional": "I²=42%, heterogeneity: moderate"
    }

    stats = parse_statistics_v6(llm_result)

    print(f"P-value: {stats.p_value}")
    print(f"Significant: {stats.is_significant}")
    print(f"Effect Measure: {stats.effect_measure.label}")
    print(f"Additional Info: {stats.additional}")
    print()


def example_outcome_with_effect_measure():
    """Example: Outcome with embedded effect measure."""
    print("=== Outcome with Effect Measure ===")

    # Simulated LLM extraction for outcome
    outcome_dict = {
        "name": "VAS",
        "category": "pain",
        "value_intervention": "2.1 ± 0.8",
        "value_control": "3.5 ± 1.2",
        "value_difference": "-1.4",
        "p_value": "0.001",
        "confidence_interval": "95% CI: -2.1 to -0.7",
        "effect_size": "Cohen's d = 0.8",
        "effect_measure": {
            "measure_type": "MD",
            "value": "-1.4",
            "ci_lower": "-2.1",
            "ci_upper": "-0.7",
            "label": "MD -1.4 (95% CI: -2.1 to -0.7)"
        },
        "timepoint": "1yr",
        "is_significant": True,
        "direction": "improved"
    }

    outcome = parse_outcome_v6(outcome_dict)

    print(f"Outcome: {outcome.name} ({outcome.category})")
    print(f"Intervention: {outcome.value_intervention}")
    print(f"Control: {outcome.value_control}")
    print(f"Difference: {outcome.value_difference}")
    print(f"Effect Measure: {outcome.effect_measure.label}")
    print(f"P-value: {outcome.p_value}")
    print(f"Direction: {outcome.direction}")
    print(f"Timepoint: {outcome.timepoint}")
    print()


def example_multiple_outcomes():
    """Example: Multiple outcomes from a single paper."""
    print("=== Multiple Outcomes from Paper ===")

    outcomes_data = [
        {
            "name": "VAS",
            "category": "pain",
            "value_intervention": "2.1",
            "value_control": "3.5",
            "p_value": "0.001",
            "effect_measure": {
                "measure_type": "MD",
                "value": "-1.4",
                "label": "MD -1.4"
            },
            "is_significant": True,
            "direction": "improved"
        },
        {
            "name": "ODI",
            "category": "function",
            "value_intervention": "18.2",
            "value_control": "24.8",
            "p_value": "0.003",
            "effect_measure": {
                "measure_type": "MD",
                "value": "-6.6",
                "label": "MD -6.6"
            },
            "is_significant": True,
            "direction": "improved"
        },
        {
            "name": "Fusion rate",
            "category": "radiologic",
            "value_intervention": "94%",
            "value_control": "89%",
            "p_value": "0.24",
            "effect_measure": {
                "measure_type": "RR",
                "value": "1.06",
                "label": "RR 1.06"
            },
            "is_significant": False,
            "direction": "unchanged"
        }
    ]

    for outcome_dict in outcomes_data:
        outcome = parse_outcome_v6(outcome_dict)
        print(f"  {outcome.name}: {outcome.effect_measure.label} (p={outcome.p_value}, {outcome.direction})")

    print()


def example_recommended_measures_by_study_type():
    """Example: Getting recommended measures for each study type."""
    print("=== Recommended Measures by Study Type ===")

    study_types = [
        "meta-analysis",
        "RCT",
        "prospective-cohort",
        "case-control",
    ]

    for study_type in study_types:
        measures = get_recommended_measures(study_type)
        print(f"{study_type:20} → {', '.join(measures)}")

    print()


if __name__ == "__main__":
    print("Effect Measure Extraction Examples (v6 Archive)\n")
    print("=" * 60)
    print()

    example_hazard_ratio()
    example_odds_ratio()
    example_mean_difference()
    example_standardized_mean_difference()
    example_outcome_with_effect_measure()
    example_multiple_outcomes()
    example_recommended_measures_by_study_type()

    print("=" * 60)
    print("\nNote: In v7.0, effect measures come from statistical analysis tools,")
    print("not from complex LLM extraction. The simplified approach focuses on")
    print("basic p-values and outcome directions only.")

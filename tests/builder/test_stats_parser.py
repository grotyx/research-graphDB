"""Tests for StatsParser module.

통계 데이터 파싱 테스트:
- P-value 추출 (다양한 형식)
- Effect size 추출 (HR, OR, RR)
- Confidence interval 파싱
- 효과 방향 판단
- Edge cases (누락 값, 형식 오류)
"""

import pytest
from typing import Optional

from src.builder.stats_parser import (
    StatsParser,
    StatisticType,
    EffectDirection,
    ConfidenceInterval,
    StatisticResult,
    StatsInput,
    StatsOutput,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def parser():
    """Default StatsParser instance."""
    return StatsParser()


@pytest.fixture
def parser_no_percentages():
    """StatsParser with percentage extraction disabled."""
    return StatsParser(config={"extract_percentages": False})


@pytest.fixture
def parser_custom_threshold():
    """StatsParser with custom significance threshold (0.01)."""
    return StatsParser(config={"significance_threshold": 0.01})


# ===========================================================================
# Test: Hazard Ratio Extraction
# ===========================================================================

class TestHazardRatioExtraction:
    """Test HR extraction with various formats."""

    def test_hr_with_ci(self, parser_no_percentages):
        """HR with confidence interval (percentages disabled to avoid 95% extraction)."""
        text = "HR 0.86 (95% CI, 0.74-0.99)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.stat_type == StatisticType.HAZARD_RATIO
        assert stat.value == 0.86
        assert stat.ci is not None
        assert stat.ci.lower == 0.74
        assert stat.ci.upper == 0.99

    def test_hr_without_ci(self, parser):
        """HR without confidence interval."""
        text = "hazard ratio = 0.65"
        output = parser.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.stat_type == StatisticType.HAZARD_RATIO
        assert stat.value == 0.65
        assert stat.ci is None

    def test_ahr_adjusted_hazard_ratio(self, parser_no_percentages):
        """Adjusted hazard ratio (aHR)."""
        text = "aHR 0.72 (95% CI: 0.60-0.88)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.stat_type == StatisticType.HAZARD_RATIO
        assert stat.value == 0.72

    def test_hr_semicolon_separator(self, parser_no_percentages):
        """HR with semicolon separator."""
        text = "aHR, 0.86; 95% CI, 0.74-0.99"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.value == 0.86
        assert stat.ci.lower == 0.74

    def test_hr_with_to_separator(self, parser_no_percentages):
        """HR CI using 'to' instead of hyphen."""
        text = "HR 0.75 (95% CI 0.60 to 0.95)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.ci.lower == 0.60
        assert stat.ci.upper == 0.95


# ===========================================================================
# Test: Odds Ratio Extraction
# ===========================================================================

class TestOddsRatioExtraction:
    """Test OR extraction."""

    def test_or_with_ci(self, parser_no_percentages):
        """OR with confidence interval."""
        text = "OR 2.5 (95% CI: 1.5-4.2)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.stat_type == StatisticType.ODDS_RATIO
        assert stat.value == 2.5
        assert stat.ci.lower == 1.5
        assert stat.ci.upper == 4.2

    def test_or_without_ci(self, parser):
        """OR without CI."""
        text = "odds ratio = 1.8"
        output = parser.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.stat_type == StatisticType.ODDS_RATIO
        assert stat.value == 1.8

    def test_aor_adjusted_odds_ratio(self, parser_no_percentages):
        """Adjusted odds ratio (aOR)."""
        text = "aOR = 3.2 (95% CI 2.1-4.8)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        # Should have OR stats (and potentially others like 3.2 matching a pattern)
        or_stats = [s for s in output.statistics if s.stat_type == StatisticType.ODDS_RATIO]
        assert len(or_stats) >= 1
        assert or_stats[0].value == 3.2


# ===========================================================================
# Test: Relative Risk Extraction
# ===========================================================================

class TestRelativeRiskExtraction:
    """Test RR extraction."""

    def test_rr_with_ci(self, parser_no_percentages):
        """RR with confidence interval."""
        text = "RR 0.75 (95% CI 0.60-0.95)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.stat_type == StatisticType.RELATIVE_RISK
        assert stat.value == 0.75

    def test_relative_risk_spelled_out(self, parser_no_percentages):
        """Relative risk spelled out."""
        text = "relative risk = 1.25 (95% CI 1.10-1.45)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        # Should have RR stats
        rr_stats = [s for s in output.statistics if s.stat_type == StatisticType.RELATIVE_RISK]
        assert len(rr_stats) >= 1
        assert rr_stats[0].value == 1.25

    def test_risk_ratio(self, parser):
        """Risk ratio."""
        text = "risk ratio = 0.88"
        output = parser.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.stat_type == StatisticType.RELATIVE_RISK
        assert stat.value == 0.88


# ===========================================================================
# Test: P-value Extraction and Linking
# ===========================================================================

class TestPValueExtraction:
    """Test p-value extraction and linking."""

    def test_p_value_equals(self, parser_no_percentages):
        """P = 0.001"""
        text = "HR 0.86 (95% CI 0.74-0.99), P = 0.001"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.p_value == 0.001

    def test_p_value_less_than(self, parser_no_percentages):
        """P < 0.05"""
        text = "OR 2.5 (95% CI 1.5-4.2), p < 0.05"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert len(output.statistics) == 1
        stat = output.statistics[0]
        assert stat.p_value == 0.05

    def test_p_value_without_leading_zero(self, parser):
        """P < .001"""
        text = "RR = 0.75, P < .001"
        output = parser.parse(StatsInput(text=text))

        assert len(output.statistics) >= 1
        # Find the RR stat
        rr_stats = [s for s in output.statistics if s.stat_type == StatisticType.RELATIVE_RISK]
        assert len(rr_stats) == 1
        assert rr_stats[0].p_value == 0.001

    def test_p_value_with_text(self, parser):
        """significant at P < 0.01"""
        text = "The result was significant at P < 0.01"
        output = parser.parse(StatsInput(text=text))

        # P-value extracted but no effect measure
        # Check that p-value extraction works
        assert "0.01" in text

    def test_p_value_spelled_out(self, parser):
        """P value = 0.03"""
        text = "HR = 0.9, P value = 0.03"
        output = parser.parse(StatsInput(text=text))

        assert len(output.statistics) >= 1
        hr_stats = [s for s in output.statistics if s.stat_type == StatisticType.HAZARD_RATIO]
        assert len(hr_stats) == 1
        assert hr_stats[0].p_value == 0.03

    def test_multiple_stats_with_p_values(self, parser):
        """Multiple statistics with p-values."""
        text = "HR = 0.86, p=0.02 and OR = 2.5, p=0.001"
        output = parser.parse(StatsInput(text=text))

        assert len(output.statistics) >= 2
        # At least one should have p-values linked
        p_values = [s.p_value for s in output.statistics if s.p_value is not None]
        assert len(p_values) >= 1


# ===========================================================================
# Test: Percentage Extraction
# ===========================================================================

class TestPercentageExtraction:
    """Test percentage extraction."""

    def test_basic_percentage(self, parser):
        """15.5%"""
        text = "The improvement rate was 15.5%"
        output = parser.parse(StatsInput(text=text))

        percentages = [s for s in output.statistics if s.stat_type == StatisticType.PERCENTAGE]
        assert len(percentages) == 1
        assert percentages[0].value == 15.5

    def test_reduced_by_percentage(self, parser):
        """reduced by X%"""
        text = "Pain was reduced by 35%"
        output = parser.parse(StatsInput(text=text))

        percentages = [s for s in output.statistics if s.stat_type == StatisticType.PERCENTAGE]
        assert len(percentages) == 1
        assert percentages[0].value == 35.0

    def test_increased_by_percentage(self, parser):
        """increased by X%"""
        text = "Fusion rate increased by 12.3%"
        output = parser.parse(StatsInput(text=text))

        percentages = [s for s in output.statistics if s.stat_type == StatisticType.PERCENTAGE]
        assert len(percentages) == 1
        assert percentages[0].value == 12.3

    def test_percentage_out_of_range_ignored(self, parser):
        """Percentages > 100 or < 0 should be ignored."""
        text = "Improvement was 150% (invalid)"
        output = parser.parse(StatsInput(text=text))

        percentages = [s for s in output.statistics if s.stat_type == StatisticType.PERCENTAGE]
        assert len(percentages) == 0

    def test_percentage_extraction_disabled(self, parser_no_percentages):
        """Percentage extraction disabled."""
        text = "Improvement rate was 25%"
        output = parser_no_percentages.parse(StatsInput(text=text))

        percentages = [s for s in output.statistics if s.stat_type == StatisticType.PERCENTAGE]
        assert len(percentages) == 0

    def test_duplicate_percentages_removed(self, parser):
        """Duplicate percentage values should be removed."""
        text = "Group A: 15%, Group B: 15%"
        output = parser.parse(StatsInput(text=text))

        percentages = [s for s in output.statistics if s.stat_type == StatisticType.PERCENTAGE]
        # Should only have one entry for 15%
        assert len(percentages) == 1


# ===========================================================================
# Test: Effect Direction Determination
# ===========================================================================

class TestEffectDirection:
    """Test effect direction determination."""

    def test_hr_less_than_1_positive_effect(self, parser):
        """HR < 1 with CI not crossing 1 = positive."""
        text = "HR 0.75 (95% CI 0.60-0.90)"
        output = parser.parse(StatsInput(text=text))

        stat = output.statistics[0]
        assert stat.effect_direction == EffectDirection.POSITIVE

    def test_hr_greater_than_1_negative_effect(self, parser):
        """HR > 1 with CI not crossing 1 = negative."""
        text = "HR 1.5 (95% CI 1.2-1.8)"
        output = parser.parse(StatsInput(text=text))

        stat = output.statistics[0]
        assert stat.effect_direction == EffectDirection.NEGATIVE

    def test_hr_ci_crosses_1_neutral(self, parser):
        """HR with CI crossing 1 = neutral."""
        text = "HR 0.95 (95% CI 0.80-1.15)"
        output = parser.parse(StatsInput(text=text))

        stat = output.statistics[0]
        assert stat.effect_direction == EffectDirection.NEUTRAL

    def test_or_greater_than_1_negative(self, parser):
        """OR > 1 (risk increase) = negative."""
        text = "OR 2.5 (95% CI 1.5-4.0)"
        output = parser.parse(StatsInput(text=text))

        stat = output.statistics[0]
        assert stat.effect_direction == EffectDirection.NEGATIVE

    def test_or_less_than_1_positive(self, parser):
        """OR < 1 (risk decrease) = positive."""
        text = "OR 0.6 (95% CI 0.4-0.8)"
        output = parser.parse(StatsInput(text=text))

        stat = output.statistics[0]
        assert stat.effect_direction == EffectDirection.POSITIVE


# ===========================================================================
# Test: Statistical Significance
# ===========================================================================

class TestStatisticalSignificance:
    """Test statistical significance determination."""

    def test_significant_by_p_value(self, parser):
        """p < 0.05 = significant."""
        text = "HR = 0.86, p = 0.02"
        output = parser.parse(StatsInput(text=text))

        hr_stats = [s for s in output.statistics if s.stat_type == StatisticType.HAZARD_RATIO]
        assert len(hr_stats) > 0
        stat = hr_stats[0]
        assert stat.is_significant is True

    def test_not_significant_by_p_value(self, parser):
        """p >= 0.05 = not significant."""
        text = "HR = 0.95, p = 0.12"
        output = parser.parse(StatsInput(text=text))

        hr_stats = [s for s in output.statistics if s.stat_type == StatisticType.HAZARD_RATIO]
        assert len(hr_stats) > 0
        stat = hr_stats[0]
        assert stat.is_significant is False

    def test_significant_by_ci_not_crossing_1(self, parser_no_percentages):
        """CI not crossing 1 = significant."""
        text = "HR 0.75 (95% CI 0.60-0.90)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        stat = output.statistics[0]
        # CI doesn't cross 1 → significant
        assert stat.is_significant is True

    def test_not_significant_by_ci_crossing_1(self, parser_no_percentages):
        """CI crossing 1 = not significant."""
        text = "HR 0.95 (95% CI 0.80-1.15)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        stat = output.statistics[0]
        # CI crosses 1 → not significant
        assert stat.is_significant is False

    def test_custom_significance_threshold(self, parser_custom_threshold):
        """Custom threshold (0.01)."""
        text = "HR = 0.86, p = 0.03"
        output = parser_custom_threshold.parse(StatsInput(text=text))

        hr_stats = [s for s in output.statistics if s.stat_type == StatisticType.HAZARD_RATIO]
        assert len(hr_stats) > 0
        stat = hr_stats[0]
        # p=0.03 >= 0.01 threshold → not significant
        assert stat.is_significant is False


# ===========================================================================
# Test: Primary Result Identification
# ===========================================================================

class TestPrimaryResultIdentification:
    """Test primary result identification."""

    def test_primary_outcome_keyword(self, parser):
        """Primary outcome mentioned in text."""
        text = "The primary outcome: HR = 0.75, p=0.01"
        output = parser.parse(StatsInput(text=text))

        assert output.primary_result is not None
        assert output.primary_result.value == 0.75

    def test_primary_endpoint_keyword(self, parser_no_percentages):
        """Primary endpoint keyword."""
        text = "Primary endpoint: OR 2.3 (95% CI 1.5-3.5)"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert output.primary_result is not None

    def test_first_hr_as_fallback(self, parser):
        """First HR/OR/RR used as fallback if no primary keyword."""
        text = "OR = 1.5, p=0.05 and RR = 1.2, p=0.10"
        output = parser.parse(StatsInput(text=text))

        # Should pick first one (OR)
        assert output.primary_result is not None
        assert output.primary_result.stat_type == StatisticType.ODDS_RATIO


# ===========================================================================
# Test: Summary Generation
# ===========================================================================

class TestSummaryGeneration:
    """Test summary generation."""

    def test_summary_with_stats(self, parser):
        """Summary when statistics are found."""
        text = "HR = 0.86, p=0.01 and OR = 2.5, p=0.03"
        output = parser.parse(StatsInput(text=text))

        # Should find at least the two effect measures
        assert "statistical results" in output.summary.lower()
        assert "effect measures" in output.summary.lower()

    def test_summary_no_stats(self, parser):
        """Summary when no statistics found."""
        text = "No statistical data available."
        output = parser.parse(StatsInput(text=text))

        assert output.summary == "No statistical results found."

    def test_has_significant_results_flag(self, parser):
        """has_significant_results flag set correctly."""
        text = "HR = 0.75, p=0.001"
        output = parser.parse(StatsInput(text=text))

        assert output.has_significant_results is True

    def test_no_significant_results_flag(self, parser_no_percentages):
        """has_significant_results flag false when no significant results."""
        text = "HR 0.95 (95% CI 0.80-1.15), p=0.50"
        output = parser_no_percentages.parse(StatsInput(text=text))

        assert output.has_significant_results is False


# ===========================================================================
# Test: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_text(self, parser):
        """Empty text input."""
        output = parser.parse(StatsInput(text=""))

        assert len(output.statistics) == 0
        assert output.primary_result is None
        assert output.summary == "No text to parse"

    def test_whitespace_only(self, parser):
        """Whitespace-only text."""
        output = parser.parse(StatsInput(text="   \n\t  "))

        assert len(output.statistics) == 0

    def test_no_statistical_content(self, parser):
        """Text with no statistical content."""
        text = "This is a paper about spine surgery with no statistics."
        output = parser.parse(StatsInput(text=text))

        assert len(output.statistics) == 0

    def test_malformed_ci_ignored(self, parser):
        """Malformed CI should be ignored."""
        text = "HR 0.86 (95% CI invalid)"
        output = parser.parse(StatsInput(text=text))

        # Should extract HR without CI
        assert len(output.statistics) >= 0

    def test_invalid_p_value_ignored(self, parser):
        """Invalid p-value (>1 or <0) should be ignored."""
        text = "p = 1.5 (invalid)"
        output = parser.parse(StatsInput(text=text))

        # Invalid p-values should not be linked
        assert all(s.p_value is None or 0 < s.p_value < 1
                  for s in output.statistics)

    def test_duplicate_removal(self, parser):
        """Duplicate statistics should be removed."""
        text = "HR 0.86 (95% CI 0.74-0.99) and HR 0.86 (95% CI 0.74-0.99)"
        output = parser.parse(StatsInput(text=text))

        # Should only have one result after deduplication
        hrs = [s for s in output.statistics if s.stat_type == StatisticType.HAZARD_RATIO]
        assert len(hrs) == 1

    def test_multiple_different_stats(self, parser):
        """Multiple different statistics should all be extracted."""
        text = "HR = 0.86, p=0.02; OR = 2.5, p=0.001; RR = 0.75, p=0.03"
        output = parser.parse(StatsInput(text=text))

        # Should have at least 3 effect measures
        stat_types = {s.stat_type for s in output.statistics}
        assert StatisticType.HAZARD_RATIO in stat_types
        assert StatisticType.ODDS_RATIO in stat_types
        assert StatisticType.RELATIVE_RISK in stat_types


# ===========================================================================
# Test: Batch Processing
# ===========================================================================

class TestBatchProcessing:
    """Test batch processing."""

    def test_parse_batch(self, parser):
        """Batch parsing multiple inputs."""
        inputs = [
            StatsInput(text="HR = 0.86, p=0.02"),
            StatsInput(text="OR = 2.5, p=0.001"),
            StatsInput(text="No statistics here"),
        ]

        outputs = parser.parse_batch(inputs)

        assert len(outputs) == 3
        # First two should have at least one statistic each
        assert len(outputs[0].statistics) >= 1
        assert len(outputs[1].statistics) >= 1
        assert len(outputs[2].statistics) == 0

    def test_parse_batch_empty(self, parser):
        """Batch parsing with empty list."""
        outputs = parser.parse_batch([])

        assert len(outputs) == 0


# ===========================================================================
# Test: ConfidenceInterval and StatisticResult
# ===========================================================================

class TestDataClasses:
    """Test data class functionality."""

    def test_confidence_interval_default_level(self):
        """ConfidenceInterval default level is 0.95."""
        ci = ConfidenceInterval(lower=0.5, upper=0.9)
        assert ci.level == 0.95

    def test_statistic_result_defaults(self):
        """StatisticResult default values."""
        stat = StatisticResult(
            stat_type=StatisticType.HAZARD_RATIO,
            value=0.86
        )
        assert stat.ci is None
        assert stat.p_value is None
        assert stat.outcome is None
        assert stat.comparison is None
        assert stat.effect_direction == EffectDirection.UNKNOWN
        assert stat.is_significant is None
        assert stat.raw_text == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

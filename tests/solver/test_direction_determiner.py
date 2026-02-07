"""Unit tests for Direction Determiner module.

pytest 실행:
    pytest tests/solver/test_direction_determiner.py -v
"""

import pytest
from dataclasses import dataclass

from solver.direction_determiner import (
    DirectionDeterminer,
    OutcomeDirection,
    ComparisonResult,
    parse_numeric_value,
    _normalize_outcome_name,
    _is_higher_better,
)


# =============================================================================
# Test Data Classes
# =============================================================================

@dataclass
class MockExtractedOutcome:
    """Mock ExtractedOutcome for testing."""
    name: str
    value_intervention: str
    value_control: str


# =============================================================================
# Test Name Normalization
# =============================================================================

class TestNameNormalization:
    """Test outcome name normalization."""

    def test_basic_normalization(self):
        """Test basic name normalization."""
        assert _normalize_outcome_name("VAS") == "vas"
        assert _normalize_outcome_name("ODI") == "odi"
        assert _normalize_outcome_name("JOA") == "joa"

    def test_with_spaces(self):
        """Test normalization with spaces."""
        assert _normalize_outcome_name("VAS Back Pain") == "vas_back_pain"
        assert _normalize_outcome_name("Fusion Rate") == "fusion_rate"

    def test_with_parentheses(self):
        """Test normalization with abbreviations in parentheses."""
        assert _normalize_outcome_name("Oswestry Disability Index (ODI)") == "odi"
        assert _normalize_outcome_name("Japanese Orthopaedic Association (JOA) Score") == "joa"
        assert _normalize_outcome_name("Numeric Rating Scale (NRS)") == "nrs"

    def test_with_hyphens(self):
        """Test normalization with hyphens."""
        assert _normalize_outcome_name("SF-36") == "sf_36"
        assert _normalize_outcome_name("EQ-5D") == "eq_5d"
        assert _normalize_outcome_name("PI-LL") == "pi_ll"

    def test_with_special_chars(self):
        """Test normalization with special characters."""
        assert _normalize_outcome_name("Blood Loss (mL)") == "ml"  # abbreviation extracted
        assert _normalize_outcome_name("Operation Time (min)") == "min"


# =============================================================================
# Test Direction Classification
# =============================================================================

class TestDirectionClassification:
    """Test is_higher_better classification."""

    def test_higher_is_better(self):
        """Test outcomes where higher is better."""
        assert _is_higher_better("Fusion Rate") is True
        assert _is_higher_better("JOA") is True
        assert _is_higher_better("SF-36") is True
        assert _is_higher_better("EQ-5D") is True
        assert _is_higher_better("Satisfaction") is True

    def test_lower_is_better(self):
        """Test outcomes where lower is better."""
        assert _is_higher_better("VAS") is False
        assert _is_higher_better("ODI") is False
        assert _is_higher_better("NDI") is False
        assert _is_higher_better("Complication Rate") is False
        assert _is_higher_better("Blood Loss") is False
        assert _is_higher_better("Operation Time") is False

    def test_context_dependent(self):
        """Test outcomes that are context-dependent."""
        assert _is_higher_better("Lordosis") is None
        assert _is_higher_better("Cobb Angle") is None
        assert _is_higher_better("Disc Height") is None

    def test_unknown_outcomes(self):
        """Test unknown outcomes."""
        assert _is_higher_better("Unknown Metric XYZ") is None


# =============================================================================
# Test Direction Determination
# =============================================================================

class TestDirectionDetermination:
    """Test direction determination from baseline/final values."""

    @pytest.fixture
    def determiner(self):
        """Create DirectionDeterminer instance."""
        return DirectionDeterminer(unchanged_threshold=0.05)

    def test_improved_pain_score(self, determiner):
        """Test improved pain score (lower is better)."""
        direction = determiner.determine_direction("VAS", 7.5, 3.2)
        assert direction == OutcomeDirection.IMPROVED

    def test_worsened_pain_score(self, determiner):
        """Test worsened pain score."""
        direction = determiner.determine_direction("VAS", 3.0, 6.5)
        assert direction == OutcomeDirection.WORSENED

    def test_improved_functional_score(self, determiner):
        """Test improved functional score (higher is better)."""
        direction = determiner.determine_direction("JOA", 8.0, 14.0)
        assert direction == OutcomeDirection.IMPROVED

    def test_worsened_functional_score(self, determiner):
        """Test worsened functional score."""
        direction = determiner.determine_direction("JOA", 14.0, 8.0)
        assert direction == OutcomeDirection.WORSENED

    def test_unchanged(self, determiner):
        """Test unchanged outcome (within threshold)."""
        # 3% change → unchanged
        direction = determiner.determine_direction("VAS", 5.0, 4.85)
        assert direction == OutcomeDirection.UNCHANGED

    def test_context_dependent(self, determiner):
        """Test context-dependent outcomes."""
        direction = determiner.determine_direction("Lordosis", 30.0, 35.0)
        assert direction == OutcomeDirection.UNKNOWN

    def test_explicit_outcome_type(self, determiner):
        """Test with explicitly specified outcome type."""
        # Force interpretation
        direction = determiner.determine_direction(
            "Custom Metric", 10.0, 15.0, outcome_type="higher_is_better"
        )
        assert direction == OutcomeDirection.IMPROVED

        direction = determiner.determine_direction(
            "Custom Metric", 10.0, 15.0, outcome_type="lower_is_better"
        )
        assert direction == OutcomeDirection.WORSENED

    def test_zero_baseline_warning(self, determiner):
        """Test handling of zero baseline value."""
        direction = determiner.determine_direction("VAS", 0.0, 5.0)
        assert direction == OutcomeDirection.UNKNOWN


# =============================================================================
# Test Comparison Interpretation
# =============================================================================

class TestComparisonInterpretation:
    """Test intervention vs control comparison."""

    @pytest.fixture
    def determiner(self):
        """Create DirectionDeterminer instance."""
        return DirectionDeterminer()

    def test_pain_improved_intervention(self, determiner):
        """Test pain improvement in intervention group."""
        result = determiner.interpret_comparison("VAS", 3.2, 5.1)

        assert result.direction == OutcomeDirection.IMPROVED
        assert result.favors == "intervention"
        assert result.difference < 0  # Lower pain in intervention
        assert result.confidence > 0.5  # High confidence

    def test_pain_worsened_intervention(self, determiner):
        """Test pain worsening in intervention group."""
        result = determiner.interpret_comparison("VAS", 6.5, 4.2)

        assert result.direction == OutcomeDirection.WORSENED
        assert result.favors == "control"
        assert result.difference > 0  # Higher pain in intervention

    def test_functional_improved_intervention(self, determiner):
        """Test functional improvement in intervention group."""
        result = determiner.interpret_comparison("JOA", 14.2, 9.8)

        assert result.direction == OutcomeDirection.IMPROVED
        assert result.favors == "intervention"
        assert result.difference > 0  # Higher function in intervention

    def test_unchanged_outcome(self, determiner):
        """Test unchanged outcome (minimal difference)."""
        result = determiner.interpret_comparison("VAS", 5.0, 5.1)

        assert result.direction == OutcomeDirection.UNCHANGED
        assert result.favors == "neither"

    def test_context_dependent_unknown(self, determiner):
        """Test context-dependent outcome."""
        result = determiner.interpret_comparison("Lordosis", 35.0, 40.0)

        assert result.direction == OutcomeDirection.UNKNOWN
        assert result.favors == "unknown"
        assert result.confidence == 0.0

    def test_zero_control_value(self, determiner):
        """Test handling of zero control value."""
        result = determiner.interpret_comparison("Complication Rate", 5.0, 0.0)

        # Should not crash, but confidence low
        assert result.confidence == 0.5

    def test_high_confidence_large_difference(self, determiner):
        """Test high confidence with large difference."""
        result = determiner.interpret_comparison("VAS", 2.0, 8.0)

        # >50% difference → high confidence
        assert result.confidence > 0.9
        assert abs(result.percent_change) > 50

    def test_low_confidence_small_difference(self, determiner):
        """Test low confidence with small difference."""
        result = determiner.interpret_comparison("VAS", 5.0, 5.3)

        # 5.66% difference → moderate confidence (< 0.6)
        assert result.confidence < 0.6


# =============================================================================
# Test Batch Interpretation
# =============================================================================

class TestBatchInterpretation:
    """Test batch comparison interpretation."""

    @pytest.fixture
    def determiner(self):
        """Create DirectionDeterminer instance."""
        return DirectionDeterminer()

    def test_batch_comparisons(self, determiner):
        """Test batch interpretation of multiple outcomes."""
        comparisons = [
            ("VAS", 3.2, 5.1, None),
            ("ODI", 18.5, 35.2, None),
            ("JOA", 14.2, 9.8, None),
            ("Fusion Rate", 92.5, 85.3, None),
        ]

        results = determiner.batch_interpret_comparisons(comparisons)

        assert len(results) == 4
        assert all(isinstance(r, ComparisonResult) for r in results)

        # All should favor intervention
        assert all(r.favors == "intervention" for r in results)

        # All should be improved
        assert all(r.direction == OutcomeDirection.IMPROVED for r in results)


# =============================================================================
# Test Numeric Value Parsing
# =============================================================================

class TestNumericValueParsing:
    """Test parsing numeric values from strings."""

    def test_simple_number(self):
        """Test simple numeric strings."""
        assert parse_numeric_value("3.2") == 3.2
        assert parse_numeric_value("85") == 85.0

    def test_with_units(self):
        """Test numbers with units."""
        assert parse_numeric_value("85.2%") == 85.2
        assert parse_numeric_value("12 points") == 12.0
        assert parse_numeric_value("120 minutes") == 120.0

    def test_with_std_dev(self):
        """Test numbers with standard deviation."""
        assert parse_numeric_value("3.2±1.1") == 3.2
        assert parse_numeric_value("45.3 ± 8.2") == 45.3

    def test_negative_numbers(self):
        """Test negative numbers."""
        assert parse_numeric_value("-5.2") == -5.2
        assert parse_numeric_value("-10.5 degrees") == -10.5

    def test_invalid_strings(self):
        """Test invalid strings."""
        assert parse_numeric_value("") is None
        assert parse_numeric_value("N/A") is None
        assert parse_numeric_value("not applicable") is None


# =============================================================================
# Test Integration with ExtractedOutcome
# =============================================================================

class TestExtractedOutcomeIntegration:
    """Test integration with ExtractedOutcome objects."""

    def test_interpret_from_extracted_outcome(self):
        """Test interpretation from mock ExtractedOutcome."""
        from solver.direction_determiner import interpret_from_extracted_outcome

        outcome = MockExtractedOutcome(
            name="VAS",
            value_intervention="3.2±1.1",
            value_control="5.1±1.3"
        )

        result = interpret_from_extracted_outcome(outcome)

        assert result.direction == OutcomeDirection.IMPROVED
        assert result.favors == "intervention"
        assert result.difference < 0

    def test_unparseable_values(self):
        """Test handling of unparseable values."""
        from solver.direction_determiner import interpret_from_extracted_outcome

        outcome = MockExtractedOutcome(
            name="VAS",
            value_intervention="N/A",
            value_control="unknown"
        )

        result = interpret_from_extracted_outcome(outcome)

        assert result.direction == OutcomeDirection.UNKNOWN
        assert result.confidence == 0.0


# =============================================================================
# Test Explanation Generation
# =============================================================================

class TestExplanation:
    """Test explanation text generation."""

    @pytest.fixture
    def determiner(self):
        """Create DirectionDeterminer instance."""
        return DirectionDeterminer()

    def test_explain_higher_is_better(self, determiner):
        """Test explanation for higher-is-better outcomes."""
        explanation = determiner.explain_outcome_type("JOA")
        assert "higher" in explanation.lower()
        assert "better" in explanation.lower()

    def test_explain_lower_is_better(self, determiner):
        """Test explanation for lower-is-better outcomes."""
        explanation = determiner.explain_outcome_type("VAS")
        assert "lower" in explanation.lower()
        assert "better" in explanation.lower()

    def test_explain_context_dependent(self, determiner):
        """Test explanation for context-dependent outcomes."""
        explanation = determiner.explain_outcome_type("Lordosis")
        assert "context" in explanation.lower()


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def determiner(self):
        """Create DirectionDeterminer instance."""
        return DirectionDeterminer()

    def test_very_small_threshold(self):
        """Test with very small unchanged threshold."""
        determiner = DirectionDeterminer(unchanged_threshold=0.001)

        # 0.2% change should be detected as improvement (below threshold = 0.1%)
        direction = determiner.determine_direction("VAS", 5.0, 4.995)
        assert direction == OutcomeDirection.UNCHANGED

    def test_very_large_threshold(self):
        """Test with very large unchanged threshold."""
        determiner = DirectionDeterminer(unchanged_threshold=0.5)

        # 30% change should still be unchanged
        direction = determiner.determine_direction("VAS", 5.0, 3.5)
        assert direction == OutcomeDirection.UNCHANGED

    def test_identical_values(self, determiner):
        """Test identical intervention and control values."""
        result = determiner.interpret_comparison("VAS", 5.0, 5.0)

        assert result.direction == OutcomeDirection.UNCHANGED
        assert result.difference == 0.0
        assert result.percent_change == 0.0

    def test_case_insensitive_outcome_names(self, determiner):
        """Test case-insensitive outcome name matching."""
        # All should be recognized
        assert determiner.is_higher_better("VAS") is False
        assert determiner.is_higher_better("vas") is False
        assert determiner.is_higher_better("Vas") is False
        assert determiner.is_higher_better("VaS") is False


# =============================================================================
# Test Public Interface
# =============================================================================

class TestPublicInterface:
    """Test public interface methods."""

    def test_is_higher_better_public(self):
        """Test public is_higher_better method."""
        determiner = DirectionDeterminer()

        assert determiner.is_higher_better("VAS") is False
        assert determiner.is_higher_better("JOA") is True
        assert determiner.is_higher_better("Lordosis") is None

    def test_all_methods_accessible(self):
        """Test that all public methods are accessible."""
        determiner = DirectionDeterminer()

        # Should not raise AttributeError
        assert hasattr(determiner, "determine_direction")
        assert hasattr(determiner, "is_higher_better")
        assert hasattr(determiner, "interpret_comparison")
        assert hasattr(determiner, "batch_interpret_comparisons")
        assert hasattr(determiner, "explain_outcome_type")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

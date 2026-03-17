"""Tests for Evidence Synthesizer meta-analysis methods (v1.27.0).

Tests cover:
    - calculate_weighted_effect_size: Inverse-variance weighted pooling
    - calculate_i_squared: Cochran's Q and I-squared heterogeneity
    - generate_forest_plot_data: Forest plot data structure
    - Edge cases: single study, missing data, degenerate CIs
"""

import math
import pytest
from unittest.mock import AsyncMock

from src.solver.evidence_synthesizer import (
    EvidenceSynthesizer,
)
from src.solver.evidence_synthesizer import ValidationError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def synthesizer():
    """EvidenceSynthesizer instance with mock Neo4j client."""
    mock_client = AsyncMock()
    return EvidenceSynthesizer(mock_client)


@pytest.fixture
def homogeneous_studies():
    """Studies with similar effect sizes (low heterogeneity)."""
    return [
        {"study_label": "Smith 2020", "effect_size": 2.0, "ci_lower": 1.0, "ci_upper": 3.0, "n": 100},
        {"study_label": "Jones 2021", "effect_size": 2.2, "ci_lower": 1.2, "ci_upper": 3.2, "n": 120},
        {"study_label": "Lee 2022", "effect_size": 1.8, "ci_lower": 0.8, "ci_upper": 2.8, "n": 90},
    ]


@pytest.fixture
def heterogeneous_studies():
    """Studies with diverse effect sizes (high heterogeneity)."""
    return [
        {"study_label": "Alpha 2020", "effect_size": 0.5, "ci_lower": 0.2, "ci_upper": 0.8, "n": 200},
        {"study_label": "Beta 2021", "effect_size": 5.0, "ci_lower": 3.0, "ci_upper": 7.0, "n": 50},
        {"study_label": "Gamma 2022", "effect_size": -1.0, "ci_lower": -2.5, "ci_upper": 0.5, "n": 80},
    ]


# =============================================================================
# Test calculate_weighted_effect_size
# =============================================================================

class TestWeightedEffectSize:
    """Tests for inverse-variance weighted mean effect size."""

    def test_basic_calculation(self, synthesizer, homogeneous_studies):
        """Pooled estimate should be between individual study estimates."""
        result = synthesizer.calculate_weighted_effect_size(homogeneous_studies)

        assert "weighted_mean" in result
        assert "ci_lower" in result
        assert "ci_upper" in result
        assert "n_studies" in result
        assert result["n_studies"] == 3

        # Weighted mean should be between min and max effect sizes
        assert 1.8 <= result["weighted_mean"] <= 2.2
        # CI should bracket the mean
        assert result["ci_lower"] < result["weighted_mean"] < result["ci_upper"]

    def test_weights_sum_to_one(self, synthesizer, homogeneous_studies):
        """Normalized weights should sum to 1."""
        result = synthesizer.calculate_weighted_effect_size(homogeneous_studies)
        assert abs(sum(result["weights"]) - 1.0) < 1e-10

    def test_narrower_ci_gets_higher_weight(self, synthesizer):
        """Study with narrower CI (more precise) should get higher weight."""
        studies = [
            {"effect_size": 2.0, "ci_lower": 1.9, "ci_upper": 2.1, "n": 1000},  # Narrow CI
            {"effect_size": 2.0, "ci_lower": 0.0, "ci_upper": 4.0, "n": 10},     # Wide CI
        ]

        result = synthesizer.calculate_weighted_effect_size(studies)
        assert result["weights"][0] > result["weights"][1]

    def test_single_study(self, synthesizer):
        """Single study should return that study's effect size."""
        studies = [
            {"effect_size": 3.0, "ci_lower": 2.0, "ci_upper": 4.0, "n": 50}
        ]

        result = synthesizer.calculate_weighted_effect_size(studies)
        assert result["weighted_mean"] == 3.0
        assert result["n_studies"] == 1

    def test_empty_raises_error(self, synthesizer):
        """Empty studies list should raise ValidationError."""
        with pytest.raises((ValueError, ValidationError)):
            synthesizer.calculate_weighted_effect_size([])

    def test_missing_effect_size_raises(self, synthesizer):
        """Study missing effect_size should raise error."""
        with pytest.raises((ValueError, ValidationError)):
            synthesizer.calculate_weighted_effect_size([{"ci_lower": 1.0, "ci_upper": 3.0}])

    def test_fallback_to_sample_size_weight(self, synthesizer):
        """Without CI, should use sample size as weight."""
        studies = [
            {"effect_size": 2.0, "n": 100},
            {"effect_size": 4.0, "n": 200},
        ]

        result = synthesizer.calculate_weighted_effect_size(studies)
        # Larger sample should have more weight, pulling mean toward 4.0
        assert result["weighted_mean"] > 3.0
        assert result["weights"][1] > result["weights"][0]

    def test_negative_effect_sizes(self, synthesizer):
        """Should handle negative effect sizes correctly."""
        studies = [
            {"effect_size": -2.0, "ci_lower": -3.0, "ci_upper": -1.0, "n": 100},
            {"effect_size": -1.5, "ci_lower": -2.5, "ci_upper": -0.5, "n": 100},
        ]

        result = synthesizer.calculate_weighted_effect_size(studies)
        assert result["weighted_mean"] < 0
        assert result["ci_upper"] < 0  # Entire CI should be negative

    def test_degenerate_ci(self, synthesizer):
        """Zero-width CI should fall back to sample size weight."""
        studies = [
            {"effect_size": 2.0, "ci_lower": 2.0, "ci_upper": 2.0, "n": 50},
            {"effect_size": 3.0, "ci_lower": 2.0, "ci_upper": 4.0, "n": 50},
        ]

        result = synthesizer.calculate_weighted_effect_size(studies)
        assert result["n_studies"] == 2
        # Should still produce a valid result
        assert 2.0 <= result["weighted_mean"] <= 3.0


# =============================================================================
# Test calculate_i_squared
# =============================================================================

class TestISquared:
    """Tests for I-squared heterogeneity statistic."""

    def test_low_heterogeneity(self, synthesizer, homogeneous_studies):
        """Homogeneous studies should yield low I-squared."""
        result = synthesizer.calculate_i_squared(homogeneous_studies)

        assert "i_squared" in result
        assert "q_statistic" in result
        assert "df" in result
        assert "p_value" in result
        assert "interpretation" in result

        assert result["i_squared"] < 50  # Should be low-moderate
        assert result["df"] == 2
        assert "Low" in result["interpretation"] or "Moderate" in result["interpretation"]

    def test_high_heterogeneity(self, synthesizer, heterogeneous_studies):
        """Heterogeneous studies should yield high I-squared."""
        result = synthesizer.calculate_i_squared(heterogeneous_studies)

        assert result["i_squared"] > 50
        assert "Substantial" in result["interpretation"] or "Considerable" in result["interpretation"]

    def test_single_study(self, synthesizer):
        """Single study should return 0 I-squared."""
        studies = [{"effect_size": 2.0, "ci_lower": 1.0, "ci_upper": 3.0}]
        result = synthesizer.calculate_i_squared(studies)

        assert result["i_squared"] == 0.0
        assert result["q_statistic"] == 0.0
        assert result["p_value"] == 1.0
        assert "fewer than 2" in result["interpretation"]

    def test_empty_studies(self, synthesizer):
        """Empty list should return 0 I-squared."""
        result = synthesizer.calculate_i_squared([])
        assert result["i_squared"] == 0.0

    def test_identical_studies(self, synthesizer):
        """Identical studies should yield 0% I-squared."""
        studies = [
            {"effect_size": 2.0, "ci_lower": 1.0, "ci_upper": 3.0, "n": 100},
            {"effect_size": 2.0, "ci_lower": 1.0, "ci_upper": 3.0, "n": 100},
            {"effect_size": 2.0, "ci_lower": 1.0, "ci_upper": 3.0, "n": 100},
        ]

        result = synthesizer.calculate_i_squared(studies)
        assert result["i_squared"] == 0.0

    def test_i_squared_bounded(self, synthesizer, heterogeneous_studies):
        """I-squared should always be in [0, 100]."""
        result = synthesizer.calculate_i_squared(heterogeneous_studies)
        assert 0 <= result["i_squared"] <= 100

    def test_p_value_bounded(self, synthesizer, heterogeneous_studies):
        """P-value should always be in [0, 1]."""
        result = synthesizer.calculate_i_squared(heterogeneous_studies)
        assert 0 <= result["p_value"] <= 1

    def test_two_studies(self, synthesizer):
        """Two divergent studies should produce high heterogeneity."""
        studies = [
            {"effect_size": 1.0, "ci_lower": 0.5, "ci_upper": 1.5, "n": 100},
            {"effect_size": 10.0, "ci_lower": 9.5, "ci_upper": 10.5, "n": 100},
        ]

        result = synthesizer.calculate_i_squared(studies)
        assert result["i_squared"] > 75
        assert result["df"] == 1


# =============================================================================
# Test generate_forest_plot_data
# =============================================================================

class TestForestPlotData:
    """Tests for forest plot data generation."""

    def test_basic_structure(self, synthesizer, homogeneous_studies):
        """Should return properly structured forest plot data."""
        result = synthesizer.generate_forest_plot_data(homogeneous_studies)

        assert "studies" in result
        assert "summary" in result
        assert "heterogeneity" in result
        assert "n_studies" in result
        assert "null_line" in result

        assert result["n_studies"] == 3
        assert result["null_line"] == 0.0

    def test_per_study_rows(self, synthesizer, homogeneous_studies):
        """Each study should have label, effect_size, CI, weight_pct."""
        result = synthesizer.generate_forest_plot_data(homogeneous_studies)

        for row in result["studies"]:
            assert "label" in row
            assert "effect_size" in row
            assert "ci_lower" in row
            assert "ci_upper" in row
            assert "weight_pct" in row
            assert row["weight_pct"] > 0

    def test_weights_sum_to_100(self, synthesizer, homogeneous_studies):
        """Weight percentages should approximately sum to 100."""
        result = synthesizer.generate_forest_plot_data(homogeneous_studies)
        total_weight = sum(row["weight_pct"] for row in result["studies"])
        assert abs(total_weight - 100.0) < 1.0  # Allow rounding error

    def test_summary_diamond(self, synthesizer, homogeneous_studies):
        """Summary should contain diamond coordinates."""
        result = synthesizer.generate_forest_plot_data(homogeneous_studies)
        summary = result["summary"]

        assert "effect_size" in summary
        assert "ci_lower" in summary
        assert "ci_upper" in summary
        assert "diamond" in summary
        assert summary["diamond"]["left"] < summary["diamond"]["center"] < summary["diamond"]["right"]

    def test_study_labels(self, synthesizer, homogeneous_studies):
        """Study labels should be preserved from input."""
        result = synthesizer.generate_forest_plot_data(homogeneous_studies)

        labels = [row["label"] for row in result["studies"]]
        assert "Smith 2020" in labels
        assert "Jones 2021" in labels
        assert "Lee 2022" in labels

    def test_heterogeneity_included(self, synthesizer, heterogeneous_studies):
        """Heterogeneity stats should be included."""
        result = synthesizer.generate_forest_plot_data(heterogeneous_studies)

        het = result["heterogeneity"]
        assert "i_squared" in het
        assert "q_statistic" in het

    def test_empty_studies(self, synthesizer):
        """Empty studies should return empty structure."""
        result = synthesizer.generate_forest_plot_data([])

        assert result["n_studies"] == 0
        assert result["studies"] == []
        assert result["summary"] is None

    def test_single_study(self, synthesizer):
        """Single study should work without errors."""
        studies = [
            {"study_label": "Only 2023", "effect_size": 1.5, "ci_lower": 0.5, "ci_upper": 2.5, "n": 50}
        ]

        result = synthesizer.generate_forest_plot_data(studies)

        assert result["n_studies"] == 1
        assert len(result["studies"]) == 1
        assert result["studies"][0]["label"] == "Only 2023"
        assert result["summary"]["effect_size"] == 1.5

    def test_default_study_labels(self, synthesizer):
        """Studies without labels should get default 'Study N' labels."""
        studies = [
            {"effect_size": 1.0, "ci_lower": 0.0, "ci_upper": 2.0},
            {"effect_size": 2.0, "ci_lower": 1.0, "ci_upper": 3.0},
        ]

        result = synthesizer.generate_forest_plot_data(studies)
        assert result["studies"][0]["label"] == "Study 1"
        assert result["studies"][1]["label"] == "Study 2"

    def test_summary_label_includes_i_squared(self, synthesizer, homogeneous_studies):
        """Summary label should include I-squared value."""
        result = synthesizer.generate_forest_plot_data(homogeneous_studies)
        assert "I^2=" in result["summary"]["label"]
        assert "Overall" in result["summary"]["label"]


# =============================================================================
# Test _chi2_survival helper
# =============================================================================

class TestChi2Survival:
    """Tests for the chi-squared survival function approximation."""

    def test_zero_x(self, synthesizer):
        """x=0 should give p=1."""
        assert synthesizer._chi2_survival(0, 5) == 1.0

    def test_zero_df(self, synthesizer):
        """df=0 should give p=1."""
        assert synthesizer._chi2_survival(5, 0) == 1.0

    def test_large_x(self, synthesizer):
        """Very large x should give p near 0."""
        p = synthesizer._chi2_survival(100, 2)
        assert p < 0.001

    def test_moderate_values(self, synthesizer):
        """Moderate chi2 value should give reasonable p."""
        # chi2(5.99, df=2) ~ p=0.05
        p = synthesizer._chi2_survival(5.99, 2)
        assert 0.01 < p < 0.15  # Approximate

    def test_bounded(self, synthesizer):
        """P-value should always be in [0, 1]."""
        for x in [0.1, 1.0, 5.0, 10.0, 50.0, 100.0]:
            for df in [1, 2, 5, 10, 20]:
                p = synthesizer._chi2_survival(x, df)
                assert 0.0 <= p <= 1.0

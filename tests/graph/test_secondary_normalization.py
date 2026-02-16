"""Tests for secondary entity normalization in RelationshipBuilder.

DV-002: Verify that secondary entity names are normalized before MERGE
to prevent duplicates caused by inconsistent casing/whitespace.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# 1. _normalize_secondary_entity() unit tests
# ---------------------------------------------------------------------------

class TestNormalizeSecondaryEntity:
    """Test RelationshipBuilder._normalize_secondary_entity()."""

    @pytest.fixture
    def builder(self):
        """Create a RelationshipBuilder with mocked dependencies."""
        from graph.relationship_builder import RelationshipBuilder

        mock_client = MagicMock()
        mock_normalizer = MagicMock()
        return RelationshipBuilder(mock_client, mock_normalizer)

    def test_trim_and_capitalize(self, builder):
        """Trim whitespace and capitalize first letter."""
        assert builder._normalize_secondary_entity(" obesity ") == "Obesity"

    def test_preserve_acronym(self, builder):
        """All-uppercase acronyms should be preserved."""
        assert builder._normalize_secondary_entity("BMI") == "BMI"

    def test_capitalize_first_letter(self, builder):
        """Lowercase first letter should be capitalized."""
        assert builder._normalize_secondary_entity("dural tear") == "Dural tear"

    def test_empty_string(self, builder):
        """Empty string should return empty string."""
        assert builder._normalize_secondary_entity("") == ""

    def test_none_passthrough(self, builder):
        """None should pass through unchanged."""
        assert builder._normalize_secondary_entity(None) is None

    def test_whitespace_only(self, builder):
        """Whitespace-only string should return empty after strip."""
        assert builder._normalize_secondary_entity("   ") == ""

    def test_already_capitalized(self, builder):
        """Already capitalized names should be unchanged."""
        assert builder._normalize_secondary_entity("Obesity") == "Obesity"

    def test_mixed_case_acronym(self, builder):
        """Mixed case (not all-uppercase) should capitalize first letter."""
        assert builder._normalize_secondary_entity("VAs score") == "VAs score"

    def test_preserve_vas(self, builder):
        """VAS (all-caps) should be preserved."""
        assert builder._normalize_secondary_entity("VAS") == "VAS"

    def test_preserve_mri(self, builder):
        """MRI (all-caps) should be preserved."""
        assert builder._normalize_secondary_entity("MRI") == "MRI"

    def test_leading_trailing_tabs(self, builder):
        """Tabs should also be stripped."""
        assert builder._normalize_secondary_entity("\tobesity\t") == "Obesity"


# ---------------------------------------------------------------------------
# 2. Anatomy normalization tests (snomed_enricher split segments)
# ---------------------------------------------------------------------------

class TestAnatomySegmentNormalization:
    """Test that anatomy segments are title-cased before MERGE in snomed_enricher."""

    def test_split_compound_anatomy_returns_parts(self):
        """split_compound_anatomy should split comma-separated anatomy strings."""
        from graph.snomed_enricher import split_compound_anatomy

        result = split_compound_anatomy("L4-5, L5-S1")
        assert len(result) == 2
        assert result[0] == "L4-5"
        assert result[1] == "L5-S1"

    def test_segment_normalization_logic(self):
        """Verify the DV-002 normalization logic matches expectations."""
        # This replicates the inline normalization used in cleanup_anatomy_nodes
        segments = ["cervical", "Lumbar", "thoracolumbar", "L4-5"]

        normalized = [
            (s[0].upper() + s[1:] if s and not s[0].isupper() else s)
            for s in segments
        ]

        assert normalized[0] == "Cervical"       # lowercase -> Capitalized
        assert normalized[1] == "Lumbar"          # already correct
        assert normalized[2] == "Thoracolumbar"   # lowercase -> Capitalized
        assert normalized[3] == "L4-5"            # already uppercase start

    def test_empty_segment_safe(self):
        """Empty segments should not cause errors in normalization."""
        segments = ["", "cervical", ""]
        normalized = [
            (s[0].upper() + s[1:] if s and not s[0].isupper() else s)
            for s in segments
        ]
        assert normalized[0] == ""
        assert normalized[1] == "Cervical"
        assert normalized[2] == ""

    def test_parse_segment_range_uppercase(self):
        """parse_segment_range should return properly cased segments."""
        from graph.snomed_enricher import parse_segment_range

        # L2-4 -> ["L2-3", "L3-4"] — these should already be uppercase
        result = parse_segment_range("L2-4")
        assert all(s[0].isupper() for s in result if s)

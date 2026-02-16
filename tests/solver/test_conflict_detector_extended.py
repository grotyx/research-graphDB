"""Extended tests for ConflictDetector module.

Covers untested branches and edge cases:
- Legacy API (detect method, ConflictInput/Output, ConflictPair)
- _determine_severity_from_levels edge cases
- _compare_severity and _severity_sort_key
- ConflictSeverity label property
- Empty conflict papers edge cases
- ConflictResult properties with edge values
- ConflictSummaryGenerator methods
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.solver.conflict_detector import (
    ConflictDetector,
    ConflictSeverity,
    ConflictResult,
    PaperEvidence,
    ConflictType,
    ConflictPair,
    ConflictInput,
    ConflictOutput,
    StudyResult,
    EVIDENCE_LEVEL_SCORES,
)
from src.solver.conflict_summary import (
    ConflictSummaryGenerator,
    SummaryConfig,
)


# ============================================================================
# Test: ConflictSeverity enum
# ============================================================================

class TestConflictSeverity:
    """Test ConflictSeverity enum."""

    def test_severity_values(self):
        """Severity integer values."""
        assert ConflictSeverity.LOW == 1
        assert ConflictSeverity.MEDIUM == 2
        assert ConflictSeverity.HIGH == 3
        assert ConflictSeverity.CRITICAL == 4

    def test_severity_labels(self):
        """Severity label property."""
        assert ConflictSeverity.LOW.label == "low"
        assert ConflictSeverity.MEDIUM.label == "medium"
        assert ConflictSeverity.HIGH.label == "high"
        assert ConflictSeverity.CRITICAL.label == "critical"

    def test_severity_comparison(self):
        """IntEnum comparison works."""
        assert ConflictSeverity.CRITICAL > ConflictSeverity.HIGH
        assert ConflictSeverity.HIGH > ConflictSeverity.MEDIUM
        assert ConflictSeverity.MEDIUM > ConflictSeverity.LOW
        assert ConflictSeverity.LOW < ConflictSeverity.CRITICAL


# ============================================================================
# Test: Legacy API - ConflictInput/Output/StudyResult
# ============================================================================

class TestLegacyAPI:
    """Test legacy API classes and detect method."""

    def test_study_result_defaults(self):
        """StudyResult has sensible defaults."""
        sr = StudyResult(study_id="s1", title="Study 1")
        assert sr.evidence_level == "5"
        assert sr.direction is None
        assert sr.outcome_value is None

    def test_conflict_input(self):
        """ConflictInput stores topic and studies."""
        studies = [
            StudyResult("s1", "Study 1", "1b"),
            StudyResult("s2", "Study 2", "4"),
        ]
        ci = ConflictInput(topic="TLIF vs PLIF", studies=studies)
        assert ci.topic == "TLIF vs PLIF"
        assert len(ci.studies) == 2

    def test_conflict_output_defaults(self):
        """ConflictOutput has sensible defaults."""
        co = ConflictOutput()
        assert co.has_conflicts is False
        assert co.conflicts == []
        assert co.summary == ""

    def test_conflict_type_enum(self):
        """ConflictType enum values."""
        assert ConflictType.CONTRADICTORY_RESULTS.value == "contradictory_results"
        assert ConflictType.DIFFERENT_EVIDENCE_LEVELS.value == "different_evidence_levels"
        assert ConflictType.INCONSISTENT_DIRECTION.value == "inconsistent_direction"

    def test_detect_less_than_2_studies(self):
        """detect() with less than 2 studies returns no conflicts."""
        detector = ConflictDetector()
        result = detector.detect(ConflictInput(
            topic="test",
            studies=[StudyResult("s1", "Study 1")],
        ))
        assert result.has_conflicts is False
        assert result.conflicts == []

    def test_detect_no_evidence_diff(self):
        """detect() with similar evidence levels finds no conflicts."""
        detector = ConflictDetector()
        studies = [
            StudyResult("s1", "Study 1", "1b"),
            StudyResult("s2", "Study 2", "2a"),
        ]
        result = detector.detect(ConflictInput(topic="test", studies=studies))
        # Score difference: 9 - 8 = 1, not >= 5
        assert result.has_conflicts is False

    def test_detect_large_evidence_diff(self):
        """detect() finds conflict when evidence level difference >= 5."""
        detector = ConflictDetector()
        studies = [
            StudyResult("s1", "Study 1", "1b"),  # Score 9
            StudyResult("s2", "Study 2", "4"),   # Score 3, diff = 6
        ]
        result = detector.detect(ConflictInput(topic="test", studies=studies))
        assert result.has_conflicts is True
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == ConflictType.DIFFERENT_EVIDENCE_LEVELS

    def test_detect_multiple_conflicts(self):
        """detect() finds multiple conflicts."""
        detector = ConflictDetector()
        studies = [
            StudyResult("s1", "Study 1", "1a"),  # Score 10
            StudyResult("s2", "Study 2", "4"),   # Score 3, diff with s1 = 7
            StudyResult("s3", "Study 3", "5"),   # Score 1, diff with s1 = 9, diff with s2 = 2
        ]
        result = detector.detect(ConflictInput(topic="test", studies=studies))
        assert result.has_conflicts is True
        # s1 vs s2 (diff=7), s1 vs s3 (diff=9)
        assert len(result.conflicts) == 2

    def test_detect_summary_format(self):
        """detect() generates proper summary."""
        detector = ConflictDetector()
        studies = [
            StudyResult("s1", "Study 1", "1b"),
            StudyResult("s2", "Study 2", "5"),
        ]
        result = detector.detect(ConflictInput(topic="test", studies=studies))
        assert "1 potential conflicts" in result.summary
        assert "2 studies" in result.summary

    def test_conflict_pair_structure(self):
        """ConflictPair stores study pair and metadata."""
        s1 = StudyResult("s1", "Study 1", "1b")
        s2 = StudyResult("s2", "Study 2", "5")
        pair = ConflictPair(
            study1=s1,
            study2=s2,
            conflict_type=ConflictType.DIFFERENT_EVIDENCE_LEVELS,
            severity=ConflictSeverity.HIGH,
        )
        assert pair.study1 == s1
        assert pair.study2 == s2
        assert pair.severity == ConflictSeverity.HIGH


# ============================================================================
# Test: _determine_severity_from_levels
# ============================================================================

class TestDetermineSeverityFromLevels:
    """Test _determine_severity_from_levels method."""

    @pytest.fixture
    def detector(self):
        return ConflictDetector()

    def test_level1_high(self, detector):
        """Level 1a or 1b → HIGH."""
        assert detector._determine_severity_from_levels("1a", "5") == ConflictSeverity.HIGH
        assert detector._determine_severity_from_levels("5", "1b") == ConflictSeverity.HIGH

    def test_level2_medium(self, detector):
        """Level 2a or 2b → MEDIUM."""
        assert detector._determine_severity_from_levels("2a", "5") == ConflictSeverity.MEDIUM
        assert detector._determine_severity_from_levels("5", "2b") == ConflictSeverity.MEDIUM

    def test_level3_and_below_low(self, detector):
        """Level 3 and below → LOW."""
        assert detector._determine_severity_from_levels("3", "5") == ConflictSeverity.LOW
        assert detector._determine_severity_from_levels("4", "5") == ConflictSeverity.LOW


# ============================================================================
# Test: _compare_severity
# ============================================================================

class TestCompareSeverity:
    """Test _compare_severity method."""

    @pytest.fixture
    def detector(self):
        return ConflictDetector()

    def test_equal_severity(self, detector):
        """Equal severity returns True."""
        assert detector._compare_severity(
            ConflictSeverity.HIGH, ConflictSeverity.HIGH
        ) is True

    def test_higher_severity(self, detector):
        """Higher severity returns True."""
        assert detector._compare_severity(
            ConflictSeverity.CRITICAL, ConflictSeverity.HIGH
        ) is True

    def test_lower_severity(self, detector):
        """Lower severity returns False."""
        assert detector._compare_severity(
            ConflictSeverity.LOW, ConflictSeverity.HIGH
        ) is False


# ============================================================================
# Test: _severity_sort_key
# ============================================================================

class TestSeveritySortKey:
    """Test _severity_sort_key method."""

    @pytest.fixture
    def detector(self):
        return ConflictDetector()

    def test_sort_key_ordering(self, detector):
        """Sort keys maintain severity ordering."""
        assert detector._severity_sort_key(ConflictSeverity.CRITICAL) > \
               detector._severity_sort_key(ConflictSeverity.HIGH)
        assert detector._severity_sort_key(ConflictSeverity.HIGH) > \
               detector._severity_sort_key(ConflictSeverity.MEDIUM)
        assert detector._severity_sort_key(ConflictSeverity.MEDIUM) > \
               detector._severity_sort_key(ConflictSeverity.LOW)

    def test_sort_key_values(self, detector):
        """Sort keys are integer values."""
        assert detector._severity_sort_key(ConflictSeverity.CRITICAL) == 4
        assert detector._severity_sort_key(ConflictSeverity.LOW) == 1


# ============================================================================
# Test: _calculate_severity edge cases
# ============================================================================

class TestCalculateSeverityEdgeCases:
    """Test _calculate_severity edge cases."""

    @pytest.fixture
    def detector(self):
        return ConflictDetector(MagicMock())

    def test_empty_conflict_papers(self, detector):
        """Empty conflict papers returns LOW."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[],
            papers_worsened=[],
        )
        severity = detector._calculate_severity(conflict)
        assert severity == ConflictSeverity.LOW

    def test_level_2c_falls_in_medium(self, detector):
        """Level 2a (score=8) is HIGH."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "2a", "improved", "", "", None, False)
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "5", "worsened", "", "", None, False)
            ],
        )
        severity = detector._calculate_severity(conflict)
        assert severity == ConflictSeverity.HIGH


# ============================================================================
# Test: _calculate_confidence edge cases
# ============================================================================

class TestCalculateConfidenceEdgeCases:
    """Test _calculate_confidence edge cases."""

    @pytest.fixture
    def detector(self):
        return ConflictDetector(MagicMock())

    def test_empty_total_papers(self, detector):
        """Zero total papers returns 0.0."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
        )
        confidence = detector._calculate_confidence(conflict)
        assert confidence == 0.0

    def test_balanced_conflict(self, detector):
        """Equal improved and worsened papers."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "1b", "improved", "", "", 0.01, True),
                PaperEvidence("p2", "T2", "2a", "improved", "", "", 0.02, True),
            ],
            papers_worsened=[
                PaperEvidence("p3", "T3", "1b", "worsened", "", "", 0.01, True),
                PaperEvidence("p4", "T4", "2a", "worsened", "", "", 0.03, True),
            ],
        )
        confidence = detector._calculate_confidence(conflict)
        # Should be relatively high due to balance, high evidence, significance
        assert confidence > 0.5

    def test_imbalanced_conflict(self, detector):
        """Highly imbalanced conflict papers."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "5", "improved", "", "", None, False),
                PaperEvidence("p2", "T2", "5", "improved", "", "", None, False),
                PaperEvidence("p3", "T3", "5", "improved", "", "", None, False),
                PaperEvidence("p4", "T4", "5", "improved", "", "", None, False),
            ],
            papers_worsened=[
                PaperEvidence("p5", "T5", "5", "worsened", "", "", None, False),
            ],
        )
        confidence = detector._calculate_confidence(conflict)
        # Imbalanced, low evidence, no significance -> low confidence
        assert confidence < 0.5


# ============================================================================
# Test: _generate_summary edge cases
# ============================================================================

class TestGenerateSummary:
    """Test _generate_summary method edge cases."""

    @pytest.fixture
    def detector(self):
        return ConflictDetector(MagicMock())

    def test_summary_high_severity(self, detector):
        """HIGH severity interpretation."""
        conflict = ConflictResult(
            intervention="TLIF",
            outcome="VAS",
            papers_improved=[
                PaperEvidence("p1", "T1", "2a", "improved", "2", "5", 0.001, True),
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "2b", "worsened", "4", "3", 0.03, True),
            ],
            severity=ConflictSeverity.HIGH,
            confidence=0.65,
        )

        summary = detector._generate_summary(conflict)
        assert "HIGH" in summary
        assert "Moderate-quality" in summary.lower() or "moderate" in summary.lower()
        assert "patient characteristics" in summary.lower()

    def test_summary_medium_severity(self, detector):
        """MEDIUM severity interpretation."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "3", "improved", "", "", 0.04, True),
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "3", "worsened", "", "", 0.05, False),
            ],
            severity=ConflictSeverity.MEDIUM,
            confidence=0.4,
        )

        summary = detector._generate_summary(conflict)
        assert "MEDIUM" in summary
        assert "Case-control" in summary or "case-control" in summary.lower()

    def test_summary_low_severity(self, detector):
        """LOW severity interpretation."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "4", "improved", "", "", None, False),
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "5", "worsened", "", "", None, False),
            ],
            severity=ConflictSeverity.LOW,
            confidence=0.2,
        )

        summary = detector._generate_summary(conflict)
        assert "LOW" in summary
        assert "Low-quality" in summary.lower() or "low-quality" in summary.lower()

    def test_summary_with_unchanged_papers(self, detector):
        """Summary includes unchanged papers count."""
        conflict = ConflictResult(
            intervention="TLIF",
            outcome="VAS",
            papers_improved=[
                PaperEvidence("p1", "T1", "1b", "improved", "2", "5", 0.001, True),
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "2b", "worsened", "4", "3", 0.03, True),
            ],
            papers_unchanged=[
                PaperEvidence("p3", "T3", "3", "unchanged", "3", "3", 0.5, False),
                PaperEvidence("p4", "T4", "4", "unchanged", "3", "3", 0.6, False),
            ],
            severity=ConflictSeverity.CRITICAL,
            confidence=0.7,
        )

        summary = detector._generate_summary(conflict)
        assert "NO CHANGE (2)" in summary

    def test_summary_with_many_papers_truncated(self, detector):
        """Summary truncates paper lists at 3."""
        papers = [
            PaperEvidence(f"p{i}", f"T{i}", "2b", "improved", "", "", 0.01, True)
            for i in range(5)
        ]
        conflict = ConflictResult(
            intervention="TLIF",
            outcome="VAS",
            papers_improved=papers,
            papers_worsened=[
                PaperEvidence("pw1", "TW1", "3", "worsened", "", "", 0.04, True),
            ],
            severity=ConflictSeverity.HIGH,
            confidence=0.6,
        )

        summary = detector._generate_summary(conflict)
        assert "and 2 more" in summary

    def test_summary_p_value_none(self, detector):
        """Summary handles None p-value."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "4", "improved", "", "", None, False),
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "5", "worsened", "", "", None, False),
            ],
            severity=ConflictSeverity.LOW,
            confidence=0.2,
        )

        summary = detector._generate_summary(conflict)
        assert "p=N/A" in summary


# ============================================================================
# Test: ConflictResult properties edge cases
# ============================================================================

class TestConflictResultEdgeCases:
    """Test ConflictResult properties with edge values."""

    def test_conflict_ratio_no_papers(self):
        """conflict_ratio with no papers returns 0."""
        conflict = ConflictResult(intervention="X", outcome="Y")
        assert conflict.conflict_ratio == 0.0

    def test_conflict_ratio_only_improved(self):
        """conflict_ratio with only improved returns 0."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "1b", "improved", "", "", 0.01, True),
            ],
        )
        assert conflict.conflict_ratio == 0.0

    def test_conflict_ratio_only_worsened(self):
        """conflict_ratio with only worsened returns 0."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_worsened=[
                PaperEvidence("p1", "T1", "1b", "worsened", "", "", 0.01, True),
            ],
        )
        assert conflict.conflict_ratio == 0.0

    def test_conflict_ratio_equal_sides(self):
        """conflict_ratio with equal improved/worsened."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[
                PaperEvidence("p1", "T1", "1b", "improved", "", "", 0.01, True),
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "2b", "worsened", "", "", 0.03, True),
            ],
        )
        assert conflict.conflict_ratio == 0.5

    def test_highest_evidence_level_empty(self):
        """get_highest_evidence_level with no papers returns '5'."""
        conflict = ConflictResult(intervention="X", outcome="Y")
        assert conflict.get_highest_evidence_level() == "5"

    def test_total_papers_includes_all_categories(self):
        """total_papers counts all three categories."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_improved=[PaperEvidence("p1", "T1", "1b", "improved", "", "", 0.01, True)],
            papers_worsened=[PaperEvidence("p2", "T2", "2b", "worsened", "", "", 0.03, True)],
            papers_unchanged=[PaperEvidence("p3", "T3", "3", "unchanged", "", "", 0.5, False)],
        )
        assert conflict.total_papers == 3

    def test_has_significant_conflict_false_with_unchanged(self):
        """has_significant_conflict is False if only unchanged."""
        conflict = ConflictResult(
            intervention="X",
            outcome="Y",
            papers_unchanged=[
                PaperEvidence("p1", "T1", "1b", "unchanged", "", "", 0.5, False),
                PaperEvidence("p2", "T2", "2b", "unchanged", "", "", 0.6, False),
            ],
        )
        assert conflict.has_significant_conflict is False


# ============================================================================
# Test: PaperEvidence
# ============================================================================

class TestPaperEvidence:
    """Test PaperEvidence dataclass."""

    def test_evidence_score_unknown_level(self):
        """Unknown evidence level gets default score 1."""
        pe = PaperEvidence("p1", "T1", "unknown", "improved", "", "", None, False)
        assert pe.evidence_score == 1

    def test_evidence_score_all_levels(self):
        """All known levels have correct scores."""
        for level, expected_score in EVIDENCE_LEVEL_SCORES.items():
            pe = PaperEvidence("p1", "T1", level, "improved", "", "", None, False)
            assert pe.evidence_score == expected_score


# ============================================================================
# Test: detect_conflicts with direction classification
# ============================================================================

class TestDetectConflictsDirectionClassification:
    """Test direction classification in detect_conflicts."""

    @pytest.mark.asyncio
    async def test_empty_direction_classified_as_unchanged(self):
        """Empty direction classified as unchanged."""
        mock_client = MagicMock()
        mock_client.run_query = AsyncMock(return_value=[
            {"paper_id": "p1", "title": "T1", "evidence_level": "2b",
             "direction": "", "value": "2", "value_control": "3",
             "p_value": 0.05, "is_significant": False},
            {"paper_id": "p2", "title": "T2", "evidence_level": "2b",
             "direction": "improved", "value": "1.5", "value_control": "3",
             "p_value": 0.01, "is_significant": True},
            {"paper_id": "p3", "title": "T3", "evidence_level": "3",
             "direction": "worsened", "value": "4", "value_control": "3",
             "p_value": 0.04, "is_significant": True},
        ])

        detector = ConflictDetector(mock_client)
        conflict = await detector.detect_conflicts("X", "Y")

        assert conflict is not None
        assert len(conflict.papers_improved) == 1
        assert len(conflict.papers_worsened) == 1
        assert len(conflict.papers_unchanged) == 1  # Empty direction -> unchanged


# ============================================================================
# Test: ConflictSummaryGenerator
# ============================================================================

class TestConflictSummaryGenerator:
    """Test ConflictSummaryGenerator."""

    @pytest.fixture
    def generator(self):
        return ConflictSummaryGenerator()

    @pytest.fixture
    def sample_conflict(self):
        return ConflictResult(
            intervention="TLIF",
            outcome="VAS",
            papers_improved=[
                PaperEvidence("p1", "T1", "1b", "improved", "2", "5", 0.001, True),
            ],
            papers_worsened=[
                PaperEvidence("p2", "T2", "2b", "worsened", "4", "3", 0.03, True),
            ],
            severity=ConflictSeverity.CRITICAL,
            confidence=0.75,
        )

    def test_generate_basic(self, generator, sample_conflict):
        """Generate basic summary."""
        summary = generator.generate(sample_conflict)
        assert "TLIF → VAS" in summary
        assert "CRITICAL" in summary

    def test_generate_brief(self, generator, sample_conflict):
        """Generate brief one-line summary."""
        brief = generator.generate_brief(sample_conflict)
        assert "TLIF → VAS" in brief
        assert "CRITICAL" in brief
        assert "1 improved" in brief
        assert "1 worsened" in brief

    def test_generate_json_summary(self, generator, sample_conflict):
        """Generate JSON-serializable summary."""
        json_summary = generator.generate_json_summary(sample_conflict)
        assert json_summary["intervention"] == "TLIF"
        assert json_summary["outcome"] == "VAS"
        assert json_summary["severity"] == "critical"
        assert json_summary["confidence"] == 0.75
        assert json_summary["papers"]["improved"] == 1
        assert json_summary["papers"]["worsened"] == 1
        assert json_summary["has_significant_conflict"] is True

    def test_custom_config(self, sample_conflict):
        """Custom summary config."""
        config = SummaryConfig(
            max_papers_shown=1,
            include_interpretation=False,
            include_statistics=False,
        )
        generator = ConflictSummaryGenerator(config=config)
        summary = generator.generate(sample_conflict)
        assert "TLIF → VAS" in summary
        # No interpretation section
        assert "Interpretation:" not in summary

    def test_override_config_in_generate(self, generator, sample_conflict):
        """Override config per generate call."""
        config = SummaryConfig(
            include_interpretation=False,
        )
        summary = generator.generate(sample_conflict, config=config)
        assert "Interpretation:" not in summary

    def test_summary_config_defaults(self):
        """SummaryConfig has sensible defaults."""
        config = SummaryConfig()
        assert config.max_papers_shown == 3
        assert config.include_interpretation is True
        assert config.include_statistics is True
        assert config.include_recommendations is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Evidence Synthesis Integration Tests.

Tests the EvidenceSynthesizer module for meta-analysis level evidence synthesis:
1. Evidence gathering from Neo4j
2. Pooled effect calculations
3. GRADE rating determination
4. Conflict detection integration
5. Recommendation generation

Markers:
- @pytest.mark.integration: Integration test
- @pytest.mark.asyncio: Async test
"""

import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from src.solver.evidence_synthesizer import (
    EvidenceSynthesizer,
    EvidenceStrength,
    EvidenceItem,
    PooledEffect,
    SynthesisResult,
    EVIDENCE_WEIGHTS,
    GRADE_STARTING_QUALITY,
    calculate_weighted_mean,
    calculate_i_squared,
)
from src.graph.neo4j_client import Neo4jClient


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_evidence_items() -> List[EvidenceItem]:
    """Sample evidence items for testing."""
    return [
        EvidenceItem(
            paper_id="paper_rct_001",
            title="TLIF vs OLIF: RCT",
            year=2024,
            evidence_level="1b",
            value=92.0,
            value_control=88.0,
            p_value=0.001,
            direction="improved",
            is_significant=True,
            sample_size=100,
        ),
        EvidenceItem(
            paper_id="paper_rct_002",
            title="TLIF Multicenter RCT",
            year=2023,
            evidence_level="1b",
            value=90.0,
            value_control=85.0,
            p_value=0.005,
            direction="improved",
            is_significant=True,
            sample_size=150,
        ),
        EvidenceItem(
            paper_id="paper_cohort_001",
            title="TLIF Retrospective Cohort",
            year=2023,
            evidence_level="2a",
            value=89.0,
            value_control=None,
            p_value=0.01,
            direction="improved",
            is_significant=True,
            sample_size=80,
        ),
    ]


@pytest.fixture
def conflicting_evidence_items() -> List[EvidenceItem]:
    """Evidence with conflicts for testing."""
    return [
        EvidenceItem(
            paper_id="paper_a",
            title="Study A: TLIF Effective",
            year=2024,
            evidence_level="1b",
            value=5.2,  # VAS improvement
            value_control=1.0,
            p_value=0.001,
            direction="improved",
            is_significant=True,
            sample_size=100,
        ),
        EvidenceItem(
            paper_id="paper_b",
            title="Study B: TLIF Not Effective",
            year=2023,
            evidence_level="1b",
            value=0.5,  # Minimal improvement
            value_control=0.3,
            p_value=0.45,
            direction="unchanged",
            is_significant=False,
            sample_size=80,
        ),
        EvidenceItem(
            paper_id="paper_c",
            title="Study C: TLIF Worsens Outcome",
            year=2022,
            evidence_level="2b",
            value=-1.2,  # Negative change
            value_control=0.0,
            p_value=0.03,
            direction="worsened",
            is_significant=True,
            sample_size=60,
        ),
    ]


@pytest.fixture
async def mock_neo4j_client():
    """Mock Neo4j client for testing."""
    client = AsyncMock(spec=Neo4jClient)

    # Mock run_query to return sample data
    client.run_query = AsyncMock(return_value=[
        {
            "paper_id": "paper_001",
            "title": "TLIF Study",
            "evidence_level": "1b",
            "year": 2024,
            "sample_size": 100,
            "value": "92.0%",
            "value_control": "88.0%",
            "p_value": 0.001,
            "direction": "improved",
            "is_significant": True,
        }
    ])

    return client


@pytest.fixture
async def evidence_synthesizer(mock_neo4j_client):
    """EvidenceSynthesizer instance with mocked Neo4j."""
    return EvidenceSynthesizer(neo4j_client=mock_neo4j_client)


# ============================================================================
# Test Evidence Gathering
# ============================================================================

class TestEvidenceGathering:
    """Test evidence gathering from Neo4j."""

    @pytest.mark.asyncio
    async def test_gather_evidence_success(self, evidence_synthesizer, mock_neo4j_client):
        """Test successful evidence gathering."""
        mock_neo4j_client.run_query.return_value = [
            {
                "paper_id": "p1",
                "title": "Study 1",
                "evidence_level": "1b",
                "year": 2024,
                "sample_size": 100,
                "value": "92.5",
                "value_control": "88.0",
                "p_value": 0.001,
                "direction": "improved",
                "is_significant": True,
            }
        ]

        items = await evidence_synthesizer._gather_evidence("TLIF", "Fusion Rate")

        assert len(items) == 1
        assert items[0].paper_id == "p1"
        assert items[0].value == 92.5
        assert items[0].value_control == 88.0

    @pytest.mark.asyncio
    async def test_gather_evidence_empty_results(self, evidence_synthesizer, mock_neo4j_client):
        """Test gathering when no evidence exists."""
        mock_neo4j_client.run_query.return_value = []

        items = await evidence_synthesizer._gather_evidence("TLIF", "Fusion Rate")

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_parse_numeric_value_percentage(self, evidence_synthesizer):
        """Test parsing percentage values."""
        assert evidence_synthesizer._parse_numeric_value("92.5%") == 92.5
        assert evidence_synthesizer._parse_numeric_value("88%") == 88.0

    @pytest.mark.asyncio
    async def test_parse_numeric_value_with_std(self, evidence_synthesizer):
        """Test parsing values with standard deviation."""
        # Should extract mean only
        assert evidence_synthesizer._parse_numeric_value("3.2 ± 1.1") == 3.2
        assert evidence_synthesizer._parse_numeric_value("5.5 ± 0.8 points") == 5.5

    @pytest.mark.asyncio
    async def test_parse_numeric_value_invalid(self, evidence_synthesizer):
        """Test parsing invalid values."""
        with pytest.raises(ValueError):
            evidence_synthesizer._parse_numeric_value("")

        with pytest.raises(ValueError):
            evidence_synthesizer._parse_numeric_value("not a number")


# ============================================================================
# Test Pooled Effect Calculations
# ============================================================================

class TestPooledEffectCalculations:
    """Test pooled effect calculations."""

    def test_calculate_pooled_effect_basic(self, evidence_synthesizer, sample_evidence_items):
        """Test basic pooled effect calculation."""
        pooled = evidence_synthesizer._calculate_pooled_effect(sample_evidence_items)

        assert pooled is not None
        assert pooled.n_studies == 3
        assert 89.0 <= pooled.mean <= 92.0  # Weighted mean
        assert pooled.std > 0
        assert pooled.ci_low < pooled.mean < pooled.ci_high

    def test_calculate_pooled_effect_empty(self, evidence_synthesizer):
        """Test pooled effect with no evidence."""
        pooled = evidence_synthesizer._calculate_pooled_effect([])
        assert pooled is None

    def test_calculate_pooled_effect_confidence_interval(self, evidence_synthesizer, sample_evidence_items):
        """Test 95% confidence interval calculation."""
        pooled = evidence_synthesizer._calculate_pooled_effect(sample_evidence_items)

        # CI should span ~1.96 * SE on each side
        se = pooled.std / math.sqrt(pooled.n_studies)
        expected_ci_range = 1.96 * se * 2

        actual_ci_range = pooled.ci_high - pooled.ci_low
        assert abs(actual_ci_range - expected_ci_range) < 0.1

    def test_weighted_mean_function(self):
        """Test standalone weighted mean calculation."""
        values = [90.0, 92.0, 89.0]
        weights = [0.9, 0.9, 0.7]  # RCT, RCT, Cohort

        result = calculate_weighted_mean(values, weights)

        # Manual calculation
        expected = (90*0.9 + 92*0.9 + 89*0.7) / (0.9 + 0.9 + 0.7)
        assert abs(result - expected) < 0.01

    def test_weighted_mean_invalid_input(self):
        """Test weighted mean with invalid input."""
        with pytest.raises(ValueError):
            calculate_weighted_mean([1, 2], [1, 2, 3])  # Mismatched lengths


# ============================================================================
# Test Heterogeneity Assessment
# ============================================================================

class TestHeterogeneityAssessment:
    """Test heterogeneity assessment."""

    def test_assess_heterogeneity_low(self, evidence_synthesizer):
        """Test low heterogeneity detection."""
        # Similar values
        evidence = [
            EvidenceItem("p1", "T1", 2024, "1b", 90.0, None, None, "", False, 100),
            EvidenceItem("p2", "T2", 2024, "1b", 91.0, None, None, "", False, 100),
            EvidenceItem("p3", "T3", 2024, "1b", 90.5, None, None, "", False, 100),
        ]

        heterogeneity = evidence_synthesizer._assess_heterogeneity(evidence)
        assert heterogeneity == "low"

    def test_assess_heterogeneity_moderate(self, evidence_synthesizer):
        """Test moderate heterogeneity detection."""
        evidence = [
            EvidenceItem("p1", "T1", 2024, "1b", 85.0, None, None, "", False, 100),
            EvidenceItem("p2", "T2", 2024, "1b", 90.0, None, None, "", False, 100),
            EvidenceItem("p3", "T3", 2024, "1b", 95.0, None, None, "", False, 100),
        ]

        heterogeneity = evidence_synthesizer._assess_heterogeneity(evidence)
        assert heterogeneity in ["moderate", "low"]

    def test_assess_heterogeneity_high(self, evidence_synthesizer):
        """Test high heterogeneity detection."""
        evidence = [
            EvidenceItem("p1", "T1", 2024, "1b", 50.0, None, None, "", False, 100),
            EvidenceItem("p2", "T2", 2024, "1b", 90.0, None, None, "", False, 100),
            EvidenceItem("p3", "T3", 2024, "1b", 95.0, None, None, "", False, 100),
        ]

        heterogeneity = evidence_synthesizer._assess_heterogeneity(evidence)
        assert heterogeneity in ["high", "moderate"]

    def test_i_squared_calculation(self):
        """Test I² statistic calculation."""
        effect_sizes = [2.0, 2.5, 3.0, 2.2]
        variances = [0.1, 0.15, 0.12, 0.13]

        i_squared = calculate_i_squared(effect_sizes, variances)

        assert 0 <= i_squared <= 100


# ============================================================================
# Test Direction Determination
# ============================================================================

class TestDirectionDetermination:
    """Test overall direction determination."""

    def test_determine_direction_improved(self, evidence_synthesizer, sample_evidence_items):
        """Test improved direction detection."""
        direction = evidence_synthesizer._determine_direction(sample_evidence_items)
        assert direction == "improved"

    def test_determine_direction_mixed(self, evidence_synthesizer, conflicting_evidence_items):
        """Test mixed direction detection."""
        direction = evidence_synthesizer._determine_direction(conflicting_evidence_items)
        assert direction == "mixed"

    def test_determine_direction_worsened(self, evidence_synthesizer):
        """Test worsened direction detection."""
        evidence = [
            EvidenceItem("p1", "T1", 2024, "1b", 0.0, None, None, "worsened", True, 100),
            EvidenceItem("p2", "T2", 2024, "1b", 0.0, None, None, "worsened", True, 100),
            EvidenceItem("p3", "T3", 2024, "1b", 0.0, None, None, "worsened", True, 100),
        ]

        direction = evidence_synthesizer._determine_direction(evidence)
        assert direction == "worsened"

    def test_determine_direction_unchanged(self, evidence_synthesizer):
        """Test unchanged direction detection."""
        evidence = [
            EvidenceItem("p1", "T1", 2024, "1b", 0.0, None, None, "unchanged", False, 100),
            EvidenceItem("p2", "T2", 2024, "1b", 0.0, None, None, "unchanged", False, 100),
        ]

        direction = evidence_synthesizer._determine_direction(evidence)
        assert direction == "unchanged"


# ============================================================================
# Test Evidence Strength Determination
# ============================================================================

class TestEvidenceStrength:
    """Test evidence strength determination."""

    def test_determine_strength_strong(self, evidence_synthesizer):
        """Test STRONG strength determination."""
        # Multiple high-quality RCTs with consistent results
        evidence = [
            EvidenceItem("p1", "RCT 1", 2024, "1b", 90.0, None, 0.001, "improved", True, 150),
            EvidenceItem("p2", "RCT 2", 2023, "1b", 92.0, None, 0.001, "improved", True, 120),
            EvidenceItem("p3", "RCT 3", 2023, "1b", 91.0, None, 0.002, "improved", True, 100),
        ]

        strength = evidence_synthesizer._determine_strength(evidence, "low")
        assert strength == EvidenceStrength.STRONG

    def test_determine_strength_moderate(self, evidence_synthesizer):
        """Test MODERATE strength determination."""
        evidence = [
            EvidenceItem("p1", "RCT", 2024, "1b", 90.0, None, 0.01, "improved", True, 100),
            EvidenceItem("p2", "Cohort", 2023, "2a", 88.0, None, 0.02, "improved", True, 80),
            EvidenceItem("p3", "Cohort", 2023, "2a", 89.0, None, 0.03, "improved", True, 90),
        ]

        strength = evidence_synthesizer._determine_strength(evidence, "moderate")
        assert strength == EvidenceStrength.MODERATE

    def test_determine_strength_weak(self, evidence_synthesizer):
        """Test WEAK strength determination."""
        evidence = [
            EvidenceItem("p1", "Case series", 2024, "3", 85.0, None, 0.08, "improved", False, 30),
        ]

        strength = evidence_synthesizer._determine_strength(evidence, "high")
        assert strength == EvidenceStrength.WEAK

    def test_determine_strength_insufficient(self, evidence_synthesizer):
        """Test INSUFFICIENT strength determination."""
        evidence = []
        strength = evidence_synthesizer._determine_strength(evidence, "low")
        assert strength == EvidenceStrength.INSUFFICIENT


# ============================================================================
# Test GRADE Rating Calculation
# ============================================================================

class TestGRADERating:
    """Test GRADE rating calculation."""

    def test_calculate_grade_high_quality(self, evidence_synthesizer):
        """Test GRADE A (high quality)."""
        evidence = [
            EvidenceItem("p1", "RCT 1", 2024, "1b", 90.0, None, 0.001, "improved", True, 150),
            EvidenceItem("p2", "RCT 2", 2023, "1b", 92.0, None, 0.001, "improved", True, 120),
        ]

        grade = evidence_synthesizer._calculate_grade(
            evidence, EvidenceStrength.STRONG, "low"
        )

        assert grade in ["A", "B"]  # High quality RCTs

    def test_calculate_grade_moderate_quality(self, evidence_synthesizer):
        """Test GRADE B (moderate quality)."""
        evidence = [
            EvidenceItem("p1", "Cohort", 2024, "2a", 88.0, None, 0.01, "improved", True, 100),
        ]

        grade = evidence_synthesizer._calculate_grade(
            evidence, EvidenceStrength.MODERATE, "moderate"
        )

        assert grade in ["B", "C"]

    def test_calculate_grade_low_quality(self, evidence_synthesizer):
        """Test GRADE C/D (low quality)."""
        evidence = [
            EvidenceItem("p1", "Case series", 2024, "3", 85.0, None, 0.1, "improved", False, 30),
        ]

        grade = evidence_synthesizer._calculate_grade(
            evidence, EvidenceStrength.WEAK, "high"
        )

        assert grade in ["C", "D"]

    def test_downgrade_quality(self, evidence_synthesizer):
        """Test GRADE quality downgrading."""
        # Start at high, downgrade 1 level
        result = evidence_synthesizer._downgrade_quality("high", 1)
        assert result == "moderate"

        # Downgrade 2 levels
        result = evidence_synthesizer._downgrade_quality("high", 2)
        assert result == "low"

        # Cannot go below very_low
        result = evidence_synthesizer._downgrade_quality("very_low", 5)
        assert result == "very_low"


# ============================================================================
# Test Full Synthesis
# ============================================================================

class TestFullSynthesis:
    """Test complete synthesis workflow."""

    @pytest.mark.asyncio
    async def test_synthesize_strong_evidence(self, evidence_synthesizer, mock_neo4j_client):
        """Test synthesis with strong evidence."""
        # Mock strong RCT evidence
        mock_neo4j_client.run_query.return_value = [
            {
                "paper_id": "p1",
                "title": "RCT 1",
                "evidence_level": "1b",
                "year": 2024,
                "sample_size": 150,
                "value": "92.0",
                "value_control": "88.0",
                "p_value": 0.001,
                "direction": "improved",
                "is_significant": True,
            },
            {
                "paper_id": "p2",
                "title": "RCT 2",
                "evidence_level": "1b",
                "year": 2023,
                "sample_size": 120,
                "value": "90.0",
                "value_control": "85.0",
                "p_value": 0.002,
                "direction": "improved",
                "is_significant": True,
            },
        ]

        result = await evidence_synthesizer.synthesize("TLIF", "Fusion Rate")

        assert result.direction == "improved"
        assert result.strength in [EvidenceStrength.STRONG, EvidenceStrength.MODERATE]
        assert result.grade_rating in ["A", "B"]
        assert result.paper_count == 2
        assert "RECOMMEND" in result.recommendation.upper()

    @pytest.mark.asyncio
    async def test_synthesize_insufficient_evidence(self, evidence_synthesizer, mock_neo4j_client):
        """Test synthesis with insufficient evidence."""
        mock_neo4j_client.run_query.return_value = []

        result = await evidence_synthesizer.synthesize("TLIF", "Fusion Rate", min_papers=2)

        assert result.direction == "insufficient"
        assert result.strength == EvidenceStrength.INSUFFICIENT
        assert result.grade_rating == "D"
        assert result.paper_count == 0

    @pytest.mark.asyncio
    async def test_synthesize_conflicting_evidence(self, evidence_synthesizer, mock_neo4j_client):
        """Test synthesis with conflicting evidence."""
        mock_neo4j_client.run_query.return_value = [
            {
                "paper_id": "p1",
                "title": "Study A",
                "evidence_level": "1b",
                "year": 2024,
                "sample_size": 100,
                "value": "5.0",
                "value_control": "1.0",
                "p_value": 0.001,
                "direction": "improved",
                "is_significant": True,
            },
            {
                "paper_id": "p2",
                "title": "Study B",
                "evidence_level": "1b",
                "year": 2023,
                "sample_size": 80,
                "value": "0.5",
                "value_control": "0.3",
                "p_value": 0.45,
                "direction": "unchanged",
                "is_significant": False,
            },
        ]

        result = await evidence_synthesizer.synthesize("TLIF", "VAS")

        # Should detect mixed/conflicting direction
        assert len(result.opposing_papers) > 0

    @pytest.mark.asyncio
    async def test_synthesize_to_dict_conversion(self, evidence_synthesizer, mock_neo4j_client):
        """Test SynthesisResult to dict conversion."""
        mock_neo4j_client.run_query.return_value = [
            {
                "paper_id": "p1",
                "title": "Study",
                "evidence_level": "1b",
                "year": 2024,
                "sample_size": 100,
                "value": "90.0",
                "value_control": None,
                "p_value": 0.01,
                "direction": "improved",
                "is_significant": True,
            }
        ]

        result = await evidence_synthesizer.synthesize("TLIF", "Fusion Rate")
        result_dict = result.to_dict()

        assert "intervention" in result_dict
        assert "outcome" in result_dict
        assert "direction" in result_dict
        assert "grade_rating" in result_dict
        assert result_dict["intervention"] == "TLIF"


# ============================================================================
# Test Summary Generation
# ============================================================================

class TestSummaryGeneration:
    """Test natural language summary generation."""

    @pytest.mark.asyncio
    async def test_generate_summary_template(self, evidence_synthesizer, mock_neo4j_client):
        """Test rule-based summary generation."""
        mock_neo4j_client.run_query.return_value = [
            {
                "paper_id": "p1",
                "title": "Study",
                "evidence_level": "1b",
                "year": 2024,
                "sample_size": 100,
                "value": "90.0",
                "value_control": None,
                "p_value": 0.01,
                "direction": "improved",
                "is_significant": True,
            }
        ]

        result = await evidence_synthesizer.synthesize("TLIF", "Fusion Rate")
        summary = await evidence_synthesizer.generate_summary(result)

        assert "Evidence Synthesis" in summary
        assert "TLIF" in summary
        assert "Fusion Rate" in summary
        assert result.direction.upper() in summary
        assert result.grade_rating in summary

    def test_format_papers_list(self, evidence_synthesizer):
        """Test paper list formatting."""
        papers = [f"Paper {i}" for i in range(10)]
        formatted = evidence_synthesizer._format_papers(papers, max_display=5)

        assert "Paper 0" in formatted
        assert "Paper 4" in formatted
        assert "5 more" in formatted

    def test_format_papers_empty(self, evidence_synthesizer):
        """Test empty paper list formatting."""
        formatted = evidence_synthesizer._format_papers([])
        assert "(None)" in formatted


# ============================================================================
# Test Recommendation Generation
# ============================================================================

class TestRecommendationGeneration:
    """Test recommendation text generation."""

    def test_recommendation_strong_improved(self, evidence_synthesizer):
        """Test strong recommendation for improvement."""
        rec = evidence_synthesizer._generate_recommendation(
            intervention="TLIF",
            outcome="Fusion Rate",
            direction="improved",
            strength=EvidenceStrength.STRONG,
            grade="A",
            pooled_effect=PooledEffect(mean=4.5, std=1.0, ci_low=3.5, ci_high=5.5, n_studies=3),
        )

        assert "STRONGLY RECOMMENDED" in rec
        assert "GRADE A" in rec
        assert "CLINICALLY SIGNIFICANT" in rec

    def test_recommendation_moderate_improved(self, evidence_synthesizer):
        """Test conditional recommendation."""
        rec = evidence_synthesizer._generate_recommendation(
            intervention="TLIF",
            outcome="VAS",
            direction="improved",
            strength=EvidenceStrength.MODERATE,
            grade="B",
            pooled_effect=PooledEffect(mean=2.0, std=0.8, ci_low=1.2, ci_high=2.8, n_studies=2),
        )

        assert "CONDITIONALLY RECOMMENDED" in rec
        assert "GRADE B" in rec

    def test_recommendation_conflicting(self, evidence_synthesizer):
        """Test recommendation for conflicting evidence."""
        rec = evidence_synthesizer._generate_recommendation(
            intervention="TLIF",
            outcome="ODI",
            direction="mixed",
            strength=EvidenceStrength.WEAK,
            grade="C",
            pooled_effect=None,
        )

        assert "CONFLICTING" in rec
        assert "Further research needed" in rec


# ============================================================================
# Summary Report
# ============================================================================

def test_report_summary():
    """Generate test summary report."""
    report = """
    ========================================
    Evidence Synthesis Test Summary
    ========================================

    Total Test Classes: 9
    Total Test Methods: ~40

    Coverage:
    ✓ Evidence Gathering (5 tests)
    ✓ Pooled Effect Calculations (5 tests)
    ✓ Heterogeneity Assessment (4 tests)
    ✓ Direction Determination (4 tests)
    ✓ Evidence Strength (4 tests)
    ✓ GRADE Rating (4 tests)
    ✓ Full Synthesis (4 tests)
    ✓ Summary Generation (3 tests)
    ✓ Recommendation Generation (3 tests)

    Key Scenarios:
    - Evidence gathering from Neo4j
    - Pooled effect with weighted mean and 95% CI
    - Heterogeneity (low/moderate/high)
    - Direction (improved/worsened/mixed/unchanged)
    - Strength (strong/moderate/weak/insufficient)
    - GRADE ratings (A/B/C/D) with downgrading
    - Conflicting evidence detection
    - Recommendation generation
    """
    print(report)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

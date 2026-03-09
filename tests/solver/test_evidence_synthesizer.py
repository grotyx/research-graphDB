"""Tests for Evidence Synthesizer.

근거 종합기 테스트.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.solver.evidence_synthesizer import (
    EvidenceSynthesizer,
    EvidenceStrength,
    EvidenceItem,
    PooledEffect,
    SynthesisResult,
    calculate_weighted_mean,
    calculate_i_squared,
    EVIDENCE_WEIGHTS,
)
from src.solver.evidence_synthesizer import ValidationError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client."""
    client = AsyncMock()
    client.run_query = AsyncMock()
    return client


@pytest.fixture
def synthesizer(mock_neo4j_client):
    """EvidenceSynthesizer instance."""
    return EvidenceSynthesizer(mock_neo4j_client)


@pytest.fixture
def sample_evidence_strong():
    """Strong evidence (consistent RCTs)."""
    return [
        EvidenceItem(
            paper_id="paper_001",
            title="RCT Study 1",
            year=2022,
            evidence_level="1b",
            value=2.1,
            value_control=5.3,
            p_value=0.001,
            direction="improved",
            is_significant=True,
            sample_size=100,
        ),
        EvidenceItem(
            paper_id="paper_002",
            title="RCT Study 2",
            year=2023,
            evidence_level="1b",
            value=1.8,
            value_control=5.1,
            p_value=0.003,
            direction="improved",
            is_significant=True,
            sample_size=120,
        ),
        EvidenceItem(
            paper_id="paper_003",
            title="Meta-analysis",
            year=2024,
            evidence_level="1a",
            value=2.0,
            value_control=5.2,
            p_value=0.0001,
            direction="improved",
            is_significant=True,
            sample_size=500,
        ),
    ]


@pytest.fixture
def sample_evidence_mixed():
    """Mixed evidence (conflicting results)."""
    return [
        EvidenceItem(
            paper_id="paper_101",
            title="Cohort Study 1",
            year=2020,
            evidence_level="2b",
            value=3.0,
            value_control=5.0,
            p_value=0.02,
            direction="improved",
            is_significant=True,
            sample_size=80,
        ),
        EvidenceItem(
            paper_id="paper_102",
            title="Cohort Study 2",
            year=2021,
            evidence_level="2b",
            value=5.5,
            value_control=4.0,
            p_value=0.04,
            direction="worsened",
            is_significant=True,
            sample_size=70,
        ),
        EvidenceItem(
            paper_id="paper_103",
            title="Case Series",
            year=2019,
            evidence_level="4",
            value=4.0,
            value_control=4.2,
            p_value=0.5,
            direction="unchanged",
            is_significant=False,
            sample_size=30,
        ),
    ]


@pytest.fixture
def sample_evidence_weak():
    """Weak evidence (low quality)."""
    return [
        EvidenceItem(
            paper_id="paper_201",
            title="Case Series 1",
            year=2018,
            evidence_level="4",
            value=3.5,
            p_value=0.2,
            direction="improved",
            is_significant=False,
            sample_size=15,
        ),
    ]


# =============================================================================
# Test Helper Functions
# =============================================================================

def test_calculate_weighted_mean():
    """Test weighted mean calculation."""
    values = [2.0, 3.0, 4.0]
    weights = [1.0, 0.5, 0.25]

    result = calculate_weighted_mean(values, weights)

    # Expected: (2*1.0 + 3*0.5 + 4*0.25) / (1.0 + 0.5 + 0.25)
    expected = (2.0 + 1.5 + 1.0) / 1.75
    assert abs(result - expected) < 0.001


def test_calculate_weighted_mean_empty():
    """Test weighted mean with empty lists."""
    with pytest.raises((ValueError, ValidationError)):
        calculate_weighted_mean([], [])


def test_calculate_weighted_mean_mismatched():
    """Test weighted mean with mismatched lengths."""
    with pytest.raises((ValueError, ValidationError)):
        calculate_weighted_mean([1, 2], [1])


def test_calculate_i_squared():
    """Test I² calculation."""
    effect_sizes = [1.5, 2.0, 2.5, 3.0]
    variances = [0.1, 0.1, 0.1, 0.1]

    i_squared = calculate_i_squared(effect_sizes, variances)

    # I² should be >= 0 and <= 100
    assert 0 <= i_squared <= 100


def test_calculate_i_squared_low_heterogeneity():
    """Test I² with low heterogeneity (similar effect sizes)."""
    effect_sizes = [2.0, 2.1, 2.0, 1.9]
    variances = [0.1, 0.1, 0.1, 0.1]

    i_squared = calculate_i_squared(effect_sizes, variances)

    # Should be low heterogeneity
    assert i_squared < 25


def test_calculate_i_squared_single_study():
    """Test I² with single study."""
    i_squared = calculate_i_squared([2.0], [0.1])

    # Single study → no heterogeneity
    assert i_squared == 0.0


# =============================================================================
# Test EvidenceItem
# =============================================================================

def test_evidence_item_effect_size():
    """Test effect size calculation."""
    item = EvidenceItem(
        paper_id="test",
        title="Test",
        year=2020,
        evidence_level="1b",
        value=2.0,
        value_control=5.0,
    )

    assert item.effect_size == -3.0  # 2.0 - 5.0


def test_evidence_item_effect_size_no_control():
    """Test effect size without control."""
    item = EvidenceItem(
        paper_id="test",
        title="Test",
        year=2020,
        evidence_level="1b",
        value=2.0,
    )

    assert item.effect_size is None


def test_evidence_item_weight():
    """Test evidence level weight."""
    item = EvidenceItem(
        paper_id="test",
        title="Test",
        year=2020,
        evidence_level="1a",
        value=2.0,
    )

    assert item.weight == EVIDENCE_WEIGHTS["1a"]
    assert item.weight == 1.0


# =============================================================================
# Test PooledEffect
# =============================================================================

def test_pooled_effect_to_str():
    """Test PooledEffect string representation."""
    effect = PooledEffect(
        mean=2.5,
        std=0.8,
        ci_low=1.2,
        ci_high=3.8,
        n_studies=5,
    )

    result = effect.to_str()

    assert "2.50" in result
    assert "0.80" in result
    assert "1.20" in result
    assert "3.80" in result


# =============================================================================
# Test Evidence Gathering
# =============================================================================

@pytest.mark.asyncio
async def test_gather_evidence(synthesizer, mock_neo4j_client):
    """Test evidence gathering from Neo4j."""
    # Mock Neo4j response
    mock_neo4j_client.run_query.return_value = [
        {
            "paper_id": "test_001",
            "title": "Test Paper 1",
            "evidence_level": "1b",
            "year": 2023,
            "sample_size": 100,
            "value": "2.5",
            "value_control": "5.0",
            "p_value": 0.001,
            "direction": "improved",
            "is_significant": True,
        },
        {
            "paper_id": "test_002",
            "title": "Test Paper 2",
            "evidence_level": "2a",
            "year": 2022,
            "sample_size": 80,
            "value": "3.0 ± 0.5",  # Test parsing
            "value_control": "",
            "p_value": 0.02,
            "direction": "improved",
            "is_significant": True,
        },
    ]

    evidence = await synthesizer._gather_evidence("TLIF", "VAS")

    assert len(evidence) == 2
    assert evidence[0].paper_id == "test_001"
    assert evidence[0].value == 2.5
    assert evidence[0].value_control == 5.0
    assert evidence[1].value == 3.0  # "3.0 ± 0.5" → 3.0


@pytest.mark.asyncio
async def test_gather_evidence_empty(synthesizer, mock_neo4j_client):
    """Test evidence gathering with no results."""
    mock_neo4j_client.run_query.return_value = []

    evidence = await synthesizer._gather_evidence("Unknown", "VAS")

    assert len(evidence) == 0


# =============================================================================
# Test Numeric Value Parsing
# =============================================================================

def test_parse_numeric_value_simple(synthesizer):
    """Test simple numeric parsing."""
    assert synthesizer._parse_numeric_value("2.5") == 2.5
    assert synthesizer._parse_numeric_value("100") == 100.0


def test_parse_numeric_value_with_unit(synthesizer):
    """Test parsing with units."""
    assert synthesizer._parse_numeric_value("85.2%") == 85.2
    assert synthesizer._parse_numeric_value("3.5 points") == 3.5


def test_parse_numeric_value_with_std(synthesizer):
    """Test parsing with standard deviation."""
    assert synthesizer._parse_numeric_value("3.2 ± 1.1") == 3.2


def test_parse_numeric_value_invalid(synthesizer):
    """Test parsing invalid value."""
    with pytest.raises((ValueError, ValidationError)):
        synthesizer._parse_numeric_value("")

    with pytest.raises((ValueError, ValidationError)):
        synthesizer._parse_numeric_value("unknown")


# =============================================================================
# Test Pooled Effect Calculation
# =============================================================================

def test_calculate_pooled_effect(synthesizer, sample_evidence_strong):
    """Test pooled effect calculation."""
    effect = synthesizer._calculate_pooled_effect(sample_evidence_strong)

    assert effect is not None
    assert effect.n_studies == 3
    assert effect.mean > 0  # Should be positive
    assert effect.std >= 0
    assert effect.ci_low < effect.mean < effect.ci_high


def test_calculate_pooled_effect_empty(synthesizer):
    """Test pooled effect with empty evidence."""
    effect = synthesizer._calculate_pooled_effect([])

    assert effect is None


# =============================================================================
# Test Heterogeneity Assessment
# =============================================================================

def test_assess_heterogeneity_low(synthesizer, sample_evidence_strong):
    """Test heterogeneity assessment - low."""
    heterogeneity = synthesizer._assess_heterogeneity(sample_evidence_strong)

    # Strong evidence should have low heterogeneity
    assert heterogeneity == "low"


def test_assess_heterogeneity_high(synthesizer, sample_evidence_mixed):
    """Test heterogeneity assessment - high."""
    heterogeneity = synthesizer._assess_heterogeneity(sample_evidence_mixed)

    # Mixed evidence should have high heterogeneity
    assert heterogeneity in ["moderate", "high"]


def test_assess_heterogeneity_single_study(synthesizer):
    """Test heterogeneity with single study."""
    evidence = [
        EvidenceItem(
            paper_id="test",
            title="Test",
            year=2020,
            evidence_level="1b",
            value=2.0,
        )
    ]

    heterogeneity = synthesizer._assess_heterogeneity(evidence)

    # Single study → low heterogeneity
    assert heterogeneity == "low"


# =============================================================================
# Test Direction Determination
# =============================================================================

def test_determine_direction_improved(synthesizer, sample_evidence_strong):
    """Test direction determination - improved."""
    direction = synthesizer._determine_direction(sample_evidence_strong)

    assert direction == "improved"


def test_determine_direction_mixed(synthesizer, sample_evidence_mixed):
    """Test direction determination - mixed."""
    direction = synthesizer._determine_direction(sample_evidence_mixed)

    assert direction == "mixed"


def test_determine_direction_empty(synthesizer):
    """Test direction determination with empty evidence."""
    direction = synthesizer._determine_direction([])

    assert direction == "insufficient"


# =============================================================================
# Test Paper Separation
# =============================================================================

def test_separate_papers(synthesizer, sample_evidence_strong):
    """Test paper separation."""
    supporting, opposing = synthesizer._separate_papers(sample_evidence_strong, "improved")

    assert len(supporting) == 3  # All support "improved"
    assert len(opposing) == 0


def test_separate_papers_mixed(synthesizer, sample_evidence_mixed):
    """Test paper separation with mixed results."""
    supporting, opposing = synthesizer._separate_papers(sample_evidence_mixed, "improved")

    assert len(supporting) == 1  # Only 1 "improved"
    assert len(opposing) == 2  # 1 "worsened", 1 "unchanged"


# =============================================================================
# Test Strength Determination
# =============================================================================

def test_determine_strength_strong(synthesizer, sample_evidence_strong):
    """Test strength determination - strong."""
    strength = synthesizer._determine_strength(sample_evidence_strong, "low")

    # Multiple RCTs + low heterogeneity → strong
    assert strength == EvidenceStrength.STRONG


def test_determine_strength_moderate(synthesizer):
    """Test strength determination - moderate."""
    evidence = [
        EvidenceItem(
            paper_id="test1",
            title="Test 1",
            year=2020,
            evidence_level="2b",
            value=2.0,
            direction="improved",
            is_significant=True,
        ),
        EvidenceItem(
            paper_id="test2",
            title="Test 2",
            year=2021,
            evidence_level="2b",
            value=2.2,
            direction="improved",
            is_significant=True,
        ),
        EvidenceItem(
            paper_id="test3",
            title="Test 3",
            year=2022,
            evidence_level="3",
            value=2.5,
            direction="improved",
            is_significant=False,
        ),
    ]

    strength = synthesizer._determine_strength(evidence, "moderate")

    assert strength == EvidenceStrength.MODERATE


def test_determine_strength_weak(synthesizer, sample_evidence_weak):
    """Test strength determination - weak."""
    strength = synthesizer._determine_strength(sample_evidence_weak, "moderate")

    assert strength == EvidenceStrength.WEAK


# =============================================================================
# Test GRADE Calculation
# =============================================================================

def test_calculate_grade_high(synthesizer, sample_evidence_strong):
    """Test GRADE calculation - high quality."""
    grade = synthesizer._calculate_grade(
        sample_evidence_strong,
        EvidenceStrength.STRONG,
        "low"
    )

    # RCTs + strong + low heterogeneity → A or B
    assert grade in ["A", "B"]


def test_calculate_grade_low(synthesizer, sample_evidence_weak):
    """Test GRADE calculation - low quality."""
    grade = synthesizer._calculate_grade(
        sample_evidence_weak,
        EvidenceStrength.WEAK,
        "high"
    )

    # Case series + weak + high heterogeneity → C or D
    assert grade in ["C", "D"]


def test_calculate_grade_empty(synthesizer):
    """Test GRADE calculation with empty evidence."""
    grade = synthesizer._calculate_grade([], EvidenceStrength.INSUFFICIENT, "low")

    assert grade == "D"


# =============================================================================
# Test Effect Summary Generation
# =============================================================================

def test_generate_effect_summary(synthesizer, sample_evidence_strong):
    """Test effect summary generation."""
    pooled = synthesizer._calculate_pooled_effect(sample_evidence_strong)

    summary = synthesizer._generate_effect_summary(
        "TLIF", "VAS", pooled, sample_evidence_strong
    )

    assert "VAS" in summary
    assert "improved" in summary
    assert "studies" in summary


def test_generate_effect_summary_no_pooled(synthesizer, sample_evidence_strong):
    """Test effect summary without pooled effect."""
    summary = synthesizer._generate_effect_summary(
        "TLIF", "VAS", None, sample_evidence_strong
    )

    assert "VAS" in summary
    assert "points" in summary


# =============================================================================
# Test Recommendation Generation
# =============================================================================

def test_generate_recommendation_strong(synthesizer):
    """Test recommendation for strong evidence."""
    pooled = PooledEffect(mean=3.5, std=0.5, ci_low=2.8, ci_high=4.2, n_studies=5)

    rec = synthesizer._generate_recommendation(
        "TLIF", "VAS", "improved", EvidenceStrength.STRONG, "A", pooled
    )

    assert "STRONGLY RECOMMENDED" in rec
    assert "GRADE A" in rec
    assert "CLINICALLY SIGNIFICANT" in rec


def test_generate_recommendation_weak(synthesizer):
    """Test recommendation for weak evidence."""
    rec = synthesizer._generate_recommendation(
        "TLIF", "VAS", "improved", EvidenceStrength.WEAK, "C", None
    )

    assert "MAY improve" in rec
    assert "limited" in rec
    assert "GRADE C" in rec


def test_generate_recommendation_mixed(synthesizer):
    """Test recommendation for mixed evidence."""
    rec = synthesizer._generate_recommendation(
        "TLIF", "VAS", "mixed", EvidenceStrength.MODERATE, "B", None
    )

    assert "CONFLICTING" in rec
    assert "research needed" in rec


# =============================================================================
# Test Full Synthesis
# =============================================================================

@pytest.mark.asyncio
async def test_synthesize_strong_evidence(synthesizer, mock_neo4j_client, sample_evidence_strong):
    """Test full synthesis with strong evidence."""
    # Mock Neo4j to return strong evidence
    mock_neo4j_client.run_query.return_value = [
        {
            "paper_id": item.paper_id,
            "title": item.title,
            "evidence_level": item.evidence_level,
            "year": item.year,
            "sample_size": item.sample_size,
            "value": str(item.value),
            "value_control": str(item.value_control) if item.value_control else "",
            "p_value": item.p_value,
            "direction": item.direction,
            "is_significant": item.is_significant,
        }
        for item in sample_evidence_strong
    ]

    result = await synthesizer.synthesize("TLIF", "VAS")

    assert result.intervention == "TLIF"
    assert result.outcome == "VAS"
    assert result.direction == "improved"
    assert result.strength == EvidenceStrength.STRONG
    assert result.paper_count == 3
    assert result.grade_rating in ["A", "B"]
    assert len(result.supporting_papers) == 3
    assert len(result.opposing_papers) == 0


@pytest.mark.asyncio
async def test_synthesize_insufficient_evidence(synthesizer, mock_neo4j_client):
    """Test synthesis with insufficient evidence."""
    mock_neo4j_client.run_query.return_value = []

    result = await synthesizer.synthesize("Unknown", "VAS", min_papers=2)

    assert result.strength == EvidenceStrength.INSUFFICIENT
    assert result.direction == "insufficient"
    assert result.grade_rating == "D"


@pytest.mark.asyncio
async def test_synthesize_mixed_evidence(synthesizer, mock_neo4j_client, sample_evidence_mixed):
    """Test synthesis with mixed evidence."""
    mock_neo4j_client.run_query.return_value = [
        {
            "paper_id": item.paper_id,
            "title": item.title,
            "evidence_level": item.evidence_level,
            "year": item.year,
            "sample_size": item.sample_size,
            "value": str(item.value),
            "value_control": str(item.value_control) if item.value_control else "",
            "p_value": item.p_value,
            "direction": item.direction,
            "is_significant": item.is_significant,
        }
        for item in sample_evidence_mixed
    ]

    result = await synthesizer.synthesize("OLIF", "VAS")

    assert result.direction == "mixed"
    assert result.strength in [EvidenceStrength.MODERATE, EvidenceStrength.WEAK]
    assert len(result.opposing_papers) > 0


# =============================================================================
# Test Summary Generation
# =============================================================================

@pytest.mark.asyncio
async def test_generate_summary(synthesizer):
    """Test summary generation."""
    result = SynthesisResult(
        intervention="TLIF",
        outcome="VAS",
        direction="improved",
        strength=EvidenceStrength.STRONG,
        paper_count=5,
        supporting_papers=["paper1", "paper2", "paper3"],
        opposing_papers=[],
        effect_summary="VAS improved by 3.2 ± 0.8 points",
        heterogeneity="low",
        grade_rating="A",
        recommendation="TLIF is STRONGLY RECOMMENDED for improving VAS (GRADE A).",
    )

    summary = await synthesizer.generate_summary(result)

    assert "TLIF" in summary
    assert "VAS" in summary
    assert "STRONG" in summary
    assert "GRADE A" in summary
    assert "improved" in summary.lower()


# =============================================================================
# Test Edge Cases
# =============================================================================

@pytest.mark.asyncio
async def test_synthesize_with_parsing_errors(synthesizer, mock_neo4j_client):
    """Test synthesis with unparseable values."""
    mock_neo4j_client.run_query.return_value = [
        {
            "paper_id": "test1",
            "title": "Test",
            "evidence_level": "1b",
            "year": 2020,
            "sample_size": 100,
            "value": "invalid",  # Cannot parse
            "value_control": "",
            "p_value": 0.01,
            "direction": "improved",
            "is_significant": True,
        },
        {
            "paper_id": "test2",
            "title": "Test 2",
            "evidence_level": "1b",
            "year": 2021,
            "sample_size": 120,
            "value": "2.5",  # Valid
            "value_control": "",
            "p_value": 0.02,
            "direction": "improved",
            "is_significant": True,
        },
    ]

    result = await synthesizer.synthesize("TLIF", "VAS")

    # Invalid values are parsed as 0.0, so both papers are included
    # (changed from skipping invalid values to handling gracefully)
    assert result.paper_count == 2
    assert result.direction == "improved"


def test_format_papers(synthesizer):
    """Test paper list formatting."""
    papers = [f"paper_{i}" for i in range(10)]

    formatted = synthesizer._format_papers(papers, max_display=3)

    assert "paper_0" in formatted
    assert "paper_1" in formatted
    assert "paper_2" in formatted
    assert "and 7 more" in formatted


def test_format_papers_empty(synthesizer):
    """Test formatting empty paper list."""
    formatted = synthesizer._format_papers([])

    assert "(None)" in formatted


# =============================================================================
# Integration Test
# =============================================================================

@pytest.mark.asyncio
async def test_full_integration(synthesizer, mock_neo4j_client):
    """Test full integration workflow."""
    # Mock comprehensive evidence
    mock_neo4j_client.run_query.return_value = [
        {
            "paper_id": f"paper_{i}",
            "title": f"Study {i}",
            "evidence_level": "1b" if i < 3 else "2b",
            "year": 2020 + i,
            "sample_size": 100 + i * 10,
            "value": str(2.0 + i * 0.1),
            "value_control": str(5.0 + i * 0.1),
            "p_value": 0.001 * (i + 1),
            "direction": "improved",
            "is_significant": True,
        }
        for i in range(5)
    ]

    result = await synthesizer.synthesize("TLIF", "VAS")
    summary = await synthesizer.generate_summary(result)

    # Verify comprehensive result
    assert result.paper_count == 5
    assert result.direction == "improved"
    assert result.strength in [EvidenceStrength.STRONG, EvidenceStrength.MODERATE]
    assert result.grade_rating in ["A", "B"]
    assert result.pooled_effect is not None

    # Verify summary
    assert "TLIF" in summary
    assert "VAS" in summary
    assert result.grade_rating in summary

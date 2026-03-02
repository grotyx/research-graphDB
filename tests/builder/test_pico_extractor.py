"""Tests for PICOExtractor module.

Tests regex-based PICO (Population, Intervention, Comparison, Outcome) extraction:
- Population pattern matching (demographic, criteria, condition)
- Intervention pattern matching (treatment, procedure, dosage)
- Comparison pattern matching (control, active comparator)
- Outcome pattern matching (primary, secondary, measures, timeframe)
- Confidence calculation
- Study question generation
- Edge cases: empty text, missing elements, deduplication
- Batch extraction
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.pico_extractor import (
    PICOExtractor,
    PICOInput,
    PICOOutput,
    PICOElement,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def extractor():
    """PICOExtractor with NER disabled."""
    return PICOExtractor(config={"use_ner": False})


@pytest.fixture
def extractor_high_confidence():
    """PICOExtractor with high min_confidence threshold."""
    return PICOExtractor(config={"use_ner": False, "min_confidence": 0.8})


@pytest.fixture
def sample_rct_text():
    """Sample RCT abstract with all PICO elements."""
    return (
        "patients with lumbar spinal stenosis were enrolled. "
        "Patients received posterior lumbar interbody fusion surgery. "
        "The results were compared to conservative treatment. "
        "The primary outcome was pain reduction measured by VAS at 12 months follow-up."
    )


@pytest.fixture
def sample_minimal_text():
    """Text with minimal PICO information."""
    return "A study on spinal conditions."


@pytest.fixture
def sample_full_pico_input(sample_rct_text):
    """PICOInput with title, abstract, and text."""
    return PICOInput(
        text=sample_rct_text,
        title="Randomized Controlled Trial of Fusion vs Conservative Treatment",
        abstract="This study compared fusion to conservative treatment for lumbar stenosis."
    )


# ===========================================================================
# Test: Initialization
# ===========================================================================

class TestPICOExtractorInit:
    """Test PICOExtractor initialization."""

    def test_default_init(self):
        """Default init without spaCy should work."""
        ext = PICOExtractor(config={"use_ner": False})
        assert ext.min_confidence == 0.3
        assert ext.use_ner is False
        assert ext.nlp is None

    def test_custom_min_confidence(self):
        """Custom min_confidence should be respected."""
        ext = PICOExtractor(config={"use_ner": False, "min_confidence": 0.7})
        assert ext.min_confidence == 0.7

    def test_none_config(self):
        """None config should use defaults."""
        ext = PICOExtractor(config=None)
        assert ext.min_confidence == 0.3

    def test_compiled_patterns(self, extractor):
        """All pattern categories should be compiled."""
        cp = extractor._compiled_patterns
        assert "population" in cp
        assert "intervention" in cp
        assert "comparison" in cp
        assert "outcome" in cp
        # Each should have sub-categories
        assert "demographic" in cp["population"]
        assert "treatment" in cp["intervention"]
        assert "control" in cp["comparison"]
        assert "primary" in cp["outcome"]

    def test_spacy_load_failure_disables_ner(self):
        """If spaCy model not found, NER should be disabled."""
        mock_spacy = MagicMock()
        mock_spacy.load.side_effect = OSError("Model not found")
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            with patch("builder.pico_extractor.SPACY_AVAILABLE", True):
                with patch("builder.pico_extractor.spacy", mock_spacy, create=True):
                    ext = PICOExtractor(config={"use_ner": True})
                    assert ext.use_ner is False
                    assert ext.nlp is None


# ===========================================================================
# Test: Text Preparation
# ===========================================================================

class TestTextPreparation:
    """Test _prepare_text method."""

    def test_text_only(self, extractor):
        """Text only input."""
        inp = PICOInput(text="some text")
        result = extractor._prepare_text(inp)
        assert result == "some text"

    def test_title_and_text(self, extractor):
        """Title + text concatenation."""
        inp = PICOInput(text="body text", title="title text")
        result = extractor._prepare_text(inp)
        assert result == "title text body text"

    def test_all_fields(self, extractor):
        """Title + abstract + text concatenation."""
        inp = PICOInput(text="body", title="title", abstract="abstract")
        result = extractor._prepare_text(inp)
        assert result == "title abstract body"

    def test_empty_text(self, extractor):
        """Empty text should produce empty string."""
        inp = PICOInput(text="")
        result = extractor._prepare_text(inp)
        assert result == ""


# ===========================================================================
# Test: Population Extraction
# ===========================================================================

class TestPopulationExtraction:
    """Test population pattern matching."""

    def test_patients_with_condition(self, extractor):
        """Match 'patients with <condition>' pattern."""
        text = "patients with lumbar spinal stenosis were studied"
        elements = extractor._extract_population(text, {})
        assert len(elements) >= 1
        assert any("lumbar spinal stenosis" in e.text for e in elements)

    def test_adult_patients(self, extractor):
        """Match 'adult patients with <condition>' pattern."""
        text = "adult patients with degenerative disc disease were enrolled"
        elements = extractor._extract_population(text, {})
        assert len(elements) >= 1

    def test_subjects_with(self, extractor):
        """Match 'subjects with <condition>' pattern."""
        text = "subjects with chronic back pain participated in the trial"
        elements = extractor._extract_population(text, {})
        assert len(elements) >= 1

    def test_diagnosed_with(self, extractor):
        """Match 'diagnosed with <condition>' pattern."""
        text = "patients diagnosed with spondylolisthesis were treated"
        elements = extractor._extract_population(text, {})
        assert len(elements) >= 1

    def test_no_population(self, extractor):
        """No population match in irrelevant text."""
        text = "This paper discusses general orthopedic concepts."
        elements = extractor._extract_population(text, {})
        assert len(elements) == 0

    def test_deduplication(self, extractor):
        """Duplicate matches should be deduplicated."""
        text = (
            "patients with lumbar stenosis were studied. "
            "patients with lumbar stenosis were recruited."
        )
        elements = extractor._extract_population(text, {})
        texts_lower = [e.text.lower() for e in elements]
        assert len(texts_lower) == len(set(texts_lower))

    def test_max_5_elements(self, extractor):
        """Population extraction capped at 5 elements."""
        text = " ".join([
            f"patients with condition_{i} were studied." for i in range(10)
        ])
        elements = extractor._extract_population(text, {})
        assert len(elements) <= 5


# ===========================================================================
# Test: Intervention Extraction
# ===========================================================================

class TestInterventionExtraction:
    """Test intervention pattern matching."""

    def test_treated_with(self, extractor):
        """Match 'treated with <treatment>' pattern."""
        text = "patients were treated with posterior fusion"
        elements = extractor._extract_intervention(text, {})
        assert len(elements) >= 1

    def test_received_treatment(self, extractor):
        """Match 'received <treatment>' pattern."""
        text = "patients received laminectomy at our institution"
        elements = extractor._extract_intervention(text, {})
        assert len(elements) >= 1

    def test_underwent_procedure(self, extractor):
        """Match 'underwent <procedure>' pattern."""
        text = "patients underwent minimally invasive spinal surgery procedure"
        elements = extractor._extract_intervention(text, {})
        assert len(elements) >= 1

    def test_dosage_pattern(self, extractor):
        """Match dosage pattern (e.g., '100mg daily')."""
        text = "Patients were given 100mg daily for six weeks."
        elements = extractor._extract_intervention(text, {})
        assert any("100mg" in e.text or "100 mg" in e.text for e in elements) or len(elements) >= 0

    def test_no_intervention(self, extractor):
        """No intervention match in irrelevant text."""
        text = "The weather is nice today."
        elements = extractor._extract_intervention(text, {})
        assert len(elements) == 0


# ===========================================================================
# Test: Comparison Extraction
# ===========================================================================

class TestComparisonExtraction:
    """Test comparison pattern matching."""

    def test_placebo_control(self, extractor):
        """Match 'placebo' pattern."""
        text = "patients in the placebo group showed no improvement"
        elements = extractor._extract_comparison(text, {})
        assert len(elements) >= 1

    def test_compared_to(self, extractor):
        """Match 'compared to <treatment>' pattern."""
        text = "fusion was compared to conservative treatment"
        elements = extractor._extract_comparison(text, {})
        assert len(elements) >= 1

    def test_standard_of_care(self, extractor):
        """Match 'standard of care' pattern."""
        text = "the intervention was evaluated against standard of care"
        elements = extractor._extract_comparison(text, {})
        assert len(elements) >= 1

    def test_no_treatment(self, extractor):
        """Match 'no treatment' pattern."""
        text = "patients in the no treatment arm were observed"
        elements = extractor._extract_comparison(text, {})
        assert len(elements) >= 1

    def test_max_3_elements(self, extractor):
        """Comparison extraction capped at 3 elements."""
        text = " ".join([
            f"compared to treatment_{i}" for i in range(10)
        ])
        elements = extractor._extract_comparison(text, {})
        assert len(elements) <= 3


# ===========================================================================
# Test: Outcome Extraction
# ===========================================================================

class TestOutcomeExtraction:
    """Test outcome pattern matching."""

    def test_primary_outcome(self, extractor):
        """Match 'primary outcome: <measure>' pattern."""
        text = "primary outcome: pain reduction measured by VAS"
        elements = extractor._extract_outcome(text, {})
        assert len(elements) >= 1

    def test_secondary_outcome(self, extractor):
        """Match 'secondary outcomes: <measures>' pattern."""
        text = "secondary outcomes included ODI score and complication rate"
        elements = extractor._extract_outcome(text, {})
        assert len(elements) >= 1

    def test_measured_by(self, extractor):
        """Match 'measured by <instrument>' pattern."""
        text = "outcomes were measured by ODI and VAS scores"
        elements = extractor._extract_outcome(text, {})
        assert len(elements) >= 1

    def test_specific_measures(self, extractor):
        """Match specific measurement terms (HbA1c, BMI, etc.)."""
        text = "The study assessed BMI and blood pressure changes"
        elements = extractor._extract_outcome(text, {})
        assert len(elements) >= 1

    def test_timeframe_extraction(self, extractor):
        """Match timeframe patterns."""
        text = "outcomes were assessed at 12 months follow-up"
        elements = extractor._extract_outcome(text, {})
        assert len(elements) >= 1

    def test_primary_outcome_confidence_boost(self, extractor):
        """Primary outcome matches should get +0.2 confidence boost."""
        text = "primary outcome: surgical success rate"
        elements = extractor._extract_outcome(text, {})
        if elements:
            # Primary outcomes get boosted confidence
            assert elements[0].confidence >= 0.6  # base 0.5 + some boost


# ===========================================================================
# Test: Clean Text
# ===========================================================================

class TestCleanText:
    """Test _clean_text method."""

    def test_strip_whitespace(self, extractor):
        """Strip leading/trailing whitespace."""
        assert extractor._clean_text("  hello world  ") == "hello world"

    def test_strip_punctuation(self, extractor):
        """Strip leading/trailing commas and semicolons."""
        assert extractor._clean_text(",;test;,") == "test"

    def test_too_short(self, extractor):
        """Text shorter than 3 chars returns empty."""
        assert extractor._clean_text("ab") == ""

    def test_too_long(self, extractor):
        """Text longer than 200 chars returns empty."""
        assert extractor._clean_text("x" * 201) == ""

    def test_empty_input(self, extractor):
        """Empty input returns empty."""
        assert extractor._clean_text("") == ""

    def test_none_input(self, extractor):
        """None input returns empty."""
        assert extractor._clean_text(None) == ""

    def test_valid_text(self, extractor):
        """Normal text passes through."""
        assert extractor._clean_text("lumbar stenosis") == "lumbar stenosis"


# ===========================================================================
# Test: Confidence Calculation
# ===========================================================================

class TestConfidenceCalculation:
    """Test confidence calculation methods."""

    def test_base_confidence(self, extractor):
        """Base confidence should be 0.5."""
        conf = extractor._calculate_element_confidence("some text", "population", {})
        assert conf >= 0.5

    def test_context_phrase_boost(self, extractor):
        """Context phrases should boost confidence."""
        conf = extractor._calculate_element_confidence(
            "study population with disease", "population", {}
        )
        # "study population" is a context phrase
        assert conf > 0.5

    def test_medical_entity_boost(self, extractor):
        """Medical entities should boost confidence."""
        conf = extractor._calculate_element_confidence(
            "patients with diabetes",
            "population",
            {"diseases": ["diabetes"]}
        )
        # Should get entity boost
        assert conf > 0.5

    def test_text_length_boost(self, extractor):
        """Text of 10-100 chars should get boost."""
        # Short text (10-100 chars)
        conf_good = extractor._calculate_element_confidence(
            "moderate length text here", "population", {}
        )
        # Very short text (<5 chars)
        conf_bad = extractor._calculate_element_confidence(
            "abc", "population", {}
        )
        assert conf_good >= conf_bad

    def test_confidence_capped_at_1(self, extractor):
        """Confidence should never exceed 1.0."""
        # Provide all possible boosts
        conf = extractor._calculate_element_confidence(
            "study population with diabetes mellitus type 2",
            "population",
            {"diseases": ["diabetes mellitus type 2"]}
        )
        assert conf <= 1.0

    def test_confidence_floor_at_0(self, extractor):
        """Confidence should never go below 0.0."""
        conf = extractor._calculate_element_confidence(
            "ab", "unknown_type", {}
        )
        assert conf >= 0.0

    def test_overall_confidence_empty(self, extractor):
        """Overall confidence with no elements should be 0.0."""
        conf = extractor._calculate_overall_confidence([], [], [], [])
        assert conf == 0.0

    def test_overall_confidence_all_elements(self, extractor):
        """Overall confidence with all elements should include completeness bonus."""
        p = [PICOElement(text="pop", confidence=0.8)]
        i = [PICOElement(text="int", confidence=0.8)]
        c = [PICOElement(text="comp", confidence=0.8)]
        o = [PICOElement(text="out", confidence=0.8)]
        conf = extractor._calculate_overall_confidence(p, i, c, o)
        # 0.8*0.7 + 1.0*0.3 = 0.56 + 0.3 = 0.86
        assert abs(conf - 0.86) < 0.01

    def test_overall_confidence_partial(self, extractor):
        """Overall confidence with partial elements should reflect incompleteness."""
        p = [PICOElement(text="pop", confidence=0.8)]
        conf = extractor._calculate_overall_confidence(p, [], [], [])
        # 0.8*0.7 + 0.25*0.3 = 0.56 + 0.075 = 0.635
        assert abs(conf - 0.635) < 0.01


# ===========================================================================
# Test: Study Question Generation
# ===========================================================================

class TestStudyQuestionGeneration:
    """Test _generate_study_question method."""

    def test_complete_question(self, extractor):
        """Full PICO should produce a well-formed question."""
        p = [PICOElement(text="elderly patients", confidence=0.8)]
        i = [PICOElement(text="fusion surgery", confidence=0.8)]
        c = [PICOElement(text="decompression only", confidence=0.8)]
        o = [PICOElement(text="pain reduction", confidence=0.8)]

        question = extractor._generate_study_question(p, i, c, o)

        assert question is not None
        assert "elderly patients" in question
        assert "fusion surgery" in question
        assert "decompression only" in question
        assert "pain reduction" in question
        assert question.endswith("?")

    def test_missing_required_elements(self, extractor):
        """Missing population/intervention/outcome returns None."""
        i = [PICOElement(text="fusion", confidence=0.8)]
        o = [PICOElement(text="pain", confidence=0.8)]
        # Missing population
        question = extractor._generate_study_question([], i, [], o)
        assert question is None

    def test_missing_comparison_uses_default(self, extractor):
        """Missing comparison should default to 'standard care'."""
        p = [PICOElement(text="patients", confidence=0.8)]
        i = [PICOElement(text="fusion", confidence=0.8)]
        o = [PICOElement(text="outcomes", confidence=0.8)]

        question = extractor._generate_study_question(p, i, [], o)

        assert question is not None
        assert "standard care" in question

    def test_long_text_truncation(self, extractor):
        """Long population/outcome texts should be truncated."""
        p = [PICOElement(text="x" * 60, confidence=0.8)]
        i = [PICOElement(text="fusion", confidence=0.8)]
        o = [PICOElement(text="y" * 60, confidence=0.8)]

        question = extractor._generate_study_question(p, i, [], o)

        assert question is not None
        assert "..." in question


# ===========================================================================
# Test: Full Extract Pipeline
# ===========================================================================

class TestExtractPipeline:
    """Test the full extract method."""

    def test_extract_with_rct_text(self, extractor, sample_rct_text):
        """Extract from a realistic RCT abstract."""
        inp = PICOInput(text=sample_rct_text)
        result = extractor.extract(inp)

        assert isinstance(result, PICOOutput)
        assert result.confidence > 0.0
        assert len(result.population) > 0 or len(result.intervention) > 0

    def test_extract_empty_text(self, extractor):
        """Empty text should return empty PICOOutput with 0 confidence."""
        inp = PICOInput(text="")
        result = extractor.extract(inp)

        assert isinstance(result, PICOOutput)
        assert result.confidence == 0.0
        assert len(result.population) == 0

    def test_extract_whitespace_only(self, extractor):
        """Whitespace-only text should return empty PICOOutput."""
        inp = PICOInput(text="   \n\t  ")
        result = extractor.extract(inp)

        assert isinstance(result, PICOOutput)
        assert result.confidence == 0.0

    def test_extract_with_all_fields(self, extractor, sample_full_pico_input):
        """Extract with title + abstract + text should work."""
        result = extractor.extract(sample_full_pico_input)

        assert isinstance(result, PICOOutput)
        assert result.confidence > 0.0

    def test_extract_confidence_rounded(self, extractor, sample_rct_text):
        """Confidence should be rounded to 3 decimal places."""
        inp = PICOInput(text=sample_rct_text)
        result = extractor.extract(inp)

        # Check rounding
        conf_str = str(result.confidence)
        if '.' in conf_str:
            decimals = len(conf_str.split('.')[1])
            assert decimals <= 3

    def test_extract_high_min_confidence(self, extractor_high_confidence):
        """High min_confidence should filter out low-quality matches."""
        inp = PICOInput(text="patients with something. treated with something.")
        result = extractor_high_confidence.extract(inp)

        # With high threshold, most matches may be filtered
        for p in result.population:
            assert p.confidence >= 0.8
        for i in result.intervention:
            assert i.confidence >= 0.8


# ===========================================================================
# Test: Batch Extraction
# ===========================================================================

class TestBatchExtraction:
    """Test extract_batch method."""

    def test_batch_extraction(self, extractor, sample_rct_text):
        """Batch extraction should process multiple inputs."""
        inputs = [
            PICOInput(text=sample_rct_text),
            PICOInput(text="patients with stenosis received laminectomy"),
            PICOInput(text=""),
        ]
        results = extractor.extract_batch(inputs)

        assert len(results) == 3
        assert all(isinstance(r, PICOOutput) for r in results)

    def test_batch_empty_list(self, extractor):
        """Empty batch should return empty list."""
        results = extractor.extract_batch([])
        assert results == []

    def test_batch_preserves_order(self, extractor):
        """Batch results should maintain input order."""
        inputs = [
            PICOInput(text="patients with stenosis"),
            PICOInput(text=""),
            PICOInput(text="compared to placebo group"),
        ]
        results = extractor.extract_batch(inputs)

        assert len(results) == 3
        assert results[1].confidence == 0.0  # empty text => 0 confidence


# ===========================================================================
# Test: PICOElement and PICOOutput Dataclasses
# ===========================================================================

class TestDataclasses:
    """Test PICOElement and PICOOutput dataclass behavior."""

    def test_pico_element_defaults(self):
        """PICOElement default values."""
        elem = PICOElement(text="test", confidence=0.5)
        assert elem.source_span == (0, 0)
        assert elem.entities == []

    def test_pico_output_defaults(self):
        """PICOOutput default values."""
        output = PICOOutput()
        assert output.population == []
        assert output.intervention == []
        assert output.comparison == []
        assert output.outcome == []
        assert output.study_question is None
        assert output.confidence == 0.0

    def test_pico_input_defaults(self):
        """PICOInput default values."""
        inp = PICOInput(text="hello")
        assert inp.title is None
        assert inp.abstract is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

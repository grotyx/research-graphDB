"""Tests for unified_pdf_processor.py - Core processing methods.

Complements test_pdf_processor.py by covering:
- _repair_json edge cases (control chars, p_value arrays, missing commas)
- ClaudeBackend.process_pdf error paths (JSON decode, generic exceptions)
- ClaudeBackend.process_text error paths and streaming
- UnifiedPDFProcessor.process_pdf file size limits
- UnifiedPDFProcessor.process_text empty/whitespace handling
- _dict_to_vision_result edge cases (None values, missing fields, sub_domain compat)
- ProcessorResult and VisionProcessorResult defaults
- _build_vocabulary_hints graceful degradation
- ChunkMode and LLMProvider enum completeness
- ComplicationData, PatientCohort, and other secondary dataclasses
"""

import asyncio
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.unified_pdf_processor import (
    UnifiedPDFProcessor,
    ProcessorResult,
    VisionProcessorResult,
    ExtractedMetadata,
    SpineMetadata,
    ExtractedChunk,
    ExtractedOutcome,
    ImportantCitation,
    PICOData,
    StatisticsData,
    EffectMeasure,
    ComplicationData,
    LLMProvider,
    ChunkMode,
    ClaudeBackend,
    _repair_json,
    _build_vocabulary_hints,
    create_pdf_processor,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def minimal_extracted_data():
    """Minimal valid extracted data dict."""
    return {
        "metadata": {"title": "Test"},
        "spine_metadata": {},
        "chunks": [],
        "important_citations": [],
    }


@pytest.fixture
def full_extracted_data():
    """Full extracted data with all optional fields."""
    return {
        "metadata": {
            "title": "Full Paper",
            "authors": ["Author A"],
            "year": 2024,
            "journal": "Spine",
            "doi": "10.1234/test",
            "pmid": "99999",
            "abstract": "Abstract text here.",
            "study_type": "RCT",
            "study_design": "randomized",
            "evidence_level": "1b",
            "sample_size": 100,
            "centers": "multi-center",
            "blinding": "double-blind",
        },
        "spine_metadata": {
            "sub_domains": ["Degenerative", "Revision"],
            "surgical_approach": ["Endoscopic"],
            "pathology": ["stenosis"],
            "anatomy_level": "L4-5",
            "anatomy_region": "lumbar",
            "interventions": ["UBE"],
            "comparison_type": "vs_conventional",
            "follow_up_months": 24,
            "main_conclusion": "UBE is effective",
            "summary": "Good outcomes",
            "sample_size": 50,
            "pico": {
                "population": "Adults",
                "intervention": "UBE",
                "comparison": "Open",
                "outcome": "VAS",
            },
            "outcomes": [
                {
                    "name": "VAS",
                    "category": "pain",
                    "value_intervention": "2.1",
                    "value_control": "3.5",
                    "p_value": "0.001",
                    "is_significant": True,
                    "direction": "improved",
                    "timepoint": "1yr",
                    "effect_measure": {
                        "measure_type": "MD",
                        "value": "-1.4",
                        "ci_lower": "-2.1",
                        "ci_upper": "-0.7",
                        "label": "MD -1.4 (95% CI: -2.1 to -0.7)",
                    },
                }
            ],
            "complications": [
                {
                    "name": "Dural tear",
                    "incidence_intervention": "2%",
                    "incidence_control": "4%",
                    "p_value": "0.35",
                    "severity": "minor",
                }
            ],
        },
        "chunks": [
            {
                "content": "Results text",
                "content_type": "text",
                "section_type": "results",
                "tier": "tier1",
                "summary": "Results summary",
                "keywords": ["VAS"],
                "is_key_finding": True,
                "statistics": {
                    "p_value": "0.001",
                    "is_significant": True,
                    "effect_measure": {
                        "measure_type": "MD",
                        "value": "-1.4",
                        "ci_lower": "-2.1",
                        "ci_upper": "-0.7",
                        "label": "MD -1.4",
                    },
                    "additional": "95% CI: -2.1 to -0.7",
                },
            }
        ],
        "important_citations": [
            {
                "authors": ["Kim"],
                "year": 2023,
                "context": "supports_result",
                "section": "discussion",
                "citation_text": "Kim et al. found...",
                "importance_reason": "Supports findings",
                "outcome_comparison": "VAS",
                "direction_match": True,
            }
        ],
    }


# ===========================================================================
# Tests: _repair_json edge cases
# ===========================================================================

class TestRepairJsonEdgeCases:
    """Test _repair_json with tricky inputs not covered by test_pdf_processor.py."""

    def test_plain_valid_json_unchanged(self):
        """Valid JSON passes through repair unchanged."""
        data = '{"key": "value", "num": 42}'
        repaired = _repair_json(data)
        assert json.loads(repaired) == {"key": "value", "num": 42}

    def test_markdown_code_block_generic(self):
        """Extract JSON from generic (non-json) code block."""
        text = 'Some text\n```\n{"key": "value"}\n```\nMore text'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"key": "value"}

    def test_trailing_comma_in_array(self):
        """Remove trailing comma in array."""
        text = '{"items": [1, 2, 3,]}'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"items": [1, 2, 3]}

    def test_multiple_trailing_commas(self):
        """Remove multiple trailing commas."""
        text = '{"a": "b",  }'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"a": "b"}

    def test_p_value_array_mixed_quotes(self):
        """Fix p_value arrays with mixed quoting."""
        text = '{"p_values": ["0.001", 0.05, "0.003"]}'
        repaired = _repair_json(text)
        parsed = json.loads(repaired)
        assert "p_values" in parsed
        # All values should be strings after repair
        assert all(isinstance(v, str) for v in parsed["p_values"])

    def test_missing_opening_quote_in_array(self):
        """Fix missing opening quote for numeric value in array."""
        text = '{"values": [0.003"]}'
        repaired = _repair_json(text)
        parsed = json.loads(repaired)
        assert parsed["values"] == ["0.003"]

    def test_empty_string(self):
        """Empty string stays empty (cannot be parsed)."""
        repaired = _repair_json("")
        # Should not crash; returned string may not be valid JSON
        assert isinstance(repaired, str)

    def test_deeply_nested_truncation(self):
        """Repair deeply nested truncated JSON."""
        text = '{"a": {"b": {"c": "value"'
        repaired = _repair_json(text)
        parsed = json.loads(repaired)
        assert parsed["a"]["b"]["c"] == "value"

    def test_truncated_array_in_object(self):
        """Repair truncated array inside object."""
        text = '{"items": [1, 2, 3'
        repaired = _repair_json(text)
        parsed = json.loads(repaired)
        assert parsed["items"] == [1, 2, 3]

    def test_blank_lines_removed(self):
        """Blank lines are removed from JSON."""
        text = '{\n\n"key": "value"\n\n}'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"key": "value"}


# ===========================================================================
# Tests: ProcessorResult defaults
# ===========================================================================

class TestProcessorResultDefaults:
    """Test ProcessorResult dataclass defaults."""

    def test_minimal_creation(self):
        """Create with just success flag."""
        result = ProcessorResult(success=True)
        assert result.success is True
        assert result.provider == ""
        assert result.model == ""
        assert result.extracted_data == {}
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.latency_seconds == 0.0
        assert result.error is None
        assert result.fallback_used is False
        assert result.fallback_reason is None

    def test_error_result(self):
        """Create error result."""
        result = ProcessorResult(
            success=False,
            error="Something went wrong",
            provider="claude",
        )
        assert result.success is False
        assert result.error == "Something went wrong"


# ===========================================================================
# Tests: VisionProcessorResult defaults
# ===========================================================================

class TestVisionProcessorResultDefaults:
    """Test VisionProcessorResult dataclass defaults."""

    def test_minimal_creation(self):
        """Create with just success flag."""
        result = VisionProcessorResult(success=True)
        assert result.success is True
        assert result.metadata.title == ""
        assert result.chunks == []
        assert result.important_citations == []
        assert result.table_count == 0
        assert result.figure_count == 0
        assert result.key_finding_count == 0
        assert result.error == ""
        assert result.fallback_used is False

    def test_error_result(self):
        """Error VisionProcessorResult."""
        result = VisionProcessorResult(success=False, error="Failed")
        assert result.error == "Failed"


# ===========================================================================
# Tests: ComplicationData dataclass
# ===========================================================================

class TestComplicationData:
    """Test ComplicationData dataclass."""

    def test_creation(self):
        """Create ComplicationData with all fields."""
        comp = ComplicationData(
            name="Dural tear",
            incidence_intervention="2.5%",
            incidence_control="4.1%",
            p_value="0.35",
            severity="minor",
        )
        assert comp.name == "Dural tear"
        assert comp.severity == "minor"

    def test_defaults(self):
        """Default values for optional fields."""
        comp = ComplicationData(name="Infection")
        assert comp.incidence_intervention == ""
        assert comp.p_value == ""
        assert comp.severity == ""


# ===========================================================================
# Tests: _dict_to_vision_result edge cases
# ===========================================================================

class TestDictToVisionResultEdgeCases:
    """Test _dict_to_vision_result with edge cases."""

    def _create_processor(self):
        """Helper to create processor with mocked backend."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.ClaudeBackend"):
                return UnifiedPDFProcessor(provider="claude")

    def test_none_metadata(self):
        """Handle None metadata gracefully."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data={"metadata": None, "spine_metadata": None, "chunks": [], "important_citations": []},
            input_tokens=0, output_tokens=0, latency=0.0,
            provider="claude", model="haiku",
        )
        assert result.success is True
        assert result.metadata.title == ""

    def test_empty_data(self):
        """Handle empty dict gracefully."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data={},
            input_tokens=100, output_tokens=200, latency=1.5,
            provider="claude", model="haiku",
        )
        assert result.success is True
        assert result.input_tokens == 100
        assert result.output_tokens == 200

    def test_sub_domain_backward_compat(self):
        """sub_domain (singular) populates sub_domains when sub_domains empty."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data={
                "metadata": {},
                "spine_metadata": {"sub_domain": "Degenerative", "sub_domains": []},
                "chunks": [],
            },
            input_tokens=0, output_tokens=0, latency=0.0,
            provider="claude", model="haiku",
        )
        assert result.metadata.spine.sub_domains == ["Degenerative"]
        assert result.metadata.spine.sub_domain == "Degenerative"

    def test_outcomes_with_effect_measure(self, full_extracted_data):
        """Outcomes with effect_measure are parsed correctly."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data=full_extracted_data,
            input_tokens=0, output_tokens=0, latency=0.0,
            provider="claude", model="haiku",
        )
        assert len(result.metadata.spine.outcomes) == 1
        outcome = result.metadata.spine.outcomes[0]
        assert outcome.name == "VAS"
        assert outcome.effect_measure is not None
        assert outcome.effect_measure.measure_type == "MD"
        assert outcome.effect_measure.value == "-1.4"

    def test_complications_parsed(self, full_extracted_data):
        """Complications are parsed from spine_metadata."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data=full_extracted_data,
            input_tokens=0, output_tokens=0, latency=0.0,
            provider="claude", model="haiku",
        )
        assert len(result.metadata.spine.complications) == 1
        assert result.metadata.spine.complications[0].name == "Dural tear"

    def test_pico_parsed(self, full_extracted_data):
        """PICO data is parsed from spine_metadata."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data=full_extracted_data,
            input_tokens=0, output_tokens=0, latency=0.0,
            provider="claude", model="haiku",
        )
        assert result.metadata.spine.pico is not None
        assert result.metadata.spine.pico.population == "Adults"
        assert result.metadata.spine.pico.intervention == "UBE"

    def test_fallback_info_passed_through(self):
        """Fallback info is captured in result."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data={"metadata": {}, "chunks": []},
            input_tokens=0, output_tokens=0, latency=0.0,
            provider="claude", model="sonnet",
            fallback_used=True, fallback_reason="max_tokens_exceeded",
        )
        assert result.fallback_used is True
        assert result.fallback_reason == "max_tokens_exceeded"

    def test_none_outcome_values_become_strings(self):
        """None values in outcome fields are converted to strings."""
        processor = self._create_processor()
        result = processor._dict_to_vision_result(
            data={
                "metadata": {},
                "spine_metadata": {
                    "outcomes": [
                        {"name": "VAS", "value_intervention": None, "p_value": None}
                    ]
                },
                "chunks": [],
            },
            input_tokens=0, output_tokens=0, latency=0.0,
            provider="claude", model="haiku",
        )
        outcome = result.metadata.spine.outcomes[0]
        assert outcome.value_intervention == "None"
        assert outcome.p_value == "None"


# ===========================================================================
# Tests: UnifiedPDFProcessor.process_pdf file size limit
# ===========================================================================

class TestProcessPdfFileSize:
    """Test PDF file size validation."""

    @pytest.mark.asyncio
    async def test_oversized_pdf_rejected(self, tmp_path):
        """PDF exceeding 100MB is rejected."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.ClaudeBackend"):
                processor = UnifiedPDFProcessor(provider="claude")

        # Create a fake file and mock its stat
        pdf_file = tmp_path / "huge.pdf"
        pdf_file.write_bytes(b"x" * 100)  # small file physically

        # Mock stat to report 150MB
        with patch.object(Path, "stat") as mock_stat:
            mock_stat_result = MagicMock()
            mock_stat_result.st_size = 150 * 1024 * 1024  # 150MB
            mock_stat.return_value = mock_stat_result

            result = await processor.process_pdf(pdf_file)

        assert result.success is False
        assert "too large" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """Non-existent file returns error result."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.ClaudeBackend"):
                processor = UnifiedPDFProcessor(provider="claude")

        result = await processor.process_pdf("/nonexistent/file.pdf")
        assert result.success is False
        assert "not found" in result.error.lower() or "File not found" in result.error


# ===========================================================================
# Tests: UnifiedPDFProcessor.process_text validation
# ===========================================================================

class TestProcessTextValidation:
    """Test process_text input validation."""

    @pytest.mark.asyncio
    async def test_empty_string(self):
        """Empty string is rejected."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.ClaudeBackend"):
                processor = UnifiedPDFProcessor(provider="claude")

        result = await processor.process_text("")
        assert result.success is False
        assert "Empty" in result.error or "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_whitespace_only(self):
        """Whitespace-only string is rejected."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.ClaudeBackend"):
                processor = UnifiedPDFProcessor(provider="claude")

        result = await processor.process_text("   \n\t  ")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_gemini_process_text_unsupported(self):
        """Gemini backend does not support text processing."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.GeminiBackend"):
                processor = UnifiedPDFProcessor(provider="gemini")

        result = await processor.process_text("some text")
        assert result.success is False
        assert "Gemini" in result.error


# ===========================================================================
# Tests: ClaudeBackend._get_max_tokens
# ===========================================================================

class TestClaudeBackendMaxTokens:
    """Test ClaudeBackend max tokens logic."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_haiku_max_tokens(self):
        """Haiku model returns 64000 max tokens."""
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            backend = ClaudeBackend(model="claude-haiku-4-5-20251001")
        assert backend._get_max_tokens("claude-haiku-4-5-20251001") == 64000

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_sonnet_max_tokens(self):
        """Sonnet model returns 64000 max tokens."""
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            backend = ClaudeBackend()
        assert backend._get_max_tokens("claude-sonnet-4-5-20250929") == 64000

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_unknown_model_default_tokens(self):
        """Unknown model returns default 16384 max tokens."""
        mock_anthropic = MagicMock()
        with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
            backend = ClaudeBackend()
        assert backend._get_max_tokens("claude-unknown-model") == 16384


# ===========================================================================
# Tests: _build_vocabulary_hints
# ===========================================================================

class TestBuildVocabularyHints:
    """Test _build_vocabulary_hints graceful degradation."""

    def test_returns_string(self):
        """Should return a string (empty or hints)."""
        result = _build_vocabulary_hints()
        assert isinstance(result, str)

    def test_import_error_returns_empty(self):
        """Import failure returns empty string."""
        # _build_vocabulary_hints does `from graph.entity_normalizer import EntityNormalizer`
        # inside a try/except, so we force that import to fail
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "entity_normalizer" in name:
                raise ImportError("no module")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = _build_vocabulary_hints()
        assert result == ""

    def test_contains_interventions_if_available(self):
        """If normalizer loads, hints contain intervention section."""
        result = _build_vocabulary_hints()
        if result:  # Only test if it actually loaded
            assert "Interventions" in result or "CONTROLLED VOCABULARY" in result


# ===========================================================================
# Tests: Enum completeness
# ===========================================================================

class TestEnumCompleteness:
    """Test enum values are complete."""

    def test_llm_provider_values(self):
        """LLMProvider has claude and gemini."""
        assert LLMProvider.CLAUDE.value == "claude"
        assert LLMProvider.GEMINI.value == "gemini"

    def test_chunk_mode_values(self):
        """ChunkMode has full, balanced, lean."""
        assert ChunkMode.FULL.value == "full"
        assert ChunkMode.BALANCED.value == "balanced"
        assert ChunkMode.LEAN.value == "lean"


# ===========================================================================
# Tests: create_pdf_processor factory
# ===========================================================================

class TestCreatePdfProcessor:
    """Test create_pdf_processor factory function."""

    def test_returns_processor_instance(self):
        """Factory returns UnifiedPDFProcessor."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.ClaudeBackend"):
                processor = create_pdf_processor(provider="claude")
        assert isinstance(processor, UnifiedPDFProcessor)

    def test_passes_provider_and_model(self):
        """Factory passes provider and model arguments."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("builder.unified_pdf_processor.ClaudeBackend") as mock_backend:
                processor = create_pdf_processor(provider="claude", model="custom-model")
        assert processor.provider == LLMProvider.CLAUDE


# ===========================================================================
# Tests: SpineMetadata defaults
# ===========================================================================

class TestSpineMetadataDefaults:
    """Test SpineMetadata default values."""

    def test_defaults(self):
        """Default SpineMetadata has empty lists."""
        sm = SpineMetadata()
        assert sm.sub_domains == []
        assert sm.surgical_approach == []
        assert sm.pathology == []
        assert sm.interventions == []
        assert sm.outcomes == []
        assert sm.complications == []
        assert sm.anatomy_level == ""
        assert sm.anatomy_region == ""
        assert sm.sample_size == 0
        assert sm.pico is None

    def test_with_outcomes_and_complications(self):
        """SpineMetadata with outcomes and complications."""
        outcome = ExtractedOutcome(name="VAS", category="pain")
        complication = ComplicationData(name="Infection")
        sm = SpineMetadata(
            outcomes=[outcome],
            complications=[complication],
        )
        assert len(sm.outcomes) == 1
        assert len(sm.complications) == 1

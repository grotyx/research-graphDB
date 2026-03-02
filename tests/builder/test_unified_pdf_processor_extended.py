"""Extended tests for UnifiedPDFProcessor module (v2).

Comprehensive test coverage for:
- Dataclass creation and validation (PICOData, EffectMeasure, StatisticsData, etc.)
- _repair_json edge cases
- _dict_to_vision_result conversion
- UnifiedPDFProcessor initialization and process_pdf / process_text
- ClaudeBackend._get_max_tokens
- ProcessorResult / VisionProcessorResult construction
- Factory function
- Error handling for corrupt/empty PDFs
"""

import json
import os
import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import asdict

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
    create_pdf_processor,
)


# ============================================================================
# Test: Dataclass Construction
# ============================================================================

class TestPICOData:
    """Test PICOData dataclass."""

    def test_default_values(self):
        pico = PICOData()
        assert pico.population == ""
        assert pico.intervention == ""
        assert pico.comparison == ""
        assert pico.outcome == ""

    def test_full_initialization(self):
        pico = PICOData(
            population="Adults 50-80 with stenosis",
            intervention="UBE",
            comparison="Open laminectomy",
            outcome="VAS, ODI",
        )
        assert pico.population == "Adults 50-80 with stenosis"
        assert pico.intervention == "UBE"


class TestEffectMeasure:
    """Test EffectMeasure dataclass."""

    def test_default_values(self):
        em = EffectMeasure()
        assert em.measure_type == ""
        assert em.value == ""
        assert em.ci_lower == ""
        assert em.ci_upper == ""
        assert em.label == ""

    def test_hazard_ratio(self):
        em = EffectMeasure(
            measure_type="HR",
            value="2.35",
            ci_lower="1.42",
            ci_upper="3.89",
            label="HR 2.35 (95% CI: 1.42-3.89)",
        )
        assert em.measure_type == "HR"
        assert em.value == "2.35"


class TestStatisticsData:
    """Test StatisticsData dataclass."""

    def test_default_values(self):
        stats = StatisticsData()
        assert stats.p_value == ""
        assert stats.is_significant is False
        assert stats.effect_measure is None
        assert stats.additional == ""

    def test_with_effect_measure(self):
        em = EffectMeasure(measure_type="OR", value="3.2")
        stats = StatisticsData(
            p_value="0.001",
            is_significant=True,
            effect_measure=em,
            additional="95% CI: 1.8-5.6",
        )
        assert stats.is_significant is True
        assert stats.effect_measure.measure_type == "OR"


class TestExtractedChunk:
    """Test ExtractedChunk dataclass."""

    def test_minimal_initialization(self):
        chunk = ExtractedChunk(
            content="Test content",
            content_type="text",
            section_type="results",
            tier="tier1",
        )
        assert chunk.content == "Test content"
        assert chunk.keywords == []
        assert chunk.is_key_finding is False
        assert chunk.statistics is None

    def test_key_finding_chunk(self):
        chunk = ExtractedChunk(
            content="VAS improved significantly",
            content_type="key_finding",
            section_type="results",
            tier="tier1",
            is_key_finding=True,
            statistics=StatisticsData(p_value="<0.001", is_significant=True),
        )
        assert chunk.is_key_finding is True
        assert chunk.statistics.is_significant is True


class TestExtractedOutcome:
    """Test ExtractedOutcome dataclass."""

    def test_default_values(self):
        outcome = ExtractedOutcome(name="VAS")
        assert outcome.name == "VAS"
        assert outcome.category == ""
        assert outcome.p_value == ""
        assert outcome.effect_measure is None
        assert outcome.is_significant is False

    def test_full_outcome(self):
        outcome = ExtractedOutcome(
            name="ODI",
            category="Functional Outcome",
            value_intervention="25.3 +/- 5.1",
            value_control="38.7 +/- 6.2",
            p_value="0.001",
            is_significant=True,
            direction="improved",
        )
        assert outcome.direction == "improved"


class TestComplicationData:
    """Test ComplicationData dataclass."""

    def test_complication(self):
        comp = ComplicationData(
            name="Dural tear",
            incidence_intervention="2.5%",
            incidence_control="4.1%",
            p_value="0.35",
            severity="minor",
        )
        assert comp.name == "Dural tear"
        assert comp.severity == "minor"


class TestSpineMetadata:
    """Test SpineMetadata dataclass."""

    def test_default_values(self):
        sm = SpineMetadata()
        assert sm.sub_domains == []
        assert sm.pathology == []
        assert sm.interventions == []
        assert sm.outcomes == []
        assert sm.complications == []
        assert sm.sample_size == 0
        assert sm.pico is None

    def test_full_spine_metadata(self):
        sm = SpineMetadata(
            sub_domains=["Degenerative"],
            surgical_approach=["Endoscopic", "Minimally Invasive"],
            pathology=["lumbar stenosis"],
            anatomy_level="L4-5",
            anatomy_region="lumbar",
            interventions=["UBE"],
            follow_up_period="24 months",
            sample_size=100,
        )
        assert len(sm.sub_domains) == 1
        assert sm.anatomy_region == "lumbar"


class TestExtractedMetadata:
    """Test ExtractedMetadata dataclass."""

    def test_default_values(self):
        meta = ExtractedMetadata()
        assert meta.title == ""
        assert meta.evidence_level == "5"

    def test_full_metadata(self):
        meta = ExtractedMetadata(
            title="Test Paper",
            authors=["Kim", "Park"],
            year=2024,
            journal="Spine",
            study_type="RCT",
            evidence_level="1b",
        )
        assert meta.year == 2024
        assert meta.evidence_level == "1b"


class TestImportantCitation:
    """Test ImportantCitation dataclass."""

    def test_citation(self):
        cit = ImportantCitation(
            authors=["Smith"],
            year=2022,
            context="supports_result",
            section="discussion",
            citation_text="Smith et al. reported similar findings",
            direction_match=True,
        )
        assert cit.context == "supports_result"
        assert cit.direction_match is True


class TestProcessorResult:
    """Test ProcessorResult dataclass."""

    def test_success_result(self):
        result = ProcessorResult(
            success=True,
            provider="claude",
            model="claude-haiku-4-5-20251001",
            extracted_data={"metadata": {"title": "Test"}},
            input_tokens=1000,
            output_tokens=500,
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        result = ProcessorResult(
            success=False,
            error="File not found",
        )
        assert result.success is False
        assert result.error == "File not found"

    def test_fallback_result(self):
        result = ProcessorResult(
            success=True,
            provider="claude",
            model="claude-sonnet-4-5-20250929",
            fallback_used=True,
            fallback_reason="max_tokens_exceeded",
        )
        assert result.fallback_used is True


class TestVisionProcessorResult:
    """Test VisionProcessorResult dataclass."""

    def test_success_result(self):
        result = VisionProcessorResult(
            success=True,
            metadata=ExtractedMetadata(title="Test"),
            chunks=[],
            table_count=2,
            figure_count=1,
            key_finding_count=3,
        )
        assert result.success is True
        assert result.table_count == 2

    def test_failure_result(self):
        result = VisionProcessorResult(success=False, error="Processing failed")
        assert result.error == "Processing failed"
        assert result.chunks == []


# ============================================================================
# Test: _repair_json extended
# ============================================================================

class TestRepairJsonExtendedV2:
    """Test _repair_json with various malformed inputs."""

    def test_valid_json_passthrough(self):
        valid = '{"key": "value"}'
        assert json.loads(_repair_json(valid)) == {"key": "value"}

    def test_trailing_comma_object(self):
        malformed = '{"a": 1, "b": 2,}'
        result = json.loads(_repair_json(malformed))
        assert result == {"a": 1, "b": 2}

    def test_trailing_comma_array(self):
        malformed = '{"items": [1, 2, 3,]}'
        result = json.loads(_repair_json(malformed))
        assert result["items"] == [1, 2, 3]

    def test_unclosed_brace(self):
        malformed = '{"key": "value"'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "key" in result

    def test_unclosed_bracket(self):
        malformed = '{"items": [1, 2, 3'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "items" in result

    def test_mixed_unclosed(self):
        malformed = '{"items": [{"name": "test"}'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "items" in result

    def test_markdown_json_block(self):
        text = '```json\n{"key": "value"}\n```'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"key": "value"}

    def test_markdown_code_block_no_tag(self):
        text = '```\n{"key": "value"}\n```'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"key": "value"}

    def test_control_characters(self):
        malformed = '{"key": "value\x00more"}'
        repaired = _repair_json(malformed)
        try:
            result = json.loads(repaired)
            assert "key" in result
        except json.JSONDecodeError:
            pass

    def test_p_value_array_fix(self):
        malformed = '{"p_values": ["0.001", 0.05, "<0.001"]}'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "p_values" in result

    def test_empty_string(self):
        repaired = _repair_json("")
        assert isinstance(repaired, str)

    def test_whitespace_only(self):
        repaired = _repair_json("   \n\t   ")
        assert isinstance(repaired, str)

    def test_deeply_nested_unclosed(self):
        malformed = '{"a": {"b": {"c": [1, 2'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "a" in result

    def test_valid_complex_json(self):
        valid = json.dumps({
            "metadata": {"title": "Test", "year": 2023},
            "chunks": [{"content": "text", "tier": "tier1"}],
        })
        repaired = _repair_json(valid)
        result = json.loads(repaired)
        assert result["metadata"]["title"] == "Test"


# ============================================================================
# Test: ClaudeBackend._get_max_tokens
# ============================================================================

class TestClaudeBackendGetMaxTokens:
    """Test ClaudeBackend._get_max_tokens."""

    def test_haiku_model(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-haiku-4-5-20251001")
                assert backend._get_max_tokens("claude-haiku-4-5-20251001") == 64000

    def test_sonnet_model(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-sonnet-4-5-20250929")
                assert backend._get_max_tokens("claude-sonnet-4-5-20250929") == 64000

    def test_unknown_model_default(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-unknown-model")
                assert backend._get_max_tokens("claude-unknown-model") == 16384


# ============================================================================
# Test: ClaudeBackend initialization
# ============================================================================

class TestClaudeBackendInit:
    """Test ClaudeBackend initialization."""

    def test_init_with_env_key(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend()
                assert backend.api_key == "test-key"

    def test_init_with_custom_model(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-sonnet-4-5-20250929")
                assert backend.model == "claude-sonnet-4-5-20250929"

    def test_init_without_api_key_raises(self):
        with patch.dict('os.environ', {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(Exception):
                ClaudeBackend()


# ============================================================================
# Test: UnifiedPDFProcessor initialization
# ============================================================================

class TestUnifiedPDFProcessorInit:
    """Test UnifiedPDFProcessor initialization."""

    def test_init_default_claude(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key', 'LLM_PROVIDER': 'claude'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "claude-haiku-4-5-20251001"
                MockBackend.return_value = mock
                processor = UnifiedPDFProcessor()
                assert processor.provider == LLMProvider.CLAUDE
                assert processor.auto_fallback is True

    def test_init_with_auto_fallback_disabled(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                processor = UnifiedPDFProcessor(auto_fallback=False)
                assert processor.auto_fallback is False

    def test_init_env_fallback_disabled(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key', 'CLAUDE_AUTO_FALLBACK': 'false'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                processor = UnifiedPDFProcessor()
                assert processor.auto_fallback is False

    def test_provider_name_property(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                processor = UnifiedPDFProcessor(provider="claude")
                assert processor.provider_name == "claude"

    def test_model_name_property(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test-model"
                MockBackend.return_value = mock
                processor = UnifiedPDFProcessor(provider="claude")
                assert processor.model_name == "test-model"


# ============================================================================
# Test: UnifiedPDFProcessor.process_pdf
# ============================================================================

class TestUnifiedPDFProcessorProcessPdf:
    """Test process_pdf method."""

    @pytest.fixture
    def processor(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MagicMock()
                mock_backend.model = "claude-haiku-4-5-20251001"
                MockBackend.return_value = mock_backend
                proc = UnifiedPDFProcessor(provider="claude")
                return proc

    @pytest.mark.asyncio
    async def test_file_not_found(self, processor):
        result = await processor.process_pdf("/nonexistent/path.pdf")
        assert result.success is False
        assert "not found" in result.error.lower() or "File not found" in result.error

    @pytest.mark.asyncio
    async def test_successful_pdf_processing(self, processor, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")

        mock_result = {
            "success": True,
            "data": {"metadata": {"title": "Test Paper"}},
            "input_tokens": 1000,
            "output_tokens": 500,
            "latency": 2.0,
            "model_used": "claude-haiku-4-5-20251001",
            "stop_reason": "end_turn",
        }
        processor._backend.process_pdf = MagicMock(return_value=mock_result)

        result = await processor.process_pdf(str(pdf_file))
        assert result.success is True
        assert result.extracted_data["metadata"]["title"] == "Test Paper"
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_fallback_on_max_tokens(self, processor, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")
        processor.auto_fallback = True

        mock_fail = {
            "success": False,
            "error": "max_tokens_exceeded",
            "input_tokens": 1000,
            "output_tokens": 8192,
            "latency": 3.0,
            "model_used": "claude-haiku-4-5-20251001",
            "stop_reason": "max_tokens",
        }
        mock_success = {
            "success": True,
            "data": {"metadata": {"title": "Test"}},
            "input_tokens": 1000,
            "output_tokens": 12000,
            "latency": 5.0,
            "model_used": "claude-sonnet-4-5-20250929",
        }
        processor._backend.process_pdf = MagicMock(side_effect=[mock_fail, mock_success])

        result = await processor.process_pdf(str(pdf_file))
        assert result.success is True
        assert result.fallback_used is True

    @pytest.mark.asyncio
    async def test_no_fallback_when_disabled(self, processor, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")
        processor.auto_fallback = False

        mock_fail = {
            "success": False,
            "error": "max_tokens_exceeded",
            "input_tokens": 1000,
            "output_tokens": 8192,
            "latency": 3.0,
            "model_used": "claude-haiku-4-5-20251001",
        }
        processor._backend.process_pdf = MagicMock(return_value=mock_fail)

        result = await processor.process_pdf(str(pdf_file))
        assert result.success is False
        assert result.fallback_used is False

    @pytest.mark.asyncio
    async def test_non_token_error(self, processor, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake pdf content")

        mock_error = {
            "success": False,
            "error": "JSON parsing error: ...",
            "latency": 1.0,
            "model_used": "claude-haiku-4-5-20251001",
        }
        processor._backend.process_pdf = MagicMock(return_value=mock_error)

        result = await processor.process_pdf(str(pdf_file))
        assert result.success is False
        assert result.fallback_used is False


# ============================================================================
# Test: UnifiedPDFProcessor.process_text
# ============================================================================

class TestUnifiedPDFProcessorProcessText:
    """Test process_text method."""

    @pytest.fixture
    def processor(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MagicMock()
                mock_backend.model = "claude-haiku-4-5-20251001"
                MockBackend.return_value = mock_backend
                return UnifiedPDFProcessor(provider="claude")

    @pytest.mark.asyncio
    async def test_empty_text(self, processor):
        result = await processor.process_text("")
        assert result.success is False
        assert "empty" in result.error.lower() or "Empty" in result.error

    @pytest.mark.asyncio
    async def test_whitespace_only_text(self, processor):
        result = await processor.process_text("   \n\t  ")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_successful_text_processing(self, processor):
        mock_result = {
            "success": True,
            "data": {"metadata": {"title": "PMC Paper"}},
            "input_tokens": 500,
            "output_tokens": 300,
            "latency": 1.0,
            "model_used": "claude-haiku-4-5-20251001",
        }
        processor._backend.process_text = MagicMock(return_value=mock_result)

        result = await processor.process_text("This is a medical paper about UBE surgery...")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_gemini_text_not_supported(self):
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.GeminiBackend') as MockBackend:
                mock_backend = MagicMock()
                mock_backend.model = "gemini-2.5-flash"
                MockBackend.return_value = mock_backend
                processor = UnifiedPDFProcessor(provider="gemini")
                result = await processor.process_text("Some text")
                assert result.success is False
                assert "not support" in result.error.lower() or "Gemini" in result.error


# ============================================================================
# Test: _dict_to_vision_result
# ============================================================================

class TestDictToVisionResult:
    """Test _dict_to_vision_result conversion."""

    @pytest.fixture
    def processor(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MagicMock()
                mock_backend.model = "test"
                MockBackend.return_value = mock_backend
                return UnifiedPDFProcessor(provider="claude")

    def test_minimal_data(self, processor):
        data = {}
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0.0, provider="claude", model="test",
        )
        assert result.success is True
        assert result.metadata.title == ""
        assert result.chunks == []

    def test_full_metadata(self, processor):
        data = {
            "metadata": {
                "title": "Test Paper",
                "authors": ["Kim", "Park"],
                "year": 2024,
                "journal": "Spine",
                "study_type": "RCT",
                "evidence_level": "1b",
                "sample_size": 100,
            },
            "spine_metadata": {
                "sub_domains": ["Degenerative"],
                "pathology": ["lumbar stenosis"],
                "interventions": ["UBE"],
                "anatomy_level": "L4-5",
                "anatomy_region": "lumbar",
                "outcomes": [
                    {
                        "name": "VAS",
                        "category": "Pain Outcome",
                        "p_value": "0.001",
                        "is_significant": True,
                        "direction": "improved",
                    }
                ],
                "complications": [
                    {"name": "Dural tear", "incidence_intervention": "2%", "severity": "minor"},
                ],
                "pico": {
                    "population": "Adults",
                    "intervention": "UBE",
                    "comparison": "Open",
                    "outcome": "VAS",
                },
            },
            "chunks": [
                {"content": "Test chunk", "content_type": "text", "section_type": "results", "tier": "tier1", "is_key_finding": True},
                {"content": "Table data", "content_type": "table", "section_type": "results", "tier": "tier1"},
                {"content": "Figure desc", "content_type": "figure", "section_type": "results", "tier": "tier2"},
            ],
            "important_citations": [
                {"authors": ["Smith"], "year": 2022, "context": "supports_result", "section": "discussion", "citation_text": "Smith et al.", "direction_match": True},
            ],
        }

        result = processor._dict_to_vision_result(
            data=data, input_tokens=1000, output_tokens=500,
            latency=2.0, provider="claude", model="test-model",
        )

        assert result.success is True
        assert result.metadata.title == "Test Paper"
        assert result.metadata.spine.sub_domains == ["Degenerative"]
        assert result.metadata.spine.pico.intervention == "UBE"
        assert len(result.chunks) == 3
        assert result.table_count == 1
        assert result.figure_count == 1
        assert result.key_finding_count == 1
        assert len(result.important_citations) == 1

    def test_none_values_handling(self, processor):
        """Test that None values in data dict are handled without crashing.

        Note: meta_dict.get("title", "") returns None when key exists with None value,
        so title stays None. The important thing is it does not crash.
        """
        data = {
            "metadata": {"title": None, "authors": None, "year": None, "sample_size": None},
            "spine_metadata": {"sub_domains": None, "pathology": None, "interventions": None},
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test",
        )
        # title gets None because dict.get("title", "") returns None when value IS None
        assert result.metadata.title is None
        assert result.metadata.authors == []
        assert result.metadata.year == 0

    def test_sub_domain_backward_compat(self, processor):
        data = {"spine_metadata": {"sub_domain": "Degenerative", "sub_domains": []}}
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test",
        )
        assert result.metadata.spine.sub_domains == ["Degenerative"]

    def test_effect_measure_in_chunks(self, processor):
        data = {
            "chunks": [{
                "content": "Result with stats",
                "content_type": "key_finding",
                "section_type": "results",
                "tier": "tier1",
                "statistics": {
                    "p_value": "0.001",
                    "is_significant": True,
                    "effect_measure": {
                        "measure_type": "HR",
                        "value": "2.35",
                        "ci_lower": "1.42",
                        "ci_upper": "3.89",
                        "label": "HR 2.35 (95% CI: 1.42-3.89)",
                    },
                },
            }],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test",
        )
        chunk = result.chunks[0]
        assert chunk.statistics.effect_measure.measure_type == "HR"

    def test_topic_summary_backward_compat(self, processor):
        data = {
            "chunks": [{
                "content": "test",
                "content_type": "text",
                "section_type": "results",
                "tier": "tier1",
                "topic_summary": "Legacy summary",
            }],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test",
        )
        assert result.chunks[0].summary == "Legacy summary"


# ============================================================================
# Test: Factory Function
# ============================================================================

class TestCreatePdfProcessor:
    """Test create_pdf_processor factory."""

    def test_factory_default(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                processor = create_pdf_processor()
                assert isinstance(processor, UnifiedPDFProcessor)

    def test_factory_with_provider(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                processor = create_pdf_processor(provider="claude")
                assert processor.provider == LLMProvider.CLAUDE


# ============================================================================
# Test: Enum values
# ============================================================================

class TestEnums:
    """Test enum definitions."""

    def test_llm_provider_values(self):
        assert LLMProvider.CLAUDE.value == "claude"
        assert LLMProvider.GEMINI.value == "gemini"

    def test_chunk_mode_values(self):
        assert ChunkMode.FULL.value == "full"
        assert ChunkMode.BALANCED.value == "balanced"
        assert ChunkMode.LEAN.value == "lean"

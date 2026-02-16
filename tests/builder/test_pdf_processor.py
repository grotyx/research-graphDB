"""Unified PDF Processor Tests.

Tests for unified_pdf_processor.py covering:
- Initialization and configuration
- Text processing pipeline (mocked)
- Metadata extraction flow
- Error handling for various failure modes
- JSON repair utilities
- Fallback logic (Haiku -> Sonnet)
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime

# Import module
import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent.parent / "src"))

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
    LLMProvider,
    ChunkMode,
    ClaudeBackend,
    _repair_json,
    _build_vocabulary_hints,
    create_pdf_processor
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sample_extracted_data():
    """Sample extracted data from LLM."""
    return {
        "metadata": {
            "title": "Comparison of UBE and Open Laminectomy",
            "authors": ["Kim JH", "Park SM"],
            "year": 2023,
            "journal": "Spine",
            "doi": "10.1097/test",
            "pmid": "12345678",
            "abstract": "This study compares UBE versus open laminectomy...",
            "study_type": "RCT",
            "study_design": "randomized",
            "evidence_level": "1b",
            "sample_size": 100,
            "centers": "multi-center",
            "blinding": "double-blind"
        },
        "spine_metadata": {
            "sub_domains": ["Degenerative"],
            "surgical_approach": ["Endoscopic", "Minimally Invasive"],
            "pathology": ["lumbar stenosis"],
            "anatomy_level": "L4-5",
            "anatomy_region": "lumbar",
            "interventions": ["UBE", "laminectomy"],
            "comparison_type": "vs_conventional",
            "follow_up_months": 24,
            "main_conclusion": "UBE showed better outcomes",
            "summary": "UBE demonstrated superior outcomes compared to open laminectomy",
            "pico": {
                "population": "Adults with lumbar stenosis",
                "intervention": "UBE decompression",
                "comparison": "Open laminectomy",
                "outcome": "VAS, ODI"
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
                    "timepoint": "1yr"
                }
            ],
            "complications": []
        },
        "chunks": [
            {
                "content": "This study compares outcomes...",
                "content_type": "text",
                "section_type": "abstract",
                "tier": "tier1",
                "summary": "Study overview",
                "keywords": ["UBE", "laminectomy"],
                "is_key_finding": False,
                "statistics": {
                    "p_value": "0.001",
                    "is_significant": True,
                    "additional": "95% CI: -2.1 to -0.7"
                }
            }
        ],
        "important_citations": [
            {
                "authors": ["Lee", "Kim"],
                "year": 2022,
                "context": "supports_result",
                "section": "discussion",
                "citation_text": "Lee et al. reported similar findings...",
                "importance_reason": "Supports our VAS results"
            }
        ]
    }


@pytest.fixture
def mock_claude_response():
    """Mock Claude API response."""
    mock_msg = MagicMock()
    mock_msg.stop_reason = "end_turn"
    mock_msg.usage.input_tokens = 5000
    mock_msg.usage.output_tokens = 2000
    return mock_msg


# ===========================================================================
# Test JSON Repair Utilities
# ===========================================================================

class TestJsonRepair:
    """Test JSON repair utilities."""

    def test_repair_trailing_comma(self):
        """Test removal of trailing commas."""
        malformed = '{"key": "value",}'
        repaired = _repair_json(malformed)
        assert json.loads(repaired) == {"key": "value"}

    def test_repair_markdown_json(self):
        """Test extraction from markdown code blocks."""
        text = '```json\n{"key": "value"}\n```'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"key": "value"}

    def test_repair_unclosed_braces(self):
        """Test closing unclosed braces."""
        malformed = '{"key": {"nested": "value"'
        repaired = _repair_json(malformed)
        # Should add closing braces
        result = json.loads(repaired)
        assert "key" in result
        assert result["key"]["nested"] == "value"

    def test_repair_valid_json(self):
        """Test that valid JSON passes through unchanged."""
        valid = '{"key": "value", "number": 123}'
        repaired = _repair_json(valid)
        assert json.loads(repaired) == {"key": "value", "number": 123}


class TestVocabularyHints:
    """Test vocabulary hints builder."""

    def test_build_vocabulary_hints(self):
        """Test vocabulary hints generation."""
        hints = _build_vocabulary_hints()

        # Should contain controlled vocabulary section
        assert "CONTROLLED VOCABULARY" in hints or hints == ""

        # Should mention interventions/outcomes/pathologies if available
        if hints:
            assert any(word in hints for word in ["Interventions", "Outcomes", "Pathologies"])


# ===========================================================================
# Test LLMProvider and ChunkMode Enums
# ===========================================================================

class TestEnums:
    """Test enums."""

    def test_llm_provider_enum(self):
        """Test LLMProvider enum."""
        assert LLMProvider.CLAUDE.value == "claude"
        assert LLMProvider.GEMINI.value == "gemini"

    def test_chunk_mode_enum(self):
        """Test ChunkMode enum."""
        assert ChunkMode.FULL.value == "full"
        assert ChunkMode.BALANCED.value == "balanced"
        assert ChunkMode.LEAN.value == "lean"


# ===========================================================================
# Test Data Classes
# ===========================================================================

class TestDataClasses:
    """Test data classes."""

    def test_pico_data(self):
        """Test PICOData dataclass."""
        pico = PICOData(
            population="Adults",
            intervention="UBE",
            comparison="Open",
            outcome="VAS"
        )
        assert pico.population == "Adults"
        assert pico.intervention == "UBE"

    def test_effect_measure(self):
        """Test EffectMeasure dataclass."""
        em = EffectMeasure(
            measure_type="HR",
            value="2.35",
            ci_lower="1.42",
            ci_upper="3.89",
            label="HR 2.35 (95% CI: 1.42-3.89)"
        )
        assert em.measure_type == "HR"
        assert em.value == "2.35"

    def test_statistics_data(self):
        """Test StatisticsData dataclass."""
        stats = StatisticsData(
            p_value="0.001",
            is_significant=True,
            additional="95% CI"
        )
        assert stats.p_value == "0.001"
        assert stats.is_significant is True

    def test_extracted_chunk(self):
        """Test ExtractedChunk dataclass."""
        chunk = ExtractedChunk(
            content="Test content",
            content_type="text",
            section_type="abstract",
            tier="tier1"
        )
        assert chunk.content == "Test content"
        assert chunk.tier == "tier1"

    def test_extracted_outcome(self):
        """Test ExtractedOutcome dataclass."""
        outcome = ExtractedOutcome(
            name="VAS",
            category="pain"
        )
        assert outcome.name == "VAS"
        assert outcome.category == "pain"

    def test_spine_metadata(self):
        """Test SpineMetadata dataclass."""
        spine = SpineMetadata(
            sub_domains=["Degenerative"],
            surgical_approach=["Endoscopic"]
        )
        assert spine.sub_domains == ["Degenerative"]
        assert spine.surgical_approach == ["Endoscopic"]

    def test_extracted_metadata(self):
        """Test ExtractedMetadata dataclass."""
        meta = ExtractedMetadata(
            title="Test Paper",
            authors=["Author1"],
            year=2023
        )
        assert meta.title == "Test Paper"
        assert meta.year == 2023

    def test_important_citation(self):
        """Test ImportantCitation dataclass."""
        citation = ImportantCitation(
            authors=["Kim"],
            year=2023,
            context="supports_result"
        )
        assert citation.authors == ["Kim"]
        assert citation.context == "supports_result"

    def test_processor_result(self):
        """Test ProcessorResult dataclass."""
        result = ProcessorResult(
            success=True,
            provider="claude",
            model="haiku"
        )
        assert result.success is True
        assert result.provider == "claude"


# ===========================================================================
# Test ClaudeBackend
# ===========================================================================

class TestClaudeBackend:
    """Test Claude backend."""

    def test_init_success(self):
        """Test successful initialization."""
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-haiku-4-5-20251001")
                assert backend.model == "claude-haiku-4-5-20251001"

    def test_init_no_api_key(self):
        """Test initialization without API key."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(Exception):  # LLMError
                ClaudeBackend()

    def test_get_max_tokens_haiku(self):
        """Test max tokens for Haiku model."""
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-haiku-4-5-20251001")
                assert backend._get_max_tokens("claude-haiku-4-5-20251001") == 64000

    def test_get_max_tokens_sonnet(self):
        """Test max tokens for Sonnet model."""
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-sonnet-4-5-20250929")
                assert backend._get_max_tokens("claude-sonnet-4-5-20250929") == 64000


# ===========================================================================
# Test UnifiedPDFProcessor Initialization
# ===========================================================================

class TestUnifiedPDFProcessorInit:
    """Test UnifiedPDFProcessor initialization."""

    def test_init_default_provider(self):
        """Test initialization with default provider (Claude)."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                assert processor.provider == LLMProvider.CLAUDE

    def test_init_gemini_provider(self):
        """Test initialization with Gemini provider."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.GeminiBackend'):
                processor = UnifiedPDFProcessor(provider="gemini")
                assert processor.provider == LLMProvider.GEMINI

    def test_init_auto_fallback_enabled(self):
        """Test auto fallback is enabled by default."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                assert processor.auto_fallback is True

    def test_init_auto_fallback_disabled(self):
        """Test disabling auto fallback."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor(auto_fallback=False)
                assert processor.auto_fallback is False

    def test_provider_name_property(self):
        """Test provider_name property."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                assert processor.provider_name == "claude"

    def test_model_name_property(self):
        """Test model_name property."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                processor = UnifiedPDFProcessor()
                assert processor.model_name == "claude-haiku-4-5-20251001"


# ===========================================================================
# Test UnifiedPDFProcessor - process_pdf
# ===========================================================================

class TestProcessPdf:
    """Test process_pdf method."""

    @pytest.mark.asyncio
    async def test_process_pdf_success(self, tmp_path, sample_extracted_data):
        """Test successful PDF processing."""
        # Create dummy PDF file
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                mock_backend.process_pdf.return_value = {
                    "success": True,
                    "data": sample_extracted_data,
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                    "latency": 3.5,
                    "stop_reason": "end_turn",
                    "model_used": "claude-haiku-4-5-20251001"
                }

                processor = UnifiedPDFProcessor()
                result = await processor.process_pdf(pdf_file)

                assert result.success is True
                assert result.provider == "claude"
                assert result.input_tokens == 5000
                assert result.output_tokens == 2000
                assert "metadata" in result.extracted_data

    @pytest.mark.asyncio
    async def test_process_pdf_file_not_found(self):
        """Test PDF processing with non-existent file."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                result = await processor.process_pdf("/nonexistent/file.pdf")

                assert result.success is False
                assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_process_pdf_with_fallback(self, tmp_path, sample_extracted_data):
        """Test PDF processing with Haiku -> Sonnet fallback."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"

                # First call: max_tokens_exceeded
                # Second call: success with Sonnet
                mock_backend.process_pdf.side_effect = [
                    {
                        "success": False,
                        "error": "max_tokens_exceeded",
                        "latency": 2.0,
                        "output_tokens": 8000,
                        "input_tokens": 5000,
                        "stop_reason": "max_tokens"
                    },
                    {
                        "success": True,
                        "data": sample_extracted_data,
                        "input_tokens": 5000,
                        "output_tokens": 3000,
                        "latency": 4.0,
                        "stop_reason": "end_turn",
                        "model_used": "claude-sonnet-4-5-20250929"
                    }
                ]

                processor = UnifiedPDFProcessor(auto_fallback=True)
                processor.fallback_model = "claude-sonnet-4-5-20250929"
                result = await processor.process_pdf(pdf_file)

                assert result.success is True
                assert result.fallback_used is True
                assert "max_tokens" in result.fallback_reason.lower()

    @pytest.mark.asyncio
    async def test_process_pdf_fallback_disabled(self, tmp_path):
        """Test PDF processing with fallback disabled."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                mock_backend.process_pdf.return_value = {
                    "success": False,
                    "error": "max_tokens_exceeded",
                    "latency": 2.0,
                    "output_tokens": 8000,
                    "input_tokens": 5000
                }

                processor = UnifiedPDFProcessor(auto_fallback=False)
                result = await processor.process_pdf(pdf_file)

                assert result.success is False
                assert result.fallback_used is False


# ===========================================================================
# Test UnifiedPDFProcessor - process_text
# ===========================================================================

class TestProcessText:
    """Test process_text method."""

    @pytest.mark.asyncio
    async def test_process_text_success(self, sample_extracted_data):
        """Test successful text processing."""
        text = "This is a sample medical paper text..."

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                mock_backend.process_text.return_value = {
                    "success": True,
                    "data": sample_extracted_data,
                    "input_tokens": 3000,
                    "output_tokens": 1500,
                    "latency": 2.5,
                    "model_used": "claude-haiku-4-5-20251001"
                }

                processor = UnifiedPDFProcessor()
                result = await processor.process_text(text)

                assert result.success is True
                assert result.provider == "claude"

    @pytest.mark.asyncio
    async def test_process_text_empty(self):
        """Test text processing with empty text."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                result = await processor.process_text("")

                assert result.success is False
                assert "empty" in result.error.lower()

    @pytest.mark.asyncio
    async def test_process_text_gemini_unsupported(self):
        """Test that Gemini doesn't support text processing."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.GeminiBackend'):
                processor = UnifiedPDFProcessor(provider="gemini")
                result = await processor.process_text("Some text")

                assert result.success is False
                assert "not support" in result.error.lower()


# ===========================================================================
# Test UnifiedPDFProcessor - dict to VisionResult conversion
# ===========================================================================

class TestDictToVisionResult:
    """Test _dict_to_vision_result conversion."""

    def test_dict_to_vision_result_success(self, sample_extracted_data):
        """Test successful conversion from dict to VisionProcessorResult."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()

                result = processor._dict_to_vision_result(
                    data=sample_extracted_data,
                    input_tokens=5000,
                    output_tokens=2000,
                    latency=3.5,
                    provider="claude",
                    model="haiku"
                )

                assert isinstance(result, VisionProcessorResult)
                assert result.success is True
                assert result.metadata.title == "Comparison of UBE and Open Laminectomy"
                assert result.metadata.year == 2023
                assert len(result.chunks) == 1
                assert len(result.important_citations) == 1

    def test_dict_to_vision_result_with_pico(self, sample_extracted_data):
        """Test PICO extraction from spine_metadata."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()

                result = processor._dict_to_vision_result(
                    data=sample_extracted_data,
                    input_tokens=5000,
                    output_tokens=2000,
                    latency=3.5,
                    provider="claude",
                    model="haiku"
                )

                assert result.metadata.spine.pico is not None
                assert result.metadata.spine.pico.population == "Adults with lumbar stenosis"
                assert result.metadata.spine.pico.intervention == "UBE decompression"

    def test_dict_to_vision_result_with_outcomes(self, sample_extracted_data):
        """Test outcomes extraction."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()

                result = processor._dict_to_vision_result(
                    data=sample_extracted_data,
                    input_tokens=5000,
                    output_tokens=2000,
                    latency=3.5,
                    provider="claude",
                    model="haiku"
                )

                assert len(result.metadata.spine.outcomes) == 1
                outcome = result.metadata.spine.outcomes[0]
                assert outcome.name == "VAS"
                assert outcome.category == "pain"
                assert outcome.is_significant is True


# ===========================================================================
# Test UnifiedPDFProcessor - process_pdf_typed
# ===========================================================================

class TestProcessPdfTyped:
    """Test process_pdf_typed method."""

    @pytest.mark.asyncio
    async def test_process_pdf_typed_success(self, tmp_path, sample_extracted_data):
        """Test typed PDF processing."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                mock_backend.process_pdf.return_value = {
                    "success": True,
                    "data": sample_extracted_data,
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                    "latency": 3.5,
                    "model_used": "claude-haiku-4-5-20251001"
                }

                processor = UnifiedPDFProcessor()
                result = await processor.process_pdf_typed(pdf_file)

                assert isinstance(result, VisionProcessorResult)
                assert result.success is True
                assert isinstance(result.metadata, ExtractedMetadata)
                assert result.metadata.title == "Comparison of UBE and Open Laminectomy"

    @pytest.mark.asyncio
    async def test_process_pdf_typed_error(self, tmp_path):
        """Test typed PDF processing with error."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                mock_backend.process_pdf.return_value = {
                    "success": False,
                    "error": "Test error",
                    "latency": 1.0,
                    "input_tokens": 0,
                    "output_tokens": 0
                }

                processor = UnifiedPDFProcessor()
                result = await processor.process_pdf_typed(pdf_file)

                assert isinstance(result, VisionProcessorResult)
                assert result.success is False
                assert result.error == "Test error"


# ===========================================================================
# Test Factory Function
# ===========================================================================

class TestFactoryFunction:
    """Test create_pdf_processor factory function."""

    def test_create_pdf_processor_default(self):
        """Test factory function with default settings."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = create_pdf_processor()
                assert isinstance(processor, UnifiedPDFProcessor)
                assert processor.provider == LLMProvider.CLAUDE

    def test_create_pdf_processor_gemini(self):
        """Test factory function with Gemini."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.GeminiBackend'):
                processor = create_pdf_processor(provider="gemini")
                assert isinstance(processor, UnifiedPDFProcessor)
                assert processor.provider == LLMProvider.GEMINI


# ===========================================================================
# Integration-like Tests
# ===========================================================================

class TestIntegration:
    """Integration-like tests."""

    @pytest.mark.asyncio
    async def test_full_workflow_mock(self, tmp_path, sample_extracted_data):
        """Test full workflow with mocked LLM."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                mock_backend.process_pdf.return_value = {
                    "success": True,
                    "data": sample_extracted_data,
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                    "latency": 3.5,
                    "model_used": "claude-haiku-4-5-20251001"
                }

                # 1. Create processor
                processor = create_pdf_processor()

                # 2. Process PDF
                result = await processor.process_pdf(pdf_file)

                # 3. Verify results
                assert result.success is True
                assert result.extracted_data["metadata"]["title"] == "Comparison of UBE and Open Laminectomy"

                # 4. Process typed
                typed_result = await processor.process_pdf_typed(pdf_file)
                assert isinstance(typed_result, VisionProcessorResult)
                assert typed_result.metadata.title == "Comparison of UBE and Open Laminectomy"

    @pytest.mark.asyncio
    async def test_error_recovery(self, tmp_path):
        """Test error propagation when backend fails."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend') as MockBackend:
                mock_backend = MockBackend.return_value
                mock_backend.model = "claude-haiku-4-5-20251001"
                mock_backend.process_pdf.side_effect = Exception("Network error")

                processor = UnifiedPDFProcessor()
                with pytest.raises(Exception, match="Network error"):
                    await processor.process_pdf(pdf_file)

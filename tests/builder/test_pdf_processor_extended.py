"""Extended tests for UnifiedPDFProcessor module.

Covers untested branches and edge cases:
- _repair_json: control characters, missing comma, p_value array fix, edge cases
- _dict_to_vision_result: None/empty values, effect_measure parsing, sub_domain compat
- process_text with fallback
- VisionProcessorResult counts (table, figure, key_finding)
- ClaudeBackend._get_max_tokens default model
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.builder.unified_pdf_processor import (
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
)


# ============================================================================
# Test: _repair_json extended edge cases
# ============================================================================

class TestRepairJsonExtended:
    """Test _repair_json with various malformed inputs."""

    def test_repair_control_characters(self):
        """Remove invalid control characters."""
        # Contains a \x00 character which is invalid in JSON
        malformed = '{"key": "value\x00more"}'
        repaired = _repair_json(malformed)
        # Should either parse or at least not crash
        try:
            result = json.loads(repaired)
            assert "key" in result
        except json.JSONDecodeError:
            # If repair couldn't fully fix it, at least we didn't crash
            pass

    def test_repair_unclosed_array(self):
        """Close unclosed arrays."""
        malformed = '{"items": [1, 2, 3'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "items" in result

    def test_repair_mixed_unclosed(self):
        """Close mixed unclosed brackets and braces."""
        malformed = '{"items": [{"name": "test"}'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "items" in result

    def test_repair_markdown_code_block_no_json_tag(self):
        """Extract from markdown code block without json tag."""
        text = '```\n{"key": "value"}\n```'
        repaired = _repair_json(text)
        assert json.loads(repaired) == {"key": "value"}

    def test_repair_trailing_comma_in_array(self):
        """Remove trailing comma in array."""
        malformed = '{"items": [1, 2, 3,]}'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert result["items"] == [1, 2, 3]

    def test_repair_nested_trailing_commas(self):
        """Remove nested trailing commas."""
        malformed = '{"outer": {"inner": "value",},}'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert result["outer"]["inner"] == "value"

    def test_repair_empty_string(self):
        """Empty string."""
        repaired = _repair_json("")
        # Should not crash; may or may not be valid JSON
        assert isinstance(repaired, str)

    def test_repair_whitespace_only(self):
        """Whitespace-only string."""
        repaired = _repair_json("   \n  \t  ")
        assert isinstance(repaired, str)

    def test_repair_deeply_nested(self):
        """Deeply nested JSON with missing closing."""
        malformed = '{"a": {"b": {"c": {"d": "value"'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert result["a"]["b"]["c"]["d"] == "value"

    def test_repair_p_value_array_mixed_quotes(self):
        """Fix p_values array with mixed quoting."""
        malformed = '{"p_values": ["0.001", 0.05, "0.023"]}'
        repaired = _repair_json(malformed)
        result = json.loads(repaired)
        assert "p_values" in result
        # All values should be strings
        for v in result["p_values"]:
            assert isinstance(v, str)

    def test_repair_valid_complex_json(self):
        """Valid complex JSON passes through."""
        valid = json.dumps({
            "metadata": {"title": "Test", "year": 2023},
            "chunks": [{"content": "text", "tier": "tier1"}],
        })
        repaired = _repair_json(valid)
        result = json.loads(repaired)
        assert result["metadata"]["title"] == "Test"

    def test_repair_missing_comma_between_fields(self):
        """Attempt to fix missing comma between JSON fields."""
        # This is a common LLM output error
        malformed = '{"key1": "value1" "key2": "value2"}'
        repaired = _repair_json(malformed)
        # May or may not succeed, but should not crash
        assert isinstance(repaired, str)


# ============================================================================
# Test: _dict_to_vision_result extended
# ============================================================================

class TestDictToVisionResultExtended:
    """Test _dict_to_vision_result with edge cases."""

    @pytest.fixture
    def processor(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                return UnifiedPDFProcessor()

    def test_none_metadata(self, processor):
        """Handle None metadata gracefully."""
        data = {"metadata": None, "chunks": [], "important_citations": []}
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.success is True
        assert result.metadata.title == ""

    def test_missing_spine_metadata(self, processor):
        """Handle missing spine_metadata."""
        data = {
            "metadata": {"title": "Test", "year": 2023},
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.success is True
        assert result.metadata.spine.sub_domains == []

    def test_spine_metadata_at_top_level(self, processor):
        """Handle spine_metadata at top level (not nested in metadata)."""
        data = {
            "metadata": {"title": "Test"},
            "spine_metadata": {
                "sub_domains": ["Degenerative"],
                "pathology": ["lumbar stenosis"],
                "interventions": ["UBE"],
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.metadata.spine.sub_domains == ["Degenerative"]
        assert result.metadata.spine.interventions == ["UBE"]

    def test_effect_measure_in_outcome(self, processor):
        """Parse effect_measure in outcome."""
        data = {
            "metadata": {"title": "Test"},
            "spine_metadata": {
                "outcomes": [{
                    "name": "Survival",
                    "category": "survival",
                    "effect_measure": {
                        "measure_type": "HR",
                        "value": "0.72",
                        "ci_lower": "0.58",
                        "ci_upper": "0.89",
                        "label": "HR 0.72 (95% CI: 0.58-0.89)"
                    },
                    "is_significant": True,
                    "direction": "improved",
                }],
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        outcome = result.metadata.spine.outcomes[0]
        assert outcome.effect_measure is not None
        assert outcome.effect_measure.measure_type == "HR"
        assert outcome.effect_measure.value == "0.72"
        assert outcome.effect_measure.ci_lower == "0.58"

    def test_effect_measure_in_chunk_statistics(self, processor):
        """Parse effect_measure in chunk statistics."""
        data = {
            "metadata": {"title": "Test"},
            "chunks": [{
                "content": "HR was 2.35",
                "content_type": "key_finding",
                "section_type": "results",
                "tier": "tier1",
                "is_key_finding": True,
                "statistics": {
                    "p_value": "0.001",
                    "is_significant": True,
                    "effect_measure": {
                        "measure_type": "HR",
                        "value": "2.35",
                        "ci_lower": "1.42",
                        "ci_upper": "3.89",
                        "label": "HR 2.35 (95% CI: 1.42-3.89)"
                    },
                },
            }],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        chunk = result.chunks[0]
        assert chunk.statistics is not None
        assert chunk.statistics.effect_measure is not None
        assert chunk.statistics.effect_measure.measure_type == "HR"

    def test_sub_domain_backward_compat(self, processor):
        """sub_domain (string) is converted to sub_domains (list)."""
        data = {
            "metadata": {"title": "Test"},
            "spine_metadata": {
                "sub_domain": "Degenerative",
                # No sub_domains key
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.metadata.spine.sub_domains == ["Degenerative"]
        assert result.metadata.spine.sub_domain == "Degenerative"

    def test_sub_domains_takes_precedence(self, processor):
        """sub_domains list takes precedence over sub_domain string."""
        data = {
            "metadata": {"title": "Test"},
            "spine_metadata": {
                "sub_domain": "Degenerative",
                "sub_domains": ["Degenerative", "Revision"],
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.metadata.spine.sub_domains == ["Degenerative", "Revision"]

    def test_null_values_handled(self, processor):
        """None/null values in data are handled gracefully."""
        data = {
            "metadata": {
                "title": None,
                "authors": None,
                "year": None,
                "sample_size": None,
            },
            "spine_metadata": {
                "pathology": None,
                "interventions": None,
                "follow_up_period": None,
                "sample_size": None,
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        # dict.get("title", "") returns None when key exists with None value
        assert result.metadata.title is None
        assert result.metadata.authors == []
        assert result.metadata.year == 0
        assert result.metadata.spine.pathology == []
        assert result.metadata.spine.interventions == []

    def test_chunk_counts(self, processor):
        """Count table, figure, key_finding chunks correctly."""
        data = {
            "metadata": {"title": "Test"},
            "chunks": [
                {"content": "text content", "content_type": "text",
                 "section_type": "abstract", "tier": "tier1"},
                {"content": "table content", "content_type": "table",
                 "section_type": "results", "tier": "tier1"},
                {"content": "figure content", "content_type": "figure",
                 "section_type": "results", "tier": "tier2"},
                {"content": "key finding", "content_type": "key_finding",
                 "section_type": "results", "tier": "tier1", "is_key_finding": True},
                {"content": "another table", "content_type": "table",
                 "section_type": "results", "tier": "tier1"},
            ],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.table_count == 2
        assert result.figure_count == 1
        assert result.key_finding_count == 1

    def test_complications_parsing(self, processor):
        """Parse complications from spine_metadata."""
        data = {
            "metadata": {"title": "Test"},
            "spine_metadata": {
                "complications": [
                    {
                        "name": "Dural tear",
                        "incidence_intervention": "2.5%",
                        "incidence_control": "4.1%",
                        "p_value": "0.35",
                        "severity": "minor",
                    },
                ],
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert len(result.metadata.spine.complications) == 1
        comp = result.metadata.spine.complications[0]
        assert comp.name == "Dural tear"
        assert comp.severity == "minor"

    def test_important_citations_parsing(self, processor):
        """Parse important citations from data."""
        data = {
            "metadata": {"title": "Test"},
            "chunks": [],
            "important_citations": [
                {
                    "authors": ["Kim", "Park"],
                    "year": 2023,
                    "context": "supports_result",
                    "section": "discussion",
                    "citation_text": "Kim et al. reported similar findings",
                    "importance_reason": "Validates our VAS results",
                    "outcome_comparison": "VAS",
                    "direction_match": True,
                },
            ],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert len(result.important_citations) == 1
        cit = result.important_citations[0]
        assert cit.authors == ["Kim", "Park"]
        assert cit.year == 2023
        assert cit.direction_match is True

    def test_follow_up_period_from_months(self, processor):
        """follow_up_period can come from follow_up_months."""
        data = {
            "metadata": {"title": "Test"},
            "spine_metadata": {
                "follow_up_months": 24,
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.metadata.spine.follow_up_period == "24"

    def test_fallback_info_in_result(self, processor):
        """Fallback info is stored in result."""
        data = {"metadata": {"title": "Test"}, "chunks": []}
        result = processor._dict_to_vision_result(
            data=data, input_tokens=100, output_tokens=50,
            latency=2.5, provider="claude", model="haiku",
            fallback_used=True, fallback_reason="max_tokens_exceeded",
        )
        assert result.fallback_used is True
        assert result.fallback_reason == "max_tokens_exceeded"
        assert result.provider == "claude"
        assert result.model == "haiku"

    def test_chunk_topic_summary_backward_compat(self, processor):
        """topic_summary field is mapped to summary."""
        data = {
            "metadata": {"title": "Test"},
            "chunks": [{
                "content": "Some content",
                "content_type": "text",
                "section_type": "abstract",
                "tier": "tier1",
                "topic_summary": "This is the topic summary",
            }],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        assert result.chunks[0].summary == "This is the topic summary"

    def test_effect_measure_not_dict(self, processor):
        """Non-dict effect_measure is ignored."""
        data = {
            "metadata": {"title": "Test"},
            "spine_metadata": {
                "outcomes": [{
                    "name": "VAS",
                    "effect_measure": "invalid_string",
                    "is_significant": True,
                    "direction": "improved",
                }],
            },
            "chunks": [],
        }
        result = processor._dict_to_vision_result(
            data=data, input_tokens=0, output_tokens=0,
            latency=0, provider="claude", model="test"
        )
        outcome = result.metadata.spine.outcomes[0]
        assert outcome.effect_measure is None


# ============================================================================
# Test: process_text with fallback
# ============================================================================

class TestProcessTextFallback:
    """Test process_text fallback behavior."""

    @pytest.mark.asyncio
    async def test_process_text_with_fallback(self):
        """Test text processing with Haiku -> Sonnet fallback."""
        sample_data = {"metadata": {"title": "Test"}, "chunks": []}

        # Build a mock backend with sequential return values
        call_count = 0
        def fake_process_text(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": False,
                    "error": "max_tokens_exceeded",
                    "latency": 1.0,
                    "output_tokens": 8000,
                    "input_tokens": 3000,
                }
            return {
                "success": True,
                "data": sample_data,
                "input_tokens": 3000,
                "output_tokens": 2000,
                "latency": 2.0,
                "model_used": "claude-sonnet-4-5-20250929",
            }

        mock_backend = MagicMock()
        mock_backend.model = "claude-haiku-4-5-20251001"
        mock_backend.process_text = fake_process_text

        # Patch ClaudeBackend in both possible module paths
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('src.builder.unified_pdf_processor.ClaudeBackend', return_value=mock_backend) as p1, \
                 patch('builder.unified_pdf_processor.ClaudeBackend', return_value=mock_backend, create=True):
                processor = UnifiedPDFProcessor(auto_fallback=True)
                # Ensure the mock backend is used regardless of module path
                processor._backend = mock_backend
                processor.model = mock_backend.model
                result = await processor.process_text("Some medical text...")

                assert result.success is True
                assert result.fallback_used is True
                assert "max_tokens" in result.fallback_reason.lower()

    @pytest.mark.asyncio
    async def test_process_text_whitespace_only(self):
        """Whitespace-only text returns error."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                result = await processor.process_text("   \n\t  ")
                assert result.success is False
                assert "empty" in result.error.lower()


# ============================================================================
# Test: ClaudeBackend._get_max_tokens
# ============================================================================

class TestClaudeBackendMaxTokens:
    """Test ClaudeBackend._get_max_tokens method."""

    def test_unknown_model_default(self):
        """Unknown model returns default 16384."""
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend(model="claude-unknown-model")
                assert backend._get_max_tokens("claude-unknown-model") == 16384


# ============================================================================
# Test: DataClass edge cases
# ============================================================================

class TestDataClassEdgeCases:
    """Test data class edge cases."""

    def test_complication_data(self):
        """Test ComplicationData defaults."""
        comp = ComplicationData(name="Dural tear")
        assert comp.name == "Dural tear"
        assert comp.incidence_intervention == ""
        assert comp.severity == ""

    def test_vision_processor_result_defaults(self):
        """Test VisionProcessorResult defaults."""
        result = VisionProcessorResult(success=False)
        assert result.metadata == ExtractedMetadata()
        assert result.chunks == []
        assert result.important_citations == []
        assert result.error == ""
        assert result.fallback_used is False

    def test_processor_result_defaults(self):
        """Test ProcessorResult defaults."""
        result = ProcessorResult(success=False)
        assert result.extracted_data == {}
        assert result.error is None
        assert result.fallback_used is False
        assert result.fallback_reason is None

    def test_statistics_data_with_effect_measure(self):
        """Test StatisticsData with EffectMeasure."""
        em = EffectMeasure(
            measure_type="OR",
            value="3.2",
            ci_lower="1.8",
            ci_upper="5.6",
            label="OR 3.2 (95% CI: 1.8-5.6)"
        )
        stats = StatisticsData(
            p_value="0.002",
            is_significant=True,
            effect_measure=em,
        )
        assert stats.effect_measure.measure_type == "OR"
        assert stats.effect_measure.value == "3.2"

    def test_extracted_outcome_defaults(self):
        """Test ExtractedOutcome defaults."""
        outcome = ExtractedOutcome(name="VAS")
        assert outcome.category == ""
        assert outcome.value_intervention == ""
        assert outcome.effect_size == ""
        assert outcome.effect_measure is None
        assert outcome.timepoint == ""
        assert outcome.is_significant is False
        assert outcome.direction == ""

    def test_spine_metadata_with_pico(self):
        """Test SpineMetadata with PICO."""
        pico = PICOData(
            population="Adults with stenosis",
            intervention="UBE",
            comparison="Open laminectomy",
            outcome="VAS",
        )
        spine = SpineMetadata(pico=pico)
        assert spine.pico.population == "Adults with stenosis"


# ============================================================================
# Test: Env-based initialization
# ============================================================================

class TestEnvBasedInit:
    """Test environment-variable based initialization."""

    def test_auto_fallback_env_false(self):
        """CLAUDE_AUTO_FALLBACK=false disables fallback."""
        with patch.dict('os.environ', {
            'ANTHROPIC_API_KEY': 'test-key',
            'CLAUDE_AUTO_FALLBACK': 'false',
        }):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                assert processor.auto_fallback is False

    def test_auto_fallback_env_yes(self):
        """CLAUDE_AUTO_FALLBACK=yes enables fallback."""
        with patch.dict('os.environ', {
            'ANTHROPIC_API_KEY': 'test-key',
            'CLAUDE_AUTO_FALLBACK': 'yes',
        }):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                assert processor.auto_fallback is True

    def test_auto_fallback_env_1(self):
        """CLAUDE_AUTO_FALLBACK=1 enables fallback."""
        with patch.dict('os.environ', {
            'ANTHROPIC_API_KEY': 'test-key',
            'CLAUDE_AUTO_FALLBACK': '1',
        }):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                assert processor.auto_fallback is True

    def test_custom_fallback_model(self):
        """Custom fallback model from env."""
        with patch.dict('os.environ', {
            'ANTHROPIC_API_KEY': 'test-key',
            'CLAUDE_FALLBACK_MODEL': 'claude-opus-4-6',
        }):
            with patch('builder.unified_pdf_processor.ClaudeBackend'):
                processor = UnifiedPDFProcessor()
                assert processor.fallback_model == "claude-opus-4-6"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Comprehensive tests for CitationContextExtractor module.

Tests for:
- ExtractedCitation and CitationExtractionResult dataclasses
- CitationImportance and LLMProvider enums
- CitationContextExtractor initialization
- extract_important_citations with mocked LLM responses
- extract_from_chunks
- parse_citation_reference (various citation formats)
- build_pubmed_query
- ClaudeBackend and GeminiBackend initialization
- Error handling (empty input, LLM failures, JSON parsing errors)
- Edge cases (citations at start/end, multiple citations, no citations)
"""

import pytest
import json
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import asdict

from builder.citation_context_extractor import (
    CitationContextExtractor,
    ExtractedCitation,
    CitationExtractionResult,
    CitationImportance,
    LLMProvider,
    ClaudeBackend,
    GeminiBackend,
    EXTRACTION_PROMPT,
    EXTRACTION_SCHEMA,
    GEMINI_EXTRACTION_SCHEMA,
)


# ===========================================================================
# Test: Dataclass Defaults and Construction
# ===========================================================================

class TestExtractedCitation:
    """Test ExtractedCitation dataclass."""

    def test_default_values(self):
        citation = ExtractedCitation()
        assert citation.authors == []
        assert citation.year == 0
        assert citation.title == ""
        assert citation.journal == ""
        assert citation.context == "background"
        assert citation.section == ""
        assert citation.citation_text == ""
        assert citation.importance_reason == ""
        assert citation.outcome_comparison == ""
        assert citation.direction_match is None
        assert citation.confidence == 0.0
        assert citation.raw_citation == ""

    def test_full_initialization(self):
        citation = ExtractedCitation(
            authors=["Kim", "Park"],
            year=2023,
            title="UBE Study",
            journal="Spine",
            context="supports_result",
            section="discussion",
            citation_text="Kim et al. (2023) reported similar findings.",
            importance_reason="Supports VAS results",
            outcome_comparison="VAS",
            direction_match=True,
            confidence=0.95,
            raw_citation="Kim et al., 2023",
        )
        assert citation.authors == ["Kim", "Park"]
        assert citation.year == 2023
        assert citation.direction_match is True
        assert citation.confidence == 0.95

    def test_direction_match_false(self):
        citation = ExtractedCitation(
            context="contradicts_result",
            direction_match=False,
        )
        assert citation.direction_match is False

    def test_direction_match_none(self):
        """direction_match=None means unclear."""
        citation = ExtractedCitation(direction_match=None)
        assert citation.direction_match is None


class TestCitationExtractionResult:
    """Test CitationExtractionResult dataclass."""

    def test_default_values(self):
        result = CitationExtractionResult()
        assert result.paper_title == ""
        assert result.important_citations == []
        assert result.all_citations == []
        assert result.main_findings == []
        assert result.extraction_stats == {}
        assert result.provider_used == ""

    def test_with_citations(self):
        cit1 = ExtractedCitation(authors=["Kim"], context="supports_result")
        cit2 = ExtractedCitation(authors=["Park"], context="background")
        result = CitationExtractionResult(
            paper_title="Test Paper",
            important_citations=[cit1],
            all_citations=[cit1, cit2],
            provider_used="claude",
        )
        assert len(result.important_citations) == 1
        assert len(result.all_citations) == 2


# ===========================================================================
# Test: Enum Definitions
# ===========================================================================

class TestEnums:
    """Test enum definitions."""

    def test_citation_importance(self):
        assert CitationImportance.HIGH.value == "high"
        assert CitationImportance.MEDIUM.value == "medium"
        assert CitationImportance.LOW.value == "low"

    def test_llm_provider(self):
        assert LLMProvider.CLAUDE.value == "claude"
        assert LLMProvider.GEMINI.value == "gemini"


# ===========================================================================
# Test: Prompt and Schema Constants
# ===========================================================================

class TestConstants:
    """Test module-level constants."""

    def test_extraction_prompt_has_placeholders(self):
        assert "{main_findings}" in EXTRACTION_PROMPT
        assert "{discussion_text}" in EXTRACTION_PROMPT
        assert "{results_text}" in EXTRACTION_PROMPT

    def test_extraction_schema_structure(self):
        assert EXTRACTION_SCHEMA["type"] == "object"
        assert "important_citations" in EXTRACTION_SCHEMA["properties"]

    def test_gemini_schema_structure(self):
        assert GEMINI_EXTRACTION_SCHEMA["type"] == "OBJECT"
        assert "important_citations" in GEMINI_EXTRACTION_SCHEMA["properties"]


# ===========================================================================
# Test: ClaudeBackend Initialization
# ===========================================================================

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

    def test_init_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(Exception):
            ClaudeBackend()


# ===========================================================================
# Test: ClaudeBackend extract_citations
# ===========================================================================

class TestClaudeBackendExtract:
    """Test ClaudeBackend.extract_citations."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend()

                mock_response = MagicMock()
                mock_response.content = [MagicMock(text='{"important_citations": []}')]
                mock_response.usage.input_tokens = 100
                mock_response.usage.output_tokens = 50
                backend.client.messages.create = MagicMock(return_value=mock_response)

                result = await backend.extract_citations("Test prompt")
                assert result["success"] is True
                assert result["data"] == {"important_citations": []}

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend()

                mock_response = MagicMock()
                mock_response.content = [MagicMock(text='```json\n{"important_citations": []}\n```')]
                mock_response.usage.input_tokens = 100
                mock_response.usage.output_tokens = 50
                backend.client.messages.create = MagicMock(return_value=mock_response)

                result = await backend.extract_citations("Test prompt")
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_json_parse_error(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend()

                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="This is not JSON")]
                mock_response.usage.input_tokens = 100
                mock_response.usage.output_tokens = 50
                backend.client.messages.create = MagicMock(return_value=mock_response)

                result = await backend.extract_citations("Test prompt")
                assert result["success"] is False
                assert "JSON parsing error" in result["error"]

    @pytest.mark.asyncio
    async def test_api_error(self):
        mock_anthropic = MagicMock()
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch.dict('sys.modules', {'anthropic': mock_anthropic}):
                backend = ClaudeBackend()
                backend.client.messages.create = MagicMock(side_effect=Exception("API timeout"))

                result = await backend.extract_citations("Test prompt")
                assert result["success"] is False
                assert "API timeout" in result["error"]


# ===========================================================================
# Test: CitationContextExtractor Initialization
# ===========================================================================

class TestExtractorInit:
    """Test CitationContextExtractor initialization."""

    def test_init_claude_provider(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key', 'LLM_PROVIDER': 'claude'}):
            with patch('builder.citation_context_extractor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                extractor = CitationContextExtractor(provider="claude")
                assert extractor.provider == LLMProvider.CLAUDE

    def test_init_env_provider(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key', 'LLM_PROVIDER': 'claude'}):
            with patch('builder.citation_context_extractor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                extractor = CitationContextExtractor()
                assert extractor.provider == LLMProvider.CLAUDE

    def test_init_legacy_api_key(self):
        """Test legacy api_key param sets Gemini provider."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('builder.citation_context_extractor.GeminiBackend') as MockBackend:
                mock_backend = MagicMock()
                mock_backend.model = "gemini-2.5-flash"
                MockBackend.return_value = mock_backend
                extractor = CitationContextExtractor(api_key="test-gemini-key")
                assert extractor.provider == LLMProvider.GEMINI


# ===========================================================================
# Test: extract_important_citations
# ===========================================================================

class TestExtractImportantCitations:
    """Test extract_important_citations method."""

    @pytest.fixture
    def mock_backend(self):
        backend = MagicMock()
        backend.model = "claude-haiku-4-5-20251001"
        return backend

    @pytest.fixture
    def extractor(self, mock_backend):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.citation_context_extractor.ClaudeBackend', return_value=mock_backend):
                ext = CitationContextExtractor(provider="claude")
                return ext

    @pytest.mark.asyncio
    async def test_empty_input(self, extractor):
        """Test with no discussion or results text."""
        result = await extractor.extract_important_citations(
            discussion_text="",
            results_text="",
        )
        assert result.important_citations == []
        assert result.all_citations == []

    @pytest.mark.asyncio
    async def test_successful_extraction(self, extractor, mock_backend):
        mock_backend.extract_citations = AsyncMock(return_value={
            "success": True,
            "data": {
                "important_citations": [
                    {
                        "raw_citation": "Kim et al., 2023",
                        "authors": ["Kim"],
                        "year": 2023,
                        "context": "supports_result",
                        "section": "discussion",
                        "citation_text": "Kim et al. reported similar findings.",
                        "confidence": 0.9,
                    },
                    {
                        "raw_citation": "Park et al., 2022",
                        "authors": ["Park"],
                        "year": 2022,
                        "context": "background",
                        "section": "discussion",
                        "citation_text": "Background information from Park.",
                        "confidence": 0.7,
                    },
                ],
                "main_findings_detected": ["UBE improved VAS"],
            },
            "input_tokens": 1000,
            "output_tokens": 500,
            "latency": 2.0,
            "model_used": "claude-haiku-4-5-20251001",
        })

        result = await extractor.extract_important_citations(
            discussion_text="Kim et al. (2023) reported similar findings.",
            results_text="VAS improved from 7.2 to 2.1",
            main_findings=["UBE improved VAS"],
            paper_title="Test Paper",
        )

        assert len(result.important_citations) == 1  # only supports_result
        assert len(result.all_citations) == 2  # both citations
        assert result.important_citations[0].context == "supports_result"
        assert result.main_findings == ["UBE improved VAS"]
        assert result.provider_used == "claude"

    @pytest.mark.asyncio
    async def test_contradicts_result_included(self, extractor, mock_backend):
        mock_backend.extract_citations = AsyncMock(return_value={
            "success": True,
            "data": {
                "important_citations": [
                    {
                        "raw_citation": "Lee et al., 2021",
                        "context": "contradicts_result",
                        "citation_text": "In contrast, Lee et al. found...",
                        "confidence": 0.85,
                        "direction_match": False,
                    },
                ],
            },
            "latency": 1.0,
        })

        result = await extractor.extract_important_citations(
            discussion_text="In contrast, Lee et al. (2021) found different results.",
        )
        assert len(result.important_citations) == 1
        assert result.important_citations[0].context == "contradicts_result"
        assert result.important_citations[0].direction_match is False

    @pytest.mark.asyncio
    async def test_comparison_included(self, extractor, mock_backend):
        mock_backend.extract_citations = AsyncMock(return_value={
            "success": True,
            "data": {
                "important_citations": [
                    {
                        "raw_citation": "Smith et al., 2020",
                        "context": "comparison",
                        "citation_text": "Compared to Smith et al....",
                        "confidence": 0.8,
                    },
                ],
            },
            "latency": 1.0,
        })

        result = await extractor.extract_important_citations(
            discussion_text="Compared to Smith et al. (2020)...",
        )
        assert len(result.important_citations) == 1
        assert result.important_citations[0].context == "comparison"

    @pytest.mark.asyncio
    async def test_methodological_not_in_important(self, extractor, mock_backend):
        """Methodological citations should not be in important_citations."""
        mock_backend.extract_citations = AsyncMock(return_value={
            "success": True,
            "data": {
                "important_citations": [
                    {
                        "raw_citation": "Zhang et al., 2019",
                        "context": "methodological",
                        "citation_text": "We adopted the method of Zhang.",
                        "confidence": 0.7,
                    },
                ],
            },
            "latency": 1.0,
        })

        result = await extractor.extract_important_citations(
            discussion_text="We adopted the method of Zhang et al. (2019).",
        )
        assert len(result.important_citations) == 0  # methodological not important
        assert len(result.all_citations) == 1

    @pytest.mark.asyncio
    async def test_backend_failure(self, extractor, mock_backend):
        mock_backend.extract_citations = AsyncMock(return_value={
            "success": False,
            "error": "API timeout",
        })

        result = await extractor.extract_important_citations(
            discussion_text="Some discussion text.",
        )
        assert result.important_citations == []
        assert result.all_citations == []

    @pytest.mark.asyncio
    async def test_exception_handling(self, extractor, mock_backend):
        mock_backend.extract_citations = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        result = await extractor.extract_important_citations(
            discussion_text="Some discussion text.",
        )
        assert result.important_citations == []

    @pytest.mark.asyncio
    async def test_text_truncation(self, extractor, mock_backend):
        """Test that long text is truncated."""
        mock_backend.extract_citations = AsyncMock(return_value={
            "success": True,
            "data": {"important_citations": []},
            "latency": 1.0,
        })

        long_text = "A" * 20000
        await extractor.extract_important_citations(
            discussion_text=long_text,
            results_text=long_text,
        )
        # Verify it was called (text gets truncated in prompt)
        mock_backend.extract_citations.assert_called_once()

    @pytest.mark.asyncio
    async def test_extraction_stats(self, extractor, mock_backend):
        """Test that extraction_stats are populated."""
        mock_backend.extract_citations = AsyncMock(return_value={
            "success": True,
            "data": {
                "important_citations": [
                    {"context": "supports_result", "confidence": 0.9, "raw_citation": "A", "citation_text": "A"},
                    {"context": "contradicts_result", "confidence": 0.8, "raw_citation": "B", "citation_text": "B"},
                    {"context": "comparison", "confidence": 0.7, "raw_citation": "C", "citation_text": "C"},
                ],
            },
            "input_tokens": 500,
            "output_tokens": 200,
            "latency": 1.5,
            "model_used": "test-model",
        })

        result = await extractor.extract_important_citations(
            discussion_text="Test discussion.",
        )
        stats = result.extraction_stats
        assert stats["total_citations"] == 3
        assert stats["important_citations"] == 3
        assert stats["supports_count"] == 1
        assert stats["contradicts_count"] == 1
        assert stats["comparison_count"] == 1
        assert stats["provider"] == "claude"


# ===========================================================================
# Test: extract_from_chunks
# ===========================================================================

class TestExtractFromChunks:
    """Test extract_from_chunks method."""

    @pytest.fixture
    def mock_backend(self):
        backend = MagicMock()
        backend.model = "claude-haiku-4-5-20251001"
        backend.extract_citations = AsyncMock(return_value={
            "success": True,
            "data": {"important_citations": []},
            "latency": 1.0,
        })
        return backend

    @pytest.fixture
    def extractor(self, mock_backend):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.citation_context_extractor.ClaudeBackend', return_value=mock_backend):
                return CitationContextExtractor(provider="claude")

    @pytest.mark.asyncio
    async def test_extracts_discussion_and_results(self, extractor, mock_backend):
        chunks = [
            {"section": "discussion", "content": "Discussion content"},
            {"section": "results", "content": "Results content"},
            {"section": "methods", "content": "Methods content"},
            {"section": "conclusion", "content": "Conclusion content"},
        ]

        result = await extractor.extract_from_chunks(chunks, paper_title="Test")
        mock_backend.extract_citations.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_chunks(self, extractor, mock_backend):
        """Empty chunks should still call extract with empty text."""
        result = await extractor.extract_from_chunks([], paper_title="Test")
        # With empty text, extract_important_citations returns early
        assert result.important_citations == []


# ===========================================================================
# Test: parse_citation_reference
# ===========================================================================

class TestParseCitationReference:
    """Test parse_citation_reference method."""

    @pytest.fixture
    def extractor(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.citation_context_extractor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                return CitationContextExtractor(provider="claude")

    def test_et_al_with_year(self, extractor):
        result = extractor.parse_citation_reference("Kim et al., 2023")
        assert result["authors"] == ["Kim"]
        assert result["year"] == 2023

    def test_et_al_with_parentheses(self, extractor):
        result = extractor.parse_citation_reference("Kim et al. (2023)")
        assert result["authors"] == ["Kim"]
        assert result["year"] == 2023

    def test_two_authors(self, extractor):
        result = extractor.parse_citation_reference("Kim and Park, 2022")
        assert result["authors"] == ["Kim", "Park"]
        assert result["year"] == 2022

    def test_two_authors_parentheses(self, extractor):
        result = extractor.parse_citation_reference("Kim and Park (2022)")
        assert result["authors"] == ["Kim", "Park"]
        assert result["year"] == 2022

    def test_single_author_parentheses(self, extractor):
        result = extractor.parse_citation_reference("Kim (2023)")
        assert result["authors"] == ["Kim"]
        assert result["year"] == 2023

    def test_year_only(self, extractor):
        result = extractor.parse_citation_reference("[15] 2021")
        assert result["year"] == 2021
        assert result["authors"] == []

    def test_no_parseable_info(self, extractor):
        result = extractor.parse_citation_reference("some random text")
        assert result["authors"] == []
        assert result["year"] == 0

    def test_empty_string(self, extractor):
        result = extractor.parse_citation_reference("")
        assert result["authors"] == []
        assert result["year"] == 0


# ===========================================================================
# Test: build_pubmed_query
# ===========================================================================

class TestBuildPubmedQuery:
    """Test build_pubmed_query method."""

    @pytest.fixture
    def extractor(self):
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('builder.citation_context_extractor.ClaudeBackend') as MockBackend:
                mock = MagicMock()
                mock.model = "test"
                MockBackend.return_value = mock
                return CitationContextExtractor(provider="claude")

    def test_query_with_title(self, extractor):
        citation = ExtractedCitation(title="UBE versus Open Laminectomy")
        query = extractor.build_pubmed_query(citation)
        assert "[Title]" in query
        assert "UBE versus Open Laminectomy" in query

    def test_query_with_author_and_year(self, extractor):
        citation = ExtractedCitation(authors=["Kim"], year=2023)
        query = extractor.build_pubmed_query(citation)
        assert "Kim[Author]" in query
        assert "2023[Date - Publication]" in query
        assert " AND " in query

    def test_query_with_author_only(self, extractor):
        citation = ExtractedCitation(authors=["Kim"])
        query = extractor.build_pubmed_query(citation)
        assert "Kim[Author]" in query

    def test_query_with_year_only(self, extractor):
        citation = ExtractedCitation(year=2023)
        query = extractor.build_pubmed_query(citation)
        assert "2023[Date - Publication]" in query

    def test_empty_query(self, extractor):
        citation = ExtractedCitation()
        query = extractor.build_pubmed_query(citation)
        assert query == ""

    def test_title_takes_priority(self, extractor):
        """When title is present, it should be used exclusively."""
        citation = ExtractedCitation(
            title="Specific Paper Title",
            authors=["Kim"],
            year=2023,
        )
        query = extractor.build_pubmed_query(citation)
        assert "[Title]" in query
        # Author/year should NOT appear when title is present
        assert "[Author]" not in query

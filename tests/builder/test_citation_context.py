"""Tests for citation_context_extractor.py.

Tests:
- Citation extraction from discussion/results text
- Citation pattern parsing
- Multiple LLM providers (Claude/Gemini)
- Error handling and edge cases
"""

import pytest
import json
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
)


class TestExtractedCitation:
    """Test ExtractedCitation dataclass."""

    def test_citation_initialization(self):
        """Test basic citation creation."""
        citation = ExtractedCitation(
            authors=["Kim", "Park"],
            year=2023,
            title="Test Study",
            context="supports_result",
            citation_text="Our findings match Kim et al. (2023).",
            confidence=0.9
        )

        assert citation.authors == ["Kim", "Park"]
        assert citation.year == 2023
        assert citation.title == "Test Study"
        assert citation.context == "supports_result"
        assert citation.confidence == 0.9

    def test_citation_defaults(self):
        """Test citation with default values."""
        citation = ExtractedCitation()

        assert citation.authors == []
        assert citation.year == 0
        assert citation.title == ""
        assert citation.context == "background"
        assert citation.confidence == 0.0


class TestCitationExtractionResult:
    """Test CitationExtractionResult dataclass."""

    def test_result_initialization(self):
        """Test result initialization."""
        result = CitationExtractionResult(
            paper_title="Test Paper",
            provider_used="claude"
        )

        assert result.paper_title == "Test Paper"
        assert result.provider_used == "claude"
        assert result.important_citations == []
        assert result.all_citations == []
        assert result.main_findings == []
        assert result.extraction_stats == {}


class TestCitationContextExtractor:
    """Test CitationContextExtractor class."""

    @pytest.fixture
    def mock_claude_response(self):
        """Create mock Claude API response."""
        return {
            "success": True,
            "data": {
                "important_citations": [
                    {
                        "raw_citation": "Kim et al., 2023",
                        "authors": ["Kim"],
                        "year": 2023,
                        "title": "Study on UBE",
                        "context": "supports_result",
                        "section": "discussion",
                        "citation_text": "Our results are consistent with Kim et al. (2023).",
                        "importance_reason": "Confirms our findings",
                        "outcome_comparison": "VAS",
                        "direction_match": True,
                        "confidence": 0.9
                    }
                ],
                "main_findings_detected": ["UBE showed better outcomes"]
            },
            "input_tokens": 1000,
            "output_tokens": 200,
            "latency": 1.5,
            "model_used": "claude-haiku-4-5-20251001"
        }

    @pytest.fixture
    def mock_gemini_response(self):
        """Create mock Gemini API response."""
        return {
            "success": True,
            "data": {
                "important_citations": [
                    {
                        "raw_citation": "Park et al., 2022",
                        "authors": ["Park"],
                        "year": 2022,
                        "context": "contradicts_result",
                        "citation_text": "Unlike Park et al. (2022), we found better outcomes.",
                        "confidence": 0.85
                    }
                ]
            },
            "input_tokens": 800,
            "output_tokens": 150,
            "latency": 1.2,
            "model_used": "gemini-2.5-flash-preview-05-20"
        }

    @pytest.mark.asyncio
    async def test_extract_citations_claude(self, mock_claude_response):
        """Test citation extraction with Claude backend."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            # Mock backend
            extractor._backend.extract_citations = AsyncMock(return_value=mock_claude_response)

            result = await extractor.extract_important_citations(
                discussion_text="Our results are consistent with Kim et al. (2023).",
                results_text="VAS improved from 7.0 to 2.0.",
                main_findings=["UBE showed better outcomes"],
                paper_title="Test Paper"
            )

            assert result.paper_title == "Test Paper"
            assert result.provider_used == "claude"
            assert len(result.important_citations) == 1

            citation = result.important_citations[0]
            assert citation.authors == ["Kim"]
            assert citation.year == 2023
            assert citation.context == "supports_result"
            assert citation.confidence == 0.9

            # Check stats
            assert result.extraction_stats["total_citations"] == 1
            assert result.extraction_stats["important_citations"] == 1
            assert result.extraction_stats["supports_count"] == 1

    @pytest.mark.asyncio
    async def test_extract_citations_gemini(self, mock_gemini_response):
        """Test citation extraction with Gemini backend."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="gemini")

            # Mock backend
            extractor._backend.extract_citations = AsyncMock(return_value=mock_gemini_response)

            result = await extractor.extract_important_citations(
                discussion_text="Unlike Park et al. (2022), we found better outcomes.",
                paper_title="Test Paper"
            )

            assert result.provider_used == "gemini"
            assert len(result.important_citations) == 1

            citation = result.important_citations[0]
            assert citation.authors == ["Park"]
            assert citation.year == 2022
            assert citation.context == "contradicts_result"

            # Check stats
            assert result.extraction_stats["contradicts_count"] == 1

    @pytest.mark.asyncio
    async def test_extract_citations_empty_text(self):
        """Test extraction with empty text."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            result = await extractor.extract_important_citations(
                discussion_text="",
                results_text=""
            )

            assert len(result.important_citations) == 0
            assert len(result.all_citations) == 0

    @pytest.mark.asyncio
    async def test_extract_citations_api_failure(self):
        """Test handling of API failure."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            # Mock API failure
            extractor._backend.extract_citations = AsyncMock(return_value={
                "success": False,
                "error": "API error"
            })

            result = await extractor.extract_important_citations(
                discussion_text="Some text with citations.",
                paper_title="Test Paper"
            )

            # Should return empty result
            assert len(result.important_citations) == 0

    @pytest.mark.asyncio
    async def test_extract_from_chunks(self, mock_claude_response):
        """Test extraction from chunk list."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")
            extractor._backend.extract_citations = AsyncMock(return_value=mock_claude_response)

            chunks = [
                {
                    "section": "discussion",
                    "content": "Our results match Kim et al. (2023)."
                },
                {
                    "section": "results",
                    "content": "VAS improved significantly."
                },
                {
                    "section": "introduction",
                    "content": "Background information."
                }
            ]

            result = await extractor.extract_from_chunks(
                chunks=chunks,
                main_findings=["Better outcomes"],
                paper_title="Test Paper"
            )

            assert len(result.important_citations) == 1

    @pytest.mark.asyncio
    async def test_extract_filters_background_citations(self, mock_claude_response):
        """Test that background citations are filtered out."""
        # Add a background citation to mock response
        mock_response = mock_claude_response.copy()
        mock_response["data"]["important_citations"].append({
            "raw_citation": "Lee et al., 2021",
            "context": "background",
            "citation_text": "Background study by Lee et al.",
            "confidence": 0.7
        })

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")
            extractor._backend.extract_citations = AsyncMock(return_value=mock_response)

            result = await extractor.extract_important_citations(
                discussion_text="Text with citations.",
                paper_title="Test"
            )

            # Should have 2 all_citations but only 1 important
            assert len(result.all_citations) == 2
            assert len(result.important_citations) == 1

            # Important citations should not include background
            for citation in result.important_citations:
                assert citation.context != "background"

    def test_parse_citation_reference_et_al(self):
        """Test parsing 'et al.' style citations."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            # With comma
            result1 = extractor.parse_citation_reference("Kim et al., 2023")
            assert result1["authors"] == ["Kim"]
            assert result1["year"] == 2023

            # Without comma
            result2 = extractor.parse_citation_reference("Kim et al. (2023)")
            assert result2["authors"] == ["Kim"]
            assert result2["year"] == 2023

    def test_parse_citation_reference_two_authors(self):
        """Test parsing two-author citations."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            result = extractor.parse_citation_reference("Kim and Park, 2023")
            assert result["authors"] == ["Kim", "Park"]
            assert result["year"] == 2023

    def test_parse_citation_reference_single_author(self):
        """Test parsing single author citations."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            result = extractor.parse_citation_reference("Smith (2022)")
            assert result["authors"] == ["Smith"]
            assert result["year"] == 2022

    def test_parse_citation_reference_year_only(self):
        """Test parsing citations with only year."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            result = extractor.parse_citation_reference("[15] (2021)")
            assert result["year"] == 2021

    def test_parse_citation_reference_no_match(self):
        """Test parsing invalid citations."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            result = extractor.parse_citation_reference("invalid citation")
            assert result["authors"] == []
            assert result["year"] == 0

    def test_build_pubmed_query_with_title(self):
        """Test PubMed query building with title."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            citation = ExtractedCitation(
                title="Study on Spine Surgery",
                authors=["Kim"],
                year=2023
            )

            query = extractor.build_pubmed_query(citation)
            assert '"Study on Spine Surgery"[Title]' in query

    def test_build_pubmed_query_with_author_year(self):
        """Test PubMed query building with author and year."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            citation = ExtractedCitation(
                authors=["Kim"],
                year=2023
            )

            query = extractor.build_pubmed_query(citation)
            assert "Kim[Author]" in query
            assert "2023[Date - Publication]" in query
            assert " AND " in query

    def test_build_pubmed_query_empty_citation(self):
        """Test PubMed query building with empty citation."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            citation = ExtractedCitation()
            query = extractor.build_pubmed_query(citation)
            assert query == ""

    @pytest.mark.asyncio
    async def test_multiple_citation_contexts(self, mock_claude_response):
        """Test extraction of citations with different contexts."""
        mock_response = {
            "success": True,
            "data": {
                "important_citations": [
                    {
                        "raw_citation": "Kim et al., 2023",
                        "context": "supports_result",
                        "citation_text": "Supports our findings.",
                        "confidence": 0.9
                    },
                    {
                        "raw_citation": "Park et al., 2022",
                        "context": "contradicts_result",
                        "citation_text": "Contradicts our findings.",
                        "confidence": 0.85
                    },
                    {
                        "raw_citation": "Lee et al., 2021",
                        "context": "comparison",
                        "citation_text": "Comparison study.",
                        "confidence": 0.8
                    },
                    {
                        "raw_citation": "Chen et al., 2020",
                        "context": "methodological",
                        "citation_text": "Methodological reference.",
                        "confidence": 0.75
                    }
                ]
            },
            "input_tokens": 1000,
            "output_tokens": 300,
            "latency": 2.0,
            "model_used": "claude-haiku-4-5"
        }

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")
            extractor._backend.extract_citations = AsyncMock(return_value=mock_response)

            result = await extractor.extract_important_citations(
                discussion_text="Text with various citations.",
                paper_title="Test"
            )

            # All citations should be in all_citations
            assert len(result.all_citations) == 4

            # Only supports/contradicts/comparison in important
            assert len(result.important_citations) == 3

            # Check stats
            stats = result.extraction_stats
            assert stats["supports_count"] == 1
            assert stats["contradicts_count"] == 1
            assert stats["comparison_count"] == 1

    @pytest.mark.asyncio
    async def test_long_text_truncation(self):
        """Test that very long text is truncated."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="claude")

            # Create very long text (over 8000 chars)
            long_text = "word " * 2000

            # Mock to capture what was sent
            async def mock_extract(prompt):
                # Check prompt doesn't contain full long text
                assert len(prompt) < len(long_text) * 2
                return {"success": True, "data": {"important_citations": []}}

            extractor._backend.extract_citations = mock_extract

            result = await extractor.extract_important_citations(
                discussion_text=long_text,
                results_text=long_text
            )

    def test_provider_selection_default(self):
        """Test default provider selection."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}, clear=True):
            extractor = CitationContextExtractor()
            assert extractor.provider == LLMProvider.CLAUDE

    def test_provider_selection_env_var(self):
        """Test provider selection from environment variable."""
        with patch.dict('os.environ', {
            'LLM_PROVIDER': 'gemini',
            'GEMINI_API_KEY': 'test-key'
        }):
            extractor = CitationContextExtractor()
            assert extractor.provider == LLMProvider.GEMINI

    def test_provider_selection_explicit(self):
        """Test explicit provider selection."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            extractor = CitationContextExtractor(provider="gemini")
            assert extractor.provider == LLMProvider.GEMINI

    def test_legacy_api_key_parameter(self):
        """Test legacy api_key parameter sets Gemini."""
        with patch.dict('os.environ', {}, clear=True):
            extractor = CitationContextExtractor(api_key="legacy-key")
            assert extractor.provider == LLMProvider.GEMINI


class TestClaudeBackend:
    """Test ClaudeBackend class."""

    def test_initialization_missing_api_key(self):
        """Test error when API key is missing."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(Exception):  # LLMError
                ClaudeBackend()

    def test_initialization_with_api_key(self):
        """Test successful initialization."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('anthropic.Anthropic'):
                backend = ClaudeBackend()
                assert backend.model

    @pytest.mark.asyncio
    async def test_extract_citations_success(self):
        """Test successful citation extraction."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            # Mock anthropic client
            mock_message = Mock()
            mock_message.content = [Mock(text='{"important_citations": []}')]
            mock_message.usage.input_tokens = 100
            mock_message.usage.output_tokens = 50

            mock_client = Mock()
            mock_client.messages.create = Mock(return_value=mock_message)

            with patch('anthropic.Anthropic', return_value=mock_client):
                backend = ClaudeBackend()
                result = await backend.extract_citations("test prompt")

                assert result["success"] is True
                assert "data" in result
                assert result["input_tokens"] == 100
                assert result["output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_extract_citations_json_error(self):
        """Test handling of JSON parsing error."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            mock_message = Mock()
            mock_message.content = [Mock(text='invalid json')]
            mock_message.usage.input_tokens = 100
            mock_message.usage.output_tokens = 50

            mock_client = Mock()
            mock_client.messages.create = Mock(return_value=mock_message)

            with patch('anthropic.Anthropic', return_value=mock_client):
                backend = ClaudeBackend()
                result = await backend.extract_citations("test prompt")

                assert result["success"] is False
                assert "error" in result


class TestGeminiBackend:
    """Test GeminiBackend class."""

    def test_initialization_missing_api_key(self):
        """Test error when API key is missing."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(Exception):  # LLMError
                GeminiBackend()

    def test_initialization_with_api_key(self):
        """Test successful initialization."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            with patch('google.genai.Client'):
                backend = GeminiBackend()
                assert backend.model

    @pytest.mark.asyncio
    async def test_extract_citations_success(self):
        """Test successful citation extraction."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test-key'}):
            # Mock Gemini response
            mock_response = Mock()
            mock_response.text = '{"important_citations": []}'
            mock_response.usage_metadata.prompt_token_count = 80
            mock_response.usage_metadata.candidates_token_count = 40

            mock_client = Mock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

            # Mock Part.from_text
            mock_part = Mock()

            with patch('google.genai.Client', return_value=mock_client):
                with patch('google.genai.types.Part') as mock_part_class:
                    mock_part_class.from_text.return_value = mock_part

                    backend = GeminiBackend()
                    result = await backend.extract_citations("test prompt")

                    assert result["success"] is True
                    assert "data" in result
                    assert result["input_tokens"] == 80
                    assert result["output_tokens"] == 40

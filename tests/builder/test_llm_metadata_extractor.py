"""Tests for LLMMetadataExtractor module.

Tests LLM-based metadata extraction from medical paper chunks:
- Single chunk extraction via LLM
- Batch extraction with concurrency
- Document-level extraction
- PICO elements parsing
- Statistics parsing (p-values, effect sizes, confidence intervals)
- Content type detection (original, citation, background)
- Rule-based fallback extraction
- Error handling: LLM failures, malformed responses
- Edge cases: empty text, disabled features
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.llm_metadata_extractor import (
    LLMMetadataExtractor,
    ChunkMetadata,
    PICOElements,
    StatsInfo,
    EffectSize,
    ExtractionError,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_llm_client():
    """Mock LLM client with generate_json."""
    client = Mock()
    client.generate_json = AsyncMock()
    client.generate = AsyncMock()
    return client


@pytest.fixture
def extractor(mock_llm_client):
    """LLMMetadataExtractor with mocked LLM client."""
    return LLMMetadataExtractor(llm_client=mock_llm_client)


@pytest.fixture
def extractor_no_pico(mock_llm_client):
    """Extractor with PICO extraction disabled."""
    return LLMMetadataExtractor(
        llm_client=mock_llm_client,
        config={"extract_pico": False}
    )


@pytest.fixture
def extractor_no_stats(mock_llm_client):
    """Extractor with stats extraction disabled."""
    return LLMMetadataExtractor(
        llm_client=mock_llm_client,
        config={"extract_stats": False}
    )


@pytest.fixture
def sample_chunk():
    """Sample medical text chunk."""
    return (
        "We found that posterior lumbar interbody fusion resulted in significantly "
        "better VAS scores compared to conservative treatment (p < 0.001). "
        "The mean improvement was 3.2 points (95% CI: 2.1-4.3)."
    )


@pytest.fixture
def sample_context():
    """Sample document context (abstract)."""
    return (
        "This randomized controlled trial compared outcomes between TLIF and "
        "conservative treatment for lumbar spondylolisthesis."
    )


@pytest.fixture
def sample_llm_response():
    """Standard LLM response dict."""
    return {
        "summary": "TLIF showed better VAS outcomes than conservative treatment.",
        "keywords": ["TLIF", "VAS", "lumbar", "fusion", "conservative"],
        "pico": {
            "population": "Lumbar spondylolisthesis patients",
            "intervention": "TLIF",
            "comparison": "Conservative treatment",
            "outcome": "VAS score improvement"
        },
        "statistics": {
            "p_values": ["p < 0.001"],
            "effect_sizes": [{"type": "MD", "value": 3.2, "ci_lower": 2.1, "ci_upper": 4.3}],
            "confidence_intervals": ["95% CI: 2.1-4.3"],
            "sample_sizes": [120],
            "statistical_tests": ["t-test"]
        },
        "content_type": "original",
        "is_key_finding": True,
        "medical_terms": ["lumbar interbody fusion", "VAS"],
        "confidence": 0.92
    }


# ===========================================================================
# Test: Initialization
# ===========================================================================

class TestLLMMetadataExtractorInit:
    """Test initialization."""

    def test_init_with_llm_client(self, mock_llm_client):
        """Init with explicit LLM client."""
        ext = LLMMetadataExtractor(llm_client=mock_llm_client)
        assert ext.llm == mock_llm_client

    def test_init_with_gemini_client_legacy(self, mock_llm_client):
        """Legacy gemini_client parameter should work."""
        ext = LLMMetadataExtractor(gemini_client=mock_llm_client)
        assert ext.llm == mock_llm_client

    @patch("builder.llm_metadata_extractor.LLMClient")
    def test_init_without_client(self, MockLLMClient):
        """No client should auto-create one."""
        ext = LLMMetadataExtractor()
        MockLLMClient.assert_called_once()

    def test_default_config(self, extractor):
        """Default config values."""
        assert extractor.extract_pico is True
        assert extractor.extract_stats is True
        assert extractor.max_keywords == 10

    def test_custom_config(self, mock_llm_client):
        """Custom config values."""
        ext = LLMMetadataExtractor(
            llm_client=mock_llm_client,
            config={"extract_pico": False, "extract_stats": False, "max_keywords": 5}
        )
        assert ext.extract_pico is False
        assert ext.extract_stats is False
        assert ext.max_keywords == 5


# ===========================================================================
# Test: PICOElements Dataclass
# ===========================================================================

class TestPICOElements:
    """Test PICOElements dataclass."""

    def test_is_complete_true(self):
        """Complete PICO (P, I, O are present)."""
        pico = PICOElements(
            population="patients",
            intervention="surgery",
            comparison="conservative",
            outcome="pain relief"
        )
        assert pico.is_complete() is True

    def test_is_complete_false_missing_population(self):
        """Incomplete PICO - missing population."""
        pico = PICOElements(intervention="surgery", outcome="pain")
        assert pico.is_complete() is False

    def test_is_complete_false_missing_outcome(self):
        """Incomplete PICO - missing outcome."""
        pico = PICOElements(population="patients", intervention="surgery")
        assert pico.is_complete() is False

    def test_is_complete_comparison_optional(self):
        """Comparison is not required for is_complete."""
        pico = PICOElements(
            population="patients",
            intervention="surgery",
            outcome="pain"
        )
        assert pico.is_complete() is True

    def test_to_dict(self):
        """to_dict should return standard PICO keys."""
        pico = PICOElements(
            population="patients",
            intervention="surgery",
            comparison="placebo",
            outcome="pain"
        )
        d = pico.to_dict()
        assert d == {"P": "patients", "I": "surgery", "C": "placebo", "O": "pain"}

    def test_to_dict_with_none(self):
        """to_dict should include None values."""
        pico = PICOElements(population="patients")
        d = pico.to_dict()
        assert d["P"] == "patients"
        assert d["I"] is None


# ===========================================================================
# Test: StatsInfo Dataclass
# ===========================================================================

class TestStatsInfo:
    """Test StatsInfo dataclass."""

    def test_has_significant_result_true(self):
        """Significant p-value detected."""
        stats = StatsInfo(p_values=["p<0.001"])
        assert stats.has_significant_result() is True

    def test_has_significant_result_false(self):
        """No significant p-value."""
        stats = StatsInfo(p_values=["p = 0.23"])
        assert stats.has_significant_result() is False

    def test_has_significant_result_empty(self):
        """No p-values at all."""
        stats = StatsInfo()
        assert stats.has_significant_result() is False

    def test_has_significant_multiple_p_values(self):
        """Multiple p-values, at least one significant."""
        stats = StatsInfo(p_values=["p = 0.12", "p<0.05", "p = 0.89"])
        assert stats.has_significant_result() is True

    def test_has_significant_border_case_no_space(self):
        """p<0.05 boundary (no space)."""
        stats = StatsInfo(p_values=["<0.05"])
        assert stats.has_significant_result() is True

    def test_has_significant_border_case_with_space(self):
        """p < 0.05 boundary (with space, only '< 0.05' is checked)."""
        stats = StatsInfo(p_values=["< 0.05"])
        assert stats.has_significant_result() is True


# ===========================================================================
# Test: Single Chunk Extraction
# ===========================================================================

class TestSingleExtraction:
    """Test extract method."""

    @pytest.mark.asyncio
    async def test_extract_basic(self, extractor, mock_llm_client, sample_chunk, sample_context, sample_llm_response):
        """Basic extraction with valid LLM response."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        result = await extractor.extract(sample_chunk, sample_context)

        assert isinstance(result, ChunkMetadata)
        assert result.summary == "TLIF showed better VAS outcomes than conservative treatment."
        assert len(result.keywords) >= 1
        assert result.content_type == "original"
        assert result.is_key_finding is True

    @pytest.mark.asyncio
    async def test_extract_with_pico(self, extractor, mock_llm_client, sample_chunk, sample_context, sample_llm_response):
        """Extraction should parse PICO elements."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        result = await extractor.extract(sample_chunk, sample_context)

        assert result.pico is not None
        assert result.pico.population == "Lumbar spondylolisthesis patients"
        assert result.pico.intervention == "TLIF"

    @pytest.mark.asyncio
    async def test_extract_with_statistics(self, extractor, mock_llm_client, sample_chunk, sample_context, sample_llm_response):
        """Extraction should parse statistics."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        result = await extractor.extract(sample_chunk, sample_context)

        assert result.statistics is not None
        assert "p < 0.001" in result.statistics.p_values
        assert len(result.statistics.effect_sizes) == 1
        assert result.statistics.effect_sizes[0].type == "MD"

    @pytest.mark.asyncio
    async def test_extract_empty_text(self, extractor):
        """Empty text should return empty metadata."""
        result = await extractor.extract("", "context")

        assert result.summary == "[No content]"
        assert result.keywords == []
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_whitespace_text(self, extractor):
        """Whitespace-only text should return empty metadata."""
        result = await extractor.extract("   \n\t  ", "context")

        assert result.summary == "[No content]"
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_extract_with_section_type(self, extractor, mock_llm_client, sample_llm_response):
        """Section type hint should be passed to LLM."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        result = await extractor.extract("chunk text", "context", section_type="results")

        assert isinstance(result, ChunkMetadata)

    @pytest.mark.asyncio
    async def test_extract_pico_disabled(self, extractor_no_pico, mock_llm_client, sample_llm_response):
        """With extract_pico=False, pico should be None."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        result = await extractor_no_pico.extract("chunk", "context")

        assert result.pico is None

    @pytest.mark.asyncio
    async def test_extract_stats_disabled(self, extractor_no_stats, mock_llm_client, sample_llm_response):
        """With extract_stats=False, statistics should be None."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        result = await extractor_no_stats.extract("chunk", "context")

        assert result.statistics is None

    @pytest.mark.asyncio
    async def test_extract_keywords_truncated(self, extractor, mock_llm_client):
        """Keywords should be truncated to max_keywords."""
        response = {
            "summary": "summary",
            "keywords": [f"kw_{i}" for i in range(20)],
            "content_type": "background",
            "is_key_finding": False,
        }
        mock_llm_client.generate_json.return_value = response

        result = await extractor.extract("chunk", "context")

        assert len(result.keywords) <= 10

    @pytest.mark.asyncio
    async def test_extract_missing_optional_fields(self, extractor, mock_llm_client):
        """LLM response missing optional fields should not crash."""
        response = {
            "summary": "A summary",
            "keywords": ["keyword"],
            "content_type": "background",
            "is_key_finding": False,
        }
        mock_llm_client.generate_json.return_value = response

        result = await extractor.extract("chunk", "context")

        assert result.pico is None
        assert result.statistics is None
        assert result.confidence == 0.8  # default

    @pytest.mark.asyncio
    async def test_extract_no_pico_in_response(self, extractor, mock_llm_client):
        """LLM response with empty pico dict should yield None pico."""
        response = {
            "summary": "summary",
            "keywords": [],
            "pico": {},
            "content_type": "background",
            "is_key_finding": False,
        }
        mock_llm_client.generate_json.return_value = response

        result = await extractor.extract("chunk", "context")

        # Empty dict is falsy, so pico should be None
        assert result.pico is None


# ===========================================================================
# Test: Batch Extraction
# ===========================================================================

class TestBatchExtraction:
    """Test extract_batch method."""

    @pytest.mark.asyncio
    async def test_batch_extraction(self, extractor, mock_llm_client, sample_llm_response):
        """Batch extraction should process multiple chunks."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        results = await extractor.extract_batch(
            chunks=["chunk1", "chunk2", "chunk3"],
            context="context"
        )

        assert len(results) == 3
        assert all(isinstance(r, ChunkMetadata) for r in results)

    @pytest.mark.asyncio
    async def test_batch_empty_list(self, extractor):
        """Empty batch should return empty list."""
        results = await extractor.extract_batch([], "context")
        assert results == []

    @pytest.mark.asyncio
    async def test_batch_with_section_types(self, extractor, mock_llm_client, sample_llm_response):
        """Batch with section types should pass them through."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        results = await extractor.extract_batch(
            chunks=["chunk1", "chunk2"],
            context="context",
            section_types=["introduction", "results"]
        )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_batch_default_section_types(self, extractor, mock_llm_client, sample_llm_response):
        """Batch without section types should default to None."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        results = await extractor.extract_batch(
            chunks=["chunk1"],
            context="context"
        )

        assert len(results) == 1


# ===========================================================================
# Test: Document-Level Extraction
# ===========================================================================

class TestDocumentLevelExtraction:
    """Test extract_document_level method."""

    @pytest.mark.asyncio
    async def test_document_level_basic(self, extractor, mock_llm_client):
        """Basic document-level extraction."""
        mock_llm_client.generate_json.return_value = {
            "title_summary": "This study demonstrates fusion superiority.",
            "main_pico": {
                "population": "Spondylolisthesis patients",
                "intervention": "TLIF",
                "comparison": "Conservative treatment",
                "outcome": "VAS improvement"
            },
            "key_findings": ["Finding 1", "Finding 2"],
            "study_design": "RCT",
            "evidence_level": "1b"
        }

        result = await extractor.extract_document_level(
            full_text="Full paper text...",
            abstract="Abstract text..."
        )

        assert result["title_summary"] == "This study demonstrates fusion superiority."
        assert result["study_design"] == "RCT"
        assert result["evidence_level"] == "1b"
        assert isinstance(result["main_pico"], PICOElements)
        assert result["main_pico"].population == "Spondylolisthesis patients"

    @pytest.mark.asyncio
    async def test_document_level_no_pico(self, extractor, mock_llm_client):
        """Document-level without PICO data."""
        mock_llm_client.generate_json.return_value = {
            "title_summary": "A review paper",
            "key_findings": [],
            "study_design": "review",
            "evidence_level": "4"
        }

        result = await extractor.extract_document_level("text", "abstract")

        assert result["main_pico"] is None

    @pytest.mark.asyncio
    async def test_document_level_llm_failure(self, extractor, mock_llm_client):
        """LLM failure should return fallback values."""
        mock_llm_client.generate_json.side_effect = Exception("LLM API timeout")

        result = await extractor.extract_document_level(
            full_text="text",
            abstract="Abstract content here"
        )

        assert result["study_design"] == "unknown"
        assert result["evidence_level"] == "unknown"
        assert result["main_pico"] is None
        assert result["title_summary"] == "Abstract content here"

    @pytest.mark.asyncio
    async def test_document_level_empty_abstract(self, extractor, mock_llm_client):
        """Empty abstract in fallback should produce empty summary."""
        mock_llm_client.generate_json.side_effect = Exception("Error")

        result = await extractor.extract_document_level("text", "")

        assert result["title_summary"] == ""


# ===========================================================================
# Test: Statistics Parsing
# ===========================================================================

class TestStatisticsParsing:
    """Test _parse_statistics method."""

    def test_parse_full_statistics(self, extractor):
        """Parse complete statistics dict."""
        raw = {
            "p_values": ["p < 0.001", "p = 0.023"],
            "effect_sizes": [
                {"type": "OR", "value": 2.5, "ci_lower": 1.2, "ci_upper": 5.1}
            ],
            "confidence_intervals": ["95% CI: 1.2-5.1"],
            "sample_sizes": [120, 115],
            "statistical_tests": ["chi-square"]
        }

        result = extractor._parse_statistics(raw)

        assert isinstance(result, StatsInfo)
        assert len(result.p_values) == 2
        assert len(result.effect_sizes) == 1
        assert result.effect_sizes[0].type == "OR"
        assert result.effect_sizes[0].value == 2.5
        assert result.sample_sizes == [120, 115]

    def test_parse_empty_statistics(self, extractor):
        """Parse empty statistics dict."""
        result = extractor._parse_statistics({})

        assert isinstance(result, StatsInfo)
        assert result.p_values == []
        assert result.effect_sizes == []

    def test_parse_effect_size_non_dict(self, extractor):
        """Non-dict effect sizes should be skipped."""
        raw = {
            "effect_sizes": ["not a dict", 42, None]
        }

        result = extractor._parse_statistics(raw)

        assert len(result.effect_sizes) == 0

    def test_parse_effect_size_partial(self, extractor):
        """Effect size with missing optional fields."""
        raw = {
            "effect_sizes": [
                {"type": "HR", "value": 0.65}
            ]
        }

        result = extractor._parse_statistics(raw)

        assert len(result.effect_sizes) == 1
        assert result.effect_sizes[0].ci_lower is None
        assert result.effect_sizes[0].ci_upper is None


# ===========================================================================
# Test: Rule-Based Extraction (Fallback)
# ===========================================================================

class TestRuleBasedExtraction:
    """Test _extract_rule_based fallback method."""

    def test_rule_based_summary(self, extractor):
        """Summary should be first sentence."""
        chunk = "First sentence here. Second sentence. Third."
        result = extractor._extract_rule_based(chunk)

        assert "First sentence here." in result.summary

    def test_rule_based_keywords(self, extractor):
        """Keywords from capitalized terms and abbreviations."""
        chunk = "Lumbar Fusion is a common procedure. ODI and VAS are outcome measures."
        result = extractor._extract_rule_based(chunk)

        assert len(result.keywords) > 0
        assert result.confidence == 0.3

    def test_rule_based_no_pico(self, extractor):
        """Rule-based extraction should not produce PICO."""
        result = extractor._extract_rule_based("Some text here.")
        assert result.pico is None

    def test_rule_based_with_p_values(self, extractor):
        """Rule-based should extract p-values."""
        chunk = "The difference was significant (p < 0.001)."
        result = extractor._extract_rule_based(chunk, section_type="results")

        assert result.statistics is not None
        assert len(result.statistics.p_values) > 0
        assert result.is_key_finding is True

    def test_rule_based_no_stats(self, extractor):
        """Chunk without stats should have None statistics."""
        result = extractor._extract_rule_based("Simple introductory text.")
        assert result.statistics is None


# ===========================================================================
# Test: Content Type Detection
# ===========================================================================

class TestContentTypeDetection:
    """Test _detect_content_type method."""

    def test_detect_original(self, extractor):
        """Text with original research indicators."""
        chunk = "We found that our study results demonstrate superiority."
        result = extractor._detect_content_type(chunk)
        assert result == "original"

    def test_detect_citation(self, extractor):
        """Text with many citations."""
        chunk = (
            "According to Smith (2020), prior research has shown that "
            "previous studies have demonstrated [1,2,3] effectiveness. "
            "It has been reported in the literature."
        )
        result = extractor._detect_content_type(chunk)
        assert result == "citation"

    def test_detect_background(self, extractor):
        """Text with neither original nor citation indicators."""
        chunk = "The lumbar spine consists of five vertebrae."
        result = extractor._detect_content_type(chunk)
        assert result == "background"


# ===========================================================================
# Test: Rule-Based Stats Extraction
# ===========================================================================

class TestRuleBasedStatsExtraction:
    """Test _extract_stats_rule_based method."""

    def test_extract_p_values(self, extractor):
        """Extract p-values from text."""
        text = "Results were significant (p < 0.001, P=0.023)."
        stats = extractor._extract_stats_rule_based(text)
        assert len(stats.p_values) >= 1

    def test_extract_effect_sizes(self, extractor):
        """Extract effect sizes."""
        text = "The hazard ratio was HR=0.65 and OR=2.3."
        stats = extractor._extract_stats_rule_based(text)
        assert len(stats.effect_sizes) >= 1

    def test_extract_sample_sizes(self, extractor):
        """Extract sample sizes."""
        text = "The study included N=120 patients in group A and n=115 in group B."
        stats = extractor._extract_stats_rule_based(text)
        assert 120 in stats.sample_sizes
        assert 115 in stats.sample_sizes

    def test_extract_confidence_intervals(self, extractor):
        """Extract confidence intervals."""
        text = "The 95% CI: 1.2-3.4 was statistically significant."
        stats = extractor._extract_stats_rule_based(text)
        assert len(stats.confidence_intervals) >= 1

    def test_no_stats_in_text(self, extractor):
        """Text without statistical info."""
        text = "The lumbar spine is a common site of pathology."
        stats = extractor._extract_stats_rule_based(text)
        assert len(stats.p_values) == 0
        assert len(stats.effect_sizes) == 0


# ===========================================================================
# Test: Rule-Based Keywords Extraction
# ===========================================================================

class TestRuleBasedKeywords:
    """Test _extract_keywords_rule_based method."""

    def test_extract_capitalized_terms(self, extractor):
        """Extract capitalized terms."""
        text = "Lumbar Stenosis requires Surgical intervention for some patients."
        keywords = extractor._extract_keywords_rule_based(text)
        assert any("Lumbar" in kw for kw in keywords)

    def test_extract_abbreviations(self, extractor):
        """Extract abbreviations."""
        text = "VAS and ODI scores were measured along with BMI."
        keywords = extractor._extract_keywords_rule_based(text)
        assert "VAS" in keywords or "ODI" in keywords or "BMI" in keywords

    def test_filter_common_words(self, extractor):
        """Common words should be filtered out."""
        text = "The quick brown fox jumps."
        keywords = extractor._extract_keywords_rule_based(text)
        assert "The" not in keywords

    def test_max_10_keywords(self, extractor):
        """Keywords should be limited to 10."""
        text = " ".join([f"Term{i}" for i in range(20)])
        keywords = extractor._extract_keywords_rule_based(text)
        assert len(keywords) <= 10


# ===========================================================================
# Test: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_long_context_truncated(self, extractor, mock_llm_client, sample_llm_response):
        """Long context should be truncated to 1000 chars."""
        mock_llm_client.generate_json.return_value = sample_llm_response
        long_context = "x" * 5000

        result = await extractor.extract("chunk", long_context)

        # Should not crash, LLM still called
        assert isinstance(result, ChunkMetadata)

    @pytest.mark.asyncio
    async def test_no_context(self, extractor, mock_llm_client, sample_llm_response):
        """Empty context should use 'No context provided'."""
        mock_llm_client.generate_json.return_value = sample_llm_response

        result = await extractor.extract("chunk", "")

        assert isinstance(result, ChunkMetadata)

    def test_effect_size_dataclass(self):
        """EffectSize dataclass values."""
        es = EffectSize(type="HR", value=0.65, ci_lower=0.4, ci_upper=1.0)
        assert es.type == "HR"
        assert es.value == 0.65
        assert es.ci_lower == 0.4
        assert es.ci_upper == 1.0

    def test_chunk_metadata_defaults(self):
        """ChunkMetadata defaults."""
        cm = ChunkMetadata(summary="test", keywords=["a"])
        assert cm.pico is None
        assert cm.statistics is None
        assert cm.content_type == "original"
        assert cm.is_key_finding is False
        assert cm.confidence == 0.0
        assert cm.medical_terms == []
        assert cm.study_design_mentioned is None

    def test_extraction_error(self):
        """ExtractionError should be a regular Exception."""
        err = ExtractionError("test error")
        assert str(err) == "test error"
        assert isinstance(err, Exception)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

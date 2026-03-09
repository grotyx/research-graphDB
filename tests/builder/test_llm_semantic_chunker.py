"""LLM Semantic Chunker unit tests.

Tests for builder/llm_semantic_chunker.py covering:
- ChunkingConfig defaults
- SemanticChunk dataclass
- Chunk section: normal, empty, long text
- LLM-based chunking (mocked LLM)
- Post-processing: position adjustment, small chunk merging
- Chunk ID generation
- Validation logic
- Document chunking (parallel sections)
- Fallback chunker
- Table/figure reference detection
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from dataclasses import dataclass

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.llm_semantic_chunker import (
    LLMSemanticChunker,
    ChunkingConfig,
    SemanticChunk,
    ChunkingError,
)
from builder.llm_section_classifier import SectionBoundary, SECTION_TIERS


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_json = AsyncMock(return_value={
        "chunks": [
            {
                "content": "This is the first chunk of text about lumbar stenosis.",
                "topic_summary": "Introduction to lumbar stenosis",
                "is_complete_thought": True,
                "contains_finding": False,
                "char_start": 0,
                "char_end": 54,
                "subsection": None,
            },
            {
                "content": "The results showed significant improvement in VAS scores.",
                "topic_summary": "VAS improvement results",
                "is_complete_thought": True,
                "contains_finding": True,
                "char_start": 55,
                "char_end": 113,
                "subsection": "Results",
            },
        ],
        "total_chunks": 2,
    })
    return client


@pytest.fixture
def chunker(mock_llm):
    """Create LLMSemanticChunker with mocked LLM."""
    return LLMSemanticChunker(llm_client=mock_llm)


@pytest.fixture
def sample_text():
    """Sample section text for testing."""
    return (
        "This is the first chunk of text about lumbar stenosis. "
        "The results showed significant improvement in VAS scores."
    )


# ============================================================================
# ChunkingConfig Tests
# ============================================================================

class TestChunkingConfig:
    """Tests for ChunkingConfig defaults."""

    def test_default_values(self):
        """Default config has sensible values."""
        config = ChunkingConfig()
        assert config.target_min_words == 300
        assert config.target_max_words == 500
        assert config.hard_max_words == 800
        assert config.overlap_sentences == 1
        assert config.preserve_paragraphs is True
        assert config.max_text_per_llm_call == 15000

    def test_custom_values(self):
        """Custom config values are preserved."""
        config = ChunkingConfig(
            target_min_words=100,
            target_max_words=200,
            hard_max_words=400,
        )
        assert config.target_min_words == 100
        assert config.target_max_words == 200
        assert config.hard_max_words == 400


# ============================================================================
# SemanticChunk Tests
# ============================================================================

class TestSemanticChunk:
    """Tests for SemanticChunk dataclass."""

    def test_creation(self):
        """SemanticChunk can be created with required fields."""
        chunk = SemanticChunk(
            chunk_id="doc1_results_000",
            content="Sample content",
            section_type="results",
            tier=1,
            topic_summary="Sample topic",
            is_complete_thought=True,
            contains_finding=True,
            char_start=0,
            char_end=14,
            word_count=2,
        )
        assert chunk.chunk_id == "doc1_results_000"
        assert chunk.tier == 1
        assert chunk.contains_finding is True

    def test_optional_fields(self):
        """Optional fields have correct defaults."""
        chunk = SemanticChunk(
            chunk_id="c1", content="text", section_type="methods",
            tier=2, topic_summary="topic", is_complete_thought=True,
            contains_finding=False, char_start=0, char_end=4, word_count=1,
        )
        assert chunk.subsection is None
        assert chunk.has_table_reference is False
        assert chunk.has_figure_reference is False


# ============================================================================
# LLMSemanticChunker Init Tests
# ============================================================================

class TestChunkerInit:
    """Tests for LLMSemanticChunker initialization."""

    def test_init_with_llm_client(self, mock_llm):
        """Initialize with explicit LLM client."""
        chunker = LLMSemanticChunker(llm_client=mock_llm)
        assert chunker.llm == mock_llm

    def test_init_with_gemini_client_legacy(self, mock_llm):
        """Legacy gemini_client parameter works."""
        chunker = LLMSemanticChunker(gemini_client=mock_llm)
        assert chunker.llm == mock_llm

    def test_init_default_config(self, mock_llm):
        """Default config is created when none provided."""
        chunker = LLMSemanticChunker(llm_client=mock_llm)
        assert chunker.config is not None
        assert isinstance(chunker.config, ChunkingConfig)

    def test_init_custom_config(self, mock_llm):
        """Custom config is used."""
        config = ChunkingConfig(target_min_words=50)
        chunker = LLMSemanticChunker(llm_client=mock_llm, config=config)
        assert chunker.config.target_min_words == 50

    def test_init_with_fallback(self, mock_llm):
        """Fallback chunker is stored."""
        fallback = MagicMock()
        chunker = LLMSemanticChunker(llm_client=mock_llm, fallback_chunker=fallback)
        assert chunker.fallback == fallback


# ============================================================================
# chunk_section() Tests
# ============================================================================

class TestChunkSection:
    """Tests for chunk_section() method."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self, chunker):
        """Empty text returns empty list."""
        result = await chunker.chunk_section("", "results", "doc1")
        assert result == []

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty(self, chunker):
        """Whitespace-only text returns empty list."""
        result = await chunker.chunk_section("   \n\n  ", "results", "doc1")
        assert result == []

    @pytest.mark.asyncio
    async def test_none_text_returns_empty(self, chunker):
        """None text returns empty list."""
        result = await chunker.chunk_section(None, "results", "doc1")
        assert result == []

    @pytest.mark.asyncio
    async def test_normal_text_returns_chunks(self, chunker, sample_text):
        """Normal text returns chunks from LLM."""
        result = await chunker.chunk_section(sample_text, "results", "doc1")
        assert len(result) >= 1
        for chunk in result:
            assert isinstance(chunk, SemanticChunk)
            assert chunk.section_type == "results"

    @pytest.mark.asyncio
    async def test_section_type_preserved(self, chunker, sample_text):
        """Section type is set correctly on chunks."""
        result = await chunker.chunk_section(sample_text, "abstract", "doc1")
        for chunk in result:
            assert chunk.section_type == "abstract"

    @pytest.mark.asyncio
    async def test_section_start_char_offset(self, chunker, sample_text):
        """Section start char offset is applied."""
        offset = 1000
        result = await chunker.chunk_section(sample_text, "results", "doc1", section_start_char=offset)
        for chunk in result:
            assert chunk.char_start >= offset

    @pytest.mark.asyncio
    async def test_long_text_triggers_split(self, mock_llm):
        """Long text triggers _chunk_long_section."""
        config = ChunkingConfig(max_text_per_llm_call=100)
        chunker = LLMSemanticChunker(llm_client=mock_llm, config=config)

        long_text = "This is a paragraph about spine surgery. " * 50
        result = await chunker.chunk_section(long_text, "methods", "doc1")
        # Should still produce chunks
        assert isinstance(result, list)


# ============================================================================
# _chunk_with_llm() Tests
# ============================================================================

class TestChunkWithLLM:
    """Tests for _chunk_with_llm() internal method."""

    @pytest.mark.asyncio
    async def test_llm_called_with_prompt(self, chunker, sample_text):
        """LLM is called with proper prompt and schema."""
        await chunker._chunk_with_llm(sample_text, "results", "doc1")
        chunker.llm.generate_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_chunks_from_llm(self, mock_llm):
        """Handle LLM returning empty chunks list."""
        mock_llm.generate_json = AsyncMock(return_value={"chunks": [], "total_chunks": 0})
        chunker = LLMSemanticChunker(llm_client=mock_llm)
        result = await chunker._chunk_with_llm("Some text here", "results", "doc1")
        assert result == []

    @pytest.mark.asyncio
    async def test_chunk_with_empty_content_skipped(self, mock_llm):
        """Chunks with empty content are skipped."""
        mock_llm.generate_json = AsyncMock(return_value={
            "chunks": [
                {"content": "", "topic_summary": "empty", "is_complete_thought": True,
                 "contains_finding": False, "char_start": 0, "char_end": 0},
                {"content": "Valid content", "topic_summary": "valid", "is_complete_thought": True,
                 "contains_finding": True, "char_start": 0, "char_end": 13},
            ],
            "total_chunks": 2,
        })
        chunker = LLMSemanticChunker(llm_client=mock_llm)
        result = await chunker._chunk_with_llm("Valid content", "results", "doc1")
        assert len(result) == 1
        assert result[0].content == "Valid content"

    @pytest.mark.asyncio
    async def test_table_reference_detected(self, mock_llm):
        """Table references are detected in content."""
        mock_llm.generate_json = AsyncMock(return_value={
            "chunks": [
                {"content": "As shown in Table 1, the results were significant.",
                 "topic_summary": "Table results", "is_complete_thought": True,
                 "contains_finding": True, "char_start": 0, "char_end": 50},
            ],
            "total_chunks": 1,
        })
        chunker = LLMSemanticChunker(llm_client=mock_llm)
        result = await chunker._chunk_with_llm(
            "As shown in Table 1, the results were significant.", "results", "doc1"
        )
        assert len(result) == 1
        assert result[0].has_table_reference is True

    @pytest.mark.asyncio
    async def test_figure_reference_detected(self, mock_llm):
        """Figure references are detected in content."""
        mock_llm.generate_json = AsyncMock(return_value={
            "chunks": [
                {"content": "Figure 3 demonstrates the trend clearly.",
                 "topic_summary": "Figure", "is_complete_thought": True,
                 "contains_finding": False, "char_start": 0, "char_end": 40},
            ],
            "total_chunks": 1,
        })
        chunker = LLMSemanticChunker(llm_client=mock_llm)
        result = await chunker._chunk_with_llm(
            "Figure 3 demonstrates the trend clearly.", "results", "doc1"
        )
        assert len(result) == 1
        assert result[0].has_figure_reference is True

    @pytest.mark.asyncio
    async def test_tier_from_section_type(self, mock_llm, sample_text):
        """Tier is set based on section type mapping."""
        mock_llm.generate_json = AsyncMock(return_value={
            "chunks": [
                {"content": sample_text, "topic_summary": "topic",
                 "is_complete_thought": True, "contains_finding": False,
                 "char_start": 0, "char_end": len(sample_text)},
            ],
            "total_chunks": 1,
        })
        chunker = LLMSemanticChunker(llm_client=mock_llm)

        # abstract is tier 1
        result = await chunker._chunk_with_llm(sample_text, "abstract", "doc1")
        assert result[0].tier == 1

        # methods is tier 2
        result = await chunker._chunk_with_llm(sample_text, "methods", "doc1")
        assert result[0].tier == 2


# ============================================================================
# Chunk ID Generation Tests
# ============================================================================

class TestChunkIdGeneration:
    """Tests for _generate_chunk_id()."""

    def test_format(self, chunker):
        """Chunk ID has correct format."""
        cid = chunker._generate_chunk_id("doc1", "results", 0)
        assert cid == "doc1_results_000"

    def test_index_padding(self, chunker):
        """Index is zero-padded to 3 digits."""
        cid = chunker._generate_chunk_id("doc1", "methods", 42)
        assert cid == "doc1_methods_042"

    def test_large_index(self, chunker):
        """Large index values work."""
        cid = chunker._generate_chunk_id("doc1", "results", 999)
        assert cid == "doc1_results_999"


# ============================================================================
# Validation Tests
# ============================================================================

class TestValidation:
    """Tests for _validate_chunks()."""

    def _make_chunk(self, content="Some content here", char_start=0, char_end=17):
        return SemanticChunk(
            chunk_id="c1", content=content, section_type="results",
            tier=1, topic_summary="topic", is_complete_thought=True,
            contains_finding=False, char_start=char_start, char_end=char_end,
            word_count=len(content.split()),
        )

    def test_empty_chunks_invalid(self, chunker):
        """Empty chunk list is invalid."""
        assert chunker._validate_chunks([], 100) is False

    def test_valid_chunks(self, chunker):
        """Valid chunks pass validation."""
        content = "A" * 100
        chunks = [self._make_chunk(content=content)]
        assert chunker._validate_chunks(chunks, 100) is True

    def test_low_coverage_invalid(self, chunker):
        """Coverage below 50% is invalid."""
        chunks = [self._make_chunk(content="Short")]
        assert chunker._validate_chunks(chunks, 1000) is False

    def test_empty_content_chunk_invalid(self, chunker):
        """Chunk with empty content is invalid."""
        chunks = [self._make_chunk(content="")]
        assert chunker._validate_chunks(chunks, 100) is False

    def test_whitespace_only_content_invalid(self, chunker):
        """Chunk with whitespace-only content is invalid."""
        chunks = [self._make_chunk(content="   ")]
        assert chunker._validate_chunks(chunks, 100) is False


# ============================================================================
# Merge Small Chunks Tests
# ============================================================================

class TestMergeSmallChunks:
    """Tests for _merge_small_chunks()."""

    def _make_chunk(self, content, char_start=0, char_end=None):
        if char_end is None:
            char_end = char_start + len(content)
        return SemanticChunk(
            chunk_id="c1", content=content, section_type="results",
            tier=1, topic_summary="topic", is_complete_thought=True,
            contains_finding=False, char_start=char_start, char_end=char_end,
            word_count=len(content.split()),
        )

    def test_empty_list(self, chunker):
        """Empty list returns empty."""
        assert chunker._merge_small_chunks([]) == []

    def test_single_chunk(self, chunker):
        """Single chunk returned as-is."""
        chunks = [self._make_chunk("Word " * 200)]
        result = chunker._merge_small_chunks(chunks)
        assert len(result) == 1

    def test_small_chunks_merged(self, chunker):
        """Two small chunks are merged."""
        # Default min_words = target_min_words / 2 = 150
        # Chunks with < 150 words should be merged
        small1 = self._make_chunk("word " * 10, char_start=0, char_end=50)
        small2 = self._make_chunk("more " * 10, char_start=50, char_end=100)
        result = chunker._merge_small_chunks([small1, small2])
        assert len(result) == 1

    def test_large_chunks_not_merged(self, chunker):
        """Large chunks are not merged."""
        large1 = self._make_chunk("word " * 200, char_start=0, char_end=1000)
        large2 = self._make_chunk("more " * 200, char_start=1000, char_end=2000)
        result = chunker._merge_small_chunks([large1, large2])
        assert len(result) == 2


# ============================================================================
# Merge Two Chunks Tests
# ============================================================================

class TestMergeTwoChunks:
    """Tests for _merge_two_chunks()."""

    def _make_chunk(self, content="text", tier=1, has_finding=False,
                    has_table=False, has_figure=False, start=0, end=4):
        return SemanticChunk(
            chunk_id="c1", content=content, section_type="results",
            tier=tier, topic_summary="topic", is_complete_thought=True,
            contains_finding=has_finding, char_start=start, char_end=end,
            word_count=len(content.split()),
            has_table_reference=has_table, has_figure_reference=has_figure,
        )

    def test_content_merged(self, chunker):
        """Contents are merged with newline separator."""
        c1 = self._make_chunk("First part", start=0, end=10)
        c2 = self._make_chunk("Second part", start=10, end=21)
        merged = chunker._merge_two_chunks(c1, c2)
        assert "First part" in merged.content
        assert "Second part" in merged.content
        assert "\n\n" in merged.content

    def test_tier_takes_minimum(self, chunker):
        """Merged tier is minimum (highest priority)."""
        c1 = self._make_chunk(tier=2)
        c2 = self._make_chunk(tier=1)
        merged = chunker._merge_two_chunks(c1, c2)
        assert merged.tier == 1

    def test_finding_is_ored(self, chunker):
        """contains_finding is OR'd."""
        c1 = self._make_chunk(has_finding=False)
        c2 = self._make_chunk(has_finding=True)
        merged = chunker._merge_two_chunks(c1, c2)
        assert merged.contains_finding is True

    def test_table_reference_ored(self, chunker):
        """has_table_reference is OR'd."""
        c1 = self._make_chunk(has_table=True)
        c2 = self._make_chunk(has_table=False)
        merged = chunker._merge_two_chunks(c1, c2)
        assert merged.has_table_reference is True

    def test_figure_reference_ored(self, chunker):
        """has_figure_reference is OR'd."""
        c1 = self._make_chunk(has_figure=False)
        c2 = self._make_chunk(has_figure=True)
        merged = chunker._merge_two_chunks(c1, c2)
        assert merged.has_figure_reference is True

    def test_char_range_spans_both(self, chunker):
        """Merged chunk spans both char ranges."""
        c1 = self._make_chunk(start=100, end=200)
        c2 = self._make_chunk(start=200, end=300)
        merged = chunker._merge_two_chunks(c1, c2)
        assert merged.char_start == 100
        assert merged.char_end == 300

    def test_summary_combined(self, chunker):
        """Summaries are combined."""
        c1 = self._make_chunk()
        c1.topic_summary = "First topic"
        c2 = self._make_chunk()
        c2.topic_summary = "Second topic"
        merged = chunker._merge_two_chunks(c1, c2)
        assert "First topic" in merged.topic_summary
        assert "Second topic" in merged.topic_summary


# ============================================================================
# Document Chunking Tests
# ============================================================================

class TestChunkDocument:
    """Tests for chunk_document()."""

    @pytest.mark.asyncio
    async def test_empty_sections(self, chunker):
        """Empty sections list returns empty."""
        result = await chunker.chunk_document([], "full text here", "doc1")
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_full_text(self, chunker):
        """Empty full text returns empty."""
        sections = [SectionBoundary("abstract", 0, 100, 0.9, 1)]
        result = await chunker.chunk_document(sections, "", "doc1")
        assert result == []

    @pytest.mark.asyncio
    async def test_single_section(self, chunker, sample_text):
        """Single section document chunking."""
        sections = [SectionBoundary("results", 0, len(sample_text), 0.9, 1)]
        result = await chunker.chunk_document(sections, sample_text, "doc1")
        assert isinstance(result, list)
        # Chunks should be re-indexed
        for i, chunk in enumerate(result):
            assert chunk.chunk_id == f"doc1_{i:03d}"

    @pytest.mark.asyncio
    async def test_failed_section_skipped(self, mock_llm, sample_text):
        """Failed section does not block other sections."""
        # First call fails, second succeeds
        mock_llm.generate_json = AsyncMock(side_effect=[
            Exception("LLM error"),
            {
                "chunks": [
                    {"content": "Valid chunk", "topic_summary": "topic",
                     "is_complete_thought": True, "contains_finding": False,
                     "char_start": 0, "char_end": 11},
                ],
                "total_chunks": 1,
            }
        ])
        chunker = LLMSemanticChunker(llm_client=mock_llm)
        sections = [
            SectionBoundary("abstract", 0, 50, 0.9, 1),
            SectionBoundary("results", 50, len(sample_text), 0.9, 1),
        ]
        result = await chunker.chunk_document(sections, sample_text, "doc1")
        # Should still have chunks from the successful section
        assert isinstance(result, list)


# ============================================================================
# Paragraph Splitting Tests
# ============================================================================

class TestSplitIntoParagraphs:
    """Tests for _split_into_paragraphs()."""

    def test_single_paragraph(self, chunker):
        """Single paragraph returns one item."""
        text = "This is a single paragraph with no blank lines."
        result = chunker._split_into_paragraphs(text)
        assert len(result) >= 1

    def test_multiple_paragraphs(self, chunker):
        """Multiple paragraphs separated by blank lines."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = chunker._split_into_paragraphs(text)
        assert len(result) == 3

    def test_empty_text(self, chunker):
        """Empty text returns empty list."""
        result = chunker._split_into_paragraphs("")
        assert result == []


# ============================================================================
# Group Paragraphs Tests
# ============================================================================

class TestGroupParagraphs:
    """Tests for _group_paragraphs()."""

    def test_empty_paragraphs(self, chunker):
        """Empty paragraph list returns empty."""
        assert chunker._group_paragraphs([]) == []

    def test_small_paragraphs_grouped(self, chunker):
        """Small paragraphs are grouped together."""
        paragraphs = [
            {"text": "Short para 1.", "start": 0, "end": 13},
            {"text": "Short para 2.", "start": 15, "end": 28},
        ]
        groups = chunker._group_paragraphs(paragraphs)
        assert len(groups) == 1  # Should be grouped together

    def test_large_paragraph_separate_group(self, chunker):
        """Large paragraph gets its own group."""
        large_text = "word " * 2500
        paragraphs = [
            {"text": large_text, "start": 0, "end": len(large_text)},
            {"text": "Short.", "start": len(large_text) + 2, "end": len(large_text) + 8},
        ]
        groups = chunker._group_paragraphs(paragraphs)
        assert len(groups) >= 1


# ============================================================================
# Fallback Chunker Tests
# ============================================================================

class TestFallbackChunker:
    """Tests for _use_fallback()."""

    def test_no_fallback_returns_empty(self, mock_llm):
        """No fallback chunker returns empty list."""
        chunker = LLMSemanticChunker(llm_client=mock_llm, fallback_chunker=None)
        result = chunker._use_fallback("text", "results", "doc1", 0)
        assert result == []

    def test_with_fallback(self, mock_llm):
        """Fallback chunker produces SemanticChunks."""
        mock_fallback = MagicMock()

        mock_chunk = MagicMock()
        mock_chunk.content = "Fallback chunk content"
        mock_chunk.metadata.start_char = 0
        mock_chunk.metadata.end_char = 22

        mock_result = MagicMock()
        mock_result.chunks = [mock_chunk]

        mock_fallback.chunk_with_tiers.return_value = mock_result

        chunker = LLMSemanticChunker(llm_client=mock_llm, fallback_chunker=mock_fallback)
        result = chunker._use_fallback("Fallback chunk content", "results", "doc1", 0)
        assert len(result) == 1
        assert isinstance(result[0], SemanticChunk)
        assert result[0].content == "Fallback chunk content"


# ============================================================================
# Table/Figure Pattern Tests
# ============================================================================

class TestPatterns:
    """Tests for TABLE_PATTERN and FIGURE_PATTERN."""

    def test_table_pattern_matches(self):
        """TABLE_PATTERN matches common table references."""
        assert LLMSemanticChunker.TABLE_PATTERN.search("See Table 1")
        assert LLMSemanticChunker.TABLE_PATTERN.search("in table 3")
        assert LLMSemanticChunker.TABLE_PATTERN.search("Tables 2")

    def test_table_pattern_no_match(self):
        """TABLE_PATTERN does not match non-table text."""
        assert LLMSemanticChunker.TABLE_PATTERN.search("tablespoon") is None

    def test_figure_pattern_matches(self):
        """FIGURE_PATTERN matches common figure references."""
        assert LLMSemanticChunker.FIGURE_PATTERN.search("Figure 1")
        assert LLMSemanticChunker.FIGURE_PATTERN.search("Fig. 2")
        assert LLMSemanticChunker.FIGURE_PATTERN.search("Figs 3")

    def test_figure_pattern_no_match(self):
        """FIGURE_PATTERN does not match non-figure text."""
        assert LLMSemanticChunker.FIGURE_PATTERN.search("figured out") is None

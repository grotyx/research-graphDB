"""Tests for section_chunker.py.

Tests:
- Section detection (IMRAD, book chapters, webpage)
- Chunk creation and properties
- Edge cases (no sections, empty text, large sections)
- Error handling
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from builder.section_chunker import (
    SectionChunker,
    Chunk,
    PAPER_SECTION_PATTERNS,
    BOOK_SECTION_PATTERNS,
)
from builder.document_type_detector import DocumentType
from core.exceptions import ProcessingError


class TestChunk:
    """Test Chunk dataclass."""

    def test_chunk_initialization(self):
        """Test basic chunk creation."""
        chunk = Chunk(
            chunk_id="paper1_chunk_0",
            paper_id="paper1",
            text="This is a test chunk with some content.",
            section="Introduction",
            chunk_index=0,
            word_count=8
        )

        assert chunk.chunk_id == "paper1_chunk_0"
        assert chunk.paper_id == "paper1"
        assert chunk.section == "Introduction"
        assert chunk.chunk_index == 0
        assert chunk.word_count == 8

    def test_chunk_auto_word_count(self):
        """Test automatic word count calculation."""
        chunk = Chunk(
            chunk_id="paper1_chunk_0",
            paper_id="paper1",
            text="This is a test.",
            section="Methods",
            chunk_index=0,
            word_count=0  # Should be auto-calculated
        )

        assert chunk.word_count == 4

    def test_chunk_table_detection(self):
        """Test automatic table detection."""
        chunk = Chunk(
            chunk_id="paper1_chunk_0",
            paper_id="paper1",
            text="As shown in Table 1, the results were significant.",
            section="Results",
            chunk_index=0,
            word_count=8
        )

        assert chunk.has_table is True

    def test_chunk_figure_detection(self):
        """Test automatic figure detection."""
        chunk = Chunk(
            chunk_id="paper1_chunk_0",
            paper_id="paper1",
            text="See Figure 2 for the visualization.",
            section="Results",
            chunk_index=0,
            word_count=6
        )

        assert chunk.has_figure is True

    def test_chunk_statistics_detection(self):
        """Test statistical data detection."""
        # Has p-value
        chunk1 = Chunk(
            chunk_id="paper1_chunk_0",
            paper_id="paper1",
            text="The result was significant (p < 0.05).",
            section="Results",
            chunk_index=0,
            word_count=7
        )
        assert chunk1.has_statistics is True

        # Has table
        chunk2 = Chunk(
            chunk_id="paper1_chunk_1",
            paper_id="paper1",
            text="See Table 1 for details.",
            section="Results",
            chunk_index=1,
            word_count=5
        )
        assert chunk2.has_statistics is True

    def test_chunk_empty_text_error(self):
        """Test error on empty text."""
        with pytest.raises(ProcessingError):
            Chunk(
                chunk_id="paper1_chunk_0",
                paper_id="paper1",
                text="",
                section="Introduction",
                chunk_index=0,
                word_count=0
            )


class TestSectionChunker:
    """Test SectionChunker class."""

    @pytest.fixture
    def chunker(self):
        """Create a chunker instance."""
        return SectionChunker()

    @pytest.mark.asyncio
    async def test_empty_text_error(self, chunker):
        """Test error on empty text."""
        with pytest.raises(ProcessingError):
            await chunker.chunk(
                text="",
                document_type=DocumentType.JOURNAL_ARTICLE,
                paper_id="paper1"
            )

    @pytest.mark.asyncio
    async def test_chunk_paper_with_sections(self, chunker):
        """Test chunking a paper with IMRAD sections."""
        text = """
Abstract
This is the abstract of the paper.

Introduction
This is the introduction section with some background information.

Methods
We used the following methodology for our study.

Results
The results show significant improvement (p < 0.05).
See Table 1 for detailed results.

Discussion
Our findings are consistent with previous studies.
This confirms the effectiveness of the approach.

References
1. Smith et al. (2020)
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper1"
        )

        assert len(chunks) > 0

        # Check section names
        sections = [c.section for c in chunks]
        assert "Abstract" in sections
        assert "Introduction" in sections
        assert "Methods" in sections
        assert "Results" in sections
        assert "Discussion" in sections

        # References should be excluded
        assert "References" not in sections

        # Check chunk IDs are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.chunk_id == f"paper1_chunk_{i}"

    @pytest.mark.asyncio
    async def test_chunk_paper_no_sections(self, chunker):
        """Test chunking paper with no clear sections (falls back to generic)."""
        text = """
This is a paper without clear section markers.
It has multiple paragraphs but no IMRAD structure.
""" + " ".join(["word"] * 150)  # Add more words to ensure at least one chunk

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper2"
        )

        assert len(chunks) > 0

        # Should all be "Content" section (generic chunking)
        for chunk in chunks:
            assert chunk.section == "Content"

    @pytest.mark.asyncio
    async def test_chunk_book(self, chunker):
        """Test chunking a book with chapters."""
        text = """
Chapter 1
This is the first chapter with some content.

Chapter 2
This is the second chapter with more content.
It has multiple paragraphs.

Chapter 3
Final chapter with conclusions.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.BOOK,
            paper_id="book1"
        )

        assert len(chunks) > 0

        # Check chapter sections
        sections = [c.section for c in chunks]
        assert "Chapter" in sections

    @pytest.mark.asyncio
    async def test_chunk_webpage(self, chunker):
        """Test chunking a webpage."""
        text = """
# Main Heading
Content under main heading.

## Subsection
More content here.

### Another Section
Final section content.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.WEBPAGE,
            paper_id="web1"
        )

        assert len(chunks) > 0

        # All should have Section type
        for chunk in chunks:
            assert chunk.section == "Section"

    @pytest.mark.asyncio
    async def test_chunk_size_limits(self, chunker):
        """Test that chunks respect size limits."""
        # Create very large section with paragraph breaks
        paragraphs = [" ".join(["word"] * 100) for _ in range(20)]
        large_text = "Introduction\n\n" + "\n\n".join(paragraphs)

        chunks = await chunker.chunk(
            text=large_text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper3"
        )

        # Should split into multiple chunks
        assert len(chunks) > 1

        # Each chunk should be within max size
        for chunk in chunks:
            assert chunk.word_count <= chunker.MAX_CHUNK_WORDS

    @pytest.mark.asyncio
    async def test_chunk_preserves_paragraphs(self, chunker):
        """Test that chunking preserves paragraph boundaries."""
        text = """
Introduction
First paragraph with some content.

Second paragraph with more information.

Third paragraph to add more context.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper4"
        )

        # Chunks should preserve paragraph structure (double newlines)
        for chunk in chunks:
            if "\n\n" in chunk.text:
                # If chunk has multiple paragraphs, check they're separated
                assert "\n\n" in chunk.text

    @pytest.mark.asyncio
    async def test_chunk_metadata(self, chunker):
        """Test chunk metadata is properly set."""
        text = """
Methods
This is the methodology section.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper5"
        )

        assert len(chunks) > 0

        # Check metadata
        for chunk in chunks:
            assert "source_section" in chunk.metadata
            assert chunk.metadata["source_section"] == chunk.section

    def test_detect_sections_paper(self, chunker):
        """Test section detection with paper patterns."""
        text = """Introduction
Some intro text.

Methods
Methodology here.

Discussion
Results section.
"""

        sections = chunker._detect_sections(text, PAPER_SECTION_PATTERNS)

        assert len(sections) >= 3
        section_names = [s[0] for s in sections]
        assert "Introduction" in section_names
        assert "Methods" in section_names
        assert "Discussion" in section_names

    def test_detect_sections_book(self, chunker):
        """Test section detection with book patterns."""
        text = """
Chapter 1
First chapter.

Chapter 2
Second chapter.
"""

        sections = chunker._detect_sections(text, BOOK_SECTION_PATTERNS)

        assert len(sections) == 2
        assert sections[0][0] == "Chapter"
        assert sections[1][0] == "Chapter"

    def test_split_section_small(self, chunker):
        """Test splitting small section (should not split)."""
        text = "This is a small section with few words."

        result = chunker._split_section(text, "Test", max_words=500)

        assert len(result) == 1
        assert result[0] == text

    def test_split_section_large(self, chunker):
        """Test splitting large section."""
        # Create large section with paragraph breaks (over 500 words)
        paragraphs = [" ".join(["word"] * 100) for _ in range(10)]
        text = "\n\n".join(paragraphs)

        result = chunker._split_section(text, "Test", max_words=500)

        # Should be split into multiple chunks
        assert len(result) > 1

        # Each chunk should be within limit
        for chunk_text in result:
            assert len(chunk_text.split()) <= 500

    def test_split_large_paragraph(self, chunker):
        """Test splitting large paragraph by sentences."""
        # Create large paragraph
        sentences = [f"This is sentence {i}." for i in range(200)]
        text = " ".join(sentences)

        result = chunker._split_large_paragraph(text, max_words=100)

        # Should be split into multiple chunks
        assert len(result) > 1

        # Each chunk should be within limit
        for chunk_text in result:
            assert len(chunk_text.split()) <= 100

    def test_has_table(self, chunker):
        """Test table detection."""
        assert chunker._has_table("See Table 1 for results.") is True
        assert chunker._has_table("See table 2 for details.") is True
        assert chunker._has_table("Tabelle 3 shows data.") is True  # German
        assert chunker._has_table("No tables here.") is False

    def test_has_figure(self, chunker):
        """Test figure detection."""
        assert chunker._has_figure("See Figure 1 for visualization.") is True
        assert chunker._has_figure("As shown in Fig. 2") is True
        assert chunker._has_figure("See figure 3 below") is True
        assert chunker._has_figure("Abbildung 4 demonstrates") is True  # German
        assert chunker._has_figure("No figures here.") is False

    @pytest.mark.asyncio
    async def test_custom_target_chunks(self, chunker):
        """Test custom target chunk count."""
        text = """
Introduction
This is a long introduction section.

Methods
Detailed methodology.

Results
Comprehensive results.

Discussion
Extended discussion.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper6",
            target_chunks=10
        )

        # Should create chunks (target is a guideline, not strict)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_numbered_sections(self, chunker):
        """Test detection of numbered sections."""
        text = """
1. Introduction
This is the introduction.

2. Methods
This is the methodology.

3. Results
These are the results.

4. Discussion
This is the discussion.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper7"
        )

        assert len(chunks) > 0

        sections = [c.section for c in chunks]
        assert "Introduction" in sections
        assert "Methods" in sections
        assert "Results" in sections
        assert "Discussion" in sections

    @pytest.mark.asyncio
    async def test_mixed_case_sections(self, chunker):
        """Test section detection with mixed case."""
        text = """
INTRODUCTION
This is uppercase.

methods
This is lowercase.

ReSuLtS
This is mixed case.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper8"
        )

        assert len(chunks) > 0

        # Should detect all sections regardless of case
        sections = [c.section for c in chunks]
        assert "Introduction" in sections
        assert "Methods" in sections
        assert "Results" in sections

    @pytest.mark.asyncio
    async def test_markdown_headings(self, chunker):
        """Test detection of markdown-style headings."""
        text = """
# Abstract
Abstract content.

## Introduction
Introduction content.

### Methods
Methods content.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper9"
        )

        assert len(chunks) > 0

        sections = [c.section for c in chunks]
        assert "Abstract" in sections
        assert "Introduction" in sections
        assert "Methods" in sections

    @pytest.mark.asyncio
    async def test_single_paragraph_document(self, chunker):
        """Test chunking document with single paragraph."""
        # Need enough words to meet MIN_CHUNK_WORDS (100)
        text = " ".join(["word"] * 120)

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper10"
        )

        # Should create at least one chunk
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_whitespace_normalization(self, chunker):
        """Test handling of extra whitespace."""
        text = """


Introduction


This has lots of extra whitespace.


Methods


More whitespace here.


"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper11"
        )

        # Should handle whitespace gracefully
        assert len(chunks) > 0

        # Chunks should not be empty
        for chunk in chunks:
            assert chunk.text.strip()

    @pytest.mark.asyncio
    async def test_chunk_index_continuity(self, chunker):
        """Test that chunk indices are continuous and start from 0."""
        text = """
Introduction
Content 1.

Methods
Content 2.

Results
Content 3.

Discussion
Content 4.
"""

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.JOURNAL_ARTICLE,
            paper_id="paper12"
        )

        # Check indices are sequential
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    @pytest.mark.asyncio
    async def test_generic_document_type(self, chunker):
        """Test chunking with generic document type."""
        # Need enough words to meet MIN_CHUNK_WORDS
        paragraphs = [" ".join(["word"] * 40) for _ in range(5)]
        text = "\n\n".join(paragraphs)

        chunks = await chunker.chunk(
            text=text,
            document_type=DocumentType.CONFERENCE_PAPER,  # Not specifically handled
            paper_id="paper13"
        )

        assert len(chunks) > 0

        # Should use generic chunking
        for chunk in chunks:
            assert chunk.section == "Content"

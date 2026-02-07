"""Section-based Semantic Chunker (v7.0).

Smart document chunking based on document structure:
- Papers: IMRAD sections (Introduction, Methods, Results, Discussion)
- Books: Chapters and subsections
- Webpages: Main content sections
- Preserves tables, figures, and contextual boundaries

Usage:
    chunker = SectionChunker()

    # Chunk with document type
    chunks = await chunker.chunk(
        text=document_text,
        document_type=DocumentType.JOURNAL_ARTICLE,
        paper_id="paper123",
        target_chunks=20
    )

    # Access chunk properties
    for chunk in chunks:
        print(f"Section: {chunk.section}")
        print(f"Words: {chunk.word_count}")
        print(f"Has table: {chunk.has_table}")
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from llm import LLMClient
from builder.document_type_detector import DocumentType

logger = logging.getLogger(__name__)


# =============================================================================
# Chunk Data Structure
# =============================================================================

@dataclass
class Chunk:
    """Semantic chunk with section context."""

    chunk_id: str           # Unique ID (paper_id + chunk_index)
    paper_id: str           # Parent document ID
    text: str               # Chunk content
    section: str            # Section name (Introduction, Methods, etc.)
    chunk_index: int        # Order within document (0-based)
    word_count: int         # Number of words
    has_table: bool = False
    has_figure: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def has_statistics(self) -> bool:
        """Check if chunk contains statistical data."""
        return self.has_table or bool(
            re.search(r'\bp\s*[<>=]\s*0\.\d+', self.text, re.I)
        )

    def __post_init__(self):
        """Validate and compute derived properties."""
        if not self.text:
            raise ValueError("Chunk text cannot be empty")

        # Ensure word count is accurate
        if self.word_count == 0:
            self.word_count = len(self.text.split())

        # Auto-detect tables/figures if not set
        if not self.has_table:
            self.has_table = bool(re.search(
                r'\b(table|tabelle)\s+\d+',
                self.text,
                re.I
            ))

        if not self.has_figure:
            self.has_figure = bool(re.search(
                r'\b(figure|fig\.?|abbildung)\s+\d+',
                self.text,
                re.I
            ))


# =============================================================================
# Section Patterns
# =============================================================================

# IMRAD section patterns (journal articles)
PAPER_SECTION_PATTERNS = [
    # Abstract
    (r'^#{1,3}\s*abstract\b', 'Abstract'),
    (r'^abstract\b', 'Abstract'),

    # Introduction / Background
    (r'^#{1,3}\s*introduction\b', 'Introduction'),
    (r'^#{1,3}\s*background\b', 'Background'),
    (r'^introduction\b', 'Introduction'),
    (r'^background\b', 'Background'),
    (r'^1\.\s*introduction', 'Introduction'),

    # Methods
    (r'^#{1,3}\s*(methods?|materials?\s+and\s+methods?)\b', 'Methods'),
    (r'^(methods?|materials?\s+and\s+methods?)\b', 'Methods'),
    (r'^2\.\s*methods?', 'Methods'),

    # Results
    (r'^#{1,3}\s*results?\b', 'Results'),
    (r'^results?\b', 'Results'),
    (r'^3\.\s*results?', 'Results'),

    # Discussion
    (r'^#{1,3}\s*discussion\b', 'Discussion'),
    (r'^discussion\b', 'Discussion'),
    (r'^4\.\s*discussion', 'Discussion'),

    # Conclusion
    (r'^#{1,3}\s*conclusions?\b', 'Conclusions'),
    (r'^conclusions?\b', 'Conclusions'),
    (r'^5\.\s*conclusions?', 'Conclusions'),

    # References (exclude from chunks)
    (r'^#{1,3}\s*(references?|bibliography)\b', 'References'),
    (r'^(references?|bibliography)\b', 'References'),
]

# Book section patterns
BOOK_SECTION_PATTERNS = [
    # Chapter markers
    (r'^chapter\s+\d+', 'Chapter'),
    (r'^part\s+(one|two|three|four|five|i|ii|iii|iv|v|\d+)', 'Part'),
    (r'^\d+\.\s+[A-Z][a-z]+', 'Section'),  # "1. Introduction"

    # Subsections
    (r'^#{1,3}\s*\d+\.\d+\s+', 'Subsection'),
]

# Webpage section patterns
WEBPAGE_SECTION_PATTERNS = [
    # HTML heading markers
    (r'^#{1,3}\s+', 'Section'),
    (r'^<h[1-3]>', 'Section'),

    # Common section titles
    (r'^overview\b', 'Overview'),
    (r'^summary\b', 'Summary'),
    (r'^key\s+points?\b', 'Key Points'),
]

# Table/Figure markers
TABLE_PATTERNS = [
    r'\btable\s+\d+',
    r'\btabelle\s+\d+',  # German
    r'\b표\s+\d+',       # Korean
]

FIGURE_PATTERNS = [
    r'\bfigure\s+\d+',
    r'\bfig\.?\s+\d+',
    r'\babbildung\s+\d+',  # German
    r'\b그림\s+\d+',       # Korean
]


# =============================================================================
# SectionChunker Class
# =============================================================================

class SectionChunker:
    """Section-based semantic chunking for all document types.

    Creates 15-25 chunks per document by:
    - Detecting section boundaries
    - Preserving semantic units (paragraphs, tables, figures)
    - Maintaining context around data
    - Splitting large sections intelligently
    """

    # Target configuration
    TARGET_CHUNKS = 20
    MIN_CHUNK_WORDS = 100
    MAX_CHUNK_WORDS = 500

    # Section-specific targets (for papers)
    SECTION_TARGETS = {
        'Abstract': 1,
        'Introduction': 2,
        'Background': 2,
        'Methods': 3,
        'Results': 5,
        'Discussion': 6,
        'Conclusions': 1,
    }

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """Initialize chunker.

        Args:
            llm_client: Optional LLM client for advanced section detection
        """
        self.llm_client = llm_client

    async def chunk(
        self,
        text: str,
        document_type: DocumentType,
        paper_id: str,
        target_chunks: int = 20
    ) -> list[Chunk]:
        """Create semantic chunks based on document structure.

        Args:
            text: Full document text
            document_type: Type of document
            paper_id: Unique document identifier
            target_chunks: Target number of chunks (default: 20)

        Returns:
            List of Chunk objects

        Raises:
            ValueError: If text is empty or invalid
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        logger.info(f"Chunking {document_type.value} document: {paper_id} (target: {target_chunks} chunks)")

        # Route to type-specific chunking
        if document_type == DocumentType.JOURNAL_ARTICLE:
            chunks = await self._chunk_paper(text, paper_id, target_chunks)
        elif document_type in (DocumentType.BOOK, DocumentType.BOOK_SECTION):
            chunks = await self._chunk_book(text, paper_id, target_chunks)
        elif document_type in (DocumentType.WEBPAGE, DocumentType.BLOG_POST):
            chunks = await self._chunk_webpage(text, paper_id, target_chunks)
        else:
            # Generic chunking for other types
            chunks = await self._chunk_generic(text, paper_id, target_chunks)

        logger.info(f"Created {len(chunks)} chunks (avg: {sum(c.word_count for c in chunks) / len(chunks):.0f} words)")

        return chunks

    async def _chunk_paper(
        self,
        text: str,
        paper_id: str,
        target: int
    ) -> list[Chunk]:
        """Chunk research paper by IMRAD sections.

        Strategy:
        - Detect major sections (Abstract, Introduction, Methods, Results, Discussion)
        - Split each section based on target distribution
        - Preserve paragraph boundaries
        - Keep tables/figures as separate chunks
        """
        # Detect section boundaries
        sections = self._detect_sections(text, PAPER_SECTION_PATTERNS)

        if not sections:
            # No sections detected, treat as generic
            logger.warning("No paper sections detected, using generic chunking")
            return await self._chunk_generic(text, paper_id, target)

        # Exclude References section
        sections = [(name, content) for name, content in sections if name != 'References']

        logger.debug(f"Detected {len(sections)} paper sections: {[s[0] for s in sections]}")

        # Create chunks from sections
        chunks = []
        chunk_index = 0

        for section_name, section_text in sections:
            if not section_text.strip():
                continue

            # Get target chunks for this section
            section_target = self.SECTION_TARGETS.get(section_name, 3)

            # Split section if too large
            section_chunks = self._split_section(
                section_text,
                section_name,
                max_words=self.MAX_CHUNK_WORDS
            )

            # Create Chunk objects
            for chunk_text in section_chunks:
                chunk = Chunk(
                    chunk_id=f"{paper_id}_chunk_{chunk_index}",
                    paper_id=paper_id,
                    text=chunk_text,
                    section=section_name,
                    chunk_index=chunk_index,
                    word_count=len(chunk_text.split()),
                    has_table=self._has_table(chunk_text),
                    has_figure=self._has_figure(chunk_text),
                    metadata={'source_section': section_name}
                )
                chunks.append(chunk)
                chunk_index += 1

        return chunks

    async def _chunk_book(
        self,
        text: str,
        paper_id: str,
        target: int
    ) -> list[Chunk]:
        """Chunk book by chapters/sections.

        Strategy:
        - Detect chapter boundaries
        - Split chapters by subsections
        - Preserve paragraph structure
        """
        sections = self._detect_sections(text, BOOK_SECTION_PATTERNS)

        if not sections:
            logger.warning("No book sections detected, using generic chunking")
            return await self._chunk_generic(text, paper_id, target)

        logger.debug(f"Detected {len(sections)} book sections")

        chunks = []
        chunk_index = 0

        for section_name, section_text in sections:
            if not section_text.strip():
                continue

            # Split large sections
            section_chunks = self._split_section(
                section_text,
                section_name,
                max_words=self.MAX_CHUNK_WORDS
            )

            for chunk_text in section_chunks:
                chunk = Chunk(
                    chunk_id=f"{paper_id}_chunk_{chunk_index}",
                    paper_id=paper_id,
                    text=chunk_text,
                    section=section_name,
                    chunk_index=chunk_index,
                    word_count=len(chunk_text.split()),
                    has_table=self._has_table(chunk_text),
                    has_figure=self._has_figure(chunk_text),
                    metadata={'source_section': section_name}
                )
                chunks.append(chunk)
                chunk_index += 1

        return chunks

    async def _chunk_webpage(
        self,
        text: str,
        paper_id: str,
        target: int
    ) -> list[Chunk]:
        """Chunk webpage by main sections.

        Strategy:
        - Detect heading markers
        - Split by logical content blocks
        - Preserve paragraph boundaries
        """
        sections = self._detect_sections(text, WEBPAGE_SECTION_PATTERNS)

        if not sections:
            logger.warning("No webpage sections detected, using generic chunking")
            return await self._chunk_generic(text, paper_id, target)

        logger.debug(f"Detected {len(sections)} webpage sections")

        chunks = []
        chunk_index = 0

        for section_name, section_text in sections:
            if not section_text.strip():
                continue

            # Split large sections
            section_chunks = self._split_section(
                section_text,
                section_name,
                max_words=self.MAX_CHUNK_WORDS
            )

            for chunk_text in section_chunks:
                chunk = Chunk(
                    chunk_id=f"{paper_id}_chunk_{chunk_index}",
                    paper_id=paper_id,
                    text=chunk_text,
                    section=section_name,
                    chunk_index=chunk_index,
                    word_count=len(chunk_text.split()),
                    has_table=self._has_table(chunk_text),
                    has_figure=self._has_figure(chunk_text),
                    metadata={'source_section': section_name}
                )
                chunks.append(chunk)
                chunk_index += 1

        return chunks

    async def _chunk_generic(
        self,
        text: str,
        paper_id: str,
        target: int
    ) -> list[Chunk]:
        """Generic chunking for documents without clear structure.

        Strategy:
        - Split by paragraph boundaries
        - Maintain target chunk size
        - Preserve semantic units
        """
        # Split by double newlines (paragraphs)
        paragraphs = re.split(r'\n\n+', text)

        chunks = []
        chunk_index = 0
        current_text = ""
        current_words = 0

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            para_words = len(paragraph.split())

            # If paragraph alone is too large, split it
            if para_words > self.MAX_CHUNK_WORDS:
                # Save current chunk if exists
                if current_text:
                    chunk = Chunk(
                        chunk_id=f"{paper_id}_chunk_{chunk_index}",
                        paper_id=paper_id,
                        text=current_text,
                        section="Content",
                        chunk_index=chunk_index,
                        word_count=current_words,
                        has_table=self._has_table(current_text),
                        has_figure=self._has_figure(current_text)
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    current_text = ""
                    current_words = 0

                # Split large paragraph
                sub_chunks = self._split_large_paragraph(paragraph, self.MAX_CHUNK_WORDS)
                for sub_text in sub_chunks:
                    chunk = Chunk(
                        chunk_id=f"{paper_id}_chunk_{chunk_index}",
                        paper_id=paper_id,
                        text=sub_text,
                        section="Content",
                        chunk_index=chunk_index,
                        word_count=len(sub_text.split()),
                        has_table=self._has_table(sub_text),
                        has_figure=self._has_figure(sub_text)
                    )
                    chunks.append(chunk)
                    chunk_index += 1

            # Add to current chunk
            elif current_words + para_words > self.MAX_CHUNK_WORDS:
                # Save current chunk
                if current_text:
                    chunk = Chunk(
                        chunk_id=f"{paper_id}_chunk_{chunk_index}",
                        paper_id=paper_id,
                        text=current_text,
                        section="Content",
                        chunk_index=chunk_index,
                        word_count=current_words,
                        has_table=self._has_table(current_text),
                        has_figure=self._has_figure(current_text)
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                # Start new chunk with current paragraph
                current_text = paragraph
                current_words = para_words

            else:
                # Add to current chunk
                if current_text:
                    current_text += "\n\n" + paragraph
                else:
                    current_text = paragraph
                current_words += para_words

        # Save final chunk
        if current_text and current_words >= self.MIN_CHUNK_WORDS:
            chunk = Chunk(
                chunk_id=f"{paper_id}_chunk_{chunk_index}",
                paper_id=paper_id,
                text=current_text,
                section="Content",
                chunk_index=chunk_index,
                word_count=current_words,
                has_table=self._has_table(current_text),
                has_figure=self._has_figure(current_text)
            )
            chunks.append(chunk)

        return chunks

    def _detect_sections(
        self,
        text: str,
        patterns: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """Detect section boundaries in text.

        Args:
            text: Full document text
            patterns: List of (regex, section_name) tuples

        Returns:
            List of (section_name, section_text) tuples
        """
        sections = []
        lines = text.split('\n')

        current_section = None
        current_text = []

        for line in lines:
            # Check if line matches any section pattern
            matched = False
            for pattern, section_name in patterns:
                if re.match(pattern, line.strip(), re.IGNORECASE):
                    # Save previous section
                    if current_section:
                        sections.append((current_section, '\n'.join(current_text)))

                    # Start new section
                    current_section = section_name
                    current_text = [line]
                    matched = True
                    break

            if not matched and current_section:
                current_text.append(line)

        # Save final section
        if current_section:
            sections.append((current_section, '\n'.join(current_text)))

        return sections

    def _split_section(
        self,
        section_text: str,
        section_name: str,
        max_words: int
    ) -> list[str]:
        """Split large section into smaller chunks.

        Args:
            section_text: Section content
            section_name: Section identifier
            max_words: Maximum words per chunk

        Returns:
            List of chunk texts
        """
        words = len(section_text.split())

        # If section is small enough, return as-is
        if words <= max_words:
            return [section_text]

        # Split by paragraphs
        paragraphs = re.split(r'\n\n+', section_text)

        chunks = []
        current_chunk = []
        current_words = 0

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            para_words = len(paragraph.split())

            # If single paragraph is too large, split it
            if para_words > max_words:
                # Save current chunk
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_words = 0

                # Split large paragraph
                sub_chunks = self._split_large_paragraph(paragraph, max_words)
                chunks.extend(sub_chunks)

            # Add to current chunk
            elif current_words + para_words > max_words:
                # Save current chunk
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))

                # Start new chunk
                current_chunk = [paragraph]
                current_words = para_words

            else:
                current_chunk.append(paragraph)
                current_words += para_words

        # Save final chunk
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        return chunks

    def _split_large_paragraph(
        self,
        paragraph: str,
        max_words: int
    ) -> list[str]:
        """Split a large paragraph by sentence boundaries.

        Args:
            paragraph: Large paragraph text
            max_words: Maximum words per chunk

        Returns:
            List of sub-chunks
        """
        # Split by sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', paragraph)

        chunks = []
        current_chunk = []
        current_words = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sent_words = len(sentence.split())

            if current_words + sent_words > max_words:
                # Save current chunk
                if current_chunk:
                    chunks.append(' '.join(current_chunk))

                # Start new chunk
                current_chunk = [sentence]
                current_words = sent_words
            else:
                current_chunk.append(sentence)
                current_words += sent_words

        # Save final chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def _has_table(self, text: str) -> bool:
        """Check if text contains table reference."""
        for pattern in TABLE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def _has_figure(self, text: str) -> bool:
        """Check if text contains figure reference."""
        for pattern in FIGURE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

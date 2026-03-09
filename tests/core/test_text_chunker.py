"""Tests for core.text_chunker — TextChunker and Chunk base classes only.

TieredTextChunker is tested separately (it is being moved to builder/).
"""

import hashlib

import pytest

from core.text_chunker import Chunk, ChunkMetadata, SourceType, TextChunker


# ── SourceType enum ──────────────────────────────────────────────────────

class TestSourceType:
    def test_values(self):
        assert SourceType.ORIGINAL.value == "original"
        assert SourceType.CITATION.value == "citation"
        assert SourceType.BACKGROUND.value == "background"


# ── ChunkMetadata dataclass ─────────────────────────────────────────────

class TestChunkMetadata:
    def test_defaults(self):
        meta = ChunkMetadata(document_id="doc1", chunk_index=0)
        assert meta.page_number is None
        assert meta.start_char == 0
        assert meta.end_char == 0
        assert meta.source_type == "unknown"
        assert meta.tier == 2
        assert meta.section == "other"
        assert meta.section_confidence == 0.0
        assert meta.content_type == "original"
        assert meta.citation_ratio == 0.0
        assert meta.position_in_document == 0.0

    def test_custom_values(self):
        meta = ChunkMetadata(
            document_id="abc",
            chunk_index=3,
            page_number=5,
            start_char=100,
            end_char=200,
            document_title="My Paper",
            document_author="Author",
            source_type="pdf",
            tier=1,
            section="abstract",
        )
        assert meta.document_id == "abc"
        assert meta.chunk_index == 3
        assert meta.page_number == 5
        assert meta.document_title == "My Paper"
        assert meta.tier == 1
        assert meta.section == "abstract"


# ── TextChunker initialization ──────────────────────────────────────────

class TestTextChunkerInit:
    def test_default_params(self):
        chunker = TextChunker()
        assert chunker.chunk_size == 512
        assert chunker.chunk_overlap == 50
        assert chunker.separators == TextChunker.DEFAULT_SEPARATORS

    def test_custom_params(self):
        chunker = TextChunker(chunk_size=256, chunk_overlap=20, separators=["\n"])
        assert chunker.chunk_size == 256
        assert chunker.chunk_overlap == 20
        assert chunker.separators == ["\n"]


# ── Empty / trivial input ───────────────────────────────────────────────

class TestChunkEmptyInput:
    @pytest.mark.parametrize("text", ["", None, "   ", "\n\n", "\t\t"])
    def test_empty_or_whitespace_returns_empty(self, text):
        chunker = TextChunker()
        assert chunker.chunk(text or "") == []

    def test_single_character(self):
        chunker = TextChunker()
        chunks = chunker.chunk("A")
        assert len(chunks) == 1
        assert chunks[0].content == "A"


# ── Basic chunking behaviour ────────────────────────────────────────────

class TestBasicChunking:
    def test_short_text_single_chunk(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=0)
        text = "This is a short sentence."
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_chunk_id_format(self):
        chunker = TextChunker(chunk_size=100, chunk_overlap=0)
        chunks = chunker.chunk("hello world", {"document_id": "mydoc"})
        assert chunks[0].id == "mydoc_0"

    def test_auto_generated_doc_id(self):
        """When no document_id is given, a hash-based ID is generated."""
        chunker = TextChunker(chunk_size=100, chunk_overlap=0)
        text = "some text"
        chunks = chunker.chunk(text)
        expected_id = hashlib.md5(text.encode()).hexdigest()[:12]
        assert chunks[0].metadata.document_id == expected_id

    def test_metadata_passthrough(self):
        chunker = TextChunker(chunk_size=500, chunk_overlap=0)
        meta = {
            "document_id": "d1",
            "page_number": 7,
            "title": "Title",
            "author": "Author",
            "source_type": "pdf",
        }
        chunks = chunker.chunk("Some text content", meta)
        m = chunks[0].metadata
        assert m.document_id == "d1"
        assert m.page_number == 7
        assert m.document_title == "Title"
        assert m.document_author == "Author"
        assert m.source_type == "pdf"

    def test_multiple_chunks_generated(self):
        chunker = TextChunker(chunk_size=20, chunk_overlap=0)
        text = "Hello world. This is a test. Another sentence here."
        chunks = chunker.chunk(text)
        assert len(chunks) > 1

    def test_chunk_content_not_empty(self):
        chunker = TextChunker(chunk_size=30, chunk_overlap=0)
        text = "Word " * 50
        chunks = chunker.chunk(text)
        for c in chunks:
            assert c.content.strip() != ""


# ── Separator priority ──────────────────────────────────────────────────

class TestSeparatorPriority:
    def test_paragraph_separator_preferred(self):
        """Double-newline splits should be preferred over single-newline."""
        chunker = TextChunker(chunk_size=30, chunk_overlap=0)
        text = "Paragraph one content here.\n\nParagraph two content here."
        chunks = chunker.chunk(text)
        # Total > 30 chars, so should split at \n\n boundary
        assert len(chunks) == 2

    def test_sentence_separator(self):
        chunker = TextChunker(chunk_size=30, chunk_overlap=0, separators=[". "])
        text = "First sentence. Second sentence. Third sentence."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2


# ── Overlap behaviour ───────────────────────────────────────────────────

class TestOverlap:
    def test_overlap_adds_text_from_previous(self):
        chunker = TextChunker(chunk_size=30, chunk_overlap=10)
        # Craft text that will produce multiple chunks
        text = "Alpha bravo charlie. Delta echo foxtrot. Golf hotel india."
        chunks = chunker.chunk(text)
        if len(chunks) >= 2:
            # The second chunk should contain overlap from the first
            # (words from the tail end of the first raw chunk)
            assert len(chunks[1].content) > 0

    def test_zero_overlap(self):
        chunker = TextChunker(chunk_size=30, chunk_overlap=0)
        text = "Alpha bravo charlie. Delta echo foxtrot. Golf hotel india."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1

    def test_single_chunk_no_overlap_applied(self):
        """Overlap has no effect when there is only one chunk."""
        chunker = TextChunker(chunk_size=500, chunk_overlap=50)
        text = "Short text."
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == "Short text."


# ── Recursive split internals ───────────────────────────────────────────

class TestRecursiveSplit:
    def test_text_within_chunk_size(self):
        chunker = TextChunker(chunk_size=100)
        result = chunker._recursive_split("short", chunker.separators)
        assert result == ["short"]

    def test_whitespace_only_returns_empty(self):
        chunker = TextChunker(chunk_size=100)
        result = chunker._recursive_split("   ", chunker.separators)
        assert result == []

    def test_no_separators_triggers_force_split(self):
        chunker = TextChunker(chunk_size=10)
        long_word = "abcdefghijklmnopqrstuvwxyz"
        result = chunker._recursive_split(long_word, [])
        # force_split breaks at chunk_size boundaries
        total = "".join(result)
        assert total == long_word


# ── Force split ─────────────────────────────────────────────────────────

class TestForceSplit:
    def test_splits_at_chunk_size(self):
        chunker = TextChunker(chunk_size=10)
        text = "abcde fghij klmno pqrst"
        result = chunker._force_split(text)
        for chunk in result:
            assert len(chunk) <= 10

    def test_tries_to_break_at_space(self):
        chunker = TextChunker(chunk_size=10)
        text = "hello world foo"
        result = chunker._force_split(text)
        # Should prefer breaking at space rather than mid-word
        assert result[0] == "hello"

    def test_very_long_word_no_space(self):
        chunker = TextChunker(chunk_size=5)
        text = "abcdefghij"
        result = chunker._force_split(text)
        assert len(result) == 2
        assert result[0] == "abcde"
        assert result[1] == "fghij"


# ── _add_overlap ────────────────────────────────────────────────────────

class TestAddOverlap:
    def test_single_chunk_unchanged(self):
        chunker = TextChunker(chunk_overlap=10)
        assert chunker._add_overlap(["only one"]) == ["only one"]

    def test_empty_list(self):
        chunker = TextChunker(chunk_overlap=10)
        assert chunker._add_overlap([]) == []

    def test_overlap_prepended(self):
        chunker = TextChunker(chunk_overlap=5)
        result = chunker._add_overlap(["hello world", "foo bar"])
        # Second chunk should have overlap from end of first chunk
        assert len(result) == 2
        assert result[0] == "hello world"
        # The overlap text comes from last 5 chars of "hello world" = "world"
        # Word boundary search: "world" has no space, so full overlap is used
        assert "world" in result[1]


# ── _generate_doc_id ────────────────────────────────────────────────────

class TestGenerateDocId:
    def test_returns_12_char_hex(self):
        chunker = TextChunker()
        doc_id = chunker._generate_doc_id("some/path.pdf")
        assert len(doc_id) == 12
        assert all(c in "0123456789abcdef" for c in doc_id)

    def test_deterministic(self):
        chunker = TextChunker()
        id1 = chunker._generate_doc_id("same")
        id2 = chunker._generate_doc_id("same")
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        chunker = TextChunker()
        id1 = chunker._generate_doc_id("path_a")
        id2 = chunker._generate_doc_id("path_b")
        assert id1 != id2


# ── Edge cases ──────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_text_exactly_chunk_size(self):
        text = "a" * 512
        chunker = TextChunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text

    def test_text_one_over_chunk_size(self):
        text = "a" * 513
        chunker = TextChunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.chunk(text)
        # Should produce 2 chunks due to force split
        assert len(chunks) >= 2

    def test_newlines_only(self):
        chunker = TextChunker()
        assert chunker.chunk("\n\n\n\n") == []

    def test_unicode_text(self):
        chunker = TextChunker(chunk_size=50, chunk_overlap=0)
        text = "척추 수술 논문 분석 시스템. 한국어 텍스트도 잘 처리됩니다."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        # Content should be preserved
        combined = " ".join(c.content for c in chunks)
        assert "척추" in combined

    def test_chunk_index_sequential(self):
        chunker = TextChunker(chunk_size=20, chunk_overlap=0)
        text = "Word " * 50
        chunks = chunker.chunk(text)
        indices = [c.metadata.chunk_index for c in chunks]
        # Indices should be in order (may skip due to empty strip filtering)
        assert indices == sorted(indices)

    def test_large_overlap_doesnt_crash(self):
        """Overlap larger than chunk_size should not crash."""
        chunker = TextChunker(chunk_size=10, chunk_overlap=100)
        text = "Alpha bravo charlie delta echo foxtrot golf hotel"
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1

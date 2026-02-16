"""Text Chunker module for splitting text into searchable chunks."""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .pdf_parser import DocumentMetadata, PageContent


class SourceType(Enum):
    """콘텐츠 출처 유형."""
    ORIGINAL = "original"
    CITATION = "citation"
    BACKGROUND = "background"


@dataclass
class ChunkMetadata:
    """Metadata for a text chunk."""
    document_id: str
    chunk_index: int
    page_number: Optional[int] = None
    start_char: int = 0
    end_char: int = 0
    document_title: Optional[str] = None
    document_author: Optional[str] = None
    source_type: str = "unknown"

    # Tiered indexing fields
    tier: int = 2                           # 1=핵심, 2=상세
    section: str = "other"                  # abstract, methods, results 등
    section_confidence: float = 0.0         # 섹션 분류 신뢰도
    content_type: str = "original"          # original, citation, background
    citation_ratio: float = 0.0             # 인용 내용 비율
    position_in_document: float = 0.0       # 문서 내 위치 (0.0~1.0)


@dataclass
class Chunk:
    """A text chunk with metadata."""
    id: str
    content: str
    metadata: ChunkMetadata


class TextChunker:
    """Split text into chunks suitable for embedding and retrieval."""

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None
    ):
        """
        Initialize the text chunker.

        Args:
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Number of overlapping characters between chunks
            separators: List of separators in priority order
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS

    def chunk(
        self,
        text: str,
        metadata: dict | None = None
    ) -> list[Chunk]:
        """
        Split text into chunks.

        Args:
            text: Text to split
            metadata: Optional metadata to attach to chunks

        Returns:
            List of Chunk objects
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}
        document_id = metadata.get("document_id", self._generate_doc_id(text))

        # Split text into chunks
        raw_chunks = self._recursive_split(text, self.separators)

        # Add overlap
        if self.chunk_overlap > 0:
            raw_chunks = self._add_overlap(raw_chunks)

        # Create Chunk objects
        chunks = []
        char_offset = 0

        for i, content in enumerate(raw_chunks):
            if not content.strip():
                continue

            chunk_id = f"{document_id}_{i}"

            chunk_metadata = ChunkMetadata(
                document_id=document_id,
                chunk_index=i,
                page_number=metadata.get("page_number"),
                start_char=char_offset,
                end_char=char_offset + len(content),
                document_title=metadata.get("title"),
                document_author=metadata.get("author"),
                source_type=metadata.get("source_type", "unknown")
            )

            chunks.append(Chunk(
                id=chunk_id,
                content=content.strip(),
                metadata=chunk_metadata
            ))

            char_offset += len(content)

        return chunks

    def chunk_document(
        self,
        pages: list["PageContent"],
        metadata: "DocumentMetadata"
    ) -> list[Chunk]:
        """
        Split a multi-page document into chunks.

        Args:
            pages: List of PageContent objects
            metadata: Document metadata

        Returns:
            List of Chunk objects with page information
        """
        document_id = self._generate_doc_id(metadata.file_path)
        all_chunks = []
        global_chunk_index = 0

        for page in pages:
            if not page.text or not page.text.strip():
                continue

            # Split page text
            raw_chunks = self._recursive_split(page.text, self.separators)

            if self.chunk_overlap > 0:
                raw_chunks = self._add_overlap(raw_chunks)

            # Create chunks with page information
            char_offset = 0
            for content in raw_chunks:
                if not content.strip():
                    continue

                chunk_id = f"{document_id}_{global_chunk_index}"

                chunk_metadata = ChunkMetadata(
                    document_id=document_id,
                    chunk_index=global_chunk_index,
                    page_number=page.page_number,
                    start_char=char_offset,
                    end_char=char_offset + len(content),
                    document_title=metadata.title,
                    document_author=metadata.author,
                    source_type=metadata.source_type
                )

                all_chunks.append(Chunk(
                    id=chunk_id,
                    content=content.strip(),
                    metadata=chunk_metadata
                ))

                char_offset += len(content)
                global_chunk_index += 1

        return all_chunks

    def chunk_web_content(
        self,
        text: str,
        metadata: Any
    ) -> list[Chunk]:
        """Split web content into chunks.

        Args:
            text: Web page text content
            metadata: Web metadata object (must have url, title, author attributes)

        Returns:
            List of Chunk objects

        Note:
            v1.15: web_scraper 모듈 제거에 따라 타입 힌트를 Any로 변경.
            metadata는 url, title, author 속성을 가진 객체이면 됩니다.
        """
        document_id = self._generate_doc_id(metadata.url)

        meta_dict = {
            "document_id": document_id,
            "title": metadata.title,
            "author": metadata.author,
            "source_type": "web"
        }

        chunks = self.chunk(text, meta_dict)

        # Update document_id in all chunks
        for chunk in chunks:
            chunk.metadata.document_id = document_id

        return chunks

    def _recursive_split(
        self,
        text: str,
        separators: list[str]
    ) -> list[str]:
        """
        Recursively split text using separators.

        Args:
            text: Text to split
            separators: List of separators to try

        Returns:
            List of text chunks
        """
        # Base case: text fits in chunk
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        # No more separators, force split
        if not separators:
            return self._force_split(text)

        separator = separators[0]
        remaining_separators = separators[1:]

        # Split by current separator
        parts = text.split(separator)

        chunks = []
        current_chunk = ""

        for part in parts:
            # Check if adding this part exceeds chunk size
            potential = current_chunk + separator + part if current_chunk else part

            if len(potential) <= self.chunk_size:
                current_chunk = potential
            else:
                # Save current chunk if not empty
                if current_chunk.strip():
                    chunks.append(current_chunk)

                # If part itself is too large, recursively split
                if len(part) > self.chunk_size:
                    sub_chunks = self._recursive_split(part, remaining_separators)
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = part

        # Don't forget the last chunk
        if current_chunk.strip():
            chunks.append(current_chunk)

        return chunks

    def _force_split(self, text: str) -> list[str]:
        """
        Force split text at chunk_size boundaries.

        Args:
            text: Text to split

        Returns:
            List of chunks
        """
        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))

            # Try to find a space to break at
            if end < len(text):
                space_idx = text.rfind(" ", start, end)
                if space_idx > start:
                    end = space_idx

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end

        return chunks

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """
        Add overlap between consecutive chunks.

        Args:
            chunks: List of chunks

        Returns:
            List of chunks with overlap
        """
        if len(chunks) <= 1 or self.chunk_overlap <= 0:
            return chunks

        overlapped = [chunks[0]]

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]

            # Get overlap from end of previous chunk
            overlap_text = prev_chunk[-self.chunk_overlap:]

            # Try to break at word boundary
            space_idx = overlap_text.find(" ")
            if space_idx > 0:
                overlap_text = overlap_text[space_idx + 1:]

            # Prepend overlap to current chunk
            current = chunks[i]
            overlapped.append(f"{overlap_text} {current}".strip())

        return overlapped

    def _generate_doc_id(self, source: str) -> str:
        """
        Generate a unique document ID.

        Args:
            source: Source identifier (file path or URL)

        Returns:
            Short hash-based ID
        """
        hash_obj = hashlib.md5(source.encode())
        return hash_obj.hexdigest()[:12]

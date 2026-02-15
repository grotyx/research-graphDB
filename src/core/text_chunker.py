"""Text Chunker module for splitting text into searchable chunks."""

import hashlib
import re
from dataclasses import dataclass, field
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


@dataclass
class TieredChunkOutput:
    """Tiered 청킹 결과."""
    chunks: list[Chunk] = field(default_factory=list)
    tier1_chunks: list[Chunk] = field(default_factory=list)
    tier2_chunks: list[Chunk] = field(default_factory=list)
    section_distribution: dict = field(default_factory=dict)
    tier_distribution: dict = field(default_factory=dict)
    total_chunks: int = 0
    total_tokens: int = 0


class TieredTextChunker(TextChunker):
    """Tier 기반 텍스트 청커 (TextChunker 확장)."""

    # 섹션 헤더 패턴
    SECTION_HEADERS = [
        (r'(?i)^abstract[:\s]', "abstract"),
        (r'(?i)^summary[:\s]', "abstract"),
        (r'(?i)^introduction[:\s]', "introduction"),
        (r'(?i)^background[:\s]', "introduction"),
        (r'(?i)^(?:materials?\s+and\s+)?methods?[:\s]', "methods"),
        (r'(?i)^patients?\s+and\s+methods?[:\s]', "methods"),
        (r'(?i)^results?[:\s]', "results"),
        (r'(?i)^findings?[:\s]', "results"),
        (r'(?i)^discussion[:\s]', "discussion"),
        (r'(?i)^conclusions?[:\s]', "conclusion"),
        (r'(?i)^summary\s+and\s+conclusions?[:\s]', "conclusion"),
    ]

    # Tier 매핑
    TIER_MAP = {
        "abstract": 1,
        "results": 1,
        "conclusion": 1,
        "introduction": 2,
        "methods": 2,
        "discussion": 2,
        "other": 2
    }

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
        use_section_classifier: bool = True,
        use_citation_detector: bool = True
    ):
        """초기화.

        Args:
            chunk_size: 청크 크기
            chunk_overlap: 오버랩 크기
            separators: 분리자 목록
            use_section_classifier: 섹션 분류기 사용 여부
            use_citation_detector: 인용 탐지기 사용 여부
        """
        super().__init__(chunk_size, chunk_overlap, separators)
        self.use_section_classifier = use_section_classifier
        self.use_citation_detector = use_citation_detector

        # 모듈 로드 (사용 시)
        self._section_classifier = None
        self._citation_detector = None

    def _get_section_classifier(self):
        """섹션 분류기 lazy loading."""
        if self._section_classifier is None and self.use_section_classifier:
            try:
                from ..builder.section_classifier import SectionClassifier
                self._section_classifier = SectionClassifier()
            except ImportError:
                self.use_section_classifier = False
        return self._section_classifier

    def _get_citation_detector(self):
        """인용 탐지기 lazy loading."""
        if self._citation_detector is None and self.use_citation_detector:
            try:
                from ..builder.citation_detector import CitationDetector
                self._citation_detector = CitationDetector()
            except ImportError:
                self.use_citation_detector = False
        return self._citation_detector

    def chunk_with_tiers(
        self,
        text: str,
        metadata: dict | None = None
    ) -> TieredChunkOutput:
        """텍스트를 Tiered 청크로 분할.

        Args:
            text: 분할할 텍스트
            metadata: 문서 메타데이터

        Returns:
            TieredChunkOutput
        """
        if not text or not text.strip():
            return TieredChunkOutput()

        metadata = metadata or {}
        document_id = metadata.get("document_id", self._generate_doc_id(text))

        # 1. 섹션 경계 탐지
        sections = self._detect_section_boundaries(text)

        # 2. 각 섹션 처리
        all_chunks = []
        global_index = 0
        total_length = len(text)

        for section_info in sections:
            section_chunks = self._process_section(
                section_info,
                document_id,
                metadata,
                global_index,
                total_length
            )
            all_chunks.extend(section_chunks)
            global_index += len(section_chunks)

        # 3. Tier별 분류
        tier1_chunks = [c for c in all_chunks if c.metadata.tier == 1]
        tier2_chunks = [c for c in all_chunks if c.metadata.tier == 2]

        # 4. 통계 계산
        section_dist = {}
        for chunk in all_chunks:
            section = chunk.metadata.section
            section_dist[section] = section_dist.get(section, 0) + 1

        tier_dist = {1: len(tier1_chunks), 2: len(tier2_chunks)}

        return TieredChunkOutput(
            chunks=all_chunks,
            tier1_chunks=tier1_chunks,
            tier2_chunks=tier2_chunks,
            section_distribution=section_dist,
            tier_distribution=tier_dist,
            total_chunks=len(all_chunks),
            total_tokens=sum(len(c.content.split()) for c in all_chunks)
        )

    def _detect_section_boundaries(self, text: str) -> list[dict]:
        """섹션 경계 탐지.

        Args:
            text: 분석할 텍스트

        Returns:
            섹션 정보 목록
        """
        sections = []
        lines = text.split('\n')
        current_section = {"name": "other", "start_line": 0, "text": "", "start_pos": 0}
        current_pos = 0

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # 섹션 헤더 확인
            matched_section = None
            for pattern, section_name in self.SECTION_HEADERS:
                if re.match(pattern, line_stripped):
                    matched_section = section_name
                    break

            if matched_section:
                # 이전 섹션 저장
                if current_section["text"].strip():
                    sections.append(current_section)

                # 새 섹션 시작
                current_section = {
                    "name": matched_section,
                    "start_line": i,
                    "text": line + "\n",
                    "start_pos": current_pos
                }
            else:
                current_section["text"] += line + "\n"

            current_pos += len(line) + 1

        # 마지막 섹션 저장
        if current_section["text"].strip():
            sections.append(current_section)

        # 섹션이 없으면 전체를 하나의 섹션으로
        if not sections:
            sections = [{"name": "other", "start_line": 0, "text": text, "start_pos": 0}]

        return sections

    def _process_section(
        self,
        section_info: dict,
        document_id: str,
        doc_metadata: dict,
        start_index: int,
        total_length: int
    ) -> list[Chunk]:
        """단일 섹션 처리.

        Args:
            section_info: 섹션 정보
            document_id: 문서 ID
            doc_metadata: 문서 메타데이터
            start_index: 시작 인덱스
            total_length: 전체 문서 길이

        Returns:
            Chunk 목록
        """
        section_name = section_info["name"]
        section_text = section_info["text"]
        section_start = section_info.get("start_pos", 0)

        # Tier 결정
        tier = self.TIER_MAP.get(section_name, 2)

        # 섹션 분류기로 신뢰도 계산
        section_confidence = 1.0
        if self.use_section_classifier:
            classifier = self._get_section_classifier()
            if classifier:
                from ..builder.section_classifier import SectionInput
                position = section_start / total_length if total_length > 0 else 0
                result = classifier.classify(SectionInput(
                    text=section_text[:500],  # 앞부분만 분석
                    source_position=position
                ))
                section_confidence = result.confidence

                # 분류기 결과가 다르면 더 낮은 신뢰도로 업데이트
                if result.section != section_name and result.confidence > 0.7:
                    section_name = result.section
                    tier = self.TIER_MAP.get(section_name, 2)

        # 텍스트를 청크로 분할 (기존 메서드 사용)
        raw_chunks = self._recursive_split(section_text, self.separators)

        if self.chunk_overlap > 0 and len(raw_chunks) > 1:
            raw_chunks = self._add_overlap(raw_chunks)

        # Chunk 객체 생성
        chunks = []
        char_offset = section_start

        for i, content in enumerate(raw_chunks):
            if not content.strip():
                continue

            chunk_index = start_index + len(chunks)
            chunk_id = f"{document_id}_{chunk_index}"

            # 인용 탐지
            content_type = "original"
            citation_ratio = 0.0

            if self.use_citation_detector:
                detector = self._get_citation_detector()
                if detector:
                    from ..builder.citation_detector import CitationInput
                    cit_result = detector.detect(CitationInput(text=content))
                    content_type = cit_result.source_type.value
                    citation_ratio = 1.0 - cit_result.original_ratio

            # 문서 내 위치 계산
            position_in_doc = char_offset / total_length if total_length > 0 else 0

            chunk_metadata = ChunkMetadata(
                document_id=document_id,
                chunk_index=chunk_index,
                page_number=doc_metadata.get("page_number"),
                start_char=char_offset,
                end_char=char_offset + len(content),
                document_title=doc_metadata.get("title"),
                document_author=doc_metadata.get("author"),
                source_type=doc_metadata.get("source_type", "pdf"),
                tier=tier,
                section=section_name,
                section_confidence=section_confidence,
                content_type=content_type,
                citation_ratio=citation_ratio,
                position_in_document=position_in_doc
            )

            chunks.append(Chunk(
                id=chunk_id,
                content=content.strip(),
                metadata=chunk_metadata
            ))

            char_offset += len(content)

        return chunks

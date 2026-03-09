"""Tiered Text Chunker module.

TieredTextChunker는 TextChunker를 확장하여 섹션 분류 및 인용 탐지를
통합한 Tier 기반 청킹을 제공합니다.

Note:
    v1.21.2: core/text_chunker.py에서 builder/로 이동 (D-006).
    core→builder 계층 위반 해소를 위해 builder/ 내에서 직접 import.
"""

from dataclasses import dataclass, field

from core.text_chunker import TextChunker, Chunk, ChunkMetadata
from builder.section_classifier import SectionClassifier, SectionInput
from builder.citation_detector import CitationDetector, CitationInput


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

        # 모듈 인스턴스 (사용 시 생성)
        self._section_classifier = None
        self._citation_detector = None

    def _get_section_classifier(self):
        """섹션 분류기 lazy loading."""
        if self._section_classifier is None and self.use_section_classifier:
            self._section_classifier = SectionClassifier()
        return self._section_classifier

    def _get_citation_detector(self):
        """인용 탐지기 lazy loading."""
        if self._citation_detector is None and self.use_citation_detector:
            self._citation_detector = CitationDetector()
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
        import re

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

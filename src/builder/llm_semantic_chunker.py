"""LLM-based Semantic Chunker.

LLM을 사용하여 논문 텍스트를 의미 단위로 분할합니다.
기본값: Claude Haiku 4.5 (환경변수로 변경 가능)
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional, Union

from llm import LLMClient, ClaudeClient, GeminiClient
from llm.prompts import SEMANTIC_CHUNKER_SYSTEM, SEMANTIC_CHUNKER_SCHEMA
from builder.llm_section_classifier import SectionBoundary, SECTION_TIERS
from builder.tiered_text_chunker import TieredTextChunker

logger = logging.getLogger(__name__)


@dataclass
class ChunkingConfig:
    """청킹 설정."""
    target_min_words: int = 300      # 최소 단어 수
    target_max_words: int = 500      # 최대 단어 수
    hard_max_words: int = 800        # 절대 최대 (이상이면 분할)
    overlap_sentences: int = 1       # 청크 간 겹침 문장 수
    preserve_paragraphs: bool = True  # 문단 경계 유지
    max_text_per_llm_call: int = 15000  # LLM 호출당 최대 문자


@dataclass
class SemanticChunk:
    """의미 단위 청크."""
    chunk_id: str              # 고유 ID (document_id + section + index)
    content: str               # 청크 내용
    section_type: str          # 섹션 타입
    tier: int                  # 1=핵심, 2=상세
    topic_summary: str         # 1문장 주제 요약
    is_complete_thought: bool  # 완전한 생각/문단인지
    contains_finding: bool     # 연구 결과 포함 여부
    char_start: int            # 원본 텍스트 시작 위치
    char_end: int              # 원본 텍스트 끝 위치
    word_count: int            # 단어 수

    # 선택적 메타데이터
    subsection: Optional[str] = None  # 하위 섹션 (e.g., "Statistical Analysis")
    has_table_reference: bool = False  # 표 참조 포함
    has_figure_reference: bool = False  # 그림 참조 포함


class ChunkingError(Exception):
    """청킹 에러."""
    pass


class LLMSemanticChunker:
    """LLM 기반 의미 청킹."""

    # 표/그림 참조 패턴
    TABLE_PATTERN = re.compile(r'\b(?:Table|Tables?)\s+\d+', re.IGNORECASE)
    FIGURE_PATTERN = re.compile(r'\b(?:Fig(?:ure)?s?\.?)\s+\d+', re.IGNORECASE)

    def __init__(
        self,
        llm_client: Union[LLMClient, ClaudeClient, GeminiClient] = None,
        config: ChunkingConfig = None,
        fallback_chunker: TieredTextChunker = None,
        # 하위 호환성
        gemini_client: Union[LLMClient, ClaudeClient, GeminiClient] = None
    ):
        """초기화.

        Args:
            llm_client: LLM 클라이언트 (None이면 자동 생성)
            config: 청킹 설정
            fallback_chunker: 규칙 기반 Fallback 청커
            gemini_client: 레거시 파라미터 (llm_client 사용 권장)
        """
        # 하위 호환성: gemini_client 파라미터도 지원
        client = llm_client or gemini_client
        if client is None:
            client = LLMClient()
        self.llm = client
        self.config = config or ChunkingConfig()
        self.fallback = fallback_chunker

    async def chunk_section(
        self,
        section_text: str,
        section_type: str,
        document_id: str,
        section_start_char: int = 0
    ) -> list[SemanticChunk]:
        """단일 섹션을 의미 단위로 분할 (LLM 기반만 사용).

        Args:
            section_text: 섹션 텍스트
            section_type: 섹션 타입 (abstract, methods, etc.)
            document_id: 문서 ID
            section_start_char: 원본 문서에서 섹션 시작 위치

        Returns:
            SemanticChunk 목록

        Raises:
            ChunkingError: 청킹 실패
        """
        if not section_text or not section_text.strip():
            return []

        # 긴 텍스트는 분할 처리
        if len(section_text) > self.config.max_text_per_llm_call:
            chunks = await self._chunk_long_section(
                section_text, section_type, document_id
            )
        else:
            chunks = await self._chunk_with_llm(
                section_text, section_type, document_id
            )

        # 위치 조정 및 후처리
        return self._post_process(chunks, section_start_char)

    async def chunk_document(
        self,
        sections: list[SectionBoundary],
        full_text: str,
        document_id: str
    ) -> list[SemanticChunk]:
        """전체 문서를 청킹.

        Args:
            sections: 섹션 경계 목록
            full_text: 전체 문서 텍스트
            document_id: 문서 ID

        Returns:
            전체 문서의 SemanticChunk 목록
        """
        if not sections or not full_text:
            return []

        # 각 섹션 병렬 처리
        tasks = []
        for section in sections:
            section_text = full_text[section.start_char:section.end_char]
            tasks.append(
                self.chunk_section(
                    section_text,
                    section.section_type,
                    document_id,
                    section.start_char
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 병합
        all_chunks = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Section {sections[i].section_type} chunking failed: {result}")
                continue
            all_chunks.extend(result)

        # 청크 ID 재정렬
        all_chunks.sort(key=lambda c: c.char_start)
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_id = f"{document_id}_{i:03d}"

        return all_chunks

    async def chunk_with_context(
        self,
        section_text: str,
        section_type: str,
        document_context: str,
        document_id: str
    ) -> list[SemanticChunk]:
        """문서 컨텍스트를 활용한 청킹.

        Args:
            section_text: 섹션 텍스트
            section_type: 섹션 타입
            document_context: 문서 컨텍스트 (보통 초록)
            document_id: 문서 ID

        Returns:
            SemanticChunk 목록
        """
        # 컨텍스트를 프롬프트에 추가
        # 현재는 기본 청킹과 동일하게 처리 (향후 확장 가능)
        return await self.chunk_section(section_text, section_type, document_id)

    async def _chunk_with_llm(
        self,
        text: str,
        section_type: str,
        document_id: str
    ) -> list[SemanticChunk]:
        """LLM을 사용한 청킹.

        Args:
            text: 청킹할 텍스트
            section_type: 섹션 타입
            document_id: 문서 ID

        Returns:
            SemanticChunk 목록
        """
        word_count = len(text.split())

        prompt = f"""Divide this {section_type} section into semantic chunks.

Section text:
---
{text}
---

Word count: {word_count}
Target chunk size: {self.config.target_min_words}-{self.config.target_max_words} words

For each chunk, provide:
1. content: The exact text of the chunk
2. topic_summary: A single sentence summarizing the chunk's main point
3. is_complete_thought: Whether this is a complete logical unit (true/false)
4. contains_finding: Whether this contains a research finding/result (true/false)
5. char_start: Starting character position in the input text
6. char_end: Ending character position

Important:
- Chunks should cover the ENTIRE input text with no gaps
- Character positions must be exact (0-indexed)
- Every character must belong to exactly one chunk
- If the text is short (< {self.config.target_min_words} words), return it as a single chunk"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "chunks": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "content": {"type": "STRING"},
                            "topic_summary": {"type": "STRING"},
                            "is_complete_thought": {"type": "BOOLEAN"},
                            "contains_finding": {"type": "BOOLEAN"},
                            "char_start": {"type": "INTEGER"},
                            "char_end": {"type": "INTEGER"},
                            "subsection": {"type": "STRING"}
                        },
                        "required": ["content", "topic_summary", "is_complete_thought",
                                     "contains_finding", "char_start", "char_end"]
                    }
                },
                "total_chunks": {"type": "INTEGER"}
            },
            "required": ["chunks", "total_chunks"]
        }

        result = await self.llm.generate_json(
            prompt=prompt,
            schema=schema,
            system=SEMANTIC_CHUNKER_SYSTEM
        )

        chunks = []
        tier = SECTION_TIERS.get(section_type, 2)

        # LLM 위치가 부정확하므로 content 기반으로 위치 재계산
        current_pos = 0

        for i, item in enumerate(result.get("chunks", [])):
            content = item.get("content", "")
            if not content.strip():
                continue

            # 원본 텍스트에서 content 위치 찾기 (LLM 제공 위치보다 정확)
            content_start = content[:50].strip()  # 첫 50자로 검색
            found_pos = text.find(content_start, current_pos)

            if found_pos >= 0:
                char_start = found_pos
                char_end = char_start + len(content)
                current_pos = char_end  # 다음 검색 시작점
            else:
                # 찾지 못하면 LLM 제공 위치 사용
                char_start = item.get("char_start", current_pos)
                char_end = item.get("char_end", char_start + len(content))
                current_pos = char_end

            # 표/그림 참조 감지
            has_table = bool(self.TABLE_PATTERN.search(content))
            has_figure = bool(self.FIGURE_PATTERN.search(content))

            chunk = SemanticChunk(
                chunk_id=self._generate_chunk_id(document_id, section_type, i),
                content=content,
                section_type=section_type,
                tier=tier,
                topic_summary=item.get("topic_summary", ""),
                is_complete_thought=item.get("is_complete_thought", True),
                contains_finding=item.get("contains_finding", False),
                char_start=char_start,
                char_end=min(char_end, len(text)),
                word_count=len(content.split()),
                subsection=item.get("subsection"),
                has_table_reference=has_table,
                has_figure_reference=has_figure
            )
            chunks.append(chunk)

        return chunks

    async def _chunk_long_section(
        self,
        section_text: str,
        section_type: str,
        document_id: str
    ) -> list[SemanticChunk]:
        """긴 섹션 분할 처리.

        Args:
            section_text: 긴 섹션 텍스트
            section_type: 섹션 타입
            document_id: 문서 ID

        Returns:
            SemanticChunk 목록
        """
        # 문단으로 분할
        paragraphs = self._split_into_paragraphs(section_text)

        # 문단 그룹화
        groups = self._group_paragraphs(paragraphs)

        # 각 그룹 청킹
        all_chunks = []
        chunk_index = 0

        for group in groups:
            group_text = group["text"]
            offset = group["offset"]

            try:
                chunks = await self._chunk_with_llm(group_text, section_type, document_id)

                # 위치 오프셋 조정
                for chunk in chunks:
                    chunk.char_start += offset
                    chunk.char_end += offset
                    chunk.chunk_id = self._generate_chunk_id(
                        document_id, section_type, chunk_index
                    )
                    chunk_index += 1

                all_chunks.extend(chunks)

            except Exception as e:
                logger.warning(f"Group chunking failed: {e}")
                # 그룹 전체를 단일 청크로
                all_chunks.append(SemanticChunk(
                    chunk_id=self._generate_chunk_id(document_id, section_type, chunk_index),
                    content=group_text,
                    section_type=section_type,
                    tier=SECTION_TIERS.get(section_type, 2),
                    topic_summary="[Group chunking failed]",
                    is_complete_thought=True,
                    contains_finding=False,
                    char_start=offset,
                    char_end=offset + len(group_text),
                    word_count=len(group_text.split())
                ))
                chunk_index += 1

        return all_chunks

    def _split_into_paragraphs(self, text: str) -> list[dict]:
        """텍스트를 문단으로 분할.

        Args:
            text: 분할할 텍스트

        Returns:
            문단 정보 목록 [{text, start, end}, ...]
        """
        paragraphs = []
        current_pos = 0

        # 빈 줄로 문단 분리
        for match in re.finditer(r'(.+?)(?:\n\s*\n|\Z)', text, re.DOTALL):
            para_text = match.group(1).strip()
            if para_text:
                start = match.start()
                end = match.end()
                paragraphs.append({
                    "text": para_text,
                    "start": start,
                    "end": end
                })

        return paragraphs

    def _group_paragraphs(self, paragraphs: list[dict]) -> list[dict]:
        """문단을 적절한 크기의 그룹으로 묶음.

        Args:
            paragraphs: 문단 목록

        Returns:
            그룹 목록 [{text, offset}, ...]
        """
        if not paragraphs:
            return []

        groups = []
        current_group_text = ""
        current_group_offset = paragraphs[0]["start"] if paragraphs else 0
        current_word_count = 0

        max_words_per_group = 2000  # 그룹당 최대 단어

        for para in paragraphs:
            para_text = para["text"]
            para_words = len(para_text.split())

            if current_word_count + para_words > max_words_per_group and current_group_text:
                # 현재 그룹 저장
                groups.append({
                    "text": current_group_text.strip(),
                    "offset": current_group_offset
                })

                # 새 그룹 시작
                current_group_text = para_text
                current_group_offset = para["start"]
                current_word_count = para_words
            else:
                # 현재 그룹에 추가
                if current_group_text:
                    current_group_text += "\n\n" + para_text
                else:
                    current_group_text = para_text
                    current_group_offset = para["start"]
                current_word_count += para_words

        # 마지막 그룹 저장
        if current_group_text.strip():
            groups.append({
                "text": current_group_text.strip(),
                "offset": current_group_offset
            })

        return groups

    def _validate_chunks(
        self,
        chunks: list[SemanticChunk],
        text_length: int
    ) -> bool:
        """청킹 결과 검증.

        Args:
            chunks: 청크 목록
            text_length: 원본 텍스트 길이

        Returns:
            유효성 여부
        """
        if not chunks:
            return False

        # 1. Content 기반 커버리지 (위치 기반 대신 - LLM 위치 오차 허용)
        # LLM이 위치를 부정확하게 반환하므로 content 길이 합계로 검증
        total_content_chars = sum(len(c.content) for c in chunks)
        coverage_ratio = total_content_chars / text_length if text_length > 0 else 0

        # 50% 이상이면 허용 (LLM이 중복 제거하거나 정리할 수 있음)
        if coverage_ratio < 0.50:
            logger.warning(f"Low content coverage: {total_content_chars}/{text_length} ({coverage_ratio:.1%})")
            return False
        elif coverage_ratio < 0.70:
            logger.info(f"Acceptable content coverage: {total_content_chars}/{text_length} ({coverage_ratio:.1%})")

        # 2. 빈 청크 확인
        for chunk in chunks:
            if not chunk.content.strip():
                logger.warning("Empty chunk found")
                return False

        # 3. 최소 청크 수 확인 (매우 짧은 텍스트 제외)
        if text_length > 500 and len(chunks) == 0:
            logger.warning("No chunks created for long text")
            return False

        return True

    def _post_process(
        self,
        chunks: list[SemanticChunk],
        section_start_char: int
    ) -> list[SemanticChunk]:
        """후처리: 위치 조정, 작은 청크 병합 등.

        Args:
            chunks: 청크 목록
            section_start_char: 섹션 시작 위치

        Returns:
            후처리된 청크 목록
        """
        # 위치 조정
        for chunk in chunks:
            chunk.char_start += section_start_char
            chunk.char_end += section_start_char

        # 작은 청크 병합
        if len(chunks) > 1:
            chunks = self._merge_small_chunks(chunks)

        return chunks

    def _merge_small_chunks(
        self,
        chunks: list[SemanticChunk]
    ) -> list[SemanticChunk]:
        """작은 청크를 인접 청크와 병합.

        Args:
            chunks: 청크 목록

        Returns:
            병합된 청크 목록
        """
        if not chunks:
            return chunks

        min_words = self.config.target_min_words // 2  # 최소 단어의 절반 미만이면 병합
        result = []
        buffer = None

        for chunk in chunks:
            if buffer is None:
                buffer = chunk
                continue

            # 버퍼가 너무 작으면 현재 청크와 병합
            if buffer.word_count < min_words:
                buffer = self._merge_two_chunks(buffer, chunk)
            # 현재 청크가 너무 작으면 버퍼와 병합
            elif chunk.word_count < min_words:
                buffer = self._merge_two_chunks(buffer, chunk)
            else:
                result.append(buffer)
                buffer = chunk

        if buffer:
            # 마지막 버퍼도 너무 작으면 이전 청크와 병합
            if result and buffer.word_count < min_words:
                result[-1] = self._merge_two_chunks(result[-1], buffer)
            else:
                result.append(buffer)

        return result

    def _merge_two_chunks(
        self,
        chunk1: SemanticChunk,
        chunk2: SemanticChunk
    ) -> SemanticChunk:
        """두 청크를 하나로 병합.

        Args:
            chunk1: 첫 번째 청크
            chunk2: 두 번째 청크

        Returns:
            병합된 청크
        """
        merged_content = chunk1.content + "\n\n" + chunk2.content
        merged_summary = f"{chunk1.topic_summary}; {chunk2.topic_summary}"

        return SemanticChunk(
            chunk_id=chunk1.chunk_id,
            content=merged_content,
            section_type=chunk1.section_type,
            tier=min(chunk1.tier, chunk2.tier),  # 더 높은 우선순위 유지
            topic_summary=merged_summary[:200],  # 길이 제한
            is_complete_thought=chunk1.is_complete_thought and chunk2.is_complete_thought,
            contains_finding=chunk1.contains_finding or chunk2.contains_finding,
            char_start=chunk1.char_start,
            char_end=chunk2.char_end,
            word_count=len(merged_content.split()),
            subsection=chunk1.subsection or chunk2.subsection,
            has_table_reference=chunk1.has_table_reference or chunk2.has_table_reference,
            has_figure_reference=chunk1.has_figure_reference or chunk2.has_figure_reference
        )

    def _use_fallback(
        self,
        section_text: str,
        section_type: str,
        document_id: str,
        section_start_char: int
    ) -> list[SemanticChunk]:
        """규칙 기반 Fallback 청킹.

        Args:
            section_text: 섹션 텍스트
            section_type: 섹션 타입
            document_id: 문서 ID
            section_start_char: 섹션 시작 위치

        Returns:
            SemanticChunk 목록
        """
        if not self.fallback:
            return []

        # TieredTextChunker 사용
        result = self.fallback.chunk_with_tiers(
            section_text,
            {"document_id": document_id}
        )

        tier = SECTION_TIERS.get(section_type, 2)
        chunks = []

        for i, chunk in enumerate(result.chunks):
            semantic_chunk = SemanticChunk(
                chunk_id=self._generate_chunk_id(document_id, section_type, i),
                content=chunk.content,
                section_type=section_type,
                tier=tier,
                topic_summary=f"[Rule-based chunk {i+1}]",
                is_complete_thought=True,
                contains_finding=False,
                char_start=section_start_char + chunk.metadata.start_char,
                char_end=section_start_char + chunk.metadata.end_char,
                word_count=len(chunk.content.split()),
                has_table_reference=bool(self.TABLE_PATTERN.search(chunk.content)),
                has_figure_reference=bool(self.FIGURE_PATTERN.search(chunk.content))
            )
            chunks.append(semantic_chunk)

        return chunks

    def _generate_chunk_id(
        self,
        document_id: str,
        section_type: str,
        index: int
    ) -> str:
        """청크 ID 생성.

        Args:
            document_id: 문서 ID
            section_type: 섹션 타입
            index: 청크 인덱스

        Returns:
            청크 ID
        """
        return f"{document_id}_{section_type}_{index:03d}"

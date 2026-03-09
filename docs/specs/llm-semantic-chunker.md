# LLM Semantic Chunker Specification

## Overview

Gemini LLM을 사용하여 논문 텍스트를 의미 단위로 분할합니다.

### 목적
- 문자 수가 아닌 **의미 단위**로 텍스트 분할
- 완전한 생각/발견을 하나의 청크로 유지
- 각 청크에 1문장 주제 요약 생성
- 연구 결과 포함 여부 표시

### 입출력 요약
- **입력**: 섹션 텍스트 + 섹션 타입 (또는 전체 문서 + 섹션 경계)
- **출력**: 의미 청크 목록 (내용, 주제 요약, 메타데이터)

---

## Data Structures

### SemanticChunk

```python
from dataclasses import dataclass
from typing import Optional

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
```

### ChunkingConfig

```python
@dataclass
class ChunkingConfig:
    """청킹 설정."""
    target_min_words: int = 300      # 최소 단어 수
    target_max_words: int = 500      # 최대 단어 수
    hard_max_words: int = 800        # 절대 최대 (이상이면 분할)
    overlap_sentences: int = 1       # 청크 간 겹침 문장 수
    preserve_paragraphs: bool = True  # 문단 경계 유지
```

---

## Interface

### LLMSemanticChunker

```python
class LLMSemanticChunker:
    """LLM 기반 의미 청킹."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        config: ChunkingConfig = None,
        fallback_chunker: TieredTextChunker = None
    ):
        """초기화.

        Args:
            gemini_client: Gemini API 클라이언트
            config: 청킹 설정
            fallback_chunker: 규칙 기반 Fallback 청커
        """

    async def chunk_section(
        self,
        section_text: str,
        section_type: str,
        document_id: str,
        section_start_char: int = 0
    ) -> list[SemanticChunk]:
        """단일 섹션을 의미 단위로 분할.

        Args:
            section_text: 섹션 텍스트
            section_type: 섹션 타입 (abstract, methods, etc.)
            document_id: 문서 ID
            section_start_char: 원본 문서에서 섹션 시작 위치

        Returns:
            SemanticChunk 목록
        """

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

    async def chunk_with_context(
        self,
        section_text: str,
        section_type: str,
        document_context: str,  # 논문 초록
        document_id: str
    ) -> list[SemanticChunk]:
        """문서 컨텍스트를 활용한 청킹.

        초록을 참조하여 더 정확한 청크 경계와 요약 생성.
        """
```

---

## LLM Prompt Template

### System Prompt

```python
SEMANTIC_CHUNK_SYSTEM = """You are a medical text segmentation expert.

Your task is to divide medical paper sections into semantic chunks that:
1. Contain ONE complete thought, finding, or logical unit
2. Are self-contained and understandable without surrounding context
3. Preserve the integrity of related information (don't split mid-argument)
4. Are approximately 300-500 words (flexible based on content)

Guidelines:
- Keep related statistics together with their interpretation
- Don't split a single finding across multiple chunks
- Group related sentences about the same topic
- Respect paragraph boundaries when possible
- Identify if the chunk contains a key research finding
"""
```

### User Prompt Template

```python
SEMANTIC_CHUNK_USER = """Divide this {section_type} section into semantic chunks.

Section text:
---
{text}
---

Word count: {word_count}
Target chunk size: 300-500 words

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
"""
```

### Output JSON Schema

```python
SEMANTIC_CHUNK_SCHEMA = {
    "type": "object",
    "properties": {
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "topic_summary": {"type": "string", "maxLength": 200},
                    "is_complete_thought": {"type": "boolean"},
                    "contains_finding": {"type": "boolean"},
                    "char_start": {"type": "integer", "minimum": 0},
                    "char_end": {"type": "integer", "minimum": 0},
                    "subsection": {"type": ["string", "null"]},
                    "has_table_reference": {"type": "boolean"},
                    "has_figure_reference": {"type": "boolean"}
                },
                "required": ["content", "topic_summary", "is_complete_thought", "contains_finding", "char_start", "char_end"]
            }
        },
        "total_chunks": {"type": "integer"},
        "chunking_notes": {"type": "string"}
    },
    "required": ["chunks", "total_chunks"]
}
```

---

## Implementation Notes

### 청크 ID 생성

```python
def _generate_chunk_id(
    self,
    document_id: str,
    section_type: str,
    index: int
) -> str:
    """청크 ID 생성.

    Format: {document_id}_{section_type}_{index:03d}
    Example: paper123_results_001
    """
    return f"{document_id}_{section_type}_{index:03d}"
```

### 청크 크기 검증

```python
def _validate_chunk_size(self, chunk: SemanticChunk) -> bool:
    """청크 크기 검증."""
    word_count = len(chunk.content.split())

    # 너무 작은 청크
    if word_count < self.config.target_min_words * 0.5:
        return False

    # 너무 큰 청크
    if word_count > self.config.hard_max_words:
        return False

    return True

def _merge_small_chunks(
    self,
    chunks: list[SemanticChunk]
) -> list[SemanticChunk]:
    """작은 청크 병합."""
    result = []
    buffer = None

    for chunk in chunks:
        if buffer is None:
            buffer = chunk
        elif len(buffer.content.split()) + len(chunk.content.split()) <= self.config.target_max_words:
            # 병합
            buffer = self._merge_chunks(buffer, chunk)
        else:
            result.append(buffer)
            buffer = chunk

    if buffer:
        result.append(buffer)

    return result
```

### 긴 섹션 처리

```python
async def _chunk_long_section(
    self,
    section_text: str,
    section_type: str,
    document_id: str
) -> list[SemanticChunk]:
    """긴 섹션 분할 처리.

    1. 문단 단위로 초기 분할
    2. 각 문단 그룹에 LLM 적용
    3. 결과 병합
    """
    # 문단으로 분할
    paragraphs = section_text.split('\n\n')

    # 문단 그룹화 (각 그룹 ~2000 단어)
    groups = self._group_paragraphs(paragraphs, max_words=2000)

    # 각 그룹 청킹
    all_chunks = []
    offset = 0

    for group in groups:
        group_text = '\n\n'.join(group)
        chunks = await self._chunk_single(group_text, section_type, document_id)

        # 위치 오프셋 조정
        for chunk in chunks:
            chunk.char_start += offset
            chunk.char_end += offset

        all_chunks.extend(chunks)
        offset += len(group_text) + 2  # '\n\n' 길이

    return all_chunks
```

### Fallback 전략

```python
async def chunk_section(
    self,
    section_text: str,
    section_type: str,
    document_id: str,
    section_start_char: int = 0
) -> list[SemanticChunk]:
    try:
        # LLM 청킹 시도
        chunks = await self._chunk_with_llm(section_text, section_type, document_id)

        # 결과 검증
        if self._validate_chunks(chunks, len(section_text)):
            return self._adjust_positions(chunks, section_start_char)

        raise ChunkingError("Invalid LLM chunking result")

    except Exception as e:
        if self.fallback_chunker:
            logger.warning(f"LLM chunking failed, using fallback: {e}")
            return self._use_rule_based_fallback(
                section_text, section_type, document_id, section_start_char
            )

        # 최후의 수단: 전체를 단일 청크로
        return [SemanticChunk(
            chunk_id=self._generate_chunk_id(document_id, section_type, 0),
            content=section_text,
            section_type=section_type,
            tier=SECTION_TIERS.get(section_type, 2),
            topic_summary="[Failed to generate summary]",
            is_complete_thought=True,
            contains_finding=False,
            char_start=section_start_char,
            char_end=section_start_char + len(section_text),
            word_count=len(section_text.split())
        )]
```

### 결과 검증

```python
def _validate_chunks(
    self,
    chunks: list[SemanticChunk],
    text_length: int
) -> bool:
    """청킹 결과 검증."""
    if not chunks:
        return False

    # 1. 전체 텍스트 커버리지
    total_chars = sum(c.char_end - c.char_start for c in chunks)
    if total_chars < text_length * 0.95:  # 95% 이상 커버
        return False

    # 2. 겹침 확인
    sorted_chunks = sorted(chunks, key=lambda c: c.char_start)
    for i in range(len(sorted_chunks) - 1):
        if sorted_chunks[i].char_end > sorted_chunks[i+1].char_start:
            return False

    # 3. 빈 청크 확인
    for chunk in chunks:
        if not chunk.content.strip():
            return False

    return True
```

---

## Test Cases

### 단위 테스트

```python
import pytest

class TestLLMSemanticChunker:
    @pytest.fixture
    def chunker(self, mock_gemini_client):
        return LLMSemanticChunker(
            gemini_client=mock_gemini_client,
            config=ChunkingConfig()
        )

    @pytest.mark.asyncio
    async def test_chunk_short_section(self, chunker):
        """짧은 섹션 청킹."""
        text = "This is a short abstract. " * 20  # ~100 words

        chunks = await chunker.chunk_section(
            text, "abstract", "doc1"
        )

        # 짧은 텍스트는 1개 청크
        assert len(chunks) == 1
        assert chunks[0].section_type == "abstract"
        assert chunks[0].tier == 1

    @pytest.mark.asyncio
    async def test_chunk_methods_section(self, chunker):
        """Methods 섹션 청킹."""
        text = """
        Study Design
        We conducted a prospective randomized controlled trial...

        Participants
        Inclusion criteria were: age over 18...

        Statistical Analysis
        Data were analyzed using SPSS version 25...
        """

        chunks = await chunker.chunk_section(
            text, "methods", "doc1"
        )

        # 하위 섹션별로 분할
        assert len(chunks) >= 2
        assert all(c.section_type == "methods" for c in chunks)

    @pytest.mark.asyncio
    async def test_chunk_results_with_findings(self, chunker):
        """연구 결과 포함 청크 식별."""
        text = """
        Primary Outcome
        The intervention group showed significantly better outcomes
        (85% vs 65%, p<0.001). The effect size was large (d=0.8).

        Secondary Outcomes
        No significant differences were found in secondary measures.
        """

        chunks = await chunker.chunk_section(
            text, "results", "doc1"
        )

        # 결과 포함 청크 식별
        finding_chunks = [c for c in chunks if c.contains_finding]
        assert len(finding_chunks) >= 1

    @pytest.mark.asyncio
    async def test_chunk_preserves_complete_thought(self, chunker):
        """완전한 생각 유지."""
        text = """
        The results of this study demonstrate that early intervention
        leads to better long-term outcomes. This finding is consistent
        with previous research by Smith et al. (2020), who reported
        similar results in a different patient population. However,
        our study extends these findings by including older patients.
        """

        chunks = await chunker.chunk_section(
            text, "discussion", "doc1"
        )

        # 관련 내용이 함께 유지됨
        for chunk in chunks:
            assert chunk.is_complete_thought

    @pytest.mark.asyncio
    async def test_chunk_document_multiple_sections(self, chunker):
        """전체 문서 청킹."""
        sections = [
            SectionBoundary("abstract", 0, 500, 0.9, 1),
            SectionBoundary("methods", 500, 2000, 0.9, 2),
            SectionBoundary("results", 2000, 4000, 0.9, 1),
        ]
        full_text = "A" * 500 + "M" * 1500 + "R" * 2000

        chunks = await chunker.chunk_document(
            sections, full_text, "doc1"
        )

        # 모든 섹션에서 청크 생성
        section_types = set(c.section_type for c in chunks)
        assert "abstract" in section_types
        assert "methods" in section_types
        assert "results" in section_types

    @pytest.mark.asyncio
    async def test_topic_summary_generation(self, chunker):
        """주제 요약 생성."""
        text = "Detailed content about surgical techniques..."

        chunks = await chunker.chunk_section(
            text, "methods", "doc1"
        )

        for chunk in chunks:
            assert chunk.topic_summary
            assert len(chunk.topic_summary) < 200

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, chunker, mock_gemini_client):
        """LLM 실패 시 Fallback."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")
        chunker.fallback_chunker = TieredTextChunker()

        text = "Some content to chunk..."
        chunks = await chunker.chunk_section(text, "methods", "doc1")

        assert len(chunks) >= 1
```

### Edge Cases

```python
@pytest.mark.asyncio
async def test_empty_section(self, chunker):
    """빈 섹션 처리."""
    chunks = await chunker.chunk_section("", "methods", "doc1")
    assert len(chunks) == 0

@pytest.mark.asyncio
async def test_very_long_section(self, chunker):
    """매우 긴 섹션 처리."""
    text = "Word " * 10000  # ~10000 단어
    chunks = await chunker.chunk_section(text, "results", "doc1")

    # 적절한 크기로 분할됨
    for chunk in chunks:
        assert chunk.word_count <= 800

@pytest.mark.asyncio
async def test_special_characters(self, chunker):
    """특수 문자 포함 텍스트."""
    text = "Results: p<0.001, CI [0.5-0.8], β=0.3 ± 0.1"
    chunks = await chunker.chunk_section(text, "results", "doc1")

    assert chunks[0].content == text
```

---

## Dependencies

- `src/llm/gemini_client.py` - GeminiClient
- `src/builder/llm_section_classifier.py` - SectionBoundary
- `src/core/text_chunker.py` - 규칙 기반 Fallback (기존 모듈)

---

## Configuration

```yaml
# config.yaml
llm_semantic_chunker:
  target_min_words: 300
  target_max_words: 500
  hard_max_words: 800
  overlap_sentences: 1
  preserve_paragraphs: true
  use_fallback: true

  # 섹션별 청킹 전략
  section_strategies:
    abstract:
      max_chunks: 2  # 초록은 최대 2개 청크
    results:
      preserve_statistics: true  # 통계는 함께 유지
    methods:
      preserve_subsections: true  # 하위 섹션 경계 유지
```

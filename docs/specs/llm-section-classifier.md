# LLM Section Classifier Specification

## Overview

Gemini LLM을 사용하여 의학 논문의 섹션 경계를 식별하고 분류합니다.

### 목적
- 논문 텍스트에서 섹션(Abstract, Introduction, Methods, Results, Discussion, Conclusion) 식별
- 각 섹션의 시작/끝 위치 추출
- Tier 할당 (Tier 1: 핵심, Tier 2: 상세)
- 실패 시 규칙 기반 분류기로 Fallback

### 입출력 요약
- **입력**: 전체 논문 텍스트 (문자열)
- **출력**: 섹션 경계 목록 (타입, 시작/끝 위치, 신뢰도, Tier)

---

## Data Structures

### SectionBoundary

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class SectionBoundary:
    """섹션 경계 정보."""
    section_type: str      # abstract, introduction, methods, results, discussion, conclusion, references, other
    start_char: int        # 시작 문자 위치
    end_char: int          # 끝 문자 위치
    confidence: float      # 신뢰도 (0.0 ~ 1.0)
    tier: int              # 1=핵심, 2=상세
    heading: Optional[str] = None  # 감지된 섹션 헤딩 (있는 경우)
```

### Tier 매핑

```python
SECTION_TIERS = {
    "abstract": 1,      # Tier 1: 핵심
    "results": 1,       # Tier 1: 핵심
    "conclusion": 1,    # Tier 1: 핵심
    "introduction": 2,  # Tier 2: 상세
    "methods": 2,       # Tier 2: 상세
    "discussion": 2,    # Tier 2: 상세
    "references": 2,    # Tier 2: 상세
    "other": 2          # Tier 2: 상세
}
```

---

## Interface

### LLMSectionClassifier

```python
class LLMSectionClassifier:
    """LLM 기반 섹션 분류기."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        fallback_classifier: SectionClassifier = None,
        config: dict = None
    ):
        """초기화.

        Args:
            gemini_client: Gemini API 클라이언트
            fallback_classifier: 규칙 기반 Fallback 분류기
            config: 추가 설정
                - min_confidence: 최소 신뢰도 (기본: 0.7)
                - max_text_length: 최대 텍스트 길이 (기본: 100000)
        """

    async def classify(
        self,
        full_text: str,
        use_fallback: bool = True
    ) -> list[SectionBoundary]:
        """전체 논문 텍스트에서 섹션 경계 식별.

        Args:
            full_text: 전체 논문 텍스트
            use_fallback: 실패 시 Fallback 사용 여부

        Returns:
            섹션 경계 목록 (시작 위치 기준 정렬)

        Raises:
            ClassificationError: 분류 실패 (Fallback도 실패한 경우)
        """

    async def classify_with_context(
        self,
        full_text: str,
        paper_metadata: dict = None
    ) -> list[SectionBoundary]:
        """메타데이터 컨텍스트를 활용한 분류.

        Args:
            full_text: 전체 논문 텍스트
            paper_metadata: 논문 메타데이터 (title, journal, year 등)

        Returns:
            섹션 경계 목록
        """

    def validate_sections(
        self,
        sections: list[SectionBoundary],
        text_length: int
    ) -> list[SectionBoundary]:
        """섹션 경계 검증 및 보정.

        - 겹치는 섹션 해결
        - 빠진 텍스트 영역 할당
        - 비정상적으로 짧은 섹션 병합

        Returns:
            검증/보정된 섹션 목록
        """
```

---

## LLM Prompt Template

### System Prompt

```python
SECTION_CLASSIFY_SYSTEM = """You are a medical research paper analyzer specializing in identifying document structure.

Your task is to identify section boundaries in medical/scientific papers with high precision.

Section types to identify:
- abstract: Paper summary, background, objectives
- introduction: Background, literature review, study rationale
- methods: Study design, participants, procedures, statistical analysis
- results: Findings, data, tables, figures descriptions
- discussion: Interpretation, limitations, implications
- conclusion: Summary of findings, recommendations
- references: Bibliography, citations list
- other: Acknowledgments, funding, conflicts of interest

Rules:
1. Identify ALL sections present in the paper
2. Provide exact character positions for start and end
3. Sections should not overlap
4. Every character should belong to exactly one section
5. Consider common variations (e.g., "Materials and Methods", "Background", "Summary")
6. If a section heading is ambiguous, use surrounding content to determine type
"""
```

### User Prompt Template

```python
SECTION_CLASSIFY_USER = """Analyze this medical paper and identify all section boundaries.

Paper text:
---
{text}
---

Total characters: {text_length}

For each section found, provide:
1. section_type: One of [abstract, introduction, methods, results, discussion, conclusion, references, other]
2. start_char: Starting character position (0-indexed)
3. end_char: Ending character position (exclusive)
4. confidence: Your confidence in this classification (0.0 to 1.0)
5. heading: The actual section heading text if found (null if none)

Return the results as a JSON array sorted by start position.
"""
```

### Output JSON Schema

```python
SECTION_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section_type": {
                        "type": "string",
                        "enum": ["abstract", "introduction", "methods", "results", "discussion", "conclusion", "references", "other"]
                    },
                    "start_char": {"type": "integer", "minimum": 0},
                    "end_char": {"type": "integer", "minimum": 0},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "heading": {"type": ["string", "null"]}
                },
                "required": ["section_type", "start_char", "end_char", "confidence"]
            }
        },
        "total_sections": {"type": "integer"},
        "analysis_notes": {"type": "string"}
    },
    "required": ["sections", "total_sections"]
}
```

---

## Implementation Notes

### 텍스트 전처리

```python
def _preprocess_text(self, text: str) -> tuple[str, dict]:
    """텍스트 전처리.

    Returns:
        (처리된 텍스트, 위치 매핑 정보)
    """
    # 1. 연속 공백 정규화
    # 2. 특수 문자 처리
    # 3. 위치 매핑 정보 유지 (원본 위치 복원용)
    pass
```

### 긴 텍스트 처리

```python
MAX_CHUNK_SIZE = 50000  # 토큰 제한 고려

async def _classify_long_text(self, text: str) -> list[SectionBoundary]:
    """긴 텍스트 분할 처리.

    1. 텍스트를 청크로 분할 (섹션 경계 추정 위치에서)
    2. 각 청크 개별 분류
    3. 결과 병합 및 검증
    """
    if len(text) <= MAX_CHUNK_SIZE:
        return await self._classify_single(text)

    # 대략적인 섹션 경계 추정 (키워드 기반)
    estimated_boundaries = self._estimate_boundaries(text)

    # 청크 분할
    chunks = self._split_at_boundaries(text, estimated_boundaries)

    # 병렬 처리
    chunk_results = await asyncio.gather(*[
        self._classify_single(chunk) for chunk in chunks
    ])

    # 결과 병합
    return self._merge_chunk_results(chunk_results, chunks)
```

### Fallback 전략

```python
async def classify(self, full_text: str, use_fallback: bool = True) -> list[SectionBoundary]:
    try:
        # LLM 분류 시도
        sections = await self._classify_with_llm(full_text)

        # 결과 검증
        if self._is_valid_result(sections, len(full_text)):
            return sections

        raise ClassificationError("Invalid LLM result")

    except Exception as e:
        if use_fallback and self.fallback:
            logger.warning(f"LLM classification failed, using fallback: {e}")
            return self._use_rule_based_fallback(full_text)

        # 최후의 수단: 전체를 단일 섹션으로
        return [SectionBoundary(
            section_type="other",
            start_char=0,
            end_char=len(full_text),
            confidence=0.0,
            tier=2
        )]
```

### 결과 검증

```python
def _is_valid_result(
    self,
    sections: list[SectionBoundary],
    text_length: int
) -> bool:
    """결과 유효성 검증."""
    if not sections:
        return False

    # 1. 전체 텍스트 커버리지 확인
    covered = sum(s.end_char - s.start_char for s in sections)
    if covered < text_length * 0.8:  # 최소 80% 커버리지
        return False

    # 2. 섹션 겹침 확인
    sorted_sections = sorted(sections, key=lambda s: s.start_char)
    for i in range(len(sorted_sections) - 1):
        if sorted_sections[i].end_char > sorted_sections[i+1].start_char:
            return False

    # 3. 최소 신뢰도 확인
    avg_confidence = sum(s.confidence for s in sections) / len(sections)
    if avg_confidence < 0.5:
        return False

    return True
```

---

## Test Cases

### 단위 테스트

```python
import pytest
from unittest.mock import AsyncMock

class TestLLMSectionClassifier:
    @pytest.fixture
    def classifier(self, mock_gemini_client):
        return LLMSectionClassifier(
            gemini_client=mock_gemini_client,
            fallback_classifier=SectionClassifier()
        )

    @pytest.mark.asyncio
    async def test_classify_standard_paper(self, classifier):
        """표준 구조 논문 분류."""
        text = """
        Abstract
        This study investigates...

        Introduction
        Background information...

        Methods
        We conducted a randomized...

        Results
        The primary outcome showed...

        Discussion
        Our findings suggest...

        Conclusion
        In summary...

        References
        1. Smith et al...
        """

        sections = await classifier.classify(text)

        assert len(sections) == 7
        assert sections[0].section_type == "abstract"
        assert sections[0].tier == 1
        assert sections[3].section_type == "results"
        assert sections[3].tier == 1

    @pytest.mark.asyncio
    async def test_classify_no_explicit_headings(self, classifier):
        """명시적 헤딩 없는 논문."""
        text = """
        Background: This study aims to evaluate...
        We enrolled 100 patients...
        The success rate was 85%...
        These results indicate...
        """
        sections = await classifier.classify(text)
        assert len(sections) >= 1

    @pytest.mark.asyncio
    async def test_classify_with_variations(self, classifier):
        """섹션 헤딩 변형 처리."""
        text = """
        SUMMARY
        This paper presents...

        BACKGROUND
        Previous studies...

        MATERIALS AND METHODS
        Study design...

        FINDINGS
        We found that...
        """
        sections = await classifier.classify(text)

        # "SUMMARY" → abstract
        assert sections[0].section_type == "abstract"
        # "MATERIALS AND METHODS" → methods
        methods_section = next(s for s in sections if s.section_type == "methods")
        assert methods_section is not None

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, classifier, mock_gemini_client):
        """LLM 실패 시 Fallback."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        text = "Abstract\nContent...\nMethods\nMore content..."
        sections = await classifier.classify(text, use_fallback=True)

        # Fallback 결과 확인
        assert len(sections) >= 1

    @pytest.mark.asyncio
    async def test_validate_sections_overlap(self, classifier):
        """겹치는 섹션 보정."""
        sections = [
            SectionBoundary("abstract", 0, 150, 0.9, 1),
            SectionBoundary("methods", 100, 300, 0.8, 2),  # 겹침
        ]
        validated = classifier.validate_sections(sections, 300)

        # 겹침 해결됨
        assert validated[0].end_char <= validated[1].start_char

    @pytest.mark.asyncio
    async def test_tier_assignment(self, classifier):
        """Tier 올바르게 할당."""
        text = "Abstract...\nResults...\nDiscussion..."
        sections = await classifier.classify(text)

        for s in sections:
            expected_tier = SECTION_TIERS.get(s.section_type, 2)
            assert s.tier == expected_tier
```

### Edge Cases

```python
@pytest.mark.asyncio
async def test_empty_text(self, classifier):
    """빈 텍스트 처리."""
    sections = await classifier.classify("")
    assert len(sections) == 0 or sections[0].section_type == "other"

@pytest.mark.asyncio
async def test_very_long_text(self, classifier):
    """매우 긴 텍스트 처리."""
    text = "Content " * 100000  # 약 800KB
    sections = await classifier.classify(text)
    assert len(sections) >= 1

@pytest.mark.asyncio
async def test_non_english_paper(self, classifier):
    """비영어 논문 처리."""
    text = """
    초록
    본 연구는...

    서론
    배경 정보...

    방법
    연구 설계...
    """
    sections = await classifier.classify(text)
    # 한국어도 처리 가능해야 함
    assert len(sections) >= 1
```

---

## Dependencies

- `src/llm/gemini_client.py` - GeminiClient
- `src/llm/cache.py` - LLMCache
- `src/builder/section_classifier.py` - 규칙 기반 Fallback (기존 모듈)

---

## Configuration

```yaml
# config.yaml
llm_section_classifier:
  min_confidence: 0.7
  max_text_length: 100000
  use_fallback: true
  cache_ttl_hours: 168

  # Tier 매핑
  tier1_sections:
    - abstract
    - results
    - conclusion
  tier2_sections:
    - introduction
    - methods
    - discussion
    - references
    - other
```

# LLM Metadata Extractor Specification

## Overview

Gemini LLM을 사용하여 청크에서 요약, PICO, 통계 등 메타데이터를 추출합니다.

### 목적
- 각 청크의 1-2문장 요약 생성
- PICO 요소 추출 (Patient, Intervention, Comparison, Outcome)
- 통계 정보 추출 (p-values, effect sizes, confidence intervals)
- 검색 키워드 추출
- 원본/인용 구분

### 입출력 요약
- **입력**: 청크 텍스트 + 문서 컨텍스트(초록)
- **출력**: 메타데이터 객체 (요약, PICO, 통계, 키워드)

---

## Data Structures

### PICOElements

```python
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class PICOElements:
    """PICO 요소."""
    population: Optional[str] = None       # 연구 대상 (환자 특성)
    intervention: Optional[str] = None     # 중재/치료
    comparison: Optional[str] = None       # 비교군
    outcome: Optional[str] = None          # 결과 지표

    def is_complete(self) -> bool:
        """모든 PICO 요소가 있는지 확인."""
        return all([self.population, self.intervention, self.outcome])

    def to_dict(self) -> dict:
        return {
            "P": self.population,
            "I": self.intervention,
            "C": self.comparison,
            "O": self.outcome
        }
```

### StatsInfo

```python
@dataclass
class EffectSize:
    """효과 크기."""
    type: str              # "Cohen's d", "OR", "RR", "HR", "MD"
    value: float
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None

@dataclass
class StatsInfo:
    """통계 정보."""
    p_values: List[str] = None            # ["p<0.001", "p=0.045"]
    effect_sizes: List[EffectSize] = None
    confidence_intervals: List[str] = None  # ["95% CI: 0.5-0.8"]
    sample_sizes: List[int] = None          # [n=100, n=150]
    statistical_tests: List[str] = None     # ["t-test", "chi-square"]

    def __post_init__(self):
        self.p_values = self.p_values or []
        self.effect_sizes = self.effect_sizes or []
        self.confidence_intervals = self.confidence_intervals or []
        self.sample_sizes = self.sample_sizes or []
        self.statistical_tests = self.statistical_tests or []

    def has_significant_result(self) -> bool:
        """유의한 결과가 있는지 확인."""
        for p in self.p_values:
            if "<0.05" in p or "<0.01" in p or "<0.001" in p:
                return True
        return False
```

### ChunkMetadata

```python
@dataclass
class ChunkMetadata:
    """청크 메타데이터."""
    summary: str                           # 1-2문장 요약
    keywords: List[str]                    # 검색 키워드 (5-10개)
    pico: Optional[PICOElements] = None    # PICO 요소
    statistics: Optional[StatsInfo] = None # 통계 정보
    content_type: str = "original"         # original, citation, background
    is_key_finding: bool = False           # 핵심 발견인지
    confidence: float = 0.0                # 추출 신뢰도

    # 추가 메타데이터
    medical_terms: List[str] = None        # 추출된 의학 용어
    study_design_mentioned: Optional[str] = None  # 언급된 연구 설계
```

---

## Interface

### LLMMetadataExtractor

```python
class LLMMetadataExtractor:
    """LLM 기반 메타데이터 추출기."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        config: dict = None
    ):
        """초기화.

        Args:
            gemini_client: Gemini API 클라이언트
            config: 추가 설정
                - extract_pico: PICO 추출 여부 (기본: True)
                - extract_stats: 통계 추출 여부 (기본: True)
                - max_keywords: 최대 키워드 수 (기본: 10)
        """

    async def extract(
        self,
        chunk: str,
        context: str,
        section_type: str = None
    ) -> ChunkMetadata:
        """단일 청크에서 메타데이터 추출.

        Args:
            chunk: 청크 텍스트
            context: 문서 컨텍스트 (초록)
            section_type: 섹션 타입 (힌트용)

        Returns:
            ChunkMetadata 객체
        """

    async def extract_batch(
        self,
        chunks: List[str],
        context: str,
        section_types: List[str] = None,
        concurrency: int = 10
    ) -> List[ChunkMetadata]:
        """배치 메타데이터 추출 (병렬 처리).

        Args:
            chunks: 청크 텍스트 목록
            context: 문서 컨텍스트 (공통)
            section_types: 각 청크의 섹션 타입
            concurrency: 동시 처리 수

        Returns:
            ChunkMetadata 목록 (입력 순서 유지)
        """

    async def extract_document_level(
        self,
        full_text: str,
        abstract: str
    ) -> dict:
        """문서 수준 메타데이터 추출.

        Returns:
            {
                "title_summary": str,
                "main_pico": PICOElements,
                "key_findings": List[str],
                "study_design": str,
                "evidence_level": str
            }
        """
```

---

## LLM Prompt Template

### System Prompt

```python
METADATA_EXTRACT_SYSTEM = """You are a medical research metadata extraction expert.

Your task is to extract structured metadata from medical paper chunks.

Extraction targets:
1. Summary: 1-2 sentence summary of the chunk's main content
2. Keywords: 5-10 searchable medical/scientific terms
3. PICO elements (if applicable):
   - P (Population): Patient characteristics, condition, age, etc.
   - I (Intervention): Treatment, procedure, exposure
   - C (Comparison): Control group, alternative treatment
   - O (Outcome): Results, endpoints, measures
4. Statistics (if present):
   - p-values: Significance levels
   - Effect sizes: Cohen's d, OR, RR, HR, etc.
   - Confidence intervals
   - Sample sizes
5. Content type: original research, citation of other work, or background

Guidelines:
- Be precise and extract only what is explicitly stated
- Use standardized medical terminology
- For statistics, preserve exact values as written
- Mark as "key_finding" if chunk contains primary research results
"""
```

### User Prompt Template

```python
METADATA_EXTRACT_USER = """Extract metadata from this medical paper chunk.

Document context (abstract):
---
{context}
---

Chunk to analyze ({section_type} section):
---
{chunk}
---

Extract:
1. summary: 1-2 sentence summary
2. keywords: 5-10 relevant search terms
3. pico: PICO elements if present (population, intervention, comparison, outcome)
4. statistics: Any statistical information (p_values, effect_sizes, confidence_intervals, sample_sizes)
5. content_type: "original" (this paper's findings), "citation" (referencing other studies), or "background"
6. is_key_finding: true if this contains a primary research result
7. medical_terms: Important medical/anatomical terms mentioned
"""
```

### Output JSON Schema

```python
METADATA_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "maxLength": 500
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 10
        },
        "pico": {
            "type": ["object", "null"],
            "properties": {
                "population": {"type": ["string", "null"]},
                "intervention": {"type": ["string", "null"]},
                "comparison": {"type": ["string", "null"]},
                "outcome": {"type": ["string", "null"]}
            }
        },
        "statistics": {
            "type": ["object", "null"],
            "properties": {
                "p_values": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "effect_sizes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "value": {"type": "number"},
                            "ci_lower": {"type": ["number", "null"]},
                            "ci_upper": {"type": ["number", "null"]}
                        }
                    }
                },
                "confidence_intervals": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "sample_sizes": {
                    "type": "array",
                    "items": {"type": "integer"}
                },
                "statistical_tests": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        },
        "content_type": {
            "type": "string",
            "enum": ["original", "citation", "background"]
        },
        "is_key_finding": {"type": "boolean"},
        "medical_terms": {
            "type": "array",
            "items": {"type": "string"}
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
        }
    },
    "required": ["summary", "keywords", "content_type", "is_key_finding"]
}
```

---

## Implementation Notes

### 배치 처리 최적화

```python
async def extract_batch(
    self,
    chunks: List[str],
    context: str,
    section_types: List[str] = None,
    concurrency: int = 10
) -> List[ChunkMetadata]:
    """배치 추출 (병렬 처리)."""
    import asyncio

    semaphore = asyncio.Semaphore(concurrency)

    async def extract_with_semaphore(chunk, section_type):
        async with semaphore:
            return await self.extract(chunk, context, section_type)

    section_types = section_types or [None] * len(chunks)

    tasks = [
        extract_with_semaphore(chunk, section_type)
        for chunk, section_type in zip(chunks, section_types)
    ]

    return await asyncio.gather(*tasks)
```

### 통계 파싱 보조

```python
def _parse_statistics(self, raw_stats: dict) -> StatsInfo:
    """통계 정보 파싱 및 정규화."""
    effect_sizes = []
    for es in raw_stats.get("effect_sizes", []):
        effect_sizes.append(EffectSize(
            type=es.get("type", "unknown"),
            value=es.get("value", 0),
            ci_lower=es.get("ci_lower"),
            ci_upper=es.get("ci_upper")
        ))

    return StatsInfo(
        p_values=raw_stats.get("p_values", []),
        effect_sizes=effect_sizes,
        confidence_intervals=raw_stats.get("confidence_intervals", []),
        sample_sizes=raw_stats.get("sample_sizes", []),
        statistical_tests=raw_stats.get("statistical_tests", [])
    )
```

### Fallback 전략

```python
async def extract(self, chunk: str, context: str, section_type: str = None) -> ChunkMetadata:
    try:
        # LLM 추출 시도
        return await self._extract_with_llm(chunk, context, section_type)

    except Exception as e:
        logger.warning(f"LLM extraction failed: {e}")

        # 규칙 기반 Fallback
        return self._extract_rule_based(chunk, section_type)

def _extract_rule_based(self, chunk: str, section_type: str) -> ChunkMetadata:
    """규칙 기반 메타데이터 추출."""
    # 기본 요약: 첫 문장
    sentences = chunk.split('.')
    summary = sentences[0] + '.' if sentences else chunk[:200]

    # 키워드: 대문자로 시작하는 명사구 추출
    keywords = self._extract_noun_phrases(chunk)[:10]

    # 통계: 정규식으로 추출
    stats = self._extract_stats_regex(chunk)

    # PICO: 규칙 기반 추출
    pico = self._extract_pico_regex(chunk)

    return ChunkMetadata(
        summary=summary,
        keywords=keywords,
        pico=pico,
        statistics=stats,
        content_type=self._detect_content_type(chunk),
        is_key_finding=section_type == "results",
        confidence=0.3  # 낮은 신뢰도 표시
    )
```

### 원본/인용 구분

```python
def _detect_content_type(self, chunk: str) -> str:
    """원본 vs 인용 vs 배경 구분."""
    # 인용 패턴
    citation_patterns = [
        r'\([A-Z][a-z]+ et al\.?,? \d{4}\)',
        r'\[[\d,\s]+\]',
        r'according to .+? \(\d{4}\)',
        r'previous studies? (?:have |has )?(?:shown|demonstrated|reported)',
        r'prior research',
        r'it has been (?:shown|reported|demonstrated)'
    ]

    citation_count = sum(
        len(re.findall(pattern, chunk, re.IGNORECASE))
        for pattern in citation_patterns
    )

    # 원본 패턴
    original_patterns = [
        r'\bwe found\b',
        r'\bour (?:study|results|findings)\b',
        r'\bthis study\b',
        r'\bin our (?:cohort|sample|population)\b',
        r'\bour (?:data|analysis)\b'
    ]

    original_count = sum(
        len(re.findall(pattern, chunk, re.IGNORECASE))
        for pattern in original_patterns
    )

    if original_count > citation_count:
        return "original"
    elif citation_count > 2:
        return "citation"
    else:
        return "background"
```

---

## Test Cases

### 단위 테스트

```python
import pytest

class TestLLMMetadataExtractor:
    @pytest.fixture
    def extractor(self, mock_gemini_client):
        return LLMMetadataExtractor(gemini_client=mock_gemini_client)

    @pytest.mark.asyncio
    async def test_extract_summary(self, extractor):
        """요약 추출."""
        chunk = "We found that early surgical intervention significantly improved outcomes in patients with lumbar disc herniation."
        context = "This study evaluates timing of surgery for disc herniation."

        result = await extractor.extract(chunk, context, "results")

        assert result.summary
        assert len(result.summary) < 500

    @pytest.mark.asyncio
    async def test_extract_pico(self, extractor):
        """PICO 추출."""
        chunk = """
        Patients with lumbar disc herniation (n=200) were randomized to
        early surgery (within 2 weeks) or conservative treatment.
        The primary outcome was pain reduction at 6 months.
        """
        context = "RCT comparing early surgery vs conservative treatment."

        result = await extractor.extract(chunk, context, "methods")

        assert result.pico is not None
        assert result.pico.population  # "lumbar disc herniation patients"
        assert result.pico.intervention  # "early surgery"
        assert result.pico.comparison  # "conservative treatment"
        assert result.pico.outcome  # "pain reduction"

    @pytest.mark.asyncio
    async def test_extract_statistics(self, extractor):
        """통계 정보 추출."""
        chunk = """
        The intervention group showed significantly better outcomes
        (85% vs 65%, p<0.001). The effect size was large (Cohen's d=0.8,
        95% CI: 0.5-1.1). Sample sizes were 100 per group.
        """
        context = "Study results."

        result = await extractor.extract(chunk, context, "results")

        assert result.statistics is not None
        assert "p<0.001" in result.statistics.p_values
        assert len(result.statistics.effect_sizes) > 0
        assert result.statistics.effect_sizes[0].type == "Cohen's d"
        assert result.statistics.effect_sizes[0].value == 0.8

    @pytest.mark.asyncio
    async def test_detect_original_content(self, extractor):
        """원본 콘텐츠 감지."""
        chunk = "In our study, we found that patients who received early treatment showed 40% improvement."
        result = await extractor.extract(chunk, "", "results")

        assert result.content_type == "original"

    @pytest.mark.asyncio
    async def test_detect_citation_content(self, extractor):
        """인용 콘텐츠 감지."""
        chunk = "Previous studies (Smith et al., 2020; Kim et al., 2019) have shown that early intervention improves outcomes."
        result = await extractor.extract(chunk, "", "introduction")

        assert result.content_type == "citation"

    @pytest.mark.asyncio
    async def test_extract_keywords(self, extractor):
        """키워드 추출."""
        chunk = "Endoscopic spine surgery using minimally invasive techniques showed promising results for lumbar stenosis."
        result = await extractor.extract(chunk, "", "results")

        assert len(result.keywords) >= 3
        # 관련 키워드 포함 확인
        keywords_lower = [k.lower() for k in result.keywords]
        assert any("endoscopic" in k or "spine" in k for k in keywords_lower)

    @pytest.mark.asyncio
    async def test_batch_extraction(self, extractor):
        """배치 추출."""
        chunks = [
            "First chunk about methods...",
            "Second chunk about results...",
            "Third chunk about discussion..."
        ]
        context = "Abstract context"
        section_types = ["methods", "results", "discussion"]

        results = await extractor.extract_batch(chunks, context, section_types)

        assert len(results) == 3
        assert all(isinstance(r, ChunkMetadata) for r in results)

    @pytest.mark.asyncio
    async def test_key_finding_detection(self, extractor):
        """핵심 발견 감지."""
        chunk = "Our primary analysis revealed a statistically significant difference (p<0.01) between groups."
        result = await extractor.extract(chunk, "", "results")

        assert result.is_key_finding is True

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, extractor, mock_gemini_client):
        """LLM 실패 시 Fallback."""
        mock_gemini_client.generate_json.side_effect = Exception("API Error")

        chunk = "Some medical content to extract..."
        result = await extractor.extract(chunk, "", "methods")

        # Fallback 결과 확인
        assert result.summary
        assert result.confidence < 0.5  # 낮은 신뢰도
```

### Edge Cases

```python
@pytest.mark.asyncio
async def test_empty_chunk(self, extractor):
    """빈 청크 처리."""
    result = await extractor.extract("", "", "methods")
    assert result.summary == "" or result.summary == "[No content]"

@pytest.mark.asyncio
async def test_no_statistics_in_methods(self, extractor):
    """Methods 섹션에 통계 없음."""
    chunk = "We conducted a retrospective review of patient records."
    result = await extractor.extract(chunk, "", "methods")

    # 통계가 없어도 정상 처리
    assert result.statistics is None or len(result.statistics.p_values) == 0

@pytest.mark.asyncio
async def test_partial_pico(self, extractor):
    """부분적 PICO."""
    chunk = "Patients with chronic pain were included."
    result = await extractor.extract(chunk, "", "methods")

    # Population만 있어도 정상
    if result.pico:
        assert result.pico.population is not None
```

---

## Dependencies

- `src/llm/gemini_client.py` - GeminiClient
- `src/builder/pico_extractor.py` - 규칙 기반 Fallback (기존 모듈)
- `src/builder/stats_parser.py` - 규칙 기반 Fallback (기존 모듈)

---

## Configuration

```yaml
# config.yaml
llm_metadata_extractor:
  extract_pico: true
  extract_stats: true
  max_keywords: 10
  min_keyword_length: 3

  # 섹션별 추출 전략
  section_strategies:
    abstract:
      extract_pico: true
      is_key_finding: true  # 초록은 항상 핵심
    methods:
      extract_pico: true
      extract_stats: false  # Methods에서는 통계 추출 안함
    results:
      extract_stats: true
      is_key_finding: true
    discussion:
      content_type_hint: "original"  # 대부분 원본 해석

  # 배치 처리
  batch:
    concurrency: 10
    retry_failed: true
```

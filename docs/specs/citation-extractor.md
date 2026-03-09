# Citation Extractor Specification

## Overview

Gemini LLM을 사용하여 논문에서 인용 정보를 추출하고 기존 논문과 매칭합니다.

### 목적
- PDF 텍스트에서 인용 정보 추출
- 인용 맥락 파악 (지지/반박/중립)
- 추출된 인용을 기존 논문 DB와 매칭
- LLM으로 매칭 결과 검증 (정확도 우선)

### 입출력 요약
- **입력**: 전체 논문 텍스트
- **출력**: 인용 정보 목록 + 기존 논문 매칭 결과

---

## Data Structures

### CitationInfo

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class CitationInfo:
    """추출된 인용 정보."""
    cited_title: Optional[str] = None      # 인용된 논문 제목
    cited_authors: List[str] = None        # 인용된 논문 저자
    cited_year: Optional[int] = None       # 인용된 논문 연도
    citation_context: str = ""             # 인용된 맥락 문장
    citation_type: str = "neutral"         # supporting, contrasting, neutral
    citation_marker: str = ""              # 원본 인용 마커 (e.g., "[1]", "(Smith, 2020)")

    # 위치 정보
    char_position: int = 0                 # 텍스트 내 위치

    def __post_init__(self):
        self.cited_authors = self.cited_authors or []
```

### CitationMatch

```python
@dataclass
class CitationMatch:
    """인용-논문 매칭 결과."""
    citation: CitationInfo
    matched_paper_id: Optional[str] = None  # 매칭된 논문 ID (없으면 None)
    match_confidence: float = 0.0           # 매칭 신뢰도
    match_method: str = ""                  # 매칭 방법 (title, author_year, llm_verify)
    llm_verified: bool = False              # LLM 검증 완료 여부
```

---

## Interface

### LLMCitationExtractor

```python
class LLMCitationExtractor:
    """LLM 기반 인용 추출기."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        config: dict = None
    ):
        """초기화.

        Args:
            gemini_client: Gemini API 클라이언트
            config: 설정
                - extract_context_sentences: 맥락 문장 수 (기본: 2)
                - llm_verify_matches: LLM 매칭 검증 여부 (기본: True)
        """

    async def extract_citations(
        self,
        full_text: str,
        include_references: bool = True
    ) -> List[CitationInfo]:
        """논문에서 인용 정보 추출.

        Args:
            full_text: 전체 논문 텍스트
            include_references: References 섹션 파싱 여부

        Returns:
            CitationInfo 목록
        """

    async def match_to_existing_papers(
        self,
        citations: List[CitationInfo],
        paper_graph: PaperGraph,
        llm_verify: bool = True
    ) -> List[CitationMatch]:
        """추출된 인용을 기존 논문과 매칭.

        Args:
            citations: 추출된 인용 목록
            paper_graph: 논문 그래프 DB
            llm_verify: LLM 검증 수행 여부 (정확도 우선 설정시 True)

        Returns:
            CitationMatch 목록
        """

    async def extract_and_match(
        self,
        full_text: str,
        paper_graph: PaperGraph
    ) -> List[CitationMatch]:
        """추출 + 매칭 통합 수행.

        Returns:
            CitationMatch 목록 (매칭된 것과 미매칭 모두 포함)
        """
```

---

## LLM Prompt Template

### 인용 추출 - System Prompt

```python
CITATION_EXTRACT_SYSTEM = """You are a citation extraction expert for medical research papers.

Your task is to identify and extract all citations in the paper text.

For each citation, extract:
1. The citation marker as it appears (e.g., "[1]", "(Smith et al., 2020)")
2. The cited paper's title (if mentioned nearby or in references)
3. The authors' names
4. The publication year
5. The context sentence where the citation appears
6. The citation type:
   - "supporting": The cited work supports or agrees with a claim
   - "contrasting": The cited work presents different or opposing findings
   - "neutral": General reference without clear support/contrast

Guidelines:
- Extract ALL citations, even if some information is missing
- Include both in-text citations and references section entries
- For numbered citations [1], [2], try to match with references section
- Preserve exact context sentences including the citation marker
"""
```

### 인용 추출 - User Prompt

```python
CITATION_EXTRACT_USER = """Extract all citations from this medical paper.

Paper text:
---
{text}
---

For each citation found, provide:
1. citation_marker: The exact citation marker (e.g., "[1]", "(Kim, 2020)")
2. cited_title: Paper title if available
3. cited_authors: List of author names
4. cited_year: Publication year
5. citation_context: The sentence containing the citation
6. citation_type: "supporting", "contrasting", or "neutral"
7. char_position: Approximate character position in text

Extract citations from:
- In-text citations throughout the paper
- References/Bibliography section
"""
```

### 매칭 검증 - System Prompt

```python
CITATION_VERIFY_SYSTEM = """You are a citation matching verification expert.

Your task is to verify if a citation refers to a specific paper in the database.

Consider:
1. Title similarity (exact or close match)
2. Author names (at least one matching)
3. Publication year (exact or ±1 year)
4. Topic/content relevance

Be conservative - only confirm matches you are confident about.
"""
```

### 매칭 검증 - User Prompt

```python
CITATION_VERIFY_USER = """Verify if this citation matches the candidate paper.

Citation information:
- Marker: {marker}
- Context: {context}
- Extracted title: {cited_title}
- Extracted authors: {cited_authors}
- Extracted year: {cited_year}

Candidate paper from database:
- Paper ID: {paper_id}
- Title: {db_title}
- Authors: {db_authors}
- Year: {db_year}
- Summary: {db_summary}

Determine:
1. is_match: true/false - Does this citation refer to this paper?
2. confidence: 0.0-1.0 - How confident are you?
3. reasoning: Brief explanation of your decision
"""
```

### Output JSON Schemas

```python
CITATION_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "citation_marker": {"type": "string"},
                    "cited_title": {"type": ["string", "null"]},
                    "cited_authors": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "cited_year": {"type": ["integer", "null"]},
                    "citation_context": {"type": "string"},
                    "citation_type": {
                        "type": "string",
                        "enum": ["supporting", "contrasting", "neutral"]
                    },
                    "char_position": {"type": "integer"}
                },
                "required": ["citation_marker", "citation_context", "citation_type"]
            }
        },
        "total_citations": {"type": "integer"}
    },
    "required": ["citations", "total_citations"]
}

CITATION_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "is_match": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string"}
    },
    "required": ["is_match", "confidence", "reasoning"]
}
```

---

## Implementation Notes

### 단계별 매칭 전략

```python
async def match_to_existing_papers(
    self,
    citations: List[CitationInfo],
    paper_graph: PaperGraph,
    llm_verify: bool = True
) -> List[CitationMatch]:
    """3단계 매칭 전략."""
    results = []

    for citation in citations:
        match = await self._find_match(citation, paper_graph)

        # LLM 검증 (정확도 우선)
        if match.matched_paper_id and llm_verify:
            verified = await self._llm_verify_match(citation, match, paper_graph)
            match.llm_verified = True
            if not verified:
                match.matched_paper_id = None
                match.match_confidence = 0.0

        results.append(match)

    return results

async def _find_match(
    self,
    citation: CitationInfo,
    paper_graph: PaperGraph
) -> CitationMatch:
    """후보 찾기."""
    # 1단계: 제목 매칭
    if citation.cited_title:
        match = await self._match_by_title(citation, paper_graph)
        if match.matched_paper_id:
            return match

    # 2단계: 저자 + 연도 매칭
    if citation.cited_authors and citation.cited_year:
        match = await self._match_by_author_year(citation, paper_graph)
        if match.matched_paper_id:
            return match

    # 3단계: 키워드 유사도
    if citation.citation_context:
        match = await self._match_by_context(citation, paper_graph)
        if match.matched_paper_id:
            return match

    return CitationMatch(citation=citation)
```

### 제목 매칭

```python
async def _match_by_title(
    self,
    citation: CitationInfo,
    paper_graph: PaperGraph
) -> CitationMatch:
    """제목 기반 매칭."""
    from difflib import SequenceMatcher

    papers = await paper_graph.list_papers()

    best_match = None
    best_score = 0.0

    for paper in papers:
        # 정규화된 제목 비교
        norm_cited = self._normalize_title(citation.cited_title)
        norm_db = self._normalize_title(paper.title)

        score = SequenceMatcher(None, norm_cited, norm_db).ratio()

        if score > best_score and score > 0.8:  # 80% 이상 유사
            best_score = score
            best_match = paper

    if best_match:
        return CitationMatch(
            citation=citation,
            matched_paper_id=best_match.paper_id,
            match_confidence=best_score,
            match_method="title"
        )

    return CitationMatch(citation=citation)

def _normalize_title(self, title: str) -> str:
    """제목 정규화."""
    import re
    # 소문자 변환
    title = title.lower()
    # 특수문자 제거
    title = re.sub(r'[^\w\s]', '', title)
    # 연속 공백 정리
    title = ' '.join(title.split())
    return title
```

### LLM 매칭 검증

```python
async def _llm_verify_match(
    self,
    citation: CitationInfo,
    match: CitationMatch,
    paper_graph: PaperGraph
) -> bool:
    """LLM으로 매칭 검증 (정확도 우선)."""
    paper = await paper_graph.get_paper(match.matched_paper_id)
    if not paper:
        return False

    prompt = CITATION_VERIFY_USER.format(
        marker=citation.citation_marker,
        context=citation.citation_context,
        cited_title=citation.cited_title or "Unknown",
        cited_authors=", ".join(citation.cited_authors) or "Unknown",
        cited_year=citation.cited_year or "Unknown",
        paper_id=paper.paper_id,
        db_title=paper.title,
        db_authors=", ".join(paper.authors),
        db_year=paper.year,
        db_summary=paper.abstract_summary
    )

    result = await self.gemini.generate_json(
        prompt=prompt,
        schema=CITATION_VERIFY_SCHEMA,
        system=CITATION_VERIFY_SYSTEM
    )

    return result["is_match"] and result["confidence"] > 0.7
```

### References 섹션 파싱

```python
def _extract_references_section(self, text: str) -> List[dict]:
    """References 섹션에서 정형화된 인용 추출."""
    import re

    # References 섹션 찾기
    ref_patterns = [
        r'\n(?:References?|Bibliography|Literature Cited)\s*\n',
        r'\n(?:REFERENCES?|BIBLIOGRAPHY)\s*\n'
    ]

    ref_start = None
    for pattern in ref_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            ref_start = match.end()
            break

    if not ref_start:
        return []

    ref_text = text[ref_start:]

    # 개별 레퍼런스 추출
    # 패턴: 번호로 시작하거나 저자명으로 시작
    ref_entries = re.split(r'\n(?=\d+\.|^\[?\d+\]?|^[A-Z][a-z]+,?\s)', ref_text, flags=re.MULTILINE)

    references = []
    for entry in ref_entries:
        entry = entry.strip()
        if len(entry) > 20:  # 너무 짧은 것 제외
            parsed = self._parse_reference_entry(entry)
            if parsed:
                references.append(parsed)

    return references

def _parse_reference_entry(self, entry: str) -> dict:
    """단일 레퍼런스 엔트리 파싱."""
    import re

    result = {
        "title": None,
        "authors": [],
        "year": None
    }

    # 연도 추출
    year_match = re.search(r'\b(19|20)\d{2}\b', entry)
    if year_match:
        result["year"] = int(year_match.group())

    # 저자 추출 (연도 앞까지)
    if year_match:
        authors_part = entry[:year_match.start()]
        # 간단한 저자 분리
        authors = re.findall(r'[A-Z][a-z]+(?:,?\s+[A-Z]\.?)+', authors_part)
        result["authors"] = authors[:5]  # 최대 5명

    # 제목 추출 (따옴표 또는 마침표 사이)
    title_match = re.search(r'["\'](.+?)["\']|\.(.+?)\.', entry)
    if title_match:
        result["title"] = title_match.group(1) or title_match.group(2)

    return result if result["year"] or result["authors"] else None
```

---

## Test Cases

### 단위 테스트

```python
import pytest

class TestLLMCitationExtractor:
    @pytest.fixture
    def extractor(self, mock_gemini_client):
        return LLMCitationExtractor(gemini_client=mock_gemini_client)

    @pytest.mark.asyncio
    async def test_extract_numbered_citations(self, extractor):
        """번호 인용 추출."""
        text = """
        Previous studies [1,2] have shown that early intervention
        improves outcomes. However, Smith et al. [3] reported
        conflicting results.

        References:
        1. Kim Y. Spine Surgery. 2020.
        2. Park S. Outcomes Study. 2019.
        3. Smith J. Contrasting Findings. 2021.
        """

        citations = await extractor.extract_citations(text)

        assert len(citations) >= 3
        # 인용 타입 확인
        assert any(c.citation_type == "contrasting" for c in citations)

    @pytest.mark.asyncio
    async def test_extract_author_year_citations(self, extractor):
        """저자-연도 인용 추출."""
        text = """
        According to Kim et al. (2020), lumbar fusion shows
        promising results. This is supported by Park (2021)
        but contradicted by Lee and Smith (2019).
        """

        citations = await extractor.extract_citations(text)

        assert len(citations) >= 3
        assert any(c.cited_year == 2020 for c in citations)
        assert any("Kim" in str(c.cited_authors) for c in citations)

    @pytest.mark.asyncio
    async def test_detect_citation_type(self, extractor):
        """인용 유형 감지."""
        text = """
        Our findings are consistent with Kim (2020) who also
        observed improved outcomes. However, this contradicts
        the results of Lee (2019) who found no significant effect.
        """

        citations = await extractor.extract_citations(text)

        supporting = [c for c in citations if c.citation_type == "supporting"]
        contrasting = [c for c in citations if c.citation_type == "contrasting"]

        assert len(supporting) >= 1
        assert len(contrasting) >= 1

    @pytest.mark.asyncio
    async def test_match_by_title(self, extractor, mock_paper_graph):
        """제목 기반 매칭."""
        citations = [CitationInfo(
            cited_title="Spine Surgery Outcomes Study",
            cited_authors=["Kim"],
            cited_year=2020,
            citation_context="As shown by Kim (2020)...",
            citation_type="supporting"
        )]

        # mock_paper_graph에 유사 제목 논문 설정
        mock_paper_graph.list_papers.return_value = [
            PaperNode("p1", "Spine Surgery Outcomes Study", ["Kim Y"], 2020, "Summary")
        ]

        matches = await extractor.match_to_existing_papers(
            citations, mock_paper_graph, llm_verify=False
        )

        assert matches[0].matched_paper_id == "p1"
        assert matches[0].match_confidence > 0.8

    @pytest.mark.asyncio
    async def test_llm_verification(self, extractor, mock_paper_graph, mock_gemini_client):
        """LLM 매칭 검증."""
        citations = [CitationInfo(
            cited_title="Similar Title",
            cited_authors=["Kim"],
            cited_year=2020,
            citation_context="Kim (2020) reported...",
            citation_type="neutral"
        )]

        # LLM이 매칭을 거부하는 경우
        mock_gemini_client.generate_json.return_value = {
            "is_match": False,
            "confidence": 0.3,
            "reasoning": "Year mismatch"
        }

        matches = await extractor.match_to_existing_papers(
            citations, mock_paper_graph, llm_verify=True
        )

        assert matches[0].matched_paper_id is None
        assert matches[0].llm_verified is True

    @pytest.mark.asyncio
    async def test_extract_and_match_integration(self, extractor, mock_paper_graph):
        """추출+매칭 통합 테스트."""
        text = """
        This study builds on the work of Kim (2020) who first
        demonstrated the effectiveness of endoscopic surgery.
        """

        results = await extractor.extract_and_match(text, mock_paper_graph)

        assert len(results) >= 1
        assert all(isinstance(r, CitationMatch) for r in results)
```

### Edge Cases

```python
@pytest.mark.asyncio
async def test_no_citations(self, extractor):
    """인용 없는 텍스트."""
    text = "This is a simple text without any citations or references."
    citations = await extractor.extract_citations(text)
    assert len(citations) == 0

@pytest.mark.asyncio
async def test_incomplete_citation(self, extractor):
    """불완전한 인용."""
    text = "Some study [?] mentioned this, but details are unclear."
    citations = await extractor.extract_citations(text)
    # 불완전해도 추출 시도
    assert len(citations) >= 0

@pytest.mark.asyncio
async def test_multiple_same_citation(self, extractor):
    """같은 인용 여러 번."""
    text = """
    Kim (2020) showed A. Later, Kim (2020) also demonstrated B.
    As Kim (2020) concluded, the effect is significant.
    """
    citations = await extractor.extract_citations(text)
    # 각 인용 컨텍스트 별로 추출 (중복 인용 마커)
    assert len(citations) >= 1
```

---

## Dependencies

- `src/llm/gemini_client.py` - GeminiClient
- `src/knowledge/paper_graph.py` - PaperGraph

---

## Configuration

```yaml
# config.yaml
citation_extractor:
  extract_context_sentences: 2    # 인용 주변 문장 수
  llm_verify_matches: true        # LLM 매칭 검증 (정확도 우선)
  min_match_confidence: 0.7       # 최소 매칭 신뢰도

  # 매칭 전략
  matching:
    title_similarity_threshold: 0.8
    use_author_year: true
    use_context_similarity: true

  # References 파싱
  parse_references: true
  max_references: 100
```

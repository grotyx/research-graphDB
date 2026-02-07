"""Citation Extractor.

LLM-based extraction of citation information from paper text.
"""

import re
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from typing import Union
from llm import LLMClient, ClaudeClient, GeminiClient


class CitationType(Enum):
    """인용 유형."""
    SUPPORTING = "supporting"      # 지지하는 인용
    CONTRASTING = "contrasting"    # 반박하는 인용
    NEUTRAL = "neutral"            # 중립적 인용
    BACKGROUND = "background"      # 배경 설명 인용
    METHODOLOGICAL = "methodological"  # 방법론적 인용


@dataclass
class CitationInfo:
    """추출된 인용 정보.

    Attributes:
        cited_title: 인용된 논문 제목 (추정)
        cited_authors: 인용된 논문 저자들
        cited_year: 인용된 논문 출판 연도
        citation_context: 인용된 맥락 문장
        citation_type: 인용 유형
        citation_text: 원본 인용 텍스트 (예: "Smith et al., 2020")
        confidence: 추출 신뢰도
    """
    cited_title: Optional[str] = None
    cited_authors: list[str] = field(default_factory=list)
    cited_year: Optional[int] = None
    citation_context: str = ""
    citation_type: CitationType = CitationType.NEUTRAL
    citation_text: str = ""
    confidence: float = 0.0


class LLMCitationExtractor:
    """LLM 기반 인용 추출기.

    논문 텍스트에서 인용 정보를 추출하고 분류합니다.
    """

    # 인용 패턴 정규식
    CITATION_PATTERNS = [
        # (Author et al., 2020)
        r'\(([A-Z][a-z]+(?:\s+et\s+al\.?)?),?\s*(\d{4})\)',
        # [1], [2,3], [1-5]
        r'\[(\d+(?:[-,]\d+)*)\]',
        # Author et al. (2020)
        r'([A-Z][a-z]+(?:\s+et\s+al\.?)?)\s*\((\d{4})\)',
        # (Author, 2020; Author, 2021)
        r'\(([^)]+,\s*\d{4}(?:;\s*[^)]+,\s*\d{4})*)\)',
        # Author and Author (2020)
        r'([A-Z][a-z]+\s+and\s+[A-Z][a-z]+)\s*\((\d{4})\)',
    ]

    def __init__(
        self,
        llm_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None,
        use_llm: bool = True,
        gemini_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None  # 하위 호환성
    ):
        """Initialize extractor.

        Args:
            llm_client: LLM API 클라이언트 (Claude 또는 Gemini)
            use_llm: LLM 사용 여부 (False면 규칙 기반만)
            gemini_client: (Deprecated) 하위 호환성을 위한 파라미터, llm_client 사용 권장
        """
        # 하위 호환성: gemini_client가 전달되면 llm_client로 사용
        client = llm_client or gemini_client
        self.llm = client
        self.gemini = self.llm  # 하위 호환성 속성
        self.use_llm = use_llm and client is not None

    async def extract_citations(
        self,
        text: str,
        use_llm: Optional[bool] = None
    ) -> list[CitationInfo]:
        """텍스트에서 인용 정보 추출.

        Args:
            text: 논문 텍스트
            use_llm: LLM 사용 여부 (None이면 인스턴스 설정 사용)

        Returns:
            CitationInfo 목록
        """
        if not text.strip():
            return []

        use_llm_now = use_llm if use_llm is not None else self.use_llm

        if use_llm_now and self.gemini:
            try:
                return await self._extract_with_llm(text)
            except Exception:
                # Fallback to rule-based
                pass

        return self._extract_with_rules(text)

    async def _extract_with_llm(self, text: str) -> list[CitationInfo]:
        """LLM으로 인용 추출."""
        # 텍스트가 너무 길면 분할
        max_length = 8000
        if len(text) > max_length:
            text = text[:max_length]

        prompt = f"""Analyze the following academic text and extract all citations.

For each citation, identify:
1. The cited author(s) name(s)
2. The publication year (if mentioned)
3. The context sentence where the citation appears
4. The citation type: "supporting" (supports the author's point), "contrasting" (presents opposing view), "neutral" (simple reference), "background" (provides context), "methodological" (describes methods)
5. The exact citation text as it appears
6. Confidence score (0.0-1.0): how certain you are about the extraction. Consider: author clarity, year presence, context clarity, citation type certainty

Return as JSON array:
{{
  "citations": [
    {{
      "authors": ["Author1", "Author2"],
      "year": 2020,
      "context": "The context sentence containing the citation",
      "type": "supporting",
      "citation_text": "Author1 et al., 2020",
      "confidence": 0.85
    }}
  ]
}}

If no citations found, return {{"citations": []}}

Text:
{text}"""

        response = await self.gemini.generate_json(prompt, {
            "type": "OBJECT",
            "properties": {
                "citations": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "authors": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "year": {"type": "INTEGER"},
                            "context": {"type": "STRING"},
                            "type": {"type": "STRING"},
                            "citation_text": {"type": "STRING"},
                            "confidence": {"type": "NUMBER"}
                        }
                    }
                }
            }
        })

        citations = []
        for item in response.get("citations", []):
            citation_type = self._parse_citation_type(item.get("type", "neutral"))
            # LLM이 반환한 신뢰도 사용, 없으면 0.75 기본값
            confidence = item.get("confidence", 0.75)
            # 범위 검증 (0.0 ~ 1.0)
            confidence = max(0.0, min(1.0, confidence))
            citations.append(CitationInfo(
                cited_authors=item.get("authors", []),
                cited_year=item.get("year"),
                citation_context=item.get("context", ""),
                citation_type=citation_type,
                citation_text=item.get("citation_text", ""),
                confidence=confidence,
            ))

        return citations

    def _extract_with_rules(self, text: str) -> list[CitationInfo]:
        """규칙 기반 인용 추출."""
        citations = []
        seen = set()

        for pattern in self.CITATION_PATTERNS:
            for match in re.finditer(pattern, text):
                citation_text = match.group(0)
                if citation_text in seen:
                    continue
                seen.add(citation_text)

                # 컨텍스트 추출 (인용 주변 문장)
                context = self._extract_context(text, match.start(), match.end())

                # 저자와 연도 파싱
                authors, year = self._parse_citation_text(citation_text)

                # 인용 유형 추정
                citation_type = self._infer_citation_type(context)

                # 신뢰도 계산
                confidence = self._calculate_rule_confidence(
                    authors=authors,
                    year=year,
                    context=context,
                    citation_type=citation_type
                )

                citations.append(CitationInfo(
                    cited_authors=authors,
                    cited_year=year,
                    citation_context=context,
                    citation_type=citation_type,
                    citation_text=citation_text,
                    confidence=confidence,
                ))

        return citations

    def _calculate_rule_confidence(
        self,
        authors: list[str],
        year: Optional[int],
        context: str,
        citation_type: CitationType
    ) -> float:
        """규칙 기반 추출의 신뢰도 계산.

        Args:
            authors: 추출된 저자 목록
            year: 추출된 연도
            context: 인용 컨텍스트
            citation_type: 인용 유형

        Returns:
            0.0 ~ 1.0 범위의 신뢰도
        """
        confidence = 0.5  # 기본 점수

        # 저자 존재 여부 (+0.15)
        if authors and len(authors) > 0:
            confidence += 0.15

        # 연도 존재 여부 (+0.15)
        if year and 1900 <= year <= 2100:
            confidence += 0.15

        # 컨텍스트 품질 (+0.10)
        if context and len(context) > 30:
            confidence += 0.10

        # 인용 유형이 특정되면 (+0.05)
        if citation_type != CitationType.NEUTRAL:
            confidence += 0.05

        # 최대 0.95로 제한 (LLM보다 낮게)
        return min(0.95, confidence)

    def _extract_context(self, text: str, start: int, end: int, window: int = 200) -> str:
        """인용 주변 컨텍스트 추출."""
        # 문장 경계 찾기
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)

        # 문장 시작점 찾기
        for i in range(context_start, start):
            if text[i] in '.!?' and i > context_start:
                context_start = i + 1
                break

        # 문장 끝점 찾기
        for i in range(end, context_end):
            if text[i] in '.!?':
                context_end = i + 1
                break

        return text[context_start:context_end].strip()

    def _parse_citation_text(self, citation_text: str) -> tuple[list[str], Optional[int]]:
        """인용 텍스트에서 저자와 연도 파싱."""
        authors = []
        year = None

        # 연도 추출
        year_match = re.search(r'(\d{4})', citation_text)
        if year_match:
            year = int(year_match.group(1))

        # 저자 추출
        # "Author et al." 패턴
        author_match = re.search(r'([A-Z][a-z]+)(?:\s+et\s+al\.?)?', citation_text)
        if author_match:
            authors.append(author_match.group(1))

        # "Author and Author" 패턴
        and_match = re.search(r'([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)', citation_text)
        if and_match:
            authors = [and_match.group(1), and_match.group(2)]

        return authors, year

    def _infer_citation_type(self, context: str) -> CitationType:
        """컨텍스트에서 인용 유형 추론."""
        context_lower = context.lower()

        # 지지 표현
        supporting_phrases = [
            "consistent with", "supports", "confirmed", "in agreement",
            "similarly", "likewise", "as shown by", "demonstrated",
            "found that", "showed that"
        ]

        # 반박 표현
        contrasting_phrases = [
            "however", "in contrast", "contradicts", "unlike",
            "disagrees", "conflicts with", "contrary to", "despite",
            "although", "whereas"
        ]

        # 방법론 표현
        methodological_phrases = [
            "method", "protocol", "procedure", "technique",
            "following", "according to", "as described by"
        ]

        # 배경 표현
        background_phrases = [
            "background", "introduction", "previously", "history",
            "first described", "originally", "traditionally"
        ]

        for phrase in contrasting_phrases:
            if phrase in context_lower:
                return CitationType.CONTRASTING

        for phrase in supporting_phrases:
            if phrase in context_lower:
                return CitationType.SUPPORTING

        for phrase in methodological_phrases:
            if phrase in context_lower:
                return CitationType.METHODOLOGICAL

        for phrase in background_phrases:
            if phrase in context_lower:
                return CitationType.BACKGROUND

        return CitationType.NEUTRAL

    def _parse_citation_type(self, type_str: str) -> CitationType:
        """문자열을 CitationType으로 변환."""
        type_map = {
            "supporting": CitationType.SUPPORTING,
            "contrasting": CitationType.CONTRASTING,
            "neutral": CitationType.NEUTRAL,
            "background": CitationType.BACKGROUND,
            "methodological": CitationType.METHODOLOGICAL,
        }
        return type_map.get(type_str.lower(), CitationType.NEUTRAL)

    async def match_to_existing_papers(
        self,
        citations: list[CitationInfo],
        paper_graph: "PaperGraph"
    ) -> list[tuple[CitationInfo, Optional[str]]]:
        """인용을 기존 논문과 매칭.

        Args:
            citations: 추출된 인용 목록
            paper_graph: 논문 그래프

        Returns:
            (CitationInfo, matched_paper_id or None) 튜플 목록
        """
        from .paper_graph import PaperGraph

        results = []
        all_papers = await paper_graph.list_papers(limit=1000)

        for citation in citations:
            matched_id = None

            # 연도와 저자로 매칭 시도
            for paper in all_papers:
                # 연도 매칭
                if citation.cited_year and paper.year:
                    if citation.cited_year != paper.year:
                        continue

                # 저자 매칭 (첫 저자 성이 포함되는지)
                if citation.cited_authors and paper.authors:
                    first_cited_author = citation.cited_authors[0].lower()
                    paper_authors_str = " ".join(paper.authors).lower()
                    if first_cited_author not in paper_authors_str:
                        continue

                # 매칭 성공
                matched_id = paper.paper_id
                break

            results.append((citation, matched_id))

        return results

    async def extract_and_link_citations(
        self,
        text: str,
        paper_graph: "PaperGraph",
        source_paper_id: str
    ) -> dict:
        """인용 추출 및 기존 논문과 링크.

        전체 워크플로우:
        1. 텍스트에서 인용 추출
        2. 기존 논문과 매칭
        3. 관계 생성 (매칭된 것만)

        Args:
            text: 논문 텍스트
            paper_graph: 논문 그래프
            source_paper_id: 소스 논문 ID

        Returns:
            {
                "citations": list[CitationInfo],
                "matched": [(CitationInfo, paper_id), ...],
                "unmatched": [CitationInfo, ...],
                "relations_created": int
            }
        """
        from .paper_graph import PaperRelation, RelationType

        # 1. 인용 추출
        citations = await self.extract_citations(text)

        # 2. 기존 논문과 매칭
        matched_pairs = await self.match_to_existing_papers(citations, paper_graph)

        matched = []
        unmatched = []
        relations_created = 0

        # 3. 관계 생성
        for citation, paper_id in matched_pairs:
            if paper_id:
                matched.append((citation, paper_id))

                # CITES 관계 생성
                relation_type = RelationType.CITES

                # 인용 유형에 따라 추가 관계도 생성
                if citation.citation_type == CitationType.SUPPORTING:
                    await paper_graph.add_relation(PaperRelation(
                        source_id=source_paper_id,
                        target_id=paper_id,
                        relation_type=RelationType.SUPPORTS,
                        confidence=citation.confidence * 0.8,
                        evidence=citation.citation_context,
                        detected_by="citation_extraction",
                    ))
                    relations_created += 1

                elif citation.citation_type == CitationType.CONTRASTING:
                    await paper_graph.add_relation(PaperRelation(
                        source_id=source_paper_id,
                        target_id=paper_id,
                        relation_type=RelationType.CONTRADICTS,
                        confidence=citation.confidence * 0.8,
                        evidence=citation.citation_context,
                        detected_by="citation_extraction",
                    ))
                    relations_created += 1

                # 기본 CITES 관계
                await paper_graph.add_relation(PaperRelation(
                    source_id=source_paper_id,
                    target_id=paper_id,
                    relation_type=relation_type,
                    confidence=citation.confidence,
                    evidence=f"Citation: {citation.citation_text}",
                    detected_by="citation_extraction",
                ))
                relations_created += 1

            else:
                unmatched.append(citation)

        return {
            "citations": citations,
            "matched": matched,
            "unmatched": unmatched,
            "relations_created": relations_created,
        }

"""Citation Detector module for identifying citations and source types in text."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceType(Enum):
    """콘텐츠 출처 유형."""
    ORIGINAL = "original"      # 이 논문의 고유 연구 결과
    CITATION = "citation"      # 다른 논문 인용
    BACKGROUND = "background"  # 일반적 배경 지식


@dataclass
class CitationInfo:
    """인용 정보."""
    cited_text: str              # 인용된 텍스트 부분
    citation_marker: str         # 인용 마커 (예: "(Kim et al., 2023)")
    authors: list[str] = field(default_factory=list)  # 추출된 저자들
    year: Optional[int] = None   # 출판 연도
    position: tuple[int, int] = (0, 0)  # 텍스트 내 위치 (start, end)


@dataclass
class CitationInput:
    """인용 탐지 입력."""
    text: str
    document_authors: Optional[list[str]] = None  # 현재 문서 저자 (선택)
    document_year: Optional[int] = None           # 현재 문서 연도 (선택)


@dataclass
class CitationOutput:
    """인용 탐지 결과."""
    source_type: SourceType
    confidence: float              # 신뢰도 (0.0 ~ 1.0)
    citations: list[CitationInfo] = field(default_factory=list)
    original_ratio: float = 1.0    # 원본 내용 비율 (0.0 ~ 1.0)


class CitationDetector:
    """인용 탐지기."""

    # 인용 마커 패턴
    CITATION_PATTERNS = [
        # APA Style: (Author et al., 2023), (Author, 2023)
        (r'\(([A-Z][a-z]+(?:\s+et\s+al\.?)?(?:,?\s*\d{4})?)\)', "apa"),
        # Multiple APA: (Kim et al., 2023; Lee, 2022)
        (r'\(([A-Z][a-z]+(?:\s+et\s+al\.?)?(?:,?\s*\d{4})?(?:;\s*[A-Z][a-z]+(?:\s+et\s+al\.?)?(?:,?\s*\d{4})?)+)\)', "apa_multi"),
        # Author & Author: (Kim & Lee, 2023)
        (r'\(([A-Z][a-z]+\s*(?:&|and)\s*[A-Z][a-z]+(?:,?\s*\d{4})?)\)', "apa_two"),
        # Numbered: [1], [1,2], [1-3], [1, 2, 3]
        (r'\[(\d+(?:[,\-–]\s*\d+)*)\]', "numbered"),
        # Superscript style: ¹, ², ¹²³
        (r'([¹²³⁴⁵⁶⁷⁸⁹⁰]+)', "superscript"),
        # Year only in context: (2023)
        (r'\((\d{4})\)', "year_only"),
    ]

    # 인용 문맥 구문
    CITATION_CONTEXT_PHRASES = [
        "according to",
        "as reported by",
        "as shown by",
        "as demonstrated by",
        "previous studies",
        "prior research",
        "earlier work",
        "it has been shown",
        "it was reported",
        "it has been reported",
        "has been demonstrated",
        "have shown that",
        "reported that",
        "found that",
        "showed that",
        "demonstrated that",
        "consistent with",
        "in agreement with",
        "similar to findings",
        "in contrast to",
        "unlike",
        "compared to previous",
    ]

    # 원본 콘텐츠 지표
    ORIGINAL_INDICATORS = [
        "our study",
        "our results",
        "our findings",
        "our analysis",
        "our data",
        "our research",
        "our investigation",
        "we found",
        "we observed",
        "we demonstrated",
        "we showed",
        "we analyzed",
        "we identified",
        "we examined",
        "we investigated",
        "we measured",
        "we recruited",
        "we included",
        "we conducted",
        "we performed",
        "in this study",
        "the present study",
        "this investigation",
        "in the current study",
        "the current analysis",
    ]

    def __init__(self, config: Optional[dict] = None):
        """초기화.

        Args:
            config: 설정 딕셔너리
                - min_confidence: 최소 신뢰도 (기본값: 0.5)
                - original_threshold: 원본 판정 임계값 (기본값: 0.7)
                - citation_threshold: 인용 판정 임계값 (기본값: 0.3)
        """
        self.config = config or {}
        self.min_confidence = self.config.get("min_confidence", 0.5)
        self.original_threshold = self.config.get("original_threshold", 0.7)
        self.citation_threshold = self.config.get("citation_threshold", 0.3)

        # 정규식 패턴 컴파일
        self._compiled_citation_patterns = [
            (re.compile(pattern, re.IGNORECASE), style)
            for pattern, style in self.CITATION_PATTERNS
        ]

        self._compiled_context_patterns = [
            re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
            for phrase in self.CITATION_CONTEXT_PHRASES
        ]

        self._compiled_original_patterns = [
            re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
            for phrase in self.ORIGINAL_INDICATORS
        ]

    def detect(self, input_data: CitationInput) -> CitationOutput:
        """텍스트에서 인용을 탐지.

        Args:
            input_data: 탐지 입력 데이터

        Returns:
            인용 탐지 결과
        """
        if not input_data.text or not input_data.text.strip():
            return CitationOutput(
                source_type=SourceType.BACKGROUND,
                confidence=0.0,
                citations=[],
                original_ratio=0.0
            )

        text = input_data.text

        # 1. 인용 마커 탐지
        citations = self._find_citation_markers(text)

        # 2. 인용 컨텍스트 분석 (마커 없는 인용)
        context_score = self._calculate_context_score(text)

        # 3. 원본 콘텐츠 점수 계산
        original_score = self._calculate_original_score(text)

        # 4. 출처 유형 결정
        source_type = self._determine_source_type(
            citations=citations,
            original_score=original_score,
            context_score=context_score
        )

        # 5. 원본 비율 계산
        original_ratio = self._calculate_original_ratio(text, citations, original_score)

        # 6. 신뢰도 계산
        confidence = self._calculate_confidence(
            citations, original_score, context_score
        )

        return CitationOutput(
            source_type=source_type,
            confidence=round(confidence, 3),
            citations=citations,
            original_ratio=round(original_ratio, 3)
        )

    def _find_citation_markers(self, text: str) -> list[CitationInfo]:
        """인용 마커 탐지.

        Args:
            text: 분석할 텍스트

        Returns:
            탐지된 인용 정보 목록
        """
        citations = []
        seen_positions = set()

        for pattern, style in self._compiled_citation_patterns:
            for match in pattern.finditer(text):
                start, end = match.span()

                # 중복 방지
                if any(s <= start < e or s < end <= e for s, e in seen_positions):
                    continue

                marker = match.group(0)
                content = match.group(1)

                # 저자 및 연도 추출
                authors, year = self._extract_author_year(content, style)

                # 연도 검증 (1900~현재+1)
                if year and not (1900 <= year <= 2030):
                    year = None

                citations.append(CitationInfo(
                    cited_text=self._get_context_text(text, start, end),
                    citation_marker=marker,
                    authors=authors,
                    year=year,
                    position=(start, end)
                ))

                seen_positions.add((start, end))

        return citations

    def _extract_author_year(
        self,
        content: str,
        style: str
    ) -> tuple[list[str], Optional[int]]:
        """인용 내용에서 저자와 연도 추출.

        Args:
            content: 인용 내용
            style: 인용 스타일

        Returns:
            (저자 목록, 연도) 튜플
        """
        authors = []
        year = None

        if style in ["apa", "apa_multi", "apa_two"]:
            # 연도 추출
            year_match = re.search(r'\b(\d{4})\b', content)
            if year_match:
                year = int(year_match.group(1))

            # 저자 추출
            author_pattern = re.compile(r'([A-Z][a-z]+)(?:\s+et\s+al\.?)?')
            author_matches = author_pattern.findall(content)
            authors = author_matches

        elif style == "year_only":
            year_match = re.search(r'(\d{4})', content)
            if year_match:
                year = int(year_match.group(1))

        return authors, year

    def _get_context_text(self, text: str, start: int, end: int, window: int = 50) -> str:
        """인용 주변 텍스트 추출.

        Args:
            text: 전체 텍스트
            start: 인용 시작 위치
            end: 인용 끝 위치
            window: 컨텍스트 윈도우 크기

        Returns:
            인용 주변 텍스트
        """
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]

    def _calculate_context_score(self, text: str) -> float:
        """인용 문맥 점수 계산.

        Args:
            text: 분석할 텍스트

        Returns:
            인용 문맥 점수 (0.0~1.0)
        """
        match_count = 0
        for pattern in self._compiled_context_patterns:
            matches = pattern.findall(text)
            match_count += len(matches)

        # 정규화 (최대 10개 매칭으로 1.0)
        return min(1.0, match_count / 10.0)

    def _calculate_original_score(self, text: str) -> float:
        """원본 콘텐츠 점수 계산.

        Args:
            text: 분석할 텍스트

        Returns:
            원본 콘텐츠 점수 (0.0~1.0)
        """
        match_count = 0
        for pattern in self._compiled_original_patterns:
            matches = pattern.findall(text)
            match_count += len(matches)

        # 정규화 (최대 5개 매칭으로 1.0)
        return min(1.0, match_count / 5.0)

    def _determine_source_type(
        self,
        citations: list[CitationInfo],
        original_score: float,
        context_score: float
    ) -> SourceType:
        """출처 유형 결정.

        Args:
            citations: 탐지된 인용 목록
            original_score: 원본 콘텐츠 점수
            context_score: 인용 문맥 점수

        Returns:
            출처 유형
        """
        has_citations = len(citations) > 0
        has_context_citations = context_score > 0.3

        # 원본 지표가 강하고 인용이 없으면 ORIGINAL
        if original_score >= self.original_threshold and not has_citations:
            return SourceType.ORIGINAL

        # 인용이 있고 원본 지표가 약하면 CITATION
        if (has_citations or has_context_citations) and original_score < self.citation_threshold:
            return SourceType.CITATION

        # 원본 지표도 인용도 없으면 BACKGROUND
        if original_score < self.citation_threshold and not has_citations and not has_context_citations:
            return SourceType.BACKGROUND

        # 혼합된 경우 - 원본 점수 기반 판단
        if original_score >= 0.5:
            return SourceType.ORIGINAL
        elif has_citations or has_context_citations:
            return SourceType.CITATION
        else:
            return SourceType.BACKGROUND

    def _calculate_original_ratio(
        self,
        text: str,
        citations: list[CitationInfo],
        original_score: float
    ) -> float:
        """원본 내용 비율 계산.

        Args:
            text: 분석한 텍스트
            citations: 탐지된 인용 목록
            original_score: 원본 콘텐츠 점수

        Returns:
            원본 내용 비율 (0.0~1.0)
        """
        if not text:
            return 0.0

        # 인용 마커가 차지하는 문자 수
        citation_chars = sum(
            c.position[1] - c.position[0]
            for c in citations
        )

        # 인용 비율 계산
        citation_ratio = citation_chars / len(text) if len(text) > 0 else 0.0

        # 원본 점수와 인용 비율을 조합
        # 원본 점수가 높고 인용이 적으면 원본 비율이 높음
        original_ratio = (1.0 - citation_ratio) * (0.5 + 0.5 * original_score)

        return min(1.0, max(0.0, original_ratio))

    def _calculate_confidence(
        self,
        citations: list[CitationInfo],
        original_score: float,
        context_score: float
    ) -> float:
        """탐지 신뢰도 계산.

        Args:
            citations: 탐지된 인용 목록
            original_score: 원본 콘텐츠 점수
            context_score: 인용 문맥 점수

        Returns:
            신뢰도 (0.0~1.0)
        """
        # 명확한 신호가 있을수록 신뢰도가 높음
        signals = []

        if len(citations) > 0:
            signals.append(min(1.0, len(citations) / 3.0))  # 인용 수

        if original_score > 0:
            signals.append(original_score)

        if context_score > 0:
            signals.append(context_score)

        if not signals:
            return 0.3  # 신호가 없으면 낮은 신뢰도

        return sum(signals) / len(signals)

    def detect_batch(self, inputs: list[CitationInput]) -> list[CitationOutput]:
        """여러 텍스트를 일괄 탐지.

        Args:
            inputs: 입력 데이터 목록

        Returns:
            탐지 결과 목록
        """
        return [self.detect(input_data) for input_data in inputs]

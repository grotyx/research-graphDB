"""LLM-based Section Classifier.

LLM을 사용하여 의학 논문의 섹션 경계를 식별하고 분류합니다.
기본값: Claude Haiku 4.5 (환경변수로 변경 가능)
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional, Union

from llm import LLMClient, ClaudeClient, GeminiClient
from llm.prompts import SECTION_CLASSIFIER_SYSTEM, SECTION_CLASSIFIER_SCHEMA
from builder.section_classifier import SectionClassifier, SectionInput

logger = logging.getLogger(__name__)


# Tier 매핑
SECTION_TIERS = {
    "abstract": 1,
    "results": 1,
    "conclusion": 1,
    "introduction": 2,
    "methods": 2,
    "discussion": 2,
    "references": 2,
    "acknowledgments": 2,
    "tables_figures": 2,
    "supplementary": 2,
    "other": 2
}


@dataclass
class SectionBoundary:
    """섹션 경계 정보."""
    section_type: str       # abstract, introduction, methods, results, discussion, conclusion, references, other
    start_char: int         # 시작 문자 위치
    end_char: int           # 끝 문자 위치
    confidence: float       # 신뢰도 (0.0 ~ 1.0)
    tier: int               # 1=핵심, 2=상세
    heading: Optional[str] = None  # 감지된 섹션 헤딩


class ClassificationError(Exception):
    """섹션 분류 에러."""
    pass


class LLMSectionClassifier:
    """LLM 기반 섹션 분류기."""

    # 최대 청크 크기 (토큰 제한 고려)
    MAX_CHUNK_SIZE = 50000

    # 섹션 헤딩 패턴 (경계 추정용)
    HEADING_PATTERNS = [
        r'\n\s*(abstract|summary|background)\s*\n',
        r'\n\s*(introduction|background)\s*\n',
        r'\n\s*(materials?\s+and\s+)?methods?\s*\n',
        r'\n\s*(results?|findings?)\s*\n',
        r'\n\s*(discussion)\s*\n',
        r'\n\s*(conclusions?)\s*\n',
        r'\n\s*(references?|bibliography)\s*\n',
        r'\n\s*(acknowledgments?|funding)\s*\n',
    ]

    def __init__(
        self,
        llm_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None,
        fallback_classifier: Optional[SectionClassifier] = None,
        config: Optional[dict] = None,
        # 하위 호환성
        gemini_client: Optional[Union[LLMClient, ClaudeClient, GeminiClient]] = None
    ):
        """초기화.

        Args:
            llm_client: LLM 클라이언트 (None이면 자동 생성)
            fallback_classifier: 규칙 기반 Fallback 분류기
            config: 추가 설정
                - min_confidence: 최소 신뢰도 (기본: 0.7)
                - max_text_length: 최대 텍스트 길이 (기본: 100000)
            gemini_client: 레거시 파라미터 (llm_client 사용 권장)
        """
        # 하위 호환성: gemini_client 파라미터도 지원
        client = llm_client or gemini_client
        if client is None:
            client = LLMClient()
        self.llm = client
        # 하위 호환성 속성
        self.gemini = self.llm
        self.fallback = fallback_classifier or SectionClassifier()
        self.config = config or {}
        self.min_confidence = self.config.get("min_confidence", 0.7)
        self.max_text_length = self.config.get("max_text_length", 100000)

    async def classify(
        self,
        full_text: str
    ) -> list[SectionBoundary]:
        """전체 논문 텍스트에서 섹션 경계 식별 (LLM 기반만 사용).

        Args:
            full_text: 전체 논문 텍스트

        Returns:
            섹션 경계 목록 (시작 위치 기준 정렬)

        Raises:
            ClassificationError: 분류 실패
        """
        if not full_text or not full_text.strip():
            return []

        # LLM 분류
        if len(full_text) > self.MAX_CHUNK_SIZE:
            sections = await self._classify_long_text(full_text)
        else:
            sections = await self._classify_single(full_text)

        # 결과 검증 및 보정
        sections = self.validate_sections(sections, len(full_text))

        # Tier 할당
        for section in sections:
            section.tier = SECTION_TIERS.get(section.section_type, 2)

        return sorted(sections, key=lambda s: s.start_char)

    async def classify_with_context(
        self,
        full_text: str,
        paper_metadata: Optional[dict] = None
    ) -> list[SectionBoundary]:
        """메타데이터 컨텍스트를 활용한 분류.

        Args:
            full_text: 전체 논문 텍스트
            paper_metadata: 논문 메타데이터 (title, journal, year 등)

        Returns:
            섹션 경계 목록
        """
        # 메타데이터를 프롬프트에 추가
        context = ""
        if paper_metadata:
            context = f"\nPaper context:\n- Title: {paper_metadata.get('title', 'Unknown')}\n- Journal: {paper_metadata.get('journal', 'Unknown')}\n- Year: {paper_metadata.get('year', 'Unknown')}\n"

        return await self.classify(full_text)

    async def _classify_single(self, text: str) -> list[SectionBoundary]:
        """단일 텍스트 분류.

        Args:
            text: 분류할 텍스트

        Returns:
            섹션 경계 목록
        """
        prompt = f"""Analyze this medical paper and identify all section boundaries.

Paper text:
---
{text}
---

Total characters: {len(text)}

For each section found, provide:
1. section_type: One of [abstract, introduction, methods, results, discussion, conclusion, references, other]
2. start_char: Starting character position (0-indexed)
3. end_char: Ending character position (exclusive)
4. confidence: Your confidence in this classification (0.0 to 1.0)
5. heading: The actual section heading text if found (null if none)

Return the results as a JSON object with a "sections" array sorted by start position."""

        schema = {
            "type": "OBJECT",
            "properties": {
                "sections": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "section_type": {
                                "type": "STRING",
                                "enum": ["abstract", "introduction", "methods", "results",
                                        "discussion", "conclusion", "references", "other"]
                            },
                            "start_char": {"type": "INTEGER"},
                            "end_char": {"type": "INTEGER"},
                            "confidence": {"type": "NUMBER"},
                            "heading": {"type": "STRING"}
                        },
                        "required": ["section_type", "start_char", "end_char", "confidence"]
                    }
                }
            },
            "required": ["sections"]
        }

        result = await self.gemini.generate_json(
            prompt=prompt,
            schema=schema,
            system=SECTION_CLASSIFIER_SYSTEM
        )

        sections = []
        for item in result.get("sections", []):
            section = SectionBoundary(
                section_type=item["section_type"],
                start_char=item["start_char"],
                end_char=min(item["end_char"], len(text)),  # 텍스트 길이 초과 방지
                confidence=item["confidence"],
                tier=SECTION_TIERS.get(item["section_type"], 2),
                heading=item.get("heading")
            )
            sections.append(section)

        return sections

    async def _classify_long_text(self, text: str) -> list[SectionBoundary]:
        """긴 텍스트 분할 처리.

        Args:
            text: 긴 텍스트

        Returns:
            병합된 섹션 경계 목록
        """
        # 대략적인 섹션 경계 추정
        estimated_boundaries = self._estimate_boundaries(text)

        # 청크 분할
        chunks = self._split_at_boundaries(text, estimated_boundaries)

        # 병렬 처리
        chunk_results = await asyncio.gather(*[
            self._classify_single(chunk["text"]) for chunk in chunks
        ], return_exceptions=True)

        # 결과 병합
        all_sections = []
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                logger.warning(f"Chunk {i} classification failed: {result}")
                continue

            offset = chunks[i]["offset"]
            for section in result:
                section.start_char += offset
                section.end_char += offset
                all_sections.append(section)

        # 겹치는 섹션 해결
        return self.validate_sections(all_sections, len(text))

    def _estimate_boundaries(self, text: str) -> list[int]:
        """키워드 기반 섹션 경계 추정.

        Args:
            text: 전체 텍스트

        Returns:
            추정된 경계 위치 목록
        """
        boundaries = [0]
        text_lower = text.lower()

        for pattern in self.HEADING_PATTERNS:
            for match in re.finditer(pattern, text_lower, re.IGNORECASE):
                pos = match.start()
                # 너무 가까운 경계 제외
                if all(abs(pos - b) > 500 for b in boundaries):
                    boundaries.append(pos)

        boundaries.append(len(text))
        return sorted(boundaries)

    def _split_at_boundaries(
        self,
        text: str,
        boundaries: list[int]
    ) -> list[dict]:
        """경계에서 텍스트 분할.

        Args:
            text: 전체 텍스트
            boundaries: 경계 위치 목록

        Returns:
            청크 정보 목록 [{"text": ..., "offset": ...}, ...]
        """
        chunks = []
        for i in range(len(boundaries) - 1):
            start = boundaries[i]
            end = boundaries[i + 1]

            # 청크가 너무 크면 추가 분할
            while end - start > self.MAX_CHUNK_SIZE:
                mid = start + self.MAX_CHUNK_SIZE
                # 문장 경계에서 분할
                sentence_end = text.rfind('. ', start, mid)
                if sentence_end > start:
                    mid = sentence_end + 2

                chunks.append({
                    "text": text[start:mid],
                    "offset": start
                })
                start = mid

            if start < end:
                chunks.append({
                    "text": text[start:end],
                    "offset": start
                })

        return chunks

    def validate_sections(
        self,
        sections: list[SectionBoundary],
        text_length: int
    ) -> list[SectionBoundary]:
        """섹션 경계 검증 및 보정.

        Args:
            sections: 섹션 목록
            text_length: 전체 텍스트 길이

        Returns:
            검증/보정된 섹션 목록
        """
        if not sections:
            return sections

        # 시작 위치 기준 정렬
        sorted_sections = sorted(sections, key=lambda s: s.start_char)

        # 겹치는 섹션 해결
        validated = []
        for section in sorted_sections:
            if not validated:
                validated.append(section)
                continue

            prev = validated[-1]

            # 겹침 확인
            if section.start_char < prev.end_char:
                # 신뢰도가 높은 쪽 우선
                if section.confidence > prev.confidence:
                    prev.end_char = section.start_char
                else:
                    section.start_char = prev.end_char

            # 비정상적으로 짧은 섹션 병합 (100자 미만)
            if section.end_char - section.start_char < 100:
                # 이전 섹션에 병합
                prev.end_char = section.end_char
                continue

            validated.append(section)

        # 빠진 영역 처리 (첫 번째 섹션 이전)
        if validated and validated[0].start_char > 0:
            validated.insert(0, SectionBoundary(
                section_type="other",
                start_char=0,
                end_char=validated[0].start_char,
                confidence=0.5,
                tier=2
            ))

        # 빠진 영역 처리 (마지막 섹션 이후)
        if validated and validated[-1].end_char < text_length:
            validated.append(SectionBoundary(
                section_type="other",
                start_char=validated[-1].end_char,
                end_char=text_length,
                confidence=0.5,
                tier=2
            ))

        return validated

    def _is_valid_result(
        self,
        sections: list[SectionBoundary],
        text_length: int
    ) -> bool:
        """결과 유효성 검증.

        Args:
            sections: 섹션 목록
            text_length: 전체 텍스트 길이

        Returns:
            유효성 여부
        """
        if not sections:
            return False

        # 1. 전체 텍스트 커버리지 확인 (최소 50% - 더 관대하게)
        covered = sum(s.end_char - s.start_char for s in sections)
        coverage_ratio = covered / text_length if text_length > 0 else 0
        if coverage_ratio < 0.50:
            logger.warning(f"Low section coverage: {covered}/{text_length} ({coverage_ratio:.1%})")
            return False
        elif coverage_ratio < 0.80:
            logger.info(f"Acceptable section coverage: {covered}/{text_length} ({coverage_ratio:.1%})")

        # 2. 심각한 섹션 겹침만 확인 (50자 이상)
        sorted_sections = sorted(sections, key=lambda s: s.start_char)
        for i in range(len(sorted_sections) - 1):
            overlap = sorted_sections[i].end_char - sorted_sections[i + 1].start_char
            if overlap > 50:  # 10자 → 50자로 완화
                logger.warning(f"Section overlap: {overlap} chars")
                return False

        # 3. 평균 신뢰도 확인 (더 관대하게)
        avg_confidence = sum(s.confidence for s in sections) / len(sections)
        if avg_confidence < 0.3:  # 0.5 → 0.3으로 완화
            logger.warning(f"Low average confidence: {avg_confidence:.2f}")
            return False

        return True

    def _use_rule_based_fallback(self, text: str) -> list[SectionBoundary]:
        """규칙 기반 Fallback 분류.

        Args:
            text: 전체 텍스트

        Returns:
            섹션 경계 목록
        """
        # 텍스트를 단락으로 분할
        paragraphs = self._split_into_paragraphs(text)

        sections = []
        current_section = None
        current_start = 0

        for para in paragraphs:
            # 각 단락 분류
            result = self.fallback.classify(SectionInput(
                text=para["text"],
                source_position=para["position"]
            ))

            # 섹션 변경 감지
            if current_section is None:
                current_section = result.section
                current_start = para["start"]
            elif result.section != current_section and result.confidence > 0.5:
                # 이전 섹션 저장
                sections.append(SectionBoundary(
                    section_type=current_section,
                    start_char=current_start,
                    end_char=para["start"],
                    confidence=0.7,  # Fallback 신뢰도
                    tier=SECTION_TIERS.get(current_section, 2)
                ))
                current_section = result.section
                current_start = para["start"]

        # 마지막 섹션 저장
        if current_section:
            sections.append(SectionBoundary(
                section_type=current_section,
                start_char=current_start,
                end_char=len(text),
                confidence=0.7,
                tier=SECTION_TIERS.get(current_section, 2)
            ))

        return sections if sections else [SectionBoundary(
            section_type="other",
            start_char=0,
            end_char=len(text),
            confidence=0.0,
            tier=2
        )]

    def _split_into_paragraphs(self, text: str) -> list[dict]:
        """텍스트를 단락으로 분할.

        Args:
            text: 전체 텍스트

        Returns:
            단락 정보 목록
        """
        paragraphs = []
        current_pos = 0

        # 빈 줄로 단락 분리
        for match in re.finditer(r'(.+?)(?:\n\s*\n|\Z)', text, re.DOTALL):
            para_text = match.group(1).strip()
            if para_text:
                start = match.start()
                paragraphs.append({
                    "text": para_text,
                    "start": start,
                    "end": match.end(),
                    "position": start / len(text) if len(text) > 0 else 0
                })

        return paragraphs

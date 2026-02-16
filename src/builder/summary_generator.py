"""Summary Generator (v1.0).

Generate comprehensive English summaries (700+ words) for all document types.
Validates quality and enhances if necessary.

Usage:
    generator = SummaryGenerator()

    # Generate summary
    summary = await generator.generate(
        text="Full document text...",
        document_type=DocumentType.JOURNAL_ARTICLE,
        tables_figures="Table 1: Results..."
    )

    print(summary.text)        # Full summary text
    print(summary.word_count)  # Actual word count
    print(summary.sections)    # Section breakdown

    # Validate existing summary
    quality = await generator.validate(summary_text)
    if not quality.is_valid():
        enhanced = await generator.enhance(summary_text, quality, original_text)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from .document_type_detector import DocumentType
from llm import LLMClient, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ContentSummary:
    """문서 요약 결과.

    Attributes:
        text: 전체 요약 텍스트 (700+ words)
        word_count: 실제 단어 수
        language: 언어 코드 (항상 "en")
        sections: 섹션별 텍스트 (선택적)
    """

    text: str
    word_count: int
    language: str = "en"
    sections: dict[str, str] = field(default_factory=dict)


@dataclass
class SummaryQuality:
    """요약 품질 메트릭.

    Validates that summary meets minimum requirements:
    - Word count >= 700
    - Contains required sections
    - Language is English

    Attributes:
        word_count: 실제 단어 수
        has_background: Background/Context 섹션 존재
        has_methodology: Methodology 섹션 존재 (연구 문서)
        has_key_findings: Key Findings 섹션 존재
        has_conclusions: Conclusions 섹션 존재
        language_detected: 감지된 언어
    """

    word_count: int
    has_background: bool
    has_methodology: bool
    has_key_findings: bool
    has_conclusions: bool
    language_detected: str

    def is_valid(self, min_words: int = 700, require_methodology: bool = False) -> bool:
        """요약이 최소 요구사항을 충족하는지 확인.

        Args:
            min_words: 최소 단어 수 (기본값: 700)
            require_methodology: Methodology 섹션 필수 여부

        Returns:
            True if summary meets all requirements
        """
        if self.word_count < min_words:
            return False

        if not self.has_background:
            return False

        if not self.has_key_findings:
            return False

        if not self.has_conclusions:
            return False

        if require_methodology and not self.has_methodology:
            return False

        if self.language_detected != "en":
            return False

        return True


# =============================================================================
# Summary Generator
# =============================================================================

class SummaryGenerator:
    """문서 요약 생성기 (v1.0).

    Generates comprehensive English summaries with 4 sections:
    1. Background/Context (150-200 words)
    2. Methodology (150-200 words, if applicable)
    3. Key Findings/Main Content (250-350 words)
    4. Conclusions/Takeaways (100-150 words)

    Minimum 700 words, no maximum limit.
    Non-English sources automatically translated to English.
    """

    MIN_WORDS = 700

    # 섹션 키워드 (검증용)
    BACKGROUND_KEYWORDS = [
        "background", "context", "introduction", "overview",
        "about", "purpose", "problem", "question"
    ]

    METHODOLOGY_KEYWORDS = [
        "method", "approach", "design", "procedure", "technique",
        "conducted", "performed", "study", "trial", "analysis"
    ]

    KEY_FINDINGS_KEYWORDS = [
        "finding", "result", "observation", "outcome", "data",
        "showed", "demonstrated", "revealed", "indicated", "significant"
    ]

    CONCLUSIONS_KEYWORDS = [
        "conclusion", "implication", "takeaway", "suggest", "recommend",
        "limitation", "future", "summary", "overall"
    ]

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """Initialize summary generator.

        Args:
            llm_client: LLM client (defaults to Claude Haiku 4.5)
        """
        self.llm = llm_client or LLMClient(
            config=LLMConfig(
                temperature=0.2,  # Slightly higher for natural language
                max_tokens=4000   # Allow long summaries
            )
        )

    async def generate(
        self,
        text: str,
        document_type: DocumentType,
        tables_figures: Optional[str] = None,
        source_language: str = "en"
    ) -> ContentSummary:
        """문서 요약 생성 (700+ words, English).

        Args:
            text: 문서 전체 텍스트
            document_type: 문서 유형
            tables_figures: 표/그림 텍스트 (선택적)
            source_language: 원본 언어 (기본값: "en")

        Returns:
            ContentSummary with text, word_count, sections

        Raises:
            ValueError: If text is empty
            RuntimeError: If LLM generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # 프롬프트 생성
        prompt = self._build_prompt(
            text=text,
            document_type=document_type,
            tables_figures=tables_figures,
            source_language=source_language
        )

        try:
            # LLM 호출
            logger.info(f"Generating summary for {document_type.value}")
            response = await self.llm.generate(
                prompt=prompt,
                system=self._get_system_prompt()
            )
            summary_text = response.text if hasattr(response, 'text') else str(response)

            # 검증
            quality = await self.validate(summary_text)
            logger.info(
                f"Initial summary quality: {quality.word_count} words, "
                f"valid={quality.is_valid()}"
            )

            # 품질이 부족하면 개선
            if not quality.is_valid(min_words=self.MIN_WORDS):
                logger.warning("Summary quality insufficient, enhancing...")
                summary_text = await self.enhance(
                    summary=summary_text,
                    quality=quality,
                    original_text=text,
                    document_type=document_type,
                    tables_figures=tables_figures
                )
                quality = await self.validate(summary_text)
                logger.info(f"Enhanced summary: {quality.word_count} words")

            # 섹션 추출
            sections = self._extract_sections(summary_text)

            return ContentSummary(
                text=summary_text.strip(),
                word_count=quality.word_count,
                language="en",
                sections=sections
            )

        except Exception as e:
            logger.error(f"Summary generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to generate summary: {e}") from e

    async def validate(self, summary: str) -> SummaryQuality:
        """요약 품질 검증.

        Args:
            summary: 요약 텍스트

        Returns:
            SummaryQuality with validation results
        """
        # 단어 수 계산
        word_count = len(summary.split())

        # 소문자 변환 (검증용)
        summary_lower = summary.lower()

        # 섹션 존재 확인
        has_background = any(
            keyword in summary_lower
            for keyword in self.BACKGROUND_KEYWORDS
        )

        has_methodology = any(
            keyword in summary_lower
            for keyword in self.METHODOLOGY_KEYWORDS
        )

        has_key_findings = any(
            keyword in summary_lower
            for keyword in self.KEY_FINDINGS_KEYWORDS
        )

        has_conclusions = any(
            keyword in summary_lower
            for keyword in self.CONCLUSIONS_KEYWORDS
        )

        # 언어 감지 (간단한 휴리스틱)
        language_detected = self._detect_language(summary)

        return SummaryQuality(
            word_count=word_count,
            has_background=has_background,
            has_methodology=has_methodology,
            has_key_findings=has_key_findings,
            has_conclusions=has_conclusions,
            language_detected=language_detected
        )

    async def enhance(
        self,
        summary: str,
        quality: SummaryQuality,
        original_text: str,
        document_type: Optional[DocumentType] = None,
        tables_figures: Optional[str] = None
    ) -> str:
        """요약 품질 개선.

        Args:
            summary: 원본 요약
            quality: 품질 메트릭
            original_text: 원본 문서 텍스트
            document_type: 문서 유형 (선택적)
            tables_figures: 표/그림 텍스트 (선택적)

        Returns:
            Enhanced summary text
        """
        # 개선 필요 사항 확인
        issues = []

        if quality.word_count < self.MIN_WORDS:
            issues.append(
                f"Summary is too brief ({quality.word_count} words, need {self.MIN_WORDS}+)"
            )

        if not quality.has_background:
            issues.append("Missing Background/Context section")

        if not quality.has_key_findings:
            issues.append("Missing Key Findings section")

        if not quality.has_conclusions:
            issues.append("Missing Conclusions section")

        if quality.language_detected != "en":
            issues.append("Summary is not in English")

        if not issues:
            return summary  # 개선 불필요

        # 개선 프롬프트
        enhancement_prompt = self._build_enhancement_prompt(
            summary=summary,
            issues=issues,
            original_text=original_text,
            tables_figures=tables_figures
        )

        try:
            response = await self.llm.generate(
                prompt=enhancement_prompt,
                system=self._get_system_prompt()
            )
            enhanced = response.text if hasattr(response, 'text') else str(response)

            return enhanced.strip()

        except Exception as e:
            logger.error(f"Enhancement failed: {e}", exc_info=True)
            # 원본 반환 (실패 시)
            return summary

    def _build_prompt(
        self,
        text: str,
        document_type: DocumentType,
        tables_figures: Optional[str],
        source_language: str
    ) -> str:
        """요약 생성 프롬프트 구성."""

        # 언어 안내
        if source_language != "en":
            language_instruction = (
                f"\nNOTE: The source document is in {source_language}. "
                "Please translate and summarize in English."
            )
        else:
            language_instruction = ""

        # 표/그림 섹션
        if tables_figures:
            tables_section = f"\n\nTABLES AND FIGURES:\n{tables_figures}"
        else:
            tables_section = ""

        prompt = f"""Generate a comprehensive English summary of the following {document_type.value}.

REQUIREMENTS:
- Minimum length: {self.MIN_WORDS} words (no maximum limit)
- Language: English (translate if necessary)
- Include all key information from tables, figures, and data
- Maintain technical accuracy and preserve important details{language_instruction}

STRUCTURE:
1. Background/Context (150-200 words):
   - What is this document about?
   - Why was it created?
   - What problem or question does it address?

2. Methodology (150-200 words, if applicable):
   - How was the work conducted?
   - What methods, approaches, or frameworks were used?
   - Study design, sample characteristics, data sources

3. Key Findings/Main Content (250-350 words):
   - What are the most important results or points?
   - Include specific data, statistics, measurements
   - Describe main arguments, claims, or observations
   - Summarize key tables and figures

4. Conclusions/Takeaways (100-150 words):
   - What should readers remember from this work?
   - What are the implications or recommendations?
   - Are there limitations or future directions mentioned?

DOCUMENT TYPE: {document_type.value}

DOCUMENT CONTENT:
{text}{tables_section}

---
Generate the summary below:"""

        return prompt

    def _build_enhancement_prompt(
        self,
        summary: str,
        issues: list[str],
        original_text: str,
        tables_figures: Optional[str]
    ) -> str:
        """개선 프롬프트 구성."""

        issues_text = "\n".join(f"- {issue}" for issue in issues)

        tables_section = ""
        if tables_figures:
            tables_section = f"\n\nREFERENCE - TABLES AND FIGURES:\n{tables_figures}"

        prompt = f"""The following summary needs improvement.

ISSUES IDENTIFIED:
{issues_text}

CURRENT SUMMARY:
{summary}

REFERENCE - ORIGINAL DOCUMENT:
{original_text[:2000]}...{tables_section}

Please enhance the summary by:
1. Adding more specific details from the original document
2. Including additional data, statistics, or examples
3. Providing deeper explanation of methodology or findings
4. Adding more context about implications and limitations
5. Ensuring all required sections are present and well-developed

Generate the enhanced summary (minimum {self.MIN_WORDS} words):"""

        return prompt

    def _get_system_prompt(self) -> str:
        """시스템 프롬프트."""
        return (
            "You are a professional medical research analyst specialized in "
            "creating comprehensive, accurate summaries of scientific documents. "
            "Write in clear, professional English suitable for academic audiences. "
            "Preserve technical terminology and important details."
        )

    def _detect_language(self, text: str) -> str:
        """언어 감지 (간단한 휴리스틱).

        Args:
            text: 텍스트

        Returns:
            Language code ("en", "ko", etc.)
        """
        # 한글 문자 비율 확인
        korean_chars = len(re.findall(r'[가-힣]', text))
        total_chars = len(re.findall(r'[가-힣a-zA-Z]', text))

        if total_chars > 0 and korean_chars / total_chars > 0.3:
            return "ko"

        # 기본값: 영어
        return "en"

    def _extract_sections(self, summary: str) -> dict[str, str]:
        """요약에서 섹션 추출.

        Args:
            summary: 요약 텍스트

        Returns:
            Dict mapping section name to text
        """
        sections = {}

        # 섹션 헤더 패턴
        section_patterns = [
            (r'(?:^|\n)(?:1\.\s*)?(?:Background|Context).*?:?\n(.*?)(?=\n(?:2\.|Methodology|Key Findings|Conclusions|\Z))', 'background'),
            (r'(?:^|\n)(?:2\.\s*)?(?:Methodology|Methods).*?:?\n(.*?)(?=\n(?:3\.|Key Findings|Results|Conclusions|\Z))', 'methodology'),
            (r'(?:^|\n)(?:3\.\s*)?(?:Key Findings|Main Content|Results).*?:?\n(.*?)(?=\n(?:4\.|Conclusions|\Z))', 'key_findings'),
            (r'(?:^|\n)(?:4\.\s*)?(?:Conclusions|Takeaways).*?:?\n(.*?)$', 'conclusions'),
        ]

        for pattern, section_name in section_patterns:
            match = re.search(pattern, summary, re.IGNORECASE | re.DOTALL)
            if match:
                sections[section_name] = match.group(1).strip()

        return sections


# =============================================================================
# Convenience Functions
# =============================================================================

async def generate_summary(
    text: str,
    document_type: DocumentType,
    tables_figures: Optional[str] = None,
    llm_client: Optional[LLMClient] = None
) -> ContentSummary:
    """편의 함수: 문서 요약 생성.

    Args:
        text: 문서 텍스트
        document_type: 문서 유형
        tables_figures: 표/그림 텍스트
        llm_client: LLM 클라이언트

    Returns:
        ContentSummary
    """
    generator = SummaryGenerator(llm_client=llm_client)
    return await generator.generate(
        text=text,
        document_type=document_type,
        tables_figures=tables_figures
    )


async def validate_summary(summary: str) -> SummaryQuality:
    """편의 함수: 요약 품질 검증.

    Args:
        summary: 요약 텍스트

    Returns:
        SummaryQuality
    """
    generator = SummaryGenerator()
    return await generator.validate(summary)

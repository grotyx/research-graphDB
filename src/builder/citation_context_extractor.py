"""Citation Context Extractor Module.

논문에서 중요한 인용(결과를 지지하거나 반박하는 선행 연구)을 LLM을 사용해 추출합니다.

주요 기능:
1. Discussion/Results 섹션에서 인용 추출
2. 인용의 컨텍스트 분석 (supports_result, contradicts_result, etc.)
3. 인용된 논문의 메타데이터 추출 (저자, 연도, 제목)

환경변수:
- LLM_PROVIDER: "claude" (기본값) 또는 "gemini"
- ANTHROPIC_API_KEY: Claude API 키 (Claude 사용 시)
- GEMINI_API_KEY: Gemini API 키 (Gemini 사용 시)

v3.2+ Important Citation Extraction Feature
v3.2.1 Claude/Gemini 듀얼 프로바이더 지원
"""

import re
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================

class LLMProvider(Enum):
    """LLM 제공자."""
    CLAUDE = "claude"
    GEMINI = "gemini"


class CitationImportance(Enum):
    """인용 중요도."""
    HIGH = "high"  # 결과를 직접 지지/반박
    MEDIUM = "medium"  # 비교 대상
    LOW = "low"  # 배경/방법론


@dataclass
class ExtractedCitation:
    """추출된 인용 정보.

    Attributes:
        authors: 저자 목록 (예: ["Kim", "Park", "Lee"])
        year: 발행 연도
        title: 논문 제목 (추출 가능한 경우)
        journal: 저널명 (추출 가능한 경우)
        context: 인용 컨텍스트 (supports_result, contradicts_result, etc.)
        section: 인용이 등장한 섹션
        citation_text: 인용이 포함된 문장 원문
        importance_reason: 왜 중요한 인용인지 설명
        outcome_comparison: 비교 대상 결과변수
        direction_match: 결과 방향 일치 여부 (True=지지, False=반박, None=불명확)
        confidence: 추출 신뢰도 (0.0-1.0)
        raw_citation: 원본 인용 텍스트 (예: "Kim et al., 2023")
    """
    authors: list[str] = field(default_factory=list)
    year: int = 0
    title: str = ""
    journal: str = ""
    context: str = "background"  # supports_result, contradicts_result, methodological, background, comparison
    section: str = ""
    citation_text: str = ""
    importance_reason: str = ""
    outcome_comparison: str = ""
    direction_match: Optional[bool] = None
    confidence: float = 0.0
    raw_citation: str = ""


@dataclass
class CitationExtractionResult:
    """인용 추출 결과.

    Attributes:
        paper_title: 원본 논문 제목
        important_citations: 중요한 인용 목록 (supports/contradicts)
        all_citations: 모든 추출된 인용 목록
        main_findings: 논문의 주요 발견사항 (인용 비교용)
        extraction_stats: 추출 통계
        provider_used: 사용된 LLM 프로바이더
    """
    paper_title: str = ""
    important_citations: list[ExtractedCitation] = field(default_factory=list)
    all_citations: list[ExtractedCitation] = field(default_factory=list)
    main_findings: list[str] = field(default_factory=list)
    extraction_stats: dict = field(default_factory=dict)
    provider_used: str = ""


# =============================================================================
# Shared Prompt
# =============================================================================

EXTRACTION_PROMPT = """당신은 의학 논문 분석 전문가입니다.
아래 논문의 Discussion/Results 섹션에서 **중요한 인용**을 추출해주세요.

## 중요한 인용의 정의
1. **supports_result**: 본 연구의 결과를 지지하는 선행 연구
   - "Our findings are consistent with Kim et al. (2023)..."
   - "Similar results were reported by Park et al..."

2. **contradicts_result**: 본 연구의 결과와 상반되는 선행 연구
   - "In contrast to Lee et al. (2022), we found..."
   - "Unlike previous studies by Chen et al..."

3. **comparison**: 직접 비교 대상으로 언급된 연구
   - "Compared to the results of Smith et al..."
   - "Our complication rate was lower than that reported by..."

4. **methodological**: 방법론적으로 참고한 중요 연구 (선택적)
   - "We adopted the technique described by..."

## 논문의 주요 발견사항
{main_findings}

## Discussion 섹션
{discussion_text}

## Results 섹션
{results_text}

## 추출 지침
1. 배경 설명용 인용(Background)은 제외하고 결과와 직접 관련된 인용만 추출
2. 각 인용에 대해:
   - 원본 인용 텍스트 (예: "Kim et al., 2023")
   - 저자명과 연도
   - 인용 컨텍스트 (supports_result, contradicts_result, comparison, methodological)
   - 인용이 포함된 문장 전체
   - 왜 중요한 인용인지 설명
   - 비교 대상 결과변수 (VAS, ODI, Fusion Rate 등)
   - 결과 방향 일치 여부
3. 신뢰도는 인용 정보의 명확성에 따라 0.0-1.0로 설정

JSON 형식으로 응답해주세요."""

# JSON Schema for structured output
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "important_citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_citation": {
                        "type": "string",
                        "description": "원본 인용 텍스트 (예: 'Kim et al., 2023' 또는 '[15]')"
                    },
                    "authors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "저자 성씨 목록"
                    },
                    "year": {
                        "type": "integer",
                        "description": "발행 연도"
                    },
                    "title": {
                        "type": "string",
                        "description": "논문 제목 (본문에서 언급된 경우)"
                    },
                    "context": {
                        "type": "string",
                        "enum": ["supports_result", "contradicts_result", "comparison", "methodological"],
                        "description": "인용 컨텍스트 유형"
                    },
                    "section": {
                        "type": "string",
                        "description": "인용이 등장한 섹션 (discussion, results, introduction)"
                    },
                    "citation_text": {
                        "type": "string",
                        "description": "인용이 포함된 문장 전체"
                    },
                    "importance_reason": {
                        "type": "string",
                        "description": "왜 이 인용이 중요한지 간단히 설명"
                    },
                    "outcome_comparison": {
                        "type": "string",
                        "description": "비교 대상 결과변수 (예: VAS, ODI, Fusion Rate)"
                    },
                    "direction_match": {
                        "type": "boolean",
                        "description": "결과 방향 일치 여부 (지지=true, 반박=false)"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "추출 신뢰도 (0.0-1.0)"
                    }
                },
                "required": ["raw_citation", "context", "citation_text", "confidence"]
            }
        },
        "main_findings_detected": {
            "type": "array",
            "items": {"type": "string"},
            "description": "논문의 주요 발견사항 목록"
        }
    },
    "required": ["important_citations"]
}

# Gemini용 대문자 스키마 (Gemini API 요구사항)
GEMINI_EXTRACTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "important_citations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "raw_citation": {
                        "type": "STRING",
                        "description": "원본 인용 텍스트 (예: 'Kim et al., 2023' 또는 '[15]')"
                    },
                    "authors": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "description": "저자 성씨 목록"
                    },
                    "year": {
                        "type": "INTEGER",
                        "description": "발행 연도"
                    },
                    "title": {
                        "type": "STRING",
                        "description": "논문 제목 (본문에서 언급된 경우)"
                    },
                    "context": {
                        "type": "STRING",
                        "enum": ["supports_result", "contradicts_result", "comparison", "methodological"],
                        "description": "인용 컨텍스트 유형"
                    },
                    "section": {
                        "type": "STRING",
                        "description": "인용이 등장한 섹션 (discussion, results, introduction)"
                    },
                    "citation_text": {
                        "type": "STRING",
                        "description": "인용이 포함된 문장 전체"
                    },
                    "importance_reason": {
                        "type": "STRING",
                        "description": "왜 이 인용이 중요한지 간단히 설명"
                    },
                    "outcome_comparison": {
                        "type": "STRING",
                        "description": "비교 대상 결과변수 (예: VAS, ODI, Fusion Rate)"
                    },
                    "direction_match": {
                        "type": "BOOLEAN",
                        "description": "결과 방향 일치 여부 (지지=true, 반박=false)"
                    },
                    "confidence": {
                        "type": "NUMBER",
                        "description": "추출 신뢰도 (0.0-1.0)"
                    }
                },
                "required": ["raw_citation", "context", "citation_text", "confidence"]
            }
        },
        "main_findings_detected": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "논문의 주요 발견사항 목록"
        }
    },
    "required": ["important_citations"]
}


# =============================================================================
# Claude Backend
# =============================================================================

class ClaudeBackend:
    """Claude 인용 추출 백엔드."""

    def __init__(self, model: Optional[str] = None):
        import anthropic

        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.model = model or os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        self.client = anthropic.Anthropic(api_key=self.api_key)

        logger.info(f"Claude citation backend initialized: model={self.model}")

    async def extract_citations(self, prompt: str) -> dict[str, Any]:
        """텍스트에서 인용 추출.

        Args:
            prompt: 추출 프롬프트 (Discussion/Results 텍스트 포함)

        Returns:
            추출 결과 딕셔너리
        """
        import asyncio
        import time

        start_time = time.time()

        try:
            # Claude는 동기 API이므로 executor에서 실행
            loop = asyncio.get_event_loop()

            def _call_api():
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=32768,  # Claude 4.5는 최대 64K 지원
                    messages=[
                        {
                            "role": "user",
                            "content": prompt + "\n\nJSON 형식으로만 응답해주세요."
                        }
                    ],
                )

            message = await loop.run_in_executor(None, _call_api)

            latency = time.time() - start_time

            # 응답 파싱
            text = message.content[0].text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())

            return {
                "success": True,
                "data": data,
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "latency": latency,
                "model_used": self.model,
            }

        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON parsing error: {e}",
                "latency": time.time() - start_time,
                "model_used": self.model,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "latency": time.time() - start_time,
                "model_used": self.model,
            }


# =============================================================================
# Gemini Backend
# =============================================================================

class GeminiBackend:
    """Gemini 인용 추출 백엔드."""

    def __init__(self, model: Optional[str] = None):
        from google import genai

        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20")
        self.client = genai.Client(api_key=self.api_key)

        logger.info(f"Gemini citation backend initialized: model={self.model}")

    async def extract_citations(self, prompt: str) -> dict[str, Any]:
        """텍스트에서 인용 추출.

        Args:
            prompt: 추출 프롬프트 (Discussion/Results 텍스트 포함)

        Returns:
            추출 결과 딕셔너리
        """
        import time
        from google.genai.types import GenerateContentConfig, Part

        start_time = time.time()

        try:
            config = GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GEMINI_EXTRACTION_SCHEMA,
                temperature=0.1
            )

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[Part.from_text(prompt)],
                config=config
            )

            latency = time.time() - start_time

            # Parse response
            response_text = response.text.strip()
            data = json.loads(response_text)

            # 토큰 사용량 추출 (Gemini API에서 제공되는 경우)
            input_tokens = 0
            output_tokens = 0
            if hasattr(response, 'usage_metadata'):
                input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)

            return {
                "success": True,
                "data": data,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency": latency,
                "model_used": self.model,
            }

        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"JSON parsing error: {e}",
                "latency": time.time() - start_time,
                "model_used": self.model,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "latency": time.time() - start_time,
                "model_used": self.model,
            }


# =============================================================================
# Citation Context Extractor (Unified)
# =============================================================================

class CitationContextExtractor:
    """논문에서 중요한 인용을 추출하는 모듈.

    LLM(Claude 또는 Gemini)을 사용하여 Discussion/Results 섹션에서
    논문 결과를 지지하거나 반박하는 중요한 인용을 식별합니다.

    환경변수:
        LLM_PROVIDER: "claude" (기본값) 또는 "gemini"
        ANTHROPIC_API_KEY: Claude API 키
        GEMINI_API_KEY: Gemini API 키

    Example:
        ```python
        # 환경변수 기반 자동 선택
        extractor = CitationContextExtractor()
        result = await extractor.extract_important_citations(
            discussion_text="Our findings are consistent with Kim et al. (2023)...",
            results_text="VAS improved from 7.2 to 2.1...",
            main_findings=["UBE showed better outcomes than open surgery"]
        )
        for citation in result.important_citations:
            print(f"{citation.raw_citation}: {citation.context}")

        # 특정 provider 지정
        extractor = CitationContextExtractor(provider="gemini")
        ```
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,  # 레거시 호환성
    ):
        """Initialize the extractor.

        Args:
            provider: LLM 제공자 ("claude" 또는 "gemini"). None이면 환경변수 사용.
            model: 모델 ID. None이면 환경변수 사용.
            api_key: API 키 (레거시 호환성, 사용 권장하지 않음)
        """
        # Provider 결정
        provider_str = provider or os.getenv("LLM_PROVIDER", "claude")
        self.provider = LLMProvider(provider_str.lower())

        # 레거시 호환성: api_key가 직접 전달된 경우 Gemini로 설정
        if api_key and not provider:
            self.provider = LLMProvider.GEMINI
            os.environ["GEMINI_API_KEY"] = api_key

        # Backend 초기화
        if self.provider == LLMProvider.CLAUDE:
            self._backend = ClaudeBackend(model=model)
        else:
            self._backend = GeminiBackend(model=model)

        self.model = self._backend.model

        logger.info(
            f"CitationContextExtractor initialized: provider={self.provider.value}, "
            f"model={self.model}"
        )

    async def extract_important_citations(
        self,
        discussion_text: str,
        results_text: str = "",
        main_findings: Optional[list[str]] = None,
        paper_title: str = ""
    ) -> CitationExtractionResult:
        """논문에서 중요한 인용을 추출합니다.

        Args:
            discussion_text: Discussion 섹션 텍스트
            results_text: Results 섹션 텍스트 (선택)
            main_findings: 논문의 주요 발견사항 목록
            paper_title: 논문 제목 (로깅용)

        Returns:
            CitationExtractionResult: 추출된 인용 정보
        """
        result = CitationExtractionResult(
            paper_title=paper_title,
            provider_used=self.provider.value
        )

        if not discussion_text and not results_text:
            logger.warning("No discussion or results text provided")
            return result

        # 주요 발견사항 포맷
        findings_str = "\n".join(f"- {f}" for f in (main_findings or [])) or "제공되지 않음"

        # 프롬프트 구성
        prompt = EXTRACTION_PROMPT.format(
            main_findings=findings_str,
            discussion_text=discussion_text[:8000] if discussion_text else "없음",
            results_text=results_text[:4000] if results_text else "없음"
        )

        try:
            # Backend 호출
            response = await self._backend.extract_citations(prompt)

            if not response.get("success"):
                logger.error(f"Citation extraction failed: {response.get('error')}")
                return result

            data = response.get("data", {})

            # Extract citations
            for citation_data in data.get("important_citations", []):
                citation = ExtractedCitation(
                    raw_citation=citation_data.get("raw_citation", ""),
                    authors=citation_data.get("authors", []),
                    year=citation_data.get("year", 0),
                    title=citation_data.get("title", ""),
                    context=citation_data.get("context", "background"),
                    section=citation_data.get("section", ""),
                    citation_text=citation_data.get("citation_text", ""),
                    importance_reason=citation_data.get("importance_reason", ""),
                    outcome_comparison=citation_data.get("outcome_comparison", ""),
                    direction_match=citation_data.get("direction_match"),
                    confidence=citation_data.get("confidence", 0.5)
                )

                # Add to important citations if supports/contradicts
                if citation.context in ["supports_result", "contradicts_result", "comparison"]:
                    result.important_citations.append(citation)

                result.all_citations.append(citation)

            # Extract main findings
            result.main_findings = data.get("main_findings_detected", main_findings or [])

            # Stats
            result.extraction_stats = {
                "total_citations": len(result.all_citations),
                "important_citations": len(result.important_citations),
                "supports_count": len([c for c in result.important_citations if c.context == "supports_result"]),
                "contradicts_count": len([c for c in result.important_citations if c.context == "contradicts_result"]),
                "comparison_count": len([c for c in result.important_citations if c.context == "comparison"]),
                "provider": self.provider.value,
                "model": response.get("model_used", self.model),
                "latency_seconds": response.get("latency", 0),
                "input_tokens": response.get("input_tokens", 0),
                "output_tokens": response.get("output_tokens", 0),
            }

            logger.info(
                f"Extracted {len(result.important_citations)} important citations "
                f"from '{paper_title[:50]}...' using {self.provider.value}"
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
        except Exception as e:
            logger.error(f"Citation extraction error: {e}")

        return result

    async def extract_from_chunks(
        self,
        chunks: list[dict],
        main_findings: Optional[list[str]] = None,
        paper_title: str = ""
    ) -> CitationExtractionResult:
        """ExtractedChunk 목록에서 중요한 인용을 추출합니다.

        Args:
            chunks: ExtractedChunk 딕셔너리 목록
            main_findings: 논문의 주요 발견사항 목록
            paper_title: 논문 제목

        Returns:
            CitationExtractionResult: 추출된 인용 정보
        """
        # Discussion과 Results 섹션 텍스트 추출
        discussion_text = ""
        results_text = ""

        for chunk in chunks:
            section = chunk.get("section", "").lower()
            content = chunk.get("content", "")

            if "discussion" in section:
                discussion_text += content + "\n"
            elif "result" in section:
                results_text += content + "\n"
            elif "conclusion" in section:
                # Conclusion도 Discussion에 포함
                discussion_text += content + "\n"

        return await self.extract_important_citations(
            discussion_text=discussion_text,
            results_text=results_text,
            main_findings=main_findings,
            paper_title=paper_title
        )

    def parse_citation_reference(self, raw_citation: str) -> dict:
        """원본 인용 텍스트에서 저자와 연도를 파싱합니다.

        Args:
            raw_citation: 원본 인용 텍스트 (예: "Kim et al., 2023")

        Returns:
            dict: {"authors": [...], "year": int}
        """
        result = {"authors": [], "year": 0}

        # Pattern: Author et al., Year
        et_al_pattern = r"([A-Z][a-z]+)\s+et\s+al\.?,?\s*\(?(\d{4})\)?"
        match = re.search(et_al_pattern, raw_citation)
        if match:
            result["authors"] = [match.group(1)]
            result["year"] = int(match.group(2))
            return result

        # Pattern: Author and Author, Year
        two_author_pattern = r"([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+),?\s*\(?(\d{4})\)?"
        match = re.search(two_author_pattern, raw_citation)
        if match:
            result["authors"] = [match.group(1), match.group(2)]
            result["year"] = int(match.group(3))
            return result

        # Pattern: Single Author (Year)
        single_pattern = r"([A-Z][a-z]+)\s*\((\d{4})\)"
        match = re.search(single_pattern, raw_citation)
        if match:
            result["authors"] = [match.group(1)]
            result["year"] = int(match.group(2))
            return result

        # Fallback: just extract year
        year_pattern = r"(\d{4})"
        match = re.search(year_pattern, raw_citation)
        if match:
            result["year"] = int(match.group(1))

        return result

    def build_pubmed_query(self, citation: ExtractedCitation) -> str:
        """PubMed 검색 쿼리를 생성합니다.

        Args:
            citation: 추출된 인용 정보

        Returns:
            str: PubMed 검색 쿼리
        """
        parts = []

        # 제목이 있으면 제목으로 검색
        if citation.title:
            return f'"{citation.title}"[Title]'

        # 저자명으로 검색
        if citation.authors:
            first_author = citation.authors[0]
            parts.append(f"{first_author}[Author]")

        # 연도로 검색
        if citation.year:
            parts.append(f"{citation.year}[Date - Publication]")

        return " AND ".join(parts) if parts else ""

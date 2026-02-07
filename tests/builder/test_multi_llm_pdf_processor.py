#!/usr/bin/env python3
"""Multi-LLM PDF Processor Test.

Claude, Gemini, OpenAI GPT를 사용하여 PDF 논문을 분석하고 결과를 비교합니다.
모든 LLM은 동일한 프롬프트와 출력 형식을 사용합니다.

환경변수:
    ANTHROPIC_API_KEY: Claude API 키
    GEMINI_API_KEY: Gemini API 키
    OPENAI_API_KEY: OpenAI API 키

Usage:
    # 특정 LLM으로 테스트
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --provider claude-haiku
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --provider claude-sonnet
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --provider gemini-flash
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --provider gemini-pro
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --provider openai

    # 모든 LLM 비교 테스트 (claude-haiku, claude-sonnet, gemini-flash, gemini-pro, openai)
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --compare

    # 특정 모델 지정
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --provider openai --model gpt-4o-mini

    # 결과를 JSON 파일로 저장
    python test_multi_llm_pdf_processor.py /path/to/paper.pdf --compare --output results.json
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes (동일한 출력 형식)
# =============================================================================

@dataclass
class ProcessorResult:
    """PDF 처리 결과."""
    success: bool
    provider: str = ""
    model: str = ""
    extracted_data: dict = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0
    error: Optional[str] = None
    cost_usd: float = 0.0


@dataclass
class ComparisonResult:
    """LLM 비교 결과."""
    pdf_path: str
    timestamp: str
    results: dict = field(default_factory=dict)  # provider -> ProcessorResult
    summary: dict = field(default_factory=dict)


# =============================================================================
# 공통 추출 프롬프트
# =============================================================================

EXTRACTION_PROMPT = """You are a medical research paper analyst specializing in spine surgery literature.
Analyze this PDF and extract the following information in JSON format:

{
  "metadata": {
    "title": "Paper title",
    "authors": ["Author 1", "Author 2"],
    "year": 2024,
    "journal": "Journal name",
    "doi": "",
    "pmid": "",
    "study_type": "RCT/Cohort/Case-control/Case series/Meta-analysis/Review",
    "study_design": "randomized/non-randomized/single-arm/multi-arm",
    "evidence_level": "1a/1b/2a/2b/3/4/5",
    "sample_size": 100,
    "centers": "single-center/multi-center",
    "blinding": "none/single-blind/double-blind/open-label"
  },
  "spine_metadata": {
    "sub_domain": "Degenerative/Deformity/Trauma/Tumor/Infection/Basic Science",
    "anatomy_level": "L4-5",
    "anatomy_region": "cervical/thoracic/lumbar/sacral",
    "pathology": ["Disease 1", "Disease 2"],
    "interventions": ["Surgery 1", "Surgery 2"],
    "comparison_type": "vs_conventional/vs_other_mis/vs_conservative/single_arm",
    "follow_up_months": 24,
    "main_conclusion": "Brief conclusion",
    "outcomes": [
      {
        "name": "VAS",
        "category": "pain/function/radiologic/complication/satisfaction",
        "baseline": 7.2,
        "final": 2.1,
        "value_intervention": "2.1 ± 0.8",
        "value_control": "3.5 ± 1.2",
        "value_difference": "-1.4",
        "p_value": "0.001",
        "confidence_interval": "95% CI: -2.1 to -0.7",
        "effect_size": "Cohen's d = 0.8",
        "timepoint": "preop/postop/1mo/3mo/6mo/1yr/2yr/final",
        "is_significant": true,
        "direction": "improved/worsened/unchanged"
      }
    ],
    "complications": [
      {
        "name": "Dural tear",
        "incidence_intervention": "2.5%",
        "incidence_control": "4.1%",
        "p_value": "0.35",
        "severity": "minor/major/revision_required"
      }
    ]
  },
  "important_citations": [
    {
      "authors": ["Kim", "Park"],
      "year": 2023,
      "context": "supports_result/contradicts_result/comparison",
      "section": "discussion/results/introduction",
      "citation_text": "Original sentence containing the citation",
      "importance_reason": "Why this citation is important"
    }
  ],
  "chunks": [
    {
      "content": "Chunk text content",
      "content_type": "text/table/figure/key_finding",
      "section_type": "abstract/introduction/methods/results/discussion/conclusion",
      "is_key_finding": false,
      "statistics": {
        "p_values": ["0.001"],
        "effect_sizes": ["Cohen's d = 0.8"],
        "confidence_intervals": ["95% CI: -2.1 to -0.7"]
      }
    }
  ]
}

CRITICAL INSTRUCTIONS:
1. Extract ALL statistical values exactly as written (p-values, CIs, effect sizes)
2. For EVERY outcome, extract: category, timepoint, baseline, final, value_intervention, value_control
3. Mark ALL chunks containing significant results as is_key_finding=true
4. Preserve complete table data in markdown format
5. For comparative studies, extract both intervention and control group values separately
6. For spine surgery papers, always extract: sub_domain, anatomy, pathology, interventions, outcomes
7. Classify outcomes by category: pain (VAS, NRS), function (ODI, JOA, EQ-5D), radiologic (fusion rate, lordosis), complication, satisfaction
8. Return ONLY valid JSON, no additional text

Return valid JSON following the schema above."""


# =============================================================================
# Claude Backend
# =============================================================================

class ClaudeBackend:
    """Claude PDF 처리 백엔드."""

    # 모델별 비용 (USD per 1M tokens)
    PRICING = {
        "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
        "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    }

    # 모델 별칭
    MODEL_ALIASES = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-5-20250929",
        "claude-haiku": "claude-haiku-4-5-20251001",
        "claude-sonnet": "claude-sonnet-4-5-20250929",
    }

    DEFAULT_MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, model: Optional[str] = None):
        import anthropic

        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        # 모델 별칭 해석
        model_input = model or self.DEFAULT_MODEL
        self.model = self.MODEL_ALIASES.get(model_input, model_input)
        self.client = anthropic.Anthropic(api_key=self.api_key)
        logger.info(f"Claude backend initialized: model={self.model}")

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """비용 계산."""
        pricing = self.PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        return (input_tokens / 1_000_000 * pricing["input"] +
                output_tokens / 1_000_000 * pricing["output"])

    def process_pdf(self, pdf_path: Path, prompt: str) -> ProcessorResult:
        """PDF 처리."""
        start_time = time.time()

        try:
            # PDF를 base64로 인코딩
            pdf_bytes = pdf_path.read_bytes()
            base64_data = base64.standard_b64encode(pdf_bytes).decode("utf-8")

            # API 호출
            message = self.client.messages.create(
                model=self.model,
                max_tokens=16384,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64_data,
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ],
            )

            latency = time.time() - start_time

            # 응답 파싱
            text = message.content[0].text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())

            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens

            return ProcessorResult(
                success=True,
                provider="claude",
                model=self.model,
                extracted_data=data,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
                cost_usd=self._calculate_cost(input_tokens, output_tokens),
            )

        except json.JSONDecodeError as e:
            return ProcessorResult(
                success=False,
                provider="claude",
                model=self.model,
                error=f"JSON parsing error: {e}",
                latency_seconds=time.time() - start_time,
            )
        except Exception as e:
            return ProcessorResult(
                success=False,
                provider="claude",
                model=self.model,
                error=str(e),
                latency_seconds=time.time() - start_time,
            )


# =============================================================================
# Gemini Backend
# =============================================================================

class GeminiBackend:
    """Gemini PDF 처리 백엔드."""

    # 모델별 비용 (USD per 1M tokens) - 2024년 12월 기준
    PRICING = {
        "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-3-pro-preview": {"input": 1.50, "output": 6.0},
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    }

    # 모델 별칭
    MODEL_ALIASES = {
        "flash": "gemini-2.5-flash",
        "pro": "gemini-3-pro-preview",
        "gemini-flash": "gemini-2.5-flash",
        "gemini-pro": "gemini-3-pro-preview",
    }

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, model: Optional[str] = None):
        from google import genai

        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")

        # 모델 별칭 해석
        model_input = model or self.DEFAULT_MODEL
        self.model = self.MODEL_ALIASES.get(model_input, model_input)
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"Gemini backend initialized: model={self.model}")

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """비용 계산."""
        pricing = self.PRICING.get(self.model, {"input": 0.10, "output": 0.40})
        return (input_tokens / 1_000_000 * pricing["input"] +
                output_tokens / 1_000_000 * pricing["output"])

    async def process_pdf(self, pdf_path: Path, prompt: str) -> ProcessorResult:
        """PDF 처리 (async)."""
        from google.genai import types

        start_time = time.time()

        try:
            # PDF 업로드
            loop = asyncio.get_event_loop()
            uploaded_file = await loop.run_in_executor(
                None,
                lambda: self.client.files.upload(file=pdf_path)
            )

            # API 호출
            pdf_part = types.Part.from_uri(
                file_uri=uploaded_file.uri,
                mime_type="application/pdf"
            )

            config = types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=65536,
                response_mime_type="application/json",
            )

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[pdf_part, prompt],
                config=config,
            )

            latency = time.time() - start_time

            # 파일 삭제
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self.client.files.delete(name=uploaded_file.name)
                )
            except Exception:
                pass

            # 응답 파싱
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())

            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

            return ProcessorResult(
                success=True,
                provider="gemini",
                model=self.model,
                extracted_data=data,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
                cost_usd=self._calculate_cost(input_tokens, output_tokens),
            )

        except json.JSONDecodeError as e:
            return ProcessorResult(
                success=False,
                provider="gemini",
                model=self.model,
                error=f"JSON parsing error: {e}",
                latency_seconds=time.time() - start_time,
            )
        except Exception as e:
            return ProcessorResult(
                success=False,
                provider="gemini",
                model=self.model,
                error=str(e),
                latency_seconds=time.time() - start_time,
            )


# =============================================================================
# OpenAI Backend
# =============================================================================

class OpenAIBackend:
    """OpenAI GPT PDF 처리 백엔드."""

    # 모델별 비용 (USD per 1M tokens) - 2024년 12월 기준
    PRICING = {
        "gpt-5.2-chat-latest": {"input": 5.0, "output": 15.0},  # 예상 가격
        "gpt-4o": {"input": 2.50, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "gpt-4": {"input": 30.0, "output": 60.0},
        "o1": {"input": 15.0, "output": 60.0},
        "o1-mini": {"input": 3.0, "output": 12.0},
    }

    DEFAULT_MODEL = "gpt-5.2-chat-latest"

    def __init__(self, model: Optional[str] = None):
        from openai import OpenAI

        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set")

        self.model = model or self.DEFAULT_MODEL
        self.client = OpenAI(api_key=self.api_key)
        logger.info(f"OpenAI backend initialized: model={self.model}")

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """비용 계산."""
        pricing = self.PRICING.get(self.model, {"input": 2.50, "output": 10.0})
        return (input_tokens / 1_000_000 * pricing["input"] +
                output_tokens / 1_000_000 * pricing["output"])

    def process_pdf(self, pdf_path: Path, prompt: str) -> ProcessorResult:
        """PDF 처리.

        OpenAI는 PDF 직접 업로드를 지원하지 않으므로 이미지로 변환하여 처리합니다.
        """
        start_time = time.time()

        try:
            # PDF를 이미지로 변환 (pymupdf 사용)
            import fitz  # PyMuPDF

            doc = fitz.open(pdf_path)
            images = []

            # 최대 20페이지까지만 처리 (API 제한)
            max_pages = min(len(doc), 20)

            for page_num in range(max_pages):
                page = doc[page_num]
                # 200 DPI로 렌더링 (200/72 ≈ 2.78)
                pix = page.get_pixmap(matrix=fitz.Matrix(2.78, 2.78))
                img_bytes = pix.tobytes("png")
                base64_img = base64.standard_b64encode(img_bytes).decode("utf-8")
                images.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_img}",
                        "detail": "high"
                    }
                })

            doc.close()

            # API 호출
            messages = [
                {
                    "role": "user",
                    "content": images + [{"type": "text", "text": prompt}]
                }
            ]

            # 새 모델은 max_completion_tokens 사용, temperature 미지원
            is_new_model = "gpt-5" in self.model or "o1" in self.model or "o3" in self.model

            api_params = {
                "model": self.model,
                "messages": messages,
                "response_format": {"type": "json_object"},
            }

            if is_new_model:
                api_params["max_completion_tokens"] = 16384
                # gpt-5.x, o1, o3는 temperature 지원 안함
            else:
                api_params["max_tokens"] = 16384
                api_params["temperature"] = 0.1

            response = self.client.chat.completions.create(**api_params)

            latency = time.time() - start_time

            # 응답 파싱
            text = response.choices[0].message.content
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())

            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            return ProcessorResult(
                success=True,
                provider="openai",
                model=self.model,
                extracted_data=data,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
                cost_usd=self._calculate_cost(input_tokens, output_tokens),
            )

        except json.JSONDecodeError as e:
            return ProcessorResult(
                success=False,
                provider="openai",
                model=self.model,
                error=f"JSON parsing error: {e}",
                latency_seconds=time.time() - start_time,
            )
        except ImportError:
            return ProcessorResult(
                success=False,
                provider="openai",
                model=self.model,
                error="PyMuPDF (fitz) is required for OpenAI PDF processing. Install: pip install pymupdf",
                latency_seconds=time.time() - start_time,
            )
        except Exception as e:
            return ProcessorResult(
                success=False,
                provider="openai",
                model=self.model,
                error=str(e),
                latency_seconds=time.time() - start_time,
            )


# =============================================================================
# Multi-LLM Processor
# =============================================================================

class MultiLLMPDFProcessor:
    """다중 LLM PDF 처리기."""

    PROVIDERS = ["claude-haiku", "claude-sonnet", "gemini-flash", "gemini-pro", "openai"]

    def __init__(self):
        """사용 가능한 백엔드 초기화."""
        self.backends = {}

        # Claude Haiku
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                self.backends["claude-haiku"] = ClaudeBackend(model="haiku")
            except Exception as e:
                logger.warning(f"Claude Haiku backend init failed: {e}")

        # Claude Sonnet
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                self.backends["claude-sonnet"] = ClaudeBackend(model="sonnet")
            except Exception as e:
                logger.warning(f"Claude Sonnet backend init failed: {e}")

        # Gemini Flash
        if os.getenv("GEMINI_API_KEY"):
            try:
                self.backends["gemini-flash"] = GeminiBackend(model="flash")
            except Exception as e:
                logger.warning(f"Gemini Flash backend init failed: {e}")

        # Gemini Pro
        if os.getenv("GEMINI_API_KEY"):
            try:
                self.backends["gemini-pro"] = GeminiBackend(model="pro")
            except Exception as e:
                logger.warning(f"Gemini Pro backend init failed: {e}")

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                self.backends["openai"] = OpenAIBackend()
            except Exception as e:
                logger.warning(f"OpenAI backend init failed: {e}")

        logger.info(f"Available backends: {list(self.backends.keys())}")

    async def process_single(
        self,
        pdf_path: Path,
        provider: str,
        model: Optional[str] = None
    ) -> ProcessorResult:
        """단일 LLM으로 처리."""
        if provider not in self.backends:
            # 동적으로 백엔드 생성 시도
            try:
                if provider in ("claude", "claude-haiku"):
                    self.backends[provider] = ClaudeBackend(model=model or "haiku")
                elif provider == "claude-sonnet":
                    self.backends[provider] = ClaudeBackend(model=model or "sonnet")
                elif provider in ("gemini", "gemini-flash"):
                    self.backends[provider] = GeminiBackend(model=model or "flash")
                elif provider == "gemini-pro":
                    self.backends[provider] = GeminiBackend(model=model or "pro")
                elif provider == "openai":
                    self.backends["openai"] = OpenAIBackend(model=model)
                else:
                    return ProcessorResult(
                        success=False,
                        provider=provider,
                        error=f"Unknown provider: {provider}"
                    )
            except Exception as e:
                return ProcessorResult(
                    success=False,
                    provider=provider,
                    error=str(e)
                )

        backend = self.backends[provider]

        # 모델 오버라이드
        if model:
            # 별칭 해석 (Claude 또는 Gemini)
            if provider.startswith("claude"):
                resolved_model = ClaudeBackend.MODEL_ALIASES.get(model, model)
            elif provider.startswith("gemini"):
                resolved_model = GeminiBackend.MODEL_ALIASES.get(model, model)
            else:
                resolved_model = model
            backend.model = resolved_model

        if provider.startswith("gemini"):
            return await backend.process_pdf(pdf_path, EXTRACTION_PROMPT)
        else:
            # Claude, OpenAI는 동기
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: backend.process_pdf(pdf_path, EXTRACTION_PROMPT)
            )

    async def compare_all(self, pdf_path: Path) -> ComparisonResult:
        """모든 사용 가능한 LLM으로 비교 처리."""
        results = {}

        for provider in self.backends.keys():
            print(f"\n🔄 Processing with {provider}...")
            result = await self.process_single(pdf_path, provider)
            results[provider] = result

            if result.success:
                print(f"   ✅ Success: {result.latency_seconds:.2f}s, ${result.cost_usd:.4f}")
            else:
                print(f"   ❌ Failed: {result.error}")

        # 요약 생성
        summary = self._generate_summary(results)

        return ComparisonResult(
            pdf_path=str(pdf_path),
            timestamp=datetime.now().isoformat(),
            results={k: asdict(v) for k, v in results.items()},
            summary=summary,
        )

    def _generate_summary(self, results: dict[str, ProcessorResult]) -> dict:
        """비교 요약 생성."""
        successful = [r for r in results.values() if r.success]

        if not successful:
            return {"status": "all_failed"}

        summary = {
            "total_providers": len(results),
            "successful": len(successful),
            "failed": len(results) - len(successful),
            "fastest": min(successful, key=lambda x: x.latency_seconds).provider,
            "cheapest": min(successful, key=lambda x: x.cost_usd).provider,
            "comparison": {}
        }

        # 메타데이터 비교
        titles = {}
        for r in successful:
            title = r.extracted_data.get("metadata", {}).get("title", "N/A")
            titles[r.provider] = title[:80] + "..." if len(title) > 80 else title

        summary["comparison"]["titles"] = titles

        # 토큰 사용량 비교
        summary["comparison"]["tokens"] = {
            r.provider: {
                "input": r.input_tokens,
                "output": r.output_tokens,
                "total": r.input_tokens + r.output_tokens
            }
            for r in successful
        }

        # 비용 비교
        summary["comparison"]["costs"] = {
            r.provider: f"${r.cost_usd:.4f}"
            for r in successful
        }

        # 소요 시간 비교
        summary["comparison"]["latency"] = {
            r.provider: f"{r.latency_seconds:.2f}s"
            for r in successful
        }

        return summary


# =============================================================================
# Display Functions
# =============================================================================

def display_result(result: ProcessorResult):
    """결과 출력."""
    print(f"\n{'='*60}")
    print(f"Provider: {result.provider.upper()} ({result.model})")
    print(f"{'='*60}")

    if not result.success:
        print(f"❌ Error: {result.error}")
        return

    print(f"✅ Success!")
    print(f"⏱️  Latency: {result.latency_seconds:.2f}s")
    print(f"📊 Tokens: {result.input_tokens:,} in / {result.output_tokens:,} out")
    print(f"💰 Cost: ${result.cost_usd:.4f}")

    # 메타데이터
    meta = result.extracted_data.get("metadata", {})
    print(f"\n--- Metadata ---")
    print(f"Title: {meta.get('title', 'N/A')}")
    print(f"Authors: {', '.join(meta.get('authors', [])[:3])}{'...' if len(meta.get('authors', [])) > 3 else ''}")
    print(f"Year: {meta.get('year', 'N/A')}")
    print(f"Journal: {meta.get('journal', 'N/A')}")
    print(f"Study Type: {meta.get('study_type', 'N/A')}")
    print(f"Evidence Level: {meta.get('evidence_level', 'N/A')}")
    print(f"Sample Size: {meta.get('sample_size', 'N/A')}")

    # Spine 메타데이터
    spine = result.extracted_data.get("spine_metadata", {})
    if spine:
        print(f"\n--- Spine Metadata ---")
        print(f"Sub-domain: {spine.get('sub_domain', 'N/A')}")
        print(f"Anatomy: {spine.get('anatomy_level', 'N/A')} ({spine.get('anatomy_region', 'N/A')})")
        print(f"Pathology: {', '.join(spine.get('pathology', []))}")
        print(f"Interventions: {', '.join(spine.get('interventions', []))}")
        print(f"Follow-up: {spine.get('follow_up_months', 'N/A')} months")

        # Outcomes
        outcomes = spine.get("outcomes", [])
        if outcomes:
            print(f"\n--- Outcomes ({len(outcomes)}) ---")
            for i, outcome in enumerate(outcomes[:5]):
                sig = "✓" if outcome.get("is_significant") else "✗"
                print(f"  [{i+1}] {outcome.get('name', 'N/A')} ({outcome.get('category', 'N/A')})")
                print(f"      p={outcome.get('p_value', 'N/A')}, direction={outcome.get('direction', 'N/A')} {sig}")

    # Chunks
    chunks = result.extracted_data.get("chunks", [])
    if chunks:
        key_findings = [c for c in chunks if c.get("is_key_finding")]
        print(f"\n--- Chunks ---")
        print(f"Total: {len(chunks)}")
        print(f"Key Findings: {len(key_findings)}")

    # Citations
    citations = result.extracted_data.get("important_citations", [])
    if citations:
        print(f"\n--- Important Citations ({len(citations)}) ---")
        for cit in citations[:3]:
            authors = ", ".join(cit.get("authors", []))
            print(f"  • {authors} ({cit.get('year', 'N/A')}) - {cit.get('context', 'N/A')}")


def display_comparison(comparison: ComparisonResult):
    """비교 결과 출력."""
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"PDF: {comparison.pdf_path}")
    print(f"Timestamp: {comparison.timestamp}")

    summary = comparison.summary

    if summary.get("status") == "all_failed":
        print("❌ All providers failed")
        return

    print(f"\n📊 Results: {summary['successful']}/{summary['total_providers']} successful")
    print(f"🚀 Fastest: {summary['fastest']}")
    print(f"💰 Cheapest: {summary['cheapest']}")

    # 비교 테이블
    print(f"\n--- Performance Comparison ---")
    print(f"{'Provider':<10} {'Latency':<12} {'Tokens':<15} {'Cost':<12}")
    print("-" * 50)

    for provider, latency in summary['comparison'].get('latency', {}).items():
        tokens = summary['comparison']['tokens'].get(provider, {})
        total_tokens = tokens.get('total', 0)
        cost = summary['comparison']['costs'].get(provider, 'N/A')
        print(f"{provider:<10} {latency:<12} {total_tokens:<15,} {cost:<12}")

    # 제목 비교
    print(f"\n--- Extracted Titles ---")
    for provider, title in summary['comparison'].get('titles', {}).items():
        print(f"{provider}: {title}")


# =============================================================================
# Main
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="Multi-LLM PDF Processor Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument(
        "--provider", "-p",
        choices=["claude-haiku", "claude-sonnet", "gemini-flash", "gemini-pro", "openai"],
        help="LLM provider to use (claude-haiku, claude-sonnet, gemini-flash, gemini-pro, openai)"
    )
    parser.add_argument("--model", "-m", help="Specific model to use")
    parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="Compare all available LLMs"
    )
    parser.add_argument(
        "--output", "-o",
        help="Save results to JSON file"
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"❌ File not found: {pdf_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("Multi-LLM PDF Processor Test")
    print(f"{'='*60}")
    print(f"PDF: {pdf_path.name}")

    processor = MultiLLMPDFProcessor()

    if args.compare:
        # 모든 LLM 비교
        comparison = await processor.compare_all(pdf_path)
        display_comparison(comparison)

        # 개별 결과도 출력
        for provider, result_dict in comparison.results.items():
            result = ProcessorResult(**result_dict)
            display_result(result)

        # JSON 저장
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(asdict(comparison), f, indent=2, ensure_ascii=False)
            print(f"\n📁 Results saved to: {args.output}")

    elif args.provider:
        # 단일 LLM
        result = await processor.process_single(pdf_path, args.provider, args.model)
        display_result(result)

        # JSON 저장
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(asdict(result), f, indent=2, ensure_ascii=False)
            print(f"\n📁 Result saved to: {args.output}")

    else:
        # 기본: Claude Haiku 사용
        print("\n💡 Tip: Use --compare to test all LLMs, or --provider to specify one")
        result = await processor.process_single(pdf_path, "claude-haiku", args.model)
        display_result(result)

    print(f"\n{'='*60}")
    print("Test completed!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())

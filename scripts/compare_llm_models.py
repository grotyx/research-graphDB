#!/usr/bin/env python3
"""
LLM Model Comparison Script for PDF Processing

Compares:
- Google Gemini 2.5 Flash (current)
- Anthropic Claude Sonnet 4.5
- Anthropic Claude Haiku 4.5

Usage:
    python scripts/compare_llm_models.py --pdf path/to/paper.pdf
    python scripts/compare_llm_models.py --pdf path/to/paper.pdf --models gemini,sonnet
"""

import asyncio
import base64
import json
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()


class ModelType(Enum):
    """Supported LLM models."""
    GEMINI_FLASH = "gemini-2.5-flash"
    CLAUDE_SONNET = "claude-sonnet-4.5"
    CLAUDE_HAIKU = "claude-haiku-4.5"


@dataclass
class ModelResult:
    """Result from a single model."""
    model: ModelType
    success: bool
    latency_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0
    extracted_data: dict = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class ComparisonResult:
    """Comparison result across all models."""
    pdf_path: str
    pdf_pages: int
    results: list[ModelResult] = field(default_factory=list)

    def summary(self) -> str:
        """Generate comparison summary."""
        lines = [
            f"\n{'='*60}",
            f"PDF Processing Comparison Results",
            f"{'='*60}",
            f"PDF: {self.pdf_path}",
            f"Pages: {self.pdf_pages}",
            f"{'='*60}\n",
        ]

        for r in self.results:
            status = "✅" if r.success else "❌"
            lines.append(f"{status} {r.model.value}")
            lines.append(f"   Latency: {r.latency_seconds:.2f}s")
            lines.append(f"   Tokens: {r.input_tokens:,} in / {r.output_tokens:,} out")
            lines.append(f"   Cost: ${r.total_cost_usd:.4f}")
            if r.error:
                lines.append(f"   Error: {r.error}")
            lines.append("")

        # Winner determination
        successful = [r for r in self.results if r.success]
        if successful:
            fastest = min(successful, key=lambda x: x.latency_seconds)
            cheapest = min(successful, key=lambda x: x.total_cost_usd)
            lines.append(f"🏆 Fastest: {fastest.model.value} ({fastest.latency_seconds:.2f}s)")
            lines.append(f"💰 Cheapest: {cheapest.model.value} (${cheapest.total_cost_usd:.4f})")

        return "\n".join(lines)


# Pricing per 1M tokens (as of Dec 2024)
PRICING = {
    ModelType.GEMINI_FLASH: {"input": 0.075, "output": 0.30},
    ModelType.CLAUDE_SONNET: {"input": 3.00, "output": 15.00},
    ModelType.CLAUDE_HAIKU: {"input": 1.00, "output": 5.00},
}


# Extraction prompt (same for all models)
EXTRACTION_PROMPT = """Analyze this medical research PDF and extract the following information in JSON format:

{
  "title": "Paper title",
  "authors": ["Author 1", "Author 2"],
  "year": 2024,
  "journal": "Journal name",
  "study_type": "RCT/Cohort/Case-control/Case series/Meta-analysis/Review",
  "evidence_level": "1a/1b/2a/2b/3/4/5",
  "sub_domain": "Degenerative/Deformity/Trauma/Tumor/Basic Science",
  "anatomy_levels": ["Cervical", "Thoracic", "Lumbar", "Sacral"],
  "pathologies": ["Disease 1", "Disease 2"],
  "interventions": ["Surgery 1", "Surgery 2"],
  "outcomes": [
    {
      "name": "VAS",
      "baseline": 7.2,
      "final": 2.1,
      "p_value": 0.001,
      "is_significant": true
    }
  ],
  "sample_size": 100,
  "follow_up_months": 24,
  "main_conclusion": "Brief conclusion"
}

Return ONLY the JSON object, no additional text."""


class GeminiProcessor:
    """Gemini 2.5 Flash PDF processor."""

    def __init__(self):
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.5-flash"  # Latest stable model

    async def process_pdf(self, pdf_path: Path) -> ModelResult:
        """Process PDF with Gemini."""
        start_time = time.time()

        try:
            # Read PDF as bytes
            pdf_bytes = pdf_path.read_bytes()

            # Create content with PDF
            from google.genai.types import Content, Part

            contents = [
                Content(
                    role="user",
                    parts=[
                        Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                        Part.from_text(text=EXTRACTION_PROMPT),
                    ]
                )
            ]

            # Generate response
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
            )

            latency = time.time() - start_time

            # Parse response
            text = response.text
            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            extracted = json.loads(text.strip())

            # Get token counts
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0

            # Calculate cost
            pricing = PRICING[ModelType.GEMINI_FLASH]
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

            return ModelResult(
                model=ModelType.GEMINI_FLASH,
                success=True,
                latency_seconds=latency,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_cost_usd=cost,
                extracted_data=extracted,
            )

        except Exception as e:
            return ModelResult(
                model=ModelType.GEMINI_FLASH,
                success=False,
                latency_seconds=time.time() - start_time,
                error=str(e),
            )


class ClaudeProcessor:
    """Claude (Sonnet/Haiku) PDF processor."""

    # Model IDs (as of Dec 2024)
    # Reference: https://docs.anthropic.com/en/docs/about-claude/models/overview
    MODEL_IDS = {
        ModelType.CLAUDE_SONNET: "claude-sonnet-4-5-20250929",  # Claude Sonnet 4.5 (latest)
        ModelType.CLAUDE_HAIKU: "claude-haiku-4-5-20251001",   # Claude Haiku 4.5
    }

    def __init__(self, model_type: ModelType):
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_type = model_type
        self.model_id = self.MODEL_IDS.get(model_type)
        if not self.model_id:
            raise ValueError(f"Unknown model type: {model_type}")

    def process_pdf(self, pdf_path: Path) -> ModelResult:
        """Process PDF with Claude."""
        start_time = time.time()

        try:
            # Read and encode PDF
            pdf_bytes = pdf_path.read_bytes()
            base64_data = base64.standard_b64encode(pdf_bytes).decode("utf-8")

            # Create message with PDF document
            message = self.client.messages.create(
                model=self.model_id,
                max_tokens=4096,
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
                            {
                                "type": "text",
                                "text": EXTRACTION_PROMPT,
                            }
                        ]
                    }
                ],
            )

            latency = time.time() - start_time

            # Parse response
            text = message.content[0].text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            extracted = json.loads(text.strip())

            # Get token counts
            input_tokens = message.usage.input_tokens
            output_tokens = message.usage.output_tokens

            # Calculate cost
            pricing = PRICING[self.model_type]
            cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

            return ModelResult(
                model=self.model_type,
                success=True,
                latency_seconds=latency,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_cost_usd=cost,
                extracted_data=extracted,
            )

        except Exception as e:
            return ModelResult(
                model=self.model_type,
                success=False,
                latency_seconds=time.time() - start_time,
                error=str(e),
            )


def count_pdf_pages(pdf_path: Path) -> int:
    """Count pages in PDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        return len(doc)
    except Exception:
        return 0


async def compare_models(
    pdf_path: Path,
    models: list[ModelType] | None = None,
) -> ComparisonResult:
    """Compare multiple models on the same PDF."""

    if models is None:
        models = [ModelType.GEMINI_FLASH, ModelType.CLAUDE_SONNET, ModelType.CLAUDE_HAIKU]

    result = ComparisonResult(
        pdf_path=str(pdf_path),
        pdf_pages=count_pdf_pages(pdf_path),
    )

    for model_type in models:
        print(f"Processing with {model_type.value}...")

        if model_type == ModelType.GEMINI_FLASH:
            processor = GeminiProcessor()
            model_result = await processor.process_pdf(pdf_path)
        else:
            processor = ClaudeProcessor(model_type)
            model_result = processor.process_pdf(pdf_path)

        result.results.append(model_result)

        if model_result.success:
            print(f"  ✅ Success in {model_result.latency_seconds:.2f}s")
        else:
            print(f"  ❌ Failed: {model_result.error}")

    return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Compare LLM models for PDF processing")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument(
        "--models",
        default="gemini,sonnet,haiku",
        help="Comma-separated list of models: gemini,sonnet,haiku"
    )
    parser.add_argument("--output", help="Output JSON file for detailed results")

    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    # Parse model selection
    model_map = {
        "gemini": ModelType.GEMINI_FLASH,
        "sonnet": ModelType.CLAUDE_SONNET,
        "haiku": ModelType.CLAUDE_HAIKU,
    }
    selected_models = []
    for m in args.models.split(","):
        m = m.strip().lower()
        if m in model_map:
            selected_models.append(model_map[m])
        else:
            print(f"Warning: Unknown model '{m}', skipping")

    if not selected_models:
        print("Error: No valid models selected")
        sys.exit(1)

    # Run comparison
    result = asyncio.run(compare_models(pdf_path, selected_models))

    # Print summary
    print(result.summary())

    # Save detailed results if requested
    if args.output:
        output_data = {
            "pdf_path": result.pdf_path,
            "pdf_pages": result.pdf_pages,
            "results": [
                {
                    "model": r.model.value,
                    "success": r.success,
                    "latency_seconds": r.latency_seconds,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "cost_usd": r.total_cost_usd,
                    "extracted_data": r.extracted_data,
                    "error": r.error,
                }
                for r in result.results
            ]
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nDetailed results saved to: {args.output}")


if __name__ == "__main__":
    main()

"""LLM Integration Layer.

Claude (Primary) 및 Gemini API 클라이언트.
기본값은 Claude Haiku 4.5이며, 환경변수로 변경 가능합니다.

Usage:
    # 기본 사용 (Claude)
    from llm import LLMClient
    client = LLMClient()
    response = await client.generate("Hello")

    # 명시적으로 Claude 사용
    from llm import ClaudeClient
    client = ClaudeClient()

    # Gemini 사용 (레거시)
    from llm import GeminiClient
    client = GeminiClient()
"""

import os

from .base import BaseLLMClient
from .cache import LLMCache, generate_cache_key
from .claude_client import ClaudeClient, ClaudeConfig, ClaudeResponse
from .claude_client import CostTracker  # Claude에서 가져옴
from .gemini_client import GeminiClient, GeminiConfig, GeminiResponse

# 환경변수 기반 기본 클라이언트 선택
_provider = os.environ.get("LLM_PROVIDER", "claude").lower()

if _provider == "gemini":
    # Gemini 사용 (레거시 호환)
    LLMClient = GeminiClient
    LLMConfig = GeminiConfig
    LLMResponse = GeminiResponse
else:
    # Claude 사용 (기본값)
    LLMClient = ClaudeClient
    LLMConfig = ClaudeConfig
    LLMResponse = ClaudeResponse


__all__ = [
    # Base Protocol
    "BaseLLMClient",

    # 통합 인터페이스 (환경변수 기반)
    "LLMClient",
    "LLMConfig",
    "LLMResponse",

    # Claude (Primary)
    "ClaudeClient",
    "ClaudeConfig",
    "ClaudeResponse",

    # Gemini (Legacy)
    "GeminiClient",
    "GeminiConfig",
    "GeminiResponse",

    # 공통
    "CostTracker",
    "LLMCache",
    "generate_cache_key",
]

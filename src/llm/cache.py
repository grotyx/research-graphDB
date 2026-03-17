"""LLM Response Cache - backward-compatible re-export.

Canonical location: core/llm_cache.py
This shim preserves `from llm.cache import LLMCache` for existing code.
"""

from core.llm_cache import LLMCache, CacheStats, generate_cache_key

__all__ = ["LLMCache", "CacheStats", "generate_cache_key"]

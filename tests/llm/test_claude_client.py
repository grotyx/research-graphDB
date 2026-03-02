"""Tests for Claude API Client module.

Covers:
- ClaudeConfig: initialization, environment variable loading, validation
- CostTracker: recording, cost estimation, reset
- RateLimiter: request throttling, token limits
- ClaudeClient: generate, generate_json, generate_batch
- API call with retry logic (rate limit, server errors, network errors)
- Model fallback on token overflow
- JSON response parsing (markdown blocks, invalid JSON)
- Cache integration
- Cost summary
"""

import pytest
import asyncio
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

from core.exceptions import LLMError


# =====================================================================
# ClaudeConfig tests
# =====================================================================

class TestClaudeConfig:
    """Tests for ClaudeConfig."""

    def test_config_with_api_key(self):
        from llm.claude_client import ClaudeConfig
        config = ClaudeConfig(api_key="test-key-123")
        assert config.api_key == "test-key-123"
        assert config.model == "claude-haiku-4-5-20251001"
        assert config.max_retries == 3
        assert config.temperature == 0.1

    def test_config_from_env(self):
        from llm.claude_client import ClaudeConfig
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key-456"}):
            config = ClaudeConfig()
        assert config.api_key == "env-key-456"

    def test_config_missing_api_key_raises(self):
        from llm.claude_client import ClaudeConfig
        with patch.dict(os.environ, {}, clear=True):
            # Remove ANTHROPIC_API_KEY if present
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(LLMError):
                    ClaudeConfig()

    def test_config_env_model_override(self):
        from llm.claude_client import ClaudeConfig
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test-key",
            "CLAUDE_MODEL": "custom-model",
            "CLAUDE_FALLBACK_MODEL": "custom-fallback",
        }):
            config = ClaudeConfig()
        assert config.model == "custom-model"
        assert config.fallback_model == "custom-fallback"


# =====================================================================
# CostTracker tests
# =====================================================================

class TestCostTracker:
    """Tests for CostTracker."""

    def test_initial_state(self):
        from llm.claude_client import CostTracker
        tracker = CostTracker()
        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0
        assert tracker.total_requests == 0
        assert tracker.estimated_cost == 0.0

    def test_record_haiku(self):
        from llm.claude_client import CostTracker
        tracker = CostTracker()
        tracker.record(1000, 500, model="claude-haiku-4-5-20251001")
        assert tracker.total_input_tokens == 1000
        assert tracker.total_output_tokens == 500
        assert tracker.total_requests == 1
        assert tracker.haiku_input_tokens == 1000
        assert tracker.haiku_output_tokens == 500

    def test_record_sonnet(self):
        from llm.claude_client import CostTracker
        tracker = CostTracker()
        tracker.record(1000, 500, model="claude-sonnet-4-5-20250929")
        assert tracker.sonnet_input_tokens == 1000
        assert tracker.sonnet_output_tokens == 500

    def test_estimated_cost(self):
        from llm.claude_client import CostTracker
        tracker = CostTracker()
        # 1M haiku input tokens: $1.0, 1M haiku output tokens: $5.0
        tracker.record(1_000_000, 1_000_000, model="haiku")
        assert tracker.estimated_cost == 6.0  # 1.0 + 5.0

    def test_record_cached(self):
        from llm.claude_client import CostTracker
        tracker = CostTracker()
        tracker.record(100, 50, cached=True)
        assert tracker.cached_requests == 1

    def test_reset(self):
        from llm.claude_client import CostTracker
        tracker = CostTracker()
        tracker.record(1000, 500)
        tracker.reset()
        assert tracker.total_input_tokens == 0
        assert tracker.total_requests == 0
        assert tracker.haiku_input_tokens == 0


# =====================================================================
# RateLimiter tests
# =====================================================================

class TestRateLimiter:
    """Tests for RateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire_under_limit(self):
        from llm.claude_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "5"}):
            limiter = RateLimiter(requests_per_minute=1000, tokens_per_minute=400_000)
        await limiter.acquire(estimated_tokens=100)
        # Should succeed without waiting

    @pytest.mark.asyncio
    async def test_record_usage(self):
        from llm.claude_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "5"}):
            limiter = RateLimiter(requests_per_minute=1000, tokens_per_minute=400_000)
        await limiter.record_usage(1000)
        assert len(limiter.token_usage) == 1

    @pytest.mark.asyncio
    async def test_max_concurrent_from_env(self):
        from llm.claude_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "3"}):
            limiter = RateLimiter(requests_per_minute=100, tokens_per_minute=100_000)
        assert limiter.semaphore._value == 3

    @pytest.mark.asyncio
    async def test_max_concurrent_clamped(self):
        from llm.claude_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "50"}):
            limiter = RateLimiter(requests_per_minute=100, tokens_per_minute=100_000)
        assert limiter.semaphore._value == 20  # clamped to max 20

    @pytest.mark.asyncio
    async def test_max_concurrent_min_1(self):
        from llm.claude_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "0"}):
            limiter = RateLimiter(requests_per_minute=100, tokens_per_minute=100_000)
        assert limiter.semaphore._value == 1  # clamped to min 1


# =====================================================================
# ClaudeClient tests
# =====================================================================

@pytest.fixture
def mock_anthropic_message():
    """Create a mock Anthropic API message response."""
    message = MagicMock()
    message.content = [MagicMock(text="Test response")]
    message.usage = MagicMock(input_tokens=100, output_tokens=50)
    message.stop_reason = "end_turn"
    return message


@pytest.fixture
def claude_client(mock_anthropic_message):
    """Create a ClaudeClient with mocked Anthropic client."""
    from llm.claude_client import ClaudeClient, ClaudeConfig

    config = ClaudeConfig(api_key="test-key-123")
    client = ClaudeClient(config=config)

    # Mock the sync Anthropic client
    client.client = MagicMock()
    client.client.messages.create.return_value = mock_anthropic_message

    return client


class TestClaudeClientGenerate:
    """Tests for ClaudeClient.generate()."""

    @pytest.mark.asyncio
    async def test_generate_basic(self, claude_client):
        response = await claude_client.generate("What is 2+2?", use_cache=False)
        assert response.text == "Test response"
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.cached is False

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, claude_client):
        response = await claude_client.generate(
            "What is 2+2?",
            system="You are a math tutor",
            use_cache=False,
        )
        assert response.text == "Test response"

    @pytest.mark.asyncio
    async def test_generate_records_cost(self, claude_client):
        await claude_client.generate("test", use_cache=False)
        assert claude_client.cost_tracker.total_requests == 1
        assert claude_client.cost_tracker.total_input_tokens == 100
        assert claude_client.cost_tracker.total_output_tokens == 50

    @pytest.mark.asyncio
    async def test_generate_with_cache_hit(self, claude_client):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value={
            "response": {"text": "Cached response"},
            "input_tokens": 50,
            "output_tokens": 25,
        })
        claude_client.cache = mock_cache

        response = await claude_client.generate("cached prompt", use_cache=True)
        assert response.text == "Cached response"
        assert response.cached is True
        assert response.latency_ms == 0

    @pytest.mark.asyncio
    async def test_generate_with_cache_miss(self, claude_client):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        mock_cache.log_cost = AsyncMock()
        claude_client.cache = mock_cache

        response = await claude_client.generate("new prompt", use_cache=True)
        assert response.text == "Test response"
        assert response.cached is False
        mock_cache.set.assert_called_once()
        mock_cache.log_cost.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_cache_disabled(self, claude_client):
        mock_cache = AsyncMock()
        claude_client.cache = mock_cache

        await claude_client.generate("test", use_cache=False)
        mock_cache.get.assert_not_called()


class TestClaudeClientGenerateJSON:
    """Tests for ClaudeClient.generate_json()."""

    @pytest.mark.asyncio
    async def test_generate_json_success(self, claude_client):
        # Mock response with valid JSON
        msg = MagicMock()
        msg.content = [MagicMock(text='{"answer": 4, "unit": "number"}')]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"
        claude_client.client.messages.create.return_value = msg

        schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
        result = await claude_client.generate_json("What is 2+2?", schema, use_cache=False)
        assert result == {"answer": 4, "unit": "number"}

    @pytest.mark.asyncio
    async def test_generate_json_with_markdown_block(self, claude_client):
        msg = MagicMock()
        msg.content = [MagicMock(text='```json\n{"answer": 42}\n```')]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"
        claude_client.client.messages.create.return_value = msg

        schema = {"type": "object"}
        result = await claude_client.generate_json("test", schema, use_cache=False)
        assert result == {"answer": 42}

    @pytest.mark.asyncio
    async def test_generate_json_with_generic_code_block(self, claude_client):
        msg = MagicMock()
        msg.content = [MagicMock(text='```\n{"answer": 42}\n```')]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"
        claude_client.client.messages.create.return_value = msg

        schema = {"type": "object"}
        result = await claude_client.generate_json("test", schema, use_cache=False)
        assert result == {"answer": 42}

    @pytest.mark.asyncio
    async def test_generate_json_invalid_json_returns_empty(self, claude_client):
        msg = MagicMock()
        msg.content = [MagicMock(text='This is not valid JSON at all')]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"
        claude_client.client.messages.create.return_value = msg

        schema = {"type": "object"}
        result = await claude_client.generate_json("test", schema, use_cache=False)
        assert result == {}

    @pytest.mark.asyncio
    async def test_generate_json_with_cache(self, claude_client):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value={
            "response": {"cached_key": "cached_value"},
            "input_tokens": 50,
            "output_tokens": 25,
        })
        claude_client.cache = mock_cache

        schema = {"type": "object"}
        result = await claude_client.generate_json("cached prompt", schema, use_cache=True)
        assert result == {"cached_key": "cached_value"}


class TestClaudeClientRetry:
    """Tests for API retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, claude_client):
        import anthropic
        rate_limit_error = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )

        msg = MagicMock()
        msg.content = [MagicMock(text="Success after retry")]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"

        claude_client.client.messages.create.side_effect = [
            rate_limit_error,
            msg,
        ]

        with patch("llm.claude_client.asyncio.sleep", new_callable=AsyncMock):
            response = await claude_client.generate("test", use_cache=False)
        assert response.text == "Success after retry"

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, claude_client):
        import anthropic

        error_resp = MagicMock()
        error_resp.status_code = 500

        server_error = anthropic.APIStatusError(
            message="Internal Server Error",
            response=error_resp,
            body=None,
        )

        msg = MagicMock()
        msg.content = [MagicMock(text="Success")]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"

        claude_client.client.messages.create.side_effect = [
            server_error,
            msg,
        ]

        with patch("llm.claude_client.asyncio.sleep", new_callable=AsyncMock):
            response = await claude_client.generate("test", use_cache=False)
        assert response.text == "Success"

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self, claude_client):
        import anthropic

        error_resp = MagicMock()
        error_resp.status_code = 400

        client_error = anthropic.APIStatusError(
            message="Bad Request",
            response=error_resp,
            body=None,
        )

        claude_client.client.messages.create.side_effect = client_error

        with pytest.raises(anthropic.APIStatusError):
            await claude_client.generate("test", use_cache=False)

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self, claude_client):
        import anthropic
        rate_limit_error = anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body=None,
        )
        claude_client.client.messages.create.side_effect = rate_limit_error

        with patch("llm.claude_client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(anthropic.RateLimitError):
                await claude_client.generate("test", use_cache=False)

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self, claude_client):
        msg = MagicMock()
        msg.content = [MagicMock(text="Success")]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"

        claude_client.client.messages.create.side_effect = [
            ConnectionError("dns resolution failed"),
            msg,
        ]

        with patch("llm.claude_client.asyncio.sleep", new_callable=AsyncMock):
            response = await claude_client.generate("test", use_cache=False)
        assert response.text == "Success"

    @pytest.mark.asyncio
    async def test_no_retry_on_unknown_exception(self, claude_client):
        claude_client.client.messages.create.side_effect = TypeError("Unexpected")

        with pytest.raises(TypeError):
            await claude_client.generate("test", use_cache=False)


class TestClaudeClientFallback:
    """Tests for model fallback on token overflow."""

    @pytest.mark.asyncio
    async def test_fallback_on_max_tokens(self, claude_client):
        msg_overflow = MagicMock()
        msg_overflow.content = [MagicMock(text="Truncated")]
        msg_overflow.usage = MagicMock(input_tokens=100, output_tokens=8192)
        msg_overflow.stop_reason = "max_tokens"

        msg_success = MagicMock()
        msg_success.content = [MagicMock(text="Full response from fallback")]
        msg_success.usage = MagicMock(input_tokens=100, output_tokens=1000)
        msg_success.stop_reason = "end_turn"

        claude_client.client.messages.create.side_effect = [
            msg_overflow,
            msg_success,
        ]

        response = await claude_client.generate("test", use_cache=False)
        assert response.text == "Full response from fallback"
        assert response.fallback_used is True

    @pytest.mark.asyncio
    async def test_no_fallback_when_disabled(self, claude_client):
        claude_client.config.auto_fallback = False

        msg_overflow = MagicMock()
        msg_overflow.content = [MagicMock(text="Truncated")]
        msg_overflow.usage = MagicMock(input_tokens=100, output_tokens=8192)
        msg_overflow.stop_reason = "max_tokens"

        claude_client.client.messages.create.return_value = msg_overflow

        response = await claude_client.generate("test", use_cache=False)
        assert response.text == "Truncated"
        assert response.fallback_used is False


class TestClaudeClientBatch:
    """Tests for batch generation."""

    @pytest.mark.asyncio
    async def test_generate_batch(self, claude_client):
        requests = [
            {"prompt": "Question 1"},
            {"prompt": "Question 2"},
        ]
        results = await claude_client.generate_batch(requests, concurrency=2)
        assert len(results) == 2
        assert all(r.text == "Test response" for r in results)

    @pytest.mark.asyncio
    async def test_generate_batch_with_schema(self, claude_client):
        msg = MagicMock()
        msg.content = [MagicMock(text='{"answer": 42}')]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"
        claude_client.client.messages.create.return_value = msg

        requests = [
            {"prompt": "What is 6*7?", "schema": {"type": "object"}},
        ]
        results = await claude_client.generate_batch(requests, concurrency=1)
        assert len(results) == 1
        # When schema is provided, text is JSON-stringified
        parsed = json.loads(results[0].text)
        assert parsed == {"answer": 42}

    @pytest.mark.asyncio
    async def test_generate_batch_handles_errors(self, claude_client):
        """Batch should skip failed requests."""
        msg = MagicMock()
        msg.content = [MagicMock(text="Success")]
        msg.usage = MagicMock(input_tokens=100, output_tokens=50)
        msg.stop_reason = "end_turn"

        call_count = 0
        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First request failed")
            return msg

        claude_client.client.messages.create.side_effect = side_effect

        requests = [
            {"prompt": "Fail"},
            {"prompt": "Success"},
        ]

        # Should not raise; failed ones are logged but do not crash
        # Note: generate() itself would re-raise non-network exceptions,
        # but gather catches them
        results = await claude_client.generate_batch(requests, concurrency=2)
        # At least the successful one should be returned
        assert len(results) >= 1


class TestClaudeClientCostSummary:
    """Tests for cost summary."""

    def test_get_cost_summary(self, claude_client):
        claude_client.cost_tracker.record(1000, 500, model="haiku")
        summary = claude_client.get_cost_summary()
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500
        assert summary["total_requests"] == 1
        assert "estimated_cost_usd" in summary

    def test_reset_cost_tracker(self, claude_client):
        claude_client.cost_tracker.record(1000, 500)
        claude_client.reset_cost_tracker()
        summary = claude_client.get_cost_summary()
        assert summary["total_requests"] == 0


# =====================================================================
# Compatibility aliases
# =====================================================================

class TestCompatibilityAliases:
    """Tests for LLMClient / LLMConfig / LLMResponse aliases."""

    def test_llm_client_alias(self):
        from llm.claude_client import LLMClient, ClaudeClient
        assert LLMClient is ClaudeClient

    def test_llm_config_alias(self):
        from llm.claude_client import LLMConfig, ClaudeConfig
        assert LLMConfig is ClaudeConfig

    def test_llm_response_alias(self):
        from llm.claude_client import LLMResponse, ClaudeResponse
        assert LLMResponse is ClaudeResponse

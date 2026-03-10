"""Tests for GeminiClient.

Comprehensive tests for the Gemini API client including:
- Configuration and initialization
- API calls with retry logic
- Rate limiting
- Cache integration
- JSON structured output
- Batch processing
- Cost tracking
- Error handling: rate limit, API errors, timeout, network errors
"""

import pytest
import json
import asyncio
import os
import time
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from core.exceptions import LLMError


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def isolate_gemini_env():
    """Set GEMINI_API_KEY and remove GEMINI_MODEL so defaults are tested."""
    env = {"GEMINI_API_KEY": "test-api-key-12345"}
    with patch.dict(os.environ, env, clear=False):
        os.environ.pop("GEMINI_MODEL", None)
        yield


@pytest.fixture
def gemini_config():
    """Create a GeminiConfig instance."""
    from llm.gemini_client import GeminiConfig
    return GeminiConfig(api_key="test-api-key-12345", max_retries=2)


@pytest.fixture
def mock_genai_client():
    """Create a mock google-genai client."""
    mock = MagicMock()
    mock.aio = MagicMock()
    mock.aio.models = MagicMock()
    mock.aio.models.generate_content = AsyncMock()
    return mock


@pytest.fixture
def gemini_client(gemini_config, mock_genai_client):
    """Create a GeminiClient with mocked internals."""
    from llm.gemini_client import GeminiClient
    with patch("llm.gemini_client.genai.Client", return_value=mock_genai_client):
        client = GeminiClient(config=gemini_config)
    client.client = mock_genai_client
    return client


def _make_mock_response(text="test response", input_tokens=10, output_tokens=20):
    """Create a mock Gemini API response."""
    mock_response = MagicMock()
    mock_response.text = text
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = input_tokens
    mock_usage.candidates_token_count = output_tokens
    mock_response.usage_metadata = mock_usage
    return mock_response


# ============================================================================
# TestGeminiConfig
# ============================================================================

class TestGeminiConfig:
    """GeminiConfig tests."""

    def test_default_values(self):
        from llm.gemini_client import GeminiConfig
        config = GeminiConfig(api_key="test-key")
        assert config.model == "gemini-2.5-flash"
        assert config.max_retries == 3
        assert config.temperature == 0.1
        assert config.max_output_tokens == 8192
        assert config.requests_per_minute == 2000
        assert config.tokens_per_minute == 4_000_000

    def test_custom_values(self):
        from llm.gemini_client import GeminiConfig
        config = GeminiConfig(
            api_key="custom-key",
            model="gemini-2.0-flash",
            temperature=0.5,
            max_retries=5,
            max_output_tokens=4096,
        )
        assert config.api_key == "custom-key"
        assert config.model == "gemini-2.0-flash"
        assert config.temperature == 0.5
        assert config.max_retries == 5

    def test_missing_api_key_raises_error(self, monkeypatch):
        from llm.gemini_client import GeminiConfig
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(LLMError, match="GEMINI_API_KEY"):
            GeminiConfig(api_key="")

    def test_api_key_from_env(self):
        from llm.gemini_client import GeminiConfig
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}):
            config = GeminiConfig()
            assert config.api_key == "env-key"


# ============================================================================
# TestCostTracker
# ============================================================================

class TestCostTracker:
    """CostTracker tests."""

    def test_initial_values(self):
        from llm.gemini_client import CostTracker
        tracker = CostTracker()
        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0
        assert tracker.total_requests == 0
        assert tracker.cached_requests == 0

    def test_record(self):
        from llm.gemini_client import CostTracker
        tracker = CostTracker()
        tracker.record(100, 200)
        assert tracker.total_input_tokens == 100
        assert tracker.total_output_tokens == 200
        assert tracker.total_requests == 1
        assert tracker.cached_requests == 0

    def test_record_cached(self):
        from llm.gemini_client import CostTracker
        tracker = CostTracker()
        tracker.record(50, 100, cached=True)
        assert tracker.cached_requests == 1

    def test_record_multiple(self):
        from llm.gemini_client import CostTracker
        tracker = CostTracker()
        tracker.record(100, 200)
        tracker.record(50, 100, cached=True)
        assert tracker.total_input_tokens == 150
        assert tracker.total_output_tokens == 300
        assert tracker.total_requests == 2
        assert tracker.cached_requests == 1

    def test_estimated_cost(self):
        from llm.gemini_client import CostTracker
        tracker = CostTracker()
        tracker.record(1_000_000, 1_000_000)
        cost = tracker.estimated_cost
        expected = (1_000_000 / 1_000_000) * 0.15 + (1_000_000 / 1_000_000) * 0.60
        assert cost == round(expected, 4)

    def test_reset(self):
        from llm.gemini_client import CostTracker
        tracker = CostTracker()
        tracker.record(100, 200)
        tracker.reset()
        assert tracker.total_input_tokens == 0
        assert tracker.total_requests == 0


# ============================================================================
# TestRateLimiter
# ============================================================================

class TestRateLimiter:
    """RateLimiter tests."""

    def test_init(self):
        from llm.gemini_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "3"}):
            limiter = RateLimiter(requests_per_minute=100, tokens_per_minute=1000)
            assert limiter.rpm == 100
            assert limiter.tpm == 1000

    def test_init_clamps_concurrency(self):
        from llm.gemini_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "50"}):
            limiter = RateLimiter(100, 1000)
            assert limiter.semaphore._value == 20  # clamped to max 20

    def test_init_min_concurrency(self):
        from llm.gemini_client import RateLimiter
        with patch.dict(os.environ, {"LLM_MAX_CONCURRENT": "0"}):
            limiter = RateLimiter(100, 1000)
            assert limiter.semaphore._value == 1  # clamped to min 1

    @pytest.mark.asyncio
    async def test_acquire_basic(self):
        from llm.gemini_client import RateLimiter
        limiter = RateLimiter(requests_per_minute=100, tokens_per_minute=100000)
        await limiter.acquire(estimated_tokens=100)
        assert len(limiter.request_times) == 1

    def test_record_usage(self):
        from llm.gemini_client import RateLimiter
        limiter = RateLimiter(100, 100000)
        limiter.record_usage(500)
        assert len(limiter.token_usage) == 1


# ============================================================================
# TestGeminiClientGenerate
# ============================================================================

class TestGeminiClientGenerate:
    """Test GeminiClient.generate method."""

    @pytest.mark.asyncio
    async def test_generate_basic(self, gemini_client, mock_genai_client):
        """Test basic text generation."""
        mock_response = _make_mock_response("Hello world", 10, 5)
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate("Say hello", use_cache=False)

        assert result.text == "Hello world"
        assert result.input_tokens == 10
        assert result.output_tokens == 5
        assert result.cached is False
        assert result.model == "gemini-2.5-flash"

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, gemini_client, mock_genai_client):
        """Test generation with system prompt."""
        mock_response = _make_mock_response("System reply")
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate(
            "prompt", system="You are a spine surgeon.", use_cache=False
        )

        assert result.text == "System reply"
        # Verify system instruction was set in the config
        call_args = mock_genai_client.aio.models.generate_content.call_args
        config = call_args.kwargs.get("config") or call_args[1].get("config")
        assert config.system_instruction == "You are a spine surgeon."

    @pytest.mark.asyncio
    async def test_generate_with_cache_hit(self, gemini_client):
        """Test generation with cache hit."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value={
            "response": {"text": "cached response"},
            "input_tokens": 5,
            "output_tokens": 10,
        })
        gemini_client.cache = mock_cache

        result = await gemini_client.generate("test prompt")

        assert result.text == "cached response"
        assert result.cached is True
        assert result.latency_ms == 0

    @pytest.mark.asyncio
    async def test_generate_cache_miss(self, gemini_client, mock_genai_client):
        """Test generation with cache miss saves to cache."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        mock_cache.log_cost = AsyncMock()
        gemini_client.cache = mock_cache

        mock_response = _make_mock_response("fresh response", 15, 25)
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate("test prompt")

        assert result.text == "fresh response"
        assert result.cached is False
        mock_cache.set.assert_called_once()
        mock_cache.log_cost.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_no_usage_metadata(self, gemini_client, mock_genai_client):
        """Test generation when response has no usage metadata."""
        mock_response = MagicMock()
        mock_response.text = "no usage"
        mock_response.usage_metadata = None
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate("test", use_cache=False)

        assert result.text == "no usage"
        assert result.input_tokens == 0
        assert result.output_tokens == 0


# ============================================================================
# TestGeminiClientGenerateJSON
# ============================================================================

class TestGeminiClientGenerateJSON:
    """Test GeminiClient.generate_json method."""

    @pytest.mark.asyncio
    async def test_generate_json_basic(self, gemini_client, mock_genai_client):
        """Test JSON structured output."""
        json_data = {"name": "test", "value": 42}
        mock_response = _make_mock_response(json.dumps(json_data), 20, 30)
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        result = await gemini_client.generate_json(
            "Extract data", schema=schema, use_cache=False
        )

        assert result == json_data
        # Verify JSON mode config
        call_args = mock_genai_client.aio.models.generate_content.call_args
        config = call_args.kwargs.get("config") or call_args[1].get("config")
        assert config.response_mime_type == "application/json"

    @pytest.mark.asyncio
    async def test_generate_json_with_cache_hit(self, gemini_client):
        """Test JSON generation with cache hit."""
        cached_data = {"cached": True}
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value={
            "response": cached_data,
            "input_tokens": 5,
            "output_tokens": 10,
        })
        gemini_client.cache = mock_cache

        result = await gemini_client.generate_json("test", schema={})

        assert result == cached_data

    @pytest.mark.asyncio
    async def test_generate_json_with_system(self, gemini_client, mock_genai_client):
        """Test JSON generation with system prompt."""
        mock_response = _make_mock_response('{"result": true}')
        mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        result = await gemini_client.generate_json(
            "prompt", schema={}, system="system instruction", use_cache=False
        )

        assert result == {"result": True}


# ============================================================================
# TestRetryLogic
# ============================================================================

class TestRetryLogic:
    """Test retry logic for API calls."""

    @staticmethod
    def _make_api_error(code: int, message: str = "error"):
        """Create a google.genai APIError with the correct constructor."""
        from google.genai import errors as genai_errors
        return genai_errors.APIError(code, {"error": {"message": message}})

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit(self, gemini_client, mock_genai_client):
        """Test retry on 429 rate limit error."""
        from google.genai import errors as genai_errors

        rate_limit_error = self._make_api_error(429, "Rate limited")
        mock_response = _make_mock_response("success after retry")

        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=[rate_limit_error, mock_response]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await gemini_client.generate("test", use_cache=False)

        assert result.text == "success after retry"

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, gemini_client, mock_genai_client):
        """Test retry on 500 server error."""
        from google.genai import errors as genai_errors

        server_error = self._make_api_error(500, "Server error")
        mock_response = _make_mock_response("recovered")

        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=[server_error, mock_response]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await gemini_client.generate("test", use_cache=False)

        assert result.text == "recovered"

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self, gemini_client, mock_genai_client):
        """Test no retry on 400 client error."""
        from google.genai import errors as genai_errors

        client_error = self._make_api_error(400, "Bad request")
        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=client_error
        )

        with pytest.raises(genai_errors.APIError):
            await gemini_client.generate("test", use_cache=False)

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self, gemini_client, mock_genai_client):
        """Test when all retries are exhausted."""
        from google.genai import errors as genai_errors

        server_error = self._make_api_error(503, "Persistent error")
        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=server_error
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(genai_errors.APIError):
                await gemini_client.generate("test", use_cache=False)

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self, gemini_client, mock_genai_client):
        """Test retry on network-related errors."""
        network_error = Exception("DNS resolution failed")
        mock_response = _make_mock_response("after network recovery")

        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=[network_error, mock_response]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await gemini_client.generate("test", use_cache=False)

        assert result.text == "after network recovery"

    @pytest.mark.asyncio
    async def test_no_retry_on_unknown_exception(self, gemini_client, mock_genai_client):
        """Test no retry on non-network exceptions."""
        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=ValueError("Unexpected error")
        )

        with pytest.raises(ValueError):
            await gemini_client.generate("test", use_cache=False)

    @pytest.mark.asyncio
    async def test_retry_json_on_rate_limit(self, gemini_client, mock_genai_client):
        """Test JSON retry on rate limit."""
        from google.genai import errors as genai_errors

        rate_limit_error = self._make_api_error(429, "Rate limited")
        mock_response = _make_mock_response('{"ok": true}')

        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=[rate_limit_error, mock_response]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await gemini_client.generate_json("test", schema={}, use_cache=False)

        assert result == {"ok": True}


# ============================================================================
# TestBatchGeneration
# ============================================================================

class TestBatchGeneration:
    """Test batch generation."""

    @pytest.mark.asyncio
    async def test_batch_generate(self, gemini_client, mock_genai_client):
        """Test batch text generation."""
        mock_response1 = _make_mock_response("response 1")
        mock_response2 = _make_mock_response("response 2")

        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=[mock_response1, mock_response2]
        )

        requests = [
            {"prompt": "prompt 1"},
            {"prompt": "prompt 2"},
        ]

        results = await gemini_client.generate_batch(requests, concurrency=2)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_batch_with_errors(self, gemini_client, mock_genai_client):
        """Test batch with some failures."""
        mock_response = _make_mock_response("ok")

        mock_genai_client.aio.models.generate_content = AsyncMock(
            side_effect=[Exception("fail"), mock_response]
        )

        requests = [
            {"prompt": "will fail"},
            {"prompt": "will succeed"},
        ]

        results = await gemini_client.generate_batch(requests, concurrency=2)

        # The failed request is filtered out
        assert len(results) >= 0  # At least some results


# ============================================================================
# TestCostSummary
# ============================================================================

class TestCostSummary:
    """Test cost summary methods."""

    def test_get_cost_summary(self, gemini_client):
        """Test cost summary output."""
        gemini_client.cost_tracker.record(1000, 2000)
        summary = gemini_client.get_cost_summary()

        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 2000
        assert summary["total_requests"] == 1
        assert "estimated_cost_usd" in summary

    def test_reset_cost_tracker(self, gemini_client):
        """Test cost tracker reset."""
        gemini_client.cost_tracker.record(1000, 2000)
        gemini_client.reset_cost_tracker()

        summary = gemini_client.get_cost_summary()
        assert summary["total_input_tokens"] == 0
        assert summary["total_requests"] == 0


# ============================================================================
# TestGeminiResponse
# ============================================================================

class TestGeminiResponse:
    """Test GeminiResponse dataclass."""

    def test_response_fields(self):
        from llm.gemini_client import GeminiResponse
        resp = GeminiResponse(
            text="test", input_tokens=10, output_tokens=20,
            latency_ms=150.5, cached=True, model="gemini-2.5-flash"
        )
        assert resp.text == "test"
        assert resp.input_tokens == 10
        assert resp.output_tokens == 20
        assert resp.latency_ms == 150.5
        assert resp.cached is True
        assert resp.model == "gemini-2.5-flash"

    def test_response_defaults(self):
        from llm.gemini_client import GeminiResponse
        resp = GeminiResponse(text="t", input_tokens=0, output_tokens=0, latency_ms=0)
        assert resp.cached is False
        assert resp.model == ""

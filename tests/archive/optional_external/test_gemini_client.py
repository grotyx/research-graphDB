"""GeminiClient 테스트."""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from src.llm.gemini_client import (
    GeminiClient,
    GeminiConfig,
    GeminiResponse,
    CostTracker,
    RateLimiter
)
from src.llm.cache import LLMCache, generate_cache_key


class TestGeminiConfig:
    """GeminiConfig 테스트."""

    def test_default_values(self):
        """기본값 테스트."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            config = GeminiConfig()
            assert config.model == "gemini-2.5-flash"
            assert config.max_retries == 3
            assert config.temperature == 0.1
            assert config.api_key == "test-key"

    def test_custom_values(self):
        """커스텀 값 테스트."""
        config = GeminiConfig(
            api_key="custom-key",
            model="custom-model",
            temperature=0.5
        )
        assert config.api_key == "custom-key"
        assert config.model == "custom-model"
        assert config.temperature == 0.5

    def test_missing_api_key_raises_error(self):
        """API 키 누락 시 에러."""
        with patch.dict("os.environ", {}, clear=True):
            # GEMINI_API_KEY 환경변수 제거
            import os
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                GeminiConfig()


class TestCostTracker:
    """CostTracker 테스트."""

    def test_initial_values(self):
        """초기값 테스트."""
        tracker = CostTracker()
        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0
        assert tracker.total_requests == 0

    def test_record_usage(self):
        """사용량 기록 테스트."""
        tracker = CostTracker()
        tracker.record(input_tokens=1000, output_tokens=500)
        assert tracker.total_input_tokens == 1000
        assert tracker.total_output_tokens == 500
        assert tracker.total_requests == 1

    def test_record_cached(self):
        """캐시된 요청 기록 테스트."""
        tracker = CostTracker()
        tracker.record(input_tokens=1000, output_tokens=500, cached=True)
        assert tracker.cached_requests == 1

    def test_estimated_cost(self):
        """비용 추정 테스트."""
        tracker = CostTracker()
        # 1M input tokens = $0.15
        # 1M output tokens = $0.60
        tracker.record(input_tokens=1_000_000, output_tokens=1_000_000)
        assert tracker.estimated_cost == 0.75

    def test_reset(self):
        """초기화 테스트."""
        tracker = CostTracker()
        tracker.record(input_tokens=1000, output_tokens=500)
        tracker.reset()
        assert tracker.total_input_tokens == 0
        assert tracker.total_requests == 0


class TestRateLimiter:
    """RateLimiter 테스트."""

    @pytest.mark.asyncio
    async def test_acquire_no_wait(self):
        """대기 없이 획득 테스트."""
        limiter = RateLimiter(requests_per_minute=100, tokens_per_minute=100000)
        # 첫 요청은 즉시 통과해야 함
        await limiter.acquire(estimated_tokens=100)
        assert len(limiter.request_times) == 1

    def test_record_usage(self):
        """토큰 사용량 기록 테스트."""
        limiter = RateLimiter(requests_per_minute=100, tokens_per_minute=100000)
        limiter.record_usage(1000)
        assert len(limiter.token_usage) == 1


class TestGeminiClient:
    """GeminiClient 테스트."""

    @pytest.fixture
    def mock_config(self):
        """Mock 설정."""
        return GeminiConfig(api_key="test-key")

    @pytest.fixture
    def mock_cache(self, tmp_path):
        """Mock 캐시."""
        return LLMCache(str(tmp_path / "test_cache.db"), ttl_hours=1)

    @pytest.fixture
    def client(self, mock_config, mock_cache):
        """테스트용 클라이언트."""
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel"):
                client = GeminiClient(config=mock_config, cache=mock_cache)
                return client

    @pytest.mark.asyncio
    async def test_generate_basic(self, client):
        """기본 텍스트 생성 테스트."""
        # Mock API 응답
        mock_response = MagicMock()
        mock_response.text = "Hello, world!"
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.candidates_token_count = 5

        client.model.generate_content = MagicMock(return_value=mock_response)

        response = await client.generate("Say hello", use_cache=False)

        assert response.text == "Hello, world!"
        assert response.input_tokens == 10
        assert response.output_tokens == 5
        assert response.cached is False

    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self, client):
        """시스템 프롬프트 포함 생성 테스트."""
        mock_response = MagicMock()
        mock_response.text = "I am a helpful assistant."
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 20
        mock_response.usage_metadata.candidates_token_count = 10

        client.model.generate_content = MagicMock(return_value=mock_response)

        response = await client.generate(
            prompt="Introduce yourself",
            system="You are a helpful assistant.",
            use_cache=False
        )

        assert response.text == "I am a helpful assistant."

    @pytest.mark.asyncio
    async def test_generate_json_valid(self, client):
        """유효한 JSON 생성 테스트."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"}
            }
        }

        mock_response = MagicMock()
        mock_response.text = '{"name": "John", "age": 30}'
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 50
        mock_response.usage_metadata.candidates_token_count = 20

        client.model.generate_content = MagicMock(return_value=mock_response)

        result = await client.generate_json(
            prompt="Get user info",
            schema=schema,
            use_cache=False
        )

        assert result["name"] == "John"
        assert result["age"] == 30

    @pytest.mark.asyncio
    async def test_generate_json_with_markdown_wrapper(self, client):
        """마크다운 코드 블록 포함 JSON 파싱 테스트."""
        schema = {"type": "object", "properties": {"value": {"type": "integer"}}}

        mock_response = MagicMock()
        mock_response.text = '```json\n{"value": 42}\n```'
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 30
        mock_response.usage_metadata.candidates_token_count = 15

        client.model.generate_content = MagicMock(return_value=mock_response)

        result = await client.generate_json(
            prompt="Get value",
            schema=schema,
            use_cache=False
        )

        assert result["value"] == 42

    @pytest.mark.asyncio
    async def test_cache_hit(self, client, mock_cache):
        """캐시 히트 테스트."""
        # 캐시에 미리 저장
        cache_key = generate_cache_key(
            operation="generate",
            content="Test prompt",
            params={"system": None}
        )
        await mock_cache.set(
            cache_key=cache_key,
            response={"text": "Cached response"},
            operation="generate",
            input_tokens=10,
            output_tokens=5
        )

        response = await client.generate("Test prompt", use_cache=True)

        assert response.text == "Cached response"
        assert response.cached is True

    @pytest.mark.asyncio
    async def test_batch_generation(self, client):
        """배치 생성 테스트."""
        mock_response = MagicMock()
        mock_response.text = "Response"
        mock_response.usage_metadata = MagicMock()
        mock_response.usage_metadata.prompt_token_count = 10
        mock_response.usage_metadata.candidates_token_count = 5

        client.model.generate_content = MagicMock(return_value=mock_response)

        requests = [
            {"prompt": "Question 1"},
            {"prompt": "Question 2"},
            {"prompt": "Question 3"}
        ]

        responses = await client.generate_batch(requests)

        assert len(responses) == 3

    def test_get_cost_summary(self, client):
        """비용 요약 테스트."""
        client.cost_tracker.record(input_tokens=1000, output_tokens=500)
        client.cost_tracker.record(input_tokens=2000, output_tokens=1000, cached=True)

        summary = client.get_cost_summary()

        assert summary["total_input_tokens"] == 3000
        assert summary["total_output_tokens"] == 1500
        assert summary["total_requests"] == 2
        assert summary["cached_requests"] == 1

    def test_reset_cost_tracker(self, client):
        """비용 추적 초기화 테스트."""
        client.cost_tracker.record(input_tokens=1000, output_tokens=500)
        client.reset_cost_tracker()

        summary = client.get_cost_summary()
        assert summary["total_requests"] == 0


class TestLLMCache:
    """LLMCache 테스트."""

    @pytest.fixture
    async def cache(self, tmp_path):
        """테스트용 캐시."""
        cache = LLMCache(str(tmp_path / "test_cache.db"), ttl_hours=1)
        yield cache

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """저장 및 조회 테스트."""
        await cache.set(
            cache_key="test_key",
            response={"text": "test response"},
            operation="test"
        )

        result = await cache.get("test_key")

        assert result is not None
        assert result["response"]["text"] == "test response"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache):
        """존재하지 않는 키 조회 테스트."""
        result = await cache.get("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate(self, cache):
        """무효화 테스트."""
        await cache.set(
            cache_key="test_key",
            response={"text": "test"},
            operation="test"
        )
        await cache.invalidate("test_key")

        result = await cache.get("test_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_by_operation(self, cache):
        """작업 유형으로 무효화 테스트."""
        await cache.set("key1", {"text": "1"}, operation="type_a")
        await cache.set("key2", {"text": "2"}, operation="type_a")
        await cache.set("key3", {"text": "3"}, operation="type_b")

        deleted = await cache.invalidate_by_operation("type_a")

        assert deleted == 2
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert await cache.get("key3") is not None

    @pytest.mark.asyncio
    async def test_get_stats(self, cache):
        """통계 조회 테스트."""
        await cache.set("key1", {"text": "1"}, operation="test")
        await cache.set("key2", {"text": "2"}, operation="test")

        stats = await cache.get_stats()

        assert stats.total_entries == 2

    @pytest.mark.asyncio
    async def test_log_cost(self, cache):
        """비용 로그 테스트."""
        await cache.log_cost("test", input_tokens=100, output_tokens=50)
        await cache.log_cost("test", input_tokens=200, output_tokens=100)

        summary = await cache.get_cost_summary()

        assert summary["total_input_tokens"] == 300
        assert summary["total_output_tokens"] == 150
        assert summary["total_requests"] == 2


class TestGenerateCacheKey:
    """캐시 키 생성 테스트."""

    def test_same_input_same_key(self):
        """동일 입력 시 동일 키."""
        key1 = generate_cache_key("op", "content", {"param": "value"})
        key2 = generate_cache_key("op", "content", {"param": "value"})
        assert key1 == key2

    def test_different_operation_different_key(self):
        """다른 작업 시 다른 키."""
        key1 = generate_cache_key("op1", "content")
        key2 = generate_cache_key("op2", "content")
        assert key1 != key2

    def test_different_content_different_key(self):
        """다른 콘텐츠 시 다른 키."""
        key1 = generate_cache_key("op", "content1")
        key2 = generate_cache_key("op", "content2")
        assert key1 != key2

    def test_key_is_sha256(self):
        """키가 SHA256 형식인지 확인."""
        key = generate_cache_key("op", "content")
        assert len(key) == 64  # SHA256 hex digest
        assert all(c in "0123456789abcdef" for c in key)

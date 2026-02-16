"""Claude API Client.

Anthropic Claude API 클라이언트.
네이티브 async 지원, JSON 구조화 출력, 적절한 에러 핸들링 포함.
GeminiClient와 동일한 인터페이스 제공.

Usage:
    # 기본 사용
    client = ClaudeClient()
    response = await client.generate("What is 2+2?")

    # JSON 출력
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    result = await client.generate_json("What is 2+2?", schema)

    # 시스템 프롬프트
    response = await client.generate("Hello", system="You are a helpful assistant")
"""

import asyncio
import json
import os
import time
import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, Any

import anthropic

from core.exceptions import LLMError
from .cache import LLMCache, generate_cache_key

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class ClaudeConfig:
    """Claude API 설정."""
    api_key: str = ""
    model: str = "claude-haiku-4-5-20251001"
    fallback_model: str = "claude-sonnet-4-5-20250929"
    auto_fallback: bool = True
    max_retries: int = 3
    requests_per_minute: int = 1000
    tokens_per_minute: int = 400_000
    timeout: float = 120.0
    temperature: float = 0.1
    max_output_tokens: int = 8192

    def __post_init__(self):
        """환경변수에서 API 키 및 모델 설정 로드."""
        if not self.api_key:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다. "
                "export ANTHROPIC_API_KEY='your-api-key' 또는 "
                "ClaudeConfig(api_key='your-key')로 설정하세요."
            )

        # 환경변수에서 모델 설정 로드
        env_model = os.environ.get("CLAUDE_MODEL", "")
        if env_model:
            self.model = env_model

        # 환경변수에서 폴백 모델 설정 로드
        env_fallback = os.environ.get("CLAUDE_FALLBACK_MODEL", "")
        if env_fallback:
            self.fallback_model = env_fallback


# =============================================================================
# Response Types
# =============================================================================

@dataclass
class ClaudeResponse:
    """Claude API 응답."""
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cached: bool = False
    model: str = ""
    fallback_used: bool = False


@dataclass
class CostTracker:
    """비용 추적.

    Claude Haiku 4.5: $1 / $5 per M tokens (input / output)
    Claude Sonnet 4.5: $3 / $15 per M tokens (input / output)
    """
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_requests: int = 0
    cached_requests: int = 0
    haiku_input_tokens: int = 0
    haiku_output_tokens: int = 0
    sonnet_input_tokens: int = 0
    sonnet_output_tokens: int = 0

    @property
    def estimated_cost(self) -> float:
        """예상 비용 (USD)."""
        # Haiku 비용
        haiku_cost = (
            (self.haiku_input_tokens / 1_000_000) * 1.0 +
            (self.haiku_output_tokens / 1_000_000) * 5.0
        )
        # Sonnet 비용
        sonnet_cost = (
            (self.sonnet_input_tokens / 1_000_000) * 3.0 +
            (self.sonnet_output_tokens / 1_000_000) * 15.0
        )
        return round(haiku_cost + sonnet_cost, 4)

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "haiku",
        cached: bool = False
    ) -> None:
        """사용량 기록."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_requests += 1
        if cached:
            self.cached_requests += 1

        # 모델별 토큰 추적
        if "sonnet" in model.lower():
            self.sonnet_input_tokens += input_tokens
            self.sonnet_output_tokens += output_tokens
        else:
            self.haiku_input_tokens += input_tokens
            self.haiku_output_tokens += output_tokens

    def reset(self) -> None:
        """초기화."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.cached_requests = 0
        self.haiku_input_tokens = 0
        self.haiku_output_tokens = 0
        self.sonnet_input_tokens = 0
        self.sonnet_output_tokens = 0


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """토큰 버킷 기반 Rate Limiter."""

    def __init__(self, requests_per_minute: int, tokens_per_minute: int):
        self.rpm = requests_per_minute
        self.tpm = tokens_per_minute
        self.request_times: deque = deque()
        self.token_usage: deque = deque()
        self.semaphore = asyncio.Semaphore(5)
        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 1000) -> None:
        """Rate limit 획득.

        Lock is released before sleeping to avoid blocking other coroutines.
        After sleeping, the loop re-checks conditions under a fresh lock.
        """
        async with self.semaphore:
            while True:
                wait_time = 0.0
                async with self._lock:
                    now = time.time()

                    # 1분 이전 기록 제거
                    while self.request_times and self.request_times[0] < now - 60:
                        self.request_times.popleft()
                    while self.token_usage and self.token_usage[0][0] < now - 60:
                        self.token_usage.popleft()

                    # RPM 체크
                    if len(self.request_times) >= self.rpm:
                        wait_time = 60 - (now - self.request_times[0])
                        if wait_time > 0:
                            pass  # will sleep outside the lock
                        else:
                            wait_time = 0.0

                    # TPM 체크 (only if RPM is not already limiting)
                    if wait_time <= 0:
                        current_tokens = sum(t[1] for t in self.token_usage)
                        if current_tokens + estimated_tokens > self.tpm:
                            wait_time = 60 - (now - self.token_usage[0][0])
                            if wait_time <= 0:
                                wait_time = 0.0

                    # No wait needed — record request and proceed
                    if wait_time <= 0:
                        self.request_times.append(time.time())
                        return

                # Sleep outside the lock so other coroutines can proceed
                await asyncio.sleep(wait_time)

    async def record_usage(self, tokens: int) -> None:
        """토큰 사용량 기록 (thread-safe with lock)."""
        async with self._lock:
            self.token_usage.append((time.time(), tokens))


# =============================================================================
# Claude Client
# =============================================================================

class ClaudeClient:
    """Claude API 클라이언트.

    GeminiClient와 동일한 인터페이스를 제공합니다.
    Haiku로 먼저 시도하고, 토큰 초과 시 자동으로 Sonnet으로 폴백합니다.
    """

    def __init__(
        self,
        config: ClaudeConfig = None,
        cache: LLMCache = None
    ):
        """초기화.

        Args:
            config: API 설정 (None이면 환경변수에서 로드)
            cache: LLM 캐시 인스턴스
        """
        self.config = config or ClaudeConfig()
        self.cache = cache
        self.cost_tracker = CostTracker()
        self.rate_limiter = RateLimiter(
            self.config.requests_per_minute,
            self.config.tokens_per_minute
        )

        # Anthropic 클라이언트 초기화
        self.client = anthropic.Anthropic(api_key=self.config.api_key)

        logger.info(
            f"ClaudeClient initialized: model={self.config.model}, "
            f"fallback={self.config.fallback_model}, auto_fallback={self.config.auto_fallback}"
        )

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        use_cache: bool = True
    ) -> ClaudeResponse:
        """텍스트 생성.

        Args:
            prompt: 사용자 프롬프트
            system: 시스템 프롬프트 (선택)
            use_cache: 캐시 사용 여부

        Returns:
            ClaudeResponse 객체
        """
        # 캐시 키 생성
        cache_key = generate_cache_key(
            operation="generate",
            content=prompt,
            params={"system": system}
        )

        # 캐시 확인
        if use_cache and self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                self.cost_tracker.record(
                    cached["input_tokens"],
                    cached["output_tokens"],
                    model=self.config.model,
                    cached=True
                )
                return ClaudeResponse(
                    text=cached["response"]["text"],
                    input_tokens=cached["input_tokens"],
                    output_tokens=cached["output_tokens"],
                    latency_ms=0,
                    cached=True,
                    model=self.config.model
                )

        # Rate limiting
        await self.rate_limiter.acquire()

        # API 호출 with retry
        start_time = time.time()
        response = await self._call_api_with_retry(prompt, system)
        latency_ms = (time.time() - start_time) * 1000

        # 토큰 사용량 기록
        input_tokens = response.get("input_tokens", 0)
        output_tokens = response.get("output_tokens", 0)
        model_used = response.get("model", self.config.model)
        fallback_used = response.get("fallback_used", False)

        await self.rate_limiter.record_usage(input_tokens + output_tokens)
        self.cost_tracker.record(input_tokens, output_tokens, model=model_used)

        # 캐시 저장
        if use_cache and self.cache:
            await self.cache.set(
                cache_key=cache_key,
                response={"text": response["text"]},
                operation="generate",
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            await self.cache.log_cost(
                operation="generate",
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )

        return ClaudeResponse(
            text=response["text"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cached=False,
            model=model_used,
            fallback_used=fallback_used
        )

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        use_cache: bool = True
    ) -> dict:
        """JSON 구조화 출력 생성.

        Args:
            prompt: 사용자 프롬프트
            schema: JSON 스키마 (dict)
            system: 시스템 프롬프트 (선택)
            use_cache: 캐시 사용 여부

        Returns:
            파싱된 JSON 딕셔너리
        """
        # 캐시 키 생성
        cache_key = generate_cache_key(
            operation="generate_json",
            content=prompt,
            params={"system": system, "schema": str(schema)}
        )

        # 캐시 확인
        if use_cache and self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                self.cost_tracker.record(
                    cached["input_tokens"],
                    cached["output_tokens"],
                    model=self.config.model,
                    cached=True
                )
                return cached["response"]

        # Rate limiting
        await self.rate_limiter.acquire()

        # JSON 프롬프트 구성
        json_prompt = f"""{prompt}

Please respond with a valid JSON object following this schema:
{json.dumps(schema, indent=2)}

Respond ONLY with the JSON object, no additional text or markdown formatting."""

        # API 호출 with retry
        start_time = time.time()
        result = await self._call_api_with_retry(json_prompt, system)
        latency_ms = (time.time() - start_time) * 1000

        # JSON 파싱
        text = result["text"]

        # JSON 블록 추출
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}\nText: {text[:200]}", exc_info=True)
            data = {}

        # 토큰 사용량 기록
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        model_used = result.get("model", self.config.model)

        await self.rate_limiter.record_usage(input_tokens + output_tokens)
        self.cost_tracker.record(input_tokens, output_tokens, model=model_used)

        # 캐시 저장
        if use_cache and self.cache:
            await self.cache.set(
                cache_key=cache_key,
                response=data,
                operation="generate_json",
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )

        return data

    async def _call_api_with_retry(
        self,
        prompt: str,
        system: Optional[str] = None
    ) -> dict:
        """API 호출 with retry 및 자동 폴백.

        Args:
            prompt: 사용자 프롬프트
            system: 시스템 프롬프트

        Returns:
            응답 딕셔너리
        """
        last_error = None
        model = self.config.model
        fallback_used = False

        for attempt in range(self.config.max_retries):
            try:
                result = await self._call_api(prompt, system, model)

                # 토큰 초과 체크 및 폴백
                if (result.get("stop_reason") == "max_tokens" and
                    self.config.auto_fallback and
                    model != self.config.fallback_model):

                    logger.warning(
                        f"Token overflow detected ({result.get('output_tokens', 0)} tokens). "
                        f"Retrying with fallback model: {self.config.fallback_model}"
                    )
                    model = self.config.fallback_model
                    result = await self._call_api(prompt, system, model)
                    fallback_used = True

                result["model"] = model
                result["fallback_used"] = fallback_used
                return result

            except anthropic.RateLimitError as e:
                last_error = e
                logger.warning(f"Rate limit (시도 {attempt + 1}/{self.config.max_retries}): {e}")
                wait_time = min(2 ** attempt * 5, 60)
                logger.info(f"{wait_time}초 후 재시도...")
                await asyncio.sleep(wait_time)
                continue

            except anthropic.APIStatusError as e:
                last_error = e
                logger.warning(f"API 에러 (시도 {attempt + 1}/{self.config.max_retries}): {e.status_code}")

                if e.status_code in [500, 502, 503, 504, 529]:
                    wait_time = min(2 ** attempt, 30)
                    logger.info(f"{wait_time}초 후 재시도...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                logger.warning(f"예외 발생 (시도 {attempt + 1}/{self.config.max_retries}): {e}")

                if any(kw in error_str for kw in ['dns', 'network', 'connection', 'timeout']):
                    wait_time = min(2 ** attempt, 30)
                    logger.info(f"네트워크 오류, {wait_time}초 후 재시도...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

        raise last_error or Exception("모든 재시도 실패")

    async def _call_api(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None
    ) -> dict:
        """단일 API 호출.

        Args:
            prompt: 사용자 프롬프트
            system: 시스템 프롬프트
            model: 사용할 모델 (None이면 config.model 사용)

        Returns:
            응답 딕셔너리
        """
        model = model or self.config.model

        # 동기 API를 비동기로 실행
        loop = asyncio.get_event_loop()

        def sync_call():
            kwargs = {
                "model": model,
                "max_tokens": self.config.max_output_tokens,
                "messages": [{"role": "user", "content": prompt}]
            }

            if system:
                kwargs["system"] = system

            if self.config.temperature is not None:
                kwargs["temperature"] = self.config.temperature

            return self.client.messages.create(**kwargs)

        message = await loop.run_in_executor(None, sync_call)

        return {
            "text": message.content[0].text,
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "stop_reason": message.stop_reason,
            "model": model
        }

    async def generate_batch(
        self,
        requests: list[dict],
        concurrency: int = 5
    ) -> list[ClaudeResponse]:
        """배치 생성 (병렬 처리).

        Args:
            requests: 요청 목록 [{"prompt": ..., "system": ..., "schema": ...}, ...]
            concurrency: 동시 요청 수

        Returns:
            ClaudeResponse 목록 (입력 순서 유지)
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def process_request(idx: int, req: dict) -> tuple[int, ClaudeResponse]:
            async with semaphore:
                if "schema" in req:
                    result = await self.generate_json(
                        prompt=req["prompt"],
                        schema=req["schema"],
                        system=req.get("system"),
                        use_cache=req.get("use_cache", True)
                    )
                    return idx, ClaudeResponse(
                        text=json.dumps(result),
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=0,
                        cached=False,
                        model=self.config.model
                    )
                else:
                    response = await self.generate(
                        prompt=req["prompt"],
                        system=req.get("system"),
                        use_cache=req.get("use_cache", True)
                    )
                    return idx, response

        tasks = [process_request(i, req) for i, req in enumerate(requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # v1.15: 순서 정렬 및 에러 처리 — 실패 시 None 유지하여 인덱스 보존
        sorted_results: list[tuple[int, Optional[ClaudeResponse]]] = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"배치 요청 실패: {r}", exc_info=True)
                continue
            sorted_results.append(r)

        sorted_results.sort(key=lambda x: x[0])
        return [r[1] for r in sorted_results]

    def get_cost_summary(self) -> dict:
        """비용 요약 반환.

        Returns:
            비용 요약 딕셔너리
        """
        return {
            "total_input_tokens": self.cost_tracker.total_input_tokens,
            "total_output_tokens": self.cost_tracker.total_output_tokens,
            "total_requests": self.cost_tracker.total_requests,
            "cached_requests": self.cost_tracker.cached_requests,
            "haiku_tokens": {
                "input": self.cost_tracker.haiku_input_tokens,
                "output": self.cost_tracker.haiku_output_tokens
            },
            "sonnet_tokens": {
                "input": self.cost_tracker.sonnet_input_tokens,
                "output": self.cost_tracker.sonnet_output_tokens
            },
            "estimated_cost_usd": self.cost_tracker.estimated_cost
        }

    def reset_cost_tracker(self) -> None:
        """비용 추적 초기화."""
        self.cost_tracker.reset()


# =============================================================================
# Compatibility Aliases (for drop-in replacement)
# =============================================================================

# GeminiClient와 호환되는 별칭
LLMClient = ClaudeClient
LLMConfig = ClaudeConfig
LLMResponse = ClaudeResponse

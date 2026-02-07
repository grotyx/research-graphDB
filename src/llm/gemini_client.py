"""Gemini API Client.

새로운 google-genai SDK를 사용한 Gemini API 클라이언트.
네이티브 async 지원, JSON 구조화 출력, 적절한 에러 핸들링 포함.
"""

import asyncio
import os
import time
import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional, Any, Type

from google import genai
from google.genai import types, errors
from pydantic import BaseModel

from .cache import LLMCache, generate_cache_key

logger = logging.getLogger(__name__)


@dataclass
class GeminiConfig:
    """Gemini API 설정."""
    api_key: str = ""
    model: str = "gemini-2.5-flash"
    max_retries: int = 3
    requests_per_minute: int = 2000
    tokens_per_minute: int = 4_000_000
    timeout: float = 60.0
    temperature: float = 0.1
    max_output_tokens: int = 8192

    def __post_init__(self):
        """환경변수에서 API 키 로드."""
        if not self.api_key:
            self.api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY 환경변수가 설정되지 않았습니다. "
                "export GEMINI_API_KEY='your-api-key' 또는 "
                "GeminiConfig(api_key='your-key')로 설정하세요."
            )


@dataclass
class GeminiResponse:
    """Gemini API 응답."""
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cached: bool = False
    model: str = ""


@dataclass
class CostTracker:
    """비용 추적."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_requests: int = 0
    cached_requests: int = 0

    @property
    def estimated_cost(self) -> float:
        """예상 비용 (USD)."""
        input_cost = (self.total_input_tokens / 1_000_000) * 0.15
        output_cost = (self.total_output_tokens / 1_000_000) * 0.60
        return round(input_cost + output_cost, 4)

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        cached: bool = False
    ) -> None:
        """사용량 기록."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_requests += 1
        if cached:
            self.cached_requests += 1

    def reset(self) -> None:
        """초기화."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.cached_requests = 0


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
        """Rate limit 획득."""
        async with self.semaphore:
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
                        await asyncio.sleep(wait_time)

                # TPM 체크
                current_tokens = sum(t[1] for t in self.token_usage)
                if current_tokens + estimated_tokens > self.tpm:
                    wait_time = 60 - (now - self.token_usage[0][0])
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)

                self.request_times.append(time.time())

    def record_usage(self, tokens: int) -> None:
        """토큰 사용량 기록."""
        self.token_usage.append((time.time(), tokens))


class GeminiClient:
    """Gemini API 클라이언트 (새로운 google-genai SDK 사용)."""

    def __init__(
        self,
        config: GeminiConfig = None,
        cache: LLMCache = None
    ):
        """초기화.

        Args:
            config: API 설정 (None이면 환경변수에서 로드)
            cache: LLM 캐시 인스턴스
        """
        self.config = config or GeminiConfig()
        self.cache = cache
        self.cost_tracker = CostTracker()
        self.rate_limiter = RateLimiter(
            self.config.requests_per_minute,
            self.config.tokens_per_minute
        )

        # 새로운 google-genai Client 초기화
        self.client = genai.Client(api_key=self.config.api_key)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        use_cache: bool = True
    ) -> GeminiResponse:
        """텍스트 생성 (네이티브 async).

        Args:
            prompt: 사용자 프롬프트
            system: 시스템 프롬프트 (선택)
            use_cache: 캐시 사용 여부

        Returns:
            GeminiResponse 객체
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
                    cached=True
                )
                return GeminiResponse(
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
        self.rate_limiter.record_usage(input_tokens + output_tokens)
        self.cost_tracker.record(input_tokens, output_tokens)

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

        return GeminiResponse(
            text=response["text"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cached=False,
            model=self.config.model
        )

    async def generate_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None,
        use_cache: bool = True
    ) -> dict:
        """JSON 구조화 출력 생성 (네이티브 async).

        Args:
            prompt: 사용자 프롬프트
            schema: JSON 스키마 (dict 또는 Pydantic model)
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
                    cached=True
                )
                return cached["response"]

        # Rate limiting
        await self.rate_limiter.acquire()

        # API 호출 with retry
        start_time = time.time()
        result = await self._call_api_json_with_retry(prompt, schema, system)
        latency_ms = (time.time() - start_time) * 1000

        # 토큰 사용량 기록
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        self.rate_limiter.record_usage(input_tokens + output_tokens)
        self.cost_tracker.record(input_tokens, output_tokens)

        # 캐시 저장
        if use_cache and self.cache:
            await self.cache.set(
                cache_key=cache_key,
                response=result["data"],
                operation="generate_json",
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )

        return result["data"]

    async def _call_api_with_retry(
        self,
        prompt: str,
        system: Optional[str] = None
    ) -> dict:
        """API 호출 with retry.

        Args:
            prompt: 사용자 프롬프트
            system: 시스템 프롬프트

        Returns:
            응답 딕셔너리
        """
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                return await self._call_api(prompt, system)

            except errors.APIError as e:
                last_error = e
                logger.warning(f"API 에러 (시도 {attempt + 1}/{self.config.max_retries}): {e.code} - {e.message}")

                # 재시도 가능한 에러인지 확인
                if e.code in [429, 500, 502, 503, 504]:
                    wait_time = min(2 ** attempt, 30)
                    logger.info(f"{wait_time}초 후 재시도...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # 재시도 불가능한 에러
                    raise

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                logger.warning(f"예외 발생 (시도 {attempt + 1}/{self.config.max_retries}): {e}")

                # 네트워크 관련 에러 확인
                if any(kw in error_str for kw in ['dns', 'network', 'connection', 'timeout', 'unavailable']):
                    wait_time = min(2 ** attempt, 30)
                    logger.info(f"네트워크 오류, {wait_time}초 후 재시도...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

        # 모든 재시도 실패
        raise last_error or Exception("모든 재시도 실패")

    async def _call_api(self, prompt: str, system: Optional[str] = None) -> dict:
        """단일 API 호출 (네이티브 async).

        Args:
            prompt: 사용자 프롬프트
            system: 시스템 프롬프트

        Returns:
            응답 딕셔너리
        """
        # 설정 구성
        config = types.GenerateContentConfig(
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
        )

        # 시스템 지시사항 추가
        if system:
            config.system_instruction = system

        # 네이티브 async 호출
        response = await self.client.aio.models.generate_content(
            model=self.config.model,
            contents=prompt,
            config=config
        )

        # 토큰 수 추출
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        return {
            "text": response.text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    async def _call_api_json_with_retry(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None
    ) -> dict:
        """JSON API 호출 with retry.

        Args:
            prompt: 사용자 프롬프트
            schema: JSON 스키마
            system: 시스템 프롬프트

        Returns:
            {"data": 파싱된 JSON, "input_tokens": int, "output_tokens": int}
        """
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                return await self._call_api_json(prompt, schema, system)

            except errors.APIError as e:
                last_error = e
                logger.warning(f"API 에러 (시도 {attempt + 1}/{self.config.max_retries}): {e.code} - {e.message}")

                if e.code in [429, 500, 502, 503, 504]:
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

                if any(kw in error_str for kw in ['dns', 'network', 'connection', 'timeout', 'unavailable']):
                    wait_time = min(2 ** attempt, 30)
                    logger.info(f"네트워크 오류, {wait_time}초 후 재시도...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

        raise last_error or Exception("모든 재시도 실패")

    async def _call_api_json(
        self,
        prompt: str,
        schema: dict,
        system: Optional[str] = None
    ) -> dict:
        """단일 JSON API 호출 (네이티브 async).

        Args:
            prompt: 사용자 프롬프트
            schema: JSON 스키마
            system: 시스템 프롬프트

        Returns:
            {"data": 파싱된 JSON, "input_tokens": int, "output_tokens": int}
        """
        import json

        # 설정 구성 (JSON 모드)
        config = types.GenerateContentConfig(
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema
        )

        # 시스템 지시사항 추가
        if system:
            config.system_instruction = system

        # 네이티브 async 호출
        response = await self.client.aio.models.generate_content(
            model=self.config.model,
            contents=prompt,
            config=config
        )

        # 토큰 수 추출
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        # JSON 파싱
        text = response.text
        if isinstance(text, str):
            data = json.loads(text)
        else:
            data = text

        return {
            "data": data,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    async def generate_batch(
        self,
        requests: list[dict],
        concurrency: int = 10
    ) -> list[GeminiResponse]:
        """배치 생성 (병렬 처리).

        Args:
            requests: 요청 목록 [{"prompt": ..., "system": ..., "schema": ...}, ...]
            concurrency: 동시 요청 수

        Returns:
            GeminiResponse 목록 (입력 순서 유지)
        """
        import json

        semaphore = asyncio.Semaphore(concurrency)

        async def process_request(idx: int, req: dict) -> tuple[int, GeminiResponse]:
            async with semaphore:
                if "schema" in req:
                    result = await self.generate_json(
                        prompt=req["prompt"],
                        schema=req["schema"],
                        system=req.get("system"),
                        use_cache=req.get("use_cache", True)
                    )
                    return idx, GeminiResponse(
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

        # 순서 정렬 및 에러 처리
        sorted_results = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"배치 요청 실패: {r}")
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
            "estimated_cost_usd": self.cost_tracker.estimated_cost
        }

    def reset_cost_tracker(self) -> None:
        """비용 추적 초기화."""
        self.cost_tracker.reset()

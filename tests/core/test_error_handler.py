"""Tests for core.error_handler — CircuitBreaker, retry, fallback, ErrorReporter."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from core.error_handler import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    ConfigurationError,
    DegradedResponse,
    ErrorReporter,
    LLMRateLimitError,
    LLMTimeoutError,
    Neo4jConnectionError,
    PDFProcessingError,
    RetryConfig,
    ServiceUnavailableError,
    SpineGraphError,
    get_error_reporter,
    with_fallback,
    with_retry,
)


# ── Exception hierarchy ─────────────────────────────────────────────────

class TestExceptionHierarchy:
    def test_spine_graph_error_alias(self):
        from core.exceptions import MedicalRAGError
        assert SpineGraphError is MedicalRAGError

    def test_neo4j_connection_error(self):
        err = Neo4jConnectionError("connection lost")
        assert "connection lost" in str(err)

    def test_llm_rate_limit_details(self):
        err = LLMRateLimitError("too many requests", retry_after=30)
        assert err.details["retry_after"] == 30

    def test_pdf_processing_error(self):
        err = PDFProcessingError("bad pdf")
        assert isinstance(err, Exception)

    def test_configuration_error(self):
        err = ConfigurationError("missing key")
        assert "missing key" in str(err)

    def test_service_unavailable_includes_service(self):
        err = ServiceUnavailableError("down", service="neo4j")
        assert err.details["service"] == "neo4j"


# ── RetryConfig ─────────────────────────────────────────────────────────

class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_retries == 3
        assert cfg.initial_delay == 1.0
        assert cfg.max_delay == 60.0
        assert cfg.exponential_base == 2.0
        assert cfg.jitter is True

    def test_calculate_delay_exponential(self):
        cfg = RetryConfig(initial_delay=1.0, exponential_base=2.0, jitter=False)
        assert cfg.calculate_delay(0) == 1.0   # 1 * 2^0
        assert cfg.calculate_delay(1) == 2.0   # 1 * 2^1
        assert cfg.calculate_delay(2) == 4.0   # 1 * 2^2
        assert cfg.calculate_delay(3) == 8.0   # 1 * 2^3

    def test_calculate_delay_capped_at_max(self):
        cfg = RetryConfig(initial_delay=1.0, exponential_base=2.0, max_delay=5.0, jitter=False)
        assert cfg.calculate_delay(10) == 5.0

    def test_calculate_delay_with_jitter(self):
        cfg = RetryConfig(initial_delay=4.0, exponential_base=1.0, jitter=True)
        # With jitter ±25%, delay should be in [3.0, 5.0]
        delays = [cfg.calculate_delay(0) for _ in range(50)]
        assert all(3.0 <= d <= 5.0 for d in delays)

    def test_delay_never_negative(self):
        cfg = RetryConfig(initial_delay=0.01, jitter=True)
        for attempt in range(10):
            assert cfg.calculate_delay(attempt) >= 0


# ── CircuitBreaker states ───────────────────────────────────────────────

class TestCircuitBreakerInit:
    def test_initial_state_closed(self):
        cb = CircuitBreaker("test_svc")
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.success_count == 0

    def test_custom_config(self):
        cfg = CircuitBreakerConfig(failure_threshold=10, timeout=120.0)
        cb = CircuitBreaker("svc", config=cfg)
        assert cb.config.failure_threshold == 10
        assert cb.config.timeout == 120.0


class TestCircuitBreakerTransitions:
    @pytest.mark.asyncio
    async def test_closed_to_open_after_threshold(self):
        cfg = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("svc", config=cfg)

        async def failing():
            raise ValueError("boom")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(failing)

        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 3

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, timeout=9999)
        cb = CircuitBreaker("svc", config=cfg)

        async def failing():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(failing)

        assert cb.state == CircuitState.OPEN

        with pytest.raises(ServiceUnavailableError):
            await cb.call(failing)

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_timeout(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, timeout=0.0)
        cb = CircuitBreaker("svc", config=cfg)

        async def failing():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(failing)
        assert cb.state == CircuitState.OPEN

        # timeout=0 means it transitions immediately to HALF_OPEN
        async def succeeding():
            return "ok"

        result = await cb.call(succeeding)
        # After the call, state check inside `call` moves to HALF_OPEN,
        # then the successful call progresses toward CLOSED
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_half_open_to_closed_after_success_threshold(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout=0.0)
        cb = CircuitBreaker("svc", config=cfg)

        async def failing():
            raise ValueError("boom")

        async def succeeding():
            return "ok"

        # Open the circuit
        with pytest.raises(ValueError):
            await cb.call(failing)
        assert cb.state == CircuitState.OPEN

        # First success in half-open
        await cb.call(succeeding)
        # Might still be HALF_OPEN (need success_threshold=2)

        # Second success should close it
        await cb.call(succeeding)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self):
        cfg = CircuitBreakerConfig(failure_threshold=1, timeout=0.0)
        cb = CircuitBreaker("svc", config=cfg)

        async def failing():
            raise ValueError("boom")

        # CLOSED → OPEN
        with pytest.raises(ValueError):
            await cb.call(failing)
        assert cb.state == CircuitState.OPEN

        # OPEN → HALF_OPEN (timeout=0) → failure → OPEN again
        with pytest.raises(ValueError):
            await cb.call(failing)
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cfg = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("svc", config=cfg)

        async def failing():
            raise ValueError("boom")

        async def succeeding():
            return "ok"

        # Accumulate some failures (not enough to open)
        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(failing)
        assert cb.failure_count == 3

        # A success resets the counter
        await cb.call(succeeding)
        assert cb.failure_count == 0


class TestCircuitBreakerGetState:
    @pytest.mark.asyncio
    async def test_get_state_initial(self):
        cb = CircuitBreaker("my_service")
        state = cb.get_state()
        assert state["name"] == "my_service"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["last_failure"] is None
        assert state["opened_at"] is None

    @pytest.mark.asyncio
    async def test_get_state_after_failure(self):
        cb = CircuitBreaker("svc", CircuitBreakerConfig(failure_threshold=10))

        async def failing():
            raise RuntimeError("err")

        with pytest.raises(RuntimeError):
            await cb.call(failing)

        state = cb.get_state()
        assert state["failure_count"] == 1
        assert state["last_failure"] is not None


# ── with_retry decorator ────────────────────────────────────────────────

class TestWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_without_retry(self):
        call_count = 0

        @with_retry(RetryConfig(max_retries=3))
        async def good_func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await good_func()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_retryable_exception(self):
        call_count = 0

        @with_retry(RetryConfig(max_retries=2, initial_delay=0.01, jitter=False))
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = await flaky_func()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        @with_retry(RetryConfig(max_retries=2, initial_delay=0.01, jitter=False))
        async def always_fails():
            raise TimeoutError("always timeout")

        with pytest.raises(TimeoutError):
            await always_fails()

    @pytest.mark.asyncio
    async def test_non_retryable_exception_raises_immediately(self):
        call_count = 0

        @with_retry(RetryConfig(max_retries=5, initial_delay=0.01))
        async def bad_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await bad_func()
        assert call_count == 1  # No retries for ValueError

    @pytest.mark.asyncio
    async def test_custom_retryable_exceptions(self):
        call_count = 0

        @with_retry(RetryConfig(
            max_retries=2,
            initial_delay=0.01,
            jitter=False,
            retryable_exceptions=(ValueError,),
        ))
        async def func():
            nonlocal call_count
            call_count += 1
            raise ValueError("custom retryable")

        with pytest.raises(ValueError):
            await func()
        assert call_count == 3  # 1 initial + 2 retries


# ── with_fallback ───────────────────────────────────────────────────────

class TestWithFallback:
    @pytest.mark.asyncio
    async def test_primary_success(self):
        async def primary():
            return "primary_data"

        async def fallback():
            return "fallback_data"

        result = await with_fallback(primary, fallback, "cache")
        assert result.success is True
        assert result.data == "primary_data"
        assert result.degraded is False
        assert result.fallback_used is None

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        async def primary():
            raise RuntimeError("primary failed")

        async def fallback():
            return "fallback_data"

        result = await with_fallback(primary, fallback, "cache")
        assert result.success is True
        assert result.data == "fallback_data"
        assert result.degraded is True
        assert result.fallback_used == "cache"
        assert "primary failed" in result.error

    @pytest.mark.asyncio
    async def test_both_fail(self):
        async def primary():
            raise RuntimeError("primary failed")

        async def fallback():
            raise RuntimeError("fallback failed")

        result = await with_fallback(primary, fallback, "cache")
        assert result.success is False
        assert result.degraded is True
        assert "Primary:" in result.error
        assert "Fallback:" in result.error


# ── DegradedResponse ────────────────────────────────────────────────────

class TestDegradedResponse:
    def test_success_response(self):
        resp = DegradedResponse(success=True, data={"key": "val"})
        assert resp.success is True
        assert resp.degraded is False
        assert resp.error is None

    def test_degraded_response(self):
        resp = DegradedResponse(
            success=True,
            data="cached",
            degraded=True,
            error="original failed",
            fallback_used="cache",
        )
        assert resp.degraded is True
        assert resp.fallback_used == "cache"


# ── ErrorReporter ───────────────────────────────────────────────────────

class TestErrorReporter:
    @pytest.mark.asyncio
    async def test_report_and_retrieve(self):
        reporter = ErrorReporter()
        err = ValueError("test error")
        await reporter.report(err, context={"key": "val"})

        recent = await reporter.get_recent_errors(limit=5)
        assert len(recent) == 1
        assert recent[0].error_type == "ValueError"
        assert recent[0].error_message == "test error"
        assert recent[0].context == {"key": "val"}

    @pytest.mark.asyncio
    async def test_max_reports_truncated(self):
        reporter = ErrorReporter(max_reports=5)
        for i in range(10):
            await reporter.report(RuntimeError(f"error {i}"))

        assert len(reporter.reports) == 5
        # Should keep the most recent
        assert reporter.reports[-1].error_message == "error 9"

    @pytest.mark.asyncio
    async def test_get_error_summary(self):
        reporter = ErrorReporter()
        await reporter.report(ValueError("v1"))
        await reporter.report(ValueError("v2"))
        await reporter.report(TypeError("t1"))

        summary = await reporter.get_error_summary()
        assert summary["total_errors"] == 3
        assert summary["error_types"]["ValueError"] == 2
        assert summary["error_types"]["TypeError"] == 1
        assert len(summary["recent_errors"]) == 3

    @pytest.mark.asyncio
    async def test_get_recent_errors_limit(self):
        reporter = ErrorReporter()
        for i in range(20):
            await reporter.report(RuntimeError(f"err {i}"))

        recent = await reporter.get_recent_errors(limit=3)
        assert len(recent) == 3


class TestGlobalErrorReporter:
    def test_singleton_pattern(self):
        # Reset global state for test isolation
        import core.error_handler as mod
        mod._global_reporter = None

        r1 = get_error_reporter()
        r2 = get_error_reporter()
        assert r1 is r2

        # Clean up
        mod._global_reporter = None

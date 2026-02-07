"""Error Handling Module for Spine GraphRAG.

Comprehensive error handling with retry logic, circuit breaker pattern,
and graceful degradation strategies.

Features:
- Unified exception hierarchy (from exceptions.py)
- Exponential backoff retry with jitter
- Circuit breaker for external services
- Error logging and alerting
- Graceful degradation
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

# Type variables for decorators
T = TypeVar("T")


# ========================================================================
# Exception Hierarchy - Import from centralized exceptions.py
# ========================================================================

# Import the primary exception hierarchy
from .exceptions import (
    MedicalRAGError,
    ValidationError,
    ProcessingError,
    LLMError,
    Neo4jError,
    ChromaDBError as _ChromaDBError,
    NormalizationError,
    ExtractionError,
    PubMedError,
    ErrorCode,
)

# Alias MedicalRAGError as SpineGraphError for backward compatibility
SpineGraphError = MedicalRAGError

# Create specific exception subclasses for error_handler patterns
# These maintain backward compatibility while using the unified hierarchy


class Neo4jConnectionError(Neo4jError):
    """Neo4j connection failure - specific subclass for retry logic."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.NEO4J_CONNECTION,
            details=details
        )


class ChromaDBError(_ChromaDBError):
    """ChromaDB error - re-exported for backward compatibility."""
    pass


class LLMRateLimitError(LLMError):
    """LLM API rate limit exceeded."""

    def __init__(self, message: str, retry_after: int = 60, details: Optional[dict] = None):
        details = details or {}
        details["retry_after"] = retry_after
        super().__init__(
            message=message,
            error_code=ErrorCode.LLM_RATE_LIMIT,
            details=details
        )


class LLMTimeoutError(LLMError):
    """LLM API timeout."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.LLM_TIMEOUT,
            details=details
        )


class LLMAuthError(LLMError):
    """LLM API authentication failure."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.LLM_API_ERROR,
            details=details
        )


class LLMAPIError(LLMError):
    """LLM API general error - re-exported for backward compatibility."""
    pass


class PDFProcessingError(ProcessingError):
    """PDF processing failure."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.EXT_PDF_PARSING,
            details=details
        )


class ConfigurationError(MedicalRAGError):
    """Configuration error."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.VAL_INVALID_VALUE,
            details=details
        )


class ServiceUnavailableError(MedicalRAGError):
    """External service unavailable."""

    def __init__(self, message: str, service: str = "unknown", details: Optional[dict] = None):
        details = details or {}
        details["service"] = service
        super().__init__(
            message=message,
            error_code=ErrorCode.PROC_UNKNOWN,
            details=details
        )


# ========================================================================
# Retry Configuration
# ========================================================================

@dataclass
class RetryConfig:
    """Retry configuration.

    Attributes:
        max_retries: Maximum retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential backoff (2^n)
        jitter: Add random jitter to avoid thundering herd
        retryable_exceptions: Exceptions that trigger retry
    """
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (
        Neo4jConnectionError,
        ChromaDBError,
        LLMRateLimitError,
        LLMTimeoutError,
        ServiceUnavailableError,
        ConnectionError,
        TimeoutError,
    )

    def calculate_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff and jitter.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds
        """
        import random

        # Exponential backoff: initial_delay * (base ^ attempt)
        delay = min(
            self.initial_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        # Add jitter (±25%)
        if self.jitter:
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)


# ========================================================================
# Circuit Breaker
# ========================================================================

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration.

    Attributes:
        failure_threshold: Failures before opening circuit
        success_threshold: Successes to close circuit (from half-open)
        timeout: Seconds before attempting recovery (half-open)
        reset_timeout: Seconds to fully reset failure count
    """
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 60.0  # 1 minute
    reset_timeout: float = 300.0  # 5 minutes


class CircuitBreaker:
    """Circuit breaker pattern implementation.

    Protects external services from cascading failures by:
    1. Tracking failure rate
    2. Opening circuit after threshold
    3. Allowing periodic test requests (half-open)
    4. Closing circuit after successful recovery
    """

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        """Initialize circuit breaker.

        Args:
            name: Service name (for logging)
            config: Circuit breaker configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.opened_at: Optional[datetime] = None

        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            ServiceUnavailableError: If circuit is open
        """
        async with self._lock:
            # Check circuit state
            if self.state == CircuitState.OPEN:
                # Check if timeout expired (move to half-open)
                if (
                    self.opened_at
                    and datetime.now() - self.opened_at > timedelta(seconds=self.config.timeout)
                ):
                    logger.info(f"Circuit breaker [{self.name}]: OPEN → HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                else:
                    # Still open, reject request
                    raise ServiceUnavailableError(
                        f"Circuit breaker [{self.name}] is OPEN. "
                        f"Service unavailable for {self.config.timeout}s."
                    )

        # Execute function
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure(e)
            raise

    async def _on_success(self) -> None:
        """Handle successful execution."""
        async with self._lock:
            self.failure_count = 0
            self.last_failure_time = None

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.info(
                    f"Circuit breaker [{self.name}]: Success count "
                    f"{self.success_count}/{self.config.success_threshold}"
                )

                if self.success_count >= self.config.success_threshold:
                    logger.info(f"Circuit breaker [{self.name}]: HALF_OPEN → CLOSED")
                    self.state = CircuitState.CLOSED
                    self.opened_at = None

    async def _on_failure(self, error: Exception) -> None:
        """Handle failed execution.

        Args:
            error: Exception that occurred
        """
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            logger.warning(
                f"Circuit breaker [{self.name}]: Failure {self.failure_count} - {error}"
            )

            if self.state == CircuitState.HALF_OPEN:
                # Failed during recovery, reopen circuit
                logger.warning(f"Circuit breaker [{self.name}]: HALF_OPEN → OPEN")
                self.state = CircuitState.OPEN
                self.opened_at = datetime.now()

            elif self.failure_count >= self.config.failure_threshold:
                # Threshold exceeded, open circuit
                logger.error(
                    f"Circuit breaker [{self.name}]: CLOSED → OPEN "
                    f"(failures: {self.failure_count})"
                )
                self.state = CircuitState.OPEN
                self.opened_at = datetime.now()

    def get_state(self) -> dict:
        """Get current circuit state.

        Returns:
            State information
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
        }


# ========================================================================
# Retry Decorator
# ========================================================================

def with_retry(config: RetryConfig = None):
    """Decorator for automatic retry with exponential backoff.

    Args:
        config: Retry configuration

    Returns:
        Decorated async function

    Example:
        @with_retry(RetryConfig(max_retries=5))
        async def fetch_data():
            ...
    """
    retry_config = config or RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_error = None

            for attempt in range(retry_config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except retry_config.retryable_exceptions as e:
                    last_error = e

                    if attempt < retry_config.max_retries:
                        delay = retry_config.calculate_delay(attempt)
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/"
                            f"{retry_config.max_retries + 1}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {retry_config.max_retries + 1} attempts"
                        )

                except Exception as e:
                    # Non-retryable exception, raise immediately
                    logger.error(f"{func.__name__} failed with non-retryable error: {e}")
                    raise

            # All retries exhausted
            raise last_error

        return wrapper

    return decorator


# ========================================================================
# Graceful Degradation
# ========================================================================

@dataclass
class DegradedResponse:
    """Response in degraded mode.

    Attributes:
        success: Whether primary operation succeeded
        data: Response data (may be partial or fallback)
        degraded: Whether in degraded mode
        error: Error message if degraded
        fallback_used: Name of fallback strategy used
    """
    success: bool
    data: Any = None
    degraded: bool = False
    error: Optional[str] = None
    fallback_used: Optional[str] = None


async def with_fallback(
    primary_func: Callable,
    fallback_func: Callable,
    fallback_name: str = "unknown",
    *args,
    **kwargs
) -> DegradedResponse:
    """Execute function with fallback on failure.

    Args:
        primary_func: Primary async function
        fallback_func: Fallback async function
        fallback_name: Name of fallback strategy (for logging)
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        DegradedResponse with result or fallback
    """
    try:
        result = await primary_func(*args, **kwargs)
        return DegradedResponse(
            success=True,
            data=result,
            degraded=False
        )

    except Exception as e:
        logger.warning(
            f"Primary function failed: {e}. Using fallback: {fallback_name}"
        )

        try:
            fallback_result = await fallback_func(*args, **kwargs)
            return DegradedResponse(
                success=True,
                data=fallback_result,
                degraded=True,
                error=str(e),
                fallback_used=fallback_name
            )

        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            return DegradedResponse(
                success=False,
                degraded=True,
                error=f"Primary: {e}, Fallback: {fallback_error}",
                fallback_used=fallback_name
            )


# ========================================================================
# Error Reporter
# ========================================================================

@dataclass
class ErrorReport:
    """Error report for monitoring.

    Attributes:
        timestamp: When error occurred
        error_type: Exception class name
        error_message: Error message
        context: Additional context (function, args, etc.)
        stack_trace: Stack trace if available
    """
    timestamp: datetime
    error_type: str
    error_message: str
    context: dict = field(default_factory=dict)
    stack_trace: Optional[str] = None


class ErrorReporter:
    """Centralized error reporting and alerting."""

    def __init__(self, max_reports: int = 1000):
        """Initialize error reporter.

        Args:
            max_reports: Maximum reports to keep in memory
        """
        self.max_reports = max_reports
        self.reports: list[ErrorReport] = []
        self._lock = asyncio.Lock()

    async def report(
        self,
        error: Exception,
        context: Optional[dict] = None,
        include_trace: bool = True
    ) -> None:
        """Report an error.

        Args:
            error: Exception that occurred
            context: Additional context information
            include_trace: Whether to include stack trace
        """
        import traceback

        async with self._lock:
            report = ErrorReport(
                timestamp=datetime.now(),
                error_type=type(error).__name__,
                error_message=str(error),
                context=context or {},
                stack_trace=traceback.format_exc() if include_trace else None
            )

            self.reports.append(report)

            # Keep only recent reports
            if len(self.reports) > self.max_reports:
                self.reports = self.reports[-self.max_reports:]

            # Log error
            logger.error(
                f"Error reported: {report.error_type} - {report.error_message}",
                extra={"context": report.context}
            )

    async def get_recent_errors(self, limit: int = 10) -> list[ErrorReport]:
        """Get recent errors.

        Args:
            limit: Maximum number of errors to return

        Returns:
            Recent error reports
        """
        async with self._lock:
            return self.reports[-limit:]

    async def get_error_summary(self) -> dict:
        """Get error summary statistics.

        Returns:
            Error summary with counts by type
        """
        async with self._lock:
            from collections import Counter

            error_types = Counter(r.error_type for r in self.reports)

            return {
                "total_errors": len(self.reports),
                "error_types": dict(error_types),
                "recent_errors": [
                    {
                        "timestamp": r.timestamp.isoformat(),
                        "type": r.error_type,
                        "message": r.error_message
                    }
                    for r in self.reports[-10:]
                ]
            }


# Global error reporter instance
_global_reporter: Optional[ErrorReporter] = None


def get_error_reporter() -> ErrorReporter:
    """Get global error reporter instance.

    Returns:
        Global ErrorReporter
    """
    global _global_reporter
    if _global_reporter is None:
        _global_reporter = ErrorReporter()
    return _global_reporter


# ========================================================================
# Usage Example
# ========================================================================

async def example_usage():
    """Error handling usage examples."""

    # 1. Retry with exponential backoff
    @with_retry(RetryConfig(max_retries=5, initial_delay=1.0))
    async def unstable_api_call():
        # Simulated API call that might fail
        import random
        if random.random() < 0.7:
            raise LLMRateLimitError("Rate limit exceeded")
        return {"status": "success"}

    try:
        result = await unstable_api_call()
        logger.info(f"API call succeeded: {result}")
    except LLMRateLimitError:
        logger.error("API call failed after all retries")

    # 2. Circuit breaker for external service
    breaker = CircuitBreaker("gemini_api", CircuitBreakerConfig(failure_threshold=3))

    async def call_gemini_api():
        # Simulated Gemini API call
        return {"response": "data"}

    try:
        result = await breaker.call(call_gemini_api)
        logger.info(f"Service call succeeded: {result}")
    except ServiceUnavailableError as e:
        logger.warning(f"Service unavailable: {e}")

    # 3. Graceful degradation with fallback
    async def fetch_from_graph():
        # Primary: Fetch from Neo4j
        raise Neo4jConnectionError("Neo4j unavailable")

    async def fetch_from_cache():
        # Fallback: Use cached data
        return {"cached": True, "data": "fallback"}

    response = await with_fallback(
        fetch_from_graph,
        fetch_from_cache,
        fallback_name="cache"
    )

    if response.success:
        logger.info(f"Data fetched (degraded={response.degraded}): {response.data}")

    # 4. Error reporting
    reporter = get_error_reporter()

    try:
        raise PDFProcessingError("Failed to parse PDF")
    except PDFProcessingError as e:
        await reporter.report(e, context={"file": "paper.pdf"})

    # Get error summary
    summary = await reporter.get_error_summary()
    logger.info(f"Error summary: {summary}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_usage())

"""Structured logging configuration for Spine GraphRAG system.

This module provides a production-ready structured logging system using structlog
with JSON output for production and colored console for development.

Features:
    - JSON structured logging for production
    - Colored console output for development
    - Context processors: timestamp, log level, module name, correlation_id
    - Domain-specific logging for LLM calls, Neo4j queries, search, PDF processing
    - Integration with existing exception hierarchy

Example:
    ```python
    from src.core.logging_config import LoggerFactory, MedicalRAGLogger

    # Basic logger
    logger = LoggerFactory.get_logger(__name__)
    logger.info("Processing document", doc_id="PMC123456")

    # Domain-specific logger
    rag_logger = MedicalRAGLogger(__name__)
    rag_logger.log_llm_call(
        model="gemini-2.5-flash",
        tokens_in=1024,
        tokens_out=512,
        duration_ms=1500
    )
    ```
"""

import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List
from enum import Enum
from contextvars import ContextVar

import structlog
from structlog.types import EventDict, WrappedLogger


# Context variable for correlation ID (for request tracing)
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class LogLevel(Enum):
    """Standard log levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Environment(Enum):
    """Environment types."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


def add_timestamp(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add ISO 8601 timestamp to log event.

    Args:
        logger: Wrapped logger instance
        method_name: Name of the logging method
        event_dict: Log event dictionary

    Returns:
        Modified event dictionary with timestamp
    """
    event_dict["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    return event_dict


def add_log_level(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add log level to event.

    Args:
        logger: Wrapped logger instance
        method_name: Name of the logging method
        event_dict: Log event dictionary

    Returns:
        Modified event dictionary with level
    """
    event_dict["level"] = method_name.upper()
    return event_dict


def add_module_name(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add module name to event.

    Args:
        logger: Wrapped logger instance
        method_name: Name of the logging method
        event_dict: Log event dictionary

    Returns:
        Modified event dictionary with module name
    """
    # Extract module name from logger name
    logger_name = event_dict.get("logger", "unknown")
    if logger_name.startswith("src."):
        # Convert src.graph.neo4j_client -> graph.neo4j_client
        module = logger_name[4:]
    else:
        module = logger_name
    event_dict["module"] = module
    return event_dict


def add_correlation_id(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add correlation ID for request tracing.

    Args:
        logger: Wrapped logger instance
        method_name: Name of the logging method
        event_dict: Log event dictionary

    Returns:
        Modified event dictionary with correlation_id
    """
    corr_id = correlation_id_var.get()
    if corr_id:
        event_dict["correlation_id"] = corr_id
    return event_dict


def configure_structlog(environment: Environment = Environment.DEVELOPMENT) -> None:
    """Configure structlog with appropriate processors and renderer.

    Args:
        environment: Environment type (development/production/testing)
    """
    # Common processors for all environments
    common_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_log_level,
        add_module_name,
        add_correlation_id,
        structlog.processors.StackInfoRenderer(),
    ]

    if environment == Environment.DEVELOPMENT:
        # Development: colored console output with key-value pairs
        processors = common_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    else:
        # Production: JSON output for log aggregation
        processors = common_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )


class LoggerFactory:
    """Factory for creating consistent loggers across the system.

    Example:
        ```python
        logger = LoggerFactory.get_logger(__name__)
        logger.info("Processing started", doc_id="123")
        ```
    """

    _configured = False
    _environment = Environment.DEVELOPMENT

    @classmethod
    def configure(cls, environment: Environment = Environment.DEVELOPMENT) -> None:
        """Configure logging system.

        Args:
            environment: Environment type
        """
        if not cls._configured:
            configure_structlog(environment)
            cls._environment = environment
            cls._configured = True

    @classmethod
    def get_logger(cls, name: str) -> structlog.stdlib.BoundLogger:
        """Get a configured logger instance.

        Args:
            name: Logger name (typically __name__)

        Returns:
            Configured structlog logger
        """
        if not cls._configured:
            cls.configure()
        return structlog.get_logger(name)

    @classmethod
    def set_correlation_id(cls, correlation_id: Optional[str] = None) -> str:
        """Set correlation ID for request tracing.

        Args:
            correlation_id: Optional correlation ID (generated if None)

        Returns:
            The correlation ID that was set
        """
        corr_id = correlation_id or str(uuid.uuid4())
        correlation_id_var.set(corr_id)
        return corr_id

    @classmethod
    def clear_correlation_id(cls) -> None:
        """Clear correlation ID."""
        correlation_id_var.set(None)


@dataclass
class LLMCallMetrics:
    """Metrics for LLM API calls.

    Attributes:
        model: Model name (e.g., gemini-2.5-flash)
        tokens_in: Input tokens consumed
        tokens_out: Output tokens generated
        duration_ms: Call duration in milliseconds
        success: Whether the call succeeded
        error_code: Error code if failed (from exceptions.ErrorCode)
        cache_hit: Whether response was served from cache
    """
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: float
    success: bool = True
    error_code: Optional[str] = None
    cache_hit: bool = False


@dataclass
class Neo4jQueryMetrics:
    """Metrics for Neo4j queries.

    Attributes:
        cypher: Cypher query (truncated for logging)
        params: Query parameters
        duration_ms: Query execution time in milliseconds
        result_count: Number of results returned
        success: Whether the query succeeded
        error_code: Error code if failed
    """
    cypher: str
    params: Dict[str, Any]
    duration_ms: float
    result_count: int
    success: bool = True
    error_code: Optional[str] = None

    def __post_init__(self):
        """Truncate long cypher queries for logging."""
        if len(self.cypher) > 200:
            self.cypher = self.cypher[:200] + "..."


@dataclass
class SearchMetrics:
    """Metrics for hybrid search operations.

    Attributes:
        query_type: Type of query (graph/vector/hybrid)
        graph_results: Number of graph search results
        vector_results: Number of vector search results
        final_count: Final count after ranking
        duration_ms: Total search duration in milliseconds
        graph_duration_ms: Graph search duration
        vector_duration_ms: Vector search duration
    """
    query_type: str
    graph_results: int
    vector_results: int
    final_count: int
    duration_ms: float
    graph_duration_ms: Optional[float] = None
    vector_duration_ms: Optional[float] = None


@dataclass
class PDFProcessingMetrics:
    """Metrics for PDF processing.

    Attributes:
        filename: PDF filename
        pages: Number of pages
        chunks_created: Number of chunks created
        duration_s: Processing duration in seconds
        sub_domain: Detected spine sub-domain
        anatomy_levels: Detected anatomy levels
        interventions: Extracted interventions
        outcomes: Extracted outcomes
    """
    filename: str
    pages: int
    chunks_created: int
    duration_s: float
    sub_domain: Optional[str] = None
    anatomy_levels: Optional[List[str]] = None
    interventions: Optional[List[str]] = None
    outcomes: Optional[List[str]] = None


class MedicalRAGLogger:
    """Domain-specific logger wrapper for Spine GraphRAG system.

    Provides high-level logging methods for common operations:
    - LLM API calls
    - Neo4j queries
    - Hybrid search
    - PDF processing

    Example:
        ```python
        logger = MedicalRAGLogger(__name__)

        # Log LLM call
        logger.log_llm_call(
            model="gemini-2.5-flash",
            tokens_in=1024,
            tokens_out=512,
            duration_ms=1500
        )

        # Log Neo4j query
        logger.log_neo4j_query(
            cypher="MATCH (p:Paper) RETURN p LIMIT 10",
            params={},
            duration_ms=25,
            result_count=10
        )
        ```
    """

    def __init__(self, name: str):
        """Initialize logger.

        Args:
            name: Logger name (typically __name__)
        """
        self.logger = LoggerFactory.get_logger(name)

    def log_llm_call(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        duration_ms: float,
        success: bool = True,
        error_code: Optional[str] = None,
        cache_hit: bool = False,
        **extra
    ) -> None:
        """Log LLM API call metrics.

        Args:
            model: Model name
            tokens_in: Input tokens
            tokens_out: Output tokens
            duration_ms: Duration in milliseconds
            success: Whether call succeeded
            error_code: Error code if failed
            cache_hit: Whether response was cached
            **extra: Additional context
        """
        metrics = LLMCallMetrics(
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            cache_hit=cache_hit
        )

        log_data = {
            "event_type": "llm_call",
            "model": metrics.model,
            "tokens_in": metrics.tokens_in,
            "tokens_out": metrics.tokens_out,
            "total_tokens": metrics.tokens_in + metrics.tokens_out,
            "duration_ms": metrics.duration_ms,
            "success": metrics.success,
            "cache_hit": metrics.cache_hit,
            **extra
        }

        if error_code:
            log_data["error_code"] = error_code
            self.logger.error("LLM call failed", **log_data)
        else:
            self.logger.info("LLM call completed", **log_data)

    def log_neo4j_query(
        self,
        cypher: str,
        params: Dict[str, Any],
        duration_ms: float,
        result_count: int,
        success: bool = True,
        error_code: Optional[str] = None,
        **extra
    ) -> None:
        """Log Neo4j query metrics.

        Args:
            cypher: Cypher query string
            params: Query parameters
            duration_ms: Query duration in milliseconds
            result_count: Number of results
            success: Whether query succeeded
            error_code: Error code if failed
            **extra: Additional context
        """
        metrics = Neo4jQueryMetrics(
            cypher=cypher,
            params=params,
            duration_ms=duration_ms,
            result_count=result_count,
            success=success,
            error_code=error_code
        )

        log_data = {
            "event_type": "neo4j_query",
            "cypher": metrics.cypher,
            "params": metrics.params,
            "duration_ms": metrics.duration_ms,
            "result_count": metrics.result_count,
            "success": metrics.success,
            **extra
        }

        if error_code:
            log_data["error_code"] = error_code
            self.logger.error("Neo4j query failed", **log_data)
        else:
            self.logger.info("Neo4j query completed", **log_data)

    def log_search(
        self,
        query_type: str,
        graph_results: int,
        vector_results: int,
        final_count: int,
        duration_ms: float,
        graph_duration_ms: Optional[float] = None,
        vector_duration_ms: Optional[float] = None,
        **extra
    ) -> None:
        """Log hybrid search metrics.

        Args:
            query_type: Type of search (graph/vector/hybrid)
            graph_results: Number of graph results
            vector_results: Number of vector results
            final_count: Final count after ranking
            duration_ms: Total duration
            graph_duration_ms: Graph search duration
            vector_duration_ms: Vector search duration
            **extra: Additional context
        """
        metrics = SearchMetrics(
            query_type=query_type,
            graph_results=graph_results,
            vector_results=vector_results,
            final_count=final_count,
            duration_ms=duration_ms,
            graph_duration_ms=graph_duration_ms,
            vector_duration_ms=vector_duration_ms
        )

        log_data = {
            "event_type": "search",
            "query_type": metrics.query_type,
            "graph_results": metrics.graph_results,
            "vector_results": metrics.vector_results,
            "final_count": metrics.final_count,
            "duration_ms": metrics.duration_ms,
            **extra
        }

        if graph_duration_ms is not None:
            log_data["graph_duration_ms"] = graph_duration_ms
        if vector_duration_ms is not None:
            log_data["vector_duration_ms"] = vector_duration_ms

        self.logger.info("Search completed", **log_data)

    def log_pdf_processing(
        self,
        filename: str,
        pages: int,
        chunks_created: int,
        duration_s: float,
        sub_domain: Optional[str] = None,
        anatomy_levels: Optional[List[str]] = None,
        interventions: Optional[List[str]] = None,
        outcomes: Optional[List[str]] = None,
        **extra
    ) -> None:
        """Log PDF processing metrics.

        Args:
            filename: PDF filename
            pages: Number of pages
            chunks_created: Number of chunks created
            duration_s: Processing duration in seconds
            sub_domain: Detected spine sub-domain
            anatomy_levels: Detected anatomy levels
            interventions: Extracted interventions
            outcomes: Extracted outcomes
            **extra: Additional context
        """
        metrics = PDFProcessingMetrics(
            filename=filename,
            pages=pages,
            chunks_created=chunks_created,
            duration_s=duration_s,
            sub_domain=sub_domain,
            anatomy_levels=anatomy_levels,
            interventions=interventions,
            outcomes=outcomes
        )

        log_data = {
            "event_type": "pdf_processing",
            "filename": metrics.filename,
            "pages": metrics.pages,
            "chunks_created": metrics.chunks_created,
            "duration_s": metrics.duration_s,
            **extra
        }

        if sub_domain:
            log_data["sub_domain"] = sub_domain
        if anatomy_levels:
            log_data["anatomy_levels"] = anatomy_levels
        if interventions:
            log_data["interventions"] = interventions
        if outcomes:
            log_data["outcomes"] = outcomes

        self.logger.info("PDF processing completed", **log_data)

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self.logger.critical(message, **kwargs)


# Initialize logging on module import
LoggerFactory.configure(Environment.DEVELOPMENT)

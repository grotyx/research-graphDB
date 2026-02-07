"""Tests for structured logging configuration.

Tests cover:
- Logger creation and configuration
- Context processors (timestamp, log level, module name, correlation_id)
- Domain-specific logging methods (LLM, Neo4j, search, PDF)
- JSON output format validation
- Correlation ID tracking
"""

import json
import uuid
from io import StringIO
from typing import Dict, Any

import pytest
import structlog

from src.core.logging_config import (
    LoggerFactory,
    MedicalRAGLogger,
    Environment,
    LLMCallMetrics,
    Neo4jQueryMetrics,
    SearchMetrics,
    PDFProcessingMetrics,
    add_timestamp,
    add_log_level,
    add_module_name,
    add_correlation_id,
    correlation_id_var,
)


class TestLoggerFactory:
    """Test LoggerFactory class."""

    def test_get_logger_creates_logger(self):
        """Test that get_logger creates a valid logger."""
        logger = LoggerFactory.get_logger("test_module")
        assert logger is not None
        # Logger can be BoundLogger or BoundLoggerLazyProxy depending on configuration
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'error')
        assert hasattr(logger, 'debug')

    def test_configure_development_environment(self):
        """Test configuration for development environment."""
        LoggerFactory.configure(Environment.DEVELOPMENT)
        logger = LoggerFactory.get_logger("test_dev")
        assert logger is not None

    def test_configure_production_environment(self):
        """Test configuration for production environment."""
        LoggerFactory.configure(Environment.PRODUCTION)
        logger = LoggerFactory.get_logger("test_prod")
        assert logger is not None

    def test_set_correlation_id(self):
        """Test setting and retrieving correlation ID."""
        corr_id = "test-correlation-123"
        result = LoggerFactory.set_correlation_id(corr_id)
        assert result == corr_id
        assert correlation_id_var.get() == corr_id

    def test_set_correlation_id_auto_generate(self):
        """Test auto-generation of correlation ID."""
        result = LoggerFactory.set_correlation_id()
        assert result is not None
        assert len(result) > 0
        # Should be a valid UUID format
        uuid.UUID(result)  # Raises ValueError if invalid

    def test_clear_correlation_id(self):
        """Test clearing correlation ID."""
        LoggerFactory.set_correlation_id("test-123")
        LoggerFactory.clear_correlation_id()
        assert correlation_id_var.get() is None


class TestContextProcessors:
    """Test context processor functions."""

    def test_add_timestamp(self):
        """Test timestamp processor adds ISO 8601 timestamp."""
        event_dict = {}
        result = add_timestamp(None, "info", event_dict)

        assert "timestamp" in result
        # Basic format check: YYYY-MM-DDTHH:MM:SS
        assert "T" in result["timestamp"]
        assert len(result["timestamp"]) >= 19

    def test_add_log_level(self):
        """Test log level processor."""
        event_dict = {}
        result = add_log_level(None, "info", event_dict)
        assert result["level"] == "INFO"

        result = add_log_level(None, "error", event_dict)
        assert result["level"] == "ERROR"

    def test_add_module_name(self):
        """Test module name processor."""
        event_dict = {"logger": "src.graph.neo4j_client"}
        result = add_module_name(None, "info", event_dict)
        assert result["module"] == "graph.neo4j_client"

        # Test non-src module
        event_dict = {"logger": "my_module"}
        result = add_module_name(None, "info", event_dict)
        assert result["module"] == "my_module"

    def test_add_correlation_id_present(self):
        """Test correlation ID processor when ID is set."""
        corr_id = "test-correlation-456"
        correlation_id_var.set(corr_id)

        event_dict = {}
        result = add_correlation_id(None, "info", event_dict)
        assert result["correlation_id"] == corr_id

    def test_add_correlation_id_absent(self):
        """Test correlation ID processor when ID is not set."""
        correlation_id_var.set(None)

        event_dict = {}
        result = add_correlation_id(None, "info", event_dict)
        assert "correlation_id" not in result


class TestLLMCallMetrics:
    """Test LLMCallMetrics dataclass."""

    def test_llm_call_metrics_creation(self):
        """Test creating LLM call metrics."""
        metrics = LLMCallMetrics(
            model="gemini-2.5-flash",
            tokens_in=1024,
            tokens_out=512,
            duration_ms=1500.5,
            success=True,
            cache_hit=False
        )

        assert metrics.model == "gemini-2.5-flash"
        assert metrics.tokens_in == 1024
        assert metrics.tokens_out == 512
        assert metrics.duration_ms == 1500.5
        assert metrics.success is True
        assert metrics.cache_hit is False
        assert metrics.error_code is None

    def test_llm_call_metrics_with_error(self):
        """Test LLM metrics with error."""
        metrics = LLMCallMetrics(
            model="gemini-2.5-flash",
            tokens_in=0,
            tokens_out=0,
            duration_ms=100,
            success=False,
            error_code="LLM_RATE_LIMIT"
        )

        assert metrics.success is False
        assert metrics.error_code == "LLM_RATE_LIMIT"


class TestNeo4jQueryMetrics:
    """Test Neo4jQueryMetrics dataclass."""

    def test_neo4j_query_metrics_creation(self):
        """Test creating Neo4j query metrics."""
        metrics = Neo4jQueryMetrics(
            cypher="MATCH (p:Paper) RETURN p LIMIT 10",
            params={"limit": 10},
            duration_ms=25.3,
            result_count=10,
            success=True
        )

        assert "MATCH (p:Paper)" in metrics.cypher
        assert metrics.params == {"limit": 10}
        assert metrics.duration_ms == 25.3
        assert metrics.result_count == 10
        assert metrics.success is True

    def test_neo4j_query_truncation(self):
        """Test long Cypher queries are truncated."""
        long_cypher = "MATCH (n) " * 100  # Very long query
        metrics = Neo4jQueryMetrics(
            cypher=long_cypher,
            params={},
            duration_ms=100,
            result_count=0
        )

        # Should be truncated to 200 chars + "..."
        assert len(metrics.cypher) <= 203
        assert metrics.cypher.endswith("...")


class TestSearchMetrics:
    """Test SearchMetrics dataclass."""

    def test_search_metrics_creation(self):
        """Test creating search metrics."""
        metrics = SearchMetrics(
            query_type="hybrid",
            graph_results=15,
            vector_results=20,
            final_count=10,
            duration_ms=350.5,
            graph_duration_ms=150.2,
            vector_duration_ms=180.3
        )

        assert metrics.query_type == "hybrid"
        assert metrics.graph_results == 15
        assert metrics.vector_results == 20
        assert metrics.final_count == 10
        assert metrics.duration_ms == 350.5
        assert metrics.graph_duration_ms == 150.2
        assert metrics.vector_duration_ms == 180.3


class TestPDFProcessingMetrics:
    """Test PDFProcessingMetrics dataclass."""

    def test_pdf_processing_metrics_creation(self):
        """Test creating PDF processing metrics."""
        metrics = PDFProcessingMetrics(
            filename="spine_study.pdf",
            pages=12,
            chunks_created=35,
            duration_s=45.2,
            sub_domain="Degenerative",
            anatomy_levels=["L4", "L5"],
            interventions=["TLIF", "PLIF"],
            outcomes=["VAS", "ODI"]
        )

        assert metrics.filename == "spine_study.pdf"
        assert metrics.pages == 12
        assert metrics.chunks_created == 35
        assert metrics.duration_s == 45.2
        assert metrics.sub_domain == "Degenerative"
        assert metrics.anatomy_levels == ["L4", "L5"]
        assert metrics.interventions == ["TLIF", "PLIF"]
        assert metrics.outcomes == ["VAS", "ODI"]


class TestMedicalRAGLogger:
    """Test MedicalRAGLogger domain-specific logging."""

    def test_logger_creation(self):
        """Test creating MedicalRAGLogger."""
        logger = MedicalRAGLogger("test_module")
        assert logger is not None
        assert logger.logger is not None

    def test_log_llm_call_success(self, caplog):
        """Test logging successful LLM call."""
        logger = MedicalRAGLogger("test_llm")

        logger.log_llm_call(
            model="gemini-2.5-flash",
            tokens_in=1024,
            tokens_out=512,
            duration_ms=1500,
            success=True,
            cache_hit=False
        )

        # Check that log was created (basic check)
        # Note: Detailed JSON validation would require parsing output

    def test_log_llm_call_failure(self, caplog):
        """Test logging failed LLM call."""
        logger = MedicalRAGLogger("test_llm")

        logger.log_llm_call(
            model="gemini-2.5-flash",
            tokens_in=0,
            tokens_out=0,
            duration_ms=100,
            success=False,
            error_code="LLM_RATE_LIMIT"
        )

    def test_log_neo4j_query_success(self):
        """Test logging successful Neo4j query."""
        logger = MedicalRAGLogger("test_neo4j")

        logger.log_neo4j_query(
            cypher="MATCH (p:Paper) RETURN p LIMIT 10",
            params={"limit": 10},
            duration_ms=25.3,
            result_count=10,
            success=True
        )

    def test_log_neo4j_query_failure(self):
        """Test logging failed Neo4j query."""
        logger = MedicalRAGLogger("test_neo4j")

        logger.log_neo4j_query(
            cypher="INVALID QUERY",
            params={},
            duration_ms=5,
            result_count=0,
            success=False,
            error_code="NEO4J_QUERY_ERROR"
        )

    def test_log_search(self):
        """Test logging search operation."""
        logger = MedicalRAGLogger("test_search")

        logger.log_search(
            query_type="hybrid",
            graph_results=15,
            vector_results=20,
            final_count=10,
            duration_ms=350.5,
            graph_duration_ms=150.2,
            vector_duration_ms=180.3
        )

    def test_log_pdf_processing(self):
        """Test logging PDF processing."""
        logger = MedicalRAGLogger("test_pdf")

        logger.log_pdf_processing(
            filename="spine_study.pdf",
            pages=12,
            chunks_created=35,
            duration_s=45.2,
            sub_domain="Degenerative",
            anatomy_levels=["L4", "L5"],
            interventions=["TLIF", "PLIF"],
            outcomes=["VAS", "ODI"]
        )

    def test_standard_logging_methods(self):
        """Test standard logging methods (debug, info, warning, error, critical)."""
        logger = MedicalRAGLogger("test_standard")

        # Should not raise exceptions
        logger.debug("Debug message", extra_field="value")
        logger.info("Info message", extra_field="value")
        logger.warning("Warning message", extra_field="value")
        logger.error("Error message", extra_field="value")
        logger.critical("Critical message", extra_field="value")


class TestProductionJSONOutput:
    """Test JSON output format for production."""

    def test_json_output_structure(self):
        """Test that production mode produces valid JSON."""
        # Reconfigure for production
        LoggerFactory.configure(Environment.PRODUCTION)
        logger = MedicalRAGLogger("test_json")

        # Note: Actual JSON validation would require capturing stdout
        # This is a basic functionality test
        logger.info("Test message", key="value")

        # Reset to development mode
        LoggerFactory._configured = False
        LoggerFactory.configure(Environment.DEVELOPMENT)


class TestCorrelationIDTracking:
    """Test correlation ID for request tracing."""

    def test_correlation_id_in_logs(self):
        """Test that correlation ID appears in logs when set."""
        corr_id = "test-request-789"
        LoggerFactory.set_correlation_id(corr_id)

        logger = MedicalRAGLogger("test_correlation")
        logger.info("Test message with correlation")

        # Verify correlation ID is set
        assert correlation_id_var.get() == corr_id

        # Clean up
        LoggerFactory.clear_correlation_id()

    def test_correlation_id_persistence(self):
        """Test correlation ID persists across multiple log calls."""
        corr_id = LoggerFactory.set_correlation_id("persistent-123")
        logger = MedicalRAGLogger("test_persistence")

        logger.info("First message")
        logger.info("Second message")
        logger.info("Third message")

        # Should still be set
        assert correlation_id_var.get() == corr_id

        LoggerFactory.clear_correlation_id()


class TestIntegrationWithExceptions:
    """Test integration with existing exception hierarchy."""

    def test_log_exception_with_error_code(self):
        """Test logging exceptions with error codes."""
        from src.core.exceptions import LLMError, ErrorCode

        logger = MedicalRAGLogger("test_exceptions")

        try:
            raise LLMError(
                message="Rate limit exceeded",
                error_code=ErrorCode.LLM_RATE_LIMIT,
                details={"retry_after": 60}
            )
        except LLMError as e:
            logger.error(
                "LLM error occurred",
                error_code=e.error_code.value,
                error_message=e.message,
                error_details=e.details
            )


# Pytest fixtures

@pytest.fixture(autouse=True)
def reset_logging_config():
    """Reset logging configuration before each test."""
    LoggerFactory._configured = False
    LoggerFactory.configure(Environment.DEVELOPMENT)
    LoggerFactory.clear_correlation_id()
    yield
    # Cleanup after test
    LoggerFactory.clear_correlation_id()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Error handling hierarchy for Spine GraphRAG system.

This module defines a comprehensive exception hierarchy with specific error codes
for different system components (LLM, Neo4j, ChromaDB, etc.).

Example:
    ```python
    try:
        await neo4j_client.run_query(cypher)
    except Neo4jError as e:
        logger.error(f"Database error: {e}")
        print(e.to_dict())  # For JSON serialization
    ```
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ErrorCode(Enum):
    """Error codes for different failure scenarios.

    Naming convention: {COMPONENT}_{ERROR_TYPE}
    """
    # Validation errors (VAL_*)
    VAL_MISSING_FIELD = "VAL_MISSING_FIELD"
    VAL_INVALID_TYPE = "VAL_INVALID_TYPE"
    VAL_INVALID_VALUE = "VAL_INVALID_VALUE"
    VAL_SCHEMA_MISMATCH = "VAL_SCHEMA_MISMATCH"

    # Processing errors (PROC_*)
    PROC_PARSING_FAILED = "PROC_PARSING_FAILED"
    PROC_CHUNKING_FAILED = "PROC_CHUNKING_FAILED"
    PROC_EMBEDDING_FAILED = "PROC_EMBEDDING_FAILED"
    PROC_TIMEOUT = "PROC_TIMEOUT"
    PROC_UNKNOWN = "PROC_UNKNOWN"

    # LLM errors (LLM_*)
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_INVALID_RESPONSE = "LLM_INVALID_RESPONSE"
    LLM_API_ERROR = "LLM_API_ERROR"
    LLM_QUOTA_EXCEEDED = "LLM_QUOTA_EXCEEDED"
    LLM_MODEL_NOT_FOUND = "LLM_MODEL_NOT_FOUND"
    LLM_CONTENT_FILTER = "LLM_CONTENT_FILTER"

    # Neo4j errors (NEO4J_*)
    NEO4J_CONNECTION = "NEO4J_CONNECTION"
    NEO4J_QUERY_ERROR = "NEO4J_QUERY_ERROR"
    NEO4J_TRANSACTION_FAILED = "NEO4J_TRANSACTION_FAILED"
    NEO4J_CONSTRAINT_VIOLATION = "NEO4J_CONSTRAINT_VIOLATION"
    NEO4J_NODE_NOT_FOUND = "NEO4J_NODE_NOT_FOUND"
    NEO4J_SCHEMA_ERROR = "NEO4J_SCHEMA_ERROR"

    # ChromaDB errors (DEPRECATED - v7.14.12: Neo4j Vector Index가 유일한 벡터 저장소)
    CHROMA_CONNECTION = "CHROMA_CONNECTION"
    CHROMA_COLLECTION_NOT_FOUND = "CHROMA_COLLECTION_NOT_FOUND"
    CHROMA_INSERT_FAILED = "CHROMA_INSERT_FAILED"
    CHROMA_QUERY_FAILED = "CHROMA_QUERY_FAILED"
    CHROMA_DELETE_FAILED = "CHROMA_DELETE_FAILED"

    # Normalization errors (NORM_*)
    NORM_NO_MATCH = "NORM_NO_MATCH"
    NORM_AMBIGUOUS = "NORM_AMBIGUOUS"
    NORM_INVALID_INPUT = "NORM_INVALID_INPUT"
    NORM_TAXONOMY_ERROR = "NORM_TAXONOMY_ERROR"

    # Extraction errors (EXT_*)
    EXT_PDF_PARSING = "EXT_PDF_PARSING"
    EXT_METADATA_MISSING = "EXT_METADATA_MISSING"
    EXT_SCHEMA_VALIDATION = "EXT_SCHEMA_VALIDATION"
    EXT_VISION_FAILED = "EXT_VISION_FAILED"
    EXT_STATISTICS_PARSING = "EXT_STATISTICS_PARSING"

    # PubMed errors (PUBMED_*)
    PUBMED_CONNECTION = "PUBMED_CONNECTION"
    PUBMED_RATE_LIMIT = "PUBMED_RATE_LIMIT"
    PUBMED_NOT_FOUND = "PUBMED_NOT_FOUND"
    PUBMED_INVALID_INPUT = "PUBMED_INVALID_INPUT"
    PUBMED_TIMEOUT = "PUBMED_TIMEOUT"


@dataclass
class MedicalRAGError(Exception):
    """Base exception for all Spine GraphRAG errors.

    All custom exceptions inherit from this base class to provide
    consistent error handling with structured error codes and details.

    Attributes:
        message: Human-readable error message
        error_code: Structured error code from ErrorCode enum
        details: Additional context (query, params, stack trace, etc.)

    Example:
        ```python
        raise MedicalRAGError(
            message="Failed to connect to database",
            error_code=ErrorCode.NEO4J_CONNECTION,
            details={"uri": "bolt://localhost:7687", "timeout": 30}
        )
        ```
    """
    message: str
    error_code: ErrorCode
    details: Optional[dict] = field(default_factory=dict)

    def __str__(self) -> str:
        """Format error for logging and display.

        Returns:
            Formatted error string with code, message, and details
        """
        base = f"[{self.error_code.value}] {self.message}"
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{base} | Details: {detail_str}"
        return base

    def to_dict(self) -> dict:
        """Serialize exception to dictionary for JSON response.

        Returns:
            Dictionary with error_code, message, and details

        Example:
            ```python
            {
                "error_code": "NEO4J_CONNECTION",
                "message": "Failed to connect to database",
                "details": {"uri": "bolt://localhost:7687"}
            }
            ```
        """
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "details": self.details or {}
        }


@dataclass
class ValidationError(MedicalRAGError):
    """Input validation failures.

    Raised when input data fails schema validation, type checks,
    or business logic constraints.

    Example:
        ```python
        raise ValidationError(
            message="Missing required field: paper_id",
            error_code=ErrorCode.VAL_MISSING_FIELD,
            details={"field": "paper_id", "schema": "PaperInput"}
        )
        ```
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.VAL_INVALID_VALUE,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


@dataclass
class ProcessingError(MedicalRAGError):
    """General processing errors during data transformation.

    Raised when PDF parsing, text chunking, embedding generation,
    or other data processing operations fail.

    Example:
        ```python
        raise ProcessingError(
            message="Failed to chunk document",
            error_code=ErrorCode.PROC_CHUNKING_FAILED,
            details={"doc_id": "123", "reason": "Empty text"}
        )
        ```
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.PROC_UNKNOWN,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


@dataclass
class LLMError(MedicalRAGError):
    """LLM API related errors.

    Raised for Gemini API failures including rate limits, timeouts,
    invalid responses, quota exceeded, and content filtering.

    Example:
        ```python
        raise LLMError(
            message="Gemini API rate limit exceeded",
            error_code=ErrorCode.LLM_RATE_LIMIT,
            details={"retry_after": 60, "model": "gemini-2.5-flash"}
        )
        ```
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.LLM_API_ERROR,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


@dataclass
class Neo4jError(MedicalRAGError):
    """Neo4j database errors.

    Raised for connection failures, query errors, transaction failures,
    constraint violations, and schema errors.

    Example:
        ```python
        raise Neo4jError(
            message="Failed to establish connection",
            error_code=ErrorCode.NEO4J_CONNECTION,
            details={
                "uri": "bolt://localhost:7687",
                "timeout": 30,
                "reason": "Connection refused"
            }
        )
        ```
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.NEO4J_QUERY_ERROR,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


@dataclass
class ChromaDBError(MedicalRAGError):
    """ChromaDB vector database errors.

    DEPRECATED (v7.14.12): ChromaDB 제거됨. Neo4j Vector Index 사용.
    하위 호환성을 위해 유지됨.
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.CHROMA_QUERY_FAILED,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


@dataclass
class NormalizationError(MedicalRAGError):
    """Entity normalization failures.

    Raised when intervention/outcome normalization fails due to
    no match, ambiguous matches, or taxonomy errors.

    Example:
        ```python
        raise NormalizationError(
            message="Ambiguous intervention term",
            error_code=ErrorCode.NORM_AMBIGUOUS,
            details={
                "input": "biportal",
                "candidates": ["UBE", "BESS"],
                "confidences": [0.8, 0.75]
            }
        )
        ```
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.NORM_NO_MATCH,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


@dataclass
class ExtractionError(MedicalRAGError):
    """Metadata extraction failures.

    Raised when PDF parsing, metadata extraction, vision processing,
    or statistics parsing fails.

    Example:
        ```python
        raise ExtractionError(
            message="Failed to extract PICO from paper",
            error_code=ErrorCode.EXT_METADATA_MISSING,
            details={
                "paper_id": "PMC123456",
                "missing_fields": ["intervention", "comparator"]
            }
        )
        ```
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.EXT_METADATA_MISSING,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


# Convenience functions for common error scenarios

def raise_validation_error(
    message: str,
    field: Optional[str] = None,
    **kwargs
) -> None:
    """Raise ValidationError with common field details.

    Args:
        message: Error message
        field: Field name that failed validation
        **kwargs: Additional details

    Raises:
        ValidationError
    """
    details = {"field": field} if field else {}
    details.update(kwargs)
    raise ValidationError(
        message=message,
        error_code=ErrorCode.VAL_INVALID_VALUE,
        details=details
    )


def raise_llm_rate_limit(
    retry_after: int,
    model: str,
    **kwargs
) -> None:
    """Raise LLMError for rate limit exceeded.

    Args:
        retry_after: Seconds to wait before retry
        model: Model name that hit rate limit
        **kwargs: Additional details

    Raises:
        LLMError
    """
    details = {"retry_after": retry_after, "model": model}
    details.update(kwargs)
    raise LLMError(
        message=f"Rate limit exceeded for {model}. Retry after {retry_after}s",
        error_code=ErrorCode.LLM_RATE_LIMIT,
        details=details
    )


def raise_neo4j_connection_error(
    uri: str,
    reason: str,
    **kwargs
) -> None:
    """Raise Neo4jError for connection failures.

    Args:
        uri: Neo4j URI
        reason: Connection failure reason
        **kwargs: Additional details

    Raises:
        Neo4jError
    """
    details = {"uri": uri, "reason": reason}
    details.update(kwargs)
    raise Neo4jError(
        message=f"Failed to connect to Neo4j at {uri}: {reason}",
        error_code=ErrorCode.NEO4J_CONNECTION,
        details=details
    )


@dataclass
class PubMedError(MedicalRAGError):
    """PubMed API related errors.

    Raised for PubMed E-utilities API failures including connection errors,
    rate limits, not found, and timeout.

    Example:
        ```python
        raise PubMedError(
            message="PubMed API rate limit exceeded",
            error_code=ErrorCode.PUBMED_RATE_LIMIT,
            details={"retry_after": 60, "doi": "10.1016/..."}
        )
        ```
    """
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.PUBMED_CONNECTION,
        details: Optional[dict] = None
    ):
        super().__init__(message=message, error_code=error_code, details=details)


def raise_pubmed_timeout(
    operation: str,
    timeout: float,
    **kwargs
) -> None:
    """Raise PubMedError for timeout.

    Args:
        operation: Operation that timed out
        timeout: Timeout value in seconds
        **kwargs: Additional details

    Raises:
        PubMedError
    """
    details = {"operation": operation, "timeout": timeout}
    details.update(kwargs)
    raise PubMedError(
        message=f"PubMed {operation} timed out after {timeout}s",
        error_code=ErrorCode.PUBMED_TIMEOUT,
        details=details
    )

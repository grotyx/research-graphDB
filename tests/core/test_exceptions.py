"""Unit tests for error handling hierarchy."""

import pytest
from src.core.exceptions import (
    MedicalRAGError,
    ValidationError,
    ProcessingError,
    LLMError,
    Neo4jError,
    ChromaDBError,
    NormalizationError,
    ExtractionError,
    ErrorCode,
    raise_validation_error,
    raise_llm_rate_limit,
    raise_neo4j_connection_error,
)


class TestMedicalRAGError:
    """Test base exception class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = MedicalRAGError(
            message="Test error",
            error_code=ErrorCode.PROC_UNKNOWN,
            details={"test": "value"}
        )
        assert error.message == "Test error"
        assert error.error_code == ErrorCode.PROC_UNKNOWN
        assert error.details == {"test": "value"}

    def test_str_format(self):
        """Test string formatting."""
        error = MedicalRAGError(
            message="Test error",
            error_code=ErrorCode.PROC_UNKNOWN,
            details={"key": "value"}
        )
        error_str = str(error)
        assert "[PROC_UNKNOWN]" in error_str
        assert "Test error" in error_str
        assert "key=value" in error_str

    def test_to_dict(self):
        """Test JSON serialization."""
        error = MedicalRAGError(
            message="Test error",
            error_code=ErrorCode.PROC_UNKNOWN,
            details={"key": "value"}
        )
        error_dict = error.to_dict()
        assert error_dict["error_code"] == "PROC_UNKNOWN"
        assert error_dict["message"] == "Test error"
        assert error_dict["details"] == {"key": "value"}


class TestValidationError:
    """Test validation error."""

    def test_validation_error(self):
        """Test ValidationError creation."""
        error = ValidationError(
            message="Missing required field",
            error_code=ErrorCode.VAL_MISSING_FIELD,
            details={"field": "paper_id"}
        )
        assert isinstance(error, MedicalRAGError)
        assert error.error_code == ErrorCode.VAL_MISSING_FIELD

    def test_default_error_code(self):
        """Test default error code."""
        error = ValidationError(message="Invalid value")
        assert error.error_code == ErrorCode.VAL_INVALID_VALUE


class TestLLMError:
    """Test LLM error."""

    def test_llm_error(self):
        """Test LLMError creation."""
        error = LLMError(
            message="Rate limit exceeded",
            error_code=ErrorCode.LLM_RATE_LIMIT,
            details={"retry_after": 60}
        )
        assert isinstance(error, MedicalRAGError)
        assert error.error_code == ErrorCode.LLM_RATE_LIMIT
        assert error.details["retry_after"] == 60


class TestNeo4jError:
    """Test Neo4j error."""

    def test_neo4j_error(self):
        """Test Neo4jError creation."""
        error = Neo4jError(
            message="Connection failed",
            error_code=ErrorCode.NEO4J_CONNECTION,
            details={"uri": "bolt://localhost:7687"}
        )
        assert isinstance(error, MedicalRAGError)
        assert error.error_code == ErrorCode.NEO4J_CONNECTION


class TestChromaDBError:
    """Test ChromaDB error."""

    def test_chromadb_error(self):
        """Test ChromaDBError creation."""
        error = ChromaDBError(
            message="Collection not found",
            error_code=ErrorCode.CHROMA_COLLECTION_NOT_FOUND,
            details={"collection_name": "spine_papers"}
        )
        assert isinstance(error, MedicalRAGError)
        assert error.error_code == ErrorCode.CHROMA_COLLECTION_NOT_FOUND


class TestNormalizationError:
    """Test normalization error."""

    def test_normalization_error(self):
        """Test NormalizationError creation."""
        error = NormalizationError(
            message="No match found",
            error_code=ErrorCode.NORM_NO_MATCH,
            details={"input": "unknown term"}
        )
        assert isinstance(error, MedicalRAGError)
        assert error.error_code == ErrorCode.NORM_NO_MATCH


class TestExtractionError:
    """Test extraction error."""

    def test_extraction_error(self):
        """Test ExtractionError creation."""
        error = ExtractionError(
            message="PDF parsing failed",
            error_code=ErrorCode.EXT_PDF_PARSING,
            details={"file": "test.pdf"}
        )
        assert isinstance(error, MedicalRAGError)
        assert error.error_code == ErrorCode.EXT_PDF_PARSING


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_raise_validation_error(self):
        """Test raise_validation_error convenience function."""
        with pytest.raises(ValidationError) as exc_info:
            raise_validation_error(
                message="Invalid field",
                field="paper_id",
                value="invalid"
            )
        error = exc_info.value
        assert error.details["field"] == "paper_id"
        assert error.details["value"] == "invalid"

    def test_raise_llm_rate_limit(self):
        """Test raise_llm_rate_limit convenience function."""
        with pytest.raises(LLMError) as exc_info:
            raise_llm_rate_limit(
                retry_after=60,
                model="gemini-2.5-flash"
            )
        error = exc_info.value
        assert error.error_code == ErrorCode.LLM_RATE_LIMIT
        assert error.details["retry_after"] == 60
        assert error.details["model"] == "gemini-2.5-flash"
        assert "60s" in error.message

    def test_raise_neo4j_connection_error(self):
        """Test raise_neo4j_connection_error convenience function."""
        with pytest.raises(Neo4jError) as exc_info:
            raise_neo4j_connection_error(
                uri="bolt://localhost:7687",
                reason="Connection refused",
                timeout=30
            )
        error = exc_info.value
        assert error.error_code == ErrorCode.NEO4J_CONNECTION
        assert error.details["uri"] == "bolt://localhost:7687"
        assert error.details["reason"] == "Connection refused"
        assert error.details["timeout"] == 30


class TestErrorCodeEnum:
    """Test ErrorCode enum."""

    def test_error_code_values(self):
        """Test error code string values."""
        assert ErrorCode.LLM_RATE_LIMIT.value == "LLM_RATE_LIMIT"
        assert ErrorCode.NEO4J_CONNECTION.value == "NEO4J_CONNECTION"
        assert ErrorCode.VAL_MISSING_FIELD.value == "VAL_MISSING_FIELD"

    def test_error_code_categories(self):
        """Test error code categorization."""
        # Validation errors start with VAL_
        assert ErrorCode.VAL_MISSING_FIELD.value.startswith("VAL_")
        assert ErrorCode.VAL_INVALID_TYPE.value.startswith("VAL_")

        # LLM errors start with LLM_
        assert ErrorCode.LLM_RATE_LIMIT.value.startswith("LLM_")
        assert ErrorCode.LLM_TIMEOUT.value.startswith("LLM_")

        # Neo4j errors start with NEO4J_
        assert ErrorCode.NEO4J_CONNECTION.value.startswith("NEO4J_")
        assert ErrorCode.NEO4J_QUERY_ERROR.value.startswith("NEO4J_")

"""Example usage of the error handling hierarchy.

This demonstrates how different components should use the exception system.
"""

import asyncio
from src.core.exceptions import (
    ValidationError,
    LLMError,
    Neo4jError,
    NormalizationError,
    ErrorCode,
    raise_validation_error,
    raise_llm_rate_limit,
    raise_neo4j_connection_error,
)


# Example 1: Input Validation
def validate_paper_metadata(paper_data: dict) -> None:
    """Validate paper metadata before processing.

    Args:
        paper_data: Dictionary with paper information

    Raises:
        ValidationError: If required fields are missing or invalid
    """
    required_fields = ["paper_id", "title", "year"]

    for field in required_fields:
        if field not in paper_data:
            raise_validation_error(
                message=f"Missing required field: {field}",
                field=field,
                schema="PaperMetadata",
                provided_fields=list(paper_data.keys())
            )

    # Type validation
    if not isinstance(paper_data["year"], int):
        raise ValidationError(
            message=f"Invalid type for 'year': expected int, got {type(paper_data['year']).__name__}",
            error_code=ErrorCode.VAL_INVALID_TYPE,
            details={
                "field": "year",
                "expected": "int",
                "received": type(paper_data["year"]).__name__,
                "value": paper_data["year"]
            }
        )

    # Value range validation
    if not (1900 <= paper_data["year"] <= 2100):
        raise ValidationError(
            message=f"Year out of valid range: {paper_data['year']}",
            error_code=ErrorCode.VAL_INVALID_VALUE,
            details={
                "field": "year",
                "value": paper_data["year"],
                "valid_range": [1900, 2100]
            }
        )


# Example 2: LLM API Error Handling
async def call_gemini_with_retry(prompt: str, max_retries: int = 3) -> str:
    """Call Gemini API with automatic retry on rate limit.

    Args:
        prompt: Input prompt
        max_retries: Maximum retry attempts

    Returns:
        Generated text response

    Raises:
        LLMError: If all retries fail or unrecoverable error occurs
    """
    for attempt in range(max_retries):
        try:
            # Simulate API call
            response = await simulate_gemini_api(prompt)
            return response

        except LLMError as e:
            if e.error_code == ErrorCode.LLM_RATE_LIMIT:
                retry_after = e.details.get("retry_after", 60)
                print(f"Rate limited. Retrying after {retry_after}s (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_after)
                else:
                    raise  # Re-raise on final attempt

            elif e.error_code == ErrorCode.LLM_QUOTA_EXCEEDED:
                # Don't retry on quota exceeded
                raise

            elif e.error_code == ErrorCode.LLM_TIMEOUT:
                # Retry timeouts
                print(f"Timeout. Retrying (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                else:
                    raise

            else:
                # Unknown LLM error - don't retry
                raise

    raise LLMError(
        message="Max retries exceeded",
        error_code=ErrorCode.LLM_TIMEOUT,
        details={"max_retries": max_retries}
    )


async def simulate_gemini_api(prompt: str) -> str:
    """Simulate Gemini API call (for demo purposes)."""
    import random
    if random.random() < 0.3:
        raise_llm_rate_limit(retry_after=60, model="gemini-2.5-flash")
    return f"Response to: {prompt[:50]}..."


# Example 3: Neo4j Database Error Handling
async def safe_neo4j_query(cypher: str, params: dict = None) -> list[dict]:
    """Execute Neo4j query with comprehensive error handling.

    Args:
        cypher: Cypher query string
        params: Query parameters

    Returns:
        Query results

    Raises:
        Neo4jError: On database errors
    """
    try:
        # Simulate Neo4j query
        result = await simulate_neo4j_query(cypher, params)
        return result

    except Neo4jError as e:
        if e.error_code == ErrorCode.NEO4J_CONNECTION:
            # Log connection error and suggest solutions
            print(f"Neo4j connection failed: {e}")
            print("Suggestions:")
            print("  1. Check if Neo4j is running: docker ps | grep neo4j")
            print("  2. Verify credentials in .env")
            print("  3. Wait 30s for Neo4j to fully initialize")
            raise

        elif e.error_code == ErrorCode.NEO4J_CONSTRAINT_VIOLATION:
            # Handle constraint violations
            print(f"Constraint violation: {e}")
            node_type = e.details.get("node_type")
            property_name = e.details.get("property")
            print(f"Duplicate {node_type} node with {property_name}: {e.details.get('value')}")
            raise

        elif e.error_code == ErrorCode.NEO4J_QUERY_ERROR:
            # Handle query syntax errors
            print(f"Cypher query error: {e}")
            print(f"Query: {cypher}")
            print(f"Params: {params}")
            raise

        else:
            # Unknown Neo4j error
            raise


async def simulate_neo4j_query(cypher: str, params: dict = None) -> list[dict]:
    """Simulate Neo4j query (for demo purposes)."""
    import random
    if random.random() < 0.2:
        raise_neo4j_connection_error(
            uri="bolt://localhost:7687",
            reason="Connection refused",
            timeout=30
        )
    return [{"result": "data"}]


# Example 4: Entity Normalization Error Handling
def normalize_intervention_safe(intervention_text: str) -> str:
    """Normalize intervention with fallback strategies.

    Args:
        intervention_text: Raw intervention text

    Returns:
        Normalized intervention name

    Raises:
        NormalizationError: If normalization completely fails
    """
    try:
        # Simulate normalization
        return simulate_normalization(intervention_text)

    except NormalizationError as e:
        if e.error_code == ErrorCode.NORM_NO_MATCH:
            # No match found - return original with warning
            print(f"Warning: Could not normalize '{intervention_text}'. Using original text.")
            return intervention_text

        elif e.error_code == ErrorCode.NORM_AMBIGUOUS:
            # Multiple matches - pick highest confidence
            candidates = e.details.get("candidates", [])
            confidences = e.details.get("confidences", [])
            if candidates and confidences:
                best_idx = confidences.index(max(confidences))
                best_candidate = candidates[best_idx]
                print(f"Warning: Ambiguous term '{intervention_text}'. Using best match: {best_candidate}")
                return best_candidate
            raise

        else:
            # Unknown normalization error
            raise


def simulate_normalization(text: str) -> str:
    """Simulate normalization (for demo purposes)."""
    import random
    if random.random() < 0.3:
        raise NormalizationError(
            message=f"Ambiguous intervention term: {text}",
            error_code=ErrorCode.NORM_AMBIGUOUS,
            details={
                "input": text,
                "candidates": ["UBE", "BESS"],
                "confidences": [0.8, 0.75]
            }
        )
    return text.upper()


# Example 5: Comprehensive Error Logging
def log_error_to_json(error: Exception, context: dict = None) -> dict:
    """Convert exception to structured log format.

    Args:
        error: Any exception
        context: Additional context (function name, inputs, etc.)

    Returns:
        Structured error log dictionary
    """
    from datetime import datetime
    from src.core.exceptions import MedicalRAGError

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "error_type": type(error).__name__,
        "context": context or {}
    }

    # If it's our custom exception, include structured data
    if isinstance(error, MedicalRAGError):
        log_entry.update(error.to_dict())
    else:
        # Generic exception
        log_entry.update({
            "error_code": "UNKNOWN",
            "message": str(error),
            "details": {}
        })

    return log_entry


# Demo Usage
async def main():
    """Demonstrate error handling patterns."""
    print("=" * 60)
    print("Error Handling Examples")
    print("=" * 60)

    # Example 1: Validation
    print("\n1. Testing input validation...")
    try:
        validate_paper_metadata({"paper_id": "123"})  # Missing title, year
    except ValidationError as e:
        print(f"✓ Caught validation error: {e}")
        print(f"  JSON: {e.to_dict()}")

    # Example 2: LLM with retry
    print("\n2. Testing LLM API with retry...")
    try:
        response = await call_gemini_with_retry("Test prompt")
        print(f"✓ Success: {response}")
    except LLMError as e:
        print(f"✗ Failed after retries: {e}")

    # Example 3: Neo4j error handling
    print("\n3. Testing Neo4j error handling...")
    try:
        result = await safe_neo4j_query("MATCH (n) RETURN n LIMIT 1")
        print(f"✓ Query success: {result}")
    except Neo4jError as e:
        print(f"✗ Database error: {e}")

    # Example 4: Normalization fallback
    print("\n4. Testing entity normalization...")
    try:
        normalized = normalize_intervention_safe("Biportal")
        print(f"✓ Normalized: {normalized}")
    except NormalizationError as e:
        print(f"✗ Normalization failed: {e}")

    # Example 5: Structured logging
    print("\n5. Testing structured error logging...")
    try:
        raise_validation_error(
            message="Test error for logging",
            field="test_field",
            value="invalid"
        )
    except ValidationError as e:
        log = log_error_to_json(e, context={"function": "main", "input": "test"})
        print(f"✓ Structured log:")
        import json
        print(json.dumps(log, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

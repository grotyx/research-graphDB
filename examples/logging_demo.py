"""Demonstration of structured logging system for Spine GraphRAG.

This script shows how to use the logging system in real-world scenarios:
1. Basic logging with context
2. LLM API call logging
3. Neo4j query logging
4. Hybrid search logging
5. PDF processing logging
6. Correlation ID tracking for request tracing
7. Production vs Development mode
8. Integration with exception handling

Run this script to see the logging output:
    python examples/logging_demo.py
"""

import time
from src.core.logging_config import LoggerFactory, MedicalRAGLogger, Environment
from src.core.exceptions import LLMError, Neo4jError, ErrorCode


def demo_basic_logging():
    """Demonstrate basic logging with context."""
    print("\n=== 1. Basic Logging with Context ===\n")

    logger = LoggerFactory.get_logger(__name__)

    logger.info("Processing document started", doc_id="PMC123456", user="researcher_01")
    logger.debug("Extracting metadata", section="methods", page=5)
    logger.warning("Missing author information", field="corresponding_author")
    logger.error("Failed to parse table", table_num=3, reason="malformed_data")


def demo_llm_logging():
    """Demonstrate LLM API call logging."""
    print("\n=== 2. LLM API Call Logging ===\n")

    rag_logger = MedicalRAGLogger(__name__)

    # Successful LLM call
    start = time.time()
    # Simulate API call
    time.sleep(0.1)
    duration_ms = (time.time() - start) * 1000

    rag_logger.log_llm_call(
        model="gemini-2.5-flash",
        tokens_in=2048,
        tokens_out=1024,
        duration_ms=duration_ms,
        success=True,
        cache_hit=False,
        operation="metadata_extraction",
        paper_id="PMC123456"
    )

    # Failed LLM call (rate limit)
    rag_logger.log_llm_call(
        model="gemini-2.5-flash",
        tokens_in=0,
        tokens_out=0,
        duration_ms=50,
        success=False,
        error_code="LLM_RATE_LIMIT",
        operation="vision_processing",
        retry_after=60
    )


def demo_neo4j_logging():
    """Demonstrate Neo4j query logging."""
    print("\n=== 3. Neo4j Query Logging ===\n")

    rag_logger = MedicalRAGLogger(__name__)

    # Successful query
    rag_logger.log_neo4j_query(
        cypher="MATCH (i:Intervention)-[a:AFFECTS]->(o:Outcome) WHERE a.is_significant = true RETURN i, o LIMIT 10",
        params={"limit": 10},
        duration_ms=25.5,
        result_count=10,
        success=True,
        query_type="evidence_search"
    )

    # Failed query
    rag_logger.log_neo4j_query(
        cypher="INVALID QUERY SYNTAX",
        params={},
        duration_ms=5.2,
        result_count=0,
        success=False,
        error_code="NEO4J_QUERY_ERROR",
        error_message="Syntax error near 'INVALID'"
    )


def demo_search_logging():
    """Demonstrate hybrid search logging."""
    print("\n=== 4. Hybrid Search Logging ===\n")

    rag_logger = MedicalRAGLogger(__name__)

    rag_logger.log_search(
        query_type="hybrid",
        graph_results=15,
        vector_results=20,
        final_count=10,
        duration_ms=350.5,
        graph_duration_ms=150.2,
        vector_duration_ms=180.3,
        query="TLIF effectiveness for lumbar stenosis",
        user_id="researcher_01"
    )


def demo_pdf_processing_logging():
    """Demonstrate PDF processing logging."""
    print("\n=== 5. PDF Processing Logging ===\n")

    rag_logger = MedicalRAGLogger(__name__)

    rag_logger.log_pdf_processing(
        filename="spine_fusion_study_2024.pdf",
        pages=12,
        chunks_created=35,
        duration_s=45.2,
        sub_domain="Degenerative",
        anatomy_levels=["L4", "L5"],
        interventions=["TLIF", "PLIF"],
        outcomes=["VAS", "ODI", "JOA"],
        study_type="RCT",
        evidence_level="1b"
    )


def demo_correlation_id_tracking():
    """Demonstrate correlation ID for request tracing."""
    print("\n=== 6. Correlation ID Tracking ===\n")

    # Set correlation ID for a user request
    request_id = LoggerFactory.set_correlation_id("req-2024-001")
    print(f"Request ID: {request_id}\n")

    rag_logger = MedicalRAGLogger(__name__)

    # All logs in this request will have the same correlation_id
    rag_logger.info("User query received", query="TLIF outcomes", user="researcher_01")
    rag_logger.info("Starting graph search", intervention="TLIF")
    rag_logger.info("Starting vector search", similarity_threshold=0.7)
    rag_logger.info("Combining results", total_results=25)

    # Clear correlation ID after request completes
    LoggerFactory.clear_correlation_id()


def demo_exception_integration():
    """Demonstrate integration with exception handling."""
    print("\n=== 7. Exception Integration ===\n")

    rag_logger = MedicalRAGLogger(__name__)

    try:
        # Simulate LLM error
        raise LLMError(
            message="Gemini API quota exceeded",
            error_code=ErrorCode.LLM_QUOTA_EXCEEDED,
            details={"quota_limit": 10000, "tokens_used": 10500}
        )
    except LLMError as e:
        rag_logger.error(
            "LLM error occurred",
            error_code=e.error_code.value,
            error_message=e.message,
            error_details=e.details,
            operation="metadata_extraction"
        )

    try:
        # Simulate Neo4j error
        raise Neo4jError(
            message="Failed to connect to Neo4j database",
            error_code=ErrorCode.NEO4J_CONNECTION,
            details={"uri": "bolt://localhost:7687", "timeout": 30}
        )
    except Neo4jError as e:
        rag_logger.error(
            "Database connection failed",
            error_code=e.error_code.value,
            error_message=e.message,
            error_details=e.details,
            retry_count=3
        )


def demo_production_mode():
    """Demonstrate production mode with JSON output."""
    print("\n=== 8. Production Mode (JSON Output) ===\n")

    # Reconfigure for production
    LoggerFactory._configured = False
    LoggerFactory.configure(Environment.PRODUCTION)

    rag_logger = MedicalRAGLogger(__name__)

    # This will output JSON instead of colored console
    rag_logger.log_llm_call(
        model="gemini-2.5-flash",
        tokens_in=1024,
        tokens_out=512,
        duration_ms=1500,
        operation="pdf_analysis"
    )

    rag_logger.log_neo4j_query(
        cypher="MATCH (p:Paper) RETURN p LIMIT 10",
        params={},
        duration_ms=25,
        result_count=10
    )

    # Reset to development mode
    LoggerFactory._configured = False
    LoggerFactory.configure(Environment.DEVELOPMENT)


def main():
    """Run all logging demonstrations."""
    print("=" * 80)
    print("Spine GraphRAG - Structured Logging Demonstration")
    print("=" * 80)

    # Configure for development (colored console output)
    LoggerFactory.configure(Environment.DEVELOPMENT)

    # Run all demos
    demo_basic_logging()
    demo_llm_logging()
    demo_neo4j_logging()
    demo_search_logging()
    demo_pdf_processing_logging()
    demo_correlation_id_tracking()
    demo_exception_integration()
    demo_production_mode()

    print("\n" + "=" * 80)
    print("Demonstration complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()

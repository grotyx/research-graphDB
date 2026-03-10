"""Pytest configuration for integration tests.

Shared fixtures and configuration for integration test suite.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_neo4j_client():
    """Shared mock Neo4j client fixture."""
    from src.graph.neo4j_client import Neo4jClient

    client = AsyncMock(spec=Neo4jClient)
    client.run_query = AsyncMock(return_value=[])
    client.run_write_query = AsyncMock(return_value={"nodes_created": 1})
    client.get_stats = AsyncMock(return_value={"nodes": {}, "relationships": {}})

    return client


@pytest.fixture
async def integration_test_config():
    """Configuration for integration tests."""
    return {
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_username": "neo4j",
        "neo4j_password": "test_password",
    }


@pytest.fixture
def sample_query_set():
    """Sample query set for testing."""
    return [
        "What is the fusion rate for TLIF?",
        "Compare UBE vs Open surgery for VAS",
        "OLIF effectiveness",
        "Get intervention hierarchy for Endoscopic Surgery",
        "Detect conflicts for OLIF",
    ]

"""Tests for neo4j_client module.

Tests for:
- Mock mode (when Neo4j not available)
- Connection lifecycle
- Query execution
- Paper operations
- Relationship operations
- Search operations
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

from src.graph.neo4j_client import (
    Neo4jClient,
    Neo4jConfig,
    MockSession,
    MockResult,
    MockSummary,
)
from src.graph.spine_schema import PaperNode


class TestNeo4jConfig:
    """Test Neo4jConfig dataclass."""

    def test_config_default_values(self):
        """Test default config values."""
        config = Neo4jConfig()

        assert config.uri == "bolt://localhost:7687"
        assert config.username == "neo4j"
        assert config.password == ""
        assert config.database == "neo4j"
        assert config.max_connection_pool_size == 50

    def test_config_custom_values(self):
        """Test custom config values."""
        config = Neo4jConfig(
            uri="bolt://remote:7687",
            username="admin",
            password="secret123",
            database="spine_graph"
        )

        assert config.uri == "bolt://remote:7687"
        assert config.username == "admin"
        assert config.password == "secret123"
        assert config.database == "spine_graph"

    def test_config_from_env(self):
        """Test loading config from environment variables."""
        with patch.dict(os.environ, {
            "NEO4J_URI": "bolt://test:7687",
            "NEO4J_USERNAME": "testuser",
            "NEO4J_PASSWORD": "testpass",
            "NEO4J_DATABASE": "testdb",
        }):
            config = Neo4jConfig.from_env()

            assert config.uri == "bolt://test:7687"
            assert config.username == "testuser"
            assert config.password == "testpass"
            assert config.database == "testdb"

    def test_config_from_env_defaults(self):
        """Test from_env falls back to defaults when env vars not set."""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            config = Neo4jConfig.from_env()

            assert config.uri == "bolt://localhost:7687"
            assert config.username == "neo4j"


class TestMockMode:
    """Test Neo4j client in mock mode (no Neo4j installation)."""

    @pytest.fixture
    def mock_client(self):
        """Create client in mock mode."""
        # Force mock mode by patching NEO4J_AVAILABLE
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', False):
            client = Neo4jClient()
            return client

    @pytest.mark.asyncio
    async def test_mock_mode_connect(self, mock_client):
        """Test connect in mock mode does nothing."""
        await mock_client.connect()
        assert mock_client._driver is None

    @pytest.mark.asyncio
    async def test_mock_mode_close(self, mock_client):
        """Test close in mock mode does nothing."""
        await mock_client.close()
        # Should not raise

    @pytest.mark.asyncio
    async def test_mock_mode_run_query(self, mock_client):
        """Test run_query in mock mode returns empty list."""
        result = await mock_client.run_query("MATCH (n) RETURN n")
        assert result == []

    @pytest.mark.asyncio
    async def test_mock_mode_run_write_query(self, mock_client):
        """Test run_write_query in mock mode returns mock dict."""
        result = await mock_client.run_write_query("CREATE (n:Test) RETURN n")
        assert result == {"mock": True}

    @pytest.mark.asyncio
    async def test_mock_mode_initialize_schema(self, mock_client):
        """Test initialize_schema in mock mode does nothing."""
        await mock_client.initialize_schema()
        # Should not raise

    @pytest.mark.asyncio
    async def test_mock_mode_context_manager(self, mock_client):
        """Test using client as async context manager in mock mode."""
        async with mock_client as client:
            result = await client.run_query("TEST")
            assert result == []

    @pytest.mark.asyncio
    async def test_mock_mode_create_paper(self, mock_client):
        """Test create_paper in mock mode."""
        paper = PaperNode(
            paper_id="test_001",
            title="Test Paper"
        )

        result = await mock_client.create_paper(paper)
        assert result == {"mock": True}

    @pytest.mark.asyncio
    async def test_mock_mode_get_stats(self, mock_client):
        """Test get_stats in mock mode."""
        stats = await mock_client.get_stats()

        assert stats["mock"] is True
        assert stats["nodes"] == 0
        assert stats["relationships"] == 0


class TestMockClasses:
    """Test MockSession, MockResult, MockSummary classes."""

    @pytest.mark.asyncio
    async def test_mock_session_run(self):
        """Test MockSession.run returns MockResult."""
        session = MockSession()
        result = await session.run("MATCH (n) RETURN n", {"param": "value"})
        assert isinstance(result, MockResult)

    @pytest.mark.asyncio
    async def test_mock_session_execute_write(self):
        """Test MockSession.execute_write."""
        session = MockSession()
        async def tx_func(tx):
            return {"test": True}

        result = await session.execute_write(tx_func)
        assert result == {"mock": True}

    @pytest.mark.asyncio
    async def test_mock_result_data(self):
        """Test MockResult.data returns empty list."""
        result = MockResult()
        data = await result.data()
        assert data == []

    @pytest.mark.asyncio
    async def test_mock_result_single(self):
        """Test MockResult.single returns None."""
        result = MockResult()
        single = await result.single()
        assert single is None

    @pytest.mark.asyncio
    async def test_mock_result_consume(self):
        """Test MockResult.consume returns MockSummary."""
        result = MockResult()
        summary = await result.consume()
        assert isinstance(summary, MockSummary)

    def test_mock_summary_counters(self):
        """Test MockSummary.counters."""
        summary = MockSummary()

        assert summary.counters.nodes_created == 0
        assert summary.counters.nodes_deleted == 0
        assert summary.counters.relationships_created == 0
        assert summary.counters.relationships_deleted == 0
        assert summary.counters.properties_set == 0


class TestNeo4jClientInitialization:
    """Test Neo4jClient initialization."""

    def test_client_init_default(self):
        """Test client initialization with defaults."""
        client = Neo4jClient()

        assert client.config is not None
        assert client._driver is None

    def test_client_init_custom_config(self):
        """Test client initialization with custom config."""
        config = Neo4jConfig(uri="bolt://custom:7687")
        client = Neo4jClient(config=config)

        assert client.config.uri == "bolt://custom:7687"

    @pytest.mark.skipif(not hasattr(sys.modules.get("src.graph.neo4j_client"), "NEO4J_AVAILABLE") or not sys.modules.get("src.graph.neo4j_client").NEO4J_AVAILABLE, reason="Neo4j not installed")
    def test_client_init_from_env(self):
        """Test client initialization loads from env."""
        with patch.dict(os.environ, {"NEO4J_URI": "bolt://envtest:7687"}):
            client = Neo4jClient()
            assert client.config.uri == "bolt://envtest:7687"


class TestConnectionLifecycle:
    """Test connection lifecycle (requires mocking)."""

    @pytest.fixture
    def mock_driver(self):
        """Create mock Neo4j driver."""
        driver = AsyncMock()
        session = AsyncMock()
        result = AsyncMock()

        # Setup mock chain
        driver.session.return_value.__aenter__.return_value = session
        session.run.return_value = result
        result.single.return_value = {"test": 1}

        return driver

    @pytest.mark.skip(reason="Requires Neo4j driver installed")
    @pytest.mark.skip(reason="Requires Neo4j driver")
    @pytest.mark.asyncio
    async def test_connect_creates_driver(self, mock_driver):
        """Test connect creates driver."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', True):
            with patch('src.graph.neo4j_client.AsyncGraphDatabase.driver', return_value=mock_driver):
                client = Neo4jClient()
                await client.connect()

                assert client._driver is not None

    @pytest.mark.skip(reason="Requires Neo4j driver")
    @pytest.mark.asyncio
    async def test_connect_idempotent(self, mock_driver):
        """Test connect is idempotent (doesn't reconnect)."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', True):
            with patch('src.graph.neo4j_client.AsyncGraphDatabase.driver', return_value=mock_driver) as mock_create:
                client = Neo4jClient()
                await client.connect()
                await client.connect()  # Second call

                # Driver creation called only once
                assert mock_create.call_count == 1

    @pytest.mark.skip(reason="Requires Neo4j driver")
    @pytest.mark.asyncio
    async def test_close_closes_driver(self, mock_driver):
        """Test close closes driver."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', True):
            with patch('src.graph.neo4j_client.AsyncGraphDatabase.driver', return_value=mock_driver):
                client = Neo4jClient()
                await client.connect()
                await client.close()

                mock_driver.close.assert_called_once()
                assert client._driver is None

    @pytest.mark.skip(reason="Requires Neo4j driver")
    @pytest.mark.asyncio
    async def test_context_manager(self, mock_driver):
        """Test async context manager."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', True):
            with patch('src.graph.neo4j_client.AsyncGraphDatabase.driver', return_value=mock_driver):
                async with Neo4jClient() as client:
                    assert client._driver is not None

                # Should close after exiting context
                mock_driver.close.assert_called_once()


class TestQueryExecution:
    """Test query execution (in mock mode)."""

    @pytest.fixture
    def client(self):
        """Create mock mode client."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', False):
            return Neo4jClient()

    @pytest.mark.asyncio
    async def test_run_query_simple(self, client):
        """Test run_query with simple query."""
        result = await client.run_query("MATCH (n) RETURN n LIMIT 10")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_query_with_parameters(self, client):
        """Test run_query with parameters."""
        result = await client.run_query(
            "MATCH (n:Paper {paper_id: $id}) RETURN n",
            parameters={"id": "test_001"}
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_query_fetch_all(self, client):
        """Test run_query with fetch_all=True."""
        result = await client.run_query(
            "MATCH (n) RETURN n",
            fetch_all=True
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_query_fetch_single(self, client):
        """Test run_query with fetch_all=False."""
        result = await client.run_query(
            "MATCH (n) RETURN n LIMIT 1",
            fetch_all=False
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_run_write_query(self, client):
        """Test run_write_query."""
        result = await client.run_write_query(
            "CREATE (n:Test {name: $name}) RETURN n",
            parameters={"name": "test"}
        )
        assert isinstance(result, dict)


class TestPaperOperations:
    """Test paper-related operations."""

    @pytest.fixture
    def client(self):
        """Create mock mode client."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', False):
            return Neo4jClient()

    @pytest.mark.asyncio
    async def test_create_paper(self, client):
        """Test create_paper."""
        paper = PaperNode(
            paper_id="test_001",
            title="Test Paper",
            year=2024
        )

        result = await client.create_paper(paper)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_paper(self, client):
        """Test get_paper."""
        result = await client.get_paper("test_001")
        assert result is None  # Mock mode returns None

    @pytest.mark.asyncio
    async def test_list_papers(self, client):
        """Test list_papers."""
        result = await client.list_papers(limit=10)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_list_papers_with_filters(self, client):
        """Test list_papers with filters."""
        result = await client.list_papers(
            sub_domain="Degenerative",
            evidence_level="1b",
            limit=20
        )
        assert isinstance(result, list)


class TestRelationshipOperations:
    """Test relationship creation operations."""

    @pytest.fixture
    def client(self):
        """Create mock mode client."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', False):
            return Neo4jClient()

    @pytest.mark.asyncio
    async def test_create_studies_relation(self, client):
        """Test create_studies_relation."""
        result = await client.create_studies_relation(
            paper_id="test_001",
            pathology_name="Lumbar Stenosis",
            is_primary=True
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_create_investigates_relation(self, client):
        """Test create_investigates_relation."""
        result = await client.create_investigates_relation(
            paper_id="test_001",
            intervention_name="TLIF",
            is_comparison=True
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_create_affects_relation_simple(self, client):
        """Test create_affects_relation with minimal params."""
        result = await client.create_affects_relation(
            intervention_name="UBE",
            outcome_name="VAS",
            source_paper_id="test_001"
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_create_affects_relation_full(self, client):
        """Test create_affects_relation with all params."""
        result = await client.create_affects_relation(
            intervention_name="TLIF",
            outcome_name="Fusion Rate",
            source_paper_id="test_002",
            value="92%",
            value_control="85%",
            p_value=0.01,
            effect_size="0.7",
            confidence_interval="95% CI: 0.02-0.15",
            is_significant=True,
            direction="improved"
        )
        assert isinstance(result, dict)


class TestSearchOperations:
    """Test search/query operations."""

    @pytest.fixture
    def client(self):
        """Create mock mode client."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', False):
            return Neo4jClient()

    @pytest.mark.asyncio
    async def test_get_intervention_hierarchy(self, client):
        """Test get_intervention_hierarchy."""
        result = await client.get_intervention_hierarchy("TLIF")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_intervention_children(self, client):
        """Test get_intervention_children."""
        result = await client.get_intervention_children("Interbody Fusion")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_effective_interventions(self, client):
        """Test search_effective_interventions."""
        result = await client.search_effective_interventions("VAS")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_interventions_for_pathology(self, client):
        """Test search_interventions_for_pathology."""
        result = await client.search_interventions_for_pathology("Lumbar Stenosis")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_paper_relations(self, client):
        """Test get_paper_relations."""
        result = await client.get_paper_relations("test_001")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_find_conflicting_results(self, client):
        """Test find_conflicting_results."""
        result = await client.find_conflicting_results("TLIF")
        assert isinstance(result, list)


class TestSchemaInitialization:
    """Test schema initialization."""

    @pytest.fixture
    def client(self):
        """Create mock mode client."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', False):
            return Neo4jClient()

    @pytest.mark.asyncio
    async def test_initialize_schema_mock_mode(self, client):
        """Test initialize_schema in mock mode."""
        await client.initialize_schema()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_initialize_schema_idempotent(self, client):
        """Test initialize_schema is idempotent."""
        await client.initialize_schema()
        await client.initialize_schema()
        # Should not raise

    @pytest.mark.asyncio
    async def test_initialize_schema_sets_flag(self, client):
        """Test initialize_schema sets _initialized flag."""
        if hasattr(client, '_initialized'):
            assert not client._initialized
        await client.initialize_schema()
        if hasattr(client, '_initialized'):
            assert client._initialized


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def client(self):
        """Create mock mode client."""
        with patch('src.graph.neo4j_client.NEO4J_AVAILABLE', False):
            return Neo4jClient()

    @pytest.mark.asyncio
    async def test_query_with_none_parameters(self, client):
        """Test query execution with None parameters."""
        result = await client.run_query(
            "MATCH (n) RETURN n",
            parameters=None
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_empty_query(self, client):
        """Test empty query string."""
        result = await client.run_query("")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_session_context_manager(self, client):
        """Test session context manager in mock mode."""
        async with client.session() as session:
            assert isinstance(session, MockSession)

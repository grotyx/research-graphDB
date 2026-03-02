"""Tests for DocumentHandler.

Comprehensive tests for document management operations including:
- Document listing with user filtering
- System statistics retrieval
- Document deletion with authorization
- Database reset with authorization
- Paper summarization
- Document export
- Error handling and edge cases
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from medical_mcp.handlers.document_handler import DocumentHandler
from core.exceptions import Neo4jError, ErrorCode


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_server():
    """Create a mock MedicalKAGServer instance."""
    server = Mock()
    server.neo4j_client = Mock()
    server.neo4j_client._driver = Mock()
    server.current_user = "system"
    server.enable_llm = True
    server._get_user_filter_clause = Mock(return_value=("", {}))
    return server


@pytest.fixture
def mock_server_no_neo4j():
    """Create a mock server without Neo4j."""
    server = Mock()
    server.neo4j_client = None
    server.current_user = "system"
    server.enable_llm = False
    server._get_user_filter_clause = Mock(return_value=("", {}))
    return server


@pytest.fixture
def handler(mock_server):
    """Create a DocumentHandler with mock server."""
    return DocumentHandler(mock_server)


@pytest.fixture
def handler_no_neo4j(mock_server_no_neo4j):
    """Create a DocumentHandler without Neo4j."""
    return DocumentHandler(mock_server_no_neo4j)


def _make_async_context_manager(mock_client):
    """Helper to make a mock Neo4j client act as an async context manager."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ============================================================================
# TestDocumentHandlerInit
# ============================================================================

class TestDocumentHandlerInit:
    """Test DocumentHandler initialization."""

    def test_init(self, mock_server):
        handler = DocumentHandler(mock_server)
        assert handler.server == mock_server
        assert handler.current_user == "system"

    def test_neo4j_client_property(self, handler, mock_server):
        assert handler.neo4j_client == mock_server.neo4j_client

    def test_user_filter_clause(self, handler):
        clause, params = handler._get_user_filter_clause("p")
        assert isinstance(clause, str)
        assert isinstance(params, dict)


# ============================================================================
# TestListDocuments
# ============================================================================

class TestListDocuments:
    """Test list_documents method."""

    @pytest.mark.asyncio
    async def test_list_documents_success(self, handler, mock_server):
        """Test listing documents with results."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[
            {
                "document_id": "paper_001",
                "title": "Lumbar Fusion Study",
                "year": 2024,
                "evidence_level": "1b",
                "source": "pdf",
                "owner": "system",
                "shared": True,
                "chunk_count": 5,
                "tier1_count": 2,
                "tier2_count": 3,
            }
        ])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.list_documents()

        assert result["success"] is True
        assert result["total_documents"] == 1
        assert result["total_chunks"] == 5
        assert result["tier_distribution"]["tier1"] == 2
        assert result["tier_distribution"]["tier2"] == 3
        assert result["stats"]["storage_backend"] == "neo4j"
        assert len(result["documents"]) == 1
        doc = result["documents"][0]
        assert doc["document_id"] == "paper_001"
        assert doc["chunk_count"] == 5

    @pytest.mark.asyncio
    async def test_list_documents_empty(self, handler, mock_server):
        """Test listing with no documents."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.list_documents()

        assert result["success"] is True
        assert result["total_documents"] == 0
        assert result["total_chunks"] == 0
        assert result["documents"] == []

    @pytest.mark.asyncio
    async def test_list_documents_multiple(self, handler, mock_server):
        """Test listing multiple documents."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[
            {"document_id": "p1", "title": "Paper 1", "year": 2023,
             "evidence_level": "2a", "source": "pdf", "owner": "system",
             "shared": True, "chunk_count": 3, "tier1_count": 1, "tier2_count": 2},
            {"document_id": "p2", "title": "Paper 2", "year": 2024,
             "evidence_level": "1b", "source": "pubmed", "owner": "user1",
             "shared": False, "chunk_count": 7, "tier1_count": 4, "tier2_count": 3},
        ])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.list_documents()

        assert result["total_documents"] == 2
        assert result["total_chunks"] == 10
        assert result["tier_distribution"]["tier1"] == 5

    @pytest.mark.asyncio
    async def test_list_documents_null_counts(self, handler, mock_server):
        """Test handling of null chunk counts."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[
            {"document_id": "p1", "title": "Paper", "year": 2023,
             "evidence_level": "", "source": "", "owner": "system",
             "shared": True, "chunk_count": None, "tier1_count": None, "tier2_count": None},
        ])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.list_documents()

        assert result["success"] is True
        assert result["documents"][0]["chunk_count"] == 0
        assert result["documents"][0]["tier1_chunks"] == 0

    @pytest.mark.asyncio
    async def test_list_documents_no_neo4j(self, handler_no_neo4j):
        """Test list_documents when Neo4j is unavailable."""
        result = await handler_no_neo4j.list_documents()
        assert result["success"] is False


# ============================================================================
# TestGetStats
# ============================================================================

class TestGetStats:
    """Test get_stats method."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, handler, mock_server):
        """Test successful stats retrieval."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[
            {"paper_count": 10, "chunk_count": 50, "tier1_count": 20, "tier2_count": 30}
        ])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.get_stats()

        assert result["document_count"] == 10
        assert result["chunk_count"] == 50
        assert result["tier1_count"] == 20
        assert result["tier2_count"] == 30
        assert result["neo4j_available"] is True
        assert result["llm_enabled"] is True

    @pytest.mark.asyncio
    async def test_get_stats_no_neo4j(self, handler_no_neo4j):
        """Test stats when Neo4j is unavailable."""
        result = await handler_no_neo4j.get_stats()

        assert result["document_count"] == 0
        assert result["neo4j_available"] is False
        assert result["llm_enabled"] is False

    @pytest.mark.asyncio
    async def test_get_stats_empty_result(self, handler, mock_server):
        """Test stats when query returns no results."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.get_stats()

        assert result["document_count"] == 0
        assert result["neo4j_available"] is True

    @pytest.mark.asyncio
    async def test_get_stats_exception(self, handler, mock_server):
        """Test stats when Neo4j throws an exception."""
        mock_server.neo4j_client.__aenter__ = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        result = await handler.get_stats()

        assert result["document_count"] == 0
        assert result["neo4j_available"] is False

    @pytest.mark.asyncio
    async def test_get_stats_null_values(self, handler, mock_server):
        """Test stats with null values from query."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[
            {"paper_count": None, "chunk_count": None, "tier1_count": None, "tier2_count": None}
        ])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.get_stats()

        assert result["document_count"] == 0
        assert result["chunk_count"] == 0


# ============================================================================
# TestDeleteDocument
# ============================================================================

class TestDeleteDocument:
    """Test delete_document method."""

    @pytest.mark.asyncio
    async def test_delete_document_success(self, handler, mock_server):
        """Test successful document deletion."""
        mock_client = AsyncMock()
        mock_client.get_paper = AsyncMock(return_value={"owner": "system"})
        mock_client.run_query = AsyncMock(return_value=[{"chunk_count": 3}])
        mock_client.delete_paper = AsyncMock(return_value={
            "nodes_deleted": 4, "relationships_deleted": 6
        })
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.delete_document("paper_001")

        assert result["success"] is True
        assert result["document_id"] == "paper_001"
        assert result["deleted_chunks"] == 3
        assert result["neo4j_nodes"] == 4
        assert result["neo4j_relationships"] == 6

    @pytest.mark.asyncio
    async def test_delete_document_access_denied(self, handler, mock_server):
        """Test deletion denied for non-owner."""
        mock_server.current_user = "user_a"
        mock_client = AsyncMock()
        mock_client.get_paper = AsyncMock(return_value={"owner": "user_b"})
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.delete_document("paper_001")

        assert result["success"] is False
        assert "Access denied" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_document_system_user_can_delete_any(self, handler, mock_server):
        """Test system user can delete any document."""
        mock_server.current_user = "system"
        mock_client = AsyncMock()
        mock_client.get_paper = AsyncMock(return_value={"owner": "other_user"})
        mock_client.run_query = AsyncMock(return_value=[{"chunk_count": 0}])
        mock_client.delete_paper = AsyncMock(return_value={
            "nodes_deleted": 1, "relationships_deleted": 0
        })
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.delete_document("paper_001")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_delete_document_no_neo4j(self, handler_no_neo4j):
        """Test deletion without Neo4j."""
        result = await handler_no_neo4j.delete_document("paper_001")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_delete_document_paper_not_found(self, handler, mock_server):
        """Test deletion when paper has no owner (default behavior)."""
        mock_client = AsyncMock()
        mock_client.get_paper = AsyncMock(return_value=None)
        mock_client.run_query = AsyncMock(return_value=[{"chunk_count": 0}])
        mock_client.delete_paper = AsyncMock(return_value={
            "nodes_deleted": 0, "relationships_deleted": 0
        })
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.delete_document("nonexistent")
        # If paper is None, authorization check is skipped, proceed to delete
        assert result["success"] is True


# ============================================================================
# TestResetDatabase
# ============================================================================

class TestResetDatabase:
    """Test reset_database method."""

    @pytest.mark.asyncio
    async def test_reset_database_success(self, handler, mock_server):
        """Test successful database reset."""
        mock_client = AsyncMock()
        mock_client.clear_database = AsyncMock(return_value={
            "nodes_deleted": 100, "relationships_deleted": 200
        })
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.reset_database()

        assert result["success"] is True
        assert result["neo4j_nodes_deleted"] == 100
        assert result["neo4j_relationships_deleted"] == 200
        assert result["taxonomy_cleared"] is False

    @pytest.mark.asyncio
    async def test_reset_database_with_taxonomy(self, handler, mock_server):
        """Test reset including taxonomy."""
        mock_client = AsyncMock()
        mock_client.clear_all_including_taxonomy = AsyncMock(return_value={
            "nodes_deleted": 500, "relationships_deleted": 800
        })
        mock_client.initialize_schema = AsyncMock()
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.reset_database(include_taxonomy=True)

        assert result["success"] is True
        assert result["taxonomy_cleared"] is True
        assert result["neo4j_nodes_deleted"] == 500
        mock_client.initialize_schema.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_database_access_denied(self, handler, mock_server):
        """Test reset denied for non-system user."""
        mock_server.current_user = "regular_user"

        result = await handler.reset_database()

        assert result["success"] is False
        assert "Access denied" in result["error"]

    @pytest.mark.asyncio
    async def test_reset_database_no_neo4j(self, handler_no_neo4j):
        """Test reset without Neo4j."""
        result = await handler_no_neo4j.reset_database()
        assert result["success"] is False


# ============================================================================
# TestSummarizePaper
# ============================================================================

class TestSummarizePaper:
    """Test summarize_paper method."""

    @pytest.mark.asyncio
    async def test_summarize_paper_empty_id(self, handler):
        """Test summarize with empty paper ID."""
        result = await handler.summarize_paper("")
        assert result["success"] is False
        assert "paper_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_summarize_paper_not_found(self, handler, mock_server):
        """Test summarize when paper doesn't exist."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.summarize_paper("nonexistent")
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_summarize_paper_existing_summary(self, handler, mock_server):
        """Test summarize with existing summary (brief style)."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[{
            "title": "Test Paper",
            "year": 2024,
            "study_type": "RCT",
            "evidence_level": "1b",
            "existing_summary": "This is an existing summary.",
            "chunk_texts": ["chunk1 text", "chunk2 text"],
        }])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.summarize_paper("paper_001", style="brief")

        assert result["success"] is True
        assert result["summary"] == "This is an existing summary."
        assert result["source"] == "existing"
        assert result["style"] == "brief"

    @pytest.mark.asyncio
    async def test_summarize_paper_no_chunks(self, handler, mock_server):
        """Test summarize with no text content."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[{
            "title": "Test Paper",
            "year": 2024,
            "study_type": "RCT",
            "evidence_level": "1b",
            "existing_summary": None,
            "chunk_texts": [],
        }])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.summarize_paper("paper_001", style="detailed")
        assert result["success"] is False
        assert "No text content" in result["error"]

    @pytest.mark.asyncio
    async def test_summarize_paper_no_neo4j(self, handler_no_neo4j):
        """Test summarize without Neo4j."""
        result = await handler_no_neo4j.summarize_paper("paper_001")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_summarize_paper_generated(self, handler, mock_server):
        """Test summarize generates new summary via LLM."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[{
            "title": "Test Paper",
            "year": 2024,
            "study_type": "RCT",
            "evidence_level": "1b",
            "existing_summary": None,
            "chunk_texts": ["This is the paper text about spine surgery."],
        }])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        mock_summary_result = Mock()
        mock_summary_result.text = "Generated summary text."
        mock_summary_result.word_count = 5
        mock_summary_result.sections = {"methods": "test"}

        # The imports happen inside the method via from ... import, so we patch
        # the modules dict to make them importable
        mock_summary_gen_module = MagicMock()
        mock_gen_class = Mock()
        mock_gen_instance = Mock()
        mock_gen_instance.generate = AsyncMock(return_value=mock_summary_result)
        mock_gen_class.return_value = mock_gen_instance
        mock_summary_gen_module.SummaryGenerator = mock_gen_class

        mock_doc_type_module = MagicMock()
        mock_doc_type_module.DocumentType.JOURNAL_ARTICLE = "journal-article"

        with patch.dict(sys.modules, {
            "builder.summary_generator": mock_summary_gen_module,
            "builder.document_type_detector": mock_doc_type_module,
        }):
            result = await handler.summarize_paper("paper_001", style="detailed")

        assert result["success"] is True
        assert result["summary"] == "Generated summary text."
        assert result["source"] == "generated"

    @pytest.mark.asyncio
    async def test_summarize_paper_import_error(self, handler, mock_server):
        """Test summarize when SummaryGenerator is not available."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[{
            "title": "Test Paper",
            "year": 2024,
            "study_type": "RCT",
            "evidence_level": "1b",
            "existing_summary": None,
            "chunk_texts": ["Some text content."],
        }])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        # Remove the module from sys.modules to force ImportError
        with patch.dict(sys.modules, {"builder.summary_generator": None}):
            result = await handler.summarize_paper("paper_001", style="detailed")

        assert result["success"] is False


# ============================================================================
# TestExportDocument
# ============================================================================

class TestExportDocument:
    """Test export_document method."""

    @pytest.mark.asyncio
    async def test_export_document_empty_id(self, handler):
        """Test export with empty document ID."""
        result = await handler.export_document("")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_export_document_not_found(self, handler, mock_server):
        """Test export when document doesn't exist."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.export_document("nonexistent")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_export_document_success(self, handler, mock_server, tmp_path):
        """Test successful document export."""
        mock_client = AsyncMock()
        mock_client.run_query = AsyncMock(return_value=[{
            "paper_id": "paper_001",
            "title": "Lumbar Fusion",
            "year": 2024,
            "authors": ["Park SM", "Kim HJ"],
            "journal": "Spine",
            "doi": "10.1234/test",
            "evidence_level": "1b",
            "study_type": "RCT",
            "sub_domain": "Degenerative",
            "anatomy_level": "Lumbar",
            "pathologies": ["Stenosis"],
            "interventions": ["PLIF"],
            "outcomes": ["VAS"],
            "chunk_id": "c1",
            "chunk_content": "This is chunk text.",
            "chunk_tier": "tier1",
            "chunk_section": "methods",
            "chunk_is_key_finding": True,
            "chunk_index": 0,
        }])
        mock_server.neo4j_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        with patch("medical_mcp.handlers.document_handler.Path") as MockPath:
            mock_dir = MagicMock()
            MockPath.return_value = mock_dir
            mock_dir.__truediv__ = MagicMock(return_value=mock_dir)
            mock_dir.mkdir = MagicMock()

            with patch("builtins.open", MagicMock()):
                with patch("json.dump"):
                    result = await handler.export_document("paper_001")

        assert result["success"] is True
        assert result["document_id"] == "paper_001"
        assert result["chunks_count"] == 1

    @pytest.mark.asyncio
    async def test_export_document_no_neo4j(self, handler_no_neo4j):
        """Test export without Neo4j raises Neo4jError (not decorated with safe_execute)."""
        with pytest.raises(Neo4jError):
            await handler_no_neo4j.export_document("paper_001")

    @pytest.mark.asyncio
    async def test_export_document_neo4j_error(self, handler, mock_server):
        """Test export when Neo4j query fails."""
        mock_server.neo4j_client.__aenter__ = AsyncMock(
            side_effect=Exception("Neo4j connection error")
        )
        mock_server.neo4j_client.__aexit__ = AsyncMock(return_value=False)

        result = await handler.export_document("paper_001")
        assert result["success"] is False


# ============================================================================
# TestUserFiltering
# ============================================================================

class TestUserFiltering:
    """Test user filtering behavior."""

    def test_user_filter_delegates_to_server(self, handler, mock_server):
        """Test that user filter delegates to server method."""
        mock_server._get_user_filter_clause.return_value = (
            "WHERE p.owner = $owner", {"owner": "user1"}
        )
        clause, params = handler._get_user_filter_clause("p")
        assert "WHERE" in clause
        assert params["owner"] == "user1"
        mock_server._get_user_filter_clause.assert_called_with("p")

    def test_user_filter_default_alias(self, handler, mock_server):
        """Test default alias parameter."""
        handler._get_user_filter_clause()
        mock_server._get_user_filter_clause.assert_called_with("p")

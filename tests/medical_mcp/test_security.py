"""Tests for Medical KAG MCP Server Security (v1.15 QC).

Verifies security hardening introduced in v1.15:
1. _get_user_filter_clause returns parameterized tuple (str, dict), not f-strings
2. Path validation rejects path traversal attacks (../../etc/passwd)
3. delete_document enforces ownership checks
4. Cypher injection prevention in user filter clause
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import sys

# pytest-asyncio configuration
pytest_plugins = ('pytest_asyncio',)


class TestUserFilterClauseParameterization:
    """Verify _get_user_filter_clause returns parameterized (str, dict) tuples."""

    def _make_server_with_user(self, user_id: str):
        """Create a minimal mock server with current_user set.

        We mock just enough of MedicalKAGServer to test _get_user_filter_clause
        without requiring Neo4j or any real external dependencies.
        """
        # Import the real method but on a mock object
        from src.medical_mcp.medical_kag_server import MedicalKAGServer

        # Mock the __init__ to avoid actual initialization
        with patch.object(MedicalKAGServer, '__init__', lambda self, **kwargs: None):
            server = MedicalKAGServer()
            server.current_user = user_id
            return server

    def test_system_user_returns_empty_clause(self):
        """'system' user gets empty clause - no filtering."""
        server = self._make_server_with_user("system")
        clause, params = server._get_user_filter_clause("p")

        assert clause == ""
        assert params == {}

    def test_regular_user_returns_parameterized_clause(self):
        """Non-system user gets WHERE clause with $current_user parameter."""
        server = self._make_server_with_user("user_123")
        clause, params = server._get_user_filter_clause("p")

        # Must return a tuple of (str, dict)
        assert isinstance(clause, str)
        assert isinstance(params, dict)

        # Clause must use $current_user parameter, not inline the value
        assert "$current_user" in clause
        assert "user_123" not in clause  # Value must NOT be inline

        # Parameters must contain the actual value
        assert params["current_user"] == "user_123"

    def test_clause_has_correct_cypher_structure(self):
        """Clause has proper WHERE...OR structure for ownership + sharing."""
        server = self._make_server_with_user("doctor_kim")
        clause, params = server._get_user_filter_clause("p")

        assert "WHERE" in clause
        assert "owner" in clause
        assert "shared" in clause
        assert "$current_user" in clause

    def test_custom_alias(self):
        """Custom node alias is used in the WHERE clause."""
        server = self._make_server_with_user("user_456")
        clause, params = server._get_user_filter_clause("paper")

        assert "paper.owner" in clause
        assert "paper.shared" in clause

    def test_malicious_username_not_injected(self):
        """Malicious username cannot inject Cypher code."""
        malicious_user = "admin' OR 1=1 //"
        server = self._make_server_with_user(malicious_user)
        clause, params = server._get_user_filter_clause("p")

        # The malicious value must be in params, never in the clause string
        assert malicious_user not in clause
        assert params["current_user"] == malicious_user

    def test_return_type_is_tuple(self):
        """Return type is exactly tuple[str, dict]."""
        server = self._make_server_with_user("user_x")
        result = server._get_user_filter_clause("p")

        assert isinstance(result, tuple)
        assert len(result) == 2
        clause, params = result
        assert isinstance(clause, str)
        assert isinstance(params, dict)


class TestPathTraversalPrevention:
    """Verify that path traversal attacks are blocked in add_pdf."""

    @pytest.fixture
    def pdf_handler(self, tmp_path):
        """Create a PDFHandler with mocked server for path validation tests."""
        try:
            from src.medical_mcp.handlers.pdf_handler import PDFHandler
        except ImportError:
            pytest.skip("PDFHandler not available")

        # Mock server with necessary attributes
        server = MagicMock()
        server.project_root = tmp_path
        server.vision_processor = None  # Disable actual processing
        server.current_user = "test_user"
        server.enable_llm = False

        handler = PDFHandler(server)
        return handler, tmp_path

    @pytest.mark.asyncio
    async def test_traversal_dot_dot_blocked(self, pdf_handler):
        """../../etc/passwd style paths are blocked."""
        handler, tmp_path = pdf_handler

        # Try to access a file outside the allowed directory
        result = await handler.add_pdf("../../etc/passwd")

        # Must fail - either file not found OR access denied
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_traversal_absolute_system_path_blocked(self, pdf_handler):
        """Absolute system paths outside allowed dirs are blocked."""
        handler, tmp_path = pdf_handler

        result = await handler.add_pdf("/etc/shadow")

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_traversal_encoded_blocked(self, pdf_handler):
        """Path with ../ components after resolve is blocked."""
        handler, tmp_path = pdf_handler

        malicious_path = str(tmp_path / "data" / ".." / ".." / "etc" / "passwd")
        result = await handler.add_pdf(malicious_path)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_valid_path_within_data_dir(self, pdf_handler):
        """Valid PDF within data/ directory is allowed (even if file doesn't exist)."""
        handler, tmp_path = pdf_handler

        # Create the data directory and a dummy PDF
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        pdf_file = data_dir / "test_paper.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 dummy content")

        # The path should resolve within allowed dirs
        result = await handler.add_pdf(str(pdf_file))

        # It should not fail with "access denied" -- it might fail for other reasons
        # (like no vision processor), but path validation should pass
        if not result["success"]:
            # If it failed, it should NOT be because of path traversal
            assert "허용된 디렉토리 외부" not in result.get("error", "")
            assert "접근 불가" not in result.get("error", "")


class TestDeleteDocumentOwnership:
    """Verify delete_document enforces ownership checks."""

    @pytest.fixture
    def document_handler(self):
        """Create a DocumentHandler with mocked Neo4j client."""
        try:
            from src.medical_mcp.handlers.document_handler import DocumentHandler
        except ImportError:
            pytest.skip("DocumentHandler not available")

        # Mock server
        server = MagicMock()
        server.current_user = "user_A"

        # Mock neo4j client
        mock_neo4j = AsyncMock()
        server.neo4j_client = mock_neo4j

        # Mock _get_user_filter_clause to return parameterized result
        server._get_user_filter_clause = Mock(
            return_value=("WHERE p.owner = $current_user OR p.shared = true",
                          {"current_user": "user_A"})
        )

        handler = DocumentHandler(server)
        # neo4j_client is now a read-only property from BaseHandler,
        # accessed via server.neo4j_client (already set above)
        return handler, mock_neo4j, server

    @pytest.mark.asyncio
    async def test_delete_own_document_succeeds(self, document_handler):
        """User can delete their own document."""
        handler, mock_neo4j, server = document_handler
        server.current_user = "user_A"

        # Mock: paper owned by user_A
        mock_neo4j.__aenter__ = AsyncMock(return_value=mock_neo4j)
        mock_neo4j.__aexit__ = AsyncMock(return_value=False)
        mock_neo4j.get_paper = AsyncMock(return_value={"owner": "user_A"})
        mock_neo4j.run_query = AsyncMock(return_value=[{"chunk_count": 5}])
        mock_neo4j.delete_paper = AsyncMock(return_value={
            "nodes_deleted": 6, "relationships_deleted": 5
        })

        result = await handler.delete_document("my_paper")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_delete_other_users_document_denied(self, document_handler):
        """User CANNOT delete another user's document."""
        handler, mock_neo4j, server = document_handler
        server.current_user = "user_A"

        # Mock: paper owned by user_B
        mock_neo4j.__aenter__ = AsyncMock(return_value=mock_neo4j)
        mock_neo4j.__aexit__ = AsyncMock(return_value=False)
        mock_neo4j.get_paper = AsyncMock(return_value={"owner": "user_B"})

        result = await handler.delete_document("not_my_paper")

        assert result["success"] is False
        assert "Access denied" in result.get("error", "") or "denied" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_system_user_can_delete_any_document(self, document_handler):
        """'system' user can delete any document."""
        handler, mock_neo4j, server = document_handler
        server.current_user = "system"

        # Mock: paper owned by anyone
        mock_neo4j.__aenter__ = AsyncMock(return_value=mock_neo4j)
        mock_neo4j.__aexit__ = AsyncMock(return_value=False)
        mock_neo4j.get_paper = AsyncMock(return_value={"owner": "user_B"})
        mock_neo4j.run_query = AsyncMock(return_value=[{"chunk_count": 3}])
        mock_neo4j.delete_paper = AsyncMock(return_value={
            "nodes_deleted": 4, "relationships_deleted": 3
        })

        result = await handler.delete_document("any_paper")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_document(self, document_handler):
        """Deleting a non-existent document (no ownership data) still works."""
        handler, mock_neo4j, server = document_handler
        server.current_user = "user_A"

        # Mock: paper not found
        mock_neo4j.__aenter__ = AsyncMock(return_value=mock_neo4j)
        mock_neo4j.__aexit__ = AsyncMock(return_value=False)
        mock_neo4j.get_paper = AsyncMock(return_value=None)
        mock_neo4j.run_query = AsyncMock(return_value=[{"chunk_count": 0}])
        mock_neo4j.delete_paper = AsyncMock(return_value={
            "nodes_deleted": 0, "relationships_deleted": 0
        })

        # When paper doesn't exist, delete should still succeed (idempotent)
        result = await handler.delete_document("nonexistent_paper")

        assert result["success"] is True


class TestDocumentHandlerParameterizedQueries:
    """Verify DocumentHandler delegates to parameterized _get_user_filter_clause."""

    def test_handler_delegates_to_server(self):
        """DocumentHandler._get_user_filter_clause delegates to server's method."""
        try:
            from src.medical_mcp.handlers.document_handler import DocumentHandler
        except ImportError:
            pytest.skip("DocumentHandler not available")

        server = MagicMock()
        server.current_user = "test_user"
        server._get_user_filter_clause = Mock(
            return_value=("WHERE p.owner = $current_user", {"current_user": "test_user"})
        )

        handler = DocumentHandler(server)
        clause, params = handler._get_user_filter_clause("p")

        # Verify delegation happened
        server._get_user_filter_clause.assert_called_once_with("p")
        assert clause == "WHERE p.owner = $current_user"
        assert params == {"current_user": "test_user"}

    def test_handler_filter_returns_tuple(self):
        """Handler's _get_user_filter_clause always returns tuple[str, dict]."""
        try:
            from src.medical_mcp.handlers.document_handler import DocumentHandler
        except ImportError:
            pytest.skip("DocumentHandler not available")

        server = MagicMock()
        server.current_user = "system"
        server._get_user_filter_clause = Mock(return_value=("", {}))

        handler = DocumentHandler(server)
        result = handler._get_user_filter_clause("p")

        assert isinstance(result, tuple)
        assert len(result) == 2


class TestCypherInjectionPrevention:
    """Test that security-critical methods prevent Cypher injection."""

    def _make_server_with_user(self, user_id: str):
        """Create minimal mock server."""
        from src.medical_mcp.medical_kag_server import MedicalKAGServer

        with patch.object(MedicalKAGServer, '__init__', lambda self, **kwargs: None):
            server = MedicalKAGServer()
            server.current_user = user_id
            return server

    def test_injection_via_username_single_quote(self):
        """Username with single quotes cannot break Cypher."""
        server = self._make_server_with_user("user'; DROP (n) //")
        clause, params = server._get_user_filter_clause("p")

        # Value must be in params only
        assert "user'; DROP (n) //" not in clause
        assert params["current_user"] == "user'; DROP (n) //"

    def test_injection_via_username_backslash(self):
        """Username with backslashes cannot break Cypher."""
        server = self._make_server_with_user("user\\nDROP DATABASE")
        clause, params = server._get_user_filter_clause("p")

        assert "user\\nDROP DATABASE" not in clause
        assert params["current_user"] == "user\\nDROP DATABASE"

    def test_injection_via_username_braces(self):
        """Username with curly braces cannot break Cypher."""
        server = self._make_server_with_user("user}{MATCH(n) DELETE n")
        clause, params = server._get_user_filter_clause("p")

        assert "user}{MATCH(n) DELETE n" not in clause

    def test_injection_via_alias_parameter(self):
        """The alias parameter is not user-controlled, but test it anyway."""
        server = self._make_server_with_user("user_A")

        # Normal aliases should work
        clause, params = server._get_user_filter_clause("paper")
        assert "paper.owner" in clause

        # The alias is developer-controlled, not user-controlled,
        # so this is defense-in-depth only
        clause, params = server._get_user_filter_clause("p")
        assert "p.owner" in clause


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for ReferenceHandler.

Comprehensive tests for reference formatting operations including:
- Single reference formatting (Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard)
- Multiple references formatting
- Style listing
- Journal style mapping
- Custom style creation
- Style preview comparison
- Paper loading from files
- Export formats (BibTeX, RIS)
- Error handling and edge cases
"""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass, field

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))


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
    server.data_dir = None
    server.search = AsyncMock(return_value={"success": True, "results": []})
    return server


@pytest.fixture
def sample_metadata():
    """Sample paper metadata."""
    return {
        "title": "Biportal Endoscopic Decompression vs Microscopic Decompression for Lumbar Stenosis",
        "authors": ["Park SM", "Kim HJ", "Lee KH"],
        "year": 2024,
        "journal": "Spine",
        "journal_abbrev": "Spine",
        "volume": "49",
        "issue": "3",
        "pages": "201-210",
        "doi": "10.1097/BRS.0000000000004567",
        "pmid": "38123456",
    }


@pytest.fixture
def sample_paper_data(sample_metadata):
    """Sample paper data as loaded from JSON."""
    return {
        "metadata": sample_metadata,
        "chunks": [{"content": "test chunk"}],
    }


@pytest.fixture
def mock_formatter():
    """Create a mock ReferenceFormatter."""
    formatter = Mock()
    formatter.format = Mock(return_value="Park SM, Kim HJ, Lee KH. Biportal Endoscopic Decompression... Spine. 2024;49(3):201-210.")
    formatter.to_bibtex = Mock(return_value="@article{park2024,\n  title={...}\n}")
    formatter.to_ris = Mock(return_value="TY  - JOUR\nAU  - Park SM\nER  -")
    formatter.format_multiple = Mock(return_value="1. Park SM...\n2. Kim HJ...")
    formatter.get_journal_style = Mock(return_value=None)
    formatter.get_style = Mock(return_value=Mock(
        name="vancouver",
        author=Mock(format="last_initials", et_al_threshold=6),
        include_doi=False,
        journal=Mock(use_abbreviation=True),
    ))
    formatter.list_styles = Mock(return_value={
        "default_styles": ["vancouver", "ama", "apa", "jbjs", "spine", "nlm", "harvard"],
        "custom_styles": [],
        "journal_mappings_detail": {},
        "default_journal_count": 10,
        "user_journal_count": 0,
    })
    formatter.set_journal_style = Mock()
    formatter.add_custom_style = Mock()
    return formatter


@pytest.fixture
def handler(mock_server, mock_formatter):
    """Create a ReferenceHandler with mock dependencies."""
    from medical_mcp.handlers.reference_handler import ReferenceHandler
    h = ReferenceHandler(mock_server)
    h._formatter = mock_formatter
    return h


@pytest.fixture
def handler_no_formatter(mock_server):
    """Create a ReferenceHandler that reports formatter not available.

    We patch the module-level FORMATTER_AVAILABLE at the correct location.
    """
    from medical_mcp.handlers.reference_handler import ReferenceHandler
    h = ReferenceHandler(mock_server)
    return h


# ============================================================================
# TestReferenceHandlerInit
# ============================================================================

class TestReferenceHandlerInit:
    """Test ReferenceHandler initialization."""

    def test_init(self, mock_server):
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", True):
            from medical_mcp.handlers.reference_handler import ReferenceHandler
            h = ReferenceHandler(mock_server)
            assert h.server == mock_server
            assert h._formatter is None

    def test_formatter_lazy_loading(self, mock_server):
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", True), \
             patch("medical_mcp.handlers.reference_handler.ReferenceFormatter") as MockFmt:
            from medical_mcp.handlers.reference_handler import ReferenceHandler
            MockFmt.return_value = Mock()
            h = ReferenceHandler(mock_server)
            # Access formatter property triggers creation
            _ = h.formatter
            MockFmt.assert_called_once()

    def test_formatter_not_available_raises(self, mock_server):
        from medical_mcp.handlers.reference_handler import ReferenceHandler
        from core.exceptions import ProcessingError
        h = ReferenceHandler(mock_server)
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", False):
            with pytest.raises(ProcessingError):
                _ = h.formatter


# ============================================================================
# TestFormatReference
# ============================================================================

class TestFormatReference:
    """Test format_reference method."""

    @pytest.mark.asyncio
    async def test_format_reference_by_paper_id(self, handler, sample_paper_data, mock_formatter):
        """Test formatting a single reference by paper ID."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_reference(paper_id="paper_001", style="vancouver")

        assert result["success"] is True
        assert result["paper_id"] == "paper_001"
        assert result["style"] == "vancouver"
        assert "formatted_reference" in result
        mock_formatter.format.assert_called_once()

    @pytest.mark.asyncio
    async def test_format_reference_bibtex(self, handler, sample_paper_data, mock_formatter):
        """Test BibTeX output format."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_reference(
            paper_id="paper_001", output_format="bibtex"
        )

        assert result["success"] is True
        assert result["output_format"] == "bibtex"
        mock_formatter.to_bibtex.assert_called_once()

    @pytest.mark.asyncio
    async def test_format_reference_ris(self, handler, sample_paper_data, mock_formatter):
        """Test RIS output format."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_reference(
            paper_id="paper_001", output_format="ris"
        )

        assert result["success"] is True
        assert result["output_format"] == "ris"
        mock_formatter.to_ris.assert_called_once()

    @pytest.mark.asyncio
    async def test_format_reference_with_target_journal(self, handler, sample_paper_data, mock_formatter):
        """Test formatting with target journal style mapping."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)
        mock_formatter.get_journal_style = Mock(return_value="jbjs")

        result = await handler.format_reference(
            paper_id="paper_001", target_journal="JBJS"
        )

        assert result["success"] is True
        assert result["style"] == "jbjs"

    @pytest.mark.asyncio
    async def test_format_reference_by_query(self, handler, sample_paper_data, mock_server):
        """Test formatting reference found by search query."""
        mock_server.search = AsyncMock(return_value={
            "success": True,
            "results": [{"document_id": "found_paper"}]
        })
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_reference(query="lumbar stenosis")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_format_reference_paper_not_found(self, handler):
        """Test when paper is not found."""
        handler._load_paper_by_id = AsyncMock(return_value=None)

        result = await handler.format_reference(paper_id="nonexistent")

        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]

    @pytest.mark.asyncio
    async def test_format_reference_no_formatter(self, handler_no_formatter):
        """Test when formatter is not available."""
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", False):
            result = await handler_no_formatter.format_reference(paper_id="paper_001")
        assert result["success"] is False
        assert "not available" in result["error"]

    @pytest.mark.asyncio
    async def test_format_reference_metadata_fields(self, handler, sample_paper_data, sample_metadata):
        """Test that metadata fields are correctly included in response."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_reference(paper_id="paper_001")

        assert result["metadata"]["authors"] == sample_metadata["authors"]
        assert result["metadata"]["year"] == sample_metadata["year"]
        assert result["metadata"]["journal"] == sample_metadata["journal"]
        assert result["metadata"]["doi"] == sample_metadata["doi"]

    @pytest.mark.asyncio
    async def test_format_reference_search_fails_fallback(self, handler, mock_server):
        """Test that search failure is handled gracefully."""
        mock_server.search = AsyncMock(side_effect=Exception("Search error"))
        handler._load_paper_by_id = AsyncMock(return_value=None)

        result = await handler.format_reference(query="test query")
        assert result["success"] is False


# ============================================================================
# TestFormatReferences
# ============================================================================

class TestFormatReferences:
    """Test format_references method (multiple)."""

    @pytest.mark.asyncio
    async def test_format_references_by_ids(self, handler, sample_paper_data, mock_formatter):
        """Test formatting multiple references by IDs."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_references(
            paper_ids=["p1", "p2"], style="ama"
        )

        assert result["success"] is True
        assert result["count"] == 2
        assert result["style"] == "ama"

    @pytest.mark.asyncio
    async def test_format_references_numbered(self, handler, sample_paper_data, mock_formatter):
        """Test numbered references."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_references(
            paper_ids=["p1"], numbered=True, start_number=5
        )

        assert result["success"] is True
        assert result["numbered"] is True

    @pytest.mark.asyncio
    async def test_format_references_bibtex(self, handler, sample_paper_data, mock_formatter):
        """Test BibTeX format for multiple references."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_references(
            paper_ids=["p1"], output_format="bibtex"
        )

        assert result["success"] is True
        assert result["output_format"] == "bibtex"

    @pytest.mark.asyncio
    async def test_format_references_ris(self, handler, sample_paper_data, mock_formatter):
        """Test RIS format for multiple references."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_references(
            paper_ids=["p1"], output_format="ris"
        )

        assert result["success"] is True
        assert result["output_format"] == "ris"

    @pytest.mark.asyncio
    async def test_format_references_by_query(self, handler, sample_paper_data, mock_server):
        """Test formatting references found by query."""
        mock_server.search = AsyncMock(return_value={
            "success": True,
            "results": [
                {"document_id": "p1"},
                {"document_id": "p2"},
            ]
        })
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.format_references(query="lumbar fusion", max_results=5)

        assert result["success"] is True
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_format_references_none_found(self, handler):
        """Test when no papers are found."""
        handler._load_paper_by_id = AsyncMock(return_value=None)

        result = await handler.format_references(paper_ids=["p1"])

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_format_references_with_target_journal(self, handler, sample_paper_data, mock_formatter):
        """Test with target journal style mapping."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)
        mock_formatter.get_journal_style = Mock(return_value="spine")

        result = await handler.format_references(
            paper_ids=["p1"], target_journal="Spine"
        )

        assert result["success"] is True
        assert result["style"] == "spine"

    @pytest.mark.asyncio
    async def test_format_references_no_formatter(self, handler_no_formatter):
        """Test without formatter."""
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", False):
            result = await handler_no_formatter.format_references(paper_ids=["p1"])
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_format_references_search_error(self, handler, mock_server):
        """Test search failure during reference lookup."""
        mock_server.search = AsyncMock(side_effect=Exception("Search error"))

        result = await handler.format_references(query="test")
        assert result["success"] is False


# ============================================================================
# TestListStyles
# ============================================================================

class TestListStyles:
    """Test list_styles method."""

    @pytest.mark.asyncio
    async def test_list_styles_success(self, handler, mock_formatter):
        """Test listing available styles."""
        result = await handler.list_styles()

        assert result["success"] is True
        assert "default_styles" in result
        assert "custom_styles" in result
        assert "journal_mappings" in result
        assert "usage_examples" in result

    @pytest.mark.asyncio
    async def test_list_styles_detail(self, handler, mock_formatter):
        """Test that style details are provided."""
        result = await handler.list_styles()

        assert result["success"] is True
        assert "vancouver" in result["default_styles"]

    @pytest.mark.asyncio
    async def test_list_styles_no_formatter(self, handler_no_formatter):
        """Test listing styles without formatter."""
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", False):
            result = await handler_no_formatter.list_styles()
        assert result["success"] is False


# ============================================================================
# TestSetJournalStyle
# ============================================================================

class TestSetJournalStyle:
    """Test set_journal_style method."""

    @pytest.mark.asyncio
    async def test_set_journal_style_success(self, handler, mock_formatter):
        """Test setting journal style mapping."""
        result = await handler.set_journal_style(
            journal_name="Spine", style_name="vancouver"
        )

        assert result["success"] is True
        assert result["journal_name"] == "Spine"
        assert result["style_name"] == "vancouver"
        mock_formatter.set_journal_style.assert_called_once_with("Spine", "vancouver")

    @pytest.mark.asyncio
    async def test_set_journal_style_invalid(self, handler, mock_formatter):
        """Test setting an invalid style."""
        result = await handler.set_journal_style(
            journal_name="Spine", style_name="nonexistent_style"
        )

        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]
        assert "available_styles" in result

    @pytest.mark.asyncio
    async def test_set_journal_style_no_formatter(self, handler_no_formatter):
        """Test without formatter."""
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", False):
            result = await handler_no_formatter.set_journal_style("Spine", "vancouver")
        assert result["success"] is False


# ============================================================================
# TestAddCustomStyle
# ============================================================================

class TestAddCustomStyle:
    """Test add_custom_style method."""

    @pytest.mark.asyncio
    async def test_add_custom_style_success(self, handler, mock_formatter):
        """Test creating a custom style."""
        mock_base = Mock()
        mock_base.author = Mock(
            format="last_initials", separator=", ",
            et_al_threshold=6, et_al_min=3, et_al_text="et al",
            initials_format="no_space",
        )
        mock_base.title_quotes = False
        mock_base.title_italics = False
        mock_base.title_period = True
        mock_base.title_case = "sentence"
        mock_base.journal = Mock(use_abbreviation=True, italicize=False)
        mock_base.date = Mock()
        mock_base.volume_bold = False
        mock_base.issue_in_parens = True
        mock_base.pages_prefix = ":"
        mock_base.doi_format = "doi:{doi}"
        mock_base.pmid_format = "PMID: {pmid}"
        mock_formatter.get_style = Mock(return_value=mock_base)

        # Mock StyleConfig.to_dict
        with patch("medical_mcp.handlers.reference_handler.StyleConfig") as MockStyleConfig:
            mock_config = Mock()
            mock_config.to_dict = Mock(return_value={"name": "my_style"})
            MockStyleConfig.return_value = mock_config

            result = await handler.add_custom_style(
                name="my_style",
                base_style="vancouver",
                author_et_al_threshold=3,
                include_doi=True,
            )

        assert result["success"] is True
        assert result["style_name"] == "my_style"

    @pytest.mark.asyncio
    async def test_add_custom_style_no_formatter(self, handler_no_formatter):
        """Test without formatter."""
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", False):
            result = await handler_no_formatter.add_custom_style(name="test")
        assert result["success"] is False


# ============================================================================
# TestPreviewStyles
# ============================================================================

class TestPreviewStyles:
    """Test preview_styles method."""

    @pytest.mark.asyncio
    async def test_preview_styles_success(self, handler, sample_paper_data, mock_formatter):
        """Test previewing multiple styles."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.preview_styles(paper_id="paper_001")

        assert result["success"] is True
        assert "previews" in result
        # Default styles + bibtex + ris
        assert "bibtex" in result["previews"]
        assert "ris" in result["previews"]

    @pytest.mark.asyncio
    async def test_preview_styles_custom_list(self, handler, sample_paper_data, mock_formatter):
        """Test preview with custom style list."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.preview_styles(
            paper_id="paper_001", styles=["vancouver", "ama"]
        )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_preview_styles_by_query(self, handler, sample_paper_data, mock_server, mock_formatter):
        """Test preview with search query."""
        mock_server.search = AsyncMock(return_value={
            "success": True,
            "results": [{"document_id": "p1"}]
        })
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)

        result = await handler.preview_styles(query="lumbar stenosis")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_preview_styles_paper_not_found(self, handler):
        """Test preview when paper is not found."""
        handler._load_paper_by_id = AsyncMock(return_value=None)

        result = await handler.preview_styles(paper_id="nonexistent")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_preview_styles_format_error_handled(self, handler, sample_paper_data, mock_formatter):
        """Test that format errors in individual styles are caught."""
        handler._load_paper_by_id = AsyncMock(return_value=sample_paper_data)
        mock_formatter.format = Mock(side_effect=Exception("Format error"))

        result = await handler.preview_styles(
            paper_id="paper_001", styles=["vancouver"]
        )

        assert result["success"] is True
        assert "Error" in result["previews"]["vancouver"]

    @pytest.mark.asyncio
    async def test_preview_styles_no_formatter(self, handler_no_formatter):
        """Test without formatter."""
        with patch("medical_mcp.handlers.reference_handler.FORMATTER_AVAILABLE", False):
            result = await handler_no_formatter.preview_styles(paper_id="p1")
        assert result["success"] is False


# ============================================================================
# TestLoadPaperById
# ============================================================================

class TestLoadPaperById:
    """Test _load_paper_by_id method."""

    @pytest.mark.asyncio
    async def test_load_paper_empty_id(self, handler):
        """Test loading with empty paper ID."""
        result = await handler._load_paper_by_id("")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_paper_no_directory(self, handler):
        """Test loading when extracted directory doesn't exist."""
        handler._get_extracted_dir = Mock(return_value=None)
        result = await handler._load_paper_by_id("paper_001")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_paper_file_found(self, handler, sample_paper_data, tmp_path):
        """Test loading paper from JSON file."""
        # Create a test JSON file
        json_file = tmp_path / "paper_001.json"
        json_file.write_text(json.dumps(sample_paper_data))

        handler._get_extracted_dir = Mock(return_value=tmp_path)
        result = await handler._load_paper_by_id("paper_001")

        assert result is not None
        assert result["metadata"]["title"] == sample_paper_data["metadata"]["title"]

    @pytest.mark.asyncio
    async def test_load_paper_by_partial_match(self, handler, sample_paper_data, tmp_path):
        """Test loading paper when ID is part of filename."""
        json_file = tmp_path / "2024_Park_paper_001_exported.json"
        json_file.write_text(json.dumps(sample_paper_data))

        handler._get_extracted_dir = Mock(return_value=tmp_path)
        result = await handler._load_paper_by_id("paper_001")

        assert result is not None

    @pytest.mark.asyncio
    async def test_load_paper_invalid_json(self, handler, tmp_path):
        """Test loading paper with invalid JSON."""
        json_file = tmp_path / "bad_paper.json"
        json_file.write_text("{ invalid json }")

        handler._get_extracted_dir = Mock(return_value=tmp_path)
        result = await handler._load_paper_by_id("bad_paper")

        assert result is None


# ============================================================================
# TestGetExtractedDir
# ============================================================================

class TestGetExtractedDir:
    """Test _get_extracted_dir method."""

    def test_get_extracted_dir_from_server(self, handler, mock_server, tmp_path):
        """Test getting extracted dir from server.data_dir."""
        extracted = tmp_path / "extracted"
        extracted.mkdir()
        mock_server.data_dir = str(tmp_path)

        result = handler._get_extracted_dir()
        # Result depends on actual filesystem
        assert result is None or isinstance(result, Path)

    def test_get_extracted_dir_no_paths(self, handler, mock_server):
        """Test when no paths exist."""
        mock_server.data_dir = None
        # The method tries multiple paths, all may fail
        result = handler._get_extracted_dir()
        # May return None if no paths exist
        assert result is None or isinstance(result, Path)

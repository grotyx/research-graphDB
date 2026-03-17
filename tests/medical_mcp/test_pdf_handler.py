"""Tests for PDFHandler.

This module tests PDF processing operations including:
- PDF file upload and validation
- Text extraction and metadata extraction
- Text analysis workflow
- Analyzed paper storage
- PDF prompt preparation
- Error handling and edge cases
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from medical_mcp.handlers.pdf_handler import PDFHandler
from core.exceptions import Neo4jError, ValidationError


@pytest.fixture
def mock_server(tmp_path):
    """Create a mock MedicalKAGServer instance."""
    server = Mock()
    # Use tmp_path to ensure path is within allowed directories
    server.project_root = tmp_path
    server.neo4j_client = Mock()
    server.neo4j_client._driver = Mock()
    server.relationship_builder = Mock()
    server.vision_processor = None
    server.current_user = "test_user"
    server.pubmed_enricher = None

    # Mock async methods
    server.analyze_text = AsyncMock(return_value={"success": True})
    server._process_with_vision = AsyncMock(return_value={"success": True})
    server._process_with_legacy_pipeline = AsyncMock(return_value={"success": True})
    server._delete_existing_chunks = AsyncMock()

    return server


@pytest.fixture
def pdf_handler(mock_server):
    """Create a PDFHandler instance."""
    return PDFHandler(mock_server)


@pytest.fixture
def tmp_pdf_file(tmp_path):
    """Create a temporary PDF file in data/ subdirectory."""
    # Create data subdirectory to match allowed directories
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    pdf_file = data_dir / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4\nSample PDF content")
    return pdf_file


class TestPDFHandlerInit:
    """Test PDFHandler initialization."""

    def test_init(self, mock_server):
        """Test basic initialization."""
        handler = PDFHandler(mock_server)
        assert handler.server == mock_server


class TestAddPDF:
    """Test add_pdf method."""

    @pytest.mark.asyncio
    async def test_add_pdf_file_not_found(self, pdf_handler):
        """Test handling of non-existent file."""
        result = await pdf_handler.add_pdf("/nonexistent/file.pdf")
        assert result["success"] is False
        # Either path traversal blocked or file not found
        assert ("파일 없음" in result["error"]) or ("접근 불가" in result["error"])

    @pytest.mark.asyncio
    async def test_add_pdf_not_pdf_file(self, pdf_handler, tmp_path):
        """Test rejection of non-PDF file."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        txt_file = data_dir / "test.txt"
        txt_file.write_text("Not a PDF")

        result = await pdf_handler.add_pdf(str(txt_file))
        assert result["success"] is False
        assert "PDF 파일이 아닙니다" in result["error"]

    @pytest.mark.asyncio
    async def test_add_pdf_path_traversal_blocked(self, pdf_handler):
        """Test path traversal protection."""
        # Try to access file outside allowed directories
        result = await pdf_handler.add_pdf("/etc/passwd")
        assert result["success"] is False
        assert "접근 불가" in result["error"] or "파일 없음" in result["error"]

    @pytest.mark.asyncio
    async def test_add_pdf_with_vision_processor(self, pdf_handler, tmp_pdf_file, mock_server):
        """Test PDF processing with vision processor."""
        mock_server.vision_processor = Mock()
        mock_server._process_with_vision = AsyncMock(
            return_value={"success": True, "paper_id": "test_paper"}
        )

        result = await pdf_handler.add_pdf(str(tmp_pdf_file), use_vision=True)
        assert result["success"] is True
        mock_server._process_with_vision.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_pdf_legacy_pipeline(self, pdf_handler, tmp_pdf_file, mock_server):
        """Test PDF processing with legacy pipeline."""
        mock_server.vision_processor = None
        mock_server._process_with_legacy_pipeline = AsyncMock(
            return_value={"success": True, "paper_id": "test_paper"}
        )

        result = await pdf_handler.add_pdf(str(tmp_pdf_file), use_vision=True)
        assert result["success"] is True
        mock_server._process_with_legacy_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_pdf_with_metadata(self, pdf_handler, tmp_pdf_file, mock_server):
        """Test PDF processing with additional metadata."""
        mock_server.vision_processor = Mock()
        mock_server._process_with_vision = AsyncMock(
            return_value={"success": True}
        )

        metadata = {"title": "Test Paper", "year": 2024}
        result = await pdf_handler.add_pdf(str(tmp_pdf_file), metadata=metadata)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_add_pdf_processing_error(self, pdf_handler, tmp_pdf_file, mock_server):
        """Test error handling during PDF processing."""
        mock_server.vision_processor = Mock()
        mock_server._process_with_vision = AsyncMock(
            side_effect=Exception("Processing failed")
        )

        result = await pdf_handler.add_pdf(str(tmp_pdf_file))
        assert result["success"] is False
        assert "Processing failed" in result["error"]


class TestAnalyzeText:
    """Test analyze_text method."""

    @pytest.mark.asyncio
    async def test_analyze_text_success(self, pdf_handler, mock_server):
        """Test successful text analysis."""
        mock_server.analyze_text = AsyncMock(
            return_value={
                "success": True,
                "paper_id": "test_123",
                "chunks_created": 15
            }
        )

        text = "This is a medical paper about spine surgery. " * 50
        result = await pdf_handler.analyze_text(
            text=text,
            title="Test Paper",
            pmid="12345"
        )

        assert result["success"] is True
        assert "paper_id" in result
        mock_server.analyze_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_text_with_metadata(self, pdf_handler, mock_server):
        """Test text analysis with metadata."""
        mock_server.analyze_text = AsyncMock(
            return_value={"success": True}
        )

        metadata = {
            "year": 2024,
            "journal": "Spine",
            "authors": ["Kim J", "Park S"],
            "doi": "10.1234/test"
        }

        result = await pdf_handler.analyze_text(
            text="Sample text " * 100,
            title="Test",
            metadata=metadata
        )

        assert result["success"] is True


class TestExtractPDFMetadata:
    """Test _extract_pdf_metadata method."""

    def test_extract_metadata_fallback(self, pdf_handler, tmp_path):
        """Test metadata extraction fallback to filename."""
        pdf_file = tmp_path / "test_paper.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch('fitz.open') as mock_fitz:
            mock_doc = Mock()
            mock_doc.metadata = {}
            mock_fitz.return_value = mock_doc

            metadata = pdf_handler._extract_pdf_metadata(pdf_file, "")
            assert metadata["title"] == "test_paper"

    def test_extract_metadata_from_pdf_metadata(self, pdf_handler, tmp_path):
        """Test extraction from PDF embedded metadata."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch('fitz.open') as mock_fitz:
            mock_doc = Mock()
            mock_doc.metadata = {
                "title": "Test Paper Title",
                "author": "Kim J, Park S",
                "creationDate": "D:20230101000000"
            }
            mock_fitz.return_value = mock_doc

            metadata = pdf_handler._extract_pdf_metadata(pdf_file, "")
            assert metadata["title"] == "Test Paper Title"
            assert "Kim J" in metadata["authors"]
            assert metadata["year"] == 2023

    def test_extract_metadata_year_from_text(self, pdf_handler, tmp_path):
        """Test year extraction from text content."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        text = "Published: 2024\nThis is a medical paper..."

        with patch('fitz.open') as mock_fitz:
            mock_doc = Mock()
            mock_doc.metadata = {}
            mock_fitz.return_value = mock_doc

            metadata = pdf_handler._extract_pdf_metadata(pdf_file, text)
            assert metadata["year"] == 2024


class TestExtractPDFText:
    """Test _extract_pdf_text method."""

    def test_extract_text_success(self, pdf_handler, tmp_path):
        """Test successful text extraction."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch('fitz.open') as mock_fitz:
            mock_doc = Mock()
            mock_page = Mock()
            mock_page.get_text.return_value = "Page content"
            mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
            mock_fitz.return_value = mock_doc

            text = pdf_handler._extract_pdf_text(pdf_file)
            assert "Page content" in text

    def test_extract_text_import_error(self, pdf_handler, tmp_path):
        """Test handling of missing PyMuPDF."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch('fitz.open', side_effect=ImportError):
            text = pdf_handler._extract_pdf_text(pdf_file)
            assert "[Placeholder text" in text
            assert "test.pdf" in text

    def test_extract_text_error(self, pdf_handler, tmp_path):
        """Test handling of extraction errors."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch('fitz.open', side_effect=Exception("Read error")):
            text = pdf_handler._extract_pdf_text(pdf_file)
            assert text == ""


class TestPreparePDFPrompt:
    """Test prepare_pdf_prompt method."""

    @pytest.mark.asyncio
    async def test_prepare_prompt_file_not_found(self, pdf_handler, tmp_path):
        """Test handling of non-existent file within allowed directory."""
        nonexistent = str(tmp_path / "nonexistent.pdf")
        result = await pdf_handler.prepare_pdf_prompt(nonexistent)
        assert result["success"] is False
        assert "파일 없음" in result["error"] or "경로" in result["error"]

    @pytest.mark.asyncio
    async def test_prepare_prompt_not_pdf(self, pdf_handler, tmp_path):
        """Test rejection of non-PDF file."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        txt_file = data_dir / "test.txt"
        txt_file.write_text("Not PDF")

        result = await pdf_handler.prepare_pdf_prompt(str(txt_file))
        assert result["success"] is False
        assert "PDF 파일이 아닙니다" in result["error"]

    @pytest.mark.asyncio
    async def test_prepare_prompt_success(self, pdf_handler, tmp_path):
        """Test successful prompt preparation."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        pdf_file = data_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch('fitz.open') as mock_fitz:
            mock_doc = Mock()
            mock_page = Mock()
            mock_page.get_text.return_value = "Sample medical paper text"
            mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
            mock_doc.__len__ = Mock(return_value=1)
            mock_fitz.return_value = mock_doc

            result = await pdf_handler.prepare_pdf_prompt(str(pdf_file))
            assert result["success"] is True
            assert "prompt" in result
            assert "pdf_text" in result
            assert "usage_guide" in result
            assert result["page_count"] == 1

    @pytest.mark.asyncio
    async def test_prepare_prompt_empty_pdf(self, pdf_handler, tmp_path):
        """Test handling of empty PDF."""
        data_dir = tmp_path / "data"
        data_dir.mkdir(exist_ok=True)
        pdf_file = data_dir / "empty.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        with patch('fitz.open') as mock_fitz:
            mock_doc = Mock()
            mock_page = Mock()
            mock_page.get_text.return_value = ""
            mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
            mock_doc.__len__ = Mock(return_value=1)
            mock_fitz.return_value = mock_doc

            result = await pdf_handler.prepare_pdf_prompt(str(pdf_file))
            assert result["success"] is False
            assert "텍스트를 추출할 수 없습니다" in result["error"]


class TestStoreAnalyzedPaper:
    """Test store_analyzed_paper method."""

    @pytest.mark.asyncio
    async def test_store_paper_missing_title(self, pdf_handler):
        """Test validation of required title field."""
        result = await pdf_handler.store_analyzed_paper(
            title="",
            abstract="Test abstract",
            year=2024,
            interventions=["TLIF"],
            outcomes=[{"name": "VAS", "p_value": 0.01}]
        )
        assert result["success"] is False
        assert "title은 필수" in result["error"]

    @pytest.mark.asyncio
    async def test_store_paper_short_abstract(self, pdf_handler):
        """Test validation of abstract length."""
        result = await pdf_handler.store_analyzed_paper(
            title="Test Paper",
            abstract="Short",
            year=2024,
            interventions=["TLIF"],
            outcomes=[{"name": "VAS"}]
        )
        assert result["success"] is False
        assert "50자 이상" in result["error"]

    @pytest.mark.asyncio
    async def test_store_paper_invalid_year(self, pdf_handler):
        """Test validation of year range."""
        result = await pdf_handler.store_analyzed_paper(
            title="Test Paper",
            abstract="Valid abstract with more than fifty characters here.",
            year=1800,
            interventions=["TLIF"],
            outcomes=[{"name": "VAS"}]
        )
        assert result["success"] is False
        assert "1900-2100" in result["error"]

    @pytest.mark.asyncio
    async def test_store_paper_missing_interventions(self, pdf_handler):
        """Test validation of required interventions."""
        result = await pdf_handler.store_analyzed_paper(
            title="Test Paper",
            abstract="Valid abstract with more than fifty characters here.",
            year=2024,
            interventions=[],
            outcomes=[{"name": "VAS"}]
        )
        assert result["success"] is False
        assert "interventions" in result["error"]

    @pytest.mark.asyncio
    async def test_store_paper_missing_outcomes(self, pdf_handler):
        """Test validation of required outcomes."""
        result = await pdf_handler.store_analyzed_paper(
            title="Test Paper",
            abstract="Valid abstract with more than fifty characters here.",
            year=2024,
            interventions=["TLIF"],
            outcomes=[]
        )
        assert result["success"] is False
        assert "outcomes" in result["error"]

    @pytest.mark.asyncio
    async def test_store_paper_no_neo4j(self, pdf_handler, mock_server):
        """Test error when Neo4j not connected."""
        mock_server.neo4j_client = None

        result = await pdf_handler.store_analyzed_paper(
            title="Test Paper",
            abstract="Valid abstract with more than fifty characters here.",
            year=2024,
            interventions=["TLIF"],
            outcomes=[{"name": "VAS"}]
        )
        assert result["success"] is False
        assert "Neo4j not connected" in result["error"]

    @pytest.mark.asyncio
    async def test_store_paper_success(self, pdf_handler, mock_server):
        """Test successful paper storage."""
        # Mock RelationshipBuilder
        @dataclass
        class BuildResult:
            nodes_created: int = 10
            relationships_created: int = 15
            warnings: list = None

        mock_server.relationship_builder.build_from_paper = AsyncMock(
            return_value=BuildResult()
        )

        result = await pdf_handler.store_analyzed_paper(
            title="Test TLIF Study",
            abstract="This is a valid abstract with more than fifty characters about TLIF surgery.",
            year=2024,
            interventions=["TLIF"],
            outcomes=[{"name": "VAS", "p_value": 0.01}],
            pathologies=["Lumbar Stenosis"],
            anatomy_levels=["L4-L5"],
            authors=["Kim J", "Park S"],
            journal="Spine",
            doi="10.1234/test",
            pmid="12345",
            evidence_level="2b",
            study_design="retrospective-cohort",
            sample_size=100
        )

        assert result["success"] is True
        assert result["paper_id"] == "pubmed_12345"
        assert "stored_metadata" in result
        assert "neo4j_result" in result

    @pytest.mark.asyncio
    async def test_store_paper_with_chunks(self, pdf_handler, mock_server):
        """Test paper storage with chunks."""
        @dataclass
        class BuildResult:
            nodes_created: int = 10
            relationships_created: int = 15
            warnings: list = None

        mock_server.relationship_builder.build_from_paper = AsyncMock(
            return_value=BuildResult()
        )
        mock_server.neo4j_client.run_query = AsyncMock()

        with patch('core.embedding.OpenAIEmbeddingGenerator') as mock_emb:
            mock_emb_instance = Mock()
            mock_emb_instance.embed_batch.return_value = [[0.1] * 3072]
            mock_emb.return_value = mock_emb_instance

            chunks = [
                {
                    "content": "Test chunk content",
                    "tier": "tier1",
                    "section_type": "results"
                }
            ]

            result = await pdf_handler.store_analyzed_paper(
                title="Test Paper",
                abstract="Valid abstract with more than fifty characters here.",
                year=2024,
                interventions=["TLIF"],
                outcomes=[{"name": "VAS"}],
                chunks=chunks
            )

            assert result["success"] is True
            assert result["stats"]["chunks_created"] == 1

    @pytest.mark.asyncio
    async def test_store_paper_pubmed_enrichment(self, pdf_handler, mock_server):
        """Test PubMed metadata enrichment during storage."""
        @dataclass
        class BuildResult:
            nodes_created: int = 10
            relationships_created: int = 15
            warnings: list = None

        @dataclass
        class PubMedMetadata:
            pmid: str = "67890"
            doi: str = "10.5678/enriched"
            authors: list = None
            journal: str = "Journal of Spine"
            publication_types: list = None

        mock_enricher = Mock()
        mock_enricher.auto_enrich = AsyncMock(return_value=PubMedMetadata())
        mock_server.pubmed_enricher = mock_enricher

        mock_server.relationship_builder.build_from_paper = AsyncMock(
            return_value=BuildResult()
        )

        result = await pdf_handler.store_analyzed_paper(
            title="Test Paper",
            abstract="Valid abstract with more than fifty characters here.",
            year=2024,
            interventions=["TLIF"],
            outcomes=[{"name": "VAS"}],
            doi="10.1234/original"
        )

        assert result["success"] is True
        assert result["pubmed_enriched"] is True


class TestClassificationMethods:
    """Test section/citation/study classification methods."""

    def test_classify_sections_no_classifier(self, pdf_handler, mock_server):
        """Test section classification fallback."""
        delattr(mock_server, 'section_classifier') if hasattr(mock_server, 'section_classifier') else None

        result = pdf_handler._classify_sections("Sample text")
        assert len(result) == 1
        assert result[0]["section"] == "full_text"
        assert result[0]["tier"] == "tier1"

    def test_detect_citations_no_detector(self, pdf_handler, mock_server):
        """Test citation detection fallback."""
        delattr(mock_server, 'citation_detector') if hasattr(mock_server, 'citation_detector') else None

        result = pdf_handler._detect_citations("Sample text")
        assert len(result) == 1
        assert result[0]["source_type"] == "original"

    def test_classify_study_no_classifier(self, pdf_handler, mock_server):
        """Test study classification fallback."""
        delattr(mock_server, 'study_classifier') if hasattr(mock_server, 'study_classifier') else None

        result = pdf_handler._classify_study("Sample text")
        assert result is None

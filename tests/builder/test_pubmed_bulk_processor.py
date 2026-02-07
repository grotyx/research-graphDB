"""PubMed Bulk Processor Tests.

PubMedBulkProcessor 모듈의 대량 임포트 기능을 테스트합니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from dataclasses import asdict

# Import module
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.pubmed_bulk_processor import (
    PubMedBulkProcessor,
    PubMedImportResult,
    BulkImportSummary,
)
from builder.pubmed_enricher import BibliographicMetadata


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sample_bibliographic_metadata():
    """샘플 BibliographicMetadata."""
    return BibliographicMetadata(
        pmid="12345678",
        doi="10.1097/BRS.0000000000001234",
        title="Comparison of TLIF and PLIF for Lumbar Degenerative Disease",
        authors=["Kim JH", "Park SM", "Lee CK"],
        journal="Spine",
        year=2023,
        abstract="Background: This study compares outcomes of TLIF vs PLIF for lumbar degenerative disease. Methods: 100 patients were randomized. Results: TLIF showed better outcomes. Conclusion: TLIF is preferred.",
        mesh_terms=["Spinal Fusion", "Lumbar Vertebrae"],
        publication_types=["Randomized Controlled Trial"],
        confidence=0.95
    )


@pytest.fixture
def sample_pubmed_papers():
    """샘플 BibliographicMetadata 리스트."""
    return [
        BibliographicMetadata(
            pmid="11111111",
            title="Paper 1: Spine Fusion Outcomes",
            authors=["Author A"],
            journal="Spine J",
            year=2022,
            abstract="Abstract 1...",
            confidence=1.0
        ),
        BibliographicMetadata(
            pmid="22222222",
            title="Paper 2: Lumbar Decompression",
            authors=["Author B"],
            journal="J Neurosurg Spine",
            year=2021,
            abstract="Abstract 2...",
            confidence=0.9
        ),
        BibliographicMetadata(
            pmid="33333333",
            title="Paper 3: Minimally Invasive Surgery",
            authors=["Author C"],
            journal="Eur Spine J",
            year=2023,
            abstract="Abstract 3...",
            confidence=0.85
        ),
    ]


# ===========================================================================
# PubMedImportResult Tests
# ===========================================================================

class TestPubMedImportResult:
    """PubMedImportResult 데이터클래스 테스트."""

    def test_default_values(self):
        """기본값 테스트."""
        result = PubMedImportResult(
            paper_id="pubmed_12345678",
            pmid="12345678",
            title="Test Paper"
        )

        assert result.paper_id == "pubmed_12345678"
        assert result.pmid == "12345678"
        assert result.title == "Test Paper"
        assert result.neo4j_created is False
        assert result.chunks_created == 0
        assert result.source == "search"
        assert result.is_abstract_only is True
        assert result.skipped is False
        assert result.skip_reason == ""
        assert result.error == ""

    def test_with_all_fields(self):
        """모든 필드 설정 테스트."""
        result = PubMedImportResult(
            paper_id="pubmed_12345678",
            pmid="12345678",
            title="Test Paper",
            neo4j_created=True,
            chunks_created=5,
            source="citation",
            is_abstract_only=True,
            skipped=False,
            error=""
        )

        assert result.neo4j_created is True
        assert result.chunks_created == 5
        assert result.source == "citation"

    def test_skipped_paper(self):
        """스킵된 논문 결과 테스트."""
        result = PubMedImportResult(
            paper_id="pubmed_12345678",
            pmid="12345678",
            title="Existing Paper",
            skipped=True,
            skip_reason="Already exists"
        )

        assert result.skipped is True
        assert result.skip_reason == "Already exists"
        assert result.neo4j_created is False

    def test_error_result(self):
        """에러 결과 테스트."""
        result = PubMedImportResult(
            paper_id="pubmed_12345678",
            pmid="12345678",
            title="Failed Paper",
            error="Neo4j connection failed"
        )

        assert result.error == "Neo4j connection failed"
        assert result.neo4j_created is False


# ===========================================================================
# BulkImportSummary Tests
# ===========================================================================

class TestBulkImportSummary:
    """BulkImportSummary 데이터클래스 테스트."""

    def test_default_values(self):
        """기본값 테스트."""
        summary = BulkImportSummary()

        assert summary.total_papers == 0
        assert summary.imported == 0
        assert summary.skipped == 0
        assert summary.failed == 0
        assert summary.total_chunks == 0
        assert summary.results == []

    def test_to_dict(self):
        """to_dict 메서드 테스트."""
        result1 = PubMedImportResult(
            paper_id="pubmed_1",
            pmid="1",
            title="Paper 1",
            neo4j_created=True,
            chunks_created=3
        )
        result2 = PubMedImportResult(
            paper_id="pubmed_2",
            pmid="2",
            title="Paper 2",
            skipped=True,
            skip_reason="Already exists"
        )

        summary = BulkImportSummary(
            total_papers=2,
            imported=1,
            skipped=1,
            failed=0,
            total_chunks=3,
            results=[result1, result2]
        )

        d = summary.to_dict()

        assert d["total_papers"] == 2
        assert d["imported"] == 1
        assert d["skipped"] == 1
        assert d["failed"] == 0
        assert d["total_chunks"] == 3
        assert len(d["results"]) == 2

    def test_summary_with_failures(self):
        """실패 포함 요약 테스트."""
        results = [
            PubMedImportResult(
                paper_id="pubmed_1",
                pmid="1",
                title="Success",
                neo4j_created=True,
                chunks_created=3
            ),
            PubMedImportResult(
                paper_id="pubmed_2",
                pmid="2",
                title="Skipped",
                skipped=True,
                skip_reason="Duplicate"
            ),
            PubMedImportResult(
                paper_id="pubmed_3",
                pmid="3",
                title="Failed",
                error="Connection error"
            ),
        ]

        summary = BulkImportSummary(
            total_papers=3,
            imported=1,
            skipped=1,
            failed=1,
            total_chunks=3,
            results=results
        )

        assert summary.imported == 1
        assert summary.skipped == 1
        assert summary.failed == 1


# ===========================================================================
# PubMedBulkProcessor Unit Tests
# ===========================================================================

class TestPubMedBulkProcessorConstants:
    """PubMedBulkProcessor 상수 테스트."""

    def test_pubmed_paper_prefix(self):
        """PUBMED_PAPER_PREFIX 상수 테스트."""
        assert PubMedBulkProcessor.PUBMED_PAPER_PREFIX == "pubmed_"


class TestPubMedBulkProcessorStatic:
    """PubMedBulkProcessor 정적 메서드 테스트."""

    def test_generate_paper_id(self):
        """paper_id 생성 테스트."""
        # Static method test
        paper_id = f"{PubMedBulkProcessor.PUBMED_PAPER_PREFIX}12345678"
        assert paper_id == "pubmed_12345678"

    def test_paper_id_format_consistency(self):
        """paper_id 형식 일관성 테스트."""
        pmid1 = "12345678"
        pmid2 = "87654321"

        paper_id1 = f"{PubMedBulkProcessor.PUBMED_PAPER_PREFIX}{pmid1}"
        paper_id2 = f"{PubMedBulkProcessor.PUBMED_PAPER_PREFIX}{pmid2}"

        assert paper_id1.startswith("pubmed_")
        assert paper_id2.startswith("pubmed_")
        assert paper_id1 != paper_id2


# ===========================================================================
# BibliographicMetadata Tests
# ===========================================================================

class TestBibliographicMetadataIntegration:
    """BibliographicMetadata와의 통합 테스트."""

    def test_metadata_has_required_fields(self, sample_bibliographic_metadata):
        """필수 필드 존재 확인."""
        meta = sample_bibliographic_metadata

        assert meta.pmid is not None
        assert meta.title is not None
        assert meta.abstract is not None
        assert isinstance(meta.authors, list)

    def test_metadata_to_dict(self, sample_bibliographic_metadata):
        """to_dict 메서드 테스트."""
        meta = sample_bibliographic_metadata
        d = meta.to_dict()

        assert d["pmid"] == "12345678"
        assert d["title"] == "Comparison of TLIF and PLIF for Lumbar Degenerative Disease"
        assert "abstract" in d
        assert "mesh_terms" in d

    def test_metadata_confidence(self, sample_bibliographic_metadata):
        """confidence 필드 테스트."""
        meta = sample_bibliographic_metadata

        assert 0 <= meta.confidence <= 1.0
        assert meta.confidence == 0.95


# ===========================================================================
# Mock-based Integration Tests
# ===========================================================================

class TestPubMedBulkProcessorMocked:
    """Mocked PubMedBulkProcessor 테스트."""

    @pytest.fixture
    def mock_processor(self):
        """Mock 객체로 구성된 processor."""
        # Create mock dependencies
        mock_neo4j = AsyncMock()
        mock_vector_db = MagicMock()
        mock_pubmed_client = MagicMock()
        mock_pubmed_enricher = MagicMock()
        mock_embedding = MagicMock()

        # Create processor with mocked __init__
        with patch.object(PubMedBulkProcessor, '__init__', lambda self, *args, **kwargs: None):
            processor = PubMedBulkProcessor.__new__(PubMedBulkProcessor)
            processor.neo4j = mock_neo4j
            processor.vector_db = mock_vector_db
            processor.pubmed_client = mock_pubmed_client
            processor.pubmed_enricher = mock_pubmed_enricher
            processor.embedding_generator = mock_embedding

        return processor

    @pytest.mark.asyncio
    async def test_check_existing_paper_found(self, mock_processor):
        """기존 논문 확인 - 존재하는 경우."""
        mock_processor.neo4j.run_query = AsyncMock(
            return_value=[{"paper_id": "existing_paper_123"}]
        )

        result = await mock_processor._check_existing_paper("12345678")

        assert result == "existing_paper_123"

    @pytest.mark.asyncio
    async def test_check_existing_paper_not_found(self, mock_processor):
        """기존 논문 확인 - 존재하지 않는 경우."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[])

        result = await mock_processor._check_existing_paper("99999999")

        assert result is None

    @pytest.mark.asyncio
    async def test_import_papers_empty_list(self, mock_processor):
        """빈 리스트 임포트."""
        summary = await mock_processor.import_papers([])

        assert summary.total_papers == 0
        assert summary.imported == 0
        assert summary.results == []

    @pytest.mark.asyncio
    async def test_get_abstract_only_papers(self, mock_processor):
        """abstract-only 논문 조회."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[
            {"paper_id": "pubmed_111", "title": "Paper 1", "pmid": "111"},
            {"paper_id": "pubmed_222", "title": "Paper 2", "pmid": "222"},
        ])

        papers = await mock_processor.get_abstract_only_papers(limit=10)

        assert len(papers) == 2
        assert papers[0]["paper_id"] == "pubmed_111"

    @pytest.mark.asyncio
    async def test_get_abstract_only_papers_empty(self, mock_processor):
        """abstract-only 논문 없음."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[])

        papers = await mock_processor.get_abstract_only_papers()

        assert papers == []

    @pytest.mark.asyncio
    async def test_upgrade_with_pdf_paper_not_found(self, mock_processor):
        """업그레이드 - 논문 없음."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[])

        result = await mock_processor.upgrade_with_pdf("nonexistent_id", {})

        assert result.get("success") is False
        # Error message can be "not found" or "not a pubmed-only paper"
        error_msg = result.get("error", "").lower()
        assert "not found" in error_msg or "not a pubmed" in error_msg


# ===========================================================================
# Edge Cases
# ===========================================================================

class TestEdgeCases:
    """엣지 케이스 테스트."""

    def test_import_result_without_pmid(self):
        """PMID 없는 결과 생성."""
        result = PubMedImportResult(
            paper_id="unknown_paper",
            pmid="",
            title="Paper without PMID"
        )

        assert result.pmid == ""
        assert result.paper_id == "unknown_paper"

    def test_import_result_long_title(self):
        """긴 제목 처리."""
        long_title = "A" * 1000
        result = PubMedImportResult(
            paper_id="pubmed_123",
            pmid="123",
            title=long_title
        )

        assert len(result.title) == 1000

    def test_bulk_summary_empty_results(self):
        """빈 결과 요약."""
        summary = BulkImportSummary()
        d = summary.to_dict()

        assert d["total_papers"] == 0
        assert d["results"] == []

    def test_bibliographic_metadata_minimal(self):
        """최소 정보 BibliographicMetadata."""
        meta = BibliographicMetadata(
            title="Minimal Paper"
        )

        assert meta.title == "Minimal Paper"
        assert meta.pmid is None
        assert meta.abstract == ""
        assert meta.authors == []


# ===========================================================================
# Data Validation Tests
# ===========================================================================

class TestDataValidation:
    """데이터 유효성 검사 테스트."""

    def test_valid_pmid_format(self):
        """유효한 PMID 형식."""
        # PMID는 숫자로만 구성
        valid_pmids = ["12345678", "1", "99999999"]

        for pmid in valid_pmids:
            paper_id = f"pubmed_{pmid}"
            assert paper_id.startswith("pubmed_")
            assert pmid.isdigit()

    def test_bibliographic_metadata_year_range(self):
        """연도 범위 테스트."""
        meta = BibliographicMetadata(
            title="Test",
            year=2023
        )

        assert 1900 <= meta.year <= 2100

    def test_confidence_bounds(self, sample_bibliographic_metadata):
        """신뢰도 범위 테스트."""
        meta = sample_bibliographic_metadata

        assert 0.0 <= meta.confidence <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

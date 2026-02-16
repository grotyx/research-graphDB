"""PubMed Downloader Tests.

PubMedDownloader 모듈의 검색, 배치 조회, 중복 확인 기능을 테스트합니다.
D-009: pubmed_bulk_processor에서 분리된 download/API 모듈 테스트.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.pubmed_downloader import (
    PubMedDownloader,
    build_search_query,
    PUBMED_PAPER_PREFIX,
)
from builder.pubmed_enricher import BibliographicMetadata


# ===========================================================================
# build_search_query Tests
# ===========================================================================

class TestBuildSearchQuery:
    """build_search_query 함수 테스트."""

    def test_basic_query(self):
        """기본 쿼리."""
        result = build_search_query("lumbar fusion")
        assert result == "lumbar fusion"

    def test_query_with_year_range(self):
        """연도 범위 필터."""
        result = build_search_query("spine surgery", year_from=2020, year_to=2024)
        assert "2020:2024[PDAT]" in result
        assert "spine surgery" in result

    def test_query_with_year_from_only(self):
        """시작 연도만."""
        result = build_search_query("spine", year_from=2020)
        assert "2020:3000[PDAT]" in result

    def test_query_with_year_to_only(self):
        """종료 연도만."""
        result = build_search_query("spine", year_to=2024)
        assert "1900:2024[PDAT]" in result

    def test_query_with_publication_types(self):
        """출판 유형 필터."""
        result = build_search_query(
            "spine",
            publication_types=["Randomized Controlled Trial", "Meta-Analysis"],
        )
        assert '"Randomized Controlled Trial"[PT]' in result
        assert '"Meta-Analysis"[PT]' in result
        assert " OR " in result

    def test_query_with_all_filters(self):
        """모든 필터 조합."""
        result = build_search_query(
            "lumbar",
            year_from=2020,
            year_to=2024,
            publication_types=["RCT"],
        )
        assert "lumbar" in result
        assert "2020:2024[PDAT]" in result
        assert '"RCT"[PT]' in result
        parts = result.split(" AND ")
        assert len(parts) == 3


# ===========================================================================
# PubMedDownloader Tests
# ===========================================================================

class TestPubMedDownloader:
    """PubMedDownloader 테스트."""

    @pytest.fixture
    def mock_downloader(self):
        """Mock 객체로 구성된 downloader."""
        mock_pubmed_client = MagicMock()
        mock_enricher = MagicMock()
        mock_neo4j = AsyncMock()

        downloader = PubMedDownloader(
            pubmed_client=mock_pubmed_client,
            pubmed_enricher=mock_enricher,
            neo4j_client=mock_neo4j,
        )
        return downloader

    @pytest.mark.asyncio
    async def test_check_existing_paper_found(self, mock_downloader):
        """기존 논문 확인 - 존재하는 경우."""
        mock_downloader.neo4j.run_query = AsyncMock(
            return_value=[{"paper_id": "pubmed_12345678"}]
        )
        result = await mock_downloader.check_existing_paper("12345678")
        assert result == "pubmed_12345678"

    @pytest.mark.asyncio
    async def test_check_existing_paper_not_found(self, mock_downloader):
        """기존 논문 확인 - 존재하지 않는 경우."""
        mock_downloader.neo4j.run_query = AsyncMock(return_value=[])
        result = await mock_downloader.check_existing_paper("99999999")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_existing_paper_error(self, mock_downloader):
        """기존 논문 확인 - 에러."""
        mock_downloader.neo4j.run_query = AsyncMock(side_effect=Exception("DB error"))
        result = await mock_downloader.check_existing_paper("12345678")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_existing_papers_batch_found(self, mock_downloader):
        """배치 중복 확인 - 일부 존재."""
        mock_downloader.neo4j.run_query = AsyncMock(return_value=[
            {"pmid": "111", "paper_id": "pubmed_111"},
            {"pmid": "222", "paper_id": "pubmed_222"},
        ])
        result = await mock_downloader.check_existing_papers_batch(["111", "222", "333"])
        assert result == {"111": "pubmed_111", "222": "pubmed_222"}

    @pytest.mark.asyncio
    async def test_check_existing_papers_batch_empty(self, mock_downloader):
        """배치 중복 확인 - 빈 목록."""
        result = await mock_downloader.check_existing_papers_batch([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_check_existing_by_doi_found(self, mock_downloader):
        """DOI 중복 확인 - 존재."""
        mock_downloader.neo4j.run_query = AsyncMock(
            return_value=[{"paper_id": "pubmed_123"}]
        )
        result = await mock_downloader.check_existing_by_doi("10.1097/BRS.123")
        assert result == "pubmed_123"

    @pytest.mark.asyncio
    async def test_check_existing_by_doi_empty(self, mock_downloader):
        """DOI 중복 확인 - 빈 DOI."""
        result = await mock_downloader.check_existing_by_doi("")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_important_citations(self, mock_downloader):
        """important citations 가져오기."""
        mock_downloader.neo4j.run_query = AsyncMock(return_value=[
            {"citations": [{"title": "Paper A", "authors": ["Kim"]}]}
        ])
        result = await mock_downloader.get_important_citations("paper_123")
        assert len(result) == 1
        assert result[0]["title"] == "Paper A"

    @pytest.mark.asyncio
    async def test_get_important_citations_json_string(self, mock_downloader):
        """important citations 가져오기 - JSON string."""
        import json
        citations = [{"title": "Paper A"}]
        mock_downloader.neo4j.run_query = AsyncMock(return_value=[
            {"citations": json.dumps(citations)}
        ])
        result = await mock_downloader.get_important_citations("paper_123")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_important_citations_empty(self, mock_downloader):
        """important citations 없음."""
        mock_downloader.neo4j.run_query = AsyncMock(return_value=[{"citations": None}])
        result = await mock_downloader.get_important_citations("paper_123")
        assert result == []


# ===========================================================================
# Constants Tests
# ===========================================================================

class TestConstants:
    """상수 테스트."""

    def test_pubmed_paper_prefix(self):
        """PUBMED_PAPER_PREFIX 상수."""
        assert PUBMED_PAPER_PREFIX == "pubmed_"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

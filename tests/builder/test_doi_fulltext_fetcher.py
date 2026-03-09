"""Tests for DOI Fulltext Fetcher module.

Covers:
- DOI normalization
- Crossref API metadata fetching (mocked HTTP)
- Unpaywall API OA info fetching (mocked HTTP)
- PDF download
- Full fetch pipeline
- Batch fetching
- Metadata-only fetching
- Bibliographic search
- Error handling: network failures, 404, timeouts, invalid data
- Data class properties and serialization
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime

import httpx

from builder.doi_fulltext_fetcher import (
    DOIFulltextFetcher,
    DOIMetadata,
    DOIFullText,
    fetch_by_doi,
    get_doi_metadata,
)


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def fetcher(tmp_path):
    """Create a DOIFulltextFetcher with a temp download dir."""
    return DOIFulltextFetcher(
        email="test@example.com",
        timeout=10.0,
        download_dir=str(tmp_path / "pdfs"),
    )


@pytest.fixture
def fetcher_no_download():
    """Create a DOIFulltextFetcher without download dir."""
    return DOIFulltextFetcher(email="test@example.com")


@pytest.fixture
def sample_crossref_response():
    """Sample Crossref API response."""
    return {
        "message": {
            "title": ["Minimally Invasive Spine Surgery"],
            "author": [
                {"given": "John", "family": "Smith"},
                {"given": "Jane", "family": "Doe"},
            ],
            "container-title": ["Spine Journal"],
            "published": {"date-parts": [[2023, 6, 15]]},
            "volume": "48",
            "issue": "3",
            "page": "200-210",
            "abstract": "<jats:p>This is a test abstract.</jats:p>",
            "publisher": "Elsevier",
            "ISSN": ["1529-9430"],
            "subject": ["Orthopedics"],
            "references-count": 42,
            "is-referenced-by-count": 15,
            "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
            "DOI": "10.1016/j.spinee.2023.01.001",
        }
    }


@pytest.fixture
def sample_unpaywall_response():
    """Sample Unpaywall API response."""
    return {
        "is_oa": True,
        "oa_status": "gold",
        "best_oa_location": {
            "url_for_pdf": "https://example.com/paper.pdf",
            "host_type": "publisher",
            "url": "https://example.com/paper",
        },
    }


def _make_mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.content = b"%PDF-1.4 fake pdf content"
    return resp


# =====================================================================
# DOIMetadata / DOIFullText dataclass tests
# =====================================================================

class TestDOIMetadata:
    """Tests for DOIMetadata dataclass."""

    def test_default_values(self):
        meta = DOIMetadata(doi="10.1016/j.test.2023")
        assert meta.doi == "10.1016/j.test.2023"
        assert meta.title == ""
        assert meta.authors == []
        assert meta.is_open_access is False
        assert meta.pdf_url is None

    def test_to_dict(self):
        meta = DOIMetadata(
            doi="10.1016/j.test.2023",
            title="Test Paper",
            year=2023,
            is_open_access=True,
        )
        d = meta.to_dict()
        assert d["doi"] == "10.1016/j.test.2023"
        assert d["title"] == "Test Paper"
        assert d["year"] == 2023
        assert d["is_open_access"] is True
        assert "authors" in d
        assert "pdf_url" in d


class TestDOIFullText:
    """Tests for DOIFullText dataclass."""

    def test_has_full_text_with_text(self):
        result = DOIFullText(doi="10.1016/test", full_text="some text")
        assert result.has_full_text is True

    def test_has_full_text_with_pdf_path(self):
        result = DOIFullText(doi="10.1016/test", pdf_path="/tmp/test.pdf")
        assert result.has_full_text is True

    def test_has_full_text_empty(self):
        result = DOIFullText(doi="10.1016/test")
        assert result.has_full_text is False

    def test_has_metadata(self):
        result = DOIFullText(doi="10.1016/test", metadata=DOIMetadata(doi="10.1016/test"))
        assert result.has_metadata is True

    def test_has_no_metadata(self):
        result = DOIFullText(doi="10.1016/test")
        assert result.has_metadata is False

    def test_to_dict_long_text_truncated(self):
        long_text = "x" * 600
        result = DOIFullText(doi="10.1016/test", full_text=long_text, fetch_time=datetime(2023, 1, 1))
        d = result.to_dict()
        assert d["full_text"].endswith("...")
        assert d["full_text_length"] == 600

    def test_to_dict_short_text(self):
        result = DOIFullText(doi="10.1016/test", full_text="short", fetch_time=None)
        d = result.to_dict()
        assert d["full_text"] == "short"
        assert d["fetch_time"] is None

    def test_to_dict_with_metadata(self):
        meta = DOIMetadata(doi="10.1016/test", title="Title")
        result = DOIFullText(doi="10.1016/test", metadata=meta)
        d = result.to_dict()
        assert d["metadata"]["title"] == "Title"

    def test_to_dict_without_metadata(self):
        result = DOIFullText(doi="10.1016/test")
        d = result.to_dict()
        assert d["metadata"] is None


# =====================================================================
# DOI normalization tests
# =====================================================================

class TestNormalizeDOI:
    """Tests for DOI normalization."""

    def test_plain_doi(self, fetcher):
        assert fetcher.normalize_doi("10.1016/j.spinee.2023.01.001") == "10.1016/j.spinee.2023.01.001"

    def test_doi_url(self, fetcher):
        result = fetcher.normalize_doi("https://doi.org/10.1016/j.spinee.2023.01.001")
        assert result == "10.1016/j.spinee.2023.01.001"

    def test_doi_prefix(self, fetcher):
        result = fetcher.normalize_doi("doi:10.1016/j.spinee.2023.01.001")
        assert result == "10.1016/j.spinee.2023.01.001"

    def test_doi_with_spaces(self, fetcher):
        result = fetcher.normalize_doi("  10.1016/j.spinee.2023.01.001  ")
        assert result == "10.1016/j.spinee.2023.01.001"

    def test_doi_http_url(self, fetcher):
        result = fetcher.normalize_doi("http://dx.doi.org/10.1016/j.spinee.2023.01.001")
        assert result == "10.1016/j.spinee.2023.01.001"

    def test_doi_uppercase_prefix(self, fetcher):
        result = fetcher.normalize_doi("DOI:10.1016/j.spinee.2023.01.001")
        assert result == "10.1016/j.spinee.2023.01.001"


# =====================================================================
# Crossref fetch tests
# =====================================================================

class TestFetchCrossref:
    """Tests for Crossref API fetching."""

    @pytest.mark.asyncio
    async def test_fetch_crossref_success(self, fetcher, sample_crossref_response):
        mock_response = _make_mock_response(sample_crossref_response)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            result = await fetcher.fetch_crossref("10.1016/j.spinee.2023.01.001")

        assert result is not None
        assert result.title == "Minimally Invasive Spine Surgery"
        assert len(result.authors) == 2
        assert result.authors[0] == "Smith John"
        assert result.journal == "Spine Journal"
        assert result.year == 2023
        assert result.volume == "48"
        assert result.references_count == 42
        assert result.cited_by_count == 15
        # JATS tags should be stripped from abstract
        assert "<jats" not in result.abstract

    @pytest.mark.asyncio
    async def test_fetch_crossref_404(self, fetcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        exc = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_resp)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.fetch_crossref("10.9999/nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_crossref_network_error(self, fetcher):
        exc = httpx.ConnectError("Connection refused")
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.fetch_crossref("10.1016/j.test")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_crossref_timeout(self, fetcher):
        exc = httpx.TimeoutException("Timed out")
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.fetch_crossref("10.1016/j.test")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_crossref_server_error(self, fetcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        exc = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_resp)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.fetch_crossref("10.1016/j.test")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_crossref_empty_fields(self, fetcher):
        """Crossref response with minimal/empty fields."""
        resp_data = {"message": {}}
        mock_response = _make_mock_response(resp_data)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            result = await fetcher.fetch_crossref("10.1016/j.empty")
        assert result is not None
        assert result.title == ""
        assert result.authors == []
        assert result.year is None


# =====================================================================
# Unpaywall fetch tests
# =====================================================================

class TestFetchUnpaywall:
    """Tests for Unpaywall API fetching."""

    @pytest.mark.asyncio
    async def test_fetch_unpaywall_open_access(self, fetcher, sample_unpaywall_response):
        mock_response = _make_mock_response(sample_unpaywall_response)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            result = await fetcher.fetch_unpaywall("10.1016/j.spinee.2023.01.001")

        assert result["is_open_access"] is True
        assert result["oa_status"] == "gold"
        assert result["pdf_url"] == "https://example.com/paper.pdf"
        assert result["oa_location"] == "publisher"

    @pytest.mark.asyncio
    async def test_fetch_unpaywall_closed(self, fetcher):
        resp_data = {"is_oa": False, "oa_status": "closed", "best_oa_location": None}
        mock_response = _make_mock_response(resp_data)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            result = await fetcher.fetch_unpaywall("10.1016/j.closed")

        assert result["is_open_access"] is False
        assert result["pdf_url"] is None

    @pytest.mark.asyncio
    async def test_fetch_unpaywall_no_pdf_url_uses_landing_page(self, fetcher):
        resp_data = {
            "is_oa": True,
            "oa_status": "green",
            "best_oa_location": {
                "url_for_pdf": None,
                "host_type": "repository",
                "url": "https://repo.example.com/paper",
            },
        }
        mock_response = _make_mock_response(resp_data)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            result = await fetcher.fetch_unpaywall("10.1016/j.nopdf")

        assert result["pdf_url"] == "https://repo.example.com/paper"

    @pytest.mark.asyncio
    async def test_fetch_unpaywall_404(self, fetcher):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        exc = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_resp)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.fetch_unpaywall("10.9999/nonexistent")

        assert result["is_open_access"] is False
        assert result["pdf_url"] is None

    @pytest.mark.asyncio
    async def test_fetch_unpaywall_network_error(self, fetcher):
        exc = httpx.ConnectError("Connection refused")
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.fetch_unpaywall("10.1016/j.test")
        assert result["is_open_access"] is False


# =====================================================================
# PDF download tests
# =====================================================================

class TestDownloadPDF:
    """Tests for PDF download."""

    @pytest.mark.asyncio
    async def test_download_pdf_success(self, fetcher, tmp_path):
        mock_response = _make_mock_response({})
        mock_response.content = b"%PDF-1.4 test content"
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            result = await fetcher.download_pdf("https://example.com/paper.pdf", "10.1016/j.test")

        assert result is not None
        assert result.endswith(".pdf")

    @pytest.mark.asyncio
    async def test_download_pdf_no_download_dir(self, fetcher_no_download):
        result = await fetcher_no_download.download_pdf("https://example.com/paper.pdf", "10.1016/j.test")
        assert result is None

    @pytest.mark.asyncio
    async def test_download_pdf_network_error(self, fetcher):
        exc = httpx.ConnectError("Connection refused")
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.download_pdf("https://example.com/paper.pdf", "10.1016/j.test")
        assert result is None


# =====================================================================
# Full fetch pipeline tests
# =====================================================================

class TestFetch:
    """Tests for full fetch pipeline."""

    @pytest.mark.asyncio
    async def test_fetch_with_metadata(self, fetcher, sample_crossref_response, sample_unpaywall_response):
        mock_cr = _make_mock_response(sample_crossref_response)
        mock_up = _make_mock_response(sample_unpaywall_response)

        call_count = 0
        async def mock_request(client, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "crossref" in url:
                return mock_cr
            return mock_up

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            result = await fetcher.fetch("10.1016/j.spinee.2023.01.001")

        assert result.doi == "10.1016/j.spinee.2023.01.001"
        assert result.metadata is not None
        assert result.metadata.title == "Minimally Invasive Spine Surgery"
        assert result.metadata.is_open_access is True
        assert result.source == "crossref"

    @pytest.mark.asyncio
    async def test_fetch_normalizes_doi(self, fetcher):
        """fetch() should normalize DOI from URL form."""
        async def mock_request(client, method, url, **kwargs):
            return _make_mock_response({"message": {}})

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            result = await fetcher.fetch("https://doi.org/10.1016/j.test")

        assert result.doi == "10.1016/j.test"

    @pytest.mark.asyncio
    async def test_fetch_crossref_failure_still_returns_result(self, fetcher):
        """When Crossref fails, result should have empty metadata."""
        call_count = 0
        async def mock_request(client, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "crossref" in url:
                raise httpx.ConnectError("fail")
            return _make_mock_response({
                "is_oa": False, "oa_status": "closed", "best_oa_location": None
            })

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            result = await fetcher.fetch("10.1016/j.test")

        assert result.metadata is not None
        assert result.metadata.doi == "10.1016/j.test"


# =====================================================================
# Batch fetch tests
# =====================================================================

class TestFetchBatch:
    """Tests for batch fetching."""

    @pytest.mark.asyncio
    async def test_fetch_batch(self, fetcher):
        async def mock_request(client, method, url, **kwargs):
            return _make_mock_response({"message": {}, "is_oa": False, "oa_status": "closed", "best_oa_location": None})

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            with patch.object(fetcher, 'fetch', new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = DOIFullText(
                    doi="10.1016/test",
                    metadata=DOIMetadata(doi="10.1016/test", is_open_access=True),
                )
                results = await fetcher.fetch_batch(
                    ["10.1016/test1", "10.1016/test2"],
                    concurrency=2,
                    delay=0.0,
                )

        assert len(results) == 2


# =====================================================================
# Metadata-only fetch tests
# =====================================================================

class TestGetMetadataOnly:
    """Tests for metadata-only fetching."""

    @pytest.mark.asyncio
    async def test_get_metadata_only_success(self, fetcher, sample_crossref_response, sample_unpaywall_response):
        mock_cr = _make_mock_response(sample_crossref_response)
        mock_up = _make_mock_response(sample_unpaywall_response)

        async def mock_request(client, method, url, **kwargs):
            if "crossref" in url:
                return mock_cr
            return mock_up

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            result = await fetcher.get_metadata_only("10.1016/j.spinee.2023.01.001")

        assert result is not None
        assert result.title == "Minimally Invasive Spine Surgery"
        assert result.is_open_access is True

    @pytest.mark.asyncio
    async def test_get_metadata_only_crossref_fails(self, fetcher):
        async def mock_request(client, method, url, **kwargs):
            if "crossref" in url:
                raise httpx.ConnectError("fail")
            return _make_mock_response({
                "is_oa": False, "oa_status": "closed", "best_oa_location": None
            })

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            result = await fetcher.get_metadata_only("10.1016/j.test")

        assert result is None


# =====================================================================
# Bibliographic search tests
# =====================================================================

class TestSearchByBibliographic:
    """Tests for Crossref bibliographic search."""

    @pytest.mark.asyncio
    async def test_search_success(self, fetcher, sample_crossref_response):
        search_resp_data = {
            "message": {
                "items": [
                    {"DOI": "10.1016/j.spinee.2023.01.001", "title": ["Test"]}
                ]
            }
        }
        mock_search = _make_mock_response(search_resp_data)
        mock_detail = _make_mock_response(sample_crossref_response)

        async def mock_request(client, method, url, **kwargs):
            if "/works/" in url:
                return mock_detail
            return mock_search

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            result = await fetcher.search_by_bibliographic(title="Minimally Invasive Spine Surgery")

        assert result is not None
        assert result.title == "Minimally Invasive Spine Surgery"

    @pytest.mark.asyncio
    async def test_search_no_title_no_authors(self, fetcher):
        result = await fetcher.search_by_bibliographic(title="", authors=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_search_no_results(self, fetcher):
        resp_data = {"message": {"items": []}}
        mock_response = _make_mock_response(resp_data)
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            result = await fetcher.search_by_bibliographic(title="nonexistent paper xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_search_with_year_filter(self, fetcher, sample_crossref_response):
        search_resp_data = {
            "message": {
                "items": [{"DOI": "10.1016/j.test", "title": ["Test"]}]
            }
        }
        mock_search = _make_mock_response(search_resp_data)
        mock_detail = _make_mock_response(sample_crossref_response)

        call_urls = []
        async def mock_request(client, method, url, **kwargs):
            call_urls.append(url)
            if "/works/" in url:
                return mock_detail
            return mock_search

        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", side_effect=mock_request):
            result = await fetcher.search_by_bibliographic(
                title="Test", year=2023
            )
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_network_error(self, fetcher):
        exc = httpx.ConnectError("Connection refused")
        with patch("builder.doi_fulltext_fetcher._async_request_with_retry", new_callable=AsyncMock, side_effect=exc):
            result = await fetcher.search_by_bibliographic(title="Test")
        assert result is None


# =====================================================================
# Convenience function tests
# =====================================================================

class TestConvenienceFunctions:
    """Tests for fetch_by_doi and get_doi_metadata."""

    @pytest.mark.asyncio
    async def test_fetch_by_doi(self):
        with patch.object(DOIFulltextFetcher, 'fetch', new_callable=AsyncMock) as mock_fetch:
            with patch.object(DOIFulltextFetcher, 'close', new_callable=AsyncMock):
                mock_fetch.return_value = DOIFullText(doi="10.1016/test")
                result = await fetch_by_doi("10.1016/test")
        assert result.doi == "10.1016/test"

    @pytest.mark.asyncio
    async def test_get_doi_metadata(self):
        meta = DOIMetadata(doi="10.1016/test", title="Test")
        with patch.object(DOIFulltextFetcher, 'get_metadata_only', new_callable=AsyncMock) as mock_get:
            with patch.object(DOIFulltextFetcher, 'close', new_callable=AsyncMock):
                mock_get.return_value = meta
                result = await get_doi_metadata("10.1016/test")
        assert result is not None
        assert result.title == "Test"


# =====================================================================
# Client lifecycle tests
# =====================================================================

class TestClientLifecycle:
    """Tests for HTTP client lifecycle."""

    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, fetcher):
        client = await fetcher._get_client()
        assert client is not None
        assert isinstance(client, httpx.AsyncClient)
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, fetcher):
        """Closing without opening should not raise."""
        await fetcher.close()
        await fetcher.close()

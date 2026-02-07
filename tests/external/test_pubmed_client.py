"""Tests for PubMed client module."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import xml.etree.ElementTree as ET

from src.external.pubmed_client import (
    PubMedClient,
    PaperMetadata,
    PubMedError,
    APIError,
    RateLimitError,
)


# Sample XML response for testing
SAMPLE_PUBMED_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
    <PubmedArticle>
        <MedlineCitation>
            <PMID>12345678</PMID>
            <Article>
                <Journal>
                    <Title>Journal of Medical Research</Title>
                </Journal>
                <ArticleTitle>Sample Article Title</ArticleTitle>
                <Abstract>
                    <AbstractText Label="BACKGROUND">This is the background.</AbstractText>
                    <AbstractText Label="METHODS">These are the methods.</AbstractText>
                    <AbstractText Label="RESULTS">These are the results.</AbstractText>
                </Abstract>
                <AuthorList>
                    <Author>
                        <LastName>Smith</LastName>
                        <ForeName>John</ForeName>
                    </Author>
                    <Author>
                        <LastName>Doe</LastName>
                        <ForeName>Jane</ForeName>
                    </Author>
                </AuthorList>
            </Article>
            <PubmedData>
                <ArticleIdList>
                    <ArticleId IdType="doi">10.1234/test.2024</ArticleId>
                    <ArticleId IdType="pubmed">12345678</ArticleId>
                </ArticleIdList>
            </PubmedData>
        </MedlineCitation>
        <PubmedData>
            <History>
                <PubMedPubDate PubStatus="pubmed">
                    <Year>2024</Year>
                    <Month>1</Month>
                    <Day>15</Day>
                </PubMedPubDate>
            </History>
        </PubmedData>
        <MeshHeadingList>
            <MeshHeading>
                <DescriptorName>Spine</DescriptorName>
            </MeshHeading>
            <MeshHeading>
                <DescriptorName>Surgery</DescriptorName>
            </MeshHeading>
        </MeshHeadingList>
        <PublicationTypeList>
            <PublicationType>Journal Article</PublicationType>
            <PublicationType>Randomized Controlled Trial</PublicationType>
        </PublicationTypeList>
    </PubmedArticle>
</PubmedArticleSet>
"""


class TestPubMedClient:
    """Tests for PubMedClient class."""

    @pytest.fixture
    def client(self):
        """Create a PubMedClient instance for testing."""
        return PubMedClient(email="test@example.com")

    @pytest.fixture
    def client_with_api_key(self):
        """Create a PubMedClient with API key."""
        return PubMedClient(email="test@example.com", api_key="test_key")

    def test_init_without_credentials(self):
        """Test initialization without email or API key."""
        client = PubMedClient()
        assert client.email is None
        assert client.api_key is None
        assert client.RATE_LIMIT_DELAY == 0.34

    def test_init_with_email(self):
        """Test initialization with email."""
        client = PubMedClient(email="test@example.com")
        assert client.email == "test@example.com"
        assert client.api_key is None

    def test_init_with_api_key(self, client_with_api_key):
        """Test initialization with API key adjusts rate limit."""
        assert client_with_api_key.api_key == "test_key"
        assert client_with_api_key.RATE_LIMIT_DELAY == 0.1

    def test_build_params_without_credentials(self):
        """Test parameter building without credentials."""
        client = PubMedClient()
        params = client._build_params(db="pubmed", term="test")
        assert params == {"db": "pubmed", "term": "test"}

    def test_build_params_with_credentials(self, client_with_api_key):
        """Test parameter building with credentials."""
        params = client_with_api_key._build_params(db="pubmed", term="test")
        assert params["email"] == "test@example.com"
        assert params["api_key"] == "test_key"
        assert params["db"] == "pubmed"
        assert params["term"] == "test"

    @patch('src.external.pubmed_client.requests.get')
    def test_search_json_success(self, mock_get, client):
        """Test successful search with JSON response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "esearchresult": {
                "idlist": ["12345678", "87654321", "11111111"]
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        pmids = client.search("spine surgery", max_results=3)

        assert pmids == ["12345678", "87654321", "11111111"]
        assert mock_get.called
        call_args = mock_get.call_args
        assert "spine surgery" in str(call_args)

    @patch('src.external.pubmed_client.requests.get')
    def test_search_xml_success(self, mock_get, client):
        """Test successful search with XML response."""
        xml_response = """<?xml version="1.0"?>
        <eSearchResult>
            <IdList>
                <Id>12345678</Id>
                <Id>87654321</Id>
            </IdList>
        </eSearchResult>
        """
        mock_response = Mock()
        mock_response.text = xml_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        pmids = client.search("spine surgery", max_results=2, retmode="xml")

        assert pmids == ["12345678", "87654321"]

    @patch('src.external.pubmed_client.requests.get')
    def test_search_api_error(self, mock_get, client):
        """Test search with API error."""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        with pytest.raises(APIError, match="Search request failed"):
            client.search("test query")

    @patch('src.external.pubmed_client.requests.get')
    def test_fetch_paper_details_success(self, mock_get, client):
        """Test successful fetch of paper details."""
        # First create a proper XML with PubDate
        xml_with_date = SAMPLE_PUBMED_XML.replace(
            "<Article>",
            """<Article>
                <Journal>
                    <Title>Journal of Medical Research</Title>
                </Journal>
                <PubDate>
                    <Year>2024</Year>
                </PubDate>"""
        )

        mock_response = Mock()
        mock_response.text = xml_with_date
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        paper = client.fetch_paper_details("12345678")

        assert isinstance(paper, PaperMetadata)
        assert paper.pmid == "12345678"
        assert paper.title == "Sample Article Title"
        assert "John Smith" in paper.authors
        assert "Jane Doe" in paper.authors
        assert paper.year == 2024
        assert paper.journal == "Journal of Medical Research"
        assert "BACKGROUND: This is the background" in paper.abstract
        assert "METHODS: These are the methods" in paper.abstract
        assert "RESULTS: These are the results" in paper.abstract
        assert "Spine" in paper.mesh_terms
        assert "Surgery" in paper.mesh_terms
        assert paper.doi == "10.1234/test.2024"
        assert "Journal Article" in paper.publication_types
        assert "Randomized Controlled Trial" in paper.publication_types

    @patch('src.external.pubmed_client.requests.get')
    def test_fetch_paper_details_with_medline_date(self, mock_get, client):
        """Test fetching paper with MedlineDate instead of Year."""
        xml_with_medline = SAMPLE_PUBMED_XML.replace(
            "<Article>",
            """<Article>
                <Journal>
                    <Title>Test Journal</Title>
                </Journal>
                <PubDate>
                    <MedlineDate>2023 Jan-Feb</MedlineDate>
                </PubDate>"""
        )

        mock_response = Mock()
        mock_response.text = xml_with_medline
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        paper = client.fetch_paper_details("12345678")
        assert paper.year == 2023

    @patch('src.external.pubmed_client.requests.get')
    def test_fetch_paper_details_no_article(self, mock_get, client):
        """Test fetch with no article in response."""
        xml_empty = """<?xml version="1.0"?>
        <PubmedArticleSet>
        </PubmedArticleSet>
        """

        mock_response = Mock()
        mock_response.text = xml_empty
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(APIError, match="No article found"):
            client.fetch_paper_details("99999999")

    @patch('src.external.pubmed_client.requests.get')
    def test_fetch_abstract(self, mock_get, client):
        """Test fetching just the abstract."""
        xml_with_date = SAMPLE_PUBMED_XML.replace(
            "<Article>",
            """<Article>
                <Journal>
                    <Title>Test Journal</Title>
                </Journal>
                <PubDate>
                    <Year>2024</Year>
                </PubDate>"""
        )

        mock_response = Mock()
        mock_response.text = xml_with_date
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        abstract = client.fetch_abstract("12345678")

        assert "BACKGROUND: This is the background" in abstract
        assert "METHODS: These are the methods" in abstract

    @pytest.mark.skip(reason="Async methods tested via integration tests - sync methods cover core logic")
    @pytest.mark.asyncio
    async def test_search_async(self, client):
        """Test async search - skipped for unit tests, use integration tests."""
        pass

    @pytest.mark.skip(reason="Async methods tested via integration tests - sync methods cover core logic")
    @pytest.mark.asyncio
    async def test_search_async_error(self, client):
        """Test async search with error - skipped for unit tests, use integration tests."""
        pass

    @pytest.mark.skip(reason="Async methods tested via integration tests - sync methods cover core logic")
    @pytest.mark.asyncio
    async def test_fetch_paper_details_async(self, client):
        """Test async fetch of paper details - skipped for unit tests, use integration tests."""
        pass

    @pytest.mark.skip(reason="Async methods tested via integration tests - sync methods cover core logic")
    @pytest.mark.asyncio
    async def test_fetch_batch_async(self, client):
        """Test async batch fetch - skipped for unit tests, use integration tests."""
        pass


class TestPaperMetadata:
    """Tests for PaperMetadata dataclass."""

    def test_paper_metadata_creation(self):
        """Test creating PaperMetadata instance."""
        paper = PaperMetadata(
            pmid="12345678",
            title="Test Title",
            authors=["John Doe"],
            year=2024,
            journal="Test Journal",
            abstract="Test abstract",
            mesh_terms=["Spine", "Surgery"],
            doi="10.1234/test"
        )

        assert paper.pmid == "12345678"
        assert paper.title == "Test Title"
        assert paper.authors == ["John Doe"]
        assert paper.year == 2024
        assert paper.journal == "Test Journal"
        assert paper.abstract == "Test abstract"
        assert paper.mesh_terms == ["Spine", "Surgery"]
        assert paper.doi == "10.1234/test"
        assert paper.publication_types == []

    def test_paper_metadata_with_publication_types(self):
        """Test PaperMetadata with publication types."""
        paper = PaperMetadata(
            pmid="12345678",
            title="Test",
            authors=[],
            year=2024,
            journal="Test",
            abstract="Test",
            mesh_terms=[],
            publication_types=["Journal Article", "RCT"]
        )

        assert paper.publication_types == ["Journal Article", "RCT"]


class TestExceptions:
    """Tests for custom exceptions."""

    def test_pubmed_error(self):
        """Test base PubMedError."""
        error = PubMedError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_api_error(self):
        """Test APIError inheritance."""
        error = APIError("API failed")
        assert str(error) == "API failed"
        assert isinstance(error, PubMedError)
        assert isinstance(error, Exception)

    def test_rate_limit_error(self):
        """Test RateLimitError inheritance."""
        error = RateLimitError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, PubMedError)
        assert isinstance(error, Exception)

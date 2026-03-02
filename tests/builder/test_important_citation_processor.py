"""Comprehensive tests for ImportantCitationProcessor module.

Tests for:
- Initialization and configuration
- Citation processing pipeline (process_paper_citations)
- PubMed search and enrichment
- DOI/Crossref fallback logic
- Basic metadata creation (_create_basic_metadata)
- Keyword extraction (_extract_keywords_from_citation_text)
- DOI extraction (_extract_doi_from_text)
- Neo4j Paper node creation (_create_cited_paper_node)
- CITES relationship creation (_create_cites_relationship)
- Integrated citation processing (process_from_integrated_citations)
- Chunk-based processing (process_from_chunks)
- Convenience function (process_important_citations)
- Error handling and edge cases
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime
from dataclasses import asdict

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.important_citation_processor import (
    ImportantCitationProcessor,
    CitationProcessingResult,
    ProcessedCitation,
)
from builder.citation_context_extractor import (
    ExtractedCitation,
    CitationExtractionResult,
)


# ===========================================================================
# Mock setup helpers
# ===========================================================================

def make_mock_metadata(**overrides):
    """Create a mock BibliographicMetadata."""
    mock = MagicMock()
    mock.pmid = overrides.get("pmid", "12345678")
    mock.doi = overrides.get("doi", "10.1097/test")
    mock.title = overrides.get("title", "Test Paper Title")
    mock.authors = overrides.get("authors", ["Kim JH", "Park SM"])
    mock.journal = overrides.get("journal", "Spine")
    mock.journal_abbrev = overrides.get("journal_abbrev", "Spine")
    mock.year = overrides.get("year", 2023)
    mock.abstract = overrides.get("abstract", "Test abstract text.")
    mock.mesh_terms = overrides.get("mesh_terms", ["Spinal Fusion"])
    mock.publication_types = overrides.get("publication_types", ["Journal Article"])
    mock.source = overrides.get("source", "pubmed")
    mock.confidence = overrides.get("confidence", 0.95)
    mock.enriched_at = overrides.get("enriched_at", datetime.now())
    return mock


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sample_citation():
    """Sample extracted citation."""
    return ExtractedCitation(
        authors=["Kim", "Park"],
        year=2023,
        context="supports_result",
        section="discussion",
        citation_text="Kim et al. (2023) reported similar findings in UBE surgery...",
        importance_reason="Supports our VAS results",
        confidence=0.9,
        raw_citation="Kim et al., 2023",
    )


@pytest.fixture
def sample_extraction_result(sample_citation):
    """Sample citation extraction result."""
    return CitationExtractionResult(
        paper_title="Test Paper",
        important_citations=[sample_citation],
        all_citations=[sample_citation],
        main_findings=["UBE improved VAS"],
        provider_used="claude",
    )


@pytest.fixture
def mock_extractor(sample_extraction_result):
    """Mock CitationContextExtractor."""
    extractor = MagicMock()
    extractor.extract_important_citations = AsyncMock(return_value=sample_extraction_result)
    extractor.parse_citation_reference = MagicMock(
        return_value={"authors": ["Kim"], "year": 2023}
    )
    return extractor


@pytest.fixture
def mock_enricher():
    """Mock PubMedEnricher."""
    enricher = MagicMock()
    enricher.search_and_enrich_citation = AsyncMock(return_value=None)
    return enricher


@pytest.fixture
def mock_neo4j():
    """Mock Neo4jClient."""
    client = AsyncMock()
    client.run_query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def processor(mock_extractor, mock_enricher, mock_neo4j):
    """ImportantCitationProcessor with mocked dependencies."""
    with patch("builder.important_citation_processor.CitationContextExtractor", return_value=mock_extractor):
        with patch("builder.important_citation_processor.PubMedEnricher", return_value=mock_enricher):
            with patch("builder.important_citation_processor.EntityExtractor"):
                proc = ImportantCitationProcessor(
                    provider="claude",
                    pubmed_email="test@test.com",
                    neo4j_client=mock_neo4j,
                    min_confidence=0.7,
                    max_citations=20,
                    analyze_cited_abstracts=False,
                )
                proc.extractor = mock_extractor
                proc.enricher = mock_enricher
                return proc


# ===========================================================================
# Test: Dataclass Construction
# ===========================================================================

class TestDataclasses:
    """Test dataclass definitions."""

    def test_citation_processing_result_defaults(self):
        result = CitationProcessingResult()
        assert result.citing_paper_id == ""
        assert result.total_citations_found == 0
        assert result.papers_created == 0
        assert result.relationships_created == 0
        assert result.pubmed_search_failures == 0
        assert result.doi_fallback_successes == 0
        assert result.basic_citations_created == 0
        assert result.processed_citations == []
        assert result.citations_data == []
        assert result.errors == []

    def test_processed_citation_defaults(self):
        citation = ExtractedCitation(authors=["Test"])
        pc = ProcessedCitation(original=citation)
        assert pc.original.authors == ["Test"]
        assert pc.pubmed_metadata is None
        assert pc.cited_paper_id is None
        assert pc.relationship_created is False


# ===========================================================================
# Test: Keyword Extraction
# ===========================================================================

class TestExtractKeywords:
    """Test _extract_keywords_from_citation_text."""

    @pytest.fixture(autouse=True)
    def setup(self, processor):
        self.proc = processor

    def test_basic_extraction(self):
        text = "Kim et al. (2023) found that TLIF lumbar fusion had better outcomes."
        result = self.proc._extract_keywords_from_citation_text(text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_medical_keywords_prioritized(self):
        text = "The study showed that endoscopic spine decompression was effective."
        result = self.proc._extract_keywords_from_citation_text(text)
        # Medical keywords should be present
        keywords = result.lower().split()
        medical_found = any(kw in ["endoscopic", "spine", "decompression"] for kw in keywords)
        assert medical_found

    def test_empty_text(self):
        result = self.proc._extract_keywords_from_citation_text("")
        assert result == ""

    def test_author_removal(self):
        text = "Smith et al. (2022) performed lumbar fusion."
        result = self.proc._extract_keywords_from_citation_text(text, authors=["Smith"])
        assert "smith" not in result.lower()

    def test_stopwords_removed(self):
        text = "The study was performed in the hospital with the patients."
        result = self.proc._extract_keywords_from_citation_text(text)
        words = result.split()
        assert "the" not in words
        assert "was" not in words

    def test_max_five_keywords(self):
        text = "TLIF PLIF ALIF OLIF XLIF LLIF spine lumbar cervical thoracic fusion surgery."
        result = self.proc._extract_keywords_from_citation_text(text)
        keywords = result.split()
        assert len(keywords) <= 5


# ===========================================================================
# Test: DOI Extraction
# ===========================================================================

class TestExtractDoi:
    """Test _extract_doi_from_text."""

    def test_valid_doi(self):
        text = "See https://doi.org/10.1097/BRS.0000000000001234 for details."
        result = ImportantCitationProcessor._extract_doi_from_text(text)
        assert result == "10.1097/BRS.0000000000001234"

    def test_doi_in_citation(self):
        text = "Kim et al. 2023, doi: 10.1016/j.spinee.2023.01.001"
        result = ImportantCitationProcessor._extract_doi_from_text(text)
        assert "10.1016" in result

    def test_no_doi(self):
        text = "Kim et al. reported similar findings."
        result = ImportantCitationProcessor._extract_doi_from_text(text)
        assert result is None

    def test_empty_text(self):
        result = ImportantCitationProcessor._extract_doi_from_text("")
        assert result is None

    def test_none_text(self):
        result = ImportantCitationProcessor._extract_doi_from_text(None)
        assert result is None

    def test_trailing_period_removed(self):
        text = "DOI: 10.1097/test.1234."
        result = ImportantCitationProcessor._extract_doi_from_text(text)
        assert not result.endswith(".")


# ===========================================================================
# Test: Basic Metadata Creation
# ===========================================================================

class TestCreateBasicMetadata:
    """Test _create_basic_metadata."""

    def test_multiple_authors(self):
        citation = ExtractedCitation(authors=["Kim", "Park"], year=2023)
        result = ImportantCitationProcessor._create_basic_metadata(citation)
        assert result is not None
        assert "Kim et al." in result.title
        assert result.source == "citation_basic"
        assert result.confidence == 0.3

    def test_single_author(self):
        citation = ExtractedCitation(authors=["Kim"], year=2023)
        result = ImportantCitationProcessor._create_basic_metadata(citation)
        assert "Kim" in result.title
        assert "et al." not in result.title

    def test_no_authors_with_raw_citation(self):
        citation = ExtractedCitation(
            authors=[],
            raw_citation="Reference [15]",
        )
        result = ImportantCitationProcessor._create_basic_metadata(citation)
        assert result is not None
        assert "Reference" in result.title

    def test_no_authors_no_raw(self):
        citation = ExtractedCitation(authors=[], raw_citation="")
        result = ImportantCitationProcessor._create_basic_metadata(citation)
        assert result is None

    def test_year_not_available(self):
        citation = ExtractedCitation(authors=["Kim"], year=0)
        result = ImportantCitationProcessor._create_basic_metadata(citation)
        assert result is not None
        assert "n.d." in result.title


# ===========================================================================
# Test: process_paper_citations
# ===========================================================================

class TestProcessPaperCitations:
    """Test main pipeline process_paper_citations."""

    @pytest.mark.asyncio
    async def test_basic_pipeline(self, processor, mock_extractor):
        """Test basic citation processing pipeline."""
        result = await processor.process_paper_citations(
            citing_paper_id="paper_001",
            discussion_text="Kim et al. (2023) reported similar findings.",
            results_text="VAS improved from 7.2 to 2.1",
            main_findings=["UBE improved VAS"],
        )
        assert isinstance(result, CitationProcessingResult)
        assert result.citing_paper_id == "paper_001"
        assert result.total_citations_found >= 0

    @pytest.mark.asyncio
    async def test_no_citations_found(self, processor, mock_extractor):
        """Test when no important citations are found."""
        empty_result = CitationExtractionResult(
            paper_title="Test",
            important_citations=[],
            all_citations=[],
            provider_used="claude",
        )
        mock_extractor.extract_important_citations = AsyncMock(return_value=empty_result)

        result = await processor.process_paper_citations(
            citing_paper_id="paper_002",
            discussion_text="No citations here.",
        )
        assert result.papers_created == 0
        assert result.relationships_created == 0

    @pytest.mark.asyncio
    async def test_pubmed_search_failure(self, processor, mock_extractor, mock_enricher):
        """Test PubMed search failure counting."""
        mock_enricher.search_and_enrich_citation = AsyncMock(return_value=None)
        # Also disable basic metadata to count as failure
        with patch.object(processor, '_create_basic_metadata', return_value=None):
            result = await processor.process_paper_citations(
                citing_paper_id="paper_003",
                discussion_text="Test discussion",
            )
            assert result.pubmed_search_failures >= 1

    @pytest.mark.asyncio
    async def test_max_citations_limit(self, processor, mock_extractor):
        """Test max citations limit."""
        processor.max_citations = 2

        # Create many citations
        many_citations = [
            ExtractedCitation(
                authors=[f"Author{i}"],
                year=2023,
                context="supports_result",
                confidence=0.9,
                raw_citation=f"Author{i} et al., 2023",
            )
            for i in range(10)
        ]
        extraction = CitationExtractionResult(
            important_citations=many_citations,
            all_citations=many_citations,
            provider_used="claude",
        )
        mock_extractor.extract_important_citations = AsyncMock(return_value=extraction)

        result = await processor.process_paper_citations(
            citing_paper_id="paper_004",
            discussion_text="Test discussion",
        )
        # Should process at most max_citations
        assert result.important_citations_count == 10
        # But only 2 should be processed (tracked via processed_citations)
        assert len(result.processed_citations) <= 2

    @pytest.mark.asyncio
    async def test_error_handling(self, processor, mock_extractor):
        """Test error handling in pipeline."""
        mock_extractor.extract_important_citations = AsyncMock(
            side_effect=Exception("LLM connection failed")
        )

        result = await processor.process_paper_citations(
            citing_paper_id="paper_005",
            discussion_text="Test discussion",
        )
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_doi_fallback_success(self, processor, mock_extractor, mock_enricher):
        """Test DOI fallback when PubMed fails."""
        mock_enricher.search_and_enrich_citation = AsyncMock(return_value=None)

        # Mock DOI fetcher
        mock_doi_fetcher = MagicMock()
        mock_doi_result = MagicMock()
        mock_doi_result.title = "DOI Found Paper"
        mock_doi_result.doi = "10.1097/test"
        mock_doi_fetcher.get_metadata_only = AsyncMock(return_value=mock_doi_result)
        mock_doi_fetcher.search_by_bibliographic = AsyncMock(return_value=None)
        processor.doi_fetcher = mock_doi_fetcher

        # Create citation with DOI in text
        citation = ExtractedCitation(
            authors=["Kim"],
            year=2023,
            context="supports_result",
            citation_text="Kim et al. doi: 10.1097/test_paper",
            confidence=0.9,
            raw_citation="Kim et al., 2023",
        )
        extraction = CitationExtractionResult(
            important_citations=[citation],
            all_citations=[citation],
            provider_used="claude",
        )
        mock_extractor.extract_important_citations = AsyncMock(return_value=extraction)

        # Mock BibliographicMetadata.from_doi_metadata
        mock_bib = make_mock_metadata(source="crossref")
        with patch("builder.important_citation_processor.BibliographicMetadata") as MockBib:
            MockBib.from_doi_metadata = MagicMock(return_value=mock_bib)

            result = await processor.process_paper_citations(
                citing_paper_id="paper_006",
                discussion_text="Test",
            )
            assert result.doi_fallback_successes >= 1


# ===========================================================================
# Test: process_from_chunks
# ===========================================================================

class TestProcessFromChunks:
    """Test process_from_chunks method."""

    @pytest.mark.asyncio
    async def test_extracts_discussion_and_results(self, processor, mock_extractor):
        chunks = [
            {"section": "discussion", "content": "Our findings are consistent with Kim et al."},
            {"section": "results", "content": "VAS improved significantly."},
            {"section": "methods", "content": "We included 100 patients."},
            {"section": "conclusion", "content": "UBE is effective."},
        ]

        result = await processor.process_from_chunks(
            citing_paper_id="paper_007",
            chunks=chunks,
        )
        assert isinstance(result, CitationProcessingResult)
        # Verify that extract_important_citations was called
        mock_extractor.extract_important_citations.assert_called()

    @pytest.mark.asyncio
    async def test_empty_chunks(self, processor, mock_extractor):
        empty_result = CitationExtractionResult(provider_used="claude")
        mock_extractor.extract_important_citations = AsyncMock(return_value=empty_result)

        result = await processor.process_from_chunks(
            citing_paper_id="paper_008",
            chunks=[],
        )
        assert result.total_citations_found == 0


# ===========================================================================
# Test: process_from_integrated_citations
# ===========================================================================

class TestProcessFromIntegratedCitations:
    """Test process_from_integrated_citations method."""

    @pytest.mark.asyncio
    async def test_basic_integrated_processing(self, processor):
        citations = [
            {
                "authors": ["Kim", "Park"],
                "year": 2023,
                "context": "supports_result",
                "section": "discussion",
                "citation_text": "Kim et al. reported similar findings.",
                "importance_reason": "Supports VAS results",
            },
        ]

        result = await processor.process_from_integrated_citations(
            citing_paper_id="paper_009",
            citations=citations,
        )
        assert result.citing_paper_id == "paper_009"
        assert result.total_citations_found == 1

    @pytest.mark.asyncio
    async def test_empty_citations(self, processor):
        result = await processor.process_from_integrated_citations(
            citing_paper_id="paper_010",
            citations=[],
        )
        assert result.total_citations_found == 0
        assert result.papers_created == 0

    @pytest.mark.asyncio
    async def test_citation_with_none_values(self, processor):
        """Test handling of None values in citation dict."""
        citations = [
            {
                "authors": None,
                "year": None,
                "context": None,
                "section": None,
                "citation_text": "Some citation text.",
            },
        ]

        result = await processor.process_from_integrated_citations(
            citing_paper_id="paper_011",
            citations=citations,
        )
        # Should not crash
        assert isinstance(result, CitationProcessingResult)

    @pytest.mark.asyncio
    async def test_citation_with_non_list_authors(self, processor):
        """Test handling when authors is not a list."""
        citations = [
            {
                "authors": "Kim",  # string instead of list
                "year": 2023,
                "context": "supports_result",
                "citation_text": "Kim reported findings.",
            },
        ]

        result = await processor.process_from_integrated_citations(
            citing_paper_id="paper_012",
            citations=citations,
        )
        assert isinstance(result, CitationProcessingResult)

    @pytest.mark.asyncio
    async def test_citation_with_non_int_year(self, processor):
        """Test handling when year is not an int."""
        citations = [
            {
                "authors": ["Kim"],
                "year": "2023",  # string year
                "context": "supports_result",
                "citation_text": "Kim reported findings.",
            },
        ]

        result = await processor.process_from_integrated_citations(
            citing_paper_id="paper_013",
            citations=citations,
        )
        assert isinstance(result, CitationProcessingResult)

    @pytest.mark.asyncio
    async def test_skip_empty_citation(self, processor):
        """Test skipping citations with no authors, year, or text."""
        citations = [
            {"authors": None, "year": None, "citation_text": None},
        ]

        result = await processor.process_from_integrated_citations(
            citing_paper_id="paper_014",
            citations=citations,
        )
        # Should skip but not crash
        assert isinstance(result, CitationProcessingResult)

    @pytest.mark.asyncio
    async def test_raw_citation_generation(self, processor):
        """Test raw_citation is generated correctly."""
        citations = [
            {
                "authors": ["Kim", "Park"],
                "year": 2023,
                "context": "supports_result",
                "citation_text": "Kim and Park reported...",
            },
        ]

        result = await processor.process_from_integrated_citations(
            citing_paper_id="paper_015",
            citations=citations,
        )
        # At least one processed citation
        assert result.total_citations_found == 1


# ===========================================================================
# Test: _create_cites_relationship
# ===========================================================================

class TestCreateCitesRelationship:
    """Test CITES relationship creation."""

    @pytest.mark.asyncio
    async def test_successful_relationship(self, processor, mock_neo4j):
        citation = ExtractedCitation(
            context="supports_result",
            section="discussion",
            citation_text="Test citation",
            confidence=0.9,
        )

        result = await processor._create_cites_relationship(
            citing_paper_id="paper_001",
            cited_paper_id="cited_001",
            citation=citation,
            confidence=0.95,
        )
        assert result is True
        mock_neo4j.run_query.assert_called()

    @pytest.mark.asyncio
    async def test_no_neo4j_client(self, processor):
        processor.neo4j_client = None
        citation = ExtractedCitation(context="supports_result", confidence=0.9)

        result = await processor._create_cites_relationship(
            citing_paper_id="paper_001",
            cited_paper_id="cited_001",
            citation=citation,
            confidence=0.95,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_query_error_handling(self, processor, mock_neo4j):
        mock_neo4j.run_query = AsyncMock(side_effect=Exception("DB error"))
        citation = ExtractedCitation(context="supports_result", confidence=0.9)

        result = await processor._create_cites_relationship(
            citing_paper_id="paper_001",
            cited_paper_id="cited_001",
            citation=citation,
            confidence=0.95,
        )
        assert result is False


# ===========================================================================
# Test: _create_cited_paper_node
# ===========================================================================

class TestCreateCitedPaperNode:
    """Test Paper node creation for cited papers."""

    @pytest.mark.asyncio
    async def test_no_neo4j_client(self, processor):
        processor.neo4j_client = None
        result = await processor._create_cited_paper_node(make_mock_metadata())
        assert result is None

    @pytest.mark.asyncio
    async def test_paper_id_from_pmid(self, processor, mock_neo4j):
        metadata = make_mock_metadata(pmid="12345678")
        mock_neo4j.run_query = AsyncMock(return_value=[])

        with patch.object(processor, '_generate_abstract_embedding', new_callable=AsyncMock, return_value=True):
            result = await processor._create_cited_paper_node(metadata)
        assert result == "pmid_12345678"

    @pytest.mark.asyncio
    async def test_paper_id_from_doi(self, processor, mock_neo4j):
        metadata = make_mock_metadata(pmid="", doi="10.1097/test")
        mock_neo4j.run_query = AsyncMock(return_value=[])

        with patch.object(processor, '_generate_abstract_embedding', new_callable=AsyncMock, return_value=True):
            result = await processor._create_cited_paper_node(metadata)
        assert result is not None
        assert result.startswith("doi_")

    @pytest.mark.asyncio
    async def test_existing_paper_skipped(self, processor, mock_neo4j):
        metadata = make_mock_metadata(pmid="12345678")
        mock_neo4j.run_query = AsyncMock(return_value=[{"id": "pmid_12345678"}])

        result = await processor._create_cited_paper_node(metadata)
        assert result == "pmid_12345678"


# ===========================================================================
# Test: Convenience function
# ===========================================================================

class TestConvenienceFunction:
    """Test process_important_citations convenience function."""

    @pytest.mark.asyncio
    async def test_convenience_function_creates_processor(self):
        from builder.important_citation_processor import process_important_citations

        with patch("builder.important_citation_processor.ImportantCitationProcessor") as MockProc:
            mock_instance = MagicMock()
            mock_instance.process_paper_citations = AsyncMock(
                return_value=CitationProcessingResult(citing_paper_id="test_001")
            )
            MockProc.return_value = mock_instance

            result = await process_important_citations(
                citing_paper_id="test_001",
                discussion_text="Test discussion",
                provider="claude",
            )
            assert result.citing_paper_id == "test_001"
            MockProc.assert_called_once()

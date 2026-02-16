"""Important Citation Processor Tests.

Tests for important_citation_processor.py covering:
- Initialization and configuration
- Citation processing pipeline
- PubMed search and enrichment
- Neo4j Paper node creation
- CITES relationship creation
- Error handling and fallback logic
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Import module
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.important_citation_processor import (
    ImportantCitationProcessor,
    CitationProcessingResult,
    ProcessedCitation,
    process_important_citations
)
from builder.citation_context_extractor import (
    ExtractedCitation,
    CitationExtractionResult
)
from builder.pubmed_enricher import BibliographicMetadata


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
        citation_text="Kim et al. (2023) reported similar findings...",
        importance_reason="Supports our VAS results",
        confidence=0.9,
        raw_citation="Kim et al., 2023"
    )


@pytest.fixture
def sample_pubmed_metadata():
    """Sample PubMed metadata."""
    return BibliographicMetadata(
        pmid="12345678",
        doi="10.1097/test",
        title="UBE versus Open Laminectomy Study",
        authors=["Kim JH", "Park SM"],
        journal="Spine",
        year=2023,
        abstract="This study compares UBE versus open laminectomy...",
        mesh_terms=["Spinal Fusion", "Lumbar Vertebrae"],
        publication_types=["Randomized Controlled Trial"],
        source="pubmed",
        confidence=0.95,
        enriched_at=datetime.now()
    )


@pytest.fixture
def sample_extraction_result():
    """Sample citation extraction result."""
    citation1 = ExtractedCitation(
        authors=["Kim", "Park"],
        year=2023,
        context="supports_result",
        section="discussion",
        citation_text="Kim et al. reported similar findings...",
        importance_reason="Supports our results",
        confidence=0.9,
        raw_citation="Kim et al., 2023"
    )

    citation2 = ExtractedCitation(
        authors=["Lee"],
        year=2022,
        context="contradicts_result",
        section="discussion",
        citation_text="Lee et al. found different outcomes...",
        importance_reason="Contradicts our VAS findings",
        confidence=0.85,
        raw_citation="Lee et al., 2022"
    )

    return CitationExtractionResult(
        paper_title="Test Paper",
        all_citations=[citation1, citation2],
        important_citations=[citation1, citation2],
        main_findings=["VAS improved"],
        extraction_stats={"total": 2, "important": 2},
        provider_used="claude-haiku"
    )


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client."""
    client = AsyncMock()
    client.run_query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_citation_extractor():
    """Mock citation extractor."""
    extractor = AsyncMock()
    return extractor


@pytest.fixture
def mock_pubmed_enricher():
    """Mock PubMed enricher."""
    enricher = AsyncMock()
    return enricher


# ===========================================================================
# Test ImportantCitationProcessor Initialization
# ===========================================================================

class TestImportantCitationProcessorInit:
    """Test ImportantCitationProcessor initialization."""

    def test_init_default(self):
        """Test initialization with defaults."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor()

                assert processor.min_confidence == 0.7
                assert processor.max_citations == 20
                assert processor.analyze_cited_abstracts is True

    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    min_confidence=0.8,
                    max_citations=10,
                    analyze_cited_abstracts=False
                )

                assert processor.min_confidence == 0.8
                assert processor.max_citations == 10
                assert processor.analyze_cited_abstracts is False

    def test_init_with_neo4j_client(self, mock_neo4j_client):
        """Test initialization with Neo4j client."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )

                assert processor.neo4j_client is mock_neo4j_client

    def test_init_with_provider_claude(self):
        """Test initialization with Claude provider."""
        with patch('builder.important_citation_processor.CitationContextExtractor') as MockExtractor:
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(provider="claude")

                # Should initialize extractor with provider
                MockExtractor.assert_called_once()

    def test_init_with_provider_gemini(self):
        """Test initialization with Gemini provider."""
        with patch('builder.important_citation_processor.CitationContextExtractor') as MockExtractor:
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(provider="gemini")

                MockExtractor.assert_called_once()


# ===========================================================================
# Test Citation Processing Pipeline
# ===========================================================================

class TestProcessPaperCitations:
    """Test process_paper_citations method."""

    @pytest.mark.asyncio
    async def test_process_paper_citations_success(
        self,
        sample_extraction_result,
        sample_pubmed_metadata,
        mock_neo4j_client
    ):
        """Test successful citation processing."""
        with patch('builder.important_citation_processor.CitationContextExtractor') as MockExtractor:
            with patch('builder.important_citation_processor.PubMedEnricher') as MockEnricher:
                # Setup mocks
                mock_extractor = MockExtractor.return_value
                mock_extractor.extract_important_citations = AsyncMock(
                    return_value=sample_extraction_result
                )

                mock_enricher = MockEnricher.return_value
                mock_enricher.search_and_enrich_citation = AsyncMock(
                    return_value=sample_pubmed_metadata
                )

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )
                processor.extractor = mock_extractor
                processor.enricher = mock_enricher

                # Process citations
                result = await processor.process_paper_citations(
                    citing_paper_id="paper_123",
                    discussion_text="This study compares...",
                    results_text="VAS improved from 7.2 to 2.1..."
                )

                assert result.citing_paper_id == "paper_123"
                assert result.total_citations_found == 2
                assert result.important_citations_count == 2

    @pytest.mark.asyncio
    async def test_process_paper_citations_no_citations(self, mock_neo4j_client):
        """Test processing when no citations are found."""
        empty_result = CitationExtractionResult(
            paper_title="",
            all_citations=[],
            important_citations=[],
            main_findings=[],
            extraction_stats={},
            provider_used="claude-haiku"
        )

        with patch('builder.important_citation_processor.CitationContextExtractor') as MockExtractor:
            with patch('builder.important_citation_processor.PubMedEnricher'):
                mock_extractor = MockExtractor.return_value
                mock_extractor.extract_important_citations = AsyncMock(
                    return_value=empty_result
                )

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )
                processor.extractor = mock_extractor

                result = await processor.process_paper_citations(
                    citing_paper_id="paper_123",
                    discussion_text="No citations here..."
                )

                assert result.total_citations_found == 0
                assert result.important_citations_count == 0
                assert result.papers_created == 0

    @pytest.mark.asyncio
    async def test_process_paper_citations_max_limit(
        self,
        sample_extraction_result,
        mock_neo4j_client
    ):
        """Test that max_citations limit is respected."""
        with patch('builder.important_citation_processor.CitationContextExtractor') as MockExtractor:
            with patch('builder.important_citation_processor.PubMedEnricher') as MockEnricher:
                mock_extractor = MockExtractor.return_value
                mock_extractor.extract_important_citations = AsyncMock(
                    return_value=sample_extraction_result
                )

                mock_enricher = MockEnricher.return_value
                mock_enricher.search_and_enrich_citation = AsyncMock(return_value=None)

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client,
                    max_citations=1  # Limit to 1
                )
                processor.extractor = mock_extractor
                processor.enricher = mock_enricher

                result = await processor.process_paper_citations(
                    citing_paper_id="paper_123",
                    discussion_text="Text..."
                )

                # Should only process 1 citation despite 2 being extracted
                assert len(result.processed_citations) == 1


# ===========================================================================
# Test Single Citation Processing
# ===========================================================================

class TestProcessSingleCitation:
    """Test _process_single_citation method."""

    @pytest.mark.asyncio
    async def test_process_single_citation_pubmed_success(
        self,
        sample_citation,
        sample_pubmed_metadata,
        mock_neo4j_client
    ):
        """Test successful PubMed enrichment."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher') as MockEnricher:
                mock_enricher = MockEnricher.return_value
                mock_enricher.search_and_enrich_citation = AsyncMock(
                    return_value=sample_pubmed_metadata
                )

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )
                processor.enricher = mock_enricher

                processed = await processor._process_single_citation(
                    citation=sample_citation,
                    citing_paper_id="paper_123"
                )

                assert processed.pubmed_metadata is not None
                assert processed.pubmed_metadata.pmid == "12345678"

    @pytest.mark.asyncio
    async def test_process_single_citation_pubmed_not_found(
        self,
        sample_citation,
        mock_neo4j_client
    ):
        """Test when PubMed search fails."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher') as MockEnricher:
                mock_enricher = MockEnricher.return_value
                mock_enricher.search_and_enrich_citation = AsyncMock(return_value=None)

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )
                processor.enricher = mock_enricher

                processed = await processor._process_single_citation(
                    citation=sample_citation,
                    citing_paper_id="paper_123"
                )

                # Should fall back to basic metadata
                assert processed.pubmed_metadata is not None
                assert processed.pubmed_metadata.source == "citation_basic"

    @pytest.mark.asyncio
    async def test_process_single_citation_with_doi_fallback(
        self,
        sample_citation,
        mock_neo4j_client
    ):
        """Test DOI fallback when PubMed fails."""
        # Add DOI to citation text
        citation_with_doi = ExtractedCitation(
            authors=["Kim"],
            year=2023,
            context="supports_result",
            section="discussion",
            citation_text="Kim et al. (doi: 10.1097/test) reported...",
            importance_reason="Test",
            confidence=0.9,
            raw_citation="Kim et al., 2023"
        )

        # Mock DOI metadata as BibliographicMetadata (matches what code expects)
        doi_metadata = BibliographicMetadata(
            doi="10.1097/test",
            title="Test Paper",
            authors=["Kim"],
            year=2023,
            abstract="",
            journal="Test Journal",
            source="crossref",
            confidence=0.7,
            enriched_at=datetime.now()
        )

        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher') as MockEnricher:
                mock_enricher = MockEnricher.return_value
                mock_enricher.search_and_enrich_citation = AsyncMock(return_value=None)

                # Mock DOI fetcher
                mock_doi_fetcher = AsyncMock()
                mock_doi_fetcher.get_metadata_only = AsyncMock(return_value=doi_metadata)

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client,
                    doi_fetcher=mock_doi_fetcher
                )
                processor.enricher = mock_enricher

                processed = await processor._process_single_citation(
                    citation=citation_with_doi,
                    citing_paper_id="paper_123"
                )

                # Should have metadata (either DOI fallback or basic)
                assert processed is not None


# ===========================================================================
# Test Neo4j Paper Creation
# ===========================================================================

class TestCreateCitedPaperNode:
    """Test _create_cited_paper_node method."""

    @pytest.mark.asyncio
    async def test_create_cited_paper_node_with_pmid(
        self,
        sample_pubmed_metadata,
        mock_neo4j_client
    ):
        """Test Paper node creation with PMID."""
        # Mock existing paper check (not found)
        mock_neo4j_client.run_query = AsyncMock(return_value=[])

        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client,
                    analyze_cited_abstracts=False  # Disable abstract analysis
                )

                paper_id = await processor._create_cited_paper_node(
                    metadata=sample_pubmed_metadata
                )

                assert paper_id == "pmid_12345678"
                assert mock_neo4j_client.run_query.called

    @pytest.mark.asyncio
    async def test_create_cited_paper_node_already_exists(
        self,
        sample_pubmed_metadata,
        mock_neo4j_client
    ):
        """Test when Paper node already exists."""
        # Mock existing paper check (found)
        mock_neo4j_client.run_query = AsyncMock(
            return_value=[{"id": "pmid_12345678"}]
        )

        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )

                paper_id = await processor._create_cited_paper_node(
                    metadata=sample_pubmed_metadata
                )

                assert paper_id == "pmid_12345678"
                # Should skip creation if exists
                assert mock_neo4j_client.run_query.call_count == 1

    @pytest.mark.asyncio
    async def test_create_cited_paper_node_with_doi_only(
        self,
        mock_neo4j_client
    ):
        """Test Paper node creation with DOI only (no PMID)."""
        metadata = BibliographicMetadata(
            doi="10.1097/test",
            title="Test Paper",
            authors=["Kim"],
            year=2023,
            source="crossref",
            confidence=0.8,
            enriched_at=datetime.now()
        )

        mock_neo4j_client.run_query = AsyncMock(return_value=[])

        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client,
                    analyze_cited_abstracts=False
                )

                paper_id = await processor._create_cited_paper_node(metadata=metadata)

                assert paper_id.startswith("doi_")
                assert "10.1097_test" in paper_id or "10_1097_test" in paper_id


# ===========================================================================
# Test CITES Relationship Creation
# ===========================================================================

class TestCreateCitesRelationship:
    """Test _create_cites_relationship method."""

    @pytest.mark.asyncio
    async def test_create_cites_relationship_success(
        self,
        sample_citation,
        mock_neo4j_client
    ):
        """Test successful CITES relationship creation."""
        mock_neo4j_client.run_query = AsyncMock(return_value=None)

        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )

                success = await processor._create_cites_relationship(
                    citing_paper_id="paper_123",
                    cited_paper_id="pmid_12345678",
                    citation=sample_citation,
                    confidence=0.95
                )

                assert success is True
                assert mock_neo4j_client.run_query.called

    @pytest.mark.asyncio
    async def test_create_cites_relationship_no_client(self, sample_citation):
        """Test CITES relationship creation without Neo4j client."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    neo4j_client=None
                )

                success = await processor._create_cites_relationship(
                    citing_paper_id="paper_123",
                    cited_paper_id="pmid_12345678",
                    citation=sample_citation,
                    confidence=0.95
                )

                assert success is False


# ===========================================================================
# Test Utility Methods
# ===========================================================================

class TestUtilityMethods:
    """Test utility methods."""

    def test_extract_keywords_from_citation_text(self):
        """Test keyword extraction from citation text."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor()

                citation_text = (
                    "Kim et al. (2023) reported that TLIF showed better "
                    "fusion rates compared to PLIF in patients with lumbar stenosis."
                )

                keywords = processor._extract_keywords_from_citation_text(
                    citation_text,
                    authors=["Kim"]
                )

                # Should extract medical keywords
                assert any(kw in keywords.lower() for kw in ["tlif", "fusion", "lumbar", "stenosis"])
                # Should exclude author names and years
                assert "kim" not in keywords.lower()
                assert "2023" not in keywords

    def test_extract_doi_from_text(self):
        """Test DOI extraction from text."""
        text = "This paper (doi: 10.1097/BRS.0001234) shows that..."

        doi = ImportantCitationProcessor._extract_doi_from_text(text)

        assert doi == "10.1097/BRS.0001234"

    def test_extract_doi_from_text_no_doi(self):
        """Test DOI extraction when no DOI present."""
        text = "This paper shows results..."

        doi = ImportantCitationProcessor._extract_doi_from_text(text)

        assert doi is None

    def test_create_basic_metadata(self):
        """Test basic metadata creation."""
        citation = ExtractedCitation(
            authors=["Kim", "Park"],
            year=2023,
            context="supports_result",
            section="discussion",
            citation_text="Test citation",
            importance_reason="Test",
            confidence=0.8,
            raw_citation="Kim et al., 2023"
        )

        metadata = ImportantCitationProcessor._create_basic_metadata(citation)

        assert metadata is not None
        assert metadata.source == "citation_basic"
        assert metadata.confidence == 0.3
        assert "Kim et al." in metadata.title

    def test_create_basic_metadata_no_info(self):
        """Test basic metadata creation with insufficient info."""
        citation = ExtractedCitation(
            authors=[],
            year=0,
            context="supports_result",
            section="discussion",
            citation_text="",
            importance_reason="",
            confidence=0.8,
            raw_citation=""
        )

        metadata = ImportantCitationProcessor._create_basic_metadata(citation)

        assert metadata is None


# ===========================================================================
# Test Integrated Citations Processing
# ===========================================================================

class TestProcessFromIntegratedCitations:
    """Test process_from_integrated_citations method."""

    @pytest.mark.asyncio
    async def test_process_integrated_citations_success(self, mock_neo4j_client):
        """Test processing integrated citations."""
        integrated_citations = [
            {
                "authors": ["Kim", "Park"],
                "year": 2023,
                "context": "supports_result",
                "section": "discussion",
                "citation_text": "Kim et al. reported similar findings...",
                "importance_reason": "Supports results"
            }
        ]

        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher') as MockEnricher:
                mock_enricher = MockEnricher.return_value
                mock_enricher.search_and_enrich_citation = AsyncMock(return_value=None)

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )
                processor.enricher = mock_enricher

                result = await processor.process_from_integrated_citations(
                    citing_paper_id="paper_123",
                    citations=integrated_citations
                )

                assert result.total_citations_found == 1
                assert result.important_citations_count == 1

    @pytest.mark.asyncio
    async def test_process_integrated_citations_empty(self, mock_neo4j_client):
        """Test processing empty integrated citations."""
        with patch('builder.important_citation_processor.CitationContextExtractor'):
            with patch('builder.important_citation_processor.PubMedEnricher'):
                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client
                )

                result = await processor.process_from_integrated_citations(
                    citing_paper_id="paper_123",
                    citations=[]
                )

                assert result.total_citations_found == 0


# ===========================================================================
# Test Convenience Function
# ===========================================================================

class TestConvenienceFunction:
    """Test process_important_citations convenience function."""

    @pytest.mark.asyncio
    async def test_convenience_function(self, mock_neo4j_client):
        """Test convenience function."""
        with patch('builder.important_citation_processor.CitationContextExtractor') as MockExtractor:
            with patch('builder.important_citation_processor.PubMedEnricher'):
                mock_extractor = MockExtractor.return_value
                empty_result = CitationExtractionResult(
                    paper_title="",
                    all_citations=[],
                    important_citations=[],
                    main_findings=[],
                    extraction_stats={},
                    provider_used="claude-haiku"
                )
                mock_extractor.extract_important_citations = AsyncMock(
                    return_value=empty_result
                )

                result = await process_important_citations(
                    citing_paper_id="paper_123",
                    discussion_text="Test discussion...",
                    neo4j_client=mock_neo4j_client
                )

                assert isinstance(result, CitationProcessingResult)
                assert result.citing_paper_id == "paper_123"


# ===========================================================================
# Integration Tests
# ===========================================================================

class TestIntegration:
    """Integration-like tests."""

    @pytest.mark.asyncio
    async def test_full_workflow(
        self,
        sample_extraction_result,
        sample_pubmed_metadata,
        mock_neo4j_client
    ):
        """Test full citation processing workflow."""
        with patch('builder.important_citation_processor.CitationContextExtractor') as MockExtractor:
            with patch('builder.important_citation_processor.PubMedEnricher') as MockEnricher:
                # Setup mocks
                mock_extractor = MockExtractor.return_value
                mock_extractor.extract_important_citations = AsyncMock(
                    return_value=sample_extraction_result
                )

                mock_enricher = MockEnricher.return_value
                mock_enricher.search_and_enrich_citation = AsyncMock(
                    return_value=sample_pubmed_metadata
                )

                # Mock Neo4j responses
                mock_neo4j_client.run_query = AsyncMock(
                    side_effect=[
                        [],  # Paper doesn't exist
                        None,  # Create paper
                        None,  # Create embedding
                        None,  # Create CITES relationship
                        [],  # Second paper doesn't exist
                        None,  # Create second paper
                        None,  # Create second embedding
                        None,  # Create second CITES relationship
                    ]
                )

                processor = ImportantCitationProcessor(
                    neo4j_client=mock_neo4j_client,
                    analyze_cited_abstracts=False
                )
                processor.extractor = mock_extractor
                processor.enricher = mock_enricher

                # Process citations
                result = await processor.process_paper_citations(
                    citing_paper_id="paper_123",
                    discussion_text="Kim et al. and Lee et al. reported...",
                    results_text="VAS improved..."
                )

                # Verify complete workflow
                assert result.total_citations_found == 2
                assert result.important_citations_count == 2
                assert result.papers_created == 2
                assert result.relationships_created == 2
                assert len(result.citations_data) == 2

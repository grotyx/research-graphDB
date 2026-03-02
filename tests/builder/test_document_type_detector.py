"""Tests for DocumentTypeDetector.

Comprehensive tests for document type detection including:
- URL-based detection (domain mapping, path analysis)
- Content-based detection (regex patterns for RCT, meta-analysis, etc.)
- Filename-based detection
- Combined multi-source detection
- Confidence scoring and alternatives
- Edge cases: ambiguous, short text, invalid URLs
- Convenience functions
- User confirmation formatting
"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from builder.document_type_detector import (
    DocumentType,
    DetectionResult,
    DocumentTypeDetector,
    detect_document_type,
    get_document_type_options,
    URL_DOMAIN_MAP,
    CONTENT_PATTERNS,
    FILENAME_PATTERNS,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def detector():
    """Create a DocumentTypeDetector instance."""
    return DocumentTypeDetector()


# ============================================================================
# TestDocumentType
# ============================================================================

class TestDocumentType:
    """Test DocumentType enum."""

    def test_journal_article(self):
        assert DocumentType.JOURNAL_ARTICLE.value == "journal-article"

    def test_book(self):
        assert DocumentType.BOOK.value == "book"

    def test_preprint(self):
        assert DocumentType.PREPRINT.value == "preprint"

    def test_patent(self):
        assert DocumentType.PATENT.value == "patent"

    def test_document_default(self):
        assert DocumentType.DOCUMENT.value == "document"

    def test_all_types_have_values(self):
        """All enum members have non-empty values."""
        for doc_type in DocumentType:
            assert doc_type.value
            assert isinstance(doc_type.value, str)


# ============================================================================
# TestDetectionResult
# ============================================================================

class TestDetectionResult:
    """Test DetectionResult dataclass."""

    def test_high_confidence(self):
        result = DetectionResult(
            document_type=DocumentType.JOURNAL_ARTICLE,
            confidence=0.95,
            detection_method="url",
        )
        assert result.is_confident is True
        assert result.needs_confirmation is False

    def test_low_confidence(self):
        result = DetectionResult(
            document_type=DocumentType.DOCUMENT,
            confidence=0.5,
            detection_method="default",
        )
        assert result.is_confident is False
        assert result.needs_confirmation is True

    def test_boundary_confidence(self):
        """Test confidence at exactly 0.85 threshold."""
        result = DetectionResult(
            document_type=DocumentType.JOURNAL_ARTICLE,
            confidence=0.85,
            detection_method="content",
        )
        assert result.is_confident is True
        assert result.needs_confirmation is False

    def test_below_boundary(self):
        result = DetectionResult(
            document_type=DocumentType.JOURNAL_ARTICLE,
            confidence=0.84,
            detection_method="content",
        )
        assert result.is_confident is False
        assert result.needs_confirmation is True

    def test_alternatives_default(self):
        result = DetectionResult(
            document_type=DocumentType.JOURNAL_ARTICLE,
            confidence=0.9,
            detection_method="url",
        )
        assert result.alternatives == []

    def test_evidence_default(self):
        result = DetectionResult(
            document_type=DocumentType.JOURNAL_ARTICLE,
            confidence=0.9,
            detection_method="url",
        )
        assert result.evidence == []


# ============================================================================
# TestURLDetection
# ============================================================================

class TestURLDetection:
    """Test URL-based document type detection."""

    def test_pubmed_url(self, detector):
        result = detector.detect(url="https://pubmed.ncbi.nlm.nih.gov/12345678/")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        assert result.confidence >= 0.95

    def test_pmc_url(self, detector):
        result = detector.detect(url="https://pmc.ncbi.nlm.nih.gov/PMC1234567/")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_doi_url(self, detector):
        result = detector.detect(url="https://doi.org/10.1016/j.spinee.2024.01.001")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        assert result.confidence >= 0.85

    def test_arxiv_url(self, detector):
        result = detector.detect(url="https://arxiv.org/abs/2301.12345")
        assert result.document_type == DocumentType.PREPRINT
        assert result.confidence >= 0.90

    def test_biorxiv_url(self, detector):
        result = detector.detect(url="https://www.biorxiv.org/content/10.1101/2024.01.01")
        assert result.document_type == DocumentType.PREPRINT

    def test_medrxiv_url(self, detector):
        result = detector.detect(url="https://www.medrxiv.org/content/2024.01.01")
        assert result.document_type == DocumentType.PREPRINT

    def test_newspaper_url(self, detector):
        result = detector.detect(url="https://www.nytimes.com/2024/01/01/health/spine-surgery.html")
        assert result.document_type == DocumentType.NEWSPAPER_ARTICLE

    def test_youtube_url(self, detector):
        result = detector.detect(url="https://www.youtube.com/watch?v=abc123")
        assert result.document_type == DocumentType.VIDEO

    def test_github_url(self, detector):
        result = detector.detect(url="https://github.com/user/repo")
        assert result.document_type == DocumentType.SOFTWARE

    def test_patent_url(self, detector):
        result = detector.detect(url="https://patents.google.com/patent/US12345")
        assert result.document_type == DocumentType.PATENT

    def test_medium_url(self, detector):
        result = detector.detect(url="https://medium.com/@user/article-title-abc123")
        assert result.document_type == DocumentType.BLOG_POST

    def test_kaggle_url(self, detector):
        result = detector.detect(url="https://www.kaggle.com/datasets/test")
        assert result.document_type == DocumentType.DATASET

    def test_www_prefix_stripped(self, detector):
        result = detector.detect(url="https://www.pubmed.ncbi.nlm.nih.gov/12345/")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_unknown_domain(self, detector):
        result = detector.detect(url="https://unknown-domain-xyz.com/page")
        assert result.document_type == DocumentType.DOCUMENT
        assert result.confidence == 0.0

    def test_path_based_article(self, detector):
        result = detector.detect(url="https://example.com/article/12345")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_path_based_blog(self, detector):
        result = detector.detect(url="https://example.com/blog/spine-tips")
        assert result.document_type == DocumentType.BLOG_POST

    def test_invalid_url(self, detector):
        result = detector.detect(url="not-a-valid-url")
        # Should return default with no matches
        assert result.document_type == DocumentType.DOCUMENT

    def test_springer_url(self, detector):
        result = detector.detect(url="https://link.springer.com/article/10.1007/s00586-024-12345")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_spine_journal_url(self, detector):
        result = detector.detect(url="https://journals.lww.com/spinejournal/Abstract/2024/01000")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        assert result.confidence >= 0.90


# ============================================================================
# TestContentDetection
# ============================================================================

class TestContentDetection:
    """Test content-based document type detection."""

    def test_doi_in_content(self, detector):
        result = detector.detect(content="DOI: 10.1016/j.spinee.2024.01.001")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        assert result.confidence >= 0.85

    def test_pmid_in_content(self, detector):
        result = detector.detect(content="PMID: 12345678")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_rct_mention(self, detector):
        result = detector.detect(content="This randomized controlled trial evaluated...")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        assert result.confidence >= 0.85

    def test_meta_analysis_mention(self, detector):
        result = detector.detect(content="A meta-analysis of 20 studies was performed.")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_systematic_review(self, detector):
        result = detector.detect(content="We conducted a systematic review of the literature.")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_p_value(self, detector):
        result = detector.detect(content="The difference was significant (p < 0.001).")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_confidence_interval(self, detector):
        result = detector.detect(content="The 95% CI was 1.2 to 3.4.")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_isbn_detection(self, detector):
        result = detector.detect(content="ISBN: 978-0-123-45678-9")
        assert result.document_type == DocumentType.BOOK
        assert result.confidence >= 0.90

    def test_thesis_mention(self, detector):
        result = detector.detect(content="Doctoral thesis submitted to the University...")
        assert result.document_type == DocumentType.THESIS
        assert result.confidence >= 0.90

    def test_patent_number(self, detector):
        result = detector.detect(content="Patent No.: US12345678B2")
        assert result.document_type == DocumentType.PATENT

    def test_preprint_mention(self, detector):
        result = detector.detect(content="This preprint has not been peer-reviewed.")
        assert result.document_type == DocumentType.PREPRINT

    def test_arxiv_id(self, detector):
        result = detector.detect(content="Available at arxiv:2301.12345")
        assert result.document_type == DocumentType.PREPRINT

    def test_conference_proceedings(self, detector):
        result = detector.detect(content="Proceedings of the International Conference on...")
        assert result.document_type == DocumentType.CONFERENCE_PAPER

    def test_technical_report(self, detector):
        result = detector.detect(content="Technical report on spine biomechanics analysis.")
        assert result.document_type == DocumentType.REPORT

    def test_empty_content(self, detector):
        result = detector.detect(content="")
        assert result.document_type == DocumentType.DOCUMENT
        assert result.confidence == 0.0

    def test_short_ambiguous_content(self, detector):
        result = detector.detect(content="Spine surgery results")
        assert result.document_type == DocumentType.DOCUMENT


# ============================================================================
# TestFilenameDetection
# ============================================================================

class TestFilenameDetection:
    """Test filename-based document type detection."""

    def test_paper_filename(self, detector):
        result = detector.detect(filename="smith_2024_lumbar_paper.pdf")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_thesis_filename(self, detector):
        result = detector.detect(filename="kim_2024_phd_thesis.pdf")
        assert result.document_type == DocumentType.THESIS
        assert result.confidence >= 0.85

    def test_dissertation_filename(self, detector):
        result = detector.detect(filename="dissertation_final.pdf")
        assert result.document_type == DocumentType.THESIS

    def test_report_filename(self, detector):
        result = detector.detect(filename="annual_report_2024.pdf")
        assert result.document_type == DocumentType.REPORT

    def test_presentation_filename(self, detector):
        result = detector.detect(filename="conference_presentation.pdf")
        assert result.document_type == DocumentType.PRESENTATION

    def test_pptx_extension(self, detector):
        result = detector.detect(filename="lecture_slides.pptx")
        assert result.document_type == DocumentType.PRESENTATION
        assert result.confidence >= 0.90

    def test_book_filename(self, detector):
        result = detector.detect(filename="spine_textbook_ch3.pdf")
        assert result.document_type == DocumentType.BOOK

    def test_chapter_filename(self, detector):
        result = detector.detect(filename="chapter_12_cervical.pdf")
        assert result.document_type == DocumentType.BOOK_SECTION

    def test_et_al_pattern(self, detector):
        result = detector.detect(filename="2024 Park et al RCT.pdf")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_generic_filename(self, detector):
        result = detector.detect(filename="document123.pdf")
        assert result.document_type == DocumentType.DOCUMENT


# ============================================================================
# TestCombinedDetection
# ============================================================================

class TestCombinedDetection:
    """Test combined multi-source detection."""

    def test_url_and_content_reinforcement(self, detector):
        """Test that URL + content detection provides higher confidence."""
        result = detector.detect(
            url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            content="PMID: 12345678. This randomized controlled trial..."
        )
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        assert result.confidence >= 0.95

    def test_url_and_filename(self, detector):
        result = detector.detect(
            url="https://arxiv.org/abs/2301.12345",
            filename="preprint_2024.pdf"
        )
        assert result.document_type == DocumentType.PREPRINT

    def test_all_sources(self, detector):
        result = detector.detect(
            url="https://pubmed.ncbi.nlm.nih.gov/12345/",
            content="DOI: 10.1234/test. The systematic review found...",
            filename="2024_review_paper.pdf"
        )
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        assert result.confidence >= 0.95

    def test_conflicting_signals(self, detector):
        """When URL says one thing and content says another."""
        result = detector.detect(
            url="https://github.com/user/repo",
            content="PMID: 12345678. This randomized controlled trial evaluated..."
        )
        # Should have alternatives
        assert result.document_type in [DocumentType.JOURNAL_ARTICLE, DocumentType.SOFTWARE]

    def test_no_inputs(self, detector):
        result = detector.detect()
        assert result.document_type == DocumentType.DOCUMENT
        assert result.confidence == 0.0
        assert len(result.alternatives) >= 1

    def test_multiple_content_patterns_bonus(self, detector):
        """Multiple evidence matches should give confidence bonus."""
        text = (
            "PMID: 12345678. DOI: 10.1016/test. "
            "This randomized controlled trial with p < 0.001 "
            "and 95% CI 1.2-3.4."
        )
        result = detector.detect(content=text)
        assert result.document_type == DocumentType.JOURNAL_ARTICLE
        # Multiple patterns should boost confidence above single pattern
        assert result.confidence >= 0.90


# ============================================================================
# TestGetTypeForSource
# ============================================================================

class TestGetTypeForSource:
    """Test get_type_for_source method."""

    def test_pubmed_source(self, detector):
        assert detector.get_type_for_source("pubmed") == DocumentType.JOURNAL_ARTICLE

    def test_pmc_source(self, detector):
        assert detector.get_type_for_source("pmc") == DocumentType.JOURNAL_ARTICLE

    def test_pdf_source(self, detector):
        assert detector.get_type_for_source("pdf") == DocumentType.JOURNAL_ARTICLE

    def test_url_source(self, detector):
        assert detector.get_type_for_source("url") == DocumentType.WEBPAGE

    def test_text_source(self, detector):
        assert detector.get_type_for_source("text") == DocumentType.DOCUMENT

    def test_unknown_source(self, detector):
        assert detector.get_type_for_source("unknown") == DocumentType.DOCUMENT

    def test_case_insensitive(self, detector):
        assert detector.get_type_for_source("PubMed") == DocumentType.JOURNAL_ARTICLE


# ============================================================================
# TestFormatForUserConfirmation
# ============================================================================

class TestFormatForUserConfirmation:
    """Test format_for_user_confirmation method."""

    def test_format_high_confidence(self, detector):
        result = DetectionResult(
            document_type=DocumentType.JOURNAL_ARTICLE,
            confidence=0.95,
            detection_method="url",
            alternatives=[DocumentType.PREPRINT],
            evidence=["[url] PubMed domain (conf: 0.95)"],
        )
        formatted = detector.format_for_user_confirmation(result)

        assert formatted["detected"] == "journal-article"
        assert formatted["confidence"] == 0.95
        assert formatted["needs_confirmation"] is False
        assert len(formatted["options"]) == 2

    def test_format_low_confidence(self, detector):
        result = DetectionResult(
            document_type=DocumentType.DOCUMENT,
            confidence=0.5,
            detection_method="default",
            alternatives=[DocumentType.JOURNAL_ARTICLE, DocumentType.WEBPAGE],
        )
        formatted = detector.format_for_user_confirmation(result)

        assert formatted["needs_confirmation"] is True
        assert len(formatted["options"]) == 3

    def test_format_options_recommended(self, detector):
        result = DetectionResult(
            document_type=DocumentType.BOOK,
            confidence=0.8,
            detection_method="content",
            alternatives=[DocumentType.BOOK_SECTION],
        )
        formatted = detector.format_for_user_confirmation(result)

        recommended = [o for o in formatted["options"] if o["recommended"]]
        assert len(recommended) == 1
        assert recommended[0]["value"] == "book"


# ============================================================================
# TestConvenienceFunctions
# ============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_detect_document_type_url(self):
        result = detect_document_type(url="https://pubmed.ncbi.nlm.nih.gov/12345/")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_detect_document_type_content(self):
        result = detect_document_type(content="This systematic review found...")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_detect_document_type_filename(self):
        result = detect_document_type(filename="thesis.pdf")
        assert result.document_type == DocumentType.THESIS

    def test_get_document_type_options(self):
        options = get_document_type_options()
        assert isinstance(options, list)
        assert len(options) == len(DocumentType)
        for opt in options:
            assert "value" in opt
            assert "label" in opt

    def test_options_have_labels(self):
        options = get_document_type_options()
        for opt in options:
            assert len(opt["label"]) > 0
            assert "-" not in opt["label"]  # Hyphens replaced with spaces + title case


# ============================================================================
# TestHelperMethods
# ============================================================================

class TestHelperMethods:
    """Test internal helper methods."""

    def test_detect_from_url_convenience(self, detector):
        result = detector.detect_from_url("https://doi.org/10.1234/test")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_detect_from_content_convenience(self, detector):
        result = detector.detect_from_content("DOI: 10.1234/test")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_detect_from_content_with_filename(self, detector):
        result = detector.detect_from_content("some text", filename="paper.pdf")
        assert isinstance(result, DetectionResult)

    def test_subdomain_partial_match(self, detector):
        """Test subdomain partial matching."""
        result = detector.detect(url="https://sub.nature.com/articles/123")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

    def test_korean_news_domain(self, detector):
        result = detector.detect(url="https://www.chosun.com/economy/2024/01/01/test")
        assert result.document_type == DocumentType.NEWSPAPER_ARTICLE


# ============================================================================
# TestEdgeCases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_confidence_cap_at_one(self, detector):
        """Confidence should never exceed 1.0 even with bonuses."""
        text = (
            "PMID: 12345. DOI: 10.1234/test. "
            "randomized controlled trial. meta-analysis. "
            "systematic review. p < 0.001. 95% CI. "
            "odds ratio. hazard ratio."
        )
        result = detector.detect(
            url="https://pubmed.ncbi.nlm.nih.gov/12345/",
            content=text,
            filename="2024_Smith_et_al_paper.pdf"
        )
        assert result.confidence <= 1.0

    def test_url_domain_map_completeness(self):
        """Verify URL_DOMAIN_MAP has expected entries."""
        assert "pubmed.ncbi.nlm.nih.gov" in URL_DOMAIN_MAP
        assert "arxiv.org" in URL_DOMAIN_MAP
        assert "youtube.com" in URL_DOMAIN_MAP

    def test_content_patterns_not_empty(self):
        """Verify CONTENT_PATTERNS has entries."""
        assert len(CONTENT_PATTERNS) > 10

    def test_filename_patterns_not_empty(self):
        """Verify FILENAME_PATTERNS has entries."""
        assert len(FILENAME_PATTERNS) > 5

    def test_none_url(self, detector):
        """Test with None url."""
        result = detector.detect(url=None, content="test")
        assert isinstance(result, DetectionResult)

    def test_none_content(self, detector):
        """Test with None content."""
        result = detector.detect(content=None)
        assert result.document_type == DocumentType.DOCUMENT

    def test_none_filename(self, detector):
        """Test with None filename."""
        result = detector.detect(filename=None)
        assert result.document_type == DocumentType.DOCUMENT

    def test_very_long_content(self, detector):
        """Test with very long content."""
        long_text = "This is a test. " * 10000
        result = detector.detect(content=long_text)
        assert isinstance(result, DetectionResult)

    def test_special_chars_in_url(self, detector):
        """Test URL with special characters."""
        result = detector.detect(url="https://pubmed.ncbi.nlm.nih.gov/123?term=spine%20surgery")
        assert result.document_type == DocumentType.JOURNAL_ARTICLE

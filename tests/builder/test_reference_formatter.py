"""Tests for ReferenceFormatter module.

7개 참고문헌 스타일 포맷팅, edge case, 유틸리티 함수 테스트.

Styles tested: Vancouver, AMA, APA, JBJS, Spine, NLM, Harvard
Edge cases: 누락 필드, 다수 저자, 특수문자, BibTeX, RIS
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.reference_formatter import (
    ReferenceFormatter,
    PaperReference,
    StyleConfig,
    AuthorFormatConfig,
    DEFAULT_STYLES,
    DEFAULT_JOURNAL_MAPPINGS,
    format_reference,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def formatter(tmp_path):
    """ReferenceFormatter with a temporary styles file (avoids touching real data)."""
    styles_file = tmp_path / "journal_styles.json"
    return ReferenceFormatter(styles_file=styles_file)


@pytest.fixture
def sample_paper():
    """Standard sample paper for most tests."""
    return PaperReference(
        paper_id="test_001",
        title="Comparison of UBE and MIS-TLIF for lumbar stenosis",
        authors=["Park SM", "Kim JH", "Lee CK"],
        year=2024,
        month=3,
        journal="Spine",
        journal_abbrev="Spine",
        volume="49",
        issue="6",
        pages="412-419",
        doi="10.1097/BRS.0000000001234",
        pmid="38012345",
    )


@pytest.fixture
def many_authors_paper():
    """Paper with 8 authors for et al. testing."""
    return PaperReference(
        paper_id="test_002",
        title="Multi-center study of lumbar fusion outcomes",
        authors=["Kim JH", "Park SM", "Lee CK", "Cho YJ",
                 "Hwang SH", "Yoon ST", "Bridwell KH", "Lenke LG"],
        year=2023,
        journal="Spine Journal",
        journal_abbrev="Spine J",
        volume="23",
        issue="10",
        pages="1450-1462",
        doi="10.1016/j.spinee.2023.05.012",
    )


@pytest.fixture
def minimal_paper():
    """Paper with minimal fields filled."""
    return PaperReference(
        paper_id="test_003",
        title="A brief report",
        authors=["Smith J"],
        year=2022,
        journal="Spine",
        journal_abbrev="Spine",
    )


# ===========================================================================
# Test: Vancouver Style
# ===========================================================================

class TestVancouverStyle:
    """Vancouver (ICMJE) style formatting tests."""

    def test_basic_formatting(self, formatter, sample_paper):
        result = formatter.format(sample_paper, style="vancouver")
        assert "Park SM" in result
        assert "Kim JH" in result
        assert "Lee CK" in result
        assert "2024" in result
        assert "49(6)" in result
        assert ":412-419" in result
        assert result.endswith(".")

    def test_et_al_threshold_6(self, formatter, many_authors_paper):
        """Vancouver uses et_al_threshold=6, et_al_min=6."""
        result = formatter.format(many_authors_paper, style="vancouver")
        assert "et al" in result
        # All 6 first authors should appear (et_al_min=6)
        assert "Kim JH" in result

    def test_no_doi_included(self, formatter, sample_paper):
        """Vancouver style does not include DOI by default."""
        result = formatter.format(sample_paper, style="vancouver")
        assert "doi:" not in result.lower()

    def test_journal_abbreviation_used(self, formatter, sample_paper):
        """Vancouver uses journal abbreviation."""
        result = formatter.format(sample_paper, style="vancouver")
        assert "Spine" in result


# ===========================================================================
# Test: AMA Style
# ===========================================================================

class TestAMAStyle:
    """AMA (American Medical Association) style formatting tests."""

    def test_basic_formatting(self, formatter, sample_paper):
        result = formatter.format(sample_paper, style="ama")
        assert "Park SM" in result
        assert "2024" in result
        assert result.endswith(".")

    def test_doi_included(self, formatter, sample_paper):
        """AMA includes DOI."""
        result = formatter.format(sample_paper, style="ama")
        assert "doi:" in result

    def test_et_al_min_3(self, formatter, many_authors_paper):
        """AMA uses et_al_min=3 when et_al_threshold=6 is exceeded."""
        result = formatter.format(many_authors_paper, style="ama")
        assert "et al" in result
        # With 8 authors and et_al_min=3, only first 3 should appear
        assert "Kim JH" in result
        assert "Park SM" in result
        assert "Lee CK" in result

    def test_journal_italicized(self, formatter, sample_paper):
        """AMA italicizes journal name."""
        result = formatter.format(sample_paper, style="ama")
        assert "*Spine*" in result


# ===========================================================================
# Test: APA Style
# ===========================================================================

class TestAPAStyle:
    """APA 7th Edition style formatting tests."""

    def test_basic_formatting(self, formatter, sample_paper):
        result = formatter.format(sample_paper, style="apa")
        assert "2024" in result
        assert result.endswith(".")

    def test_doi_as_url(self, formatter, sample_paper):
        """APA formats DOI as https://doi.org/..."""
        result = formatter.format(sample_paper, style="apa")
        assert "https://doi.org/" in result

    def test_ampersand_separator(self, formatter, sample_paper):
        """APA uses ' & ' as last author separator."""
        result = formatter.format(sample_paper, style="apa")
        assert " & " in result

    def test_initials_with_dots(self, formatter, sample_paper):
        """APA uses dots in initials (S.M.)."""
        result = formatter.format(sample_paper, style="apa")
        # "Park SM" already formatted; for a raw name, dots would be added
        # The sample paper has pre-formatted names so check config exists
        apa_config = DEFAULT_STYLES["apa"]
        assert apa_config.author.initials_format == "dots"


# ===========================================================================
# Test: JBJS Style
# ===========================================================================

class TestJBJSStyle:
    """JBJS (Bone & Joint Journal) style formatting tests."""

    def test_basic_formatting(self, formatter, sample_paper):
        result = formatter.format(sample_paper, style="jbjs")
        assert "Park SM" in result
        assert "2024" in result
        assert result.endswith(".")

    def test_abbreviated_pages(self, formatter, sample_paper):
        """JBJS uses abbreviated page ranges (412-419 -> 412-9)."""
        result = formatter.format(sample_paper, style="jbjs")
        # pages_format = abbreviated: 412-419 -> 412-9
        assert "412-9" in result

    def test_volume_format_with_b(self, formatter, sample_paper):
        """JBJS uses {volume}-B({issue}) format."""
        result = formatter.format(sample_paper, style="jbjs")
        assert "49-B(6)" in result


# ===========================================================================
# Test: Spine Style
# ===========================================================================

class TestSpineStyle:
    """Spine Journal style formatting tests."""

    def test_basic_formatting(self, formatter, sample_paper):
        result = formatter.format(sample_paper, style="spine")
        assert "Park SM" in result
        assert "2024" in result
        assert "49(6)" in result
        assert result.endswith(".")

    def test_et_al_min_3(self, formatter, many_authors_paper):
        """Spine uses et_al_min=3."""
        result = formatter.format(many_authors_paper, style="spine")
        assert "et al" in result

    def test_no_doi(self, formatter, sample_paper):
        """Spine style does not include DOI."""
        result = formatter.format(sample_paper, style="spine")
        assert "doi" not in result.lower()


# ===========================================================================
# Test: NLM Style
# ===========================================================================

class TestNLMStyle:
    """NLM (National Library of Medicine) style formatting tests."""

    def test_basic_formatting(self, formatter, sample_paper):
        result = formatter.format(sample_paper, style="nlm")
        assert "Park SM" in result
        assert "2024" in result
        assert result.endswith(".")

    def test_year_month_format(self, formatter, sample_paper):
        """NLM uses year_month date format."""
        result = formatter.format(sample_paper, style="nlm")
        assert "2024 Mar" in result

    def test_pmid_included(self, formatter, sample_paper):
        """NLM includes PMID."""
        result = formatter.format(sample_paper, style="nlm")
        assert "PMID: 38012345" in result


# ===========================================================================
# Test: Harvard Style
# ===========================================================================

class TestHarvardStyle:
    """Harvard style formatting tests."""

    def test_basic_formatting(self, formatter, sample_paper):
        result = formatter.format(sample_paper, style="harvard")
        assert "2024" in result
        assert result.endswith(".")

    def test_title_in_quotes(self, formatter, sample_paper):
        """Harvard puts title in quotes."""
        result = formatter.format(sample_paper, style="harvard")
        assert '"Comparison' in result or '"comparison' in result.lower()

    def test_pages_with_pp(self, formatter, sample_paper):
        """Harvard uses 'pp.' prefix for pages."""
        result = formatter.format(sample_paper, style="harvard")
        assert "pp. " in result

    def test_volume_bold(self, formatter, sample_paper):
        """Harvard bolds volume."""
        result = formatter.format(sample_paper, style="harvard")
        assert "**" in result  # Markdown bold

    def test_et_al_threshold_3(self, formatter, sample_paper):
        """Harvard uses et_al_threshold=3, et_al_min=1."""
        result = formatter.format(sample_paper, style="harvard")
        # 3 authors meets threshold=3, so et al. should appear
        assert "et al." in result

    def test_and_separator(self, formatter):
        """Harvard uses ' and ' between two authors."""
        paper = PaperReference(
            title="A study", authors=["Kim JH", "Park SM"],
            year=2024, journal="Spine", journal_abbrev="Spine",
        )
        result = formatter.format(paper, style="harvard")
        assert " and " in result


# ===========================================================================
# Test: Edge Cases - Missing Fields
# ===========================================================================

class TestEdgeCasesMissingFields:
    """Tests with missing or empty fields."""

    def test_no_authors(self, formatter):
        paper = PaperReference(title="No authors study", year=2024,
                               journal="Spine", journal_abbrev="Spine")
        result = formatter.format(paper, style="vancouver")
        assert "No authors study" in result
        assert "2024" in result
        assert result.endswith(".")

    def test_no_year(self, formatter):
        paper = PaperReference(title="Timeless study", authors=["Kim JH"],
                               journal="Spine", journal_abbrev="Spine")
        result = formatter.format(paper, style="vancouver")
        assert "Timeless study" in result
        assert "Kim JH" in result

    def test_no_title(self, formatter):
        paper = PaperReference(authors=["Kim JH"], year=2024,
                               journal="Spine", journal_abbrev="Spine")
        result = formatter.format(paper, style="vancouver")
        assert "Kim JH" in result
        assert "2024" in result

    def test_completely_empty_paper(self, formatter):
        paper = PaperReference()
        result = formatter.format(paper, style="vancouver")
        # Should not crash; may return empty or just a period
        assert isinstance(result, str)

    def test_no_volume_no_issue(self, formatter):
        paper = PaperReference(title="Study", authors=["Lee A"],
                               year=2023, journal="J Spine", journal_abbrev="J Spine")
        result = formatter.format(paper, style="vancouver")
        assert "2023" in result
        assert "()" not in result  # Empty parens should be removed

    def test_no_journal(self, formatter):
        paper = PaperReference(title="Orphan paper", authors=["Kim JH"],
                               year=2024, volume="10", pages="1-5")
        result = formatter.format(paper, style="vancouver")
        assert "Orphan paper" in result
        assert "Kim JH" in result


# ===========================================================================
# Test: Edge Cases - Special Characters and Authors
# ===========================================================================

class TestEdgeCasesSpecialCharacters:
    """Tests with special characters, hyphenated names, etc."""

    def test_hyphenated_author_name(self, formatter):
        paper = PaperReference(
            title="Study", authors=["Sang-Min Park"],
            year=2024, journal="Spine", journal_abbrev="Spine",
        )
        result = formatter.format(paper, style="vancouver")
        assert "Park" in result

    def test_comma_separated_author(self, formatter):
        """Author in 'Last, First' format -- the formatter parses raw names
        and produces initials. The exact output depends on parsing heuristics;
        we verify it does not crash and produces non-empty output."""
        paper = PaperReference(
            title="Study", authors=["Park, Sang-Min"],
            year=2024, journal="Spine", journal_abbrev="Spine",
        )
        result = formatter.format(paper, style="vancouver")
        # The formatter may interpret commas differently; verify it produces output
        assert len(result) > 0
        assert "Study" in result

    def test_special_characters_in_title(self, formatter):
        paper = PaperReference(
            title="Beta-TCP & HA in fusion: a <meta-analysis>",
            authors=["Kim JH"], year=2024,
            journal="Spine", journal_abbrev="Spine",
        )
        result = formatter.format(paper, style="vancouver")
        assert "&" in result or "&amp;" in result

    def test_electronic_pages(self, formatter):
        """e-pages should not be abbreviated."""
        paper = PaperReference(
            title="Study", authors=["Kim JH"], year=2024,
            journal="Spine", journal_abbrev="Spine",
            volume="10", pages="e123-e145",
        )
        result = formatter.format(paper, style="jbjs")  # JBJS abbreviates
        assert "e123-e145" in result

    def test_supplement_pages(self, formatter):
        """Supplement pages should not be abbreviated."""
        paper = PaperReference(
            title="Study", authors=["Kim JH"], year=2024,
            journal="Spine", journal_abbrev="Spine",
            volume="10", pages="S1-S10",
        )
        result = formatter.format(paper, style="jbjs")
        assert "S1-S10" in result


# ===========================================================================
# Test: Utility Functions
# ===========================================================================

class TestUtilityFunctions:
    """Tests for BibTeX, RIS, and convenience functions."""

    def test_to_bibtex(self, formatter, sample_paper):
        result = formatter.to_bibtex(sample_paper)
        assert "@article{Park2024," in result
        assert "title = {" in result
        assert "author = {Park SM and Kim JH and Lee CK}" in result
        assert "year = {2024}" in result
        assert "doi = {" in result

    def test_to_ris(self, formatter, sample_paper):
        result = formatter.to_ris(sample_paper)
        assert "TY  - JOUR" in result
        assert "TI  - Comparison" in result
        assert "AU  - Park SM" in result
        assert "AU  - Kim JH" in result
        assert "PY  - 2024" in result
        assert "VL  - 49" in result
        assert "DO  - 10.1097" in result
        assert "ER  - " in result

    def test_to_ris_pages_split(self, formatter, sample_paper):
        result = formatter.to_ris(sample_paper)
        assert "SP  - 412" in result
        assert "EP  - 419" in result

    def test_format_multiple(self, formatter, sample_paper, minimal_paper):
        result = formatter.format_multiple(
            [sample_paper, minimal_paper], style="vancouver", numbered=True
        )
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("1. ")
        assert lines[1].startswith("2. ")

    def test_format_multiple_unnumbered(self, formatter, sample_paper, minimal_paper):
        result = formatter.format_multiple(
            [sample_paper, minimal_paper], style="vancouver", numbered=False
        )
        lines = result.strip().split("\n")
        assert not lines[0].startswith("1. ")

    def test_format_reference_convenience(self, tmp_path):
        """Test the module-level format_reference convenience function."""
        metadata = {
            "title": "Test paper",
            "authors": ["Kim JH"],
            "year": 2024,
            "journal": "Spine",
            "journal_abbrev": "Spine",
            "volume": "49",
            "issue": "1",
            "pages": "10-15",
        }
        # format_reference creates its own ReferenceFormatter (which may look for
        # real styles file), so we just check it doesn't crash and returns a string
        result = format_reference(metadata, style="vancouver")
        assert isinstance(result, str)
        assert "Kim JH" in result


# ===========================================================================
# Test: PaperReference.from_metadata
# ===========================================================================

class TestPaperReferenceFromMetadata:
    """Tests for PaperReference.from_metadata factory method."""

    def test_basic_creation(self):
        meta = {
            "title": "Test", "authors": ["A B"], "year": 2024,
            "journal": "Spine", "volume": "1",
        }
        ref = PaperReference.from_metadata(meta, paper_id="p1")
        assert ref.paper_id == "p1"
        assert ref.title == "Test"
        assert ref.authors == ["A B"]
        assert ref.year == 2024

    def test_year_as_string(self):
        meta = {"title": "T", "year": "2023"}
        ref = PaperReference.from_metadata(meta)
        assert ref.year == 2023

    def test_year_invalid_string(self):
        meta = {"title": "T", "year": "unknown"}
        ref = PaperReference.from_metadata(meta)
        assert ref.year == 0

    def test_authors_not_list(self):
        meta = {"title": "T", "authors": "not a list"}
        ref = PaperReference.from_metadata(meta)
        assert ref.authors == []

    def test_authors_with_empty_strings(self):
        meta = {"title": "T", "authors": ["Kim JH", "", None, "  ", "Lee A"]}
        ref = PaperReference.from_metadata(meta)
        assert ref.authors == ["Kim JH", "Lee A"]


# ===========================================================================
# Test: StyleConfig serialization
# ===========================================================================

class TestStyleConfigSerialization:
    """Tests for StyleConfig to_dict/from_dict."""

    def test_round_trip(self):
        config = DEFAULT_STYLES["vancouver"]
        data = config.to_dict()
        restored = StyleConfig.from_dict(data)
        assert restored.name == config.name
        assert restored.author.et_al_threshold == config.author.et_al_threshold
        assert restored.title_case == config.title_case

    def test_from_dict_partial(self):
        data = {"name": "custom", "title_quotes": True}
        config = StyleConfig.from_dict(data)
        assert config.name == "custom"
        assert config.title_quotes is True
        # Defaults should remain
        assert config.final_period is True


# ===========================================================================
# Test: Journal Style Mapping
# ===========================================================================

class TestJournalStyleMapping:
    """Tests for journal-to-style mapping."""

    def test_default_journal_mapping(self, formatter):
        style = formatter.get_journal_style("Spine")
        assert style is not None

    def test_case_insensitive_lookup(self, formatter):
        style = formatter.get_journal_style("spine")
        assert style is not None

    def test_unknown_journal_returns_none(self, formatter):
        style = formatter.get_journal_style("Unknown Journal XYZ")
        assert style is None

    def test_format_with_journal_name(self, formatter, sample_paper):
        """Format using journal name instead of explicit style."""
        result = formatter.format(sample_paper, journal="Spine")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_list_styles(self, formatter):
        styles = formatter.list_styles()
        assert "default_styles" in styles
        assert "vancouver" in styles["default_styles"]
        assert "ama" in styles["default_styles"]
        assert len(styles["default_styles"]) >= 7

    def test_get_style_unknown_falls_back_to_vancouver(self, formatter):
        config = formatter.get_style("nonexistent_style")
        assert config.name == "Vancouver (ICMJE)"

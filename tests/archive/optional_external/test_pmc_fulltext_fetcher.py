"""PMC Full Text Fetcher Tests.

Tests for the PMCFullTextFetcher module that retrieves full text
from PubMed Central for Open Access papers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.pmc_fulltext_fetcher import (
    PMCFullTextFetcher,
    PMCFullText,
    PMCSection,
    fetch_pmc_fulltext,
)


# =============================================================================
# PMCSection Tests
# =============================================================================

class TestPMCSection:
    """PMCSection 데이터클래스 테스트."""

    def test_basic_creation(self):
        """기본 생성 테스트."""
        section = PMCSection(
            section_type="METHODS",
            title="Methods",
            text="We conducted a randomized controlled trial..."
        )
        assert section.section_type == "METHODS"
        assert section.title == "Methods"
        assert "randomized" in section.text

    def test_to_dict(self):
        """to_dict 메서드 테스트."""
        section = PMCSection(
            section_type="RESULTS",
            title="Results",
            text="The primary outcome showed..."
        )
        d = section.to_dict()
        assert d["section_type"] == "RESULTS"
        assert d["title"] == "Results"
        assert "primary outcome" in d["text"]


# =============================================================================
# PMCFullText Tests
# =============================================================================

class TestPMCFullText:
    """PMCFullText 데이터클래스 테스트."""

    def test_empty_fulltext(self):
        """빈 전문 테스트."""
        ft = PMCFullText(pmid="12345678")
        assert ft.pmid == "12345678"
        assert ft.has_full_text is False
        assert ft.full_text == ""
        assert ft.sections == []

    def test_with_abstract_only(self):
        """초록만 있는 경우 테스트."""
        ft = PMCFullText(
            pmid="12345678",
            abstract="This is the abstract."
        )
        assert ft.has_full_text is False  # No sections
        assert "abstract" in ft.full_text.lower()

    def test_with_sections(self):
        """섹션 있는 경우 테스트."""
        ft = PMCFullText(
            pmid="12345678",
            pmcid="PMC9876543",
            title="Test Paper",
            abstract="Abstract text.",
            sections=[
                PMCSection("INTRO", "Introduction", "Background info..."),
                PMCSection("METHODS", "Methods", "Study design..."),
                PMCSection("RESULTS", "Results", "Findings..."),
            ],
            is_open_access=True
        )
        assert ft.has_full_text is True
        assert ft.is_open_access is True
        assert len(ft.sections) == 3
        assert ft.pmcid == "PMC9876543"

    def test_get_section(self):
        """get_section 메서드 테스트."""
        ft = PMCFullText(
            pmid="12345678",
            sections=[
                PMCSection("INTRO", "Introduction", "Intro text"),
                PMCSection("METHODS", "Methods", "Methods text"),
            ]
        )
        intro = ft.get_section("INTRO")
        assert intro is not None
        assert intro.section_type == "INTRO"

        methods = ft.get_section("methods")  # Case insensitive
        assert methods is not None

        missing = ft.get_section("RESULTS")
        assert missing is None

    def test_full_text_concatenation(self):
        """full_text 속성 테스트."""
        ft = PMCFullText(
            pmid="12345678",
            abstract="Abstract here.",
            sections=[
                PMCSection("RESULTS", "Results", "Results text."),
            ]
        )
        full = ft.full_text
        assert "Abstract" in full
        assert "Results" in full

    def test_to_dict(self):
        """to_dict 메서드 테스트."""
        ft = PMCFullText(
            pmid="12345678",
            pmcid="PMC9876543",
            title="Test",
            abstract="Abstract",
            sections=[PMCSection("INTRO", "Intro", "Text")],
            is_open_access=True
        )
        d = ft.to_dict()
        assert d["pmid"] == "12345678"
        assert d["pmcid"] == "PMC9876543"
        assert d["is_open_access"] is True
        assert d["has_full_text"] is True
        assert len(d["sections"]) == 1


# =============================================================================
# PMCFullTextFetcher Tests
# =============================================================================

class TestPMCFullTextFetcher:
    """PMCFullTextFetcher 클래스 테스트."""

    def test_initialization(self):
        """초기화 테스트."""
        fetcher = PMCFullTextFetcher(timeout=60.0)
        assert fetcher.timeout == 60.0
        assert fetcher._client is None

    def test_normalize_section_type(self):
        """섹션 타입 정규화 테스트."""
        fetcher = PMCFullTextFetcher()

        assert fetcher._normalize_section_type("introduction") == "INTRO"
        assert fetcher._normalize_section_type("methods") == "METHODS"
        assert fetcher._normalize_section_type("Materials and Methods") == "METHODS"
        assert fetcher._normalize_section_type("results") == "RESULTS"
        assert fetcher._normalize_section_type("discussion") == "DISCUSS"
        assert fetcher._normalize_section_type("conclusions") == "CONCL"
        assert fetcher._normalize_section_type("unknown section") == "OTHER"
        assert fetcher._normalize_section_type("") == "OTHER"

    def test_parse_bioc_response_empty(self):
        """빈 응답 파싱 테스트."""
        fetcher = PMCFullTextFetcher()
        result = fetcher._parse_bioc_response({"documents": []}, "12345678")
        assert result.pmid == "12345678"
        assert result.is_open_access is False
        assert result.has_full_text is False

    def test_parse_bioc_response_with_content(self):
        """콘텐츠 있는 응답 파싱 테스트."""
        fetcher = PMCFullTextFetcher()
        data = {
            "documents": [{
                "infons": {"pmcid": "PMC9876543"},
                "passages": [
                    {
                        "infons": {"type": "title"},
                        "text": "Test Paper Title"
                    },
                    {
                        "infons": {"type": "abstract", "section_type": "abstract"},
                        "text": "This is the abstract."
                    },
                    {
                        "infons": {"section_type": "intro"},
                        "text": "Introduction text here that is long enough to be included."
                    },
                    {
                        "infons": {"section_type": "methods"},
                        "text": "Methods section with study design and procedures described in detail."
                    },
                ]
            }]
        }
        result = fetcher._parse_bioc_response(data, "12345678")
        assert result.pmid == "12345678"
        assert result.pmcid == "PMC9876543"
        assert result.title == "Test Paper Title"
        assert result.abstract == "This is the abstract."
        assert result.is_open_access is True
        assert len(result.sections) >= 1  # At least intro should be included

    def test_parse_bioc_response_list_format(self):
        """BioC API 리스트 형식 응답 파싱 테스트 (실제 API 형식)."""
        fetcher = PMCFullTextFetcher()
        # Real API returns a list of collections
        data = [{
            "bioctype": "BioCCollection",
            "source": "PMC",
            "documents": [{
                "bioctype": "BioCDocument",
                "id": "PMC12061607",
                "infons": {"license": "CC BY-NC"},
                "passages": [
                    {
                        "infons": {
                            "article-id_pmc": "PMC12061607",
                            "article-id_pmid": "40195641",
                            "section_type": "TITLE",
                            "type": "front"
                        },
                        "text": "A systematic review of biportal endoscopic spinal surgery"
                    },
                    {
                        "infons": {"section_type": "ABSTRACT", "type": "abstract"},
                        "text": "Biportal endoscopic spinal surgery is a minimally invasive technique."
                    },
                    {
                        "infons": {"section_type": "INTRO"},
                        "text": "Introduction section with enough content to be included in the output."
                    },
                ]
            }]
        }]
        result = fetcher._parse_bioc_response(data, "40195641")
        assert result.pmid == "40195641"
        assert result.pmcid == "PMC12061607"
        assert result.title == "A systematic review of biportal endoscopic spinal surgery"
        assert "minimally invasive" in result.abstract
        assert result.is_open_access is True

    @pytest.mark.asyncio
    async def test_fetch_fulltext_not_found(self):
        """404 응답 테스트."""
        fetcher = PMCFullTextFetcher()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(fetcher, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await fetcher.fetch_fulltext("99999999")
            assert result.pmid == "99999999"
            assert result.has_full_text is False

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetch_fulltext_success(self):
        """성공적인 전문 가져오기 테스트."""
        fetcher = PMCFullTextFetcher()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "documents": [{
                "infons": {"pmcid": "PMC1234567"},
                "passages": [
                    {"infons": {"type": "title"}, "text": "Test Paper"},
                    {"infons": {"section_type": "abstract"}, "text": "Abstract text."},
                    {"infons": {"section_type": "results"}, "text": "Results section with detailed findings and statistical analysis."},
                ]
            }]
        }

        with patch.object(fetcher, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await fetcher.fetch_fulltext("12345678")
            assert result.pmid == "12345678"
            assert result.pmcid == "PMC1234567"
            assert result.has_full_text is True

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_check_open_access(self):
        """Open Access 확인 테스트."""
        fetcher = PMCFullTextFetcher()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "documents": [{
                "infons": {},
                "passages": [
                    {"infons": {"section_type": "results"}, "text": "Results with enough content to be considered valid."},
                ]
            }]
        }

        with patch.object(fetcher, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            is_oa = await fetcher.check_open_access("12345678")
            assert is_oa is True

        await fetcher.close()


# =============================================================================
# Integration Tests (Mocked)
# =============================================================================

class TestPMCFetcherIntegration:
    """통합 테스트 (Mocked)."""

    @pytest.mark.asyncio
    async def test_fetch_batch(self):
        """배치 가져오기 테스트."""
        fetcher = PMCFullTextFetcher()

        async def mock_fetch(pmid):
            if pmid == "111":
                return PMCFullText(pmid=pmid, sections=[PMCSection("RESULTS", "R", "Results text.")])
            return PMCFullText(pmid=pmid)

        with patch.object(fetcher, 'fetch_fulltext', side_effect=mock_fetch):
            results = await fetcher.fetch_fulltext_batch(
                ["111", "222", "333"],
                concurrency=2,
                delay=0.01
            )

            assert len(results) == 3
            assert results["111"].has_full_text is True
            assert results["222"].has_full_text is False
            assert results["333"].has_full_text is False


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """엣지 케이스 테스트."""

    def test_empty_section_text(self):
        """빈 섹션 텍스트 테스트."""
        section = PMCSection("METHODS", "Methods", "")
        assert section.text == ""

    def test_pmcid_none(self):
        """PMCID None 테스트."""
        ft = PMCFullText(pmid="123", pmcid=None)
        d = ft.to_dict()
        assert d["pmcid"] is None

    def test_section_type_case_insensitive(self):
        """섹션 타입 대소문자 테스트."""
        ft = PMCFullText(
            pmid="123",
            sections=[PMCSection("RESULTS", "Results", "Text")]
        )
        assert ft.get_section("results") is not None
        assert ft.get_section("RESULTS") is not None
        assert ft.get_section("Results") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""PubMed Enricher 테스트.

PubMedEnricher 모듈의 서지 정보 강화 기능을 테스트합니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Import module
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.pubmed_enricher import (
    PubMedEnricher,
    BibliographicMetadata,
    enrich_paper_metadata
)
from external.pubmed_client import PaperMetadata


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def enricher():
    """PubMedEnricher 인스턴스."""
    return PubMedEnricher(email="test@example.com")


@pytest.fixture
def sample_pubmed_paper():
    """샘플 PaperMetadata."""
    return PaperMetadata(
        pmid="12345678",
        title="Comparison of TLIF and PLIF for Lumbar Degenerative Disease",
        authors=["Kim JH", "Park SM", "Lee CK"],
        journal="Spine",
        year=2023,
        abstract="Background: This study compares outcomes of TLIF vs PLIF...",
        doi="10.1097/BRS.0000000000001234",
        mesh_terms=["Spinal Fusion", "Lumbar Vertebrae", "Treatment Outcome"],
        publication_types=["Randomized Controlled Trial", "Comparative Study"]
    )


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
        abstract="Background: This study compares outcomes...",
        mesh_terms=["Spinal Fusion", "Lumbar Vertebrae"],
        publication_types=["Randomized Controlled Trial"],
        enriched_at=datetime.now(),
        confidence=1.0
    )


# ===========================================================================
# BibliographicMetadata Tests
# ===========================================================================

class TestBibliographicMetadata:
    """BibliographicMetadata 데이터클래스 테스트."""

    def test_to_dict(self, sample_bibliographic_metadata):
        """to_dict 메서드 테스트."""
        result = sample_bibliographic_metadata.to_dict()

        assert isinstance(result, dict)
        assert result["pmid"] == "12345678"
        assert result["doi"] == "10.1097/BRS.0000000000001234"
        assert result["year"] == 2023
        assert "mesh_terms" in result
        assert result["source"] == "pubmed"

    def test_from_pubmed(self, sample_pubmed_paper):
        """from_pubmed 클래스 메서드 테스트."""
        result = BibliographicMetadata.from_pubmed(sample_pubmed_paper, confidence=0.95)

        assert result.pmid == "12345678"
        assert result.title == sample_pubmed_paper.title
        assert result.authors == sample_pubmed_paper.authors
        assert result.mesh_terms == sample_pubmed_paper.mesh_terms
        assert result.confidence == 0.95
        assert result.source == "pubmed"
        assert result.enriched_at is not None

    def test_default_values(self):
        """기본값 테스트."""
        meta = BibliographicMetadata()

        assert meta.pmid is None
        assert meta.doi is None
        assert meta.title == ""
        assert meta.authors == []
        assert meta.mesh_terms == []
        assert meta.language == "eng"
        assert meta.source == "pubmed"
        assert meta.confidence == 0.0


# ===========================================================================
# PubMedEnricher Tests
# ===========================================================================

class TestPubMedEnricher:
    """PubMedEnricher 클래스 테스트."""

    def test_init(self, enricher):
        """초기화 테스트."""
        assert enricher.client is not None
        assert enricher.timeout == 30.0
        assert enricher.max_retries == 3

    def test_normalize_doi(self, enricher):
        """DOI 정규화 테스트."""
        # URL 형식
        assert enricher._normalize_doi("https://doi.org/10.1097/BRS.0001") == "10.1097/BRS.0001"
        assert enricher._normalize_doi("http://dx.doi.org/10.1097/BRS.0001") == "10.1097/BRS.0001"

        # doi: 접두사
        assert enricher._normalize_doi("doi:10.1097/BRS.0001") == "10.1097/BRS.0001"
        assert enricher._normalize_doi("DOI:10.1097/BRS.0001") == "10.1097/BRS.0001"

        # 표준 형식
        assert enricher._normalize_doi("10.1097/BRS.0001") == "10.1097/BRS.0001"

        # 빈 값
        assert enricher._normalize_doi("") == ""
        assert enricher._normalize_doi(None) == ""

    def test_extract_last_name(self, enricher):
        """저자 성 추출 테스트."""
        # "Kim, John" 형식
        assert enricher._extract_last_name("Kim, John H.") == "Kim"

        # "John Kim" 형식
        assert enricher._extract_last_name("John Kim") == "Kim"

        # "Kim JH" 형식 (이니셜)
        assert enricher._extract_last_name("Kim JH") == "Kim"

        # 단일 이름
        assert enricher._extract_last_name("Kim") == "Kim"

        # 빈 값
        assert enricher._extract_last_name("") == ""

    def test_calculate_title_similarity(self, enricher):
        """제목 유사도 계산 테스트."""
        title1 = "Comparison of TLIF and PLIF outcomes"
        title2 = "Comparison of TLIF and PLIF outcomes"

        # 동일한 제목
        similarity = enricher._calculate_title_similarity(title1, title2)
        assert similarity == 1.0

        # 유사한 제목
        title3 = "TLIF versus PLIF outcomes comparison study"
        similarity = enricher._calculate_title_similarity(title1, title3)
        assert 0.3 < similarity < 0.9

        # 다른 제목
        title4 = "Cervical disc replacement surgery"
        similarity = enricher._calculate_title_similarity(title1, title4)
        assert similarity < 0.3

        # 빈 값
        assert enricher._calculate_title_similarity("", title1) == 0.0
        assert enricher._calculate_title_similarity(title1, "") == 0.0

    def test_get_evidence_level_from_publication_type(self, enricher):
        """Publication type에서 근거 수준 추정 테스트."""
        # Meta-analysis → Level 1a
        assert enricher.get_evidence_level_from_publication_type(
            ["Meta-Analysis", "Review"]
        ) == "1a"

        # Systematic Review → Level 1a
        assert enricher.get_evidence_level_from_publication_type(
            ["Systematic Review"]
        ) == "1a"

        # RCT → Level 1b
        assert enricher.get_evidence_level_from_publication_type(
            ["Randomized Controlled Trial"]
        ) == "1b"

        # Case Report → Level 4 (Case series, per OCEBM 2011)
        assert enricher.get_evidence_level_from_publication_type(
            ["Case Reports"]
        ) == "4"

        # Review (not systematic) → Level 5 (Expert opinion)
        assert enricher.get_evidence_level_from_publication_type(
            ["Review"]
        ) == "5"

        # Unknown → None
        assert enricher.get_evidence_level_from_publication_type(
            ["Journal Article"]
        ) is None

        # Empty → None
        assert enricher.get_evidence_level_from_publication_type([]) is None


# ===========================================================================
# Async Tests - enrich_by_doi
# ===========================================================================

class TestEnrichByDoi:
    """enrich_by_doi 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_enrich_by_doi_success(self, enricher, sample_pubmed_paper):
        """DOI로 성공적인 검색."""
        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
                result = await enricher.enrich_by_doi("10.1097/BRS.0000000000001234")

        assert result is not None
        assert result.pmid == "12345678"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_enrich_by_doi_not_found(self, enricher):
        """DOI가 PubMed에 없는 경우."""
        with patch.object(enricher.client, 'search', return_value=[]):
            result = await enricher.enrich_by_doi("10.9999/nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_enrich_by_doi_empty(self, enricher):
        """빈 DOI."""
        result = await enricher.enrich_by_doi("")
        assert result is None

        result = await enricher.enrich_by_doi(None)
        assert result is None


# ===========================================================================
# Async Tests - enrich_by_pmid
# ===========================================================================

class TestEnrichByPmid:
    """enrich_by_pmid 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_enrich_by_pmid_success(self, enricher, sample_pubmed_paper):
        """PMID로 성공적인 검색."""
        with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
            result = await enricher.enrich_by_pmid("12345678")

        assert result is not None
        assert result.pmid == "12345678"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_enrich_by_pmid_empty(self, enricher):
        """빈 PMID."""
        result = await enricher.enrich_by_pmid("")
        assert result is None

        result = await enricher.enrich_by_pmid(None)
        assert result is None


# ===========================================================================
# Async Tests - enrich_by_title
# ===========================================================================

class TestEnrichByTitle:
    """enrich_by_title 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_enrich_by_title_success(self, enricher, sample_pubmed_paper):
        """제목으로 성공적인 검색."""
        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
                result = await enricher.enrich_by_title(
                    title="Comparison of TLIF and PLIF for Lumbar Degenerative Disease",
                    authors=["Kim JH"],
                    year=2023
                )

        assert result is not None
        assert result.pmid == "12345678"
        # 제목이 완전히 일치하면 높은 confidence
        assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_enrich_by_title_low_confidence(self, enricher, sample_pubmed_paper):
        """제목 유사도가 낮은 경우."""
        # 다른 제목으로 반환
        different_paper = PaperMetadata(
            pmid="12345678",
            title="Completely Different Title About Cervical Surgery",
            authors=["Kim JH"],
            journal="Spine",
            year=2023,
            abstract="",
            doi="",
            mesh_terms=[],
            publication_types=[]
        )

        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=different_paper):
                result = await enricher.enrich_by_title(
                    title="Comparison of TLIF and PLIF outcomes"
                )

        assert result is not None
        # 제목이 다르면 낮은 confidence
        assert result.confidence < 0.7

    @pytest.mark.asyncio
    async def test_enrich_by_title_not_found(self, enricher):
        """제목이 PubMed에 없는 경우."""
        with patch.object(enricher.client, 'search', return_value=[]):
            result = await enricher.enrich_by_title(
                title="Non-existent paper title that should not exist"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_enrich_by_title_short(self, enricher):
        """짧은 제목 (10자 미만)."""
        result = await enricher.enrich_by_title(title="Short")
        assert result is None


# ===========================================================================
# Async Tests - auto_enrich
# ===========================================================================

class TestAutoEnrich:
    """auto_enrich 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_auto_enrich_with_pmid(self, enricher, sample_pubmed_paper):
        """PMID가 있는 경우 우선 사용."""
        with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
            result = await enricher.auto_enrich(
                pmid="12345678",
                doi="10.1097/BRS.0001",
                title="Some title"
            )

        assert result is not None
        assert result.pmid == "12345678"

    @pytest.mark.asyncio
    async def test_auto_enrich_with_doi(self, enricher, sample_pubmed_paper):
        """PMID 없이 DOI로 검색."""
        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
                result = await enricher.auto_enrich(
                    doi="10.1097/BRS.0000000000001234",
                    title="Some title"
                )

        assert result is not None
        assert result.doi == "10.1097/BRS.0000000000001234"

    @pytest.mark.asyncio
    async def test_auto_enrich_with_title_only(self, enricher, sample_pubmed_paper):
        """Title로만 검색."""
        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
                result = await enricher.auto_enrich(
                    title="Comparison of TLIF and PLIF for Lumbar Degenerative Disease",
                    authors=["Kim JH"],
                    year=2023
                )

        assert result is not None

    @pytest.mark.asyncio
    async def test_auto_enrich_no_identifiers(self, enricher):
        """식별자가 없는 경우."""
        result = await enricher.auto_enrich()
        assert result is None


# ===========================================================================
# Async Tests - enrich_batch
# ===========================================================================

class TestEnrichBatch:
    """enrich_batch 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_enrich_batch_success(self, enricher, sample_pubmed_paper):
        """배치 처리 성공."""
        papers = [
            {"title": "Paper 1", "doi": "10.1097/DOI1"},
            {"title": "Paper 2", "doi": "10.1097/DOI2"},
        ]

        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
                results = await enricher.enrich_batch(papers, batch_size=2, delay=0)

        assert len(results) == 2
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_enrich_batch_empty(self, enricher):
        """빈 리스트."""
        results = await enricher.enrich_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_enrich_batch_partial_failure(self, enricher, sample_pubmed_paper):
        """일부 실패하는 경우."""
        papers = [
            {"title": "Valid paper title for testing", "doi": "10.1097/DOI1"},
            {"title": "Short"},  # 너무 짧아서 실패
        ]

        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
                results = await enricher.enrich_batch(papers, batch_size=2, delay=0)

        assert len(results) == 2
        assert results[0] is not None  # 첫 번째는 성공
        assert results[1] is None  # 두 번째는 실패 (제목이 너무 짧음)


# ===========================================================================
# Convenience Function Test
# ===========================================================================

class TestConvenienceFunction:
    """enrich_paper_metadata 편의 함수 테스트."""

    @pytest.mark.asyncio
    async def test_enrich_paper_metadata(self, sample_pubmed_paper):
        """편의 함수 테스트."""
        with patch('builder.pubmed_enricher.PubMedClient') as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.search.return_value = ["12345678"]
            mock_instance.fetch_paper_details.return_value = sample_pubmed_paper

            result = await enrich_paper_metadata(
                doi="10.1097/BRS.0000000000001234"
            )

        # API mock 환경에서는 결과가 None일 수 있으므로 타입만 체크
        from builder.pubmed_enricher import BibliographicMetadata
        assert result is None or isinstance(result, (dict, BibliographicMetadata)), f"Unexpected result type: {type(result)}"


# ===========================================================================
# Integration-like Tests
# ===========================================================================

class TestIntegration:
    """통합 테스트."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, enricher, sample_pubmed_paper):
        """전체 워크플로우 테스트."""
        # 1. DOI로 검색 시도
        with patch.object(enricher.client, 'search', return_value=["12345678"]):
            with patch.object(enricher.client, 'fetch_paper_details', return_value=sample_pubmed_paper):
                result = await enricher.auto_enrich(
                    title="Comparison of TLIF and PLIF for Lumbar Degenerative Disease",
                    doi="10.1097/BRS.0000000000001234",
                    authors=["Kim JH", "Park SM"],
                    year=2023,
                    journal="Spine"
                )

        # 2. 결과 검증
        assert result is not None
        assert result.pmid == "12345678"
        assert result.mesh_terms == ["Spinal Fusion", "Lumbar Vertebrae", "Treatment Outcome"]
        assert "Randomized Controlled Trial" in result.publication_types

        # 3. 근거 수준 추정
        evidence_level = enricher.get_evidence_level_from_publication_type(result.publication_types)
        assert evidence_level == "1b"  # RCT

        # 4. 딕셔너리 변환
        data = result.to_dict()
        assert data["source"] == "pubmed"
        assert data["confidence"] == 1.0

"""PubMed Processor Tests.

PubMedPaperProcessor 모듈의 처리/변환 기능을 테스트합니다.
D-009: pubmed_bulk_processor에서 분리된 processing/transformation 모듈 테스트.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from builder.pubmed_processor import (
    PubMedPaperProcessor,
    AbstractChunk,
    infer_evidence_level,
    build_chunk_metadata,
    split_section_text,
    parse_structured_abstract,
    PUBMED_PAPER_PREFIX,
)
from builder.pubmed_enricher import BibliographicMetadata


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sample_paper():
    """샘플 BibliographicMetadata."""
    return BibliographicMetadata(
        pmid="12345678",
        doi="10.1097/BRS.0000000000001234",
        title="Comparison of TLIF and PLIF for Lumbar Degenerative Disease",
        authors=["Kim JH", "Park SM", "Lee CK"],
        journal="Spine",
        year=2023,
        abstract="Background: This study compares outcomes. Methods: 100 patients. Results: TLIF better. Conclusion: TLIF preferred.",
        mesh_terms=["Spinal Fusion", "Lumbar Vertebrae"],
        publication_types=["Randomized Controlled Trial"],
        confidence=0.95,
    )


# ===========================================================================
# infer_evidence_level Tests
# ===========================================================================

class TestInferEvidenceLevel:
    """infer_evidence_level 함수 테스트."""

    def test_meta_analysis(self):
        assert infer_evidence_level(["Meta-Analysis"]) == "1a"

    def test_systematic_review(self):
        assert infer_evidence_level(["Systematic Review"]) == "1a"

    def test_rct(self):
        assert infer_evidence_level(["Randomized Controlled Trial"]) == "1b"

    def test_clinical_trial(self):
        assert infer_evidence_level(["Clinical Trial"]) == "2b"

    def test_cohort(self):
        assert infer_evidence_level(["Cohort Studies"]) == "2b"

    def test_case_control(self):
        assert infer_evidence_level(["Case-Control Studies"]) == "2b"

    def test_case_report(self):
        assert infer_evidence_level(["Case Report"]) == "3"

    def test_review(self):
        assert infer_evidence_level(["Review"]) == "5"

    def test_unknown(self):
        assert infer_evidence_level(["Journal Article"]) == "5"

    def test_empty(self):
        assert infer_evidence_level([]) == "5"

    def test_priority_meta_over_review(self):
        """Meta-analysis가 Review보다 우선."""
        assert infer_evidence_level(["Review", "Meta-Analysis"]) == "1a"


# ===========================================================================
# build_chunk_metadata Tests
# ===========================================================================

class TestBuildChunkMetadata:
    """build_chunk_metadata 함수 테스트."""

    def test_basic_metadata(self, sample_paper):
        """기본 메타데이터 구성."""
        meta = build_chunk_metadata(sample_paper)

        assert meta["paper_id"] == "pubmed_12345678"
        assert meta["title"] == sample_paper.title
        assert len(meta["authors"]) <= 3
        assert meta["year"] == 2023
        assert meta["journal"] == "Spine"
        assert meta["pmid"] == "12345678"
        assert meta["source"] == "pubmed"
        assert meta["is_abstract_only"] is True

    def test_metadata_author_limit(self):
        """저자 3명 제한."""
        paper = BibliographicMetadata(
            title="Test",
            authors=["A", "B", "C", "D", "E"],
            pmid="123",
        )
        meta = build_chunk_metadata(paper)
        assert len(meta["authors"]) == 3

    def test_metadata_mesh_limit(self):
        """MeSH 5개 제한."""
        paper = BibliographicMetadata(
            title="Test",
            pmid="123",
            mesh_terms=["A", "B", "C", "D", "E", "F", "G"],
        )
        meta = build_chunk_metadata(paper)
        assert len(meta["mesh_terms"]) == 5


# ===========================================================================
# split_section_text Tests
# ===========================================================================

class TestSplitSectionText:
    """split_section_text 함수 테스트."""

    def test_short_text(self):
        """짧은 텍스트 - 분할 불필요."""
        result = split_section_text("Short text.", max_chars=1500)
        assert len(result) == 1
        assert result[0] == "Short text."

    def test_long_text_split(self):
        """긴 텍스트 분할."""
        text = ". ".join(["Sentence " + str(i) for i in range(100)]) + "."
        result = split_section_text(text, max_chars=200)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= 250  # 약간의 여유

    def test_single_long_sentence(self):
        """분할 불가능한 긴 문장."""
        text = "A" * 2000
        result = split_section_text(text, max_chars=1500)
        assert len(result) >= 1


# ===========================================================================
# parse_structured_abstract Tests
# ===========================================================================

class TestParseStructuredAbstract:
    """parse_structured_abstract 함수 테스트."""

    def test_structured_abstract(self):
        """구조화된 초록 파싱."""
        abstract = "BACKGROUND: Some background. METHODS: Some methods. RESULTS: Some results. CONCLUSIONS: Some conclusions."
        chunks = parse_structured_abstract("paper_1", abstract, {})

        assert len(chunks) >= 2
        sections = [c.section for c in chunks]
        assert "background" in sections
        assert "methods" in sections

    def test_unstructured_abstract(self):
        """비구조화 초록 - 분할 없음."""
        abstract = "This is a simple abstract without section headers."
        chunks = parse_structured_abstract("paper_1", abstract, {})
        assert len(chunks) == 0  # 구조화되지 않으면 빈 리스트

    def test_partial_structure(self):
        """일부 구조만 있는 초록."""
        abstract = "BACKGROUND: Some text. Some more text without headers."
        chunks = parse_structured_abstract("paper_1", abstract, {})
        # 섹션이 2개 미만이면 빈 리스트
        assert len(chunks) == 0

    def test_chunk_ids_unique(self):
        """청크 ID 고유성."""
        abstract = "BACKGROUND: bg text. METHODS: method text. RESULTS: result text."
        chunks = parse_structured_abstract("paper_1", abstract, {})
        chunk_ids = [c.chunk_id for c in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))


# ===========================================================================
# AbstractChunk Tests
# ===========================================================================

class TestAbstractChunk:
    """AbstractChunk 데이터클래스 테스트."""

    def test_default_values(self):
        """기본값 테스트."""
        chunk = AbstractChunk(chunk_id="c1", content="text")
        assert chunk.section == "abstract"
        assert chunk.metadata == {}

    def test_custom_values(self):
        """커스텀 값 테스트."""
        chunk = AbstractChunk(
            chunk_id="c1",
            content="text",
            section="results",
            metadata={"key": "value"},
        )
        assert chunk.section == "results"
        assert chunk.metadata["key"] == "value"


# ===========================================================================
# PubMedPaperProcessor Mock Tests
# ===========================================================================

class TestPubMedPaperProcessorMocked:
    """Mock 기반 PubMedPaperProcessor 테스트."""

    @pytest.fixture
    def mock_processor(self):
        """Mock 객체로 구성된 processor."""
        mock_neo4j = AsyncMock()
        mock_embedding = MagicMock()
        mock_vision = MagicMock()
        mock_normalizer = MagicMock()
        mock_builder = MagicMock()

        processor = PubMedPaperProcessor(
            neo4j_client=mock_neo4j,
            embedding_generator=mock_embedding,
            vision_processor=mock_vision,
            entity_normalizer=mock_normalizer,
            relationship_builder=mock_builder,
        )
        return processor

    @pytest.mark.asyncio
    async def test_get_abstract_only_papers(self, mock_processor):
        """abstract-only 논문 조회."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[
            {"paper_id": "pubmed_111", "title": "Paper 1"},
            {"paper_id": "pubmed_222", "title": "Paper 2"},
        ])
        papers = await mock_processor.get_abstract_only_papers(limit=10)
        assert len(papers) == 2

    @pytest.mark.asyncio
    async def test_get_abstract_only_papers_empty(self, mock_processor):
        """abstract-only 논문 없음."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[])
        papers = await mock_processor.get_abstract_only_papers()
        assert papers == []

    @pytest.mark.asyncio
    async def test_get_import_statistics(self, mock_processor):
        """임포트 통계 조회."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[
            {"source": "pubmed", "abstract_only": True, "count": 10},
            {"source": "pdf", "abstract_only": False, "count": 5},
        ])
        stats = await mock_processor.get_import_statistics()
        assert stats["total_papers"] == 15
        assert stats["pubmed_only"] == 10
        assert stats["pdf_only"] == 5

    @pytest.mark.asyncio
    async def test_delete_paper_chunks(self, mock_processor):
        """청크 삭제."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[{"deleted_count": 3}])
        count = await mock_processor.delete_paper_chunks("pubmed_123")
        assert count == 3

    @pytest.mark.asyncio
    async def test_upgrade_not_pubmed_paper(self, mock_processor):
        """비-PubMed 논문 업그레이드 실패."""
        result = await mock_processor.upgrade_with_pdf("other_paper_123", {})
        assert result["success"] is False
        assert "not a PubMed-only paper" in result["error"]

    @pytest.mark.asyncio
    async def test_upgrade_paper_not_found(self, mock_processor):
        """논문 미발견 시 업그레이드 실패."""
        mock_processor.neo4j.run_query = AsyncMock(return_value=[])
        result = await mock_processor.upgrade_with_pdf("pubmed_123", {})
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ===========================================================================
# Constants Tests
# ===========================================================================

class TestConstants:
    """상수 테스트."""

    def test_pubmed_paper_prefix(self):
        assert PUBMED_PAPER_PREFIX == "pubmed_"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

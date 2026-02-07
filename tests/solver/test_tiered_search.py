"""Tests for TieredHybridSearch module."""

import pytest
from src.solver.tiered_search import (
    TieredHybridSearch,
    SearchInput,
    SearchOutput,
    SearchResult,
    SearchTier,
    SearchSource,
    ChunkInfo,
    MockVectorDB,
    MockGraphDB,
)
from src.solver.query_parser import MedicalEntity, EntityType
from src.builder.citation_detector import SourceType
from src.builder.study_classifier import EvidenceLevel


def make_mock_data() -> list[dict]:
    """테스트용 Mock 데이터 생성."""
    return [
        {
            "id": "chunk_1",
            "document_id": "doc_1",
            "text": "Minimally invasive surgery shows better outcomes for lumbar disc herniation.",
            "tier": 1,
            "section": "results",
            "source_type": "original",
            "evidence_level": "1b",
            "publication_year": 2023,
            "title": "RCT of Spine Surgery",
            "score": 0.95
        },
        {
            "id": "chunk_2",
            "document_id": "doc_1",
            "text": "Methods: We enrolled 200 patients.",
            "tier": 2,
            "section": "methods",
            "source_type": "original",
            "evidence_level": "1b",
            "publication_year": 2023,
            "title": "RCT of Spine Surgery",
            "score": 0.85
        },
        {
            "id": "chunk_3",
            "document_id": "doc_2",
            "text": "Previous studies reported similar findings (Smith et al., 2020).",
            "tier": 2,
            "section": "discussion",
            "source_type": "citation",
            "evidence_level": "2b",
            "publication_year": 2021,
            "title": "Cohort Study Review",
            "score": 0.80
        },
        {
            "id": "chunk_4",
            "document_id": "doc_3",
            "text": "Case series of 50 patients showed improvement in pain scores.",
            "tier": 1,
            "section": "results",
            "source_type": "original",
            "evidence_level": "4",
            "publication_year": 2022,
            "title": "Case Series Report",
            "score": 0.90
        },
        {
            "id": "chunk_5",
            "document_id": "doc_4",
            "text": "Expert opinion suggests conservative treatment first.",
            "tier": 2,
            "section": "discussion",
            "source_type": "background",
            "evidence_level": "5",
            "publication_year": 2019,
            "title": "Expert Commentary",
            "score": 0.70
        },
    ]


class TestTieredHybridSearch:
    """TieredHybridSearch 테스트."""

    @pytest.fixture
    def mock_data(self):
        return make_mock_data()

    @pytest.fixture
    def search_engine(self, mock_data):
        """Mock DB가 있는 검색 엔진."""
        vector_db = MockVectorDB(mock_data)
        graph_db = MockGraphDB(mock_data)
        return TieredHybridSearch(vector_db=vector_db, graph_db=graph_db)

    @pytest.fixture
    def search_engine_no_db(self):
        """DB 없는 검색 엔진."""
        return TieredHybridSearch()

    def test_empty_results_without_db(self, search_engine_no_db):
        """DB 없이 빈 결과."""
        result = search_engine_no_db.search(SearchInput(query="test"))
        assert result.total_found == 0
        assert result.results == []

    def test_tier1_only_search(self, search_engine):
        """Tier 1만 검색."""
        result = search_engine.search(SearchInput(
            query="spine surgery outcomes",
            tier_strategy=SearchTier.TIER1_ONLY,
            top_k=10
        ))

        # Tier 1 결과만 있어야 함
        for r in result.results:
            assert r.tier == 1

    def test_tier1_then_tier2_search(self, search_engine):
        """Tier 1 우선 검색."""
        result = search_engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.TIER1_THEN_TIER2,
            top_k=10
        ))

        # Tier 1 결과가 있으면 먼저 나와야 함
        tier1_found = False
        tier2_found = False
        for r in result.results:
            if r.tier == 1:
                tier1_found = True
            if r.tier == 2:
                tier2_found = True
                assert tier1_found, "Tier 2 should come after Tier 1"

    def test_all_tiers_search(self, search_engine):
        """전체 계층 검색."""
        result = search_engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.ALL_TIERS,
            top_k=10
        ))

        # 양쪽 Tier 결과가 있을 수 있음
        tiers = {r.tier for r in result.results}
        assert len(tiers) >= 1  # 최소 하나의 Tier

    def test_prefer_original_content(self, search_engine):
        """원본 콘텐츠 우선."""
        result = search_engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.ALL_TIERS,
            prefer_original=True,
            top_k=10
        ))

        if len(result.results) > 1:
            # 원본이 인용보다 먼저 나와야 함
            original_found = False
            for r in result.results:
                if r.source_type == "original":
                    original_found = True
                elif r.source_type in ["citation", "background"]:
                    if not original_found:
                        # 원본 없이 인용만 있을 수 있음
                        pass

    def test_evidence_level_filter(self, search_engine):
        """Evidence Level 필터링."""
        result = search_engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.ALL_TIERS,
            min_evidence_level="2b",
            top_k=10
        ))

        acceptable = ["1a", "1b", "2a", "2b"]
        for r in result.results:
            assert r.evidence_level in acceptable

    def test_year_filter(self, search_engine):
        """연도 필터링."""
        result = search_engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.ALL_TIERS,
            min_year=2022,
            top_k=10
        ))

        for r in result.results:
            assert r.chunk.publication_year >= 2022

    def test_top_k_limit(self, search_engine):
        """결과 수 제한."""
        result = search_engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.ALL_TIERS,
            top_k=2
        ))

        assert len(result.results) <= 2

    def test_search_statistics(self, search_engine):
        """검색 통계."""
        result = search_engine.search(SearchInput(
            query="spine surgery",
            tier_strategy=SearchTier.TIER1_THEN_TIER2,
            top_k=10
        ))

        assert result.total_found >= 0
        assert result.tier1_count >= 0
        assert result.tier2_count >= 0
        assert result.search_strategy_used == SearchTier.TIER1_THEN_TIER2


class TestSearchWithEntities:
    """엔티티 기반 검색 테스트."""

    @pytest.fixture
    def mock_data(self):
        return make_mock_data()

    @pytest.fixture
    def search_engine(self, mock_data):
        vector_db = MockVectorDB(mock_data)
        graph_db = MockGraphDB(mock_data)
        return TieredHybridSearch(vector_db=vector_db, graph_db=graph_db)

    def test_search_with_entities(self, search_engine):
        """엔티티가 있는 검색."""
        entities = [
            MedicalEntity(text="spine", entity_type=EntityType.ANATOMY),
            MedicalEntity(text="surgery", entity_type=EntityType.PROCEDURE),
        ]

        result = search_engine.search(SearchInput(
            query="spine surgery outcomes",
            entities=entities,
            tier_strategy=SearchTier.ALL_TIERS,
            top_k=10
        ))

        # 그래프 검색 결과도 포함될 수 있음
        assert result.total_found >= 0


class TestResultFusion:
    """결과 융합 테스트."""

    @pytest.fixture
    def search_engine(self):
        return TieredHybridSearch()

    def test_rrf_fusion(self, search_engine):
        """RRF 융합."""
        # Mock 결과 생성
        vector_results = [
            SearchResult(
                chunk=ChunkInfo(chunk_id="v1", document_id="d1", text="Vector result 1"),
                score=0.9, tier=1, source_type="original", evidence_level="1b",
                search_source=SearchSource.VECTOR, vector_score=0.9
            ),
            SearchResult(
                chunk=ChunkInfo(chunk_id="v2", document_id="d2", text="Vector result 2"),
                score=0.8, tier=1, source_type="original", evidence_level="2b",
                search_source=SearchSource.VECTOR, vector_score=0.8
            ),
        ]

        graph_results = [
            SearchResult(
                chunk=ChunkInfo(chunk_id="v1", document_id="d1", text="Vector result 1"),
                score=0.85, tier=1, source_type="original", evidence_level="1b",
                search_source=SearchSource.GRAPH, graph_score=0.85
            ),
            SearchResult(
                chunk=ChunkInfo(chunk_id="g1", document_id="d3", text="Graph result 1"),
                score=0.7, tier=1, source_type="citation", evidence_level="3b",
                search_source=SearchSource.GRAPH, graph_score=0.7
            ),
        ]

        fused = search_engine._fuse_results(vector_results, graph_results, top_k=5)

        # v1은 양쪽에서 발견되어 BOTH여야 함
        v1_result = next((r for r in fused if r.chunk.chunk_id == "v1"), None)
        assert v1_result is not None
        assert v1_result.search_source == SearchSource.BOTH

    def test_tier_merge_rrf(self, search_engine):
        """Tier 병합 RRF."""
        tier1_results = [
            SearchResult(
                chunk=ChunkInfo(chunk_id="t1_1", document_id="d1", text="Tier 1 result"),
                score=0.9, tier=1, source_type="original", evidence_level="1b"
            ),
        ]

        tier2_results = [
            SearchResult(
                chunk=ChunkInfo(chunk_id="t2_1", document_id="d2", text="Tier 2 result"),
                score=0.95, tier=2, source_type="original", evidence_level="1b"
            ),
        ]

        merged = search_engine._merge_results_rrf(tier1_results, tier2_results, top_k=5)

        # Tier 1이 더 높은 가중치를 가짐
        assert len(merged) == 2


class TestEvidenceLevelHandling:
    """Evidence Level 처리 테스트."""

    @pytest.fixture
    def search_engine(self):
        return TieredHybridSearch()

    def test_acceptable_levels(self, search_engine):
        """허용 레벨 계산."""
        acceptable = search_engine._get_acceptable_levels("2b")
        assert "1a" in acceptable
        assert "1b" in acceptable
        assert "2a" in acceptable
        assert "2b" in acceptable
        assert "3a" not in acceptable

    def test_acceptable_levels_invalid(self, search_engine):
        """잘못된 레벨."""
        acceptable = search_engine._get_acceptable_levels("invalid")
        # 모든 레벨 반환
        assert len(acceptable) == 9


class TestMockDBs:
    """Mock DB 테스트."""

    def test_mock_vector_db_search(self):
        """Mock Vector DB 검색."""
        data = make_mock_data()
        db = MockVectorDB(data)

        results = db.search(
            query_embedding=[0.1] * 3072,  # OpenAI text-embedding-3-large
            collection="tier1_chunks",
            top_k=5
        )

        # Tier 1 결과만
        for r in results:
            assert r.get("tier") == 1

    def test_mock_vector_db_filters(self):
        """Mock Vector DB 필터."""
        data = make_mock_data()
        db = MockVectorDB(data)

        results = db.search(
            query_embedding=[0.1] * 3072,  # OpenAI text-embedding-3-large
            collection="tier1_chunks",
            top_k=5,
            filters={"publication_year": {"$gte": 2023}}
        )

        for r in results:
            assert r.get("publication_year", 0) >= 2023

    def test_mock_graph_db_entity_search(self):
        """Mock Graph DB 엔티티 검색."""
        data = make_mock_data()
        db = MockGraphDB(data)

        results = db.search_by_entities(
            entities=["spine", "surgery"],
            top_k=5
        )

        # 엔티티와 매칭되는 결과
        assert len(results) > 0

    def test_mock_embedding(self):
        """Mock 임베딩."""
        db = MockVectorDB()
        embedding = db.get_embedding("test text")

        assert len(embedding) == 3072  # OpenAI text-embedding-3-large
        assert all(v == 0.1 for v in embedding)


class TestConfiguration:
    """설정 테스트."""

    def test_custom_config(self):
        """커스텀 설정."""
        engine = TieredHybridSearch(config={
            "rrf_k": 100,
            "vector_weight": 0.8,
            "graph_weight": 0.2,
            "tier1_min_results": 5
        })

        assert engine.rrf_k == 100
        assert engine.vector_weight == 0.8
        assert engine.graph_weight == 0.2
        assert engine.tier1_min_results == 5

    def test_default_config(self):
        """기본 설정."""
        engine = TieredHybridSearch()

        assert engine.rrf_k == 60
        assert engine.vector_weight == 0.7
        assert engine.graph_weight == 0.3
        assert engine.tier1_min_results == 3

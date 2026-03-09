"""Unit Tests for AdaptiveHybridRanker.

쿼리 유형 분류, 가중치 조정, 점수 정규화, 결과 병합 등
모든 핵심 기능에 대한 테스트.
"""

import pytest
from dataclasses import dataclass

# Import modules to test
from src.solver.adaptive_ranker import (
    QueryType,
    QueryClassifier,
    RankedResult,
    AdaptiveHybridRanker,
    QUERY_TYPE_WEIGHTS,
)
from src.solver.graph_result import GraphEvidence, PaperNode
from src.storage import SearchResult as VectorSearchResult


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def query_classifier():
    """QueryClassifier 인스턴스."""
    return QueryClassifier()


@pytest.fixture
def adaptive_ranker():
    """AdaptiveHybridRanker 인스턴스."""
    return AdaptiveHybridRanker()


@pytest.fixture
def mock_graph_results():
    """Mock Graph 검색 결과."""
    return [
        {
            "paper_id": "paper1",
            "title": "TLIF vs OLIF for Stenosis",
            "score": 0.85,
            "evidence": GraphEvidence(
                intervention="TLIF",
                outcome="Fusion Rate",
                value="92%",
                source_paper_id="paper1",
                evidence_level="1b",
                p_value=0.001,
                is_significant=True,
                direction="improved"
            ),
            "paper": PaperNode(
                paper_id="paper1",
                title="TLIF vs OLIF for Stenosis",
                authors=["Kim", "Lee"],
                year=2024
            )
        },
        {
            "paper_id": "paper2",
            "title": "OLIF Outcomes in Degenerative Spondylolisthesis",
            "score": 0.72,
            "evidence": GraphEvidence(
                intervention="OLIF",
                outcome="VAS",
                value="2.1 points",
                source_paper_id="paper2",
                evidence_level="2a",
                p_value=0.03,
                is_significant=True,
                direction="improved"
            ),
            "paper": PaperNode(
                paper_id="paper2",
                title="OLIF Outcomes in Degenerative Spondylolisthesis",
                authors=["Park", "Choi"],
                year=2023
            )
        },
        {
            "paper_id": "paper3",
            "title": "UBE for Lumbar Stenosis",
            "score": 0.68,
            "evidence": None,
            "paper": PaperNode(
                paper_id="paper3",
                title="UBE for Lumbar Stenosis",
                authors=["Lee"],
                year=2022
            )
        }
    ]


@pytest.fixture
def mock_vector_results():
    """Mock Vector 검색 결과."""
    return [
        VectorSearchResult(
            chunk_id="chunk1",
            document_id="paper1",
            title="TLIF vs OLIF for Stenosis",
            score=0.88,
            content="TLIF showed superior fusion rate compared to OLIF...",
            tier="tier1",
            section="results",
            source_type="original",
            evidence_level="1b",
            is_key_finding=True,
            has_statistics=True,
            publication_year=2024,
            summary="TLIF superior to OLIF in fusion rate"
        ),
        VectorSearchResult(
            chunk_id="chunk2",
            document_id="paper4",
            title="Minimally Invasive Techniques for Stenosis",
            score=0.75,
            content="Various minimally invasive approaches exist...",
            tier="tier1",
            section="introduction",
            source_type="original",
            evidence_level="4",
            is_key_finding=False,
            has_statistics=False,
            publication_year=2021,
            summary="Overview of MIS techniques"
        ),
        VectorSearchResult(
            chunk_id="chunk3",
            document_id="paper2",
            title="OLIF Outcomes in Degenerative Spondylolisthesis",
            score=0.65,
            content="OLIF demonstrated significant improvement in VAS...",
            tier="tier2",
            section="discussion",
            source_type="original",
            evidence_level="2a",
            is_key_finding=True,
            has_statistics=True,
            publication_year=2023,
            summary="OLIF effective for pain reduction"
        )
    ]


# ============================================================================
# QueryClassifier Tests
# ============================================================================

class TestQueryClassifier:
    """QueryClassifier 테스트."""

    def test_factual_queries(self, query_classifier):
        """FACTUAL 쿼리 분류 테스트."""
        queries = [
            "What is the fusion rate of TLIF?",
            "What is the complication rate of OLIF?",
            "What is the value of ODI after surgery?",
            "What is the percentage of fusion in TLIF?",
        ]

        for query in queries:
            result = query_classifier.classify(query)
            assert result == QueryType.FACTUAL, f"Failed for: {query}"

    def test_comparative_queries(self, query_classifier):
        """COMPARATIVE 쿼리 분류 테스트."""
        queries = [
            "TLIF vs OLIF for stenosis",
            "Compare TLIF versus OLIF",
            "Comparison of UBE and MED",
            "What is better between TLIF and OLIF for lumbar stenosis?",
            "Difference between endoscopic and open surgery",
        ]

        for query in queries:
            result = query_classifier.classify(query)
            assert result == QueryType.COMPARATIVE, f"Failed for: {query}"

    def test_exploratory_queries(self, query_classifier):
        """EXPLORATORY 쿼리 분류 테스트."""
        queries = [
            "What treatments exist for stenosis?",
            "What are the options for degenerative disc disease?",
            "List all surgical approaches for scoliosis",
            "What are the different types of spinal fusion?",
            "What are various techniques for decompression?",
        ]

        for query in queries:
            result = query_classifier.classify(query)
            assert result == QueryType.EXPLORATORY, f"Failed for: {query}"

    def test_evidence_queries(self, query_classifier):
        """EVIDENCE 쿼리 분류 테스트."""
        queries = [
            "Is TLIF effective for disc herniation?",
            "Does UBE work for stenosis?",
            "Evidence for OLIF in spondylolisthesis",
            "Is fusion proven to reduce pain?",
            "What is the p-value for TLIF outcomes?",
        ]

        for query in queries:
            result = query_classifier.classify(query)
            assert result == QueryType.EVIDENCE, f"Failed for: {query}"

    def test_procedural_queries(self, query_classifier):
        """PROCEDURAL 쿼리 분류 테스트."""
        queries = [
            "How is UBE performed?",
            "What are the steps of TLIF?",
            "Surgical technique for OLIF",
            "How do you perform UBE?",
            "What is the method of posterior fusion?",
        ]

        for query in queries:
            result = query_classifier.classify(query)
            assert result == QueryType.PROCEDURAL, f"Failed for: {query}"

    def test_ambiguous_queries(self, query_classifier):
        """애매한 쿼리는 EXPLORATORY로 분류."""
        queries = [
            "Tell me about spine surgery",
            "Lumbar stenosis",
            "Back pain treatment",
        ]

        for query in queries:
            result = query_classifier.classify(query)
            assert result == QueryType.EXPLORATORY, f"Failed for: {query}"

    def test_priority_resolution(self, query_classifier):
        """여러 패턴 매칭 시 우선순위 해결."""
        # COMPARATIVE와 EVIDENCE 둘 다 매칭 → COMPARATIVE 우선
        query = "Is TLIF vs OLIF effective for stenosis?"
        result = query_classifier.classify(query)
        assert result == QueryType.COMPARATIVE

    def test_confidence_scores(self, query_classifier):
        """분류 신뢰도 점수 테스트."""
        query = "TLIF vs OLIF for stenosis"
        query_type = query_classifier.classify(query)
        confidence = query_classifier.get_confidence(query, query_type)

        assert 0.0 <= confidence <= 1.0
        assert confidence >= 0.7  # COMPARATIVE는 높은 신뢰도

    def test_case_insensitivity(self, query_classifier):
        """대소문자 무관하게 분류."""
        queries = [
            "what is the fusion rate of TLIF?",
            "WHAT IS THE FUSION RATE OF TLIF?",
            "What Is The Fusion Rate Of TLIF?",
        ]

        for query in queries:
            result = query_classifier.classify(query)
            assert result == QueryType.FACTUAL


# ============================================================================
# AdaptiveHybridRanker Tests
# ============================================================================

class TestAdaptiveHybridRanker:
    """AdaptiveHybridRanker 테스트."""

    def test_basic_ranking(self, adaptive_ranker, mock_graph_results, mock_vector_results):
        """기본 랭킹 테스트."""
        query = "TLIF vs OLIF for stenosis"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=mock_graph_results,
            vector_results=mock_vector_results
        )

        # 결과 존재 확인
        assert len(results) > 0

        # 점수 내림차순 정렬 확인
        for i in range(len(results) - 1):
            assert results[i].final_score >= results[i + 1].final_score

        # 쿼리 유형 확인
        assert results[0].query_type == QueryType.COMPARATIVE

    def test_query_type_weights(self, adaptive_ranker, mock_graph_results, mock_vector_results):
        """쿼리 유형별 가중치 적용 테스트."""
        queries_and_types = [
            ("What is the fusion rate?", QueryType.FACTUAL),
            ("TLIF vs OLIF", QueryType.COMPARATIVE),
            ("What treatments exist?", QueryType.EXPLORATORY),
            ("Is TLIF effective?", QueryType.EVIDENCE),
            ("How is UBE performed?", QueryType.PROCEDURAL),
        ]

        for query, expected_type in queries_and_types:
            results = adaptive_ranker.rank(
                query=query,
                graph_results=mock_graph_results,
                vector_results=mock_vector_results
            )

            # 쿼리 유형 확인
            assert results[0].query_type == expected_type

            # 가중치 확인
            expected_weights = QUERY_TYPE_WEIGHTS[expected_type]
            assert results[0].metadata["graph_weight"] == expected_weights["graph"]
            assert results[0].metadata["vector_weight"] == expected_weights["vector"]

    def test_override_weights(self, adaptive_ranker, mock_graph_results, mock_vector_results):
        """가중치 강제 지정 테스트."""
        query = "TLIF vs OLIF"
        override_weights = {"graph": 0.5, "vector": 0.5}

        results = adaptive_ranker.rank(
            query=query,
            graph_results=mock_graph_results,
            vector_results=mock_vector_results,
            override_weights=override_weights
        )

        # 강제 지정한 가중치 적용 확인
        assert results[0].metadata["graph_weight"] == 0.5
        assert results[0].metadata["vector_weight"] == 0.5

    def test_score_normalization(self, adaptive_ranker):
        """점수 정규화 테스트."""
        results = [
            {"paper_id": "p1", "score": 0.5},
            {"paper_id": "p2", "score": 0.8},
            {"paper_id": "p3", "score": 1.0},
        ]

        normalized = adaptive_ranker._normalize_scores(results, score_key="score")

        # Min-Max 정규화 확인: (score - min) / (max - min)
        # Min = 0.5, Max = 1.0, Range = 0.5
        assert abs(normalized[0]["score"] - 0.0) < 0.01  # (0.5 - 0.5) / 0.5 = 0.0
        assert abs(normalized[1]["score"] - 0.6) < 0.01  # (0.8 - 0.5) / 0.5 = 0.6
        assert abs(normalized[2]["score"] - 1.0) < 0.01  # (1.0 - 0.5) / 0.5 = 1.0

    def test_score_normalization_edge_cases(self, adaptive_ranker):
        """점수 정규화 엣지 케이스 테스트."""
        # 모든 점수가 같은 경우
        results = [
            {"paper_id": "p1", "score": 0.7},
            {"paper_id": "p2", "score": 0.7},
        ]

        normalized = adaptive_ranker._normalize_scores(results, score_key="score")
        assert all(r["score"] == 1.0 for r in normalized)

        # 빈 리스트
        normalized = adaptive_ranker._normalize_scores([], score_key="score")
        assert normalized == []

    def test_deduplication(self, adaptive_ranker, mock_graph_results, mock_vector_results):
        """중복 제거 테스트 (같은 paper_id 병합)."""
        query = "TLIF vs OLIF"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=mock_graph_results,
            vector_results=mock_vector_results
        )

        # paper_id 중복 없음 확인
        paper_ids = [r.paper_id for r in results]
        assert len(paper_ids) == len(set(paper_ids))

    def test_graph_only_results(self, adaptive_ranker, mock_graph_results):
        """Graph 결과만 있는 경우."""
        query = "TLIF vs OLIF"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=mock_graph_results,
            vector_results=[]
        )

        # Graph 결과만 반환
        assert len(results) == len(mock_graph_results)
        # 점수 정규화로 인해 0이 될 수 있으므로 final_score만 확인
        assert all(r.final_score >= 0 for r in results)
        assert all(r.vector_score == 0 for r in results)

    def test_vector_only_results(self, adaptive_ranker, mock_vector_results):
        """Vector 결과만 있는 경우."""
        query = "What treatments exist?"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=[],
            vector_results=mock_vector_results
        )

        # Vector 결과만 반환
        assert len(results) == len(mock_vector_results)
        assert all(r.graph_score == 0 for r in results)
        # 점수 정규화로 인해 0이 될 수 있으므로 final_score만 확인
        assert all(r.final_score >= 0 for r in results)

    def test_empty_results(self, adaptive_ranker):
        """빈 결과 처리."""
        query = "test query"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=[],
            vector_results=[]
        )

        assert results == []

    def test_comparative_query_graph_preference(
        self, adaptive_ranker, mock_graph_results, mock_vector_results
    ):
        """COMPARATIVE 쿼리는 Graph 선호 (80%)."""
        query = "TLIF vs OLIF for stenosis"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=mock_graph_results,
            vector_results=mock_vector_results
        )

        # Graph 가중치 80% 확인
        assert results[0].metadata["graph_weight"] == 0.8
        assert results[0].metadata["vector_weight"] == 0.2

    def test_exploratory_query_vector_preference(
        self, adaptive_ranker, mock_graph_results, mock_vector_results
    ):
        """EXPLORATORY 쿼리는 Vector 선호 (60%)."""
        query = "What treatments exist for stenosis?"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=mock_graph_results,
            vector_results=mock_vector_results
        )

        # Vector 가중치 60% 확인
        assert results[0].metadata["graph_weight"] == 0.4
        assert results[0].metadata["vector_weight"] == 0.6


# ============================================================================
# RankedResult Tests
# ============================================================================

class TestRankedResult:
    """RankedResult 테스트."""

    def test_display_text_with_evidence(self):
        """Evidence가 있는 경우 display text."""
        evidence = GraphEvidence(
            intervention="TLIF",
            outcome="Fusion Rate",
            value="92%",
            source_paper_id="paper1",
            p_value=0.001,
            is_significant=True,
            direction="improved"
        )

        result = RankedResult(
            paper_id="paper1",
            title="TLIF Study",
            graph_score=0.9,
            vector_score=0.8,
            final_score=0.86,
            query_type=QueryType.COMPARATIVE,
            evidence=evidence
        )

        display_text = result.get_display_text()
        assert "TLIF" in display_text
        assert "improved" in display_text
        assert "Fusion Rate" in display_text

    def test_score_breakdown(self):
        """점수 분석 문자열."""
        result = RankedResult(
            paper_id="paper1",
            title="Test Paper",
            graph_score=0.85,
            vector_score=0.75,
            final_score=0.81,
            query_type=QueryType.EVIDENCE
        )

        breakdown = result.get_score_breakdown()
        assert "0.81" in breakdown  # final_score
        assert "0.85" in breakdown  # graph_score
        assert "0.75" in breakdown  # vector_score

    def test_optional_fields(self):
        """선택적 필드 처리."""
        result = RankedResult(
            paper_id="paper1",
            title="Test Paper",
            graph_score=0.5,
            vector_score=0.5,
            final_score=0.5,
            query_type=QueryType.FACTUAL
        )

        # None 필드 확인
        assert result.evidence is None
        assert result.paper is None
        assert result.vector_result is None

        # display_text에서 에러 없이 처리
        display_text = result.get_display_text()
        assert "Test Paper" in display_text


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """통합 테스트."""

    def test_end_to_end_ranking_workflow(
        self, adaptive_ranker, mock_graph_results, mock_vector_results
    ):
        """전체 랭킹 워크플로우 테스트."""
        queries = [
            ("What is the fusion rate of TLIF?", QueryType.FACTUAL),
            ("TLIF vs OLIF for stenosis", QueryType.COMPARATIVE),
            ("What treatments exist for stenosis?", QueryType.EXPLORATORY),
        ]

        for query, expected_type in queries:
            results = adaptive_ranker.rank(
                query=query,
                graph_results=mock_graph_results,
                vector_results=mock_vector_results
            )

            # 기본 검증
            assert len(results) > 0
            assert results[0].query_type == expected_type

            # 점수 범위 검증
            for result in results:
                assert 0.0 <= result.final_score <= 1.0
                assert 0.0 <= result.graph_score <= 1.0
                assert 0.0 <= result.vector_score <= 1.0

            # 정렬 검증
            scores = [r.final_score for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_real_world_query_patterns(self, adaptive_ranker):
        """실제 쿼리 패턴 테스트."""
        real_queries = [
            "What is the complication rate of OLIF in elderly patients?",
            "Compare fusion rates between TLIF and PLIF",
            "How do you perform UBE for lumbar stenosis?",
            "Is there evidence that UBE reduces blood loss?",
            "What are the surgical options for adult spinal deformity?",
        ]

        # Mock 데이터
        graph_results = [
            {
                "paper_id": f"paper{i}",
                "title": f"Study {i}",
                "score": 0.7 + i * 0.05,
            }
            for i in range(3)
        ]

        vector_results = [
            VectorSearchResult(
                chunk_id=f"chunk{i}",
                document_id=f"paper{i}",
                title=f"Study {i}",
                score=0.6 + i * 0.05,
                content="Study content",
                tier="tier1",
                section="results",
                source_type="original",
                evidence_level="2a",
                is_key_finding=True,
                has_statistics=True,
                publication_year=2024,
                summary="Study summary"
            )
            for i in range(3)
        ]

        for query in real_queries:
            results = adaptive_ranker.rank(
                query=query,
                graph_results=graph_results,
                vector_results=vector_results
            )

            # 결과 생성 확인
            assert len(results) > 0

            # 유효한 QueryType 확인
            assert results[0].query_type in list(QueryType)


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """성능 테스트."""

    def test_large_result_set_handling(self, adaptive_ranker):
        """대용량 결과 처리 테스트."""
        # 100개 Graph 결과
        graph_results = [
            {
                "paper_id": f"paper{i}",
                "title": f"Study {i}",
                "score": 0.5 + (i % 50) * 0.01,
            }
            for i in range(100)
        ]

        # 100개 Vector 결과
        vector_results = [
            VectorSearchResult(
                chunk_id=f"chunk{i}",
                document_id=f"paper{i}",
                title=f"Study {i}",
                score=0.6 + (i % 40) * 0.01,
                content="Content",
                tier="tier1",
                section="results",
                source_type="original",
                evidence_level="2a",
                is_key_finding=True,
                has_statistics=True,
                publication_year=2024,
                summary="Summary"
            )
            for i in range(100)
        ]

        query = "What is the fusion rate?"

        results = adaptive_ranker.rank(
            query=query,
            graph_results=graph_results,
            vector_results=vector_results
        )

        # 성능 확인 (100개 처리 후에도 정상 동작)
        assert len(results) <= 100  # 중복 제거 후
        assert all(0.0 <= r.final_score <= 1.0 for r in results)

    def test_query_classification_performance(self, query_classifier):
        """쿼리 분류 성능 테스트."""
        queries = [
            "What is the fusion rate?",
            "TLIF vs OLIF",
            "What treatments exist?",
        ] * 100  # 300개 쿼리

        for query in queries:
            result = query_classifier.classify(query)
            assert result in list(QueryType)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

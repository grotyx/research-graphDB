"""Tests for Unified Search Pipeline.

통합 검색 파이프라인 테스트:
- Pipeline 초기화
- Query classification
- Hybrid search
- Evidence synthesis
- Conflict detection
- End-to-end integration
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.solver.unified_pipeline import (
    UnifiedSearchPipeline,
    SearchOptions,
    SearchResponse,
    QueryAnalysis,
    create_pipeline,
    quick_search,
)
from src.solver.adaptive_ranker import QueryType, RankedResult
from src.solver.evidence_synthesizer import SynthesisResult, EvidenceStrength
from src.solver.conflict_detector import ConflictResult, ConflictSeverity
from core.exceptions import ValidationError


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client."""
    client = Mock()
    client.run_query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def pipeline(mock_neo4j_client):
    """UnifiedSearchPipeline 인스턴스."""
    return UnifiedSearchPipeline(mock_neo4j_client)


@pytest.fixture
def sample_ranked_results():
    """샘플 랭킹 결과."""
    return [
        RankedResult(
            paper_id="paper1",
            title="TLIF vs OLIF for Lumbar Stenosis",
            graph_score=0.85,
            vector_score=0.75,
            final_score=0.82,
            query_type=QueryType.COMPARATIVE
        ),
        RankedResult(
            paper_id="paper2",
            title="Fusion Rate after TLIF Surgery",
            graph_score=0.70,
            vector_score=0.80,
            final_score=0.74,
            query_type=QueryType.FACTUAL
        ),
    ]


@pytest.fixture
def sample_synthesis():
    """샘플 근거 종합 결과."""
    return SynthesisResult(
        intervention="TLIF",
        outcome="Fusion Rate",
        direction="improved",
        strength=EvidenceStrength.STRONG,
        paper_count=5,
        supporting_papers=["paper1", "paper2", "paper3"],
        opposing_papers=[],
        effect_summary="Fusion Rate improved by 92.5 ± 3.2%",
        heterogeneity="low",
        grade_rating="A",
        recommendation="TLIF is STRONGLY RECOMMENDED for improving Fusion Rate (GRADE A)."
    )


@pytest.fixture
def sample_conflict():
    """샘플 충돌 결과."""
    return ConflictResult(
        intervention="TLIF",
        outcome="VAS",
        severity=ConflictSeverity.HIGH,
        confidence=0.85,
        summary="Conflicting evidence detected..."
    )


# =============================================================================
# Test Pipeline Initialization
# =============================================================================

def test_pipeline_initialization_with_clients(mock_neo4j_client):
    """Neo4j로 초기화."""
    pipeline = UnifiedSearchPipeline(mock_neo4j_client)

    assert pipeline.neo4j_client is not None
    assert pipeline.query_classifier is not None
    assert pipeline.adaptive_ranker is not None
    assert pipeline.hybrid_ranker is not None
    assert pipeline.evidence_synthesizer is not None
    assert pipeline.conflict_detector is not None


def test_pipeline_initialization_without_neo4j():
    """Neo4j 없이 초기화."""
    pipeline = UnifiedSearchPipeline(None)

    assert pipeline.neo4j_client is None
    assert pipeline.hybrid_ranker is None
    assert pipeline.evidence_synthesizer is None
    assert pipeline.conflict_detector is None


def test_create_pipeline_helper(mock_neo4j_client):
    """create_pipeline() 헬퍼 함수."""
    pipeline = create_pipeline(mock_neo4j_client)

    assert isinstance(pipeline, UnifiedSearchPipeline)
    assert pipeline.neo4j_client is mock_neo4j_client


# =============================================================================
# Test Query Classification
# =============================================================================

@pytest.mark.asyncio
async def test_query_classification_factual(pipeline):
    """FACTUAL 쿼리 분류."""
    query = "What is the fusion rate of TLIF?"

    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(pipeline, 'hybrid_ranker', None):
        response = await pipeline.search(query, SearchOptions(
            include_synthesis=False,
            detect_conflicts=False
        ))

    assert response.query_analysis.query_type == QueryType.FACTUAL
    assert response.query_analysis.confidence > 0


@pytest.mark.asyncio
async def test_query_classification_comparative(pipeline):
    """COMPARATIVE 쿼리 분류."""
    query = "TLIF vs OLIF for stenosis"

    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(pipeline, 'hybrid_ranker', None):
        response = await pipeline.search(query, SearchOptions(
            include_synthesis=False,
            detect_conflicts=False
        ))

    assert response.query_analysis.query_type == QueryType.COMPARATIVE


@pytest.mark.asyncio
async def test_query_classification_exploratory(pipeline):
    """EXPLORATORY 쿼리 분류."""
    query = "What treatments exist for lumbar stenosis?"

    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(pipeline, 'hybrid_ranker', None):
        response = await pipeline.search(query, SearchOptions(
            include_synthesis=False,
            detect_conflicts=False
        ))

    assert response.query_analysis.query_type == QueryType.EXPLORATORY


# =============================================================================
# Test Search Execution
# =============================================================================

@pytest.mark.asyncio
async def test_search_basic(pipeline, sample_ranked_results):
    """기본 검색 실행."""
    query = "TLIF fusion rate"

    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    # Mock adaptive_ranker.rank
    with patch.object(
        pipeline.adaptive_ranker, 'rank', return_value=sample_ranked_results
    ):
        with patch.object(pipeline.hybrid_ranker, 'search', new_callable=AsyncMock):
            pipeline.hybrid_ranker.search.return_value = []

            response = await pipeline.search(query, SearchOptions(
                top_k=5,
                include_synthesis=False,
                detect_conflicts=False
            ))

    assert isinstance(response, SearchResponse)
    assert len(response.results) > 0
    assert response.query_analysis.query_type is not None
    assert response.execution_time_ms > 0


@pytest.mark.asyncio
async def test_search_with_synthesis(pipeline, sample_ranked_results, sample_synthesis):
    """근거 종합 포함 검색."""
    query = "TLIF fusion rate"

    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(
        pipeline.adaptive_ranker, 'rank', return_value=sample_ranked_results
    ):
        with patch.object(pipeline.hybrid_ranker, 'search', new_callable=AsyncMock):
            pipeline.hybrid_ranker.search.return_value = []

        # Mock evidence synthesizer
        with patch.object(
            pipeline.evidence_synthesizer, 'synthesize', new_callable=AsyncMock
        ):
            pipeline.evidence_synthesizer.synthesize.return_value = sample_synthesis

            # Mock extraction method
            pipeline._extract_intervention_outcome = Mock(
                return_value=("TLIF", "Fusion Rate")
            )

            response = await pipeline.search(query, SearchOptions(
                top_k=5,
                include_synthesis=True,
                detect_conflicts=False
            ))

    assert response.synthesis is not None
    assert response.synthesis.strength == EvidenceStrength.STRONG
    assert response.synthesis.grade_rating == "A"
    assert response.synthesis_time_ms is not None


@pytest.mark.asyncio
async def test_search_with_conflicts(pipeline, sample_ranked_results, sample_conflict):
    """충돌 탐지 포함 검색."""
    query = "TLIF vs OLIF"

    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    # Directly mock the conflict_detector
    mock_conflict_detector = AsyncMock()
    mock_conflict_detector.detect_conflicts.return_value = sample_conflict
    pipeline.conflict_detector = mock_conflict_detector

    with patch.object(
        pipeline.adaptive_ranker, 'rank', return_value=sample_ranked_results
    ), patch.object(
        pipeline.hybrid_ranker, 'search', new_callable=AsyncMock
    ) as mock_hybrid_search:
        mock_hybrid_search.return_value = []

        pipeline._extract_intervention_outcome = Mock(
            return_value=("TLIF", "VAS")
        )

        response = await pipeline.search(query, SearchOptions(
            top_k=5,
            include_synthesis=False,
            detect_conflicts=True,
            conflict_min_severity="high"
        ))

    assert response.conflicts is not None
    assert len(response.conflicts) == 1
    assert response.conflicts[0].severity == ConflictSeverity.HIGH
    assert response.conflict_time_ms is not None


@pytest.mark.asyncio
async def test_search_full_pipeline(
    pipeline, sample_ranked_results, sample_synthesis, sample_conflict
):
    """전체 파이프라인 실행 (synthesis + conflicts)."""
    query = "TLIF vs OLIF for stenosis"

    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    # Directly mock the components
    mock_conflict_detector = AsyncMock()
    mock_conflict_detector.detect_conflicts.return_value = sample_conflict
    pipeline.conflict_detector = mock_conflict_detector

    mock_evidence_synthesizer = AsyncMock()
    mock_evidence_synthesizer.synthesize.return_value = sample_synthesis
    pipeline.evidence_synthesizer = mock_evidence_synthesizer

    with patch.object(
        pipeline.adaptive_ranker, 'rank', return_value=sample_ranked_results
    ), patch.object(
        pipeline.hybrid_ranker, 'search', new_callable=AsyncMock
    ) as mock_hybrid_search:
        mock_hybrid_search.return_value = []

        pipeline._extract_intervention_outcome = Mock(
            return_value=("TLIF", "VAS")
        )

        response = await pipeline.search(query, SearchOptions(
            top_k=10,
            include_synthesis=True,
            detect_conflicts=True
        ))

    # Verify all components ran
    assert response.results is not None
    assert response.synthesis is not None
    assert response.conflicts is not None
    assert response.query_analysis is not None

    # Verify timing info
    assert response.execution_time_ms > 0
    assert response.synthesis_time_ms is not None
    assert response.conflict_time_ms is not None


# =============================================================================
# Test Response Methods
# =============================================================================

def test_search_response_get_summary(sample_ranked_results, sample_synthesis):
    """SearchResponse.get_summary() 테스트."""
    response = SearchResponse(
        results=sample_ranked_results,
        synthesis=sample_synthesis,
        conflicts=None,
        query_analysis=QueryAnalysis(
            query_type=QueryType.COMPARATIVE,
            confidence=0.85
        ),
        execution_time_ms=150.5
    )

    summary = response.get_summary()

    assert "Query Type: comparative" in summary
    assert "Results: 2 documents" in summary
    assert "Execution Time: 150.5ms" in summary
    assert "Evidence Synthesis: improved" in summary
    assert "GRADE A" in summary


def test_search_response_to_dict(sample_ranked_results):
    """SearchResponse.to_dict() 테스트."""
    response = SearchResponse(
        results=sample_ranked_results,
        synthesis=None,
        conflicts=None,
        query_analysis=QueryAnalysis(
            query_type=QueryType.FACTUAL,
            confidence=0.7
        ),
        execution_time_ms=100.0
    )

    data = response.to_dict()

    assert "results" in data
    assert "query_analysis" in data
    assert "execution_time_ms" in data
    assert len(data["results"]) == 2
    assert data["query_analysis"]["query_type"] == "factual"
    assert data["execution_time_ms"] == 100.0


# =============================================================================
# Test Options Handling
# =============================================================================

@pytest.mark.asyncio
async def test_search_options_top_k(pipeline, sample_ranked_results):
    """top_k 옵션 처리."""
    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(
        pipeline.adaptive_ranker, 'rank', return_value=sample_ranked_results
    ):
        with patch.object(pipeline.hybrid_ranker, 'search', new_callable=AsyncMock):
            pipeline.hybrid_ranker.search.return_value = []

            response = await pipeline.search(
                "test query",
                SearchOptions(top_k=1, include_synthesis=False, detect_conflicts=False)
            )

    assert len(response.results) == 1


@pytest.mark.asyncio
async def test_search_options_disable_synthesis(pipeline):
    """근거 종합 비활성화."""
    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(pipeline, 'adaptive_ranker'):
        pipeline.adaptive_ranker.rank = Mock(return_value=[])

        with patch.object(pipeline.hybrid_ranker, 'search', new_callable=AsyncMock):
            pipeline.hybrid_ranker.search.return_value = []

            response = await pipeline.search(
                "test query",
                SearchOptions(include_synthesis=False, detect_conflicts=False)
            )

    assert response.synthesis is None
    assert response.synthesis_time_ms is None


@pytest.mark.asyncio
async def test_search_options_disable_conflicts(pipeline):
    """충돌 탐지 비활성화."""
    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(pipeline, 'adaptive_ranker'):
        pipeline.adaptive_ranker.rank = Mock(return_value=[])

        with patch.object(pipeline.hybrid_ranker, 'search', new_callable=AsyncMock):
            pipeline.hybrid_ranker.search.return_value = []

            response = await pipeline.search(
                "test query",
                SearchOptions(include_synthesis=False, detect_conflicts=False)
            )

    assert response.conflicts is None
    assert response.conflict_time_ms is None


# =============================================================================
# Test Error Handling
# =============================================================================

@pytest.mark.asyncio
async def test_search_without_neo4j():
    """Neo4j 없이 검색 시도 (에러 발생)."""
    pipeline = UnifiedSearchPipeline(None)

    with pytest.raises(ValidationError, match="Neo4j client is required"):
        await pipeline.search("test query")


@pytest.mark.asyncio
async def test_search_synthesis_error_handling(pipeline, sample_ranked_results):
    """근거 종합 실패 시 에러 처리."""
    pipeline.neo4j_client.get_embedding = AsyncMock(return_value=[0.1] * 768)
    with patch.object(
        pipeline.adaptive_ranker, 'rank', return_value=sample_ranked_results
    ):
        with patch.object(pipeline.hybrid_ranker, 'search', new_callable=AsyncMock):
            pipeline.hybrid_ranker.search.return_value = []

        # Mock synthesis to raise error
        with patch.object(
            pipeline.evidence_synthesizer, 'synthesize', new_callable=AsyncMock
        ):
            pipeline.evidence_synthesizer.synthesize.side_effect = Exception("Synthesis error")

            pipeline._extract_intervention_outcome = Mock(
                return_value=("TLIF", "VAS")
            )

            # Should not crash, just log error and continue
            response = await pipeline.search(
                "test query",
                SearchOptions(include_synthesis=True, detect_conflicts=False)
            )

    assert response.synthesis is None  # Synthesis failed gracefully


# =============================================================================
# Test Quick Search Helper
# =============================================================================

@pytest.mark.asyncio
async def test_quick_search_helper(mock_neo4j_client):
    """quick_search() 헬퍼 함수."""
    with patch('src.solver.unified_pipeline.UnifiedSearchPipeline'):
        mock_pipeline = Mock()
        mock_pipeline.search = AsyncMock(return_value=SearchResponse(
            results=[],
            synthesis=None,
            conflicts=None,
            query_analysis=QueryAnalysis(QueryType.FACTUAL, 0.7),
            execution_time_ms=100.0
        ))

        with patch(
            'src.solver.unified_pipeline.create_pipeline',
            return_value=mock_pipeline
        ):
            response = await quick_search(
                "test query",
                neo4j_client=mock_neo4j_client,
                top_k=5
            )

    assert isinstance(response, SearchResponse)


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_end_to_end_integration():
    """전체 통합 테스트 (실제 DB 없이 Mock 사용).

    실제 DB 연결 없이 모든 컴포넌트가 올바르게 통합되는지 확인.
    """
    # Create mock clients
    mock_neo4j = Mock()
    mock_neo4j.run_query = AsyncMock(return_value=[])
    mock_neo4j.get_embedding = AsyncMock(return_value=[0.1] * 768)

    # Create pipeline
    pipeline = create_pipeline(mock_neo4j)

    # Execute search
    response = await pipeline.search(
        query="What is the fusion rate of TLIF?",
        options=SearchOptions(
            top_k=10,
            include_synthesis=False,  # Skip to avoid DB calls
            detect_conflicts=False
        )
    )

    # Verify response structure
    assert isinstance(response, SearchResponse)
    assert response.query_analysis.query_type == QueryType.FACTUAL
    assert response.execution_time_ms > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

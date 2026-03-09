"""Tests for GraphRAG v2.0.

Microsoft-style community-based knowledge graph RAG 테스트.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.solver.graph_rag_v2 import (
    Community,
    CommunityHierarchy,
    GraphRAGResult,
    SearchType,
    CommunityDetector,
    CommunitySummarizer,
    GlobalSearchEngine,
    LocalSearchEngine,
    GraphRAGPipeline,
)
from src.graph.neo4j_client import Neo4jClient
from src.llm.gemini_client import GeminiClient, GeminiConfig, GeminiResponse


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j 클라이언트."""
    client = Mock(spec=Neo4jClient)
    client.run_query = AsyncMock()
    client.run_write_query = AsyncMock(return_value={"nodes_created": 1})
    return client


@pytest.fixture
def mock_llm_client():
    """Mock LLM 클라이언트."""
    client = Mock(spec=GeminiClient)
    client.generate = AsyncMock(return_value=GeminiResponse(
        text="Test summary",
        input_tokens=100,
        output_tokens=50,
        latency_ms=100.0
    ))
    return client


@pytest.fixture
def sample_graph_data():
    """샘플 그래프 데이터."""
    return {
        "nodes": [
            {"id": "TLIF", "type": "intervention"},
            {"id": "UBE", "type": "intervention"},
            {"id": "VAS", "type": "outcome"},
            {"id": "ODI", "type": "outcome"},
        ],
        "edges": [
            {
                "source": "TLIF",
                "target": "VAS",
                "p_value": 0.001,
                "is_significant": True,
                "direction": "improved",
                "value": "2.3",
                "source_paper": "paper_001",
            },
            {
                "source": "TLIF",
                "target": "ODI",
                "p_value": 0.002,
                "is_significant": True,
                "direction": "improved",
                "value": "15.2",
                "source_paper": "paper_001",
            },
            {
                "source": "UBE",
                "target": "VAS",
                "p_value": 0.01,
                "is_significant": True,
                "direction": "improved",
                "value": "1.8",
                "source_paper": "paper_002",
            },
        ],
    }


@pytest.fixture
def sample_community():
    """샘플 커뮤니티."""
    return Community(
        id="community_L0_0",
        level=0,
        members=["TLIF", "VAS", "ODI"],
        summary="TLIF shows improvement in VAS and ODI scores",
        evidence_count=5,
        avg_p_value=0.01,
    )


@pytest.fixture
def sample_hierarchy(sample_community):
    """샘플 커뮤니티 계층."""
    hierarchy = CommunityHierarchy()

    # Level 0 communities
    comm0 = sample_community
    comm1 = Community(
        id="community_L0_1",
        level=0,
        members=["UBE", "VAS"],
        summary="UBE reduces pain scores",
        evidence_count=3,
        avg_p_value=0.02,
    )

    hierarchy.add_community(comm0)
    hierarchy.add_community(comm1)

    # Level 1 community
    comm_top = Community(
        id="community_L1_0",
        level=1,
        members=["TLIF", "UBE", "VAS", "ODI"],
        summary="Fusion and endoscopic surgeries improve clinical outcomes",
        evidence_count=8,
        avg_p_value=0.015,
    )

    hierarchy.add_community(comm_top)

    # Set parent relationships
    comm0.parent_id = comm_top.id
    comm1.parent_id = comm_top.id

    return hierarchy


# ============================================================================
# Community Data Structure Tests
# ============================================================================

def test_community_creation():
    """커뮤니티 생성 테스트."""
    comm = Community(
        id="test_comm",
        level=0,
        members=["A", "B", "C"],
        summary="Test summary",
        evidence_count=10,
        avg_p_value=0.05,
    )

    assert comm.id == "test_comm"
    assert comm.level == 0
    assert len(comm.members) == 3
    assert comm.summary == "Test summary"
    assert comm.evidence_count == 10
    assert comm.avg_p_value == 0.05


def test_community_to_dict():
    """커뮤니티 딕셔너리 변환 테스트."""
    comm = Community(
        id="test",
        level=1,
        members=["X", "Y"],
        parent_id="parent_test",
        summary="Summary",
    )

    data = comm.to_dict()

    assert data["id"] == "test"
    assert data["level"] == 1
    assert data["members"] == ["X", "Y"]
    assert data["parent_id"] == "parent_test"
    assert data["summary"] == "Summary"


def test_community_from_dict():
    """딕셔너리에서 커뮤니티 생성 테스트."""
    data = {
        "id": "test",
        "level": 2,
        "members": ["A", "B"],
        "parent_id": None,
        "summary": "Test",
        "evidence_count": 5,
        "avg_p_value": 0.01,
    }

    comm = Community.from_dict(data)

    assert comm.id == "test"
    assert comm.level == 2
    assert len(comm.members) == 2


def test_community_hierarchy_add_community():
    """계층 구조에 커뮤니티 추가 테스트."""
    hierarchy = CommunityHierarchy()

    comm0 = Community(id="c0", level=0, members=["A"])
    comm1 = Community(id="c1", level=1, members=["B"])

    hierarchy.add_community(comm0)
    hierarchy.add_community(comm1)

    assert len(hierarchy.communities) == 2
    assert hierarchy.max_level == 1
    assert len(hierarchy.levels[0]) == 1
    assert len(hierarchy.levels[1]) == 1


def test_community_hierarchy_get_community():
    """커뮤니티 조회 테스트."""
    hierarchy = CommunityHierarchy()
    comm = Community(id="test", level=0, members=["A"])
    hierarchy.add_community(comm)

    result = hierarchy.get_community("test")
    assert result is not None
    assert result.id == "test"

    not_found = hierarchy.get_community("nonexistent")
    assert not_found is None


def test_community_hierarchy_get_by_level():
    """레벨별 커뮤니티 조회 테스트."""
    hierarchy = CommunityHierarchy()

    for i in range(3):
        hierarchy.add_community(Community(id=f"c0_{i}", level=0, members=[f"A{i}"]))
    for i in range(2):
        hierarchy.add_community(Community(id=f"c1_{i}", level=1, members=[f"B{i}"]))

    level0 = hierarchy.get_communities_by_level(0)
    level1 = hierarchy.get_communities_by_level(1)

    assert len(level0) == 3
    assert len(level1) == 2


# ============================================================================
# CommunityDetector Tests
# ============================================================================

@pytest.mark.asyncio
async def test_community_detector_fetch_graph_data(mock_neo4j_client):
    """그래프 데이터 가져오기 테스트."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention": "TLIF",
            "outcome": "VAS",
            "p_value": 0.001,
            "is_significant": True,
            "direction": "improved",
            "value": "2.3",
            "source_paper": "paper_001",
        },
        {
            "intervention": "UBE",
            "outcome": "ODI",
            "p_value": 0.01,
            "is_significant": True,
            "direction": "improved",
            "value": "10.5",
            "source_paper": "paper_002",
        },
    ]

    detector = CommunityDetector(mock_neo4j_client)
    graph_data = await detector._fetch_graph_data()

    assert len(graph_data["nodes"]) == 4  # 2 interventions + 2 outcomes
    assert len(graph_data["edges"]) == 2


@pytest.mark.asyncio
async def test_community_detector_build_networkx_graph(mock_neo4j_client, sample_graph_data):
    """NetworkX 그래프 구축 테스트."""
    detector = CommunityDetector(mock_neo4j_client)
    G = detector._build_networkx_graph(sample_graph_data)

    assert G.number_of_nodes() == 4
    assert G.number_of_edges() == 3

    # 엣지 가중치 확인
    edge_data = G.get_edge_data("TLIF", "VAS")
    assert edge_data is not None
    assert edge_data["p_value"] == 0.001
    assert edge_data["is_significant"] is True


@pytest.mark.asyncio
async def test_community_detector_detect_communities(mock_neo4j_client, sample_graph_data):
    """커뮤니티 탐지 테스트."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention": r["source"],
            "outcome": r["target"],
            "p_value": r["p_value"],
            "is_significant": r["is_significant"],
            "direction": r["direction"],
            "value": r["value"],
            "source_paper": r["source_paper"],
        }
        for r in sample_graph_data["edges"]
    ]

    detector = CommunityDetector(mock_neo4j_client)
    hierarchy = await detector.detect_communities(resolution=1.0, min_community_size=2)

    assert hierarchy is not None
    assert len(hierarchy.communities) > 0


# ============================================================================
# CommunitySummarizer Tests
# ============================================================================

@pytest.mark.asyncio
async def test_community_summarizer_summarize_from_data(
    mock_neo4j_client,
    mock_llm_client,
    sample_community
):
    """데이터에서 요약 생성 테스트."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention": "TLIF",
            "outcome": "VAS",
            "p_value": 0.001,
            "is_significant": True,
            "direction": "improved",
            "value": "2.3",
            "source_paper": "paper_001",
        }
    ]

    summarizer = CommunitySummarizer(mock_neo4j_client, mock_llm_client)
    summary = await summarizer._summarize_from_data(sample_community)

    assert summary is not None
    assert isinstance(summary, str)
    mock_llm_client.generate.assert_called_once()


@pytest.mark.asyncio
async def test_community_summarizer_aggregate_child_summaries(
    mock_neo4j_client,
    mock_llm_client,
    sample_hierarchy
):
    """하위 요약 aggregation 테스트."""
    summarizer = CommunitySummarizer(mock_neo4j_client, mock_llm_client)

    parent_comm = sample_hierarchy.get_community("community_L1_0")
    summary = await summarizer._aggregate_child_summaries(parent_comm, sample_hierarchy)

    assert summary is not None
    assert isinstance(summary, str)


@pytest.mark.asyncio
async def test_community_summarizer_summarize_hierarchy(
    mock_neo4j_client,
    mock_llm_client,
    sample_hierarchy
):
    """계층 구조 전체 요약 테스트."""
    mock_neo4j_client.run_query.return_value = [
        {
            "intervention": "TLIF",
            "outcome": "VAS",
            "p_value": 0.001,
            "is_significant": True,
            "direction": "improved",
            "value": "2.3",
            "source_paper": "paper_001",
        }
    ]

    # Clear existing summaries
    for comm in sample_hierarchy.communities.values():
        comm.summary = ""

    summarizer = CommunitySummarizer(mock_neo4j_client, mock_llm_client)
    result = await summarizer.summarize_hierarchy(sample_hierarchy)

    # 모든 커뮤니티에 요약이 생성되었는지 확인
    for comm in result.communities.values():
        assert comm.summary != ""


# ============================================================================
# GlobalSearchEngine Tests
# ============================================================================

@pytest.mark.asyncio
async def test_global_search_engine_search(mock_llm_client, sample_hierarchy):
    """전역 검색 테스트."""
    # Mock LLM responses
    mock_llm_client.generate = AsyncMock(side_effect=[
        # Community selection
        GeminiResponse(
            text="community_L0_0, community_L0_1",
            input_tokens=100,
            output_tokens=20,
            latency_ms=100.0
        ),
        # Partial answers
        GeminiResponse(
            text="TLIF improves outcomes",
            input_tokens=100,
            output_tokens=20,
            latency_ms=100.0
        ),
        GeminiResponse(
            text="UBE reduces pain",
            input_tokens=100,
            output_tokens=20,
            latency_ms=100.0
        ),
        # Final aggregation
        GeminiResponse(
            text="Both TLIF and UBE show positive clinical outcomes",
            input_tokens=200,
            output_tokens=30,
            latency_ms=150.0
        ),
    ])

    engine = GlobalSearchEngine(sample_hierarchy, mock_llm_client)
    result = await engine.search("What are effective fusion surgeries?", max_communities=5)

    assert result is not None
    assert result.search_type == SearchType.GLOBAL
    assert len(result.communities_used) > 0
    assert result.answer != ""


@pytest.mark.asyncio
async def test_global_search_no_communities(mock_llm_client):
    """커뮤니티 없을 때 전역 검색 테스트."""
    empty_hierarchy = CommunityHierarchy()

    engine = GlobalSearchEngine(empty_hierarchy, mock_llm_client)
    result = await engine.search("Test query")

    assert result.answer == "No relevant communities found."
    assert result.confidence == 0.0


# ============================================================================
# LocalSearchEngine Tests
# ============================================================================

@pytest.mark.asyncio
async def test_local_search_engine_extract_entities(
    mock_neo4j_client,
    mock_llm_client,
    sample_hierarchy
):
    """엔티티 추출 테스트."""
    mock_neo4j_client.run_query.side_effect = [
        [{"name": "TLIF"}, {"name": "UBE"}],  # interventions
        [{"name": "VAS"}, {"name": "ODI"}],   # outcomes
    ]

    engine = LocalSearchEngine(mock_neo4j_client, sample_hierarchy, mock_llm_client)
    entities = await engine._extract_entities("What is the effect of TLIF on VAS?")

    assert "TLIF" in entities
    assert "VAS" in entities


@pytest.mark.asyncio
async def test_local_search_engine_explore_neighborhood(
    mock_neo4j_client,
    mock_llm_client,
    sample_hierarchy
):
    """엔티티 주변 탐색 테스트."""
    mock_neo4j_client.run_query.return_value = [
        {
            "source_name": "TLIF",
            "rel_type": "AFFECTS",
            "target_name": "VAS",
            "p_value": 0.001,
            "is_significant": True,
            "direction": "improved",
            "value": "2.3",
        }
    ]

    engine = LocalSearchEngine(mock_neo4j_client, sample_hierarchy, mock_llm_client)
    subgraph = await engine._explore_entity_neighborhood(["TLIF"], max_hops=2)

    assert len(subgraph) > 0
    assert subgraph[0]["source_name"] == "TLIF"


@pytest.mark.asyncio
async def test_local_search_engine_search(
    mock_neo4j_client,
    mock_llm_client,
    sample_hierarchy
):
    """로컬 검색 테스트."""
    mock_neo4j_client.run_query.side_effect = [
        [{"name": "TLIF"}],  # interventions
        [{"name": "VAS"}],   # outcomes
        [  # subgraph
            {
                "source_name": "TLIF",
                "rel_type": "AFFECTS",
                "target_name": "VAS",
                "p_value": 0.001,
                "is_significant": True,
                "direction": "improved",
                "value": "2.3",
            }
        ],
    ]

    mock_llm_client.generate.return_value = GeminiResponse(
        text="TLIF significantly improves VAS scores",
        input_tokens=200,
        output_tokens=30,
        latency_ms=150.0
    )

    engine = LocalSearchEngine(mock_neo4j_client, sample_hierarchy, mock_llm_client)
    result = await engine.search("Effect of TLIF on VAS?", max_hops=2)

    assert result is not None
    assert result.search_type == SearchType.LOCAL
    assert len(result.evidence) > 0


# ============================================================================
# GraphRAGPipeline Tests
# ============================================================================

@pytest.mark.asyncio
async def test_graph_rag_pipeline_build_index(mock_neo4j_client, mock_llm_client):
    """인덱스 구축 테스트."""
    # Mock graph data
    mock_neo4j_client.run_query.side_effect = [
        # fetch_graph_data
        [
            {
                "intervention": "TLIF",
                "outcome": "VAS",
                "p_value": 0.001,
                "is_significant": True,
                "direction": "improved",
                "value": "2.3",
                "source_paper": "paper_001",
            }
        ],
        # load check
        [],
    ]

    pipeline = GraphRAGPipeline(mock_neo4j_client, llm_client=mock_llm_client)
    hierarchy = await pipeline.build_index(
        resolution=1.0,
        min_community_size=2,
        force_rebuild=True
    )

    assert hierarchy is not None
    assert pipeline.hierarchy is not None


@pytest.mark.asyncio
async def test_graph_rag_pipeline_global_search(mock_neo4j_client, mock_llm_client, sample_hierarchy):
    """파이프라인 전역 검색 테스트."""
    pipeline = GraphRAGPipeline(mock_neo4j_client, llm_client=mock_llm_client)
    pipeline.hierarchy = sample_hierarchy
    pipeline._initialize_search_engines()

    # Override mock for specific responses
    pipeline.llm.generate = AsyncMock(side_effect=[
        GeminiResponse(text="community_L0_0", input_tokens=50, output_tokens=10, latency_ms=50),
        GeminiResponse(text="Partial answer", input_tokens=100, output_tokens=20, latency_ms=100),
        GeminiResponse(text="Final answer", input_tokens=150, output_tokens=30, latency_ms=150),
    ])

    result = await pipeline.global_search("Test query", max_communities=5)

    assert result is not None
    assert result.search_type == SearchType.GLOBAL


@pytest.mark.asyncio
async def test_graph_rag_pipeline_local_search(mock_neo4j_client, mock_llm_client, sample_hierarchy):
    """파이프라인 로컬 검색 테스트."""
    mock_neo4j_client.run_query.side_effect = [
        [{"name": "TLIF"}],  # interventions
        [{"name": "VAS"}],   # outcomes
        [{"source_name": "TLIF", "target_name": "VAS", "p_value": 0.001}],  # subgraph
    ]

    pipeline = GraphRAGPipeline(mock_neo4j_client, llm_client=mock_llm_client)
    pipeline.hierarchy = sample_hierarchy
    pipeline._initialize_search_engines()

    result = await pipeline.local_search("TLIF effect?", max_hops=2)

    assert result is not None
    assert result.search_type == SearchType.LOCAL


@pytest.mark.asyncio
async def test_graph_rag_pipeline_hybrid_search(mock_neo4j_client, mock_llm_client, sample_hierarchy):
    """파이프라인 하이브리드 검색 테스트."""
    mock_neo4j_client.run_query.side_effect = [
        [{"name": "TLIF"}],  # interventions
        [{"name": "VAS"}],   # outcomes
        [{"source_name": "TLIF", "target_name": "VAS", "p_value": 0.001}],  # subgraph
    ]

    mock_llm_client.generate = AsyncMock(side_effect=[
        # Global search
        GeminiResponse(text="community_L0_0", input_tokens=50, output_tokens=10, latency_ms=50),
        GeminiResponse(text="Global partial", input_tokens=100, output_tokens=20, latency_ms=100),
        GeminiResponse(text="Global answer", input_tokens=150, output_tokens=30, latency_ms=150),
        # Local search
        GeminiResponse(text="Local answer", input_tokens=100, output_tokens=50, latency_ms=100),
        # Combine
        GeminiResponse(text="Combined answer", input_tokens=200, output_tokens=60, latency_ms=200),
    ])

    pipeline = GraphRAGPipeline(mock_neo4j_client, llm_client=mock_llm_client)
    pipeline.hierarchy = sample_hierarchy
    pipeline._initialize_search_engines()

    result = await pipeline.hybrid_search("Test query", max_communities=5, max_hops=2)

    assert result is not None
    assert result.search_type == SearchType.HYBRID


@pytest.mark.asyncio
async def test_graph_rag_pipeline_get_statistics(mock_neo4j_client, mock_llm_client, sample_hierarchy):
    """파이프라인 통계 조회 테스트."""
    pipeline = GraphRAGPipeline(mock_neo4j_client, llm_client=mock_llm_client)

    # 인덱스 없을 때
    stats1 = pipeline.get_statistics()
    assert stats1["status"] == "not_built"

    # 인덱스 있을 때
    pipeline.hierarchy = sample_hierarchy
    stats2 = pipeline.get_statistics()

    assert stats2["status"] == "ready"
    assert stats2["total_communities"] == len(sample_hierarchy.communities)
    assert "levels" in stats2


# ============================================================================
# Integration Test
# ============================================================================

@pytest.mark.asyncio
async def test_end_to_end_workflow(mock_neo4j_client, mock_llm_client):
    """End-to-end 워크플로우 테스트."""
    # Use async side_effect for AsyncMock
    async def query_side_effect(query, params=None, fetch_all=True):
        # Check explore_entity_neighborhood query (most specific)
        if "AFFECTS*1.." in query and "source_name" in query:
            # _explore_entity_neighborhood query
            return [
                {
                    "source_name": "TLIF",
                    "rel_type": "AFFECTS",
                    "target_name": "VAS",
                    "p_value": 0.001,
                    "is_significant": True,
                    "direction": "improved",
                    "value": "2.3",
                }
            ]
        # Check fetch_graph_data query
        elif "AFFECTS" in query and "as intervention" in query:
            # _fetch_graph_data query
            return [
                {
                    "intervention": "TLIF",
                    "outcome": "VAS",
                    "p_value": 0.001,
                    "is_significant": True,
                    "direction": "improved",
                    "value": "2.3",
                    "source_paper": "paper_001",
                }
            ]
        elif "Intervention" in query and "RETURN i.name" in query:
            return [{"name": "TLIF"}]
        elif "Outcome" in query and "RETURN o.name" in query:
            return [{"name": "VAS"}]
        elif "Community" in query:
            return []  # No existing communities
        else:
            return []

    mock_neo4j_client.run_query.side_effect = query_side_effect

    # 1. 파이프라인 생성
    pipeline = GraphRAGPipeline(mock_neo4j_client, llm_client=mock_llm_client)

    # 2. 인덱스 구축
    hierarchy = await pipeline.build_index(force_rebuild=True)
    assert hierarchy is not None

    # 3. 검색 실행
    result = await pipeline.local_search("Effect of TLIF?", max_hops=2)

    assert result is not None
    assert isinstance(result, GraphRAGResult)
    assert result.search_type == SearchType.LOCAL

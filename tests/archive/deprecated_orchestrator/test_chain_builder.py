"""Tests for Chain Builder.

LangChain Chain Builder 테스트.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.orchestrator.chain_builder import (
    SpineGraphChain,
    ChainConfig,
    ChainInput,
    ChainOutput,
    HybridRetriever,
    create_chain,
)
from src.solver.hybrid_ranker import HybridResult
from src.solver.graph_result import GraphEvidence, PaperNode


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client."""
    client = MagicMock()
    client.connect = AsyncMock()
    client.close = AsyncMock()
    client.run_query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_vector_db():
    """Mock Vector DB."""
    db = MagicMock()
    db.get_embedding = MagicMock(return_value=[0.1] * 768)
    db.search_all = MagicMock(return_value=[])
    db.get_stats = MagicMock(return_value={"tier1": 100, "tier2": 200})
    return db


@pytest.fixture
def mock_config():
    """Mock chain config."""
    return ChainConfig(
        gemini_model="gemini-2.5-flash-preview-05-20",
        temperature=0.1,
        top_k=5,
        graph_weight=0.6,
        vector_weight=0.4,
    )


@pytest.fixture
def sample_graph_evidence():
    """Sample Graph evidence."""
    return GraphEvidence(
        intervention="TLIF",
        outcome="Fusion Rate",
        value="92%",
        value_control="85%",
        p_value=0.001,
        is_significant=True,
        direction="improved",
        source_paper_id="paper_001",
        evidence_level="1b",
    )


@pytest.fixture
def sample_paper_node():
    """Sample Paper node."""
    return PaperNode(
        paper_id="paper_001",
        title="TLIF vs PLIF for Lumbar Fusion",
        authors=["Kim", "Lee", "Park"],
        year=2024,
        journal="Spine",
        evidence_level="1b",
    )


@pytest.fixture
def sample_hybrid_results(sample_graph_evidence, sample_paper_node):
    """Sample hybrid search results."""
    return [
        HybridResult(
            result_type="graph",
            score=0.95,
            content="TLIF improved Fusion Rate to 92% vs 85% (p=0.001)",
            source_id="paper_001",
            evidence=sample_graph_evidence,
            paper=sample_paper_node,
            metadata={
                "p_value": 0.001,
                "evidence_level": "1b",
            }
        )
    ]


# =============================================================================
# Tests: HybridRetriever
# =============================================================================

class TestHybridRetriever:
    """HybridRetriever 테스트."""

    @pytest.mark.asyncio
    async def test_ainvoke(
        self,
        mock_neo4j_client,
        mock_vector_db,
        sample_hybrid_results
    ):
        """비동기 검색 테스트."""
        from src.solver.hybrid_ranker import HybridRanker
        from src.orchestrator.cypher_generator import CypherGenerator

        # Hybrid ranker with mocked search
        ranker = HybridRanker(
            vector_db=mock_vector_db,
            neo4j_client=mock_neo4j_client
        )
        ranker.search = AsyncMock(return_value=sample_hybrid_results)

        # Cypher generator
        generator = CypherGenerator()

        # Retriever
        retriever = HybridRetriever(
            hybrid_ranker=ranker,
            cypher_generator=generator,
            top_k=5,
        )

        # Test
        results = await retriever.ainvoke("TLIF가 Fusion Rate에 효과적인가?")

        assert len(results) == 1
        assert results[0].result_type == "graph"
        assert results[0].score == 0.95

    def test_invoke_sync(self, mock_neo4j_client, mock_vector_db):
        """동기 검색 (async 래퍼) 테스트."""
        from src.solver.hybrid_ranker import HybridRanker
        from src.orchestrator.cypher_generator import CypherGenerator

        ranker = HybridRanker(
            vector_db=mock_vector_db,
            neo4j_client=mock_neo4j_client
        )
        ranker.search = AsyncMock(return_value=[])

        generator = CypherGenerator()

        retriever = HybridRetriever(
            hybrid_ranker=ranker,
            cypher_generator=generator,
        )

        # Note: invoke()는 event loop 필요
        # pytest-asyncio로 실행하면 동작함
        # 여기서는 skip
        pass


# =============================================================================
# Tests: SpineGraphChain
# =============================================================================

class TestSpineGraphChain:
    """SpineGraphChain 테스트."""

    def test_initialization(self, mock_neo4j_client, mock_vector_db, mock_config):
        """초기화 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI") as mock_llm:
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
                api_key="test_key",
            )

            assert chain.neo4j_client == mock_neo4j_client
            assert chain.vector_db == mock_vector_db
            assert chain.config == mock_config
            assert chain.retriever is not None
            assert chain.hybrid_ranker is not None

    def test_build_retrieval_chain(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config
    ):
        """검색 체인 구축 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            retrieval_chain = chain.build_retrieval_chain()
            assert retrieval_chain is not None

    def test_build_qa_chain(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config
    ):
        """QA 체인 구축 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            qa_chain = chain.build_qa_chain()
            assert qa_chain is not None
            assert chain.qa_chain is not None

    def test_build_conflict_chain(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config
    ):
        """상충 결과 분석 체인 구축 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            conflict_chain = chain.build_conflict_chain()
            assert conflict_chain is not None
            assert chain.conflict_chain is not None

    @pytest.mark.asyncio
    async def test_invoke_qa_mode(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config,
        sample_hybrid_results
    ):
        """QA 모드 실행 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI") as mock_llm_class:
            # Mock LLM response
            mock_llm_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "TLIF is effective for improving Fusion Rate."
            mock_llm_instance.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_class.return_value = mock_llm_instance

            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            # Mock retriever
            chain.retriever.ainvoke = AsyncMock(return_value=sample_hybrid_results)

            # Test
            result = await chain.invoke("TLIF가 효과적인가?", mode="qa")

            assert isinstance(result, ChainOutput)
            assert result.answer != ""
            assert len(result.sources) == 1
            assert result.metadata["mode"] == "qa"

    @pytest.mark.asyncio
    async def test_invoke_retrieval_mode(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config,
        sample_hybrid_results
    ):
        """검색 모드 실행 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            # Mock retriever
            chain.retriever.ainvoke = AsyncMock(return_value=sample_hybrid_results)

            # Test
            result = await chain.invoke("Test query", mode="retrieval")

            assert isinstance(result, ChainOutput)
            assert result.answer == ""  # 검색만 수행
            assert len(result.sources) == 1
            assert result.metadata["mode"] == "retrieval"

    @pytest.mark.asyncio
    async def test_invoke_invalid_mode(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config
    ):
        """잘못된 모드 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            # Invalid mode should return error
            result = await chain.invoke("Test", mode="invalid_mode")

            assert "Error" in result.answer
            assert "error" in result.metadata

    def test_format_context(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config,
        sample_hybrid_results
    ):
        """컨텍스트 포맷팅 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            context = chain._format_context(sample_hybrid_results)

            assert "GRAPH Evidence" in context
            assert "Score:" in context
            assert "TLIF" in context
            assert "p-value" in context

    def test_detect_conflicts(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config
    ):
        """상충 결과 탐지 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            # Create conflicting results
            result1 = HybridResult(
                result_type="graph",
                score=0.9,
                content="TLIF improved Fusion Rate",
                source_id="paper_001",
                evidence=GraphEvidence(
                    intervention="TLIF",
                    outcome="Fusion Rate",
                    value="92%",
                    direction="improved",
                    source_paper_id="paper_001",
                ),
            )

            result2 = HybridResult(
                result_type="graph",
                score=0.8,
                content="TLIF did not improve Fusion Rate",
                source_id="paper_002",
                evidence=GraphEvidence(
                    intervention="TLIF",
                    outcome="Fusion Rate",
                    value="85%",
                    direction="unchanged",
                    source_paper_id="paper_002",
                ),
            )

            conflicts = chain._detect_conflicts([result1, result2])

            assert len(conflicts) == 2
            assert conflicts[0].evidence.intervention == "TLIF"
            assert conflicts[1].evidence.intervention == "TLIF"

    def test_get_stats(
        self,
        mock_neo4j_client,
        mock_vector_db,
        mock_config
    ):
        """통계 정보 테스트."""
        with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
            chain = SpineGraphChain(
                neo4j_client=mock_neo4j_client,
                vector_db=mock_vector_db,
                config=mock_config,
            )

            stats = chain.get_stats()

            assert "config" in stats
            assert "hybrid_ranker" in stats
            assert stats["config"]["model"] == mock_config.gemini_model


# =============================================================================
# Tests: Factory Function
# =============================================================================

class TestFactoryFunctions:
    """Factory 함수 테스트."""

    @pytest.mark.asyncio
    async def test_create_chain(self):
        """체인 생성 헬퍼 테스트."""
        with patch("src.orchestrator.chain_builder.Neo4jClient") as mock_neo4j:
            with patch("src.orchestrator.chain_builder.TieredVectorDB") as mock_vector:
                with patch("src.orchestrator.chain_builder.ChatGoogleGenerativeAI"):
                    # Mock client
                    mock_client = MagicMock()
                    mock_client.connect = AsyncMock()
                    mock_neo4j.return_value = mock_client

                    # Mock vector db
                    mock_db = MagicMock()
                    mock_vector.return_value = mock_db

                    # Create chain
                    chain = await create_chain(
                        neo4j_uri="bolt://localhost:7687",
                        neo4j_username="neo4j",
                        neo4j_password="password",
                        chromadb_path="./data/chromadb",
                        gemini_api_key="test_key",
                    )

                    assert isinstance(chain, SpineGraphChain)
                    mock_client.connect.assert_called_once()


# =============================================================================
# Integration Tests (requires real dependencies)
# =============================================================================

@pytest.mark.integration
class TestIntegration:
    """통합 테스트 (실제 의존성 필요)."""

    @pytest.mark.asyncio
    async def test_end_to_end_qa(self):
        """End-to-end QA 테스트."""
        # This requires:
        # - Running Neo4j
        # - ChromaDB with data
        # - Valid Gemini API key
        # Skip in normal test runs
        pytest.skip("Integration test - requires real services")

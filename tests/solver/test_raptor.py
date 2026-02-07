"""Tests for RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval)."""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

from src.solver.raptor import (
    TreeNode,
    ClusteringEngine,
    ClusteringMethod,
    SummarizationEngine,
    RAPTORTree,
    RAPTORRetriever,
    RAPTORPipeline,
    RetrievalStrategy,
    ClusterResult,
)
from src.storage import TextChunk
from src.llm.gemini_client import GeminiResponse


# Fixtures

@pytest.fixture
def sample_chunks():
    """Create sample text chunks for testing."""
    return [
        TextChunk(
            chunk_id="chunk_1",
            content="TLIF surgery showed 80% fusion rate with p<0.05 for lumbar stenosis patients.",
            document_id="doc_1",
            tier="tier1",
            section="Results",
            source_type="original",
            evidence_level="1b",
            publication_year=2023,
            title="TLIF Outcomes Study",
            is_key_finding=True
        ),
        TextChunk(
            chunk_id="chunk_2",
            content="OLIF demonstrated better sagittal alignment compared to TLIF in 120 patients.",
            document_id="doc_1",
            tier="tier1",
            section="Results",
            source_type="original",
            evidence_level="1b",
            publication_year=2023,
            title="TLIF vs OLIF Comparison"
        ),
        TextChunk(
            chunk_id="chunk_3",
            content="Endoscopic UBE technique reduces tissue damage and hospital stay by 40%.",
            document_id="doc_1",
            tier="tier1",
            section="Conclusion",
            source_type="original",
            evidence_level="2a",
            publication_year=2023,
            title="UBE Benefits Study"
        ),
        TextChunk(
            chunk_id="chunk_4",
            content="Lumbar stenosis affects elderly patients with degenerative spine disease.",
            document_id="doc_1",
            tier="tier2",
            section="Introduction",
            source_type="background",
            evidence_level="5",
            publication_year=2023,
            title="Background Information"
        ),
        TextChunk(
            chunk_id="chunk_5",
            content="PSO osteotomy corrects sagittal imbalance with 15-20 degree correction per level.",
            document_id="doc_1",
            tier="tier1",
            section="Results",
            source_type="original",
            evidence_level="2a",
            publication_year=2023,
            title="PSO Outcomes"
        ),
    ]


@pytest.fixture
def mock_embedding_generator():
    """Mock embedding generator."""
    mock = MagicMock()
    mock.embed = MagicMock(side_effect=lambda text: [float(i % 100) / 100 for i in range(3072)])
    return mock


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini client for summarization."""
    mock = AsyncMock()
    mock.generate_text = AsyncMock(return_value=GeminiResponse(
        text="Summary of spine surgery outcomes showing improved fusion rates and reduced complications.",
        input_tokens=100,
        output_tokens=30,
        latency_ms=500,
        model="gemini-2.5-flash"
    ))
    return mock


# TreeNode Tests

def test_tree_node_creation():
    """Test TreeNode creation and properties."""
    node = TreeNode(
        node_id="test_node_1",
        content="Test content",
        embedding=[0.1] * 3072,
        level=0,
        chunk_id="chunk_1",
        document_id="doc_1"
    )

    assert node.node_id == "test_node_1"
    assert node.level == 0
    assert node.is_leaf is True
    assert node.is_summary is False
    assert len(node.children) == 0
    assert node.parent is None


def test_tree_node_add_child():
    """Test adding children to TreeNode."""
    parent = TreeNode(
        node_id="parent",
        content="Parent summary",
        embedding=[0.1] * 3072,
        level=1
    )

    child1 = TreeNode(
        node_id="child1",
        content="Child 1 content",
        embedding=[0.2] * 3072,
        level=0
    )

    child2 = TreeNode(
        node_id="child2",
        content="Child 2 content",
        embedding=[0.3] * 3072,
        level=0
    )

    parent.add_child(child1)
    parent.add_child(child2)

    assert len(parent.children) == 2
    assert child1.parent == parent
    assert child2.parent == parent
    assert parent.num_descendants == 2


def test_tree_node_num_descendants():
    """Test recursive descendant counting."""
    root = TreeNode(node_id="root", content="Root", embedding=[0.1]*3072, level=2)

    level1_a = TreeNode(node_id="l1a", content="L1A", embedding=[0.2]*3072, level=1)
    level1_b = TreeNode(node_id="l1b", content="L1B", embedding=[0.3]*3072, level=1)

    leaf1 = TreeNode(node_id="leaf1", content="Leaf1", embedding=[0.4]*3072, level=0)
    leaf2 = TreeNode(node_id="leaf2", content="Leaf2", embedding=[0.5]*3072, level=0)
    leaf3 = TreeNode(node_id="leaf3", content="Leaf3", embedding=[0.6]*3072, level=0)

    root.add_child(level1_a)
    root.add_child(level1_b)
    level1_a.add_child(leaf1)
    level1_a.add_child(leaf2)
    level1_b.add_child(leaf3)

    assert root.num_descendants == 5  # 2 level1 + 3 leaves
    assert level1_a.num_descendants == 2
    assert level1_b.num_descendants == 1


# ClusteringEngine Tests

def test_clustering_engine_init():
    """Test ClusteringEngine initialization."""
    engine = ClusteringEngine(
        method=ClusteringMethod.GMM,
        min_cluster_size=3,
        max_cluster_size=10
    )

    assert engine.method == ClusteringMethod.GMM
    assert engine.min_cluster_size == 3
    assert engine.max_cluster_size == 10


def test_clustering_gmm():
    """Test GMM clustering."""
    engine = ClusteringEngine(method=ClusteringMethod.GMM)

    # Create test embeddings (20 samples, 3072 dims - OpenAI text-embedding-3-large)
    np.random.seed(42)
    embeddings = np.random.randn(20, 3072)

    result = engine.cluster_embeddings(embeddings, num_clusters=3)

    assert result.num_clusters == 3
    assert result.method == "gmm"
    assert len(result.clusters) == 3
    assert sum(len(cluster) for cluster in result.clusters) == 20


def test_clustering_kmeans():
    """Test K-Means clustering."""
    engine = ClusteringEngine(method=ClusteringMethod.KMEANS)

    np.random.seed(42)
    embeddings = np.random.randn(15, 3072)

    result = engine.cluster_embeddings(embeddings, num_clusters=2)

    assert result.num_clusters == 2
    assert result.method == "kmeans"
    assert len(result.clusters) == 2


def test_clustering_auto_clusters():
    """Test automatic cluster number computation."""
    engine = ClusteringEngine(min_cluster_size=3, max_cluster_size=7)

    np.random.seed(42)
    embeddings = np.random.randn(30, 3072)

    result = engine.cluster_embeddings(embeddings)  # No num_clusters specified

    # Should create 6 clusters (30 / 5 = 6, where 5 is avg of min/max)
    assert 3 <= result.num_clusters <= 10
    assert result.num_clusters > 1


def test_clustering_edge_case_few_samples():
    """Test clustering with very few samples."""
    engine = ClusteringEngine(min_cluster_size=3)

    embeddings = np.random.randn(2, 3072)  # Only 2 samples

    result = engine.cluster_embeddings(embeddings)

    assert result.num_clusters == 1  # Should create single cluster
    assert len(result.clusters[0]) == 2


# SummarizationEngine Tests

@pytest.mark.asyncio
async def test_summarization_single_chunk(mock_gemini_client):
    """Test summarization with single chunk (no LLM call)."""
    engine = SummarizationEngine(gemini_client=mock_gemini_client)

    chunks = ["Single chunk content about TLIF surgery."]
    summary = await engine.summarize_cluster(chunks)

    assert summary == chunks[0]
    mock_gemini_client.generate_text.assert_not_called()


@pytest.mark.asyncio
async def test_summarization_multiple_chunks(mock_gemini_client):
    """Test summarization with multiple chunks."""
    engine = SummarizationEngine(gemini_client=mock_gemini_client)

    chunks = [
        "TLIF showed 80% fusion rate.",
        "OLIF had better sagittal alignment.",
        "UBE reduced hospital stay."
    ]

    summary = await engine.summarize_cluster(chunks)

    assert len(summary) > 0
    assert "Summary" in summary or "outcomes" in summary
    mock_gemini_client.generate_text.assert_called_once()


@pytest.mark.asyncio
async def test_summarization_empty_chunks(mock_gemini_client):
    """Test summarization with empty chunk list."""
    engine = SummarizationEngine(gemini_client=mock_gemini_client)

    summary = await engine.summarize_cluster([])

    assert summary == ""
    mock_gemini_client.generate_text.assert_not_called()


@pytest.mark.asyncio
async def test_summarization_llm_failure(mock_gemini_client):
    """Test summarization fallback when LLM fails."""
    mock_gemini_client.generate_text = AsyncMock(side_effect=Exception("API Error"))
    engine = SummarizationEngine(gemini_client=mock_gemini_client)

    chunks = ["Chunk 1", "Chunk 2", "Chunk 3"]
    summary = await engine.summarize_cluster(chunks)

    # Should fall back to concatenation
    assert len(summary) > 0
    assert any(chunk in summary for chunk in chunks)


# RAPTORTree Tests

@pytest.mark.asyncio
async def test_raptor_tree_build(sample_chunks, mock_gemini_client):
    """Test RAPTOR tree building."""
    tree = RAPTORTree(
        summarization_engine=SummarizationEngine(gemini_client=mock_gemini_client),
        max_levels=3
    )

    with patch.object(tree, '_get_embedding', return_value=[0.1]*3072):
        root = await tree.build_tree(sample_chunks)

    assert root is not None
    assert root.level > 0
    assert len(tree.get_all_nodes()) > len(sample_chunks)  # More nodes than original chunks


@pytest.mark.asyncio
async def test_raptor_tree_leaf_nodes(sample_chunks, mock_gemini_client):
    """Test that leaf nodes match original chunks."""
    tree = RAPTORTree(
        summarization_engine=SummarizationEngine(gemini_client=mock_gemini_client),
        max_levels=3
    )

    with patch.object(tree, '_get_embedding', return_value=[0.1]*3072):
        await tree.build_tree(sample_chunks)

    leaf_nodes = tree.get_nodes_at_level(0)

    assert len(leaf_nodes) == len(sample_chunks)
    assert all(node.is_leaf for node in leaf_nodes)
    assert all(node.chunk_id is not None for node in leaf_nodes)


@pytest.mark.asyncio
async def test_raptor_tree_get_nodes_at_level(sample_chunks, mock_gemini_client):
    """Test getting nodes at specific level."""
    tree = RAPTORTree(
        summarization_engine=SummarizationEngine(gemini_client=mock_gemini_client),
        max_levels=3
    )

    with patch.object(tree, '_get_embedding', return_value=[0.1]*3072):
        root = await tree.build_tree(sample_chunks)

    level0_nodes = tree.get_nodes_at_level(0)
    level1_nodes = tree.get_nodes_at_level(1)

    assert len(level0_nodes) > 0
    assert all(node.level == 0 for node in level0_nodes)

    if len(level1_nodes) > 0:
        assert all(node.level == 1 for node in level1_nodes)
        assert all(node.is_summary for node in level1_nodes)


# RAPTORRetriever Tests

@pytest.mark.asyncio
async def test_raptor_retriever_collapsed(sample_chunks, mock_gemini_client):
    """Test collapsed retrieval strategy."""
    tree = RAPTORTree(
        summarization_engine=SummarizationEngine(gemini_client=mock_gemini_client),
        max_levels=2
    )

    with patch.object(tree, '_get_embedding', return_value=[0.1]*3072):
        await tree.build_tree(sample_chunks)

    # Mock embedding generator for retriever
    mock_emb_gen = MagicMock()
    mock_emb_gen.embed = MagicMock(return_value=[0.1]*3072)
    retriever = RAPTORRetriever(tree, embedding_generator=mock_emb_gen)

    with patch.object(retriever, '_cosine_similarity', return_value=0.8):
        results = await retriever.retrieve(
            query="TLIF fusion outcomes",
            top_k=5,
            strategy=RetrievalStrategy.COLLAPSED
        )

    assert len(results) <= 5
    assert all(isinstance(node, TreeNode) for node, score in results)
    assert all(isinstance(score, float) for node, score in results)


@pytest.mark.asyncio
async def test_raptor_retriever_tree_traversal(sample_chunks, mock_gemini_client):
    """Test tree traversal retrieval strategy."""
    tree = RAPTORTree(
        summarization_engine=SummarizationEngine(gemini_client=mock_gemini_client),
        max_levels=2
    )

    with patch.object(tree, '_get_embedding', return_value=[0.1]*3072):
        await tree.build_tree(sample_chunks)

    # Mock embedding generator for retriever
    mock_emb_gen = MagicMock()
    mock_emb_gen.embed = MagicMock(return_value=[0.1]*3072)
    retriever = RAPTORRetriever(tree, embedding_generator=mock_emb_gen)

    with patch.object(retriever, '_cosine_similarity', return_value=0.8):
        results = await retriever.retrieve(
            query="spine surgery outcomes",
            top_k=3,
            strategy=RetrievalStrategy.TREE_TRAVERSAL
        )

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_raptor_retriever_adaptive(sample_chunks, mock_gemini_client):
    """Test adaptive retrieval strategy."""
    tree = RAPTORTree(
        summarization_engine=SummarizationEngine(gemini_client=mock_gemini_client),
        max_levels=2
    )

    with patch.object(tree, '_get_embedding', return_value=[0.1]*3072):
        await tree.build_tree(sample_chunks)

    # Mock embedding generator for retriever
    mock_emb_gen = MagicMock()
    mock_emb_gen.embed = MagicMock(return_value=[0.1]*3072)
    retriever = RAPTORRetriever(tree, embedding_generator=mock_emb_gen)

    # Test with detail-seeking query
    with patch.object(retriever, '_cosine_similarity', return_value=0.8):
        results_detailed = await retriever.retrieve(
            query="What are the specific statistical p-values?",
            top_k=5,
            strategy=RetrievalStrategy.ADAPTIVE
        )

    # Should prefer leaf nodes for detailed queries
    leaf_count = sum(1 for node, _ in results_detailed if node.is_leaf)
    assert leaf_count > 0


# RAPTORPipeline Tests

@pytest.mark.asyncio
async def test_raptor_pipeline_index_documents(sample_chunks, mock_gemini_client):
    """Test document indexing pipeline."""
    with patch('src.solver.raptor.SummarizationEngine') as mock_sum_engine:
        mock_sum_engine.return_value.summarize_cluster = mock_gemini_client.generate_text

        pipeline = RAPTORPipeline(config={"max_levels": 2})
        pipeline.summarization_engine = SummarizationEngine(gemini_client=mock_gemini_client)

        with patch.object(pipeline.tree, '_get_embedding', return_value=[0.1]*3072):
            doc_id = await pipeline.index_documents(sample_chunks)

    assert doc_id == "doc_1"
    assert pipeline.retriever is not None
    assert doc_id in pipeline._trees


@pytest.mark.asyncio
async def test_raptor_pipeline_search(sample_chunks, mock_gemini_client):
    """Test pipeline search functionality."""
    sum_engine = SummarizationEngine(gemini_client=mock_gemini_client)
    pipeline = RAPTORPipeline(config={"max_levels": 2}, summarization_engine=sum_engine)

    with patch.object(pipeline.tree, '_get_embedding', return_value=[0.1]*3072):
        await pipeline.index_documents(sample_chunks)

    # Mock embedding generator for retriever
    mock_emb_gen = MagicMock()
    mock_emb_gen.embed = MagicMock(return_value=[0.1]*3072)
    pipeline.retriever.embedding_generator = mock_emb_gen

    results = await pipeline.search(
        query="TLIF outcomes",
        top_k=3,
        strategy=RetrievalStrategy.COLLAPSED
    )

    assert len(results) <= 3
    assert all("node_id" in r for r in results)
    assert all("content" in r for r in results)
    assert all("score" in r for r in results)
    assert all("level" in r for r in results)


@pytest.mark.asyncio
async def test_raptor_pipeline_get_context(sample_chunks, mock_gemini_client):
    """Test context generation for LLM."""
    sum_engine = SummarizationEngine(gemini_client=mock_gemini_client)
    pipeline = RAPTORPipeline(config={"max_levels": 2}, summarization_engine=sum_engine)

    with patch.object(pipeline.tree, '_get_embedding', return_value=[0.1]*3072):
        await pipeline.index_documents(sample_chunks)

    # Mock embedding generator for retriever
    mock_emb_gen = MagicMock()
    mock_emb_gen.embed = MagicMock(return_value=[0.1]*3072)
    pipeline.retriever.embedding_generator = mock_emb_gen

    context = await pipeline.get_context(
        query="spine surgery",
        max_tokens=1000,
        strategy=RetrievalStrategy.ADAPTIVE
    )

    assert len(context) > 0
    assert len(context) <= 4000  # max_tokens * 4 chars
    assert "[Level" in context or "[Original]" in context


@pytest.mark.asyncio
async def test_raptor_pipeline_empty_documents(mock_gemini_client):
    """Test pipeline with empty document list."""
    sum_engine = SummarizationEngine(gemini_client=mock_gemini_client)
    pipeline = RAPTORPipeline(summarization_engine=sum_engine)

    with pytest.raises(ValueError, match="Cannot index empty chunk list"):
        await pipeline.index_documents([])


@pytest.mark.asyncio
async def test_raptor_pipeline_search_before_index(mock_gemini_client):
    """Test search before indexing documents."""
    sum_engine = SummarizationEngine(gemini_client=mock_gemini_client)
    pipeline = RAPTORPipeline(summarization_engine=sum_engine)

    with pytest.raises(ValueError, match="No documents indexed yet"):
        await pipeline.search("test query")


# Integration Tests

@pytest.mark.asyncio
async def test_end_to_end_raptor_flow(sample_chunks, mock_gemini_client):
    """Test complete RAPTOR flow from indexing to retrieval."""
    # Create pipeline
    sum_engine = SummarizationEngine(gemini_client=mock_gemini_client)
    pipeline = RAPTORPipeline(
        config={
            "max_levels": 3,
            "min_cluster_size": 2,
            "max_cluster_size": 5
        },
        summarization_engine=sum_engine
    )

    with patch.object(pipeline.tree, '_get_embedding', return_value=[0.1]*3072):
        # Index documents
        doc_id = await pipeline.index_documents(sample_chunks)
        assert doc_id is not None

        # Mock embedding generator for retriever
        mock_emb_gen = MagicMock()
        mock_emb_gen.embed = MagicMock(return_value=[0.1]*3072)
        pipeline.retriever.embedding_generator = mock_emb_gen

        # Search with different strategies
        collapsed_results = await pipeline.search(
            "TLIF fusion outcomes",
            top_k=5,
            strategy=RetrievalStrategy.COLLAPSED
        )

        tree_results = await pipeline.search(
            "spine surgery statistics",
            top_k=5,
            strategy=RetrievalStrategy.TREE_TRAVERSAL
        )

        adaptive_results = await pipeline.search(
            "What are the exact p-values for fusion rates?",
            top_k=5,
            strategy=RetrievalStrategy.ADAPTIVE
        )

        # Verify all strategies return results
        assert len(collapsed_results) > 0
        assert len(tree_results) > 0
        assert len(adaptive_results) > 0

        # Get context
        context = await pipeline.get_context("TLIF outcomes")
        assert len(context) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

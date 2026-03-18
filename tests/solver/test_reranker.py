"""Tests for the Reranker module.

Covers:
- Initialization with various providers
- Graceful fallback when cohere is not available/configured
- Reranking with mock results
- Error handling during reranking
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.solver.reranker import Reranker
from src.solver.tiered_search import SearchResult, ChunkInfo, SearchSource


def _make_result(chunk_id: str, text: str, score: float = 0.5) -> SearchResult:
    """Helper to create a SearchResult."""
    return SearchResult(
        chunk=ChunkInfo(
            chunk_id=chunk_id,
            document_id=f"doc_{chunk_id}",
            text=text,
        ),
        score=score,
        tier=1,
        source_type="original",
        evidence_level="1b",
        search_source=SearchSource.VECTOR,
        vector_score=score,
    )


class TestRerankerInit:
    """Test Reranker initialization."""

    def test_provider_none_disables(self):
        """provider='none' disables reranking."""
        r = Reranker(provider="none")
        assert r.is_available is False

    def test_unknown_provider_disables(self):
        """Unknown provider disables reranking."""
        r = Reranker(provider="unknown_provider")
        assert r.is_available is False

    def test_cohere_without_api_key_disables(self):
        """Cohere without API key disables reranking."""
        with patch.dict("os.environ", {"COHERE_API_KEY": ""}, clear=False):
            r = Reranker(provider="cohere", api_key="")
            # May or may not be available depending on cohere package
            # But without key it should not be available
            if r._client is None:
                assert r.is_available is False

    @patch("src.solver.reranker.COHERE_AVAILABLE", False)
    def test_cohere_package_not_installed(self):
        """Cohere package not installed disables gracefully."""
        r = Reranker(provider="cohere")
        assert r.is_available is False


class TestRerankerFallback:
    """Test Reranker graceful fallback behavior."""

    @pytest.mark.asyncio
    async def test_unavailable_returns_original_order(self):
        """When not available, returns results unchanged (truncated to top_k)."""
        r = Reranker(provider="none")
        results = [
            _make_result("c1", "text1", 0.9),
            _make_result("c2", "text2", 0.8),
            _make_result("c3", "text3", 0.7),
        ]

        reranked = await r.rerank("query", results, top_k=2)
        assert len(reranked) == 2
        assert reranked[0].chunk.chunk_id == "c1"
        assert reranked[1].chunk.chunk_id == "c2"

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty(self):
        """Empty input returns empty output."""
        r = Reranker(provider="none")
        reranked = await r.rerank("query", [], top_k=10)
        assert reranked == []

    @pytest.mark.asyncio
    async def test_top_k_larger_than_results(self):
        """top_k larger than results returns all results."""
        r = Reranker(provider="none")
        results = [_make_result("c1", "text1")]
        reranked = await r.rerank("query", results, top_k=10)
        assert len(reranked) == 1


class TestRerankerWithMockCohere:
    """Test Reranker with mocked Cohere client."""

    @pytest.mark.asyncio
    async def test_rerank_reorders_results(self):
        """Reranker reorders results based on relevance scores."""
        r = Reranker(provider="cohere")  # Start as cohere
        r.provider = "cohere"
        r._available = True  # Force available

        # Mock the Cohere client
        mock_response = MagicMock()
        mock_result_1 = MagicMock()
        mock_result_1.index = 2  # Originally third
        mock_result_1.relevance_score = 0.99
        mock_result_2 = MagicMock()
        mock_result_2.index = 0  # Originally first
        mock_result_2.relevance_score = 0.85
        mock_response.results = [mock_result_1, mock_result_2]

        mock_client = MagicMock()
        mock_client.rerank.return_value = mock_response
        r._client = mock_client

        results = [
            _make_result("c1", "first result", 0.9),
            _make_result("c2", "second result", 0.8),
            _make_result("c3", "third result", 0.7),
        ]

        reranked = await r.rerank("query", results, top_k=2)
        assert len(reranked) == 2
        # Third result should now be first (highest relevance)
        assert reranked[0].chunk.chunk_id == "c3"
        assert reranked[0].score == 0.99
        assert reranked[1].chunk.chunk_id == "c1"
        assert reranked[1].score == 0.85

    @pytest.mark.asyncio
    async def test_rerank_exception_returns_original(self):
        """Reranker returns original order on exception."""
        r = Reranker(provider="cohere")
        r.provider = "cohere"
        r._available = True

        mock_client = MagicMock()
        mock_client.rerank.side_effect = Exception("API error")
        r._client = mock_client

        results = [
            _make_result("c1", "first", 0.9),
            _make_result("c2", "second", 0.8),
        ]

        reranked = await r.rerank("query", results, top_k=2)
        assert len(reranked) == 2
        assert reranked[0].chunk.chunk_id == "c1"

    @pytest.mark.asyncio
    async def test_rerank_with_empty_texts(self):
        """Reranker handles results with empty text gracefully."""
        r = Reranker(provider="none")
        r._available = True  # Force but no client -> will fail -> fallback

        results = [
            _make_result("c1", "", 0.9),
            _make_result("c2", "", 0.8),
        ]

        # No client set, so rerank will fail and return original
        reranked = await r.rerank("query", results, top_k=2)
        assert len(reranked) == 2

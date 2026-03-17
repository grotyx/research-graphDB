"""Cross-Encoder Reranker module for search result refinement.

Supports Cohere Rerank API as the primary provider with graceful fallback
when the dependency is not available.

v1.27.0: Initial implementation
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Optional Cohere import
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    cohere = None  # type: ignore


class Reranker:
    """Cross-encoder reranker for improving search result relevance.

    Reranks initial retrieval results using a cross-encoder model
    (Cohere Rerank API) for better semantic matching.

    If Cohere is not available or not configured, returns results unchanged
    (graceful fallback with a logged warning).

    Args:
        provider: Reranking provider ("cohere" or "none").
        model: Cohere rerank model name.
        api_key: Cohere API key. Falls back to COHERE_API_KEY env var.
    """

    def __init__(
        self,
        provider: str = "cohere",
        model: str = "rerank-v3.5",
        api_key: Optional[str] = None,
    ) -> None:
        """Initialize the reranker."""
        self.provider = provider
        self.model = model
        self._client = None
        self._available = False

        if provider == "none":
            logger.info("Reranker: disabled (provider='none')")
            return

        if provider == "cohere":
            if not COHERE_AVAILABLE:
                logger.warning(
                    "Reranker: cohere package not installed. "
                    "Install with: pip install 'spine-graphrag[rerank]'. "
                    "Falling back to no reranking."
                )
                return

            resolved_key = api_key or os.environ.get("COHERE_API_KEY", "")
            if not resolved_key:
                logger.warning(
                    "Reranker: COHERE_API_KEY not set. "
                    "Falling back to no reranking."
                )
                return

            try:
                self._client = cohere.ClientV2(api_key=resolved_key)
                self._available = True
                logger.info(f"Reranker: Cohere initialized (model={model})")
            except Exception as e:
                logger.warning(f"Reranker: Failed to initialize Cohere client: {e}")
        else:
            logger.warning(f"Reranker: Unknown provider '{provider}', disabled.")

    @property
    def is_available(self) -> bool:
        """Whether the reranker is ready to use."""
        return self._available

    async def rerank(
        self,
        query: str,
        results: list,
        top_k: int = 10,
    ) -> list:
        """Rerank search results using cross-encoder scoring.

        Args:
            query: The original search query.
            results: List of SearchResult objects to rerank.
                     Each must have a `chunk` attribute with a `text` field.
            top_k: Number of top results to return after reranking.

        Returns:
            Reranked list of SearchResult objects, truncated to top_k.
            If reranking is unavailable, returns the original results
            truncated to top_k.
        """
        if not self._available or not results:
            return results[:top_k]

        # Extract texts for reranking
        documents = []
        for r in results:
            text = getattr(r.chunk, "text", "") if hasattr(r, "chunk") else ""
            documents.append(text)

        if not any(documents):
            return results[:top_k]

        try:
            response = self._client.rerank(
                query=query,
                documents=documents,
                top_n=min(top_k, len(documents)),
                model=self.model,
            )

            # Rebuild result list in reranked order
            reranked = []
            for item in response.results:
                idx = item.index
                if 0 <= idx < len(results):
                    result = results[idx]
                    # Preserve the rerank score as the new score
                    result.score = item.relevance_score
                    reranked.append(result)

            logger.info(
                f"Reranker: reranked {len(documents)} -> {len(reranked)} results "
                f"(top_k={top_k})"
            )
            return reranked

        except Exception as e:
            logger.warning(
                f"Reranker: reranking failed ({e}), returning original order"
            )
            return results[:top_k]

"""Semantic Cache for LLM Responses.

Extension of LLM cache with semantic similarity matching.
Similar queries can retrieve cached responses even with different wording.
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.llm_cache import LLMCache, generate_cache_key

logger = logging.getLogger(__name__)


@dataclass
class SemanticCacheEntry:
    """Semantic cache entry with embeddings.

    Attributes:
        cache_key: Original cache key
        query_text: Query text
        query_embedding: Query embedding vector
        response: Cached response
        similarity_threshold: Minimum similarity for match
    """
    cache_key: str
    query_text: str
    query_embedding: np.ndarray
    response: dict
    similarity_threshold: float = 0.85


class SemanticCache:
    """Semantic cache for LLM responses.

    Features:
    - Semantic similarity matching
    - Configurable similarity threshold
    - Falls back to exact match cache (LLMCache)
    - Automatic invalidation on data updates

    Workflow:
        1. Check exact match (LLMCache)
        2. If miss, check semantic similarity
        3. If semantic match found, return cached response
        4. Otherwise, generate new response and cache

    Usage:
        cache = SemanticCache(
            llm_cache=LLMCache(),
            embedding_cache=EmbeddingCache(),
            similarity_threshold=0.85
        )

        # Generate embedding for query
        query_embedding = embedding_model.encode(query)

        # Try to get cached response
        response = await cache.get(query, query_embedding, operation="summarize")

        if response is None:
            # Generate new response
            response = await llm_generate(query)

            # Cache it
            await cache.set(query, query_embedding, response, operation="summarize")
    """

    def __init__(
        self,
        llm_cache: LLMCache,
        embedding_cache: "EmbeddingCache",
        similarity_threshold: float = 0.85,
        max_semantic_entries: int = 1000
    ):
        """Initialize semantic cache.

        Args:
            llm_cache: Underlying LLM cache (exact match)
            embedding_cache: Embedding cache for query vectors
            similarity_threshold: Minimum cosine similarity (0-1)
            max_semantic_entries: Maximum number of semantic entries to track
        """
        self.llm_cache = llm_cache
        self.embedding_cache = embedding_cache
        self.similarity_threshold = similarity_threshold
        self.max_semantic_entries = max_semantic_entries

        # In-memory semantic index
        # (operation -> deque of SemanticCacheEntry)
        self._semantic_index: dict[str, deque[SemanticCacheEntry]] = {}

    async def get(
        self,
        query: str,
        query_embedding: np.ndarray,
        operation: str = "unknown",
        params: Optional[dict] = None
    ) -> Optional[dict]:
        """Get cached response with semantic matching.

        Args:
            query: Query text
            query_embedding: Query embedding vector
            operation: Operation type (for cache key)
            params: Additional parameters

        Returns:
            Cached response or None
        """
        # 1. Try exact match first (fastest)
        cache_key = generate_cache_key(operation, query, params)
        exact_match = await self.llm_cache.get(cache_key)

        if exact_match is not None:
            logger.debug(f"Semantic cache: exact match for '{query[:50]}...'")
            return exact_match

        # 2. Try semantic match
        semantic_match = self._find_semantic_match(
            query_embedding, operation, self.similarity_threshold
        )

        if semantic_match is not None:
            logger.info(f"Semantic cache: similarity match for '{query[:50]}...'")
            return semantic_match

        # 3. No match
        logger.debug(f"Semantic cache: miss for '{query[:50]}...'")
        return None

    async def set(
        self,
        query: str,
        query_embedding: np.ndarray,
        response: dict,
        operation: str = "unknown",
        params: Optional[dict] = None,
        metadata: Optional[dict] = None,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> None:
        """Cache response with semantic indexing.

        Args:
            query: Query text
            query_embedding: Query embedding vector
            response: LLM response to cache
            operation: Operation type
            params: Additional parameters
            metadata: Response metadata
            input_tokens: Input token count
            output_tokens: Output token count
        """
        # 1. Store in exact match cache
        cache_key = generate_cache_key(operation, query, params)
        await self.llm_cache.set(
            cache_key=cache_key,
            response=response,
            operation=operation,
            metadata=metadata,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

        # 2. Add to semantic index
        self._add_to_semantic_index(
            cache_key=cache_key,
            query_text=query,
            query_embedding=query_embedding,
            response=response,
            operation=operation
        )

        logger.debug(f"Semantic cache: stored '{query[:50]}...'")

    def _find_semantic_match(
        self,
        query_embedding: np.ndarray,
        operation: str,
        threshold: float
    ) -> Optional[dict]:
        """Find semantically similar cached entry.

        Args:
            query_embedding: Query embedding to match
            operation: Operation type
            threshold: Minimum similarity threshold

        Returns:
            Cached response or None
        """
        # Get entries for this operation
        entries = self._semantic_index.get(operation, [])
        if not entries:
            return None

        # Calculate similarities
        best_match: Optional[SemanticCacheEntry] = None
        best_similarity = threshold

        for entry in entries:
            similarity = self._cosine_similarity(query_embedding, entry.query_embedding)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = entry

        if best_match:
            logger.debug(f"Semantic match found: similarity={best_similarity:.3f}")
            return best_match.response

        return None

    def _add_to_semantic_index(
        self,
        cache_key: str,
        query_text: str,
        query_embedding: np.ndarray,
        response: dict,
        operation: str
    ) -> None:
        """Add entry to semantic index.

        Args:
            cache_key: Cache key
            query_text: Query text
            query_embedding: Query embedding
            response: Cached response
            operation: Operation type
        """
        # Create entry
        entry = SemanticCacheEntry(
            cache_key=cache_key,
            query_text=query_text,
            query_embedding=query_embedding,
            response=response,
            similarity_threshold=self.similarity_threshold
        )

        # Add to index
        if operation not in self._semantic_index:
            self._semantic_index[operation] = deque(maxlen=self.max_semantic_entries)

        self._semantic_index[operation].append(entry)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Cosine similarity (0-1)
        """
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    async def invalidate_operation(self, operation: str) -> int:
        """Invalidate all cache entries for an operation.

        Args:
            operation: Operation type

        Returns:
            Number of entries invalidated
        """
        # Clear semantic index
        count_semantic = len(self._semantic_index.get(operation, []))
        if operation in self._semantic_index:
            del self._semantic_index[operation]

        # Clear exact match cache
        count_exact = await self.llm_cache.invalidate_by_operation(operation)

        total = count_semantic + count_exact
        if total > 0:
            logger.info(f"Invalidated {total} entries for operation '{operation}'")

        return total

    async def invalidate_all(self) -> None:
        """Clear all cache entries."""
        # Clear semantic index
        self._semantic_index.clear()

        # Clear exact match cache
        await self.llm_cache.cleanup_expired()

        logger.info("All semantic cache entries cleared")

    def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        # Count semantic entries
        semantic_count = sum(len(entries) for entries in self._semantic_index.values())

        return {
            "semantic_entries": semantic_count,
            "semantic_operations": len(self._semantic_index),
            "similarity_threshold": self.similarity_threshold,
            "max_entries_per_operation": self.max_semantic_entries,
        }


# Example usage
if __name__ == "__main__":
    import asyncio

    async def main():
        from core.llm_cache import LLMCache
        from .embedding_cache import EmbeddingCache

        # Initialize caches
        llm_cache = LLMCache(db_path="test_llm.db")
        embedding_cache = EmbeddingCache(db_path="test_embeddings.db")
        semantic_cache = SemanticCache(
            llm_cache=llm_cache,
            embedding_cache=embedding_cache,
            similarity_threshold=0.85
        )

        # Simulate embeddings
        query1 = "What are effective treatments for lumbar stenosis?"
        query2 = "Which treatments work well for lumbar stenosis?"  # Similar
        query3 = "What is the fusion rate for TLIF?"  # Different

        embedding1 = np.random.rand(768)
        embedding2 = embedding1 + np.random.rand(768) * 0.1  # Similar
        embedding3 = np.random.rand(768)  # Different

        # Cache response for query1
        response1 = {"answer": "Effective treatments include..."}
        await semantic_cache.set(
            query1, embedding1, response1, operation="summarize"
        )

        # Try to get query2 (should match semantically)
        cached = await semantic_cache.get(
            query2, embedding2, operation="summarize"
        )
        print(f"Query2 cached: {cached is not None}")

        # Try to get query3 (should not match)
        cached = await semantic_cache.get(
            query3, embedding3, operation="summarize"
        )
        print(f"Query3 cached: {cached is not None}")

        # Stats
        stats = semantic_cache.get_stats()
        print(f"Semantic cache stats: {stats}")

        # Cleanup
        import os
        os.unlink("test_llm.db")
        os.unlink("test_embeddings.db")

    asyncio.run(main())

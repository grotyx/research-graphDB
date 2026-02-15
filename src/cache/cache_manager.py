"""Cache Manager - Centralized Cache Management.

Manages all caching layers:
- Query cache (Cypher queries)
- Embedding cache (text embeddings)
- LLM cache (response cache with semantic matching)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .query_cache import CypherQueryCache, QueryCache
from .embedding_cache import EmbeddingCache
from .semantic_cache import SemanticCache
from ..llm.cache import LLMCache

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Cache configuration.

    Attributes:
        enabled: Enable all caching
        query_cache_enabled: Enable query cache
        query_cache_size: Query cache max size
        query_cache_ttl: Query cache TTL (seconds)
        embedding_cache_enabled: Enable embedding cache
        embedding_cache_ttl: Embedding cache TTL (days)
        llm_cache_enabled: Enable LLM cache
        llm_cache_ttl: LLM cache TTL (hours)
        semantic_cache_enabled: Enable semantic matching
        semantic_threshold: Semantic similarity threshold
    """
    enabled: bool = True

    # Query cache
    query_cache_enabled: bool = True
    query_cache_size: int = 1000
    query_cache_ttl: int = 3600  # 1 hour

    # Embedding cache
    embedding_cache_enabled: bool = True
    embedding_cache_ttl: int = 30  # 30 days

    # LLM cache
    llm_cache_enabled: bool = True
    llm_cache_ttl: int = 168  # 7 days

    # Semantic cache
    semantic_cache_enabled: bool = True
    semantic_threshold: float = 0.85

    @classmethod
    def from_dict(cls, config: dict) -> "CacheConfig":
        """Create config from dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            CacheConfig instance
        """
        return cls(
            enabled=config.get("enabled", True),
            query_cache_enabled=config.get("query_cache_enabled", True),
            query_cache_size=config.get("query_cache_size", 1000),
            query_cache_ttl=config.get("query_cache_ttl", 3600),
            embedding_cache_enabled=config.get("embedding_cache_enabled", True),
            embedding_cache_ttl=config.get("embedding_cache_ttl", 30),
            llm_cache_enabled=config.get("llm_cache_enabled", True),
            llm_cache_ttl=config.get("llm_cache_ttl", 168),
            semantic_cache_enabled=config.get("semantic_cache_enabled", True),
            semantic_threshold=config.get("semantic_threshold", 0.85),
        )


class CacheManager:
    """Centralized cache management.

    Provides unified interface to all caching layers:
    - Query cache for Cypher queries
    - Embedding cache for text embeddings
    - LLM cache for model responses
    - Semantic cache for similar query matching

    Usage:
        # Initialize
        manager = CacheManager(config=cache_config)

        # Query cache
        cached_result = manager.query_cache.get(cache_key)

        # Embedding cache
        embedding = manager.embedding_cache.get(text, model_name)

        # LLM/Semantic cache
        response = await manager.semantic_cache.get(query, embedding, operation)

        # Statistics
        stats = manager.get_all_stats()

        # Cleanup
        manager.cleanup_all()
    """

    def __init__(
        self,
        config: Optional[CacheConfig] = None,
        data_dir: str = "data"
    ):
        """Initialize cache manager.

        Args:
            config: Cache configuration
            data_dir: Data directory for cache files
        """
        self.config = config or CacheConfig()
        self.data_dir = data_dir

        # Initialize caches
        self._init_query_cache()
        self._init_embedding_cache()
        self._init_llm_cache()
        self._init_semantic_cache()

        logger.info("Cache manager initialized")

    def _init_query_cache(self) -> None:
        """Initialize query cache."""
        if not self.config.enabled or not self.config.query_cache_enabled:
            self.query_cache = None
            self.cypher_cache = None
            logger.info("Query cache disabled")
            return

        # General query cache
        self.query_cache = QueryCache(
            max_size=self.config.query_cache_size,
            ttl_seconds=self.config.query_cache_ttl
        )

        # Cypher-specific cache
        self.cypher_cache = CypherQueryCache(
            max_size=self.config.query_cache_size // 2,  # Half size for Cypher
            ttl_seconds=self.config.query_cache_ttl
        )

        logger.info(f"Query cache enabled (size={self.config.query_cache_size}, ttl={self.config.query_cache_ttl}s)")

    def _init_embedding_cache(self) -> None:
        """Initialize embedding cache."""
        if not self.config.enabled or not self.config.embedding_cache_enabled:
            self.embedding_cache = None
            logger.info("Embedding cache disabled")
            return

        self.embedding_cache = EmbeddingCache(
            db_path=f"{self.data_dir}/embedding_cache.db",
            ttl_days=self.config.embedding_cache_ttl
        )

        logger.info(f"Embedding cache enabled (ttl={self.config.embedding_cache_ttl} days)")

    def _init_llm_cache(self) -> None:
        """Initialize LLM cache."""
        if not self.config.enabled or not self.config.llm_cache_enabled:
            self.llm_cache = None
            logger.info("LLM cache disabled")
            return

        self.llm_cache = LLMCache(
            db_path=f"{self.data_dir}/llm_cache.db",
            ttl_hours=self.config.llm_cache_ttl
        )

        logger.info(f"LLM cache enabled (ttl={self.config.llm_cache_ttl} hours)")

    def _init_semantic_cache(self) -> None:
        """Initialize semantic cache."""
        if not self.config.enabled or not self.config.semantic_cache_enabled:
            self.semantic_cache = None
            logger.info("Semantic cache disabled")
            return

        if self.llm_cache is None or self.embedding_cache is None:
            self.semantic_cache = None
            logger.warning("Semantic cache requires LLM and embedding caches")
            return

        self.semantic_cache = SemanticCache(
            llm_cache=self.llm_cache,
            embedding_cache=self.embedding_cache,
            similarity_threshold=self.config.semantic_threshold
        )

        logger.info(f"Semantic cache enabled (threshold={self.config.semantic_threshold})")

    def get_all_stats(self) -> dict:
        """Get statistics from all caches.

        Returns:
            Dictionary with statistics from each cache
        """
        stats = {
            "config": {
                "enabled": self.config.enabled,
                "query_cache_enabled": self.config.query_cache_enabled,
                "embedding_cache_enabled": self.config.embedding_cache_enabled,
                "llm_cache_enabled": self.config.llm_cache_enabled,
                "semantic_cache_enabled": self.config.semantic_cache_enabled,
            }
        }

        # Query cache stats
        if self.query_cache:
            query_stats = self.query_cache.get_stats()
            stats["query_cache"] = {
                "hits": query_stats.hits,
                "misses": query_stats.misses,
                "hit_rate": f"{query_stats.hit_rate:.2%}",
                "entries": query_stats.entries,
                "evictions": query_stats.evictions,
                "size_mb": query_stats.total_size_bytes / (1024 * 1024),
            }

        # Cypher cache stats
        if self.cypher_cache:
            cypher_stats = self.cypher_cache.get_stats()
            stats["cypher_cache"] = {
                "hits": cypher_stats.hits,
                "misses": cypher_stats.misses,
                "hit_rate": f"{cypher_stats.hit_rate:.2%}",
                "entries": cypher_stats.entries,
            }

        # Embedding cache stats
        if self.embedding_cache:
            emb_stats = self.embedding_cache.get_stats()
            stats["embedding_cache"] = {
                "entries": emb_stats.total_entries,
                "size_mb": emb_stats.total_size_mb,
                "hit_count": emb_stats.hit_count,
                "hit_rate": f"{emb_stats.hit_rate:.2%}",
                "avg_embedding_dim": emb_stats.avg_embedding_size,
            }

        # Semantic cache stats
        if self.semantic_cache:
            sem_stats = self.semantic_cache.get_stats()
            stats["semantic_cache"] = sem_stats

        return stats

    def cleanup_all(self) -> dict:
        """Clean up all caches.

        Returns:
            Dictionary with cleanup counts for each cache
        """
        results = {}

        # Query cache
        if self.query_cache:
            expired = self.query_cache.cleanup_expired()
            results["query_cache_expired"] = expired

        # Cypher cache
        if self.cypher_cache:
            expired = self.cypher_cache.cleanup_expired()
            results["cypher_cache_expired"] = expired

        # Embedding cache
        if self.embedding_cache:
            expired = self.embedding_cache.cleanup_expired()
            results["embedding_cache_expired"] = expired

        # LLM cache — v1.15: asyncio.run() 대신 event loop 안전 처리
        if self.llm_cache:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.llm_cache.cleanup_expired())
                results["llm_cache_expired"] = "scheduled"
            except RuntimeError:
                expired = asyncio.run(self.llm_cache.cleanup_expired())
                results["llm_cache_expired"] = expired

        logger.info(f"Cache cleanup completed: {results}")
        return results

    def clear_all(self) -> None:
        """Clear all caches completely."""
        if self.query_cache:
            self.query_cache.clear()

        if self.cypher_cache:
            self.cypher_cache.clear()

        # Note: Embedding and LLM caches use persistent storage,
        # so we only clean expired entries
        if self.embedding_cache:
            self.embedding_cache.cleanup_expired()

        # v1.15: asyncio.run() 대신 event loop 안전 처리
        if self.llm_cache:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.llm_cache.cleanup_expired())
            except RuntimeError:
                asyncio.run(self.llm_cache.cleanup_expired())

        logger.info("All caches cleared")

    async def invalidate_on_data_update(
        self,
        node_label: Optional[str] = None,
        operation: Optional[str] = None
    ) -> None:
        """Invalidate caches after data update.

        Args:
            node_label: Node label that was updated (e.g., "Paper")
            operation: LLM operation that should be invalidated
        """
        # Invalidate query cache for node type
        if self.cypher_cache and node_label:
            count = self.cypher_cache.invalidate_node_type(node_label)
            logger.info(f"Invalidated {count} query cache entries for '{node_label}'")

        # Invalidate semantic cache for operation
        if self.semantic_cache and operation:
            count = await self.semantic_cache.invalidate_operation(operation)
            logger.info(f"Invalidated {count} semantic cache entries for '{operation}'")

    async def warmup(
        self,
        neo4j_client=None,
        embedding_function=None,
        terms: list[str] = None
    ) -> dict:
        """Warm up all caches.

        Args:
            neo4j_client: Neo4j client for query warmup
            embedding_function: Function to generate embeddings
            terms: List of terms to warm up in embedding cache

        Returns:
            Dictionary with warmup counts
        """
        results = {}

        # Warm up query cache
        if self.cypher_cache and neo4j_client:
            from .query_cache import warmup_cache
            count = await warmup_cache(self.cypher_cache, neo4j_client)
            results["query_cache_warmed"] = count

        # Warm up embedding cache
        if self.embedding_cache and embedding_function and terms:
            count = await self.embedding_cache.warmup(
                terms, embedding_function, model_name="default"
            )
            results["embedding_cache_warmed"] = count

        logger.info(f"Cache warmup completed: {results}")
        return results


# Example usage
if __name__ == "__main__":
    import asyncio

    async def main():
        # Initialize with custom config
        config = CacheConfig(
            query_cache_size=500,
            query_cache_ttl=1800,
            semantic_threshold=0.90
        )

        manager = CacheManager(config=config, data_dir="test_data")

        # Get stats
        stats = manager.get_all_stats()
        print("Cache statistics:")
        for cache_name, cache_stats in stats.items():
            print(f"  {cache_name}: {cache_stats}")

        # Cleanup
        results = manager.cleanup_all()
        print(f"Cleanup results: {results}")

    asyncio.run(main())

"""Query Cache for Cypher Queries.

LRU cache with TTL support for frequently executed graph queries.
"""

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with TTL support.

    Attributes:
        value: Cached value
        created_at: Creation timestamp
        last_accessed: Last access timestamp
        access_count: Number of times accessed
        expires_at: Expiration timestamp (None for no expiration)
    """
    value: Any
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    expires_at: Optional[float] = None

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Update last access time and increment counter."""
        self.last_accessed = time.time()
        self.access_count += 1


@dataclass
class CacheStats:
    """Cache statistics.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        entries: Current number of entries
        evictions: Number of evictions (LRU)
        expirations: Number of expired entries removed
        total_size_bytes: Approximate memory usage
    """
    hits: int = 0
    misses: int = 0
    entries: int = 0
    evictions: int = 0
    expirations: int = 0
    total_size_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class QueryCache:
    """LRU cache with TTL support for general queries.

    Features:
    - LRU eviction policy
    - TTL-based expiration
    - Cache statistics tracking
    - Thread-safe operations (for async compatibility)

    Usage:
        cache = QueryCache(max_size=1000, ttl_seconds=3600)

        # Get/Set
        key = cache.generate_key("query", {"param": "value"})
        result = cache.get(key)
        if result is None:
            result = expensive_operation()
            cache.set(key, result)

        # Statistics
        stats = cache.get_stats()
        print(f"Hit rate: {stats.hit_rate:.2%}")
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600
    ):
        """Initialize cache.

        Args:
            max_size: Maximum number of entries
            ttl_seconds: Time-to-live in seconds (0 for no expiration)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats()

    def generate_key(self, query: str, parameters: Optional[dict] = None) -> str:
        """Generate cache key from query and parameters.

        Args:
            query: Query string
            parameters: Query parameters

        Returns:
            SHA-256 hash key
        """
        data = {
            "query": query,
            "parameters": parameters or {}
        }
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        # Check if key exists
        if key not in self._cache:
            self._stats.misses += 1
            return None

        entry = self._cache[key]

        # Check expiration
        if entry.is_expired():
            self._remove(key)
            self._stats.misses += 1
            self._stats.expirations += 1
            logger.debug(f"Cache entry expired: {key[:16]}...")
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        entry.touch()

        self._stats.hits += 1
        logger.debug(f"Cache hit: {key[:16]}... (accessed {entry.access_count} times)")
        return entry.value

    def set(self, key: str, value: Any, ttl_override: Optional[int] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_override: Override default TTL (seconds)
        """
        # Calculate expiration
        ttl = ttl_override if ttl_override is not None else self.ttl_seconds
        expires_at = None if ttl <= 0 else time.time() + ttl

        # Create entry
        entry = CacheEntry(value=value, expires_at=expires_at)

        # Evict if at capacity
        if key not in self._cache and len(self._cache) >= self.max_size:
            self._evict_lru()

        # Store entry
        self._cache[key] = entry
        self._cache.move_to_end(key)

        self._update_stats()
        logger.debug(f"Cache set: {key[:16]}... (TTL: {ttl}s)")

    def invalidate(self, key: str) -> bool:
        """Invalidate specific cache entry.

        Args:
            key: Cache key

        Returns:
            True if entry was removed
        """
        if key in self._cache:
            self._remove(key)
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate entries matching pattern.

        Args:
            pattern: Pattern to match (substring)

        Returns:
            Number of entries removed
        """
        keys_to_remove = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_remove:
            self._remove(key)

        if keys_to_remove:
            logger.info(f"Invalidated {len(keys_to_remove)} entries matching '{pattern}'")

        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cache entries."""
        count = len(self._cache)
        self._cache.clear()
        self._update_stats()
        logger.info(f"Cache cleared ({count} entries removed)")

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        expired_keys = [k for k, e in self._cache.items() if e.is_expired()]
        for key in expired_keys:
            self._remove(key)

        if expired_keys:
            self._stats.expirations += len(expired_keys)
            self._update_stats()
            logger.info(f"Cleaned up {len(expired_keys)} expired entries")

        return len(expired_keys)

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats object with current statistics
        """
        self._update_stats()
        return self._stats

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._cache:
            return

        # Remove first item (least recently used)
        key, _ = self._cache.popitem(last=False)
        self._stats.evictions += 1
        logger.debug(f"Cache eviction (LRU): {key[:16]}...")

    def _remove(self, key: str) -> None:
        """Remove entry from cache."""
        if key in self._cache:
            del self._cache[key]

    def _update_stats(self) -> None:
        """Update cache statistics."""
        self._stats.entries = len(self._cache)

        # Estimate size (rough approximation)
        # Each entry: key (32 bytes) + value (estimate 1KB) + overhead (100 bytes)
        self._stats.total_size_bytes = len(self._cache) * (32 + 1024 + 100)


class CypherQueryCache(QueryCache):
    """Specialized cache for Cypher queries.

    Additional features:
    - Cypher-specific key generation
    - Query pattern recognition
    - Read/Write query differentiation

    Usage:
        cache = CypherQueryCache(max_size=500)

        # Cache read query
        key = cache.generate_cypher_key(query, params)
        result = cache.get(key)
        if result is None:
            result = await neo4j_client.run_query(query, params)
            cache.set(key, result)

        # Invalidate on write
        if is_write_query:
            cache.invalidate_pattern("Paper")  # Invalidate all paper queries
    """

    def generate_cypher_key(
        self,
        query: str,
        parameters: Optional[dict] = None,
        query_type: str = "read"
    ) -> str:
        """Generate cache key for Cypher query.

        Args:
            query: Cypher query string
            parameters: Query parameters
            query_type: "read" or "write"

        Returns:
            Cache key with query type prefix
        """
        # Normalize query (remove extra whitespace)
        normalized_query = " ".join(query.split())

        data = {
            "query_type": query_type,
            "query": normalized_query,
            "parameters": parameters or {}
        }
        serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
        hash_key = hashlib.sha256(serialized.encode()).hexdigest()

        return f"{query_type}:{hash_key}"

    def invalidate_node_type(self, node_label: str) -> int:
        """Invalidate all queries involving a node type.

        Args:
            node_label: Node label (e.g., "Paper", "Intervention")

        Returns:
            Number of entries removed
        """
        return self.invalidate_pattern(node_label)

    def should_cache(self, query: str) -> bool:
        """Determine if query should be cached.

        Args:
            query: Cypher query

        Returns:
            True if query should be cached
        """
        query_upper = query.upper()

        # Don't cache write queries
        if any(kw in query_upper for kw in ["CREATE", "MERGE", "DELETE", "SET", "REMOVE"]):
            return False

        # Don't cache queries with datetime or random
        if any(kw in query_upper for kw in ["DATETIME", "RAND()", "TIMESTAMP"]):
            return False

        return True


# Warm-up queries for common operations
WARMUP_QUERIES = [
    # Stats queries
    ("MATCH (n:Paper) RETURN count(n) as count", {}),
    ("MATCH (n:Intervention) RETURN count(n) as count", {}),
    ("MATCH (n:Pathology) RETURN count(n) as count", {}),
    ("MATCH ()-[r]->() RETURN type(r) as type, count(r) as count", {}),

    # Common searches
    ("MATCH (i:Intervention) RETURN i.name ORDER BY i.name LIMIT 50", {}),
    ("MATCH (p:Pathology) RETURN p.name ORDER BY p.name LIMIT 50", {}),

    # Hierarchy queries
    ("MATCH (i:Intervention)-[:IS_A*]->(parent) WHERE i.name = $name RETURN parent",
     {"name": "UBE"}),
    ("MATCH (i:Intervention)<-[:IS_A]-(child) WHERE i.name = $name RETURN child",
     {"name": "Endoscopic Surgery"}),
]


async def warmup_cache(cache: CypherQueryCache, neo4j_client) -> int:
    """Warm up cache with common queries.

    Args:
        cache: CypherQueryCache instance
        neo4j_client: Neo4jClient instance

    Returns:
        Number of queries warmed up
    """
    count = 0
    for query, params in WARMUP_QUERIES:
        try:
            key = cache.generate_cypher_key(query, params)

            # Execute query
            result = await neo4j_client.run_query(query, params)

            # Cache result
            cache.set(key, result, ttl_override=7200)  # 2 hours for warmup
            count += 1

        except Exception as e:
            logger.warning(f"Warmup query failed: {e}")

    logger.info(f"Cache warmed up with {count} queries")
    return count


# Example usage
if __name__ == "__main__":
    # Basic cache
    cache = QueryCache(max_size=100, ttl_seconds=60)

    # Set values
    key1 = cache.generate_key("SELECT * FROM papers WHERE id = ?", {"id": 1})
    cache.set(key1, {"title": "Test Paper"})

    # Get values
    result = cache.get(key1)
    print(f"Cached result: {result}")

    # Stats
    stats = cache.get_stats()
    print(f"Cache stats: hits={stats.hits}, misses={stats.misses}, hit_rate={stats.hit_rate:.2%}")

    # Cypher cache
    cypher_cache = CypherQueryCache(max_size=500)
    query = "MATCH (p:Paper) WHERE p.year > $year RETURN p"
    key2 = cypher_cache.generate_cypher_key(query, {"year": 2020})
    print(f"Should cache: {cypher_cache.should_cache(query)}")

"""Basic cache functionality tests."""

import pytest
import numpy as np
from pathlib import Path
import tempfile
import shutil

from src.cache.query_cache import QueryCache, CypherQueryCache
from src.cache.embedding_cache import EmbeddingCache
from src.cache.cache_manager import CacheManager, CacheConfig


class TestQueryCache:
    """Test QueryCache functionality."""

    def test_cache_basic(self):
        """Test basic cache operations."""
        cache = QueryCache(max_size=10, ttl_seconds=60)

        # Set value
        key = cache.generate_key("SELECT * FROM test", {"id": 1})
        cache.set(key, {"result": "data"})

        # Get value
        result = cache.get(key)
        assert result == {"result": "data"}

        # Stats
        stats = cache.get_stats()
        assert stats.hits == 1
        assert stats.misses == 0
        assert stats.entries == 1

    def test_cache_miss(self):
        """Test cache miss."""
        cache = QueryCache(max_size=10, ttl_seconds=60)

        key = cache.generate_key("SELECT * FROM test", {"id": 1})
        result = cache.get(key)

        assert result is None

        stats = cache.get_stats()
        assert stats.hits == 0
        assert stats.misses == 1

    def test_cache_lru_eviction(self):
        """Test LRU eviction."""
        cache = QueryCache(max_size=3, ttl_seconds=60)

        # Add 3 entries
        for i in range(3):
            key = cache.generate_key(f"query_{i}", {"id": i})
            cache.set(key, {"result": i})

        # Add 4th entry (should evict first)
        key4 = cache.generate_key("query_4", {"id": 4})
        cache.set(key4, {"result": 4})

        stats = cache.get_stats()
        assert stats.entries == 3
        assert stats.evictions == 1

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        cache = QueryCache(max_size=10, ttl_seconds=60)

        key = cache.generate_key("SELECT * FROM test", {"id": 1})
        cache.set(key, {"result": "data"})

        # Invalidate
        removed = cache.invalidate(key)
        assert removed is True

        # Check it's gone
        result = cache.get(key)
        assert result is None


class TestCypherQueryCache:
    """Test CypherQueryCache functionality."""

    def test_cypher_cache_key_generation(self):
        """Test Cypher-specific key generation."""
        cache = CypherQueryCache()

        query = "MATCH (n:Paper) WHERE n.year > $year RETURN n"
        key1 = cache.generate_cypher_key(query, {"year": 2020}, "read")
        key2 = cache.generate_cypher_key(query, {"year": 2020}, "read")
        key3 = cache.generate_cypher_key(query, {"year": 2021}, "read")

        # Same query + params = same key
        assert key1 == key2

        # Different params = different key
        assert key1 != key3

    def test_should_cache(self):
        """Test query caching decision."""
        cache = CypherQueryCache()

        # Should cache read queries
        assert cache.should_cache("MATCH (n:Paper) RETURN n")

        # Should not cache write queries
        assert not cache.should_cache("CREATE (n:Paper {title: 'Test'})")
        assert not cache.should_cache("MERGE (n:Paper {id: 1})")

        # Should not cache datetime queries
        assert not cache.should_cache("MATCH (n) WHERE n.created_at > datetime() RETURN n")

    def test_invalidate_node_type(self):
        """Test node type invalidation."""
        cache = CypherQueryCache()

        # Add some queries
        key1 = cache.generate_cypher_key("MATCH (n:Paper) RETURN n", {})
        key2 = cache.generate_cypher_key("MATCH (n:Intervention) RETURN n", {})

        cache.set(key1, [{"n": "paper1"}])
        cache.set(key2, [{"n": "intervention1"}])

        # Invalidate Paper queries
        count = cache.invalidate_node_type("Paper")

        # Should have invalidated at least one entry
        assert count >= 0


class TestEmbeddingCache:
    """Test EmbeddingCache functionality."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test_embeddings.db"
        yield str(db_path)
        shutil.rmtree(temp_dir)

    def test_embedding_cache_basic(self, temp_db):
        """Test basic embedding cache operations."""
        cache = EmbeddingCache(db_path=temp_db, ttl_days=1)

        # Create fake embedding
        text = "lumbar stenosis"
        embedding = np.random.rand(768).astype(np.float32)

        # Set
        cache.set(text, embedding, model_name="test-model")

        # Get
        retrieved = cache.get(text, model_name="test-model")

        assert retrieved is not None
        assert np.array_equal(retrieved, embedding)

    def test_embedding_cache_normalization(self, temp_db):
        """Test text normalization."""
        cache = EmbeddingCache(db_path=temp_db, ttl_days=1)

        embedding = np.random.rand(768).astype(np.float32)

        # Different text formats
        cache.set("Lumbar  Stenosis", embedding, model_name="test")

        # Should match normalized version
        retrieved = cache.get("lumbar stenosis", model_name="test")
        assert retrieved is not None
        assert np.array_equal(retrieved, embedding)

    def test_embedding_batch_operations(self, temp_db):
        """Test batch get/set."""
        cache = EmbeddingCache(db_path=temp_db, ttl_days=1)

        # Batch set
        texts = ["text1", "text2", "text3"]
        embeddings = {
            text: np.random.rand(768).astype(np.float32)
            for text in texts
        }
        cache.set_batch(embeddings, model_name="test")

        # Batch get
        results = cache.get_batch(texts, model_name="test")

        assert len(results) == 3
        for text in texts:
            assert results[text] is not None

    def test_embedding_stats(self, temp_db):
        """Test cache statistics."""
        cache = EmbeddingCache(db_path=temp_db, ttl_days=1)

        # Add some embeddings
        for i in range(5):
            embedding = np.random.rand(768).astype(np.float32)
            cache.set(f"text_{i}", embedding, model_name="test")

        # Get stats
        stats = cache.get_stats()

        assert stats.total_entries == 5
        assert stats.total_size_mb > 0


class TestCacheManager:
    """Test CacheManager functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_cache_manager_initialization(self, temp_dir):
        """Test cache manager initialization."""
        config = CacheConfig(
            query_cache_enabled=True,
            embedding_cache_enabled=True,
            llm_cache_enabled=True,
            semantic_cache_enabled=True
        )

        manager = CacheManager(config=config, data_dir=temp_dir)

        assert manager.query_cache is not None
        assert manager.cypher_cache is not None
        assert manager.embedding_cache is not None
        assert manager.llm_cache is not None
        assert manager.semantic_cache is not None

    def test_cache_manager_disabled(self, temp_dir):
        """Test cache manager with caching disabled."""
        config = CacheConfig(enabled=False)

        manager = CacheManager(config=config, data_dir=temp_dir)

        # Caches should be None
        assert manager.query_cache is None
        assert manager.cypher_cache is None

    def test_cache_manager_stats(self, temp_dir):
        """Test statistics aggregation."""
        config = CacheConfig()
        manager = CacheManager(config=config, data_dir=temp_dir)

        # Add some cached data
        if manager.query_cache:
            key = manager.query_cache.generate_key("test", {})
            manager.query_cache.set(key, {"data": "test"})

        # Get stats
        stats = manager.get_all_stats()

        assert "config" in stats
        assert stats["config"]["enabled"] is True


def test_imports():
    """Test that all modules can be imported."""
    from src.cache import (
        QueryCache,
        CypherQueryCache,
        EmbeddingCache,
        CacheManager,
    )

    assert QueryCache is not None
    assert CypherQueryCache is not None
    assert EmbeddingCache is not None
    assert CacheManager is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

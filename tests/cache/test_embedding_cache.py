"""Tests for EmbeddingCache module.

Tests persistent SQLite-based embedding cache:
- Cache get/set operations
- TTL-based expiration
- Cache hit/miss tracking
- Batch get/set operations
- Text normalization and hash generation
- Expired entry cleanup
- Model-specific cleanup
- Cache statistics
- Async warmup
- Edge cases: empty embeddings, concurrent access
"""

import pytest
import asyncio
import numpy as np
import sqlite3
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from cache.embedding_cache import EmbeddingCache, EmbeddingCacheStats


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def tmp_dir():
    """Create temporary directory for test databases."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def cache(tmp_dir):
    """EmbeddingCache with temporary database."""
    db_path = str(Path(tmp_dir) / "test_embeddings.db")
    return EmbeddingCache(db_path=db_path, ttl_days=30)


@pytest.fixture
def cache_no_ttl(tmp_dir):
    """EmbeddingCache with no TTL."""
    db_path = str(Path(tmp_dir) / "test_embeddings_no_ttl.db")
    return EmbeddingCache(db_path=db_path, ttl_days=0)


@pytest.fixture
def sample_embedding():
    """Sample 768-dimensional embedding."""
    return np.random.rand(768).astype(np.float32)


@pytest.fixture
def sample_embedding_3072():
    """Sample 3072-dimensional embedding (OpenAI text-embedding-3-large)."""
    return np.random.rand(3072).astype(np.float32)


# ===========================================================================
# Test: Initialization
# ===========================================================================

class TestEmbeddingCacheInit:
    """Test EmbeddingCache initialization."""

    def test_init_creates_db(self, tmp_dir):
        """Database file should be created on init."""
        db_path = str(Path(tmp_dir) / "new_cache.db")
        cache = EmbeddingCache(db_path=db_path)

        assert Path(db_path).exists()

    def test_init_creates_parent_dirs(self, tmp_dir):
        """Parent directories should be created."""
        db_path = str(Path(tmp_dir) / "subdir" / "cache.db")
        cache = EmbeddingCache(db_path=db_path)

        assert Path(db_path).exists()

    def test_init_default_ttl(self, tmp_dir):
        """Default TTL should be 30 days."""
        cache = EmbeddingCache(db_path=str(Path(tmp_dir) / "cache.db"))
        assert cache.ttl_days == 30

    def test_init_custom_ttl(self, tmp_dir):
        """Custom TTL should be set."""
        cache = EmbeddingCache(db_path=str(Path(tmp_dir) / "cache.db"), ttl_days=90)
        assert cache.ttl_days == 90

    def test_init_schema_created(self, tmp_dir):
        """Schema (embeddings table) should be created."""
        db_path = str(Path(tmp_dir) / "schema_test.db")
        cache = EmbeddingCache(db_path=db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_init_counters_zero(self, cache):
        """Hit/miss counters should start at 0."""
        assert cache._hit_count == 0
        assert cache._miss_count == 0


# ===========================================================================
# Test: Text Normalization
# ===========================================================================

class TestTextNormalization:
    """Test _normalize_text method."""

    def test_lowercase(self, cache):
        """Text should be lowercased."""
        assert cache._normalize_text("Hello World") == "hello world"

    def test_strip_whitespace(self, cache):
        """Leading/trailing whitespace should be stripped."""
        assert cache._normalize_text("  hello  ") == "hello"

    def test_collapse_spaces(self, cache):
        """Multiple spaces should be collapsed to one."""
        assert cache._normalize_text("hello   world") == "hello world"

    def test_combined_normalization(self, cache):
        """All normalization steps applied together."""
        assert cache._normalize_text("  Hello   WORLD  ") == "hello world"


# ===========================================================================
# Test: Hash Generation
# ===========================================================================

class TestHashGeneration:
    """Test _generate_hash method."""

    def test_deterministic(self, cache):
        """Same text + model should produce same hash."""
        h1 = cache._generate_hash("test text", "model_a")
        h2 = cache._generate_hash("test text", "model_a")
        assert h1 == h2

    def test_different_text(self, cache):
        """Different text should produce different hash."""
        h1 = cache._generate_hash("text one", "model_a")
        h2 = cache._generate_hash("text two", "model_a")
        assert h1 != h2

    def test_different_model(self, cache):
        """Different model should produce different hash."""
        h1 = cache._generate_hash("test text", "model_a")
        h2 = cache._generate_hash("test text", "model_b")
        assert h1 != h2

    def test_normalized_text_same_hash(self, cache):
        """Normalized-equivalent texts should produce same hash."""
        h1 = cache._generate_hash("Hello World", "model")
        h2 = cache._generate_hash("hello   world", "model")
        assert h1 == h2


# ===========================================================================
# Test: Get/Set Operations
# ===========================================================================

class TestGetSet:
    """Test get and set operations."""

    def test_set_and_get(self, cache, sample_embedding):
        """Set and immediately get should return the embedding."""
        cache.set("test text", sample_embedding, model_name="test-model")
        result = cache.get("test text", model_name="test-model")

        assert result is not None
        np.testing.assert_array_almost_equal(result, sample_embedding, decimal=5)

    def test_get_missing_returns_none(self, cache):
        """Get for uncached text returns None."""
        result = cache.get("uncached text", model_name="test-model")
        assert result is None

    def test_get_different_model_returns_none(self, cache, sample_embedding):
        """Get with different model_name returns None."""
        cache.set("test text", sample_embedding, model_name="model_a")
        result = cache.get("test text", model_name="model_b")
        assert result is None

    def test_set_overwrites(self, cache, sample_embedding):
        """Setting same key twice should overwrite."""
        cache.set("test text", sample_embedding, model_name="test-model")
        new_embedding = np.ones(768, dtype=np.float32)
        cache.set("test text", new_embedding, model_name="test-model")

        result = cache.get("test text", model_name="test-model")
        np.testing.assert_array_almost_equal(result, new_embedding, decimal=5)

    def test_default_model_name(self, cache, sample_embedding):
        """Default model_name should be 'default'."""
        cache.set("test text", sample_embedding)
        result = cache.get("test text")
        assert result is not None

    def test_large_embedding(self, cache, sample_embedding_3072):
        """3072-dimensional embedding should work."""
        cache.set("test text", sample_embedding_3072)
        result = cache.get("test text")

        assert result is not None
        assert result.shape == (3072,)

    def test_embedding_dtype_preserved(self, cache):
        """Embedding should be returned as float32."""
        emb = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        cache.set("test", emb)
        result = cache.get("test")

        assert result is not None
        assert result.dtype == np.float32


# ===========================================================================
# Test: Hit/Miss Tracking
# ===========================================================================

class TestHitMissTracking:
    """Test cache hit and miss counter tracking."""

    def test_hit_increments(self, cache, sample_embedding):
        """Cache hit should increment hit counter."""
        cache.set("test", sample_embedding)
        cache.get("test")
        assert cache._hit_count == 1

    def test_miss_increments(self, cache):
        """Cache miss should increment miss counter."""
        cache.get("uncached")
        assert cache._miss_count == 1

    def test_multiple_hits(self, cache, sample_embedding):
        """Multiple hits should accumulate."""
        cache.set("test", sample_embedding)
        cache.get("test")
        cache.get("test")
        cache.get("test")
        assert cache._hit_count == 3

    def test_db_hit_count_updated(self, cache, sample_embedding):
        """Database hit_count field should be updated."""
        cache.set("test", sample_embedding)
        cache.get("test")
        cache.get("test")

        # Check database directly
        conn = sqlite3.connect(cache.db_path)
        cursor = conn.execute("SELECT hit_count FROM embeddings LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        assert row[0] == 2


# ===========================================================================
# Test: TTL Expiration
# ===========================================================================

class TestTTLExpiration:
    """Test TTL-based expiration."""

    def test_expired_entry_returns_none(self, tmp_dir):
        """Expired entries should return None."""
        db_path = str(Path(tmp_dir) / "ttl_test.db")
        cache = EmbeddingCache(db_path=db_path, ttl_days=1)

        emb = np.array([1.0, 2.0], dtype=np.float32)
        cache.set("test", emb)

        # Manually set expiration to past
        conn = sqlite3.connect(db_path)
        past = (datetime.now() - timedelta(days=2)).isoformat()
        conn.execute("UPDATE embeddings SET expires_at = ?", (past,))
        conn.commit()
        conn.close()

        result = cache.get("test")
        assert result is None

    def test_expired_entry_counts_as_miss(self, tmp_dir):
        """Expired entry should count as a miss."""
        db_path = str(Path(tmp_dir) / "ttl_miss.db")
        cache = EmbeddingCache(db_path=db_path, ttl_days=1)

        emb = np.array([1.0, 2.0], dtype=np.float32)
        cache.set("test", emb)

        # Manually set expiration to past
        conn = sqlite3.connect(db_path)
        past = (datetime.now() - timedelta(days=2)).isoformat()
        conn.execute("UPDATE embeddings SET expires_at = ?", (past,))
        conn.commit()
        conn.close()

        cache.get("test")
        assert cache._miss_count == 1

    def test_no_ttl_never_expires(self, cache_no_ttl, sample_embedding):
        """Cache with ttl_days=0 should not set expires_at."""
        cache_no_ttl.set("test", sample_embedding)

        conn = sqlite3.connect(cache_no_ttl.db_path)
        cursor = conn.execute("SELECT expires_at FROM embeddings LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] is None

    def test_ttl_override(self, cache, sample_embedding):
        """ttl_override should override default TTL."""
        cache.set("test", sample_embedding, ttl_override=0)

        conn = sqlite3.connect(cache.db_path)
        cursor = conn.execute("SELECT expires_at FROM embeddings LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] is None  # 0 means no expiration


# ===========================================================================
# Test: Batch Operations
# ===========================================================================

class TestBatchOperations:
    """Test get_batch and set_batch methods."""

    def test_set_batch(self, cache):
        """Batch set should store multiple embeddings."""
        texts_embeddings = {
            "text_1": np.array([1.0, 2.0], dtype=np.float32),
            "text_2": np.array([3.0, 4.0], dtype=np.float32),
            "text_3": np.array([5.0, 6.0], dtype=np.float32),
        }
        cache.set_batch(texts_embeddings)

        result = cache.get("text_1")
        assert result is not None
        np.testing.assert_array_almost_equal(result, [1.0, 2.0], decimal=5)

    def test_set_batch_empty(self, cache):
        """Empty batch should be no-op."""
        cache.set_batch({})  # Should not raise

    def test_get_batch_all_cached(self, cache):
        """Batch get when all texts are cached."""
        emb1 = np.array([1.0, 2.0], dtype=np.float32)
        emb2 = np.array([3.0, 4.0], dtype=np.float32)
        cache.set("text_1", emb1)
        cache.set("text_2", emb2)

        results = cache.get_batch(["text_1", "text_2"])

        assert results["text_1"] is not None
        assert results["text_2"] is not None
        np.testing.assert_array_almost_equal(results["text_1"], emb1, decimal=5)

    def test_get_batch_partial(self, cache):
        """Batch get with mix of cached and uncached texts."""
        emb1 = np.array([1.0, 2.0], dtype=np.float32)
        cache.set("text_1", emb1)

        results = cache.get_batch(["text_1", "text_2"])

        assert results["text_1"] is not None
        assert results["text_2"] is None

    def test_get_batch_none_cached(self, cache):
        """Batch get when nothing is cached."""
        results = cache.get_batch(["text_1", "text_2"])

        assert results["text_1"] is None
        assert results["text_2"] is None

    def test_get_batch_hit_miss_tracking(self, cache):
        """Batch get should update hit/miss counters."""
        emb = np.array([1.0, 2.0], dtype=np.float32)
        cache.set("text_1", emb)

        cache.get_batch(["text_1", "text_2", "text_3"])

        assert cache._hit_count == 1
        assert cache._miss_count == 2

    def test_set_batch_with_ttl_override(self, cache):
        """Batch set with ttl_override should use custom TTL."""
        texts_embeddings = {
            "test": np.array([1.0], dtype=np.float32),
        }
        cache.set_batch(texts_embeddings, ttl_override=0)

        conn = sqlite3.connect(cache.db_path)
        cursor = conn.execute("SELECT expires_at FROM embeddings LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        assert row[0] is None


# ===========================================================================
# Test: Cleanup Operations
# ===========================================================================

class TestCleanupOperations:
    """Test cleanup methods."""

    def test_cleanup_expired(self, tmp_dir):
        """cleanup_expired should remove expired entries."""
        db_path = str(Path(tmp_dir) / "cleanup_test.db")
        cache = EmbeddingCache(db_path=db_path, ttl_days=1)

        # Add entries
        cache.set("text_1", np.array([1.0], dtype=np.float32))
        cache.set("text_2", np.array([2.0], dtype=np.float32))

        # Expire one entry
        conn = sqlite3.connect(db_path)
        past = (datetime.now() - timedelta(days=2)).isoformat()
        conn.execute(
            "UPDATE embeddings SET expires_at = ? WHERE text = ?",
            (past, "text_1")
        )
        conn.commit()
        conn.close()

        removed = cache.cleanup_expired()
        assert removed == 1

    def test_cleanup_expired_none(self, cache, sample_embedding):
        """cleanup_expired when nothing is expired should return 0."""
        cache.set("text", sample_embedding)
        removed = cache.cleanup_expired()
        assert removed == 0

    def test_cleanup_model(self, cache):
        """cleanup_model should remove all entries for given model."""
        cache.set("text_1", np.array([1.0], dtype=np.float32), model_name="model_a")
        cache.set("text_2", np.array([2.0], dtype=np.float32), model_name="model_b")
        cache.set("text_3", np.array([3.0], dtype=np.float32), model_name="model_a")

        removed = cache.cleanup_model("model_a")
        assert removed == 2

        # model_b should still be there
        result = cache.get("text_2", model_name="model_b")
        assert result is not None

    def test_cleanup_model_nonexistent(self, cache):
        """cleanup_model for non-existent model returns 0."""
        removed = cache.cleanup_model("nonexistent_model")
        assert removed == 0


# ===========================================================================
# Test: Statistics
# ===========================================================================

class TestStatistics:
    """Test get_stats method and EmbeddingCacheStats."""

    def test_empty_stats(self, cache):
        """Stats for empty cache."""
        stats = cache.get_stats()
        assert stats.total_entries == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0

    def test_stats_after_operations(self, cache, sample_embedding):
        """Stats should reflect operations."""
        cache.set("text_1", sample_embedding)
        cache.set("text_2", sample_embedding)
        cache.get("text_1")  # hit
        cache.get("text_3")  # miss

        stats = cache.get_stats()
        assert stats.total_entries == 2
        assert stats.hit_count == 1
        assert stats.miss_count == 1

    def test_hit_rate_no_accesses(self):
        """Hit rate with no accesses should be 0.0."""
        stats = EmbeddingCacheStats()
        assert stats.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        """Hit rate should be hit / (hit + miss)."""
        stats = EmbeddingCacheStats(hit_count=3, miss_count=7)
        assert abs(stats.hit_rate - 0.3) < 0.001

    def test_hit_rate_all_hits(self):
        """Hit rate with all hits should be 1.0."""
        stats = EmbeddingCacheStats(hit_count=10, miss_count=0)
        assert stats.hit_rate == 1.0

    def test_stats_total_size(self, cache, sample_embedding):
        """Total size should be non-zero after adding entries."""
        cache.set("text", sample_embedding)
        stats = cache.get_stats()
        assert stats.total_size_mb > 0

    def test_stats_avg_embedding_size(self, cache, sample_embedding):
        """Average embedding size should be approximately correct."""
        cache.set("text", sample_embedding)
        stats = cache.get_stats()
        # 768 floats * 4 bytes = 3072 bytes
        assert stats.avg_embedding_size > 0


# ===========================================================================
# Test: Delete Operation
# ===========================================================================

class TestDeleteOperation:
    """Test _delete method."""

    def test_delete_by_hash(self, cache, sample_embedding):
        """_delete should remove entry by hash."""
        cache.set("test text", sample_embedding)
        text_hash = cache._generate_hash("test text", "default")
        cache._delete(text_hash)

        result = cache.get("test text")
        assert result is None


# ===========================================================================
# Test: Warmup
# ===========================================================================

class TestWarmup:
    """Test async warmup method."""

    @pytest.mark.asyncio
    async def test_warmup_all_uncached(self, cache):
        """Warmup should generate and cache embeddings for uncached terms."""
        terms = ["lumbar stenosis", "disc herniation"]
        fake_embeddings = [
            np.array([1.0, 2.0], dtype=np.float32),
            np.array([3.0, 4.0], dtype=np.float32),
        ]

        embedding_func = AsyncMock(return_value=fake_embeddings)

        count = await cache.warmup(terms, embedding_func)

        assert count == 2
        result = cache.get("lumbar stenosis")
        assert result is not None

    @pytest.mark.asyncio
    async def test_warmup_all_cached(self, cache):
        """Warmup should skip already cached terms."""
        # Pre-cache
        cache.set("lumbar stenosis", np.array([1.0], dtype=np.float32))
        cache.set("disc herniation", np.array([2.0], dtype=np.float32))

        embedding_func = AsyncMock()

        count = await cache.warmup(
            ["lumbar stenosis", "disc herniation"],
            embedding_func
        )

        assert count == 0
        embedding_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_warmup_partial(self, cache):
        """Warmup should only generate for uncached terms."""
        cache.set("lumbar stenosis", np.array([1.0], dtype=np.float32))

        fake_embeddings = [np.array([2.0], dtype=np.float32)]
        embedding_func = AsyncMock(return_value=fake_embeddings)

        count = await cache.warmup(
            ["lumbar stenosis", "disc herniation"],
            embedding_func
        )

        assert count == 1

    @pytest.mark.asyncio
    async def test_warmup_error_handling(self, cache):
        """Warmup should handle embedding function errors gracefully."""
        embedding_func = AsyncMock(side_effect=Exception("API error"))

        # Should not raise
        count = await cache.warmup(["term1"], embedding_func)

        # Count should be 0 since the batch failed
        assert count == 0

    @pytest.mark.asyncio
    async def test_warmup_empty_terms(self, cache):
        """Warmup with empty term list should return 0."""
        embedding_func = AsyncMock()
        count = await cache.warmup([], embedding_func)
        assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

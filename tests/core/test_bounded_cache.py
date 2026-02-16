"""Tests for core/bounded_cache.py — BoundedCache LRU implementation."""

import pytest

from core.bounded_cache import BoundedCache


class TestBoundedCacheBasic:
    def test_get_set(self):
        cache = BoundedCache()
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_get_missing_returns_default(self):
        cache = BoundedCache()
        assert cache.get("missing") is None
        assert cache.get("missing", "fallback") == "fallback"

    def test_contains(self):
        cache = BoundedCache()
        cache.set("x", 10)
        assert "x" in cache
        assert "y" not in cache

    def test_len(self):
        cache = BoundedCache()
        assert len(cache) == 0
        cache.set("a", 1)
        cache.set("b", 2)
        assert len(cache) == 2

    def test_clear(self):
        cache = BoundedCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0
        assert "a" not in cache


class TestBoundedCacheOverwrite:
    def test_overwrite_existing_key(self):
        cache = BoundedCache()
        cache.set("k", "old")
        cache.set("k", "new")
        assert cache.get("k") == "new"
        assert len(cache) == 1

    def test_overwrite_does_not_increase_size(self):
        cache = BoundedCache(maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("a", 100)
        assert len(cache) == 2
        assert cache.get("a") == 100


class TestBoundedCacheEviction:
    def test_evicts_oldest_when_full(self):
        cache = BoundedCache(maxsize=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # should evict "a"
        assert "a" not in cache
        assert cache.get("b") == 2
        assert cache.get("d") == 4
        assert len(cache) == 3

    def test_lru_order_respected(self):
        """Accessing an item should move it to end, protecting it from eviction."""
        cache = BoundedCache(maxsize=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access "a" to make it most recently used
        cache.get("a")
        # Insert "d" — should evict "b" (least recently used), not "a"
        cache.set("d", 4)
        assert "a" in cache
        assert "b" not in cache
        assert "c" in cache
        assert "d" in cache

    def test_set_existing_key_updates_lru_order(self):
        """Re-setting an existing key should move it to end."""
        cache = BoundedCache(maxsize=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Re-set "a" — moves it to end
        cache.set("a", 10)
        # Insert "d" — should evict "b"
        cache.set("d", 4)
        assert "a" in cache
        assert cache.get("a") == 10
        assert "b" not in cache

    def test_maxsize_one(self):
        cache = BoundedCache(maxsize=1)
        cache.set("a", 1)
        assert cache.get("a") == 1
        cache.set("b", 2)
        assert "a" not in cache
        assert cache.get("b") == 2
        assert len(cache) == 1


class TestBoundedCacheDataTypes:
    def test_various_value_types(self):
        cache = BoundedCache()
        cache.set("int", 42)
        cache.set("str", "hello")
        cache.set("list", [1, 2, 3])
        cache.set("dict", {"key": "value"})
        cache.set("none", None)
        assert cache.get("int") == 42
        assert cache.get("str") == "hello"
        assert cache.get("list") == [1, 2, 3]
        assert cache.get("dict") == {"key": "value"}
        assert cache.get("none") is None

    def test_none_value_vs_missing(self):
        """Stored None should be distinguishable from a missing key."""
        cache = BoundedCache()
        cache.set("exists", None)
        assert "exists" in cache
        assert cache.get("exists") is None
        assert cache.get("exists", "sentinel") is None  # returns stored None
        assert "missing" not in cache
        assert cache.get("missing", "sentinel") == "sentinel"


class TestBoundedCacheDefaultMaxsize:
    def test_default_maxsize_500(self):
        cache = BoundedCache()
        assert cache._maxsize == 500

    def test_custom_maxsize(self):
        cache = BoundedCache(maxsize=10)
        assert cache._maxsize == 10

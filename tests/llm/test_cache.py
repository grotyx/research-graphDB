"""Tests for LLM Response Cache.

LLMCache 모듈의 단위 테스트.
"""

import pytest
import aiosqlite
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, AsyncMock
import tempfile
import shutil

from src.llm.cache import (
    LLMCache,
    CacheStats,
    generate_cache_key
)


class TestGenerateCacheKey:
    """generate_cache_key 함수 테스트."""

    def test_basic_key_generation(self):
        """기본 키 생성 테스트."""
        key = generate_cache_key(
            operation="section_classify",
            content="This is a test abstract."
        )
        assert isinstance(key, str)
        assert len(key) == 64  # SHA-256 hex length

    def test_same_input_same_key(self):
        """동일한 입력 → 동일한 키."""
        key1 = generate_cache_key("test", "content")
        key2 = generate_cache_key("test", "content")
        assert key1 == key2

    def test_different_operation_different_key(self):
        """다른 operation → 다른 키."""
        key1 = generate_cache_key("op1", "content")
        key2 = generate_cache_key("op2", "content")
        assert key1 != key2

    def test_different_content_different_key(self):
        """다른 content → 다른 키."""
        key1 = generate_cache_key("test", "content1")
        key2 = generate_cache_key("test", "content2")
        assert key1 != key2

    def test_with_params(self):
        """파라미터 포함 테스트."""
        key1 = generate_cache_key("test", "content", {"param": "value"})
        key2 = generate_cache_key("test", "content", {"param": "different"})
        assert key1 != key2

    def test_params_order_independence(self):
        """파라미터 순서 무관 테스트."""
        key1 = generate_cache_key(
            "test", "content",
            {"a": 1, "b": 2}
        )
        key2 = generate_cache_key(
            "test", "content",
            {"b": 2, "a": 1}
        )
        assert key1 == key2  # JSON sort_keys=True

    def test_none_params(self):
        """None params 처리 테스트."""
        key1 = generate_cache_key("test", "content", None)
        key2 = generate_cache_key("test", "content", {})
        assert key1 == key2  # None → {}


@pytest.fixture
async def temp_cache():
    """임시 캐시 인스턴스 생성."""
    # 임시 디렉토리 생성
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_cache.db"

    cache = LLMCache(db_path=str(db_path), ttl_hours=24)

    yield cache

    # 정리
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestLLMCacheInitialization:
    """LLMCache 초기화 테스트."""

    @pytest.mark.asyncio
    async def test_initialization(self, temp_cache):
        """초기화 테스트."""
        assert temp_cache.db_path.exists() is False  # 아직 DB 생성 전
        assert temp_cache.ttl_hours == 24
        assert temp_cache._initialized is False

    @pytest.mark.asyncio
    async def test_ensure_initialized_creates_db(self, temp_cache):
        """_ensure_initialized()가 DB를 생성하는지 테스트."""
        await temp_cache._ensure_initialized()

        assert temp_cache.db_path.exists()
        assert temp_cache._initialized is True

        # 테이블 존재 확인
        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in await cursor.fetchall()]

            assert "llm_cache" in tables
            assert "cost_log" in tables

    @pytest.mark.asyncio
    async def test_ensure_initialized_idempotent(self, temp_cache):
        """_ensure_initialized() 중복 호출 테스트."""
        await temp_cache._ensure_initialized()
        first_mtime = temp_cache.db_path.stat().st_mtime

        await temp_cache._ensure_initialized()
        second_mtime = temp_cache.db_path.stat().st_mtime

        # DB 파일이 다시 생성되지 않음
        assert first_mtime == second_mtime

    @pytest.mark.asyncio
    async def test_custom_ttl(self):
        """커스텀 TTL 설정 테스트."""
        temp_dir = tempfile.mkdtemp()
        try:
            cache = LLMCache(
                db_path=str(Path(temp_dir) / "test.db"),
                ttl_hours=48
            )
            assert cache.ttl_hours == 48
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestLLMCacheGet:
    """LLMCache.get() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, temp_cache):
        """캐시 미스 테스트."""
        result = await temp_cache.get("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, temp_cache):
        """캐시 히트 테스트."""
        cache_key = "test_key_123"
        response = {"result": "success", "data": [1, 2, 3]}
        metadata = {"source": "test"}

        # 캐시 저장
        await temp_cache.set(
            cache_key=cache_key,
            response=response,
            operation="test_op",
            metadata=metadata,
            input_tokens=100,
            output_tokens=200
        )

        # 캐시 조회
        result = await temp_cache.get(cache_key)

        assert result is not None
        assert result["response"] == response
        assert result["metadata"] == metadata
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 200

    @pytest.mark.asyncio
    async def test_get_increments_hit_count(self, temp_cache):
        """get()이 hit_count를 증가시키는지 테스트."""
        cache_key = "test_key"
        await temp_cache.set(cache_key, {"data": "test"}, "test_op")

        # 첫 번째 조회
        await temp_cache.get(cache_key)

        # DB에서 hit_count 확인
        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute(
                "SELECT hit_count FROM llm_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = await cursor.fetchone()
            assert row[0] == 1

        # 두 번째 조회
        await temp_cache.get(cache_key)

        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute(
                "SELECT hit_count FROM llm_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = await cursor.fetchone()
            assert row[0] == 2

    @pytest.mark.asyncio
    async def test_get_with_null_metadata(self, temp_cache):
        """metadata가 None인 경우 테스트."""
        cache_key = "test_key"
        await temp_cache.set(
            cache_key,
            {"data": "test"},
            "test_op",
            metadata=None
        )

        result = await temp_cache.get(cache_key)
        assert result["metadata"] is None


class TestLLMCacheSet:
    """LLMCache.set() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_set_basic(self, temp_cache):
        """기본 저장 테스트."""
        cache_key = "test_key"
        response = {"status": "ok"}

        await temp_cache.set(cache_key, response, "test_op")

        # DB 확인
        async with aiosqlite.connect(temp_cache.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM llm_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = await cursor.fetchone()

            assert row is not None
            assert row["cache_key"] == cache_key
            assert row["operation"] == "test_op"
            assert json.loads(row["response"]) == response

    @pytest.mark.asyncio
    async def test_set_with_metadata(self, temp_cache):
        """메타데이터 포함 저장 테스트."""
        cache_key = "test_key"
        metadata = {"timestamp": "2025-01-01", "version": "1.0"}

        await temp_cache.set(
            cache_key,
            {"data": "test"},
            "test_op",
            metadata=metadata
        )

        result = await temp_cache.get(cache_key)
        assert result["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_set_with_tokens(self, temp_cache):
        """토큰 수 저장 테스트."""
        cache_key = "test_key"

        await temp_cache.set(
            cache_key,
            {"data": "test"},
            "test_op",
            input_tokens=150,
            output_tokens=300
        )

        result = await temp_cache.get(cache_key)
        assert result["input_tokens"] == 150
        assert result["output_tokens"] == 300

    @pytest.mark.asyncio
    async def test_set_replace_existing(self, temp_cache):
        """기존 항목 교체 테스트."""
        cache_key = "test_key"

        # 첫 번째 저장
        await temp_cache.set(cache_key, {"version": 1}, "test_op")
        result1 = await temp_cache.get(cache_key)
        assert result1["response"]["version"] == 1

        # 같은 키로 다시 저장 (교체)
        await temp_cache.set(cache_key, {"version": 2}, "test_op")
        result2 = await temp_cache.get(cache_key)
        assert result2["response"]["version"] == 2

    @pytest.mark.asyncio
    async def test_set_expiration(self, temp_cache):
        """만료 시간 설정 테스트."""
        cache_key = "test_key"
        await temp_cache.set(cache_key, {"data": "test"}, "test_op")

        # expires_at 확인
        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute(
                "SELECT expires_at FROM llm_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = await cursor.fetchone()
            expires_at = datetime.fromisoformat(row[0])

            # TTL이 약 24시간인지 확인 (±1분 오차 허용)
            expected = datetime.now() + timedelta(hours=24)
            diff = abs((expires_at - expected).total_seconds())
            assert diff < 60  # 1분 이내


class TestLLMCacheInvalidate:
    """LLMCache.invalidate() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_invalidate_existing(self, temp_cache):
        """존재하는 캐시 삭제 테스트."""
        cache_key = "test_key"
        await temp_cache.set(cache_key, {"data": "test"}, "test_op")

        # 존재 확인
        result = await temp_cache.get(cache_key)
        assert result is not None

        # 삭제
        await temp_cache.invalidate(cache_key)

        # 삭제 확인
        result = await temp_cache.get(cache_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent(self, temp_cache):
        """존재하지 않는 캐시 삭제 시도 (에러 없어야 함)."""
        await temp_cache.invalidate("nonexistent_key")
        # 에러가 발생하지 않으면 성공

    @pytest.mark.asyncio
    async def test_invalidate_by_prefix(self, temp_cache):
        """접두사로 캐시 삭제 테스트."""
        # 여러 키 저장
        await temp_cache.set("prefix_key1", {"data": 1}, "test_op")
        await temp_cache.set("prefix_key2", {"data": 2}, "test_op")
        await temp_cache.set("other_key", {"data": 3}, "test_op")

        # prefix로 삭제
        deleted = await temp_cache.invalidate_by_prefix("prefix_")

        assert deleted == 2
        assert await temp_cache.get("prefix_key1") is None
        assert await temp_cache.get("prefix_key2") is None
        assert await temp_cache.get("other_key") is not None

    @pytest.mark.asyncio
    async def test_invalidate_by_operation(self, temp_cache):
        """작업 유형으로 캐시 삭제 테스트."""
        await temp_cache.set("key1", {"data": 1}, "section_classify")
        await temp_cache.set("key2", {"data": 2}, "section_classify")
        await temp_cache.set("key3", {"data": 3}, "chunk")

        deleted = await temp_cache.invalidate_by_operation("section_classify")

        assert deleted == 2
        assert await temp_cache.get("key1") is None
        assert await temp_cache.get("key2") is None
        assert await temp_cache.get("key3") is not None


class TestLLMCacheCleanupExpired:
    """LLMCache.cleanup_expired() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self, temp_cache):
        """만료된 항목 정리 테스트."""
        cache_key = "test_key"

        # 만료된 캐시 직접 삽입 (SQLite의 datetime('now')를 기준으로)
        async with aiosqlite.connect(temp_cache.db_path) as db:
            await temp_cache._ensure_initialized()

            # SQLite가 사용하는 현재 시간(UTC) 가져오기
            cursor = await db.execute("SELECT datetime('now')")
            current_sqlite_time = (await cursor.fetchone())[0]

            # 1시간 전으로 설정
            await db.execute(
                """
                INSERT INTO llm_cache
                (cache_key, operation, response, expires_at)
                VALUES (?, ?, ?, datetime('now', '-1 hour'))
                """,
                (
                    cache_key,
                    "test_op",
                    json.dumps({"data": "test"})
                )
            )
            await db.commit()

        # 정리 전 확인
        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM llm_cache")
            count = (await cursor.fetchone())[0]
            assert count == 1

        # 정리 실행
        deleted = await temp_cache.cleanup_expired()

        assert deleted == 1

        # 정리 후 확인
        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM llm_cache")
            count = (await cursor.fetchone())[0]
            assert count == 0

    @pytest.mark.asyncio
    async def test_cleanup_keeps_valid_entries(self, temp_cache):
        """유효한 항목은 유지 테스트."""
        # 유효한 캐시 저장
        await temp_cache.set("valid_key", {"data": "test"}, "test_op")

        # 만료된 캐시 직접 삽입
        async with aiosqlite.connect(temp_cache.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_cache
                (cache_key, operation, response, expires_at)
                VALUES (?, ?, ?, datetime('now', '-1 hour'))
                """,
                (
                    "expired_key",
                    "test_op",
                    json.dumps({"data": "expired"})
                )
            )
            await db.commit()

        # 정리
        deleted = await temp_cache.cleanup_expired()

        assert deleted == 1
        assert await temp_cache.get("valid_key") is not None
        assert await temp_cache.get("expired_key") is None

    @pytest.mark.asyncio
    async def test_cleanup_empty_cache(self, temp_cache):
        """빈 캐시 정리 테스트."""
        deleted = await temp_cache.cleanup_expired()
        assert deleted == 0


class TestLLMCacheGetStats:
    """LLMCache.get_stats() 메서드 테스트."""

    @pytest.mark.asyncio
    async def test_stats_empty_cache(self, temp_cache):
        """빈 캐시 통계 테스트."""
        stats = await temp_cache.get_stats()

        assert isinstance(stats, CacheStats)
        assert stats.total_entries == 0
        assert stats.total_size_bytes == 0
        assert stats.hit_count == 0
        assert stats.expired_entries == 0

    @pytest.mark.asyncio
    async def test_stats_with_entries(self, temp_cache):
        """항목이 있는 캐시 통계 테스트."""
        # 여러 항목 저장
        await temp_cache.set("key1", {"data": "test1"}, "test_op")
        await temp_cache.set("key2", {"data": "test2"}, "test_op")

        # 조회 (hit_count 증가)
        await temp_cache.get("key1")
        await temp_cache.get("key1")

        stats = await temp_cache.get_stats()

        assert stats.total_entries == 2
        assert stats.total_size_bytes > 0
        assert stats.hit_count == 2

    @pytest.mark.asyncio
    async def test_stats_expired_count(self, temp_cache):
        """만료된 항목 수 확인 테스트."""
        await temp_cache._ensure_initialized()

        # 만료된 캐시 삽입
        async with aiosqlite.connect(temp_cache.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_cache
                (cache_key, operation, response, expires_at)
                VALUES (?, ?, ?, datetime('now', '-1 hour'))
                """,
                (
                    "expired_key",
                    "test_op",
                    json.dumps({"data": "test"})
                )
            )
            await db.commit()

        stats = await temp_cache.get_stats()
        assert stats.expired_entries == 1


class TestLLMCacheCostTracking:
    """비용 추적 기능 테스트."""

    @pytest.mark.asyncio
    async def test_log_cost(self, temp_cache):
        """비용 로그 기록 테스트."""
        await temp_cache.log_cost(
            operation="section_classify",
            input_tokens=1000,
            output_tokens=500,
            cached=False
        )

        # DB 확인
        async with aiosqlite.connect(temp_cache.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM cost_log")
            row = await cursor.fetchone()

            assert row is not None
            assert row["operation"] == "section_classify"
            assert row["input_tokens"] == 1000
            assert row["output_tokens"] == 500
            assert row["cached"] == 0  # False

    @pytest.mark.asyncio
    async def test_get_cost_summary_all(self, temp_cache):
        """전체 비용 요약 테스트."""
        # 여러 로그 기록
        await temp_cache.log_cost("op1", 1000, 500, False)
        await temp_cache.log_cost("op2", 2000, 1000, True)
        await temp_cache.log_cost("op3", 1500, 750, False)

        summary = await temp_cache.get_cost_summary()

        assert summary["total_input_tokens"] == 4500
        assert summary["total_output_tokens"] == 2250
        assert summary["total_requests"] == 3
        assert summary["cached_requests"] == 1

        # 비용 계산 확인 (Claude Haiku 4.5: $0.80/1M input, $4.00/1M output)
        expected_cost = (4500 / 1_000_000) * 0.80 + (2250 / 1_000_000) * 4.00
        assert abs(summary["estimated_cost_usd"] - expected_cost) < 0.0001

    @pytest.mark.asyncio
    async def test_get_cost_summary_since(self, temp_cache):
        """특정 시간 이후 비용 요약 테스트."""
        await temp_cache._ensure_initialized()

        # 과거 로그 직접 삽입 (SQLite datetime 사용)
        async with aiosqlite.connect(temp_cache.db_path) as db:
            await db.execute(
                """
                INSERT INTO cost_log (operation, input_tokens, output_tokens, timestamp)
                VALUES (?, ?, ?, datetime('now', '-48 hours'))
                """,
                ("old_op", 1000, 500)
            )
            await db.commit()

        # 최근 로그 추가
        await temp_cache.log_cost("new_op", 2000, 1000, False)

        # 24시간 이후만 조회
        since = datetime.now() - timedelta(hours=24)
        summary = await temp_cache.get_cost_summary(since=since)

        # 최근 로그만 포함
        assert summary["total_input_tokens"] == 2000
        assert summary["total_output_tokens"] == 1000
        assert summary["total_requests"] == 1

    @pytest.mark.asyncio
    async def test_cost_summary_empty(self, temp_cache):
        """로그 없을 때 비용 요약 테스트."""
        summary = await temp_cache.get_cost_summary()

        assert summary["total_input_tokens"] == 0
        assert summary["total_output_tokens"] == 0
        assert summary["total_requests"] == 0
        assert summary["cached_requests"] == 0
        assert summary["estimated_cost_usd"] == 0.0


class TestLLMCacheTTLExpiration:
    """TTL 만료 동작 테스트."""

    @pytest.mark.asyncio
    async def test_expired_entry_not_returned(self, temp_cache):
        """만료된 항목은 반환되지 않음."""
        cache_key = "test_key"
        await temp_cache._ensure_initialized()

        # 이미 만료된 시간으로 캐시 삽입
        async with aiosqlite.connect(temp_cache.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_cache
                (cache_key, operation, response, expires_at)
                VALUES (?, ?, ?, datetime('now', '-1 hour'))
                """,
                (
                    cache_key,
                    "test_op",
                    json.dumps({"data": "test"})
                )
            )
            await db.commit()

        # 조회 시 None 반환
        result = await temp_cache.get(cache_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_entry_no_hit_count_increment(self, temp_cache):
        """만료된 항목 조회 시 hit_count 증가 안 함."""
        cache_key = "test_key"
        await temp_cache._ensure_initialized()

        # 만료된 캐시 삽입
        async with aiosqlite.connect(temp_cache.db_path) as db:
            await db.execute(
                """
                INSERT INTO llm_cache
                (cache_key, operation, response, expires_at, hit_count)
                VALUES (?, ?, ?, datetime('now', '-1 hour'), ?)
                """,
                (
                    cache_key,
                    "test_op",
                    json.dumps({"data": "test"}),
                    0
                )
            )
            await db.commit()

        # 조회 시도
        await temp_cache.get(cache_key)

        # hit_count가 증가하지 않음
        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute(
                "SELECT hit_count FROM llm_cache WHERE cache_key = ?",
                (cache_key,)
            )
            row = await cursor.fetchone()
            assert row[0] == 0


class TestLLMCacheEdgeCases:
    """엣지 케이스 테스트."""

    @pytest.mark.asyncio
    async def test_empty_response(self, temp_cache):
        """빈 응답 저장/조회 테스트."""
        cache_key = "empty_key"
        await temp_cache.set(cache_key, {}, "test_op")

        result = await temp_cache.get(cache_key)
        assert result["response"] == {}

    @pytest.mark.asyncio
    async def test_large_response(self, temp_cache):
        """큰 응답 저장/조회 테스트."""
        cache_key = "large_key"
        large_response = {
            "data": "x" * 100000,  # 100KB
            "items": list(range(1000))
        }

        await temp_cache.set(cache_key, large_response, "test_op")
        result = await temp_cache.get(cache_key)

        assert result["response"] == large_response

    @pytest.mark.asyncio
    async def test_unicode_content(self, temp_cache):
        """유니코드 콘텐츠 저장/조회 테스트."""
        cache_key = "unicode_key"
        response = {
            "korean": "안녕하세요",
            "japanese": "こんにちは",
            "emoji": "🏥📊"
        }

        await temp_cache.set(cache_key, response, "test_op")
        result = await temp_cache.get(cache_key)

        assert result["response"] == response

    @pytest.mark.asyncio
    async def test_special_characters_in_operation(self, temp_cache):
        """특수 문자 operation 이름 테스트."""
        cache_key = "test_key"
        operation = "section/classify:v2.0"

        await temp_cache.set(cache_key, {"data": "test"}, operation)

        deleted = await temp_cache.invalidate_by_operation(operation)
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_concurrent_access(self, temp_cache):
        """동시 접근 테스트 (기본 동작 확인)."""
        import asyncio

        async def write_cache(key, value):
            await temp_cache.set(key, {"value": value}, "test_op")

        # 여러 작업 동시 실행
        await asyncio.gather(
            write_cache("key1", 1),
            write_cache("key2", 2),
            write_cache("key3", 3)
        )

        # 모두 저장되었는지 확인
        assert await temp_cache.get("key1") is not None
        assert await temp_cache.get("key2") is not None
        assert await temp_cache.get("key3") is not None

    @pytest.mark.asyncio
    async def test_zero_tokens(self, temp_cache):
        """토큰 수 0 처리 테스트."""
        cache_key = "zero_tokens"
        await temp_cache.set(
            cache_key,
            {"data": "test"},
            "test_op",
            input_tokens=0,
            output_tokens=0
        )

        result = await temp_cache.get(cache_key)
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0

    @pytest.mark.asyncio
    async def test_duplicate_key_replacement(self, temp_cache):
        """중복 키 저장 시 교체 동작 테스트."""
        cache_key = "dup_key"

        # 첫 번째 저장
        await temp_cache.set(
            cache_key,
            {"version": 1},
            "test_op",
            input_tokens=100
        )

        # 두 번째 저장 (같은 키)
        await temp_cache.set(
            cache_key,
            {"version": 2},
            "test_op",
            input_tokens=200
        )

        # 최신 값만 있어야 함
        async with aiosqlite.connect(temp_cache.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM llm_cache WHERE cache_key = ?",
                (cache_key,)
            )
            count = (await cursor.fetchone())[0]
            assert count == 1

        result = await temp_cache.get(cache_key)
        assert result["response"]["version"] == 2
        assert result["input_tokens"] == 200

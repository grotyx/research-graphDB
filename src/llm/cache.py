"""LLM Response Cache.

SQLite 기반 LLM 응답 캐싱 시스템.
"""

import hashlib
import json
import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


def generate_cache_key(
    operation: str,
    content: str,
    params: Optional[dict] = None
) -> str:
    """캐시 키 생성.

    Args:
        operation: 작업 유형 (section_classify, chunk, extract_metadata, etc.)
        content: 입력 콘텐츠
        params: 추가 파라미터

    Returns:
        SHA-256 해시 문자열
    """
    data = {
        "operation": operation,
        "content": content,
        "params": params or {}
    }
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


@dataclass
class CacheStats:
    """캐시 통계."""
    total_entries: int = 0
    total_size_bytes: int = 0
    hit_count: int = 0
    miss_count: int = 0
    expired_entries: int = 0


class LLMCache:
    """SQLite 기반 LLM 응답 캐시."""

    SCHEMA = """
    -- 캐시 테이블
    CREATE TABLE IF NOT EXISTS llm_cache (
        cache_key TEXT PRIMARY KEY,
        operation TEXT NOT NULL,
        response TEXT NOT NULL,
        metadata TEXT,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        hit_count INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_cache_operation ON llm_cache(operation);
    CREATE INDEX IF NOT EXISTS idx_cache_expires ON llm_cache(expires_at);

    -- 비용 추적 테이블
    CREATE TABLE IF NOT EXISTS cost_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation TEXT NOT NULL,
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        cached BOOLEAN DEFAULT FALSE,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_cost_timestamp ON cost_log(timestamp);
    """

    def __init__(
        self,
        db_path: str = "data/llm_cache.db",
        ttl_hours: int = 168  # 7일
    ):
        """초기화.

        Args:
            db_path: SQLite DB 파일 경로
            ttl_hours: 캐시 만료 시간 (시간)
        """
        self.db_path = Path(db_path)
        self.ttl_hours = ttl_hours
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """DB 초기화 확인."""
        if self._initialized:
            return

        # 디렉토리 생성
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(self.SCHEMA)
            await db.commit()

        self._initialized = True

    async def get(self, cache_key: str) -> Optional[dict]:
        """캐시 조회.

        Args:
            cache_key: 캐시 키 (콘텐츠 해시)

        Returns:
            캐시된 응답 또는 None
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 만료되지 않은 캐시 조회
            cursor = await db.execute(
                """
                SELECT response, metadata, input_tokens, output_tokens
                FROM llm_cache
                WHERE cache_key = ? AND expires_at > datetime('now')
                """,
                (cache_key,)
            )
            row = await cursor.fetchone()

            if row is None:
                return None

            # hit_count 증가
            await db.execute(
                "UPDATE llm_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (cache_key,)
            )
            await db.commit()

            return {
                "response": json.loads(row["response"]),
                "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"]
            }

    async def set(
        self,
        cache_key: str,
        response: dict,
        operation: str = "unknown",
        metadata: Optional[dict] = None,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> None:
        """캐시 저장.

        Args:
            cache_key: 캐시 키
            response: 저장할 응답
            operation: 작업 유형
            metadata: 추가 메타데이터
            input_tokens: 입력 토큰 수
            output_tokens: 출력 토큰 수
        """
        await self._ensure_initialized()

        expires_at = datetime.now() + timedelta(hours=self.ttl_hours)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO llm_cache
                (cache_key, operation, response, metadata, input_tokens, output_tokens, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    operation,
                    json.dumps(response, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False) if metadata else None,
                    input_tokens,
                    output_tokens,
                    expires_at.isoformat()
                )
            )
            await db.commit()

    async def invalidate(self, cache_key: str) -> None:
        """캐시 무효화."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM llm_cache WHERE cache_key = ?",
                (cache_key,)
            )
            await db.commit()

    async def invalidate_by_prefix(self, prefix: str) -> int:
        """접두사로 캐시 무효화.

        Returns:
            삭제된 항목 수
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM llm_cache WHERE cache_key LIKE ?",
                (f"{prefix}%",)
            )
            await db.commit()
            return cursor.rowcount

    async def invalidate_by_operation(self, operation: str) -> int:
        """작업 유형으로 캐시 무효화.

        Returns:
            삭제된 항목 수
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM llm_cache WHERE operation = ?",
                (operation,)
            )
            await db.commit()
            return cursor.rowcount

    async def cleanup_expired(self) -> int:
        """만료된 캐시 정리.

        Returns:
            삭제된 항목 수
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM llm_cache WHERE expires_at <= datetime('now')"
            )
            await db.commit()
            return cursor.rowcount

    async def get_stats(self) -> CacheStats:
        """캐시 통계 반환."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 총 항목 수
            cursor = await db.execute("SELECT COUNT(*) as count FROM llm_cache")
            row = await cursor.fetchone()
            total_entries = row["count"]

            # 총 hit count
            cursor = await db.execute("SELECT SUM(hit_count) as hits FROM llm_cache")
            row = await cursor.fetchone()
            hit_count = row["hits"] or 0

            # 만료된 항목 수
            cursor = await db.execute(
                "SELECT COUNT(*) as count FROM llm_cache WHERE expires_at <= datetime('now')"
            )
            row = await cursor.fetchone()
            expired_entries = row["count"]

            # 총 크기 (대략적)
            cursor = await db.execute(
                "SELECT SUM(LENGTH(response)) as size FROM llm_cache"
            )
            row = await cursor.fetchone()
            total_size = row["size"] or 0

            return CacheStats(
                total_entries=total_entries,
                total_size_bytes=total_size,
                hit_count=hit_count,
                expired_entries=expired_entries
            )

    async def log_cost(
        self,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        cached: bool = False
    ) -> None:
        """비용 로그 기록."""
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO cost_log (operation, input_tokens, output_tokens, cached)
                VALUES (?, ?, ?, ?)
                """,
                (operation, input_tokens, output_tokens, cached)
            )
            await db.commit()

    async def get_cost_summary(
        self,
        since: datetime = None
    ) -> dict:
        """비용 요약 조회.

        Args:
            since: 이 시간 이후의 로그만 조회 (None이면 전체)

        Returns:
            비용 요약 딕셔너리
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if since:
                cursor = await db.execute(
                    """
                    SELECT
                        SUM(input_tokens) as total_input,
                        SUM(output_tokens) as total_output,
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN cached THEN 1 ELSE 0 END) as cached_requests
                    FROM cost_log
                    WHERE timestamp >= ?
                    """,
                    (since.isoformat(),)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT
                        SUM(input_tokens) as total_input,
                        SUM(output_tokens) as total_output,
                        COUNT(*) as total_requests,
                        SUM(CASE WHEN cached THEN 1 ELSE 0 END) as cached_requests
                    FROM cost_log
                    """
                )

            row = await cursor.fetchone()

            total_input = row["total_input"] or 0
            total_output = row["total_output"] or 0

            # Gemini 2.5 Flash 가격
            input_cost = (total_input / 1_000_000) * 0.15
            output_cost = (total_output / 1_000_000) * 0.60

            return {
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_requests": row["total_requests"] or 0,
                "cached_requests": row["cached_requests"] or 0,
                "estimated_cost_usd": round(input_cost + output_cost, 4)
            }

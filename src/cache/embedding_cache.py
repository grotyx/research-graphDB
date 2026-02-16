"""Embedding Cache for Text Embeddings.

Persistent cache using SQLite for text-to-embedding mappings.
"""

import hashlib
import json
import logging
import pickle
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingCacheStats:
    """Embedding cache statistics.

    Attributes:
        total_entries: Total cached embeddings
        total_size_mb: Approximate disk usage (MB)
        hit_count: Number of cache hits
        miss_count: Number of cache misses
        avg_embedding_size: Average embedding dimension
    """
    total_entries: int = 0
    total_size_mb: float = 0.0
    hit_count: int = 0
    miss_count: int = 0
    avg_embedding_size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate."""
        total = self.hit_count + self.miss_count
        if total == 0:
            return 0.0
        return self.hit_count / total


class EmbeddingCache:
    """Persistent cache for text embeddings.

    Features:
    - SQLite-based persistent storage
    - Text normalization for better hit rate
    - Binary serialization for efficiency
    - TTL-based expiration
    - Automatic cleanup of old entries

    Schema:
        - text_hash: SHA-256 hash of normalized text (PRIMARY KEY)
        - text: Original text (for debugging)
        - embedding: Pickled numpy array
        - model_name: Embedding model identifier
        - created_at: Timestamp
        - expires_at: Expiration timestamp
        - hit_count: Access counter

    Usage:
        cache = EmbeddingCache(db_path="embeddings.db")

        # Get/Set
        embedding = cache.get("sample text", model_name="medbert")
        if embedding is None:
            embedding = model.encode("sample text")
            cache.set("sample text", embedding, model_name="medbert")

        # Warm up common terms
        terms = ["lumbar stenosis", "disc herniation", ...]
        await cache.warmup(terms, embedding_function)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS embeddings (
        text_hash TEXT PRIMARY KEY,
        text TEXT NOT NULL,
        embedding BLOB NOT NULL,
        model_name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        hit_count INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model_name);
    CREATE INDEX IF NOT EXISTS idx_embeddings_expires ON embeddings(expires_at);
    CREATE INDEX IF NOT EXISTS idx_embeddings_created ON embeddings(created_at);
    """

    def __init__(
        self,
        db_path: str = "data/embedding_cache.db",
        ttl_days: int = 30
    ):
        """Initialize embedding cache.

        Args:
            db_path: SQLite database path
            ttl_days: Time-to-live in days (0 for no expiration)
        """
        self.db_path = Path(db_path)
        self.ttl_days = ttl_days
        self._hit_count: int = 0
        self._miss_count: int = 0
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Initialize database schema."""
        # Create directory
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create tables
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(self.SCHEMA)
            conn.commit()
            logger.info(f"Embedding cache initialized: {self.db_path}")
        finally:
            conn.close()

    def _normalize_text(self, text: str) -> str:
        """Normalize text for consistent hashing.

        Args:
            text: Input text

        Returns:
            Normalized text
        """
        # Lowercase, strip whitespace, collapse multiple spaces
        normalized = " ".join(text.lower().strip().split())
        return normalized

    def _generate_hash(self, text: str, model_name: str) -> str:
        """Generate hash key for text and model.

        Args:
            text: Input text
            model_name: Model identifier

        Returns:
            SHA-256 hash
        """
        normalized = self._normalize_text(text)
        data = {"text": normalized, "model": model_name}
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def get(
        self,
        text: str,
        model_name: str = "default"
    ) -> Optional[np.ndarray]:
        """Get cached embedding.

        Args:
            text: Input text
            model_name: Model identifier

        Returns:
            Cached embedding array or None if not found
        """
        text_hash = self._generate_hash(text, model_name)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT embedding, expires_at
                FROM embeddings
                WHERE text_hash = ? AND model_name = ?
                """,
                (text_hash, model_name)
            )
            row = cursor.fetchone()

            if row is None:
                self._miss_count += 1
                logger.debug(f"Embedding cache miss: {text[:50]}...")
                return None

            embedding_blob, expires_at = row

            # Check expiration
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at)
                if datetime.now() > expires_dt:
                    self._miss_count += 1
                    logger.debug(f"Embedding cache expired: {text[:50]}...")
                    self._delete(text_hash)
                    return None

            # Update hit count
            conn.execute(
                "UPDATE embeddings SET hit_count = hit_count + 1 WHERE text_hash = ?",
                (text_hash,)
            )
            conn.commit()

            # Deserialize embedding
            embedding = pickle.loads(embedding_blob)
            self._hit_count += 1
            logger.debug(f"Embedding cache hit: {text[:50]}...")
            return embedding

        finally:
            conn.close()

    def set(
        self,
        text: str,
        embedding: np.ndarray,
        model_name: str = "default",
        ttl_override: Optional[int] = None
    ) -> None:
        """Cache embedding.

        Args:
            text: Input text
            embedding: Embedding array
            model_name: Model identifier
            ttl_override: Override default TTL (days)
        """
        text_hash = self._generate_hash(text, model_name)
        normalized = self._normalize_text(text)

        # Calculate expiration
        ttl = ttl_override if ttl_override is not None else self.ttl_days
        expires_at = None if ttl <= 0 else datetime.now() + timedelta(days=ttl)

        # Serialize embedding
        embedding_blob = pickle.dumps(embedding)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO embeddings
                (text_hash, text, embedding, model_name, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    text_hash,
                    normalized,
                    embedding_blob,
                    model_name,
                    expires_at.isoformat() if expires_at else None
                )
            )
            conn.commit()
            logger.debug(f"Embedding cached: {text[:50]}... (TTL: {ttl} days)")

        finally:
            conn.close()

    def get_batch(
        self,
        texts: list[str],
        model_name: str = "default"
    ) -> dict[str, Optional[np.ndarray]]:
        """Get multiple embeddings in batch.

        Args:
            texts: List of input texts
            model_name: Model identifier

        Returns:
            Dictionary mapping text to embedding (None if not cached)
        """
        results: dict[str, Optional[np.ndarray]] = {}

        # Generate hashes
        hashes = {text: self._generate_hash(text, model_name) for text in texts}
        hash_to_text = {h: t for t, h in hashes.items()}

        conn = sqlite3.connect(self.db_path)
        try:
            # Query all at once
            placeholders = ",".join("?" * len(hashes))
            cursor = conn.execute(
                f"""
                SELECT text_hash, embedding, expires_at
                FROM embeddings
                WHERE text_hash IN ({placeholders}) AND model_name = ?
                """,
                (*hashes.values(), model_name)
            )

            # Process results
            found_hashes = set()
            for text_hash, embedding_blob, expires_at in cursor:
                # Check expiration
                if expires_at:
                    expires_dt = datetime.fromisoformat(expires_at)
                    if datetime.now() > expires_dt:
                        continue

                # Deserialize
                embedding = pickle.loads(embedding_blob)
                text = hash_to_text[text_hash]
                results[text] = embedding
                found_hashes.add(text_hash)

            # Update hit counts
            if found_hashes:
                placeholders = ",".join("?" * len(found_hashes))
                conn.execute(
                    f"UPDATE embeddings SET hit_count = hit_count + 1 WHERE text_hash IN ({placeholders})",
                    tuple(found_hashes)
                )
                conn.commit()

            # Track hit/miss counts
            self._hit_count += len(found_hashes)

            # Add None for missing texts
            miss_count = 0
            for text in texts:
                if text not in results:
                    results[text] = None
                    miss_count += 1
            self._miss_count += miss_count

            logger.debug(f"Batch get: {len(found_hashes)}/{len(texts)} cached")
            return results

        finally:
            conn.close()

    def set_batch(
        self,
        texts_embeddings: dict[str, np.ndarray],
        model_name: str = "default",
        ttl_override: Optional[int] = None
    ) -> None:
        """Cache multiple embeddings in batch.

        Args:
            texts_embeddings: Dictionary mapping text to embedding
            model_name: Model identifier
            ttl_override: Override default TTL (days)
        """
        if not texts_embeddings:
            return

        # Calculate expiration
        ttl = ttl_override if ttl_override is not None else self.ttl_days
        expires_at = None if ttl <= 0 else datetime.now() + timedelta(days=ttl)

        # Prepare data
        data = []
        for text, embedding in texts_embeddings.items():
            text_hash = self._generate_hash(text, model_name)
            normalized = self._normalize_text(text)
            embedding_blob = pickle.dumps(embedding)
            data.append((
                text_hash,
                normalized,
                embedding_blob,
                model_name,
                expires_at.isoformat() if expires_at else None
            ))

        conn = sqlite3.connect(self.db_path)
        try:
            conn.executemany(
                """
                INSERT OR REPLACE INTO embeddings
                (text_hash, text, embedding, model_name, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                data
            )
            conn.commit()
            logger.info(f"Batch cached {len(data)} embeddings")

        finally:
            conn.close()

    def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries removed
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM embeddings WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (datetime.now().isoformat(),)
            )
            count = cursor.rowcount
            conn.commit()

            if count > 0:
                logger.info(f"Cleaned up {count} expired embeddings")

            return count

        finally:
            conn.close()

    def cleanup_model(self, model_name: str) -> int:
        """Remove all entries for a specific model.

        Args:
            model_name: Model identifier

        Returns:
            Number of entries removed
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM embeddings WHERE model_name = ?",
                (model_name,)
            )
            count = cursor.rowcount
            conn.commit()

            if count > 0:
                logger.info(f"Cleaned up {count} embeddings for model '{model_name}'")

            return count

        finally:
            conn.close()

    def get_stats(self) -> EmbeddingCacheStats:
        """Get cache statistics.

        Returns:
            EmbeddingCacheStats object
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    SUM(LENGTH(embedding)) as total_size,
                    SUM(hit_count) as total_hits,
                    AVG(LENGTH(embedding)) as avg_size
                FROM embeddings
                """
            )
            row = cursor.fetchone()

            if row:
                total_entries, total_size, total_hits, avg_size = row
                total_size_mb = (total_size or 0) / (1024 * 1024)
                avg_embedding_size = int(avg_size or 0) // 4  # Rough estimate (float32)

                return EmbeddingCacheStats(
                    total_entries=total_entries or 0,
                    total_size_mb=total_size_mb,
                    hit_count=self._hit_count,
                    miss_count=self._miss_count,
                    avg_embedding_size=avg_embedding_size
                )

            return EmbeddingCacheStats()

        finally:
            conn.close()

    def _delete(self, text_hash: str) -> None:
        """Delete entry by hash."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM embeddings WHERE text_hash = ?", (text_hash,))
            conn.commit()
        finally:
            conn.close()

    async def warmup(
        self,
        terms: list[str],
        embedding_function,
        model_name: str = "default",
        batch_size: int = 32
    ) -> int:
        """Warm up cache with common terms.

        Args:
            terms: List of terms to cache
            embedding_function: Async function that generates embeddings
            model_name: Model identifier
            batch_size: Batch size for embedding generation

        Returns:
            Number of terms cached
        """
        # Filter out already cached terms
        uncached_terms = []
        for term in terms:
            if self.get(term, model_name) is None:
                uncached_terms.append(term)

        if not uncached_terms:
            logger.info("All warmup terms already cached")
            return 0

        logger.info(f"Warming up cache with {len(uncached_terms)} terms...")

        # Generate embeddings in batches
        count = 0
        for i in range(0, len(uncached_terms), batch_size):
            batch = uncached_terms[i:i + batch_size]

            try:
                # Generate embeddings
                embeddings = await embedding_function(batch)

                # Cache them
                texts_embeddings = dict(zip(batch, embeddings))
                self.set_batch(texts_embeddings, model_name, ttl_override=90)  # 90 days for warmup

                count += len(batch)
                logger.debug(f"Warmed up {count}/{len(uncached_terms)} terms")

            except Exception as e:
                logger.error(f"Warmup batch failed: {e}", exc_info=True)

        logger.info(f"Cache warmed up with {count} terms")
        return count


# Common medical terms for warmup
COMMON_MEDICAL_TERMS = [
    # Pathologies
    "lumbar stenosis",
    "disc herniation",
    "spondylolisthesis",
    "degenerative disc disease",
    "spinal fracture",
    "vertebral compression fracture",
    "spinal tumor",
    "scoliosis",
    "kyphosis",

    # Interventions
    "fusion surgery",
    "laminectomy",
    "discectomy",
    "foraminotomy",
    "vertebroplasty",
    "kyphoplasty",
    "endoscopic surgery",
    "minimally invasive surgery",

    # Outcomes
    "pain relief",
    "functional improvement",
    "fusion rate",
    "complication rate",
    "reoperation rate",
    "adjacent segment disease",
    "proximal junctional kyphosis",

    # Measurements
    "VAS score",
    "ODI score",
    "JOA score",
    "SF-36",
    "EQ-5D",
    "back pain",
    "leg pain",
    "neurological deficit",
]


# Example usage
if __name__ == "__main__":
    import asyncio

    # Initialize cache
    cache = EmbeddingCache(db_path="test_embeddings.db")

    # Test text
    text = "Lumbar stenosis is a common degenerative condition"

    # Simulate embedding
    fake_embedding = np.random.rand(768).astype(np.float32)

    # Set
    cache.set(text, fake_embedding, model_name="test-model")

    # Get
    retrieved = cache.get(text, model_name="test-model")
    print(f"Retrieved embedding shape: {retrieved.shape if retrieved is not None else None}")

    # Stats
    stats = cache.get_stats()
    print(f"Cache stats: {stats.total_entries} entries, {stats.total_size_mb:.2f} MB")

    # Cleanup
    Path("test_embeddings.db").unlink(missing_ok=True)

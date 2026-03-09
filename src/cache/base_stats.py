"""Base Cache Statistics.

Shared base dataclass for cache hit/miss tracking (CA-D-004).
"""

from dataclasses import dataclass


@dataclass
class BaseCacheStats:
    """Base cache statistics with hit/miss tracking.

    Provides common fields and hit_rate property shared across
    all cache implementations.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
    """
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate.

        Returns:
            Hit rate as float between 0.0 and 1.0
        """
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

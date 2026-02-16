"""Bounded LRU-like cache to prevent unbounded memory growth."""

from collections import OrderedDict
from typing import Any, Optional


class BoundedCache:
    """Simple LRU-like cache with maxsize.

    When the cache exceeds maxsize, the least recently used entry is evicted.
    """

    def __init__(self, maxsize: int = 500):
        self._data: OrderedDict = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return default

    def set(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        self._data.clear()

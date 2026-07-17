"""
Tiny in-process TTL cache for expensive read-only computations.

Market data is shared across users, so a single process-level cache is
both correct and much cheaper than per-request refetches. If the API is
ever scaled to multiple processes, swap this for a shared store (e.g. Redis).
"""

import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class TTLCache:
    """Minimal thread-safe TTL cache keyed by string."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, T]] = {}

    def get_or_set(self, key: str, ttl_seconds: float, factory: Callable[[], T]) -> T:
        """Return the cached value if fresh, otherwise compute and cache it."""
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and now - entry[0] < ttl_seconds:
                return entry[1]

        # Compute outside the lock so slow fetches don't block readers
        value = factory()

        with self._lock:
            self._entries[key] = (now, value)
        return value

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
        self._entries: dict[str, tuple[float, T, object]] = {}

    def get_or_set(
        self,
        key: str,
        ttl_seconds: float,
        factory: Callable[[], T],
        *,
        version: object = None,
    ) -> T:
        """Reuse a fresh version, replacing it in place when the version changes."""
        now = time.monotonic()
        with self._lock:
            # Retired date/revision keys must not survive forever without reads.
            for expired in [k for k, entry in self._entries.items() if now >= entry[0]]:
                del self._entries[expired]
            observed = self._entries.get(key)
            if observed is not None and observed[2] == version:
                return observed[1]

        value = factory()

        with self._lock:
            # A slow older calculation must not overwrite a newer completed one.
            if self._entries.get(key) is observed:
                self._entries[key] = (time.monotonic() + ttl_seconds, value, version)
        return value

    def invalidate(self, key: str) -> None:
        """Drop one cached entry (no-op when absent)."""
        with self._lock:
            self._entries.pop(key, None)

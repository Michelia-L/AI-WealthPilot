"""Process-wide admission for both interactive assistant endpoints.

Never queue while holding a FastAPI worker. Keys are authorized user/workspace
IDs, not session tokens or caller-supplied selectors. Multi-worker deployments
must also enforce shared limits at their gateway.
"""

import math
import threading
import time
from collections import deque
from contextlib import contextmanager


class AssistantLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class AssistantBusy(Exception):
    pass


class AssistantAdmission:
    WINDOW_SECONDS = 60
    USER_REQUESTS = 6
    ORG_REQUESTS = 30
    ORG_CONCURRENCY = 2

    def __init__(self):
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(4)
        self._history: dict[tuple[str, str], deque[float]] = {}
        self._active_users: set[str] = set()
        self._active_orgs: dict[str, int] = {}

    @contextmanager
    def admit(self, user_id: str, organization_id: str):
        keys = (("user", user_id), ("org", organization_id))
        with self._lock:
            now = time.monotonic()
            # Expire idle identities too, avoiding an ever-growing key cache.
            for key, history in list(self._history.items()):
                while history and history[0] <= now - self.WINDOW_SECONDS:
                    history.popleft()
                if not history:
                    del self._history[key]
            retries = [
                max(1, math.ceil(history[0] + self.WINDOW_SECONDS - now))
                for key, limit in zip(
                    keys, (self.USER_REQUESTS, self.ORG_REQUESTS), strict=True
                )
                if len(history := self._history.get(key, ())) >= limit
            ]
            if retries:
                raise AssistantLimited(max(retries))
            if (
                user_id in self._active_users
                or self._active_orgs.get(organization_id, 0) >= self.ORG_CONCURRENCY
                or not self._slots.acquire(blocking=False)
            ):
                raise AssistantBusy
            self._active_users.add(user_id)
            self._active_orgs[organization_id] = (
                self._active_orgs.get(organization_id, 0) + 1
            )
            for key in keys:
                self._history.setdefault(key, deque()).append(now)
        try:
            yield
        finally:
            with self._lock:
                self._active_users.remove(user_id)
                self._active_orgs[organization_id] -= 1
                if not self._active_orgs[organization_id]:
                    del self._active_orgs[organization_id]
                self._slots.release()


assistant_admission = AssistantAdmission()

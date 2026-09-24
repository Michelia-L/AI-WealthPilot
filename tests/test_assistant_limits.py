"""Admission must reject promptly, share capacity, and recover after failures."""

from contextlib import ExitStack

import pytest

from api.assistant_limits import AssistantAdmission, AssistantBusy, AssistantLimited


def test_global_capacity_is_shared_across_organizations():
    admission = AssistantAdmission()
    with ExitStack() as stack:
        for i in range(4):
            stack.enter_context(admission.admit(f"user-{i}", f"org-{i}"))
        with pytest.raises(AssistantBusy):
            with admission.admit("another", "another-org"):
                pytest.fail("Global capacity exceeded")
    with admission.admit("another", "another-org"):
        pass


def test_organization_concurrency_and_exception_cleanup():
    admission = AssistantAdmission()
    with admission.admit("first", "org"), admission.admit("second", "org"):
        with pytest.raises(AssistantBusy):
            with admission.admit("third", "org"):
                pytest.fail("Organization capacity exceeded")
        # A rejection must not leak a global slot.
        with admission.admit("fourth", "other-org"):
            pass
    with pytest.raises(RuntimeError):
        with admission.admit("first", "org"):
            raise RuntimeError("synthetic")
    with admission.admit("first", "org"):
        pass


def test_sliding_window_expiry_and_idle_key_cleanup(monkeypatch):
    admission = AssistantAdmission()
    now = [100.0]
    monkeypatch.setattr("api.assistant_limits.time.monotonic", lambda: now[0])
    for _ in range(admission.USER_REQUESTS):
        with admission.admit("user", "org"):
            pass
    now[0] += 30.1
    with pytest.raises(AssistantLimited) as exc:
        with admission.admit("user", "org"):
            pytest.fail("Rate limit bypassed")
    assert exc.value.retry_after == 30
    now[0] = 160.0
    with admission.admit("new-user", "new-org"):
        assert ("user", "user") not in admission._history
        assert ("org", "org") not in admission._history
    with admission.admit("user", "org"):
        pass


def test_simultaneous_admissions_enforce_global_capacity():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    admission = AssistantAdmission()
    start, finish = Barrier(12), Barrier(12)

    def attempt(i):
        start.wait(timeout=5)
        try:
            with admission.admit(f"user-{i}", f"org-{i}"):
                finish.wait(timeout=5)
                return True
        except AssistantBusy:
            finish.wait(timeout=5)
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        assert sum(pool.map(attempt, range(12))) == 4

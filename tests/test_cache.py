"""Version replacement, expiry and concurrent refresh regression tests."""

from threading import Event, Thread

from api.cache import TTLCache


def test_versions_replace_in_place_and_hits_skip_factory():
    cache = TTLCache()
    for version in range(100):
        assert (
            cache.get_or_set("fleet:en", 86400, lambda v=version: v, version=version)
            == version
        )
        assert (
            cache.get_or_set("fleet:en", 86400, lambda: None, version=version)
            == version
        )
    assert len(cache._entries) == 1


def test_expired_keys_are_removed_without_being_read(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("api.cache.time.monotonic", lambda: now[0])
    cache = TTLCache()
    cache.get_or_set("yesterday:en", 10, lambda: "old")
    now[0] = 10
    assert cache.get_or_set("today:en", 10, lambda: "new") == "new"
    assert set(cache._entries) == {"today:en"}


def test_older_inflight_version_does_not_overwrite_newer():
    cache = TTLCache()
    started, resume = Event(), Event()

    def slow():
        started.set()
        assert resume.wait(5)
        return "old"

    thread = Thread(target=lambda: cache.get_or_set("fleet", 60, slow, version=1))
    thread.start()
    try:
        assert started.wait(5)
        assert cache.get_or_set("fleet", 60, lambda: "new", version=2) == "new"
    finally:
        resume.set()
        thread.join(5)
    assert cache.get_or_set("fleet", 60, lambda: None, version=2) == "new"

"""
Unit tests for the CME Cache Manager.

Tests cover:
    - Save/load roundtrip
    - TTL-based validity checks
    - Parameter hash mismatch invalidation
    - Stale cache detection
    - Manual cache invalidation
    - Edge cases (missing files, corrupt data)
"""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.portfolio.cme_cache import CMECacheManager


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory for each test."""
    d = tmp_path / "test_cme_cache"
    d.mkdir()
    return d


@pytest.fixture
def manager(cache_dir: Path) -> CMECacheManager:
    """Create a CMECacheManager with short TTL for testing."""
    return CMECacheManager(cache_dir=cache_dir, ttl_days=90)


@pytest.fixture
def sample_report() -> dict:
    """Minimal CMEReport dict for testing."""
    return {
        "as_of_date": "2026-06-15",
        "data_lookback_years": 5,
        "risk_free_rate": 0.043,
        "risk_free_rate_source": "fred_api",
        "inflation_assumption": 0.025,
        "asset_classes": [
            {
                "name": "US Equity",
                "ticker": "SPY",
                "expected_return": 0.08,
                "volatility": 0.16,
                "sharpe_ratio": 0.23,
                "max_drawdown": -0.25,
                "var_95": 0.016,
                "cvar_95": 0.024,
                "data_points": 1250,
            },
        ],
        "correlation_matrix": {
            "US Equity": {"US Equity": 1.0},
        },
        "methodology_notes": "Test CME",
        "iv_blending_tau": 0.5,
        "iv_data_available": False,
    }


@pytest.fixture
def sample_params_hash() -> str:
    """A deterministic params hash for testing."""
    return CMECacheManager.compute_params_hash(
        lookback_years=5,
        inflation=0.025,
        asset_tickers={"us_equity": {"ticker": "SPY", "name": "US Equity"}},
        iv_blending_tau=0.5,
    )


# ============================================================
# Tests
# ============================================================

class TestCMECacheManager:
    """Test suite for CMECacheManager."""

    def test_save_and_load_roundtrip(
        self, manager: CMECacheManager, sample_report: dict, sample_params_hash: str
    ):
        """Cache should survive a save → load roundtrip."""
        manager.save(sample_report, sample_params_hash)
        loaded = manager.load()

        assert loaded is not None
        assert loaded["as_of_date"] == "2026-06-15"
        assert loaded["risk_free_rate"] == 0.043
        assert len(loaded["asset_classes"]) == 1
        assert loaded["asset_classes"][0]["ticker"] == "SPY"

    def test_cache_valid_within_ttl(
        self, manager: CMECacheManager, sample_report: dict, sample_params_hash: str
    ):
        """Cache should be valid when within TTL and params match."""
        manager.save(sample_report, sample_params_hash)
        assert manager.is_valid(sample_params_hash) is True

    def test_cache_stale_after_ttl(
        self, cache_dir: Path, sample_report: dict, sample_params_hash: str
    ):
        """Cache should be invalid (but stale) after TTL expires."""
        # Use a very short TTL
        manager = CMECacheManager(cache_dir=cache_dir, ttl_days=0)
        manager.save(sample_report, sample_params_hash)

        # Manually set computed_at to the past
        meta_path = cache_dir / "cme_metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        past = datetime.now(timezone.utc) - timedelta(days=1)
        meta["computed_at"] = past.isoformat()
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        assert manager.is_valid(sample_params_hash) is False
        assert manager.is_stale() is True

    def test_params_hash_mismatch_invalidates(
        self, manager: CMECacheManager, sample_report: dict, sample_params_hash: str
    ):
        """Cache should be invalid when params hash doesn't match."""
        manager.save(sample_report, sample_params_hash)

        different_hash = CMECacheManager.compute_params_hash(
            lookback_years=10,  # Changed!
            inflation=0.025,
            asset_tickers={"us_equity": {"ticker": "SPY", "name": "US Equity"}},
            iv_blending_tau=0.5,
        )

        assert manager.is_valid(different_hash) is False
        # But stale cache is still available
        assert manager.is_stale() is True
        assert manager.load() is not None

    def test_invalidate_clears_cache(
        self, manager: CMECacheManager, sample_report: dict, sample_params_hash: str
    ):
        """invalidate() should remove all cache files."""
        manager.save(sample_report, sample_params_hash)
        assert manager.is_valid(sample_params_hash) is True

        manager.invalidate()

        assert manager.is_valid(sample_params_hash) is False
        assert manager.is_stale() is False
        assert manager.load() is None

    def test_load_returns_none_when_no_cache(self, manager: CMECacheManager):
        """load() should return None when no cache files exist."""
        assert manager.load() is None

    def test_is_valid_returns_false_when_no_cache(
        self, manager: CMECacheManager, sample_params_hash: str
    ):
        """is_valid() should return False when no cache exists."""
        assert manager.is_valid(sample_params_hash) is False

    def test_is_stale_returns_false_when_no_cache(self, manager: CMECacheManager):
        """is_stale() should return False when no cache files exist."""
        assert manager.is_stale() is False

    def test_get_metadata_returns_none_when_no_cache(self, manager: CMECacheManager):
        """get_metadata() should return None when no cache exists."""
        assert manager.get_metadata() is None

    def test_get_metadata_enriched_fields(
        self, manager: CMECacheManager, sample_report: dict, sample_params_hash: str
    ):
        """get_metadata() should include enriched computed fields."""
        manager.save(sample_report, sample_params_hash)
        meta = manager.get_metadata()

        assert meta is not None
        assert "computed_at" in meta
        assert "params_hash" in meta
        assert meta["params_hash"] == sample_params_hash
        assert "is_expired" in meta
        assert meta["is_expired"] is False
        assert "cache_dir" in meta

    def test_compute_params_hash_deterministic(self):
        """Same inputs should produce the same hash."""
        tickers = {"a": {"ticker": "SPY", "name": "US"}}
        h1 = CMECacheManager.compute_params_hash(5, 0.025, tickers, 0.5)
        h2 = CMECacheManager.compute_params_hash(5, 0.025, tickers, 0.5)
        assert h1 == h2
        assert len(h1) == 8  # MD5 truncated to 8 chars

    def test_compute_params_hash_changes_with_input(self):
        """Different inputs should produce different hashes."""
        tickers = {"a": {"ticker": "SPY", "name": "US"}}
        h1 = CMECacheManager.compute_params_hash(5, 0.025, tickers, 0.5)
        h2 = CMECacheManager.compute_params_hash(10, 0.025, tickers, 0.5)
        h3 = CMECacheManager.compute_params_hash(5, 0.03, tickers, 0.5)
        h4 = CMECacheManager.compute_params_hash(5, 0.025, tickers, 0.7)

        assert h1 != h2
        assert h1 != h3
        assert h1 != h4

    def test_corrupt_report_file_returns_none(
        self, manager: CMECacheManager, cache_dir: Path
    ):
        """load() should handle corrupt JSON gracefully."""
        cache_dir.mkdir(parents=True, exist_ok=True)
        report_path = cache_dir / "cme_report_latest.json"
        report_path.write_text("NOT VALID JSON {{{", encoding="utf-8")

        assert manager.load() is None

    def test_corrupt_metadata_returns_invalid(
        self, manager: CMECacheManager, cache_dir: Path, sample_params_hash: str
    ):
        """is_valid() should handle corrupt metadata gracefully."""
        cache_dir.mkdir(parents=True, exist_ok=True)
        meta_path = cache_dir / "cme_metadata.json"
        meta_path.write_text("BROKEN", encoding="utf-8")

        assert manager.is_valid(sample_params_hash) is False

    def test_save_creates_directory(self, tmp_path: Path, sample_report: dict):
        """save() should create the cache directory if it doesn't exist."""
        nested_dir = tmp_path / "a" / "b" / "c"
        manager = CMECacheManager(cache_dir=nested_dir, ttl_days=90)

        h = CMECacheManager.compute_params_hash(5, 0.025, {}, 0.5)
        manager.save(sample_report, h)

        assert nested_dir.exists()
        assert manager.load() is not None

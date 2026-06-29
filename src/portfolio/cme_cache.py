"""
AI WealthPilot - CME Cache Manager

File-based caching layer for Capital Market Expectations (CME) reports.
CME is a strategic, long-term forecast that does not need to be
recomputed on every IPS workflow run. This module provides TTL-based
caching with parameter-hash validation and graceful degradation.

Cache strategy:
    1. VALID cache (within TTL + matching params) → instant return
    2. STALE cache (expired TTL or mismatched params) → attempt refresh,
       fall back to stale data on failure (stale-while-revalidate)
    3. NO cache → full computation required


"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.config import CME_CACHE_DIR, CME_CACHE_TTL_DAYS

logger = logging.getLogger(__name__)

# File names within the cache directory
_REPORT_FILENAME = "cme_report_latest.json"
_METADATA_FILENAME = "cme_metadata.json"


class CMECacheManager:
    """
    File-based CME cache with TTL-based expiration and parameter
    hash validation.

    The cache stores two files:
        - cme_report_latest.json: serialized CMEReport (model_dump)
        - cme_metadata.json: timestamp, params hash, TTL config

    Thread-safety: file writes use atomic rename pattern to avoid
    partial reads. Not designed for multi-process concurrency.

    Attributes:
        cache_dir: Directory for cache files.
        ttl_days: Number of days before cache expires.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        ttl_days: Optional[int] = None,
    ) -> None:
        """
        Initialize cache manager.

        Args:
            cache_dir: Override cache directory. Defaults to CME_CACHE_DIR.
            ttl_days: Override TTL. Defaults to CME_CACHE_TTL_DAYS.
        """
        self.cache_dir = Path(cache_dir) if cache_dir else CME_CACHE_DIR
        self.ttl_days = ttl_days if ttl_days is not None else CME_CACHE_TTL_DAYS

    @property
    def _report_path(self) -> Path:
        return self.cache_dir / _REPORT_FILENAME

    @property
    def _metadata_path(self) -> Path:
        return self.cache_dir / _METADATA_FILENAME

    # Public Interface

    def save(self, report_dict: dict, params_hash: str) -> None:
        """
        Persist a CMEReport (as dict) and its metadata to disk.

        Creates the cache directory if it does not exist. Writes are
        performed to temporary files first, then renamed for atomicity.

        Args:
            report_dict: CMEReport.model_dump() output.
            params_hash: Hash of computation parameters for validation.
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "params_hash": params_hash,
            "ttl_days": self.ttl_days,
            "as_of_date": report_dict.get("as_of_date", ""),
            "asset_class_count": len(report_dict.get("asset_classes", [])),
        }

        # Write report
        tmp_report = self._report_path.with_suffix(".tmp")
        tmp_report.write_text(
            json.dumps(report_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_report.replace(self._report_path)

        # Write metadata
        tmp_meta = self._metadata_path.with_suffix(".tmp")
        tmp_meta.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_meta.replace(self._metadata_path)

        logger.info(
            "CME cache saved: as_of=%s, assets=%d, ttl=%d days",
            metadata["as_of_date"],
            metadata["asset_class_count"],
            self.ttl_days,
        )

    def load(self) -> Optional[dict]:
        """
        Load the cached CMEReport dict from disk.

        Returns:
            CMEReport dict if cache file exists and is valid JSON,
            None otherwise.
        """
        if not self._report_path.exists():
            return None

        try:
            text = self._report_path.read_text(encoding="utf-8")
            return json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read CME cache: %s", e)
            return None

    def is_valid(self, params_hash: str) -> bool:
        """
        Check whether the cache is valid (exists, not expired, params match).

        Args:
            params_hash: Hash of current computation parameters.

        Returns:
            True if cache can be used directly without recomputation.
        """
        metadata = self._load_metadata()
        if metadata is None:
            return False

        # Check parameter consistency
        if metadata.get("params_hash") != params_hash:
            logger.debug("CME cache params mismatch: expected %s, got %s",
                         params_hash, metadata.get("params_hash"))
            return False

        # Check TTL
        return not self._is_expired(metadata)

    def is_stale(self) -> bool:
        """
        Check whether a cache exists but is expired or has mismatched params.

        Stale cache can still be used as a fallback when fresh computation
        fails (stale-while-revalidate pattern).

        Returns:
            True if cache files exist on disk (regardless of TTL/params).
        """
        return (
            self._report_path.exists()
            and self._metadata_path.exists()
        )

    def get_metadata(self) -> Optional[dict]:
        """
        Return cache metadata for diagnostics and audit trail.

        Returns:
            Metadata dict with computed_at, params_hash, ttl_days, etc.,
            or None if no cache exists.
        """
        metadata = self._load_metadata()
        if metadata is None:
            return None

        # Enrich with computed fields
        metadata["is_expired"] = self._is_expired(metadata)
        metadata["cache_dir"] = str(self.cache_dir)
        return metadata

    def invalidate(self) -> None:
        """
        Remove all cache files, forcing recomputation on next call.
        """
        for path in [self._report_path, self._metadata_path]:
            if path.exists():
                path.unlink()
                logger.debug("Removed cache file: %s", path)

        logger.info("CME cache invalidated")

    # Static Helpers

    @staticmethod
    def compute_params_hash(
        lookback_years: int,
        inflation: float,
        asset_tickers: dict,
        iv_blending_tau: float,
    ) -> str:
        """
        Compute a deterministic hash of CME computation parameters.

        If any parameter changes, the hash changes and the cache is
        considered invalid. This ensures parameter consistency.

        Args:
            lookback_years: Historical data lookback period.
            inflation: Long-term inflation assumption.
            asset_tickers: Asset class → ticker mapping dict.
            iv_blending_tau: Bayesian blending weight.

        Returns:
            8-character hex MD5 hash string.
        """
        # Normalize asset_tickers to a sorted, stable representation
        ticker_keys = sorted(asset_tickers.keys()) if asset_tickers else []
        ticker_repr = json.dumps(
            {k: asset_tickers[k] for k in ticker_keys},
            sort_keys=True,
            ensure_ascii=False,
        )

        content = f"{lookback_years}|{inflation}|{ticker_repr}|{iv_blending_tau}"
        return hashlib.md5(content.encode()).hexdigest()[:8]

    # Private Helpers

    def _load_metadata(self) -> Optional[dict]:
        """Load and parse the metadata JSON file."""
        if not self._metadata_path.exists():
            return None

        try:
            text = self._metadata_path.read_text(encoding="utf-8")
            return json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read CME cache metadata: %s", e)
            return None

    def _is_expired(self, metadata: dict) -> bool:
        """
        Check if the cache has exceeded its TTL.

        Args:
            metadata: Parsed metadata dict with 'computed_at' key.

        Returns:
            True if cache is expired.
        """
        computed_at_str = metadata.get("computed_at")
        if not computed_at_str:
            return True

        try:
            computed_at = datetime.fromisoformat(computed_at_str)
            # Ensure timezone-aware comparison
            now = datetime.now(timezone.utc)
            if computed_at.tzinfo is None:
                computed_at = computed_at.replace(tzinfo=timezone.utc)
            age_days = (now - computed_at).total_seconds() / 86400
            return age_days > self.ttl_days
        except (ValueError, TypeError):
            return True

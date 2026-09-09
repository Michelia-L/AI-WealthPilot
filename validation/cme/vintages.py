"""Immutable, content-addressed CME evidence independent of the live cache."""

import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.portfolio.cme_blending import blend_assumption
from src.portfolio.cme_models import AssetClassCME, CMEReport

Quality = Literal["fresh", "cached", "stale", "fallback", "unknown"]
Component = Literal[
    "history", "implied", "forward", "correlation", "risk_free", "inflation", "fx"
]


class FrozenRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class NumericInput(FrozenRecord):
    """Selected numeric building blocks only; never a raw provider response."""

    name: str = Field(min_length=1)
    value: float
    units: str = Field(min_length=1)


class SourceRecord(FrozenRecord):
    component: Component
    asset_key: str | None = None  # None denotes a shared source.
    provider: str = Field(min_length=1)
    proxy: str = Field(min_length=1)
    observed_at: datetime | None = None
    available_at: datetime | None = None
    retrieved_at: datetime | None = None
    quality: Quality = "unknown"
    revision_policy: Literal[
        "point_in_time", "not_revised", "latest_revised", "fixed_assumption", "unknown"
    ] = "unknown"
    snapshot_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    inputs: tuple[NumericInput, ...] = ()

    @field_validator("observed_at", "available_at", "retrieved_at")
    @classmethod
    def aware_times(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Source timestamps must include a timezone")
            return value.astimezone(timezone.utc)
        return value


class AssetSnapshot(AssetClassCME):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    key: str = Field(min_length=1)
    implied_volatility: float | None = Field(default=None, ge=0)
    blended_volatility: float | None = Field(default=None, ge=0)
    data_points: int = Field(default=0, ge=0)


class CMEVintage(FrozenRecord):
    schema_version: Literal["1.0"] = "1.0"
    as_of: date
    generated_at: datetime
    report_as_of: date
    vintage_type: Literal["observed", "reconstructed"]
    model_version: str = Field(min_length=1)
    code_version: str = Field(min_length=1)
    base_currency: str = Field(pattern=r"^[A-Z]{3}$")
    fx_treatment: str = Field(min_length=1)
    lookback_years: int = Field(ge=1)
    inflation_assumption: float
    iv_blending_tau: float = Field(ge=0, le=1)
    forward_blending_omega: float = Field(ge=0, le=1)
    risk_free_rate: float
    risk_free_rate_source: str
    cache_status: Quality
    asset_classes: tuple[AssetSnapshot, ...] = Field(min_length=1)
    # Matrix order is exactly asset_classes order; unknown entries are null.
    correlation_matrix: tuple[tuple[float | None, ...], ...]
    sources: tuple[SourceRecord, ...] = ()

    @field_validator("generated_at")
    @classmethod
    def generated_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_structure(self):
        keys = [a.key for a in self.asset_classes]
        if len(set(keys)) != len(keys):
            raise ValueError("Vintage asset keys must be unique")
        n = len(keys)
        if len(self.correlation_matrix) != n or any(
            len(row) != n for row in self.correlation_matrix
        ):
            raise ValueError("Correlation dimensions must match ordered assets")
        for i, row in enumerate(self.correlation_matrix):
            for j, value in enumerate(row):
                other = self.correlation_matrix[j][i]
                if value is not None and (
                    not -1 <= value <= 1 or (i == j and abs(value - 1) > 1e-8)
                ):
                    raise ValueError("Invalid correlation entry")
                if (value is None) != (other is None) or (
                    value is not None and abs(value - other) > 1e-8
                ):
                    raise ValueError("Correlation matrix must be symmetric")
        if any(
            s.asset_key is not None and s.asset_key not in keys for s in self.sources
        ):
            raise ValueError("Source asset keys must belong to the vintage")
        return self

    def canonical_json(self):
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    @property
    def vintage_id(self):
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()

    @property
    def decision_cutoff(self):
        return (
            self.generated_at
            if self.vintage_type == "observed"
            else datetime.combine(self.as_of, time.max, timezone.utc)
        )

    def strict_issues(self):
        """Fail closed on unproven timing; provenance is caller attestation."""
        issues = []
        if self.cache_status == "unknown":
            issues.append("unknown_cache_status")
        if self.vintage_type == "observed" and self.generated_at.date() != self.as_of:
            issues.append("observed_generation_date_mismatch")
        if (
            self.vintage_type == "reconstructed"
            and self.generated_at.date() < self.as_of
        ):
            issues.append("reconstruction_precedes_forecast_date")
        if self.report_as_of > self.as_of:
            issues.append("future_report_date")
        required = {(None, c) for c in ("correlation", "risk_free", "inflation", "fx")}
        for asset in self.asset_classes:
            if self.vintage_type == "reconstructed":
                # Rounded production outputs/components can differ by <=1e-6.
                # An unexplained forecast must not masquerade as a replay of
                # the archived linear-blend inputs.
                if asset.historical_return is None:
                    issues.append(f"missing_historical_component:{asset.key}")
                elif (
                    abs(
                        asset.expected_return
                        - blend_assumption(
                            asset.historical_return,
                            asset.forward_return,
                            self.forward_blending_omega,
                        )
                    )
                    > 1.1e-6
                ):
                    issues.append(f"inconsistent_return_components:{asset.key}")
                volatility = (
                    asset.blended_volatility
                    if asset.blended_volatility is not None
                    else asset.volatility
                )
                if (
                    abs(
                        volatility
                        - blend_assumption(
                            asset.volatility,
                            asset.implied_volatility,
                            self.iv_blending_tau,
                        )
                    )
                    > 1.1e-6
                ):
                    issues.append(f"inconsistent_volatility_components:{asset.key}")
            required.add((asset.key, "history"))
            if asset.implied_volatility is not None:
                required.add((asset.key, "implied"))
            if asset.forward_return is not None:
                required.add((asset.key, "forward"))
        for key, component in sorted(required, key=lambda x: (x[0] or "", x[1])):
            matches = [
                s
                for s in self.sources
                if s.component == component and s.asset_key in (None, key)
            ]
            if not matches:
                issues.append(f"missing_source:{key or 'shared'}:{component}")
        for source in self.sources:
            label = f"{source.asset_key or 'shared'}:{source.component}"
            times = (source.observed_at, source.available_at, source.retrieved_at)
            if any(t is None for t in times):
                issues.append(f"missing_source_dates:{label}")
                continue
            if (
                not source.observed_at
                <= source.available_at
                <= source.retrieved_at
                <= self.generated_at
            ):
                issues.append(f"invalid_source_chronology:{label}")
            if source.available_at > self.decision_cutoff:
                issues.append(f"source_not_available_at_decision:{label}")
            if source.quality == "unknown":
                issues.append(f"unknown_source_quality:{label}")
            # An actual saved observation may use then-current revised history.
            # A reconstruction needs dated vintages or non-revised evidence.
            if source.revision_policy == "unknown" or (
                self.vintage_type == "reconstructed"
                and source.revision_policy == "latest_revised"
            ):
                issues.append(f"unproven_revision_policy:{label}")
        return sorted(set(issues))

    @classmethod
    def from_report(
        cls,
        report: CMEReport,
        *,
        as_of,
        generated_at,
        vintage_type,
        model_version,
        code_version,
        base_currency,
        fx_treatment,
        cache_status,
        sources=(),
    ):
        """Archive supplied output; never call compute_cme or infer missing dates.

        as_of is the forecast decision date. report.as_of_date is usually the
        last price date and is deliberately retained as a separate field.
        """
        assets = tuple(AssetSnapshot(**a.model_dump()) for a in report.asset_classes)
        matrix = []
        for asset in assets:
            row = report.correlation_matrix.get(asset.name, {})
            matrix.append(tuple(row.get(other.name) for other in assets))
        return cls(
            as_of=as_of,
            generated_at=generated_at,
            report_as_of=report.as_of_date,
            vintage_type=vintage_type,
            model_version=model_version,
            code_version=code_version,
            base_currency=base_currency,
            fx_treatment=fx_treatment,
            lookback_years=report.data_lookback_years,
            inflation_assumption=report.inflation_assumption,
            iv_blending_tau=report.iv_blending_tau,
            forward_blending_omega=report.forward_blending_omega,
            risk_free_rate=report.risk_free_rate,
            risk_free_rate_source=report.risk_free_rate_source,
            cache_status=cache_status,
            asset_classes=assets,
            correlation_matrix=tuple(matrix),
            sources=sources,
        )


class VintageStore:
    """Append-only API; SHA-256 filenames, atomic publication, no overwrite.

    Content hashes detect accidental corruption, not malicious rewriting by a
    filesystem administrator. Identical content is idempotent; changed evidence
    gets a different ID, so model versions can coexist on the same forecast date.
    """

    def __init__(self, directory):
        self.directory = Path(directory)

    def save(self, vintage: CMEVintage):
        # Revalidate even if a caller used Pydantic's unchecked model_copy.
        vintage = CMEVintage.model_validate_json(vintage.canonical_json())
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{vintage.vintage_id}.json"
        content = vintage.canonical_json()
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if destination.read_text(encoding="utf-8") != content:
                    raise ValueError("Vintage archive integrity mismatch") from None
        finally:
            temporary.unlink(missing_ok=True)
        return vintage.vintage_id

    def load(self, vintage_id):
        if not re.fullmatch(r"[a-f0-9]{64}", vintage_id):
            raise ValueError("Invalid vintage ID")
        vintage = CMEVintage.model_validate_json(
            (self.directory / f"{vintage_id}.json").read_text(encoding="utf-8")
        )
        if vintage.vintage_id != vintage_id:
            raise ValueError("Vintage archive integrity mismatch")
        return vintage

    def list(self):
        return tuple(
            self.load(path.stem) for path in sorted(self.directory.glob("*.json"))
        )

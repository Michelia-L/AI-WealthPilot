"""Offline proofs of CME evidence preservation, maturity and blend calibration."""

import json
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from src.portfolio.cme_cache import CMECacheManager
from src.portfolio.cme_models import AssetClassCME, CMEReport
from validation.cme import (
    BlendGrid,
    CalibrationConfig,
    CMEVintage,
    NumericInput,
    RealizedPanel,
    SourceRecord,
    VintageStore,
    calibrate,
    evaluate_blending,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("CME validation must stay offline")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    for name in ("compute_cme", "fetch_implied_volatility", "fetch_forward_returns"):
        monkeypatch.setattr(f"src.portfolio.cme_engine.{name}", blocked)


def make_vintage(as_of="2019-12-31", model_version="fixture-v1", quality="fresh"):
    assets = [
        AssetClassCME(
            name=key.upper(),
            key=key,
            ticker=ticker,
            expected_return=mu + 0.01,
            historical_return=mu,
            forward_return=mu + 0.02,
            volatility=vol,
            implied_volatility=vol + 0.10,
            blended_volatility=vol + 0.05,
            sharpe_ratio=0,
            max_drawdown=-0.2,
            var_95=0.02,
            cvar_95=0.03,
            data_points=500,
        )
        for key, ticker, mu, vol in [
            ("equity", "SPY", 0.06, 0.15),
            ("bonds", "AGG", 0.02, 0.05),
            ("gold", "GLD", 0.04, 0.10),
        ]
    ]
    report = CMEReport(
        as_of_date=as_of,
        data_lookback_years=5,
        risk_free_rate=0.02,
        risk_free_rate_source="synthetic",
        inflation_assumption=0.025,
        asset_classes=assets,
        correlation_matrix={
            a.name: {b.name: 1.0 if a.key == b.key else 0.1 for b in assets}
            for a in assets
        },
    )
    earlier = pd.Timestamp(as_of, tz="UTC").to_pydatetime()
    generated = pd.Timestamp(as_of, tz="UTC").replace(hour=20).to_pydatetime()
    sources = tuple(
        SourceRecord(
            component=c,
            provider="synthetic",
            proxy="fixture",
            observed_at=earlier,
            available_at=earlier,
            retrieved_at=generated,
            quality=quality,
            revision_policy="point_in_time",
            snapshot_sha256="a" * 64,
            inputs=(
                NumericInput(
                    name="fixture_assumption", value=0.02, units="annual_decimal"
                ),
            ),
        )
        for c in (
            "history",
            "implied",
            "forward",
            "correlation",
            "risk_free",
            "inflation",
            "fx",
        )
    )
    return CMEVintage.from_report(
        report,
        as_of=as_of,
        generated_at=generated,
        vintage_type="observed",
        model_version=model_version,
        code_version="fixture-sha",
        base_currency="CNY",
        fx_treatment="unhedged_cny",
        cache_status=quality,
        sources=sources,
    )


@pytest.fixture
def vintage():
    return make_vintage()


@pytest.fixture
def panel():
    dates = pd.bdate_range("2018-01-01", "2025-12-31")
    rng = np.random.default_rng(63)
    frame = pd.DataFrame(
        rng.normal([0.0003, 0.0001, 0.0002], [0.012, 0.004, 0.008], (len(dates), 3)),
        index=dates,
        columns=["equity", "bonds", "gold"],
    )
    return RealizedPanel(
        frame,
        {"equity": "SPY", "bonds": "AGG", "gold": "GLD"},
        "CNY",
        "unhedged_cny",
        "synthetic daily total returns",
        "synthetic",
        "2018-01-01",
        "2025-12-31",
    )


def small_config(**kwargs):
    return CalibrationConfig(
        horizons=(1,), min_observations_per_year=2, min_vintages=1, **kwargs
    )


def test_vintage_round_trip_and_deep_immutability(vintage):
    assert vintage.strict_issues() == []
    restored = CMEVintage.model_validate_json(vintage.canonical_json())
    assert restored == vintage and restored.vintage_id == vintage.vintage_id
    assert restored.as_of.isoformat() == "2019-12-31"
    assert restored.sources[0].available_at == datetime(
        2019, 12, 31, tzinfo=timezone.utc
    )
    with pytest.raises(ValidationError):
        vintage.model_version = "changed"
    with pytest.raises(ValidationError):
        vintage.asset_classes[0].expected_return = 0.9
    with pytest.raises(TypeError):
        vintage.correlation_matrix[0][0] = 0.5
    with pytest.raises(ValidationError):
        vintage.sources[0].inputs[0].value = 0.8


def test_archive_is_atomic_idempotent_and_independent_of_cache(vintage, tmp_path):
    store = VintageStore(tmp_path / "vintages")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(store.save, [vintage] * 8))
    assert len(set(ids)) == 1
    assert len(list((tmp_path / "vintages").glob("*.json"))) == 1
    assert not list((tmp_path / "vintages").glob("*.tmp"))
    before = (tmp_path / "vintages" / f"{ids[0]}.json").read_bytes()
    cache = CMECacheManager(cache_dir=tmp_path / "cache")
    cache.save({"as_of_date": "2026-01-01", "asset_classes": []}, "new")
    cache.invalidate()
    assert store.load(ids[0]) == vintage
    assert (tmp_path / "vintages" / f"{ids[0]}.json").read_bytes() == before
    updated = vintage.model_copy(update={"model_version": "fixture-v2"})
    store.save(updated)
    assert {v.model_version for v in store.list()} == {"fixture-v1", "fixture-v2"}


def test_archive_rejects_corruption_and_path_traversal(vintage, tmp_path):
    store = VintageStore(tmp_path)
    identifier = store.save(vintage)
    path = tmp_path / f"{identifier}.json"
    path.write_text(vintage.canonical_json().replace("fixture-v1", "fixture-v2"))
    with pytest.raises(ValueError, match="integrity"):
        store.load(identifier)
    with pytest.raises(ValueError, match="integrity"):
        store.save(vintage)
    with pytest.raises(ValueError, match="Invalid vintage ID"):
        store.load("../outside")


def test_strict_reconstruction_never_uses_current_forward_inputs(vintage, panel):
    generated = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sources = tuple(
        s.model_copy(update={"retrieved_at": generated}) for s in vintage.sources
    )
    reconstructed = vintage.model_copy(
        update={
            "vintage_type": "reconstructed",
            "generated_at": generated,
            "sources": sources,
        }
    )
    assert (
        reconstructed.strict_issues() == []
    )  # Later retrieval of dated PIT evidence is allowed.
    forward = next(s for s in sources if s.component == "forward")
    future = forward.model_copy(
        update={"observed_at": generated, "available_at": generated}
    )
    unsuitable = reconstructed.model_copy(
        update={
            "sources": tuple(future if s.component == "forward" else s for s in sources)
        }
    )
    report = calibrate(
        [unsuitable], panel, evaluation_date="2025-12-31", config=small_config()
    )
    assert all(
        r["status"] == "unsuitable_vintage" and r["return_error"] is None
        for r in report.asset_rows
    )
    assert any(
        "source_not_available_at_decision" in issue
        for issue in report.asset_rows[0]["strict_issues"]
    )
    grid = evaluate_blending(
        [unsuitable], panel, evaluation_date="2025-12-31", config=small_config()
    )
    assert all(r["error"] is None for r in grid.rows)
    exploratory = calibrate(
        [unsuitable],
        panel,
        evaluation_date="2025-12-31",
        config=replace(small_config(), strict=False),
    )
    assert all(
        r["status"] == "ok" and not r["strict_eligible"] for r in exploratory.asset_rows
    )


def test_revised_reconstruction_and_missing_provenance_are_excluded(vintage, panel):
    sources = tuple(
        s.model_copy(update={"revision_policy": "latest_revised"})
        for s in vintage.sources
    )
    observed = vintage.model_copy(update={"sources": sources})
    assert observed.strict_issues() == []  # An actual stored, then-current observation.
    reconstructed = observed.model_copy(update={"vintage_type": "reconstructed"})
    assert any("revision_policy" in s for s in reconstructed.strict_issues())
    missing = vintage.model_copy(update={"sources": ()})
    report = calibrate(
        [missing], panel, evaluation_date="2025-12-31", config=small_config()
    )
    assert all(r["status"] == "unsuitable_vintage" for r in report.asset_rows)


def test_as_of_is_forecast_date_not_last_market_or_cache_date(vintage):
    cached = vintage.model_copy(
        update={
            "report_as_of": pd.Timestamp("2019-11-29").date(),
            "cache_status": "cached",
        }
    )
    assert cached.strict_issues() == []
    assert cached.as_of != cached.report_as_of
    wrong = cached.model_copy(update={"as_of": pd.Timestamp("2019-11-29").date()})
    assert "observed_generation_date_mismatch" in wrong.strict_issues()


def test_hand_cagr_volatility_and_strictly_future_window(vintage, panel):
    dates = pd.to_datetime(["2019-12-31", "2020-01-02", "2020-12-31", "2021-01-04"])
    frame = pd.DataFrame(
        {
            "equity": [99, 0.1, 0.1, 99],
            "bonds": [99, -0.1, 0.1, 99],
            "gold": [99, 0.1, -0.1, 99],
        },
        index=dates,
    )
    panel = replace(
        panel, returns=frame, coverage_start="2019-12-31", coverage_end="2021-01-04"
    )
    report = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    a = report.asset_rows[0]
    assert a["first_observation"] == pd.Timestamp("2020-01-02")
    assert a["observations"] == 2 and a["realized_return"] == pytest.approx(0.21)
    assert a["realized_volatility"] == 0 and a["predicted_realized_ratio"] is None
    b = report.asset_rows[1]
    assert b["realized_return"] == pytest.approx(-0.01)
    assert b["realized_volatility"] == pytest.approx(
        np.std([-0.1, 0.1], ddof=1) * np.sqrt(252)
    )
    assert b["return_error"] == pytest.approx(-0.01 - 0.03)
    assert report.correlation_rows[0]["status"] == "constant_series"
    assert report.correlation_rows[2]["realized_correlation"] == pytest.approx(-1)


def test_multiyear_calendar_cagr_and_leap_anniversary(panel):
    vintage = make_vintage("2020-02-29")
    dates = pd.to_datetime(
        [
            "2020-03-02",
            "2021-02-26",
            "2021-03-01",
            "2022-02-28",
            "2022-03-01",
            "2023-02-28",
        ]
    )
    frame = pd.DataFrame(0.1, index=dates, columns=panel.returns.columns)
    panel = replace(
        panel, returns=frame, coverage_start="2020-02-29", coverage_end="2023-02-28"
    )
    result = calibrate(
        [vintage],
        panel,
        evaluation_date="2023-02-28",
        config=replace(small_config(), horizons=(1, 3)),
    )
    assert result.asset_rows[0]["horizon_end"] == pd.Timestamp("2021-02-28")
    assert result.asset_rows[3]["realized_return"] == pytest.approx(
        (1.1**6) ** (1 / 3) - 1
    )
    assert result.asset_rows[3]["observations"] == 6


def test_maturity_is_enforced_even_when_future_data_supplied(vintage, panel):
    report = calibrate([vintage], panel, evaluation_date="2022-12-30")
    assert all(
        r["status"] == "immature"
        for r in report.asset_rows
        if r["horizon_years"] in (3, 5)
    )
    assert all(
        r["realized_return"] is None
        for r in report.asset_rows
        if r["horizon_years"] == 3
    )
    mature = calibrate([vintage], panel, evaluation_date="2022-12-31")
    assert all(
        r["status"] == "ok" for r in mature.asset_rows if r["horizon_years"] == 3
    )


def test_missing_returns_proxy_and_currency_are_not_silently_replaced(vintage, panel):
    panel.returns.loc["2020-06-01", "equity"] = np.nan
    panel.proxies["bonds"] = "different_proxy"
    report = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert [r["status"] for r in report.asset_rows] == [
        "missing_returns",
        "proxy_mismatch",
        "ok",
    ]
    assert report.matrix_rows[0]["frobenius_error"] is None
    assert report.ranking_rows[0]["rank_correlation"] is None
    with pytest.raises(ValueError, match="currency"):
        calibrate(
            [vintage], replace(panel, base_currency="USD"), evaluation_date="2020-12-31"
        )


def test_known_bias_mae_rmse_and_sample_counts(panel):
    vintages = [make_vintage(f"{year}-12-31") for year in (2018, 2019, 2020)]
    panel.returns[:] = 0
    modified = []
    for vintage, error in zip(vintages, [0.01, -0.02, 0.03], strict=True):
        assets = tuple(
            a.model_copy(update={"expected_return": -error})
            for a in vintage.asset_classes
        )
        modified.append(vintage.model_copy(update={"asset_classes": assets}))
    report = calibrate(
        modified,
        panel,
        evaluation_date="2025-12-31",
        config=CalibrationConfig(horizons=(1,)),
    )
    summary = next(
        s["return"]
        for s in report.summaries
        if s["kind"] == "asset" and s["asset_key"] == "equity"
    )
    assert summary["bias"] == pytest.approx(0.02 / 3)
    assert summary["mae"] == pytest.approx(0.02)
    assert summary["rmse"] == pytest.approx(np.sqrt((0.01**2 + 0.02**2 + 0.03**2) / 3))
    assert summary["vintage_dates"] == summary["observations"] == 3
    small = calibrate(
        modified[:1],
        panel,
        evaluation_date="2025-12-31",
        config=CalibrationConfig(horizons=(1,)),
    )
    assert small.summaries[0]["return"]["mae"] is None


def test_correlation_matrix_errors_match_hand_example(vintage, panel):
    dates = pd.bdate_range("2020-01-01", periods=4)
    frame = pd.DataFrame(
        {
            "equity": [0.01, -0.01, 0.02, -0.02],
            "bonds": [0.02, -0.02, 0.04, -0.04],
            "gold": [-0.01, 0.01, -0.02, 0.02],
        },
        index=dates,
    )
    panel = replace(
        panel, returns=frame, coverage_start="2019-12-31", coverage_end="2020-12-31"
    )
    report = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    errors = [0.9, -1.1, -1.1]
    assert [r["correlation_error"] for r in report.correlation_rows] == pytest.approx(
        errors
    )
    matrix = report.matrix_rows[0]
    assert matrix["mean_absolute_correlation_error"] == pytest.approx(
        np.mean(np.abs(errors))
    )
    assert matrix["frobenius_error"] == pytest.approx(
        np.sqrt(2 * np.sum(np.square(errors)))
    )
    assert matrix["largest_underestimated_pair"] == "equity/bonds"


@pytest.mark.parametrize("quality", ["fresh", "cached", "stale", "fallback"])
def test_quality_and_versions_are_preserved_and_stratified(panel, quality):
    first = make_vintage(quality=quality)
    second = make_vintage(model_version="fixture-v2", quality=quality)
    report = calibrate(
        [first, second], panel, evaluation_date="2020-12-31", config=small_config()
    )
    summaries = [s for s in report.summaries if s["kind"] == "asset"]
    assert len(summaries) == 6
    assert {s["cache_status"] for s in summaries} == {quality}
    assert {s["source_quality"] for s in summaries} == {quality}
    assert {s["model_version"] for s in summaries} == {"fixture-v1", "fixture-v2"}
    assert json.loads(report.to_json())["metadata"]["config"]["strict"] is True


def test_blend_endpoints_and_historical_error_comparison(vintage, panel):
    report = evaluate_blending(
        [vintage],
        panel,
        evaluation_date="2020-12-31",
        grid=BlendGrid(tau=(0, 1), omega=(0, 1)),
        config=small_config(),
    )
    rows = [r for r in report.rows if r["asset_key"] == "equity"]
    assert [r["experiment_forecast"] for r in rows] == pytest.approx(
        [0.15, 0.25, 0.06, 0.08]
    )
    assert all(
        s["mae_change_vs_historical"] == pytest.approx(0)
        for s in report.summaries
        if s["weight"] == 0
    )
    assert len(report.tables()["rows"]) == 12
    assert json.loads(report.to_json())["metadata"]["grid"]["tau"] == [0, 1]


def test_missing_components_remain_historical_fallback_without_live_queries(
    vintage, panel
):
    assets = tuple(
        a.model_copy(update={"forward_return": None, "implied_volatility": None})
        for a in vintage.asset_classes
    )
    vintage = vintage.model_copy(update={"asset_classes": assets})
    before = vintage.canonical_json()
    report = evaluate_blending(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert all(r["component_status"] == "historical_fallback" for r in report.rows)
    assert all(r["error"] == pytest.approx(r["historical_error"]) for r in report.rows)
    assert vintage.canonical_json() == before
    assert all(r["fallback_assets"] == 3 for r in report.rankings)
    legacy = assets[0].model_copy(update={"historical_return": None})
    missing = vintage.model_copy(update={"asset_classes": (legacy, *assets[1:])})
    result = evaluate_blending(
        [missing], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert all(
        r["error"] is None
        for r in result.rows
        if r["asset_key"] == "equity" and r["parameter"] == "omega"
    )


def test_future_outcomes_change_errors_but_never_archived_components(vintage, panel):
    before = vintage.canonical_json()
    original = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    panel.returns.loc["2021-01-01":] *= 5
    unchanged = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert original.asset_rows == unchanged.asset_rows
    panel.returns.loc["2020-01-01":"2020-12-31"] *= 2
    altered = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert (
        original.asset_rows[0]["return_error"] != altered.asset_rows[0]["return_error"]
    )
    assert vintage.canonical_json() == before


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CalibrationConfig(horizons=()),
        lambda: CalibrationConfig(horizons=(1, 1)),
        lambda: CalibrationConfig(horizons=(0,)),
        lambda: CalibrationConfig(min_vintages=0),
        lambda: CalibrationConfig(min_rank_assets=1),
        lambda: CalibrationConfig(material_underprediction_ratio=1),
        lambda: BlendGrid(tau=(2,)),
        lambda: BlendGrid(omega=(0, 0)),
        lambda: BlendGrid(tau=(np.nan,)),
    ],
)
def test_invalid_configurations(factory):
    with pytest.raises(ValueError):
        factory()


def test_reconstruction_requires_explained_components(vintage, panel):
    asset = vintage.asset_classes[0].model_copy(update={"forward_return": None})
    reconstructed = vintage.model_copy(
        update={
            "vintage_type": "reconstructed",
            "asset_classes": (asset, *vintage.asset_classes[1:]),
        }
    )
    assert "inconsistent_return_components:equity" in reconstructed.strict_issues()
    asset = asset.model_copy(
        update={"historical_return": None, "blended_volatility": 0.9}
    )
    invalid = reconstructed.model_copy(
        update={"asset_classes": (asset, *vintage.asset_classes[1:])}
    )
    assert "missing_historical_component:equity" in invalid.strict_issues()
    assert "inconsistent_volatility_components:equity" in invalid.strict_issues()
    result = calibrate(
        [invalid], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert all(r["status"] == "unsuitable_vintage" for r in result.asset_rows)


def test_same_date_recaptures_do_not_inflate_cohort(vintage, panel):
    another = vintage.model_copy(
        update={"generated_at": vintage.generated_at.replace(hour=21)}
    )
    with pytest.raises(ValueError, match="one vintage per forecast date"):
        calibrate(
            [vintage, another],
            panel,
            evaluation_date="2020-12-31",
            config=small_config(),
        )
    with pytest.raises(ValueError, match="unique vintages"):
        calibrate([vintage, vintage], panel, evaluation_date="2020-12-31")
    with pytest.raises(ValueError, match="unique vintages"):
        calibrate([], panel, evaluation_date="2020-12-31")


def test_source_dates_and_unknown_quality_fail_closed(vintage):
    unknown = vintage.model_copy(update={"cache_status": "unknown"})
    assert "unknown_cache_status" in unknown.strict_issues()
    source = vintage.sources[0].model_copy(update={"available_at": None})
    missing = vintage.model_copy(update={"sources": (source, *vintage.sources[1:])})
    assert any("missing_source_dates" in issue for issue in missing.strict_issues())
    source = vintage.sources[0].model_copy(
        update={"observed_at": vintage.generated_at.replace(hour=21)}
    )
    invalid = vintage.model_copy(update={"sources": (source, *vintage.sources[1:])})
    assert any(
        "invalid_source_chronology" in issue for issue in invalid.strict_issues()
    )
    source = vintage.sources[0].model_copy(
        update={"quality": "unknown", "revision_policy": "unknown"}
    )
    unknown = vintage.model_copy(update={"sources": (source, *vintage.sources[1:])})
    assert any("unknown_source_quality" in issue for issue in unknown.strict_issues())
    assert any("unproven_revision_policy" in issue for issue in unknown.strict_issues())
    future = vintage.model_copy(
        update={"report_as_of": pd.Timestamp("2020-01-01").date()}
    )
    assert "future_report_date" in future.strict_issues()
    premature = vintage.model_copy(
        update={
            "vintage_type": "reconstructed",
            "as_of": pd.Timestamp("2020-01-01").date(),
        }
    )
    assert "reconstruction_precedes_forecast_date" in premature.strict_issues()


def test_typed_provenance_rejects_unstructured_provider_payloads(vintage):
    source = vintage.sources[0].model_dump()
    source["provider_response"] = {
        "profile": "not-an-input",
        "api_key": "never-archive-this",
    }
    with pytest.raises(ValidationError):
        SourceRecord.model_validate(source)
    assert "never-archive-this" not in vintage.canonical_json()
    source.pop("provider_response")
    source["retrieved_at"] = datetime(2019, 12, 31)
    with pytest.raises(ValidationError, match="timezone"):
        SourceRecord.model_validate(source)
    with pytest.raises(ValidationError, match="timezone"):
        CMEVintage.model_validate(
            {**vintage.model_dump(), "generated_at": datetime(2019, 12, 31)}
        )


@pytest.mark.parametrize(
    "update",
    [
        {"asset_classes": ()},
        {"iv_blending_tau": 1.1},
        {"correlation_matrix": ((1.0,),)},
        {"correlation_matrix": ((1.0, 2.0, 0.0), (2.0, 1.0, 0.0), (0.0, 0.0, 1.0))},
        {"correlation_matrix": ((1.0, 0.2, 0.1), (0.1, 1.0, 0.1), (0.1, 0.1, 1.0))},
        {"correlation_matrix": ((1.0, None, 0.1), (0.1, 1.0, 0.1), (0.1, 0.1, 1.0))},
    ],
)
def test_invalid_vintage_schema(vintage, update):
    with pytest.raises(ValidationError):
        CMEVintage.model_validate({**vintage.model_dump(), **update})


def test_duplicate_asset_and_foreign_source_keys_rejected(vintage):
    with pytest.raises(ValidationError, match="unique"):
        CMEVintage.model_validate(
            {**vintage.model_dump(), "asset_classes": (vintage.asset_classes[0],) * 3}
        )
    source = vintage.sources[0].model_copy(update={"asset_key": "unknown"})
    with pytest.raises(ValidationError, match="Source asset"):
        CMEVintage.model_validate({**vintage.model_dump(), "sources": (source,)})


def test_unknown_correlations_and_small_horizon_samples(vintage, panel):
    matrix = ((1.0, None, 0.1), (None, 1.0, 0.1), (0.1, 0.1, 1.0))
    unknown = vintage.model_copy(update={"correlation_matrix": matrix})
    report = calibrate(
        [unknown], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert report.correlation_rows[0]["status"] == "forecast_unavailable"
    assert report.matrix_rows[0]["frobenius_error"] is None
    sparse = replace(panel, returns=panel.returns.loc[["2020-01-01"]])
    report = calibrate(
        [vintage], sparse, evaluation_date="2020-12-31", config=small_config()
    )
    assert all(r["status"] == "insufficient_observations" for r in report.asset_rows)
    limited = replace(
        panel, coverage_start="2019-01-01", returns=panel.returns.loc["2019-01-01":]
    )
    report = calibrate(
        [make_vintage("2018-12-31")],
        limited,
        evaluation_date="2020-12-31",
        config=small_config(),
    )
    assert all(r["status"] == "outside_coverage" for r in report.asset_rows)


@pytest.mark.parametrize("bad_value", [float("inf"), -1.1])
def test_invalid_outcome_values_do_not_enter_metrics(vintage, panel, bad_value):
    panel.returns.loc["2020-01-01", "equity"] = bad_value
    report = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert report.asset_rows[0]["status"] == "invalid_returns"
    assert report.asset_rows[0]["return_error"] is None
    json.loads(report.to_json())


def test_missing_asset_and_total_loss_have_distinct_results(vintage, panel):
    missing = replace(panel, returns=panel.returns.drop(columns="gold"))
    result = calibrate(
        [vintage], missing, evaluation_date="2020-12-31", config=small_config()
    )
    assert result.asset_rows[-1]["status"] == "missing_asset"
    panel.returns.loc["2020-01-01", "equity"] = -1
    result = calibrate(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert result.asset_rows[0]["realized_return"] == -1


def test_panel_and_evaluation_date_validation(vintage, panel):
    for update in (
        {"returns": panel.returns.iloc[::-1]},
        {"source": ""},
        {"revision_policy": "unknown"},
        {"coverage_start": "2020-01-01"},
        {"coverage_end": "2010-01-01"},
    ):
        with pytest.raises(ValueError):
            replace(panel, **update)
    with pytest.raises(ValueError, match="numeric"):
        replace(panel, returns=panel.returns.astype(str))
    with pytest.raises(ValueError, match="calendar date"):
        calibrate([vintage], panel, evaluation_date="2020-12-31T12:00:00")


def test_rank_ties_are_explicit(vintage, panel):
    panel.returns[:] = 0
    result = evaluate_blending(
        [vintage], panel, evaluation_date="2020-12-31", config=small_config()
    )
    assert all(row["status"] == "constant_ranks" for row in result.rankings)
    assert all(row["rank_correlation"] is None for row in result.rankings)

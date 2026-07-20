"""
API tests for client risk-level constrained optimization (P11).

The optimizer runs for real on deterministic pseudo-returns — only the
market fetch (_fetch_returns) is monkeypatched. Profiles come from the
shared `client` fixture (isolated tmp-path SQLite via dependency override).
"""

import numpy as np
import pandas as pd
import pytest

from src.config import DEFAULT_ASSET_CLASSES
from src.portfolio.risk_constraints import (
    RISK_LEVEL_CAPS,
    build_group_constraints,
    caps_for_tolerance,
)
from tests.test_api_advisor import _parse_sse
from tests.test_api_profiles import sample_payload

ASSETS = ["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"]
EQUITY_NAMES = [DEFAULT_ASSET_CLASSES[k]["name"] for k in ("US_EQUITY", "INTL_EQUITY")]
GOLD_NAME = DEFAULT_ASSET_CLASSES["GOLD"]["name"]

# High-return / mid-vol equities: unconstrained max-sharpe loads them, so the
# conservative equity cap visibly binds.
EQUITY_TILTED_STATS = {
    "US_EQUITY": (0.0012, 0.010),
    "INTL_EQUITY": (0.0010, 0.011),
    "US_BOND": (0.0001, 0.004),
    "GOLD": (0.0003, 0.010),
}

# Lowest-vol equities: unconstrained min-vol loads them instead.
CALM_EQUITY_STATS = {
    "US_EQUITY": (0.0005, 0.003),
    "INTL_EQUITY": (0.0004, 0.0035),
    "US_BOND": (0.0003, 0.010),
    "GOLD": (0.0003, 0.012),
}


def _fake_returns(stats: dict, n: int = 504, seed: int = 7) -> pd.DataFrame:
    """Deterministic pseudo-returns with asset display names as columns."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            DEFAULT_ASSET_CLASSES[key]["name"]: rng.normal(mean, std, n)
            for key, (mean, std) in stats.items()
        }
    )


def _patch_returns(monkeypatch, returns: pd.DataFrame) -> None:
    monkeypatch.setattr(
        "api.routers.portfolio._fetch_returns", lambda keys, period: returns
    )


def _body(profile_id=None, **overrides) -> dict:
    body = {
        "assets": ASSETS,
        "period": "5y",
        "risk_free_rate": 0.0,  # avoids the dynamic rf fetch
        "method": "mvo",
        "mode": "max-sharpe",
    }
    if profile_id is not None:
        body["profile_id"] = profile_id
    body.update(overrides)
    return body


def _create_profile(client, **overrides) -> int:
    resp = client.post("/api/profiles", json=sample_payload(**overrides))
    assert resp.status_code == 201
    return resp.json()["id"]


def _equity_sum(weights: dict) -> float:
    return sum(weights[name] for name in EQUITY_NAMES)


# ---------------------------------------------------------------------------
# src/portfolio/risk_constraints.py units
# ---------------------------------------------------------------------------


def test_caps_for_tolerance_levels():
    assert caps_for_tolerance("Conservative / 保守型") == {"equity": 0.15, "alternative": 0.10}
    assert caps_for_tolerance("Moderately Conservative / 稳健型") == {"equity": 0.30, "alternative": 0.15}
    assert caps_for_tolerance("Moderate / 平衡型") == {"equity": 0.50, "alternative": 0.20}
    assert caps_for_tolerance("Moderately Aggressive / 成长型") == {"equity": 0.70, "alternative": 0.25}
    assert caps_for_tolerance("Aggressive / 进取型") == {"equity": 0.90, "alternative": 0.30}
    # The returned dict is a copy — mutating it must not poison the constant.
    caps_for_tolerance("Aggressive / 进取型")["equity"] = 9.9
    assert RISK_LEVEL_CAPS["进取型"]["equity"] == 0.90


def test_caps_for_tolerance_unknown_level():
    with pytest.raises(ValueError):
        caps_for_tolerance("")
    with pytest.raises(ValueError):
        caps_for_tolerance("Unknown / 未知等级")


def test_build_group_constraints_filters_to_selected():
    constraints = build_group_constraints(
        {"equity": 0.15, "alternative": 0.10},
        ["US_EQUITY", "US_BOND", "GOLD"],
    )
    assert constraints == {
        "equity": {
            "assets": ["US Equities (S&P 500)"],
            "min": 0.0,
            "max": 0.15,
        },
        "alternative": {"assets": ["Gold"], "min": 0.0, "max": 0.10},
    }
    # No capped group in the selection → no constraint at all.
    assert build_group_constraints({"equity": 0.15}, ["US_BOND", "CASH"]) == {}


# ---------------------------------------------------------------------------
# POST /api/portfolio/optimize with profile_id
# ---------------------------------------------------------------------------


def test_max_sharpe_respects_conservative_caps(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns(EQUITY_TILTED_STATS))
    # min(1.0, 1.0) = 1.0 → "Conservative / 保守型"
    pid = _create_profile(
        client, risk_scores={"ability_score": 1.0, "willingness_score": 1.0}
    )

    resp = client.post("/api/portfolio/optimize", json=_body(profile_id=pid))
    assert resp.status_code == 200
    body = resp.json()

    rc = body["risk_constraints"]
    assert rc["profile_id"] == pid
    assert rc["profile_name"] == "John Doe"
    assert rc["risk_level"] == "Conservative / 保守型"
    assert rc["caps"] == {"equity": 0.15, "alternative": 0.10}

    selected = body["selected"]["weights"]
    assert _equity_sum(selected) <= 0.15 + 1e-6
    assert selected[GOLD_NAME] <= 0.10 + 1e-6

    # The max_sharpe control portfolio stays unconstrained (cost reference).
    assert _equity_sum(body["max_sharpe"]["weights"]) > 0.15 + 1e-6


def test_min_vol_respects_conservative_caps(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns(CALM_EQUITY_STATS))
    pid = _create_profile(
        client, risk_scores={"ability_score": 1.0, "willingness_score": 1.0}
    )

    resp = client.post(
        "/api/portfolio/optimize", json=_body(profile_id=pid, mode="min-vol")
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["risk_constraints"]["risk_level"] == "Conservative / 保守型"
    assert _equity_sum(body["selected"]["weights"]) <= 0.15 + 1e-6
    # Control min-vol is unconstrained → mostly the calm equities here.
    assert _equity_sum(body["min_vol"]["weights"]) > 0.5


def test_no_profile_id_leaves_response_unconstrained(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns(EQUITY_TILTED_STATS))
    resp = client.post("/api/portfolio/optimize", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_constraints"] is None
    assert _equity_sum(body["selected"]["weights"]) > 0.15 + 1e-6


def test_missing_profile_404(client):
    resp = client.post("/api/portfolio/optimize", json=_body(profile_id=999))
    assert resp.status_code == 404
    assert "画像不存在" in resp.json()["detail"]


def test_unclassified_risk_level_422(client):
    # Zero scores → tolerance_level "" → caps cannot be resolved.
    pid = _create_profile(
        client, risk_scores={"ability_score": 0, "willingness_score": 0}
    )
    resp = client.post("/api/portfolio/optimize", json=_body(profile_id=pid))
    assert resp.status_code == 422


def test_non_mvo_methods_422(client):
    pid = _create_profile(client)

    resp = client.post(
        "/api/portfolio/optimize",
        json=_body(profile_id=pid, method="resampled", n_simulations=50),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "风险约束当前仅支持经典 MVO 方法"

    resp = client.post(
        "/api/portfolio/optimize",
        json=_body(profile_id=pid, method="black-litterman"),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "风险约束当前仅支持经典 MVO 方法"


# ---------------------------------------------------------------------------
# Async endpoint: fail-fast validation + resolved caps carried into the task
# ---------------------------------------------------------------------------


def test_async_validation_fail_fast(client):
    pid = _create_profile(client)

    resp = client.post("/api/portfolio/optimize/async", json=_body(profile_id=999))
    assert resp.status_code == 404

    resp = client.post(
        "/api/portfolio/optimize/async",
        json=_body(profile_id=pid, method="resampled", n_simulations=50),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "风险约束当前仅支持经典 MVO 方法"


def test_async_result_carries_risk_constraints(client, monkeypatch):
    _patch_returns(monkeypatch, _fake_returns(EQUITY_TILTED_STATS))
    # min(3.0, 3.0) = 3.0 → "Moderate / 平衡型" (equity cap 0.50)
    pid = _create_profile(
        client, risk_scores={"ability_score": 3.0, "willingness_score": 3.0}
    )

    created = client.post("/api/portfolio/optimize/async", json=_body(profile_id=pid))
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    events = _parse_sse(client.get(f"/api/portfolio/tasks/{task_id}/events").text)
    done = events[-1]
    assert done["type"] == "done"

    result = done["result"]
    rc = result["risk_constraints"]
    assert rc["profile_id"] == pid
    assert rc["risk_level"] == "Moderate / 平衡型"
    assert rc["caps"] == {"equity": 0.50, "alternative": 0.20}
    assert _equity_sum(result["selected"]["weights"]) <= 0.50 + 1e-6
    # Control stays unconstrained.
    assert _equity_sum(result["max_sharpe"]["weights"]) > 0.50 + 1e-6

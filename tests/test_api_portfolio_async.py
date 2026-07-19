"""
API tests for the async portfolio optimization tasks (Phase 5c).

The heavy halves (_prepare_optimize / _solve_optimize) are monkeypatched —
tests cover the task lifecycle and SSE event protocol, not the optimizer
itself (covered by src tests and the sync endpoint).
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from api.schemas import OptimizeResponse, PortfolioResult
from tests.test_api_advisor import _parse_sse


def _dummy_result(weight: float) -> OptimizeResponse:
    result = PortfolioResult(
        weights={"US Equity": weight, "US Bond": 1 - weight},
        ann_return=0.08,
        ann_volatility=0.15,
        sharpe=0.5,
        success=True,
    )
    return OptimizeResponse(
        as_of=datetime.now(timezone.utc),
        params={"method": "resampled", "n_simulations": 50},
        selected=result,
        max_sharpe=result,
        min_vol=result,
        frontier_chart={"data": []},
        allocation_chart={"data": []},
        asset_stats=[],
        bl=None,
    )


@pytest.fixture
def fake_optimize(monkeypatch):
    monkeypatch.setattr(
        "api.routers.portfolio._prepare_optimize",
        lambda req: (["US_EQUITY", "US_BOND"], pd.DataFrame(), 0.045),
    )
    monkeypatch.setattr(
        "api.routers.portfolio._solve_optimize",
        lambda req, keys, returns, rf: _dummy_result(0.6),
    )


def _async_body(**overrides) -> dict:
    body = {
        "assets": ["US_EQUITY", "US_BOND"],
        "period": "5y",
        "method": "resampled",
        "mode": "max-sharpe",
        "allow_short": False,
        "n_simulations": 50,
    }
    body.update(overrides)
    return body


def test_async_task_streams_progress_and_result(client, fake_optimize):
    created = client.post("/api/portfolio/optimize/async", json=_async_body())
    assert created.status_code == 202
    task_id = created.json()["task_id"]

    resp = client.get(f"/api/portfolio/tasks/{task_id}/events")
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    nodes = [e for e in events if e["type"] == "node"]
    assert [e["node"] for e in nodes] == ["fetch", "solve"]
    assert "重采样" in nodes[1]["label"]

    done = events[-1]
    assert done["type"] == "done"
    result = done["result"]
    assert result["selected"]["weights"] == {"US Equity": 0.6, "US Bond": 0.4}
    assert result["params"]["method"] == "resampled"
    # as_of survives model_dump(mode="json") as an ISO string
    assert isinstance(result["as_of"], str)


def test_async_eager_validation(client, fake_optimize):
    # Fewer than 2 valid assets → 422 synchronously, no task created.
    resp = client.post("/api/portfolio/optimize/async", json=_async_body(assets=["NOPE"]))
    assert resp.status_code == 422

    # BL without views → 422 synchronously.
    resp = client.post(
        "/api/portfolio/optimize/async",
        json=_async_body(method="black-litterman", bl=None),
    )
    assert resp.status_code == 422


def test_async_http_error_becomes_error_event(client, monkeypatch):
    from fastapi import HTTPException

    def boom(req):
        raise HTTPException(status_code=502, detail="No price data returned.")

    monkeypatch.setattr("api.routers.portfolio._prepare_optimize", boom)

    task_id = client.post("/api/portfolio/optimize/async", json=_async_body()).json()["task_id"]
    events = _parse_sse(client.get(f"/api/portfolio/tasks/{task_id}/events").text)

    assert events[-1]["type"] == "error"
    assert "No price data" in events[-1]["message"]


def test_async_unexpected_error_becomes_error_event(client, monkeypatch):
    monkeypatch.setattr(
        "api.routers.portfolio._prepare_optimize",
        lambda req: (_ for _ in ()).throw(RuntimeError("kaboom")),
    )

    task_id = client.post("/api/portfolio/optimize/async", json=_async_body()).json()["task_id"]
    events = _parse_sse(client.get(f"/api/portfolio/tasks/{task_id}/events").text)

    assert events[-1]["type"] == "error"
    assert "kaboom" in events[-1]["message"]


def test_async_task_not_found(client):
    assert client.get("/api/portfolio/tasks/nonexistent/events").status_code == 404

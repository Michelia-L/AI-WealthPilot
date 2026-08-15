"""
AI WealthPilot - Retirement API Tests (personal inflation presets)

POST /api/retirement/simulate with demographic/lifestyle inflation
segments: the distribution-phase rate resolves from inflation_preset
(src.portfolio.inflation) while the accumulation phase keeps the base
generic-CPI rate.
"""

import pytest


def _minimal_payload(**overrides) -> dict:
    """Smallest valid request body (fast: 1k simulations)."""
    payload = {
        "current_age": 30,
        "retirement_age": 60,
        "life_expectancy": 85,
        "current_savings": 100000,
        "annual_savings": 50000,
        "desired_annual_income": 80000,
        "inflation_rate": 0.025,
        "expected_return": 0.07,
        "volatility": 0.15,
        "n_simulations": 1000,
    }
    payload.update(overrides)
    return payload


class TestRetirementSimulateInflation:
    """Personal inflation preset handling on /api/retirement/simulate."""

    def test_default_single_rate_behavior(self, client):
        """No preset ⇒ legacy behavior: both phases use inflation_rate."""
        res = client.post("/api/retirement/simulate", json=_minimal_payload())
        assert res.status_code == 200
        params = res.json()["params"]
        assert params["inflation_preset"] is None
        assert params["inflation_rate"] == pytest.approx(0.025)
        assert params["distribution_inflation_rate"] == pytest.approx(0.025)

    def test_elderly_preset_raises_distribution_rate(self, client):
        """Elderly (CPI-E style) segment adds the configured delta."""
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(inflation_preset="elderly"),
        )
        assert res.status_code == 200
        params = res.json()["params"]
        assert params["inflation_rate"] == pytest.approx(0.025)
        assert params["distribution_inflation_rate"] == pytest.approx(0.0325)
        # Accumulation phase still uses the base rate.
        assert params["distribution_inflation_rate"] > params["inflation_rate"]

    def test_luxury_preset_raises_distribution_rate(self, client):
        """Luxury (CLEWI style) segment adds a larger delta."""
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(inflation_preset="luxury"),
        )
        assert res.status_code == 200
        params = res.json()["params"]
        assert params["distribution_inflation_rate"] == pytest.approx(0.049)

    def test_custom_preset_uses_absolute_rate(self, client):
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(
                inflation_preset="custom", custom_inflation_rate=0.04
            ),
        )
        assert res.status_code == 200
        params = res.json()["params"]
        assert params["distribution_inflation_rate"] == pytest.approx(0.04)

    def test_custom_preset_without_rate_is_422(self, client):
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(inflation_preset="custom"),
        )
        assert res.status_code == 422

    def test_unknown_preset_is_422(self, client):
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(inflation_preset="celebrity"),
        )
        assert res.status_code == 422


class TestRetirementGuardrails:
    """Guyton-Klinger guardrails withdrawal strategy."""

    def test_guardrails_comparison_block(self, client):
        """guardrails ⇒ comparison block with a same-draws fixed baseline."""
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(withdrawal_strategy="guardrails"),
        )
        assert res.status_code == 200
        data = res.json()
        comp = data["comparison"]
        assert comp is not None
        assert comp["guardrails_survival_rate"] == data["survival_rate"]
        assert comp["guardrail_band"] == pytest.approx(0.2)
        assert comp["guardrail_adjust"] == pytest.approx(0.1)
        assert comp["survival_lift"] == pytest.approx(
            comp["guardrails_survival_rate"] - comp["fixed_survival_rate"]
        )

        # The baseline must equal a pure fixed request (same seed, SEED=42).
        res_fixed = client.post(
            "/api/retirement/simulate", json=_minimal_payload()
        )
        assert res_fixed.status_code == 200
        assert comp["fixed_survival_rate"] == res_fixed.json()["survival_rate"]

    def test_fixed_strategy_has_no_comparison(self, client):
        res = client.post("/api/retirement/simulate", json=_minimal_payload())
        assert res.status_code == 200
        assert res.json()["comparison"] is None

    def test_guardrail_band_out_of_range_422(self, client):
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(
                withdrawal_strategy="guardrails", guardrail_band=0.9
            ),
        )
        assert res.status_code == 422

    def test_guardrail_adjust_out_of_range_422(self, client):
        res = client.post(
            "/api/retirement/simulate",
            json=_minimal_payload(
                withdrawal_strategy="guardrails", guardrail_adjust=0.001
            ),
        )
        assert res.status_code == 422


class TestCmeSuggestion:
    """GET /api/retirement/cme-suggestion."""

    @staticmethod
    def _report(n_classes: int = 2):
        from src.portfolio.cme_models import AssetClassCME, CMEReport

        classes = [
            AssetClassCME(
                name="固定收益", ticker="AGG", expected_return=0.04,
                volatility=0.06, sharpe_ratio=0.0, max_drawdown=-0.1,
                var_95=0.01, cvar_95=0.02, blended_volatility=0.06,
            ),
            AssetClassCME(
                name="另类-黄金", ticker="GLD", expected_return=0.10,
                volatility=0.15, sharpe_ratio=0.0, max_drawdown=-0.2,
                var_95=0.02, cvar_95=0.03, blended_volatility=0.15,
            ),
        ][:n_classes]
        return CMEReport(
            as_of_date="2026-08-15", data_lookback_years=5,
            risk_free_rate=0.02, inflation_assumption=0.025,
            asset_classes=classes, correlation_matrix={},
        )

    def test_happy_path(self, client, monkeypatch):
        report = self._report()
        monkeypatch.setattr(
            "api.routers.retirement.compute_cme", lambda: (report, "cached")
        )
        res = client.get("/api/retirement/cme-suggestion")
        assert res.status_code == 200
        data = res.json()
        assert data["cache_status"] == "cached"
        assert data["as_of_date"] == "2026-08-15"
        # Default allocation: bonds 0.30 / gold 0.10 → renormalized 0.75/0.25
        assert data["expected_return"] == pytest.approx(0.75 * 0.04 + 0.25 * 0.10)
        assert sum(data["allocation"].values()) == pytest.approx(1.0)

    def test_502_when_cme_fails(self, client, monkeypatch):
        def boom():
            raise RuntimeError("no cache, no fallback")

        monkeypatch.setattr("api.routers.retirement.compute_cme", boom)
        res = client.get("/api/retirement/cme-suggestion")
        assert res.status_code == 502

    def test_502_when_too_few_classes(self, client, monkeypatch):
        report = self._report(n_classes=1)
        monkeypatch.setattr(
            "api.routers.retirement.compute_cme", lambda: (report, "fresh")
        )
        res = client.get("/api/retirement/cme-suggestion")
        assert res.status_code == 502

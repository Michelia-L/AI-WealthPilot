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

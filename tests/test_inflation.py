"""
AI WealthPilot - Personal Inflation Model Tests

Tests the demographic/lifestyle-based inflation presets in
src/portfolio/inflation.py (CPI-E / CLEWI style segment adjustments).
"""

import pytest

from src.config import PERSONAL_INFLATION_DELTAS, PERSONAL_INFLATION_ELDERLY_MIN_AGE
from src.portfolio.inflation import (
    INFLATION_PRESETS,
    resolve_personal_inflation,
    suggest_inflation_preset,
)


class TestResolvePersonalInflation:
    """resolve_personal_inflation() preset resolution."""

    def test_none_preset_behaves_as_standard(self):
        """None keeps the legacy single-rate behavior."""
        assert resolve_personal_inflation(0.025, None) == pytest.approx(0.025)

    def test_standard_returns_base_rate(self):
        assert resolve_personal_inflation(0.03, "standard") == pytest.approx(0.03)

    def test_elderly_adds_configured_delta(self):
        expected = 0.025 + PERSONAL_INFLATION_DELTAS["elderly"]
        assert resolve_personal_inflation(0.025, "elderly") == pytest.approx(expected)

    def test_luxury_adds_configured_delta(self):
        expected = 0.02 + PERSONAL_INFLATION_DELTAS["luxury"]
        assert resolve_personal_inflation(0.02, "luxury") == pytest.approx(expected)

    def test_elderly_exceeds_standard(self):
        """CPI-E style baskets outpace generic CPI — the whole point."""
        base = 0.025
        elderly = resolve_personal_inflation(base, "elderly")
        standard = resolve_personal_inflation(base, "standard")
        assert elderly > standard

    def test_custom_returns_absolute_rate(self):
        assert resolve_personal_inflation(0.025, "custom", 0.04) == pytest.approx(0.04)

    def test_custom_without_rate_raises(self):
        with pytest.raises(ValueError, match="custom_rate"):
            resolve_personal_inflation(0.025, "custom")

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown inflation preset"):
            resolve_personal_inflation(0.025, "celebrity")

    def test_presets_cover_config_deltas_plus_custom(self):
        assert set(INFLATION_PRESETS) == set(PERSONAL_INFLATION_DELTAS) | {"custom"}


class TestSuggestInflationPreset:
    """suggest_inflation_preset() age-based defaulting."""

    def test_elderly_at_threshold(self):
        assert suggest_inflation_preset(PERSONAL_INFLATION_ELDERLY_MIN_AGE) == "elderly"

    def test_elderly_above_threshold(self):
        assert suggest_inflation_preset(PERSONAL_INFLATION_ELDERLY_MIN_AGE + 15) == "elderly"

    def test_standard_below_threshold(self):
        assert suggest_inflation_preset(PERSONAL_INFLATION_ELDERLY_MIN_AGE - 1) == "standard"

    def test_standard_for_unknown_age(self):
        assert suggest_inflation_preset(None) == "standard"

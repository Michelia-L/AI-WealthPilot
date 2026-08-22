"""
Golden-fixture invariant tests (P24) — the eval seed set for LLM IPS output.

The demo fixtures double as the golden reference for what a structurally
valid, quantitatively coherent IPS looks like. These assertions pin the
invariants that any real LLM-generated IPS must also satisfy, so a fixture
edit (or a future eval harness replay) that breaks quantitative coherence
fails loudly here rather than silently degrading downstream monitoring /
backtest consumers.
"""

import json

import pytest

from src.agents.demo_mode import FIXTURES_DIR
from src.agents.ips_models import IPSDocument
from src.config import CME_INFLATION_ASSUMPTION

# Canonical risk levels — the same set validate_saa_node's volatility bands
# are keyed on (ips_workflow.py); fixtures must use a recognized level.
CANONICAL_RISK_LEVELS = {
    "conservative",
    "moderately_conservative",
    "moderate",
    "moderately_aggressive",
    "aggressive",
}

# Required narrative sections that must be non-empty strings.
_REQUIRED_NARRATIVE_FIELDS = (
    "executive_summary",
    "client_background",
    "risk_disclosure",
    "compliance_statement",
)

_REQUIRED_SECTION_MODELS = (
    "return_objective",
    "risk_tolerance",
    "time_horizon",
    "liquidity",
    "tax",
    "legal",
    "unique_circumstances",
    "investment_guidelines",
    "monitoring",
)


def _load_ips(locale: str) -> dict:
    filename = "ips_document_en.json" if locale == "en" else "ips_document.json"
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))["ips"]


@pytest.fixture(params=["zh", "en"], ids=["zh", "en"])
def golden_ips(request) -> dict:
    """The raw ``ips`` dict of each locale's fixture, parametrized."""
    return _load_ips(request.param)


def test_fixture_parses_as_ips_document(golden_ips):
    """Schema round-trip: the golden fixture must satisfy the IPS schema."""
    doc = IPSDocument(**golden_ips)
    assert doc.client_name.strip()


def test_saa_target_weights_sum_to_one(golden_ips):
    saa = golden_ips["investment_guidelines"]["strategic_allocation"]
    total = sum(row["target_weight"] for row in saa)
    assert total == pytest.approx(1.0, abs=1e-6)


def test_saa_weight_ranges_are_ordered(golden_ips):
    """Explicit documentation of the min <= target <= max invariant.

    The schema validator already enforces this; asserting it here keeps the
    invariant visible as a golden-output contract, not just a parse rule.
    """
    saa = golden_ips["investment_guidelines"]["strategic_allocation"]
    for row in saa:
        assert row["min_weight"] <= row["target_weight"] <= row["max_weight"], (
            f"{row['asset_class']}: {row['min_weight']} <= "
            f"{row['target_weight']} <= {row['max_weight']} violated"
        )


def test_real_nominal_return_identity(golden_ips):
    """required_real must equal (1 + nominal) / (1 + inflation) - 1.

    Uses the shared CME inflation assumption the fixtures are written
    against; a 0.1pp tolerance absorbs rounding in the fixture narrative.
    """
    ro = golden_ips["return_objective"]
    expected_real = (1 + ro["required_nominal_return"]) / (
        1 + CME_INFLATION_ASSUMPTION
    ) - 1
    assert ro["required_real_return"] == pytest.approx(expected_real, abs=1e-3)


def test_required_narratives_non_empty(golden_ips):
    for field in _REQUIRED_NARRATIVE_FIELDS:
        assert golden_ips[field].strip(), f"{field} must be non-empty"
    for section in _REQUIRED_SECTION_MODELS:
        assert golden_ips[section], f"{section} section must be present"


def test_benchmarks_cover_every_saa_asset_class(golden_ips):
    saa_names = {
        row["asset_class"]
        for row in golden_ips["investment_guidelines"]["strategic_allocation"]
    }
    benchmark_names = {b["asset_class"] for b in golden_ips["monitoring"]["benchmarks"]}
    assert saa_names <= benchmark_names


def test_risk_level_is_canonical(golden_ips):
    risk_level = golden_ips["risk_tolerance"]["overall_risk_level"]
    assert risk_level in CANONICAL_RISK_LEVELS

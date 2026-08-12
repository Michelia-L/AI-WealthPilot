"""
Personal (demographic & lifestyle-based) inflation model.

Generic CPI understates — or overstates — the inflation actually
experienced by key private-banking client segments (CFA curriculum:
demographic & income-based inflation):

- Elderly clients (62+): a CPI-E-style spending basket. The BLS
  experimental CPI-E roughly doubles the healthcare weight vs CPI-W
  (5.6% → 11%) and has consistently outpaced generic CPI over the past
  four decades, driven by above-average medical-cost inflation.
- Luxury-lifestyle clients: Forbes' Cost of Living Extremely Well Index
  (CLEWI) has exceeded generic CPI by roughly 2.4pp/yr over the long
  run — maintaining an "old money" lifestyle costs ever more.

Both CPI-E and CLEWI are US series with no official Chinese equivalent,
so presets are implemented as stylized additive deltas over the client's
base (generic-CPI) inflation assumption, configured in ``src.config`` —
transparent and auditable rather than a live data pipeline.
"""

from typing import Optional

from src.config import (
    PERSONAL_INFLATION_DELTAS,
    PERSONAL_INFLATION_ELDERLY_MIN_AGE,
)

#: Presets resolved as base rate + delta; "custom" takes an absolute rate.
INFLATION_PRESETS = tuple(PERSONAL_INFLATION_DELTAS) + ("custom",)


def resolve_personal_inflation(
    base_rate: float,
    preset: Optional[str] = None,
    custom_rate: Optional[float] = None,
) -> float:
    """Resolve a personal inflation rate for a client segment.

    Args:
        base_rate: Base (generic-CPI) annual inflation assumption.
        preset: Client segment — "standard", "elderly", "luxury", or
            "custom". None behaves as "standard".
        custom_rate: Absolute inflation rate, required iff preset is
            "custom".

    Returns:
        The effective annual inflation rate for the segment.

    Raises:
        ValueError: On an unknown preset, or "custom" without a rate.
    """
    if preset is None:
        preset = "standard"
    if preset == "custom":
        if custom_rate is None:
            raise ValueError("custom_rate is required when preset is 'custom'")
        return custom_rate
    if preset not in PERSONAL_INFLATION_DELTAS:
        raise ValueError(
            f"Unknown inflation preset {preset!r}; "
            f"expected one of {INFLATION_PRESETS}"
        )
    return base_rate + PERSONAL_INFLATION_DELTAS[preset]


def suggest_inflation_preset(age: Optional[int]) -> str:
    """Suggest an inflation preset from client age.

    Clients at/past the elderly threshold (60, configurable) spend out of
    a healthcare-tilted basket, so the CPI-E-style "elderly" preset is the
    better default; everyone else starts from "standard".
    """
    if age is not None and age >= PERSONAL_INFLATION_ELDERLY_MIN_AGE:
        return "elderly"
    return "standard"

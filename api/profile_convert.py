"""
Shared ClientProfile conversion helpers.

The stored JSON column keeps the ``dataclasses.asdict(ClientProfile)``
shape; these helpers convert between the API payload, that stored dict,
and the src/ dataclass (whose properties provide the derived metrics).
Used by the profiles, advisor, and IPS routers.
"""

import math
from datetime import datetime
from typing import Any, Optional

from api.schemas import ProfileDerived, ProfilePayload
from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
)


def tolerance_level(ability: float, willingness: float) -> str:
    """Classify via src/ rules; empty string when not yet assessed."""
    rp = RiskProfile(ability_score=ability, willingness_score=willingness)
    if rp.final_score == 0.0:
        return ""
    return rp.classify()


def payload_to_data(payload: ProfilePayload, created_at: str) -> dict[str, Any]:
    """Serialize the editable payload to the asdict(ClientProfile) shape."""
    now = datetime.now().isoformat()
    ability = payload.risk_scores.ability_score
    willingness = payload.risk_scores.willingness_score
    return {
        "name": payload.name,
        "age": payload.age,
        "marital_status": payload.marital_status,
        "dependents": payload.dependents,
        "financial": payload.financial.model_dump(),
        "goals": [g.model_dump() for g in payload.goals],
        "time_horizon_years": payload.time_horizon_years,
        "is_multi_stage": payload.is_multi_stage,
        "liquidity_needs": payload.liquidity_needs,
        "tax_status": payload.tax_status,
        "esg_preference": payload.esg_preference,
        "sector_restrictions": payload.sector_restrictions,
        "notes": payload.notes,
        "risk_profile": {
            "ability_score": ability,
            "willingness_score": willingness,
            "tolerance_level": tolerance_level(ability, willingness),
            "description": "",
        },
        "ability_answers": payload.ability_answers,
        "willingness_answers": payload.willingness_answers,
        "created_at": created_at,
        "updated_at": now,
    }


def profile_from_data(data: dict[str, Any]) -> ClientProfile:
    """Rebuild the src/ dataclass from its asdict shape (mirror of load_profile)."""
    d = dict(data)
    financial = FinancialSituation(**d.pop("financial", {}))
    risk = RiskProfile(**d.pop("risk_profile", {}))
    goals = [InvestmentGoal(**g) for g in d.pop("goals", [])]
    return ClientProfile(financial=financial, risk_profile=risk, goals=goals, **d)


def _safe_ratio(value: float) -> Optional[float]:
    """JSON can't carry inf/nan; None marks the infinite debt-ratio sentinel."""
    return value if math.isfinite(value) else None


def build_derived(profile: ClientProfile) -> ProfileDerived:
    """Derived metrics straight from src/ dataclass properties."""
    fin = profile.financial
    rp = profile.risk_profile
    return ProfileDerived(
        net_worth=fin.net_worth,
        annual_savings=fin.annual_income - fin.annual_expenses,
        savings_rate=fin.savings_rate,
        debt_to_asset_ratio=_safe_ratio(fin.debt_to_asset_ratio),
        final_risk_score=rp.final_score,
        tolerance_level=rp.tolerance_level,
    )

"""
Client profile CRUD — SQLite persistence (Phase 3c).

The full profile lives in a JSON column shaped exactly like
``dataclasses.asdict(ClientProfile)`` so legacy tooling and future phases
(IPS generation, advisor) can consume it unchanged. Index columns and the
``derived`` response block are computed from src/ dataclass properties —
no business logic is reimplemented here.
"""

import math
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.db import ProfileRecord, get_session
from api.migrate_profiles import import_json_profiles
from api.schemas import (
    ProfileDerived,
    ProfileDetailResponse,
    ProfileImportResponse,
    ProfileListResponse,
    ProfilePayload,
    ProfileSummary,
)
from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


# ---------------------------------------------------------------------------
# Conversion helpers (payload ↔ stored dict ↔ src dataclass)
# ---------------------------------------------------------------------------


def _tolerance_level(ability: float, willingness: float) -> str:
    """Classify via src/ rules; empty string when not yet assessed."""
    rp = RiskProfile(ability_score=ability, willingness_score=willingness)
    if rp.final_score == 0.0:
        return ""
    return rp.classify()


def _payload_to_data(payload: ProfilePayload, created_at: str) -> dict[str, Any]:
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
            "tolerance_level": _tolerance_level(ability, willingness),
            "description": "",
        },
        "ability_answers": payload.ability_answers,
        "willingness_answers": payload.willingness_answers,
        "created_at": created_at,
        "updated_at": now,
    }


def _profile_from_data(data: dict[str, Any]) -> ClientProfile:
    """Rebuild the src/ dataclass from its asdict shape (mirror of load_profile)."""
    d = dict(data)
    financial = FinancialSituation(**d.pop("financial", {}))
    risk = RiskProfile(**d.pop("risk_profile", {}))
    goals = [InvestmentGoal(**g) for g in d.pop("goals", [])]
    return ClientProfile(financial=financial, risk_profile=risk, goals=goals, **d)


def _safe_ratio(value: float) -> Optional[float]:
    """JSON can't carry inf/nan; None marks the infinite debt-ratio sentinel."""
    return value if math.isfinite(value) else None


def _derived(profile: ClientProfile) -> ProfileDerived:
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


def _detail(record: ProfileRecord) -> ProfileDetailResponse:
    profile = _profile_from_data(record.data)
    return ProfileDetailResponse(
        id=record.id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        profile=record.data,
        derived=_derived(profile),
    )


def _get_or_404(profile_id: int, session: Session) -> ProfileRecord:
    record = session.get(ProfileRecord, profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"画像不存在（id={profile_id}）")
    return record


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ProfileListResponse)
def list_profiles(session: Session = Depends(get_session)) -> ProfileListResponse:
    records = session.exec(
        select(ProfileRecord).order_by(ProfileRecord.updated_at.desc())
    ).all()
    return ProfileListResponse(
        profiles=[
            ProfileSummary(
                id=r.id,
                name=r.name,
                age=r.age,
                risk_level=r.risk_level,
                updated_at=r.updated_at,
            )
            for r in records
        ]
    )


@router.post("", response_model=ProfileDetailResponse, status_code=201)
def create_profile(
    payload: ProfilePayload, session: Session = Depends(get_session)
) -> ProfileDetailResponse:
    data = _payload_to_data(payload, created_at=datetime.now().isoformat())
    record = ProfileRecord(
        name=payload.name,
        age=payload.age,
        risk_level=data["risk_profile"]["tolerance_level"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        data=data,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return _detail(record)


@router.get("/{profile_id}", response_model=ProfileDetailResponse)
def get_profile(
    profile_id: int, session: Session = Depends(get_session)
) -> ProfileDetailResponse:
    return _detail(_get_or_404(profile_id, session))


@router.put("/{profile_id}", response_model=ProfileDetailResponse)
def update_profile(
    profile_id: int,
    payload: ProfilePayload,
    session: Session = Depends(get_session),
) -> ProfileDetailResponse:
    record = _get_or_404(profile_id, session)
    data = _payload_to_data(payload, created_at=record.created_at)
    record.name = payload.name
    record.age = payload.age
    record.risk_level = data["risk_profile"]["tolerance_level"]
    record.updated_at = data["updated_at"]
    record.data = data
    session.add(record)
    session.commit()
    session.refresh(record)
    return _detail(record)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(_get_or_404(profile_id, session))
    session.commit()


@router.post("/import", response_model=ProfileImportResponse)
def import_legacy_json(session: Session = Depends(get_session)) -> ProfileImportResponse:
    """Import data/profiles/*.json (Streamlit era) into SQLite. Idempotent."""
    return ProfileImportResponse(**import_json_profiles(session))

"""
Client profile CRUD — SQLite persistence (Phase 3c).

The full profile lives in a JSON column shaped exactly like
``dataclasses.asdict(ClientProfile)`` so legacy tooling and future phases
(IPS generation, advisor) can consume it unchanged. Index columns and the
``derived`` response block are computed from src/ dataclass properties —
no business logic is reimplemented here.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from api.db import ProfileRecord, get_session
from api.migrate_profiles import import_json_profiles
from api.profile_convert import build_derived, payload_to_data, profile_from_data
from api.schemas import (
    ProfileDetailResponse,
    ProfileImportResponse,
    ProfileListResponse,
    ProfilePayload,
    ProfileSummary,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _detail(record: ProfileRecord) -> ProfileDetailResponse:
    profile = profile_from_data(record.data)
    return ProfileDetailResponse(
        id=record.id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        profile=record.data,
        derived=build_derived(profile),
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
    data = payload_to_data(payload, created_at=datetime.now().isoformat())
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
    data = payload_to_data(payload, created_at=record.created_at)
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

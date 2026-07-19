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
    BiasItem,
    ProfileCompareEntry,
    ProfileCompareResponse,
    ProfileDetailResponse,
    ProfileImportResponse,
    ProfileListResponse,
    ProfilePayload,
    ProfileSummary,
    QuestionnaireOption,
    QuestionnaireQuestion,
    QuestionnaireResponse,
)
from src.agents.profiler import (
    RISK_ABILITY_QUESTIONS,
    RISK_WILLINGNESS_QUESTIONS,
    compare_profiles,
    identify_behavioral_biases,
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


def _build_track(questions: dict) -> list[QuestionnaireQuestion]:
    """Flatten one src/ question dict into response models (order preserved)."""
    return [
        QuestionnaireQuestion(
            key=q_key,
            question=q_data["question"],
            options=[
                QuestionnaireOption(key=o_key, label=o["label"], score=o["score"])
                for o_key, o in q_data["options"].items()
            ],
        )
        for q_key, q_data in questions.items()
    ]


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


# NOTE: declared before /{profile_id} — FastAPI matches routes in order, so
# the literal "questionnaire" segment must win over the int parameter.
@router.get("/questionnaire", response_model=QuestionnaireResponse)
def get_questionnaire() -> QuestionnaireResponse:
    """9-question dual-track risk questionnaire straight from src/ profiler.

    Option scores are included so the client can show a live preview; the
    server recomputes authoritative scores from the submitted answers on save.
    """
    return QuestionnaireResponse(
        ability=_build_track(RISK_ABILITY_QUESTIONS),
        willingness=_build_track(RISK_WILLINGNESS_QUESTIONS),
    )


MAX_COMPARE_PROFILES = 6


# NOTE: declared before /{profile_id} for the same routing-order reason as
# /questionnaire above.
@router.get("/compare", response_model=ProfileCompareResponse)
def compare_profile_set(
    ids: str, session: Session = Depends(get_session)
) -> ProfileCompareResponse:
    """Compare 2–6 profiles (src compare_profiles) with per-profile biases.

    src keys its comparison dicts by client name, so duplicate names would
    silently overwrite each other — reject them with 422 instead.
    """
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="ids 必须为逗号分隔的整数")
    id_list = list(dict.fromkeys(id_list))  # dedupe, preserve order
    if len(id_list) < 2:
        raise HTTPException(status_code=422, detail="至少需要 2 个画像才能进行对比")
    if len(id_list) > MAX_COMPARE_PROFILES:
        raise HTTPException(
            status_code=422, detail=f"一次最多对比 {MAX_COMPARE_PROFILES} 个画像"
        )

    records = [session.get(ProfileRecord, i) for i in id_list]
    missing = [i for i, r in zip(id_list, records) if r is None]
    if missing:
        raise HTTPException(status_code=404, detail=f"画像不存在（id={missing}）")
    # Past the 404 guard every record exists.
    profiles = [profile_from_data(r.data) for r in records if r is not None]
    names = [p.name for p in profiles]
    if len(set(names)) != len(names):
        raise HTTPException(
            status_code=422, detail="所选画像存在重名，对比结果会互相覆盖；请改名后再试"
        )

    comparison = compare_profiles(profiles)
    return ProfileCompareResponse(
        comparison_date=comparison.comparison_date,
        insights=comparison.insights,
        profiles=[
            ProfileCompareEntry(
                id=record.id,
                name=profile.name,
                financial_summary=comparison.financial_summary[profile.name],
                bias_count=comparison.bias_count_comparison[profile.name],
                biases=[
                    BiasItem(**vars(b)) for b in identify_behavioral_biases(profile)
                ],
            )
            for record, profile in zip(records, profiles)
            if record is not None
        ],
    )

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

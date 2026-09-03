"""
Import legacy JSON profiles (data/profiles/*.json, Streamlit era) into SQLite.

Used by the POST /api/profiles/import endpoint and runnable directly:
    python -m api.migrate_profiles

Idempotent: a file whose (name, created_at) already exists in the database
is skipped, so re-running never duplicates rows.
"""

import json
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError
from sqlmodel import Session, select

from api.db import ProfileRecord, make_engine
from api.profile_convert import payload_to_data
from api.schemas import ProfilePayload, ProfileUploadFile, RiskScoresInput
from src.agents import profiler  # module attr so conftest monkeypatching works


def _record_from_file(filepath: Path) -> ProfileRecord | None:
    """Build a ProfileRecord from one legacy JSON file, or None if unreadable."""
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        name = str(data.get("name") or "").strip()
        if not name:
            return None
        created = str(data.get("created_at") or "")
        updated = str(data.get("updated_at") or "") or created
        risk_level = str(data.get("risk_profile", {}).get("tolerance_level") or "")
        return ProfileRecord(
            name=name,
            age=int(data.get("age") or 0),
            risk_level=risk_level,
            created_at=created,
            updated_at=updated,
            data=data,
        )
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def import_json_profiles(session: Session, profiles_dir: Path | None = None) -> dict:
    """Import every not-yet-imported JSON profile into the session's DB."""
    directory = profiles_dir or profiler.PROFILES_DIR
    files = sorted(directory.glob("*.json")) if directory.exists() else []

    existing = set(
        session.exec(select(ProfileRecord.name, ProfileRecord.created_at)).all()
    )

    imported = skipped = 0
    for filepath in files:
        record = _record_from_file(filepath)
        if record is None or (record.name, record.created_at) in existing:
            skipped += 1
            continue
        session.add(record)
        existing.add((record.name, record.created_at))
        imported += 1
    session.commit()

    return {"files_found": len(files), "imported": imported, "skipped": skipped}


def _payload_from_stored(data: dict) -> ProfilePayload:
    """Map a stored-asdict(ClientProfile) dict onto the editable payload so
    upload validation reuses the form's schema. Score fields feed the manual
    fallback; non-empty questionnaire answers take precedence on save."""
    risk = data.get("risk_profile") or {}
    return ProfilePayload(
        name=data.get("name"),
        age=data.get("age"),
        marital_status=data.get("marital_status", "single"),
        dependents=data.get("dependents", 0),
        financial=data.get("financial") or {},
        goals=data.get("goals") or [],
        time_horizon_years=data.get("time_horizon_years", 10),
        is_multi_stage=data.get("is_multi_stage", False),
        liquidity_needs=data.get("liquidity_needs", 0.0),
        tax_status=data.get("tax_status", "taxable"),
        esg_preference=data.get("esg_preference", False),
        sector_restrictions=data.get("sector_restrictions") or [],
        notes=data.get("notes", ""),
        risk_scores=RiskScoresInput(
            ability_score=risk.get("ability_score") or 0.0,
            willingness_score=risk.get("willingness_score") or 0.0,
        ),
        ability_answers=data.get("ability_answers") or {},
        willingness_answers=data.get("willingness_answers") or {},
    )


def import_uploaded_profiles(session: Session, files: list[ProfileUploadFile]) -> dict:
    """Import browser-uploaded JSON profiles. Each file holds one profile
    object or an array of them. Idempotent: entries with created_at dedupe on
    (name, created_at) like import_json_profiles; entries without created_at
    (typical LLM output) dedupe on name alone. Invalid files/entries are
    reported, not raised."""
    existing = set(
        session.exec(select(ProfileRecord.name, ProfileRecord.created_at)).all()
    )
    existing_names = {name for name, _ in existing}

    imported = skipped = 0
    invalid: list[str] = []
    for file in files:
        try:
            parsed = json.loads(file.content)
        except json.JSONDecodeError:
            invalid.append(file.filename)
            continue
        entries = parsed if isinstance(parsed, list) else [parsed]
        for idx, entry in enumerate(entries):
            label = (
                f"{file.filename}[{idx}]" if isinstance(parsed, list) else file.filename
            )
            if not isinstance(entry, dict):
                invalid.append(label)
                continue
            try:
                payload = _payload_from_stored(entry)
            except ValidationError:
                invalid.append(label)
                continue
            created_at = str(entry.get("created_at") or "")
            # Files without created_at (typical LLM output) dedupe on name
            # alone, so re-uploading the same file stays idempotent.
            key = (payload.name, created_at) if created_at else None
            if (key is not None and key in existing) or (
                key is None and payload.name in existing_names
            ):
                skipped += 1
                continue
            data = payload_to_data(payload, created_at=created_at)
            if not data["created_at"]:
                data["created_at"] = datetime.now().isoformat()
            existing.add((data["name"], data["created_at"]))
            existing_names.add(data["name"])
            session.add(
                ProfileRecord(
                    name=data["name"],
                    age=data["age"],
                    risk_level=data["risk_profile"]["tolerance_level"],
                    created_at=data["created_at"],
                    updated_at=data["updated_at"],
                    data=data,
                )
            )
            imported += 1
    session.commit()

    return {
        "files_found": len(files),
        "imported": imported,
        "skipped": skipped,
        "invalid": invalid,
    }


def maybe_auto_import() -> None:
    """First-boot convenience: if the profiles table is empty, import legacy
    JSON files (no-op when there is nothing to import). Idempotent."""
    from api.db import engine, init_db

    init_db()
    with Session(engine) as session:
        if session.exec(select(ProfileRecord.id).limit(1)).first() is not None:
            return  # DB already has profiles — leave it untouched
        result = import_json_profiles(session)
    if result["imported"]:
        print(f"Auto-imported {result['imported']} legacy JSON profile(s).")


def main() -> None:
    from api.db import init_db

    init_db()
    engine = make_engine()
    with Session(engine) as session:
        result = import_json_profiles(session)
    print(
        f"Found {result['files_found']} JSON files: "
        f"{result['imported']} imported, {result['skipped']} skipped."
    )


if __name__ == "__main__":
    main()

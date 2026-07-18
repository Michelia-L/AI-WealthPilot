"""
Import legacy JSON profiles (data/profiles/*.json, Streamlit era) into SQLite.

Used by the POST /api/profiles/import endpoint and runnable directly:
    python -m api.migrate_profiles

Idempotent: a file whose (name, created_at) already exists in the database
is skipped, so re-running never duplicates rows.
"""

import json
from pathlib import Path

from sqlmodel import Session, select

from api.db import ProfileRecord, make_engine
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

    existing = set(session.exec(select(ProfileRecord.name, ProfileRecord.created_at)).all())

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

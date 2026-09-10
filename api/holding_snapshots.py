"""SQLite access for append-only IPS holdings; valuation rules live in src/."""

from sqlmodel import Session, select

from api.db import HoldingSnapshotRecord
from src.portfolio.actual_holdings import compare_snapshots


def serialize(record: HoldingSnapshotRecord) -> dict:
    return {
        **record.data,
        "id": record.id,
        "document_id": record.document_id,
        "as_of": record.as_of,
        "created_at": record.created_at,
    }


def latest_snapshots(session: Session) -> dict[str, dict]:
    records = session.exec(
        select(HoldingSnapshotRecord).order_by(
            HoldingSnapshotRecord.as_of.desc(), HoldingSnapshotRecord.id.desc()
        )
    ).all()
    latest = {}
    for record in records:
        latest.setdefault(record.document_id, serialize(record))
    return latest


def latest_snapshot(session: Session, document_id: str) -> dict | None:
    record = session.exec(
        select(HoldingSnapshotRecord)
        .where(HoldingSnapshotRecord.document_id == document_id)
        .order_by(HoldingSnapshotRecord.as_of.desc(), HoldingSnapshotRecord.id.desc())
        .limit(1)
    ).first()
    return serialize(record) if record else None


def snapshot_history(session: Session, document_id: str) -> list[dict]:
    records = session.exec(
        select(HoldingSnapshotRecord)
        .where(HoldingSnapshotRecord.document_id == document_id)
        .order_by(HoldingSnapshotRecord.as_of, HoldingSnapshotRecord.id)
    ).all()
    snapshots = [serialize(r) for r in records]
    return [
        compare_snapshots(s, snapshots[i - 1] if i else None)
        for i, s in reversed(list(enumerate(snapshots)))
    ]

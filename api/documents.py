"""Versioned publication persistence. Callers authorize scope and own transactions.

A draft contains only the client-facing projection. The original generated IPS
and its machine review remain separate staff artifacts, not approval evidence.
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.db import ArtifactRecord, DocumentRecord
from api.i18n import msg
from api.schemas import ClientDocumentContent, DocumentResponse

VISIBLE_STATUSES = ("published", "acknowledged")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def conflict(locale: str) -> HTTPException:
    return HTTPException(409, msg("documents.conflict", locale))


def document_response(record: DocumentRecord) -> DocumentResponse:
    return DocumentResponse.model_validate(record, from_attributes=True)


def create_draft(
    session: Session,
    *,
    organization_id: str,
    client_id: str,
    created_by: str,
    type: str,
    content: ClientDocumentContent,
    source_artifact_id: str | None = None,
    document_id: str | None = None,
    version: int = 1,
) -> DocumentRecord:
    record = DocumentRecord(
        organization_id=organization_id,
        client_id=client_id,
        created_by=created_by,
        type=type,
        content=content.model_dump(),
        source_artifact_id=source_artifact_id,
        version=version,
        created_at=now(),
        **({"document_id": document_id} if document_id else {}),
    )
    session.add(record)
    session.flush()
    return record


def ips_content(ips: dict, locale: str = "en") -> ClientDocumentContent:
    """Allowlist narrative sections; never copy metadata, audit or tuning values."""
    guidelines = ips.get("investment_guidelines") or {}
    sections = []
    for key, field in (
        ("return_objective", "return_objective_narrative"),
        ("time_horizon", "horizon_narrative"),
        ("liquidity", "liquidity_narrative"),
        ("tax", "tax_narrative"),
        ("legal", "legal_narrative"),
        ("unique_circumstances", "unique_narrative"),
        ("monitoring", "monitoring_narrative"),
        ("fee_schedule", "fee_narrative"),
        ("currency_policy", "currency_narrative"),
    ):
        text = (ips.get(key) or {}).get(field)
        if text:
            sections.append({"heading": msg(f"documents.{key}", locale), "text": text})
    return ClientDocumentContent(
        title=msg("documents.ips_title", locale),
        summary=ips.get("executive_summary", ""),
        recommendation=guidelines.get("guideline_narrative", ""),
        risk_explanation=(ips.get("risk_tolerance") or {}).get("risk_narrative", ""),
        risk_disclosure=ips.get("risk_disclosure", ""),
        allocation=[
            {"asset_class": item["asset_class"], "weight": item["target_weight"]}
            for item in guidelines.get("strategic_allocation", [])
        ],
        sections=sections,
    )


def draft_from_ips(
    session: Session,
    owner: ArtifactRecord,
    ips: dict,
    created_by: str,
    locale: str = "en",
) -> DocumentRecord:
    content = ips_content(ips, locale)
    previous = session.exec(
        select(DocumentRecord)
        .where(
            DocumentRecord.organization_id == owner.organization_id,
            DocumentRecord.client_id == owner.client_id,
            DocumentRecord.type == "ips",
            DocumentRecord.source_artifact_id == owner.resource_id,
        )
        .order_by(DocumentRecord.version.desc(), DocumentRecord.id)
        .limit(1)
    ).first()
    if previous is not None:
        return revise(session, previous, created_by, content, locale)
    try:
        return create_draft(
            session,
            organization_id=owner.organization_id,
            client_id=owner.client_id,
            created_by=created_by,
            type="ips",
            content=content,
            source_artifact_id=owner.resource_id,
        )
    except IntegrityError:
        session.rollback()
        # Another request may have created version 1 for this source after
        # the lookup. The source/version unique constraint prevents a split
        # logical document chain; callers can retry against the winning series.
        raise conflict(locale) from None


def validate_publishable(record: DocumentRecord, locale: str) -> None:
    """Enforce type-specific completeness at the publication boundary."""
    content = ClientDocumentContent.model_validate(record.content)
    if record.type == "ips" and not content.allocation:
        raise HTTPException(422, msg("documents.ips_allocation_required", locale))


def revise(
    session: Session,
    record: DocumentRecord,
    created_by: str,
    content: ClientDocumentContent | None,
    locale: str,
) -> DocumentRecord:
    version = session.exec(
        select(func.max(DocumentRecord.version)).where(
            DocumentRecord.document_id == record.document_id
        )
    ).one()
    try:
        return create_draft(
            session,
            organization_id=record.organization_id,
            client_id=record.client_id,
            created_by=created_by,
            type=record.type,
            content=content or ClientDocumentContent.model_validate(record.content),
            source_artifact_id=record.source_artifact_id,
            document_id=record.document_id,
            version=version + 1,
        )
    except IntegrityError:
        session.rollback()
        # Concurrent revisions cannot silently replace or reuse a version.
        raise conflict(locale) from None


def change(
    session: Session,
    record: DocumentRecord,
    expected_status: str,
    locale: str,
    **values,
) -> DocumentRecord:
    """Compare-and-set keeps editing, approval and publication races safe."""
    result = session.execute(
        update(DocumentRecord)
        .where(DocumentRecord.id == record.id, DocumentRecord.status == expected_status)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise conflict(locale)
    session.refresh(record)
    return record

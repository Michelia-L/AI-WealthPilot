"""API persistence boundary for client-owned file artifacts.

Only the SQL index grants API visibility. File names and JSON profile IDs never
confer ownership. Domain/standalone file writers remain usable without an API DB.
"""

from pathlib import Path

from pydantic import ValidationError
from sqlmodel import Session

from api import db
from api.i18n import msg
from src.agents import ips_storage, report_storage
from src.agents.ips_models import IPSDocument


def artifact_path(record: db.ArtifactRecord) -> Path:
    if record.kind not in ("ips", "report"):
        raise ValueError("Invalid artifact kind")
    if record.kind == "ips" and record.filename != f"{record.resource_id}.json":
        raise ValueError("IPS filename must match its ID")
    directory = (
        ips_storage.IPS_DIR if record.kind == "ips" else report_storage.REPORTS_DIR
    )
    if Path(record.filename).name != record.filename or not record.filename.endswith(
        ".json"
    ):
        raise ValueError("Invalid artifact filename")
    path = directory / record.filename
    if path.is_symlink():
        raise ValueError("Artifact symlinks are not supported")
    return path


def register_artifact(
    session: Session,
    *,
    kind: str,
    resource_id: str,
    filename: str,
    organization_id: str,
    client_id: str,
    created_by: str | None = None,
) -> db.ArtifactRecord:
    client = session.get(db.ClientRecord, client_id)
    if client is None or client.organization_id != organization_id:
        raise ValueError("Invalid artifact owner")
    if created_by is not None and session.get(db.UserRecord, created_by) is None:
        raise ValueError("Invalid artifact creator")
    record = db.ArtifactRecord(
        kind=kind,
        resource_id=resource_id,
        filename=filename,
        organization_id=organization_id,
        client_id=client_id,
        created_by=created_by,
    )
    artifact_path(record)
    old = session.get(db.ArtifactRecord, (kind, resource_id))
    if old is not None:
        if (old.filename, old.organization_id, old.client_id) != (
            filename,
            organization_id,
            client_id,
        ):
            raise ValueError("Artifact ownership cannot be reassigned")
        return old
    session.add(record)
    session.flush()
    return record


def save_task_ips(task, *, locale: str = "en", **kwargs) -> Path:
    """Persist the payload and its ownership before publishing a completion event."""
    with Session(db.engine) as session:
        owner = session.get(db.TaskRecord, task.task_id)
        if owner is None or not owner.organization_id or not owner.client_id:
            raise ValueError("IPS task requires client ownership")
        from api.documents import draft_from_ips, ips_content

        can_create_draft = True
        try:
            ips_content(kwargs["ips_dict"], locale)
        except (ValidationError, KeyError, TypeError, AttributeError):
            # A domain-valid IPS may need human correction (for example, its
            # weights do not sum to one). Preserve that staff artifact and its
            # audit trail without creating an invalid publication draft.
            try:
                IPSDocument.model_validate(kwargs["ips_dict"])
            except ValidationError:
                raise ValueError(msg("documents.invalid_source", locale)) from None
            can_create_draft = False

        filepath = ips_storage.save_ips(**kwargs, client_id=owner.client_id)
        try:
            artifact = register_artifact(
                session,
                kind="ips",
                resource_id=filepath.stem,
                filename=filepath.name,
                organization_id=owner.organization_id,
                client_id=owner.client_id,
                created_by=owner.created_by,
            )
            if can_create_draft:
                draft_from_ips(
                    session, artifact, kwargs["ips_dict"], owner.created_by, locale
                )
            session.commit()
        except Exception:
            # SQL rollback cannot remove a filesystem write. Remove this task's
            # unique file so a failed transaction cannot be resurrected by the
            # startup artifact migration.
            filepath.unlink(missing_ok=True)
            raise
    return filepath


def load_artifact(record: db.ArtifactRecord):
    """Reject malformed/replaced payloads as well as unsafe file paths."""
    path = artifact_path(record)
    if record.kind == "ips":
        payload = ips_storage.load_ips(path)
        if not isinstance(payload, dict) or not isinstance(
            payload.get("metadata"), dict
        ):
            raise ValueError("Invalid IPS payload")
        metadata = payload["metadata"]
    else:
        payload = report_storage.load_report(path)
        if payload.report_id != record.resource_id:
            raise ValueError("Invalid report ID")
        metadata = {"client_id": payload.client_id}
    if metadata.get("client_id") not in (None, "", record.client_id) or metadata.get(
        "organization_id"
    ) not in (None, "", record.organization_id):
        raise ValueError("Conflicting artifact ownership")
    return payload

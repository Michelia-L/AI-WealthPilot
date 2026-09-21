"""Explicit ownership for hand-written API test artifacts, never inferred by name."""

from sqlmodel import Session

from api import db
from api.ownership import create_client, ensure_local_organization


def artifact_client_id(document_id: str | None = None) -> str:
    with Session(db.engine) as session:
        if document_id:
            existing = session.get(db.ArtifactRecord, ("ips", document_id))
            if existing:
                return existing.client_id
        organization = ensure_local_organization(session)
        client = create_client(session, organization.id)
        client_id = client.id
        if document_id:
            from api.artifacts import register_artifact

            register_artifact(
                session,
                kind="ips",
                resource_id=document_id,
                filename=f"{document_id}.json",
                organization_id=organization.id,
                client_id=client_id,
            )
        session.commit()
        return client_id


def write_owned_ips(document_id: str) -> None:
    import json

    from src.agents import ips_storage

    (ips_storage.IPS_DIR / f"{document_id}.json").write_text(
        json.dumps(
            {
                "ips": {"client_name": "Fixture"},
                "audit_trail": {},
                "metadata": {"client_id": artifact_client_id(document_id)},
            }
        )
    )


def task_owner() -> dict:
    from sqlmodel import select

    with Session(db.engine) as session:
        org = ensure_local_organization(session)
        user = session.exec(select(db.UserRecord)).first()
        if user is None:
            user = db.UserRecord(email="task-fixture@example.invalid")
            session.add(user)
            session.flush()
        owner = {"organization_id": org.id, "created_by": user.id}
        session.commit()
        return owner


def index_artifacts() -> None:
    from api.migrate_resources import migrate_resources

    with db.engine.begin() as connection:
        migrate_resources(connection)

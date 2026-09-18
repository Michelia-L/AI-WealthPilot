"""Explicit ownership for hand-written API test artifacts, never inferred by name."""

from sqlmodel import Session

from api import db
from api.ownership import create_client, ensure_local_organization


def artifact_client_id() -> str:
    with Session(db.engine) as session:
        organization = ensure_local_organization(session)
        client = create_client(session, organization.id)
        client_id = client.id
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
                "metadata": {"client_id": artifact_client_id()},
            }
        )
    )

"""IPS cleanup removes authorized source files, retaining publication snapshots."""

import json
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from api import db
from api.artifacts import delete_ips_artifact
from api.i18n import msg
from src.agents import ips_storage
from tests.test_api_access import workspace as access_workspace
from tests.test_documents import CONTENT, publish

workspace = access_workspace


@pytest.mark.parametrize(
    "user,key,status",
    [
        ("advisor", "own", 204),
        ("advisor", "other", 404),
        ("advisor", "foreign", 404),
        ("admin", "other", 204),
        ("admin", "foreign", 404),
        ("client", "own", 403),
    ],
)
def test_delete_respects_ownership(workspace, user, key, status):
    client, _, _, _, artifacts, headers = workspace
    document_id = artifacts[key][0]
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    original = path.read_bytes()
    revision = ips_storage.ips_revision()
    url = f"/api/ips/{document_id}"
    response = client.delete(url, headers=headers(user))
    assert response.status_code == status
    with Session(db.engine) as session:
        owner = session.get(db.ArtifactRecord, ("ips", document_id))
        assert (owner is None) == (status == 204)
    if status == 204:
        assert response.content == b""
        assert not path.exists()
        assert ips_storage.ips_revision() != revision
        assert client.delete(url, headers=headers(user)).status_code == 404
        for suffix in ("", "/pdf", "/export"):
            assert client.get(url + suffix, headers=headers(user)).status_code == 404
        # Startup indexing must not resurrect a removed artifact.
        db.init_db()
        listing = client.get("/api/ips", headers=headers(user)).json()["documents"]
        assert document_id not in {d["document_id"] for d in listing}
    else:
        assert path.read_bytes() == original
        assert ips_storage.ips_revision() == revision


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_delete_failure_is_localized_and_preserves_index(
    workspace, monkeypatch, locale
):
    client, _, _, _, artifacts, headers = workspace
    document_id = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    original = path.read_bytes()

    def fail_rename(self, *args, **kwargs):
        raise PermissionError("PRIVATE_FILESYSTEM_DETAIL")

    monkeypatch.setattr(Path, "rename", fail_rename)
    response = client.delete(
        f"/api/ips/{document_id}",
        headers={**headers("advisor"), "X-Locale": locale},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == msg("ips.delete_failed", locale)
    assert "PRIVATE_FILESYSTEM_DETAIL" not in response.text
    assert path.read_bytes() == original
    with Session(db.engine) as session:
        assert session.get(db.ArtifactRecord, ("ips", document_id)) is not None


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_commit_failure_restores_source_and_index(workspace, monkeypatch, locale):
    client, _, _, _, artifacts, headers = workspace
    document_id = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    tombstone = path.with_name(f".{path.name}.deleting")
    original = path.read_bytes()

    def fail_commit(self):
        assert not path.exists()
        assert tombstone.read_bytes() == original
        raise OperationalError("DELETE", {}, RuntimeError("PRIVATE_DB_DETAIL"))

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        response = client.delete(
            f"/api/ips/{document_id}",
            headers={**headers("advisor"), "X-Locale": locale},
        )
    assert response.status_code == 500
    assert response.json()["detail"] == msg("ips.delete_failed", locale)
    assert "PRIVATE_DB_DETAIL" not in response.text
    assert path.read_bytes() == original
    assert not tombstone.exists()
    with Session(db.engine) as session:
        assert session.get(db.ArtifactRecord, ("ips", document_id)) is not None
    assert (
        client.get(f"/api/ips/{document_id}", headers=headers("advisor")).status_code
        == 200
    )
    # The rollback leaves a usable document, including a subsequent delete.
    assert (
        client.delete(f"/api/ips/{document_id}", headers=headers("advisor")).status_code
        == 204
    )


@pytest.mark.parametrize("committed", [False, True])
def test_startup_recovers_interrupted_deletion(workspace, monkeypatch, committed):
    client, _, _, _, artifacts, headers = workspace
    document_id = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    tombstone = path.with_name(f".{path.name}.deleting")
    original = path.read_bytes()
    commit = Session.commit

    def interrupt(self):
        assert tombstone.read_bytes() == original
        if committed:
            commit(self)
        # Bypass the normal exception/rollback handler, like process exit.
        raise SystemExit("Injected interruption")

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", interrupt)
        with pytest.raises(SystemExit), Session(db.engine) as session:
            owner = session.get(db.ArtifactRecord, ("ips", document_id))
            delete_ips_artifact(session, owner)
    assert not path.exists()
    assert tombstone.exists()
    db.init_db()
    db.init_db()  # Recovery is idempotent.
    assert not tombstone.exists()
    with Session(db.engine) as session:
        assert (
            session.get(db.ArtifactRecord, ("ips", document_id)) is None
        ) == committed
    if not committed:
        assert path.read_bytes() == original
    else:
        assert not path.exists()
    expected = 404 if committed else 200
    assert (
        client.get(f"/api/ips/{document_id}", headers=headers("advisor")).status_code
        == expected
    )


def test_committed_delete_defers_failed_tombstone_cleanup(workspace, monkeypatch):
    client, _, _, _, artifacts, headers = workspace
    document_id = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    tombstone = path.with_name(f".{path.name}.deleting")

    def fail_unlink(self, *args, **kwargs):
        raise PermissionError("Injected cleanup failure")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_unlink)
        response = client.delete(f"/api/ips/{document_id}", headers=headers("advisor"))
    assert response.status_code == 204
    assert not path.exists()
    assert tombstone.exists()
    with Session(db.engine) as session:
        assert session.get(db.ArtifactRecord, ("ips", document_id)) is None
    db.init_db()
    assert not tombstone.exists()
    assert (
        client.get(f"/api/ips/{document_id}", headers=headers("advisor")).status_code
        == 404
    )


def test_startup_retries_a_failed_rollback_restore(workspace, monkeypatch):
    client, _, _, _, artifacts, headers = workspace
    document_id = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    tombstone = path.with_name(f".{path.name}.deleting")
    original = path.read_bytes()
    rename = Path.rename

    def fail_commit(self):
        raise OperationalError("DELETE", {}, RuntimeError("Injected commit failure"))

    def fail_restore(self, target):
        if self == tombstone:
            raise PermissionError("Injected restore failure")
        return rename(self, target)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail_commit)
        patch.setattr(Path, "rename", fail_restore)
        response = client.delete(f"/api/ips/{document_id}", headers=headers("advisor"))
    assert response.status_code == 500
    assert not path.exists()
    assert tombstone.read_bytes() == original
    with Session(db.engine) as session:
        assert session.get(db.ArtifactRecord, ("ips", document_id)) is not None
    db.init_db()
    assert path.read_bytes() == original
    assert not tombstone.exists()
    assert (
        client.get(f"/api/ips/{document_id}", headers=headers("advisor")).status_code
        == 200
    )


def test_startup_never_overwrites_existing_source(workspace):
    _, _, _, _, artifacts, _ = workspace
    path = ips_storage.IPS_DIR / f"{artifacts['own'][0]}.json"
    tombstone = path.with_name(f".{path.name}.deleting")
    original = path.read_bytes()
    path.rename(tombstone)
    path.write_text("Replacement source")
    with pytest.raises(RuntimeError, match="existing source"):
        db.init_db()
    assert tombstone.read_bytes() == original
    assert path.read_text() == "Replacement source"


@pytest.mark.parametrize("replacement", ["conflicting_owner", "symlink"])
def test_delete_rejects_replaced_artifacts(workspace, tmp_path, replacement):
    client, _, clients, _, artifacts, headers = workspace
    document_id = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    if replacement == "conflicting_owner":
        payload = json.loads(path.read_text())
        payload["metadata"]["client_id"] = clients["foreign"]
        path.write_text(json.dumps(payload))
    else:
        target = tmp_path / "outside.json"
        path.rename(target)
        path.symlink_to(target)
    original = path.read_bytes()
    response = client.delete(f"/api/ips/{document_id}", headers=headers("advisor"))
    assert response.status_code == 404
    assert path.read_bytes() == original


@pytest.mark.parametrize("status", ["draft", "published", "acknowledged"])
def test_delete_retains_publication_versions(workspace, status):
    client, _, _, _, artifacts, headers = workspace
    source_id = artifacts["own"][0]
    draft = client.post(
        f"/api/ips/{source_id}/documents", headers=headers("advisor")
    ).json()
    url = f"/api/documents/{draft['id']}"
    if status != "draft":
        assert (
            client.put(url, json=CONTENT, headers=headers("advisor")).status_code == 200
        )
        publish(workspace, draft)
    if status == "acknowledged":
        assert (
            client.post(
                f"/api/me/reports/{draft['id']}/acknowledge", headers=headers("client")
            ).status_code
            == 200
        )
    before = client.get(url, headers=headers("advisor")).json()
    client_view = client.get("/api/me/reports", headers=headers("client")).json()
    assert before["status"] == status
    assert (
        client.delete(f"/api/ips/{source_id}", headers=headers("advisor")).status_code
        == 204
    )
    assert client.get(url, headers=headers("advisor")).json() == before
    assert (
        client.get("/api/me/reports", headers=headers("client")).json() == client_view
    )

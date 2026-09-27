"""IPS cleanup removes authorized source files, retaining publication snapshots."""

import json
from pathlib import Path

import pytest
from sqlmodel import Session

from api import db
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

    def fail_unlink(self, *args, **kwargs):
        raise PermissionError("PRIVATE_FILESYSTEM_DETAIL")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
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

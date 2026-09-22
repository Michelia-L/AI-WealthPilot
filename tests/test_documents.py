"""Human publication lifecycle, immutable snapshots and tenant authorization."""

import json

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from api import db, documents
from api.authorization import unassign_advisor
from api.schemas import ClientDocumentContent
from src.agents import ips_storage
from tests.test_api_access import workspace as access_workspace

workspace = access_workspace

CONTENT = {
    "title": "Fixture IPS",
    "summary": "Reviewed content",
    "recommendation": "Discuss the plan",
    "allocation": [{"asset_class": "Bonds", "weight": 1.0}],
}


def create(workspace, key="own", type="ips"):
    client, _, _, profiles, _, headers = workspace
    response = client.post(
        "/api/documents",
        json={"profile_id": profiles[key], "type": type, "content": CONTENT},
        headers=headers("admin"),
    )
    assert response.status_code == 201, response.text
    return response.json()


def transition(workspace, document, action, user="advisor"):
    client, _, _, _, _, headers = workspace
    return client.post(
        f"/api/documents/{document['id']}/{action}", headers=headers(user)
    )


def publish(workspace, document):
    for action, user in (
        ("submit", "advisor"),
        ("approve", "admin"),
        ("publish", "advisor"),
    ):
        response = transition(workspace, document, action, user)
        assert response.status_code == 200, response.text
    return response.json()


def test_full_lifecycle_and_acknowledgement(workspace):
    client, _, clients, _, _, headers = workspace
    draft = create(workspace)
    id_ = draft["id"]
    assert draft["version"] == 1 and draft["status"] == "draft"
    assert draft["client_id"] == clients["own"]
    assert draft["created_by"] == "admin"
    assert transition(workspace, draft, "publish").status_code == 409
    assert transition(workspace, draft, "approve", "admin").status_code == 409
    for action, user, status in (
        (None, None, "draft"),
        ("submit", "advisor", "in_review"),
        ("approve", "admin", "approved"),
    ):
        if action:
            response = transition(workspace, draft, action, user)
            assert response.status_code == 200
            assert response.json()["status"] == status
        assert client.get("/api/me/reports", headers=headers("client")).json() == {
            "reports": []
        }
        assert (
            client.get(f"/api/me/reports/{id_}", headers=headers("client")).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/me/reports/{id_}/acknowledge", headers=headers("client")
            ).status_code
            == 404
        )
    published = transition(workspace, draft, "publish").json()
    assert published["approved_by"] == published["reviewed_by"] == "admin"
    assert published["published_by"] == "advisor"
    assert (
        published["submitted_at"]
        <= published["approved_at"]
        <= published["published_at"]
    )
    assert (
        len(client.get("/api/me/reports", headers=headers("client")).json()["reports"])
        == 1
    )
    report = client.get(f"/api/me/reports/{id_}", headers=headers("client")).json()
    assert report["content"]["summary"] == CONTENT["summary"]
    assert (
        not {"created_by", "reviewed_by", "approved_by", "organization_id", "client_id"}
        & report.keys()
    )
    portfolio = client.get("/api/me/portfolio", headers=headers("client")).json()
    assert portfolio["allocation"] == CONTENT["allocation"]
    assert portfolio["status"] == "published_plan"
    ack = client.post(f"/api/me/reports/{id_}/acknowledge", headers=headers("client"))
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"
    assert (
        client.post(
            f"/api/me/reports/{id_}/acknowledge", headers=headers("client")
        ).json()
        == ack.json()
    )
    staff = client.get(f"/api/documents/{id_}", headers=headers("advisor")).json()
    assert staff["acknowledged_by"] == "client"
    assert staff["published_at"] == published["published_at"]


def test_only_admin_can_approve_and_only_scoped_staff_can_work(workspace):
    client, _, _, _, _, headers = workspace
    draft = create(workspace)
    assert transition(workspace, draft, "submit").status_code == 200
    assert transition(workspace, draft, "approve").status_code == 403
    for user, org, expected in (
        ("client", "a", 403),
        ("foreign_admin", "b", 404),
        ("foreign_advisor", "b", 404),
    ):
        for method, suffix, body in (
            ("GET", "", None),
            ("PUT", "", CONTENT),
            ("POST", "/submit", None),
            ("POST", "/publish", None),
            ("POST", "/revisions", {}),
        ):
            response = client.request(
                method,
                f"/api/documents/{draft['id']}{suffix}",
                json=body,
                headers=headers(user, org),
            )
            assert response.status_code == expected
    assert (
        client.post(
            f"/api/documents/{draft['id']}/approve",
            headers=headers("foreign_admin", "b"),
        ).status_code
        == 404
    )
    other = create(workspace, key="other")
    assert transition(workspace, other, "submit").status_code == 404
    assert (
        client.get(
            f"/api/documents/{other['id']}", headers=headers("advisor")
        ).status_code
        == 404
    )
    assert [
        d["id"]
        for d in client.get("/api/documents", headers=headers("advisor")).json()[
            "documents"
        ]
    ] == [draft["id"]]


def test_revisions_preserve_published_and_reviewed_content(workspace):
    client, _, _, _, _, headers = workspace
    draft = create(workspace)
    url = f"/api/documents/{draft['id']}"
    assert client.put(url, json=CONTENT, headers=headers("advisor")).status_code == 200
    for action, user in (
        ("submit", "advisor"),
        ("approve", "admin"),
        ("publish", "advisor"),
    ):
        assert transition(workspace, draft, action, user).status_code == 200
        assert (
            client.put(
                url,
                json={**CONTENT, "summary": "Overwrite"},
                headers=headers("advisor"),
            ).status_code
            == 409
        )
    old = client.get(url, headers=headers("advisor")).json()
    revision = client.post(
        url + "/revisions",
        json={"content": {**CONTENT, "summary": "Revision"}},
        headers=headers("advisor"),
    )
    assert revision.status_code == 201
    revised = revision.json()
    assert revised["id"] != draft["id"]
    assert revised["document_id"] == draft["document_id"]
    assert revised["version"] == 2 and revised["status"] == "draft"
    assert revised["approved_by"] is None and revised["published_at"] is None
    assert client.get(url, headers=headers("advisor")).json() == old
    assert (
        client.get(
            f"/api/me/reports/{revised['id']}", headers=headers("client")
        ).status_code
        == 404
    )
    assert (
        client.get("/api/me/portfolio", headers=headers("client")).json()["report_id"]
        == draft["id"]
    )
    publish(workspace, revised)
    assert (
        client.get("/api/me/portfolio", headers=headers("client")).json()["report_id"]
        == revised["id"]
    )
    assert (
        len(client.get("/api/me/reports", headers=headers("client")).json()["reports"])
        == 2
    )
    next_revision = client.post(
        url + "/revisions", json={}, headers=headers("advisor")
    ).json()
    assert next_revision["version"] == 3


def test_client_cannot_read_or_acknowledge_another_clients_report(workspace):
    client, _, _, _, _, headers = workspace
    draft = create(workspace)
    publish(workspace, draft)
    for id_ in (draft["id"], "missing"):
        for method, suffix in (("GET", ""), ("POST", "/acknowledge")):
            assert (
                client.request(
                    method,
                    f"/api/me/reports/{id_}{suffix}",
                    headers=headers("other_client"),
                ).status_code
                == 404
            )
    assert client.get("/api/me/reports", headers=headers("other_client")).json() == {
        "reports": []
    }


def test_revoked_assignment_applies_to_workflow(workspace):
    client, principals, clients, _, _, headers = workspace
    draft = create(workspace)
    with Session(db.engine) as session:
        unassign_advisor(session, principals["admin"], "a", "advisor", clients["own"])
        session.commit()
    assert transition(workspace, draft, "submit").status_code == 404
    assert client.get("/api/documents", headers=headers("advisor")).json() == {
        "documents": []
    }


def test_legacy_ips_projection_and_source_file_changes(workspace):
    client, _, _, _, artifacts, headers = workspace
    source = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{source}.json"
    raw = json.loads(path.read_text())
    raw["ips"]["executive_summary"] = "Original summary"
    raw["ips"]["optimizer_config"] = "SYNTHETIC_INTERNAL"
    raw["audit_trail"] = {"final_status": "approved", "trace": "SYNTHETIC_INTERNAL"}
    path.write_text(json.dumps(raw))
    response = client.post(f"/api/ips/{source}/documents", headers=headers("advisor"))
    assert response.status_code == 201
    draft = response.json()
    assert draft["status"] == "draft"  # machine approval is never human approval
    assert draft["source_artifact_id"] == source
    assert "SYNTHETIC_INTERNAL" not in json.dumps(draft)
    publish(workspace, draft)
    path.write_text('{"ips":{"executive_summary":"Changed source"}}')
    report = client.get(
        f"/api/me/reports/{draft['id']}", headers=headers("client")
    ).json()
    assert report["content"]["summary"] == "Original summary"
    path.unlink()
    assert (
        client.get(f"/api/me/reports/{draft['id']}", headers=headers("client")).json()
        == report
    )


@pytest.mark.parametrize("type", ["portfolio_review", "retirement_report"])
def test_other_deliverable_types_share_lifecycle(workspace, type):
    draft = create(workspace, type=type)
    assert publish(workspace, draft)["type"] == type


@pytest.mark.parametrize(
    "change",
    [
        {"organization_id": "b"},
        {"created_by": "admin"},
        {"status": "published"},
        {"content": {**CONTENT, "audit_trail": {}}},
        {
            "content": {
                **CONTENT,
                "allocation": [{"asset_class": "Bonds", "weight": 0.1}],
            }
        },
        {"type": "unknown"},
    ],
)
def test_invalid_and_internal_fields_are_rejected_without_echo(workspace, change):
    client, _, _, profiles, _, headers = workspace
    response = client.post(
        "/api/documents",
        json={
            "profile_id": profiles["own"],
            "type": "ips",
            "content": CONTENT,
            **change,
        },
        headers=headers("advisor"),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}


def test_stale_edit_cannot_overwrite_submitted_content(workspace):
    draft = create(workspace)
    with Session(db.engine) as stale:
        record = stale.get(db.DocumentRecord, draft["id"])
        assert transition(workspace, draft, "submit").status_code == 200
        with pytest.raises(HTTPException) as exc:
            documents.change(
                stale, record, "draft", "en", content={**CONTENT, "summary": "Stale"}
            )
        assert exc.value.status_code == 409


def test_document_database_constraints_and_restart(workspace):
    _, _, clients, _, _, _ = workspace
    draft = create(workspace)
    publish(workspace, draft)
    db.init_db()
    db.init_db()
    with Session(db.engine) as session:
        assert session.get(db.DocumentRecord, draft["id"]).status == "published"
        with pytest.raises(IntegrityError):
            documents.create_draft(
                session,
                organization_id="a",
                client_id=clients["foreign"],
                created_by="admin",
                type="ips",
                content=ClientDocumentContent(**CONTENT),
            )
        session.rollback()
        record = session.get(db.DocumentRecord, draft["id"])
        session.add(db.DocumentRecord(**{**record.model_dump(), "id": "duplicate"}))
        with pytest.raises(IntegrityError):
            session.commit()


def test_reimporting_an_ips_creates_a_revision_not_an_overwrite(workspace):
    client, _, _, _, artifacts, headers = workspace
    url = f"/api/ips/{artifacts['own'][0]}/documents"
    first = client.post(url, headers=headers("advisor")).json()
    publish(workspace, first)
    second = client.post(url, headers=headers("advisor")).json()
    assert second["document_id"] == first["document_id"]
    assert second["version"] == 2 and second["status"] == "draft"
    assert second["approved_by"] is None
    reports = client.get("/api/me/reports", headers=headers("client")).json()["reports"]
    assert [report["id"] for report in reports] == [first["id"]]


def test_ips_adoption_rejects_invalid_content_without_echo(workspace):
    client, _, _, _, artifacts, headers = workspace
    source = artifacts["own"][0]
    path = ips_storage.IPS_DIR / f"{source}.json"
    raw = json.loads(path.read_text())
    raw["ips"]["executive_summary"] = {"private": "SYNTHETIC_SENSITIVE_TEXT"}
    path.write_text(json.dumps(raw))
    response = client.post(f"/api/ips/{source}/documents", headers=headers("advisor"))
    assert response.status_code == 422
    assert "SYNTHETIC_SENSITIVE_TEXT" not in response.text
    assert client.get("/api/documents", headers=headers("advisor")).json() == {
        "documents": []
    }

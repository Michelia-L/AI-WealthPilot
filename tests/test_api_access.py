"""Existing business APIs enforce real sessions, roles and stable object ownership."""

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session

from api import auth, db
from api.authorization import assign_advisor, unassign_advisor
from api.main import create_app
from api.profile_convert import payload_to_data
from api.schemas import ProfilePayload
from src.agents import ips_storage, report_storage
from tests.api_ownership_helpers import index_artifacts
from tests.test_api_profiles import sample_payload
from tests.test_authorization import seed

PUBLIC = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/demo"),
}
OPERATIONS = [
    (method.upper(), path)
    for path, methods in create_app().openapi()["paths"].items()
    for method in methods
    if method in {"get", "post", "put", "delete"}
]


@pytest.mark.parametrize(
    "method,path", [item for item in OPERATIONS if item not in PUBLIC]
)
def test_every_business_operation_rejects_anonymous(anonymous_client, method, path):
    url = re.sub(r"\{[^}]+\}", "1", path)
    response = anonymous_client.request(
        method, url, json={} if method in {"POST", "PUT"} else None
    )
    assert response.status_code == 401, (method, path)
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"


@pytest.fixture
def workspace(anonymous_client):
    with Session(db.engine) as session:
        principals, clients = seed(session)
        profiles = {}
        for key, client_id in clients.items():
            data = payload_to_data(
                ProfilePayload(**sample_payload()), created_at="2026-01-01"
            )
            record = db.ProfileRecord(name=key, age=40, data=data, client_id=client_id)
            session.add(record)
            session.flush()
            profiles[key] = record.id
        session.commit()
        tokens = {
            key: auth.issue_session(
                session, session.get(db.UserRecord, key)
            ).access_token
            for key in principals
        }
    artifacts = {}
    for key in ("own", "other", "foreign"):
        path = ips_storage.save_ips(
            {"client_name": key},
            {},
            key,
            client_id=clients[key],
            profile_id=profiles[key],
        )
        report = report_storage.save_report(
            content=f"private-{key}",
            client_name=key,
            model="test",
            client_id=clients[key],
        )
        with Session(db.engine) as session:
            session.add(
                db.TaskRecord(
                    task_id=key,
                    kind="ips",
                    status="completed",
                    meta_json=json.dumps(
                        {
                            "client_id": clients[key],
                            "organization_id": "b" if key == "foreign" else "a",
                            "created_by": "advisor",
                        }
                    ),
                    events_json=json.dumps(
                        [{"type": "done", "document_id": path.stem}]
                    ),
                )
            )
            session.commit()
        artifacts[key] = (path.stem, report.report_id)

    index_artifacts()

    def headers(user, org="a"):
        return {"Authorization": f"Bearer {tokens[user]}", "X-Organization-ID": org}

    return anonymous_client, principals, clients, profiles, artifacts, headers


@pytest.mark.parametrize(
    "user,key,allowed",
    [
        ("client", "own", True),
        ("client", "other", False),
        ("advisor", "own", True),
        ("advisor", "other", False),
        ("admin", "other", True),
        ("admin", "foreign", False),
    ],
)
def test_profile_and_ips_matrix(workspace, user, key, allowed):
    client, _, _, profiles, artifacts, headers = workspace
    expected = 200 if allowed else 404
    profile_id = profiles[key]
    document_id, _ = artifacts[key]
    for url in (f"/api/profiles/{profile_id}", f"/api/ips/{document_id}"):
        response = client.get(url, headers=headers(user))
        assert response.status_code == expected
        assert response.headers["cache-control"] == "no-store"
    response = client.put(
        f"/api/profiles/{profile_id}", json=sample_payload(), headers=headers(user)
    )
    assert response.status_code == expected


def test_lists_filter_before_exposing_objects(workspace):
    client, _, _, profiles, artifacts, headers = workspace
    for user, expected in (("client", {"own"}), ("advisor", {"own"})):
        h = headers(user)
        assert {
            p["id"] for p in client.get("/api/profiles", headers=h).json()["profiles"]
        } == {profiles[key] for key in expected}
        assert {
            d["document_id"]
            for d in client.get("/api/ips", headers=h).json()["documents"]
        } == {artifacts[key][0] for key in expected}
    assert {
        r["report_id"]
        for r in client.get("/api/advisor/reports", headers=headers("advisor")).json()[
            "reports"
        ]
    } == {artifacts["own"][1]}


@pytest.mark.parametrize(
    "user,key,expected",
    [("advisor", "other", 404), ("admin", "foreign", 404), ("client", "own", 403)],
)
def test_exports_monitoring_reports_and_tasks_reject_forbidden_objects(
    workspace, user, key, expected
):
    client, _, _, profiles, artifacts, headers = workspace
    doc, report = artifacts[key]
    urls = [
        f"/api/monitoring/{doc}",
        f"/api/monitoring/{doc}/backtest",
        f"/api/monitoring/{doc}/holdings",
        f"/api/advisor/reports/{report}",
        f"/api/advisor/reports/{report}/pdf",
        f"/api/advisor/reports/{report}/export",
        f"/api/ips/tasks/{key}/events",
        f"/api/portfolio/recommendation?profile_id={profiles[key]}",
        f"/api/retirement/cme-suggestion?profile_id={profiles[key]}",
    ]
    for url in urls:
        assert client.get(url, headers=headers(user)).status_code == expected, url
    assert (
        client.delete(
            f"/api/advisor/reports/{report}", headers=headers(user)
        ).status_code
        == expected
    )
    assert (
        client.post(
            "/api/advisor/report/stream",
            json={"profile_id": profiles[key]},
            headers=headers(user),
        ).status_code
        == expected
    )
    assert (
        client.post(
            "/api/ips/generate",
            json={"profile_id": profiles[key]},
            headers=headers(user),
        ).status_code
        == expected
    )
    if user != "client":
        for suffix in ("/pdf", "/export?format=markdown"):
            assert (
                client.get(f"/api/ips/{doc}{suffix}", headers=headers(user)).status_code
                == 404
            )


def test_assignment_changes_apply_to_existing_artifacts_and_task_replay(workspace):
    client, principals, clients, profiles, artifacts, headers = workspace
    h = headers("advisor")
    url = f"/api/profiles/{profiles['other']}"
    assert client.get(url, headers=h).status_code == 404
    with Session(db.engine) as session:
        assign_advisor(session, principals["admin"], "a", "advisor", clients["other"])
        session.commit()
    assert client.get(url, headers=h).status_code == 200
    assert client.get("/api/ips/tasks/other/events", headers=h).status_code == 200
    with Session(db.engine) as session:
        unassign_advisor(session, principals["admin"], "a", "advisor", clients["other"])
        session.commit()
    assert client.get(url, headers=h).status_code == 404
    assert client.get("/api/ips/tasks/other/events", headers=h).status_code == 404
    assert (
        client.get(
            f"/api/advisor/reports/{artifacts['other'][1]}", headers=h
        ).status_code
        == 404
    )


def test_admin_cannot_switch_to_another_organization_or_edit_global_settings(workspace):
    client, _, _, _, _, headers = workspace
    for user in ("client", "advisor", "admin"):
        assert (
            client.put("/api/settings/llm", json={}, headers=headers(user)).status_code
            == 403
        )
        assert (
            client.get("/api/profiles", headers=headers(user, "b")).status_code == 403
        )
    assert client.get("/api/profiles", headers=headers("outsider")).status_code == 403
    assert (
        client.get(
            "/api/profiles", headers={"Authorization": headers("dual")["Authorization"]}
        ).status_code
        == 403
    )
    assert {
        o["id"]
        for o in client.get("/api/auth/organizations", headers=headers("dual")).json()[
            "organizations"
        ]
    } == {"a", "b"}


def test_saved_report_ownership_comes_from_authorized_profile(workspace):
    client, _, _, profiles, _, headers = workspace
    body = {
        "profile_id": profiles["own"],
        "client_name": "foreign",
        "client_id": "forged",
        "content": "fixture",
        "model": "test",
    }
    response = client.post(
        "/api/advisor/reports", json=body, headers=headers("advisor")
    )
    assert response.status_code == 201
    assert response.json()["client_name"] == "own"
    report_id = response.json()["report_id"]
    assert (
        client.get(
            f"/api/advisor/reports/{report_id}", headers=headers("foreign_admin", "b")
        ).status_code
        == 404
    )
    body["profile_id"] = profiles["foreign"]
    assert (
        client.post(
            "/api/advisor/reports", json=body, headers=headers("advisor")
        ).status_code
        == 404
    )


def test_demo_login_is_isolated_from_local_org(anonymous_client, monkeypatch):
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    response = anonymous_client.post("/api/auth/demo")
    assert response.status_code == 200
    # Even an old, explicitly provisioned local membership must not turn
    # public demo sign-in into a path to real workstation data.
    from sqlmodel import select

    from api.ownership import ensure_local_organization, set_membership

    with Session(db.engine) as session:
        user = session.exec(
            select(db.UserRecord).where(db.UserRecord.is_demo.is_(True))
        ).one()
        ensure_local_organization(session)
        set_membership(session, "local", user.id, "admin")
        session.commit()
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Organization-ID": "demo",
    }
    assert [
        o["id"]
        for o in anonymous_client.get(
            "/api/auth/organizations", headers=headers
        ).json()["organizations"]
    ] == ["demo"]
    assert (
        anonymous_client.get(
            "/api/profiles", headers={**headers, "X-Organization-ID": "local"}
        ).status_code
        == 403
    )
    assert (
        anonymous_client.put("/api/settings/llm", json={}, headers=headers).status_code
        == 403
    )


def test_every_operation_declares_its_access_scope():
    for path, methods in create_app().openapi()["paths"].items():
        for method, operation in methods.items():
            scope = operation.get("x-access-scope")
            assert scope in {
                "public",
                "authenticated",
                "shared",
                "client-scoped",
                "advisor-scoped",
                "admin-scoped",
            }, (method, path)
            if (method.upper(), path) not in PUBLIC:
                assert operation["security"] == [{"SessionBearer": []}]


def test_profile_creation_and_import_cannot_choose_another_organization(workspace):
    client, _, _, _, _, headers = workspace
    body = {**sample_payload(), "client_id": "forged", "organization_id": "b"}
    response = client.post("/api/profiles", json=body, headers=headers("advisor"))
    assert response.status_code == 201
    profile_id = response.json()["id"]
    assert (
        client.get(
            f"/api/profiles/{profile_id}", headers=headers("advisor")
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/profiles/{profile_id}", headers=headers("foreign_admin", "b")
        ).status_code
        == 404
    )
    with Session(db.engine) as session:
        profile = session.get(db.ProfileRecord, profile_id)
        assert session.get(db.ClientRecord, profile.client_id).organization_id == "a"
    assert (
        client.post("/api/profiles", json=body, headers=headers("client")).status_code
        == 403
    )
    assert (
        client.post("/api/profiles/import", headers=headers("admin")).status_code == 403
    )
    assert (
        client.post(
            "/api/profiles/import/upload",
            json={"files": [{"filename": "fixture.json", "content": "{}"}]},
            headers=headers("advisor"),
        ).status_code
        == 403
    )


def test_task_kind_and_creator_scope_cannot_be_bypassed(workspace):
    client, _, _, _, _, headers = workspace
    with Session(db.engine) as session:
        session.add(
            db.TaskRecord(
                task_id="standalone",
                organization_id="a",
                created_by="advisor",
                kind="optimize",
                status="completed",
                meta_json=json.dumps({"organization_id": "a", "created_by": "advisor"}),
                events_json='[{"type":"done"}]',
            )
        )
        session.add(db.TaskRecord(task_id="legacy", kind="ips", status="completed"))
        session.commit()
    assert (
        client.get(
            "/api/portfolio/tasks/standalone/events", headers=headers("advisor")
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/portfolio/tasks/standalone/events", headers=headers("admin")
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/ips/tasks/standalone/events", headers=headers("advisor")
        ).status_code
        == 404
    )
    assert (
        client.get("/api/ips/tasks/legacy/events", headers=headers("admin")).status_code
        == 404
    )


def test_fleet_cache_never_reuses_another_users_scope(workspace, monkeypatch):
    from pathlib import Path

    from api.routers import monitoring

    client, principals, clients, _, artifacts, headers = workspace
    seen = []

    def compute(*, documents, **kwargs):
        ids = {Path(item["filepath"]).stem for item in documents}
        seen.append(ids)
        return {
            "as_of": "2026-01-01",
            "items": [],
            "summary": {"total": len(ids), "ok": len(ids), "breach": 0, "unknown": 0},
        }

    monkeypatch.setattr(monitoring, "compute_fleet_status", compute)
    monkeypatch.setattr(monitoring, "_fleet_status_cache", monitoring.TTLCache())
    assert (
        client.get("/api/monitoring/status", headers=headers("admin")).json()[
            "summary"
        ]["total"]
        == 2
    )
    assert (
        client.get("/api/monitoring/status", headers=headers("advisor")).json()[
            "summary"
        ]["total"]
        == 1
    )
    assert seen == [
        {artifacts[key][0] for key in ("own", "other")},
        {artifacts["own"][0]},
    ]
    with Session(db.engine) as session:
        unassign_advisor(session, principals["admin"], "a", "advisor", clients["own"])
        session.commit()
    assert (
        client.get("/api/monitoring/status", headers=headers("advisor")).json()[
            "summary"
        ]["total"]
        == 0
    )
    assert seen[-1] == set()


def test_legacy_and_malformed_artifacts_fail_closed(workspace):
    client, _, _, _, _, headers = workspace
    for data in ({"metadata": {}}, {"metadata": {"client_id": {"forged": True}}}, []):
        (ips_storage.IPS_DIR / "ips_legacy.json").write_text(json.dumps(data))
        assert (
            client.get("/api/ips/ips_legacy", headers=headers("admin")).status_code
            == 404
        )
    legacy = report_storage.save_report(
        content="legacy", client_name="own", model="test"
    )
    assert (
        client.get(
            f"/api/advisor/reports/{legacy.report_id}", headers=headers("admin")
        ).status_code
        == 404
    )


def test_task_authorization_uses_columns_not_mutable_metadata(workspace):
    client, _, _, _, _, headers = workspace
    with Session(db.engine) as session:
        record = session.get(db.TaskRecord, "foreign")
        record.meta_json = json.dumps({"organization_id": "a", "created_by": "advisor"})
        session.add(record)
        session.commit()
    assert (
        client.get(
            "/api/ips/tasks/foreign/events", headers=headers("advisor")
        ).status_code
        == 404
    )


def test_artifact_authorization_precedes_payload_loading(workspace, monkeypatch):
    client, _, _, _, artifacts, headers = workspace

    def unexpected(*args, **kwargs):
        pytest.fail("Unauthorized artifact payload was loaded")

    monkeypatch.setattr(ips_storage, "load_ips", unexpected)
    monkeypatch.setattr(report_storage, "load_report", unexpected)
    doc, report = artifacts["foreign"]
    assert client.get(f"/api/ips/{doc}", headers=headers("admin")).status_code == 404
    assert (
        client.get(
            f"/api/advisor/reports/{report}", headers=headers("admin")
        ).status_code
        == 404
    )


def test_explicit_legacy_adoption_respects_client_scope(workspace):
    from api.migrate_resources import migrate_resources

    client, _, clients, _, _, headers = workspace
    path = ips_storage.save_ips({"client_name": "Legacy"}, {}, "Legacy")
    report = report_storage.save_report("Legacy", "Legacy", "fixture")
    assert (
        client.get(f"/api/ips/{path.stem}", headers=headers("client")).status_code
        == 404
    )
    with db.engine.begin() as connection:
        migrate_resources(
            connection,
            [
                {
                    "kind": "ips",
                    "filename": path.name,
                    "organization_id": "a",
                    "client_id": clients["own"],
                },
                {
                    "kind": "report",
                    "filename": Path(report.filepath).name,
                    "organization_id": "a",
                    "client_id": clients["own"],
                },
            ],
        )
    assert (
        client.get(f"/api/ips/{path.stem}", headers=headers("client")).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/ips/{path.stem}", headers=headers("foreign_admin", "b")
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/advisor/reports/{report.report_id}", headers=headers("advisor")
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/advisor/reports/{report.report_id}",
            headers=headers("foreign_admin", "b"),
        ).status_code
        == 404
    )


def test_holdings_queries_filter_tenant_and_document_owner(workspace):
    from api.holding_snapshots import (
        latest_snapshot,
        latest_snapshots,
        snapshot_history,
    )

    client, _, clients, _, artifacts, headers = workspace
    doc = artifacts["own"][0]
    with Session(db.engine) as session:
        for org, client_id in [("b", clients["foreign"]), ("a", clients["other"])]:
            session.add(
                db.HoldingSnapshotRecord(
                    document_id=doc,
                    organization_id=org,
                    client_id=client_id,
                    as_of="2026-01-01",
                    data={"sentinel": "must-not-leak"},
                )
            )
        session.commit()
        assert latest_snapshot(session, doc, organization_id="a") is None
        assert latest_snapshots(session, [doc], organization_id="a") == {}
        assert snapshot_history(session, doc, organization_id="a") == []

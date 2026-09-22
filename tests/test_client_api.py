"""Client contracts, identity-derived scope and publication-only reads."""

import json

import pytest
from sqlmodel import Session

from api import db
from api.main import create_app
from api.ownership import create_client, set_membership
from api.schemas import ClientDocumentContent, ClientPortfolioResponse, OptimizeResponse
from tests.test_api_access import workspace as access_workspace

workspace = access_workspace

CLIENT_PATHS = (
    "",
    "/profile",
    "/portfolio",
    "/goals",
    "/risk-profile",
    "/reports",
    "/advisor",
)


@pytest.mark.parametrize("suffix", CLIENT_PATHS)
def test_client_identity_cannot_be_selected_by_ids(workspace, suffix):
    client, _, clients, profiles, _, headers = workspace
    h = headers("client")
    expected = client.get(f"/api/me{suffix}", headers=h)
    assert expected.status_code == 200
    altered = client.get(
        f"/api/me{suffix}",
        params={
            "client_id": clients["foreign"],
            "profile_id": profiles["other"],
            "organization_id": "b",
            "user_id": "admin",
        },
        headers={**h, "X-Organization-ID": "b"},
    )
    assert altered.json() == expected.json()
    assert altered.headers["cache-control"] == "no-store"


def test_client_projection_excludes_internal_fields(workspace):
    client, _, _, profiles, _, headers = workspace
    with Session(db.engine) as session:
        record = session.get(db.ProfileRecord, profiles["own"])
        record.data = {**record.data, "notes": "STAFF_ONLY_SYNTHETIC"}
        session.add(record)
        session.commit()
    h = headers("client")
    identity = client.get("/api/me", headers=h).json()
    assert identity == {
        "user_id": "client",
        "email": "client@example.invalid",
        "role": "client",
        "is_demo": False,
    }
    profile = client.get("/api/me/profile", headers=h).json()
    assert set(profile) == {
        "name",
        "age",
        "marital_status",
        "dependents",
        "investable_assets",
        "total_liabilities",
        "net_worth",
        "time_horizon_years",
        "updated_at",
    }
    assert "STAFF_ONLY_SYNTHETIC" not in json.dumps(profile)
    portfolio = client.get("/api/me/portfolio", headers=h).json()
    assert portfolio["status"] == "unavailable"
    assert portfolio["performance"] is None
    assert portfolio["allocation"] == []
    goals = client.get("/api/me/goals", headers=h).json()
    assert all(g["progress"] is None for g in goals["goals"])
    assert client.get("/api/me/advisor", headers=h).json() == {
        "advisors": [{"email": "advisor@example.invalid"}]
    }


@pytest.mark.parametrize("user", ["advisor", "admin", "outsider"])
def test_link_alone_or_staff_membership_is_not_a_client_role(workspace, user):
    client, _, _, _, _, headers = workspace
    assert client.get("/api/me", headers=headers(user)).status_code == 404


def test_role_removal_and_ambiguous_links_fail_closed(workspace):
    client, _, _, _, _, headers = workspace
    with Session(db.engine) as session:
        create_client(session, "a", user_id="client")
        session.commit()
    response = client.get("/api/me", headers=headers("client"))
    assert response.status_code == 409
    assert "Contact your advisor" in response.json()["detail"]
    with Session(db.engine) as session:
        set_membership(session, "a", "client", "advisor")
        session.commit()
    assert client.get("/api/me", headers=headers("client")).status_code == 404


def test_multiple_memberships_do_not_require_an_organization_selector(workspace):
    client, _, _, _, _, headers = workspace
    # The dual user is admin in a, client in b; only b is their client identity.
    response = client.get("/api/me", headers=headers("dual", "a"))
    assert response.status_code == 200
    assert response.json()["user_id"] == "dual"


def test_missing_profile_and_pagination_validation(workspace):
    client, _, _, profiles, _, headers = workspace
    with Session(db.engine) as session:
        session.delete(session.get(db.ProfileRecord, profiles["own"]))
        session.commit()
    assert client.get("/api/me", headers=headers("client")).status_code == 200
    assert client.get("/api/me/profile", headers=headers("client")).status_code == 404
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert (
            client.get(
                "/api/me/reports", params=params, headers=headers("client")
            ).status_code
            == 422
        )


def test_risk_explanation_and_absent_assessment_are_localized(workspace):
    client, _, _, profiles, _, headers = workspace
    for locale, marker in (("en", "financial capacity"), ("zh", "财务能力")):
        response = client.get(
            "/api/me/risk-profile", headers={**headers("client"), "X-Locale": locale}
        )
        assert response.status_code == 200
        assert response.json()["assessed"]
        assert marker in response.json()["explanation"]
        assert " / " not in response.json()["level"]
    with Session(db.engine) as session:
        record = session.get(db.ProfileRecord, profiles["own"])
        record.data = {
            **record.data,
            "risk_profile": {"ability_score": 0, "willingness_score": 3},
        }
        session.add(record)
        session.commit()
    risk = client.get("/api/me/risk-profile", headers=headers("client")).json()
    assert not risk["assessed"] and risk["level"] is None
    assert "incomplete" in risk["explanation"]


def test_revoked_or_demoted_advisor_not_returned(workspace):
    client, _, _, _, _, headers = workspace
    with Session(db.engine) as session:
        set_membership(session, "a", "advisor", "client")
        session.commit()
    assert client.get("/api/me/advisor", headers=headers("client")).json() == {
        "advisors": []
    }


def test_openapi_separates_client_and_advisor_schemas():
    schema = create_app().openapi()
    for path, operations in schema["paths"].items():
        if path.startswith("/api/me"):
            for operation in operations.values():
                assert operation["tags"] == ["Client Portal"]
                assert operation["x-access-scope"] == "client-scoped"
                assert not {"client_id", "profile_id", "organization_id"} & {
                    p["name"] for p in operation.get("parameters", [])
                }
                assert (
                    "Client"
                    in operation["responses"]["200"]["content"]["application/json"][
                        "schema"
                    ]["$ref"]
                )
        elif path.startswith(("/api/profiles", "/api/ips", "/api/documents")):
            assert all(
                op["x-access-scope"] in ("advisor-scoped", "admin-scoped")
                for op in operations.values()
            )
    assert not issubclass(ClientPortfolioResponse, OptimizeResponse)
    for name, definition in schema["components"]["schemas"].items():
        if name.startswith("Client"):
            assert definition["additionalProperties"] is False
            assert (
                not {
                    "notes",
                    "metadata",
                    "audit_trail",
                    "created_by",
                    "approved_by",
                    "model",
                    "bl_config",
                    "cvar_alpha",
                }
                & definition.get("properties", {}).keys()
            )
    assert ClientDocumentContent.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize("suffix", ("", "/pdf", "/export"))
def test_client_cannot_bypass_publication_via_raw_ips(workspace, suffix):
    client, _, _, _, artifacts, headers = workspace
    for doc, _ in artifacts.values():
        assert (
            client.get(f"/api/ips/{doc}{suffix}", headers=headers("client")).status_code
            == 403
        )

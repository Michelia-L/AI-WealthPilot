"""Authorization matrix, assignment constraints, and real bearer integration."""

import pytest
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api import auth, db
from api.authorization import (
    assign_advisor,
    get_authorized_client,
    require_advisor,
    require_client,
    require_org_admin,
    unassign_advisor,
)
from api.i18n import get_request_locale
from api.ownership import create_client, set_membership
from api.schemas import Principal


def seed(session):
    for org in ("a", "b"):
        session.add(db.OrganizationRecord(id=org, name=f"Organization {org}"))
    roles = {
        "client": [("a", "client")],
        "other_client": [("a", "client")],
        "advisor": [("a", "advisor")],
        "admin": [("a", "admin")],
        "foreign_advisor": [("b", "advisor")],
        "foreign_admin": [("b", "admin")],
        "dual": [("a", "admin"), ("b", "client")],
        "outsider": [],
    }
    principals = {}
    for user_id in roles:
        user = db.UserRecord(id=user_id, email=f"{user_id}@example.invalid")
        session.add(user)
        principals[user_id] = Principal(
            user_id=user.id, email=user.email, is_demo=False
        )
    session.flush()
    for user_id, memberships in roles.items():
        for org, role in memberships:
            set_membership(session, org, user_id, role)
    clients = {
        "own": create_client(session, "a", user_id="client").id,
        "other": create_client(session, "a", user_id="other_client").id,
        "unlinked": create_client(session, "a").id,
        "advisor_self": create_client(session, "a", user_id="advisor").id,
        "foreign": create_client(session, "b").id,
        "dual_self": create_client(session, "b", user_id="dual").id,
        "outsider_self": create_client(session, "a", user_id="outsider").id,
    }
    assign_advisor(session, principals["admin"], "a", "advisor", clients["own"])
    session.commit()
    return principals, clients


@pytest.fixture
def context():
    with Session(db.engine) as session:
        principals, clients = seed(session)
        yield session, principals, clients


@pytest.mark.parametrize(
    "user, organization, client, allowed",
    [
        ("client", "a", "own", True),
        ("client", "a", "other", False),
        ("client", "a", "unlinked", False),
        ("client", "b", "foreign", False),
        ("advisor", "a", "own", True),
        ("advisor", "a", "other", False),
        ("advisor", "a", "advisor_self", False),
        ("advisor", "b", "foreign", False),
        ("foreign_advisor", "a", "own", False),
        ("admin", "a", "unlinked", True),
        ("admin", "a", "foreign", False),
        ("admin", "b", "foreign", False),
        ("foreign_admin", "a", "own", False),
        ("foreign_admin", "b", "foreign", True),
        ("dual", "a", "own", True),
        ("dual", "b", "dual_self", True),
        ("dual", "b", "foreign", False),
        ("outsider", "a", "outsider_self", False),
        ("admin", "a", "missing", False),
        ("admin", "missing", "own", False),
    ],
)
def test_object_access_matrix(context, user, organization, client, allowed):
    session, principals, clients = context
    client_id = clients.get(client, client)
    if allowed:
        result = get_authorized_client(
            session, principals[user], organization, client_id
        )
        assert result.id == client_id
        assert result.organization_id == organization
    else:
        with pytest.raises(HTTPException) as error:
            get_authorized_client(session, principals[user], organization, client_id)
        assert error.value.status_code == 404
        assert error.value.detail == "Client not found."
        assert error.value.headers == {"Cache-Control": "no-store"}


@pytest.mark.parametrize(
    "guard, role",
    [
        (require_client, "client"),
        (require_advisor, "advisor"),
        (require_org_admin, "admin"),
    ],
)
def test_role_guards_are_exact_and_scoped(context, guard, role):
    session, principals, _ = context
    guard(session, principals[role], "a")
    for user in ("client", "advisor", "admin", "outsider"):
        if user != role:
            with pytest.raises(HTTPException) as error:
                guard(session, principals[user], "a")
            assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        guard(session, principals[role], "b")
    assert error.value.status_code == 403


def test_assignment_creation_revocation_and_rollback(context):
    session, principals, clients = context
    args = (session, principals["admin"], "a", "advisor", clients["other"])
    first = assign_advisor(*args)
    original_id, original_created = first.id, first.created_at
    session.commit()
    again = assign_advisor(*args)
    assert (again.id, again.created_at) == (original_id, original_created)
    assert get_authorized_client(session, principals["advisor"], "a", clients["other"])
    unassign_advisor(*args)
    session.rollback()
    assert get_authorized_client(session, principals["advisor"], "a", clients["other"])
    unassign_advisor(*args)
    session.commit()
    unassign_advisor(*args)  # Idempotent, even after removal.
    with pytest.raises(HTTPException) as error:
        get_authorized_client(session, principals["advisor"], "a", clients["other"])
    assert error.value.status_code == 404
    assign_advisor(*args)
    session.rollback()
    assert (
        session.exec(
            select(db.AdvisorClientAssignmentRecord).where(
                db.AdvisorClientAssignmentRecord.client_id == clients["other"]
            )
        ).first()
        is None
    )


@pytest.mark.parametrize(
    "actor, org, advisor, client, status",
    [
        ("advisor", "a", "advisor", "other", 403),
        ("client", "a", "advisor", "own", 403),
        ("foreign_admin", "a", "advisor", "own", 403),
        ("admin", "a", "foreign_advisor", "own", 422),
        ("admin", "a", "client", "own", 422),
        ("admin", "a", "missing", "own", 422),
        ("admin", "a", "advisor", "foreign", 404),
        ("admin", "a", "advisor", "missing", 404),
    ],
)
def test_invalid_assignment_requests(context, actor, org, advisor, client, status):
    session, principals, clients = context
    with pytest.raises(HTTPException) as error:
        assign_advisor(
            session, principals[actor], org, advisor, clients.get(client, client)
        )
    assert error.value.status_code == status
    assert len(session.exec(select(db.AdvisorClientAssignmentRecord)).all()) == 1


def test_non_admin_cannot_revoke_assignment(context):
    session, principals, clients = context
    with pytest.raises(HTTPException) as error:
        unassign_advisor(session, principals["advisor"], "a", "advisor", clients["own"])
    assert error.value.status_code == 403
    # A foreign admin cannot remove an assignment using their own org scope.
    unassign_advisor(
        session, principals["foreign_admin"], "b", "advisor", clients["own"]
    )
    assert get_authorized_client(session, principals["advisor"], "a", clients["own"])


def test_permission_changes_are_read_again_with_same_session(context):
    session, principals, clients = context
    # Prime ORM identity map as well as the authorization queries.
    session.exec(select(db.OrganizationMembershipRecord)).all()
    assert get_authorized_client(session, principals["advisor"], "a", clients["own"])
    session.commit()
    with Session(db.engine) as writer:
        unassign_advisor(writer, principals["admin"], "a", "advisor", clients["own"])
        writer.commit()
    with pytest.raises(HTTPException) as error:
        get_authorized_client(session, principals["advisor"], "a", clients["own"])
    assert error.value.status_code == 404
    session.commit()
    with Session(db.engine) as writer:
        set_membership(writer, "a", "admin", "client")
        writer.commit()
    with pytest.raises(HTTPException) as error:
        get_authorized_client(session, principals["admin"], "a", clients["own"])
    assert error.value.status_code == 404


def test_assignment_is_not_itself_an_advisor_role(context):
    session, principals, clients = context
    set_membership(session, "a", "advisor", "client")
    session.commit()
    with pytest.raises(HTTPException) as error:
        get_authorized_client(session, principals["advisor"], "a", clients["own"])
    assert error.value.status_code == 404
    # Its current client role permits only its own linked Client.
    assert get_authorized_client(
        session, principals["advisor"], "a", clients["advisor_self"]
    )
    unassign_advisor(session, principals["admin"], "a", "advisor", clients["own"])
    set_membership(session, "a", "advisor", "advisor")
    session.commit()
    with pytest.raises(HTTPException):
        get_authorized_client(session, principals["advisor"], "a", clients["own"])


@pytest.mark.parametrize("user_state", ["disabled", "missing", "demo", "anonymous"])
def test_stale_principal_is_not_sufficient(context, user_state):
    session, principals, clients = context
    if user_state == "disabled":
        session.execute(text("UPDATE users SET is_active = 0 WHERE id = 'client'"))
    elif user_state == "demo":
        session.execute(text("UPDATE users SET is_demo = 1 WHERE id = 'client'"))
    elif user_state == "anonymous":
        principals["client"] = None
    else:
        principals["client"] = Principal(
            user_id="missing", email="fictional@example.invalid", is_demo=False
        )
    session.commit()
    with pytest.raises(HTTPException) as error:
        get_authorized_client(session, principals["client"], "a", clients["own"])
    assert error.value.status_code == 401


def test_disabled_advisor_cannot_receive_assignment(context):
    session, principals, clients = context
    session.execute(text("UPDATE users SET is_active = 0 WHERE id = 'advisor'"))
    session.commit()
    with pytest.raises(HTTPException) as error:
        assign_advisor(session, principals["admin"], "a", "advisor", clients["other"])
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "organization, advisor, client",
    [
        ("a", "foreign_advisor", "own"),
        ("b", "advisor", "foreign"),
        ("a", "advisor", "foreign"),
        ("a", "missing", "own"),
        ("a", "advisor", "missing"),
        ("a", "advisor", "own"),  # Duplicate existing assignment.
        (None, "advisor", "own"),
    ],
)
def test_database_rejects_invalid_assignments(context, organization, advisor, client):
    session, _, clients = context
    session.add(
        db.AdvisorClientAssignmentRecord(
            organization_id=organization,
            advisor_user_id=advisor,
            client_id=clients.get(client, client),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_database_prevents_moving_assigned_client_across_organizations(context):
    session, _, clients = context
    with pytest.raises(IntegrityError):
        session.execute(
            text("UPDATE clients SET organization_id = 'b' WHERE id = :id"),
            {"id": clients["own"]},
        )
    session.rollback()
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "DELETE FROM organization_memberships WHERE organization_id = 'a' AND user_id = 'advisor'"
            )
        )
    session.rollback()


def test_current_schema_upgrade_preserves_clients_and_infers_no_assignments(
    tmp_path, monkeypatch
):
    engine = db.make_engine(f"sqlite:///{tmp_path}/previous.db")
    # Create #73 tables and then remove the new index to model its old schema.
    for model in (
        db.OrganizationRecord,
        db.UserRecord,
        db.OrganizationMembershipRecord,
        db.ClientRecord,
    ):
        model.__table__.create(engine)
    db.CLIENT_ORGANIZATION_INDEX.drop(engine)
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    with Session(engine) as session:
        session.add(db.OrganizationRecord(id="a", name="Previous organization"))
        session.add(db.UserRecord(id="advisor", email="advisor@example.invalid"))
        session.flush()
        set_membership(session, "a", "advisor", "advisor")
        client = create_client(session, "a")
        client_id = client.id
        session.commit()
    db.init_db()
    db.init_db()
    with Session(engine) as session:
        assert session.get(db.ClientRecord, client_id).organization_id == "a"
        assert session.exec(select(db.AdvisorClientAssignmentRecord)).all() == []
        session.add(
            db.AdvisorClientAssignmentRecord(
                organization_id="a", advisor_user_id="advisor", client_id=client_id
            )
        )
        session.commit()
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_bearer_dependency_and_localized_denials(bare_client):
    @bare_client.app.get("/test/organizations/{organization_id}/clients/{client_id}")
    def protected_client(
        organization_id: str,
        client_id: str,
        principal: Principal = Depends(auth.get_current_principal),
        session: Session = Depends(db.get_session),
        locale: str = Depends(get_request_locale),
    ):
        record = get_authorized_client(
            session, principal, organization_id, client_id, locale=locale
        )
        return {"id": record.id}

    with Session(db.engine) as session:
        principals, clients = seed(session)
        user = session.get(db.UserRecord, "client")
        token = auth.issue_session(session, user).access_token
    path = f"/test/organizations/a/clients/{clients['own']}"
    assert bare_client.get(path).status_code == 401
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Role": "admin",
        "X-User-ID": "admin",
    }
    assert bare_client.get(path, headers=headers).status_code == 200
    denied_path = f"/test/organizations/a/clients/{clients['other']}"
    response = bare_client.get(
        denied_path + "?user_id=admin&role=admin", headers=headers
    )
    missing = bare_client.get("/test/organizations/a/clients/missing", headers=headers)
    assert response.status_code == missing.status_code == 404
    assert response.json() == missing.json() == {"detail": "Client not found."}
    assert response.headers["Cache-Control"] == "no-store"
    headers["X-Locale"] = "zh"
    assert bare_client.get(denied_path, headers=headers).json() == {
        "detail": "未找到客户。"
    }
    assert bare_client.post("/api/auth/logout", headers=headers).status_code == 204
    assert bare_client.get(path, headers=headers).status_code == 401


def test_demo_identity_has_no_assignment_bypass(context, monkeypatch):
    session, principals, clients = context
    session.execute(text("UPDATE users SET is_demo = 1 WHERE id = 'advisor'"))
    session.commit()
    with pytest.raises(HTTPException) as error:
        assign_advisor(session, principals["admin"], "a", "advisor", clients["other"])
    assert error.value.status_code == 422
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    assert get_authorized_client(session, principals["advisor"], "a", clients["own"])
    with pytest.raises(HTTPException) as error:
        get_authorized_client(session, principals["advisor"], "a", clients["other"])
    assert error.value.status_code == 404
    assign_advisor(session, principals["admin"], "a", "advisor", clients["other"])
    session.commit()
    assert get_authorized_client(session, principals["advisor"], "a", clients["other"])


def test_client_link_changes_take_effect_without_changing_principal(context):
    session, principals, clients = context
    assert get_authorized_client(session, principals["client"], "a", clients["own"])
    session.execute(
        text("UPDATE clients SET user_id = 'other_client' WHERE id = :id"),
        {"id": clients["own"]},
    )
    session.commit()
    with pytest.raises(HTTPException) as error:
        get_authorized_client(session, principals["client"], "a", clients["own"])
    assert error.value.status_code == 404
    assert get_authorized_client(
        session, principals["other_client"], "a", clients["own"]
    )


@pytest.fixture
def bare_client(anonymous_client):
    return anonymous_client

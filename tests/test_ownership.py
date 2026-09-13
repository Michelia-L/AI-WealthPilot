"""Database constraints, ownership services and legacy migration regression tests."""

import json

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api import db
from api.main import _seed_demo_profile
from api.migrate_profiles import import_json_profiles, import_uploaded_profiles
from api.ownership import (
    LOCAL_ORGANIZATION_ID,
    attach_profile,
    create_client,
    create_local_profile,
    create_organization,
    ensure_local_organization,
    get_profile_owner,
    set_membership,
)
from api.schemas import ProfileUploadFile


@pytest.fixture
def session():
    with Session(db.engine) as session:
        yield session


def new_profile():
    return db.ProfileRecord(name="Fictional client", age=30, data={})


def test_client_without_login_or_profile_and_role_independence(session):
    organization = create_organization(session, "Organization A")
    other = create_organization(session, "Organization B")
    user = db.UserRecord(email="fictional@example.invalid")
    session.add(user)
    session.flush()
    membership = set_membership(
        session, organization.id, user.id, db.MembershipRole.ADVISOR
    )
    set_membership(session, other.id, user.id, db.MembershipRole.CLIENT)
    client = create_client(session, organization.id, user_id=user.id)
    anonymous = create_client(session, organization.id)
    assert anonymous.user_id is None
    assert session.exec(select(db.ProfileRecord)).all() == []
    profile = attach_profile(session, client.id, new_profile())
    profile_id = profile.id
    client_id = client.id
    assert get_profile_owner(session, profile_id).organization_id == organization.id
    # Changing a role never changes business ownership or creates a new member.
    updated = set_membership(session, organization.id, user.id, db.MembershipRole.ADMIN)
    assert updated.id == membership.id
    assert get_profile_owner(session, profile_id).id == client_id
    assert len(session.exec(select(db.OrganizationMembershipRecord)).all()) == 2
    session.commit()
    session.expire_all()
    assert session.get(db.OrganizationMembershipRecord, membership.id).role == "admin"
    assert get_profile_owner(session, profile_id).user_id == user.id


def test_service_validation_and_profile_uniqueness(session):
    organization = create_organization(session, "Local testing")
    with pytest.raises(ValueError, match="name"):
        create_organization(session, " ")
    with pytest.raises(ValueError, match="Organization not found"):
        create_client(session, "missing")
    with pytest.raises(ValueError, match="User not found"):
        create_client(session, organization.id, user_id="missing")
    with pytest.raises(ValueError, match="not a valid"):
        set_membership(session, organization.id, "missing", "owner")
    with pytest.raises(ValueError, match="User not found"):
        set_membership(session, organization.id, "missing", db.MembershipRole.ADMIN)
    with pytest.raises(ValueError, match="Organization not found"):
        set_membership(session, "missing", "missing", db.MembershipRole.ADMIN)
    with pytest.raises(ValueError, match="Client not found"):
        attach_profile(session, "missing", new_profile())
    with pytest.raises(ValueError, match="Profile not found"):
        get_profile_owner(session, 999)
    client = create_client(session, organization.id)
    profile = attach_profile(session, client.id, new_profile())
    with pytest.raises(ValueError, match="already attached"):
        attach_profile(session, client.id, profile)
    with pytest.raises(ValueError, match="already has a profile"):
        attach_profile(session, client.id, new_profile())


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO clients (id, organization_id) VALUES ('bad', NULL)",
        "INSERT INTO clients (id, organization_id) VALUES ('bad', 'missing')",
        "INSERT INTO clients (id, organization_id, user_id) VALUES ('bad', 'org', 'missing')",
        "INSERT INTO organization_memberships VALUES ('bad', 'org', 'user', 'owner')",
        "INSERT INTO organization_memberships VALUES ('bad', 'org', 'user', NULL)",
        "INSERT INTO organization_memberships VALUES ('bad', 'missing', 'user', 'client')",
        "INSERT INTO organization_memberships VALUES ('bad', 'org', 'missing', 'client')",
        "INSERT INTO organization_memberships VALUES ('duplicate', 'org', 'user', 'client')",
        "UPDATE client_profiles SET client_id = NULL",
        "UPDATE client_profiles SET client_id = 'missing'",
        "INSERT INTO client_profiles (client_id, name, age, risk_level, created_at, updated_at) "
        "SELECT client_id, name, age, risk_level, created_at, updated_at FROM client_profiles",
        "DELETE FROM organizations WHERE id = 'org'",
        "DELETE FROM clients",
        "DELETE FROM users WHERE id = 'user'",
    ],
)
def test_database_rejects_invalid_ownership(session, statement):
    session.add(db.OrganizationRecord(id="org", name="Test organization"))
    session.add(db.UserRecord(id="user", email="test@example.invalid"))
    session.flush()
    set_membership(session, "org", "user", db.MembershipRole.ADVISOR)
    client = create_client(session, "org", user_id="user")
    attach_profile(session, client.id, new_profile())
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(text(statement))
        session.commit()
    session.rollback()
    assert len(session.exec(select(db.ProfileRecord)).all()) == 1


def test_local_creation_rolls_back_with_caller(session):
    create_local_profile(session, new_profile())
    session.rollback()
    assert session.exec(select(db.OrganizationRecord)).all() == []
    assert session.exec(select(db.ClientRecord)).all() == []
    assert session.exec(select(db.ProfileRecord)).all() == []
    first = ensure_local_organization(session)
    first.name = "Renamed workspace"
    session.add(first)
    session.flush()
    assert ensure_local_organization(session).name == "Renamed workspace"


def legacy_database(tmp_path, monkeypatch, *, empty=False):
    engine = db.make_engine(f"sqlite:///{tmp_path}/legacy-ownership.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE client_profiles (id INTEGER PRIMARY KEY, user_id VARCHAR, "
            "name VARCHAR NOT NULL, age INTEGER NOT NULL, risk_level VARCHAR NOT NULL, "
            "created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL, data JSON)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_client_profiles_name ON client_profiles (name)"
        )
        if not empty:
            connection.execute(
                text(
                    "INSERT INTO client_profiles VALUES (:id, :user_id, 'Legacy', 42, '', 'created', 'updated', :data)"
                ),
                [
                    {
                        "id": 7,
                        "user_id": None,
                        "data": '{ "notes": "虚构", "unknown": [1, 2] }',
                    },
                    {"id": 29, "user_id": "reserved-legacy-id", "data": "null"},
                ],
            )
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    return engine


def test_migration_preserves_raw_records_and_is_idempotent(tmp_path, monkeypatch):
    engine = legacy_database(tmp_path, monkeypatch)
    with engine.connect() as connection:
        before = connection.exec_driver_sql(
            "SELECT * FROM client_profiles ORDER BY id"
        ).all()
    db.init_db()
    with Session(engine) as session:
        owners = {
            p.id: p.client_id for p in session.exec(select(db.ProfileRecord)).all()
        }
        assert len(set(owners.values())) == 2
        assert all(
            c.organization_id == LOCAL_ORGANIZATION_ID and c.user_id is None
            for c in session.exec(select(db.ClientRecord)).all()
        )
        assert session.exec(select(db.OrganizationMembershipRecord)).all() == []
        assert session.exec(select(db.UserRecord)).all() == []
    # Simulate restart with a fresh pool and verify FK enforcement on it too.
    engine.dispose()
    db.init_db()
    with engine.connect() as connection:
        after = connection.exec_driver_sql(
            "SELECT id, user_id, name, age, risk_level, created_at, updated_at, data FROM client_profiles ORDER BY id"
        ).all()
        assert before == after
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    with Session(engine) as session:
        assert {
            p.id: p.client_id for p in session.exec(select(db.ProfileRecord)).all()
        } == owners
        assert len(session.exec(select(db.ClientRecord)).all()) == 2
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE client_profiles SET client_id = NULL"))
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(text("UPDATE client_profiles SET client_id = 'missing'"))
        session.rollback()
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE client_profiles SET client_id = :owner"),
                {"owner": owners[7]},
            )
        session.rollback()
        created = create_local_profile(session, new_profile())
        assert created.id > 29
        session.commit()


def test_empty_legacy_database_migrates(tmp_path, monkeypatch):
    engine = legacy_database(tmp_path, monkeypatch, empty=True)
    db.init_db()
    with Session(engine) as session:
        assert session.exec(select(db.ProfileRecord)).all() == []
        create_local_profile(session, new_profile())
        session.commit()


def test_migration_ddl_and_data_roll_back_on_failure(tmp_path, monkeypatch):
    from sqlalchemy import event

    engine = legacy_database(tmp_path, monkeypatch)

    def fail_after_drop(
        connection, cursor, statement, parameters, context, executemany
    ):
        if statement.startswith("ALTER TABLE client_profiles_owned"):
            raise RuntimeError("Injected migration failure")

    event.listen(engine, "before_cursor_execute", fail_after_drop)
    with pytest.raises(RuntimeError, match="Injected"):
        db.init_db()
    event.remove(engine, "before_cursor_execute", fail_after_drop)
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM client_profiles").scalar()
            == 2
        )
        assert "client_profiles_owned" not in inspect(connection).get_table_names()
        assert "clients" not in inspect(connection).get_table_names()
        assert "client_id" not in {
            c["name"] for c in inspect(connection).get_columns("client_profiles")
        }
    db.init_db()
    with Session(engine) as session:
        assert len(session.exec(select(db.ClientRecord)).all()) == 2


def test_migration_refuses_unknown_columns_without_data_loss(tmp_path, monkeypatch):
    engine = legacy_database(tmp_path, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE client_profiles ADD COLUMN custom_value VARCHAR"
        )
    with pytest.raises(RuntimeError, match="Unrecognized"):
        db.init_db()
    with engine.connect() as connection:
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM client_profiles").scalar()
            == 2
        )


def test_create_update_delete_api_preserves_client(bare_client):
    response = bare_client.post("/api/profiles", json={"name": "Fictional", "age": 30})
    assert response.status_code == 201
    profile_id = response.json()["id"]
    with Session(db.engine) as session:
        owner_id = get_profile_owner(session, profile_id).id
        assert (
            get_profile_owner(session, profile_id).organization_id
            == LOCAL_ORGANIZATION_ID
        )
    assert (
        bare_client.put(
            f"/api/profiles/{profile_id}", json={"name": "Updated", "age": 31}
        ).status_code
        == 200
    )
    with Session(db.engine) as session:
        assert get_profile_owner(session, profile_id).id == owner_id
    assert bare_client.delete(f"/api/profiles/{profile_id}").status_code == 204
    with Session(db.engine) as session:
        assert session.get(db.ClientRecord, owner_id) is not None
        assert session.get(db.ProfileRecord, profile_id) is None


@pytest.mark.parametrize("upload", [False, True])
def test_import_owns_profiles_and_dedupes_only_local_organization(
    session, tmp_path, upload
):
    other = create_organization(session, "Other organization")
    client = create_client(session, other.id)
    attach_profile(
        session,
        client.id,
        db.ProfileRecord(name="Imported", age=30, created_at="old", data={}),
    )
    session.commit()
    data = {"name": "Imported", "age": 30, "created_at": "old"}
    content = json.dumps(data)
    if upload:

        def run():
            return import_uploaded_profiles(
                session, [ProfileUploadFile(filename="profile.json", content=content)]
            )
    else:
        (tmp_path / "profile.json").write_text(content)

        def run():
            return import_json_profiles(session, tmp_path)

    assert run()["imported"] == 1
    assert run()["skipped"] == 1
    profiles = session.exec(select(db.ProfileRecord)).all()
    assert len(profiles) == 2
    assert {get_profile_owner(session, p.id).organization_id for p in profiles} == {
        other.id,
        LOCAL_ORGANIZATION_ID,
    }
    assert len(session.exec(select(db.ClientRecord)).all()) == 2


def test_demo_seed_has_ownership_without_identity_or_membership(session, monkeypatch):
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    assert _seed_demo_profile(session)
    assert not _seed_demo_profile(session)
    profile = session.exec(select(db.ProfileRecord)).one()
    owner = get_profile_owner(session, profile.id)
    assert owner.organization_id == LOCAL_ORGANIZATION_ID
    assert owner.user_id is None
    assert session.exec(select(db.UserRecord)).all() == []
    assert session.exec(select(db.OrganizationMembershipRecord)).all() == []


def test_concurrent_initializers_migrate_once(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine = legacy_database(tmp_path, monkeypatch)
    barrier = Barrier(2)

    def initialize():
        barrier.wait(timeout=5)
        db.init_db()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(initialize) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    with Session(engine) as session:
        assert len(session.exec(select(db.ProfileRecord)).all()) == 2
        assert len(session.exec(select(db.ClientRecord)).all()) == 2
        assert len(session.exec(select(db.OrganizationRecord)).all()) == 1


def test_ownership_upgrade_keeps_existing_identity_and_settings(tmp_path, monkeypatch):
    engine = legacy_database(tmp_path, monkeypatch)
    db.UserRecord.__table__.create(engine)
    db.AuthSessionRecord.__table__.create(engine)
    db.AppSettingRecord.__table__.create(engine)
    with Session(engine) as session:
        user = db.UserRecord(email="migration@example.invalid")
        session.add(user)
        session.flush()
        user_id = user.id
        session.add(
            db.AuthSessionRecord(
                token_hash="fictional-digest",
                user_id=user_id,
                created_at=1,
                expires_at=2,
            )
        )
        session.add(db.AppSettingRecord(key="fictional-setting", value="preserved"))
        session.commit()
    db.init_db()
    with Session(engine) as session:
        assert session.get(db.UserRecord, user_id).email == "migration@example.invalid"
        assert session.get(db.AuthSessionRecord, "fictional-digest").user_id == user_id
        assert (
            session.get(db.AppSettingRecord, "fictional-setting").value == "preserved"
        )
        assert session.exec(select(db.OrganizationMembershipRecord)).all() == []

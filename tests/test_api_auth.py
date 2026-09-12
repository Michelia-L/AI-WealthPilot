"""Identity boundaries tested against real hashing and temporary SQLite."""

import hashlib
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine, select

from api import auth, db
from api import create_user as provision
from api.main import create_app
from api.schemas import LoginRequest


@pytest.fixture
def identity(bare_client):
    credentials = LoginRequest(
        email="researcher@example.invalid", password=secrets.token_urlsafe(24)
    )
    with Session(db.engine) as session:
        user = auth.create_user(session, credentials)
        return user.id, credentials


def login(client, credentials, **kwargs):
    return client.post(
        "/api/auth/login",
        json={
            "email": credentials.email,
            "password": credentials.password.get_secret_value(),
        },
        **kwargs,
    )


def bearer(response):
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_login_persists_only_hashes_and_resolves_server_identity(bare_client, identity):
    user_id, credentials = identity
    response = login(bare_client, credentials)
    headers = bearer(response)
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert datetime.fromisoformat(payload["expires_at"]).timestamp() > time.time()
    assert response.headers["cache-control"] == "no-store"
    headers.update({"X-User-ID": "someone-else", "X-Role": "admin"})
    me = bare_client.get("/api/auth/me?user_id=someone-else", headers=headers)
    assert me.status_code == 200
    assert me.json() == {
        "user_id": user_id,
        "email": credentials.email,
        "is_demo": False,
    }
    assert me.headers["cache-control"] == "no-store"
    with Session(db.engine) as session:
        record = session.exec(select(db.AuthSessionRecord)).one()
        user = session.get(db.UserRecord, user_id)
        assert record.user_id == user_id
        assert (
            record.token_hash
            == hashlib.sha256(payload["access_token"].encode()).hexdigest()
        )
        assert payload["access_token"] not in str(record.model_dump())
        assert credentials.password.get_secret_value() not in str(user.model_dump())
        assert user.password_hash.startswith("scrypt-v1$")
        assert user.password_hash not in repr(user)
        assert credentials.password.get_secret_value() not in repr(credentials)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic invalid"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer short"},
        {"Authorization": f"Bearer {secrets.token_urlsafe(32)}"},
        {"X-User-ID": "demo", "X-Role": "admin"},
    ],
)
def test_missing_or_invalid_auth_is_401(bare_client, headers):
    for path, method in [("/api/auth/me", "get"), ("/api/auth/logout", "post")]:
        response = getattr(bare_client, method)(path, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"detail": "Please sign in and try again."}


def test_logout_revokes_only_presented_session(bare_client, identity):
    _, credentials = identity
    first, second = login(bare_client, credentials), login(bare_client, credentials)
    assert first.json()["access_token"] != second.json()["access_token"]
    response = bare_client.post("/api/auth/logout", headers=bearer(first))
    assert response.status_code == 204
    assert response.content == b""
    assert bare_client.get("/api/auth/me", headers=bearer(first)).status_code == 401
    assert (
        bare_client.post("/api/auth/logout", headers=bearer(first)).status_code == 401
    )
    assert bare_client.get("/api/auth/me", headers=bearer(second)).status_code == 200


def test_sessions_survive_app_restart_and_expire_at_deadline(
    bare_client, identity, monkeypatch
):
    _, credentials = identity
    response = login(bare_client, credentials)
    headers = bearer(response)
    expiry = int(datetime.fromisoformat(response.json()["expires_at"]).timestamp())
    # New FastAPI instance with the same persisted database, no dependency override.
    with TestClient(create_app()) as restarted:
        assert restarted.get("/api/auth/me", headers=headers).status_code == 200
        monkeypatch.setattr(auth.time, "time", lambda: expiry - 1)
        assert restarted.get("/api/auth/me", headers=headers).status_code == 200
        monkeypatch.setattr(auth.time, "time", lambda: expiry)
        assert restarted.get("/api/auth/me", headers=headers).status_code == 401
        assert restarted.post("/api/auth/logout", headers=headers).status_code == 401
        assert login(restarted, credentials).status_code == 200
    with Session(db.engine) as session:
        assert len(session.exec(select(db.AuthSessionRecord)).all()) == 1


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_user_status_is_checked_on_every_request(bare_client, identity, action):
    user_id, credentials = identity
    headers = bearer(login(bare_client, credentials))
    with Session(db.engine) as session:
        user = session.get(db.UserRecord, user_id)
        if action == "disable":
            user.is_active = False
            session.add(user)
        else:
            session.delete(user)
        session.commit()
    assert bare_client.get("/api/auth/me", headers=headers).status_code == 401
    assert login(bare_client, credentials).status_code == 401


def test_login_failure_does_not_disclose_account_state(bare_client, identity):
    user_id, credentials = identity
    wrong = credentials.model_copy(
        update={
            "password": LoginRequest(
                email=credentials.email, password=secrets.token_urlsafe(24)
            ).password
        }
    )
    invalid = login(bare_client, wrong)
    unknown = login(
        bare_client, credentials.model_copy(update={"email": "missing@example.invalid"})
    )
    with Session(db.engine) as session:
        user = session.get(db.UserRecord, user_id)
        user.is_active = False
        session.add(user)
        session.commit()
    disabled = login(bare_client, credentials)
    assert invalid.status_code == unknown.status_code == disabled.status_code == 401
    assert invalid.json() == unknown.json() == disabled.json()
    assert credentials.email not in invalid.text
    assert credentials.password.get_secret_value() not in disabled.text


def test_login_lockout_persists_and_recovers(bare_client, identity, monkeypatch):
    user_id, credentials = identity
    wrong = LoginRequest(email=credentials.email, password=secrets.token_urlsafe(24))
    for _ in range(auth.MAX_FAILED_LOGINS):
        assert login(bare_client, wrong).status_code == 401
    with Session(db.engine) as session:
        user = session.get(db.UserRecord, user_id)
        assert user.failed_logins == auth.MAX_FAILED_LOGINS
        deadline = user.locked_until
    with TestClient(create_app()) as restarted:
        assert login(restarted, credentials).status_code == 401
        monkeypatch.setattr(auth.time, "time", lambda: deadline)
        # A wrong attempt after the cooldown starts again at one, not five.
        assert login(restarted, wrong).status_code == 401
        with Session(db.engine) as session:
            user = session.get(db.UserRecord, user_id)
            assert user.failed_logins == 1
            assert user.locked_until == 0
        assert login(restarted, credentials).status_code == 200
    with Session(db.engine) as session:
        assert session.get(db.UserRecord, user_id).failed_logins == 0


def test_simultaneous_failed_logins_cannot_lose_attempts(
    bare_client, identity, monkeypatch
):
    user_id, credentials = identity
    barrier = threading.Barrier(auth.MAX_FAILED_LOGINS)

    def simultaneous_failure(*_):
        # Force all requests to read the same pre-failure user state.
        barrier.wait(timeout=10)
        return False

    monkeypatch.setattr(auth, "verify_password", simultaneous_failure)
    with ThreadPoolExecutor(max_workers=auth.MAX_FAILED_LOGINS) as pool:
        responses = list(
            pool.map(
                lambda _: login(bare_client, credentials), range(auth.MAX_FAILED_LOGINS)
            )
        )
    assert all(response.status_code == 401 for response in responses)
    with Session(db.engine) as session:
        user = session.get(db.UserRecord, user_id)
        assert user.failed_logins == auth.MAX_FAILED_LOGINS
        assert user.locked_until > time.time()


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_auth_errors_are_localized_and_never_echo_inputs(bare_client, locale):
    secret = secrets.token_urlsafe(24)
    headers = {"X-Locale": locale}
    invalid_bodies = [
        {"email": secret, "password": secret},
        {"email": "invalid@example.invalid", "password": {"secret": secret}},
        {"email": "invalid@example.invalid", "password": secret, "role": "admin"},
        {"email": "invalid@example.invalid", "password": secret * 50},
        {"password": secret},
    ]
    expected = auth.msg("auth.invalid_request", locale)
    for body in invalid_bodies:
        response = bare_client.post("/api/auth/login", json=body, headers=headers)
        assert response.status_code == 422
        assert response.json() == {"detail": expected}
        assert secret not in response.text
    malformed = bare_client.post(
        "/api/auth/login",
        content='{"password": "' + secret,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert malformed.status_code == 422
    assert secret not in malformed.text
    surrogate = bare_client.post(
        "/api/auth/login",
        content='{"email":"user@example.invalid","password":"' + secret + '\\ud800"}',
        headers={**headers, "Content-Type": "application/json"},
    )
    assert surrogate.status_code == 422
    assert surrogate.json() == {"detail": expected}
    assert secret not in surrogate.text
    assert bare_client.get("/api/auth/me", headers=headers).json() == {
        "detail": auth.msg("auth.required", locale)
    }
    invalid = login(
        bare_client,
        LoginRequest(email="missing@example.invalid", password=secret),
        headers=headers,
    )
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": auth.msg("auth.invalid_login", locale)}


def test_demo_is_explicit_and_uses_normal_sessions(bare_client, monkeypatch):
    assert bare_client.post("/api/auth/demo").status_code == 404
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    # Demo does not silently authenticate requests without a bearer token.
    assert bare_client.get("/api/auth/me").status_code == 401
    first = bare_client.post("/api/auth/demo")
    second = bare_client.post("/api/auth/demo")
    me = bare_client.get("/api/auth/me", headers=bearer(first)).json()
    assert me["is_demo"] is True
    assert me["email"] == auth.DEMO_EMAIL
    with Session(db.engine) as session:
        assert len(session.exec(select(db.UserRecord)).all()) == 1
        assert len(session.exec(select(db.AuthSessionRecord)).all()) == 2
        assert session.get(db.UserRecord, me["user_id"]).password_hash is None
    assert (
        login(
            bare_client,
            LoginRequest(email=auth.DEMO_EMAIL, password=secrets.token_urlsafe(24)),
        ).status_code
        == 401
    )
    assert (
        bare_client.post("/api/auth/logout", headers=bearer(first)).status_code == 204
    )
    assert bare_client.get("/api/auth/me", headers=bearer(first)).status_code == 401
    monkeypatch.setattr("src.config.DEMO_MODE", False)
    assert bare_client.post("/api/auth/demo").status_code == 404
    assert bare_client.get("/api/auth/me", headers=bearer(second)).status_code == 401


def test_concurrent_demo_logins_share_identity(bare_client, monkeypatch):
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(lambda _: bare_client.post("/api/auth/demo"), range(4))
        )
    assert all(response.status_code == 200 for response in responses)
    with Session(db.engine) as session:
        assert len(session.exec(select(db.UserRecord)).all()) == 1
        assert len(session.exec(select(db.AuthSessionRecord)).all()) == 4


def test_disabled_demo_identity_cannot_login(bare_client, monkeypatch):
    monkeypatch.setattr("src.config.DEMO_MODE", True)
    response = bare_client.post("/api/auth/demo")
    with Session(db.engine) as session:
        user = session.exec(select(db.UserRecord)).one()
        user.is_active = False
        session.add(user)
        session.commit()
    assert bare_client.post("/api/auth/demo").status_code == 401
    assert bare_client.get("/api/auth/me", headers=bearer(response)).status_code == 401


def test_email_uniqueness_normalization_and_password_salts(bare_client, identity):
    _, credentials = identity
    mixed_case = LoginRequest(
        email="  RESEARCHER@EXAMPLE.INVALID  ", password=credentials.password
    )
    assert login(bare_client, mixed_case).status_code == 200
    with Session(db.engine) as session:
        with pytest.raises(ValueError, match="already exists"):
            auth.create_user(session, mixed_case)
    secret = credentials.password.get_secret_value()
    first, second = auth.hash_password(secret), auth.hash_password(secret)
    assert first != second
    assert auth.verify_password(secret, first)
    assert auth.verify_password(secret, second)
    assert not auth.verify_password(secrets.token_urlsafe(24), first)
    assert not auth.verify_password(secret, None)
    assert not auth.verify_password(secret, "broken")
    assert not auth.verify_password(secret, "scrypt-v1$00$00")


def test_unicode_password_and_spaces_are_preserved(bare_client):
    credentials = LoginRequest(
        email="unicode@example.invalid",
        password="  密码 " + secrets.token_urlsafe(24) + "  ",
    )
    with Session(db.engine) as session:
        auth.create_user(session, credentials)
    assert login(bare_client, credentials).status_code == 200
    trimmed = LoginRequest(
        email=credentials.email,
        password=credentials.password.get_secret_value().strip(),
    )
    assert login(bare_client, trimmed).status_code == 401


def test_provisioning_rejects_weak_password_and_reserved_identity(bare_client):
    with Session(db.engine) as session:
        with pytest.raises(ValueError, match="15 and 1024"):
            auth.create_user(
                session,
                LoginRequest(
                    email="user@example.invalid", password=secrets.token_urlsafe(6)
                ),
            )
        with pytest.raises(ValueError, match="reserved"):
            auth.create_user(
                session,
                LoginRequest(email=auth.DEMO_EMAIL, password=secrets.token_urlsafe(24)),
            )
        assert session.exec(select(db.UserRecord)).all() == []
    with pytest.raises(ValidationError):
        LoginRequest(email="user@example.invalid", password=secrets.token_urlsafe(800))


def test_additive_schema_keeps_legacy_profiles(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE client_profiles (id INTEGER PRIMARY KEY, user_id VARCHAR, "
                "name VARCHAR NOT NULL, age INTEGER NOT NULL, risk_level VARCHAR NOT NULL, "
                "created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL, data JSON)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO client_profiles VALUES "
                "(1, NULL, 'Fictional profile', 30, '', '', '', '{}')"
            )
        )
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    db.init_db()
    db.init_db()
    with Session(engine) as session:
        profile = session.get(db.ProfileRecord, 1)
        assert profile.name == "Fictional profile"
        assert profile.user_id is None
        assert profile.data == {}
        assert session.exec(select(db.UserRecord)).all() == []
        assert session.exec(select(db.AuthSessionRecord)).all() == []


def test_openapi_marks_identity_endpoints_and_legacy_routes_keep_contract(bare_client):
    spec = bare_client.get("/openapi.json").json()
    assert spec["paths"]["/api/auth/me"]["get"]["security"] == [{"SessionBearer": []}]
    assert spec["paths"]["/api/auth/logout"]["post"]["security"] == [
        {"SessionBearer": []}
    ]
    assert "security" not in spec["paths"]["/api/auth/login"]["post"]
    assert bare_client.get("/api/health").status_code == 200
    assert bare_client.get("/api/profiles").status_code == 200
    assert bare_client.post("/api/profiles", json={}).status_code == 422


def test_cli_provisions_user_without_printing_credentials(
    bare_client, monkeypatch, capsys
):
    secret = secrets.token_urlsafe(24)
    monkeypatch.setattr("builtins.input", lambda _: "local@example.invalid")
    monkeypatch.setattr(provision.getpass, "getpass", lambda _: secret)
    assert provision.main() == 0
    assert provision.main() == 1  # duplicate email, safe error
    output = capsys.readouterr()
    assert "User created." in output.out
    assert "already exists" in output.err
    assert secret not in output.out + output.err
    assert "local@example.invalid" not in output.out + output.err
    assert (
        login(
            bare_client, LoginRequest(email="local@example.invalid", password=secret)
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "failure", ["mismatch", "email", "weak", "terminal", "database"]
)
def test_cli_failures_do_not_leak_secrets(bare_client, monkeypatch, capsys, failure):
    secret = secrets.token_urlsafe(24)
    monkeypatch.setattr(
        "builtins.input",
        lambda _: "broken" if failure == "email" else "local@example.invalid",
    )
    answers = iter(
        [secret, secrets.token_urlsafe(24) if failure == "mismatch" else secret]
    )
    monkeypatch.setattr(provision.getpass, "getpass", lambda _: next(answers))
    if failure == "weak":
        weak = secrets.token_urlsafe(2)
        monkeypatch.setattr(provision.getpass, "getpass", lambda _: weak)
    if failure == "terminal":

        def no_terminal(_):
            raise provision.getpass.GetPassWarning()

        monkeypatch.setattr(provision.getpass, "getpass", no_terminal)
    if failure == "database":

        def broken_db():
            raise SQLAlchemyError(secret)

        monkeypatch.setattr(db, "init_db", broken_db)
    assert provision.main() == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    with Session(db.engine) as session:
        assert session.exec(select(db.UserRecord)).all() == []

"""Password authentication and revocable, database-backed bearer sessions.

This module resolves identity. It does not grant access to any business object.
Routes opt in through get_current_principal; RBAC follows in #74/#75.
"""

import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import case, delete, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.db import AuthSessionRecord, UserRecord, get_session
from api.i18n import get_request_locale, msg
from api.schemas import LoginRequest, LoginResponse, Principal
from src.agents.demo_mode import is_demo_mode

SESSION_SECONDS = 12 * 60 * 60
MAX_FAILED_LOGINS = 5
LOCK_SECONDS = 5 * 60
DEMO_EMAIL = "demo@wealthpilot.invalid"

# OWASP scrypt baseline, encoded with a version for future migrations.
# Bound simultaneous KDF memory use (128 MiB each) within each API process.
_KDF_SLOTS = threading.BoundedSemaphore(2)
_HASH_PREFIX = "scrypt-v1"
_DUMMY_SALT = secrets.token_bytes(16)
_DUMMY_DIGEST = secrets.token_bytes(32)
_bearer = HTTPBearer(auto_error=False, scheme_name="SessionBearer")


class PasswordHashBusy(RuntimeError):
    """The process has no spare password-hashing capacity; callers may retry."""


def _derive(password: str, salt: bytes) -> bytes:
    # Sync routes already hold an AnyIO worker token. Never queue here: waiting
    # for a KDF slot could occupy every worker and starve unrelated API routes.
    if not _KDF_SLOTS.acquire(blocking=False):
        raise PasswordHashBusy
    try:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**17,
            r=8,
            p=1,
            maxmem=256 * 1024 * 1024,
            dklen=32,
        )
    finally:
        _KDF_SLOTS.release()


def hash_password(password: str) -> str:
    if not 15 <= len(password) <= 1024:
        raise ValueError("Password must contain between 15 and 1024 characters.")
    salt = secrets.token_bytes(16)
    return f"{_HASH_PREFIX}${salt.hex()}${_derive(password, salt).hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    # Unknown, disabled and passwordless users still perform the same KDF.
    salt, expected, valid = _DUMMY_SALT, _DUMMY_DIGEST, False
    if encoded:
        try:
            version, raw_salt, raw_digest = encoded.split("$")
            candidate_salt, candidate_digest = (
                bytes.fromhex(raw_salt),
                bytes.fromhex(raw_digest),
            )
            if (
                version == _HASH_PREFIX
                and len(candidate_salt) == 16
                and len(candidate_digest) == 32
            ):
                salt, expected, valid = candidate_salt, candidate_digest, True
        except ValueError:
            pass
    actual = _derive(password, salt)
    return hmac.compare_digest(actual, expected) and valid


def create_user(session: Session, credentials: LoginRequest) -> UserRecord:
    """Local provisioning only. Never accept role/ownership from credentials."""
    if credentials.email == DEMO_EMAIL:
        raise ValueError("This identifier is reserved for demo authentication.")
    user = UserRecord(
        email=credentials.email,
        password_hash=hash_password(credentials.password.get_secret_value()),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ValueError("A user with this identifier already exists.") from None
    session.refresh(user)
    return user


def authentication_error(locale: str, key: str = "required") -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=msg(f"auth.{key}", locale),
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )


def authenticate_password(
    session: Session, credentials: LoginRequest, locale: str
) -> UserRecord:
    user = session.exec(
        select(UserRecord).where(UserRecord.email == credentials.email)
    ).first()
    try:
        correct = verify_password(
            credentials.password.get_secret_value(),
            user.password_hash if user else None,
        )
    except PasswordHashBusy:
        raise HTTPException(
            status_code=503,
            detail=msg("auth.busy", locale),
            headers={"Retry-After": "1", "Cache-Control": "no-store"},
        ) from None
    now = int(time.time())
    if not user or not user.is_active or user.is_demo or user.locked_until > now:
        raise authentication_error(locale, "invalid_login")
    if not correct:
        # Increment in SQL so simultaneous failed logins cannot lose updates.
        # After a cooldown, the next failure starts a new attempt window.
        attempts = case(
            (UserRecord.locked_until > 0, 1), else_=UserRecord.failed_logins + 1
        )
        session.execute(
            update(UserRecord)
            .where(UserRecord.id == user.id, UserRecord.locked_until <= now)
            .values(
                failed_logins=attempts,
                locked_until=case(
                    (attempts >= MAX_FAILED_LOGINS, now + LOCK_SECONDS), else_=0
                ),
            )
        )
        session.commit()
        raise authentication_error(locale, "invalid_login")
    result = session.execute(
        update(UserRecord)
        .where(
            UserRecord.id == user.id,
            UserRecord.is_active.is_(True),
            UserRecord.locked_until <= now,
        )
        .values(failed_logins=0, locked_until=0)
    )
    session.commit()
    if not result.rowcount:
        raise authentication_error(locale, "invalid_login")
    return user


def demo_user(session: Session, locale: str) -> UserRecord:
    if not is_demo_mode():
        raise HTTPException(
            status_code=404,
            detail=msg("auth.demo_unavailable", locale),
            headers={"Cache-Control": "no-store"},
        )
    user = session.exec(
        select(UserRecord).where(UserRecord.email == DEMO_EMAIL)
    ).first()
    if user is None:
        user = UserRecord(email=DEMO_EMAIL, is_demo=True)
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            # Concurrent demo logins must converge on the same persisted user.
            session.rollback()
            user = session.exec(
                select(UserRecord).where(UserRecord.email == DEMO_EMAIL)
            ).one()
    if not user.is_demo or not user.is_active:
        raise authentication_error(locale)
    return user


def issue_session(session: Session, user: UserRecord) -> LoginResponse:
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    session.execute(
        delete(AuthSessionRecord).where(AuthSessionRecord.expires_at <= now)
    )
    session.add(
        AuthSessionRecord(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            user_id=user.id,
            created_at=now,
            expires_at=now + SESSION_SECONDS,
        )
    )
    session.commit()
    return LoginResponse(
        access_token=token,
        expires_at=datetime.fromtimestamp(now + SESSION_SECONDS, tz=timezone.utc),
    )


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
    locale: str = Depends(get_request_locale),
) -> AuthSessionRecord:
    if credentials is None or len(credentials.credentials) != 43:
        raise authentication_error(locale)
    record = session.get(
        AuthSessionRecord,
        hashlib.sha256(credentials.credentials.encode()).hexdigest(),
    )
    if record is None or record.expires_at <= int(time.time()):
        raise authentication_error(locale)
    user = session.get(UserRecord, record.user_id)
    # These flags suspend authentication without deleting sessions. Re-enabling
    # an account/demo mode can restore unexpired tokens; this is not revocation.
    if not user or not user.is_active or (user.is_demo and not is_demo_mode()):
        raise authentication_error(locale)
    return record


def get_current_principal(
    record: AuthSessionRecord = Depends(get_current_session),
    session: Session = Depends(get_session),
    locale: str = Depends(get_request_locale),
) -> Principal:
    user = session.get(UserRecord, record.user_id)
    if user is None:
        raise authentication_error(locale)
    return Principal(user_id=user.id, email=user.email, is_demo=user.is_demo)

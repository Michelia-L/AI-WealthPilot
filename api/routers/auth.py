"""Identity endpoints; existing business routes adopt authorization in #75."""

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session

from api.auth import (
    authenticate_password,
    demo_user,
    get_current_principal,
    get_current_session,
    issue_session,
)
from api.db import AuthSessionRecord, get_session
from api.i18n import get_request_locale
from api.schemas import LoginRequest, LoginResponse, Principal

router = APIRouter(prefix="/auth", tags=["identity"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
    locale: str = Depends(get_request_locale),
) -> LoginResponse:
    user = authenticate_password(session, body, locale)
    response.headers["Cache-Control"] = "no-store"
    return issue_session(session, user)


@router.post("/demo", response_model=LoginResponse)
def login_demo(
    response: Response,
    session: Session = Depends(get_session),
    locale: str = Depends(get_request_locale),
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    return issue_session(session, demo_user(session, locale))


@router.get("/me", response_model=Principal)
def current_identity(
    response: Response, principal: Principal = Depends(get_current_principal)
) -> Principal:
    response.headers["Cache-Control"] = "no-store"
    return principal


@router.post("/logout", status_code=204)
def logout(
    record: AuthSessionRecord = Depends(get_current_session),
    session: Session = Depends(get_session),
) -> Response:
    session.delete(record)
    session.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})

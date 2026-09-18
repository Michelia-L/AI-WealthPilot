"""Identity and workspace discovery endpoints."""

from fastapi import APIRouter, Depends, Response
from sqlmodel import Session, select

from api.auth import (
    authenticate_password,
    demo_user,
    get_current_principal,
    get_current_session,
    issue_session,
)
from api.db import (
    AuthSessionRecord,
    OrganizationMembershipRecord,
    OrganizationRecord,
    get_session,
)
from api.i18n import get_request_locale
from api.schemas import (
    LoginRequest,
    LoginResponse,
    OrganizationsResponse,
    OrganizationSummary,
    Principal,
)

router = APIRouter(prefix="/auth", tags=["identity"])


@router.post(
    "/login", response_model=LoginResponse, openapi_extra={"x-access-scope": "public"}
)
def login(
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
    locale: str = Depends(get_request_locale),
) -> LoginResponse:
    user = authenticate_password(session, body, locale)
    response.headers["Cache-Control"] = "no-store"
    return issue_session(session, user)


@router.post(
    "/demo", response_model=LoginResponse, openapi_extra={"x-access-scope": "public"}
)
def login_demo(
    response: Response,
    session: Session = Depends(get_session),
    locale: str = Depends(get_request_locale),
) -> LoginResponse:
    response.headers["Cache-Control"] = "no-store"
    return issue_session(session, demo_user(session, locale))


@router.get(
    "/me", response_model=Principal, openapi_extra={"x-access-scope": "authenticated"}
)
def current_identity(
    response: Response, principal: Principal = Depends(get_current_principal)
) -> Principal:
    response.headers["Cache-Control"] = "no-store"
    return principal


@router.post(
    "/logout", status_code=204, openapi_extra={"x-access-scope": "authenticated"}
)
def logout(
    record: AuthSessionRecord = Depends(get_current_session),
    session: Session = Depends(get_session),
) -> Response:
    session.delete(record)
    session.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get(
    "/organizations",
    response_model=OrganizationsResponse,
    openapi_extra={"x-access-scope": "authenticated"},
)
def organizations(
    response: Response,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> OrganizationsResponse:
    response.headers["Cache-Control"] = "no-store"
    rows = session.exec(
        select(OrganizationRecord, OrganizationMembershipRecord.role)
        .join(OrganizationMembershipRecord)
        .where(OrganizationMembershipRecord.user_id == principal.user_id)
    ).all()
    return OrganizationsResponse(
        organizations=[
            OrganizationSummary(id=org.id, name=org.name, role=role)
            for org, role in rows
            if not principal.is_demo or org.id == "demo"
        ]
    )

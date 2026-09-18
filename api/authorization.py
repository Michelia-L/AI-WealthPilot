"""Organization-scoped authorization and advisor assignment services.

Callers obtain Principal from get_current_principal and supply an explicit
organization scope. Neither a submitted user ID nor a role header is a
principal. All decisions read current database state; no global/admin bypass.
Services flush writes but leave commit/rollback to the caller.
"""

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from api.auth import authentication_error
from api.db import (
    AdvisorClientAssignmentRecord,
    ClientRecord,
    MembershipRole,
    OrganizationMembershipRecord,
    UserRecord,
)
from api.i18n import msg
from api.schemas import Principal
from src.agents.demo_mode import is_demo_mode


def _error(status: int, key: str, locale: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=msg(f"authorization.{key}", locale),
        headers={"Cache-Control": "no-store"},
    )


def _current_role(
    session: Session, principal: Principal | None, organization_id: str, locale: str
) -> str | None:
    if principal is None:
        raise authentication_error(locale)
    # Scalar queries avoid stale ORM identity-map values in reused sessions.
    user = session.exec(
        select(UserRecord.is_active, UserRecord.is_demo).where(
            UserRecord.id == principal.user_id
        )
    ).first()
    if user is None or not user.is_active or (user.is_demo and not is_demo_mode()):
        raise authentication_error(locale)
    return session.exec(
        select(OrganizationMembershipRecord.role).where(
            OrganizationMembershipRecord.organization_id == organization_id,
            OrganizationMembershipRecord.user_id == principal.user_id,
        )
    ).first()


def _require_role(
    session: Session,
    principal: Principal,
    organization_id: str,
    role: MembershipRole,
    locale: str,
) -> None:
    if _current_role(session, principal, organization_id, locale) != role:
        raise _error(403, "forbidden", locale)


def require_client(
    session: Session, principal: Principal, organization_id: str, *, locale: str = "en"
) -> None:
    """Require the client role in this organization; not an object-access check."""
    _require_role(session, principal, organization_id, MembershipRole.CLIENT, locale)


def require_advisor(
    session: Session, principal: Principal, organization_id: str, *, locale: str = "en"
) -> None:
    """Require the advisor role; assignments must still be checked per client."""
    _require_role(session, principal, organization_id, MembershipRole.ADVISOR, locale)


def require_org_admin(
    session: Session, principal: Principal, organization_id: str, *, locale: str = "en"
) -> None:
    """Require admin membership in the explicit organization, never globally."""
    _require_role(session, principal, organization_id, MembershipRole.ADMIN, locale)


def authorized_clients_statement(
    session: Session,
    principal: Principal,
    organization_id: str,
    *,
    locale: str = "en",
):
    """One query scope shared by single-object checks and collection filtering."""
    role = _current_role(session, principal, organization_id, locale)
    statement = select(ClientRecord).where(
        ClientRecord.organization_id == organization_id
    )
    if role == MembershipRole.CLIENT:
        statement = statement.where(ClientRecord.user_id == principal.user_id)
    elif role == MembershipRole.ADVISOR:
        statement = statement.where(
            select(AdvisorClientAssignmentRecord.id)
            .where(
                AdvisorClientAssignmentRecord.organization_id == organization_id,
                AdvisorClientAssignmentRecord.advisor_user_id == principal.user_id,
                AdvisorClientAssignmentRecord.client_id == ClientRecord.id,
            )
            .exists()
        )
    elif role != MembershipRole.ADMIN:
        raise _error(404, "client_not_found", locale)
    return statement


def get_authorized_client(
    session: Session,
    principal: Principal,
    organization_id: str,
    client_id: str,
    *,
    locale: str = "en",
) -> ClientRecord:
    """Return an accessible Client; missing and forbidden objects share 404."""
    statement = authorized_clients_statement(
        session, principal, organization_id, locale=locale
    ).where(ClientRecord.id == client_id)
    client = session.exec(statement.execution_options(populate_existing=True)).first()
    if client is None:
        raise _error(404, "client_not_found", locale)
    return client


def assign_advisor(
    session: Session,
    principal: Principal,
    organization_id: str,
    advisor_user_id: str,
    client_id: str,
    *,
    locale: str = "en",
) -> AdvisorClientAssignmentRecord:
    """An organization admin may assign an active advisor; repeated calls reuse it."""
    require_org_admin(session, principal, organization_id, locale=locale)
    get_authorized_client(session, principal, organization_id, client_id, locale=locale)
    advisor = session.exec(
        select(UserRecord.id)
        .join(OrganizationMembershipRecord)
        .where(
            UserRecord.id == advisor_user_id,
            UserRecord.is_active.is_(True),
            (UserRecord.is_demo.is_(False) | is_demo_mode()),
            OrganizationMembershipRecord.organization_id == organization_id,
            OrganizationMembershipRecord.role == MembershipRole.ADVISOR,
        )
    ).first()
    if advisor is None:
        raise _error(422, "advisor_required", locale)
    assignment = AdvisorClientAssignmentRecord(
        organization_id=organization_id,
        advisor_user_id=advisor_user_id,
        client_id=client_id,
    )
    session.execute(
        insert(AdvisorClientAssignmentRecord)
        .values(**assignment.model_dump())
        .on_conflict_do_nothing(
            index_elements=["organization_id", "advisor_user_id", "client_id"]
        )
    )
    return session.exec(
        select(AdvisorClientAssignmentRecord).where(
            AdvisorClientAssignmentRecord.organization_id == organization_id,
            AdvisorClientAssignmentRecord.advisor_user_id == advisor_user_id,
            AdvisorClientAssignmentRecord.client_id == client_id,
        )
    ).one()


def unassign_advisor(
    session: Session,
    principal: Principal,
    organization_id: str,
    advisor_user_id: str,
    client_id: str,
    *,
    locale: str = "en",
) -> None:
    """Idempotent admin revocation, including assignments to demoted advisors."""
    require_org_admin(session, principal, organization_id, locale=locale)
    session.execute(
        delete(AdvisorClientAssignmentRecord).where(
            AdvisorClientAssignmentRecord.organization_id == organization_id,
            AdvisorClientAssignmentRecord.advisor_user_id == advisor_user_id,
            AdvisorClientAssignmentRecord.client_id == client_id,
        )
    )

"""Resolve a unique client from the authenticated identity, never request IDs."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from api.auth import get_current_principal
from api.db import (
    ClientRecord,
    DocumentRecord,
    OrganizationMembershipRecord,
    ProfileRecord,
    get_session,
)
from api.documents import VISIBLE_STATUSES
from api.i18n import get_request_locale, msg
from api.schemas import Principal


@dataclass
class ClientAccess:
    session: Session
    principal: Principal
    client: ClientRecord
    locale: str

    def profile(self) -> ProfileRecord:
        profile = self.session.exec(
            select(ProfileRecord).where(ProfileRecord.client_id == self.client.id)
        ).first()
        if profile is None:
            raise HTTPException(
                404, msg("authorization.profile_not_found", self.locale)
            )
        return profile

    def reports(self):
        return select(DocumentRecord).where(
            DocumentRecord.client_id == self.client.id,
            DocumentRecord.organization_id == self.client.organization_id,
            DocumentRecord.status.in_(VISIBLE_STATUSES),
        )

    def report(self, report_id: str) -> DocumentRecord:
        record = self.session.exec(
            self.reports().where(DocumentRecord.id == report_id)
        ).first()
        if record is None:
            raise HTTPException(404, msg("authorization.report_not_found", self.locale))
        return record


def client_access(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> ClientAccess:
    locale = get_request_locale(request)
    statement = (
        select(ClientRecord)
        .join(
            OrganizationMembershipRecord,
            OrganizationMembershipRecord.organization_id
            == ClientRecord.organization_id,
        )
        .where(
            ClientRecord.user_id == principal.user_id,
            OrganizationMembershipRecord.user_id == principal.user_id,
            OrganizationMembershipRecord.role == "client",
        )
    )
    if principal.is_demo:
        statement = statement.where(ClientRecord.organization_id == "demo")
    clients = session.exec(statement.limit(2)).all()
    if not clients:
        raise HTTPException(404, msg("authorization.client_not_found", locale))
    if len(clients) != 1:
        # Do not guess or let a supplied organization header choose an identity.
        raise HTTPException(409, msg("client.ambiguous", locale))
    return ClientAccess(session, principal, clients[0], locale)

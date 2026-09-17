"""Request-scoped access to existing workstation APIs. No anonymous fallback."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from api.auth import get_current_principal
from api.authorization import authorized_clients_statement
from api.db import (
    ClientRecord,
    OrganizationMembershipRecord,
    ProfileRecord,
    TaskRecord,
    get_session,
)
from api.i18n import get_request_locale, msg
from api.ownership import LOCAL_ORGANIZATION_ID
from api.schemas import Principal


@dataclass
class Access:
    session: Session
    principal: Principal
    organization_id: str
    role: str
    locale: str

    def deny(self, status: int = 403, key: str = "forbidden") -> None:
        raise HTTPException(
            status,
            msg(f"authorization.{key}", self.locale),
            headers={"Cache-Control": "no-store"},
        )

    def staff(self) -> None:
        if self.role not in ("advisor", "admin"):
            self.deny()

    def admin(self) -> None:
        if self.role != "admin":
            self.deny()

    def client_ids(self):
        return authorized_clients_statement(
            self.session, self.principal, self.organization_id, locale=self.locale
        ).with_only_columns(ClientRecord.id)

    def profile(self, profile_id: int) -> ProfileRecord:
        record = self.session.exec(
            select(ProfileRecord).where(
                ProfileRecord.id == profile_id,
                ProfileRecord.client_id.in_(self.client_ids()),
            )
        ).first()
        if record is None:
            self.deny(404, "profile_not_found")
        return record

    def ips(self, document_id: str) -> dict:
        from src.agents import ips_storage

        if not document_id or not all(c.isalnum() or c in "_-" for c in document_id):
            self.deny(404, "ips_not_found")
        path = ips_storage.IPS_DIR / f"{document_id}.json"
        if not path.is_file():
            self.deny(404, "ips_not_found")
        try:
            record = ips_storage.load_ips(path)
        except (OSError, ValueError):
            self.deny(404, "ips_not_found")
        if not isinstance(record, dict) or not isinstance(record.get("metadata"), dict):
            self.deny(404, "ips_not_found")
        if not self.owns(record.get("metadata", {}).get("client_id")):
            self.deny(404, "ips_not_found")
        return record

    def owns(self, client_id: str | None) -> bool:
        return bool(
            isinstance(client_id, str)
            and client_id
            and self.session.exec(
                self.client_ids().where(ClientRecord.id == client_id)
            ).first()
        )

    def ips_documents(self) -> list[dict]:
        from src.agents import ips_storage

        return ips_storage.list_ips_documents(
            allowed_client_ids=set(self.session.exec(self.client_ids()).all())
        )

    def task(self, task_id: str, kind: str) -> None:
        import json

        record = self.session.get(TaskRecord, task_id)
        if record is None or record.kind != kind:
            self.deny(404, "task_not_found")
        try:
            meta = json.loads(record.meta_json)
        except (ValueError, TypeError):
            self.deny(404, "task_not_found")
        if not isinstance(meta, dict):
            self.deny(404, "task_not_found")
        if meta.get("organization_id") != self.organization_id:
            self.deny(404, "task_not_found")
        if meta.get("client_id"):
            if not self.owns(meta["client_id"]):
                self.deny(404, "task_not_found")
        elif meta.get("created_by") != self.principal.user_id:
            self.deny(404, "task_not_found")


def get_access(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> Access:
    locale = get_request_locale(request)
    memberships = session.exec(
        select(OrganizationMembershipRecord).where(
            OrganizationMembershipRecord.user_id == principal.user_id
        )
    ).all()
    if principal.is_demo:
        memberships = [m for m in memberships if m.organization_id == "demo"]
    organization_id = request.headers.get("X-Organization-ID")
    if not organization_id and len(memberships) == 1:
        organization_id = memberships[0].organization_id
    membership = next(
        (m for m in memberships if m.organization_id == organization_id), None
    )
    if membership is None or (principal.is_demo and organization_id != "demo"):
        raise HTTPException(
            403,
            msg("authorization.forbidden", locale),
            headers={"Cache-Control": "no-store"},
        )
    return Access(
        session, principal, membership.organization_id, membership.role, locale
    )


def staff_access(access: Access = Depends(get_access)) -> Access:
    access.staff()
    return access


def settings_access(request: Request, access: Access = Depends(get_access)) -> Access:
    access.admin()
    # LLM settings are deployment-global, administered only by the local org.
    if (
        access.principal.is_demo
        and access.organization_id == "demo"
        and request.method == "GET"
    ):
        return access
    if access.organization_id != LOCAL_ORGANIZATION_ID:
        access.deny()
    if access.principal.is_demo and request.method != "GET":
        access.deny()
    return access

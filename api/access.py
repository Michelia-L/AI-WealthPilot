"""Request-scoped access to existing workstation APIs. No anonymous fallback."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from api.auth import get_current_principal
from api.authorization import authorized_clients_statement
from api.db import (
    ArtifactRecord,
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
        from api.artifacts import load_artifact

        owner = self.artifact(document_id, "ips")
        try:
            return load_artifact(owner)
        except (OSError, ValueError, TypeError):
            self.deny(404, "ips_not_found")

    def artifacts(self, kind: str):
        return select(ArtifactRecord).where(
            ArtifactRecord.kind == kind,
            ArtifactRecord.organization_id == self.organization_id,
            ArtifactRecord.client_id.in_(self.client_ids()),
        )

    def artifact(self, resource_id: str, kind: str) -> ArtifactRecord:
        record = self.session.exec(
            self.artifacts(kind).where(
                ArtifactRecord.resource_id == resource_id,
            )
        ).first()
        if record is None:
            self.deny(404, f"{kind}_not_found")
        return record

    def iter_artifacts(self, kind: str):
        from api.artifacts import load_artifact

        # Stream ordered rows in batches; callers stop after enough valid items.
        statement = (
            self.artifacts(kind)
            .order_by(ArtifactRecord.filename.desc())
            .execution_options(yield_per=50)
        )
        rows = self.session.exec(statement)
        try:
            for record in rows:
                try:
                    payload = load_artifact(record)
                except (OSError, ValueError, TypeError):
                    continue
                yield record, payload
        finally:
            rows.close()

    def report(self, report_id: str):
        from api.artifacts import load_artifact

        record = self.artifact(report_id, "report")
        try:
            return load_artifact(record)
        except (OSError, ValueError, TypeError):
            self.deny(404, "report_not_found")

    def report_path(self, report_id: str):
        from api.artifacts import artifact_path, load_artifact

        record = self.artifact(report_id, "report")
        try:
            load_artifact(record)
            return artifact_path(record)
        except (OSError, ValueError, TypeError):
            self.deny(404, "report_not_found")

    def ips_documents(
        self, limit: int = 50, *, include_records: bool = False
    ) -> list[dict]:
        from api.artifacts import artifact_path
        from src.agents.ips_storage import summarize_ips

        documents = []
        if limit <= 0:
            return documents
        for owner, payload in self.iter_artifacts("ips"):
            try:
                summary = summarize_ips(payload, artifact_path(owner))
            except (ValueError, TypeError, AttributeError):
                continue
            if include_records:
                # Internal fleet input; never included in the public list DTO.
                summary["record"] = payload
            documents.append(summary)
            if len(documents) >= limit:
                break
        return documents

    def reports(self, client_name: str | None = None, limit: int = 50) -> list[dict]:
        from src.agents.report_storage import summarize_report

        reports = []
        if limit <= 0:
            return reports
        for _, payload in self.iter_artifacts("report"):
            if client_name and payload.client_name != client_name:
                continue
            reports.append(summarize_report(payload))
            if len(reports) >= limit:
                break
        return reports

    def task(self, task_id: str, kind: str) -> None:
        from sqlalchemy import and_, or_

        record = self.session.exec(
            select(TaskRecord.task_id).where(
                TaskRecord.task_id == task_id,
                TaskRecord.kind == kind,
                TaskRecord.organization_id == self.organization_id,
                or_(
                    TaskRecord.client_id.in_(self.client_ids()),
                    and_(
                        TaskRecord.client_id.is_(None),
                        TaskRecord.created_by == self.principal.user_id,
                    ),
                ),
            )
        ).first()
        if record is None:
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

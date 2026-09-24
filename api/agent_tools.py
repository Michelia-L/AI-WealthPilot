"""Server-bound tool registry. Model arguments never carry authority."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from api import client_views, db
from api.access import Access, get_access
from api.auth import get_current_principal, resolve_session
from api.client_access import ClientAccess, client_access
from api.i18n import get_request_locale, msg
from api.schemas import (
    AgentIpsArguments,
    AgentNoArguments,
    AgentProfileArguments,
    AgentReportArguments,
)
from src.agents.assistant import Persona


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments: type[BaseModel]
    persona: Persona
    roles: frozenset[str]
    scope: Literal["own", "assigned"]


CLIENT_ROLES = frozenset({"client"})
STAFF_ROLES = frozenset({"advisor", "admin"})
TOOL_REGISTRY = (
    ToolDefinition(
        "read_own_profile",
        "Read your basic client profile.",
        AgentNoArguments,
        "client",
        CLIENT_ROLES,
        "own",
    ),
    ToolDefinition(
        "read_own_portfolio",
        "Read your latest published IPS recommendation and target allocation.",
        AgentNoArguments,
        "client",
        CLIENT_ROLES,
        "own",
    ),
    ToolDefinition(
        "read_own_goals",
        "Read your goals; actual progress may be unavailable.",
        AgentNoArguments,
        "client",
        CLIENT_ROLES,
        "own",
    ),
    ToolDefinition(
        "list_own_reports",
        "List your published report versions.",
        AgentNoArguments,
        "client",
        CLIENT_ROLES,
        "own",
    ),
    ToolDefinition(
        "read_own_report",
        "Read one of your published report versions.",
        AgentReportArguments,
        "client",
        CLIENT_ROLES,
        "own",
    ),
    ToolDefinition(
        "list_clients",
        "List authorized client profiles in this workspace.",
        AgentNoArguments,
        "advisor",
        STAFF_ROLES,
        "assigned",
    ),
    ToolDefinition(
        "read_client_profile",
        "Read an authorized client's workstation profile.",
        AgentProfileArguments,
        "advisor",
        STAFF_ROLES,
        "assigned",
    ),
    ToolDefinition(
        "list_ips",
        "List authorized staff IPS artifacts for review.",
        AgentNoArguments,
        "advisor",
        STAFF_ROLES,
        "assigned",
    ),
    ToolDefinition(
        "read_ips",
        "Read an authorized IPS and its machine review for staff research.",
        AgentIpsArguments,
        "advisor",
        STAFF_ROLES,
        "assigned",
    ),
    ToolDefinition(
        "list_advisor_reports",
        "List authorized staff advisory reports.",
        AgentNoArguments,
        "advisor",
        STAFF_ROLES,
        "assigned",
    ),
    ToolDefinition(
        "read_advisor_report",
        "Read an authorized staff advisory report.",
        AgentReportArguments,
        "advisor",
        STAFF_ROLES,
        "assigned",
    ),
)


@dataclass
class AuthorizedAgentTools:
    request: Request = field(repr=False)
    session_hash: str = field(repr=False)
    persona: Persona
    _binding: tuple | None = field(default=None, init=False, repr=False)
    _profiles: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    _artifacts: set[tuple[str, str]] = field(
        default_factory=set, init=False, repr=False
    )
    _reports: set[str] = field(default_factory=set, init=False, repr=False)

    @property
    def locale(self):
        return get_request_locale(self.request)

    def deny(self):
        raise HTTPException(403, msg("authorization.forbidden", self.locale))

    @contextmanager
    def access(self):
        # A new session avoids cached roles, assignments and revoked sessions.
        with Session(db.engine) as session:
            login = resolve_session(session, self.session_hash, self.locale)
            principal = get_current_principal(login, session, self.locale)
            if self.persona == "client":
                access = client_access(self.request, principal, session)
                binding = (
                    principal.user_id,
                    access.client.organization_id,
                    access.client.id,
                )
                for report_id in self._reports:
                    access.report(report_id)
            elif self.persona == "advisor":
                access = get_access(self.request, principal, session)
                access.staff()
                binding = (principal.user_id, access.organization_id, access.role)
                for profile_id, client_id in self._profiles.items():
                    if access.profile(profile_id).client_id != client_id:
                        self.deny()
                for kind, resource_id in self._artifacts:
                    access.artifact(resource_id, kind)
            else:
                self.deny()
            if self._binding is not None and binding != self._binding:
                self.deny()
            self._binding = binding
            yield access

    def authorize(self) -> None:
        # Also called before each provider request and before releasing output.
        with self.access():
            pass

    def admission_identity(self) -> tuple[str, str]:
        """Resolve quota keys through the same authorization as tool execution."""
        with self.access() as access:
            organization_id = (
                access.client.organization_id
                if isinstance(access, ClientAccess)
                else access.organization_id
            )
            return access.principal.user_id, organization_id

    def permitted(self, tool: ToolDefinition, access: Access | ClientAccess) -> bool:
        role = "client" if isinstance(access, ClientAccess) else access.role
        scope = "own" if isinstance(access, ClientAccess) else "assigned"
        return (
            tool.persona == self.persona and role in tool.roles and tool.scope == scope
        )

    def definitions(self) -> list[dict]:
        with self.access() as access:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.arguments.model_json_schema(),
                    },
                }
                for tool in TOOL_REGISTRY
                if self.permitted(tool, access)
            ]

    def invoke(self, name: str, arguments: str) -> dict:
        with self.access() as access:
            tool = next((t for t in TOOL_REGISTRY if t.name == name), None)
            if tool is None or not self.permitted(tool, access):
                self.deny()
            if not isinstance(arguments, str) or len(arguments) > 8000:
                raise HTTPException(422, msg("request.invalid", self.locale))
            try:
                args = tool.arguments.model_validate_json(arguments)
            except ValidationError:
                raise HTTPException(422, msg("request.invalid", self.locale)) from None
            if isinstance(access, ClientAccess):
                return self._client_read(name, args, access)
            return self._staff_read(name, args, access)

    def _client_read(self, name, args, access: ClientAccess) -> dict:
        if name == "read_own_profile":
            value = client_views.profile(access)
        elif name == "read_own_portfolio":
            value = client_views.portfolio(access)
            if value.report_id:
                self._reports.add(value.report_id)
        elif name == "read_own_goals":
            value = client_views.goals(access)
        elif name == "list_own_reports":
            value = client_views.reports(access)
            self._reports.update(r.id for r in value.reports)
        elif name == "read_own_report":
            value = client_views.report_response(access.report(args.report_id))
            self._reports.add(args.report_id)
        else:
            self.deny()
        return value.model_dump(mode="json")

    def _staff_read(self, name, args, access: Access) -> dict:
        if name == "list_clients":
            profiles = access.session.exec(
                select(db.ProfileRecord)
                .where(db.ProfileRecord.client_id.in_(access.client_ids()))
                .order_by(db.ProfileRecord.id)
                .limit(50)
            ).all()
            self._profiles.update({p.id: p.client_id for p in profiles})
            return {"clients": [{"profile_id": p.id, "name": p.name} for p in profiles]}
        if name == "read_client_profile":
            profile = access.profile(args.profile_id)
            self._profiles[profile.id] = profile.client_id
            return {"profile": profile.data}
        if name == "list_ips":
            items = access.ips_documents()
            result = []
            for item in items:
                # Existing summaries use filesystem paths internally; never send
                # those paths to the model or include them in tool results.
                resource_id = Path(item["filepath"]).stem
                self._artifacts.add(("ips", resource_id))
                result.append(
                    {
                        "document_id": resource_id,
                        **{k: v for k, v in item.items() if k != "filepath"},
                    }
                )
            return {"documents": result}
        if name == "read_ips":
            payload = access.ips(args.document_id)
            self._artifacts.add(("ips", args.document_id))
            return {
                "ips": payload.get("ips", {}),
                "audit_trail": payload.get("audit_trail", {}),
            }
        if name == "list_advisor_reports":
            items = access.reports()
            self._artifacts.update(("report", r["report_id"]) for r in items)
            return {
                "reports": [
                    {k: v for k, v in r.items() if k != "filepath"} for r in items
                ]
            }
        if name == "read_advisor_report":
            report = access.report(args.report_id)
            self._artifacts.add(("report", args.report_id))
            return {"content": report.content, "client_name": report.client_name}
        self.deny()

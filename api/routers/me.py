"""Client Portal: identity-derived scope and explicitly allowlisted DTOs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from api import documents
from api.client_access import ClientAccess, client_access
from api.db import (
    AdvisorClientAssignmentRecord,
    DocumentRecord,
    OrganizationMembershipRecord,
    UserRecord,
)
from api.i18n import msg
from api.profile_convert import profile_from_data
from api.schemas import (
    ClientAdvisor,
    ClientAdvisorResponse,
    ClientDocumentContent,
    ClientGoal,
    ClientGoalsResponse,
    ClientIdentityResponse,
    ClientPortfolioResponse,
    ClientProfileResponse,
    ClientReportResponse,
    ClientReportsResponse,
    ClientReportSummary,
    ClientRiskProfileResponse,
)
from src.agents.demo_mode import is_demo_mode

router = APIRouter(prefix="/me", tags=["Client Portal"])
SCOPE = {"x-access-scope": "client-scoped"}


def report_summary(record: DocumentRecord) -> ClientReportSummary:
    return ClientReportSummary(
        id=record.id,
        document_id=record.document_id,
        type=record.type,
        version=record.version,
        title=record.content["title"],
        status=record.status,
        published_at=record.published_at,
        acknowledged_at=record.acknowledged_at,
    )


def report_response(record: DocumentRecord) -> ClientReportResponse:
    return ClientReportResponse(
        **report_summary(record).model_dump(),
        content=ClientDocumentContent.model_validate(record.content),
    )


@router.get("", response_model=ClientIdentityResponse, openapi_extra=SCOPE)
def identity(access: ClientAccess = Depends(client_access)):
    return ClientIdentityResponse(
        user_id=access.principal.user_id,
        email=access.principal.email,
        is_demo=access.principal.is_demo,
    )


@router.get("/profile", response_model=ClientProfileResponse, openapi_extra=SCOPE)
def profile(access: ClientAccess = Depends(client_access)):
    record = access.profile()
    profile = profile_from_data(record.data)
    return ClientProfileResponse(
        name=profile.name,
        age=profile.age,
        marital_status=profile.marital_status,
        dependents=profile.dependents,
        investable_assets=profile.financial.investable_assets,
        total_liabilities=profile.financial.total_liabilities,
        net_worth=profile.financial.net_worth,
        time_horizon_years=profile.time_horizon_years,
        updated_at=record.updated_at,
    )


@router.get("/portfolio", response_model=ClientPortfolioResponse, openapi_extra=SCOPE)
def portfolio(access: ClientAccess = Depends(client_access)):
    record = access.session.exec(
        access.reports()
        .where(DocumentRecord.type == "ips")
        .order_by(
            DocumentRecord.published_at.desc(),
            DocumentRecord.version.desc(),
            DocumentRecord.id,
        )
        .limit(1)
    ).first()
    content = ClientDocumentContent.model_validate(record.content) if record else None
    return ClientPortfolioResponse(
        status="published_plan" if record else "unavailable",
        report_id=record.id if record else None,
        allocation=content.allocation if content else [],
        recommendation=content.recommendation if content else None,
        performance_explanation=msg("client.performance_unavailable", access.locale),
    )


@router.get("/goals", response_model=ClientGoalsResponse, openapi_extra=SCOPE)
def goals(access: ClientAccess = Depends(client_access)):
    profile = profile_from_data(access.profile().data)
    return ClientGoalsResponse(
        goals=[
            ClientGoal(
                name=g.name,
                target_amount=g.target_amount,
                years=g.years,
                priority=g.priority,
            )
            for g in profile.goals
        ],
        progress_explanation=msg("client.progress_unavailable", access.locale),
    )


@router.get(
    "/risk-profile", response_model=ClientRiskProfileResponse, openapi_extra=SCOPE
)
def risk_profile(access: ClientAccess = Depends(client_access)):
    risk = profile_from_data(access.profile().data).risk_profile
    if risk.final_score == 0:
        return ClientRiskProfileResponse(
            assessed=False, explanation=msg("client.risk_unassessed", access.locale)
        )
    # Classification and the ability/willingness rule belong to the domain model.
    level = risk.classify().split(" / ")[1 if access.locale == "zh" else 0]
    return ClientRiskProfileResponse(
        assessed=True,
        level=level,
        explanation=msg("client.risk_explanation", access.locale, level=level),
    )


@router.get("/advisor", response_model=ClientAdvisorResponse, openapi_extra=SCOPE)
def advisor(access: ClientAccess = Depends(client_access)):
    emails = access.session.exec(
        select(UserRecord.email)
        .join(
            AdvisorClientAssignmentRecord,
            AdvisorClientAssignmentRecord.advisor_user_id == UserRecord.id,
        )
        .join(
            OrganizationMembershipRecord,
            (OrganizationMembershipRecord.user_id == UserRecord.id)
            & (
                OrganizationMembershipRecord.organization_id
                == AdvisorClientAssignmentRecord.organization_id
            ),
        )
        .where(
            AdvisorClientAssignmentRecord.organization_id
            == access.client.organization_id,
            AdvisorClientAssignmentRecord.client_id == access.client.id,
            OrganizationMembershipRecord.role == "advisor",
            UserRecord.is_active.is_(True),
            (UserRecord.is_demo.is_(False) | is_demo_mode()),
        )
        .order_by(UserRecord.email)
    ).all()
    return ClientAdvisorResponse(
        advisors=[ClientAdvisor(email=email) for email in emails]
    )


@router.get("/reports", response_model=ClientReportsResponse, openapi_extra=SCOPE)
def reports(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    access: ClientAccess = Depends(client_access),
):
    records = access.session.exec(
        access.reports()
        .order_by(DocumentRecord.published_at.desc(), DocumentRecord.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return ClientReportsResponse(reports=[report_summary(record) for record in records])


@router.get(
    "/reports/{report_id}", response_model=ClientReportResponse, openapi_extra=SCOPE
)
def report(report_id: str, access: ClientAccess = Depends(client_access)):
    return report_response(access.report(report_id))


@router.post(
    "/reports/{report_id}/acknowledge",
    response_model=ClientReportResponse,
    openapi_extra=SCOPE,
)
def acknowledge(report_id: str, access: ClientAccess = Depends(client_access)):
    record = access.report(report_id)
    if record.status == "published":
        try:
            documents.change(
                access.session,
                record,
                "published",
                access.locale,
                status="acknowledged",
                acknowledged_by=access.principal.user_id,
                acknowledged_at=documents.now(),
            )
            access.session.commit()
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            access.session.rollback()
            # A concurrent acknowledgement may have won after this request
            # loaded the published row. Treat that state as the same idempotent
            # success instead of exposing the internal compare-and-set race.
            record = access.report(report_id)
            if record.status != "acknowledged":
                raise
    return report_response(record)

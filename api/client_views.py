"""Allowlisted client projections shared by HTTP endpoints and agent tools."""

from api.client_access import ClientAccess
from api.db import DocumentRecord
from api.i18n import msg
from api.profile_convert import profile_from_data
from api.schemas import (
    ClientDocumentContent,
    ClientGoal,
    ClientGoalsResponse,
    ClientPortfolioResponse,
    ClientProfileResponse,
    ClientReportResponse,
    ClientReportsResponse,
    ClientReportSummary,
)


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


def profile(access: ClientAccess):
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


def portfolio(access: ClientAccess):
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


def goals(access: ClientAccess):
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


def reports(
    access: ClientAccess, limit: int = 50, offset: int = 0
) -> ClientReportsResponse:
    records = access.session.exec(
        access.reports()
        .order_by(DocumentRecord.published_at.desc(), DocumentRecord.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return ClientReportsResponse(reports=[report_summary(record) for record in records])

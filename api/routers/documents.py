"""Advisor publication workflow, separate from generated artifact diagnostics."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from api import documents
from api.access import Access, staff_access
from api.db import DocumentRecord
from api.i18n import msg
from api.schemas import (
    ClientDocumentContent,
    DocumentCreateRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentRevisionRequest,
)

router = APIRouter(
    prefix="/documents",
    tags=["Advisor documents"],
    dependencies=[Depends(staff_access)],
)
SCOPE = {"x-access-scope": "advisor-scoped"}


def get_document(access: Access, document_id: str) -> DocumentRecord:
    record = access.session.exec(
        select(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.organization_id == access.organization_id,
            DocumentRecord.client_id.in_(access.client_ids()),
        )
    ).first()
    if record is None:
        raise HTTPException(404, msg("documents.not_found", access.locale))
    return record


def finish(access: Access, record: DocumentRecord) -> DocumentResponse:
    access.session.commit()
    return documents.document_response(record)


@router.post("", response_model=DocumentResponse, status_code=201, openapi_extra=SCOPE)
def create(payload: DocumentCreateRequest, access: Access = Depends(staff_access)):
    profile = access.profile(payload.profile_id)
    record = documents.create_draft(
        access.session,
        organization_id=access.organization_id,
        client_id=profile.client_id,
        created_by=access.principal.user_id,
        type=payload.type,
        content=payload.content,
    )
    return finish(access, record)


@router.get("", response_model=DocumentListResponse, openapi_extra=SCOPE)
def list_documents(
    profile_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    access: Access = Depends(staff_access),
):
    statement = select(DocumentRecord).where(
        DocumentRecord.organization_id == access.organization_id,
        DocumentRecord.client_id.in_(access.client_ids()),
    )
    if profile_id is not None:
        statement = statement.where(
            DocumentRecord.client_id == access.profile(profile_id).client_id
        )
    records = access.session.exec(
        statement.order_by(DocumentRecord.created_at.desc(), DocumentRecord.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return DocumentListResponse(
        documents=[documents.document_response(r) for r in records]
    )


@router.get("/{document_id}", response_model=DocumentResponse, openapi_extra=SCOPE)
def detail(document_id: str, access: Access = Depends(staff_access)):
    return documents.document_response(get_document(access, document_id))


@router.put("/{document_id}", response_model=DocumentResponse, openapi_extra=SCOPE)
def edit(
    document_id: str,
    content: ClientDocumentContent,
    access: Access = Depends(staff_access),
):
    record = get_document(access, document_id)
    documents.change(
        access.session, record, "draft", access.locale, content=content.model_dump()
    )
    return finish(access, record)


@router.post(
    "/{document_id}/revisions",
    response_model=DocumentResponse,
    status_code=201,
    openapi_extra=SCOPE,
)
def revision(
    document_id: str,
    payload: DocumentRevisionRequest,
    access: Access = Depends(staff_access),
):
    record = documents.revise(
        access.session,
        get_document(access, document_id),
        access.principal.user_id,
        payload.content,
        access.locale,
    )
    return finish(access, record)


@router.post(
    "/{document_id}/submit", response_model=DocumentResponse, openapi_extra=SCOPE
)
def submit(document_id: str, access: Access = Depends(staff_access)):
    record = get_document(access, document_id)
    documents.change(
        access.session,
        record,
        "draft",
        access.locale,
        status="in_review",
        submitted_at=documents.now(),
    )
    return finish(access, record)


@router.post(
    "/{document_id}/approve",
    response_model=DocumentResponse,
    openapi_extra={"x-access-scope": "admin-scoped"},
)
def approve(document_id: str, access: Access = Depends(staff_access)):
    access.admin()
    record = get_document(access, document_id)
    documents.change(
        access.session,
        record,
        "in_review",
        access.locale,
        status="approved",
        reviewed_by=access.principal.user_id,
        approved_by=access.principal.user_id,
        approved_at=documents.now(),
    )
    return finish(access, record)


@router.post(
    "/{document_id}/publish", response_model=DocumentResponse, openapi_extra=SCOPE
)
def publish(document_id: str, access: Access = Depends(staff_access)):
    record = get_document(access, document_id)
    documents.change(
        access.session,
        record,
        "approved",
        access.locale,
        status="published",
        published_by=access.principal.user_id,
        published_at=documents.now(),
    )
    return finish(access, record)

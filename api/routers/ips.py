"""
IPS generation — async tasks with SSE progress (Phase 4b).

POST /generate spawns an in-process asyncio task that runs the src/
LangGraph workflow. Node completions (via ``astream(stream_mode="updates")``)
become progress events published on a per-task asyncio.Queue; GET
/tasks/{id}/events drains that queue as SSE. Per the migration plan there is
no Celery/Redis: tasks execute in-process, but every event is written through
to a TaskRecord row (api/tasks.py) so a finished task's stream can be
replayed after a restart, and the generated IPS is persisted to the src/
JSON store (shared with Streamlit) on success.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api.access import Access, get_access
from api.db import get_session
from api.i18n import get_request_locale, msg
from api.schemas import (
    IpsDetailResponse,
    IpsDocumentSummary,
    IpsGenerateRequest,
    IpsListResponse,
    IpsTaskCreatedResponse,
)
from api.tasks import (
    BackgroundTask,
    TaskRegistry,
    task_events_stream,
)
from src.agents import ips_storage, ips_workflow
from src.agents.advisor import is_api_configured
from src.agents.demo_mode import is_demo_mode, run_demo_ips_task

router = APIRouter(prefix="/ips", tags=["ips"], dependencies=[Depends(get_access)])

# Workflow nodes carrying a bilingual progress label (SSE timeline in the
# UI); the rendered text lives in api.i18n under these message keys.
_NODE_LABEL_KEYS: dict[str, str] = {
    "generate_cme": "ips.node.generate_cme",
    "generate": "ips.node.generate",
    "select_docs": "ips.node.select_docs",
    "review_suitability": "ips.node.review_suitability",
    "review_compliance": "ips.node.review_compliance",
    "review_consistency": "ips.node.review_consistency",
    "validate_saa": "ips.node.validate_saa",
    "revise": "ips.node.revise",
    "finalize": "ips.node.finalize",
}


def node_label(node_name: str, locale: str) -> str:
    """Localized progress label for a workflow node (raw name when unmapped)."""
    key = _NODE_LABEL_KEYS.get(node_name)
    return msg(key, locale) if key else node_name


registry = TaskRegistry()


async def _run_ips_task(
    task: BackgroundTask, profile_data: dict, max_revisions: int, locale: str = "zh"
) -> None:
    """Background coroutine: stream the workflow, push node events, save result."""
    try:
        template = ips_workflow.load_ips_template()
        initial_state = {
            "client_profile_json": json.dumps(
                profile_data, ensure_ascii=False, indent=2
            ),
            "reference_template": template,
            "max_revisions": max_revisions,
            "locale": locale,
        }
        app = ips_workflow.compile_ips_workflow()
        config = {"configurable": {"thread_id": task.task_id}}

        final_state: dict = {}
        async for chunk in app.astream(
            initial_state, config=config, stream_mode="updates"
        ):
            for node_name in chunk:
                await task.publish(
                    {
                        "type": "node",
                        "node": node_name,
                        "label": node_label(node_name, locale),
                    }
                )
            # "updates" yields per-node deltas keyed by node name; nodes return
            # only the keys they change, so merging every delta in order
            # reconstructs the final workflow state.
            for update in chunk.values():
                if isinstance(update, dict):
                    final_state.update(update)

        state = final_state
        error_message = state.get("error_message", "")
        if state.get("final_ips") is None:
            task.status = "failed"
            await task.publish(
                {
                    "type": "error",
                    "message": error_message or msg("ips.workflow_no_ips", locale),
                }
            )
            return

        filepath = ips_storage.save_ips(
            ips_dict=state["final_ips"],
            audit_trail_dict=state.get("audit_trail") or {},
            client_name=task.meta["client_name"],
            profile_id=task.meta.get("profile_id"),
            client_id=task.meta.get("client_id"),
        )
        task.status = "completed"
        await task.publish(
            {
                "type": "done",
                "success": True,
                "document_id": Path(filepath).stem,
                "status": state.get("status", ""),
                "revision_count": state.get("revision_count", 0),
            }
        )
    except ips_workflow.TokenBudgetExceeded as e:
        # Token budget gate (P24): abort with a dedicated localized message
        # instead of the generic generation-failure one.
        task.status = "failed"
        await task.publish(
            {
                "type": "error",
                "message": msg(
                    "ips.token_budget_exceeded", locale, spent=e.spent, budget=e.budget
                ),
            }
        )
    except Exception as e:
        task.status = "failed"
        await task.publish(
            {"type": "error", "message": msg("ips.generation_failed", locale, error=e)}
        )


@router.post(
    "/generate",
    response_model=IpsTaskCreatedResponse,
    status_code=202,
    openapi_extra={"x-access-scope": "advisor-scoped"},
)
async def generate_ips(
    payload: IpsGenerateRequest,
    request: Request,
    session: Session = Depends(get_session),
    access: Access = Depends(get_access),
) -> IpsTaskCreatedResponse:
    access.staff()
    record = access.profile(payload.profile_id)
    locale = get_request_locale(request)
    if not is_api_configured() and not is_demo_mode():
        raise HTTPException(
            status_code=503,
            detail=msg("common.llm_not_configured", locale),
        )

    task = registry.create(
        "ips",
        profile_id=payload.profile_id,
        client_name=record.name,
        client_id=record.client_id,
        organization_id=access.organization_id,
        created_by=access.principal.user_id,
    )
    # Demo mode (P20): replay the recorded fixture workflow instead of LangGraph.
    runner = run_demo_ips_task if is_demo_mode() else _run_ips_task
    asyncio.create_task(runner(task, record.data, payload.max_revisions, locale))
    return IpsTaskCreatedResponse(task_id=task.task_id, profile_id=payload.profile_id)


@router.get(
    "/tasks/{task_id}/events", openapi_extra={"x-access-scope": "advisor-scoped"}
)
async def task_events(
    task_id: str, request: Request, access: Access = Depends(get_access)
) -> StreamingResponse:
    access.staff()
    access.task(task_id, "ips")
    stream = task_events_stream(registry, task_id, get_request_locale(request))
    if stream is None:
        raise HTTPException(
            status_code=404,
            detail=msg("common.task_not_found", get_request_locale(request)),
        )

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# IPS document library (src/ JSON store, shared with Streamlit)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=IpsListResponse,
    openapi_extra={"x-access-scope": "client-scoped"},
)
def list_ips(access: Access = Depends(get_access)) -> IpsListResponse:
    documents = [
        IpsDocumentSummary(
            document_id=Path(d["filepath"]).stem,
            profile_id=d["profile_id"],
            client_name=d["client_name"],
            version=d["version"],
            risk_level=d["risk_level"],
            status=d["status"],
            revision_rounds=d["revision_rounds"],
            saved_at=d["saved_at"],
        )
        for d in access.ips_documents()
    ]
    return IpsListResponse(documents=documents)


@router.get(
    "/{document_id}",
    response_model=IpsDetailResponse,
    openapi_extra={"x-access-scope": "client-scoped"},
)
def get_ips(
    document_id: str, request: Request, access: Access = Depends(get_access)
) -> IpsDetailResponse:
    record = access.ips(document_id)
    locale = get_request_locale(request)
    ips = record.get("ips", {})
    meta = record.get("metadata", {})
    audit = record.get("audit_trail", {})
    return IpsDetailResponse(
        document_id=document_id,
        markdown=ips_storage.export_ips_markdown(
            ips, record.get("audit_trail"), locale=locale
        ),
        metadata=meta,
        client_name=meta.get("client_name", ips.get("client_name", "Unknown")),
        version=ips.get("version", "?"),
        risk_level=ips.get("risk_tolerance", {}).get("overall_risk_level", "?"),
        status=audit.get("final_status", "?"),
        revision_rounds=audit.get("total_rounds", 0),
        saved_at=meta.get("saved_at", ""),
    )


@router.get("/{document_id}/pdf", openapi_extra={"x-access-scope": "client-scoped"})
def get_ips_pdf(
    document_id: str, request: Request, access: Access = Depends(get_access)
) -> Response:
    """Render the stored IPS as a downloadable PDF (src export_ips_pdf).

    The src builder writes to a file path, so we render into a temp dir and
    stream the bytes back. document_id may contain CJK (client names), hence
    the RFC 5987 filename* in Content-Disposition.
    """
    record = access.ips(document_id)
    locale = get_request_locale(request)
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = ips_storage.export_ips_pdf(
            record.get("ips", {}),
            Path(tmpdir) / "ips.pdf",
            record.get("audit_trail"),
            locale=locale,
        )
        pdf_bytes = pdf_path.read_bytes()
    disposition = (
        f"attachment; filename=\"ips.pdf\"; filename*=UTF-8''{quote(document_id)}.pdf"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.get("/{document_id}/export", openapi_extra={"x-access-scope": "client-scoped"})
def export_ips_markdown(
    document_id: str, request: Request, access: Access = Depends(get_access)
) -> Response:
    """Export the stored IPS (with audit trail) as a Markdown download."""
    record = access.ips(document_id)
    locale = get_request_locale(request)
    markdown = ips_storage.export_ips_markdown(
        record.get("ips", {}), record.get("audit_trail"), locale=locale
    )
    disposition = (
        f"attachment; filename=\"ips.md\"; filename*=UTF-8''{quote(document_id)}.md"
    )
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": disposition},
    )

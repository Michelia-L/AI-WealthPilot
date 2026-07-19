"""
IPS generation — async tasks with SSE progress (Phase 4b).

POST /generate spawns an in-process asyncio task that runs the src/
LangGraph workflow. Node completions (via ``astream(stream_mode="updates")``)
become progress events on a per-task asyncio.Queue; GET /tasks/{id}/events
drains that queue as SSE. Per the migration plan there is no Celery/Redis:
tasks are process-local and lost on restart, and the generated IPS is
persisted to the src/ JSON store (shared with Streamlit) on success.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api.db import ProfileRecord, get_session
from api.schemas import (
    IpsDetailResponse,
    IpsDocumentSummary,
    IpsGenerateRequest,
    IpsListResponse,
    IpsTaskCreatedResponse,
)
from api.tasks import BackgroundTask, TaskRegistry, stream_task_events
from src.agents import ips_storage, ips_workflow
from src.agents.advisor import is_api_configured

router = APIRouter(prefix="/ips", tags=["ips"])

# Chinese labels for workflow nodes (progress timeline in the UI).
NODE_LABELS: dict[str, str] = {
    "generate_cme": "生成资本市场预期 (CME)",
    "generate": "生成 IPS 初稿",
    "select_docs": "选择评审参考文档",
    "review_suitability": "评审：适当性",
    "review_compliance": "评审：合规性",
    "review_consistency": "评审：一致性",
    "validate_saa": "量化验证 SAA",
    "revise": "修订 IPS",
    "finalize": "定稿",
}


registry = TaskRegistry()


async def _run_ips_task(task: BackgroundTask, profile_data: dict, max_revisions: int) -> None:
    """Background coroutine: stream the workflow, push node events, save result."""
    try:
        template = ips_workflow.load_ips_template()
        initial_state = {
            "client_profile_json": json.dumps(profile_data, ensure_ascii=False, indent=2),
            "reference_template": template,
            "max_revisions": max_revisions,
        }
        app = ips_workflow.compile_ips_workflow()
        config = {"configurable": {"thread_id": task.task_id}}

        final_state: dict = {}
        async for chunk in app.astream(initial_state, config=config, stream_mode="updates"):
            for node_name in chunk:
                await task.queue.put(
                    {
                        "type": "node",
                        "node": node_name,
                        "label": NODE_LABELS.get(node_name, node_name),
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
            await task.queue.put(
                {
                    "type": "error",
                    "message": error_message or "工作流未产出 IPS（可能被升级人工处理）",
                }
            )
            return

        filepath = ips_storage.save_ips(
            ips_dict=state["final_ips"],
            audit_trail_dict=state.get("audit_trail") or {},
            client_name=task.meta["client_name"],
        )
        task.status = "completed"
        await task.queue.put(
            {
                "type": "done",
                "success": True,
                "document_id": Path(filepath).stem,
                "status": state.get("status", ""),
                "revision_count": state.get("revision_count", 0),
            }
        )
    except Exception as e:
        task.status = "failed"
        await task.queue.put({"type": "error", "message": f"IPS 生成失败: {e}"})


@router.post("/generate", response_model=IpsTaskCreatedResponse, status_code=202)
async def generate_ips(
    payload: IpsGenerateRequest, session: Session = Depends(get_session)
) -> IpsTaskCreatedResponse:
    if not is_api_configured():
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY 未配置，请在 api 服务的 .env 中设置后重启。",
        )
    record = session.get(ProfileRecord, payload.profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"画像不存在（id={payload.profile_id}）")

    task = registry.create(
        "ips", profile_id=payload.profile_id, client_name=record.name
    )
    asyncio.create_task(_run_ips_task(task, record.data, payload.max_revisions))
    return IpsTaskCreatedResponse(task_id=task.task_id, profile_id=payload.profile_id)


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str) -> StreamingResponse:
    task = registry.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在（可能已随服务重启清除）")

    return StreamingResponse(
        stream_task_events(task),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# IPS document library (src/ JSON store, shared with Streamlit)
# ---------------------------------------------------------------------------


def _find_ips_file(document_id: str) -> Optional[Path]:
    """Locate an IPS file by stem; glob keeps lookups inside IPS_DIR."""
    if not all(c.isalnum() or c in "_-" for c in document_id):
        return None
    matches = list(ips_storage.IPS_DIR.glob(f"{document_id}.json"))
    return matches[0] if matches else None


@router.get("", response_model=IpsListResponse)
def list_ips() -> IpsListResponse:
    documents = [
        IpsDocumentSummary(
            document_id=Path(d["filepath"]).stem,
            client_name=d["client_name"],
            version=d["version"],
            risk_level=d["risk_level"],
            status=d["status"],
            revision_rounds=d["revision_rounds"],
            saved_at=d["saved_at"],
        )
        for d in ips_storage.list_ips_documents()
    ]
    return IpsListResponse(documents=documents)


@router.get("/{document_id}", response_model=IpsDetailResponse)
def get_ips(document_id: str) -> IpsDetailResponse:
    filepath = _find_ips_file(document_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    record = ips_storage.load_ips(filepath)
    return IpsDetailResponse(
        document_id=document_id,
        markdown=ips_storage.export_ips_markdown(
            record.get("ips", {}), record.get("audit_trail")
        ),
        metadata=record.get("metadata", {}),
    )


@router.get("/{document_id}/pdf")
def get_ips_pdf(document_id: str) -> Response:
    """Render the stored IPS as a downloadable PDF (src export_ips_pdf).

    The src builder writes to a file path, so we render into a temp dir and
    stream the bytes back. document_id may contain CJK (client names), hence
    the RFC 5987 filename* in Content-Disposition.
    """
    filepath = _find_ips_file(document_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    record = ips_storage.load_ips(filepath)
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = ips_storage.export_ips_pdf(
            record.get("ips", {}),
            Path(tmpdir) / "ips.pdf",
            record.get("audit_trail"),
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

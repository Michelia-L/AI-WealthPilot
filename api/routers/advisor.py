"""
AI Advisor — streaming advisory reports (Phase 4a).

POST /report/stream proxies the src/ streaming generator as Server-Sent
Events: one ``token`` event per LLM chunk, then a terminal ``done`` event
with the AdvisorReport metadata (validation result, token usage). The
sync OpenAI stream runs in Starlette's threadpool via StreamingResponse,
so the event loop stays free.

Reports the user chooses to keep are persisted through src/ report_storage
(the same JSON library the Streamlit app uses — one shared report store).
"""

import json
from dataclasses import asdict
from typing import Any, Generator, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session

from api.db import ProfileRecord, get_session
from api.profile_convert import profile_from_data
from api.schemas import (
    AdvisorStatusResponse,
    AdvisorStreamRequest,
    ReportDetailResponse,
    ReportListResponse,
    ReportSummary,
    SaveReportRequest,
)
from src.agents import report_storage
from src.agents.advisor import (
    AdvisorReport,
    generate_advice_stream,
    is_api_configured,
)
from src.config import DEEPSEEK_MODEL
from src.utils import sanitize_filename

router = APIRouter(prefix="/advisor", tags=["advisor"])


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _event_stream(record: ProfileRecord) -> Generator[str, None, None]:
    """Yield SSE lines: token events, then one terminal done/error event."""
    profile = profile_from_data(record.data)
    holder: list[AdvisorReport] = []

    def _run() -> Generator[str, None, None]:
        report = yield from generate_advice_stream(profile)
        holder.append(report)

    try:
        for text in _run():
            yield _sse({"type": "token", "text": text})
    except Exception as e:  # defensive: src/ generator already swallows API errors
        yield _sse({"type": "error", "message": f"流式生成中断: {e}"})
        return

    if not holder:
        yield _sse({"type": "error", "message": "生成器未返回报告"})
        return
    report = holder[0]
    yield _sse(
        {
            "type": "done",
            "success": report.success,
            "model": report.model,
            "prompt_tokens": report.prompt_tokens,
            "completion_tokens": report.completion_tokens,
            "total_tokens": report.total_tokens,
            "error_message": report.error_message,
        }
    )


@router.get("/status", response_model=AdvisorStatusResponse)
def advisor_status() -> AdvisorStatusResponse:
    return AdvisorStatusResponse(configured=is_api_configured(), model=DEEPSEEK_MODEL)


@router.post("/report/stream")
def stream_report(
    payload: AdvisorStreamRequest, session: Session = Depends(get_session)
) -> StreamingResponse:
    if not is_api_configured():
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY 未配置，请在 api 服务的 .env 中设置后重启。",
        )
    record = session.get(ProfileRecord, payload.profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"画像不存在（id={payload.profile_id}）")

    return StreamingResponse(
        _event_stream(record),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Report library (shared with the Streamlit app's JSON store)
# ---------------------------------------------------------------------------


def _find_report_file(report_id: str):
    """Locate a report file by id; glob keeps lookups inside REPORTS_DIR."""
    if not report_id.replace("_", "").isdigit():
        return None
    matches = list(report_storage.REPORTS_DIR.glob(f"report_*_{report_id}.json"))
    return matches[0] if matches else None


@router.post("/reports", response_model=ReportSummary, status_code=201)
def save_report(payload: SaveReportRequest) -> ReportSummary:
    stored = report_storage.save_report(
        content=payload.content,
        client_name=payload.client_name,
        model=payload.model,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        notes=payload.notes,
    )
    return ReportSummary(
        report_id=stored.report_id,
        client_name=stored.client_name,
        model=stored.model,
        generated_at=stored.generated_at,
        total_tokens=stored.total_tokens,
        has_notes=bool(stored.notes),
    )


@router.get("/reports", response_model=ReportListResponse)
def list_reports(
    client_name: Optional[str] = Query(default=None),
) -> ReportListResponse:
    # Never expose internal filepaths in the API surface.
    reports = [
        ReportSummary(**{k: v for k, v in r.items() if k != "filepath"})
        for r in report_storage.list_reports(client_name=client_name)
    ]
    return ReportListResponse(reports=reports)


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
def get_report(report_id: str) -> ReportDetailResponse:
    filepath = _find_report_file(report_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    report = report_storage.load_report(filepath)
    return ReportDetailResponse(
        report_id=report.report_id,
        client_name=report.client_name,
        model=report.model,
        generated_at=report.generated_at,
        total_tokens=report.total_tokens,
        has_notes=bool(report.notes),
        content=report.content,
        prompt_tokens=report.prompt_tokens,
        completion_tokens=report.completion_tokens,
        notes=report.notes,
    )


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: str) -> None:
    filepath = _find_report_file(report_id)
    if filepath is None or not report_storage.delete_report(filepath):
        raise HTTPException(status_code=404, detail="报告不存在")


_EXPORT_FORMATS = ("html", "markdown", "json")


@router.get("/reports/{report_id}/export")
def export_report_file(
    report_id: str,
    format: str = Query(default="html"),
) -> Response:
    """Export a stored report as a downloadable file (html / markdown / json).

    The HTML/Markdown renderers live in src/ report_storage (letterhead-styled
    standalone document); the JSON variant mirrors the stored record minus
    internal filepaths, which never leave the API surface.
    """
    if format not in _EXPORT_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"format 必须是 {' / '.join(_EXPORT_FORMATS)}",
        )
    filepath = _find_report_file(report_id)
    if filepath is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    report = report_storage.load_report(filepath)

    base = f"report_{sanitize_filename(report.client_name) or 'client'}_{report.report_id}"
    if format == "html":
        body = report_storage.export_report_html(report)
        media_type, ext = "text/html", "html"
    elif format == "markdown":
        body = report_storage.export_report_markdown(report)
        media_type, ext = "text/markdown", "md"
    else:
        data = {
            k: v
            for k, v in asdict(report).items()
            if k not in ("filepath", "profile_filepath")
        }
        body = json.dumps(data, ensure_ascii=False, indent=2)
        media_type, ext = "application/json", "json"

    disposition = (
        f'attachment; filename="{base}.{ext}"; '
        f"filename*=UTF-8''{quote(base)}.{ext}"
    )
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )

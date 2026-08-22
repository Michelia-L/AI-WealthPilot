"""
AI Advisor — streaming advisory reports (Phase 4a).

POST /report/stream proxies the src/ streaming generator as Server-Sent
Events: ``reasoning`` events for reasoner-style thinking chunks and
``token`` events for report content, then a terminal ``done`` event
with the AdvisorReport metadata (validation result, token usage incl.
reasoning_tokens). The
sync OpenAI stream runs in Starlette's threadpool via StreamingResponse,
so the event loop stays free.

Reports the user chooses to keep are persisted through src/ report_storage
(the same JSON library the Streamlit app uses — one shared report store).
"""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Generator, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlmodel import Session

from api.db import ProfileRecord, get_session
from api.i18n import get_request_locale, msg
from api.profile_convert import profile_from_data
from api.schemas import (
    AdvisorStatusResponse,
    AdvisorStreamRequest,
    ReportDetailResponse,
    ReportListResponse,
    ReportSummary,
    SaveReportRequest,
)
from api.tasks import sse
from src.agents import report_storage
from src.agents.advisor import (
    AdvisorReport,
    generate_advice_stream,
    is_api_configured,
)
from src.agents.demo_mode import demo_advice_stream, is_demo_mode
from src.agents.llm_config import get_llm_config
from src.utils import sanitize_filename

router = APIRouter(prefix="/advisor", tags=["advisor"])


def _event_stream(record: ProfileRecord, locale: str) -> Generator[str, None, None]:
    """Yield SSE lines: reasoning/token events, then one terminal done/error event."""
    profile = profile_from_data(record.data)
    holder: list[AdvisorReport] = []

    def _run() -> Generator[str, None, None]:
        # Demo mode (P20): replay the recorded fixture instead of the LLM.
        stream = (
            demo_advice_stream(profile, locale=locale)
            if is_demo_mode()
            else generate_advice_stream(profile, locale=locale)
        )
        report = yield from stream
        holder.append(report)

    runner = _run()
    try:
        for event in runner:
            # Generators yield reasoning/token event dicts; tolerate legacy
            # plain-string streams by wrapping them as token events.
            if not isinstance(event, dict):
                event = {"type": "token", "text": event}
            yield sse(event)
    except Exception as e:  # defensive: src/ generator already swallows API errors
        yield sse(
            {
                "type": "error",
                "message": msg("common.stream_interrupted", locale, error=e),
            }
        )
        return
    finally:
        # Cooperative cancellation (P24): when the client disconnects,
        # Starlette abandons this generator; closing it here propagates
        # through the ``yield from`` delegation (PEP 380) into the src/
        # generator, whose finally clause closes the upstream LLM stream.
        runner.close()

    if not holder:
        yield sse(
            {"type": "error", "message": msg("common.no_report_generated", locale)}
        )
        return
    report = holder[0]
    yield sse(
        {
            "type": "done",
            "success": report.success,
            "model": report.model,
            "prompt_tokens": report.prompt_tokens,
            "completion_tokens": report.completion_tokens,
            "total_tokens": report.total_tokens,
            "reasoning_tokens": report.reasoning_tokens,
            "error_message": report.error_message,
        }
    )


@router.get("/status", response_model=AdvisorStatusResponse)
def advisor_status() -> AdvisorStatusResponse:
    return AdvisorStatusResponse(
        configured=is_api_configured() or is_demo_mode(),
        model=get_llm_config().model,
        demo=is_demo_mode(),
    )


@router.post("/report/stream")
def stream_report(
    payload: AdvisorStreamRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    locale = get_request_locale(request)
    if not is_api_configured() and not is_demo_mode():
        raise HTTPException(
            status_code=503,
            detail=msg("common.llm_not_configured", locale),
        )
    record = session.get(ProfileRecord, payload.profile_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=msg("common.profile_not_found", locale, id=payload.profile_id),
        )

    return StreamingResponse(
        _event_stream(record, locale),
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
def get_report(report_id: str, request: Request) -> ReportDetailResponse:
    filepath = _find_report_file(report_id)
    if filepath is None:
        raise HTTPException(
            status_code=404,
            detail=msg("common.report_not_found", get_request_locale(request)),
        )
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
def delete_report(report_id: str, request: Request) -> None:
    filepath = _find_report_file(report_id)
    if filepath is None or not report_storage.delete_report(filepath):
        raise HTTPException(
            status_code=404,
            detail=msg("common.report_not_found", get_request_locale(request)),
        )


_EXPORT_FORMATS = ("html", "markdown", "json")


def _attachment_disposition(base: str, ext: str) -> str:
    """RFC 5987 Content-Disposition for a download named ``base.ext``.

    The plain filename= fallback travels in a latin-1 HTTP header, so fold
    non-ASCII (e.g. CJK client names) to '?'; the full UTF-8 name is
    carried by the RFC 5987 filename* parameter.
    """
    ascii_base = base.encode("ascii", "replace").decode("ascii")
    return (
        f'attachment; filename="{ascii_base}.{ext}"; '
        f"filename*=UTF-8''{quote(base)}.{ext}"
    )


@router.get("/reports/{report_id}/pdf")
def get_report_pdf(report_id: str, request: Request) -> Response:
    """Render a stored report as a downloadable PDF (src export_report_pdf).

    Same pattern as the IPS pdf endpoint: the src builder writes to a file
    path, so we render into a temp dir and stream the bytes back. Client
    names may contain CJK, hence the RFC 5987 filename* in
    Content-Disposition.
    """
    locale = get_request_locale(request)
    filepath = _find_report_file(report_id)
    if filepath is None:
        raise HTTPException(
            status_code=404, detail=msg("common.report_not_found", locale)
        )
    report = report_storage.load_report(filepath)
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = report_storage.export_report_pdf(
            report, Path(tmpdir) / "report.pdf", locale=locale
        )
        pdf_bytes = pdf_path.read_bytes()
    base = (
        f"report_{sanitize_filename(report.client_name) or 'client'}_{report.report_id}"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _attachment_disposition(base, "pdf")},
    )


@router.get("/reports/{report_id}/export")
def export_report_file(
    report_id: str,
    request: Request,
    format: str = Query(default="html"),
) -> Response:
    """Export a stored report as a downloadable file (html / markdown / json).

    The HTML/Markdown renderers live in src/ report_storage (letterhead-styled
    standalone document); the JSON variant mirrors the stored record minus
    internal filepaths, which never leave the API surface.
    """
    locale = get_request_locale(request)
    if format not in _EXPORT_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=msg(
                "advisor.invalid_export_format",
                locale,
                formats=" / ".join(_EXPORT_FORMATS),
            ),
        )
    filepath = _find_report_file(report_id)
    if filepath is None:
        raise HTTPException(
            status_code=404, detail=msg("common.report_not_found", locale)
        )
    report = report_storage.load_report(filepath)

    base = (
        f"report_{sanitize_filename(report.client_name) or 'client'}_{report.report_id}"
    )
    if format == "html":
        body = report_storage.export_report_html(report, locale=locale)
        media_type, ext = "text/html", "html"
    elif format == "markdown":
        body = report_storage.export_report_markdown(report, locale=locale)
        media_type, ext = "text/markdown", "md"
    else:
        data = {
            k: v
            for k, v in asdict(report).items()
            if k not in ("filepath", "profile_filepath")
        }
        body = json.dumps(data, ensure_ascii=False, indent=2)
        media_type, ext = "application/json", "json"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": _attachment_disposition(base, ext)},
    )

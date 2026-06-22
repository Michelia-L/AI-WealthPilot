"""
AI WealthPilot - Advisory Report Storage Module

Provides persistence for AI-generated advisory reports. Stores reports
as JSON files with metadata and maintains associations with client profiles.

CFA Reference:
- CFA L3: Documentation requirements for client advisory records.
- GIPS: Record-keeping standards for investment performance.
"""

import html
import json
import re
import markdown
import nh3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR, PROJECT_ROOT
from src.utils import sanitize_filename


# Allowlist for sanitizing LLM-generated report content before it is embedded
# in HTML (#8). The `markdown` library with the 'extra' extension passes raw
# HTML through unchanged, so a payload like `<script>` or `<img onerror=...>`
# from the model output would otherwise land verbatim in the report document.
# nh3 drops anything not on this list and any disallowed attributes.
_HTML_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "del", "div", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd",
    "li", "mark", "ol", "p", "pre", "q", "s", "small", "span", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
    "u", "ul",
}

_HTML_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    # Allow inline class/alignment on structural tags (markdown tables etc.)
    # but never event handlers or `style` with script-bearing URLs.
    "th": {"align"}, "td": {"align"}, "col": {"align", "span"},
    "colgroup": {"align", "span"},
    "span": {"class"}, "div": {"class"}, "code": {"class"},
}


def _sanitize_html(html_str: str) -> str:
    """Sanitize Markdown-rendered HTML to a safe allowlist (XSS prevention, #8).

    Strips ``<script>``, ``<iframe>``, event-handler attributes (``onerror`` etc.),
    and ``javascript:`` URLs while preserving formatting tags produced by the
    Markdown renderer.
    """
    return nh3.clean(
        html_str,
        tags=_HTML_ALLOWED_TAGS,
        attributes=_HTML_ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto"},
    )


# ============================================================
# Data Model — Stored Report
# Data Model - Stored Report
# ============================================================

@dataclass
class StoredReport:
    """Represents a stored advisory report with metadata for persistence."""
    # Unique identifier
    report_id: str = ""
    # Associated client name
    client_name: str = ""
    # Associated client profile filepath
    profile_filepath: str = ""
    # Report body (Markdown format)
    content: str = ""
    # AI model used
    model: str = ""
    # Generation timestamp
    generated_at: str = ""
    # Token usage statistics
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Storage filepath
    filepath: str = ""
    # User notes
    notes: str = ""


# ============================================================
# Storage Directory Configuration
# Storage Directory Configuration
# ============================================================

REPORTS_DIR = DATA_DIR / "reports"


def _ensure_reports_dir() -> Path:
    """Ensure the reports directory exists.

    Returns:
        Path: The reports directory path.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def _generate_report_id() -> str:
    """Generate a unique report identifier.

    Returns:
        str: Unique ID string based on timestamp.
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


# ============================================================
# Core CRUD Operations
# Core CRUD Operations
# ============================================================

def save_report(
    content: str,
    client_name: str,
    model: str,
    profile_filepath: Optional[str] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    notes: str = "",
) -> StoredReport:
    """Save an advisory report to JSON file.

    Args:
        content: Report content in Markdown format.
        client_name: Name of the client.
        model: AI model used for generation.
        profile_filepath: Path to associated client profile (optional).
        prompt_tokens: Number of prompt tokens used.
        completion_tokens: Number of completion tokens generated.
        notes: User notes about this report.

    Returns:
        StoredReport: StoredReport instance with filepath set.
    """
    _ensure_reports_dir()

    # Create report instance
    report_id = _generate_report_id()
    safe_name = sanitize_filename(client_name)
    filename = f"report_{safe_name}_{report_id}.json"
    filepath = REPORTS_DIR / filename

    # Convert absolute paths to relative paths before storing to avoid environment leak
    rel_filepath = str(filepath)
    if filepath.is_absolute():
        try:
            rel_filepath = str(filepath.relative_to(PROJECT_ROOT))
        except ValueError:
            pass

    rel_profile_filepath = profile_filepath or ""
    if rel_profile_filepath:
        try:
            p_path = Path(rel_profile_filepath)
            if p_path.is_absolute():
                rel_profile_filepath = str(p_path.relative_to(PROJECT_ROOT))
        except ValueError:
            pass

    report_to_save = StoredReport(
        report_id=report_id,
        client_name=client_name,
        profile_filepath=rel_profile_filepath,
        content=content,
        model=model,
        generated_at=datetime.now().isoformat(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        filepath=rel_filepath,
        notes=notes,
    )

    # Save to file
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(report_to_save), f, indent=2, ensure_ascii=False)

    # Return report with absolute paths for in-memory app consumption
    report_to_return = StoredReport(
        report_id=report_id,
        client_name=client_name,
        profile_filepath=profile_filepath or "",
        content=content,
        model=model,
        generated_at=report_to_save.generated_at,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        filepath=str(filepath),
        notes=notes,
    )
    return report_to_return


def load_report(filepath: Path) -> StoredReport:
    """Load a stored report from JSON file.

    Args:
        filepath: Path to the report JSON file.

    Returns:
        StoredReport: Loaded StoredReport instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    report = StoredReport(**data)
    # Convert relative paths back to absolute paths dynamically for runtime compatibility
    if report.filepath and not Path(report.filepath).is_absolute():
        report.filepath = str(PROJECT_ROOT / report.filepath)
    if report.profile_filepath and not Path(report.profile_filepath).is_absolute():
        if "ClientProfile" not in report.profile_filepath:
            report.profile_filepath = str(PROJECT_ROOT / report.profile_filepath)

    return report


def list_reports(
    client_name: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """List stored advisory reports with optional filtering.

    Args:
        client_name: Filter by client name (optional).
        limit: Maximum number of reports to return.

    Returns:
        list[dict]: List of dicts with report summary info.
    """
    _ensure_reports_dir()

    reports = []
    for filepath in sorted(REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            report = load_report(filepath)

            # Filter by client name
            if client_name and report.client_name != client_name:
                continue

            reports.append({
                "report_id": report.report_id,
                "client_name": report.client_name,
                "model": report.model,
                "generated_at": report.generated_at,
                "total_tokens": report.total_tokens,
                "filepath": report.filepath,
                "has_notes": bool(report.notes),
            })

            if len(reports) >= limit:
                break

        except Exception:
            continue

    return reports


def delete_report(filepath: Path) -> bool:
    """Delete a stored report file.

    Args:
        filepath: Path to the report JSON file.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    try:
        if filepath.exists():
            filepath.unlink()
            return True
        return False
    except Exception:
        return False


# ============================================================
# Report-Profile Association
# Report-Profile Association
# ============================================================

def get_reports_for_profile(profile_filepath: str) -> list[StoredReport]:
    """Get all reports associated with a specific client profile.

    Args:
        profile_filepath: Path to the client profile file.

    Returns:
        list[StoredReport]: List of StoredReport instances linked to the profile.
    """
    _ensure_reports_dir()

    reports = []
    for filepath in REPORTS_DIR.glob("*.json"):
        try:
            report = load_report(filepath)
            if report.profile_filepath == profile_filepath:
                reports.append(report)
        except Exception:
            continue

    return sorted(reports, key=lambda r: r.generated_at, reverse=True)


def update_report_notes(filepath: Path, notes: str) -> bool:
    """Update the notes field of a stored report.

    Args:
        filepath: Path to the report JSON file.
        notes: New notes content.

    Returns:
        bool: True if update was successful, False otherwise.
    """
    try:
        report = load_report(filepath)
        report.notes = notes

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)

        return True
    except Exception:
        return False


# ============================================================
# Export Functions
# Export Functions
# ============================================================

def _markdown_to_html(markdown_text: str) -> str:
    """Convert Markdown text to sanitized HTML.

    The Markdown renderer (with the 'extra' extension) passes raw HTML through
    unchanged, so LLM-generated content could carry `<script>` or event-handler
    payloads. The output is therefore sanitized to a safe tag/attribute
    allowlist before it is embedded in any HTML document (#8).

    Args:
        markdown_text: Markdown formatted text.

    Returns:
        str: Sanitized HTML string safe to embed in a report document.
    """
    rendered = markdown.markdown(
        markdown_text, extensions=['extra', 'nl2br'], output_format='html5'
    )
    return _sanitize_html(rendered)


def export_report_markdown(report: StoredReport) -> str:
    """Export a stored report to formatted Markdown.

    Args:
        report: StoredReport instance to export.

    Returns:
        str: Formatted Markdown string.
    """
    metadata_header = f"""# Investment Advisory Report / 投资咨询建议书

---

**Client / 客户**: {report.client_name}
**Generated / 生成时间**: {report.generated_at}
**AI Model / AI 模型**: {report.model}
**Token Usage / Token 用量**: {report.total_tokens:,}

---

"""
    return metadata_header + report.content


def export_report_html(report: StoredReport) -> str:
    """Export a stored report to formatted HTML.

    Args:
        report: StoredReport instance to export.

    Returns:
        str: Complete HTML document string.
    """
    # Convert content from Markdown to HTML
    content_html = _markdown_to_html(report.content)

    # Escape user-originated fields to prevent XSS
    # Escape user-originated fields to prevent XSS
    safe_client_name = html.escape(report.client_name)
    safe_model = html.escape(report.model)
    safe_report_id = html.escape(report.report_id)
    safe_generated_at = html.escape(report.generated_at)

    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Investment Advisory Report - {safe_client_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* ============================================================
           Formal advisory document — light "official letterhead" brand
           extension of the dark Obsidian & Gold terminal. White ground for
           print/archive fidelity; gold accent + Cinzel serif headings carry
           the heritage weight appropriate to a signed IPS document.
           ============================================================ */
        :root {{
            --gold-1: #f3e7c4;
            --gold-2: #d4af37;
            --gold-3: #aa7c11;
            --ink: #1c1917;
            --ink-soft: #44403c;
            --rule: #e7e5e4;
            --paper: #ffffff;
            --paper-tint: #faf9f7;
        }}
        body {{
            font-family: 'Plus Jakarta Sans', 'Segoe UI', Tahoma, sans-serif;
            line-height: 1.7;
            max-width: 880px;
            margin: 0 auto;
            padding: 48px 40px;
            color: var(--ink);
            background: var(--paper);
            -webkit-font-smoothing: antialiased;
        }}
        .letterhead {{
            border-top: 3px solid var(--gold-2);
            border-bottom: 1px solid var(--rule);
            padding: 28px 0 26px;
            margin-bottom: 36px;
        }}
        .letterhead .brand {{
            font-family: 'Cinzel', serif;
            font-size: 0.95rem;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--gold-3);
            margin-bottom: 10px;
        }}
        .letterhead h1 {{
            font-family: 'Cinzel', serif;
            font-size: 1.9rem;
            font-weight: 700;
            color: var(--ink);
            margin: 0 0 4px;
            letter-spacing: 0.01em;
            line-height: 1.2;
        }}
        .letterhead .doc-sub {{
            font-size: 0.82rem;
            font-weight: 500;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--gold-3);
        }}
        .metadata {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 14px 28px;
            font-size: 0.9rem;
            margin-top: 22px;
            padding-top: 18px;
            border-top: 1px solid var(--rule);
        }}
        .metadata-item {{
            display: flex;
            align-items: baseline;
        }}
        .metadata-label {{
            font-weight: 600;
            min-width: 150px;
            color: var(--gold-3);
            font-size: 0.72rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            margin-right: 12px;
        }}
        .metadata-value {{
            color: var(--ink);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.88rem;
        }}
        .content {{
            padding: 8px 0;
        }}
        h1, h2, h3, h4 {{
            font-family: 'Cinzel', serif;
            color: var(--ink);
            font-weight: 600;
            line-height: 1.3;
        }}
        .content h1 {{ font-size: 1.5rem; border-bottom: 2px solid var(--gold-2); padding-bottom: 10px; margin-top: 36px; }}
        .content h2 {{ font-size: 1.28rem; border-bottom: 1px solid var(--rule); padding-bottom: 8px; margin-top: 30px; }}
        .content h3 {{ font-size: 1.1rem; margin-top: 24px; }}
        .content h4 {{ font-size: 0.98rem; font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 600; }}
        p {{ margin: 12px 0; color: var(--ink-soft); }}
        hr {{
            border: none;
            border-top: 1px solid var(--rule);
            margin: 28px 0;
        }}
        strong {{
            color: var(--ink);
            font-weight: 600;
        }}
        ul, ol {{
            background: var(--paper-tint);
            border-left: 2px solid var(--gold-2);
            padding: 16px 24px 16px 40px;
            border-radius: 0 6px 6px 0;
            margin: 16px 0;
        }}
        li {{ margin-bottom: 8px; color: var(--ink-soft); }}
        li:last-child {{ margin-bottom: 0; }}
        blockquote {{
            border-left: 3px solid var(--gold-2);
            margin: 18px 0;
            padding: 8px 20px;
            color: var(--ink-soft);
            font-style: italic;
            background: var(--paper-tint);
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 18px 0;
            font-size: 0.9rem;
        }}
        th, td {{
            border: 1px solid var(--rule);
            padding: 10px 14px;
            text-align: left;
        }}
        th {{
            background: var(--paper-tint);
            font-weight: 600;
            color: var(--ink);
            border-bottom: 2px solid var(--gold-2);
        }}
        code {{
            font-family: 'JetBrains Mono', monospace;
            background: var(--paper-tint);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.88em;
            color: var(--gold-3);
        }}
        .footer {{
            margin-top: 48px;
            padding-top: 22px;
            border-top: 1px solid var(--rule);
            color: #78716c;
            font-size: 0.78rem;
            line-height: 1.6;
        }}
        .footer .brand-line {{
            font-family: 'Cinzel', serif;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            color: var(--gold-3);
            font-weight: 600;
            margin-bottom: 4px;
        }}
        @media print {{
            body {{ max-width: 100%; padding: 0; font-size: 11pt; }}
            .letterhead {{ border-top: 3px solid var(--gold-2) !important; }}
            ul, ol, blockquote, th {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            a {{ color: var(--ink); text-decoration: none; }}
        }}
    </style>
</head>
<body>
    <header class="letterhead">
        <div class="brand">AI WealthPilot</div>
        <h1>Investment Advisory Report<br>投资咨询建议书</h1>
        <div class="doc-sub">Private Wealth Management · Confidential</div>
        <div class="metadata">
            <div class="metadata-item">
                <span class="metadata-label">Client / 客户</span>
                <span class="metadata-value">{safe_client_name}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Generated / 生成时间</span>
                <span class="metadata-value">{safe_generated_at}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">AI Model / AI 模型</span>
                <span class="metadata-value">{safe_model}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Token Usage / Token 用量</span>
                <span class="metadata-value">{report.total_tokens:,}</span>
            </div>
        </div>
    </header>

    <main class="content">
        {content_html}
    </main>

    <footer class="footer">
        <div class="brand-line">AI WealthPilot</div>
        <p>Report ID: {safe_report_id}</p>
        <p>This report is for informational purposes only and does not constitute financial advice.</p>
        <p>本报告仅供参考，不构成投资建议。</p>
    </footer>
</body>
</html>"""

    return html_template


def export_report_to_file(
    report: StoredReport,
    output_path: Path,
    format: str = "markdown",
) -> Path:
    """Export a report to a standalone file.

    Args:
        report: StoredReport instance to export.
        output_path: Path for the output file.
        format: Export format ('markdown', 'html', or 'json').

    Returns:
        Path: Path to the exported file.

    Raises:
        ValueError: If unsupported format is specified.
    """
    if format == "markdown":
        content = export_report_markdown(report)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    elif format == "html":
        content = export_report_html(report)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    elif format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Unsupported format: {format}")

    return output_path


def get_export_formats() -> list[dict[str, str]]:
    """Get list of supported export formats with descriptions.

    Returns:
        list[dict[str, str]]: List of dicts with export format descriptions.
    """
    return [
        {
            "format": "markdown",
            "extension": ".md",
            "description": "Markdown format for documentation / 用于文档的 Markdown 格式",
        },
        {
            "format": "html",
            "extension": ".html",
            "description": "HTML format — formal letterhead styling for viewing/printing / 正式信纸样式 HTML，适合查看/打印",
        },
        {
            "format": "json",
            "extension": ".json",
            "description": "JSON format with full metadata / 包含完整元数据的 JSON 格式",
        },
    ]

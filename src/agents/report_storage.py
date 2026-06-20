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
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR, PROJECT_ROOT
from src.utils import sanitize_filename


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
    """Convert Markdown text to basic HTML.

    Args:
        markdown_text: Markdown formatted text.

    Returns:
        str: HTML formatted string.
    """
    return markdown.markdown(markdown_text, extensions=['extra', 'nl2br'], output_format='html5')


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
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        .header {{
            background-color: #1a365d;
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 24px;
        }}
        .metadata {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            font-size: 14px;
        }}
        .metadata-item {{
            display: flex;
            align-items: center;
        }}
        .metadata-label {{
            font-weight: bold;
            margin-right: 8px;
            color: #a0aec0;
        }}
        .content {{
            background-color: white;
            padding: 30px;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
        }}
        h1, h2, h3 {{
            color: #1a365d;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 10px;
        }}
        h1 {{ font-size: 28px; }}
        h2 {{ font-size: 22px; }}
        h3 {{ font-size: 18px; }}
        hr {{
            border: none;
            border-top: 1px solid #e2e8f0;
            margin: 20px 0;
        }}
        strong {{
            color: #1a365d;
        }}
        ul {{
            background-color: #f7fafc;
            padding: 20px 40px;
            border-radius: 4px;
        }}
        li {{
            margin-bottom: 8px;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding: 20px;
            color: #718096;
            font-size: 12px;
        }}
        @media print {{
            body {{
                max-width: 100%;
                padding: 0;
            }}
            .header {{
                background-color: #1a365d !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Investment Advisory Report / 投资咨询建议书</h1>
        <div class="metadata">
            <div class="metadata-item">
                <span class="metadata-label">Client / 客户:</span>
                <span>{safe_client_name}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Generated / 生成时间:</span>
                <span>{safe_generated_at}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">AI Model / AI 模型:</span>
                <span>{safe_model}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Token Usage / Token 用量:</span>
                <span>{report.total_tokens:,}</span>
            </div>
        </div>
    </div>

    <div class="content">
        {content_html}
    </div>

    <div class="footer">
        <p>Generated by AI WealthPilot | AI WealthPilot 生成</p>
        <p>Report ID: {safe_report_id}</p>
        <p>This report is for informational purposes only and does not constitute financial advice.</p>
        <p>本报告仅供参考，不构成投资建议。</p>
    </div>
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
            "description": "HTML format with styling for viewing/printing / 用于查看/打印的带样式 HTML 格式",
        },
        {
            "format": "json",
            "extension": ".json",
            "description": "JSON format with full metadata / 包含完整元数据的 JSON 格式",
        },
    ]

"""
AI WealthPilot - Advisory Report Storage Module
AI WealthPilot - 建议书持久化存储模块

Provides persistence for AI-generated advisory reports.
Stores reports as JSON files with metadata and maintains
associations with client profiles.

为 AI 生成的建议书提供持久化存储。
将报告以 JSON 文件形式存储，包含元数据，
并维护与客户画像的关联。

Key Features / 核心功能:
    1. Save advisory reports with full metadata
       保存包含完整元数据的建议书
    2. Load and query stored reports
       加载和查询已存储的报告
    3. Link reports to client profiles
       建立报告与客户画像的关联
    4. Export reports to Markdown, HTML, and JSON formats
       将报告导出为 Markdown、HTML 和 JSON 格式

CFA Reference / CFA 参考:
    - CFA L3: Documentation requirements for client advisory records
      CFA 三级：客户咨询记录的文档要求
    - GIPS: Record-keeping standards for investment performance
      GIPS：投资业绩的记录保存标准
"""

import html
import json
import re
import markdown
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.utils import sanitize_filename


# ============================================================
# Data Model — Stored Report
# 数据模型 —— 存储的建议书
# ============================================================

@dataclass
class StoredReport:
    """
    Represents a stored advisory report with metadata.
    表示包含元数据的已存储建议书。

    This dataclass captures all relevant information about
    a generated advisory report for persistence and retrieval.

    该数据类捕获生成的建议书的所有相关信息，用于持久化和检索。
    """
    # 唯一标识符 / Unique identifier
    report_id: str = ""
    # 关联的客户名称 / Associated client name
    client_name: str = ""
    # 关联的客户画像文件路径 / Associated client profile filepath
    profile_filepath: str = ""
    # 建议书正文（Markdown 格式）/ Report body (Markdown format)
    content: str = ""
    # 使用的 AI 模型 / AI model used
    model: str = ""
    # 生成时间戳 / Generation timestamp
    generated_at: str = ""
    # Token 用量统计 / Token usage statistics
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # 存储文件路径 / Storage filepath
    filepath: str = ""
    # 用户备注 / User notes
    notes: str = ""


# ============================================================
# Storage Directory Configuration
# 存储目录配置
# ============================================================

REPORTS_DIR = DATA_DIR / "reports"


def _ensure_reports_dir() -> Path:
    """
    Ensure the reports directory exists.
    确保报告目录存在。

    Returns:
        Path to the reports directory.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def _generate_report_id() -> str:
    """
    Generate a unique report identifier.
    生成唯一的报告标识符。

    Returns:
        Unique ID string based on timestamp.
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


# ============================================================
# Core CRUD Operations
# 核心增删改查操作
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
    """
    Save an advisory report to JSON file.
    将建议书保存为 JSON 文件。

    Args:
        content: Report content in Markdown format.
                 Markdown 格式的报告内容。
        client_name: Name of the client.
                     客户名称。
        model: AI model used for generation.
               用于生成的 AI 模型。
        profile_filepath: Path to associated client profile (optional).
                          关联的客户画像路径（可选）。
        prompt_tokens: Number of prompt tokens used.
                       使用的提示词 token 数。
        completion_tokens: Number of completion tokens generated.
                           生成的完成 token 数。
        notes: User notes about this report.
               用户对此报告的备注。

    Returns:
        StoredReport instance with filepath set.
        设置了 filepath 的 StoredReport 实例。
    """
    _ensure_reports_dir()

    # 创建报告实例 / Create report instance
    report_id = _generate_report_id()
    safe_name = sanitize_filename(client_name)
    filename = f"report_{safe_name}_{report_id}.json"
    filepath = REPORTS_DIR / filename

    report = StoredReport(
        report_id=report_id,
        client_name=client_name,
        profile_filepath=profile_filepath or "",
        content=content,
        model=model,
        generated_at=datetime.now().isoformat(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        filepath=str(filepath),
        notes=notes,
    )

    # 保存到文件 / Save to file
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)

    return report


def load_report(filepath: Path) -> StoredReport:
    """
    Load a stored report from JSON file.
    从 JSON 文件加载已存储的报告。

    Args:
        filepath: Path to the report JSON file.
                  报告 JSON 文件的路径。

    Returns:
        StoredReport instance.

    Raises:
        FileNotFoundError: If the file does not exist.
                           如果文件不存在。
        json.JSONDecodeError: If the file is not valid JSON.
                              如果文件不是有效的 JSON。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return StoredReport(**data)


def list_reports(
    client_name: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """
    List stored advisory reports with optional filtering.
    列出已存储的建议书，支持可选筛选。

    Args:
        client_name: Filter by client name (optional).
                     按客户名称筛选（可选）。
        limit: Maximum number of reports to return.
               返回的最大报告数量。

    Returns:
        List of dicts with report summary info.
        包含报告摘要信息的字典列表。
    """
    _ensure_reports_dir()

    reports = []
    for filepath in sorted(REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            report = load_report(filepath)

            # 按客户名称筛选 / Filter by client name
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
    """
    Delete a stored report file.
    删除已存储的报告文件。

    Args:
        filepath: Path to the report JSON file.
                  报告 JSON 文件的路径。

    Returns:
        True if deletion was successful, False otherwise.
        删除成功返回 True，否则返回 False。
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
# 报告-画像关联
# ============================================================

def get_reports_for_profile(profile_filepath: str) -> list[StoredReport]:
    """
    Get all reports associated with a specific client profile.
    获取与特定客户画像关联的所有报告。

    Args:
        profile_filepath: Path to the client profile file.
                          客户画像文件路径。

    Returns:
        List of StoredReport instances linked to the profile.
        与该画像关联的 StoredReport 实例列表。
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
    """
    Update the notes field of a stored report.
    更新已存储报告的备注字段。

    Args:
        filepath: Path to the report JSON file.
                  报告 JSON 文件的路径。
        notes: New notes content.
               新的备注内容。

    Returns:
        True if update was successful, False otherwise.
        更新成功返回 True，否则返回 False。
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
# 导出函数
# ============================================================

def _markdown_to_html(markdown_text: str) -> str:
    """
    Convert Markdown text to basic HTML.
    将 Markdown 文本转换为基本 HTML。

    This is a simple converter that handles common Markdown elements.
    For production use, consider using a full Markdown parser like `markdown`.

    这是一个简单的转换器，处理常见的 Markdown 元素。
    在生产环境中，建议使用完整的 Markdown 解析器如 `markdown`。

    Args:
        markdown_text: Markdown formatted text.

    Returns:
        HTML formatted string.
    """
    return markdown.markdown(markdown_text, extensions=['extra', 'nl2br'], output_format='html5')


def export_report_markdown(report: StoredReport) -> str:
    """
    Export a stored report to formatted Markdown.
    将已存储的报告导出为格式化的 Markdown。

    Adds metadata header to the report content for standalone viewing.

    为报告内容添加元数据头部，便于独立查看。

    Args:
        report: StoredReport instance to export.
                要导出的 StoredReport 实例。

    Returns:
        Formatted Markdown string.
        格式化的 Markdown 字符串。
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
    """
    Export a stored report to formatted HTML.
    将已存储的报告导出为格式化的 HTML。

    Creates a standalone HTML document with embedded CSS styling
    suitable for printing or viewing in a browser.

    创建一个独立的 HTML 文档，包含嵌入式 CSS 样式，
    适合打印或在浏览器中查看。

    Args:
        report: StoredReport instance to export.
                要导出的 StoredReport 实例。

    Returns:
        Complete HTML document string.
        完整的 HTML 文档字符串。
    """
    # Convert content from Markdown to HTML / 将内容从 Markdown 转换为 HTML
    content_html = _markdown_to_html(report.content)

    # Escape user-originated fields to prevent XSS
    # 转义用户输入字段以防止 XSS 攻击
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
    """
    Export a report to a standalone file.
    将报告导出为独立文件。

    Supported formats / 支持的格式:
        - 'markdown': Markdown (.md) format
        - 'html': HTML (.html) format with embedded CSS
        - 'json': JSON format with full metadata

    Args:
        report: StoredReport instance to export.
                要导出的 StoredReport 实例。
        output_path: Path for the output file.
                     输出文件的路径。
        format: Export format ('markdown', 'html', or 'json').
                导出格式（'markdown'、'html' 或 'json'）。

    Returns:
        Path to the exported file.
        导出文件的路径。

    Raises:
        ValueError: If unsupported format specified.
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
    """
    Get list of supported export formats with descriptions.
    获取支持的导出格式及其描述。

    Returns:
        List of dicts with 'format', 'extension', and 'description' keys.
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

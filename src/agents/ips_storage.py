"""
AI WealthPilot - IPS Storage & Export Module

Provides persistence and export capabilities for AI-generated
Investment Policy Statements (IPS) and their audit trails.

Key Features:
    1. Save/load IPSDocument + AuditTrail as JSON
    2. Export to professional HTML (print-ready)
    3. Export to Markdown
    4. List and query stored IPS documents

CFA Reference:
    - CFA L3: Documentation and record-keeping requirements
    - GIPS: Record-keeping standards
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.utils import sanitize_filename
from src.agents.ips_models import IPSDocument, AuditTrail


# ============================================================
# Storage Directory
# ============================================================

IPS_DIR = DATA_DIR / "ips"


def _ensure_ips_dir() -> Path:
    """Ensure the IPS storage directory exists."""
    IPS_DIR.mkdir(parents=True, exist_ok=True)
    return IPS_DIR


# ============================================================
# Core CRUD Operations
# ============================================================

def save_ips(
    ips_dict: dict,
    audit_trail_dict: dict,
    client_name: str,
    notes: str = "",
) -> Path:
    """
    Save an IPS document and its audit trail to JSON.

    Args:
        ips_dict: IPSDocument serialized as dict.
        audit_trail_dict: AuditTrail serialized as dict.
        client_name: Client name for filename.
        notes: Optional notes.

    Returns:
        Path to the saved JSON file.
    """
    _ensure_ips_dir()

    safe_name = sanitize_filename(client_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ips_{safe_name}_{timestamp}.json"
    filepath = IPS_DIR / filename

    record = {
        "ips": ips_dict,
        "audit_trail": audit_trail_dict,
        "metadata": {
            "client_name": client_name,
            "saved_at": datetime.now().isoformat(),
            "notes": notes,
        },
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    return filepath


def load_ips(filepath: Path) -> dict:
    """
    Load an IPS record from JSON.

    Args:
        filepath: Path to the IPS JSON file.

    Returns:
        Dict with 'ips', 'audit_trail', and 'metadata' keys.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_ips_documents(limit: int = 50) -> list[dict]:
    """
    List all saved IPS documents with summary info.

    Args:
        limit: Maximum number of documents to return.

    Returns:
        List of summary dicts.
    """
    _ensure_ips_dir()
    documents = []

    for filepath in sorted(IPS_DIR.glob("ips_*.json"), reverse=True):
        try:
            record = load_ips(filepath)
            ips = record.get("ips", {})
            meta = record.get("metadata", {})
            audit = record.get("audit_trail", {})

            documents.append({
                "filepath": str(filepath),
                "client_name": meta.get("client_name", ips.get("client_name", "Unknown")),
                "version": ips.get("version", "?"),
                "risk_level": ips.get("risk_tolerance", {}).get("overall_risk_level", "?"),
                "status": audit.get("final_status", "?"),
                "revision_rounds": audit.get("total_rounds", 0),
                "saved_at": meta.get("saved_at", ""),
            })

            if len(documents) >= limit:
                break
        except Exception:
            continue

    return documents


# ============================================================
# Export Functions
# ============================================================

def export_ips_markdown(ips_dict: dict, audit_trail_dict: Optional[dict] = None) -> str:
    """
    Export an IPS to formatted Markdown.

    Args:
        ips_dict: IPSDocument as dict.
        audit_trail_dict: Optional AuditTrail as dict.

    Returns:
        Formatted Markdown string.
    """
    ips = ips_dict
    lines = []

    # Header
    lines.append(f"# 投资政策声明书 (IPS)")
    lines.append("")
    lines.append(f"**客户**: {ips.get('client_name', 'N/A')}")
    lines.append(f"**编制方**: {ips.get('prepared_by', 'N/A')}")
    lines.append(f"**编制日期**: {ips.get('preparation_date', 'N/A')}")
    lines.append(f"**版本**: {ips.get('version', 'N/A')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive Summary
    lines.append("## 一、执行摘要")
    lines.append("")
    lines.append(ips.get("executive_summary", ""))
    lines.append("")

    # Client Background
    lines.append("## 二、客户背景")
    lines.append("")
    lines.append(ips.get("client_background", ""))
    lines.append("")

    # Return Objectives
    ret = ips.get("return_objective", {})
    lines.append("## 三、收益目标")
    lines.append("")
    lines.append(f"- **所需名义年化收益率**: {ret.get('required_nominal_return', 0):.2%}")
    lines.append(f"- **所需实际年化收益率**: {ret.get('required_real_return', 0):.2%}")
    lines.append(f"- **计算依据**: {ret.get('return_calculation_basis', '')}")
    lines.append("")
    lines.append(ret.get("return_objective_narrative", ""))
    lines.append("")

    # Risk Tolerance
    risk = ips.get("risk_tolerance", {})
    lines.append("## 四、风险承受能力")
    lines.append("")
    lines.append(f"**综合风险等级**: {risk.get('overall_risk_level', '')}")
    lines.append("")
    lines.append("### 客观承受能力评估")
    lines.append(risk.get("ability_assessment", ""))
    lines.append("")
    lines.append("### 主观承担意愿评估")
    lines.append(risk.get("willingness_assessment", ""))
    lines.append("")
    if risk.get("conflict_resolution"):
        lines.append("### 冲突处理")
        lines.append(risk["conflict_resolution"])
        lines.append("")
    lines.append(risk.get("risk_narrative", ""))
    lines.append("")

    # Time Horizon
    th = ips.get("time_horizon", {})
    lines.append("## 五、投资期限")
    lines.append("")
    lines.append(f"**总投资期限**: {th.get('overall_horizon_years', 0)} 年")
    lines.append("")
    for stage in th.get("stages", []):
        lines.append(f"- **{stage.get('name', '')}**: {stage.get('years', 0)} 年 — {stage.get('description', '')}")
    lines.append("")
    lines.append(th.get("horizon_narrative", ""))
    lines.append("")

    # Liquidity
    liq = ips.get("liquidity", {})
    lines.append("## 六、流动性约束")
    lines.append("")
    lines.append(f"- **即时流动性需求**: ¥{liq.get('immediate_needs', 0):,.0f}")
    lines.append(f"- **持续性需求（年）**: ¥{liq.get('ongoing_needs', 0):,.0f}")
    lines.append(f"- **应急储备**: {liq.get('emergency_reserve_months', 0)} 个月")
    lines.append("")
    lines.append(liq.get("liquidity_narrative", ""))
    lines.append("")

    # Tax
    tax = ips.get("tax", {})
    lines.append("## 七、税务约束")
    lines.append("")
    lines.append(f"**税务身份**: {tax.get('tax_status', '')}")
    lines.append("")
    lines.append(tax.get("tax_narrative", ""))
    lines.append("")

    # Legal
    legal = ips.get("legal", {})
    lines.append("## 八、法律与监管约束")
    lines.append("")
    for reg in legal.get("applicable_regulations", []):
        lines.append(f"- {reg}")
    lines.append("")
    lines.append(legal.get("legal_narrative", ""))
    lines.append("")

    # Unique Circumstances
    unique = ips.get("unique_circumstances", {})
    lines.append("## 九、特殊情况")
    lines.append("")
    if unique.get("esg_preferences"):
        lines.append(f"- **ESG 偏好**: {unique['esg_preferences']}")
    if unique.get("sector_restrictions"):
        lines.append(f"- **行业限制**: {', '.join(unique['sector_restrictions'])}")
    if unique.get("concentrated_positions"):
        lines.append(f"- **集中持仓**: {unique['concentrated_positions']}")
    lines.append("")
    lines.append(unique.get("unique_narrative", ""))
    lines.append("")

    # Investment Guidelines
    guide = ips.get("investment_guidelines", {})
    lines.append("## 十、投资指引与政策")
    lines.append("")
    lines.append("### 战略性资产配置")
    lines.append("")
    lines.append("| 资产类别 | 目标权重 | 最低权重 | 最高权重 | 配置理由 |")
    lines.append("|----------|----------|----------|----------|----------|")
    for alloc in guide.get("strategic_allocation", []):
        lines.append(
            f"| {alloc.get('asset_class', '')} "
            f"| {alloc.get('target_weight', 0):.1%} "
            f"| {alloc.get('min_weight', 0):.1%} "
            f"| {alloc.get('max_weight', 0):.1%} "
            f"| {alloc.get('rationale', '')} |"
        )
    lines.append("")
    lines.append(f"**允许的投资工具**: {', '.join(guide.get('permitted_instruments', []))}")
    lines.append(f"**禁止的投资工具**: {', '.join(guide.get('prohibited_instruments', []))}")
    lines.append(f"**再平衡政策**: {guide.get('rebalancing_policy', '')}")
    lines.append("")
    lines.append(guide.get("guideline_narrative", ""))
    lines.append("")

    # Monitoring
    mon = ips.get("monitoring", {})
    lines.append("## 十一、监控与评估")
    lines.append("")
    lines.append(f"**审查频率**: {mon.get('review_frequency', '')}")
    lines.append("")
    if mon.get("benchmarks"):
        lines.append("**绩效基准**:")
        for bm in mon["benchmarks"]:
            lines.append(f"- {bm.get('asset_class', '')}: {bm.get('benchmark', '')}")
    lines.append("")
    lines.append(mon.get("monitoring_narrative", ""))
    lines.append("")

    # Risk Disclosure
    lines.append("## 十二、风险披露与合规声明")
    lines.append("")
    lines.append("### 风险披露")
    lines.append(ips.get("risk_disclosure", ""))
    lines.append("")
    lines.append("### 合规声明")
    lines.append(ips.get("compliance_statement", ""))
    lines.append("")

    # Audit Trail Summary (if provided)
    if audit_trail_dict:
        lines.append("---")
        lines.append("")
        lines.append("## 附录：生成审计追踪")
        lines.append("")
        lines.append(f"- **修订轮次**: {audit_trail_dict.get('total_rounds', 0)}")
        lines.append(f"- **最终状态**: {audit_trail_dict.get('final_status', '')}")
        meta = audit_trail_dict.get("generation_metadata", {})
        lines.append(f"- **模型**: {meta.get('model', '')}")
        lines.append(f"- **完成时间**: {meta.get('completed_at', '')}")

        for rev in audit_trail_dict.get("revision_history", []):
            lines.append(f"\n### 第 {rev.get('round_number', '?')} 轮修订")
            lines.append(f"- 版本: {rev.get('ips_version_before', '')} → {rev.get('ips_version_after', '')}")
            for change in rev.get("changes_made", []):
                if change:
                    lines.append(f"  - {change}")

    return "\n".join(lines)


def export_ips_to_file(
    ips_dict: dict,
    output_path: Path,
    audit_trail_dict: Optional[dict] = None,
    format: str = "markdown",
) -> Path:
    """
    Export an IPS to a standalone file.

    Args:
        ips_dict: IPSDocument as dict.
        output_path: Output file path.
        audit_trail_dict: Optional AuditTrail as dict.
        format: 'markdown' or 'json'.

    Returns:
        Path to the exported file.
    """
    if format == "markdown":
        content = export_ips_markdown(ips_dict, audit_trail_dict)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    elif format == "json":
        record = {"ips": ips_dict}
        if audit_trail_dict:
            record["audit_trail"] = audit_trail_dict
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Unsupported format: {format}")

    return output_path

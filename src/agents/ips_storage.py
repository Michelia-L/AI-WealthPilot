"""
AI WealthPilot - IPS Storage & Export Module

Provides persistence and export capabilities for AI-generated
Investment Policy Statements (IPS) and their audit trails.

Key Features:
    1. Save/load IPSDocument + AuditTrail as JSON
    2. Export to professional HTML (print-ready)
    3. Export to Markdown
    4. List and query stored IPS documents


"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.utils import sanitize_filename

# Storage Directory

IPS_DIR = DATA_DIR / "ips"


def _ensure_ips_dir() -> Path:
    """Ensure the IPS storage directory exists."""
    IPS_DIR.mkdir(parents=True, exist_ok=True)
    return IPS_DIR


# Core CRUD Operations

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


# Export Functions

def export_ips_markdown(
    ips_dict: dict,
    audit_trail_dict: Optional[dict] = None,
    locale: str = "zh",
) -> str:
    """
    Export an IPS to formatted Markdown.

    Args:
        ips_dict: IPSDocument as dict.
        audit_trail_dict: Optional AuditTrail as dict.
        locale: Scaffolding language of headings and field labels ("zh"
            keeps the original Chinese wording verbatim, "en" is English).
            Narrative content stored in the IPS is emitted as-is either way.

    Returns:
        Formatted Markdown string.
    """
    labels = _MD_LABELS["en" if locale == "en" else "zh"]
    return _render_ips_markdown(ips_dict, audit_trail_dict, labels)


# Markdown scaffolding labels per locale. The zh column preserves the
# pre-i18n wording verbatim; the en column was added in Phase 22. Narrative
# content stored in the IPS is emitted as-is either way.
_MD_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "title": "# 投资政策声明书 (IPS)",
        "client": "客户",
        "prepared_by": "编制方",
        "prep_date": "编制日期",
        "version": "版本",
        "sec_summary": "## 一、执行摘要",
        "sec_background": "## 二、客户背景",
        "sec_return": "## 三、收益目标",
        "req_nominal": "所需名义年化收益率",
        "req_real": "所需实际年化收益率",
        "calc_basis": "计算依据",
        "sec_risk": "## 四、风险承受能力",
        "overall_risk": "综合风险等级",
        "ability_h": "### 客观承受能力评估",
        "willingness_h": "### 主观承担意愿评估",
        "conflict_h": "### 冲突处理",
        "quant_h": "### 量化风险指标",
        "quant_th": "| 指标 | 阈值 |",
        "quant_sep": "|------|------|",
        "max_loss": "最大可接受年度亏损",
        "vol_range": "目标波动率区间",
        "var_tol": "95% VaR 容忍度（年化）",
        "mdd_tol": "最大回撤容忍度",
        "sec_horizon": "## 五、投资期限",
        "total_horizon_fmt": "**总投资期限**: {years} 年",
        "stage_fmt": "- **{name}**: {years} 年 — {desc}",
        "sec_liquidity": "## 六、流动性约束",
        "immediate": "即时流动性需求",
        "ongoing": "持续性需求（年）",
        "reserve_fmt": "- **应急储备**: {months} 个月",
        "sec_tax": "## 七、税务约束",
        "tax_status": "税务身份",
        "sec_legal": "## 八、法律与监管约束",
        "sec_unique": "## 九、特殊情况",
        "esg": "ESG 偏好",
        "sector": "行业限制",
        "concentrated": "集中持仓",
        "sec_guidelines": "## 十、投资指引与政策",
        "saa_h": "### 战略性资产配置",
        "alloc_th": "| 资产类别 | 目标权重 | 最低权重 | 最高权重 | 配置理由 |",
        "alloc_sep": "|----------|----------|----------|----------|----------|",
        "permitted": "允许的投资工具",
        "prohibited": "禁止的投资工具",
        "rebalancing": "再平衡政策",
        "sec_fees": "## 十一、费用与成本披露",
        "fee_th": "| 费用项目 | 费率 |",
        "fee_sep": "|----------|------|",
        "fee_mgmt": "投资管理费",
        "fee_custody": "托管费",
        "fee_trans": "预估交易成本",
        "fee_ter": "**总费用率 (TER)**",
        "net_impact": "净收益影响",
        "mon_num_with_fee": "十二",
        "mon_num_without_fee": "十一",
        "disc_num_with_fee": "十三",
        "disc_num_without_fee": "十二",
        "mon_sec_fmt": "## {num}、监控与评估",
        "review_freq": "审查频率",
        "benchmarks_label": "**绩效基准**:",
        "disc_sec_fmt": "## {num}、风险披露与合规声明",
        "risk_disc_h": "### 风险披露",
        "compliance_h": "### 合规声明",
        "appendix_h": "## 附录：生成审计追踪",
        "rounds": "修订轮次",
        "final_status": "最终状态",
        "model": "模型",
        "completed_at": "完成时间",
        "rev_round_fmt": "\n### 第 {n} 轮修订",
        "rev_version_fmt": "- 版本: {before} → {after}",
    },
    "en": {
        "title": "# Investment Policy Statement (IPS)",
        "client": "Client",
        "prepared_by": "Prepared by",
        "prep_date": "Preparation date",
        "version": "Version",
        "sec_summary": "## 1. Executive Summary",
        "sec_background": "## 2. Client Background",
        "sec_return": "## 3. Return Objectives",
        "req_nominal": "Required nominal annual return",
        "req_real": "Required real annual return",
        "calc_basis": "Calculation basis",
        "sec_risk": "## 4. Risk Tolerance",
        "overall_risk": "Overall risk level",
        "ability_h": "### Ability Assessment (Objective)",
        "willingness_h": "### Willingness Assessment (Subjective)",
        "conflict_h": "### Conflict Resolution",
        "quant_h": "### Quantitative Risk Anchors",
        "quant_th": "| Metric | Threshold |",
        "quant_sep": "|--------|-----------|",
        "max_loss": "Maximum acceptable annual loss",
        "vol_range": "Target volatility range",
        "var_tol": "95% VaR tolerance (annualized)",
        "mdd_tol": "Maximum drawdown tolerance",
        "sec_horizon": "## 5. Time Horizon",
        "total_horizon_fmt": "**Total horizon**: {years} years",
        "stage_fmt": "- **{name}**: {years} years — {desc}",
        "sec_liquidity": "## 6. Liquidity Constraints",
        "immediate": "Immediate liquidity needs",
        "ongoing": "Ongoing needs (annual)",
        "reserve_fmt": "- **Emergency reserve**: {months} months",
        "sec_tax": "## 7. Tax Constraints",
        "tax_status": "Tax status",
        "sec_legal": "## 8. Legal & Regulatory Constraints",
        "sec_unique": "## 9. Unique Circumstances",
        "esg": "ESG preferences",
        "sector": "Sector restrictions",
        "concentrated": "Concentrated positions",
        "sec_guidelines": "## 10. Investment Guidelines & Policies",
        "saa_h": "### Strategic Asset Allocation",
        "alloc_th": "| Asset Class | Target Weight | Min Weight | Max Weight | Rationale |",
        "alloc_sep": "|-------------|---------------|------------|------------|-----------|",
        "permitted": "Permitted instruments",
        "prohibited": "Prohibited instruments",
        "rebalancing": "Rebalancing policy",
        "sec_fees": "## 11. Fees & Cost Disclosure",
        "fee_th": "| Fee Item | Rate |",
        "fee_sep": "|----------|------|",
        "fee_mgmt": "Investment management fee",
        "fee_custody": "Custody fee",
        "fee_trans": "Estimated transaction costs",
        "fee_ter": "**Total Expense Ratio (TER)**",
        "net_impact": "Net return impact",
        "mon_num_with_fee": "12",
        "mon_num_without_fee": "11",
        "disc_num_with_fee": "13",
        "disc_num_without_fee": "12",
        "mon_sec_fmt": "## {num}. Monitoring & Review",
        "review_freq": "Review frequency",
        "benchmarks_label": "**Performance benchmarks**:",
        "disc_sec_fmt": "## {num}. Risk Disclosure & Compliance Statement",
        "risk_disc_h": "### Risk Disclosure",
        "compliance_h": "### Compliance Statement",
        "appendix_h": "## Appendix: Generation Audit Trail",
        "rounds": "Revision rounds",
        "final_status": "Final status",
        "model": "Model",
        "completed_at": "Completed at",
        "rev_round_fmt": "\n### Revision Round {n}",
        "rev_version_fmt": "- Version: {before} → {after}",
    },
}


def _render_ips_markdown(
    ips_dict: dict, audit_trail_dict: Optional[dict], labels: dict[str, str]
) -> str:
    """Render an IPS dict to Markdown with the given scaffolding labels."""
    L = labels
    ips = ips_dict
    lines = []

    # Header
    lines.append(L["title"])
    lines.append("")
    lines.append(f"**{L['client']}**: {ips.get('client_name', 'N/A')}")
    lines.append(f"**{L['prepared_by']}**: {ips.get('prepared_by', 'N/A')}")
    lines.append(f"**{L['prep_date']}**: {ips.get('preparation_date', 'N/A')}")
    lines.append(f"**{L['version']}**: {ips.get('version', 'N/A')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive Summary
    lines.append(L["sec_summary"])
    lines.append("")
    lines.append(ips.get("executive_summary", ""))
    lines.append("")

    # Client Background
    lines.append(L["sec_background"])
    lines.append("")
    lines.append(ips.get("client_background", ""))
    lines.append("")

    # Return Objectives
    ret = ips.get("return_objective", {})
    lines.append(L["sec_return"])
    lines.append("")
    lines.append(f"- **{L['req_nominal']}**: {ret.get('required_nominal_return', 0):.2%}")
    lines.append(f"- **{L['req_real']}**: {ret.get('required_real_return', 0):.2%}")
    lines.append(f"- **{L['calc_basis']}**: {ret.get('return_calculation_basis', '')}")
    lines.append("")
    lines.append(ret.get("return_objective_narrative", ""))
    lines.append("")

    # Risk Tolerance
    risk = ips.get("risk_tolerance", {})
    lines.append(L["sec_risk"])
    lines.append("")
    lines.append(f"**{L['overall_risk']}**: {risk.get('overall_risk_level', '')}")
    lines.append("")
    lines.append(L["ability_h"])
    lines.append(risk.get("ability_assessment", ""))
    lines.append("")
    lines.append(L["willingness_h"])
    lines.append(risk.get("willingness_assessment", ""))
    lines.append("")
    if risk.get("conflict_resolution"):
        lines.append(L["conflict_h"])
        lines.append(risk["conflict_resolution"])
        lines.append("")
    lines.append(risk.get("risk_narrative", ""))
    lines.append("")

    # Quantitative risk anchors (if any are provided)
    _has_quant = any(risk.get(k) is not None for k in [
        "max_acceptable_annual_loss", "target_volatility_min",
        "target_volatility_max", "var_tolerance_95", "max_drawdown_tolerance"
    ])
    if _has_quant:
        lines.append(L["quant_h"])
        lines.append("")
        lines.append(L["quant_th"])
        lines.append(L["quant_sep"])
        if risk.get("max_acceptable_annual_loss") is not None:
            lines.append(f"| {L['max_loss']} | {risk['max_acceptable_annual_loss']:.2%} |")
        if risk.get("target_volatility_min") is not None and risk.get("target_volatility_max") is not None:
            lines.append(f"| {L['vol_range']} | {risk['target_volatility_min']:.2%} – {risk['target_volatility_max']:.2%} |")
        if risk.get("var_tolerance_95") is not None:
            lines.append(f"| {L['var_tol']} | {risk['var_tolerance_95']:.2%} |")
        if risk.get("max_drawdown_tolerance") is not None:
            lines.append(f"| {L['mdd_tol']} | {risk['max_drawdown_tolerance']:.2%} |")
        lines.append("")

    # Time Horizon
    th = ips.get("time_horizon", {})
    lines.append(L["sec_horizon"])
    lines.append("")
    lines.append(L["total_horizon_fmt"].format(years=th.get("overall_horizon_years", 0)))
    lines.append("")
    for stage in th.get("stages", []):
        lines.append(L["stage_fmt"].format(
            name=stage.get("name", ""),
            years=stage.get("years", 0),
            desc=stage.get("description", ""),
        ))
    lines.append("")
    lines.append(th.get("horizon_narrative", ""))
    lines.append("")

    # Liquidity
    liq = ips.get("liquidity", {})
    # Derive currency symbol from currency_policy or default to ¥ (CNY)
    _currency_symbols = {"CNY": "¥", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "HKD": "HK$"}
    _base_curr = (ips.get("currency_policy") or {}).get("base_currency", "CNY")
    _curr_sym = _currency_symbols.get(_base_curr, _base_curr + " ")
    lines.append(L["sec_liquidity"])
    lines.append("")
    lines.append(f"- **{L['immediate']}**: {_curr_sym}{liq.get('immediate_needs', 0):,.0f}")
    lines.append(f"- **{L['ongoing']}**: {_curr_sym}{liq.get('ongoing_needs', 0):,.0f}")
    lines.append(L["reserve_fmt"].format(months=liq.get("emergency_reserve_months", 0)))
    lines.append("")
    lines.append(liq.get("liquidity_narrative", ""))
    lines.append("")

    # Tax
    tax = ips.get("tax", {})
    lines.append(L["sec_tax"])
    lines.append("")
    lines.append(f"**{L['tax_status']}**: {tax.get('tax_status', '')}")
    lines.append("")
    lines.append(tax.get("tax_narrative", ""))
    lines.append("")

    # Legal
    legal = ips.get("legal", {})
    lines.append(L["sec_legal"])
    lines.append("")
    for reg in legal.get("applicable_regulations", []):
        lines.append(f"- {reg}")
    lines.append("")
    lines.append(legal.get("legal_narrative", ""))
    lines.append("")

    # Unique Circumstances
    unique = ips.get("unique_circumstances", {})
    lines.append(L["sec_unique"])
    lines.append("")
    if unique.get("esg_preferences"):
        lines.append(f"- **{L['esg']}**: {unique['esg_preferences']}")
    if unique.get("sector_restrictions"):
        lines.append(f"- **{L['sector']}**: {', '.join(unique['sector_restrictions'])}")
    if unique.get("concentrated_positions"):
        lines.append(f"- **{L['concentrated']}**: {unique['concentrated_positions']}")
    lines.append("")
    lines.append(unique.get("unique_narrative", ""))
    lines.append("")

    # Investment Guidelines
    guide = ips.get("investment_guidelines", {})
    lines.append(L["sec_guidelines"])
    lines.append("")
    lines.append(L["saa_h"])
    lines.append("")
    lines.append(L["alloc_th"])
    lines.append(L["alloc_sep"])
    for alloc in guide.get("strategic_allocation", []):
        lines.append(
            f"| {alloc.get('asset_class', '')} "
            f"| {alloc.get('target_weight', 0):.1%} "
            f"| {alloc.get('min_weight', 0):.1%} "
            f"| {alloc.get('max_weight', 0):.1%} "
            f"| {alloc.get('rationale', '')} |"
        )
    lines.append("")
    lines.append(f"**{L['permitted']}**: {', '.join(guide.get('permitted_instruments', []))}")
    lines.append(f"**{L['prohibited']}**: {', '.join(guide.get('prohibited_instruments', []))}")
    lines.append(f"**{L['rebalancing']}**: {guide.get('rebalancing_policy', '')}")
    lines.append("")
    lines.append(guide.get("guideline_narrative", ""))
    lines.append("")

    # Fee Schedule (if provided)
    fee = ips.get("fee_schedule")
    if fee:
        lines.append(L["sec_fees"])
        lines.append("")
        lines.append(L["fee_th"])
        lines.append(L["fee_sep"])
        lines.append(f"| {L['fee_mgmt']} | {fee.get('management_fee_rate', 0):.2%} |")
        lines.append(f"| {L['fee_custody']} | {fee.get('custody_fee_rate', 0):.2%} |")
        lines.append(f"| {L['fee_trans']} | {fee.get('transaction_cost_estimate', 0):.2%} |")
        lines.append(f"| {L['fee_ter']} | **{fee.get('total_expense_ratio', 0):.2%}** |")
        lines.append("")
        if fee.get("net_return_impact"):
            lines.append(f"**{L['net_impact']}**: {fee['net_return_impact']}")
            lines.append("")
        lines.append(fee.get("fee_narrative", ""))
        lines.append("")

        # Adjust section numbering for subsequent sections
        mon_section = L["mon_num_with_fee"]
        disclosure_section = L["disc_num_with_fee"]
    else:
        mon_section = L["mon_num_without_fee"]
        disclosure_section = L["disc_num_without_fee"]

    # Monitoring
    mon = ips.get("monitoring", {})
    lines.append(L["mon_sec_fmt"].format(num=mon_section))
    lines.append("")
    lines.append(f"**{L['review_freq']}**: {mon.get('review_frequency', '')}")
    lines.append("")
    if mon.get("benchmarks"):
        lines.append(L["benchmarks_label"])
        for bm in mon["benchmarks"]:
            lines.append(f"- {bm.get('asset_class', '')}: {bm.get('benchmark', '')}")
    lines.append("")
    lines.append(mon.get("monitoring_narrative", ""))
    lines.append("")

    # Risk Disclosure
    lines.append(L["disc_sec_fmt"].format(num=disclosure_section))
    lines.append("")
    lines.append(L["risk_disc_h"])
    lines.append(ips.get("risk_disclosure", ""))
    lines.append("")
    lines.append(L["compliance_h"])
    lines.append(ips.get("compliance_statement", ""))
    lines.append("")

    # Audit Trail Summary (if provided)
    if audit_trail_dict:
        lines.append("---")
        lines.append("")
        lines.append(L["appendix_h"])
        lines.append("")
        lines.append(f"- **{L['rounds']}**: {audit_trail_dict.get('total_rounds', 0)}")
        lines.append(f"- **{L['final_status']}**: {audit_trail_dict.get('final_status', '')}")
        meta = audit_trail_dict.get("generation_metadata", {})
        lines.append(f"- **{L['model']}**: {meta.get('model', '')}")
        lines.append(f"- **{L['completed_at']}**: {meta.get('completed_at', '')}")

        for rev in audit_trail_dict.get("revision_history", []):
            lines.append(L["rev_round_fmt"].format(n=rev.get("round_number", "?")))
            lines.append(L["rev_version_fmt"].format(
                before=rev.get("ips_version_before", ""),
                after=rev.get("ips_version_after", ""),
            ))
            for change in rev.get("changes_made", []):
                if change:
                    lines.append(f"  - {change}")

    return "\n".join(lines)


def _find_cjk_font() -> Optional[str]:
    """
    Find a suitable CJK font file for PDF rendering.

    Searches common system paths for Chinese-capable fonts.
    Returns the path to the font file, or None if not found.
    """
    candidates = [
        # Windows
        r"C:\Windows\Fonts\msyh.ttc",       # Microsoft YaHei
        r"C:\Windows\Fonts\simhei.ttf",      # SimHei
        r"C:\Windows\Fonts\simsun.ttc",      # SimSun
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Linux
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


# Locale-dependent chrome for the IPS PDF builder (Phase 22). zh keeps the
# pre-i18n wording verbatim; en is the English-only counterpart. Stored
# narrative content is emitted as-is either way.
_IPS_PDF_LABELS: dict[str, dict[str, str]] = {
    "zh": {
        "header_suffix": "投资政策声明书",
        "doc_title": "投资政策声明书 (IPS)",
        "kv_client": "客户",
        "kv_prepared_by": "编制方",
        "kv_preparation_date": "编制日期",
        "kv_version": "版本",
        "sec_executive_summary": "一、执行摘要",
        "sec_client_background": "二、客户背景",
        "sec_return_objectives": "三、收益目标",
        "sec_risk_tolerance": "四、风险承受能力",
        "sec_time_horizon": "五、投资期限",
        "sec_liquidity": "六、流动性约束",
        "sec_tax": "七、税务约束",
        "sec_legal": "八、法律与监管约束",
        "sec_unique": "九、特殊情况",
        "sec_guidelines": "十、投资指引与政策",
        "sec_fee": "十一、费用与成本披露",
        "kv_required_nominal": "所需名义年化收益率",
        "kv_required_real": "所需实际年化收益率",
        "kv_calc_basis": "计算依据",
        "kv_overall_risk": "综合风险等级",
        "sub_ability": "客观承受能力评估",
        "sub_willingness": "主观承担意愿评估",
        "sub_conflict": "冲突处理",
        "sub_quant": "量化风险指标",
        "quant_h_metric": "指标",
        "quant_h_threshold": "阈值",
        "quant_max_loss": "最大可接受年度亏损",
        "quant_target_vol": "目标波动率区间",
        "quant_var": "95% VaR 容忍度",
        "quant_mdd": "最大回撤容忍度",
        "kv_total_horizon": "总投资期限",
        "years_unit": "年",
        "months_unit": "个月",
        "kv_immediate": "即时流动性需求",
        "kv_ongoing": "持续性需求（年）",
        "kv_emergency": "应急储备",
        "kv_tax_status": "税务身份",
        "kv_esg": "ESG 偏好",
        "kv_sector": "行业限制",
        "kv_concentrated": "集中持仓",
        "sub_saa": "战略性资产配置",
        "saa_h_class": "资产类别",
        "saa_h_target": "目标权重",
        "saa_h_min": "最低权重",
        "saa_h_max": "最高权重",
        "permitted_prefix": "允许的投资工具",
        "prohibited_prefix": "禁止的投资工具",
        "rebalancing_prefix": "再平衡政策",
        "fee_mgmt": "投资管理费",
        "fee_custody": "托管费",
        "fee_txn": "预估交易成本",
        "fee_ter": "总费用率 (TER)",
        "fee_h_item": "费用项目",
        "fee_h_rate": "费率",
        "kv_net_impact": "净收益影响",
        "kv_review_freq": "审查频率",
        "sub_benchmarks": "绩效基准",
        "sub_risk_disclosure": "风险披露",
        "sub_compliance": "合规声明",
        "sig_client": "客户签名",
        "sig_date": "日期",
        "sig_advisor": "顾问签名",
        "page_fmt": "第 {page} 页",
        "sec_monitoring_tpl": "{n}、监控与评估",
        "sec_disclosure_tpl": "{n}、风险披露与合规声明",
        "n_11": "十一",
        "n_12": "十二",
        "n_13": "十三",
    },
    "en": {
        "header_suffix": "Investment Policy Statement",
        "doc_title": "Investment Policy Statement (IPS)",
        "kv_client": "Client",
        "kv_prepared_by": "Prepared by",
        "kv_preparation_date": "Preparation date",
        "kv_version": "Version",
        "sec_executive_summary": "1. Executive Summary",
        "sec_client_background": "2. Client Background",
        "sec_return_objectives": "3. Return Objectives",
        "sec_risk_tolerance": "4. Risk Tolerance",
        "sec_time_horizon": "5. Time Horizon",
        "sec_liquidity": "6. Liquidity Constraints",
        "sec_tax": "7. Tax Constraints",
        "sec_legal": "8. Legal & Regulatory Constraints",
        "sec_unique": "9. Unique Circumstances",
        "sec_guidelines": "10. Investment Guidelines & Policies",
        "sec_fee": "11. Fees & Cost Disclosure",
        "kv_required_nominal": "Required nominal annual return",
        "kv_required_real": "Required real annual return",
        "kv_calc_basis": "Calculation basis",
        "kv_overall_risk": "Overall risk level",
        "sub_ability": "Ability Assessment (Objective)",
        "sub_willingness": "Willingness Assessment (Subjective)",
        "sub_conflict": "Conflict Resolution",
        "sub_quant": "Quantitative Risk Anchors",
        "quant_h_metric": "Metric",
        "quant_h_threshold": "Threshold",
        "quant_max_loss": "Maximum acceptable annual loss",
        "quant_target_vol": "Target volatility range",
        "quant_var": "95% VaR tolerance",
        "quant_mdd": "Maximum drawdown tolerance",
        "kv_total_horizon": "Total horizon",
        "years_unit": "years",
        "months_unit": "months",
        "kv_immediate": "Immediate liquidity needs",
        "kv_ongoing": "Ongoing needs (annual)",
        "kv_emergency": "Emergency reserve",
        "kv_tax_status": "Tax status",
        "kv_esg": "ESG preferences",
        "kv_sector": "Sector restrictions",
        "kv_concentrated": "Concentrated positions",
        "sub_saa": "Strategic Asset Allocation",
        "saa_h_class": "Asset Class",
        "saa_h_target": "Target Weight",
        "saa_h_min": "Min Weight",
        "saa_h_max": "Max Weight",
        "permitted_prefix": "Permitted instruments",
        "prohibited_prefix": "Prohibited instruments",
        "rebalancing_prefix": "Rebalancing policy",
        "fee_mgmt": "Investment management fee",
        "fee_custody": "Custody fee",
        "fee_txn": "Estimated transaction costs",
        "fee_ter": "Total Expense Ratio (TER)",
        "fee_h_item": "Fee Item",
        "fee_h_rate": "Rate",
        "kv_net_impact": "Net return impact",
        "kv_review_freq": "Review frequency",
        "sub_benchmarks": "Performance benchmarks",
        "sub_risk_disclosure": "Risk Disclosure",
        "sub_compliance": "Compliance Statement",
        "sig_client": "Client Signature",
        "sig_date": "Date",
        "sig_advisor": "Advisor Signature",
        "page_fmt": "Page {page}",
        "sec_monitoring_tpl": "{n}. Monitoring & Review",
        "sec_disclosure_tpl": "{n}. Risk Disclosure & Compliance Statement",
        "n_11": "11",
        "n_12": "12",
        "n_13": "13",
    },
}


class _IPSPDF:
    """
    Internal PDF builder for IPS documents.

    Wraps fpdf2 FPDF with CJK font support, consistent styling,
    and IPS-specific rendering methods.
    """

    def __init__(self, font_path: Optional[str] = None, locale: str = "zh") -> None:
        from fpdf import FPDF

        self.pdf = FPDF(orientation="P", unit="mm", format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=25)
        self._font_family = "Helvetica"
        self._labels = _IPS_PDF_LABELS["en" if locale == "en" else "zh"]

        # Register CJK font if available
        if font_path and Path(font_path).exists():
            self.pdf.add_font("CJK", "", font_path)
            self.pdf.add_font("CJK", "B", font_path)
            self._font_family = "CJK"

    def _header_footer(self, client_name: str) -> None:
        """Configure header/footer via subclass-like callback setup."""
        # fpdf2 doesn't use subclassing for headers — we draw them manually
        pass

    def _add_header(self, client_name: str) -> None:
        """Draw page header."""
        self.pdf.set_font(self._font_family, "B", 8)
        self.pdf.set_text_color(120, 120, 120)
        self.pdf.cell(0, 5, f"AI WealthPilot — {client_name} {self._labels['header_suffix']}", align="C")
        self.pdf.ln(3)
        self.pdf.set_draw_color(200, 200, 200)
        self.pdf.line(20, self.pdf.get_y(), 190, self.pdf.get_y())
        self.pdf.ln(5)
        self.pdf.set_text_color(0, 0, 0)

    def _add_footer(self) -> None:
        """Draw page footer with page number."""
        self.pdf.set_y(-20)
        self.pdf.set_font(self._font_family, "", 8)
        self.pdf.set_text_color(120, 120, 120)
        self.pdf.cell(0, 10, self._labels["page_fmt"].format(page=self.pdf.page_no()), align="C")
        self.pdf.set_text_color(0, 0, 0)

    def _section_title(self, title: str) -> None:
        """Render a section title (h2 equivalent)."""
        self.pdf.set_font(self._font_family, "B", 14)
        self.pdf.set_text_color(26, 54, 93)  # Dark blue
        self.pdf.ln(4)
        self.pdf.cell(0, 8, title)
        self.pdf.ln(2)
        self.pdf.set_draw_color(44, 82, 130)
        self.pdf.line(20, self.pdf.get_y(), 190, self.pdf.get_y())
        self.pdf.ln(6)
        self.pdf.set_text_color(0, 0, 0)

    def _subsection_title(self, title: str) -> None:
        """Render a subsection title (h3 equivalent)."""
        self.pdf.set_font(self._font_family, "B", 11)
        self.pdf.set_text_color(44, 82, 130)
        self.pdf.cell(0, 7, title)
        self.pdf.ln(6)
        self.pdf.set_text_color(0, 0, 0)

    def _body_text(self, text: str) -> None:
        """Render body text with word wrapping."""
        if not text:
            return
        self.pdf.set_font(self._font_family, "", 10)
        self.pdf.multi_cell(0, 5, text)
        self.pdf.ln(3)

    def _key_value(self, key: str, value: str) -> None:
        """Render a key-value pair."""
        self.pdf.set_font(self._font_family, "B", 10)
        self.pdf.cell(50, 6, f"{key}:")
        self.pdf.set_font(self._font_family, "", 10)
        self.pdf.cell(0, 6, value)
        self.pdf.ln(6)

    def _simple_table(self, headers: list[str], rows: list[list[str]],
                      col_widths: Optional[list[float]] = None) -> None:
        """Render a simple table."""
        page_width = 170  # A4 width minus margins
        if not col_widths:
            col_widths = [page_width / len(headers)] * len(headers)

        # Header row
        self.pdf.set_font(self._font_family, "B", 9)
        self.pdf.set_fill_color(237, 242, 247)
        for i, header in enumerate(headers):
            self.pdf.cell(col_widths[i], 7, header, border=1, fill=True, align="C")
        self.pdf.ln()

        # Data rows
        self.pdf.set_font(self._font_family, "", 9)
        for row in rows:
            for i, cell in enumerate(row):
                self.pdf.cell(col_widths[i], 6, cell, border=1, align="C")
            self.pdf.ln()
        self.pdf.ln(3)

    def build(self, ips_dict: dict, audit_trail_dict: Optional[dict] = None, locale: str = "zh") -> bytes:
        """
        Build the complete PDF from an IPS dict.

        Args:
            ips_dict: IPSDocument as dict.
            audit_trail_dict: Optional AuditTrail as dict.
            locale: Scaffolding language ("zh" keeps the original Chinese
                chrome verbatim, "en" is English-only).

        Returns:
            PDF content as bytes.
        """
        L = _IPS_PDF_LABELS["en" if locale == "en" else "zh"]
        self._labels = L
        ips = ips_dict
        client_name = ips.get("client_name", "N/A")

        # ── Cover info ──
        self.pdf.add_page()
        self._add_header(client_name)

        self.pdf.set_font(self._font_family, "B", 22)
        self.pdf.set_text_color(26, 54, 93)
        self.pdf.ln(10)
        self.pdf.cell(0, 12, L["doc_title"], align="C")
        self.pdf.ln(15)
        self.pdf.set_text_color(0, 0, 0)

        self.pdf.set_font(self._font_family, "", 11)
        self._key_value(L["kv_client"], client_name)
        self._key_value(L["kv_prepared_by"], ips.get("prepared_by", "N/A"))
        self._key_value(L["kv_preparation_date"], ips.get("preparation_date", "N/A"))
        self._key_value(L["kv_version"], ips.get("version", "N/A"))
        self.pdf.ln(5)

        # ── 1. Executive Summary ──
        self._section_title(L["sec_executive_summary"])
        self._body_text(ips.get("executive_summary", ""))

        # ── 2. Client Background ──
        self._section_title(L["sec_client_background"])
        self._body_text(ips.get("client_background", ""))

        # ── 3. Return Objectives ──
        ret = ips.get("return_objective", {})
        self._section_title(L["sec_return_objectives"])
        nom = ret.get("required_nominal_return", 0)
        real = ret.get("required_real_return", 0)
        self._key_value(L["kv_required_nominal"], f"{nom:.2%}")
        self._key_value(L["kv_required_real"], f"{real:.2%}")
        self._key_value(L["kv_calc_basis"], ret.get("return_calculation_basis", ""))
        self._body_text(ret.get("return_objective_narrative", ""))

        # ── 4. Risk Tolerance ──
        risk = ips.get("risk_tolerance", {})
        self._section_title(L["sec_risk_tolerance"])
        self._key_value(L["kv_overall_risk"], risk.get("overall_risk_level", ""))
        self._subsection_title(L["sub_ability"])
        self._body_text(risk.get("ability_assessment", ""))
        self._subsection_title(L["sub_willingness"])
        self._body_text(risk.get("willingness_assessment", ""))
        if risk.get("conflict_resolution"):
            self._subsection_title(L["sub_conflict"])
            self._body_text(risk["conflict_resolution"])
        self._body_text(risk.get("risk_narrative", ""))

        # Quantitative risk anchors
        quant_rows = []
        if risk.get("max_acceptable_annual_loss") is not None:
            quant_rows.append([L["quant_max_loss"], f"{risk['max_acceptable_annual_loss']:.2%}"])
        if risk.get("target_volatility_min") is not None and risk.get("target_volatility_max") is not None:
            quant_rows.append([L["quant_target_vol"], f"{risk['target_volatility_min']:.2%} – {risk['target_volatility_max']:.2%}"])
        if risk.get("var_tolerance_95") is not None:
            quant_rows.append([L["quant_var"], f"{risk['var_tolerance_95']:.2%}"])
        if risk.get("max_drawdown_tolerance") is not None:
            quant_rows.append([L["quant_mdd"], f"{risk['max_drawdown_tolerance']:.2%}"])
        if quant_rows:
            self._subsection_title(L["sub_quant"])
            self._simple_table([L["quant_h_metric"], L["quant_h_threshold"]], quant_rows, [85, 85])

        # ── 5. Time Horizon ──
        th = ips.get("time_horizon", {})
        self._section_title(L["sec_time_horizon"])
        self._key_value(L["kv_total_horizon"], f"{th.get('overall_horizon_years', 0)} {L['years_unit']}")
        for stage in th.get("stages", []):
            self._body_text(f"• {stage.get('name', '')}: {stage.get('years', 0)} {L['years_unit']} — {stage.get('description', '')}")
        self._body_text(th.get("horizon_narrative", ""))

        # ── 6. Liquidity ──
        liq = ips.get("liquidity", {})
        self._section_title(L["sec_liquidity"])
        self._key_value(L["kv_immediate"], f"¥{liq.get('immediate_needs', 0):,.0f}")
        self._key_value(L["kv_ongoing"], f"¥{liq.get('ongoing_needs', 0):,.0f}")
        self._key_value(L["kv_emergency"], f"{liq.get('emergency_reserve_months', 0)} {L['months_unit']}")
        self._body_text(liq.get("liquidity_narrative", ""))

        # ── 7. Tax ──
        tax = ips.get("tax", {})
        self._section_title(L["sec_tax"])
        self._key_value(L["kv_tax_status"], tax.get("tax_status", ""))
        self._body_text(tax.get("tax_narrative", ""))

        # ── 8. Legal ──
        legal = ips.get("legal", {})
        self._section_title(L["sec_legal"])
        for reg in legal.get("applicable_regulations", []):
            self._body_text(f"• {reg}")
        self._body_text(legal.get("legal_narrative", ""))

        # ── 9. Unique Circumstances ──
        unique = ips.get("unique_circumstances", {})
        self._section_title(L["sec_unique"])
        if unique.get("esg_preferences"):
            self._key_value(L["kv_esg"], unique["esg_preferences"])
        if unique.get("sector_restrictions"):
            self._key_value(L["kv_sector"], ", ".join(unique["sector_restrictions"]))
        if unique.get("concentrated_positions"):
            self._key_value(L["kv_concentrated"], unique["concentrated_positions"])
        self._body_text(unique.get("unique_narrative", ""))

        # ── 10. Investment Guidelines ──
        guide = ips.get("investment_guidelines", {})
        self._section_title(L["sec_guidelines"])
        self._subsection_title(L["sub_saa"])
        saa_rows = []
        for alloc in guide.get("strategic_allocation", []):
            saa_rows.append([
                alloc.get("asset_class", ""),
                f"{alloc.get('target_weight', 0):.1%}",
                f"{alloc.get('min_weight', 0):.1%}",
                f"{alloc.get('max_weight', 0):.1%}",
            ])
        if saa_rows:
            self._simple_table(
                [L["saa_h_class"], L["saa_h_target"], L["saa_h_min"], L["saa_h_max"]],
                saa_rows, [50, 40, 40, 40]
            )
        self._body_text(f"{L['permitted_prefix']}: {', '.join(guide.get('permitted_instruments', []))}")
        self._body_text(f"{L['prohibited_prefix']}: {', '.join(guide.get('prohibited_instruments', []))}")
        self._body_text(f"{L['rebalancing_prefix']}: {guide.get('rebalancing_policy', '')}")
        self._body_text(guide.get("guideline_narrative", ""))

        # ── 11. Fee Schedule (optional) ──
        fee = ips.get("fee_schedule")
        if fee:
            self._section_title(L["sec_fee"])
            fee_rows = [
                [L["fee_mgmt"], f"{fee.get('management_fee_rate', 0):.2%}"],
                [L["fee_custody"], f"{fee.get('custody_fee_rate', 0):.2%}"],
                [L["fee_txn"], f"{fee.get('transaction_cost_estimate', 0):.2%}"],
                [L["fee_ter"], f"{fee.get('total_expense_ratio', 0):.2%}"],
            ]
            self._simple_table([L["fee_h_item"], L["fee_h_rate"]], fee_rows, [85, 85])
            if fee.get("net_return_impact"):
                self._key_value(L["kv_net_impact"], fee["net_return_impact"])
            self._body_text(fee.get("fee_narrative", ""))
            mon_num, disc_num = L["n_12"], L["n_13"]
        else:
            mon_num, disc_num = L["n_11"], L["n_12"]

        # ── Monitoring ──
        mon = ips.get("monitoring", {})
        self._section_title(L["sec_monitoring_tpl"].format(n=mon_num))
        self._key_value(L["kv_review_freq"], mon.get("review_frequency", ""))
        if mon.get("benchmarks"):
            self._subsection_title(L["sub_benchmarks"])
            for bm in mon["benchmarks"]:
                self._body_text(f"• {bm.get('asset_class', '')}: {bm.get('benchmark', '')}")
        self._body_text(mon.get("monitoring_narrative", ""))

        # ── Risk Disclosure & Compliance ──
        self._section_title(L["sec_disclosure_tpl"].format(n=disc_num))
        self._subsection_title(L["sub_risk_disclosure"])
        self._body_text(ips.get("risk_disclosure", ""))
        self._subsection_title(L["sub_compliance"])
        self._body_text(ips.get("compliance_statement", ""))

        # ── Signature Block ──
        self.pdf.ln(10)
        self.pdf.set_draw_color(60, 60, 60)
        self.pdf.line(20, self.pdf.get_y(), 190, self.pdf.get_y())
        self.pdf.ln(8)
        self.pdf.set_font(self._font_family, "B", 10)
        self.pdf.cell(85, 8, f"{L['sig_client']}: _________________")
        self.pdf.cell(85, 8, f"{L['sig_date']}: _________________")
        self.pdf.ln(10)
        self.pdf.cell(85, 8, f"{L['sig_advisor']}: _________________")
        self.pdf.cell(85, 8, f"{L['sig_date']}: _________________")

        # ── Footer on all pages ──
        for page_num in range(1, self.pdf.pages_count + 1):
            self.pdf.page = page_num
            self._add_footer()

        return self.pdf.output()


def export_ips_pdf(
    ips_dict: dict,
    output_path: Path,
    audit_trail_dict: Optional[dict] = None,
    locale: str = "zh",
) -> Path:
    """
    Export an IPS to professional PDF format.

    Uses fpdf2 with CJK font support for Chinese text rendering.
    Produces A4-sized pages with headers, footers, structured tables,
    and a professional signature block.

    Args:
        ips_dict: IPSDocument as dict.
        output_path: Output PDF file path.
        audit_trail_dict: Optional AuditTrail as dict.
        locale: Scaffolding language of the document chrome ("zh" / "en").

    Returns:
        Path to the exported PDF file.

    """
    font_path = _find_cjk_font()
    builder = _IPSPDF(font_path, locale=locale)
    pdf_bytes = builder.build(ips_dict, audit_trail_dict, locale=locale)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    return output_path


def export_ips_to_file(
    ips_dict: dict,
    output_path: Path,
    audit_trail_dict: Optional[dict] = None,
    format: str = "markdown",
    locale: str = "zh",
) -> Path:
    """
    Export an IPS to a standalone file.

    Args:
        ips_dict: IPSDocument as dict.
        output_path: Output file path.
        audit_trail_dict: Optional AuditTrail as dict.
        format: 'markdown', 'json', or 'pdf'.
        locale: Scaffolding language of the rendered document ("zh" / "en").

    Returns:
        Path to the exported file.
    """
    if format == "markdown":
        content = export_ips_markdown(ips_dict, audit_trail_dict, locale=locale)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
    elif format == "json":
        record = {"ips": ips_dict}
        if audit_trail_dict:
            record["audit_trail"] = audit_trail_dict
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
    elif format == "pdf":
        return export_ips_pdf(ips_dict, output_path, audit_trail_dict, locale=locale)
    else:
        raise ValueError(f"Unsupported format: {format}")

    return output_path


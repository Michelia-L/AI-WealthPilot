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
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import DATA_DIR
from src.utils import sanitize_filename
from src.agents.ips_models import IPSDocument, AuditTrail


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

    # Quantitative risk anchors (if any are provided)
    _has_quant = any(risk.get(k) is not None for k in [
        "max_acceptable_annual_loss", "target_volatility_min",
        "target_volatility_max", "var_tolerance_95", "max_drawdown_tolerance"
    ])
    if _has_quant:
        lines.append("### 量化风险指标")
        lines.append("")
        lines.append("| 指标 | 阈值 |")
        lines.append("|------|------|")
        if risk.get("max_acceptable_annual_loss") is not None:
            lines.append(f"| 最大可接受年度亏损 | {risk['max_acceptable_annual_loss']:.2%} |")
        if risk.get("target_volatility_min") is not None and risk.get("target_volatility_max") is not None:
            lines.append(f"| 目标波动率区间 | {risk['target_volatility_min']:.2%} – {risk['target_volatility_max']:.2%} |")
        if risk.get("var_tolerance_95") is not None:
            lines.append(f"| 95% VaR 容忍度（年化） | {risk['var_tolerance_95']:.2%} |")
        if risk.get("max_drawdown_tolerance") is not None:
            lines.append(f"| 最大回撤容忍度 | {risk['max_drawdown_tolerance']:.2%} |")
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
    # Derive currency symbol from currency_policy or default to ¥ (CNY)
    _currency_symbols = {"CNY": "¥", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "HKD": "HK$"}
    _base_curr = (ips.get("currency_policy") or {}).get("base_currency", "CNY")
    _curr_sym = _currency_symbols.get(_base_curr, _base_curr + " ")
    lines.append("## 六、流动性约束")
    lines.append("")
    lines.append(f"- **即时流动性需求**: {_curr_sym}{liq.get('immediate_needs', 0):,.0f}")
    lines.append(f"- **持续性需求（年）**: {_curr_sym}{liq.get('ongoing_needs', 0):,.0f}")
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

    # Fee Schedule (if provided)
    fee = ips.get("fee_schedule")
    if fee:
        lines.append("## 十一、费用与成本披露")
        lines.append("")
        lines.append("| 费用项目 | 费率 |")
        lines.append("|----------|------|")
        lines.append(f"| 投资管理费 | {fee.get('management_fee_rate', 0):.2%} |")
        lines.append(f"| 托管费 | {fee.get('custody_fee_rate', 0):.2%} |")
        lines.append(f"| 预估交易成本 | {fee.get('transaction_cost_estimate', 0):.2%} |")
        lines.append(f"| **总费用率 (TER)** | **{fee.get('total_expense_ratio', 0):.2%}** |")
        lines.append("")
        if fee.get("net_return_impact"):
            lines.append(f"**净收益影响**: {fee['net_return_impact']}")
            lines.append("")
        lines.append(fee.get("fee_narrative", ""))
        lines.append("")

        # Adjust section numbering for subsequent sections
        mon_section = "十二"
        disclosure_section = "十三"
    else:
        mon_section = "十一"
        disclosure_section = "十二"

    # Monitoring
    mon = ips.get("monitoring", {})
    lines.append(f"## {mon_section}、监控与评估")
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
    lines.append(f"## {disclosure_section}、风险披露与合规声明")
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


class _IPSPDF:
    """
    Internal PDF builder for IPS documents.

    Wraps fpdf2 FPDF with CJK font support, consistent styling,
    and IPS-specific rendering methods.
    """

    def __init__(self, font_path: Optional[str] = None) -> None:
        from fpdf import FPDF

        self.pdf = FPDF(orientation="P", unit="mm", format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=25)
        self._font_family = "Helvetica"

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
        self.pdf.cell(0, 5, f"AI WealthPilot — {client_name} 投资政策声明书", align="C")
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
        self.pdf.cell(0, 10, f"第 {self.pdf.page_no()} 页", align="C")
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

    def build(self, ips_dict: dict, audit_trail_dict: Optional[dict] = None) -> bytes:
        """
        Build the complete PDF from an IPS dict.

        Args:
            ips_dict: IPSDocument as dict.
            audit_trail_dict: Optional AuditTrail as dict.

        Returns:
            PDF content as bytes.
        """
        ips = ips_dict
        client_name = ips.get("client_name", "N/A")

        # ── Cover info ──
        self.pdf.add_page()
        self._add_header(client_name)

        self.pdf.set_font(self._font_family, "B", 22)
        self.pdf.set_text_color(26, 54, 93)
        self.pdf.ln(10)
        self.pdf.cell(0, 12, "投资政策声明书 (IPS)", align="C")
        self.pdf.ln(15)
        self.pdf.set_text_color(0, 0, 0)

        self.pdf.set_font(self._font_family, "", 11)
        self._key_value("客户", client_name)
        self._key_value("编制方", ips.get("prepared_by", "N/A"))
        self._key_value("编制日期", ips.get("preparation_date", "N/A"))
        self._key_value("版本", ips.get("version", "N/A"))
        self.pdf.ln(5)

        # ── 1. Executive Summary ──
        self._section_title("一、执行摘要")
        self._body_text(ips.get("executive_summary", ""))

        # ── 2. Client Background ──
        self._section_title("二、客户背景")
        self._body_text(ips.get("client_background", ""))

        # ── 3. Return Objectives ──
        ret = ips.get("return_objective", {})
        self._section_title("三、收益目标")
        nom = ret.get("required_nominal_return", 0)
        real = ret.get("required_real_return", 0)
        self._key_value("所需名义年化收益率", f"{nom:.2%}")
        self._key_value("所需实际年化收益率", f"{real:.2%}")
        self._key_value("计算依据", ret.get("return_calculation_basis", ""))
        self._body_text(ret.get("return_objective_narrative", ""))

        # ── 4. Risk Tolerance ──
        risk = ips.get("risk_tolerance", {})
        self._section_title("四、风险承受能力")
        self._key_value("综合风险等级", risk.get("overall_risk_level", ""))
        self._subsection_title("客观承受能力评估")
        self._body_text(risk.get("ability_assessment", ""))
        self._subsection_title("主观承担意愿评估")
        self._body_text(risk.get("willingness_assessment", ""))
        if risk.get("conflict_resolution"):
            self._subsection_title("冲突处理")
            self._body_text(risk["conflict_resolution"])
        self._body_text(risk.get("risk_narrative", ""))

        # Quantitative risk anchors
        quant_rows = []
        if risk.get("max_acceptable_annual_loss") is not None:
            quant_rows.append(["最大可接受年度亏损", f"{risk['max_acceptable_annual_loss']:.2%}"])
        if risk.get("target_volatility_min") is not None and risk.get("target_volatility_max") is not None:
            quant_rows.append(["目标波动率区间", f"{risk['target_volatility_min']:.2%} – {risk['target_volatility_max']:.2%}"])
        if risk.get("var_tolerance_95") is not None:
            quant_rows.append(["95% VaR 容忍度", f"{risk['var_tolerance_95']:.2%}"])
        if risk.get("max_drawdown_tolerance") is not None:
            quant_rows.append(["最大回撤容忍度", f"{risk['max_drawdown_tolerance']:.2%}"])
        if quant_rows:
            self._subsection_title("量化风险指标")
            self._simple_table(["指标", "阈值"], quant_rows, [85, 85])

        # ── 5. Time Horizon ──
        th = ips.get("time_horizon", {})
        self._section_title("五、投资期限")
        self._key_value("总投资期限", f"{th.get('overall_horizon_years', 0)} 年")
        for stage in th.get("stages", []):
            self._body_text(f"• {stage.get('name', '')}: {stage.get('years', 0)} 年 — {stage.get('description', '')}")
        self._body_text(th.get("horizon_narrative", ""))

        # ── 6. Liquidity ──
        liq = ips.get("liquidity", {})
        self._section_title("六、流动性约束")
        self._key_value("即时流动性需求", f"¥{liq.get('immediate_needs', 0):,.0f}")
        self._key_value("持续性需求（年）", f"¥{liq.get('ongoing_needs', 0):,.0f}")
        self._key_value("应急储备", f"{liq.get('emergency_reserve_months', 0)} 个月")
        self._body_text(liq.get("liquidity_narrative", ""))

        # ── 7. Tax ──
        tax = ips.get("tax", {})
        self._section_title("七、税务约束")
        self._key_value("税务身份", tax.get("tax_status", ""))
        self._body_text(tax.get("tax_narrative", ""))

        # ── 8. Legal ──
        legal = ips.get("legal", {})
        self._section_title("八、法律与监管约束")
        for reg in legal.get("applicable_regulations", []):
            self._body_text(f"• {reg}")
        self._body_text(legal.get("legal_narrative", ""))

        # ── 9. Unique Circumstances ──
        unique = ips.get("unique_circumstances", {})
        self._section_title("九、特殊情况")
        if unique.get("esg_preferences"):
            self._key_value("ESG 偏好", unique["esg_preferences"])
        if unique.get("sector_restrictions"):
            self._key_value("行业限制", ", ".join(unique["sector_restrictions"]))
        if unique.get("concentrated_positions"):
            self._key_value("集中持仓", unique["concentrated_positions"])
        self._body_text(unique.get("unique_narrative", ""))

        # ── 10. Investment Guidelines ──
        guide = ips.get("investment_guidelines", {})
        self._section_title("十、投资指引与政策")
        self._subsection_title("战略性资产配置")
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
                ["资产类别", "目标权重", "最低权重", "最高权重"],
                saa_rows, [50, 40, 40, 40]
            )
        self._body_text(f"允许的投资工具: {', '.join(guide.get('permitted_instruments', []))}")
        self._body_text(f"禁止的投资工具: {', '.join(guide.get('prohibited_instruments', []))}")
        self._body_text(f"再平衡政策: {guide.get('rebalancing_policy', '')}")
        self._body_text(guide.get("guideline_narrative", ""))

        # ── 11. Fee Schedule (optional) ──
        fee = ips.get("fee_schedule")
        section_num = 11
        if fee:
            self._section_title(f"十一、费用与成本披露")
            fee_rows = [
                ["投资管理费", f"{fee.get('management_fee_rate', 0):.2%}"],
                ["托管费", f"{fee.get('custody_fee_rate', 0):.2%}"],
                ["预估交易成本", f"{fee.get('transaction_cost_estimate', 0):.2%}"],
                ["总费用率 (TER)", f"{fee.get('total_expense_ratio', 0):.2%}"],
            ]
            self._simple_table(["费用项目", "费率"], fee_rows, [85, 85])
            if fee.get("net_return_impact"):
                self._key_value("净收益影响", fee["net_return_impact"])
            self._body_text(fee.get("fee_narrative", ""))
            section_num = 12
            mon_label = "十二"
            disc_label = "十三"
        else:
            mon_label = "十一"
            disc_label = "十二"

        # ── Monitoring ──
        mon = ips.get("monitoring", {})
        self._section_title(f"{mon_label}、监控与评估")
        self._key_value("审查频率", mon.get("review_frequency", ""))
        if mon.get("benchmarks"):
            self._subsection_title("绩效基准")
            for bm in mon["benchmarks"]:
                self._body_text(f"• {bm.get('asset_class', '')}: {bm.get('benchmark', '')}")
        self._body_text(mon.get("monitoring_narrative", ""))

        # ── Risk Disclosure & Compliance ──
        self._section_title(f"{disc_label}、风险披露与合规声明")
        self._subsection_title("风险披露")
        self._body_text(ips.get("risk_disclosure", ""))
        self._subsection_title("合规声明")
        self._body_text(ips.get("compliance_statement", ""))

        # ── Signature Block ──
        self.pdf.ln(10)
        self.pdf.set_draw_color(60, 60, 60)
        self.pdf.line(20, self.pdf.get_y(), 190, self.pdf.get_y())
        self.pdf.ln(8)
        self.pdf.set_font(self._font_family, "B", 10)
        self.pdf.cell(85, 8, "客户签名: _________________")
        self.pdf.cell(85, 8, "日期: _________________")
        self.pdf.ln(10)
        self.pdf.cell(85, 8, "顾问签名: _________________")
        self.pdf.cell(85, 8, "日期: _________________")

        # ── Footer on all pages ──
        for page_num in range(1, self.pdf.pages_count + 1):
            self.pdf.page = page_num
            self._add_footer()

        return self.pdf.output()


def export_ips_pdf(
    ips_dict: dict,
    output_path: Path,
    audit_trail_dict: Optional[dict] = None,
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

    Returns:
        Path to the exported PDF file.

    """
    font_path = _find_cjk_font()
    builder = _IPSPDF(font_path)
    pdf_bytes = builder.build(ips_dict, audit_trail_dict)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    return output_path


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
        format: 'markdown', 'json', or 'pdf'.

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
    elif format == "pdf":
        return export_ips_pdf(ips_dict, output_path, audit_trail_dict)
    else:
        raise ValueError(f"Unsupported format: {format}")

    return output_path


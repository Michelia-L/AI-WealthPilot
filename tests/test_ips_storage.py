"""
Tests for IPS Storage & Export Module.

Covers:
    - PDF export (export_ips_pdf, export_ips_to_file with format='pdf')
    - Markdown export with fee schedule and risk anchors
    - CJK font discovery
    - export_ips_to_file format routing
"""

import pytest
from pathlib import Path

from src.agents.ips_storage import (
    export_ips_markdown,
    export_ips_pdf,
    export_ips_to_file,
    _find_cjk_font,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_ips_dict() -> dict:
    """A complete sample IPS dict for export testing."""
    return {
        "client_name": "张明",
        "prepared_by": "AI WealthPilot IPS Generator",
        "preparation_date": "2026-06-16",
        "version": "1.0",
        "executive_summary": "本IPS为张明先生编制，综合风险等级为平衡型。",
        "client_background": "张明先生，35岁，科技行业高管。",
        "return_objective": {
            "required_nominal_return": 0.08,
            "required_real_return": 0.055,
            "return_calculation_basis": "TVM: (FV/PV)^(1/n)-1",
            "return_objective_narrative": "基于退休和教育两个目标的加权收益率。",
        },
        "risk_tolerance": {
            "ability_assessment": "客观风险承受能力较高。",
            "willingness_assessment": "主观风险承担意愿中等。",
            "overall_risk_level": "moderate",
            "risk_narrative": "综合风险评估为平衡型。",
            "max_acceptable_annual_loss": -0.15,
            "target_volatility_min": 0.10,
            "target_volatility_max": 0.15,
            "var_tolerance_95": -0.20,
            "max_drawdown_tolerance": -0.25,
        },
        "time_horizon": {
            "stages": [
                {"name": "积累期", "years": 15, "description": "财富积累阶段"},
                {"name": "分配期", "years": 20, "description": "退休支出阶段"},
            ],
            "overall_horizon_years": 35,
            "horizon_narrative": "多阶段投资期限。",
        },
        "liquidity": {
            "immediate_needs": 100000.0,
            "ongoing_needs": 200000.0,
            "emergency_reserve_months": 6,
            "liquidity_narrative": "流动性需求充足。",
        },
        "tax": {"tax_status": "中国居民个人", "tax_narrative": "适用个人所得税。"},
        "legal": {
            "applicable_regulations": ["《证券法》", "《基金法》"],
            "legal_narrative": "合规运营。",
        },
        "unique_circumstances": {
            "esg_preferences": "偏好清洁能源",
            "sector_restrictions": ["烟草", "军工"],
            "unique_narrative": "无集中持仓。",
        },
        "investment_guidelines": {
            "strategic_allocation": [
                {"asset_class": "权益类", "target_weight": 0.60, "min_weight": 0.50, "max_weight": 0.70, "rationale": "长期增长"},
                {"asset_class": "固定收益", "target_weight": 0.30, "min_weight": 0.20, "max_weight": 0.40, "rationale": "稳定收益"},
                {"asset_class": "现金等价物", "target_weight": 0.10, "min_weight": 0.05, "max_weight": 0.15, "rationale": "流动性储备"},
            ],
            "permitted_instruments": ["ETF", "公募基金", "国债"],
            "prohibited_instruments": ["杠杆ETF", "期货"],
            "rebalancing_policy": "季度再平衡",
            "guideline_narrative": "标准60/30/10配置。",
        },
        "fee_schedule": {
            "management_fee_rate": 0.01,
            "custody_fee_rate": 0.002,
            "transaction_cost_estimate": 0.003,
            "total_expense_ratio": 0.015,
            "net_return_impact": "总收益率 8.00% - TER 1.50% = 净收益率 6.50%",
            "fee_narrative": "费用结构透明，总费用率处于行业合理区间。",
        },
        "monitoring": {
            "review_frequency": "quarterly",
            "benchmarks": [{"asset_class": "权益类", "benchmark": "沪深300"}],
            "rebalancing_triggers": ["偏离目标权重5%"],
            "monitoring_narrative": "每季度审查。",
        },
        "risk_disclosure": "过往业绩不代表未来表现。投资有风险，入市需谨慎。",
        "compliance_statement": "本报告仅供参考，不构成投资建议。",
    }


# ============================================================
# Test: CJK Font Discovery
# ============================================================

class TestCJKFontDiscovery:
    """Tests for CJK font finding utility."""

    def test_find_cjk_font_returns_path_or_none(self):
        """Test that _find_cjk_font returns a valid path or None."""
        result = _find_cjk_font()
        if result is not None:
            assert Path(result).exists()


# ============================================================
# Test: PDF Export
# ============================================================

class TestPDFExport:
    """Tests for PDF export functionality."""

    def test_export_creates_file(self, sample_ips_dict, tmp_path):
        """Test that export_ips_pdf creates a valid PDF file."""
        output = tmp_path / "test_ips.pdf"
        result = export_ips_pdf(sample_ips_dict, output)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_pdf_has_valid_header(self, sample_ips_dict, tmp_path):
        """Test that exported PDF has valid PDF magic bytes."""
        output = tmp_path / "test_ips.pdf"
        export_ips_pdf(sample_ips_dict, output)
        with open(output, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_export_without_fee_schedule(self, sample_ips_dict, tmp_path):
        """Test PDF export works without fee_schedule."""
        data = sample_ips_dict.copy()
        data.pop("fee_schedule", None)
        output = tmp_path / "no_fee.pdf"
        result = export_ips_pdf(data, output)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_export_without_risk_anchors(self, sample_ips_dict, tmp_path):
        """Test PDF export works without quantitative risk anchors."""
        data = sample_ips_dict.copy()
        risk = data["risk_tolerance"].copy()
        for k in ["max_acceptable_annual_loss", "target_volatility_min",
                   "target_volatility_max", "var_tolerance_95", "max_drawdown_tolerance"]:
            risk.pop(k, None)
        data["risk_tolerance"] = risk
        output = tmp_path / "no_anchors.pdf"
        result = export_ips_pdf(data, output)
        assert result.exists()

    def test_export_creates_parent_directories(self, sample_ips_dict, tmp_path):
        """Test that export_ips_pdf creates parent dirs if needed."""
        output = tmp_path / "nested" / "dir" / "test.pdf"
        result = export_ips_pdf(sample_ips_dict, output)
        assert result.exists()

    def test_export_ips_to_file_pdf_format(self, sample_ips_dict, tmp_path):
        """Test export_ips_to_file with format='pdf'."""
        output = tmp_path / "via_router.pdf"
        result = export_ips_to_file(sample_ips_dict, output, format="pdf")
        assert result.exists()
        with open(result, "rb") as f:
            assert f.read(5) == b"%PDF-"


# ============================================================
# Test: Markdown Export Enhancements
# ============================================================

class TestMarkdownExportEnhancements:
    """Tests for markdown export with P1 features."""

    def test_fee_schedule_rendered(self, sample_ips_dict):
        """Test that fee schedule is included in markdown output."""
        md = export_ips_markdown(sample_ips_dict)
        assert "费用与成本披露" in md
        assert "投资管理费" in md
        assert "1.00%" in md
        assert "TER" in md

    def test_dynamic_section_numbering_with_fees(self, sample_ips_dict):
        """Test section numbering adjusts when fee_schedule present."""
        md = export_ips_markdown(sample_ips_dict)
        # With fees: monitoring = 十二, disclosure = 十三
        assert "十二、监控与评估" in md
        assert "十三、风险披露与合规声明" in md

    def test_dynamic_section_numbering_without_fees(self, sample_ips_dict):
        """Test section numbering when fee_schedule absent."""
        data = sample_ips_dict.copy()
        data.pop("fee_schedule", None)
        md = export_ips_markdown(data)
        # Without fees: monitoring = 十一, disclosure = 十二
        assert "十一、监控与评估" in md
        assert "十二、风险披露与合规声明" in md

    def test_quantitative_risk_anchors_rendered(self, sample_ips_dict):
        """Test that quantitative risk anchors are in markdown output."""
        md = export_ips_markdown(sample_ips_dict)
        assert "量化风险指标" in md
        assert "最大可接受年度亏损" in md
        assert "-15.00%" in md
        assert "目标波动率区间" in md

    def test_no_risk_anchors_when_absent(self, sample_ips_dict):
        """Test that risk anchor table is omitted when no anchors provided."""
        data = sample_ips_dict.copy()
        risk = data["risk_tolerance"].copy()
        for k in ["max_acceptable_annual_loss", "target_volatility_min",
                   "target_volatility_max", "var_tolerance_95", "max_drawdown_tolerance"]:
            risk.pop(k, None)
        data["risk_tolerance"] = risk
        md = export_ips_markdown(data)
        assert "量化风险指标" not in md

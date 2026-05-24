"""
AI WealthPilot - Tests for Profile Comparison & Enhanced Export
AI WealthPilot - 画像对比分析与增强导出功能测试

Tests for Phase 3 Step 6 (Profile Comparison) and Step 7 (Enhanced Export).

CFA Reference / CFA 参考:
    - Client profiling and IPS framework
    - Documentation and record-keeping requirements
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
    compare_profiles,
    format_comparison_report,
    identify_behavioral_biases,
    save_profile,
    load_profile,
)
from src.agents.report_storage import (
    StoredReport,
    save_report,
    load_report,
    export_report_markdown,
    export_report_html,
    export_report_to_file,
    _markdown_to_html,
    get_export_formats,
)


# ============================================================
# Fixtures / 测试夹具
# ============================================================

@pytest.fixture
def young_conservative_profile():
    """
    Young, conservative investor profile.
    年轻保守型投资者画像。
    """
    return ClientProfile(
        name="Young Conservative",
        age=25,
        marital_status="single",
        dependents=0,
        financial=FinancialSituation(
            annual_income=80000,
            annual_expenses=50000,
            investable_assets=100000,
            total_liabilities=20000,
            emergency_fund_months=6,
        ),
        goals=[
            InvestmentGoal(
                name="Retirement",
                target_amount=2000000,
                years=40,
                priority="high",
            ),
        ],
        time_horizon_years=40,
        tax_status="taxable",
        risk_profile=RiskProfile(
            ability_score=3.5,
            willingness_score=2.0,
            tolerance_level="Conservative",
        ),
    )


@pytest.fixture
def middle_aged_aggressive_profile():
    """
    Middle-aged, aggressive investor profile.
    中年激进型投资者画像。
    """
    return ClientProfile(
        name="Middle Aggressive",
        age=45,
        marital_status="married",
        dependents=2,
        financial=FinancialSituation(
            annual_income=250000,
            annual_expenses=120000,
            investable_assets=1500000,
            total_liabilities=300000,
            emergency_fund_months=8,
        ),
        goals=[
            InvestmentGoal(
                name="Retirement",
                target_amount=5000000,
                years=20,
                priority="high",
            ),
            InvestmentGoal(
                name="Education",
                target_amount=500000,
                years=10,
                priority="medium",
            ),
        ],
        time_horizon_years=20,
        tax_status="taxable",
        risk_profile=RiskProfile(
            ability_score=4.5,
            willingness_score=4.8,
            tolerance_level="Aggressive",
        ),
    )


@pytest.fixture
def retiree_profile():
    """
    Retiree profile with low risk tolerance.
    退休人员画像，低风险容忍度。
    """
    return ClientProfile(
        name="Retiree",
        age=68,
        marital_status="widowed",
        dependents=0,
        financial=FinancialSituation(
            annual_income=80000,
            annual_expenses=60000,
            investable_assets=1200000,
            total_liabilities=0,
            emergency_fund_months=12,
        ),
        goals=[
            InvestmentGoal(
                name="Income",
                target_amount=50000,
                years=20,
                priority="high",
            ),
        ],
        time_horizon_years=20,
        tax_status="tax-deferred",
        risk_profile=RiskProfile(
            ability_score=3.0,
            willingness_score=2.5,
            tolerance_level="Conservative",
        ),
    )


@pytest.fixture
def sample_report():
    """
    Sample advisory report for testing.
    用于测试的示例建议书。
    """
    return StoredReport(
        report_id="test_report_001",
        client_name="Test Client",
        profile_filepath="/path/to/profile.json",
        content="""# Investment Advisory Report

## Summary

This is a **test** report with *italic* text.

### Key Recommendations

- Diversify across asset classes
- Maintain 6-month emergency fund
- Consider tax-efficient strategies

---

## Conclusion

The portfolio should be reviewed annually.
""",
        model="deepseek-v4-pro",
        generated_at="2026-05-30T12:00:00",
        prompt_tokens=1500,
        completion_tokens=2000,
        total_tokens=3500,
        filepath="/path/to/report.json",
        notes="Test report notes",
    )


# ============================================================
# Tests: Profile Comparison / 画像对比测试
# ============================================================

class TestProfileComparison:
    """
    Tests for compare_profiles function.
    compare_profiles 函数测试。
    """

    def test_compare_two_profiles(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test comparing two profiles returns valid comparison.
        测试对比两个画像返回有效的对比结果。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        assert len(comparison.client_names) == 2
        assert "Young Conservative" in comparison.client_names
        assert "Middle Aggressive" in comparison.client_names

    def test_compare_three_profiles(
        self,
        young_conservative_profile,
        middle_aged_aggressive_profile,
        retiree_profile,
    ):
        """
        Test comparing three profiles.
        测试对比三个画像。
        """
        comparison = compare_profiles(
            [
                young_conservative_profile,
                middle_aged_aggressive_profile,
                retiree_profile,
            ]
        )

        assert len(comparison.client_names) == 3
        assert len(comparison.risk_score_comparison) == 3

    def test_risk_score_comparison(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test that risk scores are correctly compared.
        测试风险评分是否正确对比。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        # Middle-aged aggressive should have higher risk score
        assert (
            comparison.risk_score_comparison["Middle Aggressive"]
            > comparison.risk_score_comparison["Young Conservative"]
        )

    def test_net_worth_comparison(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test net worth comparison.
        测试净资产对比。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        # Middle-aged aggressive has higher net worth
        assert (
            comparison.net_worth_comparison["Middle Aggressive"]
            > comparison.net_worth_comparison["Young Conservative"]
        )

    def test_savings_rate_comparison(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test savings rate comparison.
        测试储蓄率对比。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        # Both should have valid savings rates
        assert comparison.savings_rate_comparison["Young Conservative"] == pytest.approx(
            0.375, abs=0.01
        )  # (80000-50000)/80000
        assert comparison.savings_rate_comparison["Middle Aggressive"] == pytest.approx(
            0.52, abs=0.01
        )  # (250000-120000)/250000

    def test_bias_count_comparison(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test behavioral bias count comparison.
        测试行为偏差数量对比。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        # Both should have bias counts >= 0
        assert comparison.bias_count_comparison["Young Conservative"] >= 0
        assert comparison.bias_count_comparison["Middle Aggressive"] >= 0

    def test_financial_summary_structure(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test financial summary has correct structure.
        测试财务概要有正确的结构。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        # Check that financial summary contains required keys
        for name in comparison.client_names:
            summary = comparison.financial_summary[name]
            assert "annual_income" in summary
            assert "net_worth" in summary
            assert "annual_savings" in summary
            assert "savings_rate" in summary
            assert "emergency_fund_months" in summary
            assert "risk_score" in summary
            assert "risk_level" in summary

    def test_insights_generated(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test that insights are generated for profiles with differences.
        测试有差异的画像会生成洞察。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        # Should have at least one insight due to risk score difference
        assert len(comparison.insights) > 0

    def test_minimum_profiles_required(self, young_conservative_profile):
        """
        Test that at least 2 profiles are required.
        测试至少需要 2 个画像。
        """
        with pytest.raises(ValueError, match="At least 2 profiles"):
            compare_profiles([young_conservative_profile])

    def test_empty_profiles_raises_error(self):
        """
        Test that empty list raises ValueError.
        测试空列表引发 ValueError。
        """
        with pytest.raises(ValueError):
            compare_profiles([])

    def test_comparison_date_set(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test that comparison date is set.
        测试对比日期是否设置。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )

        # Should have a valid ISO date
        assert comparison.comparison_date
        datetime.fromisoformat(comparison.comparison_date)  # Should not raise


# ============================================================
# Tests: Comparison Report Formatting / 对比报告格式化测试
# ============================================================

class TestComparisonReportFormatting:
    """
    Tests for format_comparison_report function.
    format_comparison_report 函数测试。
    """

    def test_report_contains_header(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test report contains comparison header.
        测试报告包含对比标题。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )
        report = format_comparison_report(comparison)

        assert "CLIENT PROFILE COMPARISON REPORT" in report
        assert "客户画像对比报告" in report

    def test_report_contains_client_names(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test report contains all client names.
        测试报告包含所有客户名称。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )
        report = format_comparison_report(comparison)

        assert "Young Conservative" in report
        assert "Middle Aggressive" in report

    def test_report_contains_risk_section(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test report contains risk comparison section.
        测试报告包含风险对比部分。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )
        report = format_comparison_report(comparison)

        assert "RISK PROFILE COMPARISON" in report
        assert "风险画像对比" in report

    def test_report_contains_financial_section(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test report contains financial comparison section.
        测试报告包含财务对比部分。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )
        report = format_comparison_report(comparison)

        assert "FINANCIAL COMPARISON" in report
        assert "财务对比" in report

    def test_report_contains_insights_section(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test report contains insights section.
        测试报告包含洞察部分。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )
        report = format_comparison_report(comparison)

        assert "KEY INSIGHTS" in report
        assert "关键洞察" in report

    def test_report_contains_bias_section(
        self, young_conservative_profile, middle_aged_aggressive_profile
    ):
        """
        Test report contains behavioral biases section.
        测试报告包含行为偏差部分。
        """
        comparison = compare_profiles(
            [young_conservative_profile, middle_aged_aggressive_profile]
        )
        report = format_comparison_report(comparison)

        assert "BEHAVIORAL BIASES" in report
        assert "行为偏差" in report


# ============================================================
# Tests: HTML Export / HTML 导出测试
# ============================================================

class TestHTMLExport:
    """
    Tests for HTML export functionality.
    HTML 导出功能测试。
    """

    def test_export_html_returns_string(self, sample_report):
        """
        Test that export_report_html returns a string.
        测试 export_report_html 返回字符串。
        """
        html = export_report_html(sample_report)

        assert isinstance(html, str)
        assert len(html) > 0

    def test_html_contains_doctype(self, sample_report):
        """
        Test HTML contains DOCTYPE declaration.
        测试 HTML 包含 DOCTYPE 声明。
        """
        html = export_report_html(sample_report)

        assert "<!DOCTYPE html>" in html

    def test_html_contains_client_name(self, sample_report):
        """
        Test HTML contains client name.
        测试 HTML 包含客户名称。
        """
        html = export_report_html(sample_report)

        assert "Test Client" in html

    def test_html_contains_model_name(self, sample_report):
        """
        Test HTML contains AI model name.
        测试 HTML 包含 AI 模型名称。
        """
        html = export_report_html(sample_report)

        assert "deepseek-v4-pro" in html

    def test_html_contains_token_usage(self, sample_report):
        """
        Test HTML contains token usage.
        测试 HTML 包含 token 用量。
        """
        html = export_report_html(sample_report)

        assert "3,500" in html  # total_tokens formatted with comma

    def test_html_contains_styling(self, sample_report):
        """
        Test HTML contains CSS styling.
        测试 HTML 包含 CSS 样式。
        """
        html = export_report_html(sample_report)

        assert "<style>" in html
        assert "font-family" in html

    def test_html_contains_report_id(self, sample_report):
        """
        Test HTML contains report ID in footer.
        测试 HTML 在页脚包含报告 ID。
        """
        html = export_report_html(sample_report)

        assert "test_report_001" in html

    def test_html_contains_disclaimer(self, sample_report):
        """
        Test HTML contains disclaimer.
        测试 HTML 包含免责声明。
        """
        html = export_report_html(sample_report)

        assert "does not constitute financial advice" in html
        assert "不构成投资建议" in html


# ============================================================
# Tests: Markdown to HTML Conversion / Markdown 转 HTML 测试
# ============================================================

class TestMarkdownToHTML:
    """
    Tests for _markdown_to_html conversion function.
    _markdown_to_html 转换函数测试。
    """

    def test_headers_conversion(self):
        """
        Test Markdown headers are converted to HTML.
        测试 Markdown 标题转换为 HTML。
        """
        md = "# H1\n## H2\n### H3"
        html = _markdown_to_html(md)

        assert "<h1>H1</h1>" in html
        assert "<h2>H2</h2>" in html
        assert "<h3>H3</h3>" in html

    def test_bold_conversion(self):
        """
        Test bold text conversion.
        测试粗体文本转换。
        """
        md = "This is **bold** text."
        html = _markdown_to_html(md)

        assert "<strong>bold</strong>" in html

    def test_italic_conversion(self):
        """
        Test italic text conversion.
        测试斜体文本转换。
        """
        md = "This is *italic* text."
        html = _markdown_to_html(md)

        assert "<em>italic</em>" in html

    def test_list_conversion(self):
        """
        Test list items conversion.
        测试列表项转换。
        """
        md = "- Item 1\n- Item 2\n- Item 3"
        html = _markdown_to_html(md)

        assert "<ul>" in html
        assert "<li>Item 1</li>" in html
        assert "<li>Item 2</li>" in html
        assert "<li>Item 3</li>" in html

    def test_horizontal_rule_conversion(self):
        """
        Test horizontal rule conversion.
        测试水平线转换。
        """
        md = "Above\n\n---\n\nBelow"
        html = _markdown_to_html(md)

        assert "<hr>" in html


# ============================================================
# Tests: Export Format Support / 导出格式支持测试
# ============================================================

class TestExportFormats:
    """
    Tests for export format support.
    导出格式支持测试。
    """

    def test_get_export_formats(self):
        """
        Test get_export_formats returns all supported formats.
        测试 get_export_formats 返回所有支持的格式。
        """
        formats = get_export_formats()

        assert len(formats) == 3
        format_names = [f["format"] for f in formats]
        assert "markdown" in format_names
        assert "html" in format_names
        assert "json" in format_names

    def test_export_format_structure(self):
        """
        Test export format dict has correct structure.
        测试导出格式字典有正确的结构。
        """
        formats = get_export_formats()

        for fmt in formats:
            assert "format" in fmt
            assert "extension" in fmt
            assert "description" in fmt

    def test_export_to_html_file(self, sample_report, tmp_path):
        """
        Test exporting report to HTML file.
        测试导出报告到 HTML 文件。
        """
        output_path = tmp_path / "test_report.html"
        result = export_report_to_file(sample_report, output_path, format="html")

        assert result.exists()
        assert result.suffix == ".html"

        # Verify HTML content
        content = result.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Test Client" in content

    def test_export_to_markdown_file(self, sample_report, tmp_path):
        """
        Test exporting report to Markdown file.
        测试导出报告到 Markdown 文件。
        """
        output_path = tmp_path / "test_report.md"
        result = export_report_to_file(sample_report, output_path, format="markdown")

        assert result.exists()
        assert result.suffix == ".md"

    def test_export_to_json_file(self, sample_report, tmp_path):
        """
        Test exporting report to JSON file.
        测试导出报告到 JSON 文件。
        """
        output_path = tmp_path / "test_report.json"
        result = export_report_to_file(sample_report, output_path, format="json")

        assert result.exists()
        assert result.suffix == ".json"

        # Verify JSON content
        with open(result, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["client_name"] == "Test Client"

    def test_export_unsupported_format_raises_error(self, sample_report, tmp_path):
        """
        Test that unsupported format raises ValueError.
        测试不支持的格式引发 ValueError。
        """
        output_path = tmp_path / "test_report.pdf"

        with pytest.raises(ValueError, match="Unsupported format"):
            export_report_to_file(sample_report, output_path, format="pdf")


# ============================================================
# Integration Tests / 集成测试
# ============================================================

class TestComparisonExportIntegration:
    """
    Integration tests for comparison and export features.
    对比与导出功能的集成测试。
    """

    def test_full_comparison_workflow(
        self,
        young_conservative_profile,
        middle_aged_aggressive_profile,
        retiree_profile,
        tmp_path,
    ):
        """
        Test full comparison workflow from profiles to report.
        测试从画像到报告的完整对比工作流。
        """
        # Step 1: Compare profiles / 对比画像
        comparison = compare_profiles(
            [
                young_conservative_profile,
                middle_aged_aggressive_profile,
                retiree_profile,
            ]
        )

        # Step 2: Generate report / 生成报告
        report_text = format_comparison_report(comparison)

        # Step 3: Verify report content / 验证报告内容
        assert "CLIENT PROFILE COMPARISON REPORT" in report_text
        assert len(comparison.insights) > 0

        # Step 4: Save as advisory report / 保存为建议书
        stored = save_report(
            content=report_text,
            client_name="Multi-Client Comparison",
            model="comparison-engine",
            notes="Automated comparison report",
        )

        # Step 5: Verify stored report / 验证存储的报告
        loaded = load_report(Path(stored.filepath))
        assert loaded.client_name == "Multi-Client Comparison"
        assert "CLIENT PROFILE COMPARISON REPORT" in loaded.content

        # Step 6: Export to HTML / 导出为 HTML
        html_path = tmp_path / "comparison_report.html"
        export_report_to_file(loaded, html_path, format="html")

        assert html_path.exists()
        html_content = html_path.read_text(encoding="utf-8")
        assert "Multi-Client Comparison" in html_content

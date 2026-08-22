"""
Locale-aware AI generation tests (Phase 22, step 4).

Covers the ``locale`` parameter added across the LLM prompt builders and the
document scaffolding renderers:

- src prompt builders: locale="zh" (and the default) keep the pre-i18n
  Chinese/bilingual prompts verbatim; locale="en" switches to English-only
  writing instructions with no bilingual-structure directives.
- SAA validation findings follow the workflow state's locale.
- Document scaffolding (markdown/HTML/PDF chrome) renders in English under
  locale="en".
- Routers resolve X-Locale and pass it through to the src generation calls.

The LLM is never called: router tests monkeypatch the src generation
functions and capture the forwarded ``locale``.
"""

import re

import pytest

from src.agents.advisor import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_EN,
    AdvisorReport,
    _build_messages,
    _build_user_prompt,
    _system_prompt,
)
from src.agents.ips_agents import (
    build_generation_prompt,
    build_review_prompt,
    build_revision_prompt,
    get_system_prompt,
)
from src.agents.ips_models import ReviewDimension
from src.agents.ips_storage import export_ips_markdown, export_ips_pdf
from src.agents.ips_workflow import IPSWorkflowState, validate_saa_node
from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
)
from src.agents.rebalance_advisor import (
    REBALANCE_SYSTEM_PROMPT,
    REBALANCE_SYSTEM_PROMPT_EN,
)
from src.agents.rebalance_advisor import (
    _build_user_prompt as _build_rebalance_prompt,
)
from src.agents.rebalance_advisor import (
    _system_prompt as _rebalance_system_prompt,
)
from src.agents.report_storage import (
    StoredReport,
    export_report_html,
    export_report_markdown,
    export_report_pdf,
)
from src.portfolio.cme_models import AssetClassCME, CMEReport
from tests.test_api_advisor import _parse_sse
from tests.test_api_profiles import sample_payload

_CJK_RE = re.compile(r"[一-鿿]")


def _has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


@pytest.fixture
def sample_profile():
    return ClientProfile(
        name="Test User",
        age=35,
        marital_status="married",
        dependents=2,
        financial=FinancialSituation(
            annual_income=150_000,
            annual_expenses=80_000,
            investable_assets=500_000,
            total_liabilities=200_000,
            emergency_fund_months=6.0,
        ),
        goals=[
            InvestmentGoal(name="Retirement", target_amount=3_000_000, years=25, priority="high"),
        ],
        time_horizon_years=25,
        risk_profile=RiskProfile(
            ability_score=3.8,
            willingness_score=3.2,
            tolerance_level="Moderate / 平衡型",
        ),
    )


@pytest.fixture
def sample_ips_dict() -> dict:
    """Minimal-but-complete IPS dict for scaffolding render tests."""
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
        },
        "time_horizon": {
            "stages": [{"name": "积累期", "years": 15, "description": "财富积累阶段"}],
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
        "legal": {"applicable_regulations": ["《证券法》"], "legal_narrative": "合规运营。"},
        "unique_circumstances": {"unique_narrative": "无。"},
        "investment_guidelines": {
            "strategic_allocation": [
                {"asset_class": "权益类", "target_weight": 0.60, "min_weight": 0.50, "max_weight": 0.70, "rationale": "长期增长"},
                {"asset_class": "固定收益", "target_weight": 0.40, "min_weight": 0.30, "max_weight": 0.50, "rationale": "稳定收益"},
            ],
            "permitted_instruments": ["ETF", "公募基金"],
            "prohibited_instruments": ["杠杆ETF"],
            "rebalancing_policy": "季度再平衡",
            "guideline_narrative": "标准60/40配置。",
        },
        "fee_schedule": {
            "management_fee_rate": 0.01,
            "custody_fee_rate": 0.002,
            "transaction_cost_estimate": 0.003,
            "total_expense_ratio": 0.015,
            "net_return_impact": "总收益率 8.00% - TER 1.50% = 净收益率 6.50%",
            "fee_narrative": "费用结构透明。",
        },
        "monitoring": {
            "review_frequency": "quarterly",
            "benchmarks": [{"asset_class": "权益类", "benchmark": "沪深300"}],
            "monitoring_narrative": "每季度审查。",
        },
        "risk_disclosure": "过往业绩不代表未来表现。",
        "compliance_statement": "本报告仅供参考，不构成投资建议。",
    }


# ============================================================
# Advisor prompt builders (src/agents/advisor.py)
# ============================================================

class TestAdvisorLocalePrompts:
    def test_default_and_zh_are_identical(self, sample_profile):
        assert _build_user_prompt(sample_profile) == _build_user_prompt(sample_profile, "zh")
        assert _build_user_prompt(sample_profile, locale="zh") == _build_user_prompt(sample_profile)
        assert _system_prompt() == SYSTEM_PROMPT
        assert _system_prompt("zh") == SYSTEM_PROMPT

    def test_zh_prompt_keeps_bilingual_directives(self, sample_profile):
        prompt = _build_user_prompt(sample_profile, "zh")
        assert "请为以下客户生成全面的投资咨询建议书" in prompt
        assert "客户画像" in prompt
        assert "中英双语" in SYSTEM_PROMPT

    def test_en_user_prompt_is_english_only(self, sample_profile):
        prompt = _build_user_prompt(sample_profile, "en")
        assert "CLIENT PROFILE" in prompt
        assert "Name: <client_name>Test User</client_name>" in prompt
        assert "Please write the advisory report entirely in English" in prompt
        # No bilingual-structure scaffolding remains.
        assert "客户画像" not in prompt
        assert "请为以下客户" not in prompt
        assert "请按照你指令" not in prompt

    def test_en_system_prompt_is_english_only(self):
        prompt = _system_prompt("en")
        assert prompt == SYSTEM_PROMPT_EN
        assert "entirely in English" in prompt
        assert "Client Summary" in prompt
        assert "Risk Disclosure" in prompt
        assert "中英双语" not in prompt
        assert not _has_cjk(prompt)

    def test_en_messages_use_en_system_prompt(self, sample_profile):
        messages = _build_messages(sample_profile, "en")
        assert messages[0]["content"] == SYSTEM_PROMPT_EN
        assert not _has_cjk(messages[0]["content"])
        # Default messages keep the original bilingual system prompt.
        assert _build_messages(sample_profile)[0]["content"] == SYSTEM_PROMPT


# ============================================================
# Rebalance prompt builders (src/agents/rebalance_advisor.py)
# ============================================================

class TestRebalanceLocalePrompts:
    MONITORING = {"client_name": "测试客户"}

    def test_default_and_zh_are_identical(self):
        assert (
            _build_rebalance_prompt(self.MONITORING)
            == _build_rebalance_prompt(self.MONITORING, locale="zh")
        )
        assert _rebalance_system_prompt() == REBALANCE_SYSTEM_PROMPT
        assert _rebalance_system_prompt("zh") == REBALANCE_SYSTEM_PROMPT

    def test_zh_prompt_keeps_bilingual_directives(self):
        prompt = _build_rebalance_prompt(self.MONITORING, locale="zh")
        assert "请基于以下量化监控结果生成调衡建议报告" in prompt
        assert "监控结果" in prompt
        assert "中英双语" in REBALANCE_SYSTEM_PROMPT

    def test_en_user_prompt_is_english_only(self):
        prompt = _build_rebalance_prompt(self.MONITORING, locale="en")
        assert "MONITORING RESULTS" in prompt
        assert "Name: <client_name>测试客户</client_name>" in prompt
        assert "Please write the advisory report entirely in English" in prompt
        assert "监控结果" not in prompt
        assert "请基于以下" not in prompt

    def test_en_system_prompt_is_english_only(self):
        prompt = _rebalance_system_prompt("en")
        assert prompt == REBALANCE_SYSTEM_PROMPT_EN
        assert "entirely in English" in prompt
        assert "Drift Diagnosis" in prompt
        assert "中英双语" not in prompt
        assert not _has_cjk(prompt)


# ============================================================
# IPS workflow prompt builders (src/agents/ips_agents.py)
# ============================================================

class TestIpsLocalePrompts:
    ROLES = ("generator", "suitability", "compliance", "consistency", "reviser")

    def test_zh_system_prompts_keep_chinese_directives(self):
        for role in self.ROLES:
            assert get_system_prompt(role) == get_system_prompt(role, "zh")
            assert _has_cjk(get_system_prompt(role, "zh"))
        assert "使用中文撰写所有叙述性内容" in get_system_prompt("generator", "zh")
        assert "使用中文描述所有问题" in get_system_prompt("suitability", "zh")
        assert "使用中文撰写" in get_system_prompt("reviser", "zh")

    def test_en_system_prompts_are_english_only(self):
        for role in self.ROLES:
            prompt = get_system_prompt(role, "en")
            assert prompt != get_system_prompt(role, "zh")
            assert not _has_cjk(prompt), f"{role} EN system prompt contains Chinese"
        assert "Write ALL narrative content in English" in get_system_prompt("generator", "en")
        assert "Describe all issues in English" in get_system_prompt("compliance", "en")
        assert "Write all content in English" in get_system_prompt("reviser", "en")

    def test_en_generator_keeps_quantitative_rules(self):
        prompt = get_system_prompt("generator", "en")
        # The business rules survive translation (risk anchors, CNY default,
        # fee disclosure, cooling-off / KYC compliance elements).
        assert "max_acceptable_annual_loss" in prompt
        assert '"CNY"' in prompt
        assert "total_expense_ratio" in prompt
        assert "24-hour cooling-off period" in prompt
        assert "KYC" in prompt

    def test_generation_prompt_zh_unchanged(self):
        prompt = build_generation_prompt("{}", "TEMPLATE", cme_text="CME TEXT", locale="zh")
        assert "客户画像数据" in prompt
        assert "所有叙述性内容使用中文" in prompt
        assert "资本市场预期 (CME)" in prompt
        assert build_generation_prompt("{}", "TEMPLATE") == build_generation_prompt("{}", "TEMPLATE", locale="zh")

    def test_generation_prompt_en(self):
        prompt = build_generation_prompt("{}", "TEMPLATE", cme_text="CME TEXT", locale="en")
        assert "CLIENT PROFILE DATA" in prompt
        assert "CAPITAL MARKET EXPECTATIONS (CME)" in prompt
        assert "Write all narrative content in English" in prompt
        assert "客户画像数据" not in prompt
        assert "使用中文" not in prompt

    def test_review_prompt_locales(self):
        items = [{"id": "C1", "name": "风险披露", "severity": "critical", "rule": "必须披露"}]
        zh = build_review_prompt("{}", "{}", ReviewDimension.SUITABILITY, items, locale="zh")
        assert "待审查的 IPS 文档" in zh
        assert "合规检查清单" in zh
        assert "规则：" in zh
        assert 'dimension 字段必须设为 "suitability"' in zh

        en = build_review_prompt("{}", "{}", ReviewDimension.SUITABILITY, items, locale="en")
        assert "IPS DOCUMENT UNDER REVIEW" in en
        assert "COMPLIANCE CHECKLIST" in en
        assert "Rule:" in en
        assert 'dimension field must be set to "suitability"' in en
        assert "待审查的 IPS 文档" not in en

    def test_revision_prompt_locales(self):
        zh = build_revision_prompt("{}", "[]", locale="zh")
        assert "当前 IPS 文档" in zh
        assert "审查发现的问题" in zh
        assert build_revision_prompt("{}", "[]") == zh

        en = build_revision_prompt("{}", "[]", locale="en")
        assert "CURRENT IPS DOCUMENT" in en
        assert "ISSUES IDENTIFIED IN REVIEW" in en
        assert "当前 IPS 文档" not in en
        assert not _has_cjk(en)


# ============================================================
# SAA validation messages follow the workflow state locale
# ============================================================

class TestSaaValidationLocale:
    def _cme_report(self) -> dict:
        report = CMEReport(
            as_of_date="2026-06-01",
            data_lookback_years=5,
            risk_free_rate=0.03,
            risk_free_rate_source="test",
            inflation_assumption=0.025,
            asset_classes=[
                AssetClassCME(
                    name="权益", ticker="TEST", expected_return=0.10,
                    volatility=0.20, sharpe_ratio=0.5, max_drawdown=-0.20,
                    var_95=0.02, cvar_95=0.03, data_points=1000,
                ),
                AssetClassCME(
                    name="固收", ticker="TEST2", expected_return=0.04,
                    volatility=0.08, sharpe_ratio=0.3, max_drawdown=-0.05,
                    var_95=0.008, cvar_95=0.012, data_points=1000,
                ),
            ],
            correlation_matrix={
                "权益": {"权益": 1.0, "固收": 0.3},
                "固收": {"权益": 0.3, "固收": 1.0},
            },
            methodology_notes="Test methodology",
        )
        return report.model_dump()

    IPS_DRAFT = {
        "return_objective": {"required_nominal_return": 0.06},
        "risk_tolerance": {"overall_risk_level": "moderate"},
        "investment_guidelines": {
            "strategic_allocation": [
                {"asset_class": "权益", "target_weight": 0.6},
                {"asset_class": "固收", "target_weight": 0.3},
                # Sum = 0.9, not 1.0 → CRITICAL weight-sum issue.
            ],
        },
    }

    def _run(self, locale: str):
        import asyncio

        state = IPSWorkflowState(
            cme_report=self._cme_report(),
            ips_draft=self.IPS_DRAFT,
            review_results=[],
            all_review_issues=[],
            locale=locale,
        )
        return asyncio.run(validate_saa_node(state))

    def test_zh_default_keeps_chinese_messages(self):
        result = self._run("zh")
        issues = result.get("all_review_issues", [])
        weight_issues = [i for i in issues if "权重之和" in i.get("description", "")]
        assert len(weight_issues) == 1
        assert weight_issues[0]["suggestion"] == "调整各资产类别权重使其加总为 100%。"
        summary = result["review_results"][-1]["summary"]
        assert "SAA 量化验证发现" in summary

    def test_en_messages_are_english(self):
        result = self._run("en")
        issues = result.get("all_review_issues", [])
        weight_issues = [
            i for i in issues if "deviating from 100%" in i.get("description", "")
        ]
        assert len(weight_issues) == 1
        assert weight_issues[0]["severity"] == "critical"
        assert not _has_cjk(weight_issues[0]["description"])
        assert not _has_cjk(weight_issues[0]["suggestion"])
        summary = result["review_results"][-1]["summary"]
        assert "Quantitative SAA validation found" in summary
        assert not _has_cjk(summary)

    def test_state_locale_defaults_to_zh(self):
        assert IPSWorkflowState().locale == "zh"


# ============================================================
# Document scaffolding (ips_storage / report_storage)
# ============================================================

class TestScaffoldingLocale:
    def test_ips_markdown_zh_unchanged(self, sample_ips_dict):
        md = export_ips_markdown(sample_ips_dict)
        assert md == export_ips_markdown(sample_ips_dict, locale="zh")
        assert "# 投资政策声明书 (IPS)" in md
        assert "十二、监控与评估" in md  # fee present → monitoring is section 12
        assert "十三、风险披露与合规声明" in md

    def test_ips_markdown_en_scaffolding(self, sample_ips_dict):
        md = export_ips_markdown(sample_ips_dict, locale="en")
        assert "# Investment Policy Statement (IPS)" in md
        assert "## 1. Executive Summary" in md
        assert "| Asset Class | Target Weight | Min Weight | Max Weight | Rationale |" in md
        assert "## 11. Fees & Cost Disclosure" in md
        assert "## 12. Monitoring & Review" in md
        assert "## 13. Risk Disclosure & Compliance Statement" in md
        assert "**Prepared by**: AI WealthPilot IPS Generator" in md
        # Chinese scaffolding is gone (stored narratives stay as-is).
        assert "投资政策声明书" not in md
        assert "执行摘要" not in md
        assert "监控与评估" not in md
        # Stored narrative content is emitted unchanged either way.
        assert "本IPS为张明先生编制，综合风险等级为平衡型。" in md

    def test_ips_markdown_en_without_fee_schedule(self, sample_ips_dict):
        data = {k: v for k, v in sample_ips_dict.items() if k != "fee_schedule"}
        md = export_ips_markdown(data, locale="en")
        assert "## 11. Monitoring & Review" in md
        assert "## 12. Risk Disclosure & Compliance Statement" in md

    def test_ips_pdf_en_builds(self, sample_ips_dict, tmp_path):
        output = export_ips_pdf(sample_ips_dict, tmp_path / "ips_en.pdf", locale="en")
        assert output.exists()
        assert output.read_bytes().startswith(b"%PDF-")
        assert output.stat().st_size > 1000

    def _stored_report(self) -> StoredReport:
        return StoredReport(
            report_id="20260727_000000_000000",
            client_name="张伟",
            content="# 一、客户概况\n正文内容。",
            model="deepseek-v4-pro",
            generated_at="2026-07-27T00:00:00",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

    def test_report_markdown_locales(self):
        report = self._stored_report()
        zh = export_report_markdown(report)
        assert zh == export_report_markdown(report, locale="zh")
        assert zh.startswith("# Investment Advisory Report / 投资咨询建议书")
        assert "**Client / 客户**: 张伟" in zh

        en = export_report_markdown(report, locale="en")
        assert en.startswith("# Investment Advisory Report\n")
        assert "**Client**: 张伟" in en
        assert "投资咨询建议书" not in en
        assert "生成时间" not in en
        # Report body is emitted unchanged either way.
        assert "# 一、客户概况" in en

    def test_report_html_locales(self):
        report = self._stored_report()
        zh = export_report_html(report)
        assert zh == export_report_html(report, locale="zh")
        assert '<html lang="zh-CN">' in zh
        assert "<h1>Investment Advisory Report<br>投资咨询建议书</h1>" in zh
        assert "Client / 客户" in zh
        assert "本报告仅供参考，不构成投资建议。" in zh

        en = export_report_html(report, locale="en")
        assert '<html lang="en">' in en
        assert "<h1>Investment Advisory Report</h1>" in en
        assert ">Client</span>" in en
        assert "投资咨询建议书" not in en
        assert "本报告仅供参考" not in en

    def test_report_pdf_en_builds(self, tmp_path):
        output = export_report_pdf(self._stored_report(), tmp_path / "report_en.pdf", locale="en")
        assert output.exists()
        assert output.read_bytes().startswith(b"%PDF-")


# ============================================================
# Routers forward X-Locale into the src generation calls
# ============================================================

FAKE_MONITORING = {"client_name": "测试客户"}


def _capturing_stream(captured: dict, report_name: str):
    """Fake streaming generator that records the forwarded locale."""

    def fake_stream(*args, **kwargs):
        captured.update(kwargs)
        yield {"type": "token", "text": f"Report for {report_name}."}
        return AdvisorReport(
            content="full content",
            model="deepseek-v4-pro",
            client_name=report_name,
            success=True,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

    return fake_stream


def _create_profile(client) -> int:
    resp = client.post("/api/profiles", json=sample_payload())
    assert resp.status_code == 201
    return resp.json()["id"]


class TestAdvisorRouterLocale:
    @pytest.fixture
    def configured(self, monkeypatch):
        monkeypatch.setattr("api.routers.advisor.is_api_configured", lambda: True)

    def test_stream_forwards_en_locale(self, client, configured, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(
            "api.routers.advisor.generate_advice_stream",
            _capturing_stream(captured, "John Doe"),
        )
        profile_id = _create_profile(client)

        resp = client.post(
            "/api/advisor/report/stream",
            json={"profile_id": profile_id},
            headers={"X-Locale": "en"},
        )
        assert resp.status_code == 200
        assert captured["locale"] == "en"
        assert _parse_sse(resp.text)[-1]["type"] == "done"

    def test_stream_forwards_zh_locale_by_default(self, client, configured, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(
            "api.routers.advisor.generate_advice_stream",
            _capturing_stream(captured, "John Doe"),
        )
        profile_id = _create_profile(client)

        resp = client.post("/api/advisor/report/stream", json={"profile_id": profile_id})
        assert resp.status_code == 200
        assert captured["locale"] == "zh"

    def _save_report(self, client) -> str:
        saved = client.post(
            "/api/advisor/reports",
            json={
                "client_name": "John Doe",
                "content": "# Report\nSome advice.",
                "model": "deepseek-v4-pro",
                "prompt_tokens": 10,
                "completion_tokens": 20,
            },
        )
        assert saved.status_code == 201
        return saved.json()["report_id"]

    def test_export_scaffolding_follows_locale(self, client):
        report_id = self._save_report(client)

        md_en = client.get(
            f"/api/advisor/reports/{report_id}/export?format=markdown",
            headers={"X-Locale": "en"},
        )
        assert md_en.status_code == 200
        assert md_en.text.startswith("# Investment Advisory Report\n")
        assert "投资咨询建议书" not in md_en.text

        html_en = client.get(
            f"/api/advisor/reports/{report_id}/export?format=html",
            headers={"X-Locale": "en"},
        )
        assert '<html lang="en">' in html_en.text
        assert "投资咨询建议书" not in html_en.text

        # The zh default keeps the bilingual scaffolding.
        md_zh = client.get(f"/api/advisor/reports/{report_id}/export?format=markdown")
        assert md_zh.text.startswith("# Investment Advisory Report / 投资咨询建议书")


class TestMonitoringRouterLocale:
    @pytest.fixture
    def configured(self, monkeypatch):
        monkeypatch.setattr("api.routers.monitoring.is_api_configured", lambda: True)
        monkeypatch.setattr(
            "api.routers.monitoring.compute_monitoring",
            lambda document_id, locale="zh": dict(FAKE_MONITORING),
        )

    def test_advice_forwards_en_locale(self, client, configured, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(
            "api.routers.monitoring.generate_rebalance_advice_stream",
            _capturing_stream(captured, "测试客户"),
        )
        resp = client.post(
            "/api/monitoring/advice",
            json={"document_id": "ips_test_20260601_093000"},
            headers={"X-Locale": "en"},
        )
        assert resp.status_code == 200
        assert captured["locale"] == "en"
        assert _parse_sse(resp.text)[-1]["type"] == "done"

    def test_advice_forwards_zh_locale_by_default(self, client, configured, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(
            "api.routers.monitoring.generate_rebalance_advice_stream",
            _capturing_stream(captured, "测试客户"),
        )
        resp = client.post(
            "/api/monitoring/advice",
            json={"document_id": "ips_test_20260601_093000"},
        )
        assert resp.status_code == 200
        assert captured["locale"] == "zh"


class _CapturingWorkflowApp:
    """Fake compiled LangGraph that records the initial state it receives."""

    captured_states: list = []

    async def astream(self, initial_state, config=None, stream_mode=None):
        type(self).captured_states.append(initial_state)
        yield {"generate": {"status": "generating"}}
        yield {
            "finalize": {
                "final_ips": {
                    "client_name": "John Doe",
                    "version": "1.0",
                    "risk_tolerance": {"overall_risk_level": "Moderate / 平衡型"},
                },
                "audit_trail": {"final_status": "approved", "total_rounds": 0},
                "status": "completed",
                "revision_count": 0,
                "error_message": "",
            }
        }


class TestIpsRouterLocale:
    @pytest.fixture
    def fake_workflow(self, monkeypatch):
        _CapturingWorkflowApp.captured_states = []
        monkeypatch.setattr("api.routers.ips.is_api_configured", lambda: True)
        monkeypatch.setattr(
            "src.agents.ips_workflow.load_ips_template", lambda: "TEMPLATE TEXT"
        )
        monkeypatch.setattr(
            "src.agents.ips_workflow.compile_ips_workflow",
            lambda **kw: _CapturingWorkflowApp(),
        )

    def test_generate_forwards_en_locale(self, client, fake_workflow):
        profile_id = _create_profile(client)

        created = client.post(
            "/api/ips/generate",
            json={"profile_id": profile_id},
            headers={"X-Locale": "en"},
        )
        assert created.status_code == 202
        task_id = created.json()["task_id"]

        events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)
        assert events[-1]["type"] == "done"

        # The request locale reached the workflow's initial state…
        assert _CapturingWorkflowApp.captured_states[-1]["locale"] == "en"
        # …and the SSE node labels were rendered in English.
        node_events = [e for e in events if e["type"] == "node"]
        assert node_events[0]["label"] == "Generate IPS draft"

        # The stored document renders with English scaffolding on request.
        document_id = events[-1]["document_id"]
        detail = client.get(f"/api/ips/{document_id}", headers={"X-Locale": "en"})
        assert detail.status_code == 200
        assert "# Investment Policy Statement (IPS)" in detail.json()["markdown"]

        export = client.get(f"/api/ips/{document_id}/export", headers={"X-Locale": "en"})
        assert export.status_code == 200
        assert "Investment Policy Statement (IPS)" in export.text
        assert "投资政策声明书" not in export.text

    def test_generate_defaults_to_zh(self, client, fake_workflow):
        profile_id = _create_profile(client)

        created = client.post("/api/ips/generate", json={"profile_id": profile_id})
        assert created.status_code == 202
        task_id = created.json()["task_id"]

        events = _parse_sse(client.get(f"/api/ips/tasks/{task_id}/events").text)
        assert _CapturingWorkflowApp.captured_states[-1]["locale"] == "zh"
        node_events = [e for e in events if e["type"] == "node"]
        assert node_events[0]["label"] == "生成 IPS 初稿"

        document_id = events[-1]["document_id"]
        detail = client.get(f"/api/ips/{document_id}")
        assert "# 投资政策声明书 (IPS)" in detail.json()["markdown"]

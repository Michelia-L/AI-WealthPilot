"""
AI WealthPilot - AI Advisor Tests
AI WealthPilot - AI 顾问模块测试

Comprehensive tests for the AI Wealth Advisor Agent,
using mocks to avoid actual API calls.

AI 财富顾问 Agent 的全面测试，
使用 Mock 避免实际 API 调用。

Test Coverage / 测试覆盖:
    - AdvisorReport data model
      AdvisorReport 数据模型
    - Prompt construction (_build_user_prompt)
      提示词构建
    - API configuration checks
      API 配置检查
    - Report generation with mocked API
      使用 Mock API 的报告生成
    - Streaming report generation
      流式报告生成
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from dataclasses import asdict

from src.agents.advisor import (
    AdvisorReport,
    _build_user_prompt,
    is_api_configured,
    generate_advice,
    generate_advice_stream,
    stream_advice,
    SYSTEM_PROMPT,
)
from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_profile():
    """Create a sample client profile for testing."""
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
            InvestmentGoal(name="Education", target_amount=300_000, years=10, priority="medium"),
        ],
        time_horizon_years=25,
        risk_profile=RiskProfile(
            ability_score=3.8,
            willingness_score=3.2,
            tolerance_level="Moderate / 平衡型",
        ),
    )


@pytest.fixture
def conflicting_profile():
    """Profile with conflicting ability and willingness scores."""
    return ClientProfile(
        name="Conflicted Investor",
        age=50,
        marital_status="single",
        dependents=0,
        financial=FinancialSituation(
            annual_income=200_000,
            annual_expenses=60_000,
            investable_assets=1_000_000,
            total_liabilities=100_000,
            emergency_fund_months=12.0,
        ),
        time_horizon_years=15,
        risk_profile=RiskProfile(
            ability_score=4.5,
            willingness_score=2.0,
            tolerance_level="Moderately Conservative / 稳健型",
        ),
    )


@pytest.fixture
def esg_profile():
    """Profile with ESG preferences and sector restrictions."""
    return ClientProfile(
        name="ESG Investor",
        age=30,
        marital_status="single",
        dependents=0,
        financial=FinancialSituation(
            annual_income=120_000,
            annual_expenses=50_000,
            investable_assets=300_000,
            total_liabilities=50_000,
            emergency_fund_months=8.0,
        ),
        time_horizon_years=20,
        esg_preference=True,
        sector_restrictions=["Tobacco", "Weapons", "Fossil Fuels"],
        notes="Strong preference for sustainable investing",
        risk_profile=RiskProfile(
            ability_score=3.5,
            willingness_score=3.0,
            tolerance_level="Moderate / 平衡型",
        ),
    )


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI API response."""
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "Mock advisory report content"
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 1000
    mock_response.usage.completion_tokens = 2000
    mock_response.usage.total_tokens = 3000
    return mock_response


@pytest.fixture
def mock_stream_chunks():
    """Create mock streaming response chunks."""
    chunks = []
    for text in ["Hello ", "World", "! This is ", "a test report."]:
        chunk = Mock()
        chunk.choices = [Mock()]
        chunk.choices[0].delta.content = text
        chunks.append(chunk)
    return chunks


# ============================================================
# Test AdvisorReport Data Model
# ============================================================

class TestAdvisorReport:
    """Tests for AdvisorReport data model."""

    def test_default_values(self):
        """Test default values of AdvisorReport."""
        report = AdvisorReport()
        assert report.content == ""
        assert report.model == ""
        assert report.generated_at == ""
        assert report.prompt_tokens == 0
        assert report.completion_tokens == 0
        assert report.total_tokens == 0
        assert report.client_name == ""
        assert report.success is False
        assert report.error_message == ""

    def test_custom_values(self):
        """Test AdvisorReport with custom values."""
        report = AdvisorReport(
            content="Test content",
            model="deepseek-v4-pro",
            generated_at="2025-01-01T12:00:00",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            client_name="Test Client",
            success=True,
        )
        assert report.content == "Test content"
        assert report.model == "deepseek-v4-pro"
        assert report.success is True

    def test_to_dict(self):
        """Test converting AdvisorReport to dictionary."""
        report = AdvisorReport(
            content="Test",
            client_name="Client",
            success=True,
        )
        d = asdict(report)
        assert isinstance(d, dict)
        assert d["content"] == "Test"
        assert d["client_name"] == "Client"
        assert d["success"] is True


# ============================================================
# Test Prompt Construction
# ============================================================

class TestPromptConstruction:
    """Tests for _build_user_prompt function."""

    def test_basic_info_in_prompt(self, sample_profile):
        """Test that basic info is included in prompt."""
        prompt = _build_user_prompt(sample_profile)

        assert "Test User" in prompt
        assert "35" in prompt
        assert "married" in prompt
        assert "2" in prompt  # dependents

    def test_financial_info_in_prompt(self, sample_profile):
        """Test that financial info is included in prompt."""
        prompt = _build_user_prompt(sample_profile)

        assert "150,000" in prompt  # income
        assert "80,000" in prompt   # expenses
        assert "500,000" in prompt  # investable assets
        assert "200,000" in prompt  # liabilities

    def test_goals_in_prompt(self, sample_profile):
        """Test that investment goals are included in prompt."""
        prompt = _build_user_prompt(sample_profile)

        assert "Retirement" in prompt
        assert "3,000,000" in prompt
        assert "Education" in prompt
        assert "300,000" in prompt

    def test_risk_profile_in_prompt(self, sample_profile):
        """Test that risk profile is included in prompt."""
        prompt = _build_user_prompt(sample_profile)

        assert "3.8" in prompt  # ability score
        assert "3.2" in prompt  # willingness score
        assert "Moderate" in prompt

    def test_conflict_detection_in_prompt(self, conflicting_profile):
        """Test that conflict is detected and noted in prompt."""
        prompt = _build_user_prompt(conflicting_profile)

        assert "CONFLICT DETECTED" in prompt or "冲突检测" in prompt
        assert "CFA principle: use the LOWER score" in prompt

    def test_no_conflict_when_aligned(self, sample_profile):
        """Test no conflict note when scores are aligned."""
        prompt = _build_user_prompt(sample_profile)

        assert "CONFLICT DETECTED" not in prompt

    def test_esg_preferences_in_prompt(self, esg_profile):
        """Test that ESG preferences are included in prompt."""
        prompt = _build_user_prompt(esg_profile)

        assert "ESG" in prompt
        assert "Tobacco" in prompt
        assert "Weapons" in prompt
        assert "Fossil Fuels" in prompt

    def test_notes_in_prompt(self, esg_profile):
        """Test that notes are included in prompt."""
        prompt = _build_user_prompt(esg_profile)

        assert "sustainable investing" in prompt

    def test_no_goals_message(self):
        """Test message when no goals defined."""
        profile = ClientProfile(name="No Goals User")
        prompt = _build_user_prompt(profile)

        assert "No specific goals defined" in prompt or "未定义具体目标" in prompt

    def test_prompt_structure(self, sample_profile):
        """Test that prompt has expected sections."""
        prompt = _build_user_prompt(sample_profile)

        assert "CLIENT PROFILE" in prompt
        assert "Basic Information" in prompt
        assert "Financial Situation" in prompt
        assert "Investment Goals" in prompt
        assert "Risk Tolerance Assessment" in prompt
        assert "Tax Status" in prompt
        assert "Liquidity Needs" in prompt


# ============================================================
# Test API Configuration
# ============================================================

class TestAPIConfiguration:
    """Tests for API configuration checks."""

    @patch("src.agents.advisor.DEEPSEEK_API_KEY", "test-api-key")
    def test_is_api_configured_true(self):
        """Test API is configured when key is set."""
        assert is_api_configured() is True

    @patch("src.agents.advisor.DEEPSEEK_API_KEY", "")
    def test_is_api_configured_false_empty(self):
        """Test API is not configured when key is empty."""
        assert is_api_configured() is False

    @patch("src.agents.advisor.DEEPSEEK_API_KEY", None)
    def test_is_api_configured_false_none(self):
        """Test API is not configured when key is None."""
        assert is_api_configured() is False


# ============================================================
# Test Report Generation (with Mock)
# ============================================================

class TestReportGeneration:
    """Tests for report generation functions using mocks."""

    @patch("src.agents.advisor._get_client")
    def test_generate_advice_success(self, mock_get_client, sample_profile, mock_openai_response):
        """Test successful report generation."""
        # Setup mock
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_get_client.return_value = mock_client

        # Generate report
        report = generate_advice(sample_profile)

        # Verify
        assert report.success is True
        assert report.content == "Mock advisory report content"
        assert report.client_name == "Test User"
        assert report.prompt_tokens == 1000
        assert report.completion_tokens == 2000
        assert report.total_tokens == 3000
        assert report.model == "deepseek-v4-pro"

    @patch("src.agents.advisor._get_client")
    def test_generate_advice_api_key_error(self, mock_get_client, sample_profile):
        """Test report generation with missing API key."""
        # Setup mock to raise ValueError
        mock_get_client.side_effect = ValueError("API key not configured")

        # Generate report
        report = generate_advice(sample_profile)

        # Verify error handling
        assert report.success is False
        assert "API key not configured" in report.error_message

    @patch("src.agents.advisor._get_client")
    def test_generate_advice_network_error(self, mock_get_client, sample_profile):
        """Test report generation with network error."""
        # Setup mock to raise Exception
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("Network error")
        mock_get_client.return_value = mock_client

        # Generate report
        report = generate_advice(sample_profile)

        # Verify error handling
        assert report.success is False
        assert "Network error" in report.error_message

    @patch("src.agents.advisor._get_client")
    def test_generate_advice_calls_api_correctly(self, mock_get_client, sample_profile, mock_openai_response):
        """Test that API is called with correct parameters."""
        # Setup mock
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_get_client.return_value = mock_client

        # Generate report
        generate_advice(sample_profile)

        # Verify API call
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "deepseek-v4-pro"
        assert call_args.kwargs["stream"] is False
        assert len(call_args.kwargs["messages"]) == 2
        assert call_args.kwargs["messages"][0]["role"] == "system"
        assert call_args.kwargs["messages"][1]["role"] == "user"


# ============================================================
# Test Streaming Report Generation
# ============================================================

class TestStreamingGeneration:
    """Tests for streaming report generation."""

    @patch("src.agents.advisor._get_client")
    def test_generate_advice_stream_success(self, mock_get_client, sample_profile, mock_stream_chunks):
        """Test successful streaming report generation."""
        # Setup mock
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = iter(mock_stream_chunks)
        mock_get_client.return_value = mock_client

        # Generate streaming report
        gen = generate_advice_stream(sample_profile)
        chunks = list(gen)

        # Verify chunks
        assert len(chunks) == 4
        assert chunks[0] == "Hello "
        assert chunks[1] == "World"

    @patch("src.agents.advisor._get_client")
    def test_stream_advice_wrapper(self, mock_get_client, sample_profile, mock_stream_chunks):
        """Test stream_advice wrapper for Streamlit integration."""
        # Setup mock
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = iter(mock_stream_chunks)
        mock_get_client.return_value = mock_client

        # Use stream_advice wrapper
        text_stream, report_container = stream_advice(sample_profile)

        # Consume the stream
        chunks = list(text_stream)

        # Verify chunks
        assert len(chunks) == 4

        # Verify report container
        assert len(report_container) == 1
        report = report_container[0]
        assert report.success is True
        assert report.content == "Hello World! This is a test report."

    @patch("src.agents.advisor._get_client")
    def test_stream_advice_error_handling(self, mock_get_client, sample_profile):
        """Test stream_advice error handling."""
        # Setup mock to raise error
        mock_get_client.side_effect = ValueError("API key not configured")

        # Use stream_advice wrapper
        text_stream, report_container = stream_advice(sample_profile)

        # Consume the stream (should not yield any chunks)
        chunks = list(text_stream)
        assert len(chunks) == 0

        # Verify error in report
        assert len(report_container) == 1
        report = report_container[0]
        assert report.success is False
        assert "API key not configured" in report.error_message


# ============================================================
# Test System Prompt
# ============================================================

class TestSystemPrompt:
    """Tests for system prompt content."""

    def test_system_prompt_contains_cfa_reference(self):
        """Test that system prompt references CFA framework."""
        assert "CFA" in SYSTEM_PROMPT
        assert "Private Wealth Management" in SYSTEM_PROMPT
        assert "IPS" in SYSTEM_PROMPT or "Investment Policy Statement" in SYSTEM_PROMPT

    def test_system_prompt_contains_output_requirements(self):
        """Test that system prompt specifies output format."""
        assert "Client Summary" in SYSTEM_PROMPT
        assert "Risk Tolerance" in SYSTEM_PROMPT
        assert "Asset Allocation" in SYSTEM_PROMPT
        assert "Risk Disclosure" in SYSTEM_PROMPT

    def test_system_prompt_is_bilingual(self):
        """Test that system prompt is bilingual."""
        # Check for Chinese characters
        assert "顾问" in SYSTEM_PROMPT or "财富" in SYSTEM_PROMPT
        assert "风险" in SYSTEM_PROMPT

    def test_system_prompt_contains_constraints(self):
        """Test that system prompt includes constraints."""
        assert "Never guarantee" in SYSTEM_PROMPT or "绝不保证" in SYSTEM_PROMPT
        assert "CFA principles" in SYSTEM_PROMPT or "CFA 原则" in SYSTEM_PROMPT


# ============================================================
# Integration Test
# ============================================================

class TestAdvisorIntegration:
    """Integration tests for advisor module."""

    @patch("src.agents.advisor._get_client")
    def test_full_workflow(self, mock_get_client, sample_profile, mock_openai_response):
        """Test complete workflow from profile to report."""
        # Setup mock
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_openai_response
        mock_get_client.return_value = mock_client

        # 1. Check API configuration
        with patch("src.agents.advisor.DEEPSEEK_API_KEY", "test-key"):
            assert is_api_configured() is True

        # 2. Build prompt
        prompt = _build_user_prompt(sample_profile)
        assert "Test User" in prompt

        # 3. Generate report
        report = generate_advice(sample_profile)
        assert report.success is True
        assert report.client_name == "Test User"

        # 4. Verify API was called with correct messages
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert "Test User" in messages[1]["content"]

"""
Unit tests for the rebalance advice streaming generator (FR-001 reasoning).

The LLM client is mocked at src.agents.rebalance_advisor._get_client; tests
assert the reasoning/token event protocol and the terminal usage capture
(including reasoning_tokens), not model output.
"""

from unittest.mock import Mock, patch

from src.agents.rebalance_advisor import generate_rebalance_advice_stream
from tests.test_advisor import _drain, _make_stream_chunk, _make_usage_chunk

MONITORING = {"client_name": "测试客户"}

# Valid per validate_rebalance_content: >= 200 chars, >= 2 Markdown headings.
REBALANCE_CONTENT = (
    "## 1. 漂移诊断 / Drift Diagnosis\n"
    "国内权益越出政策区间上沿 16.7pp，固定收益低于下沿 16.7pp，主要源于权益"
    "资产区间收益 80% 而固收区间收益 −10%，组合风险结构已偏离平衡型目标。\n"
    "## 2. 调衡建议 / Rebalancing Recommendations\n"
    "建议卖出国内权益 16.7pp、买入固定收益 16.7pp，使权重回到 50/50 的 SAA "
    "中枢，该操作符合 IPS 政策区间纪律，不涉及择时判断。\n"
    "## 3. 风险提示 / Risk Disclosure\n"
    "历史表现不代表未来收益，调仓可能产生交易成本与税务影响。"
)


def _fake_client(chunks):
    client = Mock()
    client.chat.completions.create.return_value = iter(chunks)
    return client


@patch("src.agents.rebalance_advisor._get_client")
def test_stream_emits_reasoning_then_tokens_and_captures_usage(mock_get_client):
    """Reasoning events arrive first; usage flows onto the returned report."""
    half = len(REBALANCE_CONTENT) // 2
    chunks = [
        _make_stream_chunk(reasoning="先核对各资产类别的越带情况。"),
        _make_stream_chunk(reasoning="再对照 IPS 政策区间给出调仓路径。"),
        _make_stream_chunk(content=REBALANCE_CONTENT[:half]),
        _make_stream_chunk(content=REBALANCE_CONTENT[half:]),
        _make_usage_chunk(prompt=200, completion=80, reasoning_tokens=36),
    ]
    mock_get_client.return_value = _fake_client(chunks)

    events, report = _drain(generate_rebalance_advice_stream(MONITORING))

    assert [e["type"] for e in events] == ["reasoning", "reasoning", "token", "token"]
    assert events[0]["text"] == "先核对各资产类别的越带情况。"
    assert "".join(e["text"] for e in events if e["type"] == "token") == REBALANCE_CONTENT

    assert report.success is True
    assert report.client_name == "测试客户"
    assert report.content == REBALANCE_CONTENT
    assert report.prompt_tokens == 200
    assert report.completion_tokens == 80
    assert report.total_tokens == 280
    assert report.reasoning_tokens == 36

    # The stream requests the terminal usage chunk.
    call_args = mock_get_client.return_value.chat.completions.create.call_args
    assert call_args.kwargs["stream"] is True
    assert call_args.kwargs["stream_options"] == {"include_usage": True}


@patch("src.agents.rebalance_advisor._get_client")
def test_stream_plain_model_emits_only_tokens(mock_get_client):
    """Plain chat models (no reasoning_content) stream token events only."""
    chunks = [
        _make_stream_chunk(content=REBALANCE_CONTENT[:100]),
        _make_stream_chunk(content=REBALANCE_CONTENT[100:]),
        _make_stream_chunk(
            usage=Mock(
                prompt_tokens=200,
                completion_tokens=80,
                total_tokens=280,
                completion_tokens_details=None,
            )
        ),
    ]
    mock_get_client.return_value = _fake_client(chunks)

    events, report = _drain(generate_rebalance_advice_stream(MONITORING))

    assert [e["type"] for e in events] == ["token", "token"]
    assert report.success is True
    assert report.reasoning_tokens == 0
    assert report.total_tokens == 280


@patch("src.agents.rebalance_advisor._get_client")
def test_stream_api_error_returns_failed_report(mock_get_client):
    """API failures are swallowed into the report, as before FR-001."""
    mock_get_client.side_effect = ValueError("API key not configured")

    events, report = _drain(generate_rebalance_advice_stream(MONITORING))

    assert events == []
    assert report.success is False
    assert "API key not configured" in report.error_message
    assert report.reasoning_tokens == 0

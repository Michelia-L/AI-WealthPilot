"""
Demo mode (P20): replay recorded fixtures for LLM-powered features.

When ``src.config.DEMO_MODE`` is enabled, the API replays curated, fully
fictional sample outputs from ``demo_fixtures/`` instead of calling the
DeepSeek API. This lets anyone clone the repository and experience the
complete AI advisor / IPS generation flow without an API key; developers
with a key can also set ``DEMO_MODE=1`` to force the replay path.

Fixture replay performs zero network calls. The fictional client name
「林晓兰」 inside fixtures is substituted with the actual profile name at
replay time so streamed text and saved artifacts look personalized.
"""

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from src import config
from src.agents import ips_storage
from src.agents.advisor import AdvisorReport
from src.agents.profiler import ClientProfile

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "demo_fixtures"

# Fictional demo client used across all fixtures; replaced at replay time.
DEMO_CLIENT_NAME = "林晓兰"

# Model label surfaced in done events / saved artifacts for demo output.
DEMO_MODEL = "demo-fixture"

# Per-node pacing of the demo IPS task (seconds). Kept as a module-level
# mutable so tests can shrink it to (0.0, 0.0) and keep the suite fast.
NODE_DELAY_RANGE: tuple[float, float] = (0.6, 1.0)

# Workflow node replay order — mirrors the real LangGraph happy path and
# the keys of api.routers.ips.NODE_LABELS.
_DEMO_IPS_NODES: tuple[str, ...] = (
    "generate_cme",
    "generate",
    "select_docs",
    "review_suitability",
    "review_compliance",
    "review_consistency",
    "validate_saa",
    "revise",
    "finalize",
)

# Rough streaming chunk size (characters) — mimics LLM token deltas.
_CHUNK_SIZE = 80


def is_demo_mode() -> bool:
    """Read the flag dynamically so tests can monkeypatch src.config.DEMO_MODE."""
    return bool(config.DEMO_MODE)


def _load_fixture_text(filename: str, client_name: str) -> str:
    """Read a text fixture and substitute the client-name placeholder."""
    text = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
    if client_name and client_name != DEMO_CLIENT_NAME:
        text = text.replace(DEMO_CLIENT_NAME, client_name)
    return text


def _iter_chunks(text: str) -> Generator[str, None, None]:
    """Yield the text in fixed-size pieces, mimicking LLM token streaming."""
    for start in range(0, len(text), _CHUNK_SIZE):
        yield text[start : start + _CHUNK_SIZE]


def _estimated_tokens(text: str) -> int:
    """Rough CJK-friendly token estimate (~1.5 characters per token)."""
    return max(1, int(len(text) / 1.5))


def demo_advice_stream(profile: ClientProfile) -> Generator[dict, None, AdvisorReport]:
    """Replay the recorded advisory report fixture as an event stream.

    Mirrors ``advisor.generate_advice_stream``: yields reasoning events from
    the shared thinking-preamble fixture first, then token events for the
    report body, and returns the terminal AdvisorReport via
    StopIteration.value, so callers consume it with ``yield from`` exactly
    like the real generator.
    """
    reasoning = _load_fixture_text("advisor_reasoning.txt", profile.name)
    content = _load_fixture_text("advisor_report.md", profile.name)
    for chunk in _iter_chunks(reasoning):
        yield {"type": "reasoning", "text": chunk}
    for chunk in _iter_chunks(content):
        yield {"type": "token", "text": chunk}
    completion_tokens = _estimated_tokens(content)
    prompt_tokens = _estimated_tokens(profile.summary()) + 900  # system prompt overhead
    return AdvisorReport(
        content=content,
        model=DEMO_MODEL,
        generated_at=datetime.now().isoformat(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        reasoning_tokens=_estimated_tokens(reasoning),
        client_name=profile.name,
        success=True,
        error_message="",
    )


def demo_rebalance_stream(
    monitoring: dict, profile: Optional[ClientProfile] = None
) -> Generator[dict, None, AdvisorReport]:
    """Replay the recorded rebalancing advice fixture as an event stream.

    Mirrors ``rebalance_advisor.generate_rebalance_advice_stream`` (same
    AdvisorReport dataclass, imported there from src.agents.advisor):
    reasoning events from the shared thinking-preamble fixture first, then
    token events for the report body.
    """
    client_name = str(
        monitoring.get("client_name") or (profile.name if profile else "")
    )
    reasoning = _load_fixture_text("advisor_reasoning.txt", client_name)
    content = _load_fixture_text("rebalance_advice.md", client_name)
    for chunk in _iter_chunks(reasoning):
        yield {"type": "reasoning", "text": chunk}
    for chunk in _iter_chunks(content):
        yield {"type": "token", "text": chunk}
    completion_tokens = _estimated_tokens(content)
    prompt_tokens = _estimated_tokens(
        json.dumps(monitoring, ensure_ascii=False, default=str)
    ) + 700  # system prompt overhead
    return AdvisorReport(
        content=content,
        model=DEMO_MODEL,
        generated_at=datetime.now().isoformat(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        reasoning_tokens=_estimated_tokens(reasoning),
        client_name=client_name,
        success=True,
        error_message="",
    )


async def run_demo_ips_task(task, profile_data: dict, max_revisions: int) -> None:
    """Replay the IPS workflow: node progress events, then save the fixture.

    Mirrors ``api.routers.ips._run_ips_task``'s event protocol (node → done
    /error), its write-through persistence (via task.publish), and its
    ips_storage JSON save — with zero LLM calls. ``profile_data`` and
    ``max_revisions`` are accepted for signature parity with the real
    runner; the replay itself is fixture-driven.
    """
    try:
        # Lazy import: api.routers.ips imports this module at load time.
        from api.routers.ips import NODE_LABELS

        for node in _DEMO_IPS_NODES:
            await asyncio.sleep(random.uniform(*NODE_DELAY_RANGE))
            await task.publish(
                {"type": "node", "node": node, "label": NODE_LABELS.get(node, node)}
            )

        record = json.loads(
            (FIXTURES_DIR / "ips_document.json").read_text(encoding="utf-8")
        )
        audit_trail = record.get("audit_trail") or {}
        client_name = task.meta["client_name"]
        # Substitute the fictional client name throughout the narratives.
        ips_dict = json.loads(
            json.dumps(record["ips"], ensure_ascii=False).replace(
                DEMO_CLIENT_NAME, client_name
            )
        )
        ips_dict["client_name"] = client_name

        filepath = ips_storage.save_ips(
            ips_dict=ips_dict,
            audit_trail_dict=audit_trail,
            client_name=client_name,
        )
        task.status = "completed"
        await task.publish(
            {
                "type": "done",
                "success": True,
                "document_id": Path(filepath).stem,
                "status": audit_trail.get("final_status") or "approved",
                "revision_count": 1,
            }
        )
    except Exception as e:
        logger.exception("Demo IPS task failed")
        task.status = "failed"
        await task.publish({"type": "error", "message": f"IPS 生成失败: {e}"})

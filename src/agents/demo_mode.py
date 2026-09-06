"""
Demo mode (P20): replay recorded fixtures for LLM-powered features.

When ``src.config.DEMO_MODE`` is enabled, the API replays curated, fully
fictional sample outputs from ``demo_fixtures/`` instead of calling the
DeepSeek API. This lets anyone clone the repository and experience the
complete AI advisor / IPS generation flow without an API key; developers
with a key can also set ``DEMO_MODE=1`` to force the replay path.

Fixture replay performs zero network calls. Fixtures are selected per
request locale: the ``*_en`` English fixtures for ``en``, the original
Chinese ones otherwise. At replay time the fixture persona (fictional
client 「林晓兰」 / "Evelyn Lin") is personalized against the requesting
profile — see ``_fixture_substitutions``: the placeholder name plus the
persona's key figures (age, finances, goals, risk scores, report date) are
swapped for the profile's real values, so streamed text and saved
artifacts line up with the client on record (#39).
"""

import asyncio
import json
import logging
import math
import random
import re
from datetime import date, datetime
from pathlib import Path
from typing import Generator, Optional

from src import config
from src.agents import ips_storage
from src.agents.advisor import AdvisorReport
from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
    format_risk_score,
)

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "demo_fixtures"

# Fictional demo client used across all fixtures; replaced at replay time.
DEMO_CLIENT_NAME = "林晓兰"
# Placeholder name inside the English (``*_en``) fixtures.
DEMO_CLIENT_NAME_EN = "Evelyn Lin"

# Model label surfaced in done events / saved artifacts for demo output.
DEMO_MODEL = "demo-fixture"

# Per-node pacing of the demo IPS task (seconds). Kept as a module-level
# mutable so tests can shrink it to (0.0, 0.0) and keep the suite fast.
NODE_DELAY_RANGE: tuple[float, float] = (0.6, 1.0)

# Workflow node replay order — mirrors the real LangGraph happy path and
# the keys of api.routers.ips._NODE_LABEL_KEYS.
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


def _fixture_name(base: str, locale: str) -> str:
    """Return the fixture filename for ``locale`` (``_en`` suffix for English).

    ``advisor_report.md`` → ``advisor_report_en.md`` when ``locale == "en"``;
    every other locale keeps the original (Chinese) fixture.
    """
    if locale == "en":
        stem, dot, ext = base.rpartition(".")
        return f"{stem}_en{dot}{ext}" if dot else f"{base}_en"
    return base


def _client_name_placeholder(locale: str) -> str:
    """Fictional client name used by the fixture set for ``locale``."""
    return DEMO_CLIENT_NAME_EN if locale == "en" else DEMO_CLIENT_NAME


# ---------------------------------------------------------------------------
# Fixture personalization (#39)
# ---------------------------------------------------------------------------
#
# The fixtures narrate one fictional household — the seeded demo client. At
# replay time ``_fixture_substitutions`` maps the persona's literals onto the
# requesting profile's real values and ``_apply_substitutions`` performs a
# single-pass, longest-match rewrite (deterministic, plain-text, no LLM).
#
# Deliberately NOT substituted — fixture scenario details the ClientProfile
# model cannot supply, which stay at the persona's values:
# - per-goal earmarked allocations (50 万 / CNY 500,000 education, 210 万 /
#   CNY 2.1 million retirement); required returns are instead recomputed via
#   TVM against these constants and the profile's targets;
# - the education top-up plan (每年 12 万 / CNY 120,000 per year, 每月 1 万 /
#   CNY 10,000 per month, cutting the required return to ~6.5%) — an annuity
#   scenario, not a closed-form function of profile fields;
# - mortgage terms (年还款约 11 万 / CNY 110,000, ~14% of income), occupation,
#   the 5-year fund experience, the panic-redemption history, the child's age;
# - the Moderate-band risk anchors (volatility 8%–13%, max loss −12%,
#   drawdown −20%, VaR −18%) and the fixture SAA's own numbers (5.4% expected
#   return, 4.2% net of fees, 23% fee drag) — properties of the fixture
#   portfolio, not of the profile;
# - qualitative score glosses ("中等偏上" / "above average") and narrative
#   claims keyed to the persona's ability > willingness shape;
# - ``cme_as_of_date`` (a market-data timestamp) and the rebalance fixtures'
#   market-drift figures.

_FIXTURE_DATE = "2026-07-20"  # date the fixtures were authored
_FIXTURE_AGE = 38
# "已划拨 / earmarked" goal funding exists only in the fixture narrative.
_FIXTURE_EDU_ALLOCATION = 500_000.0
_FIXTURE_RET_ALLOCATION = 2_100_000.0
# Portfolio-level constants of the fixture SAA — not profile-derived.
_FIXTURE_EXPECTED_RETURN = 0.054
_FIXTURE_INFLATION = 0.025

_EN_NUMBER_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
_ZH_NUMERALS = "零一二三四五六七八九"  # index == count

_MARITAL_ZH = {
    "married": "已婚",
    "single": "未婚",
    "divorced": "离异",
    "widowed": "丧偶",
}
_MARITAL_EN = {
    "married": "married",
    "single": "single",
    "divorced": "divorced",
    "widowed": "widowed",
}

# Name keywords pairing profile goals with the fixture's two storyline goals.
_EDU_GOAL_KEYS = ("教育", "edu")
_RET_GOAL_KEYS = ("退休", "养老", "retire")


def _fmt_wan(amount: float) -> str:
    """CNY amount in the zh fixtures' 万 style: integral when possible
    (80), otherwise up to two decimals (92.5, 33.75)."""
    wan = amount / 10_000
    if wan == int(wan):
        return str(int(wan))
    return f"{wan:.2f}".rstrip("0").rstrip(".")


def _fmt_en_money(amount: float) -> str:
    """CNY amount in the en fixtures' style: "CNY X.Y million" for exact
    0.1-million multiples from one million up, else a comma-grouped figure."""
    if abs(amount) >= 1_000_000 and amount % 100_000 == 0:
        return f"CNY {amount / 1_000_000:.1f} million"
    return f"CNY {amount:,.0f}"


def _fmt_pct(ratio: float, digits: int = 1) -> str:
    """Ratio as a percentage in the fixtures' style (47.5%, 9.15%, −0.2%)."""
    return f"{ratio * 100:.{digits}f}%".replace("-", "−")


def _fmt_num(value: float, digits: int = 1) -> str:
    """Fixed-decimal number in the fixtures' style (minus as U+2212)."""
    return f"{value:.{digits}f}".replace("-", "−")


def _kids_zh(dependents: int) -> str:
    """zh children clause for the marital phrase (育有两个孩子 / 无子女)."""
    if dependents <= 0:
        return "无子女"
    numeral = (
        _ZH_NUMERALS[dependents] if dependents < len(_ZH_NUMERALS) else str(dependents)
    )
    return f"育有{numeral}个孩子"


def _kids_en(dependents: int) -> str:
    """en children clause for the marital phrase (two children / no children)."""
    if dependents <= 0:
        return "no children"
    if dependents == 1:
        return "one child"
    word = (
        _EN_NUMBER_WORDS[dependents]
        if dependents < len(_EN_NUMBER_WORDS)
        else str(dependents)
    )
    return f"{word} children"


def _match_fixture_goals(
    goals: list,
) -> tuple[Optional[InvestmentGoal], Optional[InvestmentGoal]]:
    """Pair the fixture's two storyline goals with the profile's goals.

    Keyword match on the goal name first (教育/edu for the education slot,
    退休/养老/retire for retirement); with exactly two goals and an open
    slot, the remaining goal fills it (both open: the shorter horizon is
    education). Goals beyond the fixture's two cannot be woven into the
    narrative and are ignored.
    """

    def _named(goal, keys) -> bool:
        return any(key in goal.name.lower() for key in keys)

    edu = next((g for g in goals if _named(g, _EDU_GOAL_KEYS)), None)
    ret = next((g for g in goals if g is not edu and _named(g, _RET_GOAL_KEYS)), None)
    remaining = [g for g in goals if g is not edu and g is not ret]
    if len(goals) == 2 and remaining:
        if edu is None and ret is None:
            edu, ret = sorted(goals, key=lambda g: g.years)
        elif edu is None:
            edu = remaining[0]
        elif ret is None:
            ret = remaining[0]
    return edu, ret


def _risk_substitutions(rp: RiskProfile) -> list[tuple[str, str]]:
    """Risk-score / risk-level pairs; empty when the profile is unassessed.

    The fixture's willingness and final scores coincide (3.0 = min(3.4,
    3.0)), so occurrences of the bare 3.0 are disambiguated by wording
    context: "意愿 / willingness …" takes the willingness score, "最终评分 /
    较低值 / final score …" takes the prudence-minimum final score.
    """
    if rp.ability_score <= 0 or rp.willingness_score <= 0:
        return []
    # Match the profile page / recommender rounding (ROUND_HALF_UP, #35):
    # f"{3.25:.1f}" would show "3.2" here while the UI shows "3.3".
    ability = format_risk_score(rp.ability_score)
    willingness = format_risk_score(rp.willingness_score)
    final = format_risk_score(rp.final_score)
    gap = format_risk_score(abs(rp.ability_score - rp.willingness_score))
    pairs = [
        ("3.4", ability),
        ("意愿评分 3.0", f"意愿评分 {willingness}"),
        ("意愿（3.0）", f"意愿（{willingness}）"),
        ("意愿 3.0", f"意愿 {willingness}"),
        ("willingness score of 3.0", f"willingness score of {willingness}"),
        ("willingness scores 3.0", f"willingness scores {willingness}"),
        ("willingness (3.0)", f"willingness ({willingness})"),
        ("willingness of 3.0", f"willingness of {willingness}"),
        ("willingness 3.0", f"willingness {willingness}"),
        ("最终评分取 3.0", f"最终评分取 {final}"),
        ("最终评分 3.0", f"最终评分 {final}"),
        ("较低值 3.0", f"较低值 {final}"),
        ("final score of 3.0", f"final score of {final}"),
        ("final score is 3.0", f"final score is {final}"),
        ("lower score of 3.0", f"lower score of {final}"),
        ("the lower 3.0", f"the lower {final}"),
        ("相差 0.4 分", f"相差 {gap} 分"),
        ("0.4-point gap", f"{gap}-point gap"),
        ("0.4 points", f"{gap} points"),
    ]
    level = rp.tolerance_level or rp.classify()
    if " / " in level:
        en_label, zh_label = (part.strip() for part in level.split(" / ", 1))
        pairs += [
            ("平衡型", zh_label),
            ("Moderate", en_label),
            (
                '"overall_risk_level": "moderate"',
                f'"overall_risk_level": "{en_label.lower().replace(" ", "_")}"',
            ),
        ]
    return pairs


def _goal_substitutions(profile: ClientProfile) -> list[tuple[str, str]]:
    """Goal name/amount/horizon/required-return pairs.

    Required returns are recomputed by TVM (r = (FV/PV)^(1/n) − 1) against
    the persona's earmarked allocations (which ClientProfile does not
    carry); the narrative's formula strings are rewritten to match, so the
    arithmetic shown stays internally consistent.
    """
    pairs: list[tuple[str, str]] = []
    edu, ret = _match_fixture_goals(profile.goals)
    edu_ok = edu is not None and edu.target_amount > 0 and edu.years > 0
    ret_ok = ret is not None and ret.target_amount > 0 and ret.years > 0

    if edu is not None:
        pairs.append(("子女教育金", edu.name))
        # en documents keep the fixture's English goal labels when the
        # profile's goal name isn't ASCII-renderable (a CJK name would leak
        # into the English fixtures otherwise).
        if edu.name.isascii():
            pairs += [
                ("Child's Education Fund", edu.name),
                ("Child's education fund", edu.name),
                ("child's education fund", edu.name),
            ]
    if ret is not None:
        pairs += [("退休养老储备", ret.name), ("退休养老目标", ret.name)]
        if ret.name.isascii():
            pairs += [
                ("Retirement Reserve", ret.name),
                ("Retirement reserve", ret.name),
                ("retirement reserve", ret.name),
            ]

    age = profile.age
    t1 = t2 = 0.0
    y1 = y2 = 0
    r_edu = r_ret = 0.0
    if edu_ok:
        t1, y1 = edu.target_amount, edu.years
        r_edu = (t1 / _FIXTURE_EDU_ALLOCATION) ** (1 / y1) - 1
        pairs += [
            ("(1,200,000/500,000)^(1/10)", f"({t1:,.0f}/500,000)^(1/{y1})"),
            ("(120/50)^(1/10)", f"({t1 / 10_000:g}/50)^(1/{y1})"),
            ("120 万", f"{_fmt_wan(t1)} 万"),
            ("CNY 1.2 million", _fmt_en_money(t1)),
            ("9.15%", _fmt_pct(r_edu, 2)),
            ("10 年", f"{y1} 年"),
            ("10-year", f"{y1}-year"),
            ("10 years", f"{y1} years"),
            ("year 10", f"year {y1}"),
            ("48 岁", f"{age + y1} 岁"),
            ('"target_amount": 1200000.0', f'"target_amount": {json.dumps(float(t1))}'),
            ('"time_horizon_years": 10', f'"time_horizon_years": {y1}'),
            ('"years": 10', f'"years": {y1}'),
            (
                '"required_return": 0.0915',
                f'"required_return": {json.dumps(round(r_edu, 4))}',
            ),
        ]
    if ret_ok:
        t2, y2 = ret.target_amount, ret.years
        r_ret = (t2 / _FIXTURE_RET_ALLOCATION) ** (1 / y2) - 1
        pairs += [
            ("(4,000,000/2,100,000)^(1/22)", f"({t2:,.0f}/2,100,000)^(1/{y2})"),
            ("(400/210)^(1/22)", f"({t2 / 10_000:g}/210)^(1/{y2})"),
            ("400 万", f"{_fmt_wan(t2)} 万"),
            ("CNY 4.0 million", _fmt_en_money(t2)),
            ("2.97%", _fmt_pct(r_ret, 2)),
            ("22 年", f"{y2} 年"),
            ("20 年", f"{y2} 年"),  # the "20+ 年" horizon characterization
            ("22-year", f"{y2}-year"),
            ("22 working years", f"{y2} working years"),
            ("22 years", f"{y2} years"),
            ("20 years", f"{y2} years"),
            ("60 岁", f"{age + y2} 岁"),
            ("55 岁", f"{age + y2 - 5} 岁"),
            ("to age 60", f"to age {age + y2}"),
            ("after age 55", f"after age {age + y2 - 5}"),
            ('"target_amount": 4000000.0', f'"target_amount": {json.dumps(float(t2))}'),
            ('"time_horizon_years": 22', f'"time_horizon_years": {y2}'),
            ('"overall_horizon_years": 22', f'"overall_horizon_years": {y2}'),
            (
                '"required_return": 0.0297',
                f'"required_return": {json.dumps(round(r_ret, 4))}',
            ),
        ]
    if edu_ok and ret_ok:
        # Two-goal derivations: blended/real required return, the expected
        # return gap, stage-2 horizon, and the age-range narratives.
        blended = (t1 * r_edu + t2 * r_ret) / (t1 + t2)
        real = (1 + blended) / (1 + _FIXTURE_INFLATION) - 1
        gap_pp = (_FIXTURE_EXPECTED_RETURN - blended) * 100
        purchasing = 1 / (1 + _FIXTURE_INFLATION) ** y2
        w1, w2, wt = t1 / 10_000, t2 / 10_000, (t1 + t2) / 10_000
        point = "percentage point" if _fmt_num(gap_pp) == "1.0" else "percentage points"
        pairs += [
            (
                "(120×9.15% + 400×2.97%) / 520",
                f"({w1:g}×{_fmt_pct(r_edu, 2)} + {w2:g}×{_fmt_pct(r_ret, 2)}) / {wt:g}",
            ),
            ("120/520", f"{w1:g}/{wt:g}"),
            ("400/520", f"{w2:g}/{wt:g}"),
            ("12 年", f"{y2 - y1} 年"),
            ("12-year", f"{y2 - y1}-year"),
            ("12 years", f"{y2 - y1} years"),
            ("Ages 38 to 48", f"Ages {age} to {age + y1}"),
            ("Ages 48 to 60", f"Ages {age + y1} to {age + y2}"),
            ("4.4%", _fmt_pct(blended)),
            ("1.85%", _fmt_pct(real, 2)),
            ("1.9%", _fmt_pct(real)),
            ("1.0 个百分点", f"{_fmt_num(gap_pp)} 个百分点"),
            ("1.0 percentage point", f"{_fmt_num(gap_pp)} {point}"),
            ("58%", f"{purchasing * 100:.0f}%"),
            ('"years": 12', f'"years": {y2 - y1}'),
            (
                '"required_nominal_return": 0.044',
                f'"required_nominal_return": {json.dumps(round(blended, 4))}',
            ),
            (
                '"required_real_return": 0.0185',
                f'"required_real_return": {json.dumps(round(real, 4))}',
            ),
        ]
    return pairs


def _fixture_substitutions(profile: Optional[ClientProfile]) -> list[tuple[str, str]]:
    """Literal (old → new) pairs personalizing the fixtures for ``profile``.

    ``old`` strings are the fixture persona's literals; ``new`` strings are
    formatted from the profile in the fixtures' own conventions (万-units
    zh-side, "CNY …" / "X.Y million" en-side). The report date always maps
    to the generation day, even without a profile. Both locales' patterns
    are returned together — pairs simply no-op on fixtures that do not
    contain them.
    """
    pairs: list[tuple[str, str]] = [(_FIXTURE_DATE, date.today().isoformat())]
    if profile is None:
        return pairs

    fin = profile.financial
    savings = fin.annual_income - fin.annual_expenses
    emergency_amount = fin.emergency_fund_months * fin.annual_expenses / 12
    pairs += [
        ("80 万", f"{_fmt_wan(fin.annual_income)} 万"),
        ("42 万", f"{_fmt_wan(fin.annual_expenses)} 万"),
        ("38 万", f"{_fmt_wan(savings)} 万"),
        ("260 万", f"{_fmt_wan(fin.investable_assets)} 万"),
        ("90 万", f"{_fmt_wan(fin.total_liabilities)} 万"),
        ("170 万", f"{_fmt_wan(fin.net_worth)} 万"),
        ("约 21 万", f"约 {_fmt_wan(emergency_amount)} 万"),
        ("CNY 800,000", _fmt_en_money(fin.annual_income)),
        ("CNY 420,000", _fmt_en_money(fin.annual_expenses)),
        ("CNY 380,000", _fmt_en_money(savings)),
        ("CNY 2.6 million", _fmt_en_money(fin.investable_assets)),
        ("CNY 900,000", _fmt_en_money(fin.total_liabilities)),
        ("CNY 1.7 million", _fmt_en_money(fin.net_worth)),
        ("CNY 210,000", _fmt_en_money(emergency_amount)),
        ("47.5%", _fmt_pct(fin.savings_rate)),
    ]
    if math.isfinite(fin.debt_to_asset_ratio):
        pairs.append(("34.6%", _fmt_pct(fin.debt_to_asset_ratio)))

    months = fin.emergency_fund_months
    if months > 0:
        en_word = (
            _EN_NUMBER_WORDS[int(months)]
            if months == int(months) and int(months) < len(_EN_NUMBER_WORDS)
            else f"{months:g}"
        )
        plural = "" if months == 1 else "s"
        pairs += [
            ("6 个月", f"{months:g} 个月"),
            ("six months", f"{en_word} month{plural}"),
            ("six-month", f"{en_word}-month"),
            (
                '"emergency_reserve_months": 6',
                '"emergency_reserve_months": '
                + json.dumps(int(months) if months == int(months) else months),
            ),
        ]

    pairs += _risk_substitutions(profile.risk_profile)

    age = profile.age
    pairs += [("38 岁", f"{age} 岁"), (", 38,", f", {age},"), ("(38,", f"({age},")]
    marital_zh = _MARITAL_ZH.get(profile.marital_status)
    if marital_zh is not None:
        kids_zh = _kids_zh(profile.dependents)
        marital_en = _MARITAL_EN[profile.marital_status]
        kids_en = _kids_en(profile.dependents)
        pairs += [
            ("已婚，育有一子（6 岁）", f"{marital_zh}，{kids_zh}"),
            ("已婚，育有一子", f"{marital_zh}，{kids_zh}"),
            ("已婚育有一子", f"{marital_zh}，{kids_zh}"),
            ("is married with one child (age 6)", f"is {marital_en} with {kids_en}"),
            ("married with one child", f"{marital_en} with {kids_en}"),
            ("(38, married, one child)", f"({age}, {marital_en}, {kids_en})"),
        ]

    pairs += _goal_substitutions(profile)
    return pairs


def _apply_substitutions(text: str, pairs: list[tuple[str, str]]) -> str:
    """Single-pass, longest-match application of ``pairs``.

    One alternation regex over the escaped old strings (sorted longest
    first) replaces each literal at most once and never rescans inserted
    text — so a new value equal to another pair's old string (e.g. an
    income of 90 万 meeting the persona's 90 万 mortgage pattern) is not
    re-rewritten, and short patterns ("3.4") cannot corrupt longer ones
    ("34.6%").
    """
    mapping = {old: new for old, new in pairs if old != new}
    if not mapping:
        return text
    pattern = "|".join(
        sorted((re.escape(old) for old in mapping), key=len, reverse=True)
    )
    return re.sub(pattern, lambda m: mapping[m.group(0)], text)


def _personalize_fixture_text(
    text: str,
    client_name: str,
    locale: str = "zh",
    profile: Optional[ClientProfile] = None,
) -> str:
    """Swap the fixture persona's name and key figures for the profile's."""
    text = _apply_substitutions(text, _fixture_substitutions(profile))
    placeholder = _client_name_placeholder(locale)
    if client_name and client_name != placeholder:
        text = text.replace(placeholder, client_name)
    return text


def _load_fixture_text(
    filename: str,
    client_name: str,
    locale: str = "zh",
    profile: Optional[ClientProfile] = None,
) -> str:
    """Read a text fixture and personalize it for the requesting client."""
    text = (FIXTURES_DIR / _fixture_name(filename, locale)).read_text(encoding="utf-8")
    return _personalize_fixture_text(text, client_name, locale, profile)


def _profile_from_data(data: dict) -> Optional[ClientProfile]:
    """Rebuild a ClientProfile from its stored asdict shape (the API layer's
    ``record.data``); None when the payload does not fit the model."""
    try:
        d = dict(data)
        financial = FinancialSituation(**d.pop("financial", {}))
        risk = RiskProfile(**d.pop("risk_profile", {}))
        goals = [InvestmentGoal(**g) for g in d.pop("goals", [])]
        return ClientProfile(financial=financial, risk_profile=risk, goals=goals, **d)
    except Exception:
        logger.warning("Demo replay: profile payload not personalizable", exc_info=True)
        return None


def _iter_chunks(text: str) -> Generator[str, None, None]:
    """Yield the text in fixed-size pieces, mimicking LLM token streaming."""
    for start in range(0, len(text), _CHUNK_SIZE):
        yield text[start : start + _CHUNK_SIZE]


def _estimated_tokens(text: str) -> int:
    """Rough CJK-friendly token estimate (~1.5 characters per token)."""
    return max(1, int(len(text) / 1.5))


def demo_advice_stream(
    profile: ClientProfile, locale: str = "zh"
) -> Generator[dict, None, AdvisorReport]:
    """Replay the recorded advisory report fixture as an event stream.

    Mirrors ``advisor.generate_advice_stream``: yields reasoning events from
    the shared thinking-preamble fixture first, then token events for the
    report body, and returns the terminal AdvisorReport via
    StopIteration.value, so callers consume it with ``yield from`` exactly
    like the real generator. ``locale`` selects the fixture language.
    """
    reasoning = _load_fixture_text(
        "advisor_reasoning.txt", profile.name, locale, profile
    )
    content = _load_fixture_text("advisor_report.md", profile.name, locale, profile)
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
    monitoring: dict, profile: Optional[ClientProfile] = None, locale: str = "zh"
) -> Generator[dict, None, AdvisorReport]:
    """Replay the recorded rebalancing advice fixture as an event stream.

    Mirrors ``rebalance_advisor.generate_rebalance_advice_stream`` (same
    AdvisorReport dataclass, imported there from src.agents.advisor):
    reasoning events from the shared thinking-preamble fixture first, then
    token events for the report body. ``locale`` selects the fixture language.
    """
    client_name = str(
        monitoring.get("client_name") or (profile.name if profile else "")
    )
    reasoning = _load_fixture_text(
        "advisor_reasoning.txt", client_name, locale, profile
    )
    content = _load_fixture_text("rebalance_advice.md", client_name, locale, profile)
    for chunk in _iter_chunks(reasoning):
        yield {"type": "reasoning", "text": chunk}
    for chunk in _iter_chunks(content):
        yield {"type": "token", "text": chunk}
    completion_tokens = _estimated_tokens(content)
    prompt_tokens = (
        _estimated_tokens(json.dumps(monitoring, ensure_ascii=False, default=str)) + 700
    )  # system prompt overhead
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


async def run_demo_ips_task(
    task, profile_data: dict, max_revisions: int, locale: str = "zh"
) -> None:
    """Replay the IPS workflow: node progress events, then save the fixture.

    Mirrors ``api.routers.ips._run_ips_task``'s event protocol (node → done
    /error), its write-through persistence (via task.publish), and its
    ips_storage JSON save — with zero LLM calls. The document is the fixture
    personalized against ``profile_data`` (#39); ``max_revisions`` is
    accepted for signature parity with the real runner. Node labels, the
    error message, and the fixture document itself are selected per
    ``locale``.
    """
    try:
        # Lazy import: api.routers.ips imports this module at load time.
        from api.i18n import msg
        from api.routers.ips import node_label

        for node in _DEMO_IPS_NODES:
            await asyncio.sleep(random.uniform(*NODE_DELAY_RANGE))
            await task.publish(
                {"type": "node", "node": node, "label": node_label(node, locale)}
            )

        record = json.loads(
            (FIXTURES_DIR / _fixture_name("ips_document.json", locale)).read_text(
                encoding="utf-8"
            )
        )
        client_name = task.meta["client_name"]
        # Personalize the whole record (IPS body + audit trail) against the
        # requesting profile before persisting (#39).
        profile = _profile_from_data(profile_data)
        record = json.loads(
            _personalize_fixture_text(
                json.dumps(record, ensure_ascii=False), client_name, locale, profile
            )
        )
        audit_trail = record.get("audit_trail") or {}
        ips_dict = record["ips"]
        ips_dict["client_name"] = client_name

        filepath = ips_storage.save_ips(
            ips_dict=ips_dict,
            audit_trail_dict=audit_trail,
            client_name=client_name,
            profile_id=task.meta.get("profile_id"),
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
        await task.publish(
            {"type": "error", "message": msg("ips.generation_failed", locale, error=e)}
        )

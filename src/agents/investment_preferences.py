"""Disclose recorded preferences without implying asset or holdings screening."""

import re

from src.agents.profiler import ClientProfile


def screening_note(locale: str = "zh") -> str:
    """Current implementation boundary, shared by recommendations and reports."""
    if locale == "en":
        return (
            "Preferences recorded; screening has not been performed. The current "
            "asset-class optimizer does not apply ESG or sector exclusions, and "
            "broad-market ETFs may still hold companies in the listed sectors. "
            "Implementation requires checking candidate funds' exclusion rules "
            "and holdings, assessing ESG or screened-index alternatives, and "
            "reviewing their costs, tracking differences and risk before use. "
            "No fund substitution has been made."
        )
    return (
        "偏好已记录，尚未执行筛选。当前资产类别优化器不应用 ESG 或行业排除约束，"
        "宽基 ETF 仍可能持有客户要求排除的行业成分股。落实前需核验候选基金的"
        "排除规则与持仓，评估 ESG 基金或筛选型指数替代方案，并复核费用、"
        "跟踪差异与风险。当前尚未执行基金替换。"
    )


def _markdown_text(value: str) -> str:
    # Sector names are user data; keep them literal instead of allowing them
    # to introduce headings, links, or HTML into the generated disclosure.
    value = " ".join(value.split())
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|~-])", r"\\\1", value)


def format_investment_preferences(profile: ClientProfile, locale: str = "zh") -> str:
    """Return an optional Markdown section based solely on recorded preferences."""
    if not profile.esg_preference and not profile.sector_restrictions:
        return ""
    en = locale == "en"
    lines = [
        "**ESG and sector preferences**" if en else "**ESG 与行业排除偏好**",
        "",
    ]
    if profile.esg_preference:
        lines.append("- ESG investing preference: Yes" if en else "- ESG 投资偏好：是")
    if profile.sector_restrictions:
        label = "Requested sector exclusions" if en else "客户要求排除的行业"
        sectors = ", ".join(_markdown_text(s) for s in profile.sector_restrictions)
        lines.append(f"- {label}: {sectors}")
    lines.extend(["", screening_note(locale)])
    return "\n".join(lines)


def apply_ips_preferences(ips: dict, profile_data: dict, locale: str = "zh") -> dict:
    """Set source preferences before review, including after an LLM revision.

    The document is a fresh model dump (or demo fixture copy). Do not infer
    specific ESG criteria from a boolean or retain another persona's sectors.
    """
    unique = ips.setdefault("unique_circumstances", {})
    esg = bool(profile_data.get("esg_preference", False))
    sectors = list(profile_data.get("sector_restrictions") or [])
    unique["esg_preferences"] = (
        ("ESG investing preference" if locale == "en" else "偏好 ESG 投资")
        if esg
        else None
    )
    unique["sector_restrictions"] = sectors
    unique["screening_note"] = screening_note(locale) if esg or sectors else None
    return ips

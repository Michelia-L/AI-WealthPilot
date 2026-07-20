"""
Client risk-level weight caps for constrained portfolio optimization.

Maps a client profile's bilingual risk tolerance label (e.g.
"Moderately Conservative / 稳健型", see src.agents.profiler) to per-group
maximum weights over the DEFAULT_ASSET_CLASSES universe. Only the
risk-seeking groups (equity, alternative) are capped — bonds and cash
are left uncapped, so the conservative end is protected implicitly by
the equity/alternative ceilings.
"""

from src.config import DEFAULT_ASSET_CLASSES

# Asset-group membership keyed by DEFAULT_ASSET_CLASSES keys.
ASSET_GROUPS: dict[str, list[str]] = {
    "equity": ["US_EQUITY", "INTL_EQUITY", "EM_EQUITY", "CHINA_EQUITY"],
    "bond": ["US_BOND", "LONG_TREASURY_BOND", "HIGH_YIELD_BOND", "EM_BOND", "TIPS"],
    "alternative": ["GOLD", "COMMODITIES", "REIT", "CRYPTO"],
    "cash": ["CASH"],
}

# Per-risk-level group caps. Keys are the Chinese level names as they
# appear in the profiler's bilingual labels ("... / 保守型" etc.).
RISK_LEVEL_CAPS: dict[str, dict[str, float]] = {
    "保守型": {"equity": 0.15, "alternative": 0.10},
    "稳健型": {"equity": 0.30, "alternative": 0.15},
    "平衡型": {"equity": 0.50, "alternative": 0.20},
    "成长型": {"equity": 0.70, "alternative": 0.25},
    "进取型": {"equity": 0.90, "alternative": 0.30},
}


def caps_for_tolerance(tolerance_level: str) -> dict[str, float]:
    """Resolve a bilingual tolerance label to its group caps.

    Matches on the Chinese level stem (保守/稳健/平衡/成长/进取) so both
    the full bilingual label and the bare Chinese name resolve.

    Args:
        tolerance_level: e.g. "Moderately Conservative / 稳健型".

    Returns:
        A copy of the group's cap dict, e.g. {"equity": 0.3, "alternative": 0.15}.

    Raises:
        ValueError: If the label contains no known level name.
    """
    text = tolerance_level or ""
    for level_key, caps in RISK_LEVEL_CAPS.items():
        # "保守型"[:-1] == "保守": the stem also matches the full "保守型".
        if level_key[:-1] in text:
            return dict(caps)
    raise ValueError(f"无法识别的风险等级: {tolerance_level!r}")


def build_group_constraints(caps: dict[str, float], selected_keys: list[str]) -> dict:
    """Build optimize_with_asset_class_constraints-shaped group limits.

    Only capped groups that intersect the selected asset keys are kept;
    group members are translated to asset display names (the columns of
    the returns DataFrame the optimizer sees).

    Args:
        caps: Group caps from caps_for_tolerance, e.g. {"equity": 0.15}.
        selected_keys: DEFAULT_ASSET_CLASSES keys in this optimization run.

    Returns:
        Dict like {'equity': {'assets': ['US Equities (S&P 500)'], 'min': 0.0,
        'max': 0.15}}; empty when no capped group is in the selection.
    """
    selected = set(selected_keys)
    constraints = {}
    for group_name, cap in caps.items():
        members = [k for k in ASSET_GROUPS[group_name] if k in selected]
        if not members:
            continue
        constraints[group_name] = {
            "assets": [DEFAULT_ASSET_CLASSES[k]["name"] for k in members],
            "min": 0.0,
            "max": cap,
        }
    return constraints

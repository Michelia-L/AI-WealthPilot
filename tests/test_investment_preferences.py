"""Preference disclosure and source-of-truth behavior, without screening claims."""

import pytest

from api.profile_convert import payload_to_data, profile_from_data
from api.schemas import ProfilePayload
from src.agents.investment_preferences import (
    apply_ips_preferences,
    format_investment_preferences,
)
from src.agents.ips_agents import get_system_prompt
from tests.test_api_profiles import sample_payload


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize(
    "esg,sectors", [(False, []), (True, []), (False, ["Tobacco"]), (True, ["Defense"])]
)
def test_disclosure_matches_recorded_preferences(locale, esg, sectors):
    data = payload_to_data(
        ProfilePayload(
            **sample_payload(esg_preference=esg, sector_restrictions=sectors)
        ),
        created_at="2026-01-01T00:00:00",
    )
    text = format_investment_preferences(profile_from_data(data), locale)
    assert bool(text) == bool(esg or sectors)
    if text:
        assert (
            "screening has not been performed" if locale == "en" else "尚未执行筛选"
        ) in text
        label = (
            "ESG investing preference: Yes" if locale == "en" else "ESG 投资偏好：是"
        )
        assert (label in text) == esg
    for sector in sectors:
        assert sector in text


def test_sector_names_are_literal_markdown_data():
    data = payload_to_data(
        ProfilePayload(
            **sample_payload(
                sector_restrictions=[
                    "[Tobacco](https://example.com)",
                    "<script>\n# heading",
                ]
            )
        ),
        created_at="2026-01-01T00:00:00",
    )
    text = format_investment_preferences(profile_from_data(data), "en")
    assert "[Tobacco](" not in text
    assert "<script>" not in text
    assert "\n# heading" not in text
    assert "Tobacco" in text


def test_ips_clears_invented_or_demo_preferences_without_repeating_disclosure():
    ips = {
        "unique_circumstances": {
            "esg_preferences": "Invented",
            "sector_restrictions": ["Invented"],
            "screening_note": "Screened",
        }
    }
    apply_ips_preferences(ips, {"esg_preference": True}, "en")
    first = dict(ips["unique_circumstances"])
    apply_ips_preferences(ips, {"esg_preference": True}, "en")
    assert ips["unique_circumstances"] == first
    apply_ips_preferences(ips, {}, "en")
    assert ips["unique_circumstances"] == {
        "esg_preferences": None,
        "sector_restrictions": [],
        "screening_note": None,
    }


@pytest.mark.parametrize(
    "role", ["generator", "reviser", "suitability", "compliance", "consistency"]
)
@pytest.mark.parametrize("locale", ["en", "zh"])
def test_ips_roles_share_screening_boundary(role, locale):
    text = get_system_prompt(role, locale)
    assert ("never as implemented" if locale == "en" else "不得描述为已落实") in text

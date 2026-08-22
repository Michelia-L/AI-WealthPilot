"""Asset-class alias table tests (P25).

``config.ASSET_CLASS_ALIASES`` is the single bilingual source feeding
``monitoring._match_asset_class_key`` (SAA name -> proxy key) and
``ips_workflow._fuzzy_asset_match`` (SAA <-> CME same-category match).
These tests pin the zh/en demo-fixture SAA names and the CME fallback
asset names (always Chinese) to their expected category keys — the en
fixture names previously fell out of both mappings entirely.
"""

import json
from pathlib import Path

from src.agents.ips_workflow import _fuzzy_asset_match
from src.config import ASSET_CLASS_ALIASES, IPS_ASSET_CLASS_TICKERS
from src.portfolio.monitoring import _match_asset_class_key

_PROJECT_ROOT = Path(__file__).parent.parent
_DEMO_FIXTURES = _PROJECT_ROOT / "src" / "agents" / "demo_fixtures"
_CME_FALLBACK = _PROJECT_ROOT / "docs" / "ips_reference" / "cme_fallback.json"

# Expected IPS_ASSET_CLASS_TICKERS key per demo-fixture SAA name.
_ZH_FIXTURE_KEYS = {
    "国内权益（A股/沪深300）": "domestic_equity",
    "国际权益（发达市场）": "international_equity_dm",
    "固定收益": "fixed_income",
    "另类-黄金": "alternative_gold",
    "现金等价物": "cash",
}
_EN_FIXTURE_KEYS = {
    "Domestic Equity (A-shares / CSI 300)": "domestic_equity",
    "International Equity (Developed Markets)": "international_equity_dm",
    "Fixed Income": "fixed_income",
    "Alternatives — Gold": "alternative_gold",
    "Cash Equivalents": "cash",
}


def _fixture_saa_names(filename: str) -> list[str]:
    record = json.loads((_DEMO_FIXTURES / filename).read_text(encoding="utf-8"))
    saa = record["ips"]["investment_guidelines"]["strategic_allocation"]
    return [entry["asset_class"] for entry in saa]


def _cme_fallback_names() -> list[str]:
    report = json.loads(_CME_FALLBACK.read_text(encoding="utf-8"))
    return [entry["name"] for entry in report["asset_classes"]]


class TestFixtureGoldenMapping:
    """Every demo-fixture SAA name resolves to its category key (zh + en)."""

    def test_zh_fixture_names_match(self):
        names = _fixture_saa_names("ips_document.json")
        assert set(names) == set(_ZH_FIXTURE_KEYS)
        for name in names:
            assert _match_asset_class_key(name) == _ZH_FIXTURE_KEYS[name]

    def test_en_fixture_names_match(self):
        """The core P25 regression: en names previously fell out entirely."""
        names = _fixture_saa_names("ips_document_en.json")
        assert set(names) == set(_EN_FIXTURE_KEYS)
        for name in names:
            assert _match_asset_class_key(name) == _EN_FIXTURE_KEYS[name]


class TestCrossLanguageMatch:
    """en SAA names match their zh CME counterparts via _fuzzy_asset_match."""

    def test_en_saa_matches_zh_cme(self):
        cme_by_key = {
            _match_asset_class_key(name): name for name in _cme_fallback_names()
        }
        for saa_name, key in _EN_FIXTURE_KEYS.items():
            assert _fuzzy_asset_match(saa_name, cme_by_key[key])

    def test_mismatched_categories_do_not_match(self):
        assert not _fuzzy_asset_match("Fixed Income", "另类-黄金")
        assert not _fuzzy_asset_match("Domestic Equity (A-shares / CSI 300)", "港股")


class TestCmeFallbackCoverage:
    """The alias table covers the whole CME asset universe exactly once."""

    def test_every_cme_name_hits_a_distinct_category(self):
        names = _cme_fallback_names()
        keys = [_match_asset_class_key(name) for name in names]
        assert None not in keys
        assert len(set(keys)) == len(names)

    def test_cme_universe_covers_all_categories(self):
        keys = {_match_asset_class_key(name) for name in _cme_fallback_names()}
        assert keys == set(IPS_ASSET_CLASS_TICKERS)


class TestAliasTableContract:
    def test_keys_match_ticker_table(self):
        assert set(ASSET_CLASS_ALIASES) == set(IPS_ASSET_CLASS_TICKERS)

    def test_no_alias_shared_between_categories(self):
        seen: dict[str, str] = {}
        for key, aliases in ASSET_CLASS_ALIASES.items():
            for alias in aliases:
                assert alias not in seen, (
                    f"{alias!r} appears in both {seen[alias]} and {key}"
                )
                seen[alias] = key

    def test_prior_zh_keywords_kept_in_order(self):
        """Pre-P25 monitoring keywords survive as a subsequence of the
        flattened table, preserving the original first-hit priority."""
        prior = [
            ("国内权益", "domestic_equity"),
            ("A股", "domestic_equity"),
            ("沪深300", "domestic_equity"),
            ("国际权益", "international_equity_dm"),
            ("发达市场", "international_equity_dm"),
            ("港股", "international_equity_hk"),
            ("恒生", "international_equity_hk"),
            ("固定收益", "fixed_income"),
            ("固收", "fixed_income"),
            ("债", "fixed_income"),
            ("黄金", "alternative_gold"),
            ("Gold", "alternative_gold"),
            ("REIT", "alternative_reit"),
            ("房地产", "alternative_reit"),
            ("现金", "cash"),
            ("货币", "cash"),
            ("Cash", "cash"),
        ]
        derived = [
            (alias, key)
            for key, aliases in ASSET_CLASS_ALIASES.items()
            for alias in aliases
        ]
        idx = 0
        for pair in derived:
            if idx < len(prior) and pair == prior[idx]:
                idx += 1
        assert idx == len(prior)

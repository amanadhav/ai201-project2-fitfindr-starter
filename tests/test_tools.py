"""
tests/test_tools.py

Isolated tests for each FitFindr tool, with at least one test per failure mode.

The two LLM-backed tools (suggest_outfit, create_fit_card) are tested in a way
that does NOT require a live GROQ_API_KEY: we either monkeypatch the Groq client
or rely on the tools' own graceful fallbacks, so the suite always runs.

Run with:
    pytest tests/
"""

import pytest

import tools
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings (pure, no LLM) ─────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: nothing matches → empty list, not an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_is_case_insensitive_substring():
    # "m" should match listings whose size contains M, e.g. "M" or "S/M".
    results = search_listings("tee", size="m", max_price=None)
    assert all("m" in str(item["size"]).lower() for item in results)


def test_search_results_sorted_by_relevance():
    # More keyword overlap should not rank below less overlap.
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert isinstance(results, list)
    # Top result should mention at least one query keyword somewhere.
    if results:
        top = results[0]
        blob = (
            top["title"] + top["description"] + " ".join(top["style_tags"])
        ).lower()
        assert any(kw in blob for kw in ("vintage", "graphic", "tee"))


# ── suggest_outfit (LLM-backed, with fallback) ─────────────────────────────────

SAMPLE_ITEM = {
    "id": "lst_test",
    "title": "Faded Band Tee",
    "description": "Soft worn-in vintage band tee.",
    "category": "tops",
    "style_tags": ["grunge", "vintage", "band tee"],
    "size": "M",
    "condition": "good",
    "price": 22.0,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}


def test_suggest_outfit_returns_nonempty_string():
    result = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_empty_wardrobe_does_not_crash():
    # Failure mode: empty wardrobe → still returns useful, non-empty advice.
    result = suggest_outfit(SAMPLE_ITEM, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_handles_llm_error(monkeypatch):
    # Simulate the Groq client failing → tool must return a fallback, not raise.
    def boom():
        raise RuntimeError("simulated API outage")

    monkeypatch.setattr(tools, "_get_groq_client", boom)
    result = suggest_outfit(SAMPLE_ITEM, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card (LLM-backed, with fallback) ────────────────────────────────

def test_create_fit_card_empty_outfit_returns_message():
    # Failure mode: missing outfit → descriptive message, not a crash.
    result = create_fit_card("", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert "no outfit" in result.lower() or "can't" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_message():
    result = create_fit_card("   \n  ", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_handles_llm_error(monkeypatch):
    # Simulate API failure → templated fallback caption mentioning the item.
    def boom():
        raise RuntimeError("simulated API outage")

    monkeypatch.setattr(tools, "_get_groq_client", boom)
    result = create_fit_card("Tee with baggy jeans and boots", SAMPLE_ITEM)
    assert isinstance(result, str)
    assert "Faded Band Tee" in result


# ── Stretch: estimate_price_fairness ───────────────────────────────────────────

from tools import estimate_price_fairness, get_trending_styles


def test_price_fairness_returns_expected_shape():
    item = search_listings("graphic tee", None, None)[0]
    result = estimate_price_fairness(item)
    assert set(result) >= {
        "verdict", "item_price", "comparable_avg", "comparable_count", "message"
    }
    assert result["verdict"] in {"good_deal", "fair", "overpriced"}


def test_price_fairness_flags_a_cheap_item_as_good_deal():
    # An artificially cheap top should read as a good deal vs. real comps.
    cheap = {
        "id": "lst_fake", "title": "Cheap Tee", "description": "tee",
        "category": "tops", "style_tags": ["vintage"], "size": "M",
        "condition": "good", "price": 1.0, "colors": ["black"],
        "brand": None, "platform": "depop",
    }
    result = estimate_price_fairness(cheap)
    assert result["verdict"] == "good_deal"


def test_price_fairness_too_few_comps_is_fair_not_crash():
    lonely = {
        "id": "x", "title": "y", "description": "z", "category": "no_such_cat",
        "style_tags": [], "size": "M", "condition": "good", "price": 20.0,
        "colors": [], "brand": None, "platform": "depop",
    }
    result = estimate_price_fairness(lonely)
    assert result["verdict"] == "fair"
    assert result["comparable_count"] < 2


# ── Stretch: get_trending_styles ───────────────────────────────────────────────

def test_trending_styles_returns_ranked_tags():
    result = get_trending_styles(size=None, top_n=5)
    assert "trending" in result and isinstance(result["trending"], list)
    assert len(result["trending"]) <= 5
    if len(result["trending"]) >= 2:
        # Sorted most → least common.
        assert result["trending"][0][1] >= result["trending"][1][1]


def test_trending_styles_unknown_size_falls_back():
    result = get_trending_styles(size="ZZZ", top_n=3)
    # No listing has size ZZZ → falls back to all listings, still non-empty.
    assert result["sample_size"] > 0
    assert "trending" in result


# ── Stretch: style profile memory ──────────────────────────────────────────────

from utils.style_profile import (
    load_profile, update_profile, top_styles, save_profile, _empty_profile,
)


def test_profile_update_and_top_styles():
    profile = _empty_profile()
    item = {"style_tags": ["vintage", "grunge"], "size": "M"}
    update_profile(profile, item)
    update_profile(profile, {"style_tags": ["vintage"], "size": "M"})
    tops = top_styles(profile, n=2)
    assert tops[0] == "vintage"  # counted twice
    assert profile["interactions"] == 2
    assert profile["sizes"]["M"] == 2


def test_profile_load_missing_file_returns_empty(tmp_path):
    missing = str(tmp_path / "nope.json")
    profile = load_profile(missing)
    assert profile == _empty_profile()


def test_profile_round_trip(tmp_path):
    path = str(tmp_path / "profile.json")
    profile = _empty_profile()
    update_profile(profile, {"style_tags": ["y2k"], "size": "S"})
    save_profile(profile, path)
    reloaded = load_profile(path)
    assert reloaded["preferred_styles"]["y2k"] == 1

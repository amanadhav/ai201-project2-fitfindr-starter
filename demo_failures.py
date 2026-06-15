"""
demo_failures.py — deliberate failure-mode triggers (Milestone 5).

Run with:  python demo_failures.py

Each section triggers one tool's failure mode and shows that the agent
recovers gracefully (no exceptions, informative output).
"""

from tools import search_listings, suggest_outfit, create_fit_card
from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


def line():
    print("=" * 70)


line()
print("FAILURE 1a — search_listings returns zero results (no exception)")
line()
result = search_listings("designer ballgown", size="XXS", max_price=5)
print("Return value:", result)
print("Type:", type(result).__name__, "| Empty list, no crash:", result == [])

print()
line()
print("FAILURE 1b — full agent on the impossible query (actionable error)")
line()
session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
print("session['error']      :", session["error"])
print("session['selected_item']:", session["selected_item"])
print("session['fit_card']   :", session["fit_card"])

print()
line()
print("FAILURE 2 — suggest_outfit with an EMPTY wardrobe (general advice)")
line()
matches = search_listings("vintage graphic tee", size=None, max_price=50)
advice = suggest_outfit(matches[0], get_empty_wardrobe())
print("Item:", matches[0]["title"])
print("Non-empty string returned:", bool(advice.strip()))
print("Output:\n", advice)

print()
line()
print("FAILURE 3 — create_fit_card with an EMPTY outfit string (message)")
line()
card = create_fit_card("", matches[0])
print("Output:", card)
print("Is a descriptive string (not an exception):", isinstance(card, str))

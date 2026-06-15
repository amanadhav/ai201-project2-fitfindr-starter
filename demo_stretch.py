"""
demo_stretch.py — demonstrates all four stretch features end-to-end.

Run with:  python demo_stretch.py
"""

import os
from agent import run_agent
from utils.data_loader import get_example_wardrobe
from utils.style_profile import load_profile

SEP = "=" * 70


def show(session):
    print("Selected:", session["selected_item"]["title"],
          f"(${session['selected_item']['price']:.0f})")
    if session["adjustments"]:
        print("Adjustments:", " ".join(session["adjustments"]))
    if session["price_check"]:
        print("Price check:", session["price_check"]["message"])
    if session["trending"]:
        print("Trending:", session["trending"]["message"])
    if session["preferred_styles"]:
        print("Applied remembered styles:", session["preferred_styles"])
    print("Outfit:", session["outfit_suggestion"][:200], "...")


print(SEP)
print("STRETCH 1 + 2 — Price comparison + Trend awareness (happy path)")
print(SEP)
s1 = run_agent("vintage graphic tee under $30", get_example_wardrobe())
show(s1)

print("\n" + SEP)
print("STRETCH 4 — Retry logic with fallback (impossible size, loosened)")
print(SEP)
# A jacket in an impossible size → retry drops the size filter.
s2 = run_agent("track jacket size XXS", get_example_wardrobe())
if s2["error"]:
    print("ERROR:", s2["error"])
else:
    print("Recovered after retry.")
    show(s2)

print("\n" + SEP)
print("STRETCH 3 — Style profile memory (two sessions, fresh profile)")
print(SEP)
# Use an isolated profile file so the demo is repeatable.
test_profile = os.path.join("data", "style_profile.json")
if os.path.exists(test_profile):
    os.remove(test_profile)

print("Session A (learns from a grunge/vintage pick):")
a = run_agent("vintage grunge flannel", get_example_wardrobe(), use_memory=True)
print("  picked:", a["selected_item"]["title"], "| tags:", a["selected_item"]["style_tags"])
print("  profile now:", load_profile())

print("\nSession B (new query, memory applied without re-describing taste):")
b = run_agent("graphic tee", get_example_wardrobe(), use_memory=True)
print("  preferred_styles carried in:", b["preferred_styles"])
print("  (these were learned in Session A, not entered in Session B)")

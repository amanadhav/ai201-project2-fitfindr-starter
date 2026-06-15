"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    estimate_price_fairness,
    get_trending_styles,
)
from utils.style_profile import (
    load_profile,
    update_profile,
    top_styles,
    save_profile,
)

import re


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract search parameters from a natural-language query.

    Deterministic string parsing (regex), not an LLM call — cheap and testable.

    Returns a dict with keys:
        description (str): the query with size/price phrases stripped out
        size (str | None): e.g. "M", "8", "XL" if mentioned, else None
        max_price (float | None): a price ceiling if mentioned, else None
    """
    text = query or ""
    max_price = None
    size = None

    # max_price: "under $30", "below 30", "less than $25", or a bare "$40".
    price_match = re.search(
        r"(?:under|below|less than|max|up to)\s*\$?\s*(\d+(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if not price_match:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if price_match:
        max_price = float(price_match.group(1))

    # size: "size M", "size 8", "in a medium". Capture common letter/number sizes.
    size_match = re.search(
        r"\bsize\s+([a-z0-9]+)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not size_match:
        size_match = re.search(
            r"\b(xxs|xs|s|m|l|xl|xxl)\b",
            text,
            flags=re.IGNORECASE,
        )
    if size_match:
        size = size_match.group(1).upper()

    # description: strip the price and size phrases so they don't pollute keywords.
    description = text
    description = re.sub(
        r"(?:under|below|less than|max|up to)\s*\$?\s*\d+(?:\.\d+)?",
        " ",
        description,
        flags=re.IGNORECASE,
    )
    description = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", description)
    description = re.sub(r"\bsize\s+[a-z0-9]+\b", " ", description, flags=re.IGNORECASE)
    description = re.sub(r"\s+", " ", description).strip()

    return {"description": description or text.strip(), "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
        # ── stretch feature state ──
        "adjustments": [],           # human-readable notes when constraints loosened
        "price_check": None,         # dict from estimate_price_fairness
        "trending": None,            # dict from get_trending_styles
        "preferred_styles": [],      # remembered styles applied this session
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict, use_memory: bool = False) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py
        use_memory: (stretch) when True, load the persisted style profile to
                  bias suggestions toward the user's remembered taste, and save
                  updated preferences after a successful interaction.

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: Initialize the session — single source of truth for this run.
    session = _new_session(query, wardrobe)

    # Stretch (style memory): load remembered preferences for a returning user.
    profile = load_profile() if use_memory else None
    if profile:
        session["preferred_styles"] = top_styles(profile, n=3)

    # Step 2: Parse the query into description / size / max_price.
    parsed = _parse_query(query)
    session["parsed"] = parsed

    # Step 3: Search. Branch on the result — this is what makes the loop a
    #         planning loop rather than a fixed pipeline.
    session["search_results"] = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    # Stretch (retry logic with fallback): if nothing matched AND a size filter
    # was applied, automatically retry once without the size filter and tell the
    # user what was adjusted — rather than giving up immediately.
    if not session["search_results"] and parsed["size"] is not None:
        retry = search_listings(
            description=parsed["description"],
            size=None,
            max_price=parsed["max_price"],
        )
        if retry:
            session["search_results"] = retry
            session["adjustments"].append(
                f"No matches in size {parsed['size']}, so I dropped the size "
                f"filter and searched all sizes."
            )

    if not session["search_results"]:
        # No matches (even after any retry) → specific, actionable error. STOP.
        loosen = []
        if parsed["max_price"] is not None:
            loosen.append("raising your price")
        if parsed["size"] is not None:
            loosen.append("removing the size filter")
        loosen.append("using broader keywords")
        session["error"] = (
            f"No listings matched '{parsed['description']}'"
            + (f" under ${parsed['max_price']:.0f}" if parsed["max_price"] is not None else "")
            + (f" in size {parsed['size']}" if parsed["size"] else "")
            + ". Try " + ", ".join(loosen) + "."
        )
        return session

    # Step 4: Select the top-ranked result and store it in state. This exact
    #         dict flows into both downstream tools — no re-entry by the user.
    session["selected_item"] = session["search_results"][0]

    # Stretch (price comparison): assess whether the price is fair.
    session["price_check"] = estimate_price_fairness(session["selected_item"])

    # Stretch (trend awareness): find what's trending in the user's size range
    # so it can visibly influence the outfit suggestion below.
    session["trending"] = get_trending_styles(size=parsed["size"], top_n=5)
    trending_tags = [tag for tag, _count in session["trending"]["trending"]]

    # Step 5: Suggest an outfit using the selected item + wardrobe, biased by
    #         trending styles and (if enabled) remembered preferences.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
        trending_styles=trending_tags,
        preferred_styles=session["preferred_styles"] or None,
    )

    if not session["outfit_suggestion"]:
        # Defensive: the tool is built to always return text, but if it somehow
        # returns falsy, stop before the fit card rather than feed it nothing.
        session["error"] = "Couldn't generate an outfit suggestion for this item."
        return session

    # Step 6: Generate the shareable fit card from the outfit + selected item.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Stretch (style memory): record this interaction's preferences for next time.
    if use_memory and profile is not None:
        update_profile(profile, session["selected_item"])
        save_profile(profile)

    # Step 7: Return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

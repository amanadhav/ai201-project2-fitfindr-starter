"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Model used for the two LLM-backed tools.
_MODEL = "llama-3.3-70b-versatile"

# Tokens too common to carry meaning when scoring keyword relevance.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "in", "on", "of", "to",
    "my", "i", "im", "looking", "want", "need", "some", "that", "this",
    "under", "size", "find", "me", "something", "really", "very", "wear",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _tokenize(text: str) -> list[str]:
    """Lowercase a string and split it into meaningful word tokens."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    # 1. Load everything from the data loader (don't re-read the file).
    listings = load_listings()

    query_tokens = _tokenize(description or "")
    size_filter = size.strip().lower() if size else None

    scored: list[tuple[int, dict]] = []
    for item in listings:
        # 2a. Price filter (inclusive). Skip if over budget.
        if max_price is not None and item.get("price", 0) > max_price:
            continue

        # 2b. Size filter — case-insensitive substring match so "m" matches
        #     "S/M" and "M (oversized)". None skips this filter entirely.
        if size_filter:
            item_size = str(item.get("size", "")).lower()
            if size_filter not in item_size:
                continue

        # 3. Score by keyword overlap against title, description, style_tags.
        haystack_tokens = set(
            _tokenize(item.get("title", ""))
            + _tokenize(item.get("description", ""))
            + _tokenize(" ".join(item.get("style_tags", [])))
        )
        score = sum(1 for tok in query_tokens if tok in haystack_tokens)

        # 4. Drop anything with no keyword relevance. If the caller gave no
        #    description at all, keep everything that passed the filters.
        if query_tokens and score == 0:
            continue

        scored.append((score, item))

    # 5. Sort by score (highest first); stable sort preserves dataset order
    #    for ties. Return just the listing dicts.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _score, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(
    new_item: dict,
    wardrobe: dict,
    trending_styles: list[str] | None = None,
    preferred_styles: list[str] | None = None,
) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.
        trending_styles: (stretch) optional list of currently-trending style
                  tags. When provided, the model is told to lean into any that
                  match the item so trends visibly shape the advice.
        preferred_styles: (stretch) optional list of the user's remembered
                  preferred style tags from past sessions, so a returning user
                  gets advice tilted toward their taste without re-describing it.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Pull the item details we want the model to reason about.
    item_title = new_item.get("title", "this piece")
    item_desc = new_item.get("description", "")
    item_tags = ", ".join(new_item.get("style_tags", [])) or "n/a"
    item_colors = ", ".join(new_item.get("colors", [])) or "n/a"
    item_category = new_item.get("category", "n/a")

    # Optional context lines (stretch features). Empty string when not provided
    # so the base behavior is unchanged.
    context = ""
    if trending_styles:
        context += (
            f"\nCurrently trending styles: {', '.join(trending_styles)}. "
            f"If any of these match the item, lean into that angle and say so."
        )
    if preferred_styles:
        context += (
            f"\nThe user has previously gravitated toward these styles: "
            f"{', '.join(preferred_styles)}. Tilt the suggestion toward their taste."
        )

    items = (wardrobe or {}).get("items", [])

    if items:
        # Non-empty wardrobe: name specific pieces in the prompt.
        wardrobe_lines = "\n".join(
            f"- {w.get('name', 'item')} ({w.get('category', '?')}; "
            f"colors: {', '.join(w.get('colors', [])) or 'n/a'}; "
            f"tags: {', '.join(w.get('style_tags', [])) or 'n/a'})"
            for w in items
        )
        user_prompt = (
            f"A user is considering buying this thrifted item:\n"
            f"  Title: {item_title}\n"
            f"  Category: {item_category}\n"
            f"  Colors: {item_colors}\n"
            f"  Style tags: {item_tags}\n"
            f"  Description: {item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_lines}\n"
            f"{context}\n\n"
            f"Suggest 1–2 complete outfits that pair the new item with SPECIFIC "
            f"pieces from their wardrobe, referring to those pieces by name. "
            f"End with one short concrete styling tip (e.g. tuck, roll, cuff, layer). "
            f"Keep it to a few sentences, friendly and practical — no markdown."
        )
    else:
        # Empty wardrobe: ask for general styling advice instead.
        user_prompt = (
            f"A user is considering buying this thrifted item:\n"
            f"  Title: {item_title}\n"
            f"  Category: {item_category}\n"
            f"  Colors: {item_colors}\n"
            f"  Style tags: {item_tags}\n"
            f"  Description: {item_desc}\n"
            f"{context}\n\n"
            f"The user hasn't entered any wardrobe pieces yet. Give general styling "
            f"advice for this item: what kinds of pieces pair well with it, what vibe "
            f"it suits, and one concrete styling tip. Keep it to a few sentences, "
            f"friendly and practical — no markdown."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a sharp, encouraging personal stylist who "
                    "gives specific, wearable outfit advice.",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
        # Fall through to fallback if the model returned nothing.
        raise ValueError("empty model response")
    except Exception:
        # LLM/network/key error → graceful, non-empty fallback from item tags.
        tag_hint = item_tags if item_tags != "n/a" else item_category
        return (
            f"Couldn't reach the styling model right now, but based on its tags "
            f"({tag_hint}), {item_title} leans that aesthetic — try pairing it with "
            f"relaxed denim or trousers and a pair of boots or chunky sneakers to "
            f"build a complete look."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty / whitespace-only outfit.
    if not outfit or not outfit.strip():
        return "Can't write a fit card yet — no outfit suggestion was generated."

    new_item = new_item or {}
    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "a thrift app")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"

    # 2. Build the caption prompt.
    user_prompt = (
        f"Write a short, shareable Instagram/TikTok caption for an outfit post.\n\n"
        f"Thrifted item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"Outfit being worn: {outfit}\n\n"
        f"Rules:\n"
        f"- 2 to 4 sentences, casual first-person OOTD voice (lowercase is fine).\n"
        f"- Mention the item name, the price, and the platform once each, naturally.\n"
        f"- Capture the outfit's vibe in specific terms — not a product description.\n"
        f"- Add an emoji or two. Sound like a real person hyped about a thrift find."
    )

    # 3. Call the LLM at a high temperature so repeat runs vary.
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You write punchy, authentic social-media outfit "
                    "captions. Never sound like a product listing.",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=1.0,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
        raise ValueError("empty model response")
    except Exception:
        # Templated fallback so the user still gets something shareable.
        return f"thrifted this {title} for {price_str} off {platform} ✨ obsessed with how it came together"


# ── Tool 4 (stretch): estimate_price_fairness ─────────────────────────────────

def estimate_price_fairness(item: dict, listings: list[dict] | None = None) -> dict:
    """
    Estimate whether an item's price is fair, given comparable listings.

    Comparison method: find other listings in the SAME category. Among those,
    prefer ones that share at least one style_tag with the item (closer comps);
    if there are fewer than 2 tag-sharing comps, fall back to all same-category
    listings so we still have something to compare against. The item is compared
    to the average price of its comparables:
        price <= 85% of avg  → "good_deal"
        price >= 115% of avg → "overpriced"
        otherwise            → "fair"

    Args:
        item:     A listing dict (normally the selected item).
        listings: Comparison pool; defaults to load_listings() when None.

    Returns:
        dict with keys:
            verdict ("good_deal" | "fair" | "overpriced"),
            item_price (float), comparable_avg (float),
            comparable_count (int), message (str).
        Never raises; with too few comps returns verdict="fair" with a note.
    """
    try:
        pool = listings if listings is not None else load_listings()
        item_price = float(item.get("price", 0) or 0)
        category = item.get("category")
        item_tags = set(item.get("style_tags", []) or [])
        item_id = item.get("id")

        # Same-category comps, excluding the item itself.
        same_cat = [
            l for l in pool
            if l.get("category") == category and l.get("id") != item_id
        ]
        # Prefer comps that share a style tag.
        tag_comps = [
            l for l in same_cat
            if item_tags & set(l.get("style_tags", []) or [])
        ]
        comps = tag_comps if len(tag_comps) >= 2 else same_cat

        prices = [float(l["price"]) for l in comps if l.get("price") is not None]
        count = len(prices)

        if count < 2:
            return {
                "verdict": "fair",
                "item_price": item_price,
                "comparable_avg": item_price,
                "comparable_count": count,
                "message": (
                    f"Not enough comparable listings to judge confidently — "
                    f"treating ${item_price:.0f} as fair."
                ),
            }

        avg = sum(prices) / count
        if item_price <= 0.85 * avg:
            verdict = "good_deal"
            summary = f"a good deal — about {(1 - item_price / avg) * 100:.0f}% below"
        elif item_price >= 1.15 * avg:
            verdict = "overpriced"
            summary = f"on the high side — about {(item_price / avg - 1) * 100:.0f}% above"
        else:
            verdict = "fair"
            summary = "right around"

        return {
            "verdict": verdict,
            "item_price": item_price,
            "comparable_avg": round(avg, 2),
            "comparable_count": count,
            "message": (
                f"At ${item_price:.0f}, this is {summary} the ${avg:.0f} average "
                f"for {count} comparable {category} listings."
            ),
        }
    except Exception:
        # Defensive: never break the agent over a price estimate.
        return {
            "verdict": "fair",
            "item_price": float(item.get("price", 0) or 0),
            "comparable_avg": 0.0,
            "comparable_count": 0,
            "message": "Couldn't estimate price fairness for this item.",
        }


# ── Tool 5 (stretch): get_trending_styles ─────────────────────────────────────

def get_trending_styles(
    size: str | None = None,
    top_n: int = 5,
    listings: list[dict] | None = None,
) -> dict:
    """
    Surface currently-popular styles by tallying style_tags across the listings
    dataset, optionally narrowed to the user's size range.

    Data source: data/listings.json represents current live secondhand listings
    on depop / poshmark / thredUp. We treat the frequency of a style_tag among
    active listings as a proxy for what's trending (no live platform API is
    provided in the starter kit, so this is documented as the trend signal).

    Args:
        size:     Restrict the tally to listings whose size contains this string
                  (case-insensitive). None = all listings.
        top_n:    How many trending tags to return.
        listings: Source pool; defaults to load_listings() when None.

    Returns:
        dict: {
            "trending": [(tag, count), ...],   # most → least common
            "size": size,
            "sample_size": int,                # listings tallied
            "message": str,
        }
        If the size filter matches nothing, falls back to all listings and notes
        it in message. Never raises.
    """
    try:
        pool = listings if listings is not None else load_listings()
        size_filter = size.strip().lower() if size else None

        scoped = pool
        fell_back = False
        if size_filter:
            matched = [
                l for l in pool
                if size_filter in str(l.get("size", "")).lower()
            ]
            if matched:
                scoped = matched
            else:
                fell_back = True  # keep full pool

        counts: dict[str, int] = {}
        for l in scoped:
            for tag in l.get("style_tags", []) or []:
                counts[tag] = counts.get(tag, 0) + 1

        trending = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
        tag_names = ", ".join(t for t, _ in trending) or "n/a"

        if fell_back:
            msg = (
                f"No listings found in size {size}; showing overall trending "
                f"styles instead: {tag_names}."
            )
        elif size_filter:
            msg = f"Trending in size {size} right now: {tag_names}."
        else:
            msg = f"Trending across all listings right now: {tag_names}."

        return {
            "trending": trending,
            "size": size,
            "sample_size": len(scoped),
            "message": msg,
        }
    except Exception:
        return {
            "trending": [],
            "size": size,
            "sample_size": 0,
            "message": "Couldn't compute trending styles right now.",
        }

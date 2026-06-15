"""
utils/style_profile.py  (stretch: Style Profile Memory)

Persists a user's style preferences across sessions so a returning user doesn't
have to re-describe their taste. We store only aggregate counts — no PII.

Storage: a small JSON file at data/style_profile.json shaped like:
    {
        "preferred_styles": {"vintage": 3, "grunge": 2, ...},
        "sizes": {"M": 2, "L": 1},
        "interactions": 4
    }

Flow:
    - At the start of a session, load_profile() reads the file (or an empty
      profile if it's missing/corrupt) and top_styles() yields the user's
      favorite tags to bias outfit suggestions.
    - After a successful interaction, update_profile() increments counts from
      the selected item, and save_profile() writes it back.

Every function degrades gracefully — a missing or unreadable file simply yields
a fresh empty profile, so a brand-new user behaves exactly like the no-memory
path.
"""

import json
import os

_DEFAULT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "style_profile.json"
)


def _empty_profile() -> dict:
    return {"preferred_styles": {}, "sizes": {}, "interactions": 0}


def load_profile(path: str | None = None) -> dict:
    """Load the style profile, or return a fresh empty one if absent/corrupt."""
    path = path or _DEFAULT_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Validate shape; fall back to empty on anything unexpected.
        if not isinstance(data, dict) or "preferred_styles" not in data:
            return _empty_profile()
        data.setdefault("preferred_styles", {})
        data.setdefault("sizes", {})
        data.setdefault("interactions", 0)
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _empty_profile()


def update_profile(profile: dict, item: dict) -> dict:
    """
    Increment preference counts from one selected listing.

    Mutates and returns the profile dict.
    """
    if not item:
        return profile
    profile.setdefault("preferred_styles", {})
    profile.setdefault("sizes", {})

    for tag in item.get("style_tags", []) or []:
        profile["preferred_styles"][tag] = profile["preferred_styles"].get(tag, 0) + 1

    size = item.get("size")
    if size:
        profile["sizes"][size] = profile["sizes"].get(size, 0) + 1

    profile["interactions"] = profile.get("interactions", 0) + 1
    return profile


def top_styles(profile: dict, n: int = 3) -> list[str]:
    """Return the user's most-preferred style tags, most common first."""
    styles = (profile or {}).get("preferred_styles", {})
    return [
        tag
        for tag, _count in sorted(
            styles.items(), key=lambda kv: (-kv[1], kv[0])
        )[:n]
    ]


def save_profile(profile: dict, path: str | None = None) -> None:
    """Write the profile to disk atomically. Silently no-ops on write error."""
    path = path or _DEFAULT_PATH
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass

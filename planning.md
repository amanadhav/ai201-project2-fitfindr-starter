# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Filters the 40-item mock listings dataset by price and size, then scores the survivors by keyword overlap against the user's description and returns them ranked best-match-first. It is a pure, deterministic function — no LLM call — so it is fast and easy to test in isolation.

**Input parameters:**
- `description` (str): Free-text keywords describing the wanted item, e.g. `"vintage graphic tee"`. Tokenized and matched (case-insensitive) against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): Size to filter by, e.g. `"M"`. Matched case-insensitively as a substring so `"M"` matches `"S/M"` and `"M (oversized)"`. `None` skips the size filter entirely.
- `max_price` (float | None): Inclusive price ceiling, e.g. `30.0`. Listings with `price > max_price` are dropped. `None` skips the price filter.

**What it returns:**
A `list[dict]` of matching listing dicts, sorted by relevance score (highest first). Each dict is the full listing record: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Listings that score 0 on keyword overlap are excluded. Returns an empty list `[]` when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
Returns `[]` rather than raising. The planning loop detects the empty list and sets a helpful `session["error"]` ("No listings matched 'X' under $Y in size Z — try raising the price, dropping the size, or using broader keywords"), then returns early without calling the downstream tools. (Stretch: retry with the size filter removed before giving up.)

---

### Tool 2: suggest_outfit

**What it does:**
Takes the thrifted item the user is considering plus their current wardrobe and asks the LLM to propose 1–2 complete, wearable outfits that pair the new item with specific named pieces from the wardrobe. Handles an empty wardrobe by switching to general styling advice instead.

**Input parameters:**
- `new_item` (dict): A single listing dict (normally `session["selected_item"]`, the top search result). The tool reads its `title`, `category`, `colors`, `style_tags`, and `description` to build the prompt.
- `wardrobe` (dict): A wardrobe dict shaped like `{"items": [...]}` where each item has `name`, `category`, `colors`, `style_tags`, and optional `notes`. May be empty (`{"items": []}`).

**What it returns:**
A non-empty `str` containing the outfit suggestion(s) in natural language — referencing the new item and, when the wardrobe is non-empty, specific pieces from it by name (e.g. "your baggy straight-leg jeans + chunky white sneakers"), plus a one-line styling tip (tuck, roll, layer). Plain prose, no markdown required.

**What happens if it fails or returns nothing:**
- Empty wardrobe → the tool itself falls back to general styling advice ("This pairs well with high-waisted denim and chunky boots for a grunge feel…") so it always returns useful text.
- LLM/network error → caught and returned as a graceful fallback string built from the item's own `style_tags`/`colors` ("Couldn't reach the styling model — based on its tags this leans grunge/streetwear, so try it with relaxed denim and boots"). Never returns `""` and never raises to the loop.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion into a short, casual, shareable caption — the kind of thing someone captions an OOTD post with. Uses a higher LLM temperature so the same item yields a fresh caption each run.

**Input parameters:**
- `outfit` (str): The outfit suggestion text returned by `suggest_outfit()` (`session["outfit_suggestion"]`).
- `new_item` (dict): The listing dict for the thrifted item, used to mention `title`, `price`, and `platform` naturally (once each) in the caption.

**What it returns:**
A 2–4 sentence `str` written in a casual first-person OOTD voice (lowercase-friendly, an emoji or two, no product-listing phrasing). Mentions the item name, price, and platform once each and captures the outfit vibe in specific terms. Different inputs / repeat runs produce different captions.

**What happens if it fails or returns nothing:**
- `outfit` empty or whitespace-only → returns a clear descriptive string ("Can't write a fit card yet — no outfit suggestion was generated.") rather than raising.
- LLM/network error → returns a simple templated fallback caption built from the item fields ("thrifted this {title} for ${price} off {platform} ✨") so the user still gets something shareable.

---

### Additional Tools (if any)

### Tool 4 (stretch): estimate_price_fairness

**What it does:**
Given a listing, compares its price against comparable listings in the same `category` (and overlapping `style_tags`) in the dataset and reports whether the price is a good deal, fair, or high. Pure/deterministic — no LLM.

**Input parameters:**
- `item` (dict): A listing dict (normally `session["selected_item"]`).
- `listings` (list[dict] | None): Comparison pool; defaults to `load_listings()` when `None`.

**What it returns:**
A `dict`: `{"verdict": "good_deal" | "fair" | "overpriced", "item_price": float, "comparable_avg": float, "comparable_count": int, "message": str}` where `message` is a one-line human summary.

**What happens if it fails or returns nothing:**
If there are too few comparables (`comparable_count < 2`), returns `verdict="fair"` with a message noting there wasn't enough data to judge confidently — never divides by zero, never raises.

---

### Tool 5 (stretch): get_trending_styles

**What it does:**
Derives what styles are currently popular by tallying `style_tags` across the listings dataset, optionally narrowed to listings that fit the user's size. Surfaces the top trending tags. Pure/deterministic — no LLM. **Data source:** the mock `listings.json`, which represents current live secondhand listings on depop/poshmark/thredUp; trend = tag frequency among active listings (documented, since no live platform API is provided in the starter).

**Input parameters:**
- `size` (str | None): Restrict the trend tally to listings matching this size (case-insensitive substring). `None` = all listings.
- `top_n` (int): How many trending tags to return (default 5).
- `listings` (list[dict] | None): Source pool; defaults to `load_listings()`.

**What it returns:**
A `dict`: `{"trending": [(tag, count), ...], "size": size, "sample_size": int, "message": str}` — `trending` sorted most→least common, `message` a one-line human summary.

**What happens if it fails or returns nothing:**
If no listings match the size filter, falls back to all-listings trends and notes the fallback in `message`; never raises.

**How it influences output:** the planning loop passes the top trending tags into `suggest_outfit`, which is told to lean into any that match the item — so the trend visibly shapes the styling advice.

---

### Tool 6 (stretch): style profile memory (utils/style_profile.py)

**What it does:**
Persists a user's style preferences across sessions to `data/style_profile.json` so a returning user doesn't re-describe their taste. Each completed interaction increments counts for the selected item's `style_tags` and size; the next session reads the top preferred styles and passes them into `suggest_outfit`.

**Functions / interfaces:**
- `load_profile(path) -> dict`: returns `{"preferred_styles": {tag: count}, "sizes": {size: count}, "interactions": int}`; returns an empty profile if the file is missing/corrupt.
- `update_profile(profile, item) -> dict`: increments counts from one selected listing.
- `top_styles(profile, n=3) -> list[str]`: the most-preferred tags.
- `save_profile(profile, path) -> None`: writes JSON atomically.

**What it returns / stored:** a small JSON dict on disk (counts only, no PII).

**What happens if it fails or returns nothing:** a missing or unreadable file yields a fresh empty profile (no crash); a brand-new user simply has no preferences to apply, and the agent behaves exactly as the non-memory path.

---

### Stretch retry logic (in the planning loop)

When `search_listings` returns `[]` **and** a size filter was applied, the loop automatically retries once with `size=None`, records the adjustment in `session["adjustments"]`, and — if the retry succeeds — continues normally while telling the user the size filter was dropped. Only if the retry also returns empty does it set `session["error"]`.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is condition-driven: each step only runs if the previous step produced usable state, and the no-results case branches out early. Concretely:

1. **Initialize** — `session = _new_session(query, wardrobe)`. All result fields start `None`/empty, `error` starts `None`.

2. **Parse the query** — Extract `description`, `size`, and `max_price` from the raw query (regex: `under $30` / `$30` → `max_price`; `size M` / `size 8` → `size`; the leftover text → `description`). Store in `session["parsed"]`. This is deterministic string parsing, not an LLM call, so it's testable and cheap.

3. **Branch — search** — Call `search_listings(description, size, max_price)`; store in `session["search_results"]`.
   - **If `search_results` is empty:** set `session["error"]` to a specific, actionable message naming what to loosen, and `return session` immediately. **Do not** call `suggest_outfit` or `create_fit_card`. (Stretch retry: if empty *and* a size filter was applied, re-run once with `size=None`, record the adjustment in `session["adjustments"]`, and only error out if that also returns empty.)
   - **If `search_results` is non-empty:** set `session["selected_item"] = search_results[0]` (top-ranked) and continue.

4. **Suggest** — Call `suggest_outfit(session["selected_item"], session["wardrobe"])`; store in `session["outfit_suggestion"]`. This tool self-handles the empty-wardrobe case, so the loop doesn't branch here — but if it somehow returns falsy, set `session["error"]` and return before the fit card.

5. **Fit card** — Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`; store in `session["fit_card"]`.

6. **Done** — `return session`. The caller checks `session["error"]` first; if `None`, all three output fields are populated.

The behavior is not fixed: a no-match query exits after step 3 with only an error, a match with an empty wardrobe still completes all three steps but with general styling advice, and a normal query completes the full chain. What gets called depends entirely on what each step returns.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()`) is the one source of truth for the whole interaction and is threaded through every step. Tracked fields:

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | init | parse step |
| `parsed` (`description`, `size`, `max_price`) | parse step | `search_listings` |
| `search_results` (list[dict]) | `search_listings` | selection step |
| `selected_item` (dict) | selection step (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` (dict) | init (from UI choice) | `suggest_outfit` |
| `outfit_suggestion` (str) | `suggest_outfit` | `create_fit_card` |
| `fit_card` (str) | `create_fit_card` | returned to UI |
| `error` (str or None) | any step that fails | checked first by caller |

The user types the query once. The item found in step 3 lives in `session["selected_item"]` and flows into both `suggest_outfit` and `create_fit_card` automatically — the user never re-enters it. Because state is one plain dict returned at the end, it's trivial to inspect in tests and print in the demo.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` to a specific message: *"No listings matched 'vintage graphic tee' under $30 in size M. Try raising your price, removing the size filter, or using broader keywords like 'graphic tee'."* Return early — never call the next tools with empty input. (Stretch: auto-retry once without the size filter and tell the user it was dropped.) |
| suggest_outfit | Wardrobe is empty | Tool detects `wardrobe["items"] == []` and returns **general** styling advice for the item (vibe + what categories pair well) instead of naming specific pieces. The chain still completes through to a fit card. |
| suggest_outfit | LLM/network error | Caught inside the tool; returns a fallback string built from the item's own `style_tags`/`colors` so it's never empty and never raises into the loop. |
| create_fit_card | Outfit input is missing or incomplete | If `outfit` is empty/whitespace, return *"Can't write a fit card yet — no outfit suggestion was generated."* On LLM error, return a templated caption (`thrifted this {title} for ${price} off {platform} ✨`). Never raises. |

---

## Architecture

```
                                User query + wardrobe choice
                                          │
                                          ▼
        ┌──────────────────────────  PLANNING LOOP  ──────────────────────────┐
        │                                                                      │
        │  parse query ──► session["parsed"] = {description, size, max_price}  │
        │       │                                                              │
        │       ▼                                                              │
        ├─► search_listings(description, size, max_price)                      │
        │       │                                                              │
        │       │ results == []                                                │
        │       ├──► session["error"] = "No listings matched..."  ──► return ──┤  (ERROR
        │       │                                                              │   PATH
        │       │ results == [item, ...]                                       │   returns
        │       ▼                                                              │   here)
        │   session["selected_item"] = results[0]                              │
        │       │                                                              │
        │       ▼                                                              │
        ├─► suggest_outfit(selected_item, wardrobe)                            │
        │       │     (empty wardrobe → general advice, still returns text)    │
        │       ▼                                                              │
        │   session["outfit_suggestion"] = "..."                               │
        │       │                                                              │
        │       ▼                                                              │
        └─► create_fit_card(outfit_suggestion, selected_item)                  │
                │     (empty outfit → descriptive message)                     │
                ▼                                                              │
            session["fit_card"] = "..."                                        │
                │                                                              │
                └──────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                            Return session  ──►  UI panels:
                              • Top listing found
                              • Outfit idea
                              • Fit card
                            (or error message if session["error"] is set)

   SESSION STATE (single dict, threaded through every step):
   query → parsed → search_results → selected_item → outfit_suggestion → fit_card → error
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings** — I'll give Claude (in Kiro) the **Tool 1** block from this planning.md (the three params, the ranked-list return shape, the empty-list failure mode) plus the listings field list, and ask it to implement the function using `load_listings()`. Before trusting it I'll verify the generated code (a) filters by `max_price` *and* `size` *and* keyword score, (b) does case-insensitive substring matching for size, (c) drops zero-score listings, and (d) returns `[]` (not an exception) when nothing matches. Then I'll test 3 queries: `"vintage graphic tee", max_price=30` (expect graphic tees), `"track jacket", size="M"` (expect lst_004), and `"designer ballgown", max_price=5` (expect `[]`).

- **suggest_outfit** — I'll give Claude the **Tool 2** block plus the wardrobe schema, and ask it to build a Groq prompt that pairs the new item with named wardrobe pieces, with an explicit empty-wardrobe branch and a try/except fallback. I'll verify by running it once with `get_example_wardrobe()` (output must name real pieces like "baggy straight-leg jeans") and once with `get_empty_wardrobe()` (output must still be non-empty general advice).

- **create_fit_card** — I'll give Claude the **Tool 3** block and ask for a higher-temperature Groq call producing a casual caption that names item/price/platform once each, plus the empty-outfit guard. I'll verify by running it twice on the same item and confirming the two captions differ, and by passing `outfit=""` and confirming I get the descriptive message, not a crash.

**Milestone 4 — Planning loop and state management:**

- I'll give Claude the **Planning Loop**, **State Management**, and **Architecture** (ASCII diagram) sections together, plus the `_new_session()` stub already in `agent.py`, and ask it to implement `run_agent()` exactly matching the diagram's branch order and the session field names. I'll verify by running the two scenarios already in `agent.py`'s `__main__`: the happy path (all three fields populated, `error is None`) and the no-results path (`error` set, other fields `None`). I'll also confirm `selected_item` flows into both downstream tools without re-entry. Finally I'll wire `handle_query()` in `app.py` to map the session to the three panels and smoke-test in the Gradio UI.

---

## A Complete Interaction (Step by Step)

**What FitFindr needs to do (in my own words):**
FitFindr takes a natural-language thrifting request and runs it through three tools in sequence, carrying state forward at each step. A search query triggers `search_listings`, which filters the mock dataset by keywords, size, and price; the top match it returns then triggers `suggest_outfit`, which styles that item against the user's wardrobe; and that styling suggestion triggers `create_fit_card`, which writes a shareable caption. If `search_listings` finds nothing, the agent stops there and tells the user what to loosen (price, size, or keywords) instead of calling the later tools with empty input; if the wardrobe is empty, `suggest_outfit` falls back to general styling advice; and if the outfit text is missing, `create_fit_card` returns a clear message rather than crashing.

---

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse + Search:**
The agent parses the query into `description="vintage graphic tee"`, `size=None` (none stated), and `max_price=30.0`. It calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. The dataset is filtered to items priced ≤ $30, then scored on keyword overlap with the description against each listing's title, description, and style_tags. Matches like `lst_002` (Y2K Baby Tee, $18) and `lst_006` (Graphic Tee bootleg, $24) score highest and are returned sorted by relevance. The agent stores the list in `session["search_results"]` and selects the top result into `session["selected_item"]`.

**Step 2 — Suggest outfit:**
With results in hand, the agent calls `suggest_outfit(new_item=<top result>, wardrobe=<example wardrobe>)`. Because the wardrobe is non-empty, the tool feeds the item plus named wardrobe pieces (baggy straight-leg jeans, chunky white sneakers, vintage black denim jacket, etc.) to the LLM and gets back a concrete styling suggestion, e.g. "Tuck the front of the tee into your baggy straight-leg jeans, throw the black denim jacket over it, and finish with the chunky white sneakers." Stored in `session["outfit_suggestion"]`.

**Step 3 — Create fit card:**
The agent calls `create_fit_card(outfit=<suggestion>, new_item=<top result>)`. Using a higher temperature so output varies, the LLM writes a short caption that names the item, price, and platform once each in a casual OOTD voice. Stored in `session["fit_card"]`.

**Final output to user:**
The user sees three panels — the top listing found (title, price, platform, condition), the outfit idea, and the shareable fit card — all derived from the single original query without re-entering the item.

**Error path:** If the query were "designer ballgown size XXS under $5", `search_listings` returns an empty list. The agent sets `session["error"]` to a helpful message ("No matches under $5 in size XXS — try raising the price or dropping the size filter") and returns immediately, never calling `suggest_outfit` or `create_fit_card`.

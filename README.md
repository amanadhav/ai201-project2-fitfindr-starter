# FitFindr 🛍️

FitFindr is a multi-tool AI agent for secondhand shopping. You describe what
you're after in plain language ("vintage graphic tee under $30") and the agent
searches a mock listings dataset, styles the best match against your wardrobe,
and writes a shareable caption for the find — deciding at each step whether it
even makes sense to continue.

The point of the project isn't the three tools on their own; it's the **planning
loop** that orchestrates them and the **error handling** that keeps the agent
useful when a step returns nothing.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the repo root (it's gitignored — never commit it):

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com). The two
LLM-backed tools use Groq's `llama-3.3-70b-versatile`.

### Run it

```bash
python app.py          # Gradio UI at http://127.0.0.1:7860
python agent.py        # CLI: happy path + no-results path
python demo_failures.py  # triggers all 3 failure modes (handy for the demo video)
python demo_stretch.py   # shows the 4 bonus stretch features end-to-end
python -m pytest tests/  # 19 unit tests (run without a key — they exercise fallbacks)
```

> If the terminal shows a different port than 7860, use the one it prints.

---

## Stretch Features (Bonus)

All four optional stretch features are implemented. Each was spec'd in
[`planning.md`](planning.md) before building.

### Price Comparison Tool (`estimate_price_fairness`)
`estimate_price_fairness(item, listings=None) -> dict`. Compares the selected
item's price against **comparable listings in the same category** — preferring
comps that also share a style tag (closer matches), and falling back to all
same-category listings if there are fewer than two tag-sharing comps. The
verdict is relative to the comps' average price: `good_deal` (≤ 85% of avg),
`overpriced` (≥ 115%), else `fair`. Returns the verdict, the item price, the
comparable average, the comp count, and a plain-language message. With fewer
than two comps it returns `fair` with a note rather than dividing by zero.
*Example:* "At $18, this is a good deal — about 18% below the $22 average for 14
comparable tops listings."

### Trend Awareness Tool (`get_trending_styles`)
`get_trending_styles(size=None, top_n=5, listings=None) -> dict`. **Data source:**
`data/listings.json`, which represents current live secondhand listings on
depop/poshmark/thredUp; since the starter kit ships no live platform API, the
trend signal is the **frequency of each `style_tag` among active listings**,
optionally narrowed to the user's size. The planning loop passes the top
trending tags into `suggest_outfit`, which is instructed to lean into any that
match the item — so the trend **visibly changes the suggestion** (e.g. "...
especially since vintage and cottagecore styles are trending right now"). If no
listings match the size, it falls back to overall trends and says so.

### Style Profile Memory (`utils/style_profile.py`)
Persists preferences across sessions to `data/style_profile.json` (counts only,
no PII; gitignored). After a successful interaction, `update_profile()`
increments counts for the selected item's `style_tags`/size; the next session
(`run_agent(..., use_memory=True)`) reads `top_styles()` and passes them into
`suggest_outfit` so a returning user's advice tilts toward their taste **without
re-describing it**. A missing or corrupt file yields a fresh empty profile, so a
new user behaves exactly like the no-memory path. *Verified:* Session A learned
grunge/vintage/flannel from a pick; Session B applied them to a new query with
no re-entry.

### Retry Logic with Fallback (in the planning loop)
When `search_listings` returns `[]` **and** a size filter was applied, the loop
automatically retries once with `size=None`, records the change in
`session["adjustments"]`, and continues normally — telling the user what was
adjusted ("No matches in size XXS, so I dropped the size filter and searched all
sizes"). Only if the retry also returns empty does it set `session["error"]`.

Run `python demo_stretch.py` to see all four in action.

---

## How It Works (high level)

```
User query + wardrobe choice
        │
        ▼
   PLANNING LOOP (agent.run_agent)
        │  parse query → {description, size, max_price}
        ▼
   search_listings(description, size, max_price)
        │
        ├── results == []  ──►  set session["error"], RETURN EARLY
        │                       (suggest_outfit / create_fit_card never run)
        │
        └── results == [...] ─► session["selected_item"] = results[0]
                │
                ▼
        suggest_outfit(selected_item, wardrobe)   ─► session["outfit_suggestion"]
                │
                ▼
        create_fit_card(outfit_suggestion, selected_item) ─► session["fit_card"]
                │
                ▼
        return session  ─►  UI panels: listing · outfit · fit card
```

The whole interaction is driven by a single `session` dict that every step reads
from and writes to. See the diagram and full spec in
[`planning.md`](planning.md).

---

## Tool Inventory

### 1. `search_listings(description, size, max_price) -> list[dict]`
**Purpose:** Find listings in the mock dataset that match the user's request.
Pure and deterministic — no LLM call, so it's fast and easy to test.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `description` | `str` | Free-text keywords, e.g. `"vintage graphic tee"`. Tokenized and matched against each listing's title, description, and style_tags. |
| `size` | `str \| None` | Size filter, e.g. `"M"`. Case-insensitive substring match (so `"M"` matches `"S/M"`). `None` skips it. |
| `max_price` | `float \| None` | Inclusive price ceiling. `None` skips it. |

**Returns:** A `list[dict]` of full listing records (`id`, `title`,
`description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`,
`brand`, `platform`), sorted by keyword-overlap relevance, best match first.
Listings scoring 0 on keywords are dropped. Returns `[]` when nothing matches —
**never raises.**

### 2. `suggest_outfit(new_item, wardrobe) -> str`
**Purpose:** Style the found item against the user's existing closet.
Calls the LLM at temperature 0.7.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `new_item` | `dict` | A listing dict (normally the top search result). |
| `wardrobe` | `dict` | `{"items": [...]}` where each item has `name`, `category`, `colors`, `style_tags`, optional `notes`. May be empty. |

**Returns:** A non-empty `str` with 1–2 outfit ideas. With a real wardrobe it
names specific pieces ("your baggy straight-leg jeans + chunky white sneakers")
plus a styling tip; with an empty wardrobe it gives general styling advice.

### 3. `create_fit_card(outfit, new_item) -> str`
**Purpose:** Turn the outfit into a casual, shareable OOTD caption.
Calls the LLM at temperature 1.0 so repeat runs vary.

| Parameter | Type | Meaning |
|-----------|------|---------|
| `outfit` | `str` | The suggestion text from `suggest_outfit()`. |
| `new_item` | `dict` | The listing dict, used to mention title/price/platform once each. |

**Returns:** A 2–4 sentence `str` in a casual first-person voice. Different
inputs (and repeat runs) produce different captions.

---

## The Planning Loop — What Decisions the Agent Makes

`run_agent(query, wardrobe)` in `agent.py` is the orchestrator. It is a **planning
loop, not a fixed pipeline**: which tools run depends on what each step returns.

1. **Initialize** a `session` dict — the single source of truth for the run.
2. **Parse** the query with `_parse_query()` (regex, deterministic): pull
   `max_price` ("under $30", "$40"), `size` ("size M", standalone S/M/L/XL),
   and a cleaned `description` with those phrases stripped so they don't pollute
   keyword matching.
3. **Search**, then **branch on the result** — this is the decision point:
   - **Empty results** → build a *specific* error message (naming exactly which
     filters to loosen, based on which were actually applied), store it in
     `session["error"]`, and **return early.** The agent does **not** call
     `suggest_outfit` or `create_fit_card` with empty input.
   - **Non-empty results** → set `session["selected_item"] = results[0]` (top
     ranked) and continue.
4. **Suggest** an outfit from the selected item + wardrobe.
5. **Fit card** from the outfit + selected item.
6. **Return** the session. The caller checks `session["error"]` first; if it's
   `None`, all three output fields are populated.

Because of step 3, the agent behaves differently on different inputs:
an impossible query stops after the search with only an error; a normal query
runs the full three-tool chain.

---

## State Management

A single `session` dict (built by `_new_session()`) is threaded through every
step. The user types the query **once** — nothing is re-entered between tools.

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | init | parse step |
| `parsed` (`description`, `size`, `max_price`) | parse step | `search_listings` |
| `search_results` | `search_listings` | selection step |
| `selected_item` | selection (`results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | init (from UI choice) | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | returned to UI |
| `error` | any step that fails early | checked first by caller |

I verified state passing **by object identity**, not just by value: a test spy
confirmed the exact `selected_item` dict produced by the search is the same
object passed into both `suggest_outfit` and `create_fit_card`, and that the
`outfit_suggestion` string is the same object fed into `create_fit_card`. No
re-prompting, no hardcoded hand-offs.

---

## Error Handling (per tool)

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No listings match | Returns `[]` (never raises). The loop turns that into a specific, actionable error and stops before the LLM tools. |
| `suggest_outfit` | Wardrobe is empty | Detects `wardrobe["items"] == []` and returns **general** styling advice instead of naming pieces it doesn't have. |
| `suggest_outfit` | LLM / network / missing-key error | `try/except` returns a non-empty fallback built from the item's own style tags. |
| `create_fit_card` | Outfit string empty/whitespace | Returns `"Can't write a fit card yet — no outfit suggestion was generated."` |
| `create_fit_card` | LLM / network error | Returns a templated caption (`thrifted this {title} for ${price} off {platform} ✨`). |

### Concrete examples from testing (Milestone 5)

**No results → actionable error (full agent):**
```
$ python agent.py
=== No-results path ===
Error message: No listings matched 'designer ballgown' under $5 in size XXS.
Try raising your price, removing the size filter, using broader keywords.
```
`session["selected_item"]`, `session["outfit_suggestion"]`, and
`session["fit_card"]` all stayed `None`, and a spy confirmed `suggest_outfit`
and `create_fit_card` were **never called**.

**Empty wardrobe → general advice (not a crash):**
```
$ python -c "from tools import search_listings, suggest_outfit; from utils.data_loader import get_empty_wardrobe; r = search_listings('vintage graphic tee', None, 50); print(suggest_outfit(r[0], get_empty_wardrobe()))"
This adorable Y2K baby tee is perfect for ... try layering a cardigan or denim
jacket over the tee to add a cozy touch and create a cute, cottagecore look.
```

**Empty outfit → descriptive message (not an exception):**
```
$ python -c "from tools import search_listings, create_fit_card; r = search_listings('vintage graphic tee', None, 50); print(create_fit_card('', r[0]))"
Can't write a fit card yet — no outfit suggestion was generated.
```

All five failure modes are also locked in by `tests/test_tools.py` (including
monkeypatched API-outage tests for the two LLM tools).

---

## Testing

```bash
python -m pytest tests/ -v
```

`tests/test_tools.py` has 19 tests covering each tool's happy path **and** each
failure mode, plus the four stretch tools. The LLM tools are tested without a
live key by monkeypatching the Groq client, so the suite always runs green in CI.

---

## How I Used AI Tools

I planned everything in `planning.md` first, then used AI (Claude, inside the
Kiro IDE) to implement against that spec — reviewing and correcting the output
before trusting it.

**Instance 1 — `search_listings`.** I gave the AI the Tool 1 block from
`planning.md` (the three parameters, the ranked-`list[dict]` return shape, and
the empty-list failure mode) plus the listing field list, and asked it to
implement the function using `load_listings()`. What I changed before accepting:
the first version did naive substring matching on the raw description, which let
filler words ("looking", "for", "size") create false matches. I added a
`_tokenize()` helper with a stopword list and switched scoring to token overlap
across title + description + style_tags, then verified ranking against three
queries (graphic tee, track jacket size M, impossible ballgown).

**Instance 2 — the planning loop in `run_agent()`.** I gave the AI the Planning
Loop, State Management, and Architecture (ASCII diagram) sections together, plus
the `_new_session()` stub. What I overrode: the generated version produced a
generic `"No results found"` string and — in one draft — still fell through to
`suggest_outfit`. I rewrote the empty-results branch to (a) `return` immediately
so the downstream tools can't run, and (b) build the error message dynamically
from which filters were actually applied ("raising your price" only appears if a
price was set). I confirmed the branch with an object-identity spy test showing
the LLM tools are never called on the no-results path.

---

## Spec Reflection

What matched my `planning.md` spec: the session-dict state model, the
early-return branch on empty search results, and the per-tool failure modes all
shipped as designed.

What I refined while building:
- **Query parsing** was hand-waved in the spec ("regex or LLM"). In practice I
  needed explicit cleanup so price/size phrases don't leak into the keyword
  description — otherwise `"under"` and `"size"` skew relevance scoring.
- **Search relevance** needed tokenization + stopwords to avoid junk matches;
  the spec just said "keyword overlap."
- The **top result isn't always what I predicted** in the walkthrough — the Y2K
  Baby Tee outranks the bootleg tee for "vintage graphic tee" because it hits
  more keyword tokens. That's the scoring working correctly, and a good reminder
  that the agent's behavior is driven by data, not by my assumptions.

---

## Project Layout

```
ai201-project2-fitfindr-starter/
├── agent.py            # planning loop + query parser + session state + stretches
├── app.py              # Gradio UI (handle_query maps session → 3 panels)
├── tools.py            # 3 required tools + 2 stretch tools (price, trends)
├── data/               # mock listings + wardrobe schema
├── utils/
│   ├── data_loader.py
│   └── style_profile.py  # stretch: cross-session style memory
├── tests/test_tools.py # 19 tests, one+ per failure mode + stretch coverage
├── demo_failures.py    # triggers all 3 failure modes (for the demo video)
├── demo_stretch.py     # shows the 4 stretch features end-to-end
├── planning.md         # full spec, diagram, AI plan, walkthrough, stretch specs
└── requirements.txt
```

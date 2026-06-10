# Research: Community Insights UI Improvements

**Feature**: `009a-community-insights-ui`
**Date**: 2026-06-09
**Parent spec**: [009-community-insight-restructure](../009-community-insight-restructure/spec.md)

---

## Bug 1: Source URL renders as raw HTML text

### Observed behaviour

In the Community Insights page the source link appears as a literal string
`<a class="source-link" href="..." target="_blank">↗ Source</a>` displayed as
plain text beneath the insight card, not as a rendered hyperlink.

### Root cause

`05_community.py` builds `source_html` as a Python f-string then embeds it
inside a larger `st.markdown(f"""<div>…{source_html}…</div>""", unsafe_allow_html=True)`.

Streamlit's `st.markdown` passes the entire string through its **Markdown →
HTML pipeline first**, then applies `unsafe_allow_html=True` to render the
result. If the user-supplied `statement` or `solution` text embedded in the
same f-string contains Markdown-special characters (`*`, `_`, backticks, or
HTML-like angle brackets), the Markdown parser transforms that text and in
doing so can close or corrupt the enclosing `<div>` tags prematurely. Once the
`<div class="insight-footer">` is closed early, anything that follows it —
including `{source_html}` — falls outside the rendered HTML tree and is
displayed as escaped text.

The two concrete triggers found in production data:
- `@JsonFormat(shape=JsonFormat.Shape.NUMBER)` — the `@` and parentheses in
  the solution text are benign alone, but combined with other Markdown
  constructs they can confuse the parser.
- Multi-paragraph solution text split by blank lines — Markdown treats each
  paragraph block separately, which can break the assumed single-div context.

### Fix decision

Apply `html.escape()` from the Python standard library to all user-supplied
text fields (statement, solution) before embedding them in the HTML template.
`html.escape()` converts `&`, `<`, `>`, `"`, `'` to their HTML entity
equivalents, preventing the Markdown parser from interpreting the content as
markup and preserving the `<div>` structure that surrounds `source_html`.

The `source_html` string itself is **not** escaped — it is constructed by our
code from a validated URL, not from arbitrary user input.

`html.escape()` is in the Python standard library; no new dependency is added.

---

## Bug 2: Vote button animation state is invisible

### Observed behaviour

Clicking the ▲ vote button appears to do nothing or triggers an immediate
re-run with no visible intermediate animated state (`voting-btn` CSS class with
`vote-flash` keyframe).

### Root cause

The session-state flag pattern in the current code is correct in structure but
the intermediate render (where the `voting-btn` div should be visible) is
imperceptibly short because:

1. The `voting-btn` keyframe (`vote-flash 0.6s ease`) is CSS-side and _would_
   animate if the div was present long enough. The div IS rendered — but the
   `call_tool(vote_insight, …)` call completes in < 50 ms for a local or
   LAN-connected Neo4j, then `del` + `st.rerun()` fires immediately. The
   animation never reaches the 50% keyframe before the page re-runs.
2. `st.write("")` in `col_vote` before the vote button/div adds a vertical
   spacer that is only rendered in the button state. When showing the
   `voting-btn` div, the spacer is absent, causing a layout jump that also
   makes the animation harder to perceive.

### Fix decision

Replace the `vote-flash` keyframe with a persistent accent-coloured div (no
animation) that is visually distinct from the normal button state. A static
visual change during the loading render is sufficient signal — the Streamlit
re-run cycle is the progress indicator. Remove the `st.write("")` spacer and
align the loading div and button consistently using `margin-top` CSS so the
layout does not shift between states.

---

## Bug 3: Only Spring Boot insights are displayed

### Observed behaviour

The community page always shows Spring Boot insights regardless of which
framework's insights a developer needs. The UI provides no way to switch
frameworks.

### Root cause

`call_tool(get_community_insights)` is called with no arguments, falling back to
`framework="Spring Boot"` (the default defined in the MCP tool). The page has
no UI control for framework selection.

### Fix decision

Add a framework selector using the existing `framework_selectbox` helper (from
`_helpers.py`) with `include_all=False`. Wrap it in a top-of-page controls
row alongside the search bar. The selected framework's display name
(`FRAMEWORK_DISPLAY_NAMES[cli_key]`) is passed to `get_community_insights`.

Since insights are re-fetched on every Streamlit re-run (no `st.cache_data`
on the `call_tool` path), changing the selectbox triggers an automatic
re-fetch — no additional event-handling logic needed.

---

## Feature: Search Bar

### Requirement

A text input that lets developers narrow displayed insights by keyword, without
leaving the page or waiting for a server round-trip.

### Approach: client-side Python filtering

After fetching all insights for the selected framework, apply a
case-insensitive Python `in` check against each insight's `statement` and
`solution` fields:

```python
q = search_term.strip().lower()
if q:
    insights = [
        i for i in insights
        if q in i.get("statement", "").lower()
        or q in i.get("solution", "").lower()
    ]
```

**Why client-side rather than server-side (passing `entity_name` to the MCP
tool)**:

- `get_community_insights` accepts `entity_name` for filtering by affected
  entity nodes (`AFFECTS_CLASS`, `AFFECTS_PROPERTY`, `AFFECTS_DEPENDENCY`).
  This is a _graph relationship_ filter, not a full-text content search. It
  would miss insights whose statement text mentions a class name without that
  class being stored as a graph entity.
- Client-side filtering is instantaneous (no Neo4j round-trip) once insights
  are loaded, matching the expected UX of a search bar.
- Community insights lists are small (typically < 200 items per framework);
  loading all and filtering in Python is not a performance concern.

### UI placement

The search bar and framework selectbox are placed in a two-column header row
directly below the page title: `col_search, col_fw = st.columns([3, 2])`.
The "— N insights" count line updates to reflect the filtered count and the
active framework name.

---

## Feature: Framework & Version Badge on Insight Cards

### Requirement

Each insight card should show which framework and version it applies to, since
the page now shows insights across frameworks and the filter context can change.

### Approach

The `get_community_insights` response already returns a `version` field on each
insight (the `v.version` Cypher projection). The `framework` field is not
currently returned per insight but is known from the page-level selector. Render
two metadata chips in the `insight-footer`:

```html
<span class="fw-badge">{framework_display}</span>
<span class="ver-badge">v{version}</span>
```

`fw-badge` uses `--info-dim` / `--info` colour tokens (blue, informational).
`ver-badge` uses `--bg-surface` / `--muted` (neutral, de-emphasised) since the
version is a structural fact rather than a status signal.

---

## Feature: Submit Form — Framework-Agnostic Labels

### Current issue

The submit form inside the `＋ Submit New Insight` expander has the label
"Spring Boot version" which is incorrect when submitting insights for other
frameworks (WildFly, Angular, etc.).

### Fix

Rename the label to "Framework version" and update the placeholder to
`"e.g. 3.2 for Spring Boot, 30 for WildFly"`. The underlying `spring_boot_version`
parameter name on the MCP tool is preserved (unchanged by spec 009); only the
UI label changes.

---

## Streamlit Re-run Architecture Notes

The Community page uses Streamlit's default re-run model. Every widget
interaction triggers a full Python re-run. The framework selectbox change
triggers a re-run which calls `get_community_insights(framework=fw_display)` —
this re-fetches insights for the newly selected framework automatically.

The search bar uses `st.text_input` with `key="community_search"`. As the user
types, each keystroke triggers a re-run. Client-side filtering (pure Python
over the in-memory list) makes this instantaneous. No debounce, no `on_change`
callback, no `st.form` wrapper is needed.

The skeleton loader (`skel = st.empty()`) should only show during the initial
load and framework switches (when the MCP call fires), not during search text
typing. This is handled correctly by the existing skeleton pattern: the skeleton
renders before `call_tool(get_community_insights, …)` and is cleared after. A
search keystroke only re-runs the filtering logic, not the MCP call, but in
Streamlit's current execution model the whole script re-runs including the
`call_tool`. The skeleton will flash briefly on each keystroke. This is
acceptable given the fast local call time; no structural change is needed to
address it. If the skeleton flash is undesirable in future, `st.cache_data`
with a `framework` cache key can be introduced in a later spec.

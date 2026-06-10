# Feature Specification: Community Insights UI Improvements

**Feature Branch**: `009-community-insight-restructure`
**Spec ID**: `009a`
**Created**: 2026-06-09
**Status**: Draft
**Research**: See [research.md](research.md) for bug root-cause analysis and feature approach decisions.

---

## Overview

This spec covers three bug fixes and three UI enhancements to the Community
Insights Streamlit page (`05_community.py`). No changes are made to MCP tools,
query layers, or shared helpers.

### Bugs fixed

| # | Symptom | Root cause |
|---|---------|------------|
| B1 | Source URL renders as raw HTML text | User-supplied content not HTML-escaped; Markdown parser corrupts surrounding `<div>` |
| B2 | Vote button animation invisible / layout shifts | `vote-flash` animation completes before rerun; `st.write("")` spacer causes layout jump |
| B3 | Only Spring Boot insights shown | `get_community_insights` called with no `framework` argument |

### Features added

| # | Feature |
|---|---------|
| F1 | Framework selectbox — choose which framework's insights to display |
| F2 | Search bar — client-side keyword filter on statement and solution fields |
| F3 | Framework + version badges on each insight card |
| F4 | Submit form label fix — "Spring Boot version" → "Framework version" |

---

## File: `migration_oracle/streamlit_app/pages/05_community.py`

### Step 1 — Add standard library import

At the top of the file, after existing imports, add:

```python
import html as _html
```

This is the Python standard library `html` module providing `_html.escape()`.
The alias `_html` avoids shadowing any local variable named `html`.

---

### Step 2 — Add new CSS rules to the existing `<style>` block

Append the following rules **inside** the existing `st.markdown("""<style>…</style>""", …)` block, after the `.source-link:hover` rule:

```css
/* Controls row (search + framework selector) */
.controls-row {
    display: flex;
    align-items: flex-end;
    gap: 10px;
    margin-bottom: 1rem;
}

/* Framework badge on each card */
.fw-badge {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--info);
    background: var(--info-dim);
    border: 1px solid var(--info);
    border-radius: 5px;
    padding: 2px 7px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* Version badge on each card */
.ver-badge {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--muted);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 5px;
    padding: 2px 7px;
}

/* Vote loading div — static accent state during API call */
.voting-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent-dim);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    color: var(--accent);
    font-size: 13px;
    font-family: var(--font-ui);
    cursor: not-allowed;
    width: 100%;
    min-height: 38px;
    margin-top: 28px;
}
```

Remove the following CSS that is no longer used:

```css
/* vote button pulsing state */
@keyframes vote-flash {
    0%   { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
    50%  { background:var(--accent);     border-color:var(--accent); color:var(--accent-text); }
    100% { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
}
.voting-btn {
    animation: vote-flash 0.6s ease;
    border-radius: var(--radius);
    border: 1px solid var(--accent);
    padding: 4px 10px;
    font-size: 13px;
    font-family: var(--font-ui);
    cursor: not-allowed;
    width: 100%;
}
```

---

### Step 3 — Add framework selectbox and search bar above the insight list

Replace the skeleton + `call_tool` block:

**Before**:
```python
skel = st.empty()
skel.markdown(
    "".join(['<div class="skeleton-card"></div>'] * 3),
    unsafe_allow_html=True,
)
result = call_tool(get_community_insights)
skel.empty()
```

**After**:
```python
col_search, col_fw = st.columns([3, 2], gap="small")
with col_fw:
    cli_key = framework_selectbox("Framework", key="ci_fw_filter")
    fw_display = FRAMEWORK_DISPLAY_NAMES[cli_key]
with col_search:
    search_term = st.text_input(
        "Search insights",
        placeholder="Filter by keyword…",
        key="community_search",
        label_visibility="visible",
    )

skel = st.empty()
skel.markdown(
    "".join(['<div class="skeleton-card"></div>'] * 3),
    unsafe_allow_html=True,
)
result = call_tool(get_community_insights, framework=fw_display)
skel.empty()
```

Notes:
- `framework_selectbox` is already imported from `_helpers.py`.
- `FRAMEWORK_DISPLAY_NAMES` is already imported from `_constants.py`.
- `cli_key` defaults to `"spring-boot"` on first load (index 0), preserving existing default behaviour.
- Placing `col_fw` before `col_search` in the column loop ensures the framework selectbox renders first in DOM order even though its column is on the right visually — this matches the Streamlit column API: `col_search, col_fw = st.columns([3, 2])` but widgets are placed by entering the `with col_*` context, not by declaration order.

---

### Step 4 — Apply client-side search filter

Immediately after `insights = result.get("insights", []) if result else []`, add:

```python
q = search_term.strip().lower()
if q:
    insights = [
        i for i in insights
        if q in i.get("statement", "").lower()
        or q in i.get("solution", "").lower()
    ]
```

---

### Step 5 — Update the insight count header

Replace:
```python
st.markdown(f"""
<div style="font-family:var(--font-mono);font-size:11.5px;color:var(--muted);
            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">
  — {len(insights)} insight{"s" if len(insights)!=1 else ""}
</div>
""", unsafe_allow_html=True)
```

With:
```python
filter_label = f'"{search_term.strip()}" · ' if search_term.strip() else ""
st.markdown(f"""
<div style="font-family:var(--font-mono);font-size:11.5px;color:var(--muted);
            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">
  — {len(insights)} insight{"s" if len(insights)!=1 else ""}
  {f'· {_html.escape(filter_label)}' if filter_label else ""}
  · {_html.escape(fw_display)}
</div>
""", unsafe_allow_html=True)
```

---

### Step 6 — Fix HTML escaping and add framework/version badges to the insight card

Replace the entire card rendering block inside `with col_card:`:

**Before**:
```python
with col_card:
    st.markdown(f"""
<div class="{card_class}">
  <div class="insight-statement">{insight.get('statement', '')}</div>
  <div class="insight-solution">{insight.get('solution', '')}</div>
  <div class="insight-footer">
    <span class="vote-badge">▲ {insight.get('votes', 0)}</span>
    {verified_html}
    {source_html}
  </div>
</div>
""", unsafe_allow_html=True)
```

**After**:
```python
with col_card:
    stmt   = _html.escape(insight.get("statement", ""))
    soln   = _html.escape(insight.get("solution",  ""))
    ver    = _html.escape(insight.get("version",   ""))
    st.markdown(f"""
<div class="{card_class}">
  <div class="insight-statement">{stmt}</div>
  <div class="insight-solution">{soln}</div>
  <div class="insight-footer">
    <span class="vote-badge">▲ {insight.get('votes', 0)}</span>
    {verified_html}
    <span class="fw-badge">{_html.escape(fw_display)}</span>
    {f'<span class="ver-badge">v{ver}</span>' if ver else ""}
    {source_html}
  </div>
</div>
""", unsafe_allow_html=True)
```

Note: `source_html` is constructed from the URL value returned by the tool layer
(`r.sourceUrl` in the Cypher). It is not arbitrary user HTML; escaping is not
applied to it. The `href` attribute value originates from `evidence_url`
submitted via the form and stored verbatim in the graph — the URL is trusted at
this rendering stage.

---

### Step 7 — Fix vote button column rendering (remove spacer, replace animation)

Replace the entire `with col_vote:` block:

**Before**:
```python
with col_vote:
    st.write("")
    if st.session_state.get(voting_key):
        st.markdown('<div class="voting-btn">▲</div>', unsafe_allow_html=True)
        call_tool(vote_insight, insight_id=insight_id, delta=1)
        del st.session_state[voting_key]
        st.rerun()
    elif st.button("▲", key=f"vote_{insight_id}", help="Vote up this insight"):
        st.session_state[voting_key] = True
        st.rerun()
```

**After**:
```python
with col_vote:
    if st.session_state.get(voting_key):
        st.markdown('<div class="voting-loading">▲</div>', unsafe_allow_html=True)
        call_tool(vote_insight, insight_id=insight_id, delta=1)
        del st.session_state[voting_key]
        st.rerun()
    else:
        st.button("▲", key=f"vote_{insight_id}", help="Vote up this insight",
                  on_click=lambda _k=voting_key: st.session_state.update({_k: True}))
```

Changes:
- Remove `st.write("")` spacer — the `margin-top: 28px` on `.voting-loading`
  provides equivalent vertical alignment without a blank element.
- Replace `voting-btn` (which used the removed `vote-flash` keyframe) with
  `voting-loading` (static accent colour).
- Replace the `elif st.button(…):` + `st.session_state[key] = True; st.rerun()`
  pattern with `on_click=` callback. This sets the session state flag and
  triggers a re-run in a single Streamlit cycle rather than two, so the loading
  state is displayed and the API call fires in the same render pass.

---

### Step 8 — Update the submit form label

Inside `with st.form("submit_insight_form"):`, change:

```python
spring_boot_version = st.text_input("Spring Boot version", placeholder="e.g. 3.2.0")
```

To:

```python
spring_boot_version = st.text_input(
    "Framework version",
    placeholder="e.g. 3.2 for Spring Boot, 30 for WildFly",
)
```

No other change to the submit form is required. The variable name
`spring_boot_version` is preserved since it maps to the `spring_boot_version`
parameter on the `submit_migration_insight` tool (whose signature is frozen by
spec 009 FR-014).

---

### Step 9 — Remove the `cli_key` / `fw_display` variable shadowing

The submit form currently declares its own `cli_key = framework_selectbox("Framework", key="ci_fw")`.
After Step 3 introduces a page-level `cli_key` with `key="ci_fw_filter"`, the
submit form must use a distinct key. Change the form's selectbox call to:

```python
submit_cli_key    = framework_selectbox("Framework", key="ci_fw_submit")
submit_fw_display = FRAMEWORK_DISPLAY_NAMES[submit_cli_key]
```

And update the `call_tool(submit_migration_insight, …, framework=…)` line to
use `submit_fw_display` instead of `fw_display`.

---

## What Is Not Changed

- `migration_oracle/mcp/tools/community.py` — no changes; all tool signatures,
  parameters, and response shapes are unchanged.
- `migration_oracle/mcp/graph/queries/community.py` — no changes.
- `migration_oracle/streamlit_app/_helpers.py` — no changes; `framework_selectbox`
  is used as-is.
- `migration_oracle/streamlit_app/_constants.py` — no changes.
- All other Streamlit pages — no changes.
- No new Python packages — `html` is in the standard library.

---

## Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-001 | Source link renders as a clickable hyperlink, not as raw HTML text, for all insights that have a non-empty `source_url` value. |
| AC-002 | Source link does not appear at all for insights with an empty or null `source_url`. |
| AC-003 | Insight cards with statement or solution text containing `<`, `>`, `&`, `"`, or `'` characters render those characters literally (not as HTML tags). |
| AC-004 | Clicking the ▲ vote button shows the accent-coloured loading div and increments the vote count after rerun. |
| AC-005 | The page renders insights for any framework selectable via the framework dropdown, not only Spring Boot. |
| AC-006 | Typing in the search bar filters the displayed insights to those whose statement or solution contains the search term (case-insensitive). The count header reflects the filtered count. |
| AC-007 | Each insight card displays a framework badge and a version badge in the footer. |
| AC-008 | Clearing the search bar returns all insights for the selected framework. |
| AC-009 | The submit form shows the label "Framework version" and a multi-framework-aware placeholder. |
| AC-010 | Submitting an insight via the form (with framework selectbox and version field) succeeds and shows the success banner. |
| AC-011 | The page layout does not shift when toggling between the vote button and the vote-loading div. |

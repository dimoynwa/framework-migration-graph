# Feature Specification: Streamlit UI Redesign

**Feature Branch**: `006a-streamlit-ui-redesign`
**Created**: 2026-06-07
**Status**: Draft
**Research**: See [research.md](research.md) for the full three-approach comparison and MCP best-practice analysis.

---

# Migration Oracle — UI Redesign Specification

## Overview

This document is the complete implementation spec for the Migration Oracle Streamlit UI redesign. It lists every CSS rule, every HTML component, and every layout change applied to each file, in the exact order they appear in the code. A developer with the original app files and this document should be able to reproduce the redesign from scratch.

---

## Problem Statement

The original app had no visual design. All pages used Streamlit's default white theme with no custom CSS, no layout structure, and no visual hierarchy. Specific problems:

- All pages looked identical — plain white backgrounds, default gray widgets, no branding
- No way to tell which page you were on or what the app's state was
- Data-dense pages (Context Dashboard) displayed steps as raw columns of unformatted text
- Status values (`mechanical`, `substantial`, `high`) were plain strings — no color, no badge
- The sidebar was a single unstyled title
- Form inputs had no focus states; keyboard navigation felt broken
- Metric numbers had no visual weight and were easy to miss
- Buttons gave no feedback when clicked — the app froze silently until Streamlit re-ran
- The tool felt like a prototype rather than a production internal tool

---

## Global Design Tokens

Defined once in `app.py` as CSS custom properties on `:root`. Every page file inherits these without redeclaring them.

### Color tokens

| Token | Value | Purpose |
|---|---|---|
| `--bg` | `#0d0f14` | Page background (slightly blue-shifted near-black) |
| `--bg-surface` | `#13161e` | Sidebar, secondary surfaces |
| `--bg-card` | `#181c26` | Cards, form fields, all container backgrounds |
| `--bg-hover` | `#1e2330` | Hover state background for interactive elements |
| `--border` | `#252a38` | Default border on all components |
| `--border-bright` | `#2e3547` | Emphasized border on hover and focus |
| `--accent` | `#4ade9e` | Primary action color — buttons, links, metric values, active states |
| `--accent-dim` | `#1a4a35` | Accent-tinted background — active nav, skeleton shimmer base, loader bg |
| `--accent-text` | `#0d2b1f` | Text placed on top of `--accent` fill |
| `--warning` | `#f5a623` | Substantial effort, caution states |
| `--warning-dim` | `#3a2800` | Warning pill background |
| `--danger` | `#f87171` | High severity, errors |
| `--danger-dim` | `#3b0f0f` | Danger pill background |
| `--info` | `#60a5fa` | Mechanical effort, informational states |
| `--info-dim` | `#0f2444` | Info pill background |
| `--muted` | `#5a6278` | De-emphasized text, section labels, inactive dots |
| `--text` | `#e8eaf0` | Primary text |
| `--text-secondary` | `#9aa0b8` | Labels, captions, secondary content |

### Radius tokens

| Token | Value | Usage |
|---|---|---|
| `--radius` | `10px` | Buttons, inputs, alerts, expanders, small components |
| `--radius-lg` | `14px` | Cards, step cards, insight cards, metric blocks |

### Font tokens

| Token | Value | Usage |
|---|---|---|
| `--font-ui` | `'DM Sans', sans-serif` | All body text, button labels, form prose |
| `--font-display` | `'Syne', sans-serif` | Page titles, sidebar brand, metric values |
| `--font-mono` | `'IBM Plex Mono', monospace` | Labels, badges, status pills, CLI output, metadata |

Fonts are loaded via:
```
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');
```

---

## Shared Keyframe Animations

These animations are defined locally per file (not globally), but they are identical wherever they appear. Any future consolidation into `app.py` could use these definitions:

### `blink` — three-dot loader pulse
Used in: `01_pipeline_trigger.py`, `04_context_dashboard.py`, `05_community.py`
```css
@keyframes blink { 0%,80%,100%{opacity:0.15} 40%{opacity:1} }
```

### `sweep` — skeleton shimmer
Used in: `03_rule_explorer.py`, `05_community.py`
```css
@keyframes sweep {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}
```

### `pulse` — status dot heartbeat
Used in: `04_context_dashboard.py`
```css
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
```

### `vote-flash` — vote confirmation pulse
Used in: `05_community.py`
```css
@keyframes vote-flash {
    0%   { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
    50%  { background:var(--accent);     border-color:var(--accent); color:var(--accent-text); }
    100% { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
}
```

---

## File: `app.py`

### Step 1 — Page config

Change `st.set_page_config` to:
```python
st.set_page_config(layout="wide", page_title="Migration Oracle", page_icon="⚗️")
```

### Step 2 — Inject global stylesheet

Add `st.markdown("""<style>...</style>""", unsafe_allow_html=True)` containing all rules below, in this order:

#### Google Fonts import
```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');
```

#### Design tokens (`:root` block)
All tokens listed in the Global Design Tokens section above.

#### Global reset
```css
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--font-ui) !important;
}
```

#### Sidebar container
```css
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * {
    color: var(--text) !important;
    font-family: var(--font-ui) !important;
}
```

#### Sidebar nav items
```css
[data-testid="stSidebarNav"] a {
    border-radius: var(--radius) !important;
    padding: 8px 12px !important;
    margin: 2px 8px !important;
    font-size: 13.5px !important;
    transition: background 0.15s ease !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: var(--bg-hover) !important;
}
[data-testid="stSidebarNav"] a[aria-selected="true"] {
    background: var(--accent-dim) !important;
    color: var(--accent) !important;
}
```

#### Headings
```css
h1 {
    font-family: var(--font-display) !important;
    font-size: 28px !important;
    font-weight: 800 !important;
    letter-spacing: -0.5px !important;
    color: var(--text) !important;
    padding-bottom: 0.25rem !important;
    border-bottom: 1px solid var(--border) !important;
    margin-bottom: 1.5rem !important;
}
h2 {
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
    font-size: 18px !important;
    color: var(--text) !important;
    letter-spacing: -0.2px !important;
}
h3 { font-size: 15px !important; font-weight: 500 !important; }
```

#### Default buttons
```css
.stButton > button {
    background: var(--bg-card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border-bright) !important;
    border-radius: var(--radius) !important;
    font-family: var(--font-ui) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 0.4rem 1rem !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background: var(--bg-hover) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    transform: translateY(-1px) !important;
}
```

#### Primary buttons and form submit buttons
```css
.stButton > button[kind="primary"],
.stFormSubmitButton > button {
    background: var(--accent) !important;
    color: var(--accent-text) !important;
    border-color: var(--accent) !important;
    font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button:hover {
    opacity: 0.88 !important;
    color: var(--accent-text) !important;
    transform: translateY(-1px) !important;
}
```

#### Inputs, textareas, selectboxes
```css
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    background: var(--bg-card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    font-family: var(--font-ui) !important;
    font-size: 13.5px !important;
    transition: border-color 0.15s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px var(--accent-dim) !important;
}
input::placeholder, textarea::placeholder {
    color: var(--muted) !important;
}
```

#### Form field labels
```css
label, .stSelectbox label, .stTextInput label, .stTextArea label {
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    font-family: var(--font-mono) !important;
}
```

#### Metric cards (`st.metric`)
```css
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1rem 1.25rem !important;
}
[data-testid="stMetricLabel"] {
    color: var(--text-secondary) !important;
    font-family: var(--font-mono) !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
[data-testid="stMetricValue"] {
    color: var(--accent) !important;
    font-family: var(--font-display) !important;
    font-size: 32px !important;
    font-weight: 700 !important;
}
```

#### Alerts (`st.info`, `st.success`, `st.error`, `st.warning`)
```css
.stAlert {
    background: var(--bg-card) !important;
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    font-size: 13.5px !important;
}
[data-testid="stAlertContentInfo"]    { border-left: 3px solid var(--info) !important; }
[data-testid="stAlertContentSuccess"] { border-left: 3px solid var(--accent) !important; }
[data-testid="stAlertContentError"]   { border-left: 3px solid var(--danger) !important; }
[data-testid="stAlertContentWarning"] { border-left: 3px solid var(--warning) !important; }
```

#### Tabs (`st.tabs`)
```css
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-secondary) !important;
    font-family: var(--font-ui) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    border-radius: var(--radius) var(--radius) 0 0 !important;
    padding: 8px 16px !important;
    border: none !important;
    transition: color 0.15s !important;
}
.stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    background: var(--accent-dim) !important;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--text) !important; }
```

#### Expanders (`st.expander`)
```css
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    color: var(--text) !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 10px 14px !important;
    transition: background 0.15s !important;
}
.streamlit-expanderHeader:hover { background: var(--bg-hover) !important; }
.streamlit-expanderContent {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-top: none !important;
    border-radius: 0 0 var(--radius) var(--radius) !important;
    padding: 1rem !important;
}
```

#### Nested container blocks
```css
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1rem 1.25rem !important;
    margin-bottom: 0.75rem !important;
}
```

#### Horizontal rule
```css
hr {
    border-color: var(--border) !important;
    margin: 1.25rem 0 !important;
}
```

#### Code blocks
```css
code, pre {
    font-family: var(--font-mono) !important;
    background: var(--bg-card) !important;
    color: var(--accent) !important;
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    font-size: 12.5px !important;
}
```

#### Selectbox dropdown popover
```css
[data-baseweb="popover"] {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-bright) !important;
    border-radius: var(--radius) !important;
}
[data-baseweb="menu"] li {
    color: var(--text) !important;
    font-size: 13.5px !important;
}
[data-baseweb="menu"] li:hover { background: var(--bg-hover) !important; }
```

#### Captions
```css
.stCaption, small, [data-testid="stCaptionContainer"] {
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    font-family: var(--font-mono) !important;
}
```

#### Checkboxes
```css
.stCheckbox label { text-transform: none !important; font-size: 13.5px !important; }
```

#### Scrollbar
```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg) }
::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 3px; }
```

#### Sidebar brand block
```css
.sidebar-brand {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: -0.3px;
    padding: 1rem 1rem 0.5rem;
    display: flex;
    align-items: center;
    gap: 8px;
}
.sidebar-brand span {
    font-size: 11px;
    font-weight: 400;
    font-family: var(--font-mono);
    color: var(--muted);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 6px;
    letter-spacing: 0.04em;
}
```

### Step 3 — Render sidebar brand

Replace `st.sidebar.title("Migration Oracle")` with:
```python
st.sidebar.markdown("""
<div class="sidebar-brand">
  ⚗️ Migration Oracle <span>v1.0</span>
</div>
""", unsafe_allow_html=True)
```

---

## File: `01_pipeline_trigger.py`

### Step 1 — Inject local stylesheet

Add at the top of the page, before any widgets:

```css
/* Page header layout */
.page-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 0.25rem;
}
.page-header .icon {
    font-size: 22px;
    background: var(--accent-dim);
    border-radius: 8px;
    padding: 6px 10px;
}

/* Active flag pills (right column) */
.flag-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12.5px;
    font-family: var(--font-mono);
    color: var(--text-secondary);
}

/* Three-dot loading animation */
@keyframes blink { 0%,80%,100%{opacity:0.15} 40%{opacity:1} }
.dots span {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    margin: 0 2px;
    animation: blink 1.2s infinite;
}
.dots span:nth-child(2) { animation-delay: 0.2s; }
.dots span:nth-child(3) { animation-delay: 0.4s; }

/* Running banner shown during subprocess */
.running-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    background: var(--accent-dim);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    padding: 9px 14px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--accent);
    margin-bottom: 1rem;
}
```

### Step 2 — Page header HTML

Replace `st.title("Pipeline Trigger")` with:
```html
<div class="page-header">
  <span class="icon">🚀</span>
  <div>
    <h1 style="border:none;margin:0;padding:0;font-size:22px;">Pipeline Trigger</h1>
    <p style="color:var(--text-secondary);font-size:12px;margin:0;font-family:var(--font-mono);">
      Kick off a framework migration pipeline run
    </p>
  </div>
</div>
<hr style="margin-bottom:1.5rem;" />
```

### Step 3 — Two-column layout

Wrap the form and info panel in `st.columns([3, 2], gap="large")`. Left column (width 3) gets the form. Right column (width 2) gets the info card and active flags.

### Step 4 — Form layout changes

Inside the form:
- `From version` and `To version` inputs: place in `st.columns(2)` side by side
- Flag checkboxes: place `--dry-run` and `--force` in the left column, `--force-extract` and `--force-llm` in the right column using `st.columns(2)`
- Submit button: `st.form_submit_button("▶ Run Pipeline", use_container_width=True)`

### Step 5 — Right column info card

After the form, in the right column render this HTML card:
```html
<div style="
  background:var(--bg-card);
  border:1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius:var(--radius);
  padding:1rem 1.25rem;
  font-size:13px;
  color:var(--text-secondary);
  line-height:1.7;
">
  Triggers the <code style='background:transparent;border:none;color:var(--accent);'>migration_oracle.cli</code>
  CLI process for the selected framework and version range.
  Output streams live below as the pipeline runs.
  <br/><br/>
  Use <b style='color:var(--text);'>--dry-run</b> to preview without persisting, and
  <b style='color:var(--text);'>--force</b> flags to re-execute specific pipeline steps.
</div>
```

### Step 6 — Active flags display

For each active flag, render:
```html
<div class="flag-pill">⚑ --flag-name</div>
```

### Step 7 — CLI command display (post-submit)

Before starting the subprocess, render the command as a styled terminal line:
```html
<div style="
  display:flex; align-items:center; gap:10px;
  background:var(--bg-card);
  border:1px solid var(--border-bright);
  border-radius:var(--radius);
  padding:10px 14px;
  margin-bottom:1rem;
  font-family:var(--font-mono);
  font-size:12px;
  color:var(--text-secondary);
">
  <span style="color:var(--accent);">$</span>
  <span>{cmd_string}</span>
</div>
```

### Step 8 — Running banner loader

After the command display, before starting the subprocess:
```python
banner = st.empty()
banner.markdown("""
<div class="running-banner">
  <div class="dots"><span></span><span></span><span></span></div>
  Pipeline running…
</div>
""", unsafe_allow_html=True)
```

After `proc.wait()`, clear the banner:
```python
banner.empty()
```

---

## File: `02_run_browser.py`

### Step 1 — Page header HTML

Replace `st.title("Run Browser")` with the standard icon-header block:
```html
<div style="display:flex;align-items:center;gap:10px;margin-bottom:0.25rem;">
  <span style="font-size:22px;background:var(--accent-dim);border-radius:8px;padding:6px 10px;">📂</span>
  <div>
    <h1 style="border:none;margin:0;padding:0;font-size:22px;">Run Browser</h1>
    <p style="color:var(--text-secondary);font-size:12px;margin:0;font-family:var(--font-mono);">
      Browse past pipeline runs and inspect artifacts
    </p>
  </div>
</div>
<hr style="margin-bottom:1.5rem;" />
```

### Step 2 — Spinner on initial load

Wrap the `call_tool(_cached_list_runs)` call:
```python
with st.spinner("Loading pipeline runs…"):
    result = call_tool(_cached_list_runs)
```

### Step 3 — Run selector label

Add a section heading before the selectbox:
```python
st.markdown("#### Select Run")
```

Hide the selectbox label:
```python
idx = st.selectbox("Pipeline run", ..., label_visibility="collapsed")
```

### Step 4 — Version badge strip

After the selectbox, render inline metadata chips:
```html
<div style="display:flex;gap:8px;flex-wrap:wrap;margin:0.75rem 0 1.25rem;">
  <span style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;
               padding:4px 10px;font-family:var(--font-mono);font-size:11.5px;color:var(--text-secondary);">
    ⚙ {framework}
  </span>
  <span style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;
               padding:4px 10px;font-family:var(--font-mono);font-size:11.5px;color:var(--text-secondary);">
    from {from_version}
  </span>
  <span style="background:var(--accent-dim);border:1px solid var(--accent);border-radius:6px;
               padding:4px 10px;font-family:var(--font-mono);font-size:11.5px;color:var(--accent);">
    → {to_version}
  </span>
</div>
```

Note: the `to_version` chip uses `--accent-dim` background and `--accent` text/border to distinguish it as the migration target.

### Step 5 — Spinners on artifact tab loads

Wrap each `call_tool(get_artifact_content, ...)` call in its own spinner:
```python
with st.spinner("Loading raw artifact…"):
    resp = call_tool(get_artifact_content, framework, from_version, to_version, "raw_md")

with st.spinner("Loading filtered artifact…"):
    resp = call_tool(get_artifact_content, framework, from_version, to_version, "filtered_md")

with st.spinner("Loading entities…"):
    resp = call_tool(get_artifact_content, framework, from_version, to_version, "entities_json")
```

---

## File: `03_rule_explorer.py`

### Step 1 — Inject local stylesheet

```css
/* Skeleton shimmer for search loading state */
@keyframes sweep {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}
.search-loading {
    background: linear-gradient(
        90deg,
        var(--bg-card) 25%,
        var(--bg-hover) 50%,
        var(--bg-card) 75%
    );
    background-size: 200% 100%;
    animation: sweep 1.4s ease infinite;
    border-radius: var(--radius-lg);
    height: 72px;
    margin-bottom: 0.75rem;
}

/* Search result cards */
.rule-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1rem 1.25rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.15s;
}
.rule-card:hover { border-color: var(--border-bright); }

/* Rule type badge (top of each card) */
.rule-type-badge {
    display: inline-block;
    background: var(--info-dim);
    color: var(--info);
    border-radius: 5px;
    padding: 2px 8px;
    font-size: 11px;
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.6rem;
}

/* Rule statement (main text of each card) */
.rule-statement {
    font-size: 14.5px;
    font-weight: 500;
    color: var(--text);
    line-height: 1.5;
    margin-bottom: 0.5rem;
}

/* Rule action step text */
.rule-action {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.6;
}

/* Source link row at the bottom of each card */
.rule-source { margin-top: 0.5rem; font-size: 11.5px; font-family: var(--font-mono); }
.rule-source a { color: var(--accent); text-decoration: none; }
.rule-source a:hover { text-decoration: underline; }

/* Results count header */
.results-header {
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 1.25rem 0 0.75rem;
}
```

### Step 2 — Page header HTML

Replace `st.title("Rule Explorer")` with the standard icon-header block (icon: `🔍`).

### Step 3 — Single-row search bar

Replace the stacked query input, framework selectbox, and button with a three-column row:
```python
col_q, col_fw, col_btn = st.columns([4, 2, 1], gap="small")
```

- `col_q`: text input with `label_visibility="collapsed"`, placeholder `"e.g. javax.persistence to jakarta.persistence"`
- `col_fw`: selectbox with options `["All frameworks"] + list(FRAMEWORK_DISPLAY_NAMES.values())`, `label_visibility="collapsed"`
- `col_btn`: `st.button("Search", use_container_width=True)`

### Step 4 — Skeleton loader

Immediately after `search_clicked` check, before running the search:
```python
skeleton_area = st.empty()
skeleton_area.markdown(
    "".join(['<div class="search-loading"></div>'] * 4),
    unsafe_allow_html=True,
)
```

After the `ThreadPoolExecutor` call returns:
```python
skeleton_area.empty()
```

### Step 5 — Results count header

Before the result cards:
```html
<div class="results-header">— {n} results found</div>
```

### Step 6 — Result card HTML structure

Replace `st.expander(...)` per result with:
```html
<div class="rule-card">
  <div class="rule-type-badge">{rule_type}</div>   <!-- only if rule_type present -->
  <div class="rule-statement">{statement}</div>
  <div class="rule-action">{action_step}</div>      <!-- only if action_step present -->
  <div class="rule-source">
    <a href="{source_url}" target="_blank">↗ View source</a>
  </div>                                            <!-- only if source_url present -->
</div>
```

---

## File: `04_context_dashboard.py`

### Step 1 — Inject local stylesheet

```css
/* Three-dot loader animation */
@keyframes blink { 0%,80%,100%{opacity:0.15} 40%{opacity:1} }
.dots span {
    display:inline-block; width:6px; height:6px;
    border-radius:50%; background:var(--accent);
    margin:0 2px; animation:blink 1.2s infinite;
}
.dots span:nth-child(2) { animation-delay:0.2s; }
.dots span:nth-child(3) { animation-delay:0.4s; }

/* Inline button loading state (replaces Complete/Skip buttons) */
.btn-loading {
    display:flex; align-items:center; justify-content:center; gap:8px;
    background:var(--accent-dim);
    border:1px solid var(--accent);
    border-radius:var(--radius);
    padding:7px 14px;
    font-family:var(--font-mono);
    font-size:12px;
    color:var(--accent);
    width:100%;
    cursor:not-allowed;
}

/* Pending step card */
.step-card {
    background:var(--bg-card);
    border:1px solid var(--border);
    border-radius:var(--radius-lg);
    padding:0.85rem 1rem;
    margin-bottom:0.6rem;
    transition:border-color 0.15s;
}
.step-card:hover { border-color:var(--border-bright); }

/* Step text */
.step-summary { flex:1; font-size:13.5px; color:var(--text); line-height:1.5; }

/* Pill row below step summary */
.step-meta { display:flex; gap:6px; flex-wrap:wrap; margin-top:4px; }

/* Base pill style */
.pill {
    font-family:var(--font-mono); font-size:10.5px; padding:2px 7px;
    border-radius:5px; border:1px solid var(--border);
    color:var(--text-secondary); background:var(--bg-surface);
    text-transform:uppercase; letter-spacing:0.04em;
}

/* Semantic pill variants */
.pill.effort-mechanical { color:var(--info);    border-color:var(--info);    background:var(--info-dim); }
.pill.effort-substantial{ color:var(--warning); border-color:var(--warning); background:var(--warning-dim); }
.pill.severity-high     { color:var(--danger);  border-color:var(--danger);  background:var(--danger-dim); }

/* Active context status bar */
.status-bar {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius); padding:8px 14px;
    font-family:var(--font-mono); font-size:11.5px; color:var(--text-secondary);
    margin-bottom:1.25rem; display:flex; align-items:center; gap:8px;
}

/* Pulsing status dot */
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* Setup form card (pre-context state) */
.setup-card {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius-lg); padding:1.5rem;
    max-width:560px; margin:2rem auto;
}
```

### Step 2 — Page header HTML

Replace `st.title("Context Dashboard")` with the standard icon-header block (icon: `📋`).

### Step 3 — Setup card wrapper

Wrap the pre-context form in:
```python
st.markdown('<div class="setup-card">', unsafe_allow_html=True)
# ... form widgets ...
st.markdown('</div>', unsafe_allow_html=True)
```

Inside the setup form, place `From version` and `To version` inputs side-by-side in `st.columns(2)`.

### Step 4 — Spinner on context creation

```python
with st.spinner("Creating context…"):
    response = call_tool(create_migration_context, ...)
```

### Step 5 — Status bar

Replace `st.caption(f"Status: ...")` with:
```html
<div class="status-bar">
  <span style="width:7px;height:7px;border-radius:50%;background:{dot_color};
               display:inline-block;animation:pulse 2s infinite;"></span>
  Context <code style='background:transparent;border:none;color:var(--accent);'>{context_id}</code>
  · status: <b style='color:var(--text);'>{status}</b>
  · {framework} · {from_version} → {to_version}
</div>
```

Where `dot_color` is `var(--accent)` if status is `"in-progress"`, otherwise `var(--muted)`.

### Step 6 — Spinner on step list load

```python
with st.spinner("Loading pending steps…"):
    steps_resp = call_tool(get_pending_steps, context_id)
```

### Step 7 — Step count header

Before the step loop:
```html
<div style="font-family:var(--font-mono);font-size:11.5px;color:var(--muted);
            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">
  — {n} pending steps
</div>
```

### Step 8 — Step card HTML

For each step, lay out `st.columns([5, 2])`. Left column (width 5) renders the step card:
```html
<div class="step-card" style="flex-direction:column;align-items:flex-start;">
  <div class="step-summary">{summary}</div>
  <div class="step-meta">
    <span class="pill effort-{effort_lower}">{effort}</span>    <!-- if effort present -->
    <span class="pill severity-{severity_lower}">{severity}</span> <!-- if severity present -->
    <span class="pill">{scope}</span>                           <!-- if scope present -->
    <span class="pill">auto</span>                             <!-- if automatable -->
  </div>
</div>
```

### Step 9 — Inline button loader (Complete)

Right column (width 2) for each step:
```python
completing_key = f"completing_{step_id}"

if st.session_state.get(completing_key):
    st.markdown("""
<div class="btn-loading">
  <div class="dots"><span></span><span></span><span></span></div>
  Saving…
</div>
""", unsafe_allow_html=True)
    upd = call_tool(update_step_status, context_id, step_id, outcome="completed")
    # update session state counts from upd
    del st.session_state[completing_key]
    st.rerun()
elif st.button("✓ Complete", key=f"complete_{step_id}", use_container_width=True):
    st.session_state[completing_key] = True
    st.rerun()
```

### Step 10 — Inline button loader (Skip)

Immediately below the Complete block:
```python
skipping_key = f"skipping_{step_id}"

if st.session_state.get(skipping_key):
    st.markdown("""
<div class="btn-loading">
  <div class="dots"><span></span><span></span><span></span></div>
  Skipping…
</div>
""", unsafe_allow_html=True)
    upd = call_tool(update_step_status, context_id, step_id, outcome="skipped")
    # update session state counts from upd
    del st.session_state[skipping_key]
    st.rerun()
elif st.button("→ Skip", key=f"skip_{step_id}", use_container_width=True):
    st.session_state[skipping_key] = True
    st.rerun()
```

### Step 11 — Close Context spinner

```python
with st.expander("⊠  Close Context"):
    # selectbox and textarea widgets ...
    if st.button("Close Context", use_container_width=True):
        with st.spinner("Closing context…"):
            resp = call_tool(close_migration_context, context_id, final_status, notes)
```

---

## File: `05_community.py`

### Step 1 — Inject local stylesheet

```css
/* Three-dot loader (shared with other pages) */
@keyframes blink { 0%,80%,100%{opacity:0.15} 40%{opacity:1} }
.dots span {
    display:inline-block; width:6px; height:6px;
    border-radius:50%; background:var(--accent);
    margin:0 2px; animation:blink 1.2s infinite;
}
.dots span:nth-child(2) { animation-delay:0.2s; }
.dots span:nth-child(3) { animation-delay:0.4s; }

/* Vote flash animation */
@keyframes vote-flash {
    0%   { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
    50%  { background:var(--accent);     border-color:var(--accent); color:var(--accent-text); }
    100% { background:var(--accent-dim); border-color:var(--accent); color:var(--accent); }
}

/* Voting state button (replaces the ▲ button during API call) */
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

/* Skeleton shimmer for page load */
@keyframes sweep {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}
.skeleton-card {
    background: linear-gradient(
        90deg,
        var(--bg-card) 25%,
        var(--bg-hover) 50%,
        var(--bg-card) 75%
    );
    background-size: 200% 100%;
    animation: sweep 1.4s ease infinite;
    border-radius: var(--radius-lg);
    height: 110px;
    margin-bottom: 0.75rem;
}

/* Insight card */
.insight-card {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius-lg); padding:1.1rem 1.25rem;
    margin-bottom:0.75rem;
    transition:border-color 0.15s, transform 0.15s;
    position:relative;
}
.insight-card:hover { border-color:var(--border-bright); transform:translateY(-1px); }

/* Verified card — left accent stripe */
.insight-card.verified { border-left:3px solid var(--accent); }

/* Card text regions */
.insight-statement { font-size:14.5px; font-weight:600; color:var(--text); margin-bottom:0.5rem; line-height:1.5; }
.insight-solution  { font-size:13px; color:var(--text-secondary); line-height:1.65; margin-bottom:0.75rem; }
.insight-footer    { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }

/* Vote count badge */
.vote-badge {
    display:inline-flex; align-items:center; gap:5px;
    font-family:var(--font-mono); font-size:11.5px; color:var(--text-secondary);
    background:var(--bg-surface); border:1px solid var(--border);
    border-radius:6px; padding:3px 8px;
}

/* Verified badge */
.verified-badge {
    display:inline-flex; align-items:center; gap:4px;
    font-size:11.5px; font-family:var(--font-mono);
    color:var(--accent); background:var(--accent-dim);
    border:1px solid var(--accent); border-radius:6px; padding:3px 8px;
    text-transform:uppercase; letter-spacing:0.05em;
}

/* Source link */
.source-link { font-size:11.5px; font-family:var(--font-mono); color:var(--info); text-decoration:none; }
.source-link:hover { text-decoration:underline; }
```

### Step 2 — Page header HTML

Replace `st.title("Community Insights")` with the standard icon-header block (icon: `💬`).

### Step 3 — Skeleton loader on page load

Before calling `get_community_insights`, render three skeleton cards:
```python
skel = st.empty()
skel.markdown(
    "".join(['<div class="skeleton-card"></div>'] * 3),
    unsafe_allow_html=True,
)
result = call_tool(get_community_insights)
skel.empty()
```

### Step 4 — Insight count header

Before the insight loop:
```html
<div style="font-family:var(--font-mono);font-size:11.5px;color:var(--muted);
            text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.75rem;">
  — {n} insights
</div>
```

### Step 5 — Insight card layout

For each insight use `st.columns([8, 1], gap="small")`. Left column (width 8) renders the card HTML:
```html
<div class="insight-card [verified]">
  <div class="insight-statement">{statement}</div>
  <div class="insight-solution">{solution}</div>
  <div class="insight-footer">
    <span class="vote-badge">▲ {votes}</span>
    <span class="verified-badge">✓ Verified</span>  <!-- only if verified -->
    <a class="source-link" href="{url}" target="_blank">↗ Source</a>  <!-- only if url -->
  </div>
</div>
```

Add `verified` class to `.insight-card` only when `insight.get("verified")` is `True`.

### Step 6 — Vote flash loader

Right column (width 1):
```python
voting_key = f"voting_{insight_id}"

if st.session_state.get(voting_key):
    st.markdown('<div class="voting-btn">▲</div>', unsafe_allow_html=True)
    call_tool(vote_insight, insight_id=insight_id, delta=1)
    del st.session_state[voting_key]
    st.rerun()
elif st.button("▲", key=f"vote_{insight_id}", help="Vote up this insight"):
    st.session_state[voting_key] = True
    st.rerun()
```

### Step 7 — Submit form layout

Inside the `st.form("submit_insight_form")`:
- `Spring Boot version` and `Evidence URL` inputs side-by-side in `st.columns(2)`
- Submit button: `st.form_submit_button("Submit Insight", use_container_width=True)`

### Step 8 — Spinner on insight submit

```python
with st.spinner("Submitting insight…"):
    resp = call_tool(submit_migration_insight, ...)
```

---

## What Was Not Changed

The following are explicitly out of scope and untouched:

- All business logic, tool calls, and API call arguments
- Import structure and function signatures in all files
- `_helpers.py` and `_constants.py`
- No new Python packages — all styling is pure CSS via `st.markdown`
- Streamlit components are reused (`st.metric`, `st.tabs`, `st.expander`, `st.form`, `st.columns`) — only their appearance is overridden by CSS selectors, never replaced with raw HTML equivalents
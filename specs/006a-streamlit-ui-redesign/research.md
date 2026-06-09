# Migration Oracle — Design Research & Rationale

## Who Uses This App

Before any design decision can be justified, the user needs to be understood. Migration Oracle is used by Java backend engineers and DevOps practitioners who are:

- Comfortable with terminal interfaces, dark IDEs, and developer tooling
- Working inside a technical process (a framework migration), not a business workflow
- Looking for signal quickly — they want to know the status of a migration, what's pending, and what's blocked
- Not looking to be entertained; they want density, precision, and clarity

This audience is the daily user of tools like GitHub, Linear, Vercel, Datadog, and JetBrains IDEs. Their baseline expectation for a "good" tool UI is extremely high. A Streamlit app with the default white theme and no layout structure reads as a prototype to them, even if the backend logic is excellent.

The redesign is therefore aimed at matching the visual vocabulary of tools this audience already trusts.

---

## Research: Streamlit CSS Injection

Streamlit does not expose a theming API that covers all component states. The official theme system (via `config.toml`) handles primary color, background color, and font — but it cannot style individual component states like button hover behavior, input focus rings, or metric card typography.

The established pattern for full control is `st.markdown(..., unsafe_allow_html=True)` with a `<style>` block. This injects CSS into the page's `<head>` via Streamlit's HTML passthrough. It works reliably across Streamlit 1.x.

Key selectors used for each component type:

| Component | Selector pattern |
|---|---|
| Page background | `[data-testid="stAppViewContainer"]` |
| Sidebar | `[data-testid="stSidebar"]` |
| Nav items | `[data-testid="stSidebarNav"] a` |
| Metric label | `[data-testid="stMetricLabel"]` |
| Metric value | `[data-testid="stMetricValue"]` |
| Alert variants | `[data-testid="stAlertContentInfo"]` etc. |
| Buttons | `.stButton > button` |
| Primary button | `.stButton > button[kind="primary"]` |
| Form submit | `.stFormSubmitButton > button` |
| Inputs | `.stTextInput > div > div > input` |
| Select | `.stSelectbox > div > div` |
| Tabs | `.stTabs [data-baseweb="tab"]` |
| Expanders | `.streamlit-expanderHeader` |

These selectors were identified by inspecting the Streamlit-rendered DOM. They are internal to Streamlit and could change across versions, but have been stable across the 1.x series.

---

## Research: Dark Mode for Developer Tools

Dark interfaces are not purely aesthetic. There is a practical case for them in developer tooling contexts:

**Reduced eye strain during extended use.** Framework migrations are not 15-minute tasks. Engineers spend hours in these tools. Studies on display fatigue (including Rosenfield 2011, IOVS) show that self-luminous displays cause more ciliary muscle strain at high brightness. Dark themes reduce overall luminance.

**Terminal cognitive association.** Developer tools with dark interfaces are associated with power and low-level control — terminal, vim, VS Code dark themes, GitHub dark mode. This association is real: a tool that looks like a terminal feels more authoritative to engineers than one that looks like a form.

**Error visibility.** On a dark background, red (`#f87171`) and amber (`#f5a623`) severity indicators are highly visible without being aggressive. On a white background, the same colors need to be darker to achieve contrast, which can make them feel alarming rather than informative.

**The chosen background value `#0d0f14`** is a very slightly blue-shifted near-black. Pure black (`#000000`) creates harsh contrast with white text and can cause halation (text appearing to bleed). The blue shift (`0d0f14` vs `000000`) reduces this without appearing gray.

---

## Research: Typography in Technical UIs

Three typographic roles exist in this app: display/branding, body/UI, and data/code. Each requires a different typeface.

**Syne** (display role) was chosen for page titles and the sidebar brand. It is a geometric sans-serif with an unusually high-weight 800 cut that creates strong typographic anchors. Unlike generic options (Inter, Roboto), Syne has a distinctive geometric quality in its uppercase characters that reads as intentional without being decorative. It was designed by the Bonjour Monde foundry specifically for editorial and identity use.

**DM Sans** (body role) was chosen for all UI prose, form labels, and button text. It was designed by Colophon Foundry and is engineered for legibility at small sizes. It is optically balanced at 13–14px, the range used throughout the app. Unlike Inter (overused in design systems) or Source Sans (too corporate), DM Sans has a slight warmth that prevents the interface from feeling cold.

**IBM Plex Mono** (data role) was chosen for all status labels, badge text, metadata chips, section count headers, and CLI output. Monospaced fonts serve two purposes here: they signal "this is data, not prose" — creating a visual distinction between navigational text and informational text — and they make tabular data scannable by ensuring consistent character widths. IBM Plex Mono specifically was chosen over alternatives (JetBrains Mono, Fira Code) because it lacks programming ligatures (no `!=` becoming a single glyph), keeping it appropriate for non-code label text.

---

## Research: Color Encoding for Status Data

The original app displayed effort levels (`mechanical`, `substantial`) and severity (`high`) as raw text strings in table columns. Research on data visualization and UI design consistently shows that color is processed preattentively — the brain identifies color differences before conscious attention is applied (Treisman & Gelade, 1980).

For the status pills in the redesigned Context Dashboard:

| Value | Color | Rationale |
|---|---|---|
| `mechanical` effort | Blue (`#60a5fa`) | Mechanical = routine, systematic, low cognitive load. Blue is calm and informational. |
| `substantial` effort | Amber (`#f5a623`) | Substantial = requires judgment and time. Amber signals caution and attention without alarm. |
| `high` severity | Red/danger (`#f87171`) | High severity = potential for migration failure. Red is universally understood as a warning signal. |
| `verified` insight | Green/accent (`#4ade9e`) | Verified = trustworthy, approved. Green is universally associated with confirmation and validity. |

This color scheme follows the semantic conventions established by years of UI convention (red = error, amber = warning, blue = info, green = success). Using them consistently — not decoratively — means engineers can parse a list of 20 pending steps and identify high-severity ones without reading every row.

---

## Research: Layout Principles Applied

### Information Density vs. Clarity

Streamlit's default layout places every widget vertically, full-width. This creates an artificially long page where unrelated inputs are visually equidistant from each other, making it hard to perceive grouping.

The redesign uses `st.columns` deliberately:

- `01_pipeline_trigger.py`: 3:2 split separates the "do something" (form) from "understand context" (info panel). This follows the "primary action + supporting context" layout pattern seen in tools like Stripe's dashboard.
- `03_rule_explorer.py`: 4:2:1 split for the search bar creates a single logical input unit rather than three separate widgets stacked vertically.
- `04_context_dashboard.py`: Card + action columns for each step prevent the action buttons from becoming the visual focus. The step description is primary; the actions are secondary.

### Progressive Disclosure

Not all information needs to be visible at all times. Three patterns are used:

- The "Submit New Insight" form in `05_community.py` is inside an expander. New submissions are a minority use case; the default view should be the list of existing insights.
- The "Close Context" section in `04_context_dashboard.py` is inside an expander. Closing a context is a terminal, irreversible action — it should require intentional expansion, not be casually visible.
- The context setup form in `04_context_dashboard.py` uses `st.stop()` after the setup state, so the rest of the page does not render at all until a context is loaded. This prevents a confusing empty dashboard from appearing.

### Visual Anchoring

Each page starts with the same icon-header structure: an emoji icon in an accent-tinted rounded box, a page title in Syne, and a one-line monospace subtitle. This gives every page a consistent entry point and makes the icon scannable in peripheral vision when switching between pages quickly.

---

## Research: Why CSS Custom Properties (Variables)

All design tokens are defined as CSS custom properties on `:root` in `app.py`. This means every subsequent page file can reference `var(--accent)`, `var(--bg-card)`, etc., without redeclaring values.

The alternative — hardcoding hex values in each page — creates a maintenance problem: changing the accent color from `#4ade9e` to something else would require finding and replacing it across five page files and numerous `st.markdown` HTML strings.

With custom properties, changing the entire theme requires editing exactly one block in `app.py`. This is the same reason design systems (Material, Radix, Tailwind) use tokens rather than raw values.

---

## Research: Streamlit Metric Override

Streamlit's `st.metric` is useful but visually weak by default: a small gray label, a medium black number, and an optional delta. For this app, the Completed/Skipped/Pending counts are critical at-a-glance information. They should be the largest, most immediately visible numbers on the Context Dashboard.

The override uses:

```css
[data-testid="stMetricValue"] {
    color: var(--accent);
    font-family: var(--font-display);
    font-size: 32px;
    font-weight: 700;
}
```

This makes metric values render in Syne at 32px in the green accent color — impossible to miss against a dark card background. The label is reduced to 11px IBM Plex Mono in uppercase, creating a strong hierarchy: `COMPLETED` in small caps, `12` in large accent numerals.

---

## Research: The Verified Insight Border Stripe

The left border stripe on verified community insights (`border-left: 3px solid var(--accent)`) is a pattern used in Slack (for pinned messages), Linear (for priority items), and GitHub (for reviewed PRs). It communicates "this item has a different status from the others" without changing the card's background color (which would affect readability of the content inside) or adding a heavy visual element.

The border stripe works because:
- It is applied consistently — all verified insights get it, none of the unverified ones do
- It is in the accent green, which already carries the meaning "confirmed/valid" in this color system
- It sits on the left edge, where the eye lands first when scanning a vertical list
- It requires no label to be understood — the color alone is sufficient signal

---

## Research: Loading State Design

### Why Loading States Matter for Developer Tools

The absence of loading feedback is one of the most common complaints about Streamlit apps in production. When a button is clicked, Streamlit re-runs the entire Python script — which can take anywhere from 200ms (a simple API call) to several seconds (a subprocess, a search over embeddings). Without a visual response, the user cannot tell whether their click registered, whether the app is working, or whether something has gone wrong.

This is not a minor UX detail. In developer tooling, the mental model is "terminal" — every command gives immediate output. A button that silently freezes breaks that contract and creates doubt. Engineers will click again, leading to duplicate submissions; or they will assume a failure and navigate away mid-operation.

### The Four Loader Patterns and Why Each Was Chosen

**Running banner (`01_pipeline_trigger.py`)** — the pipeline subprocess can run for tens of seconds to several minutes. A persistent banner (not a spinner that disappears, not a progress bar with unknown denominator) was chosen because it matches what the output below it is doing: streaming continuously. The banner and the output are in the same "running" state. When the process ends, both clear at once. The three-dot `blink` animation (400ms peak, 1.2s cycle, staggered 200ms between dots) is slow enough to read as "working" rather than "alert".

**Skeleton cards (`03_rule_explorer.py`, `05_community.py`)** — skeleton loading is a pattern established by Facebook (2013) and now standard in LinkedIn, Slack, and most data-heavy interfaces. Its advantage over a centered spinner is spatial: it pre-occupies the exact area that results will fill, so the page doesn't jump when content arrives. The `sweep` keyframe (`background-position` animating from `-200%` to `200%`) creates a horizontal shimmer that reads as "content is coming from the right" — a subtle directional cue consistent with left-to-right reading order. Opacity steps down on the third skeleton card to suggest depth.

**Inline button loader (`04_context_dashboard.py`)** — the Complete and Skip buttons are repeated for every pending step. If a standard `st.spinner` were used, it would appear at the top of the page while the button that was clicked is somewhere in a list — spatially disconnected from the action. The inline loader solves this by replacing the exact button that was clicked with a `.btn-loading` div in the same position. The `session_state` flag pattern (`completing_<step_id>`, `skipping_<step_id>`) ensures only the clicked button shows the loader; all other step buttons remain interactive. This is the same pattern used in GitHub's issue list when marking issues as closed.

**Vote flash (`05_community.py`)** — voting is instantaneous from the user's perspective (no visible result changes except the count incrementing). A persistent loader would feel disproportionate. Instead, the button plays a `vote-flash` keyframe (green pulse, 0.6s, three cycles) while the API call runs in the background. This is the same pattern used by Twitter/X's like button: a brief animation confirms the action without blocking further interaction.

### The `session_state` Flag Pattern

Streamlit has no native "button loading state." The workaround is:

```python
if st.session_state.get("completing_step_1"):
    # render loader HTML
    call_tool(...)          # do the work
    del st.session_state["completing_step_1"]
    st.rerun()
elif st.button("✓ Complete", key="complete_step_1"):
    st.session_state["completing_step_1"] = True
    st.rerun()
```

This causes three renders per action: the initial render (button visible), the loading render (loader visible, work done), and the final render (updated state). The loading render is the only one visible to the user — the transition from button to loader to updated state happens faster than a human can perceive as two separate frames, so it reads as a smooth single interaction.

### `st.spinner()` for One-Shot Operations

For operations that happen once (context creation, context close, insight submission, artifact fetches), `st.spinner()` is used rather than the flag pattern. The reasons:

- These are not repeated in a loop, so spatial disconnection is not an issue
- They produce a meaningful result that replaces the form or section (the context loads, the modal closes, the success banner appears)
- `st.spinner` is idiomatic Streamlit — engineers reading the code will recognise it immediately without needing to understand the flag pattern

The spinner text is always a verb phrase in present continuous tense: `"Creating context…"`, `"Closing context…"`, `"Submitting insight…"`, `"Loading pipeline runs…"`. This matches the convention established by GitHub Actions, Vercel deploys, and most CI/CD interfaces — the system tells you what it is doing, not what you asked it to do.

---

## What Was Deliberately Not Done

**Animations are limited to loading states and micro-interactions.** Motion in the app falls into two categories: functional loaders (running banner, skeleton shimmer, inline dot animation, vote flash) that communicate system state, and micro-interactions (button hover transitions at 150ms, card hover border transitions) that communicate interactivity. Decorative animations — page transitions, entrance effects, parallax — are absent. Streamlit re-runs Python on every interaction, so any animation that spans a rerun boundary would be interrupted; all loader animations are therefore CSS-only and self-contained within a single render cycle.

**No custom JavaScript.** Streamlit does not officially support injecting JS into pages in a stable way. All interactivity is achieved through CSS (`:hover`, `:focus`) or through Python (Streamlit state, `st.rerun()`).

**No replacement of Streamlit components with raw HTML equivalents.** Buttons, forms, inputs, and tabs are still Streamlit components — only their appearance is overridden via CSS. Replacing them with HTML would break Streamlit's state management system and `st.form` submission handling.

**No third-party Streamlit component libraries.** Libraries like `streamlit-extras` or `streamlit-elements` introduce dependency risk and may not be available in all deployment environments. The entire redesign is achievable with zero new Python packages — only Google Fonts (loaded via CSS `@import`) are added.
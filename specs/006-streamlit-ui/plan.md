# Implementation Plan: Streamlit Operator UI

**Branch**: `main` | **Date**: 2026-06-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-streamlit-ui/spec.md`

---

## Summary

Build a five-page Streamlit multi-page app (`migration_oracle/streamlit_app/`) that gives operators a browser-based GUI for the Migration Oracle pipeline. The app calls tool functions from `migration_oracle.mcp.tools.*` as direct in-process Python imports (no MCP server process), invokes the pipeline CLI as a subprocess, and surfaces all errors inline via `st.error()`.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `streamlit>=1.35` (already in pyproject.toml), `migration_oracle` package (this repo), `sentence-transformers>=3.0` (for search), `neo4j>=5.0`

**Storage**: Neo4j (accessed exclusively through tool functions — no direct driver usage in page code)

**Testing**: `pytest>=8.0`, `pytest-asyncio>=0.23` (existing dev deps)

**Target Platform**: Local desktop browser (internal network)

**Project Type**: Web application (Streamlit multi-page app)

**Performance Goals**: First output line within 3 seconds of pipeline submit (SC-001); page loads under 2 seconds (SC-002)

**Constraints**: Single operator per Streamlit process; no auth; Neo4j env vars must be set before app start

**Scale/Scope**: 5 pages, ~7 tool function import modules, 1 subprocess integration

---

## Constitution Check

The project constitution file contains only unfilled placeholders — no governance constraints apply. No gate violations to resolve.

---

## Project Structure

### Documentation (this feature)

```text
specs/006-streamlit-ui/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: tool signature findings, async/decorator research
├── data-model.md        # Phase 1: all tool response shapes and session state
├── quickstart.md        # Phase 1: local dev runbook
├── contracts/
│   └── 006-streamlit-ui.md   # Phase 1: boundary rules
└── tasks.md             # Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code

```text
migration_oracle/
└── streamlit_app/
    ├── app.py                          # Streamlit entry point; sidebar config only
    ├── _helpers.py                     # Shared helpers: call_tool, framework_selectbox, effort_badge
    └── pages/
        ├── 01_pipeline_trigger.py      # US1 — Pipeline Trigger
        ├── 02_run_browser.py           # US2 — Run Browser
        ├── 03_rule_explorer.py         # US3 — Rule Explorer
        ├── 04_context_dashboard.py     # US4 — Context Dashboard
        └── 05_community.py             # US5 — Community

tests/
└── streamlit/                          # Streamlit page unit tests (optional; UI pages are smoke-tested manually)
```

**Structure Decision**: Single-project layout. All pages under `migration_oracle/streamlit_app/pages/` using Streamlit's numeric-prefix naming convention so sidebar navigation order is deterministic.

---

## Module-by-Module Responsibilities

### `app.py` — Entry Point

- Sets `st.set_page_config(layout="wide", page_title="Migration Oracle")`.
- **Does NOT import anything from `migration_oracle`** — no tool functions, no graph driver, no pipeline modules. All `migration_oracle` imports are deferred to individual page scripts.
- Streamlit discovers and loads pages lazily: a page's module is only imported when the operator first navigates to it. This means Neo4j connection failures surface on the first tool call within a page, not at app startup.
- **Neo4j unreachable at startup**: the app starts successfully regardless of Neo4j availability. When an operator navigates to a page and the first tool call fails (e.g. `ServiceUnavailable`), the page's `try/except` catches it and renders `st.error(...)` inline. No startup health check is implemented.
- Streamlit discovers pages automatically from the `pages/` subdirectory.

### `pages/01_pipeline_trigger.py` — Pipeline Trigger (US1)

**Responsibilities**:
- Present form: framework selector, from_version, to_version, flag checkboxes.
- On submit: build subprocess command list, spawn `Popen`, stream stdout line-by-line into `st.empty()`.
- Display exit code indicator (green/red).

**Imports**:
```python
import sys, subprocess, asyncio
import streamlit as st
from migration_oracle.pipeline.extractors import FRAMEWORK_DISPLAY_NAMES
```

**Key behavior**:
- Framework selector: `st.selectbox` with display names as labels; pass the CLI key as the `--framework` value.
- Subprocess command: `[sys.executable, "-m", "migration_oracle.cli", "--framework", key, from_version, to_version] + flag_args`
- `shell=False` (default). Never `shell=True`.
- After `proc.wait()`: show `st.success(f"Exit 0")` or `st.error(f"Exit {code}: {last_stderr_line}")`.
- No tool function calls on this page.

### `pages/02_run_browser.py` — Run Browser (US2)

**Responsibilities**:
- Call `list_pipeline_runs()` on page load (cached 60 s).
- Render selectbox; show 3 tabs: Raw MD, Filtered MD, Entities JSON.
- Per tab: call `get_artifact_content(...)` and render appropriately.

**Imports**:
```python
import json
import streamlit as st
from migration_oracle.mcp.tools.artifacts import list_pipeline_runs, get_artifact_content
```

**Key behavior**:
```python
@st.cache_data(ttl=60)
def _cached_list_runs():
    return list_pipeline_runs()
```
- Display label: `f"{r['framework']} → {r['to_version']}"` (skip `from_version` when blank).
- `get_artifact_content` call wrapped in `try/except`; `st.error(...)` on failure.
- `artifact_type="entities_json"` content: `st.json(json.loads(content), expanded=1)`.
- Empty state: `st.info("No pipeline runs found")` before selectbox.

### `pages/03_rule_explorer.py` — Rule Explorer (US3)

**Responsibilities**:
- Text input for query; framework filter dropdown.
- Call `search_migration_knowledge(...)` on submit (async — use `asyncio.run`).
- Render result cards.

**Imports**:
```python
import asyncio
import streamlit as st
from migration_oracle.mcp.tools.search import search_migration_knowledge
from migration_oracle.pipeline.extractors import FRAMEWORK_DISPLAY_NAMES
from migration_oracle.streamlit_app._helpers import call_tool
```

**Key behavior**:
- Do NOT use `framework_selectbox` here — that helper returns CLI keys. Rule Explorer passes display names to `search_migration_knowledge`.
- Build the filter dropdown inline:
  ```python
  display_names = ["All"] + list(FRAMEWORK_DISPLAY_NAMES.values())
  choice = st.selectbox("Framework filter", display_names, key="re_fw")
  fw: str | None = None if choice == "All" else choice  # display name or None
  ```
- Call pattern — always pass `framework` explicitly:
  ```python
  coro = search_migration_knowledge(query=q, framework=fw, max_results=20)
  result = call_tool(asyncio.run, coro)
  ```
  When `fw is None`, the Cypher `WHERE $framework IS NULL OR v.framework = $framework` returns hits across all frameworks. When `fw` is a display name (e.g. `"Spring Boot"`), only nodes for that framework are returned.
- Each card: `st.expander(hit["statement"][:80])` containing `rule_type` badge, `source_url` link, `action_step` description.
- No `steps` or `scopes` sub-sections (not present in search hit shape).
- Empty state: `st.info("No rules found for this query")`.

### `pages/04_context_dashboard.py` — Context Dashboard (US4)

**Responsibilities**:
- Form for project_id, from_version, to_version, framework.
- Load/create context; store in `st.session_state["context"]`.
- Show status, metrics, pending steps table.
- Mark Complete / Skip buttons per row; re-fetch steps after each action.
- Close Context button for in-progress contexts.

**Imports**:
```python
import streamlit as st
from migration_oracle.mcp.tools.context import (
    create_migration_context,
    get_pending_steps,
    update_step_status,
    close_migration_context,
)
from migration_oracle.pipeline.extractors import FRAMEWORK_DISPLAY_NAMES
```

**Key behavior**:
- Session state keys (flat, prefixed — all set together after a successful `create_migration_context` call):
  - `st.session_state["context_id"]` — string context UUID
  - `st.session_state["context_project_id"]` — string project ID
  - `st.session_state["context_from_version"]` — string from-version
  - `st.session_state["context_to_version"]` — string to-version
  - `st.session_state["context_framework"]` — string framework display name
  - `st.session_state["context_status"]` — string migration status
  - `st.session_state["context_completed_count"]` — int
  - `st.session_state["context_skipped_count"]` — int
- If `st.session_state.get("context_id")` is set, skip the load form and render dashboard directly.
- `get_pending_steps` wrapped in `try/except`; result in `response["pending_steps"]`.
- After `update_step_status` succeeds: (a) update `st.session_state["context_completed_count"]` and `st.session_state["context_skipped_count"]` from `response["completed_count"]` and `response["skipped_count"]`; (b) call `get_pending_steps` again and replace the local pending list. Both must happen in the same rerender so metrics and table are always in sync.
- Skip button flow: show `st.text_input("Reason")` inline per row; submit only when reason provided.
- Close Context button: shown only when `st.session_state["context_status"] == "in-progress"`.
- Empty pending state: `st.info("No pending steps remaining")` in place of table.

### `pages/05_community.py` — Community (US5)

**Responsibilities**:
- Load and display insight cards.
- Vote Up button per card; re-fetch insights after vote.
- Submit New Insight form in expander.

**Imports**:
```python
import streamlit as st
from migration_oracle.mcp.tools.community import (
    get_community_insights,
    vote_insight,
    submit_migration_insight,
)
from migration_oracle.pipeline.extractors import FRAMEWORK_DISPLAY_NAMES
```

**Key behavior**:
- Load: `get_community_insights()` (no arguments for "all insights" view). Wrap in `try/except`.
- Vote Up: `vote_insight(insight_id=id, delta=1)`. After call, re-fetch insights.
- Submit form fields: `statement`, `solution`, `spring_boot_version`, `affected_classes` (split on comma), `evidence_url`, `framework`.
- Submit response: show `st.success("Insight submitted")` when `status == "ok"`, `st.error("Duplicate detected")` when `status == "duplicate"`.
- Empty state: `st.info("No community insights found")` before cards.

---

## Shared Helpers

`migration_oracle/streamlit_app/_helpers.py` is a **required** module. The following patterns are shared across 4+ pages and must not be duplicated.

```python
from __future__ import annotations
from typing import Any, Callable
import streamlit as st
from migration_oracle.pipeline.extractors import FRAMEWORK_DISPLAY_NAMES


def call_tool(fn: Callable, *args: Any, **kwargs: Any) -> Any | None:
    """Call a tool function; catch all exceptions and render st.error. Returns None on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        st.error(str(exc))
        return None


def framework_selectbox(label: str, key: str, include_all: bool = False) -> str | None:
    """Render a framework selectbox. Returns the CLI key (e.g. 'spring-boot'), or None when 'All' is selected.
    NOT used by Rule Explorer — that page needs display names for search_migration_knowledge."""
    options: list[str | None] = list(FRAMEWORK_DISPLAY_NAMES.keys())
    display = list(FRAMEWORK_DISPLAY_NAMES.values())
    if include_all:
        options = [None] + options      # None sentinel for "all frameworks"
        display = ["All"] + display
    idx = st.selectbox(label, range(len(display)), format_func=lambda i: display[i], key=key)
    return options[idx]  # None when "All" selected; callers MUST pass framework=None explicitly, never omit the kwarg


def effort_badge(effort: str) -> str:
    """Return a short human label for an effort value."""
    return {"mechanical": "🔧 Mechanical", "substantial": "⚡ Substantial"}.get(effort, effort)
```

**Pages that use `call_tool`**: Run Browser, Rule Explorer, Context Dashboard, Community (all four).  
**Pages that use `framework_selectbox`**: Pipeline Trigger, Context Dashboard, Community — returns CLI key. Rule Explorer builds its own inline selectbox using display names (see Rule Explorer section).

---

## pyproject.toml

`streamlit>=1.35` is a **runtime dependency** (not a dev dependency) and must be listed under `[project.dependencies]`. It is already present there — **no change to pyproject.toml is required**. Do not move it to `[tool.uv] dev-dependencies` or any optional group; the `streamlit_app` module is part of the installed package and requires Streamlit at runtime.

---

## Implementation Order (suggested)

Implement in user story priority order:

1. `app.py` + sidebar config (no logic — just enables multi-page navigation)
2. `_helpers.py` (shared before any page is implemented)
3. `01_pipeline_trigger.py` (P1 — enables run creation; no graph calls)
4. `02_run_browser.py` (P2 — most operators' first post-run view)
5. `03_rule_explorer.py` (P2 — search)
6. `04_context_dashboard.py` (P3 — tracking)
7. `05_community.py` (P3 — insights)

Each page is independently testable after it is implemented.

---

## Key Implementation Notes

1. **`search_migration_knowledge` is async**: always call with `asyncio.run(...)`.
2. **`vote_insight` signature**: `delta=1` integer, not `direction="up"` string.
3. **`get_community_insights` params**: no `version_filter` or `top_k`; call with keyword args or no args.
4. **`submit_migration_insight` URL field**: parameter is `evidence_url`, not `source_url`.
5. **Run Browser display label**: `from_version` is always `""` in current data; label as `"{framework} → {to_version}"`.
6. **Rule Explorer cards**: `statement[:80]` as title; `rule_type` as badge; `action_step` as body. No steps/scopes sub-sections (not in search hit shape).
7. **FastMCP decorator — import pattern**: `@mcp.tool()` registers the function's schema on the in-memory `mcp` FastMCP instance and then **returns the original function unchanged**. The decorated name is the same callable as the unwrapped function. Therefore: import the decorated names directly (e.g. `from migration_oracle.mcp.tools.artifacts import list_pipeline_runs`) — no `__wrapped__` access, no special unwrapping. Importing the module causes the mcp instance to be created in memory (cheap, no network). No server is started.
8. **`close_migration_context` response key**: `tool_status` (not `status`) — check accordingly.

---

## Complexity Tracking

No constitution violations to justify.

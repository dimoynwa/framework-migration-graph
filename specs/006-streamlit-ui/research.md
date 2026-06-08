# Research: Streamlit Operator UI (006-streamlit-ui)

**Date**: 2026-06-08  
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## Q1: Does streamlit>=1.35 support `st.cache_data` with the `ttl` parameter?

**Decision**: Yes — use `@st.cache_data(ttl=60)` unconditionally.

`st.cache_data` with a `ttl` parameter has been available since Streamlit 1.18.0 (November 2022). In >=1.35 it is stable and the recommended API for data caching. The old `@st.cache` decorator is removed in 1.18+. No version guard is needed.

**pyproject.toml status**: `streamlit>=1.35` is **already present** in `[project.dependencies]`. No change required.

---

## Q2: Streaming subprocess output line-by-line in Streamlit without blocking the UI

**Decision**: Use `subprocess.Popen` with `stdout=PIPE, stderr=PIPE, text=True`, read `stdout` line-by-line in a `for line in proc.stdout` iterator, update an `st.empty()` placeholder after each line, then call `proc.wait()` at the end.

**Pattern**:

```python
import subprocess, sys
import streamlit as st

output_area = st.empty()
lines: list[str] = []
stderr_lines: list[str] = []

with subprocess.Popen(
    cmd,                            # list — no shell=True
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
) as proc:
    for line in proc.stdout:        # blocks on each line, not on process end
        lines.append(line.rstrip())
        output_area.code("\n".join(lines))
    proc.wait()
    stderr_lines = proc.stderr.read().splitlines()

exit_code = proc.returncode
```

**Why this works in Streamlit**: Streamlit rerenders are triggered by widget interactions, not by the iterator. The `for line in proc.stdout` loop runs inside the same Python thread that handles the script run. Streamlit buffers the `st.empty().code()` call and flushes it on each iteration, giving the effect of live streaming without threads or async.

**Alternatives considered and rejected**:
- `asyncio.create_subprocess_exec` + `async for line in proc.stdout`: Requires Streamlit >=1.35 async page support; more complex and not needed for this use case.
- `threading.Thread` + `queue.Queue`: Works but unnecessary complexity; the line iterator approach is sufficient for a single pipeline run.

---

## Q3: FastMCP `@mcp.tool()` — pure decorator or global side-effect on import?

**Decision**: Import tool functions directly. The decorator is safe to import; no server process is started.

**Findings**: `migration_oracle/mcp/instance.py` defines:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("PaysafeMigrationOracle")
```

Each tool module does `from migration_oracle.mcp.instance import mcp` and decorates functions with `@mcp.tool()`. The FastMCP `@mcp.tool()` decorator registers the function's name and schema into an in-memory registry on the `mcp` object. **It does not start a server, open a socket, or spawn a subprocess.** The decorated function remains a plain callable — `@mcp.tool()` returns the original function unchanged (FastMCP wraps at serve-time, not at decoration-time).

**Consequence**: Importing `from migration_oracle.mcp.tools.artifacts import list_pipeline_runs` causes:
1. The `mcp` FastMCP instance to be created in memory (cheap).
2. All tools in that module to be registered with the in-memory registry (cheap).
3. No network activity, no subprocess, no server loop.

The Streamlit app can therefore call tool functions as direct in-process Python calls with no special setup beyond having Neo4j env vars present.

**One caveat**: `search_migration_knowledge` is declared `async def`. Calling it from synchronous Streamlit page code requires `asyncio.run(search_migration_knowledge(...))`. Do not call it with `await` — Streamlit's page script is not an async context.

---

## Critical Discrepancies: Spec vs. Actual Tool Signatures

The following mismatches were discovered between the feature description / spec and the actual implemented tool functions. The plan and data-model reflect the **actual** implementations.

### D1 — `vote_insight`: no `direction` parameter

- **Spec assumed**: `vote_insight(insight_id, direction="up")`
- **Actual**: `vote_insight(insight_id: str, delta: int = 1)`
- **FR-024** already captures this correctly. The UI must pass `delta=1`.

### D2 — `search_migration_knowledge`: async, different params, different hit shape, and framework value type resolved

- **Async**: Must be called with `asyncio.run(...)` from Streamlit.
- **Parameter name**: `framework` (not `framework_filter`); `max_results` (not `top_k`).
- **Hit shape returned**: `{node_id, node_type, statement, score, source_url, action_step, rule_type}`.  
  There is no `title`, `changeType`, `steps`, `scopes`, or `severity` field in search results.
- **UI adaptation**: Rule Explorer cards must be built from `statement[:80]` as the title, `rule_type` as the type badge, `action_step` as the step description. No expandable steps/scopes sub-sections can be populated from search hits alone.
- **Framework value type** (resolved per FR-022 amendment): `search_migration_knowledge` expects the **display name** (e.g. `"Spring Boot"`) as the `framework` argument, matching the function's own default. The function's default `"Spring Boot"` is consistent with this expectation. Always pass explicitly:
  - Specific framework: `search_migration_knowledge(query=q, framework="Spring Boot", max_results=20)` — display name.
  - All frameworks: `search_migration_knowledge(query=q, framework=None, max_results=20)` — pass `None` explicitly; the Cypher `WHERE $framework IS NULL` branch fires and returns across all frameworks. Do **not** omit the kwarg (the default `"Spring Boot"` would apply and narrow results to Spring Boot only).
  - FR-022 (amended): the Pipeline Trigger subprocess receives the CLI key; the search function receives the display name. These are two distinct bindings from the same selector.

### D3 — `get_community_insights`: different parameter set

- **Spec assumed**: `get_community_insights(version_filter="", top_k=20)`
- **Actual**: `get_community_insights(from_version=None, to_version=None, entity_name=None, entity_type=None, verified_only=False, framework="Spring Boot")`
- **UI adaptation**: Call with no arguments for "all insights" view. Expose `verified_only` checkbox optionally. The `top_k` cap is not a parameter; the query returns all matching insights from the graph.

### D4 — `submit_migration_insight`: different field names

- **`source_url`** in spec → **`evidence_url`** in actual.
- **`version_tag`** / `spring_boot_version or angular_version` → single **`spring_boot_version`** parameter (holds the version string regardless of framework).
- **No `source_url` field**: use `evidence_url` for the URL input.

### D5 — `list_pipeline_runs`: `from_version` always empty string

- The current implementation returns `from_version: ""` for all runs (the graph only stores `to_version`).
- **UI adaptation**: Label runs as `"{framework} → {to_version}"` (drop `from_version` from the display label if blank).

### D6 — `streamlit` already in pyproject.toml

- `streamlit>=1.35` is **already listed** in `[project.dependencies]`. No pyproject.toml change needed.

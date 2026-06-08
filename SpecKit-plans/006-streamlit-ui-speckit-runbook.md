# SpecKit Runbook — `006-streamlit-ui`

> **How to use this file:** Paste each prompt block verbatim into Claude Code in the order shown.
> Do not skip the gap-review steps — they catch the most common drift before it compounds.
> Complete all items in a gap review before advancing to the next command.

---

## Prerequisites

Before starting this spec:

- `005-mcp-server` ✅ — all 21 tools registered; `list_pipeline_runs` and `get_artifact_content` must be importable from `migration_oracle.mcp.tools.artifacts`; context tools (`create_migration_context`, `get_pending_steps`, `update_step_status`, `close_migration_context`) must be importable from `migration_oracle.mcp.tools.context`
- `002-pipeline-core` ✅ — `Version` nodes with `rawMdPath`, `filteredMdPath`, `entitiesJsonPath` written by the pipeline; CLI entry point (`python -m migration_oracle.cli`) must be runnable as a subprocess
- `001-foundations` ✅ — `migration_oracle.config` importable; graph driver working
- `streamlit>=1.35` and `watchdog` must be added to `pyproject.toml` dependencies before running `/speckit.plan`
- At least one pipeline run must have been executed so the Run Browser page has data to display during manual testing
- Reference docs to keep open while reviewing gap prompts:
  - `docs/SPEC_ORGANIZATION.md` §006 (page inventory, completion gate, FE read-path constraint)
  - `docs/migration-oracle-redesign.md` §6 (MCP tool contracts for context tools, artifact tools)
  - `migration_oracle/mcp/tools/artifacts.py` — exact return shapes for `list_pipeline_runs` and `get_artifact_content`
  - `migration_oracle/mcp/tools/context.py` — exact return shapes for context tools
  - `migration_oracle/mcp/tools/community.py` — `submit_migration_insight` and `get_community_insights` signatures

---

## Command 1 — `/speckit.specify`

Paste this entire block:

```
/speckit.specify

WHAT it does:
The Streamlit UI module (`migration_oracle/streamlit_app/`) is a browser-based interface
with five pages. It provides an operator with the ability to trigger pipeline runs, browse
run artifacts, explore migration rules and steps, track migration context progress, and
browse and submit community insights — all through a Streamlit multi-page app served
locally or on an internal host.

The app calls tool functions from `migration_oracle.mcp.tools.*` directly (in-process
Python imports) — it does NOT spawn or connect to a separate MCP server process. The
tool functions are pure Python; importing them requires that Neo4j environment variables
are present. The FE never reads the filesystem directly: all artifact content is fetched
via `get_artifact_content()` and all run metadata is fetched via `list_pipeline_runs()`.

WHY it exists:
Operators running the Migration Oracle pipeline currently have no GUI. They must write
custom Cypher queries to find what pipeline runs have been completed, what artifacts
they produced, and what migration rules and steps the graph contains. The Streamlit UI
removes that friction and makes the graph's knowledge accessible without a graph client.

PAGE 01 — Pipeline Trigger (`01_pipeline_trigger.py`) and what it does:
  - Presents a form: framework selector (dropdown of registered extractor keys),
    from_version input, to_version input, and optional flag checkboxes for
    --dry-run, --force, --force-extract, --force-llm
  - On submit, builds the CLI command `python -m migration_oracle.cli --framework
    <key> <from> <to> [flags]` and executes it as a subprocess
  - Streams subprocess stdout and stderr line-by-line into a Streamlit `st.code` block
    so the operator sees live pipeline output
  - Reports exit code: success (0) shown as green, non-zero as red with the last stderr line
  - Does NOT write to the graph or call any MCP tool function — the CLI subprocess handles
    everything downstream

PAGE 02 — Run Browser (`02_run_browser.py`) and what it does:
  - Calls `list_pipeline_runs()` on page load (with `st.cache_data(ttl=60)`)
  - Renders a selectbox labelled by "framework from→to" from the returned runs list
  - Shows three tabs below the selectbox: Raw MD, Filtered MD, Entities JSON
  - Raw MD tab: calls `get_artifact_content(framework, from_version, to_version, "raw_md")`
    and renders the content via `st.markdown()`
  - Filtered MD tab: same call with `artifact_type="filtered_md"`, rendered via `st.markdown()`
  - Entities JSON tab: same call with `artifact_type="entities_json"`, parsed and rendered
    via `st.json()` with `expanded=1`
  - If `list_pipeline_runs()` returns an empty list, shows `st.info("No pipeline runs found")`
    and does not render the selectbox or tabs
  - If `get_artifact_content()` returns `status != "ok"`, shows `st.error(f"Artifact not found")`
    in the affected tab

PAGE 03 — Rule Explorer (`03_rule_explorer.py`) and what it does:
  - Text input for a search query and a framework filter dropdown (All + each supported framework)
  - Calls `search_migration_knowledge(query, framework_filter, top_k=20)` from
    `migration_oracle.mcp.tools.search` on search submit
  - Renders results as expandable cards: rule title (from `title` property if present,
    else first 80 chars of statement), ruleType badge, changeType badge, source URL link
  - Within each card, if the result includes a `steps` list, renders an ordered step list
    showing summary, effort badge, and verificationHint for each step
  - Within each card, if the result includes a `scopes` list, renders scope/severity badges
  - Empty result: `st.info("No rules found for this query")`

PAGE 04 — Context Dashboard (`04_context_dashboard.py`) and what it does:
  - Text input for project_id, from_version, to_version, and framework selector
  - "Load / Create" button: calls `create_migration_context(project_id, from_version,
    to_version, framework, scanned_entities=[])` and stores `context_id` in `st.session_state`
  - Once a context is loaded, shows:
    - Status badge (in-progress / blocked / complete / partial / abandoned)
    - Two metrics: completed step count and skipped step count
    - "Pending Steps" table: calls `get_pending_steps(context_id)` and renders step rows
      with columns: summary, effort, automatable, scope, severity
  - "Mark Complete" button per step row: calls `update_step_status(context_id, step_id,
    outcome="completed")` and refreshes the pending steps table
  - "Skip" button per step row: shows a text_input for reason, then calls
    `update_step_status(context_id, step_id, outcome="skipped", reason=reason)` and refreshes
  - "Close Context" button (shown only when context is in-progress): opens a selectbox for
    final_status (complete / partial / abandoned) and a text_area for notes, then calls
    `close_migration_context(context_id, final_status, notes)`

PAGE 05 — Community (`05_community.py`) and what it does:
  - Top section: calls `get_community_insights(version_filter="", top_k=20)` on page load
    and renders insight cards showing statement, solution, votes, verified badge, source URL
  - "Vote Up" button per insight: calls `vote_insight(insight_id, direction="up")` and
    refreshes the insight list
  - Bottom section: expander titled "Submit New Insight" containing a form with fields:
    statement (text_area), solution (text_area), spring_boot_version or angular_version
    (text_input), affected_classes (text_input, comma-separated), source_url (text_input)
  - On submit: calls `submit_migration_insight(...)` from `migration_oracle.mcp.tools.community`
    and shows `st.success("Insight submitted")` or `st.error("Duplicate detected")` based on
    the returned status field

KEY BEHAVIORS:
TOOL_CALLS_IN_PROCESS — All calls to MCP tool functions are direct Python imports; the app
  never spawns an mcp subprocess or connects to a TCP socket.
FILESYSTEM_READ_NEVER — `get_artifact_content()` is the only path by which any page reads
  file content. No page calls `open()`, `Path.read_text()`, or any equivalent.
SUBPROCESS_ISOLATION — The pipeline trigger page uses `subprocess.Popen` with
  `stdout=PIPE, stderr=PIPE, text=True` and reads output line-by-line into the UI.
  It captures the exit code and surfaces it clearly. It never calls CLI code as a Python import.
CACHE_DATA_ON_RUNS — `list_pipeline_runs()` is wrapped in `@st.cache_data(ttl=60)` to avoid
  re-querying Neo4j on every Streamlit rerun.
SESSION_STATE_FOR_CONTEXT — `context_id` loaded on the Context Dashboard is stored in
  `st.session_state["context_id"]` so it persists across page rerenders without re-creating.
ERROR_SURFACE_NOT_RAISE — All calls to MCP tool functions are wrapped in try/except. Any
  exception is shown via `st.error()` — never raised to the Streamlit runtime, which would
  show a full traceback to the user.
EMPTY_STATE_FIRST — Every page that queries data handles the empty/no-result case with
  `st.info()` before rendering any widget that depends on that data.

INTEGRATION CONSTRAINTS:
- Import paths: `from migration_oracle.mcp.tools.artifacts import list_pipeline_runs,
  get_artifact_content` — these must not be reimplemented or mocked in app code
- Import paths: `from migration_oracle.mcp.tools.context import create_migration_context,
  get_pending_steps, update_step_status, close_migration_context`
- Import paths: `from migration_oracle.mcp.tools.search import search_migration_knowledge`
- Import paths: `from migration_oracle.mcp.tools.community import submit_migration_insight,
  get_community_insights, vote_insight`
- `streamlit>=1.35` must be in `pyproject.toml` under `[project.dependencies]`
- App entry point for `streamlit run` is `migration_oracle/streamlit_app/app.py`
- All pages must live under `migration_oracle/streamlit_app/pages/` using Streamlit's
  numeric-prefix naming convention: `01_pipeline_trigger.py` through `05_community.py`
- No direct Cypher queries in any page — all graph access goes through the tool functions
- No direct filesystem reads in any page
- CLI subprocess command: `[sys.executable, "-m", "migration_oracle.cli", "--framework",
  framework, from_version, to_version] + flags` — use `sys.executable`, not a bare `python`
```

---

## Gap Review — Post-Specify

After Claude Code generates `specs/006-streamlit-ui/spec.md`, check these items before running `/speckit.plan`:

```
Review the generated spec.md for 006-streamlit-ui and verify these items before we proceed
to planning:

GAP-001: In-process tool call contract
  The spec must state that Streamlit pages import tool functions directly from
  migration_oracle.mcp.tools.*, not through a running MCP server process.
  Confirm this is stated unambiguously — not left as "calls the MCP tool".

GAP-002: Filesystem read prohibition
  The spec must explicitly state that no page calls open(), Path.read_text(), or any
  filesystem read. All file content comes via get_artifact_content() only.
  If this constraint is present only in the artifacts page section and not as a global
  constraint, add it as a global constraint.

GAP-003: Pipeline trigger subprocess isolation
  The spec must state that the CLI is called as a subprocess (subprocess.Popen),
  not imported and called as Python code. The distinction matters: importing the CLI
  entry point would couple Streamlit's process to pipeline side effects.
  Confirm the subprocess approach and the sys.executable pattern are stated.

GAP-004: Error handling contract
  The spec must state that all MCP tool calls are wrapped in try/except and surfaces
  errors via st.error() — never as an uncaught exception. If this is missing, add it.

GAP-005: Cache TTL for list_pipeline_runs
  The spec must state that list_pipeline_runs() is cached with st.cache_data(ttl=60).
  If absent, add it to the Run Browser page behaviors.

GAP-006: Empty state handling
  Each page that queries data must have a defined empty-state behavior (st.info() call).
  Verify all five pages have explicit empty-state behavior defined. Add any that are missing.

GAP-007: Context Dashboard session_state pattern
  The spec must state that context_id is stored in st.session_state so it persists
  across rerenders. Verify this is explicit for the Context Dashboard page.

GAP-008: Step action buttons in context dashboard
  The spec must state what happens after "Mark Complete" and "Skip" button actions:
  specifically that get_pending_steps() is re-called to refresh the table.
  If this is vague ("refreshes the view"), make it concrete.

GAP-009: Community page vote behavior
  The spec must state that vote_insight() is called with direction="up" and that the
  insight list is re-fetched after the vote. Verify this is stated.

GAP-010: Return shape tolerance
  The spec must state that pages tolerate optional fields in tool return values
  (e.g., steps/scopes absent from search results for pre-redesign data) — showing
  nothing rather than crashing. Verify this defensive behavior is stated.

Fix any missing or vague items before running /speckit.plan.
```

---

## Command 2 — `/speckit.plan`

Paste this entire block:

```
/speckit.plan

Read specs/006-streamlit-ui/spec.md and produce the full planning artifacts for this spec.

Required artifacts to produce in specs/006-streamlit-ui/:

1. plan.md — File-by-file implementation plan with:
   - Python 3.11+ and streamlit>=1.35 as the runtime constraint
   - Complete directory tree for migration_oracle/streamlit_app/
   - Module-by-module responsibilities, import paths, and any shared helpers
   - pyproject.toml change required: add streamlit>=1.35 to [project.dependencies]
   - Entry point for `streamlit run migration_oracle/streamlit_app/app.py`
   - Note that all graph access goes through imported tool functions — no direct Cypher

2. data-model.md — All types and data structures used in the UI:
   - PipelineRun: the dict shape returned by list_pipeline_runs() per run entry
     { framework, from_version, to_version, raw_md_path, filtered_md_path, entities_json_path }
   - ArtifactContent: the dict shape returned by get_artifact_content()
     { status, content, path_resolved, framework, from_version, to_version, artifact_type }
   - PendingStep: the dict shape returned by get_pending_steps() per step
     { step_id, step_type, rule_id, summary, instruction, verification_hint, effort,
       automatable, scope, severity, requires, recipe_id }
   - CommunityInsight: the dict shape returned by get_community_insights() per insight
     { insight_id, statement, solution, votes, verified, source_url, created_at }
   - MigrationContextState: the fields stored in st.session_state on the Context Dashboard
     { context_id, project_id, from_version, to_version, framework, migration_status,
       completed_step_count, skipped_step_count }
   - SubprocessResult: { exit_code, stdout_lines, stderr_lines } for pipeline trigger output

3. contracts/006-streamlit-ui.md — Boundary rules:
   - Pages MUST import tool functions from migration_oracle.mcp.tools.*
   - Pages MUST NOT call open(), Path.read_text(), or any filesystem access
   - Pages MUST NOT construct or execute Cypher queries
   - Pages MUST NOT spawn or connect to an MCP server process
   - Pipeline trigger page MUST call CLI via subprocess, not import
   - All tool calls MUST be wrapped in try/except with st.error() on failure
   - st.cache_data(ttl=60) MUST wrap list_pipeline_runs() in the Run Browser

4. quickstart.md — How to run the Streamlit app locally:
   - Required env vars (NEO4J_URI, NEO4J_PASSWORD minimum)
   - `uv sync` or `pip install -e .` to install streamlit
   - `streamlit run migration_oracle/streamlit_app/app.py`
   - How to verify each page loads without error against a populated graph
   - How to trigger a dry-run pipeline run from the UI

5. research.md — Answer these questions:
   - Does streamlit>=1.35 support `st.cache_data` with ttl parameter? (yes — note version gate)
   - What is the correct way to stream subprocess output line-by-line in Streamlit
     without blocking the UI? (use st.empty() + Popen line iterator)
   - Do MCP tool functions decorated with @mcp.tool() carry side-effects that make
     them unsafe to import directly into a Streamlit process? Check if FastMCP's
     @mcp.tool() decorator is a pure decorator or registers globally on import.
     The answer determines whether the app imports tool functions directly or
     extracts the underlying functions to bypass the decorator.

Do not generate tasks.md — that comes from /speckit.tasks separately.
```

---

## Gap Review — Post-Plan

After Claude Code generates the plan artifacts, check these items before running `/speckit.tasks`:

```
Review the generated plan.md, data-model.md, contracts/, research.md, and quickstart.md
for 006-streamlit-ui and verify these items before running /speckit.tasks:

PLAN-GAP-001: streamlit dependency in pyproject.toml
  plan.md must explicitly state that streamlit>=1.35 is added to [project.dependencies]
  in pyproject.toml. If it only mentions it as a dev dependency, correct it — Streamlit
  is a runtime dependency for the streamlit_app module.

PLAN-GAP-002: FastMCP decorator import safety (research.md answer)
  research.md must answer whether @mcp.tool() has side effects on import. If the decorator
  registers tools on a global FastMCP instance at import time, the app must import the
  underlying unwrapped functions, not the decorated ones. The plan must state which pattern
  to use. If research.md does not address this, the plan cannot safely specify imports.

PLAN-GAP-003: shared helper module
  If multiple pages share the same pattern (e.g. wrapping tool calls in try/except,
  rendering step cards), plan.md should define a shared helper module at
  migration_oracle/streamlit_app/_helpers.py. If such patterns exist and no shared
  helper is planned, add it rather than duplicating logic across pages.

PLAN-GAP-004: app.py responsibilities
  plan.md must specify what app.py does: set_page_config, sidebar navigation, and
  whether it imports any tool functions or purely handles routing. If app.py imports
  from migration_oracle at module level (for sidebar display of graph status), state that
  explicitly — it affects startup time and error behavior if Neo4j is unreachable.

PLAN-GAP-005: subprocess streaming approach in research.md
  research.md must answer the streaming question with a concrete pattern:
  `process = subprocess.Popen(...); for line in process.stdout: placeholder.text(line)`.
  If only a high-level answer is given, ask for the concrete Streamlit pattern.

PLAN-GAP-006: data-model.md completeness
  data-model.md must list ALL five data structures from the requirement above.
  If SubprocessResult or MigrationContextState are missing, add them.

PLAN-GAP-007: session_state key names
  plan.md or data-model.md must define the exact st.session_state key names used
  across pages. At minimum: "context_id", "context_project_id", "context_status".
  Consistent key names prevent silent bugs when multiple pages share state.

PLAN-GAP-008: empty-page behavior in app.py
  quickstart.md or plan.md must state what happens when Streamlit loads app.py and
  Neo4j is unreachable. The pages that import tool functions at module level will fail
  on import. State whether the app should catch this at startup and show a warning,
  or whether pages should handle it lazily on first tool call.

PLAN-GAP-009: contracts completeness
  contracts/006-streamlit-ui.md must include all six boundary rules from the specify
  prompt. If any are missing, add them before proceeding to tasks.

Fix all gaps before running /speckit.tasks.
```

---

## Command 3 — `/speckit.tasks`

Paste this block:

```
/speckit.tasks

Read specs/006-streamlit-ui/spec.md, plan.md, data-model.md, and contracts/ and generate
tasks.md for the 006-streamlit-ui spec.

Task ordering requirements:
1. pyproject.toml update (add streamlit) must be the first task
2. Shared helper module (_helpers.py) must come before any page file that uses it
3. app.py (entry point, routing) must come before page files
4. Pages 01–05 may be implemented in parallel [P] after app.py exists
5. An integration smoke-test task must come last: run all five pages with a live graph
   and verify no import errors and no uncaught exceptions on page load

Mark tasks [P] where pages are independent and can be worked concurrently.
Include a test task for each page covering: page loads without error, empty-state renders
correctly, and the primary happy-path interaction (submit form / click button / etc.).
```

---

## Gap Review — Post-Tasks

After Claude Code generates `specs/006-streamlit-ui/tasks.md`, check these items before running `/speckit.implement`:

```
Review the generated tasks.md for 006-streamlit-ui and verify these items before running
/speckit.implement:

TASK-GAP-001: pyproject.toml task is first
  The first task must be adding streamlit>=1.35 to pyproject.toml and running uv sync.
  If any page file task appears before this, reorder.

TASK-GAP-002: shared helper task precedes page tasks
  If _helpers.py is planned, its task must appear before any page task that imports it.
  Check the dependency ordering.

TASK-GAP-003: [P] markers on page tasks
  Tasks for 01_pipeline_trigger.py, 02_run_browser.py, 03_rule_explorer.py,
  04_context_dashboard.py, and 05_community.py should all be marked [P] if they
  do not depend on each other's outputs. Verify each has [P].

TASK-GAP-004: test task per page
  There must be a test task for each page covering:
  - Page loads without raising an exception (mock Neo4j if needed)
  - Empty-state branch renders correctly (tool returns empty list)
  - Happy-path interaction (e.g. form submit, button click)
  If any page lacks a test task, add it.

TASK-GAP-005: subprocess streaming test
  There must be a test task specifically for the pipeline trigger page's subprocess
  streaming: verifies that stdout lines appear in the UI incrementally and that
  a non-zero exit code shows the error state. This is the highest-risk UI behavior
  and must not be skipped.

TASK-GAP-006: integration smoke test is last
  The final task must be a full integration smoke test: start the Streamlit app against
  a populated local Neo4j/Memgraph, navigate to all five pages, and verify no runtime
  errors. If this is missing, add it as the last task.

TASK-GAP-007: file paths are nested
  All file paths in tasks.md must use the full nested path:
  migration_oracle/streamlit_app/pages/01_pipeline_trigger.py — not just
  01_pipeline_trigger.py or pages/01_pipeline_trigger.py. Verify all paths.

TASK-GAP-008: FastMCP import pattern resolved
  If research.md concluded that @mcp.tool() decorators have side effects, there must
  be a task to extract and expose unwrapped callable functions for the Streamlit app.
  If this task is missing and the research conclusion required it, add it before the
  page implementation tasks.

Fix all gaps before running /speckit.implement.
```

---

## Command 4 — `/speckit.implement`

Paste this block:

```
/speckit.implement

Read specs/006-streamlit-ui/tasks.md and implement all tasks in order, respecting [P]
parallelism markers. Follow these constraints exactly:

1. All pages import tool functions from migration_oracle.mcp.tools.* — never reimplement
   them. Never call open() or Path.read_text() anywhere in the streamlit_app/ tree.

2. The pipeline trigger page uses subprocess.Popen with sys.executable — never a bare
   "python" string and never importing the CLI entry point as a Python module.

3. list_pipeline_runs() in the Run Browser is wrapped with @st.cache_data(ttl=60).

4. context_id on the Context Dashboard is stored and read from st.session_state["context_id"].

5. All calls to tool functions are inside try/except blocks. Exceptions are shown via
   st.error(str(e)) — never re-raised to the Streamlit runtime.

6. Every page handles the empty/no-result case before rendering any widget that depends
   on data (use st.info() for empty states).

7. app.py sets st.set_page_config(page_title="Migration Oracle", layout="wide") and
   does nothing else at module level that requires Neo4j connectivity.

After implementing each task, confirm the file exists at the correct path before
marking the task done.
```

---

## Recovery Prompts

Use these verbatim if implementation drifts:

### RECOVERY-01: Direct filesystem read found in a page

```
Do not call open(), Path.read_text(), or any equivalent in migration_oracle/streamlit_app/.
The only way to read artifact content is via get_artifact_content() imported from
migration_oracle.mcp.tools.artifacts. This constraint is in contracts/006-streamlit-ui.md.
Remove the filesystem read and replace it with a call to get_artifact_content().
```

### RECOVERY-02: CLI imported as Python module in pipeline trigger

```
Do not import migration_oracle.cli or call cli.main() from 01_pipeline_trigger.py.
The pipeline trigger must use subprocess.Popen to run the CLI in a separate process.
Use: process = subprocess.Popen([sys.executable, "-m", "migration_oracle.cli", ...],
stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
The subprocess pattern is required to isolate side effects and enable live log streaming.
```

### RECOVERY-03: Tool function call not wrapped in try/except

```
Every call to a function imported from migration_oracle.mcp.tools.* must be inside a
try/except block. On exception, call st.error(str(e)) — do not re-raise or let the
exception propagate to the Streamlit runtime. An uncaught exception in a page shows
a full traceback to the user and breaks the page layout.
```

### RECOVERY-04: context_id not stored in st.session_state

```
context_id on the Context Dashboard must be stored in st.session_state["context_id"]
after create_migration_context() returns. Do not store it as a local variable — local
variables reset on every Streamlit rerender. The session_state key must persist across
button clicks without re-calling create_migration_context() on every rerender.
```

### RECOVERY-05: list_pipeline_runs not cached

```
list_pipeline_runs() in 02_run_browser.py must be wrapped with @st.cache_data(ttl=60).
Without caching, the function queries Neo4j on every Streamlit rerender (every button
click, tab change, or widget interaction), creating unnecessary load on the graph.
Add: @st.cache_data(ttl=60) above the wrapper function that calls list_pipeline_runs().
```

### RECOVERY-06: Direct Cypher query found in a page

```
Do not import neo4j driver or write Cypher queries in any file under
migration_oracle/streamlit_app/. All graph access goes through the tool functions in
migration_oracle.mcp.tools.*. Remove the direct Cypher call and replace it with the
appropriate tool function call (search_migration_knowledge, get_community_insights, etc).
```

---

## What Success Looks Like

Run `streamlit run migration_oracle/streamlit_app/app.py` against a populated Neo4j/Memgraph.
Check each page:

1. **Pipeline Trigger** — Fill in `--framework spring-boot`, a from_version, to_version, check `--dry-run`. Submit. See live stdout lines appear in the code block. Exit code 0 shows green.
2. **Run Browser** — Selectbox shows at least one entry. Switching tabs shows markdown content (Raw MD, Filtered MD) and JSON tree (Entities JSON) without errors. An entry with a missing artifact shows `st.error()` in that tab — not a traceback.
3. **Rule Explorer** — Type a known class name (e.g. `WebSecurityConfigurerAdapter`). Results appear as expandable cards with step lists for rules that have MigrationStep nodes.
4. **Context Dashboard** — Enter a project_id and version range. Click "Load / Create". Status badge appears. Pending steps table renders. Click "Mark Complete" on a step — the step disappears from the table.
5. **Community** — Insight cards render. "Submit New Insight" form accepts input and shows `st.success()` on submit.

No page should raise an uncaught exception or show a Streamlit traceback at any point during the above flows.

# Spec 014 — Migration Lite Mode

**Status:** 🔲 Not started  
**Prerequisite:** `004-mcp-server` ✅  
**Spec ID:** `014-migration-lite-mode`

---

## WHAT it does

The MCP server reads a single environment variable (`MIGRATION_MODE`) at startup and, based
on its value, decorates either 23 functions or 4 functions with `@mcp.tool()`. In `lite` mode,
the full-only tools are never decorated — they exist as plain Python functions in their module
but are not part of the MCP tool table, so they are invisible to `tools/list` and uncallable.
`install_migration_skill` (itself a shared tool) installs the skill bundle that matches the
active mode.

## WHY it exists

The full four-loop harness carries 23 tools, graph-persisted session state, scope-tiered
querying, and OpenRewrite graph integration. For migrations with ≤ 150 known steps, that
overhead produces no benefit — the agent can hold the entire step set in memory, route to
the external openrewrite-runner skill by file count, and complete the upgrade in a single
session without any `MigrationContext` node. Lite mode gives teams a low-friction entry
point that starts working immediately without Neo4j state, without entity scanning, and
without installing the full skill bundle.

---

## How tool registration actually works (read before writing code)

Tools in this codebase are registered via the `@mcp.tool()` decorator applied directly to
each function, against a single shared `mcp` server instance. **Registration happens at
decoration time — the moment the module containing the decorated function is imported —
not via a separate explicit registration call.** This has one direct consequence for this
spec: a tool cannot be "registered then withheld." It is either decorated (and therefore in
the tool table) or it is not decorated at all.

Two of the nine tool files mix a shared (lite-eligible) tool and a full-only tool in the same
file:

| File | Shared tool | Full-only tool |
|---|---|---|
| `tools/upgrade.py` | `analyze_upgrade_path` | `build_recipe_plan`, `check_version_availability` |
| `tools/search.py` | `search_migration_knowledge` | `search_openrewrite_recipes` |

For these two files, the mode check must live **inside the module**, gating the decorator
itself — not in `server.py`, because importing the module at all would otherwise register
every decorated function in it regardless of mode.

All other tool files are single-mode and need no internal branching:

| File | Mode | Tools |
|---|---|---|
| `tools/paysafe.py` | shared | `resolve_paysafe_dependency_by_service_name` |
| `tools/install.py` | shared | `install_migration_skill` |
| `tools/context.py` | full-only | `create_migration_context`, `get_migration_contexts`, `get_pending_steps`, `update_step_status`, `get_steps_for_scope_tier`, `update_queried_entity`, `close_migration_context` |
| `tools/deprecation.py` | full-only | `resolve_deprecation`, `entity_evolution` |
| `tools/community.py` | full-only | `submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight` |
| `tools/artifacts.py` | full-only | `list_pipeline_runs`, `get_artifact_content` |
| `tools/schema.py` | full-only | `get_graph_schema`, `execute_custom_cypher` |

For single-mode files, `server.py` controls inclusion by **conditionally importing the
module**. An unimported module's decorators never run, so its tools never register. This
is safe specifically because these files contain no tool that lite mode needs — there is
no function in them that must survive a skipped import.

---

## Components

### `migration_oracle/mcp/config.py` — mode singleton

Reads and validates `MIGRATION_MODE` once at import time. Raises `ValueError` immediately if
the value is not `"full"` or `"lite"`. Exported as the module-level constant `MIGRATION_MODE`.
Every other module that needs the mode imports this constant — never reads `os.getenv`
directly. `config.py` imports only `os` — no dependency on `server.py` or any tool module,
to avoid circular imports (tool modules import `config`, and `tools/upgrade.py` /
`tools/search.py` also import `mcp` from `server.py`).

### `migration_oracle/mcp/server.py` — the `mcp` instance and conditional imports

Defines the single shared `mcp = FastMCP(...)` instance (or equivalent) that every tool
module imports and decorates against. After constructing `mcp`, the module body conditionally
imports the full-only tool files:

```python
from migration_oracle.mcp.config import MIGRATION_MODE
from mcp.server.fastmcp import FastMCP   # or whatever the actual SDK import is

mcp = FastMCP("PaysafeMigrationOracle")

# Always imported — both contain mode-internal guards (see upgrade.py / search.py below)
from migration_oracle.mcp.tools import upgrade      # noqa: F401  (decorator side effect)
from migration_oracle.mcp.tools import search        # noqa: F401
from migration_oracle.mcp.tools import paysafe        # noqa: F401
from migration_oracle.mcp.tools import install        # noqa: F401

if MIGRATION_MODE == "full":
    from migration_oracle.mcp.tools import context        # noqa: F401
    from migration_oracle.mcp.tools import deprecation     # noqa: F401
    from migration_oracle.mcp.tools import community       # noqa: F401
    from migration_oracle.mcp.tools import artifacts       # noqa: F401
    from migration_oracle.mcp.tools import schema          # noqa: F401

logger.info("Migration Oracle starting — mode=%s tools=%d", MIGRATION_MODE, len(mcp.list_tools()))
```

Import order matters: `mcp` must exist before any tool module is imported, since tool modules
do `from migration_oracle.mcp.server import mcp` at their own top level.

### `migration_oracle/mcp/tools/upgrade.py` — in-module mode guard

```python
from migration_oracle.mcp.config import MIGRATION_MODE
from migration_oracle.mcp.server import mcp

@mcp.tool()
def analyze_upgrade_path(...):
    ...

if MIGRATION_MODE == "full":

    @mcp.tool()
    def build_recipe_plan(...):
        ...

    @mcp.tool()
    def check_version_availability(...):
        ...
```

`analyze_upgrade_path` is decorated unconditionally — it is shared. `build_recipe_plan` and
`check_version_availability` are decorated only under the `if` guard, so in lite mode the
functions still exist as plain Python (importable for unit tests that call them directly,
e.g. in a future stateless-fallback path) but are never added to `mcp`'s tool table.

### `migration_oracle/mcp/tools/search.py` — in-module mode guard

Same pattern: `search_migration_knowledge` decorated unconditionally, `search_openrewrite_recipes`
decorated only when `MIGRATION_MODE == "full"`.

### `migration_oracle/mcp/tools/install.py` — mode-aware skill installation

`install_migration_skill` is shared and always decorated. Its **body** (not its registration)
branches on `MIGRATION_MODE` to install the bundle matching the active mode:

- **`full`:** installs `framework-migration` bundle (5 files)
- **`lite`:** installs `migration-lite` bundle (2 files) and `openrewrite-runner` bundle
  (3 files)

This branch is read at call time, not import time, since the tool may be invoked any time
after the server starts.

### `migration_oracle/mcp/skills/migration_lite_main.md` — lite skill

The migration-lite skill file served as an MCP resource at `skill://migration-lite/main`.
Defines three phases: Paysafe dependency resolution (Phase 1), single `analyze_upgrade_path`
call (Phase 2), and tier-partitioned execution with file-count routing (Phase 3).

### `migration_oracle/mcp/skills/openrewrite_main.md` (existing, relocated)

Already authored in project knowledge. Must be placed under `migration_oracle/mcp/skills/`
with the filename `openrewrite_main.md` so `install.py`'s bundle manifest can reference it
by a stable relative path.

---

## Key behaviors

**MODE_SINGLETON** — `MIGRATION_MODE` is read exactly once at import time from `config.py`.
No other module calls `os.getenv("MIGRATION_MODE")`. Tests that need a different mode
monkeypatch `migration_oracle.mcp.config.MIGRATION_MODE` directly, before any tool module
or `server.py` is imported or reloaded.

**INVALID_MODE_FAILS_FAST** — If `MIGRATION_MODE` is set to any value other than `"full"`
or `"lite"`, `config.py` raises `ValueError` at import time, before `server.py` constructs
the `mcp` instance or imports any tool module. The error message names the invalid value and
lists the two valid options.

**DECORATION_NOT_REGISTRATION** — There is no code path that "registers a tool" independently
of decorating it. Whether a tool is callable is entirely determined by whether its `@mcp.tool()`
decorator executed. Mode-gating means gating *whether the decorator runs*, via either module-
level import skipping (single-mode files) or an in-module `if` guard (mixed-mode files).

**LITE_TOOL_COUNT** — In lite mode, exactly 4 tools are present in `mcp.list_tools()`:
`analyze_upgrade_path`, `search_migration_knowledge`, `resolve_paysafe_dependency_by_service_name`,
`install_migration_skill`. Calling any other tool name (e.g. `create_migration_context`)
against a lite-mode server returns the MCP protocol's standard "unknown tool" error — there is
no custom handler for this, because the tool genuinely does not exist in the table.

**FULL_TOOL_COUNT** — In full mode, exactly 23 tools are present in `mcp.list_tools()`.

**MIXED_MODULE_GUARD_PLACEMENT** — In `tools/upgrade.py` and `tools/search.py`, the
`if MIGRATION_MODE == "full":` guard wraps only the full-only function definitions. The
shared function's `@mcp.tool()` decorator is never inside a conditional. This ordering must
not be inverted (i.e. never wrap the shared tool's decorator in a mode check).

**SINGLE_MODE_FILES_NEVER_PARTIALLY_IMPORTED** — `server.py` imports `context`, `deprecation`,
`community`, `artifacts`, and `schema` as whole modules only under `MIGRATION_MODE == "full"`.
There is no scenario in this spec where one tool from one of these files is needed in lite
mode — if that ever becomes true, the tool moves to a shared file rather than the import
being special-cased.

**INSTALL_MATCHES_MODE** — `install_migration_skill`'s body inspects `MIGRATION_MODE` at call
time. In full mode it writes exactly 5 files. In lite mode it writes exactly 5 files (2 for
migration-lite + 3 for openrewrite-runner). The return payload includes `mode`,
`installed_skills` (list of bundle names), and `installed_paths` (list of absolute paths
written).

**SKILL_FILES_BUNDLED** — All skill Markdown files installed by `install_migration_skill`
ship inside the repository under `migration_oracle/mcp/skills/`. The tool never fetches files
from the network or references external paths.

**NO_RECIPE_GRAPH_LOOKUP_IN_LITE** — The lite skill delegates OpenRewrite execution to the
openrewrite-runner skill. It does not call `search_openrewrite_recipes` — which is correct
by construction in lite mode, since that tool is not decorated and therefore not callable.
The skill text must not instruct the agent to call it.

**FILE_COUNT_THRESHOLD** — Steps affecting more than 10 files trigger openrewrite-runner
delegation. Steps affecting 1–10 files are handled by agent-codemod. Steps affecting 0 files
are informational only. The threshold is a constant in the skill file, not a server-side
parameter.

**TIER_ORDER** — The lite skill processes rules in strict tier order: breaking → behavioral →
CVE/mandatory. No rule from Tier 2 is presented to the user until all Tier 1 steps are
complete. No rule from Tier 3 is presented until all Tier 2 steps are complete.

**PAYSAFE_FIRST** — Phase 1 (Paysafe dependency resolution) always completes before Phase 2
(graph call). If zero `com.paysafe` dependencies are found, Phase 1 emits "No Paysafe
dependencies detected." and immediately proceeds to Phase 2. Phase 1 is never skipped.

**GAP_FILL_CONDITIONAL** — `search_migration_knowledge` is called in Phase 3 only for rules
where both `solution` is null/empty and `steps[]` is empty or absent. Maximum calls: 1
(Phase 2 fallback) + N (gap fill, N = count of stepless/solutionless rules).

**STARTUP_LOG** — On server start, after all conditional imports complete, a single INFO-level
log line states the mode and tool count: `"Migration Oracle starting — mode={mode} tools={count}"`.
This must be logged after the conditional imports, not before, so the count is accurate.

---

## Error cases

**`MIGRATION_MODE` unset** — defaults to `"full"`. No error raised.

**`MIGRATION_MODE=lite` but `FINDIT_AUTH_TOKEN` missing** — `resolve_paysafe_dependency_by_service_name`
returns `subStatus="auth_error"` per its existing contract — this tool's body is unaffected by
the registration mechanism change. The lite skill notes the error per dependency, emits the
row as unresolved, and continues. Phase 1 never halts on individual dependency resolution
failures.

**`analyze_upgrade_path` returns empty `rules[]`** — `search_migration_knowledge` is called
once with a fallback query. If that also returns no hits, Phase 3 emits "No migration steps
found for this version range." and proceeds to Phase 4 (summary). No exception is raised.

**Skill source file missing** — `install_migration_skill` raises `FileNotFoundError` with the
missing path. The return payload is `{"status": "error", "message": "..."}`. No partial
install is left on disk.

**Target directory not writable** — `install_migration_skill` raises `PermissionError`. Same
error return shape. No partial install.

**Agent calls a full-only tool against a lite server** — the MCP transport layer returns its
standard unknown-method error. This is not something `server.py` or any tool module catches
or translates — it is the natural consequence of the tool never having been decorated.

---

## Integration constraints

- `config.py` must be importable with no side effects beyond setting `MIGRATION_MODE`. It
  must not import from `server.py` or any tool module (no circular imports).
- `server.py` must construct the `mcp` instance **before** importing any tool module, since
  every tool module does `from migration_oracle.mcp.server import mcp` at its own top level.
- `tools/upgrade.py` and `tools/search.py` are the only files containing an in-module
  `if MIGRATION_MODE == "full":` guard. No other tool file should need one — if a future
  change makes another file mixed-mode, prefer splitting it into two files over adding a
  third in-module guard, to keep the pattern rare and obvious.
- The 4 shared tools retain their existing signatures and return shapes. No parameter is
  added or removed from `analyze_upgrade_path`, `search_migration_knowledge`,
  `resolve_paysafe_dependency_by_service_name`, or `install_migration_skill`.
- `install_migration_skill`'s return shape gains two new fields (`mode`, `installed_skills`)
  alongside the existing `status`, `target`, `installed_paths`, and `message`. This is
  additive and backward-compatible.
- Skill files are plain Markdown. No build step, no template rendering, no dynamic content.
  What is committed is what is installed.
- The `openrewrite-runner` skill files (`openrewrite_main.md`, `openrewrite_recipe_catalog.md`,
  `openrewrite_examples.md`) already exist in project knowledge and must be moved into
  `migration_oracle/mcp/skills/` with names matching the bundle manifest in `install.py`.

---

## Completion gate

- [ ] `MIGRATION_MODE=lite python -c "from migration_oracle.mcp.config import MIGRATION_MODE; assert MIGRATION_MODE == 'lite'"` exits 0
- [ ] `MIGRATION_MODE=bad python -m migration_oracle.mcp.server` exits non-zero, error names the invalid value and valid options, and occurs before `mcp.list_tools()` would be callable
- [ ] Server started with `MIGRATION_MODE=lite`: `mcp.list_tools()` returns exactly the 4 shared tool names, no others
- [ ] Server started with `MIGRATION_MODE=full`: `mcp.list_tools()` returns exactly 23 tool names
- [ ] In lite mode, `build_recipe_plan`, `check_version_availability`, and `search_openrewrite_recipes` are absent from `mcp.list_tools()` even though their defining modules (`upgrade.py`, `search.py`) were imported
- [ ] Calling `create_migration_context` against a lite-mode server returns the MCP unknown-tool error, not a Python exception or business-logic error
- [ ] `install_migration_skill` in full mode writes exactly 5 files to the target directory
- [ ] `install_migration_skill` in lite mode writes exactly 5 files (2 + 3) to the target directory
- [ ] Return payload from `install_migration_skill` includes `mode`, `installed_skills`, `installed_paths`
- [ ] All 5 new/relocated skill source files are present under `migration_oracle/mcp/skills/` and pass a Markdown lint check
- [ ] `pytest tests/mcp/test_feature_flag.py` passes (config validation, mixed-module guard behavior, single-module import skipping)
- [ ] `pytest tests/mcp/test_install_skill.py` passes (install tests for both modes)
- [ ] Startup log line emitted in both modes with correct tool count, logged after conditional imports complete
# Research — 014 Migration Lite Mode

Spikes, tech choices, and open questions resolved before planning begins.

---

## R-001 — Where to put the mode constant and why `config.py`

**Question:** Should `MIGRATION_MODE` live in `server.py`, in a new `config.py`, or be
read inline wherever it's needed?

**Decision:** New `migration_oracle/mcp/config.py`.

**Reasoning:** `server.py` is already the largest module and owns transport, tool registration,
and resource registration. Adding env-var parsing there makes the startup sequence harder to
test in isolation. `install.py` also needs the mode for bundle selection — if both modules
read `os.getenv` independently there is no single place to mock in tests and no single place
to add the validation guard.

A `config.py` singleton that raises at import time (not at first call) means the invalid-mode
error surfaces immediately on server start, before any tool is registered. This is the same
pattern already used for `NEO4J_URI` and `FINDIT_AUTH_TOKEN` in the existing `config.py`
under the foundations spec.

**Confirmed:** No circular import risk. `config.py` imports only `os`. `server.py` imports
`config`. Tool modules do not import `config` — they receive no mode-dependent branching.

---

## R-002 — Decorator-based registration: what "not registered" actually means here

**Question:** Does the MCP SDK support conditional registration, or do we need a different
pattern (e.g. returning an error from the handler)?

**Finding — this codebase's actual pattern is decorator-based, not call-based.** Every tool
is defined as `@mcp.tool()` on top of a function, against one shared `mcp = FastMCP(...)`
instance constructed in `server.py`. There is no separate `server.add_tool(fn)` call site
to branch on — **the decorator itself is the registration**, and it executes the instant
Python imports the module containing it. This is a materially different mechanism from an
SDK that exposes an explicit, late-bound registration call, and it changes what "conditional
registration" can mean:

- You cannot decide *after* a module is imported whether its decorated functions are
  registered — importing the module already ran every decorator in it.
- You *can* decide whether to import a module at all (skips every tool inside it), or branch
  with a plain `if` statement around specific decorator applications *inside* the module
  before it's imported.

**Decision:** Two-tier approach based on whether a file is single-mode or mixed-mode.

- **Single-mode files** (`context.py`, `deprecation.py`, `community.py`, `artifacts.py`,
  `schema.py` — all full-only; `paysafe.py`, `install.py` — both shared): `server.py`
  conditionally imports the whole module. `if MIGRATION_MODE == "full": from ...tools import context`.
  Skipping the import means every decorator in that file never runs, so none of its tools
  appear in `mcp.list_tools()`.

- **Mixed-mode files** (`upgrade.py`: shared `analyze_upgrade_path` + full-only
  `build_recipe_plan`/`check_version_availability`; `search.py`: shared
  `search_migration_knowledge` + full-only `search_openrewrite_recipes`): the module is
  *always* imported (it contains a shared tool), so the mode check must live **inside** the
  module, wrapping only the full-only function's decorator:

  ```python
  @mcp.tool()
  def analyze_upgrade_path(...): ...      # always decorated

  if MIGRATION_MODE == "full":
      @mcp.tool()
      def build_recipe_plan(...): ...     # decorated only in full mode
  ```

**What "not registered" returns to a caller:** regardless of which of the two mechanisms
withheld a tool, the net effect is identical — the tool name is simply absent from
`mcp.list_tools()` / the `tools/list` MCP method response. A client calling a name that was
never decorated gets the MCP protocol's own unknown-tool error. No custom handler, no stub,
no business-logic-level rejection. This was correct in the original research note even
though the registration mechanism description was wrong — the *external* behavior (protocol-
level error, not a Python exception bubbling up) still holds under the decorator model.

**Confirmed:** `mcp.list_tools()` in lite mode returns exactly 4 entries: the two
unconditionally-decorated functions from the mixed-mode files, plus the two tools from the
shared single-mode files (`paysafe.py`, `install.py`).

---

## R-003 — Skill file storage: committed vs generated vs fetched

**Question:** Should skill Markdown files be committed to the repo, generated at build time,
or fetched from a remote source (S3, CDN, GitHub raw)?

**Decision:** Committed to the repository under `migration_oracle/mcp/skills/`.

**Reasoning:**

- The existing framework-migration skills are already committed under `skills/` and served
  as MCP resources. Consistency with the existing pattern is the overriding argument.
- Fetching at install time introduces a network dependency that breaks offline and air-gapped
  environments. The `FINDIT_AUTH_TOKEN` already causes pain in restricted networks — no
  additional external dependency.
- Generated at build time adds a CI step with no benefit: the content is stable Markdown
  authored by humans and reviewed in PRs. Generation would just copy it anyway.
- The three openrewrite skill files (`openrewrite_main.md`, `openrewrite_recipe_catalog.md`,
  `openrewrite_examples.md`) are already in the project knowledge. They need to be placed
  at `migration_oracle/mcp/skills/` with the exact filenames referenced in the bundle
  manifest. This is a one-time file move, not a code change.

**File manifest after the move:**

```
migration_oracle/mcp/skills/
├── framework_migration_main.md         # existing
├── framework_migration_scanning.md     # existing
├── framework_migration_version_map.md  # existing
├── framework_migration_plan_format.md  # existing
├── framework_migration_rollback.md     # existing
├── migration_lite_main.md              # new — authored in this spec
├── openrewrite_main.md                 # moved from project knowledge
├── openrewrite_recipe_catalog.md       # moved from project knowledge
└── openrewrite_examples.md             # moved from project knowledge
```

---

## R-004 — `install_migration_skill` return shape change: backward compatibility

**Question:** Adding `mode` and `installed_skills` to the return payload — is this a
breaking change for existing callers?

**Decision:** Not a breaking change. Additive fields only.

**Reasoning:** MCP tool responses are JSON objects. Adding new keys to a JSON object is
backward-compatible for any client that doesn't validate against a strict schema.
The existing fields (`status`, `target`, `installed_paths`, `message`) are unchanged.
The two new fields (`mode`, `installed_skills`) are additive.

The only risk would be a client that pattern-matches on the exact set of keys and rejects
unknown fields. No such client exists in this codebase — the Streamlit UI, Claude Code, and
Cursor all consume MCP tool responses permissively.

**No version bump required.** Document the new fields in `mcp-tools-skills-prompts.md`.

---

## R-005 — Testing strategy for decorator-time, mode-conditional registration

**Question:** How do we unit-test that the server ends up with exactly N tools per mode,
given that registration happens via decorators at import time rather than an explicit call
we can intercept?

**Decision:** Force a clean re-import of `server.py` and every tool module under a patched
`MIGRATION_MODE`, then inspect the shared `mcp` instance's tool table. This must reload
`upgrade.py` and `search.py` specifically, since their internal `if MIGRATION_MODE == "full":`
guard is evaluated once, at their own import time — reloading `server.py` alone does not
re-run their module bodies if they're already in `sys.modules`.

**Approach:**

```python
# tests/mcp/test_feature_flag.py

import importlib
import sys
import pytest

TOOL_MODULES = [
    "migration_oracle.mcp.tools.upgrade",
    "migration_oracle.mcp.tools.search",
    "migration_oracle.mcp.tools.paysafe",
    "migration_oracle.mcp.tools.install",
    "migration_oracle.mcp.tools.context",
    "migration_oracle.mcp.tools.deprecation",
    "migration_oracle.mcp.tools.community",
    "migration_oracle.mcp.tools.artifacts",
    "migration_oracle.mcp.tools.schema",
]

def _fresh_server(mode: str):
    """Force every relevant module to be re-imported from scratch under the given mode."""
    import migration_oracle.mcp.config as cfg
    cfg.MIGRATION_MODE = mode

    for name in TOOL_MODULES + ["migration_oracle.mcp.server"]:
        sys.modules.pop(name, None)        # evict — plain reload() is not enough,
                                            # since `mcp` itself must be rebuilt too

    import migration_oracle.mcp.server as srv
    return srv.mcp

def test_lite_registers_4_tools():
    mcp = _fresh_server("lite")
    names = {t.name for t in mcp.list_tools()}
    assert names == {
        "analyze_upgrade_path",
        "search_migration_knowledge",
        "resolve_paysafe_dependency_by_service_name",
        "install_migration_skill",
    }

def test_full_registers_23_tools():
    mcp = _fresh_server("full")
    assert len(mcp.list_tools()) == 23

def test_mixed_module_full_only_tools_absent_in_lite():
    mcp = _fresh_server("lite")
    names = {t.name for t in mcp.list_tools()}
    assert "build_recipe_plan" not in names
    assert "check_version_availability" not in names
    assert "search_openrewrite_recipes" not in names

def test_invalid_mode_raises_before_server_builds():
    import migration_oracle.mcp.config as cfg
    sys.modules.pop("migration_oracle.mcp.server", None)
    cfg.MIGRATION_MODE = "enterprise"
    with pytest.raises(ValueError, match="MIGRATION_MODE"):
        import migration_oracle.mcp.server  # noqa: F401
```

**Risk — module eviction via `sys.modules.pop`, not `importlib.reload`:** plain
`importlib.reload(server)` is insufficient here because `upgrade.py` and `search.py` may
already be cached in `sys.modules` from a previous test in the same process, and reloading
only `server.py` does not force their internal `if MIGRATION_MODE == "full":` block to
re-evaluate. The test helper must evict all affected modules from `sys.modules` before
re-importing, so every decorator (including the in-module guarded ones) re-runs against a
freshly-constructed `mcp` instance.

**Risk — import-time side effects:** if any tool module does anything beyond defining
functions and decorating them (e.g. opening a graph connection at import time), repeated
eviction-and-reimport in a single test process will repeat that side effect. Confirm tool
modules remain side-effect-free at import (graph connections are lazy, established inside
function bodies via a connection helper) before relying on this test pattern.

**Risk — test ordering and shared `mcp` global:** because `mcp` is a module-level singleton
inside `server.py`, and that module is evicted and rebuilt per test, this pattern only works
if no other test holds a stale reference to a previous `mcp` instance across test functions.
Use a fixture that evicts and rebuilds per test, not a session-scoped fixture.

---

## R-006 — `search_migration_knowledge` call budget in lite mode

**Question:** The spec says `search_migration_knowledge` is called at most `1 + N` times.
What is the realistic N for a populated Spring Boot 3.5 → 4.1 graph?

**Finding:** Based on the 117-step maximum across the largest known version range, and given
that well-populated rules have `MigrationStep` nodes with `instruction` populated, the
expected N is 0–5 in practice. Rules without steps are those populated before the redesign
(`actionStep` blob style) — these will decrease over time as re-extraction runs.

**Decision:** No hard cap on gap-fill calls in the spec. The conditional already naturally
limits calls to rules with no steps and no solution. A future optimization could batch
multiple gap-fill queries into one `search_migration_knowledge` call, but this is out of
scope for this spec.

---

## R-007 — File-count threshold: 10 files — is it the right number?

**Question:** The routing threshold (> 10 files → OpenRewrite delegation) was established
in earlier design discussions. Should it be configurable or hardcoded?

**Decision:** Hardcoded at 10 in the skill file. Not a server parameter.

**Reasoning:** The threshold is a skill-level concern, not a server-level concern. The MCP
server's job is to register tools; the skill's job is to decide how to use them. Making this
a server parameter would require adding a new tool or extending an existing one — complexity
with no benefit for a value unlikely to change across teams.

If a team needs a different threshold, they amend `migration_lite_main.md` in their
installation. The skill file is plain Markdown committed to their agent's skills directory,
so this is a one-line edit.

**Open question for future:** Should the threshold be an optional parameter on the migration
session invocation (e.g. `start_migration_lite(file_count_threshold=5)`)? Deferred to a
future spec if demand arises.

---

## R-008 — Startup log format

**Question:** What logging infrastructure exists in the server? Does it use Python `logging`,
print statements, or structured JSON logs?

**Finding:** The existing server uses Python `logging` at module level. The transport
selection already emits an INFO log on startup. No structured JSON log format is enforced.

**Decision:** Use `logger.info("Migration Oracle starting — mode=%s tools=%d", mode, count)`
immediately after all tools are registered. This integrates with the existing log pattern
and is trivially grep-able in CI.

---

## R-009 — `openrewrite-runner` skill: reference or execute?

**Question:** When the lite skill delegates to `openrewrite-runner`, does it load the skill
and transfer control, or does it describe the handoff and wait for the user to invoke the
runner separately?

**Decision:** The lite skill loads `skill://openrewrite-runner/main` inline and passes
context. The agent running migration-lite is expected to also have openrewrite-runner
available (it is installed by `install_migration_skill` in lite mode). There is no separate
user invocation step.

**Implication for `install_migration_skill`:** In lite mode, both `migration-lite` and
`openrewrite-runner` must be installed together. They are not independently selectable.
This is enforced by the bundle manifest — lite mode always installs both. The `install.py`
implementation does not support installing only one of the two lite bundles.

---

## R-010 — What happens if `MIGRATION_MODE=lite` but the openrewrite-runner skill is not installed?

**Question:** The server is in lite mode, but the agent's skill directory does not have
`openrewrite-runner`. What does the lite skill do when the file-count gate fires?

**Decision:** The lite skill emits a warning card and routes to agent-codemod regardless of
file count. It does not fail the session.

**Card text:**
```
⚠ openrewrite-runner skill not found in agent skill directory.
  Run install_migration_skill() to install it.
  Falling back to agent-codemod for this step (N files affected).
```

**Implication for spec:** Add this as a documented edge case in the skill file (Phase 3,
OpenRewrite route section). Not a server-side concern — the server cannot detect whether
a skill is installed in the agent's directory.

---

## R-011 — Why `upgrade.py` and `search.py` keep an in-module guard instead of being split into separate files

**Question:** Given that mixed-mode files require an internal `if MIGRATION_MODE == "full":`
guard — a pattern not needed anywhere else in the codebase — would it be cleaner to split
each into two files (e.g. `upgrade.py` + `upgrade_full.py`) so every file becomes single-mode
and `server.py` can use uniform whole-module import skipping everywhere?

**Decision:** Keep the in-module guard. Do not split the files for this spec.

**Reasoning for keeping them combined:**

- `analyze_upgrade_path` and `build_recipe_plan` share private helpers within `upgrade.py`
  today (e.g. version resolution, Cypher parameter construction) per the existing module
  layout described in `mcp-tools-skills-prompts.md` (`normalize_entities()` lives in
  `upgrade.py` and is used by both). Splitting the file means either duplicating those
  helpers or introducing a third shared-internals module — more surface area for a change
  whose actual goal is a feature flag, not a refactor.
- The two mixed-mode files are a small, fixed, enumerable set (exactly two). The spec's
  integration constraints section already states the pattern should stay rare — if a third
  file becomes mixed-mode in a future change, that's the trigger to revisit whether splitting
  pays for itself, not before.
- A reviewer reading `upgrade.py` top-to-bottom sees the mode boundary explicitly, in the
  same file, right where the full-only tool is defined. A split into `upgrade.py` /
  `upgrade_full.py` would require knowing the file-naming convention to find out which tools
  are gated at all — the in-module `if` is more discoverable, not less.

**Reasoning against splitting (cost side):**

- Splitting touches existing, working, full-mode-only code (`build_recipe_plan`,
  `search_openrewrite_recipes`) purely to satisfy a structural preference, increasing the
  diff size and review surface for a change that should be additive and low-risk.
- Any existing imports of `upgrade.build_recipe_plan` from tests or other internal callers
  (e.g. `framework-migration` skill's Loop III referencing `build_recipe_plan` directly in
  prose, even if not in code) would need updating to a new module path.

**Confirmed via R-005's test design:** the eviction-and-reimport test pattern already handles
mixed-mode files correctly by evicting them from `sys.modules` before reimport, so there is no
testing-side pressure to split either — both patterns are equally testable.

**Revisit trigger:** if a third tool file becomes mixed-mode, or if `upgrade.py` grows enough
that the in-module guard becomes hard to locate visually, open a follow-up spec to split files
at that point rather than retrofitting now.
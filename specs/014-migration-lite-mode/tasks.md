# Tasks — 014 Migration Lite Mode

**Input documents:** `spec.md`, `research.md` (this spec has no `plan.md`, `data-model.md`,
or `contracts/` — all file paths and decisions below are derived directly from those two files)

**Execution rule:** Complete tasks in order. `[P]` marks tasks with no dependency on any
unfinished task in this list — they may be done in any order relative to each other, but
never before their numbered prerequisites. Do not skip a task because it looks small;
each one maps to a specific behavior or completion-gate item in `spec.md`.

---

## Phase A — Foundation (no dependents may start before this completes)

- [ ] **T001** Create `migration_oracle/mcp/config.py` with the `MIGRATION_MODE` singleton.
  Read `os.getenv("MIGRATION_MODE", "full")`, lowercase and strip it, raise `ValueError`
  naming the invalid value and the two valid options if it is not `"full"` or `"lite"`.
  No other imports in this file beyond `os`.
  *(spec.md → Components → config.py; behavior MODE_SINGLETON, INVALID_MODE_FAILS_FAST)*

- [ ] **T002** Locate the existing `mcp = FastMCP(...)` (or equivalent) instantiation in
  `server.py`. Confirm it occurs before any `from migration_oracle.mcp.tools import ...`
  line. If any tool import currently precedes the `mcp` construction, move the construction
  above it. This ordering is required because every tool module does
  `from migration_oracle.mcp.server import mcp` at its own top level.
  *(spec.md → Components → server.py; integration constraint on import order)*

---

## Phase B — Mixed-mode file guards `[depends on T001]`

- [ ] **T003** In `migration_oracle/mcp/tools/upgrade.py`: add
  `from migration_oracle.mcp.config import MIGRATION_MODE` near the top. Leave
  `analyze_upgrade_path`'s `@mcp.tool()` decorator unconditional. Wrap the existing
  `build_recipe_plan` and `check_version_availability` function definitions (decorator
  included) inside `if MIGRATION_MODE == "full":`. Do not move, rename, or alter the body
  of any of the three functions.
  *(spec.md → MIXED_MODULE_GUARD_PLACEMENT; research.md R-002, R-011)*

- [ ] **T004** In `migration_oracle/mcp/tools/search.py`: same pattern as T003.
  `search_migration_knowledge`'s decorator stays unconditional. Wrap
  `search_openrewrite_recipes`'s definition (decorator included) inside
  `if MIGRATION_MODE == "full":`.
  *(spec.md → MIXED_MODULE_GUARD_PLACEMENT; research.md R-002, R-011)*

- [ ] **T005 [P]** Grep the rest of `migration_oracle/mcp/tools/` for any other file
  containing more than one `@mcp.tool()` definition. Confirm the only two mixed-mode files
  are `upgrade.py` and `search.py` as stated in spec.md's registration table. If a third
  mixed-mode file is found, stop and flag it — do not silently apply the same pattern; the
  spec's integration constraints say a third mixed-mode file is a trigger to reconsider the
  approach (research.md R-011), not to extend it automatically.
  *(spec.md → integration constraints; research.md R-011, "Revisit trigger")*

---

## Phase C — Server-level conditional imports `[depends on T002, T003, T004]`

- [ ] **T006** In `server.py`, after the `mcp` instance is constructed, add the
  unconditional imports for the four shared-tool modules:
  `upgrade`, `search`, `paysafe`, `install` (each imported as a module, e.g.
  `from migration_oracle.mcp.tools import upgrade  # noqa: F401`). These run regardless of
  mode because each either is fully shared (`paysafe`, `install`) or contains a shared tool
  guarded internally (`upgrade`, `search`, per T003/T004).
  *(spec.md → Components → server.py)*

- [ ] **T007** In `server.py`, add the full-mode-only conditional import block:
  ```python
  if MIGRATION_MODE == "full":
      from migration_oracle.mcp.tools import context      # noqa: F401
      from migration_oracle.mcp.tools import deprecation   # noqa: F401
      from migration_oracle.mcp.tools import community     # noqa: F401
      from migration_oracle.mcp.tools import artifacts      # noqa: F401
      from migration_oracle.mcp.tools import schema         # noqa: F401
  ```
  This must come after T006's unconditional imports in file order (not load-bearing for
  correctness, but matches the order documented in spec.md's server.py example).
  *(spec.md → Components → server.py; SINGLE_MODE_FILES_NEVER_PARTIALLY_IMPORTED)*

- [ ] **T008** Add the startup log line immediately after the conditional import block from
  T007: `logger.info("Migration Oracle starting — mode=%s tools=%d", MIGRATION_MODE,
  len(mcp.list_tools()))`. Confirm `logger` already exists in `server.py` (reuse existing
  logging setup — do not introduce a second logging configuration).
  *(spec.md → STARTUP_LOG)*

---

## Phase D — Skill file relocation `[P, no dependency on A/B/C]`

- [ ] **T009 [P]** Create `migration_oracle/mcp/skills/migration_lite_main.md` containing
  the full migration-lite skill content (three-phase flow: Paysafe resolution → single
  `analyze_upgrade_path` call → tier-partitioned execution with file-count routing to
  agent-codemod or openrewrite-runner delegation). This is new content authored for this
  spec, not a relocation.
  *(spec.md → Components → migration_lite_main.md)*

- [ ] **T010 [P]** Move `openrewrite_main.md` from wherever it currently sits in project
  knowledge into `migration_oracle/mcp/skills/openrewrite_main.md`. Filename must match
  exactly — the install bundle manifest (T013) references it by this relative path.
  *(spec.md → Components → openrewrite_main.md; integration constraints)*

- [ ] **T011 [P]** Move `openrewrite_recipe_catalog.md` and `openrewrite_examples.md` into
  `migration_oracle/mcp/skills/` alongside T010's file, same filenames.
  *(spec.md → integration constraints, "openrewrite-runner skill files")*

- [ ] **T012 [P]** Run a Markdown lint pass (e.g. `markdownlint` or equivalent already used
  in this repo) against all five files from T009–T011 plus the five existing
  framework-migration skill files. Fix any lint failures introduced by the move (broken
  relative links, heading level skips).
  *(spec.md → completion gate, "pass a Markdown lint check")*

---

## Phase E — `install_migration_skill` bundle logic `[depends on T009, T010, T011]`

- [ ] **T013** In `migration_oracle/mcp/tools/install.py`, define the `SKILL_BUNDLES` dict
  with three keys — `"framework-migration"` (5 existing files), `"migration-lite"` (2 files:
  `migration_lite_main.md` → `migration-lite/SKILL.md`, plus
  `framework_migration_version_map.md` → `migration-lite/references/version-map.md`), and
  `"openrewrite-runner"` (3 files from T010/T011, mapped to
  `openrewrite-runner/SKILL.md` and `openrewrite-runner/references/*.md`).
  *(spec.md → Components → install.py)*

- [ ] **T014** Define `MODE_BUNDLES = {"full": ["framework-migration"], "lite":
  ["migration-lite", "openrewrite-runner"]}` in the same file.
  *(spec.md → INSTALL_MATCHES_MODE)*

- [ ] **T015** Update `install_migration_skill`'s body (not its decorator — the tool stays
  unconditionally registered) to read `MIGRATION_MODE` at call time, resolve
  `MODE_BUNDLES[MIGRATION_MODE]`, and copy every file listed in `SKILL_BUNDLES` for each
  resolved bundle name to the target directory. Preserve existing target-directory resolution
  logic (`auto`/`cursor`/`claude-code` detection) — this task only changes which files get
  copied, not where.
  *(spec.md → INSTALL_MATCHES_MODE, SKILL_FILES_BUNDLED)*

- [ ] **T016** Extend the tool's return payload to add `mode` (the resolved `MIGRATION_MODE`
  string) and `installed_skills` (the list of bundle names from `MODE_BUNDLES[MIGRATION_MODE]`)
  alongside the existing `status`, `target`, `installed_paths`, `message` fields. Do not
  remove or rename any existing field.
  *(spec.md → INSTALL_MATCHES_MODE; integration constraints, "additive and backward-compatible")*

- [ ] **T017** Add explicit error handling: if any source file in a bundle is missing, raise
  `FileNotFoundError` naming the missing path, and ensure no partial set of files from that
  bundle is left on disk (clean up any files already copied in the same call before
  re-raising, or stage to a temp directory and move atomically — either approach satisfies
  the "no partial install" requirement).
  *(spec.md → Error cases, "Skill source file missing")*

- [ ] **T018** Add explicit error handling for a non-writable target directory: catch the
  underlying OS error and re-raise as `PermissionError` with the target path included in the
  message. Same no-partial-install guarantee as T017.
  *(spec.md → Error cases, "Target directory not writable")*

---

## Phase F — Tests `[depends on all of A–E]`

- [ ] **T019** Write `tests/mcp/test_feature_flag.py` with the module-eviction test helper
  from research.md R-005 (`sys.modules.pop` on all nine tool modules plus `server`, not
  `importlib.reload`). Implement `test_lite_registers_4_tools`,
  `test_full_registers_23_tools`, and `test_mixed_module_full_only_tools_absent_in_lite`
  exactly as specified in R-005.
  *(spec.md → completion gate, "pytest tests/mcp/test_feature_flag.py")*

- [ ] **T020** In the same file, add `test_invalid_mode_raises_before_server_builds`,
  asserting the `ValueError` fires on `config.py` import / mode assignment and before
  `server.py`'s module body can construct `mcp` or attempt any tool import.
  *(spec.md → INVALID_MODE_FAILS_FAST)*

- [ ] **T021 [P]** Write `tests/mcp/test_install_skill.py` covering: full mode writes
  exactly 5 files; lite mode writes exactly 5 files (2 + 3); the return payload contains
  `mode` and `installed_skills` with correct values in both modes; a missing source file
  raises `FileNotFoundError` with no partial install; a non-writable target raises
  `PermissionError` with no partial install.
  *(spec.md → completion gate, "pytest tests/mcp/test_install_skill.py"; T015–T018)*

- [ ] **T022 [P]** Add a test (in either file from T019 or T021) that calls a known
  full-only tool name (e.g. `create_migration_context`) against a lite-mode `mcp` instance
  and asserts the MCP protocol's standard unknown-tool error is raised — not a Python
  `AttributeError`, `KeyError`, or any application-level exception.
  *(spec.md → Error cases, "Agent calls a full-only tool against a lite server")*

---

## Phase G — Manual / environment-level verification `[depends on all of A–F]`

- [ ] **T023** Run `MIGRATION_MODE=lite python -c "from migration_oracle.mcp.config import
  MIGRATION_MODE; assert MIGRATION_MODE == 'lite'"` and confirm exit code 0.

- [ ] **T024** Run `MIGRATION_MODE=bad python -m migration_oracle.mcp.server` and confirm:
  non-zero exit, the error message names `"bad"` and lists `full`/`lite` as valid options,
  and no startup log line was emitted (confirming the failure occurs before tool imports).

- [ ] **T025** Start the server with `MIGRATION_MODE=full` and confirm the startup log line
  reads `tools=24`. Start with `MIGRATION_MODE=lite` and confirm `tools=4`.

---

## Task summary table

| Phase | Tasks | Parallelizable | Depends on |
|---|---|---|---|
| A — Foundation | T001–T002 | — | none |
| B — Mixed-mode guards | T003–T005 | T005 only | A |
| C — Server imports | T006–T008 | — | A, B |
| D — Skill relocation | T009–T012 | all | none |
| E — Install bundle logic | T013–T018 | — | D |
| F — Tests | T019–T022 | T021, T022 | A–E |
| G — Manual verification | T023–T025 | — | A–F |
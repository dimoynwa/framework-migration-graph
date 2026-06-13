---

description: "Task list for 012-oracle-contract-fixes"
---

# Tasks: Oracle Contract Fixes

**Input**: Design documents from `/specs/012-oracle-contract-fixes/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks grouped by user story. A Foundational phase (Phase 2) loads the three binding contract definitions before any WS2/WS5/US8 implementation can start. Within WS5 (Phase 8), the Cypher query function → MCP tool → skill update chain is sequential; all other work-streams are mutually independent.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared state with concurrently running tasks)
- **[USn]**: Which user story this task belongs to
- All file paths are relative to repository root

---

## Phase 1: Setup (Baseline Verification)

**Purpose**: Confirm the test suite passes before any changes are made, and write the static guard that prevents fixing the wrong formula copy.

- [X] T001 Run baseline test suite and record passing tests: `uv run pytest tests/ -v` from repo root
- [X] T002 Write regression guard test in `tests/mcp/test_graph_schema_guard.py` that reads `docs/graph-schema.md` and asserts the canonical formula text `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH` is present and unchanged — prevents "fixed the wrong document" regression (SC-001, TASK-GAP-010)

---

## Phase 2: Foundational (Data-Model & Contract Baseline)

**Purpose**: Load and confirm three binding contract definitions before any WS2/WS5/US8 implementation starts. These tasks must complete before the dependent phases — they establish the authoritative shapes that implementation must reproduce exactly.

**⚠️ CRITICAL**: Phases 4 (US2), 8 (US6), and 10 (US8) MUST NOT begin until the corresponding contract task here is complete.

- [X] T003 [P] Read `specs/012-oracle-contract-fixes/data-model.md` §1 and `specs/012-oracle-contract-fixes/contracts/update_step_status.md`; confirm STEP_OUTCOME MERGE identity (elementId(ctx) + elementId(step) pair), required properties (status/reason/updatedAt), idempotency guarantee (MERGE not CREATE), and legacy-array retention contract — record these as the authoritative shape before implementing any WS2 tasks (TASK-GAP-001)
- [X] T004 [P] Read `specs/012-oracle-contract-fixes/data-model.md` §2 and `specs/012-oracle-contract-fixes/contracts/update_queried_entity.md`; confirm queriedEntities key/value schema (entity_name → result_summary ≤500 chars stored as JSON string map), two-query Python read-modify-write pattern, and sequential-call requirement (no concurrent writes) — record as authoritative shape before implementing any WS5 tasks (TASK-GAP-001)
- [X] T005 [P] Read `specs/012-oracle-contract-fixes/data-model.md` §3 and `specs/012-oracle-contract-fixes/contracts/close_migration_context.md`; confirm full status enum ({complete, partial, abandoned}), `invalid_final_status` error shape (`tool_status/error_code/hint`), and that `_CLOSE_CONTEXT` Cypher needs no change (validation is Python-side only) — record as authoritative shape before implementing US8 (TASK-GAP-001)

**Checkpoint**: Three contract shapes locked in. WS2, WS5, and US8 implementation phases may now begin.

---

## Phase 3: User Story 1 — Version Arithmetic Produces Correct Sort Order (Priority: P1) 🎯 MVP

**Goal**: Replace the incorrect `sortableVersion` formula in the version-map skill and recompute ALL pre-computed Sortable cells in both tables in a single programmatic pass, then assert every cell matches the canonical formula.

**Independent Test**: (a) Every row in both tables satisfies `stored_sortable == MAJOR*1_000_000 + MINOR*1_000 + PATCH`. (b) `f(3,10,0) > f(3,9,0)`. (c) `docs/graph-schema.md` formula text is unchanged.

**WS1 file**: `migration_oracle/mcp/skills/framework_migration_version_map.md`

### Implementation

- [X] T006 [P] [US1] Replace formula `MAJOR*10000 + MINOR*100 + PATCH` → `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH` at the top formula definition in `migration_oracle/mcp/skills/framework_migration_version_map.md` (FR-001; this task only changes the formula line — no cell edits yet)
- [X] T007 [US1] Recompute ALL Sortable cells in both Spring Boot (19 rows) and Angular (14 rows) tables in a single edit pass in `migration_oracle/mcp/skills/framework_migration_version_map.md` using the corrected values table from plan.md — update every row at once, not per-row hand-edits; every cell must equal `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH` for that row's version (FR-002; depends on T006; TASK-GAP-002)
- [X] T008 [US1] Mechanically verify every Sortable cell equals the canonical formula: write and run a Python script that reads `migration_oracle/mcp/skills/framework_migration_version_map.md`, extracts each table row's version string (e.g. `3.2.0`) and stored Sortable value, parses MAJOR/MINOR/PATCH from the version string, computes `expected = MAJOR*1_000_000 + MINOR*1_000 + PATCH`, and asserts `stored == expected` for every row in both tables; also assert `f(3,10,0) > f(3,9,0)` as a formula property test; also assert `docs/graph-schema.md` still contains the text `MAJOR * 1_000_000` unchanged — the script must print each row's check so any mismatched cell is immediately visible (SC-001, SC-002; TASK-GAP-002 mechanical check — failure here means a cell was hand-transcribed incorrectly)
- [X] T009 [P] [US1] Add `**Last Updated**: 2026-06-13` and upstream schedule links (spring.io/projects/spring-boot, angular.io/guide/releases) immediately below the `# Version Map` heading; remove the duplicate `**Important version boundary:** 15 → 16` line that precedes the bullet list in `migration_oracle/mcp/skills/framework_migration_version_map.md` (FR-003, FR-004; independent of T007)

**Checkpoint**: One formula, all cells recomputed in single pass, freshness metadata present, no duplicate boundary note, assertion script passes.

---

## Phase 4: User Story 2 — Step Outcomes Recorded via STEP_OUTCOME Relationship (Priority: P1)

**Goal**: `update_step_status` must write the `STEP_OUTCOME` relationship (MERGE on ctx+step pair) in addition to legacy arrays; progress-summary query returns non-zero; idempotency and error shapes hold.

**Independent Test**: Record one outcome → progress query non-zero. Record same `(context_id, step_id)` twice → exactly one STEP_OUTCOME. Step not linked to context → documented error shape returned.

**WS2 files**: `migration_oracle/mcp/graph/queries/context.py`, `migration_oracle/mcp/tools/context.py`

**Prerequisite**: T003 (STEP_OUTCOME contract confirmed)

### Implementation

- [X] T010 [P] [US2] Extend `_RECORD_STEP_OUTCOME` in `migration_oracle/mcp/graph/queries/context.py` to add `MATCH (step:MigrationStep) WHERE elementId(step) = $step_id` and `MERGE (ctx)-[so:STEP_OUTCOME]->(step) SET so.status = $outcome, so.reason = $reason, so.updatedAt = datetime()` after existing legacy array writes; forward `reason` parameter from call site through to Cypher; update `update_step_status` docstring in `migration_oracle/mcp/tools/context.py` to remove "reason not persisted" note and state that STEP_OUTCOME is now written — Cypher change and docstring update paired in same task so they cannot drift apart (FR-005, FR-006; TASK-GAP-004)
- [X] T011 [US2] Verify auto-close second query and `context_auto_closed` field remain intact after adding STEP_OUTCOME MERGE to the first query in `migration_oracle/mcp/graph/queries/context.py` — confirm no regression to auto-close behaviour

### Tests

- [X] T012 [P] [US2] Write E2E test in `tests/mcp/test_step_outcome_e2e.py`: create context, record step outcome via `update_step_status`, run schema progress-summary Cypher (graph-schema.md example #5: `OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(step) RETURN count(CASE WHEN so.status='completed' THEN 1 END) AS completed ...`), assert counts are non-zero and match the recorded outcomes (SC-003; TASK-GAP-005)
- [X] T013 [P] [US2] Write idempotency test in `tests/mcp/test_step_outcome_idempotency.py`: call `update_step_status` twice for the same `(context_id, step_id)` pair with different outcomes; assert exactly one `STEP_OUTCOME` relationship exists in graph; assert latest outcome value is present (SC-004; TASK-GAP-006)
- [X] T014 [P] [US2] Write error-path test in `tests/mcp/test_step_outcome_errors.py`: call `update_step_status` with a `step_id` that is not linked to the context; assert documented error shape is returned and no `STEP_OUTCOME` relationship is created (TASK-GAP-009)

**Checkpoint**: STEP_OUTCOME written by update_step_status; progress query returns non-zero; double-record leaves one relationship; unlinked step returns error shape.

---

## Phase 5: User Story 3 — Scope/Severity Queries Honour Threshold Parameter (Priority: P1)

**Goal**: `get_steps_for_scope_tier` rejects unknown `severity_threshold` values with a documented error; valid thresholds filter steps to "at or above" the given level.

**Independent Test**: Seeded mixed-severity steps; `severity_threshold="high"` returns zero low/medium steps. Unknown threshold returns `error_code: "invalid_severity_threshold"`.

**WS3 file (tools)**: `migration_oracle/mcp/tools/context.py`

### Implementation

- [X] T015 [P] [US3] Add `_VALID_THRESHOLDS = {"low", "medium", "high", "critical"}` constant and input validation guard at the start of `get_steps_for_scope_tier` in `migration_oracle/mcp/tools/context.py` — reject unknown values with `{"status": "error", "error_code": "invalid_severity_threshold"}`; update docstring in the same edit to state ordering (`critical > high > medium > low`), "at or above threshold" semantics, and rejection behaviour — validation guard and docstring paired so contract cannot drift (FR-008; TASK-GAP-004; per contracts/get_steps_for_scope_tier.md)

### Tests

- [X] T016 [P] [US3] Write negative/severity and error-path tests in `tests/mcp/test_severity_threshold.py`: (a) seed steps with severities low/medium/high/critical; call `get_steps_for_scope_tier` with `severity_threshold="high"`; assert zero returned steps have severity in `{"low", "medium"}` (SC-005; TASK-GAP-007); (b) assert `severity_threshold="medium"` excludes only low; (c) assert unknown threshold value (e.g. `"urgent"`) returns `{"status": "error", "error_code": "invalid_severity_threshold"}` (TASK-GAP-009); (d) assert a nonexistent `context_id` returns `{"status": "error", "error_code": "context_not_found"}` — this covers the second documented error path from contracts/get_steps_for_scope_tier.md (issue 7 — previously missing error-path coverage)

**Checkpoint**: Severity filter excludes below-threshold steps; unknown value is rejected; docstring matches implementation.

---

## Phase 6: User Story 4 — Upgrade-Path Analysis Returns Recipe Data (Priority: P2)

**Goal**: Fix the `AUTOMATED_BY` traversal in `_ANALYZE_UPGRADE_PATH` to start from `MigrationStep` (variable `s`) not `MigrationRule` (variable `rule`), and pair the Cypher fix with a Returns-table docstring update.

**Independent Test**: `analyze_upgrade_path` with `include_recipes=true` returns non-empty recipe list for a step with an `AUTOMATED_BY` edge. Step without `AUTOMATED_BY` returns empty list.

**WS3 file (queries)**: `migration_oracle/mcp/graph/queries/upgrade.py`

### Implementation

- [X] T017 [P] [US4] Change `OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)` → `OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)` in `_ANALYZE_UPGRADE_PATH` Cypher in `migration_oracle/mcp/graph/queries/upgrade.py`; add `step_id: elementId(s)` as a required field in the per-rule `collect(DISTINCT CASE WHEN rec IS NULL THEN null ELSE {...} END)` clause so callers can map each recipe entry back to the step that requires it (see contracts/analyze_upgrade_path.md recipe-entry table — `step_id` is listed as a required field); update `analyze_upgrade_path` Returns-table docstring to state recipes are per step (traversal: `REQUIRES_STEP → AUTOMATED_BY`) and that each entry includes `step_id` — Cypher fix, `step_id` addition, and Returns-table update all in same task (FR-009; TASK-GAP-003 [P]; TASK-GAP-004; issue 3)

### Tests

- [X] T018 [P] [US4] Write recipe-join and error-path tests in `tests/mcp/test_recipe_join.py`: (a) seed `MigrationRule → REQUIRES_STEP → MigrationStep → AUTOMATED_BY → OpenRewriteRecipe` chain; call `analyze_upgrade_path` with `include_recipes=true`; assert returned rule contains non-empty `recipes` list; assert each recipe entry has a non-null `step_id` field matching the element ID of the seeded `MigrationStep` (issue 3 — `step_id` is a required field per contract); (b) assert a step without `AUTOMATED_BY` contributes an empty list (not null); (c) assert `include_recipes=false` returns no recipe data; (d) assert an unsupported framework returns `{"status": "error", "error_code": "unsupported_framework"}` (SC-006; TASK-GAP-007; issue 7 — error-path coverage for analyze_upgrade_path)

**Checkpoint**: Non-empty recipes returned for automatable steps; empty list for non-automatable steps; `include_recipes=false` unchanged.

---

## Phase 7: User Story 5 — Tool Return Fields Match Documented API (Priority: P2)

**Goal**: Fix three independently correctable API mismatches. Each task pairs the code fix WITH the Returns-table/docstring update so Cypher, Python caller, and documentation cannot drift apart.

**Independent Test**: `entity_name` non-null in `resolve_deprecation`; `require_no_params` and `only_composite` filter correctly; `submit_migration_insight` duplicate call returns `insight_id=null` and non-null `duplicate_of`.

**WS4 files**: `migration_oracle/mcp/graph/queries/deprecation.py`, `migration_oracle/mcp/tools/deprecation.py`, `migration_oracle/mcp/graph/queries/search.py`, `migration_oracle/mcp/tools/community.py`

### Implementation

- [X] T019 [P] [US5] Fix `resolve_deprecation` API mismatch: rename Cypher alias `e.name AS original_entity` → `e.name AS entity_name` in `_RESOLVE_DEPRECATION` in `migration_oracle/mcp/graph/queries/deprecation.py`; update `record.get("original_entity")` → `record.get("entity_name")` in `migration_oracle/mcp/tools/deprecation.py`; update Returns-table in `resolve_deprecation` docstring to use `entity_name` — Cypher alias, Python caller, and Returns-table all updated in same task (FR-010; TASK-GAP-004; per contracts/resolve_deprecation.md)
- [X] T020 [P] [US5] Fix `search_openrewrite_recipes` property mismatches: change `r.isComposite` → `r.composite` in both filter and RETURN clause; change `AND size(coalesce(r.requiredParams, [])) = 0` → `AND NOT EXISTS { (r)-[:HAS_PARAM]->(p:RecipeParam) WHERE p.required = true }` — both in `hydrate_openrewrite_recipes` in `migration_oracle/mcp/graph/queries/search.py`; update `search_openrewrite_recipes` docstring in `migration_oracle/mcp/tools` to reflect correct property names and real graph structure — Cypher fix and docstring update paired (FR-011, FR-012; TASK-GAP-004; per contracts/search_openrewrite_recipes.md)
- [X] T021 [P] [US5] Fix `submit_migration_insight` return shapes and docstring: on duplicate path, response field `insight_id` must be `None` (no new insight was created) and response field `duplicate_of` must be the element ID of the **existing** duplicate insight returned by the dedup query — these are different values and must not reuse the same variable; on error path, both `insight_id` and `duplicate_of` must be `None`; update docstring in `migration_oracle/mcp/tools/community.py` with dedup threshold (0.92 cosine similarity), three-pass pipeline (exact → vector → BM25+cosine), and consistent field semantics across all three status paths — both shape fixes and docstring update in same task (FR-013; TASK-GAP-004; issue 6; per contracts/submit_migration_insight.md)

### Tests

- [X] T022 [P] [US5] Write field-contract and error-path tests in `tests/mcp/test_tool_api_fields.py`: (a) `resolve_deprecation` for known deprecated entity returns non-null `entity_name`; (b) `search_openrewrite_recipes` with `require_no_params=true` excludes recipe with required `RecipeParam`; (c) `only_composite=true` returns only `composite=true` recipes; (d) two identical `submit_migration_insight` calls — second returns `status="duplicate"`, `insight_id=None`, non-null `duplicate_of`; (e) each tool's error path returns documented shape (SC-007, SC-008, SC-009; TASK-GAP-009)

**Checkpoint**: `entity_name` non-null; composite/param filters use real schema properties; duplicate insight returns correct shape; all error paths match contracts.

---

## Phase 8: User Story 6 — Resumed Sessions Skip Already-Queried Entities (Priority: P2)

**Goal**: Add `update_queried_entity` MCP tool (backed by a Cypher query function) and document the Loop II skip guard and `force_refresh` semantics. The Cypher query function is the foundation for the MCP tool and the skill update — these three tasks are sequential, not parallel. `force_refresh` is a pure agent-loop concept documented in the skill; it is NOT a parameter of any tool (confirmed by contracts/get_steps_for_scope_tier.md and contracts/update_queried_entity.md).

**Independent Test**: Call `update_queried_entity` → entity present in `queriedEntities`. Resume same context → skip guard fires, no re-query. `force_refresh` invoked via skill → entity IS re-queried and cache updated.

**WS5 files**: `migration_oracle/mcp/graph/queries/context.py`, `migration_oracle/mcp/tools/context.py`, `migration_oracle/mcp/skills/framework_migration_main.md`

**Prerequisite**: T004 (queriedEntities schema confirmed)

### Implementation

- [X] T023 [US6] Add `update_queried_entity` Cypher query function to `migration_oracle/mcp/graph/queries/context.py`: two-step Python read-modify-write — (1) `MATCH (ctx) WHERE elementId(ctx) = $id RETURN ctx.queriedEntities AS qe`, (2) parse JSON, upsert `entity_name → result_summary[:500]`, (3) `SET ctx.queriedEntities = $updated_json`; return `None` if context not found, else `{"cached_count": len(current)}` — NOT [P]: foundation for T024 and T025; no other WS5 implementation may begin before this is complete (FR-014; TASK-GAP-003; per T004 contract and contracts/update_queried_entity.md)
- [X] T024 [US6] Add `update_queried_entity` `@mcp.tool()` function to `migration_oracle/mcp/tools/context.py` with parameters `context_id: str`, `entity_name: str`, `result_summary: str`; on success return `{"status": "ok", "context_id", "entity_name", "cached_count"}`; on not-found return `{"status": "error", "error_code": "context_not_found", "hint": "Context '<id>' not found"}` — NOT [P]: depends on T023 query function; blocks T025 skill update
- [X] T025 [US6] Update Loop II skip guard paragraph in `migration_oracle/mcp/skills/framework_migration_main.md`: (a) per-entity skip guard instruction (read `ctx.queriedEntities[entity_name]`; if present skip the tool call unless the agent has been instructed to force-refresh that entity); (b) `force_refresh` semantics — this is a pure agent-loop concept, conveyed via the skill invocation (e.g. user says "re-query org.example.Foo"), NOT a parameter on any MCP tool; the agent checks it per-entity before calling tools; (c) `update_queried_entity` call-after-query instruction including sequential-call warning — NOT [P]: depends on T024 tool existing; skill cannot document a tool that is not yet implemented (FR-015; issues 1+4 — T025 was formerly a tool-parameter task which was incorrect per contracts/get_steps_for_scope_tier.md; TASK-GAP-003; per contracts/update_queried_entity.md)

### Tests

- [X] T026 [P] [US6] Write resume test in `tests/mcp/test_resume_skip_guard.py`: call `update_queried_entity` to populate an entity in `queriedEntities`; open same context (simulating resume); assert entity key is present in `queriedEntities` and the skip guard does not re-issue the tool call for that entity (SC-010; TASK-GAP-008)
- [X] T027 [P] [US6] Write force-refresh test in `tests/mcp/test_force_refresh.py`: pre-populate `queriedEntities` with an entity; simulate the agent-loop logic from `framework_migration_main.md` with `force_refresh` set for that entity (the skip guard is bypassed in code, not via a tool parameter — `force_refresh` is a local flag in the agent loop, never passed to `get_steps_for_scope_tier`); assert the entity query IS re-issued; assert `update_queried_entity` is called after and `queriedEntities[entity_name]` is overwritten with the fresh result (TASK-GAP-008; issues 1+4)
- [X] T028 [P] [US6] Write error-path test in `tests/mcp/test_update_queried_entity_errors.py`: call `update_queried_entity` with a nonexistent `context_id`; assert `{"status": "error", "error_code": "context_not_found"}` is returned (TASK-GAP-009)

**Checkpoint**: `update_queried_entity` persists entity; repeated calls upsert not duplicate; skip guard fires on resume; `force_refresh` (agent-loop concept, not a tool parameter) bypasses cache for named entity only; error path matches contract.

---

## Phase 9: User Story 7 — Build-Failure Path Has a Loadable Rollback Procedure (Priority: P3)

**Goal**: Create the `skill://framework-migration/rollback` resource (auto-discovered by `install_migration_skill`); update Loop III's build-failure row to reference it; add Loop IV stateless-fallback section.

**Independent Test**: `framework_migration_rollback.md` exists and contains concrete revert steps; `skill://framework-migration/rollback` appears in Loop III row; Loop IV section present in `framework_migration_main.md`.

**WS6 files**: `migration_oracle/mcp/skills/framework_migration_rollback.md` (new), `migration_oracle/mcp/skills/framework_migration_main.md`

### Implementation

- [X] T030 [P] [US7] Create `migration_oracle/mcp/skills/framework_migration_rollback.md` with URI `skill://framework-migration/rollback`, 5-step `git stash push` procedure (IDENTIFY → STASH → VERIFY → DECIDE with options A/B/C → RECORD), and final `update_step_status(outcome="failed", reason="build failed: [error]")` call — [P]: creates a new file, no conflict with any other task; file is auto-discovered by `install_migration_skill` — no code change to installer needed (FR-016; TASK-GAP-003; per research.md Decision 3)
- [X] T031 [US7] Update Loop III build-failure table row in `migration_oracle/mcp/skills/framework_migration_main.md` to replace "Load rollback skill" with `Load \`skill://framework-migration/rollback\`. Follow the revert procedure. Call \`update_step_status(outcome="failed", reason="build failed: [error]")\`` — depends on T030 file existing before referencing its URI
- [X] T032 [US7] Add `### Loop IV — STATELESS FALLBACK` section to `migration_oracle/mcp/skills/framework_migration_main.md` with: trigger condition (no `context_id`), steps skipped in stateless mode (reading `ctx.skippedSteps[]` — no backlog available), and in-memory steps (print backlog from agent memory, call `submit_migration_insight` without context, emit stateless-mode session summary) — add unconditionally; ISSUE-013 confirmed section does not exist (FR-017)

**Checkpoint**: Rollback skill file exists and auto-discovered; Loop III references URI; Loop IV section present.

---

## Phase 10: User Story 8 — Abandoned Sessions Can Be Closed Correctly (Priority: P3)

**Goal**: `close_migration_context` accepts `"abandoned"` and rejects other unknown values with the documented error shape. Validation logic and docstring are updated together.

**Independent Test**: `close_migration_context("abandoned")` succeeds; unknown `final_status` returns `{"tool_status": "error", "error_code": "invalid_final_status"}`.

**WS2 addendum file**: `migration_oracle/mcp/tools/context.py`

**Prerequisite**: T005 (status enum contract confirmed)

### Implementation

- [X] T033 [P] [US8] Add `_VALID_FINAL_STATUSES = {"complete", "partial", "abandoned"}` constant and input validation block to `close_migration_context` in `migration_oracle/mcp/tools/context.py`; reject unknown values with `{"tool_status": "error", "error_code": "invalid_final_status", "hint": "final_status must be one of: abandoned, complete, partial"}`; update docstring to list all three accepted values in the same edit — validation logic and docstring paired so they cannot drift (FR-007; TASK-GAP-001 consumes T005; TASK-GAP-004; per contracts/close_migration_context.md)

### Tests

- [X] T034 [P] [US8] Write status enum test in `tests/mcp/test_close_migration_context.py`: assert `close_migration_context("abandoned")` succeeds and sets context status to `"abandoned"` in graph; assert `close_migration_context("invalid_value")` returns `{"tool_status": "error", "error_code": "invalid_final_status"}`; assert `"complete"` and `"partial"` still accepted (SC-011; TASK-GAP-009)

**Checkpoint**: Abandoned close succeeds; invalid final_status returns documented error; existing values unaffected.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: FR-018 / FR-019 sweep and final no-regression run.

- [X] T035 [P] Verify FR-018: confirm all modified tools (`update_step_status`, `close_migration_context`, `get_steps_for_scope_tier`, `analyze_upgrade_path`, `resolve_deprecation`, `search_openrewrite_recipes`, `submit_migration_insight`, `update_queried_entity`) return documented error shapes on all failure paths — no new error codes introduced without a corresponding contracts/ update
- [X] T036 [P] Verify FR-019: grep all changes across WS1–WS6 and confirm no graph write is routed through `execute_custom_cypher`; all mutable writes must go through owning tools only
- [X] T037 Run full test suite and confirm no regressions: `uv run pytest tests/ -v` (SC-015)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — T003/T004/T005 can run in parallel within Phase 2
- **Phase 3 (US1)**: Depends only on Phase 1; fully independent of Phase 2
- **Phase 4 (US2)**: Depends on T003 (STEP_OUTCOME contract)
- **Phase 5 (US3)**: Depends only on Phase 1; independent of Phase 2
- **Phase 6 (US4)**: Depends only on Phase 1; independent of Phase 2
- **Phase 7 (US5)**: Depends only on Phase 1; independent of Phase 2
- **Phase 8 (US6)**: Depends on T004 (queriedEntities contract); within Phase 8: T023 → T024 → T025 all sequential (no parallel sub-tasks)
- **Phase 9 (US7)**: Depends only on Phase 1; independent of Phase 2
- **Phase 10 (US8)**: Depends on T005 (status enum contract)
- **Phase 11 (Polish)**: Depends on all user story phases completing

### WS5 Internal Dependency Chain (TASK-GAP-003)

```
T023 (Cypher query function)
  └─► T024 (MCP @mcp.tool())
        └─► T025 (skill documentation — force_refresh is agent-loop only, not a tool param)
```

T023, T024, and T025 are NOT [P] with each other. There is no parallel sub-task within WS5 — the former `force_refresh` tool-parameter task has been removed; the concept is documented purely in the skill (T025).

### Work-Stream Parallelism

```bash
# After Phase 1+2, all of these can run concurrently (touch disjoint files):
Task: "US1 — Version Arithmetic"  (Phase 3, file: framework_migration_version_map.md) [P]
Task: "US2 — STEP_OUTCOME"         (Phase 4, files: graph/queries/context.py + tools/context.py)
Task: "US3 — Severity Threshold"   (Phase 5, file: tools/context.py — different function)
Task: "US4 — Recipe Join Fix"      (Phase 6, file: graph/queries/upgrade.py) [P]
Task: "US5 — API Alignment"        (Phase 7, files: deprecation.py + search.py + community.py) [P]
Task: "US6 — Resumability"         (Phase 8, sequential chain T023→T024→T025; no parallel sub-tasks)
Task: "US7 — Rollback Skill"       (Phase 9, new file + different sections of main.md) [P]
Task: "US8 — Abandoned Close"      (Phase 10, tools/context.py — different function from US2/US6)
```

### Within Each User Story

- Cypher changes before Python callers (T023 before T024)
- Implementation tasks before test tasks (tests validate what was implemented)
- Code and paired docstring in the same task (never separate)

---

## Implementation Strategy

### MVP First (P1 User Stories Only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational) — establishes baseline and loads contracts
2. Complete Phases 3, 4, 5 (US1, US2, US3) in parallel — all P1 defects
3. **STOP and VALIDATE**: Run `uv run pytest tests/ -v` + quickstart.md WS1–WS3 checks
4. These three stories fix the three highest-impact silent-correctness defects

### Incremental Delivery

1. Phase 1 + Phase 2 → baseline confirmed, contracts loaded
2. Phases 3–5 in parallel → P1 defects resolved → validate
3. Phases 6–8 in parallel → P2 defects resolved → validate
4. Phases 9–10 in parallel → P3 defects resolved → validate
5. Phase 11 → cross-cutting verification → full test suite

### Parallel Team Strategy

With multiple contributors:

1. All complete Phase 1 + Phase 2 together (contracts loaded once)
2. Contributor A: US1 (version_map.md — no shared files)
3. Contributor B: US2 (STEP_OUTCOME Cypher + tools/context.py) → later US8 (same file, different function)
4. Contributor C: US3 (tools/context.py validation) + US4 (upgrade.py Cypher)
5. Contributor D: US5 (deprecation.py + search.py + community.py)
6. Contributor E: US6 sequential chain T023→T024→T025 + US7 (new skill file)
7. All merge → Phase 11 cross-cutting verification

---

## Notes

- [P] tasks = different files or distinct functions with no shared state — safe to run concurrently
- [USn] label maps every task to its user story for traceability
- WS2, WS3, WS5 all touch `context.py` but in distinct functions — no merge conflict
- WS5 blocking chain: T023 → T024 → T025 (all sequential); no parallel sub-tasks within WS5
- No APOC — all Cypher must work with Neo4j 5 Community
- `docs/graph-schema.md` is read-only — T002 guard test asserts it stays unchanged
- `execute_custom_cypher` must remain read-only (FR-019)
- Legacy arrays (`completedSteps`/`skippedSteps`/`failedSteps`) must remain populated (FR-005)
- Cypher change and Returns-table/docstring update are always in the same task — they must not be split
- **FR-008 spec reconciliation** (issue 8): FR-008 defers the rank representation to the plan/contract ("The concrete rank representation is a plan/contract detail"). The implemented ordering is `critical > high > medium > low` with integer ranks `low=1, medium=2, high=3, critical=4` per `_severity.py` and data-model.md §6; inclusion condition is `SEVERITY_RANK[step_severity] >= SEVERITY_RANK[threshold]`. T015's docstring target and the code are consistent with this; the spec does not contradict the implementation.
- **`update_queried_entity` contract** (issue 5): `contracts/update_queried_entity.md` write-query block was verified against plan.md lines 378–384. The write query correctly reads `RETURN 1`; `cached_count` is computed in Python as `len(current)` after the upsert — no Cypher projection and no APOC call. Contract and task/plan are consistent.

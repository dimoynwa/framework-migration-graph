---
description: "Task list for MCP Live-Probe Fixes (spec 011)"
---

# Tasks: MCP Live-Probe Fixes

**Input**: Design documents from `/specs/011-mcp-live-probe-fixes/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: INCLUDED — the spec mandates them (SC-010 enumerates nine new unit test files: eight in
`tests/mcp/` and one in `tests/paysafe/`). All tests use `pytest` + `unittest.mock.patch`; no live
Neo4j instance is required.

**Organization**: Tasks are grouped by user story (US1–US9) mapping to ISSUES.md Issues 1–10.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US9)
- File paths are relative to repo root `/Users/dimo.drangov/paysafe-version-migration-graph/`

## Path Conventions

- MCP tool layer: `migration_oracle/mcp/tools/`
- MCP query layer: `migration_oracle/mcp/graph/queries/`
- Ingestion: `migration_oracle/pipeline/`, `migration_oracle/graph/queries/`
- Paysafe resolver: `migration_oracle/paysafe/`
- Tests: `tests/mcp/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the seed-data package directory used by ingestion stories (US4, US8).

- [X] T001 [P] Create the seeds package `migration_oracle/pipeline/seeds/__init__.py` (empty package marker) so curated seed modules added in later phases are importable.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Remove the live `Neo4j TypeError` bug before any other 011 change is applied.

**⚠️ CRITICAL**: This phase is the explicit FIRST implementation task per FR-001. No user-story work
may begin until it is complete, because the existing `stepNotes` map-property write can throw during
development on any `update_step_status` code path.

- [X] T002 Remove the `_READ_STEP_NOTES` and `_WRITE_STEP_NOTES` Cypher constants and delete the `if reason:` block that calls them inside `record_step_outcome` in `migration_oracle/mcp/graph/queries/context.py` (FR-001).
- [X] T003 Remove the docstring line "The 'reason' parameter is persisted in ctx.stepNotes when non-empty." from `update_step_status` in `migration_oracle/mcp/tools/context.py` (FR-001).

**Checkpoint**: No code path writes a map-valued node property. User stories can now begin.

---

## Phase 3: User Story 1 — Agent Advances Through the Migration Checklist (Priority: P1) 🎯 MVP — Issue 1

**Goal**: `update_step_status` persists per-step outcome as a `STEP_OUTCOME` relationship (not a map
property), advances `completedSteps`, and rejects steps not on the migration path.

**Independent Test**: Call `update_step_status` with a non-empty `reason` against a real context/step;
verify success (no `TypeError`) and that the outcome + reason are retrievable via the `STEP_OUTCOME`
relationship on a subsequent read.

### Tests for User Story 1 ⚠️

- [X] T004 [P] [US1] Write `tests/mcp/test_update_step_status.py` covering FR-001–FR-004 per the plan's test-mock table: `test_step_outcome_rel_created`, `test_step_not_on_path_returns_error`, `test_no_map_property_written`, `test_reason_null_when_not_supplied`, `test_completed_steps_preserved`.

### Implementation for User Story 1

- [X] T005 [US1] Add the `_VALIDATE_STEP_ON_PATH` Cypher constant to `migration_oracle/mcp/graph/queries/context.py` (matches step on the context's version-bounded `INCLUDES_RULE → REQUIRES_STEP` path; returns `on_path` boolean) (FR-004).
- [X] T006 [US1] Add the `_MERGE_STEP_OUTCOME_REL` Cypher constant to `migration_oracle/mcp/graph/queries/context.py` (`MERGE (ctx)-[rel:STEP_OUTCOME]->(s) SET rel.status, rel.reason, rel.updatedAt`) per `contracts/step_outcome_relationship.md` (FR-002).
- [X] T007 [US1] Update `record_step_outcome` in `migration_oracle/mcp/graph/queries/context.py` to: run `_VALIDATE_STEP_ON_PATH` and return `{"on_path": False}` sentinel on failure; otherwise run the existing `_RECORD_STEP_OUTCOME` (preserving `completedSteps` advancement, FR-003) and `_MERGE_STEP_OUTCOME_REL` with `reason=reason or None` in the same write session (FR-002).
- [X] T008 [US1] Add the `step_not_on_path` guard to `update_step_status` in `migration_oracle/mcp/tools/context.py`: when `record_step_outcome` returns `on_path=False`, return `{"status":"error","error_code":"step_not_on_path","step_id":...,"hint":...}` without creating a relationship (FR-004).

**Checkpoint**: US1 fully functional — the core orchestration loop advances reliably.

---

## Phase 4: User Story 2 — Agent Auto-Applies OpenRewrite Recipes (Priority: P1) — Issue 2

**Goal**: Ingestion populates `OpenRewriteRecipe` `description`/`displayName` so the fulltext index
returns hits and `build_recipe_plan` populates `auto_track`.

**Independent Test**: `search_openrewrite_recipes(query="Spring Boot upgrade 4.0")` returns non-empty
hits; the `openrewrite_recipe_description` fulltext index is `ONLINE`; every recipe node has populated
`description`/`displayName`.

### Tests for User Story 2 ⚠️

- [X] T009 [P] [US2] Write `tests/mcp/test_search_openrewrite_recipes.py` covering FR-009–FR-012 per the plan's test-mock table: `test_description_set_on_stub`, `test_backfill_on_match`, `test_search_returns_hits`, `test_zero_hits_when_description_absent`.

### Implementation for User Story 2

- [X] T010 [US2] In `migration_oracle/pipeline/populator.py` `_write_step`, pass `step_summary=step.summary` into the `AUTOMATED_BY → OpenRewriteRecipe` MERGE and set `e.description`/`e.displayName` from `$step_summary` on `ON CREATE`, plus `coalesce(...)` backfill on `ON MATCH` (FR-009, FR-011).
- [X] T011 [US2] Add a post-`populate_graph` validation gate in `migration_oracle/pipeline/populator.py` running `MATCH (r:OpenRewriteRecipe) RETURN count(r), count(r.description), count(r.displayName)`; log a warning (not error) if the three counts differ (FR-012). Confirm `ensure_indexes()` (already called) keeps the `openrewrite_recipe_description` fulltext index `ONLINE` (FR-010).

**Checkpoint**: Recipe search returns hits; `auto_track` populates.

---

## Phase 5: User Story 3 — Check a Target Version Using the Standard Framework Name (Priority: P1) — Issues 3 & 4

**Goal**: `check_version_availability` accepts `"Spring Boot"`/`"spring-boot"`/`"springboot"`,
resolves to a canonical record, queries the graph by display form and Maven by slug form.

**Independent Test**: `check_version_availability("Spring Boot","4.0.0")` and
`check_version_availability("spring-boot","4.0.0")` both return `exists_in_graph: true` against a
graph with `Version {version:"4.0.0", framework:"Spring Boot"}`.

### Tests for User Story 3 ⚠️

- [X] T012 [P] [US3] Write `tests/mcp/test_check_version_availability.py` covering FR-005–FR-008 per the plan's test-mock table: `test_spring_boot_display_form`, `test_spring_boot_slug_form`, `test_spring_boot_no_space`, `test_graph_query_uses_display_form`, `test_maven_uses_slug`, `test_unsupported_framework_no_network_call`. (Note: a `tests/mcp/test_check_version_availability.py` already exists in the working tree — extend/replace it to match these cases.)

### Implementation for User Story 3

- [X] T013 [US3] Add the `_CanonicalFramework` NamedTuple, `_FRAMEWORK_ALIASES` map, `_normalise_key`, and `canonical_framework()` helper (returns NamedTuple on success, structured `unsupported_framework` dict on failure) at module level in `migration_oracle/mcp/tools/upgrade.py` per `contracts/canonical_framework.md` (FR-005, FR-008).
- [X] T014 [US3] Rename/define `_MAVEN_COORDS` keyed by slug in `migration_oracle/mcp/tools/upgrade.py` (FR-007).
- [X] T015 [US3] Update `check_version_availability` in `migration_oracle/mcp/tools/upgrade.py` to call `canonical_framework`, return the error dict (no network call) on the dict sentinel (FR-008), query the graph with `cf.display` (FR-006), and look up Maven by `cf.slug` (FR-007); preserve all spec-010 FR-015–FR-020 Maven probe / `latest_patch` / network-error behaviour unchanged.
- [X] T016 [US3] Confirm `_CHECK_VERSION_IN_GRAPH` in `migration_oracle/mcp/graph/queries/upgrade.py` filters on the `$framework` param (now receiving `cf.display`); adjust only if it does not already use the display-form value (FR-006).

**Checkpoint**: Any accepted framework spelling resolves correctly; MVP set (US1–US3) complete.

---

## Phase 6: User Story 4 — Look Up What Replaces a Deprecated Class (Priority: P2) — Issue 5

**Goal**: Ingestion seeds well-known Spring Boot 3.x deprecated classes with `DEPRECATED_IN` and
`REPLACED_BY` edges so `resolve_deprecation`/`entity_evolution` resolve.

**Independent Test**: `resolve_deprecation("RestTemplate","Spring Boot")` returns `status != not_found`;
`entity_evolution("WebMvcConfigurer","Spring Boot")` returns a non-empty chain.

### Tests for User Story 4 ⚠️

- [X] T017 [P] [US4] Write `tests/mcp/test_resolve_deprecation.py` covering FR-013–FR-014 per the plan's test-mock table: `test_rest_template_found`, `test_rest_template_replaced_by_rest_client`, `test_web_mvc_configurer_found`, `test_unknown_class_not_found`, `test_seed_idempotent`.

### Implementation for User Story 4

- [X] T018 [P] [US4] Create `migration_oracle/pipeline/seeds/deprecated_classes.py` with the `_DeprecatedClass` dataclass and `SPRING_BOOT_3X_DEPRECATED` list (`RestTemplate`→`RestClient`, `WebSecurityConfigurerAdapter`, `WebMvcConfigurerAdapter`, `WebMvcConfigurer`, `EnvironmentPostProcessor`) (FR-013).
- [X] T019 [US4] Add a `seed_deprecated_classes` step in `migration_oracle/pipeline/populator.py` that MERGEs `Class` nodes, `DEPRECATED_IN → Version` edges, and `REPLACED_BY` edges (where a replacement exists), all idempotent via MERGE (FR-013, FR-014).

**Checkpoint**: Deprecation lookups resolve for curated classes; unknown classes still return `not_found`.

---

## Phase 7: User Story 5 — Prioritize Rules by Severity and Change Type (Priority: P2) — Issue 6

**Goal**: `analyze_upgrade_path` projects `title`, `change_type`, `reason`(←`statement`), and
`severity`(←`BreakingScope.severity`); ingestion sets `MigrationRule.framework` and guarantees a
`HAS_SCOPE` edge.

**Independent Test**: `analyze_upgrade_path("Spring Boot","3.5.0","4.0.0")` returns rules each with
non-null `title`, `severity`, and `change_type`.

### Tests for User Story 5 ⚠️

- [X] T020 [P] [US5] Write `tests/mcp/test_analyze_upgrade_path.py` covering FR-015–FR-017 per the plan's test-mock table: `test_title_projected`, `test_reason_from_statement`, `test_reason_fallback_when_both_null`, `test_severity_extracted_from_scopes`, `test_severity_null_for_scopeless`, `test_all_three_fields_non_null`.

### Implementation for User Story 5

- [X] T021 [US5] In `migration_oracle/mcp/graph/queries/upgrade.py` `_ANALYZE_UPGRADE_PATH` `raw_rules` projection, add `title: rule.title` and change `reason` to `coalesce(rule.statement, rule.reason)` (FR-015).
- [X] T022 [US5] In `migration_oracle/mcp/tools/upgrade.py` `_flatten_rules` (or equivalent post-processing), extract top-level `severity` from the first non-null scope entry in each rule's `scopes` list (FR-015).
- [X] T023 [P] [US5] In `migration_oracle/pipeline/populator.py` `_write_entity`, set `rule.framework` on `ON CREATE SET` and `coalesce(rule.framework, $framework)` on `ON MATCH SET` for `MigrationRule` (FR-016).
- [X] T024 [US5] In `migration_oracle/pipeline/populator.py`, after the scope-linking block, add the default-`BreakingScope` Cypher per `contracts/default_breaking_scope.md`: for any `MigrationRule` lacking a `HAS_SCOPE` edge, `MERGE (bs:BreakingScope {scope:"general", severity:"low"})` and `MERGE (rule)-[:HAS_SCOPE]->(bs)` (FR-017).

**Checkpoint**: Every returned rule carries non-null title/severity/change_type.

---

## Phase 8: User Story 6 — Filter Steps by Scope Tier (Priority: P2) — Issue 7

**Goal**: `get_steps_for_scope_tier` returns scope-matching steps plus scopeless steps (with
`scope: null`) and never drops scopeless steps. Depends on US5's `HAS_SCOPE` population (T024) for
`total > 0`.

**Independent Test**: Against a context with scoped and scopeless rules, `get_steps_for_scope_tier(scope="build")`
returns scoped steps with their scope and scopeless steps with `scope: null`; `total > 0`.

### Tests for User Story 6 ⚠️

- [X] T025 [P] [US6] Write `tests/mcp/test_get_steps_for_scope_tier.py` covering FR-018–FR-019 per the plan's test-mock table: `test_matching_scope_returned`, `test_scopeless_step_returned_as_null`, `test_mismatched_scope_excluded`, `test_scope_param_passed_to_cypher`, `test_total_gt_zero_when_pending`.

### Implementation for User Story 6

- [X] T026 [US6] Fix `_GET_STEPS_FOR_SCOPE_TIER` in `migration_oracle/mcp/graph/queries/context.py`: `OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs)`, then an explicit `WITH ctx, v, r, s, bs` before `WHERE bs IS NULL OR bs.scope = $scope` (row-level filter), projecting `bs.scope AS scope` and `bs.severity AS severity` (FR-018).
- [X] T027 [US6] Fix `get_steps_for_scope_tier` in `migration_oracle/mcp/graph/queries/context.py` (Python): pass `scope=scope` to the Cypher; relax the `entity_name` guard to a `step_id` guard; allow rows with `severity is None` through unconditionally (scopeless), otherwise apply `severity_meets_threshold` (FR-018, FR-019).

**Checkpoint**: Scope-filtered orchestration returns `total > 0`; scopeless steps preserved.

---

## Phase 9: User Story 7 — See the Source Version of Each Pipeline Run (Priority: P3) — Issue 8

**Goal**: `list_pipeline_runs` reports `from_version` from the stored `Version.fromVersion`, with a
filename-parse fallback and graceful empty default.

**Independent Test**: `list_pipeline_runs` returns a non-empty `from_version` for every run matching
its artifact filename.

### Tests for User Story 7 ⚠️

- [X] T028 [P] [US7] Write `tests/mcp/test_list_pipeline_runs.py` covering FR-020–FR-022 per the plan's test-mock table: `test_stored_from_version_used`, `test_filename_fallback`, `test_graceful_empty_when_no_source`, `test_filtered_md_suffix_handled`.

### Implementation for User Story 7

- [X] T029 [P] [US7] In `migration_oracle/mcp/graph/queries/artifacts.py` `_LIST_PIPELINE_RUNS`, add `v.fromVersion AS from_version` to the projection (FR-020).
- [X] T030 [US7] In `migration_oracle/mcp/tools/artifacts.py`, replace the hardcoded `from_version=""` with `row.get("from_version") or _parse_from_version(raw_md_path)`; add `_parse_from_version` anchoring on the `-to-` separator and `-changes` token, tolerating a `_filtered.md` suffix, returning `""` on no match (FR-020, FR-022).
- [X] T031 [P] [US7] In `migration_oracle/graph/queries/pipeline.py`, add a `from_version` parameter to `upsert_version_artifact_paths` and `SET v.fromVersion = $from_version`; update the call site in `migration_oracle/pipeline/populator.py` to pass `from_version` (FR-021).

**Checkpoint**: Every run reports a correct `from_version`.

---

## Phase 10: User Story 8 — Phase-Level Lifecycle Alerts (Priority: P3) — Issue 9

**Goal**: Ingestion seeds `LifecycleAlert` nodes linked to the relevant `Version`; `analyze_upgrade_path(include_lifecycle=True)`
projects `message`/`category`/`phase`.

**Independent Test**: After seeding the 3.5→4.0 alerts, `analyze_upgrade_path(include_lifecycle=True)`
returns a non-empty `lifecycle_alerts`; `include_lifecycle=False` returns empty.

### Tests for User Story 8 ⚠️

- [X] T032 [P] [US8] Write `tests/mcp/test_lifecycle_alert.py` covering FR-023–FR-024 per the plan's test-mock table: `test_alerts_returned_when_include_lifecycle_true`, `test_empty_when_include_lifecycle_false`, `test_alert_properties_projected`, `test_idempotent_merge`.

### Implementation for User Story 8

- [X] T033 [P] [US8] Create `migration_oracle/pipeline/seeds/lifecycle_alerts.py` with the `_LifecycleAlert` dataclass and `SPRING_BOOT_4X_ALERTS` list (each with `message`, `category` ∈ {security,api,config,dependency,other}, `phase` ∈ {pre-migration,migration,post-migration}) (FR-023).
- [X] T034 [US8] Add a `seed_lifecycle_alerts` step in `migration_oracle/pipeline/populator.py` that MERGEs `(v:Version)-[:HAS_LIFECYCLE_ALERT]->(a:LifecycleAlert {message:$message})` and sets `category`/`phase`, per `data-model.md` MERGE identity, idempotent (FR-023, FR-024).
- [X] T035 [US8] Surface `LifecycleAlert` nodes through `analyze_upgrade_path` as a NEW data path — do NOT modify the existing `raw_lifecycle_events` block (lines ~15–23), which queries unrelated entity-level `DEPRECATED_IN`/`REMOVED_IN`/`INTRODUCED_IN` events and must remain untouched. Three sub-steps:
  1. In `_ANALYZE_UPGRADE_PATH` (`migration_oracle/mcp/graph/queries/upgrade.py`), add a new `OPTIONAL MATCH (v)-[:HAS_LIFECYCLE_ALERT]->(la:LifecycleAlert)` block and `collect(DISTINCT {message: la.message, category: la.category, phase: la.phase})` into a new variable `raw_phase_alerts`.
  2. Add `raw_phase_alerts` to the query's RETURN clause as a separate column (distinct from `raw_lifecycle_events`).
  3. In `migration_oracle/mcp/tools/upgrade.py`, build `lifecycle_alerts` from the new `raw_phase_alerts` column (gated by `include_lifecycle` so `False` yields `[]`), NOT from `lifecycle_events`. (FR-023, FR-024)

**Checkpoint**: Lifecycle alerts surface for the 3.5→4.0 path.

---

## Phase 11: User Story 9 — Resolve a Paysafe Service Dependency Without Hanging (Priority: P3) — Issue 10

**Goal**: Every outbound network call in the resolver is time-bounded; on timeout/unavailability the
tool returns a structured error instead of hanging.

**Independent Test**: Simulate an unresponsive FindIt backend; the tool returns a structured error
within the configured timeout.

### Tests for User Story 9 ⚠️

- [X] T036 [P] [US9] Write `tests/paysafe/test_resolver_findit_timeout.py` covering FR-025–FR-026: timeout returns structured `findit_timeout` error within the bound (no hang); normal response resolves; unregistered service returns the structured `not_found`-style result.

### Implementation for User Story 9

- [X] T037 [US9] In `migration_oracle/paysafe/resolver.py`, add the `_FINDIT_TIMEOUT_SECONDS = 10` module constant and wrap the `findit.lookup()` call in a `ThreadPoolExecutor(max_workers=1)` with `.result(timeout=_FINDIT_TIMEOUT_SECONDS)`; on `FuturesTimeout`, return `_build_error("findit_timeout", ..., recoverable=True, ...)`; preserve all existing `_FindItError` handling (FR-025, FR-026).

**Checkpoint**: Resolver returns within its configured timeout for an unresponsive backend.

---

## Phase 12: Polish & Cross-Cutting Concerns

- [X] T038 [P] Run the full `tests/mcp/` and `tests/paysafe/` suites (`pytest tests/mcp tests/paysafe`) and confirm all new and existing tests pass.
- [X] T039 [P] Update `tests/mcp/test_schema_lint.py` / `tests/mcp/test_server.py` if the new `step_not_on_path` / `findit_timeout` error shapes or the `STEP_OUTCOME` relationship change tool contracts (regression guard).
- [X] T040 Re-run ingestion end-to-end (or its idempotency tests) to confirm re-population produces no duplicate `OpenRewriteRecipe`, `Class`, `LifecycleAlert`, or `BreakingScope` nodes/edges (FR-014, FR-017, FR-024).
- [X] T041 Re-run the `/mcp-live-probe` scenario from `ISSUES.md` (3.5.0 → 4.0.0 for `paysafe-wallet-switch`) and confirm all ten issues are resolved against SC-001–SC-010.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on nothing but BLOCKS all user stories (FR-001 must be first).
- **User Stories (Phases 3–11)**: All depend on Phase 2. Within priority order P1 (US1–US3) → P2 (US4–US6) → P3 (US7–US9).
- **Polish (Phase 12)**: Depends on all targeted user stories being complete.

### Cross-Story Dependencies

- **US6 (Phase 8)** depends on **US5 task T024** (default `HAS_SCOPE` population) for `total > 0`; the query/Python fixes (T026–T027) are independent but the SC-006 outcome needs T024.
- All other user stories are independent and touch disjoint files.

### Shared-File Sequencing

| File | Tasks (in order) |
|---|---|
| `migration_oracle/mcp/graph/queries/upgrade.py` | T021 (US5 — `title`/`reason` projection) → T035 (US8 — new `raw_phase_alerts` block). Different sections of the same Cypher string; **do not run in parallel** — serialize to avoid a merge conflict. |
| `migration_oracle/mcp/tools/upgrade.py` | T013–T015 (US3 — canonical_framework) and T022 (US5 — severity) and T035 step 3 (US8 — lifecycle_alerts). Distinct functions; serialize edits to the same file. |
| `migration_oracle/pipeline/populator.py` | T010 (US2) · T019 (US4) · T023/T024 (US5) · T031 (US7 call site) · T034 (US8). Distinct blocks; serialize edits to the same file. |
| `migration_oracle/mcp/graph/queries/context.py` | T002 (Phase 2) → T005/T006/T007 (US1) · T026/T027 (US6). Serialize. |

### Within Each User Story

- Tests (the `[P]` test task) should be written first and FAIL before implementation.
- Query-layer Cypher before tool-layer wiring (e.g. T005/T006 before T007/T008).
- Seed-data modules before the populator step that consumes them (T018 before T019; T033 before T034).

---

## Parallel Opportunities

- **Setup**: T001.
- **Across P1 stories** (after Phase 2): US1, US2, US3 touch disjoint files and can run in parallel.
- **Test authoring**: T004, T009, T012, T017, T020, T025, T028, T032, T036 are all `[P]` (distinct new files).
- **Within-story [P]**: T018 (seed) ∥ T017 (test); T023 (populator) ∥ T020 (test); T029/T031 (different files) ∥ T028.
- **Polish**: T038 ∥ T039.

### Parallel Example: P1 Stories

```bash
# After Phase 2, launch the three P1 test files together:
Task: "Write tests/mcp/test_update_step_status.py (T004)"
Task: "Write tests/mcp/test_search_openrewrite_recipes.py (T009)"
Task: "Write tests/mcp/test_check_version_availability.py (T012)"
```

---

## Implementation Strategy

### MVP First (P1 — US1, US2, US3)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational — remove stepNotes write).
2. Complete US1 (orchestration loop), US2 (recipe auto-track), US3 (version check).
3. **STOP and VALIDATE**: SC-001, SC-002, SC-003.

### Incremental Delivery

1. Setup + Foundational → safe baseline (no map-property write).
2. P1 (US1–US3) → core loop + auto-track + version check → validate → demo.
3. P2 (US4–US6) → deprecation, rule metadata, scope filtering → validate.
4. P3 (US7–US9) → from_version, lifecycle alerts, resolver timeout → validate.
5. Polish (Phase 12) → full suite, idempotency, live-probe re-run.

---

## Notes

- [P] tasks = different files, no dependencies.
- All tests are unit tests with `unittest.mock.patch`; no live Neo4j (per spec 010 convention).
- FR-001 (Phase 2) MUST precede all other work — it removes the live `TypeError` bug.
- US6's `total > 0` outcome (SC-006) depends on US5's default-`HAS_SCOPE` population (T024).
- Spec 010 FR-015–FR-020 for `check_version_availability` remain in force; 011 amends only canonicalization/graph-lookup.
- Commit after each task or logical group; re-run ingestion idempotency checks before closing.

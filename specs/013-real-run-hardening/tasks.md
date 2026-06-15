---
description: "Task list for 013-real-run-hardening"
---

# Tasks: Real-Run Hardening

**Input**: Design documents from `specs/013-real-run-hardening/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks are grouped by user story (US1–US7) to enable independent implementation and testing of each story. Workstream A (US1) must complete before US2, US3, US4, US5 begin. Workstream D (US6) and E (US7) are independent and can run in parallel with any phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no intra-story dependency)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Catalogue Data & Project Baseline)

**Purpose**: Populate the Neo4j Version catalogue with nodes required by the 3.5.12 → 4.0.6 scenario before any tool tests can pass.

- [X] T001 Seed `Spring Boot 4.0.6` Version node (framework, version, sortableVersion=4000006, status="active") via `scripts/seed_013_versions.py`
- [X] T002 [P] Seed Spring Cloud Version nodes (Hoxton through Oakwood — 6 trains) with calVer sortableVersion formula via `scripts/seed_013_versions.py`

---

## Phase 2: Foundational (Shared Dataclasses — blocks US1 tool delegation)

**Purpose**: Add the `VersionResolutionResult` and `VersionResolutionFailure` dataclasses that every downstream tool and test depends on. Nothing else in this feature can begin until these types exist.

**⚠️ CRITICAL**: All US1 tool delegation tasks (T005–T012) depend on T003 being importable. T004 (`resolve_version`) depends on T003. Within Phase 3, task order is strictly: T003 → T004 → T005–T012 (T005–T009 can fan out in parallel once T004 is done).

- [X] T003 Add `VersionResolutionResult` and `VersionResolutionFailure` dataclasses to `migration_oracle/models/graph.py` (fields per data-model.md §2.4–§2.5: resolvedVersion, resolvedSortable, nodeId, requestedVersion, rounded, aheadOfCatalogue, stubCreated, direction; failure: status="NO_CANDIDATE", framework, requestedVersion, candidatesConsidered)

**Checkpoint**: Dataclasses importable — US1 implementation can begin.

---

## Phase 3: US1 — Consistent Version Resolution (Priority: P1) 🎯 MVP

**Goal**: Replace all inline version normalisation with a single shared `resolve_version` routine so that every tool that maps `(framework, version)` to a graph Version node returns the same node id. Eliminates the `to_minor_zero` patch-truncation bug (ISSUE-017) and the `check_version_availability` / `submit_migration_insight` contradiction (ISSUE-016).

**Independent Test**: Call `check_version_availability` for `spring-boot 3.5.12` (floor), then call `submit_migration_insight` for the same pair. Verify both return `exists_in_graph: true` with the identical resolved `nodeId`. Call `check_version_availability` for `4.0.9` with direction=ceil — verify it returns `4.0.6`, `rounded: true`. Call for `6.0.0` — verify `aheadOfCatalogue: true`, `4.1.0` (or highest catalogued node). Call `resolve_version` for an unknown framework — verify `NO_CANDIDATE` response with framework name.

- [X] T004 [US1] Implement `resolve_version(framework, version, mode, *, allow_stub_create=False)` in `migration_oracle/mcp/graph/queries/upgrade.py` — three Cypher variants (exact / floor / ceil), patch-preservation rule (never truncate caller-supplied patch), ahead-of-catalogue fallback for ceil (clamp + `aheadOfCatalogue=True`), `NO_CANDIDATE` failure when framework unknown, stub-MERGE gate behind `allow_stub_create` flag, returns `VersionResolutionResult | VersionResolutionFailure`. **T004 must be merged before T005–T012 start** (TASK-GAP-001).
- [X] T005 [US1] Update `check_version_availability` in `migration_oracle/mcp/tools/upgrade.py` — replace `_to_minor_zero` + `_CHECK_VERSION_IN_GRAPH` inline query with `resolve_version(mode=direction)`, add optional `direction: Literal["floor","ceil"] = "floor"` parameter, derive `exists_in_graph` from result type, preserve `nodeId` in response for SC-001 consistency guarantee
- [X] T006 [US1] Update `submit_migration_insight` in `migration_oracle/mcp/tools/upgrade.py` — call `resolve_version(mode="floor")` before cosine-similarity dedup; on `VersionResolutionFailure` return failure directly (include `candidatesConsidered`), skip dedup; must never silently no-op (FR-A07)
- [X] T007 [US1] Update `create_migration_context` in `migration_oracle/mcp/tools/context.py` — remove `to_minor_zero` calls, call `resolve_version(mode="floor")` for `fromVersion` and `resolve_version(mode="ceil")` for `toVersion`, write resolved nodes to `UPGRADES_FROM`/`UPGRADES_TO` (not the MERGE key), add optional `allow_stub_create: bool = False` parameter, return `upgrades_to_version`, `rounded`, `aheadOfCatalogue`, `stubCreated` in response
- [X] T008 [US1] Update `analyze_upgrade_path` in `migration_oracle/mcp/tools/upgrade.py` — replace `sortable_version(to_minor_zero(current_version))` with `resolve_version(mode="floor").resolvedSortable` for current, and `resolve_version(mode="ceil").resolvedSortable` for target
- [X] T009 [US1] Update `build_recipe_plan` in `migration_oracle/mcp/tools/upgrade.py` — same `resolve_version(floor/ceil)` delegation as T008
- [X] T010 [US1] Add Spring Cloud co-migration warning check in `migration_oracle/mcp/tools/context.py` — after successful `create_migration_context`, when `fromVersion` major=3 and `toVersion` major=4, check if `ctx.scannedDepsGa` contains `org.springframework.cloud:*` OR `ctx.scannedClasses` contains `org.springframework.cloud.*`; emit `co_migration_warning` identifying Oakwood train boundary and BOM-only import change (FR-A09, FR-A12)
- [X] T011 [US1] Write pytest unit tests for `resolve_version` in `tests/mcp/test_resolve_version.py` — cover: floor resolves 3.5.12 to same node; ceil resolves 4.0.9 to 4.0.6 with `rounded=True`; ceil resolves 6.0.0 to highest node with `aheadOfCatalogue=True`; exact match returns correct node; patch `3.5.12` preserved — never truncated to `3.5.0`; unknown framework returns `VersionResolutionFailure(status="NO_CANDIDATE")` with `candidatesConsidered` list (must not be empty when near-miss nodes exist); `submit_migration_insight` on a near-miss version returns `VersionResolutionFailure` with `candidatesConsidered` showing what was tried — never silent no-op; `allow_stub_create=False` does not create stub nodes (TASK-GAP-009)
- [X] T012 [US1] Write pytest integration test for round-1 contradiction fix and ISSUE-016 regression gate in `tests/mcp/test_resolve_version.py` — against live Neo4j: (a) call `check_version_availability(spring-boot, 3.5.12)` then `submit_migration_insight(spring-boot, 3.5.12)`: assert both return the same `nodeId`; (b) repeat for `(spring-boot, 4.0.6)` and `(spring-boot, 3.5.0)` — for every version where `check_version_availability` returns `exists_in_graph=true`, `submit_migration_insight` on the same pair MUST succeed with the same nodeId (ISSUE-016 regression gate); (c) assert `from_version="3.5.12"` is stored in context identity without truncation (US1.1, US1.2, US1.5, TASK-GAP-006)

**Checkpoint**: US1 complete — tools return consistent verdicts. US2, US3, US4, US5 can now begin (all require resolve_version).

---

## Phase 4: US2 — Context Discovery and Supersede (Priority: P1)

**Goal**: Add `get_migration_contexts` tool so engineers can list all prior contexts for a project, identify the wrong triple, and abandon stale ones before starting a clean session. Add `updatedAt` to every state-changing write on MigrationContext.

**⚠️ WORKSTREAM ORDERING**: T013 and T019 depend on T007 (US1) being complete. T007 writes the resolved UPGRADES_TO ceil node and returns `upgrades_to_version`/`rounded`/`aheadOfCatalogue` — T019 adds those fields to the idempotent MERGE response. Do not begin T013-T020 until T007 is merged (TASK-GAP-002).

**Independent Test**: Create a context for `project-X 3.5.12→4.0.0`. Call `get_migration_contexts(project-X)` — verify response includes the context with `id`, `fromVersion`, `toVersion`, `status`, `createdAt`, `updatedAt`, `outcome_counts`. Call `close_migration_context(id, final_status="abandoned")` — verify status becomes `abandoned` and `updatedAt` is updated. Create `project-X 3.5.12→4.0.6` — verify `created: true`. Call `get_migration_contexts` for a project with no contexts — verify `count: 0`, empty list, no error.

- [X] T013 [US2] Add `updatedAt = datetime()` and `deferredSteps = []` initialization to `_CREATE_OR_GET_CONTEXT` Cypher (ON CREATE SET and ON MATCH SET both write `updatedAt`; `deferredSteps` initialized on CREATE only) in `migration_oracle/mcp/graph/queries/context.py`
- [X] T014 [US2] Add `_GET_MIGRATION_CONTEXTS` Cypher to `migration_oracle/mcp/graph/queries/context.py` — match on `projectId` with optional `framework` filter, OPTIONAL MATCH STEP_OUTCOME relationships, WITH count CASE expressions for completed/failed/skipped/deferred, RETURN id/projectId/fromVersion/toVersion/framework/status/createdAt/updatedAt/outcome_counts ORDER BY createdAt DESC (per contract: `get_migration_contexts.md`)
- [X] T015 [US2] Implement `get_migration_contexts(project_id, framework=None)` MCP tool in `migration_oracle/mcp/tools/context.py` — returns `{status, project_id, count, contexts[]}` per contract; returns `count: 0` with empty list (not error) when no contexts exist; validates `project_id` not empty
- [X] T016 [US2] Add FR-B08 concurrent conflict detection to `create_or_get_context` in `migration_oracle/mcp/tools/context.py` — catch `neo4j.exceptions.ConstraintError` and return `{status: "error", error_code: "conflict_error", hint: "..."}` instead of propagating the exception
- [X] T017 [P] [US2] Add `ctx.updatedAt = datetime()` to `close_migration_context` Cypher in `migration_oracle/mcp/graph/queries/context.py`
- [X] T018 [P] [US2] Add `ctx.updatedAt = datetime()` to `_AUTO_CLOSE_WRITE` Cypher in `migration_oracle/mcp/graph/queries/context.py`
- [X] T019 [US2] Update `create_migration_context` tool response in `migration_oracle/mcp/tools/context.py` — idempotent MERGE second call returns `created: false`, stored identity strings, `upgrades_to_version`, `rounded`, `aheadOfCatalogue` so engineer can detect triple mismatch without a separate query (FR-B06)
- [X] T020 [US2] Update Loop I Step 1 in `migration_oracle/mcp/skills/framework_migration_main.md` — replace implicit context-check narrative with explicit supersede flow: call `get_migration_contexts`, if count=0 proceed to scan+create; if count>0 surface list; for wrong-triple in-progress contexts call `close_migration_context(final_status="abandoned")`; for matching triple resume via MERGE match path; for completed triple surface summary and stop (per `get_migration_contexts.md` Loop I Integration section)
- [X] T021 [US2] Write pytest integration tests for context lifecycle in `tests/mcp/test_get_migration_contexts.py` — `get_migration_contexts` with zero contexts returns `{count: 0, contexts: []}` (not an error — TASK-GAP-008); `get_migration_contexts` with one/many contexts returns full shape per contract; `updatedAt` set on create, match, close, and STEP_OUTCOME write; `deferredSteps` initialized as `[]` on create; create same triple twice returns `created: false` with stored identity strings on second call (idempotent MERGE — TASK-GAP-008); conflict error when MERGE constraint violated; Loop I supersede: stale context abandoned, correct triple created with `created: true`

**Checkpoint**: US2 complete — engineers can list, inspect, and supersede stale contexts.

---

## Phase 5: US3 — Resume Scan Fidelity (Priority: P2)

**Goal**: Enforce the allow-list filter server-side on both the CREATE and the MERGE MATCH path of `create_migration_context`. Application-class entities injected into a stored context are purged on re-entry and reported via `droppedCount`.

**Independent Test**: Create a context. Directly inject a non-allow-listed entity (e.g. `com.paysafe.wallet.SomeService`) into `ctx.scannedEntities`. Call `create_migration_context` again with the same triple (MERGE match path). Verify the response excludes the injected entity, `droppedCount > 0`, and the stored entity set in Neo4j no longer contains the injected entity.

- [X] T022 [US3] Add server-side allow-list enforcement on MATCH path in `migration_oracle/mcp/graph/queries/context.py` — in `_CREATE_OR_GET_CONTEXT` ON MATCH SET, overwrite all six scanned entity buckets (scannedEntities, scannedClasses, scannedClassSimple, scannedDepsGa, scannedDepArtifacts, scannedProps) with the caller-supplied values filtered through the allow-list; the old bucket values must not survive (FR-B04)
- [X] T023 [US3] Update `create_migration_context` tool handler in `migration_oracle/mcp/tools/context.py` — apply allow-list filter to incoming `scanned_entities` before passing to Cypher on BOTH create and match paths; compute `droppedCount = len(input) - len(filtered)`; include `droppedCount` in response (FR-B05); server does not trust the caller to pre-filter
- [X] T024 [US3] Write pytest integration tests in `tests/mcp/test_context.py` (extend existing file) — create context with clean entities; inject non-allow-listed entity (`com.paysafe.wallet.SomeService`); call create again with same triple (MERGE match path); assert response `droppedCount > 0`; assert Neo4j stored set excludes injected entity; assert allow-list enforcement runs on create path too (droppedCount=0 when all entities pass); assert target-above-catalogue version is clamped and `aheadOfCatalogue: true` returned (TASK-GAP-008)

**Checkpoint**: US3 complete — entity sets are always allow-list clean on context re-entry.

---

## Phase 6: US4 — Recipe-Aware Execution Routing (Priority: P2)

**Goal**: Replace the `automatable` boolean gate in Loop III with the deterministic 7-row executor-selection decision table. Add the agent-codemod executor track for mechanical/moderate steps that have a concrete instruction and entity anchor but no recipe. The `automatable` flag becomes metadata only.

**Independent Test**: Create a migration step with `automatable=true`, effort=mechanical, a concrete instruction (e.g. `rename com.fasterxml.jackson.* to tools.jackson.*`), an entity anchor, and no `AUTOMATED_BY` edge. Trigger execution routing. Verify the step enters the agent-codemod track (not deferred). Verify the engineer is shown all affected files before any changes are applied. Verify a deliberately failed build+test gate triggers rollback and marks the step `failed` without halting remaining steps.

- [X] T025 [US4] Update `_VALID_OUTCOMES` set in `update_step_status` tool handler in `migration_oracle/mcp/tools/context.py` — add `"deferred"` as the fourth valid outcome value alongside `completed | skipped | failed` (additive extension per FR-D05)
- [X] T054 [US4] Extract executor-selection logic into `migration_oracle/mcp/routing.py` — implement `select_executor(step: dict) -> Literal["openrewrite","prompted-auto","agent-codemod","human-review"]` (7-row decision table, `automatable` flag ignored as routing input) and `is_concrete_instruction(instruction: str) -> bool` (returns True only when the instruction contains a before/after example, named op with source+target, or a pattern+replacement; free-text-only returns False). These functions are the testable Python target for T029 and the authoritative implementation referenced by the skill markdown. **T054 must complete before T029** (TASK-GAP-01).
- [X] T026 [US4] Replace the existing Loop III condition routing table with the 7-row executor-selection decision table in `migration_oracle/mcp/skills/framework_migration_main.md` — rows: (1) fully-resolved recipe → OpenRewrite; (2) partially-resolved recipe → Prompted-auto; (3) no recipe + mechanical + concrete instruction + entity anchor → Agent-codemod; (4) no recipe + moderate + concrete instruction + entity anchor → Agent-codemod; (5) no recipe + mechanical + no instruction → Human-review; (6) no recipe + moderate + no instruction → Human-review; (7) no recipe + architectural → Human-review; reference `migration_oracle/mcp/routing.py` as the authoritative implementation; make explicit that `automatable` flag is never a routing input (FR-C01, FR-C02, FR-C03)
- [X] T027 [US4] Add agent-codemod executor section to Loop III in `migration_oracle/mcp/skills/framework_migration_main.md` — full 5-step protocol per `contracts/agent_codemod_executor.md`: (1) blast-radius gate with file list presentation and `blast_radius_confirm_threshold=0` default (always confirm); (2) idempotency check — mark completed without changes if already applied; (3) apply full transformation to all matched files; (4) build+test gate — mark completed on pass; (5) on gate failure: rollback all touched files via `skill://framework-migration/rollback`, call `update_step_status(outcome="failed", reason="build failed: <error>")`, continue remaining tier steps (do NOT halt session), add to Loop IV backlog
- [X] T028 [US4] Add FR-D06 eval coverage notes to `migration_oracle/mcp/skills/framework_migration_main.md` — note that the three round-1 fix paths require explicit eval cases before ISSUE-005/013/003 are treated as validated: (1) rollback skill execution triggered by deliberately failing automated step; (2) stateless-fallback Loop IV variant triggered by context-creation failure injection; (3) `get_steps_for_scope_tier` severity threshold filtering verified at both `high` and `low` thresholds with a mixed-severity fixture
- [X] T029 [US4] Write pytest unit tests targeting `migration_oracle/mcp/routing.py` in `tests/mcp/test_executor_routing.py` — all 7 `select_executor()` rows return the correct track string; `automatable=True` flag with no recipe does not select an automated track; `is_concrete_instruction()` returns False for free-text, True for rename/replace patterns; idempotency check produces `completed` without file writes when target state already matches (FR-C10, TASK-GAP-01, TASK-GAP-08). Note: T049 and T050 test agent-driven skill procedures (rollback, stateless Loop IV) — those are eval-framework scenarios, not pytest (see Phase 10).

**Checkpoint**: US4 complete — every mechanical migration step with a concrete instruction is attempted, not silently deferred.

---

## Phase 7: US5 — Bridge Tracking (Priority: P2)

**Goal**: Add the `deferred` STEP_OUTCOME status backed by `BRIDGED_BY` graph discoverability. Bridge-deferred steps appear in the Loop IV backlog, survive context re-entry, and are auto-resolved when their `requiredChange` step is completed. Ad-hoc bridges are rejected.

**Independent Test**: Create a MigrationRule with a `BRIDGED_BY` edge to a Dependency. Call `update_step_status(outcome="deferred", reason={bridgeName, bridgeReason, requiredChange: <step_elementId>})` — verify `STEP_OUTCOME` edge has `status="deferred"` AND `ctx.deferredSteps` contains the step's elementId. Call `get_migration_contexts` — verify `outcome_counts.deferred=1`. Re-enter the context — verify deferred step is in the Loop IV backlog. Mark `requiredChange` completed — verify the deferred step's `STEP_OUTCOME` edge is updated to `status="completed"`, `resolvedVia="bridge"`, `bridgeResolvedAt` set, and removed from `deferredSteps`.

- [X] T030 [US5] Update `_RECORD_STEP_OUTCOME` Cypher in `migration_oracle/mcp/graph/queries/context.py` — add `ctx.updatedAt = datetime()` to the SET clause; add `deferredSteps` CASE arm: `ctx.deferredSteps = CASE $outcome WHEN 'deferred' THEN coalesce(ctx.deferredSteps,[]) + [$step_id] ELSE coalesce(ctx.deferredSteps,[]) END`; STEP_OUTCOME edge write and array append MUST be in the SAME SET clause (PLAN-05 contract)
- [X] T031 [US5] Add bridge discoverability check to `update_step_status` handler in `migration_oracle/mcp/tools/context.py` — when `outcome="deferred"`, run Cypher to verify rule has at least one `BRIDGED_BY` edge; reject with `{error_code: "bridge_not_in_graph"}` if no edge found; also validate `r.ruleType IN edge.applicableRuleTypes` (per data-model.md §3.2); only proceed if discoverability confirmed (FR-C11)
- [X] T032 [US5] Add deferred auto-resolve check to `update_step_status` handler in `migration_oracle/mcp/tools/context.py` — when `outcome="completed"` for any step, check if `ctx.deferredSteps` contains any entry whose stored `reason.requiredChange` equals the just-completed step's elementId; if found: **parse `reason` JSON in Python** (NOT via `apoc.convert.fromJsonMap` — APOC is not declared), extract `required_change_step_id` and pass as a Cypher parameter; set `STEP_OUTCOME.status="completed"`, `resolvedVia="bridge"`, `bridgeResolvedAt=datetime()` on the deferred edge; remove step from `deferredSteps`, add to `completedSteps`. **Do NOT use `status="bridgeResolved"`** — that value is not in the STEP_OUTCOME enum and would break `outcome_counts` CASE expressions (TASK-GAP-03, TASK-GAP-04)
- [X] T033 [US5] Update `_GET_PENDING_STEPS` Cypher in `migration_oracle/mcp/graph/queries/context.py` — add `AND NOT elementId(s) IN coalesce(ctx.deferredSteps, [])` to the WHERE clause so deferred steps do not re-appear in the pending queue until resolved (Workstream C step 6)
- [X] T034 [US5] Add bridge/deferred section to Loop III in `migration_oracle/mcp/skills/framework_migration_main.md` — describe when engineer applies a bridge instead of the real change: (a) verify bridge discoverability from graph BEFORE recording outcome; (b) `requiredChange` is the elementId of the real-change MigrationStep (not free text); (c) call `update_step_status(outcome="deferred", reason=json(bridgeName, bridgeReason, requiredChange=<step_elementId>))`; (d) on `bridge_not_in_graph` rejection: route step to human-review instead (FR-C05, FR-C06, FR-C11)
- [X] T035 [US5] Update Loop IV backlog emission in `migration_oracle/mcp/skills/framework_migration_main.md` — extend backlog to include `deferredSteps` alongside `skippedSteps`; emit each deferred entry as an active backlog item showing `bridgeName`, `bridgeReason`, and `requiredChange`; make clear that deferred steps are NOT finished and must remain visible on every re-entry until `requiredChange` is completed (plan.md Workstream C step 5c)
- [X] T036 [US5] Write pytest unit tests in `tests/mcp/test_bridge_tracking.py` — `update_step_status(outcome="deferred")` accepted when rule has `BRIDGED_BY` edge; rejected with `bridge_not_in_graph` when no edge; after `outcome="deferred"`: STEP_OUTCOME edge status="deferred" AND `ctx.deferredSteps` contains step elementId (PLAN-05: both in same transaction); `get_pending_steps` excludes deferred steps; auto-resolve: mark requiredChange completed → deferred step's STEP_OUTCOME edge has **`status="completed"`, `resolvedVia="bridge"`, `bridgeResolvedAt` is set** (NOT `status="bridgeResolved"`) and step is removed from `deferredSteps`; attempt to apply bridge to already-`completed` step is rejected (TASK-GAP-03)

**Checkpoint**: US5 complete — bridge-deferred items are tracked, visible, and auto-resolved.

---

## Phase 8: US6 — Typed Dependency Resolution Failures (Priority: P3)

**Goal**: Classify Paysafe resolver failures as `auth_error` (401/403/missing credential) vs `transport_error` (timeout/ConnectionError/5xx) instead of a generic `status: "error"`. Include `remediationSteps`, `unresolvedDependencies`, and `fallbackInstructions` in both variants. Add Loop II fallback rows.

**Independent Test**: Configure the resolver with an invalid `FINDIT_AUTH_TOKEN` (HTTP 401 trigger). Call `resolve_paysafe_dependency_by_service_name`. Verify response `status="RESOLUTION_FAILED"`, `subStatus="auth_error"`, `remediationSteps` names `FINDIT_AUTH_TOKEN` and `GITLAB_API_KEY`, and `unresolvedDependencies` lists the service name. Repeat with a simulated timeout — verify `subStatus="transport_error"`.

- [X] T037 [US6] Update `migration_oracle/paysafe/resolver.py` — map HTTP 401/403 from FindIt/GitLab and absent/empty `FINDIT_AUTH_TOKEN` → `RESOLUTION_FAILED` outer envelope with `subStatus="auth_error"`, `remediationSteps`, `unresolvedDependencies`, `fallbackInstructions`; map `requests.exceptions.Timeout`, `ConnectionError`, HTTP 5xx → `subStatus="transport_error"` with connectivity-focused `remediationSteps`; existing `service_not_found`/`no_tags_found`/`no_parseable_tags` error codes unchanged (per `contracts/paysafe_auth_error.md`)
- [X] T038 [P] [US6] Update `migration_oracle/mcp/tools/paysafe.py` — pass through the new `RESOLUTION_FAILED` structure from the resolver without transformation (no logic change; resolver returns dicts)
- [X] T039 [US6] Add `query_handoff_threshold` parameter and Loop II fallback rows to `migration_oracle/mcp/skills/framework_migration_main.md` — parameter: `query_handoff_threshold: int = 0` (0 = all tiers queried before execution); fallback rows: on `subStatus="auth_error"` log remediationSteps + emit unresolvedDependencies as backlog items + surface fallbackInstructions + continue; on `subStatus="transport_error"` same; test-scope (tier 4) always executes last regardless of threshold (FR-D03, FR-D04, per contract `paysafe_auth_error.md`)
- [X] T040 [P] [US6] Write pytest unit tests for resolver in `tests/paysafe/test_resolver_typed_errors.py` — HTTP 401 maps to `subStatus="auth_error"`; absent `FINDIT_AUTH_TOKEN` maps to `auth_error` with `remediationSteps` naming the specific env var; timeout maps to `transport_error`; `unresolvedDependencies` is populated in both variants; `fallbackInstructions` is present; existing `service_not_found` error code is unchanged (backward-compat guard, TASK-GAP-009)

**Checkpoint**: US6 complete — engineers get actionable typed error responses from the Paysafe resolver.

---

## Phase 9: US7 — Portable Codebase Scanning (Priority: P3)

**Goal**: Position the Python scanner (`re` + `pathlib`) as the canonical extraction path for all entity types. The bash (`grep -E`) patterns become an optional fast path. All extractors must work on macOS/BSD and GNU/Linux. PyYAML absence degrades gracefully. Every scan response includes `extractorPath`.

**Independent Test**: Run the Python canonical extractor against a Java fixture directory on macOS (BSD utils). Verify it completes without error and returns the correct entity list. Run again with PyYAML absent — verify scan still completes, logs a warning, and `extractorPath="python"` is in the response.

- [X] T041 [P] [US7] Rewrite `migration_oracle/mcp/skills/framework_migration_scanning.md` as Python-canonical scanner — document Python-first extractors for all entity types: Java imports/annotations (`re` + `pathlib.rglob("*.java")`), `.properties` (`re.match`), `.yml`/`.yaml` (`yaml.safe_load` with PyYAML, `re` fallback), Maven `pom.xml` (`xml.etree.ElementTree`), Gradle `build.gradle` (`re` for implementation/api/compile), Angular `package.json`/`angular.json` (`json.loads`), WildFly XML (`xml.etree.ElementTree`); include the canonical Python extractor code block per plan.md Workstream E step 1 with `ALLOW_LIST` regex and `IMPORT_RE`; document optional `grep -E` fast path for both GNU and BSD with correct BSD-compatible flags (`-E` not `-P`) — mark it as optional, not primary (FR-E01)
- [X] T042 [US7] Add PyYAML degrade path to `migration_oracle/mcp/skills/framework_migration_scanning.md` — `try: import yaml` / `except ImportError: fallback to re line-scan for .properties only, log "PyYAML absent — YAML property extraction skipped; .properties files parsed only"`; Java class/dependency extraction unaffected (FR-E02)
- [X] T043 [US7] Add Loop I Step 0 preflight to `migration_oracle/mcp/skills/framework_migration_main.md` — before codebase scan: (a) `python3 --version` to confirm Python 3 available, warn and offer grep fast path if absent; (b) `python3 -c 'import yaml'` to check PyYAML, log `"PyYAML: present|absent"`; (c) report chosen extractor; (d) log `"Preflight complete. Extractor: {path}, PyYAML: {present|absent}"`
- [X] T044 [US7] Add `extractorPath` field to scan result returned in Loop I step 3 in `migration_oracle/mcp/skills/framework_migration_scanning.md` — values: `"python"` (canonical), `"grep-gnu"`, `"grep-bsd"`; always present in scan response (FR-E03)
- [X] T045 [P] [US7] Write pytest unit tests for scanning in `tests/extractors/test_spring_boot_scanner.py` (extend existing) — Python canonical extractor produces correct entity list from Java fixture directory; allow-list filters non-matching imports; PyYAML absent does not abort scan (`extractorPath="python"` still returned in result); scanner output is identical on both macOS-BSD and GNU-Linux paths (fixture-based, not platform-conditional)

**Checkpoint**: US7 complete — scanning works on macOS and Linux, degrades gracefully without PyYAML.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Package-prefix entity matching, version map delta, schema documentation, eval coverage, and Jackson transitive-dep fix.

- [X] T046 [P] Add package-prefix match bridge (FR-C07, ISSUE-027) to entity-matching CASE in `_GET_PENDING_STEPS`, `_GET_STEPS_FOR_SCOPE_TIER`, and `_ANALYZE_UPGRADE_PATH` Cypher in `migration_oracle/mcp/graph/queries/context.py` and `migration_oracle/mcp/graph/queries/upgrade.py`. Implement as a **single-tier fallback for Dependency-only rules** (no `[:AFFECTS]->(:Class)` edge): if the rule has Class nodes, plain exact-match on scannedClasses already fires — that case needs no change. The fallback covers the real Jackson scenario (ISSUE-027): rule has a Dependency GA coord but NO Class node. In that case, try a **truncated-groupId prefix**: strip the last dot-segment of the groupId to get the umbrella package root (`com.fasterxml.jackson.core` → strip `.core` → `com.fasterxml.jackson.`), then check `cls STARTS WITH truncated_prefix`. Cypher: `left(gid, size(gid) - size(split(gid,'.')[size(split(gid,'.'))-1]) - 1) + '.'` where `gid = split(e.name,':')[0]`. Match result is `"matched"` not `"uncertain"`. This is a heuristic — document it as such; groupId segment-stripping is correct for Jackson, Spring, Hibernate, and all major frameworks whose groupId segment matches their package root minus one layer. **Known edge case**: two-segment groupIds (e.g. `io.undertow`) strip to `io.`, which over-matches — any FQCN beginning with `io.` would be considered matched. This errs toward surfacing rather than silencing, which is the safe direction; note it inline in the Cypher so future maintainers know it is intentional (TASK-GAP-02).
- [X] T047 [P] Update `migration_oracle/mcp/skills/framework_migration_version_map.md` — (a) add Spring Cloud train table (6 trains: Hoxton through Oakwood) with calVer sortableVersion formula and BOM-only Oakwood note; (b) add Boot 4.0.6 row (`sortableVersion=4000006, status="active"`); (c) add calVer normalization rule (`YEAR×1_000_000 + MINOR×1_000 + PATCH`); (d) fix Spring Cloud detection signal (scan `scannedDepsGa`/`scannedClasses` for `org.springframework.cloud`, NOT `UPGRADES_FROM` — PLAN-07 fix); (e) add toolchain-gate minor-line decoupling note (Java version checked only on minor change, not every patch)
- [X] T048 [P] Update `docs/graph-schema.md` — add new MigrationContext properties to property table: `updatedAt` (datetime), `deferredSteps` (list[string]), `queriedEntities` (string JSON), `scannedClasses`, `scannedClassSimple`, `scannedDepsGa`, `scannedDepArtifacts`, `scannedProps` (all list[string]); update STEP_OUTCOME `status` enum to include `"deferred"`; add two new STEP_OUTCOME edge properties: `resolvedVia` (string, e.g. `"bridge"`) and `bridgeResolvedAt` (datetime) — written by auto-resolve in T032; add `BRIDGED_BY` relationship type with edge properties (`removalCondition`, `bridgeReason`, `applicableRuleTypes`) and cardinality note (0..N per rule) (PLAN-GAP-004)
- [X] T049 [P] Eval lane A — rollback execution (FR-D06 / ISSUE-005). **This is an agent-in-the-loop eval scenario, not a pytest test.** Create the eval scenario definition in `tests/mcp/eval/eval_rollback_scenario.yaml` (or equivalent eval-framework format): fixture = a MigrationStep with a build-breaking transformation; entry point = route step to agent-codemod executor; assertions = rollback skill fires and restores all modified files to pre-change state, step `STEP_OUTCOME.status="failed"` with failure reason, harness continues with remaining tier steps (does NOT halt). This exercises the rollback skill code path that was not validated by the first real run (TASK-GAP-01, TASK-GAP-007a, SC-008).
- [X] T050 [P] Eval lane B — stateless-fallback Loop IV (FR-D06 / ISSUE-013). **Agent-in-the-loop eval scenario, not pytest.** Create the eval scenario definition in `tests/mcp/eval/eval_stateless_fallback_scenario.yaml`: fixture = inject a `create_migration_context` error response; entry point = start Loop IV without a stored context; assertions = Loop IV completes in stateless-fallback mode, step backlog is surfaced to engineer, no exception propagates. Exercises the stateless Loop IV fallback path unvalidated by the first real run (TASK-GAP-01, TASK-GAP-007b, SC-008).
- [X] T051 [P] Eval lane C — severity threshold filtering (FR-D06 / ISSUE-003) in `tests/mcp/test_get_steps_for_scope_tier.py` (extend existing file): create a fixture with mixed-severity steps (`high`, `medium`, `low`) in one scope tier; query at `severity_threshold="high"` → only high-severity steps returned; query at `severity_threshold="low"` → all severity steps returned; assert counts match fixture (TASK-GAP-007c, SC-008)
- [X] T052 [P] E2E replay test — paysafe-wallet-switch 3.5.12→4.0.6 in `tests/mcp/test_e2e_real_run.py`: against live Neo4j with seeded Version nodes (T001/T002 complete): (1) call `get_migration_contexts(paysafe-wallet-switch)` — verify count=0 (no stale context); (2) call `create_migration_context(projectId="paysafe-wallet-switch", fromVersion="3.5.12", toVersion="4.0.6", framework="Spring Boot", scannedEntities=[...])` — verify `created: true`, `fromVersion="3.5.12"` (not truncated), `toVersion="4.0.6"`, `droppedCount=0`; (3) call `check_version_availability` and `submit_migration_insight` for `(Spring Boot, 3.5.12)` — verify both return same `nodeId` (SC-001); (4) confirm the Jackson FQCN rule (if seeded) is matched via package-prefix bridge (not `uncertain`); (5) confirm any `automatable=true`/no-recipe/mechanical step is routed to agent-codemod (not silently deferred) (TASK-GAP-005, SC-001–SC-004)
- [X] T053 [P] Jackson acceptance test in `tests/mcp/test_jackson_package_prefix.py`: seed a **Dependency-only** MigrationRule — `(r:MigrationRule)-[:AFFECTS_DEPENDENCY]->(d:Dependency {name:"com.fasterxml.jackson.core:jackson-databind"})` with NO `[:AFFECTS_CLASS]->(:Class)` node (this is the ISSUE-027 actual scenario: a transitive dep the project never declares directly); create a context with `scannedClasses=["com.fasterxml.jackson.databind.ObjectMapper"]` (the FQCN the project actually imports); call `get_pending_steps` (or `_GET_PENDING_STEPS` Cypher directly); assert the rule appears with `applicability="matched"` (NOT `"uncertain"`) — meaning the truncated-groupId prefix bridge fired (`com.fasterxml.jackson.core` → `com.fasterxml.jackson.` → matches `com.fasterxml.jackson.databind.ObjectMapper`); also assert a MigrationStep for this rule with `effort="mechanical"`, a concrete `rename` instruction, and no `AUTOMATED_BY` edge is routed to the agent-codemod track. **Do NOT seed a Class node** — seeding a Class node causes plain exact-match to fire, masking whether the truncated-prefix fallback actually works (TASK-GAP-02)
- [X] T055 Fix `specs/013-real-run-hardening/data-model.md` §3.2 BRIDGED_BY edge property — rename `requiredClassification: "required"` → `applicableRuleTypes: List[String]` (matches `tasks.md` T031, T048, and all Cypher references); add one-line note: `applicableRuleTypes` is a list of eligible `ruleType` values that may be bridged by this dependency — use values from the ruleType enum (`breaking`, `deprecation`, `behavioral`, `mandatory_migration`, `community_insight`); e.g. `["mandatory_migration","breaking"]`. Cross-ref: TASK-GAP-05.
- [X] T056 Update `specs/013-real-run-hardening/contracts/agent_codemod_executor.md` §Execution Protocol step 1c — the contract currently says "No file-count threshold overrides this default." Remove that line; align with T027 wording: `blast_radius_confirm_threshold=0` is the out-of-the-box default meaning always-confirm; a project may set a non-zero threshold to allow auto-confirmation for small scopes (FR-C09); document that `blast_radius_confirm_threshold=0` requires confirmation for ANY file count. Cross-ref: TASK-GAP-08.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — seed scripts can run immediately
- **Foundational (Phase 2)**: No code dependencies — dataclasses are greenfield additions
- **US1 (Phase 3)**: Depends on Phase 2. Within Phase 3: T003 → T004 → (T005/T006/T007/T008/T009 fan out) → T010/T011/T012
- **US2, US3, US4, US5 (Phases 4–7)**: All depend on US1 completion (resolve_version + T007 UPGRADES_TO linking must exist — TASK-GAP-002)
- **US5 (Phase 7)**: Also depends on US2 completion (T030 needs `deferredSteps` from T013) and US4 completion (T025 adds `"deferred"` to valid outcomes needed by T031–T032)
- **US6 (Phase 8)**: Independent — can start after Phase 1 at any time
- **US7 (Phase 9)**: Independent — can start after Phase 1 at any time
- **Polish (Phase 10)**: T046 (package-prefix Cypher) depends on US4/US5. T047/T048 are documentation-only and can proceed once their respective workstreams are underway. T049–T053 are tests that require all relevant implementation complete. T055 (data-model fix) and T056 (contract doc fix) are documentation-only and have no code dependencies — they can be done any time.

### User Story Dependencies

- **US1 (P1)**: Foundational — blocks US2, US3, US4, US5
- **US2 (P1)**: Depends on US1. No dependency on US3/US4/US5.
- **US3 (P2)**: Depends on US1. No dependency on US2/US4/US5.
- **US4 (P2)**: Depends on US1. No dependency on US2/US3.
- **US5 (P2)**: Depends on US1, US2 (deferredSteps init), and US4 (deferred in valid outcomes).
- **US6 (P3)**: Independent.
- **US7 (P3)**: Independent.

### Within Each User Story

- Query/Cypher layer tasks before tool/handler tasks
- Skill/markdown tasks are independent and can run in parallel with Python implementation
- Tests after implementation (unit tests can be written against the interface before full integration)

### Parallel Execution Groups

**Group 1 (after Phase 1, independent of all workstreams)**:
- Entire Phase 8 (US6: T037–T040) in parallel with other phases
- Entire Phase 9 (US7: T041–T045) in parallel with other phases — T041 is marked [P] (TASK-GAP-004)
- T047 (version-map delta, skill-only edit to `framework_migration_version_map.md`) in parallel with all Python workstreams (TASK-GAP-004)

**Group 2 (after US1 complete)**:
- Phase 4 (US2) and Phase 5 (US3) can run in parallel
- Phase 6 (US4) can run in parallel with US2 and US3

**Group 3 (within Phase 3, US1)**:
- T005, T006, T007, T008, T009 all parallel after T004 completes (different files/functions)
- T008 and T009 additionally share a file (`upgrade.py`) — coordinate to avoid merge conflicts

**Group 4 (Phase 10, Polish)**:
- T046, T047, T048, T049, T050, T051, T052, T053, T055, T056 all parallel (different files)

**Skill file concurrency note (TASK-GAP-004)**: T020, T026, T027, T028, T034, T035, T039, T043 all edit `migration_oracle/mcp/skills/framework_migration_main.md`. They are independent of Python implementation tasks (different files) and can be done by a separate developer, but must be applied sequentially to avoid merge conflicts on the skill file. Each should be committed as a separate patch. Skill file edits (T041, T042, T044, T047) that target OTHER skill files are safe to run in parallel with the main.md edits.

---

## Parallel Example: US1

```bash
# T003 must be merged first (dataclasses).
# T004 (resolve_version) must be merged before any tool delegation.
# After T004 completes, all of these can run in parallel:
Task T005: Update check_version_availability   # upgrade.py
Task T006: Update submit_migration_insight     # upgrade.py (different function, coordinate)
Task T007: Update create_migration_context     # context.py (different file — fully independent)
Task T008: Update analyze_upgrade_path         # upgrade.py (coordinate with T005/T006)
Task T009: Update build_recipe_plan            # upgrade.py (coordinate with T005/T006/T008)
Task T011: Unit+near-miss tests                # tests/mcp/test_resolve_version.py
Task T012: Integration + ISSUE-016 regression  # tests/mcp/test_resolve_version.py (same file, sequential)
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (seed catalogue data)
2. Complete Phase 2: Foundational (dataclasses)
3. Complete Phase 3: US1 (resolve_version + all tool delegation)
4. **STOP and VALIDATE**: `check_version_availability` and `submit_migration_insight` return same nodeId for 3.5.12 — SC-001 satisfied
5. Complete Phase 4: US2 (get_migration_contexts, supersede flow)
6. **STOP and VALIDATE**: engineer can list, inspect, and abandon stale contexts

### Incremental Delivery

1. Setup + Foundational + US1 → version contradiction eliminated (ISSUE-016, ISSUE-017 fixed) — ISSUE-016 regression gate in T012
2. Add US2 → context discovery and supersede (ISSUE-018 fixed)
3. Add US3 → resume scan fidelity (ISSUE-019 fixed)
4. Add US4 → recipe-aware routing with agent-codemod track (ISSUE-020, ISSUE-029 fixed)
5. Add US5 → bridge tracking (ISSUE-021 fixed)
6. Add US6 → typed dep resolution errors (ISSUE-022 fixed)
7. Add US7 → portable scanning (ISSUE-026 fixed)
8. Polish → package-prefix matching (T046), version map (T047), schema docs (T048), three eval lanes (T049/T050/T051), E2E replay (T052), Jackson acceptance (T053), data-model fix (T055), contract doc fix (T056) → ISSUE-024, ISSUE-025, ISSUE-027, ISSUE-028, ISSUE-030 fixed

### Parallel Team Strategy

With two developers:
- **Dev A**: US1 → US2 → US3 (Workstream A→B chain)
- **Dev B**: US6 + US7 (independent Workstreams D+E) in parallel with Dev A's US1, then US4 → US5 after US1 merges

---

## Notes

- [P] tasks = different files or independent within the same file (no intra-story write conflict)
- Each user story is independently completable and verifiable before moving to the next
- Tests are included because the plan.md explicitly specifies a testing strategy with named test files
- **Test directories**: use `tests/mcp/` for MCP tool tests, `tests/paysafe/` for resolver tests, `tests/extractors/` for scanner tests. `tests/mcp/eval/` is allowed for eval-framework scenario YAML files (T049/T050) — it does not exist yet and must be created. There are no `unit/` or `integration/` subdirs.
- `to_minor_zero` appears in multiple tools — T005–T009 collectively remove all call sites; do not leave any behind
- T004 (`resolve_version`) is the single highest-priority task — blocks T005–T012 within US1, and US2/US3/US4/US5 transitively (TASK-GAP-001)
- T007 (create_migration_context, UPGRADES_TO ceil-node write) must merge before Phase 4 begins (TASK-GAP-002)
- Skill file edits (multiple tasks on `framework_migration_main.md`) must be applied sequentially to that file but can be done by a separate developer in parallel with Python implementation (TASK-GAP-004)
- T049/T050/T051 are the three dedicated FR-D06 eval lanes — each covers exactly one previously-unvalidated round-1 fix path (TASK-GAP-007)
- T052 is the E2E replay test against the actual 3.5.12→4.0.6 scenario (TASK-GAP-005)
- T053 is the Jackson acceptance test: package-prefix bridge produces `matched` (not `uncertain`) and agent-codemod import rename completes (TASK-GAP-010)
- Do not modify `STEP_OUTCOME` edge shape or remove existing outcome values — `deferred` is additive only (FR-D05)
- T012 is an ISSUE-016 regression gate — must pass for every seeded (framework, version) pair before the spec is considered delivered (TASK-GAP-006)
- **FR-A12, FR-B08, FR-C11 are confirmed present in `specs/013-real-run-hardening/spec.md`** — FR-A12 = Spring Cloud co-migration warning (referenced by T010); FR-B08 = concurrent conflict detection (referenced by T016); FR-C11 = bridge discoverability gate (referenced by T031, T034). No new tasks required to add them (TASK-GAP-06).
- **PLAN-12 legacy context limitation** (accepted, not implemented): Pre-round-2 contexts with only legacy arrays (`ctx.completedSteps`, etc.) and no `STEP_OUTCOME` edges will report `outcome_counts: {completed:0, failed:0, skipped:0, deferred:0}` in `get_migration_contexts`, even when those arrays are non-empty. This is a known limitation — no task in this spec implements a `legacyContext` flag or a backfill. The `get_migration_contexts` contract doc (§Back-Compatibility Note) documents the limitation and the two mitigation options (flag vs. backfill) for a future increment. T021 tests should use only freshly-created STEP_OUTCOME contexts so this limitation does not affect test assertions (TASK-GAP-09).
- **T010 co-migration text cross-check** (TASK-GAP-10): T010's Python logic (reading `scannedDepsGa`/`scannedClasses`) is safe and independent of Phase 10. However, the warning message text referencing Oakwood/BOM details should be cross-checked against T047 (Phase 10, Spring Cloud train table) before declaring US1 fully delivered. If T047 reveals Oakwood import-mode details that differ from T010's draft message, update T010's copy accordingly.

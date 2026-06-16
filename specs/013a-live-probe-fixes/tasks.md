---
description: "Task list for 013a-live-probe-fixes"
---

# Tasks: Live Probe Fixes

**Input**: Design documents from `specs/013a-live-probe-fixes/` (`spec.md`, `research.md`)

**Prerequisites**: spec.md ✅, research.md ✅

> **FR numbering**: Requirement IDs keep the `FR-014-xxx` prefix used in `spec.md` so tasks trace 1:1 to the spec. The *feature/branch/directory* name is `013a-live-probe-fixes`. (If you prefer, `spec.md`/`research.md` can be realigned to `FR-013a-xxx` — flagged in the Notes.)

**Organization**: Tasks run in the order `spec.md §Implementation order` prescribes, with one change forced by review: **diagnosis precedes design.** Phase 0 (provenance + live-path diagnosis) is a hard gate. The SYS-1 fix in Phase 1 *branches on Phase 0's finding* — we do not assume the cause is a stale DB record, because the probe evidence (normalisation observed in `analyze_upgrade_path`, which has no context node) points at a live normalisation code path, not a zombie context. Everything else is downstream of a correct, deployed version-resolution path.

## Format: `[ID] [P?] [FR] Description`

- **[P]**: Can run in parallel (different files, no intra-task dependency)
- **[FR]**: Which functional requirement this task implements
- **[BRANCH-A]/[BRANCH-B]**: Conditional task — execute only the branch Phase 0 selects

---

## Phase 0: Provenance + Diagnosis (FR-014-001) — HARD GATE (CC-1)

**Purpose**: (1) Make the running build identifiable so "Verified" can never again mean "verified on another binary"; (2) determine *why* the live server normalises `3.5.12 → 3.5.0` before any other fix is designed. The SYS-1 remediation (Phase 1) is selected here, not assumed.

**⚠️ GATE**: No task in Phases 1–7 may be marked complete, and no eval lane (Phase 8) result is trusted, until T001–T003 are green against `:8080` (CC-1) and T0-DIAG has recorded a finding.

- [ ] T001 [FR-014-001] Stamp build identity at startup in `migration_oracle/mcp/server.py` — at import time set `_SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()` (use `timezone.utc`, **not** the deprecated `datetime.utcnow()`); expose `get_server_started_at() -> str`. Read env vars `GIT_SHA`, `GIT_BRANCH`, `FEATURE_TAGS` (comma-separated) via `os.environ.get(..., "")` into module constants `_GIT_SHA`, `_GIT_BRANCH`, `_FEATURE_TAGS`. The deploy pipeline must populate these at build time.
- [ ] T002 [FR-014-001] Inject `server_build` into `get_graph_schema` response in `migration_oracle/mcp/tools/schema.py` — add (additive, removing no key): `"server_build": {"git_sha": server._GIT_SHA, "branch": server._GIT_BRANCH, "feature_tags": [t.strip() for t in server._FEATURE_TAGS.split(",") if t.strip()], "started_at": server.get_server_started_at()}`.
- [ ] T003 [FR-014-001] Unit test in `tests/mcp/test_schema.py` — mock `GIT_SHA="abc123"`, `GIT_BRANCH="013a-live-probe-fixes"`, `FEATURE_TAGS="013-real-run-hardening,013a-live-probe-fixes"`; call `get_graph_schema`; assert `server_build` has the correct `git_sha`, `branch`, `feature_tags` list, and a non-empty ISO `started_at`.
- [ ] **T0-DIAG** [FR-014-002] **Diagnose the SYS-1 cause and record the branch decision** in `specs/013a-live-probe-fixes/research.md` (append a "Diagnosis 2026-06-15" section). Concretely:
  1. Trace the version→sortable conversion used by `analyze_upgrade_path`, `build_recipe_plan`, `check_version_availability`, and `submit_migration_insight` in `migration_oracle/mcp/tools/upgrade.py` / `community.py`. Identify every call site of `_to_minor_zero`, `normalize_version`, and `resolve_version`.
  2. Determine whether any path collapses a *supplied* patch to `.0` **before** `resolve_version(mode=floor/ceil)` runs. Confirm against the live server: call `analyze_upgrade_path("Spring Boot","3.5.12","4.0.6")` — if it returns the `3.5.0 → 4.0.0` rule set (no context involved), normalisation is a **live code path**.
  3. Record the decision:
     - **BRANCH-A** — a live normalisation path collapses supplied patches (most likely, per probe evidence). Fix is to remove/short-circuit it across all version→sortable sites. The context "zombie" is then a *consequence*, cleaned up as a one-time data fix.
     - **BRANCH-B** — `resolve_version` is provably correct and deployed on every path, and the only failure is a pre-013 `MigrationContext` node colliding on `MERGE`. Fix is the zombie-context guard only.
  4. Confirm the supporting helpers actually exist before Phase 1 relies on them: `delete_zombie_context` in `graph/queries/context.py`, and whether `create_or_get_context` returns the resolved floor/ceil node IDs. Note any that must be *created* rather than *called*.

**Checkpoint**: L-PROVENANCE runnable (`get_graph_schema` on `:8080` returns the branch SHA + `feature_tags`); T0-DIAG has selected BRANCH-A or BRANCH-B with evidence.

---

## Phase 1: Version-Resolution Correctness (FR-014-002 / SYS-1)

**Purpose**: Guarantee that a supplied patch is preserved and the target is rounded to the ceil node, on **every** tool surface — not only `create_migration_context`. The acceptance is that *no tool* reports a `3.5.0 → 4.0.0` range for a `3.5.12 → 4.0.6` request (`spec.md` FR-014-002).

**⚠️ Execute the branch T0-DIAG selected.** Then run the shared verification (T-V).

### Branch A — remove the live normalisation path (default; select if T0-DIAG finds live collapse)

- [ ] T004A [BRANCH-A][FR-014-002] T0-DIAG will have identified the exact call sites that collapse patch versions. Apply the fix only where T0-DIAG found collapse — do not touch call sites that T0-DIAG confirmed are already correct. Concretely: in `migration_oracle/mcp/tools/upgrade.py` and `community.py` (and any other file T0-DIAG flags), route every version→sortable conversion that still calls `_to_minor_zero`/`normalize_version` on the main path through `resolve_version(framework, version, mode)` with `mode="floor"` for lower/current and `mode="ceil"` for upper/target. If T0-DIAG finds that `upgrade.py` is already correct (main path already calls `resolve_version`) and the collapse is only in `community.py` or in the deployed artifact, scope T004A accordingly — do not re-implement paths that are already right. `_to_minor_zero` is **retained only** inside `resolve_version`'s `VersionResolutionFailure` graceful-degrade branch — do not delete the function, only its main-path call sites.
- [ ] T005A [BRANCH-A][FR-014-002] In `create_migration_context` (`tools/context.py`): store the **requested** strings (`3.5.12`/`4.0.6`) in the `(projectId, fromVersion, toVersion)` MERGE identity; link `UPGRADES_FROM`→floor node and `UPGRADES_TO`→ceil node from `resolve_version`. Echo `from_version`/`to_version` (requested), the resolved `upgrades_to_version`, and `target_rounded_up` (true when ceil ≠ requested). One-time data cleanup: delete any pre-013 `MigrationContext` whose identity used a collapsed `.0` triple for an in-flight project (document the cleanup query in the runbook; do not run it blindly in prod).

### Branch B — zombie-context guard only (select only if T0-DIAG proves resolve_version is correct + deployed everywhere)

- [ ] T004B [BRANCH-B][FR-014-002] Add `check_context_version_match(context_id, from_node_id, to_node_id) -> bool` to `migration_oracle/mcp/graph/queries/context.py`. Cypher must tolerate missing edges (use `OPTIONAL MATCH`, not `MATCH`, so an edgeless zombie returns `false` rather than zero rows):
  ```cypher
  MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
  OPTIONAL MATCH (ctx)-[:UPGRADES_FROM]->(vf)
  OPTIONAL MATCH (ctx)-[:UPGRADES_TO]->(vt)
  RETURN coalesce(elementId(vf) = $from_node_id AND elementId(vt) = $to_node_id, false) AS match
  ```
- [ ] T005B [BRANCH-B][FR-014-002] Add the guard to `create_migration_context` (`tools/context.py`): on the resume path (`created is False`), call `check_context_version_match(...)` with the freshly-resolved floor/ceil node IDs; if `false`, `logging.warning` the stale context id, call `delete_zombie_context(project_id, from_version, to_version)` (confirmed present in T0-DIAG), re-call `create_or_get_context` once, and assert the retry returns `created=True` (else raise `RuntimeError("zombie context re-created unexpectedly")`).

### Shared verification (both branches)

- [ ] T-V [FR-014-002] Integration test in `tests/mcp/test_e2e_replay.py` (new file), against live Neo4j. Seed a pre-013 zombie `MigrationContext {projectId:"paysafe-wallet-switch", fromVersion:"3.5.0", toVersion:"4.0.0"}` (no `UPGRADES_*` edges). Then:
  1. `create_migration_context(project_id="paysafe-wallet-switch", framework="Spring Boot", from_version="3.5.12", to_version="4.0.6", scanned_entities=[])` → assert `created=True`, `from_version="3.5.12"`, `to_version="4.0.6"`, `target_rounded_up=True`; assert no `MigrationContext {fromVersion:"3.5.0", toVersion:"4.0.0"}` remains.
  2. **Full-surface check (catches BRANCH-A mis-scoping):** `analyze_upgrade_path("Spring Boot","3.5.12","4.0.6")` → assert the returned release range reaches the ceil node (`4.1.0` rules present), i.e. it does **not** collapse to `<= 4.0.0`. Repeat the no-collapse assertion for `build_recipe_plan`. For `submit_migration_insight`, assert that it resolves `4.0.6` to the correct floor node (a catalogued version `≤ 4.0.6`) — it must **not** attempt to look up `4.0.0`, which would fail if that node is absent from the graph.

**Checkpoint**: L-REPLAY runnable; the `3.5.12 → 4.0.6` request preserves patch and rounds to ceil on every tool, not just context creation.

---

## Phase 2: Resume-Path Counts (FR-014-007)

**Purpose**: Populate `entityCount`, `droppedCount`, and `reused` on the `ON MATCH` resume path (the path the probe exercised). Serializer-only; no Cypher/schema change.

- [ ] T006 [FR-014-007] In `create_migration_context` (`tools/context.py`), on **both** the CREATE and the MATCH paths: (a) recompute `allowed_entities = _filter_entities(entities)` and `dropped = len(entities) - len(allowed_entities)` for the *current* call (do not reuse a stale CREATE-time value); (b) add to the response, using the **camelCase keys the probe and `spec.md` contract use** — `"entityCount": len(allowed_entities)`, `"droppedCount": dropped`, `"reused": ctx.get("created") is False`; ensure both counts are always present and non-None. (If snake_case keys are also emitted elsewhere for back-compat, keep them as aliases — but `entityCount`/`droppedCount` must exist, since that is what LP-005 checks.)
- [ ] T007 [FR-014-007] Extend `tests/mcp/test_e2e_replay.py`: (a) fresh create → `reused=False`, `entityCount>=0`, `droppedCount>=0` (all non-None); (b) resume with same triple → `reused=True`, same fields non-None; (c) input containing a non-allow-listed entity → `droppedCount>0` on **both** create and resume paths.

**Checkpoint**: LP-005 closed.

---

## Phase 3: Search Content Field (FR-014-003)

**Purpose**: Fix the empty content projection in `search_migration_knowledge`.

- [ ] T008 [FR-014-003] In `migration_oracle/mcp/tools/search.py` + `migration_oracle/mcp/graph/queries/search.py`: confirm the hydrate `RETURN` projects `n.statement AS statement` (rules) and `n.description AS description` (recipes), and `coalesce(n.solution, first_step.instruction) AS solution`. Find where the result objects expose the content under a key that resolves to `""` (e.g. a `text` alias mapped to a property that does not exist) and align it to the contract key `statement`. Do **not** introduce a new alias — the contract (`mcp-tools-skills-prompts.md`) field is `statement`.
- [ ] T009 [FR-014-003] Unit test in `tests/mcp/test_search.py` — seed a `MigrationRule {statement:"Use jakarta.persistence instead of javax.persistence", solution:"..."}`; query for it; assert ≥1 hit has non-empty `statement` equal to the seeded value, and non-empty `solution`.

**Checkpoint**: LP-001 closed.

---

## Phase 4: Stable `rule_id` + Entity Projection (FR-014-004)

**Purpose**: Return a stable rule key and surface `matched_entities` — across the whole tool surface, not just `analyze_upgrade_path`, and without regressing community insights to `null` ids.

- [ ] T010 [FR-014-004a] Replace the rule-level `elementId(rule) AS rule_id` projection with **`coalesce(rule.ruleId, elementId(rule)) AS rule_id`** in `migration_oracle/mcp/graph/queries/upgrade.py` for **all three** rule-emitting queries: `_ANALYZE_UPGRADE_PATH`, `_BUILD_RECIPE_PLAN`, **and** `_GET_PENDING_STEPS` (which also returns `elementId(r) AS rule_id`). Rationale: `submit_migration_insight`'s `CREATE` never sets `ruleId`, so community insights have `ruleId = null`; bare `rule.ruleId` would emit `null`. The `coalesce` yields the stable `pipeline://…` key for pipeline rules and degrades to the element ID only where no stable key exists. Leave `elementId(s) AS step_id` untouched — step identity is unchanged.
- [ ] T011 [FR-014-004a] In `submit_migration_insight` (`tools/community.py` / its Cypher), set a stable `ruleId` at create time: `ruleId: 'community://' + $framework + '/' + $version + '/' + toString(randomUUID())`, written in the `CREATE (rule:MigrationRule …)` clause. This closes the gap that T010's `coalesce` works around — once T011 lands, community rules carry a non-element-ID key and the coalesce always returns it. **If this task is explicitly deferred, record that in T029 (FU-1) and do not leave it silently undone** — the `coalesce` in T010 is a safe interim but community rule IDs remain rebuild-unstable until T011 ships.
- [ ] T012 [FR-014-004b] Add `matched_entities` to `analyze_upgrade_path` in `migration_oracle/mcp/tools/upgrade.py`, mirroring `build_recipe_plan`. **Use exact-string matching** (`e in scanned_set`), consistent with the graph's exact-match semantics and the scanning skill — **do not lower-case**, which would diverge from how the typed buckets are populated. Include `"matched_entities"` on every emitted rule dict. Confirm the ISSUE-027 truncated-groupId package-prefix bridge (Dependency-coord rule ↔ scanned `Class` FQCN prefix) is present in `_ANALYZE_UPGRADE_PATH`; if absent, port it from `_GET_PENDING_STEPS` (013 T046). When a rule survives only via the safety net but its package root matches a scanned import, promote `uncertain → matched` and attach the matching FQCNs.
- [ ] T013 [FR-014-004] Test in `tests/mcp/test_analyze_upgrade_path.py` — seed `MigrationRule {ruleId:"pipeline://Spring Boot/3.5.12/Jackson import rename"}` with `AFFECTS_DEPENDENCY → Dependency {name:"com.fasterxml.jackson.core:jackson-databind"}`; context with `scannedClasses=["com.fasterxml.jackson.databind.ObjectMapper"]`; call `analyze_upgrade_path("Spring Boot","3.5.12","4.0.6")`. Assert: (a) `rule_id == "pipeline://Spring Boot/3.5.12/Jackson import rename"` (not an element-ID); (b) `applicability == "matched"`; (c) `matched_entities` contains `"com.fasterxml.jackson.databind.ObjectMapper"`; (d) no rule has both an element-ID-shaped `rule_id` (`^4:.*:`) **and** `match_count > 0`. Add a parallel assertion that a seeded community insight returns a non-null `rule_id`.

**Checkpoint**: LP-002a + LP-002b closed across the tool surface.

---

## Phase 5: Recipe Coverage + Agent-Codemod Degrade (FR-014-005)

**Purpose**: Make the zero-recipe state visible and confirm recipe absence degrades to agent-codemod (never a stall). Ingestion is ops, not code.

- [ ] T014 [FR-014-005] In `build_recipe_plan` (`graph/queries/upgrade.py`), count recipes once (`MATCH (r:OpenRewriteRecipe) RETURN count(r) AS c`) and **merge** into the existing `diagnostics` dict (do **not** overwrite it — `build_recipe_plan` already returns `scanned_total`, `rules_included`, etc. when `user_entities` is non-empty): `diagnostics["recipes_loaded"] = c > 0`, `diagnostics["recipe_count"] = c`. This makes `auto_track=0 with recipes_loaded=False` distinguishable from `auto_track=0 with recipes present`.
- [ ] T015 [FR-014-005] Verify (and fix if needed) `select_executor()` in `migration_oracle/mcp/routing.py` routes `recipe_id is None AND effort in ("mechanical","moderate") AND is_concrete_instruction(instruction) AND has_entity_anchor` → `"agent-codemod"` (not `"human-review"`). (T0-DIAG should have confirmed the function exists; if line references drift, locate by name.)
- [ ] T016 [FR-014-005] Unit tests in `tests/mcp/test_recipe_coverage.py` — (a) mock recipe count `0`; `build_recipe_plan` → `diagnostics.recipes_loaded=False`, `recipe_count=0`, existing diagnostics keys still present, `auto_track==[]`; (b) step dict `effort="mechanical"`, concrete rename instruction, entity anchor, `recipe_id=None` → `select_executor(step) == "agent-codemod"`.
- [ ] T017 [FR-014-005] Add an OpenRewrite-ingestion runbook to `specs/013a-live-probe-fixes/runbook.md`: (1) run ingestion against target Neo4j; (2) rebuild the `openrewrite_recipe_description` full-text index; (3) verify `MATCH (r:OpenRewriteRecipe) RETURN count(r) > 0`; (4) verify `build_recipe_plan.diagnostics.recipes_loaded=True`; (5) verify `search_openrewrite_recipes` returns ≥1 hit. Also record the Phase-1 one-time zombie-cleanup query here. Ops deploy-gate for L-RECIPE; **not** a blocker for any code task (LP-003 correctness must hold at `recipe_count=0`).

**Checkpoint**: LP-003 closed (diagnostic + degrade); L-RECIPE runnable post-ingestion.

---

## Phase 6: Step-Count Parity (FR-014-006)

**Purpose**: Make `get_pending_steps` and `build_recipe_plan` agree for the same context by sharing the range source. Most of the prior 0-vs-43 gap is a SYS-1 symptom (resolved in Phase 1); this phase closes the param-vs-context-edge divergence and asserts parity correctly.

- [ ] T018 [FR-014-006] Add optional `context_id: str | None = None` to `build_recipe_plan` (`tools/upgrade.py`). When provided, derive `current_version`/`target_version` from the context's `UPGRADES_FROM`/`UPGRADES_TO` resolved nodes (same source `get_pending_steps` uses) instead of caller params; when absent, keep the `resolve_version(floor/ceil)` path. (Note in `spec.md` change table: additive optional parameter.)
- [ ] T019 [FR-014-006] Update `migration_oracle/mcp/skills/framework_migration_main.md`: (a) remove every `HAS_STEP` reference — **no such relationship exists**; the queue derives from `(:Version)-[:INCLUDES_RULE]->(:MigrationRule)-[:REQUIRES_STEP]->(:MigrationStep)` over the resolved floor/ceil range; (b) state that `build_recipe_plan` and `get_pending_steps` must agree for a context, guaranteed by passing `context_id` to `build_recipe_plan`.
- [ ] T020p [FR-014-006] Parity test in `tests/mcp/test_e2e_replay.py` — for a fresh `3.5.12 → 4.0.6` context, compare **sets of distinct `step_id`**, not list lengths (build_recipe_plan returns one row per step×recipe×scope, so raw `len()` over-counts on fan-out): `set(s.step_id for s in get_pending_steps) == set(r.step_id for r in build_recipe_plan auto+manual)` after excluding steps in a terminal `STEP_OUTCOME` state. On the probe context this is the same 43 distinct steps on both sides (not 0).

**Checkpoint**: LP-004 closed.

---

## Phase 7: Eval Lanes (Closure Gates)

**Purpose**: Exercise every fix on the live server build that carries Phase-0 provenance. CC-1 (T021) must be green before any other lane is trusted.

- [ ] T021 [L-PROVENANCE] Deploy the branch; `get_graph_schema` on `:8080` → `server_build.git_sha` matches the built artifact; `feature_tags` includes `013-real-run-hardening` and `013a-live-probe-fixes`. **If the SHA mismatches, stop** — T022–T026 are invalid until deployment is corrected (this is the gate that would have caught the original "verified but un-deployed" failure).
- [ ] T022 [L-REPLAY] Live `create_migration_context(3.5.12 → 4.0.6)` for `paysafe-wallet-switch` → `created=true`, `from_version="3.5.12"`, `to_version="4.0.6"`, `target_rounded_up=true` (`upgrades_to_version="4.1.0"`); no `3.5.0 → 4.0.0` node remains; `reused=False`; `entityCount`/`droppedCount` are integers. **Full-surface SC-002 check (all 7 tools):** (a) `analyze_upgrade_path` and `build_recipe_plan` do not collapse to `4.0.0`; (b) `submit_migration_insight` resolves `4.0.6` to a floor node `≤ 4.0.6`, not `4.0.0`; (c) `check_version_availability("Spring Boot","3.5.12")` returns `exists_in_graph=true` with a `nodeId` — call `submit_migration_insight` for the same pair and assert it resolves to the **same** `nodeId` (SC-004 / ISSUE-016 regression gate); (d) `get_steps_for_scope_tier(context_id, scope="…")` returns a non-empty step list, proving its range is derived from the correct context edges and not a collapsed `.0` range.
- [ ] T023 [L-PROBE-RERUN] Re-run the five original probes live: (a) LP-001 — every `search_migration_knowledge` hit has non-empty `statement`; (b) LP-002a — every `analyze_upgrade_path` `rule_id` is a `pipeline://…`/`community://…` key, not `^4:.*:`; (c) LP-002b — Jackson rule `applicability="matched"`, `matched_entities` non-empty; (d) LP-005 — resume call returns integer `entityCount`/`droppedCount`; (e) none of the original five findings reproduces.
- [ ] T024 [L-PARITY] Live `get_pending_steps(context_id)` vs `build_recipe_plan(context_id=…)` → distinct `step_id` **sets** equal (43 on both).
- [ ] T025 [L-MATCH] Live: Jackson rule `matched` with `com.fasterxml.jackson.*` FQCN anchor; `select_executor` on its step → `"agent-codemod"`.
- [ ] T026 [L-RECIPE] Pre-ingestion: `build_recipe_plan.diagnostics.recipes_loaded=False`, `manual_track` non-empty, ≥1 step routes to `agent-codemod`. Post-ingestion (T017): `recipes_loaded=True`, `recipe_count>0`, `search_openrewrite_recipes` ≥1 hit.

**Checkpoint**: all lanes green; CC-1…CC-5 verifiable.

---

## Phase 8: Closure Documentation (CC-3, CC-4, CC-5)

- [ ] T027 [CC-3] `CHANGELOG.md` — behavioural change for `analyze_upgrade_path`/`build_recipe_plan`/`get_pending_steps`: "`rule_id` is now the stable `MigrationRule.ruleId` (`pipeline://…`/`community://…`), falling back to the element ID only when no stable key exists; callers that persisted the old element-ID `rule_id` must re-key."
- [ ] T028 [CC-4] Confirm `framework_migration_main.md` has no `HAS_STEP` references and documents range-from-resolved-bounds (T019); mark CC-4 done.
- [ ] T029 [CC-5] Log FU-1 accurately — **not** "ruleId derived from elementId" (it is currently *not written at all* for community insights). If T011 lands, FU-1 is closed; if deferred, FU-1 reads: "`submit_migration_insight` does not set `ruleId`; community rules rely on the `coalesce → elementId` fallback, which is rebuild-unstable. Set a `community://…` key at create time." Assign an owner.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 0** is a hard gate. T0-DIAG selects BRANCH-A/B for Phase 1 and confirms helper existence. T001–T003 gate every live lane (CC-1).
- **Phase 1** executes the selected branch, then T-V. T-V's full-surface assertions guard against BRANCH-A being mis-scoped to context creation only.
- **Phase 2 (Resume counts)** is serializer-only; independent of Phase 1 *code* but its **resume test** (T007) and the L-REPLAY lane assume Phase 1 produced a correctly-resolved context, so run after Phase 1.
- **Phase 3 (Search)** — fully independent.
- **Phase 4 (rule_id + entities)** — T010 before T012; T012's entity matching is only *meaningful* once Phase 1 is correct (right range/buckets), so validate T013 after Phase 1.
- **Phase 5 (Recipe)** — independent; diagnostic + read-only verify + ops runbook.
- **Phase 6 (Parity)** — T018/T020p depend on Phase 1 (correct context bounds in the graph).
- **Phase 7 (Lanes)** — after Phases 1–6 merged + deployed; T021 first (CC-1).
- **Phase 8 (Docs)** — anytime after the code they describe lands.

### Parallel groups

- **Group A (after Phase 0 gate clears)**: Phase 3 (T008/T009), Phase 5 (T014–T017) — disjoint files.
- **Group B (after T0-DIAG selects a branch)**: Phase 1 branch tasks + T-V.
- **Group C (after Phase 1 merges)**: Phase 2 (T006/T007), Phase 4 (T010→T011→T012, then T013), Phase 6 (T018/T019/T020p).
- **Group D (after Phases 1–6 deployed)**: T021 → T022–T026, sequential, provenance-gated.
- **Group E (docs, anytime)**: T019, T027, T028, T029.

### File-concurrency notes

- `tools/context.py` is touched by Phase 1 (T005A/T005B) and Phase 2 (T006, different section: response serializer). Apply Phase 1 first; T006 is a clean follow-on.
- `graph/queries/upgrade.py` is touched by T010 (rule_id), T012 (matching/bridge), T014 (recipe diagnostic), and T018 (param). Distinct functions/queries; sequence T010 → T012 within `_ANALYZE_UPGRADE_PATH`; T014/T018 are independent of those.
- BRANCH-A's T004A touches `tools/upgrade.py`/`community.py` version conversion — coordinate with T010/T012/T018 in the same files (apply T004A first so later tasks build on the corrected resolution path).

---

## Notes

- **Diagnosis-before-design.** The prior draft assumed SYS-1 was a stale DB node and built a zombie guard. The probe shows normalisation in `analyze_upgrade_path` (no context), so the cause is most likely a live code path — hence Phase 0 / T0-DIAG decides, and BRANCH-A (remove the live normalisation) is the default. T-V's full-surface assertion fails loudly if a context-only fix leaves `analyze`/range/`submit` still collapsing.
- **`_to_minor_zero` is retained** only as the `VersionResolutionFailure` degrade inside `resolve_version` (genuinely-absent version). Its *main-path* call sites are what BRANCH-A removes.
- **`rule_id` uses `coalesce(rule.ruleId, elementId(rule))`** — bare `rule.ruleId` would emit `null` for community insights, since `submit_migration_insight` never writes `ruleId`. T011 fixes that at the source; FU-1 (T029) tracks it if deferred.
- **Entity matching stays exact-string** (T012) — no `.lower()`; lower-casing diverges from the typed-bucket population and risks false matches.
- **Counts use camelCase** (`entityCount`/`droppedCount`, T006) to match what LP-005 actually checks and the `spec.md` contract table.
- **Parity asserts on distinct `step_id` sets** (T020p), not list lengths — `build_recipe_plan` fans out per step×recipe×scope.
- **Recipe diagnostics merge**, not overwrite (T014) — `build_recipe_plan` already returns a `diagnostics` object.
- **FR prefix**: tasks use `FR-014-xxx` to match `spec.md`; the feature/branch/dir is `013a-live-probe-fixes`. Say the word and I'll realign `spec.md`/`research.md` FR IDs to `FR-013a-xxx` for full consistency.
- **CC-1 is T021.** If provenance fails, every other lane is unreliable — do not proceed.
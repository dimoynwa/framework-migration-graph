# Framework Migration — Four-Loop Harness (Increment 3)

This skill replaces the pre-redesign five-phase harness with four re-entrant runtime loops backed by `MigrationContext` graph state.

## Loop I — Context

**Purpose:** Load or create a `MigrationContext`. Run the codebase scan. Surface version boundary pre-conditions.

**Steps:**

**Step 0 — Preflight (T043)**

Before starting the codebase scan:

a. Run `python3 --version` to confirm Python 3 is available. If absent, log a warning and offer the grep fast path as the only extraction option.
b. Run `python3 -c 'import yaml'` to check PyYAML availability. Log `"PyYAML: present"` or `"PyYAML: absent"`.
c. Report the chosen extractor: `"Extractor: python"` (canonical) or `"grep-gnu"` / `"grep-bsd"` (fast path, if Python absent).
d. Log: `"Preflight complete. Extractor: {path}, PyYAML: {present|absent}"`

**Step 1 — Context discovery and supersede (T020)**

a. Call `get_migration_contexts(project_id=<id>)` to list all prior contexts.
b. If `count=0`: proceed directly to scan + create (no prior session).
c. If `count>0`: surface the list to the engineer.
   - For each context with `status="in-progress"` or `status="blocked"`: show `id`, `fromVersion`, `toVersion`, `createdAt`, `updatedAt`, `outcome_counts`.
   - If a stale context has the **wrong triple** (different `fromVersion`/`toVersion` than intended): call `close_migration_context(context_id, final_status="abandoned")` to supersede it.
   - If the **intended triple** already exists with `status="in-progress"`: resume it — call `create_migration_context` with the same triple (MERGE match path refreshes the entity set and returns `created=false`).
   - If the intended triple exists with `status="complete"`: surface the completion summary. Offer to start a new context for a different target version. Stop.
d. After abandoning any stale contexts, call `create_migration_context` with the intended triple.

**Step 2 — Status check**

If the loaded context is `status=complete`: surface the completion summary. Offer to start a new context for a different target version. Do not proceed to loops II–IV.

**Step 3 — Codebase scan**

Run the codebase scan regardless of whether this is a new session or a resume. Entities may have changed since the last session. Use the patterns from `skill://framework-migration/scanning`: FQCNs from import lines, annotations without `@`, dotted property keys, `groupId:artifactId` without versions, exact npm package names. Report `extractorPath` from the scan result.

**Step 4 — Entity diff**

If resuming: diff the new scan against `ctx.scannedEntities`. Any entity present in the new scan but not in `ctx.scannedEntities` is added to the query queue for loop II.

**Step 5 — Version map**

Load `skill://framework-migration/version-map`. Surface any toolchain pre-conditions (Java version requirement at the minor-line level, Node version requirement, Spring Cloud co-migration if applicable) before proceeding.

**Step 6 — Create context**

Call `create_migration_context` with the scanned entity list. If response includes `co_migration_warning`, surface it to the engineer immediately. If `droppedCount > 0`, report how many entities were filtered by the server-side allow-list.

### Loop I — STATELESS FALLBACK

**Trigger**: `create_migration_context` returns an error on both the initial attempt and one retry.

**Instructions**:
1. Log the failure to the user: "Context creation failed; continuing in stateless mode."
2. Continue with `analyze_upgrade_path` and `build_recipe_plan` using the scanned entities from the codebase scan.
3. Skip all tools that require a `context_id` (get_pending_steps, update_step_status, get_steps_for_scope_tier, close_migration_context).
4. Track step state in agent context only (in-memory, not persisted).
5. For every high-confidence finding (build passes), call `submit_migration_insight` without a `context_id`.
6. At session end, emit a summary noting that the session ran in stateless mode and no graph state was persisted.

**Gate:** Never call any graph query tool before this loop completes.

## Loop II — Scope-gated query

**Purpose:** Query the graph for migration rules affecting the scanned entities, in priority order by blast radius. Skip entities already resolved in prior sessions.

**Tier structure:**

| Tier | Scope filter | Severity filter | Tools called |
|---|---|---|---|
| 1 | `api-surface` | `high`, `critical` | `get_steps_for_scope_tier` → `analyze_upgrade_path` → `resolve_deprecation` per `removed` entity → `entity_evolution` if partial chain |
| 2 | `runtime` | `medium`, `high`, `critical` | Same sequence, skipping entities already cached from tier 1 |
| 3 | `config`, `build` | all | `analyze_upgrade_path` with scope filter. `search_migration_knowledge` for entities with no graph hit |
| 4 | `test` | all | `analyze_upgrade_path`. Results are deferred and handled last in loop III. |
| — | Paysafe deps | — | `resolve_paysafe_dependency_by_service_name` for every `com.paysafe` dependency. Run concurrently with tier 1 — these are independent. |

**Parameter:** `query_handoff_threshold: int = 0` (default 0 = all tiers queried before execution begins). When set to a positive value N, the harness transitions from query to execution for completed tiers once `current_tier >= N`, before querying the next tier. Test-scope (tier 4) always executes last regardless of threshold.

**Loop II fallback rows (T039) — Paysafe resolver typed errors:**

| Condition | Action |
|---|---|
| `resolve_paysafe_dependency_by_service_name` returns `subStatus="auth_error"` | Log `auth_error` with `remediationSteps` (name `FINDIT_AUTH_TOKEN` and `GITLAB_API_KEY`). Emit each entry in `unresolvedDependencies` as a Loop IV backlog item. Surface `fallbackInstructions` to engineer. Continue to next entity — do **not** halt Loop II. |
| `resolve_paysafe_dependency_by_service_name` returns `subStatus="transport_error"` | Log `transport_error` with `remediationSteps` (VPN check, `FINDIT_BASE_URL` reachability). Emit `unresolvedDependencies` as backlog items. Surface `fallbackInstructions`. Continue. |

**Skip guard:** Before any tool call in Loop II, check `ctx.queriedEntities[entity_name]`.
- If the key is present, the entity was queried in a prior session and its result is cached — skip the tool call and read the cached result from `ctx.queriedEntities[entity_name]`.
- If the user has instructed you to re-query a specific entity (e.g. "re-query org.example.Foo"), set a local `force_refresh` flag for that entity and bypass the skip guard for it. `force_refresh` is a per-entity flag in the agent loop — it is **not** a parameter on any MCP tool.
- After each successful entity query, call `update_queried_entity(context_id, entity_name, result_summary)` to persist the result. Do not call this concurrently for the same context — calls must be sequential.

## Loop III — Execution

**Purpose:** Apply migration steps in order, verify each one, and mark it done.

**Work queue:** Call `get_pending_steps` with no filters to get the full remaining queue.

**Executor-selection decision table (T026) — authoritative implementation: `migration_oracle/mcp/routing.py`**

The `automatable` flag is **metadata only** — it is never a routing input. Evaluate rows top-to-bottom; first matching row wins.

| # | Recipe state | Effort | Concrete instruction + entity anchor | Track |
|---|---|---|---|---|
| 1 | Fully resolved (`auto=true AND missingRequiredParams=[]`) | any | any | **OpenRewrite** |
| 2 | Partially resolved (edge exists but `auto=false` OR `missingRequiredParams≠[]`) | any | any | **Prompted-auto** |
| 3 | None | `mechanical` | Yes | **Agent-codemod** |
| 4 | None | `moderate` | Yes | **Agent-codemod** |
| 5 | None | `mechanical` | No | **Human-review** |
| 6 | None | `moderate` | No | **Human-review** |
| 7 | None | `architectural` | any | **Human-review** |

**Concrete instruction**: the `instruction` field must include at least one of: (a) a before/after transformation example, (b) a named operation (`rename`, `replace`, `remove`, `add`) with explicit source and target, or (c) a pattern + replacement target. Free-text descriptions without a transformation pattern do NOT qualify.

**Entity anchor**: at least one entity in the rule's affected-entity set matches the context's scanned entities (`applicability="matched"`).

**Track behaviours:**
- **OpenRewrite**: batch eligible steps into `rewrite.yml`. Apply via OpenRewrite CLI. Run build+test. On pass: `update_step_status(outcome="completed")`. On fail: rollback → `update_step_status(outcome="failed")` → continue.
- **Prompted-auto**: surface missing parameters to engineer. If provided: patch recipe params and re-evaluate at row 1. If declined: re-route to human-review.
- **Agent-codemod**: full protocol below.
- **Human-review**: emit step card (summary, instruction, verificationHint, jiraKeys, severity). Wait for engineer confirmation. On confirm: `update_step_status(outcome="completed")`. On skip: `update_step_status(outcome="skipped", reason=user_reason)`. On architectural: pause loop, emit design decision prompt, wait, record as context note, then route to human-review step execution.

**Agent-codemod executor protocol (T027):**

```
1. BLAST-RADIUS GATE
   a. Identify all files matching the entity anchor and instruction scope.
   b. Present the complete file list to the engineer.
   c. Check project-level blast_radius_confirm_threshold (default: 0 = always confirm).
      - If file count EXCEEDS threshold (or threshold=0): require explicit confirmation.
      - If file count AT OR BELOW non-zero threshold: auto-confirm. Log: "Auto-confirming: {N} files ≤ threshold {T}."
   d. threshold=0 requires confirmation for ANY file count. Only explicit project-level setting skips confirmation.

2. IDEMPOTENCY CHECK
   a. Before applying changes, check whether the target state already matches the post-transformation expectation.
   b. If already applied → call update_step_status(outcome="completed") immediately. No files written.

3. APPLY TRANSFORMATION
   a. Apply the full transformation to all matched files.
   b. Track all modified files for rollback.

4. BUILD-AND-TEST GATE
   a. Run the project's build command (Maven/Gradle).
   b. Run the test suite.
   c. On PASS → call update_step_status(outcome="completed"). Done.

5. ON GATE FAILURE → ROLLBACK
   a. Load skill://framework-migration/rollback and follow the revert procedure.
   b. The rollback skill restores all files modified in step 3 to their exact pre-change state.
   c. Call update_step_status(outcome="failed", reason="build failed: <error>").
   d. Record failure reason on STEP_OUTCOME relationship.
   e. Continue processing remaining steps in the current tier. Do NOT halt the session.
   f. Add the failed step to the Loop IV backlog with its failure reason.
```

**Bridge/deferred section (T034) — when an engineer applies a compatibility bridge instead of the real change:**

Before recording any deferred outcome:
a. Verify bridge discoverability from graph — the rule's `BRIDGED_BY` edge must exist. Call `update_step_status(outcome="deferred")` which validates this server-side.
b. `requiredChange` must be the **elementId of the real-change MigrationStep** (not free text). Resolve this step reference before recording so that the auto-resolve check can function.
c. Call `update_step_status(outcome="deferred", reason=json({"bridgeName": "...", "bridgeReason": "...", "requiredChange": "<step_elementId>"}))`.
d. On `error_code="bridge_not_in_graph"` rejection: do **not** accept the bridge. Route the step to human-review instead.
e. When the `requiredChange` step is later completed, `update_step_status` auto-resolves the deferred step (sets `STEP_OUTCOME.status="completed"`, `resolvedVia="bridge"`, `bridgeResolvedAt`).

**Prerequisites:** Do not execute a step that has a `REQUIRES` edge to a step not yet in `completedSteps`. Re-queue behind the prerequisite and surface the dependency to the user if the prerequisite is itself blocked.

**FR-D06 eval coverage notes (T028) — three round-1 fix paths require explicit eval before ISSUE-005/013/003 are treated as validated:**
1. **Rollback path** (`eval_rollback_scenario.yaml`): trigger by deliberately failing an automated step. Validate: rollback fires, step marked `failed`, session continues.
2. **Stateless fallback** (`eval_stateless_fallback_scenario.yaml`): trigger by injecting a `create_migration_context` error. Validate: Loop IV completes in stateless mode, no exception propagates.
3. **Severity threshold** (`test_get_steps_for_scope_tier.py::test_high_threshold_*`): verify `get_steps_for_scope_tier` filters at both `"high"` and `"low"` thresholds with a mixed-severity fixture.

**Interrupt safety:** `update_step_status` is called after every step, win or lose, before the agent moves to the next step.

## Loop IV — Feedback

**Purpose:** Return discovered knowledge to the graph and emit the remaining backlog.

**Steps:**

1. For each manual step where the developer's actual fix differed from `step.instruction`, capture the actual solution.
2. For each discovered deviation, call `submit_migration_insight` with confidence 0.9 (build+tests pass) / 0.7 (build only) / 0.5 (uncertain).
3. **Skipped steps backlog:** For every step in `ctx.skippedSteps[]` where `effort` is not `test`, emit a backlog item with step summary, instruction, verificationHint, jiraKeys, BreakingScope severity.
4. **Deferred steps backlog (T035):** For every step in `ctx.deferredSteps[]`, emit an active backlog item. Deferred steps are **NOT finished** — they must remain visible on every re-entry until `requiredChange` is completed and auto-resolve fires.
   - Each deferred backlog item must show: `bridgeName`, `bridgeReason`, `requiredChange` (the elementId of the real-change step), and the step summary from the original `MigrationStep` node.
   - Label each item clearly: `[DEFERRED — bridge active: {bridgeName}]` so it is not confused with a skip.
   - On session re-entry: call `get_migration_contexts` and inspect the returned `deferredSteps` count before proceeding to Loop II — if `deferredSteps > 0`, surface the deferred backlog to the engineer at the start of the session.
5. Call `close_migration_context` with `final_status=complete/partial/abandoned`.
   - Use `partial` when any skipped or deferred steps remain. Do NOT close as `complete` while `ctx.deferredSteps` is non-empty.

## Decision logic — complete reference

### Context loop decisions

| Condition | Action |
|---|---|
| No context exists for `projectId` | Create context. Run full scan. |
| Context exists, `status=in-progress` | Load context. Run scan. Diff entities. Queue new entities for loop II. |
| Context exists, `status=blocked` | Load context. Report what is blocked. Ask user to resolve. Run scan. Continue. |
| Context exists, `status=complete` | Surface summary. Offer new context for different version. Stop. |

### Query loop decisions

| Condition | Action |
|---|---|
| Entity in `ctx.queriedEntities` | Skip tool call. Read cached result from context. |
| `resolve_deprecation` returns full chain | Cache. Skip `search_migration_knowledge`. |
| `resolve_deprecation` returns partial chain | Call `entity_evolution`. Then call `search_migration_knowledge`. |
| `resolve_deprecation` returns no records | Call `search_migration_knowledge`. If still no result, mark as unverified. |
| All steps for rule are `automatable=true AND effort='mechanical'` | Skip `search_migration_knowledge`. Queue for auto track in loop III. |
| Entity name starts with `com.paysafe` | Call `resolve_paysafe_dependency_by_service_name` concurrently. Do not wait for it before proceeding with framework rule queries. |

### Execution loop decisions

| Condition | Track | Action |
|---|---|---|
| `automatable=true AND effort='mechanical' AND ab.auto=true AND missingRequiredParams=[]` | Auto | Batch in `rewrite.yml`. Apply. Verify. Mark complete. |
| `automatable=true` but `missingRequiredParams` non-empty | Prompted | Surface missing params. If user fills them: retry auto. Else: manual. |
| `effort='moderate'` | Manual | Emit step card. Wait for user. |
| `effort='architectural'` | Design gate | Pause. Emit design decision. Wait. Then manual. |
| Prerequisites not complete | Blocked | Re-queue. Surface dependency. |
| Auto apply fails build | Rollback | Load `skill://framework-migration/rollback`. Follow the revert procedure. Call `update_step_status(outcome="failed", reason="build failed: [error]")`. |

### Feedback loop decisions

| Condition | Action |
|---|---|
| Developer's fix differed from `step.instruction` | `submit_migration_insight` with actual solution |
| Verify-fail step resolved by different approach | `submit_migration_insight` with workaround, confidence based on build result |
| Steps in `ctx.skippedSteps` with `effort ≠ 'test'` | Emit backlog item with traceability to original Jira keys |
| Steps in `ctx.deferredSteps` (any) | Emit active backlog item showing `bridgeName`, `bridgeReason`, `requiredChange`; label `[DEFERRED — bridge active]`; persist across re-entries until auto-resolved |
| All non-skipped, non-deferred steps done | `close_migration_context(final_status="complete")` |
| Skipped or deferred steps remain | `close_migration_context(final_status="partial")` |

---

### Loop IV — STATELESS FALLBACK

**Trigger:** No `context_id` is available (context creation failed or was not attempted).

**Behaviour in stateless mode:**

- `ctx.skippedSteps[]` backlog is unavailable — skip reading it.
- Print a migration step summary from agent memory (rules and steps identified during Loop II).
- Call `submit_migration_insight` for any novel findings, without a `context_id`.
- Emit a stateless-mode session summary to the user:
  - List the migration rules identified.
  - Note which steps could be automated and which require manual effort.
  - Advise the user to create a `MigrationContext` for a stateful run with full resume support.

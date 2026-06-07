# Framework Migration — Four-Loop Harness (Increment 3)

This skill replaces the pre-redesign five-phase harness with four re-entrant runtime loops backed by `MigrationContext` graph state.

## Loop I — Context

**Purpose:** Load or create a `MigrationContext`. Run the codebase scan. Surface version boundary pre-conditions.

**Steps:**

1. Check for existing `MigrationContext` by `projectId`. If found and `status=in-progress` or `status=blocked`: load `completedSteps[]`, `skippedSteps[]`, and `queriedEntities{}`. Log to the user that the session is being resumed.
2. If `status=complete`: surface the completion summary. Offer to start a new context for a different target version. Do not proceed to loops II–IV.
3. Run the codebase scan regardless of whether this is a new session or a resume. Entities may have changed since the last session. Use the patterns from `skill://framework-migration/scanning`: FQCNs from import lines, annotations without `@`, dotted property keys, `groupId:artifactId` without versions, exact npm package names.
4. If resuming: diff the new scan against `ctx.scannedEntities`. Any entity present in the new scan but not in `ctx.scannedEntities` is added to the query queue for loop II.
5. Load `skill://framework-migration/version-map`. Surface any toolchain pre-conditions (Java version requirement, Node version requirement, etc.) before proceeding.
6. Call `create_migration_context` with the scanned entity list.

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

**Skip guard:** Before any tool call, check `ctx.queriedEntities[entity_name]`. If the entity was queried in a prior session, its result is cached on context — do not re-issue the tool call unless `--force-refresh` is set.

## Loop III — Execution

**Purpose:** Apply migration steps in order, verify each one, and mark it done.

**Work queue:** Call `get_pending_steps` with no filters to get the full remaining queue.

**Step routing:**

| Condition | Track | Action |
|---|---|---|
| `step.automatable=true AND step.effort='mechanical' AND AUTOMATED_BY edge exists AND missingRequiredParams=[]` | Auto | Include in `rewrite.yml` batch. Apply via OpenRewrite. Run build+test. On pass: call `update_step_status(outcome="completed")`. |
| `AUTOMATED_BY` exists but `missingRequiredParams` is non-empty | Prompted auto | Surface missing parameters to user. If user provides them, patch recipe params and retry auto track. Else route to manual. |
| `step.effort='moderate'` or no `AUTOMATED_BY` edge | Manual | Emit step card (summary, instruction, verificationHint) to user. Wait for confirmation. On confirm: `update_step_status(outcome="completed")`. On skip: `update_step_status(outcome="skipped", reason=user_reason)`. |
| `step.effort='architectural'` | Design gate | Pause loop. Emit a design decision prompt. Do not proceed until the user provides an explicit design choice. Record the choice on context as a note. Then route to manual. |
| Step has `REQUIRES` edge to a step not in `ctx.completedSteps` | Blocked | Do not execute. Re-queue behind the prerequisite. Surface the dependency to the user if the prerequisite is itself blocked. |
| Build fails after auto apply | Rollback | Load rollback skill. Revert the applied changes. Call `update_step_status(outcome="failed", reason="build failed: [error]")`. Search `search_migration_knowledge` for workarounds. Escalate this step to manual track. |

**Interrupt safety:** `update_step_status` is called after every step, win or lose, before the agent moves to the next step.

## Loop IV — Feedback

**Purpose:** Return discovered knowledge to the graph and emit the remaining backlog.

**Steps:**

1. For each manual step where the developer's actual fix differed from `step.instruction`, capture the actual solution.
2. For each discovered deviation, call `submit_migration_insight` with confidence 0.9 (build+tests pass) / 0.7 (build only) / 0.5 (uncertain).
3. For every step in `ctx.skippedSteps[]` where `effort` is not `test`, emit a backlog item with step summary, instruction, verificationHint, jiraKeys, BreakingScope severity.
4. Call `close_migration_context` with `final_status=complete/partial/abandoned`.

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
| Auto apply fails build | Rollback | Roll back. Mark failed. Search community insights. Escalate to manual. |

### Feedback loop decisions

| Condition | Action |
|---|---|
| Developer's fix differed from `step.instruction` | `submit_migration_insight` with actual solution |
| Verify-fail step resolved by different approach | `submit_migration_insight` with workaround, confidence based on build result |
| Steps in `ctx.skippedSteps` with `effort ≠ 'test'` | Emit backlog item with traceability to original Jira keys |
| All non-skipped steps done | `close_migration_context(final_status="complete")` |
| Skipped steps remain | `close_migration_context(final_status="partial")` |

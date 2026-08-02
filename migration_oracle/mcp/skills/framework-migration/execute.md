---
name: framework-migration-execute
description: >
  Execute stage — apply pending migration steps, verify builds, and update step
  status. Includes rollback reference for build-failure recovery.
compatibility:
  tools:
    - build_recipe_plan
    - resolve_deprecation
    - entity_evolution
    - search_migration_knowledge
    - search_openrewrite_recipes
    - get_graph_schema
    - execute_custom_cypher
    - get_community_insights
    - get_pending_steps
    - update_step_status
---

# Execute Stage — Apply Pending Steps

**Stage gating** — this skill is read by two audiences:

- **Launching the server:** set `MCP_ACTIVE_STAGE=execute` in the environment (or pass it to your start/redeploy script) before the MCP server process starts. Tool registration is fixed at startup; it cannot be changed mid-session.

- **Already connected:** if you are an agent with a server already running, do not restart it — infer the active stage from which tools in `compatibility.tools` are available. If a required tool is missing, stop and report a stage mismatch; do not substitute tools from another stage.

## Context discovery

When `context_id` is unknown:

1. Call `get_migration_contexts(project_id)` and filter `status="in-progress"`.
2. If exactly one match → use its `id` as `context_id`.
3. If multiple matches → stop and ask the operator to choose.
4. Always call `get_pending_steps(context_id)` fresh on every execute invocation.

## Work queue

Call `get_pending_steps` with no filters. `build_recipe_plan` and `get_pending_steps` return the same set when called for the same context.

## Executor-selection decision table

Evaluate rows top-to-bottom; first matching row wins. The `automatable` flag is metadata only.

| # | Recipe state | Effort | Concrete instruction + entity anchor | Track |
|---|---|---|---|---|
| 1 | Fully resolved (`auto=true AND missingRequiredParams=[]`) | any | any | **OpenRewrite** |
| 2 | Partially resolved | any | any | **Prompted-auto** |
| 3 | None | `mechanical` | Yes | **Agent-codemod** |
| 4 | None | `moderate` | Yes | **Agent-codemod** |
| 5 | None | `mechanical` | No | **Human-review** |
| 6 | None | `moderate` | No | **Human-review** |
| 7 | None | `architectural` | any | **Human-review** |

**Track behaviours:**
- **OpenRewrite**: batch eligible steps into `rewrite.yml`, apply via CLI, `update_step_status(outcome="applied")`.
- **Prompted-auto**: surface missing params; retry or route to human-review.
- **Agent-codemod**: blast-radius gate → idempotency check → apply → mark applied.
- **Human-review**: emit step card, wait for engineer confirmation.

## Agent-codemod protocol

```
1. BLAST-RADIUS GATE — present file list, require confirmation per threshold
2. IDEMPOTENCY CHECK — if already applied, mark completed immediately
3. APPLY TRANSFORMATION — track modified files
4. MARK APPLIED — update_step_status(outcome="applied"), continue queue
```

## Terminal build-and-fix gate

Run after all steps are applied:

1. Run build + tests. On PASS → `update_step_status(outcome="completed")` for all applied steps.
2. On failure — diagnose, fix forward (do not revert). Re-run until pass.
3. **Paysafe constraint**: never remove/downgrade `com.paysafe.*` deps; fix consuming code instead.
4. If stuck after 3 attempts, `search_migration_knowledge` then mark step blocked.

## Bridge/deferred handling

Before `outcome="deferred"`: verify `BRIDGED_BY` edge exists. `requiredChange` must be the real-change step elementId.

## Prerequisites

Do not execute a step whose `REQUIRES` prerequisite is not yet completed.

## Rollback

On catastrophic build failure requiring revert, follow `references/rollback.md`.

After execute completes, proceed to `framework-migration-feedback`.

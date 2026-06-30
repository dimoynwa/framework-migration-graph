---
name: framework-migration-feedback
description: >
  Feedback stage — submit community insights, emit backlog for skipped/deferred
  steps, and close the MigrationContext.
compatibility:
  tools:
    - submit_migration_insight
    - get_community_insights
    - vote_insight
    - verify_insight
    - get_graph_schema
    - execute_custom_cypher
    - close_migration_context
    - get_migration_contexts
---

# Feedback Stage — Insights and Close

**Stage gating** — this skill is read by two audiences:

- **Launching the server:** set `MCP_ACTIVE_STAGE=feedback` in the environment (or pass it to your start/redeploy script) before the MCP server process starts. Tool registration is fixed at startup; it cannot be changed mid-session.

- **Already connected:** if you are an agent with a server already running, do not restart it — infer the active stage from which tools in `compatibility.tools` are available. If a required tool is missing, stop and report a stage mismatch; do not substitute tools from another stage.

## Steps

1. For each manual step where the developer's fix differed from `step.instruction`, capture the actual solution.
2. For each discovered deviation, call `submit_migration_insight` with confidence 0.9 (build+tests pass) / 0.7 (build only) / 0.5 (uncertain).
3. **Skipped steps backlog:** For every step in `ctx.skippedSteps[]` where `effort` is not `test`, emit a backlog item.
4. **Deferred steps backlog:** For every step in `ctx.deferredSteps[]`, emit an active backlog item labeled `[DEFERRED — bridge active: {bridgeName}]`.
   `deferredSteps` is a real `MigrationContext` list property — initialized to `[]` on create
   (`_CREATE_OR_GET_CONTEXT` in `context.py`) and appended when `update_step_status(outcome="deferred")`.
5. Call `close_migration_context` with `final_status=complete/partial/abandoned`.
   - Use `partial` when any skipped or deferred steps remain.
   - Do NOT close as `complete` while `ctx.deferredSteps` is non-empty.

## Decision table

| Condition | Action |
|---|---|
| Developer's fix differed from instruction | `submit_migration_insight` with actual solution |
| Steps in `ctx.skippedSteps` with `effort ≠ 'test'` | Emit backlog item |
| Steps in `ctx.deferredSteps` | Emit active backlog item with bridge details |
| All non-skipped, non-deferred steps done | `close_migration_context(final_status="complete")` |
| Skipped or deferred steps remain | `close_migration_context(final_status="partial")` |

## Stateless fallback

**Trigger:** No `context_id` available.

- Skip `ctx.skippedSteps[]` backlog.
- Print migration step summary from agent memory.
- Call `submit_migration_insight` for novel findings without `context_id`.
- Advise creating a `MigrationContext` for a stateful run.

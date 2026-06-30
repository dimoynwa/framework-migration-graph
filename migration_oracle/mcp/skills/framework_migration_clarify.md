---
name: framework-migration-clarify
description: >
  Clarify stage — optional human-in-the-loop plan amendments after gap-check.
  Add manual steps, exclude steps, or force-include excluded rules.
compatibility:
  tools:
    - get_graph_schema
    - execute_custom_cypher
    - get_pending_steps
    - update_step_status
    - update_queried_entity
    - get_migration_contexts
    - add_manual_step
---

# Clarify Stage — Optional Plan Amendments

Human-in-the-loop corrections after gap-check. All changes persist to graph state on the `MigrationContext`.

**Stage gating** — this skill is read by two audiences:

- **Launching the server:** set `MCP_ACTIVE_STAGE=clarify` in the environment (or pass it to your start/redeploy script) before the MCP server process starts. Tool registration is fixed at startup; it cannot be changed mid-session.

- **Already connected:** if you are an agent with a server already running, do not restart it — infer the active stage from which tools in `compatibility.tools` are available. If a required tool is missing, stop and report a stage mismatch; do not substitute tools from another stage.

## Entry

1. Require `context_id`.
2. Read existing `gapCheckFlags` from the context (via `get_migration_contexts` or custom Cypher).
3. Call `get_pending_steps(context_id)` to see the current queue.

## Allowed mutations

### Force-include excluded rules

When a rule was excluded by entity filtering but should apply:

```
update_queried_entity(context_id, entity_name, result_summary, force_include=true)
```

This adds the entity to `forceIncludedEntities` so its steps appear in `get_pending_steps`.

### Add manual steps

```
add_manual_step(context_id, summary, instruction, file_pattern?, effort?, severity_hint?)
```

Creates a `MigrationStep` with `origin="manual"` scoped via `OWNS_STEP` to this context only.

### Exclude steps

```
update_step_status(context_id, step_id, outcome="excluded", reason="scope decision")
```

Excluded steps leave the pending queue and do **not** block `final_status="complete"`.

**Caution:** Excluding a step that is another step's `BRIDGED_BY` `requiredChange` has **UNRESOLVED** behavior per `015` data-model.md §7 — warn the operator explicitly before excluding; do not assume auto-resolve or manual fallback will apply.

## Workflow

1. Review gap-check flags with the operator.
2. Apply amendments as directed (or skip if plan is acceptable).
3. Re-call `get_pending_steps` to confirm the amended queue.
4. Hand off to `framework-migration-preview` or `framework-migration-execute`.

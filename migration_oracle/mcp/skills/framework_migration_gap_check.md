---
name: framework-migration-gap-check
description: >
  Gap-check stage — mechanical read-only audit of an existing MigrationContext.
  Writes gap-check flags only; does not mutate steps or the codebase.
compatibility:
  tools:
    - get_graph_schema
    - execute_custom_cypher
    - get_pending_steps
    - get_migration_contexts
    - write_gap_check_flags
    - get_steps_for_scope_tier
---

# Gap-Check Stage — Mechanical Plan Audit

Read-only audit of an existing `MigrationContext`. Does **not** mutate step/rule state or the codebase.

**Stage gating** — this skill is read by two audiences:

- **Launching the server:** set `MCP_ACTIVE_STAGE=gap-check` in the environment (or pass it to your start/redeploy script) before the MCP server process starts. Tool registration is fixed at startup; it cannot be changed mid-session.

- **Already connected:** if you are an agent with a server already running, do not restart it — infer the active stage from which tools in `compatibility.tools` are available. If a required tool is missing, stop and report a stage mismatch; do not substitute tools from another stage.

## Entry

1. Require `context_id` — call `get_migration_contexts` if needed to locate it.
2. Read context metadata via `get_migration_contexts` or `execute_custom_cypher` — note `mode` (`full` or `lite`).

## Checks (mode-specific)

| Check | `mode="full"` | `mode="lite"` |
|---|---|---|
| Truncation | Yes | Yes |
| Applicability audit | Yes | Yes |
| Stepless-rule check | Yes | No |
| Bridge-eligibility surfacing | Yes | No |
| Version sanity | Yes | Yes |
| Unresolved Paysafe dependency | Yes | Yes |

### Truncation

Read `diagnostics` cached on the context (set during `plan` via `create_migration_context`).
If `rules_capped_at` is not `null`, emit a `truncation` flag.

### Applicability audit

Call `get_pending_steps(context_id)` and flag steps with `applicability="uncertain"`.

### Stepless-rule check (full mode only)

Use `get_steps_for_scope_tier` per scope tier. Flag rules with entity hits but no linked `MigrationStep`.

### Bridge-eligibility (full mode only)

Flag rules with `BRIDGED_BY` edges where the required change step is still pending.

### Version sanity

Verify `fromVersion`/`toVersion` on the context resolve via graph version nodes.

### Paysafe unresolved

Flag any `com.paysafe` dependencies in scanned entities that lack a resolved version from plan.

## Persist findings

Call `write_gap_check_flags(context_id, flags=[...])` with objects:

```json
{"type": "truncation|applicability_uncertain|stepless_rule|bridge_eligible|version_sanity|paysafe_unresolved", "reference": "optional rule/entity id", "message": "human-readable explanation"}
```

Use `overwrite=false` (default) for idempotent re-runs — duplicate flags are deduplicated.

## Output

Present the flag list to the operator. Do **not** call mutation tools from other stages.

If flags were raised, consider loading the `framework-migration-clarify` bundle next; otherwise proceed to `framework-migration-execute`.

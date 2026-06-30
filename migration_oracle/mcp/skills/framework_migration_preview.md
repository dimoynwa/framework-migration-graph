---
name: framework-migration-preview
description: >
  Preview stage — read-only customer-facing plan rendering grouped by risk,
  with gap-check caveats. Exposes no mutation tools.
compatibility:
  tools:
    - get_pending_steps
    - get_migration_contexts
---

# Preview Stage — Read-Only Plan Rendering

Customer-facing, read-only view of the migration plan. **Zero mutation tools** are available in this session.

**Stage gating** — this skill is read by two audiences:

- **Launching the server:** set `MCP_ACTIVE_STAGE=preview` in the environment (or pass it to your start/redeploy script) before the MCP server process starts. Tool registration is fixed at startup; it cannot be changed mid-session.

- **Already connected:** if you are an agent with a server already running, do not restart it — infer the active stage from which tools in `compatibility.tools` are available. If a required tool is missing, stop and report a stage mismatch; do not substitute tools from another stage.

## Entry

1. Require `context_id`.
2. Call `get_pending_steps(context_id)` for the full queue.
3. Read `gapCheckFlags` from the context for caveat rendering.

## Rendering rules

Group steps by risk label:

| Label | Severity values |
|---|---|
| HIGH | `critical`, `high` |
| MEDIUM | `medium` |
| LOW | `low`, manual steps without severity |

Within each group, list: summary, instruction (truncated if long), effort, applicability, origin (`graph` or `manual`).

## Gap-check caveats

If `gapCheckFlags` is non-empty, render a **Caveats** section before the plan body.
If no flags exist, note "No gap-check findings recorded."

## Constraints

- Do **not** attempt to call mutation tools — they are not registered in this session.
- Do **not** modify the codebase or graph state.
- Present the plan for human approval before starting `framework-migration-execute`.

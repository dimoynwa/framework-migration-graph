# Contract: `update_step_status`

**Work-stream**: WS2 — Graph-State Contract
**FR**: FR-005, FR-006
**File**: `migration_oracle/mcp/graph/queries/context.py` (`_RECORD_STEP_OUTCOME`), `migration_oracle/mcp/tools/context.py`

---

## Purpose

Record the outcome of a migration step (`"completed"`, `"skipped"`, or `"failed"`). After this fix, the call writes **both** the legacy progress arrays and the schema-preferred `STEP_OUTCOME` relationship.

---

## Inputs

| Parameter | Type | Required | Valid values |
|-----------|------|----------|-------------|
| `context_id` | string | yes | Element ID of an existing `MigrationContext` |
| `step_id` | string | yes | Element ID of a `MigrationStep` |
| `outcome` | string | yes | `"completed"`, `"skipped"`, `"failed"` |
| `reason` | string | no | Free-form rationale; now persisted on `STEP_OUTCOME.reason` |

---

## Outputs — Success

```json
{
  "status": "ok",
  "step_id": "<element-id>",
  "outcome": "<string>",
  "context_id": "<element-id>",
  "context_auto_closed": false,
  "context_status": "<string>",
  "completed_count": <integer>,
  "skipped_count": <integer>
}
```

`context_auto_closed`: `true` when all pending steps are done and the context was auto-closed. `context_status`: current value of `ctx.status`.

---

## Outputs — Error (step not on path)

```json
{
  "status": "error",
  "error_code": "step_not_on_path",
  "step_id": "<element-id>",
  "hint": "Step '<step_id>' is not on the migration path for context '<context_id>'."
}
```

---

## Write Behaviour — Additive STEP_OUTCOME (FR-005, FR-006)

### What changes

The `_RECORD_STEP_OUTCOME` Cypher is extended to write `STEP_OUTCOME` in addition to the existing legacy array updates. Both writes happen in the same Cypher statement.

### Corrected `_RECORD_STEP_OUTCOME` Cypher

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (step:MigrationStep) WHERE elementId(step) = $step_id

-- Legacy array writes (UNCHANGED)
SET ctx.completedSteps = CASE $outcome WHEN 'completed'
    THEN ctx.completedSteps + [$step_id] ELSE ctx.completedSteps END,
    ctx.skippedSteps = CASE $outcome WHEN 'skipped'
    THEN ctx.skippedSteps + [$step_id] ELSE ctx.skippedSteps END,
    ctx.failedSteps = CASE $outcome WHEN 'failed'
    THEN coalesce(ctx.failedSteps, []) + [$step_id] ELSE coalesce(ctx.failedSteps, []) END

-- STEP_OUTCOME MERGE (NEW)
WITH ctx, step
MERGE (ctx)-[so:STEP_OUTCOME]->(step)
SET so.status    = $outcome,
    so.reason    = $reason,
    so.updatedAt = datetime()

RETURN elementId(ctx) AS context_id,
       size(ctx.completedSteps) AS completed_count,
       size(ctx.skippedSteps)   AS skipped_count,
       ctx.status AS migration_status
```

### Idempotency (FR-006)

The `MERGE (ctx)-[so:STEP_OUTCOME]->(step)` pattern guarantees that calling `update_step_status` twice for the same `(context_id, step_id)` pair:
- Updates the single existing `STEP_OUTCOME` relationship (setting the latest `status`, `reason`, `updatedAt`)
- Does NOT create a second `STEP_OUTCOME` relationship

### Legacy array behaviour (unchanged)

The legacy arrays `completedSteps`, `skippedSteps`, `failedSteps` on `MigrationContext` continue to be appended on each call. Their counts are returned in `completed_count` and `skipped_count`. These arrays are not deduplicated by this fix — that behaviour was pre-existing and out of scope.

### STEP_OUTCOME is authoritative on conflict

When a step's outcome changes (e.g. `failed` → `completed`), the legacy arrays will contain the element ID in **both** `failedSteps` and `completedSteps`. `STEP_OUTCOME.status` always reflects the **latest** recorded outcome — only one `STEP_OUTCOME` relationship exists per `(context, step)` pair, and it is overwritten on each call. Callers that need the current outcome must read `STEP_OUTCOME`; the legacy arrays may double-count during the dual-write period.

### `reason` now persisted

Previously the docstring said "reason is accepted but not persisted." After this fix, `reason` IS persisted as `so.reason` on the `STEP_OUTCOME` relationship. The docstring must be updated to reflect this.

---

## Legacy Array Readers — Migration Note (FR-005)

The legacy arrays `ctx.completedSteps`, `ctx.skippedSteps`, and `ctx.failedSteps` **must continue to be written** until all of the following readers are migrated to use `STEP_OUTCOME`:

| Reader | Location | Arrays used |
|--------|----------|------------|
| `_GET_PENDING_STEPS` Cypher | `migration_oracle/mcp/graph/queries/context.py` | `ctx.completedSteps`, `ctx.skippedSteps`, `ctx.failedSteps` — used in `WHERE NOT elementId(s) IN ctx.completedSteps AND NOT elementId(s) IN ctx.skippedSteps AND NOT elementId(s) IN coalesce(ctx.failedSteps, [])` to exclude already-processed steps |
| `create_migration_context` return value | `migration_oracle/mcp/tools/context.py` | Returns `completed_steps`, `skipped_steps` from the arrays |
| `close_migration_context` return value | `migration_oracle/mcp/tools/context.py` | Returns `completed_steps`, `skipped_steps` from the arrays |
| `update_step_status` return value | `migration_oracle/mcp/tools/context.py` | Returns `completed_count = size(ctx.completedSteps)`, `skipped_count = size(ctx.skippedSteps)` |
| `framework_migration_main.md` Loop I | `migration_oracle/mcp/skills/framework_migration_main.md` | Loads `completedSteps[]`, `skippedSteps[]` for session state on resume |

**This fix is additive.** The `_RECORD_STEP_OUTCOME` Cypher writes `STEP_OUTCOME` in addition to the existing array appends — it does not replace them. Removal of array writes is a separate future migration task, not in scope for this feature.

## FR-019 Compliance

`update_step_status` writes through `_RECORD_STEP_OUTCOME` only. `execute_custom_cypher` is read-only and must not be used as an alternative write path for `STEP_OUTCOME` or the legacy arrays.

---

## Docstring update (required)

```
Record the outcome of a migration step: 'completed', 'skipped', or 'failed'.

Writes both the STEP_OUTCOME relationship (status, reason, updatedAt) on the
MigrationContext → MigrationStep pair (idempotent per pair) and the legacy
completedSteps/skippedSteps/failedSteps arrays on the context node.

Auto-closes the context when no pending steps remain after this call.
Returns: step_id, outcome, context_auto_closed, context_status, completed_count, skipped_count.
```

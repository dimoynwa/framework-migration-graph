# Contract: STEP_OUTCOME Relationship

**Spec**: 011-mcp-live-probe-fixes | **FR**: FR-001–FR-004

## Purpose

Defines how per-step outcomes are persisted in Neo4j. Replaces the `stepNotes` map-valued node
property introduced by spec 010 FR-005, which is the confirmed source of `Neo4j TypeError`
(map-valued node properties require APOC; APOC is unavailable on Neo4j 5 Community).

---

## Relationship Schema

```
(ctx:MigrationContext)-[:STEP_OUTCOME {status, reason, updatedAt}]->(s:MigrationStep)
```

| Property    | Type     | Required | Notes |
|-------------|----------|----------|-------|
| `status`    | String   | YES      | `"completed"` \| `"skipped"` \| `"failed"` |
| `reason`    | String   | NO       | Agent-supplied rationale. `null` when not provided. |
| `updatedAt` | DateTime | YES      | `datetime()` at time of last write. |

---

## MERGE Semantics

```cypher
MERGE (ctx)-[rel:STEP_OUTCOME]->(s)
SET rel.status    = $status,
    rel.reason    = $reason,
    rel.updatedAt = datetime()
```

The MERGE key is the `(ctx, s)` pair — one relationship per (context, step) combination.
Repeated calls with a different status UPDATE the existing relationship in place.
No duplicate relationships are created.

---

## completedSteps Preservation Rule (FR-003)

The `STEP_OUTCOME` relationship write MUST be paired with the existing `_RECORD_STEP_OUTCOME`
Cypher that advances `ctx.completedSteps`, `ctx.skippedSteps`, and `ctx.failedSteps` String arrays.
Both writes MUST occur in the same `write_session()` block so they succeed or fail atomically.

The String-array fields (`completedSteps` etc.) serve as the fast-path filter used by
`get_pending_steps`. The `STEP_OUTCOME` relationship is the durable store for status + reason.
Both are required.

---

## step_not_on_path Guard (FR-004)

Before creating a `STEP_OUTCOME` relationship, the tool MUST validate that `step_id` exists on
the context's migration path (reachable via `UPGRADES_FROM → Version → INCLUDES_RULE → MigrationRule
→ REQUIRES_STEP → MigrationStep`). If the step is not on the path:

1. Return a structured error: `{status: "error", error_code: "step_not_on_path", step_id: ..., hint: ...}`.
2. Do NOT create a `STEP_OUTCOME` relationship.
3. Do NOT advance `completedSteps`/`skippedSteps`/`failedSteps`.

The validation runs as a `read_session()` query before the `write_session()` block.

---

## Prohibition on Map-Valued Node Properties

`ctx.stepNotes` MUST NOT exist anywhere in the codebase after this spec is implemented.

More broadly: no tool in `migration_oracle/mcp/` MUST write a map-valued property to any Neo4j
node (`SET node.prop = {key: value}`). Any per-step or per-run structured state MUST be stored
as a relationship with scalar properties.

This applies to:
- `MigrationContext` nodes
- Any other nodes whose properties are updated by MCP tools

---

## Migration Note

The `_READ_STEP_NOTES` and `_WRITE_STEP_NOTES` Cypher constants in
`migration_oracle/mcp/graph/queries/context.py`, and the `if reason:` block in
`record_step_outcome` that calls them, MUST be removed as the very first implementation task
of spec 011 (before the `STEP_OUTCOME` relationship code is added). This ensures no code path
can trigger the `Neo4j TypeError` during development.

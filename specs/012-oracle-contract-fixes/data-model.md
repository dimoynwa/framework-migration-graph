# Data Model: Oracle Contract Fixes

**Feature**: `012-oracle-contract-fixes`
**Created**: 2026-06-13
**Authority**: `docs/graph-schema.md` (read-only for this feature — no schema changes are introduced)

---

## Overview

This feature introduces **no new node labels, relationship types, or graph-schema constraints**. All model elements below already exist in `docs/graph-schema.md`. This document records the authoritative names, property sets, and behavioural contracts that implementation must respect — and that prior code had wrong.

---

## 1. `STEP_OUTCOME` Relationship

```
(MigrationContext)-[:STEP_OUTCOME {status, reason, updatedAt}]->(MigrationStep)
```

### Properties

| Property | Type | Required | Valid values |
|----------|------|----------|-------------|
| `status` | string | yes | `"completed"`, `"skipped"`, `"failed"` |
| `reason` | string | nullable | Free-form human-readable rationale |
| `updatedAt` | datetime | yes | Neo4j `datetime()` at time of write |

### MERGE identity

The relationship is **merged on the `(context, step)` pair** — specifically on the combination of:
- `elementId(ctx)` (the `MigrationContext` node)
- `elementId(step)` (the `MigrationStep` node)

Neo4j MERGE pattern:
```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (step:MigrationStep) WHERE elementId(step) = $step_id
MERGE (ctx)-[so:STEP_OUTCOME]->(step)
SET so.status    = $status,
    so.reason    = $reason,
    so.updatedAt = datetime()
```

**Idempotency guarantee**: Calling `update_step_status` twice for the same `(context_id, step_id)` pair updates the single existing `STEP_OUTCOME` relationship; it never creates a second one.

### Relationship to legacy arrays

The legacy properties `completedSteps`, `skippedSteps`, `failedSteps` on `MigrationContext` continue to be written **in addition** to `STEP_OUTCOME`. They are **not removed** by this feature. Both write paths are maintained until all readers migrate to `STEP_OUTCOME`.

| Writer | Status | Notes |
|--------|--------|-------|
| `_RECORD_STEP_OUTCOME` Cypher — legacy arrays | **retained** | unchanged |
| `_RECORD_STEP_OUTCOME` Cypher — `STEP_OUTCOME` MERGE | **added** | new addition in this feature |

### Progress-summary query (schema example #5)

Once the MERGE write is in place, the schema's example query returns non-zero counts:

```cypher
MATCH (ctx:MigrationContext {projectId: $projectId, fromVersion: $from, toVersion: $to})
OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(step:MigrationStep)
RETURN ctx.status,
       count(CASE WHEN so.status = 'completed' THEN 1 END) AS completed,
       count(CASE WHEN so.status = 'skipped'   THEN 1 END) AS skipped,
       count(CASE WHEN so.status = 'failed'    THEN 1 END) AS failed
```

---

## 2. `MigrationContext.queriedEntities` Property

### Storage format

| Property | Type | Initialised to |
|----------|------|----------------|
| `queriedEntities` | string (JSON-serialised map) | `'{}'` |

The property is already initialised to `'{}'` at context creation (see `_CREATE_OR_GET_CONTEXT`). This feature adds the **write path** that populates it.

### Key/value schema

```
{
  "<entity_name>": "<result_summary>"
}
```

| Key | Type | Constraints |
|-----|------|-------------|
| `entity_name` | string | Fully-qualified or display name of the queried entity; must match what the agent passes to deprecation/query tools |
| `result_summary` | string | ≤500 characters; plain-text summary of the entity query result (e.g. `"deprecated in 3.0.0, replaced by Foo"`) |

### Write lifecycle

1. `create_migration_context` → `queriedEntities = '{}'`
2. After each successful entity query in Loop II: agent calls `update_queried_entity(context_id, entity_name, result_summary)`
3. On Loop II resume: agent reads `queriedEntities`, skips any key already present (unless `force_refresh=True`)

### Implementation note — no APOC required

Because Neo4j 5 without APOC cannot natively manipulate JSON maps in Cypher, the write is performed in Python (read → parse → update → serialise → write). The tool reads the current `queriedEntities` string, parses it as JSON, upserts the new key, serialises back, and writes with `SET ctx.queriedEntities = $updated_json`. This is a two-query operation within a single tool call.

---

## 3. `MigrationContext.status` Enum (close-status)

The `status` property on `MigrationContext` accepts five values. `close_migration_context` previously only accepted "complete" and "partial" — `"abandoned"` was rejected at the tool layer despite being schema-valid.

### Full enum

| Value | Set by | Description |
|-------|--------|-------------|
| `"in-progress"` | `create_migration_context` (ON CREATE) | Session active |
| `"blocked"` | Manual agent action | Session waiting on an external dependency |
| `"complete"` | `update_step_status` (auto-close) or `close_migration_context` | All steps done |
| `"partial"` | `close_migration_context` | Session ended with steps skipped |
| `"abandoned"` | `close_migration_context` (**newly accepted**) | Session cancelled or deferred |

### Fix required

`close_migration_context` docstring and input validation must:
1. List all three accepted values: `"complete"`, `"partial"`, `"abandoned"`
2. Reject any other value with `{"status": "error", "error_code": "invalid_final_status", "hint": "final_status must be one of: complete, partial, abandoned"}`

The Cypher (`_CLOSE_CONTEXT`) already performs a blind `SET ctx.status = $final_status` and needs no change — validation happens in the Python tool layer.

---

## 4. `OpenRewriteRecipe` — Property and Relationship Corrections

### `composite` property (NOT `isComposite`)

| Property | Type | Correct name | Wrong name (in current code) |
|----------|------|--------------|------------------------------|
| Composite flag | boolean | **`composite`** | `isComposite` |

Schema definition (from `graph-schema.md`):
```
(:OpenRewriteRecipe {composite: boolean, ...})
```

The `hydrate_openrewrite_recipes` function in `search.py` currently checks `r.isComposite` — this property does not exist on the node and always resolves to `false`, making `only_composite=True` return nothing and `only_composite=False` return everything.

**Fix**: Change all references from `r.isComposite` to `r.composite`.

### `HAS_PARAM` relationship and `RecipeParam` nodes (NOT `requiredParams` array property)

Required parameters are NOT stored as an array property on `OpenRewriteRecipe`. They are modelled as separate `RecipeParam` nodes linked via `HAS_PARAM`:

```
(OpenRewriteRecipe)-[:HAS_PARAM]->(RecipeParam {name, type, required, description, example})
```

| Property | Type | Description |
|----------|------|-------------|
| `required` | boolean | `true` = must be supplied before the recipe can run |

**Wrong approach** (current code): `AND size(coalesce(r.requiredParams, [])) = 0`
This checks a non-existent array property. `coalesce(null, [])` returns `[]`, so `size([]) = 0` is always `true` — the filter silently passes every recipe.

**Correct approach** (Cypher subquery):
```cypher
AND NOT EXISTS {
  MATCH (r)-[:HAS_PARAM]->(p:RecipeParam)
  WHERE p.required = true
}
```

Or equivalently (for compatibility with Neo4j 5 without subquery support):
```cypher
AND NOT (r)-[:HAS_PARAM {required: true}]->()
```

Both correctly exclude recipes that have at least one required `RecipeParam`.

---

## 5. `AUTOMATED_BY` Traversal — Correct Node Start

```
(MigrationStep)-[:AUTOMATED_BY {auto, confidence, method, missingRequiredParams}]->(OpenRewriteRecipe)
```

This relationship starts from `MigrationStep`, **not** `MigrationRule`.

### Current bug in `_ANALYZE_UPGRADE_PATH`

```cypher
-- WRONG (current):
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

-- CORRECT (fix):
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
```

### Corrected traversal for recipe-per-step output

After the fix, each rule's `recipes` list contains entries associated with the **steps** that have `AUTOMATED_BY` edges:

```cypher
OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
```

A rule with N steps, where M steps have `AUTOMATED_BY` edges, produces M recipe entries (one per step). A step with no `AUTOMATED_BY` edge contributes an empty `recipes` list for that step. The empty list is distinct from the rule having no steps.

---

## 6. Severity Rank — `SEVERITY_RANK` Mapping

Already correct in `_severity.py`. Documented here for contract reference.

| Severity | Rank (integer) |
|----------|----------------|
| `"low"` | 1 |
| `"medium"` | 2 |
| `"high"` | 3 |
| `"critical"` | 4 |

"At or above threshold" = `SEVERITY_RANK[severity] >= SEVERITY_RANK[threshold]`.

Any string not in this map is **invalid** and must be rejected with `{"status": "error", "error_code": "invalid_severity_threshold"}` before the query executes.

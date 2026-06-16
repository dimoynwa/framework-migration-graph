# Contract: get_migration_contexts

**Tool**: `get_migration_contexts`  
**Spec anchor**: FR-B01, US2.1, US2.4  
**New in**: 013-real-run-hardening

---

## Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `project_id` | `str` | Yes | The project identifier to query contexts for |
| `framework` | `str \| None` | No | If supplied, filter to contexts for this framework. `null` returns all frameworks. |

---

## Return Shape

```json
{
  "status": "ok",
  "project_id": "string",
  "count": 0,
  "contexts": [
    {
      "id": "string (Neo4j elementId)",
      "projectId": "string",
      "fromVersion": "string (exact requested)",
      "toVersion": "string (exact requested)",
      "framework": "string",
      "status": "string (in-progress | complete | partial | abandoned)",
      "createdAt": "string (ISO datetime)",
      "updatedAt": "string (ISO datetime)",
      "outcome_counts": {
        "completed": 0,
        "failed": 0,
        "skipped": 0,
        "deferred": 0
      }
    }
  ]
}
```

**Empty result** (project has no contexts):

```json
{
  "status": "ok",
  "project_id": "string",
  "count": 0,
  "contexts": []
}
```

`count: 0` with an empty array is the correct response — not an error.

**Note**: `outcome_counts` are derived from `STEP_OUTCOME` relationships on each context. Total step count and "pending" count are not returned — they require running the full applicability query (`get_pending_steps`) and belong to that tool.

---

## Cypher

```cypher
MATCH (ctx:MigrationContext {projectId: $project_id})
WHERE ($framework IS NULL OR ctx.framework = $framework)

OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(:MigrationStep)
WITH ctx,
     count(CASE WHEN so.status = 'completed' THEN 1 END) AS completed_count,
     count(CASE WHEN so.status = 'failed'    THEN 1 END) AS failed_count,
     count(CASE WHEN so.status = 'skipped'   THEN 1 END) AS skipped_count,
     count(CASE WHEN so.status = 'deferred'  THEN 1 END) AS deferred_count

RETURN
  elementId(ctx)    AS id,
  ctx.projectId     AS projectId,
  ctx.fromVersion   AS fromVersion,
  ctx.toVersion     AS toVersion,
  ctx.framework     AS framework,
  ctx.status        AS status,
  toString(ctx.createdAt)  AS createdAt,
  toString(ctx.updatedAt)  AS updatedAt,
  completed_count,
  failed_count,
  skipped_count,
  deferred_count

ORDER BY ctx.createdAt DESC
```

**Index used**: `context_project` range index on `(mc.projectId)` — already defined in `migration_oracle/graph/indexes.py`. No new index required.

---

## Loop I Integration — Context Discovery and Supersede Flow

`get_migration_contexts` is the first call in Loop I step 1. It replaces the previous implicit "check for existing context" narrative. The harness follows this decision sequence:

```
1. Call get_migration_contexts(project_id=<id>)
2. If count=0 → proceed to scan + create (no prior session).
3. If count>0 → surface the list to the engineer.
   a. For each context with status="in-progress" or "blocked":
      show id, fromVersion, toVersion, createdAt, updatedAt, outcome_counts.
   b. If a stale context has the wrong triple (different from/toVersion):
      call close_migration_context(context_id, final_status="abandoned") to supersede it.
   c. If the intended triple already exists with status="in-progress":
      resume it — call create_migration_context with the same triple (MERGE match path
      refreshes the entity set and returns created=false).
   d. If the intended triple exists with status="complete":
      surface the completion summary. Offer to start a new context for a different triple. Stop.
4. After abandoning any stale contexts, call create_migration_context with the intended triple.
```

This supersede flow is the Loop I implementation of US2 (FR-B01, FR-B02).

---

## Back-Compatibility Note (PLAN-12)

Contexts created before the round-2 STEP_OUTCOME edge write was introduced have no `STEP_OUTCOME` relationships. For these legacy contexts, `get_migration_contexts` will return `outcome_counts: {completed: 0, failed: 0, skipped: 0, deferred: 0}` — all zeros — even when the context has recorded outcomes in the legacy array format (`ctx.completedSteps`, etc.).

Implementations SHOULD either:
- Accept this limitation and note it in response metadata: `"legacyContext": true` when `outcome_counts` totals zero but `ctx.completedSteps` or `ctx.skippedSteps` is non-empty, OR
- Run a one-time backfill that creates STEP_OUTCOME edges from the existing legacy arrays before `get_migration_contexts` is deployed.

No silent failure — consumers must be aware that zero outcome counts may represent a pre-round-2 context.

---

## Error Cases

| Condition | Response |
|---|---|
| `project_id` is empty string or None | `status: "error"`, `error_code: "missing_project_id"` |
| Database connectivity failure | `status: "error"`, `error_code: "db_error"`, `hint: <message>` |

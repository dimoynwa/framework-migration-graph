# Contract: `update_queried_entity`

**Work-stream**: WS5 — Resumability
**FR**: FR-014
**File**: `migration_oracle/mcp/tools/context.py` (new tool), `migration_oracle/mcp/graph/queries/context.py` (new function)

---

## Purpose

Cache the result of a Loop II entity query on the `MigrationContext` node. Called by the agent after each successful entity query to write `entity_name → result_summary` into `MigrationContext.queriedEntities`. Enables the Loop II skip guard on resume: an entity already present in `queriedEntities` is not re-queried unless `force_refresh=True`.

**Note**: `execute_custom_cypher` is read-only and must not be used for this write. All writes go through this tool (FR-019).

---

## Inputs

| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| `context_id` | string | yes | Element ID of an existing `MigrationContext` | Session to update |
| `entity_name` | string | yes | Non-empty | Fully-qualified or display name of the queried entity (e.g. `"org.example.Foo"`) |
| `result_summary` | string | yes | ≤500 characters; truncated silently beyond limit | Plain-text summary of the query result |

---

## Outputs — Success

```json
{
  "status": "ok",
  "context_id": "<element-id>",
  "entity_name": "<string>",
  "cached_count": <integer>
}
```

`cached_count`: total number of entries in `queriedEntities` after the write (including the new/updated entry).

---

## Outputs — Error (context not found)

```json
{
  "status": "error",
  "error_code": "context_not_found",
  "hint": "Context '<context_id>' not found"
}
```

Returned when no `MigrationContext` exists for the given `context_id`.

---

## `queriedEntities` Key/Value Schema

`MigrationContext.queriedEntities` stores a JSON-serialised string on the node:

```json
{
  "<entity_name>": "<result_summary>"
}
```

| Key | Type | Description |
|-----|------|-------------|
| `entity_name` | string | The same name the agent used to query the entity (e.g. fully-qualified class name, dependency GA coordinate, property key) |
| `result_summary` | string | ≤500 chars plain text; e.g. `"deprecated in 3.0.0, replaced by org.example.Bar"` |

The property is initialised to `'{}'` at context creation (`_CREATE_OR_GET_CONTEXT`). This tool upserts entries — an existing key is overwritten when `force_refresh` is in effect.

---

## Write Site

**Call sequence** (Loop II, per entity):

```
1. get_steps_for_scope_tier(context_id, scope, severity_threshold)   → hits for entity
2. resolve_deprecation(entity_name) / analyze_upgrade_path(...)      → query result
3. update_queried_entity(context_id, entity_name, result_summary)    ← THIS TOOL
```

This tool is called **after** the entity query succeeds (step 3). If the entity query fails or returns no result, do not call this tool — the entity remains uncached and will be re-queried on the next resume.

---

## Skip Guard Integration

In Loop II, before any entity tool call:

```python
queried = json.loads(ctx.queriedEntities)
# force_refresh is a Loop II agent-loop flag (e.g. from --force-refresh <entity_name> passed
# when invoking the skill). It is NOT a parameter of get_steps_for_scope_tier or this tool.
# See framework_migration_main.md Loop II for how it is set and which entity it targets.
if entity_name in queried and not force_refresh_for_this_entity:
    # Use cached result — do not re-query
    result_summary = queried[entity_name]
else:
    # Issue the tool call
    result = resolve_deprecation(entity_name=entity_name)
    result_summary = build_summary(result)
    update_queried_entity(context_id=ctx_id, entity_name=entity_name, result_summary=result_summary)
```

---

## Concurrency Limitation

`update_queried_entity` uses a read-modify-write pattern (read JSON → update in Python → write back) without atomic graph locking. Two concurrent writes for the same `context_id` will race and the slower write will overwrite the faster write's entry, silently dropping a key.

**Required**: calls to `update_queried_entity` for the same `context_id` must be **sequential**. Do not issue two `update_queried_entity` calls concurrently. Parallel entity-query tool calls (`resolve_deprecation`, `analyze_upgrade_path`) are safe; only the cache-write step must be serialised.

---

## Implementation — Two-Query Python Pattern

Because Neo4j 5 without APOC cannot manipulate JSON maps in Cypher, the write uses two queries inside one tool call:

**Read query** (read_session):
```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id
RETURN ctx.queriedEntities AS qe
```

**Python update** (in-process):
```python
import json
current = json.loads(record["qe"] or "{}")
current[entity_name] = result_summary[:500]
updated_json = json.dumps(current, ensure_ascii=False)
```

**Write query** (write_session):
```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id
SET ctx.queriedEntities = $qe
RETURN 1
```

`cached_count` is computed in Python as `len(current)` after the upsert — no Cypher projection needed (and no APOC available).

---

## FR-019 Compliance

This tool is the **only write path** for `queriedEntities`. `execute_custom_cypher` is read-only and must not be used as an alternative write path.

# Data Model — Spec 010: MCP Defect Fixes (Migration Session Hardening)

**Phase 1 artifact.**
No new node labels. No new relationship types. No Cypher schema migration required.
Changes are limited to one new optional property on an existing node and new fields in Python-level dict return values.

---

## 1. Existing Node Changes

### MigrationContext (node)

Existing properties (unchanged):

| Property | Type | Notes |
|---|---|---|
| `id` | `string` | Unique session identifier |
| `framework` | `string` | e.g. `"spring-boot"` |
| `fromVersion` | `string` | Source version, e.g. `"3.2.0"` |
| `toVersion` | `string` | Target version, e.g. `"3.4.0"` |
| `status` | `string` | Session lifecycle status |
| `stepStatuses` | `map<string, string>` | Key = `step_id`, value = status string |
| `createdAt` | `datetime` | Session creation timestamp |
| `updatedAt` | `datetime` | Last-updated timestamp |

**New optional property:**

| Property | Type | Default | Storage |
|---|---|---|---|
| `stepNotes` | `map<string, string>` | `{}` (empty map) | Neo4j map property — not a serialised string, not a list |

**Semantics:**
- Key = `step_id` (string). Value = reason text (string).
- Written by `update_step_status` when a non-empty `reason` argument is provided.
- Never contains null keys or null values.
- Absent nodes treat a missing `stepNotes` property as `{}` (see §3).

---

## 2. Tool Return Shape Changes

### `build_recipe_plan` — step dict (`manual_track` entries)

All existing fields on each step dict remain unchanged.

Two new fields are added to every entry in `manual_track`:

| Field | Type | Nullable |
|---|---|---|
| `applicability` | `"applicable" \| "not_applicable" \| "unknown"` | Never null |
| `matched_entities` | `list[str]` | Never null; empty list when not applicable or unknown |

**Applicability rules (evaluated in order; authoritative order matches `contracts/applicability_semantics.md` and `plan.md` pseudocode):**

1. `user_entities` is empty or absent →
   `applicability = "unknown"`, `matched_entities = []`
   _(regardless of step edges)_

2. Step has no `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, or `AFFECTS_DEPENDENCY` edges →
   `applicability = "unknown"`, `matched_entities = []`
   _(regardless of `user_entities` content)_

3. `user_entities` is non-empty AND step edges intersect with `user_entities` →
   `applicability = "applicable"`, `matched_entities` = sorted list of matched entity names

4. `user_entities` is non-empty AND step edges do NOT intersect with `user_entities` →
   `applicability = "not_applicable"`, `matched_entities = []`

**`matched_entities`** contains entity names sourced from the `user_entities` input list that are present among the step's `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, or `AFFECTS_DEPENDENCY` target node names.

---

### `check_version_availability` — new tool return shape

**Success shape (`status: "ok"`):**

```json
{
  "status": "ok",
  "exists_in_graph": "<bool>",
  "ga_available": "<bool>",
  "latest_patch": "<str | null>",
  "hint": "<str>"
}
```

| Field | Type | Semantics |
|---|---|---|
| `exists_in_graph` | `bool` | `true` iff a `Version` node with `framework=<framework>` and `version=<major.minor.0>` exists in Neo4j |
| `ga_available` | `bool` | `true` iff Maven Central returns `numFound >= 1` for the probed `<major.minor.0>` version |
| `latest_patch` | `str \| null` | Highest patch version for the same `major.minor` series returned by Maven Central; `null` when the probe fails or returns no results |
| `hint` | `str` | Human-readable message — e.g. available versions found, probe failure note, or unsupported framework |

**Error shapes:**

_Unsupported framework:_
```json
{
  "status": "error",
  "error_code": "unsupported_framework",
  "exists_in_graph": false,
  "ga_available": false,
  "latest_patch": null,
  "hint": "Unknown framework; supported: spring-boot"
}
```

_Maven Central unreachable:_
Returns `status: "ok"` with `ga_available: false`, `latest_patch: null`, and a `hint` that notes the probe failure. No exception is raised to the caller.

---

## 3. Cypher Property Storage Patterns

### `stepNotes` write pattern

`stepNotes` is merged entirely on the Python side. No APOC map functions are used.

Read–merge–write sequence (pseudocode):

```python
# 1. Read current map (absent property → empty dict)
existing = session.run(
    "MATCH (ctx:MigrationContext {id: $id}) RETURN coalesce(ctx.stepNotes, {}) AS m",
    id=ctx_id,
).single()["m"]

# 2. Merge in Python
existing[step_id] = reason   # overwrite or insert key

# 3. SET full map back
session.run(
    "MATCH (ctx:MigrationContext {id: $id}) SET ctx.stepNotes = $m",
    id=ctx_id, m=existing,
)
```

### `MigrationContext.stepNotes` initial value

When reading an existing `MigrationContext` node that was created before this spec, the property may be absent. The Cypher expression `coalesce(ctx.stepNotes, {})` is used to treat a missing property as an empty map, avoiding null-handling in Python code.

### Why APOC is not used

The project runs `neo4j:5` Community Edition via `docker-compose`. APOC is not installed or configured in that environment. All map manipulation (merge, upsert of a single key) is therefore performed in Python before issuing a single `SET ctx.stepNotes = $m` write.

---

## 4. No Schema Migration Required

No Cypher schema migration script is needed for this spec.

- `stepNotes` is an optional property on an existing `MigrationContext` node. Neo4j does not require a schema declaration for new properties; the first write creates it automatically.
- The `build_recipe_plan` and `check_version_availability` changes are Python-level dict fields only — they are not persisted in Neo4j.
- All changes are strictly additive. Existing nodes without `stepNotes` continue to function correctly via the `coalesce(ctx.stepNotes, {})` read pattern described in §3.

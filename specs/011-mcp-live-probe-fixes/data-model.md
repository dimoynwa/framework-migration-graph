# Data Model: MCP Live-Probe Fixes (spec 011)

**Feature Branch**: `011-mcp-live-probe-fixes`

This document describes new node labels, new relationship types, updated node/relationship
property schemas, updated tool return shapes, and new error shapes introduced by spec 011.

---

## New Node Label: `LifecycleAlert`

A `LifecycleAlert` node represents a phase-level, human-readable signal about a major change in a
framework version (e.g. a default-policy change in Spring Security). It is linked to a `Version`
node and surfaced by `analyze_upgrade_path(include_lifecycle=True)`.

### Properties

| Property   | Type   | Required | Description |
|------------|--------|----------|-------------|
| `message`  | String | YES      | Human-readable alert text. e.g. `"Spring Security 7 changes the default CSRF policy — review all state-changing endpoints."` |
| `category` | String | YES      | Coarse classification. One of: `"security"`, `"api"`, `"config"`, `"dependency"`, `"other"`. |
| `phase`    | String | YES      | Migration phase the alert is most relevant to. One of: `"pre-migration"`, `"migration"`, `"post-migration"`. |

### MERGE Identity

`LifecycleAlert` nodes are merged on `message` within the context of the linked `Version`. The
MERGE predicate is on the **relationship** `(v:Version)-[:HAS_LIFECYCLE_ALERT]->(a:LifecycleAlert {message: $message})`.

---

## New Relationship Type: `STEP_OUTCOME`

`(ctx:MigrationContext)-[:STEP_OUTCOME {status, reason, updatedAt}]->(s:MigrationStep)`

Replaces the `stepNotes` map-valued node property that was introduced by spec 010 FR-005 and
immediately confirmed as a Neo4j Community `TypeError` bug (APOC is unavailable; map-valued
node properties require APOC for MERGE). See [contracts/step_outcome_relationship.md](contracts/step_outcome_relationship.md).

### Properties

| Property    | Type     | Required | Description |
|-------------|----------|----------|-------------|
| `status`    | String   | YES      | Outcome recorded by `update_step_status`. One of: `"completed"`, `"skipped"`, `"failed"`. |
| `reason`    | String   | NO       | Human-readable rationale supplied by the agent. `null` when not provided. MUST NOT be coerced to a map. |
| `updatedAt` | DateTime | YES      | Neo4j `datetime()` at time of last write. Set by the MERGE…SET in the Cypher query. |

### MERGE Semantics

Created with `MERGE (ctx)-[:STEP_OUTCOME]->(s)` keyed on the `(ctx, s)` pair. Repeated calls with
different `status`/`reason` values UPDATE the existing relationship in place — no duplicate
relationship is created.

---

## New Relationship Type: `HAS_LIFECYCLE_ALERT`

`(v:Version)-[:HAS_LIFECYCLE_ALERT]->(a:LifecycleAlert)`

No properties on the relationship itself. Created with MERGE for idempotency.

---

## Updated Node: `Version`

| Property      | Type   | Added/Changed | Description |
|---------------|--------|---------------|-------------|
| `fromVersion` | String | ADDED         | The source version this run was built from. Persisted by `upsert_version_artifact_paths` at population time. Used by `list_pipeline_runs` as the primary source for `from_version` in the tool response. |

---

## Updated Node: `MigrationRule`

| Property    | Type   | Added/Changed | Description |
|-------------|--------|---------------|-------------|
| `framework` | String | ADDED         | Display-form framework name (e.g. `"Spring Boot"`). Set on CREATE and backfilled on MATCH when absent. Required to scope rule queries without traversing to `Version` nodes. |
| `title`     | String | EXISTING      | Short rule title. Now projected by `analyze_upgrade_path` as the top-level `title` field (was previously absent from the response). |

---

## Updated Tool Return Shape: `analyze_upgrade_path`

Each rule in the `rules` array now includes the following fields (previously null/absent):

| Field         | Source                        | Notes |
|---------------|-------------------------------|-------|
| `title`       | `rule.title`                  | Short rule title. New in spec 011. |
| `change_type` | `rule.changeType`             | Existing property, now projected. |
| `reason`      | `rule.statement`              | Maps from `rule.statement` (the `reason` field in the Cypher map already exists but mapped from `rule.reason`; this spec aligns it with `rule.statement` per FR-015). |
| `severity`    | `BreakingScope.severity`      | Extracted from the `scopes` array in `_flatten_rules` — first non-null severity value from the rule's scope list. `null` for scopeless rules. |

---

## Updated Tool Return Shape: `check_version_availability`

The `framework` parameter now accepts any of the following (case-insensitive,
space/hyphen-insensitive): `"Spring Boot"`, `"spring boot"`, `"spring-boot"`, `"springboot"`.

All spellings resolve to the same canonical record. The graph lookup uses `display` form
(`"Spring Boot"`); the Maven coordinate lookup uses `slug` form (`"spring-boot"`).

Response shape is unchanged from spec 010; the fix is the input normalisation layer.

---

## Updated Tool Return Shape: `list_pipeline_runs`

The `from_version` field in each run entry is no longer hardcoded to `""`.

| Priority | Source |
|----------|--------|
| 1st      | `v.fromVersion` stored on the Version node (persisted at ingestion) |
| 2nd      | Filename parse from `raw_md_path`: regex anchored on `-to-` separator and `-changes` token, tolerates `_filtered.md` suffix |
| Fallback | `""` when neither source yields a value (no exception) |

---

## Updated Tool Return Shape: `get_steps_for_scope_tier`

The `hits` list now includes steps with `scope: null` (rules with no `BreakingScope`). Previously
these were silently dropped by the Python severity filter. Scopeless steps are included regardless
of `severity_threshold` because they have no severity to compare.

---

## Error Shape: `step_not_on_path` (FR-004)

Returned when `update_step_status` is called with a `step_id` that does not exist on the
context's migration path. No `STEP_OUTCOME` relationship is created in this case.

```json
{
  "status": "error",
  "error_code": "step_not_on_path",
  "step_id": "<supplied step_id>",
  "hint": "Step <step_id> is not part of migration path for context <context_id>"
}
```

---

## Error Shape: `unsupported_framework` (updated by FR-008)

Returned when `check_version_availability` receives a framework value that cannot be resolved
by the `canonical_framework` helper. No network call is made.

```json
{
  "status": "error",
  "error_code": "unsupported_framework",
  "exists_in_graph": false,
  "ga_available": false,
  "latest_patch": null,
  "hint": "Unknown framework; supported: Spring Boot"
}
```

The `hint` field now lists the **display names** of supported frameworks (not slugs).

---

## Summary of Schema Changes

| What | Change type | Details |
|------|-------------|---------|
| `LifecycleAlert` node | NEW label | Properties: `message`, `category`, `phase` |
| `STEP_OUTCOME` relationship | NEW type | Properties: `status`, `reason`, `updatedAt` |
| `HAS_LIFECYCLE_ALERT` relationship | NEW type | No properties |
| `Version.fromVersion` | NEW property | Persisted at ingestion |
| `MigrationRule.framework` | NEW property | Display-form framework name |
| `MigrationRule.title` | EXISTING, now projected | Added to `analyze_upgrade_path` response |
| `stepNotes` map property on `MigrationContext` | REMOVED | Replaced by `STEP_OUTCOME` relationship |

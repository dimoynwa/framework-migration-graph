# Data Model: Split Migration Harness

## 1. MigrationStep Schema Delta

The `MigrationStep` node schema is extended to support manually created steps.

- **New Property**: `origin`
  - **Type**: `string`
  - **Values**: `"graph"` (default for pipeline-extracted steps) | `"manual"` (for steps added via `clarify`)
  - **Description**: Indicates whether the step was derived from framework documentation or added manually by a user.

### Context-Scoping for Manual Steps

Manually created steps (`origin="manual"`) are scoped to their owning `MigrationContext` via a distinct ownership relationship, separate from the `STEP_OUTCOME` relationship that records execution status.

- **Relationship Type**: `OWNS_STEP`
  - **Direction**: `(MigrationContext)-[:OWNS_STEP]->(MigrationStep {origin: "manual"})`
  - **Description**: Exclusively links a manual step to the specific migration context it was created for. This ensures the step is only visible when querying that specific context.
  - **Cypher Update**: The `get_pending_steps` query must be updated to traverse this relationship using an `OPTIONAL MATCH` (e.g., `OPTIONAL MATCH (ctx)-[:OWNS_STEP]->(manualStep:MigrationStep {origin: "manual"})`) so that it retrieves both graph-derived steps (via the version range) and context-specific manual steps.

## 2. update_step_status Outcome Enum Delta

The `status` property on the `STEP_OUTCOME` relationship is extended to include `"excluded"`.

- **Extended Values**: `"completed"`, `"skipped"`, `"failed"`, `"deferred"`, `"excluded"`
- **Schema-Level Rule (`close_migration_context` gate interaction)**: A step with `status="excluded"` represents a deliberate pre-execution scope decision. Unlike `"skipped"`, an `"excluded"` step **DOES NOT** cap the `close_migration_context` final status at `"partial"`. 
  - **Completion Gate Logic**: `final_status = "complete"` if and only if NO `STEP_OUTCOME` relationship has `outcome IN ["skipped", "failed"]`. The `"excluded"` outcome is explicitly absent from this blocking list. A context where all steps are either `"completed"` or `"excluded"` will successfully reach a `"complete"` final status.

## 3. GapCheckFlag Shape and Persistence

Findings from the `gap-check` stage are persisted as a JSON-serialized list property directly on the `MigrationContext` node.

- **Property**: `gapCheckFlags`
  - **Type**: `string` (JSON-serialized list of objects)
  - **Justification**: Storing flags as a JSON property on the context node avoids introducing a new node label (`GapCheckFlag`) and relationship type, which would require updating all existing queries to use `OPTIONAL MATCH` to avoid breaking when the new nodes are absent. It keeps the graph schema simpler and aligns with how `queriedEntities` is currently cached.

### GapCheckFlag Object Shape

```json
{
  "type": "truncation | applicability_uncertain | stepless_rule | bridge_eligible | version_sanity | paysafe_unresolved",
  "reference": "ruleId or entity identifier (optional)",
  "message": "Human-readable explanation of the finding"
}
```

## 4. Execute's Ambiguous Context Error Shape

When `execute` is invoked without a `context_id` and multiple `in_progress` contexts exist, it MUST raise an error returning a list of candidates formatted for human disambiguation.

- **Error Payload Shape**: A list of objects containing the context ID and its primary metadata.
  ```json
  [
    {
      "context_id": "demo-service|3.3.0|3.4.0",
      "framework": "Spring Boot",
      "current_version": "3.3.0",
      "target_version": "3.4.0"
    },
    ...
  ]
  ```

## 5. add_manual_step Parameter Contract

The `add_manual_step` tool accepts the following parameters:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `context_id` | string | Yes | - | The ID of the active MigrationContext |
| `summary` | string | Yes | - | One-line summary of what this step does |
| `instruction` | string | Yes | - | Full instruction text shown to the developer |
| `file_pattern` | string | No | `null` (global) | Glob pattern to restrict where this step applies |
| `effort` | string | No | `"moderate"` | Must be one of the existing `MigrationStep` effort enum values: `"mechanical"`, `"moderate"`, `"architectural"` |
| `severity_hint` | string | No | `"medium"` | Must be one of the existing `BreakingScope` severity enum values: `"low"`, `"medium"`, `"high"`, `"critical"` |

## 6. MigrationContext Diagnostics Caching

To allow `gap-check` to perform its truncation check without re-running the expensive `analyze_upgrade_path` tool, the `MigrationContext` MUST cache the original `diagnostics` payload from the `plan` stage. This avoids a costly read-only re-query.

- **Property**: `diagnostics`
  - **Type**: `string` (JSON-serialized object)
  - **Description**: Caches the `diagnostics` object returned by `analyze_upgrade_path` when the context is created.

### Diagnostics Object Shape

```json
{
  "scanned_total": 42,
  "rules_included": 150,
  "rules_excluded_by_entity_filter": 10,
  "rules_via_safety_net": 5,
  "rules_capped_at": 50
}
```

### Relationship to gapCheckFlags

The `gap-check` stage reads this `diagnostics` property. If `rules_capped_at` is not `null` (which authoritatively indicates truncation occurred because `rules_included` exceeded the `top_n` limit), it generates a `GapCheckFlag` of type `truncation` and appends it to the `gapCheckFlags` property via the `write_gap_check_flags` tool. The `diagnostics` property itself remains immutable after creation.

## 7. Excluded + BRIDGED_BY Interaction Rule

**Rule**: The interaction between an excluded step and any `BRIDGED_BY` edge pointing to it as `requiredChange` is explicitly UNRESOLVED pending a plan-stage mechanism check against `update_step_status`'s existing auto-resolve logic. Do not assume it falls back to manual instructions or fails until this is derived from the actual auto-resolve code path.

## 8. write_gap_check_flags Parameter Contract

The `write_gap_check_flags` tool accepts the following parameters:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `context_id` | string | Yes | - | The ID of the active MigrationContext |
| `flags` | list of objects | Yes | - | List of GapCheckFlag objects to persist |
| `overwrite` | boolean | No | `false` | If true, replaces all existing flags on the context. If false, appends the new flags and deduplicates identical entries (same `type`, `reference`, and `message`) to ensure idempotency if `gap-check` is run multiple times. |
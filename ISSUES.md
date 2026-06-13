# Migration Oracle — Flagged Issues
 
Generated: 2026-06-12  
Scope: All project files (`framework_migration_main.md`, `framework_migration_version_map.md`, `framework_migration_scanning.md`, `framework_migration_plan_format.md`, `graph-schema.md`, `mcp-tools-skills-prompts.md`)
 
---
 
## ISSUE-001 · CRITICAL · `sortableVersion` formula mismatch
 
**Files:** `framework_migration_version_map.md`, `graph-schema.md`
 
**Description:**  
The two documents define conflicting formulas for computing `sortableVersion`.
 
| Source | Formula | Example: `3.2.1` |
|---|---|---|
| `framework_migration_version_map.md` | `MAJOR * 10000 + MINOR * 100 + PATCH` | `30201` |
| `graph-schema.md` (Data-Flow section) | `major × 1_000_000 + minor × 1_000 + patch` | `3_002_001` |
 
The graph schema's formula is confirmed correct by its own example (`"3.2.0" → 3_002_000`), and is the one used by all tool Cypher queries (`v.sortableVersion > $current_version_sortable`). The version map skill's formula is wrong.
 
**Impact:**  
Any agent or tooling that reads `sortableVersion` from the skill file and constructs range query parameters will produce incorrect results. Once minor versions exceed 9 (e.g. Spring Boot `3.10.x`), the skill's formula causes version inversion: `3.10.0 = 31000` sorts *above* `3.9.0 = 30900` under the skill's formula, but correctly *below* it under the schema's. Silent wrong results — no error is thrown.
 
**Fix:**  
Update `framework_migration_version_map.md` to use `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH` and recompute all pre-calculated `Sortable` column values in both version tables.
 
---
 
## ISSUE-002 · HIGH · `queriedEntities` skip guard has no defined write path
 
**Files:** `framework_migration_main.md`, `mcp-tools-skills-prompts.md`
 
**Description:**  
Loop II's skip guard checks `ctx.queriedEntities[entity_name]` before issuing any tool call. `create_migration_context` initialises this property as the string `'{}'`. No MCP tool in the document ever writes to `queriedEntities` after initialisation — there is no `SET ctx.queriedEntities = ...` in any Cypher block.
 
**Impact:**  
The skip guard can never fire. On every session resume, every entity is re-queried from scratch regardless of prior work. This makes the cache mechanism entirely inoperative, increases graph query volume, and makes Loop II non-resumable in practice.
 
**Fix:**  
Add a write step to the Loop II instructions: after each successful entity query, the agent (or a new `update_queried_entity` tool) writes `entity_name → result_summary` into `queriedEntities`. Document the key/value schema explicitly in both the skill and the MCP reference.
 
---
 
## ISSUE-003 · HIGH · `get_steps_for_scope_tier` ignores the `severity_threshold` parameter
 
**Files:** `mcp-tools-skills-prompts.md`
 
**Description:**  
The tool signature accepts `severity_threshold` (default `"medium"`) and the Returns table echoes it back. However the entire Cypher query contains no condition on `bs.severity` anywhere. The only scope-related filter is `WHERE bs.scope = $scope` on the `OPTIONAL MATCH`, which filters scope but not severity. All steps for the given scope are returned regardless of their severity level.
 
**Actual Cypher (relevant excerpt):**
```cypher
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
WHERE bs.scope = $scope
OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE e.name IN ctx.scannedEntities
RETURN DISTINCT e.name AS entity_name, ..., bs.scope AS scope, bs.severity AS severity
```
 
There is no `AND bs.severity >= $threshold` or equivalent.
 
**Impact:**  
Loop II's tier structure relies on this tool returning only `high`/`critical` for tier 1 and `medium`+above for tier 2. Since the filter is silently ignored, every tier returns all severity levels. Tier 1 processes low-severity steps it should defer, inflating the work queue and mis-ordering execution priority.
 
**Fix:**  
Add severity filtering to the Cypher. Map the threshold string to a numeric rank and add a `WHERE` condition:
```cypher
WITH ... CASE bs.severity
  WHEN 'critical' THEN 0 WHEN 'high' THEN 1
  WHEN 'medium'   THEN 2 ELSE 3
END AS sev_rank
WHERE sev_rank <= $severity_threshold_rank
```
 
---
 
## ISSUE-004 · HIGH · `update_step_status` never writes `STEP_OUTCOME` — the recommended relationship is never populated
 
**Files:** `mcp-tools-skills-prompts.md`, `graph-schema.md`
 
**Description:**  
The graph schema defines `STEP_OUTCOME` as the preferred way to record step results and explicitly labels `completedSteps`, `skippedSteps`, and `failedSteps` as "legacy — prefer `STEP_OUTCOME`." However, the `update_step_status` tool has exactly two Cypher blocks, both of which **only** write to the legacy arrays:
 
```cypher
-- Cypher 1: writes completedSteps / skippedSteps / failedSteps arrays only
SET ctx.completedSteps = CASE $outcome WHEN 'completed' ...
 
-- Cypher 2: auto-close
SET ctx.status = 'complete', ctx.completedAt = datetime()
```
 
There is no `MERGE (ctx)-[:STEP_OUTCOME {status, reason, updatedAt}]->(s:MigrationStep)` anywhere in the document. No other tool creates `STEP_OUTCOME` relationships either. The relationship is defined in the schema, used in example query #5, and described as preferred — but it is never written.
 
**Impact:**  
`STEP_OUTCOME` edges are permanently empty for all sessions. Any query built against `STEP_OUTCOME` (including the schema's own progress-summary example) returns no data. The schema's "prefer `STEP_OUTCOME`" guidance is impossible to follow. The legacy arrays are in practice the only source of step state.
 
**Fix:**  
Add a `MERGE (ctx)-[so:STEP_OUTCOME {status: $outcome, reason: $reason, updatedAt: datetime()}]->(s:MigrationStep)` block to `update_step_status`. Once all reads are migrated to `STEP_OUTCOME`, retire the legacy array writes.
 
---
 
## ISSUE-005 · HIGH · Rollback skill referenced but not defined
 
**Files:** `framework_migration_main.md`
 
**Description:**  
Loop III's build-failure path instructs: "Load rollback skill. Revert the applied changes." No rollback skill exists in the documented MCP skill resources (`skill://framework-migration/main`, `skill://framework-migration/scanning`, `skill://framework-migration/plan-format`, `skill://framework-migration/version-map`). The `install_migration_skill` tool also lists no rollback skill among what it installs.
 
**Impact:**  
When an automated OpenRewrite batch fails the build, the agent has no executable procedure for reverting. The instruction is unresolvable. A partial rewrite with no rollback leaves the codebase in a broken intermediate state with no documented recovery path.
 
**Fix:**  
Either create `skill://framework-migration/rollback` defining the revert procedure (e.g. `git stash`, `git checkout HEAD`, or OpenRewrite dry-run mode), or replace "Load rollback skill" with explicit inline rollback steps in the Loop III decision table.
 
---
 
## ISSUE-006 · HIGH · `analyze_upgrade_path` traverses `AUTOMATED_BY` from `MigrationRule` — schema mismatch
 
**Files:** `mcp-tools-skills-prompts.md`, `graph-schema.md`
 
**Description:**  
The `analyze_upgrade_path` Cypher contains:
 
```cypher
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
```
 
The graph schema defines `AUTOMATED_BY` only between `MigrationStep` and `OpenRewriteRecipe`:
 
```
(MigrationStep)-[:AUTOMATED_BY {auto, confidence, method, missingRequiredParams}]->(OpenRewriteRecipe)
```
 
There is no `(MigrationRule)-[:AUTOMATED_BY]->` relationship in the schema. The traversal from `rule` will always return null for `ab` and `rec`.
 
**Impact:**  
The `recipes` field in each returned rule object is always an empty list, regardless of whether linked steps have associated recipes. Callers who use `include_recipes=true` receive no recipe data. The auto-track identification in the loop harness that relies on `analyze_upgrade_path` returning recipe information is silently broken.
 
**Fix:**  
Fix the traversal to go through steps: `OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)`, joining recipe data to its parent step.
 
---
 
## ISSUE-007 · MEDIUM · `resolve_deprecation` return field name mismatch between Cypher and documented API
 
**Files:** `mcp-tools-skills-prompts.md`
 
**Description:**  
The Returns table documents the entity name field as `entity_name`. The actual Cypher returns it as `original_entity`:
 
```cypher
RETURN
  labels(e)[0] AS entity_type,
  e.name AS original_entity,   -- ← actual column name
  ...
```
 
The Returns table says:
 
| Field | Type | Description |
|---|---|---|
| `entity_name` | string | — |
 
**Impact:**  
Any caller reading the `entity_name` field from the response gets `null`. The actual value is in `original_entity`. This is a silent data loss bug for any consumer of this tool.
 
**Fix:**  
Align the Cypher alias to `e.name AS entity_name`, or update the Returns table to document `original_entity`. Pick one and apply consistently.
 
---
 
## ISSUE-008 · MEDIUM · `--force-refresh` flag is undefined
 
**Files:** `framework_migration_main.md`
 
**Description:**  
Loop II's skip guard states: "do not re-issue the tool call unless `--force-refresh` is set." There is no definition anywhere in the project of what `--force-refresh` is, how it is passed to the agent, where the agent checks for it, or what it resets.
 
**Impact:**  
The flag is referenced as a valid escape hatch for the skip guard but cannot actually be used. Developers who need to re-query a stale entity have no documented mechanism to do so.
 
**Fix:**  
Define `--force-refresh` concretely — as a prompt parameter, a `MigrationContext` boolean property, or a `CALL` to a dedicated cache-invalidation tool — or remove the reference and describe the correct mechanism.
 
---
 
## ISSUE-009 · MEDIUM · `search_openrewrite_recipes` filters on non-existent property `r.requiredParams`
 
**Files:** `mcp-tools-skills-prompts.md`, `graph-schema.md`
 
**Description:**  
The `require_no_params` filter in the hydrate Cypher reads:
 
```cypher
AND (NOT $require_no_params OR size(coalesce(r.requiredParams, [])) = 0)
```
 
The `OpenRewriteRecipe` node in the graph schema has no `requiredParams` property. Required parameters are stored as `RecipeParam` nodes linked via `HAS_PARAM` edges. Because `r.requiredParams` is always `null`, `coalesce(r.requiredParams, [])` always returns `[]`, and `size([]) = 0` is always true. The filter passes every recipe unconditionally.
 
Similarly, `only_composite` filters on `r.isComposite`, but the schema property is named `composite` (boolean), not `isComposite`. This filter also always evaluates against `null` and may behave unexpectedly.
 
**Impact:**  
`require_no_params=true` never excludes any recipe. `only_composite=true` may not filter correctly either. Both parameters are silently non-functional due to wrong property names.
 
**Fix:**  
For `require_no_params`, replace the property check with a subquery: `AND (NOT $require_no_params OR NOT EXISTS { (r)-[:HAS_PARAM]->(:RecipeParam {required: true}) })`. For `only_composite`, fix the property reference from `r.isComposite` to `r.composite`.
 
---
 
## ISSUE-010 · MEDIUM · `submit_migration_insight` duplicate detection is undocumented and its Cypher uses `CREATE` not `MERGE`
 
**Files:** `mcp-tools-skills-prompts.md`
 
**Description:**  
The tool description says it "runs near-duplicate detection before write (cosine similarity threshold)" and may return `status="duplicate"`. The actual Cypher shown uses a plain `CREATE (r:MigrationRule {...})` with no similarity check, no conditional branching, and no `RETURN ... AS duplicate_of` path. Any dedup logic must live entirely in application code that runs before the Cypher — but neither the threshold value nor the pre-Cypher logic is documented.
 
**Impact:**  
The cosine similarity threshold is invisible to callers. They cannot predict whether an insight will be written or silently rejected. The documented return shape includes `duplicate_of` (element ID of the existing duplicate), but the Cypher never returns this value — it only returns `elementId(r) AS insight_id`.
 
**Fix:**  
Document the similarity threshold in the tool reference. Add the pre-Cypher dedup query to the documentation (the BM25/vector check that fires before the `CREATE`). Ensure the documented Returns table reflects what the code actually returns in all three status paths (`ok`, `duplicate`, `error`).
 
---
 
## ISSUE-011 · MEDIUM · `--force-refresh` flag is undefined *(see ISSUE-008)*
 
*(Consolidated above — removed as a standalone entry.)*
 
---
 
## ISSUE-012 · MEDIUM · Version tables may be stale; no staleness indicator
 
**Files:** `framework_migration_version_map.md`
 
**Description:**  
The Angular version table marks Angular 17 and 18 as "Active." As of mid-2026 these versions are likely end-of-life (Angular ships a major every ~6 months; support window is ~18 months). Spring Boot 3.2.x is listed as "Maintenance" — its window may also have ended. The document carries no `Last Updated` date or upstream-source link.
 
**Impact:**  
Agents using this file will accept EOL versions as valid migration targets without a warning. A developer migrating to Angular 17 today lands on an unsupported version with no indication from the tool.
 
**Fix:**  
Add a `Last Updated` field and a notice instructing agents to verify against upstream release schedules (spring.io/projects/spring-boot, angular.io/guide/releases). Consider linking directly to the support schedule pages.
 
---
 
## ISSUE-013 · LOW · Loop IV has no stateless-fallback variant
 
**Files:** `framework_migration_main.md`
 
**Description:**  
The stateless fallback (Loop I) skips all tools requiring a `context_id`. Loop IV calls `close_migration_context`, reads `ctx.skippedSteps[]`, and assumes a live context throughout. There is no "Loop IV — STATELESS FALLBACK" section defining what Loop IV does when running in stateless mode.
 
**Impact:**  
When the agent runs in stateless mode, Loop IV is either skipped entirely (backlog never emitted, insights never submitted) or the agent attempts context-dependent calls that error out.
 
**Fix:**  
Add a Loop IV stateless-fallback section analogous to the Loop I one, explicitly listing which steps are skipped (e.g. `close_migration_context`) and which are performed in-memory only (e.g. print backlog to console, call `submit_migration_insight` without context).
 
---
 
## ISSUE-014 · LOW · Angular boundary note duplicated with inconsistent formatting
 
**Files:** `framework_migration_version_map.md`
 
**Description:**  
The Angular section contains a fragment `**Important version boundary:** 15 → 16` on its own line, immediately followed by a `Important version boundaries:` heading that restates it. The `16 → 17 New control flow syntax (@if, @for)` bullet also appears twice.
 
**Fix:**  
Remove the orphaned `**Important version boundary:** 15 → 16` line and the duplicate `16 → 17` bullet. Keep only the consolidated bulleted list under `Important version boundaries:`.
 
---
 
## ISSUE-015 · LOW · `close_migration_context` accepts `"abandoned"` status per the schema but not per the tool
 
**Files:** `mcp-tools-skills-prompts.md`, `graph-schema.md`
 
**Description:**  
The `MigrationContext.status` schema lists five valid values: `"in-progress"`, `"blocked"`, `"complete"`, `"partial"`, `"abandoned"`. The `close_migration_context` tool restricts `final_status` to `"complete"` or `"partial"` only — `"abandoned"` is not accepted. There is no other tool that sets `status = "abandoned"`.
 
**Impact:**  
A session that the developer wants to mark as abandoned (e.g. project cancelled, migration deferred) cannot be closed with the correct status through the MCP surface. The `abandoned` state is documented but unreachable.
 
**Fix:**  
Add `"abandoned"` to the accepted values for `close_migration_context`'s `final_status` parameter.
 
---
 
## Summary
 
| ID | Severity | Area | One-line description |
|---|---|---|---|
| ISSUE-001 | CRITICAL | version-map | `sortableVersion` formula in skill contradicts graph schema formula |
| ISSUE-002 | HIGH | agent loop | `queriedEntities` skip guard has no write path — cache never populated |
| ISSUE-003 | HIGH | MCP tool | `get_steps_for_scope_tier` accepts `severity_threshold` but never applies it |
| ISSUE-004 | HIGH | MCP tool | `update_step_status` never writes `STEP_OUTCOME` — preferred relationship always empty |
| ISSUE-005 | HIGH | agent loop | Rollback skill referenced in Loop III but does not exist |
| ISSUE-006 | HIGH | MCP tool | `analyze_upgrade_path` traverses `AUTOMATED_BY` from `MigrationRule` — wrong traversal, recipes always null |
| ISSUE-007 | MEDIUM | MCP tool | `resolve_deprecation` returns `original_entity` but documents it as `entity_name` |
| ISSUE-008 | MEDIUM | agent loop | `--force-refresh` flag referenced but never defined |
| ISSUE-009 | MEDIUM | MCP tool | `search_openrewrite_recipes` filters on non-existent properties `r.requiredParams` and `r.isComposite` |
| ISSUE-010 | MEDIUM | MCP tool | `submit_migration_insight` dedup threshold undocumented; Cypher never returns `duplicate_of` |
| ISSUE-011 | MEDIUM | version-map | Version status tables may be stale; no `Last Updated` date or upstream link |
| ISSUE-012 | MEDIUM | agent loop | Loop IV has no stateless-fallback variant |
| ISSUE-013 | LOW | version-map | Angular boundary note duplicated with inconsistent formatting |
| ISSUE-014 | LOW | MCP tool | `close_migration_context` does not accept `"abandoned"` status despite it being a valid schema value |
 
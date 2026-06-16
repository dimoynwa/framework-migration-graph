# Migration Oracle — Flagged Issues
 
Generated: 2026-06-12  
Scope: All project files (`framework_migration_main.md`, `framework_migration_version_map.md`, `framework_migration_scanning.md`, `framework_migration_plan_format.md`, `graph-schema.md`, `mcp-tools-skills-prompts.md`)
 
> **STATUS: RESOLVED** — All 14 distinct issues implemented under feature `012-oracle-contract-fixes` (2026-06-14). ISSUE-011 was consolidated into ISSUE-008. Per-issue resolution is annotated inline below and summarized in the table at the end. Verification via the evaluation harness (lanes A–C) is the next step and is tracked separately.
 
---
 
## ISSUE-001 · CRITICAL · `sortableVersion` formula mismatch
 
> ✅ **RESOLVED** — FR-001/FR-002 · T006–T008 — formula corrected to `MAJOR*1_000_000 + MINOR*1_000 + PATCH`; all Sortable cells recomputed; the (correct) graph-schema copy left untouched.
 
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
 
> ✅ **RESOLVED** — FR-014 · T023–T025 — new `update_queried_entity` tool writes the cache; Loop II skip guard documented in the main skill.
 
**Files:** `framework_migration_main.md`, `mcp-tools-skills-prompts.md`
 
**Description:**  
Loop II's skip guard checks `ctx.queriedEntities[entity_name]` before issuing any tool call. `create_migration_context` initialises this property as the string `'{}'`. No MCP tool in the document ever writes to `queriedEntities` after initialisation — there is no `SET ctx.queriedEntities = ...` in any Cypher block.
 
**Impact:**  
The skip guard can never fire. On every session resume, every entity is re-queried from scratch regardless of prior work. This makes the cache mechanism entirely inoperative, increases graph query volume, and makes Loop II non-resumable in practice.
 
**Fix:**  
Add a write step to the Loop II instructions: after each successful entity query, the agent (or a new `update_queried_entity` tool) writes `entity_name → result_summary` into `queriedEntities`. Document the key/value schema explicitly in both the skill and the MCP reference.
 
---
 
## ISSUE-003 · HIGH · `get_steps_for_scope_tier` ignores the `severity_threshold` parameter
 
> ✅ **RESOLVED** — FR-008 · T015–T016 — invalid thresholds rejected; severity filter applied Python-side via `severity_meets_threshold` (rank low=1…critical=4, at-or-above).
 
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
 
> ✅ **RESOLVED** — FR-005/FR-006 · T010,T012,T013 — `STEP_OUTCOME` MERGE added (idempotent per (context, step)); legacy arrays retained.
 
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
 
> ✅ **RESOLVED** — FR-016 · T030–T031 — `skill://framework-migration/rollback` created and referenced from Loop III's build-failure path.
 
**Files:** `framework_migration_main.md`
 
**Description:**  
Loop III's build-failure path instructs: "Load rollback skill. Revert the applied changes." No rollback skill exists in the documented MCP skill resources (`skill://framework-migration/main`, `skill://framework-migration/scanning`, `skill://framework-migration/plan-format`, `skill://framework-migration/version-map`). The `install_migration_skill` tool also lists no rollback skill among what it installs.
 
**Impact:**  
When an automated OpenRewrite batch fails the build, the agent has no executable procedure for reverting. The instruction is unresolvable. A partial rewrite with no rollback leaves the codebase in a broken intermediate state with no documented recovery path.
 
**Fix:**  
Either create `skill://framework-migration/rollback` defining the revert procedure (e.g. `git stash`, `git checkout HEAD`, or OpenRewrite dry-run mode), or replace "Load rollback skill" with explicit inline rollback steps in the Loop III decision table.
 
---
 
## ISSUE-006 · HIGH · `analyze_upgrade_path` traverses `AUTOMATED_BY` from `MigrationRule` — schema mismatch
 
> ✅ **RESOLVED** — FR-009 · T017–T018 — `AUTOMATED_BY` traversed from `MigrationStep`; `step_id` added to each recipe entry.
 
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
 
> ✅ **RESOLVED** — FR-010 · T019,T022 — Cypher alias, Python caller, and Returns table all aligned to `entity_name`.
 
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
 
> ✅ **RESOLVED** — FR-015 · T025 — `--force-refresh` defined as an agent-loop concept in the main skill (not a tool parameter). Absorbs consolidated ISSUE-011.
 
**Files:** `framework_migration_main.md`
 
**Description:**  
Loop II's skip guard states: "do not re-issue the tool call unless `--force-refresh` is set." There is no definition anywhere in the project of what `--force-refresh` is, how it is passed to the agent, where the agent checks for it, or what it resets.
 
**Impact:**  
The flag is referenced as a valid escape hatch for the skip guard but cannot actually be used. Developers who need to re-query a stale entity have no documented mechanism to do so.
 
**Fix:**  
Define `--force-refresh` concretely — as a prompt parameter, a `MigrationContext` boolean property, or a `CALL` to a dedicated cache-invalidation tool — or remove the reference and describe the correct mechanism.
 
---
 
## ISSUE-009 · MEDIUM · `search_openrewrite_recipes` filters on non-existent property `r.requiredParams`
 
> ✅ **RESOLVED** — FR-011/FR-012 · T020,T022 — filters use `r.composite` and `NOT EXISTS { (r)-[:HAS_PARAM]->(:RecipeParam {required:true}) }`.
 
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
 
> ✅ **RESOLVED** — FR-013 · T021,T022 — three-pass dedup pipeline + 0.92 cosine threshold documented; `duplicate_of` returned; ok/duplicate/error shapes consistent.
 
**Files:** `mcp-tools-skills-prompts.md`
 
**Description:**  
The tool description says it "runs near-duplicate detection before write (cosine similarity threshold)" and may return `status="duplicate"`. The actual Cypher shown uses a plain `CREATE (r:MigrationRule {...})` with no similarity check, no conditional branching, and no `RETURN ... AS duplicate_of` path. Any dedup logic must live entirely in application code that runs before the Cypher — but neither the threshold value nor the pre-Cypher logic is documented.
 
**Impact:**  
The cosine similarity threshold is invisible to callers. They cannot predict whether an insight will be written or silently rejected. The documented return shape includes `duplicate_of` (element ID of the existing duplicate), but the Cypher never returns this value — it only returns `elementId(r) AS insight_id`.
 
**Fix:**  
Document the similarity threshold in the tool reference. Add the pre-Cypher dedup query to the documentation (the BM25/vector check that fires before the `CREATE`). Ensure the documented Returns table reflects what the code actually returns in all three status paths (`ok`, `duplicate`, `error`).
 
---
 
## ISSUE-011 · MEDIUM · `--force-refresh` flag is undefined *(see ISSUE-008)*
 
> ⤳ CONSOLIDATED into ISSUE-008 (`--force-refresh`); resolved with it.
 
*(Consolidated above — removed as a standalone entry.)*
 
---
 
## ISSUE-012 · MEDIUM · Version tables may be stale; no staleness indicator
 
> ✅ **RESOLVED** — FR-003 · T009 — `Last Updated` date and upstream schedule links (spring.io, angular.io) added.
 
**Files:** `framework_migration_version_map.md`
 
**Description:**  
The Angular version table marks Angular 17 and 18 as "Active." As of mid-2026 these versions are likely end-of-life (Angular ships a major every ~6 months; support window is ~18 months). Spring Boot 3.2.x is listed as "Maintenance" — its window may also have ended. The document carries no `Last Updated` date or upstream-source link.
 
**Impact:**  
Agents using this file will accept EOL versions as valid migration targets without a warning. A developer migrating to Angular 17 today lands on an unsupported version with no indication from the tool.
 
**Fix:**  
Add a `Last Updated` field and a notice instructing agents to verify against upstream release schedules (spring.io/projects/spring-boot, angular.io/guide/releases). Consider linking directly to the support schedule pages.
 
---
 
## ISSUE-013 · LOW · Loop IV has no stateless-fallback variant
 
> ✅ **RESOLVED** — FR-017 · T032 — `Loop IV — STATELESS FALLBACK` section added to the main skill.
 
**Files:** `framework_migration_main.md`
 
**Description:**  
The stateless fallback (Loop I) skips all tools requiring a `context_id`. Loop IV calls `close_migration_context`, reads `ctx.skippedSteps[]`, and assumes a live context throughout. There is no "Loop IV — STATELESS FALLBACK" section defining what Loop IV does when running in stateless mode.
 
**Impact:**  
When the agent runs in stateless mode, Loop IV is either skipped entirely (backlog never emitted, insights never submitted) or the agent attempts context-dependent calls that error out.
 
**Fix:**  
Add a Loop IV stateless-fallback section analogous to the Loop I one, explicitly listing which steps are skipped (e.g. `close_migration_context`) and which are performed in-memory only (e.g. print backlog to console, call `submit_migration_insight` without context).
 
---
 
## ISSUE-014 · LOW · Angular boundary note duplicated with inconsistent formatting
 
> ✅ **RESOLVED** — FR-004 · T009 — duplicate Angular boundary line and repeated bullet removed.
 
**Files:** `framework_migration_version_map.md`
 
**Description:**  
The Angular section contains a fragment `**Important version boundary:** 15 → 16` on its own line, immediately followed by a `Important version boundaries:` heading that restates it. The `16 → 17 New control flow syntax (@if, @for)` bullet also appears twice.
 
**Fix:**  
Remove the orphaned `**Important version boundary:** 15 → 16` line and the duplicate `16 → 17` bullet. Keep only the consolidated bulleted list under `Important version boundaries:`.
 
---
 
## ISSUE-015 · LOW · `close_migration_context` accepts `"abandoned"` status per the schema but not per the tool
 
> ✅ **RESOLVED** — FR-007 · T033–T034 — `close_migration_context` accepts `"abandoned"` with Python-side validation.
 
**Files:** `mcp-tools-skills-prompts.md`, `graph-schema.md`
 
**Description:**  
The `MigrationContext.status` schema lists five valid values: `"in-progress"`, `"blocked"`, `"complete"`, `"partial"`, `"abandoned"`. The `close_migration_context` tool restricts `final_status` to `"complete"` or `"partial"` only — `"abandoned"` is not accepted. There is no other tool that sets `status = "abandoned"`.
 
**Impact:**  
A session that the developer wants to mark as abandoned (e.g. project cancelled, migration deferred) cannot be closed with the correct status through the MCP surface. The `abandoned` state is documented but unreachable.
 
**Fix:**  
Add `"abandoned"` to the accepted values for `close_migration_context`'s `final_status` parameter.
 
---

# Live Probe Report — 2026-06-15

Server: `http://localhost:8080/sse`
Project scanned: `paysafe-wallet-switch` (Spring Boot 3.5.12 detected, normalised to `3.5.0 → 4.0.0`)
Entities extracted: 43 main-scope (135 raw Java imports after allow-list filtering) · 146 test-scope (deferred)
Tools registered: 24

## Live Probe Summary

| # | Tool | Category | Severity | One-line description |
|---|---|---|---|---|
| LP-001 | `search_migration_knowledge` | query-logic | High | All hits return empty `text` — content field missing from result projection |
| LP-002 | `analyze_upgrade_path` | query-logic | High | Rules returned without entity name; `rule_id` is Neo4j element ID not stable key |
| LP-003 | `search_openrewrite_recipes` | missing-data | Medium | Zero `OpenRewriteRecipe` nodes in graph — recipe data never loaded |
| LP-004 | `get_pending_steps` vs `build_recipe_plan` | query-logic | Medium | `build_recipe_plan` yields 43 manual steps; `get_pending_steps` returns 0 on same context |
| LP-005 | `create_migration_context` | query-logic | Low | Response omits `entityCount` and `droppedCount` — skill relies on these to report filtering |

---

## LP-001 — `search_migration_knowledge` hits have empty text content

**Severity:** High
**Category:** query-logic
**Tool(s):** `search_migration_knowledge`

**Error / symptom observed:**
5 probe queries (4 entity-targeted + 1 generic "Spring Boot 4.0 breaking changes") all returned
3 hits with varied scores — confirming hybrid RRF pipeline ran and embeddings are loaded.
However every hit had `text=""`:

```
score=0.0313 text=
score=0.0278 text=
score=0.0306 text=
```

Consistent across all 15 hits (5 queries × 3 results each).

**Root cause:**
The Cypher projection retrieves node IDs and computes scores correctly (score variance confirms
the vector index is active), but the `RETURN` clause projects a field name that does not match
the stored property on the matched node — likely returning `n.text` when the property is
stored as `n.statement` or `n.description`.

**Likely fix:**
In `migration_oracle/mcp/graph/queries/search.py`, confirm the actual property key:
```cypher
MATCH (n) WHERE n.statement IS NOT NULL RETURN n.statement LIMIT 1
```
Then align the projection in the `RETURN` clause.

**Impact:**
The agent receives search results with no content. The entire Loop II knowledge-search path
(tier 3 fallback, entities with no graph hit) is silently broken. The agent proceeds as if it
found guidance, but every result is blank.

---

## LP-002 — `analyze_upgrade_path` rules missing entity field; `rule_id` is a Neo4j element ID

**Severity:** High
**Category:** query-logic
**Tool(s):** `analyze_upgrade_path`

**Error / symptom observed:**
20 rules returned for `Spring Boot 3.5.0 → 4.0.0` — correct count, no error. But `entity`
was null on all 20 rules, and `rule_id` values are internal element IDs:

```
rule_id: 4:c474cace-f303-4271-8946-b26cf9dee8d9:1794  severity=critical  entity=null
rule_id: 4:c474cace-f303-4271-8946-b26cf9dee8d9:1789  severity=critical  entity=null
```

**Root cause:**
1. **Entity field absent:** The `RETURN` clause does not project the entity name (the
   class/property/dependency that triggered the rule). The skill's Loop II skip-guard and
   executor-selection table both require this.
2. **`rule_id` is element ID not stable key:** Element IDs change if the graph is rebuilt.

**Likely fix:**
In the `analyze_upgrade_path` Cypher, add to `RETURN`:
- `entity.name AS entity_name`
- `mr.rule_id AS rule_id` (stable stored property, not `elementId(mr)`)

**Impact:**
The skip-guard cannot function (no entity name to key on). The executor-selection entity-anchor
check cannot be evaluated. All 20 rules are anonymous — the agent cannot map rules back to
scanned project entities.

---

## LP-003 — OpenRewrite recipe data not loaded

**Severity:** Medium
**Category:** missing-data
**Tool(s):** `search_openrewrite_recipes`, `build_recipe_plan`

**Error / symptom observed:**
`MATCH (r:OpenRewriteRecipe) RETURN count(r)` via `execute_custom_cypher` → `0`.
`build_recipe_plan` returned `auto_track=0, manual=43` — all 43 steps fall to manual.

**Likely fix:**
Run the OpenRewrite recipe ingestion pipeline against the running Neo4j instance and rebuild
the full-text index on `OpenRewriteRecipe` nodes.

**Impact:**
The entire auto-track path in Loop III is unavailable. `build_recipe_plan` always returns
`auto_track=0` until recipe data is loaded.

---

## LP-004 — `get_pending_steps` returns 0 while `build_recipe_plan` shows 43 manual steps

**Severity:** Medium
**Category:** query-logic
**Tool(s):** `get_pending_steps`, `build_recipe_plan`

**Error / symptom observed:**
```
OK build_recipe_plan: auto=0, manual=43, fallback=False
OK get_pending_steps: 0 pending steps
```
Both calls used the same `context_id`. `create_migration_context` returned `created=False`
(MERGE matched an existing context).

**Root cause:**
`build_recipe_plan` queries the graph for applicable rules but does not write `MigrationStep`
nodes into the context. `get_pending_steps` reads `MigrationStep` nodes linked via `HAS_STEP`.
Since no tool in the current flow materialises those nodes, the Loop III work queue is always
empty after context creation. The `created=False` (reused context) may additionally mean prior
steps are in a terminal state — the skill has no mechanism to distinguish the two cases.

**Likely fix:**
Either `build_recipe_plan` should write `MigrationStep` nodes when a `context_id` is provided,
or a `populate_context_steps` tool should be added. `create_migration_context` should also
return a clear `reused=true` flag (distinct from `created=false`).

**Impact:**
Loop III is a no-op. The agent receives an empty pending queue and skips execution entirely —
the migration harness stalls silently after Loop II.

---

## LP-005 — `create_migration_context` response missing `entityCount` and `droppedCount`

**Severity:** Low
**Category:** query-logic
**Tool(s):** `create_migration_context`

**Error / symptom observed:**
```
context_id=4:c474cace-...:1227, created=False, entityCount=None, droppedCount=None
```

**Likely fix:**
Always return `entityCount` and `droppedCount` from both the create and MERGE paths.

**Impact:**
If the entire scanned entity list was below the allow-list threshold, the agent proceeds with
zero graph coverage and no warning surfaced to the developer.

---

## Live Probe — Clean Results

- **Version normalisation:** Patch versions `3.5.12 → 4.0.6` returned 5 rules — server normalises to `major.minor.0`. ✅
- **Hybrid search pipeline:** Score variance across 5 queries confirms embedding model loaded and RRF scoring active. ✅
- **`resolve_deprecation` / `entity_evolution`:** `EnvironmentPostProcessor` found (`deprecated_in=3.0.0`); chain=1. ✅
- **`submit_migration_insight` dedup:** Resubmit returned `status=duplicate` — fingerprint logic correct. ✅
- **24 tools registered** — matches expected surface. ✅
- **`close_migration_context`** accepted `final_status="partial"` correctly. ✅

---

## Static Analysis Summary (pre-existing, all resolved)
 
| ID | Severity | Area | One-line description | Status | Fixed by |
|---|---|---|---|---|---|
| ISSUE-001 | CRITICAL | version-map | `sortableVersion` formula in skill contradicts graph schema formula | ✅ Resolved | FR-001/2 · T006–T008 |
| ISSUE-002 | HIGH | agent loop | `queriedEntities` skip guard has no write path — cache never populated | ✅ Resolved | FR-014 · T023–T025 |
| ISSUE-003 | HIGH | MCP tool | `get_steps_for_scope_tier` accepts `severity_threshold` but never applies it | ✅ Resolved | FR-008 · T015–T016 |
| ISSUE-004 | HIGH | MCP tool | `update_step_status` never writes `STEP_OUTCOME` — preferred relationship always empty | ✅ Resolved | FR-005/6 · T010,T012,T013 |
| ISSUE-005 | HIGH | agent loop | Rollback skill referenced in Loop III but does not exist | ✅ Resolved | FR-016 · T030–T031 |
| ISSUE-006 | HIGH | MCP tool | `analyze_upgrade_path` traverses `AUTOMATED_BY` from `MigrationRule` — wrong traversal, recipes always null | ✅ Resolved | FR-009 · T017–T018 |
| ISSUE-007 | MEDIUM | MCP tool | `resolve_deprecation` returns `original_entity` but documents it as `entity_name` | ✅ Resolved | FR-010 · T019,T022 |
| ISSUE-008 | MEDIUM | agent loop | `--force-refresh` flag referenced but never defined | ✅ Resolved | FR-015 · T025 |
| ISSUE-009 | MEDIUM | MCP tool | `search_openrewrite_recipes` filters on non-existent properties `r.requiredParams` and `r.isComposite` | ✅ Resolved | FR-011/12 · T020,T022 |
| ISSUE-010 | MEDIUM | MCP tool | `submit_migration_insight` dedup threshold undocumented; Cypher never returns `duplicate_of` | ✅ Resolved | FR-013 · T021,T022 |
| ISSUE-011 | MEDIUM | version-map | Version status tables may be stale; no `Last Updated` date or upstream link | ✅ Resolved | FR-003 · T009 |
| ISSUE-012 | MEDIUM | agent loop | Loop IV has no stateless-fallback variant | ✅ Resolved | FR-017 · T032 |
| ISSUE-013 | LOW | version-map | Angular boundary note duplicated with inconsistent formatting | ✅ Resolved | FR-004 · T009 |
| ISSUE-014 | LOW | MCP tool | `close_migration_context` does not accept `"abandoned"` status despite it being a valid schema value | ✅ Resolved | FR-007 · T033–T034 |
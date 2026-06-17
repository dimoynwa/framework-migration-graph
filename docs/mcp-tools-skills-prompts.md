# MCP Tools, Skills & Prompts — Paysafe Migration Oracle

Full reference for every MCP tool, skill resource, and prompt exposed by the `PaysafeMigrationOracle` MCP server (`migration_oracle/mcp/`). Each tool entry includes its description, parameters, return shape, and representative Cypher where applicable.

For the authoritative graph model, see [graph-schema.md](./graph-schema.md). For the end-to-end pipeline (changelog extraction → graph population), see [migration-oracle-redesign.md](./migration-oracle-redesign.md).

---

## System Architecture

The Migration Oracle is a three-layer system:

| Layer | Role | Key artifacts |
|---|---|---|
| **Knowledge graph** | Stores framework release knowledge — rules, steps, affected entities, OpenRewrite recipes, community insights | Neo4j/Memgraph; schema in [graph-schema.md](./graph-schema.md) |
| **MCP server** | Exposes graph queries, context management, search, and Paysafe dependency resolution to AI agents | 23 tools, 5 skill resources, 3 prompts |
| **Agent harness** | Procedural skill that drives a four-loop migration workflow using the MCP tools | `skill://framework-migration/*` resources |

### Four-loop harness (Increment 3)

The harness replaces the earlier five-phase “scan → query → plan document” flow with four **re-entrant runtime loops** backed by `MigrationContext` graph state:

```
Loop I — Context     scan codebase → create/resume MigrationContext → version-map preconditions
Loop II — Query      scope-gated graph queries (api-surface → runtime → config/build → test)
Loop III — Execution apply steps (OpenRewrite / agent-codemod / human-review) → update_step_status
Loop IV — Feedback   submit_migration_insight → backlog → close_migration_context
```

Supporting skill files split concerns:

| Resource URI | File | Used in |
|---|---|---|
| `skill://framework-migration/main` | `framework_migration_main.md` | All loops — orchestration, decision tables, stateless fallback |
| `skill://framework-migration/scanning` | `framework_migration_scanning.md` | Loop I — entity extraction in graph-compatible string forms |
| `skill://framework-migration/version-map` | `framework_migration_version_map.md` | Loop I — version tables, Java/Node gates, Spring Cloud co-migration |
| `skill://framework-migration/plan-format` | `framework_migration_plan_format.md` | Loop III (human-readable mode) — `MIGRATION_PLAN.md` schema |
| `skill://framework-migration/rollback` | `framework_migration_rollback.md` | Loop III — revert procedure after build/test failure |

**Stateless fallback:** If `create_migration_context` fails after retry, the harness continues with `analyze_upgrade_path` + `build_recipe_plan` using in-memory step tracking only (no `context_id`-requiring tools).

**Entity matching:** Scanned entities are normalised into five typed buckets (`scannedClasses`, `scannedClassSimple`, `scannedDepsGa`, `scannedDepArtifacts`, `scannedProps`) for exact-string matching against graph nodes. See `normalize_entities()` in `migration_oracle/mcp/tools/upgrade.py` and `migration_oracle/mcp/matching.py`.

---

## Table of Contents

1. [Tool Groups](#tool-groups)
   - [Upgrade Path](#upgrade-path-tools)
   - [Migration Context](#migration-context-tools)
   - [Search](#search-tools)
   - [Community Insights](#community-insight-tools)
   - [Deprecation & Entity Evolution](#deprecation--entity-evolution-tools)
   - [Artifacts](#artifact-tools)
   - [Schema & Custom Cypher](#schema--custom-cypher-tools)
   - [Paysafe Dependency Resolution](#paysafe-dependency-tools)
   - [Skill Installation](#skill-installation)
2. [Prompts](#prompts)
3. [Skill Resources](#skill-resources)
4. [Tool Index](#tool-index)

---

## Tool Groups

---

### Upgrade Path Tools

---

#### `check_version_availability`

Check whether a framework version resolves to a graph node and (for Maven-backed frameworks) whether it exists on Maven Central.

Uses `resolve_version()` with configurable direction — the same resolution logic as `create_migration_context` and `submit_migration_insight`.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `framework` | string | yes | — | Framework name (e.g. `"Spring Boot"`) |
| `version` | string | yes | — | Version string to check (e.g. `"3.2.0"`) |
| `direction` | string | no | `"floor"` | `"floor"` — highest graph node ≤ requested; `"ceil"` — lowest graph node ≥ requested |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `exists_in_graph` | boolean | True when resolution succeeds |
| `nodeId` | string \| null | Element ID of resolved `Version` node |
| `resolved_version` | string \| null | Actual graph version after floor/ceil resolution |
| `rounded` | boolean | True when resolved version differs from requested |
| `ahead_of_catalogue` | boolean | True when target exceeds highest known graph version |
| `ga_available` | boolean | True if the resolved version is on Maven Central |
| `latest_patch` | string \| null | Latest known patch on Maven Central for the artifact |
| `hint` | string | Human-readable guidance |
| `candidates_considered` | list[string] | Near-miss versions when not found |

---

#### `analyze_upgrade_path`

Return all migration rules and lifecycle alerts for a framework version range. Optionally filters by user-scanned entities (per-kind exact matching across 5 buckets), scope, severity, and entity classification. Rules with no matching entities are classified as `excluded` unless they are high/critical (safety net: `uncertain`) or have no entity nodes (`informational`).

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `framework` | string | yes | — | Framework name |
| `current_version` | string | yes | — | Migration source version |
| `target_version` | string | yes | — | Migration target version |
| `user_entities` | list[string] | no | `[]` | Codebase entity strings (FQCNs, simple names, `group:artifact` coords, artifact IDs, property keys). Internally split into 5 typed buckets via `normalize_entities()` before querying. |
| `format` | string | no | `"json"` | `"json"` or `"markdown"` |
| `classification` | list[string] | no | `[]` | Filter by `entityClassification`: `"actionable"`, `"incomplete"`, `"informational"` |
| `include_recipes` | boolean | no | `false` | Include linked OpenRewrite recipes per step |
| `include_lifecycle` | boolean | no | `true` | Include `LifecycleAlert` nodes |
| `top_n` | integer | no | `50` | Maximum rules to return |
| `verbose` | boolean | no | `false` | Verbose output with full reason/solution fields |
| `scope_filter` | list[string] | no | `[]` | Filter by scope: `"api-surface"`, `"runtime"`, `"config"`, `"build"`, `"test"` |
| `min_severity` | string | no | `null` | Minimum severity: `"low"`, `"medium"`, `"high"`, `"critical"` |

> **Applicability semantics:** When `user_entities` is non-empty, rules are classified as `matched`, `uncertain` (high/critical safety net), `excluded`, `informational`, or `universal`. The `matched_entities` field in each rule reflects scanned strings that hit the rule, including package-prefix bridges implemented in `migration_oracle/mcp/matching.py`.

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `framework` | string | Framework name |
| `from_version` | string | Starting version |
| `to_version` | string | Target version |
| `rules` | list | Migration rules; each has `statement`, `rule_type`, `steps`, `scopes`, `recipes`, `matched_entities`, `applicability` |
| `lifecycle_alerts` | list | Phase-level alerts; each has `message`, `category`, `phase` |
| `format` | string | Output format used |
| `diagnostics` | object \| null | Present when `user_entities` is non-empty: `scanned_total`, `rules_included`, `rules_excluded_by_entity_filter`, `rules_via_safety_net`, `rules_capped_at` |

**Cypher**

```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable
MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH v, rule,
     min(CASE bs.severity
           WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium'   THEN 2 WHEN 'low'  THEN 3 ELSE 4
         END) AS sev_rank,
     collect(DISTINCT {scope: bs.scope, severity: bs.severity}) AS scopes

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH v, rule, sev_rank, scopes, e,
     CASE
       WHEN e IS NULL THEN false
       WHEN e:Class THEN
            e.name IN $scanned_classes
         OR last(split(e.name, '.')) IN $scanned_class_simple
       WHEN e:ApplicationProperty THEN
            e.name IN $scanned_props
       WHEN e:Dependency THEN
            (size(split(e.name, ':')) >= 2
               AND (split(e.name, ':')[0] + ':' + split(e.name, ':')[1]) IN $scanned_deps_ga)
         OR last(split(e.name, ':')) IN $scanned_dep_artifacts
       ELSE false
     END AS entity_match

WITH v, rule, sev_rank, scopes,
     [x IN collect(DISTINCT CASE WHEN e IS NOT NULL THEN e.name ELSE null END) WHERE x IS NOT NULL] AS affected_entities,
     count(DISTINCT e)                                            AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END)               AS match_count

WITH v, rule, sev_rank, scopes, affected_entities, affected_count, match_count,
     CASE
       WHEN affected_count = 0     THEN 'informational'
       WHEN NOT $has_entity_filter THEN 'universal'
       WHEN match_count > 0        THEN 'matched'
       WHEN sev_rank <= 1          THEN 'uncertain'
       ELSE                             'excluded'
     END AS applicability

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

WITH v, rule, scopes, affected_entities, applicability, match_count, sev_rank, affected_count,
     collect(DISTINCT CASE WHEN s IS NULL THEN null ELSE {
       step_id: elementId(s),
       step_type: s.stepType,
       summary: s.summary,
       instruction: s.instruction,
       effort: s.effort,
       automatable: s.automatable,
       verification_hint: s.verificationHint,
       cli_operation: s.cliOperation
     } END) AS steps_raw,
     collect(DISTINCT CASE WHEN rec IS NULL THEN null ELSE {
       recipe_id: rec.recipeId,
       display_name: rec.displayName,
       auto: ab.auto,
       missing_required_params: coalesce(ab.missingRequiredParams, [])
     } END) AS recipes_raw

WITH v, collect(DISTINCT {
    rule_id:              elementId(rule),
    rule_type:            labels(rule)[0],
    title:                rule.title,
    statement:            rule.statement,
    action_step:          rule.actionStep,
    source_url:           rule.sourceUrl,
    reason:               coalesce(rule.statement, rule.reason),
    solution:             rule.solution,
    change_type:          rule.changeType,
    reason_type:          rule.reasonType,
    entity_classification: rule.entityClassification,
    affected_entities:    affected_entities,
    applicability:        applicability,
    match_count:          match_count,
    universally_applicable: (affected_count = 0),
    severity:             CASE sev_rank WHEN 0 THEN 'critical' WHEN 1 THEN 'high'
                                        WHEN 2 THEN 'medium'  WHEN 3 THEN 'low' ELSE null END,
    steps:    [x IN steps_raw   WHERE x IS NOT NULL],
    scopes:   [x IN scopes      WHERE x.scope IS NOT NULL],
    recipes:  [x IN recipes_raw WHERE x IS NOT NULL AND x.recipe_id IS NOT NULL]
}) AS raw_rules

OPTIONAL MATCH (v)-[:HAS_LIFECYCLE_ALERT]->(la:LifecycleAlert)

WITH v, raw_rules,
     collect(DISTINCT {message: la.message, category: la.category, phase: la.phase}) AS raw_alerts

RETURN
    v.version          AS release_version,
    v.sortableVersion  AS release_sortable,
    [x IN raw_rules WHERE x.statement IS NOT NULL] AS rules,
    [x IN raw_alerts  WHERE x.message  IS NOT NULL] AS raw_phase_alerts
ORDER BY v.sortableVersion ASC
```

---

#### `build_recipe_plan`

Produce a two-track migration plan: **auto** (scriptable via OpenRewrite) and **manual** (human review required). Falls back to rule-level cards when no `MigrationStep` nodes exist in the graph.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `current_version` | string | yes | — | Migration source version |
| `target_version` | string | yes | — | Migration target version |
| `framework` | string | no | `"Spring Boot"` | Framework name |
| `user_entities` | list[string] | no | `[]` | Entities to filter applicable steps |
| `auto_only` | boolean | no | `false` | Return only the auto track |
| `classification` | list[string] | no | `[]` | Filter by `entityClassification` |
| `scope_filter` | list[string] | no | `[]` | Filter by scope |
| `min_severity` | string | no | `null` | Minimum severity threshold |
| `context_id` | string | no | `null` | When set, resolves version bounds from the context's `UPGRADES_FROM`/`UPGRADES_TO` edges instead of caller-supplied versions |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `auto_track` | list | Steps with `automatable=true`, effort `"mechanical"`, and a linked recipe |
| `manual_track` | list | All other steps; each has `applicability` and `matched_entities` |
| `fallback_to_rule_cards` | boolean | True when no `MigrationStep` nodes exist |
| `diagnostics` | object \| null | Entity-filter diagnostics plus `recipes_loaded` and `recipe_count` |

**Cypher**

```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable
MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH v, rule,
     min(CASE bs.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END) AS sev_rank,
     head(collect(DISTINCT bs.scope))    AS scope,
     head(collect(DISTINCT bs.severity)) AS severity

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH v, rule, sev_rank, scope, severity, e,
     CASE
       WHEN e IS NULL THEN false
       WHEN e:Class THEN
            e.name IN $scanned_classes
         OR last(split(e.name, '.')) IN $scanned_class_simple
       WHEN e:ApplicationProperty THEN e.name IN $scanned_props
       WHEN e:Dependency THEN
            (size(split(e.name, ':')) >= 2
               AND (split(e.name, ':')[0]+':'+split(e.name, ':')[1]) IN $scanned_deps_ga)
         OR last(split(e.name, ':')) IN $scanned_dep_artifacts
       ELSE false
     END AS entity_match

WITH v, rule, sev_rank, scope, severity,
     [x IN collect(DISTINCT CASE WHEN e IS NOT NULL THEN e.name ELSE null END) WHERE x IS NOT NULL] AS affected_entities,
     count(DISTINCT e) AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END) AS match_count

WITH v, rule, sev_rank, scope, severity, affected_entities, affected_count, match_count,
     CASE WHEN affected_count = 0     THEN 'informational'
          WHEN NOT $has_entity_filter THEN 'universal'
          WHEN match_count > 0        THEN 'matched'
          WHEN sev_rank <= 1          THEN 'uncertain'
          ELSE                             'excluded' END AS applicability
WHERE applicability <> 'excluded'

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

RETURN
    elementId(rule)                         AS rule_id,
    elementId(s)                            AS step_id,
    rule.statement                          AS statement,
    rule.actionStep                         AS action_step,
    s.summary                               AS summary,
    s.instruction                           AS instruction,
    s.effort                                AS effort,
    s.automatable                           AS automatable,
    s.verificationHint                      AS verification_hint,
    scope, severity, applicability, match_count, affected_entities,
    rec.recipeId                            AS recipe_id,
    ab.auto                                 AS auto,
    coalesce(ab.missingRequiredParams, [])  AS missing_required_params,
    v.version                               AS version,
    s.stepIndex                             AS step_index
ORDER BY v.sortableVersion ASC, s.stepIndex ASC
```

---

### Migration Context Tools

---

#### `create_migration_context`

Create or resume a `MigrationContext` for a `(project_id, from_version, to_version)` triple. Idempotent — MERGE key is the exact triple strings; on match refreshes typed entity buckets but does not overwrite `scannedEntities` or session status.

Resolves `from_version` with `floor` and `to_version` with `ceil` via `resolve_version()`. Applies a server-side allow-list filter to `scanned_entities` (framework-relevant prefixes only).

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes | — | Unique project identifier |
| `from_version` | string | yes | — | Starting framework version (exact MERGE key) |
| `to_version` | string | yes | — | Target framework version (exact MERGE key) |
| `framework` | string | yes | — | Framework name |
| `scanned_entities` | list[string] | no | `[]` | Entity names from codebase scan (Loop I) |
| `allow_stub_create` | boolean | no | `false` | When true, MERGE a stub `Version` node for ahead-of-catalogue targets |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `error_code` | string | On error: `"version_not_in_graph"`, `"conflict_error"`, etc. |
| `context_id` | string | Element ID — pass to all subsequent context tools |
| `project_id` | string | — |
| `from_version` | string | Caller-supplied MERGE key |
| `to_version` | string | Caller-supplied MERGE key |
| `framework` | string | — |
| `migration_status` | string | `"in-progress"`, `"complete"`, `"partial"`, `"blocked"`, `"abandoned"` |
| `scanned_entities` | list[string] | Stored entity list (allow-list filtered on create) |
| `completed_steps` | list[string] | Step element IDs (legacy array; prefer `STEP_OUTCOME`) |
| `skipped_steps` | list[string] | Step element IDs |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp |
| `completed_at` | string \| null | — |
| `notes` | string | — |
| `created` | boolean | True if newly created, false if resumed |
| `reused` | boolean | Inverse of `created` |
| `entityCount` | integer | Count after allow-list filtering |
| `droppedCount` / `dropped_count` | integer | Entities removed by allow-list |
| `upgrades_to_version` | string | Resolved ceil version on the `UPGRADES_TO` edge |
| `rounded` | boolean | True when resolved version differs from requested |
| `ahead_of_catalogue` | boolean | True when target exceeds highest known graph version |
| `stub_created` | boolean | True when a stub Version node was created |
| `co_migration_warning` | string | Present when Spring Cloud detected on Boot 3→4 upgrade |

**Error responses:** `version_not_in_graph` includes a `hint` with candidate versions. Concurrent MERGE conflicts return `conflict_error` — retry is safe.

> **Note:** `failed_steps` and `deferred_steps` are tracked in the graph node and via `STEP_OUTCOME` relationships but are not returned in this tool response.

**Cypher**

```cypher
MERGE (ctx:MigrationContext {
  projectId: $project_id,
  fromVersion: $from_version,
  toVersion: $to_version
})
ON CREATE SET
  ctx.framework = $framework,
  ctx.status = 'in-progress',
  ctx.scannedEntities = $scanned_entities,
  ctx.completedSteps = [],
  ctx.skippedSteps = [],
  ctx.failedSteps = [],
  ctx.queriedEntities = '{}',
  ctx.createdAt = datetime(),
  ctx.completedAt = null,
  ctx.notes = '',
  ctx._was_created = true,
  ctx.scannedClasses      = $scanned_classes,
  ctx.scannedClassSimple  = $scanned_class_simple,
  ctx.scannedDepsGa       = $scanned_deps_ga,
  ctx.scannedDepArtifacts = $scanned_dep_artifacts,
  ctx.scannedProps        = $scanned_props
ON MATCH SET
  ctx._was_created = false,
  ctx.scannedClasses      = $scanned_classes,
  ctx.scannedClassSimple  = $scanned_class_simple,
  ctx.scannedDepsGa       = $scanned_deps_ga,
  ctx.scannedDepArtifacts = $scanned_dep_artifacts,
  ctx.scannedProps        = $scanned_props
WITH ctx
MATCH (vf:Version {framework: $framework, version: $from_version})
MATCH (vt:Version {framework: $framework, version: $to_version})
MERGE (ctx)-[:UPGRADES_FROM]->(vf)
MERGE (ctx)-[:UPGRADES_TO]->(vt)
RETURN elementId(ctx) AS context_id,
       ctx.projectId AS project_id,
       ctx.fromVersion AS from_version,
       ctx.toVersion AS to_version,
       ctx.framework AS framework,
       ctx.status AS migration_status,
       ctx.scannedEntities AS scanned_entities,
       ctx.completedSteps AS completed_steps,
       ctx.skippedSteps AS skipped_steps,
       ctx.failedSteps AS failed_steps,
       toString(ctx.createdAt) AS created_at,
       CASE WHEN ctx.completedAt IS NULL THEN null ELSE toString(ctx.completedAt) END AS completed_at,
       coalesce(ctx.notes, '') AS notes,
       coalesce(ctx._was_created, false) AS created
```

---

#### `get_migration_contexts`

List all `MigrationContext` nodes for a project. Used in Loop I to discover prior sessions, resume in-progress contexts, or supersede stale ones.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes | — | Project identifier |
| `framework` | string | no | `null` | Optional filter by framework name |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `project_id` | string | — |
| `count` | integer | Number of contexts (0 when none exist — not an error) |
| `contexts` | list | Each: `id`, `projectId`, `fromVersion`, `toVersion`, `framework`, `status`, `createdAt`, `updatedAt`, `outcome_counts` |

Each `outcome_counts` object has: `completed`, `failed`, `skipped`, `deferred` — derived from `STEP_OUTCOME` relationships.

**Cypher**

```cypher
MATCH (ctx:MigrationContext {projectId: $project_id})
WHERE ($framework IS NULL OR ctx.framework = $framework)
OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(:MigrationStep)
WITH ctx,
     count(CASE WHEN so.status = 'completed' THEN 1 END) AS completed_count,
     count(CASE WHEN so.status = 'failed'    THEN 1 END) AS failed_count,
     count(CASE WHEN so.status = 'skipped'   THEN 1 END) AS skipped_count,
     count(CASE WHEN so.status = 'deferred'  THEN 1 END) AS deferred_count
RETURN elementId(ctx) AS id, ctx.projectId, ctx.fromVersion, ctx.toVersion,
       ctx.framework, ctx.status, toString(ctx.createdAt) AS createdAt,
       toString(ctx.updatedAt) AS updatedAt,
       completed_count, failed_count, skipped_count, deferred_count
ORDER BY ctx.createdAt DESC
```

---

#### `get_pending_steps`

Return the remaining step queue for a context, ordered by scope severity then topological step index. Excludes completed, skipped, and failed steps.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_id` | string | yes | — | Context element ID |
| `effort_filter` | list[string] | no | `[]` | Filter by effort: `"mechanical"`, `"moderate"`, `"architectural"` |
| `scope_filter` | list[string] | no | `[]` | Filter by scope |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `context_id` | string | — |
| `pending_steps` | list | Each step: `step_id`, `step_type`, `rule_id`, `summary`, `instruction`, `verification_hint`, `effort`, `automatable`, `scope`, `severity`, `recipe_id`, `requires`, `applicability` |
| `total_pending` | integer | — |

Each item in `pending_steps` carries an `applicability` field: `"matched"`, `"uncertain"`, `"informational"`, or `"universal"`. Excluded rules are filtered out and never appear in the list.

**Cypher**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
WHERE NOT elementId(s) IN ctx.completedSteps
  AND NOT elementId(s) IN ctx.skippedSteps
  AND NOT elementId(s) IN coalesce(ctx.failedSteps, [])
  AND (size($effort_filter) = 0 OR s.effort IN $effort_filter)

OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
  WHERE size($scope_filter) = 0 OR bs.scope IN $scope_filter
WITH ctx, r, s,
     min(CASE bs.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END) AS sev_rank,
     head(collect(DISTINCT bs.scope))    AS scope,
     head(collect(DISTINCT bs.severity)) AS severity

WITH ctx, r, s, sev_rank, scope, severity,
     coalesce(ctx.scannedClasses,      []) AS sc_c,
     coalesce(ctx.scannedClassSimple,  []) AS sc_cs,
     coalesce(ctx.scannedDepsGa,       []) AS sc_dga,
     coalesce(ctx.scannedDepArtifacts, []) AS sc_da,
     coalesce(ctx.scannedProps,        []) AS sc_p,
     (size(coalesce(ctx.scannedClasses, [])) > 0
       OR size(coalesce(ctx.scannedClassSimple, [])) > 0
       OR size(coalesce(ctx.scannedDepsGa, [])) > 0
       OR size(coalesce(ctx.scannedDepArtifacts, [])) > 0
       OR size(coalesce(ctx.scannedProps, [])) > 0) AS has_filter

OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH r, s, sev_rank, scope, severity, sc_c, sc_cs, sc_dga, sc_da, sc_p, has_filter, e,
     CASE
       WHEN e IS NULL THEN false
       WHEN e:Class THEN
            e.name IN sc_c
         OR last(split(e.name, '.')) IN sc_cs
       WHEN e:ApplicationProperty THEN e.name IN sc_p
       WHEN e:Dependency THEN
            (size(split(e.name, ':')) >= 2
               AND (split(e.name, ':')[0]+':'+split(e.name, ':')[1]) IN sc_dga)
         OR last(split(e.name, ':')) IN sc_da
       ELSE false
     END AS entity_match

WITH r, s, sev_rank, scope, severity, has_filter,
     count(DISTINCT e)                             AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END) AS match_count

WITH r, s, sev_rank, scope, severity,
     CASE WHEN affected_count = 0 THEN 'informational'
          WHEN NOT has_filter     THEN 'universal'
          WHEN match_count > 0    THEN 'matched'
          WHEN sev_rank <= 1      THEN 'uncertain'
          ELSE                         'excluded' END AS applicability
WHERE applicability <> 'excluded'

OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
  WHERE ab.auto = true AND coalesce(ab.missingRequiredParams, []) = []
OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
RETURN elementId(s) AS step_id,
       s.stepType    AS step_type,
       elementId(r)  AS rule_id,
       s.summary     AS summary,
       s.instruction AS instruction,
       s.verificationHint AS verification_hint,
       s.effort      AS effort,
       s.automatable AS automatable,
       scope, severity, applicability,
       rec.recipeId  AS recipe_id,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY sev_rank ASC, s.stepIndex ASC
```

---

#### `update_queried_entity`

Persist Loop II query results in the context's `queriedEntities` cache so resumed sessions skip already-queried entities.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_id` | string | yes | — | Context element ID |
| `entity_name` | string | yes | — | Entity string from the codebase scan |
| `result_summary` | string | yes | — | Brief summary of the query result (truncated to 500 chars) |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `error_code` | string | `"context_not_found"` when context missing |
| `context_id` | string | — |
| `entity_name` | string | — |
| `cached_count` | integer | Total entries in `queriedEntities` after upsert |

---

#### `update_step_status`

Record the outcome of a migration step. Writes a `STEP_OUTCOME` relationship and updates legacy step arrays on the context node. Auto-closes the context when no pending steps remain.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_id` | string | yes | — | Context element ID |
| `step_id` | string | yes | — | Step element ID |
| `outcome` | string | yes | — | `"completed"`, `"skipped"`, `"failed"`, or `"deferred"` |
| `reason` | string | no | `""` | Human-readable rationale; for `deferred`, JSON with `bridgeName`, `bridgeReason`, `requiredChange` (step elementId) |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `error_code` | string | On error: `"invalid_outcome"`, `"bridge_not_in_graph"`, `"step_not_on_path"` |
| `step_id` | string | — |
| `outcome` | string | Outcome recorded |
| `context_id` | string | — |
| `context_auto_closed` | boolean | True if context was automatically closed |
| `context_status` | string | Current migration status |
| `completed_count` | integer | — |
| `skipped_count` | integer | — |
| `auto_resolved_deferred` | list[string] | Step IDs auto-resolved when a `requiredChange` step completes |

**Deferred outcome rules:**
- The step's parent rule must have a `BRIDGED_BY` edge — otherwise returns `bridge_not_in_graph`.
- When a `requiredChange` step is later completed, deferred steps auto-resolve with `resolvedVia="bridge"`.

**Cypher — update context arrays + STEP_OUTCOME**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (s:MigrationStep) WHERE elementId(s) = $step_id
MERGE (ctx)-[so:STEP_OUTCOME]->(s)
SET so.status = $outcome, so.reason = $reason, so.updatedAt = datetime(),
    ctx.updatedAt = datetime(),
    ctx.completedSteps = CASE $outcome WHEN 'completed'
        THEN ctx.completedSteps + [$step_id] ELSE ctx.completedSteps END,
    ctx.skippedSteps = CASE $outcome WHEN 'skipped'
        THEN ctx.skippedSteps + [$step_id] ELSE ctx.skippedSteps END,
    ctx.failedSteps = CASE $outcome WHEN 'failed'
        THEN coalesce(ctx.failedSteps, []) + [$step_id] ELSE coalesce(ctx.failedSteps, []) END,
    ctx.deferredSteps = CASE $outcome WHEN 'deferred'
        THEN coalesce(ctx.deferredSteps, []) + [$step_id] ELSE coalesce(ctx.deferredSteps, []) END
RETURN elementId(ctx) AS context_id, size(ctx.completedSteps) AS completed_count,
       size(ctx.skippedSteps) AS skipped_count, ctx.status AS migration_status
```

**Cypher — auto-close context**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.status = 'complete', ctx.completedAt = datetime()
RETURN elementId(ctx) AS context_id, ctx.status AS migration_status
```

---

#### `get_steps_for_scope_tier`

Return all steps for a specific scope tier at or above a severity threshold within a context's version range.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_id` | string | yes | — | Context element ID |
| `scope` | string | yes | — | `"api-surface"`, `"runtime"`, `"config"`, `"build"`, or `"test"` |
| `severity_threshold` | string | no | `"medium"` | `"low"`, `"medium"`, `"high"`, or `"critical"` |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `context_id` | string | — |
| `scope` | string | — |
| `severity_threshold` | string | — |
| `entities` | list[string] | Unique affected entity names |
| `rule_count` | integer | — |
| `hits` | list | Steps: `entity_name`, `entity_type`, `step_id`, `rule_id`, `summary`, `scope`, `severity` |
| `total` | integer | — |

**Cypher**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
WHERE bs.scope = $scope
OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE e.name IN ctx.scannedEntities
RETURN DISTINCT e.name AS entity_name,
       labels(e)[0] AS entity_type,
       elementId(s) AS step_id,
       elementId(r) AS rule_id,
       s.summary AS summary,
       bs.scope AS scope,
       bs.severity AS severity
```

---

#### `close_migration_context`

Explicitly close a migration session with a final status and optional notes. `update_step_status` auto-closes when all steps complete — call this when skipped/deferred steps remain or to record session notes.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_id` | string | yes | — | Context element ID |
| `final_status` | string | yes | — | `"complete"`, `"partial"`, or `"abandoned"` |
| `notes` | string | no | `""` | Free-form session notes |

**Returns**

| Field | Type | Description |
|---|---|---|
| `tool_status` | string | `"ok"` or `"error"` |
| `error_code` | string | `"invalid_final_status"` when status is not one of the three allowed values |
| `context_id` | string | — |
| `migration_status` | string | Final status stored |
| `completed_steps` | list[string] | — |
| `skipped_steps` | list[string] | — |
| `completed_at` | string | ISO 8601 timestamp |
| `notes` | string | — |

**Cypher**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.status = $final_status,
    ctx.completedAt = datetime(),
    ctx.notes = $notes
RETURN elementId(ctx) AS context_id,
       ctx.status AS migration_status,
       ctx.completedSteps AS completed_steps,
       ctx.skippedSteps AS skipped_steps,
       toString(ctx.completedAt) AS completed_at,
       coalesce(ctx.notes, '') AS notes
```

---

### Search Tools

---

#### `search_migration_knowledge`

Search migration rules and community insights using hybrid BM25 + vector ranking with Reciprocal Rank Fusion (RRF). Vector search requires embeddings; falls back to BM25-only when embeddings are absent.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | yes | — | Free-text search query |
| `framework` | string | no | `"Spring Boot"` | Limit results to this framework |
| `max_results` | integer | no | `5` | Maximum hits to return |
| `rrf_k` | integer | no | `60` | RRF constant (higher = flatter ranking) |
| `top_k_per_index` | integer | no | `50` | Candidates fetched from each index before fusion |
| `min_vector_similarity` | float | no | `0.30` | Minimum cosine similarity for vector hits |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `query` | string | — |
| `hits` | list | Each hit: `node_id`, `node_type`, `statement`, `score`, `source_url`, `action_step`, `rule_type` |
| `top_k` | integer | Effective result cap |

**Cypher — BM25 phase (index: `migration_text`)**

```cypher
CALL db.index.fulltext.queryNodes($index, $search_text, {limit: $top_k})
YIELD node, score
RETURN elementId(node) AS id
ORDER BY score DESC
LIMIT $top_k
```

**Cypher — vector phase (index: `migration_knowledge_vector_mr`)**

```cypher
CALL db.index.vector.queryNodes($index, $top_k, $embedding)
YIELD node, score
WHERE score >= $min_similarity
RETURN elementId(node) AS id
ORDER BY score DESC
LIMIT $top_k
```

**Cypher — hydrate merged result set**

```cypher
MATCH (n) WHERE elementId(n) IN $ids
OPTIONAL MATCH (n)-[:INCLUDES_RULE]-(v:Version)
WHERE $framework IS NULL OR v.framework = $framework
WITH n, collect(DISTINCT v.version) AS versions
WHERE ($framework IS NULL OR size(versions) > 0)
OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)
WITH n, versions, collect(s)[0] AS first_step
RETURN elementId(n) AS node_id,
       labels(n)[0] AS node_type,
       n.statement AS statement,
       n.reason AS reason,
       coalesce(n.solution, first_step.instruction) AS solution,
       n.actionStep AS action_step,
       n.ruleType AS rule_type,
       n.sourceUrl AS source_url,
       n.description AS description,
       n.recipeId AS recipe_id,
       n.displayName AS display_name,
       versions
```

---

#### `search_openrewrite_recipes`

Search `OpenRewriteRecipe` nodes using hybrid BM25 + vector RRF ranking.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | yes | — | Free-text search query |
| `max_results` | integer | no | `5` | Maximum hits |
| `only_composite` | boolean | no | `null` | Filter to composite recipes only when `true` |
| `require_no_params` | boolean | no | `false` | Exclude recipes with required parameters when `true` |
| `rrf_k` | integer | no | `60` | RRF constant |
| `top_k_per_index` | integer | no | `50` | Candidates per index |
| `min_vector_similarity` | float | no | `0.30` | Minimum cosine similarity |

**Returns** — same shape as `search_migration_knowledge` but `statement` contains the recipe description.

**Cypher — BM25 phase (index: `openrewrite_recipe_description`)**

```cypher
CALL db.index.fulltext.queryNodes($index, $search_text, {limit: $top_k})
YIELD node, score
RETURN elementId(node) AS id
ORDER BY score DESC
LIMIT $top_k
```

**Cypher — vector phase**

```cypher
CALL db.index.vector.queryNodes($index, $top_k, $embedding)
YIELD node, score
WHERE score >= $min_similarity
RETURN elementId(node) AS id
ORDER BY score DESC
LIMIT $top_k
```

**Cypher — hydrate recipes**

```cypher
MATCH (r:OpenRewriteRecipe) WHERE elementId(r) IN $ids
  AND ($only_composite IS NULL OR coalesce(r.isComposite, false) = $only_composite)
  AND (NOT $require_no_params OR size(coalesce(r.requiredParams, [])) = 0)
RETURN elementId(r) AS node_id,
       r.recipeId AS recipe_id,
       r.displayName AS display_name,
       r.description AS description,
       r.artifactId AS artifact_id,
       r.groupId AS group_id,
       r.artifactVersion AS artifact_version,
       coalesce(r.isComposite, false) AS is_composite,
       coalesce(r.tags, []) AS tags
```

---

### Community Insight Tools

---

#### `submit_migration_insight`

Submit a developer-contributed migration insight. Runs a three-pass near-duplicate pipeline (exact → vector → BM25+cosine, threshold 0.92) before write. Creates a `MigrationRule` with `ruleType='community_insight'` linked via `INCLUDES_RULE`.

> Not idempotent — call once per unique finding.

> **Note:** The parameter name `spring_boot_version` carries the framework version string for any framework — e.g. `"3.2"` for Spring Boot, `"30"` for WildFly. The name is historical. Version is resolved via `resolve_version(mode="floor")`.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `statement` | string | yes | — | The insight statement |
| `spring_boot_version` | string | yes | — | Framework version this insight applies to |
| `solution` | string | no | `null` | Solution or workaround text |
| `affected_properties` | list[string] | no | `[]` | Spring property keys |
| `affected_classes` | list[string] | no | `[]` | Java class FQCNs |
| `affected_dependencies` | list[string] | no | `[]` | Maven artifact IDs |
| `evidence_url` | string | no | `null` | Supporting URL |
| `confidence` | float | no | `0.5` | Confidence score `[0.0, 1.0]` |
| `framework` | string | no | `"Spring Boot"` | Framework name |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"`, `"duplicate"`, or `"error"` |
| `insight_id` | string \| null | Element ID of new rule on success; `null` on duplicate/error |
| `duplicate_of` | string \| null | Element ID of existing duplicate when `status="duplicate"` |
| `message` | string | Status message |
| `error_code` | string | `"version_not_in_graph"` when version cannot be resolved |
| `candidates_considered` | list[string] | Near-miss versions on version resolution failure |

**Cypher**

```cypher
MATCH (v:Version {framework: $framework, version: $version})
CREATE (r:MigrationRule {
  statement:            $statement,
  ruleType:             'community_insight',
  sourceUrl:            coalesce($evidence_url, ''),
  communitySubmittedBy: coalesce($submitted_by, 'mcp-agent'),
  communityCreatedAt:   toString(datetime()),
  communityConfidence:  coalesce($confidence, 0.5),
  communityVotes:       0,
  communityVerified:    false
})
WITH r, v
FOREACH (emb IN CASE WHEN $embedding IS NOT NULL THEN [1] ELSE [] END |
  SET r.embedding = $embedding
)
WITH r, v
CREATE (v)-[:INCLUDES_RULE]->(r)
CREATE (s:MigrationStep {
  stepType:    'manual',
  summary:     coalesce($solution, ''),
  instruction: coalesce($solution, ''),
  effort:      'moderate',
  automatable: false
})
CREATE (r)-[:REQUIRES_STEP]->(s)
WITH r
FOREACH (class_name IN coalesce($affected_classes, []) |
  MERGE (c:Class {name: class_name})
  ON CREATE SET c.framework = $framework
  ON MATCH SET  c.framework = coalesce(c.framework, $framework)
  MERGE (r)-[:AFFECTS_CLASS]->(c)
)
WITH r
FOREACH (prop_name IN coalesce($affected_properties, []) |
  MERGE (p:ApplicationProperty {name: prop_name})
  ON CREATE SET p.framework = $framework
  ON MATCH SET  p.framework = coalesce(p.framework, $framework)
  MERGE (r)-[:AFFECTS_PROPERTY]->(p)
)
WITH r
FOREACH (dep_name IN coalesce($affected_dependencies, []) |
  MERGE (d:Dependency {name: dep_name})
  ON CREATE SET d.framework = $framework
  ON MATCH SET  d.framework = coalesce(d.framework, $framework)
  MERGE (r)-[:AFFECTS_DEPENDENCY]->(d)
)
RETURN elementId(r) AS insight_id
```

---

#### `get_community_insights`

Query community insight rules by version range, entity name, and verified status.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `from_version` | string | no | `null` | Start of version range |
| `to_version` | string | no | `null` | End of version range |
| `entity_name` | string | no | `null` | Filter to insights affecting this entity |
| `entity_type` | string | no | `null` | Reserved for future use |
| `verified_only` | boolean | no | `false` | Return only moderator-verified insights |
| `framework` | string | no | `"Spring Boot"` | Framework name |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `insights` | list | Each: `insight_id`, `statement`, `solution`, `source_url`, `submitted_by`, `created_at`, `confidence`, `votes`, `verified`, `version` (no `affected_entities` — query the graph directly for entity links) |
| `total` | integer | — |

**Cypher**

```cypher
MATCH (v:Version {framework: $framework})-[:INCLUDES_RULE]->(r:MigrationRule)
WHERE r.ruleType = 'community_insight'
  AND ($from_sortable IS NULL OR v.sortableVersion >= $from_sortable)
  AND ($to_sortable IS NULL OR v.sortableVersion <= $to_sortable)
  AND ($verified_only = false OR r.communityVerified = true)
OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH r, v, collect(DISTINCT e.name) AS affected_entities
WHERE $entity_name IS NULL
   OR ANY(name IN affected_entities WHERE name = $entity_name)
OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
WITH r, v, affected_entities, s
ORDER BY s.stepIndex ASC
WITH r, v, affected_entities, collect(s)[0] AS first_step
RETURN elementId(r)                          AS insight_id,
       r.statement                            AS statement,
       coalesce(first_step.instruction, '')   AS solution,
       r.sourceUrl                            AS source_url,
       r.communitySubmittedBy                 AS submitted_by,
       r.communityCreatedAt                   AS created_at,
       r.communityConfidence                  AS confidence,
       r.communityVotes                       AS votes,
       r.communityVerified                    AS verified,
       v.version                              AS version,
       affected_entities
ORDER BY r.communityVotes DESC, r.communityCreatedAt DESC
```

---

#### `vote_insight`

Increment or decrement the `communityVotes` counter on a community insight.

> Not idempotent — two calls with `delta=1` add 2 votes.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `insight_id` | string | yes | — | Insight element ID |
| `delta` | integer | no | `1` | `1` for upvote, `-1` for downvote |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `insight_id` | string | — |
| `new_vote_count` | integer | Updated vote count |

**Cypher**

```cypher
MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
SET r.communityVotes = coalesce(r.communityVotes, 0) + $delta
RETURN elementId(r) AS insight_id, r.communityVotes AS votes
```

---

#### `verify_insight`

Mark a community insight as moderator-verified. Not reversible via this tool.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `insight_id` | string | yes | — | Insight element ID |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `insight_id` | string | — |
| `verified` | boolean | Always `true` on success |

**Cypher**

```cypher
MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
SET r.communityVerified = true
RETURN elementId(r) AS insight_id, r.communityVerified AS verified
```

---

### Deprecation & Entity Evolution Tools

---

#### `resolve_deprecation`

Return deprecation metadata and direct replacement for a single fully-qualified entity name (one hop only).

> For the full replacement chain across multiple versions use `entity_evolution`.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_name` | string | yes | — | Fully-qualified entity name as stored in the graph (e.g. `"org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter"`) |
| `framework` | string | no | `"Spring Boot"` | Framework name |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"not_found"` |
| `entity_name` | string | — |
| `entity_type` | string | `"Class"`, `"ApplicationProperty"`, or `"Dependency"` |
| `deprecated_in` | string \| null | Version string |
| `removed_in` | string \| null | Version string |
| `replaced_by` | string \| null | Direct replacement entity name |
| `rules` | list | Related rules: `rule_id`, `statement`, `rule_type`, `action_step`, `reason`, `source_url`, `change_type`, `entity_classification`, `steps`, `scopes`, `recipes` |

**Cypher**

```cypher
MATCH (e)
WHERE (e:Class OR e:ApplicationProperty OR e:Dependency) AND e.name = $entity_name

OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REMOVED_IN]->(remV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REPLACED_BY]->(replacement)

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE rule:MigrationRule
  AND EXISTS { (rule)-[:INCLUDES_RULE]-(:Version {framework: $framework}) }

WITH e, depV, remV, replacement,
     collect({
       type: labels(rule)[0],
       statement: rule.statement,
       reason: rule.reason,
       solution: rule.solution,
       action_step: rule.actionStep
     }) AS rules

OPTIONAL MATCH (introV:Version {framework: $framework})-[:INTRODUCES]->(e)
OPTIONAL MATCH (removedByV:Version {framework: $framework})-[:REMOVES]->(e)

RETURN
  labels(e)[0] AS entity_type,
  e.name AS original_entity,
  replacement.name AS replaced_by,
  coalesce(depV.version, introV.version) AS deprecated_in,
  coalesce(remV.version, removedByV.version) AS removed_in,
  rules
```

---

#### `entity_evolution`

Trace the full `REPLACED_BY` replacement chain for an entity, up to 5 hops.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_name` | string | yes | — | Fully-qualified entity name |
| `framework` | string | no | `"Spring Boot"` | Framework name |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `origin` | string | Starting entity name |
| `chain` | list | Ordered nodes: `entity_name`, `entity_type`, `deprecated_in`, `removed_in`, `rules` |

**Cypher**

```cypher
MATCH (start)
WHERE (start:Class OR start:ApplicationProperty OR start:Dependency)
  AND start.name = $entity_name

MATCH path = (start)-[:REPLACED_BY*0..5]->(end)
WHERE NOT (end)-[:REPLACED_BY]->()

WITH nodes(path) AS lineage_nodes
UNWIND lineage_nodes AS e

OPTIONAL MATCH (e)-[:INTRODUCED_IN]->(introV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REMOVED_IN]->(remV:Version {framework: $framework})

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE rule:MigrationRule

RETURN
  labels(e)[0] AS entity_type,
  e.name AS entity_name,
  introV.version AS introduced,
  depV.version AS deprecated,
  remV.version AS removed,
  collect(DISTINCT {
      type: labels(rule)[0],
      statement: rule.statement,
      action: coalesce(rule.actionStep, rule.solution)
  }) AS rules
```

---

### Artifact Tools

---

#### `list_pipeline_runs`

List all `Version` nodes that have at least one pipeline artifact path stored in the graph. Use this to discover available `(framework, version)` keys before calling `get_artifact_content`.

**Parameters** — none

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `runs` | list | Each: `framework`, `from_version`, `to_version`, `raw_md_path`, `filtered_md_path`, `entities_json_path` |
| `total` | integer | — |

**Cypher**

```cypher
MATCH (v:Version) WHERE v.rawMdPath IS NOT NULL
RETURN v.framework AS framework,
       v.version AS version,
       v.fromVersion AS from_version,
       v.rawMdPath AS raw_md_path,
       v.filteredMdPath AS filtered_md_path,
       v.entitiesJsonPath AS entities_json_path
ORDER BY v.framework, v.sortableVersion
```

---

#### `get_artifact_content`

Read a pipeline artifact by type. The file path is resolved from the graph — callers cannot supply an arbitrary filesystem path.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `framework` | string | yes | — | Framework name |
| `from_version` | string | yes | — | Starting version |
| `to_version` | string | yes | — | Target version |
| `artifact_type` | string | yes | — | `"raw_md"`, `"filtered_md"`, or `"entities_json"` |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"`, `"not_found"`, or `"error"` |
| `framework` | string | — |
| `from_version` | string | — |
| `to_version` | string | — |
| `artifact_type` | string | — |
| `content` | string | Full file text |
| `path_resolved` | string | Resolved filesystem path |
| `message` | string | Status message |

**Cypher**

```cypher
MATCH (v:Version {framework: $framework, version: $to_version})
RETURN v.rawMdPath AS rawMdPath,
       v.filteredMdPath AS filteredMdPath,
       v.entitiesJsonPath AS entitiesJsonPath
```

---

### Schema & Custom Cypher Tools

---

#### `get_graph_schema`

Return the authoritative graph schema as a Markdown string. No Cypher is executed. Call this before writing a custom Cypher query to verify node labels and property names.

**Parameters** — none

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `schema_markdown` | string | Markdown describing all node labels, relationships, properties, and indexes |
| `server_build` | object | `git_sha`, `branch`, `feature_tags`, `started_at` — populated from env vars at server startup |

**Cypher** — none (static content; full schema in [graph-schema.md](./graph-schema.md))

---

#### `execute_custom_cypher`

Execute a read-only Cypher query and return rows. Blocked keywords (`CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, `CALL db`) cause the tool to return `status="blocked"` without executing.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | yes | — | Cypher `MATCH` query |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"`, `"blocked"`, or `"error"` |
| `rows` | list | Query result rows |
| `row_count` | integer | — |
| `blocked_keyword` | string \| null | First blocked keyword found if `status="blocked"` |
| `message` | string | Error or status message |

**Cypher** — user-supplied (validated before execution)

---

### Paysafe Dependency Tools

---

#### `resolve_paysafe_dependency_by_service_name`

Resolve a `com.paysafe.*` internal dependency via FindIt and GitLab APIs. Returns repo URL, available tags, and migration guidance. Requires `FINDIT_AUTH_TOKEN` and `GITLAB_API_KEY` environment variables.

On auth failure returns `subStatus="auth_error"` with `remediationSteps` and `unresolvedDependencies`. On network failure returns `subStatus="transport_error"`. The harness treats both as Loop IV backlog items — it does not halt Loop II.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `service_name` | string | yes | — | Service name to resolve |
| `target_version` | string | no | `null` | **Ignored in v2** — accepted for backward compatibility only |
| `framework` | string | no | `null` | **Ignored in v2** — accepted for backward compatibility only |
| `allow_latest_overall` | boolean | no | `false` | **Ignored in v2** — always behaves as `true` |
| `max_tags` | integer | no | `100` | Maximum tags to return |
| `pinned_version` | string | no | `null` | Pinned version override |
| `pinned_tag` | string | no | `null` | Pinned tag override |

**Returns** — delegate response from the Paysafe resolver: `repo`, `tags`, `migration_guidance`

| Field | Type | Description |
|---|---|---|
| `framework_version` | string \| null | Always null in v2 |
| `compatibility` | object \| null | Always null in v2 |
| `selection_strategy` | string | Always `"latest_overall"` in v2 (except pinned) |

> **v2 behaviour:** FindIt is queried once at server startup. Per-call resolution reads from
> the startup cache and falls back to a live FindIt call only on a cache miss. Compatibility
> checking has been removed — the tool always returns the latest semver-sorted tag. The agent
> harness should treat all results as needing human confirmation before deployment.

**Cypher** — none (external API calls only)

---

### Skill Installation

---

#### `install_migration_skill`

Copy bundled skill Markdown files to the Cursor or Claude Code skills directory.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `target` | string | no | `"auto"` | `"auto"` (detect from CWD/HOME), `"cursor"`, or `"claude-code"` |
| `target_dir` | string | no | `null` | Custom target directory override |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `target` | string | Resolved target IDE |
| `installed_paths` | list[string] | Paths written |
| `message` | string | Status message |

**Cypher** — none (filesystem operation)

---

## Prompts

Prompts are pre-built instruction templates that configure an AI agent to run the four-loop migration harness. They are registered as MCP prompts on the server and resolved by compatible clients (Claude Code, Cursor).

---

### `start_migration`

Start a new four-loop migration session for a project.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `framework` | string | e.g. `"Spring Boot"`, `"Angular"`, `"WildFly"` |
| `current_version` | string | Version migrating FROM (e.g. `"2.7"`) |
| `target_version` | string | Version migrating TO (e.g. `"3.2"`) |
| `project_id` | string | Unique project identifier; used to create or resume a `MigrationContext` |

**Prompt text (actual):**

```
Load skill://framework-migration/main.

Migrate project '{project_id}' from {framework} {current_version} to {framework} {target_version}.

Run the four-loop migration harness:
- Loop I: scan the codebase, call create_migration_context
- Loop II: query the graph in scope-gated tiers (api-surface → runtime → config/build → test)
- Loop III: execute each pending step (auto or manual; ask me to confirm manual steps)
- Loop IV: submit new insights via submit_migration_insight, then call close_migration_context
```

---

### `resume_migration`

Resume a four-loop session from an existing `MigrationContext`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `context_id` | string | Element ID returned by `create_migration_context` or `get_pending_steps` in a previous session |

**Prompt text (actual):**

```
Load skill://framework-migration/main.

Resume migration context '{context_id}'.

Call get_pending_steps(context_id='{context_id}') to see what remains.
Continue from Loop III: execute each pending step, then run Loop IV
(submit insights, close context).
```

---

### `migration_workflow_prompt`

Zero-parameter fallback for clients that do not support parameterised prompts. Prefer `start_migration` or `resume_migration` when the client supports parameters.

**Parameters** — none

**Prompt text (actual):**

```
Load skill://framework-migration/main.

I want to migrate this project from [framework] [current_version] to [target_version].
Project ID: [your-project-id]

Run the four-loop migration harness:
- Loop I: scan the codebase, create or resume a migration context
- Loop II: query the graph in scope-gated tiers (api-surface → runtime → config/build → test)
- Loop III: execute each pending step (auto or manual)
- Loop IV: submit any new insights, close the context
```

---

## Skill Resources

Skill resources are Markdown files registered as MCP resources under the `skill://` URI scheme. Load them at session start via `skill://framework-migration/<name>` or through the `start_migration` / `resume_migration` prompts.

---

### `skill://framework-migration/main`

**File:** `migration_oracle/mcp/skills/framework_migration_main.md`

The core four-loop migration harness. Defines the procedural workflow an agent must follow to complete a framework upgrade end-to-end.

| Loop | Name | Purpose |
|---|---|---|
| **I** | Context | Preflight (Python/PyYAML), `get_migration_contexts` for resume/supersede, codebase scan, entity diff, version-map preconditions, `create_migration_context` |
| **I (fallback)** | Stateless | When context creation fails — continue with `analyze_upgrade_path` + `build_recipe_plan` without persisting state |
| **II** | Scope-gated Query | Query in blast-radius order: `api-surface` → `runtime` → `config`/`build` → `test`; `get_steps_for_scope_tier`, `analyze_upgrade_path`, `resolve_deprecation`, `entity_evolution`, `search_migration_knowledge`; Paysafe deps via `resolve_paysafe_dependency_by_service_name`; cache via `update_queried_entity` |
| **III** | Execution | `get_pending_steps` work queue; executor routing (OpenRewrite → prompted-auto → agent-codemod → human-review); build-and-test gate; rollback on failure; bridge/deferred outcomes |
| **IV** | Feedback | `submit_migration_insight` for novel findings; skipped/deferred backlog; `close_migration_context` with `complete`/`partial`/`abandoned` |

Embedded decision tables cover context resume, query skip-guards, executor selection, and feedback routing.

---

### `skill://framework-migration/scanning`

**File:** `migration_oracle/mcp/skills/framework_migration_scanning.md`

Codebase scanning patterns for entity extraction (Loop I). Produces strings in the **exact form the graph stores** — matching is exact-string, not fuzzy.

| Section | Content |
|---|---|
| **Extractor selection** | Python canonical (`extractorPath: "python"`) vs grep fast path (`grep-gnu` / `grep-bsd`); PyYAML degrade path for YAML properties |
| **Python canonical extractor** | Full `framework_scanner.py` reference — imports, annotations, properties, Maven/Gradle deps |
| **Relevance filtering** | Allow-list prefixes per framework; noise causes false simple-name collisions |
| **Entity Format Reference** | Java FQCN, annotation simple names, property keys, `groupId:artifactId`, npm packages, WildFly subsystem keys |
| **Spring Boot / Angular / WildFly** | Per-framework extraction patterns (Python primary, grep optional) |
| **Entity Prioritisation** | Tiered cap (default 200); test entities tracked separately for tier 4 |
| **Multi-Module Detection** | Scan each module, union and dedupe before cap |

---

### `skill://framework-migration/plan-format`

**File:** `migration_oracle/mcp/skills/framework_migration_plan_format.md`

Output format for human-readable migration plans (`MIGRATION_PLAN.md`) when the harness runs in plan mode rather than interactive execution.

| Section | Content |
|---|---|
| **File location** | `$PROJECT_ROOT/MIGRATION_PLAN.md` |
| **Header / Prerequisites / Task blocks** | Structured TASK-NNN entries with risk labels, effort, before/after, verification |
| **Dependency Updates table** | Version changes including Paysafe services |
| **Risk Labels** | HIGH / MEDIUM / LOW semantics |
| **Task Ordering Rules** | Build → removed deps → APIs → derived → config → test |
| **Agent Instructions Preamble** | Sequential work, verify after each task, search before manual review |
| **Assistant Template (4B)** | Human-readable migration guide format |

---

### `skill://framework-migration/version-map`

**File:** `migration_oracle/mcp/skills/framework_migration_version_map.md`

Framework version catalogue, toolchain gates, and detection heuristics. Surfaced in Loop I Step 5 before querying begins.

| Section | Content |
|---|---|
| **Spring Boot version table** | 2.5.0 → 4.1.0 with `sortableVersion`, status, minimum Java |
| **Spring Boot key boundaries** | 2.x→3.x (Java 17, javax→jakarta); 3.x→4.x (Java 21) |
| **Spring Cloud train table** | Hoxton through Oakwood (2025.1.x); calVer sortableVersion formula; BOM-only Oakwood |
| **Angular version table** | 14.0.0 → 22.0.0 with minimum Node |
| **Angular key boundaries** | Standalone defaults, control flow, signals, zoneless |
| **Framework Detection Heuristics** | Detect from `pom.xml`, `build.gradle`, `angular.json`, `package.json` |
| **Version String Normalisation** | `"3.2"` → `3.2.0`; patch preserved on resolution |

> Status fields are advisory — validate against upstream release schedules when planning production migrations.

---

### `skill://framework-migration/rollback`

**File:** `migration_oracle/mcp/skills/framework_migration_rollback.md`

Five-step revert procedure invoked from Loop III when a build-and-test gate fails after an agent-codemod or OpenRewrite step:

1. **Identify** — note `step_id` and build error
2. **Stash** — `git stash push -m "rollback: failed migration step <step_id>"`
3. **Verify** — confirm build passes after stash
4. **Decide** — skip, retry with fix, or abandon session
5. **Record** — `update_step_status(outcome="failed", reason="build failed: …")`; continue remaining queue

---

## Tool Index

| Tool | Loop | Purpose |
|---|---|---|
| `check_version_availability` | I | Resolve and validate framework versions |
| `create_migration_context` | I | Create/resume session state |
| `get_migration_contexts` | I, IV | List prior sessions for resume/supersede |
| `analyze_upgrade_path` | II | Rules + lifecycle alerts for version range |
| `get_steps_for_scope_tier` | II | Scope-tier step discovery |
| `resolve_deprecation` | II | Single-hop deprecation lookup |
| `entity_evolution` | II | Multi-hop replacement chain |
| `search_migration_knowledge` | II | Hybrid BM25+vector search fallback |
| `search_openrewrite_recipes` | II, III | Recipe discovery |
| `resolve_paysafe_dependency_by_service_name` | II | Internal Paysafe dep resolution |
| `update_queried_entity` | II | Cache query results on context |
| `get_pending_steps` | III | Remaining execution queue |
| `build_recipe_plan` | III | Auto/manual track plan |
| `update_step_status` | III, IV | Record step outcomes |
| `close_migration_context` | IV | End session |
| `submit_migration_insight` | IV | Write community knowledge back |
| `get_community_insights` | — | Read community rules |
| `vote_insight` / `verify_insight` | — | Community moderation |
| `list_pipeline_runs` / `get_artifact_content` | — | Pipeline artifact access |
| `get_graph_schema` / `execute_custom_cypher` | — | Ad-hoc graph queries |
| `install_migration_skill` | — | Install harness skills locally |

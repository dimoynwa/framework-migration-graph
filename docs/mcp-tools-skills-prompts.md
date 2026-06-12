# MCP Tools, Skills & Prompts — Paysafe Migration Oracle

Full reference for every MCP tool, skill resource, and prompt exposed by the server. Each tool entry includes its description, parameters, return shape, and every Cypher query it executes.

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

---

## Tool Groups

---

### Upgrade Path Tools

---

#### `check_version_availability`

Check whether a framework version exists in the graph and on Maven Central.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `framework` | string | yes | — | Framework name (e.g. `"Spring Boot"`) |
| `version` | string | yes | — | Version string to check (e.g. `"3.2.0"`) |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `exists_in_graph` | boolean | True if a matching `Version` node exists |
| `ga_available` | boolean | True if the version is available on Maven Central |
| `latest_patch` | string \| null | Latest known patch version for the same minor line |
| `hint` | string | Human-readable guidance |

**Cypher**

```cypher
MATCH (v:Version {framework: $framework, version: $version})
RETURN count(v) > 0 AS found
```

---

#### `analyze_upgrade_path`

Return all migration rules and lifecycle alerts for a framework version range. Optionally filters by user-scanned entities (substring match), scope, severity, and entity classification.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `framework` | string | yes | — | Framework name |
| `current_version` | string | yes | — | Migration source version |
| `target_version` | string | yes | — | Migration target version |
| `user_entities` | list[string] | no | `[]` | Java class names, Spring property keys, or Maven artifact IDs to filter rules |
| `format` | string | no | `"json"` | `"json"` or `"markdown"` |
| `classification` | list[string] | no | `[]` | Filter by `entityClassification`: `"actionable"`, `"incomplete"`, `"informational"` |
| `include_recipes` | boolean | no | `false` | Include linked OpenRewrite recipes per step |
| `include_lifecycle` | boolean | no | `true` | Include `LifecycleAlert` nodes |
| `top_n` | integer | no | `50` | Maximum rules to return |
| `verbose` | boolean | no | `false` | Verbose output with full reason/solution fields |
| `scope_filter` | list[string] | no | `[]` | Filter by scope: `"api-surface"`, `"runtime"`, `"config"`, `"build"`, `"test"` |
| `min_severity` | string | no | `null` | Minimum severity: `"low"`, `"medium"`, `"high"`, `"critical"` |

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

**Cypher**

```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable

OPTIONAL MATCH (e_lc)-[rel:DEPRECATED_IN|REMOVED_IN|INTRODUCED_IN]->(v)
WHERE size($user_entities) = 0
   OR ANY(u IN $user_entities WHERE toLower(e_lc.name) CONTAINS toLower(u))

WITH v, collect(DISTINCT {
    event_type: type(rel),
    entity_type: labels(e_lc)[0],
    entity_name: e_lc.name
}) AS raw_lifecycle_events

OPTIONAL MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)

WITH v, raw_lifecycle_events, rule,
     collect(DISTINCT ruleEntity.name) AS affected_entities

WHERE rule IS NULL
   OR (
       (size($user_entities) = 0
          OR size(affected_entities) = 0
          OR ANY(e IN affected_entities
                   WHERE ANY(u IN $user_entities
                              WHERE toLower(e) CONTAINS toLower(u))))
       AND
       (size($classification) = 0
          OR rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

WITH v, raw_lifecycle_events, rule, affected_entities,
     collect(DISTINCT {
         step_id: elementId(s),
         step_type: s.stepType,
         summary: s.summary,
         instruction: s.instruction,
         effort: s.effort,
         automatable: s.automatable,
         verification_hint: s.verificationHint,
         cli_operation: s.cliOperation
     }) AS steps,
     collect(DISTINCT {
         scope: bs.scope,
         severity: bs.severity
     }) AS scopes,
     collect(DISTINCT {
         recipe_id: rec.recipeId,
         display_name: rec.displayName,
         auto: ab.auto,
         missing_required_params: coalesce(ab.missingRequiredParams, [])
     }) AS recipes

WITH v, raw_lifecycle_events, collect(DISTINCT {
    rule_id: elementId(rule),
    rule_type: labels(rule)[0],
    title: rule.title,
    statement: rule.statement,
    action_step: rule.actionStep,
    source_url: rule.sourceUrl,
    reason: coalesce(rule.statement, rule.reason),
    solution: rule.solution,
    change_type: rule.changeType,
    reason_type: rule.reasonType,
    entity_classification: rule.entityClassification,
    affected_entities: affected_entities,
    steps: [x IN steps WHERE x.step_id IS NOT NULL],
    scopes: [x IN scopes WHERE x.scope IS NOT NULL],
    recipes: [x IN recipes WHERE x.recipe_id IS NOT NULL]
}) AS raw_rules

OPTIONAL MATCH (v)-[:HAS_LIFECYCLE_ALERT]->(la:LifecycleAlert)

WITH v, raw_lifecycle_events, raw_rules,
     collect(DISTINCT {message: la.message, category: la.category, phase: la.phase}) AS raw_phase_alerts_all

RETURN
    v.version AS release_version,
    v.sortableVersion AS release_sortable,
    [x IN raw_rules WHERE x.statement IS NOT NULL] AS rules,
    [x IN raw_lifecycle_events WHERE x.event_type IS NOT NULL] AS lifecycle_events,
    [x IN raw_phase_alerts_all WHERE x.message IS NOT NULL] AS raw_phase_alerts
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

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` |
| `auto_track` | list | Steps with `automatable=true`, effort `"mechanical"`, and a linked recipe |
| `manual_track` | list | All other steps; each has `applicability` and `matched_entities` |
| `fallback_to_rule_cards` | boolean | True when no `MigrationStep` nodes exist |

**Cypher**

```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable

MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)
WITH v, rule, collect(DISTINCT ruleEntity.name) AS affected_entities
WHERE size($user_entities) = 0
   OR size(affected_entities) = 0
   OR ANY(e IN affected_entities
            WHERE ANY(u IN $user_entities
                       WHERE toLower(e) CONTAINS toLower(u)))

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
OPTIONAL MATCH (s)-[ab_s:AUTOMATED_BY]->(rec_s:OpenRewriteRecipe)
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ae)

WITH v, rule, affected_entities, s, bs, ab_s, rec_s,
     elementId(rule) AS rule_id,
     elementId(s) AS step_id,
     collect(DISTINCT ae.name) AS all_affected_entities

RETURN
    rule_id,
    step_id,
    rule.statement AS statement,
    rule.actionStep AS action_step,
    s.summary AS summary,
    s.instruction AS instruction,
    s.effort AS effort,
    s.automatable AS automatable,
    s.verificationHint AS verification_hint,
    bs.scope AS scope,
    bs.severity AS severity,
    rec_s.recipeId AS recipe_id,
    ab_s.auto AS auto,
    coalesce(ab_s.missingRequiredParams, []) AS missing_required_params,
    v.version AS version,
    all_affected_entities
ORDER BY v.sortableVersion ASC, s.stepIndex ASC
```

---

### Migration Context Tools

---

#### `create_migration_context`

Create or resume a `MigrationContext` for a `(project_id, from_version, to_version)` triple. Idempotent — returns the existing context unchanged when called again with the same triple.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `project_id` | string | yes | — | Unique project identifier |
| `from_version` | string | yes | — | Starting framework version |
| `to_version` | string | yes | — | Target framework version |
| `framework` | string | yes | — | Framework name |
| `scanned_entities` | list[string] | no | `[]` | Entity names from codebase scan (Loop I) |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `context_id` | string | Element ID — pass to all subsequent context tools |
| `project_id` | string | — |
| `from_version` | string | — |
| `to_version` | string | — |
| `framework` | string | — |
| `migration_status` | string | `"in-progress"`, `"complete"`, `"partial"`, `"blocked"`, `"abandoned"` |
| `scanned_entities` | list[string] | — |
| `completed_steps` | list[string] | Step element IDs |
| `skipped_steps` | list[string] | Step element IDs |
| `created_at` | string | ISO 8601 timestamp |
| `completed_at` | string \| null | — |
| `notes` | string | — |
| `created` | boolean | True if newly created, false if resumed |

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
  ctx._was_created = true
ON MATCH SET
  ctx._was_created = false
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
| `pending_steps` | list | Each step has `step_id`, `step_type`, `rule_id`, `summary`, `instruction`, `verification_hint`, `effort`, `automatable`, `scope`, `severity`, `recipe_id`, `requires` |
| `total_pending` | integer | — |

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
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
  WHERE ab.auto = true AND ab.missingRequiredParams = []
OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
RETURN elementId(s) AS step_id,
       s.stepType AS step_type,
       elementId(r) AS rule_id,
       s.summary AS summary,
       s.instruction AS instruction,
       s.verificationHint AS verification_hint,
       s.effort AS effort,
       s.automatable AS automatable,
       bs.scope AS scope,
       bs.severity AS severity,
       rec.recipeId AS recipe_id,
       s.stepIndex AS _step_index,
       CASE bs.severity
         WHEN 'critical' THEN 0 WHEN 'high' THEN 1
         WHEN 'medium'   THEN 2 ELSE 3
       END AS _severity_rank,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY _severity_rank ASC, _step_index ASC
```

---

#### `update_step_status`

Record the outcome of a migration step. Auto-closes the context when no pending steps remain after this call.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_id` | string | yes | — | Context element ID |
| `step_id` | string | yes | — | Step element ID |
| `outcome` | string | yes | — | `"completed"`, `"skipped"`, or `"failed"` |
| `reason` | string | no | `null` | Human-readable rationale |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `step_id` | string | — |
| `outcome` | string | Outcome recorded |
| `context_id` | string | — |
| `context_auto_closed` | boolean | True if context was automatically closed |
| `context_status` | string | Current migration status |
| `completed_count` | integer | — |
| `skipped_count` | integer | — |

**Cypher — validate step is on path**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
WHERE elementId(s) = $step_id
RETURN count(s) > 0 AS on_path
```

**Cypher — update context arrays**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.completedSteps = CASE $outcome WHEN 'completed'
    THEN ctx.completedSteps + [$step_id] ELSE ctx.completedSteps END,
    ctx.skippedSteps = CASE $outcome WHEN 'skipped'
    THEN ctx.skippedSteps + [$step_id] ELSE ctx.skippedSteps END,
    ctx.failedSteps = CASE $outcome WHEN 'failed'
    THEN coalesce(ctx.failedSteps, []) + [$step_id] ELSE coalesce(ctx.failedSteps, []) END
RETURN elementId(ctx) AS context_id,
       size(ctx.completedSteps) AS completed_count,
       size(ctx.skippedSteps) AS skipped_count,
       ctx.status AS migration_status
```

**Cypher — write STEP_OUTCOME relationship**

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (s:MigrationStep) WHERE elementId(s) = $step_id
MERGE (ctx)-[rel:STEP_OUTCOME]->(s)
SET rel.status    = $status,
    rel.reason    = $reason,
    rel.updatedAt = datetime()
RETURN elementId(rel) AS rel_id
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
| `hits` | list | Steps: `step_id`, `rule_id`, `summary`, `scope`, `severity` |
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
WITH ctx, v, r, s, bs
WHERE bs IS NULL OR bs.scope = $scope
RETURN DISTINCT elementId(s) AS step_id,
       elementId(r) AS rule_id,
       s.summary AS summary,
       bs.scope AS scope,
       bs.severity AS severity
```

---

#### `close_migration_context`

Explicitly close a migration session with a final status and optional notes. `update_step_status` auto-closes when all steps complete — call this tool only when ending with skipped steps or to add notes.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `context_id` | string | yes | — | Context element ID |
| `final_status` | string | yes | — | `"complete"` or `"partial"` |
| `notes` | string | no | `""` | Free-form session notes |

**Returns**

| Field | Type | Description |
|---|---|---|
| `tool_status` | string | `"ok"` |
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
OPTIONAL MATCH (n)-[:INCLUDES_RULE|DISCOVERED_IN]-(v:Version)
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

> **Note:** `only_composite` and `require_no_params` filter parameters are accepted but not yet enforced — all matching recipes are returned regardless of those values.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | yes | — | Free-text search query |
| `max_results` | integer | no | `5` | Maximum hits |
| `only_composite` | boolean | no | `null` | Reserved — not yet applied |
| `require_no_params` | boolean | no | `false` | Reserved — not yet applied |
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
  AND (NOT $only_composite OR r.composite = true)
  AND (NOT $require_no_params OR NOT EXISTS {
    MATCH (r)-[:HAS_PARAM]->(p:RecipeParam) WHERE p.required = true
  })
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

Submit a developer-contributed migration insight. Runs near-duplicate detection before write (cosine similarity threshold). Returns `status="duplicate"` if a similar insight already exists.

> Not idempotent — call once per unique finding.

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
| `insight_id` | string | Element ID of written rule |
| `duplicate_of` | string \| null | Element ID of existing duplicate |
| `message` | string | Status message |

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
| `insights` | list | Each: `insight_id`, `statement`, `solution`, `source_url`, `submitted_by`, `created_at`, `confidence`, `votes`, `verified`, `version` |
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
| `rules` | list | Related rules: `statement`, `rule_type`, `action_step`, `reason` |

**Cypher**

```cypher
MATCH (e)
WHERE (e:Class OR e:ApplicationProperty OR e:Dependency) AND e.name = $entity_name

OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REMOVED_IN]->(remV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REPLACED_BY]->(replacement)

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE rule:MigrationRule
  AND EXISTS { (rule)-[:INCLUDES_RULE|DISCOVERED_IN]-(:Version {framework: $framework}) }

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

**Cypher** — none (static content)

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

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `service_name` | string | yes | — | Service name to resolve |
| `target_version` | string | no | `null` | Filter tags compatible with this framework version |
| `framework` | string | no | `null` | Framework name |
| `allow_latest_overall` | boolean | no | `false` | Allow returning the latest tag regardless of version compatibility |
| `max_tags` | integer | no | `100` | Maximum tags to return |
| `pinned_version` | string | no | `null` | Pinned version override |
| `pinned_tag` | string | no | `null` | Pinned tag override |

**Returns** — delegate response from the Paysafe resolver: `repo`, `tags`, `migration_guidance`

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

**Behaviour:** Produces a prompt that instructs the agent to load `skill://framework-migration/main` and run all four loops from the beginning — Loop I (context + scan), Loop II (scope-gated graph query), Loop III (step execution), Loop IV (insight feedback).

---

### `resume_migration`

Resume a four-loop session from an existing `MigrationContext`.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `context_id` | string | Element ID returned by `create_migration_context` or `get_pending_steps` in a previous session |

**Behaviour:** Produces a prompt that instructs the agent to load `skill://framework-migration/main`, call `get_pending_steps(context_id=...)` to retrieve remaining work, then continue from Loop III.

---

### `migration_workflow_prompt`

Zero-parameter fallback for clients that do not support parameterised prompts. Prefer `start_migration` or `resume_migration` when the client supports parameters.

**Parameters** — none

**Behaviour:** Produces the same four-loop harness prompt with placeholder tokens `[framework]`, `[current_version]`, `[target_version]`, and `[your-project-id]` for the user to fill in manually.

---

## Skill Resources

Skill resources are Markdown files registered as MCP resources under the `skill://` URI scheme. They are loaded by the agent at the start of a migration session via `skill://framework-migration/<name>`.

---

### `skill://framework-migration/main`

**File:** `migration_oracle/mcp/skills/framework_migration_main.md`

The core migration harness. Defines four sequential loops the agent must execute to complete a migration.

| Loop | Name | Purpose |
|---|---|---|
| **I** | Context | Call `create_migration_context` with scanned entities; handle resume vs. new-session logic; surface version boundary preconditions (Java version, namespace migration) |
| **I (fallback)** | Stateless Fallback | When context creation fails, continue in-memory using `analyze_upgrade_path` + `build_recipe_plan` without persisting state |
| **II** | Scope-gated Query | Query migration rules in blast-radius priority order: `api-surface` → `runtime` → `config`/`build` → `test`; use `get_steps_for_scope_tier` per tier |
| **III** | Execution | Apply pending steps via `get_pending_steps`; route each step through a decision table: auto-execute, prompted-auto, manual, design-gate, blocked, or rollback; call `update_step_status` after each outcome |
| **IV** | Feedback | Call `submit_migration_insight` for any novel findings; emit backlog items for unresolved issues; call `close_migration_context` |

Each loop has a full decision-logic reference table embedded in the skill file.

---

### `skill://framework-migration/scanning`

**File:** `migration_oracle/mcp/skills/framework_migration_scanning.md`

Codebase scanning patterns for entity extraction (Loop I).

| Section | Content |
|---|---|
| **Entity Format Quick Reference** | Maps entity types (Java class, annotation, Spring property, Maven/Gradle dep, npm package) to their graph storage format and bash extraction commands |
| **Spring Boot — Java/Kotlin** | Import extraction (FQCN), annotation extraction (simple name without `@`), `.properties` and `.yml` parsing, Maven `pom.xml` and Gradle dependency extraction |
| **Angular — TypeScript** | Import extraction (exact npm package name), `package.json` parsing, `NgModule` extraction |
| **Entity Prioritisation** | Ranking tiers for trimming to top 200 entities: Spring Framework, Hibernate/Micrometer, annotations, Maven/Gradle artifacts, Angular packages, Spring properties, others |
| **Multi-Module Detection** | Bash commands to detect and handle multi-module Maven/Gradle projects |

---

### `skill://framework-migration/plan-format`

**File:** `migration_oracle/mcp/skills/framework_migration_plan_format.md`

Output format specification for `MIGRATION_PLAN.md` (Loop III).

| Section | Content |
|---|---|
| **File location** | `MIGRATION_PLAN.md` at the project root |
| **Header block** | Metadata: framework, from/to versions, date, project |
| **Prerequisites block** | Checklist of environment gates (Java version, toolchain, etc.) |
| **Task blocks** | One block per change: summary, file pattern, effort, before/after code reference, verification steps |
| **Dependency Updates table** | Version changes for all affected dependencies |
| **Final Verification Checklist** | Build, test, lint, cleanup |
| **Risk Labels** | `HIGH` (removed/no replacement), `MEDIUM` (deprecated/renamed), `LOW` (trivial rename) |
| **Task Ordering Rules** | Build changes → removed deps → foundational APIs → derived changes → config → test; within each group: `HIGH` before `MEDIUM` before `LOW` |
| **Effort Estimation Guide** | `XS` (single rename, <5 min) → `S` → `M` → `L` (>90 min, architectural) |
| **Agent Instructions Preamble** | Sequential-only work, verify after each task, preserve behaviour, track progress |

---

### `skill://framework-migration/version-map`

**File:** `migration_oracle/mcp/skills/framework_migration_version_map.md`

Framework version catalogue and toolchain gate rules.

| Section | Content |
|---|---|
| **Spring Boot version table** | Versions 2.5.0 → 4.1.0 with `sortableVersion`, status (`EOL`/`Maintenance`/`Active`), and minimum Java version |
| **Spring Boot key boundaries** | `2.x → 3.x`: requires Java 17 and `javax.*` → `jakarta.*`; `3.x → 4.x`: requires Java 21 |
| **Recommended incremental path** | `2.5.x → 2.7.x → 3.0.x → 3.2.x` — never skip more than one major |
| **Angular version table** | Versions 14.0.0 → 22.0.0 with status and minimum Node version |
| **Angular key boundaries** | 15→16 standalone components; 16→17 new control flow syntax; 17→18 stable signals; 18→19+ zoneless change detection |
| **Framework Detection Heuristics** | Rules to detect framework from `pom.xml`, `build.gradle`, `angular.json`, `package.json` |
| **Version String Normalisation** | `"3.2"` → `3.2.0`; `"Spring Boot 3"` → `3.0.0` or latest 3.x patch |

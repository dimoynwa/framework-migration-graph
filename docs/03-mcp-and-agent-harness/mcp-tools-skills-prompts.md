# MCP Tools, Skills & Prompts — Paysafe Migration Oracle

Full reference for every MCP tool, skill resource, and prompt exposed by the `PaysafeMigrationOracle` MCP server (`migration_oracle/mcp/`). Each tool entry includes its description, parameters, return shape, and representative Cypher where applicable.

For the authoritative graph model, see [graph-schema.md](../01-foundation/graph-schema.md). For the end-to-end pipeline (changelog extraction to graph population), see [migration-oracle-redesign.md](../01-foundation/migration-oracle-redesign.md).

---

## System Architecture

The Migration Oracle is a three-layer system:

| Layer | Role | Key artifacts |
|---|---|---|
| **Knowledge graph** | Stores framework release knowledge — rules, steps, affected entities, OpenRewrite recipes, community insights | Neo4j/Memgraph; schema in [graph-schema.md](../01-foundation/graph-schema.md) |
| **MCP server** | Exposes graph queries, search, and Paysafe dependency resolution to AI agents | Knowledge tools (full mode); count varies by `MCP_ACTIVE_STAGE` |
| **Agent harness** | Six-stage file-state migration workflow | `skill://framework-migration-*` resources; state in `ps-migration/` files |

### Six-stage file-state harness

The harness uses a linear six-stage sequence with optional research. Progress lives in
`ps-migration/` markdown files in the consumer repo — not in the graph.

```
research    → optional: scan codebase, query graph, emit research.md checkpoint
plan        → scan codebase, query graph knowledge (or consume research.md), emit plan.md / tasks.md / verification.md
gap-check   → mechanical file-only audit of plan.md and tasks.md
clarify     → optional Relevance-Index resolution in tasks.md (file-only)
preview     → read-only plan grouped by risk (file-only)
execute     → work tasks sequentially, update Status in tasks.md, run verification gate
```

Set `MCP_ACTIVE_STAGE` to restrict registered tools per session.

Supporting skill files:

| Resource URI | File | Used in |
|---|---|---|
| `skill://framework-migration-research/main` | `framework-migration/research.md` | research — knowledge query and research.md checkpoint |
| `skill://framework-migration-plan/main` | `framework-migration/plan.md` | plan — knowledge query and file emission |
| `skill://framework-migration-gap-check/main` | `framework-migration/gap-check.md` | gap-check — file-only mechanical audit |
| `skill://framework-migration-clarify/main` | `framework-migration/clarify.md` | clarify — Relevance-Index resolution |
| `skill://framework-migration-preview/main` | `framework-migration/preview.md` | preview — read-only plan rendering |
| `skill://framework-migration-execute/main` | `framework-migration/execute.md` | execute — sequential task execution |
| `skill://framework-migration-plan/scanning` | `framework-migration/scanning.md` | plan/research — entity extraction |
| `skill://framework-migration-plan/version-map` | `framework-migration/version-map.md` | plan/research — version tables, toolchain gates |
| `skill://framework-migration-execute/rollback` | `framework-migration/rollback.md` | execute — revert procedure after build failure |

Canonical file schemas: `migration_oracle/mcp/skills/templates/plan.md`, `tasks.md`, `verification.md`.
Operator guide: [instruction.md](../04-operator-guides/instruction.md).

**Removed (017):** Seven session-state tools and two graph-mutation helpers were deleted.
Per-migration progress now lives in `ps-migration/` markdown files. See spec 017 for the exact list.

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

Uses `resolve_version()` with configurable direction — the same resolution logic used during plan-stage version binding and `submit_migration_insight`.

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

### Migration Context Tools (removed in 017)

The following session-state tools were deleted. Per-migration progress now lives in
`ps-migration/` markdown files in the consumer repo. See spec 017 for the exact tool list.

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

**Cypher** — none (static content; full schema in [graph-schema.md](../01-foundation/graph-schema.md))

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

On auth failure returns `subStatus="auth_error"` with `remediationSteps` and `unresolvedDependencies`. On network failure returns `subStatus="transport_error"`. The harness treats both as plan-stage backlog items — it does not halt knowledge queries.

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

Copy bundled skill Markdown files into the consumer project's skills directory.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `target` | string | no | `"auto"` | `"auto"` (defaults to Cursor), `"cursor"`, or `"claude-code"` |
| `target_dir` | string | no | `null` | Custom install root override; when set, `scope` is ignored |
| `project_dir` | string | no | `null` | Starting path for project-root detection; defaults to process CWD |
| `scope` | string | no | `"project"` | `"project"` → `{project_root}/.cursor/skills` or `.claude/skills`; `"global"` → `~/.cursor/skills` or `~/.claude/skills` |

**Returns**

| Field | Type | Description |
|---|---|---|
| `status` | string | `"ok"` or `"error"` |
| `target` | string | Resolved target IDE |
| `installed_paths` | list[string] | Paths written |
| `message` | string | Status message |
| `mode` | string | `"full"` or `"lite"` |
| `installed_skills` | list[string] | Bundle names installed |
| `project_root` | string | Resolved consumer project root (absolute path) |
| `scope` | string | `"project"` or `"global"` |

Project-local bundles may be committed to version control or gitignored; that is a consumer-team choice.

**Full mode bundles** (six top-level directories): `framework-migration-research`, `framework-migration-plan`, `framework-migration-gap-check`, `framework-migration-clarify`, `framework-migration-preview`, `framework-migration-execute`.

**Lite mode bundles** (unchanged): `migration-lite`, `openrewrite-runner`.

**Cypher** — none (filesystem operation)

---

## Prompts
Prompts are pre-built instruction templates for the six-stage file-state migration harness.

---

### `start_migration`

Start a new file-state migration for a project.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `framework` | string | e.g. `"Spring Boot"`, `"Angular"`, `"WildFly"` |
| `current_version` | string | Version migrating FROM (e.g. `"2.7"`) |
| `target_version` | string | Version migrating TO (e.g. `"3.2"`) |
| `project_id` | string | Project identifier (recorded in plan.md header) |
| `stage` | string | One of: `research`, `plan`, `gap-check`, `clarify`, `preview`, `execute` |

**Behaviour:** Loads the stage skill bundle and directs the agent to read/write `ps-migration/{framework}-{from}-to-{to}/` files.

---

### `resume_migration`

Resume a file-state migration from an existing `ps-migration/` folder.

**Parameters**

| Name | Type | Description |
|---|---|---|
| `migration_folder` | string | Path to `ps-migration/{framework}-{from}-to-{to}/` |
| `stage` | string | Stage to resume: `research`, `plan`, `gap-check`, `clarify`, `preview`, or `execute` (default: `execute`) |

**Behaviour:** Loads the stage skill and directs the agent to read `research.md` (optional), `plan.md`, `tasks.md`, `verification.md`. For execute, picks up from the first `Status: pending` task.

---

### `migration_workflow_prompt`

Zero-parameter fallback for clients that do not support parameterised prompts.

**Behaviour:** Directs the agent to load `skill://framework-migration-plan/main` and run the six-stage sequence: research (optional) → plan → gap-check → clarify (optional) → preview (optional) → execute.

---
## Skill Resources

Skill resources are Markdown files registered as MCP resources under the `skill://` URI scheme. Load them at session start via the split `skill://framework-migration-*/` URIs or through the `start_migration` / `resume_migration` prompts.

---

### `skill://framework-migration-research/main`

**File:** `migration_oracle/mcp/skills/framework-migration/research.md`

Research stage — optional knowledge-query checkpoint that emits `research.md`.

---

### `skill://framework-migration-plan/main`

**File:** `migration_oracle/mcp/skills/framework-migration/plan.md`

Plan stage — codebase scan, full escalation-chain graph queries, file emission.

---

### `skill://framework-migration-gap-check/main`

**File:** `migration_oracle/mcp/skills/framework-migration/gap-check.md`

Gap-check stage — file-only mechanical audit of plan.md and tasks.md.

---

### `skill://framework-migration-clarify/main`

**File:** `migration_oracle/mcp/skills/framework-migration/clarify.md`

Clarify stage — file-only Relevance-Index resolution in tasks.md.

---

### `skill://framework-migration-preview/main`

**File:** `migration_oracle/mcp/skills/framework-migration/preview.md`

Preview stage — read-only plan rendering grouped by risk.

---

### `skill://framework-migration-execute/main`

**File:** `migration_oracle/mcp/skills/framework-migration/execute.md`

Execute stage — sequential task execution, verification gate.

Operator guide: [instruction.md](../04-operator-guides/instruction.md).

---

### `skill://framework-migration-plan/scanning`

**File:** `migration_oracle/mcp/skills/framework-migration/scanning.md`

Codebase scanning patterns for entity extraction (plan and research stages).

---

### `skill://framework-migration-plan/version-map`

**File:** `migration_oracle/mcp/skills/framework-migration/version-map.md`

Framework version catalogue, toolchain gates, and detection heuristics.

---

### `skill://framework-migration-execute/rollback`

**File:** `migration_oracle/mcp/skills/framework-migration/rollback.md`

Five-step revert procedure — updates Status in tasks.md (file-state; no graph session tools).

---

## Tool Index

| Tool | Stage | Purpose |
|---|---|---|
| `check_version_availability` | plan | Resolve and validate framework versions |
| `analyze_upgrade_path` | plan | Rules + lifecycle alerts for version range |
| `resolve_deprecation` | plan, execute | Single-hop deprecation lookup |
| `entity_evolution` | plan, execute | Multi-hop replacement chain |
| `search_migration_knowledge` | plan, execute | Hybrid BM25+vector search fallback |
| `search_openrewrite_recipes` | plan, execute | Recipe discovery |
| `resolve_paysafe_dependency_by_service_name` | plan | Internal Paysafe dep resolution |
| `build_recipe_plan` | plan, execute | Auto/manual track plan |
| `submit_migration_insight` | — | Write community knowledge (user-initiated) |
| `get_community_insights` | — | Read community rules |
| `vote_insight` / `verify_insight` | — | Community moderation |
| `list_pipeline_runs` / `get_artifact_content` | plan | Pipeline artifact access |
| `get_graph_schema` / `execute_custom_cypher` | plan, execute | Schema introspection |
| `install_migration_skill` | all | Install skill bundles to consumer repo |

**Removed (017):** Seven session-state tools deleted — see spec 017 for details.

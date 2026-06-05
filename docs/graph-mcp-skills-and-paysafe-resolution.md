# Migration Knowledge Graph, MCP Tools, Skills, and Paysafe Resolution
 
This document explains the **Neo4j/Memgraph knowledge graph** that stores framework migration data, every **MCP tool** exposed by the Paysafe Migration Oracle server (parameters, return shapes, and Cypher queries), the **skill resources** agents can load, and how **Paysafe internal dependency resolution** works end to end.
 
Nothing here references internal source layout — only behavior, data shapes, and operational contracts.
 
---
 
## Table of contents
 
1. [System overview](#system-overview)
2. [Graph database connection](#graph-database-connection)
3. [Graph structure](#graph-structure)
4. [Indexes and search infrastructure](#indexes-and-search-infrastructure)
5. [How data enters the graph](#how-data-enters-the-graph)
6. [MCP server overview](#mcp-server-overview)
7. [MCP tools — primary server (v2)](#mcp-tools--primary-server-v2)
8. [MCP tools — legacy granular server](#mcp-tools--legacy-granular-server)
9. [MCP resources (skills)](#mcp-resources-skills)
10. [MCP prompts](#mcp-prompts)
11. [Paysafe service resolution](#paysafe-service-resolution)
12. [Related agent skills (non-MCP)](#related-agent-skills-non-mcp)
13. [Environment variables](#environment-variables)
14. [Tool selection guide](#tool-selection-guide)
---
 
## System overview
 
The migration knowledge graph is a **property graph database** (Neo4j or Memgraph) populated from official release notes, LLM-extracted entities, community submissions, and optional OpenRewrite recipe mappings. An **MCP (Model Context Protocol) server** named **PaysafeMigrationOracle** exposes read tools so AI agents can:
 
- Plan Spring Boot or Angular upgrades between two versions
- Look up deprecations, entity evolution, and hybrid-search migration guidance
- Build OpenRewrite automation plans
- Resolve Paysafe-internal library versions against FindIt and GitLab
- Submit and query community migration insights
```
┌─────────────────────┐     Bolt (7687)      ┌──────────────────────────────┐
│  AI Agent (Cursor,  │ ◄──────────────────► │  Neo4j / Memgraph            │
│  Claude, etc.)      │                        │  Version, MigrationRule,     │
└─────────┬───────────┘                        │  Class, Property, Dependency,│
          │ MCP (stdio/SSE/HTTP)                 │  OpenRewriteRecipe, …        │
          ▼                                      └──────────────────────────────┘
┌─────────────────────┐
│ PaysafeMigration    │──────► FindIt API (service registry)
│ Oracle MCP Server   │──────► GitLab (git tags + build files)
└─────────────────────┘
```
 
Two MCP server implementations exist:
 
| Server | Role | Tool count |
|--------|------|------------|
| **Primary (v2)** | Default entry point; rich upgrade analysis, hybrid search, recipe plans | 15+ tools |
| **Legacy** | Granular JSON graph queries; superseded for most agent workflows | 12 graph tools + community + Paysafe |
 
The CLI entry point launches the **primary v2** server. Some IDE MCP configurations expose only a **subset of seven tools**; the full v2 server registers additional tools (recipe plan builder, OpenRewrite search, entity evolution, community CRUD).
 
---
 
## Graph database connection
 
| Setting | Default | Purpose |
|---------|---------|---------|
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt connection string |
| `NEO4J_USER` | (empty) | Username; empty means no auth |
| `NEO4J_PASSWORD` | (empty) | Password |
 
The server verifies connectivity at startup with `RETURN 1`. Memgraph may not support all index DDL; hybrid search degrades gracefully when indexes are missing.
 
**Property naming convention:** all node properties use **camelCase** (e.g. `sortableVersion`, `ruleType`, `sourceUrl`).
 
---
 
## Graph structure
 
### Design intent
 
The graph answers: *"What changed between framework version A and B, what does it affect, and how do I migrate?"* It links:
 
- **Releases** (`Version` nodes)
- **Documented changes** (`MigrationRule` nodes)
- **Affected artifacts** (`Class`, `ApplicationProperty`, `Dependency`)
- **Lifecycle events** (deprecated / removed / introduced in a release)
- **Replacement chains** (old entity → new entity)
- **Community workarounds** (`CommunityInsight`)
- **Automation** (`OpenRewriteRecipe` linked via `AUTOMATED_BY`)
WildFly and other JBoss-ecosystem frameworks are stored with the same schema; MCP query tools currently filter to **Spring Boot** or **Angular** only.
 
---
 
### Node labels and properties
 
#### Version
 
One node per framework release.
 
| Property | Type | Meaning |
|----------|------|---------|
| `framework` | string | Display name, e.g. `Spring Boot`, `Angular`, `WildFly` |
| `version` | string | Semantic version, e.g. `3.4.0` |
| `sortableVersion` | integer | Monotonic ordering key (see [Sortable version encoding](#sortable-version-encoding)) |
| `stabilityLevel` | string (optional) | WildFly only: `experimental`, `preview`, `community`, `default` |
 
**Identity:** composite of `framework` + `version`.
 
#### MigrationRule
 
One node per documented change item in a release.
 
| Property | Type | Meaning |
|----------|------|---------|
| `statement` | string | Original changelog / release-note text |
| `ruleType` | string | `breaking`, `potential_breaking`, `deprecation`, `behavioral`, `dependency_upgrade`, `mandatory_migration` |
| `sourceUrl` | string | Citation URL (GitHub release, Jira, docs) |
| `actionStep` | string | LLM-extracted migration instruction |
| `changeType` | string | Semantic change type from entity extraction |
| `reasonType` | string | Why the change happened (security, deprecation_cleanup, etc.) |
| `reason` | string | Explanation text |
| `entityClassification` | string | `actionable`, `incomplete`, or `informational` (null on older data) |
| `cliOperation` | string (optional) | WildFly CLI fragment |
| `subsystem` | string (optional) | WildFly subsystem name |
| `embedding` | float[] (optional) | 768-dim vector for semantic search |
 
**Classification at write time:**
 
| Tier | Condition |
|------|-----------|
| `actionable` | Has a non-empty `actionStep` |
| `incomplete` | Has affected artifacts but no action step |
| `informational` | Has reason only |
| *(discarded)* | Empty shell — not written to graph |
 
#### CommunityInsight
 
User- or blog-submitted migration workarounds.
 
| Property | Type | Meaning |
|----------|------|---------|
| `statement` | string | Insight text (10–2000 characters) |
| `solution` | string | Workaround or fix |
| `sourceUrl` | string | Evidence URL |
| `submittedBy` | string | Submitter identifier |
| `createdAt` | string | ISO timestamp |
| `confidence` | float | 0–1 (default 0.5) |
| `votes` | integer | Net vote count |
| `verified` | boolean | Moderator verified |
| `embedding` | float[] (optional) | Same model as MigrationRule |
 
#### ApplicationProperty
 
| Property | Meaning |
|----------|---------|
| `name` | Full dotted key, e.g. `spring.datasource.url` |
 
#### Class
 
| Property | Meaning |
|----------|---------|
| `name` | Simple name or fully qualified class name |
 
#### Dependency
 
| Property | Meaning |
|----------|---------|
| `name` | Maven artifact id, npm package name, or `groupId:artifactId` |
 
#### OpenRewriteRecipe
 
Populated by a separate OpenRewrite ingestion pipeline (not part of every deployment).
 
| Property | Meaning |
|----------|---------|
| `recipeId` | Fully qualified recipe id |
| `displayName` | Human-readable name |
| `description` | Recipe narrative |
| `groupId`, `artifactId`, `artifactVersion` | Maven coordinates |
| `isComposite` | Boolean — recipe chains other recipes |
| `tags` | String list |
| `parameterSchema` | Parameter schema snippet |
| `hasRequiredParams` | Boolean |
| `sourceFile` | Source YAML path inside rewrite JAR |
| `embedding` | float[] (optional) |
 
---
 
### Relationship types
 
| Relationship | Direction | Meaning |
|--------------|-----------|---------|
| `INCLUDES_RULE` | Version → MigrationRule | Rule belongs to a release |
| `DISCOVERED_IN` | CommunityInsight → Version | Insight tied to a release |
| `SUPERSEDES` | Version → Version | One release supersedes another (e.g. JBoss EAP over WildFly base) |
| `AFFECTS_PROPERTY` | Rule/Insight → ApplicationProperty | Rule references a config property |
| `AFFECTS_CLASS` | Rule/Insight → Class | Rule references a Java/TS class |
| `AFFECTS_DEPENDENCY` | Rule/Insight → Dependency | Rule references a dependency |
| `AFFECTED_IN` | Entity → Rule/Insight | Inverse of the three `AFFECTS_*` edges |
| `REPLACED_BY` | Entity → Entity | Replacement chain (same label type) |
| `DEPRECATED_IN` | Entity → Version | Entity deprecated in that release |
| `REMOVED_IN` | Entity → Version | Entity removed in that release |
| `INTRODUCED_IN` | Entity → Version | Entity introduced in that release |
| `DEPRECATES` | Version → Entity | Inverse of `DEPRECATED_IN` |
| `REMOVES` | Version → Entity | Inverse of `REMOVED_IN` |
| `INTRODUCES` | Version → Entity | Inverse of `INTRODUCED_IN` |
| `COMPOSED_OF` | OpenRewriteRecipe → OpenRewriteRecipe | Composite → child recipes |
| `AUTOMATED_BY` | MigrationRule/CommunityInsight → OpenRewriteRecipe | Recipe automates this rule |
| `AUTOMATES` | OpenRewriteRecipe → Rule/Insight | Inverse of `AUTOMATED_BY` |
| `TARGETS_VERSION` | OpenRewriteRecipe → Version | Recipe targets a framework version (optional) |
 
**Lifecycle edge selection at populate time:**
 
| Condition | Edge created |
|-----------|--------------|
| Rule type `breaking` or change type contains `remov` | `REMOVED_IN` / `REMOVES` |
| Rule type `deprecation` or change type contains `deprecat` | `DEPRECATED_IN` / `DEPRECATES` |
| Change type contains `add` or `introduc` | `INTRODUCED_IN` / `INTRODUCES` |
 
If both deprecation and removal apply, **removal wins**.
 
**`AUTOMATED_BY` edge properties** (when rule–recipe mapping has run):
 
`method`, `confidence`, `auto`, `signals`, `reasoning`, `model`, `promptVersion`, `parameterSource`, `parameters` (JSON string), `parameterBindings`, `missingRequiredParams`, `hasRequiredParams`, `blockedReason`, `verifiedBy`, `createdAt`, `updatedAt`
 
---
 
### Entity-relationship diagram
 
```
                    SUPERSEDES
Version ─────────────────────────────► Version
   │
   │ INCLUDES_RULE
   ▼
MigrationRule ──AFFECTS_PROPERTY──► ApplicationProperty
   │              AFFECTS_CLASS ───► Class
   │              AFFECTS_DEPENDENCY► Dependency
   │
   │ AUTOMATED_BY (optional)
   ▼
OpenRewriteRecipe ──COMPOSED_OF──► OpenRewriteRecipe
 
ApplicationProperty / Class / Dependency:
   ──AFFECTED_IN──► MigrationRule | CommunityInsight
   ──REPLACED_BY──► same-type entity
   ──DEPRECATED_IN | REMOVED_IN | INTRODUCED_IN──► Version
   ◄──DEPRECATES | REMOVES | INTRODUCES── Version
 
CommunityInsight ──DISCOVERED_IN──► Version
                 (same AFFECTS_* / AFFECTED_IN pattern as MigrationRule)
```
 
---
 
### Sortable version encoding
 
Version range queries use an integer `sortableVersion` on each `Version` node:
 
```
sortableVersion = major × 1_000_000 + minor × 1_000 + patch
```
 
Examples:
 
| Version | sortableVersion |
|---------|-----------------|
| 3.5.6 | 3_005_006 |
| 4.0.5 | 4_000_005 |
| 17.3.0 | 17_003_000 |
 
Pre-release suffixes (e.g. `-M1`) do not change the integer; they affect lexicographic ordering elsewhere.
 
**Range semantics:** `(current, target]` — strictly greater than current sortable, less than or equal to target sortable.
 
> **Note:** Some skill reference material uses an older formula (`major × 100_000 + minor × 1_000 + patch`). The graph and MCP tools use the **1_000_000 multiplier** above.
 
---
 
## Indexes and search infrastructure
 
Indexes are ensured at MCP server startup.
 
### Full-text indexes (Neo4j 5+ / Lucene BM25)
 
| Index name | Labels | Properties searched |
|------------|--------|---------------------|
| `migration_text` | MigrationRule, CommunityInsight | `statement`, `reason`, `solution` |
| `openrewrite_recipe_description` | OpenRewriteRecipe | `description` |
 
### Vector indexes (cosine similarity)
 
| Index name | Label | Property | Dimensions |
|------------|-------|----------|------------|
| `migration_knowledge_vector_mr` | MigrationRule | `embedding` | 768 |
| `migration_knowledge_vector_ci` | CommunityInsight | `embedding` | 768 |
| `openrewrite_recipe_vector` | OpenRewriteRecipe | `embedding` | 768 |
 
Embedding model: SentenceTransformer **`all-mpnet-base-v2`** (configurable via `SENTENCE_TRANSFORMERS_MODEL`).
 
### B-tree / property index
 
| Index name | Label | Property |
|------------|-------|----------|
| `openrewrite_recipe_id` | OpenRewriteRecipe | `recipeId` |
 
### Hybrid search algorithm
 
Tools that search by natural language (`search_migration_knowledge`, `search_openrewrite_recipes`) combine:
 
1. **Full-text BM25** from the relevant FTS index
2. **Vector cosine similarity** from the relevant vector index(es)
3. **Reciprocal Rank Fusion (RRF)** with default `k = 60` to merge ranked lists
Default tuning:
 
| Parameter | Default | Meaning |
|-----------|---------|---------|
| `top_k_per_index` | 50 | Candidates retrieved per index before fusion |
| `min_vector_similarity` | 0.30 | Cosine floor for vector hits |
| `max_results` | 5 | Final results returned to caller |
 
Lucene reserved characters in queries (dots, colons in FQCNs) are escaped automatically.
 
---
 
## How data enters the graph
 
### Population pipeline (official rules)
 
1. **Extract** documented changes from release notes (per framework)
2. **LLM entity extraction** — structured fields: classes, properties, dependencies, action steps
3. **Classify** each rule as actionable / incomplete / informational (discard empty shells)
4. **Write** Version + MigrationRule + entity nodes + lifecycle edges
5. **Optional:** compute and store `embedding` vectors on rules
Idempotency: if a `Version` node already exists for `(framework, version)`, the populate step skips writing.
 
### Precomputed entities path
 
The whole-version pipeline can pass **precomputed entity dicts** directly (skipping per-rule LLM during graph write). This is used when entities JSON was produced upstream.
 
### Community insights
 
Submitted via MCP `submit_migration_insight` or batch ingestion. Creates `CommunityInsight` linked to a `Version`, merges affected entities, optionally embeds.
 
### OpenRewrite recipes and rule mapping
 
Separate batch jobs ingest OpenRewrite recipe metadata and optionally run an LLM/deterministic judge to create `AUTOMATED_BY` edges with parameter bindings. Environments without this data still work — recipe joins simply return empty.
 
---
 
## MCP server overview
 
| Attribute | Value |
|-----------|-------|
| Server name | `PaysafeMigrationOracle` |
| Transport | `stdio` (default), `sse`, or `streamable-http` via `MCP_TRANSPORT` |
| Host / port | `MCP_HOST` (default `0.0.0.0`), `MCP_PORT` (default `8001`) for HTTP transports |
| Framework enum in tools | `"Spring Boot"` or `"Angular"` |
| Graph write via MCP | **No** — all graph mutation tools are read-only except community insight submission |
 
---
 
## MCP tools — primary server (v2)
 
### 1. `analyze_upgrade_path`
 
**Description:** Returns lifecycle alerts, migration rules, and optional OpenRewrite recipe metadata for a framework upgrade between two versions. Results are ordered chronologically and scoped to the specified framework. When `user_entities` is provided, only rules and lifecycle events affecting at least one listed entity are returned.
 
**When to use:** Plan or scope an upgrade; understand what breaks between two versions; generate a checklist for known classes/properties/dependencies.
 
**When NOT to use:** Single-entity lookup → `resolve_deprecation`; symptom without version context → `search_migration_knowledge`; find automation recipe → `search_openrewrite_recipes`.
 
#### Parameters
 
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `current_version` | string | yes | — | Start version, e.g. `3.5.6` |
| `target_version` | string | yes | — | End version (inclusive), e.g. `4.0.5` |
| `framework` | `"Spring Boot"` \| `"Angular"` | no | `"Spring Boot"` | Framework filter |
| `user_entities` | string[] \| null | no | `null` / `[]` | Class names, property keys, or dependency ids for substring filtering |
| `format` | `"markdown"` \| `"json"` | no | `"markdown"` | Output format |
| `classification` | `actionable` \| `incomplete` \| `informational`[] | no | `["actionable","incomplete"]` | Filter by `entityClassification` |
| `include_recipes` | boolean | no | `true` | Join `AUTOMATED_BY` recipe metadata |
| `include_lifecycle` | boolean | no | `false` | Include raw lifecycle event stream |
| `top_n` | integer \| null | no | `null` | Cap rules after sort |
| `verbose` | boolean | no | `false` | Include `sourceUrl` in JSON output |
 
#### Return type
 
- **`format="markdown"`:** string — human-readable report grouped by release version
- **`format="json"`:** string containing JSON:
```json
{
  "framework": "Spring Boot",
  "from": "3.5.6",
  "to": "4.0.5",
  "from_sortable": 3005006,
  "to_sortable": 4000005,
  "versions": [
    {
      "version": "4.0.0",
      "rules": [
        {
          "rule_type": "MigrationRule",
          "statement": "...",
          "reason": "...",
          "actionStep": "...",
          "solution": "...",
          "changeType": "...",
          "reasonType": "...",
          "entityClassification": "actionable",
          "affected_entities": ["WebSecurityConfigurerAdapter"],
          "recipes": [
            {
              "recipeId": "org.openrewrite...",
              "displayName": "...",
              "auto": true,
              "confidence": 0.92,
              "parameters": {},
              "missingRequiredParams": [],
              "blockedReason": ""
            }
          ],
          "sourceUrl": "..."
        }
      ],
      "lifecycle_events": []
    }
  ],
  "summary": {
    "total_rules": 42,
    "auto_applicable": 8,
    "manual": 34
  }
}
```
 
#### Cypher query
 
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
 
OPTIONAL MATCH (v)-[:INCLUDES_RULE|DISCOVERED_IN]-(rule)
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)
 
WITH v, raw_lifecycle_events, rule,
     collect(DISTINCT ruleEntity.name) AS affected_entities
 
WHERE rule IS NULL
   OR (
       (size($user_entities) = 0
          OR ANY(e IN affected_entities
                   WHERE ANY(u IN $user_entities
                              WHERE toLower(e) CONTAINS toLower(u))))
       AND
       (rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )
 
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
WITH v, raw_lifecycle_events, rule, affected_entities,
     collect(DISTINCT {
         recipeId: rec.recipeId,
         displayName: rec.displayName,
         groupId: rec.groupId,
         artifactId: rec.artifactId,
         artifactVersion: rec.artifactVersion,
         auto: ab.auto,
         confidence: ab.confidence,
         parameters: ab.parameters,
         missingRequiredParams: ab.missingRequiredParams,
         blockedReason: ab.blockedReason
     }) AS recipes
 
WITH v, raw_lifecycle_events, collect(DISTINCT {
    rule_type: labels(rule)[0],
    statement: rule.statement,
    actionStep: rule.actionStep,
    sourceUrl: rule.sourceUrl,
    reason: rule.reason,
    solution: rule.solution,
    changeType: rule.changeType,
    reasonType: rule.reasonType,
    entityClassification: rule.entityClassification,
    affected_entities: affected_entities,
    recipes: recipes
}) AS raw_rules
 
RETURN
    v.version AS release_version,
    v.sortableVersion AS release_sortable,
    [x IN raw_rules WHERE x.statement IS NOT NULL] AS rules,
    [x IN raw_lifecycle_events WHERE x.event_type IS NOT NULL] AS lifecycle_events
ORDER BY v.sortableVersion ASC
```
 
---
 
### 2. `build_recipe_plan`
 
**Description:** Builds a two-track migration plan — **auto track** (OpenRewrite `rewrite.yml`) and **manual track** (blocked rules needing human review).
 
**When to use:** Turn graph data into an executable OpenRewrite plan after version range and entity list are known.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `current_version` | string | yes | — |
| `target_version` | string | yes | — |
| `framework` | `"Spring Boot"` \| `"Angular"` | no | `"Spring Boot"` |
| `user_entities` | string[] \| null | no | `null` |
| `auto_only` | boolean | no | `false` |
| `classification` | string[] | no | `["actionable","incomplete"]` |
 
#### Return type
 
Structured JSON object:
 
```json
{
  "framework": "Spring Boot",
  "from": "3.5.6",
  "to": "4.0.5",
  "summary": {
    "total_rules": 42,
    "auto_track_size": 8,
    "manual_track_size": 34
  },
  "auto_track": {
    "rewrite_yml": "...(YAML string)...",
    "recipes": [
      {
        "recipeId": "org.openrewrite...",
        "displayName": "...",
        "parameters": {},
        "confidence": 0.92,
        "rules_covered": ["..."],
        "concern": "SECURITY",
        "risk": "HIGH",
        "version": "4.0.0"
      }
    ]
  },
  "manual_track": [
    {
      "rule_id": "...",
      "version": "4.0.0",
      "statement": "...",
      "actionStep": "...",
      "concern": "PERSISTENCE",
      "risk": "MEDIUM",
      "blocked_reason": "no_recipe_linked",
      "affected_entities": ["..."],
      "candidate_recipes": []
    }
  ]
}
```
 
Omit `manual_track` when `auto_only=true`.
 
#### Cypher query
 
```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable
 
MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification
 
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)
WITH v, rule, collect(DISTINCT ruleEntity.name) AS affected_entities
WHERE size($user_entities) = 0
   OR ANY(e IN affected_entities
            WHERE ANY(u IN $user_entities
                       WHERE toLower(e) CONTAINS toLower(u)))
 
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
WITH v, rule, affected_entities,
     collect({
         recipeId: rec.recipeId,
         displayName: rec.displayName,
         groupId: rec.groupId,
         artifactId: rec.artifactId,
         artifactVersion: rec.artifactVersion,
         auto: ab.auto,
         confidence: ab.confidence,
         parameters: ab.parameters,
         missingRequiredParams: ab.missingRequiredParams,
         hasRequiredParams: ab.hasRequiredParams,
         blockedReason: ab.blockedReason
     }) AS recipes
 
RETURN
    elementId(rule) AS rule_id,
    rule.statement AS statement,
    rule.actionStep AS actionStep,
    rule.solution AS solution,
    rule.changeType AS changeType,
    rule.reasonType AS reasonType,
    rule.entityClassification AS entityClassification,
    v.version AS version,
    v.sortableVersion AS sortable_version,
    affected_entities,
    recipes
ORDER BY v.sortableVersion ASC
```
 
Post-processing selects the best `auto=true` recipe per rule (highest confidence, no missing required params) and assembles `rewrite.yml`.
 
---
 
### 3. `resolve_deprecation`
 
**Description:** Full deprecation lifecycle for a single class, application property, or dependency: deprecated in, removed in, replaced by (one hop), and all related rules/insights.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity_name` | string | yes | — |
| `framework` | `"Spring Boot"` \| `"Angular"` | no | `"Spring Boot"` |
 
**Entity name forms:** FQCN, simple class name, property key, or artifact id. Matching is **exact**.
 
#### Return type
 
Markdown string — deprecation card, or `"No deprecation records found..."` if missing.
 
#### Cypher query
 
```cypher
MATCH (e)
WHERE (e:Class OR e:ApplicationProperty OR e:Dependency) AND e.name = $entity_name
 
OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REMOVED_IN]->(remV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REPLACED_BY]->(replacement)
 
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE (rule:MigrationRule OR rule:CommunityInsight)
  AND EXISTS { (rule)-[:INCLUDES_RULE|DISCOVERED_IN]-(:Version {framework: $framework}) }
 
RETURN
  labels(e)[0] AS entity_type,
  e.name AS original_entity,
  replacement.name AS replaced_by,
  depV.version AS deprecated_in,
  remV.version AS removed_in,
  collect({
    type: labels(rule)[0],
    statement: rule.statement,
    reason: rule.reason,
    solution: rule.solution
  }) AS rules
```
 
---
 
### 4. `search_migration_knowledge`
 
**Description:** Hybrid search (BM25 + vector + RRF) over migration rules and community insights.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `query` | string | yes | — |
| `framework` | `"Spring Boot"` \| `"Angular"` | no | `"Spring Boot"` |
| `include_community_insights` | boolean | no | `true` |
| `max_results` | integer | no | `5` |
| `rrf_k` | integer | no | `60` |
| `top_k_per_index` | integer | no | `50` |
| `min_vector_similarity` | float | no | `0.30` |
 
#### Return type
 
Markdown string — ranked list with RRF scores, node types, versions, statement/reason/solution.
 
#### Query mechanism
 
**Step 1 — Hybrid retrieval** (not raw Cypher from caller):
 
- FTS index `migration_text` on query text
- Vector indexes `migration_knowledge_vector_mr`, `migration_knowledge_vector_ci` on query embedding
- RRF fusion
**Step 2 — Hydration Cypher:**
 
```cypher
MATCH (n) WHERE id(n) IN $ids
  AND ($include_community_insights OR 'MigrationRule' IN labels(n))
MATCH (n)-[:INCLUDES_RULE|DISCOVERED_IN]-(v:Version {framework: $framework})
RETURN id(n)        AS id,
       labels(n)[0] AS type,
       n.statement  AS statement,
       n.reason     AS reason,
       n.solution   AS solution,
       collect(DISTINCT v.version) AS applies_to_versions
```
 
---
 
### 5. `search_openrewrite_recipes`
 
**Description:** Hybrid search over OpenRewrite recipe nodes.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `query` | string | yes | — |
| `max_results` | integer | no | `5` |
| `only_composite` | boolean \| null | no | `null` |
| `require_no_params` | boolean | no | `false` |
| `rrf_k` | integer | no | `60` |
| `top_k_per_index` | integer | no | `50` |
| `min_vector_similarity` | float | no | `0.30` |
 
#### Return type
 
Markdown string — recipe list with coordinates, tags, composite/leaf badge, parameter schema, composition/automation counts.
 
#### Query mechanism
 
**Step 1:** FTS `openrewrite_recipe_description` + vector `openrewrite_recipe_vector` + RRF.
 
**Step 2 — Hydration Cypher:**
 
```cypher
MATCH (r:OpenRewriteRecipe) WHERE id(r) IN $ids
 
CALL {
    WITH r
    MATCH (r)-[:COMPOSED_OF]->(child:OpenRewriteRecipe)
    RETURN count(child) AS composed_of_count
}
 
CALL {
    WITH r
    MATCH (mr:MigrationRule)-[:AUTOMATED_BY]->(r)
    RETURN count(mr) AS automates_rule_count
}
 
RETURN id(r)               AS id,
    r.recipeId           AS recipe_id,
    r.displayName        AS display_name,
    r.description        AS description,
    r.artifactId         AS artifact_id,
    r.groupId            AS group_id,
    r.artifactVersion    AS artifact_version,
    coalesce(r.isComposite, false)       AS is_composite,
    coalesce(r.tags, [])                 AS tags,
    coalesce(r.hasRequiredParams, false) AS has_required_params,
    r.parameterSchema    AS parameter_schema,
    composed_of_count,
    automates_rule_count
```
 
---
 
### 6. `entity_evolution`
 
**Description:** Traces the full `REPLACED_BY` chain (up to 5 hops) with lifecycle and rules per step.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `entity_name` | string | yes | — |
| `framework` | `"Spring Boot"` \| `"Angular"` | no | `"Spring Boot"` |
 
#### Return type
 
Markdown timeline string.
 
#### Cypher query
 
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
WHERE rule:MigrationRule OR rule:CommunityInsight
 
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
 
### 7. `get_graph_schema`
 
**Description:** Returns the authoritative graph schema document (labels, properties, relationships, indexes, example query patterns).
 
#### Parameters
 
None.
 
#### Return type
 
Markdown string (static content).
 
#### Cypher
 
None.
 
---
 
### 8. `execute_custom_cypher`
 
**Description:** Executes a **read-only** Cypher query for complex questions not covered by standard tools.
 
#### Parameters
 
| Parameter | Type | Required |
|-----------|------|----------|
| `query` | string | yes |
 
#### Return type
 
JSON string — array of result records, or error message.
 
#### Security
 
Blocks: `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, `CALL db`.
 
Uses read session (`default_access_mode="READ"`).
 
---
 
### 9. `resolve_paysafe_dependency_by_service_name`
 
**Description:** Resolves a Paysafe internal library version by FindIt service name. See [Paysafe service resolution](#paysafe-service-resolution).
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `service_name` | string | yes | — |
| `target_version` | string \| null | no | `null` |
| `allow_latest_overall` | boolean | no | `false` |
| `framework` | string | no | `"auto"` |
 
`framework` accepts: `"spring-boot"`, `"angular"`, `"auto"`.
 
#### Return type
 
Structured JSON — success or error (see Paysafe section).
 
#### Cypher
 
None — external FindIt + GitLab only.
 
---
 
### 10. `install_migration_skill`
 
**Description:** Copies the bundled framework-migration skill to Cursor or Claude Code skills directory.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `target` | string | no | `"auto"` |
| `target_dir` | string \| null | no | `null` |
 
`target`: `"cursor"`, `"claude"`, or `"auto"` (detect from environment).
 
#### Return type
 
```json
{
  "status": "ok",
  "target": "cursor",
  "installed_path": "/path/to/framework-migration",
  "files_written": ["SKILL.md", "references/scanning.md", "..."]
}
```
 
---
 
### 11. `submit_migration_insight`
 
**Description:** Submit a community migration insight discovered during a real project migration.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `statement` | string | yes | — |
| `spring_boot_version` | string | yes | — |
| `solution` | string \| null | no | `null` |
| `affected_properties` | string[] \| null | no | `null` |
| `affected_classes` | string[] \| null | no | `null` |
| `affected_dependencies` | string[] \| null | no | `null` |
| `evidence_url` | string \| null | no | `null` |
| `confidence` | float \| null | no | `null` |
| `framework` | string | no | `"Spring Boot"` |
 
`statement`: 10–2000 characters.
 
#### Return type
 
```json
{
  "insight_id": "...",
  "status": "submitted"
}
```
 
Or `"duplicate"` if near-duplicate exists.
 
#### Cypher (conceptual)
 
Creates `CommunityInsight`, links to `Version`, merges affected entity nodes, optionally sets embedding.
 
---
 
### 12. `get_community_insights`
 
**Description:** Query community-submitted insights with optional filters.
 
#### Parameters
 
| Parameter | Type | Required | Default |
|-----------|------|----------|---------|
| `from_version` | string \| null | no | `null` |
| `to_version` | string \| null | no | `null` |
| `entity_name` | string \| null | no | `null` |
| `entity_type` | string \| null | no | `null` |
| `verified_only` | boolean | no | `false` |
| `framework` | string | no | `"Spring Boot"` |
 
`entity_type`: `"property"`, `"class"`, or `"dependency"` (requires `entity_name`).
 
#### Return type
 
List of insight dicts: `statement`, `solution`, `version`, `affected_entities`, `votes`, `verified`, `confidence`.
 
---
 
### 13. `vote_insight`
 
**Description:** Upvote or downvote a community insight.
 
#### Parameters
 
| Parameter | Type | Required |
|-----------|------|----------|
| `insight_id` | string | yes |
| `vote_type` | `"up"` \| `"down"` | yes |
 
#### Return type
 
```json
{
  "insight_id": "...",
  "votes": 5,
  "status": "ok"
}
```
 
---
 
### 14. `verify_insight`
 
**Description:** Mark an insight as moderator-verified.
 
#### Parameters
 
| Parameter | Type | Required |
|-----------|------|----------|
| `insight_id` | string | yes |
 
#### Return type
 
```json
{
  "insight_id": "...",
  "verified": true,
  "status": "ok"
}
```
 
---
 
## MCP tools — legacy granular server
 
The legacy server exposes **structured JSON** tools backed by dedicated Cypher in a graph API query module. Each tool wraps a specific query pattern. Use when you need raw structured data rather than markdown reports.
 
| Tool | Purpose | Key parameters |
|------|---------|----------------|
| `get_entities_in_version` | All affected properties/classes/deps in a version range | `from_version`, `to_version`, `framework` |
| `get_versions_with_entity` | Which versions mention a class or property | `entity_name`, `entity_type`, `framework` |
| `get_rules_affecting_property` | Rules for property names | `property_names[]`, version range |
| `get_properties_renamed` | `REPLACED_BY` property pairs in range | version range |
| `get_property_replacement` | Replacement for deprecated properties | `property_name` |
| `get_rules_affecting_class` | Rules for class names | `class_names[]`, version range |
| `get_classes_replaced` | Class replacement pairs in range | version range |
| `get_classes_changed` | Classes with any rule in range | version range |
| `get_dependencies_affected` | Dependency impact grouped by dependency | `dependencies[]`, version range |
| `get_breaking_changes` | Breaking rules + removed entities | version range |
| `get_entities_with_replacements` | All replacement chains | version range |
| `get_deprecated_entities` | Entities with `DEPRECATED_IN` | version range |
| `get_agent_definitions` | Returns markdown agent definition files | none |
 
Community insight and Paysafe tools mirror the primary server.
 
**Representative Cypher** (`get_entities_in_version`):
 
```cypher
MATCH (v:Version)-[:INCLUDES_RULE]->(r:MigrationRule)
WHERE v.framework = $framework
  AND v.sortableVersion > $fromSortable
  AND v.sortableVersion <= $toSortable
OPTIONAL MATCH (r)-[:AFFECTS_PROPERTY]->(p:ApplicationProperty)
OPTIONAL MATCH (r)-[:AFFECTS_CLASS]->(c:Class)
OPTIONAL MATCH (r)-[:AFFECTS_DEPENDENCY]->(d:Dependency)
WITH collect(DISTINCT p.name) AS props,
     collect(DISTINCT c.name) AS classes,
     collect(DISTINCT d.name) AS deps
RETURN [x IN props WHERE x IS NOT NULL] AS properties,
       [x IN classes WHERE x IS NOT NULL] AS classes,
       [x IN deps WHERE x IS NOT NULL] AS dependencies
```
 
---
 
## MCP resources (skills)
 
MCP **resources** (distinct from tools) serve skill markdown content over URIs. Agents fetch these to load procedural knowledge without copying files locally.
 
### Framework migration — core resources
 
| URI | Content |
|-----|---------|
| `skill://framework-migration/main` | Main skill: end-to-end Spring Boot / Angular upgrade workflow (phases 0–4, MCP tool usage, plan vs assistant mode) |
| `skill://framework-migration/scanning` | Codebase scanning reference: bash patterns for classes (FQCN), annotations (simple name), properties (dotted keys), Maven/Gradle deps (`groupId:artifactId`), npm packages |
| `skill://framework-migration/plan-format` | Task schema for plan mode: one task = one file change with before/after, concern, risk, verification steps |
| `skill://framework-migration/version-map` | Version → sortable integer tables for Spring Boot and Angular, boundary warnings (2→3 Java 17, 3→4 Java 21, Angular control flow, etc.) |
 
**Main skill workflow summary:**
 
| Phase | Action |
|-------|--------|
| **0 — Resolve inputs** | `FROM_VERSION`, `TO_VERSION`, `FRAMEWORK`, `MODE` (plan vs assistant) |
| **1 — Scan codebase** | **Mandatory gate:** extract classes, deps, properties → combined entity list. Never call `analyze_upgrade_path` without `user_entities` |
| **2 — Query graph** | `analyze_upgrade_path` → per-entity `resolve_deprecation` → Paysafe resolution → `search_migration_knowledge` for gaps |
| **3 — Synthesize** | Group by concern (SECURITY, PERSISTENCE, WEB, CONFIG, DEPENDENCIES, BUILD, TESTING, OTHER) with risk ratings |
| **4 — Output** | Plan mode → `MIGRATION_PLAN.md`; Assistant mode → structured markdown in chat |
 
**Entity format contract (from scanning resource):**
 
| Entity type | Graph expects |
|-------------|---------------|
| Java/Kotlin class | Full FQCN from import line |
| Annotation | Simple name without `@` |
| Spring property | Full dotted key |
| Maven/Gradle dep | `groupId:artifactId` (no version) |
| npm package | Exact package name |
 
### Execution companion resources
 
These skills run **after** the main skill produces a plan:
 
| URI | Purpose |
|-----|---------|
| `skill://apply-openrewrite-maven/main` | Apply OpenRewrite via Maven plugin using `rewrite.yml` from auto track |
| `skill://apply-openrewrite-gradle/main` | Apply OpenRewrite via Gradle plugin |
| `skill://apply-angular-schematics/main` | Run Angular schematics for automated migrations |
| `skill://run-build-and-test/main` | Build and test verification after migration steps |
| `skill://emit-migration-backlog/main` | Emit remaining manual tasks as backlog items |
| `skill://recipe-task-rollback/main` | Roll back a failed recipe task |
 
---
 
## MCP prompts
 
| Prompt name | Purpose |
|-------------|---------|
| `generate-community-insights` | Workflow for analyzing codebase changes after a migration and preparing community insight submissions |
 
Legacy server also exposes `build_migration_plan` and `build_angular_migration_plan` prompts.
 
---
 
## Paysafe service resolution
 
### Purpose
 
When upgrading a Paysafe application, internal libraries (`com.paysafe.*` Maven coordinates) must be bumped to versions **built against a compatible Spring Boot or Angular version**. The MCP tool **`resolve_paysafe_dependency_by_service_name`** automates:
 
1. FindIt registry lookup (service name → GitLab repo URL)
2. Git tag discovery
3. Build-file parsing at each tag (Spring Boot / Angular version declared)
4. Compatibility selection against target framework version
### End-to-end flow
 
```
service_name
     │
     ▼
┌─────────────────────────┐
│ 1. FindIt API lookup     │  GET https://findit-api.icd.paysafe.cloud/services
│    (cached 30 days)     │  Bearer token: FINDIT_AUTH_TOKEN
└───────────┬─────────────┘
            │ codeRepoLink
            ▼
┌─────────────────────────┐
│ 2. Parse GitLab URL     │  SCP-style git URL for remote operations
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 3. Framework detection  │  auto: probe HEAD for pom.xml, build.gradle(.kts), package.json
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 4. List & sort git tags │  Semantic sort; require parsable version tags
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 5. Per-tag compatibility│  Fetch build file at tag; extract framework version
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ 6. Select best tag      │  latest_compatible | latest_overall | latest_with_known_compatibility
└─────────────────────────┘
```
 
---
 
### Step 1 — FindIt registry lookup
 
| Item | Value |
|------|-------|
| URL | `https://findit-api.icd.paysafe.cloud/services` |
| Method | GET |
| Auth | `FINDIT_AUTH_TOKEN` environment variable as Bearer token |
| Cache | In-memory, 30-day TTL |
| Retries | 2 retries with backoff on timeout/network errors |
 
**Service name matching** (in order):
 
| Step | Method |
|------|--------|
| 1 | Exact match on `name` field |
| 2 | Case-insensitive match |
| 3 | Alphanumeric normalization (strip non-alphanumeric, compare) |
| 4 | Fuzzy match via string similarity — threshold from `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` (default **0.68**) |
 
On fuzzy/case/normalized match, response includes `name_resolution` metadata:
 
```json
{
  "method": "fuzzy",
  "matched_name": "actual-service-name",
  "requested": "typo-servce-name",
  "similarity": 0.82,
  "alternatives": [{"name": "...", "similarity": 0.75}],
  "threshold_used": 0.68
}
```
 
**Extracted field:** `codeRepoLink` (GitLab repository URL).
 
**On failure:** `status: "error"`, `error_code: "service_not_found"`, with up to 12 suggested similar names in `error.details.suggestions`.
 
---
 
### Step 2 — GitLab URL parsing
 
The repository URL is converted to an SCP-style locator suitable for `git ls-remote` and archive fetch operations (e.g. `git@gitlab.com:group/project.git`).
 
---
 
### Step 3 — Framework detection
 
When `framework = "auto"`, probe build files at **HEAD** in order:
 
| File | Detected framework |
|------|-------------------|
| `pom.xml` | spring-boot (Maven) |
| `build.gradle` / `build.gradle.kts` | spring-boot (Gradle) |
| `package.json` | angular |
 
Explicit values: `"spring-boot"` or `"angular"`.
 
---
 
### Step 4 — Tag discovery
 
- List remote git tags via git client (with configurable timeout and retries)
- Parse and sort tags semantically (supports formats like `3.5.10`, `3.5.10.A`)
- Filter to parsable version tags
**On failure:** `error_code: "no_tags_found"`.
 
---
 
### Step 5 — Compatibility detection (per tag)
 
For each candidate tag, fetch the build file and extract the declared framework version:
 
| Framework | Files tried | Version extracted from |
|-----------|-------------|------------------------|
| spring-boot | `pom.xml`, `build.gradle`, `build.gradle.kts` | Spring Boot parent POM, `spring-boot.version` property, or Gradle plugin version |
| angular | `package.json` | `@angular/core` in dependencies or devDependencies |
 
Returns a compatibility object:
 
```json
{
  "framework_version": "3.5.10",
  "source_file": "pom.xml",
  "source_precedence": "spring-boot-starter-parent"
}
```
 
Build files are fetched via git archive at the specific tag ref.
 
---
 
### Step 6 — Compatibility rule
 
A tag's declared framework version is **compatible** with the target when:
 
1. **Same major version** as target
2. Declared version **≥ target** at major.minor.patch tuple level
Examples:
 
| Tag declares | Target | Compatible? |
|--------------|--------|-------------|
| Spring Boot 3.5.10 | 3.5.6 | Yes |
| Spring Boot 3.4.0 | 3.5.6 | No (minor too low) |
| Spring Boot 2.7.18 | 3.5.6 | No (major mismatch) |
| Angular 18.2.0 | 18.0.0 | Yes |
 
---
 
### Step 7 — Selection strategy
 
| Condition | Strategy | Behavior |
|-----------|----------|----------|
| No `target_version`, `allow_latest_overall=true` | `latest_overall` | Newest parsable tag; no compatibility check |
| No `target_version`, need known compat | `latest_with_known_compatibility` | Newest tag with readable framework version in build file |
| `target_version` set, compatible tag found | `latest_compatible` | Newest tag whose declared version is compatible |
| `target_version` set, none compatible, `allow_latest_overall=true` | `latest_overall` | Falls back to newest tag anyway |
| `target_version` set, none compatible, `allow_latest_overall=false` | error | `no_compatible_version` |
 
**Important:** When `target_version` is omitted, the MCP layer internally forces `allow_latest_overall=true`.
 
---
 
### Success response shape
 
```json
{
  "status": "ok",
  "service_name": "resolved-findit-name",
  "code_repo_link": "https://gitlab.com/paysafe/...",
  "framework": "spring-boot",
  "framework_version": "3.5.10",
  "selected_tag": "3.5.10.A",
  "selected_version": "3.5.10",
  "target_version": "3.5.6",
  "compatibility": {
    "framework_version": "3.5.10",
    "source_file": "pom.xml",
    "source_precedence": "spring-boot-starter-parent"
  },
  "selection_strategy": "latest_compatible",
  "effective_settings": {
    "max_tags_returned": 100,
    "git_timeout_seconds": 30,
    "retries": 2,
    "backoff_seconds": [1.0, 3.0]
  },
  "name_resolution": {
    "method": "fuzzy",
    "matched_name": "...",
    "similarity": 0.82
  }
}
```
 
`name_resolution` is present only when the FindIt match was not exact.
 
---
 
### Error response shape
 
```json
{
  "status": "error",
  "error": {
    "type": "NotFoundError",
    "message": "No service found matching '...'",
    "recoverable": false,
    "error_code": "service_not_found",
    "actionable_hint": "Closest name in registry: 'foo-service' (similarity 0.71). Use that exact name.",
    "details": {
      "service_name": "...",
      "suggestions": [{"name": "...", "similarity": 0.71}],
      "name_resolution": {"method": "none", "requested": "..."}
    }
  }
}
```
 
**Error codes:**
 
| Code | Meaning |
|------|---------|
| `invalid_service_name` | Empty service name |
| `service_not_found` | No FindIt match above fuzzy threshold |
| `no_repo_url` | Service found but no `codeRepoLink` |
| `no_tags_found` | Git repo has no tags |
| `no_compatible_version` | No tag compatible with target (and fallback disabled) |
| `compatibility_unknown` | No build file with framework version found in any tag |
| `http_timeout` / `http_request_failed` | FindIt or git network failure |
 
---
 
### Integration with framework migration workflow
 
The framework migration skill instructs agents to:
 
1. Scan build files for dependencies with `groupId` starting with `com.paysafe`
2. Pass the Maven **`artifactId`** as `service_name` (FindIt indexes by service name, not coordinates)
3. Call with `target_version = TO_VERSION`, `allow_latest_overall = true`, `framework = "auto"`
4. Map results to risk levels:
| Outcome | Risk |
|---------|------|
| Compatible tag found | LOW |
| Incompatible but `latest_overall` returned | MEDIUM |
| Null compatibility + latest overall | MEDIUM |
| Fuzzy name match | Bump risk one level |
 
**Status codes for upgrade tables:**
 
| Status | Meaning |
|--------|---------|
| `UPGRADE_AVAILABLE` | Newer compatible version found |
| `ALREADY_COMPATIBLE` | Current version matches or exceeds recommendation |
| `UNVERIFIED` | Latest returned but compatibility unknown |
| `NOT_FOUND` | Service not in FindIt |
| `NO_REPO` | No GitLab URL in registry |
| `BLOCKER` | Resolution failed with no fallback |
 
---
 
## Related agent skills (non-MCP)
 
These skills live in the agent's skill directory and complement the MCP server. They do **not** query the migration graph unless explicitly combined with MCP tools.
 
### Framework migration (primary)
 
**Trigger:** Any mention of upgrading Spring Boot or Angular, version numbers, breaking changes, migration plan, upgrade path.
 
**Requires MCP tools:** `analyze_upgrade_path`, `resolve_deprecation`, `search_migration_knowledge`, `resolve_paysafe_dependency_by_service_name`.
 
**Key rule:** Phase 1 codebase scan is a **mandatory gate** before any MCP call.
 
---
 
### Resolve Paysafe dependencies
 
**Trigger:** Upgrading Paysafe-internal libraries to versions compatible with target Spring Boot.
 
**Workflow:**
 
1. Scan for `com.paysafe` groupId dependencies
2. Lookup by artifactId via **`resolve_paysafe_dependency_by_service_name`** (consolidated tool; older docs may reference split lookup/resolve tools)
3. Produce upgrade table with statuses
**Fallback:** If resolution fails, list recent tags manually and ask user to choose.
 
---
 
### Identify BOM overrides
 
**Trigger:** Analyzing company BOMs, redundant dependency management, cleanup candidates.
 
**Workflow:**
 
1. Locate company BOM (Maven `dependencyManagement` or Gradle `dependencyManagement` block)
2. Find a consuming project that imports the BOM
3. Run `dependencyInsight` / `dependency:tree` to see who wins version resolution
4. Compare against published `spring-boot-dependencies` POM from Maven Central
5. Classify entries as Override, Add-on, or Redundant
**No graph dependency** — pure build-file analysis.
 
---
 
### Spring app properties
 
**Trigger:** Questions about configuration property values per environment (dev, stage, prod, uat).
 
**Workflow:**
 
1. Map environment names to search folders (`aws-dw-ie-dev`, `aws-dw-ie-qa`, etc.)
2. Read `rootProject.name` from Gradle settings as project name
3. Search in priority order: GitLab `oneplatform-properties` repo (if GitLab MCP available), then local `application-<profile>.yml`, `application.yml`, `bootstrap.yml`
4. Report value + source; handle placeholders and encrypted `{cipher}` values
**No graph dependency.**
 
---
 
## Environment variables
 
### Graph database
 
| Variable | Default | Purpose |
|----------|---------|---------|
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt URI |
| `NEO4J_USER` | (empty) | Username |
| `NEO4J_PASSWORD` | (empty) | Password |
 
### MCP server
 
| Variable | Default | Purpose |
|----------|---------|---------|
| `MCP_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `MCP_HOST` | `0.0.0.0` | HTTP bind host |
| `MCP_PORT` | `8001` | HTTP bind port |
| `MCP_STATELESS_HTTP` | false | Stateless HTTP mode for remote clients |
 
### Embeddings
 
| Variable | Default | Purpose |
|----------|---------|---------|
| `SENTENCE_TRANSFORMERS_MODEL` | `all-mpnet-base-v2` | Embedding model |
| `POPULATE_MIGRATION_EMBEDDINGS` | enabled | Set to `0` to skip embedding on populate |
 
### Paysafe / FindIt
 
| Variable | Default | Purpose |
|----------|---------|---------|
| `FINDIT_AUTH_TOKEN` | (embedded fallback) | Bearer token for FindIt API |
| `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` | `0.68` | Minimum similarity for fuzzy service match |
| `GITLAB_API_KEY` | — | GitLab API access for archive operations |
 
---
 
## Tool selection guide
 
| User intent | Recommended tool |
|-------------|------------------|
| "What breaks upgrading 3.5 → 4.0?" | `analyze_upgrade_path` (with scanned `user_entities`) |
| "What replaces WebSecurityConfigurerAdapter?" | `resolve_deprecation` |
| "What's the full replacement chain for X?" | `entity_evolution` |
| "How do I fix circular dependency errors after upgrade?" | `search_migration_knowledge` |
| "Find an OpenRewrite recipe for Jackson 3" | `search_openrewrite_recipes` |
| "Give me a rewrite.yml for this upgrade" | `build_recipe_plan` |
| "What version of paysafe-foo-lib for Spring Boot 3.5?" | `resolve_paysafe_dependency_by_service_name` |
| "Complex multi-hop graph question" | `get_graph_schema` then `execute_custom_cypher` |
| "Install migration skill locally" | `install_migration_skill` |
| "Share a migration workaround we discovered" | `submit_migration_insight` |
 
---
 
## Summary
 
The migration knowledge graph models **releases**, **rules**, **affected entities**, **lifecycle events**, **replacement chains**, **community insights**, and **OpenRewrite automation** as a connected property graph with full-text and vector search indexes.
 
The **PaysafeMigrationOracle** MCP server exposes fifteen primary tools for upgrade analysis, deprecation lookup, hybrid search, recipe planning, custom read-only Cypher, Paysafe dependency resolution, community insight management, and skill installation — plus **eleven MCP skill resources** for procedural migration guidance.
 
**Paysafe service resolution** bridges the FindIt service registry to GitLab tags and build-file compatibility analysis, selecting the newest tag whose declared Spring Boot or Angular version is compatible with the application's target framework version.
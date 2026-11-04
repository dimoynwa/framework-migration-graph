# Spring Boot Version Graph — Schema Overview
 
## Node Types (Classes)
 
| Node | Properties | Description |
|------|------------|-------------|
| **Version** | `framework`, `version`, `sortableVersion` | One node per Spring Boot release (e.g. 3.2.1). `sortableVersion` is an integer for range queries. |
| **MigrationRule** | `statement`, `ruleType`, `sourceUrl`, `actionStep`, `changeType`, `reasonType`, `reason` | A single migration rule from release notes. `ruleType` is from release notes (e.g. breaking, deprecation). `changeType`, `reasonType`, `reason` are LLM-extracted. |
| **CommunityInsight** | `statement`, `solution`, `sourceUrl`, `submittedBy`, `createdAt`, `confidence`, `votes`, `verified` | Community-submitted migration insight (separate from official rules). `votes` and `verified` support moderation. |
| **ApplicationProperty** | `name` | An application property (e.g. `server.port`) mentioned in a rule. |
| **Class** | `name` | A Java class (e.g. `org.springframework.boot.autoconfigure.Foo`) mentioned in a rule. |
| **Dependency** | `name` | A Maven dependency (e.g. `org.springframework.boot:spring-boot-starter`) mentioned in a rule. |
| **OpenRewriteRecipe** | `recipeId`, `displayName`, `description`, `groupId`, `artifactId`, `artifactVersion`, `framework`, `toolType`, `tags`, `sourceFile`, `parameterSchema`, `hasRequiredParams`, `isComposite`, `embedding` | An OpenRewrite recipe that can automate one or more migration rules. `parameterSchema` is JSON-encoded; `framework`/`toolType` distinguish Spring Boot vs Angular schematics. |
 
---
 
## Relationships
 
| Relationship | From → To | Description |
|--------------|-----------|-------------|
| **INCLUDES_RULE** | Version → MigrationRule | Release contains rule |
| **DISCOVERED_IN** | CommunityInsight → Version | Insight discovered in this version |
| **AFFECTS_PROPERTY** | MigrationRule → ApplicationProperty | Rule touches property |
| **AFFECTS_PROPERTY** | CommunityInsight → ApplicationProperty | Insight touches property |
| **AFFECTS_CLASS** | MigrationRule → Class | Rule touches class |
| **AFFECTS_CLASS** | CommunityInsight → Class | Insight touches class |
| **AFFECTS_DEPENDENCY** | MigrationRule → Dependency | Rule touches dependency |
| **AFFECTS_DEPENDENCY** | CommunityInsight → Dependency | Insight touches dependency |
| **REPLACED_BY** | ApplicationProperty → ApplicationProperty | Property replacement |
| **REPLACED_BY** | Class → Class | Class replacement |
| **REPLACED_BY** | Dependency → Dependency | Dependency replacement |
| **DEPRECATED_IN** | Property/Class/Dependency → Version | Entity deprecated |
| **REMOVED_IN** | Property/Class/Dependency → Version | Entity removed |
| **INTRODUCED_IN** | Property/Class/Dependency → Version | Entity introduced |
| **AUTOMATED_BY** | MigrationRule → OpenRewriteRecipe | Rule is (or might be) automated by this recipe — see "AUTOMATED_BY edge schema" below |
| **AUTOMATED_BY** | CommunityInsight → OpenRewriteRecipe | Insight is (or might be) automated by this recipe |
| **AUTOMATES** | OpenRewriteRecipe → MigrationRule \| CommunityInsight | Inverse of AUTOMATED_BY (denormalised for fast traversal from the recipe side) |
| **TARGETS_VERSION** | OpenRewriteRecipe → Version | Recipe targets this specific Version (parsed from recipeId / sourceFile / tags) |
 
---
 
## AUTOMATED_BY edge schema
 
Both `MigrationRule` and `CommunityInsight` nodes link to recipes via `AUTOMATED_BY`. The same edge type is used for **auto-applied** matches and **pending review** matches; an `auto` boolean property distinguishes them.
 
| Property | Type | Description |
|----------|------|-------------|
| `method` | string | `'deterministic'` \| `'llm_judge'` \| `'hybrid'` \| `'manual'` |
| `confidence` | float (0–1) | Final fused confidence score |
| `signals` | list[string] | Human-readable explanation, one entry per signal (e.g. `['rrf=0.022 weight=0.30', 'class_overlap=0.567 weight=0.30 note=exact=WebSecurityConfigurerAdapter']`) |
| `reasoning` | string | Free-text rationale (LLM verdict reasoning when present, comma-joined signal names otherwise) |
| `model` | string \| null | LLM identifier (`'gpt-4o'`, `'qwen-…'`); null for deterministic |
| `promptVersion` | string \| null | Used to invalidate cached LLM verdicts when the prompt changes |
| `auto` | bool | `true` = applied without human review; `false` = staged for review |
| `parameters` | string (JSON) | Bound recipe parameters, ready for `rewrite.yml`. `'{}'` for parameterless recipes |
| `parameterBindings` | list[string] | Per-parameter provenance (e.g. `'oldPropertyKey=spring.foo from rule.affects_property[0] (conf=0.95)'`) |
| `parameterSource` | string | `'deterministic'` \| `'llm'` \| `'mixed'` \| `'none'` |
| `missingRequiredParams` | list[string] | Required params that could not be filled — non-empty forces `auto=false` |
| `hasRequiredParams` | bool | Mirror of the recipe's `hasRequiredParams`, denormalised for review queries |
| `blockedReason` | string | Why a high-confidence match was demoted to `auto=false` (`missing_required=...`, `llm_param_confidence_below_threshold`) |
| `verifiedBy`, `verifiedAt` | string \| datetime | Set by humans; populator never overwrites these |
| `createdAt`, `updatedAt` | datetime | Lifecycle timestamps |
 
### Population methods
 
| Method | When to use | Cost | Provenance |
|--------|-------------|------|------------|
| `deterministic` | CI / dry runs / confident matches | Free (no LLM) | `signals` carries weighted entity-overlap breakdown |
| `llm_judge` | LLM re-rank of hybrid candidates | One LLM call per rule (batched) | `signals` includes `llm_verdict`, `llm_conf`; `evidence` quoted in `reasoning` |
| `hybrid` (default) | Production population | LLM only on uncertain rules | Both signal sets; `confidence = max(determ, llm)` |
| `manual` | Human-curated edges | n/a | `verifiedBy` set by reviewer |
 
### Review queue (pending human review)
 
```cypher
MATCH (src)-[e:AUTOMATED_BY]->(r:OpenRewriteRecipe)
WHERE e.auto = false
RETURN labels(src) AS source_label, src.statement AS statement,
       r.recipeId AS recipe_id, e.method AS method,
       e.confidence AS confidence, e.parameterSource AS param_source,
       e.missingRequiredParams AS missing_params, e.blockedReason AS blocked,
       e.signals AS signals
ORDER BY e.confidence DESC
```
 
To approve an edge during review:
 
```cypher
MATCH (src)-[e:AUTOMATED_BY]->(:OpenRewriteRecipe {recipeId: $recipe_id})
WHERE id(src) = $source_node_id
SET e.auto = true,
    e.verifiedBy = $reviewer,
    e.verifiedAt = datetime()
```
 
The populator's `MERGE` includes a `WHERE e.verifiedBy IS NULL` guard so re-runs **never overwrite verified edges**.
 
---
 
## Structure
 
```
Version (3.2.1)
  ├── INCLUDES_RULE → MigrationRule ("server.port was renamed...")
  │     ├── AFFECTS_PROPERTY → ApplicationProperty (server.port)
  │     │     ├── REPLACED_BY → ApplicationProperty (server.http.port)
  │     │     └── DEPRECATED_IN / REMOVED_IN / INTRODUCED_IN → Version
  │     ├── AFFECTS_CLASS → Class (OldConfig)
  │     │     ├── REPLACED_BY → Class (NewConfig)
  │     │     └── DEPRECATED_IN / REMOVED_IN / INTRODUCED_IN → Version
  │     └── AFFECTS_DEPENDENCY → Dependency (org.springframework:spring-core)
  │           ├── REPLACED_BY → Dependency (new:artifact)
  │           └── DEPRECATED_IN / REMOVED_IN / INTRODUCED_IN → Version
  └── DISCOVERED_IN ← CommunityInsight ("Workaround for X...")
        ├── AFFECTS_PROPERTY → ApplicationProperty
        ├── AFFECTS_CLASS → Class
        └── AFFECTS_DEPENDENCY → Dependency
```
 
---
 
## Data Flow
 
1. **Extraction**: Release notes from GitHub → raw change statements.
2. **Entity extraction**: LLM parses statements → properties, classes, dependencies (including replacements).
3. **Population**: Version and MigrationRule nodes are always created; ApplicationProperty, Class, and Dependency nodes and their relationships are created only when the LLM returns non-empty entity lists. Version-lifecycle relationships (DEPRECATED_IN, REMOVED_IN, INTRODUCED_IN) are derived from `rule_type` and `change_type`.
4. **Community insights**: Users submit insights via `submit_migration_insight` (MCP/REST). CommunityInsight nodes are created separately from MigrationRule; they link to Version via DISCOVERED_IN and to entities via AFFECTS_*. Use `include_community_insights=true` on relevant tools to include them in results.
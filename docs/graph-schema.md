# Neo4j Graph Schema — Paysafe Migration Oracle

This document is the authoritative reference for every node label, relationship type, property, constraint, and index in the Migration Oracle graph database. It also includes query pattern examples and the data-flow rules used during pipeline population.

---

## Table of Contents

1. [Overview](#overview)
2. [Node Labels](#node-labels)
   - [Version](#version)
   - [MigrationRule](#migrationrule)
   - [MigrationStep](#migrationstep)
   - [BreakingScope](#breakingscope)
   - [Class](#class)
   - [ApplicationProperty](#applicationproperty)
   - [Dependency](#dependency)
   - [OpenRewriteRecipe](#openrewriterecipe)
   - [RecipeParam](#recipeparam)
   - [MigrationContext](#migrationcontext)
   - [LifecycleAlert](#lifecyclealert)
3. [Relationship Types](#relationship-types)
4. [Constraints & Indexes](#constraints--indexes)
5. [Data-Flow & Population Rules](#data-flow--population-rules)
6. [Query Pattern Examples](#query-pattern-examples)
7. [Derived Fields](#derived-fields)

---

## Overview

```
(Version)──INCLUDES_RULE──►(MigrationRule)──REQUIRES_STEP──►(MigrationStep)──AUTOMATED_BY──►(OpenRewriteRecipe)
                │                  │                │
                │              HAS_SCOPE        AFFECTS_CLASS / AFFECTS_PROPERTY / AFFECTS_DEPENDENCY
                │                  │                │
     HAS_LIFECYCLE_ALERT       (BreakingScope)  (Class | ApplicationProperty | Dependency)
                │                                   │
         (LifecycleAlert)                      REPLACED_BY / DEPRECATED_IN / REMOVED_IN / INTRODUCED_IN
                                                    │
                                               (Version)

(MigrationContext)──UPGRADES_FROM──►(Version)
(MigrationContext)──UPGRADES_TO────►(Version)
(MigrationContext)──STEP_OUTCOME───►(MigrationStep)
```

The graph models the **knowledge** required to migrate a software project (rules, steps, affected entities, recipes) and the **state** of an ongoing migration session (context, step outcomes).

---

## Node Labels

### Version

Represents a specific release of a framework. It is the root anchor from which all migration knowledge is reachable.

| Property | Type | Required | Description |
|---|---|---|---|
| `framework` | string | yes | Display-form framework name (e.g. `"Spring Boot"`, `"Angular"`, `"WildFly"`) |
| `version` | string | yes | Semantic version string (e.g. `"3.2.0"`, `"3.2"`) |
| `sortableVersion` | integer | yes | `major×1_000_000 + minor×1_000 + patch` — enables fast range queries |
| `rawMdPath` | string | no | Filesystem path to the raw extracted changelog markdown |
| `filteredMdPath` | string | no | Filesystem path to the LLM-filtered markdown |
| `entitiesJsonPath` | string | no | Filesystem path to the extracted entities JSON |
| `fromVersion` | string | no | Source version string when used in a migration run |

**Uniqueness constraint:** `(framework, version)`

**Example:**
```cypher
(:Version {framework: "Spring Boot", version: "3.2.0", sortableVersion: 3002000})
```

---

### MigrationRule

Represents a single documented migration rule extracted from a framework changelog, or a community-submitted insight. It is the central knowledge node.

| Property | Type | Required | Description |
|---|---|---|---|
| `ruleId` | string | yes | Unique identifier. Pipeline rules use `pipeline://{framework}/{version}/{title}`; community rules use element ID |
| `statement` | string | yes | Primary text describing the change. Used for deduplication via BM25 full-text search |
| `ruleType` | string | yes | One of: `"breaking"`, `"deprecation"`, `"behavioral"`, `"mandatory_migration"`, `"community_insight"` |
| `title` | string | no | Short human-readable title |
| `reason` | string | no | Detailed explanation for the change |
| `solution` | string | no | General solution guidance |
| `actionStep` | string | no | Suggested first action |
| `changeType` | string | no | Change classification from the LLM extraction pipeline |
| `reasonType` | string | no | Reason classification from the LLM extraction pipeline |
| `entityClassification` | string | no | One of: `"actionable"`, `"incomplete"`, `"informational"` (see [Derived Fields](#derived-fields)) |
| `subsystem` | string | no | Subsystem or module affected (e.g. `"Security"`, `"Data"`) |
| `sourceUrl` | string | no | Link to upstream documentation |
| `framework` | string | yes | Framework name — denormalised to allow scoped queries without traversing `Version` |
| `jiraKeys` | list[string] | no | Paysafe Jira keys related to this rule |
| `communitySubmittedBy` | string | community only | Author; defaults to `"mcp-agent"` |
| `communityCreatedAt` | string | community only | ISO 8601 creation timestamp |
| `communityConfidence` | float | community only | Confidence score `[0.0, 1.0]`; default `0.5` |
| `communityVotes` | integer | community only | Upvote count; starts at `0` |
| `communityVerified` | boolean | community only | Manual verification flag; default `false` |
| `embedding` | list[float] | no | Sentence-transformer vector (`all-mpnet-base-v2`, 768 dims) for semantic search |

**Uniqueness constraint:** `ruleId`

**Full-text indexes:**
- `rule_statement` on `statement` — duplicate detection and BM25 keyword search
- `migration_text` on `(statement, reason, solution)` — multi-field search

**Vector index:** `migration_knowledge_vector_mr` on `embedding`

**Example:**
```cypher
(:MigrationRule {
  ruleId: "pipeline://Spring Boot/3.2.0/Remove deprecated WebMvcConfigurer adapter",
  statement: "WebMvcConfigurerAdapter has been removed. Implement WebMvcConfigurer directly.",
  ruleType: "breaking",
  framework: "Spring Boot",
  entityClassification: "actionable",
  subsystem: "Web MVC"
})
```

---

### MigrationStep

Represents a discrete, ordered action the developer must take as part of a migration rule. Steps may depend on other steps and may be automated by OpenRewrite recipes.

| Property | Type | Required | Description |
|---|---|---|---|
| `ruleId` | string | yes | Foreign key to the parent `MigrationRule.ruleId` |
| `stepIndex` | integer | yes | Zero-based order within the parent rule |
| `stepType` | string | yes | One of: `"remove"`, `"rename"`, `"replace"`, `"configure"`, `"verify"`, `"namespace"`, `"manual"` |
| `summary` | string | yes | One-line summary of what this step does |
| `instruction` | string | yes | Full instruction text shown to the developer |
| `effort` | string | yes | One of: `"mechanical"`, `"moderate"`, `"architectural"` |
| `automatable` | boolean | yes | Whether an OpenRewrite recipe can fully handle this step |
| `verificationHint` | string | no | How to confirm the step is complete (e.g. compile, run tests) |
| `cliOperation` | string | no | Suggested CLI command (e.g. `mvn rewrite:run`) |

**Composite range index:** `(ruleId, stepIndex)` — prerequisite resolution and ordered retrieval

**Range index:** `effort`

**Example:**
```cypher
(:MigrationStep {
  ruleId: "pipeline://Spring Boot/3.2.0/Remove deprecated WebMvcConfigurer adapter",
  stepIndex: 0,
  stepType: "replace",
  summary: "Replace WebMvcConfigurerAdapter with WebMvcConfigurer",
  instruction: "Change your class to implement WebMvcConfigurer directly instead of extending WebMvcConfigurerAdapter.",
  effort: "mechanical",
  automatable: true
})
```

---

### BreakingScope

Represents the impact surface and severity of a `MigrationRule`. Every rule has at least one `HAS_SCOPE` relationship; rules without an explicit scope receive the default `(general, low)` pair.

| Property | Type | Required | Description |
|---|---|---|---|
| `scope` | string | yes | One of: `"api-surface"`, `"runtime"`, `"config"`, `"build"`, `"test"`, `"general"` |
| `severity` | string | yes | One of: `"low"`, `"medium"`, `"high"`, `"critical"` |

**Uniqueness constraint:** `(scope, severity)`

**Range index:** `scope`

**Example:**
```cypher
(:BreakingScope {scope: "api-surface", severity: "high"})
```

---

### Class

Represents a Java class (or interface/annotation) referenced in a migration rule or step.

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Fully qualified class name (e.g. `"org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter"`) |
| `framework` | string | no | Framework that owns this class |

**Uniqueness constraint:** `name`

**Example:**
```cypher
(:Class {name: "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter", framework: "Spring Boot"})
```

---

### ApplicationProperty

Represents a framework configuration property key.

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Property key (e.g. `"spring.datasource.url"`, `"server.port"`) |
| `framework` | string | no | Framework that owns this property |

**Uniqueness constraint:** `name`

**Example:**
```cypher
(:ApplicationProperty {name: "spring.security.oauth2.resourceserver.jwt.issuer-uri", framework: "Spring Boot"})
```

---

### Dependency

Represents an external library or module (Maven GAV, NPM package, etc.).

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Dependency identifier (e.g. `"org.springframework.boot:spring-boot-starter-web"`) |
| `framework` | string | no | Framework ecosystem this dependency belongs to |

**Uniqueness constraint:** `name`

**Example:**
```cypher
(:Dependency {name: "org.springframework.boot:spring-boot-starter-security", framework: "Spring Boot"})
```

---

### OpenRewriteRecipe

Represents an OpenRewrite automated refactoring recipe that can execute one or more migration steps.

| Property | Type | Required | Description |
|---|---|---|---|
| `recipeId` | string | yes | Recipe fully qualified name (e.g. `"org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0"`) |
| `description` | string | no | Human-readable description |
| `displayName` | string | no | Short display name for UI |
| `composite` | boolean | no | Whether this recipe is a composite of other recipes |
| `artifactId` | string | no | Maven artifact ID of the recipe module |
| `groupId` | string | no | Maven group ID of the recipe module |
| `artifactVersion` | string | no | Version of the recipe module |
| `tags` | list[string] | no | Categorisation tags |
| `verifiedBy` | string | no | User or agent who verified this recipe works |

**Full-text index:** `openrewrite_recipe_description` on `(description, displayName)`

**Example:**
```cypher
(:OpenRewriteRecipe {
  recipeId: "org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0",
  displayName: "Upgrade to Spring Boot 3.0",
  composite: true,
  groupId: "org.openrewrite.recipe",
  artifactId: "rewrite-spring",
  artifactVersion: "5.0.0"
})
```

---

### RecipeParam

Represents a required or optional parameter of an `OpenRewriteRecipe`.

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Parameter name |
| `type` | string | no | Java type of the parameter |
| `description` | string | no | What the parameter controls |
| `required` | boolean | no | Whether the parameter must be provided |
| `example` | string | no | Example value |

**Example:**
```cypher
(:RecipeParam {name: "newGroupId", type: "String", required: true, example: "com.example"})
```

---

### MigrationContext

Represents a user's active or historical migration session. Tracks progress across a specific version range for a specific project.

| Property | Type | Required | Description |
|---|---|---|---|
| `projectId` | string | yes | Client project identifier (e.g. `"checkout-service"`) |
| `fromVersion` | string | yes | Starting framework version (e.g. `"2.7.0"`) |
| `toVersion` | string | yes | Target framework version (e.g. `"3.2.0"`) |
| `framework` | string | yes | Framework name |
| `status` | string | yes | One of: `"in-progress"`, `"blocked"`, `"complete"`, `"partial"`, `"abandoned"` |
| `scannedEntities` | list[string] | no | Entity names discovered in the client codebase during scanning |
| `completedSteps` | list[string] | no | Element IDs of completed `MigrationStep` nodes (legacy — prefer `STEP_OUTCOME`) |
| `skippedSteps` | list[string] | no | Element IDs of skipped steps (legacy — prefer `STEP_OUTCOME`) |
| `failedSteps` | list[string] | no | Element IDs of failed steps (legacy — prefer `STEP_OUTCOME`) |
| `createdAt` | datetime | yes | Session creation timestamp |
| `completedAt` | datetime | no | Session completion timestamp |
| `notes` | string | no | Free-form notes |

**Uniqueness constraint:** `(projectId, fromVersion, toVersion)`

**Range index:** `projectId`

**Example:**
```cypher
(:MigrationContext {
  projectId: "checkout-service",
  framework: "Spring Boot",
  fromVersion: "2.7.0",
  toVersion: "3.2.0",
  status: "in-progress",
  createdAt: datetime("2025-06-01T09:00:00Z")
})
```

---

### LifecycleAlert

Represents a phase-level alert about a significant framework change — things developers must know before, during, or after migration, regardless of which specific rules apply to their project.

| Property | Type | Required | Description |
|---|---|---|---|
| `message` | string | yes | Human-readable alert text |
| `category` | string | yes | One of: `"security"`, `"api"`, `"config"`, `"dependency"`, `"other"` |
| `phase` | string | yes | One of: `"pre-migration"`, `"migration"`, `"post-migration"` |

**Merge identity:** `message` (unique per linked `Version`)

**Example:**
```cypher
(:LifecycleAlert {
  message: "Spring Security 6 removes the deprecated WebSecurityConfigurerAdapter. All security configuration must use the bean-based approach.",
  category: "security",
  phase: "pre-migration"
})
```

---

## Relationship Types

### INCLUDES_RULE
```
(Version)-[:INCLUDES_RULE]->(MigrationRule)
```
Links a framework version to all migration rules that are relevant when upgrading **to** that version. No properties.

---

### REQUIRES_STEP
```
(MigrationRule)-[:REQUIRES_STEP]->(MigrationStep)
```
Links a rule to each of its migration steps. No properties. Steps should be fetched ordered by `stepIndex`.

---

### HAS_SCOPE
```
(MigrationRule)-[:HAS_SCOPE]->(BreakingScope)
```
Links a rule to one or more scope/severity pairs. Every rule has at least one — default `(general, low)` is created during population when no scope is extracted. No properties.

---

### AFFECTS_CLASS
```
(MigrationRule)-[:AFFECTS_CLASS {role}]->(Class)
(MigrationStep)-[:AFFECTS_CLASS {role}]->(Class)
```
| Property | Type | Values |
|---|---|---|
| `role` | string | `"removed"`, `"replacement"`, `"co-required"`, `"mentioned"` |

Links a rule or step to a Java class it references. Used for applicability matching — if a user's scanned codebase contains a class with this name, the rule is considered applicable.

---

### AFFECTS_PROPERTY
```
(MigrationRule)-[:AFFECTS_PROPERTY {role}]->(ApplicationProperty)
(MigrationStep)-[:AFFECTS_PROPERTY {role}]->(ApplicationProperty)
```
Same `role` values as `AFFECTS_CLASS`. Links to an application configuration property.

---

### AFFECTS_DEPENDENCY
```
(MigrationRule)-[:AFFECTS_DEPENDENCY {role}]->(Dependency)
(MigrationStep)-[:AFFECTS_DEPENDENCY {role}]->(Dependency)
```
Same `role` values as `AFFECTS_CLASS`. Links to an external dependency.

---

### REPLACED_BY
```
(Class)-[:REPLACED_BY]->(Class)
(ApplicationProperty)-[:REPLACED_BY]->(ApplicationProperty)
(Dependency)-[:REPLACED_BY]->(Dependency)
```
Created as a cross-product when both a removed entity and a replacement entity of the same kind exist on the same rule. Enables direct entity-level deprecation lookup without traversing rule nodes. No properties.

**Example:**
```cypher
(:Class {name: "...WebMvcConfigurerAdapter"})-[:REPLACED_BY]->(:Class {name: "...WebMvcConfigurer"})
```

---

### DEPRECATED_IN
```
(Class|ApplicationProperty|Dependency)-[:DEPRECATED_IN]->(Version)
```
Records the version in which an entity was deprecated. The reverse edge `DEPRECATES` is also created on `Version`. No properties.

---

### REMOVED_IN
```
(Class|ApplicationProperty|Dependency)-[:REMOVED_IN]->(Version)
```
Records the version in which an entity was removed. The reverse edge `REMOVES` is also created. No properties.

---

### INTRODUCED_IN
```
(Class|ApplicationProperty|Dependency)-[:INTRODUCED_IN]->(Version)
```
Records the version in which an entity was introduced. The reverse edge `INTRODUCES` is also created. No properties.

---

### REQUIRES
```
(MigrationStep)-[:REQUIRES]->(MigrationStep)
```
Prerequisite edge between steps. A step must not be executed until all its `REQUIRES` targets are `completed`. No properties.

---

### AUTOMATED_BY
```
(MigrationStep)-[:AUTOMATED_BY {auto, confidence, method, missingRequiredParams}]->(OpenRewriteRecipe)
```
| Property | Type | Description |
|---|---|---|
| `auto` | boolean | Whether the recipe can be applied without manual intervention |
| `confidence` | float | Confidence `[0.0, 1.0]` that the recipe is correct for this step |
| `method` | string | How the recipe was matched (e.g. `"deterministic"`) |
| `missingRequiredParams` | list[string] | Recipe params the user must supply before it can run |

A step is considered **fully automatable** when `auto = true` and `missingRequiredParams = []`.

---

### UPGRADES_FROM
```
(MigrationContext)-[:UPGRADES_FROM]->(Version)
```
Links a migration session to its starting `Version` node. No properties.

---

### UPGRADES_TO
```
(MigrationContext)-[:UPGRADES_TO]->(Version)
```
Links a migration session to its target `Version` node. No properties.

---

### STEP_OUTCOME
```
(MigrationContext)-[:STEP_OUTCOME {status, reason, updatedAt}]->(MigrationStep)
```
| Property | Type | Description |
|---|---|---|
| `status` | string | One of: `"completed"`, `"skipped"`, `"failed"` |
| `reason` | string | Human-readable rationale (nullable) |
| `updatedAt` | datetime | Timestamp of last update |

Merged on `(context, step)` pair — repeated calls update the existing relationship rather than creating a duplicate.

---

### HAS_LIFECYCLE_ALERT
```
(Version)-[:HAS_LIFECYCLE_ALERT]->(LifecycleAlert)
```
Links a version to its phase-level alerts. No properties.

---

### HAS_PARAM
```
(OpenRewriteRecipe)-[:HAS_PARAM]->(RecipeParam)
```
Links a recipe to its parameter definitions. No properties.

---

## Constraints & Indexes

| Name | Type | Target | Purpose |
|---|---|---|---|
| `version_unique` | UNIQUENESS | `Version(framework, version)` | Prevent duplicate version records |
| `migration_rule_id` | UNIQUENESS | `MigrationRule(ruleId)` | Prevent duplicate rule IDs |
| `class_name` | UNIQUENESS | `Class(name)` | Prevent duplicate class records |
| `property_name` | UNIQUENESS | `ApplicationProperty(name)` | Prevent duplicate property records |
| `dependency_name` | UNIQUENESS | `Dependency(name)` | Prevent duplicate dependency records |
| `breaking_scope_pair` | UNIQUENESS | `BreakingScope(scope, severity)` | Prevent duplicate scope/severity pairs |
| `migration_context_key` | UNIQUENESS | `MigrationContext(projectId, fromVersion, toVersion)` | Prevent duplicate sessions |
| `version_sortable` | RANGE | `Version(sortableVersion)` | Enable version range queries |
| `version_framework` | RANGE | `Version(framework)` | Enable framework-scoped lookup |
| `rule_statement` | FULLTEXT | `MigrationRule(statement)` | BM25 duplicate detection and keyword search |
| `migration_text` | FULLTEXT | `MigrationRule(statement, reason, solution)` | Multi-field keyword search |
| `step_instruction` | FULLTEXT | `MigrationStep(instruction, summary)` | Full-text search on step text |
| `step_rule_index` | RANGE | `MigrationStep(ruleId, stepIndex)` | Ordered step retrieval and prerequisite resolution |
| `step_effort` | RANGE | `MigrationStep(effort)` | Filter steps by effort tier |
| `breaking_scope_scope` | RANGE | `BreakingScope(scope)` | Scope-based rule filtering |
| `context_project` | RANGE | `MigrationContext(projectId)` | Session lookup by project |
| `openrewrite_recipe_description` | FULLTEXT | `OpenRewriteRecipe(description, displayName)` | Recipe search |
| `migration_knowledge_vector_mr` | VECTOR (768d) | `MigrationRule(embedding)` | Semantic similarity search on community insights |

---

## Data-Flow & Population Rules

### Source section → ruleType mapping

| `source_section` (from LLM extraction) | `ruleType` stored |
|---|---|
| `breaking_change` | `breaking` |
| `security_fix` | `mandatory_migration` |
| `component_upgrade` | `mandatory_migration` |
| `security_config` | `mandatory_migration` |
| `behavioral` | `behavioral` |
| `deprecation` | `deprecation` |
| `new_capability` | `behavioral` |
| Community submission | `community_insight` |

### Default scope fallback

If no `BreakingScope` is linked during population, the populator MERGEs `(:BreakingScope {scope: "general", severity: "low"})` and creates `HAS_SCOPE`.

### Entity relationship cross-product

When a rule has both `removed` and `replacement` entities of the same kind (Class, ApplicationProperty, or Dependency), the populator creates `REPLACED_BY` edges between every removed × replacement pair of that kind.

### sortableVersion formula

```python
sortableVersion = major * 1_000_000 + minor * 1_000 + patch
# "3.2.1" → 3_002_001
# "3.10.0" → 3_010_000
```

---

## Query Pattern Examples

### 1. Fetch all rules for an upgrade path

```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion >= $fromSortable AND v.sortableVersion <= $toSortable
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
RETURN v.version, r, collect(DISTINCT bs) AS scopes, collect(DISTINCT s) AS steps
ORDER BY v.sortableVersion, s.stepIndex
```

### 2. Find rules applicable to a set of scanned entities

```cypher
MATCH (r:MigrationRule {framework: $framework})
WHERE (r)-[:AFFECTS_CLASS]->(:Class) AND EXISTS {
  MATCH (r)-[:AFFECTS_CLASS]->(c:Class)
  WHERE c.name IN $entityList
}
RETURN r
```

### 3. Deprecation chain for a class

```cypher
MATCH (c:Class {name: $className})
OPTIONAL MATCH (c)-[:DEPRECATED_IN]->(dv:Version)
OPTIONAL MATCH (c)-[:REMOVED_IN]->(rv:Version)
OPTIONAL MATCH (c)-[:REPLACED_BY]->(rc:Class)
RETURN c.name, dv.version AS deprecatedIn, rv.version AS removedIn, rc.name AS replacedBy
```

### 4. Automatable steps for a version range

```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion >= $fromSortable AND v.sortableVersion <= $toSortable
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
MATCH (s)-[:AUTOMATED_BY {auto: true}]->(rec:OpenRewriteRecipe)
WHERE size([(s)-[ab:AUTOMATED_BY]->(rec) | ab.missingRequiredParams]) = 0
   OR all(p IN [(s)-[ab:AUTOMATED_BY]->(rec) | ab.missingRequiredParams][0] WHERE p = "")
RETURN s, rec
```

### 5. Session progress summary

```cypher
MATCH (ctx:MigrationContext {projectId: $projectId, fromVersion: $from, toVersion: $to})
OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(step:MigrationStep)
RETURN ctx.status,
       count(CASE WHEN so.status = 'completed' THEN 1 END) AS completed,
       count(CASE WHEN so.status = 'skipped'   THEN 1 END) AS skipped,
       count(CASE WHEN so.status = 'failed'    THEN 1 END) AS failed
```

### 6. Semantic search on community insights

```cypher
CALL db.index.vector.queryNodes('migration_knowledge_vector_mr', 10, $queryEmbedding)
YIELD node, score
WHERE node.ruleType = 'community_insight'
RETURN node, score
ORDER BY score DESC
```

---

## Derived Fields

`entityClassification` is computed at population time and stored on `MigrationRule`:

| Condition | Value |
|---|---|
| Rule has at least one `REQUIRES_STEP` edge | `"actionable"` |
| Rule has no steps but has at least one `AFFECTS_*` edge | `"incomplete"` |
| Rule has neither steps nor affected entities | `"informational"` |

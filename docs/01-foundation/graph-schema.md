# Neo4j Graph Schema — Paysafe Migration Oracle

This document is the authoritative reference for every node label, relationship type, property, constraint, and index in the Migration Oracle graph database. It also includes query pattern examples, version resolution semantics, and the data-flow rules used during pipeline population.

For MCP tool contracts that query this schema, see [mcp-tools-skills-prompts.md](../03-mcp-and-agent-harness/mcp-tools-skills-prompts.md).

---

## Table of Contents

1. [Overview](#overview)
2. [Version Resolution](#version-resolution)
3. [Node Labels](#node-labels)
   - [Version](#version)
   - [MigrationRule](#migrationrule)
   - [MigrationStep](#migrationstep)
   - [BreakingScope](#breakingscope)
   - [Class](#class)
   - [ApplicationProperty](#applicationproperty)
   - [Dependency](#dependency)
   - [TemplateSyntax](#templatesyntax)
   - [DiagnosticCode](#diagnosticcode)
   - [OpenRewriteRecipe](#openrewriterecipe)
   - [RecipeParam](#recipeparam)
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
```

The graph models **knowledge only** — migration rules, ordered steps, affected entities,
OpenRewrite recipes, lifecycle alerts, and community insights reachable from `Version` nodes.

> **Removed session-state subgraph (017):** context nodes, step-outcome edges, and
> queried-entity cache. Per-migration progress now lives in `ps-migration/` markdown files.
> `BRIDGED_BY` and community-insight rules are retained.

Community insights are stored as `MigrationRule` nodes with `ruleType='community_insight'` (linked via `INCLUDES_RULE` — not a separate label).

---

## Version Resolution

All MCP tools that accept a version string use `resolve_version(framework, version, mode)` (`migration_oracle/mcp/graph/queries/upgrade.py`):

| Mode | Semantics | Typical use |
|---|---|---|
| `exact` | Must match a graph node exactly | Rare — internal lookups |
| `floor` | Highest `sortableVersion` ≤ requested | Current/from version (`create_migration_context`, insight submission) |
| `ceil` | Lowest `sortableVersion` ≥ requested; falls back to highest known + `aheadOfCatalogue=true` | Target/to version |

**Patch preservation:** The caller's patch segment is never truncated (e.g. `3.5.12` stays `3.5.12`, not `3.5.0`).

**Stub nodes:** When `allow_stub_create=true` on context creation and the ceil target is ahead-of-catalogue, a minimal `Version` node is MERGE'd with `status: "stub"` (or `"stub-pending"`). Stub nodes lack full rule coverage until the catalogue catches up.

**sortableVersion formula:**

```python
sortableVersion = major * 1_000_000 + minor * 1_000 + patch
# Spring Boot "3.2.1"  → 3_002_001
# Spring Cloud "2025.1.0" → 2025 * 1_000_000 + 1 * 1_000 + 0 = 2_025_001_000
```

**Prereleases (`-M1`, `-RC2`, `-next.3`, `.Final`):** milestone/RC builds are valid catalogued versions and sort **below** the GA release they precede, using the previous minor line's unused patch numbers:

```python
# "4.1.0-M1"  → 4_000_901   (== 4.0.901 — above every real 4.0.x patch)
# "4.1.0-RC1" → 4_000_951
# "4.1.0"     → 4_001_000   (GA values are unchanged)
```

A prerelease node carries `preRelease: true` and `preReleaseLabel` (e.g. `"RC1"`); GA spellings such as `26.1.2.Final` or `1.0.0-GA` are stored at the plain GA integer without those properties. Consequence for range queries: a `4.0.6 → 4.1.0` path includes the 4.1 milestone/RC rules (early warning), while `4.0.6 → 4.1.0-M2` excludes builds that came later.

**Ceiling:** the formula assumes minor and patch stay ≤ 999 (`3.2.1000` would alias `3.3.0`), and a line's real patch numbers must stay below 800 so prereleases keep their unused 800–999 band.

---

## Node Labels

## Node Labels

### Version

Represents a specific release of a framework. It is the root anchor from which all migration knowledge is reachable.

| Property | Type | Required | Description |
|---|---|---|---|
| `framework` | string | yes | Display-form framework name (e.g. `"Spring Boot"`, `"Angular"`, `"WildFly"`) |
| `version` | string | yes | Semantic version string (e.g. `"3.2.0"`, `"3.2"`) |
| `sortableVersion` | integer | yes | `major×1_000_000 + minor×1_000 + patch` — enables fast range queries |
| `preRelease` | boolean | no | `true` for milestone/RC builds (`"4.1.0-RC1"`); absent on GA releases |
| `preReleaseLabel` | string | no | Prerelease suffix as published, e.g. `"RC1"`, `"next.3"` |
| `status` | string | no | Catalogue status: `"active"`, `"maintenance"`, `"eol"`, `"stub"`, `"stub-pending"` |
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
| `signal` | string | no | How a service shows the rule applies: `"symbol"`, `"config"`, `"dependency"`, `"syntax"`, `"behavioral"`, `"universal"` (spec 027). **Missing = treat as `"behavioral"`** |
| `signalConfidence` | float | no | Probability of the chosen `signal` after the contract guard |
| `signalSource` | string | no | `"model"` · `"rule"` (all-dependency component upgrade) · `"guard"` (nothing to search for) · `"low_confidence"` (below the floor) |
| `signalKeys` | list[string] | no | Canonical keys (spec 025) the planner searches for; empty for `behavioral` / `universal` |
| `features` | list[string] | no | Feature ids the rule needs (`ssr`, `testbed`, `security`, …), see [Rule signals](#rule-signals) |
| `signalQuestionsVersion` | integer | no | Version of the signal question contract; a bump re-asks every rule |
| `signalModel` | string | no | Classifier that produced the signal (`"nimble"`) |
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

Represents a Java class (or interface/annotation) or an npm exported symbol (or a member of one) referenced in a migration rule or step.

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Fully qualified class name (e.g. `"org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter"`) or bare symbol / `Owner.member` for npm (e.g. `"InjectFlags"`, `"TestBed.get"`); never contains `:` |
| `key` | string | yes | Canonical merge identity: `maven:<FQCN>` or `npm:<package>#<symbol>[.<member>]` (`npm:?#…` while the package is unresolved) |
| `ecosystem` | string | yes | `maven` or `npm` |
| `package` | string | no | npm package / entry point (e.g. `"@angular/core/testing"`) or Maven `groupId:artifactId` for dependencies |
| `symbol` | string | no | Exported symbol / FQCN |
| `member` | string | no | Method, field, or option of `symbol` (`kind: member` occurrences) |
| `verified` | string | yes | `true` · `false` · `ambiguous` — npm symbols checked against the framework's published API index at populate time; `unchecked` for maven (no API index yet) |
| `framework` | string | no | Framework that owns this class |

**Uniqueness constraint:** `key` (`name` has a plain index — a symbol like `VERSION` exists in several Angular entry points)

**Example:**
```cypher
(:Class {name: "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter", key: "maven:org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter", ecosystem: "maven", verified: "unchecked", framework: "Spring Boot"})
```

---

### ApplicationProperty

Represents a framework configuration property key.

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Property key (e.g. `"spring.datasource.url"`, `"server.port"`) or full dotted config key for npm (e.g. `"engines.node"`) |
| `key` | string | yes | Canonical merge identity: `cfg:<file>#<dotted key>` (`application.properties` for Spring, `package.json` / `tsconfig.json` / `angular.json` for Angular) |
| `file` | string | no | Config file the key belongs to |
| `ecosystem` | string | yes | `maven` or `npm` |
| `verified` | string | yes | npm: `true` when the config file is known, else `false`; maven: `unchecked` |
| `framework` | string | no | Framework that owns this property |

**Uniqueness constraint:** `key` (`name` has a plain index)

**Example:**
```cypher
(:ApplicationProperty {name: "spring.security.oauth2.resourceserver.jwt.issuer-uri", key: "cfg:application.properties#spring.security.oauth2.resourceserver.jwt.issuer-uri", ecosystem: "maven", verified: "unchecked", framework: "Spring Boot"})
```

---

### Dependency

Represents an external library or module (Maven GAV, NPM package, etc.).

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Dependency identifier (e.g. `"org.springframework.boot:spring-boot-starter-web"`, `"@angular/core"`) |
| `key` | string | yes | Canonical merge identity: `maven:<groupId>:<artifactId>` or `npm:<package>` |
| `ecosystem` | string | yes | `maven` or `npm` |
| `verified` | string | yes | npm: `true`; maven: `unchecked` |
| `framework` | string | no | Framework ecosystem this dependency belongs to |

**Uniqueness constraint:** `key` (`name` has a plain index)

**Example:**
```cypher
(:Dependency {name: "org.springframework.boot:spring-boot-starter-security", key: "maven:org.springframework.boot:spring-boot-starter-security", ecosystem: "maven", verified: "unchecked", framework: "Spring Boot"})
```

---

### TemplateSyntax

Represents an Angular template operator or block keyword affected by a rule (e.g. `@if`, `in`, `@defer`).

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | The token as written in a template (e.g. `"@defer"`) |
| `key` | string | yes | `syntax:<framework>-template#<token>` |
| `verified` | string | yes | `true` (recognized from the profile's token list) |

**Uniqueness constraint:** `key` (`template_syntax_key`)

---

### DiagnosticCode

Represents a compiler or tooling diagnostic affected by a rule (e.g. `NG8115`).

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | The diagnostic code (e.g. `"NG8115"`) |
| `key` | string | yes | `diag:<code>` |
| `verified` | string | yes | `true` (recognized by pattern) |

**Uniqueness constraint:** `key` (`diagnostic_code_key`)

---

### OpenRewriteRecipe

Represents an OpenRewrite automated refactoring recipe that can execute one or more migration steps.

| Property | Type | Required | Description |
|---|---|---|---|
| `recipeId` | string | yes | Recipe fully qualified name (e.g. `"org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0"`) |
| `description` | string | no | Human-readable description |
| `displayName` | string | no | Short display name for UI |
| `composite` | boolean | no | Whether this recipe is a composite of other recipes (alias: `isComposite` in some queries) |
| `artifactId` | string | no | Maven artifact ID of the recipe module |
| `groupId` | string | no | Maven group ID of the recipe module |
| `artifactVersion` | string | no | Version of the recipe module |
| `tags` | list[string] | no | Categorisation tags |
| `verifiedBy` | string | no | User or agent who verified this recipe works |
| `embedding` | list[float] | no | Sentence-transformer vector (768 dims) for semantic recipe search |

**Full-text index:** `openrewrite_recipe_description` on `(description, displayName)`

**Vector index:** `openrewrite_recipe_vector` on `embedding`

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

### AFFECTS_SYNTAX
```
(MigrationRule)-[:AFFECTS_SYNTAX {role}]->(TemplateSyntax)
(MigrationStep)-[:AFFECTS_SYNTAX {role}]->(TemplateSyntax)
```
Same `role` values as `AFFECTS_CLASS`. Links to an Angular template operator or block keyword.

---

### AFFECTS_DIAGNOSTIC
```
(MigrationRule)-[:AFFECTS_DIAGNOSTIC {role}]->(DiagnosticCode)
(MigrationStep)-[:AFFECTS_DIAGNOSTIC {role}]->(DiagnosticCode)
```
Same `role` values as `AFFECTS_CLASS`. Links to a compiler or tooling diagnostic.

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

### BRIDGED_BY
```
(MigrationRule)-[:BRIDGED_BY {removalCondition, bridgeReason, applicableRuleTypes}]->(Dependency)
```
| Property | Type | Description |
|---|---|---|
| `removalCondition` | string | Human-readable condition under which the bridge is removed |
| `bridgeReason` | string | Explanation of why this bridge exists |
| `applicableRuleTypes` | list[string] | ruleType values for which this bridge applies; e.g. `["breaking", "mandatory_migration"]` |

Cardinality: 0..N per rule. A rule with no `BRIDGED_BY` edges does not accept `deferred` outcomes (FR-C11).

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
| `class_key` | UNIQUENESS | `Class(key)` | One canonical identity per class / member (spec 025) |
| `property_key` | UNIQUENESS | `ApplicationProperty(key)` | One canonical identity per config key |
| `dependency_key` | UNIQUENESS | `Dependency(key)` | One canonical identity per dependency |
| `template_syntax_key` | UNIQUENESS | `TemplateSyntax(key)` | One canonical identity per template token |
| `diagnostic_code_key` | UNIQUENESS | `DiagnosticCode(key)` | One canonical identity per diagnostic |
| `breaking_scope_pair` | UNIQUENESS | `BreakingScope(scope, severity)` | Prevent duplicate scope/severity pairs |
| `version_sortable` | RANGE | `Version(sortableVersion)` | Enable version range queries |
| `version_framework` | RANGE | `Version(framework)` | Enable framework-scoped lookup |
| `class_name_index` | RANGE | `Class(name)` | Matchable-name lookup (name is no longer unique) |
| `property_name_index` | RANGE | `ApplicationProperty(name)` | Matchable-name lookup |
| `dependency_name_index` | RANGE | `Dependency(name)` | Matchable-name lookup |
| `rule_statement` | FULLTEXT | `MigrationRule(statement)` | BM25 duplicate detection and keyword search |
| `migration_text` | FULLTEXT | `MigrationRule(statement, reason, solution)` | Multi-field keyword search |
| `step_instruction` | FULLTEXT | `MigrationStep(instruction, summary)` | Full-text search on step text |
| `step_rule_index` | RANGE | `MigrationStep(ruleId, stepIndex)` | Ordered step retrieval and prerequisite resolution |
| `step_effort` | RANGE | `MigrationStep(effort)` | Filter steps by effort tier |
| `breaking_scope_scope` | RANGE | `BreakingScope(scope)` | Scope-based rule filtering |
| `openrewrite_recipe_description` | FULLTEXT | `OpenRewriteRecipe(description, displayName)` | Recipe keyword search |
| `openrewrite_recipe_vector` | VECTOR (768d) | `OpenRewriteRecipe(embedding)` | Semantic recipe search |
| `migration_knowledge_vector_mr` | VECTOR (768d) | `MigrationRule(embedding)` | Semantic similarity search on rules and community insights |

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

### Entity applicability matching (MCP layer)

When a codebase scan supplies entities, MCP tools split them into five typed buckets via `normalize_entities()` and match against graph nodes using exact-string rules plus package-prefix bridges (`migration_oracle/mcp/matching.py`):

| Graph node | Match against |
|---|---|
| `Class` | FQCN in `scannedClasses` OR simple name in `scannedClassSimple` |
| `ApplicationProperty` | Full key in `scannedProps` |
| `Dependency` | Full `groupId:artifactId` in `scannedDepsGa` OR artifact ID in `scannedDepArtifacts` |

Rules with no matching entities are `excluded` unless severity is high/critical (`uncertain` safety net) or the rule has no entity nodes (`informational`).

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

### 5. Semantic search on community insights

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

---

## Rule signals

`signal` answers one question per rule: **what in an application shows that this
rule applies to it?** The migration planner (spec 026/028) reads it from the
graph; it never calls the classifier itself.

| `signal` | The planner decides with | Example |
|---|---|---|
| `symbol` | the code uses a named API | `TestBed.get` removed |
| `config` | a config key is set | `angularCompilerOptions.strictStandalone` default changed |
| `dependency` | a package is declared (optionally in a range) | `@angular/animations` deprecated |
| `syntax` | template syntax is used | `in` is an operator |
| `behavioral` | the API name is not enough; the code must be read (or a person asked) | `onDestroy` timing |
| `universal` | every service on the hop is affected | minimum Node / TypeScript |

The classification is written by populate right after canonicalization (spec
027) and can be backfilled for hops already in the graph with
`scripts/classify_signals.py`. Two rules keep a wrong classification from
excluding a rule that applies:

- **The guard.** If the chosen type has no key to search for — for example
  `symbol` for a rule that names only its replacement — the type becomes
  `behavioral` with `signalSource: "guard"`. `signalKeys` reports whatever was
  found, so the decision can be reviewed.
- **The floors.** `symbol` / `config` / `dependency` / `syntax` need
  `SIGNAL_SEARCHABLE_MIN_PROB` (0.70); `universal` needs
  `SIGNAL_UNIVERSAL_MIN_PROB` (0.60). Below the floor the rule is `behavioral`
  with `signalSource: "low_confidence"`.

A rule with **no** signal properties (Nimble unset or unreachable, or the hop
was populated with `--skip-signals`) is read as `behavioral`, so a missing
classification never excludes anything.

`features` names the features a rule needs, from a per-framework vocabulary
with **evidence keys**: profile keys (spec 026) from which the planner can tell
without asking that a service has the feature.

| Framework | Features |
|---|---|
| Angular | `ssr`, `hydration`, `zoneless`, `zone`, `animations`, `router`, `forms`, `http`, `i18n`, `service-worker`, `testbed`, `karma`, `ngmodule`, `elements`, `upgrade`, `cli-build` |
| Spring Boot | `web-mvc`, `webflux`, `security`, `data-jpa`, `data-mongodb`, `data-redis`, `kafka`, `actuator`, `observability`, `jackson`, `batch`, `testing`, `cloud`, `gradle`, `maven` |
| WildFly | subsystems (`undertow`, `ejb3`, `messaging-activemq`, `elytron`, `jpa`, …) |

The vocabulary lives in `migration_oracle/pipeline/signals/features.py` as plain
data, so it can be exported to the planner unchanged.

**Example:**

```cypher
(:MigrationRule {
  ruleId: "pipeline://Angular/20.0.0/TestBed.get removed",
  signal: "symbol",
  signalConfidence: 0.92,
  signalSource: "model",
  signalKeys: ["npm:@angular/core/testing#TestBed.get"],
  features: ["testbed"],
  signalQuestionsVersion: 1,
  signalModel: "nimble"
})
```

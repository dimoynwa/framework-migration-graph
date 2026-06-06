# Migration Oracle — Full System Redesign
 
## Document purpose
 
This document specifies every change to the Paysafe Migration Oracle system across three layers: the knowledge graph schema, the JSON entity extraction schema produced by the second LLM call, and the agent harness that executes migrations. It is written as a complete, self-contained reference — no prior knowledge of the existing system is assumed, but the reasoning behind each change is explained against the current design so the motivation is always clear.
 
The redesign is strictly additive at the graph layer. No existing node label, relationship type, or MCP tool is removed. Every current Cypher query continues to work unchanged.
 
---
 
## Table of contents
 
1. [System overview and design principles](#1-system-overview-and-design-principles)
2. [Current system — what exists and where it breaks down](#2-current-system--what-exists-and-where-it-breaks-down)
3. [Graph schema redesign](#3-graph-schema-redesign)
4. [JSON extraction schema redesign](#4-json-extraction-schema-redesign)
5. [Graph population logic — what changes](#5-graph-population-logic--what-changes)
6. [New and updated MCP tools](#6-new-and-updated-mcp-tools)
7. [Agent harness redesign — four runtime loops](#7-agent-harness-redesign--four-runtime-loops)
8. [Backward compatibility contract](#8-backward-compatibility-contract)
9. [Migration path — implementing the redesign incrementally](#9-migration-path--implementing-the-redesign-incrementally)
---
 
## 1. System overview and design principles
 
The Migration Oracle is a knowledge pipeline with three distinct layers.
 
The **extraction pipeline** fetches release notes from GitHub, Jira, Red Hat documentation, Maven Central, and npm for nine supported frameworks (Spring Boot, Angular, WildFly, JBoss EAP, Hibernate ORM, RESTEasy, Infinispan, WildFly Elytron, Jakarta EE). It runs two sequential LLM calls: the first filters noise and imposes a severity structure on hundreds of raw changelog rows; the second extracts typed, machine-readable entities from that structured output. The result is written to a Neo4j or Memgraph property graph.
 
The **knowledge graph** stores releases (`Version` nodes), documented changes (`MigrationRule` nodes), affected artifacts (`Class`, `ApplicationProperty`, `Dependency`), community workarounds (`CommunityInsight`), and OpenRewrite automation recipes (`OpenRewriteRecipe`). It is served to agents via the `PaysafeMigrationOracle` MCP server, which exposes fifteen primary tools.
 
The **agent harness** is the procedural skill that instructs an AI agent how to use those MCP tools. Currently it runs as five sequential phases: resolve inputs, scan codebase, query graph, synthesise, and output a plan document. It has no state, no execution loop, and no feedback path.
 
### Design principles for the redesign
 
**Separation of observation and prescription.** A `MigrationRule` observes what changed. A `MigrationStep` prescribes what the developer must do. These are different things and should be different nodes. The current schema conflates them by storing the entire prescription as an unstructured `actionStep` string property on `MigrationRule`.
 
**Relationship semantics over flat lists.** `affected_classes: ["A", "B", "C"]` with `replacement_class: "D"` is ambiguous the moment there are two old classes and two new ones. Every entity reference must carry a `role` tag — `removed`, `replacement`, `co-required`, or `mentioned` — so the graph can answer "what replaces what" without re-parsing prose.
 
**Blast radius as a first-class graph concept.** The current schema can tell you a change is breaking. It cannot tell you whether the break touches the public API surface, runtime behaviour, configuration, the build system, or only tests. That distinction is essential for triage ordering. A new `BreakingScope` node carries `scope` and `severity` as explicit properties.
 
**Stateful execution as a graph concern.** A migration is a long-running project, not a single query. The agent needs to store which steps have been completed, which were skipped, and which are blocked — and it needs to resume from that state across sessions. A new `MigrationContext` node holds all of this in the graph itself, not in agent memory.
 
**The two-LLM-call pipeline stays.** The first call (filter and group) is excellent and should not change. It reads the entire raw document, deduplicates across hundreds of rows, consolidates related items, rewrites noisy Jira one-liners into actionable impact statements, and imposes a seven-section severity hierarchy. The second call reads that structured output and produces machine-readable entities. What changes is what the second call produces — a richer schema that populates the enhanced graph directly, without lossy intermediate mappings.
 
---
 
## 2. Current system — what exists and where it breaks down
 
### 2.1 Current graph nodes
 
| Node | Key properties | Notes |
|------|----------------|-------|
| `Version` | `framework`, `version`, `sortableVersion` | `sortableVersion = major × 1,000,000 + minor × 1,000 + patch` |
| `MigrationRule` | `statement`, `ruleType`, `sourceUrl`, `actionStep`, `changeType`, `reasonType`, `reason`, `entityClassification` | `entityClassification` is `actionable` / `incomplete` / `informational` |
| `CommunityInsight` | `statement`, `solution`, `sourceUrl`, `submittedBy`, `createdAt`, `confidence`, `votes`, `verified` | |
| `ApplicationProperty` | `name` | Dot-notation key |
| `Class` | `name` | FQCN or simple name |
| `Dependency` | `name` | `groupId:artifactId` or npm package |
| `OpenRewriteRecipe` | `recipeId`, `displayName`, `description`, `groupId`, `artifactId`, `artifactVersion`, `isComposite`, `hasRequiredParams`, `tags`, `parameterSchema`, `embedding` | |
 
### 2.2 Current relationships
 
| Relationship | Direction | Meaning |
|---|---|---|
| `INCLUDES_RULE` | Version → MigrationRule | Rule belongs to a release |
| `DISCOVERED_IN` | CommunityInsight → Version | Insight tied to a release |
| `SUPERSEDES` | Version → Version | EAP over WildFly base |
| `AFFECTS_PROPERTY` | Rule/Insight → ApplicationProperty | |
| `AFFECTS_CLASS` | Rule/Insight → Class | |
| `AFFECTS_DEPENDENCY` | Rule/Insight → Dependency | |
| `AFFECTED_IN` | Entity → Rule/Insight | Inverse of AFFECTS_* |
| `REPLACED_BY` | Entity → Entity | Same label type, up to 5 hops |
| `DEPRECATED_IN` | Entity → Version | |
| `REMOVED_IN` | Entity → Version | |
| `INTRODUCED_IN` | Entity → Version | |
| `DEPRECATES` / `REMOVES` / `INTRODUCES` | Version → Entity | Inverse lifecycle edges |
| `AUTOMATED_BY` | Rule/Insight → OpenRewriteRecipe | With confidence, parameters, auto flag |
| `AUTOMATES` | Recipe → Rule/Insight | Denormalised inverse |
| `COMPOSED_OF` | Recipe → Recipe | Composite recipes |
| `TARGETS_VERSION` | Recipe → Version | |
 
### 2.3 Current JSON extraction schema
 
```json
{
  "entities": [
    {
      "change_type": "string",
      "reason_type": "string",
      "reason": "string",
      "action_step": "string",
      "affected_properties": ["string"],
      "replacement_property": "string",
      "affected_classes": ["string"],
      "replacement_class": "string",
      "affected_dependencies": ["string"],
      "replacement_dependency": "string",
      "cli_operation": "string",
      "subsystem": "string"
    }
  ]
}
```
 
### 2.4 Current agent harness phases
 
| Phase | Action |
|---|---|
| 0 | Resolve `FROM_VERSION`, `TO_VERSION`, `FRAMEWORK`, `MODE` |
| 1 | Scan codebase — mandatory gate before any MCP call. Produces flat entity list. |
| 2 | Query graph: `analyze_upgrade_path` → `resolve_deprecation` per entity → Paysafe resolution → `search_migration_knowledge` for gaps |
| 3 | Synthesise — group by concern (SECURITY, PERSISTENCE, WEB, CONFIG, DEPENDENCIES, BUILD, TESTING, OTHER) with LLM-inferred risk ratings |
| 4 | Output `MIGRATION_PLAN.md` and exit |
 
### 2.5 Specific failure modes
 
**`actionStep` as a blob.** The entire prescription for a migration change is stored as one free-text string. It cannot be ordered, cannot have prerequisites, cannot be individually flagged as automatable or mechanical vs architectural, and cannot carry a verification signal. When `analyze_upgrade_path` returns forty rules, the agent receives forty prose paragraphs and must infer order, priority, and automation eligibility from the text.
 
**Flat entity lists lose relationship semantics.** `affected_classes: ["WebSecurityConfigurerAdapter", "SecurityFilterChain", "HttpSecurity"]` with `replacement_class: "SecurityFilterChain"` is uninterpretable when there are multiple old classes. Which one is removed? Is `HttpSecurity` a replacement or a co-required dependency of the replacement? The graph cannot answer this because the information was never captured — the `REPLACED_BY` edge is derived from two separate string fields rather than from typed entity pairs.
 
**No blast radius model.** The graph has `entityClassification` (`actionable` / `incomplete` / `informational`) which describes extraction quality, not impact severity. There is no way to ask "show me only the changes that touch the public API surface at critical severity" without parsing the statement blob. The agent must synthesise priority from prose, which means the 3-5 most important breaks are buried in a flat list ordered by version, not by impact.
 
**`change_type` → `ruleType` is a lossy substring mapping.** The entity extraction produces `change_type` strings like `"breaking_change"`. The graph population code maps these to `ruleType` values by substring matching — if `change_type` contains `"breaking"` or `"remov"`, `ruleType` becomes `"breaking"`. This mapping discards information and introduces ambiguity. The filtered Markdown produced by the first LLM call already has the correct severity classification in its section header — the second call should read that directly rather than re-derive it.
 
**`AUTOMATED_BY` links rule to recipe, not fix to recipe.** A recipe automates a specific fix action. The current schema attaches `AUTOMATED_BY` to `MigrationRule` (the observation) rather than to the individual step (the prescription). This makes it impossible to ask "which steps in this upgrade are automatable?" because steps do not exist as nodes — they are text inside `actionStep`. The recipe plan builder must parse prose to estimate whether automation applies.
 
**No persistent execution state.** The harness writes a Markdown plan and exits. If the migration is interrupted, the entire session must restart from scratch. There is no graph record of what has been applied, what is pending, what was skipped, or why. Long migrations (Spring Boot 2.x to 4.x spans dozens of breaking changes across multiple major versions) are impossible to manage reliably without state.
 
**No feedback path.** Every migration a team runs produces discovered workarounds — a step that did not work as described, an undocumented dependency conflict, a configuration value that needed to be different in practice. These discoveries exist nowhere in the system. The `submit_migration_insight` MCP tool exists but the harness never calls it. The knowledge graph does not compound in value across migrations.
 
---
 
## 3. Graph schema redesign
 
### 3.1 Three new node types
 
#### `MigrationStep`
 
The first-class representation of an atomic migration action. Replaces the `actionStep` string property on `MigrationRule`. A rule may have multiple steps. Steps can depend on each other via `REQUIRES` edges.
 
| Property | Type | Description |
|---|---|---|
| `stepType` | string | `remove` \| `rename` \| `replace` \| `configure` \| `verify` \| `namespace` |
| `summary` | string | Ten words or fewer — what this step does |
| `instruction` | string | Full concrete action: what to change, where, how |
| `effort` | string | `mechanical` \| `moderate` \| `architectural` |
| `automatable` | boolean | True only if a recipe can apply this step without human review |
| `verificationHint` | string | Observable signal that confirms the step succeeded |
| `cliOperation` | string | WildFly CLI fragment, if applicable (empty otherwise) |
| `embedding` | float[] | 768-dim vector for semantic search, optional |
 
**Effort levels defined precisely:**
- `mechanical` — a tool can apply this without human judgement. A property rename, a package import update, a single-line configuration change. Safe to auto-apply via OpenRewrite.
- `moderate` — a developer must review and apply the change, but the action is well-defined. A method refactor, a multi-file class restructure, a security config pattern update.
- `architectural` — a design decision is required. The agent must pause and surface a design choice to the developer before proceeding. Replacing a security model, restructuring a persistence layer, migrating an API surface.
**`entityClassification` on `MigrationRule` is now derived from steps:**
- `actionable` — at least one step has a non-empty `instruction`
- `incomplete` — entity nodes exist but no steps with instructions
- `informational` — reason text only, no entities and no steps
#### `BreakingScope`
 
Classifies the blast radius of a migration rule. A rule may have multiple scopes (e.g. a change that touches both the API surface and the build system). `BreakingScope` nodes are shared — the same `(scope, severity)` pair is a single node, and many rules link to it via `HAS_SCOPE` edges.
 
| Property | Type | Values |
|---|---|---|
| `scope` | string | `api-surface` \| `runtime` \| `config` \| `build` \| `test` |
| `severity` | string | `low` \| `medium` \| `high` \| `critical` |
 
**Scope definitions:**
- `api-surface` — changes a public API that callers of this service depend on. Classes removed from public packages, method signatures changed, REST endpoints modified.
- `runtime` — changes runtime behaviour without changing the API. Default values altered, lifecycle order changed, security behaviour modified.
- `config` — changes to `application.yml` / `application.properties` keys or values only. Does not affect compiled code.
- `build` — changes to `pom.xml`, `build.gradle`, dependency coordinates, or plugin configuration.
- `test` — changes only affect test code or test configuration. Safe to address last.
#### `MigrationContext`
 
A project-scoped, persistent record of a migration session. Created once per `(projectId, fromVersion, toVersion)` triple and updated after every executed step. Enables the agent to resume after interruption, hand off to another session, and query what remains.
 
| Property | Type | Description |
|---|---|---|
| `projectId` | string | Stable identifier — typically the git repo path or service name |
| `fromVersion` | string | Starting framework version |
| `toVersion` | string | Target framework version |
| `framework` | string | `Spring Boot` or `Angular` |
| `status` | string | `in-progress` \| `blocked` \| `complete` \| `partial` \| `abandoned` |
| `scannedEntities` | string[] | FQCNs, property keys, `groupId:artifactId` from most recent codebase scan |
| `completedSteps` | string[] | `elementId` values of `MigrationStep` nodes confirmed done |
| `skippedSteps` | string[] | `elementId` values of `MigrationStep` nodes explicitly skipped |
| `queriedEntities` | map | Entity name → query timestamp cache, prevents re-querying in resumed sessions |
| `riskOverride` | string | Optional user-set risk level if project context changes the default |
| `createdAt` | datetime | |
| `completedAt` | datetime | Set by `close_migration_context` |
| `notes` | string | Human-readable summary of what was done and what remains |
 
### 3.2 New relationship types
 
| Relationship | Direction | Meaning |
|---|---|---|
| `REQUIRES_STEP` | MigrationRule → MigrationStep | Rule has this step as part of its prescription |
| `REQUIRES` | MigrationStep → MigrationStep | Step cannot execute until the prerequisite step is complete |
| `HAS_SCOPE` | MigrationRule → BreakingScope | Rule has this blast radius classification |
| `UPGRADES_FROM` | MigrationContext → Version | Context is for an upgrade starting from this version |
| `UPGRADES_TO` | MigrationContext → Version | Context is for an upgrade targeting this version |
 
### 3.3 Modified relationship: `AFFECTS_*` gains a `role` property
 
The existing `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, and `AFFECTS_DEPENDENCY` relationships are extended with a `role` edge property. The relationship type is unchanged — existing queries continue to work. The new property is:
 
| `role` value | Meaning |
|---|---|
| `removed` | This entity is being removed in this release. Triggers `REMOVED_IN` lifecycle edge. |
| `replacement` | This entity replaces the removed one. Triggers `INTRODUCED_IN` lifecycle edge. |
| `co-required` | This entity must also be configured when adopting the replacement. No lifecycle edge. |
| `mentioned` | Referenced in the rule text but not directly changed. No lifecycle edge. |
 
When `role=removed` and `role=replacement` both exist on entities of the same `kind` within a rule, the `REPLACED_BY` edge between the old and new entity is derived automatically at population time. This replaces the fragile `replacement_class` / `replacement_property` / `replacement_dependency` single-string fields.
 
### 3.4 Modified relationship: `AUTOMATED_BY` moves from rule to step
 
`AUTOMATED_BY` now connects `MigrationStep` → `OpenRewriteRecipe` in addition to the existing `MigrationRule` → `OpenRewriteRecipe` connection. The existing rule-level connection is retained for backward compatibility. At population time, when a step is `automatable=true`, the recipe mapping runs at step level. This means `build_recipe_plan` can now filter to `automatable=true AND effort='mechanical'` steps with precision, without needing to parse rule-level prose.
 
The existing `AUTOMATED_BY` edge schema (with `method`, `confidence`, `auto`, `signals`, `parameters`, `missingRequiredParams`, `blockedReason`, `verifiedBy`, etc.) is unchanged. The same properties apply whether the edge is from a rule or a step.
 
### 3.5 New properties on existing `MigrationRule`
 
| Property | Type | Source | Description |
|---|---|---|---|
| `title` | string | `title` column of filtered MD | Short display label, ten words or fewer |
| `jiraKeys` | string[] | `jira_keys` field of extraction JSON | Enables lookup by Jira issue key |
 
`actionStep` is deprecated on `MigrationRule` but not removed. New population runs will not write it. Existing nodes retain their `actionStep` values for backward compatibility with tools that read it.
 
### 3.6 Complete updated entity-relationship structure
 
```
Version
  │─ INCLUDES_RULE ─────────────────────────────────► MigrationRule
  │                                                         │
  │                                              ┌──────────┼──────────────┐
  │                                              │          │              │
  │                                     REQUIRES_STEP   HAS_SCOPE    AUTOMATED_BY
  │                                              │          │      (rule-level, kept)
  │                                              ▼          ▼              ▼
  │                                       MigrationStep  BreakingScope  OpenRewriteRecipe
  │                                              │                          ▲
  │                                         REQUIRES                  AUTOMATED_BY
  │                                              │                   (step-level, new)
  │                                              ▼
  │                                       MigrationStep (prereq)
  │
  │  AFFECTS_CLASS {role} ──────────────────────► Class
  │  AFFECTS_PROPERTY {role} ──────────────────► ApplicationProperty
  │  AFFECTS_DEPENDENCY {role} ────────────────► Dependency
  │        (from both MigrationRule and MigrationStep)
  │
  │  Class / Property / Dependency:
  │     ─ REPLACED_BY ────────────────────────► same-type entity
  │     ─ DEPRECATED_IN ─────────────────────► Version
  │     ─ REMOVED_IN ───────────────────────► Version
  │     ─ INTRODUCED_IN ─────────────────────► Version
  │
  │◄── DISCOVERED_IN ─── CommunityInsight
  │                            │
  │               (same AFFECTS_* pattern as MigrationRule)
  │
  ◄── UPGRADES_FROM ─── MigrationContext ─── UPGRADES_TO ──► Version
```
 
### 3.7 New indexes
 
| Index name | Label | Property | Type |
|---|---|---|---|
| `migration_step_type` | MigrationStep | `stepType` | B-tree |
| `migration_step_effort` | MigrationStep | `effort` | B-tree |
| `migration_context_project` | MigrationContext | `projectId` | B-tree |
| `breaking_scope_lookup` | BreakingScope | `scope`, `severity` | Composite B-tree |
 
The existing vector and full-text indexes are unchanged. `MigrationStep` nodes with `embedding` set are indexed via the existing `migration_knowledge_vector_mr` infrastructure (the index label filter is widened to include `MigrationStep`).
 
---
 
## 4. JSON extraction schema redesign
 
### 4.1 What the first LLM call produces (unchanged)
 
The filter-and-group call (Phase 5 of the pipeline) is retained exactly as it is. It produces a structured Markdown document with seven severity sections, each containing a table with four columns: `#`, `JIRA`, `Title`, `Impact`.
 
```markdown
## 🔴 Breaking Changes
 
| # | JIRA       | Title                                    | Impact                                           |
|---|------------|------------------------------------------|--------------------------------------------------|
| 1 | SPR-18552  | WebSecurityConfigurerAdapter removed     | WebSecurityConfigurerAdapter is removed. Migrate |
|   |            |                                          | to a SecurityFilterChain @Bean. Inject           |
|   |            |                                          | HttpSecurity. Verify: /actuator/health 200.      |
 
## 🟠 Mandatory Migrations — Security & CVE Fixes
...
```
 
The section emoji maps deterministically to a `source_section` value:
 
| Section header | `source_section` value |
|---|---|
| 🔴 Breaking Changes | `breaking_change` |
| 🟠 Mandatory Migrations — Security & CVE Fixes | `security_fix` |
| 🟠 Mandatory Migrations — Major Component Upgrades | `component_upgrade` |
| 🟠 Mandatory Migrations — Security Configuration | `security_config` |
| 🟡 Behavioral Changes | `behavioral` |
| 🟡 Deprecations | `deprecation` |
| 🔵 Notable New Capabilities | `new_capability` |
 
The second LLM call reads `source_section` directly from the section header. It does not re-classify severity.
 
### 4.2 Full new JSON schema
 
```json
{
  "entities": [
    {
      "source_section":  "breaking_change",
      "title":           "WebSecurityConfigurerAdapter removed",
      "jira_keys":       ["SPR-18552"],
      "source_url":      "https://github.com/spring-projects/spring-security/releases/tag/6.0.0",
 
      "change_type":     "breaking_change",
      "reason_type":     "spec_compliance",
      "reason":          "WebSecurityConfigurerAdapter was removed in Spring Security 6. The adapter pattern is replaced by a component-based model where security configuration is expressed as a SecurityFilterChain bean.",
 
      "scopes": [
        { "scope": "api-surface", "severity": "critical" }
      ],
 
      "entities": [
        {
          "kind": "class",
          "name": "org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter",
          "role": "removed"
        },
        {
          "kind": "class",
          "name": "org.springframework.security.web.SecurityFilterChain",
          "role": "replacement"
        },
        {
          "kind": "class",
          "name": "org.springframework.security.config.annotation.web.builders.HttpSecurity",
          "role": "co-required"
        }
      ],
 
      "steps": [
        {
          "index":        0,
          "step_type":    "remove",
          "summary":      "Delete WebSecurityConfigurerAdapter subclass",
          "instruction":  "Remove the class that extends WebSecurityConfigurerAdapter. Copy the configure(HttpSecurity) method body — it will move into the new bean.",
          "effort":       "moderate",
          "automatable":  false,
          "requires":     [],
          "verification": "No import of WebSecurityConfigurerAdapter remains in the codebase.",
          "cli_operation": ""
        },
        {
          "index":        1,
          "step_type":    "replace",
          "summary":      "Define SecurityFilterChain @Bean",
          "instruction":  "Create a @Configuration class with a @Bean method that accepts HttpSecurity and returns SecurityFilterChain. Port the security rules from the removed configure() method into the lambda passed to http.authorizeHttpRequests().",
          "effort":       "moderate",
          "automatable":  false,
          "requires":     [0],
          "verification": "Application starts without NoSuchBeanDefinitionException. GET /actuator/health returns 200 without authentication.",
          "cli_operation": ""
        }
      ],
 
      "subsystem": ""
    }
  ]
}
```
 
### 4.3 Field-by-field specification
 
#### Identity fields (read directly from filtered Markdown, not re-derived)
 
| Field | Type | Source | Rule |
|---|---|---|---|
| `source_section` | string enum | Section emoji heading | Copy verbatim using the deterministic emoji → enum map. Never re-classify. |
| `title` | string | `Title` column of filtered MD table | Copy verbatim. Maximum 15 words. Do not paraphrase. |
| `jira_keys` | string[] | `JIRA` column of filtered MD table | Split on comma. Strip whitespace. Empty list if column is `N/A`. |
| `source_url` | string | `Source` column of raw MD (carried through by filter call) | URL string. Empty string if not available. |
 
#### Classification fields (LLM inferred from Impact text)
 
| Field | Type | Required | Values | Guidance |
|---|---|---|---|---|
| `change_type` | string | Yes | `breaking_change`, `mandatory_migration`, `dependency_upgrade`, `deprecation`, `behavior_change`, `configuration_change`, `namespace_migration`, `informational`, `other` | Use `source_section` as the primary signal. `breaking_change` section → `breaking_change`. Do not contradict the section classification. |
| `reason_type` | string | Optional | `security`, `performance`, `spec_compliance`, `dependency_alignment`, `bugfix`, `other`, empty | Why the change happened. |
| `reason` | string | Yes | — | 1–3 sentences: what changed, why it matters for upgraders, compatibility and behaviour impact. Do not invent. Use only the Impact text. |
 
#### Scopes (LLM inferred from Impact text)
 
| Field | Type | Required | Description |
|---|---|---|---|
| `scopes` | array of `{scope, severity}` | Yes, at least one | Assess the blast radius of the Impact text. A single rule may have multiple scopes. A configuration-only rename might be `config/low`. Removal of a public class is `api-surface/critical`. |
 
`scope` values: `api-surface`, `runtime`, `config`, `build`, `test`.
`severity` values: `low`, `medium`, `high`, `critical`.
 
#### Entities (LLM inferred, replaces all flat `affected_*` arrays)
 
| Field | Type | Description |
|---|---|---|
| `entities` | array of `{kind, name, role}` | One entry per artifact named in the Impact text |
| `kind` | string enum | `class` \| `property` \| `dependency` |
| `name` | string | FQCN for classes, dotted key for properties, `groupId:artifactId` for dependencies |
| `role` | string enum | `removed` \| `replacement` \| `co-required` \| `mentioned` |
 
**Role assignment rules:**
- `removed` — the Impact text says this entity is removed, deleted, eliminated, or no longer available.
- `replacement` — the Impact text says to use this instead, or this replaces the removed entity.
- `co-required` — the Impact text says this must also be configured, injected, or added alongside the replacement.
- `mentioned` — the entity is named in the Impact text but none of the above roles apply. Use sparingly; prefer omitting if the entity adds no information.
One rule may have multiple `removed` entities and multiple `replacement` entities. When there is a clear one-to-one mapping, the `REPLACED_BY` edge is derived at population time by matching `removed` and `replacement` entities of the same `kind`. When the mapping is many-to-many, all `REPLACED_BY` edges are created (cross-product).
 
Do not extract entities not named in the Impact text.
 
#### Steps (LLM decomposed from Impact text, replaces `action_step` blob)
 
| Field | Type | Required | Description |
|---|---|---|---|
| `index` | integer | Yes | 0-based position in this entity's step sequence |
| `step_type` | string enum | Yes | `remove` \| `rename` \| `replace` \| `configure` \| `verify` \| `namespace` |
| `summary` | string | Yes | Ten words or fewer. What this step does. |
| `instruction` | string | Yes | Full concrete action. What to change, where, and how. Must not be vague. "Review configuration" is not acceptable. "Rename `spring.datasource.url` to `spring.datasource.jdbc-url` in all `application*.yml` files" is acceptable. |
| `effort` | string enum | Yes | `mechanical` \| `moderate` \| `architectural` |
| `automatable` | boolean | Yes | True only if a tool can apply this step without any human judgement. A rename is automatable. A security architecture change is not. When in doubt, false. |
| `requires` | integer[] | Yes | Indices of steps (within this entity's step list) that must complete before this step can execute. Empty list if no prerequisites. |
| `verification` | string | Yes | An observable signal that confirms this step succeeded. Something the developer or a test can check. Must not be vague. "Compilation succeeds and no import of the old class remains" is acceptable. "Test the application" is not. |
| `cli_operation` | string | No | WildFly CLI fragment only. Empty string for Spring Boot and Angular. |
 
**Step decomposition guidance:**
- One step = one atomic action that can be verified independently.
- If the Impact text describes two sequential actions (remove X, then add Y), those are two steps with `requires: [0]` on the second.
- If the Impact text describes parallel actions that can be done in any order, those are two steps both with `requires: []`.
- Do not invent steps not supported by the Impact text.
- The verification for the final step in a sequence should confirm the overall outcome, not just the last action.
- Mark `automatable: true` only for steps of type `rename`, `namespace`, or `configure` where the change is purely mechanical and no judgement is required.
#### Framework-specific field
 
| Field | Type | Description |
|---|---|---|
| `subsystem` | string | WildFly subsystem name (`undertow`, `elytron`, `messaging`, etc.). Empty string for Spring Boot and Angular. |
 
### 4.4 Fields removed from the old schema and why
 
| Old field | Why removed |
|---|---|
| `action_step` | Replaced by `steps[]` array. The blob cannot be ordered, cannot express prerequisites, cannot carry individual automation flags, and cannot carry per-step verification signals. |
| `affected_classes` | Replaced by `entities[]` with `kind: "class"`. Flat list loses role semantics — which class is removed and which is the replacement cannot be determined. |
| `replacement_class` | Replaced by `role: "replacement"` on the relevant entity. A single string cannot express multiple replacements. |
| `affected_properties` | Replaced by `entities[]` with `kind: "property"`. |
| `replacement_property` | Replaced by `role: "replacement"` on the relevant entity. |
| `affected_dependencies` | Replaced by `entities[]` with `kind: "dependency"`. |
| `replacement_dependency` | Replaced by `role: "replacement"` on the relevant entity. |
 
### 4.5 Pydantic model
 
```python
from pydantic import BaseModel, Field
from typing import Literal, List, Optional
from enum import Enum
 
class EntityKind(str, Enum):
    CLASS      = "class"
    PROPERTY   = "property"
    DEPENDENCY = "dependency"
 
class EntityRole(str, Enum):
    REMOVED      = "removed"
    REPLACEMENT  = "replacement"
    CO_REQUIRED  = "co-required"
    MENTIONED    = "mentioned"
 
class StepType(str, Enum):
    REMOVE    = "remove"
    RENAME    = "rename"
    REPLACE   = "replace"
    CONFIGURE = "configure"
    VERIFY    = "verify"
    NAMESPACE = "namespace"
 
class Effort(str, Enum):
    MECHANICAL    = "mechanical"
    MODERATE      = "moderate"
    ARCHITECTURAL = "architectural"
 
class ScopeLevel(str, Enum):
    API_SURFACE = "api-surface"
    RUNTIME     = "runtime"
    CONFIG      = "config"
    BUILD       = "build"
    TEST        = "test"
 
class Severity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"
 
class AffectedEntity(BaseModel):
    kind: EntityKind
    name: str = Field(
        description="FQCN for classes, dotted key for properties, groupId:artifactId for deps"
    )
    role: EntityRole
 
class BreakingScopeInput(BaseModel):
    scope:    ScopeLevel
    severity: Severity
 
class MigrationStep(BaseModel):
    index:        int   = Field(description="0-based position in this entity's step sequence")
    step_type:    StepType
    summary:      str   = Field(description="Ten words or fewer — what this step does")
    instruction:  str   = Field(description="Concrete action: what to change, where, how")
    effort:       Effort
    automatable:  bool  = Field(
        description="True only if a tool can apply this without human review"
    )
    requires:     List[int] = Field(
        default_factory=list,
        description="Indices of steps within this entity that must complete first"
    )
    verification: str   = Field(
        description="Observable signal that confirms this step succeeded"
    )
    cli_operation: str  = Field(
        default="",
        description="WildFly CLI fragment if applicable, empty otherwise"
    )
 
class MigrationEntity(BaseModel):
    # identity — read directly from filtered MD, not re-derived
    source_section: Literal[
        "breaking_change", "security_fix", "component_upgrade",
        "security_config", "behavioral", "deprecation", "new_capability"
    ]
    title:      str           = Field(description="Title column from filtered MD, verbatim")
    jira_keys:  List[str]     = Field(default_factory=list)
    source_url: str           = Field(default="")
 
    # classification — LLM inferred from Impact text
    change_type: str
    reason_type: Optional[str] = ""
    reason:      str
 
    # blast radius — LLM assessed from Impact text
    scopes: List[BreakingScopeInput] = Field(
        default_factory=list,
        description="At least one scope entry required"
    )
 
    # typed entity references — replaces all flat affected_* arrays
    entities: List[AffectedEntity] = Field(default_factory=list)
 
    # ordered steps — replaces action_step blob
    steps: List[MigrationStep] = Field(default_factory=list)
 
    # framework-specific
    subsystem: str = ""
 
class MigrationEntitiesBatch(BaseModel):
    entities: List[MigrationEntity]
```
 
### 4.6 Updated extraction prompt instructions for the second LLM call
 
The prompt preamble changes from "analyze the structured changelog and extract all migration-impacting changes" to the following more precise instruction:
 
```
You are reading a structured migration changelog that has already been filtered,
deduplicated, and categorised by a prior analysis step. Your job is to decompose
each table row into a typed, machine-readable entity for graph population.
 
For each row in each table:
 
1. SOURCE SECTION: Read the section heading emoji.
   🔴 → "breaking_change"
   🟠 Security & CVE → "security_fix"
   🟠 Major Component → "component_upgrade"
   🟠 Security Configuration → "security_config"
   🟡 Behavioral → "behavioral"
   🟡 Deprecations → "deprecation"
   🔵 New Capabilities → "new_capability"
 
2. TITLE: Copy the Title column value verbatim. Do not paraphrase.
 
3. JIRA KEYS: Copy the JIRA column value. Split on comma. If the value is
   "N/A", produce an empty list.
 
4. REASON: Write 1-3 sentences from the Impact text — what changed, why it
   matters for upgraders. Do not invent. Use only information in the Impact text.
 
5. SCOPES: Assess the blast radius of the Impact text. Produce at least one
   scope entry. A single row may have multiple scopes. Use the definitions:
   api-surface = public API or class removed/changed
   runtime = default behaviour or lifecycle changed
   config = application.yml / properties keys only
   build = pom.xml, build.gradle, or plugin configuration
   test = test code or test configuration only
   Severity: critical = will definitely cause failure; high = likely causes
   failure; medium = may cause failure in some configurations; low = unlikely
   to cause failure but needs attention.
 
6. ENTITIES: List every class, property, or dependency named in the Impact text.
   Assign a role to each:
   removed = the Impact says this is removed, deleted, or no longer available
   replacement = the Impact says to use this instead
   co-required = the Impact says this must also be configured alongside the replacement
   mentioned = anything else (use sparingly)
   Use FQCNs for classes. Use dotted keys for properties. Use groupId:artifactId
   for dependencies. Do not invent names not present in the Impact text.
 
7. STEPS: Decompose the Impact into ordered, atomic actions. Each step must:
   - have a step_type (remove, rename, replace, configure, verify, namespace)
   - have a ten-word-or-fewer summary
   - have a concrete instruction (not vague)
   - declare effort (mechanical, moderate, architectural)
   - declare automatable (true ONLY for pure mechanical changes)
   - list requires[] as indices of prerequisite steps within this entity
   - have a verification signal (observable, not vague)
   Do not invent steps not supported by the Impact text. One atomic action = one step.
 
Do not invent entities, steps, or scope entries not supported by the Impact text.
Do not paraphrase the title. Do not re-classify the source_section.
Return only JSON matching the MigrationEntitiesBatch schema.
```
 
---
 
## 5. Graph population logic — what changes
 
### 5.1 MigrationRule population
 
New properties added at write time:
 
```cypher
MERGE (rule:MigrationRule {sourceUrl: $source_url})
ON CREATE SET
  rule.statement            = $reason,
  rule.title                = $title,
  rule.jiraKeys             = $jira_keys,
  rule.ruleType             = $source_section,
  rule.changeType           = $change_type,
  rule.reasonType           = $reason_type,
  rule.entityClassification = CASE
    WHEN size($steps) > 0 THEN 'actionable'
    WHEN size($entities) > 0 THEN 'incomplete'
    ELSE 'informational'
  END,
  rule.subsystem            = $subsystem
```
 
`ruleType` is now set directly from `source_section` — no substring mapping required. The mapping is:
 
| `source_section` | `ruleType` |
|---|---|
| `breaking_change` | `breaking` |
| `security_fix` | `mandatory_migration` |
| `component_upgrade` | `mandatory_migration` |
| `security_config` | `mandatory_migration` |
| `behavioral` | `behavioral` |
| `deprecation` | `deprecation` |
| `new_capability` | `behavioral` |
 
### 5.2 MigrationStep population
 
One node per step in the `steps[]` array. Nodes are keyed on `(ruleId, stepIndex)` for idempotency.
 
```cypher
MERGE (s:MigrationStep {ruleId: elementId(rule), stepIndex: $step.index})
ON CREATE SET
  s.stepType        = $step.step_type,
  s.summary         = $step.summary,
  s.instruction     = $step.instruction,
  s.effort          = $step.effort,
  s.automatable     = $step.automatable,
  s.verificationHint = $step.verification,
  s.cliOperation    = $step.cli_operation
MERGE (rule)-[:REQUIRES_STEP]->(s)
```
 
After all steps for a rule are written, `REQUIRES` edges are created by resolving the `requires[]` index list to node IDs:
 
```cypher
UNWIND $step_pairs AS pair
MATCH (cur:MigrationStep {ruleId: $rule_id, stepIndex: pair.current})
MATCH (pre:MigrationStep {ruleId: $rule_id, stepIndex: pair.prereq})
MERGE (cur)-[:REQUIRES]->(pre)
```
 
### 5.3 BreakingScope population
 
`BreakingScope` nodes are shared across rules. A `(scope, severity)` pair is a single node.
 
```cypher
UNWIND $scopes AS sc
MERGE (bs:BreakingScope {scope: sc.scope, severity: sc.severity})
MERGE (rule)-[:HAS_SCOPE]->(bs)
```
 
### 5.4 Entity population with typed roles
 
For each entry in `entities[]`:
 
```cypher
// Create or match the entity node
CALL {
  WITH ent
  CASE ent.kind
    WHEN 'class'      THEN MERGE (e:Class {name: ent.name}) RETURN e
    WHEN 'property'   THEN MERGE (e:ApplicationProperty {name: ent.name}) RETURN e
    WHEN 'dependency' THEN MERGE (e:Dependency {name: ent.name}) RETURN e
  END
} AS e
 
// Rule-level AFFECTS edge with role (backward compatible)
CALL {
  WITH rule, ent, e
  CASE ent.kind
    WHEN 'class'      THEN MERGE (rule)-[r:AFFECTS_CLASS]->(e) SET r.role = ent.role
    WHEN 'property'   THEN MERGE (rule)-[r:AFFECTS_PROPERTY]->(e) SET r.role = ent.role
    WHEN 'dependency' THEN MERGE (rule)-[r:AFFECTS_DEPENDENCY]->(e) SET r.role = ent.role
  END
}
 
// Step-level AFFECTS edges on remove/replace/rename steps
MATCH (s:MigrationStep)-[:REQUIRES_STEP]-(rule)
WHERE s.stepType IN ['remove', 'replace', 'rename']
CALL {
  WITH s, ent, e
  CASE ent.kind
    WHEN 'class'      THEN MERGE (s)-[r:AFFECTS_CLASS]->(e) SET r.role = ent.role
    WHEN 'property'   THEN MERGE (s)-[r:AFFECTS_PROPERTY]->(e) SET r.role = ent.role
    WHEN 'dependency' THEN MERGE (s)-[r:AFFECTS_DEPENDENCY]->(e) SET r.role = ent.role
  END
}
 
// Lifecycle edges derived from role
WITH e, ent, v
CALL {
  WITH e, ent, v
  CASE ent.role
    WHEN 'removed'      THEN MERGE (e)-[:REMOVED_IN]->(v) MERGE (v)-[:REMOVES]->(e)
    WHEN 'replacement'  THEN MERGE (e)-[:INTRODUCED_IN]->(v) MERGE (v)-[:INTRODUCES]->(e)
  END
}
```
 
### 5.5 REPLACED_BY derivation
 
After all entities for a rule are written, `REPLACED_BY` edges are derived by pairing `removed` and `replacement` entities of matching `kind`:
 
```cypher
// For each (removed, replacement) pair of the same kind within this rule
UNWIND $replacement_pairs AS pair
MATCH (old {name: pair.removed_name})
MATCH (new {name: pair.replacement_name})
MERGE (old)-[:REPLACED_BY]->(new)
```
 
`replacement_pairs` is computed in application code from the `entities[]` list: for each `removed` entity of `kind=X`, pair it with every `replacement` entity of `kind=X`.
 
---
 
## 6. New and updated MCP tools
 
### 6.1 New tool: `create_migration_context`
 
**Purpose:** Creates or resumes a `MigrationContext` node for a project upgrade session.
 
**Parameters:**
 
| Parameter | Type | Required | Description |
|---|---|---|---|
| `project_id` | string | yes | Stable project identifier (git repo path or service name) |
| `from_version` | string | yes | Current framework version |
| `to_version` | string | yes | Target framework version |
| `framework` | string | yes | `"Spring Boot"` or `"Angular"` |
| `scanned_entities` | string[] | yes | FQCNs, property keys, `groupId:artifactId` from codebase scan |
 
**Returns:** `{ contextId, status: "created"|"resumed", completedSteps, skippedSteps, queriedEntities }`
 
**Behaviour:** Idempotent on `(projectId, fromVersion, toVersion)`. If a context already exists, returns it without modification. The agent checks `status` to determine whether this is a new session or a resume.
 
**Cypher:**
 
```cypher
MERGE (ctx:MigrationContext {
  projectId:   $project_id,
  fromVersion: $from_version,
  toVersion:   $to_version
})
ON CREATE SET
  ctx.framework        = $framework,
  ctx.status           = "in-progress",
  ctx.createdAt        = datetime(),
  ctx.scannedEntities  = $scanned_entities,
  ctx.completedSteps   = [],
  ctx.skippedSteps     = [],
  ctx.queriedEntities  = {}
WITH ctx
MATCH (from_v:Version {framework: $framework, version: $from_version})
MATCH (to_v:Version   {framework: $framework, version: $to_version})
MERGE (ctx)-[:UPGRADES_FROM]->(from_v)
MERGE (ctx)-[:UPGRADES_TO]->(to_v)
RETURN elementId(ctx) AS contextId, ctx.status,
       ctx.completedSteps, ctx.skippedSteps
```
 
---
 
### 6.2 New tool: `get_pending_steps`
 
**Purpose:** Returns the remaining work queue for a migration context, in execution order, excluding completed and skipped steps.
 
**Parameters:**
 
| Parameter | Type | Required | Description |
|---|---|---|---|
| `context_id` | string | yes | `elementId` from `create_migration_context` |
| `effort_filter` | string[] | no | Restrict to specific effort levels, e.g. `["mechanical"]` for auto track only |
| `scope_filter` | string[] | no | Restrict to specific scopes, e.g. `["api-surface", "runtime"]` for tier 1 |
 
**Returns:** Array of step objects ordered by scope severity descending then topological step order. Each object: `{ stepId, stepType, summary, instruction, effort, automatable, verificationHint, requires: [stepId], recipeId, scope, severity }`.
 
**Cypher:**
 
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
  AND (size($effort_filter) = 0 OR s.effort IN $effort_filter)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
  WHERE size($scope_filter) = 0 OR bs.scope IN $scope_filter
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
  WHERE ab.auto = true AND ab.missingRequiredParams = []
OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
RETURN s, bs, rec.recipeId AS recipeId,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY
  CASE bs.severity
    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
    WHEN 'medium'   THEN 2 ELSE 3
  END ASC,
  s.stepType ASC
```
 
---
 
### 6.3 New tool: `update_step_status`
 
**Purpose:** Records the outcome of a step execution. This is the write that makes the harness interrupt-safe — called after every step, success or failure.
 
**Parameters:**
 
| Parameter | Type | Required | Description |
|---|---|---|---|
| `context_id` | string | yes | |
| `step_id` | string | yes | `elementId` of the `MigrationStep` node |
| `outcome` | string | yes | `"completed"` \| `"skipped"` \| `"failed"` |
| `reason` | string | no | Free text — "build passed", "user skipped: not applicable", "verify failed: ClassNotFoundException on startup" |
 
**Returns:** `{ contextId, completedCount, skippedCount, status }`. Status flips to `"complete"` automatically when no pending steps remain.
 
**Cypher:**
 
```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
CALL {
  WITH ctx
  CASE $outcome
    WHEN 'completed' THEN
      SET ctx.completedSteps = ctx.completedSteps + [$step_id]
    WHEN 'skipped' THEN
      SET ctx.skippedSteps = ctx.skippedSteps + [$step_id]
    WHEN 'failed' THEN
      SET ctx.failedSteps = coalesce(ctx.failedSteps, []) + [$step_id]
  END
}
// Auto-close if nothing remains pending (checked in application code)
RETURN elementId(ctx) AS contextId,
       size(ctx.completedSteps) AS completedCount,
       size(ctx.skippedSteps)   AS skippedCount,
       ctx.status
```
 
---
 
### 6.4 New tool: `get_steps_for_scope_tier`
 
**Purpose:** Returns only the scanned entities that have rules with steps at a given scope/severity tier. Used to drive scope-tiered querying in the query loop — the agent calls this before each tier to know which entities actually need querying, rather than querying all entities at every tier.
 
**Parameters:**
 
| Parameter | Type | Required | Description |
|---|---|---|---|
| `context_id` | string | yes | |
| `scope` | string | yes | e.g. `"api-surface"` |
| `min_severity` | string | yes | `"low"` \| `"medium"` \| `"high"` \| `"critical"` — return entities at this severity or above |
 
**Returns:** `{ entities: ["fqcn1", "prop.key2", ...], rule_count: n }` — only entities from `ctx.scannedEntities` that have graph hits at this scope tier.
 
---
 
### 6.5 New tool: `close_migration_context`
 
**Purpose:** Finalises a `MigrationContext` after migration is complete or abandoned. Sets `completedAt` and `status`. The context remains queryable for retrospectives.
 
**Parameters:**
 
| Parameter | Type | Required | Description |
|---|---|---|---|
| `context_id` | string | yes | |
| `final_status` | string | yes | `"complete"` \| `"partial"` \| `"abandoned"` |
| `notes` | string | no | Human-readable summary of what was done and what remains |
 
**Returns:** `{ contextId, completedSteps, skippedSteps, status }`
 
---
 
### 6.6 Updated tool: `analyze_upgrade_path`
 
**No parameter changes.** The tool gains the ability to filter by `BreakingScope` when the enhanced graph is populated. A new optional parameter is added:
 
| New parameter | Type | Default | Description |
|---|---|---|---|
| `scope_filter` | string[] | `[]` | If non-empty, return only rules that have at least one `HAS_SCOPE` edge to a `BreakingScope` node with a matching scope value |
| `min_severity` | string | `null` | If set, return only rules with severity at or above this level |
 
The JSON return format gains a `steps` array per rule and a `scopes` array per rule when the enhanced graph data is present. Old format is preserved when these fields are absent (older data).
 
---
 
### 6.7 Updated tool: `build_recipe_plan`
 
**No parameter changes.** The tool now operates at step level rather than rule level when `MigrationStep` nodes are present. The auto track includes only steps where `automatable=true AND effort='mechanical' AND ab.auto=true AND ab.missingRequiredParams=[]`. The manual track now emits step cards rather than rule cards, each with `instruction` and `verificationHint`.
 
---
 
## 7. Agent harness redesign — four runtime loops
 
The current five sequential phases are replaced by four re-entrant loops. Each loop checks `MigrationContext` before doing any work, skips what is already done, and writes its outcome back to the graph before yielding. The agent can be interrupted at any loop boundary and resume without repeating completed work.
 
### 7.1 Loop I — context
 
**Purpose:** Load or create a `MigrationContext`. Run the codebase scan. Surface version boundary pre-conditions.
 
**Steps:**
 
1. Check for existing `MigrationContext` by `projectId`. If found and `status=in-progress` or `status=blocked`: load `completedSteps[]`, `skippedSteps[]`, and `queriedEntities{}`. Log to the user that the session is being resumed.
2. If `status=complete`: surface the completion summary. Offer to start a new context for a different target version. Do not proceed to loops II–IV.
3. Run the codebase scan regardless of whether this is a new session or a resume. Entities may have changed since the last session. Use the patterns from `skill://framework-migration/scanning`: FQCNs from import lines, annotations without `@`, dotted property keys, `groupId:artifactId` without versions, exact npm package names.
4. If resuming: diff the new scan against `ctx.scannedEntities`. Any entity present in the new scan but not in `ctx.scannedEntities` is added to the query queue for loop II. This handles the case where a developer has already migrated some code and the set of relevant entities has changed.
5. Load `skill://framework-migration/version-map`. Surface any toolchain pre-conditions (Java version requirement, Node version requirement, etc.) before proceeding.
6. Call `create_migration_context` with the scanned entity list.
**Gate:** Never call any graph query tool before this loop completes.
 
---
 
### 7.2 Loop II — scope-gated query
 
**Purpose:** Query the graph for migration rules affecting the scanned entities, in priority order by blast radius. Skip entities already resolved in prior sessions.
 
**Tier structure:**
 
| Tier | Scope filter | Severity filter | Tools called |
|---|---|---|---|
| 1 | `api-surface` | `high`, `critical` | `get_steps_for_scope_tier` → `analyze_upgrade_path` → `resolve_deprecation` per `removed` entity → `entity_evolution` if partial chain |
| 2 | `runtime` | `medium`, `high`, `critical` | Same sequence, skipping entities already cached from tier 1 |
| 3 | `config`, `build` | all | `analyze_upgrade_path` with scope filter. `search_migration_knowledge` for entities with no graph hit |
| 4 | `test` | all | `analyze_upgrade_path`. Results are deferred and handled last in loop III. |
| — | Paysafe deps | — | `resolve_paysafe_dependency_by_service_name` for every `com.paysafe` dependency. Run concurrently with tier 1 — these are independent. |
 
**Skip guard:** Before any tool call, check `ctx.queriedEntities[entity_name]`. If the entity was queried in a prior session, its result is cached on context — do not re-issue the tool call unless `--force-refresh` is set.
 
**Decision logic within each tier:**
 
- `resolve_deprecation` returns full lifecycle (deprecated_in + removed_in + replaced_by): cache the result, skip `search_migration_knowledge` for this entity.
- `resolve_deprecation` returns partial lifecycle (deprecated_in but no replaced_by): call `entity_evolution` to trace the `REPLACED_BY` chain up to 5 hops. Then call `search_migration_knowledge`.
- `resolve_deprecation` returns no records: call `search_migration_knowledge`. If no result, mark the entity as "not in graph" on context — note it as unverified in the output.
- All steps for a rule are `automatable=true AND effort='mechanical'`: do not call `search_migration_knowledge`. Go directly to `build_recipe_plan` in loop III.
**After loop II completes:** Write the full query cache to `ctx.queriedEntities`. The loop is complete even if some entities had no graph hit — those will surface as unverified items in the output.
 
---
 
### 7.3 Loop III — execution
 
**Purpose:** Apply migration steps in order, verify each one, and mark it done. This is the loop the current harness does not have.
 
**Work queue:** Call `get_pending_steps` with no filters to get the full remaining queue. The queue is returned in scope-severity order (critical first) with topological step ordering within each rule.
 
**Step routing:**
 
| Condition | Track | Action |
|---|---|---|
| `step.automatable=true AND step.effort='mechanical' AND AUTOMATED_BY edge exists AND missingRequiredParams=[]` | Auto | Include in `rewrite.yml` batch. Apply via OpenRewrite. Run `skill://run-build-and-test/main`. On pass: call `update_step_status(outcome="completed")`. |
| `AUTOMATED_BY` exists but `missingRequiredParams` is non-empty | Prompted auto | Surface missing parameters to user. If user provides them, patch recipe params and retry auto track. Else route to manual. |
| `step.effort='moderate'` or no `AUTOMATED_BY` edge | Manual | Emit step card (summary, instruction, verificationHint) to user. Wait for confirmation. On confirm: `update_step_status(outcome="completed")`. On skip: `update_step_status(outcome="skipped", reason=user_reason)`. |
| `step.effort='architectural'` | Design gate | Pause loop. Emit a design decision prompt. Do not proceed until the user provides an explicit design choice. Record the choice on context as a note. Then route to manual. |
| Step has `REQUIRES` edge to a step not in `ctx.completedSteps` | Blocked | Do not execute. Re-queue behind the prerequisite. Surface the dependency to the user if the prerequisite is itself blocked. |
| Build fails after auto apply | Rollback | Load `skill://recipe-task-rollback/main`. Revert the applied changes. Call `update_step_status(outcome="failed", reason="build failed: [error]")`. Search `search_migration_knowledge` for the affected entity to find community workarounds. Escalate this step to manual track. |
| Verification hint check fails | Rollback | Same as build failure. The verification hint is the observable — if the hint says "no import of X remains" and imports of X are still present, the step failed. |
 
**Batching in the auto track:** Multiple mechanical steps from the same rule, or from different rules affecting the same entity, can be batched into a single `rewrite.yml` and applied together. The batch boundary is a single build-and-test cycle. If the batch fails, roll back the entire batch and escalate all steps in it to manual track individually.
 
**Interrupt safety:** `update_step_status` is called after every step, win or lose, before the agent moves to the next step. If the session ends mid-loop, the next session resumes from the first step not in `ctx.completedSteps` or `ctx.skippedSteps`.
 
---
 
### 7.4 Loop IV — feedback
 
**Purpose:** Return discovered knowledge to the graph and emit the remaining backlog.
 
**Steps:**
 
1. **Discover deviations.** Load `skill://generate-community-insights`. For each manual step where the developer's actual fix differed from `step.instruction` — identified by asking the developer explicitly — capture the actual solution.
2. **Submit workarounds.** For each discovered deviation, call `submit_migration_insight` with:
   - `statement`: description of the problem encountered
   - `solution`: the actual fix that worked
   - `spring_boot_version` (or Angular version): the `toVersion` from context
   - `affected_classes`, `affected_properties`, `affected_dependencies`: from the step's entity list
   - `confidence`: 0.9 if the build passed and tests passed after applying the workaround; 0.7 if only the build passed; 0.5 if the developer is uncertain
   - `evidence_url`: a link to the commit, PR, or documentation that confirms the workaround
3. **Emit backlog.** Load `skill://emit-migration-backlog/main`. For every step in `ctx.skippedSteps[]` where `effort` is not `test`, emit a backlog item. Each item includes:
   - The step `summary` and `instruction`
   - The step `verificationHint` (what done looks like)
   - The original `jiraKeys` from the parent `MigrationRule` for traceability
   - The `BreakingScope` severity for prioritisation in the backlog tool
4. **Close context.** Call `close_migration_context` with:
   - `final_status`: `"complete"` if all non-skipped steps are done; `"partial"` if skipped steps remain; `"abandoned"` if the migration is being intentionally halted
   - `notes`: a short summary of what was completed and what remains
**Value of loop IV:** Each `CommunityInsight` node written in step 2 is immediately available via `search_migration_knowledge` to any future agent performing the same version upgrade. Over multiple migrations, the knowledge graph compounds. The first team to upgrade hits an undocumented edge case and documents it. Every subsequent team finds that workaround in the hybrid search results and avoids the same failure.
 
---
 
### 7.5 Decision logic — complete reference
 
#### Context loop decisions
 
| Condition | Action |
|---|---|
| No context exists for `projectId` | Create context. Run full scan. |
| Context exists, `status=in-progress` | Load context. Run scan. Diff entities. Queue new entities for loop II. |
| Context exists, `status=blocked` | Load context. Report what is blocked. Ask user to resolve. Run scan. Continue. |
| Context exists, `status=complete` | Surface summary. Offer new context for different version. Stop. |
 
#### Query loop decisions
 
| Condition | Action |
|---|---|
| Entity in `ctx.queriedEntities` | Skip tool call. Read cached result from context. |
| `resolve_deprecation` returns full chain | Cache. Skip `search_migration_knowledge`. |
| `resolve_deprecation` returns partial chain | Call `entity_evolution`. Then call `search_migration_knowledge`. |
| `resolve_deprecation` returns no records | Call `search_migration_knowledge`. If still no result, mark as unverified. |
| All steps for rule are `automatable=true AND effort='mechanical'` | Skip `search_migration_knowledge`. Queue for auto track in loop III. |
| Entity name starts with `com.paysafe` | Call `resolve_paysafe_dependency_by_service_name` concurrently. Do not wait for it before proceeding with framework rule queries. |
 
#### Execution loop decisions
 
| Condition | Track | Action |
|---|---|---|
| `automatable=true AND effort='mechanical' AND ab.auto=true AND missingRequiredParams=[]` | Auto | Batch in `rewrite.yml`. Apply. Verify. Mark complete. |
| `automatable=true` but `missingRequiredParams` non-empty | Prompted | Surface missing params. If user fills them: retry auto. Else: manual. |
| `effort='moderate'` | Manual | Emit step card. Wait for user. |
| `effort='architectural'` | Design gate | Pause. Emit design decision. Wait. Then manual. |
| Prerequisites not complete | Blocked | Re-queue. Surface dependency. |
| Auto apply fails build | Rollback | Roll back. Mark failed. Search community insights. Escalate to manual. |
 
#### Feedback loop decisions
 
| Condition | Action |
|---|---|
| Developer's fix differed from `step.instruction` | `submit_migration_insight` with actual solution |
| Verify-fail step resolved by different approach | `submit_migration_insight` with workaround, confidence based on build result |
| Steps in `ctx.skippedSteps` with `effort ≠ 'test'` | Emit backlog item with traceability to original Jira keys |
| All non-skipped steps done | `close_migration_context(final_status="complete")` |
| Skipped steps remain | `close_migration_context(final_status="partial")` |
 
---
 
## 8. Backward compatibility contract
 
### What is guaranteed unchanged
 
- All existing `MigrationRule`, `Version`, `CommunityInsight`, `ApplicationProperty`, `Class`, `Dependency`, and `OpenRewriteRecipe` node labels and their existing properties.
- All existing relationship types: `INCLUDES_RULE`, `DISCOVERED_IN`, `SUPERSEDES`, `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, `AFFECTS_DEPENDENCY`, `AFFECTED_IN`, `REPLACED_BY`, `DEPRECATED_IN`, `REMOVED_IN`, `INTRODUCED_IN`, `DEPRECATES`, `REMOVES`, `INTRODUCES`, `AUTOMATED_BY` (rule-level), `AUTOMATES`, `COMPOSED_OF`, `TARGETS_VERSION`.
- All existing MCP tools and their parameters: `analyze_upgrade_path`, `build_recipe_plan`, `resolve_deprecation`, `search_migration_knowledge`, `search_openrewrite_recipes`, `entity_evolution`, `get_graph_schema`, `execute_custom_cypher`, `resolve_paysafe_dependency_by_service_name`, `install_migration_skill`, `submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight`.
- The `AUTOMATED_BY` edge schema and all its properties.
- The hybrid search infrastructure (BM25 + vector + RRF, all existing indexes).
- The filter-and-group LLM call (Phase 5 of the pipeline). Its prompt, output format, and cached artifact are unchanged.
- All skill resources at `skill://framework-migration/*` and the execution companion skills.
### What is added without breaking existing queries
 
- `MigrationStep`, `BreakingScope`, `MigrationContext` node labels — new, do not interfere with existing queries.
- `REQUIRES_STEP`, `REQUIRES`, `HAS_SCOPE`, `UPGRADES_FROM`, `UPGRADES_TO` relationship types — new.
- `role` property on `AFFECTS_*` edges — new optional property. Existing queries that do not read `role` continue to work.
- `title` and `jiraKeys` properties on `MigrationRule` — new optional properties.
- Step-level `AUTOMATED_BY` edges — new. Existing rule-level `AUTOMATED_BY` edges are retained.
### What changes in behaviour
 
- `entityClassification` on new `MigrationRule` nodes is derived from `steps[]` rather than from `action_step`. For nodes populated before the redesign, `entityClassification` retains its original value.
- `ruleType` on new `MigrationRule` nodes is set directly from `source_section` rather than via the substring mapping from `change_type`. For nodes populated before the redesign, `ruleType` retains its original value.
- `actionStep` is no longer written to new `MigrationRule` nodes. Existing nodes retain their `actionStep` values. Tools that read `actionStep` continue to work on old nodes.
### Queries that work on both old and new data
 
Any query that handles optionality correctly works across both old and new graph data. For example:
 
```cypher
MATCH (v:Version)-[:INCLUDES_RULE]->(r:MigrationRule)
WHERE v.framework = $framework
  AND v.sortableVersion > $from AND v.sortableVersion <= $to
OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
RETURN r, collect(s) AS steps, collect(bs) AS scopes
```
 
Rules without `MigrationStep` nodes (pre-redesign data) return `steps=[]`. Rules without `BreakingScope` nodes return `scopes=[]`. The agent handles both cases.
 
---
 
## 9. Migration path — implementing the redesign incrementally
 
The redesign can be delivered in three independent increments. Each increment is independently deployable and provides immediate value.
 
### Increment 1 — JSON schema and population (pipeline change only)
 
Update the Pydantic model to `MigrationEntitiesBatch` as specified in section 4.5. Update the extraction prompt as specified in section 4.6. Update the graph population code to write `MigrationStep`, `BreakingScope`, and typed `AFFECTS_*` roles as specified in section 5.
 
**Scope:** Changes to `export_extract_populate_framework.py` and the Pydantic model file only. No MCP server changes. No harness changes.
 
**Value delivered:** New graph population runs produce richer nodes immediately. Existing nodes are unaffected. Operators can run `--force-llm` on any version to re-extract with the new schema.
 
**Validation:** Run the pipeline on a known version range (e.g. Spring Boot 3.3.0 to 3.4.0). Verify that `MigrationStep` nodes are created with the expected properties. Verify that `AFFECTS_CLASS` edges carry a `role` property. Verify that `BreakingScope` nodes exist and are linked via `HAS_SCOPE`. Verify that the existing `analyze_upgrade_path` query still returns correct results for this version range.
 
### Increment 2 — New MCP tools (server change only)
 
Implement the five new MCP tools specified in section 6: `create_migration_context`, `get_pending_steps`, `update_step_status`, `get_steps_for_scope_tier`, `close_migration_context`.
 
Update `analyze_upgrade_path` to accept the new optional `scope_filter` and `min_severity` parameters.
 
Update `build_recipe_plan` to operate at step level when `MigrationStep` nodes are present.
 
**Scope:** Changes to the MCP server only. No pipeline changes. No harness skill changes.
 
**Value delivered:** The tools are available to any agent immediately. The existing harness can start using `get_pending_steps` and `update_step_status` without waiting for harness redesign.
 
**Validation:** Create a `MigrationContext` for a test project. Call `get_pending_steps` and verify the returned order matches scope-severity priority. Call `update_step_status` and verify the step ID appears in `ctx.completedSteps`. Call `get_pending_steps` again and verify the completed step is absent.
 
### Increment 3 — Agent harness (skill resource change only)
 
Update `skill://framework-migration/main` to implement the four-loop harness as specified in section 7.
 
Update the tool selection logic to use scope-tiered querying and the skip guards specified in section 7.2.
 
Add the execution loop (section 7.3) and feedback loop (section 7.4) to the skill.
 
**Scope:** Changes to the skill Markdown resources served by the MCP server. The skill is loaded by agents at runtime — no agent binary changes required.
 
**Value delivered:** Agents using the updated skill immediately benefit from stateful execution, scope-gated querying, per-step verification, and the community insight feedback path.
 
**Validation:** Run a full end-to-end migration session using the updated skill on a project with a known upgrade path (e.g. Spring Boot 3.2 to 3.4). Interrupt the session mid-way. Resume using the same `projectId`. Verify that no completed steps are re-executed. Verify that the `MigrationContext` node in the graph reflects the correct `completedSteps` list after the resumed session completes.
 
---
 
*End of redesign document.*
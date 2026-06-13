# Feature Specification: MCP Live-Probe Fixes

**Feature Branch**: `011-mcp-live-probe-fixes`

**Created**: 2026-06-11

**Status**: Draft

**Source**: `ISSUES.md` — live probe of `http://localhost:8080/sse` on 2026-06-11, simulating a
Spring Boot 3.5.0 → 4.0.0 migration for `paysafe-wallet-switch`.

## Overview

The live probe of the running MCP server found ten defects that break or degrade the migration
orchestration loop. They fall into two layers:

- **MCP server-code defects** (Issues 1, 3, 4, 8, 10) — wrong Cypher, missing parameter
  normalization, hardcoded fields, unbounded network calls.
- **Graph data / ingestion defects** (Issues 2, 5, 6, 7, 9) — nodes, properties, relationships, and
  index population that the ingestion pipeline never produced, leaving fully-implemented tools with
  nothing to return.

Two findings **supersede decisions made in spec 010** and are called out where they appear:

- Issue 1 contradicts 010's FR-005 (store `stepNotes` as a Neo4j map property) — that approach is
  the confirmed bug. 011 stores step outcomes as a relationship.
- Issues 3 & 4 contradict 010's FR-017 (standardize on the `"spring-boot"` slug) — the tool must
  accept `"Spring Boot"` like every other tool.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent Advances Through the Migration Checklist (Priority: P1) — Issue 1

A developer's agent works through the 108 pending steps for the 3.5→4.0 migration. After handling
each step it calls `update_step_status(context_id, step_id, status="completed", reason="...")`.
Previously every call threw a Neo4j `TypeError` (the tool tried to store a map-valued node
property), so the agent treated every step as failed even though `completedSteps` had advanced.
After this fix, the call succeeds, the outcome and reason are persisted, and the agent advances
reliably.

**Why this priority**: This breaks the core orchestration loop. Without it, no agent can track
progress through the checklist, regardless of which other tools work.

**Independent Test**: Call `update_step_status` with a non-empty `reason` against a real context and
step; verify the call returns success (no `TypeError`) and that the outcome + reason are retrievable
on a subsequent read.

**Acceptance Scenarios**:

1. **Given** a valid context and step, **When** `update_step_status(status="completed", reason="Already handled in migration")` is called, **Then** it returns success with no Neo4j `TypeError`, and a `STEP_OUTCOME` relationship carrying `status` and `reason` exists between the context and the step.
2. **Given** the same step is updated twice, **When** `update_step_status` is called again with a new status, **Then** the existing `STEP_OUTCOME` relationship is updated in place (no duplicate relationship is created).
3. **Given** `update_step_status` is called without a `reason`, **Then** the call still succeeds and the `reason` on the relationship is null/absent (no map property is written anywhere).

---

### User Story 2 — Agent Auto-Applies OpenRewrite Recipes (Priority: P1) — Issue 2

The agent calls `build_recipe_plan`, which depends on `search_openrewrite_recipes` to find
applicable recipes. Previously the search returned 0 hits for every query despite 333
`OpenRewriteRecipe` nodes existing, so `auto_track` was always empty and the entire automated
migration path was dead. After this fix, recipe search returns relevant recipes and `build_recipe_plan`
populates `auto_track`.

**Why this priority**: The auto-migration track is completely non-functional; all 333 recipes are
invisible to agents.

**Independent Test**: Run `search_openrewrite_recipes(query="Spring Boot upgrade 4.0")` and verify a
non-empty hit list; confirm the `openrewrite_recipe_description` fulltext index is `ONLINE` and every
`OpenRewriteRecipe` node has populated `description` and `displayName`.

**Acceptance Scenarios**:

1. **Given** 333 `OpenRewriteRecipe` nodes with populated `description`/`displayName` and an `ONLINE` fulltext index, **When** `search_openrewrite_recipes(query="Spring Boot upgrade")` is called, **Then** it returns a non-empty `hits` list.
2. **Given** the same data, **When** `build_recipe_plan` is called for a 3.5→4.0 migration, **Then** `auto_track` contains at least one applicable recipe.
3. **Given** the validation query `MATCH (r:OpenRewriteRecipe) RETURN count(r), count(r.description), count(r.displayName)`, **Then** all three counts are equal (no recipe lacks the indexed properties).

---

### User Story 3 — Agent Checks a Target Version Using the Standard Framework Name (Priority: P1) — Issues 3 & 4

Before starting, the agent calls `check_version_availability(framework="Spring Boot", version="4.0.0")`
— the same `"Spring Boot"` spelling the other ten tools require. Previously this returned
`unsupported_framework`, and even the `"spring-boot"` spelling returned `exists_in_graph: false`
because the internal query filtered on the wrong casing. After this fix, any accepted spelling
resolves correctly and the graph lookup matches the stored `"Spring Boot"` Version nodes.

**Why this priority**: An agent using the consistent framework name can never get a correct answer
from this tool today, and may refuse to proceed with a valid migration.

**Independent Test**: Call `check_version_availability("Spring Boot", "4.0.0")` and
`check_version_availability("spring-boot", "4.0.0")` against a graph containing
`Version {version:"4.0.0", framework:"Spring Boot"}`; verify both return `exists_in_graph: true`.

**Acceptance Scenarios**:

1. **Given** a `Version {version:"4.0.0", framework:"Spring Boot"}` node, **When** `check_version_availability("Spring Boot", "4.0.0")` is called, **Then** it returns `exists_in_graph: true` (no `unsupported_framework` error).
2. **Given** the same node, **When** the tool is called with `"spring-boot"`, `"spring boot"`, or `"Spring Boot"`, **Then** all three resolve to the same canonical framework and return `exists_in_graph: true`.
3. **Given** an unknown framework value, **When** the tool is called, **Then** it returns a structured `unsupported_framework` error listing the supported framework display names, without a network call.

---

### User Story 4 — Agent Looks Up What Replaces a Deprecated Class (Priority: P2) — Issue 5

The agent calls `resolve_deprecation(entity_name="RestTemplate", framework="Spring Boot")` and
`entity_evolution(entity_name="WebMvcConfigurer", framework="Spring Boot")` for the common
deprecated Spring Boot classes. Previously all returned `not_found` / empty chains because those
classes were never materialised as nodes. After this fix, the well-known deprecated classes are
present with `DEPRECATED_IN` and `REPLACED_BY` edges, so deprecation lookups and evolution chains
resolve.

**Why this priority**: Forces agents to fall back to generic search for the most common migration
entities; precise deprecation tracking is unavailable.

**Independent Test**: After ingestion, call `resolve_deprecation("RestTemplate", "Spring Boot")` and
verify `status != not_found`; call `entity_evolution("WebMvcConfigurer", "Spring Boot")` and verify a
non-empty chain.

**Acceptance Scenarios**:

1. **Given** the curated deprecated-class seed for Spring Boot 3.x has been ingested, **When** `resolve_deprecation("RestTemplate", "Spring Boot")` is called, **Then** it returns the deprecating version and replacement (status is not `not_found`).
2. **Given** the same seed, **When** `entity_evolution("WebMvcConfigurer", "Spring Boot")` is called, **Then** the returned chain is non-empty.
3. **Given** an entity not in the graph, **When** `resolve_deprecation` is called, **Then** it returns `not_found` (existing behaviour preserved).

---

### User Story 5 — Agent Prioritizes Rules by Severity and Change Type (Priority: P2) — Issue 6

The agent calls `analyze_upgrade_path` and receives rules whose `title`, `severity`, `change_type`,
and `reason` are populated, so it can sort build-breaking removals ahead of best-practice
recommendations. Previously every rule returned these as `null`. After this fix, the query projects
the stored rule properties and the linked `BreakingScope.severity`, and ingestion sets the missing
`framework` property and guarantees a scope edge.

**Why this priority**: Without `severity`/`change_type` agents cannot prioritise or route migration
work; the rule list is an undifferentiated blob.

**Independent Test**: Call `analyze_upgrade_path(framework="Spring Boot", from="3.5.0", to="4.0.0")`
and verify each returned rule has non-null `title`, `severity`, and `change_type`.

**Acceptance Scenarios**:

1. **Given** ingested `MigrationRule` nodes with `title`, `changeType`, `statement`, and a `HAS_SCOPE → BreakingScope` edge, **When** `analyze_upgrade_path` is called, **Then** each rule's `title`, `change_type`, `reason`, and `severity` response fields are populated from those properties.
2. **Given** the validation query `MATCH (mr:MigrationRule) RETURN keys(mr)`, **Then** the key set includes `framework`, `title`, `changeType`, and `statement`.
3. **Given** the validation query `MATCH (mr:MigrationRule)-[:HAS_SCOPE]->(bs) RETURN count(*)`, **Then** the count is non-zero.

---

### User Story 6 — Agent Filters Steps by Scope Tier (Priority: P2) — Issue 7

The agent calls `get_steps_for_scope_tier(context_id, scope="build")` to tackle build-system changes
first. Previously this always returned 0 because no `BreakingScope` data was reachable and scopeless
steps were dropped. After this fix, ingestion populates `HAS_SCOPE → BreakingScope` edges, and the
query returns steps that match the requested scope **plus** steps with no scope (returned with
`scope: null`) rather than silently dropping them.

**Why this priority**: The scope-filtered orchestration pattern — the recommended first call — always
returns empty today, stalling agents that follow it.

**Independent Test**: Against a context whose path includes rules with and without a `BreakingScope`,
call `get_steps_for_scope_tier(scope="build")` and verify scoped steps return with their scope and
scopeless steps return with `scope: null`; total > 0.

**Acceptance Scenarios**:

1. **Given** rules with `HAS_SCOPE → BreakingScope {scope:"build"}`, **When** `get_steps_for_scope_tier(scope="build")` is called, **Then** the matching steps are returned with `scope:"build"` and `severity` populated.
2. **Given** rules with no `BreakingScope`, **When** `get_steps_for_scope_tier` is called, **Then** those steps are still returned with `scope: null` (not dropped).
3. **Given** a context with 108 pending steps via `get_pending_steps`, **When** `get_steps_for_scope_tier` is called for any valid scope, **Then** `total > 0`.

---

### User Story 7 — Agent Sees the Source Version of Each Pipeline Run (Priority: P3) — Issue 8

The agent calls `list_pipeline_runs` to find the migration path closest to the project's current
version. Previously `from_version` was `""` for all 20 runs. After this fix, each run reports the
correct `from_version`.

**Why this priority**: Low — agents can fall back to Cypher, but the response is incomplete and the
fix is cheap.

**Independent Test**: Call `list_pipeline_runs` and verify every run has a non-empty `from_version`
that matches the value encoded in its artifact filename.

**Acceptance Scenarios**:

1. **Given** Version nodes with a stored `fromVersion` property, **When** `list_pipeline_runs` is called, **Then** each run's `from_version` equals the stored value.
2. **Given** a Version node ingested before this fix (no `fromVersion` property), **When** `list_pipeline_runs` is called, **Then** `from_version` is parsed from the artifact filename pattern `<framework>-<from>-to-<to>-changes`.
3. **Given** a run whose filename does not match the pattern and whose node has no `fromVersion`, **When** `list_pipeline_runs` is called, **Then** `from_version` is `""` (graceful, no exception).

---

### User Story 8 — Agent Receives Phase-Level Lifecycle Alerts (Priority: P3) — Issue 9

The agent calls `analyze_upgrade_path(..., include_lifecycle=True)` and receives phase-level alerts
(e.g. "Spring Security 7 changes the default CSRF policy"). Previously `lifecycle_alerts` was always
empty because no `LifecycleAlert` nodes existed. After this fix, ingestion seeds `LifecycleAlert`
nodes linked to the relevant `Version`.

**Why this priority**: Low — guidance is complete at the rule level; alerts add high-level context.

**Independent Test**: Ingest the curated lifecycle-alert seed for 3.5→4.0; call `analyze_upgrade_path`
with `include_lifecycle=True` and verify `lifecycle_alerts` is non-empty.

**Acceptance Scenarios**:

1. **Given** `LifecycleAlert` nodes linked to the `4.0.0` Version, **When** `analyze_upgrade_path(include_lifecycle=True)` is called, **Then** `lifecycle_alerts` is non-empty.
2. **Given** `include_lifecycle=False`, **When** the tool is called, **Then** `lifecycle_alerts` is empty regardless of seeded data.
3. **Given** ingestion is re-run, **When** the seed is applied again, **Then** no duplicate `LifecycleAlert` nodes are created (idempotent MERGE).

---

### User Story 9 — Agent Resolves a Paysafe Service Dependency Without Hanging (Priority: P3) — Issue 10

The agent calls `resolve_paysafe_dependency_by_service_name(service_name="paysafe-wallet-switch")`.
Previously the call hung (the FindIt lookup had no timeout) and the probe client timed out at 5s.
After this fix, every network call in the resolver is bounded, and on timeout or unavailability the
tool returns a structured error instead of hanging.

**Why this priority**: Low — supplementary tool — but a hang stalls the agent.

**Independent Test**: Simulate an unresponsive FindIt backend; verify the tool returns a structured
error within the configured timeout rather than hanging.

**Acceptance Scenarios**:

1. **Given** the FindIt backend does not respond, **When** `resolve_paysafe_dependency_by_service_name` is called, **Then** it returns a structured error within the configured timeout (no indefinite hang).
2. **Given** FindIt responds normally, **When** the tool is called for a registered service, **Then** it returns the resolved dependency as today.
3. **Given** the service is not registered, **When** the tool is called, **Then** it returns a structured `not_found`-style result, not a timeout.

---

### Edge Cases

- `update_step_status` called with a `step_id` that does not exist on the context's path → return a structured error; do not create an orphan `STEP_OUTCOME` relationship.
- `check_version_availability` called with a framework whose casing is accepted but whose Maven coordinates are unknown → resolve the framework for the graph lookup but return `ga_available: false` with a hint (graph check still works even when the Maven mapping is absent).
- `search_openrewrite_recipes` run before `ensure_indexes()` has completed (index still `POPULATING`) → return 0 hits without raising; the validation gate (US2 AS3) catches the unpopulated-data case at deploy time.
- `get_steps_for_scope_tier` called on a path where *no* rule has a `BreakingScope` → return all steps with `scope: null` (never an empty list when pending steps exist).
- `list_pipeline_runs` filename parse must not misfire on frameworks whose display name contains a hyphen — anchor on the `-to-` separator and trailing `-changes` token.
- Re-running ingestion must not duplicate seeded deprecated-class nodes, `LifecycleAlert` nodes, or their edges.

## Requirements *(mandatory)*

### Functional Requirements

**update_step_status (Issue 1 — supersedes spec 010 FR-005)**

- **FR-001**: The tool MUST NOT write any map-valued node property. The existing `stepNotes`
  map-property write (`SET ctx.stepNotes = $step_notes` with a Python dict, currently present in
  `migration_oracle/mcp/graph/queries/context.py`) MUST be removed. Because this code was introduced
  by spec 010 FR-005 and is already on the `010-mcp-defect-fixes` branch, removing it MUST be the
  first implementation task before any other 011 changes are applied.
- **FR-002**: Per-step outcome MUST be persisted as a relationship
  `(ctx:MigrationContext)-[:STEP_OUTCOME {status, reason, updatedAt}]->(s:MigrationStep)`, created
  with `MERGE` on the `(ctx, s)` pair so repeated calls update in place rather than duplicating.
  `reason` MUST be omitted/null on the relationship when not supplied; it MUST NOT be coerced into a
  map.
- **FR-003**: The existing `completedSteps` String-array advancement MUST be preserved; only the
  reason/status storage moves to the relationship.
- **FR-004**: A call with a `step_id` not present on the context's migration path MUST return a
  structured error with `error_code: "step_not_on_path"` and MUST NOT create a `STEP_OUTCOME`
  relationship.

**check_version_availability (Issues 3 & 4 — supersedes spec 010 FR-017's slug-only constraint)**

- **FR-005**: A single shared framework-canonicalization helper MUST be introduced. In this spec it
  is wired to `check_version_availability` only; the module path is left to plan.md. It MUST be
  importable by all framework-accepting tools (making it available for future wiring), but only
  `check_version_availability` is required to adopt it in spec 011 — updating the other framework-
  accepting tools is deferred to a future spec. The helper MUST accept `"Spring Boot"`, `"spring boot"`,
  `"spring-boot"`, and `"springboot"` (case-insensitive) as equivalent, resolving each to one canonical
  record exposing both a `display` form (`"Spring Boot"`) and a `slug` form (`"spring-boot"`).
  All requirements from spec 010 FR-015–FR-020 for `check_version_availability` remain in force;
  011 FR-005–FR-008 amend only the framework-canonicalization and graph-lookup behaviour.
- **FR-006**: The internal graph lookup MUST filter Version nodes using the canonical `display` form
  (`Version {framework: "Spring Boot", version: <major.minor.0>}`), so `exists_in_graph` matches the
  stored node casing.
- **FR-007**: The Maven-coordinate lookup MUST be keyed by the canonical `slug` form, keeping it
  aligned with the coordinate table from spec 010.
- **FR-008**: An unsupported framework value MUST return a structured `unsupported_framework` error
  listing the supported `display` names, without making a network call.

**search_openrewrite_recipes / build_recipe_plan (Issue 2 — ingestion layer)**

- **FR-009**: The ingestion pipeline MUST create `OpenRewriteRecipe` nodes with populated
  `description` and `displayName` properties (the fields covered by the `openrewrite_recipe_description`
  fulltext index) — not stub nodes lacking those properties.
- **FR-010**: `ensure_indexes()` MUST run as part of graph population so the
  `openrewrite_recipe_description` fulltext index and the `openrewrite_recipe_vector` vector index are
  present and `ONLINE` against the populated recipe nodes.
- **FR-011**: If hybrid (vector) search is used for recipes, each `OpenRewriteRecipe` node MUST carry
  the embedding consumed by the `openrewrite_recipe_vector` index.
- **FR-012**: After population, `MATCH (r:OpenRewriteRecipe) RETURN count(r), count(r.description), count(r.displayName)` MUST yield three equal counts.

**Deprecated classes (Issue 5 — ingestion layer)**

- **FR-013**: The ingestion pipeline MUST seed a curated registry of well-known deprecated classes
  per framework major version (minimum for Spring Boot 3.x: `RestTemplate`,
  `WebSecurityConfigurerAdapter`, `WebMvcConfigurerAdapter`, `EnvironmentPostProcessor`) and create
  `Class` nodes plus `DEPRECATED_IN` and, where a replacement is known, `REPLACED_BY` edges for each.
- **FR-014**: Seeded deprecated-class nodes and edges MUST be created with `MERGE` so re-ingestion is
  idempotent and does not duplicate them.

**MigrationRule metadata (Issue 6 — query + ingestion)**

- **FR-015**: `analyze_upgrade_path` MUST project the stored rule properties onto the response:
  `title` ← `rule.title`, `change_type` ← `rule.changeType`, `reason` ← `rule.statement`, and
  `severity` ← the linked `BreakingScope.severity` via `HAS_SCOPE`.
- **FR-016**: The ingestion pipeline MUST set a `framework` property on every `MigrationRule` node.
- **FR-017**: The ingestion pipeline MUST guarantee every `MigrationRule` has a
  `HAS_SCOPE → BreakingScope` edge so `severity` (and `scope`) are always reachable; rules whose
  source breaking-change carries no explicit scope MUST be linked to a default `BreakingScope`.

  > **Relationship name confirmed**: The authoritative relationship type is `HAS_SCOPE`. The reference
  > to `SCOPED_TO` in ISSUES.md Issue 7 was a misidentification. The existing query code in
  > `migration_oracle/mcp/graph/queries/context.py` and `upgrade.py` already uses `HAS_SCOPE`; the fix
  > is data population (ingestion), not a query rename. This is confirmed by
  > `MATCH ()-[r]->(b:BreakingScope) RETURN type(r), count(*) LIMIT 10` returning `HAS_SCOPE` (or
  > zero rows because no data has been ingested yet).

**get_steps_for_scope_tier (Issue 7 — query + ingestion)**

- **FR-018**: The scope filter has the following exact semantics: given a requested `scope_tier`,
  the query MUST return (a) steps whose linked rule has a `BreakingScope {scope: <scope_tier>}` (scope
  matches), and (b) steps whose linked rule has NO `BreakingScope` at all (scopeless, returned with
  `scope: null`). Steps whose linked rule has a `BreakingScope` with a DIFFERENT scope value MUST be
  excluded. The scope filter MUST NOT eliminate scopeless steps from the result.
- **FR-019**: With FR-017 satisfied, a call for a valid scope against a context that has pending steps
  MUST return `total > 0`.

**list_pipeline_runs (Issue 8 — query + ingestion)**

- **FR-020**: The tool MUST NOT hardcode `from_version` to `""`. It MUST return the `fromVersion`
  stored on the Version node when present.
- **FR-021**: The ingestion pipeline MUST persist `fromVersion` on the Version node (via the
  artifact-paths upsert) at population time.
- **FR-022**: When a Version node has no stored `fromVersion`, the tool MUST parse `from_version` from
  the artifact filename. The actual filename pattern produced by `pipeline/_paths.py:artifact_key` is
  `<framework>-<from>-to-<to>-changes_filtered.md`; the parser MUST anchor on the `-to-` separator
  and `-changes` token and tolerate any trailing suffix (e.g. `_filtered.md`). If neither the stored
  property nor the filename parse yields a value, `from_version` MUST be `""` with no exception.

**LifecycleAlert (Issue 9 — ingestion layer)**

- **FR-023**: The ingestion pipeline MUST create `LifecycleAlert` nodes from a curated per-version
  seed list and link each to the relevant `Version` node so `analyze_upgrade_path(include_lifecycle=True)`
  can return them. Each `LifecycleAlert` node MUST carry the following properties (all required):
  - `message` (String): human-readable alert text (e.g. `"Spring Security 7 changes the default CSRF policy"`).
  - `category` (String): coarse classification of the change — one of `"security"`, `"api"`, `"config"`, `"dependency"`, or `"other"`.
  - `phase` (String): the migration phase the alert is most relevant to (e.g. `"dependency-update"`, `"code-migration"`, `"testing"`).
  The `analyze_upgrade_path` query MUST project all three properties when returning lifecycle alerts.
- **FR-024**: `LifecycleAlert` nodes and their `Version` links MUST be created with `MERGE` for
  idempotent re-ingestion. When `include_lifecycle=False`, the tool MUST return an empty
  `lifecycle_alerts` regardless of seeded data.

**resolve_paysafe_dependency_by_service_name (Issue 10 — server code)**

- **FR-025**: Every outbound network call in the resolver MUST have an explicit timeout. In
  particular, the FindIt lookup (currently unbounded) MUST be bounded by an explicit timeout
  consistent with the existing `_HTTP_TIMEOUT_SECONDS`-style convention.
- **FR-026**: On timeout or backend unavailability, the tool MUST return the resolver's existing
  structured error shape rather than hanging or raising a raw exception.

### Key Entities

- **MigrationContext**: Active migration session node. After this fix, per-step outcomes hang off it
  via `STEP_OUTCOME` relationships (no map property).
- **MigrationStep**: Target of `STEP_OUTCOME`; returned by `get_steps_for_scope_tier`. Scopeless steps
  are no longer dropped.
- **MigrationRule**: After this fix, carries a `framework` property and always has a `HAS_SCOPE` edge;
  its `title`/`changeType`/`statement` are projected by `analyze_upgrade_path`.
- **BreakingScope**: Holds `scope` and `severity`; reachable from every rule via `HAS_SCOPE`.
- **OpenRewriteRecipe**: After this fix, carries real `description`/`displayName` (and embedding),
  covered by the fulltext/vector indexes so recipe search returns hits.
- **Class**: Deprecated classes from the curated seed exist with `DEPRECATED_IN`/`REPLACED_BY` edges.
- **LifecycleAlert** *(new label)*: Phase-level migration signals linked to a `Version`. Required
  properties: `message` (String), `category` (String — one of `"security"`, `"api"`, `"config"`,
  `"dependency"`, `"other"`), `phase` (String).
- **Version**: After this fix, carries a `fromVersion` property feeding `list_pipeline_runs`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `update_step_status` succeeds on 100% of calls (zero `Neo4j TypeError`); the supplied
  status and reason are retrievable afterward via the `STEP_OUTCOME` relationship.
- **SC-002**: `search_openrewrite_recipes` returns a non-empty hit list for representative migration
  queries, and `build_recipe_plan` populates `auto_track` with at least one recipe for the 3.5→4.0
  path.
- **SC-003**: `check_version_availability` returns `exists_in_graph: true` for a version present in
  the graph regardless of whether the framework is passed as `"Spring Boot"` or `"spring-boot"`.
- **SC-004**: `resolve_deprecation` and `entity_evolution` return non-`not_found` results for the
  curated Spring Boot 3.x deprecated classes (`RestTemplate`, `WebMvcConfigurer`,
  `EnvironmentPostProcessor`, `WebSecurityConfigurerAdapter`).
- **SC-005**: Every rule returned by `analyze_upgrade_path` has non-null `title`, `severity`, and
  `change_type`.
- **SC-006**: `get_steps_for_scope_tier` returns `total > 0` for a valid scope on a context that has
  pending steps; scopeless steps appear with `scope: null` and are never dropped.
- **SC-007**: Every run from `list_pipeline_runs` reports a non-empty `from_version` matching its
  artifact filename.
- **SC-008**: `analyze_upgrade_path(include_lifecycle=True)` returns a non-empty `lifecycle_alerts`
  for the 3.5→4.0 path.
- **SC-009**: `resolve_paysafe_dependency_by_service_name` returns within its configured timeout for
  an unresponsive backend (no hang) and resolves normally for a registered service.
- **SC-010**: All Cypher and ingestion changes are covered by tests. The following new test files are
  expected (all unit tests using mocks, consistent with spec 010's approach — no integration tests
  against a live Neo4j instance are in scope for this spec):
  - `tests/mcp/test_update_step_status.py` — covers FR-001–FR-004 (STEP_OUTCOME relationship, error
    on unknown step_id, no map property written).
  - `tests/mcp/test_check_version_availability.py` — covers FR-005–FR-008 (canonicalization helper,
    display-form graph lookup, Maven slug lookup, unsupported-framework error).
  - `tests/mcp/test_get_steps_for_scope_tier.py` — covers FR-018–FR-019 (scope match, scopeless
    returned with null, mismatched scope excluded).
  - `tests/mcp/test_list_pipeline_runs.py` — covers FR-020–FR-022 (stored fromVersion, filename-parse
    fallback including `_filtered.md` suffix, graceful empty fallback).
  - `tests/mcp/test_lifecycle_alert.py` — covers FR-023–FR-024 (alert properties projected, empty on
    include_lifecycle=False, idempotent MERGE).
  - `tests/mcp/test_analyze_upgrade_path.py` — covers FR-015–FR-017 (title/reason/severity
    projected; reason maps from `rule.statement`, not `rule.reason`).
  - `tests/mcp/test_search_openrewrite_recipes.py` — covers FR-009–FR-012 (description/displayName
    set from step.summary at stub-creation time; fulltext search returns hits).
  - `tests/mcp/test_resolve_deprecation.py` — covers FR-013–FR-014 (curated seed classes found,
    RestTemplate has REPLACED_BY edge, unknown class returns not_found, seeder is idempotent).
  Re-running ingestion must produce no duplicate seeded nodes or edges.

## Assumptions

- The graph stores `framework` on nodes in title-case display form (`"Spring Boot"`); the canonical
  helper maps every accepted spelling to that form for graph queries and to the `slug` form for Maven
  lookups.
- Curated seed lists (deprecated classes, lifecycle alerts) are an accepted, version-controlled
  source of truth; free-text extraction is a complement, not a substitute, for the well-known
  entries.
- Adding the `LifecycleAlert` label and the `STEP_OUTCOME` and (default) `HAS_SCOPE` relationships
  does not require a destructive schema migration; existing data is backfilled by re-running
  ingestion, and `from_version` for already-ingested runs is recovered via the filename-parse
  fallback without re-ingestion.
- APOC is not available (Neo4j Community); all map-like state must use relationships or primitive
  properties, never map-valued node properties.
- The 010-branch work remains valid except where 011 explicitly supersedes it (spec 010 FR-005 →
  011 FR-001–004; spec 010 FR-017's slug-only framework constraint → 011 FR-005–FR-008). All other
  spec 010 requirements for `check_version_availability` — specifically FR-015–FR-020 covering
  Maven Central probe logic, `latest_patch` computation, and network-error handling — remain in
  force unchanged.
- Maven Central's public search API is reachable from the deployment environment (carried over from
  spec 010 for `check_version_availability`'s `ga_available` field).

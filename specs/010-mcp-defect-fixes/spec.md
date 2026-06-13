# Feature Specification: MCP Defect Fixes — Migration Session Hardening

**Feature Branch**: `010-mcp-defect-fixes`

**Created**: 2026-06-10

**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent Completes a Migration Session with Patch Versions (Priority: P1)

A developer asks the migration assistant to guide them from Spring Boot 3.5.12 to 4.1.0. The agent calls `create_migration_context` with the exact patch versions from the project's `pom.xml`. Previously, the call would fail because the graph stores only `X.Y.0` forms, blocking every subsequent Loop II–IV tool. After this fix, the context is created successfully and the full orchestration harness runs to completion.

**Why this priority**: This is the single defect that blocks all step tracking, audit trail, and feedback-loop tools. Every other fix is rendered unreachable when context creation fails.

**Independent Test**: Call `create_migration_context(from_version="3.5.12", to_version="4.1.0")` against a graph that contains `3.5.0` and `4.1.0` Version nodes; verify a valid context ID is returned and subsequent `get_steps_for_scope_tier` calls succeed.

**Acceptance Scenarios**:

1. **Given** a graph with Version nodes `3.5.0` and `4.1.0`, **When** `create_migration_context` is called with `from_version="3.5.12"`, **Then** it normalises to `3.5.0`, matches the node, and returns a valid context ID.
2. **Given** a graph with no Version node for `4.1.0`, **When** `create_migration_context` is called with `to_version="4.1.0"`, **Then** it returns `{error_code: "version_not_in_graph", missing_version: "4.1.0", hint: "Graph contains 3.5.0, 4.0.0; pass one of these as to_version"}` (list reflects actual Version nodes in the graph) without raising an exception.
3. **Given** a prior failed `create_migration_context` call that wrote a zombie node, **When** the tool is called again with corrected inputs, **Then** no duplicate orphaned `MigrationContext` nodes exist in the graph.

---

### User Story 2 — Agent Checks Whether a Target Version Exists Before Starting (Priority: P1)

Before beginning a migration session, the agent calls `check_version_availability("spring-boot", "4.1.0")` to confirm the version is in the graph and is generally available. If it is not yet GA, the agent can warn the developer and suggest the latest stable patch.

**Why this priority**: Prevents wasted migration sessions on unreleased versions; gives agents a pre-flight check without any side effects.

**Independent Test**: Call `check_version_availability("spring-boot", "4.1.0")` and verify all four fields (`exists_in_graph`, `ga_available`, `latest_patch`, `hint`) are returned; call for a non-existent version and verify `exists_in_graph: false` with a meaningful hint.

**Acceptance Scenarios**:

1. **Given** a Version node for `spring-boot 4.1.0` in the graph and a Maven Central response with at least one artifact, **When** `check_version_availability("spring-boot", "4.1.0")` is called, **Then** it returns `{exists_in_graph: true, ga_available: true, latest_patch: "4.1.x", hint: "..."}`.
2. **Given** no Version node for `4.1.0` in the graph, **When** the tool is called, **Then** `exists_in_graph: false` is returned with a hint pointing to available minor-zero versions.
3. **Given** a version that exists in the graph but has no Maven Central artifacts, **When** the tool is called, **Then** `ga_available: false` and `hint` explains the version is not yet GA.

---

### User Story 3 — Agent Skips Irrelevant Recipe Steps Without Manual Grepping (Priority: P2)

The agent calls `build_recipe_plan` and receives steps with an `applicability` field. Steps that affect classes or dependencies not present in the project are marked `not_applicable`, allowing the agent to immediately focus on relevant steps without manually inspecting each one.

**Why this priority**: Reduces the 61% noise rate in recipe plan output and enables deterministic triage without additional tool calls.

**Independent Test**: Call `build_recipe_plan` with a `user_entities` list that matches only a subset of steps; verify that non-matching steps carry `applicability: "not_applicable"` and matching steps carry `applicability: "applicable"`.

**Acceptance Scenarios**:

1. **Given** a recipe plan with 10 steps of which 4 affect classes present in `user_entities`, **When** `build_recipe_plan` is called, **Then** 4 steps have `applicability: "applicable"`, the rest have `applicability: "not_applicable"`, and `matched_entities` is populated for applicable steps.
2. **Given** a recipe plan with duplicate `step_id` entries, **When** `build_recipe_plan` is called, **Then** each `step_id` appears exactly once (first occurrence wins).
3. **Given** a step with no `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, or `AFFECTS_DEPENDENCY` edges, **When** `build_recipe_plan` is called, **Then** that step returns `applicability: "unknown"`.

---

### User Story 4 — Agent Records Why a Step Was Skipped (Priority: P2)

The agent calls `update_step_status(context_id, step_id, status="skipped", reason="Jakarta EE already migrated by automated recipe")`. The reason is persisted to the `MigrationContext` node. On a subsequent session, the agent retrieves the context and sees the recorded rationale, preventing redundant work.

**Why this priority**: Provides a durable per-step audit trail that survives session boundaries; essential for multi-session migrations.

**Independent Test**: Call `update_step_status` with a non-empty `reason`, then read the context back and verify `stepNotes[step_id]` equals the supplied string.

**Acceptance Scenarios**:

1. **Given** a valid context, **When** `update_step_status` is called with `reason="already handled"`, **Then** the context's `stepNotes` map contains `{step_id: "already handled"}` when retrieved.
2. **Given** `update_step_status` is called without a `reason`, **Then** no entry is added to `stepNotes` for that step (no null keys).

---

### User Story 5 — Agent Sees All Steps Including Those Without a Scope Tag (Priority: P2)

The agent calls `get_steps_for_scope_tier(context_id, scope="API")` and receives all steps, including those that have no `BreakingScope` node (returned with `scope: null`). Previously, scopeless steps were silently dropped.

**Why this priority**: Scopeless steps are valid migration actions; losing them silently causes incomplete migration guides.

**Independent Test**: Add a step with no `HAS_SCOPE` relationship to the fixture data; call `get_steps_for_scope_tier` and verify the step is returned with `scope: null`.

**Acceptance Scenarios**:

1. **Given** a migration path with steps that have no `BreakingScope` node, **When** `get_steps_for_scope_tier` is called, **Then** those steps are returned with `scope: null`.
2. **Given** steps with scope `"API"` and steps with no scope, **When** `get_steps_for_scope_tier` is called with `scope="API"`, **Then** scoped steps are returned; scopeless steps are also returned with `scope: null`.

---

### User Story 6 — Resolver Does Not Leak OAuth Credentials in Error Messages (Priority: P1)

When GitLab version resolution fails with an exception message containing an OAuth2 token (e.g., `git clone oauth2:abc123@gitlab.example.com/...`), the error surfaced to the agent contains only the sanitised message with the credential redacted.

**Why this priority**: Security defect; any leak of OAuth tokens to the LLM context is a credential exposure risk.

**Independent Test**: Trigger a GitLab `ls-remote` failure with a URL containing `oauth2:TOKEN@host`; verify that the MCP error response body contains no OAuth2 token or basic-auth credential.

**Acceptance Scenarios**:

1. **Given** an exception message containing `oauth2:abc123@gitlab.example.com`, **When** `_build_error()` is called, **Then** the returned message replaces the credential segment with a redaction marker.
2. **Given** an exception message containing `https://user:password@host`, **When** `_build_error()` is called, **Then** the credential is scrubbed from the message.
3. **Given** an exception message containing no credentials, **When** `_build_error()` is called, **Then** the message is returned unchanged.

---

### User Story 7 — Resolver Falls Back to Artifactory When GitLab Is Unavailable (Priority: P2)

When GitLab `ls-remote` fails (e.g., network unreachable, token expired), the resolver automatically retries via Artifactory REST without surfacing the retry to the caller. The caller receives the same result shape regardless of which backend was used.

**Why this priority**: Makes version resolution robust in environments where GitLab access is restricted or tokens rotate frequently.

**Independent Test**: Simulate a GitLab failure; verify the resolver returns a valid version list sourced from Artifactory without the caller receiving any error or retry signal.

**Acceptance Scenarios**:

1. **Given** GitLab `ls-remote` raises an exception, **When** `ARTIFACTORY_BASE_URL` is set and Artifactory responds successfully, **Then** the resolver returns available versions from Artifactory without error.
2. **Given** both GitLab and Artifactory fail, **When** the resolver is called, **Then** a single structured error is returned (no raw exception stack traces).
3. **Given** `ARTIFACTORY_BASE_URL` is not set and GitLab fails, **When** the resolver is called, **Then** the original GitLab error is returned without attempting Artifactory.

---

### User Story 8 — Agent Filters Recipes to Composite-Only or No-Param Subsets (Priority: P2)

The agent calls `search_openrewrite_recipes(only_composite=true)` to retrieve only composite recipes, or `search_openrewrite_recipes(require_no_params=true)` to retrieve only recipes that can run without configuration. Both filters are applied at query time and return accurate results.

**Why this priority**: Agents currently waste tool calls post-processing results that should have been pre-filtered; silent accept-and-ignore of parameters causes incorrect query results.

**Independent Test**: Call `search_openrewrite_recipes(only_composite=true)` and verify every returned recipe has `composite=true`; call with `require_no_params=true` and verify no returned recipe has a required `RecipeParam`.

**Acceptance Scenarios**:

1. **Given** a mix of composite and non-composite recipes, **When** `search_openrewrite_recipes(only_composite=true)` is called, **Then** only recipes with `composite=true` are returned.
2. **Given** recipes with and without required parameters, **When** `search_openrewrite_recipes(require_no_params=true)` is called, **Then** no returned recipe has a linked `RecipeParam` node with `required=true`.
3. **Given** both filters applied together, **When** `search_openrewrite_recipes(only_composite=true, require_no_params=true)` is called, **Then** results satisfy both constraints simultaneously.

---

### User Story 9 — Migration Skill Continues When Context Creation Fails (Priority: P2)

An agent following the `framework_migration_main.md` skill encounters a `create_migration_context` failure. Instead of stopping, the skill instructs the agent to fall back to static lookup mode, continue with `analyze_upgrade_path` and `build_recipe_plan`, track state internally, and call `submit_migration_insight` for every high-confidence finding.

**Why this priority**: Without this documented fallback, agents improvise inconsistently; the stateless path ensures findings are still captured even when the context harness is unavailable.

**Independent Test**: Follow the skill instructions using a mock context failure; verify the agent reaches `submit_migration_insight` calls and produces a session summary noting the context failure.

**Acceptance Scenarios**:

1. **Given** `create_migration_context` returns an error on both attempts, **When** the agent follows the skill, **Then** it proceeds to `analyze_upgrade_path` and `build_recipe_plan` without halting.
2. **Given** the stateless fallback path is active, **When** a high-confidence finding is identified, **Then** `submit_migration_insight` is called without a `context_id`.
3. **Given** a macOS environment, **When** the Loop I scanning script is executed, **Then** it completes without error (no `grep -P` incompatibility).

---

### Edge Cases

- What happens when `create_migration_context` is called with a version string that cannot be parsed (e.g., `"latest"`)? It must return a clear error message without writing any graph node.
- What happens when `check_version_availability` is called and Maven Central is unreachable? It must return `ga_available: false` with a hint noting the probe failure rather than raising an exception.
- What happens when `build_recipe_plan` is called with an empty `user_entities` list? All steps must return `applicability: "unknown"` rather than `"not_applicable"`, since absence of context is not the same as non-applicability.
- What happens when `update_step_status` is called with a `step_id` that does not exist on the context? It must return a structured error rather than silently creating an invalid entry.

## Requirements *(mandatory)*

### Functional Requirements

**create_migration_context**

- **FR-001**: The tool MUST normalise `from_version` and `to_version` to `major.minor.0` form before every Cypher MATCH, accepting any patch version string (e.g., `"3.5.12"` → `"3.5.0"`).
- **FR-002**: When a normalised Version node is absent from the graph, the tool MUST run a secondary read query (`MATCH (v:Version {framework: $framework}) RETURN v.version ORDER BY v.sortableVersion`) to retrieve the actual list of available versions, then return `{error_code: "version_not_in_graph", missing_version: "<version>", hint: "Graph contains <comma-separated list of v.version>; pass one of these as from_version/to_version"}` instead of raising a `RuntimeError`. The hint MUST reflect the live graph state, not a hardcoded template.
- **FR-003**: After executing the MERGE followed by the MATCH on Version nodes, if `.single()` returns `None` (the MATCH found no result), the tool MUST issue a targeted `DELETE` for the just-created `MigrationContext` node and then return the diagnostic error. The DELETE MUST execute only in this condition — it MUST NOT run when `.single()` returns a valid result, and it MUST NOT run before the MERGE. This ensures valid in-progress contexts are never deleted on a retry.
- **FR-004**: The normalisation helper MUST be imported from `migration_oracle/mcp/tools/upgrade.py`; no duplicate implementation is permitted. As part of this spec, the function MUST be renamed from `_to_minor_zero` to `to_minor_zero` (removing the leading underscore) to allow cross-module import without static-analysis warnings; all existing call sites in `upgrade.py` MUST be updated to use the new name.

**update_step_status**

- **FR-005**: The tool MUST persist the `reason` parameter as an entry in `ctx.stepNotes` on the `MigrationContext` node when `reason` is a non-empty string. `stepNotes` is a Neo4j map property (`{step_id: "reason text", ...}`). The Cypher update MUST use `apoc.map.setKey(coalesce(ctx.stepNotes, {}), $step_id, $reason)` if APOC is available, or a Python-side map-merge followed by a full `SET ctx.stepNotes = $merged_map` if APOC is absent — never a list, never a serialised string. When `reason` is absent or an empty string, `stepNotes` MUST NOT be modified — the call is a no-op for the notes map, ensuring backward compatibility with existing callers that do not pass `reason`.

**get_steps_for_scope_tier**

- **FR-006**: Steps that have no `BreakingScope` node MUST be returned with `scope: null`; they MUST NOT be silently dropped by the optional-match predicate.

**Paysafe Resolver**

- **FR-007**: `_build_error()` MUST redact any `oauth2:[^@]+@` or `https?://[^:]+:[^@]+@` pattern from exception messages before populating the `message` field.
- **FR-008**: When GitLab `ls-remote` fails and `ARTIFACTORY_BASE_URL` is set, the resolver MUST automatically retry via the Artifactory REST `/api/search/latestVersion` endpoint using anonymous read (no credentials, no `Authorization` header); the call MUST use only `ARTIFACTORY_BASE_URL` — no additional environment variable for Artifactory credentials is permitted. Results must be returned transparent to callers.
- **FR-009**: When `ARTIFACTORY_BASE_URL` is not set, the resolver MUST NOT attempt an Artifactory call; it MUST propagate the original GitLab error.

**build_recipe_plan**

- **FR-010**: Every step in `manual_track` MUST include `applicability` (`"applicable"` | `"not_applicable"` | `"unknown"`) and `matched_entities` fields derived from `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, and `AFFECTS_DEPENDENCY` relationships intersected against `user_entities`.
- **FR-011**: When `user_entities` is a non-empty list and a step has no intersection with it, the step MUST carry `applicability: "not_applicable"` and `matched_entities: []`. When `user_entities` is empty or absent, ALL steps MUST carry `applicability: "unknown"` and `matched_entities: []` — steps MUST NOT be labelled `"not_applicable"` solely because the entity list was not provided.
- **FR-012**: Duplicate `step_id` entries MUST be deduplicated before returning; the first occurrence wins.

**search_openrewrite_recipes**

- **FR-013**: When `only_composite=true`, the query MUST filter to recipes where `composite=true` at the Cypher WHERE clause using the pattern `AND (NOT $only_composite OR r.composite = true)`; the deferred-filter comment block MUST be removed. Post-hoc Python filtering after a full result fetch is not permitted.
- **FR-014**: When `require_no_params=true`, the query MUST exclude recipes that have any `RecipeParam` node linked by `HAS_PARAM` with `required=true`, enforced at query time.

**check_version_availability (new tool)**

- **FR-015**: The tool MUST accept `framework` and `version` parameters and return `{exists_in_graph: bool, ga_available: bool, latest_patch: str | null, hint: str}`. `latest_patch` is `null` when Maven Central is unreachable or returns no results.
- **FR-016**: `exists_in_graph` MUST be `true` only when a Version node with `framework=<framework>` and `version=<major.minor.0>` exists in the graph.
- **FR-017**: `ga_available` MUST be determined by probing `https://search.maven.org/solrsearch/select?q=g:<group_id>+AND+a:<artifact_id>+AND+v:<version>&rows=1&wt=json` with no authentication; `true` if `response.numFound >= 1`. The tool MUST NOT scrape HTML or use any other Maven Central URL pattern. The mapping from `framework` to Maven `groupId` + `artifactId` MUST be encoded as a static lookup table in `plan.md`; the minimum required entry is `"spring-boot"` → `g:org.springframework.boot AND a:spring-boot`. Any unsupported `framework` value MUST return `{exists_in_graph: false, ga_available: false, latest_patch: null, hint: "Unknown framework; supported: <list>"}` without making a network call.
- **FR-018**: `latest_patch` MUST be the highest patch version for the same `major.minor` returned by Maven Central.
- **FR-019**: The tool MUST NOT write any node or relationship to Neo4j.
- **FR-020**: The tool MUST handle Maven Central probe failures gracefully, returning `ga_available: false`, `latest_patch: null`, and a hint noting the probe failure. The tool MUST NOT raise an exception for network errors.

**framework_migration_main.md**

- **FR-021**: After the Loop I failure condition, the skill MUST define an explicit STATELESS FALLBACK block instructing agents to continue with `analyze_upgrade_path` and `build_recipe_plan`, skip Loop II–III tools that require a `context_id`, track step state in agent context only, and call `submit_migration_insight` for every high-confidence finding.
- **FR-022**: The Loop I scanning script MUST use `grep -E` (POSIX ERE) instead of `grep -P` to ensure compatibility with macOS BSD grep and Linux GNU grep. This change is scoped exclusively to the scanning script lines inside `framework_migration_main.md`; no Python `subprocess` grep calls and no other skill files (`framework_migration_scanning.md`, `framework_migration_plan_format.md`, `framework_migration_version_map.md`) are to be modified.
- **FR-023**: The STATELESS FALLBACK block MUST NOT alter the existing Loop I–IV structure; it is an addendum inserted after the Loop I failure condition. Only `framework_migration_main.md` is modified by this spec; the other three skill files MUST remain untouched.

### Key Entities

- **MigrationContext**: Graph node representing an active migration session. After this fix, carries a `stepNotes` string-map property for per-step audit rationale.
- **Version**: Graph node keyed by `framework` + `version` (always in `major.minor.0` form). `create_migration_context` and `check_version_availability` both query this node.
- **MigrationStep / BreakingChange**: Nodes returned by `get_steps_for_scope_tier` and `build_recipe_plan`. After this fix, steps without a `BreakingScope` relationship are no longer silently dropped.
- **Recipe / RecipeParam**: Nodes queried by `search_openrewrite_recipes`. After this fix, `composite` and `required` properties are filtered at query time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `create_migration_context` succeeds on the first call for any project using patch version strings (e.g., `"3.5.12"`), with zero failures attributable to version format mismatch.
- **SC-002**: Zero OAuth2 tokens or basic-auth credentials appear in any MCP error response body across all resolver error paths.
- **SC-003**: `build_recipe_plan` returns no duplicate `step_id` entries and every step carries an `applicability` value; agents can filter to applicable steps without any additional tool calls.
- **SC-004**: `search_openrewrite_recipes` returns results that satisfy `only_composite` and `require_no_params` constraints in 100% of calls when those filters are supplied.
- **SC-005**: `check_version_availability` returns all four required fields for any framework/version combination, including when the version is absent from the graph or Maven Central is unreachable.
- **SC-006**: `get_steps_for_scope_tier` returns all steps including those without a `BreakingScope` node; zero scopeless steps are silently dropped.
- **SC-007**: The Loop I scanning script in `framework_migration_main.md` completes without error on macOS and Linux.
- **SC-008**: The framework-migration skill defines a documented stateless fallback path that agents follow consistently when context creation fails, resulting in `submit_migration_insight` calls even in stateless sessions.
- **SC-009**: All Cypher changes introduced by this spec are covered by unit tests using the existing Neo4j fixtures in `tests/mcp/`.

## Assumptions

- The graph stores Version nodes exclusively in `major.minor.0` form; no full patch-version nodes are expected or will be added.
- `to_minor_zero` (renamed from `_to_minor_zero` by FR-004) is already implemented and tested in `migration_oracle/mcp/tools/upgrade.py`; the rename is in-scope but the logic is unchanged.
- Maven Central's public search API (`search.maven.org/solrsearch`) is accessible from the deployment environment without authentication.
- `ARTIFACTORY_BASE_URL` is an optional environment variable; its absence is a valid configuration for environments that have direct GitLab access.
- The `framework_migration_main.md` skill file is the canonical agent instruction source; updating it is sufficient to change agent behaviour on the stateless fallback path.
- No new graph node labels, relationship types, or schema migrations are required for any fix in this spec.
- Existing callers of `get_steps_for_scope_tier` that currently receive only scoped results will receive additional scopeless steps with `scope: null`; callers are assumed able to handle nullable scope values.

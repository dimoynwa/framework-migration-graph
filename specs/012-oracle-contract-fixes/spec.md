# Feature Specification: Oracle Contract Fixes

**Feature Branch**: `012-oracle-contract-fixes`

**Created**: 2026-06-13

**Status**: Draft

**Input**: Corrects 14 unique defects documented in ISSUES.md (body numbering ISSUE-001 through ISSUE-015, with ISSUE-011 consolidated into ISSUE-008) across the Paysafe Migration Oracle so that version arithmetic, graph-state recording, scope/severity querying, tool return shapes, session resumability, and failure-recovery all behave as their documentation and graph schema already promise.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Version arithmetic produces correct sort order (Priority: P1)

A developer using the Migration Oracle to identify target versions for a Spring Boot or Angular upgrade relies on `sortableVersion` comparisons to find the next valid version. Today, the formula in the version-map skill (`MAJOR*10000 + MINOR*100 + PATCH`) diverges from the graph schema formula (`MAJOR*1_000_000 + MINOR*1_000 + PATCH`), causing version inversion for any minor ≥ 10 (e.g. Spring Boot 3.10.x sorts _below_ 3.9.x under the skill's formula). All skill tables must use the canonical graph-schema formula and every pre-computed Sortable cell must agree with it.

**Why this priority**: Silent wrong version ordering produces incorrect migration targets with no error signal — the highest-impact correctness defect.

**Independent Test**: Can be fully tested by two checks that do not depend on `3.10.x` being an existing table row: (a) for every existing row, re-compute `MAJOR*1_000_000 + MINOR*1_000 + PATCH` and assert it matches the stored Sortable cell; (b) apply the documented formula to the synthetic inputs `(3,10,0)` and `(3,9,0)` and assert `f(3,10,0) > f(3,9,0)` — this is a formula-level property test, not a table-row lookup.

**Acceptance Scenarios**:

1. **Given** the version-map skill document, **When** a reader computes `sortableVersion` for any listed version using the formula stated in that document, **Then** the result matches `MAJOR*1_000_000 + MINOR*1_000 + PATCH` exactly.
2. **Given** the canonical formula stated in the version-map document, **When** the formula is applied to `(MAJOR=3, MINOR=10, PATCH=0)` and `(MAJOR=3, MINOR=9, PATCH=0)`, **Then** `f(3,10,0)` is numerically greater than `f(3,9,0)`. This is a property test on the documented formula itself, independent of which versions are currently in the table.
3. **Given** a version entry in the table, **When** the formula is applied row by row, **Then** no cell value deviates from the canonical formula's output.

---

### User Story 2 — Step outcomes are recorded via the preferred graph relationship (Priority: P1)

A team lead querying the Oracle's progress-summary query (graph-schema.md example #5) expects to see how many steps were completed, skipped, or failed for a migration context. Today `update_step_status` writes only to legacy arrays (`completedSteps`, `skippedSteps`, `failedSteps`) and never creates the `STEP_OUTCOME` relationship that the schema marks as preferred. The progress-summary query returns empty for every session.

**Why this priority**: The schema's authoritative progress view is permanently empty, making the Oracle's tracking capability inoperative for any caller using the documented query pattern.

**Independent Test**: Can be fully tested by recording one step outcome via `update_step_status`, then running the schema's progress-summary query and confirming it returns a non-zero count. Recording the same step twice must update one relationship, not create two.

**Acceptance Scenarios**:

1. **Given** a migration context with a linked `MigrationStep`, **When** `update_step_status` is called with outcome `completed`, **Then** a `STEP_OUTCOME` relationship exists between that context and that step with `status="completed"`.
2. **Given** a `STEP_OUTCOME` relationship already exists for a `(context, step)` pair, **When** `update_step_status` is called again for the same pair with a different outcome, **Then** exactly one `STEP_OUTCOME` relationship exists (updated, not duplicated).
3. **Given** a session with recorded outcomes, **When** the schema's progress-summary query (#5) is run, **Then** the returned counts are non-zero and match the number of **distinct `(context, step)` pairs** for which an outcome was recorded (not the number of `update_step_status` calls, since repeated calls on the same pair update one relationship).
4. **Given** the fix is additive, **When** any existing reader of `completedSteps`/`skippedSteps`/`failedSteps` arrays queries a context, **Then** those arrays are still populated (legacy writes are not removed).

---

### User Story 3 — Scope/severity queries honour the threshold parameter (Priority: P1)

A developer running Loop II tier-1 processing expects `get_steps_for_scope_tier` to return only `high` and `critical` severity steps. Today the `severity_threshold` parameter is accepted and echoed back but never applied in the Cypher query — all severity levels are returned for every tier.

**Why this priority**: Tier ordering is the Oracle's core prioritisation mechanism; a broken severity filter renders the tier structure meaningless.

**Independent Test**: Can be fully tested by calling `get_steps_for_scope_tier` with `severity_threshold="high"` and asserting that no returned step has `severity` equal to `"low"` or `"medium"`.

**Acceptance Scenarios**:

1. **Given** steps with mixed severities exist for a scope, **When** `get_steps_for_scope_tier` is called with `severity_threshold="high"`, **Then** only steps with severity `"high"` or `"critical"` are returned.
2. **Given** `severity_threshold="medium"`, **When** the tool is called, **Then** steps with `"medium"`, `"high"`, and `"critical"` are returned, but `"low"` steps are excluded.
3. **Given** `severity_threshold="low"` (default), **When** the tool is called, **Then** all severity levels are returned (no filter applied beyond scope).

---

### User Story 4 — Upgrade-path analysis returns recipe data (Priority: P2)

A developer calling `analyze_upgrade_path` with `include_recipes=true` expects each applicable step to include its linked OpenRewrite recipe. Today the Cypher traverses `(MigrationRule)-[:AUTOMATED_BY]->` which the graph schema does not define — the edge only exists from `MigrationStep`. Recipe lists are always empty.

**Why this priority**: P2 despite ISSUE-006 being rated HIGH in triage, because the blast radius is narrower than P1 items: the defect only surfaces when `include_recipes=true` is explicitly requested, and the tool still returns all rules correctly otherwise. P1 slots are reserved for defects that corrupt every call or every session (version ordering, STEP_OUTCOME, severity filtering).

**Independent Test**: Can be fully tested against a graph instance that has at least one `MigrationStep` with an `AUTOMATED_BY` edge: calling `analyze_upgrade_path` with `include_recipes=true` must return a non-empty `recipes` list on that step.

**Acceptance Scenarios**:

1. **Given** a `MigrationRule` that has a linked `MigrationStep` which has an `AUTOMATED_BY` edge to an `OpenRewriteRecipe`, **When** `analyze_upgrade_path` is called with `include_recipes=true`, **Then** the returned rule object contains a non-empty `recipes` list.
2. **Given** a rule with no linked steps or no automated steps, **When** `include_recipes=true` is set, **Then** the `recipes` list for that rule is empty (not null).
3. **Given** `include_recipes=false`, **When** the tool is called, **Then** no recipe traversal is performed (behaviour unchanged).

---

### User Story 5 — Tool return fields match documented API (Priority: P2)

A caller reading the result of `resolve_deprecation` accesses `entity_name` as documented. Today the Cypher aliases the value as `original_entity`, so `entity_name` is null in every response. Similarly, `search_openrewrite_recipes` filters on `r.requiredParams` and `r.isComposite`, which do not exist on the schema's `OpenRewriteRecipe` node, making `require_no_params` and `only_composite` non-functional.

**Why this priority**: Silent null fields and silently non-functional filter parameters produce data loss and wrong recipe sets.

**Independent Test**: Three checks, each independently verifiable: (a) calling `resolve_deprecation` for any known deprecated entity and reading `response["entity_name"]` returns the entity's name, not null; (b) calling `search_openrewrite_recipes` with `require_no_params=true` excludes any recipe that has at least one required `RecipeParam`; (c) calling `submit_migration_insight` twice with identical content — the second call must return `status="duplicate"` with a non-null `duplicate_of` field matching the first call's `insight_id`.

**Acceptance Scenarios**:

1. **Given** a deprecated class exists in the graph, **When** `resolve_deprecation` is called, **Then** `response["entity_name"]` equals the class name (not null).
2. **Given** an `OpenRewriteRecipe` with a linked `RecipeParam` where `required=true`, **When** `search_openrewrite_recipes` is called with `require_no_params=true`, **Then** that recipe is excluded from results.
3. **Given** an `OpenRewriteRecipe` with `composite=true`, **When** `search_openrewrite_recipes` is called with `only_composite=true`, **Then** only composite recipes are returned.
4. **Given** `submit_migration_insight` is called with a near-duplicate insight, **When** duplicate detection fires, **Then** the response shape (including `duplicate_of` field) is consistent across `ok`, `duplicate`, and `error` status paths.

---

### User Story 6 — Resumed sessions skip already-queried entities (Priority: P2)

A developer resuming a migration session after interruption expects Loop II to skip entities that were already queried in the prior run. Today the `queriedEntities` cache is initialised to `'{}'` at context creation but no tool ever writes to it, so the skip guard can never fire. Every resume re-queries every entity from scratch.

**Why this priority**: P2 despite ISSUE-002 being rated HIGH in triage. The blast radius is meaningful but contained: resumability only affects sessions that are interrupted and resumed; a session that runs to completion is unaffected. The defect is also silent rather than corrupting — the session completes correctly, just with redundant queries.

**Independent Test**: Can be fully tested by querying one entity in session A, closing and reopening the session (same `context_id`), and confirming that Loop II's skip guard logs the entity as already resolved rather than re-issuing the tool call.

**Acceptance Scenarios**:

1. **Given** an entity has been queried in a session, **When** `queriedEntities` is read from the context, **Then** the entity name is present as a key with a result summary as its value.
2. **Given** a resumed session, **When** Loop II encounters an entity already in `queriedEntities`, **Then** the skip guard fires and no tool call is re-issued for that entity.
3. **Given** the `--force-refresh` mechanism is invoked for an entity, **When** Loop II processes that entity, **Then** the entity is re-queried and `queriedEntities` is updated with the fresh result.

---

### User Story 7 — Build-failure path has a loadable rollback procedure (Priority: P3)

A developer whose automated OpenRewrite batch fails the build follows Loop III's instructions to "Load rollback skill." Today no rollback skill exists among the installed resources, making this instruction unresolvable.

**Why this priority**: P3 despite ISSUE-005 being rated HIGH in triage. Priority here reflects blast radius, not triage severity: this defect only activates on the build-failure branch of Loop III, which is itself uncommon. A developer who hits a build failure can perform a manual `git revert` in the interim. The documentation gap is real but the workaround cost is low compared to P1/P2 defects that corrupt every run.

**Independent Test**: Can be fully tested by confirming that `skill://framework-migration/rollback` is loadable via `install_migration_skill` and contains concrete revert steps.

**Acceptance Scenarios**:

1. **Given** Loop III's build-failure path is triggered, **When** the agent loads the rollback resource, **Then** a concrete, executable revert procedure is returned.
2. **Given** no build failure, **When** Loop III runs, **Then** the rollback resource is not loaded (no unnecessary side effect).

---

### User Story 8 — Abandoned sessions can be closed correctly (Priority: P3)

A developer whose migration project is cancelled or deferred wants to close the context with status `"abandoned"`. Today `close_migration_context` accepts only `"complete"` or `"partial"`, so the graph-schema-valid `"abandoned"` state is unreachable through the MCP surface.

**Why this priority**: The state is schema-valid and documented; its absence is a tool API gap, not a correctness failure.

**Independent Test**: Calling `close_migration_context` with `final_status="abandoned"` must succeed and set the context status to `"abandoned"` in the graph.

**Acceptance Scenarios**:

1. **Given** an in-progress migration context, **When** `close_migration_context` is called with `final_status="abandoned"`, **Then** the context status is set to `"abandoned"` without error.
2. **Given** an invalid `final_status` value, **When** `close_migration_context` is called, **Then** the documented error shape is returned.

---

### Edge Cases

- What happens when `update_step_status` is called for a step not linked to the context? Must return the documented error shape, not silently succeed.
- What happens when `sortableVersion` is requested for a version not in the table (e.g. a future release)? The formula must still produce a correct value.
- What happens when `severity_threshold` is passed as an unrecognised string? The tool MUST reject it and return the documented error shape — it MUST NOT silently fall back to any default, because a silent fallback would hide caller bugs and make tier behaviour unpredictable.
- What happens when `--force-refresh` is used for an entity that was never queried? Must behave identically to a first-time query.
- What happens when `submit_migration_insight` is called and the duplicate threshold is met exactly? The boundary behaviour must be deterministic and observable from the returned shape.
- What happens when `close_migration_context` is called on an already-closed context? Must return the documented error shape, not create a second close event.

---

## Requirements *(mandatory)*

### Functional Requirements

**WS1 — Version Arithmetic**

- **FR-001**: The version-map skill document MUST state the formula `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH` as the single canonical `sortableVersion` definition. Exactly one formula MUST exist across all project documents; the formula already in `graph-schema.md` is canonical and MUST NOT be edited as part of this feature — only the version-map document and its tables are corrected. *(GAP-001)*
- **FR-002**: Every pre-computed Sortable cell in **both** the Spring Boot table **and** the Angular table MUST be recomputed — not just worked examples — so that every row equals `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH` for that row's version. No cell in either table may retain a value computed by the old formula `MAJOR*10000 + MINOR*100 + PATCH`. The inversion-free property MUST hold for the documented formula itself: applying the formula to inputs `(3,10,0)` and `(3,9,0)` MUST yield `f(3,10,0) > f(3,9,0)`. This is a formula-level invariant, not contingent on those versions being present as table rows. *(GAP-002)*
- **FR-003**: The version-map document MUST include a `Last Updated` date and links to upstream support schedule pages (spring.io, angular.io) so agents can verify version status.
- **FR-004**: The Angular section MUST contain each version boundary note exactly once; duplicate `**Important version boundary:**` lines and duplicate bullet points MUST be removed.

**WS2 — Graph-State Contract**

- **FR-005**: `update_step_status` MUST write a `STEP_OUTCOME` relationship `(MigrationContext)-[:STEP_OUTCOME {status, reason, updatedAt}]->(MigrationStep)` **in addition to** — not instead of — the existing legacy array writes (`completedSteps`, `skippedSteps`, `failedSteps`). Legacy writes MUST remain until all readers migrate to `STEP_OUTCOME`. *(GAP-003)*
- **FR-006**: The `STEP_OUTCOME` write MUST be idempotent per `(context, step)` pair — this is a stated behavioural contract: recording the same `(context, step)` pair twice MUST result in exactly one `STEP_OUTCOME` relationship (the existing one updated), never two relationships for the same pair. *(GAP-003)*
- **FR-007**: `close_migration_context` MUST accept `"abandoned"` as a valid value for `final_status` in addition to `"complete"` and `"partial"`.

**WS3 — Query Correctness**

- **FR-008**: `get_steps_for_scope_tier` MUST apply a severity filter with the ordering `critical > high > medium > low`. "At or above threshold" means severity levels of equal or greater severity than the threshold are included; lesser-severity levels are excluded. A threshold of `"high"` MUST include `critical` and `high`, and MUST exclude `medium` and `low`. A threshold of `"medium"` MUST include `critical`, `high`, and `medium`, and MUST exclude `low`. This ordering and inclusion direction MUST be stated in the tool documentation. The concrete rank representation (e.g. integers) is a plan/contract detail. *(GAP-004)*
- **FR-009**: `analyze_upgrade_path` MUST return recipe objects **per automating step** — joined through the step that requires them — not directly per rule. A rule with multiple steps may produce multiple recipe entries. A step with no automating recipe MUST contribute an empty recipe list; this empty list is distinct from the rule having no steps at all. The graph relationships used for this traversal (`REQUIRES_STEP`, `AUTOMATED_BY`) are schema-defined and MUST be respected; the literal query form is a plan/contract detail. *(GAP-005)*

**WS4 — Tool API Alignment**

- **FR-010**: `resolve_deprecation` MUST return the entity name under the field key `entity_name` as documented. Both the Cypher query alias **and** the Returns table in the tool documentation MUST use `entity_name`; the two MUST agree. *(GAP-006)*
- **FR-011**: `search_openrewrite_recipes` MUST implement `require_no_params` by checking for the absence of `RecipeParam` nodes linked via `HAS_PARAM` with `required=true`, not by reading a non-existent `r.requiredParams` property. Both the Cypher query **and** the Returns/Parameters table MUST reflect this real graph structure. *(GAP-006)*
- **FR-012**: `search_openrewrite_recipes` MUST implement `only_composite` by checking the `r.composite` property (boolean), not `r.isComposite`. Both Cypher **and** documentation MUST agree on the property name. *(GAP-006)*
- **FR-013**: `submit_migration_insight` documentation MUST: (a) state the cosine similarity threshold used for near-duplicate detection; (b) document the pre-Cypher dedup query that fires before the `CREATE`; (c) include a Returns table that explicitly covers all three status paths with consistent field shapes: `status="ok"` returns `insight_id`; `status="duplicate"` returns `insight_id=null` and `duplicate_of` (element ID of the existing duplicate); `status="error"` returns `message`. The Cypher shown in the documentation MUST match what the code actually returns in all three paths. *(GAP-006)*

**WS5 — Resumability**

- **FR-014**: After each successful entity query in Loop II, the agent or a dedicated tool MUST write `entity_name → result_summary` into `queriedEntities` on the `MigrationContext` node. **DESIGN GATE**: The write mechanism — whether a new MCP tool (e.g. `update_queried_entity`) or a direct context-property update via an existing tool — is an **unresolved design decision** that MUST be chosen and documented in the plan before implementation begins. The key/value schema for `queriedEntities` entries MUST also be defined at that stage. *(GAP-007)*
- **FR-015**: The `--force-refresh` mechanism MUST be concretely defined as exactly one of: (a) a prompt/invocation parameter the agent reads, (b) a boolean property on `MigrationContext`, or (c) a dedicated cache-invalidation tool call. Its scope — whether it refreshes a single named entity or the full context — MUST be stated. **DESIGN GATE**: The concrete form is an **unresolved design decision** that MUST be chosen in the plan; the chosen form MUST be documented in both the skill reference and the MCP tool reference. *(GAP-007)*

**WS6 — Resilience**

- **FR-016**: A **new** rollback skill resource MUST be created at URI `skill://framework-migration/rollback` and added to the set of resources that `install_migration_skill` installs. This resource MUST define a concrete, named revert procedure (e.g. VCS revert steps or OpenRewrite dry-run mode instructions) that an agent can execute when Loop III's build-failure path fires. Loop III's skill text MUST reference this resource by its URI. *(GAP-008)*
- **FR-017**: Loop IV MUST include a stateless-fallback section defining which steps are skipped when no `context_id` is available and which actions are performed in-memory only (e.g. print backlog, call `submit_migration_insight` without context).
- **FR-018**: Every tool modified by this feature MUST preserve its existing documented error shape on all failure paths. No fix may change the fields returned when a tool encounters an error; if a fix requires a richer error, the documented Returns table MUST be updated before implementation. *(GAP-009)*
- **FR-019**: `execute_custom_cypher` MUST remain read-only. No fix in this feature may route any graph write through `execute_custom_cypher`; all mutable writes MUST go through their owning tools only. *(GAP-010)*

### FR → ISSUE Traceability

Issue numbers below use **ISSUES.md body numbering** (ISSUE-001 through ISSUE-015). ISSUE-011 is explicitly a duplicate of ISSUE-008 (both concern `--force-refresh`) and is consolidated into FR-015; it does not appear separately. This yields 14 unique defects.

| FR | ISSUES.md (body #) | Severity | Summary |
|----|-------------------|----------|---------|
| FR-001 | ISSUE-001 | CRITICAL | `sortableVersion` formula mismatch in version-map skill |
| FR-002 | ISSUE-001 | CRITICAL | Pre-computed Sortable cells use wrong formula |
| FR-003 | ISSUE-012 | MEDIUM | Version tables carry no staleness indicator or upstream link |
| FR-004 | ISSUE-014 | LOW | Angular boundary note duplicated |
| FR-005 | ISSUE-004 | HIGH | `STEP_OUTCOME` relationship never written |
| FR-006 | ISSUE-004 | HIGH | `STEP_OUTCOME` idempotency contract |
| FR-007 | ISSUE-015 | LOW | `close_migration_context` rejects valid `"abandoned"` status |
| FR-008 | ISSUE-003 | HIGH | `severity_threshold` parameter ignored in Cypher |
| FR-009 | ISSUE-006 | HIGH | `AUTOMATED_BY` traversed from wrong node type |
| FR-010 | ISSUE-007 | MEDIUM | `resolve_deprecation` aliases entity name as `original_entity` |
| FR-011 | ISSUE-009 | MEDIUM | `require_no_params` reads non-existent `r.requiredParams` |
| FR-012 | ISSUE-009 | MEDIUM | `only_composite` reads non-existent `r.isComposite` |
| FR-013 | ISSUE-010 | MEDIUM | `submit_migration_insight` dedup undocumented; return shape inconsistent |
| FR-014 | ISSUE-002 | HIGH | `queriedEntities` cache has no write path |
| FR-015 | ISSUE-008 + ISSUE-011 | MEDIUM | `--force-refresh` mechanism undefined (ISSUE-011 consolidated here) |
| FR-016 | ISSUE-005 | HIGH | Rollback skill referenced but does not exist |
| FR-017 | ISSUE-013 | LOW | Loop IV has no stateless-fallback variant |
| FR-018 | (cross-cutting) | — | Error shapes preserved across all modified tools |
| FR-019 | (cross-cutting) | — | `execute_custom_cypher` stays read-only |

### Key Entities

- **`MigrationContext`**: Tracks the state of a migration session. Gains a properly-written `queriedEntities` map. `status` field now accepts `"abandoned"`.
- **`STEP_OUTCOME` relationship**: `(MigrationContext)-[:STEP_OUTCOME]->(MigrationStep)` with properties `status`, `reason`, `updatedAt`. Must be written by `update_step_status` and be queryable by the progress-summary pattern.
- **`OpenRewriteRecipe`**: Node linked to `MigrationStep` via `AUTOMATED_BY`. Properties include `composite` (boolean). Required parameters are `RecipeParam` nodes linked via `HAS_PARAM`.
- **`sortableVersion`**: Integer property on version nodes. Canonical formula: `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH`.
- **Rollback skill**: A new loadable resource (`skill://framework-migration/rollback`) defining the build-failure revert procedure.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (SINGLE_FORMULA)**: Exactly one `sortableVersion` formula exists across all project documents; the canonical formula, when applied to inputs `(3,10,0)` and `(3,9,0)`, yields `f(3,10,0) > f(3,9,0)` — verified as a formula-level property, not a table-row comparison.
- **SC-002 (NO_HALF_RECOMPUTE)**: Zero pre-computed Sortable cells in the version tables deviate from the canonical formula's output; a mechanical re-check of all rows passes without exception.
- **SC-003 (STEP_OUTCOME_WRITTEN)**: After recording a step outcome, the schema's progress-summary query returns a non-zero count for that context.
- **SC-004 (OUTCOME_IDEMPOTENT)**: Recording the same `(context, step)` outcome twice results in exactly one `STEP_OUTCOME` relationship in the graph.
- **SC-005 (SEVERITY_FILTERED)**: A tier-1 scope query (`severity_threshold="high"`) returns zero steps with `severity` in `{"low", "medium"}`.
- **SC-006 (RECIPES_NONEMPTY)**: `analyze_upgrade_path` with `include_recipes=true` returns at least one non-empty recipe object for any step that has an `AUTOMATED_BY` edge in the graph.
- **SC-007 (FIELD_NAME_MATCHES_DOC)**: `resolve_deprecation` response contains a non-null `entity_name` field for every known deprecated entity.
- **SC-008 (PARAM_FILTER_REAL)**: `require_no_params=true` excludes all recipes with at least one required `RecipeParam`; `only_composite=true` returns only recipes where `composite=true`.
- **SC-009 (DEDUP_OBSERVABLE)**: The similarity threshold for `submit_migration_insight` is stated in the tool reference; the response shape (including `duplicate_of`) is consistent across all three status paths.
- **SC-010 (CACHE_POPULATED)**: After querying an entity in Loop II, a subsequent resume of the same context finds that entity in `queriedEntities` and does not re-issue the tool call.
- **SC-011 (ABANDONABLE)**: `close_migration_context` with `final_status="abandoned"` succeeds and sets the context's `status` property to `"abandoned"`.
- **SC-012 (ROLLBACK_LOADABLE)**: The rollback skill resource loads without error and contains at least one concrete revert step.
- **SC-013 (STATELESS_LOOP_IV)**: The main skill document contains a Loop IV stateless-fallback section that lists which steps are skipped and which are performed in-memory.
- **SC-014 (FRESHNESS_DECLARED)**: The version-map document includes a `Last Updated` date and at least one upstream support schedule link.
- **SC-015 (NO_REGRESSION)**: The full existing automated test suite passes without modification after all fixes are applied. Because every defect in this feature is a silent-correctness fix (no error was thrown before), no previously-passing test should fail as a result of these changes.

---

## Assumptions

- `graph-schema.md` is the authoritative source for all property and relationship names; no new properties are invented to implement any fix.
- Version-map data is not duplicated into code; the version-map skill remains the catalogue and is updated in place.
- The rollback skill resource is a skill/documentation artifact; it may reference standard VCS operations (`git stash`, `git checkout HEAD`) or OpenRewrite dry-run mode without requiring new graph nodes or schema changes.
- The concrete forms of the `queriedEntities` write mechanism (FR-014) and the `--force-refresh` mechanism (FR-015) are unresolved at specification time; both are flagged as design-gate items to be decided in the plan.
- ISSUE-011 in ISSUES.md is a duplicate of ISSUE-008 (both concern `--force-refresh`) and is resolved by the single FR-015 requirement; only 14 unique defects are in scope.
- The behavioural contracts in FR-005 (additive writes), FR-006 (idempotency), FR-018 (error shapes), and FR-019 (read-only execute_custom_cypher) are firm: they are not subject to trade-off decisions in planning.
- Concurrent writes to `STEP_OUTCOME` and the legacy arrays are **out of scope**. Last-write-wins semantics under concurrent callers are acceptable; this feature does not introduce or require distributed locking.
- Issue-numbering convention: all ISSUE references in this document use **ISSUES.md body numbering** (001–015). The summary table in ISSUES.md uses a different sequence (001–014, with ISSUE-011 omitted); this spec uses body numbers throughout to avoid ambiguity.

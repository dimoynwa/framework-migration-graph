# Feature Specification: Real-Run Hardening

**Feature Branch**: `013-real-run-hardening`

**Created**: 2026-06-14

**Status**: Draft

**Input**: Hardens the Migration Oracle MCP server and four-loop harness against failure modes found on the first real migration run (paysafe-wallet-switch, Spring Boot 3.5.12 → 4.0.6).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Consistent Version Resolution (Priority: P1)

A migration engineer invokes two different Oracle tools in the same session for the same (framework, version) pair. Both tools must reach the same verdict — either both accept the version as usable or both reject it. No contradiction is possible.

**Why this priority**: A version verdict contradiction killed the feedback stage on the first real run. Until this is fixed, no subsequent workstream can produce a trustworthy result.

**Independent Test**: Call `check_version_availability` for `spring-boot 3.5.12`, then call `submit_migration_insight` for the same framework and version. Verify both return the same usability verdict and the same resolved node identifier.

**Acceptance Scenarios**:

1. **Given** Spring Boot 3.5.12 is in the graph, **When** `check_version_availability` is called for `spring-boot 3.5.12`, **Then** it returns `exists_in_graph: true` and the resolved Version node id.
2. **Given** Spring Boot 3.5.12 is in the graph, **When** `submit_migration_insight` is called with `fromVersion: "3.5.12"`, **Then** it resolves to the same node and succeeds — it never silently no-ops.
3. **Given** Spring Boot 3.5.14 is requested but only 3.5.12 exists in the catalogue, **When** `check_version_availability` is called for `spring-boot 3.5.14` as a lower bound, **Then** the floor path resolves down to 3.5.12, returns `exists_in_graph: true` with the resolved node, and includes a `rounded: true` flag.
4. **Given** Spring Boot 4.0.9 is requested but the highest catalogued 4.0.x node is 4.0.6, **When** the target is resolved as an upper bound, **Then** it clamps to 4.0.6, returns `aheadOfCatalogue: true` in the response, and is never rejected.
5. **Given** a version is supplied with an explicit patch (e.g., `3.5.12`), **When** resolution runs, **Then** the patch is preserved exactly — never truncated to `3.5.0`.
6. **Given** a framework version string has no match at any catalogued minor line (e.g., a completely unknown framework), **When** `resolve_version` is called, **Then** it returns an explicit `NO_CANDIDATE` failure response naming the framework and version it attempted — never a swallowed exception.
7. **Given** Spring Boot 6.0.0 is requested but the highest catalogued Spring Boot node is 4.1.0, **When** the target is resolved as an upper bound, **Then** it clamps to 4.1.0, returns `aheadOfCatalogue: true`, and is never rejected.

---

### User Story 2 — Context Discovery and Supersede (Priority: P1)

A migration engineer resumes work on a project and discovers a stale in-progress context from a previous session with a different target triple. The engineer must be able to list all contexts for the project, abandon the stale one, and start a clean context for the correct triple — without manual database surgery.

**Why this priority**: A stale context was silently resumed on the first real run, polluting the session state and wasting the engineer's time discovering the mismatch.

**Independent Test**: Create a context for `project-X 3.5.12→4.0.0`, then call `get_migration_contexts` for `project-X`. Verify the response includes the stale context. Abandon it, create `project-X 3.5.12→4.0.6`, and verify only the new context is active.

**Acceptance Scenarios**:

1. **Given** a project has one or more MigrationContext records, **When** `get_migration_contexts(projectId)` is called, **Then** each context is returned with: `id`, `fromVersion`, `toVersion`, `status`, `createdAt`, `updatedAt`, and outcome counts (completed, failed, skipped, deferred from STEP_OUTCOME).
2. **Given** a stale `in_progress` context exists for the wrong triple, **When** it is abandoned via `close_migration_context` with `final_status: "abandoned"`, **Then** its status updates to `abandoned`, `updatedAt` is set to the current time, and a subsequent `get_migration_contexts` call reflects the change.
3. **Given** a fresh context is created after abandonment, **When** `create_migration_context` is called with the correct triple, **Then** it creates and returns the new context (not the abandoned one), with `created: true`.
4. **Given** a project has no contexts, **When** `get_migration_contexts` is called, **Then** it returns an empty list with a clear `count: 0` — not an error.
5. **Given** `create_migration_context` is called twice with the identical `(projectId, fromVersion, toVersion)` triple, **When** the second call runs, **Then** it returns the existing context (idempotent MERGE) with `created: false`, the stored identity strings, and the resolved `UPGRADES_TO` Version node version — the engineer can detect the match without inspecting the database.

---

### User Story 3 — Resume Scan Fidelity (Priority: P2)

When a migration engineer re-enters an existing context by calling `create_migration_context` on a triple that already exists (the MERGE match path), the entity set returned and stored must reflect the current allow-list-filtered scan of the codebase — not a stale snapshot from the original creation. Entities that would not pass the allow-list today are dropped and reported. The server enforces the allow-list regardless of what the caller supplies.

**Why this priority**: Application classes polluted the entity set on the first real run because the allow-list filter was not applied on the MERGE match path.

**Independent Test**: Create a context, inject a non-allow-listed entity into its stored state, then call `create_migration_context` again with the same triple. Verify the response excludes the injected entity, reports a nonzero `droppedCount`, and that the stored context no longer contains the injected entity.

**Acceptance Scenarios**:

1. **Given** a context has stored entities including non-allow-listed names, **When** `create_migration_context` is called again with the same triple (MERGE match), **Then** the server rejects non-allow-listed entities from the stored set — the returned `scannedEntities` list contains only allow-list-passing names, regardless of what was stored.
2. **Given** non-allow-listed entities were dropped during the match path, **Then** the response includes `droppedCount` with the number of removed entities.
3. **Given** the match path runs a fresh codebase scan, **When** it completes, **Then** the stored entity set in the context node is overwritten with the filtered result via `ON MATCH SET` — the stale entities are not retained.
4. **Given** a caller submits entity names that include non-allow-listed values, **When** the server processes the request, **Then** the server strips those names before persisting and reflects the drop in `droppedCount` — the server does not trust the caller to pre-filter.

---

### User Story 4 — Recipe-Aware Execution Routing (Priority: P2)

When the Oracle determines that a step is mechanical and automatable but has no associated OpenRewrite recipe, it must not silently defer the step. It must route it to the agent-applied codemod executor, which applies the transformation directly, validates via build and test, and marks the step completed or failed. The engineer confirms all affected files before any changes are applied. A failed codemod does not halt the session — the harness continues with remaining steps.

**Why this priority**: The largest required change on the first real run (Jackson 2→3) was silently deferred because automation was gated on a recipe that did not exist. The step was never attempted.

**Independent Test**: Create a migration step with `automatable: true`, a concrete instruction (e.g., `rename com.fasterxml.jackson.* to tools.jackson.*`), an entity anchor, and no recipe. Trigger execution routing. Verify the step enters the agent-codemod track, the engineer is shown all affected files before any changes are applied, and a failed gate triggers rollback and continues with remaining steps.

**Acceptance Scenarios**:

1. **Given** a step has a fully resolved recipe (recipe present, `auto=true`, no missing required params), **When** routing runs, **Then** the step enters the OpenRewrite executor track — regardless of the `automatable` flag value.
2. **Given** a step has a recipe that exists but requires params not yet supplied, **When** routing runs, **Then** the step enters the prompted-auto track: the missing params are surfaced to the engineer; once supplied the step re-enters the OpenRewrite track.
3. **Given** a step has no recipe, effort=mechanical, a concrete instruction, and an entity anchor, **When** routing runs, **Then** the step enters the agent-codemod executor track.
4. **Given** a step has no recipe, effort=moderate, a concrete instruction, and an entity anchor, **When** routing runs, **Then** the step enters the agent-codemod executor track.
5. **Given** a step has no recipe and either lacks a concrete instruction or lacks an entity anchor, **When** routing runs, **Then** the step routes to the human-review track with an explanation — it is never silently deferred.
6. **Given** a step has effort=architectural, **When** routing runs, **Then** the step routes to the human-review track regardless of recipe or instruction presence.
7. **Given** the agent-codemod executor is ready to apply a transformation, **When** it evaluates the scope, **Then** it presents the complete list of files to be modified and asks the engineer to confirm before any changes are applied — the step does not proceed without confirmation.
8. **Given** the agent-codemod executor runs and the build+test gate passes, **Then** the step is marked `completed`.
9. **Given** the agent-codemod executor runs and the build+test gate fails, **Then** the step is rolled back to its pre-transformation state, marked `failed`, and the failure reason is recorded.
10. **Given** one agent-codemod step has failed and been rolled back, **When** the harness evaluates remaining steps in the current tier, **Then** it continues executing them — the failed step does not halt the session and appears in the Loop IV backlog.

---

### User Story 5 — Bridge Tracking (Priority: P2)

When a sanctioned compatibility bridge is applied instead of the direct required change (e.g., adding a compatibility shim), the Oracle records the outcome as deferred-but-tracked. The bridge must be discoverable from the migration rule graph — the harness does not accept arbitrary agent-invented bridges as sanctioned. The outstanding required change appears in the migration backlog and is visible on re-entry. The deferred item is neither lost between the `completed` and `skipped` outcome states nor silently treated as done. A bridge is resolved only when the real migration change it defers has been completed.

**Why this priority**: Without explicit tracking, bridges become permanent — the real change is never surfaced again.

**Independent Test**: Apply a bridge for a step. Verify the step's STEP_OUTCOME has `status: "deferred"` with a structured reason. Re-enter the context and verify the deferred step is in the Loop IV backlog. Mark the real change completed and verify the bridge item is resolved.

**Acceptance Scenarios**:

1. **Given** a bridge is applied for a migration step and the bridge is discoverable from the graph for that rule, **When** the outcome is recorded via `update_step_status`, **Then** the step's STEP_OUTCOME status is `deferred` with a structured reason including: `bridgeName`, `bridgeReason`, and `requiredChange`; the outcome is distinct from both `completed` and `skipped`.
2. **Given** the agent attempts to apply a bridge that is not discoverable from the rule's graph data, **When** the outcome is recorded, **Then** the operation MUST be rejected — only graph-catalogued bridges produce a `deferred` outcome; ad-hoc workarounds are not eligible.
3. **Given** a step is marked `deferred` via bridge, **When** `get_migration_contexts` or context re-entry surfaces the backlog, **Then** the step appears in the Loop IV backlog — it is not absent from the active work list.
4. **Given** a session is re-entered after a bridge was applied, **Then** the deferred step is included in the active work list — it is not silently dropped.
5. **Given** the real migration change referenced by a bridge step has been completed and marked `completed`, **When** the context state is updated, **Then** the bridge-deferred step is resolved and no longer appears in the active backlog.

---

### User Story 6 — Typed Dependency Resolution Failures (Priority: P3)

When external dependency resolution fails because credentials are absent or invalid (e.g., Paysafe artifact registry auth token missing), the Oracle returns a typed `auth_error` status — distinct from both generic errors and network-transport failures — with remediation guidance and the list of unresolved dependencies as backlog items.

**Why this priority**: Engineers need to distinguish a credential configuration problem from a data problem or a network failure so they can take the right remediation action without debugging opaque failures.

**Independent Test**: Configure the resolver with invalid credentials. Trigger a dependency resolution. Verify the response status is `auth_error`, includes a `remediationSteps` field naming the required env vars, and lists the unresolved dependencies as backlog items.

**Acceptance Scenarios**:

1. **Given** credentials are missing or invalid, **When** external dependency resolution is attempted, **Then** the response status is `auth_error` with a structured error including: `failureReason`, `remediationSteps` (naming the specific missing credentials), and `unresolvedDependencies`.
2. **Given** a network or transport failure occurs (distinct from auth), **When** external dependency resolution is attempted, **Then** the response status is `transport_error` — a separate status from `auth_error` — so the engineer can distinguish misconfiguration from connectivity.
3. **Given** any `RESOLUTION_FAILED` variant is returned, **Then** each unresolved dependency is emitted as a backlog item so it surfaces on the next planning pass.
4. **Given** a documented fallback path exists for the failed resolver, **Then** the response includes a `fallbackInstructions` field describing the alternative (e.g., using Gradle's dependency warnings directly).

---

### User Story 7 — Portable Codebase Scanning (Priority: P3)

The codebase scanning step runs correctly on both macOS/BSD and GNU/Linux developer environments. When an optional parser (e.g., tree-sitter or a language-specific extractor) is absent, the scan degrades gracefully with reduced coverage rather than failing, and reports which extractor path was used.

**Why this priority**: Scan failures block the entire migration session. Cross-platform portability is a baseline correctness requirement for any developer tool.

**Independent Test**: Run the scan on macOS with and without the optional parser installed. Verify both runs complete successfully, the macOS BSD-variant flags are used, and the response includes an `extractorPath` field.

**Acceptance Scenarios**:

1. **Given** scanning runs on macOS (BSD utilities), **When** the scan executes, **Then** it uses BSD-compatible flags and completes without error.
2. **Given** scanning runs on Linux (GNU utilities), **When** the scan executes, **Then** it uses GNU-compatible flags and completes without error.
3. **Given** an optional parser is absent, **When** the scan executes, **Then** it falls back to the basic extractor, logs a warning about reduced coverage, and completes — it does not fail.
4. **Given** any scan completes, **Then** the response includes `extractorPath` indicating which extraction strategy was used (e.g., `"treesitter"`, `"basic"`, `"java-parser"`).

---

### Edge Cases

- What happens when the requested version has no minor-line match at all in the catalogue (not just a missing patch)? → Resolution MUST return `NO_CANDIDATE` failure, never a swallowed exception (FR-A11).
- How does the system handle `get_migration_contexts` for a `projectId` that has never had a context created? → Returns empty list with `count: 0`, not an error (US2.4, FR-B01).
- What if `create_migration_context` is called a second time with the exact same `(projectId, fromVersion, toVersion)` triple? → Idempotent MERGE — returns existing context with `created: false`, no duplicate created (US2.5, FR-B06).
- What if the agent-codemod executor runs against files already migrated in a prior step? → The executor MUST detect the already-migrated state and mark the step `completed` without re-applying changes — no double-edit (FR-C10).
- What if a bridge is applied to a step that already has `status: completed`? → The bridge application MUST be rejected; a completed step cannot be retroactively demoted to deferred.
- What if the agent attempts to apply a bridge not discoverable from the rule's graph data? → Rejected — only graph-catalogued bridges produce a `deferred` outcome (FR-C11, US5.2).
- What if the agent-codemod executor produces changes that break an unrelated test? → The build+test gate catches this; rollback restores all touched files; the step is marked `failed`; the harness continues with remaining steps (FR-C04).
- What happens when two concurrent sessions call `create_migration_context` on the same triple simultaneously? → Concurrent modification MUST be detected and rejected; the second caller receives a conflict error (FR-B08).
- What if the scanning allow-list itself is missing or malformed? → Scanning MUST fail with an explicit configuration error — it MUST NOT proceed with an empty or implicit allow-list.
- What if a target version is above the entire framework catalogue (no catalogued node at or above it)? → Resolution clamps to the highest catalogued node for the framework, returns `aheadOfCatalogue: true`, and never rejects the request (FR-A05). This is the same handling as the minor-line ceiling case.
- How does the system behave when the Loop II query→execute hand-off threshold is set to zero (execute immediately)? → Execution starts after tier 1 completes; test-scope (tier 4) is still sequenced last (FR-D04).

## Requirements *(mandatory)*

### Functional Requirements

**Workstream A — Version Resolution**

- **FR-A01**: The system MUST implement a single shared version resolution routine (`resolve_version`) consumed by every tool that maps a (framework, version) string to a graph Version node; no tool may inline a separate resolution path.
- **FR-A02**: Lower-bound resolution (current/from version) MUST resolve using a floor strategy: the nearest catalogued Version node whose sortable rank is at or below the requested version's sortable rank.
- **FR-A03**: Upper-bound resolution (target/to version) MUST resolve using a ceiling strategy: the nearest catalogued Version node whose sortable rank is at or above the requested version's sortable rank. The context identity stores the exact requested string; the resolved ceiling node is used only for rule-range bounding and graph relationship linking — these are distinct, non-conflicting concerns (see also FR-B03).
- **FR-A04**: When a caller supplies an explicit patch number, `resolve_version` MUST preserve it exactly in both its return value and any derived context identity; only a missing patch component may be filled (defaulting to `.0`). Normalization MUST NOT truncate or overwrite a patch the caller provided.
- **FR-A05**: When a target version is newer than the highest catalogued node for its framework (minor-line ceiling or full-catalogue ceiling), `resolve_version` MUST clamp to the highest available node, return `aheadOfCatalogue: true`, and never return a rejection.
- **FR-A06**: `check_version_availability` and `submit_migration_insight` MUST produce the same usability verdict for any given (framework, version) input, because both route through the single shared `resolve_version` routine.
- **FR-A07**: `submit_migration_insight` MUST invoke `resolve_version` first; only after a successful resolution does the cosine-similarity dedup check run. If `resolve_version` fails, the dedup check is skipped and the explicit failure response is returned directly — including the candidate(s) considered. `submit_migration_insight` MUST NOT silently no-op on a resolution failure.
- **FR-A08**: Resolution results MUST include a `rounded` flag when the catalogued node differs from the requested version, and an `aheadOfCatalogue` flag when the target was clamped to the highest available node.
- **FR-A09**: The version catalogue MUST include Spring Cloud entries with: train version, Boot compatibility range, and a note that the 2025.1.x train uses BOM-only import (no `spring-cloud-starter-parent`). When a Boot major upgrade is identified and the version catalogue indicates a corresponding Spring Cloud train boundary, the system MUST surface a co-migration warning to the engineer identifying the required Cloud train change (FR-A12).
- **FR-A10**: `resolve_version` MUST be read-only against Version nodes by default. The one exception — MERGE-ing a minimal Version stub for a just-released target whose framework is known but whose exact patch is not yet in the catalogue — MUST be gated behind an explicit opt-in flag (`allow_stub_create`). Callers must be warned that a stub-created node lacks full rule coverage and carries an orphan-node risk if the catalogue is later updated without reconciliation.
- **FR-A11**: When `resolve_version` finds no catalogued node matching the requested framework at any minor line (i.e., the framework itself is unknown), it MUST return a `NO_CANDIDATE` failure response naming the framework and requested version it attempted. This is a distinct status from `aheadOfCatalogue`; a swallowed exception is not acceptable.
- **FR-A12**: When the engineer's planned upgrade crosses a Boot major boundary that the Spring Cloud compatibility table maps to a required Cloud train change, the Oracle MUST emit a co-migration warning identifying: the current Cloud train, the required Cloud train for the target Boot version, and whether the 2025.1.x BOM-only constraint applies.

**Workstream B — Context Lifecycle**

- **FR-B01**: The system MUST expose a `get_migration_contexts` operation that returns all MigrationContext records for a given `projectId`, including: `id`, `fromVersion`, `toVersion`, `status`, `createdAt`, `updatedAt`, and outcome counts (completed, failed, skipped, deferred) derived from STEP_OUTCOME relationships. Total step count and "pending" count are not returned — they require running the full applicability query and belong to `get_pending_steps`. When no contexts exist for the project, the operation MUST return an empty list with `count: 0` — not an error.
- **FR-B02**: The system MUST allow an in-progress context to be abandoned via `close_migration_context` with `final_status: "abandoned"`; the round-1 `"abandoned"` close status contract MUST be preserved.
- **FR-B03**: Context identity — the `(projectId, fromVersion, toVersion)` MERGE key — MUST store the exact requested version strings as supplied by the caller. The resolved floor and ceiling Version nodes are written only to the `UPGRADES_FROM` and `UPGRADES_TO` relationships and used only for rule-range bounding; they MUST NOT overwrite the identity triple. This rule and FR-A02/FR-A03 are complementary: identity resolution preserves the exact requested patch; range-bound resolution rounds; the two concerns are orthogonal and MUST NOT be conflated.
- **FR-B04**: On every `create_migration_context` call (both create and match paths), the server MUST run the scanning allow-list against the submitted entity set and server-side reject any entity that does not pass. The filtered entity set MUST replace the stored set in the context node (via `ON MATCH SET` on the match path, and as the initial write on the create path) and MUST be the only set returned to the caller.
- **FR-B05**: Every `create_migration_context` response MUST include `droppedCount` reporting the number of entities rejected by the allow-list filter (0 on create if all pass; nonzero on match if stale entities were removed).
- **FR-B06**: `create_migration_context` MUST be idempotent on the `(projectId, fromVersion, toVersion)` triple. A second call with an identical triple MUST return the existing context with `created: false`, the stored identity strings, and the resolved `UPGRADES_TO` Version node version string plus `rounded` and `aheadOfCatalogue` flags — so the engineer can detect a triple mismatch and see the actual range bounds without a separate query.
- **FR-B07**: `MigrationContext` MUST carry an `updatedAt` timestamp property. It MUST be set on every operation that changes context state: `create_migration_context` (both create and match paths), `close_migration_context`, and every STEP_OUTCOME write against the context. `get_migration_contexts` MUST return `updatedAt` as the last-activity indicator for the context.
- **FR-B08**: When two callers attempt to write to the same `MigrationContext` node simultaneously (e.g., two concurrent `create_migration_context` MERGE calls on the same triple), the second operation MUST be detected and rejected with a conflict error. It MUST NOT silently overwrite the first caller's in-flight state.

**Workstream C — Execution Routing**

- **FR-C01**: The `automatable` flag on a migration step is advisory. A step MUST route to an automated track only when the runtime evaluation confirms a usable executor exists; the boolean flag alone is never sufficient.
- **FR-C02**: A **resolved recipe** is one where: the `AUTOMATED_BY` edge exists (`rec IS NOT NULL`), `auto=true`, and `missingRequiredParams=[]`. A **partially resolved recipe** is one where the edge exists but `auto=false` OR `missingRequiredParams ≠ []`. The executor selection MUST follow this decision order, covering all input combinations with exactly one track per combination and no ambiguous or undefined state:

  | Recipe state | Effort | Instruction + entity anchor | Track |
  |---|---|---|---|
  | Fully resolved | any | any | OpenRewrite |
  | Partially resolved (missing params) | any | any | Prompted-auto |
  | None | `mechanical` | Yes | Agent-codemod |
  | None | `moderate` | Yes | Agent-codemod |
  | None | `mechanical` | No | Human-review |
  | None | `moderate` | No | Human-review |
  | None | `architectural` | any | Human-review |

  `automatable=true` with no recipe routes purely by effort and instruction presence — never to an automated track on the boolean alone. The `automatable` flag is metadata for reporting, not a routing input.

- **FR-C03**: A step with no resolved recipe, effort=mechanical or effort=moderate, a concrete instruction, and an entity anchor MUST route to the agent-codemod executor track. A **concrete instruction** is one that includes at least one of: (a) a before/after transformation example, (b) a named operation type (`rename`, `replace`, `remove`, `add`) with its source and target, or (c) a pattern (string, glob, or regex) plus a replacement target. Free-text descriptions without a transformation pattern do not qualify; such steps route to human-review.
- **FR-C04**: The agent-codemod executor MUST make a best-effort attempt to apply the full transformation before the gate runs. It MUST: (1) apply the transformation to the matched files; (2) run the build-and-test gate; (3) mark the step `completed` on gate pass; (4) trigger rollback to the full pre-transformation working-tree state and mark the step `failed` (with recorded reason) on gate failure. Rollback MUST restore all files touched by the transformation to their exact pre-change state. After rollback, the harness MUST continue processing any remaining steps in the current tier — a single failed codemod MUST NOT halt the session. The failed step MUST appear in the Loop IV backlog with its failure reason.
- **FR-C05**: When a sanctioned compatibility bridge is applied, the outcome MUST be recorded by calling `update_step_status` with `outcome: "deferred"` and a structured reason containing `bridgeName`, `bridgeReason`, and `requiredChange`. `deferred` is an additive extension to the `outcome` parameter and STEP_OUTCOME status enum — it is a new value added alongside the existing `completed | skipped | failed` values, not a replacement (see FR-D05). This `deferred` status MUST NOT be collapsed into `completed` or `skipped`.
- **FR-C06**: A bridge-deferred step MUST appear in the Loop IV backlog and MUST be visible on context re-entry as an active work item. It is resolved — and removed from the backlog — only when the `requiredChange` it references is subsequently marked `completed`.
- **FR-C07**: Entity matching MUST be exact-string at its core and MUST additionally support a documented package-prefix bridge so that a migration rule targeting a dependency GA coordinate still matches when the project imports only the corresponding classes (the Jackson transitive-dependency case). When a rule affects a `Dependency` GA coordinate and the project's scanned imports include FQCNs whose package root is implied by that dependency, the rule MUST be treated as matched — not as `uncertain`.
- **FR-C08**: When `resolve_version` is invoked in read-only default mode and the requested version is not in the catalogue but the framework is known, it MUST return the appropriate floor or ceiling result with the `rounded` flag set — it MUST NOT create a Version stub unless `allow_stub_create` is explicitly set (FR-A10).
- **FR-C09**: Before the agent-codemod executor applies a transformation, it MUST present the complete list of files it will modify and require explicit confirmation from the engineer before proceeding. No codemod is applied without confirmation. The default behavior is to always confirm regardless of file count; a project-level override may raise the threshold to skip confirmation for small-scope changes, but the out-of-the-box default is all-files confirmation.
- **FR-C10**: The agent-codemod executor MUST detect when the transformation it is about to apply has already been applied to the target files (idempotency check). If the target state already matches the post-transformation expectation, the executor MUST mark the step `completed` without re-applying any changes — no double-edit.
- **FR-C11**: A bridge outcome (`status: "deferred"`) is only valid when the bridge is discoverable from the migration rule's graph data (a catalogued bridge property or relationship on the rule node). The harness MUST verify bridge discoverability before recording a deferred outcome; if no bridge is discoverable from the graph for the rule, the operation MUST be rejected. The specific graph representation (property vs. relationship) is defined in data-model.md.

**Workstream D — Orchestration**

- **FR-D01**: A failed external dependency resolution due to absent or invalid credentials MUST return `status: "auth_error"` (distinct from generic resolution failure). The response MUST include: `failureReason`, `remediationSteps` (naming the specific missing credential variables), and `unresolvedDependencies`. A network or transport failure MUST return `status: "transport_error"` — a separate status so the engineer can distinguish misconfiguration from connectivity. Both are subtypes of `RESOLUTION_FAILED` at the outer level.
- **FR-D02**: Each unresolved dependency from any `RESOLUTION_FAILED` response MUST be emitted as a backlog item.
- **FR-D03**: Loop II MUST define a configurable query→execute hand-off threshold; once the threshold is reached, the loop transitions from querying to execution without requiring manual intervention.
- **FR-D04**: Test-scope steps (tier 4) MUST always be sequenced last in Loop II execution order, regardless of the hand-off threshold configuration.
- **FR-D05**: The following round-1 contracts MUST be extended, not broken: `STEP_OUTCOME` relationship write path (this spec adds `deferred` as a new status value to the enum — this is additive and does not alter the existing `completed | skipped | failed` values or the relationship shape); `update_queried_entity` operation and its key/value schema; the `queriedEntities` skip guard and `--force-refresh` escape mechanism; the `status: "abandoned"` close-status value on `close_migration_context`. This feature MUST NOT revert, remove, or silently change any of them.
- **FR-D06**: The system MUST provide targeted evaluation coverage for the three round-1 fixes that were not exercised by the first real-project run: (1) rollback skill execution — triggered by a deliberately failing automated step; (2) stateless-fallback variant of Loop IV — triggered by a context-creation failure injection; (3) `get_steps_for_scope_tier` severity threshold filtering — verified by a fixture with mixed-severity steps queried at both `high` and `low` thresholds. These paths MUST have passing eval cases before their ISSUE-005, ISSUE-013, and ISSUE-003 resolutions are treated as fully validated.

**Workstream E — Portable Scanning**

- **FR-E01**: The codebase scanning implementation MUST produce correct results on both macOS/BSD and GNU/Linux environments without requiring environment-specific configuration from the engineer.
- **FR-E02**: When an optional extractor (parser, language tool) is absent, scanning MUST fall back to the basic extractor, log a reduced-coverage warning, and complete successfully.
- **FR-E03**: Every scan response MUST include an `extractorPath` field identifying which extraction strategy ran.

### Key Entities

- **VersionResolutionResult**: Resolved Version node id, the original requested string, `rounded` flag, `aheadOfCatalogue` flag, resolution direction (floor/ceil), `stubCreated` flag when applicable.
- **MigrationContext**: Project id, exact requested `fromVersion`/`toVersion` strings, resolved floor/ceil node references (stored only in UPGRADES_FROM/UPGRADES_TO), status, `createdAt`, `updatedAt` (set on every state-changing operation), entity set, step list, backlog.
- **ExecutorRoute**: Step id, routing decision (openrewrite / prompted-auto / agent-codemod / human-review), rationale, blast-radius estimate, executor input parameters.
- **DeferredOutcome**: Step id, STEP_OUTCOME `status: "deferred"`, `bridgeName`, `bridgeReason`, `requiredChange` — linked to the owning MigrationContext backlog; resolved when `requiredChange` reaches `completed`. Only valid when bridge is graph-discoverable (FR-C11).
- **ResolutionFailure**: Outer `status: "RESOLUTION_FAILED"`, sub-status (`auth_error` / `transport_error` / `NO_CANDIDATE`), `failureReason`, `remediationSteps`, `unresolvedDependencies[]`, optional `fallbackInstructions`.
- **ScanResult**: Entity list (allow-list filtered), `droppedCount`, `extractorPath`, warnings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Any two Oracle tools invoked with the same (framework, version) input in the same session agree on usability verdict in 100% of cases — zero contradictions observed across a full migration session.
- **SC-002**: A migration engineer can discover, review, and supersede a stale context within a single tool-call sequence, without manual intervention in the database or configuration files.
- **SC-003**: On `create_migration_context` (match path), the entity set reflects the current allow-list state; non-allow-listed entities are rejected server-side and the count is reported — zero stale entities survive into the active session.
- **SC-004**: Every mechanical migration step with a concrete instruction and an entity anchor is either completed or explicitly failed within the session — zero steps are silently left in a deferred-without-reason state.
- **SC-005**: Every bridge application produces a visible Loop IV backlog entry that survives the next context re-entry; zero bridge-deferred items are silently dropped or collapsed into `completed`/`skipped`.
- **SC-006**: Dependency resolution failures are classified with typed statuses (`auth_error` vs `transport_error`) and reported with actionable remediation in 100% of failure cases — zero silent or opaque errors.
- **SC-007**: Codebase scanning completes successfully on both macOS and Linux developer machines without manual configuration; reduced-coverage fallback is logged when the optional parser is absent.
- **SC-008**: The three previously unvalidated round-1 fixes (rollback, stateless fallback, severity threshold) each have a passing eval lane exercising their specific code path.

## Assumptions

- The existing Neo4j graph already contains Version nodes for the Spring Boot versions needed for the first real migration run (3.5.x, 4.0.x); the catalogue extension for Spring Cloud can be added as part of this spec's data-side work.
- The four-loop harness skill exists and is callable from Claude Code; this spec targets its contract and routing logic, not a full rewrite.
- The build-and-test gate used by the agent-codemod executor is the project's existing Maven/Gradle build command; no new build tooling is introduced.
- Rollback in the agent-codemod executor means reverting file changes to the pre-transformation state using the version-control working tree; no database transaction rollback is required.
- "Sanctioned compatibility bridge" is defined by the migration rule graph (a bridge is a known, graph-catalogued alternative path); ad-hoc workarounds invented by the agent are not bridges and are not eligible for the deferred-but-tracked outcome.
- OpenRewrite remains an optional accelerator; its installation is not a prerequisite for any migration step to proceed, and its absence changes only which executor is selected — never whether a step is attempted.
- Loop II's configurable hand-off threshold defaults to a value that mirrors the current behavior; changing the default is out of scope for this spec.
- All round-1 tool contracts (`STEP_OUTCOME`, `update_queried_entity`, `queriedEntities` cache, `"abandoned"` close status) are extended, not replaced; this spec adds `deferred` to the STEP_OUTCOME status enum additively.
- The blast-radius confirmation behavior defaults to always-confirm (FR-C09); a project-level override may set a numeric threshold to skip confirmation for small-scope changes, but the default requires confirmation for any file count.
- Concurrent-session conflict detection is a correctness requirement (FR-B08); the locking mechanism (optimistic or pessimistic) is an implementation choice outside the spec's scope.

## Clarifications

### Session 2026-06-14

- Q: When an agent-codemod step fails (build+test gate fails → rollback → `status: failed`), should the harness continue with remaining steps or halt the session? → A: Continue with remaining steps in the tier; record failed step in Loop IV backlog; agent makes best-effort attempt before marking failed.
- Q: What makes an instruction "concrete" enough to qualify for the agent-codemod track? → A: Must include a transformation pattern — a before/after example, a named operation type (rename/replace/remove/add) with source and target, or a pattern plus replacement target. Free-text descriptions without a pattern route to human-review instead.
- Q: What is the default blast-radius confirmation threshold for agent-codemod? → A: Always confirm — the agent presents all affected files and requires explicit confirmation before any codemod applies; project-level override can raise the threshold for small-scope changes.

## Issue Traceability

The table below maps every open issue from the Round 2 findings (ISSUE-016 through ISSUE-030) to at least one spec anchor. All 15 issues are covered.

| Issue | Severity | Description (short) | Spec Anchor(s) |
|---|---|---|---|
| ISSUE-016 | CRITICAL | `submit_migration_insight` rejects version that `check_version_availability` accepts | FR-A01, FR-A06, FR-A07, US1 |
| ISSUE-017 | HIGH | Context resumes wrong triple after silent patch truncation | FR-A04, FR-B03, FR-B06, US1.5, US2.5 |
| ISSUE-018 | HIGH | No lookup-by-project tool; stale contexts cannot be listed or abandoned | FR-B01, US2 |
| ISSUE-019 | HIGH | `scanned_entities` polluted with app classes on resume | FR-B04, FR-B05, US3 |
| ISSUE-020 | HIGH | Router trusts `automatable=true` with no recipe — ambiguous routing | FR-C01, FR-C02, FR-C03, US4 |
| ISSUE-021 | MEDIUM | Compatibility bridges not modelled — required rules silently deferrable | FR-C05, FR-C06, FR-C11, US5 |
| ISSUE-022 | HIGH | Paysafe dep resolution failure is silent; no auth vs transport distinction | FR-D01, FR-D02, US6 |
| ISSUE-023 | MEDIUM | Loop II has no stop condition — no rule for when to stop querying | FR-D03, FR-D04 |
| ISSUE-024 | MEDIUM | Spring Cloud / train-based versioning absent | FR-A09, FR-A12 |
| ISSUE-025 | MEDIUM | Catalogue lags real targets (4.0.6 missing); fresh date implies false currency | FR-A05, FR-A08, FR-A10 |
| ISSUE-026 | HIGH | `grep -oP` GNU-only — scan breaks on macOS/BSD; PyYAML unhandled | FR-E01, FR-E02, FR-E03, US7 |
| ISSUE-027 | MEDIUM | Dep-coord vs FQCN granularity mismatch demotes matches to `uncertain` | FR-C07 |
| ISSUE-028 | LOW | Rollback, stateless fallback, severity threshold unvalidated by real run | FR-D06, SC-008 |
| ISSUE-029 | HIGH | Auto track is OpenRewrite-only — recipe-less mechanical steps deferred | FR-C01, FR-C02, FR-C03, FR-C04, US4 |
| ISSUE-030 | MEDIUM | Target ahead of catalogue truncates rule range — needs ceil resolution | FR-A02, FR-A03, FR-A05, FR-A08, FR-B03, US1.3–1.4 |

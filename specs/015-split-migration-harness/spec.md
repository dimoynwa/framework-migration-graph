# Feature Specification: Split Migration Harness

**Feature Branch**: `015-split-migration-harness`

**Created**: 2026-06-18

**Status**: Draft (Note: Do not proceed to `/speckit.plan` until the unresolved interaction in FR-014 is explicitly answered)

**Input**: User description: "Splits the existing four-loop migration harness across independent agent sessions at the loop boundaries, and inserts two new stages — gap-check (mechanical plan audit) and preview (read-only customer-facing rendering) — plus makes the existing ad-hoc human-amendment need into a named, optional clarify stage. The system exposes six session-scoped entry points: plan, gap-check, clarify, preview, execute, feedback. Each later stage resumes purely from MigrationContext graph state, never from conversation memory of an earlier stage's session."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Plan and Audit Migration (Priority: P1)

As a migration operator, I want to run the planning phase and then mechanically audit the resulting plan via a gap-check, so that I can identify potential issues (like truncated rule sets, uncertain applicability, or unresolved dependencies) before any execution begins.

**Why this priority**: This establishes the foundational separation of planning from execution and introduces the critical new audit capability.

**Independent Test**: Can be fully tested by running the `plan` stage to generate a MigrationContext, then running the `gap-check` stage to verify it correctly flags issues and writes them to the context without mutating the step/rule state or requiring execution context.

**Acceptance Scenarios**:

1. **Given** a codebase requiring migration, **When** the `plan` stage completes, **Then** a MigrationContext is created with pending steps.
2. **Given** a MigrationContext with uncertain rules, **When** the `gap-check` stage is run, **Then** it outputs a list of flags for those rules and attaches them to the context without modifying the underlying step/rule graph.
3. **Given** a "lite" mode MigrationContext, **When** the `gap-check` stage is run, **Then** it only performs truncation, applicability, and version sanity checks (skipping stepless-rule and bridge-eligibility checks).

---

### User Story 2 - Clarify and Amend Plan (Priority: P1)

As a human operator, I want to review gap-check findings and optionally clarify the plan by re-surfacing excluded rules, adding manual steps, or explicitly excluding steps, so that the plan is accurate and complete before execution.

**Why this priority**: Human-in-the-loop correction is the primary reason for splitting the harness, ensuring high-quality migrations.

**Independent Test**: Can be fully tested by taking an existing MigrationContext, invoking the `clarify` stage, adding a manual step, excluding an existing step, and verifying the graph reflects these changes correctly.

**Acceptance Scenarios**:

1. **Given** a MigrationContext, **When** I add a manual step during `clarify`, **Then** it is saved as a context-scoped MigrationStep that appears in the pending queue.
2. **Given** a MigrationContext, **When** I exclude a step during `clarify`, **Then** its outcome is marked as "excluded" and it does not block final completion status.
3. **Given** a missed rule, **When** I force-include it during `clarify`, **Then** its steps are merged into the pending queue.

---

### User Story 3 - Read-Only Preview (Priority: P2)

As a customer or reviewer, I want to view a read-only preview of the migration plan, grouped by risk label and including gap-check caveats, so that I can understand what will change without risking accidental modifications.

**Why this priority**: Provides a safe, customer-facing artifact for approval before execution.

**Independent Test**: Can be fully tested by invoking the `preview` stage on a MigrationContext and verifying it renders the plan correctly while exposing zero mutation tools.

**Acceptance Scenarios**:

1. **Given** a clarified MigrationContext, **When** the `preview` stage is run, **Then** it displays the plan grouped by risk label (HIGH/MEDIUM/LOW) with gap-check caveats visible.
2. **Given** the `preview` session, **When** I attempt to mutate the plan, **Then** no mutation tools are available to execute.

---

### User Story 4 - Execute and Complete (Priority: P1)

As a migration operator, I want to execute the approved plan across potentially multiple sessions, automatically resuming from the graph state, so that interruptions do not lose progress or require full context re-loading.

**Why this priority**: Execution is the core value delivery; resuming from graph state solves the context bloat problem.

**Independent Test**: Can be fully tested by running the `execute` stage, interrupting it, and resuming it in a new session to verify it picks up exactly where it left off using only the graph state.

**Acceptance Scenarios**:

1. **Given** exactly one "in_progress" MigrationContext, **When** `execute` is invoked without a context ID, **Then** it auto-discovers and resumes that context.
2. **Given** multiple "in_progress" MigrationContexts, **When** `execute` is invoked without a context ID, **Then** it raises an error listing the candidates.
3. **Given** a context with completed and "excluded" steps, **When** `close_migration_context` is called, **Then** the final status is "complete" (not "partial").

### Edge Cases

- What happens when `gap-check` is run on an already completed migration?
- How does the system handle `execute` being called before `plan` has finished?
- What if a manual step added during `clarify` lacks required fields expected by downstream queries?
- How does `preview` render a plan that has no gap-check flags?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose six distinct, session-scoped entry points: `plan`, `gap-check`, `clarify`, `preview`, `execute`, and `feedback`.
- **FR-002**: All stages after `plan` MUST resume state purely from the MigrationContext graph state, without relying on conversation memory from previous sessions.
- **FR-003**: The `gap-check` stage MUST be strictly read-only regarding step/rule state and codebase state (no calls to `update_step_status`, `update_queried_entity`, or `add_manual_step`), but it MUST write `GapCheckFlag` nodes or properties back to the `MigrationContext`.
- **FR-004**: The `gap-check` stage MUST perform mode-specific checks according to the following table (checking the `mode` property on the `MigrationContext` node):

  | Check Type | Full Mode (`mode="full"`) | Lite Mode (`mode="lite"`) |
  |---|---|---|
  | Truncation Check | Yes | Yes |
  | Applicability Audit | Yes | Yes |
  | Stepless-Rule Check | Yes | No |
  | Bridge-Eligibility Surfacing | Yes | No |
  | Version Sanity Check | Yes | Yes |
  | Unresolved Paysafe Dependency | Yes | Yes |
- **FR-005**: The `clarify` stage MUST allow re-surfacing existing graph rules via an extended `update_queried_entity` tool with a force-include flag.
- **FR-006**: The `clarify` stage MUST allow adding codebase-specific manual tasks via a new `add_manual_step` tool. This tool MUST create a `MigrationStep` node with `origin="manual"` and use a distinct relationship type (name TBD in data-model.md, e.g., `OWNS_STEP`) from the `MigrationContext` to the manual `MigrationStep`. This relationship is used ONLY for scoping/visibility — separate from whatever relationship later records that step's `STEP_OUTCOME` once it's acted on.
- **FR-007**: The `clarify` stage MUST allow excluding steps via `update_step_status` with `outcome="excluded"`.
- **FR-008**: The `preview` stage MUST run in a read-only session. A `preview` session, given any mutation tool name, MUST refuse execution or have no such tool registered.
- **FR-009**: The `preview` stage MUST render the plan grouped by risk label (HIGH/MEDIUM/LOW) and display gap-check findings as visible caveats.
- **FR-010**: The `execute` stage MUST auto-discover the context if exactly one `in_progress` context exists. If multiple exist and no ID is provided, it MUST raise an error returning a list of candidates formatted as `{context_id, framework, current_version, target_version}` to allow human disambiguation.
- **FR-011**: The `execute` stage MUST re-call `get_pending_steps` fresh on every invocation.
- **FR-012**: A context with `outcome="excluded"` steps MUST NOT be capped at `final_status="partial"` during `close_migration_context`, provided all other steps are completed.
- **FR-013**: Manual steps MUST satisfy all existing `OPTIONAL MATCH` queries written for graph-derived steps without requiring query modifications.
- **FR-014**: The interaction between an excluded step and any `BRIDGED_BY` edge pointing to it as `requiredChange` is UNRESOLVED pending a plan-stage mechanism check against `update_step_status`'s existing auto-resolve logic.
- **FR-015**: The `gap-check`, `clarify`, and `preview` stages MUST validate the provided `context_id`. If an invalid or nonexistent `context_id` is passed, the command MUST return an explicit error.
- **FR-016**: The `add_manual_step` tool MUST require `context_id`, `summary`, and `instruction` parameters. The parameters `file_pattern` (default: null/global), `effort` (default: "moderate"), and `severity_hint` (default: "medium") MUST be optional with sensible defaults (aligning with the `MigrationStep` effort enum `"mechanical"`, `"moderate"`, `"architectural"` and the `BreakingScope` severity enum `"low"`, `"medium"`, `"high"`, `"critical"`).
- **FR-017**: Whether `plan`/`gap-check`/`clarify`/`preview`/`execute`/`feedback` require any confirmation gate before acting is UNDECIDED — default assumption is no, pending explicit confirmation in gap review.

### Key Entities

- **MigrationContext**: The central graph node holding the state of a migration, including its mode (`mode="lite"` or `mode="full"`) and status.
- **MigrationStep**: Represents a specific action to take. Can be graph-derived or manually created (`origin="manual"`). Graph-derived steps are reachable via standard rule traversal; manually created steps are scoped to their owning context via a distinct ownership relationship (name TBD in data-model.md), separate from the `STEP_OUTCOME` relationship that records a step's execution outcome (completed/skipped/excluded/etc.) regardless of origin.
- **GapCheckFlag**: A finding produced by the `gap-check` stage, stored on or associated with the MigrationContext for retrieval by `clarify` and `preview`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Context bloat is eliminated: `execute` and `feedback` sessions are never given tool definitions for `plan`/`gap-check`/`clarify`-only tools (`analyze_upgrade_path`, `search_migration_knowledge`, `add_manual_step`), verified by session tool-registration inspection.
- **SC-002**: 100% of `preview` sessions expose zero mutation tools, ensuring complete safety for customer review.
- **SC-003**: `gap-check` successfully identifies 100% of injected truncation, applicability, and unresolved dependency issues in test migrations.
- **SC-004**: Manual steps added via `clarify` are successfully retrieved and executed by the unmodified `execute` stage in 100% of cases.
- **SC-005**: Migrations with only completed and "excluded" steps successfully reach a "complete" final status 100% of the time.

## Assumptions

- The underlying graph database (Neo4j) supports the required schema additions (e.g., `origin="manual"`, new `outcome` enum values) without breaking existing constraints.
- The tool registration layer supports restricting tool exposure per session to enforce the read-only nature of the `preview` stage.
- Users understand that `clarify` is optional and can proceed directly from `gap-check` to `execute` if the plan is acceptable.

# Feature Specification: linear-file-migration-state

**Feature Branch**: `017-linear-file-migration-state`

**Created**: 2026-07-07

**Status**: Draft

**Input**: User description: Moves per-migration PROGRESS out of the knowledge graph and into three version-controlled files...

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Plan a new migration (Priority: P1)

As an engineer preparing a framework upgrade, I want to run the plan stage to generate a complete overview of the migration so that I can see the strategy, rule ledger, and tasks without modifying any shared state.

**Why this priority**: Planning is the foundational entry point for any migration; without the initial files, no other stage can run.

**Independent Test**: Can be independently tested by running the plan stage and verifying that `ps-migration/{framework}-{from}-to-{to}/` is created with `plan.md`, `tasks.md`, and the skeleton of `verification.md`, and that the knowledge graph is not mutated.

**Acceptance Scenarios**:

1. **Given** a consumer repository ready for a migration, **When** the plan stage is run, **Then** `plan.md`, `tasks.md`, and `verification.md` skeleton are generated under `ps-migration/{framework}-{from}-to-{to}/` at the project root.
2. **Given** the plan stage runs, **When** it queries the knowledge graph, **Then** only read operations occur and no context/session state is written to the graph.

---

### User Story 2 - Execute migration tasks linearly (Priority: P1)

As an engineer performing the migration, I want the execute stage to work tasks strictly in order from `tasks.md`, updating their statuses directly in the file, so that progress is version-controlled, diffable, and reviewable in a PR.

**Why this priority**: Execution is the core loop where actual code changes occur and state transitions happen.

**Independent Test**: Can be tested by running the execute stage on an existing `tasks.md` and verifying that task statuses change (e.g., from `pending` to `done` or `failed`) directly within the file without any session/context database updates.

**Acceptance Scenarios**:

1. **Given** a populated `tasks.md`, **When** the execute stage runs, **Then** it processes tasks in strict numeric order (TASK-001..NNN).
2. **Given** a task is completed, **When** the execute stage updates progress, **Then** the task's Status in `tasks.md` is edited to `done`, `failed`, or `needs-review`.
3. **Given** a task fails its per-task verification, **When** the execute stage handles it, **Then** the rollback skill is run, the task is marked as `failed`, but execution continues to the next task (the full build happens at the end via `verification.md`).

---

### User Story 3 - Run non-mutating intermediary stages (Gap-check, Clarify, Preview) (Priority: P2)

As an engineer reviewing the migration plan, I want to use gap-check, clarify, and preview stages to annotate, adjust, and review tasks before execution without querying the graph again.

**Why this priority**: Important for human-in-the-loop validation, but relies on plan being complete first.

**Independent Test**: Can be tested by running gap-check, clarify, and preview sequentially and verifying that they only read from or mutate the local markdown files (annotating missing verifiers, promoting relevance index to tasks, rendering read-only views) without accessing the knowledge graph.

**Acceptance Scenarios**:

1. **Given** the gap-check stage runs, **When** it analyzes `plan.md` and `tasks.md`, **Then** it adds inline annotations for mechanical gaps (missing verifiers, empty instructions) without reading the graph.
2. **Given** the clarify stage runs, **When** a relevance-index entry is promoted, **Then** it becomes a real TASK with Origin=manual in `tasks.md`.
3. **Given** the preview stage runs, **When** invoked, **Then** it renders a read-only grouped view without modifying files and without touching the graph.

---

### User Story 4 - Gate completion via verification.md (Priority: P1)

As an engineer finalizing the migration, I want the execute stage to run the verification gate at the end, enforcing that no tasks are pending/failed and all `needs-review` tasks have explicit human sign-offs, to ensure quality guarantees are maintained.

**Why this priority**: Verification ensures that the migration is strictly validated before being considered complete, maintaining system integrity.

**Independent Test**: Can be tested by attempting to pass verification with pending tasks or `needs-review` tasks lacking sign-offs, and confirming that the gate fails.

**Acceptance Scenarios**:

1. **Given** all tasks are marked `done`, **When** verification.md Level 5-B is checked, **Then** the gate passes.
2. **Given** a task is marked `needs-review` without a human sign-off line, **When** verification runs, **Then** the gate fails.
3. **Given** execution completes, **When** verification is finalized, **Then** execute fills in the discovered build/test/run commands into `verification.md` before executing the gate.

---

### Edge Cases

- What happens when the knowledge graph changes after `plan.md` is generated? (Execute detects `plan.md` age > 7 days and suggests re-planning, logging a drift warning, but does not auto-replan or auto-update tasks)
- What happens when a `needs-review` task is skipped? (It remains in the file and blocks the verification completion gate until an explicit human sign-off line is added)
- What happens if the execute stage attempts to modify a `com.paysafe.*` dependency? (The verification Level 5-A strictly catches this and fails the build)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: **Folder Location**: The system MUST store all migration state across three files (`plan.md`, `tasks.md`, `verification.md`) within exactly one folder located at `$PROJECT_ROOT/ps-migration/{framework}-{from}-to-{to}/`. The folder MUST be visible (not a dotfolder), MUST NOT be nested under `specs/`, and one migration equals exactly one folder. Resumption MUST equal re-reading the folder and `git status`.
- **FR-002**: **No Session State in Graph**: The system MUST NOT persist any migration progress or context/session data into the knowledge graph. The schema edit MUST explicitly delete the `MigrationContext` node, the `STEP_OUTCOME` relationship, and the queried-entity cache. The system MUST retain the knowledge subgraph elements (`Version`, `MigrationRule`, `MigrationStep`, `OpenRewriteRecipe`, `Class`, `ApplicationProperty`, `Dependency`, and `community-insight` rules).
- **FR-003**: **Exact-Shape Contracts**: The three file schemas are exact-shape contracts, not loose suggestions, and MUST be emitted verbatim by the skills (with these shapes carried in `data-model.md`):
  - `plan.md` Rule Ledger columns: `RuleID` | `Scope` | `EntityMatched` | `classification` | `applicability` | `Render` | `tasks.md`
  - `tasks.md` task-block fields: `Status`, `Derives-from`, `Origin`, `Executor`, `Recipe`, `Effort`, `File pattern`, `Instructions`, `Verify`
  - `verification.md` structure: Levels 0-5 (with Level 5 comprising sub-checks 5-A/B/C).
- **FR-004**: **Status Enum**: The system MUST strictly use a four-way status enum for tasks: `pending | done | failed | needs-review`. The `deferred` status is explicitly removed, and `needs-review` absorbs both of its prior meanings ("agent stuck, flag a human" and "human consciously chose to skip").
- **FR-005**: **Render Outcomes Enum**: The render table MUST have exactly four outcomes based on these trigger conditions:
  1. Actionable + ≥1 non-empty MigrationStep + matched entity ⇒ `TASK`
  2. Actionable + ≥1 non-empty MigrationStep + matched entity BUT effort=architectural OR generic/templated instruction ⇒ `TASK` flagged `NEEDS-DESIGN-REVIEW`
  3. entityClassification=incomplete (AFFECTS_* edges, no REQUIRES_STEP) ⇒ `RELEVANCE-INDEX`
  4. applicability=uncertain (safety-net match) ⇒ `RELEVANCE-INDEX` labeled uncertain
  The fifth `PLACEHOLDER` / `BRIDGED_BY` outcome from the hybrid design is explicitly removed. `BRIDGED_BY` survives strictly as graph KNOWLEDGE surfaced inside task instructions.
- **FR-006**: **Deleted Tools**: The system MUST enumerate and delete the seven legacy session-state MCP tools: `create_migration_context`, `get_migration_contexts`, `get_pending_steps`, `update_step_status`, `close_migration_context`, `update_queried_entity`, and `get_steps_for_scope_tier`. These MUST be deleted outright, including their handler modules, Cypher queries, server registrations, and `tests/mcp/` coverage. There MUST be no fold into `analyze_upgrade_path`, no context-free variant, and no alias.
- **FR-007**: **Retained Tools Boundary**: All tools not explicitly named in FR-006 MUST be retained unchanged (including `analyze_upgrade_path`, `resolve_deprecation`, `entity_evolution`, `search_migration_knowledge`, `build_recipe_plan`, `resolve_paysafe_dependency_by_service_name`, `check_version_availability`, `get_community_insights`, `vote_insight`, `verify_insight`, `get_graph_schema`, `execute_custom_cypher`, `list_pipeline_runs`, `get_artifact_content`, and `install_migration_skill`). No knowledge tool may gain, lose, or rename a parameter to absorb a deleted tool's role.
- **FR-008**: **Graph Read/Write Boundary**: The system MUST adhere to strict graph write and read boundaries per stage:
  - `plan`: reads knowledge only.
  - `gap-check`, `clarify`, `preview`: never touch the graph.
  - `execute`: reads knowledge only when stuck (search-before-skip), never writes state.
  - The sole migration-reachable graph write is the user-initiated `submit_migration_insight`. `execute`'s tail MUST NOT auto-submit insights.
- **FR-009**: **Plan Execution Requirement**: The `plan` stage MUST run AFTER the full escalation chain (`analyze_upgrade_path` -> `resolve_deprecation` -> `entity_evolution` -> `search_migration_knowledge`), never from a cheap one-query-per-entity pass. The `applicability=universal` accuracy failure cited in `MIGRATION_LITE_MODE.md` is the explicitly named anti-pattern avoiding this.
- **FR-010**: **Gap-check Stage Mechanics**: The `gap-check` stage MUST read `plan.md` and `tasks.md` and add inline annotations for mechanical gaps. It MUST ensure every task shows Origin and applicability, and it MUST explicitly flag missing verifiers, empty instructions, and unclassified rules.
- **FR-011**: **Clarify Stage Mechanics**: The `clarify` stage MUST provide two distinct write actions for the Relevance Index: (1) promote an entry to a real TASK with `Origin=manual`, and (2) dismiss an entry with a recorded reason in `tasks.md`.
- **FR-012**: **Drift Rule**: When a later stage re-queries the graph and finds a rule changed since the snapshot, the system MUST treat the file as the source of truth for progress/intent and the graph as the source of truth for knowledge. A drift note MUST be surfaced in `tasks.md`, and it MUST never trigger a silent re-plan.
- **FR-013**: **Execute Stage Mechanics**: The `execute` stage MUST process tasks sequentially (TASK-001..NNN), modifying the task `Status` directly in `tasks.md`, and MUST NOT perform any task-to-task back-references or float placeholders. It MUST extract the executor route directly from the `Executor` (valid values: `openrewrite | prompted-auto | agent-codemod | human-review`) and `Recipe` fields of each task block.
- **FR-014**: **Verification Split**: The `plan` stage MUST generate the `verification.md` skeleton (Levels 0 and 5-A/B/C derived from the Rule Ledger and per-task verifiers). The `execute` stage MUST finalize `verification.md` by filling in the build/test/run commands discovered from the repo before running it as a completion gate.
- **FR-015**: **Completion Gate Definition**: The completion gate MUST consist of exactly three parts (5-A ∧ 5-B ∧ 5-C):
  - **5-A**: The Paysafe constraint holds (no `com.paysafe.*` dependency was modified/removed/downgraded).
  - **5-B**: Zero `pending` or `failed` tasks AND explicit human sign-off on every `needs-review` task. Flipping this single sub-gate is the only way to loosen the `needs-review` policy, preserving the "never silently skip" guarantee.
  - **5-C**: Every Relevance-Index entry is either promoted to a task or explicitly dismissed with a reason.
- **FR-016**: **Instruction Deliverable**: The system MUST include a top-level `INSTRUCTION.md` required deliverable. It MUST cover: folder contents/files, the stage sequence (`plan` -> `gap-check` -> `clarify` -> `preview` -> `execute`, with `clarify` and `preview` optional), resumption process (no session state), the verification gating + `needs-review` sign-off rule, the Paysafe dependency constraint, and user-initiated insight submission.
- **FR-017**: **Feedback Stage Deletion**: The `feedback` stage (old Loop IV) MUST be deleted. The `005-streamlit-ui`'s context dashboard is downstream-affected because it reads `MigrationContext` and MUST be re-scoped.
- **FR-018**: **Tool Count Reconciliation**: Tool-count reconciliation across `mcp-tools-skills-prompts.md` and the agent instructions is in scope. It MUST reconcile them against the actual registered tool set at implementation, and MUST NOT assert a specific absolute before/after number frozen in the spec.

### Key Entities

- **Migration Files**: Comprises `plan.md` (strategy/ledger), `tasks.md` (ordered task queue), and `verification.md` (completion gate) storing the exact, versioned state of the migration.
- **Task Block**: An entry in `tasks.md` holding defined fields (`Status`, `Derives-from`, `Origin`, `Executor`, `Recipe`, `Effort`, `File pattern`, `Instructions`, `Verify`) capturing all metadata for execution.
- **Knowledge Graph**: A stateless, read-only (for migration progress) Neo4j/Cypher database providing rules, dependencies, and recipes.
- **Executor Types**: `openrewrite | prompted-auto | agent-codemod | human-review`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of migration progress tracking is moved out of the Neo4j knowledge graph and into the 3 specified files.
- **SC-002**: The 7 specified legacy MCP tools, Cypher queries, handlers, and tests are completely deleted with 0 compatibility shims remaining.
- **SC-003**: A single migration run generates exactly 1 folder located at `$PROJECT_ROOT/ps-migration/{framework}-{from}-to-{to}/` containing exactly 3 markdown files.
- **SC-004**: The execute stage correctly modifies the task Status strings directly within `tasks.md` with 0 graph writes of migration progress/session state.
- **SC-005**: Attempting to pass the verification gate with a `needs-review` task missing an explicit human sign-off fails 100% of the time.
- **SC-006**: The file-only intermediary stages (`gap-check`, `clarify`, and `preview`) complete without any graph read or write operations, verifiable by audit log or network trace.

## Assumptions

- Engineers will commit the generated `ps-migration` folder into version control as part of their feature branch.
- The consumer repository structure allows the creation of a top-level directory without conflicting with existing build processes.
- The `ps-migration` folder format and markdown file schemas are exactly followed by the emitting skills.
- The project will maintain standard Git processes to review the generated files and progress diffs.
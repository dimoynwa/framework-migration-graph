---
description: "Task list template for feature implementation"
---

# Tasks: linear-file-migration-state

**Input**: Design documents from `specs/017-linear-file-migration-state/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 [P] Create INSTRUCTION.md at repo root with sections: folder contents, stage sequence, resumption, verification gating, Paysafe constraints, insight submission
- [X] T002 [P] Create plan template in migration_oracle/mcp/skills/templates/plan.md. Source: transcribe from design document §1-3 worked examples, conforming to data-model.md schemas.
- [X] T003 [P] Create tasks template in migration_oracle/mcp/skills/templates/tasks.md. Source: transcribe from design document §1-3 worked examples, conforming to data-model.md schemas.
- [X] T004 [P] Create verification template in migration_oracle/mcp/skills/templates/verification.md. Source: transcribe from design document §1-3 worked examples, conforming to data-model.md schemas.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 [P] Delete legacy context tools (handlers, Cypher) in migration_oracle/mcp/tools/context.py and migration_oracle/mcp/graph/queries/context.py
- [X] T006 [P] Delete feedback skill in migration_oracle/mcp/skills/framework_migration_feedback.md
- [X] T007 [P] Delete legacy tests in tests/mcp/test_context.py, tests/mcp/test_context_fixes.py, tests/mcp/test_step_outcome_e2e.py, tests/mcp/test_step_outcome_errors.py, tests/mcp/test_step_outcome_idempotency.py, tests/mcp/test_update_queried_entity_errors.py, tests/mcp/test_update_step_status.py, tests/mcp/test_close_migration_context.py, tests/mcp/test_get_migration_contexts.py, tests/mcp/test_get_steps_for_scope_tier.py
- [X] T008 [P] Remove context tools registration from migration_oracle/mcp/server.py
- [X] T009 [P] Remove context-subgraph writes from migration_oracle/pipeline/populator.py
- [X] T010 [P] Update graph schema docs in docs/graph-schema.md. Anchor: `### MigrationContext` and `(MigrationContext)──STEP_OUTCOME───►(MigrationStep)`. Edit: Name the sections dropped: MigrationContext node, STEP_OUTCOME relationship, queried-entity cache. Confirm BRIDGED_BY and community-insight rules are retained.
- [X] T011 [P] Update spec organization docs in docs/SPEC_ORGANIZATION.md. Anchor: `├── 04_context_dashboard.py # MigrationContext status...` and `├── context.py             # create_migration_context...`. Edit: Modify the 004 capability section by dropping the session-state tools and explicitly naming the removed items (context.py block). Mark the downstream UI section (04_context_dashboard.py) with a note acknowledging it requires re-scoping.
- [X] T012 Reconcile MCP tools prompts docs in docs/mcp-tools-skills-prompts.md against live registry. Anchor: `The core four-loop migration harness...` and `Call get_pending_steps...`. Edit: Rewrite to assert the five-stage linear sequence, remove mention of Loops I-IV or create_migration_context, clean up stateless fallback references. Remove the 7 tool entries completely. Reconcile tool counts against actual active tool count without asserting a hardcoded total.
- [X] T013 [P] Update agent instructions in .cursor/rules/specify-rules.mdc and CLAUDE.md. Anchor: Any text referencing a "four-loop" process. Edit: Rewrite the four-loop harness section to strictly dictate the five-stage file sequence. Verify no other file duplicates canonical schemas.
- [X] T014 Verify no new graph state (nodes/edges) is added to replace MigrationContext. Method: grep for CREATE/MERGE of new node labels in migration_oracle/mcp/graph/queries/ and migration_oracle/pipeline/ — expected: zero results for any label not in data-model.md's RETAINED list.

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Plan a new migration (Priority: P1) 🎯 MVP

**Goal**: Run the plan stage to generate a complete overview of the migration so that I can see the strategy, rule ledger, and tasks without modifying any shared state.

**Independent Test**: Can be independently tested by running the plan stage and verifying that `ps-migration/{framework}-{from}-to-{to}/` is created with `plan.md`, `tasks.md`, and the skeleton of `verification.md`, and that the knowledge graph is not mutated.

### Implementation for User Story 1

- [X] T015 [US1] Update main migration loop in migration_oracle/mcp/skills/framework_migration_main.md. Anchor: `## Loop I — Context (plan stage)` (and all Loop II, III, IV headers). Edit: Rewrite to replace loop nomenclature with the strict five-stage linear sequence (plan, gap-check, clarify, preview, execute), ensuring terminology and constraints align perfectly with the updated file-state design.
- [X] T016 [US1] Update plan skill in migration_oracle/mcp/skills/framework_migration_plan.md. Anchor: References to `skill://framework-migration-plan/main` or loop executions. Edit: Rewrite to assert that the plan stage must run AFTER the full escalation chain, completely read/write the ps-migration/ files, point to templates/ for canonical schemas, and confirm no graph writes or parameters were modified.
- [X] T017 [P] [US1] Update plan format docs in migration_oracle/mcp/skills/framework_migration_plan_format.md. Anchor: Any structure dictating the framework migration output. Edit: Evolve into, or replace with, documentation for the plan.md, tasks.md, and verification.md file schemas.

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 & 4 - Execute migration tasks linearly & Gate completion (Priority: P1)

**Goal**: Execute stage to work tasks strictly in order from `tasks.md`, updating their statuses directly in the file, and run the verification gate at the end, enforcing that no tasks are pending/failed and all `needs-review` tasks have explicit human sign-offs.

**Independent Test**: Can be tested by running the execute stage on an existing `tasks.md` and verifying that task statuses change directly within the file without any session/context database updates, and by attempting to pass verification with pending tasks or `needs-review` tasks lacking sign-offs, confirming that the gate fails.

### Implementation for User Story 2 & 4

- [X] T018 [US2, US4] Update execute skill in migration_oracle/mcp/skills/framework_migration_execute.md. Anchor: Mentions of iterating over `get_pending_steps` or equivalent. Edit: Rewrite to assert sequential progression (TASK-001..NNN), directly modifying tasks.md file status (pending/done/failed/needs-review). On build failure, rollback and mark failed (but fix-forward without halting the loop). Ensure verification.md commands are finalized at the very end. Implement verification gate logic (ensure 5-B sign-off required, execute finalizes verification.md, Paysafe 5-A check). Sign-off format must match: `**Sign-off**: [@username] [YYYY-MM-DD] — Reviewed and confirmed safe to proceed.`
- [X] T019 [US2, US4] Audit framework_migration_rollback.md for references to deleted tools (e.g., `update_step_status`). Edit: Update them to the file-state equivalent (e.g., "set Status to failed in tasks.md").

**Checkpoint**: At this point, User Stories 1, 2, and 4 should all work independently

---

## Phase 5: User Story 3 - Run non-mutating intermediary stages (Gap-check, Clarify, Preview) (Priority: P2)

**Goal**: Use gap-check, clarify, and preview stages to annotate, adjust, and review tasks before execution without querying the graph again.

**Independent Test**: Can be tested by running gap-check, clarify, and preview sequentially and verifying that they only read from or mutate the local markdown files without accessing the knowledge graph.

### Implementation for User Story 3

- [X] T020 [P] [US3] Update gap-check skill in migration_oracle/mcp/skills/framework_migration_gap_check.md. Anchor: References to `skill://framework-migration-gap-check/main` and its instructions block. Edit: Rewrite to assert reading only plan.md and tasks.md (no graph reads) and performing inline gap annotation to both tasks.md and plan.md.
- [X] T021 [P] [US3] Update clarify skill in migration_oracle/mcp/skills/framework_migration_clarify.md. Anchor: References to `skill://framework-migration-clarify/main` and its instruction blocks. Edit: Update logic to read/write tasks.md to promote Relevance-Index to manual tasks or dismiss with reasons.
- [X] T022 [P] [US3] Update preview skill in migration_oracle/mcp/skills/framework_migration_preview.md. Anchor: References to `skill://framework-migration-preview/main` and its instructions. Edit: Read-only rendering of grouping by risk/scope.

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T023 Grep for remaining imports of context.py and MigrationContext across tests/ directory and delete unlisted test files/fixtures
- [X] T024 Record the 005 context-dashboard downstream re-scope as a backlog item
- [X] T025 Update migration-file-state-design.md status to "Implemented"
- [X] T026 Update SPEC_ORGANIZATION.md row 006 to the right status

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed sequentially in priority order (US1 → US2/US4 → US3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 & 4 (P1)**: Depends on US1 completion (needs plan.md and tasks.md generated)
- **User Story 3 (P2)**: Depends on US1 completion (needs plan.md and tasks.md generated)

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Different user stories can be worked on in parallel by different team members

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 & 4 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

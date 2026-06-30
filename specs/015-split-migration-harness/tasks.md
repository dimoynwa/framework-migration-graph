---
description: "Task list for 015-split-migration-harness implementation"
---

# Tasks: Split Migration Harness

**Input**: Design documents from `/specs/015-split-migration-harness/`

**Prerequisites**: plan.md, spec.md, data-model.md, contracts/015-split-migration-harness.md, research.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Update `framework_migration_main.md` to reflect the 6 stages in `migration_oracle/mcp/skills/framework_migration_main.md`
- [X] T002 Update `docs/mcp-tools-skills-prompts.md` tool index and skill resource table
- [X] T003 Update `start_migration` and `resume_migration` prompts to reflect staged invocation in `migration_oracle/mcp/server.py`
- [X] T004 Update `install_migration_skill`'s bundle manifest to include the three new skill files in `migration_oracle/mcp/tools/install.py`

---

## Phase 2: Foundational (Schema and Queries)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Write Cypher query deltas for `OWNS_STEP`, `origin`, and `gapCheckFlags` persistence in `migration_oracle/mcp/graph/queries/context.py`
- [X] T006 Update `get_pending_steps` Cypher to `OPTIONAL MATCH (ctx)-[:OWNS_STEP]->(manualStep)` per data-model.md §1 in `migration_oracle/mcp/graph/queries/context.py`
- [X] T007 Implement session/tool-gating mechanism based on active stage in `migration_oracle/mcp/server.py`

**Checkpoint**: Foundation schema and queries ready

---

## Phase 3: Foundational (Tool Logic)

**Purpose**: Tool handlers that depend on the schema changes from Phase 2.

- [X] T008 Implement `write_gap_check_flags` tool logic in `migration_oracle/mcp/tools/context.py`
- [X] T009 Implement `add_manual_step` tool logic in `migration_oracle/mcp/tools/context.py`
- [X] T010 Update `update_step_status` to support `"excluded"` outcome in `migration_oracle/mcp/tools/context.py`
- [X] T011 Update `close_migration_context` to allow `"excluded"` steps for completion in `migration_oracle/mcp/tools/context.py`
- [X] T012 Implement explicit `context_id` validation for the three new stages (gap-check, clarify, preview) in `migration_oracle/mcp/tools/context.py`

**Checkpoint**: Foundation tools ready - user story implementation can now begin

---

## Phase 4: User Story 1 - Plan and Audit Migration (Priority: P1) 🎯 MVP

**Goal**: Run the planning phase and then mechanically audit the resulting plan via a gap-check.

### Tests for User Story 1
- [X] T013 Idempotency test for gap-check (calling twice against same context_id returns same flag list) in `tests/mcp/test_gap_check.py`

### Implementation for User Story 1
- [X] T014 [US1] Update `create_migration_context` to cache `diagnostics` payload on `MigrationContext` per data-model.md §6 in `migration_oracle/mcp/tools/context.py`
- [X] T015 [US1] Write `gap_check.md` skill file with mode-specific checks in `migration_oracle/mcp/skills/gap_check.md`

---

## Phase 5: User Story 2 - Clarify and Amend Plan (Priority: P1)

**Goal**: Review gap-check findings and optionally clarify the plan by re-surfacing excluded rules, adding manual steps, or explicitly excluding steps.

### Tests for User Story 2
- [X] T016 Manual-step cross-context isolation test (create two contexts, add manual step to one, confirm get_pending_steps against the other never returns it) in `tests/mcp/test_clarify.py`
- [X] T017 Error-path tests: invalid context_id passed to gap-check/clarify/preview; add_manual_step called with a context_id belonging to a closed context in `tests/mcp/test_clarify.py`

### Implementation for User Story 2
- [X] T018 [US2] Update `update_queried_entity` to support force-include flag in `migration_oracle/mcp/tools/context.py`
- [X] T019 [P] [US2] Write `clarify.md` skill file in `migration_oracle/mcp/skills/clarify.md`

---

## Phase 6: User Story 4 - Execute and Complete (Priority: P1)

**Goal**: Execute the approved plan across potentially multiple sessions, automatically resuming from the graph state.

### Tests for User Story 4
- [X] T020 Error-path test: execute called with no context_id and 2+ in_progress contexts in `tests/mcp/test_execute.py`

### Implementation for User Story 4
- [X] T021 [US4] Implement context auto-discovery and ambiguous-context error logic in the handler layer (e.g., `migration_oracle/mcp/server.py` or `migration_oracle/mcp/tools/context.py`)
- [X] T022 [US4] Update `execute` stage agent instructions to handle auto-discovery, ambiguous contexts, and fresh `get_pending_steps` polling in `migration_oracle/mcp/skills/framework_migration_main.md`

---

## Phase 7: User Story 3 - Read-Only Preview (Priority: P2)

**Goal**: View a read-only preview of the migration plan, grouped by risk label and including gap-check caveats.

### Implementation for User Story 3
- [X] T023 [P] [US3] Write `preview.md` skill file with grouping and caveat rendering in `migration_oracle/mcp/skills/preview.md`

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T024 E2E test covering the full six-command happy path with at least one gap-check flag and one clarify exclusion in `tests/e2e/test_split_migration_harness.py`
- [X] T025 Run quickstart.md validation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2 & 3)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 4+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 3) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 3) - No hard dependency on US1 (workflow note: typically acts on gap-check flags, but can be implemented and tested independently)
- **User Story 4 (P1)**: Can start after Foundational (Phase 3) - Depends on US1/US2 for plan generation and clarification
- **User Story 3 (P2)**: Can start after Foundational (Phase 3) - Depends on US1/US2 for plan generation and clarification

### Within Each User Story

- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- Different user stories can be worked on in parallel by different team members
- Tasks marked `[P]` (like new skill files) can be written in parallel with other tasks in their phase

---

## Parallel Example: User Story 2

```bash
# Launch new skill file creation in parallel with tool updates:
Task: "Update update_queried_entity to support force-include flag"
Task: "Write clarify.md skill file"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2 & 3: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 4: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 4 → Test independently → Deploy/Demo
5. Add User Story 3 → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

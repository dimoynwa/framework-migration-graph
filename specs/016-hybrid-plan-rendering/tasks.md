# Tasks: Hybrid Plan Rendering

**Input**: Design documents from `/specs/016-hybrid-plan-rendering/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. Since this feature is completely documentation/prompt-text based, tests correspond to manual validation paths.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Project initialization and basic structure
*Note: No setup tasks are required because this is a text amendment to existing files.*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented
*Note: No foundational infrastructure is required for a pure Markdown amendment.*

---

## Phase 3: User Story 1 - Plan Stage Migration Rule Classification (Priority: P1) 🎯 MVP

**Goal**: Update the `framework_migration_plan.md` skill to classify matched rules into exactly one of five outcomes (plus `UNCLASSIFIED` fallback) and append a plain-text classification suffix to the `update_queried_entity` prompt arguments, without changing any API signatures or gating.

**Independent Test**: Read the updated file and run the plan stage locally against the worked example. Verify the plain-text suffix appears in the output without dropping any rules from cache.

### Implementation for User Story 1

- [X] T001 [P] [US1] Edit `migration_oracle/mcp/skills/framework_migration_plan.md`
  **Anchor**:
  ```markdown
  **Skip guard:** Check `ctx.queriedEntities[entity_name]` before any tool call. After each successful query, call `update_queried_entity(context_id, entity_name, result_summary)`.
  ```
  **Insert**:
  ```markdown
  **Plan Classification:** After each successful query, before calling `update_queried_entity`, classify the matched rule into exactly one of five outcomes based on its `entityClassification`, `steps[]`, `applicability`, and `BRIDGED_BY`:
  1. `CONCRETE TASK`: `entityClassification="actionable"` AND ≥1 step with non-empty instructions AND matched exact entity.
  2. `CONCRETE TASK (NEEDS-DESIGN-REVIEW)`: Same as #1, but `effort="architectural"` OR instruction is generic.
  3. `RELEVANCE-INDEX ENTRY`: `entityClassification="incomplete"`.
  4. `RELEVANCE-INDEX ENTRY (uncertain)`: `applicability="uncertain"`.
  5. `PLACEHOLDER`: Rule has a `BRIDGED_BY` edge and its step is marked deferred.
  
  If a rule has anomalous or missing required fields, default to `UNCLASSIFIED`.
  
  Append a plain-text suffix identifying this classification (e.g., `... → TASK` or `... → NEEDS-INVESTIGATION`) to the `result_summary` argument of `update_queried_entity`. The classification suffix is strictly a non-gating label; it must NOT filter rules from being cached and must NEVER mutate the `applicability` field. No new parameters may be added to `update_queried_entity`.
  ```

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Explicit Traceability in Clarify Stage (Priority: P1)

**Goal**: Ensure relevance-index entries transitioned to concrete tasks via `add_manual_step` permanently retain `origin="manual"`.

**Independent Test**: Read the updated file and verify the constraint prohibiting retroactive `origin="graph"` rewriting is explicitly stated.

### Implementation for User Story 2

- [X] T002 [P] [US2] Edit `migration_oracle/mcp/skills/framework_migration_clarify.md`
  **Anchor**:
  ```markdown
  ### Add manual steps
  
  ```text
  add_manual_step(context_id, summary, instruction, file_pattern?, effort?, severity_hint?)
  ```
  
  Creates a `MigrationStep` with `origin="manual"` scoped via `OWNS_STEP` to this context only.
  ```
  **Insert**:
  ```markdown
  
  *Origin Preservation Rule:* This operation is the explicit, audited point where a relevance-index entry crosses over into a concrete task. The resulting step's `origin="manual"` must NEVER be retroactively rewritten to `origin="graph"` by any stage, even if community insights later formalize the same fix in the graph. This is a hard, irreversible constraint.
  ```

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Visual Provenance in Preview Stage (Priority: P2)

**Goal**: Mandatorily display the `origin` field for every rendered step line-item.

**Independent Test**: Read the updated file and verify that the `origin` field is promoted to a mandatory, visually distinct rendering requirement.

### Implementation for User Story 3

- [X] T003 [P] [US3] Edit `migration_oracle/mcp/skills/framework_migration_preview.md`
  **Anchor**:
  ```markdown
  Within each group, list: summary, instruction (truncated if long), effort, applicability, origin (`graph` or `manual`).
  ```
  **Insert**:
  ```markdown
  
  *Provenance Rendering:* It is **mandatory** to visibly display the `origin` field (`graph` or `manual`) for every rendered step line-item. A manual-origin step must never be visually indistinguishable from a graph-verified one.
  ```

**Checkpoint**: All user stories up to US3 are independently functional

---

## Phase 6: User Story 4 - Gap-Check Stepless Validation (Priority: P2)

**Goal**: Add an explanatory sentence to gap-check affirming it uses only the pre-existing `stepless_rule` check and must not invent new checks or payloads.

**Independent Test**: Read the updated file and verify the rule explicitly restricts new logic or schema additions.

### Implementation for User Story 4

- [X] T004 [P] [US4] Edit `migration_oracle/mcp/skills/framework_migration_gap_check.md`
  **Anchor**:
  ```markdown
  ### Stepless-rule check (full mode only)
  
  Use `get_steps_for_scope_tier` per scope tier. Flag rules with entity hits but no linked `MigrationStep`.
  ```
  **Insert**:
  ```markdown
  *Plan Rendering Note:* This pre-existing check is the actual enforcement mechanism for surfacing `RELEVANCE-INDEX ENTRY` candidates (the `NEEDS-INVESTIGATION` population) to a human. Do not introduce any new checks or modify the `write_gap_check_flags` payload shape.
  ```

**Checkpoint**: All user stories should now be independently functional

---

## Phase 7: User Story 5 - Reproducing Worked Example (Priority: P1)

**Goal**: Verify that the pipeline implementation reproduces the results of the worked example provided in the design document (`hybrid-plan-rendering.md §6`).

**Independent Test**: Follow the steps in `quickstart.md`.

### Implementation for User Story 5

- [X] T005 [US5] Verify amendments via manual walkthrough against `docs/hybrid-plan-rendering.md §6` according to `specs/016-hybrid-plan-rendering/quickstart.md`. Confirm the narrated outcomes exactly: `r1` receives `CONCRETE TASK` and `origin="graph"`, and `r2` receives `RELEVANCE-INDEX ENTRY` and `origin="manual"`. Both must be verified to have origin labels in preview's rendering rules.
- [X] T006 [US5] Verify exact constraints: confirm NO `add_manual_step`, `update_queried_entity`, `write_gap_check_flags`, or `get_pending_steps` tools changed signatures, NO parameters were added, and NO YAML `compatibility.tools` blocks were modified. Confirm zero changes were made to `execute`, `feedback`, `graph-schema`, or `mcp-tools-skills-prompts.md`.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T007 Review all four modified markdown files for consistent tone and exact spelling of anchor points.
- [X] T008 [P] Update `docs/hybrid-plan-rendering.md §7` (Open Questions) to append a resolution note regarding severity-bucketing: "Deferred to backlog — not addressed in this implementation. To be evaluated against real-world stepless_rule flag volume."
- [X] T009 [P] Update `docs/hybrid-plan-rendering.md` header line from "Status: Design amendment, not yet implemented." to "Status: Implemented." to signal completion of the feature.

---

## Dependencies & Execution Order

### Phase Dependencies

- **User Stories (Phase 3-6)**: All document edits can proceed in parallel (T001, T002, T003, T004).
- **User Story 5 (Phase 7)**: Depends on T001-T004 being complete, as it is the holistic verification step.
- **Polish (Final Phase)**: Depends on all edits being applied.

### Parallel Opportunities

- T001, T002, T003, and T004 target 4 completely independent files and can all be executed in parallel.

---

## Parallel Example: All File Edits (US1-US4)

```bash
# Apply text amendments in parallel
Task: "Edit migration_oracle/mcp/skills/framework_migration_plan.md"
Task: "Edit migration_oracle/mcp/skills/framework_migration_clarify.md"
Task: "Edit migration_oracle/mcp/skills/framework_migration_preview.md"
Task: "Edit migration_oracle/mcp/skills/framework_migration_gap_check.md"
```

---

## Implementation Strategy

1. Apply `framework_migration_plan.md` edits (US1)
2. Apply `framework_migration_clarify.md` edits (US2)
3. Apply `framework_migration_preview.md` edits (US3)
4. Apply `framework_migration_gap_check.md` edits (US4)
5. Run the verification checklist in `quickstart.md` (US5) to confirm zero code changes, preserved YAML headers, and matching the worked example.
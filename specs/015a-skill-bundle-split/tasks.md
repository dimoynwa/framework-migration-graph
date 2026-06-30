---
description: "Task list for 015a-skill-bundle-split implementation"
---

# Tasks: Split Migration Harness Skill Bundles

**Input**: Design documents from `/specs/015a-skill-bundle-split/`

**Prerequisites**: plan.md, spec.md, data-model.md, contracts/015a-skill-bundle-split.md, research.md, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Phase 1: Setup (Investigation — Blocking)

**Purpose**: Resolve the one genuinely open question before any bundle-manifest code is written.

**CRITICAL**: T002 is a blocking investigation task, not an implementation task. Per `data-model.md` §3, no task in this list implements FR-010's stale-layout handling — that remains explicitly out of scope until this investigation is complete and `data-model.md` §3 is updated with cited evidence. If T002's findings warrant new implementation work, that work is a follow-up to this spec, not contained in it.

- [X] T001 Read `install_migration_skill`'s actual current filesystem-write implementation (likely `migration_oracle/mcp/tools/install.py`) to confirm today's real overwrite/conflict behavior — no code change in this task, read-only investigation
- [X] T002 Record T001's findings in `data-model.md` Section 3 with a citation to the actual code reviewed; explicitly state whether FR-010 is now resolved or remains a follow-up item outside this spec's implementation scope

**Checkpoint**: FR-010's status is now either resolved-with-citation or explicitly deferred as a documented follow-up — either way, nothing later in this list depends on guessing it.

---

## Phase 2: Foundational (Cross-Spec Extension)

**Purpose**: The one piece of new server-side logic this spec needs, sequenced before anything that depends on it (the `resume_migration` decision table).

**CRITICAL**: No `resume_migration`-related task can begin until this phase is complete.

- [X] T003 Extend `get_migration_contexts`'s Cypher query to add `excluded` to `outcome_counts` and a new `has_gap_check_flags` boolean field, per `data-model.md` Section 4, in `migration_oracle/mcp/graph/queries/context.py`
- [X] T004 Update `get_migration_contexts`'s Python handler return-shape mapping to surface the two new fields in `migration_oracle/mcp/tools/context.py`
- [X] T005 Update `mcp-tools-skills-prompts.md`'s documented return shape for `get_migration_contexts` to include the two new fields, per the project convention that tool-behavior changes require doc updates alongside the handler

**Checkpoint**: `get_migration_contexts` now returns the signals the resume-stage decision table needs. Confirm via a quick manual query against a test context before proceeding — this is the one piece of new logic in the whole spec that isn't pure content reorganization.

---

## Phase 3: Foundational (Bundle Manifest)

**Purpose**: The install-mechanism change itself.

- [X] T006 Replace `install.py`'s single `framework-migration` bundle definition with the six-entry `FULL_MODE_BUNDLES` list per `data-model.md` Section 1, in `migration_oracle/mcp/tools/install.py`
- [X] T007 Update `install_migration_skill`'s return payload so `installed_skills` lists all six bundle names individually in full mode, in `migration_oracle/mcp/tools/install.py`

**Checkpoint**: Foundation ready — content-writing tasks for individual bundles can now proceed in parallel.

---

## Phase 4: User Story 1 - Independent Bundle Installation (Priority: P1) MVP

**Goal**: Six independent top-level bundles install correctly, with no cross-stage content leakage.

### Tests for User Story 1
- [X] T008 Structural test: run `install_migration_skill()` against a clean target dir, assert exactly six top-level bundle directories exist, each with exactly one `SKILL.md`, in `tests/mcp/test_install_bundles.py`
- [X] T009 Content-isolation test: assert no bundle's `SKILL.md` or `references/` content mentions another stage's mutation tools or procedural steps (string-search for forbidden tool names per stage, per `contracts/015a-skill-bundle-split.md`'s frontmatter contract) in `tests/mcp/test_install_bundles.py`
- [X] T010 Assert zero `framework-migration/references/{gap-check,clarify,preview}.md`-equivalent paths exist anywhere in the install output (regression test for the original defect) in `tests/mcp/test_install_bundles.py`

### Implementation for User Story 1
- [X] T011 [P] [US1] Write `framework_migration_plan.md` — extract Loop I + Loop II procedure from `framework_migration_main.md` in `migration_oracle/mcp/skills/framework_migration_plan.md`
- [X] T012 [P] [US1] Write `framework_migration_gap_check.md` — promote existing nested gap-check content to a standalone bundle `SKILL.md` in `migration_oracle/mcp/skills/framework_migration_gap_check.md`
- [X] T013 [P] [US1] Write `framework_migration_clarify.md` — promote existing nested clarify content to a standalone bundle `SKILL.md` in `migration_oracle/mcp/skills/framework_migration_clarify.md`
- [X] T014 [P] [US1] Write `framework_migration_preview.md` — promote existing nested preview content to a standalone bundle `SKILL.md` in `migration_oracle/mcp/skills/framework_migration_preview.md`
- [X] T015 [P] [US1] Write `framework_migration_execute.md` — extract Loop III procedure from `framework_migration_main.md` in `migration_oracle/mcp/skills/framework_migration_execute.md`
- [X] T016 [P] [US1] Write `framework_migration_feedback.md` — extract Loop IV procedure from `framework_migration_main.md` in `migration_oracle/mcp/skills/framework_migration_feedback.md`
- [X] T017 [US1] Relocate `framework_migration_scanning.md` and `framework_migration_version_map.md` to be referenced only from the `-plan` bundle definition, per `data-model.md` Section 6
- [X] T018 [US1] Relocate `framework_migration_rollback.md` to be referenced only from the `-execute` bundle definition, per `data-model.md` Section 6
- [X] T019 [US1] Update whatever copy/symlink mechanism produces `migration-lite`'s existing copy of `version-map.md` to source from `framework-migration-plan/references/` instead of the old `framework-migration/` path

---

## Phase 5: User Story 2 - Stage-Scoped Skill Frontmatter (Priority: P1)

**Goal**: Each bundle's frontmatter accurately declares its tool scope, matching `015`'s exposure matrix.

### Tests for User Story 2
- [X] T020 Frontmatter-parsing test: parse all six `SKILL.md` files' YAML frontmatter, assert each `compatibility.tools` list exactly matches `plan.md`'s table with zero discrepancies in `tests/mcp/test_install_bundles.py`
- [X] T021 Cross-bundle test: assert `framework-migration-preview`'s `compatibility.tools` shares no entry with any mutation tool listed in `framework-migration-clarify`'s list in `tests/mcp/test_install_bundles.py`

### Implementation for User Story 2
- [X] T022 [US2] Before writing frontmatter, confirm the final (post-`015`-review) state of `analyze_upgrade_path`/`get_steps_for_scope_tier` exposure on `gap-check`'s row against `015`'s actual shipped `contracts/015-split-migration-harness.md` — do not copy a possibly-stale matrix cell forward
- [X] T023 [US2] Add `compatibility.tools` frontmatter to all six `SKILL.md` files per `plan.md`'s table (and T022's confirmed correction, if any), across `migration_oracle/mcp/skills/framework_migration_{plan,gap_check,clarify,preview,execute,feedback}.md`

---

## Phase 6: User Story 3 - Single-Consumer References Folded Inline (Priority: P2)

**Goal**: No seventh "shared" bundle exists; single-consumer files live only inside their one consuming bundle.

### Tests for User Story 3
- [X] T024 Assert no bundle named `framework-migration-shared` (or similar) exists anywhere in install output in `tests/mcp/test_install_bundles.py`
- [X] T025 Assert `scanning.md`/`version-map.md` exist only under `framework-migration-plan/references/` and `rollback.md` only under `framework-migration-execute/references/` in `tests/mcp/test_install_bundles.py`

### Implementation for User Story 3
- [X] T026 [US3] No additional implementation task — already covered by T017/T018. This phase exists to hold T024/T025's tests, since User Story 3 in spec.md has no implementation steps beyond the relocation already performed in Phase 4.

---

## Phase 7: User Story 4 - Stage-Aware Prompt Binding (Priority: P1)

**Goal**: `start_migration`/`resume_migration` load the correct bundle for the situation, not a fixed legacy URI.

### Tests for User Story 4
- [X] T027 Assert `start_migration`'s rendered prompt text contains `skill://framework-migration-plan/main`, not `skill://framework-migration/main`, in `tests/mcp/test_prompts.py`
- [X] T028 Assert `resume_migration`, given a context with zero `outcome_counts` and `has_gap_check_flags=false`, renders a prompt loading `framework-migration-gap-check` in `tests/mcp/test_prompts.py`
- [X] T029 Assert `resume_migration`, given a context with `has_gap_check_flags=true` and all-zero completed/excluded/failed counts, renders a prompt loading `framework-migration-clarify` in `tests/mcp/test_prompts.py`
- [X] T030 Assert `resume_migration`, given a context with `outcome_counts.failed > 0`, renders a prompt loading `framework-migration-execute` in `tests/mcp/test_prompts.py`
- [X] T031 Assert `resume_migration`, given a context where all steps are accounted for (completed+excluded+failed+skipped equals total step count) and not yet closed, renders a prompt loading `framework-migration-feedback` in `tests/mcp/test_prompts.py`

### Implementation for User Story 4
- [X] T032 [US4] Update `start_migration`'s prompt text to load `skill://framework-migration-plan/main` in `migration_oracle/mcp/server.py` (or wherever prompt text is defined)
- [X] T033 [US4] Implement `resume_migration`'s stage-determination logic per `data-model.md` Section 5's decision table, including the `<total step count for context>` read noted as an open implementation detail there, in `migration_oracle/mcp/server.py`
- [X] T034 [US4] Update `resume_migration`'s prompt text to use T033's computed stage to select the loaded `skill://` URI

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T035 E2E test: fresh install -> `start_migration` loads `-plan` -> create context -> `resume_migration` at each of the four decision-table branches in sequence (zero state -> gap-check-flagged -> failed-step -> all-accounted-for) loads the correct bundle each time, in `tests/e2e/test_skill_bundle_split.py`
- [X] T036 Run quickstart.md validation end-to-end
- [X] T037 Update `SPEC_ORGANIZATION.md`'s `015` entry to Complete, noting FR-010's final disposition (resolved-with-citation per T002, or explicitly carried forward as a follow-up item) — do not mark complete with FR-010 silently unaddressed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Investigation)**: No dependencies — can start immediately. Blocks nothing else directly, but T037 cannot close out the spec until T002 records a disposition.
- **Phase 2 (get_migration_contexts extension)**: No dependency on Phase 1. BLOCKS Phase 7 (User Story 4) entirely — `resume_migration`'s decision table cannot be implemented without T003/T004.
- **Phase 3 (Bundle manifest)**: No dependency on Phase 1 or 2. BLOCKS Phase 4's bundle-writing tasks from being installable/testable, though the content files themselves (T011-T016) can be drafted in parallel with Phase 3.
- **Phase 4 (User Story 1)**: Content tasks (T011-T019) can proceed in parallel with Phase 2/3. Tests (T008-T010) require Phase 3 complete.
- **Phase 5 (User Story 2)**: Requires Phase 4's bundle files to exist (frontmatter is added to files Phase 4 creates).
- **Phase 6 (User Story 3)**: Already satisfied by Phase 4 — exists only to hold its own test tasks.
- **Phase 7 (User Story 4)**: Requires Phase 2 complete (T003/T004) before T033. Requires Phase 3 complete before T032/T034 are meaningfully testable end-to-end.
- **Phase 8 (Polish)**: Requires all prior phases complete.

### Parallel Opportunities

- T011-T016 (writing the six `SKILL.md` files) are `[P]` — independent content extractions, no shared file, per `plan.md`'s parallelism constraints.
- T003/T004 (get_migration_contexts extension) are NOT marked `[P]` relative to T033 — sequencing matters, per `plan.md`.
- T001/T002 (FR-010 investigation) are NOT parallel with anything — blocking by design, per `plan.md`.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (investigation — does not block, but should be started early since it may surface unrelated findings worth knowing about)
2. Complete Phase 3 (bundle manifest mechanism)
3. Complete Phase 4 (the six bundle content files + relocations)
4. **STOP and VALIDATE**: run T008-T010 independently — this alone fixes the original defect (cross-stage content leakage) even before Phase 5/7 ship.

### Incremental Delivery

1. Phase 1 + Phase 3 + Phase 4 -> the core defect is fixed (bundles are independent)
2. Add Phase 5 (frontmatter) -> tool-gating documentation now matches `015`'s real enforcement
3. Add Phase 2 + Phase 7 -> prompts become stage-aware, resume logic is accurate
4. Phase 6's tests confirm no regression on the "no shared bundle" requirement throughout
5. Phase 8 closes out with E2E coverage and the `SPEC_ORGANIZATION.md` update — including FR-010's honest disposition, not a silently-dropped requirement
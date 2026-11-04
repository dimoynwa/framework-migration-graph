---
description: "Task list template for feature implementation"
---

# Tasks: Migration Research Stage

**Input**: Design documents from `specs/018-migration-research-stage/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. This is a documentation/skill prose feature. No code testing tasks are required.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Project initialization and basic structure
*No setup tasks required. The target files are existing skill markdown documents.*

---

## Phase 2: User Story 1 - Checkpoint Knowledge Gathering Before Planning (Priority: P1) 🎯 MVP

**Goal**: Run an optional research stage that gathers all migration knowledge and saves it as a structured markdown artifact (`research.md`). This MUST be completed first so downstream amendments can reference the schema.

- [X] T001 [US1] Update `specs/018-migration-research-stage/data-model.md` §3.2 to change the Required column for `Before/After` to `Yes`, with the note "value may be empty string."
- [X] T002 [US1] Create the new `research.md` skill definition in `migration_oracle/mcp/skills/framework-migration/research.md`. It must implement the knowledge-query pipeline (Steps 0-4 extracted from `plan.md`) and include the standard skill frontmatter. **Note**: Adapt Step 1 (folder discovery) to check for existing `research.md` instead of `tasks.md`. Remove references to resume-at-execute, as the research stage always overwrites (as tested in T004).
- [X] T003 [US1] Add Step 5 (artifact emission) to `migration_oracle/mcp/skills/framework-migration/research.md`. **CRITICAL**: The skill file MUST NOT abbreviate the schema with a reference to `data-model.md`. It must explicitly list the complete artifact field inventory inline:
  - Header: Framework, From, To, Generated (ISO 8601), Scan checksum (SHA-256), Entity count, Rule count, Truncated.
  - Preconditions (checklist).
  - Rule Results blocks: Rule ID, Rule Type, Statement, Tier, Scope, Severity, Entity Classification, Applicability.
  - Nested under each Rule: Matched Entities (Entity Name, Deprecated In, Removed In, Replaced By, Chain Completeness).
  - Nested under each Rule: Steps (Step Type, Instruction, Before/After, Effort, Automatable, Recipe, Escalation Notes).
  - Dependency Resolutions: Service Name, Target Version, Selected Version, Selection Strategy, Status, Repo URL, Remediation Details.
  - Recipe Plan.
- [X] T004 [US1] Ensure `migration_oracle/mcp/skills/framework-migration/research.md` overwrites any existing `research.md` in the target folder without error on multiple invocations.
- [X] T005 [US1] Ensure the `compatibility.tools` frontmatter in `migration_oracle/mcp/skills/framework-migration/research.md` exactly matches the tools used in `plan.md` Steps 0-4.

**Checkpoint**: `research.md` is complete and self-contained. Plan stage amendments can now reference it safely.

---

## Phase 3: User Story 2 - Plan Consumes Valid Research Artifact (Priority: P1)

**Goal**: The plan stage detects and consumes a valid `research.md` artifact.

- [X] T006 [US2] Update `migration_oracle/mcp/skills/framework-migration/plan.md` to define the explicit SHA-256 checksum algorithm in Step 2.
  - **Anchor Before**: `## Step 2 — Codebase scan\n\nRun scan using...`
  - **Anchor After**: `These scan results are passed as...`
  - **Amendment**: Specify that the checksum is the SHA-256 hash over all entity names (FQCNs, annotations, properties, dependencies, npm packages), lexicographically sorted, deduplicated, newline-joined, UTF-8 encoded.
- [X] T007 [US2] Update `migration_oracle/mcp/skills/framework-migration/plan.md` to add Step 1.5 logic.
  - **Anchor Before**: `## Step 1 — Folder discovery\n\n...`
  - **Anchor After**: `## Step 2 — Codebase scan`
  - **Amendment**: Insert `## Step 1.5 — Detection` and the 6-branch skipping logic (absent, mismatch, parse failure, staleness, checksum mismatch, valid accept). Explicitly state: Reference the checksum algorithm defined in Step 2 (T006). The Step 1.5 prose must note that its checksum comparison runs after Step 2 completes — the document ordering places it before Step 2 for readability, but the execution order is Step 1 → Step 2 → Step 1.5 evaluation.
- [X] T008 [US2] Update `migration_oracle/mcp/skills/framework-migration/plan.md` file emission (Step 6) to instruct the agent to read inputs directly from `research.md` when skipping queries. Explicitly state: Rule-level fields (entityClassification, applicability, steps, severity, etc.) are read from `research.md`. Entity-anchor verification for render classification uses the current codebase scan from Step 2. Ensure the rule rendering still maps `BRIDGED_BY` to task instructions without a distinct render outcome.
- [X] T009 [US2] Modify the `plan.md` output template block in `migration_oracle/mcp/skills/framework-migration/plan.md`.
  - **Anchor Before**: `From to To:     {FROM} to {TO}\nGraph snapshot:`
  - **Anchor After**: `Graph snapshot: {knowledge-version id at generation time}`
  - **Amendment**: Insert `Research:` and `Research-generated:` fields. Define the inline vs artifact consumption rules for these fields. Explicitly state: When consuming a research artifact, `Research-generated:` MUST be set to the research artifact's `Generated` timestamp, not the current plan execution time. When inline, `Research-generated:` MUST be omitted entirely.

**Checkpoint**: `/migration-plan` correctly processes and consumes the `research.md` schema created in Phase 2.

---

## Phase 4: User Story 4 - Downstream Stages Verify and Display Research Provenance (Priority: P2)

**Goal**: Gap-check verifies research artifact integrity, and preview displays the knowledge source.

- [X] T010 [US4] Update `migration_oracle/mcp/skills/framework-migration/gap-check.md` to add the truncation consistency check bullet.
  - **Anchor Before**: `### Truncation` (and the following line `- Check plan.md for a truncation marker...`)
  - **Anchor After**: `` `/migration-plan` with a higher `top_n`." Severity: **HIGH**. ``
  - **Amendment**: Add a check comparing research.md truncation flag to plan.md.
- [X] T011 [US4] Update `migration_oracle/mcp/skills/framework-migration/gap-check.md` to add the provenance integrity check.
  - **Anchor Before**: `### Version sanity`
  - **Anchor After**: `the Preconditions section. Severity: **LOW**.` (without ellipsis)
  - **Amendment**: Insert `### Provenance integrity` section containing staleness and existence checks. Explicitly forbid parsing below the header.
- [X] T012 [P] [US4] Update `migration_oracle/mcp/skills/framework-migration/preview.md` to display the knowledge source.
  - **Anchor Before**: `- Relevance-Index entries: resolved (promoted or dismissed) vs. unresolved`
  - **Anchor After**: `## Risk-group rendering`
  - **Amendment**: Append `- Knowledge source: (e.g. inline queries, or research.md from <date>)` as the final bullet in the Summary Counts section.

---

## Phase 5: Polish & Cross-Cutting Concerns (Documentation)

**Purpose**: System documentation and agent instruction updates.

- [X] T013 [P] Update `docs/migration-file-state-design.md`. Update §0 file inventory to add the `research.md` line, and update §5 stage summary to add the research stage's reads/writes/graph access description.
- [X] T014 [P] Update `INSTRUCTION.md` to include `/migration-research` in the stage table, pipeline diagram, and the explicit install bundle file list.

---

## Phase 6: Verification (Strict Equivalence Testing)

**Purpose**: Guarantee the amendments do not break existing behavior.

- [X] T015 **Default-path-equivalence verification** (quickstart.md Step 1 + Step 5): Run `/migration-plan` without a prior `/migration-research` against a test project. Confirm the output is IDENTICAL to the pre-amendment `plan.md` output (same rules, same classification, same tasks), except for the `Research: inline` header.
- [X] T016 **Accelerated-path-equivalence verification** (quickstart.md Step 3 + Step 5): Run `/migration-research` then `/migration-plan`. Confirm the output matches the default path (same rules, same classification, same task order), proving the research artifact data fully satisfies plan.md's render classification.
- [X] T017 **Version-mismatch fallthrough verification** (quickstart.md Step 4): Re-run `/migration-plan` with a different target version framework. Verify that the research artifact is ignored and inline queries run.
- [X] T018 **Checksum-mismatch verification** (quickstart.md Step 6): Modify a source file to change the scan result, run `/migration-plan` without re-running research, and verify the checksum mismatch warning appears.
- [X] T019 **Downstream provenance verification** (quickstart.md Step 7): Run `/migration-gap-check` and `/migration-preview` to verify they properly display the new knowledge source lines and correctly perform truncation consistency checks.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Complete (no tasks).
- **US1 (Phase 2)**: MUST be completed first. `research.md` is a new file that acts as the data schema source of truth.
- **US2 (Phase 3)**: MUST follow US1 so it can reference the established schema.
- **US4 (Phase 4)**: Can be implemented concurrently with US2, provided US1 is complete.
- **Polish (Phase 5)**: Documentation can be done in parallel at any time. 
- **Verification (Phase 6)**: MUST follow all other implementation phases.

### Within Each User Story

- Ensure accurate markdown modification using the explicit Anchor Before/After strings provided.

### Parallel Opportunities

- T010, T011, T012 (US4 Gap Check and Preview) can be implemented in parallel across files, but T010 and T011 should be applied sequentially to `gap-check.md` to avoid anchor drift.
- T013, T014 (Documentation) can be implemented in parallel.

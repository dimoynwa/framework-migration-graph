# Tasks: Pipeline Core

**Input**: Design documents from `/specs/002-pipeline-core/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), data-model.md, contracts/002-pipeline-core.md, quickstart.md

**Tests**: Test tasks are not explicitly requested per the feature spec constraints.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create pipeline directories `runs/raw/`, `runs/nodes/`, and `runs/json/` via initialization in `migration_oracle/cli.py`
- [X] T002 Create empty `__init__.py` files for `migration_oracle/pipeline/__init__.py` and `migration_oracle/graph/queries/__init__.py` (if missing)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Implement `get_llm()` factory in `migration_oracle/pipeline/_llm.py` supporting `bedrock`, `openai`, `anthropic`, `ollama`, `litellm`, and `google` via `MODEL_PROVIDER`.
- [X] T004 Implement caching helper logic (`path.exists()` file-existence checks and six distinct skipping conditions) and `--force` flag logic in `migration_oracle/pipeline/_cache.py`.
- [X] T005 [P] Add `EXTRACTION_RATE_LIMIT_RETRIES` (default `3`) and `EXTRACTION_RETRY_BASE_DELAY` (default `2.0`) to `migration_oracle/config.py` and import them in the pipeline modules.
- [X] T006 [P] Implement `version_exists` query helper in `migration_oracle/graph/queries/pipeline.py` (Required for US1 pre-check).

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - Process Framework Changes (Priority: P1) 🎯 MVP

**Goal**: Clean, typed, graph-queryable migration rules derived from noisy change records.

**Independent Test**: Can be fully tested by running the pipeline on a known raw markdown report and validating that the output filtered markdown and entities JSON match expected structures.

### Implementation for User Story 1

- [X] T007 [US1] Implement `filter-and-group` LLM call logic using `{changes_text_markdown_table}` placeholder, markdown fence stripping, and preamble handling in `migration_oracle/pipeline/filters.py`
- [X] T008 [US1] Write artifact caching for filtered MD in `migration_oracle/pipeline/filters.py` (utilizing `_cache.py`)
- [X] T009 [US1] Add the stale-artifact console warning (if `--force-extract` set but not `--force-llm`) in `migration_oracle/pipeline/filters.py`
- [X] T010 [US1] Implement `entity-extraction` LLM call using `{framework}` and `{changes_text}` placeholders in `migration_oracle/pipeline/extractor.py`
- [X] T011 [US1] Implement the two-step structured output fallback mechanism (structured output -> plain text parsing) and validation in `migration_oracle/pipeline/extractor.py`
- [X] T012 [US1] Add the empty entity list check (fail with exit code 1) and JSON cache writing logic in `migration_oracle/pipeline/extractor.py`
- [X] T013 [US1] Implement LLM error handling (abort on malformed JSON or max retries with non-zero exit code) in `migration_oracle/pipeline/extractor.py`
- [X] T014 [US1] Register the CLI entry point `export-extract-populate-framework` and orchestration logic parsing `--framework`, positional arguments, `--force-*`, and `--output-*` path overrides in `migration_oracle/cli.py`
- [X] T015 [US1] Implement the `--skip-existing` pre-check logic (requiring raw MD, filtered MD, and Version graph node to exist) as the very first operation in `migration_oracle/cli.py` after `runs/` directory creation, before the extractor registry is called.

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Idempotent Graph Population (Priority: P1)

**Goal**: The pipeline writes extraction outputs to the graph idempotently so that running the pipeline multiple times does not create duplicate nodes or edges.

**Independent Test**: Can be tested by running the graph populator twice with the same entities JSON and verifying node/edge counts remain identical.

### Implementation for User Story 2

- [X] T016 [US2] Define the `SOURCE_SECTION_TO_RULE_TYPE` constant dictionary mapping in `migration_oracle/pipeline/populator.py`
- [X] T017 [US2] Implement idempotent `Version` node `MERGE` query on `(framework, version)` writing `sortableVersion` at population start in `migration_oracle/graph/queries/pipeline.py`.
- [X] T018a [US2] Write `MigrationRule` node and capture its elementId in `migration_oracle/pipeline/populator.py`.
- [X] T018b [US2] Implement graph writes for `MigrationStep` (using the captured elementId as `ruleId`), `BreakingScope`, and `AffectedEntity` nodes via `migration_oracle/pipeline/populator.py`.
- [X] T019 [US2] After all `MigrationStep` nodes for a rule are written, derive and write `REQUIRES` edges by resolving the `requires[]` index list to stepIndex node pairs in `migration_oracle/pipeline/populator.py`.
- [X] T020 [US2] Derive and write lifecycle edges (`REMOVED_IN`/`REMOVES` for `removed` entities; `INTRODUCED_IN`/`INTRODUCES` for `replacement` entities; `DEPRECATED_IN`/`DEPRECATES` for deprecation entities) during entity population in `migration_oracle/pipeline/populator.py`. If both deprecation and removal apply, removal wins.
- [X] T021 [US2] Implement `REPLACED_BY` cross-product edge derivation between `removed` and `replacement` roles in `migration_oracle/pipeline/populator.py`.
- [X] T022 [US2] Implement `entityClassification` derivation logic (`actionable`/`incomplete`/`informational` based on `steps` and `entities` length) in `migration_oracle/pipeline/populator.py`.
- [X] T023 [US2] Write step-level `AUTOMATED_BY` edge stub (matching the full schema: `auto=false`, `confidence=0.0`, `method='deterministic'`, `missingRequiredParams=[]`) for each step where `automatable=true` in `migration_oracle/pipeline/populator.py`. The `MERGE` must include a `WHERE e.verifiedBy IS NULL` guard so that edges with `verifiedBy` set are never overwritten by re-runs.
- [X] T024 [US2] For each step where `step_type` is `remove`, `replace`, or `rename`, write step-level `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, or `AFFECTS_DEPENDENCY` edges with the `role` property in `migration_oracle/pipeline/populator.py`. Depends on T018b (step nodes + `REQUIRES_STEP` edges written).
- [X] T025 [US2] Implement `upsert_version_artifact_paths` query to write `rawMdPath`, `filteredMdPath`, and `entitiesJsonPath` only after all writes succeed in `migration_oracle/graph/queries/pipeline.py`.
- [X] T026 [US2] Ensure all graph sessions are initialized via `migration_oracle.graph.driver` within `migration_oracle/pipeline/populator.py`.
- [X] T027 [US2] Write an end-to-end idempotency test: run the graph populator twice with the same `MigrationEntitiesBatch` fixture and assert that node counts for `MigrationRule`, `MigrationStep`, `BreakingScope`, `Class`, `ApplicationProperty`, and `Dependency`, and edge counts for `REQUIRES_STEP`, `REQUIRES`, `HAS_SCOPE`, `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, `AFFECTS_DEPENDENCY`, `REPLACED_BY`, `REMOVED_IN`, and `INTRODUCED_IN` are identical before and after the second run.
- [X] T028 [P] [US2] Implement pipeline query helper `list_pipeline_runs` (using `OPTIONAL MATCH` compatibility) in `migration_oracle/graph/queries/pipeline.py`.

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Dry Run & Artifact Caching (Priority: P2)

**Goal**: Rely on cached LLM responses when re-running unless explicitly forced, and allow dry-running the pipeline to inspect artifacts before modifying the graph.

**Independent Test**: Run with `--dry-run` and verify artifacts are created but graph is untouched. Run again without `--force` and verify artifacts are reused.

### Implementation for User Story 3

- [X] T029 [US3] Wire `--dry-run` CLI flag handling to bypass all graph write functions in `migration_oracle/cli.py` and `migration_oracle/pipeline/populator.py`. Depends on T017, T018a, and T018b.

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T030 [P] Run `quickstart.md` validation by verifying the CLI command examples locally from `specs/002-pipeline-core/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories. (T006 explicitly blocks T015 in US1).
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - Integrates heavily with artifacts generated by US1.
- **User Story 3 (P2)**: Can start after US1 & US2, acts as a toggle boundary for US2 writes.

### Within Each User Story

- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 2

```bash
# Launch queries module and populator logic concurrently
Task: "Implement idempotent Version node MERGE query... in migration_oracle/graph/queries/pipeline.py"
Task: "Define the SOURCE_SECTION_TO_RULE_TYPE constant dictionary mapping in migration_oracle/pipeline/populator.py"
```

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
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (CLI & Core Orchestration)
   - Developer B: User Story 2 (Graph Population)
3. Stories complete and integrate independently

---
description: "Task list template for feature implementation"
---

# Tasks: Framework HTTP Extractors

**Input**: Design documents from `/specs/003-framework-http-extractors/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: The examples below include test tasks. Tests are OPTIONAL - only include them if explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `migration_oracle/`, `tests/` at repository root

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create `migration_oracle/pipeline/extractors/` directory, empty `__init__.py` placeholder; create `tests/extractors/` directory with empty `conftest.py`; create documentation directory `specs/003-framework-http-extractors/`
- [x] T002 Create `contracts/003-framework-http-extractors.md` defining the six boundary rules: (1) `extract()` is the only public interface, (2) `cli.py`/`filters.py` call only `get_extractor().extract()`, (3) no circular imports to `filters.py`/`extractor.py`, (4) no filesystem or Neo4j writes from extractors, (5) HTTP client instantiated in `base.py` only, (6) `DocumentedChange` imported from `models/`, never redefined
- [x] T003 Update `DocumentedChange` in `migration_oracle/models/entities.py` to add `metadata: dict | None = None`
- [x] T004 Create `ExtractionResult` model in `migration_oracle/models/entities.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Implement abstract `BaseExtractor` and shared HTTP factory in `migration_oracle/pipeline/extractors/base.py`
  - [x] T006 Implement config env var reading (`GITHUB_TOKEN`, `SSL_VERIFY`, `JIRA_MAX_CONCURRENT`, `REDHAT_DOCS_DELAY_SEC`) in `BaseExtractor.__init__`
- [x] T007 Implement extractor registry skeleton in `migration_oracle/pipeline/extractors/__init__.py` with all 9 keys registered to stub `NotImplementedError` classes
- [x] T008 [P] Create `test_registry.py` in `tests/extractors/`
- [x] T009 [P] Create `test_jakarta_ee.py` in `tests/extractors/`
- [x] T010 [P] Implement Jakarta EE extractor in `migration_oracle/pipeline/extractors/jakarta_ee.py` (self-contained, zero external dependencies) and replace its stub in `__init__.py`

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Extract Spring Boot and Angular Changes (Priority: P1) 🎯 MVP

**Goal**: Extract framework changes for Spring Boot and Angular

**Independent Test**: Can be fully tested by running the extraction for spring-boot or angular and verifying the output change objects for a given version range.

### Tests for User Story 1

- [x] T011 [P] [US1] Create `test_spring_boot.py` in `tests/extractors/`
- [x] T012 [P] [US1] Create `test_angular.py` in `tests/extractors/`

### Implementation for User Story 1

- [x] T013 [P] [US1] Implement Spring Boot extractor in `migration_oracle/pipeline/extractors/spring_boot.py` and replace its stub in `__init__.py`
- [x] T014 [P] [US1] Implement Angular extractor in `migration_oracle/pipeline/extractors/angular.py` and replace its stub in `__init__.py`

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Extract WildFly, EAP, and Hibernate Changes (Priority: P2)

**Goal**: Extract framework changes for WildFly, EAP, and Hibernate

**Independent Test**: Can be fully tested by running the extraction for wildfly, eap, or hibernate and verifying the output change objects.

### Tests for User Story 2

- [x] T015 [P] [US2] Create `test_wildfly.py` in `tests/extractors/`
- [x] T016 [P] [US2] Create `test_wildfly_jira.py` in `tests/extractors/` (test Jira enrichment in isolation with mocked HTTP)
- [x] T017 [P] [US2] Create `test_eap.py` in `tests/extractors/`
- [x] T018 [P] [US2] Create `test_hibernate.py` in `tests/extractors/`

### Implementation for User Story 2

- [x] T019 [P] [US2] Implement WildFly extractor in `migration_oracle/pipeline/extractors/wildfly.py` and replace its stub in `__init__.py`
  - [x] T019a [US2] Implement Jira enrichment sub-task (steps 3a–3d) within `wildfly.py` (Depends on T019: base WildFly extractor structure must exist first)
- [x] T020 [P] [US2] Implement EAP extractor in `migration_oracle/pipeline/extractors/eap.py` and replace its stub in `__init__.py`
- [x] T021 [P] [US2] Implement Hibernate extractor in `migration_oracle/pipeline/extractors/hibernate.py` and replace its stub in `__init__.py`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Extract Jakarta EE and Stub Extractors (Priority: P3)

**Goal**: Extract framework changes for Jakarta EE and handle stub extractors

**Independent Test**: Can be fully tested by running the extraction for jakarta-ee or stub extractors and verifying the output change objects or expected errors.

### Tests for User Story 3

- [x] T022 [P] [US3] Create `test_resteasy.py` in `tests/extractors/`
- [x] T023 [P] [US3] Create `test_infinispan.py` in `tests/extractors/`
- [x] T024 [P] [US3] Create `test_elytron.py` in `tests/extractors/`

### Implementation for User Story 3

- [x] T025 [P] [US3] Implement RestEasy stub extractor in `migration_oracle/pipeline/extractors/resteasy.py` and replace its stub in `__init__.py`
- [x] T026 [P] [US3] Implement Infinispan stub extractor in `migration_oracle/pipeline/extractors/infinispan.py` and replace its stub in `__init__.py`
- [x] T027 [P] [US3] Implement Elytron stub extractor in `migration_oracle/pipeline/extractors/elytron.py` and replace its stub in `__init__.py`

**Checkpoint**: Registry is complete — all 9 keys are registered. Stub extractors raise `NotImplementedError` with messages naming the extractor and referencing `export-extract-populate-framework-pipeline.md`. Verified by T022, T023, T024 passing.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T028 Code cleanup and refactoring
- [x] T029 Run quickstart.md validation
- [x] T030 End-to-end smoke test: run `uv run python -m migration_oracle.cli export-extract-populate-framework --framework spring-boot 3.3.0 3.4.0 --dry-run` and verify `runs/raw/` contains expected Markdown

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - No dependencies on other stories

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Extractors within a story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Create test_spring_boot.py in tests/extractors/"
Task: "Create test_angular.py in tests/extractors/"

# Launch all extractors for User Story 1 together:
Task: "Implement Spring Boot extractor in migration_oracle/pipeline/extractors/spring_boot.py"
Task: "Implement Angular extractor in migration_oracle/pipeline/extractors/angular.py"
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
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

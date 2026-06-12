# Tasks: MCP Defect Fixes — Migration Session Hardening

**Input**: Design documents from `/specs/010-mcp-defect-fixes/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Included — SC-009 requires unit test coverage for all Cypher changes introduced by this spec.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no open dependencies)
- **[Story]**: Which user story this task belongs to (US1–US9, matching spec.md)
- Include exact file paths in every description

---

## Phase 1: Foundational (Blocking Prerequisite)

**Purpose**: Rename the normalisation helper from `_to_minor_zero` to `to_minor_zero` in `upgrade.py`. This is a prerequisite for the cross-module import in US1 (`context.py`) and for the new tool in US2 (`check_version_availability`). No other work can start until this is done.

**⚠️ CRITICAL**: All user story phases depend on this phase completing cleanly.

- [ ] T001 Rename `_to_minor_zero` → `to_minor_zero` in `migration_oracle/mcp/tools/upgrade.py`: update the function definition (line ~9) and both internal call sites inside `analyze_upgrade_path` and `build_recipe_plan` in the same file

**Checkpoint**: Run `grep -rn "_to_minor_zero" migration_oracle/` — must return zero matches before proceeding to any Phase 2+ task.

---

## Phase 2: User Story 1 — Agent Completes a Migration Session with Patch Versions (Priority: P1) 🎯 MVP

**Goal**: `create_migration_context` normalises `from_version`/`to_version` to `major.minor.0` form before every graph lookup, handles missing Version nodes with a live hint derived from the graph, and cleans up zombie `MigrationContext` nodes on failure.

**Independent Test**: Call `create_migration_context(from_version="3.5.12", to_version="4.1.0")` with mocked `context_queries`; assert the mock receives `from_version="3.5.0"` — the string `"3.5.12"` must never reach the graph query layer.

### Tests for User Story 1

- [ ] T002 [P] [US1] Create `tests/mcp/test_context_fixes.py` with US1 test cases: `test_normalises_patch_version` (mock `context_queries.create_or_get_context`, assert called with `from_version="3.5.0"`), `test_version_not_in_graph` (mock returns `None` path, assert structured error with hint), `test_zombie_cleanup_on_version_miss` (mock `context_queries.delete_zombie_context`, assert it is called with `from_version="3.5.0"`); see plan.md §Test Mock State for full mock-state table

### Implementation for User Story 1

- [ ] T003 [P] [US1] Add `_DELETE_ZOMBIE_CONTEXT` Cypher constant (`MATCH (ctx:MigrationContext {…}) WHERE NOT (ctx)-[:UPGRADES_FROM]->() DELETE ctx`) and `_GET_AVAILABLE_VERSIONS` Cypher constant to `migration_oracle/mcp/graph/queries/context.py`; see plan.md §FR-001/FR-003 for exact Cypher
- [ ] T004 [P] [US1] Import `to_minor_zero` from `migration_oracle.mcp.tools.upgrade` in `migration_oracle/mcp/tools/context.py`; apply `to_minor_zero(from_version)` and `to_minor_zero(to_version)` on the tool-layer inputs before calling `context_queries.create_or_get_context`
- [ ] T005 [US1] Implement the `record is None` branch in `migration_oracle/mcp/graph/queries/context.py`: run `_DELETE_ZOMBIE_CONTEXT` (structural WHERE guard makes it unconditionally safe — do NOT read `_was_created` from the `None` record), run `_GET_AVAILABLE_VERSIONS` for the hint, raise `VersionNotInGraphError`; see plan.md §FR-003 pseudocode (depends on T003)

**Checkpoint**: `test_normalises_patch_version`, `test_version_not_in_graph`, and `test_zombie_cleanup_on_version_miss` all pass; SC-001 satisfied.

---

## Phase 3: User Story 6 — Resolver Does Not Leak OAuth Credentials (Priority: P1)

**Goal**: `_build_error()` scrubs all `oauth2:[^@]+@` and `https?://[^:]+:[^@]+@` credential patterns from exception messages before populating the `message` field. This is the sole scrub point per `contracts/credential_scrub.md`.

**Independent Test**: `_build_error(message="oauth2:TOKEN@gitlab.example.com/repo")` must return a dict whose `message` contains `<redacted>@` and no occurrence of `TOKEN`.

### Tests for User Story 6

- [ ] T006 [P] [US6] Create `tests/paysafe/test_resolver_credential_scrub.py` with US6 tests: `test_scrubs_oauth2_token`, `test_scrubs_basic_auth`, `test_clean_message_unchanged`; see plan.md §Test Mock State for exact inputs and expected outputs

### Implementation for User Story 6

- [ ] T007 [P] [US6] Add `import re`, `_CRED_RE = re.compile(r'https?://[^:@/\s]+:[^@\s]+@|oauth2:[^@\s]+@')`, and `def _scrub(s: str) -> str: return _CRED_RE.sub('<redacted>@', s)` at module level in `migration_oracle/paysafe/resolver.py`; apply `message = _scrub(message)` as the first statement inside `_build_error()` before any other use of `message`

**Checkpoint**: All three credential-scrub tests pass; SC-002 satisfied.

---

## Phase 4: User Story 2 — Agent Checks Whether a Target Version Exists Before Starting (Priority: P1)

**Goal**: New `check_version_availability` tool returns `{status, exists_in_graph, ga_available, latest_patch, hint}` for any supported framework/version; handles Maven Central probe failures without raising an exception.

**Independent Test**: Call `check_version_availability("spring-boot", "4.1.0")` with mocked graph session and `requests.get`; verify all four data fields are returned. Call for an unsupported framework; verify no `requests.get` call is made and the error shape matches `data-model.md` §check_version_availability.

### Tests for User Story 2

- [ ] T026 [P] [US2] Create `tests/mcp/test_check_version_availability.py` with: `test_returns_all_fields_for_known_version` (use `unittest.mock.patch` to mock graph session returning `found=True` and `requests.get` returning `{"response": {"numFound": 1, "docs": [{"v": "4.1.2"}]}}`; assert all four data fields present), `test_exists_in_graph_false_for_missing_version` (mock graph returning `found=False`; assert `exists_in_graph=False`), `test_unsupported_framework_returns_error_no_network_call` (call with `framework="unknown"`; assert `requests.get` never called, `status="error"`, `error_code="unsupported_framework"`), `test_maven_central_unavailable_returns_graceful_response` (patch `requests.get` to raise `ConnectionError`; assert return value has `ga_available=False`, `latest_patch=None`, `hint` contains "Maven Central unavailable", and NO exception is raised)

### Implementation for User Story 2

- [ ] T008 [P] [US2] Add `_CHECK_VERSION_IN_GRAPH` Cypher constant (`MATCH (v:Version {framework: $framework, version: $version}) RETURN count(v) > 0 AS found`) to `migration_oracle/mcp/graph/queries/upgrade.py`
- [ ] T009 [P] [US2] Add `_FRAMEWORK_MAVEN_COORDS = {"spring-boot": ("org.springframework.boot", "spring-boot")}` lookup table and `check_version_availability` function skeleton decorated with `@mcp.tool()` in `migration_oracle/mcp/tools/upgrade.py`; step 1: normalise via `to_minor_zero(version)`; step 2: return unsupported-framework error shape (`status: "error", error_code: "unsupported_framework"`, no network call) for unknown framework keys; see plan.md §FR-015/FR-017
- [ ] T010 [US2] Implement `check_version_availability` body steps 3–6 in `migration_oracle/mcp/tools/upgrade.py`: graph read via `_CHECK_VERSION_IN_GRAPH` (step 3); Maven Central GA probe `requests.get(…, timeout=10)` with `numFound >= 1` check (step 4–5); latest-patch query with `sort=version+desc` (step 6); wrap the entire network section in `except Exception` returning `{ga_available: False, latest_patch: None, hint: "Maven Central unavailable — could not verify GA status"}` per FR-020 — MUST NOT raise (depends on T008, T009, T026)

**Checkpoint**: All four `test_check_version_availability.py` tests pass; probe-failure path returns `ga_available=False` without raising; SC-005 satisfied. Additionally confirm `check_version_availability` appears in the MCP server's tool manifest — FastMCP auto-registers `@mcp.tool()` functions when the module is imported, so no manual registration entry is needed, but verify `upgrade.py` is loaded by the server's entry point and the tool name is visible in `mcp.list_tools()` output.

---

## Phase 5: User Story 3 — Agent Skips Irrelevant Recipe Steps (Priority: P2)

**Goal**: Every entry in `build_recipe_plan`'s `manual_track` carries `applicability` (`"applicable"` | `"not_applicable"` | `"unknown"`) and `matched_entities`. Dedup runs before applicability scoring; first occurrence of each `step_id` wins.

**Independent Test**: Call `build_recipe_plan` with `user_entities=["com.example.Foo"]` against a mock that returns one matching row and one non-matching row; verify matching row has `applicability: "applicable"` and non-matching row has `applicability: "not_applicable"`. Call with `user_entities=[]`; verify all steps have `applicability: "unknown"`.

### Tests for User Story 3

- [ ] T011 [P] [US3] Create `tests/mcp/test_recipe_applicability.py` with US3 tests: `test_applicable_steps`, `test_not_applicable_steps`, `test_unknown_when_empty_entities`, `test_dedup_first_occurrence_wins`; see plan.md §Test Mock State for full mock-input/expected-output table

### Implementation for User Story 3

- [ ] T012 [P] [US3] Extend `_BUILD_RECIPE_PLAN` Cypher in `migration_oracle/mcp/graph/queries/upgrade.py` with `OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ae)` and `collect(DISTINCT ae.name) AS all_affected_entities` returned per row; see plan.md §FR-010/FR-011 (parallel-safe with T008 — T008 adds a new top-level constant; T012 modifies the existing `_BUILD_RECIPE_PLAN` string; they target different sections of the file, but verify no merge conflict before editing)
- [ ] T013 [US3] Implement dedup-first-then-applicability row-processing loop in `migration_oracle/mcp/tools/upgrade.py` `build_recipe_plan`: initialise `seen_step_ids: set[str]` and `user_ents_lower`; gate 1 (skip duplicate `step_id`); gate 2 (four-rule applicability evaluation in order: empty user_ents → unknown, empty all_affected → unknown, intersection non-empty → applicable, otherwise → not_applicable); append `applicability` and `matched_entities` to each output dict; see plan.md §FR-012 pseudocode (depends on T012)

**Checkpoint**: All four `test_recipe_applicability.py` tests pass; SC-003 satisfied.

---

## Phase 6: User Story 4 — Agent Records Why a Step Was Skipped (Priority: P2)

**Goal**: `update_step_status` with a non-empty `reason` persists the note to `ctx.stepNotes` (Neo4j map property) via Python-side read-merge-write. No APOC. Calling without `reason` is a no-op for the notes map.

**Independent Test**: Call `update_step_status(context_id, step_id, status="skipped", reason="already handled")`; verify `context_queries.record_step_outcome` mock receives `reason="already handled"`. Call without `reason`; verify `stepNotes` mock is not written.

### Tests for User Story 4

- [ ] T014 [P] [US4] Add `test_stepnotes_persisted` and `test_no_entry_without_reason` to `tests/mcp/test_context_fixes.py`; mock both the stepNotes read query (returning `{}`) and the write query; assert write query is called only when `reason` is non-empty

### Implementation for User Story 4

- [ ] T015 [US4] Remove `del reason` from `update_step_status` in `migration_oracle/mcp/tools/context.py`; pass `reason` through to `context_queries.record_step_outcome` as a keyword argument
- [ ] T016 [US4] Implement stepNotes read-merge-write in `migration_oracle/mcp/graph/queries/context.py` `record_step_outcome`: add a preparatory `MATCH … RETURN coalesce(ctx.stepNotes, {}) AS m` read; in Python `merged = {**current_map, step_id: reason}`; add `SET ctx.stepNotes = $merged` write; guard with `if reason` so empty/absent reason is a no-op; **both the read query and the write query MUST be issued on the same `write_session()` session** — open the session once, run the read, merge in Python, run the write, then close; do not open a separate session between the two queries (research.md Spike 2: "the read and write should occur in the same logical operation to minimise the race window"); see plan.md §FR-005 and data-model.md §3 pseudocode (depends on T015)

**Checkpoint**: `test_stepnotes_persisted` passes; `stepNotes` write query is not called when `reason` is absent.

---

## Phase 7: User Story 5 — Agent Sees All Steps Including Those Without a Scope Tag (Priority: P2)

**Goal**: `get_steps_for_scope_tier` returns scopeless `MigrationStep` records with `scope: null` instead of silently dropping them. The OPTIONAL MATCH predicate bug is fixed at the Cypher level.

**Independent Test**: Mock `get_steps_for_scope_tier` returning a row with `scope=None`; verify the step appears in the tool response with `scope: null`.

### Tests for User Story 5

- [ ] T017 [P] [US5] Add `test_scope_tier_returns_scopeless_steps` to `tests/mcp/test_context_fixes.py`; mock returns one row with `scope=None`; assert the row appears in the output

### Implementation for User Story 5

- [ ] T018 [US5] Remove the `WHERE bs.scope = $scope` predicate from the `OPTIONAL MATCH` in `_GET_STEPS_FOR_SCOPE_TIER` in `migration_oracle/mcp/graph/queries/context.py`; change `row.get("scope") or ""` → `row.get("scope")` in `migration_oracle/mcp/tools/context.py` to allow `null` scope values to propagate; see plan.md §FR-006 (depends on T016 — both patch `context.py`; verify no conflict before editing)

**Checkpoint**: `test_scope_tier_returns_scopeless_steps` passes; SC-006 satisfied.

---

## Phase 8: User Story 7 — Resolver Falls Back to Artifactory When GitLab Is Unavailable (Priority: P2)

**Goal**: When `_GitError("git_ls_remote_failed")` is raised and `ARTIFACTORY_BASE_URL` env var is set, `resolver.py` silently retries via Artifactory `GET …/api/search/latestVersion?a={service_name}` (anonymous read, no `Authorization` header). The caller receives the same result shape regardless of which backend succeeded. When `ARTIFACTORY_BASE_URL` is absent, the original error is returned without any Artifactory call.

**Independent Test**: Mock `_GitError` + set `ARTIFACTORY_BASE_URL` + mock `requests.get` returning `"2.3.1"`; verify `resolve()` returns `status="ok"`. Unset `ARTIFACTORY_BASE_URL`; verify `resolve()` returns `status="error"` immediately.

### Tests for User Story 7

- [ ] T019 [P] [US7] Add `test_artifactory_fallback_called` and `test_no_fallback_without_env_var` to `tests/paysafe/test_resolver_credential_scrub.py`; for `test_artifactory_fallback_called`: use `unittest.mock.patch.dict(os.environ, {"ARTIFACTORY_BASE_URL": "https://art.example.com"})` to set the env var and `unittest.mock.patch('requests.get', return_value=Mock(ok=True, text='2.3.1'))` to mock the HTTP call — no live Artifactory instance; assert `requests.get` is called with a URL containing `a=` and that no `Authorization` keyword argument is passed to `requests.get`; for `test_no_fallback_without_env_var`: ensure `ARTIFACTORY_BASE_URL` is absent from env and assert `requests.get` is never called

### Implementation for User Story 7

- [ ] T020 [US7] Add Artifactory fallback block inside `except _GitError as exc:` in `migration_oracle/paysafe/resolver.py`: read `os.environ.get("ARTIFACTORY_BASE_URL", "").rstrip("/")`; if absent, fall through to existing `_build_error` call; if present, call `requests.get(f"{base}/api/search/latestVersion?a={service_name}", timeout=10)` — no `Authorization` header; handle double-failure with structured `_build_error` call; see plan.md §FR-008/FR-009 including the `repos=` implementer note (depends on T007 — both patch `resolver.py`)

**Checkpoint**: Both `test_artifactory_fallback_called` and `test_no_fallback_without_env_var` pass; no `Authorization` header appears in the Artifactory request mock.

---

## Phase 9: User Story 8 — Agent Filters Recipes to Composite-Only or No-Param Subsets (Priority: P2)

**Goal**: `search_openrewrite_recipes` applies `only_composite` and `require_no_params` at the Cypher WHERE clause. The deferred `if only_composite is not None or require_no_params: pass` comment block is removed. Post-hoc Python filtering is not permitted.

**Independent Test**: Call with `only_composite=True`; verify the Cypher call mock receives `only_composite=True`. Confirm the deferred `pass` block is absent from `tools/search.py`.

### Tests for User Story 8

- [ ] T030 [P] [US8] Create `tests/mcp/test_openrewrite_filters.py` with: `test_only_composite_filter_applied` (mock `hydrate_openrewrite_recipes`; call `search_openrewrite_recipes(query="…", only_composite=True)`; assert mock receives `only_composite=True` and that the Cypher parameter reaches the query layer — not filtered post-hoc in Python), `test_require_no_params_filter_applied` (mock returns no recipes that have a `required=True` RecipeParam row; assert result is empty rather than containing those entries), `test_both_filters_combined` (both `only_composite=True` and `require_no_params=True` passed; assert mock receives both parameters simultaneously); use `unittest.mock.patch` for all calls to `hydrate_openrewrite_recipes`

### Implementation for User Story 8

- [ ] T021 [P] [US8] Extend `hydrate_openrewrite_recipes` in `migration_oracle/mcp/graph/queries/search.py` to accept `only_composite: bool | None = None` and `require_no_params: bool = False`; add `AND (NOT $only_composite OR r.composite = true)` and `AND (NOT $require_no_params OR NOT EXISTS { MATCH (r)-[:HAS_PARAM]->(p:RecipeParam) WHERE p.required = true })` to the WHERE clause; see plan.md §FR-013/FR-014
- [ ] T022 [P] [US8] Pass `only_composite` and `require_no_params` from `search_openrewrite_recipes` in `migration_oracle/mcp/tools/search.py` through to `hydrate_openrewrite_recipes`; remove the deferred `if only_composite is not None or require_no_params: pass` block (lines 204–206 per plan.md)

**Checkpoint**: All three `test_openrewrite_filters.py` tests pass; calling with either filter produces a Cypher call that includes the corresponding WHERE clause; SC-004 satisfied.

---

## Phase 10: User Story 9 — Migration Skill Continues When Context Creation Fails (Priority: P2)

**Goal**: `framework_migration_main.md` gains an explicit STATELESS FALLBACK block inserted after Loop I step 6 and before the `## Loop II` header. The block instructs agents to continue with `analyze_upgrade_path` and `build_recipe_plan`, skip context-dependent tools, track step state in agent context only, and call `submit_migration_insight` for every high-confidence finding without a `context_id`. No `grep -P` is used in the new block.

**Independent Test**: `grep -n "STATELESS FALLBACK" migration_oracle/mcp/skills/framework_migration_main.md` returns exactly one match; the match appears before the line that contains `## Loop II`; `grep -n "grep -P" migration_oracle/mcp/skills/framework_migration_main.md` returns zero matches.

### Implementation for User Story 9

- [ ] T023 [US9] Insert the STATELESS FALLBACK block in `migration_oracle/mcp/skills/framework_migration_main.md`: locate the exact Loop I step 6 line (`Call create_migration_context`) and the `## Loop II — Scope-gated query` header; insert the six-step fallback block (trigger, instructions 1–6) from plan.md §FR-021 between those two lines; do NOT alter any existing Loop I–IV text outside the insertion point
- [ ] T027 [P] [US9] Verify `grep -E` compliance in `migration_oracle/mcp/skills/framework_migration_main.md`: run `grep -n "grep -P" migration_oracle/mcp/skills/framework_migration_main.md` — must return zero matches; if any `grep -P` appears in the inserted block, replace with `grep -E` equivalent; no changes to any other skill file (`framework_migration_scanning.md`, `framework_migration_plan_format.md`, `framework_migration_version_map.md`) (depends on T023)
- [ ] T028 [P] [US9] Verify `submit_migration_insight` mandate in the inserted block: run `grep -n "submit_migration_insight" migration_oracle/mcp/skills/framework_migration_main.md` — must return at least one match inside the STATELESS FALLBACK section; confirm the instruction explicitly states the call is made without a `context_id` argument (depends on T023)

**Checkpoint**: `grep -c "STATELESS FALLBACK" …/framework_migration_main.md` returns `1`; T027 grep check returns zero for `grep -P`; T028 grep check confirms `submit_migration_insight` with no `context_id`; SC-007 and SC-008 satisfied.

---

## Phase 11: Polish & Cross-Cutting Concerns

- [ ] T029 Write E2E chain test `test_patch_version_full_chain` in `tests/mcp/test_context_fixes.py`: mock `context_queries.create_or_get_context` to return a valid context dict when called with `from_version="3.5.0"` (not `"3.5.12"`); mock `context_queries.get_steps_for_scope_tier` to return a non-empty list of step dicts; call `create_migration_context(from_version="3.5.12", to_version="4.1.0")` and capture the returned `context_id`; then call `get_steps_for_scope_tier(context_id=context_id, scope="API", tier="mandatory")`; assert (1) `create_or_get_context` was called with `from_version="3.5.0"`, (2) a valid `context_id` string was returned, (3) `get_steps_for_scope_tier` returned a non-empty list — this validates the end-to-end fix chain: version normalisation feeds into context creation which feeds into step retrieval
- [ ] T024 Run `pytest tests/mcp/test_context_fixes.py tests/mcp/test_recipe_applicability.py tests/mcp/test_check_version_availability.py tests/mcp/test_openrewrite_filters.py tests/paysafe/test_resolver_credential_scrub.py -v` and verify all five new test files pass with zero failures or errors (depends on T029 — T029 adds a test to `test_context_fixes.py` which must be written before this final run)
- [ ] T025 [P] Verify the to_minor_zero rename is complete: `grep -rn "_to_minor_zero" migration_oracle/ tests/` must return empty output

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **P1 Phases (2–4)**: All depend on Phase 1; Phases 2, 3, and 4 are independent of each other and can proceed in parallel after T001
- **P2 Phases (5–10)**: All depend on Phase 1; can start independently after Phase 1 with the intra-file ordering noted below
- **Polish (Phase 11)**: Depends on all implementation phases complete

### Intra-File Sequencing (cross-phase)

| File | Sequential order |
|---|---|
| `migration_oracle/mcp/graph/queries/context.py` | US1 (T003/T005) → US4 (T016) → US5 (T018) |
| `migration_oracle/mcp/tools/context.py` | US1 (T004) → US4 (T015) → US5 (T018) |
| `migration_oracle/paysafe/resolver.py` | US6 (T007) → US7 (T020) |
| `migration_oracle/mcp/tools/upgrade.py` | Phase 1 (T001) → US2 (T009/T010) / US3 (T013) — US2 and US3 touch different functions and can proceed in parallel |
| `migration_oracle/mcp/graph/queries/upgrade.py` | T008 (new `_CHECK_VERSION_IN_GRAPH` constant) + T012 (extend `_BUILD_RECIPE_PLAN`) — additive changes to different sections of the file; run sequentially or verify no conflict if running in parallel |

### Parallel Opportunities (after T001)

- T002, T003, T004 (US1 tests, Cypher constants, tool-layer import) start in parallel
- T006, T007 (US6) run in parallel with the US1 group — different file
- T008, T009, T026 (US2 Cypher, tool skeleton, test file) run in parallel with US1 and US6 — different files
- T011, T012 (US3 tests, Cypher extension) run in parallel with Phases 2–4
- T017 (US5 test), T019 (US7 test), T021/T022/T030 (US8 implementation + tests) run in parallel
- T027, T028 (US9 grep and submit_migration_insight verification) run in parallel after T023

---

## Parallel Example: P1 User Stories (Phases 2–4)

```
# After T001 completes — launch these three streams concurrently:

Stream A (US1):    T002 → T003 → T004 → T005
Stream B (US6):    T006 → T007
Stream C (US2):    T026 + T008 + T009 → T010
```

---

## Implementation Strategy

### MVP First (P1 Stories Only)

1. Complete Phase 1: Foundational (T001)
2. Complete Phases 2, 3, 4 in parallel: US1 + US6 + US2
3. **STOP and VALIDATE**: P1 tests pass — SC-001, SC-002, SC-005 satisfied
4. Deploy or demo against a real graph instance

### Incremental Delivery (P1 → P2 in priority order)

1. T001 → Foundation ready
2. Phases 2–4 in parallel → All P1 defects fixed
3. Phase 5 (US3) → SC-003 satisfied (applicability noise eliminated)
4. Phase 6 (US4) → Audit trail for skipped steps
5. Phase 7 (US5) → SC-006 satisfied (scopeless steps no longer dropped)
6. Phase 8 (US7) → Resolver Artifactory fallback coverage
7. Phase 9 (US8) → SC-004 satisfied (recipe filters applied at query time)
8. Phase 10 (US9) → SC-007, SC-008 satisfied (skill stateless path documented)
9. Phase 11 → Full test suite green

---

## Notes

- `[P]` tasks touch different files and have no open dependencies — safe to run concurrently
- `[Story]` labels map tasks to spec.md acceptance scenarios for traceability
- **Key invariant**: `"3.5.12"` must NEVER reach the graph query layer; T002 enforces this
- **No `grep -P`** in any new shell snippets — use `grep -E` (macOS BSD grep / FR-022); T027 verifies compliance post-insertion
- **No APOC**: `stepNotes` uses Python-side map-merge only (Spike 3, research.md)
- **Zombie cleanup**: structural WHERE guard (`WHERE NOT (ctx)-[:UPGRADES_FROM]->()`) — never read `_was_created` from a `None` record (plan.md §FR-003)
- **Credential scrub**: `_build_error()` is the only scrub point per `contracts/credential_scrub.md` — raw exception strings must not bypass it
- **Test strategy (accepted deviation)**: All tests use `unittest.mock.patch` — no live Neo4j or live Artifactory instance is required. This is an explicit design decision from plan.md §Testing. All Cypher changes are paired with mock-based test tasks (TASK-GAP-002 finding). Integration tests against a real Neo4j instance are a recommended future addition but are out of scope for this spec.

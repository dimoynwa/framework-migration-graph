# Tasks: Community Insight Restructure

**Input**: Design documents from `specs/009-community-insight-restructure/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅

**Implementation order**: (1) Rewrite `migration_oracle/mcp/graph/queries/community.py` queries → (2) Error handler in `migration_oracle/mcp/tools/community.py` → (3) T013→T014 sequential docstrings + T015/T016 [P] search.py cleanup → (4) Unit tests (T018–T027) → (5) Integration smoke-test T029 (includes 2 grep checks) → (6) Streamlit smoke-test T030 (LAST)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (independent files, no blocking dependency)
- **[Story]**: Maps to user story in spec.md (US1–US4)
- Each task names the exact file path to touch

---

## Phase 1: Setup

**Purpose**: Confirm the environment and confirm no new infrastructure is required before touching source files.

- [X] T001 Confirm no new Python dependencies are required: check `pyproject.toml` / `requirements.txt` and verify `fastmcp`, `neo4j` driver, `sentence-transformers`, and `streamlit` are already present; confirm `pytest` is available for the test tasks

**Checkpoint**: Environment confirmed — source rewrites can begin

---

## Phase 2: Foundational — Rewrite `migration_oracle/mcp/graph/queries/community.py`

**Purpose**: Replace all `CommunityInsight`-label Cypher strings and update all helpers. This phase BLOCKS every user story — no tool or search change is correct until these Cypher strings are in place.

**⚠️ CRITICAL**: Complete T002–T010 before starting Phase 3.

- [X] T002 [US1] Rewrite `_FIND_EXACT_STATEMENT` in `migration_oracle/mcp/graph/queries/community.py`: change `MATCH (ci:CommunityInsight) WHERE ci.statement = $statement` to `MATCH (r:MigrationRule) WHERE r.statement = $statement AND r.ruleType = 'community_insight'`

- [X] T003 [US1] Rewrite `_FETCH_EMBEDDING` in `migration_oracle/mcp/graph/queries/community.py`: change `MATCH (ci:CommunityInsight) WHERE elementId(ci) = $insight_id RETURN ci.embedding AS embedding` to `MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id RETURN r.embedding AS embedding`

- [X] T004 [US1] Rewrite `_SUBMIT_INSIGHT` in `migration_oracle/mcp/graph/queries/community.py`: replace the `CommunityInsight` CREATE + `DISCOVERED_IN` pattern with an atomic query that (a) `MATCH (v:Version {framework: $framework, version: $version})`, (b) `CREATE (r:MigrationRule {statement, ruleType: 'community_insight', sourceUrl, communitySubmittedBy, communityCreatedAt, communityConfidence, communityVotes: 0, communityVerified: false, embedding: $embedding})`, (c) `CREATE (v)-[:INCLUDES_RULE]->(r)`, (d) `CREATE (s:MigrationStep {stepType: 'manual', summary: coalesce($solution,''), instruction: coalesce($solution,''), effort: 'moderate', automatable: false})`, (e) `CREATE (r)-[:REQUIRES_STEP]->(s)`, (f) three `FOREACH` blocks for `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, `AFFECTS_DEPENDENCY` using `MERGE` with `ON CREATE / ON MATCH SET`, (g) `RETURN elementId(r) AS insight_id` — full Cypher in plan.md §1c

- [X] T005 [US2] Rewrite `_QUERY_INSIGHTS` in `migration_oracle/mcp/graph/queries/community.py`: match `(v:Version {framework: $framework})-[:INCLUDES_RULE]->(r:MigrationRule)` where `r.ruleType = 'community_insight'`, apply version range and `$verified_only` filters, `OPTIONAL MATCH` to affected entities, then `OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)` with `ORDER BY s.stepIndex ASC` and `collect(s)[0] AS first_step`, return `coalesce(first_step.instruction, '') AS solution` plus `communitySubmittedBy AS submitted_by`, `communityCreatedAt AS created_at`, `communityConfidence AS confidence`, `communityVotes AS votes`, `communityVerified AS verified` — full Cypher in plan.md §1d

- [X] T006 [US3] Rewrite `_VOTE_INSIGHT` in `migration_oracle/mcp/graph/queries/community.py`: change `MATCH (ci:CommunityInsight)` to `MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id`, change `SET ci.votes = coalesce(ci.votes, 0) + $delta` to `SET r.communityVotes = coalesce(r.communityVotes, 0) + $delta`, return `elementId(r) AS insight_id, r.communityVotes AS votes` (alias `votes` preserved so Python call site is unchanged)

- [X] T007 [US3] Rewrite `_VERIFY_INSIGHT` in `migration_oracle/mcp/graph/queries/community.py`: change `MATCH (ci:CommunityInsight)` to `MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id`, change `SET ci.verified = true` to `SET r.communityVerified = true`, return `elementId(r) AS insight_id, r.communityVerified AS verified` (alias `verified` preserved)

- [X] T008 [US1] Update `find_near_duplicate` in `migration_oracle/mcp/graph/queries/community.py`: change `vector_search(index="migration_knowledge_vector_ci", ...)` to `vector_search(index="migration_knowledge_vector_mr", ...)`; the `if not embedding: return None` short-circuit and the `_find_exact_statement` call are unchanged

- [X] T009 [US1] Update `_best_bm25_duplicate` in `migration_oracle/mcp/graph/queries/community.py`: change `bm25_search(query=statement, index="migration_text", top_k=5)` to `bm25_search(query=statement, index="rule_statement", top_k=5)`

- [X] T010 [US1] Update `submit_insight()` in `migration_oracle/mcp/graph/queries/community.py`: after `record = session.run(_SUBMIT_INSIGHT, params).single()`, add `if record is None: raise ValueError(f"Version not found: {framework} {version}")`; remove the old `RuntimeError("Failed to create CommunityInsight")` guard; driver-level failures continue to propagate as driver exceptions

- [X] T011 [P] Remove `CommunityInsight` from the `migration_text` fulltext index DDL in `migration_oracle/graph/indexes.py` line 27: change `"FOR (n:MigrationRule|CommunityInsight) ON EACH [n.statement, n.reason, n.solution]"` to `"FOR (n:MigrationRule) ON EACH [n.statement, n.reason, n.solution]"`; add a comment above the DDL string noting the live-DB drop step from plan.md §2 (this file is independent of community.py so it can be done in parallel with T002–T010)

**Checkpoint**: All Cypher is correct and `CommunityInsight` label references are gone from `queries/community.py` and `indexes.py` — user story work can now begin

---

## Phase 3: User Story 1 — Submit a Community Insight (Priority: P1) 🎯 MVP

**Goal**: The `submit_migration_insight` tool correctly writes a `MigrationRule` + `MigrationStep` pair and handles the Version-not-found case with a structured error response.

**Independent Test**: Call `submit_migration_insight` with a valid statement, solution, and version; confirm `{status: "ok", insight_id: <id>, duplicate_of: "", message: "Insight submitted"}`; verify `CommunityInsight` label absent everywhere.

- [X] T012 [US1] Add `try/except ValueError` error handler in `migration_oracle/mcp/tools/community.py` around the `community_queries.submit_insight(...)` call in `submit_migration_insight`: on `ValueError`, return `{"status": "error", "insight_id": "", "duplicate_of": "", "message": str(e)}`; existing success and duplicate branches are unchanged — full pattern in plan.md §5a

- [X] T013 [P] [US1] Update `submit_migration_insight` docstring in `migration_oracle/mcp/tools/community.py`: replace `"Submit a developer-contributed migration insight. Writes a CommunityInsight node."` with `"Submit a developer-contributed migration insight. Writes a MigrationRule node with ruleType='community_insight'."` — no signature or return-shape change

**Checkpoint**: User Story 1 is fully functional — submit path writes correct graph nodes and handles errors

---

## Phase 4: User Story 2 — Retrieve Community Insights (Priority: P2)

**Goal**: `get_community_insights` returns community insights from `MigrationRule` nodes; `search_migration_knowledge` no longer requires an `include_community_insights` flag.

**Independent Test**: After submitting an insight in US1, call `get_community_insights` for the same version range; confirm the insight appears with `solution` populated from `MigrationStep.instruction`.

- [X] T014 [P] [US2] Update `get_community_insights` docstring in `migration_oracle/mcp/tools/community.py`: replace `"Query CommunityInsight nodes by version range…"` with `"Query MigrationRule nodes (ruleType='community_insight') by version range…"` — no signature or return-shape change (this file edit is independent of T015 and T016 below)

- [X] T015 [P] [US2] Apply three surgical changes to `hydrate_nodes` in `migration_oracle/mcp/graph/queries/search.py`: (1) remove the `include_community_insights: bool = True` parameter from the Python function signature; (2) delete the Cypher filter line `AND ($include_community_insights OR 'MigrationRule' IN labels(n))`; (3) insert `OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)` and `WITH n, versions, collect(s)[0] AS first_step` after the `WHERE ($framework IS NULL OR size(versions) > 0)` line; (4) change the RETURN projection `n.solution AS solution` to `coalesce(n.solution, first_step.instruction) AS solution`; (5) remove `include_community_insights=include_community_insights` from the `session.run(cypher, ...)` call — full Cypher in plan.md §3b

- [X] T016 [P] [US2] Remove `include_community_insights` from `migration_oracle/mcp/tools/search.py`: (a) remove `include_community_insights: bool = True` from `search_migration_knowledge` signature and its docstring reference; (b) remove `include_community_insights: bool` from `_build_hits` helper signature; (c) remove `include_community_insights=include_community_insights` from the `_build_hits(...)` call inside `search_migration_knowledge`; (d) change `_build_hits(fused, framework=None, include_community_insights=False, openrewrite=True)` in `search_openrewrite_recipes` to `_build_hits(fused, framework=None, openrewrite=True)` — plan.md §4

**Checkpoint**: Community insights appear in search results automatically; `include_community_insights` removed from all three locations per FR-013

---

## Phase 5: User Story 3 — Vote and Verify Insights (Priority: P3)

**Goal**: `vote_insight` and `verify_insight` operate on `MigrationRule` nodes and return the correct shaped responses. Cypher rewrites were completed in Phase 2 (T006, T007).

**Independent Test**: Submit an insight (US1), call `vote_insight(delta=1)`, confirm `new_vote_count=1`; call `verify_insight`, confirm `verified=true`.

- [X] T017 [US3] Audit `_VOTE_INSIGHT` (T006) and `_VERIFY_INSIGHT` (T007) Cypher aliases against the `VoteInsightResult` and `VerifyInsightResult` shapes in `specs/009-community-insight-restructure/contracts/009-community-insight-restructure.md`. **Pass criteria** (two checks): (1) open `migration_oracle/mcp/graph/queries/community.py` and confirm `_VOTE_INSIGHT` returns `r.communityVotes AS votes` and that `vote_insight()` at the tool layer reads `result["votes"]` and maps it to `new_vote_count` in the returned dict; (2) confirm `_VERIFY_INSIGHT` returns `r.communityVerified AS verified` and that `verify_insight()` at the tool layer reads `result["verified"]`. **Fail criteria**: any mismatch between the Cypher alias name and the Python key used to read the result (e.g., reading `result["communityVotes"]` from a Cypher that returns `votes`) means T006 or T007 needs a fix before tests run. No code change expected if T006 and T007 were implemented correctly.

**Checkpoint**: Vote and verify paths confirmed correct — all implementation tasks are complete

---

## Phase 6: Tests

**Purpose**: Add unit tests covering five spec invariants that are not guarded by existing tests; confirm existing test suites pass unchanged after the implementation changes.

- [X] T018 [US1] Add unit test for the `ValueError` / Version-not-found path in `tests/mcp/test_community.py`: mock `community_queries.submit_insight` to `raise ValueError("Version not found: Spring Boot 9.9")`; call `submit_migration_insight(spring_boot_version="9.9", ...)`; assert the response is `{"status": "error", "insight_id": "", "duplicate_of": "", "message": "Version not found: Spring Boot 9.9"}`; update any existing assertion in this test file that still expects a `CommunityInsight` label in mock return values (plan.md §7)

- [X] T019 [US1] Add unit test for `MigrationRule` + `MigrationStep` write atomicity in `tests/mcp/test_community.py`: mock the graph session and call `submit_insight(statement="x", framework="spring_boot", version="3.0.0", ...)`; assert `session.run` was called **exactly once** — a single `session.run` call is the only mechanism that can guarantee both CREATEs execute in the same transaction; assert that the single Cypher string passed to `session.run` contains `CREATE (r:MigrationRule`, `CREATE (s:MigrationStep`, and `REQUIRES_STEP`; a string-inspection-only approach without the call-count check would pass even if the implementation split the write into two separate `session.run` calls, which would violate contracts §Write Atomicity (neither node is written if the transaction fails)

- [X] T020 [US2] Add unit test for `solution` field sourcing in `tests/mcp/test_community.py`: mock `session.run` for `_QUERY_INSIGHTS` to return a record where the `solution` key equals `"test step instruction"` (simulating `coalesce(first_step.instruction, '')`); call `query_insights(...)` and assert the returned dict entry has `"solution": "test step instruction"`; additionally inspect the `_QUERY_INSIGHTS` Cypher string and assert it contains `OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)` and `coalesce(first_step.instruction` — confirming the solution value is traversed from the step, not read from a non-existent `r.solution` property (contracts §Solution Field Source, SC-008)

- [X] T021 [US1] Add unit test for duplicate-detection index names in `tests/mcp/test_community.py`: patch `vector_search` and call `find_near_duplicate(statement="x", embedding=[0.1, 0.2])`; assert `vector_search` was called with `index="migration_knowledge_vector_mr"` and NOT with `index="migration_knowledge_vector_ci"`; in a second test, patch `bm25_search` and call `find_near_duplicate` with a non-None embedding after `_find_exact_statement` returns `None`; assert `bm25_search` was called with `index="rule_statement"` (not `"migration_text"`) — contracts §Duplicate Detection Index Names, plan.md §1g, §1h

- [X] T022 [US1] Add unit test for community property prefixes in `tests/mcp/test_community.py`: inspect the `_SUBMIT_INSIGHT` Cypher string constant and assert it contains `communityVotes`, `communityVerified`, `communitySubmittedBy`, `communityCreatedAt`, `communityConfidence`; assert it does NOT contain the unprefixed forms `votes:`, `verified:`, `submittedBy:` — this guards against an implementer writing flat property names that match the response-layer aliases instead of the spec-required prefixed names on the node (contracts §Property Naming, data-model.md §MigrationRule community_insight variant)

- [X] T023 [US2] Add unit test for the `verified_only=True` filter in `tests/mcp/test_community.py`: inspect the `_QUERY_INSIGHTS` Cypher string constant in `migration_oracle/mcp/graph/queries/community.py` and assert it contains `$verified_only = false OR r.communityVerified = true`; in a separate behavioral test, mock `session.run` to return an empty result set and call `query_insights(verified_only=True, ...)`; assert the Cypher was executed with the parameter `verified_only=True` passed through — this guards FR-010 and spec acceptance scenario US2.2 (only `communityVerified=true` nodes are returned when `verified_only=True`)

- [X] T024 [US1] Add unit test for `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, `AFFECTS_DEPENDENCY` relationship creation in `tests/mcp/test_community.py`: inspect the `_SUBMIT_INSIGHT` Cypher string constant and assert it contains `AFFECTS_CLASS`, `AFFECTS_PROPERTY`, and `AFFECTS_DEPENDENCY`; assert the Cypher contains `FOREACH` blocks for each; assert it uses `MERGE` (not `CREATE`) for entity nodes so re-submitted insights pointing at the same class/property/dependency do not duplicate nodes — guards FR-008 and spec acceptance scenario US1.4

- [X] T025 [US1] Add unit test for the embedding-disabled (`embedding=None`) path in `tests/mcp/test_community.py`: mock `community_queries.submit_insight` to record the `embedding` kwarg it receives and return `("fake-id", False)`; call `submit_migration_insight` with `POPULATE_MIGRATION_EMBEDDINGS=false` (or explicitly pass `embedding=None` at the tool layer); assert (a) no exception is raised, (b) the returned `status` is `"ok"`, (c) `submit_insight` was called with `embedding=None`; in a separate unit test, patch `vector_search` and call `find_near_duplicate(statement="x", embedding=None)` and assert `vector_search` was NOT called (the `if not embedding: return None` short-circuit must fire before the vector path) — research.md Q4, plan.md §1c, SC-007

- [X] T026 [P] [US2] Run `pytest tests/mcp/test_search.py` and confirm all tests pass with zero changes to the test file: the mocks operate at the `hydrate_nodes` boundary and removing `include_community_insights` from the Python signature does not break any mock call site (plan.md §7 — confirm-only)

- [X] T027 [P] [US4] Run `pytest tests/streamlit/test_05_community.py` and confirm all tests pass with zero changes to the test file: the mocks operate at the tool layer; all tool signatures are unchanged (plan.md §7 — confirm-only)

**Checkpoint**: Test suite green — ready for smoke testing

---

## Phase 7: Smoke Tests — User Story 4 (Priority: P4)

**Goal**: Verify the full community workflow end-to-end and confirm the Streamlit page is unbroken.

**Independent Test**: Full happy-path flow across all community tools plus Streamlit page render.

- [X] T028 [US4] Confirm `migration_oracle/streamlit_app/pages/05_community.py` requires no structural code changes: read the file and verify it calls `submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight` by Python import with unchanged signatures; run `grep -n 'CommunityInsight' migration_oracle/streamlit_app/pages/05_community.py` and assert zero results — task is complete when the grep returns empty and no import or function call differs from pre-spec signatures (explicit no-op per FR-015 and plan.md §6)

- [X] T029 [US3] Integration smoke-test (live graph required): (1) call `submit_migration_insight` with a valid `spring_boot_version`, `statement`, and `solution`; assert `status="ok"` and a valid `insight_id` is returned; (2) call `get_community_insights` for the submitted version; assert the insight appears with `solution` matching the submitted text; (3) call `vote_insight(insight_id, delta=1)`; assert `new_vote_count=1` in the response; (4) call `verify_insight(insight_id)`; assert `verified=true`; (5) run `grep -r 'CommunityInsight' migration_oracle/` — must return zero results (SC-004); (6) run `grep -r 'include_community_insights' migration_oracle/` — must return zero results (SC-003); both greps failing to return zero results indicate an incomplete removal and must block the smoke-test from passing

- [X] T030 [US4] Streamlit smoke-test — **MUST BE LAST**: start the Streamlit app (`streamlit run migration_oracle/streamlit_app/app.py`); navigate to the Community page (`migration_oracle/streamlit_app/pages/05_community.py`); verify the page loads without traceback; verify the insight submission form renders; verify the insight list renders or shows the empty-state message; submit a test insight via the UI and confirm it appears in the list; confirm no console errors (SC-006)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS Phases 3–7**
- **Phase 3 (US1)**: Depends on Phase 2 — unblocked once T002–T011 complete
- **Phase 4 (US2)**: Depends on Phase 2 — T013 and T014 are sequential (same file: `tools/community.py`); T015 and T016 are independent and can run in parallel with T013+T014
- **Phase 5 (US3)**: Depends on Phase 2 — T006 and T007 must be complete
- **Phase 6 (Tests)**: Depends on Phases 3, 4, 5 being complete
- **Phase 7 (Smoke Tests)**: Depends on Phase 6 — T030 MUST be last

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2. No dependency on US2, US3.
- **US2 (P2)**: Can start after Phase 2. T013–T014 are sequential (same file); T015–T016 are independent of T013–T014 and of each other.
- **US3 (P3)**: Cypher done in Phase 2 (T006, T007). T017 review depends on T006, T007.
- **US4 (P4)**: Depends on US1, US2, US3 all being complete before smoke tests.

### Parallel Opportunities in Phase 4

T013 and T014 both edit `migration_oracle/mcp/tools/community.py` — they are **sequential**. T015 and T016 edit different files and are **parallel** with each other and with T013+T014:

```
T013  migration_oracle/mcp/tools/community.py        — submit_migration_insight docstring  (sequential with T014)
T014  migration_oracle/mcp/tools/community.py        — get_community_insights docstring   (sequential; same file as T013)
T015  migration_oracle/mcp/graph/queries/search.py   — hydrate_nodes                      [P: different file]
T016  migration_oracle/mcp/tools/search.py           — search_migration_knowledge          [P: different file]
```

T015 and T016 may start as soon as Phase 2 is complete — they do not need to wait for T013 or T014. T013 and T014 must be completed in order to avoid same-file conflicts. In Phase 6, T024 and T025 are confirm-only test runs that can also run in parallel.

---

## Parallel Execution Example: Phase 4

```bash
# After Phase 2 and T012 (Phase 3) are complete:
# T013 → T014 must run sequentially (same file: migration_oracle/mcp/tools/community.py)
Task A-seq: "Update submit_migration_insight docstring in migration_oracle/mcp/tools/community.py" (T013)
Task B-seq: "Update get_community_insights docstring in migration_oracle/mcp/tools/community.py" (T014)  # after T013

# T015 and T016 can start immediately after Phase 2 — independent of T013/T014:
Task C-par: "Remove include_community_insights from migration_oracle/mcp/graph/queries/search.py hydrate_nodes" (T015)  [P]
Task D-par: "Remove include_community_insights from migration_oracle/mcp/tools/search.py search_migration_knowledge and _build_hits" (T016)  [P]

# In Phase 6, these two confirm-only runs can also be parallel:
Task E-par: "Run pytest tests/mcp/test_search.py" (T026)  [P]
Task F-par: "Run pytest tests/streamlit/test_05_community.py" (T027)  [P]
```

---

## Implementation Strategy

### MVP (User Story 1 Only — minimum viable change)

1. Complete Phase 1 + Phase 2 (T001–T011) — rewrites all Cypher
2. Complete Phase 3 (T012–T013) — error handler + docstring
3. Add unit tests T018–T025 in `tests/mcp/test_community.py` — confirm all pass
4. **STOP and VALIDATE**: submit path is correct end-to-end
5. Deploy if ready; US2–US4 can follow

### Incremental Delivery

1. Phase 2 → Foundation ready (all Cypher migrated)
2. Phase 3 (US1) → Submit path live ✓
3. Phase 4 (US2) → Retrieve + search path live ✓
4. Phase 5 (US3) → Vote/verify audited ✓
5. Phase 6 (Tests T018–T027) → Suite green ✓
6. Phase 7 (T028–T030) → Smoke tests pass → **Ship**

---

## Notes

- `[P]` = independent file; safe to start without waiting for sibling tasks
- `[Story]` label maps each task to the spec.md user story for traceability
- **T030 is mandatory last** — do not run the Streamlit smoke-test before all code changes and unit tests are complete
- **indexes.py caveat**: T011 code change is a no-op on any live Memgraph that already has `migration_text` created; run `DROP INDEX migration_text;` on the live instance before next restart (plan.md §2)
- **`DISCOVERED_IN` arm**: `hydrate_nodes` Cypher retains `[:INCLUDES_RULE|DISCOVERED_IN]` for backward compatibility with legacy nodes — do not remove it as part of this spec (plan.md §3b)
- Grep verification: after all tasks complete, `grep -r 'CommunityInsight' migration_oracle/` must return zero results (SC-004, contracts §No CommunityInsight Label)

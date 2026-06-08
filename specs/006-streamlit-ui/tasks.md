# Tasks: Streamlit Operator UI

**Input**: Design documents from `specs/006-streamlit-ui/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/006-streamlit-ui.md ✅, quickstart.md ✅

**Tests**: One test task per page — added per gap review. Tests use `streamlit.testing.v1.AppTest` with `unittest.mock.patch` to mock tool functions.

**FastMCP import note (GAP-008)**: research.md Q3 confirms `@mcp.tool()` returns the original function unchanged — no unwrapping task required. Import decorated names directly.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase (different files, no blocking dependencies)
- **[Story]**: Which user story this task belongs to (US1–US5)
- All file paths are fully nested (e.g. `migration_oracle/streamlit_app/pages/01_pipeline_trigger.py`)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the dependency, create the package directory structure, and create the Streamlit entry point. No `migration_oracle` graph imports. Unblocks all subsequent phases.

- [X] T001 Verify `streamlit>=1.35` is present in `[project.dependencies]` of `pyproject.toml` (confirmed by research.md D6 — no edit required); run `uv sync` to install all dependencies including Streamlit; confirm `streamlit --version` reports ≥1.35
- [X] T002 Create `migration_oracle/streamlit_app/` directory and `migration_oracle/streamlit_app/pages/` subdirectory; add empty `__init__.py` at `migration_oracle/streamlit_app/__init__.py` so the package is importable
- [X] T003 Create `migration_oracle/streamlit_app/app.py` — call `st.set_page_config(layout="wide", page_title="Migration Oracle")` and add a sidebar title; do NOT import anything from `migration_oracle` at module level (plan.md §app.py); Streamlit discovers pages automatically from the `pages/` subdirectory

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared helpers required by every page. Must be complete before any page is implemented.

**⚠️ CRITICAL**: No page can be implemented until `migration_oracle/streamlit_app/_helpers.py` exists.

- [X] T004 Create `migration_oracle/streamlit_app/_helpers.py` — implement three helpers exactly as specified in plan.md §Shared Helpers: `call_tool(fn, *args, **kwargs)` (wraps any callable in try/except, renders `st.error`, returns `None` on failure); `framework_selectbox(label, key, include_all=False)` (renders a selectbox showing display names; when `include_all=False` always returns a CLI key string e.g. `"spring-boot"`; when `include_all=True` prepends the Python sentinel `None` to the options list so that selecting "All" returns the Python value `None` — NOT the string `"all"` — return type is `str | None`; callers that receive `None` MUST pass `framework=None` explicitly to tool functions, never omit the kwarg; NOT used by Rule Explorer); `effort_badge(effort)` (maps `"mechanical"` / `"substantial"` to labelled strings). Import `FRAMEWORK_DISPLAY_NAMES` from `migration_oracle.pipeline.extractors`.

**Checkpoint**: `migration_oracle/streamlit_app/app.py` and `migration_oracle/streamlit_app/_helpers.py` exist — page implementation can now begin.

---

## Phase 3: User Story 1 — Trigger a Pipeline Run (Priority: P1) 🎯 MVP

**Goal**: Operator can select a framework, enter versions, check flags, submit the form, see live pipeline output stream, and see the exit code result.

**Independent Test**: Open Pipeline Trigger, select a framework, enter `2.7.x` → `3.2`, check `--dry-run`, click Submit. Verify output lines stream into the output area and the exit code appears green (0) or red (non-zero). No graph or Neo4j connection required for this page.

- [X] T005 [P] [US1] Create `migration_oracle/streamlit_app/pages/01_pipeline_trigger.py` — add imports (`sys`, `subprocess`, `streamlit as st`, `FRAMEWORK_DISPLAY_NAMES` from `migration_oracle.pipeline.extractors`); build the form using `st.form`: `st.selectbox` over `list(FRAMEWORK_DISPLAY_NAMES.values())` as labels with index mapped to CLI keys via `list(FRAMEWORK_DISPLAY_NAMES.keys())[idx]`; `st.text_input` for `from_version`; `st.text_input` for `to_version`; four `st.checkbox` widgets for `--dry-run`, `--force`, `--force-extract`, `--force-llm`; Submit button inside the form
- [X] T006 [US1] Add subprocess invocation and live output streaming in `migration_oracle/streamlit_app/pages/01_pipeline_trigger.py` — on form submit, validate that `from_version` and `to_version` are non-empty (show `st.warning` and stop if blank); extract CLI key from selected index; build command list `[sys.executable, "-m", "migration_oracle.cli", "--framework", key, from_version, to_version] + flag_args` (`shell=False`); spawn `subprocess.Popen` with `stdout=PIPE, stderr=PIPE, text=True`; initialize `output_area = st.empty()` and `lines: list[str] = []`; iterate `for line in proc.stdout`, append each `line.rstrip()`, call `output_area.code("\n".join(lines))`; call `proc.wait()` after the loop; read `stderr_lines = proc.stderr.read().splitlines()`
- [X] T007 [US1] Add exit-code display in `migration_oracle/streamlit_app/pages/01_pipeline_trigger.py` — after `proc.wait()`, if `proc.returncode == 0` call `st.success("Exit 0")`; else call `st.error(f"Exit {proc.returncode}: {stderr_lines[-1] if stderr_lines else 'see output above'}")`
- [X] T008 [US1] Write page-load, empty-form, and happy-path tests in `tests/streamlit/test_01_pipeline_trigger.py` — using `from streamlit.testing.v1 import AppTest` and `unittest.mock.patch`: (1) test page loads without exception: `at = AppTest.from_file("migration_oracle/streamlit_app/pages/01_pipeline_trigger.py"); at.run(); assert not at.exception`; (2) test blank version inputs: submit form with empty `from_version`; assert a warning widget appears and no subprocess is spawned; (3) happy-path: patch `subprocess.Popen` to return a mock process with `stdout=iter(["line1\n"])`, `returncode=0`, `stderr.read()` returning `""`; submit form with valid inputs; assert `at.success` is not empty
- [X] T009 [US1] Write subprocess streaming and exit-code tests in `tests/streamlit/test_01_pipeline_trigger.py` — (1) streaming: patch `subprocess.Popen` to yield multiple stdout lines; run the page; assert the `st.empty()` placeholder content grows with each line (check final code block contains all lines); (2) non-zero exit: patch process `returncode=1`, `stderr.read()` returning `"Build failed"`; submit form; assert `at.error[0].value` contains `"Exit 1"` and `"Build failed"`

**Checkpoint**: Pipeline Trigger fully functional and tested. No graph required.

---

## Phase 4: User Story 2 — Browse Pipeline Run Artifacts (Priority: P2)

**Goal**: Operator can select a completed run and view its Raw MD, Filtered MD, and Entities JSON artifacts in tabbed views.

**Independent Test**: Navigate to Run Browser with at least one pipeline run in Neo4j. Verify run appears in selectbox labelled `"framework → to_version"`, switching tabs shows content, and missing artifact shows inline error (not a crash). With empty graph, verify `st.info("No pipeline runs found")` and no selectbox renders.

- [X] T010 [P] [US2] Create `migration_oracle/streamlit_app/pages/02_run_browser.py` — import `list_pipeline_runs`, `get_artifact_content` from `migration_oracle.mcp.tools.artifacts`, `json`, `streamlit as st`, `call_tool` from `migration_oracle.streamlit_app._helpers`; define `@st.cache_data(ttl=60)` wrapper `_cached_list_runs()` that calls `list_pipeline_runs()`; on page load call via `call_tool(_cached_list_runs)`; if result is `None` or `result.get("runs", []) == []` render `st.info("No pipeline runs found")` and stop; else build display labels `f"{r['framework']} → {r['to_version']}"` and render `st.selectbox`
- [X] T011 [US2] Add three-tab artifact viewer in `migration_oracle/streamlit_app/pages/02_run_browser.py` — below the selectbox create three `st.tabs(["Raw MD", "Filtered MD", "Entities JSON"])`; in each tab call `get_artifact_content(framework, from_version, to_version, artifact_type)` via `call_tool`; if response is `None` or `response["status"] != "ok"` render `st.error("Artifact not found")`; Raw MD: `st.markdown(response["content"])`; Filtered MD: `st.markdown(response["content"])`; Entities JSON: `st.json(json.loads(response["content"]), expanded=1)`
- [X] T012 [US2] Write page-load, empty-state, and happy-path tests in `tests/streamlit/test_02_run_browser.py` — (1) page loads without exception; (2) patch `list_pipeline_runs` to return `{"runs": []}`: assert `st.info` widget with "No pipeline runs found" appears and no selectbox is rendered; (3) patch `list_pipeline_runs` to return one run `{"framework": "spring-boot", "from_version": "", "to_version": "3.2", ...}`: assert selectbox renders with label `"spring-boot → 3.2"`; (4) patch `get_artifact_content` to return `{"status": "not_found", "content": ""}`: assert `st.error` appears in the affected tab

**Checkpoint**: Run Browser complete. US1 and US2 independently functional.

---

## Phase 5: User Story 3 — Explore Migration Rules (Priority: P2)

**Goal**: Operator can enter a search query, optionally filter by framework, and browse expandable result cards.

**Independent Test**: Navigate to Rule Explorer, type `"removed API"`, click Search. Verify cards appear with statement excerpt (first 80 chars), `rule_type` badge, `source_url` link, `action_step` text. Verify selecting "All" returns results across frameworks. Verify a no-match query shows `st.info("No rules found for this query")`.

- [X] T013 [P] [US3] Create `migration_oracle/streamlit_app/pages/03_rule_explorer.py` — import `asyncio`, `streamlit as st`, `search_migration_knowledge` from `migration_oracle.mcp.tools.search`, `FRAMEWORK_DISPLAY_NAMES` from `migration_oracle.pipeline.extractors`, `call_tool` from `migration_oracle.streamlit_app._helpers`; add `st.text_input` for query (key `"re_query"`); build inline framework filter: `display_names = ["All"] + list(FRAMEWORK_DISPLAY_NAMES.values())`; `choice = st.selectbox("Framework filter", display_names, key="re_fw")`; `fw: str | None = None if choice == "All" else choice`; do NOT call `framework_selectbox` — Rule Explorer passes display names directly to `search_migration_knowledge` (plan.md §Rule Explorer)
- [X] T014 [US3] Add search invocation and result cards in `migration_oracle/streamlit_app/pages/03_rule_explorer.py` — add a Search button; on click, if query non-empty: build coroutine `coro = search_migration_knowledge(query=q, framework=fw, max_results=20)` (pass `framework=fw` explicitly — never omit; `None` fires the all-frameworks Cypher branch; a display name filters to that framework); call `result = call_tool(asyncio.run, coro)`; if `result` is `None` stop; extract `hits = result.get("hits", [])`; if empty show `st.info("No rules found for this query")`; else for each hit: `st.expander(hit["statement"][:80])` containing `st.caption(hit["rule_type"])` if non-empty, `st.markdown(f"[Source]({hit['source_url']})")` if `source_url` non-empty, `st.write(hit["action_step"])` if non-empty
- [X] T015 [US3] Write page-load, no-results, and happy-path tests in `tests/streamlit/test_03_rule_explorer.py` — (1) page loads without exception; (2) patch `search_migration_knowledge` to return `{"hits": []}`; type query and click Search; assert `st.info` widget shows "No rules found for this query"; (3) patch to return one hit with `statement="Some long rule statement"`, `rule_type="breaking-change"`, `source_url=""`, `action_step="Do something"`; click Search; assert one expander rendered with title `"Some long rule stateme"[:80]`; (4) verify that when "All" is selected, `search_migration_knowledge` is called with `framework=None` (not omitted and not `"all"`)

**Checkpoint**: Rule Explorer complete. US1, US2, and US3 independently functional.

---

## Phase 6: User Story 4 — Track Migration Context Progress (Priority: P3)

**Goal**: Operator can load or create a migration context, view pending steps, mark steps complete or skipped, and close the context.

**Independent Test**: Navigate to Context Dashboard, fill project ID, versions, framework, click "Load / Create". Verify context status badge and counts appear. Verify pending steps table renders. Click "Mark Complete" on a step — verify it disappears from the table and counts update. Navigate away and back — verify context is still loaded without re-entering the form.

- [X] T016 [P] [US4] Create `migration_oracle/streamlit_app/pages/04_context_dashboard.py` — import `streamlit as st`, `create_migration_context`, `get_pending_steps`, `update_step_status`, `close_migration_context` from `migration_oracle.mcp.tools.context`, `FRAMEWORK_DISPLAY_NAMES` from `migration_oracle.pipeline.extractors`, `call_tool`, `framework_selectbox` from `migration_oracle.streamlit_app._helpers`; if `"context_id" not in st.session_state` render the load/create form: `st.text_input` for `project_id`, `from_version`, `to_version`; `cli_key = framework_selectbox("Framework", key="cd_fw", include_all=False)` returns a CLI key string (e.g. `"spring-boot"`); convert it to a display name before calling the tool: `fw_display = FRAMEWORK_DISPLAY_NAMES[cli_key]`; on "Load / Create" button click call `create_migration_context(project_id, from_version, to_version, fw_display, scanned_entities=[])` via `call_tool` (pass the display name — the graph stores `fw_display`, not the CLI key); on success set all 8 flat `context_*` session state keys from `response` (see data-model.md §Session State): `context_id`, `context_project_id`, `context_from_version`, `context_to_version`, `context_framework` = `fw_display`, `context_status`, `context_completed_count` = `len(response["completed_steps"])`, `context_skipped_count` = `len(response["skipped_steps"])`
- [X] T017 [US4] Add context dashboard display in `migration_oracle/streamlit_app/pages/04_context_dashboard.py` — when `"context_id" in st.session_state`: render `st.caption(f"Status: {st.session_state['context_status']}")`; render two `st.metric` widgets for completed and skipped counts from session state; call `get_pending_steps(st.session_state["context_id"])` via `call_tool`; extract `pending = response.get("pending_steps", [])`; if `pending == []` show `st.info("No pending steps remaining")` and stop; else render pending steps row-by-row (columns: summary, effort, automatable, scope, severity) using `st.columns`
- [X] T018 [US4] Add step action buttons in `migration_oracle/streamlit_app/pages/04_context_dashboard.py` — for each pending step row render two buttons: "Mark Complete" and "Skip"; "Mark Complete" calls `update_step_status(context_id, step_id, outcome="completed")` via `call_tool`; on success update `st.session_state["context_completed_count"]` from `response["completed_count"]` and `st.session_state["context_skipped_count"]` from `response["skipped_count"]`; then re-fetch `get_pending_steps` and replace the pending list; "Skip" shows `st.text_input(f"Reason for skipping {step_id}", key=f"skip_reason_{step_id}")`; when reason non-empty, calls `update_step_status(..., outcome="skipped", reason=reason)` via `call_tool` and performs the same session-state update + re-fetch
- [X] T019 [US4] Add Close Context button in `migration_oracle/streamlit_app/pages/04_context_dashboard.py` — render only when `st.session_state["context_status"] == "in-progress"`; show `st.selectbox("Final status", ["complete", "partial", "abandoned"])` and `st.text_area("Notes")`; on "Close Context" button click call `close_migration_context(context_id, final_status, notes)` via `call_tool`; check `response["tool_status"]` (NOT `response["status"]`) for success; on success update `st.session_state["context_status"]` from `response["migration_status"]`
- [X] T020 [US4] Write page-load, no-pending-steps, and step-action tests in `tests/streamlit/test_04_context_dashboard.py` — (1) page loads without context in session_state: assert load/create form is rendered; (2) patch `create_migration_context` to return a valid `MigrationContextResponse`; submit form; assert all 8 `context_*` keys are set in session_state; (3) patch `get_pending_steps` to return `{"pending_steps": []}`; assert `st.info("No pending steps remaining")` shown; (4) patch `get_pending_steps` to return one step; patch `update_step_status` to return an `UpdateStepResponse` with `completed_count=1, skipped_count=0`; click "Mark Complete"; assert `st.session_state["context_completed_count"] == 1`

**Checkpoint**: Context Dashboard complete. US1–US4 independently functional.

---

## Phase 7: User Story 5 — Browse and Submit Community Insights (Priority: P3)

**Goal**: Operator can browse insight cards, vote on insights, and submit new insights.

**Independent Test**: Navigate to Community page. Verify insight cards render with statement, solution, votes, verified badge. Click "Vote Up" — verify vote count increments after re-fetch. Submit a new insight via the form — verify `st.success("Insight submitted")`. Submit the same insight again — verify `st.error("Duplicate detected")`.

- [X] T021 [P] [US5] Create `migration_oracle/streamlit_app/pages/05_community.py` — import `streamlit as st`, `get_community_insights`, `vote_insight`, `submit_migration_insight` from `migration_oracle.mcp.tools.community`, `FRAMEWORK_DISPLAY_NAMES` from `migration_oracle.pipeline.extractors`, `call_tool` from `migration_oracle.streamlit_app._helpers`; on page load call `get_community_insights()` (no arguments) via `call_tool`; extract `insights = result.get("insights", [])` if result else `[]`; if `insights == []` show `st.info("No community insights found")` and stop; else render one card per insight using `st.container`: show `statement`, `solution`, `votes`, verified badge (`"✓ Verified"` when `verified == True`), `source_url` link if non-empty
- [X] T022 [US5] Add vote and submit functionality in `migration_oracle/streamlit_app/pages/05_community.py` — "Vote Up" button per card calls `vote_insight(insight_id=insight["insight_id"], delta=1)` via `call_tool` (NOT `direction="up"` — see contracts §Tool Call Signature Constraints); on success re-fetch `get_community_insights()` and rerender; at page bottom add `st.expander("Submit New Insight")` containing `st.form` with: `statement` (text_area), `solution` (text_area), `spring_boot_version` text_input labelled "Version", `affected_classes` text_input with comma-sep hint (split to `list[str]` on submit), `evidence_url` text_input labelled "Evidence URL" (NOT `source_url`), `cli_key = framework_selectbox("Framework", key="ci_fw")` which returns a CLI key string; convert before calling the tool: `fw_display = FRAMEWORK_DISPLAY_NAMES[cli_key]`; on submit call `submit_migration_insight(statement=..., solution=..., spring_boot_version=..., affected_classes=..., evidence_url=..., framework=fw_display)` via `call_tool`; check `response["status"]`: `"ok"` → `st.success("Insight submitted")`; `"duplicate"` → `st.error("Duplicate detected")`
- [X] T023 [US5] Write page-load, empty-state, vote, and submit tests in `tests/streamlit/test_05_community.py` — (1) page loads without exception; (2) patch `get_community_insights` to return `{"insights": []}`; assert `st.info("No community insights found")` shown; (3) patch to return one insight; assert card rendered with statement and votes; (4) patch `vote_insight` to return `{"status": "ok", "new_vote_count": 5}`; click "Vote Up"; assert `vote_insight` was called with `insight_id=..., delta=1` (not `direction="up"`); (5) patch `submit_migration_insight` to return `{"status": "ok"}`; fill and submit form; assert `st.success("Insight submitted")`; (6) patch to return `{"status": "duplicate"}`; assert `st.error("Duplicate detected")`

**Checkpoint**: All five pages complete and independently tested.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Boundary compliance checks and full integration smoke test.

- [X] T024 [P] Validate empty-state rendering across all five pages — with no graph data (or Neo4j unreachable), navigate each page and confirm the correct `st.info(...)` message appears per contracts/006-streamlit-ui.md §Empty-State Contract; confirm no raw tracebacks reach the operator (FR-016, FR-017, SC-003); verify `app.py` itself starts without error even when Neo4j is unreachable (lazy import pattern per plan.md §app.py)
- [X] T025 [P] Validate graph access boundary compliance — verify no page file under `migration_oracle/streamlit_app/pages/` contains `open(`, `Path.read_text`, `neo4j`, or a bare Cypher string; verify `migration_oracle/streamlit_app/pages/03_rule_explorer.py` does NOT call `framework_selectbox`; verify `migration_oracle/streamlit_app/pages/01_pipeline_trigger.py` does NOT import `migration_oracle.mcp.tools.*`; verify `shell=True` does not appear in any page file (contracts/006-streamlit-ui.md §Graph Access Boundary, §Pipeline Invocation Boundary)
- [X] T026 Integration smoke test — start `streamlit run migration_oracle/streamlit_app/app.py` against a populated local Neo4j instance with at least one pipeline run and one community insight; navigate to all five pages; on each page: (a) verify the page renders without a Streamlit exception overlay, (b) verify at least one data widget or the empty-state `st.info` is visible; on Pipeline Trigger: submit a `--dry-run` run and verify stdout lines stream and exit 0 is shown; confirm no raw tracebacks on any page (SC-003)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001 → T002 → T003 are sequential
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user story phases; T004 must follow T001–T003
- **US1 Phase 3**: Depends on Phase 2 only — no Neo4j required; T005 → T006 → T007 → T008 → T009
- **US2 Phase 4 + US3 Phase 5**: Both depend on Phase 2 — can run in parallel with each other after T004
- **US4 Phase 6 + US5 Phase 7**: Both depend on Phase 2 — can run in parallel with each other; independent of US2/US3
- **Polish (Phase 8)**: Depends on all user story phases being complete; T024 and T025 can run in parallel; T026 must be last

### User Story Dependencies

- **US1 (P1)**: Standalone — no graph, no other user story
- **US2 (P2)**: Standalone — reads from graph but has no dependency on US1 output
- **US3 (P2)**: Standalone — same as US2; can run in parallel with US2
- **US4 (P3)**: Standalone — graph access only; no dependency on US1/US2/US3
- **US5 (P3)**: Standalone — graph access only; can run in parallel with US4

### Within Each User Story (sequential within a page file)

- T005 → T006 → T007 → T008 → T009 (US1)
- T010 → T011 → T012 (US2)
- T013 → T014 → T015 (US3)
- T016 → T017 → T018 → T019 → T020 (US4)
- T021 → T022 → T023 (US5)
- T024, T025 in parallel → T026 last (Polish)

### Parallel Opportunities

- T005 [US1] + T010 [US2] + T013 [US3] + T016 [US4] + T021 [US5]: all first-file tasks for each page — different files, can start in parallel once T004 is done if team capacity allows
- T010 [US2] and T013 [US3]: same priority (P2), different files — natural pair for two developers
- T016 [US4] and T021 [US5]: same priority (P3), different files — natural pair for two developers

---

## Parallel Example: P2 Stories (US2 + US3)

```
# After T004 (_helpers.py) is complete:

Developer A — US2:
  T010: Create migration_oracle/streamlit_app/pages/02_run_browser.py (cache + selectbox)
  T011: Add three-tab artifact viewer in migration_oracle/streamlit_app/pages/02_run_browser.py
  T012: Write tests in tests/streamlit/test_02_run_browser.py

Developer B — US3:
  T013: Create migration_oracle/streamlit_app/pages/03_rule_explorer.py (query + selector)
  T014: Add search invocation and result cards in migration_oracle/streamlit_app/pages/03_rule_explorer.py
  T015: Write tests in tests/streamlit/test_03_rule_explorer.py
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. T001–T003: Setup (verify dependency, directory, app.py)
2. T004: Foundational (`_helpers.py`)
3. T005–T009: US1 — Pipeline Trigger + tests
4. **STOP and VALIDATE**: trigger a dry-run pipeline from the UI; no Neo4j needed
5. All US1 tests pass

### Incremental Delivery

1. T001–T004: Setup + Foundational complete
2. T005–T009: US1 → **MVP** (no graph required)
3. T010–T015: US2 + US3 in parallel → Run browser and rule explorer work
4. T016–T023: US4 + US5 in parallel → Context tracking and community work
5. T024–T026: Polish → boundary validation + full integration smoke test

### Parallel Team Strategy

With two developers after T004:

- Developer A: US1 (T005–T009) → US2 (T010–T012)
- Developer B: US3 (T013–T015) → US4 (T016–T020) → US5 (T021–T023)

---

## Notes

- [P] tasks share no file with tasks in the same batch — safe to run concurrently
- [Story] label maps each task to the user story for traceability
- **FastMCP import (GAP-008)**: `@mcp.tool()` returns the original function unchanged; import decorated names directly; no `__wrapped__` access needed; no task required
- **Key contract violations to avoid** (enforced by T025):
  - `shell=True` in any subprocess call
  - `framework_selectbox` called from `03_rule_explorer.py`
  - `framework` kwarg omitted in `search_migration_knowledge` call (default `"Spring Boot"` applies — wrong for "all" case)
  - `direction="up"` passed to `vote_insight` instead of `delta=1`
  - `response["status"]` key used in `close_migration_context` response instead of `response["tool_status"]`
- Commit after each task or logical group; each phase checkpoint is a natural commit point
- T026 MUST be the last task — it validates the full integrated system

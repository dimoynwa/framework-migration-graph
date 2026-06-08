# Feature Specification: Streamlit Operator UI

**Feature Branch**: `006-streamlit-ui`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "Streamlit multi-page UI for Migration Oracle operators — pipeline trigger, run browser, rule explorer, context dashboard, community insights."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trigger a Pipeline Run (Priority: P1)

An operator selects a framework (e.g., `spring-boot`), specifies a source and target version, optionally checks flags for dry-run or force modes, and submits the form. The system executes the pipeline and streams its output live so the operator can see exactly what happened and whether the run succeeded.

**Why this priority**: Without the ability to launch runs, no artifacts are ever produced. All other pages depend on data created by this flow.

**Independent Test**: Can be tested standalone by filling the form and verifying that pipeline output appears line-by-line in the output area and that the exit status is shown in green (success) or red (failure).

**Acceptance Scenarios**:

1. **Given** the operator opens the Pipeline Trigger page, **When** they select a framework, enter valid from/to versions, and click Submit, **Then** pipeline output lines stream into the output area in real time and the exit code is displayed as a green success indicator when the run completes with code 0.
2. **Given** the operator submits the form, **When** the pipeline process exits with a non-zero code, **Then** the last stderr line is shown and the exit code is displayed as a red error indicator.
3. **Given** the operator opens the page, **When** no framework is selected or version fields are empty, **Then** the form prevents submission and prompts the operator to fill required fields.

---

### User Story 2 - Browse Pipeline Run Artifacts (Priority: P2)

An operator selects a completed pipeline run from a dropdown and browses its three artifact types — raw markdown changelog, filtered markdown, and structured entities JSON — in tabbed views without needing a file manager or graph client.

**Why this priority**: Provides direct visibility into what each pipeline run produced. Essential for verifying extraction quality before promoting results.

**Independent Test**: Can be tested by selecting any run from the dropdown and switching between the three tabs to confirm content renders correctly in each.

**Acceptance Scenarios**:

1. **Given** at least one pipeline run exists, **When** the operator opens the Run Browser, **Then** a dropdown lists all runs labelled as "framework from→to" and the first run is pre-selected.
2. **Given** a run is selected, **When** the operator views the Raw MD tab, **Then** the raw markdown content is rendered as formatted text.
3. **Given** a run is selected, **When** the operator views the Entities JSON tab, **Then** the entities are displayed as interactive, partially expanded JSON.
4. **Given** no pipeline runs exist, **When** the operator opens the Run Browser, **Then** an informational message is displayed and no dropdown or tabs are rendered.
5. **Given** an artifact type is unavailable for the selected run, **When** the operator opens its tab, **Then** an error message is shown in that tab only; other tabs remain functional.

---

### User Story 3 - Explore Migration Rules (Priority: P2)

An operator enters a search query (e.g., "removed API") and optionally filters by framework, then browses expandable result cards showing migration rules, their associated steps, effort levels, and verification hints.

**Why this priority**: Lets operators validate graph content and find applicable migration rules without writing Cypher queries.

**Independent Test**: Can be tested by entering any query and verifying cards appear with expected fields when results are found, and an info message appears when no results are found.

**Acceptance Scenarios**:

1. **Given** the operator types a search query and clicks Search, **When** matching rules exist, **Then** result cards appear showing rule title, type badge, change type badge, and source URL.
2. **Given** a result card with associated steps is expanded, **When** the operator views it, **Then** each step shows summary, effort badge, and verification hint.
3. **Given** the operator selects a specific framework filter, **When** they search, **Then** only rules for that framework are returned.
4. **Given** no rules match the query, **When** the search completes, **Then** an informational message "No rules found for this query" is shown.

---

### User Story 4 - Track Migration Context Progress (Priority: P3)

An operator loads or creates a migration context for a specific project and version range, then monitors and updates the status of individual migration steps — marking them complete or skipping them with a reason — and closes the context when migration is done.

**Why this priority**: Enables project-level migration tracking. Depends on rules and pipeline runs already being in the graph.

**Independent Test**: Can be tested by creating a context with a test project ID and verifying the pending steps table populates, and that marking a step complete removes it from the pending list on refresh.

**Acceptance Scenarios**:

1. **Given** the operator fills in project ID, version range, and framework and clicks "Load / Create", **When** the context is created or loaded, **Then** the context status badge, completed count, and skipped count are displayed.
2. **Given** a context is loaded with pending steps, **When** the operator clicks "Mark Complete" on a step, **Then** the step is removed from the pending table after refresh.
3. **Given** a context is loaded with pending steps, **When** the operator clicks "Skip" on a step and provides a reason, **Then** the step is removed from the pending table and the reason is recorded.
4. **Given** a context is in-progress, **When** the operator clicks "Close Context" and selects a final status and notes, **Then** the context status updates to the selected final status.
5. **Given** a context is not in-progress (complete/partial/abandoned), **When** the operator views the dashboard, **Then** the "Close Context" button is not shown.
6. **Given** a context has been loaded once in the current session, **When** the page re-renders (e.g., due to a button action), **Then** the loaded context is still shown without the operator having to re-enter project ID or version details.
7. **Given** a context is loaded and all steps have been resolved, **When** the operator views the pending steps area, **Then** an informational message is shown stating there are no pending steps, rather than an empty table.

---

### User Story 5 - Browse and Submit Community Insights (Priority: P3)

An operator reviews community-contributed insights (migration problems and solutions), votes on useful ones, and submits new insights from their own migration experience using a guided form.

**Why this priority**: Community knowledge augments the automated graph. Operators gain value from others' experience and contribute back without needing graph access.

**Independent Test**: Can be tested by loading the Community page and verifying insight cards render, a vote increments the count, and a new insight submission shows a success message.

**Acceptance Scenarios**:

1. **Given** community insights exist, **When** the operator opens the Community page, **Then** insight cards are shown with statement, solution, vote count, verified badge, and source URL.
2. **Given** an insight card is visible, **When** the operator clicks "Vote Up", **Then** an upvote (not a toggle or downvote) is recorded for that insight, the insight list is re-fetched from the data source, and the updated vote count is immediately visible.
3. **Given** the operator opens "Submit New Insight" and fills all fields, **When** they submit, **Then** a success confirmation is shown and the insight list refreshes.
4. **Given** the operator submits an insight that duplicates an existing one, **When** the submission is processed, **Then** an error message "Duplicate detected" is shown and no duplicate is created.
5. **Given** no insights exist, **When** the operator opens the Community page, **Then** an informational message is displayed and no cards are rendered.

---

### Edge Cases

- What happens when the pipeline subprocess hangs or takes longer than expected? The operator should be able to see output accumulating and the UI should not freeze.
- What happens when Neo4j is unreachable when the app starts? Pages that call graph tool functions should show a clear error message rather than crashing.
- What happens when the operator submits the pipeline trigger form multiple times rapidly? Each submission should start an independent subprocess; concurrent runs should be isolated.
- What happens when a version string contains special characters or spaces? The CLI command construction should handle these safely.
- What happens when the context ID in session state becomes stale (e.g., the node was deleted)? The dashboard should surface the error rather than silently failing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The app MUST provide five named pages accessible via sidebar navigation: Pipeline Trigger, Run Browser, Rule Explorer, Context Dashboard, and Community.
- **FR-002**: The Pipeline Trigger page MUST present a form with framework selector, from-version input, to-version input, and optional checkboxes for `--dry-run`, `--force`, `--force-extract`, and `--force-llm` flags.
- **FR-003**: The Pipeline Trigger page MUST invoke the pipeline by spawning it as an external subprocess — using the same Python interpreter that is running the app — and streaming its standard output and error line-by-line into the output display area in real time. The pipeline MUST NOT be invoked by importing its entry-point module; doing so would couple the app process to pipeline side effects and is prohibited.
- **FR-004**: The Pipeline Trigger page MUST display the process exit code with a distinct visual indicator: green for success (exit 0), red for failure (non-zero), showing the last stderr line on failure.
- **FR-005**: The Run Browser page MUST retrieve the list of completed pipeline runs on page load and cache the result for 60 seconds to avoid redundant graph queries on every UI interaction.
- **FR-006**: The Run Browser page MUST allow the operator to select a run and view its raw markdown, filtered markdown, and entities JSON artifacts in separate tabs.
- **FR-007**: The Rule Explorer page MUST accept a free-text search query and an optional framework filter, and return up to 20 matching migration rules.
- **FR-008**: The Rule Explorer page MUST render each result as an expandable card showing: rule title (or first 80 characters of statement), rule type, change type, source URL, associated steps (if any), and scopes/severity (if any). If a result does not include steps or scopes, those sections MUST be omitted silently rather than shown as empty or as an error.
- **FR-009**: The Context Dashboard page MUST allow the operator to load or create a migration context by providing project ID, version range, and framework.
- **FR-010**: The Context Dashboard page MUST display the current context status, completed step count, skipped step count, and a table of pending steps with summary, effort, automatable flag, scope, and severity columns. If there are no pending steps, an informational message MUST be shown in place of the table.
- **FR-011**: The Context Dashboard page MUST allow the operator to mark each pending step as complete or skipped (with a reason). After each such action, the pending steps list MUST be re-fetched from the data source so the table reflects the current state without a full page reload.
- **FR-012**: The Context Dashboard page MUST allow the operator to close an in-progress context by selecting a final status (complete, partial, or abandoned) and entering optional notes.
- **FR-013**: The Community page MUST display insight cards on page load showing statement, solution, vote count, verified badge, and source URL for up to 20 insights.
- **FR-014**: The Community page MUST allow the operator to cast an upvote on any insight. After the upvote is recorded, the insight list MUST be re-fetched so updated vote counts are immediately visible. Downvote and vote-toggle are out of scope.
- **FR-015**: The Community page MUST provide a "Submit New Insight" form accepting statement, solution, version string, affected class names (comma-separated), and source URL.
- **FR-016**: Every page that retrieves data MUST render an informational message in the empty-data state before rendering any widget that depends on that data.
- **FR-017**: Every call to a graph data-access function MUST be wrapped in error handling so that any failure surfaces as an inline error message to the operator. No raw exception output may reach the operator under any circumstances.
- **FR-018**: The context ID loaded on the Context Dashboard MUST be stored in a session-scoped store so that it survives page re-renders within the same browser session without the operator having to re-submit the load form.
- **FR-019**: No page may read file content directly from the filesystem by any means. All artifact content MUST arrive exclusively through the designated artifact retrieval function. All graph knowledge MUST arrive exclusively through the designated graph data-access functions. Direct filesystem reads of any kind are prohibited in page code.
- **FR-020**: All graph data-access functions MUST be called as direct in-process function calls within the app's own process. The app MUST NOT spawn or connect to a separate server process for graph access; there is no network socket, subprocess, or inter-process communication layer between the UI and the graph functions.
- **FR-021**: Pages that receive tool function responses with absent optional fields (for example, a migration rule that has no associated steps, or no scope/severity data) MUST render gracefully by omitting those sections rather than displaying an error or crashing.
- **FR-022**: The framework selector on the Pipeline Trigger page and the Rule Explorer framework filter MUST be populated from `FRAMEWORK_DISPLAY_NAMES` imported from `migration_oracle.pipeline.extractors`. The selector must display the human-readable display name (e.g. "Spring Boot") as the label. On the Pipeline Trigger page, the corresponding CLI key (e.g. "spring-boot") MUST be passed as the `--framework` argument to the subprocess. On the Rule Explorer page, the corresponding display name (e.g. "Spring Boot") MUST be passed as the filter value to the search function.
- **FR-023**: The pipeline subprocess MUST be constructed using a list of arguments (e.g. `[sys.executable, "-m", "migration_oracle.cli", "--framework", key, from_version, to_version] + flags`) and MUST NOT use `shell=True`. Shell interpolation of operator-supplied version strings is prohibited.
- **FR-024**: The Community page MUST call `vote_insight(insight_id=..., delta=1)` to record an upvote. The `delta` parameter is an integer; passing a `direction` string is incorrect and will raise a type error.

### Key Entities

- **Pipeline Run**: A completed execution of the migration extraction pipeline for a specific framework and version pair. Has framework key, from-version, to-version, and a set of artifact types (raw markdown, filtered markdown, entities JSON).
- **Migration Rule**: A graph node representing a breaking change or migration requirement. Has title, statement, rule type, change type, source URL, and optional associated steps and scope/severity data.
- **Migration Step**: A sub-unit of a migration rule describing a discrete action. Has summary, effort level, automatable flag, verification hint, scope, and severity.
- **Migration Context**: A project-scoped record tracking which steps have been completed, skipped, or remain pending for a given migration effort. Has project ID, version range, framework, status, and links to step outcomes.
- **Community Insight**: A user-contributed migration problem/solution pair. Has statement, solution, version tag, affected classes, source URL, vote count, and verified flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can launch a pipeline run and see the first output line within 3 seconds of clicking Submit, without any page reload.
- **SC-002**: An operator can navigate to any of the five pages and see content (or an appropriate empty-state message) in under 2 seconds from page selection.
- **SC-003**: 100% of graph tool function errors are surfaced as inline error messages; zero raw exception tracebacks are shown to the operator under any conditions.
- **SC-004**: An operator can find migration rules related to a known topic in under 30 seconds using the Rule Explorer search.
- **SC-005**: An operator can mark all pending migration steps for a context as complete or skipped without leaving the Context Dashboard page.
- **SC-006**: The run list on the Run Browser reflects runs completed in the last 60 seconds after a manual page reload (cache TTL boundary).
- **SC-007**: An operator can submit a community insight and receive confirmation or a duplicate error within 5 seconds of clicking Submit.

## Assumptions

- The app is served locally or on a trusted internal network; no user authentication or role-based access control is required for this version.
- Neo4j environment variables (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`) are configured in the shell environment before the app is started.
- The registered extractor keys (framework names shown in selectors) are available from the same module that the pipeline CLI uses and do not require a separate API call.
- All graph tool functions (`list_pipeline_runs`, `get_artifact_content`, `search_migration_knowledge`, `create_migration_context`, `get_pending_steps`, `update_step_status`, `close_migration_context`, `get_community_insights`, `vote_insight`, `submit_migration_insight`) are already implemented and tested independently; the UI spec does not cover their internal behavior.
- A single operator uses the app at a time per running instance; multi-user concurrency within a single Streamlit process is out of scope.
- Mobile and tablet viewports are out of scope; the app is designed for desktop browser use.
- The `streamlit` package version `>=1.35` is available in the project's dependency set.

# Tasks: PaysafeMigrationOracle MCP Server

**Input**: Design documents from `/specs/005-mcp-server/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/005-mcp-server.md ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on each other)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `mcp/` package skeleton so all subsequent tasks have a valid import tree.

- [x] T001 Create `migration_oracle/mcp/` package structure: `__init__.py`, `tools/__init__.py`, `graph/__init__.py`, `graph/queries/__init__.py`, `skills/` directory, and `tests/mcp/__init__.py`

**Checkpoint**: `python -c "import migration_oracle.mcp"` succeeds with no errors.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config patch + all `graph/queries/` modules. These are the lowest-level building blocks. No tool module can be implemented until the corresponding query module exists.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Add `MCP_STATELESS_HTTP: bool = _parse_bool_flag(_optional("MCP_STATELESS_HTTP", "false"))` to `migration_oracle/config.py` (single line addition per research.md §5)

- [x] T003 [P] Implement `migration_oracle/mcp/graph/queries/upgrade.py` — `analyze_upgrade_path` Cypher (with `OPTIONAL MATCH` joins to `MigrationStep` via `REQUIRES_STEP`, `BreakingScope` via `HAS_SCOPE`, `OpenRewriteRecipe` via `AUTOMATED_BY`; `scope_filter` / `min_severity` post-filter WITH clause) and `build_recipe_plan` Cypher (step-level auto/manual track split with `OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)` and `OPTIONAL MATCH (s)-[ab_s:AUTOMATED_BY]->(rec_s:OpenRewriteRecipe)`) per plan.md P-1.1

- [x] T004 [P] Implement `migration_oracle/mcp/graph/queries/deprecation.py` — `resolve_deprecation` Cypher (deprecated_in, removed_in, replaced_by one hop, linked rules) and `entity_evolution` Cypher (REPLACED_BY chain up to 5 hops) verbatim from `docs/graph-mcp-skills-and-paysafe-resolution.md §7` per plan.md P-1.2

- [x] T005 [P] Implement `migration_oracle/mcp/graph/queries/search.py` — `bm25_search(query, index, top_k) -> list[str]`, `vector_search(embedding, index, top_k, min_similarity) -> list[str]` (catches `ClientError` → returns `[]` for Memgraph degraded mode), and `hydrate_nodes(element_ids) -> list[dict]` per plan.md P-1.3

- [x] T006 [P] Implement `migration_oracle/mcp/graph/queries/schema.py` — `MUTATION_KEYWORDS` list (`CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`) + `CALL db` prefix check; `check_mutation(query: str) -> str | None` (case-insensitive); `execute_read_cypher(query, params) -> list[dict]` using `read_session()`; `GRAPH_SCHEMA_MD: str` static constant per plan.md P-1.4

- [x] T007 [P] Implement `migration_oracle/mcp/graph/queries/community.py` — `submit_insight` Cypher (create `CommunityInsight` node, link to `Version`, merge entity nodes), near-duplicate BM25 check (cosine > 0.92 returns existing elementId), `query_insights` Cypher, `vote_insight` Cypher (increment/decrement votes), `verify_insight` Cypher (set `verified=true`) verbatim from `docs/graph-mcp-skills-and-paysafe-resolution.md §7` per plan.md P-1.5

- [x] T008 [P] Implement `migration_oracle/mcp/graph/queries/context.py` — `create_or_get_context` MERGE Cypher (key: `projectId + fromVersion + toVersion`; all other props in `ON CREATE SET`; `UPGRADES_FROM` / `UPGRADES_TO` MERGE edges); `get_pending_steps` version-range Cypher (uses `UPGRADES_FROM`/`UPGRADES_TO` + `sortableVersion` range — NOT single toVersion — with `AUTOMATED_BY` join for `recipeId` and `REQUIRES` edge collect for `requires`; use `docs/migration-oracle-redesign.md §6.2` as the authoritative Cypher source — do NOT use the first Cypher block in plan.md P-1.6 which contains a single-toVersion bug; the plan.md P-1.6 prose description is correct but its inline Cypher is superseded by redesign §6.2); `record_step_outcome` write Cypher (tracks `completedSteps`, `skippedSteps`, AND `failedSteps`); `auto_close_write` Cypher (sets `status='complete'`, `completedAt=datetime()`); `get_steps_for_scope_tier` Cypher per plan.md P-1.6

- [x] T009 [P] Implement `migration_oracle/mcp/graph/queries/artifacts.py` — `list_pipeline_runs` Cypher (`MATCH (v:Version) WHERE v.rawMdPath IS NOT NULL`; returns framework, version, rawMdPath, filteredMdPath, entitiesJsonPath ordered by framework + sortableVersion) and `get_version_artifact_path` Cypher (`MATCH (v:Version {framework, version})` returning three path properties) per plan.md P-1.7. **Data contract note**: `Version` nodes have a single `version` property; if `v.fromVersion` is not present on the node (spec-002 did not store it), drop `from_version` from `ArtifactRunRecord` and return only `version` (the to_version of the run). Align with the spec-002 pipeline team if `fromVersion` storage was intended — do not block T009 on this question.

**Checkpoint**: All 7 query modules importable; `check_mutation("CREATE ...")` returns `"CREATE"`.

---

## Phase 3: User Story 1 — Migration Tool Discovery + Core Upgrade Tools (Priority: P1) 🎯 MVP

**Goal**: An AI agent connects to the server, discovers tools, and calls `analyze_upgrade_path` / `build_recipe_plan` to get structured migration rules with step and scope arrays.

**Independent Test**: `uv run pytest tests/mcp/test_upgrade.py -v` — all 6 tests pass with mocked graph driver.

### Implementation for User Story 1

- [x] T010 [P] [US1] Implement `migration_oracle/mcp/tools/upgrade.py` — register `@mcp.tool` for `analyze_upgrade_path` (full parameter signature including frozen params + new `scope_filter: list[str] = []` and `min_severity: str | None = None`; returns `UpgradePlanResult`) and `build_recipe_plan` (frozen params `current_version`, `target_version`, `framework`, `user_entities`, `auto_only`, `classification` + new `scope_filter`, `min_severity`; returns `RecipePlanResult` with `auto_track`, `manual_track`, `fallback_to_rule_cards`); call functions from `mcp.graph.queries.upgrade`; no inline Cypher (Contract C / FR-041) per plan.md P-2.1

- [x] T011 [P] [US1] Implement `tests/mcp/test_upgrade.py` — 6 tests: `test_analyze_upgrade_path_empty_graph` (empty rules, no error), `test_analyze_upgrade_path_with_scope_filter` (only matching-scope rules returned), `test_analyze_upgrade_path_no_migration_steps` (steps=[], scopes=[] on pre-redesign mock — Contract G(b)), `test_build_recipe_plan_no_automated_by` (MigrationStep nodes present but zero AUTOMATED_BY edges: all steps in manual track, auto track empty — NOT error; first-release expected behavior), `test_build_recipe_plan_no_migration_steps` (no MigrationStep nodes at all: falls back to rule-level cards; Contract G(c)), `test_build_recipe_plan_action_step_in_rule_card` (no MigrationStep nodes: assert manual track card dict contains `"action_step"` key with the non-empty value from the MigrationRule node's `actionStep` property — Contract G(c) explicit assertion) per plan.md P-5.1

**Checkpoint**: `uv run pytest tests/mcp/test_upgrade.py -v` — 6/6 pass.

---

## Phase 4: User Story 2 — Four-Loop Migration Harness (Priority: P1)

**Goal**: Agent creates a `MigrationContext`, queries by scope tier, routes steps to auto/manual tracks, records outcomes, and auto-closes the context when all steps are resolved.

**Independent Test**: `uv run pytest tests/mcp/test_context.py tests/mcp/test_skill_harness.py tests/mcp/test_deprecation.py -v` — all 18 tests pass with mocked graph.

### Implementation for User Story 2

- [x] T012 [P] [US2] Implement `migration_oracle/mcp/tools/context.py` — register 5 `@mcp.tool` decorators: `create_migration_context` (calls MERGE Cypher; returns `MigrationContextResult` with `created=True/False`); `get_pending_steps` (calls version-range query; returns `PendingStepsResult`); `update_step_status` (param named `reason: str = ""` per redesign §6.3; records outcome via `record_step_outcome`; then in application code checks `get_pending_steps` and if empty calls `auto_close_write` + sets `context_auto_closed=True` in return; returns `StepStatusResult`); `get_steps_for_scope_tier` (returns `ScopeTierResult`); `close_migration_context` (returns `CloseContextResult` with `tool_status: Literal["ok"]` + `migration_status: str` as distinct fields — NOT a single `status` field per plan.md P-2.6 constraint) per plan.md P-2.6

- [x] T013 [P] [US2] Implement `migration_oracle/mcp/tools/deprecation.py` — register `@mcp.tool` for `resolve_deprecation` (returns `DeprecationResult`) and `entity_evolution` (returns `EntityEvolutionTimeline` with chain up to 5 hops); call functions from `mcp.graph.queries.deprecation` per plan.md P-2.2

- [x] T014 [P] [US2] Write `migration_oracle/mcp/skills/framework_migration_main.md` — NEW four-loop harness (Increment 3, FR-043); NOT a copy of the pre-redesign skill; must implement all four loops from `docs/migration-oracle-redesign.md §7`: Loop I (create_migration_context or load existing; stop if complete; gate on version-map), Loop II (4 tiers: Tier 1 api-surface/high+critical → Tier 2 runtime/medium+ → Tier 3 config+build/all → Tier 4 test/all; skip guard on ctx.queriedEntities; Paysafe concurrent), Loop III (step routing: auto / no-AUTOMATED_BY → manual / prompted-auto / manual / design-gate / blocked / rollback; update_step_status after every step), Loop IV (submit_migration_insight for deviating fixes; close_migration_context); decision tables for all four loops MUST appear verbatim (FR-037) per plan.md P-3.4

- [x] T015 [P] [US2] Copy `migration_oracle/mcp/skills/framework_migration_scanning.md` from existing skill source (no content changes) per plan.md P-3.1

- [x] T016 [P] [US2] Copy `migration_oracle/mcp/skills/framework_migration_plan_format.md` from existing skill source (no content changes) per plan.md P-3.2

- [x] T017 [P] [US2] Copy `migration_oracle/mcp/skills/framework_migration_version_map.md` from existing skill source (no content changes) per plan.md P-3.3

- [x] T018 [P] [US2] Implement `tests/mcp/test_context.py` — 8 tests: `test_create_migration_context_new` (created=True), `test_create_migration_context_idempotent` (second call returns existing, created=False), `test_get_pending_steps_ordered` (severity descending order), `test_update_step_status_completed` (step in completedSteps; `reason` param accepted), `test_update_step_status_auto_close` (last step → context_auto_closed=True, application code not trigger), `test_get_steps_for_scope_tier` (correct scope/severity filter), `test_close_migration_context` (completedAt set, CloseContextResult shape with tool_status + migration_status distinct), `test_context_full_round_trip` (E2E: create_migration_context → get_pending_steps (assert full queue) → update_step_status(completed, step-1) → update_step_status(skipped, step-2) → get_pending_steps again (assert step-1 and step-2 absent, remaining steps present) → close_migration_context (assert migration_status="partial", completedAt set)) per plan.md P-5.6

- [x] T019 [P] [US2] Implement `tests/mcp/test_skill_harness.py` — 7 tests: `test_loop_i_resume_skips_completed_steps` (redesign §9 Increment 3 validation: call create_migration_context with projectId "proj-A" to create context with completedSteps=["step-1","step-2"]; call create_migration_context again with same projectId "proj-A" — assert idempotent (created=False, same context_id returned); then call get_pending_steps — assert result contains ONLY ["step-3","step-4"], NOT ["step-1","step-2"]; this validates Loop I re-invocation with same projectId correctly resumes without re-queuing resolved steps), `test_context_resume_correct_completed_steps` (no re-extension of already-completed IDs after second create_migration_context call), `test_context_resume_preserves_skipped_steps` (skippedSteps excluded from pending after Loop I re-entry), `test_context_resume_preserves_failed_steps` (failedSteps excluded from pending), `test_context_auto_close_on_resume_if_all_resolved` (update_step_status for last step → context_auto_closed=True, context_status="complete", no spurious second write), `test_loop_i_stops_on_complete_context` (status="complete" → zero calls to analyze_upgrade_path / get_steps_for_scope_tier), `test_context_resume_no_duplicate_steps` (broader: seed with completedSteps+skippedSteps+failedSteps each containing some steps from the full set; verify get_pending_steps returns only the unresolved remainder — no step appears in more than one exclusion list) per plan.md P-5.10

- [x] T020 [P] [US2] Implement `tests/mcp/test_deprecation.py` — 3 tests: `test_resolve_deprecation_found` (deprecated_in, removed_in, replaced_by correct), `test_resolve_deprecation_not_found` (not_found response), `test_entity_evolution_chain` (up to 5 hops traced correctly) per plan.md P-5.2

**Checkpoint**: `uv run pytest tests/mcp/test_context.py tests/mcp/test_skill_harness.py tests/mcp/test_deprecation.py -v` — 18/18 pass.

---

## Phase 5: User Story 3 — Hybrid Search + Community Knowledge Loop (Priority: P2)

**Goal**: Agent uses BM25+vector hybrid search to find migration knowledge, and submits community insights after resolving an issue manually.

**Independent Test**: `uv run pytest tests/mcp/test_search.py tests/mcp/test_community.py -v` — all 7 tests pass with mocked BM25/vector/graph calls.

### Implementation for User Story 3

- [x] T021 [P] [US3] Implement `_model` singleton and `get_embedding_model()` in `migration_oracle/mcp/tools/search.py` — add module-level sentinel `_model: SentenceTransformer | None = None`; implement `get_embedding_model() -> SentenceTransformer` with exact check-then-assign pattern: `global _model` / `if _model is None: _model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)` / `return _model`; variable MUST be named `_model` (Contract E / FR-017); `SentenceTransformer(...)` MUST NOT appear outside this function; model name read from `config.SENTENCE_TRANSFORMERS_MODEL` (default `all-mpnet-base-v2`)

- [x] T022 [P] [US3] Implement `@mcp.tool` handlers for `search_migration_knowledge` and `search_openrewrite_recipes` in `migration_oracle/mcp/tools/search.py` — call `get_embedding_model()` (T021) to encode query; issue BM25 (`mcp.graph.queries.search.bm25_search`) + vector (`mcp.graph.queries.search.vector_search`) calls in parallel via `asyncio.gather()` + ThreadPoolExecutor; RRF fusion (k=60); hydrate top N nodes via `mcp.graph.queries.search.hydrate_nodes`; return `SearchResult`; for `search_openrewrite_recipes`: SearchHit.node_type always `"OpenRewriteRecipe"`, rule_type always empty, statement = recipe description field; depends on T021 per plan.md P-2.3

- [x] T023 [P] [US3] Implement `migration_oracle/mcp/tools/community.py` — register `@mcp.tool` for `submit_migration_insight` (near-duplicate detection before write; returns `InsightSubmitResult`), `get_community_insights` (read session; returns `InsightQueryResult`), `vote_insight` (write session; increments/decrements votes; returns `VoteResult`), `verify_insight` (write session; sets verified=true; returns `VerifyResult`); call functions from `mcp.graph.queries.community` per plan.md P-2.5

- [x] T024 [P] [US3] Implement `tests/mcp/test_search.py` — 3 tests: `test_hybrid_search_rrf_fusion` (BM25 + vector hits merged by RRF; correct top-k), `test_hybrid_search_vector_unavailable` (ClientError on vector → BM25-only result, no exception raised — Memgraph degraded mode), `test_embedding_model_loaded_once` (get_embedding_model() called 3 times → `SentenceTransformer.__init__` called exactly once — SC-007) per plan.md P-5.3

- [x] T025 [P] [US3] Implement `tests/mcp/test_community.py` — 4 tests: `test_submit_insight_new` (CommunityInsight node created, status="ok"), `test_submit_insight_duplicate_detected` (duplicate suppressed, status="duplicate", existing id returned), `test_vote_insight_increment` (votes incremented by delta), `test_verify_insight` (verified=true set on node) per plan.md P-5.5

**Checkpoint**: `uv run pytest tests/mcp/test_search.py tests/mcp/test_community.py -v` — 7/7 pass.

---

## Phase 6: User Story 4 — Paysafe Internal Dependency Resolution (Priority: P2)

**Goal**: Agent resolves a `com.paysafe.*` dependency by delegating to the resolver module with zero extra logic.

**Independent Test**: `uv run pytest tests/mcp/test_paysafe_tool.py -v` — both tests pass including the import-boundary assertion.

### Implementation for User Story 4

- [x] T026 [P] [US4] Implement `migration_oracle/mcp/tools/paysafe.py` — import ONLY `from migration_oracle.paysafe.resolver import resolve` (Contract A — no findit, no gitlab, no other paysafe internal); register `@mcp.tool` for `resolve_paysafe_dependency_by_service_name` with full parameter set (service_name, target_version, framework, allow_latest_overall, max_tags, pinned_version, pinned_tag); body is `return resolve(service_name=service_name, ...)` — no additional logic; returns `PaysafeDependencyResult` (pass-through, no wrapping) per plan.md P-2.7

- [x] T027 [P] [US4] Implement `tests/mcp/test_paysafe_tool.py` — 2 tests: `test_resolve_delegates_to_resolver` (mock `migration_oracle.paysafe.resolver.resolve`; call the MCP tool; assert resolve() was called with exactly the args the tool received and that the tool's return value is the resolver's return value unmodified — no extra keys, no wrapped dict), `test_resolve_no_findit_import` (import `migration_oracle.mcp.tools.paysafe` and assert that `findit` is NOT in `dir()` or `sys.modules` for that module's namespace — Contract A) per plan.md P-5.7

**Checkpoint**: `uv run pytest tests/mcp/test_paysafe_tool.py -v` — 2/2 pass.

---

## Phase 7: User Story 5 — Safe Custom Cypher Execution (Priority: P3)

**Goal**: Power user runs read-only Cypher queries; all mutation keywords are blocked before any graph contact.

**Independent Test**: `uv run pytest tests/mcp/test_schema.py -v` — all 10 tests pass including 7 mutation-blocking tests.

### Implementation for User Story 5

- [x] T028 [P] [US5] Implement `migration_oracle/mcp/tools/schema.py` — register `@mcp.tool` for `get_graph_schema` (returns `GraphSchema` with static schema markdown from `mcp.graph.queries.schema.GRAPH_SCHEMA_MD` — no Cypher executed, FR-018) and `execute_custom_cypher` (Layer 1: call `check_mutation(query)` before any graph contact; if blocked return `CypherResult(status="blocked", blocked_keyword=kw, rows=[], row_count=0)`; Layer 2: open `read_session()` — both layers required per Contract D / FR-019; returns `CypherResult`) per plan.md P-2.4

- [x] T029 [P] [US5] Implement `tests/mcp/test_schema.py` — 8 tests: `test_execute_custom_cypher_safe` (MATCH query executes and returns rows), `test_execute_custom_cypher_blocks_create` (CREATE rejected before graph contact — mock asserts driver.session never called), `test_execute_custom_cypher_blocks_merge` (MERGE rejected before graph contact), `test_execute_custom_cypher_blocks_set` (SET rejected), `test_execute_custom_cypher_blocks_delete` (DELETE rejected), `test_execute_custom_cypher_blocks_remove` (REMOVE rejected), `test_execute_custom_cypher_blocks_drop` (DROP rejected), `test_execute_custom_cypher_blocks_call_db` (`CALL db.index.fulltext` rejected before graph contact), `test_execute_custom_cypher_case_insensitive` (`create` lowercase rejected), `test_get_graph_schema_no_cypher` (schema returned with zero graph driver calls) per plan.md P-5.4

**Checkpoint**: `uv run pytest tests/mcp/test_schema.py -v` — 10/10 pass including all mutation-blocking assertions (SC-003). Note: 7 distinct blocked-keyword tests cover CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL db.

---

## Phase 8: User Story 6 — Server Startup + Full 21-Tool Inventory (Priority: P1)

**Goal**: Server starts in the correct order (config → connectivity → indexes), registers all 21 tools and 4 skill resources, fails fast on bad connectivity, and continues in degraded mode on Memgraph DDL failure.

**Independent Test**: `uv run pytest tests/mcp/test_server.py tests/mcp/test_artifacts.py -v` — all 10 tests pass.

### Implementation for User Story 6

- [x] T030 [P] [US6] Implement `migration_oracle/mcp/tools/artifacts.py` — register `@mcp.tool` for `list_pipeline_runs` (calls `list_pipeline_runs` Cypher; returns `ArtifactListResult`) and `get_artifact_content` (Contract B enforced: caller supplies `framework, from_version, to_version, artifact_type`; tool queries Version node for path via `get_version_artifact_path`; `ARTIFACT_TYPE_MAP = {"raw_md": "rawMdPath", "filtered_md": "filteredMdPath", "entities_json": "entitiesJsonPath"}`; tool opens file at graph-sourced path only; returns `ArtifactContentResult` with `path_resolved` field; no direct `path` parameter accepted from caller) per plan.md P-2.8

- [x] T031 [P] [US6] Implement `migration_oracle/mcp/tools/install.py` — register `@mcp.tool` for `install_migration_skill`; copies `migration_oracle/mcp/skills/*.md` to Cursor or Claude Code skills directory; when `target="auto"` detects environment (`.cursor/` → Cursor; `~/.claude/` or `.claude/` → Claude Code); returns `InstallSkillResult` with `status`, `target`, `installed_paths: list[str]`, `message` per plan.md P-2.9

- [x] T032 [P] [US6] Implement `tests/mcp/test_artifacts.py` — 5 tests: `test_list_pipeline_runs` (runs with rawMdPath returned), `test_get_artifact_content_raw_md` (mock Version node returns path "/data/run.md"; tool queries graph first, then reads the file at that graph-resolved path — assert `Path("/data/run.md").read_text` called, NOT any caller-supplied path), `test_get_artifact_content_invalid_type` (error returned without any graph query — assert driver not called), `test_get_artifact_content_missing_version` (graph returns None → not_found response without touching filesystem), `test_get_artifact_content_no_direct_path_param` (inspect `get_artifact_content.__annotations__` or signature — assert no parameter named `path` exists — Contract B) per plan.md P-5.8

- [x] T033 [US6] Implement `migration_oracle/mcp/server.py` — `FastMCP("PaysafeMigrationOracle")`; import and register tools from all 9 tool modules (upgrade, deprecation, search, schema, community, context, paysafe, artifacts, install); register 4 skill resources at `skill://framework-migration/main`, `skill://framework-migration/scanning`, `skill://framework-migration/plan-format`, `skill://framework-migration/version-map` by reading corresponding files from `migration_oracle/mcp/skills/` at startup; register 1 migration workflow prompt; implement `startup()`: (1) config already loaded at import time, (2) verify connectivity via `driver.session().run("RETURN 1")` — raises and exits on `ServiceUnavailable`, (3) `ensure_indexes(driver)` — logs DDL failures and continues on Memgraph; `startup()` MUST be called before `mcp.run()`; transport selection: `stdio` → `mcp.run(transport="stdio")`, `sse` → bind to `config.MCP_HOST:config.MCP_PORT`, `streamable-http` → add `stateless_http=config.MCP_STATELESS_HTTP`; **NOT [P]** — depends on T010, T012, T013, T014, T015, T016, T017, T022, T023, T026, T028, T030, T031 per plan.md P-4.1

- [x] T034 [US6] Implement `tests/mcp/test_server.py` — 5 tests: `test_startup_sequence_order` (mock driver and ensure_indexes; assert connectivity check (`driver.session().run("RETURN 1")`) is called BEFORE `ensure_indexes` — verify call order via mock call_args_list), `test_startup_exits_on_connectivity_failure` (`ServiceUnavailable` raised by mocked driver → startup raises before accepting tool calls), `test_startup_continues_on_index_ddl_failure` (DDL ClientError from mocked ensure_indexes → startup logs warning and does NOT raise), `test_tool_count` (after server init, `len(mcp.list_tools())` == 21 — SC-001), `test_skill_resources_registered` (after server init, call `mcp.list_resources()`; assert all four URIs present: `skill://framework-migration/main`, `skill://framework-migration/scanning`, `skill://framework-migration/plan-format`, `skill://framework-migration/version-map`; assert count == 4 — FR-030) per plan.md P-5.9

**Checkpoint**: `uv run pytest tests/mcp/test_server.py tests/mcp/test_artifacts.py -v` — 10/10 pass; `test_tool_count` confirms exactly 21 tools; `test_skill_resources_registered` confirms all 4 skill URIs.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Integration smoke-test and coverage validation across all stories.

- [x] T035 [P] Run `uv run pytest tests/mcp/ -v --tb=short` — full suite passes (53 tests: 6+8+7+3+3+4+2+10+5+5 across all 10 test files); address any remaining failures
- [x] T036 [P] Run `uv run pytest tests/mcp/ --cov=migration_oracle/mcp --cov-report=term-missing` — review coverage gaps; verify no inline Cypher in `mcp/tools/` (Contract C / FR-041) and no `os.environ` calls in `mcp/` (Contract F / FR-042)

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup (T001)
    └─► Phase 2: Foundational — T002–T009 (T002 then T003–T009 all parallel)
              └─► Phase 3: US1  — T010–T011 [P with each other]
              └─► Phase 4: US2  — T012–T020 [P with each other]
              └─► Phase 5: US3  — T021 then T022 (singleton first); T021–T025 otherwise [P]
              └─► Phase 6: US4  — T026–T027 [P with each other]
              └─► Phase 7: US5  — T028–T029 [P with each other]
              └─► Phase 8: US6  — T030–T032 [P], then T033 (after ALL tools done), then T034
    └─► Phase 9: Polish — T035–T036
```

### User Story Dependencies

| Story | Depends on | Notes |
|---|---|---|
| US1 (P1) | Phase 2 complete | T010–T011 fully parallel with US2–US6 tool work |
| US2 (P1) | Phase 2 complete | T012–T020 fully parallel with US1, US3–US6 tool work |
| US3 (P2) | Phase 2 complete | T021 (singleton) before T022 (handlers); T023–T025 parallel with T022 |
| US4 (P2) | Phase 2 complete | T026–T027 fully parallel with all other stories |
| US5 (P3) | Phase 2 complete | T028–T029 fully parallel with all other stories |
| US6 (P1) | T010, T012, T013, T014, T015, T016, T017, T022, T023, T026, T028, T030–T031 | T033 (server.py) is the synchronisation point; T034 depends on T033 |

### Critical Path

`T001 → T002 → T008 (redesign §6.2 context Cypher) → T012 (context.py) + T014–T017 (skill files) → T033 (server.py) → T034 (test_server.py)`

---

## Parallel Execution Examples

### Phase 2: All graph/queries/ modules in parallel

```bash
# 7 query modules simultaneously — independent files, no cross-imports:
Task: "T003 migration_oracle/mcp/graph/queries/upgrade.py"
Task: "T004 migration_oracle/mcp/graph/queries/deprecation.py"
Task: "T005 migration_oracle/mcp/graph/queries/search.py"
Task: "T006 migration_oracle/mcp/graph/queries/schema.py"
Task: "T007 migration_oracle/mcp/graph/queries/community.py"
Task: "T008 migration_oracle/mcp/graph/queries/context.py"
Task: "T009 migration_oracle/mcp/graph/queries/artifacts.py"
```

### Phases 3–7: All tool modules in parallel after Phase 2

```bash
# 10 tool modules + skill files simultaneously:
Task: "T010 migration_oracle/mcp/tools/upgrade.py"
Task: "T013 migration_oracle/mcp/tools/deprecation.py"
Task: "T014 migration_oracle/mcp/skills/framework_migration_main.md"
Task: "T021 migration_oracle/mcp/tools/search.py (_model singleton)"
Task: "T022 migration_oracle/mcp/tools/search.py (tool handlers — after T021)"
Task: "T023 migration_oracle/mcp/tools/community.py"
Task: "T026 migration_oracle/mcp/tools/paysafe.py"
Task: "T028 migration_oracle/mcp/tools/schema.py"
Task: "T030 migration_oracle/mcp/tools/artifacts.py"
Task: "T031 migration_oracle/mcp/tools/install.py"
```

### Phases 3–7: All test files in parallel (alongside tool modules)

```bash
# 10 test files simultaneously (each after its tool module):
Task: "T011 tests/mcp/test_upgrade.py"
Task: "T018 tests/mcp/test_context.py"
Task: "T019 tests/mcp/test_skill_harness.py"
Task: "T020 tests/mcp/test_deprecation.py"
Task: "T024 tests/mcp/test_search.py"
Task: "T025 tests/mcp/test_community.py"
Task: "T027 tests/mcp/test_paysafe_tool.py"
Task: "T029 tests/mcp/test_schema.py"
Task: "T032 tests/mcp/test_artifacts.py"
```

---

## Implementation Strategy

### MVP (User Story 1 + Unit Tests)

1. Complete **Phase 1**: Setup (T001)
2. Complete **Phase 2**: T002 → T003 + T008 in parallel (minimum for US1 unit tests)
3. Complete **Phase 3**: T010 + T011 in parallel
4. **VALIDATE**: `uv run pytest tests/mcp/test_upgrade.py -v` — all 6 pass
5. This proves the Cypher layer + tool handler layer + backward compat (no-MigrationStep path, actionStep fallback) work.

### Incremental Delivery

1. Phase 1 + Phase 2 → Graph query layer complete
2. Phase 3 → US1 tools unit-tested (upgrade tools including actionStep assertion)
3. Phase 4 → US2 tools unit-tested (context + harness skill + E2E round-trip)
4. Phase 5 → US3 tools unit-tested (search singleton + handlers + community)
5. Phase 6 + 7 → US4 + US5 unit-tested
6. Phase 8 → T030–T032 parallel; then T033 (server.py unifies all); then T034 (21 tools + 4 resource URIs)
7. Phase 9 → Full suite + coverage

### Key Constraints Checklist (verify before T033)

| Constraint | Task | Verify |
|---|---|---|
| No inline Cypher in tool handlers | T010–T013, T022–T023, T026, T028, T030–T031 | `grep -r "MATCH\|MERGE\|RETURN" migration_oracle/mcp/tools/` returns nothing |
| `_model` singleton exact variable name and check-then-assign | T021 | `grep "_model" migration_oracle/mcp/tools/search.py` — only one assignment |
| `SentenceTransformer(...)` only inside `get_embedding_model()` | T021 | `grep "SentenceTransformer(" migration_oracle/mcp/tools/search.py` — one line only |
| MERGE key-only, ON CREATE SET for all other props | T008 | Review context.py MERGE Cypher |
| Auto-close in application code, not Cypher trigger | T012 | Handler calls `get_pending_steps` then `auto_close_write`; no ON MATCH SET |
| Artifact paths from Version node only; no caller path param | T030 | No `path` parameter in `get_artifact_content` signature; T032 tests it |
| `paysafe.py` imports only `resolver.resolve` | T026 | `grep "import" migration_oracle/mcp/tools/paysafe.py` — one line only |
| execute_custom_cypher: keyword check before driver contact + READ session | T028 | T029 mocks assert driver.session never called on blocked queries |
| All new node joins use OPTIONAL MATCH | T003, T008 | Review Cypher in upgrade.py and context.py |
| No `os.environ` in `mcp/` | All T010–T033 | `grep -r "os.environ\|os.getenv" migration_oracle/mcp/` returns nothing |
| `close_migration_context` uses `tool_status` + `migration_status` distinct | T012 | Check CloseContextResult fields in T018 `test_close_migration_context` |
| 4 skill resource URIs registered | T033 | T034 `test_skill_resources_registered` asserts all 4 |

---

## Gap Review Applied

Fixes applied from gap review (5 changes):

| Gap | Fix |
|---|---|
| TASK-GAP-003 | Split old T021 into T021 (singleton + get_embedding_model) and T022 (search tool handlers); all downstream tasks renumbered +1 |
| TASK-GAP-006 | T018 gains 8th test `test_context_full_round_trip`: create → get_pending_steps → update×2 → get_pending_steps (verify excluded) → close_migration_context (verify status) |
| TASK-GAP-009 | T034 gains 5th test `test_skill_resources_registered`: verifies all 4 skill:// URIs are in resources/list after server init |
| TASK-GAP-011(c) | T011 gains 6th test `test_build_recipe_plan_action_step_in_rule_card`: explicitly asserts manual track card contains `"action_step"` key with non-empty value from MigrationRule.actionStep |
| TASK-GAP-013 | T019 gains `test_loop_i_resume_skips_completed_steps` as first test: calls create_migration_context twice with same projectId (verifying Loop I re-entry idempotency), then asserts get_pending_steps excludes already-completed steps |

---

## Notes

- `[P]` tasks share no file path and have no incomplete dependencies — safe to launch concurrently
- Story labels map to spec.md user stories: US1–US6
- T033 (`server.py`) is the **only non-parallel task** in Phases 3–8 — it is the synchronisation point
- T021 (singleton) must complete before T022 (handlers) in Phase 5; both are in the same file
- Unit tests (T011, T018–T020, T024–T025, T027, T029, T032) use mocked graph driver; no running Neo4j required
- Integration tests in `tests/mcp/test_context.py` marked `@pytest.mark.integration` require a seeded graph
- Commit after each phase checkpoint; do not proceed to T033 until all tool modules pass their unit tests

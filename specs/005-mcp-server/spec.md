# Feature Specification: PaysafeMigrationOracle MCP Server

**Feature Branch**: `005-mcp-server`

**Created**: 2026-06-07

**Status**: Draft

**Input**: User description: "MCP Server module (migration_oracle/mcp/) implementing PaysafeMigrationOracle with 21 tools, 4 skill resources, 1 prompt, stdio/SSE/HTTP transport, four-loop agent harness skill, and backward-compatible redesign"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — AI Agent Discovers and Calls Migration Tools (Priority: P1)

An AI agent (Claude Code, Cursor, or a custom harness) connects to the MCP server and uses tool discovery to find the 21 available migration tools. The agent calls `analyze_upgrade_path` with a framework name, current version, and target version to receive a list of lifecycle alerts, migration rules, and optional recipe metadata. The agent uses the result to guide a developer through the upgrade.

**Why this priority**: This is the core value proposition of the server. Without tool discovery and `analyze_upgrade_path`, no agent workflow is possible.

**Independent Test**: Connect an MCP client to the running server; list tools; call `analyze_upgrade_path` for a known framework pair; verify structured rules are returned.

**Acceptance Scenarios**:

1. **Given** the MCP server is running and a client connects via stdio, **When** the client issues `tools/list`, **Then** 21 tools, 4 resources, and 1 prompt are returned with correct schemas.
2. **Given** the server is connected, **When** `analyze_upgrade_path` is called with `framework="wildfly"`, `current_version="26"`, `target_version="30"` and no `scope_filter` or `min_severity`, **Then** migration rules are returned in the same format as the pre-redesign baseline.
3. **Given** `scope_filter=["api-surface"]` and `min_severity="high"` are supplied, **When** `analyze_upgrade_path` is called, **Then** only rules with at least one `HAS_SCOPE` edge matching `api-surface` and severity ≥ high are included in the response.
4. **Given** no `MigrationStep` or `BreakingScope` nodes exist in the graph (pre-redesign data), **When** `analyze_upgrade_path` is called in JSON format, **Then** each rule contains `steps: []` and `scopes: []` — not an error.

---

### User Story 2 — Agent Builds and Executes a Migration Plan via Four-Loop Harness (Priority: P1)

An AI agent running the `framework_migration_main.md` skill creates a migration context for a project, queries the graph in scope-gated tiers, executes steps on auto or manual tracks, and records the final status. The developer sees step cards with instructions and can confirm manual steps.

**Why this priority**: The four-loop harness is the end-to-end workflow that delivers migration value; it depends on the context, step, and build_recipe_plan tools.

**Independent Test**: Using a test project ID, run Loop I through Loop IV against a seeded graph and verify the context transitions from `in-progress` to `complete`.

**Acceptance Scenarios**:

1. **Given** a project ID that has no prior context, **When** `create_migration_context` is called, **Then** a new `MigrationContext` node is created with status `in-progress` and edges `UPGRADES_FROM` / `UPGRADES_TO` are present.
2. **Given** an existing context with status `complete`, **When** `create_migration_context` is called with the same `(projectId, fromVersion, toVersion)`, **Then** the existing context is returned unchanged — idempotent.
3. **Given** the agent is in Loop II Tier 1, **When** `get_steps_for_scope_tier` is called with `scope=api-surface`, **Then** only entities with graph hits at that tier are returned.
4. **Given** `build_recipe_plan` is called and no `AUTOMATED_BY` edges exist (first release), **Then** the auto track is empty and all steps are in the manual track — this is not an error.
5. **Given** all pending steps are completed, **When** `update_step_status` records the last step as `completed`, **Then** the context is auto-closed.

---

### User Story 3 — Agent Searches Migration Knowledge and Submits Community Insights (Priority: P2)

A developer's agent cannot find a migration rule for a specific class. It uses `search_migration_knowledge` (hybrid BM25 + vector) to find related rules and community insights. After manually resolving the issue, the agent calls `submit_migration_insight` to record the solution for future users.

**Why this priority**: Search and community feedback create the learning loop that improves the knowledge graph over time.

**Independent Test**: Index sample nodes; call `search_migration_knowledge` with a query string; verify ranked results are returned. Then call `submit_migration_insight` and verify a `CommunityInsight` node is created.

**Acceptance Scenarios**:

1. **Given** indexed `MigrationRule` nodes, **When** `search_migration_knowledge` is called with a natural-language query, **Then** results are ranked by RRF fusion (BM25 + vector) and returned up to `max_results`.
2. **Given** a near-duplicate insight already exists, **When** `submit_migration_insight` is called with similar content, **Then** the duplicate is detected and the write is skipped or flagged.
3. **Given** an insight exists, **When** `vote_insight` is called with `delta=1`, **Then** the `votes` property is incremented by 1.
4. **Given** a moderator calls `verify_insight`, **Then** `verified=true` is set on the target insight node.

---

### User Story 4 — Agent Resolves Paysafe Internal Dependency (Priority: P2)

An agent scanning a Paysafe project encounters a `com.paysafe.*` dependency. It calls `resolve_paysafe_dependency_by_service_name` to get the canonical GitLab repo, version, and migration guidance, without the agent needing to know FindIt or GitLab API details.

**Why this priority**: Paysafe-internal resolution is a key differentiator; it runs concurrently with Tier 1 in Loop II.

**Independent Test**: Call the tool with a known Paysafe service name; verify the resolver result is returned correctly without errors.

**Acceptance Scenarios**:

1. **Given** a known Paysafe service name, **When** `resolve_paysafe_dependency_by_service_name` is called, **Then** the result from `migration_oracle.paysafe.resolver.resolve()` is returned directly.
2. **Given** an unknown service name, **When** the tool is called, **Then** the resolver's not-found result is returned — the tool adds no extra logic.

---

### User Story 5 — Agent Executes a Safe Custom Cypher Query (Priority: P3)

A power user wants to run a read-only Cypher query not covered by any built-in tool. They call `execute_custom_cypher` with a `MATCH ... RETURN` statement. The server verifies the query contains no mutation keywords and executes it in a READ session.

**Why this priority**: Escape hatch for advanced users; lower priority than core migration tools.

**Independent Test**: Call with a safe `MATCH ... RETURN` query; verify results. Call with `MERGE` in the query; verify rejection before any graph contact.

**Acceptance Scenarios**:

1. **Given** a query string `MATCH (r:MigrationRule) RETURN r.id LIMIT 5`, **When** `execute_custom_cypher` is called, **Then** up to 5 rule IDs are returned.
2. **Given** a query string containing `MERGE`, `CREATE`, `SET`, `DELETE`, `REMOVE`, `DROP`, or `CALL db`, **When** `execute_custom_cypher` is called, **Then** an error response is returned and the query is never sent to the graph.

---

### User Story 6 — Server Starts Up Cleanly and Fails Fast on Bad Config (Priority: P1)

The server is launched via CLI or Docker. It loads config, verifies graph connectivity, and ensures all required indexes exist before accepting any tool calls. If the graph is unreachable at startup, the server exits with a clear error. If Memgraph index DDL fails, it logs a warning and continues in degraded mode.

**Why this priority**: Startup correctness gates all other scenarios — a broken startup renders the server unusable.

**Independent Test**: Start the server with valid config; verify it accepts tool calls. Start with an invalid `NEO4J_URI`; verify exit with error.

**Acceptance Scenarios**:

1. **Given** valid graph credentials, **When** the server starts, **Then** connectivity is verified, indexes are ensured, and the server begins accepting tool calls.
2. **Given** an unreachable graph, **When** the server starts, **Then** it exits with a connectivity error before accepting any tool calls.
3. **Given** a Memgraph instance where index DDL fails, **When** the server starts, **Then** it logs the DDL failure and continues in degraded mode (does not exit).
4. **Given** `MCP_TRANSPORT=sse`, **When** the server starts, **Then** it binds to `MCP_HOST:MCP_PORT` and accepts SSE connections.

---

### Edge Cases

- What happens when `analyze_upgrade_path` is called with a framework/version pair that has no graph data? → Returns empty rules list, not an error.
- How does `build_recipe_plan` behave when `MigrationStep` nodes exist but none qualify for the auto track? → Returns empty auto track, all steps in manual track.
- What if `get_artifact_content` is called with a path that is not stored in any Version node property? → Returns a not-found error; never reads arbitrary filesystem paths.
- What if `create_migration_context` is called for a completed context with new entities? → Returns the existing context; caller must inspect status and handle resume logic.
- What if `update_step_status` is called for a step that was already completed? → Idempotent; returns current state without error.
- What if the embedding model file is missing at startup? → Server fails to start; missing model is not a degraded-mode scenario.

---

## Requirements *(mandatory)*

### Functional Requirements

**Server & Transport**

- **FR-001**: The server MUST support three transports selectable via `MCP_TRANSPORT`: `stdio` (default), `sse`, and `streamable-http`.
- **FR-002**: For HTTP transports, the server MUST bind to `MCP_HOST:MCP_PORT` (defaults `0.0.0.0:8001`).
- **FR-003**: `MCP_STATELESS_HTTP=true` MUST enable stateless HTTP mode for remote clients.
- **FR-004**: The server MUST NOT accept tool calls before the startup sequence completes in order: (1) load config from `migration_oracle/config.py`, (2) verify graph connectivity via `RETURN 1`, (3) ensure all required indexes via `graph/indexes.py`. If step 2 fails, the server MUST exit. If step 3 fails on Memgraph, the server logs and continues in degraded mode.
- **FR-005**: On Neo4j/Memgraph connectivity failure at startup (step 2), the server MUST raise and exit. On Memgraph index DDL failure (step 3), the server MUST log and continue. FR-004 supersedes this requirement where they overlap.

**Tool Inventory**

- **FR-006**: The server MUST expose exactly 21 tools (14 read-only tools + 5 context-management tools + 2 artifact-access tools), 4 skill resources, and 1 prompt discoverable via `tools/list`, `resources/list`, and `prompts/list`. The 14 read-only tools span the Upgrade, Deprecation, Search, Schema, Community (read), Paysafe, and Install groups. The 5 context-management tools are `create_migration_context`, `get_pending_steps`, `update_step_status`, `get_steps_for_scope_tier`, and `close_migration_context`. The 2 artifact-access tools are `list_pipeline_runs` and `get_artifact_content`.
- **FR-007**: All tools except `submit_migration_insight`, `vote_insight`, `verify_insight`, `create_migration_context`, `update_step_status`, and `close_migration_context` MUST use READ graph sessions only.

**Upgrade Tools**

- **FR-008**: `analyze_upgrade_path` MUST accept `scope_filter` (string[], default `[]`) and `min_severity` (string, default `null`) as optional parameters alongside all existing parameters.
- **FR-009**: When `scope_filter` is non-empty, `analyze_upgrade_path` MUST return only rules that have at least one `HAS_SCOPE` edge matching a listed scope.
- **FR-010**: When `min_severity` is set, `analyze_upgrade_path` MUST return only rules at that severity or above.
- **FR-011**: In JSON format, each rule in `analyze_upgrade_path` MUST include a `steps` array (via `REQUIRES_STEP` → `MigrationStep`) and a `scopes` array (via `HAS_SCOPE` → `BreakingScope`); both MUST be empty lists when those nodes are absent (pre-redesign data).
- **FR-012**: `build_recipe_plan` MUST produce a two-track plan (auto + manual). A step qualifies for the auto track only when `automatable=true`, `effort='mechanical'`, and an `AUTOMATED_BY` edge exists with `auto=true` and `missingRequiredParams=[]`. Absent `AUTOMATED_BY` edges place the step in the manual track.
- **FR-013**: `build_recipe_plan` MUST emit step cards for the manual track (summary, instruction, verificationHint, effort, blocked_reason) when `MigrationStep` nodes are present. When no `MigrationStep` nodes exist, it MUST fall back to rule-level cards using `actionStep`.

**Deprecation Tools**

- **FR-014**: `resolve_deprecation` MUST return deprecated_in, removed_in, replaced_by (one hop), and related rules for a single entity.
- **FR-015**: `entity_evolution` MUST trace the full `REPLACED_BY` chain up to 5 hops with lifecycle events and rules per node.

**Search Tools**

- **FR-016**: `search_migration_knowledge` and `search_openrewrite_recipes` MUST use hybrid search: BM25 (FTS index) + cosine similarity (vector index) fused via RRF with `k=60`. Defaults: `top_k_per_index=50`, `min_vector_similarity=0.30`, `max_results=5`.
- **FR-017**: The `SentenceTransformer` model MUST be loaded once as a module-level lazy singleton in `mcp/tools/search.py`, exposed via a `get_embedding_model()` function. The module-level variable holding the instance MUST be named `_model` and initialised to `None` (`_model: SentenceTransformer | None = None`). The function MUST implement the check-then-assign pattern exactly as: `if _model is None: _model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)`. The model MUST NOT be instantiated inside a tool handler or any per-call function. The model name is read from `SENTENCE_TRANSFORMERS_MODEL` (default `all-mpnet-base-v2`).

**Schema Tools**

- **FR-018**: `get_graph_schema` MUST return the authoritative schema as a static markdown string without executing any Cypher.
- **FR-019**: `execute_custom_cypher` MUST block queries containing (case-insensitive) any of the exact keywords `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, or the string prefix `CALL db` before the query leaves the Python process. Additionally, all sessions for this tool MUST use READ access mode on the graph driver. Both enforcement layers are independently required — the in-process keyword check AND the READ session; neither alone is sufficient.

**Community Tools**

- **FR-020**: `submit_migration_insight` MUST detect near-duplicates before writing a new `CommunityInsight` node.
- **FR-021**: `vote_insight` MUST increment or decrement the `votes` property by the specified delta.
- **FR-022**: `verify_insight` MUST set `verified=true` on the target insight node (moderator operation).

**Context Tools**

- **FR-023**: `create_migration_context` MUST be idempotent for a given `(projectId, fromVersion, toVersion)` triple; re-calling it returns the existing context unchanged. Idempotency MUST be implemented via a `MERGE` Cypher pattern on the triple — a lookup-then-create pattern is not acceptable because it creates a race condition under concurrent agent calls. The MERGE key is the triple `(projectId, fromVersion, toVersion)`. All other properties (`framework`, `status`, `createdAt`, `scannedEntities`, etc.) MUST be set only in the `ON CREATE SET` block; they MUST NOT be overwritten on subsequent `MERGE` matches.
- **FR-024**: `get_pending_steps` MUST return the remaining step queue ordered by scope severity descending then topological step order, excluding completed and skipped steps.
- **FR-025**: `update_step_status` MUST auto-close the `MigrationContext` when no pending steps remain after recording the current step's outcome. The auto-close check MUST be implemented in application code in the tool handler — not as a Cypher trigger or graph procedure. After writing the step outcome, the handler MUST query the remaining pending steps for the context and, if the list is empty, issue a follow-up write to set `ctx.status = "complete"` and `ctx.completedAt = datetime()`.
- **FR-026**: `close_migration_context` MUST set `completedAt` and `notes` on the context node with the supplied `final_status`. The tool MUST return `{ contextId, status, completedSteps: string[], skippedSteps: string[], completedAt: datetime | null, notes: string }`.

**Paysafe Tools**

- **FR-027**: `resolve_paysafe_dependency_by_service_name` MUST delegate entirely to `migration_oracle.paysafe.resolver.resolve()` with no additional resolution logic in the tool module. `mcp/tools/paysafe.py` MUST import only `migration_oracle.paysafe.resolver.resolve`; it MUST NOT import `findit.py`, `gitlab.py`, or any other paysafe-internal module directly. Parameter mapping and result pass-through are the only responsibilities of this tool module.

**Artifact Tools**

- **FR-028**: `get_artifact_content` MUST resolve the file path exclusively from Version node properties (`rawMdPath`, `filteredMdPath`, `entitiesJsonPath`). The caller supplies `(framework, from_version, to_version, artifact_type)` — the tool queries the matching Version node and reads the path from the node property. No file path is accepted as a direct parameter from the caller. The `artifact_type` parameter MUST be one of `raw_md`, `filtered_md`, or `entities_json`; these map to `rawMdPath`, `filteredMdPath`, and `entitiesJsonPath` properties on the `Version` node respectively. If the requested Version node or property is absent, the tool returns a not-found error without touching the filesystem.

**Install Tool**

- **FR-029**: `install_migration_skill` MUST copy bundled skill Markdown files to the Cursor or Claude Code skills directory; when `target="auto"`, it MUST detect the target from the environment.

**Skill Resources**

- **FR-030**: The server MUST serve four skill resources at startup from static Markdown files in `mcp/skills/`: `skill://framework-migration/main`, `skill://framework-migration/scanning`, `skill://framework-migration/plan-format`, `skill://framework-migration/version-map`. These files are read at server startup and served as MCP resources; they are not generated dynamically.

**Four-Loop Harness Skill (`framework_migration_main.md`)**

- **FR-031**: Loop I MUST call `create_migration_context` (or load existing by projectId) before any graph tool call. If context status is `complete`, the skill surfaces a summary and stops.
- **FR-032**: Loop II MUST query in four scope-gated tiers (Tier 1: api-surface/high+critical; Tier 2: runtime/medium+; Tier 3: config+build/all; Tier 4: test/all), calling `get_steps_for_scope_tier` → `analyze_upgrade_path` → `resolve_deprecation` per tier, with a skip guard on `ctx.queriedEntities`.
- **FR-033**: Loop II MUST run `resolve_paysafe_dependency_by_service_name` concurrently for all `com.paysafe.*` entities without blocking Tier 1 completion.
- **FR-034**: Loop III MUST route each step to auto track (with build+test cycle and `update_step_status`) or manual track (step card + user confirm) based on the AUTOMATED_BY edge conditions; absent `AUTOMATED_BY` edges default all steps to manual track.
- **FR-035**: Loop III MUST call `update_step_status` after every step before moving to the next.
- **FR-036**: Loop IV MUST call `submit_migration_insight` for manual steps where the developer's fix differed from `step.instruction`, and `close_migration_context` at the end of every session.
- **FR-037**: The skill MUST include decision tables for all four loops verbatim.
- **FR-043**: `mcp/skills/framework_migration_main.md` is NOT a static copy of the pre-redesign skill. Its content MUST implement the four re-entrant loops from redesign §7 (Increment 3). The file is served as a static MCP resource at startup (FR-030), but the content served must be the four-loop harness implementation described in FR-031 through FR-037.

**Backward Compatibility**

- **FR-038**: All 14 existing tool parameter signatures MUST remain frozen; `scope_filter` and `min_severity` are additive optional parameters with defaults that reproduce the original behavior when omitted — no existing parameter may be renamed or removed.
- **FR-044**: The server MUST produce correct output when zero `AUTOMATED_BY` edges exist (the expected state in the first release, before the recipe-mapping job runs): `build_recipe_plan` returns an empty auto track and a manual-only result; `analyze_upgrade_path` returns empty `recipes` arrays; Loop III of the harness routes all steps to the manual track. None of these outcomes is an error condition.
- **FR-039**: All Cypher queries joining `MigrationStep`, `BreakingScope`, or `MigrationContext` nodes MUST use `OPTIONAL MATCH` so pre-redesign data returns empty arrays, not errors.
- **FR-040**: `actionStep` on existing `MigrationRule` nodes MUST remain readable by all tools; no tool may discard it.

**Integration Constraints**

- **FR-041**: All Cypher strings MUST live in `mcp/graph/queries/` (one module per tool group); tool handlers in `mcp/tools/` MUST import query functions and MUST NOT inline Cypher.
- **FR-042**: All environment variables MUST be loaded from `migration_oracle/config.py`; no inline `os.environ` calls are permitted in any `mcp/` module.

### Key Entities

- **MigrationContext**: Tracks the state of a migration session for a `(projectId, fromVersion, toVersion)` triple; has `status`, `scannedEntities`, `queriedEntities`, `completedAt`, `notes`.
- **MigrationStep**: A discrete, independently addressable migration action linked to a `MigrationRule` via `REQUIRES_STEP`; has `automatable`, `effort`, `summary`, `instruction`, `verificationHint`.
- **BreakingScope**: Categorises a `MigrationRule` by affected code area (e.g., `api-surface`, `runtime`, `config`); linked via `HAS_SCOPE`.
- **CommunityInsight**: A developer-contributed fix or workaround linked to a `Version` node; has `statement`, `solution`, `votes`, `verified`, `confidence`, `evidence_url`.
- **OpenRewriteRecipe**: An automation recipe linked to a `MigrationStep` or `MigrationRule` via `AUTOMATED_BY`; has `auto`, `missingRequiredParams`, `composite`.
- **Version**: A framework version node; has `rawMdPath`, `filteredMdPath`, `entitiesJsonPath` for pipeline artifacts.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 21 tools are discoverable and return correctly structured responses within 2 seconds for graph queries on a populated test dataset.
- **SC-002**: `analyze_upgrade_path` called on pre-redesign data (no `MigrationStep`/`BreakingScope` nodes) returns the same rule set as the pre-redesign baseline — zero regressions in existing tool output.
- **SC-003**: `execute_custom_cypher` rejects 100% of queries containing mutation keywords before any graph contact, verified by a mutation-attempt test suite.
- **SC-004**: The server handles 10 concurrent agent connections without degraded response times or session cross-contamination.
- **SC-005**: A full Loop I–IV run on a project with 50 scanned entities completes without manual error intervention when all steps route to the manual track (first-release, no AUTOMATED_BY edges).
- **SC-006**: `submit_migration_insight` detects and suppresses near-duplicate insights with ≥ 95% accuracy on a test dataset of known duplicates.
- **SC-007**: The embedding model is loaded exactly once per server process; tool call latency for hybrid search does not increase beyond 10% on the 10th concurrent call compared to the 1st.
- **SC-008**: Startup completes (config → connectivity → indexes) in under 10 seconds on standard hardware with a reachable graph.

---

## Increment Scope

Spec 005 covers **Increment 2** (new MCP tools: context-management tool group, scope-filter/min-severity parameters on `analyze_upgrade_path`, step-level Cypher joins via `OPTIONAL MATCH`) and **Increment 3** (skill harness rewrite: `framework_migration_main.md` four-loop implementation). **Increment 1** — the pipeline changes that populate `MigrationStep` and `BreakingScope` nodes — was delivered in spec 002 and is a prerequisite for step-level code paths.

**Data dependency for step-level vs rule-level code paths**:

| Code path | Requires | Available without Increment 1? |
|-----------|----------|-------------------------------|
| `analyze_upgrade_path` returns non-empty `steps` and `scopes` arrays | `MigrationStep` + `BreakingScope` nodes in graph | No — returns empty arrays |
| `build_recipe_plan` emits step cards in manual track | `MigrationStep` nodes in graph | No — falls back to rule-level cards |
| `get_pending_steps` returns actual step queue | `MigrationStep` nodes in graph | No — returns empty queue |
| All rule-level tools (`analyze_upgrade_path`, `resolve_deprecation`, search, etc.) | `MigrationRule` nodes | Yes — work on pre-redesign data |

Implementations MUST handle both states gracefully via `OPTIONAL MATCH` (FR-039); the absence of Increment 1 data is not a server error.

Integration tests for `get_pending_steps`, `get_steps_for_scope_tier`, and `build_recipe_plan` step-level behaviour require a graph instance seeded with `MigrationStep` and `BreakingScope` nodes (Increment 1 pipeline run); unit tests with mocked graph data are the primary test path for these tools in isolation.

---

## Assumptions

- The Neo4j/Memgraph instance is already provisioned and seeded; the MCP server does not manage database lifecycle.
- `MigrationStep` and `BreakingScope` nodes are absent in the first release; their absence is a valid state, not an error condition.
- `AUTOMATED_BY` edges are absent in the first release and will be populated by a separate recipe-mapping job after initial deployment.
- The Paysafe `resolver.resolve()` function handles its own error cases; the MCP tool wrapper does not need to add retry or fallback logic.
- Skill Markdown files bundled in `mcp/skills/` are static at server startup; they do not need to be reloaded without a server restart.
- The `SentenceTransformer` model files are present in the environment at startup; missing model files cause a hard startup failure (not degraded mode).
- All agents connecting to the server are trusted internal agents; the server does not implement agent-level authentication beyond transport-level controls.
- `MCP_TRANSPORT=stdio` is the primary integration target for Claude Code and Cursor; SSE/HTTP transports are secondary but fully supported.

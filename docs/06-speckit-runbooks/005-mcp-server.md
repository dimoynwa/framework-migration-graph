# SpecKit Runbook — `005-mcp-server`

> **How to use this file:** Paste each prompt block verbatim into Claude Code in the order shown.
> Do not skip the gap-review steps — they catch the most common drift before it compounds.
> Complete all items in a gap review before advancing to the next command.

---

## Prerequisites

Before starting this spec:

- `002-pipeline-core` ✅ — `migration_oracle/pipeline/populator.py` must be complete; `Version` nodes with `rawMdPath`, `filteredMdPath`, `entitiesJsonPath` properties must be written by the pipeline
- `004-paysafe-resolver` ✅ — `migration_oracle.paysafe.resolver.resolve()` must be importable and passing all tests
- `migration_oracle/graph/driver.py` and `graph/indexes.py` from `001-foundations` must be importable
- `uv sync` must produce a clean environment with `mcp` and `sentence-transformers` in the dependency set
- Reference docs to keep open while reviewing gap prompts:
  - `docs/graph-mcp-skills-and-paysafe-resolution.md` §6–10 (all existing tools, Cypher, resources, prompts)
  - `docs/migration-oracle-redesign.md` §6 (new context-management tools), §3.1–3.2 (new node types and relationships)
  - `docs/SPEC_ORGANIZATION.md` §005 (repository scope and completion gate)

---

## Command 1 — `/speckit.specify`

Paste this entire block:

```
/speckit.specify

WHAT it does:
The MCP Server module (`migration_oracle/mcp/`) implements the `PaysafeMigrationOracle`
Model Context Protocol server. It exposes 21 tools, 4 skill resources, and 1 prompt to
AI agents via stdio, SSE, or streamable-HTTP transport. All tools are read-only against
the graph except: `submit_migration_insight`, `vote_insight`, `verify_insight`,
`create_migration_context`, `update_step_status`, and `close_migration_context`, which
perform targeted graph writes within their documented contracts.

At startup, the server verifies Neo4j/Memgraph connectivity and runs `graph/indexes.py`
to ensure all required indexes exist. Failure to connect raises at startup; missing
indexes on Memgraph are logged and skipped (Memgraph degraded mode).

WHY it exists:
AI agents (Cursor, Claude Code, custom harnesses) need a standard, discoverable interface
to the migration knowledge graph and Paysafe resolution logic. Without this server the
graph data is inaccessible to agents. The MCP protocol provides tool discovery, typed
parameters, and structured return values over stdio or HTTP, so agents can call migration
analysis tools without knowing how Cypher, hybrid search, or FindIt resolution work.

UPGRADE TOOL GROUP and what it does:
  - analyze_upgrade_path: returns lifecycle alerts, migration rules, and optional recipe
    metadata for a framework upgrade between two versions. Parameters include:
    current_version, target_version, framework, user_entities, format (markdown|json),
    classification, include_recipes, include_lifecycle, top_n, verbose — and two new
    parameters added by the redesign: scope_filter (string[], default []) and
    min_severity (string, default null). When scope_filter is non-empty, only rules with
    at least one HAS_SCOPE edge matching a listed scope are returned. When min_severity
    is set, only rules at that severity or above are returned.
    In JSON format, each rule now includes a `steps` array (from MigrationStep nodes via
    REQUIRES_STEP) and a `scopes` array (from BreakingScope nodes via HAS_SCOPE) when the
    enhanced graph data is present. For pre-redesign data where those nodes are absent,
    steps and scopes are empty lists — not errors.
  - build_recipe_plan: builds a two-track migration plan. When MigrationStep nodes exist
    for the queried rules, the auto track selects steps where automatable=true AND
    effort='mechanical' AND an AUTOMATED_BY edge with auto=true and missingRequiredParams=[]
    is present. If no AUTOMATED_BY edge exists on a step (expected in the first release
    before recipe mapping has been run), that step goes to the manual track — this is not
    an error. An empty auto track with all steps in manual is a valid result.
    The manual track emits step cards (not rule cards), each containing the step's
    summary, instruction, verificationHint, effort, and blocked_reason. When no
    MigrationStep nodes exist (pre-redesign data), the tool returns an empty auto track
    and a manual track of rule-level cards using actionStep where present.

DEPRECATION TOOL GROUP and what it does:
  - resolve_deprecation: full deprecation lifecycle for a single class, property, or
    dependency — deprecated_in, removed_in, replaced_by (one hop), and related rules.
  - entity_evolution: traces the full REPLACED_BY chain up to 5 hops with lifecycle
    events and rules per node in the chain.

SEARCH TOOL GROUP and what it does:
  - search_migration_knowledge: hybrid search (BM25 + vector + RRF) over MigrationRule
    and CommunityInsight nodes; configurable top_k, rrf_k, min_vector_similarity.
  - search_openrewrite_recipes: hybrid search over OpenRewriteRecipe nodes; filterable
    by composite flag and parameter requirements.

SCHEMA TOOL GROUP and what it does:
  - get_graph_schema: returns the authoritative graph schema document as a static
    markdown string (no Cypher executed).
  - execute_custom_cypher: executes a caller-supplied read-only Cypher query; blocks
    all mutation keywords (CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL db.*);
    enforces a READ session.

COMMUNITY TOOL GROUP and what it does:
  - submit_migration_insight: creates a CommunityInsight node linked to a Version,
    merges affected entity nodes, detects near-duplicate before writing.
  - get_community_insights: queries insights with optional version range, entity, and
    verification filters.
  - vote_insight: increments or decrements the votes property on an insight by elementId.
  - verify_insight: sets verified=true on an insight by elementId (moderator operation).

CONTEXT TOOL GROUP and what it does:
  - create_migration_context: creates or resumes a MigrationContext node for a
    (projectId, fromVersion, toVersion) triple; idempotent; links UPGRADES_FROM and
    UPGRADES_TO Version edges.
  - get_pending_steps: returns the remaining MigrationStep queue for a context, ordered
    by scope severity descending then topological step order, excluding completed and
    skipped steps; filterable by effort and scope.
  - update_step_status: records the outcome (completed/skipped/failed) of a step onto
    the MigrationContext node; auto-closes context when no pending steps remain.
  - get_steps_for_scope_tier: returns the subset of context-scanned entities that have
    graph hits at a given scope/severity tier; drives scope-gated querying in Loop II
    of the agent harness.
  - close_migration_context: finalises a context (complete/partial/abandoned); sets
    completedAt and notes.

PAYSAFE TOOL GROUP and what it does:
  - resolve_paysafe_dependency_by_service_name: delegates entirely to
    migration_oracle.paysafe.resolver.resolve(); maps the MCP tool parameters to the
    resolver's function signature and maps the resolver result directly to the tool
    return value. No logic in this tool module.

ARTIFACT TOOL GROUP and what it does:
  - list_pipeline_runs: queries Version nodes where rawMdPath IS NOT NULL; returns
    framework, from_version, to_version, raw_md_path, filtered_md_path, entities_json_path
    for each run.
  - get_artifact_content: resolves the path for the requested artifact type
    (raw_md | filtered_md | entities_json) from the Version node property, reads the
    file, and returns its content as a string.

INSTALL TOOL GROUP and what it does:
  - install_migration_skill: copies the bundled skill Markdown files to the Cursor
    or Claude Code skills directory; detects target from environment when target="auto".

SKILL RESOURCES and what they serve:
  - skill://framework-migration/main → framework_migration_main.md (end-to-end upgrade workflow)
  - skill://framework-migration/scanning → framework_migration_scanning.md (codebase scan patterns)
  - skill://framework-migration/plan-format → framework_migration_plan_format.md (plan task schema)
  - skill://framework-migration/version-map → framework_migration_version_map.md (version→sortable tables)

KEY BEHAVIORS:
STARTUP SEQUENCE — On server start: (1) load config from migration_oracle/config.py,
  (2) verify graph connectivity with RETURN 1, (3) run graph/indexes.py to ensure all
  indexes. Raise on connectivity failure. On Memgraph index DDL failure: log and continue.
  Do not accept tool calls before this sequence completes.

EMBEDDING SINGLETON — The SentenceTransformer model is loaded once at module level in
  mcp/tools/search.py via a lazy-load get_embedding_model() function. Never instantiate
  the model inside a tool handler or per-call function. The model name is read from
  SENTENCE_TRANSFORMERS_MODEL (default "all-mpnet-base-v2").

HYBRID SEARCH ALGORITHM — search_migration_knowledge and search_openrewrite_recipes:
  Step 1: BM25 from FTS index + cosine similarity from vector index(es) independently.
  Step 2: RRF with k=60 to fuse ranked lists. Step 3: hydration Cypher to fetch full
  node properties. Default top_k_per_index=50, min_vector_similarity=0.30, max_results=5.

CYPHER SECURITY — execute_custom_cypher must check the query string for the following
  keywords before sending to the graph (case-insensitive): CREATE, MERGE, SET, DELETE,
  REMOVE, DROP, and the prefix "CALL db". On any match, return an error response —
  do not execute the query. All sessions for this tool must use READ access mode.

ARTIFACT READ PATH — get_artifact_content reads only paths stored in Version node
  properties (rawMdPath, filteredMdPath, entitiesJsonPath). It must never read arbitrary
  filesystem paths from the caller. The path is resolved by querying the Version node
  first, then reading the file at that path.

TRANSPORT SELECTION — MCP_TRANSPORT env var selects stdio (default), sse, or
  streamable-http. For http transports, bind to MCP_HOST:MCP_PORT (defaults 0.0.0.0:8001).
  MCP_STATELESS_HTTP=true enables stateless HTTP mode for remote clients.

ANALYZE_UPGRADE_PATH STEP/SCOPE JOINS — The Cypher for analyze_upgrade_path must add
  OPTIONAL MATCH joins to the existing query from `graph-mcp-skills-and-paysafe-resolution.md`:
    OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
    OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
  Collect these as `steps` and `scopes` arrays per rule in the RETURN clause. Use OPTIONAL
  MATCH so that pre-redesign rules (with no step or scope nodes) return empty arrays.

BUILD_RECIPE_PLAN STEP-LEVEL AUTO TRACK — The Cypher for build_recipe_plan must join
  MigrationStep nodes and optionally their AUTOMATED_BY edges. Both joins are OPTIONAL:
    OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
    OPTIONAL MATCH (s)-[ab_s:AUTOMATED_BY]->(rec_s:OpenRewriteRecipe)
  A step qualifies for the auto track only when BOTH of these are true:
    s.automatable = true AND s.effort = 'mechanical'
    AND ab_s is NOT NULL AND ab_s.auto = true AND ab_s.missingRequiredParams = []
  When ab_s is NULL (AUTOMATED_BY edge absent — expected in the first release), the step
  is placed in the manual track regardless of its automatable/effort values. An empty
  auto track is a valid result. When no MigrationStep nodes exist at all, the tool
  returns an empty auto track and a manual track of rule-level cards.

SKILL MAIN — FOUR-LOOP HARNESS (redesign §7) — `mcp/skills/framework_migration_main.md`
  must implement the four re-entrant loops that replace the five sequential phases.
  This is Increment 3 of the redesign and is part of spec 005.

  Loop I — Context: (1) call create_migration_context or load existing context by projectId.
  If status=complete, surface summary and stop. If status=in-progress or blocked, diff new
  scan against ctx.scannedEntities and queue new entities for Loop II. Always run codebase
  scan first. Load skill://framework-migration/version-map and surface toolchain gates
  before any graph query. Gate: never call graph tools before this loop completes.

  Loop II — Scope-gated query: query in 4 tiers. Tier 1: api-surface / high+critical;
  Tier 2: runtime / medium+; Tier 3: config+build / all; Tier 4: test / all. For each tier
  call get_steps_for_scope_tier → analyze_upgrade_path → resolve_deprecation per removed
  entity → entity_evolution if partial chain. Skip guard: check ctx.queriedEntities before
  each tool call — if entity was queried in a prior session skip the call. Run
  resolve_paysafe_dependency_by_service_name concurrently for all com.paysafe entities;
  do not block tier 1 on its result.

  Loop III — Execution: call get_pending_steps to get the full queue (scope-severity order,
  critical first). Route each step:
  Auto track: automatable=true AND effort='mechanical' AND AUTOMATED_BY edge is present
    with auto=true AND missingRequiredParams=[] → batch in rewrite.yml, apply, run
    build+test, call update_step_status(completed).
  No AUTOMATED_BY edge (first release): step has automatable=true AND effort='mechanical'
    but no recipe linked → route to manual track. This is the expected default in the
    first release. Do not treat absent AUTOMATED_BY as an error.
  Prompted auto: AUTOMATED_BY exists but missingRequiredParams non-empty → surface params,
    retry or fall to manual.
  Manual: effort=moderate OR no AUTOMATED_BY edge → emit step card (summary, instruction,
    verificationHint), wait for user confirm.
  Design gate: effort=architectural → pause, emit design decision, wait, then manual.
  Blocked: REQUIRES edge to incomplete step → re-queue.
  On auto track build failure: rollback via skill://recipe-task-rollback/main, call
  update_step_status(failed), search_migration_knowledge for workarounds, escalate to
  manual. Call update_step_status after every step before moving on.

  Loop IV — Feedback: load skill://generate-community-insights; for each manual step where
  developer's actual fix differed from step.instruction, call submit_migration_insight with
  statement, solution, version, affected entities, confidence (0.9 if build+tests pass,
  0.7 if build only, 0.5 if uncertain), evidence_url. For each skipped step where
  effort ≠ 'test', emit a backlog item (via skill://emit-migration-backlog/main) containing
  step summary, instruction, verificationHint, jiraKeys from parent rule, BreakingScope
  severity. Call close_migration_context with final_status=complete/partial/abandoned.

  Decision tables (§7.5) must appear verbatim in the skill: context loop decisions, query
  loop decisions, execution loop decisions, feedback loop decisions.

BACKWARD COMPATIBILITY CONTRACT (redesign §8) — The MCP server must preserve all of:
  (a) All 14 existing tool parameter signatures are frozen. New parameters (scope_filter,
      min_severity) are optional with defaults that reproduce original behavior when omitted.
      No existing parameter may be removed or renamed.
  (b) AUTOMATED_BY edges (both rule-level and step-level) are absent in the first release
      and will be added later via a separate recipe-mapping job. The MCP server must work
      correctly with zero AUTOMATED_BY edges: build_recipe_plan returns an empty auto track;
      analyze_upgrade_path returns empty recipes arrays; Loop III routes all steps to manual.
      None of these is an error condition.
  (c) actionStep on existing MigrationRule nodes must remain readable. No tool may block
      or discard actionStep values from old nodes. New population runs stop writing actionStep,
      but tools reading it continue to work.
  (d) All Cypher that joins new node types (MigrationStep, BreakingScope, MigrationContext)
      must use OPTIONAL MATCH so pre-redesign data returns empty arrays, not errors.

OPTIONAL MATCH FOR NEW SCHEMA — All Cypher queries touching MigrationStep, BreakingScope,
  or MigrationContext must use OPTIONAL MATCH. Pre-redesign Version nodes will not have
  these connected node types. Queries that require OPTIONAL MATCH return empty lists
  for missing nodes, not errors.

GRAPH WRITE SCOPE — The only tools that write to the graph are: submit_migration_insight,
  vote_insight, verify_insight, create_migration_context, update_step_status,
  close_migration_context. All other tools use READ sessions only.

INTEGRATION CONSTRAINTS:
- All graph Cypher queries live in mcp/graph/queries/ — one module per tool group;
  tool handler functions in mcp/tools/ import query functions, never inline Cypher strings
- mcp/tools/paysafe.py imports ONLY migration_oracle.paysafe.resolver.resolve; it does
  not import findit.py, gitlab.py, or any paysafe internal module
- Embedding model must be a module-level lazy singleton in mcp/tools/search.py —
  never instantiated inside a tool handler
- mcp/tools/artifacts.py is read-only; it never writes to the graph and never reads
  filesystem paths not sourced from a Version node property
- Skill resource Markdown files live in mcp/skills/; the server reads them at startup
  and serves them as MCP resources — they are not generated dynamically
- All env vars loaded from migration_oracle/config.py — no inline os.environ calls
  in mcp/ modules
- execute_custom_cypher must enforce mutation keyword blocking before the query leaves
  the Python process — do not rely solely on graph-level read sessions as the guard
```

---

## Gap Review — Post-Specify

After `/speckit.specify` generates `spec.md`, paste this before running `/speckit.plan`:

```
Review the generated spec.md for 005-mcp-server and fix any of the following gaps
before we proceed to planning:

GAP-001: Tool count explicit
  The spec must state the total tool count as 21 (14 read-only + 5 context-management
  + 2 artifact-access tools). If the count is absent or wrong, correct it. It is not
  acceptable to leave this vague — the completion gate for 005 requires all 21 tools
  to register without error.

GAP-002: Write vs read tool split
  The spec must explicitly list which tools perform graph writes:
  submit_migration_insight, vote_insight, verify_insight, create_migration_context,
  update_step_status, close_migration_context (6 tools).
  All others are read-only. If this split is not explicit, add it.

GAP-003: execute_custom_cypher blocked keywords
  The spec must list the exact blocked keywords: CREATE, MERGE, SET, DELETE, REMOVE,
  DROP, and "CALL db" as a prefix check. If the spec is vague ("dangerous keywords")
  or omits any of these, fix it. Both the string check AND the READ session are required
  — neither alone is sufficient.

GAP-004: Embedding singleton pattern
  The spec must state that the embedding model is a module-level lazy singleton in
  mcp/tools/search.py loaded via get_embedding_model(). It must not say "load on demand"
  in a way that implies per-call loading. If the pattern is ambiguous, specify the
  lazy-load check-then-assign approach explicitly.

GAP-005: Artifact tool path security
  The spec must state that get_artifact_content resolves the file path from a Version
  node property, never from a caller-supplied path parameter. The caller specifies
  (framework, version, artifact_type) — the path comes from the graph, not from input.
  If the spec allows a path parameter or does not describe this security constraint, fix it.

GAP-006: Startup sequence ordering
  The spec must state the startup sequence in order: load config → verify connectivity
  (RETURN 1) → ensure indexes. If the order is unspecified or incorrect, fix it.
  The server must not register tools before connectivity is verified.

GAP-007: OPTIONAL MATCH requirement for new schema
  The spec must state that all Cypher queries joining to MigrationStep, BreakingScope,
  or MigrationContext must use OPTIONAL MATCH so that pre-redesign data (which has no
  such nodes) continues to work. If this requirement is absent, add it.

GAP-008: Skill resource URIs
  The spec must list all four skill resource URIs:
  skill://framework-migration/main, skill://framework-migration/scanning,
  skill://framework-migration/plan-format, skill://framework-migration/version-map.
  If any are missing, add them.

GAP-009: Paysafe tool delegation rule
  The spec must state that mcp/tools/paysafe.py contains no resolution logic — it imports
  only migration_oracle.paysafe.resolver.resolve and maps parameters to it.
  If the spec describes the resolution steps inline in the MCP tool, remove them and
  replace with a delegation statement.

GAP-010: MigrationContext idempotency
  The spec must state that create_migration_context is idempotent on
  (projectId, fromVersion, toVersion) — calling it twice does not create duplicate nodes.
  The MERGE Cypher pattern is required. If this is absent, add it.

GAP-011: analyze_upgrade_path new parameters named explicitly
  The spec must name the two new parameters added by the redesign:
  scope_filter (string[], default []) and min_severity (string | null, default null).
  If the spec only says "filterable by scope/severity" without naming these params,
  add them with their types and defaults.

GAP-012: analyze_upgrade_path redesigned JSON return
  The spec must state that the JSON format response now includes a `steps` array and a
  `scopes` array per rule when MigrationStep and BreakingScope nodes are present.
  Both arrays must be empty lists (not errors) for pre-redesign rules.
  If the JSON return shape is described using only the old schema (no steps/scopes),
  add these fields with their OPTIONAL MATCH fallback behaviour.

GAP-013: build_recipe_plan AUTOMATED_BY absent is valid
  The spec must state that AUTOMATED_BY edges are absent in the first release (recipe
  mapping runs later). When absent: auto track is empty, all steps go to manual — this
  is correct behavior, not an error. If the spec requires AUTOMATED_BY to be present
  for the tool to return a meaningful result, or treats empty auto track as an error,
  fix it. The step-level auto track filter (automatable=true AND effort='mechanical' AND
  AUTOMATED_BY present with auto=true) must only apply when the edge actually exists.

GAP-014: framework_migration_main.md implements four loops (Increment 3)
  The spec must state that `mcp/skills/framework_migration_main.md` is not a static
  copy of the old skill — it must implement the four re-entrant loops from redesign §7:
  Loop I (context/scan), Loop II (scope-gated query with 4 tiers + skip guard),
  Loop III (execution routing: auto/prompted/manual/design-gate/blocked/rollback),
  Loop IV (feedback: deviations → submit_migration_insight → backlog → close_context).
  If the spec describes the skill as "static content served at startup" without
  specifying its required content, add the four-loop requirement.

GAP-015: Backward compatibility — 14-tool parameter freeze and actionStep readability
  The spec must state: (a) all 14 existing tool parameter signatures are unchanged —
  no existing parameter is renamed or removed; new parameters use defaults that reproduce
  old behavior; (b) AUTOMATED_BY edges are absent in the first release — the server must
  produce correct output (empty auto track, manual-only result) with zero such edges;
  (c) actionStep on existing MigrationRule nodes remains readable — no tool discards or
  blocks it. If any of these three backward compat guarantees are absent, add them.

GAP-016: Increment mapping explicit
  The spec must note that spec 005 covers redesign Increment 2 (new MCP tools) and
  Increment 3 (skill harness rewrite). Increment 1 (pipeline changes) was spec 002
  and is a prerequisite. Meaningful step-level tool testing (get_pending_steps returning
  actual steps) requires a graph populated with MigrationStep nodes by Increment 1.
  If the spec does not distinguish what data is needed for step-level vs rule-level
  code paths, add this note.
```

---

## Command 2 — `/speckit.plan`

After spec.md is clean, paste:

```
/speckit.plan

Generate plan.md, data-model.md, contracts/005-mcp-server.md, research.md,
and quickstart.md for 005-mcp-server.

Required file layout (do not deviate):

migration_oracle/
└── mcp/
    ├── server.py                 # Entry point: transport selection, startup sequence, tool/resource registration
    ├── tools/
    │   ├── upgrade.py            # analyze_upgrade_path, build_recipe_plan
    │   ├── deprecation.py        # resolve_deprecation, entity_evolution
    │   ├── search.py             # search_migration_knowledge, search_openrewrite_recipes
    │   │                         #   + module-level get_embedding_model() singleton
    │   ├── schema.py             # get_graph_schema, execute_custom_cypher
    │   ├── community.py          # submit_migration_insight, get_community_insights,
    │   │                         #   vote_insight, verify_insight
    │   ├── context.py            # create_migration_context, get_pending_steps,
    │   │                         #   update_step_status, get_steps_for_scope_tier,
    │   │                         #   close_migration_context
    │   ├── paysafe.py            # resolve_paysafe_dependency_by_service_name
    │   │                         #   (delegates to migration_oracle.paysafe.resolver.resolve)
    │   ├── artifacts.py          # list_pipeline_runs, get_artifact_content
    │   └── install.py            # install_migration_skill
    ├── skills/                   # Skill Markdown files served as MCP resources
    │   ├── framework_migration_main.md      # MUST implement the four-loop harness (redesign §7):
    │   │                                    # Loop I (context/scan), Loop II (scope-gated query,
    │   │                                    # 4 tiers, skip guard), Loop III (step routing:
    │   │                                    # auto/prompted/manual/design-gate/blocked/rollback),
    │   │                                    # Loop IV (feedback: deviations/insights/backlog/close).
    │   │                                    # Decision tables from §7.5 must appear verbatim.
    │   │                                    # This is Increment 3 of the redesign.
    │   ├── framework_migration_scanning.md  # Unchanged from existing skill
    │   ├── framework_migration_plan_format.md # Unchanged from existing skill
    │   └── framework_migration_version_map.md # Unchanged from existing skill
    └── graph/
        └── queries/              # One module per tool group — see Cypher source note below
            ├── upgrade.py        # analyze_upgrade_path + build_recipe_plan Cypher
            │                     # Base from §7 of graph-mcp-skills-and-paysafe-resolution.md,
            │                     # EXTENDED per redesign §6.6–6.7 to add OPTIONAL MATCH joins
            │                     # to MigrationStep (REQUIRES_STEP) and BreakingScope (HAS_SCOPE)
            ├── deprecation.py    # resolve_deprecation Cypher, entity_evolution Cypher
            │                     # Verbatim from §7 of graph-mcp-skills-and-paysafe-resolution.md
            ├── search.py         # Hydration Cypher for hybrid search results
            │                     # Verbatim from §7 of graph-mcp-skills-and-paysafe-resolution.md
            ├── schema.py         # execute_custom_cypher blocked-keyword check + READ session;
            │                     # get_graph_schema returns static schema string (no Cypher)
            ├── community.py      # submit, query, vote, verify Cypher
            │                     # Verbatim from §7 of graph-mcp-skills-and-paysafe-resolution.md
            ├── context.py        # MigrationContext MERGE/update Cypher, get_pending_steps Cypher
            │                     # Source: redesign §6.1–6.5 (these tools are new; no legacy Cypher)
            └── artifacts.py      # list_pipeline_runs: MATCH (v:Version) WHERE v.rawMdPath IS NOT NULL
                                  # get_artifact_content: MATCH (v:Version {framework, version})
                                  #   RETURN v.rawMdPath, v.filteredMdPath, v.entitiesJsonPath

tests/
└── mcp/
    ├── test_upgrade.py           # analyze_upgrade_path and build_recipe_plan with mocked graph
    ├── test_deprecation.py       # resolve_deprecation and entity_evolution with mocked graph
    ├── test_search.py            # hybrid search with mocked FTS, vector, and hydration calls
    ├── test_schema.py            # execute_custom_cypher mutation blocking; get_graph_schema
    ├── test_community.py         # submit_migration_insight duplicate detection; vote; verify
    ├── test_context.py           # create → get_pending_steps → update_step_status round-trip
    ├── test_paysafe_tool.py      # delegation: assert paysafe tool calls resolve() with correct args
    ├── test_artifacts.py         # list_pipeline_runs; get_artifact_content path resolution
    └── test_server.py            # startup sequence: connectivity check, index setup, tool registration

Required artifacts:
- data-model.md: ToolResponse (generic wrapper), UpgradePathResult, RecipePlanResult,
  DeprecationCard, EntityEvolutionTimeline, SearchResult, GraphSchema, CypherResult,
  InsightSubmitResult, InsightQueryResult, MigrationContextResult, PendingStepsResult,
  StepStatusResult, ScopeTierResult, ArtifactListResult, ArtifactContentResult.
  Also document: all MCP tool parameter types, artifact_type enum (raw_md | filtered_md |
  entities_json), outcome enum (completed | skipped | failed).
- contracts/005-mcp-server.md:
  (a) mcp/tools/paysafe.py may only import migration_oracle.paysafe.resolver.resolve —
      not findit.py, gitlab.py, or any other paysafe internal
  (b) mcp/tools/artifacts.py must not read filesystem paths supplied by callers —
      paths must be resolved from Version node properties only
  (c) mcp/graph/queries/ modules must not import from mcp/tools/ — dependency is
      one-way: tools → queries
  (d) execute_custom_cypher must block mutation keywords in Python before query leaves
      the process — READ session is a secondary guard, not the only guard
  (e) The embedding model must be a module-level lazy singleton — no per-call instantiation
- research.md: choice of MCP framework (fastmcp vs mcp-python vs raw stdio);
  sentence-transformers loading strategy (lazy vs eager at startup);
  how to run FTS + vector queries in parallel vs sequential in hybrid search;
  Memgraph-specific index DDL compatibility gaps and mitigation
- quickstart.md: how to start the server in stdio mode and connect a test client;
  required env vars (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, MCP_TRANSPORT, MCP_HOST,
  MCP_PORT, SENTENCE_TRANSFORMERS_MODEL, FINDIT_AUTH_TOKEN, GITLAB_API_KEY);
  how to run the test suite with mocked graph (no running Neo4j required);
  how to verify all 21 tools register with `--list-tools` or equivalent

Tech stack: Python 3.11+, uv, pytest, mcp (the MCP Python SDK), sentence-transformers,
neo4j (Python driver from 001-foundations), httpx for any HTTP within tools.

Plan must include [P] parallelism markers:
- All tool group files (upgrade.py, deprecation.py, search.py, schema.py, community.py,
  context.py, paysafe.py, artifacts.py, install.py) can be implemented in parallel
  after their corresponding graph/queries/ modules exist.
- All graph/queries/ modules can be implemented in parallel with each other.
- All test files can be implemented in parallel with each other after their corresponding
  tool modules are done.
- server.py depends on all tool modules being complete — implement last.
```

---

## Gap Review — Post-Plan

After `/speckit.plan` generates the plan artifacts, paste:

```
Review the generated plan.md, data-model.md, contracts/005-mcp-server.md, and
quickstart.md for 005-mcp-server and fix any of the following gaps:

PLAN-GAP-001: data-model.md covers all 21 tool return types
  data-model.md must have a named type for the return value of every one of the 21 tools.
  If any tool's return type is described as "dict" or "any", replace it with a named type
  that lists its fields. Check especially: get_steps_for_scope_tier (must show entities[]
  and rule_count), update_step_status (must show completedCount, skippedCount, status),
  get_artifact_content (must show content as string, artifact_type, path_resolved).

PLAN-GAP-002: execute_custom_cypher blocked keyword list in data-model.md
  data-model.md or contracts/ must document the exact list of blocked keywords for
  execute_custom_cypher: CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL db (prefix).
  If the list is missing or incomplete, add it.

PLAN-GAP-003: Embedding singleton location
  plan.md must specify that get_embedding_model() lives in mcp/tools/search.py as a
  module-level function with a module-level _model variable initialized to None.
  If the plan describes embedding loading elsewhere (e.g. in server.py or a shared
  utils.py), move it to search.py.

PLAN-GAP-004: Artifact path resolution flow
  plan.md must describe the two-step flow for get_artifact_content:
  Step 1 — query graph for Version node matching (framework, version);
  Step 2 — read file at the path from the matching property (rawMdPath / filteredMdPath /
  entitiesJsonPath). If the plan skips step 1 and reads from a caller-supplied path,
  correct it.

PLAN-GAP-005: Contracts write boundary for artifacts
  contracts/005-mcp-server.md must state: "mcp/tools/artifacts.py must not accept
  file paths from callers. All file paths are read from Version node properties only."
  If absent, add it.

PLAN-GAP-006: Contracts query module one-way dependency
  contracts/005-mcp-server.md must state: "mcp/graph/queries/ modules must not import
  from mcp/tools/. The dependency is tools → queries, never queries → tools."
  If absent, add it.

PLAN-GAP-007: MigrationContext auto-close logic documented
  plan.md must describe how update_step_status auto-closes the context: after writing
  the outcome, application code checks whether any pending steps remain by comparing
  (completedSteps + skippedSteps + failedSteps) against the full step set for the
  version range. If no pending steps remain, status is set to "complete". If this
  logic is absent or says "handled by graph trigger", move it to application code.

PLAN-GAP-008: Quickstart env vars complete
  quickstart.md must list all required env vars: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
  MCP_TRANSPORT (default stdio), MCP_HOST (default 0.0.0.0), MCP_PORT (default 8001),
  MCP_STATELESS_HTTP, SENTENCE_TRANSFORMERS_MODEL (default all-mpnet-base-v2),
  FINDIT_AUTH_TOKEN, GITLAB_API_KEY, POPULATE_MIGRATION_EMBEDDINGS,
  FINDIT_SERVICE_NAME_FUZZY_THRESHOLD. If any are missing, add them.

PLAN-GAP-009: Parallel markers correct
  plan.md must mark all mcp/graph/queries/ implementation tasks [P] relative to each other.
  All mcp/tools/ implementation tasks (except server.py) must be marked [P].
  All test files must be marked [P] relative to each other.
  server.py must NOT be marked [P] — it depends on all tool modules.
  If any parallelism marker is wrong, fix it.

PLAN-GAP-010: Python version
  plan.md must state Python 3.11+ as the minimum runtime. If absent, add it.

PLAN-GAP-011: mcp/graph/queries/ has all required modules
  plan.md must list all seven query modules:
  upgrade.py, deprecation.py, search.py, schema.py, community.py, context.py, artifacts.py.
  If schema.py or artifacts.py are absent, add them with their described purpose:
  schema.py — execute_custom_cypher blocked-keyword logic + static schema string for get_graph_schema;
  artifacts.py — Version node lookup Cypher for list_pipeline_runs and get_artifact_content.

PLAN-GAP-012: upgrade.py Cypher is extended, not verbatim
  plan.md must state that mcp/graph/queries/upgrade.py starts from the reference Cypher
  in graph-mcp-skills-and-paysafe-resolution.md §7 but extends it with:
  (a) OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep) — collect as steps[] per rule
  (b) OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope) — collect as scopes[] per rule
  (c) scope_filter and min_severity WHERE guards on BreakingScope when non-empty/non-null
  If the plan says "copy Cypher verbatim from reference docs" without these additions, fix it.

PLAN-GAP-013: context.py Cypher sourced from redesign, not reference docs
  plan.md must note that mcp/graph/queries/context.py Cypher comes from
  migration-oracle-redesign.md §6.1–6.5, not from graph-mcp-skills-and-paysafe-resolution.md
  (which predates the context tools). If the plan cites the wrong document for context
  Cypher, correct it.

PLAN-GAP-014: framework_migration_main.md content is specified in plan
  plan.md must describe what framework_migration_main.md must contain: the four-loop
  harness from redesign §7 including all four loop descriptions and the decision tables
  from §7.5. It is not acceptable for plan.md to say "copy existing skill content" —
  the main skill is being rewritten as Increment 3. If absent, add the content spec.

PLAN-GAP-015: Backward compat contract in contracts/
  contracts/005-mcp-server.md must state the three backward compat guarantees:
  (a) 14 existing tool parameter signatures are frozen (list them or reference §8),
  (b) AUTOMATED_BY edges are absent in the first release — tools must produce correct
      output (empty auto track, empty recipes arrays) with zero such edges,
  (c) actionStep on existing MigrationRule nodes is readable — tools must not block it.
  If these are absent, add them.

PLAN-GAP-016: Increment 3 test in plan
  plan.md must include a test task for the Increment 3 skill validation from redesign §9:
  run a full migration session, interrupt mid-way, resume with the same projectId, verify
  that no completed steps are re-executed and that ctx.completedSteps is correct.
  If this test scenario is absent, add it under tests/mcp/test_skill_harness.py.
```

---

## Command 3 — `/speckit.tasks`

After plan artifacts are clean:

```
/speckit.tasks
```

No additional arguments needed — it reads spec.md and plan.md automatically.

---

## Gap Review — Post-Tasks

After `/speckit.tasks` generates `tasks.md`, paste:

```
Review the generated tasks.md for 005-mcp-server and fix any of the following:

TASK-GAP-001: Foundation-first ordering
  Tasks for mcp/graph/queries/ modules must appear BEFORE the corresponding mcp/tools/
  modules. Tools import from queries — the queries must exist first. If any tool task
  appears before its query module task, reorder it.

TASK-GAP-002: server.py last
  The task for mcp/server.py must appear AFTER all mcp/tools/ module tasks. server.py
  imports from every tool module. If server.py appears before any tool task, move it last.

TASK-GAP-003: Embedding singleton task discrete
  There must be a discrete task for implementing get_embedding_model() in search.py,
  including the module-level _model=None variable and the lazy-load check.
  If this is folded into a generic "implement search tools" task, split it out.

TASK-GAP-004: execute_custom_cypher mutation blocking task
  There must be a discrete task for implementing the blocked-keyword check in
  execute_custom_cypher, including a test that verifies each of the 7 blocked keywords
  (CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL db) returns an error.
  If this is absent, add it.

TASK-GAP-005: Startup sequence task
  There must be a task for server.py startup that covers all three steps in order:
  load config → verify connectivity → ensure indexes. The task must reference
  test_server.py verifying that the server raises on connectivity failure.
  If this is a vague "implement server.py" task, expand it.

TASK-GAP-006: Context round-trip E2E test task
  There must be one end-to-end test task that exercises:
  create_migration_context → get_pending_steps → update_step_status (completed)
  → update_step_status (skipped) → get_pending_steps (verify excluded) →
  close_migration_context (verify status). If this round-trip is not covered as a
  single test scenario, add it.

TASK-GAP-007: Artifact path resolution test
  There must be a test task in test_artifacts.py that verifies get_artifact_content
  queries the graph for the path first and only reads the file at the graph-resolved
  path — not a caller-supplied path. If absent, add it.

TASK-GAP-008: Paysafe delegation test
  There must be a test task in test_paysafe_tool.py that mocks resolve() and asserts
  that the MCP tool passes the correct arguments to resolve() without any additional
  processing. If absent, add it.

TASK-GAP-009: Skill resources loaded at startup
  There must be a task for loading all four skill Markdown files from mcp/skills/ into
  memory at server startup and registering them as MCP resources. This task must reference
  a test that verifies all four URIs are served. If absent, add it.

TASK-GAP-010: File path correctness
  Every task that creates a file must reference the exact path from plan.md:
  migration_oracle/mcp/server.py, migration_oracle/mcp/tools/<name>.py,
  migration_oracle/mcp/skills/<name>.md, migration_oracle/mcp/graph/queries/<name>.py,
  tests/mcp/test_<name>.py. If any task uses a flat or wrong path, correct it.

TASK-GAP-011: Absent AUTOMATED_BY and pre-redesign data tested
  There must be test tasks (in test_upgrade.py) covering these three absence cases:
  (a) No MigrationStep nodes: analyze_upgrade_path returns steps=[] per rule without error;
      build_recipe_plan returns empty auto track and manual track of rule-level cards.
  (b) MigrationStep nodes present but no AUTOMATED_BY edges: build_recipe_plan returns
      empty auto track and all steps in manual track — this is the expected first-release
      behavior and must not raise or return an error.
  (c) Old MigrationRule nodes with actionStep property: actionStep appears in the
      rule-level manual track card.
  If any of these cases are not tested, add them.

TASK-GAP-012: framework_migration_main.md four-loop content task
  There must be a discrete implementation task for writing the four-loop harness content
  into mcp/skills/framework_migration_main.md, covering all four loops with their decision
  tables. This is Increment 3 of the redesign and is not a copy of the old skill content.
  If absent, add it as a separate task that references redesign §7.

TASK-GAP-013: Interrupt+resume test for skill harness (redesign §9 Increment 3 validation)
  There must be a test task in tests/mcp/test_skill_harness.py (or equivalent) that:
  (1) simulates a migration session completing some steps and writing them to ctx.completedSteps,
  (2) creates a new Loop I invocation with the same projectId,
  (3) verifies that the resumed session skips already-completed steps and only executes
      the remaining ones.
  This is the exact validation from redesign §9 Increment 3. If absent, add it.
```

---

## Command 4 — `/speckit.implement`

After tasks.md is clean:

```
/speckit.implement
```

---

## Recovery Prompts

Use these verbatim if Claude Code's implementation drifts from the spec.

---

### Recovery 1 — Embedding model instantiated per call

```
Do not instantiate SentenceTransformer inside any tool handler function or per-call
code path. The embedding model must be a module-level variable in
migration_oracle/mcp/tools/search.py, initialized to None, and loaded once via
get_embedding_model() on first use:

    _model: SentenceTransformer | None = None

    def get_embedding_model() -> SentenceTransformer:
        global _model
        if _model is None:
            _model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)
        return _model

Every call to embed a search query must go through get_embedding_model(), never through
a local variable instantiation. If you have SentenceTransformer(...) inside any function
body other than get_embedding_model(), remove it.
```

---

### Recovery 2 — execute_custom_cypher allows mutations

```
The execute_custom_cypher tool must check the query string for mutation keywords before
sending it to the graph. The check must happen in Python, not solely at the graph level.
Add this guard at the top of the tool handler:

    BLOCKED = {"CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP"}
    upper = query.upper()
    if any(kw in upper for kw in BLOCKED) or "CALL DB" in upper:
        return {"error": "Read-only queries only. Blocked keyword detected."}

Do not proceed with a READ session as the only safeguard — the keyword check is required
even when the graph session is in READ mode, because the database-level READ mode is not
guaranteed to block all mutation forms on all Neo4j/Memgraph versions.
```

---

### Recovery 3 — mcp/tools/paysafe.py contains resolution logic

```
mcp/tools/paysafe.py must not contain any FindIt lookup, GitLab tag enumeration,
compatibility checking, or selection strategy logic. All of that lives in
migration_oracle/paysafe/resolver.py.

The tool handler must be a thin wrapper:

    from migration_oracle.paysafe.resolver import resolve

    def resolve_paysafe_dependency_by_service_name(service_name, target_version=None,
            allow_latest_overall=False, framework="auto"):
        if target_version is None:
            allow_latest_overall = True
        return resolve(service_name, target_version=target_version,
                       allow_latest_overall=allow_latest_overall, framework=framework)

Nothing else. Remove any resolution logic you have added to this file.
```

---

### Recovery 4 — get_artifact_content reads a caller-supplied path

```
get_artifact_content must NOT accept a file path from the caller. The caller supplies
(framework, version, artifact_type). The tool queries the graph for the matching Version
node and reads the path from the node's rawMdPath, filteredMdPath, or entitiesJsonPath
property. Only then is the file read.

The query must be:

    MATCH (v:Version {framework: $framework, version: $version})
    RETURN v.rawMdPath, v.filteredMdPath, v.entitiesJsonPath

If the caller could supply an arbitrary path and the tool reads it directly, this is a
path traversal vulnerability. Replace any direct path parameter with a graph-lookup step.
```

---

### Recovery 5 — Cypher inlined in tool handlers instead of query modules

```
Do not write Cypher strings inside mcp/tools/*.py handler functions. All Cypher must
live in mcp/graph/queries/<group>.py and be imported by the corresponding tool module.

Correct structure:
    # mcp/graph/queries/upgrade.py
    ANALYZE_UPGRADE_PATH_CYPHER = """
    MATCH (v:Version {framework: $framework}) ...
    """
    def run_analyze_upgrade_path(session, params): ...

    # mcp/tools/upgrade.py
    from migration_oracle.mcp.graph.queries.upgrade import run_analyze_upgrade_path

    async def analyze_upgrade_path(current_version, target_version, ...):
        with get_session() as session:
            return run_analyze_upgrade_path(session, {...})

If you have Cypher strings inside tool handler functions, extract them to the appropriate
mcp/graph/queries/ module.
```

---

### Recovery 6 — analyze_upgrade_path returns no steps or scopes

```
The analyze_upgrade_path tool is returning rules with empty steps[] and scopes[] even
when the graph has MigrationStep and BreakingScope nodes. The Cypher in
mcp/graph/queries/upgrade.py is missing the redesign additions.

Add these OPTIONAL MATCH clauses to the existing query, after the existing rule joins:

    OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
    OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
      WHERE size($scope_filter) = 0 OR bs.scope IN $scope_filter
      AND ($min_severity IS NULL OR
           CASE bs.severity
             WHEN 'critical' THEN 3 WHEN 'high' THEN 2
             WHEN 'medium'   THEN 1 ELSE 0
           END >=
           CASE $min_severity
             WHEN 'critical' THEN 3 WHEN 'high' THEN 2
             WHEN 'medium'   THEN 1 ELSE 0
           END)

Then add to the RETURN clause:
    collect(DISTINCT {
        stepType: s.stepType, summary: s.summary, instruction: s.instruction,
        effort: s.effort, automatable: s.automatable,
        verificationHint: s.verificationHint
    }) AS steps,
    collect(DISTINCT {scope: bs.scope, severity: bs.severity}) AS scopes

Filter nulls from steps and scopes with [x IN steps WHERE x.summary IS NOT NULL].
```

---

### Recovery 7 — build_recipe_plan errors or warns when AUTOMATED_BY edges are absent

```
build_recipe_plan must not raise, warn, or return an error when no AUTOMATED_BY edges
exist in the graph. AUTOMATED_BY is populated by a separate recipe-mapping job that
runs after the initial deployment. In the first release it will be absent entirely.

The correct behavior when AUTOMATED_BY edges are absent:
  - auto_track.recipes = []
  - auto_track.rewrite_yml = "" (empty string or omitted)
  - manual_track contains all MigrationStep cards (or rule-level cards if no steps exist)
  - summary.auto_track_size = 0

The Cypher must use OPTIONAL MATCH for both the step join and the recipe join:

    OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
    OPTIONAL MATCH (s)-[ab_s:AUTOMATED_BY]->(rec_s:OpenRewriteRecipe)

A step goes to the auto track only when ab_s IS NOT NULL AND ab_s.auto = true
AND (ab_s.missingRequiredParams IS NULL OR ab_s.missingRequiredParams = []).
When ab_s IS NULL, the step goes to manual — this is the expected first-release path.

If build_recipe_plan has any branch that treats NULL ab_s as an error, or returns a
non-200 / error-shaped response when no recipe edges exist, remove that branch.
```

---

### Recovery 9 — framework_migration_main.md still uses five sequential phases

```
The mcp/skills/framework_migration_main.md content still describes five sequential
phases (resolve inputs → scan → query → synthesise → output). This is the OLD harness.
Per redesign §7, it must be replaced by four re-entrant loops:

Loop I (Context): create_migration_context or resume by projectId; run codebase scan;
  diff entities if resuming; surface toolchain gates from version-map; gate — no graph
  calls before this loop completes.

Loop II (Scope-gated query): 4 tiers (api-surface/high+critical → runtime/medium+ →
  config+build/all → test/all). For each tier: get_steps_for_scope_tier → analyze_upgrade_path
  → resolve_deprecation per removed entity → entity_evolution if partial chain.
  Skip guard: check ctx.queriedEntities before every tool call.
  Run Paysafe resolution concurrently with tier 1.

Loop III (Execution): get_pending_steps → route each step: auto/prompted/manual/design-gate/
  blocked/rollback. Call update_step_status after every step result.

Loop IV (Feedback): submit_migration_insight for deviations; emit backlog for skipped steps
  where effort≠test; close_migration_context with final_status.

The decision tables from redesign §7.5 must appear verbatim in the skill content.
Delete the five-phase structure entirely. The new loops are re-entrant — the agent can
restart at any loop boundary and skip already-completed work.
```

---

### Recovery 10 — Backward compat broken: existing tool parameter removed or renamed

```
An existing tool parameter has been removed or renamed. The backward compatibility
contract (redesign §8) requires that all 14 existing tool parameter signatures are
frozen. New parameters (scope_filter, min_severity on analyze_upgrade_path) are additive
and optional — they must not replace or rename any existing parameter.

Check: analyze_upgrade_path must still accept current_version, target_version, framework,
user_entities, format, classification, include_recipes, include_lifecycle, top_n, verbose.
build_recipe_plan must still accept current_version, target_version, framework,
user_entities, auto_only, classification.

Restore any removed or renamed parameter and make the new parameter an additional optional
argument with a default that reproduces the original behavior when omitted.
```

---

### Recovery 11 — MigrationContext auto-close not implemented in application code

```
The auto-close logic for update_step_status must run in application code, not as a
graph trigger or stored procedure. After writing the outcome to ctx.completedSteps,
ctx.skippedSteps, or ctx.failedSteps, application code must check:

    pending = get_pending_steps(context_id, effort_filter=[], scope_filter=[])
    if len(pending) == 0:
        SET ctx.status = "complete", ctx.completedAt = datetime()

This check must be part of the update_step_status tool handler, called after the Cypher
write completes. Do not rely on a graph procedure, APOC trigger, or external scheduler
to close the context automatically.
```

---

## What Success Looks Like

Run the following checks after `/speckit.implement` completes.
All must pass before marking `005-mcp-server` ✅ Complete in `docs/SPEC_ORGANIZATION.md`.

### 1. All 21 tools register at startup

Start the server and verify no registration errors:

```bash
uv run python -m migration_oracle.mcp.server --list-tools
```

Expected: 21 tool names printed with no errors. The list must include:
`analyze_upgrade_path`, `build_recipe_plan`, `resolve_deprecation`, `entity_evolution`,
`search_migration_knowledge`, `search_openrewrite_recipes`, `get_graph_schema`,
`execute_custom_cypher`, `submit_migration_insight`, `get_community_insights`,
`vote_insight`, `verify_insight`, `create_migration_context`, `get_pending_steps`,
`update_step_status`, `get_steps_for_scope_tier`, `close_migration_context`,
`resolve_paysafe_dependency_by_service_name`, `list_pipeline_runs`,
`get_artifact_content`, `install_migration_skill`.

### 2. Mutation blocking

```python
from migration_oracle.mcp.tools.schema import execute_custom_cypher

for keyword in ["CREATE (n) RETURN n", "MERGE (n) RETURN n", "SET n.x = 1",
                "DELETE n", "REMOVE n.x", "DROP INDEX idx", "CALL db.indexes()"]:
    result = execute_custom_cypher(keyword)
    assert "error" in result or result.get("status") == "error", \
        f"Expected blocked for: {keyword}"
```

### 3. Embedding singleton (no double-load)

```python
from migration_oracle.mcp.tools.search import get_embedding_model

m1 = get_embedding_model()
m2 = get_embedding_model()
assert m1 is m2, "get_embedding_model() must return the same object on every call"
```

### 4. Paysafe tool delegation (no logic in tool)

```python
from unittest.mock import patch, call
from migration_oracle.mcp.tools.paysafe import resolve_paysafe_dependency_by_service_name

with patch("migration_oracle.mcp.tools.paysafe.resolve") as mock_resolve:
    mock_resolve.return_value = {"status": "ok"}
    resolve_paysafe_dependency_by_service_name("my-service", target_version="3.5.6")
    mock_resolve.assert_called_once()
    _, kwargs = mock_resolve.call_args
    assert kwargs.get("target_version") == "3.5.6"
```

### 5. Context round-trip (requires running Neo4j or Memgraph)

```python
from migration_oracle.mcp.tools.context import (
    create_migration_context, get_pending_steps, update_step_status, close_migration_context
)

ctx = create_migration_context(
    project_id="test-project",
    from_version="3.3.0",
    to_version="3.4.0",
    framework="Spring Boot",
    scanned_entities=["org.springframework.security.WebSecurityConfigurerAdapter"]
)
assert ctx["status"] in ("created", "resumed")
context_id = ctx["contextId"]

steps = get_pending_steps(context_id)
if steps:
    step_id = steps[0]["stepId"]
    result = update_step_status(context_id, step_id, outcome="completed")
    assert result["completedCount"] >= 1
    remaining = get_pending_steps(context_id)
    assert not any(s["stepId"] == step_id for s in remaining)

close_result = close_migration_context(context_id, final_status="partial",
                                       notes="Smoke test complete")
assert close_result["status"] in ("partial", "complete")
```

### 6. Interrupt+resume (Increment 3 validation — redesign §9)

This test requires a running Neo4j/Memgraph with MigrationStep nodes (i.e. Increment 1
pipeline must have been run for the target version range). It validates that the four-loop
skill harness is interrupt-safe.

```python
from migration_oracle.mcp.tools.context import (
    create_migration_context, get_pending_steps, update_step_status
)

# Phase 1 — simulate a partial session
ctx = create_migration_context(
    project_id="resume-test",
    from_version="3.2.0",
    to_version="3.4.0",
    framework="Spring Boot",
    scanned_entities=["org.springframework.security.WebSecurityConfigurerAdapter",
                      "spring.datasource.url"]
)
context_id = ctx["contextId"]
steps = get_pending_steps(context_id)
assert len(steps) > 0, "Need MigrationStep nodes in graph for this test"

# Mark first step completed — simulating mid-session interrupt after step 1
first_step_id = steps[0]["stepId"]
update_step_status(context_id, first_step_id, outcome="completed", reason="smoke test")

# Phase 2 — resume: load same context by projectId (what Loop I does)
resumed = create_migration_context(
    project_id="resume-test",        # same projectId — must resume, not recreate
    from_version="3.2.0",
    to_version="3.4.0",
    framework="Spring Boot",
    scanned_entities=["org.springframework.security.WebSecurityConfigurerAdapter",
                      "spring.datasource.url"]
)
assert resumed["status"] == "resumed", "Expected resumed, not created"
assert first_step_id in resumed["completedSteps"], "Completed step must survive resume"

# Pending queue must NOT include the completed step
remaining = get_pending_steps(context_id)
assert not any(s["stepId"] == first_step_id for s in remaining), \
    "Completed step must be absent from pending queue after resume"
```

### 7. Full test suite

```bash
pytest tests/mcp/ -v
```

All tests must pass. Look especially for:
- `test_server.py::test_startup_sequence` — config → connectivity → indexes in order
- `test_schema.py::test_blocked_keywords_*` — all 7 blocked patterns rejected
- `test_search.py::test_embedding_singleton` — same object returned twice
- `test_context.py::test_round_trip` — create → update → verify excluded → close
- `test_paysafe_tool.py::test_delegates_to_resolve` — no extra logic in tool
- `test_artifacts.py::test_path_from_graph_not_caller` — path resolved from Version node

---

## Updating `docs/SPEC_ORGANIZATION.md`

Once all smoke tests pass, update the status table:

```
| `005` | MCP Server | ✅ Complete | `specs/005-mcp-server/` |
```

Then create `specs/005-mcp-server/` with the SpecKit artifacts from this run
(spec.md, plan.md, data-model.md, contracts/, tasks.md, research.md, quickstart.md).

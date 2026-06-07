# Implementation Plan: PaysafeMigrationOracle MCP Server

**Branch**: `005-mcp-server` | **Date**: 2026-06-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-mcp-server/spec.md`

---

## Summary

Implement the `PaysafeMigrationOracle` MCP server (`migration_oracle/mcp/`) exposing 21 tools, 4 skill resources, and 1 prompt via the official `mcp>=1.0` SDK (`FastMCP`). The server adds context-management tools, scope-filter/min-severity parameters on upgrade tools, step-level Cypher joins via `OPTIONAL MATCH`, and a rewritten four-loop agent harness skill (`framework_migration_main.md`). All 14 existing tool parameter signatures are frozen; backward compatibility with pre-redesign graph data is mandatory.

---

## Technical Context

**Language/Version**: Python 3.11+ (already enforced in `pyproject.toml`)

**Primary Dependencies**: `mcp>=1.0` (FastMCP), `neo4j>=5.0` (driver, already present), `sentence-transformers>=3.0` (already present), `httpx>=0.27` (already present), `structlog>=24.0` (already present)

**Storage**: Neo4j 5.x / Memgraph — graph driver singleton pattern from `migration_oracle/graph/driver.py`

**Testing**: `pytest>=8.0`, `pytest-asyncio>=0.23`, `pytest-mock>=3.14` (all already in `pyproject.toml` dev deps)

**Target Platform**: Linux server (primary), macOS (development); `MCP_TRANSPORT=stdio` for Claude Code / Cursor

**Project Type**: MCP server (library + server process)

**Performance Goals**: SC-001: ≤ 2 seconds for graph queries on populated test dataset; SC-007: hybrid search latency increase ≤ 10% on 10th concurrent call vs 1st

**Constraints**: Backward compatibility (FR-038, FR-039, FR-040, FR-044); `OPTIONAL MATCH` on all new node type joins; no mutation in READ-only tools

**Scale/Scope**: 21 tools; 4 skill resources; 1 prompt; up to 10 concurrent agent connections (SC-004)

**Config addition required**: `MCP_STATELESS_HTTP` boolean must be added to `migration_oracle/config.py` (currently missing). See `research.md §5`.

---

## Constitution Check

The project constitution (`constitution.md`) is a blank template — no project-specific gates are defined. No violations to evaluate. Proceeding.

---

## Project Structure

### Documentation (this feature)

```text
specs/005-mcp-server/
├── plan.md              ← this file
├── spec.md              ← feature specification
├── research.md          ← Phase 0: MCP framework, embedding, search, Memgraph gaps
├── data-model.md        ← Phase 1: all return types, parameter types, enums
├── quickstart.md        ← Phase 1: startup, env vars, test client, tool verification
├── contracts/
│   └── 005-mcp-server.md  ← Phase 1: module boundary contracts A–F
├── checklists/
│   └── requirements.md
└── tasks.md             ← Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code

```text
migration_oracle/
├── config.py              ← Add MCP_STATELESS_HTTP bool (single line change)
└── mcp/
    ├── __init__.py
    ├── server.py          ← Entry point: FastMCP setup, startup sequence, transport
    ├── tools/
    │   ├── __init__.py
    │   ├── upgrade.py     ← analyze_upgrade_path, build_recipe_plan
    │   ├── deprecation.py ← resolve_deprecation, entity_evolution
    │   ├── search.py      ← search_migration_knowledge, search_openrewrite_recipes,
    │   │                      _model singleton, get_embedding_model()
    │   ├── schema.py      ← get_graph_schema, execute_custom_cypher
    │   ├── community.py   ← submit_migration_insight, get_community_insights,
    │   │                      vote_insight, verify_insight
    │   ├── context.py     ← create_migration_context, get_pending_steps,
    │   │                      update_step_status, get_steps_for_scope_tier,
    │   │                      close_migration_context
    │   ├── paysafe.py     ← resolve_paysafe_dependency_by_service_name
    │   ├── artifacts.py   ← list_pipeline_runs, get_artifact_content
    │   └── install.py     ← install_migration_skill
    ├── skills/
    │   ├── framework_migration_main.md       ← four-loop harness (Increment 3)
    │   ├── framework_migration_scanning.md
    │   ├── framework_migration_plan_format.md
    │   └── framework_migration_version_map.md
    └── graph/
        └── queries/
            ├── __init__.py
            ├── upgrade.py      ← analyze_upgrade_path + build_recipe_plan Cypher
            ├── deprecation.py  ← resolve_deprecation + entity_evolution Cypher
            ├── search.py       ← BM25, vector, hydration Cypher
            ├── schema.py       ← execute_custom_cypher blocking + static schema
            ├── community.py    ← insight CRUD Cypher
            ├── context.py      ← MigrationContext MERGE/query/update Cypher
            └── artifacts.py    ← Version artifact path query Cypher

tests/
└── mcp/
    ├── test_upgrade.py
    ├── test_deprecation.py
    ├── test_search.py
    ├── test_schema.py
    ├── test_community.py
    ├── test_context.py
    ├── test_paysafe_tool.py
    ├── test_artifacts.py
    ├── test_server.py
    └── test_skill_harness.py
```

---

## Implementation Phases

### Phase P-0 — Config patch (no parallelism, 1 file, prerequisite for everything)

**Task P-0.1**: Add `MCP_STATELESS_HTTP` to `migration_oracle/config.py`

```python
MCP_STATELESS_HTTP: bool = _parse_bool_flag(_optional("MCP_STATELESS_HTTP", "false"))
```

This is a single-line addition. No other config changes are needed for spec 005.

---

### Phase P-1 — Graph query modules (all parallel with each other)

All `mcp/graph/queries/` modules can be implemented simultaneously. They import only from `migration_oracle.graph.driver` and `migration_oracle.config`. None depends on another.

**[P] Task P-1.1**: `mcp/graph/queries/upgrade.py`

Cypher base: `docs/graph-mcp-skills-and-paysafe-resolution.md §7` `analyze_upgrade_path` and `build_recipe_plan` queries.

Extensions required by spec:

_For `analyze_upgrade_path`_: After the existing `MATCH` and `WHERE` clauses for rules, add:
```cypher
OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
OPTIONAL MATCH (rule)-[:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
```
Collect `s`, `bs`, `rec` in `RETURN` as `steps`, `scopes`, `recipes` lists.

For `scope_filter` (non-empty): add a `WITH` clause that filters `rules` keeping only those where `ANY(scope IN bs_list WHERE scope IN $scope_filter)`.

For `min_severity`: map severity to numeric rank (`critical=4, high=3, medium=2, low=1`) and filter `bs_list` by rank ≥ threshold rank.

_For `build_recipe_plan`_: Add step-level joins:
```cypher
OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab_s:AUTOMATED_BY]->(rec_s:OpenRewriteRecipe)
```
Auto-track condition: `s.automatable = true AND s.effort = 'mechanical' AND ab_s IS NOT NULL AND ab_s.auto = true AND size(ab_s.missingRequiredParams) = 0`. When `ab_s IS NULL`, step goes to manual track. When no `MigrationStep` nodes: return rule-level cards using `actionStep`.

**[P] Task P-1.2**: `mcp/graph/queries/deprecation.py`

Source: `docs/graph-mcp-skills-and-paysafe-resolution.md §7` — `resolve_deprecation` and `entity_evolution` queries. Copy verbatim; no extensions required.

**[P] Task P-1.3**: `mcp/graph/queries/search.py`

Contains:
- `bm25_search(query: str, index: str, top_k: int) -> list[str]` — runs `db.index.fulltext.queryNodes`; returns list of elementIds
- `vector_search(embedding: list[float], index: str, top_k: int, min_similarity: float) -> list[str]` — runs `db.index.vector.queryNodes`; returns list of elementIds; catches `ClientError` (Memgraph) and returns `[]`
- `hydrate_nodes(element_ids: list[str]) -> list[dict]` — `MATCH (n) WHERE elementId(n) IN $ids RETURN n`

Source: `docs/graph-mcp-skills-and-paysafe-resolution.md §7` hybrid search queries.

**[P] Task P-1.4**: `mcp/graph/queries/schema.py`

Contains:
- `MUTATION_KEYWORDS`: `["CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP"]` plus prefix check for `CALL db`
- `check_mutation(query: str) -> str | None` — returns the matched keyword if blocked, else `None`; case-insensitive
- `execute_read_cypher(query: str, params: dict) -> list[dict]` — opens `read_session()`, runs query, returns rows
- `GRAPH_SCHEMA_MD: str` — module-level constant holding the static schema markdown string (can be loaded from `docs/graph-mcp-skills-and-paysafe-resolution.md §3` at import time via `importlib.resources` or a path relative to the module)

**[P] Task P-1.5**: `mcp/graph/queries/community.py`

Source: `docs/graph-mcp-skills-and-paysafe-resolution.md §7` community tool Cypher (submit, query, vote, verify). Copy verbatim.

Near-duplicate detection: BM25 search on `CommunityInsight` FTS index for the new `statement`; if top hit cosine similarity > 0.92, return the existing `elementId` rather than writing.

**[P] Task P-1.6**: `mcp/graph/queries/context.py`

New queries (redesign §6.1–6.5); no legacy Cypher to copy.

Key queries to implement:

_create_or_get_context_:
```cypher
MERGE (ctx:MigrationContext {projectId: $project_id, fromVersion: $from_version, toVersion: $to_version})
ON CREATE SET
  ctx.framework = $framework,
  ctx.status = 'in-progress',
  ctx.scannedEntities = $scanned_entities,
  ctx.completedSteps = [],
  ctx.skippedSteps = [],
  ctx.queriedEntities = {},
  ctx.createdAt = datetime(),
  ctx.completedAt = null,
  ctx.notes = ''
WITH ctx
MATCH (vf:Version {framework: $framework, version: $from_version})
MATCH (vt:Version {framework: $framework, version: $to_version})
MERGE (ctx)-[:UPGRADES_FROM]->(vf)
MERGE (ctx)-[:UPGRADES_TO]->(vt)
RETURN ctx, elementId(ctx) AS contextId, (ctx.createdAt = datetime()) AS created
```

_get_pending_steps_ — full version range query (redesign §6.2).

Source: redesign §6.2 — NOT `graph-mcp-skills-and-paysafe-resolution.md`. Context tools are new; there is no legacy Cypher to copy for them. The Cypher MUST use `UPGRADES_FROM`/`UPGRADES_TO` edges and `sortableVersion` range comparison to cover ALL intermediate versions in a multi-hop upgrade (e.g., Spring Boot 3.2 → 3.4 spans versions 3.2.x, 3.3.x, 3.4.x). Querying only `toVersion` would return an empty or partial step list for any multi-version upgrade — the primary use case.

```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
WHERE NOT elementId(s) IN ctx.completedSteps
  AND NOT elementId(s) IN ctx.skippedSteps
  AND NOT elementId(s) IN coalesce(ctx.failedSteps, [])
  AND (size($effort_filter) = 0 OR s.effort IN $effort_filter)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
  WHERE size($scope_filter) = 0 OR bs.scope IN $scope_filter
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
  WHERE ab.auto = true AND ab.missingRequiredParams = []
OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
RETURN s, elementId(s) AS stepId, elementId(r) AS ruleId,
       bs.scope AS scope, bs.severity AS severity,
       rec.recipeId AS recipeId,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY
  CASE bs.severity
    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
    WHEN 'medium'   THEN 2 ELSE 3
  END ASC,
  s.stepIndex ASC
```

_record_step_outcome_ (write) — tracks completed, skipped, AND failed steps:
```cypher
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.completedSteps = CASE $outcome WHEN 'completed'
    THEN ctx.completedSteps + [$step_id] ELSE ctx.completedSteps END,
    ctx.skippedSteps = CASE $outcome WHEN 'skipped'
    THEN ctx.skippedSteps + [$step_id] ELSE ctx.skippedSteps END,
    ctx.failedSteps = CASE $outcome WHEN 'failed'
    THEN coalesce(ctx.failedSteps, []) + [$step_id] ELSE coalesce(ctx.failedSteps, []) END
RETURN ctx
```

_auto_close_context_ (application code in handler, NOT a Cypher trigger or graph procedure):

After writing the step outcome, the handler MUST check whether any pending steps remain by comparing `(completedSteps + skippedSteps + failedSteps)` against the full step set for the version range. If `(completedSteps ∪ skippedSteps ∪ failedSteps) = full_step_set` (i.e., no steps remain unresolved), the handler issues a follow-up write:

```python
# After recording step outcome — application code in update_step_status handler:
pending = get_pending_steps(context_id)   # returns steps NOT in completed|skipped|failed
if not pending:
    # Issue a follow-up graph write (not a trigger):
    # SET ctx.status = 'complete', ctx.completedAt = datetime()
    auto_close_write(context_id)
```

The `get_pending_steps` query excludes steps in `completedSteps`, `skippedSteps`, AND `failedSteps`. If the result list is empty, all steps have been resolved (regardless of outcome) and the context is auto-closed. `context_auto_closed=True` is returned in `StepStatusResult`.

**[P] Task P-1.7**: `mcp/graph/queries/artifacts.py`

_list_pipeline_runs_:
```cypher
MATCH (v:Version) WHERE v.rawMdPath IS NOT NULL
RETURN v.framework AS framework, v.version AS version,
       v.rawMdPath AS rawMdPath, v.filteredMdPath AS filteredMdPath,
       v.entitiesJsonPath AS entitiesJsonPath
ORDER BY v.framework, v.sortableVersion
```

_get_version_artifact_path_:
```cypher
MATCH (v:Version {framework: $framework, version: $to_version})
RETURN v.rawMdPath AS rawMdPath, v.filteredMdPath AS filteredMdPath,
       v.entitiesJsonPath AS entitiesJsonPath
```

Note: The tool handler (not the query module) resolves `artifact_type` → property name and reads the file.

---

### Phase P-2 — Tool modules (all parallel after Phase P-1 is complete)

Each `mcp/tools/*.py` module depends only on its corresponding `mcp/graph/queries/*.py` module. All can be implemented simultaneously.

**[P] Task P-2.1**: `mcp/tools/upgrade.py`

Register `@mcp.tool` for `analyze_upgrade_path` and `build_recipe_plan`. Call functions from `mcp.graph.queries.upgrade`. Apply `scope_filter` and `min_severity` post-processing in the handler if not pushed to Cypher layer. Return `UpgradePlanResult` and `RecipePlanResult` shapes from `data-model.md`.

Parameter signature for `analyze_upgrade_path` (frozen + new):
```python
def analyze_upgrade_path(
    framework: str, current_version: str, target_version: str,
    user_entities: list[str] = [],
    format: str = "json",
    classification: str | None = None,
    include_recipes: bool = False,
    include_lifecycle: bool = True,
    top_n: int = 50,
    verbose: bool = False,
    scope_filter: list[str] = [],   # NEW — FR-008
    min_severity: str | None = None,  # NEW — FR-009/FR-010
) -> dict: ...
```

Parameter signature for `build_recipe_plan` (frozen params use reference doc names; see data-model.md):
```python
def build_recipe_plan(
    current_version: str, target_version: str,   # frozen — matches reference doc §2
    framework: str = "Spring Boot",              # frozen
    user_entities: list[str] | None = None,      # frozen
    auto_only: bool = False,                     # frozen
    classification: list[str] = ["actionable", "incomplete"],  # frozen
    scope_filter: list[str] = [],                # NEW — redesign §6.7
    min_severity: str | None = None,             # NEW — redesign §6.7
) -> dict: ...
```

**[P] Task P-2.2**: `mcp/tools/deprecation.py`

Register `resolve_deprecation` and `entity_evolution`. Source Cypher from `mcp.graph.queries.deprecation`. Return `DeprecationResult` and `EntityEvolutionTimeline`.

**[P] Task P-2.3**: `mcp/tools/search.py`

Register `search_migration_knowledge` and `search_openrewrite_recipes`. Contains `_model: SentenceTransformer | None = None` and `get_embedding_model()` — EXACT pattern per FR-017 and Contract E.

Hybrid search flow:
1. `embedding = get_embedding_model().encode(query).tolist()`
2. Issue BM25 and vector queries in parallel via `asyncio.gather()` + thread executor
3. RRF fusion (k=60) on returned elementId lists
4. Hydrate top N nodes via `mcp.graph.queries.search.hydrate_nodes`

**[P] Task P-2.4**: `mcp/tools/schema.py`

Register `get_graph_schema` (returns `GraphSchema` with static markdown, no Cypher) and `execute_custom_cypher`.

For `execute_custom_cypher`:
1. Call `check_mutation(query)` → if blocked, return `CypherResult(status="blocked", blocked_keyword=kw, rows=[], row_count=0)`
2. Open `read_session()` (Layer 2 per Contract D)
3. Execute query
4. Return `CypherResult(status="ok", rows=[...], row_count=n)`

**[P] Task P-2.5**: `mcp/tools/community.py`

Register 4 tools. `submit_migration_insight` must call near-duplicate detection before writing. `vote_insight` and `verify_insight` use write sessions. `get_community_insights` uses read session.

**[P] Task P-2.6**: `mcp/tools/context.py`

Register 5 tools. Critical implementation notes:

- `create_migration_context`: use MERGE Cypher from P-1.6. Return `MigrationContextResult` with `created=True/False`.
- `update_step_status`: after recording outcome via `record_step_outcome()`, call `get_pending_steps()` in application code. If result is empty, issue `auto_close_write()` to set `status='complete'` and `completedAt=datetime()`. Set `context_auto_closed=True` in return. (FR-025, Contract D)
- `close_migration_context`: write `final_status`, `completedAt`, `notes`. Return `CloseContextResult` with shape `{ tool_status: "ok", contextId, migration_status, completedSteps, skippedSteps, completedAt, notes }` per FR-026. Note: `tool_status` is the ok/error discriminator; `migration_status` holds the final context state. Do NOT use a single `status` field for both.

**[P] Task P-2.7**: `mcp/tools/paysafe.py`

```python
from migration_oracle.paysafe.resolver import resolve  # only allowed import (Contract A)

@mcp.tool
def resolve_paysafe_dependency_by_service_name(
    service_name: str,
    target_version: str | None = None,
    framework: str | None = None,
    allow_latest_overall: bool = False,
    max_tags: int = 100,
    pinned_version: str | None = None,
    pinned_tag: str | None = None,
) -> dict:
    return resolve(
        service_name=service_name,
        target_version=target_version,
        framework=framework,
        allow_latest_overall=allow_latest_overall,
        max_tags=max_tags,
        pinned_version=pinned_version,
        pinned_tag=pinned_tag,
    )
```

No additional logic. (Contract A)

**[P] Task P-2.8**: `mcp/tools/artifacts.py`

Register `list_pipeline_runs` and `get_artifact_content`. Contract B enforced:

```python
ARTIFACT_TYPE_MAP = {
    "raw_md": "rawMdPath",
    "filtered_md": "filteredMdPath",
    "entities_json": "entitiesJsonPath",
}

@mcp.tool
def get_artifact_content(
    framework: str, from_version: str, to_version: str, artifact_type: str
) -> dict:
    if artifact_type not in ARTIFACT_TYPE_MAP:
        return {"status": "error", "message": f"Invalid artifact_type: {artifact_type}"}
    paths = get_version_artifact_path(framework=framework, to_version=to_version)
    if paths is None:
        return {"status": "not_found", ...}
    prop = ARTIFACT_TYPE_MAP[artifact_type]
    path = paths.get(prop)
    if not path:
        return {"status": "not_found", ...}
    content = Path(path).read_text()  # path sourced from graph only
    return {"status": "ok", "content": content, "path": path, ...}
```

**[P] Task P-2.9**: `mcp/tools/install.py`

Register `install_migration_skill`. Copies `mcp/skills/*.md` to the Cursor or Claude Code skills directory. Detects target from environment when `target="auto"` (check for `.cursor/` directory → Cursor; check for `~/.claude/` or `.claude/` → Claude Code).

---

### Phase P-3 — Skill Markdown files (parallel with each other, parallel with P-2)

The skill files in `mcp/skills/` are static Markdown served as MCP resources. They do not depend on any Python code. Three files are copied unchanged from existing skills; one is new.

**[P] Task P-3.1**: `mcp/skills/framework_migration_scanning.md` — Copy from existing skill; no changes.

**[P] Task P-3.2**: `mcp/skills/framework_migration_plan_format.md` — Copy from existing skill; no changes.

**[P] Task P-3.3**: `mcp/skills/framework_migration_version_map.md` — Copy from existing skill; no changes.

**[P] Task P-3.4**: `mcp/skills/framework_migration_main.md` — NEW, Increment 3 (FR-031 through FR-037, FR-043)

This file is NOT a copy of the pre-redesign skill. It MUST implement the four re-entrant loops from `docs/migration-oracle-redesign.md §7`.

**Loop I — Context**:
- Call `create_migration_context` or load existing context by `projectId`
- If `status=complete`: surface summary and stop
- If `status=in-progress` or `blocked`: diff new scan against `ctx.scannedEntities`, queue new entities for Loop II
- Load `skill://framework-migration/version-map` and surface toolchain gates
- Gate: no graph tools before Loop I completes

**Loop II — Scope-gated query (4 tiers)**:
- Tier 1: `scope=api-surface`, severity ≥ high+critical
- Tier 2: `scope=runtime`, severity ≥ medium
- Tier 3: `scope=config` + `scope=build`, all severities
- Tier 4: `scope=test`, all severities
- Per tier: `get_steps_for_scope_tier` → `analyze_upgrade_path` → `resolve_deprecation` per removed entity → `entity_evolution` if partial chain
- Skip guard: check `ctx.queriedEntities` before each call — skip if entity was queried in a prior session
- Paysafe: run `resolve_paysafe_dependency_by_service_name` concurrently for all `com.paysafe.*` entities; do NOT block Tier 1 on result

**Loop III — Execution (step routing)**:
- Call `get_pending_steps` to get full queue (scope-severity order, critical first)
- Route each step:
  - **Auto track**: `automatable=true` AND `effort='mechanical'` AND `AUTOMATED_BY` edge present with `auto=true` AND `missingRequiredParams=[]` → batch in `rewrite.yml`, apply, run build+test, call `update_step_status(completed)`
  - **First-release default (no AUTOMATED_BY edge)**: `automatable=true` AND `effort='mechanical'` but no recipe linked → manual track. NOT an error.
  - **Prompted auto**: `AUTOMATED_BY` exists but `missingRequiredParams` non-empty → surface params, retry or fall to manual
  - **Manual**: `effort=moderate` OR no `AUTOMATED_BY` edge → emit step card (summary, instruction, verificationHint), wait for user confirm
  - **Design-gate**: `effort=architectural` → pause, emit design decision, wait, then manual
  - **Blocked**: `REQUIRES` edge to incomplete step → re-queue
  - **Auto track build failure**: rollback via `skill://recipe-task-rollback/main`, call `update_step_status(failed)`, search_migration_knowledge for workarounds, escalate to manual
- Call `update_step_status` after EVERY step before moving on (FR-035)

**Loop IV — Feedback**:
- Load `skill://generate-community-insights`
- For each manual step where developer's fix differed from `step.instruction`: call `submit_migration_insight` with `confidence=0.9` (build+tests pass) / `0.7` (build only) / `0.5` (uncertain)
- For each skipped step where `effort ≠ 'test'`: emit backlog item via `skill://emit-migration-backlog/main` with step summary, instruction, verificationHint, jiraKeys, BreakingScope severity
- Call `close_migration_context` with `final_status=complete/partial/abandoned`

**Decision tables** (FR-037): Tables for all four loops from `docs/migration-oracle-redesign.md §7.5` MUST appear verbatim in the skill file.

---

### Phase P-4 — server.py (depends on all tool modules; implement last)

**Task P-4.1**: `mcp/server.py`

```python
from mcp.server.fastmcp import FastMCP
from migration_oracle import config
from migration_oracle.graph.driver import get_driver
from migration_oracle.graph.indexes import ensure_indexes
from migration_oracle.mcp.tools import (
    upgrade, deprecation, search, schema,
    community, context, paysafe, artifacts, install
)

mcp = FastMCP("PaysafeMigrationOracle")

# Register tools from each module (each module exports register(mcp) or uses @mcp.tool)
# Register resources: 4 skill Markdown files at skill:// URIs
# Register prompt: migration workflow prompt

def startup():
    """Ordered startup sequence — FR-004."""
    # Step 1: config already loaded at import time
    # Step 2: verify connectivity
    driver = get_driver()
    with driver.session() as session:
        session.run("RETURN 1").single()
    # Step 3: ensure indexes (log and continue on Memgraph DDL failure)
    ensure_indexes(driver)

if __name__ == "__main__":
    startup()
    transport = config.MCP_TRANSPORT
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        mcp.run(transport="sse", host=config.MCP_HOST, port=config.MCP_PORT)
    elif transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=config.MCP_HOST,
            port=config.MCP_PORT,
            stateless_http=config.MCP_STATELESS_HTTP,
        )
```

`startup()` must be called before `mcp.run()`. If step 2 (connectivity check) raises, the exception propagates and the process exits. If step 3 raises a DDL error, `ensure_indexes` logs and continues per existing behaviour.

---

### Phase P-5 — Tests (all parallel; implement after their corresponding tool module is done)

**[P] Task P-5.1**: `tests/mcp/test_upgrade.py`

- `test_analyze_upgrade_path_empty_graph`: empty rules list returned, no error
- `test_analyze_upgrade_path_with_scope_filter`: only rules matching scope_filter returned
- `test_analyze_upgrade_path_no_migration_steps`: steps=[], scopes=[] on pre-redesign data
- `test_build_recipe_plan_no_automated_by`: all steps in manual track, auto track empty
- `test_build_recipe_plan_no_migration_steps`: falls back to rule-level cards

**[P] Task P-5.2**: `tests/mcp/test_deprecation.py`

- `test_resolve_deprecation_found`: correct deprecated_in, removed_in, replaced_by
- `test_resolve_deprecation_not_found`: not_found response
- `test_entity_evolution_chain`: up to 5 hops traced correctly

**[P] Task P-5.3**: `tests/mcp/test_search.py`

- `test_hybrid_search_rrf_fusion`: BM25 and vector hits merged by RRF
- `test_hybrid_search_vector_unavailable`: BM25-only when vector query throws ClientError
- `test_embedding_model_loaded_once`: `get_embedding_model()` called 3 times → `SentenceTransformer.__init__` called once

**[P] Task P-5.4**: `tests/mcp/test_schema.py`

- `test_execute_custom_cypher_safe`: MATCH query executes and returns rows
- `test_execute_custom_cypher_blocks_create`: `CREATE` rejected before graph contact
- `test_execute_custom_cypher_blocks_merge`: `MERGE` rejected
- `test_execute_custom_cypher_blocks_set`: `SET` rejected
- `test_execute_custom_cypher_blocks_delete`: `DELETE` rejected
- `test_execute_custom_cypher_blocks_call_db`: `CALL db.index.fulltext` rejected
- `test_execute_custom_cypher_case_insensitive`: `create` (lowercase) rejected
- `test_get_graph_schema_no_cypher`: schema returned without any graph driver call

**[P] Task P-5.5**: `tests/mcp/test_community.py`

- `test_submit_insight_new`: CommunityInsight node created
- `test_submit_insight_duplicate_detected`: duplicate suppressed, existing id returned
- `test_vote_insight_increment`: votes incremented by delta
- `test_verify_insight`: verified=true set on node

**[P] Task P-5.6**: `tests/mcp/test_context.py`

- `test_create_migration_context_new`: new context created with MERGE, created=True
- `test_create_migration_context_idempotent`: second call returns existing context, created=False
- `test_get_pending_steps_ordered`: steps ordered by severity descending
- `test_update_step_status_completed`: step added to completedSteps; `reason` param accepted
- `test_update_step_status_auto_close`: context auto-closed when last step completed (application code, not trigger)
- `test_get_steps_for_scope_tier`: only entities at correct scope/severity returned
- `test_close_migration_context`: completedAt set, correct return shape per FR-026

**[P] Task P-5.7**: `tests/mcp/test_paysafe_tool.py`

- `test_resolve_delegates_to_resolver`: assert `resolve()` called with exact args; assert result returned verbatim
- `test_resolve_no_findit_import`: assert `findit` is NOT in the imported names of `paysafe.py`

**[P] Task P-5.8**: `tests/mcp/test_artifacts.py`

- `test_list_pipeline_runs`: runs with rawMdPath returned
- `test_get_artifact_content_raw_md`: path resolved from Version node, file read
- `test_get_artifact_content_invalid_type`: error returned without graph query
- `test_get_artifact_content_missing_version`: not_found response
- `test_get_artifact_content_no_direct_path_param`: verify tool signature has no `path` parameter

**[P] Task P-5.9**: `tests/mcp/test_server.py`

- `test_startup_sequence_order`: connectivity check happens before index ensure
- `test_startup_exits_on_connectivity_failure`: `ServiceUnavailable` from driver → startup raises
- `test_startup_continues_on_index_ddl_failure`: DDL ClientError logged, no exception raised
- `test_tool_count`: after server init, exactly 21 tools registered

**[P] Task P-5.10**: `tests/mcp/test_skill_harness.py`

Validates Increment 3 resumption semantics — the core property the four-loop harness must guarantee. Requires mocked graph (no live Neo4j needed).

- `test_context_resume_no_duplicate_steps`: Simulate a migration session interrupted mid-way. Seed the mock with `ctx.completedSteps = ["step-1", "step-2"]` and a full step set of `["step-1", "step-2", "step-3", "step-4"]`. Call `get_pending_steps()` against this state; assert the result contains ONLY `["step-3", "step-4"]` — already-completed steps are NOT re-queued.
- `test_context_resume_correct_completed_steps`: After resumption, verify `ctx.completedSteps` is not extended with any step IDs that were already in it before resumption.
- `test_context_resume_preserves_skipped_steps`: Seed with `ctx.skippedSteps = ["step-2"]`; resume; verify `step-2` does NOT appear in `get_pending_steps()` output.
- `test_context_resume_preserves_failed_steps`: Seed with `ctx.failedSteps = ["step-3"]`; verify `step-3` is excluded from pending even though it was not completed.
- `test_context_auto_close_on_resume_if_all_resolved`: Seed context where `completedSteps + skippedSteps + failedSteps = full_step_set`. Call `update_step_status` for the last step; verify `context_auto_closed=True` and `context_status="complete"` in return, and verify no second graph write is issued.
- `test_loop_i_stops_on_complete_context`: Given a context with `status="complete"`, verify that the harness logic surfaces a summary and does NOT call any graph query tools (simulated by asserting zero calls to `analyze_upgrade_path` or `get_steps_for_scope_tier`).

Note: These tests use mocked graph data per the unit-test pattern in the project. They do NOT require a seeded Neo4j instance. Tests that exercise step-level ordering with real `MigrationStep` nodes are in `test_context.py`.

---

## Parallelism Summary

```
P-0.1 (config)
    └─► P-1.1–P-1.7 (graph/queries — ALL PARALLEL)
            └─► P-2.1–P-2.9 (tools — ALL PARALLEL after all P-1.x done)
                P-3.1–P-3.4 (skills — ALL PARALLEL; can run alongside P-1 and P-2)
                    └─► P-4.1 (server.py — after ALL P-2.x and P-3.x done)
                            └─► P-5.1–P-5.10 (tests — ALL PARALLEL; each after its tool module)
```

Critical path: P-0.1 → P-1.x (max) → P-2.x (max) → P-4.1 → P-5.9

Estimated parallelism gains:
- P-1 (7 modules in parallel): ~3× speedup over sequential
- P-2 (9 modules in parallel): ~4× speedup
- P-5 (10 test files in parallel): ~4× speedup

---

## Key Implementation Constraints Summary

| Constraint | Source | Where enforced |
|---|---|---|
| No inline Cypher in tool handlers | FR-041 | Code review; `mcp/tools/` must import from `mcp/graph/queries/` |
| `_model` singleton pattern (exact variable name and check) | FR-017 | `mcp/tools/search.py` |
| MERGE key = `(projectId, fromVersion, toVersion)`, other props ON CREATE SET only | FR-023 | `mcp/graph/queries/context.py` |
| Auto-close in application code, not Cypher trigger | FR-025 | `mcp/tools/context.py` handler |
| Artifact path from Version node only | FR-028 | `mcp/tools/artifacts.py` (Contract B) |
| Paysafe tool imports only `resolver.resolve` | FR-027 | `mcp/tools/paysafe.py` (Contract A) |
| execute_custom_cypher: keyword check AND READ session | FR-019 | `mcp/graph/queries/schema.py` (Contract D) |
| OPTIONAL MATCH on all new node type joins | FR-039 | All `mcp/graph/queries/*.py` |
| actionStep readable on all tools | FR-040 | `mcp/graph/queries/upgrade.py`, `deprecation.py` |
| No `os.environ` in `mcp/` | FR-042 | Contract F; all `mcp/` files use `config.*` |
| `close_migration_context` return shape (`tool_status` + `migration_status` distinct) | FR-026 | `mcp/tools/context.py` |
| `get_pending_steps` uses sortableVersion range via UPGRADES_FROM/TO — NOT single toVersion | FR-024 | `mcp/graph/queries/context.py` P-1.6 |
| `get_pending_steps` returns `recipe_id` from AUTOMATED_BY join | FR-024/Loop III | `mcp/graph/queries/context.py` P-1.6 |
| `PendingStep.requires` field name (not `blocked_by`) | redesign §6.2 | `mcp/tools/context.py`, data-model.md |
| `update_step_status` parameter named `reason` (not `notes`) | redesign §6.3 | `mcp/tools/context.py` |
| `build_recipe_plan` params: `current_version`/`target_version` (not `from_version`/`to_version`) | reference docs §2 | `mcp/tools/upgrade.py` |

---

## Success Criteria Traceability

| SC | Validated by |
|---|---|
| SC-001: 21 tools respond in ≤ 2s | `test_server.py` tool count; performance checked manually on seeded dataset |
| SC-002: pre-redesign data parity | `test_upgrade.py` test_analyze_upgrade_path_no_migration_steps |
| SC-003: 100% mutation rejection | `test_schema.py` (7 blocking tests) |
| SC-004: 10 concurrent connections | Load test (manual); FastMCP handles async tool dispatch |
| SC-005: Loop I–IV on first release | `test_context.py` auto-close; four-loop skill (P-3.4) |
| SC-006: ≥ 95% duplicate detection | `test_community.py` duplicate test dataset |
| SC-007: model loaded once | `test_search.py` singleton test |
| SC-008: startup in ≤ 10s | `test_server.py` startup sequence; manual timing |

# Migration Oracle — Spec Organization
 
> **How to use this file:** This is the single source of truth for spec sequencing, inter-spec dependencies, gates, and SpecKit runbook locations. Update the status column after each SpecKit lifecycle step completes. Never start a spec whose prerequisites show a status other than ✅ Complete.
 
---
 
## Spec inventory
 
| ID | Name | Status | Runbook |
|----|------|--------|---------|
| `001` | Foundations | ✅ Complete | `specs/001-foundations/` |
| `002` | Pipeline Core | ✅ Complete | `specs/002-pipeline-core/` |
| `003` | Extractors | ✅ Complete | `specs/003-extractors/` |
| `004` | Paysafe Resolver | 🔲 Not started | `specs/004-paysafe-resolver/` |
| `005` | MCP Server | 🔲 Not started | `specs/005-mcp-server/` |
| `006` | Streamlit UI | 🔲 Not started | `specs/006-streamlit-ui/` |
 
**Status key:** 🔲 Not started · 🔄 In progress · 🔍 Gap review · ✅ Complete · 🚫 Blocked
 
---
 
## Dependency graph
 
```
000-foundations
       │
       ├──► 001-pipeline-core
       │           │
       │           └──► 002-extractors ──────────────┐
       │                                               │
       ├──► 003-paysafe-resolver ────────────────────►│
       │                                               ▼
       │                                       004-mcp-server
       │                                               │
       │                                               ▼
       └───────────────────────────────── 005-streamlit-ui
```
 
`002-extractors` and `003-paysafe-resolver` may be developed in parallel once `001-pipeline-core` is complete.
 
---
 
## Spec details
 
---
 
### `000` — Foundations
 
**Purpose:** Shared types, graph connection, and project scaffolding that every other spec imports. Nothing else can be built until this is solid.
 
**Repository scope:**
 
```
migration_oracle/
├── models/                        # All Pydantic types
│   ├── entities.py                # MigrationEntitiesBatch + all supporting types
│   └── graph.py                   # Graph node/edge value objects
├── config.py                      # All env var loading
├── graph/
│   ├── driver.py                  # Neo4j/Memgraph connection, session helpers
│   └── indexes.py                 # Ensure-on-startup index DDL
└── pyproject.toml                 # uv project, all dependencies declared
```
 
**Key design decisions captured here:**
- `MigrationEntitiesBatch` Pydantic schema from `migration-oracle-redesign.md` §4.5 — this is the contract between the pipeline and the graph
- `sortableVersion = major × 1_000_000 + minor × 1_000 + patch` — used everywhere version range queries appear
- Graph driver must degrade gracefully on Memgraph (unsupported index DDL caught and logged, not raised)
- All env vars from `config.py` — `NEO4J_URI`, `MODEL_PROVIDER`, `MODEL_ID`, `GITHUB_TOKEN`, `FINDIT_AUTH_TOKEN`, `SENTENCE_TRANSFORMERS_MODEL`, `SSL_VERIFY`, and all others documented in the reference files
**Completion gate:**
- [ ] `MigrationEntitiesBatch` and all sub-models are importable with no errors
- [ ] `graph/driver.py` connects to a running Neo4j or Memgraph instance
- [ ] `graph/indexes.py` is idempotent — running it twice does not raise
- [ ] All env vars load with defaults; missing required vars raise at import time with a clear message
- [ ] `uv sync` produces a clean environment
**Reference docs:** `migration-oracle-redesign.md` §4.5 (Pydantic model), `graph-mcp-skills-and-paysafe-resolution.md` §2 (connection settings), §3 (indexes), `GRAPH_STRUCTURE.md` (node labels and properties)
 
---
 
### `001` — Pipeline Core
 
**Purpose:** The two LLM calls (filter-and-group, entity extraction), the graph population logic for the new schema, artifact caching, and the CLI command.
 
**Prerequisite:** `000-foundations` ✅
 
**Repository scope:**
 
```
migration_oracle/
├── pipeline/
│   ├── filters.py                 # First LLM call: raw MD → filtered MD
│   ├── extractor.py               # Second LLM call: filtered MD → MigrationEntitiesBatch JSON
│   └── populator.py               # Graph write: MigrationStep, BreakingScope, roles, paths
├── graph/
│   └── queries/
│       └── pipeline.py            # Version existence check, artifact path upsert
└── cli.py                         # export-extract-populate-framework entry point
```
 
**Critical design decision — artifact paths on `Version` nodes:**
After each successful pipeline run, `populator.py` writes three new properties onto the `Version` node:
 
| Property | Value |
|----------|-------|
| `rawMdPath` | Absolute path to `runs/raw/<framework>-<from>-to-<to>-changes.md` |
| `filteredMdPath` | Absolute path to `runs/nodes/<framework>-<from>-to-<to>-changes_filtered.md` |
| `entitiesJsonPath` | Absolute path to `runs/json/<framework>-<from>-to-<to>-entities.json` |
 
This makes the graph the discovery index for the FE — no filesystem scan, no separate manifest. The FE queries `Version` nodes with `rawMdPath IS NOT NULL` to list available runs.
 
**CLI flags (all required):**
 
| Flag | Behaviour |
|------|-----------|
| `--framework <key>` | Required. Selects extractor. |
| `from_version` | Required positional. |
| `to_version` | Required positional. |
| `--dry-run` | Skip graph write. Still produce and cache all artifacts. |
| `--force` | Re-run everything. Equivalent to `--force-extract --force-llm`. |
| `--force-extract` | Re-fetch upstream. Overwrite raw MD. |
| `--force-llm` | Re-run both LLM calls. Overwrite filtered MD and JSON. |
| `--output-md <path>` | Override raw MD output path. |
| `--output-filtered-md <path>` | Override filtered MD output path. |
| `--output-json <path>` | Override JSON output path. |
 
**Stale artifact warning:** If `--force-extract` is set but `--force-llm` is not, and filtered MD or entities JSON already exist, print a warning recommending `--force-llm`.
 
**Completion gate:**
- [ ] `--dry-run` with a stubbed extractor produces all three artifacts in `runs/`
- [ ] `Version` node has `rawMdPath`, `filteredMdPath`, `entitiesJsonPath` after a real run
- [ ] Re-running without force flags reuses cached artifacts (verified by checking file mtimes)
- [ ] `--force-llm` re-runs both LLM calls and overwrites filtered MD and JSON
- [ ] Stale artifact warning appears when `--force-extract` is set without `--force-llm`
**Reference docs:** `export-extract-populate-framework-pipeline.md` §phases 4–7, `migration-oracle-redesign.md` §5 (population logic)
 
---
 
### `002` — Extractors
 
**Purpose:** All nine framework HTTP extractors that conform to the output contract defined in `001-pipeline-core`.
 
**Prerequisite:** `001-pipeline-core` ✅
 
**Repository scope:**
 
```
migration_oracle/
└── pipeline/
    └── extractors/
        ├── __init__.py            # Extractor registry: key → extractor class
        ├── base.py                # Abstract base class + output contract type
        ├── spring_boot.py         # Full implementation
        ├── angular.py             # Full implementation
        ├── wildfly.py             # Full implementation + Jira enrichment
        ├── eap.py                 # Full implementation
        ├── hibernate.py           # Full implementation
        ├── resteasy.py            # Full or NotImplementedError stub
        ├── infinispan.py          # Full or NotImplementedError stub
        ├── elytron.py             # Full or NotImplementedError stub
        └── jakarta_ee.py          # Full implementation (deterministic, no HTTP)
```
 
**Output contract (defined in `base.py`, consumed by `pipeline/filters.py`):**
Each extractor, given `(from_version, to_version)` for one hop, returns a list of `DocumentedChange` objects:
 
| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `breaking`, `mandatory_migration`, `deprecation`, `dependency_upgrade`, `behavioral`, `potential_breaking` |
| `confidence` | string | `confirmed` or `inferred` |
| `source_url` | string | Canonical URL |
| `statement` | string | Human-readable description |
 
**Priority order for implementation:** Spring Boot → Angular → WildFly (most used; WildFly has Jira enrichment complexity) → Jakarta EE (deterministic, zero HTTP) → remaining four (stub with `NotImplementedError` if needed to ship `004`).
 
**Extractor registry must be complete** even if some extractors are stubs — `cli.py` must reject unknown `--framework` keys with a clear error listing supported values.
 
**Completion gate:**
- [ ] Spring Boot extractor produces valid `DocumentedChange` list for a real version hop
- [ ] WildFly extractor completes including Jira enrichment (mocked Jira in tests)
- [ ] Angular extractor produces valid output
- [ ] Jakarta EE produces deterministic namespace rules for the `javax→jakarta` boundary
- [ ] Registry is complete — all nine keys registered, stubs raise `NotImplementedError` with clear message
- [ ] Full end-to-end CLI run completes for `--framework spring-boot 3.3.0 3.4.0`
**Reference docs:** `export-extract-populate-framework-pipeline.md` §phases 1–3 (all nine frameworks), §phase 3 (Jira enrichment)
 
---
 
### `003` — Paysafe Resolver
 
**Purpose:** The `resolve_paysafe_dependency_by_service_name` resolution flow — FindIt registry lookup, GitLab tag discovery, build-file compatibility checking, and version selection.
 
**Prerequisite:** `000-foundations` ✅  
**Can run in parallel with:** `002-extractors`
 
**Repository scope:**
 
```
migration_oracle/
└── paysafe/
    ├── __init__.py
    ├── resolver.py                # Full seven-step resolution flow
    ├── findit.py                  # FindIt API client (cached, with retries)
    └── gitlab.py                  # Git tag listing + build file fetching
```
 
**Seven-step flow (must be implemented exactly):**
 
| Step | Action |
|------|--------|
| 1 | FindIt lookup with four-level name matching: exact → case-insensitive → alphanumeric normalization → fuzzy (threshold from `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD`, default `0.68`) |
| 2 | Parse GitLab URL from `codeRepoLink` → SCP-style locator |
| 3 | Framework auto-detection: probe HEAD for `pom.xml` → `build.gradle(.kts)` → `package.json` |
| 4 | List and sort git tags semantically |
| 5 | Per-tag build-file fetch and framework version extraction |
| 6 | Apply compatibility rule: same major, declared version ≥ target |
| 7 | Select best tag per strategy: `latest_compatible` / `latest_overall` / `latest_with_known_compatibility` |
 
**All error codes required:**
 
| Code | Trigger |
|------|---------|
| `invalid_service_name` | Empty service name |
| `service_not_found` | No FindIt match above fuzzy threshold |
| `no_repo_url` | Service found, no `codeRepoLink` |
| `no_tags_found` | Git repo has no tags |
| `no_compatible_version` | No compatible tag, fallback disabled |
| `compatibility_unknown` | No build file with framework version in any tag |
| `http_timeout` / `http_request_failed` | Network failure |
 
**Completion gate:**
- [ ] All seven error codes are tested (mocked HTTP)
- [ ] Fuzzy name matching returns correct `name_resolution` metadata
- [ ] Compatibility rule correctly rejects lower minor versions and major mismatches
- [ ] `allow_latest_overall=true` fallback works when no compatible tag exists
- [ ] FindIt cache TTL (30-day in-memory) is implemented
**Reference docs:** `graph-mcp-skills-and-paysafe-resolution.md` §11–12 (full resolution spec)
 
---
 
### `004` — MCP Server
 
**Purpose:** The `PaysafeMigrationOracle` MCP server with all 21 tools (14 existing + 5 new context-management tools + 2 new artifact-access tools), all skill resources, and transport configuration.
 
**Prerequisites:** `001-pipeline-core` ✅, `003-paysafe-resolver` ✅
 
**Repository scope:**
 
```
migration_oracle/
└── mcp/
    ├── server.py                  # Entry point, transport selection, tool registration
    ├── tools/
    │   ├── upgrade.py             # analyze_upgrade_path, build_recipe_plan
    │   ├── deprecation.py         # resolve_deprecation, entity_evolution
    │   ├── search.py              # search_migration_knowledge, search_openrewrite_recipes
    │   ├── schema.py              # get_graph_schema, execute_custom_cypher
    │   ├── community.py           # submit_migration_insight, get_community_insights, vote_insight, verify_insight
    │   ├── context.py             # create_migration_context, get_pending_steps, update_step_status,
    │   │                          # get_steps_for_scope_tier, close_migration_context
    │   ├── paysafe.py             # resolve_paysafe_dependency_by_service_name (delegates to paysafe/)
    │   ├── artifacts.py           # list_pipeline_runs, get_artifact_content  ← FE read path
    │   └── install.py             # install_migration_skill
    ├── skills/                    # Markdown resources served as MCP resources
    │   ├── framework_migration_main.md
    │   ├── framework_migration_scanning.md
    │   ├── framework_migration_plan_format.md
    │   └── framework_migration_version_map.md
    └── graph/
        └── queries/               # One module per tool group, Cypher from reference docs
```
 
**Two new tools for FE artifact access (`artifacts.py`):**
 
`list_pipeline_runs` — queries `Version` nodes where `rawMdPath IS NOT NULL`, returns run metadata:
```json
[{
  "framework": "Spring Boot",
  "from_version": "3.3.0",
  "to_version": "3.4.0",
  "raw_md_path": "...",
  "filtered_md_path": "...",
  "entities_json_path": "..."
}]
```
 
`get_artifact_content` — reads a file at the path from the `Version` node property and returns its content as a string. Parameters: `framework`, `version`, `artifact_type` (`raw_md` | `filtered_md` | `entities_json`).
 
**Transport:** Selected via `MCP_TRANSPORT` env var. Default `stdio`. Supports `sse` and `streamable-http` (bound to `MCP_HOST`:`MCP_PORT`).
 
**Completion gate:**
- [ ] All 21 tools register without error on server start
- [ ] `list_pipeline_runs` returns results after a real pipeline run
- [ ] `get_artifact_content` returns correct file content for all three artifact types
- [ ] `analyze_upgrade_path` returns markdown and JSON correctly for a known version range
- [ ] `create_migration_context` → `get_pending_steps` → `update_step_status` round-trip works
- [ ] `resolve_paysafe_dependency_by_service_name` delegates to resolver and returns correct shape
**Reference docs:** `graph-mcp-skills-and-paysafe-resolution.md` §7–8 (all existing tools + Cypher), `migration-oracle-redesign.md` §6 (new tools)
 
---
 
### `005` — Streamlit UI
 
**Purpose:** Browser-based interface for triggering pipeline runs, browsing artifacts, exploring the graph, managing migration contexts, and submitting community insights.
 
**Prerequisite:** `004-mcp-server` ✅
 
**Repository scope:**
 
```
migration_oracle/
└── streamlit_app/
    ├── app.py                     # Entry point, page routing, MCP client setup
    └── pages/
        ├── 01_pipeline_trigger.py # Trigger a new pipeline run (form → CLI subprocess)
        ├── 02_run_browser.py      # Browse runs via list_pipeline_runs; view artifacts in tabs
        ├── 03_rule_explorer.py    # Search and browse migration rules + steps
        ├── 04_context_dashboard.py # MigrationContext status, step completion, skip tracking
        └── 05_community.py        # Browse and submit CommunityInsight nodes
```
 
**Page: Run Browser (`02_run_browser.py`)**
This is the primary artifact-viewing page. It calls `list_pipeline_runs`, renders a selectbox of available runs, then shows three tabs:
- **Raw MD** — rendered Markdown from `rawMdPath`
- **Filtered MD** — rendered Markdown from `filteredMdPath`
- **Entities JSON** — pretty-printed JSON from `entitiesJsonPath`
All file content is fetched via `get_artifact_content` (MCP tool call) — the FE never reads the filesystem directly.
 
**Completion gate:**
- [ ] All five pages render without error against a populated graph
- [ ] Run browser shows at least one run and all three artifact tabs display content
- [ ] Rule explorer returns results for a known entity name
- [ ] Context dashboard displays step completion state correctly
- [ ] Community page renders submitted insights
**Reference docs:** `migration-oracle-redesign.md` §7 (agent harness loops, for context dashboard design)
 
---
 
## SpecKit runbook locations
 
Each spec has its own directory under `specs/`. The directory structure for every spec follows the same layout:
 
```
specs/
└── NNN-spec-name/
    ├── spec.md                    # /speckit.specify output
    ├── plan.md                    # /speckit.plan output
    ├── data-model.md              # Types, schemas, storage key formats
    ├── contracts/                 # Component boundary rules
    │   └── NNN-spec-name.md
    ├── tasks.md                   # /speckit.tasks output
    ├── research.md                # Spikes and tech choices (if needed)
    ├── quickstart.md              # How to run this spec locally
    └── runbook.md                 # Full SpecKit prompt sequence for this spec
```
 
`runbook.md` in each directory contains the ready-to-paste Claude Code prompts for every SpecKit step, post-step gap reviews, and recovery prompts specific to that spec's failure modes.
 
---
 
## Reference document index
 
| Document | What it governs |
|----------|-----------------|
| `migration-oracle-redesign.md` | Canonical spec — graph schema redesign, new Pydantic models, new MCP tools, agent harness loops. **When in doubt, this wins.** |
| `export-extract-populate-framework-pipeline.md` | Full extraction pipeline — all nine frameworks, exact URLs, HTTP headers, Jira enrichment, LLM call design, caching, failure modes |
| `graph-mcp-skills-and-paysafe-resolution.md` | MCP tool contracts, Cypher queries, Paysafe resolution logic, skill resources |
| `GRAPH_STRUCTURE.md` | Node labels, properties, relationships, `AUTOMATED_BY` edge schema |
 
---
 
## Working conventions
 
**Never start a spec whose prerequisite gate is not ✅.** The gate exists because downstream specs import types, call graph queries, or delegate to modules that must be stable before being depended on.
 
**Cypher queries are not paraphrased.** Copy them from the reference documents exactly. Only deviate if a test fails and the deviation is documented with the reason.
 
**`OPTIONAL MATCH` everywhere the new schema adds nodes.** Pre-redesign `Version` nodes will not have `MigrationStep` or `BreakingScope` nodes. Any query that touches these must use `OPTIONAL MATCH` so old data continues to work.
 
**Artifact paths are written by the pipeline, read by the FE.** The pipeline is the only writer of `rawMdPath`, `filteredMdPath`, and `entitiesJsonPath` on `Version` nodes. The FE and MCP tools are read-only consumers of those properties.
 
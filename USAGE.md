# PaysafeMigrationOracle — MCP Server Usage Guide

## What it does

`PaysafeMigrationOracle` is an MCP server that exposes a Neo4j/Memgraph knowledge
graph of framework migration rules to AI agents (Claude Code, Cursor, or a custom
harness). Agents use it to:

- Discover migration rules and breaking changes between framework versions
- Execute a structured, re-entrant four-loop migration harness on a real project
- Resolve Paysafe-internal (`com.paysafe.*`) dependencies without knowing the
  FindIt or GitLab APIs
- Search migration knowledge by natural language (BM25 + vector hybrid)
- Submit and vote on community-contributed migration insights

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | Check with `python --version` |
| `uv` | `pip install uv` or `brew install uv` |
| Neo4j 5.x **or** Memgraph | Must be running and reachable before starting the server |
| SentenceTransformer model | `all-mpnet-base-v2` (default). Downloaded automatically on first start. |
| Project dependencies | `uv sync` from the repo root |

---

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `NEO4J_URI` | **Yes** | — | e.g. `bolt://localhost:7687` |
| `NEO4J_PASSWORD` | **Yes** | — | Graph password |
| `NEO4J_USERNAME` | No | `neo4j` | Graph username |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` \| `sse` \| `streamable-http` |
| `MCP_HOST` | No | `0.0.0.0` | Bind host (HTTP transports only) |
| `MCP_PORT` | No | `8080` | Bind port (HTTP transports only) |
| `MCP_STATELESS_HTTP` | No | `false` | Enable stateless HTTP for remote clients |
| `SENTENCE_TRANSFORMERS_MODEL` | No | `all-mpnet-base-v2` | Embedding model |
| `FINDIT_AUTH_TOKEN` | No | `""` | Paysafe FindIt API bearer token |
| `FINDIT_BASE_URL` | No | `https://findit-api.icd.paysafe.cloud` | FindIt endpoint |
| `GITLAB_API_KEY` | No | `""` | GitLab personal access token |
| `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` | No | `0.68` | Min fuzzy-match score for service name lookup |
| `POPULATE_MIGRATION_EMBEDDINGS` | No | `false` | Generate embeddings during pipeline runs |
| `SSL_VERIFY` | No | `true` | Set `false` to skip TLS verification |

---

## Adding to Claude Code

Add to your Claude Code MCP settings. The easiest way is via the Claude Code UI
(**Settings → MCP Servers → Add**), or edit the JSON directly.

**`.claude/mcp.json`** (project-level) or **`~/.claude/mcp.json`** (global):

```json
{
  "mcpServers": {
    "migration-oracle": {
      "command": "uv",
      "args": ["run", "python", "-m", "migration_oracle.mcp.server"],
      "cwd": "/absolute/path/to/paysafe-version-migration-graph",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

After saving, restart Claude Code. You should see `migration-oracle` appear in the
MCP server list with status **connected**.

---

## Adding to Cursor

Create or edit **`.cursor/mcp.json`** in the project root:

```json
{
  "mcpServers": {
    "migration-oracle": {
      "command": "uv",
      "args": ["run", "python", "-m", "migration_oracle.mcp.server"],
      "cwd": "/absolute/path/to/paysafe-version-migration-graph",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

Reload Cursor (**Cmd+Shift+P → Reload Window**). The server starts on first tool
call — you do not need to start it manually in stdio mode.

---

## Running with Docker

No local Python environment or `uv` install required — only Docker.

### Build the image

```bash
docker build -t paysafe-migration-oracle:latest .
```

The embedding model (`all-mpnet-base-v2`, ~400 MB) is downloaded and baked into the
image at build time. First requests are not penalised by a cold download.

To use a different model, pass `--build-arg`:

```bash
docker build --build-arg SENTENCE_TRANSFORMERS_MODEL=all-MiniLM-L6-v2 \
  -t paysafe-migration-oracle:latest .
```

### Run with docker run

```bash
docker run -d \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e NEO4J_PASSWORD=your-password \
  -e ANTHROPIC_API_KEY=your-key \
  -p 8080:8080 \
  -p 8501:8501 \
  paysafe-migration-oracle:latest
```

Both services start automatically:

| Service | Default port | URL |
|---|---|---|
| MCP SSE server | 8080 | `http://localhost:8080/sse` |
| Streamlit UI | 8501 | `http://localhost:8501` |

Override ports with `-e MCP_PORT=9090 -e STREAMLIT_SERVER_PORT=9091` (also adjust `-p`).

### Run with Docker Compose (includes Neo4j)

```bash
docker compose up -d
```

The compose file starts the oracle alongside a Neo4j 5 sidecar with a named data
volume. The oracle waits for Neo4j to become healthy before starting. Both services
are reachable on the same default ports.

To stop and preserve data:

```bash
docker compose down      # volumes retained
docker compose down -v   # volumes deleted
```

### Connect Claude Code to the running SSE server

Once the container is running, point Claude Code at the SSE endpoint instead of
starting a local process:

```json
{
  "mcpServers": {
    "migration-oracle": {
      "type": "sse",
      "url": "http://localhost:8080/sse"
    }
  }
}
```

### Container health

The image declares a built-in health-check. View its status:

```bash
docker inspect --format='{{.State.Health.Status}}' <container-id>
```

Status moves from `starting` to `healthy` within ~60 seconds of launch. The check
probes both the MCP SSE endpoint and the Streamlit health endpoint; a crash in either
service transitions the container to `unhealthy` (and the fail-fast entrypoint also
stops the container with a non-zero exit code).

---

## Starting the server manually (HTTP / SSE mode)

stdio is managed by the client. For HTTP transports, start the server yourself:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=your-password
export MCP_TRANSPORT=sse        # or streamable-http
export MCP_PORT=8080

uv run python -m migration_oracle.mcp.server
```

For stateless HTTP (multiple remote clients, no session affinity):

```bash
export MCP_TRANSPORT=streamable-http
export MCP_STATELESS_HTTP=true
uv run python -m migration_oracle.mcp.server
```

Successful startup prints:

```
INFO  PaysafeMigrationOracle ready — transport=sse
```

---

## The 21 tools

### Upgrade group

| Tool | What it does |
|---|---|
| `analyze_upgrade_path` | Returns migration rules and lifecycle alerts for a framework version range. Supports `scope_filter` and `min_severity` to narrow results. Each rule includes `steps`, `scopes`, and `recipes` arrays (empty on pre-redesign data). |
| `build_recipe_plan` | Produces a two-track plan (auto + manual). Auto track: steps with `automatable=true`, `effort=mechanical`, and a linked OpenRewrite recipe. Manual track: everything else. Falls back to rule-level cards when no `MigrationStep` nodes exist. |

### Deprecation group

| Tool | What it does |
|---|---|
| `resolve_deprecation` | Returns `deprecated_in`, `removed_in`, `replaced_by` (one hop), and related rules for a single entity name. |
| `entity_evolution` | Traces the full `REPLACED_BY` chain up to 5 hops with lifecycle events and rules per node. |

### Search group

| Tool | What it does |
|---|---|
| `search_migration_knowledge` | Hybrid BM25 + vector search over migration rules and community insights. Returns ranked hits with `statement`, `action_step`, `source_url`. |
| `search_openrewrite_recipes` | Same hybrid search over OpenRewrite recipe descriptions. Returns ranked recipe hits. |

### Schema group

| Tool | What it does |
|---|---|
| `get_graph_schema` | Returns the authoritative graph schema as a Markdown string. No Cypher executed. |
| `execute_custom_cypher` | Executes a read-only Cypher query. Blocks any query containing `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, or `CALL db` before it reaches the graph. |

### Community group

| Tool | What it does |
|---|---|
| `submit_migration_insight` | Submits a developer-contributed insight. Near-duplicate detection runs before write; returns `status: duplicate` if one already exists. |
| `get_community_insights` | Queries `CommunityInsight` nodes by version range, entity name, or verified-only filter. |
| `vote_insight` | Increments or decrements the `votes` property on an insight by `delta`. |
| `verify_insight` | Sets `verified=true` on an insight (moderator operation). |

### Context group

| Tool | What it does |
|---|---|
| `create_migration_context` | Creates or loads a `MigrationContext` for a `(project_id, from_version, to_version)` triple. Idempotent — returns the existing context unchanged if called again with the same triple. |
| `get_pending_steps` | Returns the remaining step queue for a context, ordered by scope severity then topological order. Excludes completed and skipped steps. |
| `update_step_status` | Records the outcome of a step (`completed` / `skipped` / `failed`). Auto-closes the context when no pending steps remain. |
| `get_steps_for_scope_tier` | Returns steps for a specific scope (e.g. `api-surface`) and severity threshold. Used by Loop II to query one tier at a time. |
| `close_migration_context` | Sets `completedAt`, `migration_status`, and `notes` on the context. Call at the end of every session. |

### Paysafe group

| Tool | What it does |
|---|---|
| `resolve_paysafe_dependency_by_service_name` | Resolves a `com.paysafe.*` dependency via FindIt + GitLab. Returns the canonical repo, version tags, and migration guidance. Pass `target_version` to filter tags. |

### Artifacts group

| Tool | What it does |
|---|---|
| `list_pipeline_runs` | Lists all `Version` nodes that have pipeline artifact paths stored. |
| `get_artifact_content` | Reads a pipeline artifact by type (`raw_md`, `filtered_md`, `entities_json`). The path is resolved from the `Version` node — no direct filesystem path accepted from the caller. |

### Install group

| Tool | What it does |
|---|---|
| `install_migration_skill` | Copies bundled skill Markdown files to the Cursor or Claude Code skills directory. Use `target="auto"` to detect the target from the environment. |

---

## Skill resources (4)

The server also serves four static Markdown skill files as MCP resources. An agent
loads these to understand the four-loop harness and scanning patterns:

| Resource URI | Content |
|---|---|
| `skill://framework-migration/main` | Four-loop harness implementation — Loop I–IV decision tables |
| `skill://framework-migration/scanning` | Codebase scanning patterns for entity extraction |
| `skill://framework-migration/plan-format` | Migration plan output format reference |
| `skill://framework-migration/version-map` | Framework version map and toolchain gates |

---

## The 3 prompts

The server registers three MCP prompts that clients with prompt support (Claude
Code, Cursor) can invoke directly from the slash-command palette or prompt picker.

| Prompt | Parameters | Purpose |
|---|---|---|
| `start_migration` | `framework`, `current_version`, `target_version`, `project_id` | Start a new four-loop migration harness |
| `resume_migration` | `context_id` | Resume from an existing `MigrationContext` |
| `migration_workflow_prompt` | *(none)* | Zero-parameter fallback for clients that don't support parameterized prompts |

### `start_migration` (recommended)

**In Claude Code / Cursor prompt picker** — invoke the prompt with parameters:

```
framework: Spring Boot
current_version: 2.7
target_version: 3.2
project_id: payments-service
```

The server renders this into the agent:

```
Load skill://framework-migration/main.

Migrate project 'payments-service' from Spring Boot 2.7 to Spring Boot 3.2.

Run the four-loop migration harness:
- Loop I: scan the codebase, call create_migration_context
- Loop II: query the graph in scope-gated tiers (api-surface → runtime → config/build → test)
- Loop III: execute each pending step (auto or manual; ask me to confirm manual steps)
- Loop IV: submit new insights via submit_migration_insight, then call close_migration_context
```

### `resume_migration`

Use after a previous session ended with pending steps. Pass the UUID returned
by `create_migration_context` or `get_pending_steps`:

```
context_id: 3f2a1b4c-...
```

The server renders this into the agent:

```
Load skill://framework-migration/main.

Resume migration context '3f2a1b4c-...'.

Call get_pending_steps(context_id='3f2a1b4c-...') to see what remains.
Continue from Loop III: execute each pending step, then run Loop IV
(submit insights, close context).
```

### `migration_workflow_prompt` (fallback)

For clients that do not support parameterized prompts. Paste and fill in the
placeholders manually:

```
Load skill://framework-migration/main.

I want to migrate this project from [framework] [current_version] to [target_version].
Project ID: [your-project-id]

Run the four-loop migration harness:
- Loop I: scan the codebase, create or resume a migration context
- Loop II: query the graph in scope-gated tiers (api-surface → runtime → config/build → test)
- Loop III: execute each pending step (auto or manual)
- Loop IV: submit any new insights, close the context
```

---

## The four-loop harness — tool call order

The agent follows this order internally. You do not call these manually — the
harness skill drives the sequence.

**Loop I — Context**

```
create_migration_context(
    project_id="payments-service",
    from_version="2.7",
    to_version="3.2",
    framework="Spring Boot",
    scanned_entities=["org.springframework.security.web.SecurityFilterChain", ...]
)
```

**Loop II — Scope-gated query (4 tiers)**

```
# Tier 1 — api-surface, high+critical severity
get_steps_for_scope_tier(context_id=..., scope="api-surface", severity_threshold="high")
analyze_upgrade_path(framework=..., current_version=..., target_version=...,
    user_entities=[...], scope_filter=["api-surface"], min_severity="high")
resolve_deprecation(entity_name="SecurityFilterChain")

# Paysafe deps — concurrently with Tier 1
resolve_paysafe_dependency_by_service_name(service_name="payments-core", target_version="3.2")

# Tier 2 — runtime, medium+
get_steps_for_scope_tier(context_id=..., scope="runtime", severity_threshold="medium")
analyze_upgrade_path(..., scope_filter=["runtime"], min_severity="medium")

# Tier 3 — config + build, all severities
analyze_upgrade_path(..., scope_filter=["config", "build"])
search_migration_knowledge(query="actuator endpoint security spring boot 3")  # for no-hit entities

# Tier 4 — test, all severities
analyze_upgrade_path(..., scope_filter=["test"])
```

**Loop III — Execution**

```
get_pending_steps(context_id=...)

# For each step:
#   auto track:
update_step_status(context_id=..., step_id=..., outcome="completed")
#   manual track (after user confirms):
update_step_status(context_id=..., step_id=..., outcome="completed")
#   skipped:
update_step_status(context_id=..., step_id=..., outcome="skipped", reason="deferred to next sprint")
```

**Loop IV — Feedback**

```
submit_migration_insight(
    statement="SecurityFilterChain bean registration changed in 3.0",
    spring_boot_version="3.0",
    solution="Use @Bean on SecurityFilterChain directly, remove WebSecurityConfigurerAdapter",
    confidence=0.9
)

close_migration_context(
    context_id=...,
    final_status="complete",   # or "partial" if steps were skipped
    notes="All api-surface steps completed. Test-scope steps deferred."
)
```

---

## Common one-off prompts

### Analyze an upgrade path without running the full harness

```
Using migration-oracle, call analyze_upgrade_path with:
  framework="Spring Boot", current_version="2.7", target_version="3.2"
Show me all rules with severity "high" or "critical" affecting api-surface scope.
```

### Resolve a specific deprecated class

```
Using migration-oracle, call resolve_deprecation for
  entity_name="org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter"
Then call entity_evolution for the same entity to trace its full replacement chain.
```

### Search for migration guidance

```
Using migration-oracle, call search_migration_knowledge with
  query="actuator health endpoint authentication spring boot 3"
Return the top 5 results with their action_step and source_url.
```

### Check a Paysafe internal dependency

```
Using migration-oracle, call resolve_paysafe_dependency_by_service_name with
  service_name="payments-core"
  target_version="3.2"
```

### Run a custom read-only graph query

```
Using migration-oracle, call execute_custom_cypher with:
  query="MATCH (r:MigrationRule {framework:'Spring Boot'}) WHERE r.severity = 'critical' RETURN r.id, r.statement LIMIT 10"
```

### List what pipeline artifacts are available

```
Using migration-oracle, call list_pipeline_runs to see all processed version pairs.
Then call get_artifact_content with artifact_type="filtered_md" for the version you want.
```

---

## Troubleshooting

**Server fails to start with `ServiceUnavailable`**
The graph is unreachable. Check `NEO4J_URI` and that the database is running.

**`execute_custom_cypher` returns `status: blocked`**
The query contains a mutation keyword (`CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`,
`DROP`, or `CALL db`). This is intentional — only read-only queries are permitted.

**`get_pending_steps` returns an empty list**
Either all steps are completed/skipped, or `MigrationStep` nodes don't exist in the
graph yet (Increment 1 pipeline run required). `build_recipe_plan` will fall back to
rule-level cards automatically.

**`build_recipe_plan` auto track is empty**
`AUTOMATED_BY` edges are absent in the first release. All steps route to the manual
track. This is expected — not an error.

**Search returns no results**
Embeddings may not have been generated yet. Set `POPULATE_MIGRATION_EMBEDDINGS=true`
and re-run the pipeline. BM25 works without embeddings but vector search requires them.

**`resolve_paysafe_dependency_by_service_name` fails**
Check `FINDIT_AUTH_TOKEN` and `GITLAB_API_KEY` are set. The tool delegates entirely
to the Paysafe resolver — check resolver logs for the root cause.

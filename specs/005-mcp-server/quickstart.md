# Quickstart: PaysafeMigrationOracle MCP Server (005)

**Phase 1 output** | Branch: `005-mcp-server` | Date: 2026-06-07

---

## Prerequisites

- Python 3.11+
- `uv` installed (`pip install uv` or `brew install uv`)
- A running Neo4j 5.x or Memgraph instance (for live graph queries)
- Project dependencies installed: `uv sync`

---

## Required Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `NEO4J_URI` | **Yes** | — | Bolt URI, e.g. `bolt://localhost:7687` |
| `NEO4J_PASSWORD` | **Yes** | — | Graph password |
| `NEO4J_USERNAME` | No | `neo4j` | Graph username — matches `config.py` attribute `NEO4J_USERNAME` |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` \| `sse` \| `streamable-http` |
| `MCP_HOST` | No | `0.0.0.0` | Bind host for HTTP transports |
| `MCP_PORT` | No | `8001` | Bind port for HTTP transports |
| `MCP_STATELESS_HTTP` | No | `false` | Enable stateless HTTP mode |
| `SENTENCE_TRANSFORMERS_MODEL` | No | `all-mpnet-base-v2` | Embedding model name or HuggingFace path |
| `FINDIT_AUTH_TOKEN` | No | `""` | Paysafe FindIt API bearer token |
| `FINDIT_BASE_URL` | No | `https://findit-api.icd.paysafe.cloud` | FindIt endpoint |
| `GITLAB_API_KEY` | No | `""` | GitLab personal access token |
| `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` | No | `0.68` | Minimum fuzzy-match score for FindIt service name lookup |
| `POPULATE_MIGRATION_EMBEDDINGS` | No | `false` | Set `true` to generate and store embeddings during pipeline runs |
| `SSL_VERIFY` | No | `true` | Set `false` to skip TLS verification |

---

## Starting the Server in stdio Mode

stdio mode is the primary integration target for Claude Code and Cursor.

```bash
# 1. Set required env vars
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=your-password

# 2. Start the server (stdio is the default transport)
uv run python -m migration_oracle.mcp.server
```

The server will:
1. Load config from `migration_oracle/config.py`
2. Verify graph connectivity (`RETURN 1`)
3. Ensure all indexes via `graph/indexes.py`
4. Begin accepting MCP tool calls on stdin/stdout

On success you will see structured log output like:
```
INFO  startup: config loaded
INFO  startup: graph connectivity OK (bolt://localhost:7687)
INFO  startup: indexes ensured (15 statements)
INFO  startup: PaysafeMigrationOracle ready — 21 tools, 4 resources, 1 prompt
```

---

## Connecting a Test Client

### Using the MCP Inspector (browser-based)

```bash
# Install MCP Inspector globally
npm install -g @modelcontextprotocol/inspector

# Connect to a stdio server
mcp-inspector uv run python -m migration_oracle.mcp.server
```

Open the Inspector UI at `http://localhost:5173`.

### Using the MCP Python SDK test client

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test():
    params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "migration_oracle.mcp.server"],
        env={"NEO4J_URI": "bolt://localhost:7687", "NEO4J_PASSWORD": "pass"}
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"Tools: {len(tools.tools)}")

asyncio.run(test())
```

---

## Starting in SSE or HTTP Mode

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=your-password
export MCP_TRANSPORT=sse
export MCP_HOST=0.0.0.0
export MCP_PORT=8080

uv run python -m migration_oracle.mcp.server
```

For stateless HTTP (remote clients, no session affinity):
```bash
export MCP_TRANSPORT=streamable-http
export MCP_STATELESS_HTTP=true
uv run python -m migration_oracle.mcp.server
```

---

## Verifying All 21 Tools Register

### Via MCP Inspector

After connecting, switch to the "Tools" tab. You should see exactly 21 tools listed, organised by group:

- **Upgrade**: `analyze_upgrade_path`, `build_recipe_plan`
- **Deprecation**: `resolve_deprecation`, `entity_evolution`
- **Search**: `search_migration_knowledge`, `search_openrewrite_recipes`
- **Schema**: `get_graph_schema`, `execute_custom_cypher`
- **Community**: `submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight`
- **Context**: `create_migration_context`, `get_pending_steps`, `update_step_status`, `get_steps_for_scope_tier`, `close_migration_context`
- **Paysafe**: `resolve_paysafe_dependency_by_service_name`
- **Artifacts**: `list_pipeline_runs`, `get_artifact_content`
- **Install**: `install_migration_skill`

### Via CLI flag (once implemented in server.py)

```bash
uv run python -m migration_oracle.mcp.server --list-tools
# Expected output:
# 21 tools registered:
#   analyze_upgrade_path
#   build_recipe_plan
#   ...
```

---

## Running the Test Suite (No Running Neo4j Required)

All unit tests mock the graph driver. You do not need a running Neo4j or Memgraph instance to run the unit test suite.

```bash
# Run all MCP tests
uv run pytest tests/mcp/ -v

# Run a specific test module
uv run pytest tests/mcp/test_schema.py -v

# Run with coverage
uv run pytest tests/mcp/ --cov=migration_oracle/mcp --cov-report=term-missing
```

### Mock pattern used in tests

```python
from unittest.mock import MagicMock, patch

@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_analyze_upgrade_path_empty_graph(mock_session):
    mock_session.return_value.__enter__.return_value.run.return_value = iter([])
    result = analyze_upgrade_path(framework="Spring Boot", current_version="3.0", target_version="3.4")
    assert result["status"] == "ok"
    assert result["rules"] == []
```

### Integration tests (require seeded graph)

Tests in `tests/mcp/test_context.py` that exercise `get_pending_steps`, `get_steps_for_scope_tier`, and `build_recipe_plan` step-level paths require a graph with `MigrationStep` and `BreakingScope` nodes (Increment 1 pipeline run). To run these:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_PASSWORD=test
uv run pytest tests/mcp/test_context.py -v -m integration
```

---

## Configuring Claude Code to Use the Server

Add to your Claude Code MCP settings (`.claude/mcp.json` or Claude Code settings UI):

```json
{
  "mcpServers": {
    "migration-oracle": {
      "command": "uv",
      "args": ["run", "python", "-m", "migration_oracle.mcp.server"],
      "cwd": "/path/to/paysafe-version-migration-graph",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

## Configuring Cursor to Use the Server

Add to `.cursor/mcp.json` in the project root:

```json
{
  "mcpServers": {
    "migration-oracle": {
      "command": "uv",
      "args": ["run", "python", "-m", "migration_oracle.mcp.server"],
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

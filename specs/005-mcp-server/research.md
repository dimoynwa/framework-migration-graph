# Research: PaysafeMigrationOracle MCP Server (005)

**Phase 0 output** | Branch: `005-mcp-server` | Date: 2026-06-07

---

## 1. MCP Framework Choice

**Decision**: Use `mcp.server.fastmcp.FastMCP` from the official `mcp>=1.0` SDK.

**Rationale**: The project already declares `mcp>=1.0` in `pyproject.toml`. Since MCP SDK 1.0, the `FastMCP` convenience layer ships inside the official package as `mcp.server.fastmcp`. It provides decorator-based tool registration (`@mcp.tool`), resource registration (`@mcp.resource`), and prompt registration (`@mcp.prompt`) with automatic JSON schema generation from Python type annotations. Transport selection (stdio / SSE / streamable-HTTP) is handled by passing the transport name to `mcp.run()`. No third-party wrapper is required; no raw stdio protocol implementation is needed.

**Alternatives considered**:

| Option | Verdict |
|--------|---------|
| `fastmcp` (third-party, PyPI) | Redundant — its functionality was absorbed into the official SDK at 1.0. Adds a dependency without benefit. |
| `mcp-python` (raw SDK, pre-1.0 name) | Superseded by `mcp>=1.0`. |
| Raw stdio (manual JSON-RPC) | Too low-level; would require implementing the full MCP protocol wire format, negotiation, and schema serialisation by hand. Maintenance burden without benefit. |

**Transport selection in `server.py`**:

```python
from mcp.server.fastmcp import FastMCP
from migration_oracle import config

mcp = FastMCP("PaysafeMigrationOracle")

# ... register tools, resources, prompts ...

if __name__ == "__main__":
    transport = config.MCP_TRANSPORT  # "stdio" | "sse" | "streamable-http"
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        mcp.run(transport="sse", host=config.MCP_HOST, port=config.MCP_PORT)
    elif transport == "streamable-http":
        mcp.run(transport="streamable-http", host=config.MCP_HOST, port=config.MCP_PORT,
                stateless_http=(config.MCP_STATELESS_HTTP == "true"))
```

---

## 2. SentenceTransformer Loading Strategy

**Decision**: Lazy singleton at module level in `mcp/tools/search.py`, exposed via `get_embedding_model()`. Model is NOT loaded at server startup.

**Rationale**: The spec (FR-017) explicitly mandates the lazy singleton pattern with `_model: SentenceTransformer | None = None` and the exact `if _model is None: _model = SentenceTransformer(...)` check-then-assign. The startup sequence (FR-004) does not include model loading. This means the first hybrid search call incurs a one-time load cost (5–30 seconds on first run, cached in memory thereafter). The tradeoff is acceptable because:

1. Startup time stays fast for all non-search tool calls.
2. The model is cached in process memory after the first call, so per-call overhead after warmup is sub-millisecond for encoding.
3. SC-007 requires the model to load exactly once per process — the singleton pattern guarantees this.

**If missing model at startup is a concern**: The spec says (Assumptions) that missing model files cause a hard startup failure. To surface this early, `server.py` can call `get_embedding_model()` during the startup sequence after step 3 (index check) to force an eager fail if the model file is absent, while still keeping the production load path lazy.

**Alternatives considered**:

| Option | Verdict |
|--------|---------|
| Eager load at startup | Adds 5–30 seconds to `python -m migration_oracle.mcp.server` startup. Ruled out because FR-004 startup sequence does not include model loading, and spec is explicit about lazy pattern. |
| Load per request | Violates FR-017 and SC-007. ~15 second overhead per search call. Rejected. |
| Thread-local instance | Unnecessary complexity. A single module-level instance is safe for concurrent reads because `encode()` on SentenceTransformer is thread-safe for inference. |

---

## 3. Hybrid Search: Parallel vs Sequential FTS + Vector Queries

**Decision**: Run BM25 (FTS) and vector queries in parallel using `asyncio.gather()` when the tool handler is async, or `concurrent.futures.ThreadPoolExecutor` when the Neo4j driver is used synchronously.

**Rationale**: The two index queries are independent — BM25 hits the full-text index; vector hits the vector index. They can be issued in parallel to the same Neo4j/Memgraph instance. The official `neo4j` Python driver uses synchronous Bolt sessions; to parallelize, wrap each query call in a thread. The FastMCP framework supports `async def` tool handlers, allowing `asyncio.run_in_executor` for I/O-bound graph calls.

**Implementation pattern**:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=8)

async def _parallel_search(bm25_fn, vector_fn):
    loop = asyncio.get_event_loop()
    bm25_task = loop.run_in_executor(_executor, bm25_fn)
    vector_task = loop.run_in_executor(_executor, vector_fn)
    bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)
    return bm25_results, vector_results
```

**RRF fusion** (Reciprocal Rank Fusion, k=60):

```python
def rrf_fuse(bm25_hits: list[str], vector_hits: list[str], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for rank, node_id in enumerate(bm25_hits, start=1):
        scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank)
    for rank, node_id in enumerate(vector_hits, start=1):
        scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda x: scores[x], reverse=True)
```

**Alternatives considered**:

| Option | Verdict |
|--------|---------|
| Sequential (BM25 then vector) | Simpler but 2× latency. Acceptable for low concurrency but violates SC-001 (2-second response target). |
| Async Neo4j driver (`neo4j-async`) | Available but not in current `pyproject.toml`. Adding it would change the driver layer. Ruled out to avoid scope creep. |
| Single hybrid Cypher query | Memgraph does not support combining FTS and vector indexes in one query. Neo4j 5.x supports this with `db.index.fulltext.queryNodes` + vector call but in-query parallelism is not guaranteed. Separate queries with application-level fusion is more portable. |

---

## 4. Memgraph-Specific Index DDL Compatibility Gaps

**Decision**: Use the existing `ensure_indexes()` pattern from `migration_oracle/graph/indexes.py` — catch `ClientError`, `CypherSyntaxError`, `DatabaseError` per statement, log and continue.

**Known gaps**:

| DDL statement | Neo4j 5.x | Memgraph | Mitigation |
|---|---|---|---|
| `CREATE FULLTEXT INDEX ... IF NOT EXISTS` | ✅ | ✅ (since 2.13) | None needed. |
| `CREATE CONSTRAINT ... IF NOT EXISTS` | ✅ | ✅ (since 2.10) | None needed. |
| Composite uniqueness constraint `REQUIRE (a, b) IS UNIQUE` | ✅ | ✅ | None needed. |
| Vector index (`CREATE VECTOR INDEX`) | ✅ Neo4j 5.11+ | ❌ Not supported | Memgraph uses its own vector module. The server logs a DDL warning and continues — hybrid search degrades to BM25-only on Memgraph. |
| `IF NOT EXISTS` on FULLTEXT (older Memgraph < 2.13) | N/A | ❌ Throws `CypherSyntaxError` | Caught and logged by `ensure_indexes()`. Server continues. |

**Degraded mode on Memgraph**: When vector index DDL fails, `search_migration_knowledge` and `search_openrewrite_recipes` must detect the absence of the vector index and fall back to BM25-only results. The `mcp/graph/queries/search.py` module should catch `ClientError` from the vector query and return an empty list, allowing RRF to still work on BM25 results alone.

**Startup sequence**: The existing `graph/indexes.py` already wraps each DDL statement in a try/except and logs the failure. The MCP server startup (FR-004, step 3) calls `ensure_indexes(get_driver())` directly. No additional wrapping is needed.

---

## 5. MCP_STATELESS_HTTP Environment Variable

`config.py` does not currently define `MCP_STATELESS_HTTP`. It must be added to `migration_oracle/config.py` as:

```python
MCP_STATELESS_HTTP: bool = _parse_bool_flag(_optional("MCP_STATELESS_HTTP", "false"))
```

This is the only config addition required by spec 005.

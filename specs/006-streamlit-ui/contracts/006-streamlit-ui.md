# Interface Contract: Streamlit Operator UI (006-streamlit-ui)

**Date**: 2026-06-08  
**Type**: UI boundary contract (page-to-tool and page-to-subprocess boundaries)

---

## Graph Access Boundary

| Rule | Rationale |
|------|-----------|
| Pages MUST import tool functions from `migration_oracle.mcp.tools.*` | All graph access is centralized in tool functions; no Cypher queries in page code |
| Pages MUST NOT call `open()`, `Path.read_text()`, `pathlib.Path().read_bytes()`, or any equivalent filesystem read | Artifact content arrives exclusively via `get_artifact_content()` |
| Pages MUST NOT import from `migration_oracle.graph.*` or construct/execute Cypher queries directly | Graph queries are encapsulated in tool functions |
| Pages MUST NOT spawn or connect to an MCP server process | Tool functions are plain Python callables; no MCP server subprocess or TCP socket is used |

---

## Pipeline Invocation Boundary

| Rule | Rationale |
|------|-----------|
| The Pipeline Trigger page MUST invoke the CLI via `subprocess.Popen` | Importing the CLI entry point couples the app process to pipeline side effects |
| The subprocess command MUST be built as a list: `[sys.executable, "-m", "migration_oracle.cli", "--framework", key, from_version, to_version] + flags` | `sys.executable` ensures the same interpreter; list form prevents shell injection |
| `shell=True` is prohibited | Operator-supplied version strings must not be shell-interpolated |
| The Pipeline Trigger page MUST NOT `import migration_oracle.cli` or call any function from it | Subprocess isolation is an explicit architectural boundary |

---

## Error Handling Boundary

| Rule | Rationale |
|------|-----------|
| All calls to tool functions MUST be wrapped in `try/except Exception` | Any tool exception must be caught at the page boundary |
| Caught exceptions MUST be surfaced via `st.error(str(e))` | No raw traceback may reach the operator |
| `st.exception()` (which renders a full traceback) MUST NOT be used in page code | Tracebacks contain internal paths and implementation details not appropriate for operators |

---

## Async Tool Boundary

| Rule | Rationale |
|------|-----------|
| `search_migration_knowledge` is `async def` and MUST be called with `asyncio.run(search_migration_knowledge(...))` | Streamlit page scripts run in a synchronous context; `await` is not available at module scope |
| Do NOT use `asyncio.get_event_loop().run_until_complete(...)` | Deprecated; `asyncio.run()` is the correct pattern for Python 3.11+ |

---

## Caching Boundary

| Rule | Value |
|------|-------|
| `list_pipeline_runs()` MUST be wrapped with `@st.cache_data(ttl=60)` in the Run Browser | Avoids redundant Neo4j queries on every Streamlit rerun within 60 seconds |
| No other tool function call is cached at this time | Only run enumeration benefits from a TTL cache; artifact and context reads are on-demand |

---

## Session State Boundary

| Rule | Detail |
|------|--------|
| The loaded migration context on the Context Dashboard MUST be stored in `st.session_state` using 8 flat prefixed keys | Survives page rerenders within the same browser session |
| Keys are: `"context_id"`, `"context_project_id"`, `"context_from_version"`, `"context_to_version"`, `"context_framework"`, `"context_status"`, `"context_completed_count"`, `"context_skipped_count"` | All set atomically after a successful `create_migration_context` call |
| `"context_status"` and `"context_completed_count"` / `"context_skipped_count"` MUST be updated after each `update_step_status` call from the response's `completed_count` and `skipped_count` fields | Metrics must reflect real-time step actions, not only the initial load |
| No single `"context"` dict key exists — individual flat keys only | Avoids silent key-not-found bugs from accessing nested dict fields |
| No other page reads or writes these keys — they are private to `04_context_dashboard.py` | Only the Context Dashboard requires persistence across rerenders |

---

## Tool Call Signature Constraints

These are hard facts derived from the actual implementations (see `research.md` §Critical Discrepancies).

| Call site | Correct form | Incorrect form (do not use) |
|-----------|-------------|----------------------------|
| Upvote | `vote_insight(insight_id=id, delta=1)` | `vote_insight(insight_id=id, direction="up")` |
| Search (specific framework) | `asyncio.run(search_migration_knowledge(query=q, framework="Spring Boot", max_results=20))` — display name | `search_migration_knowledge(query=q, framework="spring-boot", ...)` — CLI key does not match what the search function expects |
| Search (all frameworks) | Pass `framework=None` explicitly: `asyncio.run(search_migration_knowledge(query=q, framework=None, max_results=20))` — Cypher `WHERE $framework IS NULL` returns all | Omitting the `framework` kwarg (applies default `"Spring Boot"`) or passing `"all"` — omitting narrows to Spring Boot, `"all"` is not a valid name |
| Community page load | `get_community_insights()` | `get_community_insights(version_filter="", top_k=20)` |
| Submit insight URL field | `evidence_url=url` | `source_url=url` |
| Submit insight version field | `spring_boot_version=version` | `version_tag=version` |

---

## Empty-State Contract

Every page that queries data MUST check for empty/error results before rendering data-dependent widgets.

| Page | Empty trigger | Required response |
|------|--------------|-------------------|
| Run Browser | `runs == []` | `st.info("No pipeline runs found")` — no selectbox or tabs |
| Rule Explorer | `hits == []` | `st.info("No rules found for this query")` |
| Context Dashboard | `pending_steps == []` | `st.info("No pending steps remaining")` — no table |
| Community | `insights == []` | `st.info("No community insights found")` — no cards |

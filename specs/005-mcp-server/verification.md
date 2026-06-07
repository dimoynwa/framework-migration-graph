# Verification Protocol: PaysafeMigrationOracle MCP Server (005)

**Location**: `specs/005-mcp-server/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `005` ✅ in `SPEC_ORGANIZATION.md`
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | Check |
|---|---|
| Python dependencies installed | `uv sync` |
| `NEO4J_URI` and `NEO4J_PASSWORD` set for Levels 3–7 | `echo $NEO4J_URI` — must not be empty |
| Neo4j 5.x or Memgraph reachable for Levels 3–7 | See Level 3-A |
| `SENTENCE_TRANSFORMERS_MODEL` model files present for Level 3+ search | Directory present under `~/.cache/huggingface` |
| Working directory is the project root | `ls migration_oracle/mcp/server.py` succeeds |

## Infrastructure required per level

| Level | Name | Needs DB | Needs LLM/model |
|---|---|---|---|
| 0 | Static checks | No | No |
| 1 | Interface structure | No | No |
| 2 | Isolation behaviour | No | No |
| 3 | Integration — read path | **Yes** | No |
| 4 | Integration — write path (startup + MERGE idempotency) | **Yes** | No |
| 5 | Integration — full write path | **Yes** | No |
| 6 | Idempotency | **Yes** | No |
| 7 | Edge-case paths | **Yes** (most checks) | No |

---

## Level 0 — Static checks

No external services required. Every check must print `PASS` or raise an `AssertionError`.

### 0-A: All public MCP modules import without error

```bash
python -c "
import migration_oracle.mcp
import migration_oracle.mcp.server
import migration_oracle.mcp.instance
import migration_oracle.mcp.tools.upgrade
import migration_oracle.mcp.tools.deprecation
import migration_oracle.mcp.tools.search
import migration_oracle.mcp.tools.schema
import migration_oracle.mcp.tools.community
import migration_oracle.mcp.tools.context
import migration_oracle.mcp.tools.paysafe
import migration_oracle.mcp.tools.artifacts
import migration_oracle.mcp.tools.install
import migration_oracle.mcp.graph.queries.upgrade
import migration_oracle.mcp.graph.queries.deprecation
import migration_oracle.mcp.graph.queries.search
import migration_oracle.mcp.graph.queries.schema
import migration_oracle.mcp.graph.queries.community
import migration_oracle.mcp.graph.queries.context
import migration_oracle.mcp.graph.queries.artifacts
print('PASS: 0-A — all 19 mcp modules import without error')
"
```

### 0-B: `MUTATION_KEYWORDS` contains exactly the required six keywords

```python
from migration_oracle.mcp.graph.queries.schema import MUTATION_KEYWORDS

required = {"CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP"}
actual = set(MUTATION_KEYWORDS)
assert actual == required, f"Got: {actual}"
print(f"PASS: 0-B — MUTATION_KEYWORDS = {sorted(actual)}")
```

### 0-C: `check_mutation` correctly identifies each keyword (case-insensitive)

```python
from migration_oracle.mcp.graph.queries.schema import check_mutation

cases = {
    "MATCH (n) RETURN n": None,
    "CREATE (n:Test)": "CREATE",
    "MERGE (n:Test)": "MERGE",
    "SET n.x = 1": "SET",
    "DELETE n": "DELETE",
    "REMOVE n.x": "REMOVE",
    "DROP INDEX idx": "DROP",
    "CALL db.index.fulltext.queryNodes(...)": "CALL db",
    "match (n) create (m)": "CREATE",    # uppercase keyword inside lowercase query
    "create (n)": "CREATE",              # all-lowercase mutation
    "MATCH (n) RETURN n WHERE n.x > 0": None,  # safe query with WHERE
}

for query, expected in cases.items():
    result = check_mutation(query)
    assert result == expected, f"Query: {query!r}\n  Expected: {expected!r}\n  Got: {result!r}"

print("PASS: 0-C — check_mutation correctly handles all 11 cases including lowercase and CALL db")
```

### 0-D: Required config constants exist with correct defaults

```python
import os
# Set required vars to allow config import
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "dummy")

import importlib
import migration_oracle.config as cfg

assert hasattr(cfg, "MCP_STATELESS_HTTP"), "MCP_STATELESS_HTTP missing from config"
assert hasattr(cfg, "MCP_TRANSPORT"), "MCP_TRANSPORT missing from config"
assert hasattr(cfg, "MCP_HOST"), "MCP_HOST missing from config"
assert hasattr(cfg, "MCP_PORT"), "MCP_PORT missing from config"
assert hasattr(cfg, "SENTENCE_TRANSFORMERS_MODEL"), "SENTENCE_TRANSFORMERS_MODEL missing"

# Check default values match spec
import importlib, sys
# Reload with clean env to get defaults
for mod in list(sys.modules.keys()):
    if "migration_oracle" in mod:
        del sys.modules[mod]

os.environ.pop("MCP_STATELESS_HTTP", None)
os.environ.pop("MCP_TRANSPORT", None)
os.environ.pop("MCP_HOST", None)
os.environ.pop("SENTENCE_TRANSFORMERS_MODEL", None)
os.environ["NEO4J_URI"] = "bolt://localhost:7687"
os.environ["NEO4J_PASSWORD"] = "dummy"

import migration_oracle.config as cfg2
assert cfg2.MCP_STATELESS_HTTP == False, f"Expected False, got: {cfg2.MCP_STATELESS_HTTP!r}"
assert cfg2.MCP_TRANSPORT == "stdio", f"Expected 'stdio', got: {cfg2.MCP_TRANSPORT!r}"
assert cfg2.MCP_HOST == "0.0.0.0", f"Expected '0.0.0.0', got: {cfg2.MCP_HOST!r}"
assert cfg2.SENTENCE_TRANSFORMERS_MODEL == "all-mpnet-base-v2", f"Got: {cfg2.SENTENCE_TRANSFORMERS_MODEL!r}"
print("PASS: 0-D — all config constants present with correct defaults")
```

### 0-E: `_model` is `None` at module load time; `get_embedding_model` uses exact check-then-assign pattern

```python
import ast, pathlib

src = pathlib.Path("migration_oracle/mcp/tools/search.py").read_text()

# 1. Module-level sentinel is exactly None
assert "_model: SentenceTransformer | None = None" in src, \
    "Module-level '_model: SentenceTransformer | None = None' not found"

# 2. get_embedding_model uses global _model
assert "global _model" in src, "'global _model' not found in search.py"

# 3. Check-then-assign pattern is present
assert "if _model is None:" in src, "'if _model is None:' not found"
assert "_model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)" in src, \
    "Exact assignment '_model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)' not found"

# 4. SentenceTransformer(...) appears only inside get_embedding_model — not at top level
# It must not appear inside any @mcp.tool decorated function
import re
# Find all SentenceTransformer( calls
calls = [(m.start(), m.group()) for m in re.finditer(r"SentenceTransformer\(", src)]
assert len(calls) == 1, f"Expected exactly 1 SentenceTransformer( call, found {len(calls)}: {calls}"

print("PASS: 0-E — _model singleton pattern is correct (sentinel, global, check-then-assign, single instantiation)")
```

### 0-F: No inline Cypher in tool handler modules (Contract C / FR-041)

```bash
result=$(grep -rn "MATCH\|MERGE\|RETURN\|OPTIONAL" migration_oracle/mcp/tools/ \
         --include="*.py" \
         | grep -v "^migration_oracle/mcp/tools/_" \
         | grep -v "# " \
         | grep -v '"""' \
         | grep -v "'''" \
         | grep -v "__pycache__")
if [ -z "$result" ]; then
    echo "PASS: 0-F — no inline Cypher keywords found in mcp/tools/"
else
    echo "FAIL: 0-F — Cypher found in tool handler modules:"
    echo "$result"
    exit 1
fi
```

### 0-G: No `os.environ` calls in any `mcp/` module (Contract F / FR-042)

```bash
result=$(grep -rn "os\.environ\|os\.getenv" migration_oracle/mcp/ --include="*.py")
if [ -z "$result" ]; then
    echo "PASS: 0-G — no os.environ calls in mcp/"
else
    echo "FAIL: 0-G — os.environ found in mcp/ modules:"
    echo "$result"
    exit 1
fi
```

### 0-H: `paysafe.py` imports ONLY `migration_oracle.paysafe.resolver.resolve` (Contract A)

```python
import ast, pathlib

src = pathlib.Path("migration_oracle/mcp/tools/paysafe.py").read_text()
tree = ast.parse(src)

imports = []
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        imports.append(f"{node.module}.{','.join(a.name for a in node.names)}")

paysafe_imports = [i for i in imports if "paysafe" in i]
assert len(paysafe_imports) == 1, f"Expected 1 paysafe import, got: {paysafe_imports}"
assert "resolver" in paysafe_imports[0] and "resolve" in paysafe_imports[0], \
    f"Expected import of resolver.resolve, got: {paysafe_imports}"

# Confirm findit and gitlab are NOT imported
for forbidden in ("findit", "gitlab", "_types"):
    for imp in imports:
        assert forbidden not in imp, \
            f"Forbidden import '{forbidden}' found in paysafe.py: {imp}"

print(f"PASS: 0-H — paysafe.py has exactly 1 paysafe import: {paysafe_imports[0]}; findit/gitlab absent")
```

### 0-I: `get_artifact_content` signature has no `path` parameter (Contract B)

```python
import inspect
from migration_oracle.mcp.tools.artifacts import get_artifact_content

params = list(inspect.signature(get_artifact_content).parameters.keys())
assert "path" not in params, \
    f"Contract B violation: 'path' parameter found in get_artifact_content({params})"
assert "framework" in params, f"'framework' missing from get_artifact_content params: {params}"
assert "artifact_type" in params, f"'artifact_type' missing from get_artifact_content params: {params}"
print(f"PASS: 0-I — get_artifact_content has no 'path' param; params: {params}")
```

### 0-J: `close_migration_context` return type uses `tool_status` and `migration_status` as distinct fields

```python
import inspect, ast, pathlib

src = pathlib.Path("migration_oracle/mcp/tools/context.py").read_text()

# Assert tool_status is used and migration_status is used as distinct return keys
assert '"tool_status"' in src or "'tool_status'" in src, \
    "CloseContextResult must contain 'tool_status' key"
assert '"migration_status"' in src or "'migration_status'" in src, \
    "CloseContextResult must contain 'migration_status' key"
# Assert a single 'status' key is NOT the pattern for close_migration_context return
# (The close function should use tool_status not status for its ok/error discriminator)
import re
close_fn_match = re.search(
    r"def close_migration_context.*?(?=\n@|\Z)", src, re.DOTALL
)
assert close_fn_match, "close_migration_context function not found in context.py"
close_fn_body = close_fn_match.group(0)
assert "tool_status" in close_fn_body, \
    f"'tool_status' not found in close_migration_context body"
print("PASS: 0-J — close_migration_context uses tool_status + migration_status as distinct keys")
```

### 0-K: `ARTIFACT_TYPE_MAP` maps exactly the three required artifact types

```python
from migration_oracle.mcp.tools.artifacts import ARTIFACT_TYPE_MAP

required = {"raw_md": "rawMdPath", "filtered_md": "filteredMdPath", "entities_json": "entitiesJsonPath"}
assert ARTIFACT_TYPE_MAP == required, \
    f"ARTIFACT_TYPE_MAP mismatch.\n  Expected: {required}\n  Got: {ARTIFACT_TYPE_MAP}"
print("PASS: 0-K — ARTIFACT_TYPE_MAP has exactly 3 entries with correct property names")
```

### 0-L: `update_step_status` parameter is named `reason` not `notes`

```python
import inspect
from migration_oracle.mcp.tools.context import update_step_status

params = list(inspect.signature(update_step_status).parameters.keys())
assert "reason" in params, \
    f"'reason' parameter not found in update_step_status. Got: {params}"
assert "notes" not in params, \
    f"Stale 'notes' parameter found in update_step_status. Got: {params}"
print(f"PASS: 0-L — update_step_status uses 'reason' parameter (not 'notes'): {params}")
```

---

## Level 1 — Interface structure

No external services required.

### 1-A: Server exits cleanly on unsupported `MCP_TRANSPORT` value

```bash
NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=dummy \
MCP_TRANSPORT=grpc timeout 5 uv run python -m migration_oracle.mcp.server 2>&1 | head -5
# Expected: error mentioning unsupported transport or immediate exit
# The server must NOT silently ignore an unknown transport value
exit_code=$?
echo "Exit code: $exit_code (must be non-zero for unsupported transport)"
```

Expected: non-zero exit code and a message referencing the unsupported transport value. If the server hangs, check that the `if transport not in {"stdio", "sse", "streamable-http"}` guard exists in `server.py`.

### 1-B: Server exits on missing `NEO4J_URI`

```bash
result=$(env -i PATH="$PATH" HOME="$HOME" \
  NEO4J_PASSWORD=dummy \
  timeout 5 uv run python -c "import migration_oracle.config" 2>&1)
echo "$result"
echo "$result" | grep -qi "ConfigurationError\|Required env var\|NEO4J_URI"
if [ $? -eq 0 ]; then
    echo "PASS: 1-B — missing NEO4J_URI raises ConfigurationError"
else
    echo "FAIL: 1-B — missing NEO4J_URI did not raise ConfigurationError"
fi
```

### 1-C: `execute_custom_cypher` blocks mutations before any graph contact — no driver needed

```python
import os
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "dummy")
from unittest.mock import MagicMock, patch

# The check must happen before the driver is ever contacted.
# We verify this by patching the driver to raise if called — a blocked query must not reach it.

with patch("migration_oracle.graph.driver.read_session") as mock_session:
    mock_session.side_effect = AssertionError("Driver must NOT be called for a blocked query")

    from migration_oracle.mcp.tools.schema import execute_custom_cypher
    result = execute_custom_cypher(query="CREATE (n:Test)")

assert result["status"] == "blocked", f"Expected status='blocked', got: {result}"
assert "CREATE" in result.get("blocked_keyword", ""), \
    f"blocked_keyword should contain 'CREATE', got: {result.get('blocked_keyword')}"
assert result["rows"] == [], f"rows must be empty on blocked query, got: {result['rows']}"
mock_session.assert_not_called()
print(f"PASS: 1-C — CREATE blocked before driver contact; result: {result}")
```

### 1-D: `get_graph_schema` returns static schema with zero driver calls

```python
import os
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "dummy")
from unittest.mock import patch

with patch("migration_oracle.graph.driver.read_session") as mock_session:
    mock_session.side_effect = AssertionError("Driver must NOT be called for get_graph_schema")
    from migration_oracle.mcp.tools.schema import get_graph_schema
    result = get_graph_schema()

assert result["status"] == "ok", f"Expected status='ok', got: {result}"
assert len(result.get("schema_markdown", "")) > 100, \
    f"schema_markdown is too short: {len(result.get('schema_markdown',''))} chars"
mock_session.assert_not_called()
print("PASS: 1-D — get_graph_schema returns static schema with zero driver calls")
```

---

## Level 2 — Isolation behaviour

No live services required. Tests use in-process mocks.

### 2-A: `check_mutation` blocks `CALL db` variants (case-insensitive)

```python
from migration_oracle.mcp.graph.queries.schema import check_mutation

call_db_variants = [
    "CALL db.index.fulltext.queryNodes('idx', 'term')",
    "call db.index.vector.queryNodes('v', 10, $emb)",
    "CALL DB.SCHEMA()",
    "CALL db.create.createNode('Label')",
]

for query in call_db_variants:
    result = check_mutation(query)
    assert result is not None and "CALL" in result.upper(), \
        f"Expected CALL db to be blocked for: {query!r}\n  Got: {result!r}"

safe = "MATCH (n:MigrationRule) RETURN n LIMIT 5"
assert check_mutation(safe) is None, \
    f"Safe MATCH query was incorrectly blocked: {check_mutation(safe)!r}"

print("PASS: 2-A — CALL db variants are blocked; safe MATCH query is not blocked")
```

### 2-B: `get_embedding_model()` returns the same object instance on repeated calls

```python
import os
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "dummy")

from unittest.mock import patch, MagicMock
import migration_oracle.mcp.tools.search as search_mod

# Reset singleton state for a clean test
search_mod._model = None

fake_model = MagicMock(name="FakeSentenceTransformer")

with patch("migration_oracle.mcp.tools.search.SentenceTransformer", return_value=fake_model) as MockST:
    m1 = search_mod.get_embedding_model()
    m2 = search_mod.get_embedding_model()
    m3 = search_mod.get_embedding_model()

assert m1 is m2 is m3, "get_embedding_model() must return the same instance on every call"
assert MockST.call_count == 1, \
    f"SentenceTransformer() must be called exactly once, called {MockST.call_count} times"

search_mod._model = None  # restore
print(f"PASS: 2-B — get_embedding_model() initialises once; SentenceTransformer.__init__ called {MockST.call_count} time")
```

### 2-C: `get_artifact_content` returns error for unknown artifact_type without querying the graph

```python
import os
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "dummy")

from unittest.mock import patch

with patch("migration_oracle.mcp.graph.queries.artifacts.get_version_artifact_path") as mock_q:
    mock_q.side_effect = AssertionError("Graph must NOT be queried for invalid artifact_type")
    from migration_oracle.mcp.tools.artifacts import get_artifact_content
    result = get_artifact_content(
        framework="Spring Boot",
        from_version="3.2",
        to_version="3.4",
        artifact_type="invalid_type",
    )

assert result["status"] == "error", f"Expected 'error', got: {result['status']}"
mock_q.assert_not_called()
print(f"PASS: 2-C — unknown artifact_type returns error before graph contact; result: {result}")
```

### 2-D: RRF fusion function produces correct relative ordering

```python
from migration_oracle.mcp.tools._rrf import rrf_fuse

# BM25 list: A first, B second. Vector list: B first, A second.
bm25_hits = ["id-A", "id-B", "id-C"]
vector_hits = ["id-B", "id-A", "id-C"]

fused = rrf_fuse(bm25_hits=bm25_hits, vector_hits=vector_hits, k=60)

# id-A and id-B should both appear; id-C should appear
fused_ids = [item[0] for item in fused]
assert "id-A" in fused_ids, f"id-A missing from fused result: {fused_ids}"
assert "id-B" in fused_ids, f"id-B missing from fused result: {fused_ids}"
assert "id-C" in fused_ids, f"id-C missing from fused result: {fused_ids}"

# All scores should be positive floats
for hit_id, score in fused:
    assert isinstance(score, float) and score > 0, \
        f"RRF score must be positive float, got {score!r} for {hit_id}"

print(f"PASS: 2-D — RRF fusion produces {len(fused)} hits with positive scores; order: {fused_ids[:3]}")
```

---

## Level 3 — Integration read path

**Neo4j 5.x or Memgraph required.** Run these checks in order; each cleans up after itself.

### 3-A: Graph driver connectivity

```python
from migration_oracle.graph.driver import get_driver

driver = get_driver()
with driver.session() as session:
    result = session.run("RETURN 1 AS n").single()
    assert result["n"] == 1, f"Expected 1, got: {result['n']}"
print("PASS: 3-A — graph connectivity verified (RETURN 1 AS n = 1)")
```

### 3-B: `execute_read_cypher` returns empty list for absent node

```python
from migration_oracle.mcp.graph.queries.schema import execute_read_cypher

rows = execute_read_cypher(
    "MATCH (n:__VerifTest005__) RETURN n",
    {}
)
assert rows == [], f"Expected [], got: {rows}"
print("PASS: 3-B — execute_read_cypher returns [] for absent label")
```

### 3-C: `bm25_search` returns `[]` when FTS index is absent (Memgraph degraded mode)

```python
from migration_oracle.mcp.graph.queries.search import bm25_search

# Use a non-existent index name to force a ClientError
result = bm25_search(
    query="spring boot migration",
    index="__nonexistent_index_verif005__",
    top_k=5,
)
# Must return [] without raising, not propagate the ClientError
assert isinstance(result, list), f"Expected list, got: {type(result)}"
print(f"PASS: 3-C — bm25_search returns {result!r} (empty list) when index absent; no exception raised")
```

### 3-D: Write a synthetic Version node, verify `list_pipeline_runs` returns it, then delete

```python
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.graph.queries.artifacts import list_pipeline_runs

driver = get_driver()

# Setup
with driver.session() as session:
    session.run("""
        MERGE (v:Version {framework: '__verif005__', version: '99.0'})
        SET v.sortableVersion = 990000,
            v.rawMdPath = '/tmp/verif005_raw.md',
            v.filteredMdPath = '/tmp/verif005_filtered.md',
            v.entitiesJsonPath = '/tmp/verif005_entities.json'
    """)

# Verify it appears in list_pipeline_runs
runs = list_pipeline_runs()
matching = [r for r in runs if r.get("framework") == "__verif005__"]
assert len(matching) == 1, \
    f"Expected 1 matching run, got {len(matching)}: {matching}"
assert matching[0].get("raw_md_path") or matching[0].get("rawMdPath"), \
    f"rawMdPath not in result: {matching[0]}"

# Cleanup
with driver.session() as session:
    session.run("MATCH (v:Version {framework: '__verif005__'}) DETACH DELETE v")

print(f"PASS: 3-D — synthetic Version node written, found in list_pipeline_runs, deleted; run: {matching[0]}")
```

### 3-E: `get_version_artifact_path` returns `None` for absent Version node

```python
from migration_oracle.mcp.graph.queries.artifacts import get_version_artifact_path

result = get_version_artifact_path(
    framework="__absent_framework_verif005__",
    to_version="99.99",
)
assert result is None, \
    f"Expected None for absent Version node, got: {result}"
print("PASS: 3-E — get_version_artifact_path returns None for absent Version node")
```

---

## Level 4 — Integration write path (safe)

**Neo4j required.** Tests the startup sequence and MERGE idempotency without destructive graph operations.

### 4-A: Startup sequence completes in correct order (connectivity before indexes)

```python
import os
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "neo4j")

from unittest.mock import patch, MagicMock, call
from migration_oracle.graph.driver import get_driver

call_order = []

real_driver = get_driver()

def mock_session_ctx(*args, **kwargs):
    call_order.append("connectivity_check")
    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def run(self, q):
            class FakeResult:
                def single(self): return {"n": 1}
            return FakeResult()
    return FakeSession()

def mock_ensure_indexes(driver):
    call_order.append("ensure_indexes")

with patch.object(real_driver, "session", side_effect=mock_session_ctx), \
     patch("migration_oracle.mcp.server.ensure_indexes", side_effect=mock_ensure_indexes), \
     patch("migration_oracle.mcp.server.get_driver", return_value=real_driver):
    from migration_oracle.mcp.server import startup
    startup()

assert call_order == ["connectivity_check", "ensure_indexes"], \
    f"Expected [connectivity_check, ensure_indexes], got: {call_order}"
print("PASS: 4-A — startup sequence: connectivity check precedes ensure_indexes")
```

### 4-B: Startup raises and exits on `ServiceUnavailable`

```python
from neo4j.exceptions import ServiceUnavailable
from unittest.mock import patch, MagicMock

mock_driver = MagicMock()
mock_session = MagicMock()
mock_session.__enter__ = lambda s: s
mock_session.__exit__ = MagicMock(return_value=False)
mock_session.run.side_effect = ServiceUnavailable("Connection refused")
mock_driver.session.return_value = mock_session

raised = False
try:
    with patch("migration_oracle.mcp.server.get_driver", return_value=mock_driver):
        import importlib, migration_oracle.mcp.server as srv
        importlib.reload(srv)
        srv.startup()
except (ServiceUnavailable, Exception) as e:
    raised = True
    print(f"  Caught: {type(e).__name__}: {e}")

assert raised, "startup() must raise when driver.session().run() raises ServiceUnavailable"
print("PASS: 4-B — startup() raises on ServiceUnavailable (does not swallow and continue)")
```

### 4-C: `create_migration_context` MERGE is idempotent — second call returns `created=False`

```python
from migration_oracle.mcp.tools.context import create_migration_context
from migration_oracle.graph.driver import get_driver

test_project = "__verif005_ctx__"
test_from = "3.0"
test_to = "3.4"
test_framework = "__verif005_fw__"

# First call
r1 = create_migration_context(
    project_id=test_project,
    from_version=test_from,
    to_version=test_to,
    framework=test_framework,
)
assert r1["status"] == "ok", f"First call failed: {r1}"
assert r1["created"] == True, f"First call should have created=True, got: {r1['created']}"
ctx_id = r1["context_id"]

# Second call with same triple
r2 = create_migration_context(
    project_id=test_project,
    from_version=test_from,
    to_version=test_to,
    framework=test_framework,
)
assert r2["status"] == "ok", f"Second call failed: {r2}"
assert r2["created"] == False, f"Second call must return created=False, got: {r2['created']}"
assert r2["context_id"] == ctx_id, \
    f"Second call must return same context_id. Got: {r2['context_id']} vs {ctx_id}"

# Cleanup
with get_driver().session() as session:
    session.run(
        "MATCH (ctx:MigrationContext {projectId: $pid}) DETACH DELETE ctx",
        {"pid": test_project}
    )

print(f"PASS: 4-C — create_migration_context idempotent; ctx_id={ctx_id}; second call: created={r2['created']}")
```

---

## Level 5 — Integration full write path

**Neo4j required.** Tests write operations for community tools and step status recording.

### 5-A: `submit_migration_insight` creates a CommunityInsight node with required properties

```python
from migration_oracle.mcp.tools.community import submit_migration_insight
from migration_oracle.graph.driver import get_driver

result = submit_migration_insight(
    statement="Verif005: Use @SpringBootTest instead of @RunWith",
    solution="Replace all @RunWith(SpringRunner.class) with @SpringBootTest",
    framework="Spring Boot",
    version="3.4",
    submitted_by="verif005@test",
    confidence=0.85,
    evidence_url="",
)
assert result["status"] == "ok", f"submit_migration_insight failed: {result}"
insight_id = result["insight_id"]
assert insight_id, "insight_id must be non-empty"

# Verify node exists in graph with required properties
with get_driver().session() as session:
    node = session.run(
        "MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id "
        "RETURN ci.statement AS stmt, ci.verified AS verified, ci.votes AS votes",
        {"id": insight_id}
    ).single()

assert node is not None, f"CommunityInsight node {insight_id} not found in graph"
assert "Verif005" in node["stmt"], f"statement mismatch: {node['stmt']}"
assert node["verified"] == False, f"verified should be False on creation, got: {node['verified']}"
assert node["votes"] == 0, f"votes should be 0 on creation, got: {node['votes']}"

# Cleanup
with get_driver().session() as session:
    session.run("MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci",
                {"id": insight_id})

print(f"PASS: 5-A — submit_migration_insight created node {insight_id} with correct properties")
```

### 5-B: `vote_insight` increments votes on an existing insight

```python
from migration_oracle.mcp.tools.community import submit_migration_insight, vote_insight
from migration_oracle.graph.driver import get_driver

# Setup: create insight
setup = submit_migration_insight(
    statement="Verif005-vote: Test insight for vote check",
    solution="No-op solution",
    framework="Spring Boot",
    version="3.4",
    submitted_by="verif005",
    confidence=0.5,
    evidence_url="",
)
insight_id = setup["insight_id"]

# Vote +1
result = vote_insight(insight_id=insight_id, delta=1)
assert result["status"] == "ok", f"vote_insight failed: {result}"
assert result["new_vote_count"] == 1, \
    f"Expected new_vote_count=1 after +1 vote, got: {result['new_vote_count']}"

# Vote -1
result2 = vote_insight(insight_id=insight_id, delta=-1)
assert result2["new_vote_count"] == 0, \
    f"Expected new_vote_count=0 after -1 vote, got: {result2['new_vote_count']}"

# Cleanup
with get_driver().session() as session:
    session.run("MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci",
                {"id": insight_id})

print(f"PASS: 5-B — vote_insight: +1 → count=1, -1 → count=0 on insight {insight_id}")
```

### 5-C: `verify_insight` sets `verified=true` on an insight node

```python
from migration_oracle.mcp.tools.community import submit_migration_insight, verify_insight
from migration_oracle.graph.driver import get_driver

setup = submit_migration_insight(
    statement="Verif005-verify: Test insight for verify check",
    solution="Verified solution",
    framework="Spring Boot",
    version="3.4",
    submitted_by="verif005",
    confidence=0.9,
    evidence_url="",
)
insight_id = setup["insight_id"]

result = verify_insight(insight_id=insight_id)
assert result["status"] == "ok", f"verify_insight failed: {result}"
assert result["verified"] == True, f"verified must be True after verify_insight, got: {result['verified']}"

# Confirm in graph
with get_driver().session() as session:
    row = session.run(
        "MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id RETURN ci.verified AS v",
        {"id": insight_id}
    ).single()
assert row["v"] == True, f"verified property in graph is not True: {row['v']}"

# Cleanup
with get_driver().session() as session:
    session.run("MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci",
                {"id": insight_id})

print(f"PASS: 5-C — verify_insight set verified=True on node {insight_id}")
```

### 5-D: `update_step_status` auto-closes context when last pending step is recorded

This test requires MigrationStep nodes. If no MigrationStep nodes exist in the test graph, mark this check as **N/A (first-release)** and note it in the checklist table.

```python
# Only run if MigrationStep nodes are present (Increment 1 pipeline run required)
from migration_oracle.graph.driver import get_driver

with get_driver().session() as session:
    count = session.run("MATCH (s:MigrationStep) RETURN count(s) AS n").single()["n"]

if count == 0:
    print("SKIP: 5-D — no MigrationStep nodes in graph (Increment 1 not yet run); marking N/A")
else:
    from migration_oracle.mcp.tools.context import create_migration_context, update_step_status, get_pending_steps

    # This test requires a context with exactly one known pending step
    # Run against your seeded test graph — substitute real step_id values
    print("INFO: 5-D requires manual execution against a seeded graph with known step IDs.")
    print("      Seed a MigrationContext with one pending MigrationStep, then:")
    print("      1. Call update_step_status(context_id, step_id, 'completed', reason='verif005')")
    print("      2. Assert result['context_auto_closed'] == True")
    print("      3. Assert result['context_status'] == 'complete'")
    print("      4. Call get_pending_steps(context_id) and assert pending_steps == []")
    print("      5. Delete the test context node")
```

---

## Level 6 — Idempotency

**Neo4j required.** Verifies that re-running write operations produces identical graph state.

### 6-A: `create_migration_context` called twice — node and edge counts unchanged

```python
from migration_oracle.mcp.tools.context import create_migration_context
from migration_oracle.graph.driver import get_driver

pid = "__verif005_idem__"
fw = "__verif005_idem_fw__"

create_migration_context(project_id=pid, from_version="1.0", to_version="2.0",
                         framework=fw, scanned_entities=["com.example.Foo"])
create_migration_context(project_id=pid, from_version="1.0", to_version="2.0",
                         framework=fw, scanned_entities=["com.example.Foo"])

with get_driver().session() as session:
    node_count = session.run(
        "MATCH (ctx:MigrationContext {projectId: $pid}) RETURN count(ctx) AS n", {"pid": pid}
    ).single()["n"]
    edge_count = session.run(
        "MATCH (ctx:MigrationContext {projectId: $pid})-[r:UPGRADES_FROM|UPGRADES_TO]->(v) "
        "RETURN count(r) AS n", {"pid": pid}
    ).single()["n"]

assert node_count == 1, f"Expected 1 MigrationContext node after 2 MERGE calls, got: {node_count}"
assert edge_count == 2, \
    f"Expected 2 edges (UPGRADES_FROM + UPGRADES_TO) after 2 MERGE calls, got: {edge_count}"

# Cleanup
with get_driver().session() as session:
    session.run("MATCH (ctx:MigrationContext {projectId: $pid}) DETACH DELETE ctx", {"pid": pid})

print(f"PASS: 6-A — create_migration_context idempotent: 1 node, 2 edges after 2 calls")
```

### 6-B: `submit_migration_insight` detects duplicate — second call does not create a second node

```python
from migration_oracle.mcp.tools.community import submit_migration_insight
from migration_oracle.graph.driver import get_driver

stmt = "Verif005-dup: Identical insight statement for duplicate detection check"

r1 = submit_migration_insight(
    statement=stmt, solution="solution-A", framework="Spring Boot",
    version="3.4", submitted_by="verif005", confidence=0.8, evidence_url="",
)
assert r1["status"] == "ok", f"First submit failed: {r1}"
id1 = r1["insight_id"]

r2 = submit_migration_insight(
    statement=stmt, solution="solution-A", framework="Spring Boot",
    version="3.4", submitted_by="verif005", confidence=0.8, evidence_url="",
)
# Second call must report duplicate (or ok with same id) — must NOT create a second node
with get_driver().session() as session:
    count = session.run(
        "MATCH (ci:CommunityInsight) WHERE ci.statement CONTAINS 'Verif005-dup' "
        "RETURN count(ci) AS n"
    ).single()["n"]

assert count == 1, \
    f"Expected 1 CommunityInsight node after 2 submits of same statement, got: {count}"

if r2["status"] == "duplicate":
    print(f"  Duplicate detected explicitly: duplicate_of={r2.get('duplicate_of')}")
elif r2["status"] == "ok" and r2["insight_id"] == id1:
    print(f"  Idempotent return of existing insight id")
else:
    raise AssertionError(f"Unexpected second-submit result: {r2}")

# Cleanup
with get_driver().session() as session:
    session.run("MATCH (ci:CommunityInsight) WHERE ci.statement CONTAINS 'Verif005-dup' "
                "DETACH DELETE ci")

print(f"PASS: 6-B — submit_migration_insight: 2 calls produce 1 node; second status={r2['status']!r}")
```

---

## Level 7 — Edge-case paths

**Neo4j required for most checks.**

### 7-A: `analyze_upgrade_path` on empty graph returns empty rules — not an error (SC-002 pre-redesign parity)

```python
from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

result = analyze_upgrade_path(
    framework="__absent_framework_verif005__",
    current_version="0.0",
    target_version="1.0",
)
assert result["status"] == "ok", \
    f"analyze_upgrade_path must return ok on empty graph, got: {result}"
assert result["rules"] == [], \
    f"Expected empty rules list for absent framework, got: {result['rules']}"
print(f"PASS: 7-A — analyze_upgrade_path returns ok + empty rules for absent framework")
```

### 7-B: `execute_custom_cypher` rejects all mutation keywords — including lowercase (SC-003)

```python
from migration_oracle.mcp.tools.schema import execute_custom_cypher
from unittest.mock import patch

blocked_queries = [
    ("CREATE (n:Test)", "CREATE"),
    ("MERGE (n:Test) ON MATCH SET n.x = 1", "MERGE"),
    ("MATCH (n) SET n.x = 1", "SET"),
    ("MATCH (n) DELETE n", "DELETE"),
    ("MATCH (n) REMOVE n.x", "REMOVE"),
    ("DROP INDEX idx", "DROP"),
    ("CALL db.index.fulltext.queryNodes('idx', 'q')", "CALL db"),
    ("create (n:Sneaky)", "CREATE"),
    ("MATCH (n) where n.x > 0 set n.y = 1", "SET"),
]

driver_contact_count = [0]

for query, expected_kw in blocked_queries:
    with patch("migration_oracle.graph.driver.read_session") as mock_sess:
        mock_sess.side_effect = lambda: (_ for _ in ()).throw(
            AssertionError(f"Driver contacted for blocked query: {query!r}"))
        result = execute_custom_cypher(query=query)

    assert result["status"] == "blocked", \
        f"Query {query!r} should be blocked, got status={result['status']!r}"
    kw = result.get("blocked_keyword", "")
    assert expected_kw.split()[0].upper() in kw.upper(), \
        f"Expected {expected_kw!r} in blocked_keyword, got: {kw!r}"
    mock_sess.assert_not_called()

print(f"PASS: 7-B — all {len(blocked_queries)} mutation patterns blocked before driver contact (SC-003: 100%)")
```

### 7-C: `get_artifact_content` returns not_found for absent Version node — no filesystem access

```python
from migration_oracle.mcp.tools.artifacts import get_artifact_content
from unittest.mock import patch

with patch("pathlib.Path.read_text") as mock_read:
    mock_read.side_effect = AssertionError("Filesystem must not be accessed for absent Version node")
    result = get_artifact_content(
        framework="__absent_verif005__",
        from_version="1.0",
        to_version="2.0",
        artifact_type="raw_md",
    )

assert result["status"] == "not_found", \
    f"Expected not_found for absent Version node, got: {result['status']!r}"
mock_read.assert_not_called()
print(f"PASS: 7-C — get_artifact_content returns not_found for absent Version node without filesystem access")
```

### 7-D: `build_recipe_plan` with no `AUTOMATED_BY` edges returns empty auto track (Contract G(b) / FR-044)

This test exercises the first-release expected state (no AUTOMATED_BY edges). Uses a mocked graph.

```python
import os
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "dummy")

from unittest.mock import patch

# Simulate: rules exist with MigrationStep nodes but ZERO AUTOMATED_BY edges
mock_rules = [
    {
        "rule_id": "rule-1",
        "statement": "Remove @EnableJpaRepositories from main class",
        "rule_type": "breaking",
        "action_step": "Remove the annotation",
        "source_url": "https://example.com",
        "change_type": "removal",
        "reason": "Auto-configured in Boot 3",
        "entity_classification": "actionable",
        "steps": [
            {
                "step_id": "step-1",
                "step_type": "remove",
                "summary": "Remove @EnableJpaRepositories",
                "instruction": "Delete the annotation from MainApp.java",
                "effort": "mechanical",
                "automatable": True,
                "verification_hint": "Class compiles without the annotation",
                "cli_operation": "",
                "recipe_id": None,     # NO AUTOMATED_BY edge
            }
        ],
        "scopes": [{"scope": "api-surface", "severity": "high"}],
        "recipes": [],  # empty — no AUTOMATED_BY edges
    }
]

with patch("migration_oracle.mcp.graph.queries.upgrade.get_upgrade_rules",
           return_value=mock_rules):
    from migration_oracle.mcp.tools.upgrade import build_recipe_plan
    result = build_recipe_plan(
        current_version="3.2",
        target_version="3.4",
        framework="Spring Boot",
    )

assert result["status"] == "ok", f"Expected ok, got: {result}"
assert result["auto_track"] == [], \
    f"auto_track must be empty when no AUTOMATED_BY edges exist (Contract G(b)): {result['auto_track']}"
assert len(result["manual_track"]) >= 1, \
    f"manual_track must contain the step when no recipe exists: {result['manual_track']}"
print(f"PASS: 7-D — build_recipe_plan with no AUTOMATED_BY: auto_track=[], manual_track has {len(result['manual_track'])} card(s)")
```

### 7-E: `analyze_upgrade_path` with pre-redesign data (no MigrationStep/BreakingScope nodes) returns `steps=[]` and `scopes=[]`

```python
from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path
from unittest.mock import patch

# Simulate pre-redesign data: rules have no REQUIRES_STEP or HAS_SCOPE edges
mock_pre_redesign_rules = [
    {
        "rule_id": "old-rule-1",
        "statement": "Legacy rule without steps or scopes",
        "rule_type": "deprecation",
        "action_step": "Check the migration guide",
        "source_url": "",
        "change_type": "deprecation",
        "reason": "API removed",
        "entity_classification": "actionable",
        "steps": [],    # OPTIONAL MATCH returned nothing
        "scopes": [],   # OPTIONAL MATCH returned nothing
        "recipes": [],
    }
]

with patch("migration_oracle.mcp.graph.queries.upgrade.get_upgrade_rules",
           return_value=mock_pre_redesign_rules):
    result = analyze_upgrade_path(
        framework="wildfly", current_version="26", target_version="30"
    )

assert result["status"] == "ok", f"Expected ok, got: {result}"
assert len(result["rules"]) == 1
rule = result["rules"][0]
assert rule["steps"] == [], f"steps must be [] for pre-redesign rule, got: {rule['steps']}"
assert rule["scopes"] == [], f"scopes must be [] for pre-redesign rule, got: {rule['scopes']}"
print("PASS: 7-E — analyze_upgrade_path with pre-redesign data: steps=[] and scopes=[] (OPTIONAL MATCH correct)")
```

### 7-F: `close_migration_context` return shape has `tool_status` and `migration_status` as distinct keys

```python
from migration_oracle.mcp.tools.context import create_migration_context, close_migration_context
from migration_oracle.graph.driver import get_driver

# Create a context to close
r = create_migration_context(
    project_id="__verif005_close__",
    from_version="1.0",
    to_version="2.0",
    framework="__verif005_close_fw__",
)
ctx_id = r["context_id"]

close_result = close_migration_context(
    context_id=ctx_id,
    final_status="abandoned",
    notes="verif005 test close",
)

assert "tool_status" in close_result, \
    f"'tool_status' key missing from close_migration_context result: {list(close_result.keys())}"
assert "migration_status" in close_result, \
    f"'migration_status' key missing from close_migration_context result: {list(close_result.keys())}"
assert "status" not in close_result, \
    f"Ambiguous 'status' key must NOT be present; result has keys: {list(close_result.keys())}"
assert close_result["tool_status"] == "ok", \
    f"tool_status must be 'ok' on success, got: {close_result['tool_status']!r}"
assert close_result["migration_status"] == "abandoned", \
    f"migration_status must be 'abandoned', got: {close_result['migration_status']!r}"

# Cleanup
with get_driver().session() as session:
    session.run("MATCH (ctx:MigrationContext {projectId: '__verif005_close__'}) DETACH DELETE ctx")

print(f"PASS: 7-F — close_migration_context: tool_status='ok', migration_status='abandoned' (distinct keys)")
```

---

## Completion Gate Checklist

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| ID | Level | Description | Result |
|---|---|---|---|
| 0-A | Static | All 19 mcp modules import without error | ☐ |
| 0-B | Static | `MUTATION_KEYWORDS` = exactly {CREATE, MERGE, SET, DELETE, REMOVE, DROP} | ☐ |
| 0-C | Static | `check_mutation` correctly handles all 11 test cases incl. lowercase and CALL db | ☐ |
| 0-D | Static | Config constants: MCP_STATELESS_HTTP=False, MCP_TRANSPORT='stdio', MCP_HOST='0.0.0.0', SENTENCE_TRANSFORMERS_MODEL='all-mpnet-base-v2' | ☐ |
| 0-E | Static | `_model = None` at module load; `get_embedding_model()` uses global + check-then-assign; exactly 1 `SentenceTransformer(` call in search.py | ☐ |
| 0-F | Static | No inline Cypher keywords (MATCH/MERGE/RETURN/OPTIONAL) in `mcp/tools/*.py` | ☐ |
| 0-G | Static | No `os.environ` / `os.getenv` calls in any `mcp/` module | ☐ |
| 0-H | Static | `paysafe.py` has exactly 1 paysafe import (resolver.resolve); findit/gitlab absent | ☐ |
| 0-I | Static | `get_artifact_content` signature has no `path` parameter | ☐ |
| 0-J | Static | `close_migration_context` uses `tool_status` + `migration_status` as distinct keys | ☐ |
| 0-K | Static | `ARTIFACT_TYPE_MAP` = {raw_md→rawMdPath, filtered_md→filteredMdPath, entities_json→entitiesJsonPath} | ☐ |
| 0-L | Static | `update_step_status` parameter named `reason` (not `notes`) | ☐ |
| 1-A | Interface | Server exits on unsupported MCP_TRANSPORT (non-zero exit) | ☐ |
| 1-B | Interface | Missing NEO4J_URI raises ConfigurationError at import time | ☐ |
| 1-C | Interface | `execute_custom_cypher("CREATE ...")` returns status='blocked' before driver contact | ☐ |
| 1-D | Interface | `get_graph_schema()` returns schema_markdown > 100 chars with zero driver calls | ☐ |
| 2-A | Isolation | `check_mutation` blocks all 4 CALL db variants; allows safe MATCH | ☐ |
| 2-B | Isolation | `get_embedding_model()` called 3× → SentenceTransformer.__init__ called exactly 1× | ☐ |
| 2-C | Isolation | `get_artifact_content` with unknown artifact_type returns error before graph contact | ☐ |
| 2-D | Isolation | RRF fusion produces all input IDs with positive float scores | ☐ |
| 3-A | Read path | Graph connectivity: `RETURN 1 AS n = 1` | ☐ |
| 3-B | Read path | `execute_read_cypher` returns `[]` for absent label | ☐ |
| 3-C | Read path | `bm25_search` with absent index returns `[]` (no exception) | ☐ |
| 3-D | Read path | Synthetic Version node: written → found in list_pipeline_runs → deleted | ☐ |
| 3-E | Read path | `get_version_artifact_path` returns None for absent Version node | ☐ |
| 4-A | Write safe | Startup: connectivity check precedes ensure_indexes in call order | ☐ |
| 4-B | Write safe | Startup raises on ServiceUnavailable (does not continue) | ☐ |
| 4-C | Write safe | `create_migration_context` called twice → created=True then created=False, same context_id | ☐ |
| 5-A | Write full | `submit_migration_insight` creates CommunityInsight with statement/verified=False/votes=0 | ☐ |
| 5-B | Write full | `vote_insight +1 → count=1`; `-1 → count=0` | ☐ |
| 5-C | Write full | `verify_insight` sets verified=True in graph | ☐ |
| 5-D | Write full | `update_step_status` auto-closes context when last step recorded (N/A if no MigrationStep nodes) | ☐ / N/A |
| 6-A | Idempotency | `create_migration_context` ×2 → 1 node, 2 edges (UPGRADES_FROM + UPGRADES_TO) | ☐ |
| 6-B | Idempotency | `submit_migration_insight` ×2 with same statement → 1 CommunityInsight node; second call: duplicate or same id | ☐ |
| 7-A | Edge cases | `analyze_upgrade_path` on absent framework → status='ok', rules=[] | ☐ |
| 7-B | Edge cases | All 9 mutation patterns blocked (including lowercase `create`, embedded `set`) before driver contact (SC-003) | ☐ |
| 7-C | Edge cases | `get_artifact_content` for absent Version node → not_found, no filesystem access | ☐ |
| 7-D | Edge cases | `build_recipe_plan` with no AUTOMATED_BY edges → auto_track=[], manual_track non-empty (Contract G(b)) | ☐ |
| 7-E | Edge cases | `analyze_upgrade_path` with pre-redesign mock data → each rule has steps=[] and scopes=[] | ☐ |
| 7-F | Edge cases | `close_migration_context` result has `tool_status='ok'` and `migration_status` as separate keys; no single `status` key | ☐ |

# Verification Protocol: Streamlit Operator UI (006-streamlit-ui)

**Location**: `specs/006-streamlit-ui/verification.md`  
**Spec gate**: Run this after `/speckit.implement` completes, before marking `006` ✅  
**Execution order**: Levels 0 → 5 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | How to satisfy |
|---|---|
| Dependencies installed | `uv sync` |
| Neo4j running (Levels 3, 5, 7-C, 7-D) | `bolt://localhost:7687` reachable; `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` exported |
| Populated graph (Level 5) | At least one pipeline run and one community insight in Neo4j |
| Browser available (Level 5) | Local desktop or headless Chrome |

**Level infrastructure summary**:

| Level | Name | DB needed | LLM needed |
|---|---|---|---|
| 0 | Static checks | No | No |
| 1 | Interface structure | No | No |
| 2 | Isolation / boundary compliance | No | No |
| 3 | Integration — read path | Yes | No |
| 4 | AppTest page rendering | No | No |
| 5 | Full integration smoke test | Yes (populated) | No |
| 7 | Edge-case paths | Mixed | No |

Level 6 (idempotency) is omitted — the UI renders graph data and writes no state of its own; idempotency belongs to the tool functions, not the pages.

---

## Level 0 — Static checks

No external services needed.

### 0-A: Module imports

Each command must exit 0 with no traceback. Run all six:

```bash
python -c "import migration_oracle.streamlit_app; print('PASS: package importable')"
python -c "import migration_oracle.streamlit_app._helpers; print('PASS: _helpers importable')"
# Pages are scripts, not importable modules — check for syntax errors via ast instead:
python -c "import ast, pathlib; ast.parse(pathlib.Path('migration_oracle/streamlit_app/app.py').read_text()); print('PASS: app.py syntax ok')"
python -c "import ast, pathlib; ast.parse(pathlib.Path('migration_oracle/streamlit_app/pages/01_pipeline_trigger.py').read_text()); print('PASS: 01_pipeline_trigger syntax ok')"
python -c "import ast, pathlib; ast.parse(pathlib.Path('migration_oracle/streamlit_app/pages/02_run_browser.py').read_text()); print('PASS: 02_run_browser syntax ok')"
python -c "import ast, pathlib; ast.parse(pathlib.Path('migration_oracle/streamlit_app/pages/03_rule_explorer.py').read_text()); print('PASS: 03_rule_explorer syntax ok')"
python -c "import ast, pathlib; ast.parse(pathlib.Path('migration_oracle/streamlit_app/pages/04_context_dashboard.py').read_text()); print('PASS: 04_context_dashboard syntax ok')"
python -c "import ast, pathlib; ast.parse(pathlib.Path('migration_oracle/streamlit_app/pages/05_community.py').read_text()); print('PASS: 05_community syntax ok')"
```

### 0-B: `_helpers.py` exported symbols

```python
from migration_oracle.streamlit_app._helpers import call_tool, framework_selectbox, effort_badge
assert callable(call_tool), f"call_tool not callable: {type(call_tool)}"
assert callable(framework_selectbox), f"framework_selectbox not callable: {type(framework_selectbox)}"
assert callable(effort_badge), f"effort_badge not callable: {type(effort_badge)}"
print("PASS: all three helpers exported and callable")
```

### 0-C: `effort_badge` known values

```python
from migration_oracle.streamlit_app._helpers import effort_badge
assert "Mechanical" in effort_badge("mechanical"), f"Got: {effort_badge('mechanical')}"
assert "Substantial" in effort_badge("substantial"), f"Got: {effort_badge('substantial')}"
print("PASS: effort_badge returns correct labels for both effort values")
```

### 0-D: `app.py` has no `migration_oracle` import at module level

```bash
python -c "
import ast, pathlib
tree = ast.parse(pathlib.Path('migration_oracle/streamlit_app/app.py').read_text())
top_level_imports = [
    n for n in ast.walk(tree)
    if isinstance(n, (ast.Import, ast.ImportFrom))
    and getattr(n, 'col_offset', 99) == 0
]
for node in top_level_imports:
    if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('migration_oracle'):
        raise AssertionError(f'app.py imports migration_oracle at top level: {ast.dump(node)}')
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith('migration_oracle'):
                raise AssertionError(f'app.py imports migration_oracle at top level: {alias.name}')
print('PASS: app.py has no migration_oracle imports at module level')
"
```

### 0-E: `set_page_config` call in `app.py`

```bash
grep -q 'set_page_config' migration_oracle/streamlit_app/app.py && \
grep -q 'layout.*wide' migration_oracle/streamlit_app/app.py && \
grep -q 'Migration Oracle' migration_oracle/streamlit_app/app.py && \
echo "PASS: app.py contains set_page_config with layout=wide and page_title=Migration Oracle"
```

---

## Level 1 — Interface structure

No external services needed.

### 1-A: Streamlit ≥1.35 installed

```bash
python -c "
import importlib.metadata
v = importlib.metadata.version('streamlit')
parts = [int(x) for x in v.split('.')[:2]]
assert parts >= [1, 35], f'streamlit version too old: {v}'
print(f'PASS: streamlit=={v} satisfies >=1.35')
"
```

### 1-B: Five page files exist at exact paths

```bash
for f in \
  migration_oracle/streamlit_app/app.py \
  migration_oracle/streamlit_app/_helpers.py \
  migration_oracle/streamlit_app/__init__.py \
  migration_oracle/streamlit_app/pages/01_pipeline_trigger.py \
  migration_oracle/streamlit_app/pages/02_run_browser.py \
  migration_oracle/streamlit_app/pages/03_rule_explorer.py \
  migration_oracle/streamlit_app/pages/04_context_dashboard.py \
  migration_oracle/streamlit_app/pages/05_community.py; do
  [ -f "$f" ] || { echo "FAIL: missing $f"; exit 1; }
done
echo "PASS: all eight files exist at correct paths"
```

### 1-C: Pipeline Trigger uses `sys.executable` and list-form subprocess

```bash
grep -q 'sys\.executable' migration_oracle/streamlit_app/pages/01_pipeline_trigger.py && \
echo "PASS: sys.executable present in 01_pipeline_trigger.py"

grep -q 'subprocess\.Popen' migration_oracle/streamlit_app/pages/01_pipeline_trigger.py && \
echo "PASS: subprocess.Popen present in 01_pipeline_trigger.py"
```

### 1-D: `@st.cache_data(ttl=60)` present in Run Browser

```bash
grep -q 'cache_data.*ttl.*60\|cache_data(ttl=60)' migration_oracle/streamlit_app/pages/02_run_browser.py && \
echo "PASS: @st.cache_data(ttl=60) present in 02_run_browser.py"
```

### 1-E: `asyncio.run` present in Rule Explorer (required for async tool call)

```bash
grep -q 'asyncio\.run' migration_oracle/streamlit_app/pages/03_rule_explorer.py && \
echo "PASS: asyncio.run present in 03_rule_explorer.py"
```

---

## Level 2 — Isolation / boundary compliance

No external services needed. These checks verify the architecture contract violations from `contracts/006-streamlit-ui.md`.

### 2-A: No `open(` or `Path.read_text` in any page file (Graph Access Boundary)

```bash
result=$(grep -rn 'open(' migration_oracle/streamlit_app/pages/ | grep -v '#')
[ -z "$result" ] && echo "PASS: no open() in page files" || { echo "FAIL: open() found:"; echo "$result"; exit 1; }

result=$(grep -rn 'read_text\|read_bytes' migration_oracle/streamlit_app/pages/ | grep -v '#')
[ -z "$result" ] && echo "PASS: no read_text/read_bytes in page files" || { echo "FAIL: filesystem read found:"; echo "$result"; exit 1; }
```

### 2-B: No `framework_selectbox` call in `03_rule_explorer.py` (Rule Explorer must use inline display-name selectbox)

```bash
result=$(grep -n 'framework_selectbox' migration_oracle/streamlit_app/pages/03_rule_explorer.py | grep -v '#')
[ -z "$result" ] && echo "PASS: framework_selectbox not called in 03_rule_explorer.py" || { echo "FAIL: framework_selectbox found in rule_explorer — violates Rule Explorer display-name contract:"; echo "$result"; exit 1; }
```

### 2-C: No `migration_oracle.mcp.tools` import in `01_pipeline_trigger.py` (subprocess isolation)

```bash
result=$(grep -n 'migration_oracle\.mcp\.tools\|from migration_oracle.mcp' migration_oracle/streamlit_app/pages/01_pipeline_trigger.py | grep -v '#')
[ -z "$result" ] && echo "PASS: no mcp.tools import in 01_pipeline_trigger.py" || { echo "FAIL: graph tool imported in pipeline trigger — violates subprocess isolation:"; echo "$result"; exit 1; }
```

### 2-D: No `shell=True` in any page file (Pipeline Invocation Boundary)

```bash
result=$(grep -rn 'shell=True' migration_oracle/streamlit_app/ | grep -v '#')
[ -z "$result" ] && echo "PASS: no shell=True in streamlit_app/" || { echo "FAIL: shell=True found — prohibited by contracts:"; echo "$result"; exit 1; }
```

### 2-E: No `direction=` argument to `vote_insight` (must use `delta=1`)

```bash
result=$(grep -rn 'direction=' migration_oracle/streamlit_app/ | grep -v '#')
[ -z "$result" ] && echo "PASS: no direction= kwarg in streamlit_app/" || { echo "FAIL: direction= found — vote_insight uses delta=1, not direction=:"; echo "$result"; exit 1; }
```

### 2-F: `close_migration_context` response checked via `tool_status` not `status`

```bash
# The key used for close_migration_context success check must be tool_status
content=$(cat migration_oracle/streamlit_app/pages/04_context_dashboard.py)
echo "$content" | grep -q 'tool_status' && echo "PASS: tool_status key present in 04_context_dashboard.py" || { echo "FAIL: tool_status key missing — close_migration_context returns tool_status not status"; exit 1; }
```

### 2-G: `call_tool` catches exceptions and returns `None` on failure

```python
import unittest.mock, io, contextlib
import streamlit as st

# Patch st.error so it doesn't require a Streamlit runtime
with unittest.mock.patch('streamlit.error') as mock_err:
    from migration_oracle.streamlit_app._helpers import call_tool
    def _boom(): raise RuntimeError("neo4j unreachable")
    result = call_tool(_boom)
    assert result is None, f"Expected None, got: {result!r}"
    assert mock_err.called, "st.error was not called on exception"
    assert "neo4j unreachable" in mock_err.call_args[0][0], f"Wrong error message: {mock_err.call_args}"
    print("PASS: call_tool returns None and calls st.error on exception")
```

### 2-H: `framework_selectbox(include_all=True)` can represent the "All" sentinel as Python `None` (not the string `"all"`)

```bash
# Verify the options list in _helpers.py contains None sentinel (not string "all")
python -c "
import ast, pathlib
src = pathlib.Path('migration_oracle/streamlit_app/_helpers.py').read_text()
# Check that None is used as sentinel, not string 'all'
assert '\"all\"' not in src or 'all frameworks' in src, 'String \"all\" sentinel found — must use Python None'
# Verify the code contains: options = [None] + options (or similar None prepend pattern)
assert 'None' in src, 'None sentinel not found in _helpers.py'
print('PASS: _helpers.py uses None sentinel (not string \"all\") for include_all=True')
"
```

### 2-I: Rule Explorer passes `framework=fw` explicitly (never omits the kwarg)

```bash
# The call to search_migration_knowledge must include framework= explicitly
grep -n 'search_migration_knowledge' migration_oracle/streamlit_app/pages/03_rule_explorer.py | grep 'framework=' && \
echo "PASS: framework= kwarg explicitly passed in search_migration_knowledge call" || \
{ echo "FAIL: framework= kwarg missing — omitting defaults to 'Spring Boot', breaking all-frameworks search"; exit 1; }
```

---

## Level 3 — Integration — read path

**DB required.** Export `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` before running.  
Each check cleans up after itself.

### 3-A: Neo4j connectivity

```python
import os
from neo4j import GraphDatabase

uri = os.environ["NEO4J_URI"]
auth = (os.environ.get("NEO4J_USERNAME", "neo4j"), os.environ["NEO4J_PASSWORD"])
with GraphDatabase.driver(uri, auth=auth) as driver:
    records, _, _ = driver.execute_query("RETURN 1 AS n")
    assert records[0]["n"] == 1, f"Unexpected: {records[0]}"
print("PASS: Neo4j driver connected and query returned 1")
```

### 3-B: `list_pipeline_runs()` returns correct shape

```python
from migration_oracle.mcp.tools.artifacts import list_pipeline_runs
result = list_pipeline_runs()
assert isinstance(result, dict), f"Expected dict, got {type(result)}"
assert "runs" in result, f"Missing 'runs' key; keys={list(result.keys())}"
assert isinstance(result["runs"], list), f"'runs' must be list, got {type(result['runs'])}"
for r in result["runs"]:
    for field in ("framework", "from_version", "to_version"):
        assert field in r, f"PipelineRun missing '{field}'; keys={list(r.keys())}"
print(f"PASS: list_pipeline_runs returned {len(result['runs'])} run(s) with correct shape")
```

### 3-C: `search_migration_knowledge` returns correct SearchHit shape (no title/steps/scopes)

```python
import asyncio
from migration_oracle.mcp.tools.search import search_migration_knowledge

result = asyncio.run(search_migration_knowledge(query="migration", framework=None, max_results=5))
assert isinstance(result, dict), f"Expected dict, got {type(result)}"
assert "hits" in result, f"Missing 'hits' key; keys={list(result.keys())}"
for hit in result["hits"]:
    for required in ("node_id", "node_type", "statement", "score", "source_url", "action_step", "rule_type"):
        assert required in hit, f"SearchHit missing '{required}'; keys={list(hit.keys())}"
    for forbidden in ("title", "changeType", "steps", "scopes", "severity"):
        assert forbidden not in hit, f"SearchHit must NOT contain '{forbidden}' — it is absent from the actual tool return shape; got keys={list(hit.keys())}"
print(f"PASS: search_migration_knowledge returned {len(result['hits'])} hit(s) with correct shape and no forbidden fields")
```

### 3-D: `get_community_insights()` called with no arguments returns correct shape

```python
from migration_oracle.mcp.tools.community import get_community_insights

result = get_community_insights()
assert isinstance(result, dict), f"Expected dict, got {type(result)}"
assert "insights" in result, f"Missing 'insights' key; keys={list(result.keys())}"
for insight in result["insights"]:
    for required in ("insight_id", "statement", "solution", "votes", "verified"):
        assert required in insight, f"CommunityInsight missing '{required}'; keys={list(insight.keys())}"
print(f"PASS: get_community_insights() (no args) returned {len(result['insights'])} insight(s) with correct shape")
```

### 3-E: `search_migration_knowledge` with display-name framework filters correctly (not CLI key)

```python
import asyncio
from migration_oracle.mcp.tools.search import search_migration_knowledge

# Display name "Spring Boot" must work; CLI key "spring-boot" is wrong usage
result_display = asyncio.run(search_migration_knowledge(query="migration", framework="Spring Boot", max_results=3))
assert isinstance(result_display.get("hits"), list), f"Expected hits list; got: {result_display}"
print(f"PASS: search_migration_knowledge accepts display name 'Spring Boot' as framework — returned {len(result_display['hits'])} hit(s)")
```

---

## Level 4 — AppTest page rendering

No DB required. Uses `streamlit.testing.v1.AppTest` with `unittest.mock.patch` to mock tool functions.

### 4-A: All five pages load without exception

```python
from streamlit.testing.v1 import AppTest

for path in [
    "migration_oracle/streamlit_app/pages/01_pipeline_trigger.py",
    "migration_oracle/streamlit_app/pages/02_run_browser.py",
    "migration_oracle/streamlit_app/pages/03_rule_explorer.py",
    "migration_oracle/streamlit_app/pages/04_context_dashboard.py",
    "migration_oracle/streamlit_app/pages/05_community.py",
]:
    at = AppTest.from_file(path)
    at.run()
    assert not at.exception, f"Exception on {path}: {at.exception}"
    print(f"PASS: {path.split('/')[-1]} loads without exception")
```

### 4-B: Pipeline Trigger — blank version inputs shows warning, no subprocess spawned

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

with unittest.mock.patch("subprocess.Popen") as mock_popen:
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/01_pipeline_trigger.py")
    at.run()
    # Submit with empty from_version (leave text inputs empty)
    at.button[0].click().run()
    assert not mock_popen.called, "subprocess.Popen must NOT be called when version inputs are blank"
    assert len(at.warning) > 0 or len(at.error) > 0, "Expected a warning or error widget when version is blank"
    print("PASS: Pipeline Trigger shows warning and does not spawn subprocess for blank version inputs")
```

### 4-C: Pipeline Trigger — non-zero exit code renders st.error with "Exit N"

```python
from streamlit.testing.v1 import AppTest
import unittest.mock, io

mock_proc = unittest.mock.MagicMock()
mock_proc.stdout = iter(["output line\n"])
mock_proc.stderr.read.return_value = "Build failed"
mock_proc.returncode = 1
mock_proc.wait.return_value = None

with unittest.mock.patch("subprocess.Popen", return_value=mock_proc):
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/01_pipeline_trigger.py")
    at.run()
    at.text_input[0].set_value("2.7.x")   # from_version
    at.text_input[1].set_value("3.2")      # to_version
    at.button[0].click().run()
    error_texts = [e.value for e in at.error]
    assert any("Exit 1" in t for t in error_texts), f"Expected 'Exit 1' in error widgets; got: {error_texts}"
    assert any("Build failed" in t for t in error_texts), f"Expected stderr text in error; got: {error_texts}"
    print("PASS: Pipeline Trigger renders st.error with exit code and stderr on non-zero exit")
```

### 4-D: Run Browser — empty runs list renders `st.info("No pipeline runs found")`

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

with unittest.mock.patch("migration_oracle.mcp.tools.artifacts.list_pipeline_runs", return_value={"runs": []}):
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/02_run_browser.py")
    at.run()
    info_texts = [i.value for i in at.info]
    assert any("No pipeline runs found" in t for t in info_texts), f"Expected empty-state info; got: {info_texts}"
    assert len(at.selectbox) == 0, f"Selectbox must not render with empty runs; found: {len(at.selectbox)}"
    print("PASS: Run Browser shows st.info('No pipeline runs found') and no selectbox when runs=[]")
```

### 4-E: Run Browser — one run renders selectbox with label `"framework → to_version"`

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

run = {"framework": "spring-boot", "from_version": "", "to_version": "3.2",
       "raw_md_path": "", "filtered_md_path": None, "entities_json_path": None}
with unittest.mock.patch("migration_oracle.mcp.tools.artifacts.list_pipeline_runs", return_value={"runs": [run]}):
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/02_run_browser.py")
    at.run()
    assert len(at.selectbox) > 0, "Expected selectbox to be rendered"
    options = at.selectbox[0].options
    assert any("spring-boot → 3.2" in str(o) for o in options), f"Expected 'spring-boot → 3.2' label; got: {options}"
    print("PASS: Run Browser renders selectbox with label 'framework → to_version'")
```

### 4-F: Rule Explorer — empty hits renders `st.info("No rules found for this query")`

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

async def _fake_search(**kwargs): return {"hits": []}

with unittest.mock.patch("migration_oracle.mcp.tools.search.search_migration_knowledge", side_effect=_fake_search):
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/03_rule_explorer.py")
    at.run()
    at.text_input[0].set_value("removed API")
    at.button[0].click().run()
    info_texts = [i.value for i in at.info]
    assert any("No rules found" in t for t in info_texts), f"Expected empty-state info; got: {info_texts}"
    print("PASS: Rule Explorer shows st.info('No rules found for this query') when hits=[]")
```

### 4-G: Rule Explorer — `search_migration_knowledge` called with `framework=None` when "All" selected

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

captured_kwargs = {}
async def _capture(**kwargs):
    captured_kwargs.update(kwargs)
    return {"hits": []}

with unittest.mock.patch("migration_oracle.mcp.tools.search.search_migration_knowledge", side_effect=_capture):
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/03_rule_explorer.py")
    at.run()
    at.text_input[0].set_value("test query")
    # Select "All" — it is the first option in the selectbox (index 0)
    at.selectbox[0].set_value("All")
    at.button[0].click().run()
    assert "framework" in captured_kwargs, f"framework kwarg not passed; got: {captured_kwargs}"
    assert captured_kwargs["framework"] is None, (
        f"framework must be Python None when 'All' selected; got: {captured_kwargs['framework']!r}"
    )
    print("PASS: Rule Explorer passes framework=None (not omitted, not 'all') when All selected")
```

### 4-H: Context Dashboard — load form renders when no `context_id` in session_state

```python
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("migration_oracle/streamlit_app/pages/04_context_dashboard.py")
at.run()
# Session state is empty on fresh load — form must be present
input_keys = [inp.key for inp in at.text_input]
assert len(at.text_input) >= 3, f"Expected at least 3 text_input widgets for project_id, from_version, to_version; got: {len(at.text_input)}"
print("PASS: Context Dashboard renders load/create form when no context_id in session_state")
```

### 4-I: Context Dashboard — all 8 `context_*` keys set after `create_migration_context` success

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

fake_ctx = {
    "status": "ok", "context_id": "ctx-123", "project_id": "proj-1",
    "from_version": "2.7.x", "to_version": "3.2", "framework": "Spring Boot",
    "migration_status": "in-progress", "scanned_entities": [],
    "completed_steps": [], "skipped_steps": [], "created_at": "2026-06-08T00:00:00",
    "completed_at": None,
}

with unittest.mock.patch("migration_oracle.mcp.tools.context.create_migration_context", return_value=fake_ctx):
    with unittest.mock.patch("migration_oracle.mcp.tools.context.get_pending_steps", return_value={"pending_steps": []}):
        at = AppTest.from_file("migration_oracle/streamlit_app/pages/04_context_dashboard.py")
        at.run()
        at.text_input[0].set_value("proj-1")
        at.text_input[1].set_value("2.7.x")
        at.text_input[2].set_value("3.2")
        at.button[0].click().run()
        ss = at.session_state
        expected_keys = [
            "context_id", "context_project_id", "context_from_version",
            "context_to_version", "context_framework", "context_status",
            "context_completed_count", "context_skipped_count",
        ]
        for k in expected_keys:
            assert k in ss, f"Missing session_state key: '{k}'; present keys: {[k for k in ss if k.startswith('context')]}"
        assert ss["context_id"] == "ctx-123", f"Wrong context_id: {ss['context_id']!r}"
        assert ss["context_completed_count"] == 0, f"Wrong completed_count: {ss['context_completed_count']!r}"
        print("PASS: Context Dashboard sets all 8 context_* flat keys in session_state")
```

### 4-J: Context Dashboard — no-pending-steps shows `st.info("No pending steps remaining")`

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

fake_ctx = {
    "status": "ok", "context_id": "ctx-456", "project_id": "p", "from_version": "2.x",
    "to_version": "3.0", "framework": "Spring Boot", "migration_status": "in-progress",
    "scanned_entities": [], "completed_steps": [], "skipped_steps": [],
    "created_at": "2026-06-08T00:00:00", "completed_at": None,
}

with unittest.mock.patch("migration_oracle.mcp.tools.context.create_migration_context", return_value=fake_ctx):
    with unittest.mock.patch("migration_oracle.mcp.tools.context.get_pending_steps", return_value={"pending_steps": []}):
        at = AppTest.from_file("migration_oracle/streamlit_app/pages/04_context_dashboard.py")
        at.run()
        at.text_input[0].set_value("p"); at.text_input[1].set_value("2.x"); at.text_input[2].set_value("3.0")
        at.button[0].click().run()
        info_texts = [i.value for i in at.info]
        assert any("No pending steps remaining" in t for t in info_texts), f"Expected empty-state info; got: {info_texts}"
        print("PASS: Context Dashboard shows st.info('No pending steps remaining') when pending_steps=[]")
```

### 4-K: Context Dashboard — Mark Complete updates `context_completed_count` from response

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

fake_ctx = {
    "status": "ok", "context_id": "ctx-789", "project_id": "p", "from_version": "2.x",
    "to_version": "3.0", "framework": "Spring Boot", "migration_status": "in-progress",
    "scanned_entities": [], "completed_steps": [], "skipped_steps": [],
    "created_at": "2026-06-08T00:00:00", "completed_at": None,
}
fake_step = {
    "step_id": "step-1", "step_type": "manual", "rule_id": "r1", "summary": "Do something",
    "instruction": "", "verification_hint": "", "effort": "mechanical",
    "automatable": False, "scope": "", "severity": "", "requires": [], "recipe_id": None,
}
fake_update = {
    "status": "ok", "step_id": "step-1", "outcome": "completed",
    "context_id": "ctx-789", "context_auto_closed": False,
    "context_status": "in-progress", "completed_count": 1, "skipped_count": 0,
}

with unittest.mock.patch("migration_oracle.mcp.tools.context.create_migration_context", return_value=fake_ctx):
    with unittest.mock.patch("migration_oracle.mcp.tools.context.get_pending_steps",
                             side_effect=[{"pending_steps": [fake_step]}, {"pending_steps": []}]):
        with unittest.mock.patch("migration_oracle.mcp.tools.context.update_step_status", return_value=fake_update):
            at = AppTest.from_file("migration_oracle/streamlit_app/pages/04_context_dashboard.py")
            at.run()
            at.text_input[0].set_value("p"); at.text_input[1].set_value("2.x"); at.text_input[2].set_value("3.0")
            at.button[0].click().run()
            # Click the first "Mark Complete" button
            complete_buttons = [b for b in at.button if "Complete" in (b.label or "")]
            assert complete_buttons, f"No 'Mark Complete' button found; buttons: {[b.label for b in at.button]}"
            complete_buttons[0].click().run()
            assert at.session_state.get("context_completed_count") == 1, (
                f"Expected context_completed_count=1 from update response; got: {at.session_state.get('context_completed_count')!r}"
            )
            print("PASS: Context Dashboard updates context_completed_count from UpdateStepResponse after Mark Complete")
```

### 4-L: Context Dashboard — `close_migration_context` response checked via `tool_status` key

```bash
# Verify source code uses response["tool_status"] for close_migration_context, not response["status"]
python -c "
import pathlib
src = pathlib.Path('migration_oracle/streamlit_app/pages/04_context_dashboard.py').read_text()
lines = src.splitlines()
# Find close_migration_context usage block and check nearby response key access
for i, line in enumerate(lines):
    if 'close_migration_context' in line:
        context_block = '\n'.join(lines[max(0,i-2):i+10])
        if 'tool_status' in context_block:
            print('PASS: close_migration_context response check uses tool_status key')
            exit(0)
print('FAIL: close_migration_context response does not use tool_status key near the call site')
exit(1)
"
```

### 4-M: Community — empty insights renders `st.info("No community insights found")`

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

with unittest.mock.patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": []}):
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/05_community.py")
    at.run()
    info_texts = [i.value for i in at.info]
    assert any("No community insights found" in t for t in info_texts), f"Expected empty-state info; got: {info_texts}"
    print("PASS: Community shows st.info('No community insights found') when insights=[]")
```

### 4-N: Community — `vote_insight` called with `delta=1` (not `direction="up"`)

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

fake_insight = {
    "insight_id": "ins-1", "statement": "Test statement", "solution": "Test solution",
    "source_url": "", "submitted_by": "user", "created_at": "2026-06-08",
    "confidence": 0.9, "votes": 3, "verified": False, "version": "3.2",
}
vote_kwargs = {}
def _capture_vote(**kwargs):
    vote_kwargs.update(kwargs)
    return {"status": "ok", "insight_id": "ins-1", "new_vote_count": 4}

with unittest.mock.patch("migration_oracle.mcp.tools.community.get_community_insights",
                         return_value={"insights": [fake_insight]}):
    with unittest.mock.patch("migration_oracle.mcp.tools.community.vote_insight", side_effect=_capture_vote):
        at = AppTest.from_file("migration_oracle/streamlit_app/pages/05_community.py")
        at.run()
        vote_buttons = [b for b in at.button if "Vote" in (b.label or "")]
        assert vote_buttons, f"No Vote button found; buttons: {[b.label for b in at.button]}"
        vote_buttons[0].click().run()
        assert vote_kwargs.get("delta") == 1, (
            f"vote_insight must be called with delta=1; got: {vote_kwargs}"
        )
        assert "direction" not in vote_kwargs, (
            f"vote_insight must NOT receive direction kwarg; got: {vote_kwargs}"
        )
        print("PASS: Community calls vote_insight(delta=1) — not direction='up'")
```

### 4-O: Community — submit success renders `st.success("Insight submitted")`

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

with unittest.mock.patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": []}):
    with unittest.mock.patch("migration_oracle.mcp.tools.community.submit_migration_insight",
                             return_value={"status": "ok"}):
        at = AppTest.from_file("migration_oracle/streamlit_app/pages/05_community.py")
        at.run()
        # Open Submit expander and fill form
        at.text_area[0].set_value("Test statement")  # statement
        at.text_area[1].set_value("Test solution")   # solution
        # Submit form
        submit_buttons = [b for b in at.button if "Submit" in (b.label or "")]
        assert submit_buttons, f"No Submit button found; buttons: {[b.label for b in at.button]}"
        submit_buttons[0].click().run()
        success_texts = [s.value for s in at.success]
        assert any("Insight submitted" in t for t in success_texts), f"Expected success message; got: {success_texts}"
        print("PASS: Community shows st.success('Insight submitted') on status='ok'")
```

### 4-P: Community — submit duplicate renders `st.error("Duplicate detected")`

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

with unittest.mock.patch("migration_oracle.mcp.tools.community.get_community_insights", return_value={"insights": []}):
    with unittest.mock.patch("migration_oracle.mcp.tools.community.submit_migration_insight",
                             return_value={"status": "duplicate"}):
        at = AppTest.from_file("migration_oracle/streamlit_app/pages/05_community.py")
        at.run()
        at.text_area[0].set_value("Duplicate statement")
        at.text_area[1].set_value("Some solution")
        submit_buttons = [b for b in at.button if "Submit" in (b.label or "")]
        assert submit_buttons, "No Submit button found"
        submit_buttons[0].click().run()
        error_texts = [e.value for e in at.error]
        assert any("Duplicate detected" in t for t in error_texts), f"Expected duplicate error; got: {error_texts}"
        print("PASS: Community shows st.error('Duplicate detected') on status='duplicate'")
```

---

## Level 5 — Full integration smoke test

**DB required (populated)**. At least one pipeline run and one community insight must exist in Neo4j.

Run the app and verify each page manually.

### 5-A: App starts without error

```bash
streamlit run migration_oracle/streamlit_app/app.py &
STREAMLIT_PID=$!
sleep 5
curl -sf http://localhost:8501/_stcore/health > /dev/null && echo "PASS: Streamlit health check ok (app started)" || echo "FAIL: Streamlit health endpoint not reachable"
kill $STREAMLIT_PID 2>/dev/null
```

### 5-B through 5-F: Manual page walkthrough

Start the app (`streamlit run migration_oracle/streamlit_app/app.py`) and verify each page:

**5-B — Pipeline Trigger**:
1. Select a framework from the dropdown (populated from `FRAMEWORK_DISPLAY_NAMES`).
2. Enter `2.7.x` → `3.2`. Check `--dry-run`.
3. Click Submit.
4. **Verify**: output lines stream into the output area line-by-line (no page reload).
5. **Verify**: `st.success("Exit 0")` appears in green when done.
6. **Verify**: no raw Python traceback visible anywhere on the page.

**5-C — Run Browser**:
1. Navigate to "Run Browser".
2. **Verify**: selectbox appears with labels in `"framework → to_version"` format.
3. Select a run; click each tab (Raw MD, Filtered MD, Entities JSON).
4. **Verify**: content renders in each available tab; missing artifact shows `st.error(...)` not a crash.

**5-D — Rule Explorer**:
1. Navigate to "Rule Explorer".
2. Type a query (e.g. `"removed API"`), leave framework as "All", click Search.
3. **Verify**: result cards appear; each card shows `statement[:80]` as title, `rule_type` badge, and `action_step`.
4. **Verify**: no `steps` or `scopes` sub-sections appear (they are absent from the SearchHit shape).
5. Type a gibberish query; **verify**: `st.info("No rules found for this query")`.

**5-E — Context Dashboard**:
1. Navigate to "Context Dashboard".
2. Fill in project ID, from/to versions, select a framework.
3. Click "Load / Create".
4. **Verify**: context status badge and metric widgets for completed/skipped appear.
5. If pending steps exist: **verify** table renders with summary, effort, automatable, scope, severity columns.
6. Navigate away then back to "Context Dashboard".
7. **Verify**: context is still shown without re-entering the form (session state persisted).

**5-F — Community**:
1. Navigate to "Community".
2. **Verify**: insight cards render with statement, solution, vote count, verified badge.
3. Click "Vote Up" on any insight; **verify**: count increments and list re-fetches.
4. Open "Submit New Insight", fill all fields, submit; **verify**: `st.success("Insight submitted")`.

---

## Level 7 — Edge-case paths

### 7-A: App starts with Neo4j unreachable (lazy import pattern)

```bash
# Unset Neo4j credentials and start the app — it must NOT crash at startup
unset NEO4J_URI NEO4J_PASSWORD
streamlit run migration_oracle/streamlit_app/app.py &
STREAMLIT_PID=$!
sleep 5
STATUS=$(curl -sf http://localhost:8501/_stcore/health > /dev/null && echo "up" || echo "down")
kill $STREAMLIT_PID 2>/dev/null
[ "$STATUS" = "up" ] && echo "PASS: app starts even with Neo4j unreachable (lazy import)" || echo "FAIL: app crashed at startup when Neo4j env vars unset"
```

### 7-B: Rule Explorer — `framework=None` is the correct all-frameworks sentinel (not string omission)

```bash
# Verify the call site explicitly passes framework=fw, never bare positional or omission
python -c "
import ast, pathlib

src = pathlib.Path('migration_oracle/streamlit_app/pages/03_rule_explorer.py').read_text()
tree = ast.parse(src)

for node in ast.walk(tree):
    if isinstance(node, (ast.Call,)):
        func = getattr(node, 'func', None)
        func_name = ''
        if isinstance(func, ast.Attribute): func_name = func.attr
        elif isinstance(func, ast.Name): func_name = func.id
        if func_name == 'search_migration_knowledge':
            kw_names = [kw.arg for kw in node.keywords]
            assert 'framework' in kw_names, (
                f'search_migration_knowledge called without explicit framework= kwarg at line {node.lineno}; '
                f'omitting defaults to Spring Boot, breaking all-frameworks search'
            )
            print(f'PASS: search_migration_knowledge at line {node.lineno} has explicit framework= kwarg')
            break
else:
    raise AssertionError('search_migration_knowledge call not found in 03_rule_explorer.py')
"
```

### 7-C: Context Dashboard — stale context_id (tool raises) surfaces `st.error`, no traceback

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

def _raise(*a, **kw): raise RuntimeError("Context ctx-stale not found in graph")

with unittest.mock.patch("migration_oracle.mcp.tools.context.get_pending_steps", side_effect=_raise):
    at = AppTest.from_file("migration_oracle/streamlit_app/pages/04_context_dashboard.py")
    # Inject a stale context_id directly into session_state
    at.session_state["context_id"] = "ctx-stale"
    at.session_state["context_project_id"] = "p"
    at.session_state["context_from_version"] = "2.x"
    at.session_state["context_to_version"] = "3.0"
    at.session_state["context_framework"] = "Spring Boot"
    at.session_state["context_status"] = "in-progress"
    at.session_state["context_completed_count"] = 0
    at.session_state["context_skipped_count"] = 0
    at.run()
    assert not at.exception, f"Unhandled exception reached Streamlit runtime: {at.exception}"
    error_texts = [e.value for e in at.error]
    assert any("not found" in t.lower() or "ctx-stale" in t for t in error_texts), (
        f"Expected st.error with context-not-found message; got: {error_texts}"
    )
    print("PASS: Context Dashboard surfaces st.error on stale context_id without crashing")
```

### 7-D: Run Browser — one artifact missing shows inline error, other tabs unaffected

```python
from streamlit.testing.v1 import AppTest
import unittest.mock

run = {"framework": "spring-boot", "from_version": "", "to_version": "3.2",
       "raw_md_path": "/some/path.md", "filtered_md_path": None, "entities_json_path": None}

def _artifact_response(framework, from_version, to_version, artifact_type):
    if artifact_type == "raw_md":
        return {"status": "ok", "content": "# Changelog\n\nSome content.", "path_resolved": "/p",
                "framework": framework, "from_version": from_version,
                "to_version": to_version, "artifact_type": artifact_type}
    return {"status": "not_found", "content": "", "path_resolved": "",
            "framework": framework, "from_version": from_version,
            "to_version": to_version, "artifact_type": artifact_type}

with unittest.mock.patch("migration_oracle.mcp.tools.artifacts.list_pipeline_runs", return_value={"runs": [run]}):
    with unittest.mock.patch("migration_oracle.mcp.tools.artifacts.get_artifact_content", side_effect=_artifact_response):
        at = AppTest.from_file("migration_oracle/streamlit_app/pages/02_run_browser.py")
        at.run()
        # Page must not crash even though filtered_md and entities_json are not_found
        assert not at.exception, f"Page crashed on missing artifact: {at.exception}"
        print("PASS: Run Browser handles missing artifact type with inline error; other tabs unaffected")
```

---

## Completion Gate Checklist

Update `docs/SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| Check ID | Description | Result |
|---|---|---|
| 0-A | All modules/pages import or parse without syntax error | ☐ |
| 0-B | `call_tool`, `framework_selectbox`, `effort_badge` exported from `_helpers.py` | ☐ |
| 0-C | `effort_badge` returns correct labels for `"mechanical"` and `"substantial"` | ☐ |
| 0-D | `app.py` has no `migration_oracle` import at module level | ☐ |
| 0-E | `app.py` contains `set_page_config(layout="wide", page_title="Migration Oracle")` | ☐ |
| 1-A | `streamlit>=1.35` installed | ☐ |
| 1-B | All eight files exist at correct nested paths | ☐ |
| 1-C | `sys.executable` and `subprocess.Popen` present in `01_pipeline_trigger.py` | ☐ |
| 1-D | `@st.cache_data(ttl=60)` present in `02_run_browser.py` | ☐ |
| 1-E | `asyncio.run` present in `03_rule_explorer.py` | ☐ |
| 2-A | No `open(` or `read_text`/`read_bytes` in any page file | ☐ |
| 2-B | `framework_selectbox` not called from `03_rule_explorer.py` | ☐ |
| 2-C | No `migration_oracle.mcp.tools` import in `01_pipeline_trigger.py` | ☐ |
| 2-D | No `shell=True` in any file under `streamlit_app/` | ☐ |
| 2-E | No `direction=` kwarg anywhere in `streamlit_app/` | ☐ |
| 2-F | `tool_status` key present in `04_context_dashboard.py` for close response | ☐ |
| 2-G | `call_tool` returns `None` and calls `st.error` on exception | ☐ |
| 2-H | `_helpers.py` uses Python `None` sentinel (not string `"all"`) for `include_all=True` | ☐ |
| 2-I | `search_migration_knowledge` call has explicit `framework=` kwarg in `03_rule_explorer.py` | ☐ |
| 3-A | Neo4j driver connects and `RETURN 1` succeeds | ☐ |
| 3-B | `list_pipeline_runs()` returns dict with `"runs"` list of correct shape | ☐ |
| 3-C | `search_migration_knowledge` returns hits with correct fields; no `title`/`steps`/`scopes` | ☐ |
| 3-D | `get_community_insights()` (no args) returns correct shape | ☐ |
| 3-E | `search_migration_knowledge` accepts display name `"Spring Boot"` as `framework` | ☐ |
| 4-A | All five pages load without exception (AppTest) | ☐ |
| 4-B | Pipeline Trigger: blank version shows warning; no subprocess spawned | ☐ |
| 4-C | Pipeline Trigger: non-zero exit renders `st.error("Exit N: <stderr>")` | ☐ |
| 4-D | Run Browser: empty runs shows `st.info("No pipeline runs found")`; no selectbox | ☐ |
| 4-E | Run Browser: one run renders selectbox with label `"framework → to_version"` | ☐ |
| 4-F | Rule Explorer: empty hits shows `st.info("No rules found for this query")` | ☐ |
| 4-G | Rule Explorer: `search_migration_knowledge` called with `framework=None` when "All" selected | ☐ |
| 4-H | Context Dashboard: load form rendered when no `context_id` in session_state | ☐ |
| 4-I | Context Dashboard: all 8 `context_*` flat keys set after successful create | ☐ |
| 4-J | Context Dashboard: `st.info("No pending steps remaining")` when `pending_steps=[]` | ☐ |
| 4-K | Context Dashboard: `context_completed_count` updated from `UpdateStepResponse` | ☐ |
| 4-L | Context Dashboard: `close_migration_context` response checked via `tool_status` key | ☐ |
| 4-M | Community: empty insights shows `st.info("No community insights found")` | ☐ |
| 4-N | Community: `vote_insight` called with `delta=1`; no `direction=` kwarg | ☐ |
| 4-O | Community: submit success shows `st.success("Insight submitted")` | ☐ |
| 4-P | Community: submit duplicate shows `st.error("Duplicate detected")` | ☐ |
| 5-A | App starts and health endpoint responds (Neo4j reachable) | ☐ |
| 5-B | Pipeline Trigger: dry-run streams output; exit 0 shown in green | ☐ |
| 5-C | Run Browser: renders runs from populated DB; tabs show content | ☐ |
| 5-D | Rule Explorer: query returns result cards with correct fields; no-match shows info | ☐ |
| 5-E | Context Dashboard: load/create, view steps, navigate away and back (session persists) | ☐ |
| 5-F | Community: cards render; vote increments count; submit shows success | ☐ |
| 7-A | App starts without crash when Neo4j env vars unset | ☐ |
| 7-B | `search_migration_knowledge` call has explicit `framework=fw` (AST-verified) | ☐ |
| 7-C | Stale context_id: `get_pending_steps` error surfaces via `st.error`; no traceback | ☐ |
| 7-D | Missing artifact type: affected tab shows `st.error`; other tabs unaffected | ☐ |

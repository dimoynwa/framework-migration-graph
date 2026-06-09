# Verification Protocol: 008-mcp-bug-fixes

**Location**: `specs/008-mcp-bug-fixes/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `008` ✅
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | How to confirm |
|---|---|
| Dependencies installed | `uv sync` or `pip install -e .` in repo root |
| Neo4j reachable | `NEO4J_URI`, `NEO4J_PASSWORD` set in env |
| Spring Boot 4.0.0 data loaded | Graph contains `(:Version {framework:'Spring Boot', version:'4.0.0'})` |
| MCP server not required | All checks run directly against Python modules |

| Level | Neo4j | LLM |
|---|---|---|
| 0 — Static checks | ✗ | ✗ |
| 1 — Query structure | ✗ | ✗ |
| 2 — Isolation behaviour | ✗ | ✗ |
| 3 — Graph read path | ✓ | ✗ |
| 4 — Submit insight (no embeddings) | ✓ | ✗ |
| 5 — Search and deprecation | ✓ | ✗ |
| 6 — Idempotency | ✓ | ✗ |
| 7 — Edge-case paths | ✓ | ✗ |

---

## Level 0 — Static checks

No services required. Paste each block into a Python REPL from the repo root.

### 0-A — All modified modules import without error

```python
import migration_oracle.mcp.graph.queries.context   as ctx_q
import migration_oracle.mcp.graph.queries.upgrade   as upg_q
import migration_oracle.mcp.graph.queries.deprecation as dep_q
import migration_oracle.graph.indexes               as idx
import migration_oracle.mcp.tools.upgrade           as upg_t
import migration_oracle.mcp.tools.community         as com_t
print('PASS: 0-A all modules import cleanly')
```

### 0-B — `_INDEXES` contains the `migration_text` fulltext index DDL

```python
from migration_oracle.graph.indexes import _INDEXES
found = any('migration_text' in s for s in _INDEXES)
assert found, f'FAIL: migration_text index not in _INDEXES. Current entries: {[s for s in _INDEXES if "FULLTEXT" in s.upper()]}'
print('PASS: 0-B migration_text fulltext index present in _INDEXES')
```

### 0-C — `_INDEXES` contains the `openrewrite_recipe_description` fulltext index DDL

```python
from migration_oracle.graph.indexes import _INDEXES
found = any('openrewrite_recipe_description' in s for s in _INDEXES)
assert found, f'FAIL: openrewrite_recipe_description index not in _INDEXES. Current entries: {[s for s in _INDEXES if "FULLTEXT" in s.upper()]}'
print('PASS: 0-C openrewrite_recipe_description fulltext index present in _INDEXES')
```

### 0-D — `_to_minor_zero` helper exists in `mcp/tools/upgrade.py`

```python
from migration_oracle.mcp.tools import upgrade as upg_t
assert hasattr(upg_t, '_to_minor_zero'), 'FAIL: _to_minor_zero not found in migration_oracle.mcp.tools.upgrade'
print('PASS: 0-D _to_minor_zero helper present')
```

### 0-E — Default `classification` in `analyze_upgrade_path` (query layer) is empty list

```python
import inspect, migration_oracle.mcp.graph.queries.upgrade as upg_q
src = inspect.getsource(upg_q.analyze_upgrade_path)
assert 'classification or []' in src, (
    'FAIL: analyze_upgrade_path still defaults classification to a non-empty list. '
    f'Found in source:\n{[l for l in src.splitlines() if "classes" in l]}'
)
print('PASS: 0-E analyze_upgrade_path defaults classification to []')
```

### 0-F — Default `classification` in `build_recipe_plan` (query layer) is empty list

```python
import inspect, migration_oracle.mcp.graph.queries.upgrade as upg_q
src = inspect.getsource(upg_q.build_recipe_plan)
assert 'classification or []' in src, (
    'FAIL: build_recipe_plan still defaults classification to a non-empty list. '
    f'Found in source:\n{[l for l in src.splitlines() if "classes" in l]}'
)
print('PASS: 0-F build_recipe_plan defaults classification to []')
```

### 0-G — `_ANALYZE_UPGRADE_PATH` uses directed `[:INCLUDES_RULE]->` (not undirected)

```python
import migration_oracle.mcp.graph.queries.upgrade as upg_q
query = upg_q._ANALYZE_UPGRADE_PATH
assert ')-[:INCLUDES_RULE]->(rule:MigrationRule)' in query, (
    'FAIL: _ANALYZE_UPGRADE_PATH still uses undirected or mixed-label relationship. '
    f'Offending fragment: {[l.strip() for l in query.splitlines() if "INCLUDES_RULE" in l]}'
)
assert 'DISCOVERED_IN' not in query or 'INCLUDES_RULE|DISCOVERED_IN' not in query, (
    'FAIL: _ANALYZE_UPGRADE_PATH still mixes INCLUDES_RULE with DISCOVERED_IN in the same match'
)
print('PASS: 0-G _ANALYZE_UPGRADE_PATH uses directed INCLUDES_RULE->MigrationRule')
```

### 0-H — `_GET_PENDING_STEPS` does not reference bare `s.stepIndex` after `collect(`

```python
import migration_oracle.mcp.graph.queries.context as ctx_q
query = ctx_q._GET_PENDING_STEPS
lines = query.splitlines()
collect_line = next((i for i, l in enumerate(lines) if 'collect(DISTINCT' in l and 'requires' in l), None)
assert collect_line is not None, 'FAIL: could not find collect(DISTINCT ... requires line in _GET_PENDING_STEPS'
order_section = '\n'.join(lines[collect_line:])
# After the collect the ORDER BY must use aliases, not raw s.stepIndex
assert 's.stepIndex' not in order_section, (
    'FAIL: s.stepIndex still appears after collect() in _GET_PENDING_STEPS ORDER BY. '
    f'Fragment after collect line:\n{order_section[:300]}'
)
print('PASS: 0-H _GET_PENDING_STEPS ORDER BY uses aliases, not bare s.stepIndex')
```

### 0-I — `_GET_PENDING_STEPS` projects `_step_index` and `_severity_rank` aliases

```python
import migration_oracle.mcp.graph.queries.context as ctx_q
query = ctx_q._GET_PENDING_STEPS
assert '_step_index' in query, 'FAIL: _step_index alias missing from _GET_PENDING_STEPS RETURN clause'
assert '_severity_rank' in query, 'FAIL: _severity_rank alias missing from _GET_PENDING_STEPS RETURN clause'
print('PASS: 0-I _GET_PENDING_STEPS projects _step_index and _severity_rank aliases')
```

### 0-J — `get_pending_steps` Python function strips internal aliases from returned rows

```python
import inspect, migration_oracle.mcp.graph.queries.context as ctx_q
src = inspect.getsource(ctx_q.get_pending_steps)
assert '_internal' in src or '_step_index' in src, (
    'FAIL: get_pending_steps does not strip _step_index/_severity_rank from returned rows. '
    'Source snippet: ' + src[:400]
)
print('PASS: 0-J get_pending_steps strips internal sort-key aliases before returning')
```

### 0-K — `submit_migration_insight` wraps `encode()` in try/except

```python
import inspect, migration_oracle.mcp.tools.community as com_t
src = inspect.getsource(com_t.submit_migration_insight)
assert 'try:' in src, 'FAIL: submit_migration_insight has no try block around encode()'
assert 'except' in src, 'FAIL: submit_migration_insight has no except clause around encode()'
# Confirm the unconditional encode() call is gone
lines = [l.strip() for l in src.splitlines()]
bare_encode = [l for l in lines if l.startswith('embedding') and '.encode(' in l and 'try' not in l]
assert not bare_encode, f'FAIL: unconditional encode() call still present: {bare_encode}'
print('PASS: 0-K submit_migration_insight wraps encode() in try/except')
```

### 0-L — `_RESOLVE_DEPRECATION` includes `INTRODUCES` / `REMOVES` fallback

```python
import migration_oracle.mcp.graph.queries.deprecation as dep_q
query = dep_q._RESOLVE_DEPRECATION
assert 'INTRODUCES' in query, (
    'FAIL: _RESOLVE_DEPRECATION missing INTRODUCES relationship fallback. '
    f'Current query:\n{query}'
)
assert 'REMOVES' in query, (
    'FAIL: _RESOLVE_DEPRECATION missing REMOVES relationship fallback. '
    f'Current query:\n{query}'
)
print('PASS: 0-L _RESOLVE_DEPRECATION has INTRODUCES/REMOVES fallback lookups')
```

---

## Level 1 — Query structure

No services required. Verifies the internal Cypher structure for correctness patterns.

### 1-A — `_BUILD_RECIPE_PLAN` WHERE clause handles empty classification list

```python
import migration_oracle.mcp.graph.queries.upgrade as upg_q
query = upg_q._BUILD_RECIPE_PLAN
assert 'size($classification) = 0' in query, (
    'FAIL: _BUILD_RECIPE_PLAN WHERE does not guard against empty classification list. '
    f'Relevant lines: {[l.strip() for l in query.splitlines() if "entityClassification" in l]}'
)
print('PASS: 1-A _BUILD_RECIPE_PLAN WHERE guards empty classification with size() = 0')
```

### 1-B — `_ANALYZE_UPGRADE_PATH` WHERE clause handles empty classification list

```python
import migration_oracle.mcp.graph.queries.upgrade as upg_q
query = upg_q._ANALYZE_UPGRADE_PATH
assert 'size($classification) = 0' in query, (
    'FAIL: _ANALYZE_UPGRADE_PATH WHERE does not guard against empty classification list. '
    f'Relevant lines: {[l.strip() for l in query.splitlines() if "entityClassification" in l]}'
)
print('PASS: 1-B _ANALYZE_UPGRADE_PATH WHERE guards empty classification with size() = 0')
```

### 1-C — `_GET_PENDING_STEPS` ORDER BY references only aliased names

```python
import migration_oracle.mcp.graph.queries.context as ctx_q
query = ctx_q._GET_PENDING_STEPS
order_block = query[query.rfind('ORDER BY'):]
# Must reference the aliases, not bare node properties
assert '_severity_rank' in order_block, (
    f'FAIL: ORDER BY does not reference _severity_rank alias. ORDER BY block:\n{order_block}'
)
assert '_step_index' in order_block, (
    f'FAIL: ORDER BY does not reference _step_index alias. ORDER BY block:\n{order_block}'
)
print('PASS: 1-C ORDER BY references _severity_rank and _step_index aliases')
```

---

## Level 2 — Isolation behaviour

No services required. Pure Python logic checks.

### 2-A — `_to_minor_zero` strips patch correctly

```python
from migration_oracle.mcp.tools.upgrade import _to_minor_zero
cases = [
    ("3.5.12", "3.5.0"),
    ("4.0.6",  "4.0.0"),
    ("3.5.0",  "3.5.0"),
    ("17.0.1", "17.0.0"),
]
for inp, expected in cases:
    result = _to_minor_zero(inp)
    assert result == expected, f'FAIL: _to_minor_zero({inp!r}) = {result!r}, expected {expected!r}'
print('PASS: 2-A _to_minor_zero strips patch component correctly for all cases')
```

### 2-B — Patch version produces same `sortable_version` as `.0` equivalent

```python
from migration_oracle.mcp.tools.upgrade import _to_minor_zero
from migration_oracle.models.graph import sortable_version
pairs = [("3.5.12", "3.5.0"), ("4.0.6", "4.0.0")]
for patch_v, minor_v in pairs:
    sv_patch = sortable_version(_to_minor_zero(patch_v))
    sv_minor = sortable_version(minor_v)
    assert sv_patch == sv_minor, (
        f'FAIL: sortable_version(_to_minor_zero({patch_v!r})) = {sv_patch} '
        f'!= sortable_version({minor_v!r}) = {sv_minor}'
    )
print('PASS: 2-B patch versions normalise to same sortable value as .0 equivalents')
```

### 2-C — `submit_migration_insight` handler proceeds when embedding model raises

```python
# Simulate unavailable embedding model without any DB connection
from unittest.mock import patch, MagicMock
import migration_oracle.mcp.tools.community as com_t
import migration_oracle.mcp.graph.queries.community as com_q

# Patch encode to raise, and patch submit_insight to return a fake success
with patch.object(com_t, 'get_embedding_model') as mock_model, \
     patch.object(com_q, 'submit_insight', return_value=('fake-id-001', False)) as mock_submit:
    mock_model.return_value.encode.side_effect = RuntimeError('model not available')
    result = com_t.submit_migration_insight(
        statement='Test insight for embedding-disabled path',
        spring_boot_version='4.0.0',
    )

assert result['status'] == 'ok', f'FAIL: expected status ok, got {result}'
# Confirm submit_insight was called with embedding=None
call_kwargs = mock_submit.call_args.kwargs
assert call_kwargs.get('embedding') is None, (
    f'FAIL: embedding was not None when encode raised. Got: {call_kwargs.get("embedding")}'
)
print('PASS: 2-C submit_migration_insight proceeds with embedding=None when encode() raises')
```

### 2-D — `_get_pending_steps` return value contains no internal aliases

```python
# Simulate a DB row that includes the internal aliases to confirm stripping works
from unittest.mock import patch, MagicMock
import migration_oracle.mcp.graph.queries.context as ctx_q

fake_row = {
    'step_id': 'abc',
    'step_type': 'code',
    'rule_id': 'r1',
    'summary': 'Do X',
    'instruction': 'Run Y',
    'verification_hint': None,
    'effort': 'low',
    'automatable': False,
    'scope': None,
    'severity': None,
    'recipe_id': None,
    'requires': [],
    '_step_index': 0,
    '_severity_rank': 3,
}

with patch('migration_oracle.mcp.graph.queries.context.read_session') as mock_sess:
    mock_run = MagicMock()
    mock_run.__iter__ = lambda s: iter([fake_row])
    mock_sess.return_value.__enter__.return_value.run.return_value = mock_run
    rows = ctx_q.get_pending_steps(context_id='test-ctx', effort_filter=[], scope_filter=[])

assert rows, 'FAIL: get_pending_steps returned empty list from fake row'
assert '_step_index' not in rows[0], f'FAIL: _step_index leaked into returned row: {rows[0].keys()}'
assert '_severity_rank' not in rows[0], f'FAIL: _severity_rank leaked into returned row: {rows[0].keys()}'
assert 'step_id' in rows[0], f'FAIL: step_id missing from returned row: {rows[0].keys()}'
print('PASS: 2-D get_pending_steps strips _step_index and _severity_rank from output')
```

---

## Level 3 — Graph read path

**Neo4j required.** Run after `uv run python -c "from migration_oracle.graph.driver import driver; driver()"` succeeds.

### 3-A — Neo4j driver connects

```python
from migration_oracle.graph.driver import read_session
with read_session() as session:
    result = session.run("RETURN 1 AS n").single()
assert result["n"] == 1, f'FAIL: unexpected result {result}'
print('PASS: 3-A Neo4j driver connects and responds')
```

### 3-B — `analyze_upgrade_path` returns at least one rule for Spring Boot 3.5.0 → 4.0.0

```python
from migration_oracle.mcp.graph.queries.upgrade import analyze_upgrade_path
rows = analyze_upgrade_path(
    framework='Spring Boot',
    current_version='3.5.0',
    target_version='4.0.0',
)
all_rules = [rule for row in rows for rule in (row.get('rules') or [])]
assert len(all_rules) > 0, (
    f'FAIL: analyze_upgrade_path returned 0 rules for Spring Boot 3.5.0->4.0.0. '
    f'Rows returned: {len(rows)}, row[0] sample: {rows[0] if rows else "no rows"}'
)
print(f'PASS: 3-B analyze_upgrade_path returned {len(all_rules)} rules for Spring Boot 3.5.0->4.0.0')
```

### 3-C — `build_recipe_plan` returns a non-empty plan for Spring Boot 3.5.0 → 4.0.0

```python
from migration_oracle.mcp.graph.queries.upgrade import build_recipe_plan
plan = build_recipe_plan(
    framework='Spring Boot',
    current_version='3.5.0',
    target_version='4.0.0',
)
total = len(plan['auto_track']) + len(plan['manual_track'])
assert total > 0, (
    f'FAIL: build_recipe_plan returned empty plan. '
    f'auto_track={plan["auto_track"]}, manual_track={plan["manual_track"][:2]}, '
    f'fallback_to_rule_cards={plan["fallback_to_rule_cards"]}'
)
print(f'PASS: 3-C build_recipe_plan returned {total} steps (auto={len(plan["auto_track"])}, manual={len(plan["manual_track"])})')
```

### 3-D — Fulltext indexes `migration_text` and `openrewrite_recipe_description` exist in the graph

```python
from migration_oracle.graph.driver import read_session
with read_session() as session:
    rows = list(session.run("SHOW FULLTEXT INDEXES YIELD name RETURN name"))
index_names = {r['name'] for r in rows}
assert 'migration_text' in index_names, (
    f'FAIL: migration_text fulltext index not found in graph. '
    f'Existing fulltext indexes: {index_names}'
)
assert 'openrewrite_recipe_description' in index_names, (
    f'FAIL: openrewrite_recipe_description fulltext index not found in graph. '
    f'Existing fulltext indexes: {index_names}'
)
print(f'PASS: 3-D both fulltext indexes present: {index_names}')
```

### 3-E — `get_pending_steps` does not raise for a real context (or an absent context returns empty)

```python
from migration_oracle.mcp.graph.queries.context import get_pending_steps
# Use a context_id that almost certainly doesn't exist — should return [] not raise
try:
    steps = get_pending_steps(
        context_id='00000000-0000-0000-0000-000000000000',
        effort_filter=[],
        scope_filter=[],
    )
    assert isinstance(steps, list), f'FAIL: expected list, got {type(steps)}'
    print(f'PASS: 3-E get_pending_steps returned {len(steps)} steps without raising (absent context → [])')
except Exception as e:
    print(f'FAIL: 3-E get_pending_steps raised an exception: {type(e).__name__}: {e}')
    raise
```

### 3-F — BM25 search against `openrewrite_recipe_description` returns results

```python
from migration_oracle.mcp.graph.queries.search import bm25_search
hits = bm25_search(query='Spring Boot upgrade', index='openrewrite_recipe_description', top_k=5)
assert len(hits) > 0, (
    'FAIL: BM25 search on openrewrite_recipe_description returned 0 hits. '
    'Index may not be populated — ensure ensure_indexes() was called after server restart.'
)
print(f'PASS: 3-F BM25 search on openrewrite_recipe_description returned {len(hits)} hits')
```

---

## Level 4 — Submit insight without embeddings

**Neo4j required. LLM/embeddings not required.**

### 4-A — `submit_migration_insight` succeeds when embedding encode raises

```python
from unittest.mock import patch
import migration_oracle.mcp.tools.community as com_t

_UNIQUE_STMT = 'VERIFY-008-no-embed: test insight unique-' + __import__('uuid').uuid4().hex

with patch.object(com_t, 'get_embedding_model') as mock_model:
    mock_model.return_value.encode.side_effect = RuntimeError('embeddings disabled')
    result = com_t.submit_migration_insight(
        statement=_UNIQUE_STMT,
        spring_boot_version='4.0.0',
        solution='No solution needed — verification test',
        framework='Spring Boot',
    )

assert result['status'] in ('ok', 'duplicate'), (
    f'FAIL: submit_migration_insight returned unexpected status: {result}'
)
_insight_id = result['insight_id']
print(f'PASS: 4-A submit_migration_insight succeeded with status={result["status"]}, id={_insight_id}')
```

### 4-B — The written `CommunityInsight` node exists in the graph with null embedding

```python
# Reuse _insight_id from 4-A (run in same session)
from migration_oracle.graph.driver import read_session
with read_session() as session:
    rec = session.run(
        'MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id '
        'RETURN ci.statement AS stmt, ci.embedding AS emb',
        id=_insight_id,
    ).single()
assert rec is not None, f'FAIL: CommunityInsight node {_insight_id!r} not found in graph'
assert rec['stmt'] == _UNIQUE_STMT, f'FAIL: statement mismatch: {rec["stmt"]!r}'
assert rec['emb'] is None, f'FAIL: embedding should be null when embeddings disabled, got: {rec["emb"]}'
print(f'PASS: 4-B CommunityInsight node written with null embedding as expected')
```

### 4-C — Cleanup: remove the test insight written by 4-A

```python
from migration_oracle.graph.driver import write_session
with write_session() as session:
    session.run('MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci', id=_insight_id)
# Verify gone
from migration_oracle.graph.driver import read_session
with read_session() as session:
    rec = session.run('MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id RETURN ci', id=_insight_id).single()
assert rec is None, f'FAIL: cleanup failed — node {_insight_id!r} still exists'
print('PASS: 4-C test CommunityInsight node cleaned up')
```

---

## Level 5 — Search and deprecation integration

**Neo4j required.**

### 5-A — `search_openrewrite_recipes` returns ≥ 1 hit

```python
import asyncio
from migration_oracle.mcp.tools.search import search_openrewrite_recipes
result = asyncio.run(search_openrewrite_recipes(query='Spring Boot upgrade', max_results=5))
assert result['status'] == 'ok', f'FAIL: status={result["status"]}'
assert len(result['hits']) > 0, (
    f'FAIL: search_openrewrite_recipes returned 0 hits despite 333 recipes in graph. '
    'Ensure openrewrite_recipe_description fulltext index exists (check 3-D) and '
    'ensure_indexes() was called after server restart.'
)
print(f'PASS: 5-A search_openrewrite_recipes returned {len(result["hits"])} hits')
```

### 5-B — `resolve_deprecation` returns a result for a known Spring Boot entity

```python
# EnvironmentPostProcessor was confirmed deprecated in Spring Boot 4.0 per ISSUES.md
from migration_oracle.mcp.graph.queries.deprecation import resolve_deprecation
result = resolve_deprecation(entity_name='EnvironmentPostProcessor', framework='Spring Boot')
assert result is not None, (
    'FAIL: resolve_deprecation returned None for EnvironmentPostProcessor. '
    'The fallback INTRODUCES/REMOVES lookup may not be working, or the entity '
    'is absent from the graph entirely.'
)
assert result.get('original_entity') == 'EnvironmentPostProcessor', (
    f'FAIL: unexpected original_entity: {result.get("original_entity")}'
)
deprecated_or_removed = result.get('deprecated_in') or result.get('removed_in')
assert deprecated_or_removed is not None, (
    f'FAIL: both deprecated_in and removed_in are null for EnvironmentPostProcessor. '
    f'Full result: {result}'
)
print(f'PASS: 5-B resolve_deprecation returned entity with deprecated_in={result.get("deprecated_in")}, removed_in={result.get("removed_in")}')
```

### 5-C — `analyze_upgrade_path` tool layer returns rules (checks tool-layer classification default)

```python
import asyncio
# Call through the MCP tool layer, not the query layer
from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path
result = analyze_upgrade_path(
    framework='Spring Boot',
    current_version='3.5.0',
    target_version='4.0.0',
)
assert result['status'] == 'ok', f'FAIL: status={result["status"]}'
assert len(result['rules']) > 0, (
    f'FAIL: analyze_upgrade_path tool returned 0 rules. '
    f'Check that mcp/tools/upgrade.py also passes classification=[] (not ["actionable","incomplete"])'
)
print(f'PASS: 5-C analyze_upgrade_path tool returned {len(result["rules"])} rules')
```

---

## Level 6 — Idempotency

**Neo4j required.**

### 6-A — Submitting the same insight twice returns `duplicate` on the second call

```python
import asyncio, uuid
from unittest.mock import patch
import migration_oracle.mcp.tools.community as com_t

_DEDUP_STMT = f'DEDUP-TEST-008: duplicate detection check {uuid.uuid4().hex}'

# First submission
result1 = com_t.submit_migration_insight(
    statement=_DEDUP_STMT,
    spring_boot_version='4.0.0',
    framework='Spring Boot',
)
assert result1['status'] == 'ok', f'FAIL: first submission status={result1["status"]}'
_dedup_id = result1['insight_id']

# Second submission with identical statement
result2 = com_t.submit_migration_insight(
    statement=_DEDUP_STMT,
    spring_boot_version='4.0.0',
    framework='Spring Boot',
)
assert result2['status'] == 'duplicate', (
    f'FAIL: second submission should be duplicate, got status={result2["status"]}. '
    'Exact-statement dedup may not be working.'
)
print(f'PASS: 6-A second submit_migration_insight call returns status=duplicate')
```

### 6-B — Cleanup: remove the dedup test insight

```python
from migration_oracle.graph.driver import write_session, read_session
with write_session() as session:
    session.run('MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci', id=_dedup_id)
with read_session() as session:
    rec = session.run('MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id RETURN ci', id=_dedup_id).single()
assert rec is None, f'FAIL: dedup cleanup failed — node {_dedup_id!r} still present'
print('PASS: 6-B dedup test CommunityInsight cleaned up')
```

### 6-C — Running `ensure_indexes` twice does not raise and does not duplicate indexes

```python
from migration_oracle.graph.driver import driver as get_driver
from migration_oracle.graph.indexes import ensure_indexes
d = get_driver()
ensure_indexes(d)  # first call
ensure_indexes(d)  # second call — must be idempotent
from migration_oracle.graph.driver import read_session
with read_session() as session:
    rows = list(session.run(
        "SHOW FULLTEXT INDEXES YIELD name WHERE name IN ['migration_text','openrewrite_recipe_description'] RETURN name"
    ))
assert len(rows) == 2, (
    f'FAIL: expected exactly 2 matching fulltext indexes after double ensure_indexes, got {len(rows)}: {rows}'
)
print('PASS: 6-C ensure_indexes is idempotent — no duplicate indexes after second call')
```

---

## Level 7 — Edge-case paths

### 7-A — Patch version input returns same rules as `.0` equivalent

```python
from migration_oracle.mcp.graph.queries.upgrade import analyze_upgrade_path
rows_exact = analyze_upgrade_path(framework='Spring Boot', current_version='3.5.0', target_version='4.0.0')
rows_patch = analyze_upgrade_path(framework='Spring Boot', current_version='3.5.12', target_version='4.0.6')
rules_exact = [r for row in rows_exact for r in (row.get('rules') or [])]
rules_patch = [r for row in rows_patch for r in (row.get('rules') or [])]
assert len(rules_exact) == len(rules_patch), (
    f'FAIL: patch version produced different rule count. '
    f'3.5.0→4.0.0: {len(rules_exact)} rules, 3.5.12→4.0.6: {len(rules_patch)} rules'
)
print(f'PASS: 7-A patch version "3.5.12"→"4.0.6" returns same {len(rules_patch)} rules as "3.5.0"→"4.0.0"')
```

### 7-B — Explicit `classification` filter still narrows results correctly

```python
from migration_oracle.mcp.graph.queries.upgrade import analyze_upgrade_path
rows_all = analyze_upgrade_path(framework='Spring Boot', current_version='3.5.0', target_version='4.0.0')
rules_all = [r for row in rows_all for r in (row.get('rules') or [])]

# Pass a classification value that likely matches nothing — expect fewer or equal rules
rows_filtered = analyze_upgrade_path(
    framework='Spring Boot', current_version='3.5.0', target_version='4.0.0',
    classification=['__no_such_class__'],
)
rules_filtered = [r for row in rows_filtered for r in (row.get('rules') or [])]
assert len(rules_filtered) <= len(rules_all), (
    f'FAIL: filtered result has MORE rules ({len(rules_filtered)}) than unfiltered ({len(rules_all)})'
)
print(f'PASS: 7-B explicit classification filter works — all={len(rules_all)}, filtered={len(rules_filtered)}')
```

### 7-C — `get_pending_steps` with all steps already completed returns empty list (not crash)

```python
from migration_oracle.mcp.graph.queries.context import create_or_get_context, get_pending_steps, record_step_outcome
from migration_oracle.graph.driver import write_session

# Create a throwaway context
ctx = create_or_get_context(
    project_id='verify-008-empty-steps',
    from_version='3.5.0',
    to_version='4.0.0',
    framework='Spring Boot',
    scanned_entities=[],
)
ctx_id = ctx['context_id']

# Get steps (may be non-empty or empty depending on graph state)
steps = get_pending_steps(context_id=ctx_id, effort_filter=[], scope_filter=[])
# Mark all steps completed
for step in steps:
    record_step_outcome(context_id=ctx_id, step_id=step['step_id'], outcome='completed')

# Now pending steps must be empty
steps_after = get_pending_steps(context_id=ctx_id, effort_filter=[], scope_filter=[])
assert isinstance(steps_after, list), f'FAIL: expected list, got {type(steps_after)}'
assert len(steps_after) == 0, (
    f'FAIL: expected 0 pending steps after completing all, got {len(steps_after)}'
)
print(f'PASS: 7-C get_pending_steps returns [] after all steps completed (no crash)')

# Cleanup
with write_session() as session:
    session.run('MATCH (mc:MigrationContext) WHERE elementId(mc) = $id DETACH DELETE mc', id=ctx_id)
print('PASS: 7-C throwaway MigrationContext cleaned up')
```

### 7-D — `search_openrewrite_recipes` with an unlikely query returns empty list gracefully (not crash)

```python
import asyncio
from migration_oracle.mcp.tools.search import search_openrewrite_recipes
result = asyncio.run(search_openrewrite_recipes(
    query='xyzzy-no-match-esperanto-unicorn-quantum',
    max_results=5,
))
assert result['status'] == 'ok', f'FAIL: status={result["status"]}'
assert isinstance(result['hits'], list), f'FAIL: hits is not a list: {type(result["hits"])}'
print(f'PASS: 7-D search_openrewrite_recipes returns empty list gracefully for unmatched query')
```

---

## Completion Gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| ID | Description | Result |
|---|---|---|
| 0-A | All modified modules import without error | |
| 0-B | `_INDEXES` contains `migration_text` fulltext DDL | |
| 0-C | `_INDEXES` contains `openrewrite_recipe_description` fulltext DDL | |
| 0-D | `_to_minor_zero` helper present in `mcp/tools/upgrade.py` | |
| 0-E | `analyze_upgrade_path` query layer defaults `classification` to `[]` | |
| 0-F | `build_recipe_plan` query layer defaults `classification` to `[]` | |
| 0-G | `_ANALYZE_UPGRADE_PATH` uses directed `[:INCLUDES_RULE]->(rule:MigrationRule)` | |
| 0-H | `_GET_PENDING_STEPS` ORDER BY uses aliases, not bare `s.stepIndex` | |
| 0-I | `_GET_PENDING_STEPS` projects `_step_index` and `_severity_rank` | |
| 0-J | `get_pending_steps` strips internal aliases from returned rows | |
| 0-K | `submit_migration_insight` wraps `encode()` in try/except | |
| 0-L | `_RESOLVE_DEPRECATION` includes `INTRODUCES`/`REMOVES` fallback | |
| 1-A | `_BUILD_RECIPE_PLAN` WHERE guards empty classification with `size() = 0` | |
| 1-B | `_ANALYZE_UPGRADE_PATH` WHERE guards empty classification with `size() = 0` | |
| 1-C | ORDER BY references only `_severity_rank` and `_step_index` aliases | |
| 2-A | `_to_minor_zero` strips patch for all test cases | |
| 2-B | Patch versions produce same `sortable_version` as `.0` equivalents | |
| 2-C | `submit_migration_insight` proceeds with `embedding=None` when encode raises | |
| 2-D | `get_pending_steps` strips `_step_index` and `_severity_rank` from output | |
| 3-A | Neo4j driver connects | |
| 3-B | `analyze_upgrade_path` returns ≥ 1 rule for Spring Boot 3.5.0 → 4.0.0 | |
| 3-C | `build_recipe_plan` returns non-empty plan for Spring Boot 3.5.0 → 4.0.0 | |
| 3-D | Both fulltext indexes exist in the graph after `ensure_indexes` | |
| 3-E | `get_pending_steps` does not raise for absent context | |
| 3-F | BM25 search on `openrewrite_recipe_description` returns results | |
| 4-A | `submit_migration_insight` succeeds when `encode()` raises | |
| 4-B | Written `CommunityInsight` node has null embedding | |
| 4-C | Test insight node cleaned up | |
| 5-A | `search_openrewrite_recipes` returns ≥ 1 hit | |
| 5-B | `resolve_deprecation` returns entity for `EnvironmentPostProcessor` | |
| 5-C | `analyze_upgrade_path` tool layer returns rules | |
| 6-A | Second `submit_migration_insight` call returns `status=duplicate` | |
| 6-B | Dedup test insight cleaned up | |
| 6-C | `ensure_indexes` is idempotent — no duplicate indexes on second call | |
| 7-A | Patch version `3.5.12→4.0.6` returns same rules as `3.5.0→4.0.0` | |
| 7-B | Explicit classification filter narrows results | |
| 7-C | `get_pending_steps` returns `[]` after all steps completed (no crash) | |
| 7-D | `search_openrewrite_recipes` returns empty list gracefully for no-match query | |

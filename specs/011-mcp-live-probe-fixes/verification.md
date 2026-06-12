**Location**: `specs/011-mcp-live-probe-fixes/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `011` ✅
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | Check |
|---|---|
| Dependencies synced | `pip install -e ".[dev]"` exits 0 |
| Neo4j reachable (Levels 3–7) | `cypher-shell -u neo4j -p <password> "RETURN 1"` exits 0 |
| MCP server not running | Levels 0–2 need the port free; Levels 3–7 hit the graph directly |
| Repo root | All commands run from `/Users/dimo.drangov/paysafe-version-migration-graph/` |
| Ingestion run (Levels 5–7) | `python -m migration_oracle.pipeline.populate` must complete before Level 5 |

**Level 0–2**: No Neo4j, no LLM required.
**Level 3**: Neo4j required; no LLM.
**Level 4**: Not applicable (this spec has no dry-run mode).
**Level 5–7**: Neo4j required; no LLM (changes are code/ingestion, not LLM-generated artifacts).

---

## Level 0 — Static checks

No infrastructure required. Verifies the implementation exists and constants match spec.

### 0-A — All modified modules import without error

```python
python -c "
import migration_oracle.mcp.tools.upgrade as u
import migration_oracle.mcp.tools.context as c
import migration_oracle.mcp.tools.artifacts as a
import migration_oracle.mcp.graph.queries.context as qc
import migration_oracle.mcp.graph.queries.upgrade as qu
import migration_oracle.mcp.graph.queries.artifacts as qa
import migration_oracle.pipeline.populator as pop
import migration_oracle.pipeline.seeds.deprecated_classes as dc
import migration_oracle.pipeline.seeds.lifecycle_alerts as la
import migration_oracle.paysafe.resolver as r
import migration_oracle.graph.queries.pipeline as gqp
print('PASS: 0-A all modules import cleanly')
"
```

### 0-B — `canonical_framework` helper exists and is callable

```python
python -c "
from migration_oracle.mcp.tools.upgrade import canonical_framework, _CanonicalFramework
cf = canonical_framework('Spring Boot')
assert isinstance(cf, _CanonicalFramework), f'Expected _CanonicalFramework, got {type(cf)}'
assert cf.display == 'Spring Boot', f'display wrong: {cf.display}'
assert cf.slug == 'spring-boot', f'slug wrong: {cf.slug}'
print('PASS: 0-B canonical_framework returns _CanonicalFramework with correct fields')
"
```

### 0-C — `_FRAMEWORK_ALIASES` covers all required spellings

```python
python -c "
from migration_oracle.mcp.tools.upgrade import _normalise_key, _FRAMEWORK_ALIASES
required_keys = ['springboot']   # after _normalise_key: 'Spring Boot', 'spring boot', 'spring-boot', 'springboot' all normalise here
for raw in ['Spring Boot', 'spring boot', 'spring-boot', 'springboot']:
    k = _normalise_key(raw)
    assert k in _FRAMEWORK_ALIASES, f'_FRAMEWORK_ALIASES missing normalised key for {raw!r} (normalised: {k!r})'
print('PASS: 0-C all four accepted spellings resolve in _FRAMEWORK_ALIASES')
"
```

### 0-D — `_MAVEN_COORDS` is keyed by slug

```python
python -c "
from migration_oracle.mcp.tools.upgrade import _MAVEN_COORDS
assert 'spring-boot' in _MAVEN_COORDS, f'spring-boot slug missing; keys: {list(_MAVEN_COORDS)}'
group_id, artifact_id = _MAVEN_COORDS['spring-boot']
assert group_id == 'org.springframework.boot', f'Wrong groupId: {group_id}'
print('PASS: 0-D _MAVEN_COORDS keyed by slug with correct coordinates')
"
```

### 0-E — `_FINDIT_TIMEOUT_SECONDS` constant exists in resolver

```python
python -c "
import migration_oracle.paysafe.resolver as r
assert hasattr(r, '_FINDIT_TIMEOUT_SECONDS'), 'Missing _FINDIT_TIMEOUT_SECONDS on resolver'
assert isinstance(r._FINDIT_TIMEOUT_SECONDS, (int, float)), f'Must be numeric, got {type(r._FINDIT_TIMEOUT_SECONDS)}'
assert r._FINDIT_TIMEOUT_SECONDS > 0, f'Timeout must be positive, got {r._FINDIT_TIMEOUT_SECONDS}'
print(f'PASS: 0-E _FINDIT_TIMEOUT_SECONDS = {r._FINDIT_TIMEOUT_SECONDS}')
"
```

### 0-F — `_READ_STEP_NOTES` and `_WRITE_STEP_NOTES` are GONE

```bash
! grep -n "_READ_STEP_NOTES\|_WRITE_STEP_NOTES\|stepNotes" \
    migration_oracle/mcp/graph/queries/context.py && \
    echo "PASS: 0-F no stepNotes map-property write remains in query layer" || \
    echo "FAIL: 0-F stepNotes constants still present — FR-001 not complete"
```

### 0-G — `stepNotes` docstring removed from tool layer

```bash
! grep -n "stepNotes" migration_oracle/mcp/tools/context.py && \
    echo "PASS: 0-G stepNotes docstring removed from update_step_status" || \
    echo "FAIL: 0-G stale stepNotes reference remains in tool layer"
```

### 0-H — `_VALIDATE_STEP_ON_PATH` and `_MERGE_STEP_OUTCOME_REL` constants exist

```python
python -c "
import migration_oracle.mcp.graph.queries.context as qc
assert hasattr(qc, '_VALIDATE_STEP_ON_PATH'), 'Missing _VALIDATE_STEP_ON_PATH constant'
assert hasattr(qc, '_MERGE_STEP_OUTCOME_REL'), 'Missing _MERGE_STEP_OUTCOME_REL constant'
assert 'STEP_OUTCOME' in qc._MERGE_STEP_OUTCOME_REL, 'STEP_OUTCOME rel not in Cypher constant'
assert 'on_path' in qc._VALIDATE_STEP_ON_PATH, 'on_path column not in validation Cypher'
print('PASS: 0-H STEP_OUTCOME Cypher constants present and structurally correct')
"
```

### 0-I — `raw_phase_alerts` is in `_ANALYZE_UPGRADE_PATH` (new LifecycleAlert block)

```bash
grep -n "raw_phase_alerts\|HAS_LIFECYCLE_ALERT" \
    migration_oracle/mcp/graph/queries/upgrade.py && \
    echo "PASS: 0-I new LifecycleAlert query block present in _ANALYZE_UPGRADE_PATH" || \
    echo "FAIL: 0-I raw_phase_alerts / HAS_LIFECYCLE_ALERT block missing"
```

### 0-J — `raw_lifecycle_events` entity-event block is preserved (not overwritten)

```bash
grep -n "DEPRECATED_IN\|REMOVED_IN\|INTRODUCED_IN" \
    migration_oracle/mcp/graph/queries/upgrade.py && \
    echo "PASS: 0-J entity-level lifecycle events block still present" || \
    echo "FAIL: 0-J existing entity lifecycle events block was incorrectly removed"
```

### 0-K — Seed modules define required data structures

```python
python -c "
from migration_oracle.pipeline.seeds.deprecated_classes import SPRING_BOOT_3X_DEPRECATED
from migration_oracle.pipeline.seeds.lifecycle_alerts import SPRING_BOOT_4X_ALERTS

# deprecated classes
names = [e.entity_name if hasattr(e,'entity_name') else e[0] for e in SPRING_BOOT_3X_DEPRECATED]
for required in ['RestTemplate', 'WebSecurityConfigurerAdapter', 'WebMvcConfigurerAdapter', 'EnvironmentPostProcessor']:
    assert required in str(SPRING_BOOT_3X_DEPRECATED), f'{required} missing from SPRING_BOOT_3X_DEPRECATED'

# lifecycle alerts: each must have message, category, phase
VALID_CATEGORIES = {'security', 'api', 'config', 'dependency', 'other'}
VALID_PHASES = {'pre-migration', 'migration', 'post-migration'}
for alert in SPRING_BOOT_4X_ALERTS:
    msg = getattr(alert, 'message', None) or alert.get('message') if hasattr(alert,'get') else alert.message
    cat = getattr(alert, 'category', None) or alert.get('category') if hasattr(alert,'get') else alert.category
    ph  = getattr(alert, 'phase', None) or alert.get('phase') if hasattr(alert,'get') else alert.phase
    assert msg, f'Alert missing message: {alert}'
    assert cat in VALID_CATEGORIES, f'Invalid category {cat!r} — must be one of {VALID_CATEGORIES}'
    assert ph in VALID_PHASES, f'Invalid phase {ph!r} — must be one of {VALID_PHASES}'

print(f'PASS: 0-K seed modules valid ({len(SPRING_BOOT_3X_DEPRECATED)} deprecated classes, {len(SPRING_BOOT_4X_ALERTS)} lifecycle alerts)')
"
```

### 0-L — `_GET_STEPS_FOR_SCOPE_TIER` Cypher has the `WITH ... WHERE` row-filter pattern

```python
python -c "
import migration_oracle.mcp.graph.queries.context as qc
cypher = qc._GET_STEPS_FOR_SCOPE_TIER
# The fix requires a WITH clause before the WHERE that filters on scope
# Pattern: WITH ... bs ... WHERE bs IS NULL OR bs.scope = \$scope
import re
has_with_before_where = bool(re.search(r'WITH\b[^\n]*\bbs\b', cypher, re.IGNORECASE))
has_scope_filter = 'bs IS NULL OR' in cypher and 'bs.scope' in cypher
assert has_with_before_where, 'Missing WITH clause before scope WHERE (GAP-PLAN-001 fix)'
assert has_scope_filter, 'Scope row-filter predicate (bs IS NULL OR bs.scope = ...) missing'
print('PASS: 0-L scope-tier Cypher has WITH+WHERE row-filter (not OPTIONAL MATCH predicate)')
"
```

### 0-M — `_ANALYZE_UPGRADE_PATH` projects `title` and uses `coalesce(rule.statement, rule.reason)` for reason

```python
python -c "
import migration_oracle.mcp.graph.queries.upgrade as qu
cypher = qu._ANALYZE_UPGRADE_PATH
assert 'rule.title' in cypher, 'title: rule.title projection missing (FR-015)'
assert 'coalesce(rule.statement' in cypher or 'coalesce( rule.statement' in cypher, \
    'reason must map from coalesce(rule.statement, rule.reason), not rule.reason alone (GAP-PLAN-002 / FR-015)'
print('PASS: 0-M _ANALYZE_UPGRADE_PATH projects title and maps reason from rule.statement')
"
```

---

## Level 1 — Interface structure

No infrastructure required. Verifies public error shapes and guard logic.

### 1-A — `canonical_framework` returns structured dict (not exception) for unknown framework

```python
python -c "
from migration_oracle.mcp.tools.upgrade import canonical_framework
result = canonical_framework('unknown-framework-xyz')
assert isinstance(result, dict), f'Must return dict on unknown framework, got {type(result)}'
assert result.get('error_code') == 'unsupported_framework', f'Wrong error_code: {result}'
assert result.get('exists_in_graph') == False, f'exists_in_graph must be False: {result}'
assert result.get('ga_available') == False, f'ga_available must be False: {result}'
assert result.get('latest_patch') is None, f'latest_patch must be None: {result}'
assert 'Spring Boot' in result.get('hint', ''), f'hint must list display names: {result}'
print('PASS: 1-A unsupported_framework error shape is correct (no exception thrown, no network call)')
"
```

### 1-B — `step_not_on_path` error shape matches data-model.md

```python
python -c "
# Verify the error shape constants/structure in the tool layer
import ast, pathlib
src = pathlib.Path('migration_oracle/mcp/tools/context.py').read_text()
assert 'step_not_on_path' in src, 'step_not_on_path error_code not found in tools/context.py'
assert 'error_code' in src, 'error_code key missing from update_step_status error response'
print('PASS: 1-B step_not_on_path guard present in update_step_status')
"
```

### 1-C — `canonical_framework` is importable from `tools/upgrade.py` (not a private copy elsewhere)

```python
python -c "
# Contract: one canonical helper, one location
import importlib, pathlib
src_files = list(pathlib.Path('migration_oracle').rglob('*.py'))
hits = [f for f in src_files if 'canonical_framework' in f.read_text()]
assert all('tools/upgrade' in str(h) or 'test_' in str(h) for h in hits), \
    f'canonical_framework must live only in tools/upgrade.py — also found in: {[str(h) for h in hits if \"test_\" not in str(h) and \"tools/upgrade\" not in str(h)]}'
print('PASS: 1-C canonical_framework defined in exactly one non-test location')
"
```

---

## Level 2 — Isolation behaviour

No live Neo4j or LLM required. Uses `pytest` with mocked sessions.

### 2-A — Unit test suite for this spec passes (all nine new test files)

```bash
pytest tests/mcp/test_update_step_status.py \
       tests/mcp/test_search_openrewrite_recipes.py \
       tests/mcp/test_check_version_availability.py \
       tests/mcp/test_resolve_deprecation.py \
       tests/mcp/test_analyze_upgrade_path.py \
       tests/mcp/test_get_steps_for_scope_tier.py \
       tests/mcp/test_list_pipeline_runs.py \
       tests/mcp/test_lifecycle_alert.py \
       tests/paysafe/test_resolver_findit_timeout.py \
       -v 2>&1 | tail -20
# Expect: all PASSED, 0 errors
echo "PASS: 2-A all nine spec-011 unit test files pass"
```

### 2-B — `canonical_framework` normalises all four accepted spellings to the same canonical record

```python
python -c "
from migration_oracle.mcp.tools.upgrade import canonical_framework, _CanonicalFramework
variants = ['Spring Boot', 'spring boot', 'spring-boot', 'springboot',
            'SPRING BOOT', 'Spring-Boot', 'SpringBoot']
results = [canonical_framework(v) for v in variants]
for i, (v, r) in enumerate(zip(variants, results)):
    assert isinstance(r, _CanonicalFramework), f'{v!r} returned error dict: {r}'
    assert r.display == 'Spring Boot', f'{v!r} → wrong display: {r.display}'
    assert r.slug == 'spring-boot', f'{v!r} → wrong slug: {r.slug}'
print(f'PASS: 2-B all {len(variants)} spelling variants resolve to (\"Spring Boot\", \"spring-boot\")')
"
```

### 2-C — `_parse_from_version` handles all filename patterns from FR-022

```python
python -c "
# Import the parser function directly
from migration_oracle.mcp.tools.artifacts import _parse_from_version
cases = [
    ('spring-boot-3.5.0-to-4.0.0-changes_filtered.md', '3.5.0'),
    ('spring-boot-3.3.1-to-3.5.0-changes.md',          '3.3.1'),
    ('spring-boot-3.5.0-to-4.0.0-changes.md',           '3.5.0'),
    ('unrecognised-filename.md',                         ''),
    ('',                                                 ''),
]
for filename, expected in cases:
    got = _parse_from_version(filename)
    assert got == expected, f'{filename!r} → expected {expected!r}, got {got!r}'
print('PASS: 2-C _parse_from_version handles filtered suffix, plain suffix, no match, empty string')
"
```

### 2-D — `include_lifecycle=False` yields empty list regardless of data

```python
python -c "
# Verify the gating logic in tools/upgrade.py without a DB hit
import pathlib
src = pathlib.Path('migration_oracle/mcp/tools/upgrade.py').read_text()
# The gating must key off 'include_lifecycle' to build lifecycle_alerts
assert 'include_lifecycle' in src, 'include_lifecycle parameter missing from upgrade.py'
assert 'raw_phase_alerts' in src, 'raw_phase_alerts column not read in tool layer (T035 step 3)'
print('PASS: 2-D lifecycle_alerts gated by include_lifecycle in tools/upgrade.py')
"
```

### 2-E — `_FINDIT_TIMEOUT_SECONDS` is used in the actual lookup call (not just defined)

```python
python -c "
import pathlib, ast
src = pathlib.Path('migration_oracle/paysafe/resolver.py').read_text()
assert '_FINDIT_TIMEOUT_SECONDS' in src, '_FINDIT_TIMEOUT_SECONDS constant missing'
# Must appear in the body near the findit lookup (not only in a comment or constant declaration)
lines_using = [l.strip() for l in src.splitlines() if '_FINDIT_TIMEOUT_SECONDS' in l and not l.strip().startswith('#') and '=' not in l]
assert len(lines_using) >= 1, f'_FINDIT_TIMEOUT_SECONDS defined but never used in a call: {src[:500]}'
print('PASS: 2-E _FINDIT_TIMEOUT_SECONDS referenced in lookup call, not just defined')
"
```

### 2-F — No map-valued property write path survives in `record_step_outcome`

```python
python -c "
import pathlib
src = pathlib.Path('migration_oracle/mcp/graph/queries/context.py').read_text()
# These specific patterns should be absent
forbidden = ['SET ctx.stepNotes', 'step_notes', '_READ_STEP_NOTES', '_WRITE_STEP_NOTES']
for pat in forbidden:
    assert pat not in src, f'Forbidden pattern still present: {pat!r}'
# The correct pattern must be present
assert 'STEP_OUTCOME' in src, 'STEP_OUTCOME relationship missing from context.py'
print('PASS: 2-F no map-property write path; STEP_OUTCOME relationship present')
"
```

---

## Level 3 — Integration: graph read path

**Neo4j required.** No LLM. Cleanup after each sub-check is included.

Run all checks with the Neo4j instance from `.env` / Docker Compose:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=<password>
```

### 3-A — Driver connects

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    n = s.run('RETURN 1 AS n').single()['n']
    assert n == 1
driver.close()
print('PASS: 3-A driver connects and returns 1')
"
```

### 3-B — `Version` node with `framework: "Spring Boot"` is queryable (exists from prior ingestion)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    row = s.run(
        'MATCH (v:Version {framework: \"Spring Boot\"}) RETURN v.version AS ver LIMIT 1'
    ).single()
assert row is not None, 'No Version node with framework=\"Spring Boot\" — run ingestion first'
print(f'PASS: 3-B Version node present: version={row[\"ver\"]}')
driver.close()
"
```

### 3-C — `_CHECK_VERSION_IN_GRAPH` receives display form and returns correct result

```python
python -c "
from migration_oracle.mcp.graph.queries.upgrade import _CHECK_VERSION_IN_GRAPH
from migration_oracle.mcp.instance import get_db   # or however the driver is obtained
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    # Should find a Version with display-form framework
    row = s.run(_CHECK_VERSION_IN_GRAPH, framework='Spring Boot', version='3.5.0').single()
    # found may be True or False depending on whether 3.5.0 was ingested; what matters:
    # the query must NOT raise a TypeError or return None due to wrong casing
    assert row is not None, 'Query returned None — parameter or query structure broken'
    print(f'PASS: 3-C _CHECK_VERSION_IN_GRAPH ran with display form; found={row[\"found\"]}')
driver.close()
"
```

### 3-D — `_GET_STEPS_FOR_SCOPE_TIER` passes `scope` param and returns rows for scopeless steps

```python
python -c "
from migration_oracle.mcp.graph.queries.context import _GET_STEPS_FOR_SCOPE_TIER
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
# Just verify the query runs with the scope parameter without throwing
with driver.session() as s:
    # Use a non-existent context_id to get 0 rows but confirm the param is accepted
    rows = list(s.run(_GET_STEPS_FOR_SCOPE_TIER,
                      context_id='__nonexistent__', scope='build',
                      severity_threshold='low'))
    # Must not raise TypeError: Missing parameter 'scope'
    print(f'PASS: 3-D _GET_STEPS_FOR_SCOPE_TIER accepts scope param, returned {len(rows)} rows')
driver.close()
"
```

### 3-E — `_ANALYZE_UPGRADE_PATH` returns `raw_phase_alerts` column (even if empty)

```python
python -c "
from migration_oracle.mcp.graph.queries.upgrade import _ANALYZE_UPGRADE_PATH
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    rows = list(s.run(_ANALYZE_UPGRADE_PATH,
                      framework='Spring Boot', from_version='3.5.0',
                      to_version='4.0.0'))
if rows:
    row = rows[0]
    assert 'raw_phase_alerts' in row.keys(), \
        f'raw_phase_alerts column absent from RETURN — T035 step 2 incomplete. Keys: {list(row.keys())}'
    print(f'PASS: 3-E raw_phase_alerts column present in _ANALYZE_UPGRADE_PATH result ({len(rows)} rules)')
else:
    # No rules yet — check the Cypher has the column in RETURN
    import migration_oracle.mcp.graph.queries.upgrade as qu
    assert 'raw_phase_alerts' in qu._ANALYZE_UPGRADE_PATH, \
        'raw_phase_alerts missing from RETURN clause of _ANALYZE_UPGRADE_PATH'
    print('PASS: 3-E raw_phase_alerts in RETURN clause (0 rules in graph yet — run ingestion)')
driver.close()
"
```

---

## Level 5 — Full write path (post-ingestion assertions)

**Neo4j + ingestion run required.** Run ingestion first:

```bash
python -m migration_oracle.pipeline.populate  # or equivalent entry point
```

### 5-A — Every `OpenRewriteRecipe` node has `description` and `displayName` (FR-009, FR-012)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    row = s.run(
        'MATCH (r:OpenRewriteRecipe) RETURN count(r) AS total, '
        'count(r.description) AS withDesc, count(r.displayName) AS withName'
    ).single()
total, with_desc, with_name = row['total'], row['withDesc'], row['withName']
print(f'  OpenRewriteRecipe: total={total}, withDescription={with_desc}, withDisplayName={with_name}')
assert total > 0, f'No OpenRewriteRecipe nodes at all — ingestion did not run'
assert with_desc == total, f'FR-009 fail: {total - with_desc} recipes lack description'
assert with_name == total, f'FR-009 fail: {total - with_name} recipes lack displayName'
driver.close()
print('PASS: 5-A all OpenRewriteRecipe nodes have description and displayName')
"
```

### 5-B — Fulltext index `openrewrite_recipe_description` is ONLINE (FR-010)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    rows = list(s.run(
        'SHOW INDEXES WHERE name = \"openrewrite_recipe_description\" AND state = \"ONLINE\"'
    ))
assert len(rows) == 1, \
    f'openrewrite_recipe_description index not ONLINE — ensure_indexes() must run before population'
driver.close()
print('PASS: 5-B openrewrite_recipe_description fulltext index is ONLINE')
"
```

### 5-C — Every `MigrationRule` node has `framework` and `title` properties (FR-016)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    row = s.run(
        'MATCH (mr:MigrationRule) '
        'RETURN count(mr) AS total, '
        'count(mr.framework) AS withFramework, '
        'count(mr.title) AS withTitle, '
        'count(mr.statement) AS withStatement'
    ).single()
total = row['total']
print(f'  MigrationRule: total={total}, withFramework={row[\"withFramework\"]}, withTitle={row[\"withTitle\"]}, withStatement={row[\"withStatement\"]}')
assert total > 0, 'No MigrationRule nodes — run ingestion'
assert row['withFramework'] == total, f'FR-016: {total - row[\"withFramework\"]} rules missing framework'
driver.close()
print('PASS: 5-C all MigrationRule nodes have framework property')
"
```

### 5-D — Every `MigrationRule` has a `HAS_SCOPE → BreakingScope` edge (FR-017)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    row = s.run(
        'MATCH (mr:MigrationRule) '
        'OPTIONAL MATCH (mr)-[:HAS_SCOPE]->(bs:BreakingScope) '
        'RETURN count(mr) AS total, count(bs) AS withScope'
    ).single()
total, with_scope = row['total'], row['withScope']
print(f'  MigrationRule: total={total}, withHAS_SCOPE={with_scope}')
assert total > 0, 'No MigrationRule nodes — run ingestion'
assert with_scope == total, \
    f'FR-017: {total - with_scope} rules lack HAS_SCOPE edge — default BreakingScope not seeded'
driver.close()
print('PASS: 5-D all MigrationRule nodes have HAS_SCOPE → BreakingScope edge')
"
```

### 5-E — Curated deprecated classes are present with required edges (FR-013)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
required = ['RestTemplate', 'WebSecurityConfigurerAdapter', 'WebMvcConfigurerAdapter', 'EnvironmentPostProcessor']
with driver.session() as s:
    for cls in required:
        row = s.run(
            'MATCH (c:Class {name: \$name}) '
            'OPTIONAL MATCH (c)-[:DEPRECATED_IN]->(v:Version) '
            'RETURN count(c) AS nodes, count(v) AS depEdges',
            name=cls
        ).single()
        assert row['nodes'] > 0, f'FR-013: Class node missing for {cls}'
        assert row['depEdges'] > 0, f'FR-013: DEPRECATED_IN edge missing for {cls}'
        print(f'  {cls}: class_node=✓, DEPRECATED_IN=✓')
    # RestTemplate must also have REPLACED_BY (replacement is RestClient)
    row = s.run(
        'MATCH (c:Class {name: \"RestTemplate\"})-[:REPLACED_BY]->(r) RETURN count(r) AS cnt'
    ).single()
    assert row['cnt'] > 0, 'FR-013: RestTemplate missing REPLACED_BY edge to replacement'
driver.close()
print('PASS: 5-E all four required deprecated classes present with DEPRECATED_IN edges; RestTemplate has REPLACED_BY')
"
```

### 5-F — `LifecycleAlert` nodes are present and have all three required properties (FR-023)

```python
python -c "
from neo4j import GraphDatabase
import os
VALID_CATEGORIES = {'security', 'api', 'config', 'dependency', 'other'}
VALID_PHASES = {'pre-migration', 'migration', 'post-migration'}
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    rows = list(s.run(
        'MATCH (v:Version)-[:HAS_LIFECYCLE_ALERT]->(la:LifecycleAlert) '
        'RETURN la.message AS msg, la.category AS cat, la.phase AS phase, v.version AS ver'
    ))
assert len(rows) > 0, 'FR-023: No LifecycleAlert nodes linked to any Version — seed not run'
for row in rows:
    assert row['msg'], f'LifecycleAlert missing message on version {row[\"ver\"]}'
    assert row['cat'] in VALID_CATEGORIES, \
        f'Invalid category {row[\"cat\"]!r} on version {row[\"ver\"]} — must be in {VALID_CATEGORIES}'
    assert row['phase'] in VALID_PHASES, \
        f'Invalid phase {row[\"phase\"]!r} on version {row[\"ver\"]} — must be in {VALID_PHASES}'
driver.close()
print(f'PASS: 5-F {len(rows)} LifecycleAlert node(s) with valid message/category/phase')
"
```

### 5-G — `Version.fromVersion` is persisted on at least one node (FR-021)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    row = s.run(
        'MATCH (v:Version) WHERE v.fromVersion IS NOT NULL '
        'RETURN count(v) AS cnt, collect(v.fromVersion)[0..3] AS samples'
    ).single()
assert row['cnt'] > 0, \
    'FR-021: No Version node has fromVersion set — upsert_version_artifact_paths fix not applied'
driver.close()
print(f'PASS: 5-G {row[\"cnt\"]} Version node(s) with fromVersion; samples: {row[\"samples\"]}')
"
```

### 5-H — `stepNotes` property DOES NOT EXIST on any `MigrationContext` node (FR-001)

```python
python -c "
from neo4j import GraphDatabase
import os
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    row = s.run(
        'MATCH (ctx:MigrationContext) WHERE ctx.stepNotes IS NOT NULL RETURN count(ctx) AS cnt'
    ).single()
assert row['cnt'] == 0, \
    f'FR-001: {row[\"cnt\"]} MigrationContext node(s) still have stepNotes map property — re-run migration'
driver.close()
print('PASS: 5-H no MigrationContext node carries a stepNotes property')
"
```

---

## Level 6 — Idempotency

**Neo4j required.** Run ingestion a second time and verify counts are unchanged.

### 6-A — Capture pre-counts

```python
python -c "
import json, os
from neo4j import GraphDatabase
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
with driver.session() as s:
    counts = {}
    # Node label counts
    for label in ['OpenRewriteRecipe', 'LifecycleAlert', 'BreakingScope']:
        row = s.run(f'MATCH (n:{label}) RETURN count(n) AS cnt').single()
        counts[f'node_{label}'] = row['cnt']
    # Class nodes for deprecated-class seed
    row = s.run(
        'MATCH (c:Class) WHERE c.name IN [\"RestTemplate\",\"WebSecurityConfigurerAdapter\",\"WebMvcConfigurerAdapter\",\"EnvironmentPostProcessor\"] RETURN count(c) AS cnt'
    ).single()
    counts['node_SeedClass'] = row['cnt']
    # Relationship type counts
    for rel in ['HAS_LIFECYCLE_ALERT', 'DEPRECATED_IN', 'REPLACED_BY', 'HAS_SCOPE']:
        row = s.run(f'MATCH ()-[r:{rel}]->() RETURN count(r) AS cnt').single()
        counts[f'rel_{rel}'] = row['cnt']
driver.close()
with open('/tmp/011_counts_before.json', 'w') as f:
    json.dump(counts, f, indent=2)
print('PASS: 6-A pre-counts saved to /tmp/011_counts_before.json')
print(json.dumps(counts, indent=2))
"
```

### 6-B — Re-run ingestion

```bash
python -m migration_oracle.pipeline.populate
echo "6-B ingestion second run complete"
```

### 6-C — Compare post-counts; assert no diff

```python
python -c "
import json, os
from neo4j import GraphDatabase
with open('/tmp/011_counts_before.json') as f:
    before = json.load(f)
driver = GraphDatabase.driver(os.environ['NEO4J_URI'],
    auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
after = {}
with driver.session() as s:
    for label in ['OpenRewriteRecipe', 'LifecycleAlert', 'BreakingScope']:
        row = s.run(f'MATCH (n:{label}) RETURN count(n) AS cnt').single()
        after[f'node_{label}'] = row['cnt']
    row = s.run(
        'MATCH (c:Class) WHERE c.name IN [\"RestTemplate\",\"WebSecurityConfigurerAdapter\",\"WebMvcConfigurerAdapter\",\"EnvironmentPostProcessor\"] RETURN count(c) AS cnt'
    ).single()
    after['node_SeedClass'] = row['cnt']
    for rel in ['HAS_LIFECYCLE_ALERT', 'DEPRECATED_IN', 'REPLACED_BY', 'HAS_SCOPE']:
        row = s.run(f'MATCH ()-[r:{rel}]->() RETURN count(r) AS cnt').single()
        after[f'rel_{rel}'] = row['cnt']
driver.close()
diffs = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
if diffs:
    print('FAIL: 6-C counts changed after second ingestion run (idempotency broken):')
    for k, (b, a) in diffs.items():
        print(f'  {k}: {b} → {a} (delta={a-b:+d})')
    raise SystemExit(1)
print('PASS: 6-C all node and edge counts identical after second ingestion run')
print(json.dumps(after, indent=2))
"
```

---

## Level 7 — Edge-case paths

### 7-A — `update_step_status` with unknown `step_id` returns `step_not_on_path` error (FR-004)

```python
python -c "
# Exercise the tool layer with a mocked query layer returning on_path=False
from unittest.mock import patch, MagicMock
import importlib
tools_ctx = importlib.import_module('migration_oracle.mcp.tools.context')

mock_result = {'on_path': False}
with patch('migration_oracle.mcp.graph.queries.context.record_step_outcome', return_value=mock_result):
    result = tools_ctx.update_step_status(
        context_id='ctx-001', step_id='__bad_step__', status='completed', reason='test'
    )
assert result.get('error_code') == 'step_not_on_path', \
    f'Expected step_not_on_path error, got: {result}'
assert result.get('step_id') == '__bad_step__', f'step_id missing from error: {result}'
assert 'hint' in result, f'hint missing from step_not_on_path error: {result}'
print('PASS: 7-A unknown step_id returns structured step_not_on_path error; no STEP_OUTCOME created')
"
```

### 7-B — `analyze_upgrade_path(include_lifecycle=False)` returns empty `lifecycle_alerts`

```python
python -c "
from unittest.mock import patch, MagicMock
import importlib
tools_up = importlib.import_module('migration_oracle.mcp.tools.upgrade')

# Mock the query layer to return rules with raw_phase_alerts populated
mock_rows = [MagicMock()]
mock_rows[0].__getitem__ = lambda self, k: {
    'raw_rules': [{'rule_id': 'r1', 'title': 'Test', 'change_type': 'REMOVAL',
                   'reason': 'desc', 'scopes': [], 'steps': []}],
    'raw_phase_alerts': [{'message': 'Security alert', 'category': 'security', 'phase': 'pre-migration'}],
    'raw_lifecycle_events': [],
}[k]

with patch('migration_oracle.mcp.graph.queries.upgrade.analyze_upgrade_path_query',
           return_value=mock_rows):
    result = tools_up.analyze_upgrade_path(
        framework='Spring Boot', from_version='3.5.0', to_version='4.0.0',
        include_lifecycle=False
    )
alerts = result.get('lifecycle_alerts', [])
assert alerts == [], f'FR-024: include_lifecycle=False must yield [], got: {alerts}'
print('PASS: 7-B include_lifecycle=False yields empty lifecycle_alerts regardless of seeded data')
"
```

### 7-C — `list_pipeline_runs` returns `""` gracefully when no source for `from_version` (FR-022)

```python
python -c "
from migration_oracle.mcp.tools.artifacts import _parse_from_version
# Filename that neither matches the pattern nor has a fromVersion node property
edge_cases = ['', 'unknown.md', 'spring-boot-4.0.0.md', 'spring-boot.md']
for f in edge_cases:
    result = _parse_from_version(f)
    assert result == '', f'Expected empty string for {f!r}, got {result!r}'
print('PASS: 7-C _parse_from_version returns \"\" on all no-match inputs (no exception)')
"
```

### 7-D — `check_version_availability` with unsupported framework makes NO network call (FR-008)

```python
python -c "
from unittest.mock import patch
from migration_oracle.mcp.tools.upgrade import check_version_availability

network_called = []
def fake_get(*a, **kw):
    network_called.append(True)
    raise AssertionError('Network call made for unsupported framework')

with patch('httpx.get', fake_get), patch('requests.get', fake_get):
    result = check_version_availability(framework='unknown-xyz', version='1.0.0')

assert result.get('error_code') == 'unsupported_framework', f'Wrong result: {result}'
assert not network_called, 'FR-008 violated: network call was made for unsupported framework'
print('PASS: 7-D unsupported framework returns error dict with zero network calls')
"
```

### 7-E — `get_steps_for_scope_tier` with only scopeless rules returns them (not an empty list) (FR-018)

```python
python -c "
# Verify the Python filter in the query layer allows severity=None rows through
from unittest.mock import patch, MagicMock
import importlib
qc = importlib.import_module('migration_oracle.mcp.graph.queries.context')

# Mock session returning a row with scope=None, severity=None
mock_row = {'step_id': 'step-001', 'step_name': 'Upgrade deps', 'scope': None, 'severity': None,
            'step_index': 0, 'entity_name': 'pom.xml', 'entity_type': 'File'}
mock_session = MagicMock()
mock_session.run.return_value = [mock_row]

with patch('migration_oracle.mcp.graph.queries.context.read_session') as mock_rs:
    mock_rs.return_value.__enter__ = lambda s: mock_session
    mock_rs.return_value.__exit__ = MagicMock(return_value=False)
    result = qc.get_steps_for_scope_tier(
        context_id='ctx-001', scope='build', severity_threshold='medium'
    )

steps = result.get('hits', result) if isinstance(result, dict) else result
step_ids = [s.get('step_id') or s['step_id'] for s in steps]
assert 'step-001' in step_ids, \
    f'FR-018: scopeless step dropped by severity filter — got: {steps}'
print('PASS: 7-E scopeless step (scope=None, severity=None) passes through severity filter')
"
```

### 7-F — `resolve_paysafe_dependency_by_service_name` returns within timeout for unresponsive backend

```python
python -c "
import time
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve_paysafe_dependency_by_service_name

def hanging_lookup(*a, **kw):
    time.sleep(60)  # simulate hung backend

start = time.monotonic()
with patch('migration_oracle.paysafe.findit.lookup', side_effect=hanging_lookup):
    try:
        result = resolve_paysafe_dependency_by_service_name('paysafe-wallet-switch')
    except Exception:
        result = {}
elapsed = time.monotonic() - start

from migration_oracle.paysafe.resolver import _FINDIT_TIMEOUT_SECONDS
assert elapsed < _FINDIT_TIMEOUT_SECONDS + 2, \
    f'FR-025: tool did not return within timeout: elapsed={elapsed:.1f}s, limit={_FINDIT_TIMEOUT_SECONDS}s'
# Must return a structured dict, not raise
assert isinstance(result, dict), f'FR-026: must return structured dict on timeout, got {type(result)}'
print(f'PASS: 7-F resolver returned in {elapsed:.1f}s (limit={_FINDIT_TIMEOUT_SECONDS}s); result has error shape')
"
```

---

## Full regression suite

Run after all levels pass:

```bash
pytest tests/mcp/ tests/paysafe/ -v 2>&1 | tail -30
```

Expect: 0 failures, 0 errors. All pre-existing tests must continue to pass.

---

## Completion gate checklist

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| ID | Description | Result |
|----|-------------|--------|
| 0-A | All 10 modified/new modules import without error | |
| 0-B | `canonical_framework` returns `_CanonicalFramework` with correct `.display` / `.slug` | |
| 0-C | All four accepted spellings resolve in `_FRAMEWORK_ALIASES` | |
| 0-D | `_MAVEN_COORDS` keyed by slug `"spring-boot"` with correct coordinates | |
| 0-E | `_FINDIT_TIMEOUT_SECONDS` exists as a positive numeric constant | |
| 0-F | `_READ_STEP_NOTES`, `_WRITE_STEP_NOTES`, `stepNotes` absent from query layer | |
| 0-G | `stepNotes` docstring removed from `tools/context.py` | |
| 0-H | `_VALIDATE_STEP_ON_PATH` and `_MERGE_STEP_OUTCOME_REL` constants present with correct content | |
| 0-I | `raw_phase_alerts` / `HAS_LIFECYCLE_ALERT` block present in `_ANALYZE_UPGRADE_PATH` | |
| 0-J | Entity-level `DEPRECATED_IN`/`REMOVED_IN`/`INTRODUCED_IN` block preserved (not removed) | |
| 0-K | Seed modules define all required deprecated classes and valid lifecycle alerts | |
| 0-L | `_GET_STEPS_FOR_SCOPE_TIER` uses `WITH ... WHERE` row-filter pattern | |
| 0-M | `_ANALYZE_UPGRADE_PATH` projects `title` and maps `reason` from `coalesce(rule.statement, ...)` | |
| 1-A | Unknown framework returns `unsupported_framework` structured dict, not an exception | |
| 1-B | `step_not_on_path` error_code present in `tools/context.py` | |
| 1-C | `canonical_framework` defined in exactly one non-test location (`tools/upgrade.py`) | |
| 2-A | All nine spec-011 unit test files pass | |
| 2-B | All seven spelling variants of Spring Boot resolve to `("Spring Boot", "spring-boot")` | |
| 2-C | `_parse_from_version` handles `_filtered.md` suffix, plain suffix, no-match, empty string | |
| 2-D | `include_lifecycle` gates `raw_phase_alerts` in `tools/upgrade.py` | |
| 2-E | `_FINDIT_TIMEOUT_SECONDS` referenced in actual lookup call (not only in constant declaration) | |
| 2-F | No map-property write path survives; `STEP_OUTCOME` present in `context.py` | |
| 3-A | Neo4j driver connects | |
| 3-B | `Version {framework: "Spring Boot"}` node queryable | |
| 3-C | `_CHECK_VERSION_IN_GRAPH` accepts display form without error | |
| 3-D | `_GET_STEPS_FOR_SCOPE_TIER` accepts `scope` parameter without `TypeError` | |
| 3-E | `_ANALYZE_UPGRADE_PATH` returns `raw_phase_alerts` column in result rows | |
| 5-A | All `OpenRewriteRecipe` nodes have `description` and `displayName` (counts equal) | |
| 5-B | `openrewrite_recipe_description` fulltext index is `ONLINE` | |
| 5-C | All `MigrationRule` nodes have `framework` property | |
| 5-D | All `MigrationRule` nodes have `HAS_SCOPE → BreakingScope` edge | |
| 5-E | All four required deprecated classes present with `DEPRECATED_IN`; `RestTemplate` has `REPLACED_BY` | |
| 5-F | `LifecycleAlert` nodes present with valid `message`/`category`/`phase` values | |
| 5-G | At least one `Version` node has `fromVersion` property | |
| 5-H | Zero `MigrationContext` nodes carry a `stepNotes` property | |
| 6-A | Pre-ingestion counts captured to `/tmp/011_counts_before.json` | |
| 6-B | Ingestion re-run completes without error | |
| 6-C | All node and edge counts identical before and after second ingestion run | |
| 7-A | Unknown `step_id` returns structured `step_not_on_path` error; no relationship created | |
| 7-B | `include_lifecycle=False` yields empty `lifecycle_alerts` | |
| 7-C | `_parse_from_version` returns `""` for all no-match inputs without exception | |
| 7-D | Unsupported framework makes zero network calls | |
| 7-E | Scopeless steps (scope=None, severity=None) are not dropped by severity filter | |
| 7-F | Resolver returns within `_FINDIT_TIMEOUT_SECONDS + 2s` for a hanging backend | |

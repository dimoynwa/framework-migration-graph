# Quickstart: Oracle Contract Fixes — Local Verification

**Feature**: `012-oracle-contract-fixes`
**Target**: Neo4j 5, Python 3.11+

This guide shows how to stand up the graph, seed fixture data, and run before/after verification for each of the six work-streams.

---

## Prerequisites

```bash
# 1. Clone and install
uv sync                          # installs all dependencies into .venv

# 2. Set environment
cp .env.example .env             # or set NEO4J_PASSWORD manually
export NEO4J_PASSWORD=testpass

# 3. Start Neo4j
docker compose up -d neo4j
# wait for health check:
docker compose ps neo4j          # Status should be "healthy"
```

---

## Seed the Graph (Fixture Context)

Run the pipeline to populate the graph with Spring Boot rules and steps:

```bash
uv run migration-oracle populate \
    --framework "Spring Boot" \
    --from-version 2.7.0 \
    --to-version 3.2.0
```

Or load a minimal fixture context for unit tests (no pipeline required):

```bash
uv run pytest tests/mcp/conftest.py -v    # loads conftest fixtures into a test database
```

---

## Run the Full Test Suite (Baseline)

```bash
uv run pytest tests/ -v --tb=short
```

All tests must pass **before** and **after** applying the fixes (SC-015).

---

## Work-Stream Verification

### WS1 — Version Arithmetic

**Files changed**: `migration_oracle/mcp/skills/framework_migration_version_map.md`

**Before check**: Verify current wrong formula and computed values:
```bash
grep "MAJOR \* 10000" migration_oracle/mcp/skills/framework_migration_version_map.md
# Expected: matches (shows old formula)
grep "20500\|30000\|140000" migration_oracle/mcp/skills/framework_migration_version_map.md
# Expected: old sortable values present
```

**After check**: Verify corrected formula and values:
```bash
grep "1_000_000" migration_oracle/mcp/skills/framework_migration_version_map.md
# Expected: formula present, old formula absent

# Formula property test (run in Python):
python3 -c "
def f(major, minor, patch): return major * 1_000_000 + minor * 1_000 + patch
assert f(3,10,0) > f(3,9,0), 'Inversion present!'
print('OK: f(3,10,0)=%d > f(3,9,0)=%d' % (f(3,10,0), f(3,9,0)))
"
# Expected: OK: f(3,10,0)=3010000 > f(3,9,0)=3009000

# Verify every row matches formula:
python3 -c "
import re, pathlib
text = pathlib.Path('migration_oracle/mcp/skills/framework_migration_version_map.md').read_text()
for m in re.finditer(r'\|\s+(\d+)\.(\d+)\.(\d+)\s+\|\s+(\d+)\s+\|', text):
    maj, min_, pat, stored = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    expected = maj * 1_000_000 + min_ * 1_000 + pat
    assert stored == expected, f'{maj}.{min_}.{pat}: stored={stored}, expected={expected}'
print('All rows pass')
"

# Check freshness fields
grep "Last Updated\|spring.io\|angular.io" migration_oracle/mcp/skills/framework_migration_version_map.md
# Expected: both present
```

---

### WS2 — Graph-State Contract

**Files changed**: `migration_oracle/mcp/graph/queries/context.py`, `migration_oracle/mcp/tools/context.py`

**Before check** (run against a live Neo4j instance):
```bash
uv run pytest tests/mcp/test_update_step_status.py -v
# Note: tests that check STEP_OUTCOME will fail before the fix
```

**After check**:
```bash
# Run existing tests (must all pass — SC-015)
uv run pytest tests/mcp/test_update_step_status.py -v

# Manual Cypher verification — STEP_OUTCOME exists after recording:
# In cypher-shell or Neo4j Browser:
# MATCH (ctx:MigrationContext)-[so:STEP_OUTCOME]->(step:MigrationStep)
# RETURN ctx.projectId, so.status, so.reason, so.updatedAt, step.summary
# LIMIT 5
# Expected: non-empty result after calling update_step_status

# Idempotency check — record same step twice, count relationships:
# MATCH (ctx)-[so:STEP_OUTCOME]->(step) WHERE elementId(ctx)=$ctx_id AND elementId(step)=$step_id
# RETURN count(so)
# Expected: 1 (not 2)

# Abandoned context:
# Via MCP tool: close_migration_context(context_id=X, final_status="abandoned")
# MATCH (ctx:MigrationContext) WHERE elementId(ctx)=$id RETURN ctx.status
# Expected: "abandoned"
```

---

### WS3 — Query Correctness

**Files changed**: `migration_oracle/mcp/graph/queries/upgrade.py`, `migration_oracle/mcp/tools/context.py`

**Before check**:
```bash
uv run pytest tests/mcp/test_get_steps_for_scope_tier.py tests/mcp/test_upgrade.py -v
```

**After check** — severity filter:
```bash
uv run pytest tests/mcp/test_get_steps_for_scope_tier.py -v

# Manual: invalid threshold must return error:
python3 -c "
from migration_oracle.mcp.tools.context import get_steps_for_scope_tier
result = get_steps_for_scope_tier(context_id='some-id', scope='api-surface', severity_threshold='bogus')
assert result['status'] == 'error', f'Expected error, got: {result}'
assert result['error_code'] == 'invalid_severity_threshold'
print('OK: invalid threshold rejected')
"

# Manual: high threshold must exclude low/medium steps:
# Call get_steps_for_scope_tier with severity_threshold="high"
# Assert: no returned step has severity in {"low", "medium"}
```

**After check** — recipe join:
```bash
uv run pytest tests/mcp/test_upgrade.py -v

# If a MigrationStep with AUTOMATED_BY edge exists in your test graph:
python3 -c "
from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path
result = analyze_upgrade_path(framework='Spring Boot', current_version='2.7.0', target_version='3.2.0', include_recipes=True)
rules_with_recipes = [r for r in result['rules'] if r.get('recipes')]
print(f'Rules with non-empty recipes: {len(rules_with_recipes)}')
# Expected > 0 if any AUTOMATED_BY edge exists in the graph
"
```

---

### WS4 — Tool API Alignment

**Files changed**: `migration_oracle/mcp/graph/queries/deprecation.py`, `migration_oracle/mcp/tools/deprecation.py`, `migration_oracle/mcp/graph/queries/search.py`, `migration_oracle/mcp/tools/community.py`

**Before check**:
```bash
uv run pytest tests/mcp/test_deprecation.py tests/mcp/test_openrewrite_filters.py tests/mcp/test_search.py -v
```

**After check**:
```bash
uv run pytest tests/mcp/test_deprecation.py tests/mcp/test_openrewrite_filters.py tests/mcp/test_search.py -v

# entity_name field — must not be null:
python3 -c "
from migration_oracle.mcp.tools.deprecation import resolve_deprecation
r = resolve_deprecation(entity_name='org.springframework.boot.env.EnvironmentPostProcessor')
assert r['status'] in ('ok', 'not_found')
if r['status'] == 'ok':
    assert r['entity_name'] is not None and r['entity_name'] != ''
    print('OK: entity_name =', r['entity_name'])
"

# submit_migration_insight — duplicate path returns insight_id=None:
python3 -c "
from migration_oracle.mcp.tools.community import submit_migration_insight
# submit twice with same statement
r1 = submit_migration_insight(statement='Test insight for verification', spring_boot_version='3.2.0')
r2 = submit_migration_insight(statement='Test insight for verification', spring_boot_version='3.2.0')
assert r2['status'] == 'duplicate'
assert r2['insight_id'] is None, f'Expected None, got {r2[\"insight_id\"]}'
assert r2['duplicate_of'] is not None
print('OK: duplicate path returns insight_id=None, duplicate_of=', r2['duplicate_of'])
"
```

---

### WS5 — Resumability

**Files changed**: `migration_oracle/mcp/tools/context.py` (new tool), `migration_oracle/mcp/graph/queries/context.py` (new Cypher), `migration_oracle/mcp/skills/framework_migration_main.md`

**Before check**:
```bash
uv run pytest tests/mcp/ -k "queried_entity or resumab" -v
# Expected: no tests match yet (new functionality)
```

**After check**:
```bash
# Verify update_queried_entity tool exists and writes correctly:
python3 -c "
from migration_oracle.mcp.tools.context import create_migration_context, update_queried_entity
ctx = create_migration_context(project_id='qs-test', from_version='2.7.0', to_version='3.2.0', framework='Spring Boot')
ctx_id = ctx['context_id']
result = update_queried_entity(context_id=ctx_id, entity_name='org.example.Foo', result_summary='deprecated in 3.0')
assert result['status'] == 'ok'
print('OK: update_queried_entity returned', result)

# Read back:
from migration_oracle.graph.driver import read_session
with read_session() as s:
    row = s.run('MATCH (ctx:MigrationContext) WHERE elementId(ctx) = \$id RETURN ctx.queriedEntities AS qe', id=ctx_id).single()
import json
qe = json.loads(row['qe'])
assert 'org.example.Foo' in qe, f'Entity not found in queriedEntities: {qe}'
print('OK: entity cached in queriedEntities:', qe)
"

# Verify skill text mentions force_refresh:
grep -n "force_refresh\|force-refresh" migration_oracle/mcp/skills/framework_migration_main.md
# Expected: at least one match
```

---

### WS6 — Resilience

**Files changed**: `migration_oracle/mcp/skills/framework_migration_rollback.md` (new), `migration_oracle/mcp/skills/framework_migration_main.md`

**Before check**:
```bash
ls migration_oracle/mcp/skills/
# Expected: framework_migration_rollback.md NOT present
grep "skill://framework-migration/rollback" migration_oracle/mcp/skills/framework_migration_main.md
# Expected: no match (rollback URI not referenced)
```

**After check**:
```bash
ls migration_oracle/mcp/skills/
# Expected: framework_migration_rollback.md present

grep "skill://framework-migration/rollback" migration_oracle/mcp/skills/framework_migration_main.md
# Expected: at least one match (Loop III rollback path references the URI)

# Verify install_migration_skill picks up the rollback skill:
python3 -c "
from migration_oracle.mcp.tools.install import _SKILLS_DIR
skills = list(_SKILLS_DIR.glob('*.md'))
names = [s.name for s in skills]
assert 'framework_migration_rollback.md' in names, f'rollback skill not found: {names}'
print('OK: rollback skill present:', names)
"

# Check Loop IV stateless fallback section exists:
grep -n "STATELESS\|stateless.fallback\|stateless fallback" migration_oracle/mcp/skills/framework_migration_main.md
# Expected: at least one match
```

---

## Full Before/After Summary

```bash
# Full suite — run once before and once after all fixes:
uv run pytest tests/ -v --tb=short 2>&1 | tee /tmp/test-results.txt
grep -E "PASSED|FAILED|ERROR" /tmp/test-results.txt | wc -l
```

All counts must match between before and after runs (SC-015: no previously-passing test may fail).

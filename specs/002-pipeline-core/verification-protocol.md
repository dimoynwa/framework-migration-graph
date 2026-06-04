# Verification Protocol — `002-pipeline-core`

**Location**: `specs/002-pipeline-core/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound across levels.

---

## Prerequisites

| Requirement | How to check |
|-------------|-------------|
| `uv sync` clean | `uv sync && echo OK` |
| Neo4j or Memgraph reachable | `NEO4J_URI` set and database accepting connections |
| LLM credentials present | `MODEL_PROVIDER` and `MODEL_ID` (or Bedrock equivalents) set |
| `runs/` writable | `ls -la runs/` or create manually if absent |

Levels 0–3 require **no LLM and no database**. Levels 4–7 require both.

---

## Level 0 — Static checks

> No database. No LLM. These must pass before anything else is started.

### 0-A: Module imports

```bash
uv run python -c "from migration_oracle.pipeline._llm import get_llm"
uv run python -c "from migration_oracle.pipeline._cache import is_cached, mark_cached"
uv run python -c "from migration_oracle.pipeline.filters import run_filter"
uv run python -c "from migration_oracle.pipeline.extractor import run_extraction"
uv run python -c "from migration_oracle.pipeline.populator import SOURCE_SECTION_TO_RULE_TYPE, populate"
uv run python -c "from migration_oracle.graph.queries.pipeline import version_exists, upsert_version_artifact_paths, list_pipeline_runs"
uv run python -c "from migration_oracle.cli import app"
```

Any `ImportError` or `ModuleNotFoundError` means a module is missing or has a broken dependency. Fix before proceeding.

### 0-B: `SOURCE_SECTION_TO_RULE_TYPE` completeness

```bash
uv run python -c "
from migration_oracle.pipeline.populator import SOURCE_SECTION_TO_RULE_TYPE
expected = {
    'breaking_change', 'security_fix', 'component_upgrade', 'security_config',
    'behavioral', 'deprecation', 'new_capability'
}
actual = set(SOURCE_SECTION_TO_RULE_TYPE.keys())
missing = expected - actual
extra   = actual   - expected
assert not missing, f'Missing keys: {missing}'
assert not extra,   f'Unexpected keys: {extra}'
print('PASS: SOURCE_SECTION_TO_RULE_TYPE has exactly 7 entries')
"
```

### 0-C: `ruleType` mapping values

```bash
uv run python -c "
from migration_oracle.pipeline.populator import SOURCE_SECTION_TO_RULE_TYPE as M
assert M['breaking_change']   == 'breaking'
assert M['security_fix']      == 'mandatory_migration'
assert M['component_upgrade'] == 'mandatory_migration'
assert M['security_config']   == 'mandatory_migration'
assert M['behavioral']        == 'behavioral'
assert M['deprecation']       == 'deprecation'
assert M['new_capability']    == 'behavioral'
print('PASS: all ruleType values correct')
"
```

### 0-D: Retry constants

```bash
uv run python -c "
from migration_oracle.config import EXTRACTION_RATE_LIMIT_RETRIES, EXTRACTION_RETRY_BASE_DELAY
assert EXTRACTION_RATE_LIMIT_RETRIES == 3,   f'Got: {EXTRACTION_RATE_LIMIT_RETRIES}'
assert EXTRACTION_RETRY_BASE_DELAY   == 2.0, f'Got: {EXTRACTION_RETRY_BASE_DELAY}'
print('PASS: retry constants correct')
"
```

**Expected outcome**: All four checks print `PASS`. Zero tracebacks.

---

## Level 1 — CLI structure

> No database. No LLM.

### 1-A: Help text covers all required flags

```bash
uv run migration-oracle pipeline --help
```

Verify the following appear in the output:

- `--framework`
- `from_version` and `to_version` (positional)
- `--dry-run`
- `--force`
- `--force-extract`
- `--force-llm`
- `--output-md`
- `--output-filtered-md`
- `--output-json`
- `--skip-existing`

### 1-B: Unknown framework exits non-zero with supported key list

```bash
uv run migration-oracle pipeline --framework does-not-exist 1.0.0 2.0.0
echo "Exit code: $?"
```

Expected: non-zero exit code. Output must list the supported framework keys — not a Python traceback.

### 1-C: Missing `MODEL_PROVIDER` exits non-zero cleanly

```bash
MODEL_PROVIDER="" uv run migration-oracle pipeline --framework spring-boot 3.3.0 3.4.0 --dry-run
echo "Exit code: $?"
```

Expected: non-zero exit code with a clear error message. Not a bare `KeyError` or `AttributeError`.

**Expected outcome**: Correct flag descriptions in help, clean non-zero exits for both error cases.

---

## Level 2 — Artifact cache logic

> No database. No LLM.

### 2-A: Seed raw MD and prepare cache state

```bash
mkdir -p runs/raw runs/nodes runs/json

cat > runs/raw/spring-boot-3.3.0-to-3.4.0-changes.md << 'EOF'
## 3.3.0 → 3.4.0

| Impact | Title | Source | Jira |
|--------|-------|--------|------|
| 🔴 Breaking | `spring.datasource.url` renamed to `spring.datasource.jdbc-url` | https://example.com/1 | |
| 🟡 Deprecation | `SpringApplication.run()` array arg deprecated; use varargs | https://example.com/2 | |
EOF
```

### 2-B: Stale-artifact warning

```bash
echo "dummy filtered content" > runs/nodes/spring-boot-3.3.0-to-3.4.0-changes_filtered.md

uv run migration-oracle pipeline \
  --framework spring-boot 3.3.0 3.4.0 \
  --force-extract \
  --dry-run 2>&1 | grep -i "warn"

echo "Exit code: $?"
```

Expected:
- At least one warning line printed to stderr (contains "warn" case-insensitively)
- Exit code **0** — the warning must not abort the run

### 2-C: Cache reuse verified by mtime

> This check applies once Level 4 has produced real artifacts. Run it again after Level 4 completes.

```bash
MTIME_FILTERED=$(stat -c %Y runs/nodes/spring-boot-3.3.0-to-3.4.0-changes_filtered.md \
  2>/dev/null || stat -f %m runs/nodes/spring-boot-3.3.0-to-3.4.0-changes_filtered.md)

MTIME_JSON=$(stat -c %Y runs/json/spring-boot-3.3.0-to-3.4.0-entities.json \
  2>/dev/null || stat -f %m runs/json/spring-boot-3.3.0-to-3.4.0-entities.json)

uv run migration-oracle pipeline --framework spring-boot 3.3.0 3.4.0 --dry-run

MTIME_FILTERED_AFTER=$(stat -c %Y runs/nodes/spring-boot-3.3.0-to-3.4.0-changes_filtered.md \
  2>/dev/null || stat -f %m runs/nodes/spring-boot-3.3.0-to-3.4.0-changes_filtered.md)

MTIME_JSON_AFTER=$(stat -c %Y runs/json/spring-boot-3.3.0-to-3.4.0-entities.json \
  2>/dev/null || stat -f %m runs/json/spring-boot-3.3.0-to-3.4.0-entities.json)

[ "$MTIME_FILTERED" = "$MTIME_FILTERED_AFTER" ] \
  && echo "PASS: filtered MD not regenerated" \
  || echo "FAIL: filtered MD was overwritten"

[ "$MTIME_JSON" = "$MTIME_JSON_AFTER" ] \
  && echo "PASS: entities JSON not regenerated" \
  || echo "FAIL: entities JSON was overwritten"
```

**Expected outcome**: Warning printed, exit 0, file mtimes unchanged on second run.

---

## Level 3 — Graph connection

> Database required. No LLM.

### 3-A: Driver connects

```bash
uv run python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    result = s.run('RETURN 1 AS n').single()
    assert result['n'] == 1
print('PASS: graph driver connects')
"
```

### 3-B: `version_exists` returns `False` for unknown version

```bash
uv run python -c "
from migration_oracle.graph.queries.pipeline import version_exists
result = version_exists('spring-boot', '99.99.99')
assert result is False, f'Got: {result}'
print('PASS: version_exists returns False for unknown version')
"
```

### 3-C: `upsert_version_artifact_paths` writes all properties correctly

```bash
uv run python -c "
from migration_oracle.graph.queries.pipeline import upsert_version_artifact_paths
from migration_oracle.graph.driver import get_driver

upsert_version_artifact_paths(
    framework='spring-boot',
    version='3.4.0',
    raw_md_path='/tmp/raw.md',
    filtered_md_path='/tmp/filtered.md',
    entities_json_path='/tmp/entities.json',
)

with get_driver().session() as s:
    row = s.run(
        'MATCH (v:Version {framework: \$f, version: \$v}) RETURN v',
        f='spring-boot', v='3.4.0'
    ).single()
    assert row, 'Version node not found'
    v = row['v']
    assert v['rawMdPath']        == '/tmp/raw.md',       f'Got: {v[\"rawMdPath\"]}'
    assert v['filteredMdPath']   == '/tmp/filtered.md',  f'Got: {v[\"filteredMdPath\"]}'
    assert v['entitiesJsonPath'] == '/tmp/entities.json', f'Got: {v[\"entitiesJsonPath\"]}'
    assert v['sortableVersion']  == 3_004_000, \
        f'FAIL: sortableVersion={v[\"sortableVersion\"]} (expected 3004000)'

print('PASS: Version node has all three paths and correct sortableVersion')
"
```

### 3-D: `list_pipeline_runs` finds the test node

```bash
uv run python -c "
from migration_oracle.graph.queries.pipeline import list_pipeline_runs
runs = list_pipeline_runs(framework='spring-boot')
assert any(r['version'] == '3.4.0' for r in runs), f'Got: {runs}'
print('PASS: list_pipeline_runs finds the test Version node')
"
```

### 3-E: Cleanup

```bash
uv run python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    s.run(
        'MATCH (v:Version {framework: \$f, version: \$v}) DETACH DELETE v',
        f='spring-boot', v='3.4.0'
    )
print('Cleaned up test Version node')
"
```

**Expected outcome**: Driver connects, both query helpers return correct results, `sortableVersion` is 3004000.

---

## Level 4 — Full dry-run

> LLM required. Database required (for version-node absence check). No graph writes.

### 4-A: Seed raw MD

```bash
mkdir -p runs/raw

cat > runs/raw/spring-boot-3.3.0-to-3.4.0-changes.md << 'EOF'
## 3.3.0 → 3.4.0

| Impact | Title | Source | Jira |
|--------|-------|--------|------|
| 🔴 Breaking | `spring.datasource.url` renamed to `spring.datasource.jdbc-url` in `application.properties` | https://spring.io/blog/2024/breaking | |
| 🟡 Deprecation | `SpringApplication.run()` with array arg deprecated; use varargs overload | https://spring.io/blog/2024/deprecation | |
EOF
```

### 4-B: Run dry-run

```bash
uv run migration-oracle pipeline \
  --framework spring-boot 3.3.0 3.4.0 \
  --dry-run

echo "Exit code: $?"   # Must be 0
```

### 4-C: Artifact files exist

```bash
test -f runs/nodes/spring-boot-3.3.0-to-3.4.0-changes_filtered.md \
  && echo "PASS: filtered MD exists" \
  || echo "FAIL: filtered MD missing"

test -f runs/json/spring-boot-3.3.0-to-3.4.0-entities.json \
  && echo "PASS: entities JSON exists" \
  || echo "FAIL: entities JSON missing"
```

### 4-D: Filtered MD contains section headers

```bash
grep -E "(🔴|🟠|🟡|🔵)" \
  runs/nodes/spring-boot-3.3.0-to-3.4.0-changes_filtered.md \
  && echo "PASS: section headers present" \
  || echo "FAIL: no emoji section headers found"
```

### 4-E: Entities JSON is a valid `MigrationEntitiesBatch`

```bash
uv run python -c "
import json
from migration_oracle.models.entities import MigrationEntitiesBatch

with open('runs/json/spring-boot-3.3.0-to-3.4.0-entities.json') as f:
    data = json.load(f)

batch = MigrationEntitiesBatch(**data)
assert len(batch.entities) > 0, 'Empty entity list — extraction failed silently'
print(f'PASS: {len(batch.entities)} entities extracted, schema valid')
"
```

### 4-F: Dry-run did not write to the graph

```bash
uv run python -c "
from migration_oracle.graph.queries.pipeline import version_exists
assert not version_exists('spring-boot', '3.4.0'), \
    'FAIL: --dry-run wrote a Version node to the graph'
print('PASS: --dry-run did not write Version node')
"
```

### 4-G: Cache reuse (re-run Level 2-C now)

Run the mtime check from **Level 2-C** against the artifacts just produced.

**Expected outcome**: Exit 0, both artifact files exist, valid `MigrationEntitiesBatch` with at least one entity, no `Version` node in graph, mtimes unchanged on second run.

---

## Level 5 — Full graph write

> LLM required. Database required.

### 5-A: Full run

```bash
uv run migration-oracle pipeline \
  --framework spring-boot 3.3.0 3.4.0 \
  --force-llm

echo "Exit code: $?"   # Must be 0
```

### 5-B: Version node has all three path properties and correct `sortableVersion`

```bash
uv run python -c "
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    row = s.run(
        'MATCH (v:Version {framework: \$f, version: \$v}) RETURN v',
        f='spring-boot', v='3.4.0'
    ).single()
    assert row, 'FAIL: Version node not created'
    v = row['v']
    assert v.get('rawMdPath'),        'FAIL: rawMdPath missing'
    assert v.get('filteredMdPath'),   'FAIL: filteredMdPath missing'
    assert v.get('entitiesJsonPath'), 'FAIL: entitiesJsonPath missing'
    assert v['sortableVersion'] == 3_004_000, \
        f'FAIL: sortableVersion={v[\"sortableVersion\"]} (expected 3004000)'
print('PASS: Version node has all three paths and correct sortableVersion')
"
```

### 5-C: `MigrationRule` nodes linked with valid `ruleType`

```bash
uv run python -c "
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    result = s.run(
        '''MATCH (v:Version {framework: \$f, version: \$v})-[:INCLUDES_RULE]->(r:MigrationRule)
           RETURN count(r) AS n, collect(r.ruleType) AS types''',
        f='spring-boot', v='3.4.0'
    ).single()
    assert result['n'] > 0, 'FAIL: no MigrationRule nodes linked to Version'
    valid = {'breaking', 'mandatory_migration', 'behavioral', 'deprecation'}
    for rt in result['types']:
        assert rt in valid, f'FAIL: invalid ruleType: {rt}'
    print(f'PASS: {result[\"n\"]} MigrationRule nodes with valid ruleTypes: {set(result[\"types\"])}')
"
```

### 5-D: `MigrationStep` and `BreakingScope` nodes (OPTIONAL MATCH)

```bash
uv run python -c "
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    result = s.run(
        '''MATCH (v:Version {framework: \$f, version: \$v})-[:INCLUDES_RULE]->(r:MigrationRule)
           OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
           OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
           RETURN count(DISTINCT r)  AS rules,
                  count(DISTINCT s)  AS steps,
                  count(DISTINCT bs) AS scopes''',
        f='spring-boot', v='3.4.0'
    ).single()
    print(f'Rules: {result[\"rules\"]}, Steps: {result[\"steps\"]}, Scopes: {result[\"scopes\"]}')
    print('PASS: step/scope query executed without error (counts may be 0 for informational-only input)')
"
```

### 5-E: `entityClassification` is set and valid on all rules

```bash
uv run python -c "
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    rows = s.run(
        '''MATCH (v:Version {framework: \$f, version: \$v})-[:INCLUDES_RULE]->(r:MigrationRule)
           RETURN r.entityClassification AS ec''',
        f='spring-boot', v='3.4.0'
    ).data()
    valid = {'actionable', 'incomplete', 'informational'}
    for row in rows:
        assert row['ec'] in valid, f'FAIL: invalid entityClassification: {row[\"ec\"]}'
    print(f'PASS: all {len(rows)} rules have valid entityClassification')
"
```

### 5-F: `actionStep` not written on any new rule

```bash
uv run python -c "
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    result = s.run(
        '''MATCH (v:Version {framework: \$f, version: \$v})-[:INCLUDES_RULE]->(r:MigrationRule)
           WHERE r.actionStep IS NOT NULL
           RETURN count(r) AS n''',
        f='spring-boot', v='3.4.0'
    ).single()
    assert result['n'] == 0, \
        f'FAIL: {result[\"n\"]} new MigrationRule nodes have actionStep set'
    print('PASS: no new MigrationRule nodes have actionStep set')
"
```

**Expected outcome**: Exit 0, Version node with all three paths and `sortableVersion=3004000`, at least one rule with a valid `ruleType`, no `actionStep` on any new rule.

---

## Level 6 — Idempotency

> Requires Level 5 to have completed successfully.

### 6-A: Capture counts before second run

```bash
uv run python -c "
import json
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    nodes = s.run('''
        MATCH (v:Version {framework: \"spring-boot\", version: \"3.4.0\"})
        OPTIONAL MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)
        OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
        OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
        RETURN count(DISTINCT r)  AS rules,
               count(DISTINCT s)  AS steps,
               count(DISTINCT bs) AS scopes
    ''').single()
    edges = s.run('''
        MATCH (v:Version {framework: \"spring-boot\", version: \"3.4.0\"})
              -[e:INCLUDES_RULE]->()
        WITH count(e) AS inc
        OPTIONAL MATCH ()-[req:REQUIRES]->()
        OPTIONAL MATCH ()-[rs:REQUIRES_STEP]->()
        OPTIONAL MATCH ()-[hs:HAS_SCOPE]->()
        RETURN inc,
               count(req) AS requires,
               count(rs)  AS requires_step,
               count(hs)  AS has_scope
    ''').single()
    counts = {
        'rules':          nodes['rules'],
        'steps':          nodes['steps'],
        'scopes':         nodes['scopes'],
        'includes_rule':  edges['inc'],
        'requires':       edges['requires'],
        'requires_step':  edges['requires_step'],
        'has_scope':      edges['has_scope'],
    }
    with open('/tmp/pipeline_counts_before.json', 'w') as f:
        json.dump(counts, f)
    print('Before:', counts)
"
```

### 6-B: Second full run

```bash
uv run migration-oracle pipeline \
  --framework spring-boot 3.3.0 3.4.0 \
  --force-llm

echo "Exit code: $?"   # Must be 0
```

### 6-C: Capture counts after and compare

```bash
uv run python -c "
import json
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    nodes = s.run('''
        MATCH (v:Version {framework: \"spring-boot\", version: \"3.4.0\"})
        OPTIONAL MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)
        OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
        OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
        RETURN count(DISTINCT r)  AS rules,
               count(DISTINCT s)  AS steps,
               count(DISTINCT bs) AS scopes
    ''').single()
    edges = s.run('''
        MATCH (v:Version {framework: \"spring-boot\", version: \"3.4.0\"})
              -[e:INCLUDES_RULE]->()
        WITH count(e) AS inc
        OPTIONAL MATCH ()-[req:REQUIRES]->()
        OPTIONAL MATCH ()-[rs:REQUIRES_STEP]->()
        OPTIONAL MATCH ()-[hs:HAS_SCOPE]->()
        RETURN inc,
               count(req) AS requires,
               count(rs)  AS requires_step,
               count(hs)  AS has_scope
    ''').single()
    after = {
        'rules':          nodes['rules'],
        'steps':          nodes['steps'],
        'scopes':         nodes['scopes'],
        'includes_rule':  edges['inc'],
        'requires':       edges['requires'],
        'requires_step':  edges['requires_step'],
        'has_scope':      edges['has_scope'],
    }

with open('/tmp/pipeline_counts_before.json') as f:
    before = json.load(f)

diffs = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
if diffs:
    print(f'FAIL: counts changed after second run: {diffs}')
else:
    print(f'PASS: all node and edge counts identical after second run')
    print(f'      Counts: {after}')
"
```

**Expected outcome**: Every key in the diff dict is empty — node counts and edge counts are byte-for-byte identical before and after the second run.

---

## Level 7 — `--skip-existing`

> Requires Level 5 to have completed successfully (Version node must exist).

### 7-A: Skip when all three conditions are met

```bash
# All three should be true: raw MD exists, filtered MD exists, Version node exists
uv run migration-oracle pipeline \
  --framework spring-boot 3.3.0 3.4.0 \
  --skip-existing 2>&1

echo "Exit code: $?"  # Must be 0
```

Expected: output indicates the run was **skipped**, not that it completed after executing LLM calls or graph writes. The word "skip" or equivalent must appear.

### 7-B: Proceeds when Version node is absent (one condition missing)

```bash
# Delete the Version node to break one condition
uv run python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    s.run(
        'MATCH (v:Version {framework: \$f, version: \$v}) DETACH DELETE v',
        f='spring-boot', v='3.4.0'
    )
print('Deleted Version node')
"

# --skip-existing should now proceed (not skip) because Version node is absent
uv run migration-oracle pipeline \
  --framework spring-boot 3.3.0 3.4.0 \
  --skip-existing \
  --dry-run

echo "Exit code: $?"  # Must be 0, and the run must have executed (not skipped)
```

### 7-C: Proceeds when raw MD is absent (one condition missing)

```bash
# Remove the raw MD artifact
mv runs/raw/spring-boot-3.3.0-to-3.4.0-changes.md /tmp/raw_backup.md

uv run migration-oracle pipeline \
  --framework spring-boot 3.3.0 3.4.0 \
  --skip-existing \
  --dry-run 2>&1

echo "Exit code: $?"  # Must be 0 and must have run (fetched or used stub)

# Restore
mv /tmp/raw_backup.md runs/raw/spring-boot-3.3.0-to-3.4.0-changes.md
```

**Expected outcome**: Skips cleanly when all three conditions hold, proceeds when any condition is absent.

---

## Completion gate checklist

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| Level | Check | Result |
|-------|-------|--------|
| 0-A | All six modules import without error | |
| 0-B | `SOURCE_SECTION_TO_RULE_TYPE` has exactly 7 keys | |
| 0-C | All 7 `ruleType` mapping values are correct | |
| 0-D | `EXTRACTION_RATE_LIMIT_RETRIES=3`, `EXTRACTION_RETRY_BASE_DELAY=2.0` | |
| 1-A | `--help` lists all 10 required flags | |
| 1-B | Unknown framework exits non-zero with supported key list (not traceback) | |
| 1-C | Missing `MODEL_PROVIDER` exits non-zero with clear message | |
| 2-B | Stale-artifact warning prints; exit code 0 | |
| 2-C | Re-run without force flags does not change artifact mtimes | |
| 3-A | Graph driver connects | |
| 3-B | `version_exists` returns `False` for unknown version | |
| 3-C | `upsert_version_artifact_paths` writes all 3 paths; `sortableVersion=3004000` | |
| 3-D | `list_pipeline_runs` returns the test Version node | |
| 4-B | Dry-run exits 0 | |
| 4-C | Both artifact files exist after dry-run | |
| 4-D | Filtered MD contains emoji section headers | |
| 4-E | Entities JSON validates as `MigrationEntitiesBatch` with ≥1 entity | |
| 4-F | Dry-run does not write Version node to graph | |
| 5-A | Full run exits 0 | |
| 5-B | Version node has all 3 paths; `sortableVersion=3004000` | |
| 5-C | All `MigrationRule` `ruleType` values are from the valid enum | |
| 5-E | All rules have `entityClassification` in `{actionable, incomplete, informational}` | |
| 5-F | Zero new `MigrationRule` nodes have `actionStep` set | |
| 6-C | All node and edge counts identical after second `--force-llm` run | |
| 7-A | `--skip-existing` skips when all 3 conditions hold | |
| 7-B | `--skip-existing` proceeds when Version node is absent | |
| 7-C | `--skip-existing` proceeds when raw MD is absent | |
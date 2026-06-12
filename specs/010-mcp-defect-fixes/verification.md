# Verification Protocol — MCP Defect Fixes (Migration Session Hardening)

**Location**: `specs/010-mcp-defect-fixes/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `010` ✅
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | How to verify |
|---|---|
| Python dependencies installed | `pip install -e ".[dev]"` or `uv sync` from repo root |
| pytest available | `pytest --version` returns without error |
| No live Neo4j needed | All tests use `unittest.mock.patch` (accepted deviation, plan.md §Testing) |
| No LLM credentials needed | Same — all tests are mock-based |
| Repo root is working directory | `ls migration_oracle/` shows `mcp/`, `paysafe/`, `models/` |

**Level infrastructure summary:**

| Level | Name | Infrastructure |
|---|---|---|
| 0 | Static / structural checks | None |
| 1 | Skill file verification | None |
| 2 | Credential scrub isolation | None |
| 5 | Unit test suite | None (mock-based) |
| 7 | Edge-case static assertions | None |

Levels 3, 4, and 6 are omitted: all graph interaction is covered by mock-based unit tests
(accepted deviation); no dry-run mode exists; no new MERGE nodes are introduced that would
require idempotency checks.

---

## Level 0 — Static / Structural Checks

No external services. These checks must all pass before running any test.

### 0-A: All modified modules import without error

```bash
python -c "
import migration_oracle.mcp.tools.upgrade as u
import migration_oracle.mcp.tools.context as c
import migration_oracle.mcp.tools.search as s
import migration_oracle.mcp.graph.queries.context as qc
import migration_oracle.mcp.graph.queries.upgrade as qu
import migration_oracle.mcp.graph.queries.search as qs
import migration_oracle.paysafe.resolver as r
print('PASS: all 7 modified modules import without error')
"
```

### 0-B: `to_minor_zero` is public (no leading underscore)

```bash
python -c "
from migration_oracle.mcp.tools.upgrade import to_minor_zero
assert callable(to_minor_zero), 'to_minor_zero is not callable'
assert to_minor_zero('3.5.12') == '3.5.0', f'Got: {to_minor_zero(\"3.5.12\")}'
assert to_minor_zero('4.1.0') == '4.1.0', f'Got: {to_minor_zero(\"4.1.0\")}'
print('PASS: to_minor_zero is exported and normalises patch versions correctly')
"
```

### 0-C: No `_to_minor_zero` references remain anywhere in the project

```bash
result=$(grep -rn "_to_minor_zero" migration_oracle/ tests/ 2>/dev/null)
if [ -n "$result" ]; then
  echo "FAIL: _to_minor_zero still referenced:"
  echo "$result"
  exit 1
fi
print='PASS: zero _to_minor_zero references found'
echo "$print"
```

### 0-D: `_FRAMEWORK_MAVEN_COORDS` contains the `spring-boot` entry with correct coordinates

```bash
python -c "
from migration_oracle.mcp.tools.upgrade import _FRAMEWORK_MAVEN_COORDS
assert 'spring-boot' in _FRAMEWORK_MAVEN_COORDS, \
    f'spring-boot missing; keys: {list(_FRAMEWORK_MAVEN_COORDS.keys())}'
g, a = _FRAMEWORK_MAVEN_COORDS['spring-boot']
assert g == 'org.springframework.boot', f'groupId wrong: {g}'
assert a == 'spring-boot', f'artifactId wrong: {a}'
print('PASS: _FRAMEWORK_MAVEN_COORDS has correct spring-boot entry')
"
```

### 0-E: `_CRED_RE` and `_scrub` are defined at module level in `resolver.py`

```bash
python -c "
import migration_oracle.paysafe.resolver as r
import re
assert hasattr(r, '_CRED_RE'), 'FAIL: _CRED_RE missing from resolver module'
assert isinstance(r._CRED_RE, type(re.compile(''))), \
    f'FAIL: _CRED_RE is not a compiled regex; got {type(r._CRED_RE)}'
assert hasattr(r, '_scrub'), 'FAIL: _scrub function missing from resolver module'
assert callable(r._scrub), 'FAIL: _scrub is not callable'
print('PASS: _CRED_RE and _scrub present at resolver module level')
"
```

### 0-F: `check_version_availability` is registered as an MCP tool

```bash
python -c "
from migration_oracle.mcp.tools import upgrade
# FastMCP auto-registers @mcp.tool() when module is imported.
# Check the function exists and is callable.
assert hasattr(upgrade, 'check_version_availability'), \
    'FAIL: check_version_availability function missing from upgrade module'
assert callable(upgrade.check_version_availability), \
    'FAIL: check_version_availability is not callable'
print('PASS: check_version_availability is present and callable in upgrade module')
"
```

### 0-G: `search.py` deferred filter block is removed

```bash
result=$(grep -n "only_composite is not None or require_no_params" \
  migration_oracle/mcp/tools/search.py 2>/dev/null)
if [ -n "$result" ]; then
  echo "FAIL: deferred filter block still present in tools/search.py:"
  echo "$result"
  exit 1
fi
echo "PASS: deferred filter pass block absent from search.py"
```

### 0-H: `hydrate_openrewrite_recipes` in `queries/search.py` accepts the filter parameters

```bash
python -c "
import inspect
from migration_oracle.mcp.graph.queries.search import hydrate_openrewrite_recipes
sig = inspect.signature(hydrate_openrewrite_recipes)
params = list(sig.parameters.keys())
assert 'only_composite' in params, \
    f'FAIL: only_composite not in hydrate_openrewrite_recipes params; got {params}'
assert 'require_no_params' in params, \
    f'FAIL: require_no_params not in hydrate_openrewrite_recipes params; got {params}'
print('PASS: hydrate_openrewrite_recipes accepts only_composite and require_no_params')
"
```

---

## Level 1 — Skill File Verification

No external services. These are grep-based checks on the Markdown skill files.

### 1-A: STATELESS FALLBACK block exists exactly once in `framework_migration_main.md`

```bash
count=$(grep -c "STATELESS FALLBACK" \
  migration_oracle/mcp/skills/framework_migration_main.md 2>/dev/null || echo 0)
if [ "$count" -ne 1 ]; then
  echo "FAIL: expected exactly 1 STATELESS FALLBACK occurrence, found $count"
  exit 1
fi
echo "PASS: STATELESS FALLBACK appears exactly once"
```

### 1-B: STATELESS FALLBACK block appears before `## Loop II`

```bash
python -c "
with open('migration_oracle/mcp/skills/framework_migration_main.md') as f:
    lines = f.readlines()
fallback_line = next((i for i, l in enumerate(lines) if 'STATELESS FALLBACK' in l), None)
loop2_line = next((i for i, l in enumerate(lines) if '## Loop II' in l), None)
assert fallback_line is not None, 'FAIL: STATELESS FALLBACK not found'
assert loop2_line is not None, 'FAIL: ## Loop II not found'
assert fallback_line < loop2_line, \
    f'FAIL: STATELESS FALLBACK (line {fallback_line+1}) is after ## Loop II (line {loop2_line+1})'
print(f'PASS: STATELESS FALLBACK at line {fallback_line+1}, ## Loop II at line {loop2_line+1}')
"
```

### 1-C: No `grep -P` in `framework_migration_main.md`

```bash
result=$(grep -n "grep -P" \
  migration_oracle/mcp/skills/framework_migration_main.md 2>/dev/null)
if [ -n "$result" ]; then
  echo "FAIL: grep -P found in framework_migration_main.md (macOS incompatible):"
  echo "$result"
  exit 1
fi
echo "PASS: no grep -P in framework_migration_main.md"
```

### 1-D: `submit_migration_insight` appears inside the STATELESS FALLBACK section without a `context_id` argument

```bash
python -c "
with open('migration_oracle/mcp/skills/framework_migration_main.md') as f:
    content = f.read()

# Find the STATELESS FALLBACK section
fallback_start = content.find('STATELESS FALLBACK')
assert fallback_start != -1, 'FAIL: STATELESS FALLBACK not found'

# Find Loop II after the fallback section
loop2_pos = content.find('## Loop II', fallback_start)
assert loop2_pos != -1, 'FAIL: ## Loop II not found after STATELESS FALLBACK'

# Extract the fallback block
fallback_block = content[fallback_start:loop2_pos]
assert 'submit_migration_insight' in fallback_block, \
    'FAIL: submit_migration_insight not mentioned in STATELESS FALLBACK block'
assert 'context_id' not in fallback_block or 'without a \`context_id\`' in fallback_block \
    or 'without a context_id' in fallback_block, \
    'FAIL: STATELESS FALLBACK block does not document that context_id is omitted'
print('PASS: submit_migration_insight present in STATELESS FALLBACK block; context_id handling documented')
"
```

### 1-E: Three non-target skill files are unmodified (check by verifying they do not contain STATELESS FALLBACK)

```bash
for f in framework_migration_scanning.md framework_migration_plan_format.md framework_migration_version_map.md; do
  if grep -q "STATELESS FALLBACK" "migration_oracle/mcp/skills/$f" 2>/dev/null; then
    echo "FAIL: $f was unexpectedly modified (contains STATELESS FALLBACK)"
    exit 1
  fi
done
echo "PASS: framework_migration_scanning.md, framework_migration_plan_format.md, framework_migration_version_map.md unchanged"
```

---

## Level 2 — Credential Scrub Isolation

No external services. These inline Python blocks exercise `_scrub()` directly — no imports of live graph or HTTP clients.

### 2-A: OAuth2 token is redacted

```bash
python -c "
from migration_oracle.paysafe.resolver import _scrub
result = _scrub('oauth2:abc123token@gitlab.example.com/repo/project')
assert 'abc123token' not in result, f'FAIL: token still present in: {result}'
assert '<redacted>@' in result, f'FAIL: <redacted>@ marker absent; got: {result}'
print(f'PASS: oauth2 token scrubbed → {result}')
"
```

### 2-B: Basic-auth credentials are redacted

```bash
python -c "
from migration_oracle.paysafe.resolver import _scrub
result = _scrub('https://user:s3cr3tpass@host.example.com/path')
assert 's3cr3tpass' not in result, f'FAIL: password still present in: {result}'
assert 'user' not in result or '<redacted>@' in result, \
    f'FAIL: credential not scrubbed; got: {result}'
print(f'PASS: basic-auth credentials scrubbed → {result}')
"
```

### 2-C: Clean message passes through unchanged

```bash
python -c "
from migration_oracle.paysafe.resolver import _scrub
msg = 'Connection timed out after 30s'
result = _scrub(msg)
assert result == msg, f'FAIL: clean message was altered; got: {result}'
print('PASS: clean message returned unchanged')
"
```

### 2-D: `_build_error()` applies scrub to its `message` argument

```bash
python -c "
from migration_oracle.paysafe.resolver import _build_error
result = _build_error('git_ls_remote_failed', 'oauth2:TOKEN99@gitlab.example.com failed')
assert 'TOKEN99' not in result.get('message', ''), \
    f'FAIL: token leaked in _build_error output; message: {result.get(\"message\")}'
assert '<redacted>@' in result.get('message', ''), \
    f'FAIL: <redacted>@ marker absent from _build_error message; got: {result}'
print('PASS: _build_error scrubs credentials from message field')
"
```

---

## Level 5 — Unit Test Suite

No live Neo4j or LLM required. All tests use `unittest.mock.patch`.

Run each file individually to isolate failures, then run all five together.

### 5-A: Context fixes test file

```bash
pytest tests/mcp/test_context_fixes.py -v
```

Expected: All tests pass including `test_normalises_patch_version`, `test_version_not_in_graph`, `test_zombie_cleanup_on_version_miss`, `test_stepnotes_persisted`, `test_no_entry_without_reason`, `test_scope_tier_returns_scopeless_steps`, `test_patch_version_full_chain`.

### 5-B: Recipe applicability test file

```bash
pytest tests/mcp/test_recipe_applicability.py -v
```

Expected: All tests pass including `test_applicable_steps`, `test_not_applicable_steps`, `test_unknown_when_empty_entities`, `test_dedup_first_occurrence_wins`.

### 5-C: `check_version_availability` test file

```bash
pytest tests/mcp/test_check_version_availability.py -v
```

Expected: All tests pass including `test_returns_all_fields_for_known_version`, `test_exists_in_graph_false_for_missing_version`, `test_unsupported_framework_returns_error_no_network_call`, `test_maven_central_unavailable_returns_graceful_response`.

### 5-D: OpenRewrite filter test file

```bash
pytest tests/mcp/test_openrewrite_filters.py -v
```

Expected: All tests pass including `test_only_composite_filter_applied`, `test_require_no_params_filter_applied`, `test_both_filters_combined`.

### 5-E: Resolver credential scrub and Artifactory fallback test file

```bash
pytest tests/paysafe/test_resolver_credential_scrub.py -v
```

Expected: All tests pass including `test_scrubs_oauth2_token`, `test_scrubs_basic_auth`, `test_clean_message_unchanged`, `test_artifactory_fallback_called`, `test_no_fallback_without_env_var`.

### 5-F: Full five-file suite with zero failures

```bash
pytest tests/mcp/test_context_fixes.py \
       tests/mcp/test_recipe_applicability.py \
       tests/mcp/test_check_version_availability.py \
       tests/mcp/test_openrewrite_filters.py \
       tests/paysafe/test_resolver_credential_scrub.py \
       -v --tb=short
```

Expected: Exit code 0, zero errors, zero failures.

### 5-G: Existing test suite is not broken (regression check)

```bash
pytest tests/ -v --tb=short -q \
  --ignore=tests/streamlit \
  --ignore=tests/test_002_pipeline_core \
  --ignore=tests/test_000_foundations 2>&1 | tail -20
```

Expected: No new failures introduced. Any pre-existing failures are acceptable only if they existed before this spec was implemented — verify against the pre-implement baseline if needed.

---

## Level 7 — Edge-Case Static Assertions

No external services. These checks verify specific structural correctness guarantees that unit tests alone cannot prove.

### 7-A: Zombie cleanup Cypher uses structural WHERE guard (not `_was_created` flag)

```bash
python -c "
from migration_oracle.mcp.graph.queries.context import _DELETE_ZOMBIE_CONTEXT
assert 'UPGRADES_FROM' in _DELETE_ZOMBIE_CONTEXT, \
    f'FAIL: _DELETE_ZOMBIE_CONTEXT does not use structural UPGRADES_FROM guard; got:\n{_DELETE_ZOMBIE_CONTEXT}'
assert '_was_created' not in _DELETE_ZOMBIE_CONTEXT, \
    f'FAIL: _DELETE_ZOMBIE_CONTEXT uses _was_created flag (not readable from None record); got:\n{_DELETE_ZOMBIE_CONTEXT}'
assert 'WHERE NOT' in _DELETE_ZOMBIE_CONTEXT, \
    f'FAIL: WHERE NOT guard missing from _DELETE_ZOMBIE_CONTEXT; got:\n{_DELETE_ZOMBIE_CONTEXT}'
print('PASS: _DELETE_ZOMBIE_CONTEXT uses structural UPGRADES_FROM WHERE guard, not _was_created')
"
```

### 7-B: `check_version_availability` Cypher constant does not contain MERGE or CREATE

```bash
python -c "
from migration_oracle.mcp.graph.queries.upgrade import _CHECK_VERSION_IN_GRAPH
upper = _CHECK_VERSION_IN_GRAPH.upper()
assert 'MERGE' not in upper, \
    f'FAIL: _CHECK_VERSION_IN_GRAPH contains MERGE (tool must not write to graph per FR-019)'
assert 'CREATE' not in upper, \
    f'FAIL: _CHECK_VERSION_IN_GRAPH contains CREATE (tool must not write to graph per FR-019)'
print('PASS: _CHECK_VERSION_IN_GRAPH is read-only (no MERGE, no CREATE)')
"
```

### 7-C: `_BUILD_RECIPE_PLAN` Cypher includes `AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY` collection

```bash
python -c "
from migration_oracle.mcp.graph.queries.upgrade import _BUILD_RECIPE_PLAN
assert 'AFFECTS_CLASS' in _BUILD_RECIPE_PLAN, \
    'FAIL: AFFECTS_CLASS missing from _BUILD_RECIPE_PLAN Cypher'
assert 'AFFECTS_PROPERTY' in _BUILD_RECIPE_PLAN, \
    'FAIL: AFFECTS_PROPERTY missing from _BUILD_RECIPE_PLAN Cypher'
assert 'AFFECTS_DEPENDENCY' in _BUILD_RECIPE_PLAN, \
    'FAIL: AFFECTS_DEPENDENCY missing from _BUILD_RECIPE_PLAN Cypher'
assert 'all_affected_entities' in _BUILD_RECIPE_PLAN, \
    'FAIL: all_affected_entities alias missing from _BUILD_RECIPE_PLAN Cypher'
print('PASS: _BUILD_RECIPE_PLAN collects affected entities via all three relationship types')
"
```

### 7-D: `hydrate_openrewrite_recipes` WHERE clause contains both filter patterns in the Cypher string

```bash
python -c "
import inspect, textwrap
from migration_oracle.mcp.graph.queries.search import hydrate_openrewrite_recipes
src = inspect.getsource(hydrate_openrewrite_recipes)
assert 'r.composite' in src, \
    'FAIL: r.composite filter not found in hydrate_openrewrite_recipes source'
assert 'HAS_PARAM' in src, \
    'FAIL: HAS_PARAM filter not found in hydrate_openrewrite_recipes source'
assert 'required' in src, \
    'FAIL: required parameter filter not found in hydrate_openrewrite_recipes source'
# Confirm the deferred pass block is gone
assert 'pass' not in src.split('only_composite')[1].split('return')[0] \
    if 'only_composite' in src else True, \
    'FAIL: deferred pass block still present after only_composite check'
print('PASS: hydrate_openrewrite_recipes Cypher contains composite and required-param filters')
"
```

### 7-E: `get_steps_for_scope_tier` Cypher does not apply WHERE filter on OPTIONAL MATCH target

```bash
python -c "
from migration_oracle.mcp.graph.queries.context import _GET_STEPS_FOR_SCOPE_TIER
# The WHERE predicate on 'bs.scope' after OPTIONAL MATCH caused the inner-join bug.
# After the fix, bs.scope must not be filtered in Cypher.
lines = [l.strip() for l in _GET_STEPS_FOR_SCOPE_TIER.splitlines()]
for i, line in enumerate(lines):
    if 'OPTIONAL MATCH' in line and 'BreakingScope' in line:
        # The next non-empty line must not be 'WHERE bs.scope'
        next_lines = [l for l in lines[i+1:i+4] if l]
        for nl in next_lines:
            if 'WHERE' in nl and 'bs.scope' in nl:
                raise AssertionError(
                    f'FAIL: WHERE bs.scope predicate still follows OPTIONAL MATCH (inner-join bug): {nl}'
                )
        break
print('PASS: OPTIONAL MATCH (BreakingScope) is not followed by WHERE bs.scope filter')
"
```

### 7-F: `unsupported_framework` path in `check_version_availability` makes no network call

This is a structural check — verify the early-return path is present before the Maven Central probe:

```bash
python -c "
import inspect
from migration_oracle.mcp.tools.upgrade import check_version_availability
src = inspect.getsource(check_version_availability)
# The unsupported_framework check must appear before any requests.get call
unsupported_idx = src.find('unsupported_framework')
network_idx = src.find('requests.get')
assert unsupported_idx != -1, 'FAIL: unsupported_framework branch missing from check_version_availability'
assert network_idx != -1, 'FAIL: requests.get call missing from check_version_availability'
assert unsupported_idx < network_idx, \
    'FAIL: unsupported_framework guard appears AFTER requests.get — network call may fire for unknown frameworks'
print('PASS: unsupported_framework early-return appears before any requests.get call')
"
```

### 7-G: Artifactory fallback checks for `ARTIFACTORY_BASE_URL` before making HTTP call

```bash
python -c "
import inspect
from migration_oracle.paysafe import resolver
src = inspect.getsource(resolver)
# ARTIFACTORY_BASE_URL check must appear before requests.get in the resolver source
art_env_idx = src.find('ARTIFACTORY_BASE_URL')
requests_idx = src.find('requests.get')
assert art_env_idx != -1, 'FAIL: ARTIFACTORY_BASE_URL not referenced in resolver.py'
assert requests_idx != -1, 'FAIL: requests.get not found in resolver.py'
assert art_env_idx < requests_idx, \
    'FAIL: ARTIFACTORY_BASE_URL guard appears AFTER requests.get — env var not checked first'
# Also confirm no Authorization header is passed
requests_section = src[requests_idx:requests_idx+300]
assert 'Authorization' not in requests_section, \
    f'FAIL: Authorization header found in Artifactory requests.get call; section:\n{requests_section}'
print('PASS: ARTIFACTORY_BASE_URL is checked before requests.get; no Authorization header')
"
```

---

## Completion Gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| ID | Check | Result |
|---|---|---|
| 0-A | All 7 modified modules import without error | ☐ |
| 0-B | `to_minor_zero` is exported and normalises `"3.5.12"` → `"3.5.0"` | ☐ |
| 0-C | Zero `_to_minor_zero` references in `migration_oracle/` and `tests/` | ☐ |
| 0-D | `_FRAMEWORK_MAVEN_COORDS["spring-boot"]` = `("org.springframework.boot", "spring-boot")` | ☐ |
| 0-E | `_CRED_RE` (compiled regex) and `_scrub` function at module level in `resolver.py` | ☐ |
| 0-F | `check_version_availability` present and callable in `upgrade` module | ☐ |
| 0-G | Deferred filter `pass` block absent from `tools/search.py` | ☐ |
| 0-H | `hydrate_openrewrite_recipes` signature includes `only_composite` and `require_no_params` | ☐ |
| 1-A | `STATELESS FALLBACK` appears exactly once in `framework_migration_main.md` | ☐ |
| 1-B | `STATELESS FALLBACK` block appears before `## Loop II` | ☐ |
| 1-C | No `grep -P` in `framework_migration_main.md` | ☐ |
| 1-D | `submit_migration_insight` in STATELESS FALLBACK block; `context_id` omission documented | ☐ |
| 1-E | Three non-target skill files are unmodified | ☐ |
| 2-A | `_scrub()` redacts `oauth2:TOKEN@...` — `TOKEN` absent from output | ☐ |
| 2-B | `_scrub()` redacts `https://user:pass@host` — password absent from output | ☐ |
| 2-C | `_scrub()` returns clean message unchanged | ☐ |
| 2-D | `_build_error()` applies scrub — credential absent from returned `message` field | ☐ |
| 5-A | `test_context_fixes.py` — all tests pass (including `test_patch_version_full_chain`) | ☐ |
| 5-B | `test_recipe_applicability.py` — all tests pass | ☐ |
| 5-C | `test_check_version_availability.py` — all tests pass | ☐ |
| 5-D | `test_openrewrite_filters.py` — all tests pass | ☐ |
| 5-E | `test_resolver_credential_scrub.py` — all tests pass | ☐ |
| 5-F | Full five-file suite: exit code 0, zero failures | ☐ |
| 5-G | Existing test suite shows no new failures (regression check) | ☐ |
| 7-A | `_DELETE_ZOMBIE_CONTEXT` uses `UPGRADES_FROM` structural WHERE guard, not `_was_created` | ☐ |
| 7-B | `_CHECK_VERSION_IN_GRAPH` contains no MERGE or CREATE | ☐ |
| 7-C | `_BUILD_RECIPE_PLAN` collects `all_affected_entities` via all three relationship types | ☐ |
| 7-D | `hydrate_openrewrite_recipes` source contains `r.composite` and `HAS_PARAM` / `required` filters | ☐ |
| 7-E | `_GET_STEPS_FOR_SCOPE_TIER` OPTIONAL MATCH not followed by `WHERE bs.scope` predicate | ☐ |
| 7-F | `unsupported_framework` early-return in `check_version_availability` precedes `requests.get` | ☐ |
| 7-G | `ARTIFACTORY_BASE_URL` guard precedes `requests.get`; no `Authorization` header in fallback call | ☐ |

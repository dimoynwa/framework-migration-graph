# Verification Protocol: 004-paysafe-resolver

**Location**: `specs/004-paysafe-resolver/verification-protocol.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `004` ✅ in `docs/SPEC_ORGANIZATION.md`
**Execution order**: Levels 0 → 2 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | How to satisfy |
|-------------|---------------|
| Dependencies installed | `uv sync` exits 0 |
| `NEO4J_URI` set (import-time requirement of `config.py`) | `export NEO4J_URI=bolt://localhost:7687` |
| `NEO4J_PASSWORD` set | `export NEO4J_PASSWORD=test` |
| `FINDIT_AUTH_TOKEN` set (required for Level 7-K only) | `export FINDIT_AUTH_TOKEN=<your-token>` |
| Working directory | repo root (`/Users/dimo.drangov/paysafe-version-migration-graph`) |

## Infrastructure requirements per level

| Level | DB | LLM | External network |
|-------|----|-----|-----------------|
| 0 — Static checks | No | No | No |
| 1 — Interface structure | No | No | No |
| 2 — Isolation behaviour | No | No | No (all mocked) |
| 7 — Edge-case paths | No | No | No (mocked); 7-K optional live |

**Levels 3, 4, 5, 6 are omitted.** The paysafe resolver has no graph database dependency — it is strictly read-only with respect to Neo4j/Memgraph and makes no LLM calls. The database connection required by `config.py` at import time is satisfied by the dummy env vars above.

---

## Level 0 — Static checks

No external services. Run every check before proceeding to Level 1.

### 0-A — All paysafe modules import without error

```bash
uv run python -c "
import migration_oracle.paysafe
import migration_oracle.paysafe.resolver
import migration_oracle.paysafe.findit
import migration_oracle.paysafe.gitlab
import migration_oracle.paysafe._types
from migration_oracle.paysafe import resolve
print('PASS 0-A: all paysafe modules import without error')
"
```

### 0-B — FINDIT_BASE_URL default is the correct hostname

```bash
uv run python -c "
from migration_oracle import config
url = config.FINDIT_BASE_URL
assert 'findit-api.icd.paysafe.cloud' in url, f'FAIL 0-B: wrong default URL: {url!r}'
assert 'findit.paysafe.com' not in url, f'FAIL 0-B: old URL still in default: {url!r}'
print(f'PASS 0-B: FINDIT_BASE_URL default = {url!r}')
"
```

### 0-C — FINDIT_SERVICE_NAME_FUZZY_THRESHOLD default is 0.68

```bash
uv run python -c "
from migration_oracle import config
t = config.FINDIT_SERVICE_NAME_FUZZY_THRESHOLD
assert t == 0.68, f'FAIL 0-C: threshold = {t!r}, expected 0.68'
print(f'PASS 0-C: FINDIT_SERVICE_NAME_FUZZY_THRESHOLD = {t}')
"
```

### 0-D — GITLAB_API_KEY config entry exists with empty default

```bash
uv run python -c "
from migration_oracle import config
assert hasattr(config, 'GITLAB_API_KEY'), 'FAIL 0-D: GITLAB_API_KEY missing from config'
v = config.GITLAB_API_KEY
assert isinstance(v, str), f'FAIL 0-D: GITLAB_API_KEY is not a str: {type(v)}'
print(f'PASS 0-D: GITLAB_API_KEY in config, default = {v!r}')
"
```

### 0-E — ResolverResult has all required top-level fields

```bash
uv run python -c "
from migration_oracle.paysafe._types import ResolverResult
import typing, inspect
# Works for TypedDict and dataclass
hints = typing.get_type_hints(ResolverResult)
required = {
    'status', 'service_name', 'selected_tag', 'selected_version',
    'framework', 'framework_version', 'selection_strategy',
    'target_version', 'code_repo_link', 'compatibility', 'effective_settings',
}
missing = required - set(hints.keys())
assert not missing, f'FAIL 0-E: ResolverResult missing fields: {missing}'
print(f'PASS 0-E: ResolverResult has all {len(required)} required fields')
"
```

### 0-F — SelectionStrategy has exactly the four canonical values

```bash
uv run python -c "
from migration_oracle.paysafe._types import SelectionStrategy
import typing
# Handle Literal types and enums
try:
    vals = set(typing.get_args(SelectionStrategy))
except Exception:
    vals = {s.value for s in SelectionStrategy}
expected = {'latest_compatible', 'latest_overall', 'latest_with_known_compatibility', 'pinned'}
assert vals == expected, f'FAIL 0-F: got {vals}, expected {expected}'
print(f'PASS 0-F: SelectionStrategy = {sorted(vals)}')
"
```

### 0-G — ErrorResponse error_code enum has all canonical codes

```bash
uv run python -c "
from migration_oracle.paysafe._types import ErrorResponse
import typing
hints = typing.get_type_hints(ErrorResponse)
# The error sub-dict or nested type must contain error_code
# Check by introspecting nested type or by checking a known canonical set attribute
canonical = {
    'invalid_service_name', 'service_not_found', 'no_repo_url',
    'no_tags_found', 'no_parseable_tags', 'no_compatible_version',
    'compatibility_unknown', 'http_timeout', 'http_request_failed',
    'git_ls_remote_failed',
}
try:
    from migration_oracle.paysafe._types import ERROR_CODES
    defined = set(ERROR_CODES)
except ImportError:
    # If no exported set, verify via Literal arg on error_code field
    error_inner = hints.get('error') or hints
    code_type = typing.get_type_hints(error_inner).get('error_code') if not isinstance(error_inner, dict) else None
    defined = set(typing.get_args(code_type)) if code_type else set()
missing = canonical - defined
assert not missing, f'FAIL 0-G: canonical error codes missing from _types: {missing}'
print(f'PASS 0-G: all {len(canonical)} canonical error codes present')
"
```

### 0-H — No `datetime.utcnow()` calls anywhere in paysafe/

```bash
result=$(grep -r "utcnow" migration_oracle/paysafe/ 2>/dev/null)
if [ -n "$result" ]; then
  echo "FAIL 0-H: datetime.utcnow() found in paysafe/ — must use datetime.now(timezone.utc)"
  echo "$result"
  exit 1
fi
echo "PASS 0-H: no datetime.utcnow() calls in migration_oracle/paysafe/"
```

### 0-I — No graph driver imports in paysafe/

```bash
result=$(grep -r "from migration_oracle\.graph\|from neo4j\|import neo4j\|from migration_oracle\.pipeline" migration_oracle/paysafe/ 2>/dev/null)
if [ -n "$result" ]; then
  echo "FAIL 0-I: forbidden graph/pipeline import found in paysafe/"
  echo "$result"
  exit 1
fi
echo "PASS 0-I: no graph driver or pipeline imports in migration_oracle/paysafe/"
```

### 0-J — No direct os.environ / os.getenv calls in paysafe/

```bash
result=$(grep -rE "os\.environ|os\.getenv" migration_oracle/paysafe/ 2>/dev/null)
if [ -n "$result" ]; then
  echo "FAIL 0-J: direct env var read found in paysafe/ — all config must come from migration_oracle.config"
  echo "$result"
  exit 1
fi
echo "PASS 0-J: no direct env var reads in migration_oracle/paysafe/"
```

### 0-K — subprocess calls confined to gitlab.py only

```bash
result=$(grep -r "subprocess" migration_oracle/paysafe/resolver.py migration_oracle/paysafe/findit.py migration_oracle/paysafe/__init__.py migration_oracle/paysafe/_types.py 2>/dev/null)
if [ -n "$result" ]; then
  echo "FAIL 0-K: subprocess call found outside gitlab.py"
  echo "$result"
  exit 1
fi
echo "PASS 0-K: subprocess calls confined to gitlab.py"
```

---

## Level 1 — Interface structure

Verifies the public API surface without any external calls.

### 1-A — resolve() signature has all seven parameters

```bash
uv run python -c "
import inspect
from migration_oracle.paysafe.resolver import resolve
sig = inspect.signature(resolve)
params = set(sig.parameters.keys())
required = {'service_name', 'target_version', 'framework', 'allow_latest_overall', 'max_tags', 'pinned_version', 'pinned_tag'}
missing = required - params
assert not missing, f'FAIL 1-A: resolve() missing parameters: {missing}'
print(f'PASS 1-A: resolve() has all 7 required parameters: {sorted(params)}')
"
```

### 1-B — allow_latest_overall defaults to False (never True)

```bash
uv run python -c "
import inspect
from migration_oracle.paysafe.resolver import resolve
sig = inspect.signature(resolve)
default = sig.parameters['allow_latest_overall'].default
assert default is False, f'FAIL 1-B: allow_latest_overall default = {default!r}, must be False (not True — MCP layer sets this)'
print(f'PASS 1-B: allow_latest_overall default = False')
"
```

### 1-C — max_tags default value present and is an integer

```bash
uv run python -c "
import inspect
from migration_oracle.paysafe.resolver import resolve
sig = inspect.signature(resolve)
default = sig.parameters['max_tags'].default
assert isinstance(default, int), f'FAIL 1-C: max_tags default is not int: {type(default)}'
assert default > 0, f'FAIL 1-C: max_tags default must be positive, got {default}'
print(f'PASS 1-C: max_tags default = {default}')
# NOTE: reference doc specifies 100; data-model.md specifies 50. Confirm alignment here.
# If this prints 50, verify against docs/graph-mcp-skills-and-paysafe-resolution.md §effective_settings.
"
```

### 1-D — resolve() never raises — returns dict for any input

```bash
uv run python -c "
from migration_oracle.paysafe.resolver import resolve
# Blank name — must not raise
r1 = resolve('')
assert isinstance(r1, dict), f'FAIL 1-D: resolve(\"\") returned {type(r1)}, expected dict'
assert r1.get('status') == 'error', f'FAIL 1-D: blank name should return error status, got: {r1}'
# None values — must not raise
r2 = resolve('x', target_version=None, framework=None)
assert isinstance(r2, dict), f'FAIL 1-D: resolve with all-None optionals returned {type(r2)}'
print('PASS 1-D: resolve() returns dict and never raises for edge inputs')
"
```

### 1-E — Error response is always nested under "error" key

```bash
uv run python -c "
from migration_oracle.paysafe.resolver import resolve
result = resolve('')  # invalid_service_name
assert result['status'] == 'error', f'FAIL 1-E: status = {result[\"status\"]!r}'
assert 'error' in result, f'FAIL 1-E: top-level \"error\" key absent; got keys: {list(result.keys())}'
assert 'error_code' not in result, f'FAIL 1-E: error_code must be nested under result[\"error\"], not at top level'
assert 'error_code' in result['error'], f'FAIL 1-E: error_code absent from result[\"error\"]: {result[\"error\"]}'
print(f'PASS 1-E: error response nested correctly — result[\"error\"][\"error_code\"] = {result[\"error\"][\"error_code\"]!r}')
"
```

### 1-F — Error response has all required error sub-fields

```bash
uv run python -c "
from migration_oracle.paysafe.resolver import resolve
result = resolve('')
err = result['error']
for field in ('error_code', 'message', 'recoverable', 'actionable_hint', 'details'):
    assert field in err, f'FAIL 1-F: error sub-field {field!r} absent; got: {list(err.keys())}'
assert isinstance(err['recoverable'], bool), f'FAIL 1-F: recoverable must be bool, got {type(err[\"recoverable\"])}'
assert isinstance(err['details'], dict), f'FAIL 1-F: details must be dict, got {type(err[\"details\"])}'
print('PASS 1-F: all 5 error sub-fields present with correct types')
"
```

---

## Level 2 — Isolation behaviour

All external I/O is mocked. Requires `respx` and `unittest.mock` (both in dev deps).
Clear the FindIt module cache before each cache-related check with `_findit._cache.clear()`.

### 2-A — Pinned mode makes zero network calls

```bash
uv run python -c "
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve

def boom(*a, **kw):
    raise AssertionError('FAIL 2-A: network call made during pinned mode')

with patch('migration_oracle.paysafe.findit.lookup', side_effect=boom), \
     patch('migration_oracle.paysafe.gitlab.list_tags', side_effect=boom):
    result = resolve('any-service', pinned_version='3.5.10', pinned_tag='3.5.10.A')

assert result['status'] == 'ok', f'FAIL 2-A: status = {result[\"status\"]!r}'
assert result['selection_strategy'] == 'pinned', f'FAIL 2-A: strategy = {result[\"selection_strategy\"]!r}'
print('PASS 2-A: pinned mode made no network calls')
"
```

### 2-B — Pinned mode response has correct shape

```bash
uv run python -c "
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve

with patch('migration_oracle.paysafe.findit.lookup', side_effect=AssertionError), \
     patch('migration_oracle.paysafe.gitlab.list_tags', side_effect=AssertionError):
    result = resolve('my-lib', pinned_version='3.5.10', pinned_tag='3.5.10.A', target_version='3.5.6')

# All 11 ResolverResult fields must be present
for f in ('status','service_name','selected_tag','selected_version','framework',
          'framework_version','selection_strategy','target_version','code_repo_link',
          'compatibility','effective_settings'):
    assert f in result, f'FAIL 2-B: field {f!r} missing from pinned result; got: {sorted(result.keys())}'

# name_resolution must be absent
assert 'name_resolution' not in result, f'FAIL 2-B: name_resolution present in pinned mode'

# Field values
assert result['selected_version'] == '3.5.10', f'FAIL 2-B: selected_version = {result[\"selected_version\"]!r}'
assert result['selected_tag'] == '3.5.10.A', f'FAIL 2-B: selected_tag = {result[\"selected_tag\"]!r}'
assert result['framework'] is None, f'FAIL 2-B: framework = {result[\"framework\"]!r}, expected None'
assert result['framework_version'] is None, f'FAIL 2-B: framework_version should be None'
assert result['code_repo_link'] is None, f'FAIL 2-B: code_repo_link should be None'
assert result['compatibility'] is None, f'FAIL 2-B: compatibility should be None'
assert isinstance(result['effective_settings'], dict), f'FAIL 2-B: effective_settings must be dict, got {type(result[\"effective_settings\"])}'
print('PASS 2-B: pinned mode response shape correct — all 11 fields present, name_resolution absent')
"
```

### 2-C — FindIt cache: service list fetched only once for two lookups within 30 days

```bash
uv run python -c "
import respx, httpx
import migration_oracle.paysafe.findit as _findit

_findit._cache.clear()

SERVICES = [{'name': 'payment-service', 'codeRepoLink': 'https://gitlab.paysafe.com/payment/payment-service.git'}]

with respx.mock:
    route = respx.get('https://findit-api.icd.paysafe.cloud/services').mock(
        return_value=httpx.Response(200, json={'services': SERVICES})
    )
    _findit.lookup('payment-service')
    _findit.lookup('payment-service')  # second call — must NOT re-fetch
    call_count = route.call_count

assert call_count == 1, f'FAIL 2-C: FindIt endpoint called {call_count} times; expected 1 (cache must serve second call)'
print(f'PASS 2-C: FindIt called once for 2 lookups within 30-day window')

_findit._cache.clear()
"
```

### 2-D — FindIt cache: stale entry (>30 days) triggers re-fetch

```bash
uv run python -c "
import respx, httpx
from datetime import datetime, timezone, timedelta
import migration_oracle.paysafe.findit as _findit
from migration_oracle import config

_findit._cache.clear()

SERVICES = [{'name': 'payment-service', 'codeRepoLink': 'https://gitlab.paysafe.com/p/ps.git'}]

# Inject a stale cache entry (31 days old)
stale_ts = datetime.now(timezone.utc) - timedelta(days=31)
_findit._cache[config.FINDIT_BASE_URL] = (SERVICES, stale_ts)

with respx.mock:
    route = respx.get('https://findit-api.icd.paysafe.cloud/services').mock(
        return_value=httpx.Response(200, json={'services': SERVICES})
    )
    _findit.lookup('payment-service')
    call_count = route.call_count

assert call_count == 1, f'FAIL 2-D: FindIt called {call_count} times after stale cache; expected 1 re-fetch'
print('PASS 2-D: stale cache (31 days) triggers one re-fetch')

_findit._cache.clear()
"
```

### 2-E — Full resolution: latest_compatible strategy end-to-end

```bash
uv run python -c "
from unittest.mock import patch, MagicMock
from migration_oracle.paysafe.resolver import resolve
from migration_oracle.paysafe._types import CompatibilityInfo

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}
TAGS = ['3.5.10', '3.4.0', '3.3.5']

def mock_compat(repo_url, tag):
    versions = {'3.5.10': '3.5.10', '3.4.0': '3.4.0', '3.3.5': '3.3.5'}
    v = versions.get(tag)
    if v is None:
        return None
    return CompatibilityInfo(framework_version=v, source_file='pom.xml', source_precedence='spring-boot-starter-parent')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=TAGS), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=mock_compat):
    result = resolve('my-lib', target_version='3.5.6', framework='spring-boot', allow_latest_overall=False)

assert result['status'] == 'ok', f'FAIL 2-E: status = {result.get(\"status\")!r}; error = {result.get(\"error\")}'
assert result['selected_tag'] == '3.5.10', f'FAIL 2-E: selected_tag = {result[\"selected_tag\"]!r}, expected 3.5.10'
assert result['selected_version'] == '3.5.10', f'FAIL 2-E: selected_version = {result[\"selected_version\"]!r}'
assert result['selection_strategy'] == 'latest_compatible', f'FAIL 2-E: strategy = {result[\"selection_strategy\"]!r}'
assert result['code_repo_link'] == FINDIT_RECORD['codeRepoLink'], f'FAIL 2-E: code_repo_link not echoed from FindIt'
assert isinstance(result['effective_settings'], dict), f'FAIL 2-E: effective_settings must be dict'
assert 'max_tags_returned' in result['effective_settings'], 'FAIL 2-E: effective_settings missing max_tags_returned'
print(f'PASS 2-E: latest_compatible resolution correct — selected {result[\"selected_tag\"]}')
"
```

### 2-F — compatibility field is a dict with source_precedence, never a boolean

```bash
uv run python -c "
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve
from migration_oracle.paysafe._types import CompatibilityInfo

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}

def mock_compat(repo_url, tag):
    return CompatibilityInfo(framework_version='3.5.10', source_file='pom.xml', source_precedence='spring-boot-starter-parent')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=['3.5.10']), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=mock_compat):
    result = resolve('my-lib', target_version='3.5.6', allow_latest_overall=False)

compat = result.get('compatibility')
assert isinstance(compat, dict), f'FAIL 2-F: compatibility must be a dict, got {type(compat)} = {compat!r}'
assert 'source_precedence' in compat, f'FAIL 2-F: compatibility missing source_precedence; got: {list(compat.keys())}'
assert 'source_file' in compat, f'FAIL 2-F: compatibility missing source_file'
assert 'framework_version' in compat, f'FAIL 2-F: compatibility missing framework_version'
print(f'PASS 2-F: compatibility is a dict with source_precedence={compat[\"source_precedence\"]!r}')
"
```

### 2-G — latest_overall fallback when no compatible tag and allow_latest_overall=True

```bash
uv run python -c "
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve
from migration_oracle.paysafe._types import CompatibilityInfo

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}

def mock_compat(repo_url, tag):
    return CompatibilityInfo(framework_version='3.4.0', source_file='pom.xml', source_precedence='spring-boot-starter-parent')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=['3.4.0', '3.3.5']), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=mock_compat):
    result = resolve('my-lib', target_version='3.5.6', allow_latest_overall=True)

assert result['status'] == 'ok', f'FAIL 2-G: expected ok with latest_overall fallback; got {result}'
assert result['selection_strategy'] == 'latest_overall', f'FAIL 2-G: strategy = {result[\"selection_strategy\"]!r}'
print(f'PASS 2-G: latest_overall fallback selected tag {result[\"selected_tag\"]!r}')
"
```

### 2-H — no_compatible_version error when allow_latest_overall=False and no compatible tag

```bash
uv run python -c "
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve
from migration_oracle.paysafe._types import CompatibilityInfo

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}

def mock_compat(repo_url, tag):
    return CompatibilityInfo(framework_version='3.4.0', source_file='pom.xml', source_precedence='spring-boot-starter-parent')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=['3.4.0']), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=mock_compat):
    result = resolve('my-lib', target_version='3.5.6', allow_latest_overall=False)

assert result['status'] == 'error', f'FAIL 2-H: expected error, got {result.get(\"status\")!r}'
assert result['error']['error_code'] == 'no_compatible_version', \
    f'FAIL 2-H: error_code = {result[\"error\"][\"error_code\"]!r}'
print('PASS 2-H: no_compatible_version error returned when allow_latest_overall=False')
"
```

### 2-I — name_resolution present on non-exact match, absent on exact match

```bash
uv run python -c "
import respx, httpx, json
import migration_oracle.paysafe.findit as _findit
from migration_oracle.paysafe.findit import lookup

_findit._cache.clear()

SERVICES = [{'name': 'payment-service', 'codeRepoLink': 'https://gitlab.paysafe.com/p/ps.git'}]

# Exact match — name_resolution must be absent
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(
        return_value=httpx.Response(200, json={'services': SERVICES})
    )
    result_exact = lookup('payment-service')

assert 'name_resolution' not in result_exact, \
    f'FAIL 2-I: name_resolution present on exact match; got: {result_exact.get(\"name_resolution\")}'
print('PASS 2-I(a): name_resolution absent on exact match')

_findit._cache.clear()

# Case-insensitive match — name_resolution must be present
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(
        return_value=httpx.Response(200, json={'services': SERVICES})
    )
    result_ci = lookup('Payment-Service')

assert 'name_resolution' in result_ci, \
    f'FAIL 2-I: name_resolution absent on case-insensitive match; got keys: {list(result_ci.keys())}'
assert result_ci['name_resolution']['method'] == 'case_insensitive', \
    f'FAIL 2-I: method = {result_ci[\"name_resolution\"][\"method\"]!r}'
assert result_ci['name_resolution']['matched_name'] == 'payment-service', \
    f'FAIL 2-I: matched_name = {result_ci[\"name_resolution\"][\"matched_name\"]!r}'
print(f'PASS 2-I(b): name_resolution present on case-insensitive match with correct method')

_findit._cache.clear()
"
```

### 2-J — allow_latest_overall is not defaulted by resolver (resolver-level guard)

```bash
uv run python -c "
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve
from migration_oracle.paysafe._types import CompatibilityInfo

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}

def mock_compat(repo_url, tag):
    return CompatibilityInfo(framework_version='3.4.0', source_file='pom.xml', source_precedence='spring-boot-starter-parent')

# Call WITHOUT passing allow_latest_overall — resolver must treat as False
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=['3.4.0']), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=mock_compat):
    result = resolve('my-lib', target_version='3.5.6')

assert result['status'] == 'error', \
    f'FAIL 2-J: resolver silently defaulted allow_latest_overall=True; got {result.get(\"status\")}'
assert result['error']['error_code'] == 'no_compatible_version', \
    f'FAIL 2-J: error_code = {result[\"error\"][\"error_code\"]!r}'
print('PASS 2-J: resolver did not default allow_latest_overall to True')
"
```

---

## Level 7 — Edge-case paths

### 7-A — Compatibility rule: 20-pair boundary matrix

```bash
uv run python -c "
from migration_oracle.paysafe.gitlab import _is_compatible

pairs = [
    # (declared, target, expected)
    ('3.5.10', '3.5.6',  True),   # same major, declared minor == target minor, patch higher
    ('3.5.6',  '3.5.6',  True),   # exact match
    ('3.6.0',  '3.5.6',  True),   # same major, higher minor
    ('4.0.0',  '3.5.6',  False),  # higher major
    ('2.7.18', '3.5.6',  False),  # lower major
    ('3.4.99', '3.5.6',  False),  # same major, lower minor
    ('3.5.5',  '3.5.6',  False),  # same major, same minor, lower patch
    ('3.5.7',  '3.5.6',  True),   # same major, same minor, higher patch
    ('18.2.0', '18.0.0', True),   # angular: same major, higher minor
    ('17.3.0', '18.0.0', False),  # angular: lower major
    ('18.0.0', '18.0.0', True),   # angular: exact
    ('19.0.0', '18.2.0', False),  # different major (higher)
    ('3.5.10', '3.5.10', True),   # exact — must be compatible
    ('3.5.0',  '3.5.10', False),  # same major.minor, lower patch
    ('3.5.11', '3.5.10', True),   # same major.minor, higher patch
    ('4.0.0',  '4.0.0',  True),   # major 4, exact
    ('4.0.1',  '4.0.0',  True),   # major 4, patch bump
    ('3.0.0',  '4.0.0',  False),  # lower major
    ('5.0.0',  '4.0.0',  False),  # higher major
    ('3.5.0',  '3.5.0',  True),   # exact, zero patch
]

failures = []
for declared, target, expected in pairs:
    got = _is_compatible(declared, target)
    if got != expected:
        failures.append(f'  declared={declared!r} target={target!r}: expected={expected} got={got}')

assert not failures, 'FAIL 7-A: compatibility rule failures:\n' + '\n'.join(failures)
print(f'PASS 7-A: all {len(pairs)} compatibility rule pairs correct')
"
```

### 7-B — Tag format handling: v-prefix, alphabetic suffix, unparseable tags

```bash
uv run python -c "
from unittest.mock import patch, MagicMock
from migration_oracle.paysafe.gitlab import list_tags

# Simulate git ls-remote output with mixed formats
raw_output = '\n'.join([
    'abc123\trefs/tags/v3.5.10',       # v-prefix — must parse as 3.5.10
    'def456\trefs/tags/3.5.10.A',      # alphabetic suffix — must parse and sort with 3.5.10
    'ghi789\trefs/tags/3.4.0',         # clean semver
    'jkl012\trefs/tags/not-a-version', # unparseable — must be silently skipped
    'mno345\trefs/tags/v3.6.0',        # v-prefix higher
    'pqr678\trefs/tags/3.6.0^{}',      # tag dereferenced form — must strip ^{}
])

mock_proc = MagicMock()
mock_proc.returncode = 0
mock_proc.stdout = raw_output
mock_proc.stderr = ''

with patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=mock_proc):
    tags = list_tags('git@gitlab.paysafe.com:test/repo.git')

# v-prefix must be stripped — no tag should start with v
v_tags = [t for t in tags if t.lower().startswith('v')]
assert not v_tags, f'FAIL 7-B: v-prefixed tags not stripped: {v_tags}'

# Unparseable tag must be absent
assert 'not-a-version' not in tags, f'FAIL 7-B: unparseable tag included in result'

# Tags must be in descending semver order
from packaging.version import Version
parseable = [t for t in tags]
assert parseable == sorted(parseable, key=lambda x: Version(x.rstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZ').rstrip('.')), reverse=True), \
    f'FAIL 7-B: tags not sorted descending: {parseable}'

print(f'PASS 7-B: tag format handling correct — {len(tags)} parseable tags in order: {tags}')
"
```

### 7-C — Name matching: all four levels produce correct method labels

```bash
uv run python -c "
import respx, httpx
import migration_oracle.paysafe.findit as _findit
from migration_oracle.paysafe.findit import lookup
from migration_oracle import config

SERVICES = [{'name': 'payment-gateway-service', 'codeRepoLink': 'https://gitlab.paysafe.com/p/pgs.git'}]

def mock_findit():
    return respx.mock(base_url='https://findit-api.icd.paysafe.cloud')

# Level 1: exact match — no name_resolution
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(return_value=httpx.Response(200, json={'services': SERVICES}))
    r = lookup('payment-gateway-service')
assert 'name_resolution' not in r, f'FAIL 7-C(exact): name_resolution present on exact match'
print('PASS 7-C(exact): name_resolution absent')

# Level 2: case-insensitive
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(return_value=httpx.Response(200, json={'services': SERVICES}))
    r = lookup('Payment-Gateway-Service')
assert r.get('name_resolution', {}).get('method') == 'case_insensitive', \
    f'FAIL 7-C(case): method = {r.get(\"name_resolution\", {}).get(\"method\")!r}'
print('PASS 7-C(case-insensitive)')

# Level 3: alphanumeric normalized
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(return_value=httpx.Response(200, json={'services': SERVICES}))
    r = lookup('PaymentGatewayService')
assert r.get('name_resolution', {}).get('method') == 'alphanumeric_normalized', \
    f'FAIL 7-C(norm): method = {r.get(\"name_resolution\", {}).get(\"method\")!r}'
print('PASS 7-C(alphanumeric_normalized)')

# Level 4: fuzzy above threshold
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(return_value=httpx.Response(200, json={'services': SERVICES}))
    r = lookup('payment-gateway-servize')   # deliberate typo, high similarity
nm = r.get('name_resolution', {})
if nm:
    assert nm.get('method') == 'fuzzy', f'FAIL 7-C(fuzzy): method = {nm.get(\"method\")!r}'
    assert isinstance(nm.get('similarity'), float), f'FAIL 7-C(fuzzy): similarity not a float'
    print(f'PASS 7-C(fuzzy): matched with similarity={nm[\"similarity\"]}')
else:
    print('WARN 7-C(fuzzy): typo did not reach fuzzy threshold — adjust test input or verify threshold')

# Level 4: fuzzy below threshold → service_not_found
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(return_value=httpx.Response(200, json={'services': SERVICES}))
    r = lookup('zzzzzzz')
assert r.get('status') == 'error' or r.get('error', {}).get('error_code') == 'service_not_found', \
    f'FAIL 7-C(below-threshold): expected service_not_found; got: {r}'
print('PASS 7-C(below-threshold): service_not_found returned')

_findit._cache.clear()
"
```

### 7-D — no_tags_found vs no_parseable_tags are distinct errors

```bash
uv run python -c "
from unittest.mock import patch, MagicMock
from migration_oracle.paysafe.gitlab import list_tags
from migration_oracle.paysafe.resolver import resolve

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}

# Case 1: repo has zero tags (git ls-remote returns empty)
empty_proc = MagicMock(returncode=0, stdout='', stderr='')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=empty_proc):
    result_no_tags = resolve('my-lib', target_version='3.5.6')

assert result_no_tags['status'] == 'error', f'FAIL 7-D(no_tags_found): expected error, got {result_no_tags}'
assert result_no_tags['error']['error_code'] == 'no_tags_found', \
    f'FAIL 7-D(no_tags_found): error_code = {result_no_tags[\"error\"][\"error_code\"]!r}'
print(f'PASS 7-D(no_tags_found): no_tags_found returned when repo has zero tags')

# Case 2: repo has tags but all fail parsing (all unparseable)
unparseable_proc = MagicMock(returncode=0,
    stdout='abc\trefs/tags/not-a-version\ndef\trefs/tags/also-not-semver\n', stderr='')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=unparseable_proc):
    result_no_parse = resolve('my-lib', target_version='3.5.6')

assert result_no_parse['status'] == 'error', f'FAIL 7-D(no_parseable_tags): expected error'
assert result_no_parse['error']['error_code'] == 'no_parseable_tags', \
    f'FAIL 7-D(no_parseable_tags): error_code = {result_no_parse[\"error\"][\"error_code\"]!r}'
print('PASS 7-D(no_parseable_tags): no_parseable_tags returned when tags exist but all fail parsing')
"
```

### 7-E — max_tags limit respected (scan stops after max_tags tags)

```bash
uv run python -c "
from unittest.mock import patch, MagicMock, call
from migration_oracle.paysafe.resolver import resolve
from migration_oracle.paysafe._types import CompatibilityInfo

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}

# 20 tags, none compatible with 3.5.6 (all declare 3.4.x)
tags = [f'3.4.{i}' for i in range(19, -1, -1)]

fetch_calls = []
def mock_compat(repo_url, tag):
    fetch_calls.append(tag)
    return CompatibilityInfo(framework_version='3.4.0', source_file='pom.xml', source_precedence='spring-boot-starter-parent')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=tags), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=mock_compat):
    result = resolve('my-lib', target_version='3.5.6', allow_latest_overall=False, max_tags=5)

assert len(fetch_calls) <= 5, f'FAIL 7-E: scanned {len(fetch_calls)} tags but max_tags=5; tags scanned: {fetch_calls}'
print(f'PASS 7-E: max_tags=5 limit respected — scanned {len(fetch_calls)} tags: {fetch_calls}')
"
```

### 7-F — latest_with_known_compatibility vs latest_overall when target_version is None

```bash
uv run python -c "
from unittest.mock import patch
from migration_oracle.paysafe.resolver import resolve
from migration_oracle.paysafe._types import CompatibilityInfo

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}

# Case 1: build file readable → latest_with_known_compatibility
def mock_compat_readable(repo_url, tag):
    return CompatibilityInfo(framework_version='3.5.10', source_file='pom.xml', source_precedence='spring-boot-starter-parent')

with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=['3.5.10']), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=mock_compat_readable), \
     patch('migration_oracle.paysafe.gitlab.detect_framework_at_head', return_value='spring-boot'):
    result_readable = resolve('my-lib', allow_latest_overall=True)

assert result_readable['status'] == 'ok', f'FAIL 7-F(readable): {result_readable}'
assert result_readable['selection_strategy'] == 'latest_with_known_compatibility', \
    f'FAIL 7-F(readable): strategy = {result_readable[\"selection_strategy\"]!r}'
assert result_readable['framework_version'] is not None, 'FAIL 7-F(readable): framework_version should be populated'
print(f'PASS 7-F(readable): latest_with_known_compatibility selected, framework_version={result_readable[\"framework_version\"]!r}')

# Case 2: build file unreadable → latest_overall
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.list_tags', return_value=['3.5.10']), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', return_value=None), \
     patch('migration_oracle.paysafe.gitlab.detect_framework_at_head', return_value=None):
    result_unreadable = resolve('my-lib', allow_latest_overall=True)

assert result_unreadable['status'] == 'ok', f'FAIL 7-F(unreadable): {result_unreadable}'
assert result_unreadable['selection_strategy'] == 'latest_overall', \
    f'FAIL 7-F(unreadable): strategy = {result_unreadable[\"selection_strategy\"]!r}'
assert result_unreadable['framework_version'] is None, \
    f'FAIL 7-F(unreadable): framework_version should be None'
print('PASS 7-F(unreadable): latest_overall selected when build file unreadable')
"
```

### 7-G — Build file parser: Spring Boot and Angular source_precedence values

```bash
uv run python -c "
from unittest.mock import patch, MagicMock
from migration_oracle.paysafe.gitlab import fetch_framework_version

REPO = 'git@gitlab.paysafe.com:test/repo.git'

# Prepare a mock git archive that returns a specific file
def make_archive_mock(filename, content):
    import tarfile, io
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w') as tar:
        encoded = content.encode()
        info = tarfile.TarInfo(name=filename)
        info.size = len(encoded)
        tar.addfile(info, io.BytesIO(encoded))
    buf.seek(0)
    m = MagicMock(returncode=0, stderr='')
    m.stdout = buf.read()
    return m

# Test 1: spring-boot-starter-parent in POM
POM_PARENT = '''<project><parent><groupId>org.springframework.boot</groupId>
<artifactId>spring-boot-starter-parent</artifactId><version>3.5.10</version></parent></project>'''

with patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=make_archive_mock('pom.xml', POM_PARENT)):
    info = fetch_framework_version(REPO, '3.5.10')
assert info is not None, 'FAIL 7-G(pom-parent): fetch_framework_version returned None'
assert info.framework_version == '3.5.10', f'FAIL 7-G(pom-parent): version = {info.framework_version!r}'
assert info.source_precedence == 'spring-boot-starter-parent', f'FAIL 7-G(pom-parent): precedence = {info.source_precedence!r}'
print(f'PASS 7-G(spring-boot-starter-parent): version={info.framework_version!r}, precedence={info.source_precedence!r}')

# Test 2: @angular/core in package.json
PKG_JSON = '{\"dependencies\": {\"@angular/core\": \"^18.2.0\"}}'

with patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=make_archive_mock('package.json', PKG_JSON)):
    info_ng = fetch_framework_version(REPO, '18.2.0')
assert info_ng is not None, 'FAIL 7-G(angular): fetch_framework_version returned None for package.json'
assert '18.2' in info_ng.framework_version, f'FAIL 7-G(angular): version = {info_ng.framework_version!r}'
assert info_ng.source_precedence == 'angular-core-dep', f'FAIL 7-G(angular): precedence = {info_ng.source_precedence!r}'
print(f'PASS 7-G(angular-core-dep): version={info_ng.framework_version!r}, precedence={info_ng.source_precedence!r}')
"
```

### 7-H — Framework detection probe order at HEAD

```bash
uv run python -c "
from unittest.mock import patch, MagicMock, call
from migration_oracle.paysafe.gitlab import detect_framework_at_head

REPO = 'git@gitlab.paysafe.com:test/repo.git'

# When pom.xml is found first, spring-boot returned without checking others
call_log = []
def probe_ls_remote(cmd, **kw):
    call_log.append(cmd)
    m = MagicMock(returncode=0, stderr='')
    # Simulate pom.xml existing at HEAD
    if 'pom.xml' in str(cmd):
        m.stdout = 'abc123\tHEAD'
    else:
        m.stdout = ''
    return m

with patch('migration_oracle.paysafe.gitlab.subprocess.run', side_effect=probe_ls_remote):
    framework = detect_framework_at_head(REPO)

assert framework == 'spring-boot', f'FAIL 7-H: pom.xml found but framework = {framework!r}'
# build.gradle and package.json should NOT have been probed
probed_files = [str(c) for c in call_log]
gradle_probed = any('build.gradle' in f for f in probed_files)
assert not gradle_probed, f'FAIL 7-H: build.gradle was probed despite pom.xml being found first'
print(f'PASS 7-H: framework detection stops at first match (pom.xml → spring-boot)')
"
```

### 7-I — All canonical error codes are reachable and correctly formatted

```bash
uv run python -c "
from unittest.mock import patch, MagicMock
from migration_oracle.paysafe.resolver import resolve
import httpx

FINDIT_RECORD = {'name': 'my-lib', 'codeRepoLink': 'https://gitlab.paysafe.com/my-lib.git'}
FINDIT_NO_REPO = {'name': 'my-lib'}  # no codeRepoLink

def assert_error(result, expected_code, label):
    assert result['status'] == 'error', f'FAIL 7-I({label}): status = {result.get(\"status\")!r}'
    code = result['error']['error_code']
    assert code == expected_code, f'FAIL 7-I({label}): error_code = {code!r}, expected {expected_code!r}'
    for field in ('message', 'recoverable', 'actionable_hint', 'details'):
        assert field in result['error'], f'FAIL 7-I({label}): error sub-field {field!r} missing'
    print(f'PASS 7-I({label}): {expected_code}')

# 1. invalid_service_name
r = resolve('')
assert_error(r, 'invalid_service_name', 'invalid_service_name')

# 2. service_not_found — FindIt returns empty list
import respx
import migration_oracle.paysafe.findit as _findit
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(
        return_value=httpx.Response(200, json={'services': []}))
    r = resolve('no-such-service', target_version='3.5.6')
assert_error(r, 'service_not_found', 'service_not_found')
_findit._cache.clear()

# 3. no_repo_url — FindIt record has no codeRepoLink
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_NO_REPO):
    r = resolve('my-lib', target_version='3.5.6')
assert_error(r, 'no_repo_url', 'no_repo_url')

# 4. no_tags_found — git ls-remote returns nothing
empty_proc = MagicMock(returncode=0, stdout='', stderr='')
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=empty_proc):
    r = resolve('my-lib', target_version='3.5.6')
assert_error(r, 'no_tags_found', 'no_tags_found')

# 5. no_parseable_tags
bad_proc = MagicMock(returncode=0, stdout='abc\trefs/tags/not-semver\n', stderr='')
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=bad_proc):
    r = resolve('my-lib', target_version='3.5.6')
assert_error(r, 'no_parseable_tags', 'no_parseable_tags')

# 6. no_compatible_version
from migration_oracle.paysafe._types import CompatibilityInfo
def low_compat(repo_url, tag):
    return CompatibilityInfo(framework_version='3.4.0', source_file='pom.xml', source_precedence='spring-boot-starter-parent')
good_proc = MagicMock(returncode=0, stdout='abc\trefs/tags/3.4.0\n', stderr='')
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=good_proc), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=low_compat):
    r = resolve('my-lib', target_version='3.5.6', allow_latest_overall=False)
assert_error(r, 'no_compatible_version', 'no_compatible_version')

# 7. compatibility_unknown — all tags have build files that declare no parseable version
def unknown_compat(repo_url, tag):
    return None
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=good_proc), \
     patch('migration_oracle.paysafe.gitlab.fetch_framework_version', side_effect=unknown_compat):
    r = resolve('my-lib', target_version='3.5.6', allow_latest_overall=False)
assert_error(r, 'compatibility_unknown', 'compatibility_unknown')

# 8. http_timeout — FindIt times out
import migration_oracle.paysafe.findit as _findit
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(side_effect=httpx.TimeoutException('timeout'))
    r = resolve('my-lib', target_version='3.5.6')
assert_error(r, 'http_timeout', 'http_timeout')
_findit._cache.clear()

# 9. http_request_failed — FindIt returns non-2xx
_findit._cache.clear()
with respx.mock:
    respx.get('https://findit-api.icd.paysafe.cloud/services').mock(return_value=httpx.Response(503))
    r = resolve('my-lib', target_version='3.5.6')
assert_error(r, 'http_request_failed', 'http_request_failed')
_findit._cache.clear()

# 10. git_ls_remote_failed — subprocess returns non-zero
fail_proc = MagicMock(returncode=128, stdout='', stderr='fatal: repository not found')
with patch('migration_oracle.paysafe.findit.lookup', return_value=FINDIT_RECORD), \
     patch('migration_oracle.paysafe.gitlab.subprocess.run', return_value=fail_proc):
    r = resolve('my-lib', target_version='3.5.6')
assert_error(r, 'git_ls_remote_failed', 'git_ls_remote_failed')
"
```

### 7-J — Full test suite passes clean

```bash
uv run pytest tests/paysafe/ -v --tb=short 2>&1 | tail -20
# Expected: all tests green, no failures, no errors
```

Check the final line — it must read `passed` with zero `failed` or `error`.

### 7-K — Live smoke test (optional — requires FINDIT_AUTH_TOKEN and network)

Skip this check if `FINDIT_AUTH_TOKEN` is not set or the FindIt registry is unreachable.

```bash
uv run python -c "
import os
token = os.environ.get('FINDIT_AUTH_TOKEN', '')
if not token:
    print('SKIP 7-K: FINDIT_AUTH_TOKEN not set — live smoke test skipped')
    exit(0)

from migration_oracle.paysafe.resolver import resolve
import json

result = resolve(
    service_name='payment-service',
    target_version='3.5.6',
    framework='spring-boot',
    allow_latest_overall=True,
)
print(json.dumps(result, indent=2))

assert result['status'] in ('ok', 'error'), f'FAIL 7-K: unexpected status: {result.get(\"status\")}'
if result['status'] == 'ok':
    assert isinstance(result['effective_settings'], dict), 'FAIL 7-K: effective_settings must be dict'
    assert isinstance(result.get('compatibility'), (dict, type(None))), \
        f'FAIL 7-K: compatibility must be dict or None, got {type(result.get(\"compatibility\"))}'
    print(f'PASS 7-K: live resolution returned strategy={result[\"selection_strategy\"]!r}')
else:
    print(f'PASS 7-K: live call returned structured error: {result[\"error\"][\"error_code\"]!r}')
"
```

---

## Completion gate checklist

Update `docs/SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| Check | Description | Result |
|-------|-------------|--------|
| 0-A | All 5 paysafe modules import without error | |
| 0-B | `FINDIT_BASE_URL` default contains `findit-api.icd.paysafe.cloud` | |
| 0-C | `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` default is `0.68` | |
| 0-D | `GITLAB_API_KEY` in `config.py` with string default | |
| 0-E | `ResolverResult` has all 11 required fields | |
| 0-F | `SelectionStrategy` has exactly 4 canonical values | |
| 0-G | All 10 canonical `error_code` values present in `_types.py` | |
| 0-H | No `datetime.utcnow()` in `migration_oracle/paysafe/` | |
| 0-I | No graph driver or pipeline imports in `migration_oracle/paysafe/` | |
| 0-J | No direct `os.environ` / `os.getenv` reads in `migration_oracle/paysafe/` | |
| 0-K | `subprocess` calls confined to `gitlab.py` only | |
| 1-A | `resolve()` has all 7 parameters | |
| 1-B | `allow_latest_overall` defaults to `False` | |
| 1-C | `max_tags` default is a positive integer (confirm value matches reference doc) | |
| 1-D | `resolve()` returns a `dict` and never raises for any input | |
| 1-E | Error response always nested under `result["error"]` key | |
| 1-F | Error sub-dict has all 5 required fields with correct types | |
| 2-A | Pinned mode makes zero network calls | |
| 2-B | Pinned mode result has all 11 fields; `name_resolution` absent | |
| 2-C | FindIt service list fetched once for two lookups within 30-day window | |
| 2-D | Stale cache (31 days) triggers exactly one re-fetch | |
| 2-E | Full `latest_compatible` resolution end-to-end with mocked deps | |
| 2-F | `compatibility` field is a `dict` with `source_precedence` key (not a boolean) | |
| 2-G | `latest_overall` fallback returned when `allow_latest_overall=True` and no compatible tag | |
| 2-H | `no_compatible_version` error when `allow_latest_overall=False` and no compatible tag | |
| 2-I | `name_resolution` present on non-exact match; absent on exact match | |
| 2-J | Resolver does not default `allow_latest_overall` to `True` | |
| 7-A | All 20 compatibility rule version pairs produce correct boolean | |
| 7-B | `v`-prefix stripped; alphabetic suffix handled; unparseable tags skipped; descending order | |
| 7-C | All 4 name-matching levels produce correct `method` labels; below-threshold → `service_not_found` | |
| 7-D | `no_tags_found` and `no_parseable_tags` are distinct error codes triggered correctly | |
| 7-E | `max_tags` limit respected — scan stops after N tags | |
| 7-F | `latest_with_known_compatibility` vs `latest_overall` selected correctly when `target_version=None` | |
| 7-G | `pom.xml`, `package.json` parsed correctly with correct `source_precedence` values | |
| 7-H | Framework detection stops at first matching build file (probe order: pom.xml → gradle → package.json) | |
| 7-I | All 10 canonical error codes reachable and return correctly nested structured error | |
| 7-J | `uv run pytest tests/paysafe/ -v` exits 0 with zero failures | |
| 7-K | *(optional)* Live FindIt smoke test returns structured result with `effective_settings` dict | |

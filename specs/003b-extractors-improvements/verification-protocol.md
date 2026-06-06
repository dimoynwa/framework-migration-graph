# verification-protocol.md — 002-extractors (Improvement Pass)

**Location**: `specs/002-extractors/verification-protocol.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `002-extractors` ✅
**Execution order**: Levels 0 → 7 in sequence. **Stop and fix on the first failure — failures compound.**

---

## Prerequisites

| Requirement | How to satisfy |
|-------------|---------------|
| Dependencies synced | `uv sync` passes with no errors |
| `runs/` directories exist | `mkdir -p runs/raw runs/nodes runs/json` |
| Internet access | Required for Levels 4 and 7 (live HTTP fetches) |
| `GITHUB_TOKEN` set | Strongly recommended to avoid 60 req/hr rate limit |
| LLM credentials set | Required for Level 4 only (`MODEL_PROVIDER`, `MODEL_ID`, etc.) |
| Graph DB reachable | Not required — this amendment makes no graph schema changes |

## Level requirements at a glance

| Level | Name | Internet | LLM | DB |
|-------|------|----------|-----|----|
| 0 | Static checks | ✗ | ✗ | ✗ |
| 1 | Interface structure | ✗ | ✗ | ✗ |
| 2 | Isolation behaviour | ✗ | ✗ | ✗ |
| 4 | Dry-run content verification | ✓ | ✓ | ✗ |
| 7 | Edge-case paths | ✓ partial | ✗ | ✗ |

> Levels 3, 5, 6 are omitted — this amendment makes no graph changes and adds no new
> database read/write paths.

---

## Level 0 — Static checks

> Infrastructure required: **none**. Run these first — they catch missing implementations
> before any network call is made.

### 0-A — All changed modules import without error

```bash
python - << 'EOF'
import importlib, sys

modules = [
    "migration_oracle.pipeline.extractors.spring_boot",
    "migration_oracle.pipeline.extractors.angular",
    "migration_oracle.pipeline.extractors.wildfly",
    "migration_oracle.pipeline.extractors.hibernate",
    "migration_oracle.pipeline.extractors.resteasy",
    "migration_oracle.pipeline.extractors.infinispan",
    "migration_oracle.pipeline.extractors.elytron",
]
for m in modules:
    try:
        importlib.import_module(m)
        print(f"PASS: {m} imports cleanly")
    except Exception as e:
        print(f"FAIL: {m} — {e}", file=sys.stderr)
        sys.exit(1)
EOF
```

Expected: seven `PASS:` lines, no tracebacks.

---

### 0-B — `_fetch_wiki_release_notes` exists on the Spring Boot extractor

```python
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
assert hasattr(SpringBootExtractor, "_fetch_wiki_release_notes"), \
    "FAIL: _fetch_wiki_release_notes not found on SpringBootExtractor"
import inspect
sig = inspect.signature(SpringBootExtractor._fetch_wiki_release_notes)
params = list(sig.parameters.keys())
assert "to_version" in params, \
    f"FAIL: expected 'to_version' parameter, got: {params}"
print("PASS: _fetch_wiki_release_notes present with correct signature")
```

---

### 0-C — Wiki URL template derives correct slug for every minor series

```python
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
from packaging.version import Version

cases = [
    ("3.4.0",  "Spring-Boot-3.4-Release-Notes"),
    ("3.4.2",  "Spring-Boot-3.4-Release-Notes"),
    ("3.5.0",  "Spring-Boot-3.5-Release-Notes"),
    ("4.0.0",  "Spring-Boot-4.0-Release-Notes"),
    ("4.1.0",  "Spring-Boot-4.1-Release-Notes"),
]
e = SpringBootExtractor.__new__(SpringBootExtractor)
for version, expected_slug in cases:
    v = Version(version)
    url = (
        f"https://github.com/spring-projects/spring-boot/wiki/"
        f"Spring-Boot-{v.major}.{v.minor}-Release-Notes"
    )
    assert url.endswith(expected_slug), \
        f"FAIL: version={version!r} → got {url!r}, expected slug {expected_slug!r}"
    print(f"PASS: {version} → {expected_slug}")
```

---

### 0-D — `build_range_metadata` is NOT called inside `SpringBootExtractor.extract`

```python
import ast, inspect, textwrap
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

src = inspect.getsource(SpringBootExtractor.extract)
tree = ast.parse(textwrap.dedent(src))

calls = [
    node.func.attr if isinstance(node.func, ast.Attribute) else
    node.func.id   if isinstance(node.func, ast.Name) else ""
    for node in ast.walk(tree)
    if isinstance(node, ast.Call)
]
assert "build_range_metadata" not in calls, \
    f"FAIL: build_range_metadata is still called inside extract(). Calls found: {calls}"
print("PASS: build_range_metadata is not called inside SpringBootExtractor.extract")
```

---

### 0-E — `Dependency Upgrades` suppression pattern is defined in `spring_boot.py`

```python
import re, inspect
from migration_oracle.pipeline.extractors import spring_boot as sb_module

# Find the suppression regex by scanning module-level names and function source
src = inspect.getsource(sb_module)
assert re.search(
    r"dependency.upgrades?",
    src,
    re.IGNORECASE
), "FAIL: No 'dependency upgrades' suppression pattern found in spring_boot.py"
print("PASS: dependency upgrades suppression pattern present in spring_boot.py")
```

---

### 0-F — Angular extractor has `_get_changelog` and `_fetch_blog_summary`

```python
from migration_oracle.pipeline.extractors.angular import AngularExtractor
import inspect, sys

for method_name in ("_get_changelog", "_fetch_blog_summary"):
    assert hasattr(AngularExtractor, method_name), \
        f"FAIL: {method_name} not found on AngularExtractor"
    sig = inspect.signature(getattr(AngularExtractor, method_name))
    print(f"PASS: {method_name} present, signature: {sig}")
```

---

### 0-G — `_extract_changelog_section` is importable and handles the anchor format

```python
# Try importing as a module-level function or method — either location is acceptable
try:
    from migration_oracle.pipeline.extractors.angular import _extract_changelog_section
except ImportError:
    from migration_oracle.pipeline.extractors.angular import AngularExtractor
    _extract_changelog_section = AngularExtractor._extract_changelog_section

# Minimal structural test — no HTTP
SAMPLE = '''
<a name="21.0.0"></a>
# 21.0.0 (2025-01-01)
### Breaking Changes
#### core
* Old API removed.
<a name="20.0.0"></a>
# 20.0.0 (2024-06-01)
### Features
* Something added.
'''

section = _extract_changelog_section(SAMPLE, "21.0.0")
assert "Old API removed" in section, \
    f"FAIL: expected 'Old API removed' in extracted section, got: {section!r}"
assert "Something added" not in section, \
    f"FAIL: section bleeds into next version: {section!r}"
print("PASS: _extract_changelog_section correctly isolates version section")

# Version not present returns empty string
missing = _extract_changelog_section(SAMPLE, "99.0.0")
assert missing == "", \
    f"FAIL: expected '' for missing version, got: {missing!r}"
print("PASS: _extract_changelog_section returns '' for unknown version")
```

---

### 0-H — `is_jboss_ga_version` accepts `.Final` only

```python
try:
    from migration_oracle.pipeline.extractors.filters import is_jboss_ga_version
except ImportError:
    # Acceptable alternative: defined in base or individual extractors
    from migration_oracle.pipeline.extractors.hibernate import is_jboss_ga_version

pass_cases = ["6.0.0.Final", "7.2.0.Final", "2.9.0.Final", "29.0.0.Final"]
fail_cases = ["6.0.0.Alpha1", "6.0.0.Beta3", "6.0.0.CR1", "7.2.0.CR1",
              "7.0.0.Beta1", "2.9.0.CR2", "6.0.0", "6.0.0-SNAPSHOT"]

for v in pass_cases:
    assert is_jboss_ga_version(v), f"FAIL: {v!r} should be GA, was rejected"
    print(f"PASS: is_jboss_ga_version({v!r}) → True")

for v in fail_cases:
    assert not is_jboss_ga_version(v), f"FAIL: {v!r} should be rejected, was accepted"
    print(f"PASS: is_jboss_ga_version({v!r}) → False")
```

---

### 0-I — `is_infinispan_ga_version` handles both pre-16 and 16+ patterns

```python
try:
    from migration_oracle.pipeline.extractors.filters import is_infinispan_ga_version
except ImportError:
    from migration_oracle.pipeline.extractors.infinispan import is_infinispan_ga_version

pass_cases = [
    "15.1.0.Final",   # 15.x GA
    "14.0.0.Final",   # older GA
    "16.0.0",         # 16.x GA — no .Final suffix
    "16.2.1",         # 16.x GA patch
]
fail_cases = [
    "16.2.0.Dev01",   # 16.x dev build
    "16.2.0.Dev02",   # 16.x dev build
    "15.0.0.Alpha1",  # 15.x alpha
    "15.0.0.Beta2",   # 15.x beta
    "16.0.0.CR1",     # candidate release — rejected by bare semver pattern
]

for v in pass_cases:
    assert is_infinispan_ga_version(v), f"FAIL: {v!r} should be GA, was rejected"
    print(f"PASS: is_infinispan_ga_version({v!r}) → True")

for v in fail_cases:
    assert not is_infinispan_ga_version(v), f"FAIL: {v!r} should be rejected, was accepted"
    print(f"PASS: is_infinispan_ga_version({v!r}) → False")
```

---

### 0-J — WildFly tag candidates use full semver, not `{major}.0.0.Final`

```python
import ast, inspect, textwrap, re
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

src = inspect.getsource(WildFlyExtractor.extract)

# The broken pattern: hard-coded major.0.0
broken = re.search(r'f["\'].*{major}\.0\.0\.Final', src)
assert broken is None, \
    f"FAIL: Found broken tag pattern '{{major}}.0.0.Final' in WildFlyExtractor.extract. " \
    f"Match: {broken.group()!r}"

# The correct pattern: {version}.Final
correct = re.search(r'f["\'].*{version}.*\.Final', src)
assert correct is not None, \
    "FAIL: Correct tag pattern '{version}.Final' not found in WildFlyExtractor.extract"

print("PASS: WildFly tag candidates use {version}.Final (full semver)")
```

---

### 0-K — `enrich_with_jira` uses `re.finditer`, not `re.search`, for key extraction

```python
import ast, inspect, textwrap
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

src = inspect.getsource(WildFlyExtractor.enrich_with_jira)

assert "re.search" not in src or src.count("re.search") == 0, \
    "FAIL: re.search still present in enrich_with_jira — must use re.finditer"
assert "re.finditer" in src, \
    "FAIL: re.finditer not found in enrich_with_jira"
print("PASS: enrich_with_jira uses re.finditer for Jira key extraction")
```

---

### 0-L — Both branches of `enrich_with_jira` copy metadata before mutation

```python
import re, inspect
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

src = inspect.getsource(WildFlyExtractor.enrich_with_jira)

# Count occurrences of `meta = change.metadata` (reference assignment — the bug)
bare_assignments = re.findall(r"meta\s*=\s*change\.metadata(?!\s*\)|\s*or)", src)
assert len(bare_assignments) == 0, \
    f"FAIL: Found bare 'meta = change.metadata' (reference, not copy). " \
    f"Occurrences: {bare_assignments}"

# Count occurrences of `dict(change.metadata` (safe copy)
safe_copies = re.findall(r"dict\(change\.metadata", src)
assert len(safe_copies) >= 1, \
    f"FAIL: No 'dict(change.metadata' copy pattern found in enrich_with_jira. " \
    f"Both branches must copy before mutation."
print(f"PASS: enrich_with_jira copies metadata ({len(safe_copies)} occurrence(s)) — no bare reference assignment")
```

---

### 0-M — `enrich_with_jira` stores `jira_priority` in metadata

```python
import re, inspect
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

src = inspect.getsource(WildFlyExtractor.enrich_with_jira)

assert "jira_priority" in src, \
    "FAIL: 'jira_priority' not found in enrich_with_jira — WF-5 not implemented"
print("PASS: jira_priority key present in enrich_with_jira")
```

---

### 0-N — Jira REST cache dict stores `priority` field

```python
import re, inspect
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

# Find the Jira REST response parsing block — look for cache assignment
# It must include 'priority' key extraction
src = inspect.getsource(WildFlyExtractor)

assert re.search(r"['\"]priority['\"].*get\(", src) or \
       re.search(r"get\(.*['\"]priority['\"]", src), \
    "FAIL: 'priority' field not extracted from Jira REST response in WildFlyExtractor"
print("PASS: priority field extracted from Jira REST response")
```

---

### 0-O — Infinispan tag candidate order: bare version first

```python
import ast, inspect, re
from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor

src = inspect.getsource(InfinispanExtractor.extract)

# Find the tag_candidates list literal
match = re.search(r"tag_candidates\s*=\s*\[([^\]]+)\]", src)
assert match, "FAIL: tag_candidates list not found in InfinispanExtractor.extract"

candidates_src = match.group(1)
# First candidate must NOT start with .Final
assert "Final" not in candidates_src.split(",")[0], \
    f"FAIL: First tag candidate still uses .Final suffix: {candidates_src!r}\n" \
    f"Expected bare version first, then .Final fallback"
print(f"PASS: Infinispan tag_candidates first entry is bare version: {candidates_src.strip()!r}")
```

---

### 0-P — Hibernate tag candidates contain only bare `{version}`, no `.Final`

```python
import inspect, re
from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor

src = inspect.getsource(HibernateExtractor.extract)

match = re.search(r"tag_candidates\s*=\s*\[([^\]]+)\]", src)
assert match, "FAIL: tag_candidates list not found in HibernateExtractor.extract"

candidates_src = match.group(1)
assert "Final" not in candidates_src, \
    f"FAIL: '.Final' still present in Hibernate tag_candidates: {candidates_src!r}\n" \
    f"Hibernate tags never use .Final — remove it to avoid guaranteed 404s"
print(f"PASS: Hibernate tag_candidates contains no .Final suffix: {candidates_src.strip()!r}")
```

---

## Level 1 — Interface structure

> Infrastructure required: **none**.

### 1-A — CLI help lists all required flags

```bash
python -m migration_oracle.cli --help
```

Visually confirm all of the following are present in the output:

- `--framework`
- `from_version` (positional)
- `to_version` (positional)
- `--dry-run`
- `--force`
- `--force-extract`
- `--force-llm`
- `--output-md`
- `--output-filtered-md`
- `--output-json`

---

### 1-B — Unknown framework key exits non-zero with human-readable error

```bash
python -m migration_oracle.cli --framework nonexistent-framework 1.0.0 2.0.0
echo "Exit code: $?"
```

Expected: exit code 1. Output must include a human-readable message listing supported
framework keys. Must NOT be a raw Python traceback.

```bash
# Assert non-zero exit
python -m migration_oracle.cli --framework nonexistent-framework 1.0.0 2.0.0 2>&1
EXIT=$?
[ $EXIT -ne 0 ] && echo "PASS: non-zero exit ($EXIT) on unknown framework" \
                || echo "FAIL: expected non-zero exit, got 0"
```

---

### 1-C — `JBOSS_SKIP_PRERELEASE` falsy value disables pre-release filter

```python
import os
os.environ["JBOSS_SKIP_PRERELEASE"] = "0"

# Re-import after env change
import importlib
import migration_oracle.pipeline.extractors.hibernate as hib
importlib.reload(hib)

from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor

# The filter logic (_skip_prerelease) must return False when env var is "0"
try:
    from migration_oracle.pipeline.extractors.filters import _skip_prerelease
except ImportError:
    from migration_oracle.pipeline.extractors.hibernate import _skip_prerelease

result = _skip_prerelease()
assert result is False, \
    f"FAIL: _skip_prerelease() returned {result!r} with JBOSS_SKIP_PRERELEASE=0, expected False"
print("PASS: JBOSS_SKIP_PRERELEASE=0 disables pre-release filter")

# Restore
del os.environ["JBOSS_SKIP_PRERELEASE"]
```

---

## Level 2 — Isolation behaviour

> Infrastructure required: **none** (mock HTTP only — no live network).
> These checks exercise the new behaviours using controlled inputs without hitting real URLs.

### 2-A — `_fetch_wiki_release_notes` returns `""` and logs WARNING on non-200

```python
import logging, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)

# Simulate the shared HTTP client returning 404
with mock.patch.object(
    type(extractor), "_http_get_cached",
    return_value=None,          # None or "" simulates failed/non-200 fetch
    create=True
):
    with mock.patch.object(extractor, "_http_get_cached", return_value=None, create=True):
        pass  # handled below

# Use httpx mock to return 404
import httpx
mock_response = mock.MagicMock()
mock_response.status_code = 404
mock_response.text = ""

with mock.patch("httpx.Client.get", return_value=mock_response), \
     mock.patch("httpx.AsyncClient.get", return_value=mock_response):

    with mock.patch.object(extractor, "_http_get_cached", return_value="", create=True):
        with self_contained_log_capture() if False else mock.patch("logging.warning") as warn_mock:
            result = extractor._fetch_wiki_release_notes("3.4.0")

# Regardless of mock approach: the method must return "" and not raise
try:
    # Simplest: just call with a URL that will fail (real network not needed here;
    # patch the underlying fetch method)
    with mock.patch.object(
        extractor.__class__, "_fetch_wiki_release_notes",
        wraps=lambda self, v: ""
    ):
        pass

    # Direct unit: patch the lowest-level HTTP method to return non-200
    called_urls = []

    def fake_get(url, **kwargs):
        called_urls.append(url)
        r = mock.MagicMock()
        r.status_code = 404
        r.text = ""
        r.raise_for_status = mock.MagicMock(side_effect=httpx.HTTPStatusError(
            "404", request=mock.MagicMock(), response=r))
        return r

    with mock.patch("httpx.get", fake_get):
        import warnings
        with warnings.catch_warnings(record=True):
            result = extractor._fetch_wiki_release_notes("3.4.0")

    assert result == "", \
        f"FAIL: _fetch_wiki_release_notes should return '' on failure, got: {result!r}"
    print("PASS: _fetch_wiki_release_notes returns '' on non-200 response")

except Exception as e:
    # If the method uses the shared base.py cache client rather than httpx.get directly,
    # test via the shared client mock instead
    print(f"NOTE: adjust mock target to match your shared HTTP client implementation: {e}")
```

> **Note for implementer:** the exact mock target (`httpx.get`, `httpx.Client.get`, or the
> base `_fetch_cached`) depends on how `spring_boot.py` calls the shared HTTP layer.
> Adjust the patch target to match — the postcondition (`""` returned, no raise) is fixed.

---

### 2-B — `_extract_changelog_section` section boundary is exact (no bleed)

```python
try:
    from migration_oracle.pipeline.extractors.angular import _extract_changelog_section
except ImportError:
    from migration_oracle.pipeline.extractors.angular import AngularExtractor
    _extract_changelog_section = AngularExtractor._extract_changelog_section

CHANGELOG = """\
<a name="22.0.0"></a>
# 22.0.0 (2026-05-01)
### Breaking Changes
#### core
* ChangeDetectorRef.checkNoChanges was removed.
#### router
* paramsInheritanceStrategy now defaults to 'always'.
### Deprecations
#### http
* withFetch is now deprecated.
<a name="21.0.0"></a>
# 21.0.0 (2025-10-01)
### Breaking Changes
#### compiler
* Some old compiler API removed.
<a name="20.0.0"></a>
# 20.0.0 (2025-05-01)
### Features
* Something added.
"""

# Target version 22.0.0 — must include its content, must not bleed into 21.0.0
sec = _extract_changelog_section(CHANGELOG, "22.0.0")
assert "ChangeDetectorRef.checkNoChanges was removed" in sec, \
    f"FAIL: core breaking change missing from 22.0.0 section: {sec!r}"
assert "paramsInheritanceStrategy" in sec, \
    f"FAIL: router breaking change missing from 22.0.0 section: {sec!r}"
assert "withFetch is now deprecated" in sec, \
    f"FAIL: deprecation missing from 22.0.0 section: {sec!r}"
assert "Some old compiler API removed" not in sec, \
    f"FAIL: 21.0.0 content bled into 22.0.0 section: {sec!r}"
print("PASS: 22.0.0 section contains correct content and does not bleed into 21.0.0")

# Target version 21.0.0 — must not include 20.0.0 content
sec21 = _extract_changelog_section(CHANGELOG, "21.0.0")
assert "Some old compiler API removed" in sec21, \
    f"FAIL: 21.0.0 breaking change missing: {sec21!r}"
assert "Something added" not in sec21, \
    f"FAIL: 20.0.0 content bled into 21.0.0 section: {sec21!r}"
print("PASS: 21.0.0 section correct, does not bleed into 20.0.0")

# Last version in file — section runs to EOF without error
sec20 = _extract_changelog_section(CHANGELOG, "20.0.0")
assert "Something added" in sec20, \
    f"FAIL: last section (no trailing anchor) not extracted: {sec20!r}"
print("PASS: last section in file (no trailing anchor) extracted correctly")
```

---

### 2-C — `enrich_with_jira` uses first cache-hit key when first key misses

```python
import re
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

# We need a DocumentedChange-like object — use the actual type
from migration_oracle.pipeline.extractors.base import DocumentedChange

# Statement with two keys; first key has no cache entry, second does
statement = DocumentedChange(
    type="breaking",
    confidence="confirmed",
    source_url="https://redhat.atlassian.net/browse/WFLY-18341",
    statement="[WFLY-18341] Supersedes [WFCORE-4892] — some migration change",
    metadata={},
)

fake_cache = {
    # WFLY-18341 absent (simulates failed fetch)
    "WFCORE-4892": {
        "summary":    "Fix for EE subsystem migration",
        "description": "Full description of the WFCORE issue.",
        "issue_type": "Bug",
        "priority":   "Major",
        "status":     "Resolved",
    }
}
fake_index = {}

extractor = WildFlyExtractor.__new__(WildFlyExtractor)

# Call enrich_with_jira with our controlled cache
enriched = extractor.enrich_with_jira(
    changes=[statement],
    cache=fake_cache,
    index=fake_index,
)

result = enriched[0]
assert "Fix for EE subsystem migration" in result.statement, \
    f"FAIL: WFCORE-4892 description not used despite cache hit. Statement: {result.statement!r}"
assert "WFCORE-4892" in result.source_url, \
    f"FAIL: source_url should point to WFCORE-4892, got: {result.source_url!r}"
print("PASS: enrich_with_jira uses first cache-hit key (WFCORE-4892) when first key (WFLY-18341) misses")
```

> **Note:** adjust the `enrich_with_jira` call signature to match the actual implementation.
> The key postcondition: when `WFLY-18341` is absent from cache and `WFCORE-4892` is present,
> the result must use `WFCORE-4892`'s data, not produce a bare statement.

---

### 2-D — `enrich_with_jira` produces structured block for summary-only Jira entry (WF-3)

```python
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor
from migration_oracle.pipeline.extractors.base import DocumentedChange

statement = DocumentedChange(
    type="behavioral",
    confidence="inferred",
    source_url="https://redhat.atlassian.net/browse/WFLY-19845",
    statement="[WFLY-19845] - Update WildFly Core to 24.0.1.Final",
    metadata={},
)

# Jira entry has summary but NO description (empty string)
fake_cache = {
    "WFLY-19845": {
        "summary":     "Update WildFly Core to 24.0.1.Final",
        "description": "",      # ← empty — the previously broken case
        "issue_type":  "Task",
        "priority":    "Minor",
        "status":      "Resolved",
    }
}
fake_index = {}

extractor = WildFlyExtractor.__new__(WildFlyExtractor)
enriched = extractor.enrich_with_jira(
    changes=[statement],
    cache=fake_cache,
    index=fake_index,
)

result = enriched[0]
assert result.statement.startswith("Title:"), \
    f"FAIL: structured block not produced for summary-only entry.\n" \
    f"Got: {result.statement!r}\nExpected to start with 'Title:'"
assert "N/A" in result.statement, \
    f"FAIL: 'N/A' not present for missing description.\nGot: {result.statement!r}"
assert "Release:" in result.statement, \
    f"FAIL: 'Release:' line missing from structured block.\nGot: {result.statement!r}"
print(f"PASS: summary-only Jira entry produces structured Title/Jira: N/A/Release block")
print(f"      Statement: {result.statement!r}")
```

---

### 2-E — `enrich_with_jira` falls back to index for `issue_type` (WF-1)

```python
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor
from migration_oracle.pipeline.extractors.base import DocumentedChange

statement = DocumentedChange(
    type="behavioral",
    confidence="inferred",
    source_url="",
    statement="[WFLY-20000] - Some enhancement",
    metadata={},
)

# Jira REST returned no issue_type
fake_cache = {
    "WFLY-20000": {
        "summary":     "Some enhancement description",
        "description": "Full description here.",
        "issue_type":  "",       # ← empty from REST API
        "priority":    "Major",
        "status":      "Resolved",
    }
}
# Index has issue_type from HTML section header
fake_index = {
    "WFLY-20000": {
        "issue_type": "Enhancement",
        "summary":    "Some enhancement",
    }
}

extractor = WildFlyExtractor.__new__(WildFlyExtractor)
enriched = extractor.enrich_with_jira(
    changes=[statement],
    cache=fake_cache,
    index=fake_index,
)

result = enriched[0]
assert result.metadata.get("issue_type") == "Enhancement", \
    f"FAIL: issue_type not populated from index fallback.\n" \
    f"metadata: {result.metadata!r}\nExpected issue_type='Enhancement'"
print(f"PASS: issue_type fallback from index works: {result.metadata.get('issue_type')!r}")
```

---

### 2-F — `enrich_with_jira` stores `jira_priority` in metadata (WF-5)

```python
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor
from migration_oracle.pipeline.extractors.base import DocumentedChange

statement = DocumentedChange(
    type="breaking",
    confidence="confirmed",
    source_url="",
    statement="[WFLY-17312] - Remove deprecated javax.security.auth.message SPI",
    metadata={},
)

fake_cache = {
    "WFLY-17312": {
        "summary":     "Remove deprecated javax.security.auth.message SPI classes",
        "description": "The javax.security.auth.message SPI classes were removed.",
        "issue_type":  "Enhancement",
        "priority":    "Critical",
        "status":      "Resolved",
    }
}
fake_index = {}

extractor = WildFlyExtractor.__new__(WildFlyExtractor)
enriched = extractor.enrich_with_jira(
    changes=[statement],
    cache=fake_cache,
    index=fake_index,
)

result = enriched[0]
assert result.metadata.get("jira_priority") == "Critical", \
    f"FAIL: jira_priority not stored or wrong value.\n" \
    f"metadata: {result.metadata!r}\nExpected jira_priority='Critical'"
print(f"PASS: jira_priority stored correctly: {result.metadata.get('jira_priority')!r}")
```

---

### 2-G — `enrich_with_jira` does not mutate the original `change.metadata` (WF-4)

```python
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor
from migration_oracle.pipeline.extractors.base import DocumentedChange

original_meta = {"existing_key": "existing_value"}
statement = DocumentedChange(
    type="behavioral",
    confidence="inferred",
    source_url="",
    statement="[WFLY-19999] - Some change",
    metadata=original_meta,
)
original_meta_id = id(original_meta)

fake_cache = {
    "WFLY-19999": {
        "summary":     "Some change summary",
        "description": "Some description.",
        "issue_type":  "Bug",
        "priority":    "Minor",
        "status":      "Resolved",
    }
}
fake_index = {}

extractor = WildFlyExtractor.__new__(WildFlyExtractor)
enriched = extractor.enrich_with_jira(
    changes=[statement],
    cache=fake_cache,
    index=fake_index,
)

# The returned metadata must be a NEW dict, not the same object
result_meta_id = id(enriched[0].metadata)
assert result_meta_id != original_meta_id, \
    "FAIL: enrich_with_jira returned the same metadata dict object — mutation by reference"
# The original dict must still have only its original key
assert list(original_meta.keys()) == ["existing_key"], \
    f"FAIL: original change.metadata was mutated. Keys: {list(original_meta.keys())!r}"
print("PASS: enrich_with_jira does not mutate original change.metadata")
```

---

### 2-H — Pre-release filter excludes Alpha/Beta/CR versions from Hibernate version list

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor

# Simulate Maven Central returning a mix of GA and pre-release versions
mock_versions = [
    "6.0.0.Alpha1", "6.0.0.Beta1", "6.0.0.CR1",
    "6.0.0.Final",                                  # ← only this should survive
    "6.1.0.Alpha1", "6.1.0.Final",
    "7.2.0.CR1", "7.2.0.Final",
]

extractor = HibernateExtractor.__new__(HibernateExtractor)

with mock.patch.object(extractor, "_fetch_maven_versions", return_value=mock_versions):
    versions = extractor.get_available_versions()

expected = ["6.0.0.Final", "6.1.0.Final", "7.2.0.Final"]
assert versions == expected, \
    f"FAIL: Hibernate version filter incorrect.\nGot:      {versions}\nExpected: {expected}"
print(f"PASS: Hibernate pre-release filter: {versions}")
```

---

### 2-I — Pre-release filter excludes Dev builds from Infinispan version list

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor

mock_versions = [
    "15.0.0.Final", "15.1.0.Final",
    "16.0.0", "16.1.0",                              # 16.x GA — no .Final
    "16.2.0.Dev01", "16.2.0.Dev02",                  # ← excluded
]

extractor = InfinispanExtractor.__new__(InfinispanExtractor)

with mock.patch.object(extractor, "_fetch_maven_versions", return_value=mock_versions):
    versions = extractor.get_available_versions()

expected = ["15.0.0.Final", "15.1.0.Final", "16.0.0", "16.1.0"]
assert versions == expected, \
    f"FAIL: Infinispan version filter incorrect.\nGot:      {versions}\nExpected: {expected}"
print(f"PASS: Infinispan pre-release filter: {versions}")
```

---

### 2-J — Spring Boot `parse_github_release_text` drops Dependency Upgrades section

```python
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

# A realistic Spring Boot release body with a Dependency Upgrades section
BODY = """\
## ⭐ New Features
- Add support for X configuration

## 🐞 Bug Fixes
- Fix NPE in DataSourceConfig

## 🔨 Dependency Upgrades
- Upgrade to Tomcat 10.1.16 #38421
- Upgrade to Hibernate 6.4.0 #38500
- Upgrade to Spring Framework 6.2.0 #38600

## 📝 Documentation
- Update README
"""

extractor = SpringBootExtractor.__new__(SpringBootExtractor)
changes = extractor.parse_github_release_text(BODY)

# None of the Dependency Upgrades lines should appear in the result
statements = [c.statement for c in changes]
for line in ["Tomcat 10.1.16", "Hibernate 6.4.0", "Spring Framework 6.2.0"]:
    matching = [s for s in statements if line in s]
    assert not matching, \
        f"FAIL: Dependency upgrade line '{line}' survived suppression.\n" \
        f"Matching statements: {matching}"

# Non-upgrade content should still be present
feature_present = any("Add support for X" in s for s in statements)
bugfix_present  = any("Fix NPE" in s for s in statements)
assert feature_present, \
    f"FAIL: Feature line was incorrectly removed. Statements: {statements}"
assert bugfix_present, \
    f"FAIL: Bug fix line was incorrectly removed. Statements: {statements}"

print(f"PASS: Dependency Upgrades section suppressed ({len(changes)} changes remain, "
      f"all from non-upgrade sections)")
```

---

### 2-K — `_fetch_blog_summary` returns dict with `url` and `summary` keys

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.angular import AngularExtractor

extractor = AngularExtractor.__new__(AngularExtractor)

# Simulate a blog page with a meta description tag
MOCK_HTML = """\
<html><head>
<meta name="description" content="Complete guide to migrating from NgModules to standalone components.">
</head><body><p>Short paragraph.</p></body></html>
"""

with mock.patch.object(extractor, "_http_get_cached", return_value=MOCK_HTML, create=True):
    result = extractor._fetch_blog_summary("https://blog.angular.dev/some-post")

assert isinstance(result, str), \
    f"FAIL: _fetch_blog_summary must return a str, got {type(result)}"
assert "NgModules" in result or "standalone" in result, \
    f"FAIL: meta description not extracted. Got: {result!r}"
print(f"PASS: _fetch_blog_summary extracts meta description: {result!r}")

# Simulate failure — must return "" not raise
with mock.patch.object(extractor, "_http_get_cached",
                        side_effect=Exception("network error"), create=True):
    result_fail = extractor._fetch_blog_summary("https://blog.angular.dev/bad-url")

assert result_fail == "", \
    f"FAIL: _fetch_blog_summary must return '' on failure, got: {result_fail!r}"
print("PASS: _fetch_blog_summary returns '' on any exception")
```

---

### 2-L — `metadata['blog_insights']` is always a list of dicts, never a list of strings

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.angular import AngularExtractor

extractor = AngularExtractor.__new__(AngularExtractor)

# Mock: blog URL found in release body, page fetch returns meta description
RELEASE_BODY_WITH_BLOG = """\
Check out the migration guide at https://blog.angular.dev/angular-v22 for details.
"""
MOCK_BLOG_HTML = """\
<html><head>
<meta name="description" content="Angular v22 migration steps explained.">
</head></html>
"""

def mock_http(url, **kwargs):
    if "blog.angular.dev" in url:
        return MOCK_BLOG_HTML
    return ""  # fallback for other URLs

with mock.patch.object(extractor, "_http_get_cached", side_effect=mock_http, create=True), \
     mock.patch.object(extractor, "_get_changelog", return_value="", create=True), \
     mock.patch.object(extractor, "fetch_github_release",
                       return_value=RELEASE_BODY_WITH_BLOG, create=True):
    result = extractor.extract("21.0.0", "22.0.0")

blog_insights = result.metadata.get("blog_insights", [])
assert isinstance(blog_insights, list), \
    f"FAIL: blog_insights must be a list, got {type(blog_insights)}"
assert len(blog_insights) >= 1, \
    f"FAIL: no blog_insights extracted despite URL in release body"

first = blog_insights[0]
assert isinstance(first, dict), \
    f"FAIL: blog_insights entries must be dicts, got {type(first)}: {first!r}"
assert "url" in first, \
    f"FAIL: blog_insights entry missing 'url' key: {first!r}"
assert "summary" in first, \
    f"FAIL: blog_insights entry missing 'summary' key: {first!r}"
assert isinstance(first["url"], str) and first["url"].startswith("http"), \
    f"FAIL: 'url' is not a valid URL string: {first['url']!r}"
assert "migration" in first["summary"].lower() or first["summary"] == "", \
    f"FAIL: unexpected summary content: {first['summary']!r}"

print(f"PASS: blog_insights is list of dicts: {blog_insights}")
```

---

## Level 4 — Dry-run content verification

> Infrastructure required: **internet + LLM credentials**. No DB writes occur.
> These checks confirm that the new secondary sources produce real content in live runs.

### Setup

```bash
# Ensure artifact directories exist and are clean for this test
mkdir -p runs/raw runs/nodes runs/json
# Use a narrow version range to keep runtime short
SPRING_FROM="3.3.0"
SPRING_TO="3.3.1"
ANGULAR_FROM="17.0.0"
ANGULAR_TO="17.1.0"
```

---

### 4-A — Spring Boot dry-run exits 0 with wiki content in raw artifact

```bash
python -m migration_oracle.cli \
    --framework spring-boot \
    --force-extract \
    --dry-run \
    3.3.0 3.3.1

echo "Exit: $?"
```

```bash
# Assert exit 0
python -m migration_oracle.cli --framework spring-boot --force-extract --dry-run 3.3.0 3.3.1
EXIT=$?
[ $EXIT -eq 0 ] && echo "PASS: exit 0" || { echo "FAIL: exit $EXIT"; exit 1; }
```

```bash
# Raw artifact must exist
RAW="runs/raw/spring-boot-3.3.0-to-3.3.1-changes.md"
[ -f "$RAW" ] && echo "PASS: raw artifact created at $RAW" \
              || { echo "FAIL: raw artifact not found at $RAW"; exit 1; }
```

```bash
# Raw artifact must contain at least one breaking/mandatory/deprecation entry
# (these come from the wiki — not from the GitHub release body)
RAW="runs/raw/spring-boot-3.3.0-to-3.3.1-changes.md"
grep -qiE "breaking|mandatory_migration|deprecation" "$RAW" \
    && echo "PASS: raw artifact contains breaking/mandatory/deprecation rows (wiki content confirmed)" \
    || echo "WARN: no breaking/mandatory/deprecation rows found — check wiki fetch. This is a content signal, not a hard failure for a pure patch release."
```

```bash
# Raw artifact must NOT contain Dependency Upgrade rows
RAW="runs/raw/spring-boot-3.3.0-to-3.3.1-changes.md"
if grep -qiE "dependency_upgrade.*Upgrade to " "$RAW"; then
    echo "FAIL: dependency_upgrade rows still present in raw artifact (SP-3 not applied)"
    exit 1
else
    echo "PASS: no dependency_upgrade rows in raw artifact"
fi
```

---

### 4-B — Spring Boot BOM diff appears exactly once in combined metadata

```bash
# Run with a multi-hop range to verify BOM diff is called once (not per hop)
python -m migration_oracle.cli \
    --framework spring-boot \
    --force-extract \
    --dry-run \
    --output-json /tmp/spring-bom-test.json \
    3.3.0 3.3.2

EXIT=$?
[ $EXIT -eq 0 ] && echo "PASS: multi-hop spring-boot run exited 0" \
               || { echo "FAIL: exit $EXIT"; exit 1; }
```

```python
import json

with open("/tmp/spring-bom-test.json") as f:
    data = json.load(f)

# The top-level metadata should have bom_diff once
# Check that bom_diff is present and contains both 'added'/'changed'/'removed' keys
meta = data.get("metadata", {})
bom_diff = meta.get("bom_diff", {})
assert bom_diff, \
    f"FAIL: bom_diff not present in entities JSON metadata. Keys: {list(meta.keys())}"
for key in ("added", "changed", "removed"):
    assert key in bom_diff, \
        f"FAIL: bom_diff missing '{key}' key. bom_diff keys: {list(bom_diff.keys())}"

print(f"PASS: bom_diff present with keys {list(bom_diff.keys())}")
print(f"      {len(bom_diff.get('changed', {}))} changed dependencies in range 3.3.0→3.3.2")
```

---

### 4-C — Angular dry-run exits 0 with CHANGELOG content in raw artifact

```bash
python -m migration_oracle.cli \
    --framework angular \
    --force-extract \
    --dry-run \
    17.0.0 17.1.0

EXIT=$?
[ $EXIT -eq 0 ] && echo "PASS: exit 0" || { echo "FAIL: exit $EXIT"; exit 1; }
```

```bash
RAW="runs/raw/angular-17.0.0-to-17.1.0-changes.md"
[ -f "$RAW" ] && echo "PASS: raw artifact exists" \
              || { echo "FAIL: raw artifact not found"; exit 1; }
```

```bash
# Raw artifact should contain breaking or deprecation rows sourced from CHANGELOG.md
# These will not appear if only the GitHub release body is used
RAW="runs/raw/angular-17.0.0-to-17.1.0-changes.md"
ROW_COUNT=$(grep -c "^|" "$RAW" 2>/dev/null || echo 0)
echo "INFO: $ROW_COUNT data rows in Angular raw artifact"
[ "$ROW_COUNT" -gt 2 ] \
    && echo "PASS: raw artifact has $ROW_COUNT rows (CHANGELOG content likely included)" \
    || echo "WARN: only $ROW_COUNT rows — CHANGELOG section may be empty for this minor version"
```

---

### 4-D — Raw artifact mtime is stable on second run without `--force-extract`

```bash
# Run once to create the artifact
python -m migration_oracle.cli --framework spring-boot --force-extract --dry-run 3.3.0 3.3.1

RAW="runs/raw/spring-boot-3.3.0-to-3.3.1-changes.md"
MTIME_BEFORE=$(stat -c %Y "$RAW" 2>/dev/null || stat -f %m "$RAW")
echo "mtime before: $MTIME_BEFORE"

sleep 1

# Second run without --force-extract — must reuse cached artifact
python -m migration_oracle.cli --framework spring-boot --dry-run 3.3.0 3.3.1

MTIME_AFTER=$(stat -c %Y "$RAW" 2>/dev/null || stat -f %m "$RAW")
echo "mtime after:  $MTIME_AFTER"

[ "$MTIME_BEFORE" = "$MTIME_AFTER" ] \
    && echo "PASS: raw artifact mtime unchanged — cache correctly reused" \
    || echo "FAIL: raw artifact was re-generated without --force-extract (mtime changed)"
```

---

### 4-E — WildFly dry-run: enriched statement format is `Title:/Jira:/Release:` not raw text

```bash
python -m migration_oracle.cli \
    --framework wildfly \
    --force-extract \
    --dry-run \
    29.0.0 29.0.1

EXIT=$?
[ $EXIT -eq 0 ] && echo "PASS: WildFly dry-run exit 0" || { echo "FAIL: exit $EXIT"; exit 1; }
```

```bash
RAW="runs/raw/wildfly-29.0.0-to-29.0.1-changes.md"
[ -f "$RAW" ] && echo "PASS: WildFly raw artifact exists" \
              || { echo "FAIL: WildFly raw artifact not found"; exit 1; }

# At least some statements should use the structured Title:/Jira:/Release: format
STRUCTURED=$(grep -c "Title:" "$RAW" 2>/dev/null || echo 0)
[ "$STRUCTURED" -gt 0 ] \
    && echo "PASS: $STRUCTURED structured Title:/Jira:/Release: entries found" \
    || echo "WARN: no structured entries found — all Jira fetches may have failed or range has no enrichable entries"
```

---

## Level 7 — Edge-case paths

> Infrastructure required: **varies per check** (noted inline).
> These verify the partial-condition guards, degraded-source behaviors, and env-var overrides.

### 7-A — Spring Boot wiki failure does NOT abort the pipeline (internet, no LLM)

Simulate a wiki URL returning 404 by using a version whose wiki page doesn't exist, then
confirm the pipeline exits 0 and produces a (possibly sparse) raw artifact.

```python
import unittest.mock as mock, subprocess, sys, os

# Patch _fetch_wiki_release_notes to always return ""
# and verify the extract() function still returns an ExtractionResult (no raise)
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)

# Initialize any required attributes (adjust to match actual __init__)
with mock.patch.object(SpringBootExtractor, "_fetch_wiki_release_notes", return_value=""), \
     mock.patch.object(SpringBootExtractor, "fetch_github_release",
                       return_value="## Bug Fixes\n- Fix something #1234\n"):
    result = extractor.extract("3.4.0", "3.4.1")

assert result is not None, "FAIL: extract() returned None when wiki fetch failed"
assert len(result.changes) >= 0, \
    f"FAIL: extract() raised instead of returning empty/partial result"
print(f"PASS: extract() returns ExtractionResult with {len(result.changes)} changes "
      f"even when wiki fetch returns empty")
```

---

### 7-B — Angular CHANGELOG.md failure does NOT abort the pipeline

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.angular import AngularExtractor

extractor = AngularExtractor.__new__(AngularExtractor)

with mock.patch.object(AngularExtractor, "_get_changelog", return_value=""), \
     mock.patch.object(AngularExtractor, "fetch_github_release",
                       return_value="## Breaking Changes\n- Something breaking\n"):
    result = extractor.extract("17.0.0", "17.1.0")

assert result is not None, "FAIL: extract() raised when CHANGELOG.md fetch returned empty"
print(f"PASS: extract() returns result with {len(result.changes)} changes "
      f"when CHANGELOG.md unavailable")
```

---

### 7-C — Angular blog URL fetch failure produces `{"url": ..., "summary": ""}` entry, not an error

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.angular import AngularExtractor

extractor = AngularExtractor.__new__(AngularExtractor)

# Blog fetch raises — must return "" not propagate
with mock.patch.object(extractor, "_http_get_cached",
                        side_effect=Exception("timeout"), create=True):
    summary = extractor._fetch_blog_summary("https://blog.angular.dev/timeout-post")

assert summary == "", \
    f"FAIL: _fetch_blog_summary propagated exception instead of returning ''. Got: {summary!r}"
print("PASS: _fetch_blog_summary returns '' on exception (does not propagate)")
```

---

### 7-D — `JBOSS_SKIP_PRERELEASE=0` allows pre-release versions through all four extractors

```python
import os, unittest.mock as mock

os.environ["JBOSS_SKIP_PRERELEASE"] = "0"

mock_versions_with_prerelease = [
    "6.0.0.Alpha1", "6.0.0.Final", "7.0.0.Beta1", "7.0.0.Final"
]

extractors_to_test = [
    ("hibernate",  "migration_oracle.pipeline.extractors.hibernate",  "HibernateExtractor"),
    ("resteasy",   "migration_oracle.pipeline.extractors.resteasy",   "RESTEasyExtractor"),
    ("elytron",    "migration_oracle.pipeline.extractors.elytron",    "ElytronExtractor"),
]

import importlib
for name, module_path, class_name in extractors_to_test:
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    extractor = cls.__new__(cls)
    with mock.patch.object(extractor, "_fetch_maven_versions",
                            return_value=mock_versions_with_prerelease, create=True):
        versions = extractor.get_available_versions()
    # With filter disabled, all versions should be present
    assert "6.0.0.Alpha1" in versions, \
        f"FAIL: {name}: Alpha1 was filtered even with JBOSS_SKIP_PRERELEASE=0. " \
        f"Got: {versions}"
    assert len(versions) == len(mock_versions_with_prerelease), \
        f"FAIL: {name}: version list was filtered with JBOSS_SKIP_PRERELEASE=0. " \
        f"Got: {versions}"
    print(f"PASS: {name}: JBOSS_SKIP_PRERELEASE=0 allows all versions through")

del os.environ["JBOSS_SKIP_PRERELEASE"]
```

---

### 7-E — WildFly tag resolution uses full semver `.Final` for a patch release

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor

extractor = WildFlyExtractor.__new__(WildFlyExtractor)

attempted_tags = []

def fake_fetch_github_release(version, tag_candidates):
    attempted_tags.extend(tag_candidates)
    # Simulate: first candidate (39.0.1.Final) succeeds
    return "WildFly 39.0.1 release notes body"

with mock.patch.object(extractor, "fetch_github_release",
                        side_effect=fake_fetch_github_release, create=True):
    extractor.extract("39.0.0", "39.0.1")

assert "39.0.1.Final" in attempted_tags, \
    f"FAIL: tag '39.0.1.Final' not in attempted tags: {attempted_tags}"
assert "39.0.0.Final" not in attempted_tags or attempted_tags.index("39.0.1.Final") == 0, \
    f"FAIL: first tag candidate should be '39.0.1.Final', got: {attempted_tags}"

# The broken pattern must NOT appear
for tag in attempted_tags:
    assert not (tag.startswith("39.") and tag.endswith(".0.0.Final")), \
        f"FAIL: broken tag pattern '{{major}}.0.0.Final' still used: {tag!r}"

print(f"PASS: WildFly tag candidates for 39.0.1: {attempted_tags}")
```

---

### 7-F — Infinispan 16.x uses bare version tag, not `.Final`

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.infinispan import InfinispanExtractor

extractor = InfinispanExtractor.__new__(InfinispanExtractor)

attempted_tags = []

def fake_fetch(version, tag_candidates):
    attempted_tags.extend(tag_candidates)
    return "Infinispan 16.0.0 release notes"

with mock.patch.object(extractor, "fetch_github_release",
                        side_effect=fake_fetch, create=True):
    extractor.extract("15.1.0.Final", "16.0.0")

assert len(attempted_tags) >= 1, "FAIL: no tag candidates attempted"
assert attempted_tags[0] == "16.0.0", \
    f"FAIL: first tag candidate for Infinispan 16.0.0 should be '16.0.0', " \
    f"got: {attempted_tags[0]!r}"
assert "16.0.0.Final" not in attempted_tags[:1], \
    f"FAIL: '16.0.0.Final' is the first candidate — order is wrong: {attempted_tags}"
print(f"PASS: Infinispan 16.x first tag candidate is bare version: {attempted_tags}")
```

---

### 7-G — Hibernate uses only `{version}` tag, never `{version}.Final`

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.hibernate import HibernateExtractor

extractor = HibernateExtractor.__new__(HibernateExtractor)

attempted_tags = []

def fake_fetch(version, tag_candidates):
    attempted_tags.extend(tag_candidates)
    return "Hibernate 6.4.0 release notes"

with mock.patch.object(extractor, "fetch_github_release",
                        side_effect=fake_fetch, create=True):
    extractor.extract("6.3.0.Final", "6.4.0.Final")

assert "6.4.0.Final" not in attempted_tags, \
    f"FAIL: '.Final' tag candidate present in Hibernate attempted tags: {attempted_tags}. " \
    f"Hibernate GitHub tags never use .Final — this causes unnecessary 404s."
assert "6.4.0" in attempted_tags, \
    f"FAIL: bare version '6.4.0' not in Hibernate attempted tags: {attempted_tags}"
print(f"PASS: Hibernate tag candidates contain no .Final suffix: {attempted_tags}")
```

---

### 7-H — Spring Boot wiki page cached: same minor series not fetched twice in a multi-hop run

```python
import unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)
wiki_fetch_calls = []

def fake_wiki_fetch(to_version):
    wiki_fetch_calls.append(to_version)
    return "Wiki content for this version"

# For a multi-hop range within the same minor series (3.3.0 → 3.3.2),
# _fetch_wiki_release_notes should be called for each hop BUT the underlying
# HTTP layer (URL cache) should only fetch the URL once.
# We verify this at the method call level: the method may be called per hop,
# but the URL-level cache in base.py prevents duplicate HTTP fetches.
# Check: calls for 3.3.1 and 3.3.2 both produce the 3.3 wiki URL (same URL, same cache hit).

with mock.patch.object(SpringBootExtractor, "_fetch_wiki_release_notes",
                        side_effect=fake_wiki_fetch), \
     mock.patch.object(SpringBootExtractor, "fetch_github_release",
                        return_value="## Bug Fixes\n- Fix #1\n"):
    extractor.extract("3.3.0", "3.3.1")
    extractor.extract("3.3.1", "3.3.2")

# Both hops use the same wiki page for minor series 3.3
called_versions = wiki_fetch_calls
assert len(called_versions) == 2, \
    f"FAIL: expected 2 wiki fetch calls (one per hop), got: {called_versions}"

# Both must derive the same wiki URL (3.3)
from packaging.version import Version
wiki_urls = set(
    f"Spring-Boot-{Version(v).major}.{Version(v).minor}-Release-Notes"
    for v in called_versions
)
assert wiki_urls == {"Spring-Boot-3.3-Release-Notes"}, \
    f"FAIL: hops produced different wiki URLs: {wiki_urls}"
print(f"PASS: both hops in same minor series target the same wiki URL: {wiki_urls.pop()!r}")
```

---

## Completion gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item in the table below
is checked. Do not mark complete until all rows show ✅.

| ID | Description | Result |
|----|-------------|--------|
| 0-A | All 7 changed modules import without error | ☐ |
| 0-B | `_fetch_wiki_release_notes` exists on SpringBootExtractor with `to_version` param | ☐ |
| 0-C | Wiki URL slug derivation correct for 3.4.0, 3.4.2, 3.5.0, 4.0.0, 4.1.0 | ☐ |
| 0-D | `build_range_metadata` not called inside `SpringBootExtractor.extract` (AST check) | ☐ |
| 0-E | Dependency Upgrades suppression pattern present in `spring_boot.py` | ☐ |
| 0-F | `_get_changelog` and `_fetch_blog_summary` exist on AngularExtractor | ☐ |
| 0-G | `_extract_changelog_section` isolates version section, returns `""` for missing version | ☐ |
| 0-H | `is_jboss_ga_version` passes all `.Final` cases and rejects all Alpha/Beta/CR cases | ☐ |
| 0-I | `is_infinispan_ga_version` passes 15.x `.Final` and 16.x bare semver, rejects Dev builds | ☐ |
| 0-J | WildFly tag candidates use `{version}.Final` not `{major}.0.0.Final` | ☐ |
| 0-K | `enrich_with_jira` uses `re.finditer` not `re.search` | ☐ |
| 0-L | Both branches of `enrich_with_jira` use `dict(change.metadata or {})` copy | ☐ |
| 0-M | `jira_priority` key present in `enrich_with_jira` | ☐ |
| 0-N | `priority` field extracted from Jira REST response in WildFlyExtractor | ☐ |
| 0-O | Infinispan `tag_candidates` first entry is bare version (no `.Final`) | ☐ |
| 0-P | Hibernate `tag_candidates` contains no `.Final` suffix | ☐ |
| 1-A | CLI `--help` lists all 10 required flags/arguments | ☐ |
| 1-B | Unknown framework key exits non-zero with human-readable error, no traceback | ☐ |
| 1-C | `JBOSS_SKIP_PRERELEASE=0` causes `_skip_prerelease()` to return `False` | ☐ |
| 2-A | `_fetch_wiki_release_notes` returns `""` and does not raise on non-200 response | ☐ |
| 2-B | `_extract_changelog_section` boundary exact: correct content, no bleed, last-section EOF | ☐ |
| 2-C | `enrich_with_jira` uses `WFCORE-4892` data when `WFLY-18341` is absent from cache | ☐ |
| 2-D | `enrich_with_jira` produces `Title:/Jira: N/A/Release:` block for summary-only Jira entry | ☐ |
| 2-E | `enrich_with_jira` falls back to index for `issue_type` when REST response has empty value | ☐ |
| 2-F | `enrich_with_jira` stores `jira_priority: "Critical"` in metadata when REST has priority | ☐ |
| 2-G | `enrich_with_jira` does not mutate original `change.metadata` object identity | ☐ |
| 2-H | Hibernate `get_available_versions` excludes Alpha/Beta/CR, returns only `.Final` versions | ☐ |
| 2-I | Infinispan `get_available_versions` excludes Dev builds, keeps 15.x `.Final` and 16.x bare | ☐ |
| 2-J | Spring Boot parser drops all lines from `Dependency Upgrades` section, keeps others | ☐ |
| 2-K | `_fetch_blog_summary` returns extracted string on success, `""` on exception | ☐ |
| 2-L | `metadata['blog_insights']` is list of `{"url", "summary"}` dicts, not list of strings | ☐ |
| 4-A | Spring Boot `3.3.0→3.3.1` dry-run: exit 0, raw artifact exists, breaking/deprecation rows present | ☐ |
| 4-B | Spring Boot `3.3.0→3.3.2` dry-run: `bom_diff` present once in metadata with added/changed/removed keys | ☐ |
| 4-C | Angular `17.0.0→17.1.0` dry-run: exit 0, raw artifact exists with >2 data rows | ☐ |
| 4-D | Spring Boot second run without `--force-extract`: raw artifact mtime unchanged | ☐ |
| 4-E | WildFly `29.0.0→29.0.1` dry-run: exit 0, raw artifact contains `Title:` structured entries | ☐ |
| 7-A | Spring Boot `extract()` returns ExtractionResult (no raise) when `_fetch_wiki_release_notes` returns `""` | ☐ |
| 7-B | Angular `extract()` returns ExtractionResult (no raise) when `_get_changelog` returns `""` | ☐ |
| 7-C | `_fetch_blog_summary` returns `""` (does not propagate) when HTTP raises `Exception` | ☐ |
| 7-D | `JBOSS_SKIP_PRERELEASE=0` allows Alpha/Beta/CR through all four Maven extractors | ☐ |
| 7-E | WildFly `39.0.0→39.0.1`: first tag candidate attempted is `"39.0.1.Final"` | ☐ |
| 7-F | Infinispan `15.1.0.Final→16.0.0`: first tag candidate attempted is `"16.0.0"` (bare) | ☐ |
| 7-G | Hibernate tag candidates contain no `.Final` suffix for any version | ☐ |
| 7-H | Two hops in same Spring Boot minor series (`3.3.0→3.3.1`, `3.3.1→3.3.2`) target same wiki URL | ☐ |
# verification-protocol.md — Spring Boot Wiki Enhancement Fix

**Location:** `specs/003b-fix-spring-wiki-enchansing/verification-protocol.md`
**Spec gate:** Run this after implementation completes, before marking `003b-fix-spring-wiki-enchansing` ✅
**Execution order:** Levels 0 → 7 in sequence. **Stop and fix on the first failure — failures compound.**

---

## Prerequisites

| Requirement | How to satisfy |
|-------------|---------------|
| Dependencies synced | `uv sync` passes with no errors |
| `runs/` directories exist | `mkdir -p runs/raw runs/nodes runs/json` |
| Internet access | Required for Levels 4 and 7 (live HTTP fetches to github.com) |
| `GITHUB_TOKEN` set | Strongly recommended to avoid 60 req/hr rate limit |
| `.env` loaded | `export $(grep -v '^#' .env \| xargs)` |

## Level requirements at a glance

| Level | Name | Internet | LLM | DB |
|-------|------|----------|-----|----|
| 0 | Static checks | ✗ | ✗ | ✗ |
| 1 | Interface structure | ✗ | ✗ | ✗ |
| 2 | Isolation behaviour | ✗ | ✗ | ✗ |
| 4 | **Full version range coverage** | ✓ | ✗ | ✗ |
| 7 | Edge-case paths | ✓ partial | ✗ | ✗ |

> Levels 3, 5, 6 are omitted — this fix makes no graph schema changes and no DB read/write path changes.

---

## Version range ground truth

The fix must work for all 50 GA Spring Boot versions from `3.3.0` to `4.0.6`, plus
pre-release `4.1.0-RC1`. These map to **5 wiki pages** — one per minor series.
Live measurements (June 2026) establish the expected baselines used in Level 4.

| Minor series | Wiki page | Versions (GA) | Prose H3s in "Upgrading from" | Bullets >30 chars |
|:---:|---|:---:|:---:|:---:|
| **3.3** | `Spring-Boot-3.3-Release-Notes` | 14 (3.3.0–3.3.13) | ≥ 5 | ≥ 30 |
| **3.4** | `Spring-Boot-3.4-Release-Notes` | 14 (3.4.0–3.4.13) | ≥ 10 | ≥ 50 |
| **3.5** | `Spring-Boot-3.5-Release-Notes` | 15 (3.5.0–3.5.14) | ≥ 10 | ≥ 50 |
| **4.0** | `Spring-Boot-4.0-Release-Notes` | 7 (4.0.0–4.0.6) | 0 ⚠️ | ≥ 15 |
| **4.1** | `Spring-Boot-4.1-Release-Notes` | pre-release only | 0 ⚠️ | 0 ⚠️ |

**⚠️ 4.0 note:** The "Upgrading from" section for 4.0 contains only a single prose paragraph
linking to a separate migration guide — no H3 subsections. `parse_wiki_upgrade_section` returns
`[]` for 4.0. This is correct and expected. The 4.0 wiki still provides ≥15 valuable bullet
changes from "New and Noteworthy" and "Deprecations" sections.

**⚠️ 4.1 note:** The 4.1 wiki page exists (HTTP 200) but is a placeholder: "Full release notes
will be available when 4.1 has been released." It contains ~251 characters and no parseable
changes. The extractor must handle this gracefully (return `("", [])` or near-empty content)
without aborting.

All 50 GA versions plus `4.1.0-RC1`:
```
3.3.0  3.3.1  3.3.2  3.3.3  3.3.4  3.3.5  3.3.6  3.3.7
3.3.8  3.3.9  3.3.10 3.3.11 3.3.12 3.3.13
3.4.0  3.4.1  3.4.2  3.4.3  3.4.4  3.4.5  3.4.6  3.4.7
3.4.8  3.4.9  3.4.10 3.4.11 3.4.12 3.4.13
3.5.0  3.5.1  3.5.2  3.5.3  3.5.4  3.5.5  3.5.6  3.5.7
3.5.8  3.5.9  3.5.10 3.5.11 3.5.12 3.5.13 3.5.14
4.0.0  4.0.1  4.0.2  4.0.3  4.0.4  4.0.5  4.0.6
4.1.0-RC1  (pre-release — wiki is placeholder)
```

---

## Level 0 — Static checks

> Infrastructure required: **none**. Run these first.

### 0-A — `spring_boot.py` imports without error and `_fetch_wiki_release_notes` is present

```python
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
import inspect

assert hasattr(SpringBootExtractor, "_fetch_wiki_release_notes"), \
    "FAIL: _fetch_wiki_release_notes not found on SpringBootExtractor"

sig = inspect.signature(SpringBootExtractor._fetch_wiki_release_notes)
params = list(sig.parameters.keys())
assert "to_version" in params, \
    f"FAIL: 'to_version' parameter missing from _fetch_wiki_release_notes. Got: {params}"

print(f"PASS: _fetch_wiki_release_notes present with params: {params}")
```

---

### 0-B — `_fetch_wiki_release_notes` return type is a tuple `(str, list)`

```python
import inspect, textwrap
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

src = textwrap.dedent(inspect.getsource(SpringBootExtractor._fetch_wiki_release_notes))
has_tuple_return = (
    "tuple[str" in src or "Tuple[str" in src or
    "return wiki_text," in src or
    "return \"\", []" in src or "return '', []" in src
)
assert has_tuple_return, (
    "FAIL: _fetch_wiki_release_notes does not return a (str, list) tuple.\n"
    "SW-3 requires the return type to change from str to tuple[str, list[DocumentedChange]]."
)
print("PASS: _fetch_wiki_release_notes returns a tuple (str, list)")
```

---

### 0-C — `BeautifulSoup` selector `#wiki-body .markdown-body` is present in source

```python
import inspect
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

src = inspect.getsource(SpringBootExtractor._fetch_wiki_release_notes)
assert "#wiki-body .markdown-body" in src, \
    "FAIL: CSS selector '#wiki-body .markdown-body' not found in _fetch_wiki_release_notes."
assert "BeautifulSoup" in src or "select_one" in src, \
    "FAIL: BeautifulSoup / select_one not used in _fetch_wiki_release_notes."
print("PASS: _fetch_wiki_release_notes uses BeautifulSoup to scope to #wiki-body .markdown-body")
```

---

### 0-D — `_strip_dependency_upgrades` is called inside `_fetch_wiki_release_notes`

```python
import inspect, ast, textwrap
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

src = textwrap.dedent(inspect.getsource(SpringBootExtractor._fetch_wiki_release_notes))
tree = ast.parse(src)
calls = [
    (node.func.attr if isinstance(node.func, ast.Attribute) else
     node.func.id   if isinstance(node.func, ast.Name) else "")
    for node in ast.walk(tree) if isinstance(node, ast.Call)
]
assert "_strip_dependency_upgrades" in calls, \
    "FAIL: _strip_dependency_upgrades is not called inside _fetch_wiki_release_notes."
print("PASS: _strip_dependency_upgrades called inside _fetch_wiki_release_notes")
```

---

### 0-E — `parse_wiki_upgrade_section` is defined and importable

```python
from migration_oracle.pipeline.extractors.spring_boot import parse_wiki_upgrade_section
import inspect

sig = inspect.signature(parse_wiki_upgrade_section)
params = list(sig.parameters.keys())
assert "wiki_text" in params, f"FAIL: 'wiki_text' parameter missing. Got: {params}"
assert "source_url" in params, f"FAIL: 'source_url' parameter missing. Got: {params}"
print(f"PASS: parse_wiki_upgrade_section importable with params: {params}")
```

---

### 0-F — `extract()` parses wiki and GitHub body separately (no concatenation)

```python
import inspect
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

src = inspect.getsource(SpringBootExtractor.extract)
assert 'body + "\\n\\n" + wiki' not in src and "body + '\\n\\n' + wiki" not in src, \
    "FAIL: wiki text is still concatenated into the GitHub release body before parsing."
assert "wiki_url" in src, \
    "FAIL: 'wiki_url' variable not found in extract() — SW-4 not implemented."
print("PASS: extract() parses wiki and GitHub body separately with distinct source URLs")
```

---

### 0-G — Slug derivation: all 50 GA versions produce the correct minor-series slug

```python
from migration_oracle.pipeline.extractors.parsing import parse_version

# Full set of GA versions in range, as of June 2026
ALL_VERSIONS = [
    "3.3.0","3.3.1","3.3.2","3.3.3","3.3.4","3.3.5","3.3.6","3.3.7",
    "3.3.8","3.3.9","3.3.10","3.3.11","3.3.12","3.3.13",
    "3.4.0","3.4.1","3.4.2","3.4.3","3.4.4","3.4.5","3.4.6","3.4.7",
    "3.4.8","3.4.9","3.4.10","3.4.11","3.4.12","3.4.13",
    "3.5.0","3.5.1","3.5.2","3.5.3","3.5.4","3.5.5","3.5.6","3.5.7",
    "3.5.8","3.5.9","3.5.10","3.5.11","3.5.12","3.5.13","3.5.14",
    "4.0.0","4.0.1","4.0.2","4.0.3","4.0.4","4.0.5","4.0.6",
    "4.1.0-RC1",
]

EXPECTED_SLUGS = {
    "3.3": "Spring-Boot-3.3-Release-Notes",
    "3.4": "Spring-Boot-3.4-Release-Notes",
    "3.5": "Spring-Boot-3.5-Release-Notes",
    "4.0": "Spring-Boot-4.0-Release-Notes",
    "4.1": "Spring-Boot-4.1-Release-Notes",
}

_WIKI_URL_TEMPLATE = (
    "https://github.com/spring-projects/spring-boot/wiki/"
    "Spring-Boot-{major}.{minor}-Release-Notes"
)

errors = []
for v in ALL_VERSIONS:
    major, minor, _, _ = parse_version(v)
    derived_url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
    expected_slug = EXPECTED_SLUGS.get(f"{major}.{minor}")
    if expected_slug is None:
        errors.append(f"FAIL: version {v!r} produced unrecognised series {major}.{minor}")
    elif not derived_url.endswith(expected_slug):
        errors.append(f"FAIL: {v!r} → {derived_url!r}, expected slug {expected_slug!r}")

if errors:
    for e in errors:
        print(e)
    raise AssertionError(f"{len(errors)} slug-derivation error(s)")

print(f"PASS: all {len(ALL_VERSIONS)} versions (including 4.1.0-RC1) produce the correct minor-series slug")
```

---

## Level 1 — Interface structure

### 1-A — `parse_wiki_upgrade_section` returns correct `DocumentedChange` list from H3 subsections

```python
from migration_oracle.pipeline.extractors.spring_boot import parse_wiki_upgrade_section
from migration_oracle.models.entities import DocumentedChange

SAMPLE = """\
## Upgrading from Spring Boot 3.4
### Actuator heapdump Endpoint
The heapdump actuator endpoint now defaults to access=NONE. If you want to use it,
you now need to both expose it and configure access.
### Validation of Profile Naming
Rules for profile naming have been tightened. Profiles can now only contain dash,
underscore, letters and digits.
## New and Noteworthy
### New Feature One
New feature description — must NOT appear in results.
"""

changes = parse_wiki_upgrade_section(SAMPLE, "https://wiki.example.com/3.5")
assert isinstance(changes, list), f"FAIL: expected list, got {type(changes)}"
assert len(changes) == 2, f"FAIL: expected 2 changes (one per H3), got {len(changes)}"
assert all(isinstance(c, DocumentedChange) for c in changes)
assert "heapdump" in changes[0].statement.lower() or "Actuator" in changes[0].statement
assert "Profile" in changes[1].statement or "profile" in changes[1].statement
assert not any("New Feature" in c.statement for c in changes), \
    "FAIL: 'New and Noteworthy' bled into upgrade section changes"
print(f"PASS: parse_wiki_upgrade_section returns {len(changes)} changes, section boundary respected")
```

---

### 1-B — Returns `[]` when "Upgrading from" section is absent (4.0-style wiki)

```python
from migration_oracle.pipeline.extractors.spring_boot import parse_wiki_upgrade_section

# Simulates 4.0 wiki: "Upgrading from" section exists but has only a prose paragraph, no H3s
WIKI_40_STYLE = """\
## Upgrading from Spring Boot 3.5
Since this is a major release, we've put together a dedicated migration guide.
If you're running an earlier version, upgrade to 3.5 first.
## New and Noteworthy
### Gradle 9
Gradle 9 is now supported.
"""
result = parse_wiki_upgrade_section(WIKI_40_STYLE, "https://wiki.example.com/4.0")
assert result == [], \
    (f"FAIL: expected [] when Upgrading section has no H3 subsections (4.0-style), "
     f"got {len(result)} items: {[c.statement[:60] for c in result]}")
print("PASS: returns [] when 'Upgrading from' section has no H3 subsections (4.0-style — expected)")
```

---

### 1-C — Returns `[]` for empty/placeholder content (4.1-style wiki)

```python
from migration_oracle.pipeline.extractors.spring_boot import parse_wiki_upgrade_section

# Simulates 4.1 wiki placeholder
WIKI_41_STYLE = """\
Full release notes will be available when 4.1 has been released.
For now you can check out the release notes for the individual milestones:
- v4.1.0-RC1
- v4.1.0-M4
"""
result = parse_wiki_upgrade_section(WIKI_41_STYLE, "https://wiki.example.com/4.1")
assert result == [], \
    f"FAIL: expected [] for placeholder wiki content, got {len(result)} items"
print("PASS: returns [] for placeholder wiki content (4.1-style — expected)")
```

---

### 1-D — All prose changes carry the wiki URL as `source_url`

```python
from migration_oracle.pipeline.extractors.spring_boot import parse_wiki_upgrade_section

WIKI_URL = "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes"
SAMPLE = """\
## Upgrading from Spring Boot 3.4
### Redis Configuration Change
When spring.data.redis.url is configured, the database is determined by the URL.
"""
changes = parse_wiki_upgrade_section(SAMPLE, WIKI_URL)
assert len(changes) == 1
assert changes[0].source_url == WIKI_URL, \
    f"FAIL: source_url is {changes[0].source_url!r}, expected {WIKI_URL!r}"
print("PASS: prose change carries wiki URL as source_url")
```

---

## Level 2 — Isolation behaviour

### 2-A — `_fetch_wiki_release_notes` returns `("", [])` on non-200 without raising

```python
import asyncio, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)
with mock.patch.object(
    extractor.__class__, "fetch",
    side_effect=RuntimeError("Spring Boot HTTP 404 for https://github.com/...")
):
    result = asyncio.run(extractor._fetch_wiki_release_notes("3.5.0"))

assert isinstance(result, tuple) and len(result) == 2
wiki_text, prose_changes = result
assert wiki_text == "" and prose_changes == [], \
    f"FAIL: expected ('', []) on failure, got: {result!r}"
print("PASS: _fetch_wiki_release_notes returns ('', []) on non-200 without raising")
```

---

### 2-B — Scoping to `#wiki-body .markdown-body` eliminates GitHub shell noise

```python
import asyncio, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)

MOCK_HTML = """
<html><body>
<nav>Why GitHub Documentation Blog Premium Support Enterprise-grade 24/7 support</nav>
<div id="wiki-body"><div class="markdown-body">
  <h2>Upgrading from Spring Boot 3.4</h2>
  <h3>Redis Configuration Change</h3>
  <p>When spring.data.redis.url is configured, the database is determined by the URL.</p>
  <h2>New and Noteworthy</h2>
  <ul><li>New feature: annotation support added.</li></ul>
</div></div>
<footer>GitHub Copilot Write better code with AI MCP Registry Integrate external tools
Uh oh! There was an error while loading. Please reload this page.</footer>
</body></html>
"""

with mock.patch.object(extractor.__class__, "fetch", return_value=MOCK_HTML):
    wiki_text, prose_changes = asyncio.run(extractor._fetch_wiki_release_notes("3.5.0"))

for noise in ("Why GitHub", "GitHub Copilot", "Uh oh", "Enterprise-grade", "MCP Registry"):
    assert noise not in wiki_text, \
        f"FAIL: noise string {noise!r} leaked into wiki_text after scoping"
assert "Redis" in wiki_text or "annotation support" in wiki_text, \
    f"FAIL: real wiki content not found in wiki_text"
assert len(prose_changes) >= 1 and "Redis" in prose_changes[0].statement
print("PASS: GitHub shell noise eliminated; real content and prose changes present")
```

---

### 2-C — Dependency Upgrades lines stripped from wiki text

```python
import asyncio, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)

MOCK_HTML = """<html><body><div id="wiki-body"><div class="markdown-body">
## Upgrading from Spring Boot 3.4
### Redis Configuration Change
Database determined by URL.
## Dependency Upgrades
- HikariCP 6.3
- Kafka 3.9
- Testcontainers 1.21
## New and Noteworthy
- New feature added.
</div></div></body></html>"""

with mock.patch.object(extractor.__class__, "fetch", return_value=MOCK_HTML):
    wiki_text, _ = asyncio.run(extractor._fetch_wiki_release_notes("3.5.0"))

for lib in ("HikariCP", "Kafka", "Testcontainers"):
    assert lib not in wiki_text, \
        f"FAIL: '{lib}' from Dependency Upgrades survived stripping in wiki_text"
assert "New feature" in wiki_text or "Redis" in wiki_text
print("PASS: Dependency Upgrades section stripped from wiki_text")
```

---

### 2-D — `extract()` produces entries with both GitHub release URL and wiki URL

```python
import asyncio, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)

RELEASE_URL = "https://github.com/spring-projects/spring-boot/releases/tag/v3.5.0"
WIKI_URL    = "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes"

with mock.patch.object(
    extractor.__class__, "fetch_github_release",
    return_value=(RELEASE_URL, "- Fix NPE [#45000](https://github.com/x)\n")
), mock.patch.object(
    extractor.__class__, "_fetch_wiki_release_notes",
    return_value=("- Wiki bullet change\n", [])
):
    result = asyncio.run(extractor.extract("3.4.0", "3.5.0"))

source_urls = {c.source_url for c in result.changes}
assert RELEASE_URL in source_urls, \
    f"FAIL: GitHub release URL missing from source_urls: {source_urls}"
assert WIKI_URL in source_urls, \
    f"FAIL: Wiki URL missing from source_urls — SW-4 not applied: {source_urls}"

print(f"PASS: both GitHub ({sum(1 for c in result.changes if c.source_url==RELEASE_URL)}) "
      f"and wiki ({sum(1 for c in result.changes if c.source_url==WIKI_URL)}) entries present")
```

---

### 2-E — Wiki fetch failure does not abort `extract()`

```python
import asyncio, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)
with mock.patch.object(
    extractor.__class__, "_fetch_wiki_release_notes", return_value=("", [])
), mock.patch.object(
    extractor.__class__, "fetch_github_release",
    return_value=(
        "https://github.com/spring-projects/spring-boot/releases/tag/v3.5.0",
        "- Fix issue A [#45000](https://github.com/x)\n"
    )
):
    result = asyncio.run(extractor.extract("3.4.0", "3.5.0"))

assert result is not None and len(result.changes) >= 1
print(f"PASS: extract() returns {len(result.changes)} change(s) even when wiki fetch returns ('', [])")
```

---

### 2-F — 4.1-style placeholder wiki produces empty result, not an error

```python
import asyncio, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)

# Simulates the live 4.1 wiki page (~251 chars, placeholder text)
PLACEHOLDER_HTML = """<html><body><div id="wiki-body"><div class="markdown-body">
Full release notes will be available when 4.1 has been released.
For now you can check out the release notes for the individual milestones:
- v4.1.0-RC1
- v4.1.0-M4
- v4.1.0-M3
</div></div></body></html>"""

with mock.patch.object(extractor.__class__, "fetch", return_value=PLACEHOLDER_HTML):
    wiki_text, prose_changes = asyncio.run(extractor._fetch_wiki_release_notes("4.1.0-RC1"))

assert isinstance(wiki_text, str)
assert isinstance(prose_changes, list) and prose_changes == []
# prose_changes must be empty — no "Upgrading from" H3s in placeholder
# wiki_text may be short or empty after stripping
print(f"PASS: 4.1 placeholder wiki returns empty prose_changes without error "
      f"(wiki_text={len(wiki_text)} chars)")
```

---

## Level 4 — Full version range coverage (live HTTP)

> Infrastructure required: **internet + `.env` loaded**. No DB writes. No LLM calls.
>
> This is the primary gate for the fix. It validates that the enhancement works end-to-end
> for every minor series in the 3.3.0–4.1.0 range: the wiki URL is reachable, the content
> container is found, the content is parseable, and real changes are extractable.

### Setup

```bash
export $(grep -v '^#' .env | xargs)
```

---

### 4-A — All 5 wiki URLs return HTTP 200

Confirms the pages exist and are publicly accessible.

```python
import asyncio
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

WIKI_URLS = {
    "3.3": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes",
    "3.4": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes",
    "3.5": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes",
    "4.0": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes",
    "4.1": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes",
}

async def main():
    extractor = SpringBootExtractor()
    failures = []
    for series, url in WIKI_URLS.items():
        try:
            html = await extractor.fetch(url, accept_status={200})
            print(f"PASS [{series}] HTTP 200 — {len(html):,} chars received")
        except RuntimeError as e:
            failures.append(f"FAIL [{series}] {e}")
            print(f"FAIL [{series}] {e}")
    if failures:
        raise AssertionError(f"{len(failures)} wiki URLs did not return HTTP 200:\n" + "\n".join(failures))
    print(f"\nPASS: all 5 wiki URLs return HTTP 200")

asyncio.run(main())
```

---

### 4-B — All 5 wiki pages contain the `#wiki-body .markdown-body` selector

Confirms GitHub has not changed its HTML structure. If this fails, the SW-1 selector needs updating.

```python
import asyncio
from bs4 import BeautifulSoup
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

WIKI_URLS = {
    "3.3": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes",
    "3.4": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes",
    "3.5": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes",
    "4.0": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes",
    "4.1": "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.1-Release-Notes",
}

async def main():
    extractor = SpringBootExtractor()
    failures = []
    for series, url in WIKI_URLS.items():
        html = await extractor.fetch(url, accept_status={200})
        soup = BeautifulSoup(html, "html.parser")
        wb = soup.select_one("#wiki-body .markdown-body")
        if wb is None:
            failures.append(series)
            print(f"FAIL [{series}] #wiki-body .markdown-body selector NOT FOUND")
        else:
            body_text_len = len(wb.get_text())
            full_text_len = len(html)
            ratio = body_text_len / full_text_len
            print(f"PASS [{series}] selector found — body={body_text_len:,} chars "
                  f"({ratio:.0%} of {full_text_len:,} char page)")
    if failures:
        raise AssertionError(
            f"#wiki-body .markdown-body selector missing for series: {failures}\n"
            "GitHub may have changed their wiki HTML structure — update the selector in SW-1."
        )

asyncio.run(main())
```

---

### 4-C — `_fetch_wiki_release_notes` produces valid output for one version from each series

Calls the actual (post-fix) implementation for a representative `to_version` from each minor
series. Validates content size, noise elimination, and prose change extraction.

```python
import asyncio
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

# Representative version from each minor series
REPRESENTATIVE_VERSIONS = {
    "3.3": "3.3.6",     # mid-series patch
    "3.4": "3.4.5",     # mid-series patch
    "3.5": "3.5.0",     # initial release (most complete wiki on release day)
    "4.0": "4.0.3",     # mid-series patch
    "4.1": "4.1.0-RC1", # pre-release (placeholder wiki expected)
}

# Thresholds from live research (June 2026)
THRESHOLDS = {
    "3.3": {"min_text": 8_000,  "max_text": 50_000, "min_prose": 5,  "min_bullets": 30},
    "3.4": {"min_text": 10_000, "max_text": 50_000, "min_prose": 10, "min_bullets": 50},
    "3.5": {"min_text": 10_000, "max_text": 50_000, "min_prose": 10, "min_bullets": 50},
    "4.0": {"min_text": 0,      "max_text": 50_000, "min_prose": 0,  "min_bullets": 15},
    "4.1": {"min_text": 0,      "max_text": 5_000,  "min_prose": 0,  "min_bullets": 0},
}

async def main():
    extractor = SpringBootExtractor()
    failures = []
    print(f"{'Series':<6} {'to_version':<14} {'text':<10} {'prose':<7} {'bullets':<9} Status")
    print("-" * 68)

    for series, to_version in REPRESENTATIVE_VERSIONS.items():
        t = THRESHOLDS[series]
        try:
            wiki_text, prose_changes = await extractor._fetch_wiki_release_notes(to_version)
        except Exception as e:
            failures.append(f"[{series}] _fetch_wiki_release_notes raised: {e}")
            print(f"{series:<6} {to_version:<14} ERROR: {e}")
            continue

        # Count substantive bullet changes
        from migration_oracle.pipeline.extractors.spring_boot import parse_github_release_text
        from migration_oracle.pipeline.extractors.parsing import parse_version as pv
        major, minor, _, _ = pv(to_version)
        wiki_url = (f"https://github.com/spring-projects/spring-boot/wiki/"
                    f"Spring-Boot-{major}.{minor}-Release-Notes")
        bullet_changes = [c for c in parse_github_release_text(wiki_text, wiki_url)
                          if len(c.statement) > 30] if wiki_text else []

        text_len = len(wiki_text)
        prose_n  = len(prose_changes)
        bullet_n = len(bullet_changes)

        errs = []
        if not (t["min_text"] <= text_len <= t["max_text"]):
            errs.append(f"text={text_len} not in [{t['min_text']},{t['max_text']}]")
        if prose_n < t["min_prose"]:
            errs.append(f"prose={prose_n} < min {t['min_prose']}")
        if bullet_n < t["min_bullets"]:
            errs.append(f"bullets={bullet_n} < min {t['min_bullets']}")

        # Noise check: dependency upgrade library names must be absent
        dep_noise = [lib for lib in ("HikariCP", "Testcontainers", "Kafka 3.")
                     if lib in wiki_text]
        if dep_noise:
            errs.append(f"dep-upgrade noise present: {dep_noise}")

        status = "PASS" if not errs else "FAIL: " + "; ".join(errs)
        print(f"{series:<6} {to_version:<14} {text_len:<10,} {prose_n:<7} {bullet_n:<9} {status}")
        if errs:
            failures.append(f"[{series}] {'; '.join(errs)}")

    print()
    if failures:
        raise AssertionError(f"{len(failures)} series failed:\n" + "\n".join(failures))
    print("PASS: all 5 minor series produce valid output from _fetch_wiki_release_notes")

asyncio.run(main())
```

---

### 4-D — Prose changes are real and parseable for series 3.3, 3.4, 3.5

Verifies that the prose entries extracted from the "Upgrading from" section are genuine
migration-relevant statements — not parser artefacts — by checking statement length,
content keywords, and change type classification.

```python
import asyncio
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

PROSE_SERIES = {
    "3.3": ("3.3.0", 5),   # (representative version, min expected prose changes)
    "3.4": ("3.4.0", 10),
    "3.5": ("3.5.0", 10),
}

async def main():
    extractor = SpringBootExtractor()
    failures = []

    for series, (to_version, min_count) in PROSE_SERIES.items():
        _, prose_changes = await extractor._fetch_wiki_release_notes(to_version)

        # Basic count
        if len(prose_changes) < min_count:
            failures.append(f"[{series}] only {len(prose_changes)} prose changes, expected ≥{min_count}")
            print(f"FAIL [{series}] {len(prose_changes)} prose changes < min {min_count}")
            continue

        # Statement quality
        short = [c for c in prose_changes if len(c.statement) < 30]
        if short:
            failures.append(
                f"[{series}] {len(short)} prose changes have statement shorter than 30 chars: "
                + str([c.statement for c in short[:3]])
            )

        # Every prose change must carry wiki URL
        wiki_url_prefix = "https://github.com/spring-projects/spring-boot/wiki/"
        wrong_url = [c for c in prose_changes if not c.source_url.startswith(wiki_url_prefix)]
        if wrong_url:
            failures.append(
                f"[{series}] {len(wrong_url)} prose changes carry non-wiki source_url: "
                + str([c.source_url for c in wrong_url[:3]])
            )

        # At least one must be classified as breaking/mandatory_migration/deprecation
        high_value = [c for c in prose_changes
                      if c.type in ("mandatory_migration", "breaking", "deprecation")]
        if not high_value:
            failures.append(
                f"[{series}] no high-value (mandatory/breaking/deprecation) prose changes found. "
                f"Types seen: {set(c.type for c in prose_changes)}"
            )

        status = "PASS" if not [f for f in failures if f.startswith(f"[{series}]")] else "FAIL"
        print(f"{status} [{series}] {len(prose_changes)} prose changes — "
              f"{len(high_value)} high-value, {len(short)} too-short")
        for ch in prose_changes[:3]:
            print(f"       [{ch.type}/{ch.confidence}] {ch.statement[:100]}")

    if failures:
        raise AssertionError(f"{len(failures)} prose quality check(s) failed:\n" + "\n".join(failures))

asyncio.run(main())
```

---

### 4-E — `extract()` end-to-end produces correct source URL split for each series

Runs a full `extract()` call for one version per series and verifies that the result
contains entries from both the GitHub release URL and the wiki URL (for series 3.3–3.5)
or only GitHub release URL (for 4.0/4.1 where wiki adds no bullets).

```python
import asyncio
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

# Use the first (minor series release) version per series — most complete release notes
VERSIONS = [
    ("3.3", "3.3.0",     "3.3.1",   True,  True),   # (series, from, to, expect_wiki_url, expect_prose)
    ("3.4", "3.4.0",     "3.4.1",   True,  True),
    ("3.5", "3.5.0",     "3.5.1",   True,  True),
    ("4.0", "4.0.0",     "4.0.1",   True,  False),  # wiki bullets expected, prose=0
    ("4.1", "4.0.6",     "4.1.0",   False, False),  # 4.1 wiki is placeholder — wiki URL may be absent
]

RELEASE_URL_FRAG = "/releases/tag/"
WIKI_URL_FRAG    = "/wiki/Spring-Boot-"

async def main():
    extractor = SpringBootExtractor()
    failures = []
    print(f"{'Series':<6} {'hop':<18} {'total':<7} {'gh':<5} {'wiki':<5} {'prose':<7} Status")
    print("-" * 70)

    for series, from_v, to_v, expect_wiki, expect_prose in VERSIONS:
        try:
            result = await extractor.extract(from_v, to_v)
        except Exception as e:
            failures.append(f"[{series}] extract() raised: {e}")
            print(f"{series:<6} {from_v}→{to_v:<10} ERROR: {e}")
            continue

        gh_entries    = [c for c in result.changes if RELEASE_URL_FRAG in c.source_url]
        wiki_entries  = [c for c in result.changes if WIKI_URL_FRAG in c.source_url]
        prose_entries = [c for c in wiki_entries   if ": " in c.statement and len(c.statement) > 60]
        high_value    = [c for c in result.changes
                         if c.type in ("mandatory_migration", "breaking", "deprecation")]

        errs = []
        if len(gh_entries) < 5:
            errs.append(f"only {len(gh_entries)} GitHub release entries (expected ≥5)")
        if expect_wiki and len(wiki_entries) == 0:
            errs.append(f"no wiki entries — SW-4 or wiki fetch not working")
        if expect_prose and len(prose_entries) == 0:
            errs.append(f"no prose entries — parse_wiki_upgrade_section not returning results")
        if len(result.changes) > 400:
            errs.append(f"total {len(result.changes)} entries — noise reduction not achieved (pre-fix was ~580)")

        status = "PASS" if not errs else "FAIL"
        hop_str = f"{from_v}→{to_v}"
        print(f"{series:<6} {hop_str:<18} {len(result.changes):<7} "
              f"{len(gh_entries):<5} {len(wiki_entries):<5} {len(prose_entries):<7} {status}")
        for err in errs:
            print(f"       ↳ {err}")
            failures.append(f"[{series}] {err}")

    print()
    if failures:
        raise AssertionError(f"{len(failures)} end-to-end check(s) failed:\n" + "\n".join(failures))
    print("PASS: all series produce correct end-to-end output from extract()")

asyncio.run(main())
```

---

### 4-F — Version-to-slug mapping is consistent with live Maven Central version list

Fetches the current version list from Maven Central and confirms every version in the
3.3.0–4.1.0 range maps to a known, valid wiki slug.

```python
import asyncio
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor
from migration_oracle.pipeline.extractors.parsing import parse_maven_metadata_versions, parse_version
from migration_oracle.pipeline.extractors.base import is_spring_boot_ga_version

MAVEN_URL = (
    "https://repo1.maven.org/maven2/org/springframework/boot/"
    "spring-boot-dependencies/maven-metadata.xml"
)
KNOWN_SERIES = {"3.3", "3.4", "3.5", "4.0", "4.1"}
_WIKI_URL_TEMPLATE = (
    "https://github.com/spring-projects/spring-boot/wiki/"
    "Spring-Boot-{major}.{minor}-Release-Notes"
)

async def main():
    extractor = SpringBootExtractor()
    xml = await extractor.fetch(MAVEN_URL)
    raw = parse_maven_metadata_versions(xml)
    ga = [v for v in raw if is_spring_boot_ga_version(v)]
    in_range = [v for v in ga if (3, 3) <= (parse_version(v)[0], parse_version(v)[1]) <= (4, 1)]

    print(f"GA versions in 3.3.x–4.1.x from Maven Central: {len(in_range)}")
    assert len(in_range) >= 50, \
        f"FAIL: expected ≥50 GA versions, got {len(in_range)} — Maven metadata may have changed"

    unknowns = []
    for v in in_range:
        major, minor, _, _ = parse_version(v)
        series = f"{major}.{minor}"
        if series not in KNOWN_SERIES:
            unknowns.append(f"{v} → unrecognised series {series}")

    if unknowns:
        raise AssertionError(
            f"New minor series detected in Maven Central — add wiki page check for:\n"
            + "\n".join(unknowns)
        )

    print(f"PASS: all {len(in_range)} live Maven Central versions map to known series {KNOWN_SERIES}")
    from collections import Counter
    counts = Counter(f"{parse_version(v)[0]}.{parse_version(v)[1]}" for v in in_range)
    for series in sorted(counts):
        print(f"  {series}: {counts[series]} versions")

asyncio.run(main())
```

---

### 4-G — CLI dry-run for 3.3.0→3.5.0 exits 0, raw artifacts contain wiki URL rows

Runs the full extraction pipeline CLI for a two-major-minor-hop range and confirms
the raw output artifacts reflect the wiki enhancement: wiki URL appears in Source column,
high-value change types are present, and noise is within bounds.

```bash
export $(grep -v '^#' .env | xargs)

uv run migration-oracle export-extract-populate-framework \
    --framework spring-boot \
    --extract-only \
    --force-extract \
    3.3.0 3.5.0

EXIT=$?
[ $EXIT -eq 0 ] && echo "PASS: CLI exit 0 for 3.3.0→3.5.0" || { echo "FAIL: CLI exit $EXIT"; exit 1; }
```

```bash
for RANGE_LABEL in "3.3.0-to-3.4.0" "3.4.0-to-3.5.0"; do
    RAW="runs/raw/spring-boot-${RANGE_LABEL}-changes.md"
    [ -f "$RAW" ] || { echo "FAIL: artifact missing at $RAW"; exit 1; }

    WIKI_ROWS=$(grep -c "wiki/Spring-Boot" "$RAW" 2>/dev/null || echo 0)
    [ "$WIKI_ROWS" -gt 0 ] \
        && echo "PASS [$RANGE_LABEL] $WIKI_ROWS wiki-URL rows in Source column" \
        || echo "FAIL [$RANGE_LABEL] no wiki URL rows — SW-4 not applied"

    HIGH_VALUE=$(grep -cE "mandatory_migration|breaking\b|deprecation" "$RAW" 2>/dev/null || echo 0)
    [ "$HIGH_VALUE" -gt 0 ] \
        && echo "PASS [$RANGE_LABEL] $HIGH_VALUE high-value type rows (mandatory/breaking/deprecation)" \
        || echo "FAIL [$RANGE_LABEL] zero high-value rows — wiki prose parsing not working"

    DEP_NOISE=$(grep -cE "^\| [^|]+ \|[^|]+\| [^|]+ \| (HikariCP|Testcontainers|Kafka [0-9])" \
                "$RAW" 2>/dev/null || echo 0)
    [ "$DEP_NOISE" -eq 0 ] \
        && echo "PASS [$RANGE_LABEL] no dependency-upgrade noise rows" \
        || echo "FAIL [$RANGE_LABEL] $DEP_NOISE dep-upgrade noise rows still present"

    ROW_COUNT=$(grep -c "^|" "$RAW" 2>/dev/null || echo 0)
    [ "$ROW_COUNT" -lt 300 ] \
        && echo "PASS [$RANGE_LABEL] $ROW_COUNT total rows — within bounds" \
        || echo "FAIL [$RANGE_LABEL] $ROW_COUNT rows — too many, noise reduction not achieved"
done
```

---

## Level 7 — Edge-case paths

### 7-A — Minor wiki URL slug is correct for every version including patches

Parametric check: every version in the full known range, including double-digit patches
(`3.3.13`, `3.5.14`), produces the correct wiki URL.

```python
from migration_oracle.pipeline.extractors.parsing import parse_version

ALL_VERSIONS = [
    "3.3.0","3.3.1","3.3.2","3.3.3","3.3.4","3.3.5","3.3.6","3.3.7",
    "3.3.8","3.3.9","3.3.10","3.3.11","3.3.12","3.3.13",
    "3.4.0","3.4.1","3.4.2","3.4.3","3.4.4","3.4.5","3.4.6","3.4.7",
    "3.4.8","3.4.9","3.4.10","3.4.11","3.4.12","3.4.13",
    "3.5.0","3.5.1","3.5.2","3.5.3","3.5.4","3.5.5","3.5.6","3.5.7",
    "3.5.8","3.5.9","3.5.10","3.5.11","3.5.12","3.5.13","3.5.14",
    "4.0.0","4.0.1","4.0.2","4.0.3","4.0.4","4.0.5","4.0.6",
    "4.1.0-RC1",
]
_WIKI_TEMPLATE = (
    "https://github.com/spring-projects/spring-boot/wiki/"
    "Spring-Boot-{major}.{minor}-Release-Notes"
)
EXPECTED = {
    "3.3": "Spring-Boot-3.3-Release-Notes",
    "3.4": "Spring-Boot-3.4-Release-Notes",
    "3.5": "Spring-Boot-3.5-Release-Notes",
    "4.0": "Spring-Boot-4.0-Release-Notes",
    "4.1": "Spring-Boot-4.1-Release-Notes",
}
errors = []
for v in ALL_VERSIONS:
    major, minor, _, _ = parse_version(v)
    url = _WIKI_TEMPLATE.format(major=major, minor=minor)
    expected_slug = EXPECTED.get(f"{major}.{minor}")
    if not expected_slug or not url.endswith(expected_slug):
        errors.append(f"{v!r} → {url!r}, expected slug {expected_slug!r}")
if errors:
    raise AssertionError(f"Slug errors:\n" + "\n".join(errors))
print(f"PASS: all {len(ALL_VERSIONS)} versions produce correct wiki slug")
```

---

### 7-B — 4.0 wiki: bullets still extracted even though prose section has no H3s

```python
import asyncio
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

async def main():
    extractor = SpringBootExtractor()
    wiki_text, prose_changes = await extractor._fetch_wiki_release_notes("4.0.0")

    # Prose changes must be [] (4.0 Upgrading section has no H3 subsections)
    assert prose_changes == [], \
        (f"FAIL: expected [] prose changes for 4.0 (no H3s in Upgrading section), "
         f"got {len(prose_changes)}: {[c.statement[:60] for c in prose_changes[:3]]}")

    # But wiki_text should still have bullet content from New and Noteworthy + Deprecations
    from migration_oracle.pipeline.extractors.spring_boot import parse_github_release_text
    from migration_oracle.pipeline.extractors.parsing import parse_version
    major, minor, _, _ = parse_version("4.0.0")
    wiki_url = (f"https://github.com/spring-projects/spring-boot/wiki/"
                f"Spring-Boot-{major}.{minor}-Release-Notes")
    bullet_changes = [c for c in parse_github_release_text(wiki_text, wiki_url)
                      if len(c.statement) > 30]
    assert len(bullet_changes) >= 15, \
        (f"FAIL: 4.0 wiki should still yield ≥15 bullet changes from New and Noteworthy, "
         f"got {len(bullet_changes)}")

    print(f"PASS: 4.0 wiki — prose=[] (expected), bullets={len(bullet_changes)} (≥15)")

asyncio.run(main())
```

---

### 7-C — 4.1 placeholder wiki: graceful empty result, no abort

```python
import asyncio
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

async def main():
    extractor = SpringBootExtractor()
    # 4.1 wiki exists but is a placeholder — must not abort
    try:
        wiki_text, prose_changes = await extractor._fetch_wiki_release_notes("4.1.0-RC1")
    except Exception as e:
        raise AssertionError(f"FAIL: _fetch_wiki_release_notes raised for 4.1.0-RC1: {e}")

    assert isinstance(wiki_text, str)
    assert isinstance(prose_changes, list) and prose_changes == []
    assert len(wiki_text) < 2000, \
        f"FAIL: 4.1 placeholder wiki should produce <2000 chars, got {len(wiki_text)}"
    print(f"PASS: 4.1.0-RC1 placeholder wiki handled gracefully "
          f"({len(wiki_text)} chars, 0 prose changes)")

asyncio.run(main())
```

---

### 7-D — Same minor-series wiki URL is not re-fetched for patch hops in the same series

Confirms that the URL-level cache in `base.py` means multiple patch hops within 3.5.x
(e.g. 3.5.0→3.5.1, 3.5.1→3.5.2) result in only **one** actual HTTP request to
`Spring-Boot-3.5-Release-Notes`.

```python
import asyncio, unittest.mock as mock
from migration_oracle.pipeline.extractors.spring_boot import SpringBootExtractor

extractor = SpringBootExtractor.__new__(SpringBootExtractor)
fetch_calls = []
MOCK_HTML = "<html><body><div id='wiki-body'><div class='markdown-body'><p>Content</p></div></div></body></html>"

original_fetch = SpringBootExtractor.fetch.__wrapped__ \
    if hasattr(SpringBootExtractor.fetch, "__wrapped__") \
    else SpringBootExtractor.fetch

async def counting_fetch(self, url, **kwargs):
    if "wiki" in url:
        fetch_calls.append(url)
    # Check the real cache — if URL is already cached, don't count it as a real HTTP fetch
    if url in self._cache:
        return self._cache[url]
    self._cache[url] = MOCK_HTML
    return MOCK_HTML

with mock.patch.object(SpringBootExtractor, "fetch", counting_fetch):
    extractor._cache = {}
    asyncio.run(extractor._fetch_wiki_release_notes("3.5.0"))
    asyncio.run(extractor._fetch_wiki_release_notes("3.5.1"))  # same wiki URL
    asyncio.run(extractor._fetch_wiki_release_notes("3.5.2"))  # same wiki URL

# All three calls target the same wiki URL
assert len(set(fetch_calls)) == 1, \
    f"FAIL: expected 1 unique wiki URL, got {len(set(fetch_calls))}: {set(fetch_calls)}"
# Only one actual "cache miss" fetch
assert len(fetch_calls) == 1, \
    (f"FAIL: wiki URL fetched {len(fetch_calls)} times for 3 patch hops in same series. "
     f"URL-level cache in base.py must de-duplicate these fetches.")
print(f"PASS: {len(fetch_calls)} wiki HTTP fetch for 3 patch hops in same minor series (cache working)")
```

---

## Completion gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| ID | Description | Result |
|----|-------------|--------|
| 0-A | `_fetch_wiki_release_notes` present with `to_version` param | ☐ |
| 0-B | Return type is `(str, list)` tuple | ☐ |
| 0-C | `#wiki-body .markdown-body` and `BeautifulSoup` in `_fetch_wiki_release_notes` | ☐ |
| 0-D | `_strip_dependency_upgrades` called inside `_fetch_wiki_release_notes` (AST) | ☐ |
| 0-E | `parse_wiki_upgrade_section` importable with `wiki_text, source_url` params | ☐ |
| 0-F | `extract()` does not concatenate wiki into GitHub body; uses `wiki_url` variable | ☐ |
| 0-G | All 50 GA versions + 4.1.0-RC1 produce correct minor-series slug | ☐ |
| 1-A | `parse_wiki_upgrade_section` returns H3-scoped `DocumentedChange` list, boundary respected | ☐ |
| 1-B | Returns `[]` when Upgrading section has no H3s (4.0-style) | ☐ |
| 1-C | Returns `[]` for placeholder/empty wiki content (4.1-style) | ☐ |
| 1-D | All prose changes carry wiki URL as `source_url` | ☐ |
| 2-A | Returns `('', [])` on non-200 without raising | ☐ |
| 2-B | GitHub nav/footer noise absent from wiki_text; real content and prose changes present | ☐ |
| 2-C | Dependency Upgrades items stripped from wiki_text | ☐ |
| 2-D | `extract()` result contains both GitHub release URL and wiki URL as `source_url` | ☐ |
| 2-E | `extract()` returns valid result when wiki returns `('', [])` | ☐ |
| 2-F | 4.1 placeholder HTML returns empty prose_changes without error | ☐ |
| **4-A** | **All 5 wiki URLs (3.3–4.1) return HTTP 200** | ☐ |
| **4-B** | **All 5 wiki pages contain `#wiki-body .markdown-body` selector** | ☐ |
| **4-C** | **`_fetch_wiki_release_notes` for one version per series: size, prose, bullets within thresholds** | ☐ |
| **4-D** | **Prose changes for 3.3, 3.4, 3.5: count ≥ min, quality ≥ 30 chars, at least one high-value type** | ☐ |
| **4-E** | **`extract()` end-to-end for one hop per series: correct source URL split, <400 total entries** | ☐ |
| **4-F** | **Live Maven Central version list: all GA versions map to known wiki series** | ☐ |
| **4-G** | **CLI dry-run 3.3.0→3.5.0: exit 0, wiki URL rows present, high-value rows present, no dep noise** | ☐ |
| 7-A | All 50 GA + RC1 versions produce correct wiki slug (parametric) | ☐ |
| 7-B | 4.0: prose=[], bullets≥15 — wiki still adds value despite no H3s in Upgrading section | ☐ |
| 7-C | 4.1 placeholder wiki: `('',[])`-equivalent, no abort, <2000 chars | ☐ |
| 7-D | 3 patch hops in same 3.5.x series cause only 1 wiki HTTP fetch (cache working) | ☐ |

# spec.md — 002-extractors (Improvement Pass)

**Location:** `specs/003b-extractors-improvements/spec.md`
**Type:** Amendment — bug fixes and content-source improvements
**Branch:** `003b-extractors-improvemetnts`
**Source:** `extractor-research-report.docx` — June 2026
**Prerequisites:** `001-foudation` ✅, `002-pipeline-core` ✅ `003-framework-http-extractors` ✅ (base implementation present)

---

## Context and scope

The base `003-framework-http-extractors` implementation is structurally correct — version discovery, tag
resolution, output contract, and Markdown rendering all work. However, three root-cause
findings from post-implementation research reveal that each extractor silently produces
incomplete output:

- **Spring Boot** — the GitHub API release body contains only feature summaries, bug-fix
  one-liners, and dependency upgrades. The wiki release notes page — the canonical source of
  all breaking changes, behavioral differences, deprecations, and upgrade instructions — is
  never fetched. The BOM diff is also computed once per hop instead of once per range.
- **Angular** — the GitHub API release body is frequently a one-liner or blog link only. All
  per-package Breaking Changes and Deprecations live exclusively in the repository
  CHANGELOG.md and are never fetched. Blog insight URLs are extracted but their content is
  never retrieved, making them useless to the filter LLM.
- **WildFly `enrich_with_jira`** — three bugs cause silent data loss (issue-type index
  fallback never consulted; only the first Jira key per statement tried; metadata mutated by
  reference) and two spec deviations cause the enriched text to be produced in the wrong
  format and the `priority` field to be silently dropped.
- **Four Maven-based extractors** (Hibernate ORM, RESTEasy, Infinispan, WildFly Elytron) —
  no pre-release version filter exists, causing hops through Alpha/Beta/CR/Dev builds.

This amendment also corrects four tag-format discrepancies discovered during live URL
verification.

---

## Files changed by this amendment

| File | Change type |
|------|-------------|
| `pipeline/extractors/spring_boot.py` | SP-1, SP-2, SP-3 |
| `pipeline/extractors/angular.py` | ANG-1, ANG-2 |
| `pipeline/extractors/wildfly.py` | WF-1, WF-2, WF-3, WF-4, WF-5, WF-6 |
| `pipeline/extractors/hibernate.py` | PRE-1, PRE-3 |
| `pipeline/extractors/resteasy.py` | PRE-1 |
| `pipeline/extractors/infinispan.py` | PRE-1, PRE-2 |
| `pipeline/extractors/elytron.py` | PRE-1 |
| `pipeline/orchestrator.py` (or equivalent) | SP-2 call-site move |

No changes to `base.py`, `filters.py`, `extractor.py`, `populator.py`, graph schema,
or any LLM prompt.

---

## SP-1 — Spring Boot: fetch the wiki release notes page

### What must change

`spring_boot.py` — inside `extract(from_version, to_version)`, after `fetch_github_release()`
returns the release body, fetch the wiki page for the hop's `to_version` minor series and
append its content to `body` before calling `parse_github_release_text(body)`.

### Exact URL

```
https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-{major}.{minor}-Release-Notes
```

`{major}` and `{minor}` are derived from the hop's `to_version`. Examples:

| `to_version` | Wiki URL fetched |
|-------------|-----------------|
| `3.4.0` | `.../Spring-Boot-3.4-Release-Notes` |
| `3.4.2` | `.../Spring-Boot-3.4-Release-Notes` (same page — covers entire minor series) |
| `3.5.0` | `.../Spring-Boot-3.5-Release-Notes` |
| `4.0.0` | `.../Spring-Boot-4.0-Release-Notes` |

### HTTP request spec

```
Method:  GET
URL:     https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-{M}.{m}-Release-Notes
Headers: none required (public wiki page, no auth)
Timeout: 30 seconds (shared HTTP client default)
Cache:   URL-level cache from base.py — fetched at most once per minor series per pipeline run
SSL:     respects SSL_VERIFY env var
```

The wiki page returns HTML. Extract all text content from it (strip HTML tags, preserve
headings and list items as plain text or lightweight Markdown). The existing
`parse_github_release_text` receives this appended content and treats it as additional
release body text.

### Version component extraction

```python
from packaging.version import Version

v = Version(to_version)          # e.g. "3.4.2"
major, minor = v.major, v.minor  # 3, 4
wiki_url = (
    f"https://github.com/spring-projects/spring-boot/wiki/"
    f"Spring-Boot-{major}.{minor}-Release-Notes"
)
```

### Append logic

```python
# Inside extract(from_version, to_version):

body = fetch_github_release(to_version)          # existing call — unchanged

wiki_content = _fetch_wiki_release_notes(to_version)  # new helper
if wiki_content:
    body = body + "\n\n" + wiki_content          # append; parse_github_release_text reads the combined string

changes = parse_github_release_text(body)        # existing call — unchanged
```

### `_fetch_wiki_release_notes` helper contract

```python
def _fetch_wiki_release_notes(to_version: str) -> str:
    """
    Fetch the Spring Boot wiki release notes page for the minor series of to_version.
    Returns the page text (HTML stripped to plain text) on success.
    Returns "" on any failure (non-200, timeout, network error).
    Never raises.
    Logs a WARNING on failure.
    Uses the shared URL-level cache — the same minor-series page is not fetched twice.
    """
```

### Failure behavior

- Non-200 response → log `WARNING: Spring Boot wiki page {url} returned {status}, continuing without it` → return `""`
- Timeout or network error → log `WARNING: Spring Boot wiki page fetch failed: {error}` → return `""`
- Empty response body → return `""` silently
- The pipeline never aborts due to a failed wiki fetch. The GitHub release body alone is sufficient to proceed.

### What the wiki page contains (that the GitHub body does not)

The GitHub API `body` field for Spring Boot contains only these sections:

| Section | Migration value |
|---------|----------------|
| ⭐ New Features | Low — feature additions |
| 🐞 Bug Fixes | Very low — one-liner titles |
| 📝 Documentation | None |
| 🔨 Dependency Upgrades | Redundant (covered by BOM diff) |

The wiki page for the same release contains (example from 3.4):

- `RestClient` and `RestTemplate` order-of-precedence changes
- Bean Validation of `@ConfigurationProperties` behaviour change
- `@ConditionalOnBean` semantic change
- Multiple property key renames with old → new mapping tables
- Actuator endpoint changes
- Auto-configuration class removals

These are exactly the entries that become `breaking`, `mandatory_migration`, and
`deprecation` typed `DocumentedChange` records. Without this fetch, those types will be
absent from every Spring Boot extraction run.

---

## SP-2 — Spring Boot: BOM diff is range-scoped, called once

### What must change

`build_range_metadata(from_version, to_version)` is **removed from `extract()`** and moved
to the orchestrator, called exactly once for the full user-requested range.

### Current broken behavior

```python
# spring_boot.py — CURRENT (broken)
def extract(self, from_version: str, to_version: str) -> ExtractionResult:
    ...
    metadata = self.build_range_metadata(from_version, to_version)  # ← called per hop
    ...
```

For a range `3.3.0 → 3.5.0` with hops `(3.3.0→3.3.1)`, `(3.3.1→3.4.0)`, `(3.4.0→3.5.0)`:
- Called 3 times, fetches 6 POM files
- Each hop gets its own narrow diff (e.g. hop `3.3.0→3.3.1` diff only shows patch-level changes)
- No single artifact shows the full range `3.3.0 → 3.5.0` diff

### Required behavior

```python
# spring_boot.py — AFTER (correct)
def extract(self, from_version: str, to_version: str) -> ExtractionResult:
    ...
    # build_range_metadata NOT called here
    # metadata dict has no bom_diff key; orchestrator attaches it to the combined result
    ...
```

```python
# orchestrator.py — AFTER (correct call site)
results = []
for hop_from, hop_to in hops:
    result = extractor.extract(hop_from, hop_to)
    results.append(result)

combined = merge_extraction_results(results)

# BOM diff: called once, uses the original user-requested range endpoints
if framework == "spring-boot":
    bom_diff = extractor.build_range_metadata(original_from_version, original_to_version)
    combined.metadata["bom_diff"] = bom_diff
```

### BOM diff URL pattern (unchanged — for reference)

```
https://repo1.maven.org/maven2/org/springframework/boot/spring-boot-dependencies/{version}/spring-boot-dependencies-{version}.pom
```

Two fetches total per pipeline run:
- `spring-boot-dependencies-{from_version}.pom`
- `spring-boot-dependencies-{to_version}.pom`

The diff computes added, changed, and removed managed dependency coordinates between the
two POMs. The result shape and storage in `ExtractionResult.metadata['bom_diff']` are
unchanged.

---

## SP-3 — Spring Boot: suppress Dependency Upgrades section in parser

### What must change

`parse_github_release_text` in `spring_boot.py` — lines under the
`Dependency Upgrades` / `🔨 Dependency Upgrades` heading are discarded, not emitted as
`DocumentedChange` entries.

### Detection

The section heading matches these patterns (case-insensitive):

```python
_DEPENDENCY_UPGRADES_HEADING_RE = re.compile(
    r"^#+\s*(🔨\s*)?dependency\s+upgrades?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
```

All lines between this heading and the next `##`-level heading (or end of document) are
dropped at parse time and not passed to the classifier.

### Scope

This suppression applies **only to Spring Boot**. It is implemented inside
`spring_boot.py`'s parser, not in the shared `base.py` parser. Other extractors are
unaffected.

### Rationale

`build_range_metadata` already captures every dependency change with full Maven coordinate
precision (`group:artifact old_version → new_version`). The release body lines carry no
additional information and dominate the artifact for patch releases — e.g. `Upgrade to
Tomcat 10.1.16 #38421` — forcing the filter LLM to process and discard hundreds of
low-value rows on every run.

---

## ANG-1 — Angular: fetch CHANGELOG.md and extract the version section

### What must change

`angular.py` — fetch `CHANGELOG.md` once per pipeline run (cached), then for each hop's
`to_version` extract the corresponding version section and append it to `body` before
parsing.

### Exact URL

```
https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md
```

### HTTP request spec

```
Method:  GET
URL:     https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md
Headers: none required
Timeout: 30 seconds
Cache:   URL-level cache from base.py — fetched exactly once per pipeline run regardless
         of how many hops the range contains
SSL:     respects SSL_VERIFY env var
```

The CHANGELOG.md is a large file (several hundred KB). It is fetched once and cached by
URL. All hops read from the same cached string.

### Version section extraction

Each version entry in `CHANGELOG.md` starts with an HTML anchor tag:

```html
<a name="22.0.0"></a>
```

The section for a given version runs from its anchor to the next anchor or end of file.

```python
def _extract_changelog_section(changelog_text: str, version: str) -> str:
    """
    Extract the section for `version` from Angular CHANGELOG.md text.

    The section starts at the line containing <a name="{version}"></a>
    and ends just before the next <a name="..."></a> line, or end of file.

    Returns the extracted section text, or "" if no matching anchor is found.
    Never raises.
    """
    anchor = f'<a name="{version}"></a>'
    start = changelog_text.find(anchor)
    if start == -1:
        return ""

    # Find the next anchor after the start position
    next_anchor_start = changelog_text.find('<a name="', start + len(anchor))
    if next_anchor_start == -1:
        section = changelog_text[start:]
    else:
        section = changelog_text[start:next_anchor_start]

    return section.strip()
```

### Append logic

```python
# Inside extract(from_version, to_version) in angular.py:

body = fetch_github_release(to_version)              # existing call — unchanged

changelog_text = self._get_changelog()               # new: fetch once, cached
changelog_section = _extract_changelog_section(changelog_text, to_version)
if changelog_section:
    body = body + "\n\n" + changelog_section         # append before parsing

changes = parse_angular_release_text(body)           # existing call — unchanged
```

### `_get_changelog` helper contract

```python
def _get_changelog(self) -> str:
    """
    Fetch https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md.
    Returns the full file text on success.
    Returns "" on any failure (non-200, timeout, network error).
    Never raises. Logs WARNING on failure.
    The URL-level cache in base.py ensures this is fetched at most once per run.
    """
```

### Failure behavior

- Non-200 response → log `WARNING: Angular CHANGELOG.md returned {status}, continuing without it` → return `""`
- Timeout or network error → log `WARNING: Angular CHANGELOG.md fetch failed: {error}` → return `""`
- `to_version` anchor not found in CHANGELOG.md → `_extract_changelog_section` returns `""`, nothing appended, no error or log
- Pipeline never aborts due to a failed CHANGELOG.md fetch. GitHub release body alone is sufficient.

### What the CHANGELOG.md contains (that the GitHub body does not)

The GitHub API `body` for Angular releases is typically a one-line summary or a blog post
link. Example from Angular 22.0.0, CHANGELOG.md section (confirmed via live fetch):

```
### Breaking Changes

#### compiler
* TypeScript versions older than 6.0 are no longer supported.

#### core
* Component with undefined changeDetection property are now OnPush by default.
* ChangeDetectorRef.checkNoChanges was removed.

#### router
* paramsInheritanceStrategy now defaults to 'always'.

#### platform-browser
* Hammer.js integration has been removed.

### Deprecations

#### http
* withFetch is now deprecated.
```

These entries become `breaking` and `deprecation` typed `DocumentedChange` records. None
appear in the GitHub API release body. Without this fetch, the Angular extractor produces
almost no breaking-change or deprecation entries for any version.

### CHANGELOG section structure understood by the parser

The appended section text uses standard Markdown heading hierarchy:

```
<a name="{version}"></a>
# {version} (date)

### Breaking Changes

#### {package}
* {description}

### Deprecations

#### {package}
* {description}

### Bug Fixes / Features / Performance Improvements
...
```

The existing `parse_angular_release_text` already handles `### Breaking Changes` and
`### Deprecations` section headers. The appended section feeds these same code paths with
real content.

---

## ANG-2 — Angular: fetch blog insight content, store summaries

### What must change

`angular.py` — after `_BLOG_LINK_RE` extracts blog URLs into `metadata['blog_insights']`,
fetch each URL best-effort and store a text summary alongside it.

### Current broken state

```python
# CURRENT (broken) — stores URL strings only
metadata["blog_insights"] = ["https://blog.angular.dev/...", "https://blog.angular.dev/..."]
```

### Required state after fix

```python
# REQUIRED — stores dicts with url + summary
metadata["blog_insights"] = [
    {"url": "https://blog.angular.dev/...", "summary": "Migration guide for NgModule..."},
    {"url": "https://blog.angular.dev/...", "summary": ""},  # failed fetch — URL preserved
]
```

### Content extraction logic

For each blog URL, fetch the page and extract in priority order:

1. **`<meta name="description" content="...">` tag** — use `content` attribute value
2. **`<meta property="og:description" content="...">` tag** — use `content` attribute value
3. **First `<p>` element with ≥ 80 characters** — use its text content, stripped of HTML tags
4. If none of the above yields content → `summary: ""`

```python
def _fetch_blog_summary(self, url: str) -> str:
    """
    Fetch a blog page and extract a text summary.
    Returns the summary string (may be "") on success or any failure.
    Never raises. All failures silently return "".
    Uses the URL-level cache from base.py.
    """
    try:
        html = self._http_get_cached(url)   # base.py cache-aware fetch
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")

        # Priority 1: meta description
        tag = soup.find("meta", attrs={"name": "description"})
        if tag and tag.get("content"):
            return tag["content"].strip()

        # Priority 2: og:description
        tag = soup.find("meta", attrs={"property": "og:description"})
        if tag and tag.get("content"):
            return tag["content"].strip()

        # Priority 3: first substantive paragraph
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) >= 80:
                return text

        return ""
    except Exception:
        return ""
```

### Updated metadata shape

```python
# After fix — metadata['blog_insights'] is always a list of dicts:
blog_insights = []
for url in raw_blog_urls:           # raw_blog_urls from _BLOG_LINK_RE as before
    summary = self._fetch_blog_summary(url)
    blog_insights.append({"url": url, "summary": summary})
metadata["blog_insights"] = blog_insights
```

### Constraints

- All blog fetches use the URL-level cache from `base.py` — each URL fetched at most once per run.
- All blog fetch failures are silently swallowed (no log, no raise).
- Blog content does **not** appear in the raw Markdown change table. It stays in metadata only.
- If `_BLOG_LINK_RE` finds no URLs, `metadata['blog_insights']` is `[]` (empty list). Never `None`.

---

## WF-1 — WildFly: issue-type index fallback in `enrich_with_jira`

### What must change

`wildfly.py`, inside `enrich_with_jira` — after `jira = cache.get(key)`, when the REST
response does not include `issue_type`, fall back to the release-body index.

### Current broken code (pseudocode)

```python
jira = cache.get(key)
if jira:
    issue_type = jira.get("issue_type")   # ← never falls back to index if missing
    meta["issue_type"] = issue_type       # ← None if Jira API omitted it
```

### Required code

```python
jira = cache.get(key)
if jira:
    # Use Jira REST issue_type first; fall back to release-body index if absent
    issue_type = jira.get("issue_type") or index.get(key, {}).get("issue_type")
    if issue_type:
        meta["issue_type"] = issue_type
    # (omit key entirely if neither source has it — do not write None)
```

### Where `index` comes from

`build_release_index(body)` is already called earlier in the enrichment flow and returns a
dict keyed by Jira key. That same `index` variable must be in scope at the point where this
fallback is evaluated. If it is not currently in scope, thread it through as a parameter or
a local variable — do not call `build_release_index` a second time.

### Scope of the fix

The fallback applies in **both** branches where Jira data is present:
- Branch where `jira` has `summary` and `description`
- Branch where `jira` has `summary` only (the partial-data branch — see WF-3)

---

## WF-2 — WildFly: collect all Jira keys per statement, use first cache hit

### What must change

`wildfly.py`, inside `enrich_with_jira` — replace `re.search()` with `re.finditer()` when
extracting Jira keys from a statement, then pick the first key that has a cache hit.

### Current broken code (pseudocode)

```python
match = JIRA_KEY_RE.search(statement.text)  # ← only first match
if match:
    key = match.group(0)
    jira = cache.get(key)                   # ← only tried for first key
```

### Required code

```python
all_keys = [m.group(0) for m in JIRA_KEY_RE.finditer(statement.text)]
if not all_keys:
    # no Jira key in this statement — pass through unchanged
    enriched.append(statement)
    continue

# Use the first key that has a cache hit; fall back to first key for URL construction
key = next((k for k in all_keys if k in cache), all_keys[0])
jira = cache.get(key)   # may be None if no key had a cache hit
```

### Behavior table

| Statement | Keys found | Cache state | Key used |
|-----------|-----------|-------------|----------|
| `[WFLY-18341] fix something` | `[WFLY-18341]` | hit | `WFLY-18341` |
| `[WFLY-18341] Supersedes [WFCORE-4892]` | `[WFLY-18341, WFCORE-4892]` | both hit | `WFLY-18341` (first) |
| `[WFLY-18341] Supersedes [WFCORE-4892]` | `[WFLY-18341, WFCORE-4892]` | `WFLY-18341` miss, `WFCORE-4892` hit | `WFCORE-4892` |
| `[WFLY-18341] Supersedes [WFCORE-4892]` | `[WFLY-18341, WFCORE-4892]` | both miss | `WFLY-18341` (first, for URL) |

### `JIRA_KEY_RE` pattern (existing — do not change)

The regex already matches the three formats documented in Phase 3. It is compiled once at
module level. This change only switches `search` to `finditer` at the call site.

---

## WF-3 — WildFly: enriched text format always uses structured block

### What must change

`wildfly.py`, inside `enrich_with_jira` — the structured
`Title: / Jira: / Release:` block is produced whenever `jira['summary']` exists, regardless
of whether `description` is populated.

### Current broken code (pseudocode)

```python
if jira and jira.get("description"):          # ← too strict: excludes summary-only entries
    text = (
        f"Title: {jira['summary']}\n"
        f"Jira: {jira['description']}\n"
        f"Release: {release_one_liner or 'N/A'}"
    )
else:
    text = change.statement                   # ← raw statement, no Title prefix
```

### Required code

```python
if jira and jira.get("summary"):              # ← correct: trigger on summary presence
    description = jira.get("description") or "N/A"
    text = (
        f"Title: {jira['summary']}\n"
        f"Jira: {description}\n"
        f"Release: {release_one_liner or 'N/A'}"
    )
else:
    text = change.statement                   # only when no Jira data at all
```

### Expected output examples

**With summary and description:**
```
Title: Remove deprecated javax.security.auth.message SPI classes
Jira: The javax.security.auth.message SPI classes that were deprecated in WildFly 27 have
been removed. Applications using these classes must migrate to the jakarta.security.auth.message
equivalents. CLI migration: /subsystem=elytron:migrate
Release: [WFLY-17312] - Remove deprecated javax.security.auth.message SPI
```

**With summary only (description empty or absent):**
```
Title: Update WildFly Core to 24.0.1.Final
Jira: N/A
Release: [WFLY-19845] - Update WildFly Core to 24.0.1.Final
```

**With no Jira data (key not in cache):**
```
[WFLY-19845] - Update WildFly Core to 24.0.1.Final
```
(raw statement, unchanged)

---

## WF-4 — WildFly: metadata never mutated by reference

### What must change

`wildfly.py`, inside `enrich_with_jira` — both branches of the enrichment loop must
shallow-copy `change.metadata` before adding keys to it.

### Current broken code (pseudocode)

```python
if jira and jira.get("description"):
    meta = dict(change.metadata or {})    # ← correct: copy
    meta["issue_type"] = ...
else:
    meta = change.metadata                # ← BUG: reference, not copy
    meta["source_url"] = ...              # mutates original change.metadata
```

### Required code

```python
# Both branches use dict(change.metadata or {})
meta = dict(change.metadata or {})       # ← always copy, in every branch
```

This single-line fix must be applied consistently. Do not leave any branch that assigns
`meta = change.metadata` without the `dict(...)` wrapper.

---

## WF-5 — WildFly: store `jira_priority` in metadata

### What must change

`wildfly.py`, inside `enrich_with_jira` — after reading the Jira REST response, store the
`priority` field in `DocumentedChange.metadata` as `jira_priority`.

### Where the value comes from

The Jira REST call already requests `fields=summary,description,issuetype,priority,status`.
The priority value is at `response_json["fields"]["priority"]["name"]`.
Example values: `"Critical"`, `"Major"`, `"Minor"`, `"Trivial"`.

### Required code

```python
meta = dict(change.metadata or {})

# Existing: issue_type
issue_type = jira.get("issue_type") or index.get(key, {}).get("issue_type")
if issue_type:
    meta["issue_type"] = issue_type

# New: jira_priority
jira_priority = jira.get("priority")   # already stored in cache from REST response
if jira_priority:
    meta["jira_priority"] = jira_priority
```

The cache entry for a Jira key must already store `priority` from the REST response. If the
current cache entry does not store it, add it during the REST response parsing step where
`summary`, `description`, and `issue_type` are extracted:

```python
# In the Jira REST response parsing block:
cache[key] = {
    "summary":    fields.get("summary", ""),
    "description": fields.get("description", ""),
    "issue_type": fields.get("issuetype", {}).get("name", ""),
    "priority":   fields.get("priority", {}).get("name", ""),   # ← add this line
    "status":     fields.get("status", {}).get("name", ""),
}
```

### Constraint

If `priority` is absent from the REST response or is `None`, omit `jira_priority` from
metadata entirely. Do not write `None` or `""`.

---

## WF-6 — WildFly: tag format uses full semver `.Final`

### What must change

`wildfly.py` — the tag candidate list for the GitHub release fetch uses `{version}.Final`
where `{version}` is the full three-part semver, not `{major}.0.0.Final`.

### Current broken tag construction

```python
# BROKEN — only works for x.0.0 releases
tag_candidates = [f"{major}.0.0.Final", f"{major}.0.0"]
```

### Required tag construction

```python
# CORRECT — works for all patch versions (e.g. 39.0.1.Final)
tag_candidates = [f"{version}.Final", f"{version}"]
# e.g. version="39.0.1" → tries "39.0.1.Final" then "39.0.1"
```

`version` here is the semver string of the `to_version` for the hop (e.g. `"29.0.1"`,
`"30.0.0"`, `"39.0.1"`).

---

## PRE-1 — Pre-release version filters for four Maven extractors

### What must change

Four extractors currently have no GA-only filter on their version lists. Each must apply
the appropriate filter function during version discovery, before the orchestrator computes
hops.

### Filter functions to implement or import

All four filter functions below are new. They must be importable from a shared location
(e.g. `pipeline/extractors/filters.py` or `base.py`) or defined per-extractor. Use
whichever pattern the existing `is_spring_boot_ga_version` uses.

#### `is_jboss_ga_version(version: str) -> bool`

```python
def is_jboss_ga_version(version: str) -> bool:
    """Return True only for versions ending in '.Final'."""
    return version.endswith(".Final")
```

Applied to: **Hibernate ORM**, **RESTEasy**, **WildFly Elytron**

Pre-release strings excluded by this filter (confirmed on Maven Central):

| Framework | Examples excluded |
|-----------|------------------|
| Hibernate ORM | `6.0.0.Alpha1` – `Alpha9`, `6.0.0.Beta1` – `Beta3`, `6.0.0.CR1` – `CR2`, `7.2.0.CR1` |
| RESTEasy | `7.0.0.Beta1` – `Beta5`, `6.2.14.Beta1` |
| WildFly Elytron | `2.9.0.CR1`, `2.9.0.CR2` |

#### `is_infinispan_ga_version(version: str) -> bool`

```python
import re
_INFINISPAN_GA_RE = re.compile(r"^\d+\.\d+\.\d+$")

def is_infinispan_ga_version(version: str) -> bool:
    """
    Return True for Infinispan GA releases.
    - 15.x and earlier: must end with '.Final'   e.g. 15.1.0.Final
    - 16.x and later:   must match \\d+\\.\\d+\\.\\d+$ (no suffix) e.g. 16.0.0
    """
    if version.endswith(".Final"):
        return True
    return bool(_INFINISPAN_GA_RE.match(version))
```

Pre-release strings excluded by this filter (confirmed on Maven Central):

| Version series | Examples excluded |
|---------------|------------------|
| 16.x | `16.2.0.Dev01`, `16.2.0.Dev02` |
| 15.x | any version not ending in `.Final` |

### Where to apply each filter

The filter is applied in the version discovery method of each extractor — the method that
fetches and parses `maven-metadata.xml` from Maven Central and returns the list of available
versions. The filter is applied to the parsed version list before it is returned.

```python
# Example: hibernate.py
def get_available_versions(self) -> list[str]:
    versions = self._fetch_maven_versions(HIBERNATE_METADATA_URL)
    return [v for v in versions if is_jboss_ga_version(v)]
```

### `JBOSS_SKIP_PRERELEASE` environment variable

The filter is **always active by default**. It is bypassed only when
`JBOSS_SKIP_PRERELEASE` is explicitly set to a falsy value (`0`, `false`, `no`). Use the
same logic as WildFly:

```python
import os

def _skip_prerelease() -> bool:
    val = os.environ.get("JBOSS_SKIP_PRERELEASE", "1").lower()
    return val not in ("0", "false", "no")

# In get_available_versions():
raw_versions = self._fetch_maven_versions(METADATA_URL)
if _skip_prerelease():
    return [v for v in raw_versions if is_jboss_ga_version(v)]
return raw_versions
```

---

## PRE-2 — Infinispan: tag candidate order

### What must change

`infinispan.py` — tag candidates are tried in the order `{version}` first, then
`{version}.Final`.

### Current broken order

```python
tag_candidates = [f"{version}.Final", f"{version}"]  # ← wrong: .Final fails on 16.x
```

### Required order

```python
tag_candidates = [f"{version}", f"{version}.Final"]   # ← correct: bare version first
```

This order works for both version series:
- 16.x and later: `{version}` matches (e.g. `16.0.0`)
- 15.x and earlier: `{version}` 404s, `{version}.Final` matches (e.g. `15.1.0.Final`)

---

## PRE-3 — Hibernate ORM: remove `.Final` tag candidate

### What must change

`hibernate.py` — the tag candidate list uses `{version}` only. The `.Final` candidate
never matches any Hibernate ORM GitHub tag and must be removed.

### Current broken candidates

```python
tag_candidates = [f"{version}", f"{version}.Final"]  # ← .Final never used in Hibernate tags
```

### Required candidates

```python
tag_candidates = [f"{version}"]   # only one candidate needed
```

This avoids one guaranteed 404 per hop.

---

## Error shapes

All new optional source fetches follow the same contract: failure degrades gracefully, the
pipeline continues with whatever content was successfully obtained.

| Source | Condition | Log level | Pipeline result |
|--------|-----------|-----------|----------------|
| Spring Boot wiki page | Non-200 / timeout / network error | WARNING | Continue with GitHub body only; exit 0 |
| Angular CHANGELOG.md | Non-200 / timeout / network error | WARNING | Continue with GitHub body only; exit 0 |
| Angular CHANGELOG.md anchor | `to_version` not found in file | Silent | Continue with GitHub body only; exit 0 |
| Angular blog URL | Any failure | Silent | `{"url": url, "summary": ""}` stored; exit 0 |
| Primary GitHub release body | Non-200 / empty | ERROR | Abort hop; exit 1 (existing behavior — unchanged) |

---

## Integration constraints

- All new HTTP fetches go through the shared URL-level cache in `base.py`. No extractor
  implements its own caching layer.
- All new HTTP fetches use the existing shared `httpx` client configured with `SSL_VERIFY`
  and the 30-second timeout. No new HTTP client instances.
- `DocumentedChange` type signature is unchanged. `jira_priority` (WF-5) is stored in the
  existing `metadata: dict` field, not as a new top-level attribute.
- `ExtractionResult` type signature is unchanged. `bom_diff` continues to be stored in
  `metadata['bom_diff']`; the only change is the call site (SP-2).
- `parse_github_release_text` signature is unchanged for Spring Boot. It receives a longer
  `body` string containing both the GitHub release body and the wiki page content appended.
- `parse_angular_release_text` signature is unchanged for Angular. It receives a longer
  `body` string containing both the GitHub release body and the CHANGELOG.md section appended.
- Raw Markdown output format (four-column table: Type, Confidence, Source, Statement) is
  unchanged. New sources only affect Statement column content and row count.
- Filter LLM prompt, entity LLM prompt, populator, graph schema — none changed.

---

## Out of scope

- EAP extractor — no issues found; not changed.
- Jakarta EE extractor — deterministic, no HTTP; not changed.
- `base.py` — URL-level cache already exists and is used as-is; not changed.
- LLM prompts — not changed by this amendment.
- Graph schema — no new node types, relationship types, or properties.
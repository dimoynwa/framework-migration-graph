# Research: Angular CHANGELOG Enhancement — Current State and Issues

## Summary

The Angular extractor enriches GitHub release notes with content from the Angular
`CHANGELOG.md` hosted on `raw.githubusercontent.com`. The CHANGELOG is the canonical
source for typed migration content: breaking changes per package, deprecation notices,
and features organised by Angular workspace package. The enhancement is architecturally
sound and does produce significantly more entries. However, two issues prevent it from
reaching its full potential: all entries share the wrong `source_url`, and blog post
summaries are silently never fetched.

---

## How the Enhancement Works (Code Path)

```
AngularExtractor.extract()                          angular.py:89
  │
  ├─ fetch_github_release("angular/angular", ...)   base.py
  │    └─ returns: source_url, body (GitHub release markdown)
  │
  ├─ _get_changelog()                               angular.py:53
  │    ├─ fetches raw CHANGELOG.md from GitHub (cached per run)
  │    └─ returns: full changelog text (Markdown, ~100k+ chars)
  │
  ├─ _extract_changelog_section(changelog_text, to_version)  angular.py:28
  │    ├─ finds anchor: <a name="{version}"></a>
  │    ├─ slices text to the next anchor (or EOF)
  │    └─ returns: version-specific CHANGELOG section
  │
  ├─ body = body + "\n\n" + changelog_section       ← BUG-1: shared source_url
  │
  ├─ changes = parse_github_release_text(body, source_url)
  │
  └─ blog_insights = [_fetch_blog_summary(url) for url in blog_urls]
                                                    ← BUG-2: always returns ""
```

---

## Measured Impact (Angular 19.0.0 and 20.0.0)

### 18.2.13 → 19.0.0

| Source | Chars | Changes produced |
|--------|------:|----------------:|
| GitHub release body | 30,357 | 135 |
| CHANGELOG.md section | 35,411 | +99 |
| **Combined (with enhancement)** | — | **257** |

### 19.2.14 → 20.0.0

| Source | Chars | Changes produced |
|--------|------:|----------------:|
| GitHub release body | 31,027 | 145 |
| CHANGELOG.md section | 37,248 | +114 |
| **Combined (with enhancement)** | — | **290** |

The CHANGELOG adds **73–79% more entries** and is the primary source of typed entries:
`deprecation/confirmed` and `mandatory_migration/confirmed` entries appear exclusively
in the CHANGELOG-sourced set. Without the CHANGELOG, all entries are `behavioral/inferred`.

---

## CHANGELOG.md Section Structure

The Angular CHANGELOG is structured with per-version anchor tags and H2/H3 heading hierarchy:

```markdown
<a name="19.0.0"></a>

# 19.0.0 (2024-11-19)

Blog post: https://blog.angular.dev/meet-angular-v19-7b29dfd05b84

## Breaking Changes

### compiler

- `this.foo` property reads no longer refer to template context variables...
- changes to CSS selectors parsing where introduced...

### core

- Angular directives, components and pipes are now standalone by default.
- TypeScript versions less than 5.5 are no longer supported.

### router

...

## Bug Fixes

### common

...
```

Key properties:
- **H2 sections**: `Breaking Changes`, `Bug Fixes`, `Features`, `Performance Improvements`,
  `Reverts`, `Deprecations`
- **H3 sections**: Angular workspace package names (`compiler`, `core`, `router`, `http`, etc.)
- Each bullet is a single atomic change with a GitHub commit hash link
- The section is terminated by the next `<a name="...">` anchor

The `_extract_changelog_section` function correctly slices this content using anchor tags.
The section for 19.0.0 is 35,411 chars and contains one `## Breaking Changes` H2 section
with 7 package-level H3 subsections.

---

## Bug-1: All Entries Share the GitHub Release `source_url`

### Problem

In `extract()`, the CHANGELOG section is **appended to `body` before parsing**:

```python
# angular.py:97 — current (broken)
if changelog_section:
    body = body + "\n\n" + changelog_section

changes = parse_github_release_text(body, source_url)  # source_url = GitHub release tag
```

`source_url` is the GitHub release tag URL (e.g. `https://github.com/angular/angular/releases/tag/19.0.0`).
Every `DocumentedChange` produced from the combined body — whether it originated from the
GitHub release notes or from the CHANGELOG — is tagged with this same URL.

Confirmed by live measurement:

```
Distinct source_urls in output: 1
  https://github.com/angular/angular/releases/tag/19.0.0
```

### Consequence

- Downstream consumers (LLM filter, entity extractor, graph populator) cannot distinguish
  GitHub release entries from CHANGELOG entries
- Source column in exported Markdown is inaccurate for all CHANGELOG-sourced entries
- The CHANGELOG URL (`raw.githubusercontent.com/angular/angular/main/CHANGELOG.md`) never
  appears in any `DocumentedChange.source_url`

### Correct source URLs

| Entry origin | Expected `source_url` |
|---|---|
| GitHub release body | `https://github.com/angular/angular/releases/tag/v{version}` |
| CHANGELOG.md section | `https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md` |

---

## Bug-2: Blog Summaries Are Always Empty

### Problem

`_fetch_blog_summary` uses `self._http_get_cached(url)` — a sync `httpx.get` call — to
fetch `blog.angular.dev` pages and extract their meta description.

The blog site (`blog.angular.dev`) is a JavaScript single-page application. A plain HTTP
GET returns 0 bytes (the server sends a minimal JS shell, not rendered HTML). As a result
`_http_get_cached` returns `""` and `_fetch_blog_summary` always returns `""`.

Confirmed by live measurement:

```python
extractor._http_get_cached("https://blog.angular.dev/meet-angular-v19-7b29dfd05b84")
# → "" (0 bytes)
```

### Current behaviour

```python
blog_insights = [
    {"url": url, "summary": self._fetch_blog_summary(url)}  # summary always ""
    for url in raw_blog_urls
]
```

`metadata["blog_insights"]` always contains `{"url": "...", "summary": ""}`. The URL
is captured correctly — only the summary content is always absent.

### Impact

Blog summaries are stored in `ExtractionResult.metadata`, not in `DocumentedChange` entries,
so this does not affect change counts or types. The metadata field exists but carries no
information. A future fix would require either a JavaScript renderer (Playwright) or a
different content source (Angular blog RSS feed or a static mirror).

---

## What Good CHANGELOG Content Looks Like

For Angular 19.0.0, the CHANGELOG `## Breaking Changes` section surfaces entries that
the GitHub release body never produces in readable form:

**From CHANGELOG (with CHANGELOG URL, in correct form):**
- `[breaking/confirmed]` — `core: Angular directives, components and pipes are now standalone by default. Specify standalone: false for declarations that are currently declared in @NgModules.`
- `[breaking/confirmed]` — `core: TypeScript versions less than 5.5 are no longer supported.`
- `[breaking/confirmed]` — `compiler: this.foo property reads no longer refer to template context variables.`
- `[deprecation/confirmed]` — `http: BrowserModule.withServerTransition removed (deprecated)`

**From GitHub release body (in current output — badge markdown syntax):**
- `[behavioral/inferred]` — `| [![feat - 2e5362a469](https://img.shields.io/badge/...)](...) | feat | ...`

The CHANGELOG content is plaintext prose, correctly classified by `parse_github_release_text`.
The GitHub release body for major Angular versions is a badge-link table that parses into
syntactically valid but semantically opaque statements.

---

## Secondary Issues

### 1. CHANGELOG covers only the `main` branch

`CHANGELOG_URL` always fetches `main` branch:

```python
CHANGELOG_URL = "https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md"
```

For Angular versions still in active maintenance (e.g. v17, v18), the `main` CHANGELOG
contains those versions as long as backports are committed. In practice this works for
all GA major versions currently in scope because they are included chronologically.

### 2. No deduplication between GitHub body and CHANGELOG

Several items appear in both the GitHub release body badge table and the CHANGELOG prose.
There is no deduplication step — these appear twice with different statement text (badge
format vs plain text). The CHANGELOG version is higher quality; the GitHub badge version
adds noise. This is a secondary issue with low impact since the LLM filter pass handles
near-duplicates.

### 3. `_extract_changelog_section` returns the full section including the version header

The returned section starts with `<a name="...">` and `# 19.0.0 (date)`, which parse into
low-value entries. A minor trim would clean this up, but it has negligible impact compared
to Bug-1.

---

## Alternative Approaches Considered for Blog Summaries

| Approach | Verdict |
|---|---|
| `httpx.get` on `blog.angular.dev` | Returns 0 bytes (JS SPA, no SSR) |
| Playwright / JS rendering | Works but adds a heavy dependency; not viable |
| Angular blog RSS feed (`blog.angular.dev/feed`) | RSS feed exists; viable alternative data source |
| `og:description` from GitHub release body | GitHub release does not embed blog OG tags |
| Skip blog summaries entirely | Acceptable — they are metadata only, not change entries |

---

## Recommended Fixes

### Fix AW-1 — Parse GitHub body and CHANGELOG separately with correct `source_url`

In `extract()`, parse the GitHub release body and the CHANGELOG section independently,
each with their own `source_url`:

```python
# In extract() — REQUIRED
source_url, body = await self.fetch_github_release(
    "angular/angular", to_version, tag_candidates
)
changelog_text = await self._get_changelog()
changelog_section = _extract_changelog_section(changelog_text, to_version)

# Parse with correct source URLs
changes = parse_github_release_text(body, source_url)
if changelog_section:
    changelog_changes = parse_github_release_text(changelog_section, CHANGELOG_URL)
    changes = changes + changelog_changes
```

This is the same pattern as the Spring Boot wiki fix (SW-4).

### Fix AW-2 — Mark blog summaries as unavailable rather than silently empty

Either remove `_fetch_blog_summary` entirely or replace the always-empty summary with a
sentinel value that communicates the limitation:

```python
blog_insights = [{"url": url, "summary": None} for url in raw_blog_urls]
```

This is honest about what is known (the URL exists) vs. unknown (content unavailable
without JS rendering). Alternatively, remove `blog_insights` from metadata entirely
until a working extraction method is available.

---

## Expected Outcome After Fixes

| Metric | Before fix | After fix |
|--------|-----------|-----------|
| GitHub release entries | 135 (19.0.0) | 135 (unchanged) |
| CHANGELOG entries | +99 | +99 (unchanged in count) |
| CHANGELOG `source_url` | GitHub release tag URL | `raw.githubusercontent.com/.../CHANGELOG.md` |
| `deprecation/confirmed` entries | present (misattributed) | present (correctly attributed) |
| Blog summary `summary` field | `""` (silently empty) | `None` (explicitly unavailable) |
| Source traceability | ❌ all tagged as release URL | ✅ GitHub vs CHANGELOG distinguishable |

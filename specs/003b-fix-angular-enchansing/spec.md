# spec.md — Angular CHANGELOG Enhancement Fix

**Location:** `specs/003b-fix-angular-enchansing/spec.md`
**Type:** Bug fix — correcting source provenance and removing duplicate entries
**Branch:** `003b-fix-angular-enchansing`
**Source:** `specs/003b-fix-angular-enchansing/research.md` — June 2026
**Prerequisites:** `001-foundation` ✅, `002-pipeline-core` ✅, `003-framework-http-extractors` ✅, `003b-extractors-improvements` ✅

---

## Context and scope

`AngularExtractor.extract()` enriches the GitHub release body with a version-specific section
from Angular's `CHANGELOG.md`, fetched from `raw.githubusercontent.com`. The CHANGELOG is the
canonical source for typed migration content: `## Breaking Changes` and `## Deprecations`
sections per Angular workspace package. The enhancement is architecturally sound, but two
structural issues limit its value:

**Bug AW-1 — Shared `source_url`:** The CHANGELOG section is concatenated with the GitHub
release body *before* parsing. All resulting `DocumentedChange` entries inherit the GitHub
release tag URL as `source_url`, regardless of their actual origin. There is no way
downstream to distinguish which entries came from the release notes vs. the CHANGELOG.

**Bug AW-2 — Duplicate entries for v20–v22:** Live measurement shows that for Angular v20,
v21, and v22 the GitHub release body already embeds the full CHANGELOG content verbatim.
Appending the CHANGELOG section before parsing causes every entry to appear twice with
slightly different statement text:

| Hop | GH body changes | CHANGELOG changes | Duplicates added |
|-----|----------------:|------------------:|-----------------:|
| 18.0.0 → 19.0.0 | 135 | 122 (different) | 0 |
| 19.0.0 → 20.0.0 | 145 | 145 (identical) | ~145 |
| 20.0.0 → 21.0.0 | 110 | 111 (identical) | ~110 |
| 21.0.0 → 22.0.0 | 153 | 154 (identical) | ~153 |

For three of the four in-scope hops, the enhancement currently *worsens* output quality
by roughly doubling the entry count with duplicates.

**Non-bug: Blog summaries silently empty.** `_fetch_blog_summary` calls `_http_get_cached`
(which exists and works), but `blog.angular.dev` is a JavaScript SPA — `httpx.get` returns
0 bytes on all pages. No Angular release in scope links to a blog post in its GitHub release
body, so this is a latent issue with no current impact. The blog infrastructure will not be
changed in this spec.

All changes are in `angular.py` only. No changes to `base.py`, `parsing.py`, `filters.py`,
or any other extractor.

---

## Files changed

| File | Changes |
|------|---------|
| `migration_oracle/pipeline/extractors/angular.py` | AW-1, AW-2 |

---

## AW-1 — Parse GitHub body and CHANGELOG separately with correct `source_url`

### Problem

In `extract()` (angular.py:97–99):

```python
# CURRENT (broken)
if changelog_section:
    body = body + "\n\n" + changelog_section  # ← merges before parsing

changes = parse_github_release_text(body, source_url)  # ← all entries get release URL
```

The CHANGELOG URL (`CHANGELOG_URL = "https://raw.githubusercontent.com/..."`) never
appears in any `DocumentedChange.source_url`. Confirmed live: all 257 entries for the
18→19 hop carry `https://github.com/angular/angular/releases/tag/19.0.0`.

### What must change

Parse the GitHub release body and CHANGELOG section independently, each with their own
`source_url`, then combine the resulting change lists:

```python
# REQUIRED
source_url, body = await self.fetch_github_release(
    "angular/angular", to_version, tag_candidates
)
changelog_text = await self._get_changelog()
changelog_section = _extract_changelog_section(changelog_text, to_version)

# Parse each source with its own URL
changes = parse_github_release_text(body, source_url)
if changelog_section:
    changelog_changes = parse_github_release_text(changelog_section, CHANGELOG_URL)
    changes = changes + changelog_changes
```

### Expected effect

| Entry origin | Before | After |
|---|---|---|
| GitHub release entry `source_url` | Release tag URL | Release tag URL (unchanged) |
| CHANGELOG entry `source_url` | Release tag URL (wrong) | `CHANGELOG_URL` (correct) |

The total change count is not affected by AW-1 alone. Deduplication (AW-2) removes the
excess entries.

---

## AW-2 — Deduplicate CHANGELOG entries that duplicate the GitHub release body

### Problem

For Angular v20.0.0, v21.0.0, and v22.0.0 the GitHub release body already contains the
full CHANGELOG section verbatim. After AW-1 (separate parse), the combined list has
duplicate entries with identical statements but different `source_url` values. This doubles
the LLM filter workload and inflates graph entity counts with redundant nodes.

### What must change

After merging the two change lists, deduplicate by statement text. When a statement appears
in both sources, keep the **CHANGELOG version** (it carries the more specific `source_url`)
and discard the GitHub release body version:

```python
if changelog_section:
    changelog_changes = parse_github_release_text(changelog_section, CHANGELOG_URL)
    # Deduplicate: prefer CHANGELOG entry when statement text matches
    cl_statements = {c.statement for c in changelog_changes}
    gh_unique = [c for c in changes if c.statement not in cl_statements]
    changes = gh_unique + changelog_changes
```

A statement-text match is sufficient. Confidence and type may differ slightly due to
classifier context — the CHANGELOG version is preferred because it was parsed against the
correct `source_url`.

### Expected effect

| Hop | Before AW-2 (with AW-1) | After AW-2 |
|-----|------------------------:|----------:|
| 18.0.0 → 19.0.0 | 135 + 122 = 257 | ~222 (no overlap) |
| 19.0.0 → 20.0.0 | 145 + 145 = 290 | ~145 (near-full dedup) |
| 20.0.0 → 21.0.0 | 110 + 111 = 221 | ~111 (near-full dedup) |
| 21.0.0 → 22.0.0 | 153 + 154 = 307 | ~154 (near-full dedup) |

For the 18→19 hop (the only one where GH body and CHANGELOG have distinct content),
deduplication has minimal effect — both sources contribute genuinely different entries.

---

## Combined `extract()` implementation

After both fixes, the relevant section of `extract()` reads:

```python
async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
    tag_candidates = [f"v{to_version}", to_version]
    source_url, body = await self.fetch_github_release(
        "angular/angular", to_version, tag_candidates
    )
    changelog_text = await self._get_changelog()
    changelog_section = _extract_changelog_section(changelog_text, to_version)

    # Parse GitHub release body with its own source URL
    changes = parse_github_release_text(body, source_url)

    # Parse CHANGELOG section with CHANGELOG URL; deduplicate against GH body
    if changelog_section:
        changelog_changes = parse_github_release_text(changelog_section, CHANGELOG_URL)
        cl_statements = {c.statement for c in changelog_changes}
        gh_unique = [c for c in changes if c.statement not in cl_statements]
        changes = gh_unique + changelog_changes

    raw_blog_urls = sorted(set(_BLOG_LINK_RE.findall(body)))
    blog_insights = [
        {"url": url, "summary": self._fetch_blog_summary(url)}
        for url in raw_blog_urls
    ]
    if not changes:
        raise RuntimeError(
            f"Angular: no changes parsed for hop {from_version} → {to_version} "
            f"from {source_url}"
        )
    metadata = {"blog_insights": blog_insights}
    return ExtractionResult(changes=changes, metadata=metadata)
```

---

## Expected outcome

### Entry counts

| Hop | Current (broken) | After fix |
|-----|----------------:|----------:|
| 18.0.0 → 19.0.0 | 257 (no dedup issue) | ~222 |
| 19.0.0 → 20.0.0 | 290 (145 duplicates) | ~145 |
| 20.0.0 → 21.0.0 | 221 (110 duplicates) | ~111 |
| 21.0.0 → 22.0.0 | 307 (153 duplicates) | ~154 |

### Source attribution

After the fix, every `DocumentedChange` carries the URL of the document it was actually
extracted from. The Markdown output `Source` column becomes accurate and filterable.

### Typed entry quality

The CHANGELOG `## Breaking Changes` and `## Deprecations` sections contain human-readable
prose entries that parse to `breaking/confirmed`, `deprecation/confirmed`, and
`mandatory_migration/confirmed` types. These high-value entries are correctly attributed
to the CHANGELOG after the fix. Representative examples after AW-1+AW-2:

| Hop | Type | Statement (truncated) |
|-----|------|-----------------------|
| 18→19 | `deprecation/confirmed` | `The deprecated BrowserModule.withServerTransition method has been removed...` |
| 18→19 | `deprecation/confirmed` | `Deprecated matchesElement method has been removed from AnimationDriver...` |
| 19→20 | `deprecation/confirmed` | `ngIf/ngFor/ngSwitch are deprecated. Use the control flow blocks instead...` |
| 20→21 | `deprecation/confirmed` | `ng-reflect-* attributes are deprecated and will be removed...` |
| 21→22 | `breaking/confirmed` | (present — confirmed by CHANGELOG section analysis) |

---

## Out of scope

- No changes to `_get_changelog()`, `_extract_changelog_section()`, or `_fetch_blog_summary()`.
- No changes to `base.py`, `parsing.py`, `filters.py`, or any LLM prompt.
- No changes to `ExtractionResult` or `DocumentedChange` type signatures.
- Blog summary fetching (always empty due to JS SPA limitation) is out of scope — tracked
  separately if an RSS-based approach is implemented.
- Spring Boot, WildFly, Hibernate, and other extractor improvements are tracked in their
  own specs.

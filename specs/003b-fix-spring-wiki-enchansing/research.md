# Research: Spring Boot Wiki Enhancement — Why It Fails

## Summary

The Spring Boot extractor attempts to enrich GitHub release notes with content from the Spring Boot
wiki (e.g. `Spring-Boot-3.5-Release-Notes`). The wiki contains the highest-value migration content:
breaking changes, mandatory upgrade steps, and API deprecations. However, the current implementation
produces almost entirely noise, so the enhancement has **no net positive effect** on extraction quality.

---

## How the Enhancement Works (Code Path)

```
SpringBootExtractor.extract()                      spring_boot.py:101
  │
  ├─ fetch_github_release(...)                     base.py:237
  │    └─ returns: source_url, body (GitHub release markdown)
  │
  ├─ _fetch_wiki_release_notes(to_version)         spring_boot.py:88
  │    ├─ builds URL: github.com/.../wiki/Spring-Boot-{major}.{minor}-Release-Notes
  │    ├─ fetches full HTML page (1 MB)
  │    └─ returns: html_to_text(html)   ← BUG: passes the full page
  │
  └─ body = github_body + "\n\n" + wiki_content
       └─ parse_github_release_text(body, source_url)
```

The wiki content is appended verbatim to the GitHub release body before parsing. Both share the same
`source_url` (the GitHub release tag URL), so there is no way to distinguish wiki-sourced entries
in the output.

---

## Root Cause

**`_fetch_wiki_release_notes` calls `html_to_text(html)` on the full 1 MB GitHub page HTML**,
not on the wiki content container.

```python
# spring_boot.py:99  — current (broken)
return html_to_text(html)

# Should be:
soup = BeautifulSoup(html, "html.parser")
wiki_body = soup.select_one("#wiki-body .markdown-body")
return html_to_text(str(wiki_body)) if wiki_body else ""
```

The GitHub wiki page wraps the actual content in `#wiki-body > div.markdown-body`. Everything
outside that element is GitHub's application shell: navigation, marketing copy, footer, and
JavaScript lazy-load error messages.

---

## Measured Impact (Spring Boot 3.5.0)

| Source | Chars | "Changes" extracted | Substantive (>30 chars) |
|--------|------:|--------------------:|------------------------:|
| GitHub release body only | 8,421 | 32 | 32 |
| `html_to_text` on full wiki page | 107,788 | 496–581 | ~120 |
| `html_to_text` on `#wiki-body .markdown-body` | 35,792 | 142 | 83 |

Scoping to the correct CSS selector eliminates **66.8% of the raw text** (71,996 chars of noise)
and reduces parsed "changes" from ~550 down to 142 — a much more trustworthy set.

The 32 GitHub release changes are clean and all legitimate. The 496–581 wiki-sourced entries
produced by the current implementation contain roughly:

- **~400 error/garbage items** — JS lazy-load failure messages, GitHub navigation elements,
  marketing copy, footer links
- **~120 potentially useful items** — of which ~83 are substantive (>30 chars)

The ratio is approximately **17:1 noise-to-signal** for wiki additions.

---

## What Good Wiki Content Looks Like

The wiki's `#wiki-body .markdown-body` contains three top-level H2 sections that map directly to
migration concerns:

### 1. "Upgrading from Spring Boot X.Y" (mandatory migration)

Rich prose subsections under H3 headings, each describing a breaking change with context and
remediation steps. Example (3.5.0):

> **Actuator 'heapdump' Endpoint** — The `heapdump` actuator endpoint now defaults to
> `access=NONE`. If you want to use it, you now need to both expose it and configure access.

> **Using '.enabled' and Other Boolean Configuration Properties** — Values must now be either
> `true` or `false`. Previous versions would sometimes consider any value other than `false` as
> enabled.

> **Auto-configured TaskExecutor Names** — Only `applicationTaskExecutor` is now provided (no
> longer `taskExecutor`). Code requesting the executor by name must be adapted.

### 2. "New and Noteworthy" (new features)

Bullet and prose items covering new configuration properties, new annotations, new auto-configured
beans, integration updates, etc.

### 3. "Deprecations in Spring Boot X.Y.Z" (deprecation notices)

A structured list of deprecated APIs with their replacements. Example:

> `spring.mvc.converters.preferred-json-mapper` deprecated, replaced by
> `spring.http.converters.preferred-json-mapper`.

---

## Secondary Issues Found

### 1. Short/noise items even after scoping to wiki body (59 of 142)

The wiki's "Dependency Upgrades" section lists library versions as bare bullet items
(`Cassandra`, `Redis`, `HikariCP 6.3`, etc.) without upgrade context. These pass through
`parse_markdown_statements` as low-value `behavioral/inferred` entries. The existing
`_strip_dependency_upgrades` filter in `SpringBootExtractor` strips these from the GitHub
release body but is **not applied to wiki content**.

### 2. Prose paragraphs not captured

The "Upgrading from" section uses prose paragraphs (not bullet lists) for its richest content.
`parse_markdown_statements` only captures `<li>` elements and markdown bullets. Paragraphs that
describe breaking changes (e.g., the heapdump and profile naming examples above) are currently
missed — they appear in `html_to_text` output but get dropped by the bullet-focused parser.

### 3. No deduplication between GitHub release and wiki

Items that appear in both the GitHub release notes and the wiki notes are currently duplicated in
the output. In practice this is rare, but it adds noise.

### 4. Shared `source_url` for all wiki content

Wiki entries are tagged with the GitHub release tag URL (`releases/tag/v3.5.0`) rather than the
wiki page URL. This makes it impossible to trace which entries came from the wiki for downstream
filtering or debugging.

---

## Alternative Approaches Considered

| Approach | Verdict |
|----------|---------|
| Fetch raw wiki Markdown via `raw.githubusercontent.com/wiki/...` | Returns HTTP 404 |
| Fetch `github.com/.../wiki/....md` with `Accept: text/plain` | Returns HTTP 406 |
| Clone the wiki git repo (`github.com/{org}/{repo}.wiki.git`) | Impractical in an async HTTP extractor |
| GitHub REST API `/repos/.../contents/...` for wiki files | Wiki not exposed via contents API |
| GitHub GraphQL API | Does not expose wiki content |
| Playwright / JS-rendering | Works but adds a heavy dependency |

**Only the HTML-scraping approach is viable** without adding new dependencies. The fix must work
with the existing `httpx`/`BeautifulSoup` stack.

---

## Recommended Fix (Scoped)

A minimal, safe fix that restores the original intent without requiring new dependencies:

### Fix 1 — Scope HTML extraction to `#wiki-body .markdown-body`

In `_fetch_wiki_release_notes` (spring_boot.py:88–99), parse the HTML and extract only the
content container before converting to text:

```python
from bs4 import BeautifulSoup

async def _fetch_wiki_release_notes(self, to_version: str) -> str:
    major, minor, _, _ = parse_version(to_version)
    url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
    try:
        html = await self.fetch(url, accept_status={200})
    except RuntimeError as exc:
        logger.warning("Spring Boot wiki page fetch failed: %s", exc)
        return ""
    if not html.strip():
        return ""
    soup = BeautifulSoup(html, "html.parser")
    wiki_body = soup.select_one("#wiki-body .markdown-body")
    if not wiki_body:
        logger.warning("Spring Boot wiki: #wiki-body .markdown-body not found in %s", url)
        return html_to_text(html)   # graceful fallback
    return html_to_text(str(wiki_body))
```

**Effect**: Reduces parsed wiki "changes" from ~550 to ~142. Eliminates the GitHub nav/marketing
noise and JS error messages entirely.

### Fix 2 — Apply `_strip_dependency_upgrades` to wiki content

The wiki "Dependency Upgrades" section should be stripped the same way it is stripped from
the GitHub release body. After extracting the wiki body text, pass it through
`_strip_dependency_upgrades` before appending to the release body. This removes the remaining
~59 short noise items (bare library names).

### Fix 3 — Parse wiki prose sections explicitly

The most valuable content in the wiki ("Upgrading from" section) is prose paragraphs, not
bullet lists. A dedicated `parse_wiki_prose_sections` function should extract:
- Section heading → used as the `type` hint for `classify_statement`
- Each paragraph sentence → becomes a `DocumentedChange` statement
- Code blocks → can be appended to the preceding paragraph for context

This would surface the breaking-change descriptions that are currently being lost.

### Fix 4 — Use the wiki page URL as `source_url` for wiki entries

When wiki content is parsed separately and then combined, wiki-sourced entries should carry the
wiki page URL as their `source_url`, not the GitHub release tag URL. This requires splitting the
parse step into two phases (parse GitHub body → parse wiki body → merge results) rather than
concatenating the text first.

---

## Expected Outcome After Fixes

| Metric | Before fix | After fix (estimated) |
|--------|-----------|----------------------|
| GitHub release changes | 32 | 32 (unchanged) |
| Wiki-added changes | ~550 (mostly noise) | ~80–100 (mostly signal) |
| Noise ratio in wiki additions | ~73% | <10% |
| Breaking changes surfaced from wiki | 0 (buried in noise) | 15–20 (prose sections) |
| Source traceability | ❌ all tagged as release URL | ✅ wiki entries use wiki URL |

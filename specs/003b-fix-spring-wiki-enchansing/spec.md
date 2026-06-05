# spec.md — Spring Boot Wiki Enhancement Fix

**Location:** `specs/003b-fix-spring-wiki-enchansing/spec.md`
**Type:** Bug fix — restoring intended wiki enrichment behaviour
**Branch:** `003b-fix-spring-wiki-enchansing`
**Source:** `specs/003b-fix-spring-wiki-enchansing/research.md` — June 2026
**Prerequisites:** `001-foundation` ✅, `002-pipeline-core` ✅, `003-framework-http-extractors` ✅, `003b-extractors-improvements` ✅

---

## Context and scope

`SpringBootExtractor.extract()` is designed to enrich the GitHub release body with content from
the Spring Boot wiki page (e.g. `Spring-Boot-3.5-Release-Notes`). The wiki is the **canonical**
source for the highest-value migration data: breaking changes, mandatory upgrade steps, and API
deprecations. The GitHub release body covers only per-issue bug fixes and feature summaries.

Live measurement of the 3.5.0 extraction (see `research.md`) confirmed that the enrichment is
completely broken in practice:

| Source | "Changes" produced | Signal | Noise |
|--------|-------------------:|-------:|------:|
| GitHub release body | 32 | 32 | 0 |
| Wiki (current — full page) | ~550 | ~120 | ~430 |

The root cause is a single-line bug in `_fetch_wiki_release_notes`: `html_to_text` is called on
the **full 1 MB GitHub page** rather than on the `#wiki-body .markdown-body` container that holds
the actual wiki content. Everything outside that container — GitHub navigation, marketing copy,
footer, and JavaScript lazy-load failure messages — is passed to the parser and produces hundreds
of garbage `DocumentedChange` entries.

Three secondary issues compound the damage: (1) the Dependency Upgrades section of the wiki is
not stripped (unlike the GitHub release body), adding ~59 bare library-version noise items;
(2) the wiki's richest content — prose paragraphs in the "Upgrading from" section — is discarded
because the parser handles only bullet lists; (3) wiki-sourced entries are tagged with the GitHub
release URL instead of the wiki URL, making them untraceable.

This spec describes four targeted fixes. All changes are in `spring_boot.py` only.
No changes to `base.py`, `parsing.py`, `filters.py`, or any LLM prompt.

---

## Files changed

| File | Changes |
|------|---------|
| `migration_oracle/pipeline/extractors/spring_boot.py` | SW-1, SW-2, SW-3, SW-4 |

---

## SW-1 — Scope HTML extraction to `#wiki-body .markdown-body`

### Problem

`_fetch_wiki_release_notes` (spring_boot.py:88–99) passes the full page HTML to `html_to_text`:

```python
# CURRENT (broken)
return html_to_text(html)
```

The full page is 1 MB. Only 35,792 of those 107,788 text characters belong to the actual wiki
content. The remaining 66.8% is GitHub's application shell and produces ~430 garbage entries.

### What must change

Before calling `html_to_text`, extract the `#wiki-body .markdown-body` container using
BeautifulSoup. Pass only that element's HTML to `html_to_text`. If the selector is not found,
log a warning and fall back to the full page (defensive — the selector has been stable on GitHub).

```python
# REQUIRED
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
        logger.warning(
            "Spring Boot wiki: #wiki-body .markdown-body not found at %s — "
            "falling back to full-page extraction",
            url,
        )
        return html_to_text(html)
    return html_to_text(str(wiki_body))
```

### Expected effect

| Metric | Before | After |
|--------|--------|-------|
| Text characters passed to parser | ~107,788 | ~35,792 |
| "Changes" from wiki | ~550 | ~142 |
| JS error/nav noise entries | ~430 | 0 |

`BeautifulSoup` is already a project dependency (used in `parsing.py:html_to_text`). No new
dependency is introduced.

### Failure behaviour (unchanged)

| Condition | Log | Pipeline |
|-----------|-----|----------|
| Non-200 / timeout | WARNING | Continue with GitHub body only; exit 0 |
| Selector `#wiki-body .markdown-body` not found | WARNING | Fall back to full-page; exit 0 |
| Empty response | Silent | Continue with GitHub body only; exit 0 |

---

## SW-2 — Strip Dependency Upgrades from wiki content

### Problem

`_strip_dependency_upgrades` is already applied to the GitHub release body (inside
`parse_github_release_text`). It is **not** applied to the wiki content before it is appended.

The wiki "Dependency Upgrades" section lists ~30 library versions as bare bullet points
(`HikariCP 6.3`, `Kafka 3.9`, `Redis`, etc.). These pass through the parser as `behavioral /
inferred` entries. They are low-information duplicates of what the BOM diff already captures
with full Maven coordinates.

### What must change

In `_fetch_wiki_release_notes`, after extracting the wiki body text via `html_to_text`, pass
it through `_strip_dependency_upgrades` before returning:

```python
# REQUIRED — append to the return path in _fetch_wiki_release_notes
wiki_text = html_to_text(str(wiki_body))
return _strip_dependency_upgrades(wiki_text)
```

The existing `_strip_dependency_upgrades` function already handles:
- `## Dependency Upgrades`
- `## 🔨 Dependency Upgrades`
- `## :hammer: Dependency Upgrades`

No changes to `_strip_dependency_upgrades` itself are needed.

### Expected effect

Eliminates ~59 bare library-version noise entries from wiki output, leaving ~83 substantive
entries (all with >30-character statements).

---

## SW-3 — Parse prose paragraphs from wiki "Upgrading from" section

### Problem

The highest-value content in the wiki is the **"Upgrading from Spring Boot X.Y"** section.
It is written in prose paragraphs (not bullet lists):

```
### Actuator 'heapdump' Endpoint
The heapdump actuator endpoint now defaults to access=NONE.
If you want to use it, you now need to both expose it, and configure access.
```

`parse_markdown_statements` (the function ultimately called on the combined body) only captures
`<li>` elements and markdown bullets (`- item`). Prose paragraphs produced by `html_to_text`
are multi-sentence blocks that do not start with `-` and are therefore skipped entirely.

As a result, **zero entries from the "Upgrading from" section** appear in the output — the most
important section of the wiki produces nothing.

### What must change

Add a new function `parse_wiki_upgrade_section` in `spring_boot.py`. This function:

1. Detects the "Upgrading from" H2 section in the `html_to_text` output using the regex
   `^##\s+Upgrading from`.
2. Collects all subsection headings (H3, `###`) and the prose text that follows each one,
   until the next H2 section.
3. For each subsection, produces one `DocumentedChange` whose statement is the H3 title
   followed by the prose body (space-joined, whitespace-collapsed), with the H3 heading
   used as the section hint for `classify_statement`.

```python
import re
from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.extractors.parsing import classify_statement

_UPGRADE_H2_RE = re.compile(r"^##\s+Upgrading from", re.IGNORECASE | re.MULTILINE)
_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)


def parse_wiki_upgrade_section(
    wiki_text: str, source_url: str
) -> list[DocumentedChange]:
    """
    Extract DocumentedChange entries from the 'Upgrading from' prose section of a
    Spring Boot wiki release notes page (already converted to plain text via html_to_text).

    Each H3 subsection (e.g. 'Actuator heapdump Endpoint') becomes one entry whose
    statement is 'Title: {h3}. {prose}' and whose type/confidence are determined by
    classify_statement with the H2 section hint 'Upgrading from Spring Boot'.
    """
    upgrade_match = _UPGRADE_H2_RE.search(wiki_text)
    if not upgrade_match:
        return []

    # Clip to the Upgrading section: from H2 start to next H2 (or EOF)
    section_start = upgrade_match.end()
    next_h2 = _H2_RE.search(wiki_text, section_start)
    section_text = (
        wiki_text[section_start:next_h2.start()]
        if next_h2 else wiki_text[section_start:]
    )

    changes: list[DocumentedChange] = []
    h3_matches = list(_H3_RE.finditer(section_text))

    for idx, h3_match in enumerate(h3_matches):
        heading = h3_match.group(1).strip()
        body_start = h3_match.end()
        body_end = h3_matches[idx + 1].start() if idx + 1 < len(h3_matches) else len(section_text)
        prose_lines = [
            line.strip()
            for line in section_text[body_start:body_end].splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        prose = " ".join(prose_lines)
        if not prose:
            continue
        statement = f"{heading}: {prose}"
        change_type, confidence = classify_statement("Upgrading from Spring Boot", statement)
        changes.append(
            DocumentedChange(
                type=change_type,
                confidence=confidence,
                source_url=source_url,
                statement=statement,
            )
        )
    return changes
```

### Integration point

`parse_wiki_upgrade_section` is called in `_fetch_wiki_release_notes` **in addition to**
`html_to_text`. The prose entries are returned as a separate list, combined with the
bullet-parsed entries in `extract()`:

```python
# In extract():
source_url, body = await self.fetch_github_release(
    "spring-projects/spring-boot", to_version, tag_candidates
)
wiki_text, wiki_prose_changes = await self._fetch_wiki_release_notes(to_version)
if wiki_text:
    body = body + "\n\n" + wiki_text
changes = self.parse_github_release_text(body, source_url)
changes = changes + wiki_prose_changes   # append prose-parsed entries
```

To support this, `_fetch_wiki_release_notes` changes its return type from `str` to
`tuple[str, list[DocumentedChange]]`:

```python
async def _fetch_wiki_release_notes(
    self, to_version: str
) -> tuple[str, list[DocumentedChange]]:
    """
    Returns (wiki_text_for_bullet_parsing, prose_upgrade_changes).
    Both values are empty/[] on any fetch failure. Never raises.
    """
    ...
    wiki_text = _strip_dependency_upgrades(html_to_text(str(wiki_body)))
    wiki_url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
    prose_changes = parse_wiki_upgrade_section(wiki_text, wiki_url)
    return wiki_text, prose_changes
```

### Expected effect

The "Upgrading from" section for 3.5.0 contains 15 H3 subsections, each becoming one
`DocumentedChange`. All 15 describe breaking behavioural changes or mandatory migration steps.
These are the entries that should be classified as `breaking` or `mandatory_migration` — a
type that was previously completely absent from Spring Boot extraction output.

---

## SW-4 — Use wiki URL as `source_url` for wiki-sourced entries

### Problem

All entries produced from wiki content — both bullet-parsed and prose-parsed — are currently
tagged with the GitHub release tag URL (e.g. `releases/tag/v3.5.0`). This is incorrect: the
content comes from the wiki page. Downstream consumers (filter LLM, entity LLM, graph populator)
cannot distinguish GitHub release entries from wiki entries.

### What must change

Bullet-parsed wiki entries: `parse_github_release_text(body, source_url)` passes the GitHub
release URL as `source_url` for all entries including the appended wiki text. To avoid this, the
wiki text must be parsed **separately** with the wiki URL, and results merged:

```python
# In extract() — REQUIRED
source_url, body = await self.fetch_github_release(
    "spring-projects/spring-boot", to_version, tag_candidates
)
wiki_text, wiki_prose_changes = await self._fetch_wiki_release_notes(to_version)

# Parse GitHub release body with its own URL
changes = self.parse_github_release_text(body, source_url)

# Parse wiki bullet content with wiki URL
if wiki_text:
    wiki_url = _WIKI_URL_TEMPLATE.format(
        major=parse_version(to_version)[0],
        minor=parse_version(to_version)[1],
    )
    wiki_bullet_changes = self.parse_github_release_text(wiki_text, wiki_url)
    changes = changes + wiki_bullet_changes + wiki_prose_changes
```

### Expected effect

- GitHub release entries: `source_url = https://github.com/spring-projects/spring-boot/releases/tag/v3.5.0`
- Wiki bullet entries: `source_url = https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes`
- Wiki prose entries: `source_url = https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes`

The Markdown output table's `Source` column becomes accurate and filterable.

---

## Combined `extract()` implementation

After all four fixes, the `extract` method reads as follows:

```python
async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
    tag_candidates = [f"v{to_version}", to_version]
    source_url, body = await self.fetch_github_release(
        "spring-projects/spring-boot", to_version, tag_candidates
    )
    wiki_text, wiki_prose_changes = await self._fetch_wiki_release_notes(to_version)

    # GitHub release body → parse with release URL
    changes = self.parse_github_release_text(body, source_url)

    # Wiki body → parse bullets with wiki URL; prose changes already carry wiki URL
    if wiki_text:
        major, minor, _, _ = parse_version(to_version)
        wiki_url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
        wiki_bullet_changes = self.parse_github_release_text(wiki_text, wiki_url)
        changes = changes + wiki_bullet_changes + wiki_prose_changes

    if not changes:
        raise RuntimeError(
            f"Spring Boot: no changes parsed for hop {from_version} → {to_version} "
            f"from {source_url}"
        )
    return ExtractionResult(changes=changes, metadata={})
```

---

## Expected outcome

For a Spring Boot 3.5.0 extraction:

| Source | Changes | Notes |
|--------|--------:|-------|
| GitHub release body | 32 | Unchanged — same as before |
| Wiki bullet items | ~83 | Down from ~550; filtered, substantive |
| Wiki prose items ("Upgrading from") | ~15 | New — were completely absent |
| **Total** | **~130** | vs. current ~582 (mostly noise) |

Breaking-change and mandatory-migration typed entries will appear for the first time in
Spring Boot extraction output. Source traceability will be correct for all entries.

---

## Out of scope

- No changes to `base.py`, `parsing.py`, `filters.py`, `wildfly.py`, or any other extractor.
- No changes to the LLM filter prompt or entity prompt.
- No changes to the graph schema or populator.
- No changes to `ExtractionResult` or `DocumentedChange` type signatures.
  (`metadata` on prose changes is `None`, consistent with existing entries that have no metadata.)
- Angular, WildFly, Hibernate, and other extractor improvements are tracked separately in
  `specs/003b-extractors-improvements/`.

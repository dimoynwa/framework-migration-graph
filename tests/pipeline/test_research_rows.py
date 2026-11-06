"""Filtered-row parsing and the research appendix. No network."""

from __future__ import annotations

from migration_oracle.pipeline.extractor import EXTRACTION_PROMPT
from migration_oracle.pipeline.filters import FILTER_PROMPT
from migration_oracle.pipeline.research.markdown import (
    attach_raw_context,
    build_extraction_input,
    parse_filtered_markdown,
)
from migration_oracle.pipeline.research.schema import ResearchDossier

WITH_SOURCES = """\
## 🔴 Breaking Changes

| # | JIRA | Title | Impact | Sources |
| --- | --- | --- | --- | --- |
| 1 | WFLY-1, WFLY-2 | Remove sun.jdk | The module is no longer implicit. | https://example.com/a, https://example.com/b |
| 2 | N/A | Rename timeout | The default timeout changed. | N/A |

## Summary by Priority

| Priority Level | Count | Description |
| --- | --- | --- |
| Breaking | 2 | Must fix. |
"""

WITHOUT_SOURCES = """\
## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 7 | WFLY-1, WFLY-2 | Remove sun.jdk | The module is no longer implicit. |
"""

RAW = """\
# Spring Boot — documented changes (extract-only)

- **Framework key:** `spring-boot`
- **Resolved range:** `3.5.0` → `3.5.1`

---

## `3.5.0` → `3.5.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| breaking | confirmed | https://example.com/a | Enriched statement for sun.jdk |
| breaking | confirmed | https://example.com/other | Unrelated row |
"""


def test_filter_prompt_keeps_sources_column() -> None:
    assert "| # | JIRA | Title | Impact | Sources |" in FILTER_PROMPT
    assert "Do not include the original" not in FILTER_PROMPT
    assert "Comma-separated URLs that identify this specific change" in FILTER_PROMPT
    assert "Do not list a release-notes page" in FILTER_PROMPT


def test_extraction_prompt_uses_research_and_sources() -> None:
    assert "INTERNET RESEARCH (mandatory)" not in EXTRACTION_PROMPT
    assert "Research blocks are NOT rows" in EXTRACTION_PROMPT
    assert "source text" not in EXTRACTION_PROMPT
    assert "first URL in the row's Sources column" in EXTRACTION_PROMPT


def test_parse_sources_and_legacy_tables() -> None:
    rows = parse_filtered_markdown(WITH_SOURCES)
    assert len(rows) == 2
    assert rows[0].section == "🔴 Breaking Changes"
    assert rows[0].index == 1
    assert rows[0].jira_keys == ("WFLY-1", "WFLY-2")
    assert rows[0].title == "Remove sun.jdk"
    assert rows[0].sources == ("https://example.com/a", "https://example.com/b")
    assert rows[1].jira_keys == ()
    assert rows[1].sources == ()

    legacy = parse_filtered_markdown(WITHOUT_SOURCES)
    assert len(legacy) == 1
    assert legacy[0].sources == ()
    assert legacy[0].index == 7
    assert legacy[0].title == rows[0].title
    assert legacy[0].row_key != rows[0].row_key


def test_row_key_ignores_index_and_tracks_sources() -> None:
    original = parse_filtered_markdown(WITH_SOURCES)[0]
    reordered = parse_filtered_markdown(WITH_SOURCES.replace("| 1 |", "| 9 |", 1))[0]
    assert reordered.index == 9
    assert reordered.row_key == original.row_key

    changed = parse_filtered_markdown(
        WITH_SOURCES.replace("https://example.com/b", "https://example.com/c")
    )[0]
    assert changed.row_key != original.row_key


def test_raw_context_matches_source_urls() -> None:
    rows = attach_raw_context(parse_filtered_markdown(WITH_SOURCES), RAW)
    assert rows[0].raw_statements == ("Enriched statement for sun.jdk",)
    assert rows[1].raw_statements == ()


def test_error_dossier_leaves_filtered_markdown_unchanged() -> None:
    filtered = WITH_SOURCES
    rows = parse_filtered_markdown(filtered)
    error = ResearchDossier(
        row_key=rows[0].row_key,
        status="error",
        text="should not appear",
        sources=["https://example.com/a"],
    )
    ok = ResearchDossier(
        row_key=rows[1].row_key,
        status="ok",
        text="Timeout rename needs no user action. Affects apps that set `timeout`.",
        sources=["https://example.com/t"],
        model="fake",
        prompt_version=1,
    )
    built = build_extraction_input(filtered, rows, [error, ok])
    assert "should not appear" not in built.document
    assert "### 🔴 Breaking Changes #1 — Remove sun.jdk" not in built.document
    assert "### 🔴 Breaking Changes #2 — Rename timeout" in built.document
    assert "needs no user action" in built.document
    assert "Fetched sources:\n- https://example.com/t" in built.document
    assert filtered in built.document
    assert built.has_appendix is True

    untouched = build_extraction_input(filtered, rows, [])
    assert untouched.document == filtered
    assert untouched.has_appendix is False

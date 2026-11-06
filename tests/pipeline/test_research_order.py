"""Research before the filter LLM: kept rows, filter research blocks, merged dossiers."""

from __future__ import annotations

from migration_oracle.pipeline.research.markdown import (
    FilteredRow,
    build_filter_research,
    dossiers_for_filtered_rows,
    parse_filtered_markdown,
)
from migration_oracle.pipeline.research.rows import kept_rows
from migration_oracle.pipeline.research.schema import ResearchDossier
from migration_oracle.pipeline.triage.markdown import FILTER_TABLE_HEADER, FILTER_TABLE_SEPARATOR

ISSUE_A = "https://github.com/spring-projects/spring-boot/issues/38870"
ISSUE_B = "https://github.com/spring-projects/spring-boot/issues/38862"
WIKI = "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes"

FILTER_INPUT = "\n".join(
    [
        "# Spring Boot — documented changes (extract-only)",
        "",
        "- **Resolved range:** `3.2.0` → `3.2.1`",
        "",
        FILTER_TABLE_HEADER,
        FILTER_TABLE_SEPARATOR,
        f"| dependency_upgrade | inferred | {ISSUE_A} | Title: Upgrade to Hibernate 6.4.1.Final "
        f"Issue: Supersedes #38523 Release: upgrades [#38870]({ISSUE_A}) | dependency_upgrade | 1.83 |",
        f"| behavioral | inferred | {WIKI} | Title: Nested jar duplicates META-INF Issue: see "
        f"[#38862]({ISSUE_B}) ``` code ``` | behavior_change | 1.20 |",
        "| breaking | confirmed | https://issues.redhat.com/browse/WFLY-17948 | Remove legacy module | breaking | 3.00 |",
        "",
    ]
)


def _ok(row_key: str, url: str, text: str) -> ResearchDossier:
    return ResearchDossier(row_key=row_key, status="ok", text=f"About {text}.", sources=[url])


def test_kept_rows_extract_title_sources_and_jira() -> None:
    rows = {row.title: row for row in kept_rows(FILTER_INPUT)}
    hibernate = rows["Upgrade to Hibernate 6.4.1.Final"]
    assert hibernate.sources == (ISSUE_A,)
    assert hibernate.section == "🟠 Mandatory Migrations — Major Component Upgrades"
    assert "Title:" not in hibernate.impact
    nested = rows["Nested jar duplicates META-INF"]
    assert nested.sources == (ISSUE_B,)  # the shared wiki Source is replaced
    assert "```" not in nested.impact
    legacy = rows["Remove legacy module"]
    assert legacy.jira_keys == ("WFLY-17948",)
    assert legacy.section == "🔴 Breaking Changes"


def test_filter_research_blocks_follow_the_chunk() -> None:
    rows = kept_rows(FILTER_INPUT)
    dossiers = [_ok(row.row_key, row.sources[0], f"fact {i}") for i, row in enumerate(rows)]
    dossiers[2] = dossiers[2].model_copy(update={"status": "not_found", "text": ""})
    research = build_filter_research(rows, dossiers)
    full = research.appendix()
    assert full.startswith("## Research")
    assert f"Row sources: {ISSUE_A}" in full and f"Row sources: {ISSUE_B}" in full
    assert "WFLY-17948" not in full  # not_found dossiers are omitted
    only_a = research.appendix(f"| x | y | {ISSUE_A} | statement |")
    assert ISSUE_A in only_a and ISSUE_B not in only_a
    assert research.document("| no | matching | rows |") == "| no | matching | rows |"


def test_dossiers_are_merged_per_document_row_by_sources() -> None:
    research_rows = [
        FilteredRow("s", 1, (), "A", "a", (ISSUE_A,)),
        FilteredRow("s", 2, (), "B", "b", (ISSUE_B,)),
        FilteredRow("s", 3, (), "C", "c", ("https://example.com/c",)),
    ]
    dossiers = [
        _ok("ka", ISSUE_A, "fact A"),
        _ok("kb", ISSUE_B, "fact B"),
        _ok("kc", "https://example.com/c", "fact C"),
    ]
    document = (
        "## 🟡 Behavioral Changes\n\n"
        "| # | JIRA | Title | Impact | Sources |\n| --- | --- | --- | --- | --- |\n"
        f"| 1 | N/A | Consolidated | Both. | {ISSUE_A}, {ISSUE_B} |\n"
        "| 2 | N/A | Unrelated | None. | https://example.com/none |\n"
    )
    filtered_rows = parse_filtered_markdown(document)
    merged = dossiers_for_filtered_rows(filtered_rows, research_rows, dossiers)
    assert merged[0].status == "ok"
    assert merged[0].text == "About fact A.\n\nAbout fact B."
    assert merged[0].sources == [ISSUE_A, ISSUE_B]
    assert merged[0].row_key == filtered_rows[0].row_key
    assert merged[1].status == "not_found"

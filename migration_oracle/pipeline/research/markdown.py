"""Filtered-Markdown rows, row keys, and the entity-step research appendix."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from migration_oracle.pipeline.research.schema import ResearchDossier, normalize_url
from migration_oracle.pipeline.triage.markdown import parse_raw_markdown

SHARED_URL_MAX_ROWS = 3
RAW_CONTEXT_MAX_CHARS = 8000
_URL_RE = re.compile(r"https?://[^\s<>()\[\]|\"']+")


@dataclass(frozen=True)
class FilteredRow:
    section: str
    index: int
    jira_keys: tuple[str, ...]
    title: str
    impact: str
    sources: tuple[str, ...]
    raw_statements: tuple[str, ...] = field(default=())

    @property
    def row_key(self) -> str:
        """Stable identity. The ``#`` column is not part of the key."""
        material = "\n".join(
            [
                self.section,
                self.title,
                "\n".join(sorted(self.jira_keys)),
                "\n".join(sorted(self.sources)),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExtractionInput:
    """What the entity LLM receives. No appendix means the filtered bytes."""

    document: str
    has_appendix: bool
    section_documents: tuple[str, ...]


def parse_filtered_markdown(markdown: str) -> list[FilteredRow]:
    """Read filter-stage tables. A file without ``Sources`` yields empty sources."""
    rows: list[FilteredRow] = []
    section = ""
    header: list[str] | None = None
    fallback_index = 0
    for line in markdown.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            header = None
            fallback_index = 0
            continue
        if not line.startswith("|"):
            continue
        cells = _split_cells(line)
        if not cells or _is_separator(cells):
            continue
        if _looks_like_header(cells):
            header = [cell.strip().lower() for cell in cells]
            continue
        if header is None or not section:
            continue
        title_at = _column(header, "title")
        impact_at = _column(header, "impact")
        if title_at is None or impact_at is None:
            continue
        if title_at >= len(cells) or impact_at >= len(cells):
            continue
        number_at = _column(header, "#")
        fallback_index += 1
        index = fallback_index
        if number_at is not None and number_at < len(cells):
            try:
                index = int(cells[number_at])
            except ValueError:
                index = fallback_index
        jira_at = _column(header, "jira")
        sources_at = _column(header, "sources")
        jira_cell = cells[jira_at] if jira_at is not None and jira_at < len(cells) else ""
        sources_cell = (
            cells[sources_at] if sources_at is not None and sources_at < len(cells) else ""
        )
        rows.append(
            FilteredRow(
                section=section,
                index=index,
                jira_keys=tuple(_jira_keys(jira_cell)),
                title=cells[title_at].strip(),
                impact=cells[impact_at].strip(),
                sources=tuple(_sources(sources_cell)),
            )
        )
    return rows


def attach_raw_context(
    rows: list[FilteredRow],
    raw_markdown: str,
    *,
    shared_url_max_rows: int = SHARED_URL_MAX_ROWS,
    max_chars: int = RAW_CONTEXT_MAX_CHARS,
) -> list[FilteredRow]:
    """Attach the enriched raw statements behind each row's Sources.

    A raw row is indexed by its Source URL and by every URL in its statement
    (issue, pull request, commit, JIRA links). Many raw rows share one Source
    (a release-notes wiki page, a release tag, ``CHANGELOG.md``), so a URL that
    identifies more than ``shared_url_max_rows`` raw rows is not used for
    matching. Statements are de-duplicated and capped at ``max_chars``.
    """
    if not raw_markdown.strip():
        return list(rows)
    by_url: dict[str, list[str]] = {}
    for raw in parse_raw_markdown(raw_markdown).rows:
        keys = {normalize_url(raw.source_url)}
        keys.update(normalize_url(url) for url in _URL_RE.findall(raw.statement))
        for key in keys:
            if key:
                by_url.setdefault(key, []).append(raw.statement)
    attached: list[FilteredRow] = []
    for row in rows:
        statements: list[str] = []
        seen: set[str] = set()
        budget = max_chars
        for source in row.sources:
            matches = by_url.get(normalize_url(source), [])
            if len(matches) > shared_url_max_rows:
                continue
            for statement in matches:
                if statement in seen or len(statement) > budget:
                    continue
                seen.add(statement)
                statements.append(statement)
                budget -= len(statement)
        attached.append(
            FilteredRow(
                section=row.section,
                index=row.index,
                jira_keys=row.jira_keys,
                title=row.title,
                impact=row.impact,
                sources=row.sources,
                raw_statements=tuple(statements),
            )
        )
    return attached


def render_research_request(row: FilteredRow, framework: str, hop: tuple[str, str]) -> str:
    sources = ", ".join(row.sources) if row.sources else "N/A"
    jira = ", ".join(row.jira_keys) if row.jira_keys else "N/A"
    lines = [
        f"Framework: {framework}",
        f"Hop: {hop[0]} → {hop[1]}",
        f"Target version: {hop[1]}",
        f"Version lines: {', '.join(version_lines(hop))}",
        f"Section hint (from triage): {row.section}",
        f"Row: {row.index}",
        f"JIRA: {jira}",
        f"Title: {row.title}",
        f"Summary: {row.impact}",
        f"Sources: {sources}",
    ]
    if row.raw_statements:
        lines.append("Raw statements:")
        lines.extend(f"- {statement}" for statement in row.raw_statements)
    else:
        lines.append(
            "Raw statements: none matched. Fall back to the JIRA keys and the title."
        )
    return "\n".join(lines)


def version_lines(hop: tuple[str, str]) -> list[str]:
    """major.minor lines from the hop start to its target, e.g. 3.5.0→3.5.1 → ["3.5"]."""
    start = _major_minor(hop[0])
    end = _major_minor(hop[1])
    if start is None or end is None:
        return [hop[1]]
    if start == end:
        return [f"{end[0]}.{end[1]}"]
    if start[0] == end[0] and start[1] < end[1] and end[1] - start[1] <= 10:
        return [f"{end[0]}.{minor}" for minor in range(start[1], end[1] + 1)]
    return [f"{start[0]}.{start[1]}", f"{end[0]}.{end[1]}"]


def _major_minor(version: str) -> tuple[int, int] | None:
    match = re.match(r"^v?(\d+)\.(\d+)", version.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class FilterResearch:
    """Research blocks for the filter LLM, one per researched kept row.

    The filter input is the kept-row table. Each block is tied to its row by the
    row's Sources, so a chunk of the table gets only the blocks of its rows.
    """

    blocks: tuple[tuple[tuple[str, ...], str], ...]

    @property
    def empty(self) -> bool:
        return not self.blocks

    def appendix(self, table: str | None = None) -> str:
        """``## Research`` section for ``table`` (all blocks when ``table`` is None)."""
        chosen = [
            block
            for sources, block in self.blocks
            if table is None or any(source in table for source in sources)
        ]
        if not chosen:
            return ""
        return "## Research\n\n" + "\n\n".join(chosen) + "\n"

    def document(self, table: str) -> str:
        """``table`` followed by the research appendix for its rows."""
        appendix = self.appendix(table)
        if not appendix:
            return table
        separator = "\n" if table.endswith("\n") else "\n\n"
        return table + separator + appendix


def build_filter_research(
    rows: list[FilteredRow], dossiers: list[ResearchDossier]
) -> FilterResearch:
    """Blocks for ``ok`` dossiers, headed by the kept row's Title and Sources."""
    blocks: list[tuple[tuple[str, ...], str]] = []
    for row, dossier in zip(rows, dossiers):
        if dossier.status != "ok" or not row.sources:
            continue
        lines = [
            f"### {row.title}",
            f"Row sources: {', '.join(row.sources)}",
            "",
            *_body_lines(dossier),
        ]
        blocks.append((row.sources, "\n".join(lines).strip()))
    return FilterResearch(blocks=tuple(blocks))


def dossiers_for_filtered_rows(
    filtered_rows: list[FilteredRow],
    research_rows: list[FilteredRow],
    dossiers: list[ResearchDossier],
) -> list[ResearchDossier]:
    """Merge the dossiers of the kept rows consolidated into each filtered row.

    A kept row belongs to a filtered row when they share a Sources URL. The
    merged dossier is ``ok`` when any member is, with all members' descriptions
    and sources.
    """
    by_url: dict[str, list[ResearchDossier]] = {}
    for row, dossier in zip(research_rows, dossiers):
        if dossier.status != "ok":
            continue
        for source in row.sources:
            by_url.setdefault(normalize_url(source), []).append(dossier)
    merged: list[ResearchDossier] = []
    for row in filtered_rows:
        members: list[ResearchDossier] = []
        for source in row.sources:
            for dossier in by_url.get(normalize_url(source), []):
                if dossier not in members:
                    members.append(dossier)
        merged.append(_merge(row, members))
    return merged


def _merge(row: FilteredRow, members: list[ResearchDossier]) -> ResearchDossier:
    if not members:
        return ResearchDossier(row_key=row.row_key, status="not_found")
    if len(members) == 1:
        return members[0].model_copy(update={"row_key": row.row_key})
    sources: list[str] = []
    for member in members:
        sources.extend(url for url in member.sources if url not in sources)
    return ResearchDossier(
        row_key=row.row_key,
        status="ok",
        text="\n\n".join(member.text.strip() for member in members if member.text.strip()),
        sources=sources,
        model=members[0].model,
        prompt_version=members[0].prompt_version,
    )


def _body_lines(dossier: ResearchDossier) -> list[str]:
    lines = [dossier.text.strip()]
    if dossier.sources:
        lines.append("")
        lines.append("Fetched sources:")
        lines.extend(f"- {url}" for url in dossier.sources)
    return lines


def build_extraction_input(
    filtered_md: str,
    rows: list[FilteredRow],
    dossiers: list[ResearchDossier],
) -> ExtractionInput:
    """Append a Research section for ok dossiers. Otherwise return ``filtered_md``."""
    blocks_by_section: dict[str, list[str]] = {}
    ordered: list[str] = []
    for row, dossier in zip(rows, dossiers):
        if dossier.status != "ok":
            continue
        block = _render_block(row, dossier)
        ordered.append(block)
        blocks_by_section.setdefault(row.section, []).append(block)
    sections = tuple(_section_documents(filtered_md, blocks_by_section))
    if not ordered:
        return ExtractionInput(
            document=filtered_md,
            has_appendix=False,
            section_documents=sections,
        )
    appendix = "## Research\n\n" + "\n\n".join(ordered) + "\n"
    if filtered_md.endswith("\n"):
        document = filtered_md + "\n" + appendix
    else:
        document = filtered_md + "\n\n" + appendix
    return ExtractionInput(
        document=document,
        has_appendix=True,
        section_documents=sections,
    )


def _render_block(row: FilteredRow, dossier: ResearchDossier) -> str:
    lines = [
        f"### {row.section} #{row.index} — {row.title}",
        "",
        *_body_lines(dossier),
    ]
    return "\n".join(lines).strip()


def _section_documents(
    filtered_md: str, blocks_by_section: dict[str, list[str]]
) -> list[str]:
    """One document per change section.

    Sections without a ``Title``/``Impact`` table (``Summary by Priority``,
    ``Most Critical Items``) only restate other rows, so they are not sent on
    their own: the entity LLM would turn their bullets into duplicate entities.
    """
    documents: list[str] = []
    for heading, body in _split_sections(filtered_md):
        if not _has_change_table(body):
            continue
        extra = blocks_by_section.get(heading, [])
        if not extra:
            documents.append(body)
            continue
        research = "## Research\n\n" + "\n\n".join(extra) + "\n"
        if body.endswith("\n"):
            documents.append(body + "\n" + research)
        else:
            documents.append(body + "\n\n" + research)
    return documents


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = ""
    chunk: list[str] = []
    for line in markdown.splitlines(keepends=True):
        if line.startswith("## "):
            if heading:
                sections.append((heading, "".join(chunk)))
            heading = line[3:].strip()
            chunk = [line if line.endswith("\n") else line + "\n"]
            continue
        if heading:
            chunk.append(line)
    if heading:
        sections.append((heading, "".join(chunk)))
    return sections


def _has_change_table(body: str) -> bool:
    for line in body.splitlines():
        if line.startswith("|") and _looks_like_header(_split_cells(line)):
            return True
    return False


def _split_cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(set(cell) <= set("-: ") and "-" in cell for cell in cells)


def _looks_like_header(cells: list[str]) -> bool:
    labels = {cell.strip().lower() for cell in cells}
    return "title" in labels and "impact" in labels


def _column(header: list[str], name: str) -> int | None:
    try:
        return header.index(name)
    except ValueError:
        return None


def _jira_keys(cell: str) -> list[str]:
    keys: list[str] = []
    for part in cell.split(","):
        key = part.strip()
        if key and key.upper() not in {"N/A", "NA", "NONE", "—", "-"}:
            keys.append(key)
    return keys


def _sources(cell: str) -> list[str]:
    sources: list[str] = []
    for part in cell.split(","):
        url = part.strip()
        if url and url.upper() not in {"N/A", "NA", "NONE", "—", "-"}:
            sources.append(url)
    return sources

"""Research rows built from the kept triage rows.

Research runs before the filter LLM, on every row nimble kept. Each kept row
becomes one :class:`FilteredRow`: ``Title`` from the ``Title:`` prefix, the
statement as ``impact``, ``Sources`` = the issue / PR / commit / JIRA links in
the statement (the row ``Source`` only when it has none), JIRA keys from
``/browse/`` URLs, and a section hint from the triage ``Category`` (or the raw
``Type`` when untriaged).
"""

from __future__ import annotations

import re

from migration_oracle.pipeline.research.markdown import FilteredRow

SECTION_BREAKING = "🔴 Breaking Changes"
SECTION_SECURITY = "🟠 Mandatory Migrations — Security & CVE Fixes"
SECTION_COMPONENT = "🟠 Mandatory Migrations — Major Component Upgrades"
SECTION_BEHAVIORAL = "🟡 Behavioral Changes"
SECTION_DEPRECATIONS = "🟡 Deprecations"
SECTION_NEW = "🔵 Notable New Capabilities"

# Triage category → section hint for the research request. The filter LLM
# chooses the final section. Low-confidence internal_fix / noise rows that
# triage kept go to Behavioral Changes (fail toward keeping).
CATEGORY_SECTIONS: dict[str, str] = {
    "breaking": SECTION_BREAKING,
    "security": SECTION_SECURITY,
    "dependency_upgrade": SECTION_COMPONENT,
    "behavior_change": SECTION_BEHAVIORAL,
    "config_change": SECTION_BEHAVIORAL,
    "deprecation": SECTION_DEPRECATIONS,
    "new_optional_feature": SECTION_NEW,
}

# Raw extractor ``Type`` → section, used when a row has no triage category.
TYPE_SECTIONS: dict[str, str] = {
    "breaking": SECTION_BREAKING,
    "deprecation": SECTION_DEPRECATIONS,
    "dependency_upgrade": SECTION_COMPONENT,
    "mandatory_migration": SECTION_COMPONENT,
    "behavioral": SECTION_BEHAVIORAL,
}

IMPACT_MAX_CHARS = 400
TITLE_MAX_CHARS = 120

_TITLE_RE = re.compile(r"^\s*Title:\s*(.+?)(?=\s+(?:Issue|Release|Body|Commit|PR):|$)")
_URL_RE = re.compile(r"https?://[^\s<>()\[\]|\"'`]+")
_SPECIFIC_URL_RE = re.compile(
    r"(github\.com/[^/]+/[^/]+/(?:issues|pull|commit)/[0-9a-f]+)"
    r"|(/browse/[A-Z][A-Z0-9]+-\d+)"
    r"|(issues\.redhat\.com/browse/)"
    r"|(atlassian\.net/browse/)",
    re.IGNORECASE,
)
_JIRA_KEY_RE = re.compile(r"/browse/([A-Z][A-Z0-9]+-\d+)")


def kept_rows(filter_md: str) -> list[FilteredRow]:
    """One research row per kept row of the filter input (triaged or plain table)."""
    rows: list[FilteredRow] = []
    for position, cells in enumerate(_rows(filter_md), start=1):
        row_type, source, statement = cells[0], cells[2], cells[3]
        category = cells[4] if len(cells) > 4 else ""
        sources = _sources(statement, source)
        rows.append(
            FilteredRow(
                section=_section(category, row_type),
                index=position,
                jira_keys=tuple(_jira_keys([source, *sources, statement])),
                title=_title(statement),
                impact=_impact(statement),
                sources=tuple(sources),
            )
        )
    return rows


def _rows(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0].lower() == "type" or set(cells[0]) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def _section(category: str, row_type: str) -> str:
    key = category.strip().lower()
    if key in CATEGORY_SECTIONS:
        return CATEGORY_SECTIONS[key]
    return TYPE_SECTIONS.get(row_type.strip().lower(), SECTION_BEHAVIORAL)


def _sources(statement: str, source: str) -> list[str]:
    """Specific issue / PR / commit / JIRA links first; the row Source otherwise."""
    specific: list[str] = []
    for url in [source, *_URL_RE.findall(statement)]:
        cleaned = url.rstrip(".,;:")
        if _SPECIFIC_URL_RE.search(cleaned) and cleaned not in specific:
            specific.append(cleaned)
    if specific:
        return specific
    return [source] if source.startswith("http") else []


def _jira_keys(texts: list[str]) -> list[str]:
    keys: list[str] = []
    for text in texts:
        for key in _JIRA_KEY_RE.findall(text):
            if key not in keys:
                keys.append(key)
    return keys


def _title(statement: str) -> str:
    match = _TITLE_RE.match(statement)
    text = match.group(1) if match else _strip_links(statement)
    return _clip(text.strip(), TITLE_MAX_CHARS)


def _impact(statement: str) -> str:
    """The statement without its ``Title:`` prefix, links reduced to their text."""
    match = _TITLE_RE.match(statement)
    body = statement[match.end():] if match else statement
    body = _strip_links(body).strip() or _strip_links(statement).strip()
    # Code fences inside a table cell break Markdown rendering.
    body = body.replace("```", " ")
    return _clip(body, IMPACT_MAX_CHARS)


def _strip_links(text: str) -> str:
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"

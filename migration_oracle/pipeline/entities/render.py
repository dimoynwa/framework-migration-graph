"""Render ``runs/nodes/*_filtered.md`` from dossier entities.

One section per ``source_section``, in the filter document's order. No summary
sections. ``Impact`` is the first sentence of ``reason``. ``Sources`` are the
member rows' sources.
"""

from __future__ import annotations

import re

from migration_oracle.models.entities import MigrationEntity
from migration_oracle.pipeline.entities.clusters import Cluster
from migration_oracle.pipeline.research.rows import (
    SECTION_BEHAVIORAL,
    SECTION_BREAKING,
    SECTION_COMPONENT,
    SECTION_DEPRECATIONS,
    SECTION_NEW,
    SECTION_SECURITY,
)

SECTION_SECURITY_CONFIG = "🟠 Mandatory Migrations — Security Configuration"

_SECTIONS: tuple[tuple[str, str], ...] = (
    ("breaking_change", SECTION_BREAKING),
    ("security_fix", SECTION_SECURITY),
    ("component_upgrade", SECTION_COMPONENT),
    ("security_config", SECTION_SECURITY_CONFIG),
    ("behavioral", SECTION_BEHAVIORAL),
    ("deprecation", SECTION_DEPRECATIONS),
    ("new_capability", SECTION_NEW),
)


def first_sentence(text: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return ""
    match = re.search(r"[.!?]", compact)
    if not match:
        return compact
    return compact[: match.end()]


def render_filtered_markdown(
    items: list[tuple[MigrationEntity, Cluster]],
    *,
    framework: str,
    hop: tuple[str, str],
) -> str:
    grouped: dict[str, list[tuple[MigrationEntity, Cluster]]] = {
        key: [] for key, _heading in _SECTIONS
    }
    for entity, cluster in items:
        grouped.setdefault(entity.source_section, []).append((entity, cluster))
    lines = [
        f"# {framework} {hop[0]} → {hop[1]} — Filtered Migration Report",
        "",
        f"- **Framework:** {framework}",
        f"- **Range:** {hop[0]} → {hop[1]}",
        "- **Entity source:** dossier",
        "",
        "---",
        "",
    ]
    for key, heading in _SECTIONS:
        section_items = grouped.get(key) or []
        if not section_items:
            continue
        lines.extend(
            [
                f"## {heading}",
                "",
                "| # | JIRA | Title | Impact | Sources |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for number, (entity, cluster) in enumerate(section_items, start=1):
            jira = ", ".join(entity.jira_keys) if entity.jira_keys else "N/A"
            sources = _sources(cluster)
            lines.append(
                "| {number} | {jira} | {title} | {impact} | {sources} |".format(
                    number=number,
                    jira=_cell(jira),
                    title=_cell(entity.title),
                    impact=_cell(first_sentence(entity.reason)),
                    sources=_cell(sources),
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _sources(cluster: Cluster) -> str:
    seen: list[str] = []
    for member in cluster.members:
        for source in member.row.sources:
            if source and source not in seen:
                seen.append(source)
    return ", ".join(seen) if seen else "N/A"


def _cell(text: str) -> str:
    return " ".join((text or "").replace("|", " ").split())

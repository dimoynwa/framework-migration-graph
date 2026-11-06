"""Raw Markdown rendering, parsing, and the filter-input table derived from it."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from migration_oracle.models.entities import DocumentedChange


TRIAGE_TABLE_HEADER = (
    "| Type | Confidence | Source | Statement | Triage | Category | "
    "Cat. prob | P(action) | Impact | Triage source |"
)
TRIAGE_TABLE_SEPARATOR = (
    "|------|------------|--------|-----------|--------|----------|"
    "-----------|-----------|--------|---------------|"
)
PLAIN_TABLE_HEADER = "| Type | Confidence | Source | Statement |"
PLAIN_TABLE_SEPARATOR = "|------|------------|--------|-----------|"
FILTER_TABLE_HEADER = (
    "| Type | Confidence | Source | Statement | Category | Impact score |"
)
FILTER_TABLE_SEPARATOR = "|------|------------|--------|-----------|----------|--------------|"

_HOP_RE = re.compile(r"^## `([^`]+)` → `([^`]+)`\s*$")
_FRAMEWORK_KEY_RE = re.compile(r"^\- \*\*Framework key:\*\* `([^`]+)`\s*$")
_RANGE_RE = re.compile(
    r"^\- \*\*Resolved range:\*\* `([^`]+)` → `([^`]+)`\s*$"
)
_TITLE_RE = re.compile(r"^# (.+?) — documented changes")

# breaking+deprecation, behavior/config/security, dependency, everything else.
FILTER_GROUPS: list[tuple[str, frozenset[str] | None]] = [
    ("breaking", frozenset({"breaking", "deprecation"})),
    (
        "behavior",
        frozenset({"behavior_change", "config_change", "security"}),
    ),
    ("dependency", frozenset({"dependency_upgrade"})),
    ("rest", None),
]


@dataclass
class RawRow:
    type: str
    confidence: str
    source_url: str
    statement: str
    triage_decision: str | None = None
    triage_category: str | None = None
    triage_category_prob: str | None = None
    triage_action_prob: str | None = None
    triage_impact: str | None = None
    triage_source: str | None = None

    @property
    def triaged(self) -> bool:
        return self.triage_decision is not None


@dataclass
class ParsedRaw:
    title: str
    framework_key: str
    framework_display: str
    from_version: str
    to_version: str
    extra_lines: list[str] = field(default_factory=list)
    hops: list[tuple[str, str, list[RawRow]]] = field(default_factory=list)

    @property
    def rows(self) -> list[RawRow]:
        return [row for _hop_from, _hop_to, rows in self.hops for row in rows]

    @property
    def triaged(self) -> bool:
        return any(row.triaged for row in self.rows)


def has_triage_columns(markdown: str) -> bool:
    return TRIAGE_TABLE_HEADER in markdown


def sanitize_statement(statement: str) -> str:
    return statement.replace("|", " ").replace("\r", " ").replace("\n", " ")


def render_raw_markdown(
    *,
    framework_key: str,
    framework_display: str,
    from_version: str,
    to_version: str,
    hop_changes: list[tuple[str, str, list[DocumentedChange]]],
    metadata: dict | None = None,
    extra_lines: list[str] | None = None,
) -> str:
    """Render multi-hop raw Markdown. Triage columns appear only when rows were triaged."""
    from datetime import UTC, datetime

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    triaged = any(
        (change.metadata or {}).get("triage_decision")
        for _hop_from, _hop_to, changes in hop_changes
        for change in changes
    )
    lines = [
        f"# {framework_display} — documented changes (extract-only)",
        "",
        f"- **Framework key:** `{framework_key}`",
        f"- **Resolved range:** `{from_version}` → `{to_version}`",
        f"- **Generated (UTC):** {timestamp}",
    ]
    if triaged:
        kept, dropped, errors, model, version = _triage_counts(hop_changes)
        lines.append(
            f"- **Triage:** {model} · questions v{version} · "
            f"kept {kept} / dropped {dropped} / error {errors}"
        )
    lines.extend(["", "---", ""])
    if metadata:
        for key, value in metadata.items():
            if key in ("bom_diff", "blog_insights") and value:
                lines.append(f"- **{key}:** present in extraction metadata")
        lines.append("")
    elif extra_lines:
        lines.extend(extra_lines)
        if extra_lines[-1] != "":
            lines.append("")

    for hop_from, hop_to, changes in hop_changes:
        lines.extend([f"## `{hop_from}` → `{hop_to}`", ""])
        if triaged:
            lines.extend([TRIAGE_TABLE_HEADER, TRIAGE_TABLE_SEPARATOR])
        else:
            lines.extend([PLAIN_TABLE_HEADER, PLAIN_TABLE_SEPARATOR])
        for change in changes:
            lines.append(_format_row(change, triaged=triaged))
        lines.append("")

    return "\n".join(lines) + "\n"


def parse_raw_markdown(markdown: str) -> ParsedRaw:
    """Read a 4-column or 10-column raw file back into rows. Decisions round-trip."""
    lines = markdown.splitlines()
    title = ""
    framework_key = ""
    framework_display = ""
    from_version = ""
    to_version = ""
    for line in lines:
        title_match = _TITLE_RE.match(line)
        if title_match and not framework_display:
            framework_display = title_match.group(1).strip()
            title = line
        key_match = _FRAMEWORK_KEY_RE.match(line)
        if key_match:
            framework_key = key_match.group(1)
        range_match = _RANGE_RE.match(line)
        if range_match:
            from_version, to_version = range_match.group(1), range_match.group(2)

    extra: list[str] = []
    hops: list[tuple[str, str, list[RawRow]]] = []
    current: tuple[str, str, list[RawRow]] | None = None
    seen_rule = False
    in_header = True
    for line in lines:
        if line.startswith("## `"):
            in_header = False
            hop_match = _HOP_RE.match(line)
            if hop_match is None:
                continue
            current = (hop_match.group(1), hop_match.group(2), [])
            hops.append(current)
            continue
        if in_header:
            if seen_rule and line.startswith("- **") and not line.startswith("- **Triage:**"):
                extra.append(line)
            if line.strip() == "---":
                seen_rule = True
            continue
        if current is None or not line.startswith("|"):
            continue
        if line.startswith("|---") or line.startswith("| Type") or line.startswith("|------"):
            continue
        cells = _split_cells(line)
        if len(cells) < 4:
            continue
        row = RawRow(
            type=cells[0],
            confidence=cells[1],
            source_url=cells[2],
            statement=cells[3],
        )
        if len(cells) >= 10:
            row.triage_decision = _blank(cells[4])
            row.triage_category = _blank(cells[5])
            row.triage_category_prob = _blank(cells[6])
            row.triage_action_prob = _blank(cells[7])
            row.triage_impact = _blank(cells[8])
            row.triage_source = _blank(cells[9])
        current[2].append(row)

    return ParsedRaw(
        title=title,
        framework_key=framework_key,
        framework_display=framework_display,
        from_version=from_version,
        to_version=to_version,
        extra_lines=extra,
        hops=hops,
    )


def rows_to_changes(
    hops: list[tuple[str, str, list[RawRow]]],
) -> list[tuple[str, str, list[DocumentedChange]]]:
    """Rebuild extractor hops from parsed rows, carrying triage fields in metadata."""
    rendered: list[tuple[str, str, list[DocumentedChange]]] = []
    for hop_from, hop_to, rows in hops:
        changes: list[DocumentedChange] = []
        for row in rows:
            metadata = None
            if row.triage_decision:
                metadata = {
                    "triage_decision": row.triage_decision,
                    "triage_source": row.triage_source,
                    "triage_category": _none_if_dash(row.triage_category),
                    "triage_category_prob": _float_or_none(row.triage_category_prob),
                    "triage_action_prob": _float_or_none(row.triage_action_prob),
                    "triage_impact_score": _float_or_none(row.triage_impact),
                }
            changes.append(
                DocumentedChange(
                    type=row.type,
                    confidence=row.confidence,
                    source_url=row.source_url,
                    statement=row.statement,
                    metadata=metadata,
                )
            )
        rendered.append((hop_from, hop_to, changes))
    return rendered


def build_filter_markdown(raw_markdown: str) -> str:
    """Filter input. Untiaged files are returned unchanged.

    Triaged files contribute only ``keep`` rows and the six columns
    ``Type | Confidence | Source | Statement | Category | Impact score``.
    ``Impact score`` is the triage impact score (0–3); the filter LLM writes its
    own text ``Impact`` column, so the input column has a distinct name.
    """
    if not has_triage_columns(raw_markdown):
        return raw_markdown
    parsed = parse_raw_markdown(raw_markdown)
    lines = [
        f"# {parsed.framework_display} — documented changes (extract-only)",
        "",
        f"- **Framework key:** `{parsed.framework_key}`",
        f"- **Resolved range:** `{parsed.from_version}` → `{parsed.to_version}`",
        "",
        "---",
        "",
    ]
    for hop_from, hop_to, rows in parsed.hops:
        kept = [row for row in rows if row.triage_decision != "drop"]
        if not kept:
            continue
        lines.extend(
            [
                f"## `{hop_from}` → `{hop_to}`",
                "",
                FILTER_TABLE_HEADER,
                FILTER_TABLE_SEPARATOR,
            ]
        )
        for row in kept:
            statement = sanitize_statement(row.statement)
            category = row.triage_category or "—"
            impact = row.triage_impact or "—"
            lines.append(
                f"| {row.type} | {row.confidence} | {row.source_url} | "
                f"{statement} | {category} | {impact} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def split_filter_groups(filter_markdown: str) -> list[str]:
    """Split a triaged filter table into the FR-6 category groups, skipping empty ones."""
    if FILTER_TABLE_HEADER not in filter_markdown:
        return [filter_markdown]
    parsed_rows = _filter_rows(filter_markdown)
    chunks: list[str] = []
    for _name, categories in FILTER_GROUPS:
        if categories is None:
            chosen = [
                row
                for row in parsed_rows
                if row[4] not in _named_categories()
            ]
        else:
            chosen = [row for row in parsed_rows if row[4] in categories]
        if not chosen:
            continue
        lines = [
            FILTER_TABLE_HEADER,
            FILTER_TABLE_SEPARATOR,
        ]
        for cells in chosen:
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        chunks.append("\n".join(lines))
    return chunks or [filter_markdown]


def _named_categories() -> set[str]:
    names: set[str] = set()
    for _label, categories in FILTER_GROUPS:
        if categories is not None:
            names.update(categories)
    return names


def _filter_rows(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Type"):
            continue
        cells = _split_cells(line)
        if len(cells) >= 6:
            rows.append(cells[:6])
    return rows


def _triage_counts(
    hop_changes: list[tuple[str, str, list[DocumentedChange]]],
) -> tuple[int, int, int, str, object]:
    kept = dropped = errors = 0
    model = "—"
    version: object = "—"
    for _hop_from, _hop_to, changes in hop_changes:
        for change in changes:
            meta = change.metadata or {}
            decision = meta.get("triage_decision")
            if decision == "drop":
                dropped += 1
            elif decision == "keep":
                kept += 1
            if meta.get("triage_source") == "error":
                errors += 1
            if meta.get("triage_model"):
                model = str(meta["triage_model"])
            if meta.get("triage_questions_version") is not None:
                version = meta["triage_questions_version"]
    return kept, dropped, errors, model, version


def _format_row(change: DocumentedChange, *, triaged: bool) -> str:
    statement = sanitize_statement(change.statement)
    if not triaged:
        return (
            f"| {change.type} | {change.confidence} | "
            f"{change.source_url} | {statement} |"
        )
    meta = change.metadata or {}
    return (
        f"| {change.type} | {change.confidence} | {change.source_url} | {statement} "
        f"| {_cell(meta.get('triage_decision'))} "
        f"| {_cell(meta.get('triage_category'))} "
        f"| {_num(meta.get('triage_category_prob'))} "
        f"| {_num(meta.get('triage_action_prob'))} "
        f"| {_num(meta.get('triage_impact_score'))} "
        f"| {_cell(meta.get('triage_source'))} |"
    )


def _cell(value: object) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _num(value: object) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):.2f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"


def _split_cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _blank(value: str) -> str | None:
    if value in {"", "—", "-"}:
        return None
    return value


def _none_if_dash(value: str | None) -> str | None:
    return value


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None

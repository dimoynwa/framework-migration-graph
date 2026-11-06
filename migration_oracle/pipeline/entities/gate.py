"""Action gate: drop kept rows whose research says nothing has to change.

Protected categories stay, and a missing or failed dossier never drops a row.
"""

from __future__ import annotations

from dataclasses import dataclass

from migration_oracle.pipeline.research.markdown import FilteredRow
from migration_oracle.pipeline.research.rows import kept_rows
from migration_oracle.pipeline.research.schema import ResearchDossier, action_of

# ``none`` drops these categories. ``breaking`` / ``deprecation`` / ``security``
# are absent on purpose: they stay unless removed from GATE_PROTECTED_CATEGORIES.
_NONE_DROP = frozenset(
    {
        "internal_fix",
        "noise",
        "new_optional_feature",
        "behavior_change",
        "config_change",
        "dependency_upgrade",
        "—",
        "–",
        "-",
    }
)
_DEFAULT_PROTECTED = frozenset({"breaking", "deprecation", "security"})


@dataclass(frozen=True)
class InputRow:
    """One triage-kept row, its dossier, and the gate decision."""

    position: int
    row: FilteredRow
    category: str
    impact_score: str
    row_type: str
    source: str
    statement: str
    dossier: ResearchDossier | None
    decision: str
    reason: str
    evidence: str


def category_key(category: str) -> str:
    return (category or "").strip().lower()


def decide(
    dossier: ResearchDossier | None,
    category: str,
    protected: frozenset[str],
) -> tuple[str, str, str]:
    """Return ``(decision, reason, evidence)`` for one kept row."""
    if dossier is None:
        return "keep", "dossier_missing", "row_only"
    if dossier.status == "not_found":
        return "keep", "dossier_not_found", "row_only"
    if dossier.status == "error":
        return "keep", "dossier_error", "row_only"
    action = action_of(dossier.text)
    if action != "none":
        return "keep", f"action_{action}", "dossier"
    key = category_key(category)
    if key in protected:
        return "keep", "protected_none", "dossier"
    if key in _NONE_DROP or (key in _DEFAULT_PROTECTED and key not in protected):
        return "drop", "research_none", "dossier"
    return "keep", "action_none", "dossier"


def load_input_rows(
    filter_md: str,
    dossiers: list[ResearchDossier],
    *,
    protected: frozenset[str],
) -> list[InputRow]:
    """Align kept rows with dossiers by position. Research writes them in that order."""
    rows = kept_rows(filter_md)
    meta = _table_meta(filter_md)
    if len(meta) != len(rows):
        raise ValueError(
            f"Kept-row table has {len(meta)} data rows but {len(rows)} research rows"
        )
    aligned: list[ResearchDossier | None] = list(dossiers[: len(rows)])
    aligned.extend([None] * (len(rows) - len(aligned)))
    loaded: list[InputRow] = []
    for position, (row, fields, dossier) in enumerate(zip(rows, meta, aligned)):
        decision, reason, evidence = decide(dossier, fields[0], protected)
        loaded.append(
            InputRow(
                position=position,
                row=row,
                category=fields[0],
                impact_score=fields[1],
                row_type=fields[2],
                source=fields[3],
                statement=fields[4],
                dossier=dossier,
                decision=decision,
                reason=reason,
                evidence=evidence,
            )
        )
    return loaded


def _table_meta(filter_md: str) -> list[tuple[str, str, str, str, str]]:
    """Category, impact score, type, source, and statement, in kept-row order."""
    records: list[tuple[str, str, str, str, str]] = []
    for line in filter_md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0].lower() == "type" or set(cells[0]) <= set("-: "):
            continue
        records.append(
            (
                cells[4] if len(cells) > 4 else "",
                cells[5] if len(cells) > 5 else "",
                cells[0],
                cells[2],
                cells[3],
            )
        )
    return records

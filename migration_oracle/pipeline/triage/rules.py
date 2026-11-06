"""Deterministic keep/drop rules applied before any classifier call."""

from __future__ import annotations

import re

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.triage.questions import DROP_CATEGORIES
from migration_oracle.pipeline.triage.settings import TriageSettings


_TITLE_KEEP_RE = re.compile(
    r"(?i)\b(removed|no longer|renamed|deprecat|breaking|must|requires?)\b"
)
_FOOTER_RE = re.compile(r"(?im)^(?:breaking changes?|breaking|deprecated)\s*:")
_BANG_RE = re.compile(r"^\w+(?:\([^)\n]*\))?!:")
_TITLE_LINE_RE = re.compile(r"(?im)^title:\s*(.+)$")
_PACKAGE_SRC_RE = re.compile(r"^packages/[^/]+/src(?:/|$)")
_TOOLING_COMMIT_TYPES = frozenset({"docs", "test", "ci", "build"})
_HARD_KEEP_TYPES = frozenset({"breaking", "deprecation", "mandatory_migration"})
_DOC_ISSUE_TYPES = frozenset({"documentation", "task"})


def title_line(statement: str) -> str:
    """The title line only. The keep regex must not see the commit body."""
    match = _TITLE_LINE_RE.search(statement or "")
    if match:
        return match.group(1).strip()
    for line in (statement or "").splitlines():
        if line.strip():
            return line.strip()
    return (statement or "").strip()


def pre_triage(change: DocumentedChange) -> str | None:
    """Return ``keep``, ``drop``, or ``None`` when the classifier must decide.

    Keep is evaluated first. A row is dropped only when a drop rule matches
    and no keep rule does.
    """
    if _hard_keep(change):
        return "keep"
    if _hard_drop(change):
        return "drop"
    return None


def should_drop(answers: dict, settings: TriageSettings) -> bool:
    """FR-4: drop only when every condition holds. Missing fields keep the row."""
    action = _as_float(_nested(answers, "requires_action", "noul"))
    choice = _nested(answers, "category", "choice")
    probabilities = _nested(answers, "category", "probabilities") or {}
    if not isinstance(choice, str) or not isinstance(probabilities, dict):
        return False
    category_prob = _as_float(probabilities.get(choice))
    impact = _as_float(_nested(answers, "impact", "score"))
    if action is None or category_prob is None or impact is None:
        return False
    return (
        action < settings.drop_max_action_prob
        and choice in DROP_CATEGORIES
        and category_prob >= settings.drop_min_category_prob
        and impact < settings.drop_max_impact_score
    )


def _hard_keep(change: DocumentedChange) -> bool:
    meta = change.metadata or {}
    if meta.get("has_schematic") is True:
        return True
    if change.type in _HARD_KEEP_TYPES and change.confidence == "confirmed":
        return True
    statement = change.statement or ""
    if _FOOTER_RE.search(statement):
        return True
    title = title_line(statement)
    if _BANG_RE.match(title):
        return True
    if _TITLE_KEEP_RE.search(title):
        return True
    return False


def _hard_drop(change: DocumentedChange) -> bool:
    meta = change.metadata or {}
    if _tooling_only_commit(meta):
        return True
    if _normalized_issue_type(meta.get("github_issue_type")) in _DOC_ISSUE_TYPES:
        return True
    if meta.get("github_not_planned") is True:
        return True
    if _changelog_pointer(change.statement or ""):
        return True
    return False


def _tooling_only_commit(meta: dict) -> bool:
    commit_type = str(meta.get("angular_commit_type") or "").strip().lower()
    if commit_type not in _TOOLING_COMMIT_TYPES:
        return False
    files = meta.get("github_files")
    if not isinstance(files, list) or not files:
        return False
    return all(
        isinstance(path, str) and not _PACKAGE_SRC_RE.match(path) for path in files
    )


def _normalized_issue_type(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    if text.startswith("type:"):
        text = text.split(":", 1)[1].strip()
    return text


def _changelog_pointer(statement: str) -> bool:
    text = re.sub(r"\s+", " ", statement).strip()
    if not text or text.lower().startswith("title:"):
        return False
    lowered = text.lower()
    if lowered.startswith("for all changes since"):
        return True
    if lowered.startswith("changes in the underlying wildfly core"):
        return True
    if "/compare/" not in text or len(text) >= 500:
        return False
    stripped = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", text)
    stripped = re.sub(r"https?://\S+", " ", stripped)
    stripped = re.sub(
        r"(?i)for all changes since|see the|full changelog|"
        r"changes in the underlying wildfly core",
        " ",
        stripped,
    )
    return len(stripped.strip(" .,-")) < 40


def _nested(payload: dict, section: str, key: str) -> object:
    block = payload.get(section)
    if not isinstance(block, dict):
        return None
    return block.get(key)


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None

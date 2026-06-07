"""Shared severity helpers for scope filtering."""

from __future__ import annotations

SEVERITY_RANK: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def severity_meets_threshold(severity: str | None, min_severity: str | None) -> bool:
    if not min_severity:
        return True
    if not severity:
        return False
    return SEVERITY_RANK.get(severity.lower(), 0) >= SEVERITY_RANK.get(
        min_severity.lower(), 0
    )


def filter_by_scope_and_severity(
    scopes: list[dict],
    *,
    scope_filter: list[str],
    min_severity: str | None,
) -> bool:
    if not scopes:
        return not scope_filter and not min_severity
    for scope in scopes:
        scope_value = scope.get("scope") or ""
        severity_value = scope.get("severity") or ""
        if scope_filter and scope_value not in scope_filter:
            continue
        if not severity_meets_threshold(severity_value, min_severity):
            continue
        return True
    return False

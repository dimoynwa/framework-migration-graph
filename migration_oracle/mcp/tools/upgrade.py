"""Upgrade MCP tool handlers."""

from __future__ import annotations

from migration_oracle.mcp.graph.queries import upgrade as upgrade_queries
from migration_oracle.mcp.instance import mcp


def _to_minor_zero(version: str) -> str:
    """Normalise 'major.minor.patch' → 'major.minor.0' for graph lookups."""
    parts = version.split(".", 2)
    return f"{parts[0]}.{parts[1]}.0"


def _flatten_rules(rows: list[dict]) -> list[dict]:
    rules: list[dict] = []
    for row in rows:
        for rule in row.get("rules") or []:
            rules.append(rule)
    return rules


@mcp.tool()
def analyze_upgrade_path(
    framework: str,
    current_version: str,
    target_version: str,
    user_entities: list[str] | None = None,
    format: str = "json",
    classification: list[str] | None = None,
    include_recipes: bool = False,
    include_lifecycle: bool = True,
    top_n: int = 50,
    verbose: bool = False,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> dict:
    """Return migration rules and lifecycle alerts for a framework version range.

    Queries all MigrationRule nodes whose version range covers [current_version, target_version].
    Optionally filter by scope ('api-surface', 'runtime', 'config', 'build', 'test') and
    severity ('low', 'medium', 'high', 'critical').

    Returns: rules list (statement, steps, scopes, recipes), lifecycle_alerts list.
    Each rule contains steps: [] and scopes: [] when no MigrationStep/BreakingScope nodes
    exist in the graph (pre-redesign data) — this is expected, not an error.
    """
    rows = upgrade_queries.analyze_upgrade_path(
        framework=framework,
        current_version=_to_minor_zero(current_version),
        target_version=_to_minor_zero(target_version),
        user_entities=user_entities or [],
        classification=classification,
        scope_filter=scope_filter or [],
        min_severity=min_severity,
    )
    rules = _flatten_rules(rows)[:top_n]
    lifecycle_alerts = []
    if include_lifecycle:
        for row in rows:
            lifecycle_alerts.extend(row.get("lifecycle_events") or [])

    if format == "markdown":
        lines = [
            f"# Upgrade path: {framework} {current_version} → {target_version}",
            "",
            f"Rules: {len(rules)}",
        ]
        for rule in rules:
            lines.append(f"- {rule.get('statement', '')}")
        return {"status": "ok", "format": "markdown", "content": "\n".join(lines)}

    return {
        "status": "ok",
        "framework": framework,
        "from_version": current_version,
        "to_version": target_version,
        "rules": rules,
        "lifecycle_alerts": lifecycle_alerts,
        "format": format,
    }


@mcp.tool()
def build_recipe_plan(
    current_version: str,
    target_version: str,
    framework: str = "Spring Boot",
    user_entities: list[str] | None = None,
    auto_only: bool = False,
    classification: list[str] | None = None,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> dict:
    """Produce a two-track migration plan: auto (scriptable) and manual (human review required).

    Auto track: steps with automatable=true, effort=mechanical, and a linked OpenRewrite recipe.
    Manual track: all other steps. Falls back to rule-level cards when no MigrationStep nodes exist.

    Returns: auto_track list, manual_track list, fallback_to_rule_cards bool.
    An empty auto_track is expected in the first release (no AUTOMATED_BY edges yet).
    """
    plan = upgrade_queries.build_recipe_plan(
        framework=framework,
        current_version=_to_minor_zero(current_version),
        target_version=_to_minor_zero(target_version),
        user_entities=user_entities,
        classification=classification,
        scope_filter=scope_filter or [],
        min_severity=min_severity,
    )
    manual_track = plan["manual_track"]
    if auto_only:
        manual_track = []
    return {
        "status": "ok",
        "auto_track": plan["auto_track"],
        "manual_track": manual_track,
        "fallback_to_rule_cards": plan["fallback_to_rule_cards"],
    }

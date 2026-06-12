"""Deprecation MCP tool handlers."""

from __future__ import annotations

from migration_oracle.mcp.graph.queries import deprecation as deprecation_queries
from migration_oracle.mcp.instance import mcp


@mcp.tool()
def resolve_deprecation(entity_name: str, framework: str = "Spring Boot") -> dict:
    """Return deprecation metadata and replacement for a single entity name (one hop only).

    entity_name must be the fully-qualified name as stored in the graph
    (e.g. 'org.springframework.boot.env.EnvironmentPostProcessor', not 'EnvironmentPostProcessor').
    Short or partial names will return status='not_found'.

    Returns: deprecated_in, removed_in, replaced_by (direct successor only), and related rules.
    For the full replacement chain across multiple versions use entity_evolution instead.
    Returns status='not_found' when the entity is not in the graph.
    """
    record = deprecation_queries.resolve_deprecation(
        entity_name=entity_name, framework=framework
    )
    if record is None:
        return {
            "status": "not_found",
            "entity_name": entity_name,
            "message": "No deprecation records found",
        }
    rules = [
        {
            "rule_id": "",
            "statement": r.get("statement") or "",
            "rule_type": r.get("type") or "",
            "action_step": r.get("action_step") or r.get("solution") or "",
            "source_url": "",
            "change_type": "",
            "reason": r.get("reason") or "",
            "entity_classification": "",
            "steps": [],
            "scopes": [],
            "recipes": [],
        }
        for r in record.get("rules") or []
        if r.get("statement")
    ]
    return {
        "status": "ok",
        "entity_name": record.get("original_entity") or entity_name,
        "entity_type": record.get("entity_type") or "",
        "deprecated_in": record.get("deprecated_in"),
        "removed_in": record.get("removed_in"),
        "replaced_by": record.get("replaced_by"),
        "rules": rules,
    }


@mcp.tool()
def entity_evolution(entity_name: str, framework: str = "Spring Boot") -> dict:
    """Trace the full REPLACED_BY replacement chain for an entity, up to 5 hops.

    entity_name must be the fully-qualified name as stored in the graph
    (e.g. 'org.springframework.boot.env.EnvironmentPostProcessor', not 'EnvironmentPostProcessor').

    Returns: chain list where each node includes entity_name, entity_type, deprecated_in,
    removed_in, and related rules. The chain starts at entity_name and follows REPLACED_BY
    edges until the terminus or the 5-hop limit.
    """
    chain_rows = deprecation_queries.entity_evolution(
        entity_name=entity_name, framework=framework
    )
    chain = [
        {
            "entity_name": row.get("entity_name") or "",
            "entity_type": row.get("entity_type") or "",
            "deprecated_in": row.get("deprecated"),
            "removed_in": row.get("removed"),
            "rules": [r for r in (row.get("rules") or []) if r.get("type") or r.get("statement")],
        }
        for row in chain_rows
    ]
    return {
        "status": "ok",
        "origin": entity_name,
        "chain": chain,
    }

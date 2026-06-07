"""Tests for deprecation MCP tools."""

from __future__ import annotations

from unittest.mock import patch

from migration_oracle.mcp.tools.deprecation import entity_evolution, resolve_deprecation


def test_resolve_deprecation_found():
    record = {
        "entity_type": "Class",
        "original_entity": "WebSecurityConfigurerAdapter",
        "replaced_by": "SecurityFilterChain",
        "deprecated_in": "3.0.0",
        "removed_in": "3.4.0",
        "rules": [{"statement": "removed", "type": "MigrationRule"}],
    }
    with patch(
        "migration_oracle.mcp.tools.deprecation.deprecation_queries.resolve_deprecation",
        return_value=record,
    ):
        result = resolve_deprecation(entity_name="WebSecurityConfigurerAdapter")
    assert result["status"] == "ok"
    assert result["deprecated_in"] == "3.0.0"
    assert result["removed_in"] == "3.4.0"
    assert result["replaced_by"] == "SecurityFilterChain"


def test_resolve_deprecation_not_found():
    with patch(
        "migration_oracle.mcp.tools.deprecation.deprecation_queries.resolve_deprecation",
        return_value=None,
    ):
        result = resolve_deprecation(entity_name="MissingEntity")
    assert result["status"] == "not_found"


def test_entity_evolution_chain():
    chain = [
        {"entity_name": "A", "entity_type": "Class", "deprecated": "1.0", "removed": None, "rules": []},
        {"entity_name": "B", "entity_type": "Class", "deprecated": "2.0", "removed": "3.0", "rules": []},
    ]
    with patch(
        "migration_oracle.mcp.tools.deprecation.deprecation_queries.entity_evolution",
        return_value=chain,
    ):
        result = entity_evolution(entity_name="A")
    assert result["status"] == "ok"
    assert len(result["chain"]) == 2
    assert result["chain"][0]["entity_name"] == "A"

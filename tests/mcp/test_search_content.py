"""Tests for search content field projection (LP-001 regression prevention)."""

from __future__ import annotations

from unittest.mock import patch

from migration_oracle.mcp.tools.search import _build_hits


def test_build_hits_statement_populated():
    """Each non-openrewrite hit has a non-empty statement from node.statement."""
    fused = [("node-1", 0.9)]
    nodes = [{"node_id": "node-1", "node_type": "MigrationRule",
              "statement": "Use jakarta.persistence instead of javax.persistence",
              "solution": "Replace the import",
              "source_url": "", "action_step": "", "rule_type": "migration_rule"}]
    with patch("migration_oracle.mcp.tools.search.search_queries.hydrate_nodes", return_value=nodes):
        hits = _build_hits(fused, framework="Spring Boot", openrewrite=False)
    assert len(hits) == 1
    assert hits[0]["statement"] == "Use jakarta.persistence instead of javax.persistence"
    assert hits[0]["solution"] == "Replace the import"


def test_build_hits_statement_falls_back_to_description():
    """When statement is absent, falls back to description (for recipe-type nodes)."""
    fused = [("node-1", 0.8)]
    nodes = [{"node_id": "node-1", "node_type": "OpenRewriteRecipe",
              "statement": None, "description": "Migrate javax.persistence to jakarta",
              "solution": None, "source_url": "", "action_step": "", "rule_type": ""}]
    with patch("migration_oracle.mcp.tools.search.search_queries.hydrate_nodes", return_value=nodes):
        hits = _build_hits(fused, framework="Spring Boot", openrewrite=False)
    assert len(hits) == 1
    assert hits[0]["statement"] == "Migrate javax.persistence to jakarta"


def test_build_hits_no_empty_statement_when_data_present():
    """Regression: statement must never be empty when the node has the property."""
    fused = [("node-a", 1.0), ("node-b", 0.7)]
    nodes = [
        {"node_id": "node-a", "node_type": "MigrationRule",
         "statement": "Rule A", "solution": "Sol A",
         "source_url": "", "action_step": "", "rule_type": "pipeline_rule"},
        {"node_id": "node-b", "node_type": "MigrationRule",
         "statement": "Rule B", "solution": None,
         "source_url": "", "action_step": "", "rule_type": "pipeline_rule"},
    ]
    with patch("migration_oracle.mcp.tools.search.search_queries.hydrate_nodes", return_value=nodes):
        hits = _build_hits(fused, framework="Spring Boot", openrewrite=False)
    assert all(h["statement"] != "" for h in hits)
    assert hits[0]["solution"] == "Sol A"
    assert hits[1]["solution"] == ""

"""Tests for schema MCP tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from migration_oracle.mcp.tools.schema import execute_custom_cypher, get_graph_schema


def test_execute_custom_cypher_safe():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher",
        return_value=[{"n": 1}],
    ):
        result = execute_custom_cypher("MATCH (n) RETURN n LIMIT 1")
    assert result["status"] == "ok"
    assert result["row_count"] == 1


def test_execute_custom_cypher_blocks_create():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("CREATE (n:Test)")
    assert result["status"] == "blocked"
    assert result["blocked_keyword"] == "CREATE"
    mock_exec.assert_not_called()


def test_execute_custom_cypher_blocks_merge():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("MERGE (n:Test {id: 1})")
    assert result["status"] == "blocked"
    mock_exec.assert_not_called()


def test_execute_custom_cypher_blocks_set():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("MATCH (n) SET n.x = 1 RETURN n")
    assert result["status"] == "blocked"
    mock_exec.assert_not_called()


def test_execute_custom_cypher_blocks_delete():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("MATCH (n) DELETE n")
    assert result["status"] == "blocked"
    mock_exec.assert_not_called()


def test_execute_custom_cypher_blocks_remove():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("MATCH (n) REMOVE n.x")
    assert result["status"] == "blocked"
    mock_exec.assert_not_called()


def test_execute_custom_cypher_blocks_drop():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("DROP INDEX idx IF EXISTS")
    assert result["status"] == "blocked"
    mock_exec.assert_not_called()


def test_execute_custom_cypher_blocks_call_db():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("CALL db.index.fulltext.queryNodes('x', 'y')")
    assert result["status"] == "blocked"
    mock_exec.assert_not_called()


def test_execute_custom_cypher_case_insensitive():
    with patch(
        "migration_oracle.mcp.tools.schema.schema_queries.execute_read_cypher"
    ) as mock_exec:
        result = execute_custom_cypher("create (n:Test)")
    assert result["status"] == "blocked"
    mock_exec.assert_not_called()


def test_get_graph_schema_no_cypher():
    with patch("migration_oracle.graph.driver.get_driver") as mock_driver:
        result = get_graph_schema()
    assert result["status"] == "ok"
    assert "Version" in result["schema_markdown"]
    mock_driver.assert_not_called()

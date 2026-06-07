"""Schema and custom Cypher MCP tool handlers."""

from __future__ import annotations

from migration_oracle.mcp.graph.queries import schema as schema_queries
from migration_oracle.mcp.instance import mcp


@mcp.tool()
def get_graph_schema() -> dict:
    """Return the authoritative graph schema as a Markdown string. No Cypher is executed.

    Use this before execute_custom_cypher to understand available node labels, relationship
    types, and property names. Returns: schema_markdown string.
    """
    return {
        "status": "ok",
        "schema_markdown": schema_queries.GRAPH_SCHEMA_MD,
    }


@mcp.tool()
def execute_custom_cypher(query: str) -> dict:
    """Execute a read-only Cypher query against the graph and return rows.

    Blocked keywords (returns status='blocked'): CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL db.
    Only SELECT-equivalent MATCH queries are permitted. Returns: rows list, row_count.
    Call get_graph_schema first to verify node labels and property names before writing a query.
    """
    blocked = schema_queries.check_mutation(query)
    if blocked:
        return {
            "status": "blocked",
            "rows": [],
            "row_count": 0,
            "blocked_keyword": blocked,
            "message": f"Query blocked: contains {blocked}",
        }
    try:
        rows = schema_queries.execute_read_cypher(query)
        return {
            "status": "ok",
            "rows": rows,
            "row_count": len(rows),
            "blocked_keyword": "",
            "message": "",
        }
    except Exception as exc:  # noqa: BLE001 — surface graph errors to caller
        return {
            "status": "error",
            "rows": [],
            "row_count": 0,
            "blocked_keyword": "",
            "message": str(exc),
        }

"""Shared FastMCP instance for tool registration."""

import os

from mcp.server.fastmcp import FastMCP


def _create_mcp() -> FastMCP:
    from migration_oracle.mcp.paysafe_lifespan import paysafe_cache_lifespan

    return FastMCP("PaysafeMigrationOracle", lifespan=paysafe_cache_lifespan)


mcp = _create_mcp()

if os.environ.get("MCP_TRACE_FILE", "").strip():
    from migration_oracle.mcp.tracing import install_tracing
    install_tracing(mcp)

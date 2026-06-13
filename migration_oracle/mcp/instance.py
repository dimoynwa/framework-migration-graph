"""Shared FastMCP instance for tool registration."""

import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("PaysafeMigrationOracle")

if os.environ.get("MCP_TRACE_FILE", "").strip():
    from migration_oracle.mcp.tracing import install_tracing
    install_tracing(mcp)

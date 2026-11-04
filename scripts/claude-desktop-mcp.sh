#!/usr/bin/env bash
# Stdio launcher for Claude Desktop. Desktop cannot use the Docker SSE URL
# (localhost is not reachable as a custom connector).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$ROOT/.env"
    set +a
fi

export MCP_TRANSPORT=stdio
# Claude Desktop aborts local MCP connect after 10s. Skip index ensure and
# embedding warm-up so initialize can complete; the model loads on first search.
export MCP_FAST_START=1
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec "${ROOT}/.venv/bin/python" -m migration_oracle.mcp.server

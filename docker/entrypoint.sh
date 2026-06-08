#!/bin/sh
set -e

cleanup() {
    kill "$MCP_PID" "$ST_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python -m migration_oracle.mcp.server &
MCP_PID=$!

streamlit run migration_oracle/streamlit_app/app.py \
    --server.headless true \
    --server.port "${STREAMLIT_SERVER_PORT:-8501}" \
    --server.address 0.0.0.0 &
ST_PID=$!

# Poll until either process exits (POSIX sh; no wait -n)
while kill -0 "$MCP_PID" 2>/dev/null && kill -0 "$ST_PID" 2>/dev/null; do
    sleep 1
done

# Capture the exit code of whichever died
if ! kill -0 "$MCP_PID" 2>/dev/null; then
    wait "$MCP_PID" 2>/dev/null || true
    EXIT_CODE=$?
else
    wait "$ST_PID" 2>/dev/null || true
    EXIT_CODE=$?
fi

exit $EXIT_CODE

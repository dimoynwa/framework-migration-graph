# Quickstart: Docker Oracle Image (007)

**Branch**: `007-docker-oracle-image` | **Date**: 2026-06-08

---

## Prerequisites

- Docker ≥ 24.0 (or compatible container runtime)
- Docker Compose V2 (for the compose workflow)
- Internet access at build time (model download)

---

## 1. Build the Image

```sh
# Standard build — uses default model (all-mpnet-base-v2)
docker build -t paysafe-migration-oracle:latest .

# Verbose build to watch layer progress
docker build --progress=plain -t paysafe-migration-oracle:latest .

# Build with a specific uv version pinned
docker build \
  --build-arg UV_VERSION=0.5 \
  -t paysafe-migration-oracle:latest .
```

**Expected output**: The build downloads pytorch and the embedding model on first run (~1–2 GB). Subsequent builds with the same `uv.lock` and model ARG will use cached layers and complete in under 60 seconds.

---

## 2. Override the Embedding Model at Build Time

```sh
# Use a different sentence-transformers model
docker build \
  --build-arg SENTENCE_TRANSFORMERS_MODEL=all-MiniLM-L6-v2 \
  -t paysafe-migration-oracle:minilm .
```

> **Important**: The model name is baked into the image. Setting `SENTENCE_TRANSFORMERS_MODEL` as a runtime env var to a different value than what was used at build time will cause a cold model download on first request, violating the zero-cold-start guarantee.

---

## 3. Run with `docker run`

```sh
docker run \
  --rm \
  -p 8080:8080 \
  -p 8501:8501 \
  -e NEO4J_URI="bolt://host.docker.internal:7687" \
  -e NEO4J_PASSWORD="your-neo4j-password" \
  -e ANTHROPIC_API_KEY="your-anthropic-key" \
  paysafe-migration-oracle:latest
```

### With optional overrides

```sh
docker run \
  --rm \
  -p 8080:8080 \
  -p 8501:8501 \
  -e NEO4J_URI="bolt://neo4j:7687" \
  -e NEO4J_PASSWORD="your-neo4j-password" \
  -e ANTHROPIC_API_KEY="your-anthropic-key" \
  -e MCP_PORT=8080 \
  -e STREAMLIT_SERVER_PORT=8501 \
  -e LOG_LEVEL=DEBUG \
  -v "$(pwd)/data:/data" \
  paysafe-migration-oracle:latest
```

---

## 4. Run with Docker Compose (Recommended for local development)

```sh
# Copy the env template and fill in your values
cp .env.example .env
# Edit .env: set NEO4J_PASSWORD, ANTHROPIC_API_KEY, etc.

# Start the full stack (oracle + Neo4j)
docker compose up

# Start in detached mode
docker compose up -d

# View logs from all services
docker compose logs -f

# View logs from oracle only
docker compose logs -f oracle

# Stop and remove containers (data volume is preserved)
docker compose down

# Stop and remove containers AND data volume
docker compose down -v
```

---

## 5. Verify Both Endpoints Are Live

Run these after the container reports healthy (or after ~60 s).

### MCP SSE endpoint
```sh
# Should print HTTP headers ending with "text/event-stream" and then block (Ctrl+C to exit)
curl -v --max-time 5 http://localhost:8080/sse || true
# Exit code 28 (timeout) = healthy. Exit code 7 (refused) = not ready yet.
```

### Streamlit UI
```sh
# Should return {"status":"ok"}
curl -fsS http://localhost:8501/_stcore/health
```

### Check container health status
```sh
docker inspect --format='{{.State.Health.Status}}' $(docker ps -qf "ancestor=paysafe-migration-oracle:latest")
# Expected: healthy  (after start-period of 60 s)
```

### Open the Streamlit dashboard in a browser
```
http://localhost:8501
```

---

## 6. Connect an MCP Client to the SSE Endpoint

Configure your MCP-compatible AI client (e.g. Claude Code, Claude Desktop) with:

```json
{
  "mcpServers": {
    "paysafe-migration-oracle": {
      "url": "http://localhost:8080/sse"
    }
  }
}
```

---

## 7. Check Image Size

```sh
docker image inspect paysafe-migration-oracle:latest \
  --format='{{.Size}}' | numfmt --to=iec
# Should be ≤ 3 GB uncompressed (SC-008)
```

---

## 8. What the Container Runs Internally

The entrypoint script (`docker/entrypoint.sh`) starts both processes in the background and exits as soon as either one stops:

```sh
# MCP SSE server — listens on MCP_PORT (default 8080), binds 0.0.0.0
python -m migration_oracle.mcp.server

# Streamlit UI — the three flags below are required for correct in-container binding
streamlit run migration_oracle/streamlit_app/app.py \
    --server.headless true \
    --server.address 0.0.0.0 \
    --server.port "${STREAMLIT_SERVER_PORT:-8501}"
```

`--server.headless true` suppresses the browser-open prompt.  
`--server.address 0.0.0.0` binds to all container interfaces so the port is reachable from the host.  
`--server.port` respects the `STREAMLIT_SERVER_PORT` env var; defaults to `8501`.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Container exits immediately | Missing `NEO4J_URI` or `NEO4J_PASSWORD` | Check `docker logs <id>`; set required env vars |
| Container exits within 30 s | One process crashed | Run `docker logs <id>` to see which process failed |
| `/sse` returns connection refused | MCP server still starting | Wait up to 60 s; check `docker inspect` health status |
| First query is slow after build | Model was not pre-baked (build-time network failed) | Rebuild with network access; verify `docker build` output shows model download |
| `ModuleNotFoundError` in logs | WORKDIR or venv not correctly set up | Ensure image was built from repo root with the correct Dockerfile path |
| Health status stuck at `starting` | Neo4j not reachable — MCP server startup probe fails | Check `NEO4J_URI` and network connectivity to Neo4j |

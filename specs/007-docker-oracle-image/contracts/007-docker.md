# Container Contract: paysafe-migration-oracle (007)

**Version**: 1.0 | **Branch**: `007-docker-oracle-image` | **Date**: 2026-06-08

This document defines what the `paysafe-migration-oracle` Docker image guarantees to consumers. Any deviation from these guarantees is a regression.

---

## 1. Port Contract

The image always exposes exactly two TCP ports. Both are bound to `0.0.0.0` inside the container.

| Port | Service | Default | Overridable via | Protocol |
|------|---------|---------|-----------------|----------|
| `8080` | MCP SSE server | Yes | `MCP_PORT` env var | HTTP / `text/event-stream` |
| `8501` | Streamlit UI | Yes | `STREAMLIT_SERVER_PORT` env var | HTTP |

**Guarantees**:
- Both ports are listening within 60 seconds of container start when required environment variables are set.
- Port values are reflected in the `EXPOSE` directives of the Dockerfile.
- If a port override env var is set, the service binds to that port and the original default port is not bound.

---

## 2. Environment Variable Contract

### 2.1 Required at Runtime

| Variable | Description |
|----------|-------------|
| `NEO4J_URI` | Bolt URI of the Neo4j graph database, e.g. `bolt://neo4j:7687` |
| `NEO4J_PASSWORD` | Password for the Neo4j user |

If either required variable is absent or empty, the container exits with a non-zero code immediately after start. The error message naming the missing variable is written to stdout.

### 2.2 Pre-Set by the Image (do not override)

| Variable | Value | Reason |
|----------|-------|--------|
| `PYTHONUNBUFFERED` | `1` | Ensures MCP server log lines reach `docker logs` without buffering |
| `MCP_TRANSPORT` | `sse` | Container is built for SSE transport only |
| `HF_HOME` | `/app/.cache/huggingface` | Points to pre-baked model cache |
| `WORKDIR` | `/app` | Both processes start from this directory |

**Do not** set `PYTHONUNBUFFERED=0` or `MCP_TRANSPORT=stdio` in `docker run` — doing so produces undefined behaviour.

### 2.3 Optional Overrides (full list in data-model.md)

All other environment variables are optional and have documented defaults. Consumers may set any of them at runtime without requiring a rebuild.

---

## 3. Volume Contract

| Mount Point | Owner | Purpose | Required |
|-------------|-------|---------|----------|
| `/data` | `oracle:oracle` (uid 1000) | Runtime data injection — CA certificates, custom config files, debug artifacts | No |

**Guarantees**:
- `/data` exists in the image and is owned by `oracle:oracle`.
- The container starts successfully if `/data` is not mounted.
- Files written to `/data` by the container are owned by uid 1000; host mounts should use matching uid or set `--user 1000:1000`.

---

## 4. Health-Check Contract

The container declares a `HEALTHCHECK` instruction. Consumers of this image (orchestrators, CI pipelines) can rely on it without writing custom probes.

### 4.1 MCP SSE Health Check

| Attribute | Value |
|-----------|-------|
| Endpoint | `http://127.0.0.1:${MCP_PORT}/sse` |
| Method | GET |
| Healthy exit codes | `0` (immediate close) or `28` (timeout after headers — server is streaming) |
| Unhealthy exit codes | `7` (connection refused), `22` (HTTP 4xx/5xx) |
| Command | `curl -fsS --max-time 5 http://127.0.0.1:${MCP_PORT:-8080}/sse; ret=$?; [ $ret -eq 0 ] \|\| [ $ret -eq 28 ]` |

### 4.2 Streamlit UI Health Check

| Attribute | Value |
|-----------|-------|
| Endpoint | `http://127.0.0.1:${STREAMLIT_SERVER_PORT:-8501}/_stcore/health` |
| Method | GET |
| Expected response | `{"status":"ok"}` with HTTP 200 |
| Command | `curl -fsS --max-time 5 http://127.0.0.1:${STREAMLIT_SERVER_PORT:-8501}/_stcore/health` |

### 4.3 HEALTHCHECK Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `--interval` | `30s` | Balance between detection speed and probe overhead |
| `--timeout` | `10s` | Accommodates the SSE stream's `--max-time 5` plus overhead |
| `--start-period` | `60s` | Both services may take up to 60 s to start cold |
| `--retries` | `3` | Avoids transient failures marking the container unhealthy |

The container transitions to `unhealthy` if either service is unreachable for 3 consecutive intervals (≤ 90 s after the start period expires).

---

## 5. Fail-Fast Contract

If either internal process (MCP server or Streamlit UI) exits for any reason, the container itself stops within 30 seconds and reports a non-zero exit code. This is implemented via `wait -n` in the entrypoint script.

**Guarantee**: A container that has stopped with exit code 0 is not a healthy state — it means a process exited cleanly but unexpectedly. Orchestrators should treat any container exit as a failure.

---

## 6. Security Contract

| Guarantee | Detail |
|-----------|--------|
| Non-root runtime | Container runs as `oracle` (uid 1000, gid 1000) |
| No secrets in image | All credentials injected at runtime via environment variables |
| No capabilities | No `--cap-add` required or expected |
| Read-only root fs | Not guaranteed by default; consumers may layer `--read-only` with a writable `/data` tmpfs |

---

## 7. Build Reproducibility Contract

Given identical `pyproject.toml`, `uv.lock`, source code, and build ARGs, two builds on the same platform MUST produce images that behave identically (same Python environment, same model files). Minor-version-pinned uv and locked dependencies enforce this guarantee (FR-012).

---

## 8. Out-of-Scope Guarantees

The following are explicitly **not** guaranteed by this image:

- A bundled Neo4j instance — consumers must provide their own.
- HTTPS/TLS termination — terminate TLS at a reverse proxy or load balancer.
- Production-ready secrets management — use a secrets manager (Vault, AWS Secrets Manager) to inject env vars.
- Arm64/multi-arch builds — the image targets `linux/amd64`; arm64 support is a future enhancement.

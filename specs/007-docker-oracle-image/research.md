# Research: Docker Oracle Image (007)

**Branch**: `007-docker-oracle-image` | **Date**: 2026-06-08

---

## Decision 1 — Process Supervisor: Shell Script vs supervisord

### Decision
A POSIX sh supervisor script using `&` (background) + `wait -n` (wait for first child to exit) is the chosen mechanism. `supervisord` is explicitly excluded.

### Rationale
The spec's FR-007 mandates fail-fast: if either process exits, the container must stop and signal failure within 30 s. `wait -n` is the POSIX primitive that does exactly this — it returns as soon as *any* of the listed PIDs exits, making the shell PID 1 exit naturally. The container runtime then records the exit code.

`supervisord` is designed for the *opposite* purpose: it keeps processes alive through restarts. Its restart policies (`autorestart = true`) would silently absorb crashes and keep the container running — making FR-007 impossible without non-trivial supervisord config to disable restarts and configure an exit-on-failure global setting (`nodaemon = true` + `exitcodes` + `autorestart = false`). The added config surface area, the ~2 MB binary, and the risk of mis-configuration outweigh any benefit.

The shell script also satisfies GAP-001's portability requirement: it runs under `/bin/sh` available in `python:3.11-slim` with no extra packages.

### Alternatives Considered
| Alternative | Verdict | Reason rejected |
|------------|---------|-----------------|
| `supervisord` | Rejected | Restart policies conflict with FR-007; adds complexity and size |
| `s6-overlay` | Rejected | Overkill; requires full init system, adds ~3 MB; no advantage for 2-process case |
| `foreman` / `honcho` | Rejected | Python/Ruby dependency adds size; not available in slim base without extra install |
| `tini` as PID 1 + shell script | Acceptable alternative | `tini` improves signal forwarding; can be layered in if signal handling proves problematic in practice, but is not required for the current use case |

### Entrypoint Script Pattern
```sh
#!/bin/sh
set -e

python -m migration_oracle.mcp.server &
MCP_PID=$!

streamlit run migration_oracle/streamlit_app/app.py \
  --server.headless true \
  --server.port "${STREAMLIT_SERVER_PORT:-8501}" &
ST_PID=$!

# Exit as soon as either child exits; propagate its exit code
wait -n $MCP_PID $ST_PID
EXIT_CODE=$?
kill $MCP_PID $ST_PID 2>/dev/null || true
exit $EXIT_CODE
```

**Note**: `wait -n` requires POSIX.1-2008 sh or later. It is available in `dash` (the default `/bin/sh` on Debian/Ubuntu-based images including `python:3.11-slim`).

---

## Decision 2 — PyTorch Layer Cache Strategy

### Decision
All application dependencies are installed in a **single** `RUN uv sync --frozen --no-dev` command. PyTorch is not pre-installed in a separate layer. The **layer ordering** is the primary cache optimisation: copy lock files first, sync dependencies, download the model, copy source last.

### Rationale
The goal of cache strategy is to avoid re-downloading pytorch (~800 MB) on every source-code change. The correct lever is not splitting the `uv sync` command, but ensuring the lock-file copy + sync steps come *before* source code is copied.

Docker layer cache is content-addressed: a layer is cache-valid as long as its preceding layers and its own `RUN` instruction inputs are unchanged. By ordering:
1. `COPY pyproject.toml uv.lock ./` → cache key = lock file content
2. `RUN uv sync --frozen --no-dev` → only invalidated when `uv.lock` changes
3. `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('...')"` → only invalidated when model ARG changes
4. `COPY migration_oracle/ ./migration_oracle/` → source changes only invalidate this layer

Source-only edits (the common case) skip all of steps 1–3 from cache, saving the full pytorch + model download time.

Splitting `uv sync` into a pytorch-first layer would complicate the Dockerfile and break cache if the lock file changes the torch version — at which point *both* the split torch layer and the remainder layer are invalidated anyway.

### Alternatives Considered
| Alternative | Verdict | Reason rejected |
|------------|---------|-----------------|
| Split torch install as a separate `RUN pip install torch` before `uv sync` | Rejected | Bypasses uv lock file for the heaviest dep; breaks reproducibility guarantee (FR-012) |
| Split into `uv sync --only-group torch` + full `uv sync` | Rejected | `uv` does not support installing a subset of deps by package name in `sync` mode |
| Pre-built base image with torch already installed | Viable alternative | Reduces builder layer rebuilds to near-zero for pytorch; adds image registry management overhead; acceptable for a future optimisation once the image size baseline is measured |
| `--compile-bytecode` flag on `uv sync` | Additive | Reduces cold-start time by pre-compiling `.pyc` files; low cost; can be added without changing the strategy |

---

## Decision 3 — uv Acquisition Method

### Decision
`uv` is sourced by copying the pre-built binary from the official `ghcr.io/astral-sh/uv` image at a **pinned minor-version tag** (e.g., `ghcr.io/astral-sh/uv:0.5`). The `curl` installer is excluded.

### Rationale
- **Reproducibility**: A pinned image tag produces the same binary on every build; `curl | sh` resolves to whatever version the install script serves at build time.
- **Layer cache efficiency**: Docker pulls the uv image once and caches it; the `COPY` instruction is a no-op on subsequent builds if the tag has not moved.
- **No shell dependency in builder**: The `COPY --from` pattern requires no `curl`, `wget`, or network access at `RUN` time.
- **uv 0.5+** is the minimum version required for `uv sync --frozen` to be stable on Python 3.11 with `hatchling` build backends.

### Exact pattern
```dockerfile
FROM ghcr.io/astral-sh/uv:0.5 AS uv-bin

FROM python:3.11-slim AS builder
COPY --from=uv-bin /uv /usr/local/bin/uv
```

---

## Decision 4 — MCP SSE Health-Check Curl Pattern

### Decision
The MCP SSE endpoint (`/sse`) returns a `text/event-stream` long-lived connection. A plain `curl http://…/sse` will hang indefinitely. The health-check must use `--max-time` and accept exit code 28 (curl timeout after receiving HTTP headers) as a healthy signal.

### Confirmed liveness URL
`http://127.0.0.1:${MCP_PORT}/sse` — derived from FastMCP defaults (`sse_path: /sse`, `host: 127.0.0.1`; config.py sets `MCP_PORT` default to `8080`). FastMCP exposes no `/health` or `/ping` endpoint on the SSE transport.

### Health-check command
```sh
curl -fsS --max-time 5 http://127.0.0.1:${MCP_PORT:-8080}/sse; \
  ret=$?; [ $ret -eq 0 ] || [ $ret -eq 28 ]
```
Exit codes: 0 = server responded and closed; 28 = server responded and is streaming (healthy); 7 = connection refused (unhealthy); 22 = HTTP 4xx/5xx error (unhealthy).

Streamlit exposes a proper one-shot liveness endpoint: `http://127.0.0.1:${STREAMLIT_SERVER_PORT:-8501}/_stcore/health` returns `{"status":"ok"}` immediately.

---

## Decision 5 — Image Size Mitigation Strategy

### Target
≤ 3 GB compressed (SC-008, FR-013).

### Estimated size breakdown
| Component | Approx. size |
|-----------|-------------|
| python:3.11-slim base | ~130 MB |
| PyTorch (CPU-only, via sentence-transformers transitive dep) | ~800 MB |
| sentence-transformers + other ML deps | ~200 MB |
| all-mpnet-base-v2 model files | ~420 MB |
| Application code + remaining deps | ~100 MB |
| **Total (uncompressed)** | **~1.65 GB** |
| **Compressed estimate** | **~900 MB – 1.2 GB** |

The 3 GB ceiling is comfortably achievable with standard mitigations.

### Required mitigations (in priority order)
1. **Multi-stage build**: build-time tooling (gcc, build headers, uv binary in builder) is not copied to final image.
2. `uv sync --frozen --no-dev`: omits pytest, respx, and other dev dependencies.
3. `pip install --no-cache-dir` / `apt-get --no-install-recommends` + `rm -rf /var/lib/apt/lists/*` in the same `RUN` layer where system packages are installed.
4. `.dockerignore` excludes `tests/`, `specs/`, `.specify/`, `runs/`, `eval/`, `*.md` from build context.
5. `sentence-transformers` installs CPU-only torch by default when no CUDA is detected — no additional flag needed.

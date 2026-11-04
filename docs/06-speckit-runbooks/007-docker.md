# SpecKit Runbook — `007-docker`

> **How to use this file:** Paste each prompt block verbatim into Claude Code in the order shown.
> Do not skip the gap-review steps — they catch the most common drift before it compounds.
> Complete all items in a gap review before advancing to the next command.

---

## Prerequisites

Before starting this spec:

- `005-mcp-server` ✅ — `migration_oracle/mcp/server.py` starts via `python -m migration_oracle.mcp.server`; `MCP_TRANSPORT=sse` must be a supported transport value
- `006-streamlit-ui` ✅ — `migration_oracle/streamlit_app/app.py` must be the Streamlit entry point, runnable via `streamlit run`
- `pyproject.toml` + `uv.lock` are committed and up-to-date; `uv sync` produces a clean environment
- Python 3.11+ is required (enforced in `pyproject.toml`)
- External Neo4j 5.x is assumed — it is NOT bundled in the image; wired as a sidecar in `docker-compose.yml`

---

## Command 1 — `/speckit.specify`

Paste this entire block:

```
/speckit.specify

WHAT it does: Packages the PaysafeMigrationOracle into a single Docker image that
starts the MCP server (SSE transport) and the Streamlit UI as two co-located
processes. The image is built for minimal final size using a multi-stage build
with uv for dependency installation.

WHY it exists: Teams need a self-contained deployment artifact — a single
`docker run` (or compose up) command that makes both the MCP SSE endpoint and
the Streamlit dashboard reachable without a local Python environment or uv
install.

DOCKER IMAGE and what it does:
  - Accepts all runtime configuration via environment variables (no secrets baked in)
  - Exposes MCP SSE server on a configurable port (default 8080)
  - Exposes Streamlit UI on a configurable port (default 8501)
  - Starts both processes from a single entrypoint; if either exits non-zero the
    container exits (fail-fast)
  - Downloads and caches the sentence-transformers embedding model at build time
    so the first request is not penalised by a cold model download
  - Declares /data as the volume mount point for Neo4j connection config if needed

KEY BEHAVIORS:
MULTI_STAGE_BUILD — The final image is built from a slim Python base (python:3.11-slim);
  all build-time tooling (uv, gcc, build headers) is present only in the builder stage
  and does not appear in the final layer.
MODEL_PREBAKE — The sentence-transformers model named by SENTENCE_TRANSFORMERS_MODEL
  (default all-mpnet-base-v2) is downloaded into the image during the build stage so
  the cache is warm on first container start.
PROCESS_SUPERVISION — A lightweight supervisor (supervisord or a minimal shell script)
  starts both `python -m migration_oracle.mcp.server` (MCP_TRANSPORT=sse) and
  `streamlit run migration_oracle/streamlit_app/app.py --server.headless true` and
  forwards stdout/stderr from both to container stdout.
PORT_EXPOSURE — The image EXPOSEs port 8080 (MCP SSE) and port 8501 (Streamlit);
  both are overridable via MCP_PORT and STREAMLIT_SERVER_PORT env vars.
ENV_CONTRACT — All credentials (NEO4J_URI, NEO4J_PASSWORD, ANTHROPIC_API_KEY, etc.)
  are injected at runtime via environment variables; none are baked into layers.
NO_ROOT — The final image runs as a non-root user (uid 1000) for security.
COMPOSE_COMPANION — A docker-compose.yml is provided alongside the Dockerfile,
  wiring Neo4j as a linked service and providing sensible volume/network defaults for
  local development.
HEALTHCHECK — The image declares a HEALTHCHECK that probes the MCP SSE endpoint
  (HTTP GET /sse or equivalent liveness path) and the Streamlit health endpoint.

INTEGRATION CONSTRAINTS:
  - Base image must be python:3.11-slim (not alpine — sentence-transformers requires glibc)
  - uv must be used for dependency installation in the builder stage (not pip directly)
  - The sentence-transformers model cache dir must be set via SENTENCE_TRANSFORMERS_HOME
    or HF_HOME and must be copied from builder to final image in the same path
  - No Neo4j instance in the image; the compose file links to neo4j:5 as a sidecar
  - The entrypoint script must be sh-compatible (no bash-isms) for image portability
  - Image must produce a reproducible build: pin uv version and use uv.lock
```

---

## Gap Review (post-specify)

After `/speckit.specify` generates `specs/007-docker/spec.md`, paste this review:

```
Review specs/007-docker/spec.md for these critical gaps before we proceed to planning:

GAP-001: Supervisor choice not decided
  The spec says "supervisord or a minimal shell script". The plan must pick exactly one.
  Supervisord adds ~2 MB but gives per-process restart policies; a shell script (& + wait)
  is smaller but exits on first child death. State which is required and why.

GAP-002: Model prebake build arg
  SENTENCE_TRANSFORMERS_MODEL defaults to all-mpnet-base-v2 at runtime, but the build-time
  download needs a BUILD ARG (not an ENV) so the model name is fixed at build time.
  Is ARG SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2 the required pattern?

GAP-003: MCP SSE liveness path not confirmed
  The HEALTHCHECK behavior names "HTTP GET /sse or equivalent". Confirm the exact liveness
  URL from migration_oracle/mcp/server.py (FastMCP SSE mount point) so the Dockerfile
  HEALTHCHECK is not guessing.

GAP-004: Streamlit MCP_HOST env var wiring
  The Streamlit app (spec 006) connects to the MCP server. When both run in the same
  container the MCP host for Streamlit must be 127.0.0.1, not the external MCP_HOST.
  The spec must state this internal wiring requirement explicitly.

GAP-005: uv.lock reproducibility
  The spec says "pin uv version and use uv.lock" but does not state the minimum uv
  version required for --frozen installs, or where the uv binary is sourced from
  (ghcr.io/astral-sh/uv image vs curl installer). State the exact acquisition method.

GAP-006: Layer cache strategy for heavy deps
  sentence-transformers pulls pytorch (~800 MB). The spec must state whether pytorch
  should be installed before other deps (to maximise Docker layer cache hits on
  incremental rebuilds) or whether the full uv sync is one RUN command.

GAP-007: compose file scope
  The spec mentions docker-compose.yml but does not say whether it is development-only
  or also the production deployment artifact. This affects whether it should include
  build: context or only image: references.

GAP-008: Non-root user creation
  The spec says uid 1000 but does not state the username, whether it should be created
  with useradd/adduser, or whether the model cache directory must be chowned to it.
  Make this explicit so the Dockerfile has no ambiguity.
```

---

## Command 2 — `/speckit.plan`

Paste this entire block:

```
/speckit.plan

Generate plan.md, data-model.md, quickstart.md, contracts/007-docker.md, and
research.md for spec 007-docker.

Required artifacts:
- plan.md: multi-stage Dockerfile structure, layer ordering rationale, supervisor
  choice justification, uv acquisition method, model cache copy strategy, and the
  full file tree including docker/entrypoint.sh, docker-compose.yml, .dockerignore
- data-model.md: full environment variable contract table (name, required/optional,
  default, purpose) covering both MCP and Streamlit processes; BUILD ARG table
- quickstart.md: exact commands to build the image, run with docker run, run with
  compose, verify both endpoints are live, and override the embedding model
- contracts/007-docker.md: what the image guarantees to consumers — port contract,
  env contract, volume contract, health endpoint contract
- research.md: document the supervisord-vs-shell-script trade-off decision and the
  pytorch layer-cache strategy decision with rationale
```

---

## Gap Review (post-plan)

After `/speckit.plan` generates its artifacts, paste this review:

```
Review specs/007-docker/plan.md and supporting files for these gaps:

PLAN-GAP-001: Layer ordering not explicit
  plan.md must show the exact RUN command sequence in the builder stage:
  (1) install uv, (2) copy uv.lock + pyproject.toml, (3) uv sync --frozen,
  (4) download model. Confirm this order is stated, not implied.

PLAN-GAP-002: Model cache path consistency
  The HF_HOME / SENTENCE_TRANSFORMERS_HOME path used in the builder stage must be
  identical to the path COPYed into the final stage and set in ENV. Confirm both
  stages reference the same absolute path.

PLAN-GAP-003: entrypoint.sh in plan.md file tree
  The entrypoint script must appear as a named file in the plan.md directory tree
  (e.g. docker/entrypoint.sh). Confirm it is listed, not implied.

PLAN-GAP-004: Streamlit headless and address flags
  quickstart.md must show the exact streamlit run invocation including
  --server.headless true --server.address 0.0.0.0 --server.port flags so
  Streamlit binds correctly inside the container.

PLAN-GAP-005: compose Neo4j health dependency
  The docker-compose.yml (or its description in plan.md) must state that the
  migration-oracle service has depends_on: neo4j with condition: service_healthy
  so it does not start before Neo4j is ready.

PLAN-GAP-006: .dockerignore scope
  plan.md must mention .dockerignore and list what it must exclude: runs/, tests/,
  specs/, .claude/, __pycache__, *.pyc, *.egg-info, .git. Without this the build
  context will be large and slow.
```

---

## Command 3 — `/speckit.tasks`

```
/speckit.tasks
```

---

## Gap Review (post-tasks)

After `/speckit.tasks` generates `specs/007-docker/tasks.md`, paste this review:

```
Review specs/007-docker/tasks.md for these gaps:

TASK-GAP-001: .dockerignore task exists
  Confirm there is an explicit task to create .dockerignore before the Dockerfile
  build task — it is a prerequisite for a fast build context.

TASK-GAP-002: Model prebake verification task
  Confirm there is a task to verify the model is present in the final image layer:
    docker run --rm <image> python -c "from sentence_transformers import \
      SentenceTransformer; SentenceTransformer('all-mpnet-base-v2')"
  Not just that the build succeeds.

TASK-GAP-003: Both endpoints smoke-test task
  Confirm there is a task that starts the container and checks both
  :8080 (MCP SSE) and :8501 (Streamlit health) before the spec is marked complete.

TASK-GAP-004: compose up task
  Confirm there is a task for `docker compose up` smoke-test (not just `docker run`),
  since compose wires Neo4j — this is the realistic dev workflow.

TASK-GAP-005: Non-root verification task
  Confirm there is a task that asserts the container process runs as uid 1000, not root:
    docker run --rm <image> id
```

---

## Command 4 — `/speckit.implement`

```
/speckit.implement
```

---

## Recovery Prompts

Paste the relevant block if implementation drifts:

**1 — Wrong base image (alpine used):**
```
Do not use python:3.11-alpine. sentence-transformers requires glibc and will fail
to install on musl/alpine. Use python:3.11-slim (Debian-based) for both builder
and final stages.
```

**2 — pip used instead of uv:**
```
Do not use pip install. Use uv sync --frozen --no-dev in the builder stage.
uv must be acquired from the official ghcr.io/astral-sh/uv image using:
  COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
before the sync step. The uv.lock file must be copied before pyproject.toml
to allow Docker layer caching on dependency changes.
```

**3 — Both processes in foreground (container exits immediately):**
```
The entrypoint script must start the MCP server and Streamlit as background
processes (&), then use `wait -n` (or `wait $PID1 $PID2` with a trap) so the
container stays alive and exits with the first non-zero child exit code.
Do not use exec for either process — exec replaces the shell and abandons the other.
```

**4 — Model downloaded at runtime (not prebaked):**
```
The sentence-transformers model must be downloaded during docker build, not at
container start. In the builder stage, after uv sync, add:
  RUN python -c "from sentence_transformers import SentenceTransformer; \
      SentenceTransformer('${SENTENCE_TRANSFORMERS_MODEL}')"
Then COPY the HF_HOME directory from builder to final. If this RUN is missing,
the first container start incurs a 400–800 MB download.
```

**5 — Streamlit connecting to external MCP host inside container:**
```
When both processes run in the same container, the Streamlit app must connect
to the MCP server via 127.0.0.1 (loopback), not via the externally-advertised
MCP_HOST. Set MCP_HOST=127.0.0.1 in the entrypoint script for the Streamlit
process only, overriding any externally-injected MCP_HOST value.
```

**6 — Secrets baked into image layers:**
```
NEO4J_PASSWORD, ANTHROPIC_API_KEY, GITLAB_API_KEY, and FINDIT_AUTH_TOKEN must
never appear in any RUN, ENV, or ARG layer of the Dockerfile. They are runtime
environment variables only. Use --env-file or docker compose env_file at run time.
Remove any ENV statement for these variables immediately.
```

---

## What Success Looks Like

```bash
# Build succeeds under 1 GB final image size
docker build -t migration-oracle:007 .
docker images migration-oracle:007  # SIZE < 1 GB

# Both endpoints respond
docker run -d --name mo-test \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e NEO4J_PASSWORD=secret \
  -p 8080:8080 -p 8501:8501 migration-oracle:007

curl -I http://localhost:8080/sse        # HTTP 200 or 405
curl -I http://localhost:8501/healthz    # HTTP 200

# Runs as non-root
docker exec mo-test id  # uid=1000

# compose workflow
docker compose up -d
# Both services healthy within 60 seconds
```

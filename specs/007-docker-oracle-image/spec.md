# Feature Specification: Docker Deployment for Migration Oracle

**Feature Branch**: `007-docker-oracle-image`

**Created**: 2026-06-08

**Status**: Draft

**Input**: Package PaysafeMigrationOracle into a single Docker image with MCP SSE server and Streamlit UI co-located, using multi-stage build for minimal image size.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single-Command Deployment (Priority: P1)

A team member with no local Python environment needs to run the Migration Oracle. They have only Docker installed. With a single `docker run` command (or `docker compose up`), both the AI assistant dashboard and the MCP integration endpoint become reachable on well-known ports — no dependency installation, no virtual environment setup, no model download wait.

**Why this priority**: This is the primary value proposition. If a team cannot start the oracle with one command, the packaging effort fails its core purpose.

**Independent Test**: Can be fully tested by running `docker run` with the required environment variables and verifying both the dashboard URL and MCP endpoint respond within the container startup window.

**Acceptance Scenarios**:

1. **Given** a machine with Docker installed and no Python environment, **When** the operator runs the container image with the required environment variables, **Then** both the migration assistant UI and the MCP SSE endpoint are reachable within 60 seconds.
2. **Given** a running container, **When** the operator queries the migration assistant UI, **Then** the response is returned without any model download occurring at runtime.
3. **Given** a running container, **When** the operator connects an MCP-capable AI client to the SSE endpoint, **Then** the client receives the tool manifest and can invoke migration tools.

---

### User Story 2 - Local Development with Compose (Priority: P2)

A developer wants to run the full Migration Oracle stack locally, including a graph database. Using the provided companion configuration file, they issue a single compose command that starts the oracle container alongside a graph database, with networking and volumes pre-configured so the oracle can reach the database without manual setup.

**Why this priority**: Local development is the second most common use case; without a working compose companion, developers must manually wire up the database connection every time.

**Independent Test**: Can be fully tested by running `docker compose up` in a directory containing the companion file and verifying the oracle connects to the co-started database and returns migration data.

**Acceptance Scenarios**:

1. **Given** a machine with Docker Compose installed, **When** the operator runs compose using the companion file, **Then** both the oracle and graph database containers start, and the oracle is able to query the database.
2. **Given** the compose stack is running, **When** the operator opens the migration assistant UI, **Then** migration graph data sourced from the graph database is visible.
3. **Given** the compose stack is running, **When** the operator stops the stack, **Then** all containers stop cleanly and data persisted to named volumes is retained.

---

### User Story 3 - Fail-Fast Visibility (Priority: P3)

An operator running the oracle in a CI pipeline or monitored environment needs to know immediately if either service (the MCP server or the UI) has crashed. If either stops unexpectedly, the container itself must stop and report failure so that orchestration tooling (Docker, Kubernetes, CI runner) can detect the failure and alert.

**Why this priority**: Silent half-failures — where one service dies while the other continues — are hard to detect and lead to confusing support incidents.

**Independent Test**: Can be fully tested by intentionally terminating one of the two internal processes and verifying the container exits with a non-zero status within 30 seconds.

**Acceptance Scenarios**:

1. **Given** a running container, **When** the MCP server process exits unexpectedly, **Then** the container stops and reports a non-zero exit code within 30 seconds.
2. **Given** a running container, **When** the UI process exits unexpectedly, **Then** the container stops and reports a non-zero exit code within 30 seconds.
3. **Given** a stopped container, **When** the operator inspects container logs, **Then** log output from both services is present and clearly attributed to each service.

---

### User Story 4 - Liveness Monitoring (Priority: P4)

An operator deploying the container in a managed environment (Kubernetes, ECS, Nomad) needs the orchestrator to know whether the oracle is healthy without writing custom probes. The container must declare its own health-check so the orchestrator can automatically restart it if it becomes unresponsive.

**Why this priority**: Standard health-check declaration is a prerequisite for production-grade orchestration; without it, dead containers are not restarted automatically.

**Independent Test**: Can be fully tested by inspecting the container health status via `docker inspect` after startup and confirming both service paths are probed.

**Acceptance Scenarios**:

1. **Given** a running container, **When** the built-in health-check executes, **Then** it probes both the MCP SSE endpoint and the UI endpoint and reports healthy if both respond.
2. **Given** a container where one service has crashed, **When** the health-check executes, **Then** it reports unhealthy.

---

### Edge Cases

- What happens when the graph database is unreachable at container startup?
- What happens if a required environment variable (such as the API key) is missing or invalid?
- What happens if the configured MCP port or UI port is already occupied on the host?
- What happens if the embedding model was not pre-baked into the image (e.g., build-time network was unavailable)?
- What happens if the container is started with insufficient memory to load the embedding model?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The deployment artifact MUST start both the migration assistant UI and the MCP SSE endpoint as a single runnable unit from one command.
- **FR-002**: All configuration values — including graph database credentials, AI API keys, and service ports — MUST be injectable at runtime via environment variables; none may be embedded in the image.
- **FR-003**: The MCP SSE endpoint MUST be reachable on a configurable port (default 8080) after the container has started.
- **FR-004**: The migration assistant UI MUST be reachable on a configurable port (default 8501) after the container has started.
- **FR-005**: The embedding model MUST be present and ready inside the image at build time so that no model download occurs when the container starts or processes its first request.
- **FR-006**: The container MUST run as a non-privileged user (not root) at runtime.
- **FR-007**: If either internal service exits with a non-zero status, the container MUST itself stop and exit with a non-zero status within 30 seconds.
- **FR-008**: The container MUST declare a health-check that verifies both the MCP SSE endpoint and the migration assistant UI are responsive.
- **FR-009**: A companion configuration file MUST be provided that, when used with a standard container orchestration tool, starts the oracle alongside a graph database with networking and volumes pre-configured.
- **FR-010**: The container MUST declare a dedicated mount point at `/data` for injecting persistent configuration or data at runtime without rebuilding the image.
- **FR-011**: Log output from both internal services MUST be written to the container's standard output stream so it is captured by standard container logging infrastructure.
- **FR-012**: The image build MUST be reproducible: given the same source code and dependency lock files, two builds on the same platform MUST produce functionally identical images.
- **FR-013**: The final image MUST NOT exceed 3 GB compressed. Primary mitigations are: excluding all build-time tooling from the final stage (multi-stage build), running `uv sync --frozen --no-dev` to omit development dependencies, passing `--no-install-recommends` to any system package manager invocations, and removing package manager caches in the same `RUN` instruction that installs them.
- **FR-014**: The model download step in the builder stage MUST cause the entire `docker build` to fail with a non-zero exit code if the download fails or is incomplete. No fallback, `|| true`, or silent error suppression is permitted on the model download command.
- **FR-015**: The MCP server process MUST emit log lines to container stdout without buffering. This requires the environment variable `PYTHONUNBUFFERED=1` to be set for the MCP server process; it MUST be declared as an `ENV` in the final image.
- **FR-016**: Both processes (MCP server and Streamlit UI) MUST start from a working directory of `/app`, which is where the application source is installed in the final image stage. The entrypoint script MUST be executed with `/app` as the current directory.

### Key Entities

- **Deployment Image**: The self-contained, portable artifact that encapsulates all application code, dependencies, and the pre-cached embedding model.
- **MCP SSE Endpoint**: The AI integration surface exposed as a server-sent-events stream; consumed by MCP-compatible AI clients to invoke migration tools.
- **Migration Assistant UI**: The interactive web dashboard for exploring migration guidance, exposed as a browser-accessible service.
- **Configuration Contract**: The complete set of environment variables accepted by the container at runtime, covering credentials, endpoint URLs, and port assignments.
- **Companion Compose File**: The local-development configuration that declares the oracle container and a graph database sidecar as a single deployable unit.
- **Embedding Model Cache**: The pre-downloaded model data embedded in the image, ensuring zero-latency model availability on first use.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A team member with no Python environment installed can have the full Migration Oracle running and both services responding within 5 minutes of pulling the image, using only a single command.
- **SC-002**: The first migration query processed after container start completes in the same time as subsequent queries — no one-time model download delay is measurable on first use.
- **SC-003**: Both the migration assistant UI and the MCP endpoint are accessible from a single container start command with no additional configuration steps beyond environment variable injection.
- **SC-004**: If either internal service stops unexpectedly, the container halts and signals failure within 30 seconds, enabling orchestration tooling to detect and respond to the failure automatically.
- **SC-005**: A developer can bring up a fully functional local stack (oracle + graph database) with a single compose command and no manual networking or volume configuration.
- **SC-006**: Container health status transitions to unhealthy within two health-check intervals when either service becomes unresponsive, enabling automated restart by orchestration tooling.
- **SC-007**: Two independent builds from the same source and lock files produce images that behave identically, ensuring deployments are predictable and auditable.
- **SC-008**: The final compressed image size does not exceed 3 GB, verified by `docker image inspect` after a clean build; this ceiling accounts for pytorch (~800 MB), the pre-baked embedding model (~400 MB), and application dependencies, while excluding all build-time tooling from the final layer.

## Assumptions

- Teams have Docker (or a compatible container runtime) installed; no local Python, dependency management tooling, or virtual environment is required.
- A graph database instance will be provided externally to the image; the image does not bundle a database.
- The embedding model defaults to `all-mpnet-base-v2`; teams requiring a different model must rebuild the image with the alternative model name supplied at build time — changing only the runtime environment variable is insufficient.
- Build-time internet access is available to download the embedding model during image construction.
- The MCP transport is SSE (Server-Sent Events); other MCP transports (stdio, HTTP streaming) are out of scope for this feature.
- The deployment target is any environment capable of running Linux containers (Docker, Kubernetes, ECS, Nomad, etc.).
- Port conflicts on the host are the operator's responsibility to resolve via port mapping; the container itself does not detect host-side conflicts.
- The companion compose file targets local development; production orchestration manifests (Helm charts, ECS task definitions) are out of scope for this feature.
- The Streamlit UI calls migration tools directly in-process via shared Python imports, not via the MCP SSE endpoint over HTTP; no internal HTTP wiring between the two processes is required.

## Resolved Technical Constraints

This section records decisions that were ambiguous at specification time and have been resolved through code inspection or explicit design choice. These decisions are binding for planning and implementation.

### GAP-001 — Process Supervisor

**Decision**: A minimal sh-compatible shell script (using `&` background execution and `wait -n`) is the required supervisor mechanism. `supervisord` is explicitly excluded.

**Rationale**: The fail-fast behaviour required by FR-007 (container stops when either service exits) is the native behaviour of `wait -n` — it returns as soon as any child exits. `supervisord` introduces per-process restart policies that would silently keep the container alive after a child death, which directly conflicts with FR-007. The shell script approach adds zero image size and no additional dependencies.

**Constraint**: The entrypoint script MUST be POSIX sh-compatible (no bash-isms). It MUST use `wait -n` (or equivalent) so that the container process exits immediately when either child exits, propagating a non-zero exit code.

---

### GAP-002 — Embedding Model Build Argument

**Decision**: The model to pre-bake is controlled by a Dockerfile `ARG` named `SENTENCE_TRANSFORMERS_MODEL` with default value `all-mpnet-base-v2`. This ARG is distinct from the runtime `ENV` of the same name.

**Rationale**: The model must be fixed at build time so the correct files are embedded in the image layer. A runtime `ENV` alone would allow a mismatch between the pre-baked model and the model name requested at runtime, causing a cold download on first use — defeating FR-005.

**Constraint**: The Dockerfile MUST declare `ARG SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2` in the builder stage and use its value for the model download. The final image MUST also set `ENV SENTENCE_TRANSFORMERS_MODEL=${SENTENCE_TRANSFORMERS_MODEL}` so the runtime value matches the pre-baked model. Teams that require a different model MUST supply `--build-arg SENTENCE_TRANSFORMERS_MODEL=<name>` and accept a full rebuild. The model download `RUN` instruction MUST NOT include any error-suppression (`|| true`, `; true`, `2>/dev/null` hiding exit codes); a failed download MUST propagate a non-zero exit code and abort the build (see FR-014).

---

### GAP-003 — MCP SSE Liveness Path

**Decision**: The exact health-check URL for the MCP SSE endpoint is `http://127.0.0.1:${MCP_PORT}/sse`.

**Rationale**: Confirmed by code inspection of the FastMCP library: `FastMCP.settings.sse_path` defaults to `/sse` and `FastMCP.settings.host` defaults to `127.0.0.1`. The `config.py` in this project sets `MCP_PORT` (default `8080`). No custom `mount_path` is set on the `FastMCP` instance, so the default `/sse` path is authoritative.

**Constraint**: FastMCP exposes no dedicated `/health` or `/ping` route — the only available path is `/sse`, which returns a long-lived `text/event-stream` connection. The HEALTHCHECK MUST use `curl` with a hard timeout and treat both exit code 0 (immediate close) and exit code 28 (timeout after headers received) as healthy, and all other exit codes (7 = connection refused, 22 = HTTP error) as unhealthy. Required invocation pattern: `curl -fsS --max-time 5 http://127.0.0.1:${MCP_PORT}/sse; ret=$?; [ $ret -eq 0 ] || [ $ret -eq 28 ]`. The Streamlit health endpoint returns a proper one-shot 200: `curl -fsS --max-time 5 http://127.0.0.1:${STREAMLIT_SERVER_PORT}/_stcore/health`.

---

### GAP-004 — Streamlit-to-MCP Wiring

**Decision**: No internal HTTP wiring between the Streamlit process and the MCP SSE process is required or present.

**Rationale**: Code inspection of all Streamlit page files confirms they call migration tools via direct Python function imports (`from migration_oracle.mcp.tools.context import ...`, `from migration_oracle.mcp.tools.search import search_migration_knowledge`). The Streamlit process connects directly to Neo4j, not to the MCP SSE endpoint. Both processes share the same Python environment and the same environment variable configuration.

**Constraint**: The entrypoint script MUST NOT set a loopback MCP URL for the Streamlit process. Both processes receive the same environment variables unchanged.

---

### GAP-005 — uv Version and Acquisition Method

**Decision**: `uv` is sourced by copying the binary from the official `ghcr.io/astral-sh/uv` image at a pinned version tag (e.g., `COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /bin/uv`). The `curl`-installer method is explicitly excluded.

**Rationale**: Copying from the official uv image avoids a network call during `docker build` (the image layer is cached), produces a reproducible result tied to a specific uv version, and requires no shell tooling (`curl`, `sh`) in the builder stage.

**Constraint**: The pinned uv version tag MUST be a minor-version pin (e.g., `0.5`, not `latest`) to ensure reproducibility. Dependency installation in the builder stage MUST use `uv sync --frozen` (available since uv 0.1.24) to guarantee that only the versions recorded in `uv.lock` are installed.

---

### GAP-006 — Docker Layer Cache Strategy for Heavy Dependencies

**Decision**: The full application dependency installation is performed in a single `RUN uv sync --frozen` command. A separate prior layer pre-installs `torch` is NOT required.

**Rationale**: `uv sync --frozen` resolves from the lock file in one pass and is already significantly faster than pip. Splitting into a torch-first layer complicates the Dockerfile and breaks if the lock file changes in a way that affects torch. The model pre-bake layer (which is the actual large artefact) is ordered after `uv sync` and before copying application source code, so it survives source-only changes.

**Constraint**: The builder stage MUST order its `RUN` instructions as: (1) copy `pyproject.toml` + `uv.lock`, (2) `uv sync --frozen`, (3) download and cache the embedding model, (4) copy remaining source. This ordering ensures the `uv sync` and model-download layers are cache-stable across source-only edits.

---

### GAP-007 — Compose File Scope

**Decision**: The `docker-compose.yml` is a local-development artifact only. It uses `build: context: .` to build the oracle image from local source.

**Rationale**: Production deployments are managed by separate orchestration manifests (Helm, ECS task definitions, etc.) which are out of scope per the Assumptions section. The compose file exists solely to reduce local setup friction for developers.

**Constraint**: The compose file MUST use `build: context: .` (not a registry `image:` reference) so developers always build from local source. It MUST declare a named volume for Neo4j data persistence. It MUST NOT contain any production secrets or registry credentials.

---

### GAP-008 — Non-Root User

**Decision**: The container runs as a dedicated system user named `oracle` with UID 1000 and GID 1000, created with `adduser --system --uid 1000 --group oracle` (or equivalent for the base image's `adduser` variant). The model cache directory and `/data` volume mount point MUST be `chown`ed to `oracle` before the `USER oracle` instruction.

**Rationale**: UID 1000 is the conventional first non-root user on Linux systems, minimising permission conflicts when volumes are mounted from the host. A named user (not anonymous UID) improves auditability in container logs.

**Constraint**: The final image MUST create the `oracle` user, `chown` the model cache directory (value of `HF_HOME`) and `/data` to `oracle:oracle`, then switch to `USER oracle` before the `ENTRYPOINT` instruction. No files owned by root may be written to at runtime.

---

### GAP-009 — PYTHONUNBUFFERED Requirement

**Decision**: `ENV PYTHONUNBUFFERED=1` MUST be declared in the final image stage.

**Rationale**: Python buffers stdout by default when not attached to a terminal. The MCP SSE server is a long-running process; without unbuffered output, log lines accumulate in Python's internal buffer and may never reach `docker logs` — violating FR-011. Streamlit sets this internally, but the MCP server process does not.

**Constraint**: The final image MUST declare `ENV PYTHONUNBUFFERED=1`. This applies to both processes since they share the same environment. The entrypoint script MUST NOT override or unset this variable.

---

### GAP-010 — WORKDIR and Application Source Location

**Decision**: The working directory for both processes is `/app`. Application source code is installed into `/app` in the final image stage.

**Rationale**: Both `python -m migration_oracle.mcp.server` and `streamlit run migration_oracle/streamlit_app/app.py` require the `migration_oracle` package to be importable from the current working directory or the Python path. A fixed, documented `WORKDIR` eliminates ambiguity about where source is copied and ensures both processes start from the same root.

**Constraint**: The Dockerfile MUST declare `WORKDIR /app` in the final stage. Application source code (the `migration_oracle/` package) MUST be copied to `/app`. The virtual environment produced by `uv sync` in the builder stage MUST be copied to `/app/.venv` (or equivalent) so that `uv run` or direct `python` invocations resolve the correct interpreter. The entrypoint script MUST be placed at `/app/entrypoint.sh` and run from `/app`.

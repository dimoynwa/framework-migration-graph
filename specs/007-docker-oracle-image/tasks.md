# Tasks: Docker Deployment for Migration Oracle (007)

**Input**: Design documents from `specs/007-docker-oracle-image/`

**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/007-docker.md ✅ | quickstart.md ✅

**Tests**: Not requested in spec; validation tasks are build/runtime smoke-checks, not automated test suites.

**Organization**: Tasks grouped by user story. Each story is independently deliverable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Parallelizable (different files, no blocking dependencies)
- **[Story]**: Maps to user story from spec.md (US1–US4)
- All file paths are relative to the repository root

---

## Phase 1: Setup

**Purpose**: Create the directory scaffold and verify that all prerequisite source files exist before writing any Docker artifacts.

- [x] T001 Verify repo root contains `pyproject.toml`, `uv.lock`, and `migration_oracle/` package; create `docker/` directory

**Checkpoint**: `docker/` directory exists. No other changes to existing files.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the two lowest-level artifacts that the Dockerfile references. Both are independent of each other and can be written in parallel; the Dockerfile cannot be completed without them.

**⚠️ CRITICAL**: Complete this phase before writing any `Dockerfile` instructions that reference `docker/entrypoint.sh` or `.dockerignore`.

- [x] T002 [P] Create `docker/entrypoint.sh` — POSIX sh supervisor script: background both processes with `&`, capture PIDs, call `wait -n $MCP_PID $ST_PID`, capture exit code, `kill` surviving process, `wait` for it, `exit $EXIT_CODE`. No bash-isms. `chmod +x` after creation. Exact design in `specs/007-docker-oracle-image/plan.md` § Entrypoint Script Design.
- [x] T003 [P] Create `.dockerignore` — 10-section exclusion file: version control (`.git/`), spec artifacts (`specs/`, `SpecKit-plans/`, `.specify/`), dev/test artifacts (`tests/`, `eval/`, `runs/`, `*.md` with `!migration_oracle/**/*.md` exception), Python artifacts (`__pycache__/`, `*.pyc`, `*.pyo`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `dist/`, `*.egg-info/`), env files (`.env`, `.env.*`, `!.env.example`), IDE/tooling (`.vscode/`, `.idea/`, `.cursor/`, `.claude/`), OS (`.DS_Store`, `Thumbs.db`), docs (`docs/`, `USAGE.md`, `EVALUATION*.md`). Exact design in `specs/007-docker-oracle-image/plan.md` § .dockerignore Design.

**Checkpoint**: Both `docker/entrypoint.sh` and `.dockerignore` exist; entrypoint is executable (`ls -l docker/entrypoint.sh` shows `-rwxr-xr-x`).

---

## Phase 3: User Story 1 — Single-Command Deployment (Priority: P1) 🎯 MVP

**Goal**: A team member with Docker only can run `docker run` and have both MCP SSE and Streamlit UI reachable within 60 seconds, with no cold model download on first use.

**Independent Test**: `docker run` with required env vars → `curl http://localhost:8080/sse` exits 0 or 28; `curl http://localhost:8501/_stcore/health` returns `{"status":"ok"}`.

### Implementation for User Story 1

- [x] T004 [US1] Create `Dockerfile` — add Stage 1 (`uv-bin`): `FROM ghcr.io/astral-sh/uv:${UV_VERSION:-0.5} AS uv-bin`. This stage is purely a source for the uv binary; it is never built into a runnable container.
- [x] T005 [US1] Add Stage 2 (`builder`) to `Dockerfile` — implement the 8-step layer order from `plan.md` § Multi-Stage Dockerfile Design: (1) `COPY --from=uv-bin /uv /usr/local/bin/uv`, (2) `RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*` (update must precede install on slim base — package index is absent otherwise), (3) `WORKDIR /app`, (4) `ENV HF_HOME=/app/.cache/huggingface`, (5) `COPY pyproject.toml uv.lock ./`, (6) `RUN uv sync --frozen --no-dev`, (7) `ARG SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2` + `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${SENTENCE_TRANSFORMERS_MODEL}')"` (no `|| true`), (8) `COPY migration_oracle/ ./migration_oracle/`.
- [x] T006 [US1] Add Stage 3 (`final`) to `Dockerfile` — from `python:3.11-slim`: (a) **re-declare the build ARG** `ARG SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2` as the very first instruction of this stage — ARG values do not propagate between stages; without this, `${SENTENCE_TRANSFORMERS_MODEL}` in the subsequent ENV line resolves to an empty string, silently breaking FR-005; (b) install `curl` and `procps` together in one `RUN apt-get update && apt-get install -y --no-install-recommends curl procps && rm -rf /var/lib/apt/lists/*` — `procps` provides `pgrep` and `pkill` required by T016/T017 fail-fast validation; (c) create `oracle` group (gid 1000) and user (uid 1000, no home); (d) `COPY --from=builder /app/.venv /app/.venv`, `COPY --from=builder /app/.cache /app/.cache`; (e) `WORKDIR /app`; (f) `COPY migration_oracle/ ./migration_oracle/`; (g) `COPY docker/entrypoint.sh ./entrypoint.sh && chmod +x ./entrypoint.sh`; (h) `RUN mkdir -p /data && chown -R oracle:oracle /app /data`; (i) `ENV PYTHONUNBUFFERED=1 MCP_TRANSPORT=sse MCP_HOST=0.0.0.0 MCP_PORT=8080 STREAMLIT_SERVER_PORT=8501 HF_HOME=/app/.cache/huggingface SENTENCE_TRANSFORMERS_MODEL=${SENTENCE_TRANSFORMERS_MODEL} PATH="/app/.venv/bin:$PATH"`; (j) `EXPOSE 8080 8501`; (k) `VOLUME /data`; (l) `HEALTHCHECK` (SSE exit-code 0/28 AND Streamlit 200 — exact CMD from `plan.md` § Stage 3); (m) `USER oracle`; (n) `ENTRYPOINT ["/app/entrypoint.sh"]`.
- [x] T007 [P] [US1] Create `.env.example` — document all env vars from `specs/007-docker-oracle-image/data-model.md`: required vars (`NEO4J_URI`, `NEO4J_PASSWORD`) with placeholder values and comment "# REQUIRED"; pre-set-by-image vars commented out with "# Set by image — do not override"; all optional vars with their defaults and one-line purpose comment. Group by section matching data-model.md (Graph DB, AI Provider, External Integrations, MCP Server, Streamlit, Embedding Model, Observability).

### Validation for User Story 1

- [ ] T008 [US1] Build and validate: run `docker build --progress=plain -t paysafe-migration-oracle:latest .` from repo root; confirm exit code 0 and that model download output (`all-mpnet-base-v2`) is visible in build log (FR-014 enforcement — no silent skip).
- [ ] T009 [US1] Verify model files in final image layer: `docker run --rm --entrypoint python paysafe-migration-oracle:latest -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-mpnet-base-v2')"` must exit 0 and print no `Downloading` progress lines — this confirms model files were copied from builder to the final stage, not just present in the builder layer (FR-005, SC-002).
- [ ] T010 [P] [US1] Verify non-root runtime: `docker run --rm --entrypoint id paysafe-migration-oracle:latest` must output `uid=1000(oracle) gid=1000(oracle)` — confirms the `USER oracle` instruction in the final stage is effective and no root escalation occurs (FR-006, GAP-008).
- [ ] T011 [US1] Run and validate both endpoints: `docker run --rm -p 8080:8080 -p 8501:8501 -e NEO4J_URI=... -e NEO4J_PASSWORD=... paysafe-migration-oracle:latest`; within 60 s confirm SSE endpoint (`curl --max-time 5 http://localhost:8080/sse`) exits 0 or 28, and Streamlit (`curl -fsS http://localhost:8501/_stcore/health`) returns HTTP 200 (SC-001, SC-003).
- [ ] T012 [US1] Validate no cold model download: after T011's container is running, check `docker logs <container-id> 2>&1 | grep -i "download\|Downloading\|fetching"` — the output must be empty, confirming no HuggingFace download traffic occurred at runtime. Additionally verify `docker logs <container-id> 2>&1 | grep -i "sentence.transform\|model"` shows the model loaded from cache (a cache-hit line), not freshly downloaded (SC-002, FR-005).

**Checkpoint**: User Story 1 fully functional. Both endpoints reachable within 60 s. Model files confirmed in final layer. Non-root uid confirmed. `docker build` fails if network unavailable during model download (FR-014).

---

## Phase 4: User Story 2 — Local Development with Compose (Priority: P2)

**Goal**: `docker compose up` in the repo root starts oracle + Neo4j with no manual network or volume configuration; oracle can query the database.

**Independent Test**: `docker compose up -d && sleep 30 && curl -fsS http://localhost:8501/_stcore/health` returns HTTP 200 and oracle logs show successful Neo4j connection.

### Implementation for User Story 2

- [x] T013 [US2] Create `docker-compose.yml` — version `3.9`, two services (`oracle` and `neo4j`): oracle uses `build: context: .` with `SENTENCE_TRANSFORMERS_MODEL` ARG, maps ports `${MCP_PORT:-8080}:${MCP_PORT:-8080}` and `${STREAMLIT_SERVER_PORT:-8501}:${STREAMLIT_SERVER_PORT:-8501}`, sets full env block from `plan.md` § docker-compose.yml Design (NEO4J_URI hardwired to `bolt://neo4j:7687`), mounts `oracle-data:/data`, `depends_on: neo4j: condition: service_healthy`, `restart: "no"`; neo4j uses `image: neo4j:5`, exposes 7474/7687, mounts `neo4j-data:/data`, declares `healthcheck` using `cypher-shell`; two named volumes: `oracle-data`, `neo4j-data`. Exact YAML in `plan.md` § docker-compose.yml Design.

### Validation for User Story 2

- [ ] T014 [US2] Validate compose start: `docker compose up -d`; wait for neo4j healthcheck to pass (`docker compose ps` shows neo4j healthy); confirm oracle starts and connects to neo4j (check `docker compose logs oracle` for connection success, no `NEO4J_URI` errors) (SC-005, acceptance scenario 1).
- [ ] T015 [US2] Validate data persistence: with compose running, create data in Neo4j via the UI; run `docker compose down`; run `docker compose up -d` again; confirm data is still present in Neo4j (named volume preserved) (acceptance scenario 3).

**Checkpoint**: User Stories 1 and 2 both work. Single compose command brings up full stack including database (T013–T015 complete).

---

## Phase 5: User Story 3 — Fail-Fast Visibility (Priority: P3)

**Goal**: If either internal process exits unexpectedly, the container itself exits with a non-zero code within 30 seconds.

**Independent Test**: `docker exec <id> kill <mcp-pid>` → `docker wait <id>` returns non-zero within 30 s.

### Validation for User Story 3

*(Implementation is already in `docker/entrypoint.sh` from T002; this phase is pure validation.)*

- [ ] T016 [US3] Validate MCP fail-fast: `docker exec <container-id> kill $(pgrep -f 'migration_oracle.mcp.server')` inside a running container; confirm with `docker wait` that the container exits with a non-zero code within 30 seconds (SC-004, FR-007, acceptance scenario 1).
- [ ] T017 [US3] Validate Streamlit fail-fast: `docker exec <container-id> kill $(pgrep -f 'streamlit')` inside a running container; confirm with `docker wait` that the container exits with a non-zero code within 30 seconds (FR-007, acceptance scenario 2).
- [ ] T018 [US3] Validate log visibility: `docker logs <container-id>` on a running container; confirm log lines from both the MCP server (`migration_oracle.mcp`) and Streamlit (`streamlit`) are present and timestamped in the output (FR-011, FR-015, acceptance scenario 3).

**Checkpoint**: All three user stories independently functional and tested. Fail-fast confirmed for both processes (T016–T018 complete).

---

## Phase 6: User Story 4 — Liveness Monitoring (Priority: P4)

**Goal**: `docker inspect` reports `healthy` after startup; reports `unhealthy` when a service crashes, without any custom probe written by the operator.

**Independent Test**: `docker inspect --format='{{.State.Health.Status}}' <id>` returns `healthy` ≥ 60 s after container start (before `start-period` expires the status is `starting`).

### Validation for User Story 4

*(HEALTHCHECK instruction is already in the Dockerfile from T006; this phase validates the declared probe.)*

- [ ] T019 [US4] Validate HEALTHCHECK transitions to healthy: start a container with required env vars; after 60 s (start-period), run `docker inspect --format='{{.State.Health.Status}}' <id>`; confirm status is `healthy`; confirm `docker inspect --format='{{.State.Health.Log}}' <id>` shows the SSE probe exiting 0 or 28 and the Streamlit probe returning 200 (FR-008, SC-006, acceptance scenario 1).
- [ ] T020 [US4] Validate HEALTHCHECK reports unhealthy after service crash: in a healthy running container, kill one internal process (MCP or Streamlit); after two `--interval` windows (60 s total), run `docker inspect` and confirm health status is `unhealthy` (SC-006, acceptance scenario 2).

**Checkpoint**: All four user stories implemented and validated (T019–T020 complete).

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Size ceiling verification, end-to-end quickstart smoke-test, and documentation sign-off.

- [ ] T021 [P] Verify image size: `docker image inspect paysafe-migration-oracle:latest --format='{{.Size}}' | numfmt --to=iec`; confirm ≤ 3 GB uncompressed (SC-008, FR-013). If over limit, apply additional `.dockerignore` exclusions or layer cleanup per plan.md § Phase C.
- [ ] T022 [P] Run quickstart.md end-to-end: execute the build command (§1), override-model build (§2), `docker run` with optional overrides (§3), compose workflow (§4), verify-endpoints commands (§5), MCP client config check (§6), and image size check (§7) as documented in `specs/007-docker-oracle-image/quickstart.md`; confirm all commands succeed and output matches documented expectations.
- [ ] T023 Update `specs/007-docker-oracle-image/checklists/requirements.md` — mark all 16 items complete with final validation notes; record actual measured image size (SC-008 evidence).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS Dockerfile authoring (T004–T006 reference `docker/entrypoint.sh`)
- **User Story 1 (Phase 3)**: Depends on Phase 2 — T004/T005/T006 are sequential (same file); T007 is parallel with T004–T006 (different file)
- **User Story 2 (Phase 4)**: Depends on Phase 3 validation (T011 confirms docker run works) — T013 can be written concurrently but validation (T014/T015) requires a working image
- **User Story 3 (Phase 5)**: Depends on Foundational (T002) + Phase 3 image being built (T008)
- **User Story 4 (Phase 6)**: Depends on Phase 3 image being built (T006 adds HEALTHCHECK)
- **Polish (Phase 7)**: Depends on all user story phases being complete

### User Story Dependencies

- **US1 (P1)**: No inter-story dependencies — blocks everything else
- **US2 (P2)**: Depends only on US1 image being buildable
- **US3 (P3)**: Depends only on Phase 2 (entrypoint.sh) + US1 image
- **US4 (P4)**: Depends only on US1 Dockerfile (HEALTHCHECK is in T006)

### Within Phase 3

- T004 → T005 → T006 (sequential — same Dockerfile)
- T007 [P] can run concurrently with T004–T006 (different file)
- T008 depends on T006 complete (image built)
- T009 and T010 [P] depend on T008 — both run against the built image, independently of each other
- T011 depends on T008 (needs running container)
- T012 depends on T011 (container running)

---

## Parallel Example: Phase 2 + Phase 3 Setup

```sh
# These two tasks can run in parallel — different files, no dependencies:
# Worker A:
create docker/entrypoint.sh   # T002

# Worker B:
create .dockerignore           # T003

# After both complete → start T004 (Dockerfile Stage 1)
```

## Parallel Example: Phase 3 + Phase 4 (once image is built)

```sh
# After T008 (docker build succeeds), these can run in parallel:
# Worker A: T009 (model in final layer) + T010 (non-root id check) — both [P], single commands
# Worker B: T013 (docker-compose.yml authoring — different file, no runtime dependency yet)
# Worker C (after T009/T010): T011 → T012 (docker run validation chain)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T003)
3. Complete Phase 3: User Story 1 (T004–T012)
4. **STOP and VALIDATE**: Both endpoints reachable, model pre-baked, build fails on download error
5. Ship image — teams can now `docker run` with a single command

### Incremental Delivery

1. Phase 1 + 2 → Scaffold ready
2. Phase 3 (US1) → `docker run` works → **MVP ship point**
3. Phase 4 (US2) → `docker compose up` works → Developer DX complete
4. Phase 5 (US3) → Fail-fast confirmed → Ops/CI ready
5. Phase 6 (US4) → Healthcheck declared → Orchestration ready
6. Phase 7 (Polish) → Size check, quickstart sign-off

---

## Notes

- [P] tasks = different files or independent validation steps; no sequencing risk
- Tasks T008–T012, T014–T015, T016–T018, T019–T020 are runtime validation steps; they require a built image or running container, not just file creation
- No automated test suite is required by the spec; validations are manual `docker` CLI commands
- Commit after T003 (scaffold complete), T012 (US1 MVP validated), T013 (compose authored), and T023 (polish done)
- If `docker build` hangs at model download (T008), the most common cause is a missing DNS record for `huggingface.co` inside the builder; verify network access with `--network=host` or a corporate proxy env var
- All env var names, default values, and port numbers are authoritative in `specs/007-docker-oracle-image/data-model.md`

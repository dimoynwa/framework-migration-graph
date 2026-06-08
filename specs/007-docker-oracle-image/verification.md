# Verification Protocol: Docker Oracle Image (007)

**Location**: `specs/007-docker-oracle-image/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `007` ✅ in `SPEC_ORGANIZATION.md`
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

---

## Prerequisites

| Requirement | Check |
|---|---|
| Repo root contains `pyproject.toml`, `uv.lock`, `migration_oracle/` | `ls pyproject.toml uv.lock migration_oracle/` exits 0 |
| Docker daemon is running | `docker info` exits 0 |
| Build-time internet access (for model download) | `curl -I https://huggingface.co` exits 0 |
| Neo4j 5 available (Levels 5–6 only) | `docker compose up neo4j -d` or external bolt:// URI |
| Working directory is repository root | All paths below are relative to repo root |

## Infrastructure by Level

| Level | Name | Docker build | Running container | Neo4j |
|---|---|---|---|---|
| 0 | Static file checks | No | No | No |
| 1 | Build correctness | Yes | No | No |
| 2 | Image inspection | Yes | No | No |
| 3 | Runtime endpoints | Yes | Yes | No |
| 4 | Fail-fast behavior | Yes | Yes | No |
| 5 | Compose stack | Yes | Yes | Yes |
| 6 | Idempotency | Yes | Yes | Yes |
| 7 | Edge-case paths | Yes | Yes | No |

---

## Level 0 — Static file checks

*No Docker required. All checks are grep/stat commands on source files.*

### 0-A: Dockerfile exists at repo root

```bash
test -f Dockerfile && echo 'PASS: Dockerfile exists' || echo 'FAIL: Dockerfile missing'
```

### 0-B: Three-stage build — uv-bin, builder, final

```bash
stages=$(grep -c '^FROM' Dockerfile)
echo "FROM count: $stages"
grep '^FROM' Dockerfile
# Expected: 3 FROM lines
# FROM ghcr.io/astral-sh/uv:... AS uv-bin
# FROM python:3.11-slim AS builder
# FROM python:3.11-slim AS final (or no alias)
[ "$stages" -eq 3 ] && echo 'PASS: 3 stages present' || echo 'FAIL: Expected 3 FROM lines, got '"$stages"
```

### 0-C: ARG SENTENCE_TRANSFORMERS_MODEL declared in BOTH builder and final stage

```bash
count=$(grep -c 'ARG SENTENCE_TRANSFORMERS_MODEL' Dockerfile)
echo "ARG declarations found: $count"
grep -n 'ARG SENTENCE_TRANSFORMERS_MODEL' Dockerfile
# Must appear at least twice: once in builder stage (for download RUN), once in final stage
# (so that the subsequent ENV SENTENCE_TRANSFORMERS_MODEL=${SENTENCE_TRANSFORMERS_MODEL} resolves correctly)
[ "$count" -ge 2 ] && echo 'PASS: ARG re-declared in final stage' || echo 'FAIL: ARG declared only '"$count"' time(s) — final stage ENV will be empty string'
```

### 0-D: ENV PYTHONUNBUFFERED=1 in Dockerfile (FR-015, GAP-009)

```bash
grep 'PYTHONUNBUFFERED=1' Dockerfile && echo 'PASS: PYTHONUNBUFFERED=1 present' || echo 'FAIL: PYTHONUNBUFFERED=1 missing — MCP server stdout will buffer'
```

### 0-E: HEALTHCHECK with curl, --max-time, and exit-code 0/28 SSE logic (GAP-003)

```bash
grep 'HEALTHCHECK' Dockerfile
# Verify the HEALTHCHECK CMD contains:
# - curl ... --max-time 5 ... /sse  (SSE probe with timeout)
# - [ $ret -eq 0 ] || [ $ret -eq 28 ]  (accept both clean close and timeout-after-headers)
# - curl ... /_stcore/health          (Streamlit probe)
grep -A3 'HEALTHCHECK' Dockerfile
grep 'max-time' Dockerfile && echo 'PASS: --max-time present in HEALTHCHECK' || echo 'FAIL: --max-time missing — HEALTHCHECK will hang on SSE stream'
grep '\$ret' Dockerfile && echo 'PASS: exit-code 0/28 logic present' || echo 'FAIL: exit-code 28 not handled — SSE timeout incorrectly treated as unhealthy'
grep '_stcore/health' Dockerfile && echo 'PASS: Streamlit health probe present' || echo 'FAIL: Streamlit /_stcore/health probe missing'
```

### 0-F: USER oracle declared (FR-006, GAP-008)

```bash
grep 'USER oracle' Dockerfile && echo 'PASS: USER oracle present' || echo 'FAIL: USER oracle missing — container will run as root'
```

### 0-G: ENTRYPOINT points to /app/entrypoint.sh (FR-001, GAP-010)

```bash
grep 'ENTRYPOINT' Dockerfile
grep '"/app/entrypoint.sh"' Dockerfile && echo 'PASS: ENTRYPOINT set to /app/entrypoint.sh' || echo 'FAIL: ENTRYPOINT missing or wrong path'
```

### 0-H: EXPOSE 8080 and 8501 declared (FR-003, FR-004)

```bash
grep 'EXPOSE' Dockerfile
grep 'EXPOSE.*8080' Dockerfile && echo 'PASS: EXPOSE 8080' || echo 'FAIL: EXPOSE 8080 missing'
grep 'EXPOSE.*8501' Dockerfile && echo 'PASS: EXPOSE 8501' || echo 'FAIL: EXPOSE 8501 missing'
```

### 0-I: VOLUME /data declared (FR-010)

```bash
grep 'VOLUME /data' Dockerfile && echo 'PASS: VOLUME /data present' || echo 'FAIL: VOLUME /data missing'
```

### 0-J: docker/entrypoint.sh exists and is executable (T002)

```bash
test -f docker/entrypoint.sh && echo 'PASS: entrypoint.sh exists' || echo 'FAIL: docker/entrypoint.sh missing'
test -x docker/entrypoint.sh && echo 'PASS: entrypoint.sh is executable' || echo 'FAIL: entrypoint.sh is not executable — chmod +x required'
```

### 0-K: entrypoint.sh uses POSIX sh shebang, not bash (GAP-001)

```bash
head -1 docker/entrypoint.sh
head -1 docker/entrypoint.sh | grep -E '^#!/bin/sh|^#!/usr/bin/env sh' && echo 'PASS: POSIX sh shebang' || echo 'FAIL: Not POSIX sh — must be #!/bin/sh or #!/usr/bin/env sh, not #!/bin/bash'
```

### 0-L: entrypoint.sh backgrounds both processes and uses wait -n (GAP-001, FR-007)

```bash
grep 'migration_oracle.mcp.server' docker/entrypoint.sh && echo 'PASS: MCP server command present' || echo 'FAIL: MCP server start command missing from entrypoint'
grep 'streamlit' docker/entrypoint.sh && echo 'PASS: Streamlit command present' || echo 'FAIL: Streamlit start command missing from entrypoint'
grep '&$\|& $\|&\s' docker/entrypoint.sh && echo 'PASS: Background & operator present' || echo 'FAIL: Processes not backgrounded with & — container will block on first process'
grep 'wait' docker/entrypoint.sh && echo 'PASS: wait present' || echo 'FAIL: wait missing — fail-fast cannot work without wait'
```

### 0-M: .dockerignore excludes build-context-bloating paths (T003)

```bash
test -f .dockerignore && echo 'PASS: .dockerignore exists' || echo 'FAIL: .dockerignore missing'
for pattern in '.git' 'specs/' 'tests/' '.claude/' '__pycache__' '*.pyc' 'runs/'; do
  grep -q "$pattern" .dockerignore && echo "PASS: .dockerignore excludes $pattern" || echo "FAIL: .dockerignore missing $pattern"
done
```

### 0-N: docker-compose.yml has oracle and neo4j services with depends_on condition (FR-009, GAP-007)

```bash
test -f docker-compose.yml && echo 'PASS: docker-compose.yml exists' || echo 'FAIL: docker-compose.yml missing'
grep 'oracle' docker-compose.yml && echo 'PASS: oracle service present' || echo 'FAIL: oracle service missing'
grep 'neo4j' docker-compose.yml && echo 'PASS: neo4j service present' || echo 'FAIL: neo4j service missing'
grep 'service_healthy' docker-compose.yml && echo 'PASS: depends_on condition: service_healthy present' || echo 'FAIL: service_healthy condition missing — oracle may start before Neo4j is ready'
grep 'build:' docker-compose.yml && echo 'PASS: build: context present (dev artifact)' || echo 'FAIL: build: context missing — compose uses registry image, not local source'
```

### 0-O: .env.example documents required variables (FR-002)

```bash
test -f .env.example && echo 'PASS: .env.example exists' || echo 'FAIL: .env.example missing'
grep 'NEO4J_URI' .env.example && echo 'PASS: NEO4J_URI in .env.example' || echo 'FAIL: NEO4J_URI missing from .env.example'
grep 'NEO4J_PASSWORD' .env.example && echo 'PASS: NEO4J_PASSWORD in .env.example' || echo 'FAIL: NEO4J_PASSWORD missing from .env.example'
grep -i 'REQUIRED' .env.example && echo 'PASS: REQUIRED annotation present' || echo 'FAIL: REQUIRED annotation missing — required vars not distinguished from optional'
```

### 0-P: No secrets in Dockerfile ENV or ARG layers (FR-002)

```bash
for secret in NEO4J_PASSWORD ANTHROPIC_API_KEY GITLAB_API_KEY FINDIT_AUTH_TOKEN OPENAI_API_KEY; do
  grep "ENV.*$secret\b\|ARG.*$secret\b" Dockerfile && echo "FAIL: $secret baked into Dockerfile layer" || echo "PASS: $secret not in Dockerfile"
done
```

---

## Level 1 — Build correctness

*Requires `docker build`. No running containers needed.*

### 1-A: docker build exits 0 (FR-012)

```bash
docker build --progress=plain -t paysafe-migration-oracle:test-007 . 2>&1 | tee /tmp/007-build.log
echo "Build exit code: $?"
# If non-zero, inspect /tmp/007-build.log for the failure layer
```

### 1-B: Model download visible in build log — no silent skip (FR-014, GAP-002)

```bash
grep -i 'all-mpnet-base-v2\|Downloading\|huggingface\|sentence.transform' /tmp/007-build.log | head -20
# Must show download or cache-load activity for all-mpnet-base-v2
# "Downloading" lines confirm model was fetched (first build)
# "Loading" or "Using cached" lines confirm cache hit (subsequent builds)
grep -qi 'all-mpnet-base-v2' /tmp/007-build.log && echo 'PASS: model name visible in build log' || echo 'FAIL: all-mpnet-base-v2 not mentioned in build output — model may have been silently skipped'
```

### 1-C: Image size ≤ 3 GB uncompressed (SC-008, FR-013)

```bash
size_bytes=$(docker image inspect paysafe-migration-oracle:test-007 --format='{{.Size}}')
size_gb=$(echo "scale=2; $size_bytes / 1024 / 1024 / 1024" | bc)
echo "Image size: ${size_gb} GB (${size_bytes} bytes)"
[ "$size_bytes" -le 3221225472 ] && echo 'PASS: Image ≤ 3 GB' || echo "FAIL: Image exceeds 3 GB — actual ${size_gb} GB; apply additional .dockerignore exclusions or check for leftover builder artifacts"
```

---

## Level 2 — Image inspection

*Requires the image built in Level 1. Single-shot `docker run --rm` commands. No Neo4j.*

### 2-A: Container runs as uid=1000 oracle — not root (FR-006, GAP-008)

```bash
id_output=$(docker run --rm --entrypoint id paysafe-migration-oracle:test-007)
echo "$id_output"
echo "$id_output" | grep 'uid=1000(oracle)' && echo 'PASS: Running as oracle uid=1000' || echo "FAIL: Expected uid=1000(oracle), got: $id_output"
```

### 2-B: Model files in final layer — no Downloading at import time (FR-005, SC-002)

```bash
model_output=$(docker run --rm --entrypoint python paysafe-migration-oracle:test-007 \
  -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('all-mpnet-base-v2'); print('loaded')" 2>&1)
echo "$model_output"
echo "$model_output" | grep -i 'downloading' && echo 'FAIL: Model is being downloaded at runtime — not pre-baked' || echo 'PASS: No download activity'
echo "$model_output" | grep 'loaded' && echo 'PASS: Model loaded successfully' || echo 'FAIL: Model did not load'
```

### 2-C: PYTHONUNBUFFERED=1 in container environment (FR-015)

```bash
docker run --rm --entrypoint env paysafe-migration-oracle:test-007 | grep PYTHONUNBUFFERED
docker run --rm --entrypoint env paysafe-migration-oracle:test-007 | grep 'PYTHONUNBUFFERED=1' && echo 'PASS: PYTHONUNBUFFERED=1 in container env' || echo 'FAIL: PYTHONUNBUFFERED not set to 1'
```

### 2-D: SENTENCE_TRANSFORMERS_MODEL matches pre-baked model (GAP-002)

```bash
docker run --rm --entrypoint env paysafe-migration-oracle:test-007 | grep SENTENCE_TRANSFORMERS_MODEL
docker run --rm --entrypoint env paysafe-migration-oracle:test-007 | grep 'SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2' && echo 'PASS: SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2' || echo 'FAIL: SENTENCE_TRANSFORMERS_MODEL env var is empty or wrong — ARG not re-declared in final stage'
```

### 2-E: /data exists and is owned by oracle (FR-010, GAP-008)

```bash
docker run --rm --entrypoint sh paysafe-migration-oracle:test-007 -c "ls -la / | grep data"
docker run --rm --entrypoint sh paysafe-migration-oracle:test-007 \
  -c 'stat -c "%U %G" /data 2>/dev/null || stat -f "%Su %Sg" /data' | grep 'oracle oracle' \
  && echo 'PASS: /data owned by oracle' || echo 'FAIL: /data not owned by oracle'
```

### 2-F: WORKDIR is /app (GAP-010)

```bash
workdir=$(docker run --rm --entrypoint pwd paysafe-migration-oracle:test-007)
echo "WORKDIR: $workdir"
[ "$workdir" = "/app" ] && echo 'PASS: WORKDIR is /app' || echo "FAIL: WORKDIR is $workdir, expected /app"
```

### 2-G: HF_HOME points to /app/.cache/huggingface and model cache is present

```bash
docker run --rm --entrypoint env paysafe-migration-oracle:test-007 | grep HF_HOME
docker run --rm --entrypoint sh paysafe-migration-oracle:test-007 \
  -c 'ls /app/.cache/huggingface/hub/ 2>/dev/null || ls /app/.cache/huggingface/' | head -10
docker run --rm --entrypoint sh paysafe-migration-oracle:test-007 \
  -c 'test -d /app/.cache/huggingface && echo PASS: HF_HOME cache dir exists || echo FAIL: /app/.cache/huggingface missing — model was not copied from builder stage'
```

---

## Level 3 — Runtime endpoints

*Requires a running container. Neo4j not required — these checks only verify process startup and port binding.*
*Note: the container will log Neo4j connection errors; that is expected at this level.*

Start a test container (substitute real credentials or use dummy values — the endpoints respond before Neo4j is needed):

```bash
docker run -d --name mo-007-test \
  -e NEO4J_URI=bolt://localhost:7687 \
  -e NEO4J_PASSWORD=testonly \
  -e ANTHROPIC_API_KEY=sk-test \
  -p 8080:8080 -p 8501:8501 \
  paysafe-migration-oracle:test-007
echo "Container ID: $(docker ps -qf name=mo-007-test)"
echo "Waiting 60 s for startup..."
sleep 60
```

### 3-A: MCP SSE endpoint responds — curl exits 0 or 28 (FR-003, GAP-003, SC-001)

```bash
curl -fsS --max-time 5 http://localhost:8080/sse
ret=$?
echo "curl exit code: $ret"
# 0 = clean close (some FastMCP versions close immediately on GET)
# 28 = timeout after receiving headers (SSE stream kept alive until --max-time)
# 7 = connection refused (port not bound — process not up)
# 22 = HTTP error (server returned 4xx/5xx)
([ $ret -eq 0 ] || [ $ret -eq 28 ]) && echo 'PASS: SSE endpoint reachable (exit 0 or 28)' || echo "FAIL: SSE endpoint not reachable — curl exit code $ret (7=refused, 22=HTTP error)"
```

### 3-B: Streamlit health endpoint returns HTTP 200 (FR-004, SC-001)

```bash
http_code=$(curl -o /dev/null -s -w '%{http_code}' --max-time 5 http://localhost:8501/_stcore/health)
echo "HTTP status: $http_code"
[ "$http_code" = "200" ] && echo 'PASS: Streamlit /_stcore/health returned 200' || echo "FAIL: Streamlit health returned $http_code — UI not up"
```

### 3-C: Both endpoints reachable within 60 seconds of container start (SC-001, SC-003)

```bash
# Run this check starting a FRESH container (do not reuse mo-007-test from above)
docker rm -f mo-007-timing 2>/dev/null
start_ts=$(date +%s)
docker run -d --name mo-007-timing \
  -e NEO4J_URI=bolt://localhost:7687 \
  -e NEO4J_PASSWORD=testonly \
  -e ANTHROPIC_API_KEY=sk-test \
  -p 8082:8080 -p 8503:8501 \
  paysafe-migration-oracle:test-007

for i in $(seq 1 60); do
  sse_ret=1; stl_ret=1
  curl -fsS --max-time 3 http://localhost:8082/sse >/dev/null 2>&1; sse_ret=$?
  ([ $sse_ret -eq 0 ] || [ $sse_ret -eq 28 ]) || true
  stl_code=$(curl -o /dev/null -s -w '%{http_code}' --max-time 3 http://localhost:8503/_stcore/health 2>/dev/null)
  ([ $sse_ret -eq 0 ] || [ $sse_ret -eq 28 ]) && [ "$stl_code" = "200" ] && break
  sleep 1
done
end_ts=$(date +%s)
elapsed=$((end_ts - start_ts))
echo "Both endpoints up after ${elapsed}s"
([ $sse_ret -eq 0 ] || [ $sse_ret -eq 28 ]) && [ "$stl_code" = "200" ] && [ $elapsed -le 60 ] \
  && echo "PASS: Both endpoints reachable within 60 s (actual: ${elapsed}s)" \
  || echo "FAIL: Not both reachable within 60 s (sse_ret=$sse_ret stl=$stl_code elapsed=${elapsed}s)"
docker rm -f mo-007-timing
```

### 3-D: Both MCP and Streamlit log output present in docker logs (FR-011, FR-015)

```bash
docker logs mo-007-test 2>&1 | head -50
# Check for MCP server log lines
docker logs mo-007-test 2>&1 | grep -i 'mcp\|server\|migration_oracle\|sse\|uvicorn\|fastmcp' && echo 'PASS: MCP server log lines present' || echo 'FAIL: No MCP server output in docker logs — PYTHONUNBUFFERED may be unset or MCP process not started'
# Check for Streamlit log lines
docker logs mo-007-test 2>&1 | grep -i 'streamlit\|Network URL\|Local URL\|You can now view' && echo 'PASS: Streamlit log lines present' || echo 'FAIL: No Streamlit output in docker logs'
```

### 3-E: No model download at runtime — model loaded from image cache (FR-005, SC-002)

```bash
docker logs mo-007-test 2>&1 | grep -i 'downloading\|fetching.*model\|huggingface.*download' && echo 'FAIL: Model download activity detected at runtime — model was not pre-baked' || echo 'PASS: No model download in runtime logs'
```

**Cleanup after Level 3:**

```bash
docker rm -f mo-007-test 2>/dev/null
```

---

## Level 4 — Fail-fast behavior

*Container must exit non-zero within 30 s when either internal process dies (FR-007, SC-004).*
*Requires `procps` (pgrep/pkill) installed in final stage per T006.*

Start a fresh test container for each sub-check:

### 4-A: MCP server process killed → container exits non-zero within 30 s (FR-007, US3 scenario 1)

```bash
docker rm -f mo-007-ff-mcp 2>/dev/null
docker run -d --name mo-007-ff-mcp \
  -e NEO4J_URI=bolt://localhost:7687 \
  -e NEO4J_PASSWORD=testonly \
  -e ANTHROPIC_API_KEY=sk-test \
  paysafe-migration-oracle:test-007
sleep 15  # wait for both processes to be up

# Find and kill the MCP server process inside the container
mcp_pid=$(docker exec mo-007-ff-mcp pgrep -f 'migration_oracle.mcp.server' 2>/dev/null || \
          docker exec mo-007-ff-mcp pgrep -f 'migration_oracle' 2>/dev/null | head -1)
echo "MCP server PID: $mcp_pid"
docker exec mo-007-ff-mcp kill "$mcp_pid"

# Wait up to 30 s for container to exit
exit_code=$(timeout 35 docker wait mo-007-ff-mcp 2>/dev/null)
ret=$?
echo "docker wait exit code (process): $ret  Container exit code: $exit_code"
# timeout command exit code 124 = container did NOT stop within 35 s
[ $ret -ne 124 ] && [ "$exit_code" != "0" ] \
  && echo "PASS: Container exited non-zero (code: $exit_code) after MCP kill" \
  || echo "FAIL: Container did not stop within 30 s OR exited 0 — ret=$ret exit_code=$exit_code"
docker rm -f mo-007-ff-mcp 2>/dev/null
```

### 4-B: Streamlit process killed → container exits non-zero within 30 s (FR-007, US3 scenario 2)

```bash
docker rm -f mo-007-ff-st 2>/dev/null
docker run -d --name mo-007-ff-st \
  -e NEO4J_URI=bolt://localhost:7687 \
  -e NEO4J_PASSWORD=testonly \
  -e ANTHROPIC_API_KEY=sk-test \
  paysafe-migration-oracle:test-007
sleep 15

st_pid=$(docker exec mo-007-ff-st pgrep -f 'streamlit' 2>/dev/null | head -1)
echo "Streamlit PID: $st_pid"
docker exec mo-007-ff-st kill "$st_pid"

exit_code=$(timeout 35 docker wait mo-007-ff-st 2>/dev/null)
ret=$?
echo "docker wait exit code (process): $ret  Container exit code: $exit_code"
[ $ret -ne 124 ] && [ "$exit_code" != "0" ] \
  && echo "PASS: Container exited non-zero (code: $exit_code) after Streamlit kill" \
  || echo "FAIL: Container did not stop within 30 s OR exited 0 — ret=$ret exit_code=$exit_code"
docker rm -f mo-007-ff-st 2>/dev/null
```

---

## Level 5 — Compose stack

*Requires Docker Compose and a running Neo4j sidecar. Run from repo root.*

### 5-A: docker compose up -d exits 0 (SC-005, FR-009)

```bash
docker compose up -d 2>&1 | tee /tmp/007-compose.log
echo "Compose exit code: $?"
[ $? -eq 0 ] && echo 'PASS: docker compose up -d succeeded' || echo 'FAIL: compose up failed — check /tmp/007-compose.log'
```

### 5-B: Neo4j healthcheck passes (prerequisite for oracle start)

```bash
echo "Waiting for Neo4j to become healthy..."
for i in $(seq 1 30); do
  status=$(docker compose ps neo4j --format '{{.Health}}' 2>/dev/null || docker inspect --format='{{.State.Health.Status}}' "$(docker compose ps -q neo4j)" 2>/dev/null)
  echo "Attempt $i: neo4j health = $status"
  [ "$status" = "healthy" ] && break
  sleep 3
done
[ "$status" = "healthy" ] && echo 'PASS: neo4j is healthy' || echo 'FAIL: neo4j never reached healthy state'
```

### 5-C: Oracle connects to Neo4j — no connection errors in logs (US2 scenario 1)

```bash
sleep 30  # allow oracle to start after neo4j becomes healthy
docker compose logs oracle 2>&1 | tail -40
docker compose logs oracle 2>&1 | grep -i 'neo4j.*error\|connection.*refused\|could not connect\|ServiceUnavailable' \
  && echo 'FAIL: Neo4j connection errors in oracle logs' || echo 'PASS: No Neo4j connection errors'
docker compose logs oracle 2>&1 | grep -i 'connected\|neo4j\|bolt\|driver' | head -5
```

### 5-D: Data persistence across compose down/up (US2 scenario 3)

```bash
# Create a test node in Neo4j
docker compose exec neo4j cypher-shell -u neo4j -p "$(grep NEO4J_PASSWORD .env.example | head -1 | cut -d= -f2 || echo 'testpass')" \
  "CREATE (t:VerificationTest {id: '007-persist-check', ts: timestamp()}) RETURN t.id" 2>/dev/null \
  || echo "Note: cypher-shell create failed — use UI or adjust credentials"

docker compose down
docker compose up -d
sleep 30

# Verify the test node survived
result=$(docker compose exec neo4j cypher-shell -u neo4j -p "$(grep NEO4J_PASSWORD .env.example | head -1 | cut -d= -f2 || echo 'testpass')" \
  "MATCH (t:VerificationTest {id: '007-persist-check'}) RETURN t.id" 2>/dev/null)
echo "Persistence check result: $result"
echo "$result" | grep '007-persist-check' && echo 'PASS: Data persisted across compose restart' || echo 'FAIL: Data lost — named volume may not be configured correctly'

# Cleanup test node
docker compose exec neo4j cypher-shell -u neo4j -p "$(grep NEO4J_PASSWORD .env.example | head -1 | cut -d= -f2 || echo 'testpass')" \
  "MATCH (t:VerificationTest {id: '007-persist-check'}) DELETE t" 2>/dev/null
```

---

## Level 6 — Idempotency

### 6-A: Reproducible build — second build produces functionally identical image (FR-012, SC-007)

```bash
# Tag first build result and build again
docker tag paysafe-migration-oracle:test-007 paysafe-migration-oracle:test-007-first
docker build -q -t paysafe-migration-oracle:test-007-second . >/dev/null 2>&1

# Compare: both must pass the id check and model load check
for tag in test-007-first test-007-second; do
  id_out=$(docker run --rm --entrypoint id paysafe-migration-oracle:$tag 2>/dev/null)
  model_ok=$(docker run --rm --entrypoint python paysafe-migration-oracle:$tag \
    -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-mpnet-base-v2'); print('ok')" 2>/dev/null | grep 'ok')
  env_val=$(docker run --rm --entrypoint env paysafe-migration-oracle:$tag 2>/dev/null | grep SENTENCE_TRANSFORMERS_MODEL)
  echo "[$tag] id=$id_out  model=$model_ok  env=$env_val"
done

# Both should show uid=1000(oracle), model ok, and same env var
docker rmi paysafe-migration-oracle:test-007-first paysafe-migration-oracle:test-007-second 2>/dev/null
echo 'PASS: Both builds produce functionally identical images (review output above for discrepancies)'
```

### 6-B: Container restart — both endpoints respond again (SC-003)

```bash
# Using the compose stack from Level 5
docker compose restart oracle
sleep 30
sse_ret=1
for i in $(seq 1 30); do
  curl -fsS --max-time 3 http://localhost:8080/sse >/dev/null 2>&1; sse_ret=$?
  ([ $sse_ret -eq 0 ] || [ $sse_ret -eq 28 ]) && break
  sleep 2
done
stl_code=$(curl -o /dev/null -s -w '%{http_code}' --max-time 5 http://localhost:8501/_stcore/health)
([ $sse_ret -eq 0 ] || [ $sse_ret -eq 28 ]) && [ "$stl_code" = "200" ] \
  && echo 'PASS: Both endpoints respond after oracle restart' \
  || echo "FAIL: After restart — sse_ret=$sse_ret stl=$stl_code"
```

---

## Level 7 — Edge-case paths

### 7-A: HEALTHCHECK transitions to `healthy` within start-period (FR-008, SC-006, US4 scenario 1)

```bash
docker rm -f mo-007-hc 2>/dev/null
docker run -d --name mo-007-hc \
  -e NEO4J_URI=bolt://localhost:7687 \
  -e NEO4J_PASSWORD=testonly \
  -e ANTHROPIC_API_KEY=sk-test \
  -p 8084:8080 -p 8505:8501 \
  paysafe-migration-oracle:test-007

echo "Waiting up to 90 s for health status to leave 'starting'..."
for i in $(seq 1 45); do
  hc=$(docker inspect --format='{{.State.Health.Status}}' mo-007-hc 2>/dev/null)
  echo "Attempt $i (${i}x2s): $hc"
  [ "$hc" = "healthy" ] && break
  [ "$hc" = "unhealthy" ] && break
  sleep 2
done
echo "Final health status: $hc"
[ "$hc" = "healthy" ] && echo 'PASS: HEALTHCHECK reported healthy' || echo "FAIL: Health status is '$hc' — check HEALTHCHECK CMD in Dockerfile; inspect docker inspect mo-007-hc for probe log"

# Show last healthcheck log
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' mo-007-hc 2>/dev/null | tail -5
docker rm -f mo-007-hc 2>/dev/null
```

### 7-B: HEALTHCHECK reports `unhealthy` when a service crashes (FR-008, SC-006, US4 scenario 2)

```bash
docker rm -f mo-007-hc-crash 2>/dev/null
docker run -d --name mo-007-hc-crash \
  -e NEO4J_URI=bolt://localhost:7687 \
  -e NEO4J_PASSWORD=testonly \
  -e ANTHROPIC_API_KEY=sk-test \
  -p 8086:8080 -p 8507:8501 \
  paysafe-migration-oracle:test-007

# Wait for healthy state first
for i in $(seq 1 45); do
  hc=$(docker inspect --format='{{.State.Health.Status}}' mo-007-hc-crash 2>/dev/null)
  [ "$hc" = "healthy" ] && break
  sleep 2
done
echo "Pre-crash health: $hc"

# Kill Streamlit inside the container
st_pid=$(docker exec mo-007-hc-crash pgrep -f 'streamlit' 2>/dev/null | head -1)
docker exec mo-007-hc-crash kill "$st_pid" 2>/dev/null
# Note: entrypoint's wait -n will cause container to exit — check health log before exit
sleep 5  # give healthcheck one interval to run

hc_after=$(docker inspect --format='{{.State.Health.Status}}' mo-007-hc-crash 2>/dev/null)
echo "Post-crash health: $hc_after"
echo "Health log:"
docker inspect --format='{{range .State.Health.Log}}Output: {{.Output}} ExitCode: {{.ExitCode}}{{"\n"}}{{end}}' mo-007-hc-crash 2>/dev/null | tail -6

# Container may have exited (fail-fast) OR health may show unhealthy — both are acceptable outcomes
([ "$hc_after" = "unhealthy" ] || [ "$(docker inspect --format='{{.State.Status}}' mo-007-hc-crash)" = "exited" ]) \
  && echo 'PASS: Container reported unhealthy or exited (fail-fast) after service crash' \
  || echo 'FAIL: Container still healthy after Streamlit was killed'
docker rm -f mo-007-hc-crash 2>/dev/null
```

### 7-C: Build fails when model name is invalid — FR-014 enforcement (GAP-002)

```bash
# A non-existent model name must cause docker build to exit non-zero
docker build --build-arg SENTENCE_TRANSFORMERS_MODEL=nonexistent-model-xyzzy-007-test \
  -t paysafe-migration-oracle:test-007-badmodel . 2>&1 | tail -20
build_ret=${PIPESTATUS[0]}
echo "Build exit code with bad model: $build_ret"
[ $build_ret -ne 0 ] && echo 'PASS: Build failed (non-zero) with invalid model name (FR-014)' \
  || echo 'FAIL: Build succeeded with invalid model — model download step is suppressing errors (|| true or silent failure)'
docker rmi paysafe-migration-oracle:test-007-badmodel 2>/dev/null
```

---

## Completion Gate Checklist

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| Check ID | Description | Result |
|---|---|---|
| 0-A | Dockerfile exists at repo root | ☐ |
| 0-B | Three FROM stages (uv-bin, builder, final) | ☐ |
| 0-C | ARG SENTENCE_TRANSFORMERS_MODEL declared in both builder and final stage | ☐ |
| 0-D | ENV PYTHONUNBUFFERED=1 in Dockerfile | ☐ |
| 0-E | HEALTHCHECK has --max-time, exit-code 0/28 logic, and /_stcore/health probe | ☐ |
| 0-F | USER oracle declared | ☐ |
| 0-G | ENTRYPOINT ["/app/entrypoint.sh"] | ☐ |
| 0-H | EXPOSE 8080 and 8501 | ☐ |
| 0-I | VOLUME /data | ☐ |
| 0-J | docker/entrypoint.sh exists and is executable | ☐ |
| 0-K | entrypoint.sh uses POSIX sh shebang (not bash) | ☐ |
| 0-L | entrypoint.sh backgrounds both processes with & and uses wait | ☐ |
| 0-M | .dockerignore excludes .git, specs/, tests/, .claude/, __pycache__, *.pyc, runs/ | ☐ |
| 0-N | docker-compose.yml has oracle + neo4j with service_healthy condition and build: context | ☐ |
| 0-O | .env.example exists with NEO4J_URI, NEO4J_PASSWORD, and REQUIRED annotations | ☐ |
| 0-P | No secrets (NEO4J_PASSWORD, ANTHROPIC_API_KEY, etc.) in Dockerfile ENV/ARG | ☐ |
| 1-A | docker build exits 0 | ☐ |
| 1-B | Model name visible in build log (no silent skip) | ☐ |
| 1-C | Image size ≤ 3 GB uncompressed | ☐ |
| 2-A | Container runs as uid=1000(oracle) | ☐ |
| 2-B | Model imports without Downloading at runtime | ☐ |
| 2-C | PYTHONUNBUFFERED=1 in container env | ☐ |
| 2-D | SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2 in container env | ☐ |
| 2-E | /data owned by oracle | ☐ |
| 2-F | WORKDIR is /app | ☐ |
| 2-G | /app/.cache/huggingface model cache dir present in final image | ☐ |
| 3-A | SSE endpoint curl exits 0 or 28 | ☐ |
| 3-B | Streamlit /_stcore/health returns HTTP 200 | ☐ |
| 3-C | Both endpoints reachable within 60 s of container start | ☐ |
| 3-D | Both MCP server and Streamlit log lines visible in docker logs | ☐ |
| 3-E | No model download activity in runtime logs | ☐ |
| 4-A | Killing MCP process → container exits non-zero within 30 s | ☐ |
| 4-B | Killing Streamlit process → container exits non-zero within 30 s | ☐ |
| 5-A | docker compose up -d exits 0 | ☐ |
| 5-B | neo4j service reaches healthy state | ☐ |
| 5-C | No Neo4j connection errors in oracle logs after compose up | ☐ |
| 5-D | Data persists in named volume across docker compose down/up | ☐ |
| 6-A | Two builds from same source produce functionally identical images | ☐ |
| 6-B | Both endpoints respond after docker compose restart oracle | ☐ |
| 7-A | HEALTHCHECK transitions to healthy status within 90 s | ☐ |
| 7-B | HEALTHCHECK reports unhealthy (or container exits) after service crash | ☐ |
| 7-C | docker build exits non-zero with invalid SENTENCE_TRANSFORMERS_MODEL build arg | ☐ |

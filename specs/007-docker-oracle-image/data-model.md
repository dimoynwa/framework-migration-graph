# Data Model: Docker Oracle Image (007)

**Branch**: `007-docker-oracle-image` | **Date**: 2026-06-08

---

## Build Arguments (ARG)

Build arguments are consumed only during `docker build`. They are not available at runtime unless explicitly propagated to `ENV`.

| ARG | Default | Purpose |
|-----|---------|---------|
| `SENTENCE_TRANSFORMERS_MODEL` | `all-mpnet-base-v2` | Name of the sentence-transformers model to download and cache in the builder stage. Must match the runtime `ENV` of the same name. Changing this value requires a full rebuild. |
| `UV_VERSION` | `0.5` | Minor-version tag of the `ghcr.io/astral-sh/uv` image used to source the `uv` binary. Pin to a minor version for reproducibility. |

---

## Runtime Environment Variables

### Required (container fails to start without these)

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `NEO4J_URI` | *(none — required)* | MCP server, Streamlit | Bolt URI of the Neo4j instance, e.g. `bolt://neo4j:7687` |
| `NEO4J_PASSWORD` | *(none — required)* | MCP server, Streamlit | Password for the Neo4j user |

### Optional — Graph Database

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `NEO4J_USERNAME` | `neo4j` | MCP server, Streamlit | Neo4j username |
| `SSL_VERIFY` | `true` | MCP server | Whether to verify TLS certificates on outbound HTTP calls (`false` / `0` to disable) |

### Optional — AI Model Provider

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `MODEL_PROVIDER` | `anthropic` | MCP server | LLM provider: `anthropic`, `openai`, `ollama`, `litellm` |
| `MODEL_ID` | `""` (provider default) | MCP server | Override the LLM model ID, e.g. `claude-opus-4-8` |
| `ANTHROPIC_API_KEY` | `""` | MCP server | Anthropic API key; required when `MODEL_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | `""` | MCP server | OpenAI API key; required when `MODEL_PROVIDER=openai` |
| `OPENAI_BASE_URL` | `""` | MCP server | Custom OpenAI-compatible base URL |
| `LITELLM_BASE_URL` | `""` | MCP server | LiteLLM proxy base URL |
| `OLLAMA_HOST` | `http://localhost:11434` | MCP server | Ollama server address |
| `AWS_REGION` | `eu-central-1` | MCP server | AWS region for Bedrock model access |

### Optional — External Integrations

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `GITHUB_TOKEN` | `""` | MCP server | GitHub token for release note extraction |
| `GITLAB_API_KEY` | `""` | MCP server | GitLab API key for changelog access |
| `FINDIT_AUTH_TOKEN` | `""` | MCP server | Paysafe FindIt service authentication token |
| `FINDIT_BASE_URL` | `https://findit-api.icd.paysafe.cloud` | MCP server | Paysafe FindIt API base URL |

### Optional — MCP Server

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `MCP_TRANSPORT` | `sse` (overridden in image) | MCP server | Transport protocol. Must be `sse` in the container; `stdio` and `streamable-http` are out of scope. |
| `MCP_HOST` | `0.0.0.0` | MCP server | Interface to bind the SSE server. `0.0.0.0` exposes on all interfaces inside the container. |
| `MCP_PORT` | `8080` | MCP server, health-check | Port the MCP SSE server listens on inside the container. |
| `MCP_STATELESS_HTTP` | `false` | MCP server | Enable stateless HTTP mode (not applicable for SSE transport; leave as default). |

### Optional — Streamlit UI

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `STREAMLIT_SERVER_PORT` | `8501` | Streamlit | Port Streamlit listens on inside the container. |

### Optional — Embedding Model

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `SENTENCE_TRANSFORMERS_MODEL` | `all-mpnet-base-v2` | MCP server, Streamlit | Runtime model name. **Must match the value of the `SENTENCE_TRANSFORMERS_MODEL` build ARG** used when the image was built. Changing this at runtime without a matching rebuild causes a cold download on first use, violating FR-005. |
| `HF_HOME` | `/app/.cache/huggingface` | Both | Root directory for HuggingFace/sentence-transformers model cache. Pre-populated at build time. Must be owned by the `oracle` user. |

### Optional — Observability & Tuning

| Variable | Default | Consumed By | Purpose |
|----------|---------|-------------|---------|
| `LOG_LEVEL` | `INFO` | MCP server | Python logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ARTIFACT_CACHE_DIR` | `./artifacts` | MCP server | Local directory for extracted migration artifact caching |
| `EXTRACTION_RATE_LIMIT_RETRIES` | `3` | MCP server | Max retries on rate-limited extraction requests |
| `EXTRACTION_RETRY_BASE_DELAY` | `2.0` | MCP server | Base backoff delay in seconds for extraction retries |
| `JIRA_MAX_CONCURRENT` | `4` | MCP server | Max concurrent Jira API requests |
| `REDHAT_DOCS_DELAY_SEC` | `2.0` | MCP server | Delay between Red Hat docs scrape requests |
| `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` | `0.68` | MCP server | Fuzzy match threshold for FindIt service name resolution |
| `JBOSS_SKIP_PRERELEASE` | `1` | MCP server | Skip pre-release versions when scanning JBoss/WildFly changelogs |
| `SPRING_INCLUDE_PRERELEASE` | `1` | MCP server | Include pre-release versions when scanning Spring changelogs |
| `PYTHONUNBUFFERED` | `1` (set in image) | MCP server | Forces unbuffered stdout/stderr. Pre-set in image `ENV`; do not override. |

---

## Volume Mount Points

| Mount Path | Purpose | Notes |
|------------|---------|-------|
| `/data` | Runtime data injection — e.g. custom connection config, CA certificates | Owned by `oracle:oracle` (uid 1000). Optional; container runs without it. |

---

## Exposed Ports

| Port | Protocol | Service | Configurable via |
|------|----------|---------|-----------------|
| `8080` | TCP / HTTP SSE | MCP SSE server | `MCP_PORT` env var |
| `8501` | TCP / HTTP | Streamlit UI | `STREAMLIT_SERVER_PORT` env var |

---

## Non-Root User Contract

| Attribute | Value |
|-----------|-------|
| Username | `oracle` |
| UID | `1000` |
| GID | `1000` |
| Home dir | `/app` |
| Directories owned | `/app`, `/app/.cache`, `/data` |

---

## Key Entities (build-time)

### Builder Stage
- Inputs: `pyproject.toml`, `uv.lock`, `ARG SENTENCE_TRANSFORMERS_MODEL`
- Outputs: `/app/.venv` (full dependency tree, no dev deps), `/app/.cache/huggingface` (pre-baked model)
- Tooling present: `uv`, `gcc`, build headers (NOT copied to final stage)

### Final Stage
- Inputs from builder: `/app/.venv`, `/app/.cache/huggingface`
- Inputs from source: `migration_oracle/` package, `docker/entrypoint.sh`
- Runtime user: `oracle` (uid 1000)
- Declared volumes: `/data`
- Declared ports: `8080`, `8501`

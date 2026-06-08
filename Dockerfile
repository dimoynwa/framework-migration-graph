# Stage 1 — uv binary source
FROM ghcr.io/astral-sh/uv:0.5 AS uv-bin

# Stage 2 — builder: installs deps and pre-bakes the embedding model
FROM python:3.11-slim AS builder

COPY --from=uv-bin /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV HF_HOME=/app/.cache/huggingface

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

# uv.lock pins the CUDA-linked torch build, which pulls in nvidia-* CUDA
# runtimes (~2.9 GB) and triton (~660 MB). Replace torch with the CPU-only
# wheel, then remove the now-orphaned GPU packages and other inference-unused
# packages (sympy, cuda-python, package test dirs) to minimise the venv copy.
RUN SP=/app/.venv/lib/python3.11/site-packages \
    && VIRTUAL_ENV=/app/.venv uv pip install torch \
         --index-url https://download.pytorch.org/whl/cpu \
         --reinstall --quiet \
    && rm -rf "${SP}/nvidia" "${SP}/triton" "${SP}/cuda" \
    && find "${SP}" -maxdepth 1 \( \
         -name 'nvidia_*.dist-info' -o \
         -name 'triton*.dist-info' -o \
         -name 'cuda*.dist-info' \
       \) -exec rm -rf {} + \
    && find "${SP}" -maxdepth 3 -type d -name 'tests' -exec rm -rf {} + 2>/dev/null || true \
    && find "${SP}" -maxdepth 3 -type d -name 'test' -exec rm -rf {} + 2>/dev/null || true

ARG SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2
RUN /app/.venv/bin/python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('${SENTENCE_TRANSFORMERS_MODEL}')"

COPY migration_oracle/ ./migration_oracle/

# Stage 3 — final: minimal runtime image
FROM python:3.11-slim AS final

# Re-declare ARG so ${SENTENCE_TRANSFORMERS_MODEL} resolves in the ENV below.
# ARG values do not propagate between stages — omitting this silently bakes
# ENV SENTENCE_TRANSFORMERS_MODEL= (empty string) into the image.
ARG SENTENCE_TRANSFORMERS_MODEL=all-mpnet-base-v2

# System: curl for health-check, procps for pgrep/pkill (fail-fast validation)
RUN apt-get update && apt-get install -y --no-install-recommends curl procps \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN addgroup --system --gid 1000 oracle \
    && adduser --system --uid 1000 --gid 1000 --no-create-home oracle

# Copy virtualenv and model cache from builder with oracle ownership in one
# layer — avoids a separate chown layer that would double the data on disk.
COPY --chown=oracle:oracle --from=builder /app/.venv /app/.venv
COPY --chown=oracle:oracle --from=builder /app/.cache /app/.cache

WORKDIR /app

COPY --chown=oracle:oracle migration_oracle/ ./migration_oracle/

COPY --chown=oracle:oracle docker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

RUN mkdir -p /data && chown oracle:oracle /data

ENV PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8080 \
    STREAMLIT_SERVER_PORT=8501 \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_MODEL=${SENTENCE_TRANSFORMERS_MODEL} \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8080 8501

VOLUME /data

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS --max-time 5 http://127.0.0.1:${MCP_PORT:-8080}/sse; ret=$?; \
      ([ $ret -eq 0 ] || [ $ret -eq 28 ]) && \
      curl -fsS --max-time 5 http://127.0.0.1:${STREAMLIT_SERVER_PORT:-8501}/_stcore/health

USER oracle

ENTRYPOINT ["/app/entrypoint.sh"]

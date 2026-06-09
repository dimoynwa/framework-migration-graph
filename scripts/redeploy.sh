#!/usr/bin/env bash
set -euo pipefail

IMAGE="paysafe-migration-oracle:latest"
CONTAINER="oracle-test"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"

# 1. Stop & remove all containers from this image
echo "Stopping ${CONTAINER}..."
docker stop "${CONTAINER}" 2>/dev/null || true

for id in $(docker ps -aq --filter "ancestor=${IMAGE}"); do
    echo "Removing container ${id}..."
    docker rm -f "${id}"
done

# 2. Rebuild
echo "Building ${IMAGE}..."
docker build -t "${IMAGE}" "${PROJECT_ROOT}"

# 3. Start
echo "Starting ${CONTAINER}..."
docker run -d \
    --name "${CONTAINER}" \
    -p 8080:8080 \
    -p 8501:8501 \
    --env-file "${ENV_FILE}" \
    -e NEO4J_URI=bolt://host.docker.internal:7687 \
    -v "${PROJECT_ROOT}/runs:/app/runs:ro" \
    "${IMAGE}"

# 4. Wait for healthy
echo "Waiting for health check (up to 60s)..."
for i in $(seq 1 30); do
    status=$(docker inspect --format='{{.State.Health.Status}}' "${CONTAINER}" 2>/dev/null || echo "starting")
    if [ "${status}" = "healthy" ]; then
        echo "Container is healthy."
        echo "  MCP:       http://localhost:8080/sse"
        echo "  Streamlit: http://localhost:8501"
        exit 0
    fi
    sleep 2
done

echo "Container did not become healthy within 60s -- check logs:"
echo "  docker logs ${CONTAINER}"
exit 1

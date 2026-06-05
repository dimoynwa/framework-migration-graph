#!/usr/bin/env bash
# RAW-only extraction runs (no filter/entity LLM, no graph population).
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
source .env
set +a

export JBOSS_SKIP_PRERELEASE=0
export SPRING_INCLUDE_PRERELEASE=1
export MODEL_PROVIDER=anthropic
export LOG_LEVEL=INFO

CLI=(uv run migration-oracle export-extract-populate-framework --extract-only --force-extract)

run() {
  local framework="$1" from="$2" to="$3"
  shift 3
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) START ${framework} ${from} -> ${to} ==="
  "${CLI[@]}" --framework "$framework" "$@" "$from" "$to"
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) DONE  ${framework} ${from} -> ${to} ==="
}

echo "Angular extractions..."
run angular 18.0.0 19.0.0
run angular 19.0.0 20.0.0
run angular 20.0.0 21.0.0
run angular 21.0.0 22.0.0

echo "Spring Boot extractions..."
run spring-boot 3.3.0 3.4.0
run spring-boot 3.4.0 3.5.0
run spring-boot 3.5.0 4.0.0
# 4.1.0 GA is not on Maven yet; extract through latest 4.1 prerelease (RC1).
run spring-boot 4.0.0 4.1.0-RC1 --output-md runs/raw/spring-boot-4.0.0-to-4.1.0-changes.md

echo "WildFly extractions..."
pairs=(
  "28.0.0 29.0.0"
  "29.0.0 30.0.0"
  "30.0.0 31.0.0"
  "31.0.0 32.0.0"
  "32.0.0 33.0.0"
  "33.0.0 34.0.0"
  "34.0.0 35.0.0"
  "35.0.0 36.0.0"
  "36.0.0 37.0.0"
  "37.0.0 38.0.0"
  "38.0.0 39.0.0"
  "39.0.0 40.0.0"
)
for pair in "${pairs[@]}"; do
  from="${pair%% *}"
  to="${pair##* }"
  run wildfly "$from" "$to"
done

echo "ALL RAW EXTRACTIONS COMPLETE"

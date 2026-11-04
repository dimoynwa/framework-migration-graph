#!/usr/bin/env bash
# Spring Boot patch-level ingestion.
#
# One hop per released version (3.1.0 → 3.1.1 → … → 3.2.0), with its own raw /
# filtered / entities artifacts and its own Version node carrying only the
# changes documented for that release.
#
# Usage:
#   scripts/run_spring_boot_patch_ingest.sh                      # extract-only, default ranges
#   scripts/run_spring_boot_patch_ingest.sh full                 # + filter LLM, entity LLM, graph
#   scripts/run_spring_boot_patch_ingest.sh full "3.1.0 3.2.0"   # explicit minor ranges
#   MODE=full HOP_GRANULARITY=minor scripts/run_spring_boot_patch_ingest.sh
#   SPRING_INCLUDE_PRERELEASE=1 scripts/run_spring_boot_patch_ingest.sh extract-only "4.0.9 4.1.0-RC1"
#
# Cost note: each hop is one filter LLM call plus one entity LLM call, so a
# minor line with 13 patch releases costs ~13x the calls of the old one-shot
# range run. --skip-existing keeps re-runs cheap.
#
# Re-ingesting a minor line that was previously ingested as a single coarse
# range leaves the old coarse Version node (e.g. 3.4.0) in the graph next to the
# new patch nodes, so a range query surfaces both. Delete the coarse node first:
#   MATCH (v:Version {framework: 'Spring Boot', version: '3.4.0'}) DETACH DELETE v
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
source .env
set +a

# Default to GA-only steps. Milestone/RC builds are supported (4.1.0-M1 → … →
# 4.1.0-RC1 each become a hop and a Version node sorting below the GA release
# they precede); set SPRING_INCLUDE_PRERELEASE=1 to include them.
export SPRING_INCLUDE_PRERELEASE="${SPRING_INCLUDE_PRERELEASE:-0}"
export MODEL_PROVIDER="${MODEL_PROVIDER:-anthropic}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

MODE="${1:-extract-only}"
case "$MODE" in
  extract-only|full) shift ;;
  *) echo "unknown mode '$MODE' (expected: extract-only | full)" >&2; exit 2 ;;
esac

RANGES=("$@")
if [ "${#RANGES[@]}" -eq 0 ]; then
  RANGES=(
    "3.1.0 3.2.0"
    "3.2.0 3.3.0"
    "3.3.0 3.4.0"
    "3.4.0 3.5.0"
    "3.5.0 4.0.0"
  )
fi

CLI=(
  uv run migration-oracle export-extract-populate-framework
  --framework spring-boot
  --hop-granularity "${HOP_GRANULARITY:-patch}"
  --hop-by-hop
  --skip-existing
)
if [ "$MODE" = "extract-only" ]; then
  CLI+=(--extract-only)
fi

for range in "${RANGES[@]}"; do
  from="${range%% *}"
  to="${range##* }"
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) spring-boot ${from} -> ${to} (${MODE}) ==="
  "${CLI[@]}" "$from" "$to"
done

echo "ALL SPRING BOOT PATCH-LEVEL RUNS COMPLETE"

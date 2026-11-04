#!/usr/bin/env bash
# RAW-only (no LLM) re-extraction to verify spec 021 GitHub enrichment.
#
# Re-runs upstream extraction with --extract-only, so no filter LLM, no entity
# LLM and no graph writes happen; every hop still goes through the GitHub
# issue/commit enrichment added by spec 021. Overwrites runs/raw/ in place, so
# pass --force-extract semantics below.
#
# Usage:
#   scripts/run_raw_enrichment_check.sh                  # default scope below
#   scripts/run_raw_enrichment_check.sh spring-boot      # one framework only
#   scripts/run_raw_enrichment_check.sh angular
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
source .env
set +a

export SPRING_INCLUDE_PRERELEASE="${SPRING_INCLUDE_PRERELEASE:-0}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"
# Enrichment gates (default true in config; stated here so a run is self-describing).
export SPRING_BOOT_GITHUB_ENRICHMENT="${SPRING_BOOT_GITHUB_ENRICHMENT:-true}"
export ANGULAR_GITHUB_ENRICHMENT="${ANGULAR_GITHUB_ENRICHMENT:-true}"

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "GITHUB_TOKEN is empty — extraction will run but rows stay unenriched." >&2
fi

CLI=(
  ./.venv/bin/migration-oracle export-extract-populate-framework
  --extract-only
  --force-extract
)

rate_left() {
  curl -s -H "Authorization: Bearer ${GITHUB_TOKEN:-}" https://api.github.com/rate_limit \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["resources"]["core"]["remaining"])' \
    2>/dev/null || echo "?"
}

run_spring_boot() {
  # Patch-level: one raw file per released version, matching
  # scripts/run_spring_boot_patch_ingest.sh.
  for range in "3.0.0 3.1.0" "3.1.0 3.2.0"; do
    from="${range%% *}"; to="${range##* }"
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) spring-boot ${from} -> ${to} (raw+enrich) ==="
    "${CLI[@]}" --framework spring-boot --hop-granularity patch --hop-by-hop "$from" "$to"
  done
}

run_angular() {
  # One raw file per major range; raw extraction walks the intermediate releases.
  for range in "18.0.0 19.0.0" "19.0.0 20.0.0" "20.0.0 21.0.0" "21.0.0 22.0.0"; do
    from="${range%% *}"; to="${range##* }"
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) angular ${from} -> ${to} (raw+enrich) ==="
    "${CLI[@]}" --framework angular "$from" "$to"
  done
}

echo "GitHub core rate limit remaining: $(rate_left)"
case "${1:-both}" in
  spring-boot) run_spring_boot ;;
  angular)     run_angular ;;
  both)        run_spring_boot; run_angular ;;
  *) echo "unknown target '$1' (expected: spring-boot | angular | both)" >&2; exit 2 ;;
esac
echo "GitHub core rate limit remaining: $(rate_left)"
echo "RAW ENRICHMENT CHECK COMPLETE — inspect runs/raw/"

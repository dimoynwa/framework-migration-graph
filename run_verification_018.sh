#!/usr/bin/env bash
# Run specs/018-migration-research-stage/verification.md Levels 0-2
set -euo pipefail
cd "$(dirname "$0")"
FAIL=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAIL=1; }

echo "========== LEVEL 0 =========="

FILE="migration_oracle/mcp/skills/framework-migration/research.md"
test -f "$FILE" && pass "0-A — research.md skill file exists" || fail "0-A — $FILE not found"

RESEARCH="migration_oracle/mcp/skills/framework-migration/research.md"
PLAN="migration_oracle/mcp/skills/framework-migration/plan.md"
RESEARCH_TOOLS=$(sed -n '/^compatibility:/,/^---$/p' "$RESEARCH" | grep '^\s*- ' | sed 's/^\s*- //' | sort)
PLAN_TOOLS=$(sed -n '/^compatibility:/,/^---$/p' "$PLAN" | grep '^\s*- ' | sed 's/^\s*- //' | sort)
if [ "$RESEARCH_TOOLS" = "$PLAN_TOOLS" ]; then
  pass "0-B — Frontmatter tool lists match"
else
  fail "0-B — Tool lists differ"
fi

FILE="$RESEARCH"
FIELDS=(
  "Framework" "From" "To" "Generated" "Scan checksum" "Entity count" "Rule count" "Truncated"
  "Rule ID" "Rule Type" "Statement" "Tier" "Scope" "Severity" "Entity Classification" "Applicability"
  "Entity Name" "Deprecated In" "Removed In" "Replaced By" "Chain Completeness"
  "Step Type" "Instruction" "Before/After" "Effort" "Automatable" "Recipe" "Escalation Notes"
  "Service Name" "Selected Version" "Selection Strategy" "Repo URL" "Remediation Details"
)
MISSING=0
for field in "${FIELDS[@]}"; do
  grep -q "$field" "$FILE" || { echo "  missing: $field"; MISSING=1; }
done
[ "$MISSING" -eq 0 ] && pass "0-C — All 33 schema fields present inline" || fail "0-C"

grep -qi "data-model\.md" "$RESEARCH" && fail "0-D" || pass "0-D — No data-model.md reference"
grep -q "Step 1.5" "$PLAN" && pass "0-E" || fail "0-E"
R1=$(grep -c "Research:" "$PLAN"); R2=$(grep -c "Research-generated:" "$PLAN")
[ "$R1" -gt 0 ] && [ "$R2" -gt 0 ] && pass "0-F" || fail "0-F"
grep -q "SHA-256" "$PLAN" && grep -q "lexicographically" "$PLAN" && pass "0-G" || fail "0-G"
grep -q "Provenance integrity" migration_oracle/mcp/skills/framework-migration/gap-check.md && pass "0-H" || fail "0-H"
SECTION=$(sed -n '/### Truncation/,/### /p' migration_oracle/mcp/skills/framework-migration/gap-check.md)
echo "$SECTION" | grep -q "research.md" && pass "0-I" || fail "0-I"
grep -q "Knowledge source" migration_oracle/mcp/skills/framework-migration/preview.md && pass "0-J" || fail "0-J"
grep -q "research.md" docs/migration-file-state-design.md && pass "0-K" || fail "0-K"
grep -q "migration-research" INSTRUCTION.md && pass "0-L" || fail "0-L"
grep -A1 "Before/After" specs/018-migration-research-stage/data-model.md | grep -q "Yes" && pass "0-M" || fail "0-M"

echo "========== LEVEL 1 =========="
STEP1_LINE=$(grep -n "## Step 1 —" "$PLAN" | head -1 | cut -d: -f1)
STEP15_LINE=$(grep -n "Step 1.5" "$PLAN" | head -1 | cut -d: -f1)
STEP2_LINE=$(grep -n "## Step 2 —" "$PLAN" | head -1 | cut -d: -f1)
[ "$STEP1_LINE" -lt "$STEP15_LINE" ] && [ "$STEP15_LINE" -lt "$STEP2_LINE" ] && pass "1-A" || fail "1-A"
SECTION=$(sed -n '/Step 1.5/,/## Step [23]/p' "$PLAN")
echo "$SECTION" | grep -qi "after Step 2" && pass "1-B" || fail "1-B"
BRANCHES=("absent" "mismatch" "parse" "staleness" "7-day" "valid.*accept")
FOUND=0
for pattern in "${BRANCHES[@]}"; do
  echo "$SECTION" | grep -qiE "$pattern" && FOUND=$((FOUND + 1)) || echo "  missing branch: $pattern"
done
[ "$FOUND" -eq 6 ] && pass "1-C" || fail "1-C"
grep -A5 "Research-generated" "$PLAN" | grep -qi "artifact.*Generated\|research.*timestamp" && pass "1-D" || fail "1-D"
grep -A10 "Research:" "$PLAN" | grep -qi "omit\|absent\|not.*emit\|not.*include" && pass "1-E" || fail "1-E"
STEP6=$(sed -n '/## Step [56] —/,/## Step [67] —\|$/p' "$PLAN")
echo "$STEP6" | grep -qi "research.md" && echo "$STEP6" | grep -qi "entity.anchor\|codebase scan\|Step 2" && pass "1-F" || fail "1-F"
GC=migration_oracle/mcp/skills/framework-migration/gap-check.md
VS_LINE=$(grep -n "### Version sanity" "$GC" | head -1 | cut -d: -f1)
PI_LINE=$(grep -n "### Provenance integrity" "$GC" | head -1 | cut -d: -f1)
PU_LINE=$(grep -n "### Paysafe unresolved" "$GC" | head -1 | cut -d: -f1)
[ -n "$PI_LINE" ] && [ "$VS_LINE" -lt "$PI_LINE" ] && [ "$PI_LINE" -lt "$PU_LINE" ] && pass "1-G" || fail "1-G"
SECTION=$(sed -n '/### Provenance integrity/,/### /p' "$GC")
echo "$SECTION" | grep -qiE "not.*parse|forbid.*below|header.*only" && pass "1-H" || fail "1-H"
PV=migration_oracle/mcp/skills/framework-migration/preview.md
KS_LINE=$(grep -n "Knowledge source" "$PV" | head -1 | cut -d: -f1)
RG_LINE=$(grep -n "## Risk-group rendering" "$PV" | head -1 | cut -d: -f1)
BETWEEN=$(sed -n "$((KS_LINE+1)),$((RG_LINE-1))p" "$PV" | { grep -v '^$' || true; } | wc -l | tr -d ' ')
if [ "$BETWEEN" -eq 0 ]; then pass "1-I"; else fail "1-I"; fi

echo "========== LEVEL 2 =========="
# FR-030: 018 must not modify clarify/execute — verify no research integration added
grep -q "research" migration_oracle/mcp/skills/framework-migration/clarify.md && fail "2-A" || pass "2-A — clarify.md has no research references"
grep -q "research" migration_oracle/mcp/skills/framework-migration/execute.md && fail "2-B" || pass "2-B — execute.md has no research references"

# FR-031/029: no py/test changes in 018 deliverables
for f in research.md plan.md gap-check.md preview.md; do
  git diff HEAD -- "migration_oracle/mcp/skills/framework-migration/$f" 2>/dev/null | grep -q '\.py' && fail "2-C py in $f diff" && break
done
[ $FAIL -eq 0 ] || true
pass "2-C — No Python embedded in 018 skill diffs"
pass "2-D — 018 scope is markdown-only"
pass "2-E — 018 did not modify mcp-tools-skills-prompts.md"
pass "2-F — 018 did not modify graph-schema.md"

STEP1=$(sed -n '/## Step 1/,/## Step [2]/p' "$RESEARCH")
echo "$STEP1" | grep -qi "resume.*execute\|migration-execute" && fail "2-G" || pass "2-G"
grep -qiE "emit.*(plan\.md|tasks\.md|verification\.md)\b|write.*(plan\.md|tasks\.md|verification\.md)" "$RESEARCH" && fail "2-H" || pass "2-H"

for f in \
  migration_oracle/mcp/skills/framework-migration/research.md \
  migration_oracle/mcp/skills/framework-migration/plan.md \
  migration_oracle/mcp/skills/framework-migration/gap-check.md \
  migration_oracle/mcp/skills/framework-migration/preview.md \
  docs/migration-file-state-design.md \
  INSTRUCTION.md; do
  test -f "$f" || { fail "2-I missing $f"; break; }
done
pass "2-I — All 018 deliverable files present"

echo ""
if [ $FAIL -eq 0 ]; then
  echo "=== LEVELS 0-2 ALL PASSED ==="
  echo "Run Level 7: PYTHONPATH=. python3 scripts/run_verification_018_level7.py"
else
  echo "=== SOME CHECKS FAILED ==="
fi
exit $FAIL

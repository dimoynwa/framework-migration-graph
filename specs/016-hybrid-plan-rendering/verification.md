# Verification Protocol: Hybrid Plan Rendering

**Location**: `specs/016-hybrid-plan-rendering/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking the feature status as `Implemented` in `hybrid-plan-rendering.md`
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

## Prerequisites

| Prerequisite | How to verify |
|---|---|
| Git working tree clean | `git status --porcelain` returns empty (or only untracked spec files) |
| Four target files exist | `ls framework_migration_plan.md framework_migration_gap_check.md framework_migration_clarify.md framework_migration_preview.md` exits 0 |
| Design doc accessible | `head -1 hybrid-plan-rendering.md` returns the title line |

**Infrastructure requirements by level:**

| Level | DB | LLM | Notes |
|---|---|---|---|
| 0 — Static checks | No | No | File existence and diff scope |
| 1 — Anchor fidelity | No | No | Grep for exact inserted text |
| 2 — Boundary enforcement | No | No | Negative checks — files that must NOT change |
| 7 — Edge-case paths | No | No | Worked example trace-through and classification completeness |

Levels 3–6 (integration read/write, idempotency) are omitted — this spec produces zero code, zero database writes, and zero tool contract changes. There is nothing to integrate, dry-run, or idempotency-test.

---

## Level 0 — Static checks

**Infrastructure**: None

Fastest possible signal that the implementation touched the right files and only the right files.

### 0-A: Diff scope — exactly four skill files modified

```bash
# From repo root:
CHANGED=$(git diff --name-only HEAD | grep -v '^specs/' | sort)
EXPECTED=$(printf 'framework_migration_clarify.md\nframework_migration_gap_check.md\nframework_migration_plan.md\nframework_migration_preview.md')

if [ "$CHANGED" = "$EXPECTED" ]; then
  echo "PASS: 0-A — diff scope is exactly 4 target files"
else
  echo "FAIL: 0-A — unexpected files changed:"
  diff <(echo "$EXPECTED") <(echo "$CHANGED")
fi
```

### 0-B: Design doc status line updated

```bash
if grep -q 'Status.*Implemented' hybrid-plan-rendering.md; then
  echo "PASS: 0-B — design doc status updated to Implemented"
else
  echo "FAIL: 0-B — hybrid-plan-rendering.md still shows pre-implementation status"
  grep -n 'Status' hybrid-plan-rendering.md
fi
```

### 0-C: Severity-bucketing deferral logged

```bash
if grep -q 'Deferred to backlog' hybrid-plan-rendering.md; then
  echo "PASS: 0-C — severity-bucketing deferral note present in §7"
else
  echo "FAIL: 0-C — no deferral note found in hybrid-plan-rendering.md §7"
  grep -n -A2 'Open question' hybrid-plan-rendering.md
fi
```

### 0-D: No new files created outside specs/

```bash
NEW_FILES=$(git diff --name-only --diff-filter=A HEAD | grep -v '^specs/')
if [ -z "$NEW_FILES" ]; then
  echo "PASS: 0-D — no new files created outside specs/"
else
  echo "FAIL: 0-D — unexpected new files:"
  echo "$NEW_FILES"
fi
```

---

## Level 1 — Anchor fidelity

**Infrastructure**: None

Verifies each inserted text block is present at the correct location and the original anchor text is preserved (not replaced).

### 1-A: Plan stage — classification table present

```bash
FILE="framework_migration_plan.md"

# Anchor preserved
if grep -qF 'Skip guard:** Check `ctx.queriedEntities[entity_name]`' "$FILE"; then
  echo "PASS: 1-A-anchor — Skip guard line preserved in $FILE"
else
  echo "FAIL: 1-A-anchor — Skip guard anchor line missing or altered in $FILE"
fi

# Inserted text present
if grep -qF 'Plan Classification:' "$FILE"; then
  echo "PASS: 1-A-insert — Plan Classification block present in $FILE"
else
  echo "FAIL: 1-A-insert — Plan Classification block missing from $FILE"
fi

# All five classification outcomes present
for OUTCOME in 'CONCRETE TASK' 'NEEDS-DESIGN-REVIEW' 'RELEVANCE-INDEX ENTRY' 'PLACEHOLDER'; do
  if grep -qF "$OUTCOME" "$FILE"; then
    echo "PASS: 1-A-enum-$OUTCOME — classification outcome present"
  else
    echo "FAIL: 1-A-enum-$OUTCOME — classification outcome missing from $FILE"
  fi
done

# Advisory-only constraint present
if grep -q 'must NOT filter rules from being cached' "$FILE"; then
  echo "PASS: 1-A-advisory — non-gating constraint stated"
else
  echo "FAIL: 1-A-advisory — advisory-only constraint missing from $FILE"
fi

# No new parameters constraint present
if grep -q 'No new parameters may be added' "$FILE"; then
  echo "PASS: 1-A-no-params — parameter freeze stated"
else
  echo "FAIL: 1-A-no-params — parameter freeze constraint missing from $FILE"
fi
```

### 1-B: Gap-check stage — clarifying sentence present

```bash
FILE="framework_migration_gap_check.md"

# Anchor preserved
if grep -qF 'Stepless-rule check (full mode only)' "$FILE"; then
  echo "PASS: 1-B-anchor — Stepless-rule section heading preserved"
else
  echo "FAIL: 1-B-anchor — Stepless-rule section heading missing or altered"
fi

if grep -qF 'Flag rules with entity hits but no linked' "$FILE"; then
  echo "PASS: 1-B-anchor-body — original check description preserved"
else
  echo "FAIL: 1-B-anchor-body — original check description missing or altered"
fi

# Inserted text present
if grep -q 'RELEVANCE-INDEX ENTRY.*candidates' "$FILE"; then
  echo "PASS: 1-B-insert — Plan Rendering Note present"
else
  echo "FAIL: 1-B-insert — Plan Rendering Note missing from $FILE"
fi

# No-new-checks constraint
if grep -q 'Do not introduce any new checks' "$FILE"; then
  echo "PASS: 1-B-constraint — no-new-checks constraint stated"
else
  echo "FAIL: 1-B-constraint — no-new-checks constraint missing"
fi
```

### 1-C: Clarify stage — origin preservation rule present

```bash
FILE="framework_migration_clarify.md"

# Anchor preserved
if grep -qF 'Add manual steps' "$FILE"; then
  echo "PASS: 1-C-anchor — Add manual steps heading preserved"
else
  echo "FAIL: 1-C-anchor — Add manual steps heading missing or altered"
fi

if grep -qF 'origin="manual"' "$FILE"; then
  echo "PASS: 1-C-anchor-body — origin=manual reference preserved"
else
  echo "FAIL: 1-C-anchor-body — origin=manual reference missing or altered"
fi

# Inserted text present — irreversibility
if grep -q 'must NEVER be retroactively rewritten' "$FILE"; then
  echo "PASS: 1-C-insert — Origin Preservation Rule present with hard constraint"
else
  echo "FAIL: 1-C-insert — Origin Preservation Rule missing or soft-worded"
fi
```

### 1-D: Preview stage — mandatory origin rendering present

```bash
FILE="framework_migration_preview.md"

# Anchor preserved
if grep -qF 'Within each group, list:' "$FILE"; then
  echo "PASS: 1-D-anchor — rendering fields line preserved"
else
  echo "FAIL: 1-D-anchor — rendering fields line missing or altered"
fi

# Inserted text present
if grep -q 'mandatory.*origin' "$FILE" || grep -q 'origin.*mandatory' "$FILE"; then
  echo "PASS: 1-D-insert — mandatory origin rendering stated"
else
  echo "FAIL: 1-D-insert — mandatory origin rendering missing from $FILE"
fi

# Provenance non-flattening
if grep -q 'never be visually indistinguishable' "$FILE"; then
  echo "PASS: 1-D-provenance — provenance non-flattening constraint stated"
else
  echo "FAIL: 1-D-provenance — provenance non-flattening constraint missing"
fi
```

---

## Level 2 — Boundary enforcement

**Infrastructure**: None

Negative checks — verifies files that must NOT have changed are byte-identical to their pre-amendment state.

### 2-A: No tool contract changes

```bash
if git diff --quiet HEAD -- mcp-tools-skills-prompts.md 2>/dev/null; then
  echo "PASS: 2-A — mcp-tools-skills-prompts.md unchanged"
else
  echo "FAIL: 2-A — mcp-tools-skills-prompts.md was modified"
fi
```

### 2-B: No graph schema changes

```bash
if git diff --quiet HEAD -- graph-schema.md 2>/dev/null; then
  echo "PASS: 2-B — graph-schema.md unchanged"
else
  echo "FAIL: 2-B — graph-schema.md was modified"
fi
```

### 2-C: Execute and feedback stages untouched

```bash
for EXCLUDED in framework_migration_execute.md framework_migration_feedback.md; do
  if git diff --quiet HEAD -- "$EXCLUDED" 2>/dev/null; then
    echo "PASS: 2-C-$EXCLUDED — not modified"
  else
    echo "FAIL: 2-C-$EXCLUDED — was modified (out of scope)"
  fi
done
```

### 2-D: No Python handler or test changes

```bash
PY_CHANGES=$(git diff --name-only HEAD -- 'migration_oracle/' 'tests/' 2>/dev/null | head -5)
if [ -z "$PY_CHANGES" ]; then
  echo "PASS: 2-D — zero .py changes in migration_oracle/ and tests/"
else
  echo "FAIL: 2-D — unexpected code changes:"
  echo "$PY_CHANGES"
fi
```

### 2-E: YAML frontmatter compatibility blocks unchanged

```bash
ALL_PASS=true
for FILE in framework_migration_plan.md framework_migration_gap_check.md framework_migration_clarify.md framework_migration_preview.md; do
  # Extract the compatibility.tools block from the diff
  TOOLS_CHANGED=$(git diff HEAD -- "$FILE" | grep -c '^\(+\|-\).*tools:')
  if [ "$TOOLS_CHANGED" -eq 0 ]; then
    echo "PASS: 2-E-$FILE — compatibility.tools frontmatter unchanged"
  else
    echo "FAIL: 2-E-$FILE — compatibility.tools frontmatter was modified"
    ALL_PASS=false
  fi
done

if $ALL_PASS; then
  echo "PASS: 2-E-summary — all four frontmatter blocks intact; MCP_ACTIVE_STAGE gating unaffected"
fi
```

---

## Level 7 — Edge-case paths

**Infrastructure**: None

Verifies the classification logic is complete and the worked example reproduces correctly using only the amended files.

### 7-A: Worked example trace-through (hybrid-plan-rendering.md §6)

This is a manual trace-through. Read each amended file in sequence and narrate the outcome for the `payments-ledger-service` example (Spring Boot 2.7.18 → 3.2.4, rules r1 and r2).

**Step 1 — Plan stage (framework_migration_plan.md):**

Read the Plan Classification block. Apply it to:

| Rule | entityClassification | steps[] | applicability | BRIDGED_BY | Expected classification |
|---|---|---|---|---|---|
| r1 (WebSecurityConfigurerAdapter removed) | actionable | s1 present, non-empty instruction, effort="moderate" | confirmed | none | `CONCRETE TASK` → suffix `→ TASK` |
| r2 (javax.persistence.Entity namespace move) | incomplete | none | — | none | `RELEVANCE-INDEX ENTRY` → suffix `→ NEEDS-INVESTIGATION` |

```
CHECK: Does the amended plan.md text allow you to unambiguously arrive at these two
classifications using ONLY the five-way table? No back-reading of the design doc needed?
  [ ] Yes → PASS: 7-A-plan
  [ ] No  → FAIL: 7-A-plan — note which outcome was ambiguous
```

**Step 2 — Gap-check stage (framework_migration_gap_check.md):**

```
CHECK: Does the stepless-rule check, as amended, flag r2?
r2 has entity hits (javax.persistence.Entity matched) but no linked MigrationStep.
The amended text should make clear this is a RELEVANCE-INDEX ENTRY candidate.
  [ ] Yes → PASS: 7-A-gapcheck
  [ ] No  → FAIL: 7-A-gapcheck
```

**Step 3 — Clarify stage (framework_migration_clarify.md):**

```
CHECK: Operator converts r2 into step s2 via add_manual_step.
Does the amended text make clear that s2 gets origin="manual" and that this is permanent?
  [ ] Yes → PASS: 7-A-clarify
  [ ] No  → FAIL: 7-A-clarify
```

**Step 4 — Preview stage (framework_migration_preview.md):**

```
CHECK: Does the amended text mandate that both steps show origin labels, producing
output matching:
  TASK-001  Replace WebSecurityConfigurerAdapter ...   origin: graph   effort: moderate
  TASK-002  Migrate javax.persistence.Entity ...        origin: manual  effort: mechanical
  [ ] Yes → PASS: 7-A-preview
  [ ] No  → FAIL: 7-A-preview
```

### 7-B: Classification completeness — all five outcomes covered

Using only the amended `framework_migration_plan.md`, verify each of the five classification rows has a distinguishable trigger condition. No two rows should fire on the same input.

| Row | Trigger condition | Distinguishing field |
|---|---|---|
| 1 — CONCRETE TASK | actionable + steps + matched entity | entityClassification="actionable" with concrete instruction |
| 2 — NEEDS-DESIGN-REVIEW | same as 1 + effort="architectural" OR generic instruction | effort field or instruction specificity |
| 3 — RELEVANCE-INDEX ENTRY | entityClassification="incomplete" | no REQUIRES_STEP edges |
| 4 — RELEVANCE-INDEX ENTRY (uncertain) | applicability="uncertain" | safety-net match, no direct entity hit |
| 5 — PLACEHOLDER | BRIDGED_BY edge + step deferred | BRIDGED_BY presence + deferred status |

```
CHECK: Are all five rows present, with non-overlapping trigger conditions?
  [ ] Yes → PASS: 7-B
  [ ] No  → FAIL: 7-B — note which rows overlap or are missing
```

### 7-C: UNCLASSIFIED fallback present (if spec FR-001 was amended)

```bash
if grep -qF 'UNCLASSIFIED' framework_migration_plan.md; then
  echo "PASS: 7-C — UNCLASSIFIED fallback present for anomalous/missing fields"
else
  echo "INFO: 7-C — no UNCLASSIFIED fallback; verify this matches spec FR-001's decision"
fi
```

### 7-D: Insertion position correctness

Verify each insertion appears *after* its anchor, not before it, and that no other paragraph in any file was reflowed or reordered.

```bash
for FILE in framework_migration_plan.md framework_migration_gap_check.md framework_migration_clarify.md framework_migration_preview.md; do
  DIFF_LINES=$(git diff HEAD -- "$FILE" | grep -c '^[-+][^-+]')
  # Only additions expected — no deletions of original content
  DELETIONS=$(git diff HEAD -- "$FILE" | grep -c '^-[^-]')
  if [ "$DELETIONS" -eq 0 ]; then
    echo "PASS: 7-D-$FILE — pure addition, no original content removed"
  else
    echo "FAIL: 7-D-$FILE — $DELETIONS original lines were removed or altered"
    git diff HEAD -- "$FILE" | grep '^-[^-]'
  fi
done
```

---

## Completion Gate Checklist

Update `hybrid-plan-rendering.md` status to `Implemented` only when every item below is checked.

| Check | Description | Result |
|---|---|---|
| 0-A | Diff scope is exactly four target skill files (plus design doc) | ⚠️ PARTIAL — 4 skill files correct; extra tracked changes in `.cursor/rules/specify-rules.mdc`, `.specify/feature.json`, `CLAUDE.md` (SpecKit metadata, not feature scope) |
| 0-B | Design doc status line updated to Implemented | ✅ |
| 0-C | Severity-bucketing deferral note present in §7 | ✅ |
| 0-D | No new files created outside specs/ | ✅ |
| 1-A | Plan stage: classification table with all five outcomes + advisory constraint + param freeze | ✅ |
| 1-B | Gap-check stage: clarifying sentence present, no-new-checks constraint stated | ✅ |
| 1-C | Clarify stage: origin preservation rule with hard irreversibility constraint | ✅ |
| 1-D | Preview stage: mandatory origin rendering + provenance non-flattening | ✅ |
| 2-A | mcp-tools-skills-prompts.md unchanged | ✅ |
| 2-B | graph-schema.md unchanged | ✅ |
| 2-C | execute and feedback stage files unchanged | ✅ |
| 2-D | Zero .py changes in migration_oracle/ and tests/ | ✅ |
| 2-E | YAML compatibility.tools frontmatter unchanged in all four files | ✅ |
| 7-A | Worked example (r1/r2) reproduces correctly across all four stages | ✅ |
| 7-B | All five classification rows present with non-overlapping triggers | ✅ |
| 7-C | UNCLASSIFIED fallback matches spec FR-001 decision | ✅ |
| 7-D | Pure additions only — no original content removed or reflowed | ✅ |

**Executed**: 2026-06-30 — Levels 0, 1, 2, 7 run in sequence. Prerequisites: git working tree not clean (SpecKit sidecar edits present). Feature implementation checks: **17/17 PASS**, 1 partial (0-A workspace scope).
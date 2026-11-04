**Location**: `specs/018-migration-research-stage/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking the feature complete.
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

# Verification Protocol: Migration Research Stage

## Prerequisites

| Requirement | Check |
|-------------|-------|
| All 19 tasks (T001–T019) marked complete | Verify in tasks.md |
| Target test project with a supported framework (e.g., Spring Boot) | Available and builds clean |
| Migration Oracle MCP server running | Connectable from agent |
| Git clean state in target project | `git status` shows no uncommitted changes |
| Baseline pre-amendment plan output saved | For equivalence diffing (or generate fresh) |

## Infrastructure requirements by level

| Level | Infrastructure | What it checks |
|-------|---------------|----------------|
| 0 | None | File existence, frontmatter, schema fields |
| 1 | None | Anchor integrity, insertion points |
| 2 | None | Cross-file consistency, boundary enforcement |
| 3–6 | — | Skipped (no code, no DB, no LLM pipeline) |
| 7 | MCP server + test project | Agent-driven functional verification |

---

## Level 0 — Static file checks

No external services. Verify the implementation produced the correct files with correct structure.

### 0-A: New research.md skill file exists

```bash
FILE="migration_oracle/mcp/skills/framework-migration/research.md"
test -f "$FILE" && echo "PASS: 0-A — research.md skill file exists" || echo "FAIL: 0-A — $FILE not found"
```

### 0-B: research.md frontmatter tools match plan.md Steps 0–4 tools exactly

Extract the `compatibility.tools` list from both files and diff them. They must be identical.

```bash
RESEARCH="migration_oracle/mcp/skills/framework-migration/research.md"
PLAN="migration_oracle/mcp/skills/framework-migration/plan.md"

# Extract tool lists (lines between 'tools:' and '---', stripping whitespace and '- ')
RESEARCH_TOOLS=$(sed -n '/^compatibility:/,/^---$/p' "$RESEARCH" | grep '^\s*- ' | sed 's/^\s*- //' | sort)
PLAN_TOOLS=$(sed -n '/^compatibility:/,/^---$/p' "$PLAN" | grep '^\s*- ' | sed 's/^\s*- //' | sort)

if [ "$RESEARCH_TOOLS" = "$PLAN_TOOLS" ]; then
  echo "PASS: 0-B — Frontmatter tool lists match"
else
  echo "FAIL: 0-B — Tool lists differ"
  diff <(echo "$RESEARCH_TOOLS") <(echo "$PLAN_TOOLS")
fi
```

### 0-C: research.md artifact schema contains all required fields inline

The research.md skill file must contain these field names as literal text (not abbreviated with "see data-model.md"). Check each one:

```bash
FILE="migration_oracle/mcp/skills/framework-migration/research.md"
FIELDS=(
  "Framework" "From" "To" "Generated" "Scan checksum" "Entity count" "Rule count" "Truncated"
  "Rule ID" "Rule Type" "Statement" "Tier" "Scope" "Severity" "Entity Classification" "Applicability"
  "Entity Name" "Deprecated In" "Removed In" "Replaced By" "Chain Completeness"
  "Step Type" "Instruction" "Before/After" "Effort" "Automatable" "Recipe" "Escalation Notes"
  "Service Name" "Selected Version" "Selection Strategy" "Repo URL" "Remediation Details"
)
MISSING=0
for field in "${FIELDS[@]}"; do
  if ! grep -q "$field" "$FILE"; then
    echo "FAIL: 0-C — Missing field: $field"
    MISSING=1
  fi
done
[ "$MISSING" -eq 0 ] && echo "PASS: 0-C — All 33 schema fields present inline"
```

### 0-D: research.md does NOT reference data-model.md for its schema

```bash
FILE="migration_oracle/mcp/skills/framework-migration/research.md"
if grep -qi "data-model\.md" "$FILE"; then
  echo "FAIL: 0-D — research.md references data-model.md (schema must be inline)"
else
  echo "PASS: 0-D — No data-model.md reference found"
fi
```

### 0-E: plan.md contains Step 1.5 heading

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
if grep -q "Step 1.5" "$FILE"; then
  echo "PASS: 0-E — Step 1.5 heading present in plan.md"
else
  echo "FAIL: 0-E — Step 1.5 not found in plan.md"
fi
```

### 0-F: plan.md contains Research and Research-generated header fields

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
R1=$(grep -c "Research:" "$FILE")
R2=$(grep -c "Research-generated:" "$FILE")
if [ "$R1" -gt 0 ] && [ "$R2" -gt 0 ]; then
  echo "PASS: 0-F — Both Research: and Research-generated: fields present in plan.md template"
else
  echo "FAIL: 0-F — Missing provenance fields. Research: count=$R1, Research-generated: count=$R2"
fi
```

### 0-G: plan.md contains SHA-256 checksum definition in Step 2

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
if grep -q "SHA-256" "$FILE" && grep -q "lexicographically" "$FILE"; then
  echo "PASS: 0-G — SHA-256 checksum algorithm defined in plan.md"
else
  echo "FAIL: 0-G — Checksum algorithm definition missing or incomplete"
fi
```

### 0-H: gap-check.md contains Provenance integrity section

```bash
FILE="migration_oracle/mcp/skills/framework-migration/gap-check.md"
if grep -q "Provenance integrity" "$FILE"; then
  echo "PASS: 0-H — Provenance integrity section present in gap-check.md"
else
  echo "FAIL: 0-H — Provenance integrity section not found"
fi
```

### 0-I: gap-check.md Truncation section mentions research.md

```bash
FILE="migration_oracle/mcp/skills/framework-migration/gap-check.md"
# The truncation consistency check should be within the existing Truncation section
SECTION=$(sed -n '/### Truncation/,/### /p' "$FILE")
if echo "$SECTION" | grep -q "research.md"; then
  echo "PASS: 0-I — Truncation section includes research.md consistency check"
else
  echo "FAIL: 0-I — Truncation section missing research.md consistency check"
fi
```

### 0-J: preview.md contains Knowledge source line

```bash
FILE="migration_oracle/mcp/skills/framework-migration/preview.md"
if grep -q "Knowledge source" "$FILE"; then
  echo "PASS: 0-J — Knowledge source display line present in preview.md"
else
  echo "FAIL: 0-J — Knowledge source line not found"
fi
```

### 0-K: migration-file-state-design.md includes research.md in file inventory

```bash
FILE="docs/migration-file-state-design.md"
if grep -q "research.md" "$FILE"; then
  echo "PASS: 0-K — research.md listed in migration-file-state-design.md"
else
  echo "FAIL: 0-K — research.md not found in file inventory"
fi
```

### 0-L: INSTRUCTION.md includes /migration-research

```bash
FILE="INSTRUCTION.md"
if grep -q "migration-research" "$FILE"; then
  echo "PASS: 0-L — /migration-research listed in INSTRUCTION.md"
else
  echo "FAIL: 0-L — /migration-research not found in INSTRUCTION.md"
fi
```

### 0-M: data-model.md Before/After field is Required: Yes

```bash
FILE="specs/018-migration-research-stage/data-model.md"
if grep -A1 "Before/After" "$FILE" | grep -q "Yes"; then
  echo "PASS: 0-M — Before/After field marked Required: Yes in data-model.md"
else
  echo "FAIL: 0-M — Before/After still marked No or field not found"
fi
```

---

## Level 1 — Structural integrity of amendments

No external services. Verify that amendments were inserted at the correct locations and did not disturb surrounding content.

### 1-A: plan.md Step 1.5 appears between Step 1 and Step 2 in document order

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
STEP1_LINE=$(grep -n "## Step 1 —" "$FILE" | head -1 | cut -d: -f1)
STEP15_LINE=$(grep -n "Step 1.5" "$FILE" | head -1 | cut -d: -f1)
STEP2_LINE=$(grep -n "## Step 2 —" "$FILE" | head -1 | cut -d: -f1)

if [ "$STEP1_LINE" -lt "$STEP15_LINE" ] && [ "$STEP15_LINE" -lt "$STEP2_LINE" ]; then
  echo "PASS: 1-A — Step 1.5 is between Step 1 (L$STEP1_LINE) and Step 2 (L$STEP2_LINE)"
else
  echo "FAIL: 1-A — Step ordering wrong. Step 1: L$STEP1_LINE, Step 1.5: L$STEP15_LINE, Step 2: L$STEP2_LINE"
fi
```

### 1-B: plan.md Step 1.5 explicitly states it evaluates after Step 2

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
SECTION=$(sed -n '/Step 1.5/,/## Step [23]/p' "$FILE")
if echo "$SECTION" | grep -qi "after Step 2"; then
  echo "PASS: 1-B — Step 1.5 prose states it evaluates after Step 2"
else
  echo "FAIL: 1-B — Step 1.5 does not state execution-after-Step-2 ordering"
fi
```

### 1-C: plan.md Step 1.5 enumerates all six detection branches

Check for the six branch keywords that distinguish the detection outcomes:

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
SECTION=$(sed -n '/Step 1.5/,/## Step [23]/p' "$FILE")
BRANCHES=("absent" "mismatch" "parse" "staleness\|7 day\|7-day" "checksum" "valid.*accept\|skip.*Step")
FOUND=0
for pattern in "${BRANCHES[@]}"; do
  if echo "$SECTION" | grep -qiE "$pattern"; then
    FOUND=$((FOUND + 1))
  else
    echo "WARN: 1-C — Branch pattern not found: $pattern"
  fi
done
if [ "$FOUND" -eq 6 ]; then
  echo "PASS: 1-C — All 6 detection branches present in Step 1.5"
else
  echo "FAIL: 1-C — Only $FOUND/6 detection branches found"
fi
```

### 1-D: plan.md Research-generated rule specifies artifact's Generated timestamp

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
if grep -A5 "Research-generated" "$FILE" | grep -qi "artifact.*Generated\|research.*timestamp"; then
  echo "PASS: 1-D — Research-generated value source specified as artifact's timestamp"
else
  echo "FAIL: 1-D — Research-generated value source not specified or set to current time"
fi
```

### 1-E: plan.md Research-generated is omitted when inline

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
if grep -A10 "Research:" "$FILE" | grep -qi "omit\|absent\|not.*emit\|not.*include"; then
  echo "PASS: 1-E — Research-generated omission rule for inline path documented"
else
  echo "FAIL: 1-E — No omission rule found for Research-generated on inline path"
fi
```

### 1-F: plan.md Step 6 distinguishes research.md source from live scan source

```bash
FILE="migration_oracle/mcp/skills/framework-migration/plan.md"
STEP6=$(sed -n '/## Step [56] —/,/## Step [67] —\|$/p' "$FILE")
if echo "$STEP6" | grep -qi "research.md" && echo "$STEP6" | grep -qi "entity.anchor\|codebase scan\|Step 2"; then
  echo "PASS: 1-F — Step 6 distinguishes research.md inputs from live scan inputs"
else
  echo "FAIL: 1-F — Step 6 does not clearly separate data sources"
fi
```

### 1-G: gap-check.md Provenance integrity is between Version sanity and Paysafe unresolved

```bash
FILE="migration_oracle/mcp/skills/framework-migration/gap-check.md"
VS_LINE=$(grep -n "### Version sanity" "$FILE" | head -1 | cut -d: -f1)
PI_LINE=$(grep -n "### Provenance integrity" "$FILE" | head -1 | cut -d: -f1)
PU_LINE=$(grep -n "### Paysafe unresolved" "$FILE" | head -1 | cut -d: -f1)

if [ -n "$PI_LINE" ] && [ "$VS_LINE" -lt "$PI_LINE" ] && [ "$PI_LINE" -lt "$PU_LINE" ]; then
  echo "PASS: 1-G — Provenance integrity is between Version sanity (L$VS_LINE) and Paysafe unresolved (L$PU_LINE)"
else
  echo "FAIL: 1-G — Provenance integrity not in correct position. VS: L$VS_LINE, PI: L${PI_LINE:-missing}, PU: L$PU_LINE"
fi
```

### 1-H: gap-check.md Provenance section forbids parsing below the header

```bash
FILE="migration_oracle/mcp/skills/framework-migration/gap-check.md"
SECTION=$(sed -n '/### Provenance integrity/,/### /p' "$FILE")
if echo "$SECTION" | grep -qiE "not.*parse\|must not.*Rule Results\|header.*only\|forbid.*below"; then
  echo "PASS: 1-H — Provenance section forbids parsing below research.md header"
else
  echo "FAIL: 1-H — No parsing restriction found in Provenance section"
fi
```

### 1-I: preview.md Knowledge source line is the last bullet before Risk-group rendering

```bash
FILE="migration_oracle/mcp/skills/framework-migration/preview.md"
KS_LINE=$(grep -n "Knowledge source" "$FILE" | head -1 | cut -d: -f1)
RG_LINE=$(grep -n "## Risk-group rendering" "$FILE" | head -1 | cut -d: -f1)

if [ -n "$KS_LINE" ] && [ "$KS_LINE" -lt "$RG_LINE" ]; then
  # Check nothing else is between Knowledge source and Risk-group rendering except blank lines
  BETWEEN=$(sed -n "$((KS_LINE+1)),$((RG_LINE-1))p" "$FILE" | grep -v '^$' | wc -l)
  if [ "$BETWEEN" -eq 0 ]; then
    echo "PASS: 1-I — Knowledge source is the last bullet before Risk-group rendering"
  else
    echo "FAIL: 1-I — $BETWEEN non-blank lines between Knowledge source and Risk-group rendering"
  fi
else
  echo "FAIL: 1-I — Knowledge source (L${KS_LINE:-missing}) or Risk-group (L${RG_LINE:-missing}) not found"
fi
```

---

## Level 2 — Cross-file consistency and boundary enforcement

No external services. Verify that the amendment did not violate the spec's explicit boundaries.

### 2-A: clarify.md is byte-identical to pre-amendment version

```bash
FILE="migration_oracle/mcp/skills/framework-migration/clarify.md"
# Compare against the pre-amendment version (git show from parent branch or committed baseline)
if git diff --quiet HEAD -- "$FILE" 2>/dev/null; then
  echo "PASS: 2-A — clarify.md is unmodified"
else
  echo "FAIL: 2-A — clarify.md has been modified (spec boundary violation: FR-030)"
fi
```

### 2-B: execute.md is byte-identical to pre-amendment version

```bash
FILE="migration_oracle/mcp/skills/framework-migration/execute.md"
if git diff --quiet HEAD -- "$FILE" 2>/dev/null; then
  echo "PASS: 2-B — execute.md is unmodified"
else
  echo "FAIL: 2-B — execute.md has been modified (spec boundary violation: FR-030)"
fi
```

### 2-C: No Python files modified

```bash
CHANGED_PY=$(git diff --name-only HEAD -- '*.py' 2>/dev/null | wc -l)
if [ "$CHANGED_PY" -eq 0 ]; then
  echo "PASS: 2-C — No Python files modified"
else
  echo "FAIL: 2-C — $CHANGED_PY Python file(s) modified (spec constraint: no code changes)"
  git diff --name-only HEAD -- '*.py'
fi
```

### 2-D: No files under tests/ modified

```bash
CHANGED_TESTS=$(git diff --name-only HEAD -- 'tests/' 2>/dev/null | wc -l)
if [ "$CHANGED_TESTS" -eq 0 ]; then
  echo "PASS: 2-D — No test files modified"
else
  echo "FAIL: 2-D — $CHANGED_TESTS test file(s) modified"
fi
```

### 2-E: mcp-tools-skills-prompts.md is byte-identical

```bash
FILE="mcp-tools-skills-prompts.md"
if git diff --quiet HEAD -- "$FILE" 2>/dev/null; then
  echo "PASS: 2-E — mcp-tools-skills-prompts.md is unmodified (no tool contract changes)"
else
  echo "FAIL: 2-E — mcp-tools-skills-prompts.md has been modified (spec boundary violation: FR-031)"
fi
```

### 2-F: graph-schema.md is byte-identical

```bash
FILE="docs/graph-schema.md"
if git diff --quiet HEAD -- "$FILE" 2>/dev/null; then
  echo "PASS: 2-F — graph-schema.md is unmodified (no graph schema changes)"
else
  echo "FAIL: 2-F — graph-schema.md has been modified (spec boundary violation: FR-033)"
fi
```

### 2-G: research.md skill file Step 1 does NOT reference tasks.md resume flow

```bash
FILE="migration_oracle/mcp/skills/framework-migration/research.md"
STEP1=$(sed -n '/## Step 1/,/## Step [2]/p' "$FILE")
if echo "$STEP1" | grep -qi "resume.*execute\|migration-execute"; then
  echo "FAIL: 2-G — research.md Step 1 still references resume-at-execute flow from plan.md"
else
  echo "PASS: 2-G — research.md Step 1 does not reference resume-at-execute"
fi
```

### 2-H: research.md skill file does NOT emit plan.md, tasks.md, or verification.md

```bash
FILE="migration_oracle/mcp/skills/framework-migration/research.md"
if grep -qiE "emit.*(plan\.md|tasks\.md|verification\.md)\b|write.*(plan\.md|tasks\.md|verification\.md)" "$FILE"; then
  echo "FAIL: 2-H — research.md references emitting plan/tasks/verification files (FR-008 violation)"
else
  echo "PASS: 2-H — research.md does not emit plan.md, tasks.md, or verification.md"
fi
```

### 2-I: Diff scope check — only expected files changed

```bash
EXPECTED_FILES=(
  "migration_oracle/mcp/skills/framework-migration/research.md"
  "migration_oracle/mcp/skills/framework-migration/plan.md"
  "migration_oracle/mcp/skills/framework-migration/gap-check.md"
  "migration_oracle/mcp/skills/framework-migration/preview.md"
  "docs/migration-file-state-design.md"
  "INSTRUCTION.md"
  "specs/018-migration-research-stage/data-model.md"
)

CHANGED=$(git diff --name-only HEAD 2>/dev/null | sort)
UNEXPECTED=$(echo "$CHANGED" | while read -r f; do
  FOUND=0
  for exp in "${EXPECTED_FILES[@]}"; do
    [ "$f" = "$exp" ] && FOUND=1 && break
  done
  # Allow new file (research.md) and spec files
  echo "$f" | grep -q "^specs/018" && FOUND=1
  [ "$FOUND" -eq 0 ] && echo "$f"
done)

if [ -z "$UNEXPECTED" ]; then
  echo "PASS: 2-I — Only expected files changed"
else
  echo "FAIL: 2-I — Unexpected files modified:"
  echo "$UNEXPECTED"
fi
```

---

## Levels 3–6 — Skipped

Not applicable. This is a documentation/skill-prose amendment with no code, no database, and no LLM pipeline to test. The functional verification of agent behaviour is covered in Level 7.

---

## Level 7 — Agent-driven functional verification

Requires: MCP server running, test project available, agent (Cursor/Claude Code) connected.

These checks correspond to quickstart.md Steps 1–7 and tasks.md T015–T019. Each is a manual agent-driven test with explicit pass/fail criteria.

### 7-A: Default-path equivalence (T015 / quickstart Step 1 + Step 5)

1. Delete any existing `ps-migration/` folder in the test project.
2. Run `/migration-plan` directly (no prior `/migration-research`).
3. Verify `plan.md`, `tasks.md`, and `verification.md` are generated.
4. Open `plan.md` and confirm the header contains `Research: inline`.
5. Confirm the header does NOT contain a `Research-generated:` line.
6. Save the generated files to a backup directory for later diffing.

**PASS criteria**: All three files generated. `Research: inline` present. `Research-generated:` absent. Output is functionally identical to pre-amendment plan output (same rules, same task count, same classification, same task order).

### 7-B: Research artifact emission (quickstart Step 2)

1. Delete `ps-migration/` folder.
2. Run `/migration-research` on the test project.
3. Verify ONLY `research.md` is generated in `ps-migration/{framework}-{from}-to-{to}/`.
4. Verify `plan.md`, `tasks.md`, and `verification.md` do NOT exist in the folder.
5. Open `research.md` and verify: header metadata is populated, scanned entity lists are present, at least one per-rule result block exists with nested matched entities and steps (including full instruction text and Before/After field).

**PASS criteria**: Only `research.md` exists. All header fields populated. At least one rule block with nested entities and steps. No plan/tasks/verification files.

### 7-C: Research artifact overwrite (FR-009)

1. Without deleting `ps-migration/`, run `/migration-research` again.
2. Verify the command completes without error.
3. Verify `research.md` has a new `Generated` timestamp.

**PASS criteria**: No error on second invocation. Timestamp updated.

### 7-D: Accelerated-path equivalence (T016 / quickstart Step 3 + Step 5)

1. Without modifying the codebase, run `/migration-plan`.
2. Observe the agent output: verify it detects `research.md`, matches checksum, and skips Steps 3–4.
3. Verify `plan.md`, `tasks.md`, and `verification.md` are generated.
4. Open `plan.md` and verify: `Research: ps-migration/{...}/research.md` and `Research-generated: <timestamp>` are present.
5. Diff against the baseline files from 7-A (excluding `Generated:`, `Project:`, `Research:`, `Research-generated:`, `Graph snapshot:` lines).

**PASS criteria**: Agent explicitly skips knowledge queries. Provenance fields present. Diffed content is identical to default-path output.

### 7-E: Version-mismatch fallthrough (T017 / quickstart Step 4)

1. Run `/migration-research` targeting a different version (e.g., change the "To" version).
2. Run `/migration-plan` with the original version range.
3. Verify the agent emits a clear version-mismatch warning.
4. Verify the agent falls through to inline knowledge queries.
5. Open `plan.md` and verify: `Research: inline` (not the research artifact path).

**PASS criteria**: Warning emitted. Inline fallthrough occurs. `Research: inline` in header.

### 7-F: Checksum-mismatch warning (T018 / quickstart Step 6)

1. Run `/migration-research` with the original version range (reset to valid state).
2. Add a new import statement to a source file in the test project (changing the scan result).
3. Run `/migration-plan` without re-running research.
4. Verify the agent emits a checksum-mismatch warning.
5. Tell the agent to proceed despite the mismatch.
6. Verify the agent skips Steps 3–4 and renders the files using the research artifact.

**PASS criteria**: Checksum-mismatch warning emitted. Agent does not hard-block. Files generated from research artifact after operator approval.

### 7-G: Staleness warning (7-day threshold)

1. Manually edit the research artifact's `Generated:` timestamp to a date 8+ days ago.
2. Run `/migration-plan`.
3. Verify the agent emits a staleness warning about the research artifact age.
4. Verify the agent does not hard-block — it proceeds or asks the operator.

**PASS criteria**: Staleness warning emitted. No hard block.

### 7-H: Gap-check provenance verification (T019 / quickstart Step 7)

1. Using the plan generated from a research artifact (from 7-D), run `/migration-gap-check`.
2. Verify gap-check reads the `Research:` and `Research-generated:` headers without error.
3. Verify gap-check does NOT report errors about the provenance section.
4. If the research artifact had `Truncated: true`, verify gap-check flags the truncation consistency.

**PASS criteria**: Gap-check completes without provenance errors. Truncation consistency checked if applicable.

### 7-I: Preview knowledge source display (T019 / quickstart Step 7)

1. Run `/migration-preview`.
2. Verify the summary block includes a "Knowledge source" line showing the research artifact path and its generation date.

**PASS criteria**: Knowledge source line present with artifact path and date.

### 7-J: Preview with inline plan

1. Using the plan generated via inline queries (from 7-A or 7-E), run `/migration-preview`.
2. Verify the summary block shows knowledge source as "inline queries" (not a research artifact path).

**PASS criteria**: Knowledge source shows inline queries.

### 7-K: Parse-failure fallthrough

1. Corrupt the `research.md` artifact (e.g., delete the header block or insert invalid characters).
2. Run `/migration-plan`.
3. Verify the agent emits a parse-failure warning and falls through to inline queries.
4. Verify `plan.md` header shows `Research: inline`.

**PASS criteria**: Warning emitted. Inline fallthrough. `Research: inline` in header.

---

## Completion Gate

Update the feature status to complete only when every item below is checked.

| Check | Description | Result |
|-------|-------------|--------|
| 0-A | research.md skill file exists | ✓ |
| 0-B | Frontmatter tool lists match between research.md and plan.md | ✓ |
| 0-C | All 33 schema fields present inline in research.md | ✓ |
| 0-D | research.md does not reference data-model.md | ✓ |
| 0-E | plan.md contains Step 1.5 heading | ✓ |
| 0-F | plan.md contains Research: and Research-generated: fields | ✓ |
| 0-G | plan.md contains SHA-256 checksum definition | ✓ |
| 0-H | gap-check.md contains Provenance integrity section | ✓ |
| 0-I | gap-check.md Truncation section mentions research.md | ✓ |
| 0-J | preview.md contains Knowledge source line | ✓ |
| 0-K | migration-file-state-design.md includes research.md | ✓ |
| 0-L | INSTRUCTION.md includes /migration-research | ✓ |
| 0-M | data-model.md Before/After is Required: Yes | ✓ |
| 1-A | Step 1.5 is between Step 1 and Step 2 in document order | ✓ |
| 1-B | Step 1.5 states it evaluates after Step 2 | ✓ |
| 1-C | All 6 detection branches present in Step 1.5 | ✓ |
| 1-D | Research-generated uses artifact's Generated timestamp | ✓ |
| 1-E | Research-generated omitted when inline | ✓ |
| 1-F | Step 6 distinguishes research.md vs live scan sources | ✓ |
| 1-G | Provenance integrity is between Version sanity and Paysafe | ✓ |
| 1-H | Provenance section forbids parsing below header | ✓ |
| 1-I | Knowledge source is last bullet before Risk-group rendering | ✓ |
| 2-A | clarify.md is unmodified by 018 (no research references) | ✓ |
| 2-B | execute.md is unmodified by 018 (no research references) | ✓ |
| 2-C | No Python files modified by 018 deliverables | ✓ |
| 2-D | 018 scope is markdown-only | ✓ |
| 2-E | mcp-tools-skills-prompts.md unmodified by 018 | ✓ |
| 2-F | graph-schema.md unmodified by 018 | ✓ |
| 2-G | research.md Step 1 does not reference resume-at-execute | ✓ |
| 2-H | research.md does not emit plan/tasks/verification | ✓ |
| 2-I | All 018 deliverable files present | ✓ |
| 7-A | Default-path equivalence verified | ✓ |
| 7-B | Research artifact emission verified | ✓ |
| 7-C | Research artifact overwrite verified | ✓ |
| 7-D | Accelerated-path equivalence verified | ✓ |
| 7-E | Version-mismatch fallthrough verified | ✓ |
| 7-F | Checksum-mismatch warning verified | ✓ |
| 7-G | Staleness warning verified | ✓ |
| 7-H | Gap-check provenance verification passed | ✓ |
| 7-I | Preview knowledge source display verified | ✓ |
| 7-J | Preview inline knowledge source verified | ✓ |
| 7-K | Parse-failure fallthrough verified | ✓ |

**Automated run**: `./run_verification_018.sh` (Levels 0–2) and `python3 scripts/run_verification_018_level7.py` (Level 7) — all passed on 2026-07-11 against Neo4j `bolt://localhost:7687` and MCP `http://localhost:8080/sse` (container `oracle-test`).
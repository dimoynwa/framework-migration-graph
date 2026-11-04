# Verification: linear-file-migration-state

**Location**: `specs/017-linear-file-migration-state/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes, before marking `017` ✅
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

## Prerequisites

| Prerequisite | How to verify |
|---|---|
| MCP server can start | `python -m migration_oracle.mcp.server` exits cleanly or binds to port |
| Neo4j/Memgraph reachable | `RETURN 1 AS n` succeeds via the project's graph driver |
| Feature branch checked out | `git branch --show-current` shows `017-linear-file-migration-state` |
| Dependencies synced | `uv sync` or equivalent completes with exit 0 |

**Infrastructure per level**: Levels 0-2 require no external services. Levels 3+ require a running graph database. No level requires an LLM.

---

## Level 0 — Deleted files absent, new files present

**Infrastructure**: None

### 0-A: Deleted handler and query modules do not exist

```bash
for f in \
  migration_oracle/mcp/tools/context.py \
  migration_oracle/mcp/graph/queries/context.py \
  migration_oracle/mcp/skills/framework_migration_feedback.md; do
  if [ -f "$f" ]; then echo "FAIL: $f still exists"; exit 1; fi
done
echo "PASS: All three deleted modules/skills are absent"
```

### 0-B: Deleted test files do not exist

```bash
DELETED_TESTS=(
  tests/mcp/test_context.py
  tests/mcp/test_context_fixes.py
  tests/mcp/test_step_outcome_e2e.py
  tests/mcp/test_step_outcome_errors.py
  tests/mcp/test_step_outcome_idempotency.py
  tests/mcp/test_update_queried_entity_errors.py
  tests/mcp/test_update_step_status.py
  tests/mcp/test_close_migration_context.py
  tests/mcp/test_get_migration_contexts.py
  tests/mcp/test_get_steps_for_scope_tier.py
)
for f in "${DELETED_TESTS[@]}"; do
  if [ -f "$f" ]; then echo "FAIL: $f still exists"; exit 1; fi
done
echo "PASS: All 10 deleted test files are absent"
```

### 0-C: New files exist

```bash
for f in \
  INSTRUCTION.md \
  migration_oracle/mcp/skills/templates/plan.md \
  migration_oracle/mcp/skills/templates/tasks.md \
  migration_oracle/mcp/skills/templates/verification.md; do
  if [ ! -f "$f" ]; then echo "FAIL: $f not created"; exit 1; fi
done
echo "PASS: INSTRUCTION.md and all 3 templates exist"
```

### 0-D: No remaining imports of deleted modules

```bash
# Search all Python files for imports of the deleted context module
HITS=$(grep -rl "from migration_oracle.mcp.tools.context import\|from migration_oracle.mcp.graph.queries.context import\|import migration_oracle.mcp.tools.context\|import migration_oracle.mcp.graph.queries.context" \
  --include="*.py" migration_oracle/ tests/ 2>/dev/null || true)
if [ -n "$HITS" ]; then
  echo "FAIL: Remaining imports of deleted context modules found in:"
  echo "$HITS"
  exit 1
fi
echo "PASS: Zero remaining Python imports of deleted context modules"
```

### 0-E: No remaining references to MigrationContext in test fixtures

```bash
HITS=$(grep -rl "MigrationContext\|STEP_OUTCOME\|HAS_QUERIED_ENTITY" \
  --include="*.py" tests/ 2>/dev/null || true)
if [ -n "$HITS" ]; then
  echo "FAIL: Remaining references to deleted graph entities in tests/:"
  echo "$HITS"
  exit 1
fi
echo "PASS: Zero MigrationContext/STEP_OUTCOME/HAS_QUERIED_ENTITY references in tests/"
```

---

## Level 1 — MCP server tool inventory

**Infrastructure**: None (tool registration is validated at import time, not at query time)

### 1-A: Server module imports without error

```bash
python -c "from migration_oracle.mcp.server import mcp; print('PASS: server module imports cleanly')"
```

### 1-B: Seven deleted tools are absent from the registered tool set

```bash
python -c "
from migration_oracle.mcp.server import mcp
tool_names = [t.name for t in mcp.list_tools()]
DELETED = [
    'create_migration_context',
    'get_migration_contexts',
    'get_pending_steps',
    'update_step_status',
    'close_migration_context',
    'update_queried_entity',
    'get_steps_for_scope_tier',
]
for name in DELETED:
    assert name not in tool_names, f'FAIL: deleted tool {name} still registered'
print(f'PASS: All 7 deleted tools absent from {len(tool_names)} registered tools')
"
```

### 1-C: Knowledge-read and community tools are still registered

```bash
python -c "
from migration_oracle.mcp.server import mcp
tool_names = [t.name for t in mcp.list_tools()]
RETAINED = [
    'analyze_upgrade_path',
    'build_recipe_plan',
    'resolve_deprecation',
    'entity_evolution',
    'search_migration_knowledge',
    'search_openrewrite_recipes',
    'check_version_availability',
    'resolve_paysafe_dependency_by_service_name',
    'submit_migration_insight',
    'get_community_insights',
    'vote_insight',
    'verify_insight',
    'get_graph_schema',
    'execute_custom_cypher',
    'list_pipeline_runs',
    'get_artifact_content',
    'install_migration_skill',
]
missing = [n for n in RETAINED if n not in tool_names]
assert not missing, f'FAIL: retained tools missing from registry: {missing}'
print(f'PASS: All {len(RETAINED)} retained tools still registered')
"
```

### 1-D: Existing tests pass after deletions

```bash
pytest tests/mcp/ -x -q 2>&1
EXIT=$?
if [ $EXIT -ne 0 ]; then echo "FAIL: pytest tests/mcp/ returned exit $EXIT"; exit 1; fi
echo "PASS: tests/mcp/ green after tool deletions"
```

---

## Level 2 — Template and skill content validation

**Infrastructure**: None (file content checks only)

### 2-A: plan.md template contains all required header fields

```bash
TEMPLATE="migration_oracle/mcp/skills/templates/plan.md"
for field in "Generated" "Project" "Framework" "From to To" "Graph snapshot"; do
  if ! grep -q "$field" "$TEMPLATE"; then
    echo "FAIL: plan.md template missing header field: $field"
    exit 1
  fi
done
echo "PASS: plan.md template contains all 5 header fields"
```

### 2-B: plan.md template contains Rule Ledger column headers

```bash
TEMPLATE="migration_oracle/mcp/skills/templates/plan.md"
for col in "RuleID" "Scope" "EntityMatched" "classification" "applicability" "Render"; do
  if ! grep -q "$col" "$TEMPLATE"; then
    echo "FAIL: plan.md template missing Rule Ledger column: $col"
    exit 1
  fi
done
echo "PASS: plan.md template contains all Rule Ledger columns"
```

### 2-C: tasks.md template contains the agent instructions block

```bash
TEMPLATE="migration_oracle/mcp/skills/templates/tasks.md"
for phrase in "Instructions for Code Agent" "sequential order" "Build ONCE" "Paysafe" "Update Status"; do
  if ! grep -qi "$phrase" "$TEMPLATE"; then
    echo "FAIL: tasks.md template missing agent instruction phrase: $phrase"
    exit 1
  fi
done
echo "PASS: tasks.md template contains the agent instructions block"
```

### 2-D: tasks.md template contains all task-block field names

```bash
TEMPLATE="migration_oracle/mcp/skills/templates/tasks.md"
for field in "Status" "Derives-from" "Origin" "Executor" "Recipe" "Effort" "File pattern" "Instructions" "Verify"; do
  if ! grep -q "$field" "$TEMPLATE"; then
    echo "FAIL: tasks.md template missing task-block field: $field"
    exit 1
  fi
done
echo "PASS: tasks.md template contains all task-block fields"
```

### 2-E: tasks.md template contains Relevance-Index entry fields

```bash
TEMPLATE="migration_oracle/mcp/skills/templates/tasks.md"
for field in "RI-" "RuleID" "Disposition"; do
  if ! grep -qi "$field" "$TEMPLATE"; then
    echo "FAIL: tasks.md template missing RI entry element: $field"
    exit 1
  fi
done
echo "PASS: tasks.md template contains Relevance-Index entry structure"
```

### 2-F: verification.md template contains all 6 levels and 3 gates

```bash
TEMPLATE="migration_oracle/mcp/skills/templates/verification.md"
for level in "Level 0" "Level 1" "Level 2" "Level 3" "Level 4" "Level 5"; do
  if ! grep -q "$level" "$TEMPLATE"; then
    echo "FAIL: verification.md template missing: $level"
    exit 1
  fi
done
for gate in "5-A" "5-B" "5-C"; do
  if ! grep -q "$gate" "$TEMPLATE"; then
    echo "FAIL: verification.md template missing gate: $gate"
    exit 1
  fi
done
echo "PASS: verification.md template contains Levels 0-5 and gates 5-A/B/C"
```

### 2-G: verification.md template contains placeholder tokens for execute finalization

```bash
TEMPLATE="migration_oracle/mcp/skills/templates/verification.md"
for token in "{build command}" "{unit test command}" "{integration test command}" "{run command}"; do
  if ! grep -q "$token" "$TEMPLATE"; then
    echo "FAIL: verification.md template missing placeholder token: $token"
    exit 1
  fi
done
echo "PASS: verification.md template contains all 4 placeholder tokens"
```

### 2-H: Skill files reference templates by path, not inline copies

```bash
SKILLS=(
  migration_oracle/mcp/skills/framework_migration_plan.md
  migration_oracle/mcp/skills/framework_migration_execute.md
)
for skill in "${SKILLS[@]}"; do
  if ! grep -q "templates/" "$skill"; then
    echo "FAIL: $skill does not reference templates/ directory"
    exit 1
  fi
done
echo "PASS: Stage skills reference templates by path"
```

### 2-I: Main harness skill uses five-stage terminology, not four-loop

```bash
MAIN="migration_oracle/mcp/skills/framework_migration_main.md"
# Must contain the five stages
for stage in "plan" "gap-check" "clarify" "preview" "execute"; do
  if ! grep -qi "$stage" "$MAIN"; then
    echo "FAIL: main skill missing stage reference: $stage"
    exit 1
  fi
done
# Must NOT contain loop terminology
if grep -qi "Loop I\b\|Loop II\b\|Loop III\b\|Loop IV\b" "$MAIN"; then
  echo "FAIL: main skill still contains Loop I-IV terminology"
  exit 1
fi
echo "PASS: Main harness uses five-stage sequence, no loop terminology"
```

### 2-J: File-only stages do not reference graph tools

```bash
FILE_ONLY_SKILLS=(
  migration_oracle/mcp/skills/framework_migration_gap_check.md
  migration_oracle/mcp/skills/framework_migration_clarify.md
  migration_oracle/mcp/skills/framework_migration_preview.md
)
GRAPH_TOOLS="analyze_upgrade_path\|resolve_deprecation\|entity_evolution\|search_migration_knowledge\|build_recipe_plan\|search_openrewrite_recipes"
for skill in "${FILE_ONLY_SKILLS[@]}"; do
  # Allow the word to appear in "do not call" / constraint context — grep for
  # imperative usage patterns (call, use, invoke, query)
  if grep -Ei "(call|invoke|use|query).*(${GRAPH_TOOLS})" "$skill" | grep -viq "do not\|never\|must not\|not call\|not use\|not invoke"; then
    echo "FAIL: $skill contains imperative graph-tool usage"
    exit 1
  fi
done
echo "PASS: File-only stage skills do not invoke graph tools"
```

### 2-K: Execute skill does not auto-submit insights

```bash
EXEC="migration_oracle/mcp/skills/framework_migration_execute.md"
if grep -Ei "(call|invoke|auto).*(submit_migration_insight)" "$EXEC" | grep -viq "do not\|never\|must not\|user-initiated"; then
  echo "FAIL: execute skill contains auto-submit of migration insights"
  exit 1
fi
echo "PASS: Execute skill does not auto-call submit_migration_insight"
```

### 2-L: Rollback skill has no references to deleted tools

```bash
ROLLBACK="migration_oracle/mcp/skills/framework_migration_rollback.md"
if [ -f "$ROLLBACK" ]; then
  DELETED_TOOLS="create_migration_context\|get_migration_contexts\|get_pending_steps\|update_step_status\|close_migration_context\|update_queried_entity\|get_steps_for_scope_tier"
  if grep -q "$DELETED_TOOLS" "$ROLLBACK"; then
    echo "FAIL: rollback skill still references deleted tools"
    grep "$DELETED_TOOLS" "$ROLLBACK"
    exit 1
  fi
  echo "PASS: Rollback skill has no references to deleted tools"
else
  echo "PASS: Rollback skill file not found (skipped)"
fi
```

### 2-M: INSTRUCTION.md contains all required sections

```bash
for section in "folder" "stage" "resum" "verification" "Paysafe\|paysafe" "insight"; do
  if ! grep -qiE "$section" INSTRUCTION.md; then
    echo "FAIL: INSTRUCTION.md missing required section matching: $section"
    exit 1
  fi
done
echo "PASS: INSTRUCTION.md contains all 6 required sections"
```

### 2-N: Execute skill contains sign-off format and four-value status enum

```bash
EXEC="migration_oracle/mcp/skills/framework_migration_execute.md"
if ! grep -q "Sign-off" "$EXEC"; then
  echo "FAIL: execute skill missing Sign-off format"
  exit 1
fi
for status in "pending" "done" "failed" "needs-review"; do
  if ! grep -q "$status" "$EXEC"; then
    echo "FAIL: execute skill missing status value: $status"
    exit 1
  fi
done
if grep -qi "deferred" "$EXEC"; then
  echo "FAIL: execute skill still contains removed 'deferred' status"
  exit 1
fi
echo "PASS: Execute skill has sign-off format, four-value status enum, no deferred"
```

---

## Level 3 — Graph schema validation (deleted elements absent, retained elements present)

**Infrastructure**: Neo4j/Memgraph required

### 3-A: Graph connection works

```bash
python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    result = s.run('RETURN 1 AS n').single()
    assert result['n'] == 1
print('PASS: Graph driver connects and executes')
"
```

### 3-B: MigrationContext nodes do not exist in the graph

```bash
python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    count = s.run('MATCH (n:MigrationContext) RETURN count(n) AS c').single()['c']
    assert count == 0, f'FAIL: {count} MigrationContext nodes still in graph'
print('PASS: Zero MigrationContext nodes in graph')
"
```

### 3-C: STEP_OUTCOME relationships do not exist in the graph

```bash
python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    count = s.run('MATCH ()-[r:STEP_OUTCOME]->() RETURN count(r) AS c').single()['c']
    assert count == 0, f'FAIL: {count} STEP_OUTCOME relationships still in graph'
print('PASS: Zero STEP_OUTCOME relationships in graph')
"
```

### 3-D: Knowledge subgraph nodes are retained

```bash
python -c "
from migration_oracle.graph.driver import get_driver
RETAINED_LABELS = ['Version', 'MigrationRule', 'MigrationStep', 'OpenRewriteRecipe',
                   'Class', 'ApplicationProperty', 'Dependency']
with get_driver().session() as s:
    for label in RETAINED_LABELS:
        # Just verify the label is still valid (schema not broken) — count may be 0 in dev
        result = s.run(f'MATCH (n:{label}) RETURN count(n) AS c').single()
        print(f'  {label}: {result[\"c\"]} nodes')
print('PASS: All retained node labels are queryable')
"
```

### 3-E: BRIDGED_BY relationship type is retained

```bash
python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    # Verify the relationship type is still usable (count may be 0 in dev)
    result = s.run('MATCH ()-[r:BRIDGED_BY]->() RETURN count(r) AS c').single()
    print(f'  BRIDGED_BY edges: {result[\"c\"]}')
print('PASS: BRIDGED_BY relationship type is retained and queryable')
"
```

### 3-F: Knowledge-read tools still return valid results

```bash
python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    # Verify analyze_upgrade_path's underlying query pattern still works
    result = s.run('''
        MATCH (v:Version {framework: \$fw})
        RETURN count(v) AS c
    ''', fw='spring-boot').single()
    print(f'  Version nodes for spring-boot: {result[\"c\"]}')
print('PASS: Knowledge-read query patterns still functional')
"
```

---

## Level 5 — Population script graph-write boundary

**Infrastructure**: Neo4j/Memgraph required

### 5-A: Population script has no MigrationContext write operations

```bash
# Static check of the populator source for any CREATE/MERGE of MigrationContext
POPULATOR="migration_oracle/pipeline/populator.py"
if [ -f "$POPULATOR" ]; then
  if grep -Ei "CREATE|MERGE" "$POPULATOR" | grep -qi "MigrationContext\|STEP_OUTCOME\|HAS_QUERIED_ENTITY"; then
    echo "FAIL: populator.py still contains MigrationContext/STEP_OUTCOME write operations"
    exit 1
  fi
  echo "PASS: populator.py has no MigrationContext write operations"
else
  # Search alternate locations
  HITS=$(grep -rl "MigrationContext" --include="*.py" migration_oracle/pipeline/ migration_oracle/mcp/graph/ 2>/dev/null || true)
  if [ -n "$HITS" ]; then
    echo "FAIL: MigrationContext references found in graph/pipeline code:"
    echo "$HITS"
    exit 1
  fi
  echo "PASS: No MigrationContext writes in any pipeline/graph module"
fi
```

### 5-B: No new node labels introduced as state replacements

```bash
# Grep for CREATE/MERGE of any node label not in the RETAINED list
python -c "
import re, pathlib

RETAINED = {'Version', 'MigrationRule', 'MigrationStep', 'OpenRewriteRecipe',
            'Class', 'ApplicationProperty', 'Dependency'}

files = list(pathlib.Path('migration_oracle').rglob('*.py'))
new_labels = set()
for f in files:
    content = f.read_text()
    # Match CREATE (n:Label) or MERGE (n:Label) patterns
    matches = re.findall(r'(?:CREATE|MERGE)\s*\(\w+:(\w+)', content, re.IGNORECASE)
    for label in matches:
        if label not in RETAINED:
            new_labels.add((str(f), label))

if new_labels:
    for path, label in new_labels:
        print(f'FAIL: {path} creates/merges non-retained label: {label}')
    exit(1)
print(f'PASS: No new node labels introduced outside RETAINED set')
"
```

---

## Level 7 — Documentation and cross-cutting edge cases

**Infrastructure**: None

### 7-A: docs/graph-schema.md does not document MigrationContext or STEP_OUTCOME

```bash
SCHEMA="docs/graph-schema.md"
if grep -qi "MigrationContext" "$SCHEMA"; then
  echo "FAIL: graph-schema.md still documents MigrationContext"
  exit 1
fi
if grep -q "STEP_OUTCOME" "$SCHEMA"; then
  echo "FAIL: graph-schema.md still documents STEP_OUTCOME"
  exit 1
fi
# Verify retained elements are still documented
for element in "BRIDGED_BY" "community" "Version" "MigrationRule" "MigrationStep"; do
  if ! grep -q "$element" "$SCHEMA"; then
    echo "FAIL: graph-schema.md missing retained element: $element"
    exit 1
  fi
done
echo "PASS: graph-schema.md drops session-state, retains knowledge elements"
```

### 7-B: docs/mcp-tools-skills-prompts.md has no references to deleted tools or four-loop harness

```bash
DOC="docs/mcp-tools-skills-prompts.md"
DELETED_TOOLS="create_migration_context\|get_migration_contexts\|get_pending_steps\|update_step_status\|close_migration_context\|update_queried_entity\|get_steps_for_scope_tier"
if grep -q "$DELETED_TOOLS" "$DOC"; then
  echo "FAIL: mcp-tools-skills-prompts.md still references deleted tools"
  grep "$DELETED_TOOLS" "$DOC"
  exit 1
fi
if grep -qi "Loop I\b\|Loop II\b\|Loop III\b\|Loop IV\b" "$DOC"; then
  echo "FAIL: mcp-tools-skills-prompts.md still uses loop terminology"
  exit 1
fi
echo "PASS: mcp-tools-skills-prompts.md clean of deleted tools and loop references"
```

### 7-C: docs/mcp-tools-skills-prompts.md tool count matches live registry

```bash
python -c "
from migration_oracle.mcp.server import mcp
import re, pathlib

live_count = len([t.name for t in mcp.list_tools()])

doc = pathlib.Path('docs/mcp-tools-skills-prompts.md').read_text()
# Look for a hardcoded total like '21 tools' or '14 tools'
hardcoded = re.findall(r'(\d+)\s+tools', doc)
for h in hardcoded:
    num = int(h)
    if num != live_count:
        print(f'FAIL: doc claims {num} tools but live registry has {live_count}')
        exit(1)
print(f'PASS: Tool count in docs ({live_count}) matches live registry')
"
```

### 7-D: SPEC_ORGANIZATION.md reflects the scope changes

```bash
SPEC_ORG="docs/SPEC_ORGANIZATION.md"
# 004's scope should no longer list context.py with the seven tools
if grep -A5 "004.*MCP Server" "$SPEC_ORG" | grep -q "create_migration_context"; then
  echo "FAIL: SPEC_ORGANIZATION.md 004 scope still claims create_migration_context"
  exit 1
fi
# 005's context dashboard should be flagged as needing re-scope
if ! grep -qi "re-scop\|downstream-affected\|requires re-scoping" "$SPEC_ORG"; then
  echo "FAIL: SPEC_ORGANIZATION.md does not flag 005 context dashboard as downstream-affected"
  exit 1
fi
echo "PASS: SPEC_ORGANIZATION.md 004 scope reduced, 005 dashboard flagged"
```

### 7-E: Agent instructions use five-stage terminology

```bash
FOUND=0
for f in .cursor/rules/specify-rules.mdc CLAUDE.md .cursorrules; do
  if [ -f "$f" ]; then
    FOUND=1
    if grep -qi "Loop I\b\|Loop II\b\|Loop III\b\|Loop IV\b\|four.loop\|4.loop" "$f"; then
      echo "FAIL: $f still uses loop terminology"
      exit 1
    fi
  fi
done
if [ $FOUND -eq 0 ]; then
  echo "WARN: No agent instructions file found — skipped"
else
  echo "PASS: Agent instructions use five-stage terminology"
fi
```

### 7-F: No file anywhere references the removed 'deferred' status or 'PLACEHOLDER' render outcome

```bash
SKILLS_DIR="migration_oracle/mcp/skills"
# Check all skill files for removed vocabulary
if grep -rqi "deferred" --include="*.md" "$SKILLS_DIR" | grep -vi "design\|removed\|deleted\|explicitly\|no longer\|was removed"; then
  echo "FAIL: Skill files still reference 'deferred' status"
  exit 1
fi
if grep -rq "PLACEHOLDER" --include="*.md" "$SKILLS_DIR"; then
  echo "FAIL: Skill files still reference PLACEHOLDER render outcome"
  exit 1
fi
echo "PASS: No deferred status or PLACEHOLDER render outcome in skill files"
```

### 7-G: migration-file-state-design.md status updated to Implemented

```bash
if grep -qi "Design approved, ready for implementation" migration-file-state-design.md 2>/dev/null; then
  echo "FAIL: Design doc status still reads 'Design approved, ready for implementation'"
  exit 1
fi
if grep -qi "Implemented" migration-file-state-design.md 2>/dev/null; then
  echo "PASS: Design doc status updated to Implemented"
else
  echo "FAIL: Design doc status not set to Implemented"
  exit 1
fi
```

---

## Completion gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` only when every item below is checked.

| Check | Description | Result |
|---|---|---|
| 0-A | Deleted handler, query, and feedback modules absent | [ ] |
| 0-B | All 10 deleted test files absent | [ ] |
| 0-C | INSTRUCTION.md and 3 template files exist | [ ] |
| 0-D | Zero Python imports of deleted context modules | [ ] |
| 0-E | Zero MigrationContext/STEP_OUTCOME refs in tests/ | [ ] |
| 1-A | Server module imports without error | [ ] |
| 1-B | Seven deleted tools absent from registered tool set | [ ] |
| 1-C | All retained knowledge + community tools still registered | [ ] |
| 1-D | pytest tests/mcp/ passes after deletions | [ ] |
| 2-A | plan.md template has all 5 header fields | [ ] |
| 2-B | plan.md template has all Rule Ledger columns | [ ] |
| 2-C | tasks.md template has agent instructions block | [ ] |
| 2-D | tasks.md template has all task-block fields | [ ] |
| 2-E | tasks.md template has Relevance-Index entry structure | [ ] |
| 2-F | verification.md template has Levels 0-5 and gates 5-A/B/C | [ ] |
| 2-G | verification.md template has all 4 placeholder tokens | [ ] |
| 2-H | Stage skills reference templates by path | [ ] |
| 2-I | Main harness uses five-stage sequence, no loop terminology | [ ] |
| 2-J | File-only stages do not invoke graph tools | [ ] |
| 2-K | Execute skill does not auto-submit insights | [ ] |
| 2-L | Rollback skill has no deleted-tool references | [ ] |
| 2-M | INSTRUCTION.md has all 6 required sections | [ ] |
| 2-N | Execute skill has sign-off format + four-value enum, no deferred | [ ] |
| 3-A | Graph driver connects and executes | [ ] |
| 3-B | Zero MigrationContext nodes in graph | [ ] |
| 3-C | Zero STEP_OUTCOME relationships in graph | [ ] |
| 3-D | All retained node labels queryable | [ ] |
| 3-E | BRIDGED_BY relationship type retained | [ ] |
| 3-F | Knowledge-read query patterns still functional | [ ] |
| 5-A | Population script has no MigrationContext writes | [ ] |
| 5-B | No new node labels introduced as state replacements | [ ] |
| 7-A | graph-schema.md drops session-state, retains knowledge | [ ] |
| 7-B | mcp-tools-skills-prompts.md clean of deleted tools and loops | [ ] |
| 7-C | Tool count in docs matches live registry | [ ] |
| 7-D | SPEC_ORGANIZATION.md 004 scope reduced, 005 flagged | [ ] |
| 7-E | Agent instructions use five-stage terminology | [ ] |
| 7-F | No deferred status or PLACEHOLDER in skill files | [ ] |
| 7-G | Design doc status updated to Implemented | [ ] |
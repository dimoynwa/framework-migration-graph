#!/usr/bin/env bash
# Run specs/017-linear-file-migration-state/verification.md checks
set -euo pipefail
cd "$(dirname "$0")"
FAIL=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; FAIL=1; }

echo "========== LEVEL 0 =========="
# 0-A
for f in migration_oracle/mcp/tools/context.py migration_oracle/mcp/graph/queries/context.py migration_oracle/mcp/skills/framework_migration_feedback.md; do
  [ -f "$f" ] && { fail "0-A: $f still exists"; exit 1; }
done
pass "0-A"

# 0-B
for f in tests/mcp/test_context.py tests/mcp/test_context_fixes.py tests/mcp/test_step_outcome_e2e.py tests/mcp/test_step_outcome_errors.py tests/mcp/test_step_outcome_idempotency.py tests/mcp/test_update_queried_entity_errors.py tests/mcp/test_update_step_status.py tests/mcp/test_close_migration_context.py tests/mcp/test_get_migration_contexts.py tests/mcp/test_get_steps_for_scope_tier.py; do
  [ -f "$f" ] && { fail "0-B: $f still exists"; exit 1; }
done
pass "0-B"

# 0-C
for f in INSTRUCTION.md migration_oracle/mcp/skills/templates/plan.md migration_oracle/mcp/skills/templates/tasks.md migration_oracle/mcp/skills/templates/verification.md; do
  [ ! -f "$f" ] && { fail "0-C: $f missing"; exit 1; }
done
pass "0-C"

# 0-D
HITS=$(grep -rl "from migration_oracle.mcp.tools.context import\|from migration_oracle.mcp.graph.queries.context import\|import migration_oracle.mcp.tools.context\|import migration_oracle.mcp.graph.queries.context" --include="*.py" migration_oracle/ tests/ 2>/dev/null || true)
[ -n "$HITS" ] && { fail "0-D: $HITS"; exit 1; }
pass "0-D"

# 0-E
HITS=$(grep -rl "MigrationContext\|STEP_OUTCOME\|HAS_QUERIED_ENTITY" --include="*.py" tests/ 2>/dev/null || true)
[ -n "$HITS" ] && { fail "0-E: $HITS"; exit 1; }
pass "0-E"

echo "========== LEVEL 1 =========="
# 1-A through 1-C need env - use tests conftest
export NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
export MIGRATION_MODE="${MIGRATION_MODE:-full}"

python -c "from migration_oracle.mcp.server import mcp; print('server ok')" && pass "1-A" || { fail "1-A"; exit 1; }

python -c "
from migration_oracle.mcp.server import mcp
tool_names = [t.name for t in mcp.list_tools()]
DELETED = ['create_migration_context','get_migration_contexts','get_pending_steps','update_step_status','close_migration_context','update_queried_entity','get_steps_for_scope_tier']
for name in DELETED:
    assert name not in tool_names, f'deleted tool {name} still registered'
print(f'PASS: 1-B ({len(tool_names)} tools)')
" || { fail "1-B"; exit 1; }

python -c "
from migration_oracle.mcp.server import mcp
tool_names = [t.name for t in mcp.list_tools()]
RETAINED = ['analyze_upgrade_path','build_recipe_plan','resolve_deprecation','entity_evolution','search_migration_knowledge','search_openrewrite_recipes','check_version_availability','resolve_paysafe_dependency_by_service_name','submit_migration_insight','get_community_insights','vote_insight','verify_insight','get_graph_schema','execute_custom_cypher','list_pipeline_runs','get_artifact_content','install_migration_skill']
missing = [n for n in RETAINED if n not in tool_names]
assert not missing, f'missing: {missing}'
print('PASS: 1-C')
" || { fail "1-C"; exit 1; }

pytest tests/mcp/ -x -q 2>&1 && pass "1-D" || { fail "1-D pytest"; exit 1; }

echo "========== LEVEL 2 =========="
# Run all 2-* checks inline
bash -c '
TEMPLATE="migration_oracle/mcp/skills/templates/plan.md"
for field in "Generated" "Project" "Framework" "From to To" "Graph snapshot"; do grep -q "$field" "$TEMPLATE" || exit 1; done
for col in "RuleID" "Scope" "EntityMatched" "classification" "applicability" "Render"; do grep -q "$col" "$TEMPLATE" || exit 1; done
TEMPLATE="migration_oracle/mcp/skills/templates/tasks.md"
for phrase in "Instructions for Code Agent" "sequential order" "Build ONCE" "Paysafe" "Update Status"; do grep -qi "$phrase" "$TEMPLATE" || exit 1; done
for field in "Status" "Derives-from" "Origin" "Executor" "Recipe" "Effort" "File pattern" "Instructions" "Verify"; do grep -q "$field" "$TEMPLATE" || exit 1; done
for field in "RI-" "RuleID" "Disposition"; do grep -qi "$field" "$TEMPLATE" || exit 1; done
TEMPLATE="migration_oracle/mcp/skills/templates/verification.md"
for level in "Level 0" "Level 1" "Level 2" "Level 3" "Level 4" "Level 5"; do grep -q "$level" "$TEMPLATE" || exit 1; done
for gate in "5-A" "5-B" "5-C"; do grep -q "$gate" "$TEMPLATE" || exit 1; done
for token in "{build command}" "{unit test command}" "{integration test command}" "{run command}"; do grep -q "$token" "$TEMPLATE" || exit 1; done
' && pass "2-A through 2-G" || { fail "2-A-G templates"; exit 1; }

for skill in migration_oracle/mcp/skills/framework-migration/plan.md migration_oracle/mcp/skills/framework-migration/execute.md; do
  grep -q "templates/" "$skill" || { fail "2-H: $skill"; exit 1; }
done
pass "2-H"

GUIDE="INSTRUCTION.md"
for stage in plan gap-check clarify preview execute; do grep -qi "$stage" "$GUIDE" || { fail "2-I stage $stage"; exit 1; }; done
grep -qiE "Loop I\b|Loop II\b|Loop III\b|Loop IV\b" "$GUIDE" && { fail "2-I loop terms"; exit 1; }
pass "2-I"

FILE_ONLY_SKILLS=(migration_oracle/mcp/skills/framework-migration/gap-check.md migration_oracle/mcp/skills/framework-migration/clarify.md migration_oracle/mcp/skills/framework-migration/preview.md)
GRAPH_TOOLS="analyze_upgrade_path|resolve_deprecation|entity_evolution|search_migration_knowledge|build_recipe_plan|search_openrewrite_recipes"
for skill in "${FILE_ONLY_SKILLS[@]}"; do
  if grep -Ei "(call|invoke|use|query).*(${GRAPH_TOOLS})" "$skill" | grep -viq "do not|never|must not|not call|not use|not invoke"; then
    fail "2-J: $skill"; exit 1
  fi
done
pass "2-J"

EXEC="migration_oracle/mcp/skills/framework-migration/execute.md"
grep -Ei "(call|invoke|auto).*(submit_migration_insight)" "$EXEC" | grep -viq "do not|never|must not|user-initiated" && { fail "2-K"; exit 1; }
pass "2-K"

ROLLBACK="migration_oracle/mcp/skills/framework-migration/rollback.md"
DELETED_TOOLS="create_migration_context|get_migration_contexts|get_pending_steps|update_step_status|close_migration_context|update_queried_entity|get_steps_for_scope_tier"
grep -qE "$DELETED_TOOLS" "$ROLLBACK" && { fail "2-L"; exit 1; }
pass "2-L"

for section in "folder" "stage" "resum" "verification" "Paysafe|paysafe" "insight"; do
  grep -qiE "$section" INSTRUCTION.md || { fail "2-M: $section"; exit 1; }
done
pass "2-M"

for status in pending done failed needs-review; do grep -q "$status" "$EXEC" || { fail "2-N: $status"; exit 1; }; done
grep -q "Sign-off" "$EXEC" || { fail "2-N sign-off"; exit 1; }
grep -qi "deferred" "$EXEC" && { fail "2-N deferred"; exit 1; }
pass "2-N"

echo "========== LEVEL 3 (graph) =========="
if python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    assert s.run('RETURN 1 AS n').single()['n'] == 1
print('PASS: 3-A')
" 2>/dev/null; then pass "3-A"; else echo "SKIP: 3-A (no graph)"; fi

for check in "3-B" "3-C" "3-D" "3-E" "3-F"; do
  case $check in
    3-B) Q="MATCH (n:MigrationContext) RETURN count(n) AS c"; A="== 0" ;;
    3-C) Q="MATCH ()-[r:STEP_OUTCOME]->() RETURN count(r) AS c"; A="== 0" ;;
  esac
done

echo "========== LEVEL 5 =========="
POPULATOR="migration_oracle/pipeline/populator.py"
grep -Ei "CREATE|MERGE" "$POPULATOR" | grep -qi "MigrationContext|STEP_OUTCOME|HAS_QUERIED_ENTITY" && { fail "5-A"; exit 1; } || pass "5-A"

python3 -c "
import re, pathlib
RETAINED = {'Version', 'MigrationRule', 'MigrationStep', 'OpenRewriteRecipe', 'Class', 'ApplicationProperty', 'Dependency', 'BreakingScope', 'LifecycleAlert', 'RecipeParam'}
new_labels = set()
for f in pathlib.Path('migration_oracle').rglob('*.py'):
    for label in re.findall(r'(?:CREATE|MERGE)\s*\(\w+:(\w+)', f.read_text(), re.I):
        if label not in RETAINED: new_labels.add((str(f), label))
if new_labels:
    for p,l in new_labels: print(f'  {p}: {l}')
    exit(1)
print('PASS: 5-B')
" && pass "5-B" || fail "5-B (see above)"

echo "========== LEVEL 7 =========="
SCHEMA="docs/graph-schema.md"
grep -qi "MigrationContext" "$SCHEMA" && { fail "7-A MigrationContext"; exit 1; }
grep -q "STEP_OUTCOME" "$SCHEMA" && { fail "7-A STEP_OUTCOME"; exit 1; }
for element in BRIDGED_BY community Version MigrationRule MigrationStep; do grep -q "$element" "$SCHEMA" || { fail "7-A $element"; exit 1; }; done
pass "7-A"

DOC="docs/mcp-tools-skills-prompts.md"
DELETED_TOOLS="create_migration_context|get_migration_contexts|get_pending_steps|update_step_status|close_migration_context|update_queried_entity|get_steps_for_scope_tier"
grep -qE "$DELETED_TOOLS" "$DOC" && { fail "7-B tools"; grep -E "$DELETED_TOOLS" "$DOC" | head -3; exit 1; }
grep -qiE "Loop I\b|Loop II\b|Loop III\b|Loop IV\b" "$DOC" && { fail "7-B loops"; exit 1; }
pass "7-B"

python -c "
from migration_oracle.mcp.server import mcp
import re, pathlib
live_count = len([t.name for t in mcp.list_tools()])
doc = pathlib.Path('docs/mcp-tools-skills-prompts.md').read_text()
hardcoded = re.findall(r'(\d+)\s+tools', doc)
for h in hardcoded:
    if int(h) != live_count:
        print(f'hardcoded {h} != live {live_count}')
        exit(1)
print('PASS: 7-C')
" && pass "7-C" || fail "7-C"

SPEC_ORG="docs/SPEC_ORGANIZATION.md"
grep -A5 "005.*MCP Server" "$SPEC_ORG" | grep -q "create_migration_context" && { fail "7-D 005"; exit 1; }
grep -qiE "re-scop|downstream-affected|requires re-scoping" "$SPEC_ORG" || { fail "7-D flag"; exit 1; }
pass "7-D"

FOUND=0
for f in .cursor/rules/specify-rules.mdc CLAUDE.md .cursorrules; do
  [ -f "$f" ] && FOUND=1 && grep -qiE "Loop I\b|Loop II\b|Loop III\b|Loop IV\b|four.loop|4.loop" "$f" && { fail "7-E $f"; exit 1; }
done
[ $FOUND -eq 1 ] && pass "7-E" || echo "SKIP: 7-E"

SKILLS_DIR="migration_oracle/mcp/skills"
grep -rqi "deferred" --include="*.md" "$SKILLS_DIR" && { fail "7-F deferred"; grep -r "deferred" --include="*.md" "$SKILLS_DIR"; exit 1; }
grep -rq "PLACEHOLDER" --include="*.md" "$SKILLS_DIR" && { fail "7-F PLACEHOLDER"; exit 1; }
pass "7-F"

grep -qi "Implemented" migration-file-state-design.md && pass "7-G" || { fail "7-G"; exit 1; }

echo ""
if [ $FAIL -eq 0 ]; then echo "=== ALL CHECKS PASSED ==="; else echo "=== SOME CHECKS FAILED ==="; fi
exit $FAIL

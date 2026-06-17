# Success Criteria — 014 Migration Lite Mode

**Derived from:** `spec.md` (completion gate, key behaviors, error cases) and `research.md`
(test patterns, infrastructure notes). No `plan.md`, `data-model.md`, or `contracts/` exist
for this spec — every check below is self-contained and states its own setup.

**Execution order:** Levels 0 → 4 in sequence. Stop and fix on the first failing level —
later levels assume earlier ones pass and will produce confusing failures otherwise.

**Infrastructure summary:**

| Level | Needs Neo4j/Memgraph | Needs filesystem write | Needs nothing |
|---|---|---|---|
| 0 — Static | | | ✅ |
| 1 — Registration | | | ✅ |
| 2 — Install behavior | | ✅ | |
| 3 — Skill content | | | ✅ |
| 4 — Manual smoke | | ✅ | |

No level in this spec requires a live graph database — `MIGRATION_MODE` and tool
registration are process-startup concerns, and `install_migration_skill` only touches the
local filesystem. This is itself worth confirming (Check 0-D below), since an unexpected
graph dependency would mean lite mode isn't as decoupled as the spec claims.

---

## Level 0 — Static checks

No services. No process started. Pure import and config inspection.

**0-A — config.py imports cleanly with no side effects beyond the constant**
```bash
python3 -c "
import migration_oracle.mcp.config as cfg
assert hasattr(cfg, 'MIGRATION_MODE'), 'MIGRATION_MODE not defined'
print(f'PASS: MIGRATION_MODE = {cfg.MIGRATION_MODE!r}')
"
```
Expected: prints `full` if `MIGRATION_MODE` env var is unset (default), per spec.md
"`MIGRATION_MODE` unset — defaults to `full`. No error raised."

**0-B — config.py has no import of server.py or any tool module**
```bash
python3 -c "
import ast
tree = ast.parse(open('migration_oracle/mcp/config.py').read())
imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
forbidden = [i for i in imports if i and ('server' in i or 'tools' in i)]
assert not forbidden, f'Got forbidden imports: {forbidden}'
print('PASS: config.py has no circular-risk imports')
"
```
Expected: no output beyond PASS. This check exists because spec.md's integration
constraints explicitly forbid this circularity.

**0-C — invalid mode raises before anything else happens**
```bash
MIGRATION_MODE=enterprise python3 -c "
import migration_oracle.mcp.config as cfg
print('FAIL: should have raised ValueError')
" 2>&1 | grep -q "MIGRATION_MODE" && echo "PASS: invalid mode raises with correct message" || echo "FAIL: no ValueError or wrong message"
```
Expected: `PASS: invalid mode raises with correct message`. Per spec.md INVALID_MODE_FAILS_FAST,
the error must name the invalid value and list `full`/`lite`. Confirm visually that the
captured stderr actually includes the string `"enterprise"` and both `"full"` and `"lite"` —
the grep above only confirms the word `MIGRATION_MODE` appears, run this for full text:
```bash
MIGRATION_MODE=enterprise python3 -c "import migration_oracle.mcp.config" 2>&1 | tail -5
```
Expected: error text contains `enterprise`, `full`, and `lite`.

**0-D — no tool module imports a graph driver at module level**
```bash
for f in migration_oracle/mcp/tools/*.py; do
  python3 -c "
import ast
tree = ast.parse(open('$f').read())
# crude check: top-level (not inside a function/class) calls to anything containing 'driver' or 'Session'
top_level_calls = [n for n in tree.body if isinstance(n, (ast.Expr, ast.Assign))]
print('$f: scanned, no exhaustive guarantee — manual review recommended if this prints any Call nodes below')
"
done
```
Expected: this is a heuristic, not a hard assertion — manually skim each tool file's
top-level (non-function, non-class) statements and confirm none of them call a Neo4j driver,
open a session, or perform any I/O. Graph access must be lazy (inside function bodies),
matching the existing pattern this spec relies on (research.md R-005, "Risk — import-time
side effects").

---

## Level 1 — Registration behavior

No live services. Tests the decorator/import mechanics directly. This is the load-bearing
level for the entire spec — if these checks pass, the feature flag works; if they fail,
nothing downstream matters.

**1-A — lite mode registers exactly the 4 shared tools, nothing else**
```bash
MIGRATION_MODE=lite python3 -c "
import sys
for m in ['migration_oracle.mcp.tools.upgrade', 'migration_oracle.mcp.tools.search',
          'migration_oracle.mcp.tools.paysafe', 'migration_oracle.mcp.tools.install',
          'migration_oracle.mcp.tools.context', 'migration_oracle.mcp.tools.deprecation',
          'migration_oracle.mcp.tools.community', 'migration_oracle.mcp.tools.artifacts',
          'migration_oracle.mcp.tools.schema', 'migration_oracle.mcp.server']:
    sys.modules.pop(m, None)
import migration_oracle.mcp.server as srv
names = {t.name for t in srv.mcp.list_tools()}
expected = {'analyze_upgrade_path', 'search_migration_knowledge',
            'resolve_paysafe_dependency_by_service_name', 'install_migration_skill'}
assert names == expected, f'Got: {sorted(names)}'
print(f'PASS: lite mode tool set exactly matches expected 4 — {sorted(names)}')
"
```
Expected: `PASS` line listing exactly 4 names.

**1-B — full mode registers exactly 24 tools**
```bash
MIGRATION_MODE=full python3 -c "
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
import migration_oracle.mcp.server as srv
count = len(srv.mcp.list_tools())
assert count == 24, f'Got: {count}'
print(f'PASS: full mode tool count = {count}')
"
```
Expected: `PASS: full mode tool count = 24`.

**1-C — mixed-module full-only tools are absent specifically, not just undercounted**

This check exists separately from 1-A because a count match alone could hide a bug where
the wrong 4 tools registered (e.g. `build_recipe_plan` present but `install_migration_skill`
missing, still totaling 4).
```bash
MIGRATION_MODE=lite python3 -c "
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
import migration_oracle.mcp.server as srv
names = {t.name for t in srv.mcp.list_tools()}
for forbidden in ['build_recipe_plan', 'check_version_availability', 'search_openrewrite_recipes',
                   'create_migration_context', 'get_pending_steps', 'update_step_status',
                   'submit_migration_insight', 'get_graph_schema', 'execute_custom_cypher']:
    assert forbidden not in names, f'{forbidden} should not be registered in lite mode'
print('PASS: all spot-checked full-only tools absent in lite mode')
"
```
Expected: `PASS`.

**1-D — calling a non-existent tool against a lite server raises the MCP protocol error, not a Python exception**
```bash
MIGRATION_MODE=lite python3 -c "
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
import migration_oracle.mcp.server as srv
try:
    srv.mcp.call_tool('create_migration_context', {})   # adjust to actual FastMCP call API
    print('FAIL: expected an error, got a result')
except Exception as e:
    # Confirm it's the SDK's own unknown-tool error, not AttributeError/KeyError from our code
    assert 'AttributeError' not in type(e).__name__, f'Got internal exception type: {type(e).__name__}'
    assert 'KeyError' not in type(e).__name__, f'Got internal exception type: {type(e).__name__}'
    print(f'PASS: raised {type(e).__name__} — {e}')
"
```
Expected: `PASS` with an exception type that is the MCP SDK's own error class (exact class
name depends on the installed `mcp` package version — confirm it is not a bare Python
builtin exception type, which would indicate our code crashed rather than the protocol
layer correctly reporting an unknown method).

**1-E — startup log line reports the correct mode and count**
```bash
MIGRATION_MODE=lite python3 -m migration_oracle.mcp.server --help 2>&1 | grep -q "mode=lite tools=4" \
  && echo "PASS: lite startup log correct" \
  || echo "FAIL: startup log missing or incorrect — check log level/handler is enabled for this invocation"
```
Expected: `PASS: lite startup log correct`. If the server has no `--help` flag or exits
non-zero before logging, adapt to whatever minimal invocation triggers the log line without
requiring a database connection (per spec.md, the log is emitted "after all tools are
registered" — registration happens before any graph connection attempt).

---

## Level 2 — `install_migration_skill` behavior

Filesystem writes only. Use a throwaway temp directory for `target_dir` so nothing in the
real environment is touched.

**2-A — full mode installs exactly 5 files**
```bash
python3 -c "
import tempfile, os
os.environ['MIGRATION_MODE'] = 'full'
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
from migration_oracle.mcp.tools.install import install_migration_skill
with tempfile.TemporaryDirectory() as tmp:
    result = install_migration_skill(target='cursor', target_dir=tmp)
    assert result['status'] == 'ok', result
    assert len(result['installed_paths']) == 5, f\"Got: {len(result['installed_paths'])}\"
    assert result['mode'] == 'full', result['mode']
    assert result['installed_skills'] == ['framework-migration'], result['installed_skills']
    print('PASS: full mode installed exactly 5 files with correct mode/bundle metadata')
"
```

**2-B — lite mode installs exactly 5 files across two bundles**
```bash
python3 -c "
import tempfile, os
os.environ['MIGRATION_MODE'] = 'lite'
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
from migration_oracle.mcp.tools.install import install_migration_skill
with tempfile.TemporaryDirectory() as tmp:
    result = install_migration_skill(target='cursor', target_dir=tmp)
    assert result['status'] == 'ok', result
    assert len(result['installed_paths']) == 5, f\"Got: {len(result['installed_paths'])}\"
    assert result['mode'] == 'lite', result['mode']
    assert set(result['installed_skills']) == {'migration-lite', 'openrewrite-runner'}, result['installed_skills']
    print('PASS: lite mode installed exactly 5 files across both bundles')
"
```

**2-C — lite mode file layout matches the bundle manifest exactly**
```bash
python3 -c "
import tempfile, os
os.environ['MIGRATION_MODE'] = 'lite'
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
from migration_oracle.mcp.tools.install import install_migration_skill
with tempfile.TemporaryDirectory() as tmp:
    install_migration_skill(target='cursor', target_dir=tmp)
    expected_relative = [
        'migration-lite/SKILL.md',
        'migration-lite/references/version-map.md',
        'openrewrite-runner/SKILL.md',
        'openrewrite-runner/references/recipe-catalog.md',
        'openrewrite-runner/references/examples.md',
    ]
    for rel in expected_relative:
        full = os.path.join(tmp, rel)
        assert os.path.isfile(full), f'Missing: {full}'
    print('PASS: all 5 expected relative paths exist')
"
```

**2-D — missing source file raises `FileNotFoundError` with no partial install**
```bash
python3 -c "
import tempfile, os, shutil
os.environ['MIGRATION_MODE'] = 'lite'
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
import migration_oracle.mcp.tools.install as inst_mod
from migration_oracle.mcp.tools.install import install_migration_skill, SKILL_BUNDLES

# Temporarily point one bundle entry at a nonexistent file
orig = SKILL_BUNDLES['migration-lite'][0]
SKILL_BUNDLES['migration-lite'][0] = ('skills/does_not_exist.md', 'migration-lite/SKILL.md')
try:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            install_migration_skill(target='cursor', target_dir=tmp)
            print('FAIL: expected FileNotFoundError')
        except FileNotFoundError as e:
            assert 'does_not_exist' in str(e), str(e)
            # confirm no partial install: target dir should have nothing from this bundle attempt
            leftover = [f for f in os.listdir(tmp) if os.path.exists(f)]
            print(f'PASS: FileNotFoundError raised correctly — {e}')
finally:
    SKILL_BUNDLES['migration-lite'][0] = orig
"
```
Expected: `PASS` line. Manually inspect that the temp dir (before its context manager exits)
contains no half-written `migration-lite/` subdirectory — adapt the script to check this
synchronously if your implementation copies files in a different order than the manifest list.

**2-E — non-writable target directory raises `PermissionError`**
```bash
python3 -c "
import tempfile, os, stat
os.environ['MIGRATION_MODE'] = 'lite'
import sys
for m in list(sys.modules.keys()):
    if m.startswith('migration_oracle.mcp'):
        sys.modules.pop(m, None)
from migration_oracle.mcp.tools.install import install_migration_skill
with tempfile.TemporaryDirectory() as tmp:
    os.chmod(tmp, stat.S_IRUSR | stat.S_IXUSR)  # read+execute only, no write
    try:
        install_migration_skill(target='cursor', target_dir=tmp)
        print('FAIL: expected PermissionError')
    except PermissionError as e:
        assert tmp in str(e), f'Path not in error message: {e}'
        print(f'PASS: PermissionError raised with target path — {e}')
    finally:
        os.chmod(tmp, stat.S_IRWXU)  # restore so cleanup can delete it
"
```
Expected: `PASS`. Note: this check may behave differently when run as root (root often bypasses
permission bits) — run as a non-root user, or skip with a documented reason if CI runs as root.

---

## Level 3 — Skill content sanity

No services. Confirms the migration-lite skill text itself doesn't contradict the spec's
constraints — this is the check most likely to be skipped, and is exactly where the
"no recipe graph lookup in lite mode" constraint would silently regress if a future edit to
the skill file reintroduced it.

**3-A — migration-lite skill never references the forbidden tool**
```bash
grep -i "search_openrewrite_recipes" migration_oracle/mcp/skills/migration_lite_main.md \
  && echo "FAIL: migration-lite skill references search_openrewrite_recipes" \
  || echo "PASS: no reference to search_openrewrite_recipes in migration-lite skill"
```
Expected: `PASS`. Per spec.md NO_RECIPE_GRAPH_LOOKUP_IN_LITE.

**3-B — migration-lite skill never references full-only context tools**
```bash
for tool in create_migration_context get_pending_steps update_step_status \
            get_steps_for_scope_tier update_queried_entity close_migration_context; do
  grep -qi "$tool" migration_oracle/mcp/skills/migration_lite_main.md \
    && echo "FAIL: found reference to $tool" \
    && exit 1
done
echo "PASS: no full-only context tool referenced in migration-lite skill"
```
Expected: `PASS`.

**3-C — migration-lite skill explicitly names the three tools it does use**
```bash
for tool in analyze_upgrade_path search_migration_knowledge resolve_paysafe_dependency_by_service_name; do
  grep -qi "$tool" migration_oracle/mcp/skills/migration_lite_main.md \
    || { echo "FAIL: $tool not mentioned in migration-lite skill"; exit 1; }
done
echo "PASS: all three required tools are referenced in the skill text"
```
Expected: `PASS`.

**3-D — file-count threshold of 10 appears in the skill, matching spec.md FILE_COUNT_THRESHOLD**
```bash
grep -q "> 10\|10 files\|greater than 10" migration_oracle/mcp/skills/migration_lite_main.md \
  && echo "PASS: file-count threshold present in skill text" \
  || echo "FAIL: threshold not found — confirm exact phrasing matches spec.md"
```
Expected: `PASS`. If this fails on phrasing alone, read the file manually and confirm the
threshold value (not just the grep pattern) is 10, not some other number.

---

## Level 4 — Manual smoke test (full end-to-end, by hand)

No automated assertions — this is a human-run sanity pass before marking the spec complete.
Each step has an explicit expected outcome to compare against.

- [ ] **4-A** Run `MIGRATION_MODE=lite` and start the server using whatever your team's
  normal startup command is (stdio, sse, or streamable-http per `MCP_TRANSPORT`). Confirm
  the process starts without error and the startup log shows `mode=lite tools=4`.

- [ ] **4-B** From an MCP client (Claude Code, Cursor, or a raw MCP client script), call
  `tools/list` and visually confirm the response contains exactly the 4 expected tool names
  with their full parameter schemas intact (not stubs).

- [ ] **4-C** Call `install_migration_skill` from the live client (not a unit test) against
  your actual `~/.cursor/skills/` or `~/.claude/skills/` directory (or a scratch copy of it).
  Confirm both `migration-lite/` and `openrewrite-runner/` directories appear with the
  correct file layout from Check 2-C.

- [ ] **4-D** Open `migration-lite/SKILL.md` in the installed location and read it
  top to bottom as if you were the agent. Confirm the three-phase flow (Paysafe → single
  graph call → tiered execution) reads coherently and the file-count routing logic to
  `openrewrite-runner` is unambiguous.

- [ ] **4-E** Repeat 4-A through 4-C with `MIGRATION_MODE=full` (or unset) and confirm the
  full 24-tool surface and the `framework-migration` bundle install both work exactly as
  they did before this spec — this is the regression check that lite mode did not break
  full mode.

---

## Completion gate

Update `SPEC_ORGANIZATION.md` to `✅ Complete` for `006-migration-lite-mode` only when every
item below is checked.

| Check | Description | Result |
|---|---|---|
| 0-A | config.py imports cleanly, MIGRATION_MODE defaults to full | |
| 0-B | config.py has no circular-risk imports | |
| 0-C | invalid mode raises with correct message text | |
| 0-D | no tool module performs I/O at import time (manual review) | |
| 1-A | lite mode registers exactly the 4 expected shared tools | |
| 1-B | full mode registers exactly 24 tools | |
| 1-C | spot-checked full-only tools absent in lite mode | |
| 1-D | calling unknown tool raises protocol error, not internal exception | |
| 1-E | startup log reports correct mode and count | |
| 2-A | full mode installs exactly 5 files, correct metadata | |
| 2-B | lite mode installs exactly 5 files across 2 bundles | |
| 2-C | lite mode file layout matches manifest exactly | |
| 2-D | missing source file → FileNotFoundError, no partial install | |
| 2-E | non-writable target → PermissionError with path in message | |
| 3-A | migration-lite skill never calls search_openrewrite_recipes | |
| 3-B | migration-lite skill never references full-only context tools | |
| 3-C | migration-lite skill references all 3 tools it's allowed to use | |
| 3-D | file-count threshold of 10 present and correctly phrased | |
| 4-A | lite server starts cleanly, correct startup log | |
| 4-B | tools/list from a live client matches exactly | |
| 4-C | install_migration_skill works against a real skill directory | |
| 4-D | migration-lite SKILL.md reads coherently end-to-end | |
| 4-E | full mode unaffected — regression check passes | |
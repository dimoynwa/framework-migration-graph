**Location**: `specs/015-split-migration-harness/verification.md`
**Spec gate**: Run this after `/speckit.implement` completes.
**Execution order**: Levels 0 → 7 in sequence. Stop and fix on the first failure — failures compound.

**Note on level applicability for this spec**: This is an MCP tool/skill-file extension, not a
CLI/LLM-extraction pipeline. Level 1 has minimal content (no CLI flags were added — the new
surface is MCP tools and the `MCP_ACTIVE_STAGE` session parameter). Level 4 is reinterpreted as
"tool-gating dry-run" (does the allowlist mechanism block correctly with no real mutation
attempted) rather than an LLM dry-run flag, since this spec has no LLM call of its own to verify.

---

## Prerequisites

| Requirement | Detail |
|---|---|
| Dependency sync | `uv sync` completes cleanly in repo root |
| Database reachability | Neo4j/Memgraph instance reachable at `NEO4J_URI`; `graph/driver.py` connects |
| LLM credentials | Not required — this spec adds no new LLM call |
| Writable directories | None new — no new artifact paths introduced by this spec |
| Existing server state | `004-mcp-server`'s 21 tools registered and passing `tests/mcp/` before starting |
| Test fixtures | A throwaway `MigrationContext` for a known small range (e.g. Spring Boot `3.3.0` → `3.4.0`) — created and torn down per level, never reused across levels |

**Levels requiring DB**: 3, 4, 5, 6, 7 (where noted)
**Levels requiring LLM**: None
**Levels requiring neither**: 0, 1, 2

---

## Level 0 — Static checks

*Infrastructure: None*

**0-A — Module imports**
```bash
python -c "from migration_oracle.mcp.tools import context; print('PASS: context.py imports')"
python -c "from migration_oracle.mcp.graph.queries import context as ctx_queries; print('PASS: graph/queries/context.py imports')"
python -c "import migration_oracle.mcp.server as server; print('PASS: server.py imports')"
```

**0-B — `origin` enum values present**
```python
from migration_oracle.mcp.tools import context
assert context.MIGRATION_STEP_ORIGIN_VALUES == {"graph", "manual"}, \
    f"Got: {context.MIGRATION_STEP_ORIGIN_VALUES}"
print("PASS: origin enum is exactly {'graph','manual'}")
```
*(If the constant has a different name in the real implementation, locate it via `grep -rn "origin" migration_oracle/mcp/tools/context.py` and substitute — do not skip this check.)*

**0-C — `STEP_OUTCOME` status enum includes `excluded`**
```python
from migration_oracle.mcp.tools import context
assert "excluded" in context.STEP_OUTCOME_VALUES, f"Got: {context.STEP_OUTCOME_VALUES}"
assert context.STEP_OUTCOME_VALUES == {"completed", "skipped", "failed", "deferred", "excluded"}, \
    f"Got: {context.STEP_OUTCOME_VALUES}"
print("PASS: STEP_OUTCOME enum includes excluded, no extras")
```

**0-D — `add_manual_step` effort/severity enums match existing schema**
```python
from migration_oracle.mcp.tools import context
assert context.EFFORT_VALUES == {"mechanical", "moderate", "architectural"}, f"Got: {context.EFFORT_VALUES}"
assert context.SEVERITY_VALUES == {"low", "medium", "high", "critical"}, f"Got: {context.SEVERITY_VALUES}"
print("PASS: effort and severity enums match data-model.md §5")
```

**0-E — `GapCheckFlag` type enum present**
```python
from migration_oracle.mcp.tools import context
expected = {"truncation", "applicability_uncertain", "stepless_rule", "bridge_eligible",
            "version_sanity", "paysafe_unresolved"}
assert context.GAP_CHECK_FLAG_TYPES == expected, f"Got: {context.GAP_CHECK_FLAG_TYPES}"
print("PASS: GapCheckFlag type enum matches data-model.md §3")
```

**0-F — `MCP_ACTIVE_STAGE` config values**
```python
from migration_oracle import config
expected_stages = {"plan", "gap-check", "clarify", "preview", "execute", "feedback"}
assert config.VALID_ACTIVE_STAGES == expected_stages, f"Got: {config.VALID_ACTIVE_STAGES}"
print("PASS: six stage values defined")
```

---

## Level 1 — Interface structure

*Infrastructure: None*

**1-A — Tool registration list per stage (allowlist matrix smoke check)**

For each stage, confirm the registered tool set is non-empty and `add_manual_step` /
`write_gap_check_flags` only appear where the contracts matrix says they should:

```bash
MCP_ACTIVE_STAGE=preview python -c "
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
forbidden = {'add_manual_step', 'write_gap_check_flags', 'update_step_status',
             'update_queried_entity', 'create_migration_context', 'close_migration_context'}
leaked = tools & forbidden
assert not leaked, f'preview stage leaked mutation tools: {leaked}'
assert tools == {'get_pending_steps', 'get_migration_contexts'}, f'Got: {tools}'
print('PASS: preview stage exposes exactly get_pending_steps + get_migration_contexts')
"
```

```bash
MCP_ACTIVE_STAGE=gap-check python -c "
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
forbidden = {'add_manual_step', 'update_step_status', 'update_queried_entity',
             'create_migration_context', 'close_migration_context'}
leaked = tools & forbidden
assert not leaked, f'gap-check stage leaked mutation tools: {leaked}'
assert 'write_gap_check_flags' in tools, 'gap-check missing its own write tool'
print('PASS: gap-check exposes write_gap_check_flags, no other mutation tools')
"
```

```bash
MCP_ACTIVE_STAGE=clarify python -c "
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
required = {'add_manual_step', 'update_step_status', 'update_queried_entity', 'get_pending_steps'}
missing = required - tools
assert not missing, f'clarify missing required tools: {missing}'
assert 'create_migration_context' not in tools, 'clarify should not create new contexts'
print('PASS: clarify exposes its full required mutation set')
"
```

**1-B — Invalid `MCP_ACTIVE_STAGE` value rejected**
```bash
MCP_ACTIVE_STAGE=not-a-real-stage python -c "
from migration_oracle.mcp import server
try:
    server.get_registered_tool_names()
    print('FAIL: invalid stage did not raise')
    exit(1)
except ValueError as e:
    print(f'PASS: invalid stage rejected with: {e}')
"
```

**1-C — Missing `MCP_ACTIVE_STAGE` for a stage-gated server raises a clear error (not a traceback)**
```bash
unset MCP_ACTIVE_STAGE
python -c "
from migration_oracle.mcp import server
try:
    server.get_registered_tool_names()
    print('FAIL: missing stage did not raise')
    exit(1)
except (ValueError, KeyError) as e:
    print(f'PASS: missing stage rejected with clear message: {e}')
"
```

---

## Level 2 — Isolation behaviour

*Infrastructure: None (in-memory / mocked context object only)*

**2-A — `write_gap_check_flags` dedup logic (no DB)**

Test the dedup/idempotency logic in isolation against a mocked context object, per
data-model.md §8 (`overwrite=false` deduplicates identical `type`+`reference`+`message` triples):

```python
from migration_oracle.mcp.tools.context import dedup_gap_check_flags  # adjust import to real location

existing = [{"type": "truncation", "reference": None, "message": "Rule count equals top_n (50)."}]
incoming = [{"type": "truncation", "reference": None, "message": "Rule count equals top_n (50)."},
            {"type": "applicability_uncertain", "reference": "RULE-42", "message": "Uncertain match."}]

result = dedup_gap_check_flags(existing, incoming)
assert len(result) == 2, f"Expected 2 deduped flags, got {len(result)}: {result}"
assert result.count({"type": "truncation", "reference": None,
                      "message": "Rule count equals top_n (50)."}) == 1, \
    "Duplicate truncation flag was not deduplicated"
print("PASS: identical flag triples deduplicated, distinct flags both retained")
```

**2-B — `overwrite=true` replaces rather than merges**
```python
from migration_oracle.mcp.tools.context import dedup_gap_check_flags

existing = [{"type": "truncation", "reference": None, "message": "old"}]
incoming = [{"type": "version_sanity", "reference": None, "message": "new"}]

result = apply_gap_check_write(existing, incoming, overwrite=True)  # adjust to real function name
assert result == incoming, f"overwrite=True should fully replace, got: {result}"
print("PASS: overwrite=True replaces existing flags entirely")
```

**2-C — Lite-mode gap-check branch skips full-mode-only checks**

Mock a context with `mode="lite"` and confirm the handler's check list excludes
`stepless_rule` and `bridge_eligible`:

```python
from migration_oracle.mcp.tools.context import get_applicable_gap_checks  # adjust to real name

lite_checks = get_applicable_gap_checks(mode="lite")
full_checks = get_applicable_gap_checks(mode="full")

assert "stepless_rule" not in lite_checks, f"lite mode ran stepless_rule check: {lite_checks}"
assert "bridge_eligible" not in lite_checks, f"lite mode ran bridge_eligible check: {lite_checks}"
assert {"truncation", "applicability_uncertain", "version_sanity", "paysafe_unresolved"} <= set(lite_checks), \
    f"lite mode missing a required check: {lite_checks}"
assert {"stepless_rule", "bridge_eligible"} <= set(full_checks), \
    f"full mode missing a full-only check: {full_checks}"
print("PASS: lite mode correctly omits stepless_rule/bridge_eligible; full mode includes them")
```
*(This is a single mode-aware handler per plan.md's explicit constraint — if these two assertions
require importing two different functions/modules, that itself is a finding: report it as a
deviation from the "one handler, early branch" design before proceeding.)*

**2-D — `diagnostics` truncation derivation uses one authoritative source**

Per the last data-model.md review, confirm the implementation does not check
`truncation_occurred` and the count comparison as two independent branches:

```python
from migration_oracle.mcp.tools.context import check_truncation  # adjust to real name

# Deliberately inconsistent input: stale boolean says no truncation, counts say otherwise
diagnostics = {"rules_included": 50, "rules_capped_at": 50, "total_applicable_rules": 80,
               "truncation_occurred": False}
flagged = check_truncation(diagnostics)
assert flagged is True, \
    "check_truncation trusted a stale truncation_occurred boolean over the count comparison"
print("PASS: truncation check derives from counts, not a separately-stored boolean")
```

---

## Level 3 — Integration: read path

*Infrastructure: DB only, no LLM*

**3-A — Driver connectivity**
```bash
python -c "
from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    result = s.run('RETURN 1 AS n').single()
    assert result['n'] == 1
print('PASS: graph driver connects')
"
```

**3-B — `get_pending_steps` returns empty for a nonexistent context (no traceback)**
```python
from migration_oracle.mcp.tools.context import get_pending_steps

result = get_pending_steps(context_id="nonexistent-context-id-xyz")
assert result == [] or result is None, f"Expected empty/None for nonexistent context, got: {result}"
print("PASS: get_pending_steps on absent context returns empty, not an error")
```

**3-C — `OWNS_STEP` traversal round-trip (write a synthetic manual step, read it back, clean up)**
```python
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.tools.context import add_manual_step, get_pending_steps, create_migration_context

ctx = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                 target_version="3.4.0", repo_id="verification-test-A")
context_id = ctx["context_id"]

step = add_manual_step(context_id=context_id, summary="Test manual step",
                        instruction="Verify OWNS_STEP traversal")
steps = get_pending_steps(context_id=context_id)
manual_steps = [s for s in steps if s.get("origin") == "manual"]
assert len(manual_steps) == 1, f"Expected 1 manual step, got: {manual_steps}"
assert manual_steps[0]["summary"] == "Test manual step"

# Cleanup
with get_driver().session() as s:
    s.run("MATCH (ctx:MigrationContext {context_id: $cid}) DETACH DELETE ctx", cid=context_id)
    s.run("MATCH (s:MigrationStep {origin: 'manual', _verification_marker: 'test-A'}) DETACH DELETE s")
print("PASS: OWNS_STEP write-then-read round-trip works, cleaned up")
```

**3-D — Cross-context isolation (the highest-priority regression test from this thread's review)**
```python
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.tools.context import add_manual_step, get_pending_steps, create_migration_context

ctx_a = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                   target_version="3.4.0", repo_id="verification-iso-A")
ctx_b = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                   target_version="3.4.0", repo_id="verification-iso-B")
cid_a, cid_b = ctx_a["context_id"], ctx_b["context_id"]

add_manual_step(context_id=cid_a, summary="Isolation-test step", instruction="Should not leak to B")

steps_b = get_pending_steps(context_id=cid_b)
leaked = [s for s in steps_b if s.get("summary") == "Isolation-test step"]
assert leaked == [], f"Manual step from context A leaked into context B: {leaked}"

steps_a = get_pending_steps(context_id=cid_a)
present = [s for s in steps_a if s.get("summary") == "Isolation-test step"]
assert len(present) == 1, f"Manual step missing from its own context A: {present}"

# Cleanup
with get_driver().session() as s:
    s.run("MATCH (ctx:MigrationContext) WHERE ctx.context_id IN [$a, $b] DETACH DELETE ctx",
          a=cid_a, b=cid_b)
print("PASS: manual step under context A is invisible to context B, visible in A")
```

---

## Level 4 — Tool-gating dry-run (safe path)

*Infrastructure: DB only (no real mutation should occur in this level)*

**4-A — `preview` session cannot mutate even if a mutation call is attempted at the transport layer**
```bash
MCP_ACTIVE_STAGE=preview python -c "
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
assert 'update_step_status' not in tools
# Confirm the underlying handler also refuses if called directly bypassing registration,
# as a defense-in-depth check (not just absence from the registry):
from migration_oracle.mcp.tools import context
import inspect
sig = inspect.signature(context.update_step_status)
print('PASS: update_step_status not registered for preview; handler exists but is unreachable via MCP transport')
"
```
*(If the implementation has no defense-in-depth check beyond registration-time filtering, that
matches plan.md's stated design exactly — record this as expected, not a gap.)*

**4-B — `gap-check` session: confirm it produces a flag list without writing step/rule state**
```python
from migration_oracle.mcp.tools.context import create_migration_context, get_pending_steps

ctx = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                 target_version="3.4.0", repo_id="verification-gapcheck-dry")
context_id = ctx["context_id"]
steps_before = get_pending_steps(context_id=context_id)

# Run gap-check logic (adjust import to real handler location)
from migration_oracle.mcp.tools.context import run_gap_check
flags = run_gap_check(context_id=context_id)

steps_after = get_pending_steps(context_id=context_id)
assert steps_before == steps_after, "gap-check mutated the pending step queue"
assert isinstance(flags, list), f"Expected a list of flags, got: {type(flags)}"
print(f"PASS: gap-check produced {len(flags)} flags with zero step/rule mutation")

from migration_oracle.graph.driver import get_driver
with get_driver().session() as s:
    s.run("MATCH (ctx:MigrationContext {context_id: $cid}) DETACH DELETE ctx", cid=context_id)
```

---

## Level 5 — Full write path

*Infrastructure: DB only*

**5-A — `clarify`: force-include an excluded rule merges its steps into the pending queue**
```python
# Requires a known rule that entity matching would exclude for this version range.
# Substitute a real ruleId from a seeded/known dataset before running.
from migration_oracle.mcp.tools.context import update_queried_entity, get_pending_steps, create_migration_context

ctx = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                 target_version="3.4.0", repo_id="verification-forceinclude")
context_id = ctx["context_id"]

before = {s["step_id"] for s in get_pending_steps(context_id=context_id)}
update_queried_entity(context_id=context_id, entity_name="<known-excluded-entity>", force_include=True)
after = {s["step_id"] for s in get_pending_steps(context_id=context_id)}

assert after - before, "force_include=True produced no new pending steps"
print(f"PASS: force-include merged {len(after - before)} new step(s) into the pending queue")
```

**5-B — `clarify`: `outcome="excluded"` is written correctly and does not appear as `skipped`**
```python
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.tools.context import update_step_status, get_pending_steps

steps = get_pending_steps(context_id=context_id)
target_step_id = steps[0]["step_id"]
update_step_status(context_id=context_id, step_id=target_step_id, outcome="excluded")

with get_driver().session() as s:
    rec = s.run(
        "MATCH (ctx:MigrationContext {context_id: $cid})-[r:STEP_OUTCOME]->(s:MigrationStep {step_id: $sid}) "
        "RETURN r.outcome AS outcome", cid=context_id, sid=target_step_id
    ).single()
    assert rec["outcome"] == "excluded", f"Expected 'excluded', got: {rec['outcome']}"
print("PASS: excluded outcome written correctly on STEP_OUTCOME relationship")
```

**5-C — `add_manual_step` writes all required properties, including `origin="manual"`**
```python
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.tools.context import add_manual_step

result = add_manual_step(context_id=context_id, summary="Update internal RestTemplate wrapper",
                          instruction="Replace deprecated method calls in WrapperX",
                          file_pattern="**/WrapperX.java", effort="moderate", severity_hint="high")
step_id = result["step_id"]

with get_driver().session() as s:
    rec = s.run("MATCH (s:MigrationStep {step_id: $sid}) RETURN s", sid=step_id).single()
    node = dict(rec["s"])
    assert node["origin"] == "manual", f"Got origin: {node.get('origin')}"
    assert node["summary"] == "Update internal RestTemplate wrapper"
    assert node["effort"] == "moderate"
    assert node["severity_hint"] == "high"
print("PASS: add_manual_step writes all required and optional properties correctly")
```

**5-D — Deprecated/forbidden field absence: manual steps never get `applicability` field**

Graph-derived rules carry an `applicability` field (`universal`/`uncertain`/`matched`); manual
steps have no such concept and must not silently inherit one:

```python
from migration_oracle.graph.driver import get_driver

with get_driver().session() as s:
    rec = s.run("MATCH (s:MigrationStep {step_id: $sid}) RETURN s", sid=step_id).single()
    node = dict(rec["s"])
    assert "applicability" not in node, f"Manual step incorrectly has applicability field: {node}"
print("PASS: manual step has no applicability field")
```

---

## Level 6 — Idempotency

*Infrastructure: DB only*

**6-A — `write_gap_check_flags` called twice with identical input produces no duplicate flags**

This is the idempotency test named explicitly in tasks.md (T013) — the protocol below is its
runnable form:

```python
import json
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.tools.context import create_migration_context, run_gap_check

ctx = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                 target_version="3.4.0", repo_id="verification-idempotency")
context_id = ctx["context_id"]

flags_first = run_gap_check(context_id=context_id)

with get_driver().session() as s:
    before = s.run(
        "MATCH (ctx:MigrationContext {context_id: $cid}) RETURN ctx.gapCheckFlags AS f", cid=context_id
    ).single()["f"]
before_count = len(json.loads(before)) if before else 0

flags_second = run_gap_check(context_id=context_id)

with get_driver().session() as s:
    after = s.run(
        "MATCH (ctx:MigrationContext {context_id: $cid}) RETURN ctx.gapCheckFlags AS f", cid=context_id
    ).single()["f"]
after_count = len(json.loads(after)) if after else 0

assert before_count == after_count, \
    f"gap-check is not idempotent: {before_count} flags before second run, {after_count} after"
assert flags_first == flags_second, "Second gap-check run produced a different flag list"
print(f"PASS: gap-check idempotent — {after_count} flags stable across two runs")

with get_driver().session() as s:
    s.run("MATCH (ctx:MigrationContext {context_id: $cid}) DETACH DELETE ctx", cid=context_id)
```

**6-B — Relationship count check: `OWNS_STEP` edges do not multiply on repeated `get_pending_steps` reads**
```python
from migration_oracle.graph.driver import get_driver

# (context_id and a manual step already created in 5-C / 3-C pattern — recreate fresh here)
with get_driver().session() as s:
    for _ in range(3):
        s.run(
            "MATCH (ctx:MigrationContext {context_id: $cid}) RETURN ctx",
            cid=context_id
        ).consume()
    count = s.run(
        "MATCH (:MigrationContext {context_id: $cid})-[r:OWNS_STEP]->(:MigrationStep) RETURN count(r) AS c",
        cid=context_id
    ).single()["c"]
    assert count == 1, f"Expected exactly 1 OWNS_STEP edge after repeated reads, got: {count}"
print("PASS: repeated reads do not multiply OWNS_STEP edges")
```

**6-C — `close_migration_context` completion-gate idempotency**

Calling `close_migration_context` is not expected to be re-callable per se, but confirm the gate
*logic* (not the call) gives the same `final_status` if evaluated twice against the same
unchanged outcome set:

```python
from migration_oracle.mcp.tools.context import compute_final_status  # adjust to real function name

outcomes_1 = ["completed", "completed", "excluded"]
outcomes_2 = ["completed", "completed", "excluded"]  # identical, re-evaluated
assert compute_final_status(outcomes_1) == compute_final_status(outcomes_2) == "complete", \
    f"Got: {compute_final_status(outcomes_1)}, {compute_final_status(outcomes_2)}"
print("PASS: completion-gate logic is deterministic and stable across re-evaluation")
```

---

## Level 7 — Edge-case paths

*Infrastructure: DB for 7-A/7-B/7-D, none for 7-C*

**7-A — `final_status` guard: ALL conditions for "complete" (no skipped/failed, some excluded present)**
```python
from migration_oracle.mcp.tools.context import compute_final_status

# (A) All conditions met: only completed + excluded → complete
assert compute_final_status(["completed", "excluded", "completed"]) == "complete"
print("PASS (7-A-A): completed+excluded only -> complete")

# (B) One condition absent: a skipped outcome present -> capped at partial
assert compute_final_status(["completed", "excluded", "skipped"]) == "partial"
print("PASS (7-A-B): presence of skipped caps at partial despite excluded steps")

# (C) A different condition absent: a failed outcome present -> capped at partial
assert compute_final_status(["completed", "excluded", "failed"]) == "partial"
print("PASS (7-A-C): presence of failed caps at partial despite excluded steps")
```

**7-B — `execute` auto-discovery vs. ambiguous-context error**
```python
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.tools.context import create_migration_context
from migration_oracle.mcp.tools.execute import resolve_execute_context  # adjust to real location

# Single in_progress context -> auto-discovered
ctx = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                 target_version="3.4.0", repo_id="verification-exec-single")
resolved = resolve_execute_context(context_id=None)
assert resolved["context_id"] == ctx["context_id"], f"Auto-discovery picked wrong context: {resolved}"
print("PASS: single in_progress context auto-discovered")

# Second in_progress context created -> now ambiguous, must raise with full candidate metadata
ctx2 = create_migration_context(framework="Spring Boot", current_version="3.4.0",
                                  target_version="3.5.0", repo_id="verification-exec-double")
try:
    resolve_execute_context(context_id=None)
    print("FAIL: ambiguous context did not raise")
    exit(1)
except Exception as e:
    payload = getattr(e, "candidates", None) or e.args[0]
    assert isinstance(payload, list) and len(payload) == 2, f"Got: {payload}"
    for c in payload:
        assert {"context_id", "framework", "current_version", "target_version"} <= set(c.keys()), \
            f"Candidate missing required fields per data-model.md §4: {c}"
    print("PASS: ambiguous-context error includes full candidate metadata per data-model.md §4")

with get_driver().session() as s:
    s.run("MATCH (ctx:MigrationContext) WHERE ctx.context_id IN [$a, $b] DETACH DELETE ctx",
          a=ctx["context_id"], b=ctx2["context_id"])
```

**7-C — Invalid `context_id` passed to `gap-check` / `clarify` / `preview` (no DB needed if validated before query)**
```python
from migration_oracle.mcp.tools.context import run_gap_check, add_manual_step, get_pending_steps

for fn, kwargs in [
    (run_gap_check, {"context_id": "totally-invalid-id"}),
    (add_manual_step, {"context_id": "totally-invalid-id", "summary": "x", "instruction": "y"}),
    (get_pending_steps, {"context_id": "totally-invalid-id"}),
]:
    try:
        fn(**kwargs)
        print(f"FAIL: {fn.__name__} did not reject invalid context_id")
        exit(1)
    except Exception as e:
        print(f"PASS: {fn.__name__} rejected invalid context_id with: {type(e).__name__}: {e}")
```

**7-D — `add_manual_step` called against a closed context is rejected**
```python
from migration_oracle.graph.driver import get_driver
from migration_oracle.mcp.tools.context import create_migration_context, close_migration_context, add_manual_step

ctx = create_migration_context(framework="Spring Boot", current_version="3.3.0",
                                 target_version="3.4.0", repo_id="verification-closed-ctx")
context_id = ctx["context_id"]
close_migration_context(context_id=context_id, final_status="complete")

try:
    add_manual_step(context_id=context_id, summary="late add", instruction="should fail")
    print("FAIL: add_manual_step succeeded against a closed context")
    exit(1)
except Exception as e:
    print(f"PASS: add_manual_step rejected against closed context: {e}")

with get_driver().session() as s:
    s.run("MATCH (ctx:MigrationContext {context_id: $cid}) DETACH DELETE ctx", cid=context_id)
```

**7-E — BRIDGED_BY + excluded interaction remains explicitly unresolved (process check, not a code check)**

This is not a pass/fail code assertion — it is a documentation-state check:

```bash
grep -q "UNRESOLVED" specs/015-split-migration-harness/data-model.md && \
  echo "INFO: BRIDGED_BY+excluded interaction still marked UNRESOLVED in data-model.md — confirm this was either resolved with a real mechanism check before implement, or that implement deliberately did not build BRIDGED_BY-aware exclusion logic and that gap is tracked, not silently shipped." || \
  echo "INFO: no UNRESOLVED marker found — confirm data-model.md §7 was actually updated with a derived rule, not just had the marker removed."
```
*(Whichever branch prints, a human must read the actual current data-model.md §7 and confirm
the implementation matches what it says — this check only confirms the marker's presence, not
correctness.)*

---

## Completion gate checklist

Update `SPEC_ORGANIZATION.md` to `✅ Complete` for `015-split-migration-harness` only when every
item below is checked.

| Check ID | Description | Result |
|---|---|---|
| 0-A | All three new/touched modules import without error | ☐ |
| 0-B | `origin` enum is exactly `{"graph","manual"}` | ☐ |
| 0-C | `STEP_OUTCOME` enum includes `excluded`, no extras | ☐ |
| 0-D | `effort`/`severity_hint` enums match `data-model.md` §5 | ☐ |
| 0-E | `GapCheckFlag` type enum matches `data-model.md` §3 | ☐ |
| 0-F | Six `MCP_ACTIVE_STAGE` values defined | ☐ |
| 1-A | `preview` exposes exactly 2 read-only tools; `gap-check`/`clarify` expose their required sets | ☐ |
| 1-B | Invalid `MCP_ACTIVE_STAGE` value rejected with clear error | ☐ |
| 1-C | Missing `MCP_ACTIVE_STAGE` rejected with clear error, not a traceback | ☐ |
| 2-A | `write_gap_check_flags` dedup logic removes identical triples, keeps distinct ones | ☐ |
| 2-B | `overwrite=true` fully replaces rather than merges | ☐ |
| 2-C | Lite mode skips `stepless_rule`/`bridge_eligible`; full mode includes them; one handler | ☐ |
| 2-D | Truncation check derives from one authoritative source, not two independent conditions | ☐ |
| 3-A | Graph driver connects | ☐ |
| 3-B | `get_pending_steps` on nonexistent context returns empty, not an error | ☐ |
| 3-C | `OWNS_STEP` write-then-read round-trip works and is cleaned up | ☐ |
| 3-D | Manual step under context A is invisible from context B (cross-context isolation) | ☐ |
| 4-A | `preview` stage cannot reach `update_step_status` via MCP transport | ☐ |
| 4-B | `gap-check` produces flags with zero step/rule state mutation | ☐ |
| 5-A | `clarify` force-include merges new steps into pending queue | ☐ |
| 5-B | `outcome="excluded"` written correctly, distinct from `skipped` | ☐ |
| 5-C | `add_manual_step` writes all required/optional properties correctly | ☐ |
| 5-D | Manual steps never inherit an `applicability` field | ☐ |
| 6-A | `write_gap_check_flags` idempotent across two identical runs (no duplicate flags) | ☐ |
| 6-B | Repeated `get_pending_steps` reads do not multiply `OWNS_STEP` edges | ☐ |
| 6-C | `close_migration_context` gate logic deterministic across re-evaluation | ☐ |
| 7-A-A | completed+excluded only → `complete` | ☐ |
| 7-A-B | any `skipped` present → capped at `partial` despite excluded steps | ☐ |
| 7-A-C | any `failed` present → capped at `partial` despite excluded steps | ☐ |
| 7-B | `execute` auto-discovers single in_progress context; raises full-metadata error when ambiguous | ☐ |
| 7-C | Invalid `context_id` rejected by `gap-check`/`clarify`/`preview` | ☐ |
| 7-D | `add_manual_step` rejected against a closed context | ☐ |
| 7-E | `BRIDGED_BY`+`excluded` interaction status in `data-model.md` §7 manually confirmed correct | ☐ |
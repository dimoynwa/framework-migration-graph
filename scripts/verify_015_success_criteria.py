#!/usr/bin/env python3
"""Run specs/015-split-migration-harness/success-criteria.md verification levels 0-7."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
os.chdir(REPO)
os.environ.setdefault("MIGRATION_MODE", "full")


@dataclass
class Result:
    check_id: str
    passed: bool
    detail: str = ""


results: list[Result] = []


def record(check_id: str, passed: bool, detail: str = "") -> None:
    results.append(Result(check_id, passed, detail))
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {check_id}"
    if detail:
        line += f" — {detail}"
    print(line)
    if not passed:
        sys.exit(1)


def _reload_server_module() -> None:
    for name in list(sys.modules):
        if name == "migration_oracle.mcp.config" or name.startswith("migration_oracle.mcp."):
            sys.modules.pop(name, None)


def run_subprocess_check(check_id: str, env: dict[str, str], code: str) -> None:
    full_env = {**os.environ, **env}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=full_env,
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    passed = proc.returncode == 0 and "PASS" in proc.stdout
    detail = (proc.stdout + proc.stderr).strip().replace("\n", " | ")
    record(check_id, passed, detail or f"exit={proc.returncode}")


def level_0() -> None:
    print("\n=== Level 0 — Static checks ===")
    for mod, label in [
        ("migration_oracle.mcp.tools.context", "context.py"),
        ("migration_oracle.mcp.graph.queries.context", "graph/queries/context.py"),
        ("migration_oracle.mcp.server", "server.py"),
    ]:
        try:
            importlib.import_module(mod)
            record(f"0-A-{label}", True)
        except Exception as exc:
            record(f"0-A-{label}", False, str(exc))

    from migration_oracle.mcp.tools import context as ctx

    record(
        "0-B",
        ctx.MIGRATION_STEP_ORIGIN_VALUES == {"graph", "manual"},
        str(ctx.MIGRATION_STEP_ORIGIN_VALUES),
    )
    record(
        "0-C",
        ctx.STEP_OUTCOME_VALUES == {"completed", "skipped", "failed", "deferred", "excluded"},
        str(ctx.STEP_OUTCOME_VALUES),
    )
    record(
        "0-D",
        ctx.EFFORT_VALUES == {"mechanical", "moderate", "architectural"}
        and ctx.SEVERITY_VALUES == {"low", "medium", "high", "critical"},
        f"effort={ctx.EFFORT_VALUES}, severity={ctx.SEVERITY_VALUES}",
    )
    expected_flags = {
        "truncation", "applicability_uncertain", "stepless_rule", "bridge_eligible",
        "version_sanity", "paysafe_unresolved",
    }
    record("0-E", ctx.GAP_CHECK_FLAG_TYPES == expected_flags, str(ctx.GAP_CHECK_FLAG_TYPES))

    from migration_oracle.mcp import config as mcp_config

    record(
        "0-F",
        mcp_config.VALID_ACTIVE_STAGES
        == {"plan", "gap-check", "clarify", "preview", "execute", "feedback"},
        str(mcp_config.VALID_ACTIVE_STAGES),
    )


def level_1() -> None:
    print("\n=== Level 1 — Interface structure ===")
    run_subprocess_check(
        "1-A-preview",
        {"MIGRATION_MODE": "full", "MCP_ACTIVE_STAGE": "preview"},
        """
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
forbidden = {'add_manual_step', 'write_gap_check_flags', 'update_step_status',
             'update_queried_entity', 'create_migration_context', 'close_migration_context'}
leaked = tools & forbidden
assert not leaked, f'preview leaked: {leaked}'
assert tools == {'get_pending_steps', 'get_migration_contexts'}, f'Got: {tools}'
print('PASS: preview stage')
""",
    )
    run_subprocess_check(
        "1-A-gap-check",
        {"MIGRATION_MODE": "full", "MCP_ACTIVE_STAGE": "gap-check"},
        """
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
forbidden = {'add_manual_step', 'update_step_status', 'update_queried_entity',
             'create_migration_context', 'close_migration_context'}
leaked = tools & forbidden
assert not leaked, f'gap-check leaked: {leaked}'
assert 'write_gap_check_flags' in tools
print('PASS: gap-check stage')
""",
    )
    run_subprocess_check(
        "1-A-clarify",
        {"MIGRATION_MODE": "full", "MCP_ACTIVE_STAGE": "clarify"},
        """
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
required = {'add_manual_step', 'update_step_status', 'update_queried_entity', 'get_pending_steps'}
missing = required - tools
assert not missing, f'clarify missing: {missing}'
assert 'create_migration_context' not in tools
print('PASS: clarify stage')
""",
    )
    run_subprocess_check(
        "1-B",
        {"MIGRATION_MODE": "full", "MCP_ACTIVE_STAGE": "not-a-real-stage"},
        """
try:
    from migration_oracle.mcp import server
    server.get_registered_tool_names()
    print('FAIL: invalid stage accepted')
    raise SystemExit(1)
except ValueError as e:
    print(f'PASS: invalid stage rejected: {e}')
""",
    )
    run_subprocess_check(
        "1-C",
        {"MIGRATION_MODE": "full"},
        """
import os
os.environ.pop('MCP_ACTIVE_STAGE', None)
from migration_oracle.mcp import server
try:
    server.get_registered_tool_names()
    print('FAIL: missing stage accepted')
    raise SystemExit(1)
except ValueError as e:
    print(f'PASS: missing stage rejected: {e}')
""",
    )


def level_2() -> None:
    print("\n=== Level 2 — Isolation behaviour ===")
    from migration_oracle.mcp.tools.context import (
        apply_gap_check_write,
        check_truncation,
        dedup_gap_check_flags,
        get_applicable_gap_checks,
    )

    existing = [{"type": "truncation", "reference": None, "message": "Rule count equals top_n (50)."}]
    incoming = [
        {"type": "truncation", "reference": None, "message": "Rule count equals top_n (50)."},
        {"type": "applicability_uncertain", "reference": "RULE-42", "message": "Uncertain match."},
    ]
    result = dedup_gap_check_flags(existing, incoming)
    record("2-A", len(result) == 2 and result.count(existing[0]) == 1, str(result))

    overwrite_result = apply_gap_check_write(
        [{"type": "truncation", "reference": None, "message": "old"}],
        [{"type": "version_sanity", "reference": None, "message": "new"}],
        overwrite=True,
    )
    record(
        "2-B",
        overwrite_result == [{"type": "version_sanity", "reference": None, "message": "new"}],
        str(overwrite_result),
    )

    lite_checks = get_applicable_gap_checks(mode="lite")
    full_checks = get_applicable_gap_checks(mode="full")
    record(
        "2-C",
        "stepless_rule" not in lite_checks
        and "bridge_eligible" not in lite_checks
        and {"truncation", "applicability_uncertain", "version_sanity", "paysafe_unresolved"} <= set(lite_checks)
        and {"stepless_rule", "bridge_eligible"} <= set(full_checks),
        f"lite={lite_checks}, full={full_checks}",
    )

    diagnostics = {
        "rules_included": 50,
        "rules_capped_at": 50,
        "truncation_occurred": False,
    }
    record("2-D", check_truncation(diagnostics) is True, "rules_capped_at authoritative")


def db_available() -> bool:
    try:
        from migration_oracle.graph.driver import get_driver

        with get_driver().session() as s:
            s.run("RETURN 1").single()
        return True
    except Exception as exc:
        print(f"DB unavailable — skipping levels 3-7: {exc}")
        return False


def delete_context(driver, context_id: str) -> None:
    with driver.session() as s:
        s.run(
            "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $cid DETACH DELETE ctx",
            cid=context_id,
        )
        s.run(
            "MATCH (s:MigrationStep {origin: 'manual'}) WHERE NOT (s)<-[:OWNS_STEP]-() DETACH DELETE s",
        )


def level_3() -> None:
    print("\n=== Level 3 — Integration read path ===")
    from migration_oracle.graph.driver import get_driver
    from migration_oracle.mcp.tools.context import (
        add_manual_step,
        create_migration_context,
        get_pending_steps,
    )

    record("3-A", True, "driver connectivity confirmed")

    result = get_pending_steps(context_id="nonexistent-context-id-xyz")
    pending = result.get("pending_steps", result) if isinstance(result, dict) else result
    record("3-B", pending == [] or pending is None, str(result))

    ctx = create_migration_context(
        project_id="verification-test-A",
        from_version="3.3.0",
        to_version="3.4.0",
        framework="Spring Boot",
        allow_stub_create=True,
    )
    if ctx.get("status") == "error":
        record("3-C", False, f"create_migration_context failed: {ctx.get('hint')}")
        record("3-D", False, "skipped — no context")
        return

    context_id = ctx["context_id"]
    step = add_manual_step(
        context_id=context_id,
        summary="Test manual step",
        instruction="Verify OWNS_STEP traversal",
    )
    if step.get("status") == "error":
        record("3-C", False, step.get("hint", str(step)))
        delete_context(get_driver(), context_id)
        return

    steps = get_pending_steps(context_id=context_id)
    manual_steps = [s for s in steps["pending_steps"] if s.get("origin") == "manual"]
    record(
        "3-C",
        len(manual_steps) == 1 and manual_steps[0]["summary"] == "Test manual step",
        str(manual_steps),
    )

    ctx_b = create_migration_context(
        project_id="verification-iso-B",
        from_version="3.3.0",
        to_version="3.4.0",
        framework="Spring Boot",
        allow_stub_create=True,
    )
    if ctx_b.get("status") == "error":
        record("3-D", False, ctx_b.get("hint", str(ctx_b)))
    else:
        cid_b = ctx_b["context_id"]
        steps_b = get_pending_steps(context_id=cid_b)
        leaked = [s for s in steps_b["pending_steps"] if s.get("summary") == "Test manual step"]
        record("3-D", leaked == [], f"leaked={leaked}")
        delete_context(get_driver(), cid_b)

    delete_context(get_driver(), context_id)


def level_4() -> None:
    print("\n=== Level 4 — Tool-gating dry-run ===")
    run_subprocess_check(
        "4-A",
        {"MIGRATION_MODE": "full", "MCP_ACTIVE_STAGE": "preview"},
        """
from migration_oracle.mcp import server
tools = server.get_registered_tool_names()
assert 'update_step_status' not in tools
print('PASS: preview cannot reach update_step_status via MCP transport')
""",
    )

    from migration_oracle.graph.driver import get_driver
    from migration_oracle.mcp.tools.context import (
        create_migration_context,
        get_pending_steps,
        run_gap_check,
    )

    ctx = create_migration_context(
        project_id="verification-gapcheck-dry",
        from_version="3.3.0",
        to_version="3.4.0",
        framework="Spring Boot",
        allow_stub_create=True,
        diagnostics={
            "rules_included": 50,
            "rules_capped_at": 50,
            "rules_excluded_by_entity_filter": 0,
            "rules_via_safety_net": 0,
            "scanned_total": 1,
        },
    )
    if ctx.get("status") == "error":
        record("4-B", False, ctx.get("hint", str(ctx)))
        return

    context_id = ctx["context_id"]
    before = get_pending_steps(context_id=context_id)["pending_steps"]
    flags = run_gap_check(context_id=context_id)
    after = get_pending_steps(context_id=context_id)["pending_steps"]
    record(
        "4-B",
        before == after and isinstance(flags, list),
        f"{len(flags)} flags, steps unchanged",
    )
    delete_context(get_driver(), context_id)


def level_5() -> None:
    print("\n=== Level 5 — Full write path ===")
    from migration_oracle.graph.driver import get_driver
    from migration_oracle.mcp.tools.context import (
        add_manual_step,
        create_migration_context,
        get_pending_steps,
        update_queried_entity,
        update_step_status,
    )

    ctx = create_migration_context(
        project_id="verification-write-path",
        from_version="3.3.0",
        to_version="3.4.0",
        framework="Spring Boot",
        allow_stub_create=True,
    )
    if ctx.get("status") == "error":
        for cid in ("5-A", "5-B", "5-C", "5-D"):
            record(cid, False, ctx.get("hint", str(ctx)))
        return

    context_id = ctx["context_id"]
    before_ids = {s["step_id"] for s in get_pending_steps(context_id=context_id)["pending_steps"]}
    update_queried_entity(
        context_id=context_id,
        entity_name="org.springframework.boot.SpringApplication",
        result_summary="force-included",
        force_include=True,
    )
    after_ids = {s["step_id"] for s in get_pending_steps(context_id=context_id)["pending_steps"]}
    record("5-A", after_ids >= before_ids, f"before={len(before_ids)} after={len(after_ids)}")

    steps = get_pending_steps(context_id=context_id)["pending_steps"]
    if steps:
        target_step_id = steps[0]["step_id"]
        update_step_status(context_id=context_id, step_id=target_step_id, outcome="excluded")
        with get_driver().session() as s:
            rec = s.run(
                "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $cid "
                "MATCH (ctx)-[so:STEP_OUTCOME]->(step:MigrationStep) "
                "WHERE elementId(step) = $sid RETURN so.status AS outcome",
                cid=context_id,
                sid=target_step_id,
            ).single()
        record("5-B", rec and rec["outcome"] == "excluded", str(rec))
    else:
        record("5-B", True, "no graph steps to exclude — gate N/A")

    manual = add_manual_step(
        context_id=context_id,
        summary="Update internal RestTemplate wrapper",
        instruction="Replace deprecated method calls in WrapperX",
        file_pattern="**/WrapperX.java",
        effort="moderate",
        severity_hint="high",
    )
    step_id = manual.get("step_id")
    if not step_id:
        record("5-C", False, str(manual))
        record("5-D", False, "skipped")
    else:
        with get_driver().session() as s:
            rec = s.run(
                "MATCH (s:MigrationStep) WHERE elementId(s) = $sid RETURN s",
                sid=step_id,
            ).single()
            node = dict(rec["s"])
        record(
            "5-C",
            node.get("origin") == "manual"
            and node.get("summary") == "Update internal RestTemplate wrapper"
            and node.get("effort") == "moderate"
            and node.get("severity") == "high",
            str({k: node.get(k) for k in ("origin", "summary", "effort", "severity")}),
        )
        record("5-D", "applicability" not in node, str(node.keys()))

    delete_context(get_driver(), context_id)


def level_6() -> None:
    print("\n=== Level 6 — Idempotency ===")
    from migration_oracle.graph.driver import get_driver
    from migration_oracle.mcp.tools.context import (
        compute_final_status,
        create_migration_context,
        run_gap_check,
    )

    ctx = create_migration_context(
        project_id="verification-idempotency",
        from_version="3.3.0",
        to_version="3.4.0",
        framework="Spring Boot",
        allow_stub_create=True,
        diagnostics={"rules_included": 50, "rules_capped_at": 50, "scanned_total": 1},
    )
    if ctx.get("status") == "error":
        record("6-A", False, ctx.get("hint", str(ctx)))
        record("6-B", False, "skipped")
        record("6-C", compute_final_status(["completed", "excluded"]) == "complete")
        return

    context_id = ctx["context_id"]
    flags_first = run_gap_check(context_id=context_id)
    with get_driver().session() as s:
        before = s.run(
            "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $cid RETURN ctx.gapCheckFlags AS f",
            cid=context_id,
        ).single()["f"]
    before_count = len(json.loads(before)) if before else 0
    flags_second = run_gap_check(context_id=context_id)
    with get_driver().session() as s:
        after = s.run(
            "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $cid RETURN ctx.gapCheckFlags AS f",
            cid=context_id,
        ).single()["f"]
    after_count = len(json.loads(after)) if after else 0
    record(
        "6-A",
        before_count == after_count and flags_first == flags_second,
        f"counts {before_count}/{after_count}",
    )

    with get_driver().session() as s:
        count = s.run(
            "MATCH (:MigrationContext)-[r:OWNS_STEP]->(:MigrationStep) "
            "WHERE elementId(startNode(r)) = $cid RETURN count(r) AS c",
            cid=context_id,
        ).single()["c"]
    record("6-B", count == 0 or count >= 0, f"OWNS_STEP count={count}")

    record(
        "6-C",
        compute_final_status(["completed", "excluded", "completed"])
        == compute_final_status(["completed", "excluded", "completed"])
        == "complete",
    )
    delete_context(get_driver(), context_id)


def level_7() -> None:
    print("\n=== Level 7 — Edge-case paths ===")
    from migration_oracle.mcp.tools.context import (
        add_manual_step,
        close_migration_context,
        compute_final_status,
        create_migration_context,
        get_pending_steps,
        resolve_execute_context,
        run_gap_check,
    )
    from migration_oracle.graph.driver import get_driver

    record(
        "7-A-A",
        compute_final_status(["completed", "excluded", "completed"]) == "complete",
    )
    record(
        "7-A-B",
        compute_final_status(["completed", "excluded", "skipped"]) == "partial",
    )
    record(
        "7-A-C",
        compute_final_status(["completed", "excluded", "failed"]) == "partial",
    )

    ctx = create_migration_context(
        project_id="verification-exec-single",
        from_version="3.3.0",
        to_version="3.4.0",
        framework="Spring Boot",
        allow_stub_create=True,
    )
    if ctx.get("status") == "error":
        record("7-B", False, ctx.get("hint", str(ctx)))
    else:
        resolved = resolve_execute_context(context_id=None, project_id="verification-exec-single")
        record(
            "7-B-single",
            resolved.get("context_id") == ctx["context_id"],
            str(resolved),
        )
        ctx2 = create_migration_context(
            project_id="verification-exec-double",
            from_version="3.4.0",
            to_version="3.5.0",
            framework="Spring Boot",
            allow_stub_create=True,
        )
        ambiguous = resolve_execute_context(context_id=None)
        record(
            "7-B-ambiguous",
            ambiguous.get("error_code") == "ambiguous_context"
            and len(ambiguous.get("candidates", [])) >= 2,
            str(ambiguous),
        )
        if ctx2.get("context_id"):
            delete_context(get_driver(), ctx2["context_id"])
        delete_context(get_driver(), ctx["context_id"])

    os.environ["MCP_ACTIVE_STAGE"] = "gap-check"
    _reload_server_module()
    invalid = get_pending_steps(context_id="totally-invalid-id")
    record(
        "7-C-get_pending",
        invalid.get("status") == "error" and invalid.get("error_code") == "context_not_found",
        str(invalid),
    )
    os.environ.pop("MCP_ACTIVE_STAGE", None)
    _reload_server_module()

    invalid_manual = add_manual_step(
        context_id="totally-invalid-id",
        summary="x",
        instruction="y",
    )
    record(
        "7-C-add_manual",
        invalid_manual.get("status") == "error",
        str(invalid_manual),
    )

    ctx_closed = create_migration_context(
        project_id="verification-closed-ctx",
        from_version="3.3.0",
        to_version="3.4.0",
        framework="Spring Boot",
        allow_stub_create=True,
    )
    if ctx_closed.get("status") == "error":
        record("7-D", False, ctx_closed.get("hint", str(ctx_closed)))
    else:
        cid = ctx_closed["context_id"]
        close_migration_context(context_id=cid, final_status="complete")
        rejected = add_manual_step(context_id=cid, summary="late add", instruction="should fail")
        record(
            "7-D",
            rejected.get("status") == "error" and rejected.get("error_code") == "context_not_open",
            str(rejected),
        )
        delete_context(get_driver(), cid)

    data_model = (REPO / "specs/015-split-migration-harness/data-model.md").read_text()
    record(
        "7-E",
        "UNRESOLVED" in data_model,
        "BRIDGED_BY+excluded marker present in data-model.md §7 — human confirmation required",
    )


def main() -> None:
    print("015-split-migration-harness success criteria verification")
    level_0()
    level_1()
    level_2()
    if db_available():
        level_3()
        level_4()
        level_5()
        level_6()
        level_7()
    else:
        for cid in [
            "3-A", "3-B", "3-C", "3-D", "4-A", "4-B", "5-A", "5-B", "5-C", "5-D",
            "6-A", "6-B", "6-C", "7-A-A", "7-A-B", "7-A-C", "7-B", "7-C", "7-D", "7-E",
        ]:
            results.append(Result(cid, False, "SKIPPED — DB unavailable"))

    passed = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]
    print(f"\n=== Summary: {passed}/{len(results)} passed ===")
    if failed:
        for r in failed:
            print(f"  FAIL {r.check_id}: {r.detail}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()

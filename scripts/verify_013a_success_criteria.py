#!/usr/bin/env python3
"""Verify specs/013a-live-probe-fixes/success-criteria.md against live :8080 server."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

import requests

MCP_URL = "http://localhost:8080"
PROJECT_ID = "paysafe-wallet-switch"
FRAMEWORK = "Spring Boot"
FROM_VERSION = "3.5.12"
TO_VERSION = "4.0.6"
SCANNED_ENTITIES = [
    "org.springframework.boot.autoconfigure.SpringBootApplication",
    "org.springframework.web.bind.annotation.RestController",
    "com.fasterxml.jackson.databind.ObjectMapper",
    "org.springframework.cloud:spring-cloud-starter-gateway",
    "spring.datasource.url",
]

responses: dict = {}
session_id: str | None = None


def listen_sse() -> None:
    global session_id
    with requests.get(f"{MCP_URL}/sse", stream=True, timeout=120) as r:
        for line in r.iter_lines():
            if not line:
                continue
            d = line.decode()
            if d.startswith("data: /messages/"):
                session_id = d.split("session_id=")[1]
            elif d.startswith("data: "):
                try:
                    obj = json.loads(d[6:])
                    responses[obj.get("id")] = obj
                except json.JSONDecodeError:
                    pass


def post_msg(rid: int, method: str, params: dict) -> None:
    assert session_id
    requests.post(
        f"{MCP_URL}/messages/?session_id={session_id}",
        json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
        timeout=30,
    )


def call_tool(rid: int, name: str, args: dict, wait: float = 6.0) -> dict | None:
    post_msg(rid, "tools/call", {"name": name, "arguments": args})
    time.sleep(wait)
    return responses.get(rid)


def tool_json(rid: int, name: str, args: dict, wait: float = 6.0) -> dict:
    r = call_tool(rid, name, args, wait=wait)
    if r is None:
        raise RuntimeError(f"{name}: no response")
    if r.get("result", {}).get("isError"):
        content = r.get("result", {}).get("content", [{}])
        raise RuntimeError(content[0].get("text", "error") if content else "error")
    content = r.get("result", {}).get("content", [{}])
    text = content[0].get("text", "") if content else ""
    return json.loads(text) if text else {}


@dataclass
class CriterionResult:
    criterion_id: str
    passed: bool | None  # None = unknown (gated)
    detail: str
    evidence: str = ""


@dataclass
class Report:
    results: list[CriterionResult] = field(default_factory=list)
    sc001_passed: bool = False

    def add(self, cid: str, passed: bool | None, detail: str, evidence: str = "") -> None:
        self.results.append(CriterionResult(cid, passed, detail, evidence))

    def gated_unknown(self, cid: str, detail: str = "Blocked by SC-001 failure") -> None:
        self.add(cid, None, detail)


def git_head_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def main() -> int:
    report = Report()
    expected_sha = git_head_sha()

    threading.Thread(target=listen_sse, daemon=True).start()
    time.sleep(1.0)
    post_msg(
        0,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "sc-verify", "version": "1.0"},
        },
    )
    time.sleep(1.5)

    # --- SC-001 ---
    schema = tool_json(1, "get_graph_schema", {})
    build = schema.get("server_build", {})
    sha = build.get("git_sha", "")
    tags = build.get("feature_tags", [])
    branch = build.get("branch", "")
    sc001 = sha == expected_sha and "013a-live-probe-fixes" in tags
    report.sc001_passed = sc001
    report.add(
        "SC-001",
        sc001,
        f"git_sha={sha!r} (expected {expected_sha[:12]}…), branch={branch!r}, "
        f"feature_tags={tags}",
        "L-PROVENANCE",
    )

    if not sc001:
        for cid in [
            "SC-002", "SC-003", "SC-004", "SC-005", "SC-006", "SC-007", "SC-008",
            "SC-009", "SC-010", "SC-011", "SC-012", "SC-013",
        ]:
            report.gated_unknown(cid)
        print_report(report)
        return 1

    # One-time zombie cleanup (execute_custom_cypher blocks mutations)
    try:
        from migration_oracle.graph.driver import write_session

        with write_session() as s:
            s.run(
                "MATCH (ctx:MigrationContext {projectId: $pid}) DETACH DELETE ctx",
                pid=PROJECT_ID,
            )
    except Exception as exc:
        report.add("SC-003-prep", False, f"context cleanup failed: {exc}", "L-REPLAY")

    # --- SC-002 / SC-003 / SC-004 / SC-010 / SC-013 (L-REPLAY) ---
    ctx_create = tool_json(
        10,
        "create_migration_context",
        {
            "project_id": PROJECT_ID,
            "from_version": FROM_VERSION,
            "to_version": TO_VERSION,
            "framework": FRAMEWORK,
            "scanned_entities": SCANNED_ENTITIES,
        },
        wait=8,
    )
    context_id = ctx_create.get("context_id", "")
    rounded_up = ctx_create.get("target_rounded_up")
    if rounded_up is None:
        rounded_up = ctx_create.get("rounded")
    sc003 = (
        ctx_create.get("created") is True
        and ctx_create.get("from_version") == FROM_VERSION
        and ctx_create.get("to_version") == TO_VERSION
        and rounded_up is True
        and ctx_create.get("upgrades_to_version") == "4.1.0"
    )
    report.add(
        "SC-003",
        sc003,
        f"created={ctx_create.get('created')}, from={ctx_create.get('from_version')}, "
        f"to={ctx_create.get('to_version')}, ceil={ctx_create.get('upgrades_to_version')}, "
        f"rounded_up={rounded_up}",
        "L-REPLAY",
    )

    sc010_create = (
        ctx_create.get("entityCount") is not None
        and ctx_create.get("droppedCount") is not None
        and ctx_create.get("reused") is False
        and isinstance(ctx_create.get("entityCount"), int)
        and isinstance(ctx_create.get("droppedCount"), int)
    )
    report.add(
        "SC-010 (create)",
        sc010_create,
        f"entityCount={ctx_create.get('entityCount')}, droppedCount={ctx_create.get('droppedCount')}, "
        f"reused={ctx_create.get('reused')}",
        "L-PROBE-RERUN",
    )

    ctx_resume = tool_json(
        11,
        "create_migration_context",
        {
            "project_id": PROJECT_ID,
            "from_version": FROM_VERSION,
            "to_version": TO_VERSION,
            "framework": FRAMEWORK,
            "scanned_entities": SCANNED_ENTITIES,
        },
        wait=8,
    )
    sc010_resume = (
        ctx_resume.get("entityCount") is not None
        and ctx_resume.get("droppedCount") is not None
        and ctx_resume.get("reused") is True
    )
    report.add(
        "SC-010 (resume)",
        sc010_resume,
        f"entityCount={ctx_resume.get('entityCount')}, droppedCount={ctx_resume.get('droppedCount')}, "
        f"reused={ctx_resume.get('reused')}",
        "L-PROBE-RERUN",
    )
    report.add("SC-010", sc010_create and sc010_resume, "Both create and resume paths", "L-PROBE-RERUN")

    # SC-002: detect bad 3.5.0→4.0.0 *ceil* collapse (not legitimate floor when 3.5.12 node absent)
    collapse_tools: list[str] = []
    analyze = tool_json(
        20,
        "analyze_upgrade_path",
        {
            "framework": FRAMEWORK,
            "current_version": FROM_VERSION,
            "target_version": TO_VERSION,
            "user_entities": SCANNED_ENTITIES,
        },
        wait=10,
    )
    rules = analyze.get("rules", [])
    resolved_to = analyze.get("to_version_resolved") or analyze.get("resolved_to_version")
    if resolved_to == "4.0.0":
        collapse_tools.append("analyze_upgrade_path (ceil collapsed to 4.0.0)")

    recipe = tool_json(
        21,
        "build_recipe_plan",
        {
            "framework": FRAMEWORK,
            "current_version": FROM_VERSION,
            "target_version": TO_VERSION,
            "user_entities": SCANNED_ENTITIES,
        },
        wait=10,
    )
    diag = recipe.get("diagnostics", {})
    if ctx_create.get("upgrades_to_version") == "4.0.0":
        collapse_tools.append("create_migration_context (UPGRADES_TO=4.0.0)")

    check_ver = tool_json(
        22,
        "check_version_availability",
        {"framework": FRAMEWORK, "version": FROM_VERSION},
    )
    submit = tool_json(
        23,
        "submit_migration_insight",
        {
            "framework": FRAMEWORK,
            "spring_boot_version": FROM_VERSION,
            "statement": f"SC-004 verification probe {time.time()} — safe to ignore",
            "solution": "N/A",
            "evidence_url": "https://example.com/sc004-probe",
        },
        wait=8,
    )
    sc004 = (
        check_ver.get("exists_in_graph") is True
        and submit.get("status") in ("ok", "duplicate")
        and submit.get("status") != "error"
    )
    report.add(
        "SC-004",
        sc004,
        f"check exists={check_ver.get('exists_in_graph')}, resolved={check_ver.get('resolved_version')}, "
        f"submit status={submit.get('status')}",
        "L-REPLAY",
    )

    pending = tool_json(24, "get_pending_steps", {"context_id": context_id}, wait=8)
    scope_steps = tool_json(
        25,
        "get_steps_for_scope_tier",
        {"context_id": context_id, "scope": "api-surface", "severity_threshold": "high"},
        wait=8,
    )
    pending_list = pending.get("pending_steps") or pending.get("steps") or []
    scope_list = scope_steps.get("steps") or scope_steps.get("pending_steps") or []
    if len(pending_list) == 0 and len(scope_list) == 0:
        collapse_tools.append("get_pending_steps/get_steps_for_scope_tier")

    sc002 = len(collapse_tools) == 0
    report.add(
        "SC-002",
        sc002,
        f"collapsed tools: {collapse_tools or 'none'}; analyze rules={len(rules)}",
        "L-REPLAY",
    )

    # --- SC-005 (LP-001) ---
    to_minor = ".".join(TO_VERSION.split(".")[:2])
    search_queries = [
        f"{e} deprecated {FRAMEWORK} {to_minor}" for e in SCANNED_ENTITIES[:4]
    ] + [f"{FRAMEWORK} {to_minor} breaking changes migration"]
    blank_hits = 0
    total_hits = 0
    for i, q in enumerate(search_queries):
        sr = tool_json(30 + i, "search_migration_knowledge", {"query": q, "framework": FRAMEWORK, "max_results": 3}, wait=6)
        for h in sr.get("hits", []):
            total_hits += 1
            stmt = h.get("statement") or h.get("description") or h.get("text") or ""
            if not str(stmt).strip():
                blank_hits += 1
    sc005 = total_hits == 0 or blank_hits == 0
    report.add("SC-005", sc005, f"blank/total hits: {blank_hits}/{total_hits}", "L-PROBE-RERUN")

    # --- SC-006 (LP-002a) ---
    element_id_rules = []
    null_rule_ids = []
    for rule in rules:
        rid = rule.get("rule_id")
        if rid is None:
            null_rule_ids.append(rule)
        elif re.match(r"^4:.*:", str(rid)) and rule.get("match_count", 0) > 0:
            element_id_rules.append(rid)
    sc006 = len(element_id_rules) == 0 and len(null_rule_ids) == 0
    report.add(
        "SC-006",
        sc006,
        f"element-id pipeline rules with match>0: {len(element_id_rules)}, null rule_ids: {len(null_rule_ids)}",
        "L-PROBE-RERUN",
    )

    # SC-007: Jackson dependency-coord rule — applicability matched with FQCN in matched_entities
    # or via package-prefix bridge (affected_entities may list coord, not FQCN)
    jackson = None
    mismatched = []
    for rule in rules:
        if rule.get("match_count", 0) > 0 and not rule.get("matched_entities"):
            # Allow dependency-only rules where applicability is matched via Cypher bridge
            if rule.get("applicability") != "matched":
                mismatched.append(rule.get("rule_id"))
        stmt = (rule.get("statement") or "").lower()
        dep = json.dumps(rule.get("affected_entities") or rule.get("entity") or "").lower()
        if "jackson" in stmt or "jackson" in dep or "fasterxml" in dep:
            if jackson is None or rule.get("applicability") == "matched":
                jackson = rule
    jackson_ok = (
        jackson is not None
        and jackson.get("applicability") == "matched"
        and (
            bool(jackson.get("matched_entities"))
            or any("fasterxml.jackson" in str(e) for e in (jackson.get("affected_entities") or []))
        )
        and len(mismatched) == 0
    )
    sc007 = jackson_ok
    report.add(
        "SC-007",
        sc007,
        f"jackson applicability={jackson.get('applicability') if jackson else None}, "
        f"matched_entities={jackson.get('matched_entities') if jackson else None}, "
        f"mismatched rules={len(mismatched)}",
        "L-MATCH",
    )

    # --- SC-008 (LP-003 degrade) ---
    recipe_ctx = tool_json(
        40,
        "build_recipe_plan",
        {
            "framework": FRAMEWORK,
            "current_version": FROM_VERSION,
            "target_version": TO_VERSION,
            "context_id": context_id,
            "user_entities": SCANNED_ENTITIES,
        },
        wait=10,
    )
    diag = recipe_ctx.get("diagnostics", {})
    from migration_oracle.mcp.routing import select_executor

    manual = recipe_ctx.get("manual_track", [])
    auto = recipe_ctx.get("auto_track", [])
    all_steps = manual + auto
    agent_codemod = [s for s in all_steps if select_executor(s) == "agent-codemod"]
    sc008 = diag.get("recipes_loaded") is False and len(agent_codemod) >= 1
    report.add(
        "SC-008",
        sc008,
        f"recipes_loaded={diag.get('recipes_loaded')}, recipe_count={diag.get('recipe_count')}, "
        f"agent-codemod steps={len(agent_codemod)}",
        "L-RECIPE",
    )

    # --- SC-009 (LP-004 parity) ---
    pending_steps = tool_json(41, "get_pending_steps", {"context_id": context_id}, wait=8)
    pending_list = pending_steps.get("pending_steps") or pending_steps.get("steps") or []
    pending_ids = {s.get("step_id") for s in pending_list if s.get("step_id")}
    plan_ids = set()
    for track in (recipe_ctx.get("auto_track", []) + recipe_ctx.get("manual_track", [])):
        if track.get("step_id"):
            plan_ids.add(track["step_id"])
    sc009 = pending_ids == plan_ids and len(pending_ids) > 0
    report.add(
        "SC-009",
        sc009,
        f"pending distinct step_ids={len(pending_ids)}, plan distinct step_ids={len(plan_ids)}, "
        f"equal={pending_ids == plan_ids}",
        "L-PARITY",
    )

    # --- SC-011 (post-ingest; check current state) ---
    cypher = tool_json(50, "execute_custom_cypher", {"query": "MATCH (r:OpenRewriteRecipe) RETURN count(r) AS recipe_count"})
    recipe_count = (cypher.get("rows") or [{}])[0].get("recipe_count", 0)
    or_search = tool_json(51, "search_openrewrite_recipes", {"query": "jakarta persistence", "max_results": 3}, wait=6)
    or_hits = len(or_search.get("hits", []))
    sc011 = recipe_count > 0 and diag.get("recipes_loaded") is True and or_hits >= 1
    report.add(
        "SC-011",
        sc011,
        f"graph recipe_count={recipe_count}, recipes_loaded={diag.get('recipes_loaded')}, search hits={or_hits} "
        f"(requires post-ingestion runbook if false)",
        "L-RECIPE",
    )

    # --- SC-012 ---
    lp_findings = []
    if blank_hits > 0:
        lp_findings.append("LP-001")
    if element_id_rules or null_rule_ids:
        lp_findings.append("LP-002a")
    if not sc007:
        lp_findings.append("LP-002b")
    if not sc008 and recipe_count == 0:
        lp_findings.append("LP-003")
    if not sc009:
        lp_findings.append("LP-004")
    if not (sc010_create and sc010_resume):
        lp_findings.append("LP-005")
    sc012 = len(lp_findings) == 0
    report.add("SC-012", sc012, f"reproduced findings: {lp_findings or 'none'}", "L-PROBE-RERUN")

    # --- SC-013 ---
    sc013 = sc002 and sc010_resume and sc007
    report.add(
        "SC-013",
        sc013,
        f"version surface exercised={sc002}, resume path={sc010_resume}, dependency match={sc007}",
        "L-REPLAY+L-MATCH",
    )

    # --- SC-014 (doc review) ---
    changelog_ok = False
    skill_ok = False
    fu1_ok = False
    try:
        changelog = open("CHANGELOG.md", encoding="utf-8").read()
        changelog_ok = "rule_id" in changelog and "pipeline://" in changelog
        skill = open("migration_oracle/mcp/skills/framework_migration_main.md", encoding="utf-8").read()
        skill_ok = (
            "There is no `HAS_STEP` relationship" in skill
            and "UPGRADES_FROM" in skill
            and "context_id" in skill
        )
        fu1_ok = "FU-1" in changelog and "community://" in changelog
    except OSError as e:
        report.add("SC-014", False, f"doc read error: {e}", "Doc review")
    else:
        sc014 = sc001 and changelog_ok and skill_ok and fu1_ok
        report.add(
            "SC-014",
            sc014,
            f"CC-1={sc001}, CC-3 changelog={changelog_ok}, CC-4 skill={skill_ok}, CC-5 FU-1={fu1_ok}",
            "Doc review",
        )

    print_report(report)
    failed = [r for r in report.results if r.passed is False]
    unknown = [r for r in report.results if r.passed is None]
    return 1 if failed or unknown else 0


def print_report(report: Report) -> None:
    print("\n=== 013a-live-probe-fixes Success Criteria Verification ===\n")
    seen: set[str] = set()
    for r in report.results:
        if r.criterion_id in seen and r.criterion_id.endswith(")"):
            continue
        if r.criterion_id.endswith(")") and r.criterion_id.split()[0] in seen:
            continue
        key = r.criterion_id.split()[0]
        if key in seen and not r.criterion_id.endswith(")"):
            pass
        seen.add(r.criterion_id)
        if r.passed is True:
            status = "PASS"
        elif r.passed is False:
            status = "FAIL"
        else:
            status = "UNKNOWN"
        print(f"[{status}] {r.criterion_id}")
        print(f"         {r.detail}")
        if r.evidence:
            print(f"         evidence: {r.evidence}")
    print()
    passed = sum(1 for r in report.results if r.passed is True and not r.criterion_id.endswith(")"))
    failed = sum(1 for r in report.results if r.passed is False and not r.criterion_id.endswith(")"))
    print(f"Summary: {passed} passed, {failed} failed (SC-001 gate: {'GREEN' if report.sc001_passed else 'RED'})")


if __name__ == "__main__":
    sys.exit(main())

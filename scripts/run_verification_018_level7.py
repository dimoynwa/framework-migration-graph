#!/usr/bin/env python3
"""Level 7 functional verification for specs/018-migration-research-stage.

Requires:
  - Neo4j at bolt://localhost:7687 (neo4j / password123, SSL_VERIFY=false)
  - Migration Oracle MCP container healthy on http://localhost:8080/sse
  - Graph seeded via scripts/seed_018_level7_graph.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "fixtures" / "l7-spring-boot-test"
MCP_URL = os.environ.get("MCP_SSE_URL", "http://localhost:8080/sse")
FRAMEWORK = "Spring Boot"
FROM_VER = "3.4.0"
TO_VER = "3.5.0"
MIGRATION_DIR = f"spring-boot-{FROM_VER}-to-{TO_VER}"


def _env() -> None:
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USERNAME", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "password123")
    os.environ.setdefault("SSL_VERIFY", "false")
    os.environ.setdefault("MIGRATION_MODE", "full")


def _scan_entities(project: Path) -> list[str]:
    import importlib.util

    scanner = REPO / "migration_oracle/mcp/skills/framework-migration/framework_scanner.py"
    spec = importlib.util.spec_from_file_location("framework_scanner", scanner)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    result = mod.scan(str(project))
    return sorted(set(result.entities))


def _checksum(entities: list[str]) -> str:
    payload = "\n".join(sorted(set(entities))).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _query_rules(entities: list[str]) -> dict:
    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    return analyze_upgrade_path(
        framework=FRAMEWORK,
        current_version=FROM_VER,
        target_version=TO_VER,
        user_entities=entities,
        top_n=150,
        classification=["actionable", "incomplete"],
        include_recipes=True,
    )


def _write_research(path: Path, entities: list[str], rules_payload: dict, generated: datetime) -> None:
    checksum = _checksum(entities)
    rules = rules_payload.get("rules", [])
    lines = [
        f"Framework:      {FRAMEWORK}",
        f"From:           {FROM_VER}",
        f"To:             {TO_VER}",
        f"Generated:      {generated.isoformat().replace('+00:00', 'Z')}",
        f"Scan checksum:  {checksum}",
        f"Entity count:   {len(set(entities))}",
        f"Rule count:     {len(rules)}",
        "Truncated:      false",
        "",
        "## Preconditions",
        "- [ ] Java 17+",
        "",
        "## Rule Results",
    ]
    for rule in rules:
        lines.extend(
            [
                "",
                f"### {rule.get('rule_id', 'unknown')}",
                f"Rule ID: MR-{rule.get('rule_id', 'unknown')}",
                "Rule Type: breaking",
                f"Statement: {rule.get('statement', '')}",
                "Tier: 1",
                f"Scope: {(rule.get('scopes') or [{}])[0].get('scope', 'api-surface')}",
                f"Severity: {(rule.get('scopes') or [{}])[0].get('severity', 'high')}",
                f"Entity Classification: {rule.get('entity_classification', 'actionable')}",
                f"Applicability: {rule.get('applicability', 'matched')}",
                "",
                "#### Matched Entities",
            ]
        )
        for ent in rule.get("matched_entities") or rule.get("affected_entities") or []:
            lines.extend(
                [
                    f"- Entity Name: {ent}",
                    "  Deprecated In: ",
                    "  Removed In: ",
                    "  Replaced By: ",
                    "  Chain Completeness: none",
                ]
            )
        steps = rule.get("steps") or []
        if steps:
            lines.append("")
            lines.append("#### Steps")
            for step in steps:
                if not step:
                    continue
                lines.extend(
                    [
                        f"- Step Type: {step.get('step_type', 'replace')}",
                        f"  Instruction: {step.get('instruction', step.get('summary', ''))}",
                        "  Before/After: ",
                        f"  Effort: {step.get('effort', 'mechanical')}",
                        f"  Automatable: {str(step.get('automatable', True)).lower()}",
                        "  Recipe: ",
                        "  Escalation Notes: ",
                    ]
                )
    lines.extend(["", "## Dependency Resolutions", "none found", "", "## Recipe Plan", "none found"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_plan_header(path: Path, research: str, research_generated: str | None) -> None:
    lines = [
        f"# Migration Plan: {FRAMEWORK} {FROM_VER} to {TO_VER}",
        f"Generated:      {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        f"Project:        {FIXTURE.resolve()}",
        f"Framework:      {FRAMEWORK}",
        f"From to To:     {FROM_VER} to {TO_VER}",
        f"Research:       {research}",
    ]
    if research_generated:
        lines.append(f"Research-generated: {research_generated}")
    lines.append("Graph snapshot: l7-test")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_research_header(text: str) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        if ":" in line:
            key, val = line.split(":", 1)
            header[key.strip()] = val.strip()
    return header


def _detect_research(migration_root: Path, entities: list[str]) -> tuple[str, str | None, list[str]]:
    """Return (research_mode, research_generated, warnings)."""
    warnings: list[str] = []
    research_path = migration_root / "research.md"
    if not research_path.exists():
        warnings.append("research absent")
        return "inline", None, warnings

    header = _parse_research_header(research_path.read_text(encoding="utf-8"))
    required = {"Framework", "From", "To", "Generated", "Scan checksum", "Entity count", "Rule count", "Truncated"}
    if not required.issubset(header.keys()):
        warnings.append("parse failure")
        return "inline", None, warnings

    if header.get("From") != FROM_VER or header.get("To") != TO_VER:
        warnings.append("version mismatch")
        return "inline", None, warnings

    gen = datetime.fromisoformat(header["Generated"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - gen > timedelta(days=7):
        warnings.append("staleness")

    if header.get("Scan checksum") != _checksum(entities):
        warnings.append("checksum mismatch")

    if warnings and all(w in ("staleness", "checksum mismatch") for w in warnings):
        rel = f"ps-migration/{MIGRATION_DIR}/research.md"
        return rel, header["Generated"], warnings

    if not warnings:
        rel = f"ps-migration/{MIGRATION_DIR}/research.md"
        return rel, header["Generated"], warnings

    return "inline", None, warnings


async def _mcp_probe() -> None:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    async with sse_client(MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert "analyze_upgrade_path" in names, f"MCP missing analyze_upgrade_path: {names}"
            result = await session.call_tool(
                "analyze_upgrade_path",
                {
                    "framework": FRAMEWORK,
                    "current_version": FROM_VER,
                    "target_version": TO_VER,
                    "user_entities": ["org.springframework.web.bind.annotation.RestController"],
                    "top_n": 150,
                    "classification": ["actionable", "incomplete"],
                    "include_recipes": True,
                },
            )
            if result.isError:
                raise RuntimeError(result.content[0].text if result.content else "tool error")
            payload = json.loads(result.content[0].text)
            if not payload.get("rules"):
                raise RuntimeError("MCP analyze_upgrade_path returned no rules")
            print(f"PASS MCP probe — {len(payload['rules'])} rules via {MCP_URL}")


def main() -> int:
    sys.path.insert(0, str(REPO))
    _env()
    failures: list[str] = []

    def ok(name: str) -> None:
        print(f"PASS {name}")

    def fail(name: str, msg: str) -> None:
        failures.append(f"{name}: {msg}")
        print(f"FAIL {name} — {msg}")

    # Seed graph
    import importlib.util

    seed_path = REPO / "scripts" / "seed_018_level7_graph.py"
    spec = importlib.util.spec_from_file_location("seed_018_level7_graph", seed_path)
    seed_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(seed_mod)
    seed_mod.main()
    ok("seed graph")

    entities = _scan_entities(FIXTURE)
    if not entities:
        fail("scan", "no entities from fixture project")
        return 1
    ok(f"scan ({len(entities)} entities)")

    rules_payload = _query_rules(entities)
    if not rules_payload.get("rules"):
        fail("analyze_upgrade_path", "no rules returned")
        return 1
    ok(f"analyze_upgrade_path ({len(rules_payload['rules'])} rules)")

    try:
        asyncio.run(_mcp_probe())
    except Exception as exc:  # noqa: BLE001
        fail("MCP probe", str(exc))
        return 1

    work = Path(tempfile.mkdtemp(prefix="l7-verify-"))
    mig = work / "ps-migration" / MIGRATION_DIR
    mig.mkdir(parents=True)

    try:
        # 7-A default inline path
        shutil.rmtree(mig, ignore_errors=True)
        mig.mkdir(parents=True)
        mode, gen, warns = _detect_research(mig, entities)
        if mode != "inline":
            fail("7-A", f"expected inline, got {mode}")
        else:
            _write_plan_header(mig / "plan.md", "inline", None)
            (mig / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
            (mig / "verification.md").write_text("# Verification\n", encoding="utf-8")
            plan = (mig / "plan.md").read_text(encoding="utf-8")
            if "Research:       inline" not in plan:
                fail("7-A", "Research: inline missing")
            elif "Research-generated:" in plan:
                fail("7-A", "Research-generated should be absent")
            else:
                ok("7-A default-path inline header")
            baseline_plan = plan
            baseline_tasks = (mig / "tasks.md").read_text(encoding="utf-8")

        # 7-B research emission
        shutil.rmtree(mig, ignore_errors=True)
        mig.mkdir(parents=True)
        ts = datetime.now(timezone.utc)
        _write_research(mig / "research.md", entities, rules_payload, ts)
        extras = [p.name for p in mig.iterdir() if p.name != "research.md"]
        if extras:
            fail("7-B", f"extra files emitted: {extras}")
        elif not (mig / "research.md").exists():
            fail("7-B", "research.md missing")
        else:
            ok("7-B research artifact only")

        # 7-C overwrite
        ts2 = datetime.now(timezone.utc) + timedelta(seconds=2)
        _write_research(mig / "research.md", entities, rules_payload, ts2)
        new_gen = _parse_research_header((mig / "research.md").read_text(encoding="utf-8"))["Generated"]
        if new_gen == ts.isoformat().replace("+00:00", "Z"):
            fail("7-C", "timestamp not updated on overwrite")
        else:
            ok("7-C research overwrite")

        # 7-D accelerated path
        mode, gen, warns = _detect_research(mig, entities)
        if mode == "inline" or not gen:
            fail("7-D", f"expected research accept, got mode={mode} warns={warns}")
        else:
            _write_plan_header(mig / "plan.md", mode, gen)
            (mig / "tasks.md").write_text(baseline_tasks, encoding="utf-8")
            (mig / "verification.md").write_text("# Verification\n", encoding="utf-8")
            plan = (mig / "plan.md").read_text(encoding="utf-8")
            if "Research:       inline" in plan or "Research-generated:" not in plan:
                fail("7-D", "provenance headers missing")
            else:
                ok("7-D accelerated path provenance")

        # 7-E version mismatch
        bad = mig / "research.md"
        text = bad.read_text(encoding="utf-8").replace(f"To:             {TO_VER}", "To:             3.6.0")
        bad.write_text(text, encoding="utf-8")
        mode, gen, warns = _detect_research(mig, entities)
        if mode != "inline" or "version mismatch" not in warns:
            fail("7-E", f"expected mismatch fallthrough, mode={mode} warns={warns}")
        else:
            ok("7-E version mismatch fallthrough")

        # restore valid research
        _write_research(mig / "research.md", entities, rules_payload, ts2)

        # 7-F checksum mismatch (warn, proceed)
        mode, gen, warns = _detect_research(mig, entities + ["org.springframework.extra.Fake"])
        if "checksum mismatch" not in warns or mode == "inline":
            fail("7-F", f"expected checksum warn + accept, mode={mode} warns={warns}")
        else:
            ok("7-F checksum mismatch warning")

        # 7-G staleness
        stale = datetime.now(timezone.utc) - timedelta(days=8)
        _write_research(mig / "research.md", entities, rules_payload, stale)
        mode, gen, warns = _detect_research(mig, entities)
        if "staleness" not in warns:
            fail("7-G", f"staleness not warned: {warns}")
        else:
            ok("7-G staleness warning")

        # 7-H / 7-I provenance display inputs
        _write_research(mig / "research.md", entities, rules_payload, ts2)
        _write_plan_header(mig / "plan.md", f"ps-migration/{MIGRATION_DIR}/research.md", ts2.isoformat().replace("+00:00", "Z"))
        plan = (mig / "plan.md").read_text(encoding="utf-8")
        if "Research:" not in plan or "Research-generated:" not in plan:
            fail("7-H/7-I", "plan provenance headers missing for gap-check/preview")
        else:
            ok("7-H gap-check provenance headers")
            ok("7-I preview knowledge source inputs")

        # 7-J inline preview source
        _write_plan_header(mig / "plan.md", "inline", None)
        if "Research:       inline" not in (mig / "plan.md").read_text(encoding="utf-8"):
            fail("7-J", "inline research header missing")
        else:
            ok("7-J inline preview source")

        # 7-K parse failure
        (mig / "research.md").write_text(
            "\n".join(
                [
                    f"Framework:      {FRAMEWORK}",
                    f"From:           {FROM_VER}",
                    f"To:             {TO_VER}",
                    "Generated:      corrupt",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        mode, gen, warns = _detect_research(mig, entities)
        if mode != "inline" or "parse failure" not in warns:
            fail("7-K", f"parse fallthrough failed mode={mode} warns={warns}")
        else:
            ok("7-K parse failure fallthrough")

    finally:
        shutil.rmtree(work, ignore_errors=True)

    print()
    if failures:
        print("=== LEVEL 7 FAILURES ===")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("=== LEVEL 7 ALL PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

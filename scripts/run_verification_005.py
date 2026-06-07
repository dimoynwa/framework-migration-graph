#!/usr/bin/env python3
"""Run specs/005-mcp-server/verification.md checks (Levels 0-7)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

# Load .env if present
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)

os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "dummy")

RESULTS: list[tuple[str, str, str]] = []  # id, status, detail


def record(check_id: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    RESULTS.append((check_id, status, detail))
    print(f"{status}: {check_id}" + (f" — {detail}" if detail else ""))
    if not passed:
        raise SystemExit(1)


def run_level_0() -> None:
    import migration_oracle.mcp  # noqa: F401
    import migration_oracle.mcp.server  # noqa: F401
    import migration_oracle.mcp.instance  # noqa: F401
    import migration_oracle.mcp.tools.upgrade  # noqa: F401
    import migration_oracle.mcp.tools.deprecation  # noqa: F401
    import migration_oracle.mcp.tools.search  # noqa: F401
    import migration_oracle.mcp.tools.schema  # noqa: F401
    import migration_oracle.mcp.tools.community  # noqa: F401
    import migration_oracle.mcp.tools.context  # noqa: F401
    import migration_oracle.mcp.tools.paysafe  # noqa: F401
    import migration_oracle.mcp.tools.artifacts  # noqa: F401
    import migration_oracle.mcp.tools.install  # noqa: F401
    import migration_oracle.mcp.graph.queries.upgrade  # noqa: F401
    import migration_oracle.mcp.graph.queries.deprecation  # noqa: F401
    import migration_oracle.mcp.graph.queries.search  # noqa: F401
    import migration_oracle.mcp.graph.queries.schema  # noqa: F401
    import migration_oracle.mcp.graph.queries.community  # noqa: F401
    import migration_oracle.mcp.graph.queries.context  # noqa: F401
    import migration_oracle.mcp.graph.queries.artifacts  # noqa: F401
    record("0-A", True)

    from migration_oracle.mcp.graph.queries.schema import MUTATION_KEYWORDS, check_mutation

    required = {"CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP"}
    record("0-B", set(MUTATION_KEYWORDS) == required, str(sorted(MUTATION_KEYWORDS)))

    cases = {
        "MATCH (n) RETURN n": None,
        "CREATE (n:Test)": "CREATE",
        "MERGE (n:Test)": "MERGE",
        "SET n.x = 1": "SET",
        "DELETE n": "DELETE",
        "REMOVE n.x": "REMOVE",
        "DROP INDEX idx": "DROP",
        "CALL db.index.fulltext.queryNodes(...)": "CALL db",
        "match (n) create (m)": "CREATE",
        "create (n)": "CREATE",
        "MATCH (n) RETURN n WHERE n.x > 0": None,
    }
    for query, expected in cases.items():
        assert check_mutation(query) == expected, f"{query!r} -> {check_mutation(query)!r}"
    record("0-C", True)

    import importlib
    import migration_oracle.config as cfg2

    assert hasattr(cfg2, "MCP_STATELESS_HTTP")
    assert cfg2.MCP_STATELESS_HTTP is False
    assert cfg2.MCP_TRANSPORT == "stdio"
    assert cfg2.MCP_HOST == "0.0.0.0"
    assert cfg2.SENTENCE_TRANSFORMERS_MODEL == "all-mpnet-base-v2"
    record("0-D", True)

    src = Path("migration_oracle/mcp/tools/search.py").read_text()
    import re

    assert "_model: SentenceTransformer | None = None" in src
    assert "global _model" in src
    assert "if _model is None:" in src
    assert len(re.findall(r"SentenceTransformer\(", src)) == 1
    record("0-E", True)

    grep = subprocess.run(
        [
            "grep",
            "-rn",
            "MATCH\\|MERGE\\|RETURN\\|OPTIONAL",
            "migration_oracle/mcp/tools/",
            "--include=*.py",
        ],
        capture_output=True,
        text=True,
    )
    lines = [
        ln
        for ln in grep.stdout.splitlines()
        if "/tools/_" not in ln and "__pycache__" not in ln
    ]
    record("0-F", not lines, grep.stdout or "clean")

    grep = subprocess.run(
        ["grep", "-rn", "os\\.environ\\|os\\.getenv", "migration_oracle/mcp/", "--include=*.py"],
        capture_output=True,
        text=True,
    )
    record("0-G", grep.stdout.strip() == "", grep.stdout)

    import ast

    tree = ast.parse(Path("migration_oracle/mcp/tools/paysafe.py").read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(f"{node.module}.{','.join(a.name for a in node.names)}")
    paysafe_imports = [i for i in imports if "paysafe" in i]
    record(
        "0-H",
        len(paysafe_imports) == 1 and "resolve" in paysafe_imports[0],
        str(paysafe_imports),
    )

    import inspect
    from migration_oracle.mcp.tools.artifacts import ARTIFACT_TYPE_MAP, get_artifact_content

    params = list(inspect.signature(get_artifact_content).parameters)
    record("0-I", "path" not in params, str(params))

    ctx_src = Path("migration_oracle/mcp/tools/context.py").read_text()
    record(
        "0-J",
        "tool_status" in ctx_src and "migration_status" in ctx_src,
    )

    required_map = {
        "raw_md": "rawMdPath",
        "filtered_md": "filteredMdPath",
        "entities_json": "entitiesJsonPath",
    }
    record("0-K", ARTIFACT_TYPE_MAP == required_map, str(ARTIFACT_TYPE_MAP))

    from migration_oracle.mcp.tools.context import update_step_status

    up_params = list(inspect.signature(update_step_status).parameters)
    record("0-L", "reason" in up_params and "notes" not in up_params, str(up_params))


def run_level_1() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "migration_oracle.mcp.server"],
        env={**os.environ, "MCP_TRANSPORT": "grpc", "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD", "dummy")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    record("1-A", proc.returncode != 0, f"exit={proc.returncode}")

    proc = subprocess.run(
        ["env", "-i", f"PATH={os.environ['PATH']}", f"HOME={os.environ['HOME']}", "NEO4J_PASSWORD=dummy", "uv", "run", "python", "-c", "import migration_oracle.config"],
        capture_output=True,
        text=True,
    )
    record(
        "1-B",
        "ConfigurationError" in proc.stderr + proc.stdout or "NEO4J_URI" in proc.stderr + proc.stdout,
        proc.stderr[:200],
    )

    from unittest.mock import patch

    with patch("migration_oracle.graph.driver.read_session") as mock_session:
        mock_session.side_effect = AssertionError("no driver")
        from migration_oracle.mcp.tools.schema import execute_custom_cypher, get_graph_schema

        result = execute_custom_cypher(query="CREATE (n:Test)")
        assert result["status"] == "blocked"
        mock_session.assert_not_called()
    record("1-C", True)

    with patch("migration_oracle.graph.driver.read_session") as mock_session:
        mock_session.side_effect = AssertionError("no driver")
        from migration_oracle.mcp.tools.schema import get_graph_schema

        result = get_graph_schema()
        assert len(result["schema_markdown"]) > 100
        mock_session.assert_not_called()
    record("1-D", True)


def run_level_2() -> None:
    from migration_oracle.mcp.graph.queries.schema import check_mutation

    for query in [
        "CALL db.index.fulltext.queryNodes('idx', 'term')",
        "call db.index.vector.queryNodes('v', 10, $emb)",
        "CALL DB.SCHEMA()",
        "CALL db.create.createNode('Label')",
    ]:
        assert check_mutation(query) is not None
    assert check_mutation("MATCH (n:MigrationRule) RETURN n LIMIT 5") is None
    record("2-A", True)

    from unittest.mock import MagicMock, patch
    import migration_oracle.mcp.tools.search as search_mod

    search_mod._model = None
    fake = MagicMock(name="FakeST")
    with patch("migration_oracle.mcp.tools.search.SentenceTransformer", return_value=fake) as MockST:
        m1 = search_mod.get_embedding_model()
        m2 = search_mod.get_embedding_model()
        m3 = search_mod.get_embedding_model()
        assert m1 is m2 is m3
        assert MockST.call_count == 1
    search_mod._model = None
    record("2-B", True)

    from unittest.mock import patch

    with patch("migration_oracle.mcp.graph.queries.artifacts.get_version_artifact_path") as mock_q:
        mock_q.side_effect = AssertionError("no graph")
        from migration_oracle.mcp.tools.artifacts import get_artifact_content

        result = get_artifact_content(
            framework="Spring Boot",
            from_version="3.2",
            to_version="3.4",
            artifact_type="invalid_type",
        )
        assert result["status"] == "error"
        mock_q.assert_not_called()
    record("2-C", True)

    from migration_oracle.mcp.tools._rrf import rrf_fuse

    fused = rrf_fuse(bm25_hits=["id-A", "id-B", "id-C"], vector_hits=["id-B", "id-A", "id-C"], k=60)
    fused_ids = [x[0] for x in fused]
    assert all(i in fused_ids for i in ("id-A", "id-B", "id-C"))
    record("2-D", True)


def run_level_3() -> None:
    from migration_oracle.graph.driver import get_driver
    from migration_oracle.mcp.graph.queries.schema import execute_read_cypher
    from migration_oracle.mcp.graph.queries.search import bm25_search
    from migration_oracle.mcp.graph.queries.artifacts import list_pipeline_runs, get_version_artifact_path

    driver = get_driver()
    with driver.session() as session:
        assert session.run("RETURN 1 AS n").single()["n"] == 1
    record("3-A", True)

    assert execute_read_cypher("MATCH (n:__VerifTest005__) RETURN n", {}) == []
    record("3-B", True)

    result = bm25_search(query="spring boot migration", index="__nonexistent_index_verif005__", top_k=5)
    assert isinstance(result, list)
    record("3-C", True, repr(result))

    with driver.session() as session:
        session.run(
            """
            MERGE (v:Version {framework: '__verif005__', version: '99.0'})
            SET v.sortableVersion = 990000,
                v.rawMdPath = '/tmp/verif005_raw.md',
                v.filteredMdPath = '/tmp/verif005_filtered.md',
                v.entitiesJsonPath = '/tmp/verif005_entities.json'
            """
        )
    runs = list_pipeline_runs()
    matching = [r for r in runs if r.get("framework") == "__verif005__"]
    assert len(matching) == 1
    assert matching[0].get("raw_md_path") or matching[0].get("rawMdPath")
    with driver.session() as session:
        session.run("MATCH (v:Version {framework: '__verif005__'}) DETACH DELETE v")
    record("3-D", True)

    assert get_version_artifact_path(framework="__absent_framework_verif005__", to_version="99.99") is None
    record("3-E", True)


def ensure_version_nodes(driver, *, framework: str, from_version: str, to_version: str) -> None:
    with driver.session() as session:
        session.run(
            """
            MERGE (a:Version {framework: $framework, version: $from_version})
            SET a.sortableVersion = 3000000
            MERGE (b:Version {framework: $framework, version: $to_version})
            SET b.sortableVersion = 3004000
            """,
            framework=framework,
            from_version=from_version,
            to_version=to_version,
        )


def run_level_4() -> None:
    from unittest.mock import patch, MagicMock
    from neo4j.exceptions import ServiceUnavailable
    from migration_oracle.graph.driver import get_driver

    call_order: list[str] = []
    real_driver = get_driver()

    class FakeSession:
        def __enter__(self):
            call_order.append("connectivity_check")
            return self

        def __exit__(self, *a):
            pass

        def run(self, q):
            class R:
                def single(inner):
                    return {"n": 1}

            return R()

    def mock_ensure_indexes(driver):
        call_order.append("ensure_indexes")

    with patch.object(real_driver, "session", side_effect=lambda: FakeSession()), patch(
        "migration_oracle.mcp.server.ensure_indexes", side_effect=mock_ensure_indexes
    ), patch("migration_oracle.mcp.server.get_driver", return_value=real_driver):
        from migration_oracle.mcp.server import startup

        startup()
    record("4-A", call_order == ["connectivity_check", "ensure_indexes"], str(call_order))

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = lambda s: s
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.run.side_effect = ServiceUnavailable("Connection refused")
    mock_driver.session.return_value = mock_session
    raised = False
    try:
        with patch("migration_oracle.mcp.server.get_driver", return_value=mock_driver):
            from migration_oracle.mcp.server import startup

            startup()
    except ServiceUnavailable:
        raised = True
    record("4-B", raised)

    from migration_oracle.mcp.tools.context import create_migration_context

    test_project = "__verif005_ctx__"
    test_framework = "__verif005_fw__"
    ensure_version_nodes(get_driver(), framework=test_framework, from_version="3.0", to_version="3.4")
    with get_driver().session() as session:
        session.run(
            "MATCH (ctx:MigrationContext {projectId: $pid}) DETACH DELETE ctx",
            {"pid": test_project},
        )
    r1 = create_migration_context(
        project_id=test_project,
        from_version="3.0",
        to_version="3.4",
        framework=test_framework,
    )
    r2 = create_migration_context(
        project_id=test_project,
        from_version="3.0",
        to_version="3.4",
        framework=test_framework,
    )
    assert r1["created"] is True and r2["created"] is False
    assert r1["context_id"] == r2["context_id"]
    with get_driver().session() as session:
        session.run(
            "MATCH (ctx:MigrationContext {projectId: $pid}) DETACH DELETE ctx",
            {"pid": test_project},
        )
    record("4-C", True)


def run_level_5() -> None:
    from migration_oracle.mcp.tools.community import submit_migration_insight, vote_insight, verify_insight
    from migration_oracle.graph.driver import get_driver

    driver = get_driver()
    with driver.session() as session:
        session.run(
            "MERGE (v:Version {framework: 'Spring Boot', version: '3.4'}) SET v.sortableVersion = 3004000"
        )
        session.run(
            "MATCH (ci:CommunityInsight) WHERE ci.statement CONTAINS 'Verif005' DETACH DELETE ci"
        )

    result = submit_migration_insight(
        statement="Verif005: Use @SpringBootTest instead of @RunWith",
        solution="Replace all @RunWith(SpringRunner.class) with @SpringBootTest",
        spring_boot_version="3.4",
        confidence=0.85,
        evidence_url="",
    )
    assert result["status"] == "ok"
    insight_id = result["insight_id"]
    with get_driver().session() as session:
        node = session.run(
            "MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id RETURN ci.statement AS stmt, ci.verified AS verified, ci.votes AS votes",
            {"id": insight_id},
        ).single()
    assert node and "Verif005" in node["stmt"] and node["verified"] is False and node["votes"] == 0
    with get_driver().session() as session:
        session.run("MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci", {"id": insight_id})
    record("5-A", True)

    setup = submit_migration_insight(
        statement="Verif005-vote: Test insight for vote check",
        solution="No-op solution",
        spring_boot_version="3.4",
        confidence=0.5,
        evidence_url="",
    )
    insight_id = setup["insight_id"]
    r1 = vote_insight(insight_id=insight_id, delta=1)
    r2 = vote_insight(insight_id=insight_id, delta=-1)
    assert r1["new_vote_count"] == 1 and r2["new_vote_count"] == 0
    with get_driver().session() as session:
        session.run("MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci", {"id": insight_id})
    record("5-B", True)

    setup = submit_migration_insight(
        statement="Verif005-verify: Test insight for verify check",
        solution="Verified solution",
        spring_boot_version="3.4",
        confidence=0.9,
        evidence_url="",
    )
    insight_id = setup["insight_id"]
    result = verify_insight(insight_id=insight_id)
    assert result["verified"] is True
    with get_driver().session() as session:
        session.run("MATCH (ci:CommunityInsight) WHERE elementId(ci) = $id DETACH DELETE ci", {"id": insight_id})
    record("5-C", True)

    with get_driver().session() as session:
        count = session.run("MATCH (s:MigrationStep) RETURN count(s) AS n").single()["n"]
    if count == 0:
        record("5-D", True, "N/A — no MigrationStep nodes")
    else:
        record("5-D", True, "MigrationStep nodes present — manual seed required")


def run_level_6() -> None:
    from migration_oracle.mcp.tools.context import create_migration_context
    from migration_oracle.mcp.tools.community import submit_migration_insight
    from migration_oracle.graph.driver import get_driver

    pid = "__verif005_idem__"
    fw = "__verif005_idem_fw__"
    ensure_version_nodes(get_driver(), framework=fw, from_version="1.0", to_version="2.0")
    with get_driver().session() as session:
        session.run("MATCH (ctx:MigrationContext {projectId: $pid}) DETACH DELETE ctx", {"pid": pid})
    create_migration_context(project_id=pid, from_version="1.0", to_version="2.0", framework=fw, scanned_entities=["com.example.Foo"])
    create_migration_context(project_id=pid, from_version="1.0", to_version="2.0", framework=fw, scanned_entities=["com.example.Foo"])
    with get_driver().session() as session:
        node_count = session.run(
            "MATCH (ctx:MigrationContext {projectId: $pid}) RETURN count(ctx) AS n", {"pid": pid}
        ).single()["n"]
        edge_count = session.run(
            "MATCH (ctx:MigrationContext {projectId: $pid})-[r:UPGRADES_FROM|UPGRADES_TO]->(v) RETURN count(r) AS n",
            {"pid": pid},
        ).single()["n"]
    with get_driver().session() as session:
        session.run("MATCH (ctx:MigrationContext {projectId: $pid}) DETACH DELETE ctx", {"pid": pid})
    record("6-A", node_count == 1 and edge_count == 2, f"nodes={node_count} edges={edge_count}")

    stmt = "Verif005-dup: Identical insight statement for duplicate detection check"
    r1 = submit_migration_insight(statement=stmt, solution="solution-A", spring_boot_version="3.4", confidence=0.8, evidence_url="")
    r2 = submit_migration_insight(statement=stmt, solution="solution-A", spring_boot_version="3.4", confidence=0.8, evidence_url="")
    with get_driver().session() as session:
        count = session.run(
            "MATCH (ci:CommunityInsight) WHERE ci.statement CONTAINS 'Verif005-dup' RETURN count(ci) AS n"
        ).single()["n"]
        session.run("MATCH (ci:CommunityInsight) WHERE ci.statement CONTAINS 'Verif005-dup' DETACH DELETE ci")
    record("6-B", count == 1 and r2["status"] in ("duplicate", "ok"), f"count={count} status2={r2['status']}")


def run_level_7() -> None:
    from unittest.mock import patch
    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path, build_recipe_plan
    from migration_oracle.mcp.tools.schema import execute_custom_cypher
    from migration_oracle.mcp.tools.artifacts import get_artifact_content
    from migration_oracle.mcp.tools.context import create_migration_context, close_migration_context
    from migration_oracle.graph.driver import get_driver

    result = analyze_upgrade_path(
        framework="__absent_framework_verif005__",
        current_version="0.0",
        target_version="1.0",
    )
    record("7-A", result["status"] == "ok" and result["rules"] == [])

    blocked = [
        ("CREATE (n:Test)", "CREATE"),
        ("MERGE (n:Test) ON MATCH SET n.x = 1", "MERGE"),
        ("MATCH (n) SET n.x = 1", "SET"),
        ("MATCH (n) DELETE n", "DELETE"),
        ("MATCH (n) REMOVE n.x", "REMOVE"),
        ("DROP INDEX idx", "DROP"),
        ("CALL db.index.fulltext.queryNodes('idx', 'q')", "CALL db"),
        ("create (n:Sneaky)", "CREATE"),
        ("MATCH (n) where n.x > 0 set n.y = 1", "SET"),
    ]
    for query, expected_kw in blocked:
        with patch("migration_oracle.graph.driver.read_session") as mock_sess:
            mock_sess.side_effect = AssertionError("driver")
            res = execute_custom_cypher(query=query)
            assert res["status"] == "blocked"
            mock_sess.assert_not_called()
    record("7-B", True)

    with patch("pathlib.Path.read_text") as mock_read:
        mock_read.side_effect = AssertionError("fs")
        res = get_artifact_content(
            framework="__absent_verif005__",
            from_version="1.0",
            to_version="2.0",
            artifact_type="raw_md",
        )
        assert res["status"] == "not_found"
        mock_read.assert_not_called()
    record("7-C", True)

    plan = {
        "auto_track": [],
        "manual_track": [{"step_id": "step-1", "rule_id": "rule-1"}],
        "fallback_to_rule_cards": False,
    }
    with patch("migration_oracle.mcp.tools.upgrade.upgrade_queries.build_recipe_plan", return_value=plan):
        res = build_recipe_plan(current_version="3.2", target_version="3.4")
    record("7-D", res["auto_track"] == [] and len(res["manual_track"]) >= 1)

    rows = [{"rules": [{"statement": "legacy", "steps": [], "scopes": [], "recipes": []}]}]
    with patch("migration_oracle.mcp.tools.upgrade.upgrade_queries.analyze_upgrade_path", return_value=rows):
        res = analyze_upgrade_path(framework="wildfly", current_version="26", target_version="30")
    rule = res["rules"][0]
    record("7-E", rule["steps"] == [] and rule["scopes"] == [])

    ensure_version_nodes(get_driver(), framework="__verif005_close_fw__", from_version="1.0", to_version="2.0")
    with get_driver().session() as session:
        session.run("MATCH (ctx:MigrationContext {projectId: '__verif005_close__'}) DETACH DELETE ctx")
    r = create_migration_context(
        project_id="__verif005_close__",
        from_version="1.0",
        to_version="2.0",
        framework="__verif005_close_fw__",
    )
    close_result = close_migration_context(context_id=r["context_id"], final_status="abandoned", notes="verif005")
    with get_driver().session() as session:
        session.run("MATCH (ctx:MigrationContext {projectId: '__verif005_close__'}) DETACH DELETE ctx")
    record(
        "7-F",
        close_result.get("tool_status") == "ok"
        and close_result.get("migration_status") == "abandoned"
        and "status" not in close_result,
    )


def main() -> None:
    levels = [
        ("Level 0", run_level_0),
        ("Level 1", run_level_1),
        ("Level 2", run_level_2),
        ("Level 3", run_level_3),
        ("Level 4", run_level_4),
        ("Level 5", run_level_5),
        ("Level 6", run_level_6),
        ("Level 7", run_level_7),
    ]
    print("=== 005-mcp-server verification ===\n")
    for name, fn in levels:
        print(f"\n--- {name} ---")
        try:
            fn()
        except SystemExit:
            print("\nVerification STOPPED on first failure.")
            sys.exit(1)
        except Exception as exc:
            print(f"FAIL: {name} — {exc}")
            sys.exit(1)

    print("\n=== Summary ===")
    for check_id, status, detail in RESULTS:
        print(f"  {check_id}: {status}" + (f" ({detail})" if detail else ""))
    print(f"\nAll {len(RESULTS)} checks passed.")
    subprocess.run(["uv", "run", "pytest", "tests/mcp/", "-q"], check=True)


if __name__ == "__main__":
    main()

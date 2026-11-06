"""Backfill script (spec 027 FR-6, AC-7): only the FR-5 properties, idempotent."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "classify_signals.py"


def _script():
    spec = importlib.util.spec_from_file_location("classify_signals", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self._rows = rows or []

    def __iter__(self):
        return iter(self._rows)

    def single(self):
        return self._rows[0] if self._rows else None


class _Session:
    """Fake Neo4j session over a ruleId → properties map."""

    def __init__(self, graph: dict[str, dict]) -> None:
        self.graph = graph

    def run(self, query: str, **params):
        q = " ".join(query.split())
        if "WHERE r.ruleId IN $ids" in q:
            present = [{"ruleId": rule_id} for rule_id in params["ids"] if rule_id in self.graph]
            return _Result(present)
        if "MATCH (r:MigrationRule {ruleId: $id})" in q and "SET r += $props" in q:
            node = self.graph[params["id"]]
            before = dict(node)
            node.update(params["props"])
            return _Result([{"before": before}])
        raise AssertionError(f"unexpected query: {q}")

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.fixture
def backfill(monkeypatch: pytest.MonkeyPatch):
    # The script loads the developer's .env at import; keep it out of the tests.
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: False)
    module = _script()
    graph: dict[str, dict] = {}
    driver = pytest.importorskip("migration_oracle.graph.driver")
    monkeypatch.setattr(driver, "read_session", lambda: _Session(graph))
    monkeypatch.setattr(driver, "write_session", lambda: _Session(graph))
    return module, graph


PROPS = {
    "pipeline://Angular/20.0.0/rule a": {
        "signal": "symbol",
        "signalConfidence": 0.9,
        "signalSource": "model",
        "signalKeys": ["npm:@angular/core#DestroyRef"],
        "features": ["testbed"],
        "signalQuestionsVersion": 1,
        "signalModel": "nimble",
    },
    "pipeline://Angular/20.0.0/rule b": {
        "signal": "behavioral",
        "signalConfidence": 0.8,
        "signalSource": "model",
        "signalKeys": [],
        "features": [],
        "signalQuestionsVersion": 1,
        "signalModel": "nimble",
    },
}


def test_ac7_sets_only_the_fr5_properties(backfill) -> None:
    module, graph = backfill
    graph["pipeline://Angular/20.0.0/rule a"] = {"statement": "keep me", "title": "rule a"}
    graph["pipeline://Angular/20.0.0/rule b"] = {"statement": "also keep me"}

    updated, unchanged, unknown = module._apply(PROPS, dry_run=False)

    assert (updated, unchanged, unknown) == (2, 0, [])
    node = graph["pipeline://Angular/20.0.0/rule a"]
    assert node["statement"] == "keep me"
    assert node["signal"] == "symbol"
    assert node["signalKeys"] == ["npm:@angular/core#DestroyRef"]
    assert "ruleId" not in node  # the script never rewrites identity
    assert node["signalQuestionsVersion"] == 1
    assert graph["pipeline://Angular/20.0.0/rule b"]["statement"] == "also keep me"


def test_ac7_second_run_changes_nothing(backfill) -> None:
    module, graph = backfill
    graph["pipeline://Angular/20.0.0/rule a"] = {}
    graph["pipeline://Angular/20.0.0/rule b"] = {}
    module._apply(PROPS, dry_run=False)
    before = {rule_id: dict(node) for rule_id, node in graph.items()}

    updated, unchanged, unknown = module._apply(PROPS, dry_run=False)

    assert updated == 0
    assert unchanged == 2
    assert unknown == []
    assert graph == before


def test_ac7_unknown_rule_ids_are_reported(backfill) -> None:
    module, graph = backfill
    graph["pipeline://Angular/20.0.0/rule a"] = {}

    updated, unchanged, unknown = module._apply(PROPS, dry_run=False)

    assert updated == 1
    assert unchanged == 0
    assert unknown == ["pipeline://Angular/20.0.0/rule b"]


def test_ac7_dry_run_does_not_write(backfill) -> None:
    module, graph = backfill
    graph["pipeline://Angular/20.0.0/rule a"] = {}
    graph["pipeline://Angular/20.0.0/rule b"] = {}

    updated, unchanged, unknown = module._apply(PROPS, dry_run=True)

    assert updated == 0
    assert unchanged == 2
    assert unknown == []
    assert graph["pipeline://Angular/20.0.0/rule a"] == {}
    assert graph["pipeline://Angular/20.0.0/rule b"] == {}

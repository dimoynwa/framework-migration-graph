"""Populator wiring (spec 027 FR-5, FR-6) and the backfill rules (AC-7).

The fake session mirrors the populator's Cypher, including ``SET r += $props``
for the signal properties.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from migration_oracle.models.entities import (
    AffectedEntity,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
)
from migration_oracle.pipeline import populator
from migration_oracle.pipeline.canonical.api_index import build_hop_index
from migration_oracle.pipeline.signals.settings import SignalSettings
from migration_oracle.pipeline.triage.client import FakeTriageClient
from migration_oracle.pipeline.triage.settings import TriageSettings


@dataclass
class GraphState:
    nodes: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    edges: set[tuple[str, str, str, str, str]] = field(default_factory=set)

    def merge_node(self, label: str, key: str, props: dict[str, Any]) -> None:
        existing = self.nodes.setdefault((label, key), {})
        existing.update(props)


class FakeResult:
    def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
        self._data = data or []

    def single(self) -> dict[str, Any] | None:
        return self._data[0] if self._data else None


_LABELS = ("TemplateSyntax", "DiagnosticCode", "ApplicationProperty", "Dependency", "Class")


class FakeSession:
    def __init__(self, state: GraphState) -> None:
        self.state = state

    def run(self, query: str, **params: Any) -> FakeResult:
        q = " ".join(query.split())
        if "MERGE (v:Version" in q:
            key = f"{params['framework']}:{params['version']}"
            self.state.merge_node("Version", key, {"sortableVersion": params["sortable_version"]})
            return FakeResult()
        if "MERGE (rule:MigrationRule" in q:
            self.state.merge_node(
                "MigrationRule", params["source_url"], {"title": params["title"]}
            )
            version_key = f"{params['framework']}:{params['version']}"
            self.state.edges.add(
                ("Version", version_key, "INCLUDES_RULE", "MigrationRule", params["source_url"])
            )
            return FakeResult([{"rule_id": params["source_url"]}])
        if "SET rule += $props" in q:
            rule_key = params["rule_id"]
            node = self.state.nodes.setdefault(("MigrationRule", rule_key), {})
            node.update(params["props"])
            return FakeResult()
        if "MERGE (bs:BreakingScope" in q:
            return FakeResult()
        if "MERGE (s:MigrationStep" in q and "AUTOMATED_BY" not in q:
            step_key = f"{params['rule_id']}:{params['step_index']}"
            self.state.merge_node("MigrationStep", step_key, {"stepType": params["step_type"]})
            return FakeResult()
        if "MERGE (e:" in q and "key: $key" in q:
            label = self._label(q)
            self.state.merge_node(
                label,
                params["key"],
                {
                    "name": params.get("name"),
                    "package": params.get("package"),
                    "symbol": params.get("symbol"),
                    "member": params.get("member"),
                    "file": params.get("file"),
                    "ecosystem": params.get("ecosystem"),
                    "verified": params.get("verified"),
                },
            )
            return FakeResult()
        return FakeResult()

    @staticmethod
    def _label(q: str) -> str:
        for label in _LABELS:
            if f"(e:{label}" in q or f"(old:{label}" in q:
                return label
        raise AssertionError(f"no known entity label in query: {q}")


@pytest.fixture
def graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GraphState:
    state = GraphState()

    class FakeWriteSession:
        def __enter__(self) -> FakeSession:
            return FakeSession(state)

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(populator, "write_session", lambda: FakeWriteSession())
    monkeypatch.setattr(populator, "get_driver", lambda: object())
    monkeypatch.setattr(populator, "ensure_indexes", lambda _driver: None)
    monkeypatch.setattr(populator.pipeline_queries, "version_exists", lambda *_: False)
    monkeypatch.setattr(
        populator.pipeline_queries, "upsert_version_artifact_paths", lambda **_kw: None
    )
    monkeypatch.setattr(populator.pipeline_queries, "merge_version", lambda **_kw: None)
    return state


def _index():
    return build_hop_index(
        ("19.2.0", "20.0.0"),
        [{"@angular/core/testing": {"TestBed": ["get", "inject"]}, "@angular/core": {}}],
    )


def _patch_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "migration_oracle.pipeline.canonical.run.load_hop_index",
        lambda *_a, **_kw: _index(),
    )


def _batch(*rules: list[AffectedEntity]) -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": f"rule {number}",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "api-surface", "severity": "high"}],
                "entities": [entity.model_dump() for entity in group],
            }
            for number, group in enumerate(rules)
        ]
    )


def _affected(kind: str, name: str, role: str = "removed") -> AffectedEntity:
    return AffectedEntity(kind=EntityKind(kind), name=name, role=EntityRole(role))


def _signal_settings(tmp_path: Path, **overrides: object) -> SignalSettings:
    client = TriageSettings(
        base_url=str(overrides.pop("base_url", "http://triage.example")),
        endpoint_path="/v1/systemone",
        model="nimble",
        api_key="",
        timeout_sec=30.0,
        max_concurrent=2,
        state_max_chars=6000,
        drop_max_action_prob=0.2,
        drop_min_category_prob=0.8,
        drop_max_impact_score=1.0,
        filter_max_input_tokens=60000,
        cache_dir=tmp_path / "artifacts",
    )
    return SignalSettings(
        client=client,
        state_max_chars=4000,
        searchable_min_prob=float(overrides.pop("searchable_min_prob", 0.70)),
        universal_min_prob=float(overrides.pop("universal_min_prob", 0.60)),
        feature_min_prob=float(overrides.pop("feature_min_prob", 0.50)),
        cache_dir=tmp_path / "artifacts",
    )


def _symbol_answers(probability: float = 0.92, testbed: float = 0.88) -> dict:
    probabilities = {
        "symbol": probability,
        "config": 0.01,
        "dependency": 0.01,
        "syntax": 0.01,
        "behavioral": 1 - probability - 0.03,
        "universal": 0.01,
    }
    return {
        "signal": {
            "type": "choice",
            "choice": "symbol",
            "probabilities": probabilities,
            "confidence": 0.4,
        },
        "feature.testbed": {"type": "noul", "noul": testbed},
        "feature.ssr": {"type": "noul", "noul": 0.1},
    }


def _populate(
    graph: GraphState,
    monkeypatch: pytest.MonkeyPatch,
    batch: MigrationEntitiesBatch,
    tmp_path: Path,
    **overrides,
) -> populator.PopulationResult:
    kwargs = dict(
        batch=batch,
        framework_display="Angular",
        framework_key="angular",
        to_version="20.0.0",
        from_version="19.2.0",
        raw_md_path="runs/raw/x.md",
        filtered_md_path="runs/nodes/x.md",
        entities_json_path="runs/json/x.json",
        skip_if_version_exists=False,
        canonical_jsonl_path=tmp_path / "canonical.jsonl",
        canonical_summary_path=tmp_path / "canonical-summary.json",
        signals_jsonl_path=tmp_path / "signals.jsonl",
        signals_summary_path=tmp_path / "signals-summary.json",
    )
    kwargs.update(overrides)
    return populator.populate_graph(**kwargs)


def test_fr5_signal_properties_are_written_with_the_rule(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch([_affected("class", "TestBed.get")])
    result = _populate(
        graph,
        monkeypatch,
        batch,
        tmp_path,
        signal_client=FakeTriageClient(_symbol_answers()),
        signal_settings=_signal_settings(tmp_path),
    )

    assert result.signal_status == "ok"
    assert result.signals_written == 1
    node = graph.nodes[("MigrationRule", "pipeline://Angular/20.0.0/rule 0")]
    assert node["signal"] == "symbol"
    assert node["signalConfidence"] == pytest.approx(0.92)
    assert node["signalSource"] == "model"
    assert node["signalKeys"] == ["npm:@angular/core/testing#TestBed.get"]
    assert node["features"] == ["testbed"]
    assert node["signalQuestionsVersion"] == 1
    assert node["signalModel"] == "nimble"


def test_fr5_only_the_fr5_properties_are_set(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch([_affected("class", "TestBed.get")])
    _populate(
        graph,
        monkeypatch,
        batch,
        tmp_path,
        signal_client=FakeTriageClient(_symbol_answers()),
        signal_settings=_signal_settings(tmp_path),
    )
    node = graph.nodes[("MigrationRule", "pipeline://Angular/20.0.0/rule 0")]
    assert set(node) == {
        "title",
        "signal",
        "signalConfidence",
        "signalSource",
        "signalKeys",
        "features",
        "signalQuestionsVersion",
        "signalModel",
    }


def test_skip_signals_writes_no_signal_properties(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    client = FakeTriageClient(_symbol_answers())
    batch = _batch([_affected("class", "TestBed.get")])
    result = _populate(
        graph,
        monkeypatch,
        batch,
        tmp_path,
        skip_signals=True,
        signal_client=client,
        signal_settings=_signal_settings(tmp_path),
    )
    assert result.signal_status == "skipped"
    assert result.signals_written == 0
    assert client.calls == []
    node = graph.nodes[("MigrationRule", "pipeline://Angular/20.0.0/rule 0")]
    assert "signal" not in node


def test_ac6_populate_succeeds_when_nimble_is_disabled(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch([_affected("class", "TestBed.get")])
    result = _populate(
        graph,
        monkeypatch,
        batch,
        tmp_path,
        signal_client=FakeTriageClient(_symbol_answers()),
        signal_settings=_signal_settings(tmp_path, base_url=""),
    )
    assert result.skipped is False
    assert result.rules_written == 1
    assert result.signal_status == "disabled"
    assert result.signals_written == 0
    # The rule is still there; the planner reads it as ``behavioral``.
    assert ("MigrationRule", "pipeline://Angular/20.0.0/rule 0") in graph.nodes


def test_dry_run_writes_signal_artifacts_but_no_graph(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch([_affected("class", "TestBed.get")])
    result = _populate(
        graph,
        monkeypatch,
        batch,
        tmp_path,
        dry_run=True,
        signal_client=FakeTriageClient(_symbol_answers()),
        signal_settings=_signal_settings(tmp_path),
    )
    assert result.skipped is True
    assert result.signal_status == "ok"
    assert result.signals_written == 1
    assert graph.nodes == {}
    assert (tmp_path / "signals.jsonl").exists()
    assert (tmp_path / "signals-summary.json").exists()


def test_partial_nimble_writes_only_the_classified_rules(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from migration_oracle.pipeline.triage.client import TriageTransportError

    _patch_index(monkeypatch)
    batch = _batch(
        [_affected("class", "TestBed.get")],
        [_affected("class", "VERSION")],
    )
    # First rule succeeds, the second cannot be classified.
    client = FakeTriageClient([_symbol_answers(), TriageTransportError("timeout")])
    result = _populate(
        graph,
        monkeypatch,
        batch,
        tmp_path,
        signal_client=client,
        signal_settings=_signal_settings(tmp_path, searchable_min_prob=0.70),
    )
    assert result.signal_status == "partial"
    assert result.signals_written == 1
    rule_nodes = [key for label, key in graph.nodes if label == "MigrationRule"]
    assert len(rule_nodes) == 2
    classified = [
        node
        for (label, _key), node in graph.nodes.items()
        if label == "MigrationRule" and "signal" in node
    ]
    assert len(classified) == 1

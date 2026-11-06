"""Populator graph-write tests (spec 025 AC-3, AC-4, FR-4.4).

The fake session mirrors the populator's Cypher: entity nodes merge on the
canonical ``key`` and carry ``name`` / ``package`` / ``symbol`` / ``member`` /
``file`` / ``ecosystem`` / ``verified``.
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


@dataclass
class GraphState:
    nodes: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    edges: set[tuple[str, str, str, str, str]] = field(default_factory=set)

    def merge_node(self, label: str, key: str, props: dict[str, Any]) -> None:
        existing = self.nodes.setdefault((label, key), {})
        existing.update(props)

    def merge_edge(self, from_label: str, from_key: str, rel: str, to_label: str, to_key: str) -> None:
        self.edges.add((from_label, from_key, rel, to_label, to_key))


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
            self.state.merge_node("MigrationRule", params["source_url"], {"title": params["title"]})
            version_key = f"{params['framework']}:{params['version']}"
            self.state.merge_edge(
                "Version", version_key, "INCLUDES_RULE", "MigrationRule", params["source_url"]
            )
            return FakeResult([{"rule_id": params["source_url"]}])
        if "MERGE (bs:BreakingScope" in q:
            return FakeResult()
        if "MERGE (s:MigrationStep" in q and "AUTOMATED_BY" not in q:
            step_key = f"{params['rule_id']}:{params['step_index']}"
            self.state.merge_node("MigrationStep", step_key, {"stepType": params["step_type"]})
            return FakeResult()
        # Step → entity writes and rule → entity writes merge on {key}
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
            if "MATCH (s:MigrationStep" in q:
                step_key = f"{params['rule_id']}:{params['step_index']}"
                self.state.merge_edge("MigrationStep", step_key, self._edge(q), label, params["key"])
            elif "MATCH (rule:MigrationRule" in q:
                rule_key = next(
                    k for label, k in self.state.nodes if label == "MigrationRule"
                )
                self.state.merge_edge(
                    "MigrationRule", rule_key, self._edge(q), label, params["key"]
                )
            return FakeResult()
        for rel in ("REMOVED_IN", "INTRODUCED_IN", "DEPRECATED_IN"):
            if f"MERGE (e)-[:{rel}]" in q:
                label = self._label(q)
                version_key = f"{params['framework']}:{params['version']}"
                self.state.merge_edge(label, params["key"], rel, "Version", version_key)
                return FakeResult()
        if "MERGE (old)-[:REPLACED_BY]->(new)" in q:
            label = self._label(q)
            self.state.merge_edge(
                label, params["removed_key"], "REPLACED_BY", label, params["replacement_key"]
            )
            return FakeResult()
        return FakeResult()

    @staticmethod
    def _label(q: str) -> str:
        for label in _LABELS:
            if f"(e:{label}" in q or f"(old:{label}" in q or f"(new:{label}" in q or f"(c:{label}" in q:
                return label
        raise AssertionError(f"no known entity label in query: {q}")

    @staticmethod
    def _edge(q: str) -> str:
        for edge in (
            "AFFECTS_SYNTAX",
            "AFFECTS_DIAGNOSTIC",
            "AFFECTS_PROPERTY",
            "AFFECTS_DEPENDENCY",
            "AFFECTS_CLASS",
        ):
            if f":{edge}]" in q:
                return edge
        raise AssertionError(f"no known AFFECTS edge in query: {q}")


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
    monkeypatch.setattr(populator.pipeline_queries, "upsert_version_artifact_paths", lambda **_kw: None)
    monkeypatch.setattr(populator.pipeline_queries, "merge_version", lambda **_kw: None)
    return state


def _batch(*rules: list[AffectedEntity]) -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            {
                "source_section": "breaking_change",
                "title": f"rule {number}",
                "change_type": "breaking_change",
                "reason": "r",
                "scopes": [{"scope": "api-surface", "severity": "high"}],
                "entities": [e.model_dump() for e in group],
            }
            for number, group in enumerate(rules)
        ]
    )


def _affected(kind: str, name: str, role: str = "removed", package: str = "") -> AffectedEntity:
    return AffectedEntity(kind=EntityKind(kind), name=name, role=EntityRole(role), package=package)


def _populate(graph: GraphState, monkeypatch: pytest.MonkeyPatch, batch: MigrationEntitiesBatch, **overrides):
    canonical_dir = overrides.pop("canonical_dir", None)
    kwargs = dict(
        batch=batch,
        framework_display="Angular",
        framework_key="angular",
        to_version="20.1.0",
        from_version="20.0.0",
        raw_md_path="runs/raw/x.md",
        filtered_md_path="runs/nodes/x.md",
        entities_json_path="runs/json/x.json",
        skip_if_version_exists=False,
        # Signal artifacts stay out of runs/: these tests are about the graph.
        skip_signals=True,
    )
    kwargs.update(overrides)
    if canonical_dir is not None:
        kwargs["canonical_jsonl_path"] = canonical_dir / "canonical.jsonl"
        kwargs["canonical_summary_path"] = canonical_dir / "summary.json"
        kwargs["signals_jsonl_path"] = canonical_dir / "signals.jsonl"
        kwargs["signals_summary_path"] = canonical_dir / "signals-summary.json"
    return populator.populate_graph(**kwargs)


def _index() -> Any:
    return build_hop_index(
        ("20.0.0", "20.1.0"),
        [{"@angular/core": {"InjectFlags": ["Static"], "VERSION": []}, "@angular/router": {"VERSION": []}}],
    )


def _patch_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "migration_oracle.pipeline.canonical.run.load_hop_index",
        lambda *_a, **_kw: _index(),
    )


# --- AC-3: idempotent writes ---------------------------------------------------


def test_populate_twice_creates_no_new_nodes(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch([_affected("class", "@angular/core InjectFlags")])
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    first_nodes = dict(graph.nodes)
    first_edges = set(graph.edges)
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    assert graph.nodes == first_nodes
    assert graph.edges == first_edges


# --- AC-3: two spellings share one node -------------------------------------------


def test_two_spellings_of_one_symbol_share_one_node(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch(
        [_affected("class", "InjectFlags")],
        [_affected("class", "@angular/core InjectFlags")],
    )
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    class_nodes = [key for label, key in graph.nodes if label == "Class"]
    assert class_nodes == ["npm:@angular/core#InjectFlags"]
    node = graph.nodes[("Class", "npm:@angular/core#InjectFlags")]
    assert node["name"] == "InjectFlags"
    assert node["package"] == "@angular/core"
    assert node["verified"] == "true"


# --- AC-3: VERSION from two entry points --------------------------------------------


def test_version_from_two_entry_points_with_llm_packages_is_two_nodes(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch(
        [_affected("class", "VERSION", package="@angular/core")],
        [_affected("class", "VERSION", package="@angular/router")],
    )
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    class_nodes = sorted(key for label, key in graph.nodes if label == "Class")
    assert class_nodes == ["npm:@angular/core#VERSION", "npm:@angular/router#VERSION"]


def test_ambiguous_version_without_hint_is_one_node(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch(
        [_affected("class", "VERSION")],
        [_affected("class", "VERSION")],
    )
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    class_nodes = [key for label, key in graph.nodes if label == "Class"]
    assert class_nodes == ["npm:?#VERSION"]
    assert graph.nodes[("Class", "npm:?#VERSION")]["verified"] == "ambiguous"


# --- new labels (FR-4.2) ---------------------------------------------------------------


def test_syntax_and_diagnostic_get_their_own_labels_and_edges(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch(
        [_affected("property", "in", role="mentioned"), _affected("property", "NG8115", role="mentioned")]
    )
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    assert ("TemplateSyntax", "syntax:angular-template#in") in graph.nodes
    assert ("DiagnosticCode", "diag:NG8115") in graph.nodes
    assert any(e[2] == "AFFECTS_SYNTAX" for e in graph.edges)
    assert any(e[2] == "AFFECTS_DIAGNOSTIC" for e in graph.edges)


def test_member_is_stored_with_the_class_label(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "migration_oracle.pipeline.canonical.run.load_hop_index",
        lambda *_a, **_kw: build_hop_index(
            ("20.0.0", "20.1.0"), [{"@angular/core/testing": {"TestBed": ["get", "inject"]}}]
        ),
    )
    batch = _batch([_affected("class", "TestBed.get")])
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    assert ("Class", "npm:@angular/core/testing#TestBed.get") in graph.nodes
    assert graph.nodes[("Class", "npm:@angular/core/testing#TestBed.get")]["name"] == "TestBed.get"


# --- dry-run (FR-5) ---------------------------------------------------------------------


def test_dry_run_writes_canonical_artifacts_but_not_the_graph(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch([_affected("class", "@angular/core InjectFlags")])
    result = _populate(
        graph, monkeypatch, batch, dry_run=True, canonical_dir=tmp_path
    )
    assert result.skipped is True
    assert graph.nodes == {} and graph.edges == set()
    assert (tmp_path / "canonical.jsonl").exists()
    assert (tmp_path / "summary.json").exists()


def test_populate_writes_canonical_artifacts_also_when_writing(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    batch = _batch([_affected("class", "@angular/core InjectFlags")])
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    assert (tmp_path / "canonical.jsonl").exists()
    assert (tmp_path / "summary.json").exists()


def test_existing_version_skips_before_canonicalization(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An existing Version node is not repopulated: no index fetch, no audit rewrite."""
    def _no_fetch(*_a, **_kw):
        raise AssertionError("API index must not be loaded for a skipped hop")

    monkeypatch.setattr("migration_oracle.pipeline.canonical.run.load_hop_index", _no_fetch)
    monkeypatch.setattr(populator.pipeline_queries, "version_exists", lambda *_: True)
    batch = _batch([_affected("class", "@angular/core InjectFlags")])
    result = _populate(
        graph, monkeypatch, batch, skip_if_version_exists=True, canonical_dir=tmp_path
    )
    assert result.skipped is True
    assert graph.nodes == {}
    assert not (tmp_path / "canonical.jsonl").exists()


def test_dry_run_on_existing_version_still_writes_audit(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_index(monkeypatch)
    monkeypatch.setattr(populator.pipeline_queries, "version_exists", lambda *_: True)
    batch = _batch([_affected("class", "@angular/core InjectFlags")])
    result = _populate(
        graph,
        monkeypatch,
        batch,
        dry_run=True,
        skip_if_version_exists=True,
        canonical_dir=tmp_path,
    )
    assert result.skipped is True
    assert (tmp_path / "canonical.jsonl").exists()


# --- offline populate (AC-4) --------------------------------------------------------------


def test_populate_succeeds_with_unavailable_index(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from migration_oracle.pipeline.canonical.api_index import HopApiIndex

    monkeypatch.setattr(
        "migration_oracle.pipeline.canonical.run.load_hop_index",
        lambda *_a, **_kw: HopApiIndex.unavailable(("20.0.0", "20.1.0")),
    )
    batch = _batch([_affected("class", "InjectFlags")])
    result = _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    assert result.skipped is False
    node = graph.nodes[("Class", "npm:?#InjectFlags")]
    assert node["verified"] == "false"
    import json

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["api_index"]["status"] == "unavailable"


# --- FR-4.4: matching compatibility ------------------------------------------------------------


def test_canonical_names_never_look_like_coordinates(
    graph: GraphState, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """After canonicalization the groupId:artifactId heuristic in
    ``mcp/matching.py`` only sees real dependencies (spec FR-4.4)."""
    from migration_oracle.mcp import matching

    _patch_index(monkeypatch)
    batch = _batch(
        [
            _affected("class", "@angular/router:Router"),
            _affected("property", "TestBed.get", role="mentioned"),
        ]
    )
    _populate(graph, monkeypatch, batch, canonical_dir=tmp_path)
    for label, key in graph.nodes:
        if label not in ("Class", "ApplicationProperty"):
            continue
        name = graph.nodes[(label, key)]["name"]
        assert ":" not in name, (label, name)
        assert " " not in name, (label, name)
    # the raw name would have been read as a Maven coordinate by the heuristic
    assert matching._is_class_fqcn("@angular/router:Router") is False
    assert ":" in "@angular/router:Router"  # what the heuristic keys on
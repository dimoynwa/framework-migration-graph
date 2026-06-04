"""Tests for pipeline graph population idempotency."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from migration_oracle.models.entities import (
    AffectedEntity,
    BreakingScopeInput,
    Effort,
    EntityKind,
    EntityRole,
    MigrationEntitiesBatch,
    MigrationEntity,
    MigrationStep,
    ScopeLevel,
    Severity,
    StepType,
)
from migration_oracle.pipeline import populator


@dataclass
class GraphState:
    nodes: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    edges: set[tuple[str, str, str, str, str]] = field(default_factory=set)

    def merge_node(self, label: str, key: str, props: dict[str, Any]) -> None:
        node_key = (label, key)
        existing = self.nodes.get(node_key, {})
        existing.update(props)
        self.nodes[node_key] = existing

    def merge_edge(
        self,
        from_label: str,
        from_key: str,
        rel: str,
        to_label: str,
        to_key: str,
        props: dict[str, Any] | None = None,
    ) -> None:
        edge = (from_label, from_key, rel, to_label, to_key)
        self.edges.add(edge)
        if props:
            self.nodes.setdefault((from_label, from_key), {})
            self.nodes.setdefault((to_label, to_key), {})


class FakeResult:
    def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
        self._data = data or []

    def single(self) -> dict[str, Any] | None:
        return self._data[0] if self._data else None


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
            rule_id = params["source_url"]
            self.state.merge_node("MigrationRule", params["source_url"], {"title": params["title"]})
            version_key = f"{params['framework']}:{params['version']}"
            self.state.merge_edge("Version", version_key, "INCLUDES_RULE", "MigrationRule", params["source_url"])
            return FakeResult([{"rule_id": rule_id}])
        if "MERGE (bs:BreakingScope" in q:
            scope_key = f"{params['scope']}:{params['severity']}"
            self.state.merge_node("BreakingScope", scope_key, {})
            rule_key = next(k for label, k in self.state.nodes if label == "MigrationRule")
            self.state.merge_edge("MigrationRule", rule_key, "HAS_SCOPE", "BreakingScope", scope_key)
            return FakeResult()
        if "MERGE (s:MigrationStep" in q:
            step_key = f"{params['rule_id']}:{params['step_index']}"
            self.state.merge_node("MigrationStep", step_key, {"stepType": params["step_type"]})
            rule_nodes = [k for label, k in self.state.nodes if label == "MigrationRule"]
            if rule_nodes:
                self.state.merge_edge("MigrationRule", rule_nodes[-1], "REQUIRES_STEP", "MigrationStep", step_key)
            return FakeResult()
        if "MERGE (cur)-[:REQUIRES]->(pre)" in q:
            cur = f"{params['rule_id']}:{params['current']}"
            pre = f"{params['rule_id']}:{params['prereq']}"
            self.state.merge_edge("MigrationStep", cur, "REQUIRES", "MigrationStep", pre)
            return FakeResult()
        if "MATCH (s:MigrationStep" in q and "MERGE (e:" in q:
            label = "Class" if "Class" in q else "ApplicationProperty" if "ApplicationProperty" in q else "Dependency"
            edge = "AFFECTS_CLASS" if label == "Class" else "AFFECTS_PROPERTY" if label == "ApplicationProperty" else "AFFECTS_DEPENDENCY"
            step_key = f"{params['rule_id']}:{params['step_index']}"
            self.state.merge_node(label, params["name"], {})
            self.state.merge_edge("MigrationStep", step_key, edge, label, params["name"])
            return FakeResult()
        if "MERGE (e:Class" in q or "MERGE (e:ApplicationProperty" in q or "MERGE (e:Dependency" in q:
            label = "Class" if "Class" in q else "ApplicationProperty" if "ApplicationProperty" in q else "Dependency"
            self.state.merge_node(label, params["name"], {})
            rule_nodes = [k for label_name, k in self.state.nodes if label_name == "MigrationRule"]
            if rule_nodes and "AFFECTS_" in q:
                edge = "AFFECTS_CLASS" if "AFFECTS_CLASS" in q else "AFFECTS_PROPERTY" if "AFFECTS_PROPERTY" in q else "AFFECTS_DEPENDENCY"
                self.state.merge_edge("MigrationRule", rule_nodes[-1], edge, label, params["name"])
            return FakeResult()
        if "MERGE (old)-[:REPLACED_BY]->(new)" in q:
            label = "Class" if "Class" in q else "ApplicationProperty" if "ApplicationProperty" in q else "Dependency"
            self.state.merge_edge(label, params["removed_name"], "REPLACED_BY", label, params["replacement_name"])
            return FakeResult()
        if "REMOVED_IN" in q:
            label = "Class" if "Class" in q else "ApplicationProperty" if "ApplicationProperty" in q else "Dependency"
            version_key = f"{params['framework']}:{params['version']}"
            self.state.merge_edge(label, params["name"], "REMOVED_IN", "Version", version_key)
            self.state.merge_edge("Version", version_key, "REMOVES", label, params["name"])
            return FakeResult()
        if "INTRODUCED_IN" in q:
            label = "Class" if "Class" in q else "ApplicationProperty" if "ApplicationProperty" in q else "Dependency"
            version_key = f"{params['framework']}:{params['version']}"
            self.state.merge_edge(label, params["name"], "INTRODUCED_IN", "Version", version_key)
            self.state.merge_edge("Version", version_key, "INTRODUCES", label, params["name"])
            return FakeResult()
        if "DEPRECATED_IN" in q:
            label = "Class" if "Class" in q else "ApplicationProperty" if "ApplicationProperty" in q else "Dependency"
            version_key = f"{params['framework']}:{params['version']}"
            self.state.merge_edge(label, params["name"], "DEPRECATED_IN", "Version", version_key)
            self.state.merge_edge("Version", version_key, "DEPRECATES", label, params["name"])
            return FakeResult()
        if "AUTOMATED_BY" in q:
            step_key = f"{params['rule_id']}:{params['step_index']}"
            stub = params["stub_id"]
            self.state.merge_node("OpenRewriteRecipe", stub, {})
            self.state.merge_edge("MigrationStep", step_key, "AUTOMATED_BY", "OpenRewriteRecipe", stub)
            return FakeResult()
        if "SET v.rawMdPath" in q:
            return FakeResult()
        return FakeResult()


@pytest.fixture
def sample_batch() -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            MigrationEntity(
                source_section="breaking_change",
                title="Remove legacy API",
                change_type="breaking_change",
                reason="Legacy API removed in target version.",
                scopes=[
                    BreakingScopeInput(scope=ScopeLevel.API_SURFACE, severity=Severity.HIGH)
                ],
                entities=[
                    AffectedEntity(
                        kind=EntityKind.CLASS,
                        name="com.example.LegacyApi",
                        role=EntityRole.REMOVED,
                    ),
                    AffectedEntity(
                        kind=EntityKind.CLASS,
                        name="com.example.NewApi",
                        role=EntityRole.REPLACEMENT,
                    ),
                ],
                steps=[
                    MigrationStep(
                        index=0,
                        step_type=StepType.REMOVE,
                        summary="Remove legacy import",
                        instruction="Delete imports of com.example.LegacyApi.",
                        effort=Effort.MECHANICAL,
                        automatable=True,
                        requires=[],
                        verification="Project compiles without LegacyApi.",
                    )
                ],
            )
        ]
    )


def _count_nodes(state: GraphState, label: str) -> int:
    return sum(1 for node_label, _ in state.nodes if node_label == label)


def _count_edges(state: GraphState, rel: str) -> int:
    return sum(1 for edge in state.edges if edge[2] == rel)


def test_populator_is_idempotent(sample_batch: MigrationEntitiesBatch, monkeypatch: pytest.MonkeyPatch) -> None:
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
    monkeypatch.setattr(populator.pipeline_queries, "upsert_version_artifact_paths", lambda **_kwargs: None)
    monkeypatch.setattr(populator.pipeline_queries, "merge_version", lambda **_kwargs: None)

    kwargs = dict(
        batch=sample_batch,
        framework_display="Stub Framework",
        to_version="2.0.0",
        raw_md_path="runs/raw/x.md",
        filtered_md_path="runs/nodes/x.md",
        entities_json_path="runs/json/x.json",
        skip_if_version_exists=False,
    )
    populator.populate_graph(**kwargs)
    first_nodes = dict(state.nodes)
    first_edges = set(state.edges)

    populator.populate_graph(**kwargs)
    assert state.nodes == first_nodes
    assert state.edges == first_edges

    assert _count_nodes(state, "MigrationRule") == 1
    assert _count_nodes(state, "MigrationStep") == 1
    assert _count_nodes(state, "BreakingScope") == 1
    assert _count_nodes(state, "Class") == 2
    assert _count_edges(state, "REQUIRES_STEP") == 1
    assert _count_edges(state, "REPLACED_BY") == 1
    assert _count_edges(state, "REMOVED_IN") == 1
    assert _count_edges(state, "INTRODUCED_IN") == 1

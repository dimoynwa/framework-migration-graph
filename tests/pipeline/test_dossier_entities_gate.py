"""AC-1: the action gate and the reasons written to the cluster artifact."""

from __future__ import annotations

import json
from pathlib import Path

from migration_oracle.pipeline.entities.gate import decide
from migration_oracle.pipeline.entities.run import run_dossier_entities
from migration_oracle.pipeline.research.schema import ResearchDossier

PROTECTED = frozenset({"breaking", "deprecation", "security"})

TABLE = """\
| Type | Confidence | Source | Statement | Category | Impact score |
| --- | --- | --- | --- | --- | --- |
| fix | inferred | https://github.com/angular/angular/pull/1 | Title: Internal fix | internal_fix | 0.1 |
| breaking | confirmed | https://github.com/angular/angular/pull/2 | Title: Remove API | breaking | 2.0 |
| fix | inferred | https://github.com/angular/angular/pull/3 | Title: Unclear change | noise | 0.2 |
| fix | inferred | https://github.com/angular/angular/pull/4 | Title: Missing action | noise | 0.2 |
| fix | inferred | https://github.com/angular/angular/pull/5 | Title: Not found | noise | 0.2 |
"""


def _dossier(text: str, status: str = "ok") -> ResearchDossier:
    return ResearchDossier(row_key="k", status=status, text=text, sources=[])


def test_gate_decisions() -> None:
    assert decide(_dossier("**Action:** none"), "internal_fix", PROTECTED)[:2] == (
        "drop",
        "research_none",
    )
    assert decide(_dossier("**Action:** none"), "breaking", PROTECTED)[:2] == (
        "keep",
        "protected_none",
    )
    assert decide(_dossier("**Action:** unclear from the sources"), "noise", PROTECTED)[0] == "keep"
    assert decide(_dossier("**What changed:** something"), "noise", PROTECTED)[1] == "action_missing"
    decision, reason, evidence = decide(
        _dossier("", status="not_found"), "noise", PROTECTED
    )
    assert (decision, reason, evidence) == ("keep", "dossier_not_found", "row_only")
    assert decide(None, "breaking", PROTECTED)[2] == "row_only"
    assert decide(_dossier("**Action:** none"), "behavior_change", PROTECTED)[0] == "drop"
    assert decide(_dossier("**Action:** none"), "", PROTECTED) == (
        "keep",
        "action_none",
        "dossier",
    )


def test_removing_a_protected_category_drops_that_none() -> None:
    only_breaking = frozenset({"breaking"})
    assert decide(_dossier("**Action:** none"), "deprecation", only_breaking)[0] == "drop"
    assert decide(_dossier("**Action:** none"), "breaking", only_breaking)[0] == "keep"


def test_decisions_are_written_with_reasons(tmp_path: Path) -> None:
    dossiers = [
        _dossier("**Action:** none"),
        _dossier("**Action:** none"),
        _dossier("**Action:** unclear from the sources"),
        _dossier("**What changed:** a fact without an action line"),
        _dossier("", status="not_found"),
    ]

    def forbid(_prompt: str) -> str:
        raise AssertionError("stop-after-clusters must not call the entity model")

    jsonl = tmp_path / "clusters.jsonl"
    run_dossier_entities(
        filter_md=TABLE,
        dossiers=dossiers,
        framework_key="angular",
        framework_display="Angular",
        hop=("19.0.0", "20.0.0"),
        filtered_path=tmp_path / "filtered.md",
        json_path=tmp_path / "entities.json",
        stop_after_clusters=True,
        complete=forbid,
        clusters_jsonl=jsonl,
        clusters_summary=tmp_path / "summary.json",
    )
    rows = [
        json.loads(line)
        for line in jsonl.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["type"] == "row"
    ]
    assert [(row["decision"], row["reason"], row["evidence"]) for row in rows] == [
        ("drop", "research_none", "dossier"),
        ("keep", "protected_none", "dossier"),
        ("keep", "action_unclear", "dossier"),
        ("keep", "action_missing", "dossier"),
        ("keep", "dossier_not_found", "row_only"),
    ]
    assert rows[0]["cluster_key"] is None
    assert rows[1]["cluster_key"]
    assert not (tmp_path / "entities.json").exists()

"""AC-3, AC-4, AC-5: one call per cluster, title uniqueness, and the entity cache."""

from __future__ import annotations

import json
from pathlib import Path

from migration_oracle.pipeline.entities.prompt import render_prompt
from migration_oracle.pipeline.entities.run import run_dossier_entities
from migration_oracle.pipeline.research.schema import ResearchDossier
from migration_oracle.pipeline.triage.settings import load_settings as load_triage

TABLE = """\
| Type | Confidence | Source | Statement | Category | Impact score |
| --- | --- | --- | --- | --- | --- |
| breaking | confirmed | https://github.com/angular/angular/pull/1 | Title: Alpha change | breaking | 2 |
| breaking | confirmed | https://github.com/angular/angular/pull/2 | Title: Beta change | breaking | 2 |
"""

SAME_TITLE = """\
| Type | Confidence | Source | Statement | Category | Impact score |
| --- | --- | --- | --- | --- | --- |
| breaking | confirmed | https://github.com/angular/angular/pull/1 | Title: Remove Renderer | breaking | 2 |
| breaking | confirmed | https://github.com/angular/angular/pull/2 | Title: Remove Renderer | breaking | 2 |
"""


def _dossier(text: str, source: str) -> ResearchDossier:
    return ResearchDossier(row_key="k", status="ok", text=text, sources=[source])


def _entity(title: str) -> dict:
    return {
        "source_section": "breaking_change",
        "title": title,
        "change_type": "breaking_change",
        "reason": f"{title} was removed. Update callers.",
        "scopes": [{"scope": "api-surface", "severity": "high"}],
    }


def _one(title: str) -> str:
    return json.dumps({"entities": [_entity(title)]})


def _two() -> str:
    return json.dumps({"entities": [_entity("Alpha change"), _entity("Extra")]})


def _run(tmp_path: Path, table: str, dossiers: list[ResearchDossier], complete):
    return run_dossier_entities(
        filter_md=table,
        dossiers=dossiers,
        framework_key="angular",
        framework_display="Angular",
        hop=("19.0.0", "20.0.0"),
        filtered_path=tmp_path / "filtered.md",
        json_path=tmp_path / "entities.json",
        complete=complete,
        clusters_jsonl=tmp_path / "clusters.jsonl",
        clusters_summary=tmp_path / "summary.json",
    )


def test_two_entities_are_retried_once_and_the_other_cluster_is_kept(tmp_path: Path) -> None:
    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        if "Alpha change" in prompt:
            return _two()
        return _one("Beta change")

    result = _run(
        tmp_path,
        TABLE,
        [
            _dossier("**Action:** required\n\n**What changed:** Alpha change", "https://github.com/angular/angular/pull/1"),
            _dossier("**Action:** required\n\n**What changed:** Beta change", "https://github.com/angular/angular/pull/2"),
        ],
        complete,
    )
    alpha_calls = [prompt for prompt in calls if "Alpha change" in prompt]
    beta_calls = [prompt for prompt in calls if "Beta change" in prompt]
    assert len(alpha_calls) == 2
    assert len(beta_calls) == 1
    assert [entity.title for entity in result.batch.entities] == ["Beta change"]
    clusters = [
        json.loads(line)
        for line in (tmp_path / "clusters.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["type"] == "cluster"
    ]
    statuses = {cluster["title"]: cluster["status"] for cluster in clusters}
    assert statuses[None] == "error" or any(cluster["status"] == "error" for cluster in clusters)
    assert any(cluster["status"] == "ok" and cluster["title"] == "Beta change" for cluster in clusters)
    assert "Beta change" in (tmp_path / "entities.json").read_text(encoding="utf-8")
    assert "Alpha change" not in (tmp_path / "entities.json").read_text(encoding="utf-8")


def test_duplicate_titles_get_distinct_rule_ids(tmp_path: Path, capsys) -> None:
    def complete(prompt: str) -> str:
        return _one("Remove Renderer")

    result = _run(
        tmp_path,
        SAME_TITLE,
        [_dossier("**Action:** required", "https://github.com/angular/angular/pull/1"), _dossier("**Action:** required", "https://github.com/angular/angular/pull/2")],
        complete,
    )
    titles = [entity.title for entity in result.batch.entities]
    assert titles[0] == "Remove Renderer"
    assert titles[1].startswith("Remove Renderer (")
    assert titles[0] != titles[1]
    rule_ids = [f"pipeline://Angular/20.0.0/{title}" for title in titles]
    assert len(set(rule_ids)) == 2
    assert "renamed duplicate entity title" in capsys.readouterr().err
    rendered = (tmp_path / "filtered.md").read_text(encoding="utf-8")
    assert "Summary by Priority" not in rendered
    assert titles[1] in rendered
    assert "https://github.com/angular/angular/pull/1" in rendered


def test_second_run_makes_no_calls_until_one_dossier_changes(tmp_path: Path) -> None:
    calls: list[str] = []
    dossiers = [
        _dossier("**Action:** required\n\n**What changed:** first", "https://github.com/angular/angular/pull/1"),
        _dossier("**Action:** required\n\n**What changed:** second", "https://github.com/angular/angular/pull/2"),
    ]

    def complete(prompt: str) -> str:
        calls.append(prompt)
        if "NEW FACT" in prompt:
            return _one("Updated title")
        if "first" in prompt:
            return _one("First change")
        return _one("Second change")

    _run(tmp_path, TABLE, dossiers, complete)
    assert len(calls) == 2
    _run(tmp_path, TABLE, dossiers, complete)
    assert len(calls) == 2

    dossiers[0].text += "\nNEW FACT"
    _run(tmp_path, TABLE, dossiers, complete)
    assert len(calls) == 3
    entities = (tmp_path / "entities.json").read_text(encoding="utf-8")
    filtered = (tmp_path / "filtered.md").read_text(encoding="utf-8")
    assert "Updated title" in entities
    assert "Updated title" in filtered
    assert "Second change" in entities


def test_prompt_keeps_the_dossier_rules() -> None:
    angular = render_prompt("Angular", "ROW TEXT")
    assert "All rows below are one change. Produce at most one entity." in angular
    assert "**Before/after:**" in angular
    assert '{"entities": []}' in angular
    assert "No research is available" in angular
    assert '→ "breaking_change"' in angular
    assert "ROW TEXT" in angular
    assert "undertow" not in angular
    assert "undertow" in render_prompt("WildFly", "rows")


def test_triage_drop_threshold_defaults_to_0_20() -> None:
    assert load_triage().drop_max_action_prob == 0.20

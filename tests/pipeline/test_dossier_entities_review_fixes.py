"""Review fixes for 024: mode switch, partial failures, URL variants, cache key, input layout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import migration_oracle.config as config
import migration_oracle.pipeline.research.run as research_run
from migration_oracle.cli import export_extract_populate_framework
from migration_oracle.pipeline._cache import CacheFlags
from migration_oracle.pipeline._paths import default_entities_json_path, default_raw_md_path
from migration_oracle.pipeline.entities.clusters import Cluster, cluster_kept, specific_key
from migration_oracle.pipeline.entities.gate import load_input_rows
from migration_oracle.pipeline.entities.prompt import render_cluster_input
from migration_oracle.pipeline.entities.run import run_dossier_entities
from migration_oracle.pipeline.filters import (
    filter_input_digest_path,
    refresh_flags_for_filter_input,
)
from migration_oracle.pipeline.research.agent import ModelTurn, ToolCall
from migration_oracle.pipeline.research.schema import ResearchDossier

from tests.pipeline.test_dossier_entities_clusters import COMMIT, PULL, _member

TABLE = """\
| Type | Confidence | Source | Statement | Category | Impact score |
| --- | --- | --- | --- | --- | --- |
| breaking | confirmed | https://github.com/angular/angular/pull/1 | Title: Alpha change | breaking | 2 |
| breaking | confirmed | https://github.com/angular/angular/pull/2 | Title: Beta change | breaking | 2 |
"""


def _dossiers() -> list[ResearchDossier]:
    return [
        ResearchDossier(
            row_key="k",
            status="ok",
            text="**What changed:** Alpha\n**Action:** required",
            sources=["https://github.com/angular/angular/pull/1"],
        ),
        ResearchDossier(
            row_key="k",
            status="ok",
            text="**What changed:** Beta\n**Action:** required",
            sources=["https://github.com/angular/angular/pull/2"],
        ),
    ]


def _entity(title: str) -> str:
    return json.dumps(
        {
            "entities": [
                {
                    "source_section": "breaking_change",
                    "title": title,
                    "change_type": "breaking_change",
                    "reason": f"{title}.",
                    "scopes": [{"scope": "api-surface", "severity": "high"}],
                }
            ]
        }
    )


def _run(tmp_path: Path, table: str, dossiers, complete):
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


# --- 1. dossier output must not pass for filter-LLM output ---------------------


def test_dossier_run_removes_the_filter_input_sidecar(tmp_path: Path) -> None:
    filtered = tmp_path / "filtered.md"
    filtered.write_text("old filter LLM document\n", encoding="utf-8")
    sidecar = filter_input_digest_path(filtered)
    sidecar.write_text("digest-of-the-same-filter-input\n", encoding="utf-8")

    _run(tmp_path, TABLE, _dossiers(), lambda prompt: _entity("Alpha" if "Alpha" in prompt else "Beta"))

    assert "Entity source:** dossier" in filtered.read_text(encoding="utf-8")
    assert not sidecar.exists()
    cached = CacheFlags(
        skip_extraction=True,
        skip_filter_llm=True,
        skip_entity_llm=True,
        raw_was_cached=True,
        stale_filtered_warning=False,
        stale_json_warning=False,
    )
    flags = refresh_flags_for_filter_input(cached, TABLE, filtered)
    assert flags.skip_filter_llm is False
    assert flags.skip_entity_llm is False


# --- 2. a hop with failed clusters is not populated ----------------------------


def test_failed_clusters_are_reported_on_the_result(tmp_path: Path) -> None:
    def complete(prompt: str) -> str:
        if "Alpha" in prompt:
            raise RuntimeError("model down")
        return _entity("Beta")

    result = _run(tmp_path, TABLE, _dossiers(), complete)
    assert result.failed_clusters == 1
    assert [entity.title for entity in result.batch.entities] == ["Beta"]


RAW = """\
# Stub Framework — documented changes (extract-only)

- **Framework key:** `stub_framework`
- **Resolved range:** `1.0.0` → `2.0.0`

---

## `1.0.0` → `2.0.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| breaking | confirmed | https://example.com/a | Remove LegacyClient |
| breaking | confirmed | https://example.com/b | Rename OtherClient |
"""


class _ScriptedModel:
    async def complete(self, messages, *, tools, response_format):
        if not any(message.get("role") == "tool" for message in messages):
            return ModelTurn(
                tool_calls=[ToolCall("f", "fetch_url", {"url": "https://example.com/a"})]
            )
        return ModelTurn(content="**What changed:** a client changed.\n**Action:** required")


class _Fetcher:
    def fetch(self, url: str):
        from migration_oracle.pipeline.research.tools import ToolOutput

        return ToolOutput(text=f"Page {url}", fetched_url=url)


def test_partial_failure_skips_population_and_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_ID", "fake-entity-model")
    monkeypatch.setattr(config, "MODEL_PROVIDER", "openai")
    raw = default_raw_md_path("stub_framework", "1.0.0", "2.0.0")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(RAW, encoding="utf-8")

    def complete(prompt: str) -> str:
        if "LegacyClient" in prompt:
            raise RuntimeError("model down")
        return _entity("Rename OtherClient")

    def forbid(*_args, **_kwargs):
        raise AssertionError("a hop with failed clusters must not be populated")

    monkeypatch.setattr("migration_oracle.pipeline.entities.run._default_complete", complete)
    monkeypatch.setattr("migration_oracle.cli.populate_graph", forbid)
    monkeypatch.setattr(research_run, "build_model", lambda _settings: _ScriptedModel())
    monkeypatch.setattr(research_run, "build_fetcher", lambda _settings, force=False: _Fetcher())
    result = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--skip-triage"],
        env={
            "RESEARCH_BASE_URL": "http://research.example/v1",
            "RESEARCH_MODEL_ID": "fake-model",
        },
    )
    assert result.exit_code == 3, result.output
    assert "graph not populated" in result.output
    entities = default_entities_json_path("stub_framework", "1.0.0", "2.0.0")
    assert "Rename OtherClient" in entities.read_text(encoding="utf-8")


# --- 3. GitHub URL variants meet the plain URL ---------------------------------


@pytest.mark.parametrize(
    ("variant", "plain"),
    [
        (COMMIT + ".patch", COMMIT),
        (COMMIT + ".diff", COMMIT),
        (PULL.format(n=7) + "/files", PULL.format(n=7)),
        (PULL.format(n=7) + ".diff", PULL.format(n=7)),
        (PULL.format(n=7) + "/commits/abcdef1234567890", PULL.format(n=7)),
        ("https://patch-diff.githubusercontent.com/raw/angular/angular/pull/7.diff", PULL.format(n=7)),
        ("https://github.com/Angular/Angular/issues/9#issuecomment-1", "https://github.com/angular/angular/issues/9"),
    ],
)
def test_github_variants_share_a_key(variant: str, plain: str) -> None:
    assert specific_key(variant) == specific_key(plain)


def test_fetched_patch_url_joins_the_commit_row() -> None:
    rows = [
        _member("commit row", [COMMIT], position=0),
        _member("changelog row", ["https://example.com/notes"], position=1, dossier_sources=[COMMIT + ".patch"]),
    ]
    clusters = cluster_kept(rows, max_rows=4)
    assert len(clusters) == 1
    assert len(clusters[0].members) == 2


# --- 4. the cache follows everything the prompt sends --------------------------


def test_changed_category_re_runs_the_cluster(tmp_path: Path) -> None:
    calls: list[str] = []

    def complete(prompt: str) -> str:
        calls.append(prompt)
        return _entity("Alpha" if "Alpha" in prompt else "Beta")

    _run(tmp_path, TABLE, _dossiers(), complete)
    assert len(calls) == 2
    _run(tmp_path, TABLE, _dossiers(), complete)
    assert len(calls) == 2

    retriaged = TABLE.replace("Title: Alpha change | breaking |", "Title: Alpha change | deprecation |")
    _run(tmp_path, retriaged, _dossiers(), complete)
    assert len(calls) == 3
    assert "Triage: deprecation" in calls[-1]


# --- 7. the triage line belongs to its row --------------------------------------


def test_triage_line_follows_the_row_heading() -> None:
    rows = load_input_rows(TABLE, _dossiers(), protected=frozenset({"breaking"}))
    text = render_cluster_input(Cluster(tuple(rows)), "Angular", ("19.0.0", "20.0.0"))
    lines = text.splitlines()
    first = lines.index("## Row 1")
    second = lines.index("## Row 2")
    assert lines[first + 1].startswith("Triage: breaking")
    assert lines[second + 1].startswith("Triage: breaking")
    assert not any(line.startswith("Triage:") for line in lines[:first])


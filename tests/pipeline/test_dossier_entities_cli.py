"""AC-6: mode selection, stop-after-clusters, and the filter path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import migration_oracle.config as config
import migration_oracle.pipeline.research.run as research_run
from migration_oracle.cli import export_extract_populate_framework
from migration_oracle.pipeline._paths import (
    default_clusters_jsonl_path,
    default_entities_json_path,
    default_filtered_md_path,
    default_raw_md_path,
)
from migration_oracle.pipeline.entities.settings import resolve_entity_source
from migration_oracle.pipeline.research.agent import ModelTurn, ToolCall

RAW = """\
# Stub Framework — documented changes (extract-only)

- **Framework key:** `stub_framework`
- **Resolved range:** `1.0.0` → `2.0.0`

---

## `1.0.0` → `2.0.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| breaking | confirmed | https://example.com/a | Remove LegacyClient |
"""


class _ScriptedModel:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, *, tools, response_format):
        self.calls += 1
        if not any(message.get("role") == "tool" for message in messages):
            return ModelTurn(tool_calls=[ToolCall("f", "fetch_url", {"url": "https://example.com/a"})])
        return ModelTurn(
            content="**What changed:** LegacyClient was removed.\n**Action:** required"
        )


class _Fetcher:
    def fetch(self, url: str):
        from migration_oracle.pipeline.research.tools import ToolOutput

        return ToolOutput(text=f"Page {url}", fetched_url=url)


def test_resolve_entity_source(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_entity_source(None, skip_research=False, research_enabled=True) == "dossier"
    assert resolve_entity_source(None, skip_research=False, research_enabled=False) == "filter"
    assert resolve_entity_source(None, skip_research=True, research_enabled=True) == "filter"
    assert resolve_entity_source("filter", skip_research=False, research_enabled=True) == "filter"
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_entity_source("dossier", skip_research=True, research_enabled=True)
    monkeypatch.setenv("ENTITY_SOURCE", "filter")
    assert resolve_entity_source(None, skip_research=False, research_enabled=True) == "filter"
    monkeypatch.setenv("ENTITY_SOURCE", "dossier")
    assert resolve_entity_source("filter", skip_research=False, research_enabled=True) == "filter"


def test_dossier_with_skip_research_is_a_usage_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--entity-source",
            "dossier",
            "--skip-research",
        ],
    )
    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_stop_after_clusters_needs_no_main_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_ID", "")
    monkeypatch.setattr(config, "MODEL_PROVIDER", "")
    raw = default_raw_md_path("stub_framework", "1.0.0", "2.0.0")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(RAW, encoding="utf-8")

    def forbid(*_args, **_kwargs):
        raise AssertionError("entity and filter LLMs must not run")

    monkeypatch.setattr("migration_oracle.pipeline.filters._invoke_filter", forbid)
    monkeypatch.setattr("migration_oracle.pipeline.extractor._invoke_structured", forbid)
    monkeypatch.setattr("migration_oracle.pipeline.entities.run.get_llm", forbid)
    monkeypatch.setattr("migration_oracle.cli.populate_graph", forbid)
    model = _ScriptedModel()
    monkeypatch.setattr(research_run, "build_model", lambda _settings: model)
    monkeypatch.setattr(research_run, "build_fetcher", lambda _settings, force=False: _Fetcher())
    result = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--skip-triage", "--stop-after-clusters"],
        env={
            "RESEARCH_BASE_URL": "http://research.example/v1",
            "RESEARCH_MODEL_ID": "fake-model",
            "MODEL_PROVIDER": "",
            "MODEL_ID": "",
        },
    )
    assert result.exit_code == 0, result.output
    assert "Stopped after clusters" in result.output
    jsonl = default_clusters_jsonl_path("stub_framework", "1.0.0", "2.0.0")
    assert jsonl.exists()
    records = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    assert any(record["type"] == "row" and record["decision"] == "keep" for record in records)
    assert any(record["type"] == "cluster" and record["status"] == "skipped" for record in records)
    assert not default_entities_json_path("stub_framework", "1.0.0", "2.0.0").exists()
    assert not default_filtered_md_path("stub_framework", "1.0.0", "2.0.0").exists()
    assert model.calls >= 1

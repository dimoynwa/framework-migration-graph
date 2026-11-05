"""CLI wiring for research. Search is a fake; Tavily is never contacted."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

import migration_oracle.config as config
import migration_oracle.pipeline.research.run as research_run
from migration_oracle.cli import export_extract_populate_framework
from migration_oracle.models.entities import (
    BreakingScopeInput,
    MigrationEntitiesBatch,
    MigrationEntity,
    ScopeLevel,
    Severity,
)
from migration_oracle.pipeline._paths import (
    default_entities_json_path,
    default_filtered_md_path,
    default_raw_md_path,
    default_research_jsonl_path,
)
from migration_oracle.pipeline.research.agent import ChatCompletionsModel, ModelTurn, ToolCall
from migration_oracle.pipeline.research.settings import (
    completions_url,
    load_settings,
    normalize_base_url,
)
from migration_oracle.pipeline.research.tools import SearchHit, TavilyQuotaError, ToolOutput

RAW = """\
# Stub Framework — documented changes (extract-only)

- **Framework key:** `stub_framework`
- **Resolved range:** `1.0.0` → `2.0.0`

---

## `1.0.0` → `2.0.0`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| breaking | confirmed | https://example.com/a | Remove LegacyClient |
| behavioral | inferred | https://example.com/b | Rename timeout |
| behavioral | inferred | https://example.com/c | Drop adapter |
"""

FILTERED = """\
## 🔴 Breaking Changes

| # | JIRA | Title | Impact | Sources |
| --- | --- | --- | --- | --- |
| 1 | N/A | Remove LegacyClient | Remove LegacyClient. | https://example.com/a |
| 2 | N/A | Rename timeout | Rename the timeout property. | https://example.com/b |
| 3 | N/A | Drop adapter | Drop the adapter class. | https://example.com/c |
"""


class FakeSearch:
    def __init__(self, *, fail_on: int | None = None) -> None:
        self.queries: list[str] = []
        self.fail_on = fail_on

    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        self.queries.append(query)
        if self.fail_on is not None and len(self.queries) == self.fail_on:
            raise TavilyQuotaError(432)
        return [SearchHit("Guide", "https://example.com/guide", "note")]


class FakeFetcher:
    def fetch(self, url: str) -> ToolOutput:
        return ToolOutput(text=f"Page {url} mentions the class.", fetched_url=url)


class ScriptedModel:
    """Search, fetch the row Source, then write the description."""

    def __init__(self) -> None:
        self.final_calls = 0

    async def complete(self, messages, *, tools, response_format):
        tool_messages = [message for message in messages if message["role"] == "tool"]
        title = "change"
        source = "https://example.com/a"
        for message in messages:
            if message.get("role") != "user":
                continue
            for line in message["content"].splitlines():
                if line.startswith("Title: "):
                    title = line.split("Title: ", 1)[1].strip()
                if line.startswith("Sources: "):
                    source = line.split("Sources: ", 1)[1].strip()
        if not tool_messages:
            return ModelTurn(tool_calls=[ToolCall("s", "web_search", {"query": title})])
        if len(tool_messages) == 1:
            return ModelTurn(tool_calls=[ToolCall("f", "fetch_url", {"url": source})])
        self.final_calls += 1
        return ModelTurn(
            content=(
                f"{title} changed: `com.example.LegacyClient` was removed. "
                f"Applications that import it must change ({source})."
            )
        )


def _batch() -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            MigrationEntity(
                source_section="breaking_change",
                title="Remove LegacyClient",
                change_type="breaking_change",
                reason="Removed.",
                scopes=[BreakingScopeInput(scope=ScopeLevel.API_SURFACE, severity=Severity.HIGH)],
            )
        ]
    )


def _seed(tmp_path: Path) -> None:
    raw = default_raw_md_path("stub_framework", "1.0.0", "2.0.0")
    filtered = default_filtered_md_path("stub_framework", "1.0.0", "2.0.0")
    raw.parent.mkdir(parents=True, exist_ok=True)
    filtered.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(RAW, encoding="utf-8")
    filtered.write_text(FILTERED, encoding="utf-8")


def test_base_url_with_and_without_method_path_match(caplog: pytest.LogCaptureFixture, monkeypatch) -> None:
    monkeypatch.setenv("RESEARCH_BASE_URL", "http://host:8010/v1/chat/completions")
    monkeypatch.setenv("RESEARCH_MODEL_ID", "fake")
    monkeypatch.setenv("TAVILY_API_KEY", "not-a-real-key")
    caplog.set_level("DEBUG", logger="migration_oracle.pipeline.research")
    first = load_settings()
    second = load_settings()
    plain = normalize_base_url("http://host:8010/v1")
    assert first.base_url == plain
    assert completions_url(first.base_url) == completions_url("http://host:8010/v1")
    assert completions_url("http://host:8010/v1/chat/completions/") == completions_url(plain)
    trimmed = [record for record in caplog.records if "trimmed" in record.message]
    assert len(trimmed) == 1
    assert second.completions_url == first.completions_url


@pytest.mark.asyncio
async def test_chat_client_posts_the_normalized_completions_url(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert "authorization" not in {key.lower() for key in request.headers}
        body = json.loads(request.content)
        assert body["stream"] is False
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "{}"}}]},
        )

    from migration_oracle.pipeline.research.settings import ResearchSettings

    settings = ResearchSettings(
        base_url="http://host:8010/v1/chat/completions",
        model_id="fake-model",
        api_key="",
        tavily_api_key="not-a-real-key",
        enable_thinking=False,
        max_concurrent=1,
        max_tool_calls=6,
        timeout_sec=5,
        search_results=5,
        fetch_max_chars=100,
        entity_max_input_tokens=60000,
        cache_dir=tmp_path,
    )
    model = ChatCompletionsModel(settings, transport=httpx.MockTransport(handler))
    await model.complete(
        [{"role": "user", "content": "hi"}],
        tools=None,
        response_format=None,
    )
    assert seen == ["http://host:8010/v1/chat/completions"]


def test_quota_stops_the_hop_and_rerun_researches_only_uncached_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_PROVIDER", "openai")
    _seed(tmp_path)
    earlier_jsonl = tmp_path / "runs" / "research" / "stub_framework-0.1.0-to-1.0.0-research.jsonl"
    earlier_entities = tmp_path / "runs" / "json" / "stub_framework-0.1.0-to-1.0.0-entities.json"
    earlier_jsonl.parent.mkdir(parents=True, exist_ok=True)
    earlier_entities.parent.mkdir(parents=True, exist_ok=True)
    earlier_jsonl.write_text("earlier-hop\n", encoding="utf-8")
    earlier_entities.write_text('{"entities": []}\n', encoding="utf-8")

    holder = {"search": FakeSearch(fail_on=3), "model": ScriptedModel()}
    invoked: list[str] = []

    def fake_invoke(document: str, framework: str) -> MigrationEntitiesBatch:
        invoked.append(document)
        return _batch()

    monkeypatch.setattr("migration_oracle.pipeline.extractor._invoke_structured", fake_invoke)
    monkeypatch.setattr(research_run, "build_model", lambda _settings: holder["model"])
    monkeypatch.setattr(research_run, "build_search", lambda _settings: holder["search"])
    monkeypatch.setattr(research_run, "build_fetcher", lambda _settings, force=False: FakeFetcher())

    def forbid_tavily(*_args, **_kwargs):
        raise AssertionError("Tavily must not be called from tests")

    monkeypatch.setattr(
        "migration_oracle.pipeline.research.tools.TavilySearchClient.search",
        forbid_tavily,
    )

    env = {
        "RESEARCH_BASE_URL": "http://research.example/v1",
        "RESEARCH_MODEL_ID": "fake-model",
        "TAVILY_API_KEY": "not-a-real-key",
        "RESEARCH_MAX_CONCURRENT": "1",
        "MODEL_PROVIDER": "openai",
    }
    failed = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--dry-run", "--skip-triage"],
        env=env,
    )
    assert failed.exit_code == 2, failed.output
    assert (
        "Tavily quota exhausted at stub_framework 1.0.0→2.0.0 "
        "(2/3 rows researched). Re-run after the quota resets; finished rows are cached."
        in failed.output
    )
    assert not default_research_jsonl_path("stub_framework", "1.0.0", "2.0.0").exists()
    assert not default_entities_json_path("stub_framework", "1.0.0", "2.0.0").exists()
    assert earlier_jsonl.read_text(encoding="utf-8") == "earlier-hop\n"
    assert earlier_entities.read_text(encoding="utf-8") == '{"entities": []}\n'
    assert invoked == []

    holder["search"] = FakeSearch()
    resumed = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--dry-run", "--skip-triage"],
        env=env,
    )
    assert resumed.exit_code == 0, resumed.output
    assert holder["search"].queries
    assert len(holder["search"].queries) == 1
    assert default_research_jsonl_path("stub_framework", "1.0.0", "2.0.0").exists()
    assert default_entities_json_path("stub_framework", "1.0.0", "2.0.0").exists()
    assert invoked


def test_skip_research_keeps_the_entity_input_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_PROVIDER", "openai")
    _seed(tmp_path)
    seen: list[str] = []

    def fake_invoke(document: str, framework: str) -> MigrationEntitiesBatch:
        seen.append(document)
        return _batch()

    def forbid_model(*_args, **_kwargs):
        raise AssertionError("research model should not be built")

    monkeypatch.setattr("migration_oracle.pipeline.extractor._invoke_structured", fake_invoke)
    monkeypatch.setattr(research_run, "build_model", forbid_model)
    monkeypatch.setattr(research_run, "build_search", forbid_model)
    result = CliRunner().invoke(
        export_extract_populate_framework,
        [
            "--framework",
            "stub_framework",
            "1.0.0",
            "2.0.0",
            "--dry-run",
            "--skip-triage",
            "--skip-research",
        ],
        env={
            "RESEARCH_BASE_URL": "http://research.example/v1",
            "RESEARCH_MODEL_ID": "fake-model",
            "TAVILY_API_KEY": "not-a-real-key",
            "MODEL_PROVIDER": "openai",
        },
    )
    assert result.exit_code == 0, result.output
    assert seen == [FILTERED]
    assert not default_research_jsonl_path("stub_framework", "1.0.0", "2.0.0").exists()


def test_stop_after_research_writes_dossiers_and_skips_entities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_PROVIDER", "openai")
    _seed(tmp_path)

    def forbid_entities(*_args, **_kwargs):
        raise AssertionError("entity LLM must not run with --stop-after-research")

    monkeypatch.setattr("migration_oracle.pipeline.extractor._invoke_structured", forbid_entities)
    monkeypatch.setattr("migration_oracle.cli.populate_graph", forbid_entities)
    monkeypatch.setattr(research_run, "build_model", lambda _settings: ScriptedModel())
    monkeypatch.setattr(research_run, "build_search", lambda _settings: FakeSearch())
    monkeypatch.setattr(research_run, "build_fetcher", lambda _settings, force=False: FakeFetcher())
    env = {
        "RESEARCH_BASE_URL": "http://research.example/v1",
        "RESEARCH_MODEL_ID": "fake-model",
        "TAVILY_API_KEY": "not-a-real-key",
        "MODEL_PROVIDER": "openai",
    }
    result = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--skip-triage", "--stop-after-research"],
        env=env,
    )
    assert result.exit_code == 0, result.output
    assert "Stopped after research" in result.output
    assert default_research_jsonl_path("stub_framework", "1.0.0", "2.0.0").exists()
    assert not default_entities_json_path("stub_framework", "1.0.0", "2.0.0").exists()


def test_stop_after_research_requires_research_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("RESEARCH_BASE_URL", "RESEARCH_MODEL_ID", "TAVILY_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--stop-after-research"],
    )
    assert result.exit_code != 0
    assert "needs research enabled" in result.output


def test_missing_model_id_fails_with_a_clear_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_ID", "")
    _seed(tmp_path)
    result = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--dry-run", "--skip-triage", "--skip-research"],
    )
    assert result.exit_code != 0
    assert "MODEL_ID is not set" in result.output


def test_stop_after_research_needs_no_main_model_and_writes_no_filtered_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_ID", "")
    _seed(tmp_path)
    filtered = default_filtered_md_path("stub_framework", "1.0.0", "2.0.0")
    filtered.unlink()

    def forbid_llm(*_args, **_kwargs):
        raise AssertionError("no main LLM call expected")

    monkeypatch.setattr("migration_oracle.pipeline.filters._invoke_filter", forbid_llm)
    monkeypatch.setattr("migration_oracle.pipeline.extractor._invoke_structured", forbid_llm)
    model = ScriptedModel()
    monkeypatch.setattr(research_run, "build_model", lambda _settings: model)
    monkeypatch.setattr(research_run, "build_search", lambda _settings: FakeSearch())
    monkeypatch.setattr(research_run, "build_fetcher", lambda _settings, force=False: FakeFetcher())
    result = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--skip-triage", "--stop-after-research"],
        env={
            "RESEARCH_BASE_URL": "http://research.example/v1",
            "RESEARCH_MODEL_ID": "fake-model",
            "TAVILY_API_KEY": "not-a-real-key",
        },
    )
    assert result.exit_code == 0, result.output
    assert not filtered.exists()
    jsonl = default_research_jsonl_path("stub_framework", "1.0.0", "2.0.0")
    assert len(jsonl.read_text(encoding="utf-8").splitlines()) == 3  # one per kept raw row
    assert model.final_calls == 3


def test_research_runs_before_the_filter_llm_and_feeds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "MODEL_PROVIDER", "openai")
    _seed(tmp_path)
    default_filtered_md_path("stub_framework", "1.0.0", "2.0.0").unlink()
    filter_inputs: list[str] = []
    entity_inputs: list[str] = []

    def fake_filter(table: str, *, partial: bool = False) -> str:
        filter_inputs.append(table)
        return FILTERED

    def fake_entities(document: str, framework: str) -> MigrationEntitiesBatch:
        entity_inputs.append(document)
        return _batch()

    monkeypatch.setattr("migration_oracle.pipeline.filters._invoke_filter", fake_filter)
    monkeypatch.setattr("migration_oracle.pipeline.extractor._invoke_structured", fake_entities)
    monkeypatch.setattr(research_run, "build_model", lambda _settings: ScriptedModel())
    monkeypatch.setattr(research_run, "build_search", lambda _settings: FakeSearch())
    monkeypatch.setattr(research_run, "build_fetcher", lambda _settings, force=False: FakeFetcher())
    result = CliRunner().invoke(
        export_extract_populate_framework,
        ["--framework", "stub_framework", "1.0.0", "2.0.0", "--dry-run", "--skip-triage"],
        env={
            "RESEARCH_BASE_URL": "http://research.example/v1",
            "RESEARCH_MODEL_ID": "fake-model",
            "TAVILY_API_KEY": "not-a-real-key",
            "MODEL_PROVIDER": "openai",
        },
    )
    assert result.exit_code == 0, result.output
    # The filter LLM saw the kept rows and their research blocks.
    assert len(filter_inputs) == 1
    assert "## Research" in filter_inputs[0]
    assert "Row sources: https://example.com/a" in filter_inputs[0]
    assert "com.example.LegacyClient" in filter_inputs[0]
    # The entity LLM saw the document plus research merged per document row.
    assert len(entity_inputs) == 1
    assert "### 🔴 Breaking Changes #1 — Remove LegacyClient" in entity_inputs[0]
    assert "must change" in entity_inputs[0]

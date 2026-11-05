"""Agent citation checks, budgets, and the research cache. No Tavily calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_oracle.models.entities import (
    BreakingScopeInput,
    MigrationEntitiesBatch,
    MigrationEntity,
    ScopeLevel,
    Severity,
)
from migration_oracle.pipeline._cache import CacheFlags
from migration_oracle.pipeline._paths import (
    default_research_jsonl_path,
    default_research_summary_path,
)
from migration_oracle.pipeline.extractor import (
    refresh_flags_for_entity_input,
    run_extraction,
)
from migration_oracle.pipeline.research.agent import (
    ModelTurn,
    ToolCall,
    research_row,
)
from migration_oracle.pipeline.research.markdown import (
    build_extraction_input,
    parse_filtered_markdown,
)
from migration_oracle.pipeline.research.run import run_research
from migration_oracle.pipeline.research.schema import build_dossier
from migration_oracle.pipeline.research.settings import ResearchSettings
from migration_oracle.pipeline.research.tools import (
    SearchHit,
    SearchTool,
    TavilyQuotaError,
    ToolOutput,
)

FILTERED = """\
## 🔴 Breaking Changes

| # | JIRA | Title | Impact | Sources |
| --- | --- | --- | --- | --- |
| 1 | SB-1 | Remove LegacyClient | Remove LegacyClient. | https://example.com/a |
| 2 | SB-2 | Rename timeout | Rename the timeout property. | https://example.com/b |

## 🟡 Deprecations

| # | JIRA | Title | Impact | Sources |
| --- | --- | --- | --- | --- |
| 1 | SB-3 | Deprecate Adapter | Adapter is deprecated. | https://example.com/c |
"""

HOP = ("3.5.0", "3.5.1")


def _settings(tmp_path: Path, **overrides: object) -> ResearchSettings:
    values: dict[str, object] = {
        "base_url": "http://research.example/v1",
        "model_id": "fake-model",
        "api_key": "",
        "tavily_api_key": "not-a-real-key",
        "enable_thinking": False,
        "max_concurrent": 1,
        "max_tool_calls": 6,
        "timeout_sec": 5,
        "search_results": 5,
        "fetch_max_chars": 2000,
        "entity_max_input_tokens": 60000,
        "cache_dir": tmp_path / "artifacts",
    }
    values.update(overrides)
    return ResearchSettings(**values)  # type: ignore[arg-type]


class FakeSearch:
    def __init__(self, *, fail_on: int | None = None) -> None:
        self.queries: list[str] = []
        self.fail_on = fail_on

    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        self.queries.append(query)
        if self.fail_on is not None and len(self.queries) == self.fail_on:
            raise TavilyQuotaError(432)
        return [SearchHit("Guide", "https://example.com/guide", "LegacyClient removed")]


class FakeFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str) -> ToolOutput:
        self.urls.append(url)
        return ToolOutput(text=f"Page for {url} names LegacyClient.", fetched_url=url)


class ScriptedModel:
    """Search, fetch the row Source, then write the description."""

    def __init__(self, final_payload) -> None:
        self.calls = 0
        self.final_calls = 0
        self.final_payload = final_payload

    async def complete(self, messages, *, tools, response_format):
        self.calls += 1
        tool_messages = [message for message in messages if message["role"] == "tool"]
        source = _source(messages)
        title = _line(messages, "Title: ")
        if not tool_messages:
            return ModelTurn(tool_calls=[ToolCall("s", "web_search", {"query": title})])
        if len(tool_messages) == 1:
            return ModelTurn(tool_calls=[ToolCall("f", "fetch_url", {"url": source})])
        self.final_calls += 1
        payload = self.final_payload(messages) if callable(self.final_payload) else self.final_payload
        return ModelTurn(content=payload)


def _source(messages: list[dict]) -> str:
    return _line(messages, "Sources: ")


def _line(messages: list[dict], prefix: str) -> str:
    for message in messages:
        if message.get("role") != "user":
            continue
        for line in message["content"].splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :].strip()
    return "https://example.com/a"


def _ok_payload(messages: list[dict]) -> str:
    source = _source(messages)
    return (
        "`com.example.LegacyClient` was removed. Applications that import it must "
        f"switch to `com.example.Client` ({source})."
    )


def _bad_payload(messages: list[dict]) -> str:
    source = _source(messages)
    return (
        "`com.example.NotFetched` is gone, see [the guide](https://example.com/never-fetched) "
        "and https://example.com/also-never-fetched. "
        f"`com.example.LegacyClient` was removed ({source})."
    )


def _flags(*, skip_entity: bool) -> CacheFlags:
    return CacheFlags(
        skip_extraction=True,
        skip_filter_llm=True,
        skip_entity_llm=skip_entity,
        raw_was_cached=True,
        stale_filtered_warning=False,
        stale_json_warning=False,
    )


def _entity(title: str) -> MigrationEntitiesBatch:
    return MigrationEntitiesBatch(
        entities=[
            MigrationEntity(
                source_section="breaking_change",
                title=title,
                change_type="breaking_change",
                reason="Because the dossier said so.",
                scopes=[BreakingScopeInput(scope=ScopeLevel.API_SURFACE, severity=Severity.HIGH)],
            )
        ]
    )


@pytest.mark.asyncio
async def test_unfetched_urls_are_removed_from_the_description(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    row = parse_filtered_markdown(FILTERED)[0]
    search = SearchTool(
        FakeSearch(),
        cache_dir=settings.cache_dir,
        framework="Spring Boot",
        to_version="3.5.1",
        max_results=5,
    )
    dossier, _calls = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=settings,
        model=ScriptedModel(_bad_payload),
        search=search,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert dossier.status == "ok"
    assert "never-fetched" not in dossier.text
    assert "the guide" in dossier.text  # a Markdown link keeps its label
    assert "https://example.com/a" in dossier.text
    assert dossier.sources == ["https://example.com/a"]


def test_not_found_marker_empty_text_and_nothing_fetched_are_not_found() -> None:
    fetched = {"https://example.com/a"}
    assert build_dossier("NOT_FOUND", fetched_urls=fetched, row_key="k", model="m").status == "not_found"
    assert build_dossier("  ", fetched_urls=fetched, row_key="k", model="m").status == "not_found"
    from_memory = build_dossier("LegacyClient was removed.", fetched_urls=set(), row_key="k", model="m")
    assert from_memory.status == "not_found"
    assert from_memory.text == ""


def test_uncited_text_lists_every_fetched_page_and_drops_think_blocks() -> None:
    dossier = build_dossier(
        "<think>hmm</think>LegacyClient was removed.",
        fetched_urls={"https://example.com/b", "https://example.com/a/"},
        row_key="k",
        model="m",
    )
    assert dossier.status == "ok"
    assert dossier.text == "LegacyClient was removed."
    assert dossier.sources == ["https://example.com/a/", "https://example.com/b"]


def test_trailing_punctuation_and_slash_still_match_fetched_url() -> None:
    dossier = build_dossier(
        "See https://example.com/a/. Also [docs](https://example.com/b).",
        fetched_urls={"https://example.com/a", "https://example.com/b"},
        row_key="k",
        model="m",
    )
    assert dossier.text == "See https://example.com/a/. Also [docs](https://example.com/b)."
    assert dossier.sources == ["https://example.com/a", "https://example.com/b"]


@pytest.mark.asyncio
async def test_budget_timeout_and_invalid_json_are_errors(tmp_path: Path) -> None:
    row = parse_filtered_markdown(FILTERED)[0]
    search = SearchTool(
        FakeSearch(),
        cache_dir=tmp_path / "artifacts",
        framework="Spring Boot",
        to_version="3.5.1",
        max_results=5,
    )
    fetcher = FakeFetcher()

    class AlwaysSearch:
        async def complete(self, messages, *, tools, response_format):
            return ModelTurn(tool_calls=[ToolCall("s", "web_search", {"query": "again"})])

    budget, _used = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=_settings(tmp_path, max_tool_calls=1),
        model=AlwaysSearch(),
        search=search,
        fetcher=fetcher,  # type: ignore[arg-type]
    )
    # Budget used up, then the final description request returns no text.
    assert budget.status == "not_found"

    class Slow:
        async def complete(self, messages, *, tools, response_format):
            raise TimeoutError("row timed out")

    timed, _used = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=_settings(tmp_path),
        model=Slow(),
        search=search,
        fetcher=fetcher,  # type: ignore[arg-type]
    )
    assert timed.status == "error"
    assert timed.text == ""
    assert "TimeoutError: row timed out" in timed.error


def test_disabled_research_makes_no_calls_and_keeps_filtered_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    class Boom:
        async def complete(self, *args, **kwargs):
            raise AssertionError("model was called")

    rows = parse_filtered_markdown(FILTERED)
    dossiers = run_research(
        rows,
        "Spring Boot",
        HOP,
        framework_key="spring-boot",
        settings=_settings(tmp_path, base_url="", tavily_api_key=""),
        model=Boom(),  # type: ignore[arg-type]
        search=FakeSearch(),
    )
    assert dossiers == []
    assert not default_research_jsonl_path("spring-boot", *HOP).exists()
    built = build_extraction_input(FILTERED, rows, dossiers)
    assert built.document == FILTERED

    skipped = run_research(
        rows,
        "Spring Boot",
        HOP,
        framework_key="spring-boot",
        settings=_settings(tmp_path),
        model=Boom(),  # type: ignore[arg-type]
        search=FakeSearch(),
        skip=True,
    )
    assert skipped == []


def test_second_run_is_cached_and_one_changed_row_regenerates_entities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = _settings(tmp_path)
    model = ScriptedModel(_ok_payload)
    search = FakeSearch()
    rows = parse_filtered_markdown(FILTERED)
    first = run_research(
        rows,
        "Spring Boot",
        HOP,
        framework_key="spring-boot",
        settings=settings,
        model=model,  # type: ignore[arg-type]
        search=search,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert len(first) == 3
    assert all(item.status == "ok" for item in first)
    assert search.queries
    assert "Spring Boot" in search.queries[0] and "3.5.1" in search.queries[0]
    summary = json.loads(
        default_research_summary_path("spring-boot", *HOP).read_text(encoding="utf-8")
    )
    assert summary["tool_calls"] == 6
    assert summary["wall_time_sec"] >= 0
    assert summary["rows"] == 3
    calls_after_first = model.calls
    queries_after_first = list(search.queries)

    second = run_research(
        rows,
        "Spring Boot",
        HOP,
        framework_key="spring-boot",
        settings=settings,
        model=model,  # type: ignore[arg-type]
        search=search,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert [item.row_key for item in second] == [item.row_key for item in first]
    assert model.calls == calls_after_first
    assert search.queries == queries_after_first

    document = build_extraction_input(FILTERED, rows, second)
    json_path = tmp_path / "runs" / "json" / "spring-boot-3.5.0-to-3.5.1-entities.json"
    seen: list[str] = []

    def fake_invoke(document_text: str, framework: str) -> MigrationEntitiesBatch:
        seen.append(document_text)
        return _entity("from research")

    monkeypatch.setattr(
        "migration_oracle.pipeline.extractor._invoke_structured", fake_invoke
    )
    run_extraction(
        document.document,
        framework_display="Spring Boot",
        output_path=json_path,
        flags=_flags(skip_entity=False),
        section_documents=list(document.section_documents),
    )
    assert seen == [document.document]
    cached_flags = refresh_flags_for_entity_input(
        _flags(skip_entity=True),
        document.document,
        json_path,
        has_appendix=document.has_appendix,
    )
    assert cached_flags.skip_entity_llm is True

    changed = FILTERED.replace("Rename timeout", "Rename connect-timeout")
    changed_rows = parse_filtered_markdown(changed)
    third = run_research(
        changed_rows,
        "Spring Boot",
        HOP,
        framework_key="spring-boot",
        settings=settings,
        model=model,  # type: ignore[arg-type]
        search=search,
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert len(search.queries) == len(queries_after_first) + 1
    assert model.final_calls == 4  # three rows, then exactly one more
    changed_document = build_extraction_input(changed, changed_rows, third)
    refreshed = refresh_flags_for_entity_input(
        _flags(skip_entity=True),
        changed_document.document,
        json_path,
        has_appendix=True,
    )
    assert refreshed.skip_entity_llm is False
    run_extraction(
        changed_document.document,
        framework_display="Spring Boot",
        output_path=json_path,
        flags=refreshed,
    )
    assert seen[-1] == changed_document.document
    assert "Rename connect-timeout" in seen[-1]


def test_entity_step_splits_when_the_input_exceeds_the_token_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_invoke(document_text: str, framework: str) -> MigrationEntitiesBatch:
        calls.append(document_text)
        title = "breaking" if "Breaking" in document_text else "deprecation"
        section = "breaking_change" if title == "breaking" else "deprecation"
        return MigrationEntitiesBatch(
            entities=[
                MigrationEntity(
                    source_section=section,  # type: ignore[arg-type]
                    title=title,
                    change_type="breaking_change",
                    reason="Split section.",
                    scopes=[
                        BreakingScopeInput(scope=ScopeLevel.API_SURFACE, severity=Severity.LOW)
                    ],
                )
            ]
        )

    monkeypatch.setattr(
        "migration_oracle.pipeline.extractor._invoke_structured", fake_invoke
    )
    built = build_extraction_input(FILTERED, [], [])
    result = run_extraction(
        FILTERED,
        framework_display="Spring Boot",
        output_path=tmp_path / "entities.json",
        flags=_flags(skip_entity=False),
        section_documents=list(built.section_documents),
        max_input_tokens=1,
    )
    assert len(calls) == 2
    assert [entity.title for entity in result.batch.entities] == ["breaking", "deprecation"]

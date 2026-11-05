"""Research without TAVILY_API_KEY: fetch_url only, no web_search, no Tavily client."""

from __future__ import annotations

from pathlib import Path

import pytest

from migration_oracle.pipeline.research import run as research_run
from migration_oracle.pipeline.research.agent import (
    FETCH_ONLY_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    TOOL_SPECS,
    ModelTurn,
    ToolCall,
    research_row,
)
from migration_oracle.pipeline.research.markdown import parse_filtered_markdown
from migration_oracle.pipeline.research.run import row_cache_path, run_research
from migration_oracle.pipeline.research.settings import load_settings

from test_research_agent import FILTERED, HOP, FakeFetcher, _settings


class FetchOnlyModel:
    """Tries web_search once, then fetches the row Source and answers."""

    def __init__(self) -> None:
        self.tool_names: list[list[str]] = []
        self.system_prompts: list[str] = []
        self.tool_results: list[str] = []

    async def complete(self, messages, *, tools, response_format):
        self.system_prompts.append(messages[0]["content"])
        if tools is not None:
            self.tool_names.append([spec["function"]["name"] for spec in tools])
        tool_messages = [message for message in messages if message["role"] == "tool"]
        self.tool_results = [message["content"] for message in tool_messages]
        source = next(
            line[len("Sources: ") :]
            for line in messages[1]["content"].splitlines()
            if line.startswith("Sources: ")
        )
        if not tool_messages:
            return ModelTurn(tool_calls=[ToolCall("s", "web_search", {"query": "LegacyClient"})])
        if len(tool_messages) == 1:
            return ModelTurn(tool_calls=[ToolCall("f", "fetch_url", {"url": source})])
        return ModelTurn(
            content=(
                f"**What changed:** `com.example.LegacyClient` was removed ({source})\n"
                "**Affects:** all applications\n**Action:** none"
            )
        )


def test_empty_tavily_key_keeps_research_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_BASE_URL", "http://research.example/v1")
    monkeypatch.setenv("RESEARCH_MODEL_ID", "fake-model")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    settings = load_settings()
    assert settings.enabled
    assert not settings.search_enabled
    monkeypatch.setenv("TAVILY_API_KEY", "not-a-real-key")
    assert load_settings().search_enabled


@pytest.mark.asyncio
async def test_without_search_only_fetch_url_is_offered(tmp_path: Path) -> None:
    settings = _settings(tmp_path, tavily_api_key="")
    row = parse_filtered_markdown(FILTERED)[0]
    model = FetchOnlyModel()
    fetcher = FakeFetcher()
    dossier, calls = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=settings,
        model=model,
        search=None,
        fetcher=fetcher,  # type: ignore[arg-type]
    )
    assert dossier.status == "ok"
    assert calls == 2
    assert all(names == ["fetch_url"] for names in model.tool_names)
    assert model.system_prompts[0] == FETCH_ONLY_SYSTEM_PROMPT
    assert "web_search" not in FETCH_ONLY_SYSTEM_PROMPT
    assert model.tool_results[0].startswith("web_search is not available")
    assert fetcher.urls == ["https://example.com/a"]


def test_tavily_mode_prompt_and_tools_are_unchanged() -> None:
    assert [spec["function"]["name"] for spec in TOOL_SPECS] == ["web_search", "fetch_url"]
    assert "Every web_search query must include" in SYSTEM_PROMPT


def test_run_without_key_never_builds_a_search_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    research_run.reset_notices()

    def forbid(*_args, **_kwargs):
        raise AssertionError("Tavily client must not be built without a key")

    monkeypatch.setattr(research_run, "build_search", forbid)
    settings = _settings(tmp_path, tavily_api_key="")
    dossiers = run_research(
        parse_filtered_markdown(FILTERED),
        "Spring Boot",
        HOP,
        framework_key="spring-boot",
        settings=settings,
        model=FetchOnlyModel(),  # type: ignore[arg-type]
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert [dossier.status for dossier in dossiers] == ["ok", "ok", "ok"]


def test_fetch_only_rows_do_not_share_the_tavily_cache(tmp_path: Path) -> None:
    with_key = row_cache_path(_settings(tmp_path), "k", "spring-boot", HOP)
    without_key = row_cache_path(_settings(tmp_path, tavily_api_key=""), "k", "spring-boot", HOP)
    assert with_key != without_key

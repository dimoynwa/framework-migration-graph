"""Regression tests for the 023 review fixes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from migration_oracle.pipeline.research.agent import ModelTurn, ToolCall, research_row
from migration_oracle.pipeline.research.markdown import (
    attach_raw_context,
    build_extraction_input,
    parse_filtered_markdown,
)
from migration_oracle.pipeline.research.run import run_research
from migration_oracle.pipeline.research.tools import SearchTool, refusal_reason

from tests.pipeline.test_research_agent import (
    FILTERED,
    HOP,
    FakeFetcher,
    FakeSearch,
    _ok_payload,
    _settings,
)


class FlakyModel:
    """Fails every call until ``healthy`` is set, then researches normally."""

    def __init__(self) -> None:
        self.healthy = False
        self.calls = 0

    async def complete(self, messages, *, tools, response_format):
        self.calls += 1
        if not self.healthy:
            raise RuntimeError("research model HTTP 503")
        if tools is None:
            return ModelTurn(content=_ok_payload(messages))
        if not any(message["role"] == "tool" for message in messages):
            source = next(
                line[len("Sources: ") :]
                for message in messages
                if message["role"] == "user"
                for line in message["content"].splitlines()
                if line.startswith("Sources: ")
            )
            return ModelTurn(tool_calls=[ToolCall("f", "fetch_url", {"url": source})])
        return ModelTurn(content=_ok_payload(messages))


def _run(rows, settings, model, *, hop=HOP, framework_key="spring-boot"):
    return run_research(
        rows,
        "Spring Boot",
        hop,
        framework_key=framework_key,
        settings=settings,
        model=model,  # type: ignore[arg-type]
        search=FakeSearch(),
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )


def test_error_dossiers_are_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = _settings(tmp_path)
    rows = parse_filtered_markdown(FILTERED)
    model = FlakyModel()
    first = _run(rows, settings, model)
    assert {item.status for item in first} == {"error"}

    model.healthy = True
    second = _run(rows, settings, model)
    assert {item.status for item in second} == {"ok"}


def test_cache_key_includes_framework_and_hop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = _settings(tmp_path)
    rows = parse_filtered_markdown(FILTERED)
    model = FlakyModel()
    model.healthy = True
    _run(rows, settings, model)
    after_first = model.calls
    _run(rows, settings, model)
    assert model.calls == after_first  # same hop: cached
    _run(rows, settings, model, hop=("3.5.1", "3.5.2"))
    after_other_hop = model.calls
    assert after_other_hop > after_first  # other hop: researched again
    _run(rows, settings, model, framework_key="other-framework")
    assert model.calls > after_other_hop  # other framework: researched again


@pytest.mark.asyncio
async def test_exact_budget_finalizes_instead_of_erroring(tmp_path: Path) -> None:
    row = parse_filtered_markdown(FILTERED)[0]
    seen_final: list[list[dict]] = []

    class OneFetchThenMore:
        async def complete(self, messages, *, tools, response_format):
            if tools is None:
                seen_final.append(messages)
                return ModelTurn(content=_ok_payload(messages))
            return ModelTurn(
                tool_calls=[ToolCall("f", "fetch_url", {"url": "https://example.com/a"})]
            )

    dossier, used = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=_settings(tmp_path, max_tool_calls=1),
        model=OneFetchThenMore(),
        search=SearchTool(
            FakeSearch(),
            cache_dir=tmp_path / "artifacts",
            framework="Spring Boot",
            to_version="3.5.1",
            max_results=5,
        ),
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert used == 1
    assert dossier.status == "ok"
    assert seen_final and seen_final[0][-1]["role"] == "user"
    assert "Write the description now" in seen_final[0][-1]["content"]


@pytest.mark.asyncio
async def test_turn_exceeding_the_remaining_budget_is_dropped(tmp_path: Path) -> None:
    row = parse_filtered_markdown(FILTERED)[0]

    class TwoAtOnce:
        async def complete(self, messages, *, tools, response_format):
            return ModelTurn(
                tool_calls=[
                    ToolCall("a", "fetch_url", {"url": "https://example.com/a"}),
                    ToolCall("b", "fetch_url", {"url": "https://example.com/b"}),
                ]
            )

    dossier, used = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=_settings(tmp_path, max_tool_calls=1),
        model=TwoAtOnce(),
        search=SearchTool(
            FakeSearch(),
            cache_dir=tmp_path / "artifacts",
            framework="Spring Boot",
            to_version="3.5.1",
            max_results=5,
        ),
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    # The over-budget turn is not executed; nothing was fetched, so nothing is grounded.
    assert used == 0
    assert dossier.status == "not_found"


SHARED_RAW = """\
# Spring Boot — documented changes (extract-only)

- **Framework key:** `spring-boot`
- **Resolved range:** `3.5.0` → `3.5.1`

---

## `3.5.0` → `3.5.1`

| Type | Confidence | Source | Statement |
|------|------------|--------|-----------|
| breaking | confirmed | https://example.com/wiki | Remove LegacyClient [#101](https://github.com/o/r/issues/101) |
| behavioral | inferred | https://example.com/wiki | Unrelated one |
| behavioral | inferred | https://example.com/wiki | Unrelated two |
| behavioral | inferred | https://example.com/wiki | Unrelated three |
| behavioral | inferred | https://example.com/wiki | Unrelated four |
"""

SHARED_FILTERED = """\
## 🔴 Breaking Changes

| # | JIRA | Title | Impact | Sources |
| --- | --- | --- | --- | --- |
| 1 | N/A | Remove LegacyClient | Remove it. | https://example.com/wiki, https://github.com/o/r/issues/101 |
| 2 | N/A | Only wiki | Something. | https://example.com/wiki |
"""


def test_shared_source_urls_do_not_attach_unrelated_rows() -> None:
    rows = attach_raw_context(parse_filtered_markdown(SHARED_FILTERED), SHARED_RAW)
    # Matched through the issue link inside the statement, not the shared wiki URL.
    assert rows[0].raw_statements == (
        "Remove LegacyClient [#101](https://github.com/o/r/issues/101)",
    )
    assert rows[1].raw_statements == ()


def test_raw_context_is_capped() -> None:
    rows = attach_raw_context(
        parse_filtered_markdown(SHARED_FILTERED),
        SHARED_RAW,
        shared_url_max_rows=10,
        max_chars=20,
    )
    assert sum(len(item) for item in rows[1].raw_statements) <= 20


def test_section_split_skips_summary_sections() -> None:
    filtered = FILTERED + """
## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 2 | Must fix before migrating. |

## 🚨 Most Critical Items for Migration

- Remove LegacyClient before upgrading.
"""
    rows = parse_filtered_markdown(filtered)
    built = build_extraction_input(filtered, rows, [])
    assert len(built.section_documents) == 2
    assert not any("Summary by Priority" in doc for doc in built.section_documents)
    assert not any("Most Critical" in doc for doc in built.section_documents)


@pytest.mark.parametrize(
    "url",
    ["http://100.64.0.1/admin", "http://[::ffff:10.0.0.1]/admin"],
)
def test_fetch_guard_blocks_shared_and_mapped_private_addresses(url: str) -> None:
    assert refusal_reason(url) is not None


# --- prompt review -----------------------------------------------------------

from migration_oracle.pipeline.extractor import _render_prompt  # noqa: E402
from migration_oracle.pipeline.filters import _filter_chunks, render_filter_prompt  # noqa: E402
from migration_oracle.pipeline.research.agent import SYSTEM_PROMPT  # noqa: E402
from migration_oracle.pipeline.research.markdown import (  # noqa: E402
    render_research_request,
    version_lines,
)
from migration_oracle.pipeline.triage.markdown import (  # noqa: E402
    FILTER_TABLE_HEADER,
    FILTER_TABLE_SEPARATOR,
)


def test_entity_prompt_subsystem_rules_depend_on_framework() -> None:
    wildfly = _render_prompt("WildFly", "DOC")
    spring = _render_prompt("Spring Boot", "DOC")
    assert "management model" in wildfly
    assert 'Empty string "" for WildFly' not in wildfly
    assert "Always the empty string" in spring
    for prompt in (wildfly, spring):
        assert "{" + "subsystem_rule}" not in prompt
        assert "{" + "cli_rule}" not in prompt
        assert prompt.rstrip().endswith("DOC")


def test_entity_prompt_does_not_parse_braces_in_the_document() -> None:
    prompt = _render_prompt("Spring Boot", "uses {framework} and {cli_rule} literally")
    assert prompt.rstrip().endswith("uses {framework} and {cli_rule} literally")


def test_filter_prompt_substitution_keeps_braces() -> None:
    prompt = render_filter_prompt("| a | ${placeholder} {x} |")
    assert "${placeholder} {x}" in prompt
    assert "PARTIAL INPUT" not in prompt
    assert "PARTIAL INPUT" in render_filter_prompt("t", partial=True)


def test_partial_filter_chunks_keep_the_preamble(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILTER_MAX_INPUT_TOKENS", "1")
    table = "\n".join(
        [
            "# Spring Boot — documented changes (extract-only)",
            "",
            "- **Framework key:** `spring-boot`",
            "- **Resolved range:** `3.5.0` → `3.5.1`",
            "",
            FILTER_TABLE_HEADER,
            FILTER_TABLE_SEPARATOR,
            "| behavioral | inferred | https://e/a | one | breaking | 2.00 |",
            "| behavioral | inferred | https://e/b | two | deprecation | 1.00 |",
            "| behavioral | inferred | https://e/c | three | dependency_upgrade | 1.00 |",
            "",
        ]
    )
    chunks = _filter_chunks(table)
    assert len(chunks) == 2
    assert all("Resolved range:** `3.5.0` → `3.5.1`" in chunk for chunk in chunks)


def test_research_request_lists_version_lines() -> None:
    assert version_lines(("3.5.0", "3.5.1")) == ["3.5"]
    assert version_lines(("3.4.0", "3.5.0")) == ["3.4", "3.5"]
    assert version_lines(("3.5.0", "4.0.0")) == ["3.5", "4.0"]
    row = parse_filtered_markdown(FILTERED)[0]
    assert "Version lines: 3.5" in render_research_request(row, "Spring Boot", HOP)


def test_research_prompt_documents_the_fields() -> None:
    for text in (
        "NOT_FOUND",
        "**What changed:**",
        "**Affects:**",
        "**Action:**",
        "**Before/after:**",
        "do not repeat the Summary",
        "no JSON",
    ):
        assert text in SYSTEM_PROMPT


def test_error_reason_is_recorded_in_jsonl_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from migration_oracle.pipeline._paths import (
        default_research_jsonl_path,
        default_research_summary_path,
    )

    monkeypatch.chdir(tmp_path)
    settings = _settings(tmp_path)
    rows = parse_filtered_markdown(FILTERED)
    dossiers = _run(rows, settings, FlakyModel())
    assert all(item.status == "error" for item in dossiers)
    assert all("RuntimeError: research model HTTP 503" in item.error for item in dossiers)
    assert all(item.error.startswith("tool loop") for item in dossiers)

    lines = default_research_jsonl_path("spring-boot", *HOP).read_text().splitlines()
    assert "research model HTTP 503" in json.loads(lines[0])["error"]
    summary = json.loads(default_research_summary_path("spring-boot", *HOP).read_text())
    assert summary["errors"] == {"tool loop: RuntimeError": len(rows)}


@pytest.mark.asyncio
async def test_answer_without_tool_calls_is_the_description_no_extra_call(
    tmp_path: Path,
) -> None:
    row = parse_filtered_markdown(FILTERED)[0]
    calls: list[object] = []

    class FetchThenWrite:
        async def complete(self, messages, *, tools, response_format):
            calls.append(tools)
            assert response_format is None  # no JSON schema any more
            if any(m["role"] == "tool" for m in messages):
                return ModelTurn(content="LegacyClient was removed (https://example.com/a).")
            return ModelTurn(tool_calls=[ToolCall("a", "fetch_url", {"url": "https://example.com/a"})])

    dossier, used = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=_settings(tmp_path),
        model=FetchThenWrite(),  # type: ignore[arg-type]
        search=SearchTool(FakeSearch(), cache_dir=tmp_path, framework="Spring Boot", to_version=HOP[1], max_results=3),
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert dossier.status == "ok"
    assert dossier.text == "LegacyClient was removed (https://example.com/a)."
    assert dossier.sources == ["https://example.com/a"]
    assert used == 1
    assert len(calls) == 2 and all(tools is not None for tools in calls)


@pytest.mark.asyncio
async def test_tool_calls_in_one_turn_run_concurrently_and_keep_order(tmp_path: Path) -> None:
    import threading

    row = parse_filtered_markdown(FILTERED)[0]
    barrier = threading.Barrier(3, timeout=2)  # deadlocks unless all three run at once

    class BarrierFetcher(FakeFetcher):
        def fetch(self, url):
            barrier.wait()
            return super().fetch(url)

    urls = [f"https://example.com/{i}" for i in range(3)]
    seen: list[list[str]] = []

    class ThreeFetches:
        async def complete(self, messages, *, tools, response_format):
            if any(m["role"] == "tool" for m in messages):
                seen.append([m["tool_call_id"] for m in messages if m["role"] == "tool"])
                return ModelTurn(content=_ok_payload(messages))
            return ModelTurn(
                tool_calls=[ToolCall(f"c{i}", "fetch_url", {"url": u}) for i, u in enumerate(urls)]
            )

    dossier, used = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=_settings(tmp_path),
        model=ThreeFetches(),  # type: ignore[arg-type]
        search=SearchTool(FakeSearch(), cache_dir=tmp_path, framework="Spring Boot", to_version=HOP[1], max_results=3),
        fetcher=BarrierFetcher(),  # type: ignore[arg-type]
    )
    assert dossier.status != "error", dossier.error
    assert used == 3
    assert seen == [["c0", "c1", "c2"]]


def test_cache_key_includes_thinking_flag(tmp_path: Path) -> None:
    from dataclasses import replace

    from migration_oracle.pipeline.research.run import row_cache_path

    settings = _settings(tmp_path)
    on = row_cache_path(replace(settings, enable_thinking=True), "k", "spring-boot", HOP)
    off = row_cache_path(replace(settings, enable_thinking=False), "k", "spring-boot", HOP)
    assert on != off


@pytest.mark.asyncio
async def test_turn_over_budget_finalizes_with_fetched_pages(tmp_path: Path) -> None:
    row = parse_filtered_markdown(FILTERED)[0]
    tool_messages: list[str] = []

    class Greedy:
        async def complete(self, messages, *, tools, response_format):
            if tools is None:
                tool_messages.extend(m["content"] for m in messages if m["role"] == "tool")
                return ModelTurn(content=_ok_payload(messages))
            if any(m["role"] == "tool" for m in messages):
                # Budget 2, one used: asks for two more.
                return ModelTurn(
                    tool_calls=[
                        ToolCall("b", "web_search", {"query": "x"}),
                        ToolCall("c", "web_search", {"query": "y"}),
                    ]
                )
            source = next(
                line[len("Sources: ") :]
                for m in messages
                if m["role"] == "user"
                for line in m["content"].splitlines()
                if line.startswith("Sources: ")
            )
            return ModelTurn(tool_calls=[ToolCall("a", "fetch_url", {"url": source})])

    dossier, used = await research_row(
        row,
        framework="Spring Boot",
        hop=HOP,
        settings=_settings(tmp_path, max_tool_calls=2),
        model=Greedy(),  # type: ignore[arg-type]
        search=SearchTool(FakeSearch(), cache_dir=tmp_path, framework="Spring Boot", to_version=HOP[1], max_results=3),
        fetcher=FakeFetcher(),  # type: ignore[arg-type]
    )
    assert dossier.status == "ok", dossier.error
    assert used == 1
    assert "[System: 1/2 tool calls used, 1 left." in tool_messages[-1]


@pytest.mark.asyncio
async def test_model_timeout_message_names_the_timeout(tmp_path: Path) -> None:
    import httpx

    from migration_oracle.pipeline.research.agent import ChatCompletionsModel

    class Hang(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ReadTimeout("", request=request)

    settings = _settings(tmp_path)
    model = ChatCompletionsModel(settings, transport=Hang())
    with pytest.raises(RuntimeError, match=r"ReadTimeout after .*s \(1 messages, 2 chars\)"):
        await model.complete([{"role": "user", "content": "hi"}], tools=None, response_format=None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**What changed:** x\n**Action:** required: rename `a.b` to `a.c`", "required"),
        ("**Action:** none", "none"),
        ("**Action:** No action needed.", "none"),
        ("**Action:** unclear from the sources", "unclear"),
        ("LegacyClient was removed.", "missing"),
    ],
)
def test_action_line_is_classified_for_the_summary(text: str, expected: str) -> None:
    from migration_oracle.pipeline.research.schema import action_of

    assert action_of(text) == expected


def test_summary_counts_action_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from migration_oracle.pipeline._paths import default_research_summary_path

    monkeypatch.chdir(tmp_path)
    model = FlakyModel()
    model.healthy = True
    _run(parse_filtered_markdown(FILTERED), _settings(tmp_path), model)
    summary = json.loads(default_research_summary_path("spring-boot", *HOP).read_text())
    # The fake model's text has no **Action:** line.
    assert summary["action"] == {"required": 0, "none": 0, "unclear": 0, "missing": 3}

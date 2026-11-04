"""Spring Boot GitHub issue enrichment.

Recorded release text and issue JSON stand in for the GitHub API, same approach
as ``tests/extractors/test_wildfly_jira.py``.
"""

from __future__ import annotations

import logging

import pytest
import respx
from httpx import Response

from migration_oracle import config
from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.extractors.base import HopContext
from migration_oracle.pipeline.extractors.github_enrichment import (
    backport_target,
    clean_issue_body,
    extract_issue_numbers,
    parse_github_issue,
)
from migration_oracle.pipeline.extractors.spring_boot import (
    SPRING_BOOT_REPO,
    SpringBootExtractor,
    parse_github_release_text,
)

RELEASE_URL = "https://github.com/spring-projects/spring-boot/releases/tag/v3.1.10"
ISSUES = "https://api.github.com/repos/spring-projects/spring-boot/issues"
ISSUE_WEB = "https://github.com/spring-projects/spring-boot/issues"

AC1_TITLE = (
    "When graceful shutdown of Tomcat is aborted it may report that it "
    "completed successfully"
)
AC1_BODY = (
    "There is a race condition when graceful shutdown is aborted. The result "
    "is reported as IDLE when it should have been REQUESTS_ACTIVE and this "
    "affects log messages."
)
AC1_RELEASE = (
    "## Bug Fixes\n"
    f"- {AC1_TITLE} [#39942]({ISSUE_WEB}/39942)\n"
)


def _issue(
    number: int,
    *,
    title: str,
    body: str,
    labels: list[str] | None = None,
    state_reason: str = "completed",
    pull: bool = False,
) -> dict:
    payload: dict = {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": label} for label in (labels or [])],
        "state_reason": state_reason,
        "html_url": f"{ISSUE_WEB}/{number}",
    }
    if pull:
        payload["pull_request"] = {"url": f"https://api.github.com/repos/{SPRING_BOOT_REPO}/pulls/{number}"}
    return payload


def _mock_release(body: str, version: str = "3.1.10") -> None:
    respx.get(
        f"https://api.github.com/repos/spring-projects/spring-boot/releases/tags/v{version}"
    ).mock(
        return_value=Response(
            200,
            json={
                "body": body,
                "html_url": (
                    "https://github.com/spring-projects/spring-boot/releases/tag/"
                    f"v{version}"
                ),
            },
        )
    )


@pytest.fixture
def github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(config, "SPRING_BOOT_GITHUB_ENRICHMENT", True)


def test_extract_issue_numbers_prefers_first_distinct_ref() -> None:
    statement = (
        f"See [#39942]({ISSUE_WEB}/39942) and also "
        f"{ISSUE_WEB.replace('/issues', '/pull')}/15"
    )
    assert extract_issue_numbers(statement) == [39942, 15]
    assert extract_issue_numbers("no issue here") == []


def test_backport_target_matches_short_pointers_only() -> None:
    assert backport_target("Backport of #39900") == 39900
    assert backport_target("Forward port of issue #39900 to 3.2.x") == 39900
    assert backport_target("back-port of #12") == 12
    assert backport_target("Not a pointer") is None
    assert backport_target(("x" * 220) + " Backport of #39900") is None


def test_clean_issue_body_strips_template_fences_and_stack_traces() -> None:
    template = "<!--\nThanks for raising an issue.\nPlease describe it.\n-->"
    assert clean_issue_body(template) == "N/A"

    fenced = "before\n```java\n" + "\n".join(f"line {i}" for i in range(11)) + "\n```\nafter"
    cleaned = clean_issue_body(fenced)
    assert "[code omitted]" in cleaned
    assert "line 0" not in cleaned
    short_fence = "```\nonly\na\nfew\nlines\n```"
    assert "only" in clean_issue_body(short_fence)

    traced = (
        "Shutdown hits a race condition.\n"
        "java.lang.IllegalStateException: aborted\n"
        "\tat org.apache.catalina.core.StandardServer.await(StandardServer.java:431)\n"
        "\tat org.springframework.boot.web.embedded.tomcat.GracefulShutdown.abort(GracefulShutdown.java:80)\n"
        "Caused by: java.lang.NullPointerException: missing\n"
        "\tat org.example.Demo.fail(Demo.java:3)\n"
        "The log line is wrong.\n"
    )
    cleaned_trace = clean_issue_body(traced)
    assert "race condition" in cleaned_trace
    assert "log line is wrong" in cleaned_trace
    assert "StandardServer" not in cleaned_trace
    assert "NullPointerException" not in cleaned_trace

    assert clean_issue_body("<p>race condition</p>") == "race condition"
    assert clean_issue_body("alpha\n\n  beta") == "alpha beta"
    truncated = clean_issue_body("abcdef", max_chars=4)
    assert truncated == "abc…"


def test_parse_github_issue_marks_pull_requests() -> None:
    issue = parse_github_issue(
        _issue(77, title="Bump tomcat", body="routine", labels=["type: dependency-upgrade"], pull=True),
        number=77,
    )
    assert issue["is_pull_request"] is True
    assert issue["labels"] == ["type: dependency-upgrade"]
    assert issue["body"] == "routine"


@pytest.mark.asyncio
@respx.mock
async def test_ac1_release_row_uses_issue_title_body_and_labels(github_token: None) -> None:
    _mock_release(AC1_RELEASE)
    respx.get(f"{ISSUES}/39942").mock(
        return_value=Response(
            200,
            json=_issue(
                39942,
                title=AC1_TITLE,
                body=AC1_BODY,
                labels=["type: bug"],
            ),
        )
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    change = result.changes[0]
    assert change.source_url == f"{ISSUE_WEB}/39942"
    assert change.statement.startswith(f"Title: {AC1_TITLE}")
    issue_section = change.statement.split("Issue:", 1)[1].split("Release:", 1)[0]
    assert "race condition" in issue_section
    assert change.metadata is not None
    assert change.metadata["github_labels"] == ["type: bug"]
    assert change.metadata["github_issue"] == 39942
    assert change.metadata["github_issue_type"] == "bug"
    assert change.metadata["release_url"] == RELEASE_URL
    assert "[#39942]" in change.statement.split("Release:", 1)[1]


@pytest.mark.asyncio
@respx.mock
async def test_ac2_template_only_body_is_na(github_token: None) -> None:
    _mock_release(f"## Bug Fixes\n- Empty template [#50]({ISSUE_WEB}/50)\n")
    respx.get(f"{ISSUES}/50").mock(
        return_value=Response(
            200,
            json=_issue(
                50,
                title="Empty template",
                body="<!--\nThanks for raising a Spring Boot issue.\n-->",
                labels=["type: bug"],
            ),
        )
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    assert "Issue: N/A" in result.changes[0].statement


@pytest.mark.asyncio
@respx.mock
async def test_ac3_backport_uses_original_body_once(github_token: None) -> None:
    _mock_release(
        f"## Bug Fixes\n- Shutdown report [#50]({ISSUE_WEB}/50)\n"
    )
    respx.get(f"{ISSUES}/50").mock(
        return_value=Response(
            200,
            json=_issue(
                50,
                title="Shutdown report",
                body="Backport of #39900",
                labels=["type: bug"],
            ),
        )
    )
    upstream = respx.get(f"{ISSUES}/39900").mock(
        return_value=Response(
            200,
            json=_issue(
                39900,
                title="Original shutdown report",
                body="The original report describes a race condition during shutdown.",
                labels=["type: enhancement"],
            ),
        )
    )
    further = respx.get(f"{ISSUES}/11111").mock(
        return_value=Response(200, json=_issue(11111, title="nope", body="should not load"))
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    change = result.changes[0]
    assert "race condition during shutdown" in change.statement
    assert change.metadata is not None
    assert change.metadata["github_backport_of"] == 39900
    assert change.metadata["github_issue"] == 50
    assert change.metadata["github_labels"] == ["type: bug"]
    assert change.source_url == f"{ISSUE_WEB}/50"
    assert change.statement.startswith("Title: Shutdown report")
    assert upstream.called
    assert not further.called


@pytest.mark.asyncio
@respx.mock
async def test_backport_does_not_recurse(github_token: None) -> None:
    _mock_release(f"## Bug Fixes\n- Pointer [#1]({ISSUE_WEB}/1)\n")
    respx.get(f"{ISSUES}/1").mock(
        return_value=Response(
            200, json=_issue(1, title="Pointer", body="Backport of #2")
        )
    )
    respx.get(f"{ISSUES}/2").mock(
        return_value=Response(
            200, json=_issue(2, title="Mid", body="Backport of #3")
        )
    )
    deepest = respx.get(f"{ISSUES}/3").mock(
        return_value=Response(
            200, json=_issue(3, title="Deep", body="the real race condition text")
        )
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    assert "Backport of #3" in result.changes[0].statement
    assert "real race condition text" not in result.changes[0].statement
    assert result.changes[0].metadata is not None
    assert result.changes[0].metadata["github_backport_of"] == 2
    assert not deepest.called


@pytest.mark.asyncio
@respx.mock
async def test_ac4_dependency_upgrade_does_not_override_breaking(github_token: None) -> None:
    body = (
        "## Breaking Changes\n"
        f"- Remove the legacy shutdown hook [#10]({ISSUE_WEB}/10)\n"
        "## Bug Fixes\n"
        f"- Upgrade tomcat [#11]({ISSUE_WEB}/11)\n"
        f"- Fix a regression [#12]({ISSUE_WEB}/12)\n"
    )
    _mock_release(body)
    respx.get(f"{ISSUES}/10").mock(
        return_value=Response(
            200,
            json=_issue(10, title="Remove hook", body="gone", labels=["type: dependency-upgrade"]),
        )
    )
    respx.get(f"{ISSUES}/11").mock(
        return_value=Response(
            200,
            json=_issue(11, title="Upgrade tomcat", body="bumped", labels=["type: dependency-upgrade"]),
        )
    )
    respx.get(f"{ISSUES}/12").mock(
        return_value=Response(
            200,
            json=_issue(12, title="Fix a regression", body="fixed", labels=["type: regression"]),
        )
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    by_issue = {change.metadata["github_issue"]: change for change in result.changes}
    assert by_issue[10].type == "breaking"
    assert by_issue[10].confidence == "confirmed"
    assert by_issue[11].type == "dependency_upgrade"
    assert by_issue[11].confidence == "inferred"
    assert by_issue[12].type == "behavioral"
    assert by_issue[12].confidence == "inferred"


@pytest.mark.asyncio
@respx.mock
async def test_ac5_without_token_makes_no_issue_request(caplog: pytest.LogCaptureFixture) -> None:
    body = AC1_RELEASE
    _mock_release(body)
    issue_route = respx.get(url__regex=rf"{ISSUES}/\d+").mock(
        return_value=Response(500, text="should not be called")
    )
    caplog.set_level(logging.INFO)

    async with SpringBootExtractor() as extractor:
        first = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )
        second = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    expected = parse_github_release_text(body, RELEASE_URL)
    for result in (first, second):
        assert [
            (change.type, change.confidence, change.source_url, change.statement, change.metadata)
            for change in result.changes
        ] == [
            (change.type, change.confidence, change.source_url, change.statement, change.metadata)
            for change in expected
        ]
    assert issue_route.call_count == 0
    token_logs = [record for record in caplog.records if "GITHUB_TOKEN" in record.message]
    assert len(token_logs) == 1
    assert token_logs[0].levelno == logging.INFO


@pytest.mark.asyncio
@respx.mock
async def test_ac6_404_leaves_that_row_and_enriches_the_rest(github_token: None) -> None:
    body = (
        "## Bug Fixes\n"
        f"- Missing issue [#111]({ISSUE_WEB}/111)\n"
        f"- Present issue [#222]({ISSUE_WEB}/222)\n"
        f"- Tries missing then present [#111]({ISSUE_WEB}/111) [#222]({ISSUE_WEB}/222)\n"
    )
    _mock_release(body)
    missing = respx.get(f"{ISSUES}/111").mock(return_value=Response(404, json={"message": "Not Found"}))
    respx.get(f"{ISSUES}/222").mock(
        return_value=Response(
            200,
            json=_issue(222, title="Present issue", body="has a race condition", labels=["type: bug"]),
        )
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    assert len(result.changes) == 3
    assert result.changes[0].source_url == RELEASE_URL
    assert not result.changes[0].statement.startswith("Title:")
    assert result.changes[1].source_url == f"{ISSUE_WEB}/222"
    assert "race condition" in result.changes[1].statement
    assert result.changes[2].metadata is not None
    assert result.changes[2].metadata["github_issue"] == 222
    assert missing.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_ac7_rate_limit_stops_further_issue_requests(
    github_token: None, caplog: pytest.LogCaptureFixture
) -> None:
    body = (
        "## Bug Fixes\n"
        f"- First [#1]({ISSUE_WEB}/1)\n"
        f"- Second [#2]({ISSUE_WEB}/2)\n"
        f"- Third [#3]({ISSUE_WEB}/3)\n"
    )
    _mock_release(body)
    route = respx.get(url__regex=rf"{ISSUES}/\d+")
    route.side_effect = [
        Response(
            200,
            json=_issue(1, title="First", body="enriched first", labels=["type: bug"]),
        ),
        Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0"},
        ),
        Response(200, json=_issue(3, title="Third", body="should not be fetched")),
    ]
    caplog.set_level(logging.WARNING)

    async with SpringBootExtractor() as extractor:
        extractor._github_enrich_max_concurrent = 1
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )
        await extractor.fetch_github_issues(SPRING_BOOT_REPO, [4])

    assert len(result.changes) == 3
    assert "enriched first" in result.changes[0].statement
    assert result.changes[1].source_url == RELEASE_URL
    assert result.changes[2].source_url == RELEASE_URL
    assert route.call_count == 2
    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "rate limit" in record.message
    ]
    assert len(warnings) == 1


@pytest.mark.asyncio
@respx.mock
async def test_enrichment_disabled_skips_issue_requests(
    github_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "SPRING_BOOT_GITHUB_ENRICHMENT", False)
    _mock_release(AC1_RELEASE)
    issue_route = respx.get(url__regex=rf"{ISSUES}/\d+").mock(
        return_value=Response(500, text="should not be called")
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    assert issue_route.call_count == 0
    assert result.changes[0].source_url == RELEASE_URL
    assert not result.changes[0].statement.startswith("Title:")


@pytest.mark.asyncio
@respx.mock
async def test_enrichment_exception_returns_unenriched_rows(
    github_token: None, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_release(AC1_RELEASE)
    caplog.set_level(logging.WARNING)

    async with SpringBootExtractor() as extractor:
        async def explode(repo: str, numbers: object) -> dict:
            raise RuntimeError("boom")

        extractor.fetch_github_issues = explode  # type: ignore[method-assign]
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    assert result.changes[0].source_url == RELEASE_URL
    assert not result.changes[0].statement.startswith("Title:")
    assert any("enrichment skipped" in record.message for record in caplog.records)


@pytest.mark.asyncio
@respx.mock
async def test_not_planned_rows_are_kept(github_token: None) -> None:
    _mock_release(f"## Bug Fixes\n- Dropped idea [#9]({ISSUE_WEB}/9)\n")
    respx.get(f"{ISSUES}/9").mock(
        return_value=Response(
            200,
            json=_issue(
                9,
                title="Dropped idea",
                body="will not do",
                labels=["type: enhancement"],
                state_reason="not_planned",
            ),
        )
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    change = result.changes[0]
    assert change.metadata is not None
    assert change.metadata["github_not_planned"] is True
    assert change.metadata["github_state_reason"] == "not_planned"
    assert change.type == "behavioral"


@pytest.mark.asyncio
@respx.mock
async def test_wiki_rows_are_not_enriched(github_token: None) -> None:
    _mock_release(
        f"## Bug Fixes\n- Release fix [#39942]({ISSUE_WEB}/39942)\n",
        version="3.4.0",
    )
    respx.get(f"{ISSUES}/39942").mock(
        return_value=Response(
            200, json=_issue(39942, title=AC1_TITLE, body=AC1_BODY, labels=["type: bug"])
        )
    )
    wiki = respx.get(
        "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes"
    ).mock(
        return_value=Response(
            200,
            text=(
                "<html><body><div id='wiki-body'><div class='markdown-body'>"
                "<h2>New Features</h2><ul><li>Wiki only note #88888</li></ul>"
                "</div></div></body></html>"
            ),
        )
    )
    wiki_issue = respx.get(f"{ISSUES}/88888").mock(
        return_value=Response(500, text="wiki issues are out of scope")
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.3.13", "3.4.0", hop_context=HopContext("3.3.13", "3.4.0")
        )

    assert wiki.called
    assert not wiki_issue.called
    wiki_rows = [change for change in result.changes if "wiki" in change.source_url]
    assert wiki_rows
    assert all(not change.statement.startswith("Title:") for change in wiki_rows)
    assert any(change.source_url == f"{ISSUE_WEB}/39942" for change in result.changes)


@pytest.mark.asyncio
@respx.mock
async def test_invalid_json_and_410_are_omitted(github_token: None) -> None:
    body = (
        "## Bug Fixes\n"
        f"- Gone [#7]({ISSUE_WEB}/7)\n"
        f"- Garbage [#8]({ISSUE_WEB}/8)\n"
        f"- Fine [#9]({ISSUE_WEB}/9)\n"
    )
    _mock_release(body)
    respx.get(f"{ISSUES}/7").mock(return_value=Response(410, text="gone"))
    respx.get(f"{ISSUES}/8").mock(return_value=Response(200, text="not-json"))
    respx.get(f"{ISSUES}/9").mock(
        return_value=Response(200, json=_issue(9, title="Fine", body="kept"))
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.1.9", "3.1.10", hop_context=HopContext("3.1.9", "3.1.10")
        )

    assert result.changes[0].source_url == RELEASE_URL
    assert result.changes[1].source_url == RELEASE_URL
    assert result.changes[2].source_url == f"{ISSUE_WEB}/9"


@pytest.mark.asyncio
async def test_apply_does_not_mutate_existing_metadata() -> None:
    original_meta = {"stability_level": "preview"}
    change = DocumentedChange(
        type="behavioral",
        confidence="inferred",
        source_url=RELEASE_URL,
        statement=f"Fix [#4]({ISSUE_WEB}/4)",
        metadata=original_meta,
    )
    issue = parse_github_issue(
        _issue(4, title="Fix", body="details", labels=["type: bug"]),
        number=4,
    )
    async with SpringBootExtractor() as extractor:
        enriched = extractor._apply_github_issues([change], {4: issue})
    assert enriched[0].metadata is not None
    assert enriched[0].metadata["stability_level"] == "preview"
    assert enriched[0].metadata is not original_meta
    assert "github_issue" not in original_meta

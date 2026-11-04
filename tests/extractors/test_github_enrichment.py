"""Parser, cleaning, and shared rate-limit tests for GitHub enrichment."""

from __future__ import annotations

import logging

import pytest
import respx
from httpx import Response

from migration_oracle import config
from migration_oracle.pipeline.extractors.angular import ANGULAR_REPO, AngularExtractor
from migration_oracle.pipeline.extractors.github_enrichment import (
    backport_target,
    clean_issue_body,
    extract_commit_shas,
    parse_github_commit,
)

LAZY_ROUTES_MESSAGE = (
    "fix(core): correctly perform lazy routes migration for components with "
    "additional decorators (#58796)\n"
    "\n"
    "This fixes an issue where the lazy-routes migration would crash for "
    "component classes a\n"
    "decorator without arguments in front of the `@Component` decorator "
    "(in particular, it needed\n"
    "to be the first decorator).\n"
    "\n"
    "Fixes #58793\n"
    "\n"
    "PR Close #58796"
)


@pytest.fixture
def github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GITHUB_TOKEN", "test-token")


def test_clean_issue_body_strips_template_fences_and_stack_traces() -> None:
    template = "<!--\nThanks for raising an issue.\nPlease describe it.\n-->"
    assert clean_issue_body(template) == "N/A"

    fenced = "before\n```java\n" + "\n".join(f"line {i}" for i in range(11)) + "\n```\nafter"
    cleaned = clean_issue_body(fenced)
    assert "[code omitted]" in cleaned
    assert "line 0" not in cleaned
    assert "only" in clean_issue_body("```\nonly\na\nfew\nlines\n```")

    traced = (
        "Shutdown hits a race condition.\n"
        "java.lang.IllegalStateException: aborted\n"
        "\tat org.apache.catalina.core.StandardServer.await(StandardServer.java:431)\n"
        "Caused by: java.lang.NullPointerException: missing\n"
        "\tat org.example.Demo.fail(Demo.java:3)\n"
        "The log line is wrong.\n"
    )
    cleaned_trace = clean_issue_body(traced)
    assert "race condition" in cleaned_trace
    assert "log line is wrong" in cleaned_trace
    assert "StandardServer" not in cleaned_trace
    assert "NullPointerException" not in cleaned_trace
    assert clean_issue_body("alpha\n\n  beta") == "alpha beta"
    assert "Record<string, Foo>" in clean_issue_body("passed as Record<string, Foo>")
    assert clean_issue_body("<p>race condition</p>") == "race condition"
    assert clean_issue_body("abcdef", max_chars=4) == "abc…"


def test_backport_target_matches_short_pointers_only() -> None:
    assert backport_target("Backport of #39900") == 39900
    assert backport_target("Forward port of issue #39900 to 3.2.x") == 39900
    assert backport_target(("x" * 220) + " Backport of #39900") is None


def test_parse_lazy_routes_commit_strips_footers() -> None:
    commit = parse_github_commit(
        {
            "sha": "99715104a1a787c3899dfbfac6b44f28c7d24356",
            "html_url": "https://github.com/angular/angular/commit/99715104a1a787c3899dfbfac6b44f28c7d24356",
            "commit": {"message": LAZY_ROUTES_MESSAGE},
            "files": [
                {"filename": "packages/core/schematics/ng-generate/route-lazy-loading/util.ts"},
                {"filename": "packages/core/src/render3/jit/environment.ts"},
            ],
        },
        sha="99715104a1",
        repo="angular/angular",
    )
    assert commit["type"] == "fix"
    assert commit["scope"] == "core"
    assert commit["pr"] == 58796
    assert commit["fixes"] == [58793]
    assert commit["bang"] is False
    assert "would crash" in commit["body"]
    assert "PR Close" not in commit["body"]
    assert "Fixes #58793" not in commit["body"]
    assert commit["header"].startswith("fix(core): correctly perform lazy routes migration")


def test_parse_commit_breaking_bang_and_deprecated() -> None:
    message = (
        "feat(forms)!: drop the legacy control value accessor\n"
        "\n"
        "Callers pass a signal instead.\n"
        "\n"
        "BREAKING CHANGE: ControlValueAccessor#writeValue\n"
        "now receives a signal.\n"
        "\n"
        "DEPRECATED: FormBuilder.group options bag\n"
        "\n"
        "Fixes #10\n"
        "Closes #11\n"
    )
    commit = parse_github_commit(
        {
            "sha": "abcdef1234567890",
            "commit": {"message": message},
            "files": [{"filename": "packages/forms/src/form_builder.ts"}],
        },
        sha="abcdef1234567890",
    )
    assert commit["bang"] is True
    assert commit["scope"] == "forms"
    assert "signal" in commit["breaking"]
    assert commit["deprecated"] == "FormBuilder.group options bag"
    assert commit["fixes"] == [10, 11]
    assert "BREAKING CHANGE" not in commit["body"]
    assert "DEPRECATED" not in commit["body"]


def test_extract_commit_shas_keeps_first_distinct() -> None:
    statement = (
        "[99715104a1](https://github.com/angular/angular/commit/99715104a1) "
        "and https://github.com/angular/angular/commit/abcdef1234"
    )
    assert extract_commit_shas(statement) == ["99715104a1", "abcdef1234"]


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_stops_later_commit_and_issue_requests(
    github_token: None, caplog: pytest.LogCaptureFixture
) -> None:
    route = respx.get(url__regex=r"https://api\.github\.com/repos/angular/angular/(commits|issues)/")
    route.side_effect = [
        Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0"},
        ),
        Response(200, json={"sha": "bbbbbbb", "commit": {"message": "fix: no"}}),
    ]
    caplog.set_level(logging.WARNING)

    async with AngularExtractor() as extractor:
        extractor._github_enrich_max_concurrent = 1
        first = await extractor.fetch_github_commits(ANGULAR_REPO, ["aaaaaaa", "bbbbbbb"])
        second = await extractor.fetch_github_issues(ANGULAR_REPO, [1])

    assert first == {}
    assert second == {}
    assert route.call_count == 1
    assert sum(1 for record in caplog.records if "rate limit" in record.message) == 1


@pytest.mark.asyncio
@respx.mock
async def test_commit_422_is_omitted(github_token: None) -> None:
    respx.get(
        "https://api.github.com/repos/angular/angular/commits/badbad1"
    ).mock(return_value=Response(422, json={"message": "No commit found"}))

    async with AngularExtractor() as extractor:
        commits = await extractor.fetch_github_commits(ANGULAR_REPO, ["badbad1"])

    assert commits == {}

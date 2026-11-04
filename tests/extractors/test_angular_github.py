"""Angular commit and issue enrichment wiring tests."""

from __future__ import annotations

import logging

import pytest
import respx
from httpx import Response

from migration_oracle import config
from migration_oracle.pipeline.extractors.angular import (
    CHANGELOG_URL,
    AngularExtractor,
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

FULL_SHA = "99715104a1a787c3899dfbfac6b44f28c7d24356"
SHORT_SHA = "99715104a1"
COMMIT_WEB = f"https://github.com/angular/angular/commit/{FULL_SHA}"
COMMITS = "https://api.github.com/repos/angular/angular/commits"
ISSUES = "https://api.github.com/repos/angular/angular/issues"
RELEASE_API = "https://api.github.com/repos/angular/angular/releases/tags/v19.0.1"
RELEASE_WEB = "https://github.com/angular/angular/releases/tag/v19.0.1"


def _release(body: str) -> None:
    respx.get(RELEASE_API).mock(
        return_value=Response(200, json={"body": body, "html_url": RELEASE_WEB})
    )


def _changelog(text: str) -> None:
    respx.get(CHANGELOG_URL).mock(return_value=Response(200, text=text))


def _commit(sha: str, message: str, files: list[str], *, full_sha: str | None = None) -> dict:
    resolved = full_sha or sha
    return {
        "sha": resolved,
        "html_url": f"https://github.com/angular/angular/commit/{resolved}",
        "commit": {"message": message},
        "files": [{"filename": name} for name in files],
    }


def _issue(number: int, *, title: str, body: str, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": label} for label in (labels or [])],
        "state_reason": "completed",
        "html_url": f"https://github.com/angular/angular/issues/{number}",
    }


@pytest.fixture
def github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(config, "ANGULAR_GITHUB_ENRICHMENT", True)


@pytest.mark.asyncio
@respx.mock
async def test_ac8_commit_row_includes_scope_issue_and_schematic(github_token: None) -> None:
    _release("## Bug Fixes\n- Unrelated release note without a commit\n")
    _changelog(
        '<a name="19.0.1"></a>\n'
        "# 19.0.1\n"
        f"- [{SHORT_SHA}](https://github.com/angular/angular/commit/{SHORT_SHA}) "
        "fix correctly perform lazy routes migration for components with additional "
        f"decorators ([#58796](https://github.com/angular/angular/pull/58796))\n"
    )
    respx.get(f"{COMMITS}/{SHORT_SHA}").mock(
        return_value=Response(
            200,
            json=_commit(
                SHORT_SHA,
                LAZY_ROUTES_MESSAGE,
                [
                    "packages/core/schematics/ng-generate/route-lazy-loading/util.ts",
                    "packages/core/src/render3/jit/environment.ts",
                ],
                full_sha=FULL_SHA,
            ),
        )
    )
    respx.get(f"{ISSUES}/58793").mock(
        return_value=Response(
            200,
            json=_issue(
                58793,
                title="Lazy routes migration crashes",
                body="The migration throws when a decorator has no arguments.",
            ),
        )
    )
    pull = respx.get(f"{ISSUES}/58796").mock(return_value=Response(500, text="not fetched"))

    async with AngularExtractor() as extractor:
        result = await extractor.extract("19.0.0", "19.0.1")

    change = next(row for row in result.changes if row.metadata and row.metadata.get("github_commit"))
    assert change.statement.startswith(
        "Title: fix(core): correctly perform lazy routes migration"
    )
    commit_section = change.statement.split("Commit:", 1)[1].split("Issue:", 1)[0]
    assert "would crash" in commit_section
    assert "Issue: #58793 Lazy routes migration crashes —" in change.statement
    assert "PR Close" not in change.statement
    assert change.metadata is not None
    assert change.metadata["angular_package"] == "core"
    assert change.metadata["github_pr"] == 58796
    assert change.metadata["github_fixes"] == [58793]
    assert change.metadata["has_schematic"] is True
    assert change.metadata["github_commit"] == FULL_SHA
    assert change.source_url == COMMIT_WEB
    assert change.metadata["release_url"] == CHANGELOG_URL
    assert not pull.called


@pytest.mark.asyncio
@respx.mock
async def test_ac9_breaking_footer_overrides_behavioral_row(github_token: None) -> None:
    sha = "abc1234"
    _release(
        "## Bug Fixes\n"
        f"- adjust provider tokens [abc1234](https://github.com/angular/angular/commit/{sha})\n"
    )
    _changelog("")
    respx.get(f"{COMMITS}/{sha}").mock(
        return_value=Response(
            200,
            json=_commit(
                sha,
                "refactor(core): adjust provider tokens\n\n"
                "Details of the change.\n\n"
                "BREAKING CHANGE: the old token is removed\n",
                ["packages/core/src/di/injector.ts"],
            ),
        )
    )

    async with AngularExtractor() as extractor:
        result = await extractor.extract("19.0.0", "19.0.1")

    change = result.changes[0]
    assert change.type == "breaking"
    assert change.confidence == "confirmed"
    assert "Breaking: the old token is removed" in change.statement
    assert change.metadata is not None
    assert change.metadata["has_schematic"] is False


@pytest.mark.asyncio
@respx.mock
async def test_ac10_pull_without_commit_uses_issue_path(github_token: None) -> None:
    _release(
        "## Bug Fixes\n"
        "- Fix the router outlet "
        "([#55](https://github.com/angular/angular/pull/55))\n"
    )
    _changelog("")
    respx.get(f"{ISSUES}/55").mock(
        return_value=Response(
            200,
            json=_issue(55, title="Fix the router outlet", body="outlet activation order changed"),
        )
    )

    async with AngularExtractor() as extractor:
        result = await extractor.extract("19.0.0", "19.0.1")

    change = result.changes[0]
    assert change.source_url == "https://github.com/angular/angular/issues/55"
    assert change.statement.startswith("Title: Fix the router outlet")
    assert "Issue: outlet activation order changed" in change.statement
    assert change.metadata is not None
    assert change.metadata["github_issue"] == 55
    assert "github_commit" not in change.metadata


@pytest.mark.asyncio
@respx.mock
async def test_linked_issue_does_not_follow_a_further_issue(github_token: None) -> None:
    sha = "def5678"
    _release(
        "## Bug Fixes\n"
        f"- note [def5678](https://github.com/angular/angular/commit/{sha})\n"
    )
    _changelog("")
    respx.get(f"{COMMITS}/{sha}").mock(
        return_value=Response(
            200,
            json=_commit(sha, "fix(core): note\n\nFixes #7\nFixes #8\n", ["packages/core/src/a.ts"]),
        )
    )
    respx.get(f"{ISSUES}/7").mock(
        return_value=Response(
            200, json=_issue(7, title="First", body="Backport of #99")
        )
    )
    second = respx.get(f"{ISSUES}/8").mock(return_value=Response(500, text="second fix"))
    nested = respx.get(f"{ISSUES}/99").mock(return_value=Response(500, text="nested"))

    async with AngularExtractor() as extractor:
        result = await extractor.extract("19.0.0", "19.0.1")

    assert "Issue: #7 First — Backport of #99" in result.changes[0].statement
    assert result.changes[0].metadata is not None
    assert result.changes[0].metadata["github_fixes"] == [7, 8]
    assert not second.called
    assert not nested.called


@pytest.mark.asyncio
@respx.mock
async def test_missing_commit_leaves_that_row_unchanged(github_token: None) -> None:
    _release(
        "## Bug Fixes\n"
        "- missing [1111111](https://github.com/angular/angular/commit/1111111)\n"
        "- present [2222222](https://github.com/angular/angular/commit/2222222)\n"
    )
    _changelog("")
    respx.get(f"{COMMITS}/1111111").mock(return_value=Response(404, json={"message": "Not Found"}))
    respx.get(f"{COMMITS}/2222222").mock(
        return_value=Response(
            200,
            json=_commit(2222222, "fix(router): present\n\nThe outlet was wrong.\n", ["packages/router/src/a.ts"]),
        )
    )

    async with AngularExtractor() as extractor:
        result = await extractor.extract("19.0.0", "19.0.1")

    assert result.changes[0].source_url == RELEASE_WEB
    assert not result.changes[0].statement.startswith("Title:")
    assert "The outlet was wrong" in result.changes[1].statement
    assert result.changes[1].metadata is not None
    assert result.changes[1].metadata["angular_package"] == "router"


@pytest.mark.asyncio
@respx.mock
async def test_without_token_makes_no_commit_or_issue_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = (
        "## Bug Fixes\n"
        "- note [99715104a1](https://github.com/angular/angular/commit/99715104a1)\n"
    )
    _release(body)
    _changelog("")
    route = respx.get(url__regex=r"https://api\.github\.com/repos/angular/angular/(commits|issues)/").mock(
        return_value=Response(500, text="should not be called")
    )
    caplog.set_level(logging.INFO)

    async with AngularExtractor() as extractor:
        result = await extractor.extract("19.0.0", "19.0.1")

    assert route.call_count == 0
    assert result.changes[0].source_url == RELEASE_WEB
    assert not result.changes[0].statement.startswith("Title:")
    assert any("GITHUB_TOKEN" in record.message for record in caplog.records)


@pytest.mark.asyncio
@respx.mock
async def test_issue_excerpt_is_capped_at_500_chars(github_token: None) -> None:
    sha = "abc9999"
    _release(
        "## Bug Fixes\n"
        f"- note [abc9999](https://github.com/angular/angular/commit/{sha})\n"
    )
    _changelog("")
    respx.get(f"{COMMITS}/{sha}").mock(
        return_value=Response(200, json=_commit(sha, "fix(core): note\n\nFixes #3\n", ["a.ts"]))
    )
    respx.get(f"{ISSUES}/3").mock(
        return_value=Response(200, json=_issue(3, title="Long", body="Z" * 800))
    )

    async with AngularExtractor() as extractor:
        result = await extractor.extract("19.0.0", "19.0.1")

    excerpt = result.changes[0].statement.split("— ", 1)[1].split("Release:", 1)[0].strip()
    assert excerpt == "Z" * 500

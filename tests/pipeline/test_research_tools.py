"""Search anchoring, fetch guards, and Tavily status mapping.

The Tavily client is exercised with an injected poster. These tests do not
call api.tavily.com and do not read a real API key.
"""

from __future__ import annotations

import json

import httpx
import pytest

from migration_oracle.pipeline.research.settings import ResearchSettings
from migration_oracle.pipeline.research.tools import (
    PageFetcher,
    SearchTool,
    TavilyQuotaError,
    TavilySearchClient,
    ensure_version_anchor,
)


def _settings(tmp_path) -> ResearchSettings:
    return ResearchSettings(
        base_url="http://research.example/v1",
        model_id="fake",
        api_key="",
        tavily_api_key="not-a-real-key",
        enable_thinking=False,
        max_concurrent=1,
        max_tool_calls=6,
        timeout_sec=5,
        search_results=5,
        fetch_max_chars=50,
        entity_max_input_tokens=60000,
        cache_dir=tmp_path / "artifacts",
    )


class _RecordingSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, *, max_results: int) -> list:
        self.queries.append(query)
        return []


def test_search_query_gains_framework_and_target_version(tmp_path) -> None:
    client = _RecordingSearch()
    tool = SearchTool(
        client,
        cache_dir=_settings(tmp_path).cache_dir,
        framework="Spring Boot",
        to_version="3.5.1",
        max_results=5,
    )
    assert ensure_version_anchor("datasource rename", "Spring Boot", "3.5.1").endswith(
        "Spring Boot 3.5.1"
    )
    tool.search("datasource rename")
    tool.search("Spring Boot 3.5.1 datasource rename")
    assert client.queries == [
        "datasource rename Spring Boot 3.5.1",
        "Spring Boot 3.5.1 datasource rename",
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://10.1.2.3/admin",
        "http://169.254.169.254/latest",
        "http://localhost/admin",
    ],
)
def test_fetch_refuses_private_targets(tmp_path, url: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"request was sent: {request.url}")

    fetcher = PageFetcher(
        cache_dir=_settings(tmp_path).cache_dir,
        max_chars=100,
        transport=httpx.MockTransport(handler),
    )
    result = fetcher.fetch(url)
    assert result.fetched_url is None
    assert result.text.startswith("Refused:")


def test_github_issue_uses_rest_client_and_token(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "gh-test-token")
    seen: dict[str, str] = {}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={
                "number": 10,
                "title": "Remove Foo",
                "body": "Use Bar instead of Foo",
                "labels": [{"name": "type: breaking"}],
                "html_url": "https://github.com/acme/widgets/issues/10",
            },
        )

    fetcher = PageFetcher(
        cache_dir=_settings(tmp_path).cache_dir,
        max_chars=2000,
        token="gh-test-token",
        transport=httpx.MockTransport(handler),
    )
    page = "https://github.com/acme/widgets/issues/10"
    result = fetcher.fetch(page)
    assert seen["url"] == "https://api.github.com/repos/acme/widgets/issues/10"
    assert seen["auth"] == "Bearer gh-test-token"
    assert "Remove Foo" in result.text
    assert "Use Bar instead of Foo" in result.text
    assert result.fetched_url == page
    fetcher.fetch(page)
    assert calls["n"] == 1


def test_html_fetch_is_stripped_and_capped(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><script>ignore()</script><p>" + ("Alpha " * 40) + "</p></html>",
        )

    fetcher = PageFetcher(
        cache_dir=_settings(tmp_path).cache_dir,
        max_chars=30,
        transport=httpx.MockTransport(handler),
    )
    result = fetcher.fetch("https://example.com/guide")
    assert "ignore" not in result.text
    assert "Alpha" in result.text
    assert len(result.text) <= 30
    assert result.fetched_url == "https://example.com/guide"


def test_tavily_status_codes_use_injected_poster_only() -> None:
    """Status mapping stays local. ``post`` never opens a socket."""
    calls = {"n": 0}

    def post(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, dict]:
        assert url.endswith("/search")
        assert payload["api_key"] == "not-a-real-key"
        calls["n"] += 1
        if calls["n"] < 3:
            return 429, {}
        return 432, {}

    client = TavilySearchClient("not-a-real-key", post=post, sleep=lambda _seconds: None)
    with pytest.raises(TavilyQuotaError) as raised:
        client.search("Spring Boot 3.5.1 change", max_results=5)
    assert raised.value.status_code == 432
    assert calls["n"] == 3

    def unauthorized(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, dict]:
        return 401, {}

    denied = TavilySearchClient("not-a-real-key", post=unauthorized, sleep=lambda _s: None)
    with pytest.raises(TavilyQuotaError) as auth:
        denied.search("query", max_results=1)
    assert auth.value.status_code == 401

    def ok(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, dict]:
        return 200, {
            "results": [
                {"title": "Guide", "url": "https://example.com/g", "content": "snippet"}
            ]
        }

    found = TavilySearchClient("not-a-real-key", post=ok, sleep=lambda _s: None).search(
        "query", max_results=1
    )
    assert found[0].snippet == "snippet"
    assert json.dumps(found[0].as_dict())

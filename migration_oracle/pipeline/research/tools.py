"""Search and page-fetch tools for one research row.

Search results are cached under ``ARTIFACT_CACHE_DIR/research/search/``.
GitHub issue, pull, and commit URLs are read through the GitHub REST helpers
from the enrichment stage (token and parsed body). Pages whose host resolves
to a private, loopback, or link-local address are refused before any request.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx

from migration_oracle.pipeline.extractors.base import GITHUB_HEADERS
from migration_oracle.pipeline.extractors.github_enrichment import (
    commit_api_url,
    issue_api_url,
    parse_github_commit,
    parse_github_issue,
)
from migration_oracle.pipeline.extractors.parsing import html_to_text

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_BACKOFF_SEC = (0.5, 1.0)
_GITHUB_ISSUE_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/(?:issues|pull)/(\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
_GITHUB_COMMIT_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/commit/([0-9a-f]{7,40})(?:[/?#].*)?$",
    re.IGNORECASE,
)
_LOCAL_NAMES = {"localhost", "localhost.localdomain"}
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")

Post = Callable[[str, dict, dict[str, str]], tuple[int, dict]]
Sleep = Callable[[float], None]


class TavilyQuotaError(Exception):
    """Tavily refused the key or the account is out of searches."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"Tavily HTTP {status_code}")
        self.status_code = status_code


class TavilySearchError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Tavily HTTP {status_code}")
        self.status_code = status_code


class ResearchQuotaExceeded(Exception):
    """The run must stop. Finished row dossiers stay in the row cache."""

    def __init__(self, framework: str, hop: tuple[str, str], done: int, total: int) -> None:
        self.framework = framework
        self.hop = hop
        self.done = done
        self.total = total
        self.message = (
            f"Tavily quota exhausted at {framework} {hop[0]}→{hop[1]} "
            f"({done}/{total} rows researched). Re-run after the quota resets; "
            f"finished rows are cached."
        )
        super().__init__(self.message)


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str

    def as_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class SearchClient(Protocol):
    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        """Return hits or raise :class:`TavilyQuotaError`."""


def ensure_version_anchor(query: str, framework: str, to_version: str) -> str:
    """Append ``<Framework> <to_version>`` when the model omitted either part."""
    text = query.strip()
    lowered = text.lower()
    if framework.lower() in lowered and to_version.lower() in lowered:
        return text
    return f"{text} {framework} {to_version}".strip()


class TavilySearchClient:
    """HTTP adapter for Tavily Search. Tests inject ``post`` and never call Tavily."""

    def __init__(
        self,
        api_key: str,
        *,
        post: Post | None = None,
        sleep: Sleep | None = None,
        timeout_sec: float = 30,
    ) -> None:
        self._api_key = api_key
        self._post = post
        self._sleep = sleep or _default_sleep
        self._timeout = timeout_sec

    def search(self, query: str, *, max_results: int) -> list[SearchHit]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
        }
        for attempt in range(3):
            status, body = self._send(payload)
            if status == 429 and attempt < 2:
                self._sleep(_BACKOFF_SEC[attempt])
                continue
            if status == 429 or status in {401, 432, 433}:
                raise TavilyQuotaError(status)
            if status != 200:
                raise TavilySearchError(status)
            hits: list[SearchHit] = []
            for item in body.get("results") or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "")
                if not url:
                    continue
                hits.append(
                    SearchHit(
                        title=str(item.get("title") or ""),
                        url=url,
                        snippet=str(item.get("content") or item.get("snippet") or ""),
                    )
                )
            return hits
        raise TavilyQuotaError(429)

    def _send(self, payload: dict) -> tuple[int, dict]:
        if self._post is not None:
            return self._post(TAVILY_SEARCH_URL, payload, {"Content-Type": "application/json"})
        response = httpx.post(
            TAVILY_SEARCH_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self._timeout,
        )
        try:
            body = response.json()
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return response.status_code, body


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


@dataclass(frozen=True)
class ToolOutput:
    text: str
    fetched_url: str | None = None


class SearchTool:
    def __init__(
        self,
        client: SearchClient,
        *,
        cache_dir: Path,
        framework: str,
        to_version: str,
        max_results: int,
        force: bool = False,
    ) -> None:
        self._client = client
        self._cache_dir = cache_dir / "research" / "search"
        self._framework = framework
        self._to_version = to_version
        self._max_results = max_results
        self._force = force

    def search(self, query: str) -> ToolOutput:
        anchored = ensure_version_anchor(query, self._framework, self._to_version)
        path = self._cache_dir / f"{_digest(anchored + '\n' + str(self._max_results))}.json"
        if not self._force and path.exists():
            return ToolOutput(text=path.read_text(encoding="utf-8"))
        try:
            hits = self._client.search(anchored, max_results=self._max_results)
        except TavilyQuotaError:
            raise
        except TavilySearchError as exc:
            return ToolOutput(text=f"Search failed: {exc}")
        payload = json.dumps([hit.as_dict() for hit in hits], ensure_ascii=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        return ToolOutput(text=payload)


class PageFetcher:
    """Fetch a public page, or a GitHub issue/pull/commit through the REST API."""

    def __init__(
        self,
        *,
        cache_dir: Path,
        max_chars: int,
        token: str = "",
        verify: bool = True,
        transport: httpx.BaseTransport | None = None,
        force: bool = False,
    ) -> None:
        self._cache_dir = cache_dir / "research" / "fetch"
        self._max_chars = max_chars
        self._token = token
        self._verify = verify
        self._transport = transport
        self._force = force

    def fetch(self, url: str) -> ToolOutput:
        cleaned = url.strip()
        refusal = refusal_reason(cleaned)
        if refusal:
            return ToolOutput(text=f"Refused: {refusal}")
        cache_path = self._cache_dir / _digest(cleaned)
        if not self._force and cache_path.exists():
            return ToolOutput(
                text=cache_path.read_text(encoding="utf-8"),
                fetched_url=cleaned,
            )
        try:
            text = self._download(cleaned)
        except httpx.HTTPError as exc:
            return ToolOutput(text=f"Fetch failed: {exc}")
        if not text.strip():
            return ToolOutput(text="Fetch failed: empty page")
        if len(text) > self._max_chars:
            text = text[: self._max_chars]
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
        return ToolOutput(text=text, fetched_url=cleaned)

    def _download(self, url: str) -> str:
        github = _github_api_request(url)
        headers = dict(GITHUB_HEADERS)
        if github is not None:
            target, kind = github
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
        else:
            target, kind = url, "page"
            headers = {"User-Agent": "migration-oracle", "Accept": "text/html, text/plain"}
        with httpx.Client(
            verify=self._verify,
            timeout=30.0,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            current = target
            for _ in range(5):
                refusal = refusal_reason(current)
                if refusal:
                    raise httpx.HTTPError(refusal)
                response = client.get(current, headers=headers)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise httpx.HTTPError(f"HTTP {response.status_code} without location")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise httpx.HTTPError(f"HTTP {response.status_code} for {current}")
                if kind == "issue":
                    return _render_issue(response.json(), url)
                if kind == "commit":
                    return _render_commit(response.json(), url)
                content_type = response.headers.get("content-type", "")
                return _page_text(response.text, content_type)
        raise httpx.HTTPError(f"too many redirects for {url}")


def refusal_reason(url: str) -> str | None:
    """Return a reason when the URL must not be fetched, else None."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "only public http(s) URLs are allowed"
    host = parsed.hostname.strip("[]").lower()
    if host in _LOCAL_NAMES or host.endswith(".local") or host.endswith(".internal"):
        return "URL resolves to a private, loopback, or link-local address"
    literal = _literal_ip(host)
    if literal is not None:
        if _is_blocked(literal):
            return "URL resolves to a private, loopback, or link-local address"
        return None
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None
    for info in infos:
        address = info[4][0]
        ip = _literal_ip(address)
        if ip is not None and _is_blocked(ip):
            return "URL resolves to a private, loopback, or link-local address"
    return None


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if isinstance(ip, ipaddress.IPv4Address) and ip in _SHARED_ADDRESS_SPACE:
        return True
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _github_api_request(url: str) -> tuple[str, str] | None:
    issue = _GITHUB_ISSUE_RE.match(url.strip())
    if issue:
        repo = f"{issue.group(1)}/{issue.group(2)}"
        return issue_api_url(repo, int(issue.group(3))), "issue"
    commit = _GITHUB_COMMIT_RE.match(url.strip())
    if commit:
        repo = f"{commit.group(1)}/{commit.group(2)}"
        return commit_api_url(repo, commit.group(3)), "commit"
    return None


def _render_issue(payload: object, page_url: str) -> str:
    if not isinstance(payload, dict):
        raise httpx.HTTPError("GitHub issue payload is not an object")
    number = int(payload.get("number") or _GITHUB_ISSUE_RE.match(page_url).group(3))  # type: ignore[union-attr]
    issue = parse_github_issue(payload, number=number)
    labels = ", ".join(issue["labels"])
    lines = [issue["title"], labels, issue["body"], issue["html_url"] or page_url]
    return "\n".join(line for line in lines if line)


def _render_commit(payload: object, page_url: str) -> str:
    if not isinstance(payload, dict):
        raise httpx.HTTPError("GitHub commit payload is not an object")
    match = _GITHUB_COMMIT_RE.match(page_url)
    sha = match.group(3) if match else str(payload.get("sha") or "")
    repo = f"{match.group(1)}/{match.group(2)}" if match else ""
    commit = parse_github_commit(payload, sha=sha, repo=repo)
    lines = [
        commit["header"],
        commit["body"],
        commit["breaking"],
        commit["deprecated"],
        commit["html_url"] or page_url,
    ]
    return "\n".join(line for line in lines if line)


def _page_text(body: str, content_type: str) -> str:
    looks_html = "html" in content_type.lower() or "<html" in body[:500].lower() or "<p" in body[:500].lower()
    if not looks_html:
        return body
    text = html_to_text(body)
    if text.strip():
        return text
    from bs4 import BeautifulSoup

    return BeautifulSoup(body, "html.parser").get_text("\n", strip=True)


def github_token() -> str:
    return os.environ.get("GITHUB_TOKEN", "").strip()


def ssl_verify() -> bool:
    raw = os.environ.get("SSL_VERIFY", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

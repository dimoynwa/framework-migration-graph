"""Abstract base extractor and shared HTTP client."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx

from migration_oracle import config
from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.github_enrichment import (
    GitHubCommit,
    GitHubIssue,
    commit_api_url,
    issue_api_url,
    parse_github_commit,
    parse_github_issue,
)

__all__ = [
    "BaseExtractor",
    "DocumentedChange",
    "ExtractionResult",
    "HopContext",
    "HopResult",
    "is_jboss_ga_version",
    "is_infinispan_ga_version",
    "is_spring_boot_ga_version",
]
from migration_oracle.pipeline.extractors.parsing import (
    compute_hops,
    enters_new_minor_line,
    is_version_alias,
    releases_covered_by_hop,
    resolve_version_alias,
    select_hop_versions,
    validate_hop_granularity,
)

logger = logging.getLogger(__name__)


def _unique(items: Iterable) -> list:
    ordered: list = []
    seen: set = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


class _GitHubRateLimit(Exception):
    """Primary GitHub rate limit (403/429 with ``X-RateLimit-Remaining: 0``)."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"GitHub enrichment API rate limit HTTP {status_code}")
        self.status_code = status_code


@dataclass(frozen=True)
class HopContext:
    """Planning metadata for one version hop passed to :meth:`BaseExtractor.extract`."""

    from_version: str
    to_version: str
    granularity: str = "patch"
    #: Releases whose notes document this hop (intermediate milestones/patches
    #: on the target line plus ``to_version``). Empty means ``(to_version,)``.
    covered_versions: tuple[str, ...] = ()

    @property
    def release_versions(self) -> tuple[str, ...]:
        """Releases to read notes from, oldest first; always ends at ``to_version``."""
        return self.covered_versions or (self.to_version,)

    @property
    def enters_minor_line(self) -> bool:
        """True when this hop crosses into a new ``major.minor`` line."""
        return enters_new_minor_line(self.from_version, self.to_version)

    @property
    def is_patch_step(self) -> bool:
        """True when the hop stays inside one minor line (``3.3.1 → 3.3.2``)."""
        return not self.enters_minor_line


@dataclass
class HopResult:
    """Extraction output for a single planned version hop."""

    context: HopContext
    result: ExtractionResult

    @property
    def from_version(self) -> str:
        return self.context.from_version

    @property
    def to_version(self) -> str:
        return self.context.to_version

    @property
    def changes(self) -> list[DocumentedChange]:
        return self.result.changes

# Matches GA releases for the JBoss/Red Hat Maven ecosystem: X.Y.Z.Final
_JBOSS_GA_PATTERN = re.compile(r"^\d+\.\d+\.\d+\.Final$")

# Matches GA releases for Spring Boot: plain X.Y.Z with no suffix
_SPRING_GA_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def is_jboss_ga_version(version: str) -> bool:
    """Return True only for JBoss-ecosystem GA releases (X.Y.Z.Final).

    Rejects: Alpha, Beta, CR, SP (service pack is kept — see NOTE below).
    Used by: WildFly (already filtered), Hibernate ORM, RESTEasy, WildFly Elytron.

    NOTE: Service pack versions like X.Y.Z.SP1 are also excluded by this filter.
    SP releases are rare and do not have standalone GitHub release pages. If a
    user needs to include an SP version in their range they must use
    JBOSS_SKIP_PRERELEASE=0 to disable the filter entirely.
    """
    return bool(_JBOSS_GA_PATTERN.match(version))


def is_infinispan_ga_version(version: str) -> bool:
    """Return True for GA Infinispan releases.

    Infinispan changed version conventions at 16.x:
    - 15.x and older: GA releases end in .Final (e.g. 15.0.20.Final)
    - 16.x and newer: GA releases are plain X.Y.Z (e.g. 16.2.0)

    Rejects: X.Y.Z.Dev01, X.Y.Z.Dev02, X.Y.Z.Beta1, X.Y.Z.CR1, etc.
    16.x lines using .Final (e.g. 16.2.0.Final) are rejected as non-GA.
    """
    if _SPRING_GA_PATTERN.match(version):
        return True
    if _JBOSS_GA_PATTERN.match(version):
        major = int(version.split(".", maxsplit=1)[0])
        return major < 16
    return False


def is_spring_boot_ga_version(version: str) -> bool:
    """Return True only for Spring Boot GA releases (plain X.Y.Z, no suffix).

    Rejects: 4.1.0-M4, 4.1.0-RC1, 4.0.0-SNAPSHOT, 3.3.0-M2, etc.
    Required because as of Spring Boot 4.0.0-M1, milestone and RC builds
    are published to Maven Central alongside GA releases.
    """
    return bool(_SPRING_GA_PATTERN.match(version))


GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class BaseExtractor(ABC):
    """Async framework extractor with URL-level caching."""

    framework_key: str = ""
    display_name: str = ""
    default_timeout: float = 30.0

    def __init__(self) -> None:
        self._github_token = config.GITHUB_TOKEN
        self._ssl_verify = config.SSL_VERIFY
        self._jira_max_concurrent = config.JIRA_MAX_CONCURRENT
        self._github_enrich_max_concurrent = max(1, config.GITHUB_ENRICH_MAX_CONCURRENT)
        self._github_enrich_rate_limited = False
        self._github_enrich_misses: set[str] = set()
        self._redhat_delay = config.REDHAT_DOCS_DELAY_SEC
        self._cache: dict[str, str | bytes] = {}
        headers = dict(GITHUB_HEADERS)
        if self._github_token:
            headers["Authorization"] = f"Bearer {self._github_token}"
        self._client = httpx.AsyncClient(
            verify=self._ssl_verify,
            timeout=httpx.Timeout(self.default_timeout),
            headers=headers,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> BaseExtractor:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    @property
    def jira_max_concurrent(self) -> int:
        return self._jira_max_concurrent

    @property
    def redhat_docs_delay_sec(self) -> float:
        return self._redhat_delay

    def _http_get_cached(self, url: str, *, timeout: float | None = None) -> str:
        """Sync URL fetch with instance cache; returns '' on any failure."""
        if url in self._cache:
            cached = self._cache[url]
            return cached.decode() if isinstance(cached, bytes) else cached
        try:
            response = httpx.get(
                url,
                timeout=timeout or self.default_timeout,
                verify=self._ssl_verify,
                follow_redirects=True,
            )
            if response.status_code != 200:
                return ""
            text = response.text
            self._cache[url] = text
            return text
        except Exception:
            return ""

    async def _fetch_maven_versions(self, url: str) -> list[str]:
        xml = await self.fetch(url)
        from migration_oracle.pipeline.extractors.parsing import (
            parse_maven_metadata_versions,
        )

        return parse_maven_metadata_versions(xml)

    def get_available_versions(self) -> list[str]:
        """Sync wrapper for version discovery (used by tests and verification)."""
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.discover_versions())
        raise RuntimeError("get_available_versions() cannot run inside a running event loop")

    async def fetch(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        accept_status: set[int] | None = None,
    ) -> str:
        if url in self._cache:
            cached = self._cache[url]
            return cached.decode() if isinstance(cached, bytes) else cached

        try:
            response = await self._client.get(
                url, timeout=timeout or self.default_timeout, headers=headers
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"{self.display_name} extraction failed for URL {url}: {exc}"
            ) from exc

        ok = accept_status or {200}
        if response.status_code not in ok:
            raise RuntimeError(
                f"{self.display_name} HTTP {response.status_code} for {url}"
            )
        text = response.text
        self._cache[url] = text
        return text

    async def fetch_json(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        accept_status: set[int] | None = None,
    ) -> Any:
        text = await self.fetch(
            url, timeout=timeout, headers=headers, accept_status=accept_status
        )
        import json

        return json.loads(text)

    async def fetch_first_ok(
        self,
        urls: list[str],
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        last_error: Exception | None = None
        for url in urls:
            try:
                if url in self._cache:
                    cached = self._cache[url]
                    return url, cached.decode() if isinstance(cached, bytes) else cached
                response = await self._client.get(
                    url, timeout=timeout or self.default_timeout, headers=headers
                )
                if response.status_code == 200:
                    self._cache[url] = response.text
                    return url, response.text
                last_error = RuntimeError(
                    f"{self.display_name} HTTP {response.status_code} for {url}"
                )
            except (RuntimeError, httpx.HTTPError) as exc:
                last_error = exc if isinstance(exc, RuntimeError) else RuntimeError(str(exc))
        raise RuntimeError(
            f"{self.display_name}: no successful response from {urls!r}"
        ) from last_error

    async def fetch_github_release(
        self, repo: str, version: str, tag_candidates: list[str]
    ) -> tuple[str, str]:
        api_urls = [
            f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
            for tag in tag_candidates
        ]
        try:
            url, _ = await self.fetch_first_ok(api_urls)
            data = await self.fetch_json(url)
            body = data.get("body") or ""
            html_url = data.get("html_url") or url
            if body.strip():
                return html_url, body
        except RuntimeError:
            pass

        for tag in tag_candidates:
            page_url = f"https://github.com/{repo}/releases/tag/{tag}"
            try:
                html = await self.fetch(
                    page_url,
                    headers={"Accept": "text/html"},
                    accept_status={200},
                )
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(html, "html.parser")
                article = soup.find("div", class_="markdown-body") or soup.find(
                    "div", {"data-test-selector": "release-body"}
                )
                if article:
                    text = article.get_text("\n", strip=True)
                    if text.strip():
                        return page_url, text
            except RuntimeError:
                continue

        raise RuntimeError(
            f"{self.display_name}: no release body for {version!r} "
            f"(tags tried: {tag_candidates!r})"
        )

    async def fetch_github_issues(
        self, repo: str, numbers: Iterable[int]
    ) -> dict[int, GitHubIssue]:
        """Fetch GitHub issues and pull requests by number.

        Per-item failures (404, 410, 422, timeout, bad JSON) are logged at DEBUG
        and omitted. A primary rate-limit response stops further issue and commit
        requests for the rest of this extractor's run.
        """
        ordered = _unique(numbers)
        return await self._fetch_github_map(
            ordered,
            url_for=lambda number: issue_api_url(repo, number),
            parse=lambda payload, number: parse_github_issue(payload, number=number),
        )

    async def fetch_github_commits(
        self, repo: str, shas: Iterable[str]
    ) -> dict[str, GitHubCommit]:
        """Fetch GitHub commits by SHA. Same failure and rate-limit rules as issues."""
        ordered = _unique(sha.lower() for sha in shas)
        return await self._fetch_github_map(
            ordered,
            url_for=lambda sha: commit_api_url(repo, sha),
            parse=lambda payload, sha: parse_github_commit(payload, sha=sha, repo=repo),
        )

    async def _fetch_github_map(self, keys: list, *, url_for, parse) -> dict:
        if not keys:
            return {}
        results: dict = {}
        semaphore = asyncio.Semaphore(self._github_enrich_max_concurrent)

        async def load(key: object) -> None:
            url = url_for(key)
            cached = self._cached_text(url)
            if cached is not None:
                try:
                    results[key] = parse(json.loads(cached), key)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    logger.debug("GitHub enrichment parse failed for %s: %s", url, exc)
                return
            if url in self._github_enrich_misses or self._github_enrich_rate_limited:
                return
            async with semaphore:
                if url in self._github_enrich_misses or self._github_enrich_rate_limited:
                    return
                try:
                    payload = await self._fetch_github_payload(url)
                except _GitHubRateLimit as exc:
                    self._stop_github_enrichment(exc.status_code)
                    return
                except (RuntimeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                    logger.debug("GitHub enrichment fetch failed for %s: %s", url, exc)
                    return
                try:
                    results[key] = parse(payload, key)
                except (TypeError, ValueError) as exc:
                    logger.debug("GitHub enrichment parse failed for %s: %s", url, exc)

        await asyncio.gather(*(load(key) for key in keys))
        return results

    def _cached_text(self, url: str) -> str | None:
        if url not in self._cache:
            return None
        cached = self._cache[url]
        return cached.decode() if isinstance(cached, bytes) else cached

    async def _fetch_github_payload(self, url: str) -> dict:
        try:
            response = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise RuntimeError(str(exc)) from exc

        if response.status_code in (403, 429):
            remaining = response.headers.get("X-RateLimit-Remaining", "")
            if remaining.strip() == "0":
                raise _GitHubRateLimit(response.status_code)
            raise RuntimeError(f"HTTP {response.status_code} for {url}")

        if response.status_code in (404, 410, 422):
            self._github_enrich_misses.add(url)
            raise RuntimeError(f"HTTP {response.status_code} for {url}")

        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code} for {url}")

        self._cache[url] = response.text
        payload = json.loads(response.text)
        if not isinstance(payload, dict):
            raise TypeError(f"GitHub payload for {url} is not an object")
        return payload

    def _stop_github_enrichment(self, status_code: int) -> None:
        if self._github_enrich_rate_limited:
            return
        self._github_enrich_rate_limited = True
        logger.warning(
            "GitHub enrichment API rate limit exhausted "
            "(HTTP %s, X-RateLimit-Remaining: 0); "
            "skipping further GitHub enrichment requests for this run",
            status_code,
        )

    @abstractmethod
    async def discover_versions(self) -> list[str]:
        """Return ordered versions available for this framework."""

    @abstractmethod
    async def extract(
        self,
        from_version: str,
        to_version: str,
        *,
        hop_context: HopContext | None = None,
    ) -> ExtractionResult:
        """
        Extract documented changes for a single version hop.

        ``hop_context`` describes how the hop was planned (granularity and
        whether it crosses into a new minor line). Extractors that have
        minor-line-only sources (migration guides, wiki release notes) use it to
        avoid re-attaching the same prose to every patch hop; it is optional so
        that extractors and callers may ignore it.
        """

    async def plan_hops(
        self,
        from_version: str,
        to_version: str,
        granularity: str = "patch",
    ) -> list[HopContext]:
        """Discover releases and plan the hop boundaries for ``granularity``."""
        granularity = validate_hop_granularity(granularity)
        versions = await self.discover_versions()
        from_version = resolve_version_alias(versions, from_version)
        to_version = resolve_version_alias(versions, to_version)
        boundaries = select_hop_versions(
            versions, from_version, to_version, granularity
        )
        return [
            HopContext(
                from_version=hop_from,
                to_version=hop_to,
                granularity=granularity,
                covered_versions=releases_covered_by_hop(versions, hop_from, hop_to),
            )
            for hop_from, hop_to in compute_hops(boundaries)
        ]

    async def resolve_versions(
        self, from_version: str, to_version: str
    ) -> tuple[str, str]:
        """Resolve ``latest`` / ``latest-ga`` / ``X.Y.Z-SNAPSHOT`` to published releases."""
        if not (is_version_alias(from_version) or is_version_alias(to_version)):
            return from_version, to_version
        versions = await self.discover_versions()
        return (
            resolve_version_alias(versions, from_version),
            resolve_version_alias(versions, to_version),
        )

    async def extract_contexts(
        self,
        contexts: list[HopContext],
        *,
        per_hop_range_metadata: bool = False,
    ) -> list[HopResult]:
        """
        Extract the given planned hops and return one :class:`HopResult` each.

        A hop whose extraction fails is logged and returned with an empty change
        list, so a broken release page does not abort the whole range. When
        ``per_hop_range_metadata`` is set, range-level metadata (BOM diff) is
        computed for each hop instead of only for the outer range — this is what
        makes patch-level dependency and CVE deltas visible.
        """
        hop_results: list[HopResult] = []

        for context in contexts:
            try:
                result = await self.extract(
                    context.from_version, context.to_version, hop_context=context
                )
            except RuntimeError as exc:
                logger.warning(
                    "%s: skipping hop %s → %s: %s",
                    self.display_name,
                    context.from_version,
                    context.to_version,
                    exc,
                )
                hop_results.append(
                    HopResult(context=context, result=ExtractionResult(changes=[]))
                )
                continue
            if per_hop_range_metadata:
                try:
                    result.metadata.update(
                        await self.build_range_metadata(
                            context.from_version, context.to_version
                        )
                    )
                except RuntimeError as exc:
                    logger.warning(
                        "%s: range metadata failed for hop %s → %s: %s",
                        self.display_name,
                        context.from_version,
                        context.to_version,
                        exc,
                    )
            hop_results.append(HopResult(context=context, result=result))

        return hop_results

    async def extract_hops(
        self,
        from_version: str,
        to_version: str,
        *,
        granularity: str = "patch",
        per_hop_range_metadata: bool = False,
    ) -> list[HopResult]:
        """Plan hops for ``granularity`` and extract each of them separately."""
        contexts = await self.plan_hops(from_version, to_version, granularity)
        return await self.extract_contexts(
            contexts, per_hop_range_metadata=per_hop_range_metadata
        )

    async def extract_range(
        self, from_version: str, to_version: str, granularity: str = "patch"
    ) -> tuple[ExtractionResult, list[tuple[str, str, list[DocumentedChange]]]]:
        """Discover versions, extract each hop, and return aggregated result."""
        hop_results = await self.extract_hops(
            from_version, to_version, granularity=granularity
        )
        all_changes: list[DocumentedChange] = []
        metadata: dict = {}
        hop_changes: list[tuple[str, str, list[DocumentedChange]]] = []

        for hop in hop_results:
            hop_changes.append((hop.from_version, hop.to_version, list(hop.changes)))
            all_changes.extend(hop.changes)
            metadata.update(hop.result.metadata)

        if not all_changes:
            raise RuntimeError(
                f"{self.display_name}: no changes extracted for "
                f"{from_version} → {to_version}"
            )

        range_meta = await self.build_range_metadata(from_version, to_version)
        metadata.update(range_meta)
        return ExtractionResult(changes=all_changes, metadata=metadata), hop_changes

    async def build_range_metadata(
        self, from_version: str, to_version: str
    ) -> dict:
        """Optional range-level metadata hook (e.g. BOM diff)."""
        return {}

    async def sleep_redhat(self) -> None:
        if self._redhat_delay > 0:
            await asyncio.sleep(self._redhat_delay)

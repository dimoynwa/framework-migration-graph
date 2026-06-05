"""Abstract base extractor and shared HTTP client."""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from migration_oracle import config
from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.parsing import (
    compute_hops,
    versions_in_range,
)

logger = logging.getLogger(__name__)

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

    @abstractmethod
    async def discover_versions(self) -> list[str]:
        """Return ordered versions available for this framework."""

    @abstractmethod
    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        """Extract documented changes for a single version hop."""

    async def extract_range(
        self, from_version: str, to_version: str
    ) -> tuple[ExtractionResult, list[tuple[str, str, list[DocumentedChange]]]]:
        """Discover versions, extract each hop, and return aggregated result."""
        versions = await self.discover_versions()
        in_range = versions_in_range(versions, from_version, to_version)
        hops = compute_hops(in_range)
        all_changes: list[DocumentedChange] = []
        metadata: dict = {}
        hop_changes: list[tuple[str, str, list[DocumentedChange]]] = []

        for hop_from, hop_to in hops:
            try:
                result = await self.extract(hop_from, hop_to)
            except RuntimeError as exc:
                logger.warning(
                    "%s: skipping hop %s → %s: %s",
                    self.display_name,
                    hop_from,
                    hop_to,
                    exc,
                )
                hop_changes.append((hop_from, hop_to, []))
                continue
            hop_changes.append((hop_from, hop_to, result.changes))
            all_changes.extend(result.changes)
            metadata.update(result.metadata)

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

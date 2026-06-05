"""Angular HTTP extractor."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.parsing import (
    filter_release_versions,
    parse_github_release_text,
)

logger = logging.getLogger(__name__)

NPM_REGISTRY_URL = "https://registry.npmjs.org/@angular/core"
CHANGELOG_URL = (
    "https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md"
)
_BLOG_LINK_RE = re.compile(
    r"https://(?:blog\.)?angular\.dev/[^\s\)]+"
)


def _extract_changelog_section(changelog_text: str, version: str) -> str:
    """Extract the CHANGELOG.md section for a given version."""
    anchor = f'<a name="{version}"></a>'
    start = changelog_text.find(anchor)
    if start == -1:
        return ""

    next_anchor_start = changelog_text.find('<a name="', start + len(anchor))
    if next_anchor_start == -1:
        section = changelog_text[start:]
    else:
        section = changelog_text[start:next_anchor_start]

    return section.strip()


class AngularExtractor(BaseExtractor):
    framework_key = "angular"
    display_name = "Angular"

    async def discover_versions(self) -> list[str]:
        data = await self.fetch_json(NPM_REGISTRY_URL)
        versions = list(data.get("versions", {}).keys())
        return filter_release_versions(versions, final_only=False)

    async def _get_changelog(self) -> str:
        """Fetch Angular CHANGELOG.md (cached at most once per run)."""
        if CHANGELOG_URL in self._cache:
            cached = self._cache[CHANGELOG_URL]
            return cached.decode() if isinstance(cached, bytes) else cached
        try:
            return await self.fetch(CHANGELOG_URL, accept_status={200})
        except RuntimeError as exc:
            logger.warning("Angular CHANGELOG.md fetch failed: %s", exc)
            return ""

    def _fetch_blog_summary(self, url: str) -> str:
        """Fetch a blog page and extract a text summary."""
        try:
            html = self._http_get_cached(url)
            if not html:
                return ""
            soup = BeautifulSoup(html, "html.parser")

            tag = soup.find("meta", attrs={"name": "description"})
            if tag and tag.get("content"):
                return tag["content"].strip()

            tag = soup.find("meta", attrs={"property": "og:description"})
            if tag and tag.get("content"):
                return tag["content"].strip()

            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) >= 80:
                    return text

            return ""
        except Exception:
            return ""

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        tag_candidates = [f"v{to_version}", to_version]
        source_url, body = await self.fetch_github_release(
            "angular/angular", to_version, tag_candidates
        )
        changelog_text = await self._get_changelog()
        changelog_section = _extract_changelog_section(changelog_text, to_version)
        if changelog_section:
            body = body + "\n\n" + changelog_section

        changes = parse_github_release_text(body, source_url)
        raw_blog_urls = sorted(set(_BLOG_LINK_RE.findall(body)))
        blog_insights = [
            {"url": url, "summary": self._fetch_blog_summary(url)}
            for url in raw_blog_urls
        ]
        if not changes:
            raise RuntimeError(
                f"Angular: no changes parsed for hop {from_version} → {to_version} "
                f"from {source_url}"
            )
        metadata = {"blog_insights": blog_insights}
        return ExtractionResult(changes=changes, metadata=metadata)

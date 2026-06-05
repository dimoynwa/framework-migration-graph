"""Spring Boot HTTP extractor."""

from __future__ import annotations

import logging
import re

from migration_oracle import config
from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import (
    BaseExtractor,
    is_spring_boot_ga_version,
)
from migration_oracle.pipeline.extractors.parsing import (
    bom_diff,
    filter_release_versions,
    html_to_text,
    parse_github_release_text as _parse_github_release_text,
    parse_maven_metadata_versions,
    parse_pom_dependencies,
    parse_version,
    version_key,
)

logger = logging.getLogger(__name__)

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/springframework/boot/"
    "spring-boot-dependencies/maven-metadata.xml"
)
POM_URL_TEMPLATE = (
    "https://repo1.maven.org/maven2/org/springframework/boot/"
    "spring-boot-dependencies/{version}/spring-boot-dependencies-{version}.pom"
)
_WIKI_URL_TEMPLATE = (
    "https://github.com/spring-projects/spring-boot/wiki/"
    "Spring-Boot-{major}.{minor}-Release-Notes"
)
_DEPENDENCY_UPGRADES_HEADING_RE = re.compile(
    r"^#*\s*(?:🔨\s*|:\s*hammer:\s*)?dependency\s+upgrades?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_dependency_upgrades(body: str) -> str:
    """Remove the Dependency Upgrades section from a release body."""
    match = _DEPENDENCY_UPGRADES_HEADING_RE.search(body)
    if not match:
        return body
    start = match.start()
    remainder = body[match.end() :]
    next_heading = re.search(r"^#+\s", remainder, re.MULTILINE)
    end = match.end() + (next_heading.start() if next_heading else len(remainder))
    return body[:start].rstrip() + body[end:]


def parse_github_release_text(
    body: str, source_url: str = ""
) -> list:
    """Parse Spring Boot release text, suppressing Dependency Upgrades lines."""
    return _parse_github_release_text(
        _strip_dependency_upgrades(body), source_url
    )


class SpringBootExtractor(BaseExtractor):
    framework_key = "spring-boot"
    display_name = "Spring Boot"

    def parse_github_release_text(self, body: str, source_url: str = "") -> list:
        return parse_github_release_text(body, source_url)

    async def discover_versions(self) -> list[str]:
        xml = await self.fetch(MAVEN_METADATA_URL)
        raw_versions = parse_maven_metadata_versions(xml)
        if config.SPRING_INCLUDE_PRERELEASE:
            seen: set[str] = set()
            versions = []
            for v in raw_versions:
                if v and v not in seen:
                    seen.add(v)
                    versions.append(v)
            versions.sort(key=version_key)
            return versions
        versions = [v for v in raw_versions if is_spring_boot_ga_version(v)]
        return filter_release_versions(versions, final_only=False)

    async def _fetch_wiki_release_notes(self, to_version: str) -> str:
        """Fetch wiki release notes for the minor series of to_version."""
        major, minor, _, _ = parse_version(to_version)
        url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
        try:
            html = await self.fetch(url, accept_status={200})
        except RuntimeError as exc:
            logger.warning("Spring Boot wiki page fetch failed: %s", exc)
            return ""
        if not html.strip():
            return ""
        return html_to_text(html)

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        tag_candidates = [f"v{to_version}", to_version]
        source_url, body = await self.fetch_github_release(
            "spring-projects/spring-boot", to_version, tag_candidates
        )
        wiki_content = await self._fetch_wiki_release_notes(to_version)
        if wiki_content:
            body = body + "\n\n" + wiki_content
        changes = self.parse_github_release_text(body, source_url)
        if not changes:
            raise RuntimeError(
                f"Spring Boot: no changes parsed for hop {from_version} → {to_version} "
                f"from {source_url}"
            )
        return ExtractionResult(changes=changes, metadata={})

    async def build_range_metadata(
        self, from_version: str, to_version: str
    ) -> dict:
        from_url = POM_URL_TEMPLATE.format(version=from_version)
        to_url = POM_URL_TEMPLATE.format(version=to_version)
        from_pom, to_pom = await self.fetch(from_url), await self.fetch(to_url)
        diff = bom_diff(
            parse_pom_dependencies(from_pom), parse_pom_dependencies(to_pom)
        )
        return {"bom_diff": diff}

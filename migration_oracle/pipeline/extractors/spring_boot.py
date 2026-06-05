"""Spring Boot HTTP extractor."""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from migration_oracle import config
from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.base import (
    BaseExtractor,
    is_spring_boot_ga_version,
)
from migration_oracle.pipeline.extractors.parsing import (
    bom_diff,
    classify_statement,
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
_UPGRADE_H2_RE = re.compile(r"^##\s+Upgrading from", re.IGNORECASE | re.MULTILINE)
_H2_RE = re.compile(r"^##\s+", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)


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


def parse_wiki_upgrade_section(
    wiki_text: str, source_url: str
) -> list[DocumentedChange]:
    """
    Extract DocumentedChange entries from the 'Upgrading from' prose section of a
    Spring Boot wiki release notes page (already converted to plain text via html_to_text).

    Each H3 subsection (e.g. 'Actuator heapdump Endpoint') becomes one entry whose
    statement is 'Title: {h3}. {prose}' and whose type/confidence are determined by
    classify_statement with the H2 section hint 'Upgrading from Spring Boot'.
    """
    upgrade_match = _UPGRADE_H2_RE.search(wiki_text)
    if not upgrade_match:
        return []

    section_start = upgrade_match.end()
    next_h2 = _H2_RE.search(wiki_text, section_start)
    section_text = (
        wiki_text[section_start:next_h2.start()]
        if next_h2
        else wiki_text[section_start:]
    )

    changes: list[DocumentedChange] = []
    h3_matches = list(_H3_RE.finditer(section_text))

    for idx, h3_match in enumerate(h3_matches):
        heading = h3_match.group(1).strip()
        body_start = h3_match.end()
        body_end = (
            h3_matches[idx + 1].start()
            if idx + 1 < len(h3_matches)
            else len(section_text)
        )
        prose_lines = [
            line.strip()
            for line in section_text[body_start:body_end].splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        prose = " ".join(prose_lines)
        if not prose:
            continue
        statement = f"{heading}: {prose}"
        change_type, confidence = classify_statement(
            "Upgrading from Spring Boot", statement
        )
        changes.append(
            DocumentedChange(
                type=change_type,
                confidence=confidence,
                source_url=source_url,
                statement=statement,
            )
        )
    return changes


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

    async def _fetch_wiki_release_notes(
        self, to_version: str
    ) -> tuple[str, list[DocumentedChange]]:
        """
        Returns (wiki_text_for_bullet_parsing, prose_upgrade_changes).
        Both values are empty/[] on any fetch failure. Never raises.
        """
        major, minor, _, _ = parse_version(to_version)
        url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
        try:
            html = await self.fetch(url, accept_status={200})
        except RuntimeError as exc:
            logger.warning("Spring Boot wiki page fetch failed: %s", exc)
            return "", []
        if not html.strip():
            return "", []
        soup = BeautifulSoup(html, "html.parser")
        wiki_body = soup.select_one("#wiki-body .markdown-body")
        if not wiki_body:
            logger.warning(
                "Spring Boot wiki: #wiki-body .markdown-body not found at %s — "
                "falling back to full-page extraction",
                url,
            )
            wiki_text = html_to_text(html)
        else:
            wiki_text = html_to_text(str(wiki_body))
            if not wiki_text.strip():
                wiki_text = wiki_body.get_text("\n", strip=False)
        wiki_text = _strip_dependency_upgrades(wiki_text)
        prose_changes = parse_wiki_upgrade_section(wiki_text, url)
        return wiki_text, prose_changes

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        tag_candidates = [f"v{to_version}", to_version]
        source_url, body = await self.fetch_github_release(
            "spring-projects/spring-boot", to_version, tag_candidates
        )
        wiki_text, wiki_prose_changes = await self._fetch_wiki_release_notes(to_version)

        changes = self.parse_github_release_text(body, source_url)

        if wiki_text:
            major, minor, _, _ = parse_version(to_version)
            wiki_url = _WIKI_URL_TEMPLATE.format(major=major, minor=minor)
            wiki_bullet_changes = self.parse_github_release_text(wiki_text, wiki_url)
            changes = changes + wiki_bullet_changes + wiki_prose_changes

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

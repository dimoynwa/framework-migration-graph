"""WildFly HTTP extractor with Jira enrichment."""

from __future__ import annotations

from migration_oracle import config
from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.parsing import (
    apply_cli_hints,
    filter_release_versions,
    html_to_text,
    normalize_wildfly_maven_version,
    parse_github_release_text,
    parse_maven_metadata_versions,
    parse_version,
)
from migration_oracle.pipeline.extractors.wildfly_jira import (
    JIRA_KEY_RE,
    enrich_with_jira,
    normalize_jira_url as normalize_jira_host,
)

__all__ = ["WildFlyExtractor", "JIRA_KEY_RE", "normalize_jira_host"]

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/wildfly/wildfly-dist/maven-metadata.xml"
)


class WildFlyExtractor(BaseExtractor):
    framework_key = "wildfly"
    display_name = "WildFly"

    async def discover_versions(self) -> list[str]:
        xml = await self.fetch(MAVEN_METADATA_URL)
        raw = parse_maven_metadata_versions(xml)
        if config.JBOSS_SKIP_PRERELEASE:
            raw = [v for v in raw if v.endswith(".Final")]
        normalized = [normalize_wildfly_maven_version(v) for v in raw]
        return filter_release_versions(normalized, final_only=False)

    async def _fetch_release_body(self, version: str) -> tuple[str, str]:
        tag = f"{version}.Final"
        repo = "wildfly/wildfly"
        try:
            return await self.fetch_github_release(repo, version, [tag])
        except RuntimeError:
            pass

        major, _, _, _ = parse_version(version)
        guide_url = f"https://docs.wildfly.org/{major}/Migration_Guide.html"
        try:
            html = await self.fetch(guide_url, timeout=60.0)
            return guide_url, html_to_text(html)
        except RuntimeError:
            fallback = "https://www.wildfly.org/news/"
            html = await self.fetch(fallback, timeout=60.0)
            return fallback, html_to_text(html)

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        source_url, body = await self._fetch_release_body(to_version)
        changes = parse_github_release_text(body, source_url)
        try:
            changes = await enrich_with_jira(self, body, changes)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "WildFly Jira enrichment skipped: %s", exc
            )
        changes = apply_cli_hints(changes)
        if not changes:
            raise RuntimeError(
                f"WildFly: no changes parsed for hop {from_version} → {to_version}"
            )
        return ExtractionResult(changes=changes, metadata={})

"""Hibernate ORM HTTP extractor."""

from __future__ import annotations

from migration_oracle import config
from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor, is_jboss_ga_version
from migration_oracle.pipeline.extractors.parsing import (
    filter_release_versions,
    parse_asciidoc_migration_guide,
    parse_markdown_statements,
    parse_maven_metadata_versions,
    parse_version,
)

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/hibernate/orm/hibernate-core/maven-metadata.xml"
)
ASCIIDOC_URL = (
    "https://raw.githubusercontent.com/hibernate/hibernate-orm/{tag}/migration-guide.adoc"
)


class HibernateExtractor(BaseExtractor):
    framework_key = "hibernate"
    display_name = "Hibernate ORM"

    async def discover_versions(self) -> list[str]:
        xml = await self.fetch(MAVEN_METADATA_URL)
        raw_versions = parse_maven_metadata_versions(xml)
        if config.JBOSS_SKIP_PRERELEASE:
            versions = [v for v in raw_versions if is_jboss_ga_version(v)]
        else:
            versions = raw_versions
        from migration_oracle.pipeline.extractors.parsing import (
            normalize_wildfly_maven_version,
        )

        normalized = [normalize_wildfly_maven_version(v) for v in versions]
        return filter_release_versions(normalized, final_only=False)

    async def _fetch_guide(self, version: str) -> tuple[str, str]:
        major, _, _, _ = parse_version(version)
        # tag_candidates: plain {version} first, {version}.Final as fallback
        if major >= 6:
            for tag in (version, f"{version}.Final"):
                url = ASCIIDOC_URL.format(tag=tag)
                try:
                    content = await self.fetch(url, accept_status={200})
                    return url, content
                except RuntimeError:
                    continue
        tag_candidates = [f"{version}.Final", version]
        return await self.fetch_github_release(
            "hibernate/hibernate-orm", version, tag_candidates
        )

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        source_url, body = await self._fetch_guide(to_version)
        major, _, _, _ = parse_version(to_version)
        if major >= 6 and body.strip().startswith("="):
            changes = parse_asciidoc_migration_guide(body, source_url)
        else:
            changes = parse_markdown_statements(body, source_url)
        if not changes:
            raise RuntimeError(
                f"Hibernate: no changes parsed for hop {from_version} → {to_version}"
            )
        return ExtractionResult(changes=changes, metadata={})

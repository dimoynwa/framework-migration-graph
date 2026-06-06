"""WildFly Elytron extractor stub (version discovery implemented; extract is stub)."""

from __future__ import annotations

from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import is_jboss_ga_version
from migration_oracle.pipeline.extractors.filters import _skip_prerelease
from migration_oracle.pipeline.extractors.parsing import (
    filter_release_versions,
    normalize_wildfly_maven_version,
)
from migration_oracle.pipeline.extractors.stubs import StubExtractor

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/wildfly/security/wildfly-elytron/maven-metadata.xml"
)


class ElytronExtractor(StubExtractor):
    framework_key = "elytron"
    display_name = "WildFly Elytron"
    stub_name = "WildFly Elytron"

    def get_available_versions(self) -> list[str]:
        import asyncio

        return asyncio.run(self._filtered_maven_versions())

    async def _filtered_maven_versions(self) -> list[str]:
        raw_versions = await self._fetch_maven_versions(MAVEN_METADATA_URL)
        if _skip_prerelease():
            return [v for v in raw_versions if is_jboss_ga_version(v)]
        return list(raw_versions)

    async def discover_versions(self) -> list[str]:
        raw_versions = await self._fetch_maven_versions(MAVEN_METADATA_URL)
        if _skip_prerelease():
            versions = [v for v in raw_versions if is_jboss_ga_version(v)]
        else:
            versions = raw_versions
        normalized = [normalize_wildfly_maven_version(v) for v in versions]
        return filter_release_versions(normalized, final_only=False)

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        self._raise_not_implemented()

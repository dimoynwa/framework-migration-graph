"""Infinispan extractor stub (version discovery implemented; extract is stub)."""

from __future__ import annotations

from migration_oracle import config
from migration_oracle.pipeline.extractors.base import is_infinispan_ga_version
from migration_oracle.pipeline.extractors.parsing import (
    filter_release_versions,
    parse_maven_metadata_versions,
)
from migration_oracle.pipeline.extractors.stubs import StubExtractor

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/infinispan/infinispan-core/maven-metadata.xml"
)

# Planned tag candidates (version first, then .Final for pre-16.x compatibility):
# TAG_CANDIDATES = ["{version}", "{version}.Final"]


class InfinispanExtractor(StubExtractor):
    framework_key = "infinispan"
    display_name = "Infinispan"
    stub_name = "Infinispan"

    async def discover_versions(self) -> list[str]:
        xml = await self.fetch(MAVEN_METADATA_URL)
        raw_versions = parse_maven_metadata_versions(xml)
        if config.JBOSS_SKIP_PRERELEASE:
            versions = [v for v in raw_versions if is_infinispan_ga_version(v)]
        else:
            versions = raw_versions
        return filter_release_versions(versions, final_only=False)

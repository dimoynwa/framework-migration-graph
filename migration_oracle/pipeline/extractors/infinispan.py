"""Infinispan HTTP extractor."""

from __future__ import annotations

from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import (
    BaseExtractor,
    is_infinispan_ga_version,
)
from migration_oracle.pipeline.extractors.filters import _skip_prerelease
from migration_oracle.pipeline.extractors.parsing import (
    filter_release_versions,
    normalize_wildfly_maven_version,
    parse_github_release_text,
)

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/infinispan/infinispan-core/maven-metadata.xml"
)


class InfinispanExtractor(BaseExtractor):
    framework_key = "infinispan"
    display_name = "Infinispan"

    def get_available_versions(self) -> list[str]:
        import asyncio

        return asyncio.run(self._filtered_maven_versions())

    async def _filtered_maven_versions(self) -> list[str]:
        raw_versions = await self._fetch_maven_versions(MAVEN_METADATA_URL)
        if _skip_prerelease():
            return [v for v in raw_versions if is_infinispan_ga_version(v)]
        return list(raw_versions)

    async def discover_versions(self) -> list[str]:
        raw_versions = await self._fetch_maven_versions(MAVEN_METADATA_URL)
        if _skip_prerelease():
            versions = [v for v in raw_versions if is_infinispan_ga_version(v)]
        else:
            versions = raw_versions
        return filter_release_versions(versions, final_only=False)

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        version = normalize_wildfly_maven_version(to_version)
        tag_candidates = [f"{version}", f"{version}.Final"]
        source_url, body = await self.fetch_github_release(
            "infinispan/infinispan", to_version, tag_candidates
        )
        changes = parse_github_release_text(body, source_url)
        if not changes:
            raise RuntimeError(
                f"Infinispan: no changes parsed for hop {from_version} → {to_version}"
            )
        return ExtractionResult(changes=changes, metadata={})

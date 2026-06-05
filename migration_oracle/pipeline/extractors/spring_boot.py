"""Spring Boot HTTP extractor."""

from __future__ import annotations

from migration_oracle import config
from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import (
    BaseExtractor,
    is_spring_boot_ga_version,
)
from migration_oracle.pipeline.extractors.parsing import (
    bom_diff,
    filter_release_versions,
    parse_github_release_text,
    parse_maven_metadata_versions,
    parse_pom_dependencies,
    version_key,
)

MAVEN_METADATA_URL = (
    "https://repo1.maven.org/maven2/org/springframework/boot/"
    "spring-boot-dependencies/maven-metadata.xml"
)
POM_URL_TEMPLATE = (
    "https://repo1.maven.org/maven2/org/springframework/boot/"
    "spring-boot-dependencies/{version}/spring-boot-dependencies-{version}.pom"
)


class SpringBootExtractor(BaseExtractor):
    framework_key = "spring-boot"
    display_name = "Spring Boot"

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

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        tag_candidates = [f"v{to_version}", to_version]
        source_url, body = await self.fetch_github_release(
            "spring-projects/spring-boot", to_version, tag_candidates
        )
        changes = parse_github_release_text(body, source_url)
        if not changes:
            raise RuntimeError(
                f"Spring Boot: no changes parsed for hop {from_version} → {to_version} "
                f"from {source_url}"
            )
        metadata = await self.build_range_metadata(from_version, to_version)
        return ExtractionResult(changes=changes, metadata=metadata)

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

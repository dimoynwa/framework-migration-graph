"""Test stub extractor for pipeline integration tests."""

from __future__ import annotations

from migration_oracle.models.entities import DocumentedChange, ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor


class StubFrameworkExtractor(BaseExtractor):
    framework_key = "stub_framework"
    display_name = "Stub Framework"

    async def discover_versions(self) -> list[str]:
        return ["1.0.0", "2.0.0"]

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        changes = [
            DocumentedChange(
                type="breaking",
                confidence="confirmed",
                source_url=f"https://example.com/{to_version}",
                statement=(
                    f"Sample breaking change upgrade {from_version} → {to_version}: "
                    "remove legacy API."
                ),
            ),
            DocumentedChange(
                type="behavioral",
                confidence="inferred",
                source_url=f"https://example.com/{to_version}/behavior",
                statement="Default timeout value changed from 30s to 60s.",
            ),
        ]
        return ExtractionResult(changes=changes, metadata={})

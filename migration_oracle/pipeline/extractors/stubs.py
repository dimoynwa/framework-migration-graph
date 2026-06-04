"""Stub extractors that raise NotImplementedError."""

from __future__ import annotations

from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor

PIPELINE_DOC = "docs/export-extract-populate-framework-pipeline.md"


class StubExtractor(BaseExtractor):
    stub_name: str = "Framework"

    def _raise_not_implemented(self) -> None:
        raise NotImplementedError(
            f"{self.stub_name} extractor is not implemented. "
            f"See {PIPELINE_DOC} for the planned extraction pipeline."
        )

    async def discover_versions(self) -> list[str]:
        self._raise_not_implemented()

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        self._raise_not_implemented()

    async def extract_range(
        self, from_version: str, to_version: str
    ) -> tuple[ExtractionResult, list[tuple[str, str, list]]]:
        self._raise_not_implemented()

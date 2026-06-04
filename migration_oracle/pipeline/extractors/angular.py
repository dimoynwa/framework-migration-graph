"""Angular HTTP extractor."""

from __future__ import annotations

import re

from migration_oracle.models.entities import ExtractionResult
from migration_oracle.pipeline.extractors.base import BaseExtractor
from migration_oracle.pipeline.extractors.parsing import (
    filter_release_versions,
    parse_github_release_text,
)

NPM_REGISTRY_URL = "https://registry.npmjs.org/@angular/core"
_BLOG_LINK_RE = re.compile(r"https://angular\.dev/[^\s\)]+")


class AngularExtractor(BaseExtractor):
    framework_key = "angular"
    display_name = "Angular"

    async def discover_versions(self) -> list[str]:
        data = await self.fetch_json(NPM_REGISTRY_URL)
        versions = list(data.get("versions", {}).keys())
        return filter_release_versions(versions, final_only=False)

    async def extract(self, from_version: str, to_version: str) -> ExtractionResult:
        tag_candidates = [f"v{to_version}", to_version]
        source_url, body = await self.fetch_github_release(
            "angular/angular", to_version, tag_candidates
        )
        changes = parse_github_release_text(body, source_url)
        blog_insights = sorted(set(_BLOG_LINK_RE.findall(body)))
        if not changes:
            raise RuntimeError(
                f"Angular: no changes parsed for hop {from_version} → {to_version} "
                f"from {source_url}"
            )
        metadata = {"blog_insights": blog_insights} if blog_insights else {}
        return ExtractionResult(changes=changes, metadata=metadata)

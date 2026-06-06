"""Angular extractor tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.pipeline.extractors.angular import NPM_REGISTRY_URL, AngularExtractor


@pytest.mark.asyncio
@respx.mock
async def test_extract_parses_release() -> None:
    respx.get(NPM_REGISTRY_URL).mock(
        return_value=Response(
            200,
            json={"versions": {"18.0.0": {}, "19.0.0": {}}},
        )
    )
    respx.get(
        "https://api.github.com/repos/angular/angular/releases/tags/v19.0.0"
    ).mock(
        return_value=Response(
            200,
            json={
                "body": "## Breaking Changes\n- Strict templates default\n",
                "html_url": "https://github.com/angular/angular/releases/tag/v19.0.0",
            },
        )
    )
    respx.get(
        "https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md"
    ).mock(return_value=Response(200, text=""))

    async with AngularExtractor() as extractor:
        result = await extractor.extract("18.0.0", "19.0.0")

    assert len(result.changes) >= 1
    assert result.metadata.get("blog_insights") == []

"""Infinispan extractor tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.pipeline.extractors.infinispan import (
    MAVEN_METADATA_URL,
    InfinispanExtractor,
)

METADATA = """<?xml version="1.0"?>
<metadata><versioning><versions>
<version>16.0.0</version>
</versions></versioning></metadata>
"""


@pytest.mark.asyncio
@respx.mock
async def test_extract_parses_release() -> None:
    respx.get(MAVEN_METADATA_URL).mock(return_value=Response(200, text=METADATA))
    respx.get(
        "https://api.github.com/repos/infinispan/infinispan/releases/tags/16.0.0"
    ).mock(
        return_value=Response(
            200,
            json={
                "body": "## Breaking Changes\n- Cache API changed\n",
                "html_url": "https://github.com/infinispan/infinispan/releases/tag/16.0.0",
            },
        )
    )

    async with InfinispanExtractor() as extractor:
        result = await extractor.extract("15.0.0", "16.0.0")

    assert len(result.changes) >= 1

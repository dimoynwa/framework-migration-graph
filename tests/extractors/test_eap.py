"""EAP extractor tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.pipeline.extractors.eap import EAPExtractor


@pytest.mark.asyncio
@respx.mock
async def test_extract_parses_redhat_docs() -> None:
    html = "<html><body><h2>Changes</h2><ul><li>Update /subsystem=logging</li></ul></body></html>"
    respx.get(url__regex=r"https://access\.redhat\.com/.*").mock(
        return_value=Response(200, text=html)
    )

    async with EAPExtractor() as extractor:
        extractor._redhat_delay = 0
        result = await extractor.extract("7.4.0", "8.0.0")

    assert len(result.changes) >= 1
    assert result.changes[0].type == "mandatory_migration"

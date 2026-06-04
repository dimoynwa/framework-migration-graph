"""Hibernate extractor tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.pipeline.extractors.hibernate import (
    MAVEN_METADATA_URL,
    HibernateExtractor,
)

METADATA = """<?xml version="1.0"?>
<metadata><versioning><versions>
<version>6.4.0.Final</version><version>6.5.0.Final</version>
</versions></versioning></metadata>
"""

ASCIIDOC = """= Migration Guide
== Breaking
- Schema validation defaults changed
"""


@pytest.mark.asyncio
@respx.mock
async def test_extract_asciidoc_guide() -> None:
    respx.get(MAVEN_METADATA_URL).mock(return_value=Response(200, text=METADATA))
    respx.get(
        "https://raw.githubusercontent.com/hibernate/hibernate-orm/6.5.0/migration-guide.adoc"
    ).mock(return_value=Response(200, text=ASCIIDOC))

    async with HibernateExtractor() as extractor:
        result = await extractor.extract("6.4.0", "6.5.0")

    assert len(result.changes) >= 1

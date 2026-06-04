"""Spring Boot extractor tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.pipeline.extractors.spring_boot import (
    MAVEN_METADATA_URL,
    SpringBootExtractor,
)

SAMPLE_METADATA = """<?xml version="1.0"?>
<metadata>
  <versioning><versions>
    <version>3.3.0</version><version>3.4.0</version>
  </versions></versioning>
</metadata>
"""

SAMPLE_RELEASE = {
    "body": "## Breaking Changes\n- Removed legacy API\n",
    "html_url": "https://github.com/spring-projects/spring-boot/releases/tag/v3.4.0",
}


@pytest.mark.asyncio
@respx.mock
async def test_extract_parses_release_body() -> None:
    respx.get(MAVEN_METADATA_URL).mock(return_value=Response(200, text=SAMPLE_METADATA))
    respx.get(
        "https://api.github.com/repos/spring-projects/spring-boot/releases/tags/v3.4.0"
    ).mock(return_value=Response(200, json=SAMPLE_RELEASE))
    pom = "<project><dependencyManagement><dependencies><dependency><groupId>g</groupId><artifactId>a</artifactId><version>1</version></dependency></dependencies></dependencyManagement></project>"
    respx.get(url__regex=r".*spring-boot-dependencies/3\.[34]\.0/.*\.pom").mock(
        return_value=Response(200, text=pom)
    )

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract("3.3.0", "3.4.0")

    assert len(result.changes) >= 1
    assert result.changes[0].type == "breaking"

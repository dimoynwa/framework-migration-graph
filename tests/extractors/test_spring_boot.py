"""Spring Boot extractor tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.pipeline.extractors.base import HopContext
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
    respx.get(
        "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes"
    ).mock(return_value=Response(404, text=""))

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract("3.3.0", "3.4.0")

    assert len(result.changes) >= 1
    assert result.changes[0].type == "breaking"
    assert "bom_diff" not in result.metadata


WIKI_HTML = """
<html><body><div id="wiki-body"><div class="markdown-body">
<h2>New Features</h2><ul><li>Added a fancy new feature</li></ul>
<h2>Upgrading from Spring Boot 3.3</h2>
<h3>Actuator heapdump endpoint</h3><p>The endpoint is now opt-in.</p>
</div></div></body></html>
"""


def _release(body: str, version: str) -> dict:
    return {
        "body": body,
        "html_url": f"https://github.com/spring-projects/spring-boot/releases/tag/v{version}",
    }


@pytest.mark.asyncio
@respx.mock
async def test_patch_hop_skips_minor_line_wiki_page() -> None:
    """The 3.4 wiki page describes entering 3.4, not the 3.4.0 → 3.4.1 patch step."""
    respx.get(
        "https://api.github.com/repos/spring-projects/spring-boot/releases/tags/v3.4.1"
    ).mock(
        return_value=Response(
            200, json=_release("## Bug Fixes\n- Fixed a startup failure\n", "3.4.1")
        )
    )
    wiki_route = respx.get(
        "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes"
    ).mock(return_value=Response(200, text=WIKI_HTML))

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.4.0", "3.4.1", hop_context=HopContext("3.4.0", "3.4.1")
        )

    assert not wiki_route.called
    assert result.changes
    assert not any("wiki" in change.source_url for change in result.changes)


@pytest.mark.asyncio
@respx.mock
async def test_minor_line_entry_hop_fetches_wiki_page() -> None:
    respx.get(
        "https://api.github.com/repos/spring-projects/spring-boot/releases/tags/v3.4.0"
    ).mock(
        return_value=Response(
            200, json=_release("## Breaking Changes\n- Removed legacy API\n", "3.4.0")
        )
    )
    wiki_route = respx.get(
        "https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes"
    ).mock(return_value=Response(200, text=WIKI_HTML))

    async with SpringBootExtractor() as extractor:
        result = await extractor.extract(
            "3.3.13", "3.4.0", hop_context=HopContext("3.3.13", "3.4.0")
        )

    assert wiki_route.called
    assert any("wiki" in change.source_url for change in result.changes)
    assert any("Actuator heapdump endpoint" in change.statement for change in result.changes)

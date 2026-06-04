"""WildFly extractor tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.pipeline.extractors.wildfly import (
    MAVEN_METADATA_URL,
    WildFlyExtractor,
)

METADATA = """<?xml version="1.0"?>
<metadata><versioning><versions>
<version>29.0.0.Final</version><version>30.0.0.Final</version>
</versions></versioning></metadata>
"""


@pytest.mark.asyncio
@respx.mock
async def test_extract_github_release() -> None:
    respx.get(MAVEN_METADATA_URL).mock(return_value=Response(200, text=METADATA))
    respx.get(
        "https://api.github.com/repos/wildfly/wildfly/releases/tags/30.0.0.Final"
    ).mock(
        return_value=Response(
            200,
            json={
                "body": "- [WFLY-9999] - Update subsystem config\n",
                "html_url": "https://github.com/wildfly/wildfly/releases/tag/30.0.0.Final",
            },
        )
    )
    respx.get(
        "https://redhat.atlassian.net/rest/api/2/issue/WFLY-9999"
        "?fields=summary,description,issuetype,priority,status"
    ).mock(
        return_value=Response(
            200,
            json={
                "fields": {
                    "summary": "Subsystem",
                    "description": "Detailed Jira text",
                    "issuetype": {"name": "Bug"},
                }
            },
        )
    )

    async with WildFlyExtractor() as extractor:
        result = await extractor.extract("29.0.0", "30.0.0")

    assert len(result.changes) >= 1

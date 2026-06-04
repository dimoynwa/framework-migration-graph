"""WildFly Jira enrichment unit tests."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from migration_oracle.models.entities import DocumentedChange
from migration_oracle.pipeline.extractors.wildfly_jira import collect_jira_keys, enrich_with_jira
from migration_oracle.pipeline.extractors.wildfly import WildFlyExtractor


def test_collect_jira_keys_from_body() -> None:
    body = "[WFLY-1234] - Fix something"
    keys = collect_jira_keys(body, [])
    assert "WFLY-1234" in keys


@pytest.mark.asyncio
@respx.mock
async def test_enrich_with_jira_merges_description() -> None:
    respx.get(
        "https://redhat.atlassian.net/rest/api/2/issue/WFLY-1234"
        "?fields=summary,description,issuetype,priority,status"
    ).mock(
        return_value=Response(
            200,
            json={
                "fields": {
                    "summary": "Fix docs",
                    "description": "Full migration impact text.",
                    "issuetype": {"name": "Bug"},
                }
            },
        )
    )
    changes = [
        DocumentedChange(
            type="behavioral",
            confidence="inferred",
            source_url="https://github.com/wildfly/wildfly",
            statement="[WFLY-1234] - Fix something",
        )
    ]
    async with WildFlyExtractor() as extractor:
        enriched = await enrich_with_jira(extractor, "[WFLY-1234]", changes)
    assert "Full migration impact" in enriched[0].statement
    assert "redhat.atlassian.net" in enriched[0].source_url

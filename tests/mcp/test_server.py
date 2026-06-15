"""Tests for MCP server startup and registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from neo4j.exceptions import ServiceUnavailable

from migration_oracle.mcp import server as mcp_server
from migration_oracle.mcp.instance import mcp


@pytest.mark.asyncio
async def test_tool_count():
    tools = await mcp.list_tools()
    assert len(tools) == 24


@pytest.mark.asyncio
async def test_skill_resources_registered():
    resources = await mcp.list_resources()
    uris = {str(r.uri) for r in resources}
    expected = {
        "skill://framework-migration/main",
        "skill://framework-migration/scanning",
        "skill://framework-migration/plan-format",
        "skill://framework-migration/version-map",
        "skill://framework-migration/rollback",
    }
    assert expected.issubset(uris)
    assert len([r for r in resources if str(r.uri) in expected]) == 5


def test_startup_sequence_order():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    calls: list[str] = []

    def _run(*args, **kwargs):
        calls.append("connectivity")
        return MagicMock(single=lambda: {"ok": 1})

    mock_session.run.side_effect = _run

    with (
        patch("migration_oracle.mcp.server.get_driver", return_value=mock_driver),
        patch(
            "migration_oracle.mcp.server.ensure_indexes",
            side_effect=lambda d: calls.append("indexes"),
        ),
    ):
        mcp_server.startup()
    assert calls == ["connectivity", "indexes"]


def test_startup_exits_on_connectivity_failure():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.run.side_effect = ServiceUnavailable("down")
    with (
        patch("migration_oracle.mcp.server.get_driver", return_value=mock_driver),
        patch("migration_oracle.mcp.server.ensure_indexes") as mock_indexes,
    ):
        with pytest.raises(ServiceUnavailable):
            mcp_server.startup()
    mock_indexes.assert_not_called()


def test_startup_continues_on_index_ddl_failure():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    mock_session.run.return_value.single.return_value = {"ok": 1}
    with (
        patch("migration_oracle.mcp.server.get_driver", return_value=mock_driver),
        patch("migration_oracle.mcp.server.ensure_indexes") as mock_indexes,
    ):
        mcp_server.startup()
    mock_indexes.assert_called_once()

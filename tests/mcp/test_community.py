"""Tests for community insight MCP tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from migration_oracle.mcp.tools.community import (
    submit_migration_insight,
    verify_insight,
    vote_insight,
)


def test_submit_insight_new():
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1])
    with (
        patch(
            "migration_oracle.mcp.tools.community.get_embedding_model",
            return_value=mock_model,
        ),
        patch(
            "migration_oracle.mcp.tools.community.community_queries.submit_insight",
            return_value=("insight-1", False),
        ),
    ):
        result = submit_migration_insight(
            statement="Workaround for X",
            spring_boot_version="3.4.0",
        )
    assert result["status"] == "ok"
    assert result["insight_id"] == "insight-1"


def test_submit_insight_duplicate_detected():
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1])
    with (
        patch(
            "migration_oracle.mcp.tools.community.get_embedding_model",
            return_value=mock_model,
        ),
        patch(
            "migration_oracle.mcp.tools.community.community_queries.submit_insight",
            return_value=("existing-id", True),
        ),
    ):
        result = submit_migration_insight(
            statement="Duplicate insight",
            spring_boot_version="3.4.0",
        )
    assert result["status"] == "duplicate"
    assert result["insight_id"] == "existing-id"


def test_vote_insight_increment():
    with patch(
        "migration_oracle.mcp.tools.community.community_queries.vote_insight",
        return_value={"insight_id": "i1", "votes": 6},
    ):
        result = vote_insight(insight_id="i1", delta=1)
    assert result["status"] == "ok"
    assert result["new_vote_count"] == 6


def test_verify_insight():
    with patch(
        "migration_oracle.mcp.tools.community.community_queries.verify_insight",
        return_value={"insight_id": "i1", "verified": True},
    ):
        result = verify_insight(insight_id="i1")
    assert result["verified"] is True

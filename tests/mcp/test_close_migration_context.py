"""Status enum tests for close_migration_context."""

from unittest.mock import MagicMock, patch


def _mock_close(final_status):
    return {
        "context_id": "ctx-1",
        "migration_status": final_status,
        "completed_steps": [],
        "skipped_steps": [],
        "completed_at": "2026-06-13T10:00:00",
        "notes": "",
    }


def test_abandoned_status_accepted():
    """close_migration_context('abandoned') succeeds."""
    from migration_oracle.mcp.tools.context import close_migration_context

    with patch("migration_oracle.mcp.tools.context.context_queries.close_migration_context") as mock:
        mock.return_value = _mock_close("abandoned")
        result = close_migration_context(context_id="ctx-1", final_status="abandoned")

    assert result["tool_status"] == "ok"
    assert result["migration_status"] == "abandoned"


def test_complete_status_accepted():
    """close_migration_context('complete') still works."""
    from migration_oracle.mcp.tools.context import close_migration_context

    with patch("migration_oracle.mcp.tools.context.context_queries.close_migration_context") as mock:
        mock.return_value = _mock_close("complete")
        result = close_migration_context(context_id="ctx-1", final_status="complete")

    assert result["tool_status"] == "ok"


def test_partial_status_accepted():
    """close_migration_context('partial') still works."""
    from migration_oracle.mcp.tools.context import close_migration_context

    with patch("migration_oracle.mcp.tools.context.context_queries.close_migration_context") as mock:
        mock.return_value = _mock_close("partial")
        result = close_migration_context(context_id="ctx-1", final_status="partial")

    assert result["tool_status"] == "ok"


def test_invalid_status_returns_error():
    """Unknown final_status returns documented error shape without calling the DB."""
    from migration_oracle.mcp.tools.context import close_migration_context

    with patch("migration_oracle.mcp.tools.context.context_queries.close_migration_context") as mock:
        result = close_migration_context(context_id="ctx-1", final_status="invalid_value")
        mock.assert_not_called()

    assert result["tool_status"] == "error"
    assert result["error_code"] == "invalid_final_status"

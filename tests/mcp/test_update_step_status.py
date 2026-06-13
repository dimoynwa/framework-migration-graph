"""Tests for spec 011 US1: update_step_status with STEP_OUTCOME relationship."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_record_result(on_path=True, completed_count=1):
    if not on_path:
        return {"on_path": False}
    return {
        "context_id": "ctx-1",
        "completed_count": completed_count,
        "skipped_count": 0,
        "migration_status": "in-progress",
    }


@patch("migration_oracle.mcp.tools.context.context_queries.auto_close_write")
@patch("migration_oracle.mcp.tools.context.context_queries.get_pending_steps", return_value=[MagicMock()])
@patch("migration_oracle.mcp.tools.context.context_queries.record_step_outcome")
def test_step_outcome_rel_created(mock_record, mock_pending, mock_close):
    """Successful call returns ok status and the step/outcome back to caller."""
    mock_record.return_value = _make_record_result(on_path=True)

    from migration_oracle.mcp.tools.context import update_step_status

    result = update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="completed",
        reason="done manually",
    )

    assert result["status"] == "ok"
    assert result["step_id"] == "step-1"
    assert result["outcome"] == "completed"
    mock_record.assert_called_once_with(
        context_id="ctx-1",
        step_id="step-1",
        outcome="completed",
        reason="done manually",
    )


@patch("migration_oracle.mcp.tools.context.context_queries.auto_close_write")
@patch("migration_oracle.mcp.tools.context.context_queries.get_pending_steps", return_value=[])
@patch("migration_oracle.mcp.tools.context.context_queries.record_step_outcome")
def test_step_not_on_path_returns_error(mock_record, mock_pending, mock_close):
    """When record_step_outcome signals on_path=False, the tool returns a structured error."""
    mock_record.return_value = {"on_path": False}

    from migration_oracle.mcp.tools.context import update_step_status

    result = update_step_status(
        context_id="ctx-1",
        step_id="step-99",
        outcome="completed",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "step_not_on_path"
    assert result["step_id"] == "step-99"
    assert "hint" in result
    mock_close.assert_not_called()


@patch("migration_oracle.mcp.tools.context.context_queries.auto_close_write")
@patch("migration_oracle.mcp.tools.context.context_queries.get_pending_steps", return_value=[MagicMock()])
@patch("migration_oracle.mcp.tools.context.context_queries.record_step_outcome")
def test_no_map_property_written(mock_record, mock_pending, mock_close):
    """The tool layer must not pass a dict/map value as reason — reason is always a scalar string."""
    mock_record.return_value = _make_record_result()

    from migration_oracle.mcp.tools.context import update_step_status

    update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="skipped",
        reason="deferred",
    )

    _, kwargs = mock_record.call_args
    assert isinstance(kwargs.get("reason", ""), str), "reason must be a plain string, not a map"


@patch("migration_oracle.mcp.tools.context.context_queries.auto_close_write")
@patch("migration_oracle.mcp.tools.context.context_queries.get_pending_steps", return_value=[MagicMock()])
@patch("migration_oracle.mcp.tools.context.context_queries.record_step_outcome")
def test_reason_null_when_not_supplied(mock_record, mock_pending, mock_close):
    """When caller omits reason, record_step_outcome is called with reason='' (empty string default)."""
    mock_record.return_value = _make_record_result()

    from migration_oracle.mcp.tools.context import update_step_status

    update_step_status(context_id="ctx-1", step_id="step-1", outcome="completed")

    _, kwargs = mock_record.call_args
    reason_val = kwargs.get("reason", "")
    assert reason_val == "" or reason_val is None


@patch("migration_oracle.mcp.tools.context.context_queries.auto_close_write")
@patch("migration_oracle.mcp.tools.context.context_queries.get_pending_steps", return_value=[])
@patch("migration_oracle.mcp.tools.context.context_queries.record_step_outcome")
def test_completed_steps_preserved(mock_record, mock_pending, mock_close):
    """completed_count from record_step_outcome result is forwarded to the tool response."""
    mock_record.return_value = _make_record_result(completed_count=3)
    mock_close.return_value = {"migration_status": "complete"}

    from migration_oracle.mcp.tools.context import update_step_status

    result = update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="completed",
    )

    assert result["completed_count"] == 3
    assert result["context_auto_closed"] is True

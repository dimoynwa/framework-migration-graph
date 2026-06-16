"""Unit tests for bridge tracking / deferred outcome (T036)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from migration_oracle.mcp.tools.context import update_step_status


def _mock_bridge_found(bridge_name="compat-bridge"):
    return {"bridge_name": bridge_name, "applicable_rule_types": ["breaking"]}


def _mock_record_step_outcome():
    return {"completed_count": 1, "skipped_count": 0, "migration_status": "in-progress"}


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_deferred_accepted_when_bridge_in_graph(mock_q):
    """update_step_status(outcome='deferred') accepted when rule has BRIDGED_BY edge."""
    mock_q.check_bridge_discoverability.return_value = _mock_bridge_found()
    mock_q.record_step_outcome.return_value = _mock_record_step_outcome()
    mock_q.auto_resolve_deferred_steps.return_value = []
    mock_q.get_pending_steps.return_value = [MagicMock()]  # still pending, no auto-close

    result = update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="deferred",
        reason='{"bridgeName": "compat", "requiredChange": "step-2"}',
    )
    assert result["status"] == "ok"
    assert result["outcome"] == "deferred"


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_deferred_rejected_when_no_bridge_in_graph(mock_q):
    """update_step_status(outcome='deferred') rejected with bridge_not_in_graph when no BRIDGED_BY edge."""
    mock_q.check_bridge_discoverability.return_value = {"bridge_name": None, "applicable_rule_types": None}

    result = update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="deferred",
        reason="{}",
    )
    assert result["status"] == "error"
    assert result["error_code"] == "bridge_not_in_graph"


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_deferred_rejected_when_discoverability_is_none(mock_q):
    """update_step_status(outcome='deferred') rejected when bridge check returns None (no rule/step found)."""
    mock_q.check_bridge_discoverability.return_value = None

    result = update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="deferred",
        reason="{}",
    )
    assert result["status"] == "error"
    assert result["error_code"] == "bridge_not_in_graph"


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_completed_triggers_auto_resolve(mock_q):
    """When outcome='completed', auto_resolve_deferred_steps is called."""
    mock_q.record_step_outcome.return_value = _mock_record_step_outcome()
    mock_q.auto_resolve_deferred_steps.return_value = ["deferred-step-id"]
    mock_q.get_pending_steps.return_value = [MagicMock()]

    result = update_step_status(
        context_id="ctx-1",
        step_id="step-req",
        outcome="completed",
    )
    assert result["status"] == "ok"
    mock_q.auto_resolve_deferred_steps.assert_called_once_with(
        context_id="ctx-1",
        completed_step_id="step-req",
    )
    assert "auto_resolved_deferred" in result
    assert result["auto_resolved_deferred"] == ["deferred-step-id"]


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_invalid_outcome_rejected(mock_q):
    """Invalid outcome value is rejected with error."""
    result = update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="bridgeResolved",  # NOT a valid outcome
    )
    assert result["status"] == "error"
    assert result["error_code"] == "invalid_outcome"

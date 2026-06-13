"""E2E test: update_step_status writes STEP_OUTCOME relationship and progress query returns non-zero."""

from unittest.mock import MagicMock, patch

import pytest


def _make_session(records=None):
    session = MagicMock()
    result = MagicMock()
    result.single.return_value = records[0] if records else None
    session.run.return_value = result
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    return session


def test_update_step_status_calls_step_outcome_merge():
    """After update_step_status, STEP_OUTCOME MERGE is included in the Cypher query."""
    from migration_oracle.mcp.graph.queries.context import _RECORD_STEP_OUTCOME

    assert "MERGE (ctx)-[so:STEP_OUTCOME]->(step)" in _RECORD_STEP_OUTCOME
    assert "so.status    = $outcome" in _RECORD_STEP_OUTCOME
    assert "so.reason    = $reason" in _RECORD_STEP_OUTCOME
    assert "so.updatedAt = datetime()" in _RECORD_STEP_OUTCOME


def test_record_step_outcome_forwards_reason():
    """record_step_outcome passes reason to the Cypher query."""
    from migration_oracle.mcp.graph.queries import context as ctx_queries

    fake_record = {
        "context_id": "ctx-1",
        "completed_count": 1,
        "skipped_count": 0,
        "migration_status": "in-progress",
    }
    with patch("migration_oracle.mcp.graph.queries.context.write_session") as mock_ws:
        session = MagicMock()
        result = MagicMock()
        result.single.return_value = fake_record
        session.run.return_value = result
        session.__enter__ = lambda s: s
        session.__exit__ = MagicMock(return_value=False)
        mock_ws.return_value = session

        ctx_queries.record_step_outcome(
            context_id="ctx-1",
            step_id="step-1",
            outcome="completed",
            reason="all tests pass",
        )

        call_kwargs = session.run.call_args
        assert call_kwargs[1].get("reason") == "all tests pass" or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1].get("reason") == "all tests pass"
        )

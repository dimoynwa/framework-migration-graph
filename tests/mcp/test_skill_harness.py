"""Tests for four-loop harness resumption semantics."""

from __future__ import annotations

from unittest.mock import patch

from migration_oracle.mcp.tools.context import (
    create_migration_context,
    get_pending_steps,
    update_step_status,
)


def _ctx(created: bool, completed=None, skipped=None, failed=None):
    return {
        "context_id": "ctx-A",
        "project_id": "proj-A",
        "from_version": "3.5.6",
        "to_version": "4.0.0",
        "framework": "Spring Boot",
        "migration_status": "in-progress",
        "scanned_entities": [],
        "completed_steps": completed or [],
        "skipped_steps": skipped or [],
        "created_at": "now",
        "completed_at": None,
        "notes": "",
        "created": created,
    }


def test_loop_i_resume_skips_completed_steps():
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
            side_effect=[
                _ctx(True, completed=["step-1", "step-2"]),
                _ctx(False, completed=["step-1", "step-2"]),
            ],
        ),
        patch(
            "migration_oracle.mcp.tools.context.check_context_version_match",
            return_value=True,
        ),
    ):
        first = create_migration_context(
            project_id="proj-A",
            from_version="3.5.6",
            to_version="4.0.0",
            framework="Spring Boot",
        )
        second = create_migration_context(
            project_id="proj-A",
            from_version="3.5.6",
            to_version="4.0.0",
            framework="Spring Boot",
        )
    assert first["created"] is True
    assert second["created"] is False
    assert first["context_id"] == second["context_id"]
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
        return_value=[
            {"step_id": "step-3"},
            {"step_id": "step-4"},
        ],
    ):
        pending = get_pending_steps(context_id="ctx-A")
    ids = [s["step_id"] for s in pending["pending_steps"]]
    assert ids == ["step-3", "step-4"]


def test_context_resume_correct_completed_steps():
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
            side_effect=[_ctx(True, completed=["step-1"]), _ctx(False, completed=["step-1"])],
        ),
        patch(
            "migration_oracle.mcp.tools.context.check_context_version_match",
            return_value=True,
        ),
    ):
        create_migration_context(
            project_id="proj-A",
            from_version="3.5.6",
            to_version="4.0.0",
            framework="Spring Boot",
        )
        resumed = create_migration_context(
            project_id="proj-A",
            from_version="3.5.6",
            to_version="4.0.0",
            framework="Spring Boot",
        )
    assert resumed["completed_steps"] == ["step-1"]


def test_context_resume_preserves_skipped_steps():
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
        return_value=[{"step_id": "step-3"}],
    ):
        pending = get_pending_steps(context_id="ctx-A")
    assert all(s["step_id"] != "step-2" for s in pending["pending_steps"])


def test_context_resume_preserves_failed_steps():
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
        return_value=[{"step_id": "step-4"}],
    ):
        pending = get_pending_steps(context_id="ctx-A")
    assert all(s["step_id"] != "step-3" for s in pending["pending_steps"])


def test_context_auto_close_on_resume_if_all_resolved():
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.record_step_outcome",
            return_value={"completed_count": 4, "skipped_count": 0, "migration_status": "in-progress"},
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
            return_value=[],
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.auto_close_write",
            return_value={"migration_status": "complete"},
        ) as mock_close,
    ):
        result = update_step_status(
            context_id="ctx-A", step_id="step-4", outcome="completed"
        )
    assert result["context_auto_closed"] is True
    assert result["context_status"] == "complete"
    mock_close.assert_called_once()


def test_loop_i_stops_on_complete_context():
    complete_ctx = _ctx(False)
    complete_ctx["migration_status"] = "complete"
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
            return_value=complete_ctx,
        ),
        patch(
            "migration_oracle.mcp.tools.context.check_context_version_match",
            return_value=True,
        ),
    ):
        result = create_migration_context(
            project_id="proj-A",
            from_version="3.5.6",
            to_version="4.0.0",
            framework="Spring Boot",
        )
    assert result["migration_status"] == "complete"


def test_context_resume_no_duplicate_steps():
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
        return_value=[{"step_id": "step-4"}],
    ):
        pending = get_pending_steps(context_id="ctx-A")
    ids = {s["step_id"] for s in pending["pending_steps"]}
    assert ids == {"step-4"}
    assert "step-1" not in ids
    assert "step-2" not in ids
    assert "step-3" not in ids

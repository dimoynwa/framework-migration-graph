"""Tests for context MCP tools."""

from __future__ import annotations

from unittest.mock import patch

from migration_oracle.mcp.tools.context import (
    close_migration_context,
    create_migration_context,
    get_pending_steps,
    get_steps_for_scope_tier,
    update_step_status,
)


def test_create_migration_context_new():
    ctx = {
        "context_id": "ctx-1",
        "project_id": "proj",
        "from_version": "3.5.6",
        "to_version": "4.0.0",
        "framework": "Spring Boot",
        "migration_status": "in-progress",
        "scanned_entities": ["A"],
        "completed_steps": [],
        "skipped_steps": [],
        "created_at": "now",
        "completed_at": None,
        "notes": "",
        "created": True,
    }
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
        return_value=ctx,
    ):
        result = create_migration_context(
            project_id="proj",
            from_version="3.5.6",
            to_version="4.0.0",
            framework="Spring Boot",
            scanned_entities=["A"],
        )
    assert result["created"] is True
    assert result["context_id"] == "ctx-1"


def test_create_migration_context_idempotent():
    ctx = {
        "context_id": "ctx-1",
        "project_id": "proj",
        "from_version": "3.5.6",
        "to_version": "4.0.0",
        "framework": "Spring Boot",
        "migration_status": "in-progress",
        "scanned_entities": ["A"],
        "completed_steps": ["step-1"],
        "skipped_steps": [],
        "created_at": "now",
        "completed_at": None,
        "notes": "",
        "created": False,
    }
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
            return_value=ctx,
        ),
        patch(
            "migration_oracle.mcp.tools.context.check_context_version_match",
            return_value=True,
        ),
    ):
        result = create_migration_context(
            project_id="proj",
            from_version="3.5.6",
            to_version="4.0.0",
            framework="Spring Boot",
        )
    assert result["created"] is False


def test_get_pending_steps_ordered():
    rows = [
        {"step_id": "s1", "severity": "critical", "summary": "a"},
        {"step_id": "s2", "severity": "high", "summary": "b"},
    ]
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
        return_value=rows,
    ):
        result = get_pending_steps(context_id="ctx-1")
    assert result["total_pending"] == 2
    assert result["pending_steps"][0]["step_id"] == "s1"


def test_update_step_status_completed():
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.record_step_outcome",
            return_value={"completed_count": 1, "skipped_count": 0, "migration_status": "in-progress"},
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
            return_value=[{"step_id": "s2"}],
        ),
    ):
        result = update_step_status(
            context_id="ctx-1",
            step_id="s1",
            outcome="completed",
            reason="build passed",
        )
    assert result["outcome"] == "completed"
    assert result["context_auto_closed"] is False


def test_update_step_status_auto_close():
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.record_step_outcome",
            return_value={"completed_count": 2, "skipped_count": 0, "migration_status": "in-progress"},
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
            return_value=[],
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.auto_close_write",
            return_value={"migration_status": "complete"},
        ),
    ):
        result = update_step_status(
            context_id="ctx-1",
            step_id="s2",
            outcome="completed",
        )
    assert result["context_auto_closed"] is True
    assert result["context_status"] == "complete"


def test_get_steps_for_scope_tier():
    rows = [
        {
            "entity_name": "com.example.Foo",
            "entity_type": "Class",
            "step_id": "s1",
            "rule_id": "r1",
            "summary": "change",
            "scope": "api-surface",
            "severity": "high",
        }
    ]
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier",
        return_value=rows,
    ):
        result = get_steps_for_scope_tier(
            context_id="ctx-1", scope="api-surface", severity_threshold="high"
        )
    assert result["rule_count"] == 1
    assert result["total"] == 1
    assert result["hits"][0]["step_id"] == "s1"


def test_close_migration_context():
    closed = {
        "context_id": "ctx-1",
        "migration_status": "partial",
        "completed_steps": ["s1"],
        "skipped_steps": ["s2"],
        "completed_at": "2026-06-07T00:00:00Z",
        "notes": "done",
    }
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.close_migration_context",
        return_value=closed,
    ):
        result = close_migration_context(
            context_id="ctx-1", final_status="partial", notes="done"
        )
    assert result["tool_status"] == "ok"
    assert result["migration_status"] == "partial"
    assert "status" not in result or result.get("status") != result["migration_status"]


def test_context_full_round_trip():
    pending_first = [
        {"step_id": "step-1", "summary": "a"},
        {"step_id": "step-2", "summary": "b"},
        {"step_id": "step-3", "summary": "c"},
    ]
    pending_second = [{"step_id": "step-3", "summary": "c"}]
    pending_after_one = [{"step_id": "step-2"}, {"step_id": "step-3"}]
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.get_pending_steps",
            side_effect=[
                pending_first,
                pending_after_one,
                [{"step_id": "step-3"}],
                pending_second,
            ],
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.record_step_outcome",
            return_value={"completed_count": 1, "skipped_count": 1, "migration_status": "in-progress"},
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.auto_close_write",
            return_value={"migration_status": "complete"},
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.close_migration_context",
            return_value={
                "context_id": "ctx-1",
                "migration_status": "partial",
                "completed_steps": ["step-1"],
                "skipped_steps": ["step-2"],
                "completed_at": "t",
                "notes": "",
            },
        ),
    ):
        first = get_pending_steps(context_id="ctx-1")
        assert len(first["pending_steps"]) == 3
        update_step_status(context_id="ctx-1", step_id="step-1", outcome="completed")
        update_step_status(context_id="ctx-1", step_id="step-2", outcome="skipped")
        second = get_pending_steps(context_id="ctx-1")
        ids = {s["step_id"] for s in second["pending_steps"]}
        assert ids == {"step-3"}
        closed = close_migration_context(context_id="ctx-1", final_status="partial")
    assert closed["migration_status"] == "partial"
    assert closed["completed_at"] == "t"

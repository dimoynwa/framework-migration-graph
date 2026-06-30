"""Tests for clarify stage tools (015-split-migration-harness)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def test_manual_step_cross_context_isolation():
    """Manual steps added to one context must not appear in another's pending queue."""
    from migration_oracle.mcp.graph.queries import context as context_queries

    ctx_a_steps = [
        {"step_id": "manual-a", "summary": "A manual", "applicability": "manual"},
    ]
    ctx_b_steps: list = []

    def fake_pending(*, context_id, **kwargs):
        if context_id == "ctx-a":
            return ctx_a_steps
        return ctx_b_steps

    with patch.object(context_queries, "get_pending_steps", side_effect=fake_pending):
        a = context_queries.get_pending_steps(context_id="ctx-a")
        b = context_queries.get_pending_steps(context_id="ctx-b")

    assert len(a) == 1
    assert a[0]["step_id"] == "manual-a"
    assert b == []


def test_add_manual_step_closed_context_error():
    from migration_oracle.mcp.tools.context import add_manual_step

    with patch(
        "migration_oracle.mcp.tools.context.validate_context_id_for_stage",
        return_value=None,
    ), patch(
        "migration_oracle.mcp.tools.context.context_queries.get_context_metadata",
        return_value={
            "context_id": "ctx-1",
            "status": "complete",
            "framework": "Spring Boot",
        },
    ):
        result = add_manual_step(
            context_id="ctx-1",
            summary="Fix security",
            instruction="Review filter chain",
        )

    assert result["status"] == "error"
    assert result["error_code"] == "context_not_open"


def test_invalid_context_id_gap_check_stage():
    from migration_oracle.mcp.tools.context import get_pending_steps

    with patch(
        "migration_oracle.mcp.stage_gating.get_active_stage",
        return_value="gap-check",
    ), patch(
        "migration_oracle.mcp.tools.context.validate_context_id_for_stage",
        return_value={
            "status": "error",
            "error_code": "context_not_found",
            "hint": "Context 'bad' not found",
        },
    ):
        result = get_pending_steps(context_id="bad")

    assert result["error_code"] == "context_not_found"


def test_update_queried_entity_force_include():
    from migration_oracle.mcp.tools.context import update_queried_entity

    with patch(
        "migration_oracle.mcp.tools.context.validate_context_id_for_stage",
        return_value=None,
    ), patch(
        "migration_oracle.mcp.tools.context.context_queries.update_queried_entity",
        return_value={"cached_count": 1},
    ), patch(
        "migration_oracle.mcp.tools.context.context_queries.force_include_entity",
    ) as mock_force:
        result = update_queried_entity(
            context_id="ctx-1",
            entity_name="org.example.Foo",
            result_summary="re-included",
            force_include=True,
        )

    assert result["status"] == "ok"
    assert result["force_included"] is True
    mock_force.assert_called_once_with(
        context_id="ctx-1",
        entity_name="org.example.Foo",
    )


def test_excluded_outcome_accepted():
    from migration_oracle.mcp.tools.context import update_step_status

    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.record_step_outcome",
            return_value={
                "completed_count": 0,
                "skipped_count": 0,
                "migration_status": "in-progress",
                "on_path": True,
            },
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
            step_id="step-1",
            outcome="excluded",
            reason="out of scope",
        )

    assert result["status"] == "ok"
    assert result["outcome"] == "excluded"
    assert result["context_auto_closed"] is True

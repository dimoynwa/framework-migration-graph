"""E2E tests for the six-stage split migration harness (015)."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest


def _evict_mcp_modules() -> None:
    for name in list(sys.modules):
        if name == "migration_oracle.mcp.config" or name.startswith("migration_oracle.mcp."):
            sys.modules.pop(name, None)


async def _tool_names(mcp) -> set[str]:
    tools = await mcp.list_tools()
    return {t.name for t in tools}


def _fresh_server(mode: str, stage: str | None = None):
    os.environ["MIGRATION_MODE"] = mode
    if stage is None:
        os.environ.pop("MCP_ACTIVE_STAGE", None)
    else:
        os.environ["MCP_ACTIVE_STAGE"] = stage
    _evict_mcp_modules()
    import migration_oracle.mcp.server as srv

    return srv.mcp


@pytest.mark.asyncio
async def test_preview_stage_zero_mutation_tools():
    """Preview session exposes only get_pending_steps and get_migration_contexts."""
    mcp = _fresh_server("full", stage="preview")
    names = await _tool_names(mcp)
    assert names == {"get_pending_steps", "get_migration_contexts"}


@pytest.mark.asyncio
async def test_gap_check_stage_includes_write_flags():
    mcp = _fresh_server("full", stage="gap-check")
    names = await _tool_names(mcp)
    assert "write_gap_check_flags" in names
    assert "add_manual_step" not in names
    assert "update_step_status" not in names


def test_six_stage_happy_path_tool_flow():
    """Simulate the six-command happy path with gap-check flag and clarify exclusion."""
    from migration_oracle.mcp.tools.context import (
        add_manual_step,
        close_migration_context,
        get_pending_steps,
        update_step_status,
        write_gap_check_flags,
    )

    flag = {"type": "applicability_uncertain", "message": "uncertain rule"}
    pending_after_exclude = [{"step_id": "step-2", "summary": "remaining"}]

    with (
        patch(
            "migration_oracle.mcp.tools.context.validate_context_id_for_stage",
            return_value=None,
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.write_gap_check_flags",
            return_value=[flag],
        ) as mock_flags,
        patch(
            "migration_oracle.mcp.tools.context.context_queries.get_context_metadata",
            return_value={"context_id": "ctx-1", "status": "in-progress"},
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.add_manual_step",
            return_value={"step_id": "manual-1", "summary": "custom"},
        ),
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
            side_effect=[pending_after_exclude, pending_after_exclude, []],
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.auto_close_write",
            return_value={"migration_status": "complete"},
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.auto_resolve_deferred_steps",
            return_value=[],
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.close_migration_context",
            return_value={
                "context_id": "ctx-1",
                "migration_status": "complete",
                "completed_steps": ["step-2"],
                "skipped_steps": [],
                "completed_at": "now",
                "notes": "",
            },
        ),
    ):
        # 2. gap-check
        gap = write_gap_check_flags(context_id="ctx-1", flags=[flag])
        assert gap["flag_count"] == 1

        # 3. clarify — manual step + exclude
        manual = add_manual_step(
            context_id="ctx-1",
            summary="Update security config",
            instruction="Review filter chain",
        )
        assert manual["step_id"] == "manual-1"

        excluded = update_step_status(
            context_id="ctx-1",
            step_id="step-1",
            outcome="excluded",
        )
        assert excluded["outcome"] == "excluded"
        assert excluded["context_auto_closed"] is False

        # 5. execute — complete remaining
        pending = get_pending_steps(context_id="ctx-1")
        assert pending["total_pending"] == 1

        done = update_step_status(
            context_id="ctx-1",
            step_id="step-2",
            outcome="completed",
        )
        assert done["context_auto_closed"] is True

        # 6. feedback
        closed = close_migration_context(
            context_id="ctx-1",
            final_status="complete",
        )
        assert closed["migration_status"] == "complete"

    mock_flags.assert_called_once()

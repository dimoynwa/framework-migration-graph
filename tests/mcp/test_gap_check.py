"""Tests for gap-check stage tools (015-split-migration-harness)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_write_gap_check_flags_idempotent():
    """Calling twice with same flags returns deduplicated list."""
    from migration_oracle.mcp.tools.context import write_gap_check_flags

    flag = {
        "type": "truncation",
        "reference": "rule-1",
        "message": "Rules capped at 50",
    }
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.write_gap_check_flags",
        side_effect=[
            [flag],
            [flag],
        ],
    ) as mock_write:
        first = write_gap_check_flags(context_id="ctx-1", flags=[flag])
        second = write_gap_check_flags(context_id="ctx-1", flags=[flag])

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert first["flags"] == second["flags"]
    assert mock_write.call_count == 2
    assert mock_write.call_args_list[1].kwargs.get("overwrite") is False


def test_write_gap_check_flags_invalid_context():
    from migration_oracle.mcp.tools.context import write_gap_check_flags

    with patch(
        "migration_oracle.mcp.tools.context.validate_context_id_for_stage",
        return_value=None,
    ), patch(
        "migration_oracle.mcp.tools.context.context_queries.write_gap_check_flags",
        side_effect=ValueError("Context not found: bad"),
    ):
        result = write_gap_check_flags(
            context_id="bad",
            flags=[{"type": "truncation", "message": "test"}],
        )
    assert result["status"] == "error"
    assert result["error_code"] == "context_not_found"


def test_create_migration_context_caches_diagnostics():
    from migration_oracle.mcp.tools.context import create_migration_context

    ctx = {
        "context_id": "ctx-1",
        "project_id": "demo",
        "from_version": "3.3.0",
        "to_version": "3.4.0",
        "framework": "Spring Boot",
        "migration_status": "in-progress",
        "scanned_entities": [],
        "completed_steps": [],
        "skipped_steps": [],
        "created_at": "now",
        "completed_at": None,
        "notes": "",
        "created": True,
    }
    diagnostics = {
        "scanned_total": 10,
        "rules_included": 50,
        "rules_excluded_by_entity_filter": 5,
        "rules_via_safety_net": 2,
        "rules_capped_at": 50,
    }
    with (
        patch(
            "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
            return_value=ctx,
        ),
        patch(
            "migration_oracle.mcp.tools.context.resolve_version",
            side_effect=lambda fw, ver, **kw: type("R", (), {
                "nodeId": "n1",
                "resolvedVersion": ver,
                "rounded": False,
                "aheadOfCatalogue": False,
                "stubCreated": False,
            })(),
        ),
        patch(
            "migration_oracle.mcp.tools.context.context_queries.set_diagnostics_on_create",
        ) as mock_diag,
    ):
        result = create_migration_context(
            project_id="demo",
            from_version="3.3.0",
            to_version="3.4.0",
            framework="Spring Boot",
            diagnostics=diagnostics,
        )

    assert result["diagnostics_cached"] is True
    mock_diag.assert_called_once_with(context_id="ctx-1", diagnostics=diagnostics)

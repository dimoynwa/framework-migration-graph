"""Tests for spec 010 context fixes: version normalisation, zombie cleanup, stepNotes, scope tier."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from migration_oracle.mcp.graph.queries.context import VersionNotInGraphError


# ---------------------------------------------------------------------------
# US1 — Version normalisation & zombie cleanup
# ---------------------------------------------------------------------------

@patch("migration_oracle.mcp.tools.context.context_queries.delete_zombie_context")
@patch("migration_oracle.mcp.tools.context.context_queries.create_or_get_context")
def test_normalises_patch_version(mock_create, mock_delete):
    mock_create.return_value = {
        "context_id": "ctx-1",
        "project_id": "proj",
        "from_version": "3.5.0",
        "to_version": "4.1.0",
        "framework": "spring-boot",
        "migration_status": "in-progress",
        "scanned_entities": [],
        "completed_steps": [],
        "skipped_steps": [],
        "failed_steps": [],
        "created_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "notes": "",
        "created": True,
    }

    from migration_oracle.mcp.tools.context import create_migration_context

    result = create_migration_context(
        project_id="proj",
        from_version="3.5.12",
        to_version="4.1.0",
        framework="spring-boot",
    )

    assert result["status"] == "ok"
    mock_create.assert_called_once_with(
        project_id="proj",
        from_version="3.5.0",
        to_version="4.1.0",
        framework="spring-boot",
        scanned_entities=[],
    )
    mock_delete.assert_not_called()


@patch("migration_oracle.mcp.tools.context.context_queries.delete_zombie_context")
@patch(
    "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
    side_effect=VersionNotInGraphError("3.5.0", ["3.3.0", "3.4.0"]),
)
def test_version_not_in_graph(mock_create, mock_delete):
    from migration_oracle.mcp.tools.context import create_migration_context

    result = create_migration_context(
        project_id="proj",
        from_version="3.5.0",
        to_version="4.1.0",
        framework="spring-boot",
    )

    assert result["status"] == "error"
    assert result["error_code"] == "version_not_in_graph"
    assert "hint" in result
    assert "3.3.0" in result["hint"] or "3.4.0" in result["hint"]


@patch("migration_oracle.mcp.tools.context.context_queries.delete_zombie_context")
@patch(
    "migration_oracle.mcp.tools.context.context_queries.create_or_get_context",
    side_effect=VersionNotInGraphError("3.5.0", []),
)
def test_zombie_cleanup_on_version_miss(mock_create, mock_delete):
    from migration_oracle.mcp.tools.context import create_migration_context

    create_migration_context(
        project_id="proj",
        from_version="3.5.12",
        to_version="4.1.0",
        framework="spring-boot",
    )

    mock_delete.assert_called_once_with(
        project_id="proj",
        from_version="3.5.0",
        to_version="4.1.0",
    )


# ---------------------------------------------------------------------------
# US4 — stepNotes persistence
# ---------------------------------------------------------------------------

@patch("migration_oracle.mcp.tools.context.context_queries.auto_close_write")
@patch("migration_oracle.mcp.tools.context.context_queries.get_pending_steps", return_value=[])
@patch("migration_oracle.mcp.tools.context.context_queries.record_step_outcome")
def test_stepnotes_persisted(mock_record, mock_pending, mock_close):
    mock_record.return_value = {
        "context_id": "ctx-1",
        "completed_count": 1,
        "skipped_count": 0,
        "migration_status": "in-progress",
    }
    mock_close.return_value = {"migration_status": "complete"}

    from migration_oracle.mcp.tools.context import update_step_status

    update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="skipped",
        reason="already handled",
    )

    mock_record.assert_called_once_with(
        context_id="ctx-1",
        step_id="step-1",
        outcome="skipped",
        reason="already handled",
    )


@patch("migration_oracle.mcp.tools.context.context_queries.auto_close_write")
@patch("migration_oracle.mcp.tools.context.context_queries.get_pending_steps", return_value=[MagicMock()])
@patch("migration_oracle.mcp.tools.context.context_queries.record_step_outcome")
def test_no_entry_without_reason(mock_record, mock_pending, mock_close):
    mock_record.return_value = {
        "context_id": "ctx-1",
        "completed_count": 0,
        "skipped_count": 1,
        "migration_status": "in-progress",
    }

    from migration_oracle.mcp.tools.context import update_step_status

    update_step_status(
        context_id="ctx-1",
        step_id="step-1",
        outcome="skipped",
        reason="",
    )

    mock_record.assert_called_once_with(
        context_id="ctx-1",
        step_id="step-1",
        outcome="skipped",
        reason="",
    )


# ---------------------------------------------------------------------------
# US5 — Scopeless steps not dropped
# ---------------------------------------------------------------------------

@patch(
    "migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier",
    return_value=[
        {
            "entity_name": "com.example.Foo",
            "entity_type": "JavaClass",
            "step_id": "step-1",
            "rule_id": "rule-1",
            "summary": "Fix Foo",
            "scope": None,
            "severity": "high",
        }
    ],
)
def test_scope_tier_returns_scopeless_steps(mock_get):
    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(
        context_id="ctx-1",
        scope="api-surface",
        severity_threshold="medium",
    )

    hits = result["hits"]
    assert len(hits) == 1
    assert hits[0]["scope"] is None


# ---------------------------------------------------------------------------
# E2E chain test (T029)
# ---------------------------------------------------------------------------

@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
@patch("migration_oracle.mcp.tools.context.context_queries.create_or_get_context")
def test_patch_version_full_chain(mock_create, mock_get_steps):
    mock_create.return_value = {
        "context_id": "ctx-chain",
        "project_id": "proj",
        "from_version": "3.5.0",
        "to_version": "4.1.0",
        "framework": "spring-boot",
        "migration_status": "in-progress",
        "scanned_entities": [],
        "completed_steps": [],
        "skipped_steps": [],
        "failed_steps": [],
        "created_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "notes": "",
        "created": True,
    }
    mock_get_steps.return_value = [
        {
            "entity_name": "com.example.Foo",
            "entity_type": "JavaClass",
            "step_id": "step-1",
            "rule_id": "rule-1",
            "summary": "Fix",
            "scope": "api-surface",
            "severity": "high",
        }
    ]

    from migration_oracle.mcp.tools.context import (
        create_migration_context,
        get_steps_for_scope_tier,
    )

    ctx_result = create_migration_context(
        project_id="proj",
        from_version="3.5.12",
        to_version="4.1.0",
        framework="spring-boot",
    )

    assert ctx_result["status"] == "ok"
    context_id = ctx_result["context_id"]
    assert isinstance(context_id, str) and context_id

    mock_create.assert_called_once_with(
        project_id="proj",
        from_version="3.5.0",
        to_version="4.1.0",
        framework="spring-boot",
        scanned_entities=[],
    )

    steps_result = get_steps_for_scope_tier(
        context_id=context_id,
        scope="API",
        severity_threshold="mandatory",
    )

    assert len(steps_result["hits"]) > 0

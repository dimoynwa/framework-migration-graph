"""Unit tests for get_migration_contexts tool (T021)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from migration_oracle.mcp.tools.context import get_migration_contexts


def _ctx_row(
    ctx_id="ctx-1",
    project_id="proj-x",
    from_v="3.5.12",
    to_v="4.0.6",
    framework="Spring Boot",
    status="in-progress",
    created="2026-01-01T00:00:00",
    updated="2026-01-02T00:00:00",
    completed=0,
    failed=0,
    skipped=0,
    deferred=0,
    excluded=0,
    has_gap_check_flags=False,
):
    return {
        "id": ctx_id,
        "projectId": project_id,
        "fromVersion": from_v,
        "toVersion": to_v,
        "framework": framework,
        "status": status,
        "createdAt": created,
        "updatedAt": updated,
        "completed_count": completed,
        "failed_count": failed,
        "skipped_count": skipped,
        "deferred_count": deferred,
        "excluded_count": excluded,
        "has_gap_check_flags": has_gap_check_flags,
    }


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_zero_contexts_returns_empty_list_not_error(mock_q):
    """get_migration_contexts with zero contexts returns {count: 0, contexts: []} — not an error."""
    mock_q.get_migration_contexts.return_value = []

    result = get_migration_contexts(project_id="proj-x")
    assert result["status"] == "ok"
    assert result["count"] == 0
    assert result["contexts"] == []


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_one_context_returned_with_full_shape(mock_q):
    """get_migration_contexts with one context returns full shape per contract."""
    mock_q.get_migration_contexts.return_value = [_ctx_row()]

    result = get_migration_contexts(project_id="proj-x")
    assert result["status"] == "ok"
    assert result["count"] == 1
    ctx = result["contexts"][0]
    assert ctx["id"] == "ctx-1"
    assert ctx["fromVersion"] == "3.5.12"
    assert ctx["toVersion"] == "4.0.6"
    assert ctx["status"] == "in-progress"
    assert "outcome_counts" in ctx
    assert ctx["outcome_counts"]["deferred"] == 0


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_outcome_counts_shape(mock_q):
    """outcome_counts includes completed/failed/skipped/deferred/excluded."""
    mock_q.get_migration_contexts.return_value = [
        _ctx_row(completed=5, failed=1, skipped=2, deferred=1, excluded=2, has_gap_check_flags=True)
    ]

    result = get_migration_contexts(project_id="proj-x")
    ctx = result["contexts"][0]
    counts = ctx["outcome_counts"]
    assert counts["completed"] == 5
    assert counts["failed"] == 1
    assert counts["skipped"] == 2
    assert counts["deferred"] == 1
    assert counts["excluded"] == 2
    assert ctx["has_gap_check_flags"] is True


def test_empty_project_id_returns_error():
    """Empty project_id returns error without hitting DB."""
    result = get_migration_contexts(project_id="")
    assert result["status"] == "error"
    assert result["error_code"] == "missing_project_id"


@patch("migration_oracle.mcp.tools.context.context_queries")
def test_framework_filter_passed_to_query(mock_q):
    """framework parameter is passed through to the query layer."""
    mock_q.get_migration_contexts.return_value = []

    get_migration_contexts(project_id="proj-x", framework="Spring Boot")
    mock_q.get_migration_contexts.assert_called_once_with(
        project_id="proj-x", framework="Spring Boot"
    )

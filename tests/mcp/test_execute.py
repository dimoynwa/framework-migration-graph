"""Tests for execute stage context discovery (015-split-migration-harness)."""

from __future__ import annotations

from unittest.mock import patch

from migration_oracle.mcp.tools.context import resolve_execute_context


def test_resolve_execute_context_auto_discover_single():
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_in_progress_contexts",
        return_value=[
            {
                "context_id": "ctx-1",
                "project_id": "demo",
                "from_version": "3.3.0",
                "to_version": "3.4.0",
                "framework": "Spring Boot",
            }
        ],
    ):
        result = resolve_execute_context(context_id=None, project_id="demo")

    assert result["status"] == "ok"
    assert result["context_id"] == "ctx-1"


def test_resolve_execute_context_ambiguous():
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.get_in_progress_contexts",
        return_value=[
            {
                "context_id": "ctx-1",
                "framework": "Spring Boot",
                "from_version": "3.3.0",
                "to_version": "3.4.0",
            },
            {
                "context_id": "ctx-2",
                "framework": "Spring Boot",
                "from_version": "3.4.0",
                "to_version": "3.5.0",
            },
        ],
    ):
        result = resolve_execute_context(context_id=None, project_id="demo")

    assert result["status"] == "error"
    assert result["error_code"] == "ambiguous_context"
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["context_id"] == "ctx-1"


def test_resolve_execute_context_explicit_id():
    with patch(
        "migration_oracle.mcp.tools.context.context_queries.context_exists",
        return_value=True,
    ):
        result = resolve_execute_context(context_id="ctx-1")

    assert result["status"] == "ok"
    assert result["context_id"] == "ctx-1"

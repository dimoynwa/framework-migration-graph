"""Severity threshold validation tests for get_steps_for_scope_tier."""

from unittest.mock import patch


def test_unknown_threshold_returns_error():
    """Unknown severity_threshold returns documented error shape."""
    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(
        context_id="ctx-1",
        scope="api-surface",
        severity_threshold="urgent",
    )
    assert result["status"] == "error"
    assert result["error_code"] == "invalid_severity_threshold"


def test_valid_thresholds_accepted():
    """All four valid threshold values are accepted without error."""
    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    for threshold in ("low", "medium", "high", "critical"):
        with patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier") as mock:
            mock.return_value = []
            result = get_steps_for_scope_tier(
                context_id="ctx-1",
                scope="api-surface",
                severity_threshold=threshold,
            )
            assert result.get("status") == "ok", f"threshold={threshold} should be accepted"


def test_high_threshold_excludes_low_medium():
    """severity_threshold='high' excludes steps with severity low or medium."""
    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    mock_rows = [
        {"entity_name": "Foo", "entity_type": "Class", "step_id": "s1", "rule_id": "r1",
         "summary": "x", "scope": "api-surface", "severity": "low"},
        {"entity_name": "Bar", "entity_type": "Class", "step_id": "s2", "rule_id": "r2",
         "summary": "y", "scope": "api-surface", "severity": "medium"},
        {"entity_name": "Baz", "entity_type": "Class", "step_id": "s3", "rule_id": "r3",
         "summary": "z", "scope": "api-surface", "severity": "high"},
        {"entity_name": "Qux", "entity_type": "Class", "step_id": "s4", "rule_id": "r4",
         "summary": "w", "scope": "api-surface", "severity": "critical"},
    ]

    with patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier") as mock:
        mock.return_value = [r for r in mock_rows if r["severity"] in ("high", "critical")]
        result = get_steps_for_scope_tier(
            context_id="ctx-1",
            scope="api-surface",
            severity_threshold="high",
        )

    assert result["status"] == "ok"
    returned_severities = {h["severity"] for h in result["hits"]}
    assert "low" not in returned_severities
    assert "medium" not in returned_severities


def test_medium_threshold_excludes_only_low():
    """severity_threshold='medium' excludes only low severity steps."""
    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    with patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier") as mock:
        mock.return_value = [
            {"entity_name": "Bar", "entity_type": "Class", "step_id": "s2", "rule_id": "r2",
             "summary": "y", "scope": "api-surface", "severity": "medium"},
            {"entity_name": "Baz", "entity_type": "Class", "step_id": "s3", "rule_id": "r3",
             "summary": "z", "scope": "api-surface", "severity": "high"},
        ]
        result = get_steps_for_scope_tier(
            context_id="ctx-1",
            scope="api-surface",
            severity_threshold="medium",
        )

    assert result["status"] == "ok"
    returned_severities = {h["severity"] for h in result["hits"]}
    assert "low" not in returned_severities


def test_nonexistent_context_handled():
    """A nonexistent context_id propagates from the query layer (not blocked by threshold guard)."""
    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    with patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier") as mock:
        mock.return_value = []
        result = get_steps_for_scope_tier(
            context_id="nonexistent-ctx",
            scope="api-surface",
            severity_threshold="medium",
        )

    assert result.get("status") == "ok"
    assert result["hits"] == []

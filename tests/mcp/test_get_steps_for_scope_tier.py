"""Tests for spec 011 US6: get_steps_for_scope_tier returns scopeless steps and passes scope param."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_step_row(
    step_id: str = "s1",
    scope: str | None = "build",
    severity: str | None = "high",
    entity_name: str | None = None,
) -> dict:
    return {
        "entity_name": entity_name,
        "entity_type": "Class",
        "step_id": step_id,
        "rule_id": f"rule-{step_id}",
        "summary": f"Step {step_id}",
        "scope": scope,
        "severity": severity,
    }


@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
def test_matching_scope_returned(mock_get):
    """Steps with scope matching the requested scope are included in hits."""
    mock_get.return_value = [_make_step_row(step_id="s1", scope="build", severity="high")]

    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(context_id="ctx-1", scope="build")

    assert result["total"] >= 1
    assert result["hits"][0]["scope"] == "build"


@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
def test_scopeless_step_returned_as_null(mock_get):
    """Steps with scope=None (scopeless) are included with scope: null in the response."""
    mock_get.return_value = [_make_step_row(step_id="s2", scope=None, severity=None)]

    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(context_id="ctx-1", scope="build")

    assert result["total"] >= 1
    assert result["hits"][0]["scope"] is None


@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
def test_mismatched_scope_excluded(mock_get):
    """Steps with a different scope are filtered out by the query layer (not returned)."""
    mock_get.return_value = []  # query layer handles the filtering

    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(context_id="ctx-1", scope="build")

    assert result["total"] == 0
    assert result["hits"] == []


@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
def test_scope_param_passed_to_cypher(mock_get):
    """get_steps_for_scope_tier passes scope down to the query layer."""
    mock_get.return_value = []

    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    get_steps_for_scope_tier(context_id="ctx-1", scope="api-surface")

    mock_get.assert_called_once_with(
        context_id="ctx-1",
        scope="api-surface",
        min_severity="medium",
    )


@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
def test_total_gt_zero_when_pending(mock_get):
    """total > 0 when the query returns rows."""
    mock_get.return_value = [
        _make_step_row(step_id="s1", scope="build"),
        _make_step_row(step_id="s2", scope=None, severity=None),
    ]

    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(context_id="ctx-1", scope="build")

    assert result["total"] > 0


# ---------------------------------------------------------------------------
# T051: severity threshold filtering (FR-D06 / ISSUE-003)
# ---------------------------------------------------------------------------

@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
def test_high_threshold_returns_only_high_severity(mock_get):
    """severity_threshold='high' returns only high-severity steps from the query layer."""
    mock_get.return_value = [
        _make_step_row(step_id="s-high", scope="api-surface", severity="high", entity_name="com.example.Foo"),
    ]

    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(context_id="ctx-1", scope="api-surface", severity_threshold="high")

    assert result["status"] == "ok"
    assert all(h["severity"] in ("high", "critical") for h in result["hits"] if h["severity"])
    mock_get.assert_called_once_with(context_id="ctx-1", scope="api-surface", min_severity="high")


@patch("migration_oracle.mcp.tools.context.context_queries.get_steps_for_scope_tier")
def test_low_threshold_returns_all_severities(mock_get):
    """severity_threshold='low' returns all severity levels."""
    mock_get.return_value = [
        _make_step_row(step_id="s-high", scope="build", severity="high", entity_name="com.example.A"),
        _make_step_row(step_id="s-med", scope="build", severity="medium", entity_name="com.example.B"),
        _make_step_row(step_id="s-low", scope="build", severity="low", entity_name="com.example.C"),
    ]

    from migration_oracle.mcp.tools.context import get_steps_for_scope_tier

    result = get_steps_for_scope_tier(context_id="ctx-1", scope="build", severity_threshold="low")

    assert result["status"] == "ok"
    assert result["total"] == 3
    mock_get.assert_called_once_with(context_id="ctx-1", scope="build", min_severity="low")

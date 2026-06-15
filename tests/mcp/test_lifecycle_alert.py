"""Tests for spec 011 US8: lifecycle alerts surfaced via analyze_upgrade_path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

_VER_ROW = {"node_id": "fake-id-0", "resolved_version": "3.5.0", "sortable": 3005000}


def _make_alert(
    message: str = "Spring Security 7 changes default CSRF policy.",
    category: str = "security",
    phase: str = "pre-migration",
) -> dict:
    return {"message": message, "category": category, "phase": phase}


def _make_rows_with_alerts(alerts: list[dict]) -> list[dict]:
    return [
        {
            "release_version": "4.0.0",
            "release_sortable": 400000000,
            "rules": [
                {
                    "rule_id": "r1",
                    "rule_type": "MigrationRule",
                    "statement": "Upgrade",
                    "action_step": None,
                    "source_url": None,
                    "reason": None,
                    "solution": None,
                    "title": "Upgrade",
                    "change_type": "breaking",
                    "reason_type": None,
                    "entity_classification": None,
                    "affected_entities": [],
                    "steps": [],
                    "scopes": [{"scope": "api-surface", "severity": "high"}],
                    "recipes": [],
                }
            ],
            "lifecycle_events": [],
            "raw_phase_alerts": alerts,
        }
    ]


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_alerts_returned_when_include_lifecycle_true(mock_session_ctx):
    """lifecycle_alerts is non-empty when include_lifecycle=True and alerts exist."""
    alerts = [_make_alert()]
    rows = _make_rows_with_alerts(alerts)
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
        include_lifecycle=True,
    )

    assert result["status"] == "ok"
    assert len(result["lifecycle_alerts"]) >= 1


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_empty_when_include_lifecycle_false(mock_session_ctx):
    """lifecycle_alerts is empty when include_lifecycle=False."""
    alerts = [_make_alert()]
    rows = _make_rows_with_alerts(alerts)
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
        include_lifecycle=False,
    )

    assert result["lifecycle_alerts"] == []


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_alert_properties_projected(mock_session_ctx):
    """Each lifecycle alert has message, category, and phase fields."""
    alerts = [_make_alert(message="CSRF policy changed", category="security", phase="pre-migration")]
    rows = _make_rows_with_alerts(alerts)
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
        include_lifecycle=True,
    )

    alert = result["lifecycle_alerts"][0]
    assert "message" in alert
    assert "category" in alert
    assert "phase" in alert
    assert alert["message"] == "CSRF policy changed"


@patch("migration_oracle.pipeline.populator.write_session")
def test_idempotent_merge(mock_write_ctx):
    """seed_lifecycle_alerts uses MERGE so re-seeding produces no duplicates."""
    session = MagicMock()
    mock_write_ctx.return_value.__enter__.return_value = session
    session.run.return_value = MagicMock()

    from migration_oracle.pipeline.populator import seed_lifecycle_alerts

    seed_lifecycle_alerts()
    seed_lifecycle_alerts()

    for call_args in session.run.call_args_list:
        cypher = call_args[0][0] if call_args[0] else ""
        if cypher.strip():
            assert "MERGE" in cypher, f"Expected MERGE in Cypher, got: {cypher[:100]}"

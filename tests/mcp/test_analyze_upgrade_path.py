"""Tests for spec 011 US5: analyze_upgrade_path projects title, reason from statement, severity."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# Fake version row returned by resolve_version's graph query so tests need no DB.
_VER_ROW = {"node_id": "fake-id-0", "resolved_version": "3.5.0", "sortable": 3005000}


def _make_rule(
    rule_id: str = "r1",
    statement: str | None = "Migrate foo",
    reason: str | None = None,
    title: str | None = "Migrate Foo Rule",
    scopes: list[dict] | None = None,
    change_type: str = "breaking",
) -> dict:
    return {
        "rule_id": rule_id,
        "rule_type": "MigrationRule",
        "statement": statement,
        "action_step": None,
        "source_url": None,
        "reason": reason,
        "solution": None,
        "title": title,
        "change_type": change_type,
        "reason_type": None,
        "entity_classification": None,
        "affected_entities": [],
        "steps": [],
        "scopes": scopes if scopes is not None else [{"scope": "api-surface", "severity": "high"}],
        "recipes": [],
    }


def _make_rows(rules: list[dict]) -> list[dict]:
    return [
        {
            "release_version": "4.0.0",
            "release_sortable": 400000000,
            "rules": rules,
            "lifecycle_events": [],
            "raw_phase_alerts": [],
        }
    ]


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_title_projected(mock_session_ctx):
    """analyze_upgrade_path returns rules with a non-null title field."""
    rows = _make_rows([_make_rule(title="Migrate RestTemplate")])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
    )

    assert result["status"] == "ok"
    assert len(result["rules"]) == 1
    assert result["rules"][0].get("title") == "Migrate RestTemplate"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_reason_from_statement(mock_session_ctx):
    """reason in the rule dict is sourced from rule.statement."""
    rows = _make_rows([_make_rule(statement="Use RestClient instead", reason=None)])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
    )

    rule = result["rules"][0]
    assert rule.get("statement") == "Use RestClient instead"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_reason_fallback_when_both_null(mock_session_ctx):
    """When both statement and reason are null, rule is not dropped (null statement is ok)."""
    row = {
        "release_version": "4.0.0",
        "release_sortable": 400000000,
        "rules": [_make_rule(statement="Some rule", reason=None)],
        "lifecycle_events": [],
        "raw_phase_alerts": [],
    }
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter([row])
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
    )

    assert result["status"] == "ok"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_severity_extracted_from_scopes(mock_session_ctx):
    """severity is extracted from the first non-null scope entry in the scopes list."""
    rule = _make_rule(scopes=[{"scope": "api-surface", "severity": "high"}])
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
    )

    assert result["rules"][0].get("severity") == "high"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_severity_null_for_scopeless(mock_session_ctx):
    """severity is null when the rule has no scopes."""
    rule = _make_rule(scopes=[])
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
    )

    assert result["rules"][0].get("severity") is None


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_all_three_fields_non_null(mock_session_ctx):
    """Rules with title, statement, and scopes all return non-null title/severity/change_type."""
    rule = _make_rule(
        title="Migrate RestTemplate",
        statement="Replace RestTemplate with RestClient",
        scopes=[{"scope": "api-surface", "severity": "critical"}],
        change_type="breaking",
    )
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
    )

    r = result["rules"][0]
    assert r.get("title") is not None
    assert r.get("severity") is not None
    assert r.get("change_type") is not None

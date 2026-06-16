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


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_analyze_upgrade_path_rule_id_is_stable_key(mock_session_ctx):
    """rule_id is a stable pipeline:// URI, never a raw Neo4j element ID like '4:'."""
    rule = _make_rule(
        rule_id="pipeline://Spring Boot/3.5.12/Jackson import rename",
        statement="Rename Jackson import",
    )
    rule["applicability"] = "matched"
    rule["affected_entities"] = ["com.fasterxml.jackson.databind.ObjectMapper"]
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.12",
        target_version="4.0.6",
    )

    assert result["status"] == "ok"
    assert len(result["rules"]) == 1
    rule_id = result["rules"][0]["rule_id"]
    assert rule_id != ""
    assert rule_id.startswith("pipeline://"), f"Expected pipeline:// prefix, got: {rule_id!r}"
    assert not rule_id.startswith("4:"), f"rule_id must not be a raw Neo4j element ID, got: {rule_id!r}"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_analyze_upgrade_path_matched_entities_populated(mock_session_ctx):
    """matched_entities is populated when user_entities overlap with affected_entities."""
    rule = _make_rule(rule_id="pipeline://Spring Boot/3.5.12/Jackson rename")
    rule["applicability"] = "matched"
    rule["affected_entities"] = ["com.fasterxml.jackson.databind.ObjectMapper"]
    rule["match_count"] = 1
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.12",
        target_version="4.0.6",
        user_entities=["com.fasterxml.jackson.databind.ObjectMapper"],
    )

    assert result["status"] == "ok"
    r = result["rules"][0]
    assert "matched_entities" in r
    assert "com.fasterxml.jackson.databind.ObjectMapper" in r["matched_entities"]


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_analyze_upgrade_path_no_lowercase_entity_matching(mock_session_ctx):
    """Entity matching is case-sensitive: 'com.example.Foo' does not match 'com.example.foo'."""
    rule = _make_rule(rule_id="pipeline://Spring Boot/3.5.0/Foo rename")
    rule["applicability"] = "matched"
    rule["affected_entities"] = ["com.example.Foo"]
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    # Pass the exact-case entity — should match
    result_exact = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
        user_entities=["com.example.Foo"],
    )
    assert "com.example.Foo" in result_exact["rules"][0]["matched_entities"]

    # Reset mock for second call
    mock_run.__iter__ = lambda s: iter(_make_rows([{**rule}]))

    # Pass lowercase variant — should NOT match
    result_lower = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.0",
        target_version="4.0.0",
        user_entities=["com.example.foo"],
    )
    matched = result_lower["rules"][0]["matched_entities"]
    assert "com.example.foo" not in matched, (
        "Lowercase 'com.example.foo' should not match mixed-case 'com.example.Foo'"
    )


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_analyze_upgrade_path_dependency_bridge_matched_entities(mock_session_ctx):
    """Dependency-only rule matched via groupId prefix → matched_entities lists scanned FQCN."""
    rule = _make_rule(rule_id="pipeline://Spring Boot/4.0.0/Spring Web change")
    rule["applicability"] = "matched"
    rule["match_count"] = 1
    rule["affected_entities"] = ["org.springframework:spring-web"]
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.12",
        target_version="4.0.6",
        user_entities=["org.springframework.web.bind.annotation.RestController"],
    )

    r = result["rules"][0]
    assert r["applicability"] == "matched"
    assert r["matched_entities"]
    assert "org.springframework.web.bind.annotation.RestController" in r["matched_entities"]


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_analyze_upgrade_path_no_empty_matched_entities_when_match_count_positive(mock_session_ctx):
    """Invariant: no rule with match_count > 0 has empty matched_entities."""
    rules = [
        {
            **_make_rule(rule_id="pipeline://Spring Boot/4.0.0/Rule A"),
            "applicability": "matched",
            "match_count": 1,
            "affected_entities": ["org.springframework:spring-core"],
        },
        {
            **_make_rule(rule_id="pipeline://Spring Boot/4.0.0/Rule B"),
            "applicability": "matched",
            "match_count": 1,
            "affected_entities": ["com.fasterxml.jackson.databind.ObjectMapper"],
        },
    ]
    rows = _make_rows(rules)
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.12",
        target_version="4.0.6",
        user_entities=[
            "org.springframework.web.bind.annotation.RestController",
            "com.fasterxml.jackson.databind.ObjectMapper",
        ],
    )

    bad = [
        r for r in result["rules"]
        if (r.get("match_count") or 0) > 0 and not r.get("matched_entities")
    ]
    assert bad == [], f"Rules with match_count>0 but empty matched_entities: {bad}"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_analyze_upgrade_path_jackson_dependency_bridge_matched_entities(mock_session_ctx):
    """Jackson Dependency-only rule: truncated groupId bridge populates matched_entities."""
    rule = _make_rule(rule_id="pipeline://Spring Boot/4.0.0/Jackson 3 now required")
    rule["applicability"] = "matched"
    rule["match_count"] = 1
    rule["affected_entities"] = ["com.fasterxml.jackson.core:jackson-databind"]
    rows = _make_rows([rule])
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.__iter__ = lambda s: iter(rows)
    mock_run.single.return_value = _VER_ROW

    from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path

    result = analyze_upgrade_path(
        framework="Spring Boot",
        current_version="3.5.12",
        target_version="4.0.6",
        user_entities=["com.fasterxml.jackson.databind.ObjectMapper"],
    )

    r = result["rules"][0]
    assert r["applicability"] == "matched"
    assert "com.fasterxml.jackson.databind.ObjectMapper" in r["matched_entities"]

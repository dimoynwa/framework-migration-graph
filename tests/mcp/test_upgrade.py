"""Tests for upgrade MCP tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path, build_recipe_plan
from migration_oracle.models.graph import VersionResolutionFailure

_FAILURE = VersionResolutionFailure(
    status="NO_CANDIDATE", framework="Spring Boot",
    requestedVersion="3.5.6", candidatesConsidered=[],
)


def test_analyze_upgrade_path_empty_graph():
    with patch(
        "migration_oracle.mcp.tools.upgrade.upgrade_queries.analyze_upgrade_path",
        return_value=[],
    ), patch("migration_oracle.mcp.tools.upgrade.resolve_version", return_value=_FAILURE):
        result = analyze_upgrade_path(
            framework="Spring Boot",
            current_version="3.5.6",
            target_version="4.0.0",
        )
    assert result["status"] == "ok"
    assert result["rules"] == []


def test_analyze_upgrade_path_with_scope_filter():
    rows = [
        {
            "rules": [
                {
                    "statement": "keep",
                    "scopes": [{"scope": "api-surface", "severity": "high"}],
                },
            ]
        }
    ]
    with patch(
        "migration_oracle.mcp.tools.upgrade.upgrade_queries.analyze_upgrade_path",
        return_value=rows,
    ) as mock_query, patch(
        "migration_oracle.mcp.tools.upgrade.resolve_version", return_value=_FAILURE
    ):
        result = analyze_upgrade_path(
            framework="Spring Boot",
            current_version="3.5.6",
            target_version="4.0.0",
            scope_filter=["api-surface"],
        )
        mock_query.assert_called_once()
    assert len(result["rules"]) == 1
    assert result["rules"][0]["statement"] == "keep"


def test_analyze_upgrade_path_no_migration_steps():
    rows = [
        {
            "rules": [
                {
                    "statement": "rule",
                    "steps": [],
                    "scopes": [],
                    "recipes": [],
                }
            ]
        }
    ]
    with patch(
        "migration_oracle.mcp.tools.upgrade.upgrade_queries.analyze_upgrade_path",
        return_value=rows,
    ), patch("migration_oracle.mcp.tools.upgrade.resolve_version", return_value=_FAILURE):
        result = analyze_upgrade_path(
            framework="Spring Boot",
            current_version="3.5.6",
            target_version="4.0.0",
        )
    rule = result["rules"][0]
    assert rule["steps"] == []
    assert rule["scopes"] == []


def test_build_recipe_plan_no_automated_by():
    plan = {
        "auto_track": [],
        "manual_track": [{"step_id": "s1", "rule_id": "r1"}],
        "fallback_to_rule_cards": False,
    }
    with patch(
        "migration_oracle.mcp.tools.upgrade.upgrade_queries.build_recipe_plan",
        return_value=plan,
    ), patch("migration_oracle.mcp.tools.upgrade.resolve_version", return_value=_FAILURE):
        result = build_recipe_plan(
            current_version="3.5.6",
            target_version="4.0.0",
        )
    assert result["auto_track"] == []
    assert len(result["manual_track"]) == 1


def test_build_recipe_plan_no_migration_steps():
    plan = {
        "auto_track": [],
        "manual_track": [{"step_id": "", "rule_id": "r1", "action_step": "Do thing"}],
        "fallback_to_rule_cards": True,
    }
    with patch(
        "migration_oracle.mcp.tools.upgrade.upgrade_queries.build_recipe_plan",
        return_value=plan,
    ), patch("migration_oracle.mcp.tools.upgrade.resolve_version", return_value=_FAILURE):
        result = build_recipe_plan(
            current_version="3.5.6",
            target_version="4.0.0",
        )
    assert result["fallback_to_rule_cards"] is True
    assert result["auto_track"] == []


def test_build_recipe_plan_action_step_in_rule_card():
    plan = {
        "auto_track": [],
        "manual_track": [
            {
                "step_id": "",
                "rule_id": "r1",
                "action_step": "Replace WebSecurityConfigurerAdapter",
            }
        ],
        "fallback_to_rule_cards": True,
    }
    with patch(
        "migration_oracle.mcp.tools.upgrade.upgrade_queries.build_recipe_plan",
        return_value=plan,
    ), patch("migration_oracle.mcp.tools.upgrade.resolve_version", return_value=_FAILURE):
        result = build_recipe_plan(
            current_version="3.5.6",
            target_version="4.0.0",
        )
    card = result["manual_track"][0]
    assert card["action_step"] == "Replace WebSecurityConfigurerAdapter"
    assert card["action_step"]


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_build_recipe_plan_dependency_bridge_applicability(mock_session_ctx):
    """Dependency-only rule: Cypher bridge marks matched; matched_entities populated."""
    row = {
        "step_id": "step-bridge-1",
        "rule_id": "pipeline://Spring Boot/4.0.0/Web change",
        "statement": "Web migration",
        "action_step": "",
        "summary": "Update web layer",
        "instruction": "migrate",
        "effort": "mechanical",
        "automatable": True,
        "verification_hint": "",
        "scope": "api-surface",
        "severity": "high",
        "applicability": "matched",
        "match_count": 1,
        "affected_entities": ["org.springframework:spring-web"],
        "recipe_id": None,
        "auto": None,
        "missing_required_params": [],
        "version": "4.0.0",
        "step_index": 1,
    }
    plan_result = MagicMock()
    plan_result.__iter__ = lambda s: iter([row])
    count_result = MagicMock()
    count_result.single.return_value = {"c": 0}
    session = mock_session_ctx.return_value.__enter__.return_value
    session.run.side_effect = [count_result, plan_result]

    from migration_oracle.mcp.graph.queries.upgrade import build_recipe_plan

    result = build_recipe_plan(
        framework="Spring Boot",
        current_version="3.5.12",
        target_version="4.0.6",
        scanned_classes=["org.springframework.web.bind.annotation.RestController"],
        scanned_class_simple=["RestController"],
        scanned_deps_ga=[],
        scanned_dep_artifacts=[],
        scanned_props=[],
        has_entity_filter=True,
    )

    assert len(result["manual_track"]) == 1
    step = result["manual_track"][0]
    assert step["applicability"] == "matched"
    assert "org.springframework.web.bind.annotation.RestController" in step["matched_entities"]

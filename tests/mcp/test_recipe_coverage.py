"""Tests for recipe coverage diagnostic and agent-codemod routing (LP-003)."""

from __future__ import annotations

from unittest.mock import patch

from migration_oracle.mcp.routing import select_executor


def test_select_executor_no_recipe_mechanical_concrete_matched_routes_agent_codemod():
    """Row 3: no recipe, mechanical effort, concrete instruction, matched entity → agent-codemod."""
    step = {
        "recipe_id": None,
        "auto": None,
        "missing_required_params": [],
        "effort": "mechanical",
        "instruction": "rename `javax.persistence.Entity` to `jakarta.persistence.Entity`",
        "applicability": "matched",
    }
    assert select_executor(step) == "agent-codemod"


def test_select_executor_no_recipe_mechanical_no_anchor_routes_human_review():
    """Row 5: no recipe, mechanical effort, no entity anchor → human-review."""
    step = {
        "recipe_id": None,
        "auto": None,
        "missing_required_params": [],
        "effort": "mechanical",
        "instruction": "rename `javax.persistence.Entity` to `jakarta.persistence.Entity`",
        "applicability": "uncertain",
    }
    assert select_executor(step) == "human-review"


def test_select_executor_no_recipe_moderate_concrete_matched_routes_agent_codemod():
    """Row 4: no recipe, moderate effort, concrete instruction, matched entity → agent-codemod."""
    step = {
        "recipe_id": None,
        "auto": None,
        "missing_required_params": [],
        "effort": "moderate",
        "instruction": "replace `import com.fasterxml.jackson.databind.ObjectMapper` with the new import",
        "applicability": "matched",
    }
    assert select_executor(step) == "agent-codemod"


_VER_ROW = {"node_id": "fake-id-0", "resolved_version": "3.5.0", "sortable": 3005000}


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_build_recipe_plan_includes_recipe_diagnostics(mock_session_ctx):
    """build_recipe_plan tool always includes diagnostics.recipes_loaded and recipe_count."""
    # Wire resolve_version's .single() call to return a fake version row (no real DB needed)
    mock_run = mock_session_ctx.return_value.__enter__.return_value.run.return_value
    mock_run.single.return_value = _VER_ROW

    mock_plan = {
        "auto_track": [],
        "manual_track": [{"step_id": "s1", "rule_id": "r1", "summary": "step", "instruction": "do thing",
                           "verification_hint": "", "effort": "mechanical", "blocked_reason": "",
                           "action_step": "", "applicability": "informational", "matched_entities": []}],
        "fallback_to_rule_cards": False,
        "rules_included": 1,
        "excluded_count": 0,
        "uncertain_count": 0,
        "recipes_loaded": False,
        "recipe_count": 0,
    }
    from migration_oracle.mcp.tools.upgrade import build_recipe_plan
    from migration_oracle.mcp.graph.queries import upgrade as upgrade_queries

    with patch.object(upgrade_queries, "build_recipe_plan", return_value=mock_plan):
        result = build_recipe_plan(current_version="3.5.0", target_version="4.0.0")

    assert "diagnostics" in result
    assert result["diagnostics"]["recipes_loaded"] is False
    assert result["diagnostics"]["recipe_count"] == 0

"""Tests for spec 010/011c US3: build_recipe_plan applicability scoring and dedup."""

from __future__ import annotations

from unittest.mock import patch


def _make_row(
    step_id: str,
    summary: str,
    affected: list[str],
    applicability: str = "matched",
) -> dict:
    return {
        "step_id": step_id,
        "rule_id": f"rule-{step_id}",
        "statement": summary,
        "action_step": "",
        "summary": summary,
        "instruction": "do it",
        "effort": "moderate",
        "automatable": False,
        "verification_hint": "",
        "scope": "api-surface",
        "severity": "high",
        "applicability": applicability,
        "match_count": 1 if applicability == "matched" else 0,
        "affected_entities": affected,
        "recipe_id": None,
        "auto": None,
        "missing_required_params": [],
        "version": "3.3.0",
    }


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_applicable_steps(mock_session_ctx):
    rows = [_make_row("s1", "Fix Foo", ["com.example.Foo"], applicability="matched")]
    mock_session_ctx.return_value.__enter__.return_value.run.return_value.__iter__ = lambda s: iter(rows)

    from migration_oracle.mcp.graph.queries.upgrade import build_recipe_plan

    result = build_recipe_plan(
        framework="spring-boot",
        current_version="3.2.0",
        target_version="3.3.0",
        scanned_classes=["com.example.Foo"],
        scanned_class_simple=["Foo"],
        scanned_deps_ga=[],
        scanned_dep_artifacts=[],
        scanned_props=[],
        has_entity_filter=True,
    )

    assert result["manual_track"][0]["applicability"] == "matched"
    assert "com.example.Foo" in result["manual_track"][0]["matched_entities"]


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_not_applicable_steps(mock_session_ctx):
    # Excluded rows are filtered in Cypher (WHERE applicability <> 'excluded').
    # When the mock returns an excluded row it still comes through, so we verify
    # applicability is passed through as-is and matched_entities is empty.
    rows = [_make_row("s1", "Fix Foo", ["com.example.Foo"], applicability="excluded")]
    mock_session_ctx.return_value.__enter__.return_value.run.return_value.__iter__ = lambda s: iter(rows)

    from migration_oracle.mcp.graph.queries.upgrade import build_recipe_plan

    result = build_recipe_plan(
        framework="spring-boot",
        current_version="3.2.0",
        target_version="3.3.0",
        scanned_classes=["com.example.Bar"],
        scanned_class_simple=["Bar"],
        scanned_deps_ga=[],
        scanned_dep_artifacts=[],
        scanned_props=[],
        has_entity_filter=True,
    )

    assert result["manual_track"][0]["applicability"] == "excluded"
    assert result["manual_track"][0]["matched_entities"] == []


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_unknown_when_empty_entities(mock_session_ctx):
    rows = [_make_row("s1", "Fix Foo", ["com.example.Foo"], applicability="universal")]
    mock_session_ctx.return_value.__enter__.return_value.run.return_value.__iter__ = lambda s: iter(rows)

    from migration_oracle.mcp.graph.queries.upgrade import build_recipe_plan

    result = build_recipe_plan(
        framework="spring-boot",
        current_version="3.2.0",
        target_version="3.3.0",
        scanned_classes=[],
        scanned_class_simple=[],
        scanned_deps_ga=[],
        scanned_dep_artifacts=[],
        scanned_props=[],
        has_entity_filter=False,
    )

    assert result["manual_track"][0]["applicability"] == "universal"


@patch("migration_oracle.mcp.graph.queries.upgrade.read_session")
def test_dedup_first_occurrence_wins(mock_session_ctx):
    rows = [
        _make_row("s1", "First occurrence", ["com.example.Foo"]),
        _make_row("s1", "Duplicate — should be dropped", ["com.example.Bar"]),
    ]
    mock_session_ctx.return_value.__enter__.return_value.run.return_value.__iter__ = lambda s: iter(rows)

    from migration_oracle.mcp.graph.queries.upgrade import build_recipe_plan

    result = build_recipe_plan(
        framework="spring-boot",
        current_version="3.2.0",
        target_version="3.3.0",
        scanned_classes=[],
        scanned_class_simple=[],
        scanned_deps_ga=[],
        scanned_dep_artifacts=[],
        scanned_props=[],
        has_entity_filter=False,
    )

    steps = result["manual_track"]
    assert len(steps) == 1
    assert steps[0]["summary"] == "First occurrence"

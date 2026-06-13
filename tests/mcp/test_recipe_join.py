"""Recipe join and error-path tests for analyze_upgrade_path."""

from migration_oracle.mcp.graph.queries.upgrade import _ANALYZE_UPGRADE_PATH


def test_automated_by_traversal_starts_from_step():
    """AUTOMATED_BY must start from MigrationStep variable (s), not MigrationRule."""
    assert "OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)" in _ANALYZE_UPGRADE_PATH


def test_automated_by_not_from_rule():
    """The old bug pattern (rule)-[ab:AUTOMATED_BY] must not be present."""
    assert "(rule)-[ab:AUTOMATED_BY]" not in _ANALYZE_UPGRADE_PATH


def test_recipe_entry_includes_step_id():
    """Each recipe entry in recipes_raw must include step_id from the step node."""
    assert "step_id: elementId(s)" in _ANALYZE_UPGRADE_PATH


def test_include_recipes_false_unchanged():
    """The query structure has recipes_raw that gets filtered — no change to the filtering logic."""
    assert "recipes_raw" in _ANALYZE_UPGRADE_PATH
    assert "[x IN recipes_raw WHERE x IS NOT NULL AND x.recipe_id IS NOT NULL]" in _ANALYZE_UPGRADE_PATH

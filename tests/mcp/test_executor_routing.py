"""Unit tests for executor-selection routing logic (T029)."""

from __future__ import annotations

import pytest

from migration_oracle.mcp.routing import is_concrete_instruction, select_executor


def _step(
    recipe_id=None,
    auto=None,
    missing_params=None,
    effort="mechanical",
    instruction="",
    applicability="matched",
    automatable=False,
):
    return {
        "recipe_id": recipe_id,
        "auto": auto,
        "missing_required_params": missing_params or [],
        "effort": effort,
        "instruction": instruction,
        "applicability": applicability,
        "automatable": automatable,
    }


class TestSelectExecutor:
    def test_row1_fully_resolved_recipe(self):
        """Row 1: fully resolved recipe → openrewrite."""
        s = _step(recipe_id="r.RewriteX", auto=True, missing_params=[])
        assert select_executor(s) == "openrewrite"

    def test_row2_partially_resolved_recipe_auto_false(self):
        """Row 2: recipe exists + auto=False → prompted-auto."""
        s = _step(recipe_id="r.RewriteX", auto=False)
        assert select_executor(s) == "prompted-auto"

    def test_row2_partially_resolved_recipe_missing_params(self):
        """Row 2: recipe exists + missing params → prompted-auto."""
        s = _step(recipe_id="r.RewriteX", auto=True, missing_params=["targetVersion"])
        assert select_executor(s) == "prompted-auto"

    def test_row3_mechanical_concrete_instruction_entity_anchor(self):
        """Row 3: no recipe, mechanical, concrete instruction, entity anchor → agent-codemod."""
        s = _step(
            effort="mechanical",
            instruction="rename com.fasterxml.jackson.core to tools.jackson",
            applicability="matched",
        )
        assert select_executor(s) == "agent-codemod"

    def test_row4_moderate_concrete_instruction_entity_anchor(self):
        """Row 4: no recipe, moderate, concrete instruction, entity anchor → agent-codemod."""
        s = _step(
            effort="moderate",
            instruction="replace javax.annotation.PostConstruct with jakarta.annotation.PostConstruct",
            applicability="matched",
        )
        assert select_executor(s) == "agent-codemod"

    def test_row5_mechanical_no_instruction(self):
        """Row 5: no recipe, mechanical, no concrete instruction → human-review."""
        s = _step(effort="mechanical", instruction="Update the configuration.", applicability="matched")
        assert select_executor(s) == "human-review"

    def test_row6_moderate_no_instruction(self):
        """Row 6: no recipe, moderate, no concrete instruction → human-review."""
        s = _step(effort="moderate", instruction="Consider refactoring the service layer.", applicability="matched")
        assert select_executor(s) == "human-review"

    def test_row7_architectural(self):
        """Row 7: no recipe, architectural → human-review."""
        s = _step(effort="architectural", instruction="rename Foo to Bar", applicability="matched")
        assert select_executor(s) == "human-review"

    def test_automatable_true_no_recipe_does_not_select_automated_track(self):
        """automatable=True with no recipe routes by effort/instruction, NOT to an automated track."""
        s = _step(
            effort="mechanical",
            instruction="Update the configuration.",
            applicability="matched",
            automatable=True,
        )
        result = select_executor(s)
        assert result not in ("openrewrite", "prompted-auto")

    def test_no_entity_anchor_routes_to_human_review(self):
        """No entity anchor (applicability != matched) → human-review even with concrete instruction."""
        s = _step(
            effort="mechanical",
            instruction="rename com.example.Foo to com.example.Bar",
            applicability="informational",
        )
        assert select_executor(s) == "human-review"


class TestIsConcreteInstruction:
    def test_rename_pattern(self):
        assert is_concrete_instruction("rename com.fasterxml.jackson to tools.jackson") is True

    def test_replace_with_pattern(self):
        assert is_concrete_instruction("replace javax.annotation with jakarta.annotation") is True

    def test_arrow_pattern(self):
        assert is_concrete_instruction("`OldClass` → `NewClass`") is True

    def test_free_text_returns_false(self):
        assert is_concrete_instruction("Update your configuration to use the new API.") is False

    def test_empty_returns_false(self):
        assert is_concrete_instruction("") is False

    def test_none_like_returns_false(self):
        assert is_concrete_instruction("   ") is False

    def test_before_after_pattern(self):
        assert is_concrete_instruction("before: `@Component`, after: `@Service`") is True

"""Jackson package-prefix bridge acceptance test (T053).

Verifies that a Dependency-only MigrationRule (no [:AFFECTS_CLASS] node) is matched
via the truncated-groupId prefix fallback when the context contains an FQCN from
that dependency's package namespace.

This is a UNIT test targeting the entity-match CASE logic indirectly through
the routing.py is_concrete_instruction + the Cypher CASE semantics.

For a live-Neo4j version of this test, see the integration test in test_context.py.
"""

from __future__ import annotations

import pytest

from migration_oracle.mcp.routing import is_concrete_instruction, select_executor


def _jackson_step(
    recipe_id=None,
    auto=None,
    missing_params=None,
    effort="mechanical",
    instruction="rename com.fasterxml.jackson.* to tools.jackson.*",
    applicability="matched",  # package-prefix match fires → matched
):
    return {
        "recipe_id": recipe_id,
        "auto": auto,
        "missing_required_params": missing_params or [],
        "effort": effort,
        "instruction": instruction,
        "applicability": applicability,
        "automatable": True,
    }


class TestJacksonPackagePrefixRoute:
    def test_jackson_rule_with_matched_applicability_routes_to_agent_codemod(self):
        """Jackson rename step (matched via package-prefix) → agent-codemod track."""
        step = _jackson_step()
        assert select_executor(step) == "agent-codemod"

    def test_jackson_import_rename_is_concrete_instruction(self):
        """The Jackson rename instruction qualifies as concrete (pattern + target)."""
        assert is_concrete_instruction("rename com.fasterxml.jackson.* to tools.jackson.*") is True

    def test_uncertain_applicability_goes_to_human_review(self):
        """When applicability='uncertain' (package-prefix not fired), step goes to human-review."""
        step = _jackson_step(applicability="uncertain")
        assert select_executor(step) == "human-review"

    def test_informational_applicability_goes_to_human_review(self):
        """informational applicability (no entity anchor) → human-review even with concrete instruction."""
        step = _jackson_step(applicability="informational")
        assert select_executor(step) == "human-review"

    def test_jackson_with_recipe_routes_to_openrewrite(self):
        """If Jackson step has a fully-resolved recipe, OpenRewrite wins (row 1 takes priority)."""
        step = _jackson_step(recipe_id="tools.jackson.migrate.JacksonToToolsJackson", auto=True)
        assert select_executor(step) == "openrewrite"

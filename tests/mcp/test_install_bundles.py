"""Tests for 015a six-bundle skill installation."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

_SKILLS_DIR = Path(__file__).resolve().parents[2] / "migration_oracle" / "mcp" / "skills"

FULL_BUNDLES = [
    "framework-migration-plan",
    "framework-migration-gap-check",
    "framework-migration-clarify",
    "framework-migration-preview",
    "framework-migration-execute",
    "framework-migration-feedback",
]

EXPECTED_TOOLS = {
    "framework-migration-plan": {
        "analyze_upgrade_path", "build_recipe_plan", "resolve_deprecation",
        "entity_evolution", "search_migration_knowledge", "search_openrewrite_recipes",
        "get_graph_schema", "execute_custom_cypher", "get_community_insights",
        "create_migration_context", "get_steps_for_scope_tier",
        "resolve_paysafe_dependency_by_service_name", "list_pipeline_runs",
        "get_artifact_content", "install_migration_skill", "update_queried_entity",
        "get_migration_contexts",
    },
    "framework-migration-gap-check": {
        "get_graph_schema", "execute_custom_cypher", "get_pending_steps",
        "get_migration_contexts", "write_gap_check_flags", "get_steps_for_scope_tier",
    },
    "framework-migration-clarify": {
        "get_graph_schema", "execute_custom_cypher", "get_pending_steps",
        "update_step_status", "update_queried_entity", "get_migration_contexts",
        "add_manual_step",
    },
    "framework-migration-preview": {"get_pending_steps", "get_migration_contexts"},
    "framework-migration-execute": {
        "build_recipe_plan", "resolve_deprecation", "entity_evolution",
        "search_migration_knowledge", "search_openrewrite_recipes", "get_graph_schema",
        "execute_custom_cypher", "get_community_insights", "get_pending_steps",
        "update_step_status",
    },
    "framework-migration-feedback": {
        "submit_migration_insight", "get_community_insights", "vote_insight",
        "verify_insight", "get_graph_schema", "execute_custom_cypher",
        "close_migration_context", "get_migration_contexts",
    },
}

STAGE_FORBIDDEN_TOOLS = {
    "framework-migration-preview": {
        "add_manual_step", "write_gap_check_flags", "update_step_status",
        "update_queried_entity", "create_migration_context",
    },
    "framework-migration-gap-check": {"add_manual_step", "update_step_status"},
    "framework-migration-clarify": {"write_gap_check_flags"},
}


def _reload_install_module():
    os.environ["MIGRATION_MODE"] = "full"
    for name in ("migration_oracle.mcp.tools.install", "migration_oracle.mcp.config"):
        sys.modules.pop(name, None)
    import migration_oracle.mcp.tools.install as inst_mod
    return inst_mod


def _parse_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match, f"No frontmatter in {skill_md}"
    return yaml.safe_load(match.group(1))


@pytest.fixture
def full_install(tmp_path):
    inst = _reload_install_module()
    result = inst.install_migration_skill(target="cursor", target_dir=str(tmp_path))
    yield tmp_path, result
    os.environ.setdefault("MIGRATION_MODE", "lite")


def test_six_top_level_bundles_each_with_skill_md(full_install):
    root, result = full_install
    assert result["status"] == "ok"
    assert set(result["installed_skills"]) == set(FULL_BUNDLES)
    for bundle in FULL_BUNDLES:
        skill = root / bundle / "SKILL.md"
        assert skill.is_file(), f"Missing {bundle}/SKILL.md"
        assert len(list((root / bundle).glob("**/SKILL.md"))) == 1


def test_no_nested_gap_clarify_preview_references(full_install):
    root, _ = full_install
    forbidden = [
        "framework-migration/references/gap-check.md",
        "framework-migration/references/clarify.md",
        "framework-migration/references/preview.md",
        "references/gap-check.md",
        "references/clarify.md",
        "references/preview.md",
    ]
    for rel in forbidden:
        assert not (root / rel).exists(), f"Stale nested ref found: {rel}"


def test_content_isolation_no_cross_stage_tools(full_install):
    root, _ = full_install
    for bundle, forbidden in STAGE_FORBIDDEN_TOOLS.items():
        skill = root / bundle / "SKILL.md"
        body = skill.read_text(encoding="utf-8").lower()
        refs_dir = root / bundle / "references"
        if refs_dir.exists():
            for ref in refs_dir.rglob("*.md"):
                body += ref.read_text(encoding="utf-8").lower()
        for tool in forbidden:
            assert tool not in body, f"{bundle} mentions forbidden tool {tool}"


def test_frontmatter_tools_match_matrix(full_install):
    root, _ = full_install
    for bundle in FULL_BUNDLES:
        fm = _parse_frontmatter(root / bundle / "SKILL.md")
        tools = set(fm["compatibility"]["tools"])
        assert tools == EXPECTED_TOOLS[bundle], f"{bundle}: {tools}"


def test_preview_shares_no_mutation_tools_with_clarify(full_install):
    root, _ = full_install
    preview_tools = set(
        _parse_frontmatter(root / "framework-migration-preview" / "SKILL.md")["compatibility"]["tools"]
    )
    clarify_tools = set(
        _parse_frontmatter(root / "framework-migration-clarify" / "SKILL.md")["compatibility"]["tools"]
    )
    mutation = {"add_manual_step", "update_step_status", "update_queried_entity"}
    assert not (preview_tools & mutation)
    assert mutation <= clarify_tools


def test_no_shared_bundle_exists(full_install):
    root, _ = full_install
    for path in root.rglob("*"):
        if path.is_dir() and "shared" in path.name.lower():
            pytest.fail(f"Unexpected shared bundle: {path}")


def test_reference_relocation(full_install):
    root, _ = full_install
    assert (root / "framework-migration-plan" / "references" / "scanning.md").is_file()
    assert (root / "framework-migration-plan" / "references" / "version-map.md").is_file()
    assert (root / "framework-migration-execute" / "references" / "rollback.md").is_file()
    assert not (root / "framework-migration-gap-check" / "references").exists() or not any(
        (root / "framework-migration-gap-check" / "references").iterdir()
    )

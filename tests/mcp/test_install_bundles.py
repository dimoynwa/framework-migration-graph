"""Tests for six-bundle skill installation (020)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
import yaml

_SKILLS_DIR = Path(__file__).resolve().parents[2] / "migration_oracle" / "mcp" / "skills"

FULL_BUNDLES = [
    "framework-migration-research",
    "framework-migration-plan",
    "framework-migration-gap-check",
    "framework-migration-clarify",
    "framework-migration-preview",
    "framework-migration-execute",
]

EXPECTED_TOOLS = {
    "framework-migration-research": {
        "analyze_upgrade_path", "build_recipe_plan", "resolve_deprecation",
        "entity_evolution", "search_migration_knowledge", "search_openrewrite_recipes",
        "get_graph_schema", "execute_custom_cypher", "get_community_insights",
        "resolve_paysafe_dependency_by_service_name", "list_pipeline_runs",
        "get_artifact_content", "install_migration_skill",
    },
    "framework-migration-plan": {
        "analyze_upgrade_path", "build_recipe_plan", "resolve_deprecation",
        "entity_evolution", "search_migration_knowledge", "search_openrewrite_recipes",
        "get_graph_schema", "execute_custom_cypher", "get_community_insights",
        "resolve_paysafe_dependency_by_service_name", "list_pipeline_runs",
        "get_artifact_content", "install_migration_skill", "check_version_availability",
    },
    "framework-migration-gap-check": {"install_migration_skill"},
    "framework-migration-clarify": {"install_migration_skill"},
    "framework-migration-preview": {"install_migration_skill"},
    "framework-migration-execute": {
        "build_recipe_plan", "resolve_deprecation", "entity_evolution",
        "search_migration_knowledge", "search_openrewrite_recipes", "get_graph_schema",
        "execute_custom_cypher", "get_community_insights", "install_migration_skill",
    },
}

REMOVED_TOOLS = {
    "create_migration_context", "get_migration_contexts", "get_pending_steps",
    "update_step_status", "close_migration_context", "update_queried_entity",
    "get_steps_for_scope_tier", "write_gap_check_flags", "add_manual_step",
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
    assert result["installed_skills"] == FULL_BUNDLES
    assert set(result["installed_skills"]) == set(FULL_BUNDLES)
    for bundle in FULL_BUNDLES:
        skill = root / bundle / "SKILL.md"
        assert skill.is_file(), f"Missing {bundle}/SKILL.md"
        assert len(list((root / bundle).glob("**/SKILL.md"))) == 1


def test_no_feedback_bundle(full_install):
    root, _ = full_install
    assert not (root / "framework-migration-feedback").exists()


def test_no_removed_tools_in_bundle_prose(full_install):
    root, _ = full_install
    for bundle in FULL_BUNDLES:
        skill = root / bundle / "SKILL.md"
        body = skill.read_text(encoding="utf-8").lower()
        refs_dir = root / bundle / "references"
        if refs_dir.exists():
            for ref in refs_dir.rglob("*.md"):
                body += ref.read_text(encoding="utf-8").lower()
        for tool in REMOVED_TOOLS:
            assert tool not in body, f"{bundle} mentions removed tool {tool}"


def test_frontmatter_tools_match_matrix(full_install):
    root, _ = full_install
    for bundle in FULL_BUNDLES:
        fm = _parse_frontmatter(root / bundle / "SKILL.md")
        tools = set(fm["compatibility"]["tools"])
        assert tools == EXPECTED_TOOLS[bundle], f"{bundle}: {tools}"


def test_frontmatter_tools_match_stage_gating_allowlist(full_install):
    """Research (and other) frontmatter tools must match STAGE_TOOL_ALLOWLIST."""
    from migration_oracle.mcp.stage_gating import STAGE_TOOL_ALLOWLIST

    root, _ = full_install
    stage_for_bundle = {
        "framework-migration-research": "research",
        "framework-migration-plan": "plan",
        "framework-migration-gap-check": "gap-check",
        "framework-migration-clarify": "clarify",
        "framework-migration-preview": "preview",
        "framework-migration-execute": "execute",
    }
    for bundle, stage in stage_for_bundle.items():
        fm = _parse_frontmatter(root / bundle / "SKILL.md")
        tools = set(fm["compatibility"]["tools"])
        assert tools == set(STAGE_TOOL_ALLOWLIST[stage]), f"{bundle}/{stage}"


def test_reference_relocation(full_install):
    root, _ = full_install
    plan_refs = root / "framework-migration-plan" / "references"
    assert (plan_refs / "scanning.md").is_file()
    assert (plan_refs / "version-map.md").is_file()
    assert (plan_refs / "framework_scanner.py").is_file()
    assert (root / "framework-migration-execute" / "references" / "rollback.md").is_file()
    scanning = (plan_refs / "scanning.md").read_text(encoding="utf-8")
    assert "python3 references/framework_scanner.py" in scanning
    # Primary command block must not use the source-tree path.
    primary = scanning.split("Development source")[0]
    assert "python3 migration_oracle/mcp/skills/framework-migration/framework_scanner.py" not in primary
    research = (root / "framework-migration-research" / "SKILL.md").read_text(encoding="utf-8")
    assert "../framework-migration-plan/references/scanning.md" in research
    assert "../framework-migration-plan/references/version-map.md" in research
    assert (root / "framework-migration-plan" / "SKILL.md").is_file()

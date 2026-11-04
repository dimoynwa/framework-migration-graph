"""Session-scoped MCP tool allowlists for the six-stage file-state migration harness."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_VALID_STAGES = frozenset({
    "research",
    "plan",
    "gap-check",
    "clarify",
    "preview",
    "execute",
})

# Tool-to-session exposure matrix. gap-check, clarify, and preview are file-only stages.
# research tools must match framework-migration/research.md compatibility.tools.
STAGE_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    "research": frozenset({
        "analyze_upgrade_path",
        "build_recipe_plan",
        "resolve_deprecation",
        "entity_evolution",
        "search_migration_knowledge",
        "search_openrewrite_recipes",
        "get_graph_schema",
        "execute_custom_cypher",
        "get_community_insights",
        "resolve_paysafe_dependency_by_service_name",
        "list_pipeline_runs",
        "get_artifact_content",
        "install_migration_skill",
    }),
    "plan": frozenset({
        "analyze_upgrade_path",
        "build_recipe_plan",
        "resolve_deprecation",
        "entity_evolution",
        "search_migration_knowledge",
        "search_openrewrite_recipes",
        "get_graph_schema",
        "execute_custom_cypher",
        "get_community_insights",
        "resolve_paysafe_dependency_by_service_name",
        "list_pipeline_runs",
        "get_artifact_content",
        "install_migration_skill",
        "check_version_availability",
    }),
    "gap-check": frozenset({
        "install_migration_skill",
    }),
    "clarify": frozenset({
        "install_migration_skill",
    }),
    "preview": frozenset({
        "install_migration_skill",
    }),
    "execute": frozenset({
        "build_recipe_plan",
        "resolve_deprecation",
        "entity_evolution",
        "search_migration_knowledge",
        "search_openrewrite_recipes",
        "get_graph_schema",
        "execute_custom_cypher",
        "get_community_insights",
        "install_migration_skill",
    }),
}


def get_active_stage() -> str | None:
    """Return the active harness stage from MCP_ACTIVE_STAGE, or None when unset."""
    raw = os.environ.get("MCP_ACTIVE_STAGE", "").strip().lower()
    if not raw:
        return None
    if raw not in _VALID_STAGES:
        raise ValueError(
            f"Invalid MCP_ACTIVE_STAGE={raw!r}; valid options are: "
            + ", ".join(sorted(_VALID_STAGES))
        )
    return raw


def apply_stage_gating(mcp) -> None:
    """Remove tools not in the allowlist for the active stage."""
    stage = get_active_stage()
    if stage is None:
        return
    allowed = STAGE_TOOL_ALLOWLIST[stage]
    tools = mcp._tool_manager._tools
    removed = [name for name in list(tools) if name not in allowed]
    for name in removed:
        del tools[name]
    logger.info(
        "Stage gating applied — stage=%s allowed=%d removed=%d",
        stage,
        len(allowed),
        len(removed),
    )

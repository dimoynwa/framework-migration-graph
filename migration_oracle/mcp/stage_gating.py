"""Session-scoped MCP tool allowlists for the split migration harness."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_VALID_STAGES = frozenset({
    "plan",
    "gap-check",
    "clarify",
    "preview",
    "execute",
    "feedback",
})

# Tool-to-session exposure matrix (specs/015-split-migration-harness/contracts/).
STAGE_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
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
        "create_migration_context",
        "get_steps_for_scope_tier",
        "resolve_paysafe_dependency_by_service_name",
        "list_pipeline_runs",
        "get_artifact_content",
        "install_migration_skill",
        "update_queried_entity",
        "get_migration_contexts",
    }),
    "gap-check": frozenset({
        "get_graph_schema",
        "execute_custom_cypher",
        "get_pending_steps",
        "get_steps_for_scope_tier",
        "get_migration_contexts",
        "write_gap_check_flags",
    }),
    "clarify": frozenset({
        "get_graph_schema",
        "execute_custom_cypher",
        "get_pending_steps",
        "update_step_status",
        "get_migration_contexts",
        "update_queried_entity",
        "add_manual_step",
    }),
    "preview": frozenset({
        "get_pending_steps",
        "get_migration_contexts",
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
        "get_pending_steps",
        "update_step_status",
        "get_migration_contexts",
    }),
    "feedback": frozenset({
        "get_graph_schema",
        "execute_custom_cypher",
        "submit_migration_insight",
        "get_community_insights",
        "vote_insight",
        "verify_insight",
        "close_migration_context",
        "get_migration_contexts",
    }),
}

_STAGES_REQUIRING_CONTEXT_ID = frozenset({"gap-check", "clarify", "preview"})


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


def validate_context_id_for_stage(context_id: str) -> dict | None:
    """Return an error dict when context_id is missing/invalid for gated stages."""
    stage = get_active_stage()
    if stage not in _STAGES_REQUIRING_CONTEXT_ID:
        return None
    if not context_id or not str(context_id).strip():
        return {
            "status": "error",
            "error_code": "missing_context_id",
            "hint": f"context_id is required for the {stage} stage",
        }
    from migration_oracle.mcp.graph.queries import context as context_queries

    if not context_queries.context_exists(context_id=context_id):
        return {
            "status": "error",
            "error_code": "context_not_found",
            "hint": f"Context '{context_id}' not found",
        }
    return None

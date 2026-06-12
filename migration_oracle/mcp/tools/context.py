"""Migration context MCP tool handlers."""

from __future__ import annotations

from migration_oracle.mcp.graph.queries import context as context_queries
from migration_oracle.mcp.graph.queries.context import VersionNotInGraphError
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.tools.upgrade import to_minor_zero


def _pending_step(row: dict) -> dict:
    requires = [r for r in (row.get("requires") or []) if r]
    return {
        "step_id": row.get("step_id") or "",
        "step_type": row.get("step_type") or "",
        "rule_id": row.get("rule_id") or "",
        "summary": row.get("summary") or "",
        "instruction": row.get("instruction") or "",
        "verification_hint": row.get("verification_hint") or "",
        "effort": row.get("effort") or "",
        "automatable": bool(row.get("automatable")),
        "scope": row.get("scope") or "",
        "severity": row.get("severity") or "",
        "requires": requires,
        "recipe_id": row.get("recipe_id"),
    }


@mcp.tool()
def create_migration_context(
    project_id: str,
    from_version: str,
    to_version: str,
    framework: str,
    scanned_entities: list[str] | None = None,
) -> dict:
    """Create or resume a MigrationContext for a (project_id, from_version, to_version) triple. Idempotent.

    If a context with the same triple already exists, returns it unchanged (created=False).
    Pass scanned_entities from Loop I codebase scan to seed the context with project-specific entities.
    Returns: context_id (use in all subsequent context tool calls), migration_status, scanned_entities.
    """
    from_norm = to_minor_zero(from_version)
    to_norm = to_minor_zero(to_version)
    try:
        ctx = context_queries.create_or_get_context(
            project_id=project_id,
            from_version=from_norm,
            to_version=to_norm,
            framework=framework,
            scanned_entities=scanned_entities or [],
        )
    except VersionNotInGraphError as exc:
        context_queries.delete_zombie_context(
            project_id=project_id,
            from_version=from_norm,
            to_version=to_norm,
        )
        hint = ", ".join(exc.available_versions) if exc.available_versions else "none found"
        return {
            "status": "error",
            "error_code": "version_not_in_graph",
            "missing_version": exc.missing_version,
            "hint": f"Available versions in graph: {hint}",
        }
    return {
        "status": "ok",
        "context_id": ctx["context_id"],
        "project_id": ctx["project_id"],
        "from_version": ctx["from_version"],
        "to_version": ctx["to_version"],
        "framework": ctx["framework"],
        "migration_status": ctx["migration_status"],
        "scanned_entities": ctx.get("scanned_entities") or [],
        "completed_steps": ctx.get("completed_steps") or [],
        "skipped_steps": ctx.get("skipped_steps") or [],
        "created_at": ctx.get("created_at") or "",
        "completed_at": ctx.get("completed_at"),
        "notes": ctx.get("notes") or "",
        "created": bool(ctx.get("created")),
    }


@mcp.tool()
def get_pending_steps(
    context_id: str,
    effort_filter: list[str] | None = None,
    scope_filter: list[str] | None = None,
) -> dict:
    """Return the remaining step queue for a context, ordered by scope severity then topological order.

    Excludes completed and skipped steps. Returns an empty list when:
      (a) all steps are done, or
      (b) no MigrationStep nodes exist in the graph (pre-redesign data — use build_recipe_plan instead).
    Supports effort_filter (e.g. ['mechanical']) and scope_filter (e.g. ['api-surface']) to narrow results.
    """
    rows = context_queries.get_pending_steps(
        context_id=context_id,
        effort_filter=effort_filter or [],
        scope_filter=scope_filter or [],
    )
    pending = [_pending_step(row) for row in rows]
    return {
        "status": "ok",
        "context_id": context_id,
        "pending_steps": pending,
        "total_pending": len(pending),
    }


@mcp.tool()
def update_step_status(
    context_id: str,
    step_id: str,
    outcome: str,
    reason: str = "",
) -> dict:
    """Record the outcome of a migration step: 'completed', 'skipped', or 'failed'.

    Auto-closes the context when no pending steps remain after this call.
    Returns: step_id, outcome, context_auto_closed, context_status, completed_count, skipped_count.
    """
    result = context_queries.record_step_outcome(
        context_id=context_id,
        step_id=step_id,
        outcome=outcome,
        reason=reason,
    )
    if result.get("on_path") is False:
        return {
            "status": "error",
            "error_code": "step_not_on_path",
            "step_id": step_id,
            "hint": f"Step {step_id} is not part of migration path for context {context_id}",
        }
    pending = context_queries.get_pending_steps(context_id=context_id)
    context_auto_closed = False
    context_status = result.get("migration_status") or "in-progress"
    if not pending:
        closed = context_queries.auto_close_write(context_id=context_id)
        context_auto_closed = True
        context_status = closed.get("migration_status") or "complete"
    return {
        "status": "ok",
        "step_id": step_id,
        "outcome": outcome,
        "context_id": context_id,
        "context_auto_closed": context_auto_closed,
        "context_status": context_status,
        "completed_count": result.get("completed_count") or 0,
        "skipped_count": result.get("skipped_count") or 0,
    }


@mcp.tool()
def get_steps_for_scope_tier(
    context_id: str,
    scope: str,
    severity_threshold: str = "medium",
) -> dict:
    """Return steps for a specific scope tier at or above a severity threshold.

    Valid scope values: 'api-surface', 'runtime', 'config', 'build', 'test'.
    Valid severity_threshold values: 'low', 'medium', 'high', 'critical'.
    Returns: entities list (unique entity names with hits), hits list (entity+step pairs), rule_count.
    Use in Loop II to query one tier at a time before calling analyze_upgrade_path for that tier.
    """
    rows = context_queries.get_steps_for_scope_tier(
        context_id=context_id,
        scope=scope,
        min_severity=severity_threshold,
    )
    hits = [
        {
            "step_id": row.get("step_id") or "",
            "rule_id": row.get("rule_id") or "",
            "summary": row.get("summary") or "",
            "scope": row.get("scope"),
            "severity": row.get("severity") or None,
        }
        for row in rows
    ]
    rule_ids = {row.get("rule_id") for row in rows if row.get("rule_id")}
    entities: list[str] = []
    return {
        "status": "ok",
        "context_id": context_id,
        "scope": scope,
        "severity_threshold": severity_threshold,
        "entities": entities,
        "rule_count": len(rule_ids),
        "hits": hits,
        "total": len(hits),
    }


@mcp.tool()
def close_migration_context(
    context_id: str,
    final_status: str,
    notes: str = "",
) -> dict:
    """Set completedAt, migration_status, and notes on a context. Call at the end of every session.

    final_status: 'complete' (all steps done) or 'partial' (steps were skipped or deferred).
    Note: update_step_status auto-closes the context when all steps complete — call this tool
    explicitly only when ending a session with skipped steps or adding notes.
    Returns: context_id, migration_status, completed_steps, skipped_steps, completed_at, notes.
    """
    result = context_queries.close_migration_context(
        context_id=context_id,
        final_status=final_status,
        notes=notes,
    )
    return {
        "tool_status": "ok",
        "context_id": result["context_id"],
        "migration_status": result["migration_status"],
        "completed_steps": result.get("completed_steps") or [],
        "skipped_steps": result.get("skipped_steps") or [],
        "completed_at": result.get("completed_at"),
        "notes": result.get("notes") or "",
    }

"""Migration context MCP tool handlers."""

from __future__ import annotations

from migration_oracle.mcp.graph.queries import context as context_queries
from migration_oracle.mcp.graph.queries.context import VersionNotInGraphError
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.tools.upgrade import normalize_entities, to_minor_zero


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
        "applicability": row.get("applicability") or "informational",
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
    entities = scanned_entities or []
    norm = normalize_entities(entities)
    norm_from = to_minor_zero(from_version)
    norm_to = to_minor_zero(to_version)
    try:
        ctx = context_queries.create_or_get_context(
            project_id=project_id,
            from_version=norm_from,
            to_version=norm_to,
            framework=framework,
            scanned_entities=entities,
            scanned_classes=norm["scanned_classes"],
            scanned_class_simple=norm["scanned_class_simple"],
            scanned_deps_ga=norm["scanned_deps_ga"],
            scanned_dep_artifacts=norm["scanned_dep_artifacts"],
            scanned_props=norm["scanned_props"],
        )
    except VersionNotInGraphError as exc:
        if not exc.available:
            context_queries.delete_zombie_context(
                project_id=project_id,
                from_version=norm_from,
                to_version=norm_to,
            )
        hint = (
            f"Version '{exc.version}' not in graph. Available: {', '.join(exc.available)}"
            if exc.available
            else f"Version '{exc.version}' not found in graph."
        )
        return {"status": "error", "error_code": "version_not_in_graph", "hint": hint}
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
    Writes a STEP_OUTCOME relationship (ctx)-[:STEP_OUTCOME {status, reason, updatedAt}]->(step)
    in addition to the legacy completedSteps/skippedSteps/failedSteps arrays.
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
            "hint": f"Step '{step_id}' is not on the migration path for context '{context_id}'.",
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


_VALID_THRESHOLDS = {"low", "medium", "high", "critical"}


@mcp.tool()
def get_steps_for_scope_tier(
    context_id: str,
    scope: str,
    severity_threshold: str = "medium",
) -> dict:
    """Return steps for a specific scope tier at or above a severity threshold.

    Valid scope values: 'api-surface', 'runtime', 'config', 'build', 'test'.
    Valid severity_threshold values: 'low', 'medium', 'high', 'critical' (critical > high > medium > low).
    Returns only steps whose severity is at or above the threshold.
    Unknown severity_threshold values are rejected with error_code='invalid_severity_threshold'.
    Returns: entities list (unique entity names with hits), hits list (entity+step pairs), rule_count.
    Use in Loop II to query one tier at a time before calling analyze_upgrade_path for that tier.
    """
    if severity_threshold not in _VALID_THRESHOLDS:
        return {
            "status": "error",
            "error_code": "invalid_severity_threshold",
            "hint": f"severity_threshold must be one of: {', '.join(sorted(_VALID_THRESHOLDS))}",
        }
    rows = context_queries.get_steps_for_scope_tier(
        context_id=context_id,
        scope=scope,
        min_severity=severity_threshold,
    )
    entities = sorted({row["entity_name"] for row in rows if row.get("entity_name")})
    hits = [
        {
            "entity_name": row.get("entity_name") or "",
            "entity_type": row.get("entity_type") or "",
            "step_id": row.get("step_id") or "",
            "rule_id": row.get("rule_id") or "",
            "summary": row.get("summary") or "",
            "scope": row.get("scope"),
            "severity": row.get("severity") or "",
        }
        for row in rows
    ]
    rule_ids = {row.get("rule_id") for row in rows if row.get("rule_id")}
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
def update_queried_entity(
    context_id: str,
    entity_name: str,
    result_summary: str,
) -> dict:
    """Store the result summary for a queried entity in the context's queriedEntities cache.

    Call after each successful entity query in Loop II so resumed sessions can skip
    already-queried entities. result_summary is truncated to 500 characters.
    Returns: status, context_id, entity_name, cached_count (total entries after upsert).
    On context not found: status='error', error_code='context_not_found'.
    """
    result = context_queries.update_queried_entity(
        context_id=context_id,
        entity_name=entity_name,
        result_summary=result_summary,
    )
    if result is None:
        return {
            "status": "error",
            "error_code": "context_not_found",
            "hint": f"Context '{context_id}' not found",
        }
    return {
        "status": "ok",
        "context_id": context_id,
        "entity_name": entity_name,
        "cached_count": result["cached_count"],
    }


_VALID_FINAL_STATUSES = {"complete", "partial", "abandoned"}


@mcp.tool()
def close_migration_context(
    context_id: str,
    final_status: str,
    notes: str = "",
) -> dict:
    """Set completedAt, migration_status, and notes on a context. Call at the end of every session.

    final_status: 'complete' (all steps done), 'partial' (steps were skipped or deferred),
    or 'abandoned' (session cancelled or deferred). Any other value is rejected.
    Note: update_step_status auto-closes the context when all steps complete — call this tool
    explicitly only when ending a session with skipped steps or adding notes.
    Returns: context_id, migration_status, completed_steps, skipped_steps, completed_at, notes.
    """
    if final_status not in _VALID_FINAL_STATUSES:
        return {
            "tool_status": "error",
            "error_code": "invalid_final_status",
            "hint": "final_status must be one of: abandoned, complete, partial",
        }
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

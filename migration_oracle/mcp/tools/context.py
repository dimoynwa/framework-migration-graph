"""Migration context MCP tool handlers."""

from __future__ import annotations

from migration_oracle.mcp.graph.queries import context as context_queries
from migration_oracle.mcp.graph.queries.context import VersionNotInGraphError
from migration_oracle.mcp.graph.queries.upgrade import resolve_version
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.tools.upgrade import normalize_entities, to_minor_zero
from migration_oracle.models.graph import VersionResolutionFailure


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
    allow_stub_create: bool = False,
) -> dict:
    """Create or resume a MigrationContext for a (project_id, from_version, to_version) triple. Idempotent.

    If a context with the same triple already exists, returns it unchanged (created=False).
    Pass scanned_entities from Loop I codebase scan to seed the context with project-specific entities.
    allow_stub_create: when True, creates a stub Version node for toVersion if not in graph.
    Returns: context_id, migration_status, scanned_entities, droppedCount, rounded, ahead_of_catalogue.
    """
    entities = scanned_entities or []
    norm = normalize_entities(entities)

    # Apply allow-list filter before any write (T023)
    allowed_entities = _filter_entities(entities)
    dropped_count = len(entities) - len(allowed_entities)
    norm_filtered = normalize_entities(allowed_entities)

    # Resolve versions via resolve_version (T007 — no to_minor_zero)
    resolved_from = resolve_version(framework, from_version, mode="floor")
    if isinstance(resolved_from, VersionResolutionFailure):
        return {
            "status": "error",
            "error_code": "version_not_in_graph",
            "hint": (
                f"fromVersion '{from_version}' not found in graph for framework '{framework}'. "
                f"Candidates: {', '.join(resolved_from.candidatesConsidered) or 'none'}"
            ),
        }

    resolved_to = resolve_version(framework, to_version, mode="ceil", allow_stub_create=allow_stub_create)
    if isinstance(resolved_to, VersionResolutionFailure):
        return {
            "status": "error",
            "error_code": "version_not_in_graph",
            "hint": (
                f"toVersion '{to_version}' not found in graph for framework '{framework}'. "
                f"Candidates: {', '.join(resolved_to.candidatesConsidered) or 'none'}"
            ),
        }

    try:
        ctx = context_queries.create_or_get_context(
            project_id=project_id,
            from_version=from_version,  # MERGE key = exact caller string (not normalised)
            to_version=to_version,      # MERGE key = exact caller string
            framework=framework,
            scanned_entities=allowed_entities,
            scanned_classes=norm_filtered["scanned_classes"],
            scanned_class_simple=norm_filtered["scanned_class_simple"],
            scanned_deps_ga=norm_filtered["scanned_deps_ga"],
            scanned_dep_artifacts=norm_filtered["scanned_dep_artifacts"],
            scanned_props=norm_filtered["scanned_props"],
            from_node_id=resolved_from.nodeId,
            to_node_id=resolved_to.nodeId,
        )
    except VersionNotInGraphError as exc:
        if not exc.available:
            context_queries.delete_zombie_context(
                project_id=project_id,
                from_version=from_version,
                to_version=to_version,
            )
        hint = (
            f"Version '{exc.version}' not in graph. Available: {', '.join(exc.available)}"
            if exc.available
            else f"Version '{exc.version}' not found in graph."
        )
        return {"status": "error", "error_code": "version_not_in_graph", "hint": hint}
    except Exception as exc:
        import neo4j.exceptions
        if isinstance(exc, neo4j.exceptions.ConstraintError):
            return {
                "status": "error",
                "error_code": "conflict_error",
                "hint": "Concurrent context creation conflict. Retry the call — the context was already created.",
            }
        raise

    # Check Spring Cloud co-migration warning (T010)
    co_migration_warning = None
    try:
        from_major = int(from_version.split(".")[0])
        to_major = int(to_version.split(".")[0])
        if from_major == 3 and to_major == 4 and framework.lower() in ("spring boot", "springboot"):
            sc_in_deps = any(
                ga.startswith("org.springframework.cloud:")
                for ga in (norm_filtered["scanned_deps_ga"] or [])
            )
            sc_in_classes = any(
                cls.startswith("org.springframework.cloud.")
                for cls in (norm_filtered["scanned_classes"] or [])
            )
            if sc_in_deps or sc_in_classes:
                co_migration_warning = (
                    "Spring Cloud detected. Upgrading Boot 3.x → 4.x requires also migrating "
                    "to Spring Cloud 2025.1.x (Oakwood train). Oakwood drops "
                    "spring-cloud-starter-parent — use spring-cloud-dependencies BOM-only import instead."
                )
    except (ValueError, IndexError):
        pass

    result = {
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
        "updated_at": ctx.get("updated_at") or "",
        "completed_at": ctx.get("completed_at"),
        "notes": ctx.get("notes") or "",
        "created": bool(ctx.get("created")),
        "dropped_count": dropped_count,
        "upgrades_to_version": resolved_to.resolvedVersion,
        "rounded": resolved_to.rounded,
        "ahead_of_catalogue": resolved_to.aheadOfCatalogue,
        "stub_created": resolved_to.stubCreated,
    }
    if co_migration_warning:
        result["co_migration_warning"] = co_migration_warning
    return result


_ALLOW_LIST_PREFIXES = (
    "org.springframework",
    "jakarta.",
    "javax.",
    "org.hibernate",
    "io.micrometer",
    "io.projectreactor",
    "org.thymeleaf",
    "com.fasterxml.jackson",
    "tools.jackson",
    "org.springdoc",
    "com.querydsl",
    "org.flywaydb",
    "org.liquibase",
    "org.apache.tomcat",
    "org.eclipse.jetty",
    "io.undertow",
    "org.springframework.cloud",
    "spring.",
)


def _filter_entities(entities: list[str]) -> list[str]:
    """Filter entity strings to only allow-listed prefixes (T022/T023)."""
    filtered = []
    for e in entities:
        if not e:
            continue
        name = e.split(":")[0] if ":" in e else e
        if any(name.startswith(p) for p in _ALLOW_LIST_PREFIXES):
            filtered.append(e)
    return filtered


@mcp.tool()
def get_migration_contexts(
    project_id: str,
    framework: str | None = None,
) -> dict:
    """List all MigrationContext nodes for a project. Returns count=0 with empty list when none exist.

    Returns: status, project_id, count, contexts[].
    Each context has: id, projectId, fromVersion, toVersion, framework, status, createdAt, updatedAt, outcome_counts.
    """
    if not project_id:
        return {
            "status": "error",
            "error_code": "missing_project_id",
            "hint": "project_id must not be empty",
        }
    try:
        rows = context_queries.get_migration_contexts(project_id=project_id, framework=framework)
    except Exception as exc:
        return {
            "status": "error",
            "error_code": "db_error",
            "hint": str(exc),
        }
    contexts = [
        {
            "id": row.get("id") or "",
            "projectId": row.get("projectId") or "",
            "fromVersion": row.get("fromVersion") or "",
            "toVersion": row.get("toVersion") or "",
            "framework": row.get("framework") or "",
            "status": row.get("status") or "",
            "createdAt": row.get("createdAt") or "",
            "updatedAt": row.get("updatedAt") or "",
            "outcome_counts": {
                "completed": row.get("completed_count") or 0,
                "failed": row.get("failed_count") or 0,
                "skipped": row.get("skipped_count") or 0,
                "deferred": row.get("deferred_count") or 0,
            },
        }
        for row in rows
    ]
    return {
        "status": "ok",
        "project_id": project_id,
        "count": len(contexts),
        "contexts": contexts,
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


_VALID_OUTCOMES = {"completed", "skipped", "failed", "deferred"}


@mcp.tool()
def update_step_status(
    context_id: str,
    step_id: str,
    outcome: str,
    reason: str = "",
) -> dict:
    """Record the outcome of a migration step: 'completed', 'skipped', 'failed', or 'deferred'.

    For outcome='deferred', the step's rule must have a BRIDGED_BY edge in the graph.
    Auto-closes the context when no pending steps remain after this call.
    Writes a STEP_OUTCOME relationship (ctx)-[:STEP_OUTCOME {status, reason, updatedAt}]->(step).
    Returns: step_id, outcome, context_auto_closed, context_status, completed_count, skipped_count.
    """
    if outcome not in _VALID_OUTCOMES:
        return {
            "status": "error",
            "error_code": "invalid_outcome",
            "hint": f"outcome must be one of: {', '.join(sorted(_VALID_OUTCOMES))}",
        }

    # Bridge discoverability check for deferred outcomes (T031)
    if outcome == "deferred":
        bridge_info = context_queries.check_bridge_discoverability(step_id=step_id)
        if bridge_info is None or bridge_info.get("bridge_name") is None:
            return {
                "status": "error",
                "error_code": "bridge_not_in_graph",
                "step_id": step_id,
                "hint": (
                    f"Step '{step_id}' cannot be deferred: its rule has no BRIDGED_BY edge in the graph. "
                    "Route to human-review instead."
                ),
            }

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

    # Auto-resolve any deferred steps whose requiredChange = this completed step (T032)
    auto_resolved: list[str] = []
    if outcome == "completed":
        auto_resolved = context_queries.auto_resolve_deferred_steps(
            context_id=context_id,
            completed_step_id=step_id,
        )

    pending = context_queries.get_pending_steps(context_id=context_id)
    context_auto_closed = False
    context_status = result.get("migration_status") or "in-progress"
    if not pending:
        closed = context_queries.auto_close_write(context_id=context_id)
        context_auto_closed = True
        context_status = closed.get("migration_status") or "complete"

    response = {
        "status": "ok",
        "step_id": step_id,
        "outcome": outcome,
        "context_id": context_id,
        "context_auto_closed": context_auto_closed,
        "context_status": context_status,
        "completed_count": result.get("completed_count") or 0,
        "skipped_count": result.get("skipped_count") or 0,
    }
    if auto_resolved:
        response["auto_resolved_deferred"] = auto_resolved
    return response


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

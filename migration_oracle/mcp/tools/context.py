"""Migration context MCP tool handlers."""

from __future__ import annotations

import logging

from migration_oracle.mcp.graph.queries import context as context_queries
from migration_oracle.mcp.graph.queries.context import VersionNotInGraphError, check_context_version_match
from migration_oracle.mcp.graph.queries.upgrade import resolve_version
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.stage_gating import validate_context_id_for_stage
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
        "origin": row.get("origin") or "graph",
    }


@mcp.tool()
def create_migration_context(
    project_id: str,
    from_version: str,
    to_version: str,
    framework: str,
    scanned_entities: list[str] | None = None,
    allow_stub_create: bool = False,
    diagnostics: dict | None = None,
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

    # Zombie guard (BRANCH-B): on resume, verify context edges point to correct nodes
    if not ctx.get("created") and resolved_from.nodeId and resolved_to.nodeId:
        if not check_context_version_match(
            context_id=ctx["context_id"],
            from_node_id=resolved_from.nodeId,
            to_node_id=resolved_to.nodeId,
        ):
            logging.warning(
                "Zombie context detected for %s %s→%s (id=%s), deleting and recreating",
                project_id, from_version, to_version, ctx["context_id"],
            )
            context_queries.delete_zombie_context(
                project_id=project_id,
                from_version=from_version,
                to_version=to_version,
            )
            ctx = context_queries.create_or_get_context(
                project_id=project_id,
                from_version=from_version,
                to_version=to_version,
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
            if not ctx.get("created"):
                raise RuntimeError("zombie context re-created unexpectedly")

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
        "reused": not bool(ctx.get("created")),
        "entityCount": len(allowed_entities),
        "droppedCount": dropped_count,
        "dropped_count": dropped_count,
        "upgrades_to_version": resolved_to.resolvedVersion,
        "rounded": resolved_to.rounded,
        "ahead_of_catalogue": resolved_to.aheadOfCatalogue,
        "stub_created": resolved_to.stubCreated,
    }
    if co_migration_warning:
        result["co_migration_warning"] = co_migration_warning
    if diagnostics and ctx.get("created"):
        context_queries.set_diagnostics_on_create(
            context_id=ctx["context_id"],
            diagnostics=diagnostics,
        )
        result["diagnostics_cached"] = True
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
    Each context has: id, projectId, fromVersion, toVersion, framework, status, createdAt,
    updatedAt, outcome_counts (including excluded), and has_gap_check_flags.
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
                "excluded": row.get("excluded_count") or 0,
            },
            "has_gap_check_flags": bool(row.get("has_gap_check_flags")),
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

    Excludes completed, skipped, failed, deferred, and excluded steps. Returns an empty list when:
      (a) all steps are done, or
      (b) no MigrationStep nodes exist in the graph (pre-redesign data — use build_recipe_plan instead).
    Supports effort_filter (e.g. ['mechanical']) and scope_filter (e.g. ['api-surface']) to narrow results.
    """
    stage_err = validate_context_id_for_stage(context_id)
    if stage_err:
        return stage_err
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


_VALID_OUTCOMES = {"completed", "skipped", "failed", "deferred", "excluded"}


@mcp.tool()
def update_step_status(
    context_id: str,
    step_id: str,
    outcome: str,
    reason: str = "",
) -> dict:
    """Record the outcome of a migration step: 'completed', 'skipped', 'failed', 'deferred', or 'excluded'.

    For outcome='deferred', the step's rule must have a BRIDGED_BY edge in the graph.
    For outcome='excluded', the step is removed from the pending queue but does not block
    final_status='complete' during close_migration_context.
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
    force_include: bool = False,
) -> dict:
    """Store the result summary for a queried entity in the context's queriedEntities cache.

    Call after each successful entity query in Loop II so resumed sessions can skip
    already-queried entities. When force_include=True (clarify stage), re-surface rules
    for this entity that were previously excluded by the entity filter.
    result_summary is truncated to 500 characters.
    Returns: status, context_id, entity_name, cached_count (total entries after upsert).
    On context not found: status='error', error_code='context_not_found'.
    """
    stage_err = validate_context_id_for_stage(context_id)
    if stage_err:
        return stage_err
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
    if force_include:
        context_queries.force_include_entity(
            context_id=context_id,
            entity_name=entity_name,
        )
    return {
        "status": "ok",
        "context_id": context_id,
        "entity_name": entity_name,
        "cached_count": result["cached_count"],
        "force_included": force_include,
    }


_VALID_FINAL_STATUSES = {"complete", "partial", "abandoned"}


@mcp.tool()
def close_migration_context(
    context_id: str,
    final_status: str,
    notes: str = "",
) -> dict:
    """Set completedAt, migration_status, and notes on a context. Call at the end of every session.

    final_status: 'complete' (all actionable steps done; excluded steps do not block complete),
    'partial' (steps were skipped or deferred), or 'abandoned' (session cancelled).
    Any other value is rejected.
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


_VALID_GAP_FLAG_TYPES = frozenset({
    "truncation",
    "applicability_uncertain",
    "stepless_rule",
    "bridge_eligible",
    "version_sanity",
    "paysafe_unresolved",
})

_VALID_EFFORTS = frozenset({"mechanical", "moderate", "architectural"})
_VALID_SEVERITY_HINTS = frozenset({"low", "medium", "high", "critical"})

# Public aliases for verification and external contracts (success-criteria.md Level 0).
MIGRATION_STEP_ORIGIN_VALUES = frozenset({"graph", "manual"})
STEP_OUTCOME_VALUES = _VALID_OUTCOMES
EFFORT_VALUES = _VALID_EFFORTS
SEVERITY_VALUES = _VALID_SEVERITY_HINTS
GAP_CHECK_FLAG_TYPES = _VALID_GAP_FLAG_TYPES

_LITE_GAP_CHECKS = (
    "truncation",
    "applicability_uncertain",
    "version_sanity",
    "paysafe_unresolved",
)
_FULL_ONLY_GAP_CHECKS = ("stepless_rule", "bridge_eligible")


def dedup_gap_check_flags(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Merge incoming flags into existing, deduplicating identical type+reference+message triples."""
    merged = list(existing)
    seen = {
        (f.get("type"), f.get("reference"), f.get("message"))
        for f in existing
    }
    for flag in incoming:
        key = (flag.get("type"), flag.get("reference"), flag.get("message"))
        if key not in seen:
            merged.append(flag)
            seen.add(key)
    return merged


def apply_gap_check_write(
    existing: list[dict],
    incoming: list[dict],
    *,
    overwrite: bool = False,
) -> list[dict]:
    if overwrite:
        return list(incoming)
    return dedup_gap_check_flags(existing, incoming)


def get_applicable_gap_checks(*, mode: str) -> list[str]:
    checks = list(_LITE_GAP_CHECKS)
    if mode == "full":
        checks.extend(_FULL_ONLY_GAP_CHECKS)
    return checks


def check_truncation(diagnostics: dict) -> bool:
    """Return True when rules_capped_at indicates truncation (authoritative source)."""
    return diagnostics.get("rules_capped_at") is not None


def compute_final_status(outcomes: list[str]) -> str:
    """Derive final_status from step outcomes; excluded does not block complete."""
    if "skipped" in outcomes or "failed" in outcomes:
        return "partial"
    return "complete"


def run_gap_check(context_id: str) -> list[dict]:
    """Run mode-aware gap-check audit and persist flags. Read-only on step/rule graph."""
    import json

    meta = context_queries.get_context_metadata(context_id=context_id)
    if meta is None:
        raise ValueError(f"Context not found: {context_id}")

    mode = meta.get("mode") or "full"
    applicable = set(get_applicable_gap_checks(mode=mode))
    flags: list[dict] = []

    diag_raw = meta.get("diagnostics")
    if diag_raw and "truncation" in applicable:
        try:
            diagnostics = json.loads(diag_raw) if isinstance(diag_raw, str) else diag_raw
        except (ValueError, TypeError):
            diagnostics = {}
        if check_truncation(diagnostics):
            flags.append({
                "type": "truncation",
                "reference": None,
                "message": (
                    f"Rule count capped at {diagnostics.get('rules_capped_at')} "
                    f"({diagnostics.get('rules_included')} included)."
                ),
            })

    if "applicability_uncertain" in applicable:
        pending = context_queries.get_pending_steps(context_id=context_id)
        for step in pending:
            if step.get("applicability") == "uncertain":
                flags.append({
                    "type": "applicability_uncertain",
                    "reference": step.get("rule_id"),
                    "message": f"Uncertain applicability for step: {step.get('summary', '')}",
                })

    if flags:
        context_queries.write_gap_check_flags(
            context_id=context_id,
            flags=flags,
            overwrite=False,
        )
    return flags


def resolve_execute_context(
    context_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Resolve the MigrationContext for the execute stage.

    When context_id is provided, validates it exists. When omitted, auto-discovers
    the sole in-progress context for project_id (or globally when project_id is also omitted).
    Returns an ambiguous_context error when multiple in-progress contexts match.
    """
    if context_id:
        if not context_queries.context_exists(context_id=context_id):
            return {
                "status": "error",
                "error_code": "context_not_found",
                "hint": f"Context '{context_id}' not found",
            }
        return {"status": "ok", "context_id": context_id}

    candidates = context_queries.get_in_progress_contexts(project_id=project_id)
    if not candidates:
        return {
            "status": "error",
            "error_code": "no_in_progress_context",
            "hint": "No in-progress MigrationContext found",
        }
    if len(candidates) == 1:
        return {"status": "ok", "context_id": candidates[0]["context_id"]}
    return {
        "status": "error",
        "error_code": "ambiguous_context",
        "hint": "Multiple in-progress contexts found — provide context_id explicitly",
        "candidates": [
            {
                "context_id": c["context_id"],
                "framework": c.get("framework") or "",
                "current_version": c.get("from_version") or "",
                "target_version": c.get("to_version") or "",
            }
            for c in candidates
        ],
    }


@mcp.tool()
def write_gap_check_flags(
    context_id: str,
    flags: list[dict],
    overwrite: bool = False,
) -> dict:
    """Persist gap-check findings on a MigrationContext.

    flags: list of {type, reference?, message} objects.
    overwrite: when True, replaces all existing flags; when False, appends and deduplicates.
    """
    stage_err = validate_context_id_for_stage(context_id)
    if stage_err:
        return stage_err
    if not flags:
        return {
            "status": "error",
            "error_code": "empty_flags",
            "hint": "flags must contain at least one entry",
        }
    for flag in flags:
        if flag.get("type") not in _VALID_GAP_FLAG_TYPES:
            return {
                "status": "error",
                "error_code": "invalid_flag_type",
                "hint": f"type must be one of: {', '.join(sorted(_VALID_GAP_FLAG_TYPES))}",
            }
        if not flag.get("message"):
            return {
                "status": "error",
                "error_code": "missing_message",
                "hint": "each flag must include a message",
            }
    try:
        persisted = context_queries.write_gap_check_flags(
            context_id=context_id,
            flags=flags,
            overwrite=overwrite,
        )
    except ValueError as exc:
        return {
            "status": "error",
            "error_code": "context_not_found",
            "hint": str(exc),
        }
    return {
        "status": "ok",
        "context_id": context_id,
        "flags": persisted,
        "flag_count": len(persisted),
    }


@mcp.tool()
def add_manual_step(
    context_id: str,
    summary: str,
    instruction: str,
    file_pattern: str | None = None,
    effort: str = "moderate",
    severity_hint: str = "medium",
) -> dict:
    """Add a context-scoped manual migration step during the clarify stage.

    Creates a MigrationStep with origin='manual' linked via OWNS_STEP to the context.
    """
    stage_err = validate_context_id_for_stage(context_id)
    if stage_err:
        return stage_err
    if not summary or not instruction:
        return {
            "status": "error",
            "error_code": "missing_required_field",
            "hint": "summary and instruction are required",
        }
    if effort not in _VALID_EFFORTS:
        return {
            "status": "error",
            "error_code": "invalid_effort",
            "hint": f"effort must be one of: {', '.join(sorted(_VALID_EFFORTS))}",
        }
    if severity_hint not in _VALID_SEVERITY_HINTS:
        return {
            "status": "error",
            "error_code": "invalid_severity_hint",
            "hint": f"severity_hint must be one of: {', '.join(sorted(_VALID_SEVERITY_HINTS))}",
        }
    meta = context_queries.get_context_metadata(context_id=context_id)
    if meta is None:
        return {
            "status": "error",
            "error_code": "context_not_found",
            "hint": f"Context '{context_id}' not found",
        }
    if meta.get("status") != "in-progress":
        return {
            "status": "error",
            "error_code": "context_not_open",
            "hint": f"Context '{context_id}' has status '{meta.get('status')}' — manual steps require in-progress",
        }
    try:
        created = context_queries.add_manual_step(
            context_id=context_id,
            summary=summary,
            instruction=instruction,
            file_pattern=file_pattern,
            effort=effort,
            severity_hint=severity_hint,
        )
    except ValueError as exc:
        return {
            "status": "error",
            "error_code": "context_not_found",
            "hint": str(exc),
        }
    return {
        "status": "ok",
        "context_id": context_id,
        "step_id": created["step_id"],
        "summary": created.get("summary") or summary,
        "origin": "manual",
    }

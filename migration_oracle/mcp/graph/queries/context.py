"""MigrationContext Cypher queries."""

from __future__ import annotations

from migration_oracle.graph.driver import read_session, write_session
from migration_oracle.mcp.graph.queries._severity import SEVERITY_RANK, severity_meets_threshold

_CREATE_OR_GET_CONTEXT = """
MERGE (ctx:MigrationContext {
  projectId: $project_id,
  fromVersion: $from_version,
  toVersion: $to_version
})
ON CREATE SET
  ctx.framework = $framework,
  ctx.status = 'in-progress',
  ctx.scannedEntities = $scanned_entities,
  ctx.completedSteps = [],
  ctx.skippedSteps = [],
  ctx.failedSteps = [],
  ctx.queriedEntities = '{}',
  ctx.createdAt = datetime(),
  ctx.completedAt = null,
  ctx.notes = '',
  ctx._was_created = true
ON MATCH SET
  ctx._was_created = false
WITH ctx
MATCH (vf:Version {framework: $framework, version: $from_version})
MATCH (vt:Version {framework: $framework, version: $to_version})
MERGE (ctx)-[:UPGRADES_FROM]->(vf)
MERGE (ctx)-[:UPGRADES_TO]->(vt)
RETURN elementId(ctx) AS context_id,
       ctx.projectId AS project_id,
       ctx.fromVersion AS from_version,
       ctx.toVersion AS to_version,
       ctx.framework AS framework,
       ctx.status AS migration_status,
       ctx.scannedEntities AS scanned_entities,
       ctx.completedSteps AS completed_steps,
       ctx.skippedSteps AS skipped_steps,
       ctx.failedSteps AS failed_steps,
       toString(ctx.createdAt) AS created_at,
       CASE WHEN ctx.completedAt IS NULL THEN null ELSE toString(ctx.completedAt) END AS completed_at,
       coalesce(ctx.notes, '') AS notes,
       coalesce(ctx._was_created, false) AS created
"""

_GET_PENDING_STEPS = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
WHERE NOT elementId(s) IN ctx.completedSteps
  AND NOT elementId(s) IN ctx.skippedSteps
  AND NOT elementId(s) IN coalesce(ctx.failedSteps, [])
  AND (size($effort_filter) = 0 OR s.effort IN $effort_filter)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
  WHERE size($scope_filter) = 0 OR bs.scope IN $scope_filter
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
  WHERE ab.auto = true AND ab.missingRequiredParams = []
OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
RETURN elementId(s) AS step_id,
       s.stepType AS step_type,
       elementId(r) AS rule_id,
       s.summary AS summary,
       s.instruction AS instruction,
       s.verificationHint AS verification_hint,
       s.effort AS effort,
       s.automatable AS automatable,
       bs.scope AS scope,
       bs.severity AS severity,
       rec.recipeId AS recipe_id,
       s.stepIndex AS _step_index,
       CASE bs.severity
         WHEN 'critical' THEN 0 WHEN 'high' THEN 1
         WHEN 'medium'   THEN 2 ELSE 3
       END AS _severity_rank,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY _severity_rank ASC, _step_index ASC
"""

_RECORD_STEP_OUTCOME = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.completedSteps = CASE $outcome WHEN 'completed'
    THEN ctx.completedSteps + [$step_id] ELSE ctx.completedSteps END,
    ctx.skippedSteps = CASE $outcome WHEN 'skipped'
    THEN ctx.skippedSteps + [$step_id] ELSE ctx.skippedSteps END,
    ctx.failedSteps = CASE $outcome WHEN 'failed'
    THEN coalesce(ctx.failedSteps, []) + [$step_id] ELSE coalesce(ctx.failedSteps, []) END
RETURN elementId(ctx) AS context_id,
       size(ctx.completedSteps) AS completed_count,
       size(ctx.skippedSteps) AS skipped_count,
       ctx.status AS migration_status
"""

_AUTO_CLOSE_WRITE = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.status = 'complete', ctx.completedAt = datetime()
RETURN elementId(ctx) AS context_id, ctx.status AS migration_status
"""

_GET_STEPS_FOR_SCOPE_TIER = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
MATCH (v:Version)
WHERE v.sortableVersion > from_v.sortableVersion
  AND v.sortableVersion <= to_v.sortableVersion
MATCH (v)-[:INCLUDES_RULE]->(r:MigrationRule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
WHERE bs.scope = $scope
OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE e.name IN ctx.scannedEntities
RETURN DISTINCT e.name AS entity_name,
       labels(e)[0] AS entity_type,
       elementId(s) AS step_id,
       elementId(r) AS rule_id,
       s.summary AS summary,
       bs.scope AS scope,
       bs.severity AS severity
"""

_CLOSE_CONTEXT = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.status = $final_status,
    ctx.completedAt = datetime(),
    ctx.notes = $notes
RETURN elementId(ctx) AS context_id,
       ctx.status AS migration_status,
       ctx.completedSteps AS completed_steps,
       ctx.skippedSteps AS skipped_steps,
       toString(ctx.completedAt) AS completed_at,
       coalesce(ctx.notes, '') AS notes
"""


def create_or_get_context(
    *,
    project_id: str,
    from_version: str,
    to_version: str,
    framework: str,
    scanned_entities: list[str],
) -> dict:
    with write_session() as session:
        record = session.run(
            _CREATE_OR_GET_CONTEXT,
            project_id=project_id,
            from_version=from_version,
            to_version=to_version,
            framework=framework,
            scanned_entities=scanned_entities,
        ).single()
    if record is None:
        raise RuntimeError("Failed to create or load MigrationContext")
    return dict(record)


def get_pending_steps(
    *,
    context_id: str,
    effort_filter: list[str] | None = None,
    scope_filter: list[str] | None = None,
) -> list[dict]:
    with read_session() as session:
        rows = [
            dict(row)
            for row in session.run(
                _GET_PENDING_STEPS,
                context_id=context_id,
                effort_filter=effort_filter or [],
                scope_filter=scope_filter or [],
            )
        ]
    _internal = {"_step_index", "_severity_rank"}
    return [{k: v for k, v in row.items() if k not in _internal} for row in rows]


def record_step_outcome(
    *,
    context_id: str,
    step_id: str,
    outcome: str,
) -> dict:
    with write_session() as session:
        record = session.run(
            _RECORD_STEP_OUTCOME,
            context_id=context_id,
            step_id=step_id,
            outcome=outcome,
        ).single()
    if record is None:
        raise ValueError(f"Context not found: {context_id}")
    return dict(record)


def auto_close_write(*, context_id: str) -> dict:
    with write_session() as session:
        record = session.run(_AUTO_CLOSE_WRITE, context_id=context_id).single()
    if record is None:
        raise ValueError(f"Context not found: {context_id}")
    return dict(record)


def get_steps_for_scope_tier(
    *,
    context_id: str,
    scope: str,
    min_severity: str,
) -> list[dict]:
    with read_session() as session:
        rows = [
            dict(row)
            for row in session.run(
                _GET_STEPS_FOR_SCOPE_TIER,
                context_id=context_id,
                scope=scope,
            )
        ]
    return [
        row
        for row in rows
        if row.get("entity_name")
        and severity_meets_threshold(row.get("severity"), min_severity)
    ]


def close_migration_context(
    *,
    context_id: str,
    final_status: str,
    notes: str = "",
) -> dict:
    with write_session() as session:
        record = session.run(
            _CLOSE_CONTEXT,
            context_id=context_id,
            final_status=final_status,
            notes=notes,
        ).single()
    if record is None:
        raise ValueError(f"Context not found: {context_id}")
    return dict(record)

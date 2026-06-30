"""MigrationContext Cypher queries."""

from __future__ import annotations

from migration_oracle.graph.driver import read_session, write_session
from migration_oracle.mcp.graph.queries._severity import SEVERITY_RANK, severity_meets_threshold


class VersionNotInGraphError(Exception):
    """Raised when a requested version is not present in the graph."""

    def __init__(self, version: str, available: list[str] | None = None) -> None:
        self.version = version
        self.available = available or []
        hint = f" Available: {self.available}" if self.available else ""
        super().__init__(f"Version '{version}' not found in graph.{hint}")

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
  ctx.deferredSteps = [],
  ctx.excludedSteps = [],
  ctx.queriedEntities = '{}',
  ctx.gapCheckFlags = '[]',
  ctx.forceIncludedEntities = [],
  ctx.createdAt = datetime(),
  ctx.updatedAt = datetime(),
  ctx.completedAt = null,
  ctx.notes = '',
  ctx._was_created = true,
  ctx.scannedClasses       = $scanned_classes,
  ctx.scannedClassSimple   = $scanned_class_simple,
  ctx.scannedDepsGa        = $scanned_deps_ga,
  ctx.scannedDepArtifacts  = $scanned_dep_artifacts,
  ctx.scannedProps         = $scanned_props
ON MATCH SET
  ctx._was_created = false,
  ctx.updatedAt = datetime(),
  ctx.scannedClasses       = $scanned_classes,
  ctx.scannedClassSimple   = $scanned_class_simple,
  ctx.scannedDepsGa        = $scanned_deps_ga,
  ctx.scannedDepArtifacts  = $scanned_dep_artifacts,
  ctx.scannedProps         = $scanned_props
WITH ctx
MATCH (vf:Version) WHERE elementId(vf) = $from_node_id
MATCH (vt:Version) WHERE elementId(vt) = $to_node_id
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
       coalesce(ctx.deferredSteps, []) AS deferred_steps,
       toString(ctx.createdAt) AS created_at,
       toString(ctx.updatedAt) AS updated_at,
       CASE WHEN ctx.completedAt IS NULL THEN null ELSE toString(ctx.completedAt) END AS completed_at,
       coalesce(ctx.notes, '') AS notes,
       coalesce(ctx._was_created, false) AS created
"""

_GET_MIGRATION_CONTEXTS = """
MATCH (ctx:MigrationContext {projectId: $project_id})
WHERE ($framework IS NULL OR ctx.framework = $framework)

OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(:MigrationStep)
WITH ctx,
     count(CASE WHEN so.status = 'completed' THEN 1 END) AS completed_count,
     count(CASE WHEN so.status = 'failed'    THEN 1 END) AS failed_count,
     count(CASE WHEN so.status = 'skipped'   THEN 1 END) AS skipped_count,
     count(CASE WHEN so.status = 'deferred'  THEN 1 END) AS deferred_count,
     count(CASE WHEN so.status = 'excluded'  THEN 1 END) AS excluded_count,
     (ctx.gapCheckFlags IS NOT NULL AND ctx.gapCheckFlags <> '[]') AS has_gap_check_flags

RETURN
  elementId(ctx)          AS id,
  ctx.projectId           AS projectId,
  ctx.fromVersion         AS fromVersion,
  ctx.toVersion           AS toVersion,
  ctx.framework           AS framework,
  ctx.status              AS status,
  toString(ctx.createdAt) AS createdAt,
  toString(ctx.updatedAt) AS updatedAt,
  completed_count,
  failed_count,
  skipped_count,
  deferred_count,
  excluded_count,
  has_gap_check_flags

ORDER BY ctx.createdAt DESC
"""

_GET_CONTEXT_BY_ID = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id

OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(:MigrationStep)
WITH ctx,
     count(CASE WHEN so.status = 'completed' THEN 1 END) AS completed_count,
     count(CASE WHEN so.status = 'failed'    THEN 1 END) AS failed_count,
     count(CASE WHEN so.status = 'skipped'   THEN 1 END) AS skipped_count,
     count(CASE WHEN so.status = 'deferred'  THEN 1 END) AS deferred_count,
     count(CASE WHEN so.status = 'excluded'  THEN 1 END) AS excluded_count,
     (ctx.gapCheckFlags IS NOT NULL AND ctx.gapCheckFlags <> '[]') AS has_gap_check_flags

RETURN
  elementId(ctx)          AS id,
  ctx.projectId           AS projectId,
  ctx.fromVersion         AS fromVersion,
  ctx.toVersion           AS toVersion,
  ctx.framework           AS framework,
  ctx.status              AS status,
  toString(ctx.createdAt) AS createdAt,
  toString(ctx.updatedAt) AS updatedAt,
  completed_count,
  failed_count,
  skipped_count,
  deferred_count,
  excluded_count,
  has_gap_check_flags
LIMIT 1
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
  AND NOT elementId(s) IN coalesce(ctx.deferredSteps, [])
  AND NOT elementId(s) IN coalesce(ctx.excludedSteps, [])
  AND (size($effort_filter) = 0 OR s.effort IN $effort_filter)

OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
  WHERE size($scope_filter) = 0 OR bs.scope IN $scope_filter
WITH ctx, r, s,
     min(CASE bs.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END) AS sev_rank,
     head(collect(DISTINCT bs.scope))    AS scope,
     head(collect(DISTINCT bs.severity)) AS severity

WITH ctx, r, s, sev_rank, scope, severity,
     coalesce(ctx.scannedClasses,      []) AS sc_c,
     coalesce(ctx.scannedClassSimple,  []) AS sc_cs,
     coalesce(ctx.scannedDepsGa,       []) AS sc_dga,
     coalesce(ctx.scannedDepArtifacts, []) AS sc_da,
     coalesce(ctx.scannedProps,        []) AS sc_p,
     coalesce(ctx.forceIncludedEntities, []) AS force_included,
     (size(coalesce(ctx.scannedClasses, [])) > 0
       OR size(coalesce(ctx.scannedClassSimple, [])) > 0
       OR size(coalesce(ctx.scannedDepsGa, [])) > 0
       OR size(coalesce(ctx.scannedDepArtifacts, [])) > 0
       OR size(coalesce(ctx.scannedProps, [])) > 0) AS has_filter

OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH r, s, sev_rank, scope, severity, sc_c, sc_cs, sc_dga, sc_da, sc_p, has_filter, force_included, e,
     CASE
       WHEN e IS NULL THEN false
       WHEN e:Class THEN
            e.name IN sc_c
         OR last(split(e.name, '.')) IN sc_cs
       WHEN e:ApplicationProperty THEN e.name IN sc_p
       WHEN e:Dependency THEN
            (size(split(e.name, ':')) >= 2
               AND (split(e.name, ':')[0]+':'+split(e.name, ':')[1]) IN sc_dga)
         OR last(split(e.name, ':')) IN sc_da
         // Package-prefix bridge: primary = Class node package, fallback = groupId (T046)
         OR any(cls IN sc_c WHERE
              any(ruleClass IN [(r)-[:AFFECTS_CLASS]->(rc:Class) | rc.name] WHERE
                cls STARTS WITH (left(ruleClass,
                  size(ruleClass) - size(split(ruleClass, '.')[size(split(ruleClass, '.'))-1]) - 1) + '.')
              )
            )
         OR (
              // Fallback: only when rule has no Class nodes at all (Dependency-only rule)
              NOT (r)-[:AFFECTS_CLASS]->(:Class)
              AND size(split(e.name, ':')) >= 2
              AND any(cls IN sc_c WHERE
                cls STARTS WITH (split(e.name, ':')[0] + '.')
              )
            )
       ELSE false
     END AS entity_match

WITH r, s, sev_rank, scope, severity, has_filter, force_included,
     count(DISTINCT e)                             AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END) AS match_count,
     sum(CASE WHEN e IS NOT NULL AND e.name IN force_included THEN 1 ELSE 0 END) AS force_match_count

WITH r, s, sev_rank, scope, severity,
     CASE WHEN affected_count = 0 THEN 'informational'
          WHEN NOT has_filter     THEN 'universal'
          WHEN match_count > 0    THEN 'matched'
          WHEN force_match_count > 0 THEN 'matched'
          WHEN sev_rank <= 1      THEN 'uncertain'
          ELSE                         'excluded' END AS applicability
WHERE applicability <> 'excluded'

OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
  WHERE ab.auto = true AND coalesce(ab.missingRequiredParams, []) = []
OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
RETURN elementId(s) AS step_id,
       s.stepType    AS step_type,
       coalesce(r.ruleId, elementId(r))  AS rule_id,
       s.summary     AS summary,
       s.instruction AS instruction,
       s.verificationHint AS verification_hint,
       s.effort      AS effort,
       s.automatable AS automatable,
       scope, severity, applicability,
       rec.recipeId  AS recipe_id,
       s.stepIndex   AS _step_index,
       sev_rank      AS _severity_rank,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY _severity_rank ASC, _step_index ASC
"""

_GET_PENDING_MANUAL_STEPS = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:OWNS_STEP]->(s:MigrationStep {origin: "manual"})
WHERE NOT elementId(s) IN ctx.completedSteps
  AND NOT elementId(s) IN ctx.skippedSteps
  AND NOT elementId(s) IN coalesce(ctx.failedSteps, [])
  AND NOT elementId(s) IN coalesce(ctx.deferredSteps, [])
  AND NOT elementId(s) IN coalesce(ctx.excludedSteps, [])
  AND (size($effort_filter) = 0 OR s.effort IN $effort_filter)
  AND (size($scope_filter) = 0 OR coalesce(s.scope, '') IN $scope_filter)
RETURN elementId(s) AS step_id,
       s.stepType    AS step_type,
       coalesce(s.ruleId, 'manual') AS rule_id,
       s.summary     AS summary,
       s.instruction AS instruction,
       s.verificationHint AS verification_hint,
       s.effort      AS effort,
       coalesce(s.automatable, false) AS automatable,
       coalesce(s.scope, 'config') AS scope,
       coalesce(s.severity, 'medium') AS severity,
       'manual' AS applicability,
       s.origin AS origin,
       null AS recipe_id,
       coalesce(s.stepIndex, 9999) AS _step_index,
       CASE coalesce(s.severity, 'medium')
         WHEN 'critical' THEN 0 WHEN 'high' THEN 1
         WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END AS _severity_rank,
       [] AS requires
ORDER BY _severity_rank ASC, _step_index ASC
"""

_RECORD_STEP_OUTCOME = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.completedSteps = CASE $outcome WHEN 'completed'
    THEN ctx.completedSteps + [$step_id] ELSE ctx.completedSteps END,
    ctx.skippedSteps = CASE $outcome WHEN 'skipped'
    THEN ctx.skippedSteps + [$step_id] ELSE ctx.skippedSteps END,
    ctx.failedSteps = CASE $outcome WHEN 'failed'
    THEN coalesce(ctx.failedSteps, []) + [$step_id] ELSE coalesce(ctx.failedSteps, []) END,
    ctx.deferredSteps = CASE $outcome WHEN 'deferred'
    THEN coalesce(ctx.deferredSteps, []) + [$step_id] ELSE coalesce(ctx.deferredSteps, []) END,
    ctx.excludedSteps = CASE $outcome WHEN 'excluded'
    THEN coalesce(ctx.excludedSteps, []) + [$step_id] ELSE coalesce(ctx.excludedSteps, []) END,
    ctx.updatedAt = datetime()
WITH ctx
MATCH (step:MigrationStep) WHERE elementId(step) = $step_id
MERGE (ctx)-[so:STEP_OUTCOME]->(step)
SET so.status    = $outcome,
    so.reason    = $reason,
    so.updatedAt = datetime()
RETURN elementId(ctx) AS context_id,
       size(ctx.completedSteps) AS completed_count,
       size(ctx.skippedSteps) AS skipped_count,
       ctx.status AS migration_status
"""

_CHECK_STEP_ON_PATH = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
OPTIONAL MATCH (ctx)-[:OWNS_STEP]->(owned:MigrationStep)
  WHERE elementId(owned) = $step_id
OPTIONAL MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
OPTIONAL MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
OPTIONAL MATCH (v:Version)-[:INCLUDES_RULE]->(:MigrationRule)-[:REQUIRES_STEP]->(pathStep:MigrationStep)
  WHERE elementId(pathStep) = $step_id
    AND v.sortableVersion > from_v.sortableVersion
    AND v.sortableVersion <= to_v.sortableVersion
RETURN owned IS NOT NULL OR pathStep IS NOT NULL AS on_path
"""

_AUTO_CLOSE_WRITE = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.status = 'complete', ctx.completedAt = datetime(), ctx.updatedAt = datetime()
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
    ctx.updatedAt = datetime(),
    ctx.notes = $notes
RETURN elementId(ctx) AS context_id,
       ctx.status AS migration_status,
       ctx.completedSteps AS completed_steps,
       ctx.skippedSteps AS skipped_steps,
       toString(ctx.completedAt) AS completed_at,
       coalesce(ctx.notes, '') AS notes
"""


_CHECK_BRIDGE_DISCOVERABILITY = """
MATCH (s:MigrationStep) WHERE elementId(s) = $step_id
MATCH (r:MigrationRule)-[:REQUIRES_STEP]->(s)
OPTIONAL MATCH (r)-[:BRIDGED_BY]->(b:Dependency)
RETURN b.name AS bridge_name, b.applicableRuleTypes AS applicable_rule_types
LIMIT 1
"""

_RESOLVE_DEFERRED_STEPS = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
UNWIND coalesce(ctx.deferredSteps, []) AS deferred_id
MATCH (ds:MigrationStep) WHERE elementId(ds) = deferred_id
MATCH (ctx)-[dso:STEP_OUTCOME]->(ds) WHERE dso.status = 'deferred'
WHERE $completed_step_id IN dso.reason
RETURN elementId(ds) AS deferred_step_id, dso.reason AS reason
"""

_AUTO_RESOLVE_DEFERRED = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ds:MigrationStep) WHERE elementId(ds) = $deferred_step_id
MATCH (ctx)-[dso:STEP_OUTCOME]->(ds)
SET dso.status = 'completed',
    dso.resolvedVia = 'bridge',
    dso.bridgeResolvedAt = datetime(),
    dso.updatedAt = datetime(),
    ctx.deferredSteps = [d IN coalesce(ctx.deferredSteps, []) WHERE d <> $deferred_step_id],
    ctx.completedSteps = ctx.completedSteps + [$deferred_step_id],
    ctx.updatedAt = datetime()
RETURN elementId(ds) AS resolved_step_id
"""


def check_bridge_discoverability(*, step_id: str) -> dict | None:
    with read_session() as session:
        record = session.run(_CHECK_BRIDGE_DISCOVERABILITY, step_id=step_id).single()
    if record is None:
        return None
    return dict(record)


def auto_resolve_deferred_steps(*, context_id: str, completed_step_id: str) -> list[str]:
    """After a step is completed, resolve any deferred steps whose requiredChange = that step."""
    import json

    # First fetch deferred steps with their reasons
    with read_session() as session:
        rows = list(session.run(
            """
            MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
            UNWIND coalesce(ctx.deferredSteps, []) AS deferred_id
            MATCH (ds:MigrationStep) WHERE elementId(ds) = deferred_id
            MATCH (ctx)-[dso:STEP_OUTCOME]->(ds) WHERE dso.status = 'deferred'
            RETURN elementId(ds) AS deferred_step_id, dso.reason AS reason
            """,
            context_id=context_id,
        ))

    resolved_ids: list[str] = []
    for row in rows:
        reason_raw = row.get("reason") or ""
        try:
            reason_obj = json.loads(reason_raw)
        except (ValueError, TypeError):
            continue
        if reason_obj.get("requiredChange") == completed_step_id:
            with write_session() as session:
                session.run(
                    _AUTO_RESOLVE_DEFERRED,
                    context_id=context_id,
                    deferred_step_id=row["deferred_step_id"],
                ).single()
            resolved_ids.append(row["deferred_step_id"])

    return resolved_ids


def create_or_get_context(
    *,
    project_id: str,
    from_version: str,
    to_version: str,
    framework: str,
    scanned_entities: list[str],
    scanned_classes: list[str] | None = None,
    scanned_class_simple: list[str] | None = None,
    scanned_deps_ga: list[str] | None = None,
    scanned_dep_artifacts: list[str] | None = None,
    scanned_props: list[str] | None = None,
    from_node_id: str = "",
    to_node_id: str = "",
) -> dict:
    with write_session() as session:
        record = session.run(
            _CREATE_OR_GET_CONTEXT,
            project_id=project_id,
            from_version=from_version,
            to_version=to_version,
            framework=framework,
            scanned_entities=scanned_entities,
            scanned_classes=scanned_classes or [],
            scanned_class_simple=scanned_class_simple or [],
            scanned_deps_ga=scanned_deps_ga or [],
            scanned_dep_artifacts=scanned_dep_artifacts or [],
            scanned_props=scanned_props or [],
            from_node_id=from_node_id,
            to_node_id=to_node_id,
        ).single()
    if record is None:
        raise RuntimeError("Failed to create or load MigrationContext")
    return dict(record)


def get_migration_contexts(
    *,
    project_id: str,
    framework: str | None = None,
) -> list[dict]:
    with read_session() as session:
        rows = [
            dict(row)
            for row in session.run(
                _GET_MIGRATION_CONTEXTS,
                project_id=project_id,
                framework=framework,
            )
        ]
    return rows


def get_context_by_id(*, context_id: str) -> dict | None:
    with read_session() as session:
        record = session.run(_GET_CONTEXT_BY_ID, context_id=context_id).single()
    if record is None:
        return None
    return dict(record)


def get_pending_steps(
    *,
    context_id: str,
    effort_filter: list[str] | None = None,
    scope_filter: list[str] | None = None,
) -> list[dict]:
    params = {
        "context_id": context_id,
        "effort_filter": effort_filter or [],
        "scope_filter": scope_filter or [],
    }
    with read_session() as session:
        graph_rows = [
            dict(row)
            for row in session.run(_GET_PENDING_STEPS, **params)
        ]
        manual_rows = [
            dict(row)
            for row in session.run(_GET_PENDING_MANUAL_STEPS, **params)
        ]
    _internal = {"_step_index", "_severity_rank"}
    combined = graph_rows + manual_rows
    combined.sort(
        key=lambda r: (
            r.get("_severity_rank", 4),
            r.get("_step_index", 9999),
        )
    )
    return [{k: v for k, v in row.items() if k not in _internal} for row in combined]


def step_on_path_or_owned(*, context_id: str, step_id: str) -> bool:
    with read_session() as session:
        record = session.run(
            _CHECK_STEP_ON_PATH,
            context_id=context_id,
            step_id=step_id,
        ).single()
    if record is None:
        return False
    return bool(record.get("on_path"))


def record_step_outcome(
    *,
    context_id: str,
    step_id: str,
    outcome: str,
    reason: str = "",
) -> dict:
    if not step_on_path_or_owned(context_id=context_id, step_id=step_id):
        return {"on_path": False}
    with write_session() as session:
        record = session.run(
            _RECORD_STEP_OUTCOME,
            context_id=context_id,
            step_id=step_id,
            outcome=outcome,
            reason=reason,
        ).single()
    if record is None:
        raise ValueError(f"Context not found: {context_id}")
    result = dict(record)
    result["on_path"] = True
    return result


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


def delete_zombie_context(
    *,
    project_id: str,
    from_version: str,
    to_version: str,
) -> None:
    """Delete a MigrationContext node that was created with an invalid version."""
    with write_session() as session:
        session.run(
            """
            MATCH (ctx:MigrationContext {
              projectId: $project_id,
              fromVersion: $from_version,
              toVersion: $to_version
            })
            DETACH DELETE ctx
            """,
            project_id=project_id,
            from_version=from_version,
            to_version=to_version,
        )


_CHECK_CONTEXT_VERSION_MATCH = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
OPTIONAL MATCH (ctx)-[:UPGRADES_FROM]->(vf)
OPTIONAL MATCH (ctx)-[:UPGRADES_TO]->(vt)
RETURN coalesce(elementId(vf) = $from_node_id AND elementId(vt) = $to_node_id, false) AS match
"""


def check_context_version_match(
    *,
    context_id: str,
    from_node_id: str,
    to_node_id: str,
) -> bool:
    """Return True if the context's UPGRADES_FROM/UPGRADES_TO edges point to the given node IDs."""
    with read_session() as session:
        record = session.run(
            _CHECK_CONTEXT_VERSION_MATCH,
            context_id=context_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
        ).single()
    if record is None:
        return False
    return bool(record.get("match"))


_GET_QUERIED_ENTITIES = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id
RETURN ctx.queriedEntities AS qe
"""

_SET_QUERIED_ENTITIES = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id
SET ctx.queriedEntities = $updated_json
RETURN 1
"""


def update_queried_entity(
    *,
    context_id: str,
    entity_name: str,
    result_summary: str,
) -> dict | None:
    """Read-modify-write queriedEntities on a MigrationContext.

    Returns None if context not found, else {"cached_count": <len after upsert>}.
    Sequential calls required — no concurrent writes.
    """
    import json

    with read_session() as session:
        record = session.run(_GET_QUERIED_ENTITIES, id=context_id).single()
    if record is None:
        return None

    raw = record.get("qe") or "{}"
    try:
        current: dict = json.loads(raw)
    except (ValueError, TypeError):
        current = {}

    current[entity_name] = result_summary[:500]
    updated_json = json.dumps(current)

    with write_session() as session:
        session.run(_SET_QUERIED_ENTITIES, id=context_id, updated_json=updated_json).single()

    return {"cached_count": len(current)}


_GET_CONTEXT_VERSION_BOUNDS = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
MATCH (ctx)-[:UPGRADES_FROM]->(from_v:Version)
MATCH (ctx)-[:UPGRADES_TO]->(to_v:Version)
RETURN from_v.version AS from_version,
       to_v.version AS to_version,
       ctx.framework AS framework
"""


def get_context_version_bounds(*, context_id: str) -> dict | None:
    """Return the resolved from/to version strings from context's UPGRADES_FROM/UPGRADES_TO edges."""
    with read_session() as session:
        record = session.run(_GET_CONTEXT_VERSION_BOUNDS, context_id=context_id).single()
    if record is None:
        return None
    return dict(record)


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


_CONTEXT_EXISTS = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
RETURN elementId(ctx) AS id, ctx.status AS status
LIMIT 1
"""

_GET_CONTEXT_METADATA = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
RETURN elementId(ctx) AS context_id,
       ctx.projectId AS project_id,
       ctx.fromVersion AS from_version,
       ctx.toVersion AS to_version,
       ctx.framework AS framework,
       ctx.status AS status,
       ctx.mode AS mode,
       coalesce(ctx.diagnostics, null) AS diagnostics,
       coalesce(ctx.gapCheckFlags, '[]') AS gap_check_flags
"""

_SET_DIAGNOSTICS_ON_CREATE = """
MATCH (ctx:MigrationContext)
WHERE elementId(ctx) = $context_id AND ctx.diagnostics IS NULL
SET ctx.diagnostics = $diagnostics_json
RETURN 1
"""

_WRITE_GAP_CHECK_FLAGS = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.gapCheckFlags = $flags_json,
    ctx.updatedAt = datetime()
RETURN coalesce(ctx.gapCheckFlags, '[]') AS gap_check_flags
"""

_CREATE_MANUAL_STEP = """
MATCH (ctx:MigrationContext)
WHERE elementId(ctx) = $context_id AND ctx.status = 'in-progress'
CREATE (s:MigrationStep {
  origin: 'manual',
  stepType: 'manual',
  summary: $summary,
  instruction: $instruction,
  verificationHint: '',
  effort: $effort,
  automatable: false,
  scope: coalesce($file_pattern, 'config'),
  severity: $severity_hint,
  stepIndex: 9999
})
CREATE (ctx)-[:OWNS_STEP]->(s)
RETURN elementId(s) AS step_id, s.summary AS summary
"""

_FORCE_INCLUDE_ENTITY = """
MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
SET ctx.forceIncludedEntities = coalesce(ctx.forceIncludedEntities, []) + [$entity_name],
    ctx.updatedAt = datetime()
RETURN size(ctx.forceIncludedEntities) AS force_included_count
"""

_GET_IN_PROGRESS_CONTEXTS = """
MATCH (ctx:MigrationContext)
WHERE ($project_id IS NULL OR ctx.projectId = $project_id)
  AND ctx.status = 'in-progress'
RETURN elementId(ctx) AS context_id,
       ctx.projectId AS project_id,
       ctx.fromVersion AS from_version,
       ctx.toVersion AS to_version,
       ctx.framework AS framework
ORDER BY ctx.updatedAt DESC
"""


def context_exists(*, context_id: str) -> bool:
    with read_session() as session:
        record = session.run(_CONTEXT_EXISTS, context_id=context_id).single()
    return record is not None


def get_context_metadata(*, context_id: str) -> dict | None:
    with read_session() as session:
        record = session.run(_GET_CONTEXT_METADATA, context_id=context_id).single()
    if record is None:
        return None
    return dict(record)


def set_diagnostics_on_create(*, context_id: str, diagnostics: dict) -> None:
    import json

    with write_session() as session:
        session.run(
            _SET_DIAGNOSTICS_ON_CREATE,
            context_id=context_id,
            diagnostics_json=json.dumps(diagnostics),
        ).single()


def write_gap_check_flags(
    *,
    context_id: str,
    flags: list[dict],
    overwrite: bool = False,
) -> list[dict]:
    import json

    existing: list[dict] = []
    if not overwrite:
        meta = get_context_metadata(context_id=context_id)
        if meta is not None:
            raw = meta.get("gap_check_flags") or "[]"
            try:
                existing = json.loads(raw)
            except (ValueError, TypeError):
                existing = []

    merged = list(existing)
    seen = {
        (f.get("type"), f.get("reference"), f.get("message"))
        for f in existing
    }
    for flag in flags:
        key = (flag.get("type"), flag.get("reference"), flag.get("message"))
        if key not in seen:
            merged.append(flag)
            seen.add(key)

    with write_session() as session:
        record = session.run(
            _WRITE_GAP_CHECK_FLAGS,
            context_id=context_id,
            flags_json=json.dumps(merged),
        ).single()
    if record is None:
        raise ValueError(f"Context not found: {context_id}")
    return merged


def add_manual_step(
    *,
    context_id: str,
    summary: str,
    instruction: str,
    file_pattern: str | None = None,
    effort: str = "moderate",
    severity_hint: str = "medium",
) -> dict:
    with write_session() as session:
        record = session.run(
            _CREATE_MANUAL_STEP,
            context_id=context_id,
            summary=summary,
            instruction=instruction,
            file_pattern=file_pattern,
            effort=effort,
            severity_hint=severity_hint,
        ).single()
    if record is None:
        meta = get_context_metadata(context_id=context_id)
        if meta is None:
            raise ValueError(f"Context not found: {context_id}")
        if meta.get("status") != "in-progress":
            raise ValueError(f"Context '{context_id}' is not in-progress")
        raise RuntimeError(f"Failed to add manual step to context '{context_id}'")
    return dict(record)


def force_include_entity(*, context_id: str, entity_name: str) -> int:
    with write_session() as session:
        record = session.run(
            _FORCE_INCLUDE_ENTITY,
            context_id=context_id,
            entity_name=entity_name,
        ).single()
    if record is None:
        raise ValueError(f"Context not found: {context_id}")
    return int(record.get("force_included_count") or 0)


def get_in_progress_contexts(*, project_id: str | None = None) -> list[dict]:
    with read_session() as session:
        rows = [
            dict(row)
            for row in session.run(_GET_IN_PROGRESS_CONTEXTS, project_id=project_id)
        ]
    return rows

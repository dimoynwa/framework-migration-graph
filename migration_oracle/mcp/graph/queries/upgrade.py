"""Upgrade path and recipe plan Cypher queries."""

from __future__ import annotations

from typing import Literal

from migration_oracle.graph.driver import read_session, write_session
from migration_oracle.mcp.graph.queries._severity import filter_by_scope_and_severity
from migration_oracle.models.graph import (
    VersionResolutionFailure,
    VersionResolutionResult,
    sortable_version,
)

# ---------------------------------------------------------------------------
# resolve_version — canonical version resolution (T004)
# ---------------------------------------------------------------------------

_RESOLVE_EXACT = """
MATCH (v:Version {framework: $framework, version: $version})
RETURN elementId(v) AS node_id, v.version AS resolved_version, v.sortableVersion AS sortable
LIMIT 1
"""

_RESOLVE_FLOOR = """
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion <= $sortable
RETURN elementId(v) AS node_id, v.version AS resolved_version, v.sortableVersion AS sortable
ORDER BY v.sortableVersion DESC
LIMIT 1
"""

_RESOLVE_CEIL = """
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion >= $sortable
RETURN elementId(v) AS node_id, v.version AS resolved_version, v.sortableVersion AS sortable
ORDER BY v.sortableVersion ASC
LIMIT 1
"""

_RESOLVE_CEIL_FALLBACK = """
MATCH (v:Version {framework: $framework})
RETURN elementId(v) AS node_id, v.version AS resolved_version, v.sortableVersion AS sortable
ORDER BY v.sortableVersion DESC
LIMIT 1
"""

_LIST_CANDIDATES = """
MATCH (v:Version {framework: $framework})
RETURN v.version AS version
ORDER BY v.sortableVersion DESC
LIMIT 10
"""

_STUB_MERGE = """
MERGE (v:Version {framework: $framework, version: $version})
ON CREATE SET
  v.sortableVersion = $sortable,
  v.status          = "stub",
  v.createdAt       = datetime()
RETURN elementId(v) AS node_id, v.version AS resolved_version, v.sortableVersion AS sortable
"""


def resolve_version(
    framework: str,
    version: str,
    mode: Literal["exact", "floor", "ceil"],
    *,
    allow_stub_create: bool = False,
) -> VersionResolutionResult | VersionResolutionFailure:
    """Resolve (framework, version) to a graph Version node.

    Modes:
      exact — must match exactly; returns NO_CANDIDATE if absent.
      floor — highest node with sortableVersion <= requested (lower-bound/current).
      ceil  — lowest node with sortableVersion >= requested (upper-bound/target).
              Falls back to highest known node + aheadOfCatalogue=True when nothing qualifies.

    Patch preservation: the caller-supplied patch segment is NEVER truncated.
    allow_stub_create: when True, a STUB Version node is created if no ceil candidate exists.
    """
    sv = sortable_version(version)

    if mode == "exact":
        with read_session() as session:
            row = session.run(_RESOLVE_EXACT, framework=framework, version=version).single()
        if row is None:
            with read_session() as session:
                candidates = [r["version"] for r in session.run(_LIST_CANDIDATES, framework=framework)]
            return VersionResolutionFailure(
                status="NO_CANDIDATE",
                framework=framework,
                requestedVersion=version,
                candidatesConsidered=candidates,
            )
        return VersionResolutionResult(
            resolvedVersion=row["resolved_version"],
            resolvedSortable=row["sortable"],
            nodeId=row["node_id"],
            requestedVersion=version,
            rounded=row["resolved_version"] != version,
            aheadOfCatalogue=False,
            stubCreated=False,
            direction=mode,
        )

    if mode == "floor":
        with read_session() as session:
            row = session.run(_RESOLVE_FLOOR, framework=framework, sortable=sv).single()
        if row is None:
            with read_session() as session:
                candidates = [r["version"] for r in session.run(_LIST_CANDIDATES, framework=framework)]
            return VersionResolutionFailure(
                status="NO_CANDIDATE",
                framework=framework,
                requestedVersion=version,
                candidatesConsidered=candidates,
            )
        return VersionResolutionResult(
            resolvedVersion=row["resolved_version"],
            resolvedSortable=row["sortable"],
            nodeId=row["node_id"],
            requestedVersion=version,
            rounded=row["resolved_version"] != version,
            aheadOfCatalogue=False,
            stubCreated=False,
            direction=mode,
        )

    # mode == "ceil"
    with read_session() as session:
        row = session.run(_RESOLVE_CEIL, framework=framework, sortable=sv).single()

    if row is not None:
        return VersionResolutionResult(
            resolvedVersion=row["resolved_version"],
            resolvedSortable=row["sortable"],
            nodeId=row["node_id"],
            requestedVersion=version,
            rounded=row["resolved_version"] != version,
            aheadOfCatalogue=False,
            stubCreated=False,
            direction=mode,
        )

    # No node >= sv — use highest available node (ahead-of-catalogue)
    with read_session() as session:
        fallback = session.run(_RESOLVE_CEIL_FALLBACK, framework=framework).single()

    if fallback is None:
        if allow_stub_create:
            with write_session() as session:
                stub = session.run(_STUB_MERGE, framework=framework, version=version, sortable=sv).single()
            return VersionResolutionResult(
                resolvedVersion=stub["resolved_version"],
                resolvedSortable=stub["sortable"],
                nodeId=stub["node_id"],
                requestedVersion=version,
                rounded=False,
                aheadOfCatalogue=False,
                stubCreated=True,
                direction=mode,
            )
        with read_session() as session:
            candidates = [r["version"] for r in session.run(_LIST_CANDIDATES, framework=framework)]
        return VersionResolutionFailure(
            status="NO_CANDIDATE",
            framework=framework,
            requestedVersion=version,
            candidatesConsidered=candidates,
        )

    if allow_stub_create:
        # Stub requested but we have a fallback — return the fallback with aheadOfCatalogue
        pass  # falls through to aheadOfCatalogue return

    return VersionResolutionResult(
        resolvedVersion=fallback["resolved_version"],
        resolvedSortable=fallback["sortable"],
        nodeId=fallback["node_id"],
        requestedVersion=version,
        rounded=True,
        aheadOfCatalogue=True,
        stubCreated=False,
        direction=mode,
    )


_ANALYZE_UPGRADE_PATH = """
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable
MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH v, rule,
     min(CASE bs.severity
           WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium'   THEN 2 WHEN 'low'  THEN 3 ELSE 4
         END) AS sev_rank,
     collect(DISTINCT {scope: bs.scope, severity: bs.severity}) AS scopes

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH v, rule, sev_rank, scopes, e,
     CASE
       WHEN e IS NULL THEN false
       WHEN e:Class THEN
            e.name IN $scanned_classes
         OR last(split(e.name, '.')) IN $scanned_class_simple
       WHEN e:ApplicationProperty THEN
            e.name IN $scanned_props
       WHEN e:Dependency THEN
            (size(split(e.name, ':')) >= 2
               AND (split(e.name, ':')[0] + ':' + split(e.name, ':')[1]) IN $scanned_deps_ga)
         OR last(split(e.name, ':')) IN $scanned_dep_artifacts
         OR (
              NOT (rule)-[:AFFECTS_CLASS]->(:Class)
              AND size(split(e.name, ':')) >= 2
              AND any(cls IN $scanned_classes WHERE
                cls STARTS WITH (split(e.name, ':')[0] + '.')
              )
            )
       ELSE false
     END AS entity_match

WITH v, rule, sev_rank, scopes,
     [x IN collect(DISTINCT CASE WHEN e IS NOT NULL THEN e.name ELSE null END) WHERE x IS NOT NULL] AS affected_entities,
     count(DISTINCT e)                                            AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END)               AS match_count

WITH v, rule, sev_rank, scopes, affected_entities, affected_count, match_count,
     CASE
       WHEN affected_count = 0     THEN 'informational'
       WHEN NOT $has_entity_filter THEN 'universal'
       WHEN match_count > 0        THEN 'matched'
       WHEN sev_rank <= 1          THEN 'uncertain'
       ELSE                             'excluded'
     END AS applicability

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

WITH v, rule, scopes, affected_entities, applicability, match_count, sev_rank, affected_count,
     collect(DISTINCT CASE WHEN s IS NULL THEN null ELSE {
       step_id: elementId(s),
       step_type: s.stepType,
       summary: s.summary,
       instruction: s.instruction,
       effort: s.effort,
       automatable: s.automatable,
       verification_hint: s.verificationHint,
       cli_operation: s.cliOperation
     } END) AS steps_raw,
     collect(DISTINCT CASE WHEN rec IS NULL THEN null ELSE {
       recipe_id: rec.recipeId,
       display_name: rec.displayName,
       step_id: elementId(s),
       auto: ab.auto,
       missing_required_params: coalesce(ab.missingRequiredParams, [])
     } END) AS recipes_raw

WITH v, collect(DISTINCT {
    rule_id:              coalesce(rule.ruleId, elementId(rule)),
    rule_type:            labels(rule)[0],
    title:                rule.title,
    statement:            rule.statement,
    action_step:          rule.actionStep,
    source_url:           rule.sourceUrl,
    reason:               coalesce(rule.statement, rule.reason),
    solution:             rule.solution,
    change_type:          rule.changeType,
    reason_type:          rule.reasonType,
    entity_classification: rule.entityClassification,
    affected_entities:    affected_entities,
    applicability:        applicability,
    match_count:          match_count,
    universally_applicable: (affected_count = 0),
    severity:             CASE sev_rank WHEN 0 THEN 'critical' WHEN 1 THEN 'high'
                                        WHEN 2 THEN 'medium'  WHEN 3 THEN 'low' ELSE null END,
    steps:    [x IN steps_raw   WHERE x IS NOT NULL],
    scopes:   [x IN scopes      WHERE x.scope IS NOT NULL],
    recipes:  [x IN recipes_raw WHERE x IS NOT NULL AND x.recipe_id IS NOT NULL]
}) AS raw_rules

OPTIONAL MATCH (v)-[:HAS_LIFECYCLE_ALERT]->(la:LifecycleAlert)

WITH v, raw_rules,
     collect(DISTINCT {message: la.message, category: la.category, phase: la.phase}) AS raw_alerts

RETURN
    v.version          AS release_version,
    v.sortableVersion  AS release_sortable,
    [x IN raw_rules WHERE x.statement IS NOT NULL] AS rules,
    [x IN raw_alerts  WHERE x.message  IS NOT NULL] AS raw_phase_alerts
ORDER BY v.sortableVersion ASC
"""

_BUILD_RECIPE_PLAN = """
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable
MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
WITH v, rule,
     min(CASE bs.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
           WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END) AS sev_rank,
     head(collect(DISTINCT bs.scope))    AS scope,
     head(collect(DISTINCT bs.severity)) AS severity

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH v, rule, sev_rank, scope, severity, e,
     CASE
       WHEN e IS NULL THEN false
       WHEN e:Class THEN
            e.name IN $scanned_classes
         OR last(split(e.name, '.')) IN $scanned_class_simple
       WHEN e:ApplicationProperty THEN e.name IN $scanned_props
       WHEN e:Dependency THEN
            (size(split(e.name, ':')) >= 2
               AND (split(e.name, ':')[0]+':'+split(e.name, ':')[1]) IN $scanned_deps_ga)
         OR last(split(e.name, ':')) IN $scanned_dep_artifacts
         // Package-prefix bridge: mirrored from _GET_PENDING_STEPS (context.py L148-162)
         OR any(cls IN $scanned_classes WHERE
              any(ruleClass IN [(rule)-[:AFFECTS_CLASS]->(rc:Class) | rc.name] WHERE
                cls STARTS WITH (left(ruleClass,
                  size(ruleClass) - size(split(ruleClass, '.')[size(split(ruleClass, '.'))-1]) - 1) + '.')
              )
            )
         OR (
              NOT (rule)-[:AFFECTS_CLASS]->(:Class)
              AND size(split(e.name, ':')) >= 2
              AND any(cls IN $scanned_classes WHERE
                cls STARTS WITH (split(e.name, ':')[0] + '.')
              )
            )
       ELSE false
     END AS entity_match

WITH v, rule, sev_rank, scope, severity,
     [x IN collect(DISTINCT CASE WHEN e IS NOT NULL THEN e.name ELSE null END) WHERE x IS NOT NULL] AS affected_entities,
     count(DISTINCT e) AS affected_count,
     sum(CASE WHEN entity_match THEN 1 ELSE 0 END) AS match_count

WITH v, rule, sev_rank, scope, severity, affected_entities, affected_count, match_count,
     CASE WHEN affected_count = 0     THEN 'informational'
          WHEN NOT $has_entity_filter THEN 'universal'
          WHEN match_count > 0        THEN 'matched'
          WHEN sev_rank <= 1          THEN 'uncertain'
          ELSE                             'excluded' END AS applicability
WHERE applicability <> 'excluded'

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

RETURN
    coalesce(rule.ruleId, elementId(rule))  AS rule_id,
    elementId(s)                            AS step_id,
    rule.statement                          AS statement,
    rule.actionStep                         AS action_step,
    s.summary                               AS summary,
    s.instruction                           AS instruction,
    s.effort                                AS effort,
    s.automatable                           AS automatable,
    s.verificationHint                      AS verification_hint,
    scope, severity, applicability, match_count, affected_entities,
    rec.recipeId                            AS recipe_id,
    ab.auto                                 AS auto,
    coalesce(ab.missingRequiredParams, [])  AS missing_required_params,
    v.version                               AS version,
    s.stepIndex                             AS step_index
ORDER BY v.sortableVersion ASC, s.stepIndex ASC
"""


_CHECK_VERSION_IN_GRAPH = """
MATCH (v:Version {framework: $framework, version: $version})
RETURN count(v) > 0 AS found
"""


def _clean_list(items: list[dict], key: str) -> list[dict]:
    return [item for item in items if item.get(key)]


def analyze_upgrade_path(
    *,
    framework: str,
    current_version: str,
    target_version: str,
    scanned_classes: list[str] | None = None,
    scanned_class_simple: list[str] | None = None,
    scanned_deps_ga: list[str] | None = None,
    scanned_dep_artifacts: list[str] | None = None,
    scanned_props: list[str] | None = None,
    has_entity_filter: bool = False,
    classification: list[str] | None = None,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> list[dict]:
    classes = classification or []
    scopes = scope_filter or []
    params = {
        "framework": framework,
        "current_version_sortable": sortable_version(current_version),
        "target_version_sortable": sortable_version(target_version),
        "scanned_classes": scanned_classes or [],
        "scanned_class_simple": scanned_class_simple or [],
        "scanned_deps_ga": scanned_deps_ga or [],
        "scanned_dep_artifacts": scanned_dep_artifacts or [],
        "scanned_props": scanned_props or [],
        "has_entity_filter": has_entity_filter,
        "classification": classes,
    }
    with read_session() as session:
        rows = list(session.run(_ANALYZE_UPGRADE_PATH, params))

    if not scopes and not min_severity:
        return [dict(row) for row in rows]

    filtered: list[dict] = []
    for row in rows:
        data = dict(row)
        rules = data.get("rules") or []
        kept_rules = []
        for rule in rules:
            rule_scopes = _clean_list(rule.get("scopes") or [], "scope")
            if filter_by_scope_and_severity(
                rule_scopes, scope_filter=scopes, min_severity=min_severity
            ):
                kept_rules.append(rule)
        if kept_rules:
            data["rules"] = kept_rules
            filtered.append(data)
    return filtered


def build_recipe_plan(
    *,
    framework: str,
    current_version: str,
    target_version: str,
    scanned_classes: list[str] | None = None,
    scanned_class_simple: list[str] | None = None,
    scanned_deps_ga: list[str] | None = None,
    scanned_dep_artifacts: list[str] | None = None,
    scanned_props: list[str] | None = None,
    has_entity_filter: bool = False,
    classification: list[str] | None = None,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> dict:
    classes = classification or []
    scopes = scope_filter or []
    params = {
        "framework": framework,
        "current_version_sortable": sortable_version(current_version),
        "target_version_sortable": sortable_version(target_version),
        "scanned_classes": scanned_classes or [],
        "scanned_class_simple": scanned_class_simple or [],
        "scanned_deps_ga": scanned_deps_ga or [],
        "scanned_dep_artifacts": scanned_dep_artifacts or [],
        "scanned_props": scanned_props or [],
        "has_entity_filter": has_entity_filter,
        "classification": classes,
    }
    _RECIPE_COUNT = "MATCH (r:OpenRewriteRecipe) RETURN count(r) AS c"
    with read_session() as session:
        recipe_count_row = session.run(_RECIPE_COUNT).single()
    recipe_count = recipe_count_row["c"] if recipe_count_row else 0

    with read_session() as session:
        rows = [dict(row) for row in session.run(_BUILD_RECIPE_PLAN, params)]

    auto_track: list[dict] = []
    manual_track: list[dict] = []
    has_steps = any(row.get("step_id") for row in rows)
    fallback_to_rule_cards = not has_steps

    from migration_oracle.mcp.matching import compute_matched_entities

    norm = {
        "scanned_classes": scanned_classes or [],
        "scanned_class_simple": scanned_class_simple or [],
        "scanned_deps_ga": scanned_deps_ga or [],
        "scanned_dep_artifacts": scanned_dep_artifacts or [],
        "scanned_props": scanned_props or [],
    }

    excluded_count = 0
    uncertain_count = 0
    seen_rule_ids: set[str] = set()
    seen_step_ids: set[str] = set()

    for row in rows:
        if scopes or min_severity:
            scope = row.get("scope")
            severity = row.get("severity")
            rule_scopes = [{"scope": scope, "severity": severity}] if scope else []
            if not filter_by_scope_and_severity(
                rule_scopes, scope_filter=scopes, min_severity=min_severity
            ):
                continue

        applicability = row.get("applicability") or "informational"
        if applicability == "uncertain":
            uncertain_count += 1

        matched_entities = compute_matched_entities(row, norm)

        step_id = row.get("step_id")
        rule_id = row.get("rule_id")
        if not has_steps:
            if rule_id in seen_rule_ids:
                continue
            seen_rule_ids.add(rule_id)
            action_step = row.get("action_step") or ""
            manual_track.append(
                {
                    "step_id": "",
                    "rule_id": rule_id,
                    "summary": row.get("statement") or "",
                    "instruction": action_step,
                    "verification_hint": "",
                    "effort": "",
                    "blocked_reason": "no_migration_steps",
                    "action_step": action_step,
                    "applicability": applicability,
                    "matched_entities": matched_entities,
                }
            )
            continue

        if not step_id:
            continue
        if step_id in seen_step_ids:
            continue
        seen_step_ids.add(step_id)

        auto_ok = (
            row.get("automatable") is True
            and row.get("effort") == "mechanical"
            and row.get("recipe_id")
            and row.get("auto") is True
            and not (row.get("missing_required_params") or [])
        )
        if auto_ok:
            auto_track.append(
                {
                    "step_id": step_id,
                    "rule_id": rule_id,
                    "summary": row.get("summary") or "",
                    "recipe_id": row.get("recipe_id") or "",
                    "rewrite_yml_fragment": "",
                    "applicability": applicability,
                    "matched_entities": matched_entities,
                }
            )
        else:
            manual_track.append(
                {
                    "step_id": step_id,
                    "rule_id": rule_id,
                    "summary": row.get("summary") or "",
                    "instruction": row.get("instruction") or "",
                    "verification_hint": row.get("verification_hint") or "",
                    "effort": row.get("effort") or "",
                    "blocked_reason": "",
                    "action_step": row.get("action_step") or "",
                    "applicability": applicability,
                    "matched_entities": matched_entities,
                }
            )

    total_included = len(auto_track) + len(manual_track)
    return {
        "auto_track": auto_track,
        "manual_track": manual_track,
        "fallback_to_rule_cards": fallback_to_rule_cards,
        "rules_included": total_included,
        "excluded_count": excluded_count,
        "uncertain_count": uncertain_count,
        "recipes_loaded": recipe_count > 0,
        "recipe_count": recipe_count,
    }

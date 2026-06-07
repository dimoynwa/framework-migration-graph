"""Upgrade path and recipe plan Cypher queries."""

from __future__ import annotations

from migration_oracle.graph.driver import read_session
from migration_oracle.mcp.graph.queries._severity import filter_by_scope_and_severity
from migration_oracle.models.graph import sortable_version

_ANALYZE_UPGRADE_PATH = """
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable

OPTIONAL MATCH (e_lc)-[rel:DEPRECATED_IN|REMOVED_IN|INTRODUCED_IN]->(v)
WHERE size($user_entities) = 0
   OR ANY(u IN $user_entities WHERE toLower(e_lc.name) CONTAINS toLower(u))

WITH v, collect(DISTINCT {
    event_type: type(rel),
    entity_type: labels(e_lc)[0],
    entity_name: e_lc.name
}) AS raw_lifecycle_events

OPTIONAL MATCH (v)-[:INCLUDES_RULE|DISCOVERED_IN]-(rule)
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)

WITH v, raw_lifecycle_events, rule,
     collect(DISTINCT ruleEntity.name) AS affected_entities

WHERE rule IS NULL
   OR (
       (size($user_entities) = 0
          OR ANY(e IN affected_entities
                   WHERE ANY(u IN $user_entities
                              WHERE toLower(e) CONTAINS toLower(u))))
       AND
       (rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

WITH v, raw_lifecycle_events, rule, affected_entities,
     collect(DISTINCT {
         step_id: elementId(s),
         step_type: s.stepType,
         summary: s.summary,
         instruction: s.instruction,
         effort: s.effort,
         automatable: s.automatable,
         verification_hint: s.verificationHint,
         cli_operation: s.cliOperation
     }) AS steps,
     collect(DISTINCT {
         scope: bs.scope,
         severity: bs.severity
     }) AS scopes,
     collect(DISTINCT {
         recipe_id: rec.recipeId,
         display_name: rec.displayName,
         auto: ab.auto,
         missing_required_params: coalesce(ab.missingRequiredParams, [])
     }) AS recipes

WITH v, raw_lifecycle_events, collect(DISTINCT {
    rule_id: elementId(rule),
    rule_type: labels(rule)[0],
    statement: rule.statement,
    action_step: rule.actionStep,
    source_url: rule.sourceUrl,
    reason: rule.reason,
    solution: rule.solution,
    change_type: rule.changeType,
    reason_type: rule.reasonType,
    entity_classification: rule.entityClassification,
    affected_entities: affected_entities,
    steps: [x IN steps WHERE x.step_id IS NOT NULL],
    scopes: [x IN scopes WHERE x.scope IS NOT NULL],
    recipes: [x IN recipes WHERE x.recipe_id IS NOT NULL]
}) AS raw_rules

RETURN
    v.version AS release_version,
    v.sortableVersion AS release_sortable,
    [x IN raw_rules WHERE x.statement IS NOT NULL] AS rules,
    [x IN raw_lifecycle_events WHERE x.event_type IS NOT NULL] AS lifecycle_events
ORDER BY v.sortableVersion ASC
"""

_BUILD_RECIPE_PLAN = """
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion > $current_version_sortable
  AND v.sortableVersion <= $target_version_sortable

MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
WHERE rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)
WITH v, rule, collect(DISTINCT ruleEntity.name) AS affected_entities
WHERE size($user_entities) = 0
   OR ANY(e IN affected_entities
            WHERE ANY(u IN $user_entities
                       WHERE toLower(e) CONTAINS toLower(u)))

OPTIONAL MATCH (rule)-[:REQUIRES_STEP]->(s:MigrationStep)
OPTIONAL MATCH (rule)-[:HAS_SCOPE]->(bs:BreakingScope)
OPTIONAL MATCH (s)-[ab_s:AUTOMATED_BY]->(rec_s:OpenRewriteRecipe)

WITH v, rule, affected_entities, s, bs, ab_s, rec_s,
     elementId(rule) AS rule_id,
     elementId(s) AS step_id

RETURN
    rule_id,
    step_id,
    rule.statement AS statement,
    rule.actionStep AS action_step,
    s.summary AS summary,
    s.instruction AS instruction,
    s.effort AS effort,
    s.automatable AS automatable,
    s.verificationHint AS verification_hint,
    bs.scope AS scope,
    bs.severity AS severity,
    rec_s.recipeId AS recipe_id,
    ab_s.auto AS auto,
    coalesce(ab_s.missingRequiredParams, []) AS missing_required_params,
    v.version AS version
ORDER BY v.sortableVersion ASC, s.stepIndex ASC
"""


def _clean_list(items: list[dict], key: str) -> list[dict]:
    return [item for item in items if item.get(key)]


def analyze_upgrade_path(
    *,
    framework: str,
    current_version: str,
    target_version: str,
    user_entities: list[str] | None = None,
    classification: list[str] | None = None,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> list[dict]:
    entities = user_entities or []
    classes = classification or ["actionable", "incomplete"]
    scopes = scope_filter or []
    params = {
        "framework": framework,
        "current_version_sortable": sortable_version(current_version),
        "target_version_sortable": sortable_version(target_version),
        "user_entities": entities,
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
    user_entities: list[str] | None = None,
    classification: list[str] | None = None,
    scope_filter: list[str] | None = None,
    min_severity: str | None = None,
) -> dict:
    entities = user_entities or []
    classes = classification or ["actionable", "incomplete"]
    scopes = scope_filter or []
    params = {
        "framework": framework,
        "current_version_sortable": sortable_version(current_version),
        "target_version_sortable": sortable_version(target_version),
        "user_entities": entities,
        "classification": classes,
    }
    with read_session() as session:
        rows = [dict(row) for row in session.run(_BUILD_RECIPE_PLAN, params)]

    auto_track: list[dict] = []
    manual_track: list[dict] = []
    has_steps = any(row.get("step_id") for row in rows)
    fallback_to_rule_cards = not has_steps

    seen_rule_ids: set[str] = set()
    for row in rows:
        if scopes or min_severity:
            scope = row.get("scope")
            severity = row.get("severity")
            rule_scopes = [{"scope": scope, "severity": severity}] if scope else []
            if not filter_by_scope_and_severity(
                rule_scopes, scope_filter=scopes, min_severity=min_severity
            ):
                continue

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
                }
            )
            continue

        if not step_id:
            continue

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
                }
            )

    return {
        "auto_track": auto_track,
        "manual_track": manual_track,
        "fallback_to_rule_cards": fallback_to_rule_cards,
    }

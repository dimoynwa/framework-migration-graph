#!/usr/bin/env python3
"""
Comprehensive live Cypher query tester against Neo4j.
Tests every query found in migration_oracle source code.
"""

import sys
import traceback
from datetime import datetime

from neo4j import GraphDatabase
from neo4j.exceptions import ClientError, CypherSyntaxError, DatabaseError

URI      = "bolt://localhost:7687"
USER     = "neo4j"
PASSWORD = "password123"

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

results = []   # list of (query_id, label, status, detail)


def run(session, query, params=None, label=""):
    """Run a Cypher query, return (rows, None) or (None, error_str)."""
    try:
        rows = list(session.run(query, **(params or {})))
        return rows, None
    except (ClientError, CypherSyntaxError, DatabaseError, Exception) as exc:
        return None, str(exc)


def record(qid, label, status, detail=""):
    tag = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ "}.get(status, "  ")
    print(f"  {tag} [{qid}] {label}: {detail[:120]}")
    results.append((qid, label, status, detail))


print("=" * 70)
print("Cypher Query Live Test")
print(f"Neo4j: {URI}")
print(f"Date:  {datetime.now().isoformat(timespec='seconds')}")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# Step 0 — Discover available data so we can use real params
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Step 0: Discover graph state ──")
with driver.session() as s:
    rows, err = run(s, "MATCH (v:Version) RETURN v.framework AS f, v.version AS ver, v.sortableVersion AS sv ORDER BY f, sv")
    if err:
        print(f"  FATAL: cannot reach graph — {err}")
        sys.exit(1)
    versions = [(r["f"], r["ver"], r["sv"]) for r in rows]
    print(f"  Versions in graph: {len(versions)}")
    for fw, ver, sv in versions:
        print(f"    {fw} {ver} (sortable={sv})")

    rows2, _ = run(s, "MATCH (r:MigrationRule) RETURN count(r) AS cnt")
    rule_count = rows2[0]["cnt"] if rows2 else 0
    print(f"  MigrationRule count: {rule_count}")

    rows3, _ = run(s, "MATCH (r:OpenRewriteRecipe) RETURN count(r) AS cnt")
    recipe_count = rows3[0]["cnt"] if rows3 else 0
    print(f"  OpenRewriteRecipe count: {recipe_count}")

    rows4, _ = run(s, "MATCH (c:Class) RETURN count(c) AS cnt")
    class_count = rows4[0]["cnt"] if rows4 else 0
    print(f"  Class count: {class_count}")

# Pick test params from real data
if not versions:
    print("  FATAL: no Version nodes in graph — populate graph first")
    sys.exit(1)

# Find a Spring Boot pair if available
sb_versions = [(fw, ver, sv) for fw, ver, sv in versions if fw and "Spring" in fw]
if len(sb_versions) >= 2:
    FRAMEWORK     = sb_versions[0][0]
    FROM_VER      = sb_versions[0][1]
    FROM_SORT     = sb_versions[0][2]
    TO_VER        = sb_versions[-1][1]
    TO_SORT       = sb_versions[-1][2]
elif versions:
    FRAMEWORK     = versions[0][0] or "Spring Boot"
    FROM_VER      = versions[0][1]
    FROM_SORT     = versions[0][2]
    TO_VER        = versions[-1][1]
    TO_SORT       = versions[-1][2]
else:
    FRAMEWORK, FROM_VER, FROM_SORT, TO_VER, TO_SORT = "Spring Boot", "3.5.0", 30500, "4.0.0", 40000

print(f"\n  Using: {FRAMEWORK}  {FROM_VER} → {TO_VER}  (sortable {FROM_SORT} → {TO_SORT})\n")

# ─────────────────────────────────────────────────────────────────────────────
# Q1 — artifacts.py: _LIST_PIPELINE_RUNS
# ─────────────────────────────────────────────────────────────────────────────
print("── artifacts.py ──")
with driver.session() as s:
    q = """
    MATCH (v:Version) WHERE v.rawMdPath IS NOT NULL
    RETURN v.framework AS framework,
           v.version AS version,
           v.fromVersion AS from_version,
           v.rawMdPath AS raw_md_path,
           v.filteredMdPath AS filtered_md_path,
           v.entitiesJsonPath AS entities_json_path
    ORDER BY v.framework, v.sortableVersion
    """
    rows, err = run(s, q)
    if err:
        record("Q1", "_LIST_PIPELINE_RUNS", "FAIL", err)
    else:
        record("Q1", "_LIST_PIPELINE_RUNS", "PASS", f"{len(rows)} rows")

with driver.session() as s:
    q = """
    MATCH (v:Version {framework: $framework, version: $to_version})
    RETURN v.rawMdPath AS rawMdPath,
           v.filteredMdPath AS filteredMdPath,
           v.entitiesJsonPath AS entitiesJsonPath
    """
    rows, err = run(s, q, {"framework": FRAMEWORK, "to_version": TO_VER})
    if err:
        record("Q2", "_GET_VERSION_ARTIFACT_PATH", "FAIL", err)
    else:
        record("Q2", "_GET_VERSION_ARTIFACT_PATH", "PASS", f"{len(rows)} rows")

# ─────────────────────────────────────────────────────────────────────────────
# Q3-Q4 — deprecation.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n── deprecation.py ──")
TEST_ENTITY = "EnvironmentPostProcessor"

with driver.session() as s:
    q = """
    MATCH (e)
    WHERE (e:Class OR e:ApplicationProperty OR e:Dependency) AND e.name = $entity_name
    OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
    OPTIONAL MATCH (e)-[:REMOVED_IN]->(remV:Version {framework: $framework})
    OPTIONAL MATCH (e)-[:REPLACED_BY]->(replacement)
    OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
    WHERE rule:MigrationRule
      AND EXISTS { (rule)-[:INCLUDES_RULE|DISCOVERED_IN]-(:Version {framework: $framework}) }
    WITH e, depV, remV, replacement,
         collect({
           type: labels(rule)[0],
           statement: rule.statement,
           reason: rule.reason,
           solution: rule.solution,
           action_step: rule.actionStep
         }) AS rules
    OPTIONAL MATCH (introV:Version {framework: $framework})-[:INTRODUCES]->(e)
    OPTIONAL MATCH (removedByV:Version {framework: $framework})-[:REMOVES]->(e)
    RETURN
      labels(e)[0] AS entity_type,
      e.name AS entity_name,
      replacement.name AS replaced_by,
      coalesce(depV.version, introV.version) AS deprecated_in,
      coalesce(remV.version, removedByV.version) AS removed_in,
      rules
    """
    rows, err = run(s, q, {"entity_name": TEST_ENTITY, "framework": FRAMEWORK})
    if err:
        record("Q3", "_RESOLVE_DEPRECATION", "FAIL", err)
    else:
        record("Q3", "_RESOLVE_DEPRECATION", "PASS", f"{len(rows)} rows (entity={'found' if rows else 'not_found'})")

with driver.session() as s:
    q = """
    MATCH (start)
    WHERE (start:Class OR start:ApplicationProperty OR start:Dependency)
      AND start.name = $entity_name
    MATCH path = (start)-[:REPLACED_BY*0..5]->(end)
    WHERE NOT (end)-[:REPLACED_BY]->()
    WITH nodes(path) AS lineage_nodes
    UNWIND lineage_nodes AS e
    OPTIONAL MATCH (e)-[:INTRODUCED_IN]->(introV:Version {framework: $framework})
    OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
    OPTIONAL MATCH (e)-[:REMOVED_IN]->(remV:Version {framework: $framework})
    OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
    WHERE rule:MigrationRule
    RETURN
      labels(e)[0] AS entity_type,
      e.name AS entity_name,
      introV.version AS introduced,
      depV.version AS deprecated,
      remV.version AS removed,
      collect(DISTINCT {
          type: labels(rule)[0],
          statement: rule.statement,
          action: coalesce(rule.actionStep, rule.solution)
      }) AS rules
    """
    rows, err = run(s, q, {"entity_name": TEST_ENTITY, "framework": FRAMEWORK})
    if err:
        record("Q4", "_ENTITY_EVOLUTION", "FAIL", err)
    else:
        record("Q4", "_ENTITY_EVOLUTION", "PASS", f"{len(rows)} rows")

# ─────────────────────────────────────────────────────────────────────────────
# Q5 — community.py: _FIND_EXACT_STATEMENT
# ─────────────────────────────────────────────────────────────────────────────
print("\n── community.py ──")
with driver.session() as s:
    q = """
    MATCH (r:MigrationRule)
    WHERE r.statement = $statement AND r.ruleType = 'community_insight'
    RETURN elementId(r) AS insight_id
    LIMIT 1
    """
    rows, err = run(s, q, {"statement": "test statement"})
    if err:
        record("Q5", "_FIND_EXACT_STATEMENT", "FAIL", err)
    else:
        record("Q5", "_FIND_EXACT_STATEMENT", "PASS", f"{len(rows)} rows")

with driver.session() as s:
    q = """
    MATCH (r:MigrationRule)
    WHERE r.ruleType = 'community_insight'
    RETURN elementId(r) AS insight_id
    LIMIT 1
    """
    rows, err = run(s, q)
    sample_insight_id = rows[0]["insight_id"] if rows else None

if sample_insight_id:
    with driver.session() as s:
        q = """
        MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
        RETURN r.embedding AS embedding
        """
        rows, err = run(s, q, {"insight_id": sample_insight_id})
        if err:
            record("Q6", "_FETCH_EMBEDDING", "FAIL", err)
        else:
            record("Q6", "_FETCH_EMBEDDING", "PASS", f"{len(rows)} rows")
else:
    record("Q6", "_FETCH_EMBEDDING", "WARN", "no community_insight nodes to test against")

# Q7 — _QUERY_INSIGHTS
with driver.session() as s:
    q = """
    MATCH (v:Version {framework: $framework})-[:INCLUDES_RULE]->(r:MigrationRule)
    WHERE r.ruleType = 'community_insight'
      AND ($from_sortable IS NULL OR v.sortableVersion >= $from_sortable)
      AND ($to_sortable IS NULL OR v.sortableVersion <= $to_sortable)
      AND ($verified_only = false OR r.communityVerified = true)
    OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
    WITH r, v, collect(DISTINCT e.name) AS affected_entities
    WHERE $entity_name IS NULL
       OR ANY(name IN affected_entities WHERE name = $entity_name)
    OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
    WITH r, v, affected_entities, s
    ORDER BY s.stepIndex ASC
    WITH r, v, affected_entities, collect(s)[0] AS first_step
    RETURN elementId(r)                          AS insight_id,
           r.statement                            AS statement,
           coalesce(first_step.instruction, '')   AS solution,
           r.sourceUrl                            AS source_url,
           r.communitySubmittedBy                 AS submitted_by,
           r.communityCreatedAt                   AS created_at,
           r.communityConfidence                  AS confidence,
           r.communityVotes                       AS votes,
           r.communityVerified                    AS verified,
           v.version                              AS version,
           affected_entities
    ORDER BY r.communityVotes DESC, r.communityCreatedAt DESC
    """
    rows, err = run(s, q, {
        "framework": FRAMEWORK,
        "from_sortable": None,
        "to_sortable": None,
        "entity_name": None,
        "verified_only": False,
    })
    if err:
        record("Q7", "_QUERY_INSIGHTS", "FAIL", err)
    else:
        record("Q7", "_QUERY_INSIGHTS", "PASS", f"{len(rows)} rows")

# Q8 — _VOTE_INSIGHT (read-only probe — skip write)
with driver.session() as s:
    # Just validate syntax via EXPLAIN
    q = """
    MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
    SET r.communityVotes = coalesce(r.communityVotes, 0) + $delta
    RETURN elementId(r) AS insight_id, r.communityVotes AS votes
    """
    try:
        s.run("EXPLAIN " + q, insight_id="fake-id", delta=1).consume()
        record("Q8", "_VOTE_INSIGHT (syntax)", "PASS", "EXPLAIN OK")
    except Exception as exc:
        record("Q8", "_VOTE_INSIGHT (syntax)", "FAIL", str(exc))

# Q9 — _VERIFY_INSIGHT (syntax only)
with driver.session() as s:
    q = """
    MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
    SET r.communityVerified = true
    RETURN elementId(r) AS insight_id, r.communityVerified AS verified
    """
    try:
        s.run("EXPLAIN " + q, insight_id="fake-id").consume()
        record("Q9", "_VERIFY_INSIGHT (syntax)", "PASS", "EXPLAIN OK")
    except Exception as exc:
        record("Q9", "_VERIFY_INSIGHT (syntax)", "FAIL", str(exc))

# ─────────────────────────────────────────────────────────────────────────────
# Q10-Q11 — search.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n── search.py ──")
with driver.session() as s:
    q = """
    CALL db.index.fulltext.queryNodes($index, $search_text, {limit: $top_k})
    YIELD node, score
    RETURN elementId(node) AS id
    ORDER BY score DESC
    LIMIT $top_k
    """
    rows, err = run(s, q, {"index": "rule_statement", "search_text": "spring boot", "top_k": 5})
    if err:
        record("Q10", "bm25_search (rule_statement)", "FAIL", err)
    else:
        record("Q10", "bm25_search (rule_statement)", "PASS", f"{len(rows)} hits")

with driver.session() as s:
    rows, err = run(s, q, {"index": "migration_text", "search_text": "deprecated", "top_k": 5})
    if err:
        record("Q10b", "bm25_search (migration_text)", "FAIL", err)
    else:
        record("Q10b", "bm25_search (migration_text)", "PASS", f"{len(rows)} hits")

with driver.session() as s:
    rows, err = run(s, q, {"index": "openrewrite_recipe_description", "search_text": "upgrade", "top_k": 5})
    if err:
        record("Q10c", "bm25_search (openrewrite_recipe_description)", "FAIL", err)
    else:
        record("Q10c", "bm25_search (openrewrite_recipe_description)", "PASS", f"{len(rows)} hits")

# hydrate_nodes
with driver.session() as s:
    q = """
    MATCH (n) WHERE elementId(n) IN $ids
    OPTIONAL MATCH (n)-[:INCLUDES_RULE]-(v:Version)
    WHERE $framework IS NULL OR v.framework = $framework
    WITH n, collect(DISTINCT v.version) AS versions
    WHERE ($framework IS NULL OR size(versions) > 0)
    OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)
    WITH n, versions, collect(s)[0] AS first_step
    RETURN elementId(n) AS node_id,
           labels(n)[0] AS node_type,
           n.statement AS statement,
           n.reason AS reason,
           coalesce(n.solution, first_step.instruction) AS solution,
           n.actionStep AS action_step,
           n.ruleType AS rule_type,
           n.sourceUrl AS source_url,
           n.description AS description,
           n.recipeId AS recipe_id,
           n.displayName AS display_name,
           versions
    """
    rows, err = run(s, q, {"ids": [], "framework": FRAMEWORK})
    if err:
        record("Q11", "hydrate_nodes", "FAIL", err)
    else:
        record("Q11", "hydrate_nodes", "PASS", f"{len(rows)} rows (empty ids)")

# hydrate_openrewrite_recipes
with driver.session() as s:
    q = """
    MATCH (r:OpenRewriteRecipe) WHERE elementId(r) IN $ids
    RETURN elementId(r) AS node_id,
           r.recipeId AS recipe_id,
           r.displayName AS display_name,
           r.description AS description,
           r.artifactId AS artifact_id,
           r.groupId AS group_id,
           r.artifactVersion AS artifact_version,
           coalesce(r.composite, false) AS is_composite,
           coalesce(r.tags, []) AS tags
    """
    rows, err = run(s, q, {"ids": []})
    if err:
        record("Q12", "hydrate_openrewrite_recipes", "FAIL", err)
    else:
        record("Q12", "hydrate_openrewrite_recipes", "PASS", f"{len(rows)} rows (empty ids)")

# hydrate_openrewrite_recipes with composite filter
with driver.session() as s:
    q = """
    MATCH (r:OpenRewriteRecipe) WHERE elementId(r) IN $ids
      AND coalesce(r.composite, false) = true
      AND NOT EXISTS { MATCH (r)-[:HAS_PARAM]->(p:RecipeParam) WHERE p.required = true }
    RETURN elementId(r) AS node_id,
           r.recipeId AS recipe_id,
           r.displayName AS display_name,
           r.description AS description,
           r.artifactId AS artifact_id,
           r.groupId AS group_id,
           r.artifactVersion AS artifact_version,
           coalesce(r.composite, false) AS is_composite,
           coalesce(r.tags, []) AS tags
    """
    rows, err = run(s, q, {"ids": []})
    if err:
        record("Q12b", "hydrate_openrewrite_recipes (composite+no_params filter)", "FAIL", err)
    else:
        record("Q12b", "hydrate_openrewrite_recipes (composite+no_params filter)", "PASS", "EXPLAIN OK")

# ─────────────────────────────────────────────────────────────────────────────
# Q13-Q14 — upgrade.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n── upgrade.py ──")
with driver.session() as s:
    q = """
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
        rule_id:              elementId(rule),
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
    params = {
        "framework": FRAMEWORK,
        "current_version_sortable": FROM_SORT,
        "target_version_sortable": TO_SORT,
        "scanned_classes": [],
        "scanned_class_simple": [],
        "scanned_deps_ga": [],
        "scanned_dep_artifacts": [],
        "scanned_props": [],
        "has_entity_filter": False,
        "classification": [],
    }
    rows, err = run(s, q, params)
    if err:
        record("Q13", "_ANALYZE_UPGRADE_PATH", "FAIL", err)
    else:
        total_rules = sum(len(r["rules"] or []) for r in rows)
        record("Q13", "_ANALYZE_UPGRADE_PATH", "PASS" if total_rules > 0 else "WARN",
               f"{len(rows)} version rows, {total_rules} rules total")

with driver.session() as s:
    q = """
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
        elementId(rule)                         AS rule_id,
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
    rows, err = run(s, q, params)
    if err:
        record("Q14", "_BUILD_RECIPE_PLAN", "FAIL", err)
    else:
        record("Q14", "_BUILD_RECIPE_PLAN", "PASS" if rows else "WARN",
               f"{len(rows)} step rows")

with driver.session() as s:
    q = """
    MATCH (v:Version {framework: $framework, version: $version})
    RETURN count(v) > 0 AS found
    """
    rows, err = run(s, q, {"framework": FRAMEWORK, "version": TO_VER})
    if err:
        record("Q15", "_CHECK_VERSION_IN_GRAPH", "FAIL", err)
    else:
        found = rows[0]["found"] if rows else False
        record("Q15", "_CHECK_VERSION_IN_GRAPH", "PASS" if found else "WARN",
               f"found={found}")

# ─────────────────────────────────────────────────────────────────────────────
# Q16-Q22 — context.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n── context.py ──")

# _CREATE_OR_GET_CONTEXT (syntax check via EXPLAIN — it's a write, we don't execute)
with driver.session() as s:
    q = """
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
      ctx._was_created = true,
      ctx.scannedClasses       = $scanned_classes,
      ctx.scannedClassSimple   = $scanned_class_simple,
      ctx.scannedDepsGa        = $scanned_deps_ga,
      ctx.scannedDepArtifacts  = $scanned_dep_artifacts,
      ctx.scannedProps         = $scanned_props
    ON MATCH SET
      ctx._was_created = false,
      ctx.scannedClasses       = $scanned_classes,
      ctx.scannedClassSimple   = $scanned_class_simple,
      ctx.scannedDepsGa        = $scanned_deps_ga,
      ctx.scannedDepArtifacts  = $scanned_dep_artifacts,
      ctx.scannedProps         = $scanned_props
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
    try:
        s.run("EXPLAIN " + q,
              project_id="test", from_version=FROM_VER, to_version=TO_VER,
              framework=FRAMEWORK, scanned_entities=[],
              scanned_classes=[], scanned_class_simple=[],
              scanned_deps_ga=[], scanned_dep_artifacts=[], scanned_props=[]).consume()
        record("Q16", "_CREATE_OR_GET_CONTEXT (syntax)", "PASS", "EXPLAIN OK")
    except Exception as exc:
        record("Q16", "_CREATE_OR_GET_CONTEXT (syntax)", "FAIL", str(exc))

# Create a real context for testing downstream queries
CTX_ID = None
try:
    with driver.session() as s:
        ctx_q = """
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
          ctx._was_created = true,
          ctx.scannedClasses       = $scanned_classes,
          ctx.scannedClassSimple   = $scanned_class_simple,
          ctx.scannedDepsGa        = $scanned_deps_ga,
          ctx.scannedDepArtifacts  = $scanned_dep_artifacts,
          ctx.scannedProps         = $scanned_props
        ON MATCH SET
          ctx._was_created = false,
          ctx.scannedClasses       = $scanned_classes,
          ctx.scannedClassSimple   = $scanned_class_simple,
          ctx.scannedDepsGa        = $scanned_deps_ga,
          ctx.scannedDepArtifacts  = $scanned_dep_artifacts,
          ctx.scannedProps         = $scanned_props
        WITH ctx
        MATCH (vf:Version {framework: $framework, version: $from_version})
        MATCH (vt:Version {framework: $framework, version: $to_version})
        MERGE (ctx)-[:UPGRADES_FROM]->(vf)
        MERGE (ctx)-[:UPGRADES_TO]->(vt)
        RETURN elementId(ctx) AS context_id,
               coalesce(ctx._was_created, false) AS created
        """
        rec_row = s.run(ctx_q,
            project_id="__cypher_test__",
            from_version=FROM_VER,
            to_version=TO_VER,
            framework=FRAMEWORK,
            scanned_entities=[],
            scanned_classes=[], scanned_class_simple=[],
            scanned_deps_ga=[], scanned_dep_artifacts=[], scanned_props=[],
        ).single()
        if rec_row:
            CTX_ID = rec_row["context_id"]
            created = rec_row["created"]
            print(f"  [setup] MigrationContext created={created}, id={CTX_ID}")
        else:
            print("  [setup] WARNING: could not create MigrationContext (version not in graph?)")
except Exception as exc:
    print(f"  [setup] MigrationContext creation error: {exc}")

# _GET_PENDING_STEPS
if CTX_ID:
    with driver.session() as s:
        q = """
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
             (size(coalesce(ctx.scannedClasses, [])) > 0
               OR size(coalesce(ctx.scannedClassSimple, [])) > 0
               OR size(coalesce(ctx.scannedDepsGa, [])) > 0
               OR size(coalesce(ctx.scannedDepArtifacts, [])) > 0
               OR size(coalesce(ctx.scannedProps, [])) > 0) AS has_filter

        OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
        WITH r, s, sev_rank, scope, severity, sc_c, sc_cs, sc_dga, sc_da, sc_p, has_filter, e,
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
               ELSE false
             END AS entity_match

        WITH r, s, sev_rank, scope, severity, has_filter,
             count(DISTINCT e)                             AS affected_count,
             sum(CASE WHEN entity_match THEN 1 ELSE 0 END) AS match_count

        WITH r, s, sev_rank, scope, severity,
             CASE WHEN affected_count = 0 THEN 'informational'
                  WHEN NOT has_filter     THEN 'universal'
                  WHEN match_count > 0    THEN 'matched'
                  WHEN sev_rank <= 1      THEN 'uncertain'
                  ELSE                         'excluded' END AS applicability
        WHERE applicability <> 'excluded'

        OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
          WHERE ab.auto = true AND coalesce(ab.missingRequiredParams, []) = []
        OPTIONAL MATCH (s)-[:REQUIRES]->(prereq:MigrationStep)
        RETURN elementId(s) AS step_id,
               s.stepType    AS step_type,
               elementId(r)  AS rule_id,
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
        rows, err = run(s, q, {"context_id": CTX_ID, "effort_filter": [], "scope_filter": []})
        if err:
            record("Q17", "_GET_PENDING_STEPS", "FAIL", err)
        else:
            record("Q17", "_GET_PENDING_STEPS", "PASS", f"{len(rows)} steps")
else:
    record("Q17", "_GET_PENDING_STEPS", "WARN", "skipped — no MigrationContext available")

# _RECORD_STEP_OUTCOME (syntax only)
with driver.session() as s:
    q = """
    MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
    SET ctx.completedSteps = CASE $outcome WHEN 'completed'
        THEN ctx.completedSteps + [$step_id] ELSE ctx.completedSteps END,
        ctx.skippedSteps = CASE $outcome WHEN 'skipped'
        THEN ctx.skippedSteps + [$step_id] ELSE ctx.skippedSteps END,
        ctx.failedSteps = CASE $outcome WHEN 'failed'
        THEN coalesce(ctx.failedSteps, []) + [$step_id] ELSE coalesce(ctx.failedSteps, []) END
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
    try:
        s.run("EXPLAIN " + q,
              context_id="fake", step_id="fake", outcome="completed", reason="").consume()
        record("Q18", "_RECORD_STEP_OUTCOME (syntax)", "PASS", "EXPLAIN OK")
    except Exception as exc:
        record("Q18", "_RECORD_STEP_OUTCOME (syntax)", "FAIL", str(exc))

# _AUTO_CLOSE_WRITE (syntax only)
with driver.session() as s:
    q = """
    MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $context_id
    SET ctx.status = 'complete', ctx.completedAt = datetime()
    RETURN elementId(ctx) AS context_id, ctx.status AS migration_status
    """
    try:
        s.run("EXPLAIN " + q, context_id="fake").consume()
        record("Q19", "_AUTO_CLOSE_WRITE (syntax)", "PASS", "EXPLAIN OK")
    except Exception as exc:
        record("Q19", "_AUTO_CLOSE_WRITE (syntax)", "FAIL", str(exc))

# _GET_STEPS_FOR_SCOPE_TIER
if CTX_ID:
    with driver.session() as s:
        q = """
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
        rows, err = run(s, q, {"context_id": CTX_ID, "scope": "api"})
        if err:
            record("Q20", "_GET_STEPS_FOR_SCOPE_TIER", "FAIL", err)
        else:
            record("Q20", "_GET_STEPS_FOR_SCOPE_TIER", "PASS", f"{len(rows)} rows")
else:
    record("Q20", "_GET_STEPS_FOR_SCOPE_TIER", "WARN", "skipped — no MigrationContext available")

# _CLOSE_CONTEXT (syntax only — keep context alive for teardown)
with driver.session() as s:
    q = """
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
    try:
        s.run("EXPLAIN " + q, context_id="fake", final_status="partial", notes="").consume()
        record("Q21", "_CLOSE_CONTEXT (syntax)", "PASS", "EXPLAIN OK")
    except Exception as exc:
        record("Q21", "_CLOSE_CONTEXT (syntax)", "FAIL", str(exc))

# _GET_QUERIED_ENTITIES / _SET_QUERIED_ENTITIES (syntax only)
with driver.session() as s:
    for qid, label, q in [
        ("Q22a", "_GET_QUERIED_ENTITIES (syntax)",
         "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id RETURN ctx.queriedEntities AS qe"),
        ("Q22b", "_SET_QUERIED_ENTITIES (syntax)",
         "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id SET ctx.queriedEntities = $updated_json RETURN 1"),
    ]:
        try:
            s.run("EXPLAIN " + q, id="fake", updated_json="{}").consume()
            record(qid, label, "PASS", "EXPLAIN OK")
        except Exception as exc:
            record(qid, label, "FAIL", str(exc))

# delete_zombie_context (syntax only)
with driver.session() as s:
    q = """
    MATCH (ctx:MigrationContext {
      projectId: $project_id,
      fromVersion: $from_version,
      toVersion: $to_version
    })
    DELETE ctx
    """
    try:
        s.run("EXPLAIN " + q,
              project_id="fake", from_version=FROM_VER, to_version=TO_VER).consume()
        record("Q23", "delete_zombie_context (syntax)", "PASS", "EXPLAIN OK")
    except Exception as exc:
        record("Q23", "delete_zombie_context (syntax)", "FAIL", str(exc))

# ─────────────────────────────────────────────────────────────────────────────
# Q24 — indexes.py: all DDL statements (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
print("\n── indexes.py (DDL) ──")
ddl_statements = [
    "CREATE CONSTRAINT version_unique IF NOT EXISTS FOR (v:Version) REQUIRE (v.framework, v.version) IS UNIQUE",
    "CREATE CONSTRAINT migration_rule_id IF NOT EXISTS FOR (r:MigrationRule) REQUIRE r.ruleId IS UNIQUE",
    "CREATE CONSTRAINT class_name IF NOT EXISTS FOR (c:Class) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT property_name IF NOT EXISTS FOR (p:ApplicationProperty) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT dependency_name IF NOT EXISTS FOR (d:Dependency) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT breaking_scope_pair IF NOT EXISTS FOR (bs:BreakingScope) REQUIRE (bs.scope, bs.severity) IS UNIQUE",
    "CREATE CONSTRAINT migration_context_key IF NOT EXISTS FOR (mc:MigrationContext) REQUIRE (mc.projectId, mc.fromVersion, mc.toVersion) IS UNIQUE",
    "CREATE INDEX version_sortable IF NOT EXISTS FOR (v:Version) ON (v.sortableVersion)",
    "CREATE INDEX version_framework IF NOT EXISTS FOR (v:Version) ON (v.framework)",
    "CREATE FULLTEXT INDEX rule_statement IF NOT EXISTS FOR (r:MigrationRule) ON EACH [r.statement]",
    "CREATE FULLTEXT INDEX step_instruction IF NOT EXISTS FOR (s:MigrationStep) ON EACH [s.instruction, s.summary]",
    "CREATE INDEX step_rule_index IF NOT EXISTS FOR (s:MigrationStep) ON (s.ruleId, s.stepIndex)",
    "CREATE INDEX step_effort IF NOT EXISTS FOR (s:MigrationStep) ON (s.effort)",
    "CREATE INDEX breaking_scope_scope IF NOT EXISTS FOR (bs:BreakingScope) ON (bs.scope)",
    "CREATE INDEX context_project IF NOT EXISTS FOR (mc:MigrationContext) ON (mc.projectId)",
    "CREATE FULLTEXT INDEX migration_text IF NOT EXISTS FOR (n:MigrationRule) ON EACH [n.statement, n.reason, n.solution]",
    "CREATE FULLTEXT INDEX openrewrite_recipe_description IF NOT EXISTS FOR (r:OpenRewriteRecipe) ON EACH [r.description, r.displayName]",
]
for i, ddl in enumerate(ddl_statements):
    name = ddl.split()[2] + " " + ddl.split()[3]
    with driver.session() as s:
        try:
            s.run(ddl).consume()
            record(f"DDL{i+1:02d}", name, "PASS", "idempotent OK")
        except (ClientError, DatabaseError) as exc:
            record(f"DDL{i+1:02d}", name, "FAIL", str(exc))

# ─────────────────────────────────────────────────────────────────────────────
# Teardown — delete test MigrationContext
# ─────────────────────────────────────────────────────────────────────────────
if CTX_ID:
    try:
        with driver.session() as s:
            s.run("""
            MATCH (ctx:MigrationContext {projectId: '__cypher_test__'})
            DETACH DELETE ctx
            """).consume()
        print(f"\n  [teardown] Deleted test MigrationContext {CTX_ID}")
    except Exception as exc:
        print(f"\n  [teardown] WARNING: could not delete test context: {exc}")

driver.close()

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
passed = [r for r in results if r[2] == "PASS"]
warned = [r for r in results if r[2] == "WARN"]
failed = [r for r in results if r[2] == "FAIL"]

print("\n" + "=" * 70)
print(f"RESULTS: {len(passed)} PASS  |  {len(warned)} WARN  |  {len(failed)} FAIL")
print("=" * 70)

if warned:
    print("\nWARNINGS:")
    for qid, label, _, detail in warned:
        print(f"  ⚠️  [{qid}] {label}: {detail}")

if failed:
    print("\nFAILURES:")
    for qid, label, _, detail in failed:
        print(f"  ❌ [{qid}] {label}: {detail}")

# Write ISSUES.md
now = datetime.now().isoformat(timespec="seconds")
lines = [
    "# MCP Server — Cypher Query Live Test Results\n",
    f"Probe date: {now}\n",
    f"Neo4j: {URI}\n",
    f"Framework: {FRAMEWORK}  {FROM_VER} → {TO_VER}\n",
    "\n## Summary\n",
    "| # | Query ID | Label | Status | Detail |\n",
    "|---|---|---|---|---|\n",
]
for i, (qid, label, status, detail) in enumerate(results, 1):
    icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(status, "")
    lines.append(f"| {i} | `{qid}` | {label} | {icon} {status} | {detail[:100]} |\n")

if failed:
    lines.append("\n## Failures\n")
    for qid, label, _, detail in failed:
        lines.append(f"\n### [{qid}] {label}\n")
        lines.append(f"**Error:** `{detail}`\n")

if warned:
    lines.append("\n## Warnings\n")
    for qid, label, _, detail in warned:
        lines.append(f"\n### [{qid}] {label}\n")
        lines.append(f"**Detail:** {detail}\n")

if not failed and not warned:
    lines.append("\n## Result: CLEAN — all queries passed.\n")

with open("ISSUES.md", "w") as f:
    f.writelines(lines)
print(f"\nReport written to ISSUES.md")
sys.exit(1 if failed else 0)

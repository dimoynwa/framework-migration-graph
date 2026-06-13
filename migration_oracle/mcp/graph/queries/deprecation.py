"""Deprecation and entity evolution Cypher queries."""

from __future__ import annotations

from migration_oracle.graph.driver import read_session

_RESOLVE_DEPRECATION = """
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

_ENTITY_EVOLUTION = """
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


def resolve_deprecation(*, entity_name: str, framework: str) -> dict | None:
    with read_session() as session:
        record = session.run(
            _RESOLVE_DEPRECATION,
            entity_name=entity_name,
            framework=framework,
        ).single()
    if record is None or record.get("entity_name") is None:
        return None
    return dict(record)


def entity_evolution(*, entity_name: str, framework: str) -> list[dict]:
    with read_session() as session:
        return [dict(row) for row in session.run(
            _ENTITY_EVOLUTION,
            entity_name=entity_name,
            framework=framework,
        )]

"""Hybrid search and node hydration Cypher queries."""

from __future__ import annotations

import re

from neo4j.exceptions import ClientError

from migration_oracle.graph.driver import read_session

_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def escape_lucene(query: str) -> str:
    return _LUCENE_SPECIAL.sub(r"\\\1", query)


def bm25_search(*, query: str, index: str, top_k: int) -> list[str]:
    escaped = escape_lucene(query)
    cypher = """
    CALL db.index.fulltext.queryNodes($index, $search_text, {limit: $top_k})
    YIELD node, score
    RETURN elementId(node) AS id
    ORDER BY score DESC
    LIMIT $top_k
    """
    with read_session() as session:
        try:
            rows = session.run(
                cypher, index=index, search_text=escaped, top_k=top_k
            )
            return [row["id"] for row in rows if row.get("id")]
        except ClientError:
            return []


def vector_search(
    *,
    embedding: list[float],
    index: str,
    top_k: int,
    min_similarity: float,
) -> list[str]:
    cypher = """
    CALL db.index.vector.queryNodes($index, $top_k, $embedding)
    YIELD node, score
    WHERE score >= $min_similarity
    RETURN elementId(node) AS id
    ORDER BY score DESC
    LIMIT $top_k
    """
    try:
        with read_session() as session:
            rows = session.run(
                cypher,
                index=index,
                embedding=embedding,
                top_k=top_k,
                min_similarity=min_similarity,
            )
            return [row["id"] for row in rows if row.get("id")]
    except ClientError:
        return []


def hydrate_nodes(
    *,
    element_ids: list[str],
    framework: str | None = None,
) -> list[dict]:
    if not element_ids:
        return []
    cypher = """
    MATCH (n) WHERE elementId(n) IN $ids
    OPTIONAL MATCH (n)-[:INCLUDES_RULE|DISCOVERED_IN]-(v:Version)
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
           n.title AS title,
           n.displayName AS display_name,
           versions
    """
    with read_session() as session:
        return [
            dict(row)
            for row in session.run(
                cypher,
                ids=element_ids,
                framework=framework,
            )
        ]


def hydrate_openrewrite_recipes(
    *,
    element_ids: list[str],
    only_composite: bool | None = None,
    require_no_params: bool = False,
) -> list[dict]:
    if not element_ids:
        return []
    cypher = """
    MATCH (r:OpenRewriteRecipe) WHERE elementId(r) IN $ids
      AND (NOT $only_composite OR r.composite = true)
      AND (NOT $require_no_params OR NOT EXISTS {
        MATCH (r)-[:HAS_PARAM]->(p:RecipeParam) WHERE p.required = true
      })
    RETURN elementId(r) AS node_id,
           r.recipeId AS recipe_id,
           r.displayName AS display_name,
           r.description AS description,
           r.artifactId AS artifact_id,
           r.groupId AS group_id,
           r.artifactVersion AS artifact_version,
           coalesce(r.isComposite, false) AS is_composite,
           coalesce(r.tags, []) AS tags
    """
    with read_session() as session:
        return [
            dict(row)
            for row in session.run(
                cypher,
                ids=element_ids,
                only_composite=only_composite is True,
                require_no_params=require_no_params,
            )
        ]

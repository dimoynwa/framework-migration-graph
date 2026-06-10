"""Community insight CRUD Cypher queries."""

from __future__ import annotations

import math

from migration_oracle.graph.driver import read_session, write_session
from migration_oracle.mcp.graph.queries.search import bm25_search, vector_search

_DUPLICATE_SIMILARITY_THRESHOLD = 0.92

_FIND_EXACT_STATEMENT = """
MATCH (r:MigrationRule)
WHERE r.statement = $statement AND r.ruleType = 'community_insight'
RETURN elementId(r) AS insight_id
LIMIT 1
"""

_FETCH_EMBEDDING = """
MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
RETURN r.embedding AS embedding
"""

_SUBMIT_INSIGHT = """
MATCH (v:Version {framework: $framework, version: $version})
CREATE (r:MigrationRule {
  statement:            $statement,
  ruleType:             'community_insight',
  sourceUrl:            coalesce($evidence_url, ''),
  communitySubmittedBy: coalesce($submitted_by, 'mcp-agent'),
  communityCreatedAt:   toString(datetime()),
  communityConfidence:  coalesce($confidence, 0.5),
  communityVotes:       0,
  communityVerified:    false
})
WITH r, v
FOREACH (emb IN CASE WHEN $embedding IS NOT NULL THEN [1] ELSE [] END |
  SET r.embedding = $embedding
)
WITH r, v
CREATE (v)-[:INCLUDES_RULE]->(r)
CREATE (s:MigrationStep {
  stepType:    'manual',
  summary:     coalesce($solution, ''),
  instruction: coalesce($solution, ''),
  effort:      'moderate',
  automatable: false
})
CREATE (r)-[:REQUIRES_STEP]->(s)
WITH r
FOREACH (class_name IN coalesce($affected_classes, []) |
  MERGE (c:Class {name: class_name})
  ON CREATE SET c.framework = $framework
  ON MATCH SET  c.framework = coalesce(c.framework, $framework)
  MERGE (r)-[:AFFECTS_CLASS]->(c)
)
WITH r
FOREACH (prop_name IN coalesce($affected_properties, []) |
  MERGE (p:ApplicationProperty {name: prop_name})
  ON CREATE SET p.framework = $framework
  ON MATCH SET  p.framework = coalesce(p.framework, $framework)
  MERGE (r)-[:AFFECTS_PROPERTY]->(p)
)
WITH r
FOREACH (dep_name IN coalesce($affected_dependencies, []) |
  MERGE (d:Dependency {name: dep_name})
  ON CREATE SET d.framework = $framework
  ON MATCH SET  d.framework = coalesce(d.framework, $framework)
  MERGE (r)-[:AFFECTS_DEPENDENCY]->(d)
)
RETURN elementId(r) AS insight_id
"""

_QUERY_INSIGHTS = """
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

_VOTE_INSIGHT = """
MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
SET r.communityVotes = coalesce(r.communityVotes, 0) + $delta
RETURN elementId(r) AS insight_id, r.communityVotes AS votes
"""

_VERIFY_INSIGHT = """
MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id
SET r.communityVerified = true
RETURN elementId(r) AS insight_id, r.communityVerified AS verified
"""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _find_exact_statement(*, statement: str) -> str | None:
    with read_session() as session:
        record = session.run(_FIND_EXACT_STATEMENT, statement=statement).single()
    if record is None:
        return None
    return record.get("insight_id")


def _best_bm25_duplicate(*, statement: str, embedding: list[float]) -> str | None:
    hits = bm25_search(query=statement, index="rule_statement", top_k=5)
    for hit_id in hits:
        with read_session() as session:
            record = session.run(_FETCH_EMBEDDING, insight_id=hit_id).single()
        stored = record.get("embedding") if record else None
        if stored and _cosine_similarity(embedding, stored) >= _DUPLICATE_SIMILARITY_THRESHOLD:
            return hit_id
    return None


def find_near_duplicate(
    *,
    statement: str,
    embedding: list[float] | None = None,
) -> str | None:
    exact_id = _find_exact_statement(statement=statement)
    if exact_id:
        return exact_id
    if not embedding:
        return None
    vector_hits = vector_search(
        embedding=embedding,
        index="migration_knowledge_vector_mr",
        top_k=5,
        min_similarity=_DUPLICATE_SIMILARITY_THRESHOLD,
    )
    if vector_hits:
        return vector_hits[0]
    return _best_bm25_duplicate(statement=statement, embedding=embedding)


def submit_insight(
    *,
    statement: str,
    framework: str,
    version: str,
    solution: str | None = None,
    affected_properties: list[str] | None = None,
    affected_classes: list[str] | None = None,
    affected_dependencies: list[str] | None = None,
    evidence_url: str | None = None,
    confidence: float | None = None,
    submitted_by: str = "mcp-agent",
    embedding: list[float] | None = None,
) -> tuple[str, bool]:
    duplicate_id = find_near_duplicate(statement=statement, embedding=embedding)
    if duplicate_id:
        return duplicate_id, True
    params = {
        "statement": statement,
        "framework": framework,
        "version": version,
        "solution": solution,
        "affected_properties": affected_properties or [],
        "affected_classes": affected_classes or [],
        "affected_dependencies": affected_dependencies or [],
        "evidence_url": evidence_url,
        "confidence": confidence,
        "submitted_by": submitted_by,
        "embedding": embedding,
    }
    with write_session() as session:
        record = session.run(_SUBMIT_INSIGHT, params).single()
    if record is None:
        raise ValueError(f"Version not found: {framework} {version}")
    return record["insight_id"], False


def query_insights(
    *,
    framework: str,
    from_sortable: int | None = None,
    to_sortable: int | None = None,
    entity_name: str | None = None,
    verified_only: bool = False,
) -> list[dict]:
    with read_session() as session:
        return [
            dict(row)
            for row in session.run(
                _QUERY_INSIGHTS,
                framework=framework,
                from_sortable=from_sortable,
                to_sortable=to_sortable,
                entity_name=entity_name,
                verified_only=verified_only,
            )
        ]


def vote_insight(*, insight_id: str, delta: int) -> dict:
    with write_session() as session:
        record = session.run(
            _VOTE_INSIGHT, insight_id=insight_id, delta=delta
        ).single()
    if record is None:
        raise ValueError(f"Insight not found: {insight_id}")
    return dict(record)


def verify_insight(*, insight_id: str) -> dict:
    with write_session() as session:
        record = session.run(_VERIFY_INSIGHT, insight_id=insight_id).single()
    if record is None:
        raise ValueError(f"Insight not found: {insight_id}")
    return dict(record)

"""Community insight CRUD Cypher queries."""

from __future__ import annotations

import math

from migration_oracle.graph.driver import read_session, write_session
from migration_oracle.mcp.graph.queries.search import bm25_search, vector_search

_DUPLICATE_SIMILARITY_THRESHOLD = 0.92

_FIND_EXACT_STATEMENT = """
MATCH (ci:CommunityInsight)
WHERE ci.statement = $statement
RETURN elementId(ci) AS insight_id
LIMIT 1
"""

_FETCH_EMBEDDING = """
MATCH (ci:CommunityInsight) WHERE elementId(ci) = $insight_id
RETURN ci.embedding AS embedding
"""

_SUBMIT_INSIGHT = """
MATCH (v:Version {framework: $framework, version: $version})
CREATE (ci:CommunityInsight {
  statement: $statement,
  solution: coalesce($solution, ''),
  sourceUrl: coalesce($evidence_url, ''),
  submittedBy: coalesce($submitted_by, 'mcp-agent'),
  createdAt: toString(datetime()),
  confidence: coalesce($confidence, 0.5),
  votes: 0,
  verified: false,
  embedding: $embedding
})
CREATE (ci)-[:DISCOVERED_IN]->(v)
WITH ci
FOREACH (class_name IN coalesce($affected_classes, []) |
  MERGE (c:Class {name: class_name})
  MERGE (ci)-[:AFFECTS_CLASS]->(c)
)
WITH ci
FOREACH (prop_name IN coalesce($affected_properties, []) |
  MERGE (p:ApplicationProperty {name: prop_name})
  MERGE (ci)-[:AFFECTS_PROPERTY]->(p)
)
WITH ci
FOREACH (dep_name IN coalesce($affected_dependencies, []) |
  MERGE (d:Dependency {name: dep_name})
  MERGE (ci)-[:AFFECTS_DEPENDENCY]->(d)
)
RETURN elementId(ci) AS insight_id
"""

_QUERY_INSIGHTS = """
MATCH (ci:CommunityInsight)-[:DISCOVERED_IN]->(v:Version {framework: $framework})
WHERE ($from_sortable IS NULL OR v.sortableVersion >= $from_sortable)
  AND ($to_sortable IS NULL OR v.sortableVersion <= $to_sortable)
  AND ($verified_only = false OR ci.verified = true)
OPTIONAL MATCH (ci)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH ci, v, collect(DISTINCT e.name) AS affected_entities
WHERE $entity_name IS NULL
   OR ANY(name IN affected_entities WHERE name = $entity_name)
RETURN elementId(ci) AS insight_id,
       ci.statement AS statement,
       ci.solution AS solution,
       ci.sourceUrl AS source_url,
       ci.submittedBy AS submitted_by,
       ci.createdAt AS created_at,
       ci.confidence AS confidence,
       ci.votes AS votes,
       ci.verified AS verified,
       v.version AS version,
       affected_entities
ORDER BY ci.votes DESC, ci.createdAt DESC
"""

_VOTE_INSIGHT = """
MATCH (ci:CommunityInsight) WHERE elementId(ci) = $insight_id
SET ci.votes = coalesce(ci.votes, 0) + $delta
RETURN elementId(ci) AS insight_id, ci.votes AS votes
"""

_VERIFY_INSIGHT = """
MATCH (ci:CommunityInsight) WHERE elementId(ci) = $insight_id
SET ci.verified = true
RETURN elementId(ci) AS insight_id, ci.verified AS verified
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
    hits = bm25_search(query=statement, index="migration_text", top_k=5)
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
        index="migration_knowledge_vector_ci",
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
        raise RuntimeError("Failed to create CommunityInsight")
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

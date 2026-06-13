"""Community insight MCP tool handlers."""

from __future__ import annotations

from migration_oracle.mcp.graph.queries import community as community_queries
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.tools.search import get_embedding_model
from migration_oracle.models.graph import sortable_version


def _normalise_version(v: str) -> str:
    """Pad 'major' → 'major.0.0' and 'major.minor' → 'major.minor.0'."""
    parts = v.split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


@mcp.tool()
def submit_migration_insight(
    statement: str,
    spring_boot_version: str,
    solution: str | None = None,
    affected_properties: list[str] | None = None,
    affected_classes: list[str] | None = None,
    affected_dependencies: list[str] | None = None,
    evidence_url: str | None = None,
    confidence: float | None = None,
    framework: str = "Spring Boot",
) -> dict:
    """Submit a developer-contributed migration insight. Writes a MigrationRule node with ruleType='community_insight'.

    Near-duplicate detection runs a three-pass pipeline (exact → vector → BM25+cosine) with a
    0.92 cosine similarity threshold before write. Returns status='duplicate' if a similar insight
    already exists — no new node is created.

    Return field semantics across all three status paths:
    - status='ok':        insight_id=<new element ID>,  duplicate_of=None
    - status='duplicate': insight_id=None,              duplicate_of=<existing element ID>
    - status='error':     insight_id=None,              duplicate_of=None

    Not idempotent — call once per unique finding.

    Note: the parameter 'spring_boot_version' holds the framework version string
    regardless of the 'framework' value (e.g. '3.2' for Spring Boot, '30' for WildFly).
    """
    embedding: list[float] | None = None
    try:
        _vec = get_embedding_model().encode(statement)
        embedding = _vec.tolist()
    except Exception:
        pass
    try:
        new_id, is_duplicate = community_queries.submit_insight(
            statement=statement,
            framework=framework,
            version=_normalise_version(spring_boot_version),
            solution=solution,
            affected_properties=affected_properties,
            affected_classes=affected_classes,
            affected_dependencies=affected_dependencies,
            evidence_url=evidence_url,
            confidence=confidence,
            embedding=embedding,
        )
    except ValueError as e:
        return {"status": "error", "insight_id": None, "duplicate_of": None, "message": str(e)}
    if is_duplicate:
        return {
            "status": "duplicate",
            "insight_id": None,
            "duplicate_of": new_id,
            "message": "Near-duplicate insight already exists",
        }
    return {
        "status": "ok",
        "insight_id": new_id,
        "duplicate_of": None,
        "message": "Insight submitted",
    }


@mcp.tool()
def get_community_insights(
    from_version: str | None = None,
    to_version: str | None = None,
    entity_name: str | None = None,
    entity_type: str | None = None,
    verified_only: bool = False,
    framework: str = "Spring Boot",
) -> dict:
    """Query MigrationRule nodes (ruleType='community_insight') by version range, entity name, or verified status. Read-only.

    Returns: insights list with statement, solution, votes, verified, confidence, version.
    Note: entity_type filter is accepted but not yet applied — all entity types are returned.
    Use verified_only=True to return only moderator-approved insights.
    """
    del entity_type  # reserved for future entity-type filtering
    from_sortable = sortable_version(from_version) if from_version else None
    to_sortable = sortable_version(to_version) if to_version else None
    insights = community_queries.query_insights(
        framework=framework,
        from_sortable=from_sortable,
        to_sortable=to_sortable,
        entity_name=entity_name,
        verified_only=verified_only,
    )
    records = [
        {
            "insight_id": row.get("insight_id") or "",
            "statement": row.get("statement") or "",
            "solution": row.get("solution") or "",
            "source_url": row.get("source_url") or "",
            "submitted_by": row.get("submitted_by") or "",
            "created_at": row.get("created_at") or "",
            "confidence": row.get("confidence") or 0.0,
            "votes": row.get("votes") or 0,
            "verified": bool(row.get("verified")),
            "version": row.get("version") or "",
        }
        for row in insights
    ]
    return {"status": "ok", "insights": records, "total": len(records)}


@mcp.tool()
def vote_insight(insight_id: str, delta: int = 1) -> dict:
    """Increment or decrement the votes count on a community insight. Not idempotent.

    delta=1 for upvote, delta=-1 for downvote. Calling twice with delta=1 adds 2 votes.
    Returns: insight_id, new_vote_count.
    """
    result = community_queries.vote_insight(insight_id=insight_id, delta=delta)
    return {
        "status": "ok",
        "insight_id": result["insight_id"],
        "new_vote_count": result["votes"],
    }


@mcp.tool()
def verify_insight(insight_id: str) -> dict:
    """Mark a community insight as verified (moderator operation). Sets verified=true.

    This is a write operation and is not reversible via this tool.
    Returns: insight_id, verified (always true on success).
    """
    result = community_queries.verify_insight(insight_id=insight_id)
    return {
        "status": "ok",
        "insight_id": result["insight_id"],
        "verified": bool(result["verified"]),
    }

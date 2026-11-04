"""Community insight MCP tool handlers."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from migration_oracle.mcp.graph.queries import community as community_queries
from migration_oracle.mcp.graph.queries.upgrade import resolve_version
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.tools.search import get_embedding_model
from migration_oracle.models.graph import VersionResolutionFailure, sortable_version


@mcp.tool()
def submit_migration_insight(
    statement: Annotated[
        str,
        Field(description="Developer-contributed migration finding or workaround to store as a community insight."),
    ],
    spring_boot_version: Annotated[
        str,
        Field(description="Framework version string to attach the insight to; name is legacy and applies to any framework."),
    ],
    solution: Annotated[
        str | None,
        Field(description="Optional recommended remediation or workaround text."),
    ] = None,
    affected_properties: Annotated[
        list[str] | None,
        Field(description="Optional affected application property keys."),
    ] = None,
    affected_classes: Annotated[
        list[str] | None,
        Field(description="Optional affected fully-qualified class names or simple class names."),
    ] = None,
    affected_dependencies: Annotated[
        list[str] | None,
        Field(description="Optional affected dependency coordinates or artifact IDs."),
    ] = None,
    evidence_url: Annotated[
        str | None,
        Field(description="Optional source URL supporting the submitted insight."),
    ] = None,
    confidence: Annotated[
        float | None,
        Field(description="Optional confidence score for the insight, typically between 0 and 1."),
    ] = None,
    framework: Annotated[
        str,
        Field(description="Framework name whose Version node should receive the community insight."),
    ] = "Spring Boot",
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
    resolution = resolve_version(framework, spring_boot_version, mode="floor")
    if isinstance(resolution, VersionResolutionFailure):
        return {
            "status": "error",
            "error_code": "version_not_in_graph",
            "insight_id": None,
            "duplicate_of": None,
            "message": (
                f"Version {spring_boot_version!r} not found in graph for framework {framework!r}. "
                f"Candidates considered: {', '.join(resolution.candidatesConsidered) or 'none'}"
            ),
            "candidates_considered": resolution.candidatesConsidered,
        }

    resolved_version = resolution.resolvedVersion

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
            version=resolved_version,
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
    from_version: Annotated[
        str | None,
        Field(description="Optional lower bound framework version for insight lookup."),
    ] = None,
    to_version: Annotated[
        str | None,
        Field(description="Optional upper bound framework version for insight lookup."),
    ] = None,
    entity_name: Annotated[
        str | None,
        Field(description="Optional affected entity name to filter insights by."),
    ] = None,
    entity_type: Annotated[
        str | None,
        Field(description="Accepted for compatibility but not currently applied; all entity types are returned."),
    ] = None,
    verified_only: Annotated[
        bool,
        Field(description="When true, return only moderator-verified community insights."),
    ] = False,
    framework: Annotated[
        str,
        Field(description="Framework name for the insight query, for example 'Spring Boot'."),
    ] = "Spring Boot",
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
def vote_insight(
    insight_id: Annotated[
        str,
        Field(description="Community insight identifier to vote on."),
    ],
    delta: Annotated[
        int,
        Field(description="Vote delta: 1 for upvote, -1 for downvote. The operation is not idempotent."),
    ] = 1,
) -> dict:
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
def verify_insight(
    insight_id: Annotated[
        str,
        Field(description="Community insight identifier to mark as verified. Moderator/trusted-operator write operation."),
    ],
) -> dict:
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

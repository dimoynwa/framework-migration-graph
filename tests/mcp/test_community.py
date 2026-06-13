"""Tests for community insight MCP tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from migration_oracle.mcp.graph.queries.community import (
    _QUERY_INSIGHTS,
    _SUBMIT_INSIGHT,
    find_near_duplicate,
    submit_insight,
)
from migration_oracle.mcp.tools.community import (
    submit_migration_insight,
    verify_insight,
    vote_insight,
)


def test_submit_insight_new():
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1])
    with (
        patch(
            "migration_oracle.mcp.tools.community.get_embedding_model",
            return_value=mock_model,
        ),
        patch(
            "migration_oracle.mcp.tools.community.community_queries.submit_insight",
            return_value=("insight-1", False),
        ),
    ):
        result = submit_migration_insight(
            statement="Workaround for X",
            spring_boot_version="3.4.0",
        )
    assert result["status"] == "ok"
    assert result["insight_id"] == "insight-1"


def test_submit_insight_duplicate_detected():
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1])
    with (
        patch(
            "migration_oracle.mcp.tools.community.get_embedding_model",
            return_value=mock_model,
        ),
        patch(
            "migration_oracle.mcp.tools.community.community_queries.submit_insight",
            return_value=("existing-id", True),
        ),
    ):
        result = submit_migration_insight(
            statement="Duplicate insight",
            spring_boot_version="3.4.0",
        )
    assert result["status"] == "duplicate"
    assert result["insight_id"] is None
    assert result["duplicate_of"] == "existing-id"


def test_vote_insight_increment():
    with patch(
        "migration_oracle.mcp.tools.community.community_queries.vote_insight",
        return_value={"insight_id": "i1", "votes": 6},
    ):
        result = vote_insight(insight_id="i1", delta=1)
    assert result["status"] == "ok"
    assert result["new_vote_count"] == 6


def test_verify_insight():
    with patch(
        "migration_oracle.mcp.tools.community.community_queries.verify_insight",
        return_value={"insight_id": "i1", "verified": True},
    ):
        result = verify_insight(insight_id="i1")
    assert result["verified"] is True


# T018: ValueError / Version-not-found path
def test_submit_insight_version_not_found():
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1])
    with (
        patch(
            "migration_oracle.mcp.tools.community.get_embedding_model",
            return_value=mock_model,
        ),
        patch(
            "migration_oracle.mcp.tools.community.community_queries.submit_insight",
            side_effect=ValueError("Version not found: Spring Boot 9.9"),
        ),
    ):
        result = submit_migration_insight(
            statement="Some insight",
            spring_boot_version="9.9",
        )
    assert result == {
        "status": "error",
        "insight_id": None,
        "duplicate_of": None,
        "message": "Version not found: Spring Boot 9.9",
    }


# T019: MigrationRule + MigrationStep write atomicity — single session.run
def test_submit_insight_write_atomicity():
    mock_record = MagicMock()
    mock_record.__getitem__ = lambda self, key: "new-id" if key == "insight_id" else None
    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = mock_record

    with (
        patch(
            "migration_oracle.mcp.graph.queries.community.find_near_duplicate",
            return_value=None,
        ),
        patch(
            "migration_oracle.mcp.graph.queries.community.write_session",
        ) as mock_write_session,
    ):
        mock_write_session.return_value.__enter__ = lambda self: mock_session
        mock_write_session.return_value.__exit__ = MagicMock(return_value=False)
        submit_insight(
            statement="x",
            framework="spring_boot",
            version="3.0.0",
            solution="fix it",
        )

    assert mock_session.run.call_count == 1
    cypher_arg = mock_session.run.call_args[0][0]
    assert "CREATE (r:MigrationRule" in cypher_arg
    assert "CREATE (s:MigrationStep" in cypher_arg
    assert "REQUIRES_STEP" in cypher_arg


# T020: solution field sourcing from MigrationStep.instruction
def test_query_insights_solution_from_step():
    mock_record = {
        "insight_id": "i1",
        "statement": "stmt",
        "solution": "test step instruction",
        "source_url": "",
        "submitted_by": "agent",
        "created_at": "2026-01-01",
        "confidence": 0.8,
        "votes": 0,
        "verified": False,
        "version": "3.0.0",
        "affected_entities": [],
    }
    mock_session = MagicMock()
    mock_session.run.return_value = [mock_record]

    with patch(
        "migration_oracle.mcp.graph.queries.community.read_session",
    ) as mock_read_session:
        mock_read_session.return_value.__enter__ = lambda self: mock_session
        mock_read_session.return_value.__exit__ = MagicMock(return_value=False)
        from migration_oracle.mcp.graph.queries.community import query_insights
        results = query_insights(framework="Spring Boot")

    assert results[0]["solution"] == "test step instruction"
    assert "OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)" in _QUERY_INSIGHTS
    assert "coalesce(first_step.instruction" in _QUERY_INSIGHTS


# T021: duplicate-detection index names
def test_find_near_duplicate_uses_mr_vector_index():
    with (
        patch(
            "migration_oracle.mcp.graph.queries.community._find_exact_statement",
            return_value=None,
        ),
        patch(
            "migration_oracle.mcp.graph.queries.community.vector_search",
            return_value=["dup-id"],
        ) as mock_vector,
    ):
        result = find_near_duplicate(statement="x", embedding=[0.1, 0.2])

    mock_vector.assert_called_once()
    call_kwargs = mock_vector.call_args[1]
    assert call_kwargs["index"] == "migration_knowledge_vector_mr"
    assert call_kwargs["index"] != "migration_knowledge_vector_ci"
    assert result == "dup-id"


def test_find_near_duplicate_uses_rule_statement_bm25_index():
    with (
        patch(
            "migration_oracle.mcp.graph.queries.community._find_exact_statement",
            return_value=None,
        ),
        patch(
            "migration_oracle.mcp.graph.queries.community.vector_search",
            return_value=[],
        ),
        patch(
            "migration_oracle.mcp.graph.queries.community.bm25_search",
            return_value=[],
        ) as mock_bm25,
    ):
        find_near_duplicate(statement="x", embedding=[0.1, 0.2])

    mock_bm25.assert_called_once()
    call_kwargs = mock_bm25.call_args[1]
    assert call_kwargs["index"] == "rule_statement"


# T022: community property prefixes in _SUBMIT_INSIGHT Cypher
def test_submit_insight_cypher_uses_prefixed_properties():
    assert "communityVotes" in _SUBMIT_INSIGHT
    assert "communityVerified" in _SUBMIT_INSIGHT
    assert "communitySubmittedBy" in _SUBMIT_INSIGHT
    assert "communityCreatedAt" in _SUBMIT_INSIGHT
    assert "communityConfidence" in _SUBMIT_INSIGHT
    assert "votes:" not in _SUBMIT_INSIGHT
    assert "verified:" not in _SUBMIT_INSIGHT
    assert "submittedBy:" not in _SUBMIT_INSIGHT


# T023: verified_only filter in _QUERY_INSIGHTS
def test_query_insights_verified_only_filter_in_cypher():
    assert "$verified_only = false OR r.communityVerified = true" in _QUERY_INSIGHTS


def test_query_insights_verified_only_param_passed():
    mock_session = MagicMock()
    mock_session.run.return_value = []

    with patch(
        "migration_oracle.mcp.graph.queries.community.read_session",
    ) as mock_read_session:
        mock_read_session.return_value.__enter__ = lambda self: mock_session
        mock_read_session.return_value.__exit__ = MagicMock(return_value=False)
        from migration_oracle.mcp.graph.queries.community import query_insights
        query_insights(framework="Spring Boot", verified_only=True)

    call_kwargs = mock_session.run.call_args
    assert call_kwargs[1]["verified_only"] is True


# T024: AFFECTS_CLASS, AFFECTS_PROPERTY, AFFECTS_DEPENDENCY relationships in _SUBMIT_INSIGHT
def test_submit_insight_cypher_has_entity_relationships():
    assert "AFFECTS_CLASS" in _SUBMIT_INSIGHT
    assert "AFFECTS_PROPERTY" in _SUBMIT_INSIGHT
    assert "AFFECTS_DEPENDENCY" in _SUBMIT_INSIGHT
    assert "FOREACH" in _SUBMIT_INSIGHT
    assert "MERGE" in _SUBMIT_INSIGHT


# T025: embedding-disabled (embedding=None) path
def test_submit_insight_embedding_none_no_exception():
    submitted_kwargs: dict = {}

    def capture_submit(**kwargs):
        submitted_kwargs.update(kwargs)
        return ("fake-id", False)

    with (
        patch(
            "migration_oracle.mcp.tools.community.get_embedding_model",
            side_effect=Exception("no model"),
        ),
        patch(
            "migration_oracle.mcp.tools.community.community_queries.submit_insight",
            side_effect=capture_submit,
        ),
    ):
        result = submit_migration_insight(
            statement="test stmt",
            spring_boot_version="3.0.0",
        )

    assert result["status"] == "ok"
    assert submitted_kwargs.get("embedding") is None


def test_find_near_duplicate_skips_vector_when_embedding_none():
    with (
        patch(
            "migration_oracle.mcp.graph.queries.community._find_exact_statement",
            return_value=None,
        ),
        patch(
            "migration_oracle.mcp.graph.queries.community.vector_search",
        ) as mock_vector,
    ):
        result = find_near_duplicate(statement="x", embedding=None)

    mock_vector.assert_not_called()
    assert result is None

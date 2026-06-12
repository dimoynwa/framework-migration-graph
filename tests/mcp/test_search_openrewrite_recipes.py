"""Tests for spec 011 US2: OpenRewriteRecipe description/displayName population."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# FR-009: description/displayName set on stub nodes during ingestion
# ---------------------------------------------------------------------------

@patch("migration_oracle.pipeline.populator.write_session")
def test_description_set_on_stub(mock_write_session):
    """_write_step sets e.description and e.displayName from step.summary on ON CREATE."""
    from migration_oracle.models.entities import MigrationStep, StepType, MigrationEntity
    from migration_oracle.models.entities import Effort

    session = MagicMock()
    session.run.return_value = MagicMock()

    from migration_oracle.pipeline.populator import _write_step

    step = MigrationStep(
        index=0,
        step_type=StepType.CONFIGURE,
        summary="Update Spring Boot parent POM to 4.0.0",
        instruction="Open pom.xml and change the parent version",
        effort=Effort.MODERATE,
        automatable=True,
        verification="mvn spring-boot:run",
        cli_operation="",
        requires=[],
    )
    entity = MagicMock()
    entity.entities = []

    _write_step(session, rule_id="rule-id-1", step=step, entity=entity, framework_display="Spring Boot")

    # Collect all Cypher strings passed to session.run()
    all_cypher = " ".join(str(c) for c in session.run.call_args_list)
    assert "description" in all_cypher
    assert "displayName" in all_cypher


@patch("migration_oracle.pipeline.populator.write_session")
def test_backfill_on_match(mock_write_session):
    """_write_step uses coalesce on ON MATCH SET so existing descriptions are not overwritten."""
    from migration_oracle.models.entities import MigrationStep, StepType
    from migration_oracle.models.entities import Effort

    session = MagicMock()
    session.run.return_value = MagicMock()

    from migration_oracle.pipeline.populator import _write_step

    step = MigrationStep(
        index=0,
        step_type=StepType.CONFIGURE,
        summary="Backfill check summary",
        instruction="test",
        effort=Effort.MODERATE,
        automatable=True,
        verification="",
        cli_operation="",
        requires=[],
    )
    entity = MagicMock()
    entity.entities = []

    _write_step(session, rule_id="rule-id-2", step=step, entity=entity, framework_display="Spring Boot")

    all_cypher = " ".join(str(c) for c in session.run.call_args_list)
    assert "coalesce" in all_cypher.lower()


# ---------------------------------------------------------------------------
# FR-009/FR-010: search_openrewrite_recipes returns hits when descriptions populated
# ---------------------------------------------------------------------------

@patch("migration_oracle.mcp.tools.search.search_queries.hydrate_openrewrite_recipes")
@patch("migration_oracle.mcp.tools.search.search_queries.bm25_search", return_value=["r1"])
@patch("migration_oracle.mcp.tools.search.search_queries.vector_search", return_value=[])
@patch("migration_oracle.mcp.tools.search.get_embedding_model")
def test_search_returns_hits(mock_model, mock_vector, mock_bm25, mock_hydrate):
    """search_openrewrite_recipes returns non-empty hits when fulltext index yields results."""
    mock_model.return_value.encode.return_value.tolist.return_value = [0.1] * 384
    mock_hydrate.return_value = [
        {
            "node_id": "r1",
            "recipe_id": "org.openrewrite.spring.UpgradeSpringBoot_4_0",
            "display_name": "Upgrade Spring Boot to 4.0",
            "description": "Upgrade Spring Boot parent POM to 4.0.0",
            "artifact_id": "rewrite-spring",
            "group_id": "org.openrewrite",
            "artifact_version": "8.0.0",
            "is_composite": False,
            "tags": [],
        }
    ]

    import asyncio
    from migration_oracle.mcp.tools.search import search_openrewrite_recipes

    result = asyncio.run(search_openrewrite_recipes(query="Spring Boot upgrade 4.0"))

    assert result["status"] == "ok"
    assert len(result["hits"]) == 1
    assert result["hits"][0]["statement"] == "Upgrade Spring Boot parent POM to 4.0.0"


@patch("migration_oracle.mcp.tools.search.search_queries.hydrate_openrewrite_recipes")
@patch("migration_oracle.mcp.tools.search.search_queries.bm25_search", return_value=[])
@patch("migration_oracle.mcp.tools.search.search_queries.vector_search", return_value=[])
@patch("migration_oracle.mcp.tools.search.get_embedding_model")
def test_zero_hits_when_description_absent(mock_model, mock_vector, mock_bm25, mock_hydrate):
    """search_openrewrite_recipes returns empty hits when fulltext BM25 returns nothing."""
    mock_model.return_value.encode.return_value.tolist.return_value = [0.1] * 384
    mock_hydrate.return_value = []

    import asyncio
    from migration_oracle.mcp.tools.search import search_openrewrite_recipes

    result = asyncio.run(search_openrewrite_recipes(query="Spring Boot upgrade 4.0"))

    assert result["status"] == "ok"
    assert result["hits"] == []

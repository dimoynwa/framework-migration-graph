"""Tests for spec 010 US8: search_openrewrite_recipes filter pass-through."""

from __future__ import annotations

from unittest.mock import patch, MagicMock


def _make_recipe_node(node_id: str = "r1") -> dict:
    return {
        "node_id": node_id,
        "recipe_id": f"recipe-{node_id}",
        "display_name": "Test Recipe",
        "description": "A test recipe",
        "artifact_id": "rewrite-spring",
        "group_id": "org.openrewrite",
        "artifact_version": "8.0.0",
        "is_composite": True,
        "tags": [],
    }


@patch("migration_oracle.mcp.tools.search.search_queries.hydrate_openrewrite_recipes")
@patch("migration_oracle.mcp.tools.search.search_queries.bm25_search", return_value=["r1"])
@patch("migration_oracle.mcp.tools.search.search_queries.vector_search", return_value=[])
@patch("migration_oracle.mcp.tools.search.get_embedding_model")
def test_only_composite_filter_applied(mock_model, mock_vector, mock_bm25, mock_hydrate):
    mock_model.return_value.encode.return_value.tolist.return_value = [0.1] * 384
    mock_hydrate.return_value = [_make_recipe_node("r1")]

    import asyncio
    from migration_oracle.mcp.tools.search import search_openrewrite_recipes

    asyncio.run(search_openrewrite_recipes(query="spring upgrade", only_composite=True))

    mock_hydrate.assert_called_once()
    call_kwargs = mock_hydrate.call_args[1]
    assert call_kwargs.get("only_composite") is True


@patch("migration_oracle.mcp.tools.search.search_queries.hydrate_openrewrite_recipes")
@patch("migration_oracle.mcp.tools.search.search_queries.bm25_search", return_value=["r1"])
@patch("migration_oracle.mcp.tools.search.search_queries.vector_search", return_value=[])
@patch("migration_oracle.mcp.tools.search.get_embedding_model")
def test_require_no_params_filter_applied(mock_model, mock_vector, mock_bm25, mock_hydrate):
    mock_model.return_value.encode.return_value.tolist.return_value = [0.1] * 384
    mock_hydrate.return_value = []

    import asyncio
    from migration_oracle.mcp.tools.search import search_openrewrite_recipes

    result = asyncio.run(
        search_openrewrite_recipes(query="spring upgrade", require_no_params=True)
    )

    assert result["hits"] == []
    mock_hydrate.assert_called_once()
    call_kwargs = mock_hydrate.call_args[1]
    assert call_kwargs.get("require_no_params") is True


@patch("migration_oracle.mcp.tools.search.search_queries.hydrate_openrewrite_recipes")
@patch("migration_oracle.mcp.tools.search.search_queries.bm25_search", return_value=["r1"])
@patch("migration_oracle.mcp.tools.search.search_queries.vector_search", return_value=[])
@patch("migration_oracle.mcp.tools.search.get_embedding_model")
def test_both_filters_combined(mock_model, mock_vector, mock_bm25, mock_hydrate):
    mock_model.return_value.encode.return_value.tolist.return_value = [0.1] * 384
    mock_hydrate.return_value = [_make_recipe_node("r1")]

    import asyncio
    from migration_oracle.mcp.tools.search import search_openrewrite_recipes

    asyncio.run(
        search_openrewrite_recipes(
            query="spring upgrade", only_composite=True, require_no_params=True
        )
    )

    call_kwargs = mock_hydrate.call_args[1]
    assert call_kwargs.get("only_composite") is True
    assert call_kwargs.get("require_no_params") is True

"""Tests for hybrid search MCP tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from migration_oracle.mcp.tools import search as search_tools


@pytest.mark.asyncio
async def test_hybrid_search_rrf_fusion():
    with (
        patch(
            "migration_oracle.mcp.tools.search.get_embedding_model",
            return_value=MagicMock(encode=lambda q: MagicMock(tolist=lambda: [0.1, 0.2])),
        ),
        patch(
            "migration_oracle.mcp.tools.search.search_queries.bm25_search",
            return_value=["id-a", "id-b"],
        ),
        patch(
            "migration_oracle.mcp.tools.search.search_queries.vector_search",
            return_value=["id-b", "id-c"],
        ),
        patch(
            "migration_oracle.mcp.tools.search.search_queries.hydrate_nodes",
            return_value=[
                {"node_id": "id-b", "node_type": "MigrationRule", "statement": "hit-b"},
                {"node_id": "id-a", "node_type": "MigrationRule", "statement": "hit-a"},
            ],
        ),
    ):
        result = await search_tools.search_migration_knowledge(
            query="security config", max_results=2
        )
    assert result["status"] == "ok"
    assert len(result["hits"]) <= 2
    assert result["hits"][0]["node_id"] == "id-b"


@pytest.mark.asyncio
async def test_hybrid_search_vector_unavailable():
    with (
        patch(
            "migration_oracle.mcp.tools.search.get_embedding_model",
            return_value=MagicMock(encode=lambda q: MagicMock(tolist=lambda: [0.1])),
        ),
        patch(
            "migration_oracle.mcp.tools.search.search_queries.bm25_search",
            return_value=["id-a"],
        ),
        patch(
            "migration_oracle.mcp.tools.search.search_queries.vector_search",
            return_value=[],
        ),
        patch(
            "migration_oracle.mcp.tools.search.search_queries.hydrate_nodes",
            return_value=[
                {"node_id": "id-a", "node_type": "MigrationRule", "statement": "only bm25"},
            ],
        ),
    ):
        result = await search_tools.search_migration_knowledge(query="fallback")
    assert result["status"] == "ok"
    assert result["hits"][0]["statement"] == "only bm25"


def test_embedding_model_loaded_once():
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance
    with patch("migration_oracle.mcp.tools.search.SentenceTransformer", mock_cls):
        search_tools._model = None
        first = search_tools.get_embedding_model()
        second = search_tools.get_embedding_model()
        third = search_tools.get_embedding_model()
    assert first is second is third
    mock_cls.assert_called_once()

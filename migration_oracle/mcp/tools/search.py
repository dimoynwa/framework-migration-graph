"""Hybrid search MCP tool handlers."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from sentence_transformers import SentenceTransformer

from migration_oracle import config
from migration_oracle.mcp.graph.queries import search as search_queries
from migration_oracle.mcp.instance import mcp
from migration_oracle.mcp.tools._rrf import rrf_fuse

_model: SentenceTransformer | None = None
_executor = ThreadPoolExecutor(max_workers=4)


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)
    return _model


def _run_search_pair(
    *,
    query: str,
    bm25_index: str,
    vector_index: str,
    top_k_per_index: int,
    min_vector_similarity: float,
    rrf_k: int,
    max_results: int,
) -> list[tuple[str, float]]:
    embedding = get_embedding_model().encode(query).tolist()

    def _bm25() -> list[str]:
        return search_queries.bm25_search(
            query=query, index=bm25_index, top_k=top_k_per_index
        )

    def _vector() -> list[str]:
        return search_queries.vector_search(
            embedding=embedding,
            index=vector_index,
            top_k=top_k_per_index,
            min_similarity=min_vector_similarity,
        )

    bm25_hits = _bm25()
    vector_hits = _vector()
    fused = rrf_fuse(bm25_hits, vector_hits, k=rrf_k)
    return fused[:max_results]


async def _async_search_pair(**kwargs) -> list[tuple[str, float]]:
    loop = asyncio.get_running_loop()

    def _run() -> list[tuple[str, float]]:
        return _run_search_pair(**kwargs)

    return await loop.run_in_executor(_executor, _run)


async def _parallel_retrieval(
    *,
    query: str,
    bm25_index: str,
    vector_index: str,
    top_k_per_index: int,
    min_vector_similarity: float,
) -> tuple[list[str], list[str]]:
    embedding = get_embedding_model().encode(query).tolist()
    loop = asyncio.get_running_loop()
    bm25_task = loop.run_in_executor(
        _executor,
        lambda: search_queries.bm25_search(
            query=query, index=bm25_index, top_k=top_k_per_index
        ),
    )
    vector_task = loop.run_in_executor(
        _executor,
        lambda: search_queries.vector_search(
            embedding=embedding,
            index=vector_index,
            top_k=top_k_per_index,
            min_similarity=min_vector_similarity,
        ),
    )
    bm25_hits, vector_hits = await asyncio.gather(bm25_task, vector_task)
    return bm25_hits, vector_hits


def _build_hits(
    fused: list[tuple[str, float]],
    *,
    framework: str | None,
    openrewrite: bool,
) -> list[dict]:
    ids = [node_id for node_id, _ in fused]
    if openrewrite:
        nodes = search_queries.hydrate_openrewrite_recipes(element_ids=ids)
    else:
        nodes = search_queries.hydrate_nodes(
            element_ids=ids,
            framework=framework,
        )
    by_id = {node["node_id"]: node for node in nodes}
    hits: list[dict] = []
    for node_id, score in fused:
        node = by_id.get(node_id)
        if not node:
            continue
        if openrewrite:
            hits.append(
                {
                    "node_id": node_id,
                    "node_type": "OpenRewriteRecipe",
                    "statement": node.get("description") or "",
                    "score": score,
                    "source_url": "",
                    "action_step": "",
                    "rule_type": "",
                }
            )
        else:
            hits.append(
                {
                    "node_id": node_id,
                    "node_type": node.get("node_type") or "",
                    "statement": node.get("statement") or "",
                    "score": score,
                    "source_url": node.get("source_url") or "",
                    "action_step": node.get("action_step") or "",
                    "rule_type": node.get("rule_type") or "",
                }
            )
    return hits


@mcp.tool()
async def search_migration_knowledge(
    query: str,
    framework: str = "Spring Boot",
    max_results: int = 5,
    rrf_k: int = 60,
    top_k_per_index: int = 50,
    min_vector_similarity: float = 0.30,
) -> dict:
    """Search migration rules and community insights using hybrid BM25 + vector ranking (RRF).

    Returns up to max_results hits ordered by Reciprocal Rank Fusion score. Each hit
    includes: statement, action_step, source_url, node_type, score.
    Vector search requires embeddings; if embeddings were not generated (POPULATE_MIGRATION_EMBEDDINGS=false),
    only BM25 results are returned.
    """
    bm25_hits, vector_hits = await _parallel_retrieval(
        query=query,
        bm25_index="migration_text",
        vector_index="migration_knowledge_vector_mr",
        top_k_per_index=top_k_per_index,
        min_vector_similarity=min_vector_similarity,
    )
    fused = rrf_fuse(bm25_hits, vector_hits, k=rrf_k)[:max_results]
    hits = _build_hits(
        fused,
        framework=framework,
        openrewrite=False,
    )
    return {
        "status": "ok",
        "query": query,
        "hits": hits,
        "top_k": max_results,
    }


@mcp.tool()
async def search_openrewrite_recipes(
    query: str,
    max_results: int = 5,
    only_composite: bool | None = None,
    require_no_params: bool = False,
    rrf_k: int = 60,
    top_k_per_index: int = 50,
    min_vector_similarity: float = 0.30,
) -> dict:
    """Search OpenRewrite recipe descriptions using hybrid BM25 + vector ranking (RRF).

    Returns up to max_results recipe hits with statement and score.
    Note: only_composite and require_no_params filters are accepted but not yet applied —
    all matching recipes are returned regardless of those values (deferred to a future release).
    """
    bm25_hits, vector_hits = await _parallel_retrieval(
        query=query,
        bm25_index="openrewrite_recipe_description",
        vector_index="openrewrite_recipe_vector",
        top_k_per_index=top_k_per_index,
        min_vector_similarity=min_vector_similarity,
    )
    fused = rrf_fuse(bm25_hits, vector_hits, k=rrf_k)[:max_results]
    hits = _build_hits(fused, framework=None, openrewrite=True)
    if only_composite is not None or require_no_params:
        # Filtering deferred to hydration layer when properties are available.
        pass
    return {
        "status": "ok",
        "query": query,
        "hits": hits,
        "top_k": max_results,
    }

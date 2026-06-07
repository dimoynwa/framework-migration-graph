"""Reciprocal rank fusion for hybrid search."""

from __future__ import annotations


def rrf_fuse(
    *ranked_lists: list[str],
    k: int = 60,
    bm25_hits: list[str] | None = None,
    vector_hits: list[str] | None = None,
) -> list[tuple[str, float]]:
    if bm25_hits is not None or vector_hits is not None:
        ranked_lists = tuple(
            hits for hits in (bm25_hits or [], vector_hits or []) if hits is not None
        )
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, node_id in enumerate(ranked, start=1):
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)

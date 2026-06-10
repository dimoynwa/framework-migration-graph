# Research: Community Insight Restructure

**Feature**: `009-community-insight-restructure`
**Date**: 2026-06-09

---

## Q1: Is `FOREACH` over an empty list a safe no-op in Neo4j / Memgraph?

**Decision**: Yes — safe, no guard needed.

**Rationale**: In both Neo4j and Memgraph, `FOREACH (x IN [] | ...)` iterates zero times and executes no operations. Passing an empty list or `null` (with `coalesce($param, [])`) to the `FOREACH` body is the idiomatic Cypher pattern for optional batch writes. The existing `_SUBMIT_INSIGHT` query already uses this pattern for `$affected_classes`, `$affected_properties`, and `$affected_dependencies` — it is proven correct in production.

The same holds for the `MigrationStep` `CREATE` in the new `_SUBMIT_INSIGHT`: the step is always created unconditionally (FR-003 requires at least one step per submission), so no `FOREACH` guard is needed there. The `CREATE (s:MigrationStep {...})` line executes in the same transaction as the `CREATE (r:MigrationRule {...})` line; if either fails, the driver raises an exception and the whole transaction rolls back.

**Alternatives considered**: A separate pre-check query to validate inputs before the write transaction — rejected because the single-transaction atomicity guarantee is preferable, and the FOREACH pattern is already established in this codebase.

---

## Q2: Does `hydrate_nodes` need a fallback for `MigrationRule` nodes with no `REQUIRES_STEP` child?

**Decision**: Yes — `OPTIONAL MATCH` is required, and `coalesce` handles the null case. Pre-existing official rules are unaffected.

**Rationale**: Not all `MigrationRule` nodes have `REQUIRES_STEP` children. Official changelog rules loaded from structured data typically carry a direct `solution` property on the rule node; they may or may not have step children. The hydration Cypher must handle both cases without filtering out either.

The new projection `coalesce(n.solution, first_step.instruction) AS solution` achieves this:

| Node type | `n.solution` | `first_step` | Result |
|-----------|-------------|--------------|--------|
| Official `MigrationRule` (has `solution`) | non-null string | may be null | `n.solution` is returned |
| Official `MigrationRule` (no `solution`) | null | may be null | null (acceptable; no regression from current behaviour) |
| Community insight `MigrationRule` | null (never set) | first `MigrationStep` | `first_step.instruction` |

The `OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)` does not filter out nodes that have no steps — it produces a null `s` row, which `collect(s)[0]` collapses to null for `first_step`. The subsequent `coalesce` then falls back to `n.solution`.

**Removing `include_community_insights`**: The filter `AND ($include_community_insights OR 'MigrationRule' IN labels(n))` was the only mechanism excluding `CommunityInsight` nodes from results. After the restructure there are no `CommunityInsight` nodes to exclude, so removing this filter causes no regression. Pre-existing official `MigrationRule` nodes that lack `REQUIRES_STEP` children remain in results and return whatever `n.solution` currently provides (which may be null for some rule types — this was already true before this spec).

---

## Q3: Does removing `include_community_insights` from `search_migration_knowledge` break any registered MCP client?

**Decision**: No — not a breaking change.

**Rationale**:

1. **Parameter has a default of `True`**: Every existing MCP caller that omits `include_community_insights` already receives the `True` behaviour (all results). Removing the parameter keeps this behaviour permanent.

2. **Current callers that pass `True` explicitly**: They will receive the same result set after the parameter is removed. Their call will still succeed at the MCP transport layer because FastMCP ignores unknown parameters passed by clients (extra parameters in MCP tool calls are dropped, not rejected).

3. **The one caller that passes `False`**: `search_openrewrite_recipes` calls `_build_hits(fused, framework=None, include_community_insights=False, openrewrite=True)` — but this path already uses `openrewrite=True`, which routes to `hydrate_openrewrite_recipes` instead of `hydrate_nodes`. The `include_community_insights=False` argument has no effect on that code path (it is passed to `hydrate_nodes` only when `openrewrite=False`). Removing the parameter from `_build_hits` cleans up dead logic.

4. **Streamlit page**: Calls the tool function by Python import. Once `include_community_insights` is removed from the signature, the page continues to work because it never passed this argument.

**Alternatives considered**: Deprecation period with a warning before removal — rejected because there is no external API versioning contract on this internal MCP server parameter, and the `False` use case is now meaningless (community insights are `MigrationRule` nodes and would appear in results regardless).

---

## Q4: How does `submit_insight` behave when `embedding=None` (embeddings disabled)?

**Decision**: Three guarantees must hold — (a) node written without `embedding` property, (b) vector search skipped, (c) no exception raised. All three are satisfied by the existing code structure after the index-name fix.

**Rationale**:

**(a) Node written without `embedding` property**

The `_SUBMIT_INSIGHT` Cypher includes `embedding: $embedding` in the `CREATE` clause. When `$embedding` is `None`/null, both Neo4j and Memgraph silently drop null-valued properties at write time — the property is simply absent from the created node, not stored as null. No guard, conditional, or two-phase write is needed. This is the same behaviour relied upon by the spec 008 bug fix #3.

**(b) Vector search skipped when `embedding=None`**

`find_near_duplicate` code path when `embedding=None`:

```python
def find_near_duplicate(*, statement, embedding=None):
    exact_id = _find_exact_statement(statement=statement)  # always runs
    if exact_id:
        return exact_id
    if not embedding:          # <-- short-circuits here when embedding is None
        return None            # vector_search and _best_bm25_duplicate are NOT called
    ...
```

Only `_find_exact_statement` runs — an exact-statement lookup against the `rule_statement` fulltext index. The broader `_best_bm25_duplicate` (which uses BM25 scoring + cosine similarity) and `vector_search` are both skipped because both require a non-null embedding. This is intentional: without an embedding, the only reliable duplicate check is exact string equality.

**(c) No exception raised**

`_find_exact_statement` never uses the embedding. The `if not embedding: return None` branch returns before any embedding-dependent code. The subsequent write passes `embedding=None` to the Cypher param, which the driver accepts. No path in `submit_insight()` raises when `embedding=None`.

**Summary of the embedding-disabled call chain**:

```
submit_migration_insight(embedding=None from tools layer)
  → find_near_duplicate(embedding=None)
      → _find_exact_statement(statement)   # BM25 exact match only
      → if not embedding: return None      # no vector, no _best_bm25_duplicate
  → submit_insight writes MigrationRule { ..., no embedding property }
  → returns (insight_id, False)
```

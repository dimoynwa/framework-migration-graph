# Contract: `search_openrewrite_recipes`

**Work-stream**: WS4 — Tool API Alignment
**FR**: FR-011, FR-012
**File**: `migration_oracle/mcp/graph/queries/search.py` (`hydrate_openrewrite_recipes`)

---

## Purpose

Search OpenRewrite recipe descriptions using hybrid BM25 + vector ranking. Supports filtering by parameter presence (`require_no_params`) and composite status (`only_composite`).

---

## Inputs

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | yes | — | Search query text |
| `max_results` | int | no | `5` | Maximum hits to return |
| `only_composite` | bool\|None | no | `None` | `True`: only composite recipes; `False`: only non-composite; `None`: no filter |
| `require_no_params` | bool | no | `False` | `True`: exclude any recipe that has a required `RecipeParam` |
| `rrf_k` | int | no | `60` | RRF fusion constant |
| `top_k_per_index` | int | no | `50` | Candidates retrieved per index before fusion |
| `min_vector_similarity` | float | no | `0.30` | Minimum cosine similarity for vector hits |

---

## Outputs — Success

```json
{
  "status": "ok",
  "query": "<string>",
  "hits": [
    {
      "node_id": "<element-id>",
      "node_type": "OpenRewriteRecipe",
      "statement": "<description-string>",
      "score": <float>
    }
  ],
  "top_k": <integer>
}
```

---

## Filter Corrections (FR-011, FR-012)

Both filters are applied in `hydrate_openrewrite_recipes` in `search.py` via Cypher `WHERE` clauses appended to the base query.

### `only_composite` — corrected property name (FR-012)

**Wrong (current)**:
```cypher
AND coalesce(r.isComposite, false) = true    -- r.isComposite does not exist
AND coalesce(r.isComposite, false) = false
```

**Correct**:
```cypher
AND coalesce(r.composite, false) = true      -- r.composite is the schema property
AND coalesce(r.composite, false) = false
```

The `composite` property is defined in `graph-schema.md` under `OpenRewriteRecipe`. `isComposite` does not exist — it always resolves to `null`, so `coalesce(null, false)` is always `false`, making `only_composite=True` return no results and `only_composite=False` return everything.

### `require_no_params` — corrected to use `HAS_PARAM` subquery (FR-011)

**Wrong (current)**:
```cypher
AND size(coalesce(r.requiredParams, [])) = 0   -- r.requiredParams does not exist
```

`requiredParams` is not a property on `OpenRewriteRecipe`. It does not exist in the schema. `coalesce(null, [])` always returns `[]`, so `size([]) = 0` is always `true` — the filter silently passes every recipe regardless of its required parameters.

**Correct** (use the `EXISTS` subquery form exclusively):
```cypher
AND NOT EXISTS { (r)-[:HAS_PARAM]->(:RecipeParam {required: true}) }
```

This uses the Neo4j 5 inline `EXISTS` pattern, which checks for the presence of a `HAS_PARAM` relationship leading to a `RecipeParam` node with `required=true`. It correctly excludes any recipe that has at least one required parameter. The node-property filter `{required: true}` is on the `RecipeParam` label, not on the relationship.

### Corrected `hydrate_openrewrite_recipes` implementation sketch

```python
def hydrate_openrewrite_recipes(*, element_ids, only_composite=None, require_no_params=False):
    filters = "WHERE elementId(r) IN $ids"
    if only_composite is True:
        filters += " AND coalesce(r.composite, false) = true"                          # ← fix
    elif only_composite is False:
        filters += " AND coalesce(r.composite, false) = false"                         # ← fix
    if require_no_params:
        filters += " AND NOT EXISTS { (r)-[:HAS_PARAM]->(:RecipeParam {required: true}) }"  # ← fix
    cypher = f"""
    MATCH (r:OpenRewriteRecipe) {filters}
    RETURN elementId(r) AS node_id,
           r.recipeId AS recipe_id,
           r.displayName AS display_name,
           r.description AS description,
           r.artifactId AS artifact_id,
           r.groupId AS group_id,
           r.artifactVersion AS artifact_version,
           coalesce(r.composite, false) AS composite,   -- ← fix (was is_composite from isComposite)
           coalesce(r.tags, []) AS tags
    """
```

Note: the returned `composite` field name changes from `is_composite` to `composite` to match the schema property name. Check if any caller reads `is_composite` and update accordingly.

---

## Error Shapes (unchanged)

No tool-level error shapes are defined for this tool — search failures return empty `hits`. This behaviour is unchanged (FR-018).

# Research: MCP Server Bug Fixes

**Spec**: `008-mcp-bug-fixes`
**Date**: 2026-06-09
**Source**: [`ISSUES.md`](ISSUES.md) — discovered during a simulated Spring Boot 3.5.0 → 4.0.0 migration on 2026-06-08.

---

## Issue 1 — `get_pending_steps` crashes with Cypher `SyntaxError`

**Severity**: High  
**File**: `migration_oracle/mcp/graph/queries/context.py`  
**Query constant**: `_GET_PENDING_STEPS` (line 49)

### Root Cause

The final `RETURN` clause includes an aggregation function:

```cypher
RETURN ...,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY
  CASE bs.severity
    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
    WHEN 'medium'   THEN 2 ELSE 3
  END ASC,
  s.stepIndex ASC
```

Once `collect(DISTINCT ...)` is present in the `RETURN`, Neo4j treats the whole clause as an aggregation projection. The non-aggregated column variables (`s`, `bs`) become grouping keys, but Neo4j 5.x enforces that **all variables referenced in `ORDER BY` must be projected in the same `WITH`/`RETURN` clause by name**. `s.stepIndex` and `bs.severity` are referenced in the `ORDER BY` without being explicitly aliased, which triggers:

```
SyntaxError: In a WITH/RETURN with DISTINCT or an aggregation, it is not possible
to access variables declared before the WITH/RETURN: s (line 35, column 3)
```

### Fix

Lift the sort keys into named aliases in the `RETURN` so they are available to `ORDER BY`:

```cypher
RETURN elementId(s) AS step_id,
       s.stepType    AS step_type,
       ...
       collect(DISTINCT elementId(prereq)) AS requires,
       s.stepIndex   AS _step_index,
       CASE bs.severity
         WHEN 'critical' THEN 0 WHEN 'high' THEN 1
         WHEN 'medium'   THEN 2 ELSE 3
       END AS _severity_rank
ORDER BY _severity_rank ASC, _step_index ASC
```

The `_step_index` and `_severity_rank` aliases become part of the returned rows; they should be stripped in the Python layer (or declared as private by convention) if they are not part of the expected output schema.

---

## Issue 2 — `analyze_upgrade_path` and `build_recipe_plan` always return 0 rules

**Severity**: High  
**File**: `migration_oracle/mcp/graph/queries/upgrade.py`  
**Query constants**: `_ANALYZE_UPGRADE_PATH` (line 9), `_BUILD_RECIPE_PLAN` (line 92)

### Root Cause

Direct Cypher inspection of the graph confirms:

```cypher
MATCH (mr:MigrationRule)
RETURN mr.from_version, mr.to_version, count(*)
// → null | null | 630
```

`MigrationRule` nodes have **no `from_version` or `to_version` properties**. Version association is stored as a relationship:

```
(:Version {version:'4.0.0', framework:'Spring Boot'}) -[:INCLUDES_RULE]-> (:MigrationRule)
```

The `_ANALYZE_UPGRADE_PATH` query does traverse `INCLUDES_RULE` (`OPTIONAL MATCH (v)-[:INCLUDES_RULE|DISCOVERED_IN]-(rule)`), but the query has a `WHERE` filter on `rule.entityClassification`:

```cypher
WHERE rule IS NULL
   OR (
       ...
       AND
       (rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )
```

The default `$classification` list is `["actionable", "incomplete"]`. If stored `entityClassification` values on the majority of `MigrationRule` nodes differ from these literals (e.g. `"breaking_change"`, `"config"`, or any other value), the filter silently discards every rule. A secondary factor: the undirected relationship match `(v)-[:INCLUDES_RULE|DISCOVERED_IN]-(rule)` may return `CommunityInsight` nodes (which traverse `DISCOVERED_IN`) mixed in with `MigrationRule` nodes; those community nodes have no `statement` property and are filtered by the final `[x IN raw_rules WHERE x.statement IS NOT NULL]`, but if rules are also missing `statement` for any reason, they vanish too.

`_BUILD_RECIPE_PLAN` uses a directed `MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)` which is correct, but the same `entityClassification` filter applies:

```cypher
WHERE rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification
```

### Fix

1. **Widen the default `classification` list** in both Python functions (`analyze_upgrade_path`, `build_recipe_plan`) to `None` (no filter), or include `None` as a sentinel meaning "accept all":

```python
# before
classes = classification or ["actionable", "incomplete"]
# after
classes = classification or []  # empty → no filter applied in Cypher
```

2. **Update the Cypher `WHERE`** to treat an empty list as "accept all":

```cypher
WHERE rule IS NULL
   OR (
       ...
       AND
       (size($classification) = 0
          OR rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )
```

3. **Fix the undirected relationship** in `_ANALYZE_UPGRADE_PATH` to be explicit:

```cypher
-- before:
OPTIONAL MATCH (v)-[:INCLUDES_RULE|DISCOVERED_IN]-(rule)
-- after:
OPTIONAL MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
```

This removes ambiguity and prevents `CommunityInsight` nodes from polluting the rule set.

---

## Issue 3 — `submit_migration_insight` fails when embeddings are disabled

**Severity**: Medium  
**File**: `migration_oracle/mcp/tools/community.py` (line 32)

### Root Cause

The tool calls `get_embedding_model().encode(statement).tolist()` unconditionally before writing the insight. When `POPULATE_MIGRATION_EMBEDDINGS=false` the embedding model may not be initialised or may return `None`, causing the `tolist()` call to fail. The exception is caught somewhere upstream and surfaced as a generic `"Failed to create CommunityInsight"`.

The `community_queries.submit_insight` function in `graph/queries/community.py` (line 143) accepts `embedding: list[float] | None = None` — so the query layer is already prepared for a missing embedding. The bug is in the tool handler which does not gate the `encode()` call.

The near-duplicate detection in `find_near_duplicate` (line 122) also gracefully skips when `embedding` is `None`:

```python
if not embedding:
    return None
```

### Fix

Check whether embeddings are available before encoding:

```python
@mcp.tool()
def submit_migration_insight(...) -> dict:
    embedding: list[float] | None = None
    try:
        embedding = get_embedding_model().encode(statement).tolist()
    except Exception:
        pass  # embeddings disabled or unavailable; duplicate check uses BM25 only
    insight_id, is_duplicate = community_queries.submit_insight(
        ...
        embedding=embedding,
    )
    ...
```

Alternatively, expose a helper `embeddings_available() -> bool` in `search.py` that checks the config flag, and gate the encode call on that.

---

## Issue 4 — `search_openrewrite_recipes` returns 0 results despite 333 recipes in the graph

**Severity**: Medium  
**File**: `migration_oracle/mcp/tools/search.py` (line 183), `migration_oracle/graph/indexes.py`

### Root Cause

The tool calls `_parallel_retrieval` with `bm25_index="openrewrite_recipe_description"`. The BM25 leg calls:

```python
search_queries.bm25_search(query=query, index="openrewrite_recipe_description", top_k=top_k_per_index)
```

Which executes:

```cypher
CALL db.index.fulltext.queryNodes($index, $search_text, {limit: $top_k})
```

However, `graph/indexes.py` defines only two fulltext indexes:

```python
"CREATE FULLTEXT INDEX rule_statement IF NOT EXISTS FOR (r:MigrationRule) ON EACH [r.statement]",
"CREATE FULLTEXT INDEX step_instruction IF NOT EXISTS FOR (s:MigrationStep) ON EACH [s.instruction, s.summary]",
```

There is no `openrewrite_recipe_description` fulltext index. The `bm25_search` function catches `ClientError` and returns `[]` silently. The vector index `openrewrite_recipe_vector` is also empty because `POPULATE_MIGRATION_EMBEDDINGS=false`. Both legs of the RRF return empty lists, so no recipes are surfaced.

A similar gap exists for the `migration_text` BM25 index used by `search_migration_knowledge`: it is also missing from `indexes.py`.

### Fix

Add the missing fulltext indexes to `graph/indexes.py`:

```python
"CREATE FULLTEXT INDEX migration_text IF NOT EXISTS "
"FOR (n:MigrationRule|CommunityInsight) ON EACH [n.statement, n.reason, n.solution]",

"CREATE FULLTEXT INDEX openrewrite_recipe_description IF NOT EXISTS "
"FOR (r:OpenRewriteRecipe) ON EACH [r.description, r.displayName]",
```

These indexes must be created before the BM25 leg of any hybrid search can return results. The `ensure_indexes` call at server startup will apply them idempotently.

---

## Issue 5 — `Class` and `ApplicationProperty` entity nodes missing `framework` property

**Severity**: Medium  
**File**: `migration_oracle/mcp/graph/queries/deprecation.py`

### Root Cause

`resolve_deprecation` queries:

```cypher
MATCH (e)
WHERE (e:Class OR e:ApplicationProperty OR e:Dependency) AND e.name = $entity_name
OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
```

Direct Cypher confirms:

```cypher
MATCH (c:Class) WHERE c.framework = 'Spring Boot' RETURN count(c)
// → 0
```

The `Class` and `ApplicationProperty` nodes stored in the graph for Spring Boot 4.0.0 were **not given a `framework` property** during ingestion. The query still works for the `Version {framework: $framework}` filter on the relationship traversal (`DEPRECATED_IN`, `REMOVED_IN`, `INTRODUCED_IN`), so the tool should technically return results — unless the `MATCH` for the base entity `(e)` with just `e.name = $entity_name` is too broad and `OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})` finds no version, leading to `depV = NULL`.

If no version-framework relationship exists (because `Class` nodes have no `DEPRECATED_IN` edge pointing to the correct `Version {framework:'Spring Boot'}`), then `deprecated_in`, `removed_in`, and `replaced_by` all return `null`, and the tool returns `status: "not_found"`.

The underlying issue is that entity extraction during ingestion either:
- Did not write the `DEPRECATED_IN` / `REMOVED_IN` relationships linking the Spring Boot 4.0.0 `Class` entities back to the `Version` node, OR
- Wrote entities under a different label (e.g. `Entity` instead of `Class`).

### Fix

**Short-term (query-level)**: Make `resolve_deprecation` also search by traversing the `Version` node:

```cypher
MATCH (v:Version {framework: $framework})
OPTIONAL MATCH (v)-[:REMOVES|INTRODUCES]->(e)
  WHERE (e:Class OR e:ApplicationProperty) AND e.name = $entity_name
...
```

**Long-term (data-level)**: Fix the ingestion pipeline to write `framework` onto `Class` and `ApplicationProperty` nodes, and to write the `DEPRECATED_IN` / `REMOVED_IN` relationships for Spring Boot 4.x entities.

The spec covers the query-level short-term fix only. The ingestion pipeline fix is a separate data-quality concern.

---

## Issue 6 — `analyze_upgrade_path` ignores exact patch versions

**Severity**: Low  
**File**: `migration_oracle/mcp/tools/upgrade.py`, `migration_oracle/models/graph.py`

### Root Cause

`sortable_version("3.5.12")` returns `3_005_012`. The graph stores versions at `major.minor.0` granularity, so `Version {version: '3.5.0'}` has `sortableVersion = 3_005_000`. The query uses `>` and `<=` on `sortableVersion`, so:

- `3.5.12` → `3_005_012` as `current_version_sortable`
- Query: `v.sortableVersion > 3_005_012 AND v.sortableVersion <= $target`
- `Version {version: '3.5.0', sortableVersion: 3_005_000}` fails this check (3_005_000 > 3_005_012 is FALSE).

If `"3.5.12"` is passed as `current_version` and `"4.0.0"` as `target_version`, the Version node `3.5.0` is skipped and there is no error — the tool silently returns whatever versions lie between `3.5.12` and `4.0.0` by sortable value.

In this specific test case (`3.5.0 → 4.0.0`), passing `"3.5.0"` works but `"3.5.12"` would not find `3.5.x` rules (none exist anyway since the graph only stores `3.5.0`). The more dangerous case is multi-hop migrations where intermediate patch versions cause Version nodes to be skipped.

### Fix

Normalise input versions to `major.minor.0` before computing `sortable_version`:

```python
def _normalise_to_minor(version: str) -> str:
    parts = version.split(".")
    return f"{parts[0]}.{parts[1]}.0"
```

Apply in `analyze_upgrade_path` and `build_recipe_plan`:

```python
current_sv = sortable_version(_normalise_to_minor(current_version))
target_sv  = sortable_version(_normalise_to_minor(target_version))
```

Also add a note to the tool's docstring (already added in spec 005a) to state that only `major.minor.0` is stored.

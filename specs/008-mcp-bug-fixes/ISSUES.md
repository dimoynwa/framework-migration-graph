# MCP Server — Known Issues

Discovered during a simulated Spring Boot 3.5.0 → 4.0.0 migration on 2026-06-08.
All issues were reproduced via direct JSON-RPC calls to `http://localhost:8080/sse`.

---

## Issue 1 — `get_pending_steps` crashes with a Cypher `SyntaxError`

**Severity:** High — the tool is completely unusable.

**Tool:** `get_pending_steps`

**Error returned:**
```
Error executing tool get_pending_steps:
{neo4j_code: Neo.ClientError.Statement.SyntaxError}
{message: In a WITH/RETURN with DISTINCT or an aggregation, it is not possible to access
variables declared before the WITH/RETURN: s (line 35, column 3 (offset: 1388))
"  s.stepIndex ASC"
   ^}
{gql_status: 42001}
```

**Root cause:** The generated Cypher query aggregates or uses `DISTINCT` in a `WITH` clause on line ~34, which drops the `s` binding (the `MigrationStep` node). The subsequent `ORDER BY s.stepIndex ASC` on line 35 references `s` after it has gone out of scope.

**Likely fix:** Either include `s.stepIndex` in the `WITH` projection before the `ORDER BY`, or restructure the query so that sorting happens before the aggregation step, e.g.:
```cypher
// Instead of:
WITH DISTINCT ..., collect(s) AS steps
ORDER BY s.stepIndex  -- s is gone here

// Do:
WITH ..., s
ORDER BY s.stepIndex
WITH collect(s) AS steps
```

**Impact:** Developers cannot retrieve their step queue after creating a migration context, breaking the core context-driven workflow.

---

## Issue 2 — `analyze_upgrade_path` and `build_recipe_plan` always return 0 rules

**Severity:** High — the two most important planning tools return empty results.

**Tools:** `analyze_upgrade_path`, `build_recipe_plan`

**Reproduction:**
```json
{
  "name": "analyze_upgrade_path",
  "arguments": {
    "framework": "Spring Boot",
    "current_version": "3.5.0",
    "target_version": "4.0.0"
  }
}
// → { "rules": [], "lifecycle_alerts": [] }
```

**Root cause:** Both tools filter `MigrationRule` nodes by comparing `mr.from_version` / `mr.to_version` properties against the supplied version range. A direct Cypher audit shows those properties are `null` on every `MigrationRule` node in the graph:

```cypher
MATCH (mr:MigrationRule)
RETURN mr.from_version, mr.to_version, count(*)
// → null | null | 630
```

Rules are not stored with version range properties; they are connected to `Version` nodes via `INCLUDES_RULE` relationships:

```
(:Version {version:'4.0.0', framework:'Spring Boot'}) -[:INCLUDES_RULE]-> (:MigrationRule)
```

The version 4.0.0 node has 54 rules attached this way. The query never walks this edge.

**Likely fix:** Replace the property-based filter with a relationship traversal:
```cypher
MATCH (v:Version {version: $target_version, framework: $framework})
      -[:INCLUDES_RULE]->(mr:MigrationRule)
```

**Impact:** Developers get no migration guidance from the two tools that are the front door to the oracle. Everything downstream (recipe plan, scope-tier analysis) is also empty as a result.

---

## Issue 3 — `submit_migration_insight` fails when embeddings are disabled

**Severity:** Medium — community knowledge contribution is blocked.

**Tool:** `submit_migration_insight`

**Error returned:**
```
Error executing tool submit_migration_insight: Failed to create CommunityInsight
```

**Root cause:** The tool's near-duplicate detection calls the embedding model to compute a cosine similarity score before writing the node. When `POPULATE_MIGRATION_EMBEDDINGS=false` (the current runtime state — confirmed because `search_migration_knowledge` returns uniform BM25-only scores), the embedding call fails or returns `None`, and the tool aborts rather than falling back.

**Likely fix:** Gate the duplicate check on whether embeddings are available. When they are not, either skip the check entirely or fall back to a BM25/string-similarity dedup:
```python
if embedding_available:
    # run cosine similarity check
else:
    # skip or use fuzzy string match
```

**Impact:** No community insights can be written to the graph. The `get_community_insights`, `vote_insight`, and `verify_insight` tools are all vacuously correct (they return empty lists / succeed on no-ops) but the ecosystem never grows any community knowledge.

---

## Issue 4 — `search_openrewrite_recipes` returns 0 results despite 333 recipes in the graph

**Severity:** Medium — automation suggestions are unreachable.

**Tool:** `search_openrewrite_recipes`

**Reproduction:**
```json
{
  "name": "search_openrewrite_recipes",
  "arguments": { "query": "Spring Boot upgrade 4.0", "max_results": 5 }
}
// → { "hits": [] }
```

**Direct Cypher confirms data exists:**
```cypher
MATCH (r:OpenRewriteRecipe) RETURN count(r)
// → 333
```

**Root cause:** The hybrid BM25 + vector search (RRF) for recipes requires at least one of the two indices to return results. With `POPULATE_MIGRATION_EMBEDDINGS=false` the vector index is empty. If the BM25 index was also not populated (or uses a different node property than the search queries), both legs of the RRF return zero hits and the tool surfaces nothing.

**Likely fix:** Ensure BM25 full-text indexing is built on the recipe node's text property (likely `description` or `name`) independently of the embedding pipeline. The BM25 leg of RRF should work without embeddings.

**Impact:** Developers cannot discover scriptable OpenRewrite automation for their migration, even though a rich recipe catalogue exists in the graph.

---

## Issue 5 — Spring Boot `Class` and `ApplicationProperty` entity nodes are missing

**Severity:** Medium — entity-level lookup tools are non-functional for Spring Boot.

**Tools:** `resolve_deprecation`, `entity_evolution`

**Reproduction:**
```json
{
  "name": "resolve_deprecation",
  "arguments": { "entity_name": "EnvironmentPostProcessor", "framework": "Spring Boot" }
}
// → { "status": "not_found", "deprecated_in": null, "removed_in": null, "replaced_by": null }
```

**Direct Cypher confirms the gap:**
```cypher
MATCH (c:Class) WHERE c.framework = 'Spring Boot' RETURN count(c)
// → 0
```

The Spring Boot 4.0.0 `Version` node does have `REMOVES` / `INTRODUCES` / `REMOVED_IN` / `INTRODUCED_IN` relationships to `Class` and `ApplicationProperty` nodes (13 and 16 respectively, per schema inspection), but those nodes do not carry a `framework` property — or the `Class` nodes are not populated at all for this framework.

The migration guide text confirms real deprecations exist:
- `org.springframework.boot.env.EnvironmentPostProcessor` → deprecated in 4.0, replaced by `org.springframework.context.env.EnvironmentPostProcessor`
- `org.springframework.boot.autoconfigure.thread` package moved

**Likely fix:** Ensure the entity extraction pipeline writes `framework` property onto `Class` / `ApplicationProperty` nodes during ingestion, and that `resolve_deprecation` queries by `Version` relationship if the `framework` property is absent.

**Impact:** Developers cannot look up whether a specific class or property they use has been deprecated or removed, which is one of the highest-value lookups during a migration.

---

## Issue 6 — `analyze_upgrade_path` version range ignores exact patch versions

**Severity:** Low — cosmetic/UX, but worth noting.

**Tool:** `analyze_upgrade_path`

**Context:** The tool accepts `current_version: "3.5.12"` and `target_version: "4.0.6"` but the graph stores versions at `major.minor.0` granularity (`3.5.0`, `4.0.0`). There is no normalisation or fuzzy matching — passing `3.5.12` returns nothing, passing `3.5.0` would return results (if Issue 2 were fixed).

**Likely fix:** Normalise input versions to `major.minor.0` before querying, or document clearly that only `major.minor.0` strings are accepted. Alternatively, match on `sortableVersion` ranges using a floor/ceiling approach.

**Impact:** Developers who supply real product version strings (e.g. `3.5.12`) get empty results with no explanation, making the tool appear broken rather than a version-format mismatch.

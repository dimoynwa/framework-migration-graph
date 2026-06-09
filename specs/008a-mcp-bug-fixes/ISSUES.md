# MCP Server — Live Probe Issues

Probe date: 2026-06-09
Server: http://localhost:8080/sse
Fake project: payment-gateway-service (Spring Boot 3.5.0 → 4.0.0)

## Summary

| # | Tool | Category | Severity | One-line description |
|---|---|---|---|---|
| 1 | `analyze_upgrade_path`, `build_recipe_plan` | `query-logic` | High | General rules (no entity links) silently excluded when `user_entities` is provided |
| 2 | `submit_migration_insight` | `embedding-dep` | High | Submission fails with "Failed to create CommunityInsight" — write blocked when embedding unavailable |
| 3 | `resolve_deprecation`, `entity_evolution` | `missing-data` | Medium | Always returns `not_found` — no `Class` nodes with `framework='Spring Boot'` in graph |
| 4 | `search_openrewrite_recipes` | `index-missing` | Medium | 0 hits despite 333 `OpenRewriteRecipe` nodes — nodes lack `description`/`displayName` properties |
| 5 | `search_migration_knowledge` | `embedding-dep` | Low | First query after server start times out (cold model-loading delay) |

---

## Issue 1 — General migration rules excluded when user_entities provided

**Severity:** High
**Category:** `query-logic`
**Tool(s):** `analyze_upgrade_path`, `build_recipe_plan`

**Error / symptom observed:**
`analyze_upgrade_path` called with `user_entities=["WebSecurityConfigurerAdapter","HttpSecurity","spring.datasource.url","spring.jpa.hibernate.ddl-auto","RestTemplate"]` returns `rules: []` and `lifecycle_alerts: []`. Called without `user_entities` (empty list), the same version range returns 50 rules.

**Root cause:**
Cypher probe confirms 54 `MigrationRule` nodes are reachable from `Version {version:'4.0.0'}` via `INCLUDES_RULE`. Of these, 16 have **no** `AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY` edges (general rules). The remaining 38 have entity edges but their affected entities (e.g. `spring.jackson.use-jackson2-defaults`, `spring.http.codecs.max-in-memory-size`) do not contain any of the 5 probe entity strings.

The WHERE clause in `_ANALYZE_UPGRADE_PATH` (and `_BUILD_RECIPE_PLAN`) filters rules via:
```cypher
(size($user_entities) = 0
   OR ANY(e IN affected_entities WHERE ANY(u IN $user_entities WHERE toLower(e) CONTAINS toLower(u))))
```
When `user_entities` is non-empty, rules with `affected_entities = []` always fail this check and are silently dropped. This means every "general" migration rule — one that applies to all projects regardless of scanned entities — is excluded whenever a developer provides their project's entity list.

**Likely fix:**
Add a guard to pass through rules that have no entity links even when `user_entities` is provided:
```cypher
(size($user_entities) = 0
   OR size(affected_entities) = 0   -- ← include general rules unconditionally
   OR ANY(e IN affected_entities WHERE ANY(u IN $user_entities WHERE toLower(e) CONTAINS toLower(u))))
```
Apply the same fix to `_BUILD_RECIPE_PLAN`.

**Impact:**
A developer scanning their project and passing `user_entities` receives an empty migration plan despite 54 applicable rules existing in the graph. The tool looks broken or the graph looks unpopulated. This is the most impactful usability issue found in this probe.

---

## Issue 2 — submit_migration_insight fails with "Failed to create CommunityInsight"

**Severity:** High
**Category:** `embedding-dep`
**Tool(s):** `submit_migration_insight`

**Error / symptom observed:**
```
Error executing tool submit_migration_insight: Failed to create CommunityInsight
```
`get_community_insights` returns 0 insights, confirming no prior write succeeded. The write fails unconditionally — even the first submission.

**Root cause:**
The probe does not have the `sentence-transformers` model loaded in the server process. The `submit_insight` query layer likely performs a vector-similarity dedup check that requires an embedding vector. When `embedding=None` is passed (because encoding failed or the model is not loaded), the Cypher write query fails. The error message "Failed to create CommunityInsight" is raised in the query layer when the write returns no result.

This is distinct from the tool-layer fix applied in spec-008 (guarding the `encode()` call with try/except). The query layer itself still fails when `embedding=None` is passed through, because the similarity check or `MERGE`/`CREATE` logic cannot proceed without a vector.

**Likely fix:**
In `community_queries.submit_insight`, add a guard: if `embedding is None`, skip the vector-similarity dedup step and proceed directly to the `CREATE` query without the vector property. The dedup check should be optional, not a hard dependency for the write path.

**Impact:**
Community knowledge cannot be submitted from any deployment where the sentence-transformers model is not pre-loaded (e.g. Docker containers without the model baked in, or cold-start environments). The feature is completely non-functional in those environments.

---

## Issue 3 — resolve_deprecation / entity_evolution always return not_found

**Severity:** Medium
**Category:** `missing-data`
**Tool(s):** `resolve_deprecation`, `entity_evolution`

**Error / symptom observed:**
```
resolve_deprecation(entity_name="EnvironmentPostProcessor") → status='not_found'
entity_evolution(entity_name="EnvironmentPostProcessor") → chain=[]
```

**Root cause:**
Cypher probe `MATCH (c:Class) WHERE c.framework = 'Spring Boot' RETURN count(c)` returns 0. No `Class` nodes with `framework='Spring Boot'` exist in the graph. The entity extraction pipeline (which produces `Class`, `Interface`, etc. nodes and their `DEPRECATED_IN`/`REPLACED_BY` relationships) has not been run against the Spring Boot changelog data.

Note: even if the pipeline had run, short names like `EnvironmentPostProcessor` would need to be passed as their fully-qualified form (e.g. `org.springframework.boot.env.EnvironmentPostProcessor`) as the tool description now documents. The sample entity names observed in graph are FQNs.

**Likely fix:**
Run the entity extraction pipeline for Spring Boot. This is a data-pipeline issue, not a server-code bug. The tools themselves work correctly — they fail gracefully with `status='not_found'` as designed.

**Impact:**
Any agent trying to trace deprecation chains or entity replacement paths for Spring Boot entities will always get `not_found`. The deprecation tracking feature is non-functional for this framework.

---

## Issue 4 — search_openrewrite_recipes returns 0 hits despite 333 nodes

**Severity:** Medium
**Category:** `index-missing`
**Tool(s):** `search_openrewrite_recipes`

**Error / symptom observed:**
`search_openrewrite_recipes(query="Spring Boot upgrade 4.0")` returns `hits: []`. Cypher probe confirms `MATCH (r:OpenRewriteRecipe) RETURN count(r)` = 333.

**Root cause:**
The fulltext index `openrewrite_recipe_description` is defined over `[r.description, r.displayName]` on `OpenRewriteRecipe` nodes. However, the 333 nodes in the graph were created with only `recipeId` populated — `description` and `displayName` properties are absent (stub nodes from the data pipeline). BM25 has no text to index, so all queries return 0 results.

**Likely fix:**
The recipe data ingestion pipeline needs to populate `description` and `displayName` from the OpenRewrite recipe registry (YAML/JSON sources). This is a data-pipeline issue. Once properties are populated, the existing fulltext index will pick them up automatically on the next index refresh.

**Impact:**
The `search_openrewrite_recipes` tool is completely non-functional. Developers and AI agents cannot discover applicable OpenRewrite recipes for their migration, blocking the auto-migration workflow.

---

## Issue 5 — First search_migration_knowledge call times out (cold model load)

**Severity:** Low
**Category:** `embedding-dep`
**Tool(s):** `search_migration_knowledge`

**Error / symptom observed:**
The first call to `search_migration_knowledge` after server start returned `no_response` (request completed but SSE response not received within 4-second window). A retry 8 seconds later returned 3 hits with hybrid scores. Queries 2–5 in the same session all succeeded within the wait window.

**Root cause:**
The sentence-transformers model (`all-mpnet-base-v2`) is loaded lazily on first use. The first `encode()` call triggers disk read and model initialisation, which takes longer than the probe's 4-second SSE polling timeout. No error is raised — the response simply arrives after the client stopped waiting.

**Likely fix:**
Eagerly load the embedding model at server startup (warm-up call on `__main__` or in an `@app.on_event("startup")` handler). This eliminates the first-call latency spike. Alternatively, document the cold-start delay and recommend a warm-up ping before serving real traffic.

**Impact:**
The first search query from any new client session may appear to fail (no response returned). Agents relying on the first search result will silently miss it and may incorrectly conclude the search tool is broken.

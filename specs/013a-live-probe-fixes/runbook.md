# Runbook — `013a-live-probe-fixes`

## 1. OpenRewrite Recipe Ingestion (SC-011 / LP-003)

Run this after deploying the branch. Steps 1–5 must be executed against the target Neo4j instance.

```bash
# 1. Run ingestion against target Neo4j
python -m migration_oracle.scripts.ingest_openrewrite_recipes \
  --neo4j-uri "$NEO4J_URI" --neo4j-user "$NEO4J_USER" --neo4j-password "$NEO4J_PASSWORD"

# 2. Rebuild the full-text index
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
  "DROP INDEX openrewrite_recipe_description IF EXISTS;
   CALL db.index.fulltext.createNodeIndex(
     'openrewrite_recipe_description', ['OpenRewriteRecipe'], ['description']
   );"

# 3. Verify recipe count > 0
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
  "MATCH (r:OpenRewriteRecipe) RETURN count(r) AS recipe_count;"

# 4. Verify build_recipe_plan reports recipes_loaded=true
#    Call via MCP client: build_recipe_plan(current_version="3.5.0", target_version="4.0.0")
#    Expect: diagnostics.recipes_loaded=true, diagnostics.recipe_count > 0

# 5. Verify search_openrewrite_recipes returns >= 1 hit
#    Call via MCP client: search_openrewrite_recipes(query="jakarta persistence")
#    Expect: hits list non-empty
```

---

## 2. One-time zombie context cleanup

If any project accumulated a `MigrationContext` created under pre-013 normalisation
(`fromVersion="3.5.0"`, `toVersion="4.0.0"` when the caller passed `3.5.12 → 4.0.6`),
delete it before the first live replay:

```cypher
-- Identify zombie contexts (review before deleting)
MATCH (ctx:MigrationContext {projectId: "paysafe-wallet-switch"})
WHERE ctx.fromVersion = "3.5.0" AND ctx.toVersion = "4.0.0"
RETURN elementId(ctx), ctx.fromVersion, ctx.toVersion, ctx.status, ctx.createdAt;

-- Delete confirmed zombies (run only after review)
MATCH (ctx:MigrationContext {projectId: "paysafe-wallet-switch"})
WHERE ctx.fromVersion = "3.5.0" AND ctx.toVersion = "4.0.0"
DETACH DELETE ctx;
```

The zombie guard in `create_migration_context` (T005B) will automatically handle any zombie that
was not cleaned up manually — it detects mismatched `UPGRADES_FROM`/`UPGRADES_TO` edges on resume
and re-creates the context. This one-time query just avoids the warning log on the first call.

---

## 3. Build provenance verification (CC-1 gate)

After deploying the branch, verify the live server reports the correct build:

```bash
# Call get_graph_schema and check server_build
curl -s http://localhost:8080/sse ...  # or use MCP client

# Expected:
# server_build.branch = "013a-live-probe-fixes"
# server_build.feature_tags includes "013a-live-probe-fixes" and "013-real-run-hardening"
# server_build.git_sha matches the deployed artifact SHA
```

Set these env vars in the deploy pipeline before starting the server:

```bash
export GIT_SHA=$(git rev-parse HEAD)
export GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
export FEATURE_TAGS="013-real-run-hardening,013a-live-probe-fixes"
```

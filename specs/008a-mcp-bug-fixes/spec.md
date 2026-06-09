# Feature Specification: MCP Server Bug Fixes (Round 2)

**Feature Branch**: `008a-mcp-bug-fixes`
**Created**: 2026-06-09
**Status**: Draft
**Research**: See [research.md](research.md) for per-issue root-cause analysis.
**Source**: [`ISSUES.md`](../../ISSUES.md) — 4 bugs fixed from live black-box probe (Spring Boot 3.5.0 → 4.0.0).

---

## Scope

Fix 4 bugs found by the live MCP probe. No new features, no tool renames. Fix 4 adds `framework` annotation to entity nodes (non-breaking — uniqueness key unchanged).

| # | Issue | Severity | Category | File(s) |
|---|-------|----------|----------|---------|
| 1 | General rules excluded when `user_entities` provided | High | `query-logic` | `mcp/graph/queries/upgrade.py` |
| 2 | `submit_migration_insight` fails with "Failed to create CommunityInsight" | High | `version-format` | `mcp/tools/community.py` |
| 3 | First search query after cold start times out | Low | `embedding-dep` | `mcp/server.py` |
| 4 | Class/ApplicationProperty/Dependency nodes missing `framework` property | Medium | `missing-data` | `pipeline/populator.py`, `mcp/graph/queries/community.py` |

Issue 5 from the probe (OpenRewriteRecipe stubs missing `description`/`displayName`) remains Out of Scope — data-pipeline gap requiring recipe registry integration.

---

## Fix 1 — General rules excluded when `user_entities` is provided

**File**: `migration_oracle/mcp/graph/queries/upgrade.py`

### Root cause

`_ANALYZE_UPGRADE_PATH` collects `affected_entities` via `OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)`. Rules with **no** entity relationships end up with `affected_entities = []`. The WHERE filter is:

```cypher
size($user_entities) = 0
   OR ANY(e IN affected_entities WHERE ANY(u IN $user_entities WHERE toLower(e) CONTAINS toLower(u)))
```

When `user_entities` is non-empty, `ANY(e IN [] ...)` is always `false`, so every general migration rule is silently dropped. Live probe confirmed: 50 rules return with `user_entities=[]`, 0 rules with 5 entities provided — despite 16 of the 54 rules having no entity links at all.

The same logic is present in `_BUILD_RECIPE_PLAN`.

### Change — `_ANALYZE_UPGRADE_PATH`

In the WHERE clause that filters `rule`, add `OR size(affected_entities) = 0` so rules without entity links are always included:

Replace:

```cypher
WHERE rule IS NULL
   OR (
       (size($user_entities) = 0
          OR ANY(e IN affected_entities
                   WHERE ANY(u IN $user_entities
                              WHERE toLower(e) CONTAINS toLower(u))))
       AND
       (size($classification) = 0
          OR rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )
```

With:

```cypher
WHERE rule IS NULL
   OR (
       (size($user_entities) = 0
          OR size(affected_entities) = 0
          OR ANY(e IN affected_entities
                   WHERE ANY(u IN $user_entities
                              WHERE toLower(e) CONTAINS toLower(u))))
       AND
       (size($classification) = 0
          OR rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )
```

### Change — `_BUILD_RECIPE_PLAN`

Same guard for the entity filter in `_BUILD_RECIPE_PLAN`:

Replace:

```cypher
WHERE size($user_entities) = 0
   OR ANY(e IN affected_entities
            WHERE ANY(u IN $user_entities
                       WHERE toLower(e) CONTAINS toLower(u)))
```

With:

```cypher
WHERE size($user_entities) = 0
   OR size(affected_entities) = 0
   OR ANY(e IN affected_entities
            WHERE ANY(u IN $user_entities
                       WHERE toLower(e) CONTAINS toLower(u)))
```

---

## Fix 2 — `submit_migration_insight` fails with version format mismatch

**File**: `migration_oracle/mcp/tools/community.py`

### Root cause

`_SUBMIT_INSIGHT` opens with:

```cypher
MATCH (v:Version {framework: $framework, version: $version})
```

This requires an **exact string match** on `version`. The graph stores versions as `"4.0.0"` but callers naturally pass `"4.0"` (as the probe did with `spring_boot_version="4.0"`). The `MATCH` returns zero rows, `session.run(...).single()` returns `None`, and `submit_insight` raises `RuntimeError("Failed to create CommunityInsight")`.

The error surface in `community.py` makes it look like an embedding failure, but the actual cause is a version-string mismatch one layer down.

### Change — normalise `spring_boot_version` in the tool handler

Add a `_normalise_version` helper in `migration_oracle/mcp/tools/community.py` and apply it before calling `community_queries.submit_insight`. The helper pads short versions to the `major.minor.0` form the graph uses:

```python
def _normalise_version(v: str) -> str:
    """Pad 'major' → 'major.0.0' and 'major.minor' → 'major.minor.0'."""
    parts = v.split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])
```

In `submit_migration_insight`, apply it to `spring_boot_version` before passing to the query layer:

```python
insight_id, is_duplicate = community_queries.submit_insight(
    statement=statement,
    framework=framework,
    version=_normalise_version(spring_boot_version),   # ← normalise here
    ...
)
```

No changes are required in `community_queries.submit_insight` or `_SUBMIT_INSIGHT`.

---

---

## Fix 3 — Eager embedding model warm-up on server start

**File**: `migration_oracle/mcp/server.py`

### Root cause

`get_embedding_model()` in `search.py` is a lazy singleton — the `SentenceTransformer` object is created on the first call to `encode()`, which happens inside the first real tool call. Loading the model from disk takes 2–5 seconds; during that time the SSE client receives no response and the call times out with `no_response`.

The `startup()` function already performs eager setup for Neo4j and indexes. The embedding model is not included.

### Change

Add a warm-up call at the end of `startup()`. Wrap it in a try/except so a missing `sentence-transformers` package (`POPULATE_MIGRATION_EMBEDDINGS=false` deployments) does not prevent the server from starting:

```python
def startup() -> None:
    """Ordered startup: config (import time) → connectivity → indexes → model warm-up."""
    driver = get_driver()
    with driver.session() as session:
        session.run("RETURN 1").single()
    ensure_indexes(driver)
    try:
        from migration_oracle.mcp.tools.search import get_embedding_model
        get_embedding_model()
        logger.info("Embedding model warm-up complete")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Embedding model warm-up skipped: %s", exc)
    logger.info(
        "PaysafeMigrationOracle ready — transport=%s",
        config.MCP_TRANSPORT,
    )
```

The import is deferred inside the function to avoid a module-level import cycle (search imports from tools which are registered after server module load).

---

## Fix 4 — Annotate entity nodes with `framework` property in the pipeline

**Files**:
- `migration_oracle/pipeline/populator.py`
- `migration_oracle/mcp/graph/queries/community.py`

### Root cause

`Class`, `ApplicationProperty`, and `Dependency` nodes are created via `MERGE (e:{label} {name: $name})` — only `name` is in the MERGE key. The `framework_display` value is available in `_write_affected_entity` (it's passed as a parameter) but is never SET on the node. The result: `MATCH (c:Class) WHERE c.framework = 'Spring Boot'` returns 0.

The existing uniqueness constraints enforce `c.name IS UNIQUE` (global per label). **This fix does not change the MERGE key or the constraints** — `framework` is added as an annotation property only.

### Change A — `_write_affected_entity` in `populator.py`

Add `ON CREATE SET` / `ON MATCH SET` clauses so the `framework` property is written when the node is first created and preserved (not overwritten) on subsequent matches:

Replace:

```python
session.run(
    f"""
    MERGE (e:{label} {{name: $name}})
    WITH e
    MATCH (rule:MigrationRule)
    WHERE elementId(rule) = $rule_id
    MERGE (rule)-[rel:{edge}]->(e)
    SET rel.role = $role
    """,
    name=affected.name,
    rule_id=rule_id,
    role=role,
)
```

With:

```python
session.run(
    f"""
    MERGE (e:{label} {{name: $name}})
    ON CREATE SET e.framework = $framework
    ON MATCH SET  e.framework = coalesce(e.framework, $framework)
    WITH e
    MATCH (rule:MigrationRule)
    WHERE elementId(rule) = $rule_id
    MERGE (rule)-[rel:{edge}]->(e)
    SET rel.role = $role
    """,
    name=affected.name,
    rule_id=rule_id,
    role=role,
    framework=framework_display,
)
```

`coalesce(e.framework, $framework)` means "first write wins" — if a node was already created by a different framework's pipeline run, its `framework` is not overwritten. This is intentional: entity nodes can in principle be shared across frameworks; the first framework to write them claims the property.

### Change B — propagate `framework_display` to `_write_step`

`_write_step` also creates entity nodes (for REMOVE/REPLACE/RENAME step types) but currently has no `framework_display` parameter. Add it:

Change the signature from:

```python
def _write_step(session, *, rule_id: str, step, entity) -> None:
```

To:

```python
def _write_step(session, *, rule_id: str, step, entity, framework_display: str) -> None:
```

Update the call site at populator.py line 220 (inside `_write_entity_block` or the equivalent loop), passing `framework_display=framework_display`.

Apply the same `ON CREATE SET` / `ON MATCH SET` pattern to the MERGE inside `_write_step`:

```cypher
MERGE (e:{label} {name: $name})
ON CREATE SET e.framework = $framework
ON MATCH SET  e.framework = coalesce(e.framework, $framework)
```

Add `framework=framework_display` to the `session.run(...)` params.

### Change C — `_SUBMIT_INSIGHT` in `community.py`

When community insights are submitted, the FOREACH blocks that create entity nodes also omit `framework`. Update each of the three FOREACH blocks to set `framework` after the MERGE:

Replace:

```cypher
FOREACH (class_name IN coalesce($affected_classes, []) |
  MERGE (c:Class {name: class_name})
  MERGE (ci)-[:AFFECTS_CLASS]->(c)
)
WITH ci
FOREACH (prop_name IN coalesce($affected_properties, []) |
  MERGE (p:ApplicationProperty {name: prop_name})
  MERGE (ci)-[:AFFECTS_PROPERTY]->(p)
)
WITH ci
FOREACH (dep_name IN coalesce($affected_dependencies, []) |
  MERGE (d:Dependency {name: dep_name})
  MERGE (ci)-[:AFFECTS_DEPENDENCY]->(d)
)
```

With:

```cypher
FOREACH (class_name IN coalesce($affected_classes, []) |
  MERGE (c:Class {name: class_name})
  ON CREATE SET c.framework = $framework
  ON MATCH SET  c.framework = coalesce(c.framework, $framework)
  MERGE (ci)-[:AFFECTS_CLASS]->(c)
)
WITH ci
FOREACH (prop_name IN coalesce($affected_properties, []) |
  MERGE (p:ApplicationProperty {name: prop_name})
  ON CREATE SET p.framework = $framework
  ON MATCH SET  p.framework = coalesce(p.framework, $framework)
  MERGE (ci)-[:AFFECTS_PROPERTY]->(p)
)
WITH ci
FOREACH (dep_name IN coalesce($affected_dependencies, []) |
  MERGE (d:Dependency {name: dep_name})
  ON CREATE SET d.framework = $framework
  ON MATCH SET  d.framework = coalesce(d.framework, $framework)
  MERGE (ci)-[:AFFECTS_DEPENDENCY]->(d)
)
```

Note: `$framework` is already passed as a parameter to `_SUBMIT_INSIGHT` via the `framework` key in the params dict.

---

## Acceptance Criteria

1. **Issue 1**: `analyze_upgrade_path("Spring Boot", "3.5.0", "4.0.0", user_entities=["WebSecurityConfigurerAdapter", "RestTemplate"])` returns ≥ 1 rule (the 16 general rules with no entity links must be included).
2. **Issue 1**: `build_recipe_plan("Spring Boot", "3.5.0", "4.0.0", user_entities=["RestTemplate"])` returns at least one item in `auto_track` or `manual_track`.
3. **Issue 2**: `submit_migration_insight(statement="...", spring_boot_version="4.0", framework="Spring Boot")` returns `status: "ok"` or `status: "duplicate"` — no `RuntimeError`.
4. **Issue 2**: `submit_migration_insight(spring_boot_version="4")` also succeeds (single-segment versions padded to `4.0.0`).
5. **Issue 3**: After server restart, the first call to `search_migration_knowledge` succeeds within 5 seconds (no cold-start timeout).
6. **Issue 3**: If `sentence-transformers` is not installed, `startup()` logs a warning and the server still starts.
7. **Issue 4**: After re-running the pipeline, `MATCH (c:Class) WHERE c.framework = 'Spring Boot' RETURN count(c)` returns > 0.
8. **Issue 4**: Existing nodes with no `framework` property are not broken — re-running the pipeline sets `framework` on them (first-write-wins for nodes that already exist).
9. Calling with `user_entities=[]` (empty) still returns the full rule set (no regression on the existing no-filter path).

---

## Out of Scope

- **OpenRewriteRecipe stubs** (`search_openrewrite_recipes` returns 0 hits): 333 nodes exist but have no `description`/`displayName` properties. Requires recipe registry integration — separate ticket.
- **`resolve_deprecation` short-name limitation**: The tool requires fully-qualified entity names (already documented in spec 008). The `not_found` for short names like `EnvironmentPostProcessor` is expected behaviour; adding `framework` to Class nodes (Fix 4) does not change this.
- Changing entity uniqueness constraints from `name IS UNIQUE` to `(name, framework) IS UNIQUE` — schema migration, separate ticket.
- Any changes to tool signatures, new MCP tools.

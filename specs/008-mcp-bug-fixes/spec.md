# Feature Specification: MCP Server Bug Fixes

**Feature Branch**: `008-mcp-bug-fixes`
**Created**: 2026-06-09
**Status**: Draft
**Research**: See [research.md](research.md) for per-issue root-cause analysis.
**Source**: [`ISSUES.md`](ISSUES.md) — 6 bugs found during Spring Boot 3.5.0 → 4.0.0 migration simulation.

---

## Scope

Fix all 6 bugs documented in `ISSUES.md`. No new features, no schema changes, no tool renames.

| # | Issue | Severity | File(s) |
|---|-------|----------|---------|
| 1 | `get_pending_steps` crashes with Cypher `SyntaxError` | High | `mcp/graph/queries/context.py` |
| 2 | `analyze_upgrade_path` / `build_recipe_plan` return 0 rules | High | `mcp/graph/queries/upgrade.py` |
| 3 | `submit_migration_insight` fails without embeddings | Medium | `mcp/tools/community.py` |
| 4 | `search_openrewrite_recipes` returns 0 results | Medium | `graph/indexes.py` |
| 5 | `Class`/`ApplicationProperty` entities not found | Medium | `mcp/graph/queries/deprecation.py` |
| 6 | Exact patch versions ignored in version range | Low | `mcp/tools/upgrade.py` |

---

## Fix 1 — `get_pending_steps` Cypher SyntaxError

**File**: `migration_oracle/mcp/graph/queries/context.py`

The `_GET_PENDING_STEPS` query ends with an aggregation (`collect(DISTINCT ...)`) in the `RETURN` clause and then `ORDER BY s.stepIndex` which Neo4j 5.x rejects because `s` is no longer in scope after the aggregation.

**Change**: In `_GET_PENDING_STEPS`, project the sort keys as named aliases and reference them in `ORDER BY`.

Replace:

```cypher
RETURN elementId(s) AS step_id,
       s.stepType AS step_type,
       elementId(r) AS rule_id,
       s.summary AS summary,
       s.instruction AS instruction,
       s.verificationHint AS verification_hint,
       s.effort AS effort,
       s.automatable AS automatable,
       bs.scope AS scope,
       bs.severity AS severity,
       rec.recipeId AS recipe_id,
       collect(DISTINCT elementId(prereq)) AS requires
ORDER BY
  CASE bs.severity
    WHEN 'critical' THEN 0 WHEN 'high' THEN 1
    WHEN 'medium'   THEN 2 ELSE 3
  END ASC,
  s.stepIndex ASC
```

With:

```cypher
RETURN elementId(s) AS step_id,
       s.stepType AS step_type,
       elementId(r) AS rule_id,
       s.summary AS summary,
       s.instruction AS instruction,
       s.verificationHint AS verification_hint,
       s.effort AS effort,
       s.automatable AS automatable,
       bs.scope AS scope,
       bs.severity AS severity,
       rec.recipeId AS recipe_id,
       collect(DISTINCT elementId(prereq)) AS requires,
       s.stepIndex AS _step_index,
       CASE bs.severity
         WHEN 'critical' THEN 0 WHEN 'high' THEN 1
         WHEN 'medium'   THEN 2 ELSE 3
       END AS _severity_rank
ORDER BY _severity_rank ASC, _step_index ASC
```

The two `_`-prefixed columns (`_step_index`, `_severity_rank`) are included in the raw row dict returned by `get_pending_steps`. Strip them in the Python function before returning:

```python
def get_pending_steps(...) -> list[dict]:
    with read_session() as session:
        rows = [
            dict(row)
            for row in session.run(_GET_PENDING_STEPS, ...)
        ]
    _internal = {"_step_index", "_severity_rank"}
    return [{k: v for k, v in row.items() if k not in _internal} for row in rows]
```

---

## Fix 2 — `analyze_upgrade_path` / `build_recipe_plan` return 0 rules

**File**: `migration_oracle/mcp/graph/queries/upgrade.py`

Two changes:

### 2a — Fix `_ANALYZE_UPGRADE_PATH`

Replace the undirected, mixed-label relationship match with a directed, typed match, and widen the `entityClassification` filter:

Replace:

```cypher
OPTIONAL MATCH (v)-[:INCLUDES_RULE|DISCOVERED_IN]-(rule)
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)

WITH v, raw_lifecycle_events, rule,
     collect(DISTINCT ruleEntity.name) AS affected_entities

WHERE rule IS NULL
   OR (
       (size($user_entities) = 0
          OR ANY(e IN affected_entities
                   WHERE ANY(u IN $user_entities
                              WHERE toLower(e) CONTAINS toLower(u))))
       AND
       (rule.entityClassification IS NULL
          OR rule.entityClassification IN $classification)
     )
```

With:

```cypher
OPTIONAL MATCH (v)-[:INCLUDES_RULE]->(rule:MigrationRule)
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ruleEntity)

WITH v, raw_lifecycle_events, rule,
     collect(DISTINCT ruleEntity.name) AS affected_entities

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

### 2b — Fix `_BUILD_RECIPE_PLAN`

Same `entityClassification` widening:

Replace:

```cypher
WHERE rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification
```

With:

```cypher
WHERE size($classification) = 0
   OR rule.entityClassification IS NULL
   OR rule.entityClassification IN $classification
```

### 2c — Change default `classification` to empty list

In both `analyze_upgrade_path` and `build_recipe_plan` Python functions, change:

```python
# before
classes = classification or ["actionable", "incomplete"]
# after
classes = classification or []
```

This makes the default "no classification filter" rather than accidentally filtering by specific labels that may not match stored values.

---

## Fix 3 — `submit_migration_insight` fails without embeddings

**File**: `migration_oracle/mcp/tools/community.py`

Wrap the embedding encode call in a try/except so the tool continues without embeddings when they are unavailable. The `community_queries.submit_insight` already accepts `embedding=None` and falls back to BM25-only duplicate detection.

Replace:

```python
embedding = get_embedding_model().encode(statement).tolist()
insight_id, is_duplicate = community_queries.submit_insight(
    ...
    embedding=embedding,
)
```

With:

```python
embedding: list[float] | None = None
try:
    embedding = get_embedding_model().encode(statement).tolist()
except Exception:
    pass
insight_id, is_duplicate = community_queries.submit_insight(
    ...
    embedding=embedding,
)
```

---

## Fix 4 — `search_openrewrite_recipes` returns 0 results

**File**: `migration_oracle/graph/indexes.py`

Add the two missing fulltext indexes to the `_INDEXES` list:

```python
"CREATE FULLTEXT INDEX migration_text IF NOT EXISTS "
"FOR (n:MigrationRule|CommunityInsight) ON EACH [n.statement, n.reason, n.solution]",

"CREATE FULLTEXT INDEX openrewrite_recipe_description IF NOT EXISTS "
"FOR (r:OpenRewriteRecipe) ON EACH [r.description, r.displayName]",
```

These are appended to the existing `_INDEXES` list. The `ensure_indexes` call at server startup applies them idempotently.

Also update `_EXPECTED_CONSTRAINTS` documentation comment (or a nearby `_EXPECTED_INDEXES` set if one is added) to include these two names so future audits catch drift.

---

## Fix 5 — `resolve_deprecation` returns `not_found` for known entities

**File**: `migration_oracle/mcp/graph/queries/deprecation.py`

The existing `_RESOLVE_DEPRECATION` query searches for entities by name and then follows `DEPRECATED_IN` / `REMOVED_IN` relationships to Version nodes filtered by `framework`. If the `Class` node has no `DEPRECATED_IN` edge to a Spring Boot `Version` node, the optional matches return `null` and the tool reports `not_found`.

Add a secondary lookup via `Version` node relationships so that entities reachable via `REMOVES` / `INTRODUCES` are also returned:

Replace `_RESOLVE_DEPRECATION` with:

```cypher
MATCH (e)
WHERE (e:Class OR e:ApplicationProperty OR e:Dependency) AND e.name = $entity_name

OPTIONAL MATCH (e)-[:DEPRECATED_IN]->(depV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REMOVED_IN]->(remV:Version {framework: $framework})
OPTIONAL MATCH (e)-[:REPLACED_BY]->(replacement)

OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WHERE (rule:MigrationRule OR rule:CommunityInsight)
  AND EXISTS { (rule)-[:INCLUDES_RULE|DISCOVERED_IN]-(:Version {framework: $framework}) }

WITH e, depV, remV, replacement,
     collect({
       type: labels(rule)[0],
       statement: rule.statement,
       reason: rule.reason,
       solution: rule.solution,
       action_step: rule.actionStep
     }) AS rules

OPTIONAL MATCH (introV:Version {framework: $framework})-[:INTRODUCES]->(e)
OPTIONAL MATCH (removedByV:Version {framework: $framework})-[:REMOVES]->(e)

RETURN
  labels(e)[0] AS entity_type,
  e.name AS original_entity,
  replacement.name AS replaced_by,
  coalesce(depV.version, introV.version) AS deprecated_in,
  coalesce(remV.version, removedByV.version) AS removed_in,
  rules
```

This adds `INTRODUCES` and `REMOVES` as fallback sources for `deprecated_in` / `removed_in` when the direct entity → version relationship is absent.

---

## Fix 6 — Patch versions ignored in version range

**File**: `migration_oracle/mcp/tools/upgrade.py`

Add a private normalisation helper and apply it before computing `sortable_version`:

```python
def _to_minor_zero(version: str) -> str:
    """Normalise 'major.minor.patch' → 'major.minor.0' for graph lookups."""
    parts = version.split(".", 2)
    return f"{parts[0]}.{parts[1]}.0"
```

In both `analyze_upgrade_path` and `build_recipe_plan`, change:

```python
# before
"current_version_sortable": sortable_version(current_version),
"target_version_sortable":  sortable_version(target_version),

# after
"current_version_sortable": sortable_version(_to_minor_zero(current_version)),
"target_version_sortable":  sortable_version(_to_minor_zero(target_version)),
```

---

## Acceptance Criteria

1. **Issue 1**: `get_pending_steps` returns a list of steps without raising a `SyntaxError`. Results are ordered by severity then `stepIndex`.
2. **Issue 2**: `analyze_upgrade_path("Spring Boot", "3.5.0", "4.0.0")` returns at least one rule. `build_recipe_plan` likewise returns a non-empty plan for the same range.
3. **Issue 3**: `submit_migration_insight` succeeds (returns `status: "ok"` or `status: "duplicate"`) when `POPULATE_MIGRATION_EMBEDDINGS=false`.
4. **Issue 4**: `search_openrewrite_recipes("Spring Boot upgrade")` returns ≥ 1 hit after server restart (indexes are rebuilt on first startup).
5. **Issue 5**: `resolve_deprecation("EnvironmentPostProcessor", "Spring Boot")` returns a non-null `deprecated_in` or `removed_in` when such an entity exists in the graph.
6. **Issue 6**: `analyze_upgrade_path("Spring Boot", "3.5.12", "4.0.6")` returns the same rules as `("Spring Boot", "3.5.0", "4.0.0")`.

---

## Out of Scope

- Fixing the entity ingestion pipeline to write `framework` onto `Class`/`ApplicationProperty` nodes (data-quality issue, separate ticket).
- Implementing `only_composite` / `require_no_params` filtering in `search_openrewrite_recipes` (deferred from spec 005a).
- Backfilling vector embeddings (requires `POPULATE_MIGRATION_EMBEDDINGS=true` and a re-run of the pipeline).
- Adding new MCP tools or changing tool signatures.

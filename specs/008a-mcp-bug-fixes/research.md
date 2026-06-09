# Research: MCP Bug Fixes Round 2 (spec 008a)

**Source**: Live black-box probe report (`ISSUES.md` — 2026-06-09)
**Issues researched**: Issues 3 and 5 from the probe (previously marked Out of Scope in spec 008a draft)

---

## Issue A — Cold-start search latency

### Symptom
First call to `search_migration_knowledge` after server start returns `no_response`. Retry 8 seconds later succeeds. All subsequent calls succeed immediately.

### Root cause

**`migration_oracle/mcp/tools/search.py:15-23`**

```python
_model: SentenceTransformer | None = None

def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.SENTENCE_TRANSFORMERS_MODEL)
    return _model
```

Model is lazy-loaded on the first call to `encode()`. Loading `all-mpnet-base-v2` from disk takes 2–5 seconds. The MCP SSE client has no built-in retry, so a first-call timeout means lost results.

**`migration_oracle/mcp/server.py:125-134`** — `startup()` connects to Neo4j and builds indexes, but never touches the embedding model:

```python
def startup() -> None:
    driver = get_driver()
    with driver.session() as session:
        session.run("RETURN 1").single()
    ensure_indexes(driver)
    logger.info("PaysafeMigrationOracle ready ...")
```

**Docker note**: `Dockerfile` pre-bakes the model weights into the image during build (`SentenceTransformer('all-mpnet-base-v2')`), so disk I/O is not the bottleneck — the bottleneck is the Python object initialisation and tokenizer load that still happens at runtime.

### Fix location
`migration_oracle/mcp/server.py` — add a warm-up call at the end of `startup()`.

The import must be guarded with a try/except because `POPULATE_MIGRATION_EMBEDDINGS=false` deployments may not have sentence-transformers installed. Failure to warm up must not prevent the server from starting.

---

## Issue B — Missing `framework` property on Class / ApplicationProperty / Dependency nodes

### Symptom
Probe diagnostic: `MATCH (c:Class) WHERE c.framework = 'Spring Boot' RETURN count(c)` → 0.

`resolve_deprecation("EnvironmentPostProcessor")` → `not_found`.
`entity_evolution("EnvironmentPostProcessor")` → `chain=[]`.

### What exists in the graph
Entity names ARE reachable via MigrationRule edges:

```
MATCH (v:Version {version:'4.0.0', framework:'Spring Boot'})
      -[:INCLUDES_RULE]->(mr)-[:AFFECTS_CLASS|...]->(e)
RETURN DISTINCT e.name LIMIT 10
```

Returns: `org.springframework.boot.EnvironmentPostProcessor`, `org.springframework.boot.env.EnvironmentPostProcessor`, `spring.http.codecs.max-in-memory-size`, etc.

So the nodes exist — they just have no `framework` property.

### Root cause — pipeline populator

**`migration_oracle/pipeline/populator.py:354-366`** (`_write_affected_entity`):

```python
session.run(
    f"""
    MERGE (e:{label} {{name: $name}})          # ← only 'name' in MERGE key
    WITH e
    MATCH (rule:MigrationRule) WHERE elementId(rule) = $rule_id
    MERGE (rule)-[rel:{edge}]->(e)
    SET rel.role = $role
    """,
    name=affected.name,
    rule_id=rule_id,
    role=role,
)
```

`framework_display` **is available** as a parameter to `_write_affected_entity` (line 347) and is used in the REMOVED_IN / INTRODUCED_IN / DEPRECATED_IN relationship writes below (lines 368–403), but is **never set on the entity node itself**.

**`migration_oracle/pipeline/populator.py:327-338`** (`_write_step`):

```python
session.run(
    f"""
    MATCH (s:MigrationStep ...)
    MERGE (e:{label} {{name: $name}})          # ← only 'name', no framework
    MERGE (s)-[rel:{edge}]->(e)
    SET rel.role = $role
    """,
    ...
)
```

`_write_step` has no `framework_display` parameter and is called from line 220 without it. This function creates entity nodes for REMOVE/REPLACE/RENAME step types.

**`migration_oracle/mcp/graph/queries/community.py:39-52`** (`_SUBMIT_INSIGHT`):

```cypher
FOREACH (class_name IN coalesce($affected_classes, []) |
  MERGE (c:Class {name: class_name})           ← no framework
  MERGE (ci)-[:AFFECTS_CLASS]->(c)
)
```

Same issue when community insights are submitted via the MCP tool.

### Schema constraint
`migration_oracle/graph/indexes.py:13-15`:

```python
"CREATE CONSTRAINT class_name IF NOT EXISTS FOR (c:Class) REQUIRE c.name IS UNIQUE",
"CREATE CONSTRAINT property_name IF NOT EXISTS FOR (p:ApplicationProperty) REQUIRE p.name IS UNIQUE",
"CREATE CONSTRAINT dependency_name IF NOT EXISTS FOR (d:Dependency) REQUIRE d.name IS UNIQUE",
```

Constraints use `name` alone as the unique key — not `(name, framework)`. This means a single `Class` node named `RestTemplate` is shared across all frameworks. Adding `framework` as part of the MERGE key would require replacing these constraints with composite ones and is a schema-migration, out of scope here.

### Fix approach

Use `SET e.framework = $framework` (not `{framework: $framework}` in the MERGE key) to annotate nodes after creation without changing the uniqueness key:

```cypher
MERGE (e:{label} {name: $name})
ON CREATE SET e.framework = $framework
ON MATCH SET  e.framework = coalesce(e.framework, $framework)
```

`ON MATCH` uses `coalesce` (first-write-wins) so that if a node was already written by a different framework's pipeline run, the first framework's value is preserved. The annotation is best-effort and is only used for diagnostic queries (`WHERE c.framework = $framework`); the runtime queries (`resolve_deprecation`) rely on Version relationships, not the entity's `framework` property.

**`_write_step` partial fix**: pass `framework_display` through the call chain so step-linked entity nodes are also annotated. Call site at populator.py:220 already has `framework_display` in scope.

### Why `resolve_deprecation` still returns `not_found`
Even after adding `framework` to nodes, `resolve_deprecation("EnvironmentPostProcessor")` returns `not_found` because:
1. The probe used the **short name**. The graph stores `org.springframework.boot.env.EnvironmentPostProcessor` — the tool description already documents this (added in spec 008).
2. `EnvironmentPostProcessor` has a `DEPRECATED_IN` edge in the graph **only if** the pipeline extracted it from a deprecation section. Entities only reachable via `AFFECTS_CLASS` edges from MigrationRules are not surfaced by `resolve_deprecation`.

Adding `framework` to Class nodes does not change the `not_found` result for short names. But it fixes the probe diagnostic (the `MATCH (c:Class) WHERE c.framework = 'Spring Boot'` check) and makes framework-scoped entity queries possible.

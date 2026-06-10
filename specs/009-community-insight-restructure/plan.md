# Implementation Plan: Community Insight Restructure

**Branch**: `009-community-insight-restructure` | **Date**: 2026-06-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-community-insight-restructure/spec.md`

## Summary

Flatten community-contributed migration insights from a separate `CommunityInsight` node label into `MigrationRule` nodes with `ruleType='community_insight'`. All four community MCP tool signatures and return shapes are preserved. The `include_community_insights` parameter is removed from `search_migration_knowledge`. No new dependencies, no new indexes.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastMCP (tool registration), Neo4j Python driver (graph queries), sentence-transformers (embedding), Streamlit (UI — no changes needed)

**Storage**: Neo4j / Memgraph graph database

**Testing**: pytest

**Target Platform**: Linux server (Docker container, as per spec 007)

**Project Type**: MCP server + Streamlit web app

**Performance Goals**: No change from current baseline

**Constraints**: Write transaction must create `MigrationRule` + `MigrationStep` atomically; embedding omission must not raise

**Scale/Scope**: Single-repository rewrite touching 4 source files; 2 files confirmed no-op

## Constitution Check

The project constitution file (`.specify/memory/constitution.md`) contains only an unfilled template — no principles or gates are defined. No violations to track.

## Project Structure

### Documentation (this feature)

```text
specs/009-community-insight-restructure/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── contracts/
│   └── 009-community-insight-restructure.md  ← Phase 1 output
├── checklists/
│   └── requirements.md  ← already exists (all checks passed)
└── tasks.md             ← Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (files changed by this spec)

```text
migration_oracle/
├── graph/
│   └── indexes.py                         ← FR-017: remove CommunityInsight from migration_text label list
├── mcp/
│   ├── graph/
│   │   └── queries/
│   │       ├── community.py               ← FR-001…FR-009, FR-011, FR-012, FR-016, FR-017, FR-018 (major rewrite)
│   │       └── search.py                  ← FR-013: remove include_community_insights param + filter, add solution traversal
│   └── tools/
│       ├── community.py                   ← FR-016, FR-018: docstring updates + Version-not-found error handler
│       └── search.py                      ← FR-013: remove include_community_insights from signatures + call sites
└── streamlit_app/
    └── pages/
        └── 05_community.py                ← FR-015: NO CHANGES (calls tool functions by import; signatures unchanged)
```

---

## File-by-File Change Plan

### 1. `migration_oracle/mcp/graph/queries/community.py` — Major rewrite

All Cypher strings and helper functions are rewritten. No external API change.

#### 1a. `_FIND_EXACT_STATEMENT`

**Before**: `MATCH (ci:CommunityInsight) WHERE ci.statement = $statement`
**After**: `MATCH (r:MigrationRule) WHERE r.statement = $statement AND r.ruleType = 'community_insight'`

Add `ruleType` filter so exact-match only hits community insight rules, not official changelog rules with identical statements.

#### 1b. `_FETCH_EMBEDDING`

**Before**: `MATCH (ci:CommunityInsight) WHERE elementId(ci) = $insight_id RETURN ci.embedding AS embedding`
**After**: `MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id RETURN r.embedding AS embedding`

The element ID lookup is label-agnostic in principle, but using the correct label is required by FR-016.

#### 1c. `_SUBMIT_INSIGHT` — Full rewrite

Old query: creates a `CommunityInsight` node linked via `DISCOVERED_IN` with flat properties.

New query (see data-model.md for full property list):

```cypher
MATCH (v:Version {framework: $framework, version: $version})
CREATE (r:MigrationRule {
  statement:             $statement,
  ruleType:              'community_insight',
  sourceUrl:             coalesce($evidence_url, ''),
  communitySubmittedBy:  coalesce($submitted_by, 'mcp-agent'),
  communityCreatedAt:    toString(datetime()),
  communityConfidence:   coalesce($confidence, 0.5),
  communityVotes:        0,
  communityVerified:     false,
  embedding:             $embedding
})
CREATE (v)-[:INCLUDES_RULE]->(r)
CREATE (s:MigrationStep {
  stepType:    'manual',
  summary:     coalesce($solution, ''),
  instruction: coalesce($solution, ''),
  effort:      'moderate',
  automatable: false
})
CREATE (r)-[:REQUIRES_STEP]->(s)
WITH r
FOREACH (class_name IN coalesce($affected_classes, []) |
  MERGE (c:Class {name: class_name})
  ON CREATE SET c.framework = $framework
  ON MATCH SET  c.framework = coalesce(c.framework, $framework)
  MERGE (r)-[:AFFECTS_CLASS]->(c)
)
WITH r
FOREACH (prop_name IN coalesce($affected_properties, []) |
  MERGE (p:ApplicationProperty {name: prop_name})
  ON CREATE SET p.framework = $framework
  ON MATCH SET  p.framework = coalesce(p.framework, $framework)
  MERGE (r)-[:AFFECTS_PROPERTY]->(p)
)
WITH r
FOREACH (dep_name IN coalesce($affected_dependencies, []) |
  MERGE (d:Dependency {name: dep_name})
  ON CREATE SET d.framework = $framework
  ON MATCH SET  d.framework = coalesce(d.framework, $framework)
  MERGE (r)-[:AFFECTS_DEPENDENCY]->(d)
)
RETURN elementId(r) AS insight_id
```

**Embedding-None handling**: Neo4j/Memgraph silently drops null properties during `CREATE`, so passing `embedding: None` results in a node with no `embedding` property (no exception, no sentinel value). No conditional branching needed in Cypher; the Python call site simply passes `embedding=embedding` as today.

**Version-not-found**: When `MATCH (v:Version {...})` matches nothing, the query returns no rows → `record is None`. In `submit_insight()`, `record is None` means the `Version` node doesn't exist (a driver-level write error raises an exception instead). Handle in Python (see §1h).

#### 1d. `_QUERY_INSIGHTS` — Full rewrite

Old query: matches `CommunityInsight` nodes with `DISCOVERED_IN`, reads flat properties.

New query:

```cypher
MATCH (v:Version {framework: $framework})-[:INCLUDES_RULE]->(r:MigrationRule)
WHERE r.ruleType = 'community_insight'
  AND ($from_sortable IS NULL OR v.sortableVersion >= $from_sortable)
  AND ($to_sortable IS NULL OR v.sortableVersion <= $to_sortable)
  AND ($verified_only = false OR r.communityVerified = true)
OPTIONAL MATCH (r)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
WITH r, v, collect(DISTINCT e.name) AS affected_entities
WHERE $entity_name IS NULL
   OR ANY(name IN affected_entities WHERE name = $entity_name)
OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)
WITH r, v, affected_entities, s
ORDER BY s.stepIndex ASC
WITH r, v, affected_entities, collect(s)[0] AS first_step
RETURN elementId(r)               AS insight_id,
       r.statement                AS statement,
       coalesce(first_step.instruction, '') AS solution,
       r.sourceUrl                AS source_url,
       r.communitySubmittedBy     AS submitted_by,
       r.communityCreatedAt       AS created_at,
       r.communityConfidence      AS confidence,
       r.communityVotes           AS votes,
       r.communityVerified        AS verified,
       v.version                  AS version,
       affected_entities
ORDER BY r.communityVotes DESC, r.communityCreatedAt DESC
```

The `query_insights()` Python function returns `list[dict]` with the same key aliases as before (`submitted_by`, `created_at`, `confidence`, `votes`, `verified`), so the MCP tool layer (`tools/community.py`) needs no key-mapping changes.

#### 1e. `_VOTE_INSIGHT`

**Before**: `MATCH (ci:CommunityInsight)… SET ci.votes = coalesce(ci.votes, 0) + $delta RETURN … ci.votes AS votes`
**After**: `MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id SET r.communityVotes = coalesce(r.communityVotes, 0) + $delta RETURN elementId(r) AS insight_id, r.communityVotes AS votes`

The Python return alias `votes` is preserved so `vote_insight()` result dict key is unchanged → MCP tool accesses `result["votes"]` as today.

#### 1f. `_VERIFY_INSIGHT`

**Before**: `MATCH (ci:CommunityInsight)… SET ci.verified = true RETURN … ci.verified AS verified`
**After**: `MATCH (r:MigrationRule) WHERE elementId(r) = $insight_id SET r.communityVerified = true RETURN elementId(r) AS insight_id, r.communityVerified AS verified`

Same alias preservation.

#### 1g. `find_near_duplicate` — index names

- `vector_search(index="migration_knowledge_vector_ci", ...)` → `vector_search(index="migration_knowledge_vector_mr", ...)`

#### 1h. `_best_bm25_duplicate` — BM25 index

- `bm25_search(query=statement, index="migration_text", top_k=5)` → `bm25_search(query=statement, index="rule_statement", top_k=5)`

#### 1i. `submit_insight()` — Version-not-found error + RuntimeError message

```python
def submit_insight(...) -> tuple[str, bool]:
    duplicate_id = find_near_duplicate(statement=statement, embedding=embedding)
    if duplicate_id:
        return duplicate_id, True
    params = { ... }
    with write_session() as session:
        record = session.run(_SUBMIT_INSIGHT, params).single()
    if record is None:
        raise ValueError(f"Version not found: {framework} {version}")
    return record["insight_id"], False
```

The old `RuntimeError("Failed to create CommunityInsight")` is replaced by `ValueError("Version not found: …")`. Driver-level failures still propagate as driver exceptions.

The MCP tool (`tools/community.py`) must catch `ValueError` and return the structured error:

```python
try:
    insight_id, is_duplicate = community_queries.submit_insight(...)
except ValueError as e:
    return {"status": "error", "insight_id": "", "duplicate_of": "", "message": str(e)}
```

This keeps the MCP tool's external return shape unchanged (all four fields present); callers already handle `status` values.

---

### 2. `migration_oracle/graph/indexes.py` — Remove `CommunityInsight` from `migration_text`

**Line 26–27 before**:
```python
"CREATE FULLTEXT INDEX migration_text IF NOT EXISTS "
"FOR (n:MigrationRule|CommunityInsight) ON EACH [n.statement, n.reason, n.solution]",
```

**After**:
```python
"CREATE FULLTEXT INDEX migration_text IF NOT EXISTS "
"FOR (n:MigrationRule) ON EACH [n.statement, n.reason, n.solution]",
```

The `_EXPECTED_INDEXES` set on line 51 already lists `"migration_text"` — no change there.

**Note**: The user's `/speckit-plan` input stated "indexes.py: no changes needed (confirmed already clean)", but `spec.md` FR-017 and direct source inspection at line 27 both confirm `CommunityInsight` is still present. The spec is authoritative; this change is required.

**Deployment caveat — live database**: The DDL uses `IF NOT EXISTS`, which means this code change is a no-op on any Memgraph instance that already has the `migration_text` index created with the old `MigrationRule|CommunityInsight` label union. The running database will continue using the old index definition until it is explicitly dropped. After deploying this spec, run the following on the live Memgraph instance before the next application restart:

```cypher
DROP INDEX ON :MigrationRule(migration_text);
-- or the Memgraph fulltext drop form:
DROP INDEX migration_text;
```

On next startup, `ensure_indexes()` recreates the index with the corrected label list (`MigrationRule` only). This is a manual ops step, not a code task. The consequence of skipping it is benign (no new `CommunityInsight` nodes are written, so the extra label in the index is dead coverage) but cleanup is the stated goal of FR-017.

---

### 3. `migration_oracle/mcp/graph/queries/search.py` — Remove `include_community_insights`, add solution traversal

#### 3a. `hydrate_nodes` signature

Remove `include_community_insights: bool = True` parameter.

#### 3b. `hydrate_nodes` Cypher — targeted changes only

**Scope**: Three surgical edits to the existing Cypher string. The `MATCH (n) WHERE elementId(n) IN $ids`, `OPTIONAL MATCH ...-(v:Version)`, version filter `WHERE ($framework IS NULL OR size(versions) > 0)`, and all RETURN field projections except `solution` are **unchanged**.

**Change 1 — Remove** the filter line (the only line that referenced `$include_community_insights`):
```cypher
AND ($include_community_insights OR 'MigrationRule' IN labels(n))
```

**Change 2 — Add** two lines immediately after `WHERE ($framework IS NULL OR size(versions) > 0)` to resolve the first `MigrationStep` child:
```cypher
OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)
WITH n, versions, collect(s)[0] AS first_step
```

**Change 3 — Replace** the single RETURN projection:
```cypher
-- before
n.solution AS solution,
-- after
coalesce(n.solution, first_step.instruction) AS solution,
```

The full Cypher after all three edits for reference:
```cypher
MATCH (n) WHERE elementId(n) IN $ids
OPTIONAL MATCH (n)-[:INCLUDES_RULE|DISCOVERED_IN]-(v:Version)
WHERE $framework IS NULL OR v.framework = $framework
WITH n, collect(DISTINCT v.version) AS versions
WHERE ($framework IS NULL OR size(versions) > 0)
OPTIONAL MATCH (n)-[:REQUIRES_STEP]->(s:MigrationStep)
WITH n, versions, collect(s)[0] AS first_step
RETURN elementId(n)                                        AS node_id,
       labels(n)[0]                                        AS node_type,
       n.statement                                         AS statement,
       n.reason                                            AS reason,
       coalesce(n.solution, first_step.instruction)        AS solution,
       n.actionStep                                        AS action_step,
       n.ruleType                                          AS rule_type,
       n.sourceUrl                                         AS source_url,
       n.description                                       AS description,
       n.recipeId                                          AS recipe_id,
       n.displayName                                       AS display_name,
       versions
```

`coalesce(n.solution, first_step.instruction)` is safe for all node types:
- Official `MigrationRule` nodes: `n.solution` is set → coalesce returns it; `OPTIONAL MATCH` on `REQUIRES_STEP` may or may not match but result is unused.
- Community insight `MigrationRule` nodes: `n.solution` is null → falls through to `first_step.instruction`.
- `OpenRewriteRecipe` nodes: this Cypher path isn't called for them (`hydrate_openrewrite_recipes` is used instead).

**`collect(s)[0]` is intentionally unordered**: Official `MigrationRule` nodes may have multiple `REQUIRES_STEP` children (structured changelog rules with several steps). `collect(s)[0]` picks an arbitrary element, but this is harmless because official rules always have `n.solution` set — `coalesce` short-circuits on that value and `first_step.instruction` is never read. Do not add `ORDER BY s.stepIndex ASC` to this path; it would be a spurious sort on data that is never consumed for the production case, and could change behaviour unexpectedly if `n.solution` is ever null on an official rule.

**`DISCOVERED_IN` arm becomes dead code after this spec**: The relationship pattern `[:INCLUDES_RULE|DISCOVERED_IN]` retains `DISCOVERED_IN` for backward compatibility with any legacy `CommunityInsight` nodes that may exist in a live database prior to migration. Once all pre-existing `CommunityInsight` nodes are removed from the live graph, the `|DISCOVERED_IN` arm can be dropped in a follow-up cleanup. It is not a blocker for this spec.

#### 3c. `hydrate_nodes` Python call site

Remove `include_community_insights=include_community_insights` from `session.run(cypher, ids=..., framework=..., ...)`.

---

### 4. `migration_oracle/mcp/tools/search.py` — Remove `include_community_insights` from tool and helper

#### 4a. `search_migration_knowledge` tool function

Remove `include_community_insights: bool = True` from the signature. Remove the corresponding line from the docstring that references `include_community_insights=False`. Remove `include_community_insights=include_community_insights` from the `_build_hits(...)` call.

#### 4b. `_build_hits` helper

Remove `include_community_insights: bool` parameter. Remove `include_community_insights=include_community_insights` from the `hydrate_nodes(...)` call.

#### 4c. `search_openrewrite_recipes` call site

Line 207: `_build_hits(fused, framework=None, include_community_insights=False, openrewrite=True)` → `_build_hits(fused, framework=None, openrewrite=True)`.

---

### 5. `migration_oracle/mcp/tools/community.py` — Error handler + docstring updates

No signature or return-shape changes (FR-014).

#### 5a. `submit_migration_insight` — Version-not-found error handler (FR-018)

The `ValueError` raised by `submit_insight()` when no matching `Version` node exists must be caught here and returned as a structured response. Add a `try/except` around the `community_queries.submit_insight(...)` call:

```python
try:
    insight_id, is_duplicate = community_queries.submit_insight(
        statement=statement,
        framework=framework,
        version=_normalise_version(spring_boot_version),
        ...
    )
except ValueError as e:
    return {"status": "error", "insight_id": "", "duplicate_of": "", "message": str(e)}
```

The existing success/duplicate return branches are unchanged. The error response uses the same four-field shape as the other branches so no MCP caller needs updating.

#### 5b. Docstring updates (FR-016)

No signature or return-shape changes.

| Location | Old text | New text |
|----------|----------|----------|
| `submit_migration_insight` docstring line 1 | `"Submit a developer-contributed migration insight. Writes a CommunityInsight node."` | `"Submit a developer-contributed migration insight. Writes a MigrationRule node with ruleType='community_insight'."` |
| `get_community_insights` docstring line 1 | `"Query CommunityInsight nodes by version range…"` | `"Query MigrationRule nodes (ruleType='community_insight') by version range…"` |

---

### 6. `migration_oracle/streamlit_app/pages/05_community.py` — No changes (explicit no-op)

This page calls `submit_migration_insight`, `get_community_insights`, `vote_insight`, and `verify_insight` by Python import. All four tool function signatures and return shapes are preserved byte-for-byte (FR-014). The page requires no structural changes and must not be modified (FR-015).

---

### 7. Test files — scope and disposition

| File | Disposition | Required action |
|------|-------------|-----------------|
| `tests/mcp/test_community.py` | **Changes needed** | Add test for `ValueError` / Version-not-found path in `submit_migration_insight`: mock `community_queries.submit_insight` to raise `ValueError("Version not found: Spring Boot 9.9")` and assert the tool returns `{status: "error", message: "Version not found: Spring Boot 9.9"}`. Existing tests that exercise the success and duplicate branches remain valid; update any assertion that still expects a `CommunityInsight` label in mock return values. |
| `tests/mcp/test_search.py` | **Confirm-only** | Mocks at the `hydrate_nodes` boundary. Removing `include_community_insights` from the Python signature does not break any mock call site because the parameter is never passed from test code. No test changes expected; verify by running the suite. |
| `tests/streamlit/test_05_community.py` | **Confirm-only** | Mocks at the tool layer. Tool signatures are unchanged. No test changes expected; verify by running the suite. |

---

## Complexity Tracking

No constitution gates defined; no complexity to justify.

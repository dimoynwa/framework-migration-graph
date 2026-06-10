# Data Model: Community Insight Restructure

**Feature**: `009-community-insight-restructure`
**Date**: 2026-06-09

---

## Graph Nodes

### `MigrationRule` (community_insight variant)

Properties written by `submit_insight()` in a single `CREATE` statement:

| Property | Type | Source | Notes |
|----------|------|--------|-------|
| `statement` | string | tool param `statement` | Required; used for duplicate detection |
| `ruleType` | string | hardcoded `'community_insight'` | Sole discriminator for community filtering |
| `sourceUrl` | string | `coalesce($evidence_url, '')` | Empty string when not provided |
| `communitySubmittedBy` | string | `coalesce($submitted_by, 'mcp-agent')` | Prefixed to avoid namespace collision |
| `communityCreatedAt` | string | `toString(datetime())` | ISO 8601 string at write time |
| `communityConfidence` | float | `coalesce($confidence, 0.5)` | Range [0.0, 1.0] by convention |
| `communityVotes` | integer | hardcoded `0` | Incremented/decremented by `vote_insight` |
| `communityVerified` | boolean | hardcoded `false` | Set to `true` by `verify_insight` |
| `embedding` | float[] | tool param `embedding` | **Omitted when `None`** — null properties are dropped by Neo4j/Memgraph at write time |

**Not set on `MigrationRule` community nodes** (these exist only on official changelog rules):
- `solution` — sourced from `MigrationStep.instruction` at query time
- `reason`
- `actionStep`
- `ruleId`

---

### `MigrationStep` (community_insight variant)

One `MigrationStep` is created per `submit_insight()` call in the same write transaction:

| Property | Type | Source | Notes |
|----------|------|--------|-------|
| `stepType` | string | hardcoded `'manual'` | Distinguishes from automated steps |
| `summary` | string | `coalesce($solution, '')` | Short form of the workaround |
| `instruction` | string | `coalesce($solution, '')` | Full text; this is the `solution` exposed externally |
| `effort` | string | hardcoded `'moderate'` | Consistent with manual migration work |
| `automatable` | boolean | hardcoded `false` | Community insights are manual by definition |

**Not set** (used by structured changelog rules only): `ruleId`, `stepIndex`, `codeExample`

---

## Graph Relationships

| Relationship | Direction | Source | Target | When created |
|-------------|-----------|--------|--------|-------------|
| `INCLUDES_RULE` | `(v:Version)→(r:MigrationRule)` | `Version` node matching `{framework, version}` | New `MigrationRule` | Every successful `submit_insight()` |
| `REQUIRES_STEP` | `(r:MigrationRule)→(s:MigrationStep)` | New `MigrationRule` | New `MigrationStep` | Every successful `submit_insight()` |
| `AFFECTS_CLASS` | `(r:MigrationRule)→(c:Class)` | New `MigrationRule` | MERGE'd `Class` node | When `affected_classes` list is non-empty |
| `AFFECTS_PROPERTY` | `(r:MigrationRule)→(p:ApplicationProperty)` | New `MigrationRule` | MERGE'd `ApplicationProperty` node | When `affected_properties` list is non-empty |
| `AFFECTS_DEPENDENCY` | `(r:MigrationRule)→(d:Dependency)` | New `MigrationRule` | MERGE'd `Dependency` node | When `affected_dependencies` list is non-empty |

**Removed**: `DISCOVERED_IN` — this relationship linked old `CommunityInsight` nodes to `Version`. No longer used.

---

## External Response Types

### `CommunityInsightRecord`

Returned per element inside `get_community_insights().insights[]`:

| Field | Type | Source (graph) | Notes |
|-------|------|----------------|-------|
| `insight_id` | string | `elementId(r)` | Neo4j element ID of `MigrationRule` |
| `statement` | string | `r.statement` | |
| `solution` | string | `coalesce(first_step.instruction, '')` | Traversed via `OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s)` |
| `source_url` | string | `r.sourceUrl` | |
| `submitted_by` | string | `r.communitySubmittedBy` | Mapped from prefixed property |
| `created_at` | string | `r.communityCreatedAt` | |
| `confidence` | float | `r.communityConfidence` | |
| `votes` | integer | `r.communityVotes` | |
| `verified` | boolean | `r.communityVerified` | |
| `version` | string | `v.version` | Framework version string |

### `SubmitInsightResult`

Returned by `submit_migration_insight()`:

| Field | Type | Success value | Duplicate value | Error value |
|-------|------|---------------|-----------------|-------------|
| `status` | string | `"ok"` | `"duplicate"` | `"error"` |
| `insight_id` | string | new element ID | existing element ID | `""` |
| `duplicate_of` | string | `""` | existing element ID | `""` |
| `message` | string | `"Insight submitted"` | `"Near-duplicate insight already exists"` | `"Version not found: <framework> <version>"` |

### `VoteInsightResult`

Returned by `vote_insight()`:

| Field | Type | Source |
|-------|------|--------|
| `status` | string | hardcoded `"ok"` |
| `insight_id` | string | `elementId(r)` from `_VOTE_INSIGHT` result |
| `new_vote_count` | integer | `r.communityVotes` after update (aliased as `votes` in Cypher, mapped in Python) |

### `VerifyInsightResult`

Returned by `verify_insight()`:

| Field | Type | Source |
|-------|------|--------|
| `status` | string | hardcoded `"ok"` |
| `insight_id` | string | `elementId(r)` from `_VERIFY_INSIGHT` result |
| `verified` | boolean | `r.communityVerified` after SET (always `true` on success; aliased as `verified` in Cypher) |

---

## Index Usage After Restructure

| Index | Type | Covers | Used by |
|-------|------|--------|---------|
| `rule_statement` | FULLTEXT on `MigrationRule.statement` | Community insight statements | `_best_bm25_duplicate` (replaces `migration_text`) |
| `migration_knowledge_vector_mr` | VECTOR on `MigrationRule.embedding` | Community insight embeddings | `find_near_duplicate` (replaces `migration_knowledge_vector_ci`) |
| `migration_text` | FULLTEXT on `MigrationRule` only | Official rule text search | `search_migration_knowledge` BM25 path (no longer covers `CommunityInsight`) |

**Obsolete after this spec** (can be dropped manually from live DB):
- `migration_knowledge_vector_ci` vector index on `CommunityInsight.embedding`

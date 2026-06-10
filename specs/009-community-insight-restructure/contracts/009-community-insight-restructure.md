# Contracts: Community Insight Restructure

**Feature**: `009-community-insight-restructure`
**Date**: 2026-06-09

These are the boundary rules for this feature. Violating any of these rules constitutes a regression.

---

## Write Atomicity

`submit_migration_insight` MUST create a `MigrationRule` node AND at least one `MigrationStep` child in the **same write transaction**. A rule node without a step child is not a valid outcome of this tool. If the transaction fails (e.g., the `Version` node does not exist), neither node is written.

## Embedding Placement

The embedding vector MUST be stored on `MigrationRule.embedding`, not on `MigrationStep.embedding`. Vector search returns `MigrationRule` element IDs and hydrates `MigrationRule` nodes; placing the embedding on the step child would cause all vector similarity lookups to miss.

When `embedding` is `None` (i.e., `POPULATE_MIGRATION_EMBEDDINGS=false`), the property MUST be omitted from the written node. The write MUST NOT raise an exception in this case.

## Duplicate Detection Index Names

`find_near_duplicate` MUST use the vector index `migration_knowledge_vector_mr` for cosine similarity checks. The index name `migration_knowledge_vector_ci` MUST NOT appear anywhere in the codebase after this spec.

`_best_bm25_duplicate` MUST use the fulltext index `rule_statement` for BM25 duplicate detection. The `migration_text` index MUST NOT be used for this purpose after this spec (it covers a superset of fields that would produce false positives).

## Community Insight Filtering

`get_community_insights` MUST filter by `ruleType='community_insight'`. Returning all `MigrationRule` nodes regardless of `ruleType` is incorrect — it would mix official changelog rules into the community insights feed.

## Property Naming on the Node

All community-sourced metadata MUST use the `community` prefix on the `MigrationRule` node:

| Node property | Exposed as in response |
|---------------|----------------------|
| `communityVotes` | `votes` |
| `communityVerified` | `verified` |
| `communitySubmittedBy` | `submitted_by` |
| `communityCreatedAt` | `created_at` |
| `communityConfidence` | `confidence` |

The query layer (`_QUERY_INSIGHTS`, `_VOTE_INSIGHT`, `_VERIFY_INSIGHT`) is responsible for the alias mapping. The MCP tool layer receives pre-mapped keys and is not aware of the prefixed property names.

## Solution Field Source

The `solution` field in every community insight response MUST be sourced from `MigrationStep.instruction` via `OPTIONAL MATCH (r)-[:REQUIRES_STEP]->(s:MigrationStep)`. Reading `r.solution` directly is incorrect — community insight `MigrationRule` nodes do not have a `solution` property.

A rule with no `MigrationStep` child (which should not occur for community insights but may occur for other rule types) returns `solution` as an empty string or null — it does not cause an error.

## No `CommunityInsight` Label

No code anywhere in the project may create or query nodes with the `CommunityInsight` label after this spec. This includes:
- Cypher query strings
- Index DDL statements
- Test fixtures
- Comments that imply the label is still active

Verified by: `grep -r 'CommunityInsight' migration_oracle/` returning no results.

## Tool Signature Preservation

All four community MCP tool function signatures MUST remain identical to their pre-spec versions:

```python
def submit_migration_insight(statement, spring_boot_version, solution, affected_properties,
    affected_classes, affected_dependencies, evidence_url, confidence, framework) -> dict: ...

def get_community_insights(from_version, to_version, entity_name, entity_type,
    verified_only, framework) -> dict: ...

def vote_insight(insight_id, delta) -> dict: ...

def verify_insight(insight_id) -> dict: ...
```

No `@mcp.tool()` decorator may be altered.

## Streamlit Page Non-Modification

`migration_oracle/streamlit_app/pages/05_community.py` MUST NOT receive any structural changes. The page calls tool functions by Python import; all tool signatures and return shapes are preserved.

## Version-Not-Found Response

When `submit_migration_insight` is called with a `framework`/`spring_boot_version` combination that has no matching `Version` node in the graph, the tool MUST return:

```json
{"status": "error", "insight_id": "", "duplicate_of": "", "message": "Version not found: <framework> <version>"}
```

A bare `RuntimeError` or unhandled exception propagating to the MCP caller is not acceptable.

# Research: Oracle Contract Fixes

**Feature**: `012-oracle-contract-fixes`
**Phase**: Phase 0 — Design Gate Resolution
**Created**: 2026-06-13

---

## Runtime & Target

| Dimension | Value |
|-----------|-------|
| **Neo4j version** | 5.x (Neo4j Community 5, `neo4j:5` Docker image) |
| **Bolt URI** | `bolt://neo4j:7687` (service-name routing inside Docker; `bolt://localhost:7687` on host) |
| **Cypher dialect** | Cypher 5 — no APOC dependency in existing queries; all new queries must work without APOC |
| **Server runtime** | Python 3.11+, `mcp >= 1.0`, `neo4j >= 5.0` driver |
| **Test runner** | `pytest` with `asyncio_mode = auto` (`pytest-asyncio >= 0.23`) |

---

## Decision 1 — FR-014: queriedEntities Write Mechanism

**Decision: New `update_queried_entity` MCP tool**

### Alternatives considered

| Option | Summary | Rejected because |
|--------|---------|-----------------|
| **Write inside `get_steps_for_scope_tier`** | Piggyback the write on the scope-query call | Violates single-responsibility: scope-query is a read; mixing state mutation would make the tool non-idempotent and harder to test |
| **Write inside `update_step_status`** | Couple entity caching to step outcome recording | Wrong lifecycle: an entity is queried in Loop II; the step is acted on in Loop III. They are different events with different callers |
| **Write inside existing `create_migration_context`** | Update on context creation | Cannot know entity results at creation time |
| **New `update_queried_entity` tool** ✅ | Dedicated MCP tool, called by the agent after each Loop II entity query | Clear separation of concerns; explicitly testable; no existing tool semantics are changed |

### Rationale

The `queriedEntities` cache is written from Loop II, after a successful entity query (not during step execution or context creation). A dedicated tool makes this write path:
1. Explicitly invocable and independently testable
2. Visible to the agent as a named action in the session transcript
3. Consistent with the pattern of owning tools for all writes (FR-019)

The `execute_custom_cypher` read-only constraint (FR-019) also rules out ad-hoc writes.

### Concrete specification

**Tool name**: `update_queried_entity`

**Parameters**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `context_id` | string | yes | Element ID of the `MigrationContext` |
| `entity_name` | string | yes | Fully-qualified or display name of the queried entity |
| `result_summary` | string | yes | ≤500 character summary of the query result (e.g. "deprecated in 3.0.0, replaced by …") |

**Returns (success)**:
```json
{
  "status": "ok",
  "context_id": "<element-id>",
  "entity_name": "<name>",
  "cached_count": <integer>
}
```

**Returns (error)**:
```json
{
  "status": "error",
  "error_code": "context_not_found",
  "hint": "Context '<id>' not found"
}
```

**Cypher implementation strategy**: Because `queriedEntities` is stored as a JSON-serialised string and Neo4j 5 without APOC cannot manipulate JSON maps in Cypher, the write is done in two Python steps:

1. **Read** current `queriedEntities` string from the context node.
2. **Parse** as JSON dict in Python.
3. **Upsert** `entity_name → result_summary`.
4. **Write** the updated JSON string back via `SET ctx.queriedEntities = $updated_json`.

This is a two-query operation (one read, one write) inside a single tool call. Because the agent calls this tool serially (one entity at a time), there is no concurrent-write risk — consistent with the concurrency out-of-scope assumption in the spec.

**`queriedEntities` key/value schema**:
```
{
  "<entity_name>": "<result_summary (≤500 chars)>"
}
```
Stored as `JSON.stringify(map)` on `MigrationContext.queriedEntities`. Initialised to `'{}'` at context creation (existing behaviour).

---

## Decision 2 — FR-015: --force-refresh Mechanism

**Decision: Prompt/invocation parameter (agent-level)**

### Alternatives considered

| Option | Summary | Rejected because |
|--------|---------|-----------------|
| **Boolean property on MigrationContext** | `ctx.forceRefresh = true`, cleared after each loop | Persists across sessions unnecessarily; creates a "sticky" state that must be explicitly reset; adds a property not in the current schema; harder for the agent to target one specific entity |
| **Dedicated cache-invalidation tool** | `invalidate_queried_entity(context_id, entity_name)` | An additional tool with a one-shot use case adds surface area without meaningfully improving the agent's ability to re-query; the agent calling `update_queried_entity` after re-querying achieves the same result |
| **Prompt/invocation parameter** ✅ | The agent includes `force_refresh: true` as a parameter when calling the entity-query tool, or mentions `--force-refresh <entity_name>` in the Loop II skill text | Requires no schema change; aligns with the existing skill text which already says "unless `--force-refresh` is set"; agent-controlled, not graph-persisted |

### Rationale

The skill text for Loop II already says "do not re-issue the tool call unless `--force-refresh` is set." This framing treats `--force-refresh` as an agent-level instruction, not a graph property. Keeping it as such:

1. Requires no schema migration or new tool
2. Lets the agent target a single named entity without invalidating the whole cache
3. Consistent with how other agent-level overrides work (e.g. `--stateless-mode`)

### Concrete specification

**Form**: A named parameter `force_refresh: bool = False` added to `get_steps_for_scope_tier`. When `True` for a given entity, the agent:

1. Ignores the cached entry in `queriedEntities` for that entity
2. Re-issues the entity-query tool call as if no cache exists
3. Calls `update_queried_entity` with the fresh result, which **overwrites** the old entry for that key (upsert semantics)

**Where the agent reads `force_refresh`**: As a named parameter on the `get_steps_for_scope_tier` tool call in Loop II. The agent passes `force_refresh=True` when the user explicitly requests a re-query for a named entity (e.g. the user says "re-query org.example.Foo"). The parameter is **not** stored in the graph; it lives only in the current agent invocation.

**Scope**: Single entity per invocation. `force_refresh=True` bypasses the cache check for exactly the entity being processed in the current `get_steps_for_scope_tier` call. Other entities in `queriedEntities` are unaffected.

**Exact reset semantics**:

| Phase | What happens |
|-------|-------------|
| Before re-query | Old cached entry (`entity_name → old_summary`) remains in `queriedEntities` — not pre-deleted |
| Entity tool call | `resolve_deprecation` (or equivalent) is called fresh, ignoring the old entry |
| After re-query | `update_queried_entity(context_id, entity_name, new_summary)` overwrites the old entry in place |
| Net result | `queriedEntities[entity_name]` = new result; one entry total (no duplication) |

**Edge case**: `force_refresh=True` on an entity that was never queried behaves identically to a first-time query. The `update_queried_entity` call writes a new key.

**Skill text update required**: Loop II's skip-guard paragraph must be updated to read: "Check `ctx.queriedEntities[entity_name]`. If present, use the cached result — skip the tool call — unless `force_refresh=True` was passed to this `get_steps_for_scope_tier` call. After any tool call (fresh or forced), call `update_queried_entity` to persist or update the cached result."

**No graph schema change required.**

---

## Decision 3 — Rollback Resource Procedure

**Decision: `git stash push` → build verification → optional `git stash pop`**

### Rationale

When OpenRewrite batch application fails the build:
1. The project's source files have been mutated (OpenRewrite writes in-place)
2. The developer needs to quickly restore a known-good state
3. `git stash push` is the safest standard Git operation for this: it saves the applied diff as a recoverable stash entry rather than discarding it, allowing inspection before discard

### Concrete rollback procedure (for `framework_migration_rollback.md`)

```
1. IDENTIFY what was applied:
   List the recipes that were run in the failed batch.

2. STASH the applied changes:
   git stash push -m "migration-rollback-<step_id>"
   This removes the OpenRewrite mutations and restores the pre-batch state.

3. VERIFY the restore:
   Run the build (mvn test -q / gradle test / npm test).
   Build must pass before proceeding.

4. DECIDE:
   Option A — Retry with fewer recipes:
     git stash drop stash@{0}
     Remove the failing recipe from the batch. Retry.
   Option B — Inspect and fix manually:
     git stash show -p stash@{0}
     Review the diff. Apply the correct subset manually. git stash drop stash@{0}.
   Option C — Full discard:
     git stash drop stash@{0}
     Escalate the step to the manual track.

5. RECORD the outcome:
   Call update_step_status with outcome="failed" and reason="build failed: <error summary>".
```

**URI**: `skill://framework-migration/rollback`
**File**: `migration_oracle/mcp/skills/framework_migration_rollback.md`

The file is auto-discovered by `install_migration_skill` (it copies all `*.md` files from the skills directory), so no code change to the installer is required — only the file must be created.

---

## Decision 4 — Dedup Cosine Similarity Threshold

**Decision: Document as 0.92 (the value already in `community.py`)**

The constant `_DUPLICATE_SIMILARITY_THRESHOLD = 0.92` is already defined in `migration_oracle/mcp/graph/queries/community.py`. The threshold applies to the `all-mpnet-base-v2` sentence-transformer model (768 dimensions).

The dedup pipeline is:
1. Exact-statement match via `_FIND_EXACT_STATEMENT` (always runs first)
2. Vector search using `migration_knowledge_vector_mr` index with `min_similarity=0.92`
3. BM25 shortlist (top-5 by `rule_statement` fulltext index) → cosine similarity check at ≥ 0.92 for each candidate

The threshold value 0.92 is high enough to catch near-verbatim rephrasing while avoiding false positives on unrelated rules. It must be documented in the tool docstring and tool reference so callers can observe the dedup boundary.

**`insight_id` vs `duplicate_of` semantics fix (required)**:

Current incorrect behaviour on `status="duplicate"`:
```json
{ "status": "duplicate", "insight_id": "<duplicate's ID>", "duplicate_of": "<duplicate's ID>" }
```

Correct behaviour (per FR-013):
```json
{ "status": "duplicate", "insight_id": null, "duplicate_of": "<existing insight's element ID>" }
```

`insight_id=null` signals "no new insight was created." `duplicate_of` identifies the existing insight.

---

## Work-Stream Independence Analysis

All six work-streams are mutually independent — they touch disjoint sets of files:

| WS | Files touched | Parallel? |
|----|---------------|-----------|
| WS1 — Version Arithmetic | `migration_oracle/mcp/skills/framework_migration_version_map.md` | [P] |
| WS2 — Graph-State Contract | `migration_oracle/mcp/graph/queries/context.py`, `migration_oracle/mcp/tools/context.py` | [P] |
| WS3 — Query Correctness | `migration_oracle/mcp/graph/queries/context.py` (`_GET_STEPS_FOR_SCOPE_TIER`), `migration_oracle/mcp/tools/context.py`, `migration_oracle/mcp/graph/queries/upgrade.py` (`_ANALYZE_UPGRADE_PATH`) | [P] |
| WS4 — Tool API Alignment | `migration_oracle/mcp/graph/queries/deprecation.py`, `migration_oracle/mcp/graph/queries/search.py`, `migration_oracle/mcp/tools/deprecation.py`, `migration_oracle/mcp/tools/community.py` | [P] |
| WS5 — Resumability | `migration_oracle/mcp/tools/context.py` (new tool), `migration_oracle/mcp/graph/queries/context.py` (new Cypher), `migration_oracle/mcp/skills/framework_migration_main.md` | [P] |
| WS6 — Resilience | `migration_oracle/mcp/skills/framework_migration_rollback.md` (new file), `migration_oracle/mcp/skills/framework_migration_main.md` | [P] |

**Note**: WS2, WS3, and WS5 all touch `context.py` (both tools and queries modules), but their changes are in distinct functions and Cypher strings — they can be implemented in parallel in isolated git branches and merged without conflict.

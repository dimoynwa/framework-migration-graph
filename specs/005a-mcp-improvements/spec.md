# Feature Specification: MCP Server Improvements

**Feature Branch**: `005a-mcp-improvements`
**Created**: 2026-06-07
**Status**: Draft
**Research**: See [research.md](research.md) for the full three-approach comparison and MCP best-practice analysis.

---

## Scope

Two focused improvements to the MCP server:

1. **Parameterized MCP prompts** — Replace the zero-parameter `migration_workflow_prompt()` stub with typed, re-entrant prompts that clients can fill in via a structured form.
2. **Tool docstrings** — Add a docstring to every `@mcp.tool()` function so FastMCP can surface meaningful descriptions to the LLM. Currently all 21 tools have no docstring; the LLM receives only the function name.

No changes to tool logic, graph queries, or transport configuration.

---

## 1. Parameterized MCP Prompts

### Rationale

See [research.md § 1 — Approach 3](research.md#approach-3--mcp-prompts-capability-with-parameters-recommended). The current `migration_workflow_prompt()` in `server.py` is effectively static text with no parameters. LLM clients that support `prompts/list` surface a form; without typed fields the form is empty and the user receives no guidance on what to fill in.

### Implementation

**File**: `migration_oracle/mcp/server.py`

Replace the existing `migration_workflow_prompt` with three prompt handlers:

```python
@mcp.prompt()
def start_migration(
    framework: str,
    current_version: str,
    target_version: str,
    project_id: str,
) -> str:
    """Start a four-loop migration harness for a project.

    framework: e.g. 'Spring Boot', 'WildFly', 'Quarkus'
    current_version: the version the project is migrating FROM, e.g. '2.7'
    target_version: the version the project is migrating TO, e.g. '3.2'
    project_id: unique project identifier used to create or resume a MigrationContext
    """
    return (
        f"Load skill://framework-migration/main.\n\n"
        f"Migrate project '{project_id}' from {framework} {current_version} "
        f"to {framework} {target_version}.\n\n"
        f"Run the four-loop migration harness:\n"
        f"- Loop I: scan the codebase, call create_migration_context\n"
        f"- Loop II: query the graph in scope-gated tiers "
        f"(api-surface → runtime → config/build → test)\n"
        f"- Loop III: execute each pending step (auto or manual; ask me to confirm manual steps)\n"
        f"- Loop IV: submit new insights via submit_migration_insight, "
        f"then call close_migration_context"
    )


@mcp.prompt()
def resume_migration(context_id: str) -> str:
    """Resume a four-loop migration harness from an existing MigrationContext.

    context_id: the UUID returned by create_migration_context or
                get_pending_steps from a previous session.
    """
    return (
        f"Load skill://framework-migration/main.\n\n"
        f"Resume migration context '{context_id}'.\n\n"
        f"Call get_pending_steps(context_id='{context_id}') to see what remains.\n"
        f"Continue from Loop III: execute each pending step, then run Loop IV "
        f"(submit insights, close context)."
    )


@mcp.prompt()
def migration_workflow_prompt() -> str:
    """Zero-parameter fallback for clients that do not support parameterized prompts.

    Prefer start_migration or resume_migration when the client supports parameters.
    """
    return (
        "Load skill://framework-migration/main.\n\n"
        "I want to migrate this project from [framework] [current_version] "
        "to [target_version].\n"
        "Project ID: [your-project-id]\n\n"
        "Run the four-loop migration harness:\n"
        "- Loop I: scan the codebase, create or resume a migration context\n"
        "- Loop II: query the graph in scope-gated tiers "
        "(api-surface → runtime → config/build → test)\n"
        "- Loop III: execute each pending step (auto or manual)\n"
        "- Loop IV: submit any new insights, close the context"
    )
```

---

## 2. Tool Descriptions (Docstrings)

FastMCP uses the function's first docstring line as the `description` field in the `tools/list` response. The full docstring body is not transmitted to the client but is used internally for developer reference.

The descriptions below follow the rules in [research.md § 2](research.md#2-mcp-tool-description-best-practices):
- Imperative first sentence, ≤ 120 characters.
- State what is returned.
- List valid values for closed-set parameters.
- Flag side effects, idempotency, and known limitations.

---

### Upgrade Group

**File**: `migration_oracle/mcp/tools/upgrade.py`

#### `analyze_upgrade_path`

```
Return migration rules and lifecycle alerts for a framework version range.

Queries all MigrationRule nodes whose version range covers [current_version, target_version].
Optionally filter by scope ('api-surface', 'runtime', 'config', 'build', 'test') and
severity ('low', 'medium', 'high', 'critical').

Returns: rules list (statement, steps, scopes, recipes), lifecycle_alerts list.
Each rule contains steps: [] and scopes: [] when no MigrationStep/BreakingScope nodes
exist in the graph (pre-redesign data) — this is expected, not an error.
```

**Why**: Without a docstring the LLM receives only `analyze_upgrade_path`. The description above tells the model what data comes back, which parameters narrow results, and handles the "empty steps" confusion that would otherwise cause retry loops.

#### `build_recipe_plan`

```
Produce a two-track migration plan: auto (scriptable) and manual (human review required).

Auto track: steps with automatable=true, effort=mechanical, and a linked OpenRewrite recipe.
Manual track: all other steps. Falls back to rule-level cards when no MigrationStep nodes exist.

Returns: auto_track list, manual_track list, fallback_to_rule_cards bool.
An empty auto_track is expected in the first release (no AUTOMATED_BY edges yet).
```

**Why**: "Two-track" and "fallback" are key concepts the model needs to reason about Loop III branching. Without the description the model cannot distinguish auto from manual steps.

---

### Deprecation Group

**File**: `migration_oracle/mcp/tools/deprecation.py`

#### `resolve_deprecation`

```
Return deprecation metadata and replacement for a single entity name (one hop only).

Returns: deprecated_in, removed_in, replaced_by (direct successor only), and related rules.
For the full replacement chain across multiple versions use entity_evolution instead.
Returns status='not_found' when the entity is not in the graph.
```

**Why**: "One hop" vs "full chain" is the key disambiguation. Without it the model may call `resolve_deprecation` when it needs `entity_evolution`, or vice versa.

#### `entity_evolution`

```
Trace the full REPLACED_BY replacement chain for an entity, up to 5 hops.

Returns: chain list where each node includes entity_name, entity_type, deprecated_in,
removed_in, and related rules. The chain starts at entity_name and follows REPLACED_BY
edges until the terminus or the 5-hop limit.
```

**Why**: The 5-hop limit is an undocumented constraint that the model would otherwise not know about. Stating it prevents the model from assuming arbitrarily long chains are possible.

---

### Search Group

**File**: `migration_oracle/mcp/tools/search.py`

#### `search_migration_knowledge`

```
Search migration rules and community insights using hybrid BM25 + vector ranking (RRF).

Returns up to max_results hits ordered by Reciprocal Rank Fusion score. Each hit
includes: statement, action_step, source_url, node_type, score.
Vector search requires embeddings; if embeddings were not generated (POPULATE_MIGRATION_EMBEDDINGS=false),
only BM25 results are returned. Set include_community_insights=False to exclude CommunityInsight nodes.
```

**Why**: The hybrid search mechanism, the fallback to BM25-only, and the `include_community_insights` flag are all invisible without a docstring. The model needs to know what it gets back to chain this call with `submit_migration_insight`.

#### `search_openrewrite_recipes`

```
Search OpenRewrite recipe descriptions using hybrid BM25 + vector ranking (RRF).

Returns up to max_results recipe hits with statement and score.
Note: only_composite and require_no_params filters are accepted but not yet applied —
all matching recipes are returned regardless of those values (deferred to a future release).
```

**Why**: The `only_composite` and `require_no_params` no-op situation is a silent gotcha. If the model passes these and trusts the filter, it will act on wrong data. Disclosing this up front is the honest and safe behavior.

---

### Schema Group

**File**: `migration_oracle/mcp/tools/schema.py`

#### `get_graph_schema`

```
Return the authoritative graph schema as a Markdown string. No Cypher is executed.

Use this before execute_custom_cypher to understand available node labels, relationship
types, and property names. Returns: schema_markdown string.
```

**Why**: "No Cypher executed" tells the model this is safe and fast. "Use before execute_custom_cypher" gives the model a workflow hint that reduces schema hallucination errors.

#### `execute_custom_cypher`

```
Execute a read-only Cypher query against the graph and return rows.

Blocked keywords (returns status='blocked'): CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL db.
Only SELECT-equivalent MATCH queries are permitted. Returns: rows list, row_count.
Call get_graph_schema first to verify node labels and property names before writing a query.
```

**Why**: Without listing the blocked keywords the model may attempt mutations and receive an opaque `blocked` status, triggering confused retries. Enumerating the keywords eliminates that loop.

---

### Community Group

**File**: `migration_oracle/mcp/tools/community.py`

#### `submit_migration_insight`

```
Submit a developer-contributed migration insight. Writes a CommunityInsight node.

Near-duplicate detection runs before write; returns status='duplicate' if a
similar insight already exists (cosine similarity threshold). Not idempotent —
call once per unique finding.

Note: the parameter 'spring_boot_version' holds the framework version string
regardless of the 'framework' value (e.g. '3.2' for Spring Boot, '30' for WildFly).
```

**Why**: The `spring_boot_version` parameter name is a historical accident — it is confusing when `framework` is not Spring Boot. The docstring makes the intent explicit until the parameter is renamed in a future breaking-change release.

#### `get_community_insights`

```
Query CommunityInsight nodes by version range, entity name, or verified status. Read-only.

Returns: insights list with statement, solution, votes, verified, confidence, version.
Note: entity_type filter is accepted but not yet applied — all entity types are returned.
Use verified_only=True to return only moderator-approved insights.
```

**Why**: Same pattern as `search_openrewrite_recipes` — an accepted-but-no-op parameter needs disclosure.

#### `vote_insight`

```
Increment or decrement the votes count on a community insight. Not idempotent.

delta=1 for upvote, delta=-1 for downvote. Calling twice with delta=1 adds 2 votes.
Returns: insight_id, new_vote_count.
```

**Why**: Negative delta for downvote is invisible from the function signature alone. The idempotency warning prevents double-voting bugs in agentic loops.

#### `verify_insight`

```
Mark a community insight as verified (moderator operation). Sets verified=true.

This is a write operation and is not reversible via this tool.
Returns: insight_id, verified (always true on success).
```

**Why**: "Moderator operation" and "not reversible" are important constraints that prevent misuse in automated pipelines.

---

### Context Group

**File**: `migration_oracle/mcp/tools/context.py`

#### `create_migration_context`

```
Create or resume a MigrationContext for a (project_id, from_version, to_version) triple. Idempotent.

If a context with the same triple already exists, returns it unchanged (created=False).
Pass scanned_entities from Loop I codebase scan to seed the context with project-specific entities.
Returns: context_id (use in all subsequent context tool calls), migration_status, scanned_entities.
```

**Why**: Idempotency is the key guarantee that makes Loop I re-entrant. `context_id` is the thread that connects all subsequent calls — stating "use in all subsequent context tool calls" makes the chaining explicit.

#### `get_pending_steps`

```
Return the remaining step queue for a context, ordered by scope severity then topological order.

Excludes completed and skipped steps. Returns an empty list when:
  (a) all steps are done, or
  (b) no MigrationStep nodes exist in the graph (pre-redesign data — use build_recipe_plan instead).
Supports effort_filter (e.g. ['mechanical']) and scope_filter (e.g. ['api-surface']) to narrow results.
```

**Why**: The empty-list ambiguity between "all done" and "no data" is the most common source of agent confusion. Naming both cases and providing the fallback tool name (`build_recipe_plan`) prevents stuck loops.

#### `update_step_status`

```
Record the outcome of a migration step: 'completed', 'skipped', or 'failed'.

Auto-closes the context when no pending steps remain after this call.
The 'reason' parameter is accepted but not persisted in the current release.
Returns: step_id, outcome, context_auto_closed, context_status, completed_count, skipped_count.
```

**Why**: Auto-close behavior is invisible without documentation. The model needs to know the context may close so it doesn't call `close_migration_context` redundantly.

#### `get_steps_for_scope_tier`

```
Return steps for a specific scope tier at or above a severity threshold.

Valid scope values: 'api-surface', 'runtime', 'config', 'build', 'test'.
Valid severity_threshold values: 'low', 'medium', 'high', 'critical'.
Returns: entities list (unique entity names with hits), hits list (entity+step pairs), rule_count.
Use in Loop II to query one tier at a time before calling analyze_upgrade_path for that tier.
```

**Why**: Without the valid values list, the model invents scope strings like `"api_surface"` or `"API"`. The `"Use in Loop II"` hint gives the model the correct call order.

#### `close_migration_context`

```
Set completedAt, migration_status, and notes on a context. Call at the end of every session.

final_status: 'complete' (all steps done) or 'partial' (steps were skipped or deferred).
Note: update_step_status auto-closes the context when all steps complete — call this tool
explicitly only when ending a session with skipped steps or adding notes.
Returns: context_id, migration_status, completed_steps, skipped_steps, completed_at, notes.
```

**Why**: The distinction between auto-close and explicit close is confusing without explanation. Stating when to call this tool (only for partial/notes cases) prevents double-close calls.

---

### Paysafe Group

**File**: `migration_oracle/mcp/tools/paysafe.py`

#### `resolve_paysafe_dependency_by_service_name`

```
Resolve a com.paysafe.* dependency via FindIt and GitLab. Returns repo, tags, and migration guidance.

Requires FINDIT_AUTH_TOKEN and GITLAB_API_KEY environment variables. Returns an error dict if either is missing.
Pass target_version to filter returned tags to those compatible with that framework version.
The tool delegates entirely to the Paysafe resolver — check resolver logs for root-cause errors.
```

**Why**: The env-var requirement is the most common failure mode. Stating it up front prevents the model from blaming the tool or retrying without fixing configuration.

---

### Artifacts Group

**File**: `migration_oracle/mcp/tools/artifacts.py`

#### `list_pipeline_runs`

```
List all Version nodes that have pipeline artifact paths stored in the graph.

A pipeline run is a processed (framework, version) pair that has at least one artifact
path (raw_md, filtered_md, or entities_json). Returns: runs list with framework, to_version,
and path fields. Use to discover available artifact keys before calling get_artifact_content.
```

**Why**: "What is a pipeline run" is unanswerable without this definition. The model needs it to chain `list_pipeline_runs` → `get_artifact_content` correctly.

#### `get_artifact_content`

```
Read a pipeline artifact by type. The file path is resolved from the graph — no direct path accepted.

artifact_type: 'raw_md' | 'filtered_md' | 'entities_json'.
The path is read from the Version node in the graph; callers cannot supply an arbitrary filesystem path.
Returns: content (full text), path_resolved, status ('ok' | 'not_found' | 'error').
```

**Why**: "No direct path accepted" is a security constraint that must be explicit so the model does not attempt path injection.

---

### Install Group

**File**: `migration_oracle/mcp/tools/install.py`

#### `install_migration_skill`

```
Copy bundled skill Markdown files to the Cursor or Claude Code skills directory.

target: 'auto' (detect from environment), 'cursor', or 'claude-code'.
'auto' checks for .cursor or .claude directories in CWD and HOME; defaults to 'cursor' if neither found.
Returns: installed_paths list, target (resolved). Use once after first connecting to the server.
```

**Why**: Valid `target` values and the auto-detection logic are undiscoverable without the docstring. The "use once" hint prevents repeated installation calls in harness loops.

---

## 3. Acceptance Criteria

1. `tools/list` returns 21 tools; each tool has a non-empty `description` field.
2. `prompts/list` returns 3 prompts: `start_migration`, `resume_migration`, `migration_workflow_prompt`.
3. `start_migration` with all four required parameters returns a ready-to-send prompt string with no unfilled placeholders.
4. `resume_migration` with a `context_id` returns a prompt that references the ID directly.
5. `migration_workflow_prompt` (no parameters) returns the same static text as before.
6. No tool logic changes — all existing tests pass unmodified.

---

## 4. Out of Scope

- Renaming `spring_boot_version` to `version` in `submit_migration_insight` (breaking parameter change — defer to 006).
- Implementing `only_composite` / `require_no_params` filtering in `search_openrewrite_recipes` (graph data gap — defer).
- Implementing `entity_type` filtering in `get_community_insights` (graph data gap — defer).
- Persisting the `reason` field in `update_step_status` (graph schema extension — defer).

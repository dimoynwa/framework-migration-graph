# PaysafeMigrationOracle — Evaluation Results

Date: 2026-06-07  
Model: claude-sonnet-4-6  

---

## Layer 0 — Schema Audit

**Tools:** 21/21 registered ✓  
**Prompts:** 3/3 registered (`start_migration`, `resume_migration`, `migration_workflow_prompt`) ✓  
**Descriptions ≥ 20 chars:** 21/21 ✓  
**`start_migration` args:** `{framework, current_version, target_version, project_id}` ✓

**Non-imperative first-word violations (6 tools):**

| Tool | Actual first word | Better |
|---|---|---|
| `build_recipe_plan` | "Produce" | "Build" |
| `close_migration_context` | "Set" | "Close" |
| `get_community_insights` | "Query" | "Return" |
| `install_migration_skill` | "Copy" | "Install" |
| `update_step_status` | "Record" | "Update" or "Mark" |
| `vote_insight` | "Increment" | "Vote" |

These all pass the lint test (words are in the allowed list), but per the EVALUATION.md checklist the preferred pattern is a verb that matches the tool name itself.

**Checklist items — all met:**
- ✓ Closed-set params enumerated: `scope`, `severity_threshold`, `artifact_type`, `outcome`, `final_status`, `target` all enumerate valid values
- ✓ Write side effects flagged: `submit_migration_insight` ("Writes"), `verify_insight` ("write operation"), `vote_insight` ("Not idempotent")
- ✓ Read-only tools declared: `get_community_insights`, `execute_custom_cypher`, `get_graph_schema`
- ✓ Env vars named: `resolve_paysafe_dependency_by_service_name` names `FINDIT_AUTH_TOKEN` and `GITLAB_API_KEY`; `search_migration_knowledge` names `POPULATE_MIGRATION_EMBEDDINGS`
- ✓ Non-ok statuses disclosed: `get_artifact_content` (`ok|not_found|error`), `execute_custom_cypher` (`blocked`), `resolve_deprecation` (`not_found`), `submit_migration_insight` (`duplicate`)
- ✓ No-op params disclosed: `get_community_insights` (`entity_type`), `search_openrewrite_recipes` (`only_composite`, `require_no_params`), `update_step_status` (`reason`)

---

## Layer 1 — Contract Tests

**58/58 tests pass** (53 original + 5 new schema lint tests)

---

## Layer 2 — Tool Selection (inline assessment)

Evaluating all 21 scenarios against the tool descriptions:

| # | Scenario | Expected | Verdict | Notes |
|---|---|---|---|---|
| 1 | "migration rules from Spring Boot 2.7 to 3.2" | `analyze_upgrade_path` | ✓ | Clear match — "version range" |
| 2 | "what replaced WebSecurityConfigurerAdapter" | `resolve_deprecation` | ✓ | "single entity", "one hop only" |
| 3 | "Trace the full deprecation chain for WebMvcConfigurerAdapter" | `entity_evolution` | ✓ | "full REPLACED_BY chain" and "Trace" keyword align |
| 4 | "Search for guidance on actuator endpoint security in Boot 3" | `search_migration_knowledge` | ✓ | "Search migration rules and community insights" |
| 5 | "Find an OpenRewrite recipe for Spring Security migration" | `search_openrewrite_recipes` | ✓ | "Search OpenRewrite recipe descriptions" |
| 6 | "Start a migration session for project payments-service from 2.7 to 3.2" | `create_migration_context` | ✓ | "Create or resume a MigrationContext" |
| 7 | "What steps are still pending for context abc-123?" | `get_pending_steps` | ✓ | "remaining step queue for a context" |
| 8 | "Mark step step-42 as completed" | `update_step_status` | ⚠️ | Description says "Record the outcome" — "Mark" (the natural verb) doesn't appear. Risk of `close_migration_context` or `verify_insight` being selected |
| 9 | "What api-surface steps are critical for context abc-123?" | `get_steps_for_scope_tier` | ✓ | "specific scope tier...severity threshold" |
| 10 | "Close the migration context, we skipped the test steps" | `close_migration_context` | ✓ | Tool name contains "close" even if description starts with "Set" |
| 11 | "Build me a migration plan split into auto and manual tracks" | `build_recipe_plan` | ✓ | "two-track migration plan: auto...and manual" |
| 12 | "What does the graph schema look like?" | `get_graph_schema` | ✓ | Unambiguous |
| 13 | "Run this Cypher: MATCH (r:MigrationRule) RETURN r LIMIT 5" | `execute_custom_cypher` | ✓ | Unambiguous |
| 14 | "Submit an insight: SecurityFilterChain registration changed in 3.0" | `submit_migration_insight` | ✓ | "Submit" in tool name + scenario |
| 15 | "Show me community insights for Spring Boot 3.x" | `get_community_insights` | ✓ | "CommunityInsight nodes by version range" |
| 16 | "Upvote insight insight-99" | `vote_insight` | ⚠️ | Description says "Increment or decrement" not "upvote" — but tool name `vote_insight` + `delta=1 for upvote` in description covers it |
| 17 | "Approve insight insight-99 as verified" | `verify_insight` | ✓ | "Mark as verified (moderator operation)" |
| 18 | "Resolve the com.paysafe dependency for payments-core" | `resolve_paysafe_dependency_by_service_name` | ✓ | "com.paysafe.* dependency" |
| 19 | "List all pipeline artifacts we have stored" | `list_pipeline_runs` | ⚠️ | Tool is named "list_pipeline_runs" but scenario says "artifacts" — `get_artifact_content` could also match. Description cross-reference "Use to discover available artifact keys before calling `get_artifact_content`" mitigates this |
| 20 | "Read the filtered migration document for Spring Boot 3.2" | `get_artifact_content` | ✓ | `artifact_type: 'filtered_md'` aligns with "filtered migration document" |
| 21 | "Install the migration skill for Claude Code" | `install_migration_skill` | ✓ | "Copy bundled skill Markdown files...to Claude Code skills directory" |

**Projected accuracy: 21/21 (100%)** — the 3 flagged items (⚠️) have sufficient signal in context to resolve correctly, but represent latent risks worth hardening.

---

## Key Findings & Recommendations

**High priority (EVALUATION.md Common Failure Mode matches):**

1. **Scenario 8 `update_step_status`** — description says "Record the outcome" but the natural user phrasing is "mark as completed/done." Add "Mark a step outcome" or "Update or mark a step as 'completed'" to the first sentence. This is the exact *wrong-tool-in-group* failure mode documented in EVALUATION.md.

2. **Scenario 19 `list_pipeline_runs`** — "List all pipeline artifacts" could pull `get_artifact_content` first. The cross-reference "Use to discover available artifact keys before calling `get_artifact_content`" mitigates this but the tool name (`list_pipeline_runs`) doesn't contain "artifacts." Consider renaming or adding "artifacts" to the description's first sentence.

3. **6 non-imperative first words** — rewrite to match the tool name verb (e.g., `vote_insight` → "Vote on a community insight: delta=1 upvotes, delta=-1 downvote.").

---

## Artifacts Created

- `tests/mcp/test_schema_lint.py` — 5 Layer 0 schema lint tests (all passing)
- `eval/run_tool_selection.py` — Layer 2 tool selection eval script

To run Layer 2 when `ANTHROPIC_API_KEY` is available:

```bash
export ANTHROPIC_API_KEY=<your-key>
uv run python eval/run_tool_selection.py --ci
```

---

## Metrics Summary

| Metric | Target | Result |
|---|---|---|
| Description coverage (≥ 20 chars) | 100% | 100% ✓ |
| Tool count | 21 | 21 ✓ |
| Prompt count | 3 | 3 ✓ |
| Contract tests passing | 100% | 58/58 ✓ |
| Tool selection accuracy (projected) | ≥ 95% | 21/21 (100%) ✓ |
| Imperative first-word compliance | 100% | 15/21 (71%) ✗ |

# PaysafeMigrationOracle — Evaluation Results

Date: 2026-06-08
Model: claude-sonnet-4-6 (inline evaluation — no API key required)

---

## Layer 0 — Schema Audit

**Tools:** 21/21 registered ✓  
**Prompts:** 3/3 registered ✓  
**Descriptions ≥ 20 chars:** 21/21 ✓  
**Imperative first-word compliance:** 21/21 ✓  

### Automated schema lint

```
5/5 tests/mcp/test_schema_lint.py tests PASSED
```

### Checklist violations

| Tool | Failing item | Suggested fix |
|---|---|---|
| All 21 tools | Every parameter has an empty description — parameter-level descriptions are entirely absent | Add `description=` to every `Annotated[T, Field(...)]` or parameter annotation |
| `submit_migration_insight` | Parameter named `spring_boot_version` but used for all frameworks (WildFly, Quarkus, etc.) | Rename to `version`; the docstring note is a fragile workaround |
| `close_migration_context` | `final_status` description lists only `'complete'` and `'partial'`; implementation accepts any string (e.g. `'abandoned'`) | Add `'abandoned'` to the enumeration in the docstring |
| `close_migration_context` | Returns list omits `tool_status` key — actual return dict uses `tool_status` (not `status`) as error discriminator | Add `tool_status` to the Returns line |
| `get_community_insights` | Description does not distinguish its use case from `search_migration_knowledge` (which also returns community insights) | Add "Use this tool to browse by version or entity name; use `search_migration_knowledge` for free-text queries" |
| `vote_insight` | `delta` parameter has no per-parameter description | Add parameter-level description: `delta: 1 for upvote, -1 for downvote` |
| `update_step_status` | `outcome` parameter has no per-parameter description | Add parameter-level description enumerating `completed`, `skipped`, `failed` |
| `get_artifact_content` | `artifact_type` parameter has no per-parameter description | Add parameter-level description: `'raw_md' \| 'filtered_md' \| 'entities_json'` |
| `get_steps_for_scope_tier` | `scope` and `severity_threshold` valid values are in the docstring body only, not in parameter-level fields | Add parameter-level descriptions enumerating valid values for both parameters |

---

## Layer 1 — Contract Tests

**58/58 tests pass**

```
tests/mcp/test_artifacts.py        5 passed
tests/mcp/test_community.py        4 passed
tests/mcp/test_context.py          7 passed
tests/mcp/test_deprecation.py      3 passed
tests/mcp/test_paysafe_tool.py     2 passed
tests/mcp/test_schema.py          10 passed
tests/mcp/test_schema_lint.py      5 passed
tests/mcp/test_search.py           3 passed
tests/mcp/test_server.py           5 passed
tests/mcp/test_skill_harness.py    7 passed
tests/mcp/test_upgrade.py          6 passed

Total: 58 passed in 8.66s
```

No failures.

---

## Layer 2 — Tool Selection

Evaluation method: inline judgment against live descriptions loaded from the running MCP server. Each verdict is based solely on reading the tool descriptions — tool names were not used as tiebreakers.

| # | Scenario | Expected | Verdict | Risk / Notes |
|---|---|---|---|---|
| 1 | I need to find migration rules for going from Spring Boot 2.7 to 3.2 | `analyze_upgrade_path` | ✓ | "Return migration rules…for a framework version range" maps exactly |
| 2 | Show me what replaced WebSecurityConfigurerAdapter | `resolve_deprecation` | ⚠️ | `entity_evolution` ("Trace the full REPLACED_BY chain") is tempting for "what replaced X"; description cross-references the distinction but a rephrasing could flip the pick |
| 3 | Trace the full deprecation chain for WebMvcConfigurerAdapter | `entity_evolution` | ✓ | "full…chain" wording matches description's "full REPLACED_BY replacement chain" literally |
| 4 | Search for guidance on actuator endpoint security in Boot 3 | `search_migration_knowledge` | ✓ | "guidance" vs "OpenRewrite recipe descriptions" is unambiguous |
| 5 | Find an OpenRewrite recipe for the Spring Security migration | `search_openrewrite_recipes` | ✓ | "OpenRewrite recipe" explicit in both scenario and description |
| 6 | Start a migration session for project payments-service from 2.7 to 3.2 | `create_migration_context` | ✓ | "Create or resume a MigrationContext for a (project_id, from_version, to_version) triple" is clear |
| 7 | What steps are still pending for context abc-123? | `get_pending_steps` | ✓ | "remaining step queue for a context" matches; `get_steps_for_scope_tier` requires a scope not given |
| 8 | Mark step step-42 as completed | `update_step_status` | ✓ | First line enumerates 'completed'/'skipped'/'failed'; no ambiguity |
| 9 | What api-surface steps are critical for context abc-123? | `get_steps_for_scope_tier` | ✓ | 'api-surface' named as a valid scope value in the description |
| 10 | Close the migration context, we skipped the test steps | `close_migration_context` | ✓ | "Call at the end of every session" is explicit; 'partial' correctly implied |
| 11 | Build me a migration plan split into auto and manual tracks | `build_recipe_plan` | ✓ | "two-track migration plan: auto…and manual" is a literal match |
| 12 | What does the graph schema look like? | `get_graph_schema` | ✓ | Only tool returning "graph schema as a Markdown string" |
| 13 | Run this Cypher: MATCH (r:MigrationRule) RETURN r LIMIT 5 | `execute_custom_cypher` | ✓ | "Execute a read-only Cypher query" is the only match |
| 14 | Submit an insight: SecurityFilterChain registration changed in 3.0 | `submit_migration_insight` | ✓ | Tool selection unambiguous; `spring_boot_version` param naming is a Layer 3 risk |
| 15 | Show me community insights for Spring Boot 3.x | `get_community_insights` | ⚠️ | `search_migration_knowledge` also mentions community insights; version-filter phrasing helps but "search for community insights about Boot 3" rephrasing would pick the wrong tool |
| 16 | Upvote insight insight-99 | `vote_insight` | ✓ | "Increment or decrement the votes count" maps cleanly; delta=1 stated |
| 17 | Approve insight insight-99 as verified | `verify_insight` | ✓ | "moderator operation…Sets verified=true" is explicit |
| 18 | Resolve the com.paysafe dependency for payments-core | `resolve_paysafe_dependency_by_service_name` | ✓ | "com.paysafe.*" in both scenario and description |
| 19 | List all pipeline artifacts we have stored | `list_pipeline_runs` | ✓ | "List all Version nodes that have pipeline artifact paths" matches |
| 20 | Read the filtered migration document for Spring Boot 3.2 | `get_artifact_content` | ✓ | 'filtered_md' is listed; "no direct path accepted" is present |
| 21 | Install the migration skill for Claude Code | `install_migration_skill` | ✓ | "Claude Code skills directory" explicit |

**Confirmed correct: 21/21 (100%)**  
**Latent risk (⚠️): 2 tools** — `resolve_deprecation` (#2) and `get_community_insights` (#15)  
**Failures (✗): 0 tools**

### ⚠️ Fix recommendations

**#2 — `resolve_deprecation`:** Move the one-hop distinction to the first sentence:
> *"Return deprecation metadata and the immediate replacement for a single entity (one hop only). For a multi-hop chain use `entity_evolution`."*

The cross-reference already exists in sentence 3; promoting it to sentence 1 removes the risk entirely.

**#15 — `get_community_insights`:** Add a use-case differentiator:
> *"Query CommunityInsight nodes by version range, entity name, or verified status. Read-only. Use this tool to browse insights by version or entity; for free-text keyword search across rules and insights use `search_migration_knowledge`."*

---

## Layer 3 — Parameter Correctness

### Closed-set parameters

| Parameter | Tool | Enumerated in description? | Risk |
|---|---|---|---|
| `scope` | `get_steps_for_scope_tier` | ✓ in docstring body | Low |
| `severity_threshold` | `get_steps_for_scope_tier` | ✓ in docstring body | Low |
| `outcome` | `update_step_status` | ✓ in first line | Low |
| `artifact_type` | `get_artifact_content` | ✓ in docstring body | Low — not in parameter field |
| `final_status` | `close_migration_context` | ⚠️ 'complete' and 'partial' only; 'abandoned' accepted but undocumented | Medium |
| `delta` | `vote_insight` | ✓ in docstring body | Low |
| `target` | `install_migration_skill` | ✓ in docstring body | Low |
| `scope_filter` | `analyze_upgrade_path`, `get_pending_steps` | ⚠️ referenced but valid values not repeated | Low-medium |

### Hallucination-prone parameters

| Parameter | Tool | Constraint quality | Risk |
|---|---|---|---|
| `query` | `execute_custom_cypher` | ✓ All blocked keywords listed in description | Low |
| `spring_boot_version` | `submit_migration_insight` | ✗ Misleadingly named for non-Spring frameworks | Medium — model may omit or misinterpret when framework is WildFly/Quarkus |
| `context_id` threading | all context tools | ✓ `create_migration_context` explicitly says "Returns: context_id — use in all subsequent context tool calls" | Low |

### Systematic gap: zero parameter-level descriptions

Every parameter across all 21 tools has an empty `description` field in the JSON schema. All constraints live in the tool-level docstring only. This means:

- MCP clients that display per-parameter help (e.g. some IDE integrations) show nothing.
- Valid-value constraints are invisible at the parameter level in the schema.
- Risk is latent — current docstrings are complete enough for Claude — but adding `Field(description=...)` annotations would make the server robust against partial-schema clients.

---

## Key Findings & Recommendations

**Priority 1 — Latent tool-selection risks (will cause failures under rephrasing):**

1. **`resolve_deprecation` vs `entity_evolution`** — Promote the one-hop vs full-chain distinction to the first sentence of `resolve_deprecation`.
2. **`get_community_insights` vs `search_migration_knowledge`** — Add a use-case differentiator sentence to `get_community_insights`.

**Priority 2 — Undocumented parameter values (cause wrong parameter construction):**

3. **`close_migration_context.final_status`** — Add `'abandoned'` to valid values; add `tool_status` to the Returns list.
4. **`submit_migration_insight.spring_boot_version`** — Rename to `version` or add a parameter-level description; the docstring workaround is fragile under tool-call generation.

**Priority 3 — Description quality (no breakage today, improves robustness):**

5. **All parameter descriptions are empty** — Add `Field(description=...)` for all closed-set parameters (`outcome`, `artifact_type`, `scope`, `severity_threshold`, `final_status`, `delta`, `target`).
6. **`scope_filter` and `min_severity` valid values** not repeated in `analyze_upgrade_path` and `get_pending_steps` — copy the enumeration from `get_steps_for_scope_tier`.

---

## Metrics Summary

| Metric | Target | Result |
|---|---|---|
| Description coverage (≥ 20 chars) | 100% | 21/21 ✓ |
| Tool count | 21 | 21 ✓ |
| Prompt count | 3 | 3 ✓ |
| Imperative first-word compliance | 100% | 21/21 ✓ |
| Contract tests passing | 100% | 58/58 ✓ |
| Tool selection accuracy (projected) | ≥ 95% | 21/21 (100%) |
| Latent-risk tools (⚠️) | 0 | 2 |
| Parameter-level descriptions present | 100% | 0/21 tools ✗ |
| Undocumented closed-set values | 0 | 2 (`final_status` missing 'abandoned', `spring_boot_version` misleading name) |

# Contracts: Split Migration Harness

## Tool-to-Session Exposure Matrix

This matrix defines which MCP tools are exposed and executable during each of the six session-scoped entry points. 

**Important Note**: The existing tool contracts for `plan`, `execute`, and `feedback` are **unchanged**. This contract only adds rows/columns for the new stages and tools; it never removes or narrows an existing tool's contract.

| Tool Name | `plan` | `gap-check` | `clarify` | `preview` | `execute` | `feedback` |
|-----------|--------|-------------|-----------|-----------|-----------|------------|
| `analyze_upgrade_path` | ✅ | ❌* | ❌ | ❌ | ❌ | ❌ |
| `build_recipe_plan` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `resolve_deprecation` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `entity_evolution` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `search_migration_knowledge` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `search_openrewrite_recipes` | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| `get_graph_schema` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `execute_custom_cypher` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `submit_migration_insight` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `get_community_insights` | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| `vote_insight` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `verify_insight` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `create_migration_context` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `get_pending_steps` | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `update_step_status` | ❌ | ❌ | ✅ | ❌ | ✅ | ❌ |
| `get_steps_for_scope_tier` | ✅ | ✅** | ❌ | ❌ | ❌ | ❌ |
| `close_migration_context` | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| `resolve_paysafe_dependency_by_service_name` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `list_pipeline_runs` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `get_artifact_content` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `install_migration_skill` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `update_queried_entity` | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `get_migration_contexts` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `add_manual_step` (NEW) | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| `write_gap_check_flags` (NEW)*** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |

*\* `analyze_upgrade_path` is explicitly excluded from `gap-check` to avoid re-running the expensive plan tool. Instead, `gap-check`'s truncation check reads the originally returned count/top_n value already cached on the context.*
*\*\* `get_steps_for_scope_tier` is exposed to `gap-check` to enable tier-bucketed step reads required for the stepless-rule and bridge-eligibility checks.*
*\*\*\* Assuming a dedicated tool or extension to `update_migration_context` is created to persist the gap-check flags.*

**Preview Stage Constraint**: As shown above, the `preview` row is strictly `false` for all mutation tools. It only exposes `get_pending_steps` and `get_migration_contexts`.
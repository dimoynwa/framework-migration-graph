---
name: framework-migration-plan
description: >
  Plan stage — scan codebase, create or resume a MigrationContext, and run
  scope-gated graph queries (Loops I and II). Use when starting a new migration
  or refreshing entity scope before gap-check.
compatibility:
  tools:
    - analyze_upgrade_path
    - build_recipe_plan
    - resolve_deprecation
    - entity_evolution
    - search_migration_knowledge
    - search_openrewrite_recipes
    - get_graph_schema
    - execute_custom_cypher
    - get_community_insights
    - create_migration_context
    - get_steps_for_scope_tier
    - resolve_paysafe_dependency_by_service_name
    - list_pipeline_runs
    - get_artifact_content
    - install_migration_skill
    - update_queried_entity
    - get_migration_contexts
---

# Plan Stage — Context and Scope-Gated Query

**Stage gating** — this skill is read by two audiences:

- **Launching the server:** set `MCP_ACTIVE_STAGE=plan` in the environment (or pass it to your start/redeploy script) before the MCP server process starts. Tool registration is fixed at startup; it cannot be changed mid-session.

- **Already connected:** if you are an agent with a server already running, do not restart it — infer the active stage from which tools in `compatibility.tools` are available. If a required tool is missing, stop and report a stage mismatch; do not substitute tools from another stage.

After plan completes, proceed to the `framework-migration-gap-check` bundle.

## Loop I — Context

**Purpose:** Load or create a `MigrationContext`. Run the codebase scan. Surface version boundary pre-conditions.

**Step 0 — Preflight**

Before starting the codebase scan:

a. Run `python3 --version` to confirm Python 3 is available.
b. Check PyYAML: run `python3 -c 'import yaml'`. If that fails, install with `python3 -m pip install --quiet pyyaml`.
c. Report the chosen extractor: `"Extractor: python"` or `"grep-gnu"` / `"grep-bsd"`.

**Step 1 — Context discovery and supersede**

a. Call `get_migration_contexts(project_id=<id>)` to list all prior contexts.
b. If `count=0`: proceed directly to scan + create.
c. If `count>0`: surface the list to the engineer.
   - For each context with `status="in-progress"` or `status="blocked"`: show `id`, `fromVersion`, `toVersion`, `createdAt`, `updatedAt`, `outcome_counts`.
   - If a stale context has the **wrong triple**: call `close_migration_context(context_id, final_status="abandoned")`.
   - If the **intended triple** already exists with `status="in-progress"`: resume via MERGE — call `create_migration_context` with the same triple (`created=false`).
   - If the intended triple exists with `status="complete"`: surface summary and stop.
d. After abandoning stale contexts, call `create_migration_context` with the intended triple.

**Step 2 — Status check**

If the loaded context is `status=complete`: surface summary. Do not proceed to Loop II.

**Step 3 — Codebase scan**

Run the codebase scan. Use patterns from `references/scanning.md`: FQCNs from import lines, annotations without `@`, dotted property keys, `groupId:artifactId` without versions, exact npm package names.

**Step 4 — Entity diff**

If resuming: diff the new scan against `ctx.scannedEntities`. New entities are queued for Loop II.

**Step 5 — Version map**

Load `references/version-map.md`. Surface toolchain pre-conditions before proceeding.

**Step 6 — Create context**

Call `create_migration_context` with the scanned entity list. Surface `co_migration_warning` and `droppedCount` if present.

### Loop I — STATELESS FALLBACK

**Trigger**: `create_migration_context` returns an error on both the initial attempt and one retry.

1. Log: "Context creation failed; continuing in stateless mode."
2. Continue with `analyze_upgrade_path` and `build_recipe_plan` using scanned entities.
3. Skip all tools requiring `context_id`.
4. Track step state in agent memory only.
5. Call `submit_migration_insight` for high-confidence findings without `context_id`.

**Gate:** Never call any graph query tool before this loop completes.

## Loop II — Scope-gated query

**Purpose:** Query the graph for migration rules affecting scanned entities, in priority order by blast radius.

| Tier | Scope filter | Severity filter | Tools |
|---|---|---|---|
| 1 | `api-surface` | `high`, `critical` | `get_steps_for_scope_tier` → `analyze_upgrade_path` → `resolve_deprecation` → `entity_evolution` |
| 2 | `runtime` | `medium`, `high`, `critical` | Same sequence, skipping cached entities |
| 3 | `config`, `build` | all | `analyze_upgrade_path` with scope filter; `search_migration_knowledge` for misses |
| 4 | `test` | all | `analyze_upgrade_path` — deferred to execute |
| — | Paysafe deps | — | `resolve_paysafe_dependency_by_service_name` concurrently with tier 1 |

**Skip guard:** Check `ctx.queriedEntities[entity_name]` before any tool call. After each successful query, call `update_queried_entity(context_id, entity_name, result_summary)`.

**Paysafe errors:** On `auth_error` or `transport_error`, log remediation steps, emit backlog items, continue — do not halt Loop II.

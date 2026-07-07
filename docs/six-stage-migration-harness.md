# Six-Stage Split Migration Harness — Usage Guide

This guide explains how to drive the **split migration harness** exposed by the
`PaysafeMigrationOracle` MCP server: the six session-scoped stages
`plan → gap-check → clarify → preview → execute → feedback`, the tool gating
behind each stage, ready-to-use prompts, a real worked example, and a direct
answer to the most common operational question: **do we need a restart after
every step?**

---

## 1. Mental model

The harness is a **re-entrant, graph-backed state machine**. There is exactly
one source of truth: the `MigrationContext` node in Neo4j (keyed by
`project_id` + `from_version` + `to_version`). Every stage:

1. Loads state **from the graph** (never from prior chat/session memory).
2. Reads/writes only the tools its stage is allowed to use.
3. Hands off to the next stage by loading that stage's **skill resource**.

Because all state lives in the graph, you can stop after any stage, come back
hours later (or from a different machine), and resume exactly where you left off.

```
            scan codebase
                 │
                 ▼
 ┌────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐   ┌──────────┐   ┌──────────┐
 │  plan  │──▶│ gap-check │──▶│ clarify  │──▶│ preview │──▶│ execute  │──▶│ feedback │
 └────────┘   └───────────┘   └──────────┘   └─────────┘   └──────────┘   └──────────┘
   create/      audit, write     human edits    read-only      apply steps,   submit
   resume ctx   gap flags        (manual steps, plan render    update step    insights,
   + Loop II    (read-only)      excludes,      (read-only)    outcomes       close ctx
   queries                       force-include)
       │             │                │              │              │              │
       └─────────────┴────────────────┴──────────────┴──────────────┴──────────────┘
                          all state persists on the MigrationContext (Neo4j)
```

`clarify` is **optional** — skip it if gap-check raised no flags or the plan is
already acceptable.

---

## 2. The stages and their gated tool sets

Each stage exposes only a subset of the 26 tools. The allowlist is defined in
`migration_oracle/mcp/stage_gating.py` (`STAGE_TOOL_ALLOWLIST`) and the matching
`compatibility.tools` block in each skill file.

| Stage | Skill resource | Tools | Purpose | Mutates? |
|---|---|---|---|---|
| **plan** | `skill://framework-migration-plan/main` | **17** | Scan code, create/resume context, scope-gated graph queries (Loops I & II) | Creates/updates context, caches queried entities |
| **gap-check** | `skill://framework-migration-gap-check/main` | **6** | Mechanical read-only audit; write gap-check flags | Flags only (no step/code changes) |
| **clarify** | `skill://framework-migration-clarify/main` | **7** | Human-in-the-loop: add manual steps, exclude steps, force-include rules | Context steps & queue |
| **preview** | `skill://framework-migration-preview/main` | **2** | Read-only customer-facing plan render with caveats | **Nothing** |
| **execute** | `skill://framework-migration-execute/main` | **11** | Apply pending steps, record outcomes | Step outcomes (and your codebase) |
| **feedback** | `skill://framework-migration-feedback/main` | **8** | Submit/verify community insights, close context | Insights, context status |

### Exact tool allowlists

**plan (17):** `analyze_upgrade_path`, `build_recipe_plan`, `resolve_deprecation`,
`entity_evolution`, `search_migration_knowledge`, `search_openrewrite_recipes`,
`get_graph_schema`, `execute_custom_cypher`, `get_community_insights`,
`create_migration_context`, `get_steps_for_scope_tier`,
`resolve_paysafe_dependency_by_service_name`, `list_pipeline_runs`,
`get_artifact_content`, `install_migration_skill`, `update_queried_entity`,
`get_migration_contexts`

**gap-check (6):** `get_graph_schema`, `execute_custom_cypher`,
`get_pending_steps`, `get_steps_for_scope_tier`, `get_migration_contexts`,
`write_gap_check_flags`

**clarify (7):** `get_graph_schema`, `execute_custom_cypher`,
`get_pending_steps`, `update_step_status`, `update_queried_entity`,
`get_migration_contexts`, `add_manual_step`

**preview (2):** `get_pending_steps`, `get_migration_contexts`

**execute (11):** `build_recipe_plan`, `resolve_deprecation`, `entity_evolution`,
`search_migration_knowledge`, `search_openrewrite_recipes`, `get_graph_schema`,
`execute_custom_cypher`, `get_community_insights`, `get_pending_steps`,
`update_step_status`, `get_migration_contexts`

**feedback (8):** `get_graph_schema`, `execute_custom_cypher`,
`submit_migration_insight`, `get_community_insights`, `vote_insight`,
`verify_insight`, `close_migration_context`, `get_migration_contexts`

> When `MCP_ACTIVE_STAGE` is **unset**, all 26 tools are registered (no gating) —
> useful for a single-session run (see §5).

---

## 3. Do we need a restart after every step?

**Short answer: No — not for the harness to work. Yes — only if you want the
server to *physically enforce* per-stage tool gating.**

### Why

Tool registration is **fixed at server startup**. The server reads
`MCP_ACTIVE_STAGE` once at process boot and calls `apply_stage_gating(...)` to
delete out-of-stage tools from the registry. It **cannot** be changed mid-process.

So there are two valid operating modes:

#### Mode A — Single session, no restarts (recommended for most users)

Run the server **once** with **no** `MCP_ACTIVE_STAGE` (all 26 tools registered).
The agent walks through all six stages in one session, loading each stage's skill
resource in turn and simply using the tools that stage calls for. **No restart
between stages.** This works because:

- State is entirely in the `MigrationContext` (graph), not in the session.
- Each skill tells the agent which tools to use for that stage.
- The skills explicitly support this: *"if you are an agent with a server already
  running, do not restart it — infer the active stage from which tools in
  `compatibility.tools` are available."*

This is the right choice for interactive use in Claude Code / Cursor and for the
Docker SSE deployment.

#### Mode B — One restart per stage (hard enforcement / least privilege)

Restart the server with `MCP_ACTIVE_STAGE=<stage>` before each stage. This
**physically removes** every tool not on that stage's allowlist, so the model
*cannot* call them even by mistake. Use this when you need a hard safety boundary —
e.g. guaranteeing the `preview` session is incapable of mutating anything
(only 2 read tools registered), or running stages as separate CI jobs / separate
least-privilege service principals.

The trade-off is operational: each restart costs a container boot + health wait
(~15–20s in our environment).

### Rule of thumb

| You want… | Restart per stage? | How |
|---|---|---|
| Fastest interactive migration | **No** | One full-mode server, walk the skills |
| Resume later / different machine | **No** (just reconnect) | `resume_migration(context_id=…)` |
| Hard tool-gating / least privilege | **Yes** | `MCP_ACTIVE_STAGE=<stage>` per restart |
| Stages as separate CI jobs | **Yes** | One job per stage with the env var |

**You never restart *within* a stage** — only (optionally) *between* stages.
Re-running the same stage against the same context is idempotent and safe.

---

## 4. Sample prompts

### 4.0 Simple prompts (copy-paste, the quick way)

These are the everyday prompts you type into Cursor / Claude Code with the
`migration-oracle` MCP connected. No tool names, no skill URIs, no IDs to
memorize — just intent. The agent loads the right stage skill and uses the right
tools for you. Run them in order; say *"continue to the next stage"* between them.

| Stage | When to use it |
|---|---|
| **Start** | Beginning a brand-new migration for this repo |
| **Plan** | Build the personalized step list from your code |
| **Gap-check** | Audit the plan for risky/uncertain steps (read-only) |
| **Clarify** | Add your own steps / drop steps you don't need |
| **Preview** | See the final plan grouped by risk before doing anything |
| **Execute** | Actually apply the changes, step by step |
| **Feedback** | Share what you learned and close the migration |
| **Resume** | Pick up an existing migration where you left off |

**Start a migration**
```
Using migration-oracle, start a Spring Boot 3.5.0 → 4.0.0 migration for this
project. Scan the repo and build my personalized plan.
```

**Plan**
```
Run the plan stage: scan this repo, create the migration context, and find which
Spring Boot 4.0.0 changes actually affect my code.
```

**Gap-check**
```
Run the gap-check stage on my migration. Audit the plan for high-risk steps that
have no clear match in my code and flag them for review. Don't change anything.
```

**Clarify**
```
Run the clarify stage. Add a manual step "Migrate Spring Cloud to 2025.1.x
(Oakwood) BOM-only import", and drop the steps for tech we don't use
(Elasticsearch, MongoDB, Hazelcast, Neo4j driver). Then show me the updated plan.
```

**Preview**
```
Run the preview stage. Show my final migration plan grouped by risk
(HIGH / MEDIUM / LOW), and mark which steps are manual vs auto-detected.
```

**Execute**
```
Run the execute stage. Work through my pending steps from highest risk down,
apply each change, and update each step's status as you go.
```

**Feedback**
```
Run the feedback stage. Submit anything useful we learned during this migration,
then close it out.
```

**Resume later**
```
Resume my Spring Boot migration for this project — pick up where I left off.
```

> Tip: you don't need to track the `context_id` — the agent finds your existing
> migration for this project automatically. Provide it only if you run several
> migrations for the same repo at once.

### 4.1 Slash-command prompts (parameterized)

The server also registers three MCP **prompts** (slash-command palette in
Claude Code / Cursor). They render instructions that tell the agent which skill
to load and what to do.

### `start_migration` (recommended entry point)

Parameters: `framework`, `current_version`, `target_version`, `project_id`,
`stage` (default `plan`).

```
/start_migration
  framework: Spring Boot
  current_version: 3.5.0
  target_version: 4.0.0
  project_id: paysafe-ss-onetime-password
  stage: plan
```

### `resume_migration` (continue an existing context)

Parameter: `context_id` (the `elementId` returned by `create_migration_context`).
The server inspects context state and picks the right stage to resume.

```
/resume_migration
  context_id: 4:c474cace-f303-4271-8946-b26cf9dee8d9:745
```

### `migration_workflow_prompt` (zero-parameter fallback)

For clients without parameterized prompts — paste and fill placeholders.

### 4.2 Explicit prompts (advanced — naming skills & tools)

Use these when you want precise control: they name the skill resource and the
exact tools/IDs. Handy for scripting, demos, or when several contexts exist.

**Plan:**
```
Load skill://framework-migration-plan/main.
Start a Spring Boot 3.5.0 → 4.0.0 migration for project
"paysafe-ss-onetime-password". Scan this repo for framework entities, create (or
resume) the MigrationContext, then run the Loop II scope-gated queries.
```

**Gap-check:**
```
Load skill://framework-migration-gap-check/main.
Run a read-only gap-check audit on context
4:c474cace-...:745. Flag every step with applicability="uncertain", run the
stepless-rule and version-sanity checks, and persist the findings with
write_gap_check_flags. Do not change any steps.
```

**Clarify:**
```
Load skill://framework-migration-clarify/main.
On context 4:c474cace-...:745: add a manual step
"Migrate Spring Cloud to 2025.1.x (Oakwood) BOM-only import", then exclude the
uncertain steps for technologies we don't use (Elasticsearch, MongoDB, Hazelcast,
Neo4j driver, reactive Pulsar). Show the amended queue.
```

**Preview:**
```
Load skill://framework-migration-preview/main.
Render the final migration plan for context 4:c474cace-...:745 grouped by risk
(HIGH/MEDIUM/LOW). Show origin (graph/manual) and applicability for every step,
and render the gap-check caveats section first.
```

**Execute (skipped in this guide):**
```
Load skill://framework-migration-execute/main.
Resume context 4:c474cace-...:745. Work the pending queue top-down; for each step
apply the change, then call update_step_status with the outcome.
```

**Feedback (skipped in this guide):**
```
Load skill://framework-migration-feedback/main.
Submit any new insights discovered during this migration, then close context
4:c474cace-...:745 with final_status="partial" and notes.
```

---

## 5. Running the stages (operational recipes)

### Mode A — one full-mode server (no restarts)

```bash
docker run -d --name migration-oracle \
  --env-file .env \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e MCP_TRANSPORT=sse \
  -e MIGRATION_MODE=full \
  -p 8080:8080 -p 8501:8501 \
  paysafe-migration-oracle:latest
```

Then point your client at `http://localhost:8080/sse` and use the prompts in §4.
Walk all stages in one session — no restart needed.

### Mode B — one restart per stage (hard gating)

```bash
run_stage () {                       # $1 = plan|gap-check|clarify|preview|execute|feedback
  docker rm -f migration-oracle >/dev/null 2>&1
  docker run -d --name migration-oracle --env-file .env \
    -e NEO4J_URI=bolt://host.docker.internal:7687 \
    -e MCP_TRANSPORT=sse \
    -e MCP_ACTIVE_STAGE="$1" \
    -p 8080:8080 -p 8501:8501 \
    paysafe-migration-oracle:latest >/dev/null
  # wait for health before connecting
  until [ "$(docker inspect --format='{{.State.Health.Status}}' migration-oracle)" = healthy ]; do sleep 2; done
  echo "stage $1 ready — tools gated to the $1 allowlist"
}

run_stage plan        # then drive the plan prompt
run_stage gap-check   # then drive the gap-check prompt
run_stage clarify     # optional
run_stage preview     # read-only render
# run_stage execute   # apply changes
# run_stage feedback  # insights + close
```

> A client connected to the running server can confirm the active stage by calling
> `tools/list` — the count and names will match the allowlist in §2 (e.g. `preview`
> returns exactly 2 tools).

---

## 6. Worked example — `paysafe-ss-onetime-password` (Spring Boot 3.5.0 → 4.0.0)

Real run through `plan → gap-check → clarify → preview` (execute/feedback skipped),
Mode B (one restart per stage). The MigrationContext was seeded from 33 scanned
framework entities (JPA/Jakarta, Spring Data Redis, Spring Kafka, Cloud OpenFeign +
Eureka, HATEOAS, validation, Jackson, `@MockBean`/`@SpyBean`).

| Stage | Tools registered | Key outcome |
|---|---|---|
| **plan** | 17 | Resumed context (`reused=true`); surfaced **Spring Cloud co-migration warning** (Boot 4 ⇒ Spring Cloud 2025.1 "Oakwood"); Loop II tier-1 matched `MockBean`/`SpyBean`; `resolve_deprecation` → removed in 4.0.0, replaced by `MockitoSpyBean` |
| **gap-check** | 6 | 46 pending steps; **16 flagged `uncertain`**; 12 gap-check flags persisted; version + stepless-rule checks run; **no** mutation tools available |
| **clarify** | 7 | Added 1 **manual** step (Spring Cloud Oakwood, `origin=manual`); excluded 5 irrelevant uncertain steps (Elasticsearch, MongoDB, Hazelcast session, RestClient, Neo4j driver) → queue **46 → 42** |
| **preview** | 2 | Read-only render of **42 steps: 26 HIGH / 11 MEDIUM / 5 LOW**, with caveats section and `origin`/`applicability` per line |

### Applicability tiers in the final plan

- **`matched`** — project's scanned entities hit the rule (truly personalized):
  `@MockBean→@MockitoBean`, OAuth2/SAML2 explicit starters, Jersey→Spring MVC,
  `spring-boot-tx→spring-boot-transaction`, `spring-boot-starter-aop→aspectj`,
  Wavefront→OTLP, remove `spring-boot-parent`.
- **`uncertain`** — high/critical with no entity match, surfaced for human review
  (gap-check population): Jackson `com.fasterxml.jackson→tools.jackson`,
  `EnvironmentPostProcessor` import move, Pushgateway rename.
- **`informational`** — general guidance with no affected entities.
- **`[MANUAL]`** — added in clarify; always rendered distinctly from graph steps.

### What got persisted on the MigrationContext (verified in Neo4j)

```
MigrationContext (paysafe-ss-onetime-password, status=in-progress)
  ├─ UPGRADES_FROM / UPGRADES_TO → Version
  ├─ OWNS_STEP        → 1 MigrationStep (origin=manual, "Spring Cloud Oakwood")
  ├─ STEP_OUTCOME {status:excluded} → 5 MigrationStep
  └─ gapCheckFlags    (12 flags, serialized JSON on the node)
```

Every stage re-derived this purely from the graph — nothing carried across the
four restarts in session memory, which is exactly the re-entrancy guarantee.

---

## 7. FAQ

**Q: Can I skip clarify?**
Yes. It's optional. If gap-check raised no flags or the plan is acceptable, go
straight from gap-check to preview/execute.

**Q: What happens if I call a tool that isn't in the current stage?**
In Mode B it isn't registered, so the call fails (tool not found) — by design.
In Mode A all tools exist; the skill instructs the agent not to reach across
stages, but there's no hard block.

**Q: Do gated stages need a `context_id`?**
`gap-check`, `clarify`, and `preview` require a valid `context_id` (enforced by
`validate_context_id_for_stage`). `plan` creates it; the others resume it.

**Q: Is re-running a stage safe?**
Yes — stages are idempotent against the graph. `create_migration_context` MERGEs
on the triple; `write_gap_check_flags` deduplicates; preview is read-only.

**Q: How do I find my context_id later?**
`get_migration_contexts(project_id=...)` lists all contexts with their status and
outcome counts, then `resume_migration(context_id=...)`.

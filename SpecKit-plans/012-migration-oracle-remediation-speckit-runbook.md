# SpecKit Runbook — Migration Oracle Correctness & Consistency Remediation

> Generated with the SpecKit SDD Buddy skill.
> Source defect register: `ISSUES.md` (generated 2026-06-12).
> Authoritative property/relationship names: `graph-schema.md` — treat as source of truth in every prompt below.
> Scope: all 14 distinct open issues (body numbering 001–015; 011 is already consolidated into 008).

---

## 0. Decision Gate (run before writing anything)

Per SDD Buddy §2, classify the work before choosing a lifecycle.

- The change is **not** isolated to one file/function — it spans `framework_migration_version_map.md`, `framework_migration_main.md`, `mcp-tools-skills-prompts.md`, the Cypher in the MCP server, the graph data, and adds one new skill resource.
- Several issues **change contracts** (tool return shapes 004/007/010, accepted enum values 015, query behavior 003/006) → these are spec **amendments + contracts/ update**, not new behavior from scratch.
- One issue **adds a new component** (005, the rollback skill) → new artifact.
- Two issues require a genuine **design decision** (002 + 008: how `queriedEntities` is written and how `--force-refresh` is expressed — new tool vs. context property) → **design gate**, must be resolved before tasks.

The project has **no existing SpecKit artifacts** (`spec.md`/`plan.md`/`tasks.md` are absent). So rather than amend a non-existent spec, this runbook creates **one remediation spec** that documents the corrected behavior and contracts, then runs `plan → tasks → implement`. The issues are organized into six work-streams:

| WS | Theme | Issues |
|----|-------|--------|
| WS1 | Version arithmetic & catalogue | 001 (CRITICAL), 012, 014 |
| WS2 | Graph-state contract | 004, 015 |
| WS3 | Query correctness | 003, 006 |
| WS4 | Tool API / return-shape alignment | 007, 009, 010 |
| WS5 | Resumability cache (design gate) | 002, 008 |
| WS6 | Resilience artifacts & fallbacks | 005, 013 |

> If you'd rather not open a formal spec, the amendment-only alternative is in §11.

---

## 1. Prerequisites

Complete ALL before running any command.

- [ ] Working tree clean: `git status` is clean; create branch `git checkout -b fix/migration-oracle-correctness`.
- [ ] Current test suite passes (record the baseline — these fixes must not regress it).
- [ ] `graph-schema.md` is confirmed as the **single source of truth** for node labels, property names, and relationship types. Where Cypher and schema disagree, the **schema wins** unless an issue explicitly says otherwise.
- [ ] A throwaway/seeded Neo4j instance is available to run before/after Cypher and prove the fixes (especially 003, 004, 006, 009).
- [ ] You have a fixture project with a known `MigrationContext` (in-progress, with scanned entities) to exercise resume/skip-guard behavior (002, 008).
- [ ] Confirm whether `STEP_OUTCOME`-based reads exist anywhere downstream (query #5 in `graph-schema.md`) so 004's read-migration scope is known.

---

## 2. Command 1 — `/speckit.specify`

Paste verbatim into Claude Code. (SDD Buddy §4 — all five sections present, behavior only, no implementation detail.)

```
/speckit.specify

WHAT it does: Corrects 14 documented defects (see ISSUES.md) across the Paysafe Migration
Oracle so that version arithmetic, graph-state recording, scope/severity querying, tool
return shapes, session resumability, and failure-recovery all behave as their documentation
and graph schema already promise. No new product capability is added; the system's stated
contracts are made true.

WHY it exists: The Oracle currently produces silent wrong results. sortableVersion is computed
two different ways; the preferred STEP_OUTCOME relationship is never written; a severity filter
is accepted but ignored; recipe lookups traverse a relationship that does not exist; a documented
return field is null; a resumability cache is never populated; and a referenced rollback procedure
does not exist. Each defect is silent (no error thrown), so correctness must be specified and verified.

VERSION ARITHMETIC (WS1) and what it does:
  - The single canonical sortableVersion formula is MAJOR*1_000_000 + MINOR*1_000 + PATCH
    (the formula already in graph-schema.md). The version-map document and every precomputed
    "Sortable" cell are made to match it.
  - The version catalogue declares its freshness and points to upstream support schedules.
  - The Angular boundary notes contain each boundary exactly once.

GRAPH-STATE CONTRACT (WS2) and what it does:
  - Recording a step outcome writes the schema's preferred STEP_OUTCOME relationship
    (status, reason, updatedAt), idempotently per (context, step).
  - A migration session can be closed with any status the schema declares valid, including
    "abandoned".

QUERY CORRECTNESS (WS3) and what it does:
  - Scope-tier retrieval returns only steps at or above the requested severity threshold.
  - Upgrade-path analysis returns recipe data joined to the step it automates.

TOOL API ALIGNMENT (WS4) and what it does:
  - Deprecation lookup returns the entity name under the field name its API documents.
  - Recipe search filters on parameter presence and composite-ness using the real graph
    structure, not absent properties.
  - Insight submission documents its duplicate-detection behavior and returns the same shape
    in all outcomes (written / duplicate / error).

RESUMABILITY (WS5) and what it does:
  - The query-loop skip guard reads a cache that is actually written after each entity query,
    so resumed sessions do not re-query resolved entities.
  - A concrete, named mechanism exists to force re-querying a single entity.

RESILIENCE (WS6) and what it does:
  - A rollback procedure exists as a loadable resource for the build-failure path.
  - The feedback loop has a defined stateless-mode behavior.

KEY BEHAVIORS:
SINGLE_FORMULA — Exactly one sortableVersion formula exists across all project docs and Cypher; "3.10.0" sorts above "3.9.0".
NO_HALF_RECOMPUTE — Every precomputed Sortable cell equals the canonical formula's output; none are left on the old formula.
STEP_OUTCOME_WRITTEN — After recording an outcome, the schema's progress-summary query (graph-schema.md #5) returns non-empty counts.
OUTCOME_IDEMPOTENT — Recording the same (context, step) outcome twice updates one relationship, never creates two.
SEVERITY_FILTERED — A tier-1 (high/critical) scope query never returns low/medium steps.
RECIPES_NONEMPTY — Upgrade-path analysis with include_recipes=true returns recipe objects for steps that have an AUTOMATED_BY edge.
FIELD_NAME_MATCHES_DOC — Deprecation lookup's documented field returns the entity value, not null.
PARAM_FILTER_REAL — require_no_params=true excludes recipes that have a required parameter; only_composite filters on the actual composite property.
DEDUP_OBSERVABLE — Insight submission's duplicate threshold is documented and the returned shape matches in all three status paths.
CACHE_POPULATED — After querying an entity, the skip guard finds it cached on resume and does not re-issue the call.
ABANDONABLE — A session can be closed as "abandoned" through the tool surface.
ROLLBACK_LOADABLE — The build-failure path can load a rollback resource that exists.

INTEGRATION CONSTRAINTS:
  - graph-schema.md is authoritative for ALL property and relationship names. Do not invent
    properties. STEP_OUTCOME, HAS_PARAM, RecipeParam, and the legacy *Steps arrays already exist.
  - The CORRECT formula already lives in graph-schema.md — do not "fix" it there; only the
    version-map doc and its tables are wrong.
  - Write boundaries: execute_custom_cypher is read-only and must stay read-only; do not route
    any fix through it. Mutable writes go through their owning tool only.
  - Do not duplicate version-map data into code; the version-map skill remains the catalogue.
  - Legacy completedSteps/skippedSteps/failedSteps arrays stay populated until all readers move
    to STEP_OUTCOME; this is an additive contract change, not a removal.
  - Error cases: every changed tool must still return its documented error shape on failure.
```

---

## 3. Gap Review — Post-Specify

Run before `/speckit.plan` (SDD Buddy §5).

```
Review the generated spec.md for the Migration Oracle remediation and check these gaps before
we proceed to planning. Fix any that are missing or underspecified.

GAP-001: Single-formula guarantee
  Spec must state there is ONE formula and that graph-schema.md's version is canonical.
  Verify it explicitly forbids editing the (already-correct) schema copy.

GAP-002: Recompute completeness
  Spec must require EVERY precomputed Sortable cell in BOTH tables (Spring Boot and Angular)
  be recomputed — not just the worked examples. State the inversion test (3.10.0 vs 3.9.0).

GAP-003: STEP_OUTCOME additive, not replacing
  Spec must say STEP_OUTCOME is written IN ADDITION to legacy arrays until readers migrate.
  Confirm idempotency (MERGE on (context, step)) is a stated behavior, not an implementation hint.

GAP-004: Severity threshold semantics
  Spec must define how the threshold string maps to ordering (critical<high<medium<low) and
  that "threshold" means "at or above". Without this, the fix could invert the comparison.

GAP-005: Recipe-to-step join shape
  Spec must state recipes are returned per-step (joined through REQUIRES_STEP), not per-rule.
  Confirm what an empty recipe list means vs. a missing edge.

GAP-006: Return-shape parity (007, 010)
  For every tool whose return shape changes, spec must require Cypher output AND the documented
  Returns table to match. List the three submit-insight status paths explicitly.

GAP-007: Design-gate items flagged (002, 008)
  Spec must explicitly mark the queriedEntities write path and --force-refresh mechanism as
  UNRESOLVED design decisions requiring a choice in plan (new tool vs. context property).

GAP-008: New-artifact scope (005)
  Spec must say a rollback resource is a NEW skill resource with a defined revert procedure,
  and that install_migration_skill must include it.

GAP-009: Error shapes preserved
  Spec must require each modified tool keep its existing error/return shape on the failure path.

GAP-010: No new write surface via read-only tool
  Spec must reaffirm execute_custom_cypher stays read-only and no fix smuggles writes through it.
```

---

## 4. Command 2 — `/speckit.plan`

```
/speckit.plan

Produce plan.md plus data-model.md, contracts/, research.md for the Migration Oracle remediation.

Required artifacts:
- data-model.md: document the STEP_OUTCOME relationship (status, reason, updatedAt) and its
  MERGE identity (context, step); the MigrationContext.queriedEntities property (its key/value
  schema — entity_name -> result_summary); the close-status enum including "abandoned"; and a
  note that RecipeParam/HAS_PARAM (not an OpenRewriteRecipe.requiredParams property) is how
  required params are modeled, and the composite flag is `composite` (not isComposite).
- contracts/: per-tool corrected contracts for get_steps_for_scope_tier (severity behavior),
  analyze_upgrade_path (recipe join), update_step_status (STEP_OUTCOME + arrays),
  resolve_deprecation (entity_name field), search_openrewrite_recipes (HAS_PARAM subquery +
  composite), submit_migration_insight (dedup threshold + MERGE + 3 status paths),
  close_migration_context (abandoned). Each contract states inputs, outputs, error shape.
- research.md: resolve the two design-gate decisions:
    (a) queriedEntities write path: new update_queried_entity tool vs. write inside an existing
        context tool. Pick one; justify.
    (b) --force-refresh: prompt parameter vs. context boolean vs. cache-invalidation tool.
        Pick one; justify. Define exactly what it resets.
  Also decide the rollback resource's concrete procedure (git stash / checkout HEAD / OpenRewrite
  dry-run) and the dedup cosine-similarity threshold value to document.
- quickstart.md: how to stand up the seeded graph + fixture context and run the before/after
  verification for each work-stream locally.

Runtime: state the Neo4j/Cypher target and the server runtime version.
Parallelism: identify which work-streams are independent ([P]).
```

---

## 5. Gap Review — Post-Plan

```
Review plan.md, data-model.md, contracts/, research.md before /speckit.tasks. Fix gaps.

PLAN-GAP-001: queriedEntities key/value schema is fully specified in data-model.md (key =
  entity_name; value shape), and the WRITE site is named in a contract (002).
PLAN-GAP-002: --force-refresh decision is final in research.md, with the exact reset semantics
  and where the agent reads it (008). No lingering "TBD".
PLAN-GAP-003: STEP_OUTCOME contract shows the MERGE pattern and confirms legacy arrays still
  written; a migration note lists every current reader of the legacy arrays (004).
PLAN-GAP-004: severity threshold->rank mapping table is in a contract, with the "<= rank" filter
  direction stated (003).
PLAN-GAP-005: analyze_upgrade_path contract shows recipe joined via
  (rule)-[:REQUIRES_STEP]->(s)-[:AUTOMATED_BY]->(rec), and recipes attach to their step (006).
PLAN-GAP-006: search_openrewrite_recipes contract uses EXISTS { (r)-[:HAS_PARAM]->
  (:RecipeParam {required:true}) } and `composite`, not requiredParams/isComposite (009).
PLAN-GAP-007: submit_migration_insight contract documents the threshold value, the pre-write
  dedup query, and the Returns table for ok/duplicate/error including duplicate_of (010).
PLAN-GAP-008: rollback resource has a concrete procedure and is added to install_migration_skill;
  Loop IV stateless behavior is defined (005, 013).
PLAN-GAP-009: close_migration_context contract lists complete/partial/abandoned (015).
PLAN-GAP-010: version-map plan includes a staleness header + upstream links and the Angular
  boundary de-duplication (012, 014); confirms graph-schema formula is untouched (001).
PLAN-GAP-011: contracts state execute_custom_cypher remains read-only; no fix routes writes
  through it.
```

---

## 6. Command 3 — `/speckit.tasks`

```
/speckit.tasks
```

---

## 7. Gap Review — Post-Tasks

```
Review tasks.md before /speckit.implement. Fix gaps.

TASK-GAP-001: Foundation-first ordering — data-model/contract tasks (STEP_OUTCOME shape,
  queriedEntities schema, status enum) precede the tool-edit tasks that depend on them.
TASK-GAP-002: The sortableVersion recompute is a SINGLE task that regenerates ALL cells in both
  tables programmatically (not hand-edited per row), with a check task asserting cell == formula.
TASK-GAP-003: Independent work-streams (WS1 version-map vs WS3 query Cypher vs WS6 rollback
  resource) are marked [P]; WS5 design-gate task is NOT [P] and blocks its dependents.
TASK-GAP-004: Each tool-fix task pairs the Cypher change WITH the Returns-table/doc change in the
  same task (007, 009, 010) so they cannot drift apart.
TASK-GAP-005: E2E task — run a full mock migration that records an outcome and asserts the
  graph-schema #5 progress query returns non-empty (proves 004 end to end).
TASK-GAP-006: Idempotency test — record the same (context, step) twice; assert one STEP_OUTCOME.
TASK-GAP-007: Negative/severity test — tier-1 query over seeded mixed-severity steps returns no
  low/medium (003); recipe-join test asserts non-empty recipes for an automatable step (006).
TASK-GAP-008: Resume test — query an entity, resume, assert skip guard fires and no re-query
  (002); force-refresh test asserts the single entity IS re-queried (008).
TASK-GAP-009: Error-path tests retained for every modified tool (unchanged error shape).
TASK-GAP-010: A guard test asserts graph-schema.md's formula text is unchanged (prevents the
  "fixed the wrong copy" regression for 001).
```

---

## 8. Command 4 — `/speckit.implement`

```
/speckit.implement
```

---

## 9. Recovery Prompts (paste verbatim when Claude Code drifts)

These target this remediation's specific risks (SDD Buddy §6).

**Fixed the correct copy of the formula:**
```
Do not modify the sortableVersion formula in graph-schema.md — it is already correct and is the
source of truth. Only framework_migration_version_map.md and its precomputed Sortable cells are
wrong. Revert any change to graph-schema.md's formula or its examples.
```

**Half-recomputed the version tables:**
```
Recompute EVERY Sortable cell in both the Spring Boot and Angular tables from
MAJOR*1_000_000 + MINOR*1_000 + PATCH. Do not leave any cell on the old *10000+*100 formula.
Generate the column programmatically and assert each cell equals the formula output, including a
case that proves 3.10.0 sorts above 3.9.0.
```

**Replaced legacy arrays instead of adding STEP_OUTCOME:**
```
STEP_OUTCOME is ADDITIVE. Keep writing completedSteps/skippedSteps/failedSteps. Add a
MERGE (ctx)-[so:STEP_OUTCOME {status:$outcome, reason:$reason, updatedAt:datetime()}]->(s)
that updates one relationship per (context, step). Do not delete the legacy array writes until a
separate task migrates all readers.
```

**Recipe joined to rule again:**
```
Recipes attach to the STEP that automates them. Traverse
(rule)-[:REQUIRES_STEP]->(s:MigrationStep)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe) and return
each recipe under its parent step. There is no (MigrationRule)-[:AUTOMATED_BY] relationship in the
schema — do not use one.
```

**Severity filter inverted or scope-only:**
```
get_steps_for_scope_tier must filter on severity. Map critical=0, high=1, medium=2, low=3 and keep
rows where sev_rank <= the threshold's rank ("at or above"). The existing WHERE bs.scope=$scope is
not sufficient.
```

**Invented properties for recipe filters:**
```
OpenRewriteRecipe has no requiredParams and no isComposite. For require_no_params use
NOT EXISTS { (r)-[:HAS_PARAM]->(:RecipeParam {required:true}) }. For only_composite use r.composite.
```

**Doc and Cypher drifted:**
```
For resolve_deprecation, submit_migration_insight, and search_openrewrite_recipes, the Cypher
output fields and the Returns table must match exactly. If you alias e.name AS entity_name in
Cypher, the table must read entity_name — change both in the same edit, never one alone.
```

**Write smuggled through the read-only tool:**
```
Do not route any write through execute_custom_cypher — it is read-only and must stay read-only.
The queriedEntities write goes through the tool chosen in research.md, not a custom Cypher call.
```

**Rollback left as a dangling reference:**
```
"Load rollback skill" must resolve to a real resource. Create skill://framework-migration/rollback
with the concrete revert procedure decided in research.md, and add it to install_migration_skill's
installed set. Do not leave the Loop III build-failure path pointing at a non-existent skill.
```

---

## 10. What Success Looks Like

Acceptance smoke test — all must pass:

1. `grep` finds the `*1_000_000` formula in exactly one place (schema) and the version-map doc agrees; a unit assertion confirms every Sortable cell matches the formula and 3.10.0 > 3.9.0.
2. Record one step outcome, then run graph-schema.md query #5 — completed/skipped/failed counts are non-empty; recording it again leaves a single STEP_OUTCOME edge.
3. Seeded tier-1 scope query returns only high/critical steps; `include_recipes=true` returns recipes for an automatable step.
4. `resolve_deprecation` response carries the value under `entity_name`; `require_no_params=true` excludes a recipe with a required `RecipeParam`; `only_composite=true` filters on `composite`.
5. `submit_migration_insight` docs state a threshold and the response shape is identical across ok/duplicate/error (with `duplicate_of` populated on duplicate).
6. Query an entity → resume → skip guard fires (no re-query); applying the chosen `--force-refresh` mechanism re-queries exactly that one entity.
7. `close_migration_context(final_status="abandoned")` succeeds; the build-failure path loads a real rollback resource; Loop IV has a defined stateless path.
8. Baseline test suite still green.

---

## 11. Alternative — Amendment-Only Path (skip the new spec)

If you don't want a formal `spec.md`, the same fixes can ship as targeted amendments (SDD Buddy §7).
Use this when the team treats the Oracle as already-specced-by-docs and just wants the deltas.

```
Amend the Migration Oracle docs and tool Cypher to fix ISSUES.md, grouped:

A) framework_migration_version_map.md — adopt MAJOR*1_000_000+MINOR*1_000+PATCH, recompute all
   Sortable cells, add a "Last Updated" header + upstream links, de-duplicate the Angular
   boundary notes. Do not touch graph-schema.md's formula.
B) mcp-tools-skills-prompts.md — add severity filter to get_steps_for_scope_tier; join recipes via
   step in analyze_upgrade_path; add STEP_OUTCOME MERGE to update_step_status; align
   resolve_deprecation's field to entity_name; fix search_openrewrite_recipes to HAS_PARAM +
   composite; document submit_migration_insight dedup + return shape; allow "abandoned" in
   close_migration_context.
C) framework_migration_main.md — define the queriedEntities write step and a concrete
   --force-refresh mechanism; replace "Load rollback skill" with a real resource reference; add a
   Loop IV stateless-fallback section.

Do not regenerate whole files. After amending, re-run /speckit.plan only for the contract deltas
in (B), since those change tool return shapes.
```

> Note: even on the amendment path, items 002 and 008 still require the design decision in §4's
> research step before implementation — don't let "amendment" skip the design gate.
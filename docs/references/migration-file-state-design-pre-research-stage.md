# File-Based Migration State - Schema and Skill Amendment

Status: Implemented (017-linear-file-migration-state).
Supersedes for state: the graph-state session model (MigrationContext, STEP_OUTCOME,
queried-entity cache) and the seven session-state MCP tools.
Keeps: the graph as a knowledge base that is read-only for state, and the five-way render
classification from hybrid-plan-rendering.md (re-cast as the plan-to-task renderer).

Presentation note: schema examples are shown in plain code blocks. Command and code
snippets inside a schema are ordinary lines (prefixed "$" for shell) so no code fence is
ever nested inside another, and the document uses only ASCII and no angle-bracket tokens,
so it renders and loads in every viewer. Placeholders are written in braces, e.g. {FROM}.

---

## 0. The split in one line

The graph stops holding progress. Progress lives in three version-controlled files in the
consumer repo. The graph is queried for knowledge only.

```
KNOWLEDGE (graph, read-only for state)     PROGRESS (files, git-tracked, consumer repo)
  Version / MigrationRule                    migration/{fw}-{from}-to-{to}/
  MigrationStep / OpenRewriteRecipe            plan.md          strategy + rule ledger + provenance
  Class / ApplicationProperty                  tasks.md         file-anchored work queue + status
  Dependency / community insights              verification.md  end-of-run completion gate
```

Writes to the graph after this change: only submit_migration_insight, from the migration
harness. The community-curation tools vote_insight / verify_insight are also writes, but
they live outside the per-migration loop and are unaffected. Everything the harness does
during a migration is a graph READ plus a FILE write.

Location: $PROJECT_ROOT/migration/{framework}-{from}-to-{to}/ (visible, so it shows up in
PR review). Consumer repos already on SpecKit may nest under specs/ instead. One migration
equals one folder. Resume equals re-read the folder plus "git status"; there is no
multi-session supersede logic.

Removed tools (7). Five are pure session-state and delete outright: create_migration_context,
get_migration_contexts, get_pending_steps, update_step_status, close_migration_context.
Two do live query work in Loop II and are reassigned, not simply deleted:

- update_queried_entity: its resume-cache role becomes a write to plan.md / tasks.md.
- get_steps_for_scope_tier: it retrieves scoped MigrationStep records (a knowledge read
  that gap-check depends on). That read must survive as a knowledge query - fold it into
  analyze_upgrade_path's scoped return, or keep a knowledge-only variant that takes the
  scanned entities plus tier and no context_id.

Their session-state plumbing, the MigrationContext / STEP_OUTCOME subgraph, and the
matching tests/mcp/ coverage are dropped from docs/graph-schema.md. Net tool count goes
23 to 16.

Stateless-fallback distinction collapses. Today there is a stateless fallback
(analyze_upgrade_path + build_recipe_plan, no context_id) for when context creation fails.
Under the file model there is no context to create, so the fallback path is the only path,
plus file persistence on top.

---

## 1. plan.md - strategy, context, and the rule ledger

Knowledge snapshot and provenance anchor. Generated AFTER Loop II's full escalation chain
runs - never from a cheap one-query-per-entity pass (that is the applicability=universal
accuracy failure MIGRATION_LITE_MODE.md warns about).

```
# Migration Plan: {FRAMEWORK} {FROM} to {TO}
# meta: generated from graph knowledge - do not hand-edit the Rule Ledger
Generated:      {ISO date}
Project:        {absolute PROJECT_ROOT}
Framework:      {FRAMEWORK}
From to To:     {FROM} to {TO}
Graph snapshot: {knowledge-version id at generation time}

## Preconditions
Complete ALL before starting tasks.
- [ ] Runtime gate: e.g. Java 17 for Boot 3 / Java 21 for Boot 4
- [ ] Namespace boundary: e.g. javax to jakarta applies
- [ ] Co-migration: e.g. Spring Cloud train 2021.x to 2023.x
- [ ] Clean tree: git status clean; branch migration/{FROM}-to-{TO} created

## Scope order (blast radius)
api-surface -> runtime -> config/build -> test

## Rule Ledger
Every matched graph rule, classified by the render table (section 4). Source of truth
for what each task in tasks.md derives from. Columns:
RuleID | Scope | EntityMatched | classification | applicability | Render | tasks.md

  MR-4831 | api-surface | o.s.s.c.a.w.c.WebSecurityConfigurerAdapter
          | actionable | direct | TASK | TASK-003
  MR-5107 | runtime | javax.persistence.Entity
          | incomplete | direct | RELEVANCE-INDEX | (none)
  MR-6620 | config | server.servlet.context-path
          | actionable | direct | TASK | TASK-007

## Dependency Updates
  spring-boot-starter-parent | 2.7.x -> 3.2.4 | Paysafe service: none | Parent POM first

## OpenRewrite recipes (from build_recipe_plan / search_openrewrite_recipes)
Recipes that back any Executor=openrewrite task, so tasks.md can reference them by id.
  org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2 | backs TASK-003, TASK-007 | partial

## Drift rule
plan.md is a point-in-time snapshot. If execute/clarify re-query the graph and find a
rule changed: file is source of truth for progress/intent; graph is source of truth for
knowledge. On divergence, surface a drift note in tasks.md - never silently re-plan.
```

Rule IDs are the durable MigrationRule id (plus version range plus entity), not an
ephemeral session label - so any later skill can re-fetch the rule from the graph.

---

## 2. tasks.md - the file-anchored work queue

Evolves the existing MIGRATION_PLAN.md TASK block. Two sections: Tasks (concrete,
executable) and Relevance Index (matched rules with no prescribed fix - listed so nothing
is silently dropped; candidates for clarify). In the example, "$" marks a shell line and
indented lines are code; no nested code fences are used.

```
# Tasks: {FRAMEWORK} {FROM} to {TO}
HIGH: {n}  MEDIUM: {n}  LOW: {n}  Relevance-index: {n}

## Instructions for Code Agent
1. Work sequentially, TASK-001 to TASK-NNN. Transitional non-compiling states are expected.
2. Build once at the end via verification.md. Fix forward; do not revert tasks.
   PAYSAFE CONSTRAINT: never modify/remove/downgrade any com.paysafe.* dependency.
3. When stuck, SEARCH before skipping: search_migration_knowledge(...) /
   resolve_deprecation(...) - knowledge queries are allowed. Only then mark NEEDS-REVIEW.
4. Update each task's Status line as you go - this file is the progress record.

---

### TASK-003  HIGH  Security config
Status:       pending          # pending | done | failed | deferred | needs-review
Derives-from: MR-4831          # provenance to plan.md Rule Ledger
Origin:       graph            # graph | manual (manual = added by clarify; one-way)
Executor:     agent-codemod    # openrewrite | prompted-auto | agent-codemod | human-review
Recipe:       none             # openrewrite recipe id from plan.md, if Executor=openrewrite
Effort:       M
File pattern: src/main/java/**/*SecurityConfig.java

Instructions
  1. $ grep -rl "WebSecurityConfigurerAdapter" src/
  2. Replace: extends WebSecurityConfigurerAdapter  with a SecurityFilterChain @Bean ...
  3. ...

Before (java):
  class ... extends WebSecurityConfigurerAdapter { configure(HttpSecurity) ... }
After (java):
  @Bean SecurityFilterChain filterChain(HttpSecurity http) { ... }

Verify (per-task, one-liner):
  $ ! grep -rq "WebSecurityConfigurerAdapter" src/
  Expected: exit 0 (no matches remain).

---

## Relevance Index (NOT tasks - surfaced, not silently dropped)
Matched a rule but no graph-prescribed fix. review reports them; clarify may promote one
into a real task via a manual edit (Origin: manual).

- RI-01  MR-5107  javax.persistence.Entity affects this codebase; the graph has no
  prescribed MigrationStep yet. applicability: direct. Awaiting clarify.
- RI-02  MR-7744  safety-net match, applicability: uncertain; may apply, not confirmed
  against your code.
```

Status and Origin are what the removed update_step_status / step-origin graph writes
become. Editing a checkbox/status IS the progress write now.

---

## 3. verification.md - end-of-run completion gate

Adapts the layered, cheapest-first, stop-on-first-failure structure of the
verification-protocol-writer skill to a migrated consumer app (not a graph pipeline).
Every check is machine-verifiable; failures compound, so stop at the first. Shell lines
are prefixed "$".

```
# Verification: {FRAMEWORK} {FROM} to {TO}
Run:   after all tasks.md tasks are done, before deleting the migration/ folder.
Order: Level 0 to 5 in sequence. Stop and fix on first failure.

## Prerequisites
- [ ] Runtime gate satisfied (Java version from plan.md)
- [ ] Build tool reachable; test DB/services up (for integration levels)

### Level 0 - Static residue (no build)
Each TASK's per-task verifier, plus a global sweep that no removed symbol survives:
  $ ! grep -rq "WebSecurityConfigurerAdapter" src/    # PASS: no removed API remains
  $ ! grep -rq "javax.persistence" src/               # PASS: namespace migration complete

### Level 1 - Clean build
  $ {build command}                                   # PASS: exit 0

### Level 2 - Unit tests
  $ {unit test command}                               # PASS: exit 0

### Level 3 - Integration tests
  $ {integration test command}                        # PASS: exit 0

### Level 4 - App starts
  $ {run command} &  sleep {n}
  $ curl -fsS localhost:{port}/actuator/health        # PASS: UP

### Level 5 - Constraints and provenance
- [ ] Paysafe constraint held:
      $ git diff {base} -- '**/pom.xml' | grep -i com.paysafe
      shows no version change to any com.paysafe.* dependency
- [ ] Every tasks.md task is done or explicitly deferred (none pending/failed)
- [ ] Every Relevance-Index entry is promoted, deferred-with-reason, or logged to backlog

## Completion gate
  0-A  No removed API symbols remain      [ ]
  1-A  Clean build                        [ ]
  2-A  Unit tests pass                    [ ]
  3-A  Integration tests pass             [ ]
  4-A  App starts / health UP             [ ]
  5-A  Paysafe constraint held            [ ]
  5-B  No pending/failed tasks            [ ]
  5-C  Relevance index resolved           [ ]
All ticked -> migration complete. Remove the migration/ folder and commit, or archive it.
```

verification.md is generated by plan as a skeleton (Levels 0 and 5-A/B/C derive from the
Rule Ledger plus per-task verifiers) and finalized by execute, which fills in the
build/test/run commands discovered from the repo.

---

## 4. The render table (unchanged logic, new target)

Same five outcomes as hybrid-plan-rendering.md section 2 - but the output is a row in
plan.md's Rule Ledger plus a tasks.md entry, not a graph result_summary suffix.

- actionable AND at least 1 MigrationStep with non-empty instruction AND a matched entity
  => TASK
- same as above but effort=architectural OR generic/templated instruction
  => TASK, flagged NEEDS-DESIGN-REVIEW
- entityClassification=incomplete (AFFECTS_* edges but no REQUIRES_STEP)
  => RELEVANCE-INDEX
- applicability=uncertain (safety-net match, no direct hit)
  => RELEVANCE-INDEX, labeled uncertain
- rule has BRIDGED_BY and its step is later deferred
  => PLACEHOLDER (points at the bridge; never deleted)

---

## 5. How the four skills change

plan
  Reads:  codebase scan (scanning skill); graph knowledge via the full escalation chain
          (analyze_upgrade_path -> resolve_deprecation -> entity_evolution ->
          search_migration_knowledge); scoped-step retrieval (the reassigned
          get_steps_for_scope_tier knowledge read); build_recipe_plan /
          search_openrewrite_recipes for OpenRewrite routes;
          resolve_paysafe_dependency_by_service_name.
  Writes: creates plan.md (Rule Ledger + recipe table, render-classified),
          tasks.md (Tasks + Relevance Index), verification.md (skeleton).
  Graph:  read knowledge only.

review
  Reads:  plan.md + tasks.md.
  Writes: annotates gaps/preview inline (grouped by risk; every task shows Origin +
          applicability); no state mutation.
  Graph:  optional read to double-check knowledge.

clarify
  Reads:  tasks.md Relevance Index.
  Writes: edits tasks.md - promotes a RI entry to a real TASK with Origin=manual
          (one-way; never rewritten to graph).
  Graph:  allowed to query knowledge on demand.

execute
  Reads:  tasks.md work queue.
  Writes: edits tasks.md Status per task (replaces update_step_status); on failure runs
          rollback skill and sets Status=failed; finalizes and runs verification.md.
  Graph:  allowed to query knowledge when stuck (rollback + "search before skip").

The one remaining harness write. submit_migration_insight is knowledge, not state, so it
stays - and it is now the entire cross-project learning loop the harness produces. Assign
it an explicit owner: execute's tail, after a manual-origin or clarified fix succeeds,
reads that outcome from tasks.md and submits it. Do not leave it implicit; with
MigrationContext gone, nothing else feeds the graph from a migration run.

Executor routing is unchanged - the openrewrite -> prompted-auto -> agent-codemod ->
human-review table keys off effort + concrete-instruction + entity-anchor, which is
exactly what the render table computes. It now reads the route from the task's Executor
line (and Recipe line for the OpenRewrite tier) instead of get_pending_steps.

---

## 6. What this costs vs. the graph-state model

- Loses: cross-project analytics that came from querying MigrationContext at scale (which
  rules defer often, etc.). Partially recoverable only through submit_migration_insight.
- Softens: guarantees that were tool-enforced (update_step_status "never skip") become
  file conventions the skill prose must carry. verification.md Level 5-B is the backstop.
- Gains: git-tracked, diffable, PR-reviewable state that lives with the code; a stateless,
  shareable, cacheable knowledge graph; 7 tools removed (23 to 16).

---

## 7. Open items to resolve before implementing

1. get_steps_for_scope_tier's knowledge role - decide whether to fold scoped-step
   retrieval into analyze_upgrade_path or keep a context-free knowledge-only variant.
   This is the one removal that is not purely mechanical.
2. Folder location - migration/ at root vs. nested under specs/ for SpecKit repos. Pick
   one default; make the other a documented override.
3. Submission trigger - confirm execute's tail owns submit_migration_insight, and define
   exactly which outcomes qualify as novel enough to submit.
4. Stale-snapshot policy - how stale can plan.md's graph snapshot be before execute forces
   a re-plan rather than just noting drift? (Left open, same spirit as
   hybrid-plan-rendering.md section 7.)
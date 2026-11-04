---
name: framework-migration-execute
description: >
  Execute stage — work tasks sequentially from tasks.md, update Status inline,
  finalize verification.md, and run the completion gate.
compatibility:
  tools:
    - build_recipe_plan
    - resolve_deprecation
    - entity_evolution
    - search_migration_knowledge
    - search_openrewrite_recipes
    - get_graph_schema
    - execute_custom_cypher
    - get_community_insights
    - install_migration_skill
---

# Execute Stage — Sequential Task Execution

Invoked via `/migration-execute`. After execute completes (all tasks worked + Level 5
gate passed), the migration is done.

## File boundary

**Reads:** `ps-migration/{framework}-{from}-to-{to}/tasks.md`, `plan.md`
**Writes:** `tasks.md` Status lines; finalizes `verification.md` at the end.

**Graph:** Knowledge-read only when stuck (search-before-skip). Never write session state.
Allowed reads: `search_migration_knowledge`, `resolve_deprecation`, `entity_evolution`.

## Entry

1. Locate `ps-migration/{framework}-{from}-to-{to}/`.
2. Verify all three files exist (`plan.md`, `tasks.md`, `verification.md`). If missing,
   stop — run `/migration-plan` first.
3. Read `tasks.md` — find the first task with `Status: pending`.
4. Read `plan.md` for provenance, Paysafe dependency table, and staleness check.

## Staleness check

If `plan.md`'s `Generated` date is older than 7 days, surface a staleness warning to the
operator. Do not auto-replan — the operator decides whether to re-run `/migration-plan` or
continue.

## Work queue

Process TASK-001 through TASK-NNN strictly in order. Valid statuses:

`pending | done | failed | needs-review`

Update each task's `**Status**:` line directly in tasks.md after each task is worked.

## Executor-selection decision table

Read `Executor`, `Recipe`, `Effort`, `Instructions`, `Before/After`, and `Applicability`
from each task block. Evaluate rows top-to-bottom; first matching row wins. The
`automatable` flag is metadata only — it is never a routing input.

| # | Recipe state | Effort | Concrete instruction + entity anchor | Track |
|---|---|---|---|---|
| 1 | Fully resolved (`auto=true AND missingRequiredParams=[]`) | any | any | **OpenRewrite** |
| 2 | Partially resolved (`auto=false` OR `missingRequiredParams≠[]`) | any | any | **Prompted-auto** |
| 3 | None | `mechanical` | Yes | **Agent-codemod** |
| 4 | None | `moderate` | Yes | **Agent-codemod** |
| 5 | None | `mechanical` | No | **Human-review** |
| 6 | None | `moderate` | No | **Human-review** |
| 7 | None | `architectural` | any | **Human-review** |

### "Concrete instruction" definition

The task's `Instructions` field qualifies as concrete if it includes at least one of:

- A before/after transformation example (in the `Before/After` field)
- A named operation (`rename`, `replace`, `remove`, `add`) with explicit source and target
- A pattern + replacement target

Free-text descriptions without a transformation pattern do NOT qualify — route to
human-review (rows 5–7).

### "Entity anchor" definition

At least one entity in the task's affected-entity set has `Applicability: matched` (a
direct hit from the codebase scan, not `uncertain` or `universal`).

## Track behaviours

### OpenRewrite

Use `build_recipe_plan` to assemble a `rewrite.yml` from all consecutive OpenRewrite-track
tasks. Batch ALL eligible tasks into a single `rewrite.yml`. Apply via OpenRewrite CLI.
Do not run per-task builds within the batch.

**Batch failure:** if the batch fails, roll back the entire batch (`git stash push`) and
escalate all tasks in the batch to human-review individually. Set `Status: failed` for
each, with reason noting the batch failure.

After a successful batch, set `Status: done` for each task in the batch.

### Prompted-auto

Surface missing recipe parameters to the engineer. If provided: patch recipe params and
re-evaluate the task at row 1 (OpenRewrite). If declined: re-route to human-review.

### Agent-codemod

Full protocol:

```
1. BLAST-RADIUS GATE
   a. Identify all files matching the entity anchor and instruction scope.
   b. Present the complete file list to the engineer.
   c. Check project-level blast_radius_confirm_threshold (default: 0 = always confirm).
      - File count EXCEEDS threshold (or threshold=0): require explicit confirmation.
      - File count AT OR BELOW non-zero threshold: auto-confirm.
        Log: "Auto-confirming: {N} files ≤ threshold {T}."
   d. threshold=0 requires confirmation for ANY file count.

2. IDEMPOTENCY CHECK
   a. Inspect the target files for the transformation described in Instructions.
   b. If the change has already been applied (content matches the After state):
      set Status: done immediately. Do not re-apply.

3. APPLY TRANSFORMATION
   a. Make the code change.
   b. Record every modified file path (feeds terminal verification).

4. PER-TASK VERIFICATION
   a. Run the check described in the task's Verify field.
   b. If Verify is empty, skip to step 5.
   c. On verification failure: set Status: failed, note the error. Continue to next task
      (fix-forward — see below).

5. MARK DONE
   a. Set Status: done in tasks.md.
   b. Continue to the next pending task.
```

### Human-review

Emit a step card containing:

- Task ID and summary
- Full Instructions text
- Before/After examples (if present)
- Verify hint
- Effort level
- Severity (from plan.md Rule Ledger)

Wait for engineer response. Three possible outcomes:

| Response | Action |
|---|---|
| **Confirm** | Engineer applies the fix. Set `Status: done`. |
| **Skip** | Set `Status: needs-review` with engineer's reason. |
| **Architectural** | Pause the loop. Emit a design decision prompt. Wait for the engineer's design choice. Record the choice as a note in tasks.md. Then resume and re-evaluate the task. |

## Fix-forward policy

On per-task verification failure: set `Status: failed`, apply a targeted fix if obvious,
and continue to the next task. Do not halt the loop or revert prior tasks. Failed tasks
are addressed during terminal verification or in a follow-up pass.

## Drift rule

If a knowledge query (when stuck) reveals a rule has changed since plan.md was generated,
add a drift note to tasks.md below the affected task:

```
**Drift**: Graph rule {RuleID} has changed since plan generation. Files are the source
of truth for progress; graph is the source of truth for knowledge.
```

Do not silently re-plan or modify the task's Instructions.

## Paysafe constraint

Never modify, remove, or downgrade any dependency whose groupId starts with `com.paysafe`.
If a build error implicates a Paysafe library, fix the consuming code — do not touch the
Paysafe dependency itself.

## Knowledge queries when stuck

Before marking a task `needs-review`, attempt these graph reads in order:

1. `search_migration_knowledge` — keyword/semantic search for the entity or error
2. `resolve_deprecation` — check if the entity has a deprecation chain
3. `entity_evolution` — trace the `REPLACED_BY` chain for a replacement

If any query returns actionable guidance, apply it and mark `done`. If all three return
nothing useful, then mark `needs-review` with the reason.

## Rollback

Load `references/rollback.md` for the full revert procedure.

On catastrophic build failure requiring full revert:

1. `git stash push -m "rollback: failed migration task {TASK-ID}"`
2. Verify the build passes after stash.
3. Set `Status: failed` in tasks.md for the failing task, noting the error.
4. If the build still fails after stash, prior tasks may be involved — surface the
   situation to the operator and set `Status: needs-review` on the suspect tasks.
5. Continue to the next pending task (fix-forward).

Progress is tracked entirely in tasks.md — there is no graph-backed migration session.

## Terminal verification

After all tasks are worked:

1. **Finalize verification.md** — replace placeholder tokens (`{build command}`,
   `{unit test command}`, `{integration test command}`, `{run command}`) with commands
   discovered from the repo's build files. Do not rewrite other content.

2. **Run Levels 0–5** in sequence, stopping on first failure:

   | Level | Check |
   |---|---|
   | **0** | Static residue — no removed API symbols remain (grep/search, no build needed) |
   | **1** | Clean build |
   | **2** | Unit tests pass |
   | **3** | Integration tests pass |
   | **4** | App starts, health endpoint returns UP |
   | **5-A** | Paysafe constraint — `git diff` shows no `com.paysafe.*` version downgrades |
   | **5-B** | Zero `pending`/`failed` tasks; any `needs-review` requires explicit sign-off |
   | **5-C** | All Relevance-Index entries resolved (promoted or dismissed) |

3. **Sign-off format** for 5-B:

   ```
   **Sign-off**: [@username] [YYYY-MM-DD] — Reviewed and confirmed safe to proceed.
   ```

## Insight submission

`submit_migration_insight` is **user-initiated only**. After a successful manual-origin or
clarified fix, the operator may choose to submit the outcome to the knowledge graph.
The execute stage never auto-submits.
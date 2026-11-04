# Migration Harness — Operator Guide

This guide describes the six-stage linear migration workflow. Progress lives entirely in
version-controlled markdown files under `ps-migration/` in the consumer repository. The
knowledge graph is read-only for migration session state.

## Folder Contents

Each migration creates one folder at:

```
$PROJECT_ROOT/ps-migration/{framework}-{from}-to-{to}/
```

| File | Purpose |
|---|---|
| `research.md` | Optional checkpoint of knowledge-query results (scan, rules, dependencies, recipes) |
| `plan.md` | Strategy, rule ledger, dependency table, drift rule, provenance anchor |
| `tasks.md` | Ordered work queue (TASK-001..NNN), Relevance Index, inline status |
| `verification.md` | Levels 0–5 completion gate (build/test/run commands finalized by execute) |

Resume a migration by re-reading this folder and checking `git status`. There is no
session state in Neo4j.

## Setup

Run `install_migration_skill()` once per consumer project (or once per repo checkout).
By default, bundles install into `.cursor/skills/` (or `.claude/skills/` for Claude Code)
at the project root so slash commands travel with the repository. Use `scope="global"` to
install under `~/.cursor/skills/` instead. Teams may commit project-local bundles or
add them to `.gitignore` — that choice is yours.

**Full-mode install bundles** (six top-level directories):

| Bundle | Source skill file |
|---|---|
| `framework-migration-research` | `framework-migration/research.md` |
| `framework-migration-plan` | `framework-migration/plan.md` (+ `scanning.md`, `version-map.md` references) |
| `framework-migration-gap-check` | `framework-migration/gap-check.md` |
| `framework-migration-clarify` | `framework-migration/clarify.md` |
| `framework-migration-preview` | `framework-migration/preview.md` |
| `framework-migration-execute` | `framework-migration/execute.md` (+ `rollback.md` reference) |

## Stage Sequence

Run stages in order. `research` and `clarify`/`preview` are optional.

```
/migration-research (optional) → /migration-plan → /migration-gap-check → /migration-clarify (optional) → /migration-preview (optional) → /migration-execute
```

| Stage | Command | What it does | Graph access | File access |
|---|---|---|---|---|
| **research** | `/migration-research` | Scans codebase, queries knowledge graph, emits `research.md` checkpoint | Knowledge-read only | Writes `research.md` only |
| **plan** | `/migration-plan` | Scans codebase, queries knowledge graph (or consumes research artifact), emits files | Knowledge-read only | Writes all three plan files |
| **gap-check** | `/migration-gap-check` | Flags mechanical gaps: missing verifiers, unclassified rules, empty instructions | None | Annotates `plan.md` and `tasks.md` |
| **clarify** | `/migration-clarify` | Resolves Relevance-Index entries: promote to TASK (Origin: manual) or dismiss with reason | None | Edits `tasks.md` only |
| **preview** | `/migration-preview` | Read-only risk-grouped rendering for human review before execution | None | Reads `plan.md` and `tasks.md` |
| **execute** | `/migration-execute` | Works TASK-001..NNN sequentially, updates Status inline, finalizes verification | Knowledge-read when stuck | Edits `tasks.md`; finalizes `verification.md` |

Canonical file schemas live in `migration_oracle/mcp/skills/templates/`.

## Task Status Values

Each task in `tasks.md` carries a `Status` field with one of four values:

| Status | Meaning |
|---|---|
| `pending` | Not yet attempted (the only non-terminal state) |
| `done` | Successfully applied and verified |
| `failed` | Applied but build/test failed; marked for fix-forward |
| `needs-review` | Agent got stuck, or human chose to defer — requires explicit sign-off |

There is no `deferred` status. `needs-review` covers both "agent couldn't resolve" and
"human consciously skipped."

## Resumption

1. Locate the migration folder under `ps-migration/`.
2. Read `tasks.md` — the first `pending` task is where `/migration-execute` resumes.
3. Check `git status` for uncommitted progress.
4. Run `/migration-execute` — it picks up from the first pending task.

If `plan.md`'s `Generated` date is older than 7 days, execute surfaces a staleness
warning but does not auto-replan.

**To start fresh:** delete or archive the existing `ps-migration/` folder and re-run
`/migration-plan` from the beginning.

## Drift Rule

`plan.md` is a point-in-time knowledge snapshot. If execute or clarify re-queries the
graph and finds a rule changed: files are the source of truth for progress; the graph is
the source of truth for knowledge. On divergence, a drift note is added to `tasks.md` —
the harness never silently re-plans.

## Verification Gating

After all tasks are worked, execute finalizes `verification.md` — replacing placeholder
tokens (`{build command}`, `{unit test command}`, etc.) with commands discovered from the
repo — and runs Levels 0–5 in sequence, stopping on first failure:

| Level | Check |
|---|---|
| **0** | Static residue — no removed API symbols remain (no build needed) |
| **1** | Clean build |
| **2** | Unit tests pass |
| **3** | Integration tests pass |
| **4** | App starts, health endpoint returns UP |
| **5-A** | Paysafe constraint — no `com.paysafe.*` dependency downgraded |
| **5-B** | Zero `pending`/`failed` tasks; every `needs-review` task has explicit sign-off |
| **5-C** | All Relevance-Index entries resolved (promoted or dismissed with reason) |

The sign-off format for 5-B:

```
**Sign-off**: [@username] [YYYY-MM-DD] — Reviewed and confirmed safe to proceed.
```

## Paysafe Constraint

The Paysafe constraint is absolute throughout all stages:

- Never modify, remove, or downgrade any dependency whose groupId starts with `com.paysafe`.
- If a build error implicates a Paysafe library, fix the consuming code — do not touch the
  Paysafe dependency itself.
- Unresolved Paysafe dependencies from `resolve_paysafe_dependency_by_service_name` errors
  appear in `plan.md`'s Dependency Updates table with unresolved status — they are never
  silently dropped.

## Insight Submission

`submit_migration_insight` is **user-initiated only**. No stage auto-submits insights.
After a successful manual-origin or clarified fix, the operator may choose to submit the
outcome to the knowledge graph by asking their agent:
"Submit a migration insight for [description of the fix]."

## After Completion

When all Level 0–5 checks pass: the migration is complete. Remove the `ps-migration/`
folder and commit, or archive it for reference.
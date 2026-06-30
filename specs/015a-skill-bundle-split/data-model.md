# Data Model: Split Migration Harness Skill Bundles

## 1. Skill Bundle Manifest Delta

`install_migration_skill`'s internal bundle-definition list (consumed by its filesystem-write
logic, per `research.md` R1 — the same list-iteration mechanism already used for `lite` mode's
two-bundle install) changes for `MIGRATION_MODE=full` from one entry to six:

**Before:**
```python
FULL_MODE_BUNDLES = [
    {"name": "framework-migration", "skill_md": "framework_migration_main.md",
     "references": ["framework_migration_scanning.md", "framework_migration_version_map.md",
                     "framework_migration_plan_format.md", "framework_migration_gap_check.md",
                     "framework_migration_clarify.md", "framework_migration_preview.md"]},
]
```

**After:**
```python
FULL_MODE_BUNDLES = [
    {"name": "framework-migration-plan", "skill_md": "framework_migration_plan.md",
     "references": ["framework_migration_scanning.md", "framework_migration_version_map.md"]},
    {"name": "framework-migration-gap-check", "skill_md": "framework_migration_gap_check.md",
     "references": []},
    {"name": "framework-migration-clarify", "skill_md": "framework_migration_clarify.md",
     "references": []},
    {"name": "framework-migration-preview", "skill_md": "framework_migration_preview.md",
     "references": []},
    {"name": "framework-migration-execute", "skill_md": "framework_migration_execute.md",
     "references": ["framework_migration_rollback.md"]},
    {"name": "framework-migration-feedback", "skill_md": "framework_migration_feedback.md",
     "references": []},
]
```

`framework_migration_plan_format.md` is intentionally omitted from this manifest's `references`
lists — per `015`'s design, `preview` renders via that file's schema, but `015` already
established this as a rendering-logic reuse, not a packaged file dependency; if `preview`'s
`SKILL.md` needs the actual schema reference bundled, add `framework_migration_plan_format.md`
to `framework-migration-preview`'s `references` list as a follow-up — flagged here rather than
assumed, since no artifact in this thread confirms whether `015`'s preview implementation reads
that file from disk at runtime or has its schema inlined into the skill prose already.

**Idempotency note**: This manifest change is additive at the *definition* level — it does not
by itself address what happens to the old single-bundle layout already on disk from before this
fix (that is FR-010, see §3 below).

---

## 2. `compatibility.tools` Frontmatter Per Bundle

Each of the six `SKILL.md` files' YAML frontmatter gets a `compatibility.tools` list. Per
`research.md` R2, this field already exists as a convention (`migration-lite/SKILL.md`'s
frontmatter) — this is population of an existing field, not a new schema element.

Exact values are specified in `plan.md`'s "`compatibility.tools` Per Bundle" table, copied
verbatim from `015`'s `contracts/015-split-migration-harness.md` exposure matrix. That table is
the single source of truth; do not re-derive these lists independently while implementing.

**Format** (matching `migration-lite`'s existing structure exactly):
```yaml
---
name: framework-migration-preview
description: >
  Read-only rendering of a migration plan's pending steps, grouped by risk label, with
  gap-check findings shown as visible caveats. Exposes no mutation tools. Use this skill
  when a customer or reviewer needs to see what a migration will do without any risk of
  changing it.
compatibility:
  tools:
    - get_pending_steps
    - get_migration_contexts
---
```

---

## 3. FR-010 — Stale Single-Bundle Layout Handling

**Status: DEFERRED (follow-up outside 015a scope).** Investigated 2026-06-18 against
`migration_oracle/mcp/tools/install.py` (`_install_to_target`, lines 70–109).

**Confirmed current behavior** (`install.py:_install_to_target`):
1. Files are staged in a temp directory, then copied with `shutil.copy2` into the target tree.
2. Existing files at the same relative path are **silently overwritten** — no conflict error.
3. Stale directories or files **not present in the new manifest are never deleted** (e.g. a prior
   `framework-migration/references/gap-check.md` would remain on disk after re-install).
4. On install failure mid-copy, only partial files from the **current** attempt are unlinked;
   pre-existing stale content is untouched.

**Disposition**: No detect-and-remove or detect-and-warn logic is implemented in 015a. Operators
with the old single-bundle `framework-migration/` layout should manually remove it after running
`install_migration_skill` in full mode, or accept orphaned files alongside the six new bundles.
A follow-up spec may add parameterized stale-layout cleanup mirroring `write_gap_check_flags`'s
`overwrite` precedent.

---

## 4. `get_migration_contexts` Return-Shape Extension (FR-011 Decision)

Per `plan.md`'s explicit decision (Option (a)), `get_migration_contexts`'s Cypher and return
projection gain two additive fields. This is a cross-spec touch into `015`'s already-shipped
`context.py` — scoped narrowly and additively per `plan.md`'s framing.

**Before** (confirmed real shape, per `research.md` R4):
```json
{
  "status": "ok",
  "project_id": "...",
  "count": 1,
  "contexts": [
    {
      "id": "...", "projectId": "...", "fromVersion": "3.3.0", "toVersion": "3.4.0",
      "framework": "Spring Boot", "status": "in_progress",
      "createdAt": "...", "updatedAt": "...",
      "outcome_counts": {"completed": 4, "failed": 0, "skipped": 1, "deferred": 0}
    }
  ]
}
```

**After:**
```json
{
  "status": "ok",
  "project_id": "...",
  "count": 1,
  "contexts": [
    {
      "id": "...", "projectId": "...", "fromVersion": "3.3.0", "toVersion": "3.4.0",
      "framework": "Spring Boot", "status": "in_progress",
      "createdAt": "...", "updatedAt": "...",
      "outcome_counts": {"completed": 4, "failed": 0, "skipped": 1, "deferred": 0, "excluded": 2},
      "has_gap_check_flags": true
    }
  ]
}
```

**Cypher delta** (additive `WITH`/`RETURN` clauses only — existing aggregation logic for the
other four outcome buckets is untouched):
```cypher
// existing aggregation pattern extended with one more CASE branch:
count(CASE WHEN so.status = 'excluded' THEN 1 END) AS excluded_count

// new, separate presence check (cheap -- does not deserialize/return the flag list itself):
WITH ctx, has_gap_check_flags: (ctx.gapCheckFlags IS NOT NULL AND ctx.gapCheckFlags <> '[]')
```

**Backward compatibility**: Both new fields are additive. Existing callers reading only the
four original `outcome_counts` keys are unaffected; `has_gap_check_flags` is a new top-level key
on each context entry, not a replacement of any existing key. This mirrors the precedent set by
`lite` mode's additive `mode`/`installed_skills` fields on `install_migration_skill`'s payload.

---

## 5. `resume_migration` Stage-Determination Decision Table (Final)

Now implementable given §4's extension. This is the production version of `research.md` R4's
draft table, with the previously-blocking branch resolved:

```
IF context.status IN ("complete", "partial", "abandoned")
    -> no stage to resume; report closed, do not suggest a bundle

ELSE IF has_gap_check_flags == true
        AND outcome_counts.excluded == 0
        AND outcome_counts.completed == 0
        AND outcome_counts.failed == 0
    -> gap-check ran, nothing acted on yet -> suggest "framework-migration-clarify"
       (checked before the zero-outcomes branch so flagged contexts are not re-suggested gap-check)

ELSE IF sum(outcome_counts.values()) == 0
    -> context exists but nothing has been gap-checked or executed yet
       -> suggest "framework-migration-gap-check"

ELSE IF outcome_counts.failed > 0 OR outcome_counts.deferred > 0
    -> suggest "framework-migration-execute" (resume unfinished/failed work)

ELSE IF (outcome_counts.completed + outcome_counts.excluded + outcome_counts.failed
          + outcome_counts.skipped) == <total step count for context>
        AND context.status != closed
    -> suggest "framework-migration-feedback" (everything accounted for, ready to close)

ELSE
    -> suggest "framework-migration-execute" (steps remain with no outcome yet)
```

**Open implementation note**: `<total step count for context>` is not directly present in
`get_migration_contexts`'s shape either — it would need to come from a `get_pending_steps` call
or a count derived from `outcome_counts` plus however many steps have no `STEP_OUTCOME` edge at
all. This is a smaller, mechanical gap than §3/§4 (not requiring a new design decision, just an
additional read), but should be confirmed during implementation rather than assumed to be free.

---

## 6. Single-Consumer Reference Relocation (FR-004, User Story 3)

| File | Old location | New location |
|---|---|---|
| `framework_migration_scanning.md` | `framework-migration/references/` | `framework-migration-plan/references/` |
| `framework_migration_version_map.md` | `framework-migration/references/` | `framework-migration-plan/references/` |
| `framework_migration_rollback.md` | `framework-migration/references/` | `framework-migration-execute/references/` |

No new "shared" bundle is created. Per `research.md` R5, `migration-lite`'s existing copy of
`version-map.md` (currently sourced from the old `framework-migration` bundle, per
`MIGRATION_LITE_MODE.md`'s "shared with framework-migration" comment) must have its source path
updated to `framework-migration-plan/references/version-map.md` — whatever copy-vs-symlink
mechanism produces that file for `migration-lite` needs its source reference updated as part of
this relocation, not left pointing at a path that no longer exists post-fix.
# Contracts: Split Migration Harness Skill Bundles

## Bundle Frontmatter Contract

Every one of the six new bundles' `SKILL.md` MUST declare:
- `name`: the bundle's directory name (e.g. `framework-migration-gap-check`)
- `description`: scoped to that stage only — MUST NOT describe another stage's procedure
- `compatibility.tools`: exact list per `plan.md`'s `compatibility.tools` Per Bundle table

No bundle's `compatibility.tools` list MAY include a tool marked ❌ for that stage in `015`'s
exposure matrix. No bundle's `compatibility.tools` list MAY omit a tool marked ✅ for that stage.

## Install Manifest Contract

`install_migration_skill()` called with `MIGRATION_MODE=full` MUST write exactly six top-level
bundle directories, per `data-model.md` §1's `FULL_MODE_BUNDLES` list. The tool's return payload
MUST list all six bundle names individually under `installed_skills`, mirroring `lite` mode's
existing `installed_skills` field shape (`["migration-lite", "openrewrite-runner"]` style list,
not a single string).

`MIGRATION_MODE=lite` behavior is UNCHANGED by this spec — `migration-lite` +
`openrewrite-runner` continue to install exactly as documented in `MIGRATION_LITE_MODE.md`,
except for `version-map.md`'s source-path update (data-model.md §6).

## `get_migration_contexts` Contract Delta

**Existing fields** (`id`, `projectId`, `fromVersion`, `toVersion`, `framework`, `status`,
`createdAt`, `updatedAt`, and `outcome_counts.{completed,failed,skipped,deferred}`) are
UNCHANGED — same names, same types, same semantics.

**New fields**, additive only:
- `outcome_counts.excluded` (integer) — count of `STEP_OUTCOME` relationships with
  `status="excluded"` for this context.
- `has_gap_check_flags` (boolean) — `true` if `ctx.gapCheckFlags` is set and not an empty list,
  `false` otherwise.

Any existing caller that does not read these two new fields is unaffected. No existing field is
renamed, removed, or has its type or meaning changed.

## Prompt Contract Delta

`start_migration`'s prompt text changes its `Load skill://...` line from
`skill://framework-migration/main` to `skill://framework-migration-plan/main`. No other change
to `start_migration`'s parameters or remaining prompt body.

`resume_migration`'s prompt text changes from a fixed `Load skill://framework-migration/main`
line to a computed line selecting one of the six bundle URIs, per `data-model.md` §5's decision
table. `resume_migration`'s parameters (`context_id`) are UNCHANGED.

## Out of Scope (Explicit Non-Goals)

- `015`'s `MCP_ACTIVE_STAGE` server-side tool-gating mechanism is NOT modified by this spec.
- `015`'s `gap-check`/`clarify`/`preview` *procedural logic* (what each stage actually does) is
  NOT modified — only how that already-written content is packaged into installable bundles.
- No new MCP tool is introduced by this spec. `get_migration_contexts` is extended, not replaced
  or duplicated.
- FR-010's stale-layout handling is NOT implemented until `data-model.md` §3's blocking
  investigation is complete — `tasks.md` MUST NOT contain an implementation task for this until
  that section is resolved with cited source evidence.

## T022 Confirmation — `get_steps_for_scope_tier` on gap-check (2026-06-18)

`framework-migration-gap-check`'s `compatibility.tools` includes `get_steps_for_scope_tier`.
This was **deliberately confirmed**, not copied unchecked from a stale matrix cell:

- **015 contract** (`contracts/015-split-migration-harness.md` footnote \*\*): gap-check exposes
  `get_steps_for_scope_tier` for tier-bucketed step reads required by the stepless-rule and
  bridge-eligibility checks.
- **Skill implementation** (`framework_migration_gap_check.md` § Stepless-rule check): calls
  `get_steps_for_scope_tier` per scope tier.
- **015 contract** explicitly excludes `analyze_upgrade_path` from gap-check (truncation reads
  cached `diagnostics` on the context instead) — that exclusion is preserved; only
  `get_steps_for_scope_tier` was added for the audit checks above.

`analyze_upgrade_path` does **not** appear on gap-check's tool list.
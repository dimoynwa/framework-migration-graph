# Research: Split Migration Harness Skill Bundles

**Spec**: `015a-skill-bundle-split`
**Purpose**: Resolve the two UNRESOLVED items in `spec.md` (FR-010, FR-011) before `/speckit.plan`, and document the precedent this fix is modeled on so plan.md doesn't need to re-derive it.

---

## R1. Precedent — How `install_migration_skill` Already Supports Multi-Bundle Installation

**Question**: Does the existing tool actually support writing multiple independent top-level bundles in one call, or would this require new mechanism, not just new content?

**Finding**: It already does. Per `MIGRATION_LITE_MODE.md`'s documented `lite`-mode behavior, a single `install_migration_skill()` call writes two independent top-level bundles:

```
migration-lite/
├── SKILL.md
└── references/
    └── version-map.md

openrewrite-runner/
├── SKILL.md
└── references/
    ├── recipe-catalog.md
    └── examples.md
```

Both are written "together" in one call — the tool's existing logic already iterates a *list* of bundle definitions for the active mode and writes each independently, rather than assuming one bundle per mode. The `full`-mode path today happens to use a list of length one (`framework-migration`), which is why it doesn't already exhibit this bug at the install-mechanism level — the mechanism is multi-bundle-capable; only the `full`-mode bundle *definition* needs to change from one entry to six.

**Conclusion**: No new install mechanism is needed. This is a content/manifest change to the `full`-mode bundle list, not a new code path. `plan.md` should scope this as "extend the existing per-mode bundle list from 1 entry to 6 entries for `full`," not "build multi-bundle support."

**Source**: `MIGRATION_LITE_MODE.md` §11 (Skill Installation), bundle-map table and directory tree shown verbatim.

---

## R2. FR-005 Verification — Does a `compatibility.tools` Convention Already Exist to Extend?

**Question**: Is `compatibility.tools` an established frontmatter field, or would this spec be inventing a new convention?

**Finding**: Established. `migration-lite/SKILL.md`'s actual frontmatter (quoted in `MIGRATION_LITE_MODE.md` Appendix A) already includes:

```yaml
compatibility:
  tools:
    - resolve_paysafe_dependency_by_service_name
    - analyze_upgrade_path
    - search_migration_knowledge
    - install_migration_skill
  skills:
    - openrewrite-runner   # loaded on demand in Phase 3, Java/JVM projects only
```

This confirms two things plan.md can rely on directly:
1. `compatibility.tools` is a real, already-used field — FR-005 is asking for population of an existing convention, not invention of a new one.
2. `compatibility.skills` is also an established sibling field, used for one bundle to declare a same-mode dependency on another (`migration-lite` → `openrewrite-runner`). This is the natural place to put the "next stage" pointer from FR-003's exemption (e.g. `framework-migration-gap-check`'s frontmatter could declare `compatibility.skills: [framework-migration-clarify]` as an *optional, conditional* next step) — worth plan.md considering as the structured form of the "brief one-line pointer" FR-003 allows in prose, rather than only prose.

**Open sub-question for plan.md, not blocking**: should the natural-next-stage relationship be expressed only in prose (simplest) or also structurally via `compatibility.skills` (more consistent with precedent, but implies a fixed next-stage even though `015` made `clarify` optional and `gap-check`→`execute` a valid skip path)? Given `015`'s explicit design that stage progression is non-linear (clarify is skippable; gap-check can lead straight to execute), a fixed `compatibility.skills` next-stage declaration may overstate a hard dependency that doesn't exist. **Recommendation**: prose-only pointers, no `compatibility.skills` entries between the six new bundles, to avoid implying a mandatory sequence the underlying design explicitly rejected.

---

## R3. FR-010 — Stale Single-Bundle Layout Migration Path

**Question**: What should happen when `install_migration_skill()` runs against a target directory that already has the old `framework-migration/` single-bundle layout on disk from before this fix?

**Investigation**: `mcp-tools-skills-prompts.md` and `MIGRATION_LITE_MODE.md` describe `install_migration_skill`'s parameters (`target`, `target_dir`) and return payload (`status`, `target`, `installed_paths`, `message`, plus `lite`-mode's additive `mode`/`installed_skills` fields) but **neither document specifies the tool's overwrite behavior** — whether it currently fails if a target file exists, silently overwrites, or skips existing files. This is a genuine gap in the existing documentation, not something this research can resolve by reading further docs.

**What would need to happen to actually resolve this** (for whoever picks up `/speckit.plan`):
1. Read the actual current implementation of `install_migration_skill`'s filesystem-write logic (not yet shown in this thread — only its documented contract has been reviewed) to determine today's real overwrite semantics.
2. Three candidate behaviors, listed for plan.md to choose from once (1) is known — none selected here since picking one without checking the implementation would repeat the exact mistake flagged earlier in this thread (asserting a resolution without checking the actual mechanism):
   - **(a) Detect-and-remove**: if `framework-migration/` (old layout) exists at the target, remove it before writing the six new bundles. Cleanest end state; destructive if anything was hand-edited in the old layout.
   - **(b) Detect-and-warn**: leave the old directory in place, but include a warning in the return payload's `message` field telling the operator to remove it manually. Safer, but leaves stale/misleading content on disk indefinitely if ignored.
   - **(c) No special handling**: six new bundles are written alongside the untouched old `framework-migration/` directory. Simplest to implement, worst end state — exactly the confusing duplicate-content scenario Edge Case 1 in spec.md warns about.
3. Given this tool already has an `overwrite`-adjacent precedent in a *different* tool in this same codebase (`write_gap_check_flags`'s `overwrite` boolean parameter, per `015`'s `data-model.md` §8), option (a) or a parameterized version of it (an explicit `clean_stale_layout: bool` argument, defaulting to a safe choice) is the most consistent style with how this codebase already handles "old data vs. new data" conflicts elsewhere. This is a **recommendation to investigate first**, not a resolution — FR-010 remains UNRESOLVED until the actual current overwrite behavior is confirmed.

**Status**: Remains UNRESOLVED. Carry into `plan.md` as a required Phase 0 investigation step: read `install_migration_skill`'s actual current source before designing the migration path.

---

## R4. FR-011 — `resume_migration` Stage-Determination Logic

**Question**: What `MigrationContext` state is actually queryable, and can a decision table for "which bundle should resume_migration suggest" be built from it?

**Finding — RESOLVED.** `mcp-tools-skills-prompts.md`'s actual tool reference for `get_migration_contexts` was located and quotes its full return shape:

> **Returns**: `status`, `project_id`, `count` (0 when none exist — not an error), `contexts` —
> each entry: `id`, `projectId`, `fromVersion`, `toVersion`, `framework`, `status`, `createdAt`,
> `updatedAt`, `outcome_counts`. Each `outcome_counts` object has `completed`, `failed`,
> `skipped`, `deferred` — derived from `STEP_OUTCOME` relationships.

This changes the picture from R4's original hypothesis in two important ways:

1. **`gapCheckFlags` is NOT in `get_migration_contexts`'s return shape.** Per `015`'s
   `data-model.md` §3, `gapCheckFlags` is a property written directly on the `MigrationContext`
   node, but the tool's documented `RETURN` projection doesn't include it — only the six
   `outcome_counts` buckets and basic identifying fields are returned today. If `resume_migration`
   needs to know whether gap-check has run, either (a) `get_migration_contexts` needs a new
   returned field for this spec, or (b) a separate read is needed (e.g. `execute_custom_cypher`,
   read-only, or a new lightweight tool). This is a **new finding this research surfaces that
   `015` did not have to solve**, since `015` only ever needed `write_gap_check_flags` to persist
   the property — nothing in `015` needed to *read* it back from a list-style query.
2. **`outcome_counts` has no `excluded` bucket.** It lists `completed`, `failed`, `skipped`,
   `deferred` — not `excluded`. This was written before `015`'s `excluded` outcome value existed
   (per `015`'s own `data-model.md` §2, `excluded` is a `015`-introduced addition to the
   `STEP_OUTCOME` enum). This means **`015`'s implementation likely needs a one-line addition to
   `get_migration_contexts`'s Cypher** to add an `excluded` count alongside the existing four —
   otherwise no list-based tool can ever see that any steps were excluded without a dedicated
   per-step query. This is a real, previously-undetected gap in `015`'s own implementation,
   found only because `016` needed to read this state back. Worth flagging to whoever owns `015`
   even though it's surfaced here.

**Revised decision table**, now grounded in the real return shape rather than a hypothesis:

```
IF context.status == "complete" | "partial" | "abandoned"   → no stage to resume; report closed
ELSE IF gapCheckFlags-equivalent signal is unavailable        → cannot determine gap-check state
        from get_migration_contexts alone; BLOCKED until
        (1) or (2) above is decided
ELSE IF outcome_counts shows 0 across all buckets             → suggest "gap-check" (nothing
                                                                  executed yet, but plan ran)
ELSE IF outcome_counts.failed > 0 OR outcome_counts.deferred>0 → suggest "execute" (resume
                                                                  unfinished work) — clarify
                                                                  optional/independent
ELSE IF sum(outcome_counts) == total pending steps             → suggest "feedback" (all
        AND context.status != closed                             accounted for, ready to close)
ELSE                                                            → suggest "execute" (steps
                                                                  remain with no outcome yet)
```

**Status**: **Partially resolved.** The real return shape is now known, which is strictly better
than the original hypothesis — but it surfaces a genuine blocking dependency: `016`'s
`resume_migration` logic cannot reliably detect "gap-check has run but clarify/execute haven't
started" or "steps were excluded" using `get_migration_contexts` as it exists today. **This must
be carried into `plan.md` as an explicit cross-spec dependency**: either `016`'s `plan.md` proposes
a small, additive extension to `get_migration_contexts`'s `RETURN` clause (adding `gapCheckFlags`
presence and an `excluded` count to `outcome_counts`), or `016` accepts a coarser, less accurate
decision table that can't distinguish those two states. This is a real design choice for
`plan.md` to make explicitly, not something `research.md` should decide unilaterally.

---

## R5. Confirmation — `version-map.md` Cross-Reference from `migration-lite`

**Question** (from spec.md Edge Cases): Does `migration-lite`'s existing reference to `framework-migration`'s `version-map.md` need re-pointing once that file moves under `framework-migration-plan/references/`?

**Finding**: Yes, mechanically — `MIGRATION_LITE_MODE.md`'s bundle tree explicitly shows:
```
migration-lite/
└── references/
    └── version-map.md                ← shared with framework-migration
```
The comment "shared with framework-migration" confirms this file is either copied or symlinked from the `framework-migration` bundle today. Once `version-map.md`'s canonical location moves to `framework-migration-plan/references/` (FR-004), whatever mechanism produces `migration-lite`'s copy (copy-on-install vs. symlink — not specified in any document reviewed so far) needs its source path updated to match.

**Status**: Mechanically necessary, low-risk, not a design question — just needs a task in `plan.md`'s scope to update the path reference. Not left UNRESOLVED, since unlike R3/R4 this doesn't require a new decision, only a path-string update.

---

## Summary of Carry-Forward Items for `plan.md`

| Item | Status | Action Required Before Finalizing data-model.md |
|---|---|---|
| Multi-bundle write mechanism | ✅ Confirmed to already exist | None — reuse as-is, scope as a manifest/content change only |
| `compatibility.tools` convention | ✅ Confirmed to already exist | Populate per FR-005; do not invent new frontmatter shape |
| Next-stage pointer style | Recommendation given (prose, not `compatibility.skills`) | plan.md should confirm or override this recommendation explicitly |
| FR-010 (stale layout handling) | ❌ Unresolved | `install_migration_skill`'s documented contract (`mcp-tools-skills-prompts.md`) says only "Copy bundled skill Markdown files" — no overwrite/conflict semantics are specified anywhere. This is a genuine undocumented gap, not something findable by further reading; plan.md must read the actual source or explicitly choose a behavior and document it as new. |
| FR-011 (resume_migration decision table) | 🟡 Partially resolved | Real `get_migration_contexts` return shape confirmed (`id`, `projectId`, `fromVersion`, `toVersion`, `framework`, `status`, `createdAt`, `updatedAt`, `outcome_counts` with `completed`/`failed`/`skipped`/`deferred`). **New blocking finding**: this shape has no `gapCheckFlags` signal and no `excluded` bucket — both are `015` additions the list-query was never updated to expose. plan.md must explicitly decide: extend `get_migration_contexts` (cross-spec change into `015`'s surface) or accept a coarser decision table. |
| `version-map.md` cross-reference | Mechanical fix, not a design gap | Add as a plan.md task; update whatever copy/symlink mechanism produces `migration-lite`'s copy |
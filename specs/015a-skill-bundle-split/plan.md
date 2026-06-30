# Implementation Plan: Split Migration Harness Skill Bundles

**Branch**: `015a-skill-bundle-split` | **Date**: 2026-06-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015a-skill-bundle-split/spec.md`, resolved findings from `research.md`

## Summary

Restructures `install_migration_skill`'s full-mode output from one bundle (`framework-migration`, with `gap-check`/`clarify`/`preview` incorrectly nested as `references/` files) into six independent top-level bundles, one per `015` stage. Per `research.md` R1/R2, this reuses the existing multi-bundle write mechanism and `compatibility.tools` frontmatter convention already proven by `migration-lite` + `openrewrite-runner` — no new install mechanism is built. Additionally updates `start_migration`/`resume_migration` prompts to be stage-aware, and makes one explicit, documented choice on the `015`-surface extension needed to support `resume_migration`'s stage-determination logic (FR-011).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: MCP SDK (filesystem-write skill installer), no new dependencies

**Storage**: Neo4j/Memgraph — only touched if the FR-011 decision below selects the `get_migration_contexts` extension path

**Testing**: pytest, plus manual bundle-content inspection (frontmatter parsing checks)

**Target Platform**: Cursor / Claude Code skill directories (filesystem), MCP server

**Project Type**: MCP server skill-packaging fix + prompt update

**Performance Goals**: N/A — this is a packaging/documentation-layer fix, not a runtime-performance change

**Constraints**: Must not change `015`'s server-side `MCP_ACTIVE_STAGE` tool-gating mechanism (out of scope per spec.md Assumptions). Must not introduce a seventh "shared" bundle (FR-004).

**Scale/Scope**: 6 skill bundles (replacing 1), 2 prompt updates, 1 install-manifest table update, 1 explicit cross-spec decision (FR-011)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Library-First**: N/A (skill-file packaging + prompt text)
- **CLI Interface**: N/A
- **Test-First**: Yes — bundle-structure and frontmatter-content checks are written before the bundle manifest is changed
- **Simplicity**: Six bundles, no shared seventh bundle (per FR-004); each single-consumer reference file folds directly into its one consuming bundle rather than inventing cross-bundle sharing infrastructure

**Research gate**: `research.md` R1–R5 must be read before this plan is acted on. R1 and R2 are confirmed precedents (no new mechanism needed). R3 (FR-010) is unresolved and requires reading `install_migration_skill`'s actual source before Phase 1 can finalize — this is **blocking** for FR-010-related tasks specifically, not for the rest of the spec. R4 (FR-011) is now resolved enough to make an explicit decision (see below). R5 is a mechanical, non-blocking fix.

---

## Decision: FR-011 Resolution

Per `research.md` R4, `get_migration_contexts`'s real return shape cannot distinguish "gap-check ran, nothing else has happened yet" from "steps were excluded during clarify" — it has no `gapCheckFlags` signal and no `excluded` bucket in `outcome_counts`.

**Decision taken**: **Option (a) — extend `get_migration_contexts`.** Add a `has_gap_check_flags: boolean` field (cheap presence check, not the full flag list — keeps the list-query lightweight) and an `excluded` count alongside the existing four `outcome_counts` buckets.

**Why not option (b) (accept a coarser table)**: A `resume_migration` that can't tell "fresh from plan, never gap-checked" apart from "gap-checked, ignored, jumped straight to execute" would suggest `gap-check` in both cases — which is harmless but actively unhelpful in the second case, since `clarify` (the next-natural-step after a flagged gap-check) would never be suggested at all, silently defeating one of `015`'s own central design goals (giving clarify findings visibility). The coarser table doesn't just lose precision, it loses the one signal that's supposed to prompt the optional-but-valuable `clarify` step. Given the extension is additive (two new fields, no existing field changed or removed) and mirrors `015`'s own established pattern of additive return-shape extensions (lite mode's `mode`/`installed_skills` fields on `install_migration_skill`'s payload), the cross-spec cost is low relative to the value preserved.

**Consequence for scope**: This plan now includes one task touching `015`'s `get_migration_contexts` Cypher (`migration_oracle/mcp/graph/queries/context.py`) and its return-shape documentation in `mcp-tools-skills-prompts.md`. This is flagged explicitly as a **cross-spec change**: `015` is marked ✅ Complete, so this is a small, additive amendment to already-shipped work, not new `015` scope creep. Treat it as a `015a` task that happens to touch a `015` file, not a reopening of `015`.

---

## Project Structure

### Documentation (this feature)

```text
specs/015a-skill-bundle-split/
├── spec.md              # Feature specification
├── research.md          # Phase 0 output (already complete)
├── plan.md              # This file
├── data-model.md        # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   └── 015a-skill-bundle-split.md
└── tasks.md              # Phase 2 output
```

### Source Code (repository root)

```text
migration_oracle/
└── mcp/
    ├── skills/
    │   ├── framework_migration_plan.md          # was: framework_migration_main.md's Loop I+II portion
    │   ├── framework_migration_gap_check.md      # was: nested reference under framework-migration/
    │   ├── framework_migration_clarify.md        # was: nested reference under framework-migration/
    │   ├── framework_migration_preview.md        # was: nested reference under framework-migration/
    │   ├── framework_migration_execute.md        # was: framework_migration_main.md's Loop III portion
    │   ├── framework_migration_feedback.md       # was: framework_migration_main.md's Loop IV portion
    │   ├── framework_migration_scanning.md       # unchanged content, moves under -plan bundle only
    │   ├── framework_migration_version_map.md    # unchanged content, moves under -plan bundle only
    │   └── framework_migration_rollback.md       # unchanged content, moves under -execute bundle only
    └── tools/
        ├── install.py                            # bundle manifest: 1 entry -> 6 entries for full mode
        └── context.py                            # get_migration_contexts Cypher: add has_gap_check_flags,
                                                    # excluded count (per FR-011 decision above)
```

**Structure Decision**: This is primarily a content-reorganization of existing skill markdown (splitting `framework_migration_main.md` into six files along its already-documented Loop I/II/III/IV + new-stage boundaries from `015`) plus one bundle-manifest change in `install.py` plus one small, additive Cypher change in `context.py`. No new modules.

---

## Bundle-to-Source Mapping

| New bundle | `SKILL.md` source content | `references/` content |
|---|---|---|
| `framework-migration-plan` | Loop I + Loop II procedure from `framework_migration_main.md` | `scanning.md`, `version-map.md` |
| `framework-migration-gap-check` | New content from `015`'s gap-check skill design (mode-aware single handler description, per `015` plan.md) | none |
| `framework-migration-clarify` | New content from `015`'s clarify skill design | none |
| `framework-migration-preview` | New content from `015`'s preview skill design | none |
| `framework-migration-execute` | Loop III procedure from `framework_migration_main.md` | `rollback.md` |
| `framework-migration-feedback` | Loop IV procedure from `framework_migration_main.md` | none |

Per FR-003, each `SKILL.md` may include a one-line prose pointer to the natural next stage (e.g. `framework-migration-gap-check/SKILL.md` ending with "If flags were raised above, consider loading the `framework-migration-clarify` bundle next; otherwise proceed to `framework-migration-execute`.") — no other bundle's procedural content is duplicated or referenced.

---

## `compatibility.tools` Per Bundle (FR-005)

Sourced directly from `015`'s `contracts/015-split-migration-harness.md` tool-to-session exposure matrix — copied here as the binding source for each bundle's frontmatter, not re-derived:

| Bundle | `compatibility.tools` |
|---|---|
| `framework-migration-plan` | `analyze_upgrade_path`, `build_recipe_plan`, `resolve_deprecation`, `entity_evolution`, `search_migration_knowledge`, `search_openrewrite_recipes`, `get_graph_schema`, `execute_custom_cypher`, `get_community_insights`, `create_migration_context`, `get_steps_for_scope_tier`, `resolve_paysafe_dependency_by_service_name`, `list_pipeline_runs`, `get_artifact_content`, `install_migration_skill`, `update_queried_entity`, `get_migration_contexts` |
| `framework-migration-gap-check` | `get_graph_schema`, `execute_custom_cypher`, `get_pending_steps`, `get_migration_contexts`, `write_gap_check_flags`, `get_steps_for_scope_tier` |
| `framework-migration-clarify` | `get_graph_schema`, `execute_custom_cypher`, `get_pending_steps`, `update_step_status`, `update_queried_entity`, `get_migration_contexts`, `add_manual_step` |
| `framework-migration-preview` | `get_pending_steps`, `get_migration_contexts` — and nothing else |
| `framework-migration-execute` | `build_recipe_plan`, `resolve_deprecation`, `entity_evolution`, `search_migration_knowledge`, `search_openrewrite_recipes`, `get_graph_schema`, `execute_custom_cypher`, `get_community_insights`, `get_pending_steps`, `update_step_status` |
| `framework-migration-feedback` | `submit_migration_insight`, `get_community_insights`, `vote_insight`, `verify_insight`, `get_graph_schema`, `execute_custom_cypher`, `close_migration_context`, `get_migration_contexts` |

**T022 resolved (2026-06-18):** `get_steps_for_scope_tier` is on gap-check's tool list;
`analyze_upgrade_path` is not. Rationale and citations in
`contracts/015a-skill-bundle-split.md` § T022 Confirmation.

---

## FR-010 Resolution Path (Blocking Sub-Task)

Per `research.md` R3, this remains genuinely unresolved. Before `data-model.md` can specify the stale-layout handling behavior:

1. **Required first step**: read `install_migration_skill`'s actual filesystem-write implementation (not yet available in any artifact reviewed in this thread) to determine current real overwrite/conflict semantics.
2. Once known, choose between (a) detect-and-remove the old `framework-migration/` layout, (b) detect-and-warn, or (c) no special handling — `research.md` recommends (a) or a parameterized variant for consistency with `write_gap_check_flags`'s `overwrite` parameter precedent, but this is a recommendation, not a decision, until step 1 is done.
3. Record the chosen behavior in `data-model.md` with the actual source-code evidence cited, not asserted from precedent alone.

**This plan does not resolve FR-010** — it scopes the investigation as a required Phase 1 step and blocks `data-model.md`'s relevant section until done.

---

## Parallelism Constraints

Writing the six new `SKILL.md` files is safe to parallelize `[P]` — they are independent content extractions from `framework_migration_main.md` plus `015`'s already-written gap-check/clarify/preview design content, with no shared mutable state between them.

The `install.py` bundle-manifest change and the `context.py` Cypher change (FR-011 decision) are not parallel with each other or with the skill-file-writing tasks in the sense of merge conflict risk (different files, no actual conflict) — but the `context.py` change should be sequenced before any task that writes `resume_migration`'s decision-table logic, since that logic depends on the new `has_gap_check_flags`/`excluded` fields existing.

FR-010's investigation task is not parallel with anything — it's a blocking read-only investigation step that gates whatever stale-layout-handling task follows it.

---

## Quickstart Outline (for Phase 1's `quickstart.md`)

1. Run `install_migration_skill()` in full mode against a clean target directory.
2. Confirm six top-level bundle directories exist, each with exactly one `SKILL.md`.
3. Parse each bundle's frontmatter; confirm `compatibility.tools` matches the table above.
4. Confirm `scanning.md`/`version-map.md` exist only under `framework-migration-plan/references/`; `rollback.md` only under `framework-migration-execute/references/`; no `framework-migration-shared` bundle exists anywhere.
5. Call `start_migration`; confirm its prompt text loads `skill://framework-migration-plan/main`.
6. Create a `MigrationContext`, run gap-check against it (producing at least one flag), then call `resume_migration`; confirm its prompt text suggests loading the `clarify` bundle (exercising the FR-011 decision table's middle branch, the one that was previously undetectable before this spec's `get_migration_contexts` extension).
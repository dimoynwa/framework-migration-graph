# Feature Specification: Split Migration Harness Skill Bundles

**Feature Branch**: `015a-skill-bundle-split`

**Created**: 2026-06-18

**Status**: Draft

**Prerequisite**: `015-split-migration-harness` ✅ Complete (implementation done; this spec fixes a packaging defect discovered post-implementation)

**Input**: User description: "After running `install_migration_skill`, the `gap-check`, `clarify`, and `preview` skills all land as `references/` files nested under the single `framework-migration/SKILL.md` bundle, rather than as independently loadable skill bundles. This defeats the session-independence and tool-gating properties `015` was built to establish. Restructure the install output into six independent top-level skill bundles — one per stage (`plan`, `gap-check`, `clarify`, `preview`, `execute`, `feedback`) — mirroring the existing `migration-lite` + `openrewrite-runner` two-bundle precedent already proven by `install_migration_skill`."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Independent Bundle Installation (Priority: P1)

As an agent operator running `install_migration_skill` in full mode, I want each of the six migration stages to install as its own top-level skill bundle, so that loading the skill for one stage never pulls in another stage's instructions, mutation guidance, or unrelated tool references.

**Why this priority**: This is the entire reason the defect matters — without bundle-level separation, every other guarantee from `015` (session independence, tool-gating, preview's read-only safety) is undermined at the documentation layer even if the server-side tool allowlist is correctly enforced.

**Independent Test**: Run `install_migration_skill()` against a clean target directory in full mode; verify six top-level directories are created, each containing exactly one `SKILL.md` and no cross-stage content; verify no `framework-migration/references/{gap-check,clarify,preview}.md` files exist anywhere in the output.

**Acceptance Scenarios**:

1. **Given** a clean skills directory and `MIGRATION_MODE=full`, **When** `install_migration_skill()` is called, **Then** six top-level bundle directories are created: `framework-migration-plan`, `framework-migration-gap-check`, `framework-migration-clarify`, `framework-migration-preview`, `framework-migration-execute`, `framework-migration-feedback`.
2. **Given** the six bundles are installed, **When** an agent reads only `framework-migration-preview/SKILL.md`, **Then** it contains no mutation-tool instructions, no `clarify` exclusion/manual-step guidance, and no `gap-check` audit logic — only preview's rendering instructions.
3. **Given** the six bundles are installed, **When** the install tool's return payload is inspected, **Then** `installed_skills` lists all six bundle names individually, not one `framework-migration` entry.
4. **Given** a prior installation used the old single-bundle layout, **When** `install_migration_skill()` is re-run after this fix ships, **Then** the stale `framework-migration/` directory (old layout) is removed or clearly superseded, not left alongside the new six bundles as orphaned, confusing duplicate content.

---

### User Story 2 - Stage-Scoped Skill Frontmatter (Priority: P1)

As an agent loading a stage's skill bundle, I want that bundle's `SKILL.md` frontmatter to declare only the MCP tools relevant to that stage, so that the skill-level documentation matches the server-side tool-gating allowlist from `015` instead of contradicting it.

**Why this priority**: `015`'s `plan.md` designed a real tool-allowlist enforcement mechanism (`MCP_ACTIVE_STAGE`-based registration filtering). If the skill file an agent reads still says "this skill uses all 23 tools" or omits a `compatibility.tools` list scoped to the stage, the documentation and the enforcement mechanism tell two different stories.

**Independent Test**: Parse each of the six `SKILL.md` frontmatter blocks; verify each `compatibility.tools` list matches that stage's row in the `015` tool-to-session exposure matrix exactly (no extra tools, no missing tools).

**Acceptance Scenarios**:

1. **Given** the `framework-migration-preview` bundle, **When** its frontmatter is parsed, **Then** `compatibility.tools` contains exactly `get_pending_steps` and `get_migration_contexts`.
2. **Given** the `framework-migration-clarify` bundle, **When** its frontmatter is parsed, **Then** `compatibility.tools` contains `add_manual_step`, `update_step_status`, `update_queried_entity`, `get_pending_steps`, and any other tool marked ✅ for `clarify` in the `015` exposure matrix — and no tool marked ❌.
3. **Given** any two bundles' frontmatter, **When** compared, **Then** no bundle's `compatibility.tools` list is a superset of another's in a way that contradicts the `015` matrix (e.g. `preview` must never list a mutation tool that `clarify` also lists, since `preview`'s row is empty for all mutation tools).

---

### User Story 3 - Single-Consumer References Folded Inline (Priority: P2)

As a maintainer of the skill bundles, I want reference files consumed by exactly one stage (`scanning.md`, `version-map.md` for `plan`; `rollback.md` for `execute`) folded directly into that stage's own bundle rather than kept in a separate shared bundle, so that there is no seventh "shared" bundle holding content nothing else actually shares.

**Why this priority**: Avoids inventing unnecessary structure. Lower priority than P1 items because it's an internal organization choice that doesn't affect external bundle-loading behavior, but it prevents a confusing half-shared, half-not structure from shipping.

**Independent Test**: After installation, confirm `scanning.md` and `version-map.md` exist only under `framework-migration-plan/references/`, and `rollback.md` exists only under `framework-migration-execute/references/` — with no separate `framework-migration-shared/` bundle anywhere in the install output.

**Acceptance Scenarios**:

1. **Given** the six bundles are installed, **When** the install output is scanned for any bundle named `framework-migration-shared` or similar, **Then** none exists.
2. **Given** the `framework-migration-plan` bundle, **When** its `references/` directory is listed, **Then** it contains `scanning.md` and `version-map.md`.
3. **Given** the `framework-migration-execute` bundle, **When** its `references/` directory is listed, **Then** it contains `rollback.md`.

---

### User Story 4 - Stage-Aware Prompt Binding (Priority: P1)

As an agent invoked via the `start_migration` or `resume_migration` MCP prompts, I want the prompt text to load the skill bundle matching the stage I'm actually about to run, so that I'm not instructed to load a single monolithic skill resource that no longer matches the six-bundle install layout.

**Why this priority**: `start_migration`/`resume_migration` currently say "Load skill://framework-migration/main" as a fixed instruction. That URI scheme and the one-shot load behavior predate both `015` and this fix; leaving it unchanged would mean the prompts actively contradict the new bundle layout the moment this spec ships.

**Independent Test**: Invoke `start_migration` and confirm its prompt text loads `framework-migration-plan`'s skill resource (or whichever stage is the correct entry point for a new migration); invoke `resume_migration` with a `context_id` and confirm it loads a stage determined by the context's current state, not a hardcoded stage.

**Acceptance Scenarios**:

1. **Given** `start_migration` is invoked with no prior context, **When** its prompt text is rendered, **Then** it instructs the agent to load `skill://framework-migration-plan/main` (or equivalent), not `skill://framework-migration/main`.
2. **Given** `resume_migration` is invoked with a `context_id` whose pending queue is non-empty and whose `gapCheckFlags` property is unset, **When** its prompt text is rendered, **Then** it instructs the agent to load the `gap-check` bundle next, consistent with the natural stage progression `015` defined.
3. **Given** `resume_migration` is invoked with a `context_id` that is already `in_progress` with steps actively being worked, **When** its prompt text is rendered, **Then** it instructs the agent to load the `execute` bundle.

### Edge Cases

- What happens if `install_migration_skill` is called with `target_dir` pointing at a directory that still contains the old single-bundle `framework-migration/` layout from before this fix?
- How does `resume_migration` determine the "correct next stage" to load when a context has gap-check flags present but no `clarify`-stage activity recorded — does it default to suggesting `clarify`, or does it leave the choice to the agent/human?
- What happens if an agent ignores the prompt's stage-specific instruction and manually requests `skill://framework-migration-clarify/main` while actually configured to run in `MCP_ACTIVE_STAGE=preview`? (This is a documentation/instruction-following gap, not a server-enforced one — the tool-gating mechanism, not the skill loader, is the actual enforcement boundary.)
- Does `migration-lite`'s existing reference to `framework-migration`'s `version-map.md` (noted in `MIGRATION_LITE_MODE.md`'s bundle table) need to be re-pointed to `framework-migration-plan`'s copy once the file moves?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `install_migration_skill`, when `MIGRATION_MODE=full`, MUST install exactly six top-level skill bundles: `framework-migration-plan`, `framework-migration-gap-check`, `framework-migration-clarify`, `framework-migration-preview`, `framework-migration-execute`, `framework-migration-feedback`.
- **FR-002**: Each of the six bundles MUST contain exactly one `SKILL.md` file at its top level, scoped to that single stage's procedural instructions only.
- **FR-003**: No bundle's `SKILL.md` or `references/` content MUST describe, instruct, or reference the mutation tools, audit logic, or procedural steps belonging to a different stage, except where a brief one-line pointer to the natural next stage is needed for workflow continuity (e.g. "after gap-check completes, proceed to the clarify bundle if flags were raised").
- **FR-004**: `scanning.md` and `version-map.md` MUST be relocated into `framework-migration-plan/references/`. `rollback.md` MUST be relocated into `framework-migration-execute/references/`. No standalone "shared" bundle MUST be created to hold these files.
- **FR-005**: Each bundle's YAML frontmatter MUST declare a `compatibility.tools` list that exactly matches that stage's row in the `015` tool-to-session exposure matrix (`contracts/015-split-migration-harness.md`) — no tool included that the matrix marks ❌ for that stage, no tool omitted that the matrix marks ✅.
- **FR-006**: `install_migration_skill`'s return payload's `installed_skills` field MUST list all six bundle names individually when run in full mode, replacing the prior single `framework-migration` entry.
- **FR-007**: `mcp-tools-skills-prompts.md`'s bundle-map table (the one documenting `MIGRATION_MODE` → bundles installed → file count) MUST be updated to list the six bundle names under `full`, replacing the single-row `framework-migration` entry, mirroring the existing two-row format already used for `lite` mode's `migration-lite` + `openrewrite-runner` bundles.
- **FR-008**: The `start_migration` prompt MUST be updated to load `skill://framework-migration-plan/main` (or the equivalent stage-specific resource) instead of `skill://framework-migration/main`.
- **FR-009**: The `resume_migration` prompt MUST determine which of the six bundles to instruct the agent to load based on the resumed context's current state (e.g. pending `gapCheckFlags` unreviewed → suggest `gap-check`; steps actively pending with no flags outstanding → suggest `execute`), rather than loading a single fixed skill resource regardless of context state.
- **FR-010**: A migration path or explicit handling MUST exist for environments where the prior single-bundle `framework-migration/` layout is already installed on disk — UNRESOLVED pending research into whether `install_migration_skill` should detect and remove the stale layout, leave it in place with a warning, or require manual cleanup. Do not assume an answer before this is checked against the tool's current overwrite/idempotency behavior.
- **FR-011**: The exact stage-determination logic for `resume_migration` (FR-009) is **partially resolved** by `research.md` R4: `get_migration_contexts`'s confirmed return shape (`outcome_counts` with `completed`/`failed`/`skipped`/`deferred`, no `gapCheckFlags` signal, no `excluded` bucket) is insufficient on its own to distinguish "gap-check ran but clarify/execute haven't started" from "steps were excluded." `plan.md` MUST explicitly choose one of: (a) extend `get_migration_contexts`'s `RETURN` clause to add an `excluded` count and a `gapCheckFlags`-presence signal — a small cross-spec change into `015`'s surface — or (b) accept a coarser decision table that cannot distinguish those two states, documenting the resulting limitation. Do not silently pick (a) or (b) without recording the choice and its consequence in `data-model.md`.

### Key Entities

- **Skill Bundle**: A top-level directory containing one `SKILL.md` and an optional `references/` subdirectory, installed by `install_migration_skill`. Prior to this spec, `full` mode installed one bundle (`framework-migration`) covering all six stages internally; this spec changes that to six independently installed bundles.
- **`compatibility.tools` (frontmatter field)**: An existing YAML frontmatter convention (seen in `migration-lite`'s `SKILL.md`) declaring which MCP tools a skill bundle expects to use. This spec requires it be populated per-bundle to match the `015` exposure matrix, where it may currently be absent or scoped to the old single-bundle structure.
- **Stage-determination state**: Whatever subset of `MigrationContext` properties (`gapCheckFlags`, pending step counts, `STEP_OUTCOME` presence, etc.) is used by `resume_migration` to pick which bundle to suggest loading next — exact shape unresolved per FR-011.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of fresh `install_migration_skill()` calls in full mode produce exactly six top-level bundle directories, zero `references/{gap-check,clarify,preview}.md` files anywhere in the output tree.
- **SC-002**: Every one of the six bundles' `compatibility.tools` frontmatter lists matches its corresponding row in the `015` exposure matrix with zero discrepancies (verified by direct comparison, not sampling).
- **SC-003**: Reading any single bundle's `SKILL.md` in isolation is sufficient to execute that stage correctly — no bundle requires cross-referencing another bundle's `SKILL.md` for its own stage's core procedure (brief "next stage" pointers per FR-003 are exempt from this check).
- **SC-004**: `start_migration` and `resume_migration` prompt text never references the old `skill://framework-migration/main` URI after this ships.

## Assumptions

- The underlying six-stage design from `015` (stage names, tool exposure matrix, stage responsibilities) is correct and unchanged — this spec only fixes how that design is packaged into installable skill bundles, not the stage design itself.
- `install_migration_skill`'s filesystem-write mechanism can be extended to write to multiple named top-level directories in one call without requiring a new tool — it already does this for `lite` mode's two-bundle install.
- The `migration-lite` + `openrewrite-runner` precedent is the correct structural template to follow, since it is the only existing proof that this tool supports multi-bundle installation.
- This spec does not change `015`'s server-side `MCP_ACTIVE_STAGE` tool-gating mechanism — that mechanism is assumed to already be correctly implemented and is out of scope here. This spec only fixes the skill-file/documentation layer to match it.
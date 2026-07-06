# Implementation Plan: Hybrid Plan Rendering

**Branch**: `016-hybrid-plan-rendering` | **Date**: 2026-06-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-hybrid-plan-rendering/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

This feature implements a hybrid migration-plan pipeline rendering strategy by editing prompt/documentation text across four specific `.md` files corresponding to the pipeline stages. The Plan stage will classify each matched rule into one of 5 rendering outcomes and append a plain-text classification suffix to `update_queried_entity`. The Clarify stage will strictly enforce that manual step origins are never rewritten, the Preview stage will mandatorily display the origin, and the Gap-Check stage will rely on its pre-existing stepless-rule check with an added explanatory sentence. No code, schema, or MCP tool contract changes are introduced.

## Technical Context

**Language/Version**: Markdown (Prose/Prompt-Text)

**Primary Dependencies**: None (Documentation only)

**Storage**: Markdown files (No database schema changes)

**Testing**: Manual review of prompt text and verifying against worked example in `hybrid-plan-rendering.md §6`

**Target Platform**: AI Agent Context / Documentation

**Project Type**: Specification / Prompt Engineering

**Performance Goals**: N/A (Documentation change)

**Constraints**: ZERO application code changes. No new node labels, relationship types, or properties in `graph-schema.md`. No MCP tool parameter changes. `update_queried_entity`, `write_gap_check_flags`, `add_manual_step`, and `get_pending_steps` must keep exact current contracts. Severity-bucketing of `stepless_rule` is explicitly deferred as an open question/non-goal for this spec (as determined in the specify phase). No compatibility tool blocks are modified, ensuring stage-gating and MCP restart behavior remains identical.

**Scale/Scope**: 4 markdown files modified (`framework_migration_plan.md`, `framework_migration_gap_check.md`, `framework_migration_clarify.md`, `framework_migration_preview.md`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- All changes are strictly documentation/prompt-text based.
- No new libraries, CLI interfaces, or application code added, satisfying all constraints of the specification.

## Project Structure

### Documentation (this feature)

```text
specs/016-hybrid-plan-rendering/
├── plan.md              # This file (/speckit-plan command output)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

**Note:** No `data-model.md` or `contracts/` files are generated, as specified.

### Source Code (repository root)

```text
migration_oracle/mcp/skills/
├── framework_migration_plan.md
├── framework_migration_gap_check.md
├── framework_migration_clarify.md
└── framework_migration_preview.md
```

**Structure Decision**: Edits will be applied directly to the existing markdown skill files.

## Target File Anchor Points

### 1. `migration_oracle/mcp/skills/framework_migration_plan.md`

**Anchor Point**: Under the `## Loop II — Scope-gated query` section, after the tier table and the `Skip guard` paragraph.

**Current text being anchored against**:
```markdown
**Skip guard:** Check `ctx.queriedEntities[entity_name]` before any tool call. After each successful query, call `update_queried_entity(context_id, entity_name, result_summary)`.
```

**Text to insert**:
```markdown
**Plan Classification:** After each successful query, before calling `update_queried_entity`, classify the matched rule into exactly one of five outcomes based on its `entityClassification`, `steps[]`, `applicability`, and `BRIDGED_BY`:
1. `CONCRETE TASK`: `entityClassification="actionable"` AND ≥1 step with non-empty instructions AND matched exact entity.
2. `CONCRETE TASK (NEEDS-DESIGN-REVIEW)`: Same as #1, but `effort="architectural"` OR instruction is generic.
3. `RELEVANCE-INDEX ENTRY`: `entityClassification="incomplete"`.
4. `RELEVANCE-INDEX ENTRY (uncertain)`: `applicability="uncertain"`.
5. `PLACEHOLDER`: Rule has a `BRIDGED_BY` edge and its step is marked deferred.

If a rule has anomalous or missing required fields, default to `UNCLASSIFIED`.

Append a plain-text suffix identifying this classification (e.g., `... → TASK` or `... → NEEDS-INVESTIGATION`) to the `result_summary` argument of `update_queried_entity`. The classification suffix is strictly a non-gating label; it must NOT filter rules from being cached and must NEVER mutate the `applicability` field. No new parameters may be added to `update_queried_entity`.
```

### 2. `migration_oracle/mcp/skills/framework_migration_gap_check.md`

**Anchor Point**: Under the `### Stepless-rule check (full mode only)` section.

**Current text being anchored against**:
```markdown
### Stepless-rule check (full mode only)

Use `get_steps_for_scope_tier` per scope tier. Flag rules with entity hits but no linked `MigrationStep`.
```

**Text to insert**:
```markdown
*Plan Rendering Note:* This pre-existing check is the actual enforcement mechanism for surfacing `RELEVANCE-INDEX ENTRY` candidates (the `NEEDS-INVESTIGATION` population) to a human. Do not introduce any new checks or modify the `write_gap_check_flags` payload shape.
```

### 3. `migration_oracle/mcp/skills/framework_migration_clarify.md`

**Anchor Point**: Under the `### Add manual steps` section.

**Current text being anchored against**:
```markdown
### Add manual steps

```text
add_manual_step(context_id, summary, instruction, file_pattern?, effort?, severity_hint?)
```

Creates a `MigrationStep` with `origin="manual"` scoped via `OWNS_STEP` to this context only.
```

**Text to insert**:
```markdown

*Origin Preservation Rule:* This operation is the explicit, audited point where a relevance-index entry crosses over into a concrete task. The resulting step's `origin="manual"` must NEVER be retroactively rewritten to `origin="graph"` by any stage, even if community insights later formalize the same fix in the graph. This is a hard, irreversible constraint.
```

### 4. `migration_oracle/mcp/skills/framework_migration_preview.md`

**Anchor Point**: Under the `## Rendering rules` section.

**Current text being anchored against**:
```markdown
Within each group, list: summary, instruction (truncated if long), effort, applicability, origin (`graph` or `manual`).
```

**Note**: The current text already lists origin in the rendering fields; this amendment promotes it from implicit inclusion to an explicitly mandatory, visually distinct field.

**Text to insert**:
```markdown

*Provenance Rendering:* It is **mandatory** to visibly display the `origin` field (`graph` or `manual`) for every rendered step line-item. A manual-origin step must never be visually indistinguishable from a graph-verified one.
```

## Data Model & Contracts

- **Data Model**: No `data-model.md` changes; classification values are a closed five-item enum used only in prose/skill-doc text, not persisted to any store or passed as a typed argument anywhere.
- **Contracts**: No `contracts/` file is required for this spec, since no inter-component delegation rule changes are introduced. No parameters are added to any existing MCP tools.
- **Stage Gating**: The `compatibility.tools` frontmatter in all four edited files remains entirely untouched. MCP_ACTIVE_STAGE gating mechanics and server restart behaviors are completely unaffected by this update.
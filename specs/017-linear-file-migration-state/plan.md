# Implementation Plan: linear-file-migration-state

**Branch**: `017-linear-file-migration-state` | **Date**: 2026-07-07 | **Spec**: [specs/017-linear-file-migration-state/spec.md](spec.md)

**Input**: Feature specification from `specs/017-linear-file-migration-state/spec.md`

## Summary

Moves per-migration progress out of the knowledge graph and into three version-controlled files (`plan.md`, `tasks.md`, `verification.md`) within `ps-migration/{framework}-{from}-to-{to}/`. Refactors the migration harness into a five-stage linear sequence, completely deleting seven session-state MCP tools and their associated schema components, and ensuring strict file-only stages.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastMCP, Neo4j, PyYAML

**Storage**: Local file system (Markdown files) + Neo4j (strictly read-only for migration session state)

**Testing**: pytest

**Target Platform**: CLI / MCP Server

**Project Type**: MCP Server / Agent Skills

**Performance Goals**: N/A

**Constraints**: No context or session-state persisting to graph.

**Scale/Scope**: 7 tools deleted, complete rewrite of workflow.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No constitution violations detected. Simplicity, statelessness, and file-based text I/O align perfectly with best practices.

## Project Structure

### Documentation (this feature)

```text
specs/017-linear-file-migration-state/
├── plan.md              
├── research.md          
├── data-model.md        
├── quickstart.md        
├── contracts/
│   └── stage-boundaries.md
```

### Source Code

```text
src/
├── migration_oracle/mcp/
│   ├── server.py
│   ├── tools/
│   ├── graph/queries/
│   └── skills/
├── docs/
└── tests/mcp/
```

**Structure Decision**: Refactoring existing modules by deleting the tools, updating skills, and rewriting documentation files.

## File-by-File Change List

### Files to Delete

- `migration_oracle/mcp/tools/context.py`: Delete the module completely. No re-export shim allowed.
- `migration_oracle/mcp/graph/queries/context.py`: Delete completely.
- `migration_oracle/mcp/skills/framework_migration_feedback.md`: Delete completely.
- `tests/mcp/test_context.py`: Delete.
- `tests/mcp/test_context_fixes.py`: Delete.
- `tests/mcp/test_step_outcome_e2e.py`: Delete.
- `tests/mcp/test_step_outcome_errors.py`: Delete.
- `tests/mcp/test_step_outcome_idempotency.py`: Delete.
- `tests/mcp/test_update_queried_entity_errors.py`: Delete.
- `tests/mcp/test_update_step_status.py`: Delete.
- `tests/mcp/test_close_migration_context.py`: Delete.
- `tests/mcp/test_get_migration_contexts.py`: Delete.
- `tests/mcp/test_get_steps_for_scope_tier.py`: Delete.

### Files to Add

- `INSTRUCTION.md`: At repo root. Top-level operator guide detailing:
  - Folder contents and files.
  - Stage sequence (`plan` -> `gap-check` -> `clarify` -> `preview` -> `execute`, with `clarify` and `preview` optional).
  - Resumption process (no session state).
  - Verification gating + `needs-review` sign-off rule.
  - Paysafe dependency constraints.
  - User-initiated insight submission.
- `migration_oracle/mcp/skills/templates/plan.md`: The canonical template text for `plan.md` to be emitted by the skills. Transcribed from the worked examples in design document §1-3.
- `migration_oracle/mcp/skills/templates/tasks.md`: The canonical template text for `tasks.md` to be emitted by the skills. Transcribed from the worked examples in design document §1-3.
- `migration_oracle/mcp/skills/templates/verification.md`: The canonical template text for `verification.md` to be emitted by the skills. Transcribed from the worked examples in design document §1-3.

### Files to Edit

- **`migration_oracle/mcp/server.py`**:
  *Anchor*: Registration of tools such as `def create_migration_context(...)` and `def get_migration_contexts(...)`
  *Edit*: Remove `create_migration_context`, `get_migration_contexts`, `get_pending_steps`, `update_step_status`, `close_migration_context`, `update_queried_entity`, `get_steps_for_scope_tier` strictly matching their `def <name>` registrations.

- **`migration_oracle/pipeline/populator.py`**:
  *Anchor*: `MigrationContext` and `STEP_OUTCOME` references inside functions responsible for Neo4j generation.
  *Edit*: Remove any context-subgraph writes. (Verify this path exists; if it doesn't, search for `MigrationContext` writes in the `graph/` directory).

- **`docs/graph-schema.md`**:
  *Anchor*: `### MigrationContext` and `(MigrationContext)──STEP_OUTCOME───►(MigrationStep)`
  *Edit*: Name the sections dropped: `MigrationContext` node, `STEP_OUTCOME` relationship, queried-entity cache. Confirm `BRIDGED_BY` and `community-insight` rules are retained.

- **`migration_oracle/mcp/skills/framework_migration_main.md`**:
  *Anchor*: `## Loop I — Context (plan stage)` (and all `Loop II`, `Loop III`, `Loop IV` headers)
  *Edit*: Rewrite to replace the loop nomenclature with the strict five-stage linear sequence (`plan`, `gap-check`, `clarify`, `preview`, `execute`), ensuring the terminology and constraints align perfectly with the updated file-state design.

- **`migration_oracle/mcp/skills/framework_migration_plan.md`**:
  *Anchor*: References to `skill://framework-migration-plan/main` or loop executions.
  *Edit*: Rewrite to assert that the `plan` stage must run AFTER the full escalation chain (`analyze_upgrade_path` -> `resolve_deprecation` -> `entity_evolution` -> `search_migration_knowledge`), completely read/write the `ps-migration/` files, point to `templates/` for the canonical schemas, and confirm no graph writes or parameters were modified.

- **`migration_oracle/mcp/skills/framework_migration_gap_check.md`**:
  *Anchor*: References to `skill://framework-migration-gap-check/main` and its instructions block.
  *Edit*: Rewrite to assert reading only `plan.md` and `tasks.md` (no graph reads) and performing inline gap annotation to both `tasks.md` and `plan.md`.

- **`migration_oracle/mcp/skills/framework_migration_clarify.md`**:
  *Anchor*: References to `skill://framework-migration-clarify/main` and its instruction blocks.
  *Edit*: Update logic to read/write `tasks.md` to promote Relevance-Index to manual tasks or dismiss with reasons.

- **`migration_oracle/mcp/skills/framework_migration_preview.md`**:
  *Anchor*: References to `skill://framework-migration-preview/main` and its instructions.
  *Edit*: Read-only rendering of grouping by risk/scope.

- **`migration_oracle/mcp/skills/framework_migration_execute.md`**:
  *Anchor*: Mentions of iterating over `get_pending_steps` or equivalent.
  *Edit*: Rewrite to assert sequential progression (TASK-001..NNN), directly modifying the `tasks.md` file status (pending/done/failed/needs-review). On build failure, rollback and mark failed (but fix-forward without halting the loop). Ensure `verification.md` commands are finalized at the very end.

- **`migration_oracle/mcp/skills/framework_migration_plan_format.md`**:
  *Anchor*: Any structure dictating the framework migration output.
  *Edit*: Evolve into, or replace with, documentation for the `plan.md`, `tasks.md`, and `verification.md` file schemas.

- **`docs/mcp-tools-skills-prompts.md`**:
  *Anchor*: `The core four-loop migration harness. Defines the procedural workflow...` (and the table containing Loops I-IV) and `Call get_pending_steps(context_id='{context_id}') to see what remains.`
  *Edit*: Rewrite to assert the five-stage linear sequence (`plan`, `gap-check`, `clarify`, `preview`, `execute`), remove any mention of Loops I-IV or `create_migration_context`, and clean up any stateless fallback references related to session state tools. Remove the 7 tool entries completely (noting exact names), reconcile the tool counts as a discrete step (resolving against actual active tool count without asserting a hardcoded total), and update skill-resource list.

- **`docs/SPEC_ORGANIZATION.md`**:
  *Anchor*: `├── 04_context_dashboard.py # MigrationContext status...` and `├── context.py             # create_migration_context...`
  *Edit*: Modify the `004` capability section (the context tools) by dropping the session-state tools and explicitly naming the removed items (`context.py` block). Mark the downstream UI section (`04_context_dashboard.py`) with a note acknowledging it requires re-scoping. Validate alignment with the canonical registration location. (This is a hard prerequisite task).

- **`.cursor/rules/specify-rules.mdc`** (or equivalent agent instructions doc, check `CLAUDE.md` and `.cursorrules` as needed):
  *Anchor*: Any text referencing a "four-loop" process. (e.g., `- Loop I: scan the codebase`, `- Loop II: query the graph`, etc.)
  *Edit*: Rewrite the four-loop harness section to strictly dictate the five-stage file sequence. Also verify no other file duplicates canonical schemas.

### Tool Boundaries
- Ensure that ZERO knowledge-read tools (`analyze_upgrade_path`, `build_recipe_plan`, etc.) have their signatures altered or parameters added (e.g., adding `scope_tier`) to absorb the deleted `get_steps_for_scope_tier`'s functionality.

### Template Canonical Linking
- The canonical `plan.md`, `tasks.md`, and `verification.md` file schemas must exist as markdown templates in `migration_oracle/mcp/skills/templates/`. The stage skill prose must reference the template by path (e.g., "emit `plan.md` following the schema at `templates/plan.md`") rather than inlining a copy of the template text within the skill prose itself.

### Test Validation
- Ensure to `grep` for imports of `context.py` and `MigrationContext` across the `tests/` directory to safely catch and delete any unlisted test files or fixtures that depend on the deleted modules.

### Scope and External Impacts
- **Note**: The `005-streamlit-ui` UI feature (`04_context_dashboard.py`) depends on the deleted `MigrationContext` graph nodes. It must be marked as downstream-affected and re-scoped outside this execution.

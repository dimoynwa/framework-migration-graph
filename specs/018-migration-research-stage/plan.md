# Implementation Plan: Migration Research Stage

**Branch**: `018-migration-research-stage` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-migration-research-stage/spec.md`

## Summary

Adds an optional `/migration-research` stage to the migration harness to persist knowledge-query results as a structured markdown artifact (`research.md`). Amends `/migration-plan` to detect and consume this artifact (skipping redundant queries), updates `/migration-gap-check` to verify provenance, and updates `/migration-preview` to display the knowledge source. Ensures strict default-path equivalence when research is not run.

## Technical Context

**Language/Version**: Markdown (Prompt/Skill documentation)
**Primary Dependencies**: None (MCP tools are unaffected)
**Storage**: Local File System (`ps-migration/`)
**Testing**: Manual validation of artifact schema, diff comparison for equivalence
**Target Platform**: Cursor IDE / Migration Oracle MCP
**Project Type**: Agent Skills Documentation
**Performance Goals**: Eliminate redundant graph query latency on re-plan
**Constraints**: No Python code changes, no MCP tool changes, preserve exact inline query behavior
**Scale/Scope**: 1 new stage document, 3 amended stage documents, 2 amended system docs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

N/A - The project constitution relies on generic templates in `.specify/memory/constitution.md`. The design complies strictly with all constraints established in the specification, primarily preserving the "no python code change" and "identical fallback" rules.

## Project Structure

### Documentation (this feature)

```text
specs/018-migration-research-stage/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── stage-boundaries.md
└── tasks.md             # Phase 2 output (to be generated)
```

### Source Code (repository root)

```text
migration_oracle/mcp/skills/framework-migration/
├── research.md                      # NEW: The research stage skill definition
├── plan.md                          # AMEND: Add Step 1.5 detection logic, update Step 2, update header
├── gap-check.md                     # AMEND: Add provenance check, truncation consistency check
└── preview.md                       # AMEND: Add knowledge source line in summary

docs/
└── migration-file-state-design.md   # AMEND: Update file inventory and stage summary

INSTRUCTION.md                       # AMEND: Update stage table, pipeline diagram, bundle list
```

**Structure Decision**: The implementation focuses purely on markdown skill documents and system instruction updates. No python files, tests, or MCP tool files are altered. The structure strictly avoids files in `migration_oracle/` (except `.md` skills) and `tests/`.

### Execution Plan (Amendment Insertions)

**1. `migration_oracle/mcp/skills/framework-migration/plan.md`**
*(Note for `/speckit-tasks` generation: The execution order for these three amendments MUST be (1) Step 2 checksum definition, (2) Step 1.5 detection logic, and (3) Header template fields. This ensures the checksum logic is defined before Step 1.5 references it.)*

- **Anchor Before**: `## Step 1 — Folder discovery\n\n...`
- **Anchor After**: `## Step 2 — Codebase scan`
- **Amendment**: Insert `## Step 1.5 — Detection` and explicit skipping logic BEFORE the Step 2 heading in the document structure. However, explicitly state in prose under Step 1.5 that its logic evaluates AFTER Step 2 completes, to utilize the scan checksum.
- **Anchor Before**: `## Step 2 — Codebase scan\n\nRun scan using...`
- **Anchor After**: `These scan results are passed as...`
- **Amendment**: Update Step 2 text to define the explicit SHA-256 checksum algorithm (sorted, deduplicated, newline-joined across all 5 types).
- **Anchor Before**: `From to To:     {FROM} to {TO}\nGraph snapshot:`
- **Anchor After**: `Graph snapshot: {knowledge-version id at generation time}`
- **Amendment**: Append `Research:` and `Research-generated:` fields to the output template. Take care not to disturb the `# meta:` line above it.

**2. `migration_oracle/mcp/skills/framework-migration/gap-check.md`**
- **Anchor Before**: `### Truncation\n\n- Check plan.md for a truncation marker...`
- **Anchor After**: `...with a higher \`top_n\`." Severity: **HIGH**.`
- **Amendment**: Add the truncation consistency check (comparing research.md to plan.md) as a bullet within the existing `### Truncation` section.
- **Anchor Before**: `### Version sanity`
- **Anchor After**: `...the Preconditions section. Severity: **LOW**.`
- **Amendment**: Insert a new `### Provenance integrity` section containing the staleness check (`Research-generated` age against `Generated`) and verifying `research.md` existence without parsing inner rules.

**3. `migration_oracle/mcp/skills/framework-migration/preview.md`**
- **Anchor Before**: `- Relevance-Index entries: resolved (promoted or dismissed) vs. unresolved`
- **Anchor After**: `## Risk-group rendering`
- **Amendment**: Append `- Knowledge source: (e.g. inline queries, or research.md from <date>)` as the final bullet in the Summary Counts section.

**4. `docs/migration-file-state-design.md`**
- **Anchor Before**: `migration/{fw}-{from}-to-{to}/`
- **Anchor After**: `plan.md          strategy + rule ledger + provenance`
- **Amendment**: Insert `research.md      checkpointed query knowledge (optional)` to the file inventory.

**5. `INSTRUCTION.md`**
- **Anchor Before**: `| **plan** | \`/migration-plan\``
- **Anchor After**: `...` (Stage sequence table)
- **Amendment**: Prepend `| **research** | \`/migration-research\`` to the stage table.
- **Anchor Before**: `| `install_migration_skill` | Installs the 5 core framework-migration skill files:`
- **Anchor After**: `...`
- **Amendment**: Add `research.md` to the explicit bundle list.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |

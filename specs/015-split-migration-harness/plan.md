# Implementation Plan: Split Migration Harness

**Branch**: `015-split-migration-harness` | **Date**: 2026-06-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015-split-migration-harness/spec.md`

## Summary

Splits the existing four-loop migration harness across independent agent sessions at the loop boundaries, and inserts two new stages — gap-check (mechanical plan audit) and preview (read-only customer-facing rendering) — plus makes the existing ad-hoc human-amendment need into a named, optional clarify stage. The system exposes six session-scoped entry points: plan, gap-check, clarify, preview, execute, feedback. Each later stage resumes purely from MigrationContext graph state, never from conversation memory of an earlier stage's session.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: MCP SDK, Neo4j driver

**Storage**: Neo4j Graph Database

**Testing**: pytest

**Target Platform**: CLI / Cursor Agent

**Project Type**: MCP Server

**Performance Goals**: Eliminate context bloat in `execute` sessions

**Constraints**: Strict read-only enforcement for `preview` stage

**Scale/Scope**: 6 distinct session entry points, 2 new tools, 3 new skill files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Library-First**: N/A (MCP server extension)
- **CLI Interface**: N/A
- **Test-First**: Yes, new tools and Cypher queries will be tested before integration.
- **Simplicity**: The session/tool-gating mechanism is designed as a simple allowlist rather than complex RBAC.

## Project Structure

### Documentation (this feature)

```text
specs/015-split-migration-harness/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── 015-split-migration-harness.md
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
migration_oracle/
└── mcp/
    ├── server.py                  # Session/tool-gating mechanism implementation
    ├── tools/
    │   └── context.py             # add_manual_step, excluded outcome support, write_gap_check_flags
    ├── skills/
    │   ├── gap_check.md           # New skill (implemented as a single handler with an early-branch on ctx.mode for which checks to skip)
    │   ├── clarify.md             # New skill
    │   ├── preview.md             # New skill
    │   └── framework_migration_main.md # Split/annotated to reflect the 6 stages
    └── graph/
        └── queries/
            └── context.py         # New Cypher for manual-step scoping (OWNS_STEP) and gap-check flag persistence
```

**Structure Decision**: The implementation touches the MCP server layer, specifically the context tools, the graph queries for context management, and the markdown skill files that guide the agent.

## Session/Tool-Gating Mechanism Design

To satisfy the `preview` stage's zero-mutation requirement, we will implement a minimal per-command tool allowlist enforced at MCP server registration time.

1. **Session Initialization**: When the MCP server is started or a session is initialized, an environment variable (e.g., `MCP_ACTIVE_STAGE`) or an initialization parameter will specify the active stage (`plan`, `gap-check`, `clarify`, `preview`, `execute`, `feedback`).
2. **Tool Registration**: The `server.py` will read this active stage and filter the list of tools to register against a hardcoded allowlist matrix (defined in `contracts/015-split-migration-harness.md`). This enforcement happens at tool registration time: tools not in the allowlist for the active stage are simply not decorated with `@mcp.tool()`.
3. **Enforcement**: Because the tools are simply not registered with the MCP SDK for that session, the LLM cannot invoke them. This provides a robust, zero-mutation guarantee for `preview` (and other stages), as the tools literally do not exist in the MCP server's tool table for that session.

## Parallelism Constraints

**CRITICAL (Runtime Session Concurrency)**: `gap-check`, `clarify`, and `preview` reads are **NOT safe to parallelize** with a concurrently running `execute` session against the same `context_id`. Shared graph writes from `execute` (e.g., updating step outcomes) could race with `clarify`'s exclusion writes or cause `gap-check`/`preview` to read inconsistent state. There must be no `[P]` marking across these boundaries for the same `context_id` during actual migration execution.

**Safe Parallelism for `tasks.md` (Task Authoring/Implementation)**:
*Clarification: The runtime session-concurrency warning above applies to the end-user executing the migration; it does NOT apply to the coding agent authoring the implementation tasks. The tasks below describe agent implementation work and are safe to parallelize.*
The following implementation tasks are safe to mark `[P]` (parallelizable) during task generation:
- Writing the three new skill markdown files (`gap_check.md`, `clarify.md`, `preview.md`)
- Writing the Cypher query deltas in `migration_oracle/mcp/graph/queries/context.py`
- Implementing the `add_manual_step` tool logic
- Implementing the `write_gap_check_flags` tool logic
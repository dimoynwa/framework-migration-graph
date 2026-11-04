# Interface Contracts: linear-file-migration-state

This document specifies the read/write boundaries and contract handoffs for the five-stage linear migration workflow.

## Component Contract: Read/Write Boundary per Stage

1. **`plan` Stage**
   - **Graph Boundary**: Knowledge-read only.
   - **File Boundary**: Writes `plan.md`, `tasks.md`, and the skeleton of `verification.md`.
   - **Handoff Preconditions**: To ensure `gap-check` functions, `plan` MUST output fully populated `classification` and `applicability` columns in the Rule Ledger. Every generated TASK block MUST include all fields from `data-model.md`, including `Verify`, even if empty.

2. **`gap-check` Stage**
   - **Graph Boundary**: FILE-ONLY. Never touches the graph.
   - **File Boundary**: Reads `plan.md` and `tasks.md`. Writes inline annotations to `tasks.md` and `plan.md` (flagging missing verifiers in tasks and unclassified rules in the ledger) for mechanical gaps.

3. **`clarify` Stage**
   - **Graph Boundary**: FILE-ONLY. Never touches the graph.
   - **File Boundary**: Reads and writes `tasks.md` (promotes Relevance-Index entries or dismisses them with reason).

4. **`preview` Stage**
   - **Graph Boundary**: FILE-ONLY. Never touches the graph.
   - **File Boundary**: Reads `plan.md` and `tasks.md`. Writes nothing (rendering only).

5. **`execute` Stage**
   - **Graph Boundary**: Knowledge-read only when stuck (search-before-skip). Never writes state to the graph.
   - **File Boundary**: Reads and writes `tasks.md` (updates task `Status`). Reads and finalizes `verification.md`.

## Data Lifecycle Contracts

### Origin=manual One-Way Constraint
When the `clarify` stage promotes a Relevance-Index entry into a real `TASK` in `tasks.md`, it assigns `Origin=manual`. This promotion is one-way. It MUST NOT be rewritten, pushed, or synchronized back to the knowledge graph as state.

### Insight Submission Trigger
The tool `submit_migration_insight` MUST strictly remain **user-initiated**. No stage in the workflow (especially the tail of `execute`) may auto-call this tool or prompt an automated insight submission.

### `verification.md` Handoff
- **Skeleton Emission**: The `plan` stage is strictly responsible for emitting the skeleton of `verification.md` (Levels 0-5) derived from the Rule Ledger and per-task verifiers. It uses exact placeholder tokens: `{build command}`, `{unit test command}`, `{integration test command}`, and `{run command}`.
- **Finalization**: The `execute` stage takes the generated skeleton and finalizes it by strictly replacing the placeholder tokens (`{build command}`, etc.) with the discovered commands specific to the repository. It MUST NOT rewrite content outside these placeholder slots or regenerate the file.

### Drift Rule (Source of Truth)
When `execute` (or a re-run of `plan`) queries the graph and detects a change in rule knowledge since the snapshot:
- **Files** remain the sole source of truth for migration **intent and progress**.
- **Graph** remains the sole source of truth for **knowledge**.
- Divergences MUST be surfaced as drift notes within `tasks.md`, and MUST NOT trigger silent re-planning or state rewrites.

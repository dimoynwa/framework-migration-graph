---
name: framework-migration-preview
description: >
  Preview stage — read-only customer-facing plan rendering grouped by risk.
  Reads plan.md and tasks.md only; writes nothing.
compatibility:
  tools:
    - install_migration_skill
---

# Preview Stage — Read-Only Plan Rendering

Invoked via `/migration-preview`. File-only, read-only stage. **Zero mutation** — no file
writes, no graph access.

This is the customer-facing approval gate. It renders the post-clarify (or post-gap-check)
migration plan for human review before execution begins. Preview reads the amended plan so
the customer sees the final version, not the pre-clarify one.

## Entry

1. Locate `ps-migration/{framework}-{from}-to-{to}/`.
2. Verify `plan.md` and `tasks.md` exist. If missing, stop — run `/migration-plan` first.
3. Read both files.

## Summary counts

Open the preview with a summary block:

- Total task count
- Breakdown by risk group: HIGH / MEDIUM / LOW
- Count of NEEDS-DESIGN-REVIEW tasks (subset of the risk groups)
- Relevance-Index entries: resolved (promoted or dismissed) vs. unresolved
- Knowledge source: inline queries, or research.md from `<date>` (read `Research:` and `Research-generated:` from plan.md header)

## Risk-group rendering

Group tasks by severity, not by matching header text:

| Risk label | Task severity values |
|---|---|
| **HIGH** | `critical`, `high` |
| **MEDIUM** | `medium` |
| **LOW** | `low`, tasks without explicit severity (including manual-origin tasks with no graph severity) |

Within each group, render each task with these fields:

- Task ID (TASK-001, TASK-002, ...)
- Summary (from Instructions, truncated if long)
- Effort
- Applicability (`matched`, `uncertain`, `universal`)
- Origin (`graph` or `manual`) — **mandatory for every task, no exceptions**
- Render (TASK or TASK NEEDS-DESIGN-REVIEW)
- Executor
- Status

### Origin display rules

The `Origin` field (`graph` or `manual`) must be shown for every single task in the
rendered output, with no exceptions — including low-risk or manual-without-severity tasks
in the LOW group. Do not collapse or omit this field for any risk group.

Manual-origin tasks are tagged with a `[manual]` prefix before the task summary to
distinguish them visually from graph-verified tasks. This is the reader's sole signal for
how much confidence to place in a given task.

## Gap-check caveats

If tasks.md or plan.md contain `**Gap-check` annotations or `<!-- gap-check:` comments,
render a **Caveats** section before the risk-grouped plan body. Include the full text of
each annotation.

Caveats should not be hidden or summarized — the customer needs to see exactly what
gap-check flagged (e.g. "3 rules included via the high/critical safety net without a
confirmed match in your codebase").

If no gap annotations exist, note: "No gap-check findings recorded."

## Relevance Index summary

After the risk-grouped tasks, render the Relevance Index:

**If `/migration-clarify` ran:** show resolved RI entries with their disposition —
promoted entries reference their new TASK ID; dismissed entries show the documented reason.

**If `/migration-clarify` did not run:** show unresolved RI entries with ID, RuleID,
Description, and Applicability. Note: "These entries have not been triaged. Run
`/migration-clarify` to promote or dismiss them before execution."

## Constraints

- Do **not** write to any file — this stage is strictly read-only.
- Do **not** call graph query tools — they are not available in this stage.
- Do **not** modify the codebase.

## Next step

After rendering, prompt the operator:

- **Approved** → proceed to `/migration-execute`.
- **Changes needed** → go back to `/migration-clarify` to amend the plan, then re-run
  `/migration-preview`.
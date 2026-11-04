---
name: framework-migration-clarify
description: >
  Clarify stage — resolve Relevance-Index entries in tasks.md.
  Promotes to manual tasks or dismisses with reason. File-only.
compatibility:
  tools:
    - install_migration_skill
---

# Clarify Stage — Relevance-Index Resolution

Invoked via `/migration-clarify`. File-only stage. Reads and writes `tasks.md`.
**Never** touches the graph.

This stage is triggered when gap-check or preview surfaces unresolved Relevance-Index
entries. It is the one explicit, audited point where a relevance-index entry crosses over
into a concrete task.

## Entry

1. Locate `ps-migration/{framework}-{from}-to-{to}/`.
2. Verify `tasks.md` exists. If missing, stop — run `/migration-plan` first.
3. Read `tasks.md` — find the Relevance Index section.
4. If no RI entries exist, report "nothing to clarify" and suggest proceeding to
   `/migration-preview` or `/migration-execute`.

## RI entry types

The plan stage produces two kinds of RI entries. Present them to the operator in this
priority order (direct matches first — they are more likely to need promotion):

| Type | Source condition | Typical clarify action |
|---|---|---|
| **RELEVANCE-INDEX (direct)** | `entityClassification="incomplete"` — entity definitely exists in codebase, graph has no prescribed fix | Promotion likely — operator usually knows the fix |
| **RELEVANCE-INDEX (uncertain)** | `applicability="uncertain"` — safety-net match, entity may not apply | First question: does this actually affect the codebase? Dismissal with "not applicable" is common |

## Gap-check annotations

If gap-check ran before clarify (the normal flow), tasks.md may contain `**Gap-check**:`
annotations on RI entries. Review these alongside each entry — they explain why clarify
was triggered. After promoting or dismissing an entry, **keep the annotation** as an audit
trail. Do not delete it.

## Allowed mutations

### Promote to TASK

Convert an RI entry into a full TASK block with `Origin: manual`. This is **one-way** —
once created as `manual`, never rewrite to `graph`, even if a community insight later
formalizes the same fix in the graph.

**TASK numbering:** assign the next sequential TASK-NNN ID after the highest existing one
in tasks.md.

**Insertion point:** append the new TASK block at the end of the Tasks section, immediately
before the Relevance Index section header. The execute stage processes tasks in order, and
newly promoted tasks naturally come after graph-derived ones.

**Field guidance for promoted tasks:**

| Field | Value | Source |
|---|---|---|
| Status | `pending` | Always |
| Derives-from | The RI entry's RuleID (e.g. `MR-5107`) | From the RI entry itself |
| Origin | `manual` | Always — never `graph` |
| Applicability | Carry forward from the RI entry (`direct` or `uncertain`) | From the RI entry |
| Executor | Default to `human-review` unless the operator provides a concrete instruction + entity anchor (which qualifies for `agent-codemod` per the execute decision table) | Operator-assessed |
| Recipe | `none` | RI entries have no graph-prescribed steps, so no linked recipe |
| Effort | Prompt the operator: `mechanical`, `moderate`, or `architectural` | Operator-assessed |
| File pattern | Prompt the operator for the affected file glob | Operator-provided |
| Instructions | Prompt the operator for the concrete fix | Operator-provided |
| Before/After | Prompt the operator (may be empty if the fix is not a simple transformation) | Operator-provided |
| Verify | Prompt the operator for a one-liner verification check (may be empty) | Operator-provided |

Mark the RI entry as promoted:

```
Disposition: promoted → TASK-NNN
```

### Dismiss with reason

Mark the RI entry as not applicable or not actionable:

```
Disposition: dismissed — {reason}
```

The reason must be specific: "not applicable — entity not found in codebase" or
"deferred — low severity, will address in a future migration." Do not dismiss without a
documented reason.

### Leave for later

The operator may choose not to act on an entry now. It stays in the Relevance Index
section with no Disposition line. **Consequence:** unresolved RI entries will block the
Level 5-C completion gate during terminal verification. Make this explicit to the operator.

## Header count updates

After each promote or dismiss action, update the header counts at the top of tasks.md:

- **Promote:** Relevance-index count decreases by 1. The risk count (HIGH/MEDIUM/LOW)
  for the promoted task's severity increases by 1.
- **Dismiss:** Relevance-index count decreases by 1. Risk counts do not change.
- **Leave for later:** No count changes.

## Workflow

1. Present all RI entries to the operator, grouped by type (direct first, uncertain second).
2. For each entry: show the RuleID, description, applicability, and any gap-check annotation.
3. Ask the operator: promote to TASK, dismiss with reason, or leave for later.
4. For promotions: prompt for the required fields (see table above).
5. Write the changes to tasks.md — new TASK blocks, disposition lines, updated header counts.
6. Summarize: N promoted, N dismissed, N left unresolved.
7. Hand off to `/migration-preview` (recommended) or `/migration-execute`.

## Constraints

- Do **not** call graph query tools — they are not available in this stage.
- Do **not** modify `plan.md` — it is a read-only reference for provenance.
- Do **not** change `Status` on existing TASK blocks — that is the execute stage's job.
- Do **not** add new Relevance-Index entries — new entries come from `/migration-plan`
  (graph queries) or `/migration-gap-check` (cross-file consistency checks).
- Do **not** modify `verification.md` — that is finalized by execute.
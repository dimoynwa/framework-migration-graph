---
name: framework-migration-gap-check
description: >
  Gap-check stage — mechanical file-only audit of plan.md and tasks.md.
  Annotates gaps inline; never touches the graph.
compatibility:
  tools:
    - install_migration_skill
---

# Gap-Check Stage — Mechanical Plan Audit

Invoked via `/migration-gap-check`. File-only stage. Reads and annotates `plan.md` and
`tasks.md`. **Never** touches the graph.

After gap-check completes, proceed to `/migration-clarify` (if Relevance-Index entries
exist or gaps require human judgment) or `/migration-preview` / `/migration-execute`.

## Entry

1. Locate `ps-migration/{framework}-{from}-to-{to}/`.
2. Verify all three files exist (`plan.md`, `tasks.md`, `verification.md`). If any are
   missing, stop — the plan stage did not complete. Re-run `/migration-plan`.
3. Read `plan.md` and `tasks.md`.

## Checks

Run every check. Flag each finding with a severity (`HIGH` or `LOW`).

### Cross-file consistency (stepless-rule equivalent)

Compare plan.md's Rule Ledger against tasks.md:

- Every Rule Ledger row with `Render=TASK` or `Render=TASK (NEEDS-DESIGN-REVIEW)` must
  have a corresponding TASK block in tasks.md (`Derives-from` references the rule ID).
- Every Rule Ledger row with `Render=RELEVANCE-INDEX` or `Render=RELEVANCE-INDEX (uncertain)`
  must have a corresponding entry in tasks.md's Relevance Index section.
- Flag any rule present in the ledger but missing from tasks.md — this is the file-state
  equivalent of the old `stepless_rule` flag. Severity: **HIGH**.

### Required TASK fields

Every TASK block in tasks.md must include all of: Status, Derives-from, Origin, Executor,
Recipe (may be `none`), Effort, File pattern, Instructions, Before/After (may be empty),
Verify (may be empty).

- Flag TASK blocks missing any required field. Severity: **HIGH** for missing Origin,
  Executor, or Instructions; **LOW** for missing Before/After or empty Verify.

### Origin and applicability

- Every TASK block must have `Origin: graph` or `Origin: manual`. Flag if missing.
  Severity: **HIGH**.
- Every TASK block must show applicability (`matched`, `uncertain`, `universal`). Flag if
  missing. Severity: **LOW**.
- For `Origin: graph` TASK blocks, `Applicability` must be `matched` and the task must
  show at least one current project entity anchor (`Matched entities`, `EntityMatched`, or
  equivalent). If it has `informational`, `uncertain`, `universal`, `_none_`, or an empty
  anchor, flag it: "graph task lacks project-specific evidence; move to Relevance Index or
  clarify into a manual task." Severity: **HIGH**.
- For graph TASK blocks that describe a specific legacy method, annotation, property, or
  dependency, verify the old symbol is named in the task evidence. If the task only cites a
  framework-generic anchor such as `SpringBootApplication`, flag it: "task has generic
  framework anchor only." Severity: **HIGH**.

### Rule Ledger completeness

- Flag Rule Ledger rows missing `classification` or `applicability` columns.
  Severity: **HIGH**.

### Truncation

- Check plan.md for a truncation marker (a note that rule count equaled `top_n` during
  plan Step 4). If present, flag: "Plan may have truncated results; consider re-running
  `/migration-plan` with a higher `top_n`." Severity: **HIGH**.
- When `plan.md` declares a research source (`Research:` is not `inline`), read the
  referenced `research.md` header only and compare its `Truncated` flag to plan.md's
  truncation marker. If they disagree (one indicates truncation, the other does not),
  flag: "Truncation flag inconsistent between research.md and plan.md." Severity: **HIGH**.

### Version sanity

- Verify From/To versions in plan.md header are consistent with preconditions listed in
  the Preconditions section. Severity: **LOW**.

### Provenance integrity

When `plan.md` header declares a research source (`Research:` is not `inline`):

- Verify the referenced `research.md` file still exists at the declared path. If missing,
  flag: "Referenced research.md no longer exists." Severity: **HIGH**.
- Read header metadata only from `research.md` (Framework, From, To, Generated,
  Scan checksum, Entity count, Rule count, Truncated). Forbid parsing below the header —
  do not parse Rule Results, Dependency Resolutions, or Recipe Plan sections.
- If `Research-generated:` is more than 7 days older than plan.md's `Generated` timestamp,
  flag: "Research artifact is stale (>7 days older than plan)." Severity: **LOW**.

### Paysafe unresolved

- Check plan.md's Dependency Updates table for `com.paysafe` dependencies without a
  resolved target version. Flag each one. Severity: **HIGH**.

### Bridge-context

- Any TASK whose instructions mention a `BRIDGED_BY` relationship should have
  `Executor: human-review`. Flag if a different executor is assigned. Severity: **HIGH**.

### Empty verifiers

- Flag TASK blocks where the Verify field is empty AND the task is HIGH or MEDIUM effort.
  Severity: **LOW**.

## Annotation format

Add inline gap notes directly in the files:

In **tasks.md**, append below flagged TASK blocks:

```
**Gap-check [HIGH]**: {description of mechanical gap}
```

In **plan.md**, append below flagged Rule Ledger rows:

```
<!-- gap-check [HIGH]: {description} -->
```

## Constraints

- Do **not** call graph query tools — they are not available in this stage.
- Do **not** modify the codebase.
- Do **not** change task Status values.
- Do **not** add or remove TASK blocks — that is the clarify stage's job.

## Output

Present the gap list to the operator, grouped by severity (HIGH first).

- If **Relevance-Index entries exist** in tasks.md: suggest `/migration-clarify` to
  promote or dismiss them before execution.
- If **HIGH-severity gaps** were found: recommend addressing them before proceeding.
  The operator may re-run `/migration-plan` (for truncation or missing rules) or proceed
  to `/migration-clarify` (for missing fields that need human input).
- If **no gaps found**: proceed directly to `/migration-preview` or `/migration-execute`.

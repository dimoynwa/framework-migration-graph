# Tasks: {FRAMEWORK} {FROM} to {TO}
HIGH: {n}  MEDIUM: {n}  LOW: {n}  Relevance-index: {n}

## Instructions for Code Agent
1. Work tasks strictly in sequential order (TASK-001..NNN).
2. Build ONCE at the end via verification.md. Fix forward; do not revert tasks.
3. Search before skipping. The Paysafe constraint is absolute: never downgrade `com.paysafe.*`.
4. Update Status inline as you go.

---

### TASK-001  {RISK}  {concern title}
**Status**: pending
**Derives-from**: {RULE-ID}
**Origin**: graph
**Executor**: openrewrite
**Recipe**: {recipe-id or none}
**Effort**: {trivial|moderate|architectural}
**File pattern**: {glob}

**Instructions**
  1. $ grep -rl "{pattern}" src/
  2. {specific transformation step}
  3. ...

**Before** ({lang}):
  {representative old snippet}
**After** ({lang}):
  {representative new snippet}

**Verify** (per-task, one-liner):
  $ ! grep -rq "{removed-symbol}" src/
  Expected: exit 0 (no matches remain).

---

## Relevance Index (NOT tasks - surfaced, not silently dropped)
Matched a rule but no graph-prescribed fix. clarify may promote one into a real task
(Origin=manual).

- RI-001  RuleID: {RULE-ID}  {description}  Applicability: {applicability}  Disposition: awaiting clarify
- RI-002  RuleID: {RULE-ID}  {description}  Applicability: uncertain  Disposition: awaiting clarify

# Contract: Agent-Codemod Executor

**Spec anchor**: FR-C01, FR-C02, FR-C03, FR-C04, FR-C09, FR-C10  
**New in**: 013-real-run-hardening

---

## Purpose

The agent-codemod executor is a Loop III executor track for migration steps that:
- Have no resolved OpenRewrite recipe (`AUTOMATED_BY` edge absent, or edge present but `auto=false` or `missingRequiredParams ≠ []`)
- Have `effort = mechanical` or `effort = moderate`
- Have a concrete instruction (see definition below)
- Have an entity anchor (at least one entity in the rule's affected-entity set matches the scanned context)

The agent applies the transformation directly to the codebase, gates it with a build-and-test run, and records the outcome. It does **not** require an `AUTOMATED_BY` edge — no graph schema change is needed to represent the agent-codemod track.

---

## Position in Loop III Selection

The executor-selection decision runs in this fixed order for every pending step:

1. **Resolved recipe** (`rec IS NOT NULL AND auto=true AND missingRequiredParams=[]`) → OpenRewrite track
2. **Partially resolved recipe** (edge exists but `auto=false` OR `missingRequiredParams ≠ []`) → Prompted-auto track
3. **No recipe, `mechanical` or `moderate` effort, concrete instruction, entity anchor present** → Agent-codemod track ← this contract
4. All other cases → Human-review track

One track per step. No step may be in two tracks simultaneously.

---

## Eligibility Criteria

A step is eligible for agent-codemod **only when all four** are true:

| Criterion | Requirement |
|---|---|
| Recipe state | No resolved recipe (criteria #3 above) |
| Effort | `mechanical` OR `moderate` |
| Concrete instruction | The `instruction` field meets the definition below |
| Entity anchor | At least one entity in the rule's affected-entity set matches the context's scanned entities |

**Concrete instruction definition**: the `instruction` must include at least one of:
- (a) A before/after transformation example
- (b) A named operation type (`rename`, `replace`, `remove`, `add`) with explicit source and target
- (c) A pattern (string, glob, or regex) plus a replacement target

Free-text description without a transformation pattern does not qualify. Steps with only a free-text description route to human-review.

---

## Execution Protocol

```
1. BLAST-RADIUS GATE
   a. Identify all files matching the entity anchor and instruction scope.
   b. Present the complete file list to the engineer.
   c. Check project-level setting `blast_radius_confirm_threshold` (default: 0 = always confirm).
      - If the affected file count EXCEEDS the threshold (or the threshold is 0): require explicit
        confirmation before proceeding. Do NOT apply changes without confirmation.
      - If the affected file count is AT OR BELOW a non-zero threshold: proceed without confirmation
        (FR-C09 project-level override). Log: "Auto-confirming: {N} files ≤ threshold {T}."
   d. The out-of-the-box default (`blast_radius_confirm_threshold = 0`) requires confirmation for
      ANY file count — even a single file. A project may set a non-zero threshold (e.g. 5) to allow
      auto-confirmation for small scopes without engineer intervention. Only an explicit project-level
      setting may skip confirmation; `blast_radius_confirm_threshold = 0` never auto-confirms.

2. IDEMPOTENCY CHECK
   a. Before applying any change, check whether the target state already matches
      the post-transformation expectation.
   b. If already applied → mark step `completed` immediately, no changes written.

3. APPLY TRANSFORMATION
   a. Apply the full transformation to all matched files.
   b. Track all modified files for rollback.

4. BUILD-AND-TEST GATE
   a. Run the project's build command (Maven/Gradle).
   b. Run the test suite.
   c. On PASS → call `update_step_status(outcome="completed")`. Done.

5. ON GATE FAILURE → ROLLBACK
   a. Load `skill://framework-migration/rollback` and follow the revert procedure defined there.
   b. The rollback skill restores all files modified in step 3 to their exact pre-change state
      using the VCS working tree (no database rollback required).
   c. Call `update_step_status(outcome="failed", reason="build failed: <error>")`.
   d. Record the failure reason on the STEP_OUTCOME relationship.
   e. Continue processing remaining steps in the current tier. Do NOT halt the session.
   f. Add the failed step to the Loop IV backlog with its failure reason.
```

---

## Graph Representation

No new graph schema is required. The outcome is recorded using the existing `update_step_status` tool with `outcome="completed"` or `outcome="failed"`. The executor track is a runtime routing decision — it is not persisted as a node or edge.

The `AUTOMATED_BY` edge is **not** written for agent-codemod outcomes. The agent-codemod track is represented only by the `STEP_OUTCOME` relationship with `status="completed"` or `status="failed"` and the `reason` field distinguishing it from OpenRewrite outcomes when needed.

---

## Failure Behaviour

- A failed agent-codemod step does not halt the session.
- Rollback restores the working tree to the exact pre-transformation state (all touched files).
- The failed step appears in the Loop IV backlog with its `reason`.
- The harness continues with remaining steps in the current tier.

---

## Out of Scope

- The agent-codemod executor never applies `deferred` (bridge) outcomes — that is a separate decision made before executor routing runs.
- The executor does not handle `architectural` effort steps.
- The executor does not apply changes without engineer confirmation.

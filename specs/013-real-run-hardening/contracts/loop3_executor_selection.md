# Contract: Loop III Executor Selection

**Spec anchor**: FR-C01, FR-C02, US4  
**New in**: 013-real-run-hardening

---

## Rule

Every pending step is assigned to **exactly one** executor track. The selection is deterministic given the step's recipe state, effort level, and instruction completeness. The `automatable` flag is metadata for reporting — it is not a routing input.

---

## Decision Table

Evaluated top-to-bottom; first matching row wins.

| # | Recipe state | Effort | Instruction + entity anchor | Track |
|---|---|---|---|---|
| 1 | Fully resolved | any | any | **OpenRewrite** |
| 2 | Partially resolved | any | any | **Prompted-auto** |
| 3 | None | `mechanical` | Yes | **Agent-codemod** |
| 4 | None | `moderate` | Yes | **Agent-codemod** |
| 5 | None | `mechanical` | No | **Human-review** |
| 6 | None | `moderate` | No | **Human-review** |
| 7 | None | `architectural` | any | **Human-review** |

**Definitions**:
- **Fully resolved recipe**: `AUTOMATED_BY` edge exists AND `auto=true` AND `missingRequiredParams=[]`
- **Partially resolved recipe**: `AUTOMATED_BY` edge exists AND (`auto=false` OR `missingRequiredParams ≠ []`)
- **No recipe**: no `AUTOMATED_BY` edge
- **Concrete instruction + entity anchor**: see [agent_codemod_executor.md](agent_codemod_executor.md)

---

## Track Behaviour Summary

### OpenRewrite
- Batch eligible steps into `rewrite.yml`.
- Apply via OpenRewrite CLI.
- Run build+test.
- On pass: `update_step_status(outcome="completed")`.
- On fail: rollback → `update_step_status(outcome="failed")` → continue.

### Prompted-auto
- Surface missing parameters to the engineer.
- If engineer provides them: patch recipe params and re-evaluate against row 1.
- If engineer declines: re-route to human-review.

### Agent-codemod
- Full protocol in [agent_codemod_executor.md](agent_codemod_executor.md).

### Human-review
- Emit step card (summary, instruction, verificationHint, jiraKeys, severity).
- Wait for engineer confirmation.
- On confirm: `update_step_status(outcome="completed")`.
- On skip: `update_step_status(outcome="skipped", reason=user_reason)`.
- On architectural effort: pause loop; emit design decision prompt; wait for explicit design choice; record as context note; then route to human-review step execution.

---

## Constraints

- One track per step. A step cannot appear in multiple tracks simultaneously.
- `automatable=true` with no recipe routes by effort and instruction presence — **never** to an automated track on the boolean alone.
- Bridge/deferred decisions happen before executor routing. A step routed to any executor track is an active step, not a bridge candidate.
- Test-scope (tier 4) steps complete human-review last, regardless of routing track.

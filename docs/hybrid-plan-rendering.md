# Hybrid Plan Rendering — Design Amendment
 
This document specifies the **hybrid plan rendering** design: a per-rule decision that
renders migration knowledge as either a concrete, file-anchored task or an honest
"needs investigation" entry, based on fields the graph already stores — not a new node
label, not a new pipeline stage, and not a new tool.
 
It amends four existing stage skills (`plan`, `gap-check`, `clarify`, `preview`) and
touches no other part of the system. `execute` and `feedback` are unaffected — they
already consume whatever `get_pending_steps` returns, regardless of a step's origin.
 
**Status:** Implemented.
**Affects:** `framework_migration_plan.md`, `framework_migration_gap_check.md`,
`framework_migration_clarify.md`, `framework_migration_preview.md`.
**Does not affect:** graph schema, `execute`, `feedback`, MCP tool contracts.
 
---
 
## 1. Problem this solves
 
Two plan-generation strategies were considered for this project:
 
- **Graph-state handoff** (current design) — `plan` caches "which rules/steps apply to
  this codebase" as state on `MigrationContext`. Concrete, file-level instructions are
  deferred to `execute`, which reads `get_pending_steps` live.
- **Concrete-task handoff** (SpecKit-style) — `plan` would emit a frozen, file-level
  task list (`change this file`, `add this property`) up front, the way SpecKit's
  `/speckit.plan` → `tasks.md` works.
Neither is strictly better. The graph-state approach is honest about rules that have no
prescribed fix yet (`entityClassification="incomplete"`, no `MigrationStep`), but it
under-serves the common case — most matched rules *do* have a complete, automatable
step, and forcing a relevance-index detour before every concrete action is friction the
data doesn't require. The concrete-task approach is more readable, but generating it
cheaply (one shallow query per entity, skipping the `resolve_deprecation` →
`entity_evolution` → `search_migration_knowledge` escalation chain) reintroduces the
known accuracy failure documented in `MIGRATION_LITE_MODE.md`: every rule comes back
tagged `applicability="universal"`, meaning "applies to this version range in general,"
not "confirmed against your code."
 
**The hybrid resolves this by rendering each rule individually**, using fields the full
escalation chain already produces, instead of picking one output shape for every rule
up front.
 
---
 
## 2. The render rule
 
After Loop II's full per-entity escalation completes (unchanged — this cost is paid
regardless of which design is used), classify each matched rule:
 
| Condition (existing fields, no new ones) | Render as |
|---|---|
| `entityClassification="actionable"` and the rule has ≥1 `MigrationStep` with a non-empty `instruction` and a matched entity (exact FQCN / property key / `groupId:artifactId`) | **Concrete task** |
| Same as above but step `effort="architectural"`, or `instruction` is generic/templated with no entity-specific detail | **Concrete task, flagged `NEEDS-DESIGN-REVIEW`** — give the scaffold, don't claim it's a drop-in fix |
| `entityClassification="incomplete"` (rule has `AFFECTS_*` edges but no `REQUIRES_STEP` edges) | **Relevance-index entry, not a task** — "this rule affects `X`; the graph has no prescribed fix yet" |
| `applicability="uncertain"` (high/critical safety-net match, no direct entity hit) | **Relevance-index entry**, explicitly labeled "may apply, not confirmed against your code" |
| Rule has a `BRIDGED_BY` edge and a step is later marked `deferred` | **Task downgraded to a placeholder** pointing at the bridge condition — never silently deleted |
 
This table is the only new piece of logic. It is a **rendering decision**, computed from
data the existing `analyze_upgrade_path` / `get_pending_steps` responses already carry
(`entityClassification`, `steps[]`, `applicability`, `BRIDGED_BY`). No new Cypher, no new
node label.
 
---
 
## 3. Where it lives in the six-stage pipeline
 
The render rule does not live in one place — it is naturally satisfied by the existing
stage boundaries, as long as each stage does its existing job:
 
```
plan        → tags each cached entity result with the render decision (§2 table)
gap-check   → mechanically flags any matched rule with no MigrationStep
               (the "stepless_rule" check — this is what actually *catches*
               every relevance-index candidate; it is not new, see §4.1)
clarify     → human converts a relevance-index entry into a real task via
               add_manual_step (origin="manual") — this is the one explicit,
               audited point where the hybrid's two categories cross over
preview     → renders the queue grouped by risk, labeling each task's origin
               (graph vs. manual) and applicability, so provenance is never
               flattened away
execute     → unchanged — consumes get_pending_steps as-is
feedback    → unchanged — submit_migration_insight already captures deviations,
               which is how a recurring manual step eventually becomes a
               graph-native one for the next project's plan stage
```
 
The key property: **`plan` never has to decide whether something becomes a task.** It
only tags a classification. The actual graph-aware enforcement is `gap-check`'s existing
stepless-rule check, and the actual conversion is `clarify`'s existing
`add_manual_step` — both of which already exist for other reasons and require no new
tooling.
 
---
 
## 4. Amendments by file
 
### 4.1 `framework_migration_plan.md`
 
**Add to Loop II, after the skip-guard / `update_queried_entity` step:**
 
> After each successful query, before caching, classify the result per the render table
> in `hybrid-plan-rendering.md` §2. Append the classification to the `result_summary`
> string passed to `update_queried_entity` (e.g. `"... → TASK"` or `"... →
> NEEDS-INVESTIGATION"`). This is advisory only — it does not gate which rules are
> cached, and it does not change `analyze_upgrade_path`'s own `applicability` field.
 
No change to tool calls, parameters, or the stateless fallback path.
 
### 4.2 `framework_migration_gap_check.md`
 
**No new check required.** The existing **Stepless-rule check** (full mode only) already
flags exactly the population that needs relevance-index treatment:
 
> Use `get_steps_for_scope_tier` per scope tier. Flag rules with entity hits but no
> linked `MigrationStep`.
 
Add one clarifying sentence to that section:
 
> A `stepless_rule` flag means this rule has no graph-prescribed fix — it should be
> presented to the operator as a relevance-index entry, not a task, until resolved in
> `clarify`.
 
This makes explicit what the flag is *for* in hybrid-rendering terms, without changing
its trigger condition or `write_gap_check_flags` payload shape.
 
### 4.3 `framework_migration_clarify.md`
 
**Add a short note under "Add manual steps":**
 
> Use this to convert a `stepless_rule`-flagged relevance-index entry into a concrete
> task when the operator already knows the fix. The resulting step's `origin="manual"`
> is what `preview` and `execute` use to distinguish it from a graph-verified step — do
> not attempt to retroactively mark it `origin="graph"`.
 
No change to `add_manual_step`'s parameters or the `OWNS_STEP` scoping behavior.
 
### 4.4 `framework_migration_preview.md`
 
**Amend the "Rendering rules" section** to require `origin` in the per-step line item
(it is already returned by `get_pending_steps` but was not previously listed as
mandatory in the rendered output):
 
> Within each group, list: summary, instruction (truncated if long), effort,
> applicability, **and origin (`graph` or `manual`) — always show this field; it is the
> reader's signal for how much confidence to place in the step.**
 
This is the only required preview-stage change. No new tool, no new caveat category
beyond the existing gap-check caveats section.
 
---
 
## 5. What does NOT change
 
- Graph schema (`graph-schema.md`) — no new node label, relationship type, or property.
- `framework_migration_execute.md` — the executor-selection table already keys off
  `effort` + "concrete instruction + entity anchor," which is precisely what the render
  rule in §2 also checks. Execute does not need to know a step came from the hybrid
  classification; it already behaves correctly on `origin="manual"` steps via the
  existing decision table.
- `framework_migration_feedback.md` — `submit_migration_insight`'s existing deviation
  capture is already the right mechanism for promoting a recurring manual fix into
  graph-native knowledge.
- MCP tool contracts — `analyze_upgrade_path`, `get_pending_steps`, `add_manual_step`,
  `write_gap_check_flags` are all used as-is, with existing parameters.
---
 
## 6. Worked example
 
`payments-ledger-service`, Spring Boot `2.7.18 → 3.2.4`. Two matched rules:
 
- **r1** — `WebSecurityConfigurerAdapter` removed; has step `s1`, `effort="moderate"`,
  concrete instruction, matched entity. → render rule: **concrete task**.
- **r2** — `javax.persistence.Entity` namespace move; `entityClassification="incomplete"`,
  no `MigrationStep`. → render rule: **relevance-index entry**.
**`plan`:** caches both; r2's `result_summary` carries `"→ NEEDS-INVESTIGATION"`.
 
**`gap-check`:** stepless-rule check flags r2:
```json
{"type": "stepless_rule", "reference": "r2",
 "message": "javax.persistence.Entity matched but rule r2 has no MigrationStep."}
```
 
**`clarify`:** operator adds a manual step for r2 via `add_manual_step`, producing `s2`
with `origin="manual"`.
 
**`preview`:** renders both as HIGH-risk tasks, but labeled by origin:
```
TASK-001  Replace WebSecurityConfigurerAdapter ...   origin: graph   effort: moderate
TASK-002  Migrate javax.persistence.Entity ...        origin: manual  effort: mechanical
```
 
**`execute` / `feedback`:** unchanged — both steps complete via agent-codemod, and
`submit_migration_insight` captures r2's solution as a community insight so the next
project's `plan` stage finds a real `MigrationStep` instead of an `incomplete`
classification.
 
---
 
## 7. Open question for implementation
 
Should `gap-check`'s `stepless_rule` flag distinguish "no step, high/critical severity"
from "no step, low severity" for prioritizing which relevance-index entries get a
`clarify` pass first? Not addressed here — left for the implementing spec to decide
against real-world flag volume.

**Resolution:** Deferred to backlog — not addressed in this implementation. To be evaluated against real-world stepless_rule flag volume.
# SpecKit Runbook — Hybrid Plan Rendering

> **Source spec:** `hybrid-plan-rendering.md` (status: design amendment, not yet implemented)
> **Type:** Spec amendment to four existing migration-stage skill files —
> `framework_migration_plan.md`, `framework_migration_gap_check.md`,
> `framework_migration_clarify.md`, `framework_migration_preview.md`
> **Prerequisite:** none of the four target files are mid-edit; no other pending amendment
> touches the same anchor sections
> **Does not touch:** `graph-schema.md`, `framework_migration_execute.md`,
> `framework_migration_feedback.md`, any MCP tool handler, `mcp-tools-skills-prompts.md`

---

## Prerequisites block

Before running any command in this runbook, verify:

- [ ] `hybrid-plan-rendering.md` is in the project knowledge base and its status line still
      reads "Design amendment, not yet implemented" (re-check in case this was already applied)
- [ ] The four target skill files are in the project knowledge base at their current content —
      re-view them immediately before `/speckit.specify` in case they've drifted since this
      runbook was written
- [ ] No MCP server restart is implied by this work — none of the four files' `compatibility.tools`
      frontmatter blocks change, so `MCP_ACTIVE_STAGE` gating is unaffected end to end

**Spec-registration decision (resolve before running Command 1):** the four target skill files
are *not* part of the numbered `000`–`005` inventory in `SPEC_ORGANIZATION.md` — they are
standalone harness skill docs. So this work does **not** automatically get an `SPEC_ORGANIZATION.md`
row, and the closing "update the status cell to ✅" step from the other spec runbooks does not
apply here. Pick one of two homes before running:

- **(A) Standalone amendment (default for this runbook).** Run the lifecycle below with its
  artifacts written under `specs/hybrid-plan-rendering/` (un-numbered), and do **not** add a row
  to `SPEC_ORGANIZATION.md`. The completion signal is `hybrid-plan-rendering.md`'s own status
  line (see "What success looks like" §5), not an inventory cell.
- **(B) Fold into `004-mcp-server`.** If the team prefers this to live under a numbered spec,
  treat it as an amendment to `004` per `speckit-sdd-buddy` §7 instead — but note `004` is still
  `🔲 Not started`, so this would block on `004` starting first. Only choose (B) if you are
  willing to gate this work behind `004`'s prerequisites.

This runbook assumes **(A)**. If you choose (B), stop and re-scope against `004`'s spec first.

---

## Command 1 — `/speckit.specify`

**Prompt to paste:**

```
/speckit.specify

WHAT it does: Adds a per-rule rendering classification to the migration-plan pipeline.
Each matched migration rule, once Loop II's full escalation chain (resolve_deprecation →
entity_evolution → search_migration_knowledge) has run, is classified into exactly one of
five render outcomes using fields the graph already returns — entityClassification, the
presence and contents of steps[], applicability, and BRIDGED_BY — and that classification
is surfaced consistently across four pipeline stages (plan, gap-check, clarify, preview).
No new node label, relationship type, MCP tool, or pipeline stage is introduced.

WHY it exists: Two designs were rejected as strictly worse: a pure graph-state handoff
(under-serves the common case where a rule already has a complete fix, forcing every rule
through a relevance-index detour) and a pure concrete-task handoff (cheap to generate but
reintroduces the known applicability="universal" accuracy failure documented in
MIGRATION_LITE_MODE.md, since it skips the escalation chain). The hybrid renders each rule
individually instead of picking one output shape for the whole plan up front.

PLAN STAGE and what it does:
- After each successful Loop II query and before caching, classifies the result per the
  render table (see KEY BEHAVIORS: RENDER_CLASSIFICATION below)
- Appends the classification as a suffix to the result_summary string already passed to
  update_queried_entity (e.g. "... → TASK" / "... → NEEDS-INVESTIGATION")
- Named operations touched: update_queried_entity (argument content only, not signature)

GAP-CHECK STAGE and what it does:
- Its existing Stepless-rule check (full mode only) is the actual enforcement mechanism for
  the NEEDS-INVESTIGATION population — no new check is added
- Gains one clarifying sentence on what a stepless_rule flag means for plan rendering
- Named operations touched: none — write_gap_check_flags payload shape is unchanged

CLARIFY STAGE and what it does:
- Its existing add_manual_step operation is the one explicit, audited point where a
  relevance-index entry crosses over into a concrete task
- Gains a note that the resulting step's origin="manual" must never be retroactively
  rewritten to origin="graph"
- Named operations touched: none — add_manual_step's parameters are unchanged

PREVIEW STAGE and what it does:
- Its existing per-step line-item rendering must always display the origin field
  (graph or manual), upgraded from optional-mention to mandatory
- Named operations touched: none — get_pending_steps already returns origin; this is a
  presentation requirement only

KEY BEHAVIORS:
RENDER_CLASSIFICATION — Every matched rule, after full escalation, lands in exactly one of:
  (1) CONCRETE TASK — entityClassification="actionable" AND ≥1 MigrationStep with non-empty
      instruction AND a matched entity (exact FQCN / property key / groupId:artifactId)
  (2) CONCRETE TASK, flagged NEEDS-DESIGN-REVIEW — same as (1) but effort="architectural" OR
      instruction is generic/templated with no entity-specific detail
  (3) RELEVANCE-INDEX ENTRY — entityClassification="incomplete" (AFFECTS_* edges exist,
      no REQUIRES_STEP edge); rendered as "this rule affects X; no prescribed fix yet"
  (4) RELEVANCE-INDEX ENTRY, labeled uncertain — applicability="uncertain" (safety-net match,
      no direct entity hit); rendered as "may apply, not confirmed against your code"
  (5) PLACEHOLDER — rule has a BRIDGED_BY edge and its step is later marked deferred; task is
      downgraded to a placeholder pointing at the bridge condition, never silently deleted
NO_NEW_DATA_FIELD — every input to the classification (entityClassification, steps[],
  applicability, BRIDGED_BY) is already returned today by analyze_upgrade_path /
  get_pending_steps. The classification is a pure function over existing response shape.
ADVISORY_ONLY_AT_PLAN — plan's classification suffix never gates which rules are cached and
  never mutates analyze_upgrade_path's own applicability field. It is a label, not a filter.
PROVENANCE_NEVER_FLATTENED — preview must always show origin per step; a manual-origin step
  must never be visually indistinguishable from a graph-verified one.
ORIGIN_IS_ONE_WAY — once a step is created via add_manual_step with origin="manual", no
  stage may rewrite it to origin="graph", even after a community insight later formalizes
  the same fix in the graph.
STEPLESS_RULE_IS_THE_CATCH — gap-check's pre-existing stepless_rule flag is the only
  enforcement mechanism for surfacing relevance-index candidates to a human; this amendment
  does not add a second detection path.

INTEGRATION CONSTRAINTS:
- execute and feedback stages are explicitly out of scope — execute already behaves
  correctly on origin="manual" via its existing effort + entity-anchor executor-selection
  table; feedback's submit_migration_insight deviation capture is unchanged
- Graph schema (graph-schema.md) is read-only with respect to this change — no new node
  label, relationship type, or property may be introduced to satisfy this spec
- No MCP tool's parameter list, return shape, or registration may change
- update_queried_entity, write_gap_check_flags, add_manual_step, get_pending_steps are all
  used exactly as currently contracted in mcp-tools-skills-prompts.md
- This is documentation/prompt-text only — no changes to migration_oracle/mcp/tools/ or
  migration_oracle/mcp/graph/queries/ handler code, and no new entries in tests/mcp/
```

---

## Post-specify gap review

```
Review the generated spec.md for hybrid-plan-rendering and check for these critical gaps
before we proceed to planning:

GAP-001: Five-way classification fully enumerated, not abbreviated to two
  The worked example in hybrid-plan-rendering.md §6 only exercises outcomes (1) and (3).
  spec.md must explicitly carry all five render outcomes from KEY BEHAVIORS, including
  (2) NEEDS-DESIGN-REVIEW and (5) PLACEHOLDER/BRIDGED_BY, not just the two the example shows.
  Risk: an implementer who only reads the worked example ships a two-way classifier that
  silently mishandles architectural-effort steps and bridged/deferred steps.

GAP-002: "No new tool" constraint is testable, not just asserted
  spec.md must state explicitly which existing tool calls are touched (update_queried_entity,
  add_manual_step is referenced but unchanged, get_pending_steps is read-only consumed) and
  that none gain, lose, or rename a parameter. Risk: a plan.md that "helpfully" adds an
  optional render_hint parameter to update_queried_entity would violate the spec's own
  stated boundary while looking like a natural extension.

GAP-003: ORIGIN_IS_ONE_WAY behavior is stated as irreversible, not just discouraged
  Confirm the spec phrases this as a hard constraint ("must never") rather than a soft
  preference. Risk: soft phrasing invites a plan.md that adds a "promote to graph origin"
  convenience path, which the source design doc explicitly forbids.

GAP-004: Stepless-rule check is named as pre-existing, not newly introduced
  spec.md must make clear gap-check's stepless_rule check already exists today and this
  amendment only adds an explanatory sentence to it. Risk: a plan.md that treats this as a
  new check to build duplicates existing logic or, worse, adds a second flag type alongside
  stepless_rule for the same population.

GAP-005: Advisory-only nature of plan's classification stated as a hard non-gate
  spec.md must state that the plan-stage classification suffix does not affect which rules
  get cached and does not affect applicability. Risk: an implementer could read "classify
  before caching" as license to drop NEEDS-INVESTIGATION rules from the cache entirely,
  which would break gap-check's stepless-rule detection downstream (it operates over cached
  rules).

GAP-006: Severity-bucketing of stepless_rule explicitly marked out of scope
  The source spec's own §7 leaves "should stepless_rule distinguish high/critical from low
  severity" as an open question for the implementing spec to decide. spec.md must either
  explicitly resolve this (pick one, state why) or explicitly defer it as a backlog item —
  it must not be silently absent. Risk: silently dropping this means it's neither decided
  nor tracked, and it resurfaces as a surprise later.

GAP-007: Write-boundary statement for the four touched files
  spec.md must state plainly that this work is prompt/documentation text edits to four
  specific .md files, with zero application code changes. Risk: without this stated
  explicitly, plan.md may invent a code module (e.g. a render_classifier.py) that doesn't
  need to exist — the classification is meant to live in agent-followed prose, not in a
  callable function, per the source design's "rendering decision, not new Cypher" framing.

GAP-008: execute/feedback exclusion is explicit, not just implied by omission
  Confirm spec.md explicitly lists execute and feedback as out of scope with the reason
  (they already consume get_pending_steps / origin correctly), rather than simply not
  mentioning them. Risk: an implementer who notices execute and feedback aren't mentioned
  may assume this was an oversight and "fix" them anyway.

GAP-009: Worked example reproducibility named as an acceptance check
  spec.md should reference that hybrid-plan-rendering.md §6 (payments-ledger-service,
  Spring Boot 2.7.18 → 3.2.4, rules r1/r2) is available as a ready-made test fixture for
  later verification. Risk: without naming this, plan.md/tasks.md may invent a different,
  weaker example instead of reusing the one the design doc already worked through in detail.

Fix any of the above that are missing or underspecified before proceeding.
```

---

## Command 2 — `/speckit.plan`

```
/speckit.plan

Required artifacts for this spec:

- plan.md: must state, file by file, the exact anchor point in each of the four target
  files where the new text is inserted (section heading or the specific paragraph it
  follows), quoting the current text being anchored against. No new source files. No new
  Python modules, no new Cypher queries, no new MCP tool registrations.

- data-model.md: this spec introduces no new types, schemas, or storage key formats —
  plan.md must explicitly state "no data-model.md changes; classification values are a
  closed five-item enum used only in prose/skill-doc text, not persisted to any store or
  passed as a typed argument anywhere." Do not generate a data-model.md with invented
  structures.

- contracts/: no new component boundaries are introduced — plan.md must state explicitly
  that no contracts/ file is required for this spec, since no inter-component delegation
  rule changes.

- research.md: not required — there is no open technical unknown being spiked. If
  /speckit.plan generates one anyway, it should be empty/omitted rather than contain
  invented research questions.

- quickstart.md: must describe how to verify the amendment locally — i.e., how to re-read
  the four amended files and walk the hybrid-plan-rendering.md §6 worked example by hand
  against the new prose, since there is no running service component to "start" for a
  documentation-only change.
```

---

## Post-plan gap review

```
Review the generated plan.md for hybrid-plan-rendering and check for these gaps before we
proceed to tasks:

PLAN-GAP-001: Anchor quoting is exact, not paraphrased
  Each of the four file edits in plan.md must quote the exact current text it anchors
  against (e.g. plan.md's edit must quote the literal "Skip guard:" sentence from
  framework_migration_plan.md verbatim). Risk: a paraphrased anchor means Claude Code's
  str_replace-equivalent edit fails to match during /speckit.implement, or worse, matches
  the wrong location.

PLAN-GAP-002: No invented data-model.md content
  Confirm data-model.md is either absent or contains only the explicit "no changes" note
  from the specify prompt. Risk: SpecKit's default behavior is to always populate this file;
  left unchecked, it may invent a RenderClassification enum as if it were a persisted type,
  contradicting the spec's explicit "not persisted" constraint.

PLAN-GAP-003: No invented contracts/ file
  Confirm no contracts/NNN-hybrid-plan-rendering.md file was generated, or if one was,
  that it states no boundary changes rather than inventing new delegation rules between
  plan/gap-check/clarify/preview that don't actually exist in the source design.

PLAN-GAP-004: Four-file edit scope, not four-file scope with a fifth slipped in
  Confirm plan.md's file list is exactly: framework_migration_plan.md,
  framework_migration_gap_check.md, framework_migration_clarify.md,
  framework_migration_preview.md. Risk: plan.md scope-creeping into
  mcp-tools-skills-prompts.md "for completeness" when no tool contract changed, or into
  framework_migration_execute.md / framework_migration_feedback.md, both explicitly named
  as out of scope in the source design doc's §5.

PLAN-GAP-005: No new Python/handler files in the file layout section
  Confirm plan.md's project structure / file layout section lists zero new .py files.
  Risk: SpecKit's default templates assume a code deliverable; this spec's deliverable is
  pure prose, and a plan.md that adds e.g. migration_oracle/mcp/render_classifier.py
  contradicts GAP-007 from the specify-stage review.

PLAN-GAP-006: quickstart.md's verification path matches the worked example
  quickstart.md must point at the same r1/r2 / payments-ledger-service example named in
  GAP-009, not a freshly invented scenario. Risk: two different "how to verify this" stories
  existing in the same spec creates ambiguity about which one is authoritative.

PLAN-GAP-007: Open question (severity-bucketing) carried forward, not dropped
  Confirm plan.md still carries forward whatever GAP-006 (specify-stage) resolved about the
  stepless_rule severity-bucketing open question — either as an explicit decision plan.md
  implements, or as an explicit non-goal noted in plan.md's scope section.

PLAN-GAP-008: Stage-gating mechanics explicitly declared unaffected
  plan.md must state that none of the four edited files' compatibility.tools frontmatter
  blocks change, and therefore MCP_ACTIVE_STAGE gating and server restart behavior are
  unaffected. Risk: without this stated, an implementer may add an unnecessary "restart
  the MCP server" step to quickstart.md or tasks.md.
```

---

## Command 3 — `/speckit.tasks`

```
/speckit.tasks
```

No additional context needed — SpecKit reads the plan automatically.

---

## Post-tasks gap review

```
Review the generated tasks.md for hybrid-plan-rendering and check for these gaps before we
proceed to implement:

TASK-GAP-001: Four tasks, one per file, independently markable [P]
  Confirm there are exactly four primary edit tasks — one per target file — and that they
  are marked [P] (parallel-safe), since each touches a distinct file with no shared state.
  Risk: tasks.md sequencing them artificially in series wastes a round trip for no reason;
  these edits have no ordering dependency on each other.

TASK-GAP-002: Each task names its exact anchor and exact inserted text
  Every task description must reproduce the literal anchor text and the literal text to
  insert (matching plan.md's PLAN-GAP-001-verified quotes), not just say "add the
  classification note to the gap-check stepless-rule section." Risk: vague task descriptions
  reintroduce the same ambiguity PLAN-GAP-001 was meant to close, one level later.

TASK-GAP-003: No task creates a new file
  Confirm zero tasks create new .py, .md (beyond the four targets), or test files. Risk:
  SpecKit's task templates often add a "create research.md" or "create contracts/" task by
  default even when plan.md said these aren't needed — carry forward PLAN-GAP-002/003's
  resolution into the task list, don't let it regenerate at this stage.

TASK-GAP-004: Verification task uses the worked example, not a new fixture
  There must be a task (not just acceptance criteria prose) that walks
  hybrid-plan-rendering.md §6's r1/r2 example end-to-end against the four edited files and
  confirms the narrated outcome (TASK-001 graph-origin, TASK-002 manual-origin, both shown
  with origin labels in preview's rendering rules). Risk: without a dedicated task, this
  check gets silently skipped during /speckit.implement.

TASK-GAP-005: No task touches execute, feedback, graph-schema, or mcp-tools-skills-prompts.md
  Explicitly confirm by scanning every task's target file. Risk: a single stray task that
  "syncs documentation" across these excluded files reintroduces scope creep that both prior
  gap reviews were built to prevent.

TASK-GAP-006: Status-line update task exists
  There must be a task to update hybrid-plan-rendering.md's own header line from
  "Status: Design amendment, not yet implemented." to "Status: Implemented." once the other
  tasks complete — the source doc tracks its own implementation state and this is the
  closing signal. Risk: without this task, the source-of-truth doc is left permanently
  showing the work as not-yet-done even after it ships.

TASK-GAP-007: Open question (severity-bucketing) has a backlog task, not silence
  Whatever PLAN-GAP-007 resolved (explicit decision or explicit non-goal), tasks.md must
  reflect it as either an implemented task or an explicitly logged backlog item — not
  simply absent from the task list with no trace.

TASK-GAP-008: No task suite added under tests/mcp/
  Confirm tasks.md does not add pytest files. Risk: since no MCP tool contract changed, new
  tests under tests/mcp/ would test nothing real and inflate the test suite with assertions
  about prose strings, which is not what that test directory is for.
```

---

## Command 4 — `/speckit.implement`

```
/speckit.implement
```

---

## Recovery prompts

Use these verbatim when Claude Code drifts from the spec during implementation.

**Drift: classification logic implemented as code instead of skill prose**
```
Do not create a render_classifier.py or any callable function implementing the five-way
render table. The classification in hybrid-plan-rendering.md §2 is a rendering decision an
agent applies while reading skill-doc prose, not a persisted type or a runtime computation.
The only deliverable is edited text inside the four named .md skill files. Revert any new
.py file and reapply the change as a documentation edit only.
```

**Drift: update_queried_entity or add_manual_step gains a new parameter**
```
Do not add render_hint, classification, or any new parameter to update_queried_entity or
add_manual_step. The amendment is advisory-only: the classification is appended as a plain
text suffix inside the existing result_summary string argument. No MCP tool signature may
change. Revert the parameter addition and express the classification as a string suffix
instead.
```

**Drift: origin retroactively rewritten from manual to graph**
```
Do not implement any path that rewrites a step's origin from "manual" to "graph" after a
community insight formalizes the same fix in the graph knowledge base. origin="manual" is
permanent for that step once created via add_manual_step. The mechanism for "this fix is now
graph-native" is that the *next* project's plan stage finds a real MigrationStep via
analyze_upgrade_path — it does not retroactively alter the original manual step's record.
```

**Drift: stepless_rule check duplicated or a second flag type introduced**
```
Do not add a new gap-check flag type alongside stepless_rule (e.g. needs_investigation or
relevance_index_candidate). The existing stepless_rule flag, unchanged in trigger condition
and unchanged in write_gap_check_flags payload shape, is the sole detection mechanism for
the relevance-index population. The only change to gap-check is one clarifying sentence
appended to the existing Stepless-rule check subsection.
```

**Drift: NEEDS-INVESTIGATION rules dropped from the cache**
```
Plan's classification step happens "before caching" but must not change WHAT gets cached —
every matched rule, regardless of classification, is still passed to update_queried_entity
exactly as before. Only the result_summary string's content changes (a suffix is appended).
Do not filter, skip, or conditionally omit update_queried_entity calls based on the
classification outcome.
```

**Drift: preview silently omits origin for manual steps to "simplify" the view**
```
The origin field (graph or manual) must be shown for every single step in preview's
rendered output, with no exceptions, including low-risk or manual-without-severity steps in
the LOW group. Do not collapse or omit this field for any step grouping. It is the reader's
sole signal for how much confidence to place in that step.
```

---

## What success looks like

This is a documentation-only amendment, so "success" is verified by manual trace-through
rather than an automated test run:

1. **Diff scope check** — `git diff` shows changes in exactly these four files and nowhere
   else:
   - `framework_migration_plan.md`
   - `framework_migration_gap_check.md`
   - `framework_migration_clarify.md`
   - `framework_migration_preview.md`

2. **Anchor fidelity check** — for each of the four files, confirm the inserted text sits at
   the exact anchor named in plan.md (end of Loop II / end of Skip guard for plan; end of
   Stepless-rule check subsection for gap-check; end of Add manual steps subsection for
   clarify; the "Within each group, list:" line for preview) and that no other paragraph in
   any of the four files was reflowed, reordered, or altered.

3. **Worked-example walkthrough** — using only the four amended files (not the original
   design doc), manually narrate `hybrid-plan-rendering.md` §6's `payments-ledger-service`
   example:
   - `plan` tags r1 with a TASK-bound classification and r2 with `→ NEEDS-INVESTIGATION`
     in its cached `result_summary`
   - `gap-check`'s stepless-rule check flags r2 as `stepless_rule`
   - `clarify`'s amended note correctly describes converting r2 via `add_manual_step` into
     `s2` with `origin="manual"`
   - `preview`'s mandatory-origin rendering rule produces output matching:
     ```
     TASK-001  Replace WebSecurityConfigurerAdapter ...   origin: graph   effort: moderate
     TASK-002  Migrate javax.persistence.Entity ...        origin: manual  effort: mechanical
     ```
   All four bullets must check out using only the new prose — if any step requires
   "back-reading" the original design doc to make sense, the amendment is incomplete.

4. **No-tool-contract-change check** — confirm `mcp-tools-skills-prompts.md` is byte-identical
   to its pre-amendment state, and `pytest tests/mcp/` (if run) shows zero new or modified
   test files related to this change.

5. **Status-line update** — `hybrid-plan-rendering.md`'s own header now reads
   `**Status:** Implemented.` (or equivalent), and the open question from its §7
   (severity-bucketing of `stepless_rule`) is either resolved with a stated reason or
   explicitly carried into a tracked backlog item — not silently dropped either way.

All five checks passing constitutes the completion gate for this amendment.

> **Note (differs from the numbered-spec runbooks):** under home **(A)**, there is no
> `SPEC_ORGANIZATION.md` row to flip to ✅ — the source doc's own status line is the
> completion record. Do not go looking for an inventory cell to update. (Under home **(B)**,
> update `004-mcp-server`'s status per that spec's own runbook instead.)
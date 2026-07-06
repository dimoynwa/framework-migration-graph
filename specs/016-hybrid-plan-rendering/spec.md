# Feature Specification: Hybrid Plan Rendering

**Feature Branch**: `016-hybrid-plan-rendering`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "WHAT it does: Adds a per-rule rendering classification to the migration-plan pipeline. Each matched migration rule, once Loop II's full escalation chain (resolve_deprecation → entity_evolution → search_migration_knowledge) has run, is classified into exactly one of five render outcomes using fields the graph already returns — entityClassification, the presence and contents of steps[], applicability, and BRIDGED_BY — and that classification is surfaced consistently across four pipeline stages (plan, gap-check, clarify, preview). No new node label, relationship type, MCP tool, or pipeline stage is introduced. WHY it exists: Two designs were rejected as strictly worse: a pure graph-state handoff (under-serves the common case where a rule already has a complete fix, forcing every rule through a relevance-index detour) and a pure concrete-task handoff (cheap to generate but reintroduces the known applicability=\"universal\" accuracy failure documented in MIGRATION_LITE_MODE.md, since it skips the escalation chain). The hybrid renders each rule individually instead of picking one output shape for the whole plan up front. PLAN STAGE and what it does: - After each successful Loop II query and before caching, classifies the result per the render table (see KEY BEHAVIORS: RENDER_CLASSIFICATION below) - Appends the classification as a suffix to the result_summary string already passed to update_queried_entity (e.g. \"... → TASK\" / \"... → NEEDS-INVESTIGATION\") - Named operations touched: update_queried_entity (argument content only, not signature) GAP-CHECK STAGE and what it does: - Its existing Stepless-rule check (full mode only) is the actual enforcement mechanism for the NEEDS-INVESTIGATION population — no new check is added - Gains one clarifying sentence on what a stepless_rule flag means for plan rendering - Named operations touched: none — write_gap_check_flags payload shape is unchanged CLARIFY STAGE and what it does: - Its existing add_manual_step operation is the one explicit, audited point where a relevance-index entry crosses over into a concrete task - Gains a note that the resulting step's origin=\"manual\" must never be retroactively rewritten to origin=\"graph\" - Named operations touched: none — add_manual_step's parameters are unchanged PREVIEW STAGE and what it does: - Its existing per-step line-item rendering must always display the origin field (graph or manual), upgraded from optional-mention to mandatory - Named operations touched: none — get_pending_steps already returns origin; this is a presentation requirement only KEY BEHAVIORS: RENDER_CLASSIFICATION — Every matched rule, after full escalation, lands in exactly one of: (1) CONCRETE TASK — entityClassification=\"actionable\" AND ≥1 MigrationStep with non-empty instruction AND a matched entity (exact FQCN / property key / groupId:artifactId) (2) CONCRETE TASK, flagged NEEDS-DESIGN-REVIEW — same as (1) but effort=\"architectural\" OR instruction is generic/templated with no entity-specific detail (3) RELEVANCE-INDEX ENTRY — entityClassification=\"incomplete\" (AFFECTS_* edges exist, no REQUIRES_STEP edge); rendered as \"this rule affects X; no prescribed fix yet\" (4) RELEVANCE-INDEX ENTRY, labeled uncertain — applicability=\"uncertain\" (safety-net match, no direct entity hit); rendered as \"may apply, not confirmed against your code\" (5) PLACEHOLDER — rule has a BRIDGED_BY edge and its step is later marked deferred; task is downgraded to a placeholder pointing at the bridge condition, never silently deleted NO_NEW_DATA_FIELD — every input to the classification (entityClassification, steps[], applicability, BRIDGED_BY) is already returned today by analyze_upgrade_path / get_pending_steps. The classification is a pure function over existing response shape. ADVISORY_ONLY_AT_PLAN — plan's classification suffix never gates which rules are cached and never mutates analyze_upgrade_path's own applicability field. It is a label, not a filter. PROVENANCE_NEVER_FLATTENED — preview must always show origin per step; a manual-origin step must never be visually indistinguishable from a graph-verified one. ORIGIN_IS_ONE_WAY — once a step is created via add_manual_step with origin=\"manual\", no stage may rewrite it to origin=\"graph\", even after a community insight later formalizes the same fix in the graph. STEPLESS_RULE_IS_THE_CATCH — gap-check's pre-existing stepless_rule flag is the only enforcement mechanism for surfacing relevance-index candidates to a human; this amendment does not add a second detection path. INTEGRATION CONSTRAINTS: - execute and feedback stages are explicitly out of scope — execute already behaves correctly on origin=\"manual\" via its existing effort + entity-anchor executor-selection table; feedback's submit_migration_insight deviation capture is unchanged - Graph schema (graph-schema.md) is read-only with respect to this change — no new node label, relationship type, or property may be introduced to satisfy this spec - No MCP tool's parameter list, return shape, or registration may change - update_queried_entity, write_gap_check_flags, add_manual_step, get_pending_steps are all used exactly as currently contracted in mcp-tools-skills-prompts.md - This is documentation/prompt-text only — no changes to migration_oracle/mcp/tools/ or migration_oracle/mcp/graph/queries/ handler code, and no new entries in tests/mcp/"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Plan Stage Migration Rule Classification (Priority: P1)

As the Plan stage of the migration-plan pipeline, I need to consistently classify each matched migration rule into exactly one of five rendering outcomes based strictly on graph-supplied fields (entityClassification, steps[], applicability, BRIDGED_BY) and append this classification as a suffix to the `result_summary` payload when calling `update_queried_entity`.

**Why this priority**: Correctly tagging the outcome in the `result_summary` early ensures that subsequent steps have clear expectations on whether a rule is an actionable concrete task, an architectural task needing review, a relevance-index entry, an uncertain relevance-index entry, or a placeholder for a bridged step, avoiding the applicability="universal" failure mode without introducing new schema fields.

**Independent Test**: Can be tested independently by running Loop II queries for rules that fit each of the 5 render outcomes and verifying that a plain-text suffix identifying the classification is appended to the `update_queried_entity` arguments, without changing its API signature or graph properties. Exact string formats are defined at the plan phase.

**Acceptance Scenarios**:

1. **Given** a matched rule resulting in a `CONCRETE TASK` outcome (entityClassification="actionable", >0 Steps with non-empty instructions, and matched exact entity), **When** `update_queried_entity` is called, **Then** a plain-text suffix identifying the classification outcome (e.g., indicating "TASK") is appended to the `result_summary`.
2. **Given** a matched rule resulting in a `CONCRETE TASK (NEEDS-DESIGN-REVIEW)` outcome (same as 1, but effort="architectural" OR instruction is generic/templated), **When** `update_queried_entity` is called, **Then** a plain-text suffix identifying the outcome (e.g., indicating "TASK (NEEDS-DESIGN-REVIEW)") is appended to the `result_summary`.
3. **Given** a matched rule resulting in a `RELEVANCE-INDEX ENTRY` outcome (entityClassification="incomplete"), **When** `update_queried_entity` is called, **Then** a plain-text suffix identifying the outcome (e.g., indicating "RELEVANCE-INDEX ENTRY") is appended to the `result_summary`.
4. **Given** a matched rule resulting in a `RELEVANCE-INDEX ENTRY (uncertain)` outcome (applicability="uncertain"), **When** `update_queried_entity` is called, **Then** a plain-text suffix identifying the outcome (e.g., indicating "RELEVANCE-INDEX ENTRY (uncertain)") is appended to the `result_summary`.
5. **Given** a matched rule resulting in a `PLACEHOLDER` outcome (rule has BRIDGED_BY edge and step marked deferred), **When** `update_queried_entity` is called, **Then** a plain-text suffix identifying the outcome (e.g., indicating "PLACEHOLDER") is appended to the `result_summary`.
6. **Given** a matched rule whose graph response is anomalous or missing required fields, **When** `update_queried_entity` is called, **Then** a fallback plain-text suffix identifying the outcome as `UNCLASSIFIED` is appended to the `result_summary` and the rule is not suppressed from the cache.

**Constraint Note:** The `ADVISORY_ONLY_AT_PLAN` behavior is not a sixth outcome but a cross-cutting constraint (enforced via FR-004/FR-005). The classification suffix must never mutate the `applicability` field of the `analyze_upgrade_path` response, and rules are never filtered from the cache based on their classification.

---

### User Story 2 - Explicit Traceability in Clarify Stage (Priority: P1)

As the Clarify stage of the pipeline, I need to ensure that any relevance-index entry that crosses into becoming a concrete task uses `add_manual_step`, and that the `origin="manual"` flag is permanently preserved and never rewritten to `origin="graph"`.

**Why this priority**: Preserving provenance is critical for accountability. `origin="manual"` signifies a human or LLM heuristic decision that must never be obfuscated or flattened back into a system-derived `origin="graph"`.

**Independent Test**: Can be tested independently by simulating a Clarify stage flow that converts a relevance-index entry into a step using `add_manual_step` and verifying the constraints preventing retroactive rewriting to `origin="graph"`.

**Acceptance Scenarios**:

1. **Given** a relevance-index entry being transitioned to a concrete task via `add_manual_step`, **When** the human adds a manual step, **Then** the step retains `origin="manual"`.
2. **Given** a manual step exists, **When** a community insight formalizes the same fix in the graph later, **Then** the existing step's origin must not be retroactively rewritten to `origin="graph"`.

---

### User Story 3 - Visual Provenance in Preview Stage (Priority: P2)

As the Preview stage of the pipeline, I need to mandatorily display the `origin` field (graph or manual) for every rendered step line-item, so that the provenance of the step is always visibly distinct.

**Why this priority**: The presentation of `origin` allows the user to immediately discern which tasks are community-verified versus those generated heuristically or manually in the Clarify stage.

**Independent Test**: Can be tested independently by reviewing the Preview stage rendering rules to ensure that step origin is exposed visually.

**Acceptance Scenarios**:

1. **Given** pending steps returned by `get_pending_steps` that contain `origin="manual"` and `origin="graph"`, **When** the Preview stage renders them, **Then** each line item visibly differentiates its origin, fulfilling the `PROVENANCE_NEVER_FLATTENED` requirement.

---

### User Story 4 - Gap-Check Stepless Validation (Priority: P2)

As the Gap-Check stage of the pipeline, I rely solely on the pre-existing `stepless_rule` check to enforce action on the `NEEDS-INVESTIGATION` population without adding any new detection mechanisms. The prompt text simply gains one clarifying sentence explaining what a `stepless_rule` flag means for plan rendering.

**Why this priority**: The design mandates that no new detection path is built. The pipeline must rely on the existing schema and check logic, preventing duplicated logic or duplicate flag types.

**Independent Test**: Can be tested independently by validating that gap-check correctly enforces the stepless rule policy without mutating `write_gap_check_flags` payload shapes and uses only the pre-existing check.

**Acceptance Scenarios**:

1. **Given** a `RELEVANCE-INDEX ENTRY` rule, **When** gap-check runs its pre-existing `stepless_rule` check, **Then** it correctly flags the rule for the `NEEDS-INVESTIGATION` population and the `write_gap_check_flags` payload shape is unchanged.

---

### User Story 5 - Reproducing Worked Example (Priority: P1)

As a feature implementer or tester, I need to verify that my pipeline implementation reproduces the results of the worked example provided in the design document (`hybrid-plan-rendering.md §6`).

**Why this priority**: The worked example (payments-ledger-service, Spring Boot 2.7.18 → 3.2.4, rules r1/r2) provides a known-good baseline to ensure the rendering logic works correctly for both CONCRETE TASK and RELEVANCE-INDEX ENTRY classifications.

**Independent Test**: Run the pipeline against the payments-ledger-service code using the parameters from the worked example and verify the resulting plan rendering matches the expected outputs.

**Acceptance Scenarios**:

1. **Given** the `payments-ledger-service` codebase and an upgrade path of Spring Boot 2.7.18 → 3.2.4, **When** the migration plan is generated for rules r1 and r2, **Then** the output perfectly matches the expected rendering documented in `hybrid-plan-rendering.md §6`.

### Edge Cases

- **Multiple entities per rule with mixed actionability:** When a rule matches multiple entities, and some matches yield actionable tasks while others are uncertain, the classification is evaluated per entity-rule pair. If forced to roll up to the rule level, the most conservative (least actionable) classification wins (e.g., `uncertain` or `incomplete` supersedes `actionable`).
- **BRIDGED_BY where the bridge condition is already satisfied:** Explicitly deferred to backlog. This is an unlikely edge case in the standard sequential flow and can be addressed in a future iteration if observed in practice.
- **Graph updated mid-planning altering a rule's actionability:** Explicitly deferred. The plan stage is sequential and cross-session state changes are already handled by existing context resume mechanisms.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Plan stage MUST classify each matched rule into exactly one of the 5 predefined rendering classifications, or `UNCLASSIFIED` as a fallback when required fields are anomalous or absent.
- **FR-002**: The classification MUST be a pure function of existing fields returned by the graph: `entityClassification`, `steps[]`, `applicability`, and `BRIDGED_BY`.
- **FR-003**: The Plan stage MUST append the resulting classification as a plain-text suffix to the `result_summary` argument of `update_queried_entity` (e.g., identifying it as a task). No parameters of `update_queried_entity` may be added, removed, or renamed. Exact string literals for the suffix are an implementation detail deferred to the plan phase.
- **FR-004**: The Plan stage MUST NOT use the classification to filter rules from being cached. The classification suffix is strictly a non-gating label.
- **FR-005**: The Plan stage MUST NOT mutate the `applicability` field of the `analyze_upgrade_path` response.
- **FR-006**: The Clarify stage MUST strictly enforce that steps created via `add_manual_step` retain `origin="manual"`.
- **FR-007**: The pipeline MUST NEVER allow any stage to rewrite `origin="manual"` to `origin="graph"`, even if community insights later validate the step. This is a hard, irreversible constraint.
- **FR-008**: The Preview stage MUST mandatorily display the `origin` field for every step line-item.
- **FR-009**: The Gap-Check stage MUST rely exclusively on its pre-existing `stepless_rule` check to surface relevance-index candidates to the human. It MUST NOT introduce new checks or alter the `write_gap_check_flags` payload shape.
- **FR-010**: No new node label, relationship type, or property MAY be added to the graph schema (`graph-schema.md`) to satisfy this feature.
- **FR-011**: The `execute` and `feedback` pipeline stages are explicitly OUT OF SCOPE and MUST NOT be modified by this feature, because `execute` already correctly uses existing effort/entity logic for manual steps, and `feedback` already handles deviations correctly.
- **FR-012**: The parameters and return shapes of `update_queried_entity`, `write_gap_check_flags`, `add_manual_step`, and `get_pending_steps` MUST remain exactly as currently contracted. No parameters (like `render_hint`) may be added.
- **FR-013**: The changes MUST only apply to documentation and prompt-text edits in the four specific `.md` files corresponding to the pipeline stages. ZERO application code changes are permitted (no new scripts like `render_classifier.py`, no modifications to `migration_oracle/mcp/tools/` or `migration_oracle/mcp/graph/queries/` code).
- **FR-014**: Severity-bucketing of `stepless_rule` (e.g., distinguishing high/critical from low severity) is explicitly deferred to the backlog and is OUT OF SCOPE for this implementation.
- **FR-015**: If a rule cannot be cleanly classified into one of the 5 predefined outcomes (e.g., required fields like `entityClassification` are null or anomalous), the Plan stage MUST surface the rule to the operator with a fallback classification of `UNCLASSIFIED` and MUST NOT suppress the rule from the cache.

### Key Entities

- **MigrationRule Classification**: The derived render outcome of a migration rule evaluation, computed purely from `entityClassification`, `steps[]`, `applicability`, and `BRIDGED_BY`.
- **MigrationStep Origin**: Identifies if a task was supplied directly by the graph (`origin="graph"`) or by human/LLM heuristic (`origin="manual"`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of matched rules evaluated by the Plan stage are successfully mapped to exactly one of the 5 rendering classifications.
- **SC-002**: 0 changes are made to the graph schema (`graph-schema.md`), MCP tool contracts, or execution handler code. No new parameters are added to any existing MCP tools.
- **SC-003**: 100% of Preview stage outputs visibly include the origin indicator (`graph` or `manual`) for step line-items.
- **SC-004**: 100% of steps converted from relevance-index entries to concrete tasks via `add_manual_step` permanently retain `origin="manual"`.
- **SC-005**: The worked example from `hybrid-plan-rendering.md §6` perfectly reproduces the documented output when tested against the implementation.

## Assumptions

- No code changes are required to the MCP graph engine or tool executors, as this is purely a documentation/prompt-text orchestration change.
- The fields `entityClassification`, `steps[]`, `applicability`, and `BRIDGED_BY` are always reliably returned by `analyze_upgrade_path`.
- The Clarify stage only uses `add_manual_step` for converting relevance-index entries into concrete tasks.
- The pre-existing `stepless_rule` checks in the Gap-Check stage correctly catch relevance-index entries without requiring any adjustments.
- Severity-bucketing of `stepless_rule` is safely deferred to a later iteration without negatively impacting the current hybrid rendering logic.
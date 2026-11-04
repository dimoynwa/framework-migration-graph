# Feature Specification: Migration Research Stage

**Feature Branch**: `018-migration-research-stage`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Adds an optional research stage to the migration harness that persists knowledge-query results (codebase scan, version-map preconditions, full escalation-chain rule results across all four scope tiers, Paysafe dependency resolution, and OpenRewrite recipe discovery) as a structured markdown artifact in the ps-migration/ folder. When /migration-plan runs and finds a valid research artifact, it skips its own knowledge queries and renders directly from the artifact. When no research artifact exists, plan runs its full inline pipeline exactly as it does today — no behaviour change on the default path."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Checkpoint Knowledge Gathering Before Planning (Priority: P1)

As a migration operator, I want to run an optional research stage that gathers all migration knowledge (codebase scan results, version preconditions, rule queries across all scope tiers, dependency resolution, and recipe discovery) and saves it as a structured markdown artifact, so that I can resume or re-plan without repeating expensive knowledge queries from scratch.

**Why this priority**: This is the core value proposition — decoupling knowledge gathering from plan rendering solves interruption recovery, redundant re-querying after clarify, and enables deterministic testing of render logic.

**Independent Test**: Can be fully tested by invoking the research stage on a codebase, verifying that `research.md` is written to the correct migration folder with complete header metadata and per-rule result blocks, without emitting `plan.md`, `tasks.md`, or `verification.md`.

**Acceptance Scenarios**:

1. **Given** a migration request for a specific framework and version range, **When** the research stage completes, **Then** a `research.md` artifact is written to `ps-migration/{framework}-{from}-to-{to}/` containing header metadata (framework, versions, generation timestamp, scan checksum, entity count, rule count, truncation flag), version-map preconditions, scanned entity lists, per-rule result blocks, Paysafe resolution outcomes, and recipe plan data.
2. **Given** an existing `research.md` artifact, **When** the operator runs `/migration-research` again, **Then** the file is overwritten with a fresh scan and updated knowledge queries, without throwing an error about the file already existing.
3. **Given** an operator who never invokes the research stage, **When** they run the plan stage directly, **Then** behaviour is identical to the pre-amendment plan stage except for the `Research: inline` header field in the emitted `plan.md`.

---

### User Story 2 - Plan Consumes Valid Research Artifact (Priority: P1)

As a migration operator who has already run research, I want the plan stage to detect and consume a valid `research.md` artifact — skipping redundant knowledge queries while still running a fresh codebase scan — so that I can generate plan files faster without sacrificing staleness awareness.

**Why this priority**: The research artifact is only valuable if plan can reliably consume it; this is the primary integration point.

**Independent Test**: Can be fully tested by placing a valid `research.md` in the migration folder, running the plan stage, and verifying that plan skips knowledge queries (Steps 3–4 equivalent), reads render inputs from the artifact, still runs the codebase scan, and emits `plan.md`, `tasks.md`, and `verification.md` with `Research:` and `Research-generated:` provenance fields in the plan header.

**Acceptance Scenarios**:

1. **Given** a valid `research.md` whose From/To versions match the current migration request, **When** the plan stage runs, **Then** it skips knowledge queries, reads all render-classification inputs from the research artifact, runs the codebase scan for checksum comparison, and proceeds to render classification and file emission.
2. **Given** a `research.md` whose From/To versions do not match the current request, **When** the plan stage runs, **Then** it falls through to the full inline knowledge-query pipeline with a warning — never silently using stale knowledge.
3. **Given** a `research.md` that is parseable but whose scan checksum differs from the current codebase scan, **When** the plan stage runs, **Then** it warns the operator but does not hard-block — the operator decides whether to re-research or proceed.
4. **Given** a `research.md` older than 7 days, **When** the plan stage runs, **Then** it warns about staleness but does not hard-block, consistent with the existing 7-day staleness policy for plan artifacts.
5. **Given** a `research.md` that is missing, malformed, or fails validation, **When** the plan stage runs, **Then** it falls through to the full inline pipeline with a warning and sets `Research: inline` in the plan header.

---

### User Story 3 - Re-Plan After Clarify Without Redundant Queries (Priority: P1)

As a migration operator who has clarified a plan and needs to re-render plan files, I want to re-run the plan stage using an existing research artifact so that unchanged knowledge is not re-queried, while render classification still uses the current codebase scan for entity-anchor checks.

**Why this priority**: Re-planning after clarify is a common workflow; eliminating redundant graph queries directly addresses the coupling problem described in the feature rationale.

**Independent Test**: Can be fully tested by running research once, then running plan, clarify (amending tasks), and plan again — verifying the second plan invocation reads from `research.md` and does not repeat knowledge queries.

**Acceptance Scenarios**:

1. **Given** a valid `research.md` and an amended `tasks.md` from a clarify session, **When** the operator re-runs plan, **Then** knowledge queries are skipped and only render classification and file emission re-execute.
2. **Given** a re-plan invocation, **When** render classification runs, **Then** it uses the current codebase scan (always executed) for entity-anchor checks even though rule results come from the research artifact.

---

### User Story 4 - Downstream Stages Verify and Display Research Provenance (Priority: P2)

As a reviewer or operator auditing a migration plan, I want gap-check to verify research artifact integrity and preview to display the knowledge source, so that I can trace whether plan knowledge came from a prior research checkpoint or inline queries.

**Why this priority**: Provenance tracking ensures trust in plan outputs without blocking workflows that lack a research artifact.

**Independent Test**: Can be fully tested by running gap-check and preview on a plan that references a research artifact, verifying provenance checks and the knowledge-source display line without any file mutations.

**Acceptance Scenarios**:

1. **Given** a `plan.md` whose header references `Research: ps-migration/{...}/research.md`, **When** gap-check runs, **Then** it verifies the referenced `research.md` still exists, checks truncation-flag consistency between the research artifact and plan, and flags staleness when `Research-generated` is more than 7 days older than `Generated`.
2. **Given** a plan produced from a research artifact, **When** preview runs, **Then** the summary block includes a knowledge-source line showing `research.md` with its generation date.
3. **Given** a plan produced via inline queries, **When** preview runs, **Then** the summary block shows knowledge source as inline queries.
4. **Given** gap-check or preview runs, **When** no `research.md` exists, **Then** neither stage requires or blocks on the research artifact — they operate on `plan.md`, `tasks.md`, and `verification.md` only.

---

### Edge Cases

- What happens when research completes but the operator deletes `research.md` before running plan? Plan falls through to inline queries with a warning.
- What happens when research and plan are run for the same version range but the codebase changed significantly (checksum mismatch)? Plan warns; operator chooses to re-research or proceed with potentially stale rule-to-entity mappings.
- What happens when the research artifact's truncation flag indicates results were capped? Plan and gap-check must surface the same truncation warning as the inline path.
- What happens when research was run with a partial tier failure recorded in the artifact? Plan uses whatever rule results are present in the artifact; gaps are noted identically to inline query failures.
- What happens when an operator runs research twice for the same migration folder? The latest `research.md` overwrites the previous artifact; plan uses the most recent file at detection time.

## Requirements *(mandatory)*

### Functional Requirements

#### Research Stage

- **FR-001**: The system MUST provide an optional research stage entry point (`/migration-research`) that executes the knowledge-gathering portion of the current plan pipeline (preflight, codebase scan, version-map load, multi-tier escalation-chain queries, Paysafe dependency resolution, and OpenRewrite recipe discovery) as a standalone invocation.
- **FR-002**: The research stage MUST write a structured markdown artifact (`research.md`) to `ps-migration/{framework}-{from}-to-{to}/research.md`.
- **FR-003**: The research artifact MUST include header metadata: framework, From/To versions, generation timestamp, scan checksum, entity count, rule count, and truncation flag.
- **FR-004**: The research artifact schema MUST be complete and minimal. It MUST include exactly: (a) all fields the render classification table reads (entityClassification, applicability, full step instruction text, effort, automatable, and the list of matched entity names); (b) all fields file emission reads (preconditions, Paysafe resolution, recipe plan, truncation flag, and deprecation chain details for each matched entity: `deprecated_in`, `removed_in`, `replaced_by`, and `chain completeness status` nested at the per-entity level within the rule block); and (c) header metadata (framework, From/To versions, generation timestamp, scan checksum, entity count, rule count).
- **FR-005**: The research artifact schema MUST NOT carry any unused fields that are not consumed by either render classification or file emission. Unused fields reserved for future use are strictly forbidden to prevent schema drift.
- **FR-006**: The research stage MUST use the same knowledge-query operations as the plan stage's current knowledge-gathering steps. The new `research.md` skill file's `compatibility.tools` frontmatter MUST list exactly the same tools that `plan.md` uses in its Steps 0–4. No missing tools and no extra tools.
- **FR-007**: The research artifact data MUST support the four-way render classification table from the current `plan.md` (TASK, TASK NEEDS-DESIGN-REVIEW, RELEVANCE-INDEX, RELEVANCE-INDEX uncertain). `BRIDGED_BY` MUST be surfaced as instructional text within a TASK, not as a separate fifth outcome.
- **FR-008**: The research stage MUST NOT emit `plan.md`, `tasks.md`, or `verification.md`.
- **FR-009**: The research stage MUST overwrite any existing `research.md` artifact in the target folder without error when invoked multiple times.

#### Plan Stage Amendments

- **FR-010**: The plan stage MUST gain a detection step (Step 1.5) after folder discovery and before knowledge queries that checks for `research.md` in the migration folder.
- **FR-011**: The Step 1.5 detection logic MUST explicitly enumerate and handle all six branches:
  1. `research.md` absent → run full pipeline
  2. version mismatch → warning + run full pipeline
  3. parse failure → warning + run full pipeline
  4. staleness (> 7 days) → warning + operator decides whether to re-research or proceed
  5. checksum mismatch → warning + operator decides whether to re-research or proceed
  6. valid and accepted → skip the version-map load and knowledge query steps (Steps 3–4)
- **FR-012**: When a valid research artifact is accepted, the plan stage MUST skip the version-map load and knowledge query steps (currently Steps 3–4), read all render inputs from the research artifact, and proceed to render classification and file emission.
- **FR-013**: The codebase scan (Step 2) MUST run BEFORE the skip-decision in Step 1.5, not after. The scan produces the checksum that Step 1.5 compares. The skip logic MUST ONLY bypass the version-map and knowledge query steps. The codebase scan is never skipped.
- **FR-014**: On any research artifact validation failure (version mismatch, parse error, missing file), the plan stage MUST fall through to the full inline knowledge-query pipeline with a warning.
- **FR-015**: On scan checksum mismatch or research artifact age exceeding 7 days, the plan stage MUST warn but MUST NOT hard-block — the operator decides whether to re-research or proceed.
- **FR-016**: The plan stage MUST add `Research:` and `Research-generated:` fields to the `plan.md` header for downstream provenance tracking. When a research artifact is consumed, `Research-generated:` MUST be set to the research artifact's generation timestamp. When no research artifact is used, `Research:` MUST be set to `inline` and `Research-generated:` MUST be omitted.
- **FR-017**: The plan stage MUST retain its inline knowledge-gathering steps as a fallback path — they are not removed from the skill documentation.
- **FR-018**: Running `/migration-plan` without a prior `/migration-research` stage MUST produce `plan.md`, `tasks.md`, and `verification.md` output IDENTICAL to the pre-amendment skill, except for the addition of the `Research:` header field. "Identical" means the same rules, same classification, same task order, and same task content. No restructuring of Steps 0–4 may alter the inline path's behaviour.

#### Gap-Check Stage Amendments

- **FR-019**: Gap-check MUST gain a research artifact provenance check that verifies the referenced `research.md` still exists when `plan.md` declares a research source path. Gap-check MUST NOT parse `research.md` beyond its header metadata (i.e. it must not parse the Rule Results section or cross-validate individual rules against `plan.md`'s Rule Ledger).
- **FR-020**: Gap-check MUST read the research artifact's header metadata to verify truncation-flag consistency between the research artifact and `plan.md`.
- **FR-021**: Gap-check MUST flag staleness when `Research-generated` is more than 7 days older than `Generated` in the plan header.
- **FR-022**: No existing gap-check validations MUST change as a result of this feature.

#### Preview Stage Amendments

- **FR-023**: Preview MUST add one display line in the summary block indicating knowledge source (research artifact path with date, or inline queries).
- **FR-024**: Preview MUST remain read-only with zero file mutations.

#### Documentation Deliverables

- **FR-025**: The agent instructions document (`INSTRUCTION.md`) MUST be updated to include the `/migration-research` stage in its stage table, pipeline diagram, and install bundle file list.
- **FR-026**: `migration-file-state-design.md` MUST be updated to document `research.md` in its file inventory (§0) and stage summary (§5).

#### Cross-Cutting Constraints

- **FR-027**: No downstream stage (gap-check, clarify, preview, execute) MUST require `research.md` to exist — only `plan.md`, `tasks.md`, and `verification.md` are required.
- **FR-028**: `research.md` MUST be consumed exclusively by the plan stage's detection step — no other stage reads or writes it.
- **FR-029**: The research artifact MUST be structured markdown, consistent with the `ps-migration/` folder convention — no new file format.
- **FR-030**: There MUST be no changes to `clarify.md` or `execute.md`. This is an explicit integration boundary. Neither stage interacts with `research.md` or plan's knowledge-query pipeline, and they MUST NOT be modified to check research artifact freshness.
- **FR-031**: No knowledge-query operation's parameter list, return shape, or registration MUST change.
- **FR-032**: The codebase scan checksum MUST be computed as the SHA-256 hash of all entity names from all types (FQCNs, annotations, properties, dependencies, npm packages), sorted lexicographically, one per line, newline-delimited, and UTF-8 encoded.
- **FR-033**: The graph schema MUST remain unaffected — no new node labels, relationship types, or properties.

### Key Entities

- **Research Artifact (`research.md`)**: A structured markdown checkpoint capturing all knowledge-gathering outputs for a specific framework version migration. Key attributes: framework, From/To versions, generation timestamp, scan checksum, entity count, rule count, truncation flag, preconditions, entity lists, per-rule results, dependency resolutions, recipe plan. Written by the research stage; read by the plan stage detection step.
- **Plan Header Provenance Fields**: Metadata in `plan.md` tracing knowledge origin. `Research:` holds either `inline` or the path to the consumed `research.md`; `Research-generated:` holds the research artifact's generation timestamp when applicable.
- **Scan Checksum**: A fingerprint of the codebase scan output used to detect whether the codebase has changed since research ran. Computed during both research and plan (plan always re-scans); compared at plan detection time.
- **Per-Rule Result Block**: A structured section within `research.md` capturing one matched migration rule's complete query outcome — sufficient for plan's render classification without re-querying the knowledge source.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators who run research before plan can complete the plan stage without re-executing knowledge queries when the research artifact is valid, reducing plan-stage duration by eliminating redundant query time (measurable by comparing plan runs with and without a valid artifact on the same codebase).
- **SC-002**: Re-planning after clarify with an existing valid research artifact completes without any knowledge queries, while still producing updated `plan.md`, `tasks.md`, and `verification.md` files.
- **SC-003**: Running plan without a prior research stage produces plan output identical to the pre-amendment behaviour (verified by diff comparison of emitted files, excluding the new `Research:` header field).
- **SC-004**: 100% of research artifact validation failures (version mismatch, parse error, missing file) result in graceful fallthrough to the inline pipeline with an operator-visible warning — never silent use of stale or mismatched knowledge.
- **SC-005**: Gap-check correctly flags provenance integrity issues (missing referenced artifact, truncation inconsistency, staleness exceeding 7 days) in plans that declare a research source.

## Assumptions

- The existing plan stage's knowledge-gathering steps (preflight through recipe discovery) are stable and well-defined; the research stage mirrors them exactly without behavioural drift.
- Render classification and file emission can ideally be validated deterministically using a fixture `research.md` plus a fixture codebase scan, without requiring a live knowledge-source connection. This is an architectural benefit, not a strict acceptance test.
- The 7-day staleness threshold for research artifacts aligns with the existing 7-day staleness policy already applied to `plan.md` in the execute stage.
- Operators understand that scan checksum mismatch is a warning, not a block — they are expected to exercise judgment about whether codebase changes invalidate cached rule results.
- Service pack and pre-release version filtering policies (where applicable) are unchanged; research inherits the same version-map and query behaviour as inline plan.
- The `ps-migration/{framework}-{from}-to-{to}/` folder convention remains the canonical location for all migration artifacts.
- Markdown is sufficient as the research artifact format because all sibling artifacts (`plan.md`, `tasks.md`, `verification.md`) are already markdown and the render pipeline already parses markdown structures.
- Clarify and execute stages intentionally have no interaction with research artifacts; any future integration would be a separate feature.

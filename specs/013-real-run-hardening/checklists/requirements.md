# Specification Quality Checklist: Real-Run Hardening

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-14
**Revised**: 2026-06-14 (gap review pass + clarification session + pre-planning fixes)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified (10 edge cases including idempotency and full-catalogue ceiling)
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows (7 user stories, P1–P3)
- [x] Feature meets measurable outcomes defined in Success Criteria (8 SC)
- [x] No implementation details leak into specification

## Gap Review (2026-06-14)

Post-generation review against 10 gaps:

- [x] GAP-001: Issue traceability table added; ISSUE-028 anchored to FR-D06 and SC-008
- [x] GAP-002: FR-A10 added — resolve_version read-only default; stub-MERGE gated behind flag with orphan-node risk noted
- [x] GAP-003: FR-D01 updated with auth_error/transport_error distinct statuses; FR-A11 added for no-candidate resolve_version failure
- [x] GAP-004: FR-B03 and FR-A03 include explicit reconciliation note (identity vs floor/ceil are orthogonal concerns)
- [x] GAP-005: FR-C02 expanded with explicit 6-row routing matrix covering all (recipe × effort × instruction+anchor) combinations
- [x] GAP-006: FR-B04 updated with "server-side reject" language; US3.1 and US3.4 state server enforces, not caller
- [x] GAP-007: FR-C06 updated with Loop IV backlog reference and bridge-done condition; FR-C05 states deferred is distinct from completed/skipped; US5.4 covers resolution condition
- [x] GAP-008: FR-C09 added — blast-radius confirmation gate; US4.6 covers the acceptance scenario
- [x] GAP-009: FR-D05 explicitly lists "abandoned" close status among preserved round-1 contracts
- [x] GAP-010: Three missing edge cases added (idempotent double-create, double-codemod prevention, above-entire-catalogue); FR-B06 and FR-C10 cover the first two

## Pre-Planning Fixes (2026-06-14)

12 gaps identified and resolved before planning:

- [x] SPEC-GAP-001: `updatedAt` added as required MigrationContext property (FR-B07); `get_migration_contexts` returns it; write path defined on every state-changing operation
- [x] SPEC-GAP-002: `deferred` explicitly an additive STEP_OUTCOME extension; `update_step_status` named as writer; FR-D05 changed to "extended, not broken"
- [x] SPEC-GAP-003: "resume"/"resume_migration" replaced throughout by `create_migration_context` match path; `ON MATCH SET` owns the allow-list refresh and `droppedCount`
- [x] SPEC-GAP-004: "resolved recipe" defined (`rec IS NOT NULL AND auto=true AND missingRequiredParams=[]`); routing table gains "partially resolved → prompted-auto" row; table is now 7 rows
- [x] SPEC-GAP-005: FR-B01 returns outcome-counts from STEP_OUTCOME (completed/failed/skipped/deferred); "total" and "pending" dropped — they belong to `get_pending_steps`
- [x] SPEC-GAP-006: FR-B06 echoes resolved `UPGRADES_TO` version string, `rounded`, and `aheadOfCatalogue` flags in the `create_migration_context` response
- [x] SPEC-GAP-007: FR-C11 added — bridge discoverability is a hard precondition; non-graph-catalogued bridges are rejected
- [x] SPEC-GAP-008: FR-A12 added — Boot-Cloud boundary alert is a behavioral requirement; ISSUE-024 fully covered
- [x] SPEC-GAP-009: Traceability fixed — ISSUE-021 now cites FR-C05, FR-C06, FR-C11 (removed incorrect FR-C09 reference)
- [x] SPEC-GAP-010: US1.1 and US1.3 updated to use `exists_in_graph: true` (the real field name from `check_version_availability`)
- [x] SPEC-GAP-011: FR-B08 added — concurrent-resume conflict detection required; second caller receives conflict error
- [x] SPEC-GAP-012: FR-A07 updated — `resolve_version` runs before dedup in `submit_migration_insight`; on resolution failure dedup is skipped and failure is returned directly

## Notes

All checklist items pass. Spec is ready for `/speckit-plan`.

# Specification Quality Checklist: Oracle Contract Fixes

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-06-13
**Revised**: 2026-06-13 (gap review); 2026-06-13 (blocking/should-fix/minor review)
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
- [x] Edge cases are identified (all decided, none left as either/or)
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Review Pass 1 — Gap Review (2026-06-13)

| Gap | Resolution |
|-----|------------|
| GAP-001 | FR-001: explicit "one formula"; graph-schema.md MUST NOT be edited |
| GAP-002 | FR-002: both tables, every row, inversion as formula-level property |
| GAP-003 | FR-005/006: additive contract + idempotency as stated behaviour |
| GAP-004 | FR-008: severity ordering + "at or above" inclusion direction |
| GAP-005 | FR-009: per-step join; empty-list vs. missing-edge distinction |
| GAP-006 | FR-010–013: Cypher AND Returns table must agree; submit-insight 3 paths explicit |
| GAP-007 | FR-014/015: DESIGN GATE flags added |
| GAP-008 | FR-016: new skill resource; install_migration_skill must include it |
| GAP-009 | FR-018 (new): error shapes preserved |
| GAP-010 | FR-019 (new): execute_custom_cypher read-only enforced |

## Review Pass 2 — Blocking/Should-fix/Minor (2026-06-13)

| # | Category | Resolution |
|---|----------|------------|
| 1 | BLOCKING | Inversion test reframed as `f(3,10,0) > f(3,9,0)` formula property — not table-row lookup. Fixed in US1 Independent Test, Acceptance Scenario 2, FR-002, SC-001. |
| 2 | BLOCKING | Issue numbering unified to body numbering (001–015); FR→ISSUE traceability table added to Requirements. Input line updated. Assumptions clarified. |
| 3 | SHOULD-FIX | Priority rationale added to US4, US6, US7: blast-radius criterion explained for each HIGH issue rated P2/P3. |
| 4 | SHOULD-FIX | FR-008 and FR-009 implementation detail removed: integer ranks and literal Cypher path moved to "plan/contract detail"; behavioural statements retained. |
| 5 | SHOULD-FIX | SC-015 (NO_REGRESSION) added: existing test suite must stay green. |
| 6 | SHOULD-FIX | US2 Scenario 3: "number of calls" corrected to "number of distinct (context, step) pairs". |
| 7 | MINOR | Unrecognised `severity_threshold` edge case decided: reject with documented error shape (no silent fallback). |
| 8 | MINOR | US5 Independent Test expanded to cover all three defects including submit_migration_insight dedup path. |
| 9 | MINOR | Concurrency out-of-scope stated in Assumptions (last-write-wins); issue-numbering convention declared. |

## Notes

- 19 FRs (FR-001–FR-019), 15 SCs (SC-001–SC-015) after both review passes
- 2 DESIGN GATE items (FR-014, FR-015) flagged for resolution in `/speckit-plan`
- Spec is ready for `/speckit-plan`

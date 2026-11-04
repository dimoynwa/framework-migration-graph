# Data Model: linear-file-migration-state

**Note**: The canonical template texts for `plan.md`, `tasks.md`, and `verification.md` reside in `migration_oracle/mcp/skills/templates/` and MUST conform exactly to the authoritative shapes outlined in this document. Any schema changes here MUST be mirrored in the templates.

## File Schemas (Authoritative Shape)

### 1. `plan.md`
**Structure**: Header, Preconditions, Scope-Order, Dependency, Recipe, Drift-Rule, and Rule Ledger.

**Header Fields**:
- `Generated`: ISO 8601 date string. Used by `execute` for the 7-day staleness check.
- `Project`: Absolute path to `PROJECT_ROOT`. Required for resumption.
- `Framework`: The framework being migrated (e.g., `spring-boot`).
- `From to To`: The version transition (e.g., `2.7.18 to 3.2.0`).
- `Graph snapshot`: Knowledge-version element ID. Anchors the drift-detection provenance trail.

**Rule Ledger Columns**:
1. `RuleID`
2. `Scope`
3. `EntityMatched`
4. `classification`
5. `applicability`
6. `Render`
7. `tasks.md`

### 2. `tasks.md`

**File-Level Header**:
```markdown
HIGH: {n} MEDIUM: {n} LOW: {n} Relevance-index: {n}
```

**Agent Instructions Block** (Mandatory file-level constraint block):
```markdown
## Instructions for Code Agent
1. Work tasks strictly in sequential order (TASK-001..NNN).
2. Build ONCE at the end via verification.md. Fix forward; do not revert tasks.
3. Search before skipping. The Paysafe constraint is absolute: never downgrade `com.paysafe.*`.
4. Update Status inline as you go.
```

**Task Block Fields**:
- `Status`
- `Derives-from`
- `Origin`
- `Executor`
- `Recipe`
- `Effort`
- `File pattern`
- `Instructions`
- `Before/After`
- `Verify`

**Relevance-Index Entry Shape**:
Each Relevance-Index entry MUST contain the following fields to be resolvable by the `clarify` stage:
- `ID`: Sequence identifier (e.g., `RI-001`).
- `RuleID`: The identifier from the knowledge graph.
- `Description`: Summary of what affects the codebase.
- `Applicability`: Reason it fell into the index (e.g., `uncertain` or `incomplete`).
- `Disposition`: Resolution line (e.g., `awaiting clarify` or `dismissed: [reason]`).

### 3. `verification.md`
**Structure (Levels 0-5)**:
- **Level 0**: Static residue check (no build required).
- **Level 1**: Clean build (pass criterion: exit 0).
- **Level 2**: Unit tests (pass criterion: exit 0).
- **Level 3**: Integration tests (pass criterion: exit 0).
- **Level 4**: App starts + health check (pass criterion: UP).
- **Level 5**: Constraints and provenances (Gate 5-A/B/C).
  - **Gate 5-A**: Paysafe constraint.
  - **Gate 5-B**: Tasks verification (zero pending/failed + explicit human sign-off on needs-review).
  - **Gate 5-C**: Relevance-Index resolution.

## Enums

### Executor Enum (Closed Enum)
Valid execution routing strategies for tasks:
- `openrewrite`
- `prompted-auto`
- `agent-codemod`
- `human-review`

### Status Enum (Closed Enum)
Valid states for a `TASK` in `tasks.md`:
- `pending`
- `done`
- `failed`
- `needs-review`

### Render Outcomes (Closed Enum)
Valid mappings for matched rules:
1. Actionable + ≥1 non-empty MigrationStep + matched entity ⇒ **TASK**
2. Actionable + ≥1 non-empty MigrationStep + matched entity BUT effort=architectural OR generic/templated instruction ⇒ **TASK** flagged **NEEDS-DESIGN-REVIEW**
3. `entityClassification=incomplete` (AFFECTS_* edges, no REQUIRES_STEP) ⇒ **RELEVANCE-INDEX**
4. `applicability=uncertain` (safety-net match) ⇒ **RELEVANCE-INDEX** labeled **uncertain**

## Graph Node/Relationship Changes

### DELETED Graph Entities
- `MigrationContext` (Node)
  - Properties removed: `contextId`, `framework`, `fromVersion`, `toVersion`, `status`, `createdAt`, `updatedAt`, `totalSteps`, `pendingSteps`, `completedSteps`, `failedSteps`, `deferredSteps`
  - Relationships removed from this node: `STEP_OUTCOME`, `INCLUDES_RULE`, `HAS_QUERIED_ENTITY`
- `STEP_OUTCOME` (Relationship from `MigrationContext` to `MigrationStep`)
  - Properties removed: `status`, `reason`, `updatedAt`, `resolvedVia`, `bridgeResolvedAt`
- Queried-entity cache (Properties on `MigrationContext` or `HAS_QUERIED_ENTITY` edges tracking pre-resolved entities)

### RETAINED Graph Entities
- `Version`
- `MigrationRule`
- `MigrationStep`
- `OpenRewriteRecipe`
- `Class`
- `ApplicationProperty`
- `Dependency`
- `community-insight` (rules)
- `BRIDGED_BY` (relationship)

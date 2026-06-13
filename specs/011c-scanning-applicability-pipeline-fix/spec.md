# Feature Specification: Scanning & Applicability Pipeline Fix

**Feature Branch**: `011c-scanning-applicability-pipeline-fix`

**Created**: 2026-06-12

**Status**: Draft

**Source**: [`GAPS.md`](GAPS.md) — five compounding defects identified by static code review
and cross-validated against the live server on 2026-06-12.

## Overview

Migration plans produced by the server are **silently incomplete**. Rules that
genuinely apply to a project are omitted because of a broken applicability
pipeline spanning the scan contract, the matching predicate, and the execution
queue. Five defects compound each other:

1. **Substring matching** (`CONTAINS`) produces false positives for short tokens
   and misses FQCNs longer than stored graph names — the most common scan output.
2. **Broken scan contract** — `scannedEntities` on `MigrationContext` is a flat
   untyped list; `get_pending_steps` applies no entity filter at all, so the plan
   the developer reviews and the steps they execute come from different rule sets.
3. **No safety net** — `high`/`critical` rules with no entity match are silently
   dropped instead of flagged as `"uncertain"`.
4. **Silent output truncation** — the `top_n=50` cap drops applicable rules with no
   indication in the response.
5. **Dead code / doc mismatch** — `hydrate_nodes` traverses a non-existent
   `DISCOVERED_IN` relationship; `search_openrewrite_recipes` docstring contradicts
   the implementation for `only_composite` / `require_no_params`.

A false negative on a breaking change is far costlier than a false positive. This
spec prioritises completeness and visibility over noise reduction.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent Receives the Correct Applicable Rule Set (Priority: P1)

A developer's agent scans `paysafe-wallet-switch` and obtains 1444 entities (1431
class names, 6 artifact IDs, 7 property keys). It calls `analyze_upgrade_path`
with those entities. Previously, rules whose stored entity names were longer than
the scanned short names — or whose stored names appeared as substrings of unrelated
scanned tokens — were silently mis-classified. After this fix, each entity kind is
matched at the correct tier (FQCN-to-FQCN strong, FQCN-to-simple weak,
groupId:artifactId strong, artifactId-only weak, property exact) and the returned
`applicability` values are accurate.

**Why this priority**: Incorrect applicability is the root cause of incomplete
migration plans. Every other improvement builds on this.

**Independent Test**: Call `analyze_upgrade_path` with entities that are known to
match graph nodes only via the weak tier (scanned simple name, stored FQCN) and
verify `applicability = "matched"` and `matched_entities` is non-empty. Repeat
with entities known to be false-positive substring matches under the old logic
and verify they are no longer matched.

**Acceptance Scenarios**:

1. **Given** a rule linked to `e.name = "org.springframework.web.client.RestTemplate"` and `scanned_class_simple = ["RestTemplate"]`, **When** `analyze_upgrade_path` is called, **Then** the rule has `applicability = "matched"` and `matched_entities = ["org.springframework.web.client.RestTemplate"]`.
2. **Given** a rule linked to `e.name = "spring-boot-starter-web"` and `scanned_dep_artifacts = ["web"]`, **When** `analyze_upgrade_path` is called, **Then** the rule is **not** matched (short token `"web"` is not a valid artifact-only match for `"spring-boot-starter-web"`).
3. **Given** a rule linked to `e.name = "org.springframework.boot:spring-boot-starter-data-redis"` and `scanned_deps_ga = ["org.springframework.boot:spring-boot-starter-data-redis"]`, **When** `analyze_upgrade_path` is called, **Then** the rule has `applicability = "matched"` via the strong dependency tier.
4. **Given** a rule with no entity links, **When** `analyze_upgrade_path` is called with any entities, **Then** `applicability = "informational"` and `universally_applicable = true`.

---

### User Story 2 — Agent Never Misses a Breaking Change (Priority: P1)

The agent calls `analyze_upgrade_path` for a project whose entity scan misses the
exact form of a `critical`-severity rule's affected entity. Previously that rule was
silently dropped. After this fix, the rule is returned with
`applicability = "uncertain"`, signalling the developer must manually confirm
whether it applies rather than having the system silently decide it does not.

**Why this priority**: Silent omission of critical/high rules is the highest-risk
consequence of the defects. The safety net is a hard contract.

**Independent Test**: Call `analyze_upgrade_path` with entity sets that do not match
any affected entity of a known `critical` rule; verify the rule appears in the
response with `applicability = "uncertain"`, not absent.

**Acceptance Scenarios**:

1. **Given** a `critical` rule linked to entity `"spring-security-oauth2-authorization-server"` and `scanned_dep_artifacts = ["unrelated-artifact"]`, **When** `analyze_upgrade_path` is called, **Then** the rule is returned with `applicability = "uncertain"` (not absent).
2. **Given** a `high` rule with no entity match, **When** `analyze_upgrade_path` is called, **Then** it is returned with `applicability = "uncertain"` and `matched_entities = []`.
3. **Given** a `medium` rule with no entity match, **When** `analyze_upgrade_path` is called, **Then** it is **not** returned (medium rules below the safety net threshold are excluded when unmatched).
4. **Given** `analyze_upgrade_path` is called with `user_entities = []`, **Then** all rules are returned — `informational` for no-entity rules, `uncertain` is not used when there is no scan to disagree with.

---

### User Story 3 — Execution Queue Matches the Reviewed Plan (Priority: P1)

A developer reviews the plan from `analyze_upgrade_path` (entity-filtered), then
calls `get_pending_steps` to start executing. Previously the execution queue was
completely unfiltered — it included steps for rules excluded from the plan. The
developer was presented with work items they had already determined did not apply.
After this fix, `get_pending_steps` applies the same per-kind exact matching
(sourced from `ctx.scannedClasses` etc. on the `MigrationContext`) so the plan
and the execution queue are consistent.

**Why this priority**: Plan/queue divergence breaks the core orchestration loop:
excluded rules re-appear as pending steps, creating a retry cycle.

**Independent Test**: Create a context, call `analyze_upgrade_path` to get the
filtered rule set, then call `get_pending_steps`; verify the set of `rule_id`
values in the step queue is a subset of the rule IDs returned by
`analyze_upgrade_path` (no rule_id in steps that was excluded from the plan).

**Acceptance Scenarios**:

1. **Given** a context with `scannedClasses = ["org.springframework.web.client.RestTemplate"]`, **When** `get_pending_steps` is called, **Then** only steps whose parent rule matches `RestTemplate` (or is `informational`/`uncertain`) are returned; steps for unrelated rules are absent.
2. **Given** a context created before this spec (no `scannedClasses` property), **When** `get_pending_steps` is called, **Then** it returns all steps (unfiltered fallback; existing behaviour preserved for legacy contexts).
3. **Given** a `high` rule with no entity match in the context scan, **When** `get_pending_steps` is called, **Then** its steps are returned with `applicability = "uncertain"`.
4. **Given** a rule excluded by entity filter (`applicability = "excluded"`), **When** `get_pending_steps` is called, **Then** its steps are **not** returned.

---

### User Story 4 — Agent Sees Diagnostics When Rules Are Excluded (Priority: P2)

The agent calls `analyze_upgrade_path` and receives 12 rules. It also receives a
`diagnostics` block showing 180 rules were evaluated, 164 excluded by entity
filter, and 4 included via the safety net. The developer can immediately see the
plan is based on a narrow entity scan and decide to broaden it rather than
assuming the 12 rules are exhaustive.

**Why this priority**: Diagnostics are the primary observability mechanism for the
filtering pipeline. Without them, under-inclusive plans are indistinguishable from
complete ones.

**Independent Test**: Call `analyze_upgrade_path` with a narrow entity list and
verify the `diagnostics` block is present and that
`rules_included + rules_excluded_by_entity_filter + rules_via_safety_net` equals
the total rules evaluated in the version range.

**Acceptance Scenarios**:

1. **Given** a call with `user_entities` non-empty, **When** `analyze_upgrade_path` returns, **Then** the response contains a `diagnostics` object with fields `scanned_total`, `matched_entities`, `unmatched_entities`, `rules_included`, `rules_excluded_by_entity_filter`, `rules_via_safety_net`.
2. **Given** a call with `user_entities = []` (no filter), **When** `analyze_upgrade_path` returns, **Then** `diagnostics` is absent or `null` (no filtering happened).
3. **Given** the `top_n` limit is reached, **When** `analyze_upgrade_path` returns, **Then** `diagnostics` includes `"rules_capped_at": <top_n>`.
4. **Given** `build_recipe_plan` is called with `user_entities` non-empty, **Then** the response also includes the same `diagnostics` structure.

---

### User Story 5 — Search Returns Correct Version Links (Priority: P3)

The agent calls `search_migration_knowledge` and expects hits to be filtered by
the requested `framework`. Previously `hydrate_nodes` traversed both
`INCLUDES_RULE` and the non-existent `DISCOVERED_IN` relationship. After this fix,
only `INCLUDES_RULE` is traversed (the only type written by ingestion), removing
a dead code path that could become a correctness hazard if the schema evolves.

**Why this priority**: No observable behaviour change today; correctness risk and
code clarity. Low priority.

**Independent Test**: Confirm `search_migration_knowledge` returns the same hits
before and after the `DISCOVERED_IN` removal (behaviour must be unchanged).

**Acceptance Scenarios**:

1. **Given** `MigrationRule` nodes linked via `INCLUDES_RULE` to a `Version`, **When** `search_migration_knowledge(framework="Spring Boot")` is called, **Then** the same rules are returned as before the change (no regression).
2. **Given** no `DISCOVERED_IN` relationships exist in the graph, **When** `hydrate_nodes` is executed, **Then** the OPTIONAL MATCH on `INCLUDES_RULE` alone produces the same result as the previous `INCLUDES_RULE|DISCOVERED_IN` form.

---

### Edge Cases

- `analyze_upgrade_path` with `user_entities` containing both FQCNs and simple
  names for the same class → the strong tier matches (FQCN), `matched_entities`
  contains the FQCN, no duplicate entry.
- `scanned_deps_ga` entry with trailing version (`"org.springframework.boot:spring-boot-starter-web:3.5.0"`) → split on `:` and use only `[0]+":"+[1]`; version segment is discarded.
- `create_migration_context` called a second time for the same triple (resume) → `ON MATCH SET` must update the five kind-separated arrays so a broader re-scan is reflected.
- Context with all five `scanned*` arrays empty (legacy or entity-free scan) → `get_pending_steps` returns all steps unfiltered; `diagnostics.scanned_total = 0`.
- `top_n` cap applied after safety-net uncertain rules → `uncertain` rules survive truncation; `matched` and `informational` fill remaining slots by severity.
- `search_openrewrite_recipes` called with `only_composite=True` → filter IS applied; docstring update must reflect this accurately.

---

## Requirements *(mandatory)*

### Functional Requirements

**Per-kind exact matching — `analyze_upgrade_path` and `build_recipe_plan`**

- **FR-001**: The `$user_entities` flat-list parameter MUST be replaced in both
  `_ANALYZE_UPGRADE_PATH` and `_BUILD_RECIPE_PLAN` Cypher queries with five typed
  parameters: `$scanned_classes` (FQCN list), `$scanned_class_simple` (simple name
  list), `$scanned_deps_ga` (`groupId:artifactId` list), `$scanned_dep_artifacts`
  (bare artifactId list), `$scanned_props` (dotted property key list).
- **FR-002**: The `CONTAINS`-based predicate MUST be replaced with the per-kind
  exact matching table defined in GAPS.md §4: strong-tier (`IN`) and weak-tier
  (`last(split(…)) IN`) as specified in research Spike 1. No `CONTAINS` predicate
  may remain in the entity-matching path.
- **FR-003**: The Python tool layer MUST normalize the caller-supplied
  `user_entities` list into the five typed buckets before passing them to the query
  functions, using the rules in GAPS.md §3. The tool's public signature
  (`user_entities: list[str]`) is unchanged; normalization is internal.
- **FR-004**: The Python `_enrich()` post-processor in `upgrade.py` MUST be
  removed. Applicability (`matched` / `informational` / `uncertain` / `excluded`)
  MUST be computed entirely inside the Cypher `WITH` chain and returned directly
  in the `applicability` column. Python only forwards the value.

**Breaking-change safety net**

- **FR-005**: A rule whose minimum `BreakingScope.severity` (via `HAS_SCOPE`) is
  `"high"` or `"critical"` and whose entity-match count is zero MUST be returned
  with `applicability = "uncertain"`. It MUST NOT be excluded silently.
- **FR-006**: A rule with no `HAS_SCOPE` edge at all and no entity links MUST be
  returned with `applicability = "informational"` (universally applicable).
- **FR-007**: A rule with entity links but no match and severity below `"high"`
  (`sev_rank > 1`) MUST be classified `"excluded"` and filtered from the response.
  The count of such rules MUST appear in `diagnostics.rules_excluded_by_entity_filter`.

**Kind-separated entity storage on `MigrationContext`**

- **FR-008**: `create_migration_context` MUST write five new primitive-array
  properties on the `MigrationContext` node at creation time:
  `scannedClasses`, `scannedClassSimple`, `scannedDepsGa`, `scannedDepArtifacts`,
  `scannedProps`. These are populated by normalizing the `scanned_entities` input
  before the Cypher write.
- **FR-009**: `ON MATCH SET` in `_CREATE_OR_GET_CONTEXT` MUST update all five
  arrays so a resumed context reflects a broader re-scan.
- **FR-010**: The existing `scannedEntities` flat-list property MUST be retained
  for backwards compatibility but is no longer read by any query tool.

**`get_pending_steps` entity filter**

- **FR-011**: `_GET_PENDING_STEPS` MUST apply the per-kind exact matching logic
  (Spike 4 / GAPS.md §6.3) reading from `ctx.scannedClasses`,
  `ctx.scannedClassSimple`, `ctx.scannedDepsGa`, `ctx.scannedDepArtifacts`,
  `ctx.scannedProps` on the context node.
- **FR-012**: Steps belonging to `"excluded"` rules MUST NOT be returned. Steps
  belonging to `"uncertain"` rules MUST be returned with `applicability = "uncertain"`.
  Steps belonging to `"matched"` and `"informational"` rules are returned as today.
- **FR-013**: When all five `scanned*` arrays are absent or empty on the context
  node (legacy contexts), `get_pending_steps` MUST return all steps without filtering
  (identical to current behaviour). No error is raised.
- **FR-014**: The `_pending_step()` response dict in `tools/context.py` MUST include
  `applicability` forwarded from the Cypher result.

**Coverage diagnostics**

- **FR-015**: When `user_entities` is non-empty, `analyze_upgrade_path` MUST include
  a `diagnostics` object in its response with fields:
  - `scanned_total` (int): count of unique entities passed after normalization.
  - `matched_entities` (list[str]): entity names that hit at least one rule.
  - `unmatched_entities` (list[str]): entity names that hit no rule.
  - `rules_included` (int): rules returned (`matched` + `informational` + `uncertain`).
  - `rules_excluded_by_entity_filter` (int): rules dropped (`excluded`).
  - `rules_via_safety_net` (int): rules returned with `applicability = "uncertain"`.
- **FR-016**: When `user_entities` is empty, `diagnostics` MUST be `null` in the
  response.
- **FR-017**: When the `top_n` cap truncates the rule list, `diagnostics` MUST
  include `rules_capped_at: <top_n>`. Rules surviving the cap MUST be ordered:
  `uncertain` first (by descending severity), then `matched` (by descending severity),
  then `informational` — so high-priority rules survive truncation.
- **FR-018**: `build_recipe_plan` and `get_pending_steps` MUST include the same
  `diagnostics` structure under the same conditions.

**Dead code removal**

- **FR-019**: `hydrate_nodes` in `migration_oracle/mcp/graph/queries/search.py:75`
  MUST remove `DISCOVERED_IN` from the relationship traversal. The correct form is
  `(n)-[:INCLUDES_RULE]-(v:Version)` only.

**Docstring correction**

- **FR-020**: The `search_openrewrite_recipes` tool docstring in
  `migration_oracle/mcp/tools/search.py` MUST be updated to accurately state that
  `only_composite` and `require_no_params` filters are applied at the Cypher layer,
  removing the incorrect "not yet applied" language.

### Key Entities

- **MigrationContext**: After this fix carries five new primitive-array properties
  (`scannedClasses`, `scannedClassSimple`, `scannedDepsGa`, `scannedDepArtifacts`,
  `scannedProps`) in addition to the existing flat `scannedEntities`.
- **MigrationRule**: Unchanged schema; the applicability classification now happens
  in Cypher rather than Python.
- **BreakingScope**: `severity` field drives the safety-net threshold (`"high"` /
  `"critical"` → `sev_rank <= 1`). Already linked via `HAS_SCOPE`.
- **Class / ApplicationProperty / Dependency**: Targets of
  `AFFECTS_CLASS` / `AFFECTS_PROPERTY` / `AFFECTS_DEPENDENCY` edges from rules.
  The matching predicate changes; the node schema does not.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `analyze_upgrade_path` returns `applicability = "matched"` for a rule
  whose affected entity FQCN has only its simple name in `scanned_class_simple`
  (weak-tier match confirmed). Zero false negatives for the weak-tier path.
- **SC-002**: No `high` or `critical` rule is absent from the `analyze_upgrade_path`
  response regardless of entity match; it appears with `applicability = "uncertain"`
  when unmatched.
- **SC-003**: Every `rule_id` present in the `get_pending_steps` queue is also
  present in the `analyze_upgrade_path` response for the same context (plan and
  execution queue are consistent).
- **SC-004**: `get_pending_steps` returns the same rule set as before this spec
  for legacy contexts (no `scanned*` arrays present on context node).
- **SC-005**: Every `analyze_upgrade_path` response with a non-empty `user_entities`
  input includes a `diagnostics` block where
  `rules_included + rules_excluded_by_entity_filter` equals the total matching
  rules for the version range (before the `top_n` cap).
- **SC-006**: When `top_n` truncates the result, `uncertain` rules are present in
  the returned list and `diagnostics.rules_capped_at` is set.
- **SC-007**: `search_migration_knowledge` returns identical hits before and after
  the `DISCOVERED_IN` removal (no regression on search results).
- **SC-008**: `search_openrewrite_recipes` docstring no longer contains "not yet
  applied"; the tool behaves as described.
- **SC-009**: All Cypher and Python changes are covered by tests. The following new
  test files are required:
  - `tests/mcp/test_analyze_upgrade_path_matching.py` — FR-001–FR-007 (per-kind
    exact matching: strong/weak tiers, safety-net uncertain, medium excluded,
    informational for no-entity rules).
  - `tests/mcp/test_context_entity_filter.py` — FR-008–FR-014 (kind-separated
    arrays written at create time, updated on resume, `get_pending_steps` filters
    by context arrays, uncertain steps returned, legacy contexts unfiltered).
  - `tests/mcp/test_diagnostics.py` — FR-015–FR-018 (diagnostics present when
    entities non-empty, null when no entities, rules_capped_at set on truncation,
    ordering: uncertain → matched → informational).

## Assumptions

- The graph stores `MigrationRule` entity links via `AFFECTS_CLASS`,
  `AFFECTS_PROPERTY`, `AFFECTS_DEPENDENCY` edges and `BreakingScope` severity via
  `HAS_SCOPE`. These relationships are present; this spec does not add new node
  labels or relationship types to the schema.
- `Class.name` is stored in FQCN form in the graph for all rules that benefit from
  strong-tier matching. If a class was ingested as a simple name, weak-tier matching
  handles it.
- `Dependency.name` is stored in `groupId:artifactId` form (no version) for strong
  tier and bare `artifactId` for weak tier. Spec 011b covers any gaps in this
  assumption.
- The `top_n` default of 50 is retained; the diagnostic `rules_capped_at` field
  makes the cap observable without changing the limit.
- APOC is unavailable (Neo4j Community); all new state on `MigrationContext` uses
  primitive arrays.
- The `user_entities` normalization in FR-003 is best-effort: the tool accepts
  mixed forms (FQCNs, simple names, artifact coordinates, property keys) and
  distributes them to the appropriate typed bucket by heuristic (dot-separated with
  uppercase segments → likely FQCN, colon-separated → dependency, dot-separated
  lowercase → property key). A bucket may be empty; that is valid.
- Spec 011b (`analyze-upgrade-path-entity-matching`) addresses the graph-side data
  gaps (missing entity nodes) that would prevent even correct matching from finding
  hits. 011c fixes the matching predicate and contract; 011b fixes the data. Both
  are required for full plan completeness.

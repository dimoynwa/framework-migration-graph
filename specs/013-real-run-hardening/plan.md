# Implementation Plan: Real-Run Hardening

**Branch**: `013-real-run-hardening` | **Date**: 2026-06-14 | **Spec**: [spec.md](spec.md)

---

## Summary

Hardens the Migration Oracle MCP server (Python 3.12 / mcp ≥ 1.0 / Neo4j 5) and the four-loop harness skill against the 15 failure modes discovered during the first real migration run. The primary fixes are: unifying version resolution into a single shared routine (eliminating the `to_minor_zero` patch-truncation bug that caused ISSUE-017), adding `get_migration_contexts` for context discovery, enforcing the allow-list on the MERGE match path, routing recipe-less mechanical steps to an agent-applied codemod executor, tracking sanctioned bridges as deferred STEP_OUTCOME entries, classifying Paysafe resolver failures as `auth_error` vs `transport_error`, and making the grep-based scanner portable across macOS/BSD and GNU/Linux.

---

## Technical Context

**Language/Version**: Python 3.12 (requires `>=3.11` per `pyproject.toml`)  
**MCP runtime**: `mcp>=1.0` (FastMCP transport layer)  
**Primary Dependencies**: `neo4j>=5.0`, `mcp>=1.0`, `pydantic>=2.0`, `packaging>=24.0`  
**Storage**: Neo4j 5.x (Docker image `neo4j:5`); graph schema with Version, MigrationRule, MigrationStep, MigrationContext, BreakingScope, Dependency, OpenRewriteRecipe labels  
**Testing**: `pytest>=8.0` with `pytest-asyncio`, `pytest-mock`  
**Target Platform**: Linux container (Docker Compose); developer machines: macOS/BSD and GNU/Linux  
**Performance Goals**: Tool latency p95 < 500ms (Neo4j-bound); scanning within Claude context window  
**Constraints**: No new build tooling; rollback uses VCS working tree only; OpenRewrite is optional  
**Project Type**: MCP server (JSON-over-HTTP/stdio) + four-loop harness skill (Markdown)

---

## Constitution Check

Constitution is a blank template — no governance gates apply. All implementation decisions default to the spec's explicit requirements and the existing codebase patterns.

---

## Project Structure

### Documentation (this feature)

```text
specs/013-real-run-hardening/
├── plan.md              ← this file
├── spec.md
├── research.md          ← Phase 0
├── data-model.md        ← Phase 1
├── quickstart.md        ← Phase 1
└── contracts/
    ├── get_migration_contexts.md
    ├── resolve_version_delegation.md
    ├── agent_codemod_executor.md
    ├── loop3_executor_selection.md
    └── paysafe_auth_error.md
```

### Source Code (affected paths)

```text
migration_oracle/
├── models/graph.py                         # A: VersionResolutionResult/Failure dataclasses added; sortable_version unchanged
├── graph/indexes.py                        # no new indexes required
├── mcp/
│   ├── graph/queries/
│   │   ├── upgrade.py                      # A: resolve_version routine added here
│   │   └── context.py                      # B: updatedAt, deferredSteps, get_migration_contexts Cypher
│   ├── tools/
│   │   ├── upgrade.py                      # A: delegate to resolve_version; remove to_minor_zero calls
│   │   ├── context.py                      # B: get_migration_contexts tool, droppedCount, updatedAt
│   │   └── paysafe.py                      # D: auth_error / transport_error pass-through
│   ├── skills/
│   │   ├── framework_migration_main.md     # B: Loop I step 1+supersede flow; C: routing table; D: Loop II fallback; D: query→execute
│   │   ├── framework_migration_version_map.md  # A: Spring Cloud table + calendar normalization; Boot 4.0.6
│   │   └── framework_migration_scanning.md     # E: Python-canonical scanner + grep fast path + PyYAML degrade
│   └── paysafe/
│       └── resolver.py                     # D: map 401/403/timeout → auth_error/transport_error

docs/graph-schema.md                        # schema additions: updatedAt, deferredSteps, typed entity buckets,
                                            #   queriedEntities, BRIDGED_BY rel, deferred STEP_OUTCOME status
```

---

## Parallelism

The five workstreams have these dependencies:

```
A (version resolution) ──► B (context lifecycle — needs ceil-node linking in create_migration_context)
A                       ──► C (execution routing — resolve_version needed before routing runs)
D (orchestration)       — independent of A, B, C
E (scanning)            — independent of A, B, C, D
```

**Parallel-safe groupings**:
- **Group 1 (independent)**: E (scanning portability) + D (orchestration/paysafe error classification)
- **Group 2 (after A)**: B (context lifecycle) + C (execution routing)
- **Group 3 (skill edits, independent)**: Spring Cloud version-map delta + Loop II hand-off + agent-codemod skill section

Workstream A must be completed before B and C begin. E and D can run concurrently with A.

---

## Phase 0: Research (complete)

See [research.md](research.md). All unknowns resolved:
- Runtime: Python 3.12 / mcp ≥ 1.0
- Bridge model: `(:MigrationRule)-[:BRIDGED_BY]->(:Dependency)` relationship
- Scanning portability: Python scanner is canonical; `grep -E` is optional fast path
- Spring Cloud train table: 6 trains, 2025.1.x Oakwood is BOM-only
- Loop II hand-off: `query_handoff_threshold` integer, default 0
- `updatedAt`: all four state-changing Cypher writes
- Concurrent conflict: ConstraintValidationFailed → conflict_error

---

## Phase 1: Implementation

### Workstream A — Version Resolution (blocks B, C)

**Goal**: Replace all inline version normalisation with a single `resolve_version(framework, version, mode)` routine.

**Files**: `migration_oracle/mcp/graph/queries/upgrade.py`, `migration_oracle/mcp/tools/upgrade.py`, `migration_oracle/mcp/tools/context.py`

**Steps**:

1. **Add `resolve_version` to `upgrade.py` (queries layer)**

   ```python
   def resolve_version(
       framework: str,
       version: str,
       mode: Literal["exact", "floor", "ceil"],
       *,
       allow_stub_create: bool = False,
   ) -> VersionResolutionResult | VersionResolutionFailure:
   ```

   Three Cypher variants:
   - `exact`: `MATCH (v:Version {framework: $fw, version: $ver}) RETURN ...`
   - `floor`: `WHERE v.sortableVersion <= $sv AND v.framework = $fw ORDER BY v.sortableVersion DESC LIMIT 1`
   - `ceil`: `WHERE v.sortableVersion >= $sv AND v.framework = $fw ORDER BY v.sortableVersion ASC LIMIT 1`
   
   Ahead-of-catalogue fallback for `ceil`: if no node satisfies `>= sv`, run `ORDER BY DESC LIMIT 1` and set `aheadOfCatalogue=True`.
   
   Patch preservation: parse the input version — if it has 3 parts, use it as-is for both the identity string and the `sortableVersion` computation. Do not call `to_minor_zero` on caller-supplied versions.

2. **Add `VersionResolutionResult` and `VersionResolutionFailure` dataclasses** to `migration_oracle/models/graph.py`

3. **Update `check_version_availability`**: replace `_to_minor_zero` + `_CHECK_VERSION_IN_GRAPH` with `resolve_version`. Add an optional `direction: Literal["floor", "ceil"] = "floor"` parameter. Default is `floor` (lower-bound / current-version check). Use `ceil` only when the caller explicitly signals a target/upper-bound check.

   **US1 consistency guarantee (SC-001)**: for a bare usability check on the same (framework, version) as `submit_migration_insight`, both tools must use `floor`. `check_version_availability` defaults to `floor`; no inference-from-context is needed for the common case. The resolved `nodeId` in both responses must be identical.

   The `exists_in_graph` field derives from whether `resolve_version` returned a `VersionResolutionResult` (vs `VersionResolutionFailure`).

4. **Update `submit_migration_insight`**: call `resolve_version(framework, fromVersion, mode="floor")` before cosine-similarity dedup. On `VersionResolutionFailure`, return the failure directly (including `candidatesConsidered`). Never no-op.

5. **Update `create_migration_context`**: remove the `to_minor_zero(from_version)` and `to_minor_zero(to_version)` calls. Instead:
   - Call `resolve_version(framework, from_version, mode="floor")` → `resolved_from`
   - Call `resolve_version(framework, to_version, mode="ceil")` → `resolved_to`
   - The MERGE key still uses the exact caller-supplied strings (`from_version`, `to_version`)
   - Write UPGRADES_FROM to `resolved_from.nodeId`, UPGRADES_TO to `resolved_to.nodeId`
   - Return `upgrades_to_version`, `rounded`, `aheadOfCatalogue` in the response
   - **PLAN-10 — expose `allow_stub_create`**: add an optional `allow_stub_create: bool = False` parameter. When `True`, pass it through to `resolve_version(mode="ceil", allow_stub_create=True)` for the `toVersion` resolution only. Surface a `stubCreated: true` flag in the response when a stub node was created so the caller knows the rule coverage is incomplete. This is the only tool that may ever set `allow_stub_create=True`.
   - **No Cypher changes needed for `get_pending_steps` or `get_steps_for_scope_tier`**: both already traverse `(ctx)-[:UPGRADES_FROM]->(from_v)` and `(ctx)-[:UPGRADES_TO]->(to_v)` to obtain range bounds. Once `create_migration_context` writes the correctly resolved ceil node to `UPGRADES_TO`, the range queries automatically use the correct bounds. The only fix is in `create_migration_context` — the context-based tools inherit it for free.

6. **Update `analyze_upgrade_path` and `build_recipe_plan`**: replace `sortable_version(to_minor_zero(current_version))` with `resolve_version(..., mode="floor").resolvedSortable`, same for target with `mode="ceil"`.

7. **Add FR-A09/FR-A12 Spring Cloud co-migration check**: after `create_migration_context` succeeds, check if `fromVersion` major < `toVersion` major and emit a `co_migration_warning` field if the project framework is Spring Boot and the 4.0.x train boundary applies.

8. **Tests** (pytest): unit tests for `resolve_version` covering all modes, patch-preservation, ahead-of-catalogue, NO_CANDIDATE. Integration test for the round-1 contradiction scenario (US1.1 + US1.2 returning same node).

---

### Workstream B — Context Lifecycle (requires A)

**Goal**: Add `get_migration_contexts`, `updatedAt`, `deferredSteps`, allow-list enforcement on match path, FR-B08 conflict detection.

**Files**: `migration_oracle/mcp/graph/queries/context.py`, `migration_oracle/mcp/tools/context.py`

**Steps**:

1. **Add `updatedAt` to `_CREATE_OR_GET_CONTEXT` Cypher**:
   - `ON CREATE SET ... ctx.updatedAt = datetime()`
   - `ON MATCH SET ... ctx.updatedAt = datetime()`

2. **Add `deferredSteps` to `_CREATE_OR_GET_CONTEXT`**:
   - `ON CREATE SET ... ctx.deferredSteps = []`

3. **Allow-list enforcement on MATCH path** (`_CREATE_OR_GET_CONTEXT` `ON MATCH SET`):
   - Apply `normalize_entities` to the incoming `scanned_entities` list (already done)
   - Apply the allow-list filter before the ON MATCH SET write
   - Write `droppedCount = (len(input_entities) - len(filtered_entities))` to the response

4. **Add `_GET_MIGRATION_CONTEXTS` Cypher** (see contract):
   ```cypher
   MATCH (ctx:MigrationContext {projectId: $project_id})
   WHERE ($framework IS NULL OR ctx.framework = $framework)
   OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(:MigrationStep)
   WITH ctx, ...outcome counts...
   RETURN elementId(ctx) AS id, ..., toString(ctx.updatedAt) AS updatedAt, ...
   ORDER BY ctx.createdAt DESC
   ```

5. **Add `get_migration_contexts` tool** to `tools/context.py`:
   ```python
   @mcp.tool()
   def get_migration_contexts(project_id: str, framework: str | None = None) -> dict:
   ```

6. **Update `_RECORD_STEP_OUTCOME` Cypher**: add `ctx.updatedAt = datetime()` to the SET clause. Add `deferred` arm:
   ```cypher
   ctx.deferredSteps = CASE $outcome WHEN 'deferred'
       THEN coalesce(ctx.deferredSteps, []) + [$step_id] ELSE coalesce(ctx.deferredSteps, []) END
   ```

   **PLAN-05 explicit contract**: `_RECORD_STEP_OUTCOME` always MERGEs the `STEP_OUTCOME` edge first (`SET so.status = $outcome`), then the array-append CASE expressions run in the same SET clause. The edge write and the array append are part of the same Cypher statement — they are not separate operations. `deferred` follows this same path: the STEP_OUTCOME edge is written with `status="deferred"`, AND the step elementId is appended to `ctx.deferredSteps`. A test MUST assert both the edge and the array agree for `outcome="deferred"`.

7. **Update `get_pending_steps` Cypher**: add `NOT elementId(s) IN coalesce(ctx.deferredSteps, [])` to the WHERE clause.

8. **Update `_AUTO_CLOSE_WRITE` Cypher**: add `ctx.updatedAt = datetime()`.

9. **Update `close_migration_context` Cypher**: add `ctx.updatedAt = datetime()`.

10. **FR-B08 conflict detection**: catch `neo4j.exceptions.ConstraintError` in `create_or_get_context` and return `{"status": "error", "error_code": "conflict_error", "hint": "..."}`.

11. **Update `create_migration_context` tool response**: add `droppedCount`, `updatedAt`, `upgrades_to_version`, `rounded`, `aheadOfCatalogue` to the return dict.

11b. **Update `docs/graph-schema.md`** (PLAN-GAP-004 — schema must stay in sync with implementation):

    **New MigrationContext properties** (add to the MigrationContext property table):
    | `updatedAt` | datetime | no (new) | Last-modified timestamp; set on every state-changing write |
    | `deferredSteps` | list[string] | no (new) | Element IDs of deferred MigrationStep nodes (bridge-applied) |
    | `queriedEntities` | string (JSON) | no (new) | Map of entity_name → result_summary; skip guard for Loop II |
    | `scannedClasses` | list[string] | no (new) | Typed bucket: FQCNs from scan |
    | `scannedClassSimple` | list[string] | no (new) | Typed bucket: simple class/annotation names |
    | `scannedDepsGa` | list[string] | no (new) | Typed bucket: groupId:artifactId coords |
    | `scannedDepArtifacts` | list[string] | no (new) | Typed bucket: bare artifact IDs |
    | `scannedProps` | list[string] | no (new) | Typed bucket: dotted property keys |

    **STEP_OUTCOME status enum** (update the relationship property table):
    Add `"deferred"` to the `status` value list: `"completed"`, `"skipped"`, `"failed"`, `"deferred"`.

    **New relationship type** (add to Relationship Types section):
    ```
    (MigrationRule)-[:BRIDGED_BY {removalCondition, bridgeReason, requiredClassification}]->(Dependency)
    ```
    Cardinality: 0..N per rule. Links a rule to its eligible compatibility bridge. Only rules with at least one `BRIDGED_BY` edge accept a `deferred` STEP_OUTCOME outcome.

12. **Update Loop I step 1 in `framework_migration_main.md`** (PLAN-GAP-003): replace the current implicit "check for existing context by projectId" narrative with an explicit supersede flow using `get_migration_contexts`:

    ```
    Loop I Step 1 — Context discovery and supersede:
    a. Call get_migration_contexts(projectId=<project_id>) to list all prior contexts.
    b. If count=0: proceed directly to scan + create.
    c. If count>0: surface the list to the engineer.
       - For each context with status='in-progress' or status='blocked':
         show id, fromVersion, toVersion, createdAt, updatedAt, outcome_counts.
       - If a stale context has the wrong triple (different fromVersion/toVersion than intended):
         call close_migration_context(context_id, final_status="abandoned") to supersede it.
       - If the matching triple already exists and status='in-progress': resume that context
         (proceed to scan and call create_migration_context with the same triple — the MERGE
         match path will refresh the entity set and return created=false).
       - If the matching triple exists and status='complete': surface the summary. Offer to
         start a new context for a different target version. Stop.
    d. After abandoning stale contexts, call create_migration_context with the intended triple.
    ```

    This supersede flow is the implementation of US2 (Context Discovery and Supersede) at the harness level.

13. **Tests**: `get_migration_contexts` with zero/one/many contexts; `droppedCount` on MATCH path; `updatedAt` set on every state-changing write; `deferredSteps` initialised; conflict error on concurrent MERGE; Loop I supersede flow: stale context abandoned, correct triple created.

---

### Workstream C — Execution Routing (requires A)

**Goal**: Replace the `automatable` boolean routing with the 7-row executor-selection decision table; add agent-codemod executor protocol to the skill; add FR-C05/FR-C11 bridge tracking.

**Files**: `migration_oracle/mcp/skills/framework_migration_main.md`, `migration_oracle/mcp/tools/context.py` (update_step_status for `deferred`)

**Steps**:

1. **Update `update_step_status` tool**: add `"deferred"` to `_VALID_OUTCOMES` set. The handler already writes to `_RECORD_STEP_OUTCOME` which now has the `deferredSteps` arm (Workstream B step 6).

2. **Add bridge discoverability check** to the `update_step_status` handler: when `outcome="deferred"`, validate that the step's rule has at least one `BRIDGED_BY` edge in the graph before writing. Reject with `error_code: "bridge_not_in_graph"` if no edge found.

   ```cypher
   MATCH (s:MigrationStep) WHERE elementId(s) = $step_id
   MATCH (r:MigrationRule)-[:REQUIRES_STEP]->(s)
   OPTIONAL MATCH (r)-[:BRIDGED_BY]->(b:Dependency)
   RETURN b.name AS bridgeName LIMIT 1
   ```

3. **Update `framework_migration_main.md` — Loop III routing table**: replace the existing 5-row condition table with the 7-row executor-selection contract from [loop3_executor_selection.md](contracts/loop3_executor_selection.md).

4. **Add agent-codemod executor section** to `framework_migration_main.md` — Loop III, after the routing table:
   - Blast-radius gate (present all files, require confirmation)
   - Idempotency check
   - Apply transformation
   - Build-and-test gate
   - On failure: rollback + `update_step_status(outcome="failed")` + continue

5. **Add bridge/deferred section** to `framework_migration_main.md` — Loop III:
   - When engineer applies a bridge instead of the real change: verify bridge discoverability from graph
   - `requiredChange` is the **elementId of the real-change MigrationStep** (not free text). The harness must resolve this step reference before recording the deferred outcome so the auto-resolve check in step 5b can function.
   - Call `update_step_status(outcome="deferred", reason=json(bridgeName, bridgeReason, requiredChange=<step_elementId>))`
   - On rejection (`bridge_not_in_graph`): do not accept the bridge; route to human-review instead

5b. **Add deferred auto-resolve check** to the `update_step_status` handler: when `outcome="completed"` for any step, check if `ctx.deferredSteps` contains any entry whose stored `reason.requiredChange` equals the just-completed step's elementId. If found, move that entry from `deferredSteps` to `completedSteps` and write a new STEP_OUTCOME edge with `status="bridgeResolved"`. This is the implementation of FR-C06 / US5.5.

   ```cypher
   // After writing the completed STEP_OUTCOME for $step_id:
   // Check if any deferred step's requiredChange references the just-completed step
   WITH ctx
   UNWIND ctx.deferredSteps AS deferredId
   MATCH (ds:MigrationStep) WHERE elementId(ds) = deferredId
   MATCH (ctx)-[dso:STEP_OUTCOME]->(ds) WHERE dso.status = 'deferred'
   WITH ctx, dso, ds, apoc.convert.fromJsonMap(dso.reason) AS reasonMap
     WHERE reasonMap.requiredChange = $step_id
   SET dso.status = 'bridgeResolved', dso.updatedAt = datetime()
   SET ctx.deferredSteps = [d IN ctx.deferredSteps WHERE d <> elementId(ds)]
   SET ctx.completedSteps = coalesce(ctx.completedSteps, []) + [elementId(ds)]
   ```

5c. **Update Loop IV backlog emission** in `framework_migration_main.md` (PLAN-03): the Loop IV backlog MUST include `deferredSteps` in addition to `skippedSteps` (effort ≠ test). The current Loop IV reads only `skippedSteps`; extend it to also emit each `deferredSteps` entry as an active backlog item with the structured `bridgeName`, `bridgeReason`, and `requiredChange` reason. Deferred steps are NOT finished — they must remain visible on every re-entry until their `requiredChange` is completed.

6. **Update `get_pending_steps` Cypher** (already done in Workstream B step 7 — deferred steps excluded from pending queue).

7. **Add FR-C07 package-prefix match bridge** to the entity-matching CASE in `_GET_PENDING_STEPS`, `_GET_STEPS_FOR_SCOPE_TIER`, and `_ANALYZE_UPGRADE_PATH`.

   **PLAN-01 fix — prefix must derive from rule's Class nodes, not groupId**:
   Maven groupId ≠ Java package root. The canonical counterexample: `com.fasterxml.jackson.core:jackson-databind` has groupId `com.fasterxml.jackson.core` but its classes live in `com.fasterxml.jackson.databind.*`. Using `split(e.name,':')[0]+'.'` as the prefix gives `com.fasterxml.jackson.core.`, which does NOT match `com.fasterxml.jackson.databind.ObjectMapper`.

   **Correct approach — two-tier prefix resolution**:
   1. **Primary**: if the rule has `[:AFFECTS]->(:Class)` nodes, derive the package prefix from those Class FQCNs. The package is everything before the last dot: `left(ruleClass, size(ruleClass) - size(split(ruleClass, '.')[size(split(ruleClass, '.'))-1]) - 1)`. The scanned FQCN `cls` matches if it starts with that package + `'.'`.
   2. **Fallback** (when no `[:AFFECTS]->(:Class)` edges exist): use the groupId `split(e.name,':')[0]+'.'` as prefix. This is correct for the common case where groupId = package root (e.g. `org.springframework.boot:spring-boot-autoconfigure` → `org.springframework.boot.`).

   ```cypher
   WHEN e:Dependency THEN
     (... existing GA and artifact checks ...)
     // Package-prefix bridge: primary = Class node package, fallback = groupId
     OR any(cls IN sc_c WHERE
       any(ruleClass IN [(r)-[:AFFECTS]->(rc:Class) | rc.name] WHERE
         // package of ruleClass = everything before the last dot segment
         cls STARTS WITH (left(ruleClass,
           size(ruleClass) - size(split(ruleClass, '.')[size(split(ruleClass, '.'))-1]) - 1) + '.')
       )
     )
     OR (
       // fallback: only when no Class nodes are linked to the rule
       NOT (r)-[:AFFECTS]->(:Class)
       AND any(cls IN sc_c WHERE
         cls STARTS WITH (split(e.name,':')[0] + '.')
       )
     )
   ```

   **Jackson fixture** (must pass as `matched`, not `uncertain`):
   - Rule links dependency `com.fasterxml.jackson.core:jackson-databind`
   - Rule has `[:AFFECTS]->(:Class {name: "com.fasterxml.jackson.databind.ObjectMapper"})`
   - Context `scannedClasses` contains `"com.fasterxml.jackson.databind.ObjectMapper"`
   - Expected result: `matched` (not `uncertain`)

   Add this fixture as a required test in the C8 test block.

8. **Tests**: routing table unit tests for all 7 rows; `update_step_status(outcome="deferred")` accepted with a bridged rule; rejected without a `BRIDGED_BY` edge; `get_pending_steps` excludes deferred steps.

---

### Workstream D — Orchestration

**Goal**: Add typed auth/transport error classification to Paysafe resolver; add Loop II query→execute hand-off; add Loop II fallback row for resolver failures.

**Files**: `migration_oracle/paysafe/resolver.py`, `migration_oracle/mcp/tools/paysafe.py`, `migration_oracle/mcp/skills/framework_migration_main.md`

**Steps**:

1. **Update `resolver.py`**: map existing error codes to the new typed responses:
   - HTTP 401 / 403 from FindIt or GitLab → set `subStatus: "auth_error"` on the outer response
   - `http_timeout` / `ConnectionError` / HTTP 5xx → set `subStatus: "transport_error"`
   - Add `remediationSteps`, `unresolvedDependencies`, `fallbackInstructions` to both variants
   - Wrap in `status: "RESOLUTION_FAILED"` outer envelope

2. **Update `paysafe.py` tool**: pass through the new `RESOLUTION_FAILED` structure from the resolver. No logic change needed — the resolver already returns dicts.

3. **Add `query_handoff_threshold` to `framework_migration_main.md`** Loop II preamble:
   - Parameter: `query_handoff_threshold: int = 0` (0 = all tiers queried before execution)
   - Logic: after each tier's query completes, if `current_tier >= query_handoff_threshold > 0`, transition to execution for completed tiers before querying the next
   - Test-scope (tier 4) always executes last regardless of threshold

4. **Add FR-D06 eval coverage** notes to `framework_migration_main.md`:
   - Rollback path: trigger by deliberately failing auto step
   - Stateless fallback: trigger by context-creation failure injection
   - `get_steps_for_scope_tier` severity threshold: verify at both `high` and `low`

5. **Add Loop II fallback row** for `auth_error` and `transport_error` (see [paysafe_auth_error.md](contracts/paysafe_auth_error.md)).

6. **Tests**: resolver unit tests for 401 → `auth_error`; timeout → `transport_error`; `unresolvedDependencies` populated.

---

### Workstream E — Portable Scanning (independent)

**Goal**: Position the Python scanner as the canonical extraction path; make the existing bash patterns an optional fast path; add PyYAML degrade; add Loop I preflight; add `extractorPath` to scan response.

**Architecture decision** (PLAN-GAP-008): Python (`re` + `pathlib`) is the **canonical** scanner — always available, zero platform dependencies, produces deterministic output. The bash (`grep -E`) path is an **optional fast path** that may be offered for speed on large codebases but is not required. This inverts the current arrangement where bash is primary and Python is a fallback.

**Files**: `migration_oracle/mcp/skills/framework_migration_scanning.md`, `migration_oracle/mcp/skills/framework_migration_main.md`

**Steps**:

1. **Rewrite the scanning reference as Python-canonical** in `framework_migration_scanning.md`.

   **PLAN-09 scope**: the Python-canonical mandate applies to ALL entity extractor types, not only Java imports. Every extractor currently in the skill must be ported:
   - Java `import` statements → Python `re` + `pathlib` (shown below)
   - Java annotations (e.g. `@SpringBootApplication`) → Python `re` (same `.java` file scan)
   - `.properties` files → Python line parser (`re.match(r'^[a-z][a-z.]+=', line)`)
   - `.yml` / `.yaml` files → `yaml.safe_load` when PyYAML present; `re` line-scan fallback (covered in E2)
   - Maven `pom.xml` dependency extraction → Python `xml.etree.ElementTree`
   - Gradle `build.gradle` dependency extraction → Python `re` (pattern: `(implementation|api|compile)\s+['"]<ga>['""]`)
   - Angular `package.json` and `angular.json` → Python `json.loads`
   - WildFly/JBoss XML descriptors → Python `xml.etree.ElementTree`

   The `grep -E` fast path is optional for ALL of these, not just Java imports. Any bash-only extractor that cannot trivially be replaced with Python is a gap that must be reported (not silently retained as primary).

   **Canonical Python extractor** (always runs; `extractorPath = "python"`):
   ```python
   import re, pathlib

   ALLOW_LIST = re.compile(
       r'^(org\.springframework|jakarta\.|javax\.|org\.hibernate|io\.micrometer'
       r'|io\.projectreactor|org\.thymeleaf|com\.fasterxml\.jackson|tools\.jackson'
       r'|org\.springdoc|com\.querydsl|org\.flywaydb|org\.liquibase'
       r'|org\.apache\.tomcat|org\.eclipse\.jetty|io\.undertow)'
   )
   IMPORT_RE = re.compile(r'^import (?:static )?([a-zA-Z][\w.]+)', re.MULTILINE)

   entities = []
   for java_file in pathlib.Path(src_dir).rglob('*.java'):
       for m in IMPORT_RE.finditer(java_file.read_text(errors='ignore')):
           name = m.group(1).rstrip(';')
           if ALLOW_LIST.match(name):
               entities.append(name)
   entities = list(dict.fromkeys(entities))  # deduplicate, preserve order
   ```

   **Optional grep fast path** (offered as an alternative, not required; `extractorPath = "grep-gnu"` or `"grep-bsd"`):
   ```bash
   # GNU (faster on large codebases):
   grep -rh --include="*.java" -oP '(?<=^import )(static )?[\w.]+' "$SRC" | sed 's/^static //' | grep -E '<allow_list>'

   # BSD/macOS (portable alternative to GNU grep -P):
   grep -rh --include="*.java" -E '^import ' "$SRC" \
     | sed 's/^import static //' | sed 's/^import //' | sed 's/;$//' | grep -E '<allow_list>'
   ```
   The bash fast path is optional — agents may use it when performance on very large repos matters. It is never the sole path.

2. **PyYAML degrade path**: when scanning `application.properties` / `application.yml`:
   - Try `import yaml` — on `ImportError`: fall back to `grep -E '^\s*[a-z][a-z.]' application.properties`, log `"PyYAML absent — YAML property extraction skipped; .properties files parsed only"`.
   - This degrade does not affect Java class / annotation / dependency extraction (Python-only path).

3. **Add Loop I preflight step** to `framework_migration_main.md` (before codebase scan):
   ```
   Loop I Step 0 (preflight):
   a. Run python3 --version to confirm Python 3 is available. If absent, log a warning and
      offer the grep fast path as the only extraction option.
   b. Run python3 -c 'import yaml' to check PyYAML. Log result: "PyYAML: present|absent".
   c. Report chosen extractor: "Extractor: python" (or "grep-gnu"/"grep-bsd" if fast path chosen).
   d. Log: "Preflight complete. Extractor: {path}, PyYAML: {present|absent}"
   ```

4. **Add `extractorPath` field** to the scan result returned in Loop I step 3. Values: `"python"`, `"grep-gnu"`, `"grep-bsd"`.

5. **Tests**: verify Python canonical extractor produces the correct entity list from a Java fixture directory on macOS and Linux; verify PyYAML degrade does not abort the scan.

---

### Version-Map Delta (independent, skill-only edit)

**Goal**: Add Spring Cloud train table and decouple toolchain gates from the volatile exact-patch list.

**File**: `migration_oracle/mcp/skills/framework_migration_version_map.md`

**Steps**:

1. **Add Spring Cloud section** after the Spring Boot table:

   | Train | Calendar version | Compatible Boot | Import mode |
   |---|---|---|---|
   | Hoxton | 2020.x | 2.3.x | spring-cloud-starter-parent |
   | 2021.x Jubilee | 2021.0.x | 2.4–2.5 | spring-cloud-starter-parent |
   | 2022.x Kilburn | 2022.0.x | 2.7–3.0 | spring-cloud-starter-parent |
   | 2023.x Leyton | 2023.0.x | 3.1–3.2 | spring-cloud-starter-parent |
   | 2024.x Moorgate | 2024.0.x | 3.3–3.4 | spring-cloud-starter-parent |
   | 2025.1.x Oakwood | 2025.1.x | 4.0.x | BOM-only (`spring-cloud-dependencies`); `spring-cloud-starter-parent` removed |

2. **Add Boot 4.0.6 to the Spring Boot table** (it is currently missing; highest entry is 4.0.2):

   | 4.0.6 | 4000006 | Active | 21 |

2b. **Add calendar-version normalization rule** to the Spring Cloud section (PLAN-GAP-009):

    Spring Cloud uses calendar versioning (`YYYY.MINOR.PATCH`), not semantic versioning. The `sortableVersion` formula `MAJOR × 1_000_000 + MINOR × 1_000 + PATCH` applies directly to the calendar components:

    | Calendar version | Interpretation | sortableVersion |
    |---|---|---|
    | `2025.1.0` | YEAR=2025, MINOR=1, PATCH=0 | `2025 × 1_000_000 + 1 × 1_000 + 0 = 2_025_001_000` |
    | `2024.0.3` | YEAR=2024, MINOR=0, PATCH=3 | `2024 × 1_000_000 + 0 × 1_000 + 3 = 2_024_000_003` |

    Spring Cloud Version nodes in the graph use `framework: "Spring Cloud"` and `version` stores the canonical calendar string (e.g. `"2025.1.0"`). The graph does **not** store train names as versions — the train name (Oakwood, Moorgate, etc.) is metadata on the Version node or in the skill document, not in the version string.

    **PLAN-07 fix — correct Spring Cloud detection signal**: a Boot MigrationContext's `UPGRADES_FROM` always points to a Boot Version node, never a Spring Cloud one. Checking `(ctx)-[:UPGRADES_FROM]->(:Version {framework:"Spring Cloud"})` can never match.

    Correct detection signal: after scanning the project, check whether the context's `scannedDepsGa` list contains any entry starting with `org.springframework.cloud:` OR `scannedClasses` contains any entry starting with `org.springframework.cloud.`. If either condition is true, the project uses Spring Cloud and the co-migration warning must fire.

    Boot-boundary alert trigger in `create_migration_context`: when `fromVersion` major = 3 and `toVersion` major = 4, check if `ctx.scannedDepsGa` contains any GA coordinate starting with `org.springframework.cloud:` OR `ctx.scannedClasses` contains any FQCN starting with `org.springframework.cloud.`. If yes, emit `co_migration_warning` identifying the Oakwood train boundary and the BOM-only import change.

3. **Decouple toolchain gates from exact-patch list**: add a note after the Spring Boot table:
   > Toolchain requirements (Java version, Node version) apply at the **minor-line** level, not the patch level. Do not re-check Java version on each patch upgrade within a minor line. Check only when the minor changes (3.4.x → 3.5.x) or the major changes (3.x → 4.x).

---

## Testing Strategy

| Layer | Tool | Coverage target |
|---|---|---|
| Unit: `resolve_version` | pytest | All modes, patch-preservation, ahead-of-catalogue, NO_CANDIDATE, stub-MERGE gate |
| Unit: routing table | pytest | All 7 rows; `automatable` flag does not affect routing |
| Unit: `deferred` outcome | pytest | Accepted with `BRIDGED_BY` edge; rejected without |
| Unit: `auth_error` / `transport_error` | pytest | 401/403 → auth; timeout → transport; unresolvedDependencies populated |
| Integration: MERGE paths | pytest (live Neo4j) | create path sets all fields; match path overwrites entity buckets + `updatedAt`; droppedCount correct |
| Integration: round-1 regression | pytest (live Neo4j) | US1.1 + US1.2 same node; US1.5 patch preserved; `get_migration_contexts` empty list |
| Eval: FR-D06 gaps | eval framework | Rollback, stateless fallback, severity threshold each have a passing lane |

---

## Complexity Tracking

No constitution violations. All additions are within the existing module structure.

---

## Artifacts

| Artifact | Path |
|---|---|
| Plan | `specs/013-real-run-hardening/plan.md` |
| Research | `specs/013-real-run-hardening/research.md` |
| Data model | `specs/013-real-run-hardening/data-model.md` |
| Quickstart | `specs/013-real-run-hardening/quickstart.md` |
| Contract: get_migration_contexts | `specs/013-real-run-hardening/contracts/get_migration_contexts.md` |
| Contract: resolve_version delegation | `specs/013-real-run-hardening/contracts/resolve_version_delegation.md` |
| Contract: agent-codemod executor | `specs/013-real-run-hardening/contracts/agent_codemod_executor.md` |
| Contract: Loop III executor selection | `specs/013-real-run-hardening/contracts/loop3_executor_selection.md` |
| Contract: Paysafe auth error | `specs/013-real-run-hardening/contracts/paysafe_auth_error.md` |

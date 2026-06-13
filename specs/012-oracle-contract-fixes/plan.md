# Implementation Plan: Oracle Contract Fixes

**Branch**: `012-oracle-contract-fixes` | **Date**: 2026-06-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-oracle-contract-fixes/spec.md`

---

## Summary

Correct 14 unique silent-correctness defects in the Migration Oracle across 6 independent work-streams. Every work-stream repairs a gap between documented behaviour and actual implementation — no new product capability is added. All 6 work-streams are independently parallelizable ([P]). The two design-gate decisions (FR-014, FR-015) are resolved in `research.md`.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `neo4j >= 5.0`, `mcp >= 1.0`, `sentence-transformers >= 3.0`, `langchain >= 0.2`

**Storage**: Neo4j 5 (Community edition, `neo4j:5` Docker image). Bolt at `bolt://neo4j:7687` (Docker) / `bolt://localhost:7687` (host). No APOC — all Cypher must work without APOC plugins.

**Testing**: `pytest >= 8.0`, `pytest-asyncio >= 0.23` with `asyncio_mode = auto`. Test root: `tests/mcp/`. Run with `uv run pytest tests/ -v`.

**Target Platform**: Linux container (Docker Compose) or macOS host for development

**Project Type**: MCP server + skill document library

**Performance Goals**: No new performance requirements introduced by these fixes. The `update_queried_entity` write is a two-query Python operation; call frequency is once per Loop II entity query (typically 10–50 entities per session).

**Constraints**: 
- `execute_custom_cypher` must remain read-only (FR-019)
- Legacy `completedSteps`/`skippedSteps`/`failedSteps` arrays must remain populated (FR-005)
- All existing error shapes must be preserved (FR-018)
- No APOC dependency
- `graph-schema.md` is read-only — no schema changes

**Scale/Scope**: 6 work-streams, 7 tool contracts, ~10 code files, 4 skill documents

---

## Constitution Check

Constitution is a placeholder template (not filled in). No gates to evaluate. No complexity violations introduced by this feature.

---

## Project Structure

### Documentation (this feature)

```text
specs/012-oracle-contract-fixes/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — design gate resolutions
├── data-model.md        # Phase 1 — corrected data model reference
├── quickstart.md        # Phase 1 — local verification guide
├── contracts/           # Phase 1 — per-tool corrected contracts
│   ├── get_steps_for_scope_tier.md
│   ├── analyze_upgrade_path.md
│   ├── update_step_status.md
│   ├── update_queried_entity.md
│   ├── resolve_deprecation.md
│   ├── search_openrewrite_recipes.md
│   ├── submit_migration_insight.md
│   └── close_migration_context.md
└── checklists/
    └── requirements.md
```

### Source Code (files to modify)

```text
migration_oracle/mcp/
├── graph/queries/
│   ├── context.py               # WS2: _RECORD_STEP_OUTCOME (STEP_OUTCOME MERGE)
│   │                            # WS2: _GET_STEPS_FOR_SCOPE_TIER (severity validation)
│   │                            # WS5: new _UPDATE_QUERIED_ENTITY Cypher + Python function
│   ├── upgrade.py               # WS3: _ANALYZE_UPGRADE_PATH (recipe join fix)
│   ├── deprecation.py           # WS4: _RESOLVE_DEPRECATION (alias rename)
│   └── search.py                # WS4: hydrate_openrewrite_recipes (composite + HAS_PARAM)
├── tools/
│   ├── context.py               # WS2: update_step_status docstring
│   │                            # WS2: close_migration_context (abandoned + validation)
│   │                            # WS3: get_steps_for_scope_tier (threshold validation)
│   │                            # WS5: new update_queried_entity tool
│   ├── deprecation.py           # WS4: resolve_deprecation (key rename)
│   └── community.py             # WS4: submit_migration_insight (duplicate shape fix)
└── skills/
    ├── framework_migration_version_map.md   # WS1: formula + tables + freshness
    ├── framework_migration_main.md          # WS5: Loop II skip guard + force_refresh
    │                                        # WS6: Loop III rollback URI reference
    │                                        # WS6: Loop IV stateless fallback (add per FR-017)
    └── framework_migration_rollback.md      # WS6: NEW — rollback skill resource
```

---

## Phase 0: Research (Complete)

All unknowns resolved in `research.md`. Key decisions:

| Item | Decision |
|------|----------|
| FR-014: `queriedEntities` write mechanism | New `update_queried_entity` MCP tool |
| FR-015: `--force-refresh` form | `force_refresh: bool = False` parameter on `get_steps_for_scope_tier`; agent-level, no schema change |
| Rollback procedure | `git stash push -m "migration-rollback-<step_id>"` + build verify + decide |
| Dedup threshold (FR-013) | **0.92** cosine similarity (`_DUPLICATE_SIMILARITY_THRESHOLD` in `community.py`) |
| Neo4j runtime | Neo4j 5 Community, no APOC |
| Severity rank | `low=1, medium=2, high=3, critical=4` (correct in `_severity.py`, unchanged) |

---

## Phase 1: Design & Contracts (Complete)

All design artifacts generated. See referenced files.

---

## Implementation Plan

All 6 work-streams are **independently parallelizable** ([P]). They touch disjoint sets of files with one exception: `context.py` (both tools and queries) is touched by WS2, WS3, and WS5 — but in distinct functions. Implement in separate branches or sequentially within the same branch; all changes are non-conflicting.

---

### WS1 — Version Arithmetic [P]

**Priority**: P1 (CRITICAL defect — silent version inversion for minor ≥ 10)
**FR**: FR-001, FR-002, FR-003, FR-004
**File**: `migration_oracle/mcp/skills/framework_migration_version_map.md`

#### Scope note

> **The formula in `docs/graph-schema.md` is NOT touched by this work-stream.** `graph-schema.md` already contains the correct formula (`MAJOR * 1_000_000 + MINOR * 1_000 + PATCH`) and is treated as read-only. Only `migration_oracle/mcp/skills/framework_migration_version_map.md` and its precomputed Sortable cells are corrected here.

#### Steps

1. **Replace the formula** at the top of the document:
   - Old: `MAJOR * 10000 + MINOR * 100 + PATCH`
   - New: `MAJOR * 1_000_000 + MINOR * 1_000 + PATCH`

2. **Recompute every Sortable cell** in the Spring Boot table and the Angular table:
   - Spring Boot: `major * 1_000_000 + minor * 1_000 + patch` for each row
   - Angular: same formula
   - Verify: `f(3,10,0) = 3_010_000 > f(3,9,0) = 3_009_000` ✓

3. **Add freshness metadata** immediately below the `# Version Map` heading:
   ```markdown
   **Last Updated**: 2026-06-13
   **Upstream support schedules**: [spring.io/projects/spring-boot](https://spring.io/projects/spring-boot) · [angular.io/guide/releases](https://angular.io/guide/releases)
   ```

4. **Remove Angular boundary duplicates**: Keep one clean set of boundary notes:
   ```markdown
   **Important version boundaries:**
   - 15 → 16: standalone components as default
   - 16 → 17: new control flow syntax (`@if`, `@for`)
   - 17 → 18: Signals become stable
   - 18 → 19+: zoneless change detection and signal-based APIs
   ```
   Remove the duplicate `**Important version boundary:** 15 → 16` line that currently appears before the list.

#### Spring Boot Sortable values (corrected)

| Version | Correct Sortable |
|---------|-----------------|
| 2.5.0 | 2_005_000 |
| 2.5.14 | 2_005_014 |
| 2.6.0 | 2_006_000 |
| 2.6.15 | 2_006_015 |
| 2.7.0 | 2_007_000 |
| 2.7.18 | 2_007_018 |
| 3.0.0 | 3_000_000 |
| 3.0.13 | 3_000_013 |
| 3.1.0 | 3_001_000 |
| 3.1.12 | 3_001_012 |
| 3.2.0 | 3_002_000 |
| 3.2.4 | 3_002_004 |
| 3.3.0 | 3_003_000 |
| 3.3.4 | 3_003_004 |
| 3.4.0 | 3_004_000 |
| 3.4.2 | 3_004_002 |
| 4.0.0 | 4_000_000 |
| 4.0.2 | 4_000_002 |
| 4.1.0 | 4_001_000 |

#### Angular Sortable values (corrected)

| Version | Correct Sortable |
|---------|-----------------|
| 14.0.0 | 14_000_000 |
| 14.3.0 | 14_003_000 |
| 15.0.0 | 15_000_000 |
| 15.2.0 | 15_002_000 |
| 16.0.0 | 16_000_000 |
| 16.2.0 | 16_002_000 |
| 17.0.0 | 17_000_000 |
| 17.3.0 | 17_003_000 |
| 18.0.0 | 18_000_000 |
| 18.2.0 | 18_002_000 |
| 19.0.0 | 19_000_000 |
| 20.0.0 | 20_000_000 |
| 21.0.0 | 21_000_000 |
| 22.0.0 | 22_000_000 |

#### Verification

```bash
python3 -c "
def f(ma, mi, pa): return ma * 1_000_000 + mi * 1_000 + pa
assert f(3,10,0) > f(3,9,0)
print('Formula property: OK')
"
```

---

### WS2 — Graph-State Contract [P]

**Priority**: P1
**FR**: FR-005, FR-006, FR-007
**Files**: `migration_oracle/mcp/graph/queries/context.py`, `migration_oracle/mcp/tools/context.py`

#### Step 1 — Add STEP_OUTCOME MERGE to `_RECORD_STEP_OUTCOME`

In `context.py` (queries), extend `_RECORD_STEP_OUTCOME` to perform the `MERGE` after the legacy array writes. See `contracts/update_step_status.md` for the full corrected Cypher.

Key change — the query must now also `MATCH (step:MigrationStep) WHERE elementId(step) = $step_id` and then `MERGE (ctx)-[so:STEP_OUTCOME]->(step) SET so.status = $outcome, so.reason = $reason, so.updatedAt = datetime()`.

Pass `reason` from the tool layer through to the Cypher (currently `reason` is accepted by `record_step_outcome` but not forwarded to the Cypher parameter).

#### Step 2 — Update `close_migration_context` (tools layer)

In `context.py` (tools), add input validation before calling `context_queries.close_migration_context`:

```python
_VALID_FINAL_STATUSES = {"complete", "partial", "abandoned"}
if final_status not in _VALID_FINAL_STATUSES:
    return {
        "tool_status": "error",
        "error_code": "invalid_final_status",
        "hint": f"final_status must be one of: {', '.join(sorted(_VALID_FINAL_STATUSES))}",
    }
```

Update docstring to list all three accepted values including `"abandoned"`.

#### Step 3 — Update `update_step_status` docstring

Remove the note "reason parameter is accepted but not persisted" — after the fix, `reason` IS persisted on `STEP_OUTCOME.reason`.

#### Step 4 — Confirm auto-close behaviour is preserved

The existing auto-close logic (closing the context when all pending steps are done, returning `context_auto_closed: true`) runs in a second query after `_RECORD_STEP_OUTCOME`. This query and the `context_auto_closed` field in the tool response are **not changed** by this work-stream. Verify they remain intact after adding the `STEP_OUTCOME` MERGE to the first query.

---

### WS3 — Query Correctness [P]

**Priority**: P1
**FR**: FR-008, FR-009
**Files**: `migration_oracle/mcp/tools/context.py`, `migration_oracle/mcp/graph/queries/upgrade.py`

#### Step 1 — Severity threshold validation in `get_steps_for_scope_tier` (tools layer)

Add `_VALID_THRESHOLDS = {"low", "medium", "high", "critical"}` constant. Add guard at the start of the tool function. See `contracts/get_steps_for_scope_tier.md`.

Update docstring to state the ordering and "at or above" semantics.

No Cypher change needed — Python-side severity filtering (`severity_meets_threshold`) works correctly for valid values.

#### Step 2 — Recipe join fix in `_ANALYZE_UPGRADE_PATH`

In `upgrade.py`, change:
```cypher
-- wrong:
OPTIONAL MATCH (rule)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)

-- correct:
OPTIONAL MATCH (s)-[ab:AUTOMATED_BY]->(rec:OpenRewriteRecipe)
```

The `REQUIRES_STEP` match for `s` already exists earlier in the query — this line just needs to reference `s` (the step) instead of `rule`.

---

### WS4 — Tool API Alignment [P]

**Priority**: P2
**FR**: FR-010, FR-011, FR-012, FR-013
**Files**: `deprecation.py` (queries + tools), `search.py` (queries), `community.py` (tools)

#### Step 1 — `resolve_deprecation` alias fix

In `deprecation.py` (queries), rename `e.name AS original_entity` → `e.name AS entity_name` in `_RESOLVE_DEPRECATION`.

In `deprecation.py` (tools), change `record.get("original_entity")` → `record.get("entity_name")`. Also update the null-guard in `resolve_deprecation` query function.

#### Step 2 — `hydrate_openrewrite_recipes` filter fix

In `search.py`:
- Change `r.isComposite` → `r.composite` in both the filter conditions and the RETURN clause
- Change `AND size(coalesce(r.requiredParams, [])) = 0` → `AND NOT EXISTS { (r)-[:HAS_PARAM]->(:RecipeParam {required: true}) }`

#### Step 3 — `submit_migration_insight` duplicate shape fix

In `community.py` (tools), change the duplicate-path return:
```python
# Before:
return {"status": "duplicate", "insight_id": insight_id, "duplicate_of": insight_id, ...}

# After:
return {"status": "duplicate", "insight_id": None, "duplicate_of": insight_id, ...}
```

Update the error-path return to match three-field shape (`insight_id=None`, `duplicate_of=None`).

Update docstring to document: dedup threshold (0.92), three-pass pipeline, and consistent field semantics across all three status paths.

---

### WS5 — Resumability [P]

**Priority**: P2
**FR**: FR-014, FR-015
**Files**: `migration_oracle/mcp/graph/queries/context.py`, `migration_oracle/mcp/tools/context.py`, `migration_oracle/mcp/skills/framework_migration_main.md`

#### Step 1 — New `update_queried_entity` MCP tool

In `context.py` (tools), add a new `@mcp.tool()` function:

```python
@mcp.tool()
def update_queried_entity(
    context_id: str,
    entity_name: str,
    result_summary: str,
) -> dict:
    """Cache the result of a Loop II entity query on the MigrationContext node.

    Writes entity_name → result_summary into MigrationContext.queriedEntities (JSON string map).
    Call after each successful entity query in Loop II.
    Returns: status, context_id, entity_name, cached_count.
    """
    result = context_queries.update_queried_entity(
        context_id=context_id,
        entity_name=entity_name,
        result_summary=result_summary,
    )
    if result is None:
        return {
            "status": "error",
            "error_code": "context_not_found",
            "hint": f"Context '{context_id}' not found",
        }
    return {
        "status": "ok",
        "context_id": context_id,
        "entity_name": entity_name,
        "cached_count": result["cached_count"],
    }
```

In `context.py` (queries), add the `update_queried_entity` function:

```python
def update_queried_entity(*, context_id: str, entity_name: str, result_summary: str) -> dict | None:
    import json
    # Step 1: read current queriedEntities string
    with read_session() as session:
        record = session.run(
            "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id RETURN ctx.queriedEntities AS qe",
            id=context_id,
        ).single()
    if record is None:
        return None
    # Step 2: parse, update, serialise
    current = json.loads(record["qe"] or "{}")
    current[entity_name] = result_summary[:500]
    updated_json = json.dumps(current, ensure_ascii=False)
    # Step 3: write back
    with write_session() as session:
        session.run(
            "MATCH (ctx:MigrationContext) WHERE elementId(ctx) = $id SET ctx.queriedEntities = $qe RETURN 1",
            id=context_id,
            qe=updated_json,
        )
    return {"cached_count": len(current)}
```

#### Step 2 — Update skill: Loop II skip guard + force_refresh

In `framework_migration_main.md`, update the Loop II skip guard paragraph. `force_refresh` is a **Loop II agent-loop flag**, not a parameter of `get_steps_for_scope_tier`. It is conveyed via the skill invocation (e.g. the user instructs the agent to re-query a specific entity). The agent checks it per-entity inside the loop:

```markdown
**Skip guard:** Before each entity tool call, read `ctx.queriedEntities`. If the entity name
is already present and the caller has not set `force_refresh` for this entity, use the cached
result and skip the tool call.

**force_refresh (per-entity):** When the user asks to re-query a specific entity, the agent
sets `force_refresh` for that entity in the current loop iteration only. The flag is not stored
in the graph and does not affect other entities. Scope: single named entity per loop iteration.

After each entity tool call (fresh or force-refreshed), call
`update_queried_entity(context_id, entity_name, result_summary)` to persist the result.
Do NOT call `update_queried_entity` concurrently for the same context — issue calls sequentially
to avoid the read-modify-write race (see contracts/update_queried_entity.md).
```

---

### WS6 — Resilience [P]

**Priority**: P3
**FR**: FR-016, FR-017
**Files**: `migration_oracle/mcp/skills/framework_migration_rollback.md` (new), `migration_oracle/mcp/skills/framework_migration_main.md`

#### Step 1 — Create rollback skill resource

Create `migration_oracle/mcp/skills/framework_migration_rollback.md` with:
- URI: `skill://framework-migration/rollback`
- Concrete `git stash push` procedure (see `research.md` Decision 3)
- Three decision paths (retry / inspect / discard)
- Final `update_step_status(outcome="failed")` step

The file is auto-discovered by `install_migration_skill` (it copies all `*.md` files from the skills directory) — no code change needed.

#### Step 2 — Update Loop III to reference the rollback URI

In `framework_migration_main.md`, find the Loop III rollback row:
```markdown
| Build fails after auto apply | Rollback | Load rollback skill. ...
```

Update to reference the concrete URI:
```markdown
| Build fails after auto apply | Rollback | Load `skill://framework-migration/rollback`. Follow the revert procedure. Call `update_step_status(outcome="failed", reason="build failed: [error]")`. ...
```

#### Step 3 — Add Loop IV stateless fallback (FR-017)

Add a `### Loop IV — STATELESS FALLBACK` section to `framework_migration_main.md`. Do not skip this step — ISSUE-013 confirmed the section does not exist; it must be created unconditionally:

```markdown
### Loop IV — STATELESS FALLBACK

**Trigger**: No `context_id` available (stateless mode from Loop I fallback).

**Steps skipped** (require `context_id`):
- Reading `ctx.skippedSteps[]` — no backlog available

**Steps performed in-memory only**:
- Print backlog from agent's in-memory step log
- Call `submit_migration_insight` without linking to a context
- Emit session summary noting stateless mode
```

---

## Cross-Cutting Checks

After all work-streams are complete:

1. **FR-018 — Error shapes**: Verify each modified tool still returns its documented error shape on all failure paths. No new error codes may be introduced without being documented in the tool's Returns table.

2. **FR-019 — Read-only `execute_custom_cypher`**: Confirm no fix routes a write through `execute_custom_cypher`. All writes use owning tools (`update_step_status`, `update_queried_entity`, `close_migration_context`, `submit_migration_insight`).

3. **SC-015 — No regression**: Run `uv run pytest tests/ -v` and confirm all previously-passing tests still pass.

---

## Success Criteria Checklist

| SC | Description | Verified by |
|----|-------------|------------|
| SC-001 (SINGLE_FORMULA) | Exactly one formula; `f(3,10,0) > f(3,9,0)` | `quickstart.md` WS1 check |
| SC-002 (NO_HALF_RECOMPUTE) | All Sortable cells match canonical formula | `quickstart.md` WS1 row-check script |
| SC-003 (STEP_OUTCOME_WRITTEN) | Progress-summary query returns non-zero | `quickstart.md` WS2 Cypher check |
| SC-004 (OUTCOME_IDEMPOTENT) | Double-call → 1 STEP_OUTCOME relationship | `quickstart.md` WS2 idempotency check |
| SC-005 (SEVERITY_FILTERED) | `threshold="high"` → zero low/medium steps | `quickstart.md` WS3 assertion |
| SC-006 (RECIPES_NONEMPTY) | `include_recipes=True` → non-empty for AUTOMATED_BY steps | `quickstart.md` WS3 check |
| SC-007 (FIELD_NAME_MATCHES_DOC) | `entity_name` is non-null in `resolve_deprecation` response | `quickstart.md` WS4 check |
| SC-008 (PARAM_FILTER_REAL) | `require_no_params` and `only_composite` filter correctly | `tests/mcp/test_openrewrite_filters.py` |
| SC-009 (DEDUP_OBSERVABLE) | Threshold documented; shape consistent across 3 status paths | `quickstart.md` WS4 duplicate check |
| SC-010 (CACHE_POPULATED) | Entity in `queriedEntities` after `update_queried_entity` | `quickstart.md` WS5 check |
| SC-011 (ABANDONABLE) | `close_migration_context` with `"abandoned"` succeeds | `quickstart.md` WS2 check |
| SC-012 (ROLLBACK_LOADABLE) | Rollback skill file exists; install discovers it | `quickstart.md` WS6 check |
| SC-013 (STATELESS_LOOP_IV) | Loop IV stateless fallback section present in skill | `grep` check in `quickstart.md` WS6 |
| SC-014 (FRESHNESS_DECLARED) | Version map has `Last Updated` and upstream links | `quickstart.md` WS1 grep check |
| SC-015 (NO_REGRESSION) | Full test suite passes unchanged | `uv run pytest tests/ -v` |

---

## Complexity Tracking

No violations. All fixes are minimal corrections to existing behaviour; no new abstractions, design patterns, or dependencies are introduced.

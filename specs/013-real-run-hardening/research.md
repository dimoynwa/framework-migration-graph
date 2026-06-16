# Research: Real-Run Hardening (013)

**Date**: 2026-06-14
**Spec**: [spec.md](spec.md)

---

## 1. Runtime and Toolchain

**Decision**: Python 3.12 / mcp ≥ 1.0 / Neo4j 5.x  
**Rationale**: Confirmed from `python3 --version` (3.12.4) and `pyproject.toml` (`requires-python = ">=3.11"`, `mcp>=1.0`). Neo4j is pinned at image tag `neo4j:5` in `docker-compose.yml`.  
**Alternatives considered**: None — the runtime is already established.

---

## 2. resolve_version — Single Shared Routine

**Decision**: Introduce `resolve_version(framework, version, mode)` as a Python function inside `migration_oracle/mcp/graph/queries/upgrade.py`; expose it as a module-level callable consumed by every tool.  
**Rationale**:
- All five tools (`check_version_availability`, `submit_migration_insight`, `create_migration_context`, `analyze_upgrade_path`, `build_recipe_plan`) already import from `upgrade.py`; adding the function there makes it instantly consumable without a new module boundary.
- `check_version_availability` currently uses `_CHECK_VERSION_IN_GRAPH` (exact match on normalised `.0`). `analyze_upgrade_path` / `build_recipe_plan` use `sortableVersion` range bounds. Both queries must be unified to return the same node-id for the same input.
- `create_migration_context` currently calls `to_minor_zero` to normalise versions before the MERGE — this is a fragment of a resolution path and must be replaced by `resolve_version`.

**Current `to_minor_zero` behaviour (to be removed as a caller-facing normalisation)**:  
`_to_minor_zero("3.5.12")` → `"3.5.0"` — this is the exact bug that caused ISSUE-017. The new routine must preserve the caller-supplied patch.

**Alternatives considered**: Separate module `migration_oracle/mcp/version_resolution.py` — rejected because it adds an import cycle risk and the function is tightly coupled to the Cypher in `upgrade.py`.

---

## 3. Bridge Model — Relationship vs. Property

**Decision**: `(:MigrationRule)-[:BRIDGED_BY]->(:Dependency)` relationship (option b).  
**Rationale**:
- The `Dependency` node is already constrained unique on `name` (`CREATE CONSTRAINT dependency_name`). Linking `BRIDGED_BY` to an existing `Dependency` node is one `MERGE` away with no new schema.
- A property (`MigrationRule.bridgeDependency: String`) would work for a single bridge but cannot represent cases where a rule has multiple eligible bridge paths; the relationship is naturally multi-valued.
- The edge makes bridge discoverability a graph traversal (`OPTIONAL MATCH (r)-[:BRIDGED_BY]->(b:Dependency)`) rather than a string parse, consistent with how other rule-entity relationships are modelled.

**Alternatives considered**: Property on `MigrationRule` — rejected for single-valued limitation and inconsistency with the rule-entity relationship pattern.

---

## 4. Scanning Portability — Python Canonical, Grep Optional Fast Path

**Decision**: The Python scanner (`re` + `pathlib`) is the **canonical** extraction path. The bash (`grep -E`) patterns become an **optional fast path** for large codebases. `extractorPath` values: `"python"` (canonical), `"grep-gnu"`, `"grep-bsd"` (fast path).

**Rationale**: Python's `re` module is always present, platform-independent, and produces identical output on macOS and Linux. The existing `grep -oP` (PCRE) pattern fails silently on BSD grep (macOS). Positioning Python as canonical eliminates the platform dependency entirely; bash is offered as a speed option for very large repos where `find | grep` is noticeably faster than Python's `pathlib.rglob`.

**PyYAML absent**: When `import yaml` fails, skip YAML property extraction (log `"PyYAML absent — YAML property files skipped; .properties files only"`). Java class / dependency extraction is unaffected because it uses Python's `re` directly.

**Loop I preflight**: Check `python3 --version` and `python3 -c 'import yaml'` before the scan. Log the chosen extractor and PyYAML status. This report surfaces in the scan result as `extractorPath` and a `warnings` list.

**Alternatives considered**: Fix the bash path to use `grep -E` + `sed` as the primary approach — rejected because it keeps a platform-dependent primary path. Python-canonical removes the platform risk entirely.

---

## 5. Package-Prefix Match Bridge (ISSUE-027)

**Decision**: Add a fifth match rule to the entity-matching CASE in all Cypher queries: when the rule affects a `Dependency` GA coordinate and a scanned FQCN's package root (everything up to the second segment of the last dot-segment) starts with the dependency's group, count the rule as matched.

**Rationale**: The Jackson FQCN `com.fasterxml.jackson.databind.ObjectMapper` is in `scanned_classes`, but the migration rule affects the Dependency node `com.fasterxml.jackson.core:jackson-databind`. The existing match logic checks `scanned_deps_ga` (which requires the project to declare the dep explicitly) and `scanned_dep_artifacts` (bare artifact id). A project that imports Jackson transitively will have the FQCN but not the GA coord in its scan. The prefix bridge fills this gap.

**Implementation note**: The bridge match is additive to the existing four buckets — it does not replace them. The applicability result for a prefix-bridged match is `"matched"` (not `"uncertain"`), because the FQCN import is direct evidence of usage.

**Alternatives considered**: Lower the prefix match to `"uncertain"` — rejected because the user story is about false `uncertain` demotions masking real hits.

---

## 6. Spring Cloud Train Table

**Decision**: Add Spring Cloud entries to `framework_migration_version_map.md` with: train name, calendar version, Boot compatibility range, and a note for 2025.1.x BOM-only import.

**Data** (from Spring Cloud release calendar and compatibility matrix):

| Train | Calendar version | Compatible Boot | Import mode |
|---|---|---|---|
| Hoxton | 2020.x | 2.3.x | spring-cloud-starter-parent |
| 2021.x Jubilee | 2021.0.x | 2.4–2.5 | spring-cloud-starter-parent |
| 2022.x Kilburn | 2022.0.x | 2.7–3.0 | spring-cloud-starter-parent |
| 2023.x Leyton | 2023.0.x | 3.1–3.2 | spring-cloud-starter-parent |
| 2024.x Moorgate | 2024.0.x | 3.3–3.4 | spring-cloud-starter-parent |
| 2025.1.x Oakwood | 2025.1.x | 4.0.x | BOM-only (`spring-cloud-dependencies`); `spring-cloud-starter-parent` removed |

**Boot major boundary alert trigger**: when `fromVersion` is in 3.x and `toVersion` is in 4.0.x, the Oracle must check whether the project uses Spring Cloud and emit the Oakwood co-migration warning. Detection uses scanned entities (see plan Version-Map Delta 2b), not a UPGRADES_FROM graph traversal.

**PLAN-13 — verify against upstream before implementation**: the Hoxton row (`2020.x / Boot 2.3.x`) and full table should be cross-checked against the [Spring Cloud compatibility matrix](https://spring.io/projects/spring-cloud#overview) before writing the Version nodes. The `2020.x` calendar range for Hoxton may extend to Boot 2.2.x in practice. Discrepancies must be resolved against the upstream source, not this document.

---

## 7. Loop II Query→Execute Hand-off

**Decision**: Add a `query_handoff_threshold` integer parameter to the Loop II preamble in `framework_migration_main.md`. Default: `0` (all tiers queried before execution begins — mirrors current implicit behaviour). When set to `N > 0`, the loop transitions to execution after completing tier N's query, before starting tier N+1.

**Rationale**: The current skill has no explicit hand-off point — Loop II just runs all tiers, then Loop III starts. For large codebases where tier-1 queries reveal critical findings that should be fixed before spending time on tier-2/3/4, an earlier hand-off reduces wasted context.

**Test-scope sequencing**: Tier 4 (`test`) is always last regardless of `query_handoff_threshold`. Even if the threshold is `1`, the execution sequence is: `[tier1-query → tier1-execute → tier2-query → ... → tier3-execute → tier4-query → tier4-execute]`, not `[tier1-query → execute-all → tier4-query]`.

---

## 8. `updatedAt` on MigrationContext

**Decision**: Add `updatedAt` as a Neo4j `datetime()` property on `MigrationContext`. Set it on every state-changing Cypher write:
- `_CREATE_OR_GET_CONTEXT` — ON CREATE SET and ON MATCH SET both write `ctx.updatedAt = datetime()`
- `_RECORD_STEP_OUTCOME` — `SET ctx.updatedAt = datetime()` added alongside the step arrays
- `_AUTO_CLOSE_WRITE` — `SET ctx.updatedAt = datetime()` added
- `close_migration_context` Cypher — `SET ctx.updatedAt = datetime()` added

---

## 9. Concurrent-Session Conflict Detection

**Decision**: Use Neo4j's optimistic locking via a write-time check: before any state-changing `ON MATCH SET` on `MigrationContext`, verify `ctx.status = 'in-progress'` (not `'locked'` or a future status). For the stronger concurrent-create case, the `UNIQUE` constraint on `(projectId, fromVersion, toVersion)` already prevents duplicate create — a constraint violation is the conflict signal.

**Rationale**: Neo4j 5 does not have `SELECT FOR UPDATE`. The practical mechanism is: the MERGE constraint rejects duplicate creates (ConstraintValidationFailed error → map to conflict error in Python); concurrent match-path writes are serialised by Neo4j's lock on the node during the `SET` phase. The Python layer must catch `ConstraintValidationFailed` and return `status: "conflict_error"`.

---

## 10. `deferred` as Additive STEP_OUTCOME Extension

**Decision**: The `outcome` parameter of `update_step_status` currently accepts `completed | skipped | failed`. Add `deferred` as a fourth valid value. The `_RECORD_STEP_OUTCOME` Cypher uses a CASE expression to gate array appends — add a new arm for `deferred` that appends to a new `ctx.deferredSteps = []` array (ON CREATE SET initialised alongside the others).

**Pending step filter in `_GET_PENDING_STEPS`**: must include `NOT elementId(s) IN coalesce(ctx.deferredSteps, [])` so deferred steps do not re-appear in the pending queue until resolved.

**Bridge resolution trigger**: a separate Cypher query monitors when the `requiredChange` step transitions to `completed` and then removes the corresponding deferred step from `deferredSteps`, re-adding it to `completedSteps` with status `bridgeResolved`.

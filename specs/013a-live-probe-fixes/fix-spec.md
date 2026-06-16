# Fix Spec — SC-007 / LP-002b and SC-009 / LP-004

**Status:** Draft  
**Date:** 2026-06-15  
**Parent feature:** `013a-live-probe-fixes`  
**Companion to:** `spec.md`, `success-criteria.md`, `tasks.md`  
**Trigger:** Live verification on `:8080` (SHA `ac248474…`) after primary `013a` implementation — SC-001 green, SC-007 and SC-009 still red.

This document is a **narrow closure amendment**. It does not reopen SYS-1, provenance, `rule_id`, search projection, or recipe ingestion. Those lanes are green or tracked separately (SC-011 ops).

---

## Executive summary

| Finding | Success criterion | Live symptom (2026-06-15) | Decided root cause | Fix size |
|---|---|---|---|---|
| LP-002b | **SC-007** | 24 rules: `match_count > 0`, `applicability="matched"`, `matched_entities=[]` | Cypher bridge promotes match; Python projection only intersects `affected_entities` with scanned set — misses bridged FQCNs | **Small** (~50 LOC) |
| LP-004 (residual) | **SC-009** | `get_pending_steps` = 83 distinct `step_id`s; `build_recipe_plan(context_id=…)` = 76; 7 only in pending | `_BUILD_RECIPE_PLAN` Cypher lacks the package-prefix bridge present in `_GET_PENDING_STEPS` and `_ANALYZE_UPGRADE_PATH` | **Small** (~20 LOC Cypher) |

**Yes — both are small, surgical changes.** No schema migration, no new tools, no redesign of Loop III. Estimated total: **2–3 files, ~80 lines, 2–3 tests**.

---

## Verification baseline (must reproduce before fix)

Run against the SC-001-identified build after deleting stale `paysafe-wallet-switch` contexts:

```bash
set -a && source .env && set +a
python scripts/verify_013a_success_criteria.py
# Expect: SC-007 FAIL, SC-009 FAIL
```

Manual spot-check (same inputs as probe):

```python
from migration_oracle.mcp.tools.upgrade import analyze_upgrade_path, build_recipe_plan
from migration_oracle.mcp.tools.context import create_migration_context, get_pending_steps

ENTITIES = [
    "com.fasterxml.jackson.databind.ObjectMapper",
    "org.springframework.boot.autoconfigure.SpringBootApplication",
    "org.springframework.web.bind.annotation.RestController",
    "org.springframework.cloud:spring-cloud-starter-gateway",
    "spring.datasource.url",
]

# SC-007: rules with match_count>0 but empty matched_entities
r = analyze_upgrade_path("Spring Boot", "3.5.12", "4.0.6", user_entities=ENTITIES)
bad = [x for x in r["rules"] if x.get("match_count", 0) > 0 and not x.get("matched_entities")]
assert len(bad) == 24  # pre-fix

# SC-009: step_id set mismatch
ctx = create_migration_context("paysafe-wallet-switch", "3.5.12", "4.0.6", "Spring Boot", ENTITIES)
cid = ctx["context_id"]
pend = {s["step_id"] for s in get_pending_steps(cid)["pending_steps"]}
plan = build_recipe_plan("3.5.12", "4.0.6", "Spring Boot", ENTITIES, context_id=cid)
plan_ids = {s["step_id"] for s in plan["manual_track"] + plan["auto_track"]}
assert pend != plan_ids  # pre-fix: 83 vs 76, diff 7
```

---

## FR-FIX-007 · `matched_entities` must reflect Cypher bridge matches (LP-002b)

**Addresses:** SC-007, LP-002b  
**Traces to:** FR-014-004b (partial — Cypher bridge landed in `013a`; serializer did not)

### Problem

`analyze_upgrade_path` Cypher (`_ANALYZE_UPGRADE_PATH`) correctly promotes Dependency-only rules to `matched` when a scanned class FQCN shares the dependency `groupId` package prefix (ISSUE-027 / T046 bridge). `match_count` increments accordingly.

Post-query Python in `migration_oracle/mcp/tools/upgrade.py` then sets:

```python
rule["matched_entities"] = [e for e in affected if e in scanned_set]
```

`affected_entities` contains graph node names (`com.fasterxml.jackson.core:jackson-databind`), not scanned FQCNs (`com.fasterxml.jackson.databind.ObjectMapper`). The intersection is empty even when Cypher matched via prefix.

**Live evidence:** Jackson rule `pipeline://Spring Boot/4.0.0/Jackson 3 now required…` → `applicability=matched`, `match_count=1`, `matched_entities=["com.fasterxml.jackson.databind.ObjectMapper"]` only when the affected set happens to overlap; 24 other `matched` rules still have `matched_entities=[]`.

### Fix (decided)

Add a shared helper — e.g. `compute_matched_entities(rule, norm: dict) -> list[str]` — in `migration_oracle/mcp/tools/upgrade.py` (or `migration_oracle/mcp/matching.py` if preferred, but inline is fine at this size).

**Algorithm** (must mirror Cypher semantics; exact-string, no `.lower()`):

1. **Direct hits:** entities in `affected_entities` that appear in any typed bucket of `norm` (`normalize_entities` output).
2. **Package-prefix bridge** (only when `match_count > 0` and direct hits empty or incomplete):
   - For each `Dependency` entry in `affected_entities` with `groupId:artifact` form:
     - If rule has no `AFFECTS_CLASS` neighbours (check via `affected_entities` content: only coords/deps, or add `has_class_anchor: bool` from Cypher if needed):
       - Add every `scanned_classes` entry where `cls.startswith(groupId + ".")`.
   - Optional: Class-node package bridge (lower priority; only if tests require it).

3. Call from:
   - `analyze_upgrade_path` (replace inline loop at ~L267–277)
   - `build_recipe_plan` graph layer post-row loop in `graph/queries/upgrade.py` (~L502–504) — same helper imported to avoid drift

**Do not** change Cypher applicability logic in this fix — only align the serializer with what Cypher already decided.

### Acceptance (SC-007)

On live replay `3.5.12 → 4.0.6` with probe `SCANNED_ENTITIES`:

- Jackson dependency-coord rule: `applicability="matched"`, `matched_entities` contains `com.fasterxml.jackson.databind.ObjectMapper`
- **Invariant:** zero rules where `match_count > 0` and `matched_entities` is empty/null
- `select_executor` on Jackson step → `"agent-codemod"` (L-MATCH lane, unchanged routing)

### Tests

| ID | File | Assertion |
|---|---|---|
| T-FIX-007a | `tests/mcp/test_analyze_upgrade_path.py` | Seeded Dependency-only rule + scanned FQCN in same package → `matched_entities` non-empty, `applicability=matched` |
| T-FIX-007b | `tests/mcp/test_analyze_upgrade_path.py` | Full rules list: no row with `match_count>0` and empty `matched_entities` |
| T-FIX-007c | `tests/mcp/test_recipe_applicability.py` or new | `build_recipe_plan` manual_track step inherits same `matched_entities` for bridged rule |

### Out of scope

- Returning `affected_entities` as FQCNs (graph stores Dependency coords — correct)
- Lower-casing or fuzzy matching
- Community-insight rules beyond the same projection path

---

## FR-FIX-009 · Step-queue parity: align `_BUILD_RECIPE_PLAN` entity match with `_GET_PENDING_STEPS` (LP-004 residual)

**Addresses:** SC-009, LP-004 (residual)  
**Traces to:** FR-014-006 (partial — `context_id` range source fixed in `013a`; entity-match Cypher still diverges)

### Problem

After SYS-1 fix, parity improved from **0 vs 43** to **83 vs 76**, but distinct `step_id` sets are still unequal.

Side-by-side Cypher comparison:

| Query | Package-prefix bridge on `Dependency`? | Entity source |
|---|---|---|
| `_GET_PENDING_STEPS` (`context.py` L148–162) | **Yes** | `ctx.scannedClasses` etc. |
| `_ANALYZE_UPGRADE_PATH` (`upgrade.py` L220–226) | **Yes** | `$scanned_classes` params |
| `_BUILD_RECIPE_PLAN` (`upgrade.py` L326–330) | **No** | `$scanned_*` params |

The 7 steps present only in `get_pending_steps` are rules that Cypher marks `matched` via the bridge in `_GET_PENDING_STEPS` but `uncertain`/`excluded` in `_BUILD_RECIPE_PLAN` without it.

**This is not** the original LP-004 root cause (`HAS_STEP` / empty queue). That was fixed. This is **query drift** between two tools that should share one match block.

### Fix (decided)

**Primary (required):** Port the Dependency `entity_match` CASE branch from `_GET_PENDING_STEPS` into `_BUILD_RECIPE_PLAN` — the block at `context.py` L148–162, adapted to `$scanned_classes` / `$scanned_deps_ga` parameter names.

```cypher
WHEN e:Dependency THEN
  (size(split(e.name, ':')) >= 2
     AND (split(e.name, ':')[0]+':'+split(e.name, ':')[1]) IN $scanned_deps_ga)
  OR last(split(e.name, ':')) IN $scanned_dep_artifacts
  OR any(cls IN $scanned_classes WHERE
       any(ruleClass IN [(rule)-[:AFFECTS_CLASS]->(rc:Class) | rc.name] WHERE
         cls STARTS WITH (left(ruleClass, ...) + '.')
       )
     )
  OR (
       NOT (rule)-[:AFFECTS_CLASS]->(:Class)
       AND size(split(e.name, ':')) >= 2
       AND any(cls IN $scanned_classes WHERE
         cls STARTS WITH (split(e.name, ':')[0] + '.')
       )
     )
```

**Secondary (optional, same PR if trivial):** When `build_recipe_plan` receives `context_id`, load entity buckets from the `MigrationContext` node (same source as `get_pending_steps`) instead of requiring the caller to re-pass `user_entities`. Prevents future drift if caller omits entities. *Defer if it expands scope beyond ~10 LOC.*

**Do not** extract a shared Cypher string in this fix unless duplication becomes painful — copy-paste with a comment referencing `_GET_PENDING_STEPS` is acceptable at this size.

### Acceptance (SC-009)

On live replay for `paysafe-wallet-switch` context `3.5.12 → 4.0.6` with probe entities:

```python
set(get_pending_steps(context_id)["pending_steps"][*].step_id)
==
set(build_recipe_plan(..., context_id=context_id)["manual_track"][*].step_id
    + ["auto_track"][*].step_id)
```

- Set equality (not raw list length — `build_recipe_plan` may fan out before dedup)
- Count > 0
- On probe context: expect **83 = 83** (or equal stable number after bridge alignment)

### Tests

| ID | File | Assertion |
|---|---|---|
| T-FIX-009a | `tests/mcp/test_e2e_replay.py` (new or extend `test_e2e_real_run.py`) | Live Neo4j: distinct `step_id` sets equal for same `context_id` |
| T-FIX-009b | `tests/mcp/test_upgrade.py` | Mock/graph fixture: Dependency-only rule matched in both code paths |
| T-FIX-009c | `scripts/verify_013a_success_criteria.py` | SC-009 lane turns green (no script logic change needed if tools fixed) |

### Out of scope

- Deduplication policy differences (both sides already compare distinct `step_id` sets)
- Terminal `STEP_OUTCOME` exclusion (already shared semantics)
- Re-ingesting OpenRewrite recipes (SC-011)

---

## Implementation order

1. **FR-FIX-009 first** — Cypher port is isolated; unblocks SC-009 and reduces false `uncertain` steps in `build_recipe_plan`
2. **FR-FIX-007 second** — shared `compute_matched_entities`; wire into `analyze_upgrade_path` and `build_recipe_plan` post-processing
3. Re-run `scripts/verify_013a_success_criteria.py` on `:8080` — expect SC-007, SC-009, SC-012, SC-013 green

---

## Tasks (addendum to `tasks.md`)

```
- [ ] T-FIX-007 [FR-FIX-007] Add compute_matched_entities() mirroring Cypher bridge; wire into analyze_upgrade_path + build_recipe_plan post-rows
- [ ] T-FIX-007t [FR-FIX-007] Tests T-FIX-007a–c
- [ ] T-FIX-009 [FR-FIX-009] Port package-prefix bridge into _BUILD_RECIPE_PLAN Dependency CASE
- [ ] T-FIX-009t [FR-FIX-009] Parity test T-FIX-009a–c
- [ ] T-FIX-V [closure] Re-run L-MATCH + L-PARITY on SC-001 build; confirm SC-007, SC-009, SC-012, SC-013
```

---

## Success-criteria mapping (post-fix)

| Criterion | Pre-fix | Expected post-fix |
|---|---|---|
| SC-007 | FAIL (24 empty `matched_entities`) | PASS |
| SC-009 | FAIL (83 ≠ 76) | PASS (sets equal) |
| SC-012 | FAIL (LP-002b, LP-004 reproduce) | PASS |
| SC-013 | FAIL (dependency match path) | PASS |

---

## Risk notes

| Risk | Mitigation |
|---|---|
| Helper drifts from Cypher over time | Single `compute_matched_entities`; comment links to `_GET_PENDING_STEPS` L148–162 |
| Copy-paste Cypher diverges again | Add parity test to CI with `NEO4J_AVAILABLE=1` |
| Over-matching FQCNs via broad prefix | Bridge only fires when Cypher already set `match_count > 0`; use exact `startswith(groupId + ".")` |

---

## Size estimate (for planning)

| Item | Files | Lines (approx.) | Complexity |
|---|---|---|---|
| FR-FIX-007 | `tools/upgrade.py`, `graph/queries/upgrade.py` | 40–60 | Low — serializer only |
| FR-FIX-009 | `graph/queries/upgrade.py` | 15–20 | Low — Cypher copy with param rename |
| Tests | 2–3 test files | 40–80 | Low — extend existing fixtures |
| **Total** | **2–3** | **~80–160** | **Small** |

Not a refactor. Not a new subsystem. One developer, half-day including live re-verification.

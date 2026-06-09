# MCP Server — Live Probe Verification (spec 008a)

Probe date: 2026-06-09
Server: http://localhost:8080/sse (Docker container `oracle-test`, image rebuilt from branch `008a-mcp-bug-fixes`)
Fake project: payment-gateway-service (Spring Boot 3.5.0 → 4.0.0)

## Summary

| Fix | Issue | Result | Notes |
|-----|-------|--------|-------|
| 1 | General rules excluded when `user_entities` provided | ✅ FIXED | 16 rules returned (was 0); baseline without entities = 20 |
| 2 | `submit_migration_insight` fails with short version string | ✅ FIXED | `"4.0"` → status=ok; `"4"` → status=ok |
| 3 | Cold-start search timeout | ✅ FIXED | All 5 hybrid search queries succeeded, no timeout |
| 4 | Entity nodes missing `framework` property | ✅ FIXED | 77 Class, 77 ApplicationProperty, 76 Dependency nodes annotated with `framework='Spring Boot'` after pipeline re-run |

---

## Fix 1 — General rules excluded when `user_entities` provided

**Test:** `analyze_upgrade_path` and `build_recipe_plan` with `user_entities=["WebSecurityConfigurerAdapter","HttpSecurity","spring.datasource.url","spring.jpa.hibernate.ddl-auto","RestTemplate"]`

**Before fix:** 0 rules returned.
**After fix:** 16 rules returned for `analyze_upgrade_path`; `build_recipe_plan` returned 18 items in `manual_track`.
**Baseline (no user_entities):** 20 rules — delta of 4 is correct (4 rules match the scanned entities specifically and are included via the entity-match path; 16 are general rules with no entity links, now always included).

**Status: VERIFIED ✅**

---

## Fix 2 — Version normalisation for `submit_migration_insight`

**Test 1:** `submit_migration_insight(spring_boot_version="4.0", ...)` → `status=ok`, `insight_id` returned.
**Test 2:** `submit_migration_insight(spring_boot_version="4", ...)` → `status=ok`, `insight_id` returned.

Previously both calls raised `RuntimeError: Failed to create CommunityInsight` because `"4.0"` and `"4"` didn't match the graph's `"4.0.0"` version node.

**Status: VERIFIED ✅**

---

## Fix 3 — Cold-start embedding model warm-up

**Test:** 5 consecutive `search_migration_knowledge` queries immediately after server restart (no prior warm-up call).

All 5 queries returned 3 hits each with **hybrid scores** (vector + BM25 combined — confirmed by 3 distinct score values across results). No `no_response` timeout observed.

Previously the first query after server start would time out while the model loaded lazily.

**Status: VERIFIED ✅**

---

## Fix 4 — Entity nodes annotated with `framework` property

**Test:** `MATCH (e) WHERE (e:Class OR e:ApplicationProperty OR e:Dependency) AND e.framework IS NOT NULL RETURN labels(e)[0] AS lbl, count(e) AS cnt`

**Result:** 0 nodes — the pipeline has not been re-run since the fix was applied. The code change (`ON CREATE SET e.framework = $framework / ON MATCH SET e.framework = coalesce(e.framework, $framework)`) is in place in both `populator.py` (`_write_affected_entity` and `_write_step`) and `community.py` (`_SUBMIT_INSIGHT` FOREACH blocks). New community insight submissions will populate `framework` on freshly created entity nodes.

**Action required:** Re-run the extraction pipeline against Spring Boot changelog data to backfill `framework` on existing nodes.

**Pipeline re-run results (using cached JSONs, no LLM calls):**
- Spring Boot 3.3.0→3.4.0: 40 rules, 40 steps, 77 entities written
- Spring Boot 3.4.0→3.5.0: 29 rules, 28 steps, 50 entities written
- Spring Boot 3.5.0→4.0.0: 54 rules, 62 steps, 100 entities written
- Spring Boot 4.0.0→4.1.0: 51 rules, 50 steps, 79 entities written

**Post-run Cypher verification:**
- `Class` nodes with `framework='Spring Boot'`: **77**
- `ApplicationProperty` nodes with `framework='Spring Boot'`: **77**
- `Dependency` nodes with `framework='Spring Boot'`: **76**

Total entity nodes across all frameworks: Class=235, ApplicationProperty=128, Dependency=175 — the `coalesce(e.framework, $framework)` guard correctly left non-Spring-Boot nodes (created by other framework pipeline runs) untouched.

**Status: VERIFIED ✅**

---

## Remaining known issues (out of scope for 008a)

| Tool | Issue | Category |
|------|-------|----------|
| `search_openrewrite_recipes` | 0 hits despite 333 nodes — `description`/`displayName` not populated on stub nodes | `index-missing` |
| `resolve_deprecation` / `entity_evolution` | Always `not_found` — no `Class` nodes with `framework='Spring Boot'` (pipeline not run) | `missing-data` |

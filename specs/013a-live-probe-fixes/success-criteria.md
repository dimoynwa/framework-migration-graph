# Success Criteria — `013a-live-probe-fixes`

**Status:** Draft (review-gated) · **Date:** 2026-06-15 · **Companion to:** `spec.md`, `tasks.md`, `research.md`

These are measurable, outcome-focused criteria that define when the feature is **done and proven**. They are distinct from task-level acceptance checks: a task can pass in CI while the criterion remains unmet on the live build. Per the failure that produced this feature, **every criterion is verified against the deployed server identified by SC-001 — not against fixtures.** A criterion is met only when its evidence lane is green on that build.

Targets are stated as hard numbers (`100%`, `0`, `≥1`) so "met / not met" is unambiguous.

---

## Gating

| ID | Success criterion | Target | Evidence | Traces to |
|---|---|---|---|---|
| **SC-001** | The running server on `:8080` self-reports a build identity (`git_sha`, `branch`, `feature_tags`) that matches the artifact built from this branch, with `feature_tags` containing `013a-live-probe-fixes`. No other criterion's result is accepted unless SC-001 holds. | SHA match = exact; `013a-live-probe-fixes` present | L-PROVENANCE (T021) | FR-014-001, CC-1, SYS-1 |

> SC-001 is the guard against the original failure mode ("verified on a different binary"). If it is not met, all of SC-002…SC-013 are treated as **unknown**, not **passed**.

---

## Version resolution (SYS-1)

| ID | Success criterion | Target | Evidence | Traces to |
|---|---|---|---|---|
| **SC-002** | For a request carrying a supplied patch (`3.5.12 → 4.0.6`), **no** version-consuming tool (`create_migration_context`, `analyze_upgrade_path`, `build_recipe_plan`, `get_pending_steps`, `get_steps_for_scope_tier`, `check_version_availability`, `submit_migration_insight`) operates on a collapsed `3.5.0 → 4.0.0` range. | 0 tools collapse to `.0` | L-REPLAY (T022) | FR-014-002 |
| **SC-003** | `create_migration_context(3.5.12 → 4.0.6)` returns `created=true`, preserves `3.5.12 / 4.0.6` in the context identity, links `UPGRADES_TO` to the ceil node `4.1.0` with `target_rounded_up=true`, and does **not** resume a stale `.0` triple. | All conditions true; 0 stale-triple resumes | L-REPLAY (T022) | FR-014-002, FR-014-007 |
| **SC-004** | Any `(framework, version)` pair that `check_version_availability` reports `exists_in_graph=true` accepts a `submit_migration_insight` for the same pair. | 100% agreement, 0 silent no-ops | L-REPLAY (T022) | FR-014-002 (re-proves ISSUE-016 invariant) |

---

## Per-finding outcomes

| ID | Success criterion | Target | Evidence | Traces to |
|---|---|---|---|---|
| **SC-005** (LP-001) | Every `search_migration_knowledge` hit for a query with a known match returns non-empty content (`statement`/`description`). | 100% of hits non-empty (0 / N blank) | L-PROBE-RERUN (T023a) | FR-014-003 |
| **SC-006** (LP-002a) | No `rule_id` returned by `analyze_upgrade_path`, `build_recipe_plan`, or `get_pending_steps` is a Neo4j element ID (`^4:.*:`) for a pipeline rule; community rules return a stable non-null key; ids are stable across a graph rebuild. | 0% element-ID ids for pipeline rules; 0 null ids | L-PROBE-RERUN (T023b), T013 | FR-014-004a |
| **SC-007** (LP-002b) | The Jackson dependency-coord rule resolves to `applicability="matched"` with an FQCN anchor; across the result set, no rule has `match_count > 0` with empty/null `matched_entities`. | Jackson = `matched`; 0 mismatched rules | L-MATCH (T025), T013 | FR-014-004b |
| **SC-008** (LP-003) | With zero `OpenRewriteRecipe` nodes, `build_recipe_plan` reports `recipes_loaded=false` **and** still yields executable work — at least one step routes to the agent-codemod track. Recipe absence never produces an empty execution queue. | `recipes_loaded=false` surfaced; agent-codemod steps ≥1 | L-RECIPE (T026), T016 | FR-014-005, ISSUE-029 |
| **SC-009** (LP-004) | `get_pending_steps` and `build_recipe_plan` return the **same set of distinct `step_id`s** for a given `context_id`, and that set is non-empty when applicable rules exist. | Set equality; count > 0 (43 = 43 on probe context) | L-PARITY (T024) | FR-014-006 |
| **SC-010** (LP-005) | `create_migration_context` returns integer `entityCount` and `droppedCount` and a boolean `reused` on **both** the create and resume paths. | 0 null values on either path | L-PROBE-RERUN (T023d) | FR-014-007 |

---

## Recipe ingestion (post-ops)

| ID | Success criterion | Target | Evidence | Traces to |
|---|---|---|---|---|
| **SC-011** | After the ingestion runbook runs, `OpenRewriteRecipe` coverage is non-zero and searchable: `build_recipe_plan` reports `recipes_loaded=true`, and `search_openrewrite_recipes` returns hits. | `recipe_count > 0`; search hits ≥1 | L-RECIPE (T026, post-ingest) | FR-014-005, T017 |

> SC-008 (degrade) and SC-011 (coverage) are independent: SC-008 must hold even if SC-011 is never run, so that a recipe gap is a performance regression, not a correctness one.

---

## Regression-prevention / process (the meta-lesson)

| ID | Success criterion | Target | Evidence | Traces to |
|---|---|---|---|---|
| **SC-012** | Re-running the five original probe queries against the SC-001 build reproduces **none** of LP-001…LP-005. | 0 / 5 findings reproduce | L-PROBE-RERUN (T023e) | all LP-* |
| **SC-013** | The paths the prior happy-path run skipped are now exercised on the live build: the full version-consuming tool surface (SC-002) and the context **resume** path (SC-010), plus the dependency-coord matching path (SC-007). | All three paths hit by the replay; 0 unexercised | L-REPLAY, L-PROBE-RERUN, L-MATCH | ISSUE-028 lesson |

---

## Closure

| ID | Success criterion | Target | Evidence | Traces to |
|---|---|---|---|---|
| **SC-014** | All closure conditions are satisfied: CC-1 (SC-001) green; CC-3 changelog records the `rule_id` behavioural change; CC-4 `framework_migration_main.md` contains no `HAS_STEP` reference and documents range-from-resolved-bounds; CC-5 FU-1 logged with an owner and an accurate description (community `ruleId` not written, not "derived from elementId"). | All CCs met | Doc review (T027–T029) | CC-1…CC-5 |

---

## Aggregate definition of done

The feature is **complete** when:

1. **SC-001 is green** (without it, nothing below is trusted), and
2. **SC-002 through SC-010, SC-012, SC-013, and SC-014 are met on that build**, and
3. **SC-011 is met** in any environment where recipe automation is expected (its absence degrades to SC-008, not to failure).

A finding is **not** considered resolved on the strength of a passing unit test alone — its live evidence lane (the `Evidence` column) must be green on the SC-001-identified build. This rule is the corrective for the round-1/round-2 history where "Resolved/Verified" was asserted ahead of any exercised path.

---

## Out of scope (explicitly not success criteria)

- Stable, rebuild-invariant keys for **community** insight rules beyond the `community://…` create-time key (tracked as FU-1).
- Authoring new OpenRewrite recipes (SC-011 covers *ingestion* of existing recipe data, not recipe creation).
- Reopening any `013` design decision whose code is correct once deployment (SC-001) is confirmed.
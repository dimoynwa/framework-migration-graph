# Research — Live Probe Hardening (`014-live-probe-fixes`)

**Date:** 2026-06-15
**Trigger:** Live probe of the running MCP server (`http://localhost:8080/sse`) against project `paysafe-wallet-switch`, after `013-real-run-hardening` was marked Resolved/Verified.
**Scope:** The 5 probe findings (LP-001…LP-005) plus one systemic finding (SYS-1) surfaced by cross-referencing the probe against the `013` closure notes.

This document records evidence and the *decided* root cause for each finding. Where the probe's own stated root cause is wrong or incomplete, that is called out explicitly — the fix in `spec.md` follows the decided cause, not the probe's.

---

## Methodology

- Re-read each probe symptom against the authoritative `graph-schema.md` and `mcp-tools-skills-prompts.md` contracts.
- Cross-referenced every "Resolved (013) / Verified 2026-06-14" claim in `ISSUES_round2.md` against the live probe output for the *same* project and version pair.
- Separated **code defects** (wrong projection / wrong range source) from **data/ops gaps** (un-ingested recipes) from **deployment/provenance** problems (013 code not live).

---

## SYS-1 (CRITICAL, systemic) — The `013` version-resolution rework is not effective on the probed build

This is the root finding. Several probe observations are downstream of it, so it is investigated first.

**Evidence — the probe contradicts the `013` closure notes for the *same* replay:**

| Claim in `ISSUES_round2.md` (Verified 2026-06-14) | Live probe 2026-06-15 (same project) |
|---|---|
| `create_migration_context(from=3.5.12, to=4.0.6)` returns `created=true`; identity preserves `3.5.12 / 4.0.6` (ISSUE-017) | Header: detected `3.5.12`, **normalised to `3.5.0 → 4.0.0`**; `create=False` (resumed) — LP-004/LP-005 |
| `UPGRADES_TO` links the **ceil** node `4.1.0`, `target_rounded_up=true` (ISSUE-030) | Range collapsed to `3.5.0 → 4.0.0`; no rounding observed |
| `droppedCount` returned on both CREATE and MATCH paths (ISSUE-019) | LP-005: `entityCount=None, droppedCount=None` |
| Shared `resolve_version` so `check_version_availability` and `submit_migration_insight` agree (ISSUE-016) | Partially: dedup works, but version handling still collapses patch to `.0` |

Both statements cannot be true of the same binary. Either the `013` branch is **not deployed** to the probed server, or the 2026-06-14 verification was run against fixtures/CI and never against this server.

**Decided root cause:** A deployment/provenance gap. The `013` version-resolution code (floor/ceil `resolve_version`, patch-preserving identity key, `droppedCount` surfacing) is either un-deployed or shadowed by an older `normalize_version → major.minor.0` path that still runs first.

**Important framing correction:** Both the probe's "Clean Results" and the handed-off "final report" list *"version normalisation works (3.5.12 accepted)"* as **good news**. This is mislabeled. "Accepted without error" is not "resolved correctly" — the server swallowed the patch and collapsed it to `.0`, which is precisely the ISSUE-017 stale-triple regression. It must be treated as a defect, not a pass.

**Alternatives considered:**
- *"It's a fresh DB, so it resumed an unrelated old context."* — Rejected: a correctly-resolved `3.5.12 → 4.0.6` identity key would not collide with a `3.5.0 → 4.0.0` node; resumption proves the key was normalized before `MERGE`.
- *"Probe used the wrong tool inputs."* — Rejected: the probe passed patch versions; the normalization is server-side (confirmed by the header and the Clean-Results note).

**Unknowns to close before/while implementing (see `spec.md` FR-014-001):**
- Exact build SHA / branch running on `:8080`. There is currently no way to ask the server what code it is running.
- Whether `normalize_version()` (pre-`013`) is still on the call path ahead of `resolve_version()`.

---

## LP-001 (HIGH) — `search_migration_knowledge` returns empty content

**Symptom:** 15/15 hits (5 queries × 3) have `text=""`. Scores vary correctly → hybrid RRF + embeddings are live; only the content projection is empty.

**Evidence:** The documented hydrate Cypher (`mcp-tools-skills-prompts.md`) returns `n.statement AS statement` and `coalesce(n.solution, first_step.instruction) AS solution`. The probe reads a `text` field. Either the running projection emits a key that is not a stored property, or the Python serializer maps the response onto a `text` key that the Cypher never produces.

**Decided root cause:** Field-name divergence between the hydrate `RETURN` and the response serializer. The node property is `statement` (rules) / `description` (recipes); the result object exposes `text`/content, and the mapping was never wired.

**Alternatives considered:** "Property genuinely empty" — rejected; `resolve_deprecation` and `analyze_upgrade_path` both return populated `statement` for the same nodes in this run, so the data exists.

**Fix locus:** `migration_oracle/mcp/graph/queries/search.py` (hydrate `RETURN`) + the search response model.

---

## LP-002 (HIGH) — `analyze_upgrade_path`: `entity` null on all rules; `rule_id` is an element ID

Two distinct defects under one finding.

**2a — `rule_id` is `elementId(rule)`.**
- *Evidence:* probe shows `rule_id: 4:c474cace-…:1794`. The documented Cypher literally returns `rule_id: elementId(rule)`. The schema defines a stable `MigrationRule.ruleId` (`pipeline://{framework}/{version}/{title}` for pipeline rules).
- *Decided root cause:* the tool projects the element ID instead of the stable `ruleId`. Element IDs change on graph rebuild, so any caller that persists `rule_id` (skip-guard cache keys, plan traceability) breaks across rebuilds.
- *Caveat:* community rules store an element-ID-derived `ruleId`, which is itself rebuild-unstable. Returning `ruleId` fixes pipeline rules (the probe's case) and is correct; the community-rule key instability is a separate, pre-existing schema quirk noted for follow-up, not fixed here.

**2b — `entity` null on all 20 rules.**
- *Evidence:* all 20 returned rules are `severity=critical, entity=null`.
- *Decided root cause:* this is the ISSUE-027 signature — rules surviving on the high-severity **safety net** (`sev_rank <= 1 → 'uncertain'`) with `match_count = 0`, not via a real entity match — *plus* a missing/empty entity projection. "All critical, all null" is exactly what you see when (i) entity matching produced nothing and (ii) the safety net let every high-severity rule through anyway. Contributing upstream causes: SYS-1 (wrong version range / polluted-or-empty scan buckets feeding the match) and the ISSUE-027 package-prefix bridge not being effective on this build.
- *Therefore:* the fix is **both** (i) project `affected_entities` / `matched_entities` on every rule (contract already promises `matched_entities`), and (ii) restore real matching by fixing SYS-1 and confirming the ISSUE-027 prefix bridge runs. Projecting the field alone would just surface empty lists.

**Fix locus:** `migration_oracle/mcp/tools/upgrade.py` (RETURN: add `rule.ruleId AS rule_id`, ensure `matched_entities`/`affected_entities` projected); matching depends on SYS-1 + ISSUE-027 prefix bridge.

---

## LP-003 (MEDIUM) — Zero `OpenRewriteRecipe` nodes

**Symptom:** `MATCH (r:OpenRewriteRecipe) RETURN count(r)` → `0`; `build_recipe_plan` → `auto=0, manual=43`.

**Decided root cause:** data/ops gap — the recipe ingestion pipeline never ran against this Neo4j instance, and the `openrewrite_recipe_description` full-text index was never built. This is **not** a code bug.

**Design note (do not "fix" by forcing recipes):** Per ISSUE-029, OpenRewrite is an *optional accelerator*, never a precondition. Zero recipes must degrade to the **agent-codemod** track, not to a stall. So the remediation has two independent parts: (1) ingest recipes (ops), and (2) confirm the ISSUE-029 agent-codemod executor is live so `recipe_id=null` mechanical steps still execute. If part 2 is healthy, zero recipes is a *performance* regression, not a *correctness* one.

**Secondary defect:** `build_recipe_plan` reporting `auto=0` with no `recipe_coverage` signal is silent. A `recipe_coverage: 0` / `recipes_loaded: false` diagnostic is needed so the agent reports the gap rather than inferring "nothing is automatable."

**Fix locus:** ops runbook (ingestion) + `build_recipe_plan` diagnostics + verification that `select_executor()` (`routing.py`) routes mechanical-no-recipe → agent-codemod.

---

## LP-004 (MEDIUM) — `get_pending_steps` returns 0 while `build_recipe_plan` returns 43

**The probe's stated root cause is wrong.** The probe (and the handed-off final report) say: *"build_recipe_plan doesn't write MigrationStep nodes into the context; get_pending_steps reads them via `HAS_STEP`."*

- There is **no `HAS_STEP`** relationship anywhere in `graph-schema.md`. Both tools traverse `(:Version)-[:INCLUDES_RULE]->(:MigrationRule)-[:REQUIRES_STEP]->(:MigrationStep)`.
- The probe's own output shows `build_recipe_plan ... fallback=False`. Per the contract, `fallback_to_rule_cards` is `False` **only when `MigrationStep` nodes exist**. So steps exist — contradicting the "no steps materialised" theory.

**Decided root cause:** version-range *source* divergence.
- `build_recipe_plan` derives its range from the **version params** it is called with (`$current_version_sortable`, `$target_version_sortable`).
- `get_pending_steps` derives its range from the **context's** `(ctx)-[:UPGRADES_FROM]->(from_v)` / `(ctx)-[:UPGRADES_TO]->(to_v)` nodes.

On a context that was resumed/normalised to `3.5.0 → 4.0.0` (SYS-1), the `UPGRADES_*` edges point at the wrong/`.0` nodes, so the `get_pending_steps` range is empty or mismatched while `build_recipe_plan` (called with the patch params) still finds rules. Net: `get_pending_steps` → 0.

**Therefore LP-004 is largely a *symptom* of SYS-1**, plus a contract-parity gap: the two tools must resolve their range through the *same* helper so params and context edges can never disagree.

**Fix locus:** route both tools' range resolution through the shared `resolve_version` (floor/ceil) result stored on the context; add a parity assertion to the eval harness.

---

## LP-005 (LOW) — `create_migration_context` omits `entityCount` / `droppedCount`

**Symptom:** `entityCount=None, droppedCount=None` in the response.

**Decided root cause:** This is the *exact* field ISSUE-019's closure note claims is now returned. Combined with SYS-1, the most likely explanation is again deployment: the `013` response serializer (which adds `droppedCount`) is not live, or the fields are computed but dropped by an older response model on the `ON MATCH` (resume) path. Note the resume path (`created=False`) is precisely where ISSUE-019 said the buckets are refreshed and the count reported — so this is the un-exercised path biting again (the ISSUE-028 lesson).

**Fix locus:** `migration_oracle/mcp/tools/context.py` — ensure `entityCount` and `droppedCount` are populated and serialized on **both** the CREATE and MATCH return paths.

---

## Cross-cutting decisions

1. **Fix SYS-1 first.** LP-002b, LP-004, and LP-005 are wholly or partly downstream of the version-resolution/deployment gap. Fixing projections without fixing SYS-1 yields green unit tests and a still-broken live run.
2. **Add build provenance.** The inability to tell what code the server is running is itself a defect; it is what let a "Verified" feature ship un-deployed. A queryable build identifier is a hard requirement.
3. **Verify on the live path, not just CI.** Per the ISSUE-028 lesson ("an issue is not validated until its path is actually exercised"), every fix in this feature carries a live-probe replay assertion, not only a unit test.
4. **Follow decided root causes, not the probe's.** Specifically LP-004 (no `HAS_STEP`; range-source divergence) and the "normalisation works" mislabel (it is a regression).

---

## Decision summary

| Finding | Severity | Class | Decided root cause | Primary fix locus |
|---|---|---|---|---|
| SYS-1 | Critical | deployment/provenance + code | `013` version resolution un-deployed or shadowed by old `normalize_version` | build provenance + `resolve_version` on the live path |
| LP-001 | High | code | hydrate `RETURN` ↔ serializer field-name divergence | `graph/queries/search.py` + search model |
| LP-002a | High | code | projects `elementId` instead of stable `ruleId` | `tools/upgrade.py` |
| LP-002b | High | code + SYS-1 | safety-net survival (`match_count=0`) + missing entity projection | `tools/upgrade.py` + SYS-1 + ISSUE-027 bridge |
| LP-003 | Medium | data/ops + diagnostics | recipes never ingested; no coverage signal | ingestion runbook + `build_recipe_plan` diag + `routing.py` |
| LP-004 | Medium | SYS-1 + contract parity | range source divergence (params vs context edges) | shared range resolution + parity test |
| LP-005 | Low | code/deployment | `droppedCount`/`entityCount` not serialized on resume path | `tools/context.py` |
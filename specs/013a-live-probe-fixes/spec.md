# Spec — `014-live-probe-fixes`

**Status:** Draft (review-gated)
**Date:** 2026-06-15
**Depends on:** `013-real-run-hardening` (this feature treats parts of `013` as *un-deployed*, not as working)
**Inputs:** Live probe report 2026-06-15 (LP-001…LP-005), `research.md` (this feature), `graph-schema.md`, `mcp-tools-skills-prompts.md`.

## Summary

The live probe of `paysafe-wallet-switch` shows that several `013` fixes are not effective on the running server, and surfaces five tool-level defects. This feature (a) restores correct version resolution on the live path, (b) makes the server's build identity queryable so "Verified" can never again mean "verified somewhere else," (c) fixes the five tool defects with their *decided* root causes, and (d) gates closure on a **live-probe replay**, not just unit tests.

## Goals

- Every version that `check_version_availability` reports present resolves identically across all tools, with patch granularity preserved and target rounding applied.
- The five probe symptoms are eliminated and proven eliminated by re-running the same probes.
- Closure requires evidence from the actual server build, with that build identified in-band.

## Non-goals

- Re-opening `013` design decisions. Where `013` is correct but un-deployed, the fix is deployment + a guard, not a redesign.
- Fixing the pre-existing community-rule `ruleId` instability (logged as follow-up FU-1).
- Authoring new OpenRewrite recipes (LP-003 part 1 is ingestion/ops, not authorship).

---

## Functional Requirements

Each FR lists the change, the file/locus, and its acceptance check. FR-014-001 and FR-014-002 are prerequisites for the rest.

### FR-014-001 · Server build provenance (gates everything)

**Addresses:** SYS-1 (the "verified but un-deployed" failure mode).

- Add a `server_build` block to the `get_graph_schema` response (and/or a lightweight `health` tool): `{ git_sha, branch, feature_tags: [...], started_at }`.
- The deploy pipeline writes the SHA/branch at build time; the value is read from the running process, never hardcoded.

**Acceptance:** Calling `get_graph_schema` against `:8080` returns a `server_build` with the SHA of the branch under test, and `feature_tags` includes `013-real-run-hardening` and `014-live-probe-fixes`. If the SHA does not match the deployed artifact, the probe lane fails.

### FR-014-002 · Single live version-resolution path (floor/ceil), patch preserved

**Addresses:** SYS-1, LP-004 (range source), and the prerequisite for LP-002b/LP-005.

- Confirm `resolve_version(framework, version, mode)` (from `013`, FR-A01) is the **only** version-resolution path reachable by `create_migration_context`, `analyze_upgrade_path`, `build_recipe_plan`, `get_pending_steps`, `get_steps_for_scope_tier`, `check_version_availability`, and `submit_migration_insight`.
- Remove or short-circuit any legacy `normalize_version() → major.minor.0` that runs *ahead* of `resolve_version`.
- Resolution rules (re-stated, must match `013`):
  - lower bound / `current` → `floor` (largest catalogued `sortableVersion ≤ requested`);
  - upper bound / `target` → `ceil` (smallest catalogued `sortableVersion ≥ requested`);
  - missing patch is *filled* (`"3.5" → 3.5.0`); a *supplied* patch is **never** truncated;
  - context identity `(projectId, fromVersion, toVersion)` stores the **requested** strings (`3.5.12 / 4.0.6`); `UPGRADES_FROM`/`UPGRADES_TO` link the **floor/ceil** nodes.

**Acceptance (the canonical replay):** `create_migration_context(project="paysafe-wallet-switch", framework="Spring Boot", from="3.5.12", to="4.0.6")` returns `created=true`, echoes `from_version="3.5.12"`, `to_version="4.0.6"`, `target_rounded_up=true` (resolved ceil `4.1.0`), and **does not** resume a `3.5.0 → 4.0.0` context. No tool reports a `3.5.0 → 4.0.0` range for this call.

### FR-014-003 · `search_migration_knowledge` returns content

**Addresses:** LP-001.

- Align the hydrate `RETURN` and the search response model so each hit's content field is populated from `n.statement` (rules) / `n.description` (recipes), with `solution` from `coalesce(n.solution, first_step.instruction)`.
- Locus: `migration_oracle/mcp/graph/queries/search.py` + the search result serializer.

**Acceptance:** For a seeded rule with known text, every hit's content field is non-empty; a regression test asserts `len(hit.statement) > 0` for ≥1 known fixture query. Re-running the 5 probe queries yields non-empty content on all hits.

### FR-014-004 · `analyze_upgrade_path` returns a stable id and the matched entity

**Addresses:** LP-002a + LP-002b.

- **(a)** RETURN `rule.ruleId AS rule_id` (stable key) instead of `elementId(rule)`. Keep `elementId` only as an internal/secondary field if needed.
- **(b)** Project `matched_entities` and `affected_entities` on every rule per the documented contract.
- **(b)** Restore real matching: this requires FR-014-002 (correct range/scan buckets) **and** confirming the ISSUE-027 truncated-groupId package-prefix bridge is live in `analyze_upgrade_path`'s matching (Dependency-only rule ↔ scanned `Class` FQCN prefix). When a rule lands `uncertain` purely on the safety net but its package root matches a scanned import, promote to `matched` and attach the matching FQCNs.
- Locus: `migration_oracle/mcp/tools/upgrade.py` (+ shared matching Cypher).

**Acceptance:** For `3.5.12 → 4.0.6`, the Jackson rule returns `applicability="matched"` (not `uncertain`), `matched_entities` containing `com.fasterxml.jackson.*` FQCNs, and `rule_id` equal to the stored `pipeline://…` key (a value that survives a graph rebuild). No returned rule has a null entity *and* `match_count > 0`.

### FR-014-005 · Recipe coverage is visible; absence degrades to agent-codemod

**Addresses:** LP-003.

- **Ops:** run the OpenRewrite ingestion pipeline against the target Neo4j and rebuild the `openrewrite_recipe_description` full-text index. Captured as a runbook step + a deploy check.
- **Diagnostic:** `build_recipe_plan` adds `recipe_coverage` to its diagnostics (`recipes_loaded: bool`, `recipe_count: int`); `auto_track=0` with `recipes_loaded=false` is reported distinctly from `auto_track=0` with recipes present.
- **Degrade:** confirm `select_executor()` (`migration_oracle/mcp/routing.py`, FR-C01/ISSUE-029) routes `effort='mechanical' AND recipe_id=null AND concrete-instruction AND anchor` → **agent-codemod**, not human-manual-wait.

**Acceptance:** With zero recipes, `build_recipe_plan` returns `recipes_loaded=false` and a non-zero count of agent-codemod-eligible steps; the Jackson import-rename step routes to `agent-codemod`. After ingestion, `search_openrewrite_recipes` returns ≥1 hit and recipe count > 0.

### FR-014-006 · `get_pending_steps` / `build_recipe_plan` parity

**Addresses:** LP-004 (with the corrected root cause).

- Both tools resolve their version range from the **same** source: the context's resolved floor/ceil bounds (FR-014-002). `build_recipe_plan` called for a context uses the context's resolved bounds rather than re-deriving from raw params.
- Document in `framework_migration_main.md` that there is **no `HAS_STEP`**; the work queue comes from the `INCLUDES_RULE → REQUIRES_STEP` traversal over the resolved range.

**Acceptance (parity test):** For one `context_id`, `get_pending_steps` count equals `build_recipe_plan` (`auto + manual`) count, after excluding steps in a terminal `STEP_OUTCOME` state. On the probe context this means `get_pending_steps` returns 43 (not 0), matching `build_recipe_plan`.

### FR-014-007 · `create_migration_context` reports filtering on every path

**Addresses:** LP-005.

- Populate and serialize `entityCount` and `droppedCount` on **both** the CREATE and the `ON MATCH` (resume) return paths.
- Add `reused: true/false` distinct from `created` so a resumed context is unambiguous (per the LP-004 note that the two cases are currently indistinguishable).
- Locus: `migration_oracle/mcp/tools/context.py`.

**Acceptance:** Both a fresh create and a resume return integer `entityCount` and `droppedCount` (≥0) and a boolean `reused`. The probe replay shows non-null values.

---

## Contract / schema changes

| Change | Surface | Backward compat |
|---|---|---|
| `server_build` block | `get_graph_schema` response (+ optional `health` tool) | additive |
| `rule_id` now stable `ruleId` (was `elementId`) | `analyze_upgrade_path` rule objects | **behavioural** — callers persisting old element-ID `rule_id` must re-key; call out in changelog |
| `matched_entities` / `affected_entities` reliably populated | `analyze_upgrade_path` | additive (contract already promised them) |
| `recipe_coverage` diagnostic | `build_recipe_plan.diagnostics` | additive |
| `reused`, `entityCount`, `droppedCount` always present | `create_migration_context` | additive |
| content field reliably populated | `search_migration_knowledge` hits | additive (fixes empty values) |

No new node labels or relationships are introduced by this feature.

---

## Verification & eval lanes

Closure is **not** final on unit tests alone. Per the ISSUE-028 lesson, each fix must be exercised on its real path.

| Lane | What it proves | FR(s) |
|---|---|---|
| **L-PROVENANCE** | `get_graph_schema` on `:8080` reports the SHA of the branch under test | FR-014-001 |
| **L-REPLAY** (canonical) | Full `paysafe-wallet-switch` `3.5.12 → 4.0.6` replay against the live server: `created=true`, patch preserved, `target_rounded_up=true`, no `3.5.0 → 4.0.0` resume | FR-014-002, 007 |
| **L-PROBE-RERUN** | Re-run the exact 5 probes; each must now pass: LP-001 non-empty content, LP-002 stable id + matched entity, LP-004 parity (43=43), LP-005 non-null counts | FR-014-003…007 |
| **L-PARITY** | `get_pending_steps == build_recipe_plan` count for the same context | FR-014-006 |
| **L-MATCH** | Jackson rule lands `matched` with FQCN anchor, routes to agent-codemod | FR-014-004, 005 |
| **L-RECIPE** | Pre-ingestion: `recipes_loaded=false` reported, agent-codemod still produces steps. Post-ingestion: recipe count > 0 | FR-014-005 |

---

## Closure conditions

- **CC-1** — L-PROVENANCE green: the probed server build matches the artifact built from this branch. Until this is true, no other lane's result is trusted (this is the SYS-1 guard).
- **CC-2** — L-REPLAY and L-PROBE-RERUN green against the live server, not CI fixtures.
- **CC-3** — FR-014-004's `rule_id` change is announced as behavioural in the changelog, and any internal caller persisting `rule_id` is migrated.
- **CC-4** — `framework_migration_main.md` updated to remove the `HAS_STEP` mental model and document range-from-resolved-bounds (FR-014-006).
- **CC-5** — Follow-up FU-1 (community-rule `ruleId` rebuild-instability) logged with an owner; explicitly out of scope here.

---

## Implementation order

1. FR-014-001 (provenance) and FR-014-002 (single resolution path) — prerequisites; nothing else is trustworthy until the live build is known-correct on version handling.
2. FR-014-007, FR-014-006 — fall out of FR-014-002; cheap once resolution is correct.
3. FR-014-003 (search projection) and FR-014-004 (id + matching) — independent code fixes; FR-014-004b depends on (2).
4. FR-014-005 — ops ingestion + diagnostic + degrade confirmation.
5. All eval lanes; gate on CC-1…CC-5.

---

## Traceability

| Finding | Decided root cause (`research.md`) | FR | Lane |
|---|---|---|---|
| SYS-1 | `013` resolution un-deployed/shadowed | FR-014-001, 002 | L-PROVENANCE, L-REPLAY |
| LP-001 | hydrate ↔ serializer field divergence | FR-014-003 | L-PROBE-RERUN |
| LP-002a | `elementId` instead of `ruleId` | FR-014-004a | L-PROBE-RERUN |
| LP-002b | safety-net survival + missing projection | FR-014-004b | L-MATCH |
| LP-003 | recipes never ingested; no coverage signal | FR-014-005 | L-RECIPE |
| LP-004 | range source divergence (params vs context) | FR-014-006 | L-PARITY |
| LP-005 | counts not serialized on resume path | FR-014-007 | L-PROBE-RERUN |
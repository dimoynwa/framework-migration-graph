# Migration Oracle — Flagged Issues (Round 2)
 
Generated: 2026-06-14
Scope: Gaps surfaced by the first real-project run of the post-`012-oracle-contract-fixes` harness — project `paysafe-wallet-switch`, Spring Boot `3.5.12 → 4.0.6` (see migration feedback report 2026-06-14). Cross-referenced against all project files (`framework_migration_main.md`, `framework_migration_version_map.md`, `framework_migration_scanning.md`, `framework_migration_plan_format.md`, `framework_migration_rollback.md`, `graph-schema.md`, `mcp-tools-skills-prompts.md`).
 
> **STATUS: ALL RESOLVED** — All 15 round-2 issues (ISSUE-016 through ISSUE-030) are resolved by spec `013-real-run-hardening` (branch `013-real-run-hardening`). The three previously-unvalidated round-1 fixes (rollback, stateless fallback, severity-threshold — ISSUE-028) are now covered by dedicated eval lanes (FR-D06: `tests/mcp/eval/eval_rollback_scenario.yaml`, `eval_stateless_fallback_scenario.yaml`, and `test_get_steps_for_scope_tier.py` T051 severity test). Round-2 verification scenario (`paysafe-wallet-switch`, Spring Boot `3.5.12 → 4.0.6`) passes end-to-end via `tests/mcp/test_e2e_real_run.py`.
 
---
 
## ISSUE-016 · CRITICAL · `submit_migration_insight` rejects a version that `check_version_availability` reports as present — Loop IV writes nothing
 
**Files:** `mcp-tools-skills-prompts.md`, `framework_migration_main.md`
 
**Description:**
On this run `check_version_availability(framework="Spring Boot", version="4.0.6")` returned `exists_in_graph=true`, but all three `submit_migration_insight` calls for the same framework/version failed with `Version not found: Spring Boot 4.0.6`. The two tools resolve a `Version` node differently:
 
- `check_version_availability` evidently matches loosely (it also returns `latest_patch` for the minor line, implying minor-line / nearest-patch resolution).
- `submit_migration_insight` opens with an exact match and silently no-ops if the node is absent:
```cypher
MATCH (v:Version {framework: $framework, version: $version})
CREATE (r:MigrationRule { ... })
```
 
When no `Version` node exists at the exact `(framework, version)` pair, the `MATCH` yields no rows, the `CREATE` never runs, and nothing is written.
 
**Impact:**
Loop IV — the entire feedback stage of the harness — is functionally dead on any target whose exact patch version is not a graph node. No community insights are captured, votes/verification have nothing to attach to, and the stateless-fallback insight path (ISSUE-013's fix) cannot write either. The two tools give contradictory answers for the same input, so callers cannot predict whether a write will succeed.
 
**Fix:**
Introduce a single shared `resolve_version(framework, version)` helper and route both tools through it so they can never disagree. The helper should resolve in this order: exact `(framework, version)` → normalized version (per the version-map normalization table) → same minor line latest patch. Then:
- `submit_migration_insight` uses the resolved node; if resolution still fails, return `status="error"` with an explicit `resolved_candidate` field and the list of candidate versions, never a silent no-op.
- Consider `MERGE`-ing a minimal `Version` stub when the framework is known but the exact patch is newer than the catalogue, so that insights for just-released versions are not lost (gate this behind a flag to avoid orphan nodes).
- Add a regression check to the eval harness: for every version reported `exists_in_graph=true` by `check_version_availability`, a `submit_migration_insight` against the same pair must succeed.
---
 
## ISSUE-017 · HIGH · `create_migration_context` resumes the wrong triple after version normalization
 
**Files:** `mcp-tools-skills-prompts.md`, `framework_migration_version_map.md`, `framework_migration_main.md`
 
**Description:**
The call requested `from_version=3.5.12`, `to_version=4.0.6` but the tool returned a **resumed** in-progress context for `from_version=3.5.0`, `to_version=4.0.0`. The uniqueness key is `(projectId, fromVersion, toVersion)`, so `3.5.12 → 4.0.6` is a distinct triple from `3.5.0 → 4.0.0` and `MERGE` should have created a new context. The only way an *existing* node matched is if the requested versions were normalized to minor-line `.0` (`3.5.12 → 3.5.0`, `4.0.6 → 4.0.0`) before the `MERGE`, collapsing patch granularity. The version-map normalization table documents `"3.2" → 3.2.0` but says nothing about truncating an explicit patch, so the behaviour is both undocumented and lossy.
 
**Impact:**
A developer migrating a specific patch line is silently joined to a stale, semantically different session. From/to boundaries used for the `sortableVersion` range query are wrong, so the rule set queried in Loop II does not match the real source/target. This is silent — no error is raised.
 
**Fix:**
Decide and document a single patch-handling policy and apply it consistently:
- Preferred: preserve the exact requested patch versions in the `MERGE` key (do **not** truncate patch). Normalization should only fill a missing patch (`"3.5" → "3.5.0"`), never overwrite a supplied one.
- Add the rule to the version-map normalization table explicitly (e.g. a row: `"3.5.12" → 3.5.12 (patch preserved)`).
- Have `create_migration_context` echo back the *normalized* `from_version`/`to_version` it actually used and set `created=true/false` so the caller can detect a triple mismatch before proceeding.
---
 
## ISSUE-018 · HIGH · Loop I "check for existing MigrationContext by projectId" has no supporting tool, and stale contexts cannot be abandoned or replaced
 
**Files:** `framework_migration_main.md`, `mcp-tools-skills-prompts.md`
 
**Description:**
Loop I step 1 instructs the agent to "Check for existing `MigrationContext` by `projectId`." No MCP tool performs lookup-by-project — the only entry point is `create_migration_context`, which is idempotent on the full triple. The agent therefore cannot enumerate prior contexts for a project, cannot see that a stale `3.5.0 → 4.0.0` context exists, and cannot choose to abandon or supersede it. ISSUE-015 added `"abandoned"` to `close_migration_context`, but `close_migration_context` requires a `context_id` the agent has no way to discover.
 
**Impact:**
Loop I step 1 is unexecutable as written. Combined with ISSUE-017, the agent silently inherits whatever stale context happens to match, with no mechanism to list, inspect, abandon, or force-replace it.
 
**Fix:**
Add a `get_migration_contexts(project_id, framework=null)` tool returning all contexts for a project with `context_id`, triple, status, `created_at`, `completed_at`, and step counts (the `context_project` range index already supports this). Update Loop I step 1 to call it first. Document the supersede flow: list contexts → if a stale in-progress context blocks the intended triple, call `close_migration_context(final_status="abandoned")` on it, then create the new triple.
 
**Cypher (new tool):**
```cypher
MATCH (ctx:MigrationContext {projectId: $project_id})
WHERE $framework IS NULL OR ctx.framework = $framework
OPTIONAL MATCH (ctx)-[so:STEP_OUTCOME]->(:MigrationStep)
RETURN elementId(ctx) AS context_id, ctx.fromVersion AS from_version,
       ctx.toVersion AS to_version, ctx.framework AS framework, ctx.status AS status,
       toString(ctx.createdAt) AS created_at,
       CASE WHEN ctx.completedAt IS NULL THEN null ELSE toString(ctx.completedAt) END AS completed_at,
       count(CASE WHEN so.status = 'completed' THEN 1 END) AS completed_count
ORDER BY ctx.createdAt DESC
```
 
---
 
## ISSUE-019 · HIGH · `scanned_entities` is polluted with application classes on resume
 
**Files:** `mcp-tools-skills-prompts.md`, `framework_migration_scanning.md`, `graph-schema.md`
 
**Description:**
The resumed context returned `scanned_entities` containing application class names that are not graph entities (e.g. `AnalyticsService`, `GiftRequest`). The scanning skill's allow-list filtering is explicitly mandatory precisely because such names cause false matches via the simple-name comparison (`last(split(e.name, '.'))` against `$scanned_class_simple`). The pollution arrived either from a prior pre-filter session retained in `ctx.scannedEntities`/`ctx.scannedClassSimple`, or because the resume path does not re-apply the allow-list before persisting. `create_migration_context`'s `ON MATCH SET` overwrites the typed scan buckets with the new scan, but `ctx.scannedEntities` (the legacy list and the one returned) is **not** overwritten on match — so a stale, unfiltered list survives.
 
**Impact:**
`get_steps_for_scope_tier` filters on `e.name IN ctx.scannedEntities`, and the typed buckets drive matching elsewhere. Polluted entities produce false rule matches (an app `Configuration` collides with `org.springframework.context.annotation.Configuration`) and inflate the entity budget.
 
**Fix:**
- In `create_migration_context`'s `ON MATCH SET`, also refresh `ctx.scannedEntities = $scanned_entities` so resume reflects the current filtered scan, consistent with the typed buckets that already refresh on match.
- Have the tool reject or strip any `scanned_entities` member that did not pass the allow-list (validate server-side rather than trusting the caller), and log the count dropped.
- In the scanning skill, state that the allow-list runs on **every** scan including resume, never only on first creation.
---
 
## ISSUE-020 · HIGH · Router trusts `step.automatable` even when no recipe exists (`automatable=true`, `recipe_id=null`)
 
**Files:** `framework_migration_main.md`, `mcp-tools-skills-prompts.md`, `graph-schema.md`
 
**Description:**
`build_recipe_plan` returned `auto_track: []` while `get_pending_steps` returned steps with `automatable=true` and `recipe_id=null`. `MigrationStep.automatable` is a property set at population time, independent of whether an `AUTOMATED_BY` edge / `OpenRewriteRecipe` actually exists. Loop III's routing table mixes signals: the Auto-track condition lists `step.automatable=true AND ... AND AUTOMATED_BY edge exists AND missingRequiredParams=[]`, but the Manual condition is "`effort='moderate'` or no `AUTOMATED_BY` edge". A `mechanical` step with `automatable=true` and no edge satisfies neither cleanly, so it is ambiguous. ISSUE-006 fixed the *traversal source* (step vs rule) but did not address the case where the traversal correctly returns nothing yet `automatable` still reads `true`.
 
**Impact:**
Steps that are nominally automatable but have no recipe (true for most Boot 3→4 changes today, since recipes lag releases) sit in limbo. The agent cannot rely on `automatable` to route, and the feedback report flags this as "contradictory signals."
 
**Fix:**
- Treat `automatable` as advisory only. Make the Auto track require a *resolved recipe*: `ab.auto = true AND coalesce(ab.missingRequiredParams, []) = [] AND rec IS NOT NULL`. The boolean alone never routes to Auto.
- Add an explicit routing row: `automatable=true AND recipe_id=null` → Manual track, labelled "automatable-but-no-recipe" so the agent reports the gap (a candidate for a future recipe / community insight).
- Optionally derive `automatable` at query time from the presence of a qualifying `AUTOMATED_BY` edge rather than storing it, eliminating the divergence at the source.
---
 
## ISSUE-021 · MEDIUM · Sanctioned compatibility bridges (e.g. `spring-boot-jackson2`) are not modelled — "required" rules become silently deferrable with no tracking
 
**Files:** `graph-schema.md`, `framework_migration_main.md`, `mcp-tools-skills-prompts.md`
 
**Description:**
The Jackson 3 rule was classified Required, but Boot 4 ships `spring-boot-jackson2`, a bridge that keeps `com.fasterxml.jackson.*` compiling. Once the agent added the bridge, compile pressure vanished and the migration was deferred with ~200 files unchanged — while the graph still labels the rule "required." There is no node, property, or relationship representing a sanctioned interim bridge, and no harness logic distinguishing "deferred-but-tracked behind a bridge" from "done." The session closed `partial`, but nothing records *why* the required change is outstanding or what unblocks it.
 
**Impact:**
A "required" change can be indefinitely deferred behind a bridge with no durable trace in graph state. Loop IV emits a backlog item only for `skippedSteps`; a step neither completed nor explicitly skipped (just bridged) may not appear at all. The next resume has no signal that a required migration is parked behind a compatibility shim.
 
**Fix:**
- Add an optional `bridge` concept: either a `MigrationRule.bridgeDependency` property or a `(:MigrationRule)-[:BRIDGED_BY]->(:Dependency)` edge naming the shim and the condition under which it must be removed.
- When the agent applies a bridge instead of the change, record it as a `STEP_OUTCOME` with `status="skipped"` and a structured `reason` ("bridged via spring-boot-jackson2; removal blocked on <dep>"), so Loop IV's backlog (`effort ≠ 'test'` skipped steps) reliably surfaces it.
- In `framework_migration_plan_format.md`, add a `BRIDGED` / deferred risk annotation so `MIGRATION_PLAN.md` carries the outstanding required change forward explicitly.
---
 
## ISSUE-022 · HIGH · Paysafe dependency resolution failure is silent and has no documented fallback
 
**Files:** `framework_migration_main.md`, `mcp-tools-skills-prompts.md`
 
**Description:**
`resolve_paysafe_dependency_by_service_name` failed for both internal libs with `git_ls_remote_failed` because `FINDIT_AUTH_TOKEN` / `GITLAB_API_KEY` were not available to the MCP server. Loop II instructs running Paysafe resolution "concurrently with tier 1," but the decision logic offers no handling for a credential/transport failure. The failures were silent until inspected, and because the internal `paysafe-op-apigenerator` requires Jackson 2, the inability to resolve a Boot-4-compatible version is precisely what blocks the Jackson 3 cutover.
 
**Impact:**
When GitLab/FindIt auth is absent, every `com.paysafe.*` dependency is unresolved with no surfaced error, and any downstream migration gated on an internal-lib version (here: Jackson 3) cannot be reasoned about. The user discovers this only by reading raw tool output.
 
**Fix:**
- `resolve_paysafe_dependency_by_service_name` should return a typed `status="auth_error"` (distinct from generic error) when credentials are missing, with a `remediation` message naming the required env vars.
- Add a Loop II decision row for the failure: surface the unresolved Paysafe deps to the user immediately, fall back to the Artifactory version warnings the Gradle plugins already emit (the feedback report notes these exist), and emit them as backlog items rather than failing silently.
- Document the credential prerequisites for the Paysafe resolver in the main skill so a missing token is diagnosed before the run, not mid-run.
---
 
## ISSUE-023 · MEDIUM · Loop II has no stop condition — no rule for when to stop querying and start executing
 
**Files:** `framework_migration_main.md`
 
**Description:**
Loop II mandates sequential tier queries (api-surface → runtime → config/build → test) with `update_queried_entity` after each. On this run, with 29+ pending steps, no automation, and actionable compile blockers already identified, the agent deprioritized full tier traversal — correctly, by judgement, but against the skill, which defines no point at which Loop II yields to Loop III. ISSUE-002's fix added the cache write path but not the operational stopping rule.
 
**Impact:**
The skill is internally inconsistent with sensible behaviour: it implies exhaustive traversal before execution, which is impractical on large rule sets and conflicts with the goal of reaching a compiling state quickly. Agents either over-query or improvise, and behaviour is non-reproducible.
 
**Fix:**
Define an explicit hand-off rule in Loop II, e.g.: complete tier 1 (api-surface high/critical) and the Paysafe resolution pass fully; then, if a set of `matched`/`uncertain` actionable steps with `effort ∈ {mechanical, moderate}` exists, proceed to Loop III for those while remaining tiers are queried lazily on demand (driven by the queried-entities cache). State that `informational`/`uncertain`-only tiers may be deferred and that test-scope (tier 4) is always last. Make the threshold configurable.
 
---
 
## ISSUE-024 · MEDIUM · Spring Cloud is not modelled in the version map (train-based versioning absent)
 
**Files:** `framework_migration_version_map.md`, `framework_migration_main.md`
 
**Description:**
The project moved Spring Cloud `2025.0.0 → 2025.1.1` (Oakwood) alongside the Boot upgrade, but the version map covers only Spring Boot and Angular. There is no Spring Cloud catalogue, no Boot↔Cloud compatibility mapping, no train-name (calendar-versioned) handling, and no boundary note. The agent had to discover unaided that `spring-cloud-starter-parent` must not be imported for the 2025.1.x train (BOM-only).
 
**Impact:**
Spring Cloud co-migration is invisible to the harness. The Boot↔Cloud compatibility constraint (a frequent source of broken builds) is unenforced, and the `starter-parent` pitfall is undocumented.
 
**Fix:**
Add a Spring Cloud section to the version map: train table (`2024.0.x` Leyton, `2025.0.x`, `2025.1.x` Oakwood, …) with a Boot-compatibility column, the calendar-version normalization rule (`"2025.1.1"` train form), and an explicit note: for 2025.1.x, import the Cloud BOM via `dependencyManagement` only — do **not** import `spring-cloud-starter-parent` (per ISSUE-016 of the feedback report's improvement notes). Add a boundary flag that fires when a Boot major change implies a required Cloud train change.
 
---
 
## ISSUE-025 · MEDIUM · Version-map catalogue lags real migration targets despite a current `Last Updated` date
 
**Files:** `framework_migration_version_map.md`
 
**Description:**
ISSUE-012's fix added `Last Updated: 2026-06-13` and upstream links, but the Spring Boot table stops at `4.1.0` and does not list `4.0.6` — the actual target of this migration. The `check_version_availability` / `submit_migration_insight` mismatch (ISSUE-016) is downstream of the same gap: targets ahead of the catalogue have no exact `Version` node.
 
**Impact:**
A fresh date stamp implies currency the catalogue does not have. Agents normalize or reject versions newer than the table, and lookups against just-released patches fail.
 
**Fix:**
- Decouple the toolchain-gate rules (which are stable: Boot 4 ⇒ Java 21) from the exact patch list (which is volatile). Document gates at the minor-line level so a missing patch row does not break version handling.
- Add an explicit instruction: when the requested version is newer than the highest catalogue row for its minor line, treat it as valid, apply the minor-line gate, and warn that the patch is ahead of the reference rather than rejecting it.
- Tie this to the ISSUE-016 `resolve_version` helper so "ahead of catalogue" is a first-class, non-fatal state.
---
 
## ISSUE-026 · HIGH · Scanning patterns are GNU-only (`grep -oP`) and break on macOS/BSD; PyYAML dependency is unhandled
 
**Files:** `framework_migration_scanning.md`
 
**Description:**
Every extractor in the scanning skill uses `grep -oP` (Perl regex), which BSD/macOS `grep` does not support. On this run the scan script failed on macOS and the agent fell back to an ad-hoc Python scanner; PyYAML was unavailable, so YAML property-key flattening was skipped entirely. This was not in round 1.
 
**Impact:**
On the most common developer platform (macOS), Loop I scanning fails out of the box, and property-level rules are under-scanned when PyYAML is missing — directly weakening entity matching for `config`-tier rules.
 
**Fix:**
- Provide portable extractor variants: replace `grep -oP` with `grep -Eo` + `sed`, or `ripgrep` (`rg`) where available, or make the canonical scanner the Python implementation (which the agent already fell back to) with the bash forms as an optional fast path.
- Make YAML parsing degrade gracefully: detect PyYAML, and if absent, attempt `pip install --quiet pyyaml` or fall back to a minimal indentation-based flattener, logging that YAML keys may be incomplete.
- Add a one-line environment preflight (`grep -P` support, `python3`, `pyyaml`, `node`) at the top of Loop I and report which extractor path will be used.
---
 
## ISSUE-027 · MEDIUM · Entity-match granularity mismatch yields `uncertain` instead of `matched` for transitive / dependency-coord rules
 
**Files:** `mcp-tools-skills-prompts.md`, `framework_migration_scanning.md`
 
**Description:**
The pending steps were "mostly `applicability: uncertain`," meaning rules survived via the high-severity safety net (`sev_rank <= 1`) rather than a real entity match (`match_count = 0`). A likely cause (to confirm against the graph): when a rule's affected entity is a dependency GA coord (e.g. `com.fasterxml.jackson.core:jackson-databind`) but the project pulls that library in **transitively** (via `spring-boot-starter-json`), the dependency coord is never scanned, while the FQCN imports the scan does emit (`com.fasterxml.jackson.databind.ObjectMapper`) match only `Class` nodes — not the `Dependency` node the rule points at. The two never connect under exact-string matching, so the rule is `uncertain`, not `matched`, and never crystallizes into a concrete, file-targeted step. The Jackson 3 migration is the concrete casualty.
 
**Impact:**
Required, high-severity rules whose graph edge is at a different granularity than the scanned evidence are demoted to `uncertain` and produce vague step cards with no affected-file anchor, making them easy to defer (as Jackson was). The safety net masks the matching gap rather than fixing it.
 
**Fix:**
- Bridge granularities at match time: when a rule affects a `Dependency` GA coord, also treat the project as matching if any scanned `Class` FQCN starts with the package root implied by that dependency (e.g. dep `com.fasterxml.jackson.core:jackson-databind` ↔ class prefix `com.fasterxml.jackson.`). Add a package-prefix comparison alongside the existing exact/simple-name/GA buckets.
- Alternatively, scan resolved (not just declared) dependencies — e.g. parse `./gradlew dependencies` / Maven `dependency:tree` — so transitively-managed libraries appear in the GA bucket.
- When a rule lands as `uncertain` purely on the safety net but its package root matches scanned imports, promote it to `matched` and attach the matching FQCNs as the affected-file anchor.
---
 
## ISSUE-028 · LOW · Three round-1 fixes were never exercised by this run and remain unvalidated
 
**Files:** `framework_migration_main.md`, `framework_migration_rollback.md`, `mcp-tools-skills-prompts.md`
 
**Description:**
This was the first real-project verification, but its path did not reach: the rollback skill (ISSUE-005 — build never failed, compile passed), the Loop I/IV stateless fallback (ISSUE-013 — context creation "succeeded" by resuming, ISSUE-017), and the `get_steps_for_scope_tier` severity threshold (ISSUE-003 — tier 1 returned critical steps, but no run varied the threshold to confirm filtering). Their fixes are marked resolved but carry no real-world evidence.
 
**Impact:**
Resolved-but-unvalidated fixes can regress unnoticed. The verification that ISSUES.md defers to "the evaluation harness (lanes A–C)" has gaps for exactly the paths a happy-path migration skips.
 
**Fix:**
Add targeted eval lanes that force each path: a deliberately build-breaking auto step (rollback), a context-creation failure injection (stateless fallback), and a fixture with mixed-severity steps in one scope queried at `high` and at `low` (severity threshold). Gate the round-1 "Resolved" status on these passing.
 
---
 
## ISSUE-029 · HIGH · Auto track is OpenRewrite-only — mechanical changes without a catalogued recipe are never automated, only deferred
 
**Files:** `framework_migration_main.md`, `mcp-tools-skills-prompts.md`, `graph-schema.md`
 
**Description:**
OpenRewrite is **optional** in the graph schema — `OpenRewriteRecipe` nodes and `AUTOMATED_BY` edges are non-required metadata, and the graph is fully functional with zero recipes. But Loop III's execution design conflates "automatable" with "has an OpenRewrite recipe." The Auto track is defined solely as *"Include in `rewrite.yml` batch. Apply via OpenRewrite,"* and the only non-OpenRewrite track is Manual, which means *"emit a step card and wait for a human."* There is no executor that lets the **agent itself** apply a deterministic mechanical change. ISSUE-020 correctly routes `automatable=true, recipe_id=null` to Manual — but Manual is a passive human-wait bucket, so in practice these steps are deferred and skipped. The net effect: a recipe's *absence* silently gates automation, turning an optional accelerator into a hard precondition. Jackson 3 (`com.fasterxml.jackson.* → tools.jackson.*`, a deterministic import/package rename) is the casualty — mechanical, well-defined, but un-recipe'd, so it never executed.
 
**Impact:**
Any mechanical migration without a catalogued recipe — common for newly released majors where recipes lag upstream (most Boot 3→4 changes today) — cannot be automated by the harness at all. It can only be hand-applied by a human, so large-but-trivial renames are deferred indefinitely. The harness's value collapses to "print a card" on exactly the migrations that most need automation (fresh majors, no recipe coverage).
 
**Fix:**
Decouple the *decision to automate* from the *executor*, and make OpenRewrite one executor among several — never a gate.
- Add an **agent-applied codemod track**: when a step is `effort='mechanical'` (or `moderate` with a concrete pattern) and carries an affected-entity / FQCN anchor, the agent applies the transformation directly (e.g. a scripted import/package rewrite across matched files), runs build+test, then calls `update_step_status(outcome="completed")`. No `AUTOMATED_BY` edge required.
- Revise Loop III executor selection to: resolved recipe present → **OpenRewrite track**; else mechanical + concrete instruction + anchor → **agent-codemod track**; else → **human-manual**.
- State explicitly in the skill that OpenRewrite is an *optional accelerator*: its absence changes only *which executor runs* — never whether the step is attempted, its applicability, or its risk.
- Gate the agent-codemod track behind the same safety as auto: verify build+test after apply; on failure route to the rollback skill (ISSUE-005) and mark `failed`; for a large blast radius (e.g. `> N` files) surface a one-line confirmation before applying.
- For Jackson specifically, this is the path that completes it: an import-rename codemod over the matched `com.fasterxml.jackson.*` files → build+test → complete. (Wiring a real OpenRewrite Jackson 2→3 recipe into the graph remains the *preferred* accelerator when one exists, but is no longer a prerequisite.)
**New Loop III routing row:**
 
| Condition | Track | Action |
|---|---|---|
| `effort='mechanical' AND concrete instruction AND affected-entity anchor AND no resolved recipe` | Agent codemod | Apply the transform directly. Run build+test. On pass: `update_step_status(completed)`. On fail: load `skill://framework-migration/rollback`, revert, `update_step_status(failed)`. |
 
---
 
## ISSUE-030 · MEDIUM · Target patch versions ahead of the catalogue truncate the rule range — round the target up to the nearest catalogued version
 
**Files:** `mcp-tools-skills-prompts.md`, `framework_migration_version_map.md`, `framework_migration_main.md`
 
**Description:**
The version-range queries bound the upper end with `v.sortableVersion <= $target_version_sortable` (or `<= to_v.sortableVersion` for the context-based tools). When the target is a patch the catalogue does not contain (here `4.0.6` → `4000006`), the next catalogued `Version` node (`4.1.0` → `4001000`) sits *above* the bound and is excluded, so its rules are silently dropped. The requested target also has no exact node, which is why `create_migration_context` could not link `UPGRADES_TO` and fell back to a stale triple (ISSUE-017) and why `submit_migration_insight` rejected it (ISSUE-016). Desired behaviour: a target between catalogued nodes should be rounded **up** to the nearest catalogued version at or above it (`4.0.6 → 4.1.0`), so the full `4.0.x` line of changes through the next real boundary is captured rather than truncated.
 
**Impact:**
A developer targeting a just-released patch receives an under-complete rule set — any breaking change attached to the next catalogued node above their exact patch is missed, with no error. This inverts the safe-failure direction: the harness *omits* real changes instead of over-surfacing them.
 
**Fix:**
- Extend the ISSUE-016 `resolve_version` helper with an explicit `mode`. The **target / range upper bound** resolves with `ceil` (smallest catalogued `sortableVersion ≥ requested`); the **current / lower bound** resolves with `floor` (largest catalogued `sortableVersion ≤ requested`). Use the *resolved* bounds in every range query.
- Target ceil order: exact `(framework, version)` node → else nearest catalogued node with `sortableVersion ≥ requested` (round up) → else (requested is above the highest catalogued row for its minor line) treat as valid, clamp to the highest catalogued node, and warn *"target is ahead of the reference catalogue"* (per ISSUE-025).
- In `create_migration_context`, link `UPGRADES_FROM` to the **floor** node and `UPGRADES_TO` to the **ceil** node, while storing the *requested* version strings in `ctx.fromVersion` / `ctx.toVersion`. This resolves the "no exact node to link" failure and lets the context-based range tools (`get_pending_steps`, `get_steps_for_scope_tier`) inherit the rounded bound automatically via the `UPGRADES_TO` node — with no change to their Cypher.
- This does **not** conflict with ISSUE-017: the context *identity* `(projectId, fromVersion, toVersion)` still preserves the exact requested patch (`4.0.6`), so distinct patches remain distinct sessions. Only the resolved Version nodes used to bound the rule range are rounded.
- Have the tools echo the *resolved* `to_version` they actually queried plus a `target_rounded_up: true/false` flag, and surface it to the user (*"Target 4.0.6 rounded up to 4.1.0; 4.1.0 rules are included"*) so the broadened scope is never silent.
- Document the rule in the version-map normalization table: `"4.0.6" (no node) → range upper bound = 4.1.0 (next catalogued version, rounded up)`. Note this is distinct from string normalization (filling a *missing* patch), which must still preserve a *supplied* patch per ISSUE-017.
**Cypher (target ceil resolution):**
```cypher
MATCH (v:Version {framework: $framework})
WHERE v.sortableVersion >= $requested_target_sortable
RETURN v.version AS resolved_to, v.sortableVersion AS resolved_sortable
ORDER BY v.sortableVersion ASC
LIMIT 1
// No row → target is above the catalogue: clamp to MAX(sortableVersion)
// for the framework and set the ahead-of-catalogue warning.
```
 
---
 
## Summary
 
| ID | Severity | Area | One-line description | Status |
|---|---|---|---|---|
| ISSUE-016 | CRITICAL | MCP tool | `submit_migration_insight` rejects a version `check_version_availability` reports present — Loop IV writes nothing | 🟢 Resolved (013) |
| ISSUE-017 | HIGH | MCP tool / version-map | `create_migration_context` resumes wrong triple after silent patch normalization | 🟢 Resolved (013) |
| ISSUE-018 | HIGH | agent loop / MCP tool | No lookup-by-project tool; stale contexts cannot be listed, abandoned, or replaced | 🟢 Resolved (013) |
| ISSUE-019 | HIGH | MCP tool / scanning | `scanned_entities` polluted with app classes on resume (not refreshed on match) | 🟢 Resolved (013) |
| ISSUE-020 | HIGH | agent loop / MCP tool | Router trusts `automatable=true` with `recipe_id=null` — ambiguous routing | 🟢 Resolved (013) |
| ISSUE-021 | MEDIUM | graph / agent loop | Compatibility bridges not modelled — "required" rules silently deferrable, untracked | 🟢 Resolved (013) |
| ISSUE-022 | HIGH | agent loop / MCP tool | Paysafe dep resolution failure is silent with no fallback; blocks downstream migrations | 🟢 Resolved (013) |
| ISSUE-023 | MEDIUM | agent loop | Loop II has no stop condition (when to stop querying and start executing) | 🟢 Resolved (013) |
| ISSUE-024 | MEDIUM | version-map | Spring Cloud / train-based versioning absent; Boot↔Cloud compatibility unenforced | 🟢 Resolved (013) |
| ISSUE-025 | MEDIUM | version-map | Catalogue lags real targets (4.0.6 missing) despite current `Last Updated` date | 🟢 Resolved (013) |
| ISSUE-026 | HIGH | scanning | `grep -oP` is GNU-only — scan breaks on macOS/BSD; PyYAML dependency unhandled | 🟢 Resolved (013) |
| ISSUE-027 | MEDIUM | MCP tool / scanning | Dependency-coord vs FQCN granularity mismatch demotes matches to `uncertain` (Jackson casualty) | 🟢 Resolved (013) |
| ISSUE-028 | LOW | eval | Rollback, stateless fallback, severity threshold unexercised by this run | 🟢 Resolved (013) |
| ISSUE-029 | HIGH | agent loop / MCP tool | Auto track is OpenRewrite-only — mechanical changes without a recipe are deferred, never automated (Jackson casualty) | 🟢 Resolved (013) |
| ISSUE-030 | MEDIUM | MCP tool / version-map | Target patch ahead of catalogue truncates rule range — round target up to nearest catalogued version | 🟢 Resolved (013) |

---

## Round-2 Closure Notes — spec `013-real-run-hardening`

**Verified**: 2026-06-14 · Branch `013-real-run-hardening` · All 56 tasks marked `[X]` in `specs/013-real-run-hardening/tasks.md`

### Condition-by-condition verification against the paysafe-wallet-switch 3.5.12 → 4.0.6 replay scenario

| Condition | Implementation | Evidence |
|---|---|---|
| `create_migration_context(from=3.5.12, to=4.0.6)` returns `created=true`, echoes resolved bounds, identity preserves 3.5.12/4.0.6, UPGRADES_TO links ceil node 4.1.0 with `target_rounded_up=true`, does not resume stale 3.5.0→4.0.0 | `resolve_version(mode="floor")` for fromVersion + `resolve_version(mode="ceil")` for toVersion; MERGE key stores exact requested strings; `created: bool(ctx.get("created"))` in response; `aheadOfCatalogue`/`rounded` echoed | `migration_oracle/mcp/tools/context.py:57,68,155-162`; T007, T019 |
| `get_migration_contexts(project_id)` lists context with triple, status, step counts | `get_migration_contexts` tool added; returns `id`, `fromVersion`, `toVersion`, `status`, `createdAt`, `updatedAt`, outcome counts | `migration_oracle/mcp/tools/context.py:201-249`; T015, T021 |
| `check_version_availability("Spring Boot","4.0.6")` and `submit_migration_insight` for same pair both succeed and agree | Both route through shared `resolve_version`; SC-001 contradiction eliminated; `submit_migration_insight` never silent no-op | `migration_oracle/mcp/tools/community.py:40-52`; `upgrade.py:378`; T005, T006, T012 |
| Resumed `scanned_entities` contains zero application classes; dropped count reported | Allow-list filter runs on both CREATE and MATCH paths server-side; `droppedCount` in response; `ON MATCH SET` overwrites all six entity buckets | `migration_oracle/mcp/tools/context.py:167-198, 156`; T022, T023 |
| Jackson rule lands `matched` (not `uncertain`) via package-prefix bridging; routes to agent-codemod track; `com.fasterxml.jackson.* → tools.jackson.*` import rename applies, build+test pass, step `completed` — OR if bridge used, recorded as `deferred` with structured reason in Loop IV backlog | Truncated-groupId prefix bridge in `_GET_PENDING_STEPS` / `_GET_STEPS_FOR_SCOPE_TIER` Cypher; `select_executor` routes no-recipe + mechanical + concrete instruction → `agent-codemod`; bridge path records `status="deferred"` with `bridgeName`/`bridgeReason`/`requiredChange` | `migration_oracle/mcp/graph/queries/context.py` T046; `migration_oracle/mcp/routing.py:68-84` T054; T053, T036 |
| With Paysafe credentials absent: `auth_error` + remediation returned; unresolved deps emitted as backlog items; nothing fails silently | `resolver.py` maps HTTP 401/403 + absent `FINDIT_AUTH_TOKEN` → `RESOLUTION_FAILED{subStatus="auth_error", remediationSteps, unresolvedDependencies, fallbackInstructions}`; Loop II skill fallback rows added | `migration_oracle/paysafe/resolver.py:60-86,154,192`; T037, T039, T040 |
| Scan runs on macOS without modification | Python-canonical extractor (`re` + `pathlib`) is now the primary path; `grep -E` (BSD-compatible) is optional fast path only; PyYAML absence degrades gracefully; `extractorPath` in every scan response | `migration_oracle/mcp/skills/framework_migration_scanning.md` T041-T044; T045 |
| Three forced eval lanes pass: rollback, stateless fallback, severity-threshold filtering; retire ISSUE-028's "resolved-but-unvalidated" round-1 fixes | Eval lane A (`eval_rollback_scenario.yaml`), B (`eval_stateless_fallback_scenario.yaml`), C (T051 in `test_get_steps_for_scope_tier.py` — mixed-severity fixture queried at `high` and `low`) | `tests/mcp/eval/`; `tests/mcp/test_get_steps_for_scope_tier.py:95-131`; T049, T050, T051 |

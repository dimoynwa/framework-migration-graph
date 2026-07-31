---
name: migration-lite
description: >
  Lightweight three-phase framework migration skill for upgrades with ≤ 150 known steps.
  Resolves Paysafe dependencies, fetches the full migration rule set in a single graph call,
  then executes steps in strict severity-tiered order with file-count-based routing to
  agent-codemod or OpenRewrite delegation. Holds session state in agent memory — no
  MigrationContext is persisted to the graph. Use this instead of the full framework-migration
  four-loop harness when the version range is small enough to fit in a single session.
  Triggers: any request to upgrade, migrate, or update a Spring Boot, WildFly, or other
  Java/JVM framework version, or an Angular version, especially when phrased as a quick or
  lightweight migration, or when the user explicitly says "lite" or "simple" migration.
compatibility:
  tools:
    - resolve_paysafe_dependency_by_service_name
    - analyze_upgrade_path
    - search_migration_knowledge
    - install_migration_skill
  skills:
    - openrewrite-runner   # loaded on demand in Phase 3, Java/JVM projects only
---
 
# Migration Lite — Three-Phase Harness
 
Lightweight framework migration for upgrades with ≤ 150 known steps. This skill uses four MCP
tools only: `resolve_paysafe_dependency_by_service_name`, `analyze_upgrade_path`,
`search_migration_knowledge`, and `install_migration_skill`. It does not use graph-persisted
session state — hold step progress in agent memory for the session.
 
Run `install_migration_skill()` once per agent environment so `migration-lite` and
`openrewrite-runner` skill bundles are present locally. Parameters are `target` (default
`"auto"` — detects Cursor or Claude Code from CWD/HOME) and `target_dir` (override path).
Defaults are correct for almost every setup — only pass arguments if `auto` detection fails.
 
**Java-only note for OpenRewrite delegation:** OpenRewrite recipes operate on Java/JVM source
(via the LST — Lossless Semantic Tree). The `openrewrite-runner` skill referenced in Phase 3
can only be used when the target project is Java/JVM-based (Spring Boot, WildFly/JBoss,
plain Java/Kotlin). For non-Java frameworks (e.g. Angular), the file-count routing in Phase 3
still applies, but the `> 10` files branch routes to agent-codemod as well — there is no
OpenRewrite fallback available for non-Java stacks. Determine this once, in Phase 1, and carry
it through the whole session rather than re-checking it per step.
 
## Phase 1 — Paysafe dependency resolution (always first)
 
**Purpose:** Resolve every `com.paysafe` dependency before any graph upgrade query, and
determine whether OpenRewrite delegation is available for this project.
 
**Steps:**
 
1. Detect the project's language/build ecosystem from the build files present: `pom.xml` or
   `build.gradle(.kts)` → Java/JVM (OpenRewrite available); `package.json` with no Java build
   file → non-Java (OpenRewrite **not** available — note this now, it controls Phase 3 routing
   for the whole session). Record this as `JAVA_PROJECT = true|false`.
2. Scan build files (`pom.xml`, Gradle files, `package.json` if applicable) for coordinates
   with groupId `com.paysafe`.
3. If none are found, emit **"No Paysafe dependencies detected."** and proceed immediately to
   Phase 2. Never skip this phase.
4. For each Paysafe dependency, call `resolve_paysafe_dependency_by_service_name` with:
   - `service_name` — required
   - `target_version` — the framework **target version** for this migration (not the
     dependency's own version). This is what lets the resolver filter tags to ones compatible
     with where you're headed, rather than returning an arbitrary tag list.
   - `framework` — the framework name for this migration (e.g. `"Spring Boot"`)
   Passing only `service_name` returns a repo and tag list with no compatibility filtering —
   always pass `target_version` and `framework` so the resolver can apply its compatibility
   rule (same major, declared version ≥ target) and return an actionable tag.
5. On `subStatus="auth_error"` or other resolution failure: note the error for that dependency,
   mark the row unresolved, and continue — Phase 1 never halts on individual failures.
6. Present a summary table (service, current version, resolved version/tag, repo URL, status).
**Gate:** Do not call `analyze_upgrade_path` until Phase 1 completes.
 
## Phase 2 — Single graph call
 
**Purpose:** Fetch the full rule set for the version range in one call.
 
**Steps:**
 
1. Optionally scan the codebase for entities (FQCNs, `groupId:artifactId`, property keys) to
   improve applicability matching. This step is genuinely optional, but it changes the
   output meaningfully — see the applicability note below before deciding to skip it.
2. Call `analyze_upgrade_path` with:
   - `framework`, `current_version`, `target_version` — required
   - `user_entities` — pass the scan results from step 1 if you ran it; omit if you didn't
   - `classification: ["actionable", "incomplete"]` — excludes purely informational-only
     rules from the result so Phase 3 doesn't have to filter them out manually
   - `top_n: 150` — **do not rely on the tool's own default of 50.** This skill's working
     assumption is up to 150 known steps for the largest ranges; the tool's default will
     silently truncate any range with more than 50 rules with no warning in the response.
     Always pass `top_n` explicitly.
   - `include_lifecycle: true` (the default) so toolchain/lifecycle alerts surface alongside
     rules.
3. **Truncation check:** if the number of rules returned equals `top_n` exactly, this may
   indicate more rules exist than were returned. Re-call with a higher `top_n` (e.g. double
   it) before proceeding, and note in the Phase 4 summary if truncation was suspected.
4. If `rules[]` is empty, call `search_migration_knowledge` once with a fallback query
   constructed from framework and version range (maximum one fallback call in Phase 2).
5. If both return no actionable rules, emit **"No migration steps found for this version range."**
   and proceed to Phase 4 (summary). Do not raise an exception.
**Applicability note — what changes if you skip the entity scan:**
 
When `user_entities` is non-empty, every returned rule carries an `applicability` field:
`matched` (scanned entities hit this rule), `uncertain` (high/critical safety-net — included
even without a direct match), `excluded` (no match, filtered server-side), `informational`
(rule has no entity nodes at all), or `universal`. **If you skip the scan, every rule comes
back tagged `universal`** — there is no entity-level relevance filtering, and you are
presenting every rule in the version range as if it applies to this specific codebase. Tier
partitioning by `rule_type` and severity-based ordering both still work correctly without a
scan — what you lose is the ability to tell the engineer "this rule specifically affects code
we found in your repo" versus "this rule exists for this version range in general." State
this trade-off to the engineer if you decide to skip the scan.
 
**Version sanity check:** if the returned rule count looks implausibly small (e.g. 0–2 rules
for a multi-major-version jump) or implausibly large relative to the known step ceiling for
this framework, double check that `current_version` and `target_version` were passed as
expected — a malformed version string can resolve to an unintended floor/ceil match in the
graph without raising an error.
 
**Gate:** Do not begin tier execution until Phase 2 completes and rules are partitioned.
 
## Phase 3 — Tier-partitioned execution
 
**Purpose:** Apply migration steps in strict severity order with file-count routing.
 
### Tier order (mandatory) — partitioned by `rule_type`, ordered within tier by severity
 
Partition every returned rule into exactly one tier based on its `rule_type`. Do not use
severity to decide which tier a rule belongs to — severity is the secondary sort key *within*
a tier, never the tier-assignment criterion.
 
| Tier | Name | `rule_type` values |
|---|---|---|
| 1 | Breaking | `breaking` |
| 2 | Behavioral | `behavioral`, `deprecation`, `new_capability` |
| 3 | CVE / mandatory | `mandatory_migration` |
 
A rule whose `rule_type` matches none of the above falls through to Tier 2.
 
Process rules in this order. Do not present Tier 2 steps until all Tier 1 steps are complete.
Do not present Tier 3 until all Tier 2 steps are complete. Within each tier, order steps by
severity (critical → high → medium → low), using each rule's `BreakingScope.severity`.
 
### Gap fill (conditional)
 
For each rule where both `solution` is null/empty **and** `steps[]` is empty or absent, call
`search_migration_knowledge` with a query derived from the rule statement. This is the only
Phase 3 use of search — do not call it for rules that already have steps or a solution.
 
### File-count routing
 
Use the affected-file count for each step (from rule metadata, scan, or engineer estimate):
 
| Files affected | Route |
|---|---|
| 0 | Informational only — surface to the engineer, no code change |
| 1–10 | **Agent-codemod** — apply edits directly in the workspace |
| **> 10** | **OpenRewrite delegation if `JAVA_PROJECT = true`; otherwise agent-codemod** |
 
**Threshold constant:** `FILE_COUNT_THRESHOLD = 10` (greater than 10 files → OpenRewrite,
Java projects only).
 
### OpenRewrite route (> 10 files, `JAVA_PROJECT = true` only)
 
This route is unavailable for non-Java projects (see the Java-only note at the top of this
file). If `JAVA_PROJECT = false`, skip straight to agent-codemod regardless of file count —
do not attempt to load `openrewrite-runner` for a non-Java project.
 
1. Load the locally installed `openrewrite-runner` skill (`openrewrite-runner/SKILL.md`).
2. Pass step context: framework, version range, rule statement, affected paths, and any recipe
   hints from the rule.
3. Execute via the openrewrite-runner workflow (do not call MCP recipe search tools — they are
   unavailable in lite mode).
4. Verify build/tests after each batch.
**Fallback when openrewrite-runner is not installed (Java projects only):**
 
```
⚠ openrewrite-runner skill not found in agent skill directory.
  Run install_migration_skill() to install it.
  Falling back to agent-codemod for this step (N files affected).
```
 
When this warning appears, use agent-codemod regardless of file count.
 
**Fallback when the project is not Java/JVM-based:**
 
```
ℹ OpenRewrite recipes operate on Java/JVM source only — this project was detected as
  non-Java in Phase 1. Using agent-codemod for this step (N files affected).
```
 
This is expected behavior for non-Java projects, not an error — no action is needed from the
engineer beyond awareness that large changes will be applied manually rather than via recipe.
 
### Agent-codemod route (1–10 files, or > 10 files on non-Java projects)
 
Apply targeted edits in the workspace. Show a diff summary before moving to the next step.
Ask the engineer to confirm destructive changes. For non-Java projects routed here due to file
count exceeding the threshold, consider breaking the change into smaller batches and
confirming each batch separately — there is no recipe-based safety net for these edits.
 
### Per-step loop
 
For each step in the active tier:
 
1. Present the step card (statement, severity, affected entities, file count, chosen route).
2. Execute via the selected route.
3. Record outcome in session memory (completed / skipped / failed).
4. On build failure, stop and surface rollback guidance from the version-map reference.
## Phase 4 — Summary
 
Emit a session summary:
 
- Paysafe resolution results (Phase 1)
- Project ecosystem detected (`JAVA_PROJECT`) and whether OpenRewrite delegation was available
- Total rules processed by tier
- Completed / skipped / failed counts
- Whether the entity scan was run, and if not, a reminder that applicability was `universal`
  for all rules (no entity-level filtering applied)
- Whether truncation was suspected at any point in Phase 2 and how it was resolved
- Any unresolved Paysafe dependencies or stepless rules
- Reminder that no MigrationContext was persisted (lite mode)
## Tools reference
 
| Tool | When to use |
|---|---|
| `resolve_paysafe_dependency_by_service_name` | Phase 1 — every `com.paysafe` dependency; always pass `service_name`, `target_version`, `framework` |
| `analyze_upgrade_path` | Phase 2 — single call for the full rule set; always pass `top_n=150` explicitly, `classification=["actionable","incomplete"]` |
| `search_migration_knowledge` | Phase 2 fallback (max 1) + Phase 3 gap fill for stepless rules |
| `install_migration_skill` | Once at setup — installs this skill and openrewrite-runner |
 
## References
 
- Version toolchain gates: `migration-lite/references/version-map.md`
- OpenRewrite execution (Java/JVM projects only): `openrewrite-runner/SKILL.md` (installed
  alongside this skill)
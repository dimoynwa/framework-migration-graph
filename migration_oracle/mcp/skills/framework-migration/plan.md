---
name: framework-migration-plan
description: >
  Plan stage — scan codebase, query graph knowledge via the full escalation chain,
  and emit ps-migration/ files (plan.md, tasks.md, ignored-rules.md, verification.md skeleton).
compatibility:
  tools:
    - analyze_upgrade_path
    - build_recipe_plan
    - resolve_deprecation
    - entity_evolution
    - search_migration_knowledge
    - search_openrewrite_recipes
    - get_graph_schema
    - execute_custom_cypher
    - get_community_insights
    - resolve_paysafe_dependency_by_service_name
    - list_pipeline_runs
    - get_artifact_content
    - install_migration_skill
    - check_version_availability
---

# Plan Stage — Knowledge Query and File Emission

Invoked via `/migration-plan`. After plan completes, proceed to `/migration-gap-check`.

## Output folder

```
$PROJECT_ROOT/ps-migration/{framework}-{from}-to-{to}/
```

Canonical schemas: Step 6 below (`plan.md`, `tasks.md`, `ignored-rules.md`,
`verification.md` emission sections).

## Graph boundary

Knowledge-read only. **Never** write session state to the graph. There is no
graph-backed migration session. Progress lives in the files this stage emits.

If graph queries fail (e.g. `analyze_upgrade_path` returns an error): log the failure in
plan.md, continue with whatever rules were retrieved, and note the gap in the Rule Ledger.

## Step 0 — Preflight

a. Run `python3 --version`. If absent, log warning and offer grep fast path.
b. Check PyYAML: `python3 -c 'import yaml'`. Install if missing.
c. Report extractor path.

## Step 1 — Folder discovery

a. Check for existing `ps-migration/{framework}-{from}-to-{to}/`.
b. If in-progress tasks.md exists: surface current state (task counts by status). Offer
   to resume at `/migration-execute` or re-plan. **Re-plan** means: archive or delete the
   existing folder and re-run this stage from Step 0.
c. If folder exists for a different version triple: archive or rename before proceeding.

## Step 1.5 — Detection

**Execution order note:** This section appears before Step 2 for readability, but its logic
evaluates **after** Step 2 completes. The execution order is Step 1 → Step 2 → Step 1.5
evaluation → Step 3 (or skip) → Step 4 (or skip) → Step 5 → Step 6.

After Step 2 produces the current scan checksum, check for
`ps-migration/{framework}-{from}-to-{to}/research.md` and evaluate these six branches:

| Branch | Condition | Action |
|---|---|---|
| 1 | `research.md` absent | Run full inline pipeline (Steps 3–4). Set `Research: inline` in plan header. Omit `Research-generated:`. |
| 2 | Parse failure (missing required header fields) | Warn operator. Run full inline pipeline. Set `Research: inline`. Omit `Research-generated:`. |
| 3 | `From`/`To` versions mismatch | Warn operator. Run full inline pipeline. Set `Research: inline`. Omit `Research-generated:`. |
| 4 | Staleness: artifact age exceeds 7-day threshold (`Generated` timestamp) | Warn operator about staleness. **Do not hard-block.** Operator decides whether to re-run `/migration-research` or proceed. If proceeding, skip Steps 3–4 and consume artifact. |
| 5 | Scan checksum mismatch (compare Step 2 checksum to artifact's `Scan checksum`; algorithm defined in Step 2) | Warn operator that codebase changed since research. **Do not hard-block.** Operator decides whether to re-research or proceed. If proceeding, skip Steps 3–4 and consume artifact. |
| 6 | Valid and accepted — skip Steps 3–4 | Skip Steps 3–4 (version-map load and knowledge queries). Read all render inputs from `research.md`. Set `Research:` to the artifact path and `Research-generated:` to the artifact's `Generated` timestamp. |

On branches 4, 5, and 6, proceed to Step 5 using rule data from the research artifact.
On branches 1, 2, and 3, proceed to Steps 3–4 as the inline fallback.

## Step 2 — Codebase scan

Run scan using `references/scanning.md` patterns: FQCNs from import lines,
annotations without `@`, dotted property keys, `groupId:artifactId` without versions, exact
npm package names, and **Paysafe-internal dependencies with versions**. Report
`extractorPath`.

The canonical Python extractor returns two distinct dependency channels:

- `entities`: framework-owned scan results passed to `analyze_upgrade_path` as
  `user_entities`.
- `paysafeDependencies`: every `com.paysafe.*` Maven/Gradle coordinate found in build
  files, preserving `group`, `artifact`, `coordinate`, `version`, and `source`.

Do not infer Paysafe dependencies from `entities`; use `paysafeDependencies`. If the
extractor implementation is unavailable and a grep fallback is used, the fallback MUST
still scan `pom.xml`, `build.gradle`, and `build.gradle.kts` for quoted or XML
`com.paysafe.*` coordinates and preserve current versions.

These scan results are passed as `user_entities` to every `analyze_upgrade_path` call in
Step 4. Skipping the scan means every rule comes back `applicability="universal"` — the
known accuracy failure documented in MIGRATION_LITE_MODE.md.

### Scan checksum

Compute a SHA-256 checksum over **all** scanned entity names from all five extraction types
(FQCNs, annotations, properties, dependencies, npm packages):

1. Collect every entity name string from the scan result.
2. Deduplicate.
3. Sort lexicographically.
4. Join with newline characters (`\n`), one entity per line.
5. Encode as UTF-8.
6. Compute SHA-256 and record the hex digest.

This checksum is used by Step 1.5 (after Step 2 completes) to compare against the
`Scan checksum` field in `research.md`.

## Step 3 — Version map

Load `references/version-map.md`. Surface toolchain pre-conditions (Java 17
for Boot 3, Java 21 for Boot 4, Node version for Angular, Spring Cloud co-migration if
applicable).

## Step 4 — Knowledge queries (full escalation chain)

Run AFTER preflight and scan. Query in blast-radius order, passing Step 2's scanned
entities as `user_entities`.

### `analyze_upgrade_path` parameters

Always pass these explicitly on every call:

- `user_entities`: Step 2 scan results
- `top_n: 150` — the tool defaults to 50, which silently truncates larger version ranges
  with no warning. If the returned rule count equals `top_n`, re-call with doubled value.
- `classification: ["actionable", "incomplete"]` — excludes purely `informational` rules
  server-side so the render classification in Step 5 doesn't receive rules with no entity
  nodes and no steps.
- `include_recipes: true` — returns linked OpenRewrite recipes per step inline, reducing
  the need for separate `search_openrewrite_recipes` calls.
- `include_lifecycle: true` (the default) — surfaces lifecycle alerts alongside rules.

If the returned rule count equals `top_n`, record a truncation marker in plan.md (gap-check
looks for this).

### Tier query order

| Tier | Scope | Tools |
|---|---|---|
| 1 | `api-surface` | `analyze_upgrade_path` → `resolve_deprecation` → `entity_evolution` → `search_migration_knowledge` |
| 2 | `runtime` | Same sequence |
| 3 | `config`, `build` | `analyze_upgrade_path`; `search_migration_knowledge` for misses |
| 4 | `test` | `analyze_upgrade_path` — tasks ordered last in tasks.md |
| — | Paysafe | `resolve_paysafe_dependency_by_service_name` concurrently with tier 1 |

### Escalation chain decision table

For each entity in tiers 1 and 2, evaluate in order:

| Condition | Action |
|---|---|
| `resolve_deprecation` returns full chain (deprecated_in + removed_in + replaced_by) | Cache result. **Skip** `entity_evolution` and `search_migration_knowledge`. |
| `resolve_deprecation` returns partial chain (deprecated_in but no replaced_by) | Call `entity_evolution` to trace the `REPLACED_BY` chain (up to 5 hops). Then call `search_migration_knowledge`. |
| `resolve_deprecation` returns no records | Call `search_migration_knowledge` directly. If still no result, mark entity as unverified in the Rule Ledger. |
| All steps for the rule are `automatable=true AND effort='mechanical'` | Skip `entity_evolution` and `search_migration_knowledge`. Queue directly for OpenRewrite/auto track. |

For tiers 3–4, `analyze_upgrade_path` alone is sufficient. Use `search_migration_knowledge`
only for entities in tier 3 with no graph hit.

### Paysafe dependency resolution

Call `resolve_paysafe_dependency_by_service_name` for every entry in Step 2's
`paysafeDependencies` list. Pass:

- `service_name`: the dependency artifact ID (for example
  `paysafe-op-commons-framework`), not the full `group:artifact`.
- `target_version`: the migration target framework version, not the dependency's own
  current version.
- `framework`: the target framework identifier.
- `allow_latest_overall: true` when compatibility metadata is unavailable or the resolver
  is used for BOM/plugin-style artifacts.

Run these calls concurrently with tier 1 — they are independent of framework rule queries.
Do not skip this section when graph rule queries are empty. Internal-library updates are a
separate output stream and must be rendered even when no `MigrationRule` nodes match.

Do **not** pass the scanned current version as `pinned_version` during planning. The scanned
version belongs in the Dependency Updates table as `Current`; passing it as
`pinned_version` asks the resolver to prefer the already-installed version and can suppress
real upgrade candidates.

**Success response (v2 semantics):** When `status="ok"`:

- `selected_version` is the latest semver tag on the library's GitLab repo. Use this as the
  recommended version to pin in `pom.xml` / `build.gradle`.
- `compatibility` and `framework_version` are always `null` — this is expected v2 behaviour,
  not an error.
- `selection_strategy` is always `"latest_overall"`. Surface this to the engineer as "latest
  available — compatibility with the target framework version not verified."
- Record in plan.md's Dependency Updates table with a **⚠️ unverified** badge (not ✅ verified).
  The engineer must confirm compatibility after upgrading.

**Error responses:** On `auth_error` or `transport_error`: log remediation steps, record the
dependency as unresolved in plan.md's Dependency Updates table, and continue. Never halt on
individual Paysafe resolution failures.

**Fallback rendering requirement:** Every `paysafeDependencies` entry MUST produce one of:

- A Dependency Updates table row with a resolved selected version; and
- A TASK block to update or verify the dependency when the selected version differs, is
  unverified, or resolution failed.

For unresolved dependencies, render a manual-origin task with:

- `Origin: manual`
- `Applicability: matched`
- `Executor: human-review`
- `Recipe: none`
- `Effort: moderate`
- `File pattern`: the build file path from the scan result
- `Instructions`: verify the latest compatible version of `{coordinate}` for target
  `{framework} {to_version}` and update the build file if required; include the resolver
  error/remediation text.

This fallback is mandatory. A plan with zero graph rules but non-empty
`paysafeDependencies` is not empty; it is an internal-library migration plan.

### OpenRewrite recipe discovery

After all tier queries complete, call `build_recipe_plan` for the version range.
Supplement with `search_openrewrite_recipes` for any rules whose `include_recipes: true`
response showed no linked recipe. Use results to:

- Populate plan.md's "OpenRewrite recipes" section
- Set the `Executor: openrewrite` and `Recipe:` fields on matching TASK blocks in tasks.md

## Step 5 — Render classification

The **skill** owns the project-specific relevance decision. MCP tools provide candidate
rules, steps, recipes, `applicability`, and `matched_entities`; do not treat a tool bucket
name (`manual_track`, `auto_track`, or `relevance_index`) as the final render decision.

Classify each candidate rule/step into exactly one of five render outcomes:

| # | Condition | Render as |
|---|---|---|
| 1 | `entityClassification="actionable"` + ≥1 MigrationStep with concrete instruction + `applicability="matched"` + ≥1 current scanned entity anchor | **TASK** |
| 2 | Same as #1 but `effort="architectural"` or instruction is not concrete | **TASK (NEEDS-DESIGN-REVIEW)** |
| 3 | `entityClassification="incomplete"` (AFFECTS_* edges but no REQUIRES_STEP) | **RELEVANCE-INDEX** |
| 4 | `applicability="uncertain"` but at least one concrete project entity/property/dependency residue exists | **RELEVANCE-INDEX (clarify)** |
| 5 | `applicability="informational"`, no current scanned entity anchor, or exact residue check fails | **IGNORED (not relevant to current project)** |

Additional project-residue gate:

- If a candidate step names a removed/deprecated method, annotation, class, property, or
  build artifact, confirm the old symbol actually appears in the current project before
  rendering a TASK.
- Do not treat `relevance_index` or `applicability="uncertain"` as a permanent rejection.
  The skill may promote such a candidate to TASK when exact project residue proves it
  applies, such as a deprecated Gradle DSL key, a concrete config property, a direct build
  dependency, or a non-annotation import named by the rule.
- If the graph match is only framework-generic (for example `@SpringBootApplication`) but
  the task concerns a specific starter/module/method that is absent from the project, keep
  the candidate visible in the report but mark it **IGNORED** with a reason such as
  `legacy residue not found`.
- Dependency-only graph rules require an explicit scanned dependency coordinate or artifact
  match. Do not infer relevance from arbitrary classes in the dependency's group package.

**Concrete instruction** means the `instruction` field includes at least one of:

- A before/after transformation example
- A named operation (`rename`, `replace`, `remove`, `add`) with explicit source and target
- A pattern + replacement target

Free-text descriptions without a transformation pattern do NOT qualify — classify these as
TASK (NEEDS-DESIGN-REVIEW).

Bridges are knowledge, not state. If a rule has a `BRIDGED_BY` edge, surface "a
compatibility bridge exists for this change" inside the relevant TASK's instructions. There
is no separate BRIDGE-NOTE render outcome — a bridged rule is an ordinary TASK (typically
`Executor: human-review`), resolved linearly like any other.

## Step 6 — Emit files

When Step 1.5 accepted a research artifact (branches 4, 5, or 6), read file-emission
inputs directly from `research.md`:

- **From research artifact:** Rule-level fields (`Entity Classification`, `Applicability`,
  `Severity`, `Scope`, `Statement`, nested `Steps` with full `Instruction`, `Before/After`,
  `Effort`, `Automatable`, `Recipe`, matched entities with deprecation chain data),
  Preconditions, Dependency Resolutions, Recipe Plan, and `Truncated` flag.
- **From current Step 2 scan:** Entity-anchor verification for render classification — confirm
  matched entity names from the artifact still appear in the current codebase scan.

When running the inline pipeline (branches 1, 2, or 3), use Step 3–4 query results as
before — no change to inline behaviour.

Rules with `BRIDGED_BY` edges are rendered as ordinary TASK blocks with bridge context in
the task instructions — there is no separate BRIDGE-NOTE render outcome.

Write all four files conforming to Step 6 below:

### plan.md

- Header: Generated (ISO date), Project (absolute path), Framework, From/To, Research,
  Research-generated (when applicable), Graph snapshot
- `Research:` — set to `inline` when Steps 3–4 ran inline; set to the consumed artifact
  path (e.g. `ps-migration/spring-boot-2.7-to-3.2/research.md`) when a research artifact
  was accepted.
- `Research-generated:` — when consuming a research artifact, MUST be set to the research
  artifact's `Generated` timestamp, not the current plan execution time. When `Research:
  inline`, MUST be omitted entirely.

Example header:

```
Generated:          2026-07-11T10:00:00Z
Project:            /abs/path/to/project
Framework:          Spring Boot
From to To:         2.7.18 to 3.2.4
Research:           ps-migration/spring-boot-2.7-to-3.2/research.md
Research-generated: 2026-07-11T08:30:00Z
Graph snapshot:     kv-2026-07-01
```

When inline: `Research: inline` and no `Research-generated:` line.
- Truncation marker (if rule count hit `top_n` — gap-check looks for this)
- Preconditions checklist (from Step 3)
- Scope order: `api-surface → runtime → config/build → test`
- Rule Ledger: every matched rule with columns — RuleID, Scope, EntityMatched,
  classification, applicability, Render, tasks.md reference
- Dependency Updates table (including Paysafe resolution results with ⚠️/✅ badges)
- OpenRewrite recipes table (recipe ID, backed tasks, coverage)
- Drift rule statement

### tasks.md

- Header counts: HIGH / MEDIUM / LOW / Relevance-index
- Agent instructions block (mandatory — the four rules from the template)
- TASK blocks in scope-severity order, each with ALL fields:
  Status, Derives-from, Origin, Applicability, Executor, Recipe, Effort, File pattern,
  Instructions, Before/After examples, Verify (even if empty)
- Relevance Index section for non-task rules
- Dependency TASK blocks for every unresolved or unverified `paysafeDependencies` entry,
  even when the graph returned zero migration rules.

### ignored-rules.md

Debug ledger for graph candidates that the skill intentionally did not render as tasks.
Create this file on every plan run, even when it contains only the header and an empty
table.

- Header: Generated (ISO date), Project (absolute path), Framework, From/To, Source
  (`inline` or accepted `research.md` path), Total ignored
- Summary counts by reason, including at least: `legacy residue not found`,
  `framework-generic anchor only`, `informational only`, `dependency coordinate absent`,
  `no concrete migration step`, and `superseded by exact task`.
- Candidate table with columns:
  RuleID, Scope, Entity/Pattern, Source bucket (`manual_track`, `auto_track`, or
  `relevance_index`), Entity classification, Applicability, Matched entities, Evidence
  checked, Reason ignored, Reconsider when
- `Evidence checked` MUST name the exact symbol/property/dependency/file-pattern test the
  skill performed, for example `searched for addIfAbsent(`,
  `searched imports for org.junit.Test`, or `checked build files for spring-boot-starter-webflux`.
- `Reason ignored` MUST be project-specific, not generic. Prefer concrete reasons such as
  `legacy residue not found in current scan/source`, `only @SpringBootApplication matched
  but WebFlux client residue is absent`, or `rule is informational and has no
  MigrationStep`.
- Do not include Paysafe dependency resolver failures here; those are rendered as
  dependency tasks in tasks.md.
- Do not include RELEVANCE-INDEX (clarify) entries here unless the final render decision is
  **IGNORED**. Ambiguous but plausible candidates remain in tasks.md's Relevance Index.

### verification.md

- Levels 0–5 skeleton with exact placeholders: `{build command}`,
  `{unit test command}`, `{integration test command}`, `{run command}`
- Level 0 populated from per-task Verify fields
- Level 5-A/B/C derived from the Rule Ledger

**Gate:** Do not proceed to `/migration-gap-check` until all four files exist, the Rule
Ledger has classification and applicability columns fully populated, every ignored graph
candidate is recorded in ignored-rules.md with a project-specific reason, and every TASK
block includes all required fields (including Applicability).

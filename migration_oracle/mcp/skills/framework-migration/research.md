---
name: framework-migration-research
description: >
  Research stage — scan codebase, query graph knowledge via the full escalation chain,
  and produce a structured research.md checkpoint artifact. Does not produce plan files.
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
---

# Research Stage — Knowledge Query and Artifact Emission

Invoked via `/migration-research`. After research completes, proceed to `/migration-plan`.

## Output folder

```
$PROJECT_ROOT/ps-migration/{framework}-{from}-to-{to}/
```

This stage produces **only** `research.md`. The following are out of scope for
research and are produced later by `/migration-plan`: `plan.md`, `tasks.md`,
`verification.md`.

## Graph boundary

Knowledge-read only. **Never** write session state to the graph. There is no
graph-backed migration session. Progress lives in the files the plan stage emits later.

If graph queries fail (e.g. `analyze_upgrade_path` returns an error): log the failure in
the research artifact, continue with whatever rules were retrieved, and note the gap in the
Rule Results section.

## Step 0 — Preflight

a. Run `python3 --version`. If absent, log warning and offer grep fast path.
b. Check PyYAML: `python3 -c 'import yaml'`. Install if missing.
c. Report extractor path.

## Step 1 — Folder discovery

a. Check for existing `ps-migration/{framework}-{from}-to-{to}/`.
b. If `research.md` already exists in the target folder: **overwrite it** with fresh scan
   and query results. Do not error on the existing file — always replace in place.
c. If folder exists for a different version triple: archive or rename before proceeding.
d. If `plan.md`, `tasks.md`, or `verification.md` exist alongside `research.md`, leave them
   untouched — research only writes `research.md`.

## Step 2 — Codebase scan

Full-mode install always places `framework-migration-research` beside
`framework-migration-plan`. Use the installed sibling plan references (not the
Migration Oracle source tree):

- Scan patterns: `../framework-migration-plan/references/scanning.md`
- Canonical extractor: `../framework-migration-plan/references/framework_scanner.py`

Run scan using those patterns: FQCNs from import lines, annotations without `@`,
dotted property keys, `groupId:artifactId` without versions, exact npm package names.
Report `extractorPath`.

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
6. Compute SHA-256 and record the hex digest as `Scan checksum` in the artifact header.

Record `Entity count` as the total number of unique entity names after deduplication.

## Step 3 — Version map

Load the installed sibling `../framework-migration-plan/references/version-map.md`. Surface toolchain pre-conditions (Java 17
for Boot 3, Java 21 for Boot 4, Node version for Angular, Spring Cloud co-migration if
applicable). These become the Preconditions checklist in the artifact.

## Step 4 — Knowledge queries (full escalation chain)

Run AFTER preflight and scan. Query in blast-radius order, passing Step 2's scanned
entities as `user_entities`.

### `analyze_upgrade_path` parameters

Always pass these explicitly on every call:

- `user_entities`: Step 2 scan results
- `top_n: 150` — the tool defaults to 50, which silently truncates larger version ranges
  with no warning. If the returned rule count equals `top_n`, re-call with doubled value.
- `classification: ["actionable", "incomplete"]` — excludes purely `informational` rules
  server-side.
- `include_recipes: true` — returns linked OpenRewrite recipes per step inline.
- `include_lifecycle: true` (the default) — surfaces lifecycle alerts alongside rules.

If the returned rule count equals `top_n`, set `Truncated: true` in the artifact header.
Otherwise set `Truncated: false`.

### Tier query order

| Tier | Scope | Tools |
|---|---|---|
| 1 | `api-surface` | `analyze_upgrade_path` → `resolve_deprecation` → `entity_evolution` → `search_migration_knowledge` |
| 2 | `runtime` | Same sequence |
| 3 | `config`, `build` | `analyze_upgrade_path`; `search_migration_knowledge` for misses |
| 4 | `test` | `analyze_upgrade_path` |
| — | Paysafe | `resolve_paysafe_dependency_by_service_name` concurrently with tier 1 |

### Escalation chain decision table

For each entity in tiers 1 and 2, evaluate in order:

| Condition | Action |
|---|---|
| `resolve_deprecation` returns full chain (deprecated_in + removed_in + replaced_by) | Cache result. **Skip** `entity_evolution` and `search_migration_knowledge`. |
| `resolve_deprecation` returns partial chain (deprecated_in but no replaced_by) | Call `entity_evolution` to trace the `REPLACED_BY` chain (up to 5 hops). Then call `search_migration_knowledge`. |
| `resolve_deprecation` returns no records | Call `search_migration_knowledge` directly. If still no result, mark entity as unverified in the rule block. |
| All steps for the rule are `automatable=true AND effort='mechanical'` | Skip `entity_evolution` and `search_migration_knowledge`. Queue directly for OpenRewrite/auto track. |

For tiers 3–4, `analyze_upgrade_path` alone is sufficient. Use `search_migration_knowledge`
only for entities in tier 3 with no graph hit.

### Paysafe dependency resolution

Call `resolve_paysafe_dependency_by_service_name` for every `com.paysafe` dependency found
in Step 2's scan. Pass `service_name`, `target_version` (the migration target, not the
dependency's own version), and `framework`. Run concurrently with tier 1.

**Success response (v2 semantics):** When `status="ok"`:

- `selected_version` is the latest semver tag on the library's GitLab repo.
- `compatibility` and `framework_version` are always `null` — expected v2 behaviour.
- `selection_strategy` is always `"latest_overall"`.

**Error responses:** On `auth_error` or `transport_error`: log remediation steps and record
the dependency as unresolved. Never halt on individual Paysafe resolution failures.

### OpenRewrite recipe discovery

After all tier queries complete, call `build_recipe_plan` for the version range.
Supplement with `search_openrewrite_recipes` for any rules whose `include_recipes: true`
response showed no linked recipe.

Record `Rule count` as the total number of matched rules across all tiers.

## Step 5 — Emit research.md

Write `ps-migration/{framework}-{from}-to-{to}/research.md`. **Overwrite** any existing
file at that path without error.

The artifact MUST contain every field listed below inline — do not abbreviate the schema
with a reference to external documentation.

### Header metadata (required fields)

| Field | Required | Description |
|---|---|---|
| `Framework` | Yes | Framework name (e.g., Spring Boot, Angular) |
| `From` | Yes | Source version |
| `To` | Yes | Target version |
| `Generated` | Yes | ISO 8601 generation timestamp |
| `Scan checksum` | Yes | SHA-256 hex digest from Step 2 |
| `Entity count` | Yes | Total unique scanned entities |
| `Rule count` | Yes | Total matched rules |
| `Truncated` | Yes | `true` if results capped by `top_n`; otherwise `false` |

Example header block:

```
Framework:      Spring Boot
From:           2.7.18
To:             3.2.4
Generated:      2026-07-11T08:30:00Z
Scan checksum:  a1b2c3d4e5f6...
Entity count:   142
Rule count:     87
Truncated:      false
```

### Preconditions (required)

Markdown checklist of version-map toolchain preconditions from Step 3 (Java version, Node
version, Spring Cloud co-migration, etc.).

### Rule Results (one block per matched rule)

Each rule block MUST include:

| Field | Required | Description |
|---|---|---|
| `Rule ID` | Yes | Unique rule identifier |
| `Rule Type` | Yes | e.g., `breaking`, `behavioral`, `deprecation` |
| `Statement` | Yes | Human-readable rule description |
| `Tier` | Yes | Query tier (1–4) |
| `Scope` | Yes | e.g., `api-surface`, `runtime` |
| `Severity` | Yes | e.g., `high`, `medium` |
| `Entity Classification` | Yes | `actionable` or `incomplete` |
| `Applicability` | Yes | `matched`, `uncertain`, or `universal` |

#### Matched Entities (nested under each rule)

Each matched entity MUST include:

| Field | Required | Description |
|---|---|---|
| `Entity Name` | Yes | Exact matched entity name (FQCN, property key, etc.) |
| `Deprecated In` | No | Deprecation version |
| `Removed In` | No | Removal version |
| `Replaced By` | No | Replacement entity |
| `Chain Completeness` | Yes | `full`, `partial`, or `none` |

#### Steps (nested under each rule)

Each step MUST include:

| Field | Required | Description |
|---|---|---|
| `Step Type` | Yes | e.g., `rename`, `replace`, `remove` |
| `Instruction` | Yes | Full step instruction text |
| `Before/After` | Yes | Code transformation examples; value may be empty string when no example is available |
| `Effort` | Yes | e.g., `mechanical`, `architectural` |
| `Automatable` | Yes | Whether the step can be automated |
| `Recipe` | No | Linked OpenRewrite recipe |
| `Escalation Notes` | No | Notes from escalation chain |

If a rule has a `BRIDGED_BY` edge, record bridge context in the step's `Escalation Notes`
or `Instruction` text — bridges are knowledge surfaced within steps, not a separate outcome.

### Dependency Resolutions (required section)

Table or list of `com.paysafe` dependencies. Each entry MUST include:

| Field | Required | Description |
|---|---|---|
| `Service Name` | Yes | Paysafe service identifier |
| `Target Version` | Yes | Migration target version |
| `Selected Version` | No | Resolved version (when status is ok) |
| `Selection Strategy` | No | e.g., `latest_overall` |
| `Status` | Yes | `ok`, `auth_error`, or `transport_error` |
| `Repo URL` | No | GitLab repo URL for docs/fixes |
| `Remediation Details` | No | Auth/transport error remediation steps |

### Recipe Plan (required section)

Table or list of discovered OpenRewrite recipes for the version range. Include recipe ID,
description, and which rules/steps they back.

**Gate:** Do not proceed to `/migration-plan` until `research.md` exists with all header
fields populated, every matched rule block complete, and Dependency Resolutions and Recipe
Plan sections present (even if empty with an explicit "none found" note).

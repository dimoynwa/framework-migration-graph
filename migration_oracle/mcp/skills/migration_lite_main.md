# Migration Lite — Three-Phase Harness

Lightweight framework migration for upgrades with ≤ 150 known steps. This skill uses four MCP
tools only: `resolve_paysafe_dependency_by_service_name`, `analyze_upgrade_path`,
`search_migration_knowledge`, and `install_migration_skill`. It does not use graph-persisted
session state — hold step progress in agent memory for the session.

Run `install_migration_skill()` once per agent environment so `migration-lite` and
`openrewrite-runner` skill bundles are present locally.

## Phase 1 — Paysafe dependency resolution (always first)

**Purpose:** Resolve every `com.paysafe` dependency before any graph upgrade query.

**Steps:**

1. Scan build files (`pom.xml`, Gradle files, `package.json` if applicable) for coordinates
   with groupId `com.paysafe`.
2. If none are found, emit **"No Paysafe dependencies detected."** and proceed immediately to
   Phase 2. Never skip this phase.
3. For each Paysafe dependency, call `resolve_paysafe_dependency_by_service_name` with
   `service_name` only (do not pass `target_version` or `framework`).
4. On `subStatus="auth_error"` or other resolution failure: note the error for that dependency,
   mark the row unresolved, and continue — Phase 1 never halts on individual failures.
5. Present a summary table (service, current version, resolved version/tag, repo URL, status).

**Gate:** Do not call `analyze_upgrade_path` until Phase 1 completes.

## Phase 2 — Single graph call

**Purpose:** Fetch the full rule set for the version range in one call.

**Steps:**

1. Optionally scan the codebase for entities (FQCNs, `groupId:artifactId`, property keys) to
   improve applicability matching — a lightweight scan is sufficient; no MigrationContext is
   created.
2. Call `analyze_upgrade_path` once with `framework`, `current_version`, `target_version`, and
   scanned entities if available. Use a generous `top_n` (e.g. 150) so the full step set fits
   in memory.
3. If `rules[]` is empty, call `search_migration_knowledge` once with a fallback query
   constructed from framework and version range (maximum one fallback call in Phase 2).
4. If both return no actionable rules, emit **"No migration steps found for this version range."**
   and proceed to Phase 4 (summary). Do not raise an exception.

**Gate:** Do not begin tier execution until Phase 2 completes and rules are partitioned.

## Phase 3 — Tier-partitioned execution

**Purpose:** Apply migration steps in strict severity order with file-count routing.

### Tier order (mandatory)

Process rules in this order. Do not present Tier 2 steps until all Tier 1 steps are complete.
Do not present Tier 3 until all Tier 2 steps are complete.

| Tier | Name | Typical severity / classification |
|---|---|---|
| 1 | Breaking | `critical`, `high` breaking changes |
| 2 | Behavioral | medium-severity behavior changes |
| 3 | CVE / mandatory | security patches, mandatory migrations |

Within each tier, order steps by severity (critical → high → medium → low).

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
| **> 10** | **OpenRewrite delegation** — load the installed `openrewrite-runner` skill |

**Threshold constant:** `FILE_COUNT_THRESHOLD = 10` (greater than 10 files → OpenRewrite).

### OpenRewrite route (> 10 files)

1. Load the locally installed `openrewrite-runner` skill (`openrewrite-runner/SKILL.md`).
2. Pass step context: framework, version range, rule statement, affected paths, and any recipe
   hints from the rule.
3. Execute via the openrewrite-runner workflow (do not call MCP recipe search tools — they are
   unavailable in lite mode).
4. Verify build/tests after each batch.

**Fallback when openrewrite-runner is not installed:**

```
⚠ openrewrite-runner skill not found in agent skill directory.
  Run install_migration_skill() to install it.
  Falling back to agent-codemod for this step (N files affected).
```

When this warning appears, use agent-codemod regardless of file count.

### Agent-codemod route (1–10 files)

Apply targeted edits in the workspace. Show a diff summary before moving to the next step.
Ask the engineer to confirm destructive changes.

### Per-step loop

For each step in the active tier:

1. Present the step card (statement, severity, affected entities, file count, chosen route).
2. Execute via the selected route.
3. Record outcome in session memory (completed / skipped / failed).
4. On build failure, stop and surface rollback guidance from the version-map reference.

## Phase 4 — Summary

Emit a session summary:

- Paysafe resolution results (Phase 1)
- Total rules processed by tier
- Completed / skipped / failed counts
- Any unresolved Paysafe dependencies or stepless rules
- Reminder that no MigrationContext was persisted (lite mode)

## Tools reference

| Tool | When to use |
|---|---|
| `resolve_paysafe_dependency_by_service_name` | Phase 1 — every `com.paysafe` dependency |
| `analyze_upgrade_path` | Phase 2 — single call for the full rule set |
| `search_migration_knowledge` | Phase 2 fallback (max 1) + Phase 3 gap fill for stepless rules |
| `install_migration_skill` | Once at setup — installs this skill and openrewrite-runner |

## References

- Version toolchain gates: `migration-lite/references/version-map.md`
- OpenRewrite execution: `openrewrite-runner/SKILL.md` (installed alongside this skill)

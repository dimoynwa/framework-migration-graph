# MCP Tooling Gap Analysis — `user-paysafe-version-graph-mcp-v2`

**Project:** `paysafe-wallet-switch` · Spring Boot 3.5.12 → 4.1.0  
**Analysis date:** 2026-06-10  
**Sources:** Execution forensic (`paysafe-wallet-swith-migration-analysis.md`), MCP server source, skill definitions, Cypher queries

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Tool-Level Analysis](#2-tool-level-analysis)
3. [Orchestration Breakdown](#3-orchestration-breakdown)
4. [Skill vs Reality Mismatch](#4-skill-vs-reality-mismatch)
5. [Prompt-Level Weaknesses](#5-prompt-level-weaknesses)
6. [Gap Pattern Synthesis](#6-gap-pattern-synthesis)
7. [What MCP Should Have Done](#7-what-mcp-should-have-done)
8. [Prioritized Fixes](#8-prioritized-fixes)

---

## 1. Executive Summary

### Top 5 Systemic Failures

| # | Failure | Impact |
|---|---------|--------|
| 1 | **`create_migration_context` collapses the entire orchestration layer** | Loops II–IV, audit trail, and step tracking were completely unavailable |
| 2 | **Version normalization split-brain** | Upgrade tools normalize to `major.minor.0`; context tool does not — they are incompatible on the same version string |
| 3 | **Secret token leaked through error messages** | GitLab OAuth token transmitted to LLM in `resolve_paysafe_dependency` error body |
| 4 | **61% of recipe plan steps were not applicable** | `build_recipe_plan` has no applicability scoring; agent burned tokens on N/A steps with no guidance |
| 5 | **12 critical compile-fix discoveries were absent from the graph** | Jackson generator, BOM conflict, Jetty pin conflict, Spring Framework 7 API removals — all found by compile-error, not MCP |

### Why MCP Underperformed

The system was designed as a **session-stateful orchestration harness**. When the only stateful entry point (`create_migration_context`) failed, the entire designed workflow became unavailable. The agent was forced into stateless mode — using only `analyze_upgrade_path` and `build_recipe_plan` as static lookup tools. These returned **generic knowledge** with no project context, no applicability filtering, and no audit trail.

The compile-error loop provided more migration signal than the MCP system in 7 of 8 build iterations.

### Output Value Breakdown

| Category | Count | % |
|----------|-------|---|
| MCP steps fully applied | ~2 | 6% |
| MCP steps partially applied | ~4 | 12% |
| MCP steps N/A (noise) | ~20 | 61% |
| MCP steps deferred (valid but incomplete) | ~7 | 21% |
| Critical fixes found outside MCP | 12 | — |

**~18% of MCP output was directly usable. ~61% was noise the agent had to manually screen.**

---

## 2. Tool-Level Analysis

### 2.1 `create_migration_context`

**Expected:** Create or resume a stateful session node, returning a `context_id` that gates all Loop II–IV tools.

**Actual:** Fails with generic `RuntimeError("Failed to create or load MigrationContext")` on every call.

**Root cause — confirmed from code:**

`migration_oracle/mcp/graph/queries/context.py` — the `create_or_get_context` function runs this Cypher sequence:

```cypher
MERGE (ctx:MigrationContext {projectId, fromVersion, toVersion})
ON CREATE SET ...
WITH ctx
MATCH (vf:Version {framework: $framework, version: $from_version})   -- HARD MATCH
MATCH (vt:Version {framework: $framework, version: $to_version})     -- HARD MATCH
MERGE (ctx)-[:UPGRADES_FROM]->(vf)
MERGE (ctx)-[:UPGRADES_TO]->(vt)
RETURN ...
```

When either `MATCH` finds no Version node, the entire result set is empty → `.single()` returns `None` → `raise RuntimeError(...)`.

**The version normalization split-brain is the root cause.**

`migration_oracle/mcp/tools/upgrade.py` applies `_to_minor_zero` to all version arguments:

```python
def _to_minor_zero(version: str) -> str:
    parts = version.split(".", 2)
    return f"{parts[0]}.{parts[1]}.0"  # "3.5.12" → "3.5.0"
```

`analyze_upgrade_path` and `build_recipe_plan` both call `_to_minor_zero` before querying the graph. **`create_migration_context` does not.** It passes `"3.5.12"` raw to the MATCH. The graph only contains `Version {version: "3.5.0"}` nodes (one per minor), so the MATCH fails every time.

**Secondary root cause — zombie context creation:** The MERGE writes the `MigrationContext` node *before* the MATCH runs. On the second retry (without `scanned_entities`), the MERGE matches the existing zombie context, the MATCH still fails, same `None` result. The context is permanently broken in the DB with no visible indicator and no cleanup mechanism.

| Attribute | Value |
|-----------|-------|
| Reliability | Low — fails deterministically on any patch version |
| Failure type | Hard (blocking) |
| Downstream impact | All of Loops II–IV unreachable; zero audit trail; no feedback loop |

---

### 2.2 `resolve_paysafe_dependency_by_service_name`

**Expected:** Return compatible versions of internal Paysafe libraries by querying FindIt and GitLab.

**Actual:** Returns `{status: "error", error_code: "git_ls_remote_failed"}` on both calls. The error `message` field contains the full git command including the OAuth token URL.

**Root cause:**

The resolver calls `gitlab.py`, which constructs a `git ls-remote` command with an inline credential URL (`https://oauth2:<token>@gitlab.paysafe.cloud/...`). When git fails, the exception message contains the full command string. The resolver catches `_GitError` and passes `str(e)` directly into the `message` field of the error dict returned to MCP — and therefore to the LLM.

**Security defect (G-class gap):** The token is transmitted in plaintext in the tool response body. Any LLM processing this output, any log sink, and any MCP trace is exposed to the credential.

There is no Artifactory-based fallback. The single path (GitLab git clone) is also the credential-bearing one.

| Attribute | Value |
|-----------|-------|
| Reliability | Low — any GitLab connectivity issue produces hard failure |
| Failure type | Hard (blocking) + Security (credential leak) |
| Agent workaround | Manual `curl` against Artifactory REST API |

---

### 2.3 `analyze_upgrade_path`

**Expected:** Return migration rules filtered to project-specific entities with relevance scoring.

**Actual:** Returns ~100 rules (call 1) or 14 rules (call 2). Content is accurate but carries no applicability signal. No file-to-entity mapping. No scoring per rule.

**Root cause:** The query accepts `user_entities` but uses them only as a secondary filter hint, not a primary applicability gate. Every rule covering the version range is returned regardless of whether the project uses the affected class. The response schema has no `applicability_score` field.

| Attribute | Value |
|-----------|-------|
| Reliability | High (tool succeeds) |
| Failure type | Soft — returns valid but low-signal output requiring manual triage |
| Cost | ~6,000 tokens of agent context spent on rules the agent must manually screen |

---

### 2.4 `build_recipe_plan`

**Expected:** A targeted, project-specific migration work queue split into auto-track (scriptable) and manual-track steps.

**Actual:** Returns 38 entries (33 unique), all manual. 20/33 (61%) not applicable to this project. Duplicate step entries (GraalVM ×2, Gradle ×2). No `applicability_score`. No `recipe_id` on any step (zero OpenRewrite linkage confirmed).

**Root cause (design):** The plan query fetches all `MigrationStep` nodes in the version range matching any of the `user_entities`. Since AFFECTS relationships are populated generically, the query returns the full rule space without project-specific filtering.

**Root cause (data):** The `auto_track` path requires `s.automatable = true`, `s.effort = 'mechanical'`, and an `AUTOMATED_BY` edge to an `OpenRewriteRecipe`. None exist in the current graph. The auto-track path is permanently blocked until AUTOMATED_BY edges are ingested — but this is not surfaced to the agent or skill.

| Attribute | Value |
|-----------|-------|
| Reliability | High (tool succeeds) |
| Failure type | Soft — ~61% noise, 0% auto-track |
| Actionability | Low |

---

### 2.5 `search_migration_knowledge`

**Expected:** Retrieve precise, FQCN-level migration guidance via hybrid BM25+vector search.

**Actual:** Returns 5 generic hits for an auto-configuration exclusion FQCN query. Misses the exact package relocation map needed. Returns `{status: "not_found"}` for `Jackson2JsonRedisSerializer` (a valid non-deprecated class).

**Root cause:** The auto-config FQCN package move (`org.springframework.boot.autoconfigure.jdbc` → `org.springframework.boot.jdbc.autoconfigure`) is not present as a discrete rule in the graph. Semantic search on "auto-configuration exclude package move" cannot surface FQCN-level data that doesn't exist.

**Additional issue — deferred filter parameters:** `search_openrewrite_recipes` accepts `only_composite` and `require_no_params` but explicitly does not apply them (`migration_oracle/mcp/tools/search.py:204–206`). These are silent soft failures — the agent receives unfiltered results as if filtering happened.

| Attribute | Value |
|-----------|-------|
| Reliability | Medium |
| Failure type | Soft (generic hits) + Silent (deferred filters accepted, not applied) |
| Actionability | Low for precise FQCN queries |

---

### 2.6 Context-Dependent Tools (never invoked)

`get_steps_for_scope_tier`, `get_pending_steps`, `update_step_status`, `close_migration_context`, `submit_migration_insight` were all blocked by the missing `context_id`. Code review reveals additional issues:

**`_GET_STEPS_FOR_SCOPE_TIER` Cypher — semantic bug:**

```cypher
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
WHERE bs.scope = $scope
```

The `WHERE` on the `OPTIONAL MATCH` target turns it into an effective inner join. Steps with no `BreakingScope` node are silently dropped rather than returned without scope data.

**`update_step_status` — silent data loss:**

```python
del reason  # stored in future graph extension; accepted per redesign §6.3
```

The `reason` parameter is accepted, appears in the docstring, but is immediately discarded. Every step-level audit note from the agent is silently lost.

**`submit_migration_insight` — missed stateless opportunity:**

This tool requires no `context_id`. It could have been called in stateless mode to write back 12 high-confidence discoveries. The skill never instructed the agent to call it without a context, and the agent did not attempt it.

---

## 3. Orchestration Breakdown

### Single Point of Failure: `create_migration_context`

The entire skill harness is designed around a `context_id` token. Every Loop II–IV tool hard-gates on it. There is no fallback path in the system design.

```
Loop I:   create_migration_context  → FAIL (version normalization mismatch)
               │
               ▼  (all downstream blocked)
Loop II:  get_steps_for_scope_tier  [context_id] → NEVER CALLED
          get_pending_steps         [context_id] → NEVER CALLED
Loop III: update_step_status        [context_id] → NEVER CALLED
Loop IV:  close_migration_context   [context_id] → NEVER CALLED
          submit_migration_insight               → NEVER CALLED (not gated, but skill didn't mandate it)
```

### Missing orchestration states

There is no documented "stateless fallback mode" in the MCP server or the skill. The agent improvised by continuing with `analyze_upgrade_path` and `build_recipe_plan` directly — violating the skill's documented gate rule, which was the only viable path to satisfy the user request.

### Broken feedback loop

`submit_migration_insight` was never called. The 12 high-value discoveries from this session were never written back to the graph. Every future migration agent will encounter the same gaps and discover the same fixes by compile-error. **The knowledge graph has no mechanism to learn from actual migration sessions.**

---

## 4. Skill vs Reality Mismatch

### 4.1 Violated assumptions

| Skill Assumption | Reality |
|-----------------|---------|
| Loop I always succeeds | `create_migration_context` fails on patch versions due to normalization split-brain |
| `auto_track` contains actionable steps | `auto_track` was empty; no AUTOMATED_BY edges exist in the graph |
| `manual_track` steps are project-targeted | 61% were N/A; no applicability gate |
| Codebase scan uses `grep -P` | macOS BSD grep doesn't support `-P`/PCRE; scan failed twice with exit code 2 |
| `get_steps_for_scope_tier` drives tier-by-tier execution | Never reachable without `context_id` |
| `submit_migration_insight` closes the feedback loop | Not called; skill doesn't mandate it in stateless mode |

### 4.2 Over-constrained execution flow

The skill defines a rigid four-loop harness with hard gates between phases. When Loop I fails, there is no branching logic:

- No `if context_id is None: proceed_in_stateless_mode()` branch
- No `retry_create_context_with_normalized_version()` hint
- No guidance for an agent that encounters a pre-condition failure

### 4.3 Missing fallback strategy

The skill should define an explicit stateless fallback:

```
STATELESS FALLBACK (when create_migration_context fails after 2 retries):
  1. Continue with analyze_upgrade_path and build_recipe_plan as static lookup only
  2. Skip get_steps_for_scope_tier and get_pending_steps entirely
  3. Apply steps directly, tracking state in agent context
  4. Call submit_migration_insight (no context_id needed) for any high-value discoveries
  5. Note context failure in session summary; request platform team to investigate
```

None of this exists in the current skill.

---

## 5. Prompt-Level Weaknesses

### 5.1 No "verify before trust" pattern

The skill instructs the agent to process `manual_track` steps sequentially with no instruction to:
- Grep the codebase before attempting each step
- Check applicability before applying changes
- Cross-reference step instructions against actual source files

The agent manually invented grep-based N/A filtering but burned significant tokens doing so. This pattern should be codified.

### 5.2 No fallback reasoning pattern for tool errors

The skill has no guidance on what to do when a tool returns an error. The agent had to reason autonomously: *"context creation failed → I cannot use context-gated tools → I will proceed with stateless tools."* This is correct but not guaranteed — a less capable agent might abandon the task or loop indefinitely.

### 5.3 No "compile-driven validation" track

The skill assumes MCP steps are the primary migration driver. There is no recognition that **compile errors are a more reliable, project-specific signal** than generic graph rules. The entire migration was completed by the compile-error loop; MCP was supplementary in 7 of 8 build iterations.

A well-designed skill should include:

```
COMPILE-DRIVEN TRACK (when auto_track is empty):
  1. Apply high-severity manual_track steps that grep-confirm as applicable
  2. Run ./gradlew compileJava
  3. Fix each compile error using graph knowledge + LLM reasoning
  4. Repeat until clean
  5. Submit each non-graph fix as submit_migration_insight
```

### 5.4 No uncertainty quantification

Steps are returned with `effort` and `severity` but no `confidence` or `applicability_score`. The agent has no signal for which steps are "probably applicable to most Spring Boot 3→4 projects" vs "specific to projects using feature X." Treating all 33 steps equally wastes agent reasoning budget.

---

## 6. Gap Pattern Synthesis

### Pattern A: "Tool failure → manual reasoning replaces system"

The most consistent pattern across this migration. Every critical failure produced the same response: the agent improvised a workaround not guided by MCP.

| Tool failure | Agent workaround |
|-------------|-----------------|
| `create_migration_context` fails | Proceeds stateless without guidance |
| `resolve_paysafe_dependency` fails | Uses `curl` against Artifactory |
| `resolve_deprecation` returns not_found | Uses JAR inspection (`jar tf`) |
| `search_migration_knowledge` returns generic hits | Uses `rg` grep + compile error |

The MCP system is not robust to its own failures.

### Pattern B: "Compile errors provide more value than MCP"

All 12 critical migration fixes came from compile errors, not graph steps. The graph contains generic version-range rules; compile errors are project-specific and deterministic. The system is not designed to capture and reuse compile-error knowledge.

### Pattern C: "Version resolution happens outside MCP"

Spring Boot 4.1.0 GA unavailability, Paysafe BOM latest version, http-interfaces maximum compatible version — all resolved via `curl` to Maven Central and Artifactory. The MCP system has no version availability tool and the Paysafe resolver is broken. The agent operated without the infrastructure it was designed to rely on.

### Pattern D: "Graph knowledge is generic; project knowledge is absent"

Of the 33 recipe plan steps, 20 were generic Spring Boot 4 guidance not applicable to this repository. The project-specific context (`scannedEntities`, `queriedEntities`) that would enable applicability filtering was never written because context creation failed. The graph has knowledge *about* Spring Boot 4 migrations but no knowledge *about this project*.

### Pattern E: "Feedback loop is permanently severed"

12 high-confidence insights were identified. Zero were written to the graph. The next migration agent will start from the same knowledge state. The graph cannot improve from execution.

---

## 7. What MCP Should Have Done

### Failure: `create_migration_context`

**Expected behavior:** Normalize version strings to `major.minor.0` before the Cypher MATCH (consistent with upgrade tools). Return a structured diagnostic identifying which Version node was missing rather than a generic `RuntimeError`.

**Required change:** Apply `_to_minor_zero()` to `from_version` and `to_version` in `create_or_get_context()` in `migration_oracle/mcp/graph/queries/context.py`. Add structured error response: `{"error_code": "version_not_in_graph", "missing_version": "3.5.12", "hint": "Graph contains 3.5.0 — retry with from_version=3.5.0"}`.

---

### Failure: `resolve_paysafe_dependency_by_service_name`

**Expected behavior:** Redact credentials before constructing error message. Provide an Artifactory fallback path that doesn't require GitLab credentials for version list queries.

**Required change:** Add a regex scrub of `oauth2:[^@]+@` patterns in `_build_error()` in `migration_oracle/paysafe/resolver.py`. Implement an Artifactory REST fallback (`/api/search/latestVersion`) that returns available versions without git access.

---

### Failure: `build_recipe_plan` — 61% noise

**Expected behavior:** Each step includes `applicability_score` and `matched_entities` based on intersection of `scanned_entities` with `AFFECTS_*` relationships. Steps with zero intersection are returned with `applicability: "not_applicable"` so the agent can skip them.

**Required change:** Extend the `build_recipe_plan` Cypher to join AFFECTS_* relationships against `$user_entities`. Add `applicability` and `matched_entities` fields to each step in the response. The AFFECTS_CLASS/AFFECTS_PROPERTY/AFFECTS_DEPENDENCY relationships already exist in the schema — this is a query extension only.

---

### Failure: Auto-config FQCN map missing

**Expected behavior:** `search_migration_knowledge("spring boot 4 auto configuration jdbc exclude")` returns the exact old-to-new package mapping for JDBC, Kafka, Liquibase, JPA, and other auto-config classes.

**Required change:** Ingest the Spring Boot 4 auto-config exclusion FQCN lookup table as discrete `MigrationRule` nodes with AFFECTS_CLASS relationships. This is a data ingestion gap.

---

### Failure: Spring Framework 7 API removals absent

**Expected behavior:** `resolve_deprecation("HttpHeaders.containsKey")` returns `{replacement: "containsHeader", removed_in: "Spring Framework 6.0", step: "..."}`.

**Required change:** Ingest the Spring Framework 7 API removal table as DEPRECATED/REMOVED entities with REPLACED_BY relationships. The 9 compile-fix discoveries from this session are the highest-priority candidates.

---

## 8. Prioritized Fixes

### P0 — System-breaking

**P0-1: Fix `create_migration_context` version normalization**

Apply `_to_minor_zero()` to `from_version` and `to_version` before the Cypher MATCH in `create_or_get_context()`, consistent with how `analyze_upgrade_path` and `build_recipe_plan` normalize versions. Add a diagnostic fallback query: if `.single()` returns None, re-run a lightweight query to identify which Version node is absent and include it in the error.

- File: `migration_oracle/mcp/graph/queries/context.py`
- Impact: Restores entire Loops II–IV and the feedback loop for all migrations using patch versions

---

**P0-2: Redact credentials from all resolver error messages**

Add a credential scrub function in `migration_oracle/paysafe/resolver.py` that strips `oauth2:[^@]+@` (and similar patterns) from any string passed to `_build_error()`. Apply it to all exception messages caught from `gitlab.py` and `findit.py` before populating the response.

- File: `migration_oracle/paysafe/resolver.py` — `_build_error()`
- Impact: Eliminates token leak to LLM, logs, and MCP traces

---

**P0-3: Define stateless fallback mode in the framework-migration skill**

Add an explicit `if create_migration_context fails after 2 retries:` branch to the skill harness documenting which tools are available in stateless mode, which to skip, and mandating `submit_migration_insight` for any discoveries regardless of context availability.

---

### P1 — High impact

**P1-1: Applicability scoring in `build_recipe_plan`**

Extend the plan Cypher to intersect AFFECTS_* relationships against `$user_entities`. Return `applicability: "applicable" | "not_applicable" | "unknown"` and `matched_entities: [...]` per step. Steps with no entity match should be filterable client-side.

**P1-2: Version availability tool**

New tool `check_version_availability(framework, version)` → `{exists_in_graph: bool, ga_available: bool, rc_available: bool, latest_patch: str}`. Probes Maven Central and Artifactory. Prevents the agent from requesting a migration to a non-existent GA version.

**P1-3: Paysafe Artifactory resolver fallback**

When GitLab `ls-remote` fails, fall back to Artifactory REST API to return available versions without requiring git credentials. Decouple version listing from repository access.

**P1-4: Ingest Spring Framework 7 API removal table**

The 9 compile-fix discoveries (HttpHeaders, UriComponentsBuilder, RequestFactory timeout setters, trailing slash config, auto-config FQCNs) should become discrete `MigrationRule` → `MigrationStep` nodes linked to Spring Boot 4.0.0. These are the highest-density-value rules for any Spring Boot 4 migration.

**P1-5: Fix `search_openrewrite_recipes` deferred filter parameters**

Either implement `only_composite` and `require_no_params` filtering at the hydration layer, or remove the parameters from the tool schema. Silent accept-and-ignore is a trust violation that misleads the agent.

---

### P2 — Quality improvements

**P2-1: Deduplicate `build_recipe_plan` manual_track steps**

GraalVM 25 and Gradle 8.14+ each appear twice in the response. Add a `step_id` deduplication pass before returning `manual_track`.

**P2-2: Fix `get_steps_for_scope_tier` OPTIONAL MATCH WHERE semantics**

The `WHERE bs.scope = $scope` clause on the OPTIONAL MATCH turns it into an effective inner join. Steps with no `BreakingScope` node are silently excluded. Change to a separate MATCH + UNION pattern or post-filter in Python.

**P2-3: Persist `reason` in `update_step_status`**

Currently `del reason`. Store it as `ctx.stepNotes` (a map from step_id to reason string) to build a recoverable audit trail of why each step was skipped or marked failed.

**P2-4: Cross-platform scan script in skill**

Replace `grep -P` (PCRE, macOS-incompatible) with `rg` or `grep -E` in the Loop I codebase scan script. The current script fails on macOS with exit code 2 before entity extraction is complete.

**P2-5: Mandate `submit_migration_insight` in stateless mode**

`submit_migration_insight` requires no `context_id` and works independently. The skill should mandate calling it for any compile-error discovery regardless of whether a context exists. This is the only feedback channel that survives context failure and the only path to graph improvement from real migrations.

---

## Connecting Thread: Tool → Skill → Prompt → Outcome

```
context.py: patch version "3.5.12" used in hard MATCH; graph only has "3.5.0"
  → create_migration_context fails silently with generic error
  → skill has no stateless fallback branch
  → agent violates skill gate rule but has no alternative
  → Loops II–IV permanently unavailable
  → no step tracking, no audit trail, no feedback loop
  → graph learns nothing from this session
  → next agent encounters the same gaps
```

```
resolver.py: git error message not scrubbed before returning to MCP
  → OAuth token transmitted to LLM in tool response body
  → no Artifactory fallback path
  → agent falls back to manual curl
  → Paysafe dependency versions remain unresolved
  → http-interfaces starter stays on incompatible 3.5.x
  → runtime incompatibility risk remains at migration end
```

```
build_recipe_plan: no applicability scoring, no AUTOMATED_BY edges
  → 61% of steps are noise; 0% auto-track
  → skill has no "check applicability before executing" instruction
  → agent burns ~2,000 tokens per session screening N/A steps
  → real project-specific issues (apigenerator, BOM conflict, Jetty pin) absent from graph
  → compile errors provide higher migration signal than the entire recipe plan
```

The pattern across all three threads is identical: **the MCP system fails to degrade gracefully, fails to communicate failure cause, and fails to learn from execution.** Fixing `create_migration_context` is the highest-leverage single change — it restores the entire orchestration layer and the feedback loop simultaneously.

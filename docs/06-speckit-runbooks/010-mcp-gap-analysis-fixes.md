# SpecKit Runbook — `010-mcp-gap-analysis-fixes`

> **How to use this file:** Paste each prompt block verbatim into Claude Code in the order shown.
> Do not skip the gap-review steps — they catch the most common drift before it compounds.
> Complete all items in a gap review before advancing to the next command.
>
> **Source:** `analysis/mcp-tooling-gap-analysis.md` — forensic analysis of a real
> Spring Boot 3.5.12 → 4.1.0 migration session that exposed 13 defects across
> MCP tools, resolver, query layer, and skill harness.

---

## Prerequisites

Before starting this spec:

- `008-mcp-bug-fixes` ✅ — Cypher syntax errors and version range bugs from the first
  simulation are already fixed; `_GET_PENDING_STEPS` is working
- `009-community-insight-restructure` ✅ — `CommunityInsight` nodes merged into
  `MigrationRule`; `submit_migration_insight` updated
- Neo4j is running and the graph contains `Version {version: "3.5.0"}` nodes (minor-zero
  form) — confirmed by `MATCH (v:Version) RETURN v.version LIMIT 5`
- Reference files to keep open during gap reviews:
  - `migration_oracle/mcp/graph/queries/context.py` — `_CREATE_OR_GET_CONTEXT`,
    `_GET_STEPS_FOR_SCOPE_TIER`, `update_step_status`
  - `migration_oracle/mcp/tools/context.py` — `create_migration_context` MCP wrapper;
    note it does **not** call `_to_minor_zero` before delegating to the query layer
  - `migration_oracle/mcp/tools/upgrade.py` — `_to_minor_zero`, `analyze_upgrade_path`,
    `build_recipe_plan`; note `_to_minor_zero` is defined here and applied in upgrade tools
    but **not** imported into `context.py`
  - `migration_oracle/mcp/graph/queries/upgrade.py` — `_BUILD_RECIPE_PLAN_QUERY` Cypher;
    note `AFFECTS_CLASS | AFFECTS_PROPERTY | AFFECTS_DEPENDENCY` relationships exist but
    are not joined against `$user_entities` to produce per-step applicability
  - `migration_oracle/paysafe/resolver.py` — `_build_error()`, `_GitError` catch blocks;
    line 160 passes `str(exc)` of a git command that embeds `oauth2:<token>@`
  - `migration_oracle/mcp/tools/search.py` — `search_openrewrite_recipes` lines 204–206
    where `only_composite` and `require_no_params` are accepted but explicitly not applied
  - `migration_oracle/mcp/skills/framework_migration_main.md` — the four-loop harness;
    no stateless fallback branch, `grep -P` used in Loop I scanning

---

## Command 1 — `/speckit.specify`

Paste this entire block:

```
/speckit.specify

WHAT it does:
This spec fixes 13 defects in the MCP server, Paysafe resolver, and framework-migration
skill that were identified during a live Spring Boot 3.5.12 → 4.1.0 migration session.
The fixes restore the full Loop I–IV orchestration harness, eliminate a credential-leak
security defect, add applicability scoring to recipe plan output, implement deferred tool
filter parameters, add a new `check_version_availability` MCP tool, and update the
framework-migration skill with a stateless fallback branch and platform-safe scanning.
No graph schema changes. No node label additions. No tool renames.

WHY it exists:
The live migration session showed that `create_migration_context` fails deterministically
on any project using patch versions (e.g. "3.5.12") because the Cypher MATCH requires
exact Version node keys and the graph only stores minor-zero forms ("3.5.0"). This single
failure blocked all Loop II–IV tools, leaving the agent with no step tracking, no audit
trail, and no feedback loop. Separately, the Paysafe resolver leaks OAuth tokens through
error messages, 61% of recipe plan steps are unfiltered noise with no applicability signal,
`search_openrewrite_recipes` silently ignores two accepted filter parameters, and the
skill's Loop I codebase scan fails on macOS with `grep -P`.

create_migration_context and what it fixes:
- Accepts `from_version` and `to_version` in any patch form ("3.5.12", "3.5.0")
- Normalizes both to major.minor.0 before the Cypher MATCH, consistent with
  `analyze_upgrade_path` and `build_recipe_plan`
- Returns a structured diagnostic dict when either Version node is absent from the graph:
  `{error_code: "version_not_in_graph", missing_version: "...", hint: "Graph contains X.Y.0"}`
  instead of a generic RuntimeError
- Cleans up the zombie MigrationContext node written by a failed MERGE before re-raising,
  so retries do not accumulate orphaned context nodes

update_step_status and what it fixes:
- Persists the `reason` parameter as `ctx.stepNotes[step_id]` (a string map property on the
  MigrationContext node) instead of silently discarding it via `del reason`
- Provides a recoverable per-step audit trail of skipped / failed step rationale

get_steps_for_scope_tier and what it fixes:
- The `WHERE bs.scope = $scope` predicate on `OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)`
  turns the optional match into an effective inner join, silently dropping steps that have no
  BreakingScope node
- Replace with a pattern that returns all steps and filters scope post-match, so scopeless
  steps are included with `scope: null` rather than dropped

resolver and what it fixes:
- `_build_error()` scrubs `oauth2:[^@]+@` (and `https?://[^:]+:[^@]+@`) from any exception
  message before populating the `message` field — eliminates OAuth token transmission to LLM
- Adds an Artifactory REST fallback path: when GitLab `ls-remote` fails, queries
  `/api/search/latestVersion?repos=&g=&a=` to return available versions without git access
- The fallback is transparent to callers — same return shape

build_recipe_plan and what it fixes:
- Each step in `manual_track` gains two new fields:
  `applicability: "applicable" | "not_applicable" | "unknown"` and `matched_entities: [...]`
  derived by intersecting the step's AFFECTS_CLASS/AFFECTS_PROPERTY/AFFECTS_DEPENDENCY
  relationships against the `$user_entities` parameter
- Steps with no intersection return `applicability: "not_applicable"` so agents can skip them
  without manual grepping
- Duplicate step entries (same `step_id` appearing twice) are deduplicated before returning;
  the first occurrence wins

search_openrewrite_recipes and what it fixes:
- `only_composite` filter: when true, only return recipes whose `composite = true` property
  is set; implemented at the Cypher WHERE clause, not post-hoc in Python
- `require_no_params` filter: when true, only return recipes with no required parameters
  (i.e. no `RecipeParam` node linked by `HAS_PARAM` with `required = true`)
- Both parameters are now applied; the deferred-filter comment block at lines 204–206 is removed

check_version_availability (new tool):
- New MCP tool: `check_version_availability(framework, version) → dict`
- Returns: `{exists_in_graph: bool, ga_available: bool, latest_patch: str, hint: str}`
- `exists_in_graph`: true if a Version node with `framework=X, version=major.minor.0` exists
- `ga_available`: probes Maven Central search API for the exact version with `packaging=jar`
  and `v=<version>` — true if at least one artifact is returned
- `latest_patch`: the highest patch version found in Maven Central for the same major.minor
- `hint`: human-readable guidance, e.g. "4.1.0 is not yet GA; latest patch is 4.0.4"
- No authentication required; purely read-only; no new graph writes

framework_migration_main.md skill and what it fixes:
- Adds an explicit STATELESS FALLBACK block after Loop I:
  "If `create_migration_context` returns an error after 2 retries: proceed using
  `analyze_upgrade_path` and `build_recipe_plan` as static lookup; skip Loop II–III tool
  calls that require context_id; track step state in agent context only; call
  `submit_migration_insight` for every high-confidence discovery regardless of context
  availability; note context failure in session summary"
- Replaces `grep -P` in the Loop I scanning script with `grep -E` (POSIX ERE, works on
  macOS BSD grep and Linux GNU grep without ripgrep dependency)
- Adds a mandatory `submit_migration_insight` instruction to the stateless path — the tool
  requires no context_id and is the only feedback channel that survives context failure

KEY BEHAVIORS:
VERSION_NORMALIZATION — `create_migration_context` normalizes from_version and to_version
  to major.minor.0 before every Cypher MATCH, matching the behavior of upgrade tools
DIAGNOSTIC_ERROR — if a Version node is absent, the tool returns a structured error dict
  with error_code, missing_version, and hint rather than raising RuntimeError
CREDENTIAL_SCRUB — `_build_error()` in resolver.py never passes raw exception messages
  containing git URLs to the MCP response; all credential patterns are scrubbed before return
ARTIFACTORY_FALLBACK — when GitLab ls-remote fails, the resolver automatically retries via
  Artifactory REST API without surfacing the retry to the caller
APPLICABILITY_SIGNAL — every step in `build_recipe_plan`'s manual_track includes
  applicability and matched_entities fields; agents can filter to applicable steps without
  manual grep-based triage
DEDUP_STEPS — `build_recipe_plan` never returns the same step_id more than once
FILTER_FIDELITY — `search_openrewrite_recipes` only_composite and require_no_params
  parameters are applied at query time; no silent accept-and-ignore
VERSION_AVAILABILITY — `check_version_availability` allows agents to verify target version
  GA status before beginning a migration session
SKILL_RESILIENCE — the framework-migration skill defines an explicit, documented stateless
  fallback path; agents do not need to improvise when context creation fails
PLATFORM_SAFE_SCAN — the Loop I scanning script works on macOS and Linux without ripgrep

[INTEGRATION CONSTRAINTS]
- `_to_minor_zero` is defined in `migration_oracle/mcp/tools/upgrade.py`; import it from
  there in `migration_oracle/mcp/tools/context.py` — do not duplicate the implementation
- `check_version_availability` must not write to Neo4j; it is a read+probe-only tool
- The Artifactory REST base URL must be read from environment variable
  `ARTIFACTORY_BASE_URL`; do not hardcode any Paysafe-internal URL
- Credential scrubbing must be applied in `_build_error()` itself — not at the call sites —
  so all future callers inherit the protection automatically
- Zombie context cleanup in `create_migration_context` must use a separate Cypher DELETE
  only when `.single()` returns None after the MERGE+MATCH; do not delete valid contexts
- `get_steps_for_scope_tier` must return steps with no BreakingScope node with scope=null,
  not silently drop them; existing callers that expect a non-null scope must be updated
- All Cypher changes must be covered by unit tests using the existing Neo4j test fixtures
  in `tests/mcp/`
- `framework_migration_main.md` changes must not alter the existing Loop I–IV structure;
  the stateless fallback is an addendum block inserted after the Loop I failure condition
```

---

## Gap Review — post-specify

Before running `/speckit.plan`, verify all items below are satisfied in the generated `spec.md`:

**GAP-001: Zombie context cleanup scope**
The spec must state exactly when the orphaned-MERGE cleanup runs: only when `.single()`
returns `None` after a MERGE+MATCH sequence. Confirm the spec does not say "always delete
before creating" (which would break idempotent resume of valid contexts).

**GAP-002: stepNotes storage format**
The spec must specify that `stepNotes` is stored as a map property on `MigrationContext`
(Neo4j map type: `{step_id_1: "reason text", ...}`) and that the Cypher update uses
`ctx.stepNotes = apoc.map.setKey(coalesce(ctx.stepNotes, {}), $step_id, $reason)` — or
an equivalent map-merge pattern. If the spec says "store as a list" or omits the format,
it will cause a data model mismatch.

**GAP-003: Artifactory fallback authentication**
The spec must state that the Artifactory fallback uses no credentials (anonymous read) for
the `/api/search/latestVersion` endpoint, and that `ARTIFACTORY_BASE_URL` is the only env
var required. If the spec implies a separate Artifactory credential, the fallback will fail
under the same conditions as the GitLab path.

**GAP-004: applicability when user_entities is empty**
The spec must define the applicability value returned when `$user_entities` is empty (no
entities provided): `"unknown"` with `matched_entities: []`. Steps must not be labeled
`"not_applicable"` when the entity list is simply absent.

**GAP-005: check_version_availability Maven Central probe**
The spec must name the exact Maven Central REST endpoint and the query strategy. The tool
must not scrape HTML. Confirm: `https://search.maven.org/solrsearch/select?q=g:...+AND+a:...+AND+v:...&rows=1&wt=json`
(or the equivalent `search.maven.org/remotecontent` redirect approach). If the spec says
"query Maven Central" without naming the endpoint, the plan will invent an approach.

**GAP-006: grep -E replacement scope**
The spec must state that *only* the Loop I scanning script in `framework_migration_main.md`
is changed — not any Python code that uses subprocess grep. Confirm the spec does not
over-specify this as a project-wide grep flag change.

**GAP-007: search_openrewrite_recipes filter implementation layer**
The spec must state filters are implemented at the Cypher WHERE clause (not post-processed
in Python after fetching all results). If implemented post-hoc, large recipe graphs will
over-fetch. Confirm the spec names the Cypher pattern: `AND (NOT $only_composite OR
r.composite = true)`.

**GAP-008: scope of skill changes**
The spec must limit skill changes to `framework_migration_main.md` only. The other three
skill files (`framework_migration_scanning.md`, `framework_migration_plan_format.md`,
`framework_migration_version_map.md`) must not be touched. If the spec says "update the
framework-migration skill" without scoping to the main file, all four will be edited.

**GAP-009: Version node absence hint content**
The diagnostic error hint must be computable from a graph query, not hardcoded. The spec
should state: run a `MATCH (v:Version {framework: $framework}) RETURN v.version` to find
what versions exist, then format the hint as `"Graph contains <list>; pass one of these as
from_version"`. A hardcoded hint will be wrong for any framework other than Spring Boot.

**GAP-010: update_step_status backward compat**
The spec must confirm that callers that do not pass `reason` (the parameter is currently
optional and was previously silently discarded) continue to work — i.e. `stepNotes` is
only updated when `reason` is a non-empty string, and the update is a no-op otherwise.

---

## Command 2 — `/speckit.plan`

Paste this entire block:

```
/speckit.plan

Generate plan.md, data-model.md, contracts/, and research.md for spec 010-mcp-gap-analysis-fixes.

Required artifacts:

FILE STRUCTURE — all changes are modifications to existing files plus one new file:
  migration_oracle/mcp/tools/context.py       — import _to_minor_zero; normalize before delegate
  migration_oracle/mcp/graph/queries/context.py — 3 Cypher/Python changes (MERGE cleanup,
                                                  stepNotes persist, scope tier OPTIONAL MATCH fix)
  migration_oracle/mcp/tools/upgrade.py        — add check_version_availability tool function
  migration_oracle/mcp/graph/queries/upgrade.py — extend BUILD_RECIPE_PLAN_QUERY for applicability
                                                  + dedup; no schema change
  migration_oracle/paysafe/resolver.py         — scrub credentials in _build_error();
                                                  Artifactory fallback in the _GitError catch block
  migration_oracle/mcp/tools/search.py         — implement only_composite + require_no_params
                                                  at query layer in search_openrewrite_recipes
  migration_oracle/mcp/skills/framework_migration_main.md — stateless fallback block +
                                                  grep -E replacement + submit_migration_insight mandate
  tests/mcp/test_context_fixes.py              — new test file covering items 1–3
  tests/mcp/test_recipe_applicability.py       — new test file covering build_recipe_plan changes
  tests/paysafe/test_resolver_credential_scrub.py — new test file covering credential scrub

DATA MODEL — no new node labels, no relationship type additions.
  New property on MigrationContext: `stepNotes` (map<string,string>, optional, default {})
  New return fields on build_recipe_plan step dict:
    applicability: "applicable" | "not_applicable" | "unknown"  (string)
    matched_entities: list[str]
  New tool response shape for check_version_availability:
    exists_in_graph: bool
    ga_available: bool
    latest_patch: str | null
    hint: str

CONTRACTS — document:
  _to_minor_zero import contract: upgrade.py owns the function; context.py imports it;
    neither file may redefine it
  credential scrub contract: _build_error() is the sole scrub point; raw exception strings
    must never appear in any other MCP response path
  Artifactory fallback contract: fallback is transparent — callers receive same error_code
    shape whether GitLab or Artifactory was queried; the internal path taken is not exposed
  applicability contract: "unknown" is returned when user_entities=[]; agents must not
    interpret "unknown" as "not applicable"

RESEARCH — spike needed on:
  Maven Central REST endpoint for GA availability check (no auth, JSON response)
  Neo4j map property update Cypher pattern for stepNotes (apoc.map.setKey vs SET ctx.stepNotes[$k])
  Whether APOC library is available in the project's Neo4j instance (check docker-compose.yml)
  Artifactory /api/search/latestVersion endpoint format and whether anonymous read is permitted
```

---

## Gap Review — post-plan

Before running `/speckit.tasks`, verify all items below:

**PLAN-GAP-001: _to_minor_zero import path**
`plan.md` must show an explicit import statement in `context.py`:
`from migration_oracle.mcp.tools.upgrade import _to_minor_zero`. If the plan says
"use the normalization helper" without naming the import, the implementer will redefine it.

**PLAN-GAP-002: APOC dependency confirmed**
`research.md` must record whether APOC is available. If not, the stepNotes map update
must use a SET ctx.stepNotes = $updated_map pattern (compute the updated map in Python,
then write it back). The plan must show which approach applies.

**PLAN-GAP-003: Zombie context DELETE Cypher**
`plan.md` must include the exact Cypher for the cleanup:
`MATCH (ctx:MigrationContext {projectId: $project_id, fromVersion: $from_version_raw, toVersion: $to_version_raw}) WHERE NOT (ctx)-[:UPGRADES_FROM]->() DELETE ctx`
— or equivalent. "Delete the orphaned node" without the exact pattern will produce an
incorrect or dangerous query.

**PLAN-GAP-004: applicability Cypher join**
`plan.md` must show the Cypher extension for `_BUILD_RECIPE_PLAN_QUERY`:
the WITH clause that collects `collect(DISTINCT affected.name)` per step and uses
`size(apoc.coll.intersection(..., $user_entities))` or equivalent set-intersection to
populate `matched_entities` and derive `applicability`. If the plan says "add applicability
scoring" without the Cypher, the implementer will invent a pattern.

**PLAN-GAP-005: Artifactory fallback URL construction**
`plan.md` must show how the Artifactory query URL is constructed from `ARTIFACTORY_BASE_URL`
and the service name. Since the resolver receives a service/artifact name (not a full
Maven coordinate), the plan must document how the service name maps to `groupId:artifactId`
for the Artifactory query.

**PLAN-GAP-006: check_version_availability Maven probe error handling**
`plan.md` must specify what `check_version_availability` returns when the Maven Central
network call fails (timeout, HTTP 5xx): `ga_available: false, latest_patch: null,
hint: "Maven Central unavailable — could not verify GA status"`. A network error must not
raise an exception from this tool.

**PLAN-GAP-007: dedup strategy**
`plan.md` must document the deduplication pass in `build_recipe_plan`: iterate
`manual_track` after assembly, keep first occurrence of each `step_id`, discard
subsequent duplicates. The plan must confirm this is applied before `applicability` scoring
(not after) to avoid computing applicability for entries that will be dropped.

**PLAN-GAP-008: skill file line targets**
`plan.md` must reference the exact section in `framework_migration_main.md` where the
stateless fallback block is inserted (after Loop I step 6, before Loop II header) and the
exact `grep -P` occurrence(s) to replace. Vague "update the skill file" will cause drift.

**PLAN-GAP-009: test fixture Neo4j state**
`plan.md` must note which test fixtures need updating: specifically, `tests/mcp/` likely
uses a `conftest.py` that seeds Version nodes. Confirm that `Version {version: "3.5.12"}`
is NOT seeded (to test the normalization path) and that `Version {version: "3.5.0"}` IS
seeded. Document the fixture state explicitly.

---

## Command 3 — `/speckit.tasks`

```
/speckit.tasks
```

---

## Gap Review — post-tasks

Before running `/speckit.implement`, verify all items below:

**TASK-GAP-001: Foundation order**
The task that adds `_to_minor_zero` import to `context.py` must come after (or be marked
[P] with) the task that confirms `_to_minor_zero` is importable from `upgrade.py`. If
`upgrade.py` is being modified in the same spec, confirm the function is not accidentally
removed or renamed.

**TASK-GAP-002: Cypher change tasks are paired with tests**
Every Cypher modification task (MERGE cleanup, stepNotes, scope tier fix, applicability
join, recipe dedup) must have a corresponding test task that runs against a real (test)
Neo4j instance. No Cypher change should be marked complete without an integration test.

**TASK-GAP-003: check_version_availability registered in MCP server**
There must be a task that registers `check_version_availability` in the MCP server's tool
list (wherever `build_recipe_plan`, `analyze_upgrade_path`, etc. are registered). A tool
function that exists but is not registered is invisible to agents.

**TASK-GAP-004: credential scrub task covers all _build_error call sites**
The credential scrub task must cover `_build_error()` itself — not just one call site.
Verify no task attempts to scrub only the `_GitError` catch block; the fix must be in
the shared helper so all future call sites are protected automatically.

**TASK-GAP-005: skill file tasks are isolated**
There must be separate tasks for (a) stateless fallback block, (b) grep replacement, and
(c) submit_migration_insight mandate. Bundling all three into one task risks partial
application being marked complete.

**TASK-GAP-006: E2E test task**
There must be an end-to-end test task that simulates the full Loop I → II flow:
create_migration_context with a patch version → assert context_id returned →
get_pending_steps → assert non-empty result. This test validates the entire fix chain.

**TASK-GAP-007: Artifactory fallback task has network mock**
The Artifactory fallback test task must use a responses/httpretty/respx mock — not a
live Artifactory instance. The test must verify the fallback is triggered when git raises
`_GitError` and that the returned shape matches the normal success path.

---

## Command 4 — `/speckit.implement`

```
/speckit.implement
```

---

## Recovery Prompts

Paste verbatim if implementation drifts.

---

**R-01 — _to_minor_zero duplicated in context.py**

```
Do not redefine `_to_minor_zero` in `migration_oracle/mcp/tools/context.py`.
Import it directly: `from migration_oracle.mcp.tools.upgrade import _to_minor_zero`.
The function must exist in exactly one place. Any duplicate definition will cause the two
files to diverge silently when the normalization logic changes.
```

---

**R-02 — Zombie context cleanup deleting valid contexts**

```
The MERGE cleanup must only run when `.single()` returns None — meaning the MATCH on
Version nodes found no results. Do NOT run the DELETE before the MERGE, and do NOT delete
the context node on every call. The pattern is:
  1. Run MERGE + MATCH (version nodes)
  2. If result is None → run a targeted DELETE for the just-created orphaned MERGE node
  3. Raise the diagnostic error
  4. If result is not None → return normally (context is valid)
Deleting outside this condition will corrupt in-progress migration sessions.
```

---

**R-03 — Applicability computed post-hoc in Python instead of Cypher**

```
The applicability scoring for `build_recipe_plan` must be computed inside the Cypher query
using a set-intersection of the step's AFFECTS_* relationships against `$user_entities`.
Do NOT fetch all steps and then filter in Python — this defeats the purpose and over-fetches
on large graphs. The Cypher must include:
  OPTIONAL MATCH (s)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(e)
  WITH s, r, ..., collect(DISTINCT e.name) AS affected
  WITH s, r, ..., affected,
       [u IN $user_entities WHERE u IN affected] AS matched
  RETURN ..., CASE WHEN size($user_entities) = 0 THEN 'unknown'
                   WHEN size(matched) > 0 THEN 'applicable'
                   ELSE 'not_applicable' END AS applicability,
              matched AS matched_entities
```

---

**R-04 — credential scrub applied only at one call site**

```
The credential scrub must be applied inside `_build_error()` in
`migration_oracle/paysafe/resolver.py` — not at any individual `except _GitError` block.
The function signature for _build_error should add an internal scrub step before
constructing the return dict:
  import re
  _CRED_RE = re.compile(r'https?://[^:@/\s]+:[^@\s]+@')
  def _scrub(s: str) -> str:
      return _CRED_RE.sub('<redacted>@', s)
Apply `_scrub` to the `message` argument at the top of `_build_error`. No other change
is needed — all callers inherit the protection automatically.
```

---

**R-05 — check_version_availability raises on Maven Central timeout**

```
`check_version_availability` must NOT raise an exception when the Maven Central HTTP call
fails. Catch all network errors (requests.Timeout, requests.ConnectionError, HTTPError)
and return:
  {"exists_in_graph": <bool>, "ga_available": False, "latest_patch": None,
   "hint": "Maven Central unavailable — GA status could not be verified"}
The tool is advisory; agents must be able to proceed without a confirmed GA status.
Raising here would block migrations against unreachable Maven Central (e.g. corporate proxy).
```

---

**R-06 — Skill file Loop I–IV structure altered**

```
Changes to `migration_oracle/mcp/skills/framework_migration_main.md` must be additive only:
  1. Insert the STATELESS FALLBACK block as a new subsection immediately after Loop I step 6
     (the `create_migration_context` call), before the "## Loop II" header. Do not remove
     any Loop I–IV content.
  2. Replace `grep -P` with `grep -E` in the scanning script lines only — do not change
     any surrounding prose or pattern logic.
  3. Add the `submit_migration_insight` mandate as a bullet under the STATELESS FALLBACK
     block — do not modify the existing Loop IV section.
If the skill file is regenerated from scratch, the changes to the four-loop structure will
be lost. Edit in place.
```

---

## What Success Looks Like

Run these checks after `/speckit.implement` completes:

```bash
# 1. Patch version no longer breaks context creation
python -c "
from migration_oracle.mcp.tools.context import create_migration_context
result = create_migration_context('test-project', 'spring-boot', '3.5.12', '4.1.0', [])
assert 'context_id' in result or result.get('error_code') == 'version_not_in_graph', result
print('P0-1 PASS:', result.get('error_code', 'created'))
"

# 2. Credential scrub — no token in error output
python -c "
from migration_oracle.paysafe.resolver import _build_error
out = _build_error('git_ls_remote_failed', 'git ls-remote https://oauth2:glpat-secret@gitlab.paysafe.cloud/foo failed', None)
assert 'glpat-secret' not in out['message'], 'TOKEN LEAKED'
print('P0-2 PASS:', out['message'])
"

# 3. Applicability fields present in recipe plan
python -c "
from migration_oracle.mcp.tools.upgrade import build_recipe_plan
result = build_recipe_plan('spring-boot', '3.5.0', '4.1.0', user_entities=['RestTemplate'])
steps = result.get('manual_track', [])
assert all('applicability' in s for s in steps), 'missing applicability'
assert all('matched_entities' in s for s in steps), 'missing matched_entities'
print('P1-1 PASS: steps =', len(steps), '| applicable =', sum(1 for s in steps if s['applicability']=='applicable'))
"

# 4. Skill file contains stateless fallback
grep -q "STATELESS FALLBACK" migration_oracle/mcp/skills/framework_migration_main.md && echo "P0-3 PASS" || echo "P0-3 FAIL"
grep -q "grep -E" migration_oracle/mcp/skills/framework_migration_main.md && echo "P2-4 PASS" || echo "P2-4 FAIL"
grep -qv "grep -P" migration_oracle/mcp/skills/framework_migration_main.md && echo "grep -P removed" || echo "grep -P still present"

# 5. Unit tests pass
python -m pytest tests/mcp/test_context_fixes.py tests/mcp/test_recipe_applicability.py tests/paysafe/test_resolver_credential_scrub.py -v
```

All five checks must pass and all new test files must have zero failures before the spec is
considered complete.

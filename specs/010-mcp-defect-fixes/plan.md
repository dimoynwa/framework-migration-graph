# Implementation Plan: MCP Defect Fixes — Migration Session Hardening

**Branch**: `010-mcp-defect-fixes` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-mcp-defect-fixes/spec.md`

## Summary

Harden the MCP server's migration-session tools by fixing 9 functional defects across 7 source files:
normalise version strings before graph lookups (P0-1), scrub OAuth2/basic-auth credentials from error
messages (P0-2), add a stateless fallback path to the skill harness (P0-3), apply `only_composite` and
`require_no_params` filters at query time (P1-5), add `applicability` scoring to `build_recipe_plan`
(P2-1), fix the OPTIONAL MATCH scope-tier inner-join bug (P2-2), persist `stepNotes` rationale (P2-3),
add Artifactory fallback for GitLab failures (P2-5), and add a `check_version_availability` pre-flight
tool (new). No schema migration, no new node labels, no new relationship types.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: `neo4j` (Python driver), `sentence-transformers`, `mcp`, `requests`, `packaging`

**Storage**: Neo4j 5 Community Edition (no APOC). All graph reads via `read_session()`; writes via `write_session()`.

**Testing**: `pytest` + `unittest.mock.patch` for unit tests. Tests in `tests/mcp/` and `tests/paysafe/`.

**Target Platform**: Linux container (Docker Compose). macOS for local dev — grep compatibility required.

**Project Type**: MCP server (Python daemon, tool-based API over Neo4j)

**Performance Goals**: No new N+1 queries introduced. The `check_version_availability` tool makes at most 2 HTTP calls (graph read + Maven Central probe); both are bounded by timeouts.

**Constraints**: No APOC. All Cypher must run on Neo4j 5 Community. No new env vars for Artifactory credentials. Skill file changes restricted to `framework_migration_main.md` only.

## Constitution Check

The project constitution file is an unfilled template. Constraints are derived from the codebase directly.

| Gate | Status | Notes |
|---|---|---|
| No new node labels or relationship types | PASS | Spec Assumption confirmed; only property additions |
| No APOC usage | PASS | `neo4j:5` Community; Python-side map-merge for stepNotes |
| No duplicate helper functions | PASS | `to_minor_zero` renamed and imported; no copy |
| Security: no credential leakage | PASS | `_build_error()` scrub enforced by contract |
| Skill file scope | PASS | Only `framework_migration_main.md` modified |
| No new Artifactory credential env vars | PASS | Anonymous read only; FR-008 explicit |

## Project Structure

### Documentation (this feature)

```text
specs/010-mcp-defect-fixes/
├── plan.md              ← this file
├── spec.md              ← feature specification
├── research.md          ← Phase 0: spike findings
├── data-model.md        ← Phase 1: property and return shape changes
├── contracts/
│   ├── to_minor_zero_import.md
│   ├── credential_scrub.md
│   ├── artifactory_fallback.md
│   └── applicability_semantics.md
└── tasks.md             ← Phase 2 (/speckit-tasks — not yet generated)
```

### Source Code — Modified Files

```text
migration_oracle/
├── mcp/
│   ├── tools/
│   │   ├── context.py          # import to_minor_zero; normalise before delegate; fix del reason
│   │   ├── upgrade.py          # rename _to_minor_zero→to_minor_zero; add check_version_availability
│   │   └── search.py           # pass only_composite/require_no_params to hydration query
│   ├── graph/
│   │   └── queries/
│   │       ├── context.py      # MERGE zombie cleanup; stepNotes Python-merge; scope tier OPTIONAL MATCH fix
│   │       ├── upgrade.py      # extend _BUILD_RECIPE_PLAN with affected_entities per step; dedup
│   │       └── search.py       # extend hydrate_openrewrite_recipes with composite/param WHERE clauses
│   └── skills/
│       └── framework_migration_main.md  # STATELESS FALLBACK block + grep -E + submit_migration_insight
└── paysafe/
    └── resolver.py             # _CRED_RE + _scrub in _build_error(); Artifactory fallback in _GitError catch

tests/
├── mcp/
│   ├── test_context_fixes.py      # NEW — version normalisation, zombie cleanup, stepNotes, scope tier
│   ├── test_recipe_applicability.py  # NEW — applicability scoring, dedup, empty user_entities
│   └── conftest.py                # existing — no changes needed
└── paysafe/
    └── test_resolver_credential_scrub.py  # NEW — scrub regex, double-failure, Artifactory fallback
```

**Structure Decision**: Single Python package; all modifications are targeted patches to existing modules. Three new test files map 1:1 to the fix groups.

## Phase 0 — Research Findings

See [research.md](./research.md) for full spike details. Key decisions:

| Question | Decision |
|---|---|
| Maven Central endpoint | `https://search.maven.org/solrsearch/select?q=g:{gId}+AND+a:{aId}+AND+v:{v}&rows=1&wt=json` — `numFound >= 1` = GA |
| Latest patch query | Same endpoint without `v:`, `sort=version+desc`, read first doc's `latestVersion` field |
| stepNotes Cypher | Python-side merge (read map → merge in Python → `SET ctx.stepNotes = $merged`) |
| APOC available? | **No** — `neo4j:5` Community, no `NEO4J_PLUGINS` configured |
| Artifactory endpoint | `GET {ARTIFACTORY_BASE_URL}/api/search/latestVersion?g=…&a=…` — anonymous, plain-text response |

## Phase 1 — Design Detail

### FR-001 / FR-004 — Version normalisation in create_migration_context

**Problem**: `context.py:create_migration_context` passes raw `from_version`/`to_version` straight to the graph query. The graph stores only `major.minor.0` nodes, so patch versions fail the MATCH silently.

**Fix**:
1. In `upgrade.py`: rename `_to_minor_zero` → `to_minor_zero`. Update the 2 call sites (`analyze_upgrade_path`, `build_recipe_plan`) in the same file.
2. In `context.py`: `from migration_oracle.mcp.tools.upgrade import to_minor_zero`. Apply before calling `context_queries.create_or_get_context`.
3. The graph query `_CREATE_OR_GET_CONTEXT` MERGE key uses `$from_version`/`$to_version` — these are now already normalised before passing in, so no Cypher change is needed for the MERGE predicate.
4. When `.single()` returns `None` after the MERGE+MATCH block, the tool must issue a targeted DELETE of the just-created context node (identified by `_was_created=true`) before returning the `version_not_in_graph` error. A secondary read query `MATCH (v:Version {framework: $framework}) RETURN v.version ORDER BY v.sortableVersion` provides the live hint list.

**Zombie cleanup Cypher pattern** (added to `context.py` query module):
```cypher
MATCH (ctx:MigrationContext {projectId: $project_id, fromVersion: $from_version, toVersion: $to_version})
WHERE NOT (ctx)-[:UPGRADES_FROM]->()
DELETE ctx
```
The structural guard `WHERE NOT (ctx)-[:UPGRADES_FROM]->()` is used instead of the `_was_created` flag because when `.single()` returns `None` the record is unavailable — `_was_created` cannot be read from it. A zombie node (MERGE ran but Version MATCH failed) will always have no `UPGRADES_FROM` relationship, making this check equivalent and always safe to read. This runs only in the `None` branch of Python code — never as a general pre-step.

### FR-002 — Dynamic version_not_in_graph hint

Secondary query added to `context.py` query module:
```cypher
MATCH (v:Version {framework: $framework})
RETURN v.version
ORDER BY v.sortableVersion
```
Called in the error branch only. Result is joined as comma-separated string in the hint.

### FR-003 — Zombie cleanup guard

Python logic in `create_or_get_context`:
```python
record = session.run(_CREATE_OR_GET_CONTEXT, ...).single()
if record is None:
    # Structural guard in _DELETE_ZOMBIE_CONTEXT makes this unconditionally safe:
    # a zombie node (MERGE ran but Version MATCH failed) has no UPGRADES_FROM edge.
    # No flag check is needed — do not attempt to read _was_created from the None record.
    session.run(_DELETE_ZOMBIE_CONTEXT, project_id=project_id,
                from_version=from_version_normalised, to_version=to_version_normalised)
    versions = _get_available_versions(framework)
    raise VersionNotInGraphError(missing_version, versions)
```

**Why the `_was_created` flag is not used here**: when `.single()` returns `None` the record object is `None` — `record["_was_created"]` would raise `TypeError`. The structural WHERE guard in `_DELETE_ZOMBIE_CONTEXT` (`WHERE NOT (ctx)-[:UPGRADES_FROM]->()`) is the correct guard: a zombie node (created by MERGE before a failed Version MATCH) will never have an `UPGRADES_FROM` edge, so the DELETE is safe to run unconditionally in this branch. A valid in-progress context always has both `UPGRADES_FROM` and `UPGRADES_TO` edges and is never touched.

**Verification**: `_CREATE_OR_GET_CONTEXT` in `migration_oracle/mcp/graph/queries/context.py` lines 25–27 confirms `ctx._was_created` is already set in ON CREATE/ON MATCH — this is an existing implementation detail that is correct but irrelevant to the cleanup path.

### FR-005 — stepNotes persistence

In `context_queries.record_step_outcome`:
1. Add a preparatory read: `MATCH (ctx) WHERE elementId(ctx) = $context_id RETURN coalesce(ctx.stepNotes, {}) AS stepNotes`
2. In Python: `merged = {**current_notes, step_id: reason}` when `reason` is non-empty
3. Add a SET: `SET ctx.stepNotes = $merged_map`

Alternative: combine into one query using `WITH` to carry the merged map. Either approach is acceptable; separating is clearer.

In `context.py` tool layer (`update_step_status`): remove `del reason`. Pass `reason` through to `context_queries.record_step_outcome`.

### FR-006 — Scope tier OPTIONAL MATCH fix

In `_GET_STEPS_FOR_SCOPE_TIER` (context.py query):
```cypher
# BEFORE (bug — WHERE on target node turns OPTIONAL MATCH into inner join)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
WHERE bs.scope = $scope

# AFTER (correct — scope filter moves to Python; all steps returned with scope: null for scopeless)
OPTIONAL MATCH (r)-[:HAS_SCOPE]->(bs:BreakingScope)
```
The Python `get_steps_for_scope_tier` function already post-filters by `min_severity`. Scope filtering in the Cypher query is removed; the Python layer receives all rows and returns them (including `bs.scope = null` rows).

The tool layer `get_steps_for_scope_tier` in `context.py` uses `row.get("scope") or ""` for the hit dict. Change to `row.get("scope")` (allow null) so scopeless steps surface with `scope: null`.

### FR-007 — Credential scrub in _build_error

In `resolver.py`, add at module level:
```python
import re
_CRED_RE = re.compile(r'https?://[^:@/\s]+:[^@\s]+@|oauth2:[^@\s]+@')
def _scrub(s: str) -> str:
    return _CRED_RE.sub('<redacted>@', s)
```
In `_build_error()`: apply `message = _scrub(message)` as the first line of the function body.

### FR-008 / FR-009 — Artifactory fallback

In `resolver.py`, inside the `except _GitError as exc:` block for `git_ls_remote_failed`:
```python
artifactory_base = os.environ.get("ARTIFACTORY_BASE_URL", "").rstrip("/")
if not artifactory_base:
    return _build_error(exc.error_code, exc.message or "git ls-remote failed.", ...)
try:
    # Use artifact ID only — the Artifactory latestVersion endpoint accepts `a=` without `g=`.
    # `service_name` is used directly as the artifact ID; no groupId derivation is required.
    url = f"{artifactory_base}/api/search/latestVersion?a={service_name}"
    resp = requests.get(url, timeout=10)  # no Authorization header — anonymous read
    if resp.ok and resp.text.strip():
        tags = [resp.text.strip()]
        # continue with tags through the existing selection strategy
    else:
        return _build_error("git_ls_remote_failed",
                            "GitLab failed and Artifactory returned no version.",
                            recoverable=True,
                            actionable_hint="Check GitLab access and Artifactory repository.",
                            details={"repo_url": code_repo_link})
except Exception as art_exc:
    return _build_error("git_ls_remote_failed",
                        f"GitLab failed and Artifactory fallback also failed.",
                        recoverable=True,
                        actionable_hint="Check GitLab access credentials and Artifactory availability.",
                        details={"repo_url": code_repo_link})
```

**URL construction rule**: The Artifactory `/api/search/latestVersion` endpoint accepts `a={artifact_id}` without a `g=` (groupId) parameter. The `service_name` passed to `resolve()` is used directly as the artifact ID — no groupId derivation from `codeRepoLink` or FindIt metadata is attempted. This avoids an impossible mapping (GitLab URLs do not carry Maven coordinates) while still locating internal artifacts by their artifact ID in Artifactory.

**Note — `repos=` parameter**: `research.md` Spike 4 lists the endpoint as `…?g={groupId}&a={artifactId}&repos={repo}`. The plan omits `repos=` because the virtual repo name is not known statically. This may cause broader-than-intended searches on some Artifactory instances. The implementer MUST verify against the actual Paysafe Artifactory instance: if `repos=` is required to scope results correctly, add `repos={ARTIFACTORY_REPO}` and introduce `ARTIFACTORY_REPO` as an optional env var. If anonymous search without `repos=` returns the correct result, no change is needed.

### FR-010 / FR-011 / FR-012 — build_recipe_plan applicability + dedup

In `upgrade.py` (graph queries), extend `_BUILD_RECIPE_PLAN`:
```cypher
OPTIONAL MATCH (rule)-[:AFFECTS_CLASS|AFFECTS_PROPERTY|AFFECTS_DEPENDENCY]->(ae)
WITH ..., collect(DISTINCT ae.name) AS all_affected_entities
```
Return `all_affected_entities` per row.

In `build_recipe_plan` Python function, the row-processing loop follows this order:

```python
seen_step_ids: set[str] = set()
user_ents_lower = {e.lower() for e in (user_entities or [])}

for row in rows:
    step_id = row.get("step_id") or ""

    # 1. DEDUP FIRST — skip rows whose step_id has already been seen
    if step_id and step_id in seen_step_ids:
        continue
    if step_id:
        seen_step_ids.add(step_id)

    # 2. APPLICABILITY — computed only for rows that survive the dedup gate
    all_affected = row.get("all_affected_entities") or []
    all_affected_lower = {e.lower() for e in all_affected}
    if not user_ents_lower or not all_affected_lower:
        applicability = "unknown"
        matched_entities = []
    else:
        matched_entities = [e for e in all_affected if e.lower() in user_ents_lower]
        applicability = "applicable" if matched_entities else "not_applicable"

    # 3. Append to auto_track or manual_track with applicability/matched_entities fields
```

Dedup (step 1) runs before applicability scoring (step 2). This prevents wasted work on rows that will be discarded and ensures the first occurrence's entity set is used for scoring.

### FR-013 / FR-014 — search_openrewrite_recipes filters

The current flow: BM25+vector → element IDs → `hydrate_openrewrite_recipes(element_ids)`. Filters must apply in `hydrate_openrewrite_recipes` at Cypher WHERE.

In `search_queries.hydrate_openrewrite_recipes`, add parameters `only_composite: bool | None` and `require_no_params: bool`:
```cypher
WHERE elementId(r) IN $ids
  AND (NOT $only_composite OR r.composite = true)
  AND (NOT $require_no_params OR NOT EXISTS {
    MATCH (r)-[:HAS_PARAM]->(p:RecipeParam) WHERE p.required = true
  })
```

In `search.py` tool layer: pass `only_composite` and `require_no_params` through to `hydrate_openrewrite_recipes`. Remove the deferred `pass` block.

### FR-015 through FR-020 — check_version_availability (new tool)

New function in `upgrade.py` tool layer. Decorated with `@mcp.tool()`.

```python
_FRAMEWORK_MAVEN_COORDS = {
    "spring-boot": ("org.springframework.boot", "spring-boot"),
}

@mcp.tool()
def check_version_availability(framework: str, version: str) -> dict:
    ...
```

Steps:
1. Normalise version: `normalised = to_minor_zero(version)`
2. Lookup Maven coords: if framework not in `_FRAMEWORK_MAVEN_COORDS`, return `{status: "error", error_code: "unsupported_framework", exists_in_graph: false, ga_available: false, latest_patch: None, hint: "Unknown framework; supported: spring-boot"}` — no network call
3. Graph read: `MATCH (v:Version {framework: $framework, version: $normalised}) RETURN v` → `exists_in_graph`
4. Maven Central probe: `GET https://search.maven.org/solrsearch/select?q=g:{gId}+AND+a:{aId}+AND+v:{normalised}&rows=1&wt=json` with `timeout=10`. **On any network error (timeout, connection error, HTTP 5xx)**: MUST NOT raise; return `{status: "ok", exists_in_graph: <from step 3>, ga_available: False, latest_patch: None, hint: "Maven Central unavailable — could not verify GA status"}`
5. Parse `response.json()["response"]["numFound"]` — `>= 1` means `ga_available=True`
6. Latest patch query (only when step 5 succeeds): `GET .../solrsearch/select?q=g:{gId}+AND+a:{aId}&rows=1&wt=json&sort=version+desc` — extract `docs[0]["v"]` as `latest_patch`; on error set `latest_patch=None`

### FR-021 / FR-022 / FR-023 — framework_migration_main.md

**Insertion point**: Insert the STATELESS FALLBACK block immediately after Loop I step 6 (`Call create_migration_context`) and immediately before the `## Loop II — Scope-gated query` header. Do not alter or reorder any existing Loop I steps or any Loop II–IV content.

Add a **STATELESS FALLBACK** section at that location:

```markdown
### Loop I — Stateless Fallback

**Trigger**: `create_migration_context` returns an error on both the initial attempt and one retry.

**Instructions**:
1. Log the failure to the user: "Context creation failed; continuing in stateless mode."
2. Continue with `analyze_upgrade_path` and `build_recipe_plan` using the scanned entities from the codebase scan.
3. Skip all tools that require a `context_id` (get_pending_steps, update_step_status, get_steps_for_scope_tier, close_migration_context).
4. Track step state in agent context only (in-memory, not persisted).
5. For every high-confidence finding (build passes), call `submit_migration_insight` without a `context_id`.
6. At session end, emit a summary noting that the session ran in stateless mode and no graph state was persisted.
```

**grep fix** _(verified)_: `grep` was searched in `framework_migration_main.md` and returned zero matches — confirmed no inline grep commands exist in the file. The scanning patterns are referenced via `skill://framework-migration/scanning` URIs; the grep commands live in `framework_migration_scanning.md` which is out of scope for this spec. The `grep -E` requirement therefore applies exclusively to any new inline shell examples introduced by the stateless fallback block above. If the fallback block includes a shell scanning snippet, it MUST use `grep -E` (not `grep -P`). No existing lines in the file need to be modified.

## Framework → Maven Coordinate Lookup Table

_(Required by FR-017; minimum required entry for spec 010)_

| Framework key | groupId | artifactId |
|---|---|---|
| `spring-boot` | `org.springframework.boot` | `spring-boot` |

Additional entries (Angular, Spring Framework, etc.) can be added in `plan.md` amendments without a new spec.

## Test Mock State

All tests in `tests/mcp/` and `tests/paysafe/` use `unittest.mock.patch` — no live Neo4j instance is required. The existing `conftest.py` only sets `NEO4J_URI`/`NEO4J_PASSWORD` environment variables.

### tests/mcp/test_context_fixes.py — required mock data

| Test | Mock target | Mock return value |
|---|---|---|
| `test_normalises_patch_version` | `context_queries.create_or_get_context` | valid context dict; verify it is called with `from_version="3.5.0"` (not `"3.5.12"`) |
| `test_version_not_in_graph` | `context_queries.create_or_get_context` | raise `RuntimeError` (simulates `.single()` → None path) |
| `test_zombie_cleanup_on_version_miss` | `context_queries.create_or_get_context` + `context_queries.delete_zombie_context` | first returns None; verify delete query is called with `from_version="3.5.0"` |
| `test_stepnotes_persisted` | `context_queries.record_step_outcome` | verify `reason="already handled"` reaches the query layer; mock `get_stepnotes` read returning `{}` |
| `test_scope_tier_returns_scopeless_steps` | `context_queries.get_steps_for_scope_tier` | return row with `scope=None`; verify step appears in result with `scope: null` |

Key invariant for normalization tests: **`Version {version: "3.5.12"}` is never a valid mock return** — the test exercises that `to_minor_zero("3.5.12")` → `"3.5.0"` is applied before the query, and the query is mocked to expect `"3.5.0"`. The raw patch form `"3.5.12"` must never reach the graph query layer.

### tests/mcp/test_recipe_applicability.py — required mock data

| Test | Mock input | Expected output |
|---|---|---|
| `test_applicable_steps` | `user_entities=["com.example.Foo"]`, row has `all_affected_entities=["com.example.Foo"]` | `applicability="applicable"`, `matched_entities=["com.example.Foo"]` |
| `test_not_applicable_steps` | `user_entities=["com.example.Bar"]`, row has `all_affected_entities=["com.example.Foo"]` | `applicability="not_applicable"`, `matched_entities=[]` |
| `test_unknown_when_empty_entities` | `user_entities=[]` | all steps `applicability="unknown"` |
| `test_dedup_first_occurrence_wins` | two rows with same `step_id="s1"`, different summaries | only first row appears in output |

### tests/paysafe/test_resolver_credential_scrub.py — required mock data

| Test | Input | Expected |
|---|---|---|
| `test_scrubs_oauth2_token` | `_build_error(message="oauth2:TOKEN@gitlab.example.com/repo")` | message contains `<redacted>@` not `TOKEN` |
| `test_scrubs_basic_auth` | `_build_error(message="https://user:pass@host/path")` | credential segment replaced |
| `test_clean_message_unchanged` | `_build_error(message="something went wrong")` | message unchanged |
| `test_artifactory_fallback_called` | mock `_GitError("git_ls_remote_failed")` + `ARTIFACTORY_BASE_URL` set + Artifactory returns `"2.3.1"` | `resolve()` returns `status="ok"` |
| `test_no_fallback_without_env_var` | mock `_GitError` + `ARTIFACTORY_BASE_URL` unset | returns `status="error"` |

## Complexity Tracking

No constitution violations. All changes are targeted patches; no new abstractions, no new external services beyond Maven Central and optional Artifactory.

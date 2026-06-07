# SpecKit Runbook — `004-paysafe-resolver`

> **How to use this file:** Paste each prompt block verbatim into Claude Code in the order shown.
> Do not skip the gap-review steps — they catch the most common drift before it compounds.
> Complete all items in a gap review before advancing to the next command.

---

## Prerequisites

Before starting this spec:

- `001-foundations` ✅ — `MigrationEntitiesBatch`, `config.py` (env vars), and `graph/driver.py` must be importable
- `FINDIT_AUTH_TOKEN` and `GITLAB_API_KEY` must be documented in `config.py`
- `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` (default `0.68`) must be in `config.py`
- `uv sync` must produce a clean environment
- Reference docs to keep open while reviewing gap prompts:
  - `docs/graph-mcp-skills-and-paysafe-resolution.md` §11–12
  - `docs/SPEC_ORGANIZATION.md` §004

**NEW REQUIREMENT (beyond the reference spec):**  
The resolver must also support a **manual override mode** where the caller supplies
a `pinned_version` (and optionally `pinned_tag`) directly, bypassing FindIt and GitLab entirely.
This is needed when FindIt is unreachable, a service is not registered, or an operator wants
to force a specific known-good version. The manual mode must surface in the tool response with
`selection_strategy: "pinned"` and no `name_resolution` metadata.

---

## Command 1 — `/speckit.specify`

Paste this entire block:

```
/speckit.specify

WHAT it does:
The Paysafe Resolver module (`migration_oracle/paysafe/`) resolves a Paysafe-internal
library to the correct version for a target framework upgrade. Given a service name and
an optional target framework version, it locates the library's GitLab repository via
the FindIt registry, enumerates its git tags, checks each tag's build file for a declared
framework version, and returns the newest tag that is compatible with the caller's target.

When the caller already knows the version they want, they can supply `pinned_version`
(and optionally `pinned_tag`) to bypass all network lookups and receive a "pinned" result
immediately, without touching FindIt or GitLab.

WHY it exists:
Paysafe applications depend on internal libraries (`com.paysafe.*` Maven coordinates).
When upgrading a framework (e.g. Spring Boot 3.3 → 3.5), those internal libraries must
be bumped to versions that were themselves built against a compatible framework version.
No public registry exposes this information; it must be derived from the library's own
build files at specific git tags.

RESOLVER and what it does:
  - Resolves a library version from FindIt + GitLab, OR returns a caller-supplied pinned
    version when `pinned_version` is provided
  - Supported operations: resolve(service_name, target_version, framework, allow_latest_overall,
    max_tags, pinned_version, pinned_tag)
  - Returns a structured result with: status, selected_tag, selected_version,
    framework_version, selection_strategy, name_resolution metadata (when applicable)

FINDIT CLIENT and what it does:
  - Fetches and caches the full FindIt service list (in-memory, 30-day TTL)
  - Applies four-level name matching: exact → case-insensitive → alphanumeric-normalized → fuzzy
  - Fuzzy threshold configurable via FINDIT_SERVICE_NAME_FUZZY_THRESHOLD (default 0.68)
  - Returns the matched service record with `codeRepoLink`, or an error with suggestions

GITLAB CLIENT and what it does:
  - Converts GitLab HTTPS URLs to SCP-style git locators
  - Lists remote tags via git ls-remote with configurable timeout and retries
  - Fetches build files at a specific tag ref via git archive
  - Detects framework from build-file presence at HEAD (pom.xml → spring-boot; package.json → angular)
  - Parses Spring Boot version from: spring-boot-starter-parent POM, spring-boot.version property,
    or Gradle plugin version declaration
  - Parses Angular version from @angular/core in package.json dependencies or devDependencies

KEY BEHAVIORS:
PINNED MODE — When `pinned_version` is provided, the resolver returns immediately with
  `selection_strategy: "pinned"`, `selected_version: pinned_version`, and
  `selected_tag: pinned_tag` (if supplied, else null). No FindIt or GitLab call is made.
  Response shape is identical to the standard success shape with strategy set to "pinned".

FOUR-LEVEL NAME MATCHING — FindIt lookup tries exact → case-insensitive → alphanumeric
  normalization → fuzzy in sequence; stops at the first successful level.
  Fuzzy match only fires if similarity ≥ threshold (env: FINDIT_SERVICE_NAME_FUZZY_THRESHOLD).
  On non-exact match, `name_resolution` metadata is always included in the response.

COMPATIBILITY RULE — A tag's declared framework version is compatible when:
  (1) same major as target, AND (2) declared ≥ target at major.minor.patch tuple level.
  Example: declares 3.5.10, target 3.5.6 → compatible. Declares 3.4.0, target 3.5.6 → not compatible.

SELECTION STRATEGY — Exactly three valid strategies:
  "latest_compatible": target_version set, compatible tag found — return newest compatible.
  "latest_overall": target_version omitted (MCP layer forces allow_latest_overall=true), OR
    target_version set but no compatible tag found and allow_latest_overall=true.
  "latest_with_known_compatibility": target_version omitted, need readable build file.
  "pinned": caller supplied pinned_version directly.

FINDIT CACHE — The full service list is cached in-memory with a 30-day TTL.
  Cache is a module-level singleton initialized lazily on first call. Never fetched per-call.

TAG PARSING — Tags must be semantically parsable (e.g. "3.5.10", "3.5.10.A").
  Tags that cannot be parsed as versions are silently skipped.
  Sorted descending by semantic version; newest considered first.

ERROR ISOLATION — Every error case produces a structured error response with `status: "error"`,
  `error_code`, `message`, `recoverable` flag, `actionable_hint`, and `details`.
  Errors never raise uncaught exceptions to the caller — always return the error response shape.

RETRIES — FindIt HTTP calls and git operations each support 2 retries with configurable
  backoff (default: 1s, 3s). Timeout also configurable. On exhaustion: http_timeout or
  http_request_failed error code.

INTEGRATION CONSTRAINTS:
- All env vars (FINDIT_AUTH_TOKEN, GITLAB_API_KEY, FINDIT_SERVICE_NAME_FUZZY_THRESHOLD) loaded
  from migration_oracle/config.py — do not re-read env vars inline in paysafe/ modules
- The resolver module lives at migration_oracle/paysafe/ — no code outside this directory
  may import implementation details; only the resolver's public function is imported by mcp/tools/paysafe.py
- FindIt cache must be a module-level singleton — never instantiate per-call
- All git operations go through migration_oracle/paysafe/gitlab.py — no subprocess git calls
  scattered in resolver.py
- Error responses must never raise; they must always be returned as structured dicts
- Pinned mode must short-circuit before any network I/O — do not call FindIt or GitLab if
  pinned_version is supplied
```

---

## Gap Review — Post-Specify

After `/speckit.specify` generates `spec.md`, paste this before running `/speckit.plan`:

```
Review the generated spec.md for 004-paysafe-resolver and fix any of the following gaps
before we proceed to planning:

GAP-001: Pinned mode response shape
  Spec must state the exact response shape for pinned mode:
  { status: "ok", service_name: <input>, selected_version: pinned_version,
    selected_tag: pinned_tag | null, selection_strategy: "pinned",
    framework: null, framework_version: null, name_resolution: absent }.
  If the spec says pinned mode returns a different shape or omits any of these fields, correct it.

GAP-002: Error response shape completeness
  Every one of these seven error_code values must appear in the spec with trigger condition:
  invalid_service_name, service_not_found, no_repo_url, no_tags_found,
  no_compatible_version, compatibility_unknown, http_timeout, http_request_failed.
  Add any that are missing.

GAP-003: FindIt cache invalidation
  The spec must state that the 30-day TTL cache has no explicit invalidation path —
  it simply expires. If the spec implies a force-refresh or eviction method, remove it.

GAP-004: Alphanumeric normalization definition
  The spec must define alphanumeric normalization as: strip all non-alphanumeric characters,
  lowercase, then compare. If it is vague ("normalize somehow"), specify this exactly.

GAP-005: Framework detection order at HEAD
  The spec must state the probe order at HEAD: pom.xml first → build.gradle / build.gradle.kts
  second → package.json third. If order is unspecified or wrong, fix it.

GAP-006: Compatibility rule edge cases
  The spec must address what happens when the build file at a tag exists but declares NO
  parsable framework version. This tag must be counted as "compatibility unknown" and skipped
  when using latest_compatible strategy, but included when using latest_overall.

GAP-007: Tag sort format
  The spec must state that the "A" suffix in tags like "3.5.10.A" is stripped before
  semantic sort, so "3.5.10.A" sorts as "3.5.10". If this is absent, add it.

GAP-008: name_resolution absence in pinned mode
  The spec must explicitly say `name_resolution` is NOT present in pinned-mode responses
  (it is only present when FindIt did a non-exact match). If the spec is ambiguous, fix it.

GAP-009: allow_latest_overall MCP default
  The spec must note that when the MCP tool omits target_version, the MCP layer internally
  forces allow_latest_overall=true. This is a caller-side default, not a resolver default.
  The resolver itself must not default allow_latest_overall; the caller must be explicit.

GAP-010: Write boundary
  The resolver module is read-only — it never writes to the Neo4j/Memgraph graph.
  Confirm this is stated. If absent, add it.
```

---

## Command 2 — `/speckit.plan`

After spec.md is clean, paste:

```
/speckit.plan

Generate plan.md, data-model.md, contracts/004-paysafe-resolver.md, research.md,
and quickstart.md for 004-paysafe-resolver.

Required file layout (do not deviate):

migration_oracle/
└── paysafe/
    ├── __init__.py          # exports: resolve()
    ├── resolver.py          # orchestrates the seven-step flow + pinned mode short-circuit
    ├── findit.py            # FindIt HTTP client, cache, four-level name matching
    └── gitlab.py            # Git tag listing, archive fetch, build-file parsing, framework detection

tests/
└── paysafe/
    ├── test_resolver.py     # integration-style tests with mocked HTTP/git
    ├── test_findit.py       # unit tests: cache TTL, all four matching levels, error shapes
    └── test_gitlab.py       # unit tests: tag sort, compatibility rule, build-file parse

Required artifacts:
- data-model.md: ResolverResult (all fields), NameResolution (all fields), CompatibilityInfo,
  ErrorResponse (all fields including error_code enum), ResolveRequest (all input params
  including pinned_version and pinned_tag)
- contracts/004-paysafe-resolver.md: what mcp/tools/paysafe.py may and may not call;
  that resolver.py is the only public entry point; that paysafe/ never imports from pipeline/
- research.md: choice of git client library (gitpython vs subprocess vs dulwich),
  choice of fuzzy matching library (thefuzz / rapidfuzz), semantic version parsing library
- quickstart.md: how to run tests with mocked FindIt and GitLab; required env vars;
  how to smoke-test with a real FindIt call

Tech stack: Python 3.11+, uv, pytest, httpx (or requests — match what 001-foundations uses),
rapidfuzz for fuzzy matching, packaging.version for semantic sort.

Plan must include [P] parallelism markers — findit.py and gitlab.py can be implemented
concurrently; test files are parallel after their implementation files are done.
```

---

## Gap Review — Post-Plan

After `/speckit.plan` generates the plan artifacts, paste:

```
Review the generated plan.md, data-model.md, contracts/004-paysafe-resolver.md, and
quickstart.md for 004-paysafe-resolver and fix any of the following gaps:

PLAN-GAP-001: ResolveRequest pinned fields
  data-model.md must include pinned_version: str | None and pinned_tag: str | None
  in the ResolveRequest type. If absent or typed incorrectly, fix it.

PLAN-GAP-002: ErrorResponse error_code enum
  data-model.md must list all eight error_code values as a literal enum or TypedLiteral:
  invalid_service_name, service_not_found, no_repo_url, no_tags_found,
  no_compatible_version, compatibility_unknown, http_timeout, http_request_failed.
  If the list is incomplete, add missing values.

PLAN-GAP-003: CompatibilityInfo source_precedence
  data-model.md must show CompatibilityInfo with fields: framework_version (str),
  source_file (str), source_precedence (str — e.g. "spring-boot-starter-parent").
  If source_precedence is absent, add it.

PLAN-GAP-004: FindIt cache structure
  plan.md or data-model.md must show how the 30-day in-memory cache is structured:
  a module-level dict keyed by a stable cache key (e.g. the FindIt URL), holding
  (service_list, fetched_at_timestamp). If it is described as a simple variable without
  expiry tracking, correct it.

PLAN-GAP-005: Contracts write boundary explicit
  contracts/004-paysafe-resolver.md must state: "paysafe/ modules must not write to
  Neo4j/Memgraph. No graph driver import is permitted in this package." If absent, add it.

PLAN-GAP-006: Contracts import restriction
  contracts/004-paysafe-resolver.md must state that mcp/tools/paysafe.py imports ONLY
  migration_oracle.paysafe.resolver.resolve — not findit.py or gitlab.py directly.
  If this delegation rule is missing, add it.

PLAN-GAP-007: Quickstart env vars
  quickstart.md must list: FINDIT_AUTH_TOKEN, GITLAB_API_KEY,
  FINDIT_SERVICE_NAME_FUZZY_THRESHOLD (and its default). If any are absent, add them.

PLAN-GAP-008: Quickstart pinned smoke test
  quickstart.md must show a minimal invocation in pinned mode:
    from migration_oracle.paysafe.resolver import resolve
    result = resolve("any-name", pinned_version="3.5.10", pinned_tag="3.5.10.A")
    assert result["selection_strategy"] == "pinned"
  If absent, add it.

PLAN-GAP-009: Parallel markers
  plan.md must mark findit.py and gitlab.py implementation tasks [P].
  Test files for findit and gitlab must be marked [P] relative to each other.
  If [P] markers are missing, add them.

PLAN-GAP-010: Python version
  plan.md must state Python 3.11+ as the minimum runtime. If absent, add it.
```

---

## Command 3 — `/speckit.tasks`

After plan artifacts are clean:

```
/speckit.tasks
```

No additional arguments needed — it reads spec.md and plan.md automatically.

---

## Gap Review — Post-Tasks

After `/speckit.tasks` generates `tasks.md`, paste:

```
Review the generated tasks.md for 004-paysafe-resolver and fix any of the following:

TASK-GAP-001: Foundation-first ordering
  The task for creating data-model types (ResolverResult, NameResolution, CompatibilityInfo,
  ErrorResponse, ResolveRequest) must appear BEFORE any implementation task for findit.py,
  gitlab.py, or resolver.py. If it is ordered after, move it first.

TASK-GAP-002: Pinned mode task exists
  There must be a discrete task for implementing pinned mode short-circuit in resolver.py,
  including the assertion that no HTTP/git call is made when pinned_version is supplied.
  If it is folded into a generic "implement resolver" task without being called out, add it.

TASK-GAP-003: Cache TTL task
  There must be a task that specifically implements the 30-day TTL check on the FindIt cache
  (compare current time to fetched_at, invalidate and refetch if expired).
  If this is missing, add it under the findit.py implementation tasks.

TASK-GAP-004: All seven error codes tested
  There must be individual test tasks (or clearly enumerated scenarios within one task)
  covering all seven error codes: invalid_service_name, service_not_found, no_repo_url,
  no_tags_found, no_compatible_version, compatibility_unknown, http_timeout.
  If any are absent, add them.

TASK-GAP-005: Fuzzy matching level tested
  There must be a test task for each of the four FindIt matching levels (exact, case-insensitive,
  alphanumeric-normalized, fuzzy). If they are bundled as "test name matching" without individual
  scenarios, split them.

TASK-GAP-006: Compatibility rule boundary test
  There must be a test task that specifically checks the compatibility rule rejects:
  (a) same-major but lower minor, and (b) different-major version.
  If this is not present, add it.

TASK-GAP-007: E2E happy-path test
  There must be one end-to-end test task that exercises the full flow from service_name input
  to selected_tag output with mocked FindIt and GitLab responses — not just unit-level assertions.
  If absent, add it.

TASK-GAP-008: Pinned mode E2E test
  There must be a test task that calls resolve() with pinned_version and asserts:
  no HTTP call was made AND selection_strategy == "pinned". If absent, add it.

TASK-GAP-009: File path correctness
  Every task that creates a file must reference the exact path from plan.md:
  migration_oracle/paysafe/__init__.py, migration_oracle/paysafe/resolver.py,
  migration_oracle/paysafe/findit.py, migration_oracle/paysafe/gitlab.py,
  tests/paysafe/test_resolver.py, tests/paysafe/test_findit.py, tests/paysafe/test_gitlab.py.
  If any task uses a flat or wrong path, correct it.
```

---

## Command 4 — `/speckit.implement`

After tasks.md is clean:

```
/speckit.implement
```

---

## Recovery Prompts

Use these verbatim if Claude Code's implementation drifts from the spec.

---

### Recovery 1 — FindIt client instantiated per call

```
Do not instantiate the FindIt cache or fetch the service list inside resolve() or any
per-call function. The FindIt service list cache must be a module-level variable in
migration_oracle/paysafe/findit.py, initialized to None, and loaded lazily on first call
via a get_service_list() function that checks expiry (30-day TTL) before returning.
Never fetch the list more than once per cache window regardless of how many resolve()
calls are made concurrently.
```

---

### Recovery 2 — Pinned mode makes HTTP calls

```
When pinned_version is supplied, resolver.py must return immediately with the pinned
result — before calling any function in findit.py or gitlab.py.
The check must be the very first conditional in resolve():
  if pinned_version is not None:
      return build_pinned_result(service_name, pinned_version, pinned_tag)
Do not call FindIt "for informational purposes" or "to enrich the pinned response" —
pinned mode must make zero network calls.
```

---

### Recovery 3 — Error raised instead of returned

```
The resolver and its sub-modules (findit.py, gitlab.py) must never raise exceptions to
the caller of resolve(). All error conditions must be caught internally and returned as
a structured dict with { status: "error", error: { error_code, message, recoverable,
actionable_hint, details } }. Do not let HTTPError, GitCommandError, or any network
exception propagate out of migration_oracle/paysafe/. Only raise inside the module for
internal signalling between findit.py/gitlab.py and resolver.py (which re-catches them).
```

---

### Recovery 4 — Graph driver imported in paysafe/

```
Do not import neo4j, migration_oracle.graph.driver, or any graph-related module inside
migration_oracle/paysafe/. This package is read-only and has no graph dependency.
If you need to write resolution results to the graph, that write belongs in the MCP tool
layer (mcp/tools/paysafe.py), not in the resolver. Remove any graph import from paysafe/.
```

---

### Recovery 5 — mcp/tools/paysafe.py imports findit.py or gitlab.py directly

```
mcp/tools/paysafe.py must import only migration_oracle.paysafe.resolver.resolve.
Do not import from migration_oracle.paysafe.findit or migration_oracle.paysafe.gitlab
anywhere outside the paysafe/ package. The resolver is the single public API of the
paysafe package — internal modules are implementation details.
```

---

### Recovery 6 — allow_latest_overall defaulting incorrectly

```
The resolver function signature must NOT default allow_latest_overall to True.
It must default to False. The MCP layer (mcp/tools/paysafe.py) is responsible for
passing allow_latest_overall=True when target_version is omitted from the tool call.
If the resolver defaults to True, the error path for no_compatible_version will never
be reachable — which breaks the tests. Fix the default to False and update the MCP
tool wrapper to set it True when target_version is absent.
```

---

## What Success Looks Like

Run the following smoke tests after `/speckit.implement` completes.
All must pass before marking `004-paysafe-resolver` ✅ Complete in `docs/SPEC_ORGANIZATION.md`.

### 1. Pinned mode (no network required)

```python
from migration_oracle.paysafe.resolver import resolve

result = resolve("any-service", pinned_version="3.5.10", pinned_tag="3.5.10.A")
assert result["status"] == "ok"
assert result["selected_version"] == "3.5.10"
assert result["selected_tag"] == "3.5.10.A"
assert result["selection_strategy"] == "pinned"
assert "name_resolution" not in result
```

### 2. Invalid service name guard

```python
result = resolve("")
assert result["status"] == "error"
assert result["error"]["error_code"] == "invalid_service_name"
```

### 3. Compatibility rule unit check

```python
from migration_oracle.paysafe.gitlab import is_compatible

assert is_compatible(declared="3.5.10", target="3.5.6")   is True
assert is_compatible(declared="3.4.0",  target="3.5.6")   is False
assert is_compatible(declared="2.7.18", target="3.5.6")   is False
assert is_compatible(declared="18.2.0", target="18.0.0")  is True
```

### 4. Full mock E2E (pytest)

```
pytest tests/paysafe/test_resolver.py -v
```

All tests must pass. Look especially for:
- `test_latest_compatible_selected` — verifies correct tag is chosen
- `test_no_compatible_version_error` — verifies error when no compatible tag exists
- `test_pinned_mode_no_http` — verifies zero network calls in pinned mode
- `test_fuzzy_name_resolution_metadata` — verifies name_resolution block present on fuzzy match
- `test_all_error_codes` — parametrized or individual tests for all 7 error codes

---

## Updating `docs/SPEC_ORGANIZATION.md`

Once all smoke tests pass, update the status table:

```
| `004` | Paysafe Resolver | ✅ Complete | `specs/004-paysafe-resolver/` |
```

Then create `specs/004-paysafe-resolver/` with the SpecKit artifacts from this run
(spec.md, plan.md, data-model.md, contracts/, tasks.md, research.md, quickstart.md).

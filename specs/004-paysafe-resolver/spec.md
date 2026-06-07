# Feature Specification: Paysafe Internal Library Version Resolver

**Feature Branch**: `004-paysafe-resolver`

**Created**: 2026-06-06

**Status**: Draft

**Input**: User description: "Paysafe Resolver module that resolves internal library versions for framework upgrades using FindIt registry and GitLab build file scanning, with pinned version bypass mode."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resolve Compatible Library Version (Priority: P1)

A caller (MCP tool or automated pipeline) knows the name of a Paysafe internal library and a target framework version (e.g., Spring Boot 3.5.6). They ask the resolver to find the newest library release that was itself built against a compatible framework version. The resolver queries FindIt to locate the library's GitLab repository, scans git tags descending by version, inspects each tag's build file, and returns the newest tag whose declared framework version satisfies the compatibility rule.

**Why this priority**: This is the core value proposition — without it, upgrade automation cannot determine safe internal dependency versions.

**Independent Test**: Can be fully tested by calling `resolve(service_name="my-lib", target_version="3.5.6", framework="spring-boot")` against a mocked FindIt + GitLab layer and verifying the response contains `selection_strategy: "latest_compatible"` with the expected tag and version.

**Acceptance Scenarios**:

1. **Given** a library whose tags include `3.5.10` (declares Spring Boot 3.5.10) and `3.4.0` (declares 3.4.0), **When** `resolve` is called with `target_version="3.5.6"`, **Then** the result has `selected_tag="3.5.10"`, `selected_version="3.5.10"`, `selection_strategy="latest_compatible"`, and `status="ok"`.
2. **Given** no tag declares a framework version ≥ target (same major), **When** `resolve` is called with `allow_latest_overall=False`, **Then** the result has `status="error"` with `error_code="no_compatible_version"`.
3. **Given** no compatible tag exists but `allow_latest_overall=True`, **When** `resolve` is called, **Then** the result has `selection_strategy="latest_overall"` and `status="ok"` with the newest parseable tag.

---

### User Story 2 - Return Pinned Version Without Network I/O (Priority: P1)

A caller already knows which version of a library to use (e.g., it was previously resolved and persisted). They supply `pinned_version` (and optionally `pinned_tag`) to the resolver. The resolver must return immediately with a "pinned" result, making no calls to FindIt or GitLab, regardless of any other parameters.

**Why this priority**: Pinned mode is a critical performance and reliability path — callers with known answers should never incur network latency or be blocked by external service outages.

**Independent Test**: Can be tested by calling `resolve(service_name="any", pinned_version="3.5.10", pinned_tag="3.5.10")` with all network clients stubbed to raise errors — the result must be `selection_strategy: "pinned"` with no network calls made.

**Acceptance Scenarios**:

1. **Given** `pinned_version="3.5.10"` and `pinned_tag="3.5.10"`, **When** `resolve` is called, **Then** the result has `status="ok"`, `selected_version="3.5.10"`, `selected_tag="3.5.10"`, `selection_strategy="pinned"`, `framework=null`, `framework_version=null`, `name_resolution` key absent, and no FindIt or GitLab calls were made.
2. **Given** `pinned_version="3.5.10"` with no `pinned_tag` supplied, **When** `resolve` is called, **Then** `selected_tag` is `null` and `selection_strategy="pinned"`.
3. **Given** `pinned_version` is supplied alongside a valid `service_name` and `target_version`, **When** `resolve` is called, **Then** FindIt and GitLab are never contacted and the pinned result is returned as-is.

---

### User Story 3 - Fuzzy Name Matching for Library Lookup (Priority: P2)

A caller provides a library name that does not exactly match the FindIt service registry (e.g., due to casing, hyphens, or minor spelling variations). The resolver applies a four-level matching cascade (exact → case-insensitive → alphanumeric-normalized → fuzzy) and returns the best match. On any non-exact match, the response includes `name_resolution` metadata documenting the matched name and the matching level used.

**Why this priority**: Internal library names are inconsistently referenced in project files; strict matching would cause unnecessary lookup failures.

**Independent Test**: Can be tested by seeding a mock FindIt response with `"my-internal-lib"` and calling `resolve(service_name="MyInternalLib")` — the result must have `name_resolution.method="alphanumeric_normalized"` and `name_resolution.matched_name="my-internal-lib"`.

**Acceptance Scenarios**:

1. **Given** FindIt contains `"payment-service"`, **When** `resolve` is called with `service_name="Payment Service"`, **Then** `name_resolution.method` is `"case_insensitive"` or `"alphanumeric_normalized"` and the repo link is returned.
2. **Given** the service name is close but not an exact match and similarity exceeds the configured threshold, **When** `resolve` is called, **Then** `name_resolution.method="fuzzy"`, `name_resolution.matched_name` is the canonical registry name, `name_resolution.similarity` is the numeric similarity score, and `name_resolution.alternatives` lists other close candidates.
3. **Given** no match is found at any level, **When** `resolve` is called, **Then** `status="error"`, `error_code="service_not_found"`, and the error response includes suggested similar names from FindIt.

---

### User Story 4 - Resolve Latest Version Without Target Constraint (Priority: P2)

A caller omits `target_version` entirely. When this happens, the MCP layer is responsible for explicitly passing `allow_latest_overall=True` to the resolver — this is a caller-side default, not a resolver default. The resolver returns the newest parseable tag, reading its build file to report `framework_version` if available, using strategy `"latest_overall"` or `"latest_with_known_compatibility"` as appropriate.

**Why this priority**: Callers that do not yet know their target version still need a sensible "latest" answer with observability into what framework that version targets.

**Independent Test**: Can be tested by calling `resolve(service_name="my-lib")` (no `target_version`) against a mock GitLab with known tags — the result must be the tag with the highest semver, with `selection_strategy` set appropriately.

**Acceptance Scenarios**:

1. **Given** `target_version` is omitted and the newest tag's build file is readable, **When** `resolve` is called, **Then** `selection_strategy="latest_with_known_compatibility"` and `framework_version` is populated.
2. **Given** `target_version` is omitted and the newest tag's build file cannot be read, **When** `resolve` is called, **Then** `selection_strategy="latest_overall"` and `framework_version` is `null`.

---

### User Story 5 - Structured Error on Any Failure (Priority: P1)

Any failure scenario (FindIt unreachable, library not found, no parseable tags, git timeout) must produce a structured error response — never an uncaught exception. The error response carries enough information for the caller to decide whether to retry or surface the error to the user.

**Why this priority**: The resolver is called in automated pipelines; uncaught exceptions would crash the pipeline rather than allowing graceful degradation.

**Independent Test**: Can be tested by simulating each failure mode (network timeout, 404, no tags) and asserting the response always has `status="error"`, `error_code`, `message`, `recoverable`, and `actionable_hint` fields.

**Acceptance Scenarios**:

1. **Given** FindIt returns a network timeout after retries are exhausted, **When** `resolve` is called, **Then** `status="error"`, `error_code="http_timeout"`, `recoverable=True`.
2. **Given** GitLab `ls-remote` fails (network error or auth failure), **When** `resolve` is called, **Then** `status="error"`, `error_code="git_ls_remote_failed"`, `recoverable=True`, and `actionable_hint` suggests checking credentials.
3. **Given** the repository has tags but none can be parsed as semantic versions, **When** `resolve` is called, **Then** `status="error"`, `error_code="no_parseable_tags"`, `recoverable=False`.

---

### Edge Cases

- What happens when a tag exists but its build file is missing or malformed? (Tag is silently skipped; if all tags are skipped, falls through to `latest_overall` or error.)
- What happens when FindIt returns an empty service list? (`status="error"`, `error_code="service_not_found"` with no suggestions.)
- What happens when `max_tags` is reached before a compatible tag is found? (Return best result found so far under `latest_overall` if allowed, else error.)
- What happens when the FindIt cache is populated but stale (>30 days)? (The cache simply expires — there is no explicit invalidation path. The next call after expiry re-fetches the full service list and replaces the stale entry.)
- What happens when a tag uses an unsupported version format like `3.5.10.RELEASE`? (Must be parseable; `3.5.10.A` is acceptable. Tags failing parsing are silently skipped.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The resolver MUST accept `service_name`, `target_version` (optional), `framework` (optional), `allow_latest_overall` (optional), `max_tags` (optional), `pinned_version` (optional), and `pinned_tag` (optional) as parameters to its public `resolve` function.
- **FR-002**: When `pinned_version` is provided, the resolver MUST return immediately with the following exact response shape and MUST NOT contact FindIt or GitLab:
  `{ status: "ok", service_name: <input service_name>, selected_version: <pinned_version>, selected_tag: <pinned_tag | null>, selection_strategy: "pinned", framework: null, framework_version: null, target_version: <input target_version | null>, code_repo_link: null, compatibility: null }`.
  The `name_resolution` key MUST be absent from pinned-mode responses.
- **FR-003**: The resolver MUST locate a library's git repository by querying the FindIt service registry using the four-level name matching cascade: exact → case-insensitive → alphanumeric-normalized → fuzzy. Alphanumeric normalization is defined as: strip all non-alphanumeric characters, lowercase the result, then compare. Example: `"My-Internal.Lib"` normalizes to `"myinternallib"`.
- **FR-004**: Fuzzy matching MUST only fire when the similarity score meets or exceeds the configured threshold (default 0.68); the threshold MUST be configurable via environment variable.
- **FR-005**: On any non-exact name match, the resolver MUST include `name_resolution` metadata in the response with the following fields: `method` (one of `"case_insensitive"`, `"alphanumeric_normalized"`, `"fuzzy"`), `matched_name` (the canonical name from FindIt). For fuzzy matches, `similarity` (numeric score) and `threshold_used` (the configured threshold) MUST also be present, and `alternatives` (list of other close candidate names) SHOULD be included when available.
- **FR-006**: The FindIt service list MUST be cached in-memory as a module-level singleton with a 30-day TTL; the cache MUST be initialized lazily on first call and MUST NOT be re-instantiated per call. There is no explicit invalidation path — the cache simply expires after 30 days and is re-fetched on the next call; no eviction or force-refresh mechanism is provided.
- **FR-007**: The resolver MUST enumerate git tags for the matched repository, parse them as semantic versions, silently skip unparseable tags, and process them in descending version order (newest first). Tags with an alphabetic suffix (e.g., `3.5.10.A`) MUST have the suffix stripped before semantic sorting, so `3.5.10.A` sorts as `3.5.10`.
- **FR-008**: A tag's declared framework version MUST be considered compatible when: (1) its major version equals the target's major, AND (2) its `(major, minor, patch)` tuple is ≥ the target's tuple. If the build file at a tag exists but declares no parseable framework version, that tag MUST be counted as "compatibility unknown": it is skipped when using the `latest_compatible` strategy but included (as the newest parseable-version tag) when falling back to `latest_overall`.
- **FR-009**: The resolver MUST select the newest compatible tag when `target_version` is set and a compatible tag is found (`selection_strategy="latest_compatible"`).
- **FR-010**: When `target_version` is set but no compatible tag exists and `allow_latest_overall=True`, the resolver MUST fall back to the newest parseable tag (`selection_strategy="latest_overall"`).
- **FR-011**: When `target_version` is omitted, the resolver MUST return the newest parseable tag, reporting `framework_version` from its build file when readable (`selection_strategy="latest_with_known_compatibility"` or `"latest_overall"`).
- **FR-012**: The resolver MUST parse the declared framework version from a tag's build file, supporting: Spring Boot starter parent POM, `spring-boot.version` property, Gradle plugin version declaration, and `@angular/core` in `package.json` dependencies/devDependencies. Framework detection at HEAD MUST probe in this order: `pom.xml` first → `build.gradle` / `build.gradle.kts` second → `package.json` third; the first file found determines the framework type.
- **FR-013**: Every error scenario MUST produce a structured response dict in the following nested shape — no error MUST propagate as an uncaught exception:
  `{ "status": "error", "error": { "error_code": <str>, "message": <str>, "recoverable": <bool>, "actionable_hint": <str>, "details": <dict> } }`.
  The `error_code` field lives inside the `error` sub-dict; callers access it as `result["error"]["error_code"]`. The full set of valid `error_code` values and their trigger conditions is:

  | `error_code`             | Trigger condition |
  |--------------------------|-------------------|
  | `invalid_service_name`   | `service_name` is empty, null, or contains only whitespace |
  | `service_not_found`      | FindIt returns no match at any of the four matching levels |
  | `no_repo_url`            | The matched FindIt record contains no `codeRepoLink` |
  | `no_tags_found`          | The GitLab repository has no git tags at all |
  | `no_compatible_version`  | Tags exist and were scanned but none satisfy the compatibility rule and `allow_latest_overall=False` |
  | `compatibility_unknown`  | All scanned tags have build files that exist but declare no parseable framework version, and `allow_latest_overall=False` |
  | `http_timeout`           | A FindIt HTTP call times out after all retries are exhausted |
  | `http_request_failed`    | A FindIt HTTP call returns a non-success status or a non-timeout network error after all retries |
  | `git_ls_remote_failed`   | `git ls-remote` against the GitLab repository fails (network error, auth failure, or non-zero exit) after all retries |
  | `no_parseable_tags`      | The repository has one or more tags but none can be parsed as a semantic version (all skipped) |

- **FR-014**: FindIt HTTP calls and git operations MUST each support configurable retry logic with at least 2 retries and configurable backoff (default: 1s, 3s); on exhaustion, the response MUST use `error_code="http_timeout"` or `"http_request_failed"` as applicable.
- **FR-015**: All environment variables (`FINDIT_AUTH_TOKEN`, `GITLAB_API_KEY`, `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD`) MUST be loaded exclusively from the project's central config module; no module within the resolver MUST read environment variables directly.
- **FR-016**: All git operations (tag listing, build file fetching, framework detection) MUST be encapsulated in the GitLab client module; resolver logic MUST NOT contain direct subprocess git calls.
- **FR-017**: The resolver module is strictly read-only with respect to the graph database (Neo4j/Memgraph). It MUST NOT write, update, merge, or delete any nodes or relationships in the graph at any point during resolution.
- **FR-018**: The resolver MUST NOT default `allow_latest_overall` to `True` internally. When the MCP tool omits `target_version`, the MCP layer is responsible for explicitly passing `allow_latest_overall=True` to the resolver; the resolver treats an absent or `False` value as a hard constraint.
- **FR-019**: The handling of `v`-prefixed git tags (e.g., `v3.5.10`) — whether to strip the prefix before parsing or silently skip — MUST be decided and documented in `research.md` before implementation. The resolver MUST apply the decided behaviour consistently across all tag scanning operations.

### Key Entities

- **ResolverResult**: The structured dict returned by `resolve()` on success — contains `status` (`"ok"`), `service_name`, `selected_tag`, `selected_version`, `framework`, `framework_version`, `selection_strategy`, `target_version` (echo of the caller-supplied target, or null), `code_repo_link` (GitLab URL from the FindIt record, null in pinned mode), `compatibility` (whether the selected version satisfies the target constraint, null when no target was given or in pinned mode), and optionally `name_resolution` (absent in pinned mode and when name matched exactly).
- **ErrorResult**: The structured dict returned by `resolve()` on any failure — has the shape `{ "status": "error", "error": { "error_code", "message", "recoverable", "actionable_hint", "details" } }`. Callers MUST read error details via `result["error"]["error_code"]`, not `result["error_code"]`.
- **FindItServiceRecord**: A single entry from the FindIt registry — contains at minimum the service name and `codeRepoLink`.
- **FindItCache**: The module-level singleton holding the fetched service list and its expiry timestamp.
- **NameResolutionMetadata**: Metadata included in the result when name matching was non-exact — contains `method` (one of `"case_insensitive"`, `"alphanumeric_normalized"`, `"fuzzy"`), `matched_name` (canonical registry name). For fuzzy matches, additionally contains `similarity` (numeric score, e.g. `0.82`), `threshold_used` (the configured minimum threshold), and `alternatives` (list of other close candidate names from FindIt).
- **SelectionStrategy**: An enumerated value — one of `latest_compatible`, `latest_overall`, `latest_with_known_compatibility`, `pinned`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A pinned-mode call completes in under 5 milliseconds with no network I/O, regardless of FindIt or GitLab availability.
- **SC-002**: A full resolve call (FindIt + GitLab tag scan + build file fetch) completes within the configured timeout window, with results returned even when some tags fail to parse.
- **SC-003**: All failure modes (network error, service not found, no parseable tags, no compatible version) produce a structured error dict with all required fields — zero uncaught exceptions in any tested scenario.
- **SC-004**: Name matching resolves the correct service record for at least 95% of inputs that differ from the canonical registry name only by casing or separator characters.
- **SC-005**: The FindIt service list is fetched at most once per 30-day window across all calls in a process lifetime, verifiable by counting network calls in a multi-call test scenario.
- **SC-006**: The compatibility rule correctly identifies compatible and incompatible tags across a test matrix of at least 20 version pairs covering same-major/different-minor/patch combinations.

## Assumptions

- The FindIt registry is an internal HTTP service accessible within the network environment where the resolver runs; no public internet access is assumed or required.
- GitLab repositories are accessible via SCP-style git over SSH; callers are assumed to have appropriate SSH credentials configured in their environment.
- Library git tags are assumed to follow semantic versioning conventions parseable as `MAJOR.MINOR.PATCH` or `MAJOR.MINOR.PATCH.SUFFIX` (e.g., `3.5.10`, `3.5.10.A`). Whether `v`-prefixed tags (e.g., `v3.5.10`) are silently skipped or stripped of their prefix before parsing is a known open question — some Paysafe GitLab repos publish only `v`-prefixed tags, which would cause `no_parseable_tags` to be returned for those libraries if stripping is not implemented. This decision MUST be documented in `research.md` before implementation begins.
- The resolver is called by `mcp/tools/paysafe.py` exclusively; no other entry points are in scope.
- Framework auto-detection from build files (pom.xml → spring-boot, package.json → angular) is used only for informational reporting; it does not alter the compatibility rule.
- The caller is responsible for supplying a meaningful `framework` parameter when required; the resolver does not infer framework from `service_name`.
- Performance requirements assume the resolver runs in an async or worker context where blocking I/O (git subprocess calls) is acceptable.
- The resolver is a pure read-only consumer; it never writes to, updates, or deletes data in the graph database (Neo4j/Memgraph) or any other persistent store.

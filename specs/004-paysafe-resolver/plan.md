# Implementation Plan: Paysafe Internal Library Version Resolver

**Branch**: `004-paysafe-resolver` | **Date**: 2026-06-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-paysafe-resolver/spec.md`

---

## Summary

Implement `migration_oracle/paysafe/` — a read-only resolver that, given a Paysafe
internal service name and an optional target framework version, locates the library's
GitLab repository via the FindIt registry, scans git tags newest-first, and returns the
newest tag whose declared build-file framework version is compatible with the target.
A pinned-version bypass allows callers to short-circuit all network I/O when the answer
is already known. All errors are returned as structured dicts; no exception escapes the
public API.

---

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**:
- `httpx>=0.27` — FindIt HTTP client (already in project)
- `rapidfuzz>=3.0` — fuzzy service-name matching (already in project)
- `packaging>=24.0` — semantic version parsing and sort (**must be added to `pyproject.toml`**)
- `subprocess` (stdlib) — git operations (`ls-remote`, `archive`)

**Storage**: None — resolver is purely read-only; does not write to Neo4j/Memgraph or any store

**Testing**: `pytest>=8.0`, `pytest-mock>=3.14`, `respx>=0.21` (all in dev-dependencies)

**Target Platform**: Linux server (same as rest of `migration_oracle`)

**Project Type**: Internal library module, called by `mcp/tools/paysafe.py`

**Performance Goals**: Pinned-mode calls < 5ms. Full-resolution calls complete within
configured timeout (default 30s per git op, 10s per HTTP call). Default tag scan limit: 100.

**Constraints**: No writes to graph DB. No env var reads outside `config.py`. No git calls
outside `gitlab.py`. `allow_latest_overall` has no resolver-side default.

**Config gaps to resolve during implementation**:
1. Add `GITLAB_API_KEY: str = _optional("GITLAB_API_KEY", "")` to `migration_oracle/config.py`
2. Add `"packaging>=24.0"` to `[project] dependencies` in `pyproject.toml`

---

## Constitution Check

The project constitution file is a blank template with no filled-in principles. No
governance constraints are in force beyond those stated in the spec and research files.

**Gate status**: PASS — no violations.

---

## Project Structure

### Documentation (this feature)

```text
specs/004-paysafe-resolver/
├── plan.md              ← this file
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── 004-paysafe-resolver.md
└── checklists/
    └── requirements.md
```

### Source Code

```text
migration_oracle/
├── config.py                    ← add GITLAB_API_KEY here
└── paysafe/
    ├── __init__.py              ← exports: resolve()
    ├── resolver.py              ← seven-step orchestration + pinned short-circuit
    ├── findit.py                ← HTTP client, 30-day cache singleton, 4-level matching
    └── gitlab.py                ← ls-remote, archive, build-file parse, framework detect

tests/
└── paysafe/
    ├── __init__.py
    ├── test_resolver.py         ← integration-style: mocked HTTP + git
    ├── test_findit.py           ← unit: cache TTL, all matching levels, error shapes
    └── test_gitlab.py           ← unit: tag sort, compat rule, build-file parsing
```

---

## Phase 0 — Research (COMPLETE)

All technology choices resolved. See [research.md](research.md).

| Decision | Choice | Key reason |
|----------|--------|------------|
| Git client | `subprocess` (stdlib) | Zero deps; `ls-remote` + `archive` are one-shot ops |
| Fuzzy matching | `rapidfuzz` (already in project) | Already declared; 10–40× faster than thefuzz |
| Semver parsing | `packaging.version.Version` | PEP 440 compatible; handles `3.5.10.A` and v-prefixed tags |
| HTTP client | `httpx` (already in project) | Project standard; matches 001-foundations |
| v-prefix tags | Strip `v`/`V` before parsing | Many Paysafe repos use v-prefixed tags; silent skip would break them |

---

## Phase 1 — Design & Contracts (COMPLETE)

Artifacts generated:

- [data-model.md](data-model.md) — `ResolverResult`, `NameResolution`, `CompatibilityInfo`, `ErrorResponse`
- [contracts/004-paysafe-resolver.md](contracts/004-paysafe-resolver.md) — public API boundary, module responsibilities
- [quickstart.md](quickstart.md) — test invocations, env vars, smoke tests

---

## Phase 2 — Implementation

> Tasks file generated separately by `/speckit-tasks`.

### Step 1 — Config & dependency updates

**Files**: `migration_oracle/config.py`, `pyproject.toml`

- Add `GITLAB_API_KEY: str = _optional("GITLAB_API_KEY", "")` to `config.py`
- Add `FINDIT_BASE_URL: str = _optional("FINDIT_BASE_URL", "https://findit-api.icd.paysafe.cloud")` to `config.py` (already partially present — verify the default URL is `findit-api.icd.paysafe.cloud`, not `findit.paysafe.com`)
- Add `"packaging>=24.0"` to `[project] dependencies` in `pyproject.toml`
- Run `uv sync` to update the lock file

---

### Step 2 — `migration_oracle/paysafe/__init__.py`

```python
from migration_oracle.paysafe.resolver import resolve

__all__ = ["resolve"]
```

No logic. Single export.

---

### Step 3A — `migration_oracle/paysafe/findit.py` [P: parallel with 3B]

**Responsibility**: FindIt HTTP client, 30-day cache singleton, four-level name matching.

**Module-level cache** (singleton — never re-instantiated per call):

```python
_cache: _CacheEntry | None = None  # module-level, initialized lazily
```

**Key functions**:

```python
def lookup(service_name: str) -> dict:
    """Four-level match; returns FindIt service record or raises _FindItError."""

def _fetch_services() -> list[dict]:
    """HTTP GET to FINDIT_BASE_URL/api/services with auth header and retry."""

def _match(name: str, services: list[dict]) -> tuple[dict, str] | None:
    """Returns (record, method) or None. method: exact|case_insensitive|alphanumeric_normalized|fuzzy."""
```

**Four-level matching cascade**:

1. Exact string match
2. Case-insensitive compare (`name.lower() == svc_name.lower()`)
3. Alphanumeric normalization: `re.sub(r'[^a-z0-9]', '', name.lower())`
4. Fuzzy: `rapidfuzz.fuzz.ratio(norm_input, norm_candidate) / 100.0 >= threshold`

Stop at first successful level. On non-exact match, populate `name_resolution` in the
return value.

**Retry logic**: 2 retries with delays of 1s, 3s. On timeout → `http_timeout`. On
non-2xx / network error → `http_request_failed`.

**Cache TTL**: 30 days. No invalidation path. Checked at start of each `lookup()` call.

---

### Step 3B — `migration_oracle/paysafe/gitlab.py` [P: parallel with 3A]

**Responsibility**: All git I/O — tag listing, build-file fetch, framework version parsing,
framework detection at HEAD.

**Key functions**:

```python
def list_tags(repo_url: str) -> list[str]:
    """Run git ls-remote --tags; return tags sorted descending by semver.
    Strips v-prefix before parsing. Skips unparseable tags silently.
    Raises _GitError on ls-remote failure."""

def fetch_framework_version(repo_url: str, tag: str) -> str | None:
    """Run git archive for the tag; extract and parse the build file.
    Returns framework version string or None if unreadable/absent."""

def detect_framework_at_head(repo_url: str) -> str | None:
    """Probe HEAD for build files in order: pom.xml → build.gradle/build.gradle.kts → package.json.
    Returns 'spring-boot', 'angular', or None."""
```

**Tag sort**: Use `packaging.version.Version` after stripping leading `v`/`V` and trailing
alphabetic suffix (e.g., `3.5.10.A` — `packaging` handles this as a local segment).

**Framework detection probe order at HEAD**: `pom.xml` → `build.gradle` / `build.gradle.kts` → `package.json`

**Build-file parsing**:

- Spring Boot: parse `spring-boot-starter-parent` version from POM parent, OR
  `spring-boot.version` property, OR Gradle plugin `id("org.springframework.boot") version "..."`
- Angular: parse `@angular/core` version from `package.json` `dependencies` or `devDependencies`

**Retry logic**: 2 retries, delays 1s, 3s. On `ls-remote` non-zero exit, network error, or auth failure after all retries → `git_ls_remote_failed`. (Note: these are git operation errors, not HTTP errors — `http_timeout` / `http_request_failed` apply only to FindIt HTTP calls in `findit.py`.)

**URL conversion**: HTTPS GitLab URLs converted to SCP-style (`git@gitlab.paysafe.com:...`) for
SSH-based git operations.

---

### Step 4 — `migration_oracle/paysafe/resolver.py`

**Responsibility**: Orchestrate the seven-step flow. No HTTP or git code here.

**Seven-step flow**:

1. If `pinned_version` → return pinned `ResolverResult` immediately (no network I/O)
2. Validate `service_name` (blank → `invalid_service_name` error)
3. `findit.lookup(service_name)` → service record or error
4. Extract `codeRepoLink` (absent → `no_repo_url` error)
5. `gitlab.list_tags(repo_url)` → sorted tags or error
6. Scan tags (newest-first, up to `max_tags`):
   - `gitlab.fetch_framework_version(repo_url, tag)` for each
   - Apply compatibility rule
   - Accumulate compatible, unknown, overall candidates
7. Select strategy and build `ResolverResult`:
   - `latest_compatible` if `target_version` is set and a compatible tag was found
   - `latest_with_known_compatibility` if `target_version` is `None` and the newest parseable tag's build file is readable (framework version known)
   - `latest_overall` if (a) `target_version` is `None` and newest tag's build file is unreadable, OR (b) `target_version` is set, no compatible found, and `allow_latest_overall=True`
   - `compatibility_unknown` error if all scanned tags have build files declaring no parseable framework version and `allow_latest_overall=False`
   - `no_compatible_version` error if incompatible tags exist and `allow_latest_overall=False`

All errors returned as `ErrorResponse` dicts — no exceptions escape.

---

### Step 5A — `tests/paysafe/test_findit.py` [P: parallel with 5B, 5C after Step 3A]

Cover:

- Cache TTL: populated cache returns cached data; stale cache (>30 days) re-fetches
- All four matching levels with correct `name_resolution.method`
- Fuzzy match includes `similarity`, `threshold_used`, `alternatives`
- `service_not_found` error shape when no level matches
- `http_timeout` and `http_request_failed` error shapes
- Retry behaviour (2 retries before error)

---

### Step 5B — `tests/paysafe/test_gitlab.py` [P: parallel with 5A, 5C after Step 3B]

Cover:

- Tag parsing: v-prefix stripping, alphabetic suffix handling (`3.5.10.A`), descending sort
- Silently skips unparseable tags; returns only valid ones
- Compatibility rule: same-major-gte passes, different-major fails, lower-minor fails
- `compatibility_unknown` (build file exists, no parseable version)
- `build_file_missing` (tag has no build file) → tag silently skipped
- Spring Boot POM parent parse, property parse, Gradle plugin parse
- Angular `@angular/core` parse from dependencies and devDependencies
- Framework detection probe order at HEAD

---

### Step 5C — `tests/paysafe/test_resolver.py` [P: parallel with 5A, 5B after Steps 3A+3B+4]

Cover:

- Pinned mode: correct shape, no network calls, `name_resolution` absent
- `latest_compatible` strategy end-to-end
- `latest_overall` fallback when no compatible tag
- `latest_with_known_compatibility` when `target_version` omitted
- `invalid_service_name` on blank input
- `no_repo_url` when FindIt record missing `codeRepoLink`
- `no_tags_found` when repo has no tags
- `no_parseable_tags` when all tags fail version parsing
- `no_compatible_version` error with `allow_latest_overall=False`
- `compatibility_unknown` error
- All error responses use the nested `{ "status": "error", "error": { ... } }` shape
- `allow_latest_overall` is not defaulted by the resolver

---

## Parallelism Map

```
Step 1 (config/deps)
    └── Step 2 (__init__.py)
            ├── Step 3A (findit.py)    [P] ─────┐
            └── Step 3B (gitlab.py)   [P] ─────┤
                                                 └── Step 4 (resolver.py)
                                                         ├── Step 5A (test_findit.py)  [P]
                                                         ├── Step 5B (test_gitlab.py)  [P]
                                                         └── Step 5C (test_resolver.py)[P]
```

Steps 3A and 3B can be implemented concurrently by different developers.
Steps 5A, 5B, 5C can be written concurrently once their implementation files are done.

---

## Complexity Tracking

No constitution violations.

# Research: 004-paysafe-resolver

**Date**: 2026-06-06 | **Branch**: `004-paysafe-resolver`

---

## RES-001: Git Client Library

**Decision**: `subprocess` (standard library) via a thin wrapper in `gitlab.py`

**Rationale**: The two required git operations — `git ls-remote` and `git archive` — are both
read-only, one-shot shell invocations. They need timeout control and retry logic, but not
a full object-oriented git model. `subprocess.run` with `check=False`, `timeout=`, and
`capture_output=True` covers both cleanly with zero new dependencies and no version-pinning risk.

**Alternatives considered**:

- **GitPython** — large dependency, adds ~6 MB to the wheel; its `Repo` abstraction requires
  cloning a local working copy, which is wasteful for a remote tag scan. Overkill.
- **Dulwich** — pure-Python git, avoids the `git` binary, but its `ls-remote` and archive
  support is less battle-tested and adds another dependency for no clear gain.

**Implementation note**: All subprocess calls MUST be wrapped in `gitlab.py`; none may appear
in `resolver.py`. Timeout (default 15s) and retry count (default 2) are read from
`migration_oracle/config.py`.

---

## RES-002: Fuzzy Matching Library

**Decision**: `rapidfuzz` (already in `pyproject.toml` as `rapidfuzz>=3.0`)

**Rationale**: `rapidfuzz` is already declared as a project dependency — adding a second
library for the same purpose would be unnecessary. It exposes `fuzz.ratio` and
`process.extractOne`, which satisfy the similarity-score and best-match needs directly.
It is 10–40× faster than `thefuzz` for large service lists.

**Alternatives considered**:

- **thefuzz (fuzzywuzzy)** — slower, requires optional `python-Levenshtein` for acceptable
  perf, and is not in the project's dependency set.

**Usage**: `rapidfuzz.fuzz.ratio(a, b) / 100.0` yields a 0–1 similarity score; compare
against `FINDIT_SERVICE_NAME_FUZZY_THRESHOLD` (default 0.68, from `config.py`).

---

## RES-003: Semantic Version Parsing and Sorting

**Decision**: `packaging.version.Version` from the `packaging` library

**Rationale**: `packaging` is the canonical Python packaging version parser; it handles
PEP 440 versions and is already a transitive dependency of `hatchling` (the build backend).
It must be added as an explicit dependency in `pyproject.toml` to avoid relying on
transitive availability.

**Alternatives considered**:

- **`semver` library** — strict SemVer only; rejects common tag formats like `3.5.10.A`
  that appear in Paysafe repos.
- **`distutils.version`** — deprecated since Python 3.10, removed in 3.12.
- **Manual regex sort** — fragile, reinvents what `packaging` already handles correctly.

**v-prefix handling decision**: Tags with a `v` prefix (e.g., `v3.5.10`) MUST have the
prefix stripped before parsing. Rationale: many Paysafe GitLab repos use `v`-prefixed tags;
silently skipping them would cause `no_parseable_tags` errors for entire libraries. The
resolver strips a leading `v` (case-insensitive) before attempting `Version()` parsing.
Tags that still fail after stripping are silently skipped. **This decision resolves FR-019.**

**Suffix handling**: The alphabetic suffix in tags like `3.5.10.A` is treated as a
PEP 440 local version segment by `packaging.version.Version` and sorts correctly.

---

## RES-004: HTTP Client

**Decision**: `httpx` (already in `pyproject.toml` as `httpx>=0.27`)

**Rationale**: `httpx` is the project's established HTTP client (used by 001-foundations).
It supports sync and async, response streaming, and timeout configuration. FindIt calls
are sync (the resolver is not async-native), so `httpx.Client` with a `Timeout` object
is used.

**Alternatives considered**:

- **`requests`** — not in the project's dependency set; would add a duplicate HTTP client.

---

## RES-005: `GITLAB_API_KEY` Config Gap

**Finding**: `GITLAB_API_KEY` is referenced in the spec but absent from
`migration_oracle/config.py`. It must be added as an optional env var (default empty
string, same pattern as `FINDIT_AUTH_TOKEN`). When empty, git operations rely on
ambient SSH credentials; when set, it is passed as a credential helper or HTTP header
for HTTPS-based git operations.

**Action**: Add `GITLAB_API_KEY: str = _optional("GITLAB_API_KEY", "")` to `config.py`
during implementation Phase 2.

---

## RES-006: `packaging` Dependency Declaration

**Finding**: `packaging` is used transitively (via hatchling) but not declared as a direct
dependency. It must be added to `[project] dependencies` in `pyproject.toml` to avoid
breakage if the build backend changes.

**Action**: Add `"packaging>=24.0"` to `pyproject.toml` during implementation Phase 2.

# Feature Specification: GitHub Change Enrichment (Spring Boot + Angular)

**Feature Branch**: `021-github-change-enrichment`

**Created**: 2026-11-04

**Status**: Draft

**Scope**: Lightweight spec (no full SpecKit flow). Extract-stage change only.

## Problem

Release-note rows from GitHub-hosted frameworks carry only a one-line title. The detail the
filter/entity LLM steps need to judge migration impact lives one click away on GitHub.

**Spring Boot** — rows reference an issue/PR:

```
| behavioral | inferred | https://github.com/spring-projects/spring-boot/releases/tag/v3.1.10 | When graceful shutdown of Tomcat is aborted it may report that it completed successfully [#39942](https://github.com/spring-projects/spring-boot/issues/39942) |
```

The issue has the body (root cause, affected behaviour), labels (`type: bug`,
`type: dependency-upgrade`, …) and close reason.

**Angular** — rows reference a commit (and sometimes a PR); the package/scope is lost:

```
| mandatory_migration | confirmed | https://raw.githubusercontent.com/angular/angular/main/CHANGELOG.md |   [99715104a1](https://github.com/angular/angular/commit/99715104…)   fix    correctly perform lazy routes migration for components with additional decorators ([#58796](https://github.com/angular/angular/pull/58796)) |
```

The commit message (`GET /repos/angular/angular/commits/{sha}`) contains the conventional-commit
header with scope (`fix(core): …`), an explanatory body, footers (`BREAKING CHANGE:`,
`DEPRECATED:`, `Fixes #58793`, `PR Close #58796`) and the changed file list. Commit links are
always present; PR links are not (21.0.0→22.0.0: 372 commits, 13 PR links).

**Volume** (unique refs in existing `runs/raw`):

| Framework | Patch hop | Minor/major range |
|---|---|---|
| Spring Boot (issues/PRs) | 5–50 | 316–711 |
| Angular (commits) | — | 262–372 per major |

## Goal

Enrich rows with data from the GitHub REST API through one reusable helper, following the
existing WildFly Jira enrichment pattern (`wildfly.py::enrich_with_jira` / `_load_jira_cache`).
Spring Boot is enriched from **issues**, Angular from **commits** (+ the linked issue).

## Non-Goals

- GraphQL batching (follow-up if latency/rate limit becomes a problem).
- Hibernate / Infinispan enrichment (the helper must be reusable; wiring is out of scope).
- Wiki-derived Spring Boot rows and Angular blog insights.
- Changing filter/entity LLM prompts.

---

## Part A — Shared core (`github_enrichment.py` + `base.py`)

### FR-A1 Fetch helpers on `BaseExtractor`

- `fetch_github_issues(repo, numbers) -> dict[int, GitHubIssue]` —
  `GET /repos/{repo}/issues/{n}` (covers issues and PRs).
- `fetch_github_commits(repo, shas) -> dict[str, GitHubCommit]` —
  `GET /repos/{repo}/commits/{sha}`.
- Both use the existing client/headers (`Authorization: Bearer GITHUB_TOKEN`) and the in-memory
  `fetch` cache; concurrency bounded by `GITHUB_ENRICH_MAX_CONCURRENT` (default `8`).
- Per-item failures (404, 410, 422, timeout, bad JSON) are logged at DEBUG and the item is
  omitted; they never fail the hop.
- On 403/429 with `X-RateLimit-Remaining: 0`: stop issuing GitHub enrichment requests for the
  rest of the run, log one WARNING, return what was fetched.

Data shapes (TypedDict):

- `GitHubIssue`: `number`, `title`, `body` (cleaned), `labels: list[str]`, `is_pull_request`,
  `state_reason`, `html_url`.
- `GitHubCommit`: `sha`, `html_url`, `header` (first line), `type`, `scope`, `body` (cleaned,
  footers removed), `breaking: str` (text of `BREAKING CHANGE:` footer or `""`),
  `deprecated: str` (text of `DEPRECATED:` footer or `""`), `fixes: list[int]`
  (`Fixes|Closes|Resolves #N`), `pr: int | None` (`PR Close #N` or `(#N)` in header),
  `files: list[str]`.

### FR-A2 Body cleaning (shared)

- Strip HTML comments (`<!-- … -->`; the Spring Boot issue template is entirely a comment),
  fenced code blocks longer than 10 lines (→ `[code omitted]`), stack traces.
- `html_to_text`, collapse whitespace, truncate to `GITHUB_ENRICH_BODY_MAX_CHARS`
  (default `1500`) with `…`. Empty → `"N/A"`.

### FR-A3 Gating

- Runs only when `GITHUB_TOKEN` is set (unauthenticated limit is 60 req/h). Without a token:
  one INFO line, rows unchanged.
- Per-framework switches: `SPRING_BOOT_GITHUB_ENRICHMENT`, `ANGULAR_GITHUB_ENRICHMENT`
  (`true`/`false`, default `true`).
- Any unexpected exception in enrichment is caught in `extract()`, logged as WARNING, and the
  unenriched changes are returned.

### FR-A4 Common output contract

For every enriched row:

- `source_url` = GitHub `html_url` of the issue/commit; the previous source moves to
  `metadata["release_url"]`.
- `statement` keeps the `Title: … / <Detail>: … / Release: <original line>` shape used by WildFly.
- Rows with no reference, or whose reference could not be fetched, are returned unchanged.
- Type refinement never downgrades a row already classified by section heading
  (breaking, deprecation, mandatory_migration) — except where explicitly stated below.

---

## Part B — Spring Boot (issues)

### FR-B1 Reference collection

From each release-body row: `spring-projects/spring-boot/(issues|pull)/(\d+)` and bare `#(\d+)`.
If several, use the first one fetched successfully.

### FR-B2 Backport resolution

If the cleaned body is < 200 chars and matches `(?i)(back|forward)[- ]?port of (issue )?#(\d+)`,
fetch the referenced issue (one level, no recursion) and use its body; keep the original
number/labels/`html_url`; set `metadata["github_backport_of"]`.

### FR-B3 Row output

- `statement` = `Title: <issue title>\nIssue: <cleaned body>\nRelease: <original line>`
- `metadata`: `github_issue`, `github_labels`, `github_issue_type` (`type: …` label value),
  `github_state_reason`; `github_not_planned = True` when `state_reason == "not_planned"`
  (row is kept).
- Type: `type: dependency-upgrade` on a default `behavioral / inferred` row →
  `dependency_upgrade / inferred`. Other labels leave the type unchanged.

---

## Part C — Angular (commits)

### FR-C1 Reference collection

From each row (release body and CHANGELOG section): `angular/angular/commit/([0-9a-f]{7,40})`.
Rows without a commit link but with `angular/angular/(pull|issues)/(\d+)` fall back to the
issue path of FR-A1 (same output as FR-B3, minus backport handling).

### FR-C2 Commit message parsing

- Header regex: `^(?P<type>\w+)(\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<subject>.+?)(\s*\(#(?P<pr>\d+)\))?$`.
- Footers (case-insensitive, may span multiple lines until the next footer or end):
  `BREAKING CHANGE:` / `BREAKING CHANGES:`, `DEPRECATED:`, `Fixes|Closes|Resolves #N`
  (several allowed), `PR Close #N`.
- `body` = message without the header and footers, cleaned per FR-A2.

### FR-C3 Linked issue

If `fixes` is non-empty, fetch the **first** fixed issue (FR-A1) and include its title and the
first 500 chars of its cleaned body. This is the user-facing symptom, which commit bodies often
omit. One issue per commit, no recursion.

### FR-C4 Row output

- `statement` =
  ```
  Title: <commit header>
  Commit: <cleaned body or N/A>
  Breaking: <breaking footer>        (only when present)
  Deprecated: <deprecated footer>    (only when present)
  Issue: #<n> <issue title> — <issue body excerpt>   (only when FR-C3 fetched)
  Release: <original line>
  ```
- `metadata`: `github_commit` (full sha), `angular_package` (= scope, e.g. `core`, `router`,
  `forms`, `compiler-cli`, `migrations`), `angular_commit_type` (`fix`, `feat`, `perf`, …),
  `github_pr`, `github_fixes`, `has_schematic = True` when any changed file is under
  `packages/*/schematics/` (an automated `ng update` migration exists).
- Type refinement (strong signals from the source; may override the section-derived type):
  | Signal | type / confidence |
  |---|---|
  | `breaking` footer or `!` in header | `breaking / confirmed` |
  | `deprecated` footer | `deprecation / confirmed` |
  | otherwise | unchanged |

---

## Acceptance Criteria

**Shared**

1. **AC-1** With `GITHUB_TOKEN` unset, no request is made to `/issues/` or `/commits/`, and
   Spring Boot and Angular output equals current output byte-for-byte.
2. **AC-2** A 404 on one reference leaves that row unchanged and others enriched.
3. **AC-3** A 403 with `X-RateLimit-Remaining: 0` stops further enrichment requests; the hop
   still returns all rows.
4. **AC-4** Issue body consisting only of an HTML-comment template → `Issue: N/A`.

**Spring Boot**

5. **AC-5** Recorded release body with `#39942` + recorded issue JSON → `source_url` is the
   issue URL, statement starts `Title: When graceful shutdown of Tomcat is aborted…`, the
   `Issue:` section contains "race condition", `metadata["github_labels"] == ["type: bug"]`.
6. **AC-6** Backport issue with body `Backport of #39900` → statement uses #39900's body and
   `metadata["github_backport_of"] == 39900`.
7. **AC-7** `type: dependency-upgrade` on a default row → `dependency_upgrade`; a row under a
   "Breaking" section stays `breaking`.

**Angular**

8. **AC-8** Recorded commit `99715104a1…` → statement contains `Title: fix(core): correctly
   perform lazy routes migration…`, a `Commit:` section containing "would crash", an `Issue: #58793`
   line; `metadata["angular_package"] == "core"`, `metadata["github_pr"] == 58796`,
   `metadata["has_schematic"] is True`; `PR Close` text does not appear in the statement.
9. **AC-9** Recorded commit with a `BREAKING CHANGE:` footer on a row classified `behavioral`
   → `breaking / confirmed` and a `Breaking:` line with the footer text.
10. **AC-10** Row with a PR link but no commit link → enriched through the issue path.

**Live / regression**

11. **AC-11** Live: Spring Boot `3.1.9 → 3.1.10` and Angular `19.0.0 → 19.0.1` each enrich
    ≥ 90% of rows that carry a reference; enrichment requests ≤ 2 × unique references.
12. **AC-12** Existing `tests/extractors/test_spring_boot*.py` and `test_angular.py` pass
    unchanged (no token in test env).

## Implementation Notes

- Files: new `migration_oracle/pipeline/extractors/github_enrichment.py` (TypedDicts, regexes,
  cleaning, commit-message parser, row builders — mirrors `wildfly_jira.py`);
  `base.py` (fetch helpers); `spring_boot.py`, `angular.py` (call enrichment after parsing /
  changelog dedup); `migration_oracle/config.py`.
- Tests: `tests/extractors/test_github_enrichment.py` (parser, cleaning, rate-limit stop) and
  per-framework wiring tests with recorded JSON fixtures, mocked `fetch` as in
  `tests/extractors/test_wildfly_jira.py`.
- Request budget per full range with token: Spring Boot ≤ ~1.4k, Angular ≤ ~750
  (commits + one linked issue each) — well within 5000/h.
- Docs: Spring Boot and Angular paragraphs in
  `docs/export-extract-populate-framework-pipeline.md`; `CHANGELOG.md` entry.

## Estimate

~1.5 days total:

| Work | Effort |
|---|---|
| Shared helpers, cleaning, rate-limit handling | 2 h |
| Spring Boot wiring, backports, type mapping | 2 h |
| Angular commit parser, linked issue, wiring | 3 h |
| Tests (fixtures + unit) | 3 h |
| Docs + live check | 1 h |

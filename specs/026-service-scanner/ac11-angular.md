# AC-11 (Angular half) — real-service check

Spec: `specs/026-service-scanner/spec5.md` (026.5, FR-6 templates).
Run: 2026-11-06, macOS 25.6.0 (darwin arm64), CPython 3.12, `migration-scan` from this tree.

## Status

**Partially met — the timing, size and correctness criteria pass; the ≥ 1 000-source-file
requirement does not.** No Angular service of that size is reachable from this workspace: the
filesystem has no Angular application outside the test fixtures, and the GitLab MCP server
(where such a service would live) needed authentication, which was declined. The check below
therefore runs on a real, publicly available Angular application plus a synthetic tree at the
required scale. Re-running AC-11 on the size-qualified service is the one open item; the
commands are at the bottom.

## Service under test

| Property | Value |
|---|---|
| Repository | `gothinkster/angular-realworld-example-app` (shallow clone) |
| Framework | Angular **21.2.12** (from `package-lock`/`package.json`), detected as `angular 21.2.12` |
| Files scanned | 66 (`files_scanned`), 0 skipped, 0 diagnostics |
| Sources | 48 `.ts` (8 with an inline template, 6 of them `*.spec.ts`) + 11 `*.html` templates |

This is a genuine, idiomatic Angular app: standalone components, signals, `@if` / `@for` /
`@defer`, `*ngIf` / `*ngFor` from `@rx-angular/template`, custom pipes, `provideZonelessChangeDetection`,
an inline-template component, and Vitest specs.

## Timings and size

| Run | Wall clock | `duration_ms` | Profile size |
|---|---|---|---|
| cold (1st, includes grammar import) | **0.27 s** | 110 | 122 190 B (119 KB) |
| warm (#2) | 0.11 s | 110 | 122 190 B |
| warm (#3) | 0.10 s | 105 | 122 190 B |

- **< 30 s cold: passed** with a factor of ~100 to spare (0.27 s).
- **< 2 MB profile: passed** (119 KB, i.e. ~1/17 of the budget). The profile is bounded by the
  API surface, not by the codebase: 80 symbols, 23 members, 63 config, 12 template keys.
- Warm timings are informational here; the incremental cache that makes warm re-scans
  cheap is spec9, which owns the `< 3 s warm` criterion.

### Scale check at the required size

To exercise the *size* criterion where a real service was unavailable, a synthetic Angular tree
of **1 801 files** (1 200 components with inline templates, 600 standalone `.html` templates,
40 feature folders) was scanned:

| Files | Wall clock | `duration_ms` | Profile |
|---|---|---|---|
| 1 801 (1 200 `.ts` + 600 `.html` + manifest) | **1.13 s** | 600 | 48 KB |

Extrapolating the real app's per-file cost (~1.5 ms/file) to 1 000–5 000 source files stays far
inside 30 s, and the profile stays in the tens of KB because facts are keyed by API surface, not
by file. This is evidence for the budget, not a substitute for the real-service run.

## Spot check — 10 random import sites

Selection: 10 files sampled at random (seed 42) from the files that have at least one symbol
location; for each, the first stored location and the source line it points at.

| # | File | Line | Recorded key | Source line |
|---|---|---|---|---|
| 1 | `src/main.ts` | 1 | `npm:@angular/platform-browser#bootstrapApplication` | `import { bootstrapApplication } from '@angular/platform-browser';` |
| 2 | `src/app/core/auth/services/jwt.service.ts` | 1 | `npm:@angular/core#Injectable` | `import { Injectable } from '@angular/core';` |
| 3 | `src/app/app.component.ts` | 1 | `npm:@angular/core#ChangeDetectionStrategy` | `import { ChangeDetectionStrategy, Component } from '@angular/core';` |
| 4 | `src/app/features/article/components/article-meta.component.ts` | 1 | `npm:@angular/core#Component` | `import { ChangeDetectionStrategy, Component, Input } from '@angular/core';` |
| 5 | `src/app/features/article/components/article-comment.component.ts` | 1 | `npm:@angular/core#EventEmitter` | `import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output, inject } from '@angular/core';` |
| 6 | `src/app/core/layout/header.component.ts` | 1 | `npm:@angular/core#inject` | `import { ChangeDetectionStrategy, Component, inject } from '@angular/core';` |
| 7 | `src/app/core/auth/services/user.service.spec.ts` | 3 | `npm:vitest#afterEach` | `import { describe, it, expect, beforeEach, afterEach, beforeAll, vi } from 'vitest';` |
| 8 | `src/app/core/auth/services/jwt.service.spec.ts` | 3 | `npm:vitest#beforeAll` | `import { …, beforeAll, vi } from 'vitest';` |
| 9 | `src/app/features/profile/services/profile.service.spec.ts` | 3 | `npm:vitest#afterEach` | `import { …, afterEach, … } from 'vitest';` |
| 10 | `src/app/core/auth/if-authenticated.directive.ts` | 1 | `npm:@angular/core#DestroyRef` | `import { DestroyRef, Directive, inject, Input, OnInit, signal, TemplateRef, ViewContainerRef } from '@angular/core';` |

**Result: 10 / 10 external imports recorded with the right key and the right line.** Every
location is an import site (spec1 FR-9), so the line is the `import` statement, not a later use —
which is what a matcher searches.

## Template counts against `grep`

The FR-6 facts were checked against `grep` on the same tree, `.html` and inline `.ts` templates
counted separately because they are stored with different `file` values:

| Token | Profile `count` | `grep` (`.html`) | `grep` (`.ts` inline) | Sum | Match |
|---|---|---|---|---|---|
| `@if` | 25 | 18 | 7 | 25 | yes |
| `@for` | 8 | 5 | 3 | 8 | yes |
| `pipe:date` | 3 | 1 | 2 | 3 | yes |
| `@else` | 3 | 3 | 0 | 3 | yes |
| `@empty` | 1 | 0 | 1 | 1 | yes |
| `as` | 4 | 4 | 0 | 4 | yes |

Stored lines were compared with `grep -n` for `@if`: e.g. `auth.component.html:7, 11, 19`,
`header.component.html:5, 7, 24, 44, 56, 85`, `article-comment.component.ts:13, 31`,
`article-list.component.ts:25, 29, 34` — all agree, inline templates included. Prose was not
counted: `Sign in` (header line 14) and `<!-- Show this for logged in users -->` (line 23) are not
`in` tokens, and `{{ a || b }}` in the header produced no `pipe:` key.

## 025 Angular entity keys used by the service

Method: every `angular-*-canonical.jsonl` in `runs/canonical/` was read, Angular keys extracted
(`npm:@angular…`, `syntax:angular-template…`) — **252 distinct keys** — and each was searched for
in the service's `src/` with a token-aware `grep` (a member key needs `Sym` followed by `.member`
on the same expression). Keys the service really uses: **32**. In the profile: **25**.

| Missing 025 key | `grep` hits | Why it is not a profile key |
|---|---|---|
| `npm:@angular/platform-browser#ApplicationConfig` | 2 | **Wrong package in 025.** The app imports it from `@angular/core` (`app.config.ts:1`), and the profile records `npm:@angular/core#ApplicationConfig` at that line. The scanner is right; the rule key carries 025's attribution. |
| `npm:@angular/platform-server#testing` | 29 | Not a code fact: `platform-server/testing` appears only as a dependency name in rules/lockfiles, never as an import in `src/`. |
| `syntax:angular-template#**` | 1 | The one hit is a JSDoc opener (`/**`) in a `.ts` file, not a template operator. |
| `syntax:angular-template#in` | 29 | Every hit is TypeScript — type annotations and prose in JSDoc (`in markdown`). There is no `in` inside any binding: `grep` for `{{ … in … }}` and `[x]="… in …"` returns nothing. |
| `syntax:angular-template#void` | 43 | Every hit is a TS return type (`ngOnInit(): void`), not a template expression. |
| `syntax:angular-template#async` | 115 (bare word) | The `async` pipe **is** in the profile, as `syntax:angular-template#pipe:async` (4 sites, matching `grep -rn "| async"` = 4). `async` alone is not in `ANGULAR_SYNTAX_TOKENS`, so 025 only produced this key because an LLM declared `kind: syntax`; 114 of the 115 bare-word hits are TS `async` functions / identifiers (112 alone in `.ts`); the rest are the 4 real pipe uses, which the profile records as `pipe:async`. |
| `syntax:angular-template#track` | 8 | `track` is `@for` microsyntax, not a token in `ANGULAR_SYNTAX_TOKENS` (025 got it the same way, from an LLM `kind: syntax`). The block itself is recorded: `@for` = 8, exactly the 8 `track` sites. |

**No unexplained miss.** Two of the seven are the 025 side attributing a package / key form the
scanner cannot produce (`ApplicationConfig` under the wrong package; a pipe emitted as a bare
token). That is a matcher input question for 028, not a scanner gap:

- `syntax:angular-template#async` vs `syntax:angular-template#pipe:async` — the scanner's `pipe:`
  prefix (spec5 FR-6) and 025's bare-token form will not compare equal. Either 025 should
  canonicalize a pipe name to `pipe:<name>`, or 027's rule signals should mark pipe rules with
  the `pipe:` prefix. **Recommended: fix on the 025/027 side** — the scanner's form is the one
  that can tell `async` the pipe from `async` the identifier.
- `npm:@angular/platform-browser#ApplicationConfig` — an ingestion package-attribution error worth
  a check in 025, since a rule keyed on it will never match a service that imports it correctly.

## Regression

```
pytest tests/scanner/            → 382 passed, 4 skipped
pytest tests/pipeline/test_shared_keys.py tests/pipeline/test_canonical_normalize.py
                                 → 28 passed   (the 025 tests that use migration_keys/)
```

No spec1–spec4 test was changed. Two of them assert `set(builtin.SOURCE_EXTRACTORS) == set(GRAMMARS)`
(exactly the TS grammars); the `html` extractor therefore ships as
`builtin.EXTRA_SOURCE_EXTRACTORS` and is installed into the same registry, so those assertions
still hold without editing an earlier spec's test.

`tests/pipeline/test_canonical_populate.py` aborts with a numpy segmentation fault
(`numpy/linalg/linalg.py:561 in inv`) in this environment **with and without** this change
(verified by stashing the work tree), so it is unrelated to 026.5.

## How to re-run on the size-qualified service

```bash
# 1. cold timing and size
time migration-scan /path/to/angular-service --force
jq '.templates[] | {key, count}' /path/to/angular-service/.migration/profile.json
du -h /path/to/angular-service/.migration/profile.json      # < 2 MB

# 2. template counts against grep (per token)
grep -rn "@if"  /path/to/angular-service/src --include=*.html | wc -l
grep -rn "@if"  /path/to/angular-service/src --include=*.ts   | wc -l
grep -rnE "\| *date" /path/to/angular-service/src --include=*.html | wc -l

# 3. 10 random import sites
jq -r '.symbols[] | .key as $k | .locations[] | "\(.file):\(.line) \($k)"' \
  /path/to/angular-service/.migration/profile.json | shuf -n 10

# 4. 025 keys the service really uses, against the profile
#    (re-run the token-aware comparison from the table above on .migration/profile.json)
```

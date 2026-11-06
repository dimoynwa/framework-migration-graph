# AC-11 (Angular half) — real-service check

Spec: `specs/026-service-scanner/spec5.md` (026.5, FR-6 templates).
Run: 2026-11-06, macOS 25.6.0 (darwin arm64), CPython 3.12, `migration-scan` from this tree.

## Status

**Met on a real Paysafe Angular service, with one size caveat.** Run 2 (below) uses
`paysafe-wac-web-login-fe`: timing, size, import-site correctness, template counts and the 025
key check all pass. The service has **702** TS / JS / HTML source files, below the spec's
≥ 1 000; that is the only criterion not literally met (a synthetic 1 801-file tree, run 1, covers
the scale side). The run also found and fixed a **native crash** (py-tree-sitter 0.26.0 segfault),
which the earlier, smaller public app had not triggered.

## Run 2 — `paysafe-wac-web-login-fe` (primary, 2026-11-06)

| Property | Value |
|---|---|
| Repository | `/Users/dimo.drangov/DevelopmentTools/paysafe-wac-web-login-fe`, commit `5308f9de`, clean work tree |
| Framework | `angular 20.3.27` (source `package-lock.json`) |
| Files scanned | 709 (615 `.ts`, 15 `.js`, 71 `.html`, manifests), 0 skipped |
| Profile written to | outside the repo (`--out`), so the service work tree stayed untouched |

### Native crash found and fixed

The first run exited **139 (segfault)**. The crash is inside py-tree-sitter **0.26.0** (`Node`
access during the TS extractor's shadowing check); 22 of 631 TS / JS files crashed it, mostly
large `*.spec.ts` files. 0.24.0 and 0.25.2 parse the same files cleanly, and the crash persists
even with the extractor's `.parent` walks removed, so it is in the binding, not in our tree
logic. Fix: `pyproject.toml` pins `tree-sitter>=0.25,<0.26` (lock now 0.25.2), and
`tests/scanner/test_ts_native_stability.py` guards it with a synthetic 813-line spec file that
reproduces the crash under 0.26.0 (run in a subprocess so a segfault fails the test instead of
killing pytest) plus a version assertion. No service code was copied into the tests.

### Timings and size

| Run | Wall clock | `duration_ms` | Profile |
|---|---|---|---|
| cold (`--force`, 1st) | **1.35 s** | 800 | **441 KB** (451 552 B) |
| warm (`--force`, 2nd / 3rd) | 1.06 s / 1.06 s | 800 | 441 KB |

- **< 30 s cold: passed** (1.35 s). **< 2 MB: passed** (441 KB; 781 KB even with
  `--max-locations 100000`). 0 diagnostics.
- Summary line: `scanned 709 files · angular 20.3.27 · 88 deps · 288 symbols · 71 members ·
  166 config · 13 template tokens · 0 diagnostics`.

### Import sites — 10 random, plus every single-line import

Sampled from the **source** (not from the profile), so a missing fact would show. The check
uses `--max-locations 100000`: with the default 20, a popular key (`Component`, `Observable`,
`TranslateService`) keeps only 20 locations by design (`count` stays exact, `truncated: true`).

- **10 random external import statements (seed 11): 10 / 10** recorded with the right key and
  line (`@angular/core`, `@angular/core/testing`, `@angular/common/http`,
  `@angular/platform-browser/animations`, `@angular/forms`, `@ngx-translate/core`, `rxjs`).
- **Full sweep of all 1 443 single-line external-looking imports: 1 443 / 1 443 correct.** 1 291
  are recorded as expected; the other 152 are correctly *not* facts: 151 are the service's own
  code through `baseUrl: "./src"` (`'app/app.const'`, `'app/request-money/…'` — spec3's `baseUrl`
  rule) and 1 is Node's `util` in `jest.ts`, a builtin the service does not declare.

### Template counts against `grep`

`count` is distinct `(file, line)` sites, so `grep -n` lines are the comparison.

| Token | Profile | `grep` | Match |
|---|---|---|---|
| `@if` | 137 | 137 (`.html`) | yes |
| `@for` | 14 | 14 | yes |
| `@else` | 4 | 4 | yes |
| `@switch` / `@case` | 1 / 5 | 1 / 5 | yes |
| `*ngFor` | 1 | 1 (inline template in `dropdown.component.spec.ts`) | yes |
| `pipe:translate` | 299 | 298 `.html` lines + 1 inline | yes |
| `pipe:async` | 8 | 8 lines (9 occurrences, two on one line) | yes |
| `pipe:stringSplitter` | 31 | 31 | yes |
| `pipe:number` | 3 | 3 `.html` (the 4th `grep` hit is the TS type `string \| number`) | yes |
| `pipe:uppercase` | 3 | 3 | yes |

### 025 Angular keys the service really uses

Method (`specs/026-service-scanner/ac11/keys025.py`): every key of `runs/canonical/angular-*-canonical.jsonl`
— **313** Angular `npm:` / `syntax:` / `cfg:` keys — tested against the source with a token-aware
check (imports parsed per file, `Sym.member` or a decorator option for members, template syntax
in `.html` / inline templates, JSON paths for `cfg:` keys). **Used by the service: 43. In the
profile: 40.** All three misses are explained:

| Missing 025 key | Why |
|---|---|
| `npm:@angular/core#Component.imports` | False positive of the check: the `imports:` hits are `TestBed.configureTestingModule({ imports })`; no `@Component` in the service has an `imports` option. The profile is right. |
| `syntax:angular-template#?.` | Role `mentioned` in "Parentheses are always respected in template expressions" (19.2 → 20); `?.` is not in `ANGULAR_SYNTAX_TOKENS`. The service does use `?.` in 14 templates, so if 028 should match this rule, `?.` must become a token (or the rule a `behavioral` signal in 027). |
| `syntax:angular-template#async` | Known form mismatch: the scanner records the pipe as `pipe:async` (8 sites). 025 should canonicalize pipes to `pipe:<name>`, or 027 should map them. |

Side observation for 025 / 027: its `syntax:angular-template#…` keys include noise that no
template can contain (`Y`, `y`, `w`, `this.void`, `HostListener`, `document:click`,
`ng-reflect-*`).

### Re-run

```bash
S=$BB_THREAD_STORAGE/ac11; R=/Users/dimo.drangov/DevelopmentTools/paysafe-wac-web-login-fe
time migration-scan $R --out $S/profile.json --force                      # cold, size
migration-scan $R --out $S/profile-full.json --force --max-locations 100000  # for the checks
uv run python specs/026-service-scanner/ac11/keys025.py $R $S/profile-full.json   # 025 key check
```

## Run 1 — public app + synthetic scale tree (earlier, 2026-11-06)

### Service under test

| Property | Value |
|---|---|
| Repository | `gothinkster/angular-realworld-example-app` (shallow clone) |
| Framework | Angular **21.2.12** (from `package-lock`/`package.json`), detected as `angular 21.2.12` |
| Files scanned | 66 (`files_scanned`), 0 skipped, 0 diagnostics |
| Sources | 48 `.ts` (8 with an inline template, 6 of them `*.spec.ts`) + 11 `*.html` templates |

This is a genuine, idiomatic Angular app: standalone components, signals, `@if` / `@for` /
`@defer`, `*ngIf` / `*ngFor` from `@rx-angular/template`, custom pipes, `provideZonelessChangeDetection`,
an inline-template component, and Vitest specs.

### Timings and size

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

### Spot check — 10 random import sites

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

### Template counts against `grep`

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

### 025 Angular entity keys used by the service

Method: every `angular-*-canonical.jsonl` in `runs/canonical/` was read, Angular keys extracted
(`npm:@angular…`, `syntax:angular-template…`) — **252 distinct keys** — and each was searched for
in the service's `src/` with a token-aware `grep` (a member key needs `Sym` followed by `.member`
on the same expression). Keys the service really uses: **32**. In the profile: **25**.

| Missing 025 key | `grep` hits | Why it is not a profile key |
|---|---|---|
| `npm:@angular/platform-browser#ApplicationConfig` | 2 | **Correct in both.** The `grep` hits are the bare name; the app imports it from `@angular/core` (`app.config.ts:1`), recorded as `npm:@angular/core#ApplicationConfig`. The 025 key is the `role: removed` entity of the rule "`ApplicationConfig` Removed from `@angular/platform-browser`" — the *old* import location; the same rule's `role: replacement` entity is `npm:@angular/core#ApplicationConfig`, which **is** in the profile. A service still importing from `platform-browser` would match the removed key; this one is already migrated. (Corrected in review 2026-11-06: an earlier version of this report called it a 025 attribution error.) |
| `npm:@angular/platform-server#testing` | 29 | Not a code fact: `platform-server/testing` appears only as a dependency name in rules/lockfiles, never as an import in `src/`. |
| `syntax:angular-template#**` | 1 | The one hit is a JSDoc opener (`/**`) in a `.ts` file, not a template operator. |
| `syntax:angular-template#in` | 29 | Every hit is TypeScript — type annotations and prose in JSDoc (`in markdown`). There is no `in` inside any binding: `grep` for `{{ … in … }}` and `[x]="… in …"` returns nothing. |
| `syntax:angular-template#void` | 43 | Every hit is a TS return type (`ngOnInit(): void`), not a template expression. |
| `syntax:angular-template#async` | 115 (bare word) | The `async` pipe **is** in the profile, as `syntax:angular-template#pipe:async` (4 sites, matching `grep -rn "| async"` = 4). `async` alone is not in `ANGULAR_SYNTAX_TOKENS`, so 025 only produced this key because an LLM declared `kind: syntax`; 114 of the 115 bare-word hits are TS `async` functions / identifiers (112 alone in `.ts`); the rest are the 4 real pipe uses, which the profile records as `pipe:async`. |
| `syntax:angular-template#track` | 8 | `track` is `@for` microsyntax, not a token in `ANGULAR_SYNTAX_TOKENS` (025 got it the same way, from an LLM `kind: syntax`). The block itself is recorded: `@for` = 8, exactly the 8 `track` sites. |

**No unexplained miss.** One of the seven is a key form the scanner cannot produce (a pipe
emitted as a bare token). That is a matcher input question for 028, not a scanner gap:

- `syntax:angular-template#async` vs `syntax:angular-template#pipe:async` — the scanner's `pipe:`
  prefix (spec5 FR-6) and 025's bare-token form will not compare equal. Either 025 should
  canonicalize a pipe name to `pipe:<name>`, or 027's rule signals should mark pipe rules with
  the `pipe:` prefix. **Recommended: fix on the 025/027 side** — the scanner's form is the one
  that can tell `async` the pipe from `async` the identifier.
- `npm:@angular/platform-browser#ApplicationConfig` is **not** an attribution error (see the
  table): it is the removed side of a move, and the replacement key matches this service. For
  028 this is the expected shape of a "moved symbol" rule — `removed` key absent and
  `replacement` key present means the service is already migrated.


## Regression

```
pytest tests/scanner/            → 382 passed, 4 skipped
pytest tests/pipeline/test_shared_keys.py tests/pipeline/test_canonical_normalize.py
                                 → 28 passed   (the 025 tests that use migration_keys/)
```

Two spec3 / spec4 tests asserted `set(builtin.SOURCE_EXTRACTORS) == set(GRAMMARS)`, so the
`html` extractor first shipped as a separate `builtin.EXTRA_SOURCE_EXTRACTORS`. Review
2026-11-06 closed that: `html` is in `SOURCE_EXTRACTORS`, and the two tests now check behavior
(every TS grammar maps to `extract_ts`) instead of the registry's exact shape.

`tests/pipeline/test_canonical_populate.py` aborts with a numpy segmentation fault
(`numpy/linalg/linalg.py:561 in inv`) in this environment **with and without** this change
(verified by stashing the work tree), so it is unrelated to 026.5.

### How Run 1 was re-runnable (superseded by Run 2)

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

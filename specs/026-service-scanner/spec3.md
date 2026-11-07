# Feature Specification 026.3: TypeScript / JavaScript Imports, Members, Decorators

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Implemented (2026-11-06)

**Depends on**: spec1 (extractor contract, profile writer), spec2 (tsconfig `paths`, workspace
package names). Shared context: see `spec1.md`.

**Scope**: per-file extraction of external imports, member accesses and decorator options from
TS / JS sources. Imports of own code (relative, `paths` aliases) are **skipped** in this spec;
following them through barrels to an external package is spec4.

## Requirements

### FR-5 TypeScript / JavaScript sources (without barrels)

Parsed with **tree-sitter** (`tree-sitter-typescript` for `.ts` / `.tsx`, `tree-sitter-javascript`
for `.js` / `.jsx` / `.mjs` / `.cjs`).

**Import forms recorded**

| Form | Recorded as |
|---|---|
| `import { A, B as C } from 'pkg'` | `npm:pkg#A`, `npm:pkg#B` (local name `C` kept for member tracking) |
| `import D from 'pkg'` | `npm:pkg#default` |
| `import * as ns from 'pkg'` | namespace `ns` → members `ns.X` become `npm:pkg#X` |
| `import 'pkg'` (side effect) | `npm:pkg` in `side_effect_imports` |
| `import type { T } from 'pkg'` | `npm:pkg#T` with `type_only: true` |
| `import { type T, V } from 'pkg'` (inline) | `npm:pkg#T` with `type_only: true`, `npm:pkg#V` without |
| `export { A } from 'pkg'` | re-export: recorded in the file's **export map** (input for spec4); for an external `pkg` also recorded as a usage of `npm:pkg#A` |
| `export * from 'pkg'` | export map (`star_exports`, spec4); for an external `pkg` also the package-level symbol `npm:pkg` |
| `import('pkg')`, `require('pkg')` with a string literal | `npm:pkg` in `symbols` (+ destructured names when present) |
| `import x = require('pkg')` (TypeScript) | `npm:pkg` in `symbols`; `x.member` → `npm:pkg#member` |

`side_effect_imports` holds only `import 'pkg'`. Every other use of a package without a named
symbol (`import()`, `require()`, `export *`) is the package-level key `npm:pkg` in `symbols`.
`symbols[].locations` are **import sites** only (spec1 FR-9): a decorator or a call adds no
symbol location.

**Package of a specifier**: `@scope/name/sub/path` → package `@scope/name/sub/path` (Angular
entry points such as `@angular/core/testing` are packages in 025). The dependency it belongs
to is `@scope/name` (or `name` for unscoped). Deep file imports (`rxjs/internal/…`,
`lodash/fp.js`) are kept as written, extension included.

**Own code is not recorded**: relative specifiers, specifiers matching `compilerOptions.paths`
(spec2), specifiers whose first segment is an entry directly under `compilerOptions.baseUrl`
(`'app/core/x'` with `baseUrl: "./src"` and `src/app/`), and workspace package names declared
in the same repo (spec2). A declared npm dependency of the same name wins over a `baseUrl`
entry. In this spec they are only counted per file (`own_imports`) and kept in the export map,
so spec4 can resolve them.

**Node builtins** (`node:fs`, bare `fs` / `path`) are skipped. A bare builtin name that the repo
declares as an npm dependency (`events`, `buffer`, `util`, `url`, `process` polyfills) is an
external npm package. `node:` is always a builtin.

**Members**: for every identifier bound to an external import (named, aliased, default,
namespace), member accesses `Local.member` and `Local.member(` in the same file are recorded
as `npm:<pkg>#<Symbol>.<member>` with the access location. Examples: `TestBed.get(…)`,
`TB.get(…)` after `import { TestBed as TB }`, `core.inject(…)` after `import * as core`. Only
the first member segment is recorded (`A.b.c` → `A.b`). A local declaration that shadows the
import name inside a scope stops member tracking in that scope.

**Decorators**: the literal keys of the first object argument of `@Component({...})`,
`@Injectable(...)`, … are recorded as members: `npm:@angular/core#Component.standalone`,
`…#Component.changeDetection`. Shorthand keys (`{ selector }`) count, and so does a decorator
through a namespace import (`@core.Component({...})`). Many Angular rules are about decorator
options. The decorator adds no symbol location (its import site already is one).

**Per-file output** (extractor contract, spec1): `symbols`, `members`, `side_effect_imports`,
an export map (`{exported name → (specifier, original name)}` and `export *` specifiers), and
the bindings of own-code imports. A file tree-sitter cannot parse (error nodes covering the
whole file) → diagnostic; partial parse errors still yield the imports that parsed.

## Acceptance Criteria

- **AC-1 TS imports**: every row of the FR-5 table on a fixture file, including `type`-only,
  dynamic `import()` and `require`. Relative and `paths`-alias imports are not recorded.
  `@angular/core/testing` is its own package; `rxjs/internal/x` kept as written.
- **AC-3 Members**: `TestBed.get(…)`, `TB.get` (alias), `core.inject` (namespace) and
  `@Component({standalone: true})` → the expected member keys and lines. `A.b.c` → `A.b`.
- **AC-3.2**: `.js`, `.mjs`, `.cjs`, `.tsx` fixtures parse with the right grammar.
- **AC-3.3 Bounds**: a symbol used in 30 files with `--max-locations 5` → `count` exact,
  `files: 30`, 5 locations, `truncated: true`; `test` flag correct on `*.spec.ts` sites.
- **AC-3.4** (review 2026-11-06):
  - `baseUrl: "./src"` + `'app/core/x'` → not recorded, and a declared `lodash` still wins over
    a `lodash/` entry under `baseUrl`;
  - declared `events` / `buffer` → `npm:events#…`, `npm:buffer#…`; `fs` / `node:path` skipped;
  - two `@Input()` → `npm:@angular/core#Input` with one location (the import site);
  - `export * from '@angular/cdk/a11y'` → `npm:@angular/cdk/a11y` in `symbols`;
  - `import { type Signal, inject }` → only `Signal` is `type_only`;
  - `import fs = require('fs-extra')` → `npm:fs-extra`, `fs.copy` → `npm:fs-extra#copy`;
  - `@Component({ selector })` and `@core.Component({ selector: 'x' })` → `…#Component.selector`;
  - `import('pkg')` / `require('pkg')` → `symbols`, not `side_effect_imports`;
  - `lodash/fp.js` → `npm:lodash/fp.js#…`.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec2 in the default order) must still pass. A failing earlier test that checks **behavior** is a regression, not an outdated test. A test that pins an internal detail (the exact contents of a registry, a private helper's shape) may be changed deliberately when this spec extends that detail; such a change is named in the spec's CHANGELOG entry.

## How to test after spec3

```bash
migration-scan /path/to/angular-service
jq '[.symbols[] | select(.key | startswith("npm:@angular/core#"))] | length' .migration/profile.json
jq '.members[] | select(.key | test("TestBed"))' .migration/profile.json
grep -rn "from '@angular/core'" src | head   # spot-check against the profile
```

Known gap until spec4: symbols imported through `@app/*` barrels are missing.

## Implementation Notes

- Module: `migration_planner/scanner/ts.py`.
- New dependencies: `tree-sitter`, `tree-sitter-typescript`, `tree-sitter-javascript`
  (prebuilt wheels, no compiler needed).
- Use tree-sitter queries for import / export / call / member / decorator nodes; keep the
  extractor a pure function of `(path, bytes, module context)` for spec9 caching.

## Estimate

~6 h: imports, members, decorators 5 h; fixtures and tests 1 h.

# Feature Specification 026.3: TypeScript / JavaScript Imports, Members, Decorators

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Draft

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
| `export { A } from 'pkg'` / `export * from 'pkg'` | re-export: recorded in the file's **export map** (input for spec4); for an external `pkg` also recorded as a usage of `npm:pkg#A` |
| `import('pkg')`, `require('pkg')` with a string literal | `npm:pkg` (+ destructured names when present) |

**Package of a specifier**: `@scope/name/sub/path` → package `@scope/name/sub/path` (Angular
entry points such as `@angular/core/testing` are packages in 025). The dependency it belongs
to is `@scope/name` (or `name` for unscoped). Deep file imports (`rxjs/internal/…`) are kept as
written.

**Own code is not recorded**: relative specifiers, specifiers matching `compilerOptions.paths`
(spec2), and workspace package names declared in the same repo (spec2). In this spec they are
only counted per file (`own_imports`) and kept in the export map, so spec4 can resolve them.

**Members**: for every identifier bound to an external import (named, aliased, default,
namespace), member accesses `Local.member` and `Local.member(` in the same file are recorded
as `npm:<pkg>#<Symbol>.<member>` with the access location. Examples: `TestBed.get(…)`,
`TB.get(…)` after `import { TestBed as TB }`, `core.inject(…)` after `import * as core`. Only
the first member segment is recorded (`A.b.c` → `A.b`). A local declaration that shadows the
import name inside a scope stops member tracking in that scope.

**Decorators**: `@Component({...})`, `@Injectable(...)` are usages of the imported symbol. The
literal keys of their first object argument are recorded as members:
`npm:@angular/core#Component.standalone`, `…#Component.changeDetection`. Many Angular rules
are about decorator options.

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

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec2 in the default order) must still pass unchanged; a failing earlier test is a regression, not an outdated test.

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

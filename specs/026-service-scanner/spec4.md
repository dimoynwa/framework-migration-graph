# Feature Specification 026.4: Barrel and Alias Resolution (TS / JS)

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Implemented (2026-11-06)

**Depends on**: spec2 (effective tsconfig `paths` / `baseUrl`, workspace packages), spec3
(per-file export maps and own-code import bindings). Shared context: see `spec1.md`.

**Scope**: a post-pass that follows own-code imports through barrels and path aliases until an
external package is reached, and records the external key at the original import site.

## Requirements

### FR-5 Barrels and aliases

- When a file imports from its own code, the scanner resolves the target file: relative path,
  `compilerOptions.paths` aliases (with `*` wildcards and multiple targets, first existing wins),
  `baseUrl`, workspace package names (their `package.json` `main` / `module` / `types` / `exports`
  `"."` entry, else `index.*`; a subpath `@demo/ui/testing` tries `exports["./testing"]` and
  `"./*"` patterns first), trying `.ts`, `.tsx`, `.d.ts`, `.js`, `.mjs`, `.cjs`, `/index.*`.
  A bundler query (`./worker?worker`) is stripped before probing.
- A `paths` alias whose targets all live under `node_modules`
  (`"@angular/*": ["./node_modules/@angular/*"]`) is a redirect to an external package, not own
  code: imports through it stay external facts.
- It then follows `export { X } from '…'`, `export { X as Y } from '…'`, `export * from '…'`,
  `export * as ns from '…'` and `import { X } from '…'; export { X }` until an external package is
  reached.
- **Several `export *`**: every own star is searched in order until one exports the name (the
  `public-api.ts` pattern). If none does, a name behind exactly **one** external `export *` is
  attributed to that package; behind **several** external stars it is not guessed:
  diagnostic `ambiguous_export` (`map: @angular/core | rxjs`) and no fact.
- Only **module-scope** declarations end a chain as own code; a `const` inside a function body
  does not shadow an `export *` name.
- The external key is recorded at the **original import site**, so
  `import { inject } from '@app/core'` with `core/index.ts → export { inject } from '@angular/core'`
  gives `npm:@angular/core#inject` at the importing file.
- Renames are applied along the chain: `export { inject as di } from '@angular/core'` and
  `import { di } from '@app/core'` → `npm:@angular/core#inject`, and member tracking of the
  local `di` records `npm:@angular/core#inject.<member>`.
- Namespace imports of a barrel (`import * as core from '@app/core'`) resolve per member:
  `core.inject(…)` → `npm:@angular/core#inject`. A re-exported external namespace
  (`export * as rx from 'rxjs'`, then `rx.filter()`) gives `npm:rxjs#filter` at the access.
- Inline `type` on an own import (`import { type Signal } from '@app/core'`) keeps
  `type_only` per name at the import site.
- Names that end in a local declaration (own class / function) are dropped silently: that is own
  code.
- Cycles and depth > 10 stop resolution and add a diagnostic (`barrel_cycle`,
  `barrel_depth`). An unresolvable target file → diagnostic `unresolved_import`.

### Execution

- Runs after all per-file extraction, on the collected export maps (spec1 post-pass). Resolution
  results are memoized per `(file, exported name)`.

## Acceptance Criteria

- **AC-2 Barrels**: `a.ts` imports `inject` from `@app/core`, `core/index.ts` re-exports from
  `./di`, and `di.ts` re-exports from `@angular/core` → `npm:@angular/core#inject` at `a.ts`.
  A barrel cycle gives a diagnostic and no crash.
- **AC-2.2**: `export *` chain, rename chain (`as`), namespace import of a barrel, a
  workspace-package import, and a `paths` alias with `*` → the expected keys at the import site.
- **AC-2.3**: a name that resolves to a local class is not recorded; depth 11 → diagnostic.
- **AC-2.4** (review 2026-11-06):
  - `export * from './a'; export * from './b'` with the name in `b` → resolved;
  - `import { Injectable } from '@angular/core'; export { Injectable }` → resolved;
  - `"@angular/*": ["./node_modules/@angular/*"]` → `@angular/core` imports stay external, no
    `unresolved_import`;
  - `export * from '@angular/core'; export * from 'rxjs'` + `import { map }` →
    `ambiguous_export`, no `npm:@angular/core#map`;
  - a single `export * from 'rxjs'` next to a function with `const map` → `npm:rxjs#map`;
  - `import { type Signal, inject } from '@app/core'` → only `Signal` is `type_only` at the site;
  - `@demo/ui/testing` via `exports["./testing"]` → resolved;
  - `export * as rx from 'rxjs'` + `rx.filter()` → `npm:rxjs#filter`;
  - `'./worker?worker'` → no `unresolved_import`.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec3 in the default order) must still pass. A failing earlier test that checks **behavior** is a regression, not an outdated test. A test that pins an internal detail (the exact contents of a registry, a private helper's shape) may be changed deliberately when this spec extends that detail; such a change is named in the spec's CHANGELOG entry.

## How to test after spec4

```bash
migration-scan /path/to/angular-service --force
grep -rn "from '@app/" src | head    # pick a few barrel imports
jq '.symbols[] | select(.locations[].file == "src/app/<file>.ts") | .key' .migration/profile.json
jq '[.diagnostics[] | select(.kind | startswith("barrel") or . == "unresolved_import")]' .migration/profile.json
```

Expected: the symbol count goes up compared to spec3 on a service that uses barrels, and the
barrel-imported Angular symbols appear at the importing file.

## Implementation Notes

- Module: `migration_planner/scanner/ts_resolve.py` (part of FR-5; kept separate from `ts.py`
  so the per-file extractor stays pure and cacheable).

## Estimate

~5 h: resolution 4 h; fixtures and tests 1 h.

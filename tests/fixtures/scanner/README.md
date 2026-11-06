# polyglot fixture

One tree that exercises spec 026.1 (skeleton, CLI, discovery, modules) and 026.2 (npm manifests):

- `.` — npm module root (`package.json`, `tsconfig.json`) with a source file and a `*.spec.ts`
  test, so the `test: true` flag has something to point at. `package.json` declares one
  dependency (`@angular/core`) and one config subtree (`engines`), so the npm reader has
  something to record without a lockfile.
- `backend/` — Maven module root (`pom.xml`) with a Java source and a Spring
  `application.yml`, which discovery classifies as `manifest:spring.config`.
- `tools/` — Gradle Kotlin DSL module root (`build.gradle.kts`) with a Java source.

No build outputs are committed; `build/`, `.gradle/`, `node_modules/` and `.migration/` are
ignored here so a stray IDE sync or a local scan cannot change the fixture between runs.

`tests/fixtures/scanner/angular-app/` is the fuller npm fixture (026.2): `package.json` with all
four dependency scopes plus `browserslist` / `overrides` / `resolutions`, a `package-lock.json`
that pins `@angular/core` to `19.2.4`, an `angular.json` with two projects and three architects,
and three `tsconfig` files that use comments, trailing commas and `extends`.

`tests/fixtures/scanner/npm-workspace/` covers AC-8.2: a root workspace (`package.json` plus one
lockfile) with two package modules, so the scanner produces three modules, records the workspace
package names as own packages, and reads each module's own dependency scopes.

`tests/fixtures/scanner/ts-imports/` covers spec 026.3: one TypeScript file with every row of the
FR-5 import table (named, aliased, default, namespace, side-effect, `type`, `export … from`,
`export *`, `import()`, `require()` with and without destructuring), plus a relative import, a
`@app/*` paths alias and a workspace package (`@demo/ui`) so the own-code cases are exercised.
The files those own imports name (`src/local.ts`, `src/app/shared.ts`, `packages/ui/src/index.ts`)
exist too, because spec 026.4 resolves them: an own import with no file is an
`unresolved_import` diagnostic, and this fixture has none.

`tests/fixtures/scanner/ts-barrels/` covers spec 026.4, one fixture per acceptance criterion:

- `src/app/core/` — a barrel (`index.ts`) that re-exports from `./di` and `export *` from
  `./util`, with a rename (`export { inject as di }`) and a local class the barrel declares
  itself. `src/app/feature.ts` imports from `@app/core`, so the external keys land there.
- `src/app/namespaced.ts` — `import * as core from '@app/core'`, then `core.inject(…)` and a
  namespaced decorator (`@core.Component({…})`).
- `src/app/feature-imports.ts` — a workspace package (`@demo/ui`, entry point from its
  `exports` map) and a `paths` alias with two targets (`@shared/*`).
- `src/app/cycle-a.ts` + `cycle-b.ts` — a barrel cycle (diagnostic, no crash).
- `src/deep/ok0…ok9.ts` (depth 10, resolves) and `deep0…deep10.ts` (depth 11, `barrel_depth`).
- `src/app/mixed.ts` + `mixed-barrel.ts` — a name that ends in a local declaration next to one
  that reaches Angular.

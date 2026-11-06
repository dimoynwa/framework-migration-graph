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

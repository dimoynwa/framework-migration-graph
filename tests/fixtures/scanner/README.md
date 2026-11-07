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

`tests/fixtures/scanner/ts-barrels/` covers spec 026.4, one fixture per acceptance criterion:- `src/app/core/` — a barrel (`index.ts`) that re-exports from `./di` and `export *` from
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

`tests/fixtures/scanner/angular-templates/` covers spec 026.5 (FR-6 / AC-4): one Angular module
with every source of a template.

- `src/app/app.component.html` — `@if` / `@else if` / `@else` / `@empty`, `@defer` /
  `@placeholder` / `@loading` / `@error`, `@let`, `*ngFor`, `{{ in }}`, a `| date:` pipe, a
  `a || b` that must not become a pipe, prose containing `in`, and a leading HTML comment that
  holds `@defer *ngFor in void @switch` so a commented token has somewhere to be ignored.
- `src/app/inline.component.ts` — an inline backtick template (multi-line, so token lines are
  `.ts` lines), a single-quoted inline template with `*ngIf`, and a template whose text holds
  `in` outside any binding.

`tests/fixtures/scanner/node-html/` is the negative case: a Node module (no Angular framework)
with an `index.html` full of template syntax, which must produce **no** `templates[]` entries
because a non-Angular `.html` file is not a template.

`tests/fixtures/scanner/spring-maven/` covers spec 026.6 (FR-3, FR-8, AC-6): a Maven
multi-module tree whose parent pom holds what a child inherits.

- Root `pom.xml` — a parent pom (`com.acme:acme-parent`) with `<properties>`
  (`java.version`, `spring-boot.version`, `jackson.version`, and an
  `acme.version` that is `${project.version}`), the `spring-boot-dependencies` BOM import
  (FR-3 case 2, its version from a property), a managed entry that is not an import, and
  `<modules>` naming `app` and `lib`.
- `app/pom.xml` — a child with no Boot parent of its own: its Spring Boot version comes from the
  parent's BOM. It exercises a dependency with no version, a `<scope>runtime</scope>`, a
  `${jackson.version}` inherited from the parent, a `${acme.version}` that resolves through the
  parent's `${project.version}`, an unresolved `${external.bom.version}` (AC-6: raw text plus a
  diagnostic), a plugin, and a plugin with no `<groupId>`.
- `lib/pom.xml` — a second child, to prove the parent's properties reach every module.

`tests/fixtures/scanner/spring-gradle/` covers spec 026.6 for Gradle (AC-7):

- `settings.gradle.kts` — `pluginManagement { plugins { … } }` (the Boot and
  dependency-management versions), and `include("service", ":platform:common")` so the module
  roots come from the settings script.
- `build.gradle.kts` — the root project declaring `id("org.springframework.boot") version "3.4.1"
  apply false`: a version for the subprojects, but the root is not itself on Spring Boot.
- `gradle/libs.versions.toml` — `[versions]` / `[libraries]` / `[plugins]`, with `version.ref`,
  a literal-version library and a literal-version plugin.
- `gradle.properties` — `springBootVersion` and `springCloudVersion`, variables a build file uses.
- `service/build.gradle` — Groovy DSL: an unversioned Boot plugin (version inherited from the
  root), a catalog plugin alias, `ext { … }`, `platform(…)` as a BOM, string and map notation, a
  catalog accessor, `project(':platform:common')` (not a fact), a variable from
  `gradle.properties`, a trailing closure with `exclude`, an unresolved `$externalLibVersion`,
  a `java { toolchain { … } }` and a flat `sourceCompatibility`.
- `platform/common/build.gradle.kts` — a Kotlin subproject with no Spring facts at all.

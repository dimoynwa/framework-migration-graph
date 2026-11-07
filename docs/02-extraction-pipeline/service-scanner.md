# Service Scanner (`migration-scan`)

The first part of the **migration planner**: the tool that reads one service repository and
writes a small, deterministic profile of what is in it. The planner's whole job is to answer
"which migration rules apply to *this* service" — and it answers that from the profile, not by
reading the codebase into an agent's context.

`migration-scan` is step 026 of the road to that answer. It reads the service; it does not read
the graph, call a model or use the network.

```text
service repo ──▶ migration-scan ──▶ .migration/profile.json ──▶ matcher (028) ──▶ commands (030)
                                    (+ one summary line on stdout)
```

## Principles

| Principle | Meaning |
|---|---|
| **No LLM, no network, no graph** | The scanner runs in a service repo, offline. It imports nothing from `migration_oracle.config`, `graph`, `mcp` or `pipeline`, so it installs without Neo4j, LangChain or the model clients. |
| **External symbols only** | Imports of the service's own code (relative paths, path aliases, its own Java packages) are not recorded. |
| **Rule-independent** | The profile records facts, never decisions. One scan serves every framework hop. |
| **Bounded output** | Per symbol a count (always exact) plus at most `--max-locations` locations. |
| **Agent-friendly** | stdout is one summary line. The profile is for tools, not for an agent's context. |
| **Best effort, never silent** | Anything unresolvable is counted and listed in `diagnostics`. One bad file never fails a scan. |

## CLI

```text
migration-scan [PATH] [--out FILE] [--force] [--max-locations N]
               [--include-tests/--no-include-tests] [--json-summary]
```

| Flag | Default | Behavior |
|---|---|---|
| `PATH` | current directory | Repository to scan. |
| `--out FILE` | `PATH/.migration/profile.json` | Where the profile goes. |
| `--max-locations N` | `20` | Locations stored per symbol. `count` is always exact. |
| `--include-tests` | on | Test files are scanned and each location is flagged `test: true`. |
| `--no-include-tests` | — | Drop `*.spec.ts`, `*.test.ts`, `src/test/**` and every test source set `src/<name>Test/**` (`src/integrationTest`, `src/componentTest`, …) and Maven's `src/it/**` at discovery. |
| `--json-summary` | off | Print the summary as one JSON object instead of the line. |
| `--no-values` | off | Store no config value: `value` is `null` in every `config[]` entry, so a profile can be attached to a CI job (026.8). |
| `--force` | off | Accepted now; it only has an effect once the incremental cache lands (spec9). |

stdout is always one line, with every count printed even when zero:

```text
scanned 4812 files · angular 19.2.0 · 61 deps · 312 symbols · 48 members · 27 config · 4 template tokens · 3 diagnostics → .migration/profile.json (2.4 s)
```

Exit codes: `0` profile written, `1` usage error, `2` no supported manifest found under `PATH`.

On a first run in a repository that does not ignore `.migration/`, a hint is printed to stderr.
Nothing is written to `.gitignore`.

## File discovery

- Inside a git work tree the file list is `git ls-files --cached --others --exclude-standard`,
  so `.gitignore` is respected and committed files are scanned even if ignored later.
- Outside git the tree is walked, applying `.gitignore` files as it goes, so the two modes
  produce the same file set.
- Never entered, at any depth: `node_modules`, `.angular`, `.gradle`, `.git`, `.migration`.
- Build-output names `dist`, `build`, `target`, `out` are skipped only outside a `src/`
  directory. Inside `src/` they are ordinary Java packages or app folders
  (`src/main/java/com/x/build/`) and are scanned.
- Walk mode applies every `.gitignore` from the root down to the file's directory.
- A source file over 2 MB is not read; a manifest gets a 50 MB cap instead, because a real
  `package-lock.json` is often over 2 MB. A `*.min.js` or a JS file whose first line exceeds
  1000 characters is treated as generated. Both are counted in `diagnostics`.
- Each remaining file is classified `manifest:<kind>` or `source:<lang>`; anything else is
  ignored, so a later spec only registers a handler for its own kind.

## Modules

A **module root** is a directory holding `package.json`, `pom.xml` or `build.gradle(.kts)`.
Every manifest and source file belongs to its nearest module root, so npm workspaces, Maven
modules and Gradle subprojects all land in one profile. A file under no module root (a root
`tsconfig.json`, a shared `config/application.yml` next to `svc/pom.xml`) belongs to module
`.`, which then appears in `modules[]`; nothing is dropped.

The repo-level `framework` is the one detected in most modules; a tie is listed in
`diagnostics` and broken deterministically by name. With no detection at all the summary says
`no framework`.

## npm manifests (026.2)

One reader handles `package.json`, `package-lock.json`, `angular.json` and `tsconfig*.json`
together, because they answer one question: what does this npm module declare, install and
compile with? It runs once per module with all of that module's npm manifests.

### `package.json`

- `dependencies`, `devDependencies`, `peerDependencies` and `optionalDependencies` become
  `dependencies[]` entries with `{key: "npm:<name>", range, version, scope, module}`. `range` is
  the specifier exactly as written (`"^19.2.0"`); `version` is the **installed** version from
  `package-lock.json` when it is known.
- Config keys (scalars only, values truncated to 200 chars) come from `engines.*`, `type`,
  `browserslist`, `overrides.*`, `resolutions.*` and `workspaces`:
  `cfg:package.json#engines.node = ">=18.19.0"`. Lists keep their index
  (`browserslist.0`), so no two facts collide on one key.
- The package's own `name` and the names of its npm workspace packages are recorded in
  `modules[].own_packages` (each module lists its own names). Source extractors get the
  repo-wide union, so a later spec can tell an import of the repo's own code (any sibling
  package) from an import of an external package.

### `package-lock.json`

Only versions are read: `packages["node_modules/<name>"].version`, with the module's own
`node_modules` preferred over a hoisted one. Lockfile v1 `dependencies` is the fallback. A
module without its own lockfile uses the nearest one in a parent directory up to the scan root,
so `frontend/packages/ui` reads `frontend/package-lock.json`. `dependencies[].version_source` is
`lockfile` (installed), `range` (the lowest version the range allows) or `null`.

### Angular version (FR-3)

Only a module whose `package.json` declares `@angular/core` (any scope) is an Angular module; a
hoisted `@angular/core` in a shared lockfile does not make a sibling `server` package Angular.
Its version is the lockfile's installed one, else the declared range kept as `raw` and
normalized to the **lowest** version it allows (`>1.2` → `1.3.0`, as in npm). The repo-level `framework` is then
the one found in most modules (026.1).

| Range | Normalized |
|---|---|
| `^19.2.0` | `19.2.0` |
| `~1.4` | `1.4.0` |
| `>=18` | `18.0.0` |
| `19.x` | `19.0.0` |
| `^19.2.0 \|\| ^20.0.0` | `19.2.0` |
| `*`, `latest`, `workspace:*`, `file:…` | `null` (no floor to normalize) |
| anything else | `null` + an `unsupported_range` diagnostic |

The floor is the right answer because the profile answers "which version *could* this service be
on": with `^19.2.0` it may be any 19.x, and a rule that applies from 19.2 applies.

### `angular.json`

Every scalar leaf becomes a config key with the project name replaced by `*`, so one key
describes every project:

```text
cfg:angular.json#projects.*.architect.build.builder = "@angular-devkit/build-angular:application"
```

Builders (`…architect.<target>.builder`) therefore land one key per target, which is what most
rules are written against. The real project names go to `modules[].angular_projects`.

### `tsconfig*.json`

- JSON with comments and trailing commas is accepted (`strip_jsonc`, no dependency).
- `extends` is followed inside the repo, giving the **effective** config. A config that
  extends something in `node_modules` or outside the repo is not followed and produces a
  `tsconfig_extends_outside_repo` diagnostic; a cycle produces `tsconfig_cycle`.
- Scalar leaves of the effective `compilerOptions.*` and `angularCompilerOptions.*` become
  `cfg:tsconfig.json#<dotted path>` — one file name, because `tsconfig.app.json` and
  `tsconfig.spec.json` canonicalize to the same key in 025. Each key is emitted once, with
  `file` saying which config it came from.
- `compilerOptions.paths` and `baseUrl` are kept on the module as the **effective path map**
  (`PathMap`, passed to source extractors), for import resolution in spec3 / spec4.



`.migration/profile.json` is UTF-8 JSON with sorted keys and sorted lists: two scans of an
unchanged tree differ only in `generated.at` (and the measured `duration_ms`).

```json
{
  "schema": 1,
  "generated": { "at": "2026-11-06T10:20:00Z", "scanner": "026", "root": ".",
                 "files_scanned": 4812, "files_skipped": 37, "duration_ms": 2410 },
  "inputs_hash": "sha256:…",
  "framework": { "name": "angular", "version": "19.2.0", "raw": "^19.2.0", "source": "package-lock.json" },
  "modules": [
    { "path": ".", "manifests": ["package.json", "angular.json", "tsconfig.json"],
      "frameworks": [{ "name": "angular", "version": "19.2.0", "raw": "^19.2.0",
                       "source": "package-lock.json" }],
      "angular_projects": ["payments-ui"], "own_packages": ["payments-ui"] }
  ],
  "dependencies": [
    { "key": "npm:@angular/platform-server", "range": "^19.2.0", "version": "19.2.4",
      "scope": "dependencies", "module": ".", "kind": "dependency" }
  ],
  "symbols": [
    { "key": "npm:@angular/core#inject", "count": 1840, "files": 912, "type_only": false,
      "locations": [{ "file": "src/app/a.service.ts", "line": 5, "test": false }],
      "truncated": true }
  ],
  "members": [
    { "key": "npm:@angular/core/testing#TestBed.get", "count": 3,
      "locations": [{ "file": "src/app/a.spec.ts", "line": 12, "test": true }] }
  ],
  "side_effect_imports": [{ "key": "npm:zone.js", "count": 1, "locations": [] }],
  "wildcard_imports": [
    { "key": "maven:java.util.*", "count": 12, "files": 3,
      "names": ["ArrayList", "List", "Map"],
      "locations": [{ "file": "src/main/java/com/acme/Svc.java", "line": 6, "test": false }],
      "truncated": false }
  ],
  "config": [
    { "key": "cfg:package.json#engines.node", "value": ">=18", "file": "package.json",
      "module": ".", "line": null, "raw_key": null, "profile": null, "kind": null, "test": false }
  ],
  "templates": [{ "key": "syntax:angular-template#@defer", "count": 4, "locations": [] }],
  "diagnostics": [
    { "kind": "unresolved_variable", "file": "build.gradle", "line": 14, "detail": "$jacksonVersion" }
  ]
}
```

### Which spec fills which section

| Section | Filled by |
|---|---|
| `generated`, `inputs_hash`, `modules[].path/manifests`, discovery `diagnostics` | **026.1** (this page) |
| `framework`, `modules[].frameworks` | **026.2** (Angular), **026.6** (Spring Boot) |
| `modules[].angular_projects`, `modules[].own_packages`, npm `dependencies`, npm / angular / tsconfig `config` | **026.2** |
| `symbols`, `members`, `side_effect_imports` (TS/JS) | **026.3**, barrel-resolved keys **026.4** |
| `templates` | **026.5** |
| Maven / Gradle `dependencies`, `cfg:pom.xml` / `cfg:build.gradle` `config` | **026.6** |
| `symbols`, `members`, `wildcard_imports` (Java) | **026.7** |
| Spring `config`, `modules[].spring_config_files` | **026.8** |
| Incremental cache, `--jobs`, `[planner]` extra | spec9 |

A section whose spec has not landed yet is an empty list, so the schema is stable throughout.

### Reading it

- `locations` are **import sites** — the files a matcher must search for instance calls, because
  the scanner does not resolve types (`entity.getStatusCodeValue()` on a local variable is not
  attributed to `ResponseEntity`).
- `count` is the number of distinct `(file, line)` sites, always exact. `truncated: true` means
  more sites exist than the stored locations.
- `files` is the number of distinct files using the fact.
- `dependencies[]` has one entry per `(key, module, scope, kind)`; `kind` is
  `dependency | bom | parent | plugin`, so a BOM import and a plain dependency on the same
  artifact are two entries. `version_source` says where `version` came from: `lockfile` or
  `range` for npm, `declared`, `catalog`, `inherited` or `pluginManagement` for Maven / Gradle.
- `wildcard_imports[]` is one entry per wildcard import key (`maven:java.util.*`), with `names`:
  the simple names the service uses that only that package can supply (026.7), so a matcher can
  test `java.util.Map` without the scanner resolving the class.
- `config[]` has one entry per occurrence `(key, module, file, profile, line)`: the same key in
  two modules, files or Spring profiles is two entries. `line` is filled by the Maven / Gradle
  readers (026.6) and by the Spring config reader (spec8); `raw_key`, `profile` and `kind` are
  the Spring reader's and `null` elsewhere.
- All paths are relative to the scan root with `/` separators, so a profile can be attached to a
  CI job and read on another machine.
- `inputs_hash` is sha256 over the sorted `(path, sha256(content))` of every scanned file, the
  scanner version and the output-changing scan options (`--max-locations`, `--include-tests`).
  An unchanged tree scanned with the same options gives an unchanged hash.

## TypeScript / JavaScript sources (026.3)

`migration_planner/scanner/ts.py` parses `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` and `.cjs` with
**tree-sitter** (the grammar follows the extension) and records imports, member accesses and
decorator options. The extractor is a pure function of the file's bytes, so spec9 can cache it
and run it in a process pool.

### What is recorded

| Form | Fact |
|---|---|
| `import { A, B as C } from 'pkg'` | `npm:pkg#A`, `npm:pkg#B` |
| `import D from 'pkg'` / `import { default as D }` | `npm:pkg#default` |
| `import * as ns from 'pkg'` + `ns.X` | `npm:pkg#X` at the use site |
| `import 'pkg'` | `npm:pkg` in `side_effect_imports` |
| `import type { T } from 'pkg'` / `import { type T }` | `npm:pkg#T`, `type_only: true` (per name for inline `type`) |
| `export { A } from 'pkg'` | `npm:pkg#A` |
| `export * from 'pkg'` | `npm:pkg` in `symbols` (names feed the export map for spec4) |
| `import('pkg')`, `require('pkg')`, `import x = require('pkg')` | `npm:pkg` in `symbols` (plus the destructured names) |

Only `import 'pkg'` goes to `side_effect_imports`. `symbols[].locations` are import sites: a
decorator or a call never adds a symbol location.

**Package of a specifier.** `@angular/core/testing` is its own package (an Angular entry point,
as in 025); deep imports are kept as written (`rxjs/internal/operators/map`, `lodash/fp.js`).
The rules live in
`migration_keys/specifiers.py`, shared with 025.

**Own code is not a fact.** A relative specifier, a `compilerOptions.paths` alias, a specifier
under `compilerOptions.baseUrl` (`'app/core/x'` with `baseUrl: "./src"`; a declared dependency
of the same name wins) and a workspace package name are counted in `own_imports` and kept as
`OwnImport` entries (specifier, local names, import site) for spec4 to follow through a barrel.
A Node builtin (`node:fs`, `fs`) is neither and is skipped, unless the repo declares an npm
package of that name (`events`, `buffer` polyfills), which is then external. If `@shared/x` never shows up in the profile, that is the reason: it
is the service's own code.

**Members.** For every identifier bound to an external import — named, aliased, default or
namespace — `Local.member` is recorded as `npm:<pkg>#<Symbol>.<member>` at the access line,
first segment only (`A.b.c` → `A.b`). A local declaration that shadows the name stops tracking
in that scope, so `function f(TestBed) { TestBed.get(…) }` is not a use of the imported
`TestBed`.

**Decorators.** Each literal key of a decorator's first object argument is a member
(`npm:@angular/core#Component.standalone`), shorthand keys (`{ selector }`) and namespaced
decorators (`@core.Component({…})`) included — that is what most Angular rules are written
against. The decorator adds no symbol location.

**Parse errors.** A file whose whole tree fails is a `parse_error` diagnostic; a partial parse
still yields the imports that parsed and adds `partial_parse_error`. One bad file never loses
the rest of its facts.

### Barrels and aliases (026.4)

A previous version of this page said symbols behind a barrel were missing. They are resolved now
by a post-pass, `migration_planner/scanner/ts_resolve.py`, which runs on the collected per-file
facts and adds facts **at the original import site**.

```text
core/index.ts:  export { inject } from './di'
di.ts:          export { inject } from '@angular/core'
a.ts:           import { inject } from '@app/core'     →  npm:@angular/core#inject at a.ts:1
```

**Specifier → file.** A relative path, a `compilerOptions.paths` alias (longest matching pattern,
targets in order, first existing wins), a `baseUrl` path or a workspace package name (its
`package.json` `exports["."]` / `types` / `module` / `main`, else `index.*`; a subpath such as
`@demo/ui/testing` tries `exports["./testing"]` and `"./*"` patterns first). A `paths` alias whose
targets all live under `node_modules` is a redirect to an external package and stays external. A
bundler query (`./worker?worker`) is stripped. Each candidate is probed with `.ts`, `.tsx`, `.d.ts`, `.js`, `.jsx`, `.mjs`, `.cjs` and `/index.*`; a `.js`
specifier also finds its `.ts` source, which is what `NodeNext` projects write.

**File → external package.** `export { X } from '…'`, `export { X as Y } from '…'` (renames
applied along the chain), `export * from '…'`, `export * as ns from '…'` and
`import { X } …; export { X }` are followed until an external package is reached. Every own
`export *` is searched in order until one exports the name. A name that ends in a module-scope
declaration is own code and is dropped silently (a `const` inside a function does not count). An
external `export *` cannot be enumerated: behind exactly one, the name belongs to that package;
behind several, it is not guessed — `ambiguous_export` (`map: @angular/core | rxjs`), no fact.

**What is recorded.**

| Shape | Fact |
|---|---|
| `import { inject } from '@app/core'` | `npm:@angular/core#inject` at the import site |
| `export { inject as di } …` + `import { di } …` | `npm:@angular/core#inject`; `di.call(…)` → `… #inject.call` |
| `import * as core from '@app/core'` + `core.inject(…)` | `npm:@angular/core#inject` at the access |
| `@core.Component({ selector })` on a barrel namespace | `…#Component` + member `…#Component.selector` |
| `export * as rx from 'rxjs'` + `import { rx } …` + `rx.filter()` | `npm:rxjs#filter` at the access |
| `import { type Signal } from '@app/core'` | `type_only: true` at the site |
| a name the barrel declares itself | nothing (own code) |

**Bounds, never silent.** A cycle gives `barrel_cycle`, a chain deeper than 10 gives
`barrel_depth`, and an own import whose file cannot be found gives `unresolved_import`. A
specifier that names an asset (`./x.scss`, `./data.json`) is not a module and is skipped without a
diagnostic. Results are memoized per `(file, exported name)`, and only a definitive answer is
cached — a give-up depends on how deep one entry point already is, so caching it could deny a
shorter chain the same name.

`symbols[].locations` stay import sites only (FR-9): a barrel's own `export … from 'pkg'` is an
import site too, so an intermediate barrel of the codebase is listed alongside the file that
imports it.

## Angular templates (026.5)

Templates are the one place Angular facts live outside TypeScript, so `migration_planner/scanner/templates.py`
lexes them and fills `templates[]`. Two sources, one lexer:

| Source | Where it is found | `file` / `line` |
|---|---|---|
| `*.html` | the `html` extractor, for modules whose framework is Angular | the `.html` file and its own line |
| inline `template: '…'` / `` template: `…` `` | the spec3 `@Component` decorator pass | the **`.ts`** file, and the token's line in it |

A `*.html` file of a module with no Angular framework is **not** a template (FR-6), so the
`index.html` of a Node service or a static site contributes nothing. Only Angular's `@Component`
(from `@angular/core`, or re-exported through the service's own barrel) carries an inline
template — a `template` option on `@Directive`, on an own-code decorator or on a Vue class
component (`vue-property-decorator`) is not one — and a template literal with `${…}`
substitutions is skipped, because its rendered text is not static.

### What becomes a fact

| Shape | Key |
|---|---|
| `@if (a) { … }`, `@for (…)`, `@switch (…)`, `@defer`, `@let x = …`, `@else`, `@else if`, `@empty`, `@case`, `@placeholder`, `@error`, `@loading` | `syntax:angular-template#@if` … |
| `*ngFor`, `*ngIf`, `*ngSwitchCase`, … | `syntax:angular-template#*ngFor` |
| `{{ a in b }}`, `[x]="a as b"`, `(e)="typeof a"`, `@if (a in b)` | `syntax:angular-template#in`, `#as`, `#typeof` |
| `{{ value \| date:'short' }}`, `\| async` | `syntax:angular-template#pipe:date` |
| `@let` in a microsyntax (`*ngFor="let item of items"`) | `syntax:angular-template#let` |

The token list comes from `migration_keys/angular.py` (`ANGULAR_SYNTAX_TOKENS`), the same list 025
canonicalizes a rule entity with, so a rule and a fact meet on one key.

**Where a token must sit.** A block keyword counts when it carries block syntax — a
`(condition)` or a `{` body, or, for `@let`, a name and `=`. Text before it does not matter:
since Angular 17 an `@` before a block name always opens a block, so `Save @if (busy) {…}` and
the pluralization idiom `item@if (n > 1) {s}` are blocks, while `a@for.com` is not (no block
syntax follows). The content of an element with `ngNonBindable` is not compiled by Angular and
yields no tokens; the element's own attributes still do. Expression tokens only count **inside a binding**: `{{ … }}`,
`[prop]="…"`, `[(prop)]="…"`, `(event)="…"`, `*dir="…"`, the condition of a block keyword, and an
interpolation in any attribute (`title="{{ x | async }}"`). Plain text between tags is never an
expression, so:

- `The word in a sentence` → no `in`;
- `<p>the @defer block is new</p>` → no `@defer`;
- `{{ a || b }}` → no pipe (it is a logical or), and neither bar of `||` starts one;
- `[title]="'a in b'"` → no `in` (string literals are masked);
- `<!-- @defer *ngFor in -->` → nothing (comments are skipped whole).

**Locations.** `templates[]` follows the same bound as the other fact sections: `{key, count,
files, locations, truncated}`, one site per `(file, line)` — a location has no column (spec1
FR-1), so two `in` tokens on one line are one site — and at most `--max-locations` stored. The
`test` flag comes from the file: a `*.spec.html` or an inline template in a `src/test/**` /
`*.spec.ts` file is flagged `true`.

```bash
jq '.templates[] | {key, count}' .migration/profile.json
grep -rn "@defer\|\*ngFor" src --include=*.html | wc -l   # compare with the counts
```

## Maven and Gradle builds (026.6)

`migration_planner/scanner/maven.py` reads `pom.xml`, `migration_planner/scanner/gradle.py`
reads `build.gradle(.kts)`, `settings.gradle(.kts)`, `gradle/libs.versions.toml` and
`gradle.properties`. They answer the two questions a migration plan needs about a Java module:
**which Spring Boot version it builds against** (FR-3) and **what its build declares** (FR-8).

**No build is executed.** Maven is read with `xml.etree` (namespaces stripped, external entities
never resolved); Gradle with a tolerant lexer for the forms build scripts really use. A build
script is a program and a lexer cannot read a program, so a construct it does not understand is
skipped — and a *dependency-looking* line it cannot parse is reported as `unparsed_gradle`
instead of disappearing (FR-8).

### The Spring Boot version (FR-3)

The first source that applies, in this order:

| # | Where | `source` |
|---|---|---|
| 1 | Maven `<parent>` `org.springframework.boot:spring-boot-starter-parent` | `<pom>#parent` |
| 2 | Maven BOM import `org.springframework.boot:spring-boot-dependencies` in `<dependencyManagement>` | `<pom>#dependencyManagement` |
| 3 | Gradle plugin `id 'org.springframework.boot' version 'X'` (or `id("…") version "…"`, or `alias(libs.plugins.spring.boot)`) | `<file>#plugins` / `#catalog` |
| 3a | …applied without a version (`apply plugin:`), its version from a `buildscript` `classpath "org.springframework.boot:spring-boot-gradle-plugin:X"` | `<file>#buildscript` |
| 4 | Gradle `platform("org.springframework.boot:spring-boot-dependencies:X")` | `<file>#platform` |

A child module with no declaration of its own inherits its in-repo parent's: the Maven parent
chain is followed, and a Gradle subproject gets the version its root project declares — in
`pluginManagement { plugins { … } }` or in a root `plugins` block with `apply false`, which is
exactly what that idiom is for — or on the root's `buildscript` classpath, the classic
pre-`plugins {}` layout, whose `ext { springBootVersion = … }` the subproject sees too. `source`
always names the script that declares the version, not the one that applies the plugin. `apply false` gives the *subprojects* a version; it does not put
the root project on Spring Boot, so the root module's `frameworks[]` stays empty.

The result is `modules[].frameworks[] = {name: "spring-boot", version, raw, source}`, and the
repo-level `framework` is the one found in most modules (026.1).

A source whose version does not resolve (`${boot.version}` set outside the repo, `version
"$bootV"` declared nowhere) does not stop the search, so a later source that does resolve wins.
When none does, the module is still on Spring Boot: the fact has an empty `version` and the text
as written in `raw` (the shape an unnormalizable Angular range has, 026.2), and the
`unresolved_variable` diagnostic says why. A Gradle plugin applied with no version anywhere in the
repo (`apply plugin: 'org.springframework.boot'` with no classpath entry) is the same: Spring
Boot, version unknown.

### Maven (FR-8)

- `<parent>`, `<dependencies>`, `<dependencyManagement>` (imported BOMs and managed entries) and
  `<build><plugins>` / `<pluginManagement>` become `dependencies[]` entries keyed
  `maven:<groupId>:<artifactId>` with `kind: parent | dependency | bom | plugin`. One entry per
  `(key, module, scope, kind)`, so the same artifact as a BOM import and as a dependency is two
  facts. A plugin with no `<groupId>` gets Maven's default `org.apache.maven.plugins`.
- `${prop}` is resolved from the pom's own `<properties>` over its in-repo parents', plus
  Maven's implicit `project.version` / `project.parent.version` / … Maven assembles the
  inherited model first and interpolates the result, so a `${project.version}` written in a
  parent's `<properties>` means the version of the module being built — the child's own, when it
  declares one. `groupId` and `artifactId` are interpolated too (`${project.groupId}` for a
  sibling module). An unresolvable `${x}` keeps its raw text, is **not** reported as a `version`,
  and becomes one `unresolved_variable` diagnostic at the line that mentions it.
- `<properties>` entries become `cfg:pom.xml#properties.<name>` (`properties.java.version`), for
  the pom and for every module that inherits it — a rule about `java.version` applies to a child
  that inherits the value just as much as to the parent that writes it. `file` names the pom
  that declares it.
- `<modules>` are followed. Discovery already makes every directory with a `pom.xml` a module
  root, so this only adds a declared module that has no manifest of its own.
- The parent is found from `<parent><relativePath>` (default `../pom.xml`; a directory means its
  `pom.xml`), else the nearest ancestor pom with matching coordinates. Both stay inside the scan
  root: scanning `svc/` of a multi-module checkout does not read `../pom.xml`. A parent **outside** the repo is coordinates only: the
  scan never reads above the scan root and never touches `~/.m2`, because the version it declares
  is the fact that matters.

### Gradle (FR-8)

| Form | Fact |
|---|---|
| `id 'x' version 'v'` / `id("x") version "v"` / `id("x").version("v")` | `gradle-plugin:x`, `kind: plugin` |
| `apply plugin: 'x'` | `gradle-plugin:x` |
| `alias(libs.plugins.x)` | `gradle-plugin:<catalog id>`, version from the catalog |
| `implementation 'g:a:v'` / `"g:a"` | `maven:g:a`, `scope: implementation` |
| `implementation group: 'g', name: 'a', version: 'v'` | same, map notation (Groovy / Kotlin) |
| `platform(…)` / `enforcedPlatform(…)` | the same key with `kind: bom` |
| `implementation(libs.spring.boot.starter.web)` | catalog accessor, `version.ref` resolved |
| `implementation(libs.bundles.web)` | every library of the bundle |
| `implementation(kotlin("stdlib"))` | `maven:org.jetbrains.kotlin:kotlin-stdlib` |
| `implementation 'g:a:1', 'g:b:2'` | one fact per coordinate (Groovy varargs) |
| `dependencyManagement { imports { mavenBom 'g:a:v' } }` | `kind: bom` (the Spring plugin's syntax) |
| `implementation project(':core')`, `files(…)`, `gradleApi()` | nothing: not external coordinates |

- Any configuration name is a `scope` (`implementation`, `api`, `compileOnly`, `runtimeOnly`,
  `testImplementation`, `annotationProcessor`, …), and `buildscript`'s `classpath` is
  `buildscript:classpath` — the build's own classpath, not a dependency of the module.
- Variables resolve from `ext { … }` (wherever it is written, `buildscript` included),
  `ext { set('x', '…') }` (what Spring Initializr writes), `ext.x = '…'` / `project.ext.x`,
  `ext.set(…)`, `extra["…"]`, a Kotlin top-level `val x = "…"`, `gradle.properties` of the repo
  root and of the module (the module's own wins), and `pluginManagement` versions. An unresolved `$var` / `${var}` keeps its raw text
  and becomes one `unresolved_variable` diagnostic per name and file.
- `gradle/libs.versions.toml` is parsed with `tomllib`; `version.ref` is resolved, and a
  subproject without its own catalog reads the Gradle root project's. A `[plugins]` entry in
  string notation is `"<id>:<version>"`. A broken catalog is a `version_catalog_parse_error`
  diagnostic; an accessor the catalog does not declare (library, bundle or plugin) and a
  `version.ref` to a missing `[versions]` entry are `unresolved_catalog_entry`.
- `java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }`, `jvmToolchain(21)` and
  `sourceCompatibility` / `targetCompatibility` become
  `cfg:build.gradle#java.toolchain.languageVersion` and `cfg:build.gradle#sourceCompatibility`.
  The key always names `build.gradle` or `build.gradle.kts` (the two names 025 / 027 know), while
  `config[].file` keeps the real subproject path.
- `settings.gradle(.kts)` `include(…)` declares module roots, which the scan folds into
  `modules[]` (a declared module with no manifest of its own is listed too).
- Declared **external groupIds** are kept per module and handed to source extractors as
  `ModuleEnv.group_ids`, so spec7 can recognize a fully qualified `org.x.Y.z()` usage that has no
  import. The repo's own groupIds — Maven `<groupId>` of every module and in-repo parent, Gradle
  `group = …` (top level, `allprojects`, `subprojects`) — are `own_group_ids` and are removed
  repo-wide, so a dependency on a sibling (`com.acme:lib`) never makes `com.acme.…` look external.
  A groupId inherited from an *external* parent (the starter parent) is not owned. The trade-off:
  an external artifact that shares the repo's exact groupId (another `com.acme` repo) is treated
  as own code too.

```bash
migration-scan /path/to/spring-service
jq '.framework, [.dependencies[] | {key, version, kind}]' .migration/profile.json
mvn help:effective-pom -q | grep -A2 spring-boot-starter-parent   # compare the version
```

## Java sources (026.7)

`migration_planner/scanner/java.py` parses `*.java` with **tree-sitter-java** and records the
external imports and where they are used. It is a pure function of the file's bytes, like the
TypeScript extractor, so spec9 can cache it and run it in a process pool.

### What is recorded

| Form | Fact |
|---|---|
| `import a.b.C;` | `maven:a.b.C` in `symbols[]`, at the import line |
| `import a.b.C.Inner;` | `maven:a.b.C.Inner` (a nested type keeps its dots) |
| `import static a.b.C.m;` | `maven:a.b.C.m` in `members[]` |
| `import static a.b.Outer.Inner;` (a nested type: capital first letter and a lower-case letter) | `maven:a.b.Outer.Inner` in `symbols[]`, at the import line and every use |
| `import a.b.*;` | `maven:a.b.*` in `wildcard_imports[]`, plus `names` |
| `import static a.b.C.*;` | `maven:a.b.C.*` in `wildcard_imports[]`, plus `names` |
| type in any position — field, parameter, `extends`, `implements`, generic argument, `new C(…)`, cast, `instanceof`, `throws`, `C.class`, `C::new` | `maven:a.b.C` in `symbols[]` at the use site |
| `@C` / `@C(attr = …)` | the annotation as a symbol, and `maven:a.b.C.attr` per attribute |
| `@C("x")` | `maven:a.b.C.value` (the single-value shorthand) |
| `@C(attr = …)` where only `import a.b.*;` can supply `C` | `maven:a.b.C.attr` per attribute, under every class wildcard of the file (see below) |
| `C.m(…)`, `C.FIELD` | `maven:a.b.C.m` / `maven:a.b.C.FIELD` in `members[]` |
| a statically imported name used bare (`assertEquals(…)`) | the member, at the use site |
| `org.x.Y.z()`, `@org.x.Ann`, `org.x.Y` with **no import** | `maven:org.x.Y` and `maven:org.x.Y.z`, when the name starts with a groupId the repo's builds declare (026.6) **or its parent groupId** |

**Parent groupIds.** A Spring Boot service usually declares only `org.springframework.boot`
starters, yet its code names `org.springframework.util.Assert` (`spring-core`, a transitive
dependency). So the parent of every declared groupId counts too (`org.springframework.boot` →
`org.springframework`, `com.fasterxml.jackson.core` → `com.fasterxml.jackson`), with two limits: a
parent needs at least two segments (`io.micrometer` does not make every `io.…` name external),
and a parent that is, contains or lies under one of the repo's own groupIds is left out, so a
dependency on `com.acme.platform` never makes the repo's `com.acme.shop` code external. The
groupIds themselves (`ModuleEnv.group_ids`) are unchanged; the scan also hands the extractor
`ModuleEnv.own_group_ids` for the second limit.

Comments inside a name (`import org.x /* … */ .Y;`) are not part of the key, and the `static`
keyword is read from the parse tree, so `import statics.Foo;` is a class import.

A chain records the **first segment after the class**, exactly as the TypeScript extractor does,
so `RequestMethod.GET.name()` is `maven:…RequestMethod.GET` — the enum constant — and not a
member of it.

A call on a variable is **not** resolved (spec1 Non-Goals): `entity.getStatusCode()` on a local
is not attributed to `ResponseEntity`, and `this` / `super` are not owners. The symbol entry's
`locations` are the files a matcher must search for such a call, which is why the import site is
recorded as well as each type use.

### Own packages, and what a wildcard supplies

Every `package x.y;` in the scanned sources is an **own package**, so an import of one — or of
anything under one, matched segment by segment, so `com.acme.shop` owns
`com.acme.shop.web.Controller` but not `com.acme.shopping.Cart` — is the repo's own code in
another module, not an external library. The extractor records it like any other import and the
**own-package post-pass** removes it once the whole set is known (one file cannot know its
siblings' packages).

A wildcard import names no class, so its entry lists the simple names the file uses that nothing
else explains:

```json
{ "key": "maven:java.util.*", "count": 12, "files": 3,
  "names": ["ArrayList", "HashMap", "List", "Map"], "locations": ["…"] }
```

A matcher tests `java.util.Map` against `names`. What is **not** in it: a name the file declares
itself (`record Report(…)`), a name another import already binds, a `java.lang` type (imported
implicitly), and a name that is not capitalized — `list.add(x)` is a call on a variable, and the
Java convention of a capitalized type name is the only signal a scanner has without a classpath.
Names are unioned across the files that share one wildcard import, because the profile has one
entry per key.

The post-pass also drops a name an **own wildcard** supplies: with `import com.acme.shop.service.*;`
next to `import org.springframework.web.bind.annotation.*;`, a `Widget` declared in
`com.acme.shop.service` is not listed under Spring's entry.

**Annotation attributes under a wildcard.** `@RequestMapping(method = …)` with only
`import org.springframework.web.bind.annotation.*;` has no FQCN, but its attributes are what a
rule names, so each attribute is a member under every class wildcard of the file
(`maven:org.springframework.web.bind.annotation.RequestMapping.method`) — the same policy as
`names`: two wildcard packages both get it, because without a classpath the scanner cannot tell
which declares the annotation. The annotation itself stays a name under the wildcard entry, not a
symbol. The post-pass drops an attribute whose annotation an own package supplies, unless the
file also imports that class explicitly. A qualified call `C.m()` on a wildcard-supplied `C` is
still not a member: only its name is under the wildcard.

### Tests and errors

- `src/test/java/**` and `src/<name>Test/java/**` (`integrationTest`, `componentTest`,
  `acceptanceTest`, `apiTest`, …) and Maven's `src/it/java/**` locations carry `test: true`, like
  every other spec's.
- A partial parse keeps every fact that did parse and adds one `partial_parse_error` with the
  line of the first error; a file where nothing parses is one `parse_error`. Neither fails a scan
  (AC-5.4).

```bash
migration-scan /path/to/spring-service --force
jq '[.symbols[] | select(.key | startswith("maven:org.springframework"))] | length' .migration/profile.json
jq '.members[] | select(.key | test("RequestMapping"))' .migration/profile.json
grep -rn "^import org.springframework" src/main/java | shuf -n 10   # spot-check against the profile
```

## Spring configuration (026.8)

`migration_planner/scanner/spring_config.py` turns every `application*` / `bootstrap*` file of a
Java module into `config[]` facts. A module is Java when it has a `pom.xml` / `build.gradle(.kts)`,
or when the repo has one somewhere and the module is `.` or not an npm package — so a shared
`config/application.yml` at the root is read even next to a tooling `package.json`, while an
Angular module's `application.yml` is not. Many Spring Boot rules are property renames or default
changes (`spring.data.mongodb.*` → `spring.mongodb.*`), so *which properties the service sets* is
part of its profile.

### What becomes a fact

One entry per occurrence, never merged by key:

```json
{ "key": "cfg:application.properties#spring.data.mongodb.authentication-database",
  "value": "admin", "file": "src/main/resources/application-prod.yml",
  "module": ".", "profile": "prod", "kind": "application", "test": false,
  "line": 7, "raw_key": "spring.data.mongodb.authenticationDatabase" }
```

| Field | Meaning |
|---|---|
| `key` | The canonical form under the **one file name rules use**, `cfg:application.properties#…`, whichever file really holds it (025 FR-2.6). |
| `file` | The real path, so a matcher can say "set only in `src/test`". |
| `profile` | From the file name (`application-prod.yml` → `prod`, else `default`), or from a document's `spring.config.activate.on-profile` / legacy `spring.profiles` (also `spring.profiles[0]`), matched in canonical form so `onProfile` counts. `spring.profiles.active` does **not** change the profile: it activates one, and its document is still the default one. |
| `kind` | `application` or `bootstrap`. |
| `test` | `true` under `src/test/`, Maven's `src/it/`, or a test source set `src/<name>Test/` (`src/integrationTest/resources`). |
| `line` | The line the key is written on (a YAML key's own mark, not its document's). |
| `raw_key` | The written form when canonicalization changed it. |

The same key in two profiles, modules or files is **two entries**: `spring.datasource.url` in
`application-prod.yml` and in `src/test/resources/application.yml` are different facts, and a
matcher can tell "set only in test" from "set in production".

`modules[].spring_config_files` lists every such file of the module, `bootstrap*` included —
some rules are about the file's presence (a `bootstrap.yml` needs
`spring-cloud-starter-bootstrap` since Spring Boot 2.4).

### Parsing

- **`.properties`** — Java's format, with its own small parser: `=`, `:` or whitespace
  separators, `#` / `!` comments, `\` line continuation and `\uXXXX` escapes. A comment line
  never continues, even when it ends in `\`. `#---` / `!---` on its own line (no leading
  whitespace) splits the file into documents, as `---` does in YAML (Boot 2.4+). A line with no
  key at all is an `unparsed_property` diagnostic rather than a silent drop.
- **`.yml` / `.yaml`** — PyYAML's `compose` step, because the marks are what the profile needs:
  `line` is the key's real line. Nested maps flatten to `a.b.c`, lists to `key[0].sub`, anchors
  and `<<` merge keys are applied (a key written in the document wins), multi-document files are
  one document per `---`, and an empty map or list is a key with an empty value. An unparsable
  file is one `yaml_parse_error` and the module's other files are still read.

### Canonical keys (Spring relaxed binding)

Property-name segments become lower-case kebab-case:

| Written | Canonical |
|---|---|
| `spring.data.mongodb.authenticationDatabase` | `spring.data.mongodb.authentication-database` |
| `server.SERVER_PORT` | `server.server-port` |
| `logging.level.com.Foo.BarService` | unchanged — `logging.level` is a **map prefix**, so what follows is a logger name |
| `spring.jpa.properties.hibernate.dialect` | unchanged (`spring.jpa.properties.*`) |
| `management.metrics.tags.Application` | unchanged (`management.metrics.tags.*`) |
| `spring.cloud.gateway.routes[0].metadata.Connect-Timeout` | unchanged (`…routes[*].metadata.*`) |

The map-prefix list is `SPRING_MAP_PREFIXES` in `migration_keys/spring.py`, next to
`canonical_key`, `is_secret_key` and `redact_value` — the same module 025 imports: 025's Spring
Boot normalizer builds a property's key with `canonical_key` too (the entity's `name` stays as
written), so a rule written `authenticationDatabase` and a service setting
`authentication-database` meet on one key.

### Secrets never reach the profile

| Case | Stored |
|---|---|
| The key's last segment names a credential (`password`, `passwd`, `secret`, `token`, `credential`, `api-key`, `apikey`, `private-key`, `client-secret`, …) | `"<redacted>"` |
| The value contains a URL with user info (`jdbc:postgresql://user:pass@host/db`) | `"<redacted>"` |
| The value is a placeholder (`${DB_PASSWORD}`, `${PORT:8080}`) | kept exactly as written — a reference, never resolved |
| Anything else | the scalar, truncated to 200 characters |
| `--no-values` | `null`, in every `config[]` entry of every reader |

A suffix is not a token: `app.tokens-per-second` is not a secret. A secret word followed by a
qualifier that makes the key a setting *about* the secret is not a secret either:
`token-uri`, `access-token-validity-seconds`, `secret-header-name` keep their value
(`NON_SECRET_SUFFIXES`), while `hmac-secret-key` stays redacted. Lists and maps are recorded as
keys only. `--no-values` is applied by the profile accumulator, not by one reader, so it covers
npm and Maven values too, and it is part of `inputs_hash`.

```bash
migration-scan /path/to/spring-service --force
jq '[.config[] | select(.key | startswith("cfg:application.properties#"))] | length' .migration/profile.json
jq '.config[] | select(.value == "<redacted>") | .key' .migration/profile.json
grep -c "<known secret>" .migration/profile.json   # → 0
```

The AC-11 result on a real service (timings, size, the 153/153 property-key check, the secret
check, the 10 import sites) is in `specs/026-service-scanner/ac11-spring.md`.

## Canonical keys

The profile uses the same key formats as the graph (spec 025), so the matcher compares sets
without translation:

| Kind | Key |
|---|---|
| npm class | `npm:<package>#<symbol>` |
| npm member | `npm:<package>#<symbol>.<member>` |
| npm dependency | `npm:<package>` |
| Maven class | `maven:<FQCN>` |
| Maven dependency | `maven:<groupId>:<artifactId>` |
| Gradle plugin | `gradle-plugin:<plugin id>` |
| config key | `cfg:<file>#<dotted key>` |
| template syntax | `syntax:<framework>-template#<token>` |

The builders live in `migration_keys/`, a dependency-free package imported by both ingestion and
the planner. The Angular entry-point, template-token and config-prefix lists live there too, so
the two sides cannot drift.

## Extractor contract

Each later 026 spec adds one module and registers it in `builtin.py`; the scan loop never
changes.

- **Manifest readers** receive a module root, its manifest files and the scan root, and return
  `dependencies`, `config`, `frameworks`, `diagnostics`, plus what source extractors need:
  `own_packages` (own-code names), `path_map` (the effective tsconfig import map), `module_roots`
  (Maven `<modules>` / Gradle `include`), and `group_ids` (Maven groupIds, for spec7's
  fully-qualified usages). One reader registered for several manifest kinds runs once per module
  with all of them — which is how one Gradle reader handles the build script, the settings
  script, the version catalog and `gradle.properties` together. A reader may also return
  `spring_config_files` (026.8), the module's `application*` / `bootstrap*` files.
- **Source extractors** receive one file (path, bytes, module, `test` flag, and the module's
  `ModuleEnv`, which now also carries `group_ids`) and return per-file facts. They are pure
  functions of the file content, so spec9 can cache them and run them in a process pool.
- **Post-passes** receive the collected per-file facts plus how imports resolve
  (`PostPassContext` / `ResolutionEnv`). A post-pass may **return** a `FileFacts` fragment, which
  the scan merges like any extractor's output, or **replace entries in `context.files`** to drop
  some. Barrel resolution is the first kind (spec4); own-package filtering is the second (spec7),
  and the scan merges every file's facts only *after* the post-passes, so a removed fact never
  reaches the profile. A post-pass that raises is a `post_pass_error` diagnostic, never a failed
  scan.

See `migration_planner/scanner/contract.py` and `migration_planner/scanner/builtin.py`.

## Package layout and isolation

```text
migration_planner/            planner: runs in a service repo
  scanner/
    cli.py                    migration-scan
    discover.py               file discovery, classification, module roots
    npm_manifests.py          package.json / lock / angular.json / tsconfig (026.2)
    maven.py                  pom.xml: parent / BOM / dependencies, Spring Boot (026.6)
    gradle.py                 build / settings / catalog / properties, Spring Boot (026.6)
    ts.py                     TS / JS imports, members, decorators (026.3)
    ts_resolve.py             barrels, aliases, workspace entry points (026.4)
    templates.py              Angular template tokens, .html + inline (026.5)
    java.py                   Java imports, usages, wildcards, own packages (026.7)
    spring_config.py          application*/bootstrap* → config keys, secrets (026.8)
    profile.py                pydantic profile model, merge, atomic writer
    scan.py                   the one scan loop
    contract.py               extractor contract + registry
    builtin.py                the readers / extractors this package ships
migration_keys/               pure key builders + Angular data (shared with ingestion)
  keys.py
  angular.py
  spring.py                   Spring canonical form, map prefixes, redaction
  specifiers.py               package-of-specifier and own-code rules
```

`tests/scanner/test_isolation.py` guards the split: it fails if anything under `migration_planner/`
or `migration_keys/` imports `migration_oracle`, `neo4j`, `langchain*`, `httpx` or `socket`, and
it runs a scan with no `NEO4J_URI`, no `.env` and sockets blocked.

## Verifying a scan

```bash
migration-scan /path/to/angular-service
jq '.framework, (.dependencies | length), [.config[].key] | unique' .migration/profile.json
migration-scan /tmp/empty-dir; echo $?    # → 2
```

Expected on an Angular service after 026.3: `angular <version>` in the summary line, every
declared npm dependency with its lockfile version,
`cfg:angular.json#projects.*.architect.build.builder` among the config keys, and `symbols[]` /
`members[]` filled from the TypeScript sources. Compare `framework.version` with
`npm ls @angular/core`, and a `symbols[]` entry with `grep -rn "from '@angular/core'" src`.

After 026.5 `templates[]` is filled too: compare one `@defer` / `*ngFor` count with
`grep -rn "@defer\|\*ngFor" src --include=*.html`, and one `pipe:` key with
`grep -rn "| date" src`.

After 026.6 a Spring service also reports `spring-boot <version>`: compare it with
`mvn help:effective-pom -q | grep -A2 spring-boot-starter-parent` (or
`./gradlew dependencies`), and one `dependencies[]` entry with the coordinate in the build
file.

After 026.7 the Java sources are read too. `symbols[]` and `members[]` hold the external imports
and their usages, and `wildcard_imports[]` holds `import a.b.*` with the simple names it may
supply. Compare an import with `grep -rn "^import org.springframework" src/main/java`, and check
that no key starts `maven:` with the service's own package — those are filtered:

```bash
jq '[.symbols[] | select(.key | startswith("maven:org.springframework"))] | length' .migration/profile.json
jq '.wildcard_imports | map({key, names})' .migration/profile.json
jq '[.symbols[], .members[] | select(.key | startswith("maven:com.acme"))] | length' .migration/profile.json  # → 0
```

After 026.8 `config[]` holds the Spring properties too. Compare a key with the service's own
file, and check that a credential is redacted:

```bash
jq '[.config[] | select(.key | startswith("cfg:application.properties#"))] | length' .migration/profile.json
jq -r '.config[] | select(.value == "<redacted>") | .key' .migration/profile.json
jq -r '.modules[].spring_config_files[]' .migration/profile.json
grep -rn "spring.datasource.url" src/main/resources/application*.yml   # the key must be in the profile
```

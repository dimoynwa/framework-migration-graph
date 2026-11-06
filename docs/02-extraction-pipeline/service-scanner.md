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
| `--no-include-tests` | — | Drop `*.spec.ts`, `*.test.ts`, `src/test/**` at discovery. |
| `--json-summary` | off | Print the summary as one JSON object instead of the line. |
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
  "wildcard_imports": [],
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
| `framework`, `modules[].frameworks` | **026.2** (Angular), spec6 (Spring Boot) |
| `modules[].angular_projects`, `modules[].own_packages`, npm `dependencies`, npm / angular / tsconfig `config` | **026.2** |
| `symbols`, `members`, `side_effect_imports` (TS/JS) | **026.3**, barrel-resolved keys **026.4** |
| `templates` | **026.5** |
| Maven / Gradle `dependencies`, `cfg:pom.xml` / `cfg:build.gradle` `config` | spec6 |
| `symbols`, `members`, `wildcard_imports` (Java) | spec7 |
| Spring `config`, `modules[].spring_config_files` | spec8 |
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
  artifact are two entries.
- `config[]` has one entry per occurrence `(key, module, file, profile, line)`: the same key in
  two modules, files or Spring profiles is two entries. `line`, `raw_key`, `profile`, `kind` are
  filled by the Spring config reader (spec8) and `null` elsewhere.
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

## Canonical keys

The profile uses the same key formats as the graph (spec 025), so the matcher compares sets
without translation:

| Kind | Key |
|---|---|
| npm class | `npm:<package>#<symbol>` |
| npm member | `npm:<package>#<symbol>.<member>` |
| npm dependency | `npm:<package>` |
| Maven class | `maven:<FQCN>` |
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
  `own_packages` (own-code names) and `path_map` (the effective tsconfig import map). One reader
  registered for several manifest kinds runs once per module with all of them.
- **Source extractors** receive one file (path, bytes, module, `test` flag, and the module's
  `ModuleEnv`) and return per-file facts. They are pure functions of the file content, so spec9
  can cache them and run them in a process pool.
- **Post-passes** receive the collected per-file facts plus how imports resolve
  (`PostPassContext` / `ResolutionEnv`) and return a `FileFacts` fragment, which the scan merges
  like any extractor's output. Barrel resolution is one (spec4); own-package filtering in spec7
  is the next. A post-pass that raises is a `post_pass_error` diagnostic, never a failed scan.

See `migration_planner/scanner/contract.py` and `migration_planner/scanner/builtin.py`.

## Package layout and isolation

```text
migration_planner/            planner: runs in a service repo
  scanner/
    cli.py                    migration-scan
    discover.py               file discovery, classification, module roots
    npm_manifests.py          package.json / lock / angular.json / tsconfig (026.2)
    ts.py                     TS / JS imports, members, decorators (026.3)
    ts_resolve.py             barrels, aliases, workspace entry points (026.4)
    templates.py              Angular template tokens, .html + inline (026.5)
    profile.py                pydantic profile model, merge, atomic writer
    scan.py                   the one scan loop
    contract.py               extractor contract + registry
    builtin.py                the readers / extractors this package ships
migration_keys/               pure key builders + Angular data (shared with ingestion)
  keys.py
  angular.py
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
`grep -rn "| date" src`. Java facts stay empty until specs 6–8.

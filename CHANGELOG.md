# Changelog

## [026.4-service-scanner] — 2026-11-06

### New features

- **Barrels and aliases resolve to the external package (FR-5).** `migration_planner/scanner/ts_resolve.py` is the post-pass spec4 promised: it takes the own-code imports spec3 collected, follows them through barrels, `paths` aliases, `baseUrl` and workspace packages, and records the external key **at the original import site** — `import { inject } from '@app/core'` with `core/index.ts → export { inject } from '@angular/core'` gives `npm:@angular/core#inject` at the importing file, which is the line a matcher must search.
- **Chains are followed, not guessed.** `export { X } from '…'`, `export { X as Y } from '…'` (renames applied along the chain), `export * from '…'` and `export * as ns from '…'`. A name that ends in a local declaration is own code and is dropped silently; an `export *` of a package cannot be enumerated, so a name that reaches it belongs to that package.
- **Specifier → file.** Relative paths, `compilerOptions.paths` (longest pattern, targets in order, first existing wins), `baseUrl`, and workspace package names via their `package.json` `exports["."]` / `types` / `module` / `main`, else `index.*`. Every candidate is probed with `.ts`, `.tsx`, `.d.ts`, `.js`, `.jsx`, `.mjs`, `.cjs` and `/index.*`; a `.js` specifier also finds its `.ts` source (`NodeNext`).
- **Members follow the chain too.** `di.call(…)` after `export { inject as di }` becomes `npm:@angular/core#inject.call`; `core.inject(…)` and `@core.Component({ selector })` on a barrel namespace resolve per member. Own-code member accesses are now kept by spec3 (`FileFacts.own_member_bindings`, `OwnMember`) for this pass.
- **New contract seam for post-passes.** `PostPassContext` / `ResolutionEnv` / `OwnPackage` and a `PostPass` that returns a `FileFacts` fragment; `scan()` merges it like any extractor's output. The npm reader now reports each own package's directory and entry points (`ManifestFacts.own_package_sources`), which is what makes a workspace-package import resolvable.
- **Bounded, never silent.** A cycle gives `barrel_cycle`, a chain deeper than 10 gives `barrel_depth` (AC-2.3: depth 11), an own import with no file gives `unresolved_import`. An asset specifier (`./x.scss`, `./data.json`) is not a module and is skipped without a diagnostic. Results are memoized per `(file, exported name)`.

### Fixes

- **A give-up must not poison the memo.** Only a definitive resolution is cached: a `barrel_depth`/`barrel_cycle` result is a property of one entry point, so caching it would deny a shorter chain the same name. Covered by `test_a_short_chain_still_resolves_after_a_deep_one_gave_up`.
- **The same cycle was reported once per importer.** `barrel_cycle` / `barrel_depth` now dedupe per `(kind, file)`; the chains differ per entry point and a reader only needs the file.

### Fixes (review 2026-11-06)

- **Only the first own `export *` was searched.** A barrel with `export * from './a'; export * from './b'` (the Angular `public-api.ts` shape) stopped at `a` when it lacked the name, so everything behind `b` was lost. A file that does not export a name is now "not found" and the search moves on.
- **`import { X } from 'pkg'; export { X }` was treated as own code.** The export is now linked to its import and followed (a re-exported `import * as ns` becomes a namespace export).
- **A `paths` alias into `node_modules` dropped every import through it.** `"@angular/*": ["./node_modules/@angular/*"]` made `@angular/core` own code, so `Component`, `inject`, … vanished behind `unresolved_import`. Such aliases are redirects to an external package now (`migration_keys.specifiers.own_path_aliases`).
- **Several external `export *` attributed a name to the first one** (`map` → `npm:@angular/core#map`). With one external star the name is still attributed; with several it is reported as `ambiguous_export` and not recorded.
- **A `const` inside a function body shadowed `export *` names.** `local_declarations` now holds module-scope declarations only.
- **Inline `type` through a barrel** (`import { type Signal } from '@app/core'`) keeps `type_only` per name (`OwnImport.type_names`).
- **Workspace subpath exports** (`@demo/ui/testing` → `exports["./testing"]`, `"./*"` patterns) resolve (`OwnPackage.subpath_exports`).
- **`export * as rx from 'rxjs'`** re-exported through a barrel: `rx.filter()` gives `npm:rxjs#filter` at the access (was nothing).
- **A bundler query** (`./worker?worker`) no longer gives a false `unresolved_import`.
- Removed an unused `typing.Any` import in `contract.py`.

### Tests

- `tests/scanner/test_ts_resolve.py` (60 tests): AC-2 (the key at the import site, cycle → diagnostic, no crash), AC-2.2 (`export *`, rename chain, namespace import of a barrel, workspace package, `paths` alias with `*`, namespaced re-export, every probed extension, `.js` → `.ts`), AC-2.3 (local declaration dropped, depth 10 vs 11), the diagnostics, memoization, and the seam between spec3 and spec4.
- New fixture `tests/fixtures/scanner/ts-barrels/` with a core barrel, a barrel of a barrel, an `export *`, a rename, a namespace barrel import, a cycle, a 10/11-deep chain, a workspace package with an `exports` map and a `paths` alias with two targets.
- `tests/fixtures/scanner/ts-imports/` gained the targets its own imports name (`src/local.ts`, `src/app/shared.ts`, `packages/ui/`) and an `@demo/ui` `main`/`types`, so the spec3 fixture has no genuinely unresolved import.
- Whole scanner suite plus the 025 shared-key / canonicalization tests pass unchanged: 337 passed in `tests/scanner`, 73 passed in the 025 key and canonicalization files — 410 passed, no spec1 / spec2 / spec3 regressions.

## [026.3-service-scanner] — 2026-11-06

### New features

- **TypeScript / JavaScript extraction.** `migration_planner/scanner/ts.py` parses `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` and `.cjs` with **tree-sitter** and fills `symbols[]`, `members[]` and `side_effect_imports[]`. Every FR-5 import form is handled: named, aliased (`B as C` keeps `npm:pkg#B`), default (`#default`), namespace, side-effect, `import type` and inline `type` (`type_only`), `export … from`, `export *`, `import('pkg')` / `require('pkg')` including destructuring, and `import x = require('pkg')`. The extractor is a pure function of the file's bytes, so spec9 can cache it and run it in a process pool.
- **Members.** `Local.member` for every identifier bound to an external import, first segment only (`A.b.c` → `A.b`). A namespace import resolves per name (`core.inject(…)` → `npm:@angular/core#inject`). A local declaration that shadows the name stops tracking in that scope — a parameter named `TestBed` is not the imported `TestBed`.
- **Decorators.** Every literal key of a decorator's first object argument is a member (`npm:@angular/core#Component.standalone`, `….changeDetection`). Angular rules are mostly about these options.
- **`migration_keys/specifiers.py`.** The import-specifier rules both sides need: `package_of_specifier` (`@angular/core/testing` is its own package, `rxjs/internal/x` and `lodash/fp.js` kept as written), `dependency_name`, `is_own_code` (relative, paths alias, workspace package), `is_node_builtin`, and `resolve_path_alias` for spec4. Pure string handling, no file system, no `migration_oracle`.
- **Spec4 inputs are already collected.** `FileFacts` gains typed `ExportBinding`, `OwnImport`, `star_exports`, `namespace_exports`, `local_declarations` and `own_import_bindings`, replacing the untyped `export_map` dict — so spec4 can follow a barrel without re-parsing anything.
- **`builtin.py` registry.** The shipped readers and extractors live in one list and are installed when the scanner package is imported, so `migration-scan` needs no setup step while `reset_registry()` stays a working escape hatch.

### Fixes

- **`reset_registry()` could not empty the registry.** `scan()` re-installed the built-in readers and extractors on every call, so nothing could opt out of them. Installation is now an import-time effect of `builtin`, never something `scan()` does inside a scan.
- **A `const` that shadows an import was not detected.** `const TestBed = local(); TestBed.get(x)` was attributed to the imported `TestBed`, because only the declaration node was checked and not the block that scopes it. Block-scoped declarations are now checked per enclosing block.
- **`require('pkg')` bound to a name looked shadowed by its own declaration.** The declarator that *creates* an import binding is now excluded from the shadow check, which had been silently dropping `const m = require('pkg'); m.thing()`.
- **`await import('pkg')` recorded nothing.** The `await_expression` wrapper between the call and its `variable_declarator` stopped the declarator lookup, so the binding (and the package fact) was lost.

### Fixes (review 2026-11-06)

- **`baseUrl` imports were recorded as npm packages.** With `baseUrl: "./src"`, `'app/core/core.service'` gave `npm:app/core/core.service#CoreService`. The scan now hands extractors the entries directly under `baseUrl` (`ModuleEnv.base_url_roots`), and such specifiers are own code; a declared dependency of the same name still wins.
- **Declared npm packages named like Node builtins were dropped.** `events`, `buffer`, `util`, `url`, `process` … are external when the repo declares them (`ModuleEnv.declared_dependencies`); `node:` is always a builtin.
- **Decorators added symbol locations.** `@Input()` twice gave `Input` a count of 3 while `inject` called twice stayed at 1. `symbols[].locations` are import sites only again (spec1 FR-9); decorators contribute members.
- **`export * from '<external>'` recorded nothing.** It is now the package-level symbol `npm:<pkg>`.
- **Inline `import { type T, V }`** marks only `T` as `type_only` (was neither); all-`type` specifiers make the whole import type-only.
- **`import x = require('pkg')`** (TypeScript) is recorded, with member tracking on `x`.
- **Decorator options**: shorthand keys (`{ selector }`), method keys and namespaced decorators (`@core.Component({…})`) now become members.
- **Package-level uses moved to `symbols`.** `import('pkg')` / `require('pkg')` were in `side_effect_imports`; that section now holds only `import 'pkg'`.
- **Deep file imports are kept as written** (`lodash/fp.js` → `npm:lodash/fp.js#…`, was folded to `npm:lodash`), as FR-5 says.
- Removed the unused `ts.register()`; registration lives in `builtin.py`.

### Tests

- `tests/scanner/test_ts.py` (62 tests) covers AC-1 (every FR-5 form, own code skipped, entry points and deep imports), AC-3 (members through named / aliased / namespace bindings, first-segment rule, four shadowing shapes, decorator keys), AC-3.2 (all six grammars incl. tsx/jsx syntax), parse errors and AC-3.3 (`count` exact, `files: 30`, 5 locations, `truncated`, test flags).
- `tests/scanner/test_specifiers.py` (40 tests) covers the shared specifier rules.
- New fixture `tests/fixtures/scanner/ts-imports/` puts every import form in one file, with a workspace package and a paths alias for the own-code cases. Verified against a real 709-file Angular service: 0.8 s, 361 symbols, 152 members, 0 diagnostics, no alias leakage.
- Whole scanner suite and the 025 shared-key / canonicalization tests pass: 348 passed (`tests/scanner` 275, `test_shared_keys.py` 8, the four `test_canonical_*.py` files 65), no regressions in the spec1 / spec2 tests.

## [026.2-service-scanner] — 2026-11-06

### New features

- **npm manifests.** `migration_planner/scanner/npm_manifests.py` reads `package.json`, `package-lock.json`, `angular.json` and `tsconfig*.json` in one pass per module. All four dependency scopes (`dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies`) become `dependencies[]` entries with the range exactly as written and the **installed** version from the lockfile, so `npm:@angular/core` says `range: "^19.2.0"` and `version: "19.2.4"`. A module with no lockfile of its own reads the nearest one in a parent directory, which is how an npm workspace is installed.
- **Config keys.** `package.json` `engines.*`, `type`, `browserslist`, `overrides.*`, `resolutions.*` and `workspaces` become `cfg:package.json#<dotted path>`, lists keeping their index. Every scalar leaf of `angular.json` becomes a key with the project name replaced by `*` — `cfg:angular.json#projects.*.architect.build.builder` — so one rule matches a repo with any number of projects, while the real names go to a new `modules[].angular_projects`. `tsconfig*.json` accepts comments and trailing commas, follows `extends` inside the repo, and emits `cfg:tsconfig.json#compilerOptions.*` / `angularCompilerOptions.*` from the **effective** config.
- **Angular version (FR-3).** `package-lock.json` beats the `package.json` range: the framework version is what the build installs, not what the manifest wishes for. With no lockfile the range is kept as `raw` and normalized to the **lowest** version it allows (`^19.2.0` → `19.2.0`, `~1.4` → `1.4.0`, `>=18` → `18.0.0`, `19.x` → `19.0.0`, a `||` union → its lowest alternative). `*`, `latest`, `workspace:*` and `file:` carry no floor and stay `null` without a diagnostic; anything else is `unsupported_range`.
- **Own packages.** A module's `package.json` `name` and its npm workspace package names are recorded in a new `modules[].own_packages` (per module) and handed to source extractors, as a repo-wide union, through the new `ModuleEnv`. That is the input spec3 needs to skip imports of the service's own code instead of recording them as external.
- **Effective path map.** `compilerOptions.paths` and `baseUrl` are resolved across `extends` into a `PathMap` on the module — `paths` as written, `paths_dir` the directory they are relative to (`baseUrl` when set, else the config file that declared them, which is TypeScript's own rule) — for import resolution in spec3 / spec4.
- **`builtin.py`.** The readers and extractors this package ships live in one registry list, so the scan loop still knows nothing about npm, Maven or Angular and a later spec only adds an entry.

### Fixes

- A `tsconfig` cycle or an `extends` pointing at `node_modules` used to be unresolvable; both are now diagnostics (`tsconfig_cycle`, `tsconfig_extends_outside_repo`) and the scan continues.
- A `package.json` dependency whose value is not a string is a diagnostic (`invalid_dependency`) instead of a silently missing entry.

### Fixes (review 2026-11-06)

- **A hoisted `@angular/core` made every workspace package Angular.** A module is now Angular only when its `package.json` declares `@angular/core`; the lockfile supplies the exact version.
- **A nested workspace root's lockfile was not found.** A module without its own `package-lock.json` now uses the nearest one in a parent directory up to the scan root (`frontend/package-lock.json` for `frontend/packages/ui`), not only the scan root's.
- **A `package-lock.json` over 2 MB was skipped**, so versions fell back to range floors. Manifests now have a 50 MB cap; the 2 MB cap applies to sources.
- **`modules[].own_packages` listed every package of the repo in every module**, a Maven module included. It now lists the module's own names; extractors still get the repo-wide union.
- **`dependencies[].version_source`** (`lockfile` | `range` | `null`) says whether `version` is installed or a range floor.
- The `tsconfig` of `angular.json` targets is chosen in declaration order (build first), not by file name.
- `>1` / `>1.2` normalize to `2.0.0` / `1.3.0` as in npm (was `1.0.1` / `1.2.1`).
- Removed the unused `npm_manifests.register()`; registration lives in `builtin.py`.

### Tests

- `tests/scanner/test_npm_manifests.py` (71 tests) covers AC-8 (lockfile beats range, all four scopes, `*`-normalized `angular.json` keys and per-target builders, comments / trailing commas / `extends`, effective paths), AC-8.2 (the npm workspace fixture → three modules, own packages, per-module dependencies) and AC-8.3 (a broken `package.json` → diagnostic, scan continues, exit `0`), plus the range normalizer and the JSONC stripper.
- Two new fixtures: `tests/fixtures/scanner/angular-app/` (lockfile, two Angular projects, three tsconfigs) and `tests/fixtures/scanner/npm-workspace/` (root lockfile, two package modules).
- The whole scanner suite and the 025 shared-key tests pass unchanged: 181 passed (`tests/scanner` 173, the 025 `test_shared_keys.py` 8), no regressions in the spec1 tests.

## [026.1-service-scanner] — 2026-11-06

### New features

- **`migration-scan`, the first part of the migration planner.** A new top-level package `migration_planner/` reads one service repository and writes `.migration/profile.json`: which files it scanned, how they group into modules, and the fact sections the later specs fill. It reads the service only — no graph, no LLM, no network — so it runs in a service repo with none of the ingestion dependencies installed. stderr carries a hint when `.migration/` is not in `.gitignore`; nothing is written to it. See [the scanner page](../docs/02-extraction-pipeline/service-scanner.md).
- **Discovery and modules.** Inside a git work tree files come from `git ls-files --cached --others --exclude-standard`; outside git the tree is walked and `.gitignore` is applied, so both modes give the same file set. `node_modules`, `.angular`, `.gradle`, `.git` and `.migration` are never entered, and `dist`, `build`, `target`, `out` outside `src/`; files over 2 MB and generated / minified JS are skipped and counted in `diagnostics`. Every manifest and source file belongs to its nearest module root (`package.json`, `pom.xml`, `build.gradle(.kts)`), and the repo-level `framework` is the one found in most modules, with ties listed in `diagnostics`.
- **Profile model and atomic writer.** The profile is pydantic (`Profile`, `ModuleEntry`, `SymbolEntry`, …) and is written through a temp file plus `rename`, so a crashed scan never leaves a half-written profile. Keys are sorted and lists are sorted, so two scans of an unchanged tree differ only in `generated.at`; `inputs_hash` changes when one byte changes. Every fact section that no spec fills yet is an empty list, so the schema is stable while specs 2–9 land.
- **Extractor contract.** `migration_planner/scanner/contract.py` defines the seam the later specs plug into: manifest readers (`dependencies`, `config`, `frameworks`, `diagnostics`), per-file source extractors (pure functions of the file content, so spec9 can cache and parallelize them) and post-passes. A reader or extractor that raises becomes a diagnostic; one bad file never fails a scan.
- **`migration_keys/`.** The canonical key builders (`npm_key`, `maven_key`, `cfg_key`, `syntax_key`, `diag_key`) and the Angular entry-point / template-token / config-prefix data moved out of `migration_oracle/pipeline/canonical/` into a dependency-free package that ingestion and the planner both import. 025 now reads them from there; no key or token changed.
- **Exit codes and summary.** `0` profile written, `1` usage error, `2` no supported manifest under `PATH`. stdout is one stable line (`scanned 4812 files · angular 19.2.0 · 61 deps · …`) with every count printed even when zero; `--json-summary` prints the same numbers as one JSON object. New entry point `migration-scan = "migration_planner.scanner.cli:main"`.

### Fixes (review 2026-11-06)

- **Java packages named `build` / `target` / `out` / `dist` were not scanned.** Those names are now skipped only outside a `src/` directory; `node_modules`, `.angular`, `.gradle`, `.git`, `.migration` are still skipped at any depth.
- **Files under no module root were dropped.** A root `tsconfig.json` or a shared `config/application.yml` next to `svc/pom.xml` now belongs to module `.`, which is listed in `modules[]` and reaches the manifest readers.
- **Walk mode ignored intermediate `.gitignore` files.** Every `.gitignore` from the root down to a file's directory now applies.
- **`config[]` merged entries by key only.** It now keeps one entry per occurrence `(key, module, file, profile, line)`, and `ConfigFact` / `ConfigEntry` carry `module`, `line`, `raw_key`, `profile`, `kind`, `test` for spec8.
- **`dependencies[]` merged a BOM and a dependency on the same artifact.** `kind` (`dependency | bom | parent | plugin`) is added and entries are unique per `(key, module, scope, kind)`.
- **`inputs_hash` ignored scan options.** `--max-locations` and `--include-tests` are now part of it, so spec9 cannot report `unchanged` after an option change.
- AC-9a now states the real contract (`generated.at` and `generated.duration_ms` differ between scans), and its test no longer contains a no-op assertion.

### Tests

- `tests/scanner/` (101 tests) covers the CLI contract, discovery in git and walk modes, skipped and generated files, modules, profile merge and bounds, determinism (`AC-9a`), the extractor contract, and isolation (`AC-10`): an AST guard fails if anything under `migration_planner/` or `migration_keys/` imports `migration_oracle`, `neo4j`, `langchain*`, `httpx` or `socket`, and a scan runs with no `NEO4J_URI`, no `.env` and sockets blocked.
- `tests/pipeline/test_shared_keys.py` guards `AC-1.4`: the 025 normalizer still produces byte-identical keys and uses the moved Angular data.

## [027-rule-signals] — 2026-11-06

### New features

- **Rule detection signals.** A new ingestion stage between canonicalization and the graph write classifies every rule by **how a service shows that the rule applies**: `symbol` (the code uses a named API), `config` (a config key is set), `dependency` (a package is declared), `syntax` (template syntax is used), `behavioral` (only code that relies on the old behaviour is affected) or `universal` (every service on the hop). System-1 picks the type and the feature tags; code decides what the planner can search for.
- **Feature tags.** Each rule also gets the features it needs (`ssr`, `hydration`, `zoneless`, `zone`, `animations`, `router`, `forms`, `http`, `i18n`, `service-worker`, `testbed`, `karma`, `ngmodule`, `elements`, `upgrade`, `cli-build` for Angular; starters for Spring Boot; subsystems for WildFly). The vocabulary lives in `migration_oracle/pipeline/signals/features.py` as plain data with **evidence keys** — the profile keys from which the planner can tell, without asking, that a service has the feature. So the planner can rule out whole groups and ask one question ("Do you use SSR?") instead of one per rule.
- **One System-1 request per rule.** A `signal` choice plus one `feature.<id>` `noul` per vocabulary entry, in a single body, so the state travels once per rule. Cached under `ARTIFACT_CACHE_DIR/signals/` by `SIGNAL_QUESTIONS_VERSION`, model, framework and state. The state contains the canonical keys, so a canonicalization change re-asks only the rules it affects. `--force-signals` ignores the cache.
- **Contract guard and floors.** The expensive mistake is excluding a rule that applies, so every uncertain rule falls back to `behavioral`: a type with no key to search for (a rule that names only its replacement, a `config` key with no known file, an unresolved `npm:?#X` package) becomes `behavioral` / `guard`; a type below `SIGNAL_SEARCHABLE_MIN_PROB` (0.70) or `universal` below `SIGNAL_UNIVERSAL_MIN_PROB` (0.60) becomes `behavioral` / `low_confidence`. Only `removed` and `mentioned` entities count — finding the *replacement* means the service has already migrated.
- **Deterministic shortcut.** A rule whose entities are all dependencies with `change_type: component_upgrade` is `dependency` by rule, without asking for the type; its features are still requested.
- **Graph properties.** `MigrationRule` gains `signal`, `signalConfidence`, `signalSource`, `signalKeys`, `features`, `signalQuestionsVersion`, `signalModel`, written in the same session as the rule. A rule without them is read by the planner as `behavioral`, so a missing classification never excludes anything.
- **`scripts/classify_signals.py`** backfills hops already in the graph: it reads `runs/json/*-entities.json`, canonicalizes, classifies, and `SET r += $props` on the matching `ruleId`. Sets only those properties, is idempotent, and reports `ruleId`s that are not in the graph.
- `--skip-signals` writes the rules without signal properties. `--dry-run` runs the stage and writes `runs/signals/` without touching the graph.
- New settings: `SIGNAL_STATE_MAX_CHARS` (4000), `SIGNAL_SEARCHABLE_MIN_PROB` (0.70), `SIGNAL_UNIVERSAL_MIN_PROB` (0.60), `SIGNAL_FEATURE_MIN_PROB` (0.50). The endpoint is the triage one (`TRIAGE_BASE_URL` / `TRIAGE_MODEL`); Nimble unset or unreachable logs once, writes no properties, and populate continues.
- `migration_oracle/pipeline/rule_ids.py` holds the `pipeline://{framework}/{version}/{title}` format, so populate and the backfill agree on the id.

## [025-entity-canonicalization] — 2026-11-06

### New features

- **Canonical entity identity.** Every affected entity gets one canonical identity before the graph write: `kind` (`class` · `member` · `property` · `dependency` · `syntax` · `diagnostic`), `ecosystem`, `package`, `symbol`, `member`, `file`, the matchable `name`, the merge `key`, and `verified`. Entity nodes now `MERGE` on `key`; `name` stays what scanners and MCP queries match on. Existing `runs/json/*-entities.json` files become canonical at populate time — no new LLM run is needed.
- **Deterministic normalizer** (`migration_oracle/pipeline/canonical/`): cleans backticks/quotes/`@`/trailing `()`, splits the three Angular package spellings (`@angular/core InjectFlags`, `@angular/router:Router`, `@angular/core/rxjs-interop RxResourceOptions`) into package + bare symbol, gives `TestBed.get` one `member` key whether the model said `class` or `property`, attaches bare options to their rule's replacement symbol (`exhaustive` → `provideCheckNoChangesConfig.exhaustive`), maps template operators (`in`, `void`, `@defer`, …) to new `TemplateSyntax` nodes and `NGxxxx` codes to new `DiagnosticCode` nodes, and files dotted config keys under their file (`engines.node` → `package.json`). Spring Boot / WildFly names stay byte-for-byte; only the key is computed.
- **Angular API verification.** For each hop the golden public-API files (`goldens/public-api/**/index.api.md` in `angular/angular`) are fetched at both version tags (GitHub token, cached under `ARTIFACT_CACHE_DIR/api-index/angular/<version>.json`) and each symbol is resolved to its entry point. Symbols found in several entry points pick the one matching a rule dependency, else stay `ambiguous` with `package: "?"`. Unverified entities are still written, marked `verified: false`; nothing is dropped. When the index cannot be fetched, populate continues with all npm entities unverified and the summary records `api_index: unavailable`.
- **Canonical audit artifacts.** `runs/canonical/<framework>-<from>-to-<to>-canonical.jsonl` holds one line per entity occurrence (raw kind/name, canonical fields, the applied normalization steps); `…-summary.json` counts per kind, verified percentages, collapsed raw names, and the `unverified_keys` manual-review list. `--dry-run` writes both without graph writes — the cheap way to review a hop.
- **Prompt naming rules.** `DOSSIER_ENTITY_PROMPT_VERSION` is 3: the Angular profile now asks for the bare exported symbol in `name`, the import path in the new optional `package` field, `Owner.member` for members, and `kind: "syntax" | "diagnostic"` where appropriate.

### Changed

- **Constraints.** The `class_name` / `property_name` / `dependency_name` uniqueness constraints are replaced by `*_key IS UNIQUE` constraints (plus new `template_syntax_key` and `diagnostic_code_key`); `name` gets plain indexes since it is no longer unique (`VERSION` exists in several Angular entry points). Startup drops the old name constraints automatically.
- `seed_deprecated_classes` and step-entity writes merge on `maven:<FQCN>` / canonical keys.
- After canonicalization no `Class` or `ApplicationProperty` name contains `:`, so the `groupId:artifactId` heuristic in `mcp/matching.py` only sees real dependencies. No MCP tool changed.

### Fixes (review 2026-11-06)

- **API index was always empty.** The golden parser expected `export declare` with two-space members, but the files are API Extractor reports (`export class X {`, four-space members). It now parses exported declarations, `export { X as Y }` aliases (`NgFor`, `Location`), the type of `export const TestBed: TestBedStatic`, and inline function option fields (`provideCheckNoChangesConfig.exhaustive`); re-exports of imported symbols are skipped. Test fixtures are real golden excerpts. On the 8 Angular hops verified npm occurrences go from 0% to 86%.
- **Golden listing was always empty.** The Contents API returns `type: "dir"`, not `"tree"`, and subtree paths lost their entry point. One `git/trees/<tag>:goldens/public-api?recursive=1` request replaces it; pre-v19 `index.md` goldens are accepted.
- **`GITHUB_TOKEN` was not used on populate**, so index fetches hit the 60/h anonymous limit.
- A missing tag no longer drops the whole hop: the index is `partial` and the summary lists `missing_versions`.
- `primitives/*` / `testing` entry points no longer make `Injector`, `InjectionToken`, `inject`, `Attribute` ambiguous.
- Bare options take their owner from the API index first (`useNgZoneOnStable` → `provideExperimentalCheckNoChangesForDebug`, not its replacement).
- `<pkg>#<sym>` is split; LLM `kind: syntax | diagnostic` is kept for tokens outside the profile list; non-identifiers such as `ng-reflect-*` get no owner.
- An existing `Version` node is skipped before canonicalization (no index fetch, no audit rewrite) unless `--dry-run`.
- Maven entities are `verified: "unchecked"` instead of an unchecked `"true"`.

## [Unreleased] — 2026-11-06

### New features

- **Version aliases.** `FROM`/`TO` accept `latest`, `latest-ga` (`latest-stable`), and `X.Y.Z-SNAPSHOT`. A snapshot resolves to the newest published build of that version (for example `4.2.0-SNAPSHOT → 4.2.0-RC2`); an unpublished line is an error. Aliases are resolved before artifact paths and `Version` nodes are named.

### Fixes

- **Minor hops read every covered release.** A Spring Boot minor hop used to read only the `to` release notes, so `4.0.0 → 4.1.0` lost everything from `4.1.0-M1 … RC1` and `4.1.0 → 4.1.2` lost `4.1.1`. It now reads all releases after `from` up to `to` on the target line, keeping duplicated rows once.
- **Stale raw files are re-extracted.** In hop-by-hop mode a raw file whose range or hop sections do not match the hop (old whole-range layout) is re-extracted instead of being reused.

## [024-dossier-entities] — 2026-11-05

### New features

- **Dossier entities.** When research is enabled, graph entities are built from the research dossiers instead of the filter LLM. An action gate drops rows whose dossier says `**Action:** none`, except `breaking`, `deprecation`, and `security`. Rows that share a pull request, commit, issue, or JIRA key are clustered, and each cluster gets one entity call. `runs/nodes/*_filtered.md` is rendered from those entities, so `filteredMdPath` is unchanged.
- `--entity-source dossier|filter` (env `ENTITY_SOURCE`). `filter`, research disabled, and `--skip-research` keep the previous filter-LLM path. `--entity-source dossier --skip-research` is an error.
- `--stop-after-clusters` writes `runs/clusters/` (gate decisions and cluster membership) and stops before any entity call. It does not need `MODEL_*`.
- Per-cluster entity cache under `ARTIFACT_CACHE_DIR/entities/`. A changed dossier re-runs only that cluster. `--force-llm` ignores the cache. Duplicate titles in one hop are suffixed with the source URL tail so distinct changes are not merged in the graph.
- **Research reuses `runs/research/*-research.jsonl`.** Before the row cache, each research row is looked up by `row_key` in the hop's existing JSONL. A line is used when it is not `error` and its `prompt_version` and `model` match the current `PROMPT_VERSION` and `RESEARCH_MODEL_ID`, so a hop whose JSONL is complete makes no research model calls even with an empty `ARTIFACT_CACHE_DIR`. Hand edits to a dossier's text are used. `--force-research` ignores the JSONL. The summary has a new `artifact_hits` count.
- `TRIAGE_DROP_MAX_ACTION_PROB` now defaults to `0.20` (was `0.10`).

### Fixes (review)

- A dossier run deletes `_filtered.md.input.sha256`, so switching back to `--entity-source filter` calls the filter LLM instead of reusing the rendered document.
- A hop with any failed entity cluster writes its artifacts but is not populated; the run exits 3 after the remaining hops. Previously the partial batch was populated and the missing rules could not be added later.
- GitHub `.patch` / `.diff` / `/files` / `/commits/<sha>` / `patch-diff` URLs are clustered with the plain pull, commit, or issue URL.
- The per-cluster cache key covers the triage category, statement, and source, not only the dossier text. `DOSSIER_ENTITY_PROMPT_VERSION` is 2.
- The cluster input puts `Triage:` under its `## Row n` heading; cluster splits and failures are no longer logged twice.

### Configuration

- `ENTITY_CONCURRENCY` (default 4), `CLUSTER_MAX_ROWS` (default 4), `CLUSTER_CONFIRM` (default `off`), `GATE_PROTECTED_CATEGORIES` (default `breaking,deprecation,security`).
- Dedicated entity model: `ENTITY_MODEL_PROVIDER` (`openai` | `deepseek`), `ENTITY_MODEL_ID`, `ENTITY_BASE_URL`, `ENTITY_API_KEY`, `ENTITY_OUTPUT_FORMAT`, `ENTITY_THINKING`, `ENTITY_REASONING_EFFORT`, `ENTITY_MAX_OUTPUT_TOKENS`, `ENTITY_TIMEOUT_SEC`. OpenAI uses strict `json_schema` structured output with `reasoning_effort`; DeepSeek uses `json_object` with thinking enabled. Unset `ENTITY_MODEL_ID` keeps `MODEL_*`.

## [023-per-change-research] — 2026-11-04

### New features

- **Default hop granularity is now `minor`**: `HOP_GRANULARITY` / `--hop-granularity` default to one hop per minor line (`19.0.0 → 19.1.0 → 19.2.0 → 20.0.0`) instead of every patch release. Pass `--hop-granularity patch` (or set `HOP_GRANULARITY=patch`) for the old behaviour.
- **Fetch-only research**: `TAVILY_API_KEY` is now optional. Without it research still runs when `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID` are set. The model gets only `fetch_url` and reads the row Sources and the pages they link to. With a key, prompt, tools and cache are unchanged. Fetch-only rows use their own cache key.
- **Per-change research** runs after the filter and before the entity LLM. A small tool-calling model reads each filtered row, searches with Tavily, and fetches the cited pages. It writes a fact dossier (`runs/research/*-research.jsonl`) and does not write migration steps. The entity prompt receives those dossiers as a Research appendix and is told to prefer cited facts over memory.
- Filtered tables gain a `Sources` column (comma-separated source URLs, or `N/A`). The entity step copies the first of those URLs into `source_url`. Older filtered files without the column still parse.
- Research stays off unless `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID` are set (`TAVILY_API_KEY` only enables `web_search`). `--skip-research` leaves the entity input unchanged. `--force-research` ignores the row cache. A row that times out, exceeds its tool budget, or returns invalid JSON is passed through to the entity step unchanged.
- An exhausted Tavily quota (HTTP 432, 433, 401, or 429 after three attempts) stops that hop with exit code 2. Finished rows stay cached, and a re-run continues from the rows that were not finished. Fetches to private, loopback, or link-local addresses are refused.
- Error dossiers are not cached, so a model or Tavily outage does not hide rows from later runs. The research cache is keyed per framework and hop (prompt version 2). Using the full tool budget now yields a dossier instead of an error. Raw statements are attached by issue/PR/commit links and skip Source URLs shared by many rows (`RESEARCH_SHARED_URL_MAX_ROWS`, `RESEARCH_RAW_CONTEXT_MAX_CHARS`). The per-section entity split skips summary sections.
- Prompt review: the filter's `Sources` column now lists the issue/PR/commit/JIRA links inside each statement instead of the shared release-notes page; the triage input column is `Impact score`; `Category` maps explicitly to sections; split filter parts keep the framework header and omit summaries. The research prompt documents every dossier field and the hop's version lines (`PROMPT_VERSION` 3), and a row's own Sources are always trusted. The entity prompt explains research blocks and fills `subsystem` / `cli_operation` only for WildFly.
- `--stop-after-research` stops a run after the research stage (no entity LLM, no graph writes).
- Research now runs right after triage, on every kept row, and before the filter LLM. The filter LLM writes the migration document from the kept rows plus a Research appendix (blocks tied to rows by Sources), and the entity LLM receives that document plus the research merged per document row. `--stop-after-research` stops before the filter LLM, so it needs no `MODEL_*`. `MODEL_ID` is now required and checked only for steps that call the main LLM; `langchain-openai` is a dependency for `MODEL_PROVIDER=openai`.
- Triage and research show a `tqdm` progress bar per hop on a terminal (stderr; `keep/drop/error` and `ok/not_found/error/cached` counts). Bars are off when output is not a TTY or with `TQDM_DISABLE=1`.

### Changed

- Research budgets: `RESEARCH_MAX_TOOL_CALLS` defaults to `12` (was `6`) and `RESEARCH_TIMEOUT_SEC` to `240` (was `120`). The per-request model timeout is now its own setting, `RESEARCH_MODEL_TIMEOUT_SEC` (`60`), so one hung completion no longer consumes the whole row budget.

## [022-system1-change-triage] — 2026-11-04

### New features

- **System-1 change triage** runs after extraction and before the filter LLM. A fast local classifier (`TRIAGE_BASE_URL` + `TRIAGE_MODEL`, contract `POST /v1/systemone`) labels every raw row. Only rows that are confidently noise are dropped; low confidence, errors, timeouts, and an unreachable endpoint keep the row. With triage off, the raw file and the filter input stay the historical 4-column table.
- Raw files gain triage columns and a `Triage:` summary line. `runs/triage/*-triage.jsonl` stores full probability distributions so `--retriage-from-cache` can retune thresholds without another model call. `--skip-triage` and `--force-triage` control the stage. Answers are cached by questions version, model, and state.
- The filter prompt uses `Category` and `Impact` when those columns are present, and splits an oversized kept table into category groups.
- `runs/nodes/*.md` follows the kept rows. A `*.input.sha256` file next to it records the filter input. When triage changes which rows are kept, the cached filtered Markdown and entities JSON are regenerated instead of being silently reused.

## [021-github-change-enrichment] — 2026-11-04

### New features

- Spring Boot GitHub release rows that cite an issue or pull request are enriched from the GitHub Issues API (title, cleaned body, labels, close reason) so later filter and entity steps see more than the one-line release note. A short backport or forward-port pointer is replaced with the original issue body, one level only.
- Angular release and changelog rows that cite a commit are enriched from the commit message (scope, body, breaking and deprecation footers, linked issue, schematic files). A row with only a pull or issue link uses the issue path. Requires `GITHUB_TOKEN`. Disable with `SPRING_BOOT_GITHUB_ENRICHMENT=false` or `ANGULAR_GITHUB_ENRICHMENT=false`. A primary rate-limit response stops further issue and commit fetches for the rest of the run without dropping the hop.

## [hop-granularity] — 2026-11-04

### New features

- **Configurable ingestion step size**: `export-extract-populate-framework` accepts `--hop-granularity patch|minor` (env `HOP_GRANULARITY`, default `patch`). `minor` collapses each minor line into one hop while keeping patch endpoints (`3.3.12 → 3.4.0 → 3.4.2`).
- **`--hop-by-hop` / `--no-hop-by-hop`** (env `HOP_BY_HOP`, default off): runs filter LLM, entity LLM, and graph population once per version hop, so each hop gets its own raw/filtered/entities artifacts and its own `Version` node carrying only that hop's rules. Cache resolution and `--skip-existing` apply per hop, so an interrupted range resumes at the first missing hop; `--output-*` overrides are rejected because paths are derived per hop.
- **Per-hop BOM diff** under `--hop-by-hop` (`BaseExtractor.extract_contexts(per_hop_range_metadata=True)`) — patch-level dependency and CVE movement was previously flattened into one range-level diff.
- **Prereleases are ordinary versions**: `4.1.0-RC1`, `4.1.0-M1`, `22.0.0-rc.2`, `20.0.0-next.3` and the JBoss `26.1.2.Final` spelling now parse. Prerelease `sortableVersion` sits below the GA release it precedes (`4.1.0-M1` → 4000901, `4.1.0-RC1` → 4000951, `4.1.0` → 4001000), so **GA integers are unchanged** and no backfill is required. New `Version` properties: `preRelease`, `preReleaseLabel`.
- **`scripts/run_spring_boot_patch_ingest.sh`**: GA-only patch-level Spring Boot ingestion by default (extract-only unless `full`), with `SPRING_INCLUDE_PRERELEASE=1` to include milestone/RC hops.

### Bug fixes

- `version_key()` ignored prerelease suffixes, so `4.1.0-M1`, `4.1.0-RC1` and `4.1.0` compared equal: discovery order decided hop sequences, and a range ending at `4.1.0-RC1` also swallowed the GA release.
- Spring Boot minor-line wiki pages (`Spring-Boot-{major}.{minor}-Release-Notes`) were attached to every hop that landed inside the line — measured 57 duplicated rows in each of the 13 hops of a 3.3.x range. They are now attached only to the hop that **enters** the line. `extract()` calls without a `hop_context` keep the previous behaviour.

## [013a-live-probe-fixes] — 2026-06-15

### Behavioural change (breaking for callers that persist rule_id)

- `analyze_upgrade_path`, `build_recipe_plan`, and `get_pending_steps` now return `rule_id` as the stable `MigrationRule.ruleId` property (`pipeline://…` for pipeline rules, `community://…` for community insights), falling back to `elementId(rule)` only when no `ruleId` property exists. Callers that persisted the previous element-ID-based `rule_id` must re-key their stored values.

### New features

- **Server build provenance**: `get_graph_schema` now includes a `server_build` block (`git_sha`, `branch`, `feature_tags`, `started_at`). Set `GIT_SHA`, `GIT_BRANCH`, `FEATURE_TAGS` env vars at deploy time.
- **`matched_entities`** added to `analyze_upgrade_path` rule objects (exact-string matching against scanned entities).
- **Recipe coverage diagnostic**: `build_recipe_plan` now returns `diagnostics.recipes_loaded` (bool) and `diagnostics.recipe_count` (int), making the zero-recipe state visible.
- **`context_id` parameter** added to `build_recipe_plan` (optional); when provided, version range is derived from the context's resolved `UPGRADES_FROM`/`UPGRADES_TO` bounds.
- **`reused`, `entityCount`, `droppedCount`** always present on `create_migration_context` response (both create and resume paths).
- **`solution` field** added to `search_migration_knowledge` hit objects.
- Community insights now receive a stable `ruleId` of the form `community://{framework}/{version}/{uuid}` at create time.

### Bug fixes

- Zombie context guard: if `create_migration_context` resumes a context whose `UPGRADES_FROM`/`UPGRADES_TO` edges point to wrong nodes, it deletes and re-creates the context.
- `search_migration_knowledge` hits now include `solution` field (was missing from serializer).
- `_ANALYZE_UPGRADE_PATH` Cypher now includes the package-prefix bridge for Dependency-only rules (matching scanned class FQCNs against dependency groupId prefix), consistent with `_GET_PENDING_STEPS`.
- `build_recipe_plan` entity matching now uses exact-string comparison (was using `.lower()`, diverging from how typed buckets are populated).

### Follow-up (FU-1 — out of scope)

- Community rule `ruleId` was previously not written at all by `submit_migration_insight`. Now set to `community://…` at create time. Existing community rules created before this release still have no `ruleId` and rely on the `coalesce(rule.ruleId, elementId(rule))` fallback, which remains rebuild-unstable for those nodes. Owner: TBD.

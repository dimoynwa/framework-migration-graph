# Feature Specification 026.1: Service Scanner — Skeleton, CLI, Discovery, Profile Writer

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec on 2026-11-06)

**Status**: Implemented (2026-11-06)

**Scope**: Lightweight spec (no full SpecKit flow). First of nine small specs that together make up
**026 Service Scanner**. Each one ends with something you can run and test on its own.
This file also holds the **shared context** (problem, principles, non-goals, profile schema)
that the other eight specs refer to.

## 026 split

Requirement IDs (FR-x, AC-x) are kept from the original single spec, so references such as
"026 FR-8a" in `027-rule-signals` stay valid.

| Spec | Part | FRs | ACs | Test after it lands | Effort |
|---|---|---|---|---|---|
| **spec1** | Package split, CLI, discovery, module roots, profile model + writer, determinism, isolation | FR-1, FR-2, FR-3 (module roots, repo framework), FR-9 | AC-9a, AC-10 | `migration-scan` on any repo writes a valid, deterministic profile with `modules[]` | ~7 h |
| **spec2** | npm manifests, tsconfig, Angular version | FR-3 (Angular), FR-4 | AC-8 | Angular repo: framework, `dependencies[]`, `cfg:package.json/angular.json/tsconfig.json` keys | ~3.5 h |
| **spec3** | TS/JS imports, members, decorators (no barrels) | FR-5 (minus barrels) | AC-1, AC-3 | Angular repo: `symbols[]`, `members[]`, `side_effect_imports[]` | ~6 h |
| spec4 | Barrel / alias resolution | FR-5 (barrels) | AC-2 | `@app/*` imports resolve to the external package at the import site | ~5 h |
| spec5 | Angular templates + Angular real-service check | FR-6 | AC-4, AC-11 (Angular) | Angular repo: `templates[]`; full Angular profile validated on a real service | ~5.5 h |
| spec6 | Maven + Gradle manifests, Spring Boot version | FR-3 (Spring Boot), FR-8 | AC-6, AC-7 | Spring repo: framework, `dependencies[]`, `cfg:pom.xml/build.gradle` keys | ~6 h |
| spec7 | Java sources | FR-7 | AC-5 | Spring repo: `symbols[]`, `members[]`, `wildcard_imports[]` | ~5 h |
| spec8 | Spring config files + Spring real-service check | FR-8a | AC-8a, AC-11 (Spring) | Spring repo: `config[]` with `cfg:application.properties#…`, secrets redacted | ~6.5 h |
| spec9 | Incremental cache, process pool, packaging extras, final docs | FR-10 | AC-9b, AC-11 (timings) | warm re-scan prints `unchanged` in < 3 s | ~4 h |

Order: spec1 → (spec2 → spec3 → spec4 → spec5) and (spec6 → spec7 → spec8) → spec9. The Angular
and Java tracks are independent after spec1; spec7 needs spec6 (groupIds for FQCN usages).

### Planner roadmap (026 is step 1)

| Spec | Part | Reads | Writes |
|---|---|---|---|
| **026** | **Scanner**: service repo → facts | code, manifests | `.migration/profile.json` |
| 027 | *(ingestion)* Rule signals: Nimble classifies each rule (`symbol` / `config` / `dependency` / `syntax` / `behavioral` / `universal`) + feature tags | rules | `MigrationRule` properties |
| 028 | Matcher: profile × rule signals → applies / excluded / unknown, per rule and step | profile, graph | `.migration/decisions.json` |
| 029 | Unknowns: code excerpts → Nimble; generated human questions | profile, code excerpts | decisions, `.migration/answers.yaml` |
| 030 | Agent commands: `rules`, `show`, `answer`, `done`, `verify` | all of the above | `.migration/report.md` |

027 is the one ingestion change the planner needs; see `specs/027-rule-signals/spec.md`.

---

## Shared context (applies to spec1–spec9)

The 026 scanner is the first part of the **migration planner**: the tool an agent or a person
runs in a service repo to get only the rules and steps that apply to that service. 026 covers
**only reading the service**: a deterministic scanner that parses the codebase and its build
manifests and writes one profile file.

**Not ingestion.** Ingestion (extract → triage → research → entities → populate, specs
017–025) builds the shared rule graph once per framework hop, on our side. The planner runs per
service, in the service repo, and only reads the graph.

**Depends on**: `025-entity-canonicalization`, for the key formats only. The profile uses the
same canonical keys as the graph (`npm:<package>#<symbol>`, `maven:<FQCN>`, `cfg:<file>#<key>`,
`syntax:…`), so the matcher compares sets without translation. The scanner itself never reads
the graph.

### Problem

We want to answer "which migration rules apply to this service" without an agent reading the
codebase into its context. A service can have thousands of classes and tens of thousands of
imports. The facts the rules depend on are few and mechanical:

- which framework and version the service is on;
- which dependencies it declares;
- which framework / library symbols it imports and calls;
- which config keys it sets;
- which template syntax it uses (Angular).

All of these can be read with a parser. No LLM and no tokens are needed. The result must be
small (bounded by the libraries' API surface, not by the codebase size). It must not depend on
the rules, so one scan serves every hop.

### Goal

```
                         ┌──────── planner (runs in the service repo) ────────┐
service repo ──▶ migration-scan ──▶ .migration/profile.json ──▶ 028 matcher … 030
                  │                 (+ one summary line on stdout)
                  │
                  ├─ manifests: package.json, angular.json, tsconfig*.json,          (spec2)
                  │             pom.xml, build.gradle(.kts), settings.gradle(.kts),  (spec6)
                  │             gradle/libs.versions.toml, gradle.properties,        (spec6)
                  │             application*.properties|yml|yaml,                    (spec8)
                  │             bootstrap*.properties|yml|yaml                       (spec8)
                  └─ sources:   *.ts *.tsx *.js *.jsx *.mjs *.cjs                    (spec3, spec4)
                                *.html (templates)                                   (spec5)
                                *.java                                               (spec7)
```

### Key Principles

- **No LLM, no network, no graph.** The scanner runs in the service repo, offline. It does not
  import `migration_oracle.config` (which requires `NEO4J_URI`) or any graph code.
- **External symbols only.** Imports of the service's own code (relative paths, path aliases,
  the service's own Java packages) are not recorded. Barrels and aliases are followed until
  they reach an external package.
- **Rule-independent.** The profile records facts, not decisions. It never reads the graph.
- **Bounded output.** Per symbol: a count plus at most `--max-locations` locations.
- **Agent-friendly.** stdout is one summary line. The profile is for tools, not for an agent's
  context.
- **Best effort, never silent.** Anything the scanner cannot resolve (an unparsable file, an
  unresolved Gradle variable, a barrel cycle) is counted and listed in `diagnostics`. The scan
  never fails because of one file.

### Non-Goals (all of 026)

- Matching against rules, Nimble, questions, the `rules` / `show` / `answer` / `verify` commands.
- Type inference. Instance method calls (`entity.getStatusCodeValue()` on a local variable) are
  not resolved. The profile lists every file that imports an owner type (its `locations`), so a
  later matcher can search only those files.
- Kotlin and Groovy **sources**, Scala, lockfiles other than `package-lock.json`. See Open
  Questions in spec2 and spec7.
- Spring config outside the repo (Config Server, Kubernetes ConfigMaps, environment variables).
  Only files in the repo are read.
- Uploading the profile anywhere.

### Extractor contract (how spec2–spec8 plug in)

spec1 defines a small internal interface so each later spec only adds one module:

- **Manifest readers** get a module root and the list of manifest files in it, and return
  `dependencies`, `config`, `frameworks` and `diagnostics` fragments.
- **Source extractors** get one file (path, bytes, module, `test` flag) and return per-file
  facts (`symbols`, `members`, `side_effect_imports`, `wildcard_imports`, `templates`,
  `diagnostics`, plus any export map needed later). They are pure functions of the file content,
  so spec9 can cache them and run them in a process pool.
- **Post-passes** (barrel resolution in spec4, own-package filtering in spec7) run on the
  collected per-file facts.
- The profile builder merges fragments, applies `--max-locations`, sorts, and writes.

Readers and extractors are registered in one list; a spec that is not implemented yet simply
contributes nothing, and its profile sections stay empty lists.

---

## Requirements (spec1)

### FR-1 CLI

```
migration-scan [PATH] [--out FILE] [--force] [--max-locations N] [--include-tests/--no-include-tests] [--json-summary]
```

- `PATH` defaults to the current directory. `--out` defaults to `PATH/.migration/profile.json`.
- New entry point `migration-scan = "migration_planner.scanner.cli:main"` in `pyproject.toml`
  (later also callable as `migrate scan` from the 030 command group).
- The planner is a separate top-level package, `migration_planner/`, next to
  `migration_oracle/`. It imports nothing from `migration_oracle.config`, `graph`, `mcp` or
  `pipeline`. The key formats and Angular token lists it shares with 025 move to a small pure
  module, `migration_keys/` (no dependencies), which both packages import.
- stdout, one line:
  `scanned 4812 files · angular 19.2.0 · 61 deps · 312 symbols · 48 members · 27 config · 4 template tokens · 3 diagnostics → .migration/profile.json (2.4 s)`
  Counts that are zero are still printed, so the format is stable while later specs land.
- `--json-summary` prints the same as one JSON object instead.
- Exit codes: `0` written, `1` usage error, `2` no supported manifest found under `PATH`
  (supported = any manifest file name from the Goal diagram, even before its reader exists).
- `--max-locations` (default `20`) caps locations per symbol. `count` is always exact; it counts
  distinct `(file, line)` sites (two uses of one key on one line are one site, since a location
  has no column).
- Tests (`*.spec.ts`, `*.test.ts`, `src/test/java/**`, `src/test/**`, and every Gradle test
  source set `src/<name>Test/**` — `src/integrationTest`, `src/componentTest`,
  `src/acceptanceTest`, `src/apiTest`, … — plus Maven's `src/it/**`; amended 2026-11-07) are
  included by default,
  since many rules are test-only (`TestBed.get`, `@MockBean`). Each location records
  `test: true|false`. `--no-include-tests` drops test files at discovery.
- `--force` is accepted now; it only has an effect once the cache lands (spec9).
- On first run, the summary suggests adding `.migration/` to `.gitignore` (not written).

### FR-2 File discovery

- In a git work tree, files come from `git ls-files --cached --others --exclude-standard`, so
  `.gitignore` is respected. Otherwise walk the tree.
- Always skipped, at any depth: `node_modules`, `.angular`, `.gradle`, `.git`, `.migration`.
- Build-output names `dist`, `build`, `target`, `out` are skipped only when no ancestor
  directory is `src`. Inside `src/` they are Java packages or app folders
  (`src/main/java/com/x/build/`), not build output.
- Any source file > 2 MB is skipped (counted in `diagnostics`). Manifests get a 50 MB cap
  instead: a real `package-lock.json` is often > 2 MB, and skipping it would replace installed
  versions with range floors.
- Outside git, the walk applies every `.gitignore` from the root down to the file's directory.
- Generated / minified JS (`*.min.js`, a first line > 1 000 chars) is skipped and counted.
- Each discovered file is classified as `manifest:<kind>` or `source:<lang>` or ignored, so
  later specs only register a handler for their kind.

### FR-3 Modules and framework detection (module part)

A repo can hold several modules (npm workspaces, Maven modules, Gradle subprojects).

- **Module roots**: every directory with a `package.json`, `pom.xml` or `build.gradle(.kts)`,
  excluding skipped directories. Each source and manifest file belongs to its nearest module
  root. A file under no module root belongs to `.`, and `.` is listed in `modules[]` whenever
  any file belongs to it (a root `tsconfig.json`, a shared `config/application.yml` next to
  `svc/pom.xml`), so no manifest is dropped.
  (Maven `<modules>` and Gradle `include(...)` are also followed in spec6.)
- Each module gets `manifests: [...]` (file names relative to the module) and
  `frameworks: [{name, version, raw, source}]`. A module can have none. The detectors are added
  in spec2 (Angular) and spec6 (Spring Boot).
- The repo-level `framework` is the one found in most modules; ties are listed in
  `diagnostics`. With no detector result, `framework` is `null` and the summary line prints
  `no framework`.

### FR-9 Profile file

`.migration/profile.json`, UTF-8, deterministic order (keys sorted, lists sorted by key then
location), so two scans of the same tree are byte-identical except `generated.at` and
`generated.duration_ms`.

The full schema is defined now; sections whose spec is not implemented yet are empty lists.

```json
{
  "schema": 1,
  "generated": { "at": "2026-11-06T10:20:00Z", "scanner": "026", "root": ".",
                 "files_scanned": 4812, "files_skipped": 37, "duration_ms": 2410 },
  "inputs_hash": "sha256:…",
  "framework": { "name": "angular", "version": "19.2.0", "raw": "^19.2.0", "source": "package-lock.json" },
  "modules": [
    { "path": ".", "manifests": ["package.json", "angular.json", "tsconfig.json"],
      "frameworks": [{ "name": "angular", "version": "19.2.0" }], "angular_projects": ["payments-ui"] }
  ],
  "dependencies": [
    { "key": "npm:@angular/platform-server", "range": "^19.2.0", "version": "19.2.4",
      "scope": "dependencies", "module": ".", "kind": "dependency", "version_source": "lockfile" }
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
  "side_effect_imports": [{ "key": "npm:zone.js", "count": 1, "locations": ["…"] }],
  "wildcard_imports": [],
  "config": [
    { "key": "cfg:package.json#engines.node", "value": ">=18", "file": "package.json",
      "module": ".", "line": null, "raw_key": null, "profile": null, "kind": null, "test": false },
    { "key": "cfg:angular.json#projects.*.architect.build.builder",
      "value": "@angular-devkit/build-angular:application", "file": "angular.json" }
  ],
  "templates": [{ "key": "syntax:angular-template#@defer", "count": 4, "locations": ["…"] }],
  "diagnostics": [
    { "kind": "unresolved_variable", "file": "build.gradle", "line": 14, "detail": "$jacksonVersion" }
  ]
}
```

| Section | Filled by |
|---|---|
| `generated`, `inputs_hash`, `modules[].path/manifests`, `diagnostics` (discovery) | spec1 |
| `framework`, `modules[].frameworks` | spec2 (Angular), spec6 (Spring Boot) |
| `modules[].angular_projects`, npm `dependencies`, npm / angular / tsconfig `config` | spec2 |
| `symbols`, `members`, `side_effect_imports` (TS/JS) | spec3, spec4 |
| `templates` | spec5 |
| Maven / Gradle `dependencies`, `cfg:pom.xml` / `cfg:build.gradle` `config` | spec6 |
| `symbols`, `members`, `wildcard_imports` (Java) | spec7 |
| Spring `config`, `modules[].spring_config_files` | spec8 |

- `locations` of a symbol are its **import sites**. Those are the files a matcher must search for
  instance calls (Non-Goals).
- `files` = number of distinct files using the symbol.
- `dependencies[]`: one entry per `(key, module, scope, kind)`, `kind` =
  `dependency | bom | parent | plugin` (filled by spec6; npm entries are `dependency`).
- `config[]`: one entry per occurrence `(key, module, file, profile, line)`, never merged by key
  alone. `line`, `raw_key`, `profile`, `kind` are filled by spec8 and `null` elsewhere; `value`
  is `null` with `--no-values` (spec8).
- `truncated: true` when `count` > number of stored locations.
- All paths are relative to the scan root, with `/` separators.
- `inputs_hash` = sha256 over the sorted `(path, sha256(content))` of every scanned file and
  manifest, plus the scanner version and the output-changing scan options (`--max-locations`,
  `--include-tests`; spec8 adds `--no-values`), so spec9 never reports `unchanged` after an
  option change.
- Profile models as pydantic, same style as `models/entities.py`. Writing goes through a temp
  file + rename, so a crashed scan never leaves a half-written profile.

### Package split and isolation

- `migration_planner/__init__.py`, `migration_planner/scanner/` with `cli.py`, `discover.py`,
  `profile.py` (model, merge, writer).
- `migration_keys/`: key builders (`npm_key`, `maven_key`, `cfg_key`, `syntax_key`) and the
  Angular token list, moved out of `migration_oracle/pipeline/canonical/` (025 now imports them
  from `migration_keys`), so ingestion and planner cannot drift. 025's tests must still pass.
- Import-guard test (AC-10). The `[planner]` / `[ingest]` extras split is in spec9.

---

## Acceptance Criteria (spec1)

Fixtures under `tests/fixtures/scanner/`, tests under `tests/scanner/`.

- **AC-1.1 CLI**: `--help`, defaults for `PATH` / `--out`, `--json-summary` output parses as JSON
  with the same counts as the text line; usage error → exit `1`; a directory with no supported
  manifest → exit `2` and no profile written.
- **AC-1.2 Discovery**: in a git fixture, a `.gitignore`d file is not scanned; outside git, the
  walk gives the same file set. Skipped directories, a > 2 MB file and a `*.min.js` /
  long-first-line file are skipped and counted in `diagnostics`. `--no-include-tests` drops
  `*.spec.ts` and `src/test/**`.
- **AC-1.2b Source-tree names**: `src/main/java/com/x/build/A.java` and `src/app/out/c.ts` are
  scanned; `target/classes/Gen.java` and `src/node_modules/x.js` are not. In walk mode,
  `a/.gitignore` with `*.gen.ts` ignores `a/b/x.gen.ts`.
- **AC-1.3 Modules**: a fixture with a root `package.json` and nested `backend/pom.xml` and
  `tools/build.gradle.kts` → three modules; each source file is assigned to its nearest root.
  `svc/pom.xml` + root `tsconfig.json` + `config/application.properties` → modules `.` and
  `svc`, with both root files listed under `.`.
- **AC-1.5 Fact merge**: the same config key in two modules, files or Spring profiles → one
  entry each; the same dependency as `bom` and as `dependency` → two entries.
- **AC-9a Determinism**: two scans of the same tree → identical profile except `generated.at`
  and `generated.duration_ms`. Changing one byte in one file, or `--max-locations` /
  `--include-tests`, changes `inputs_hash`.
- **AC-10 Isolation**: `migration-scan` runs in a clean environment with no `NEO4J_URI` or
  other `.env` and no network (sockets blocked in the test). An import-graph test fails if
  anything under `migration_planner/` or `migration_keys/` imports `migration_oracle`, `neo4j`,
  `langchain*` or `httpx`.
- **AC-1.4 Key move**: 025 canonicalization tests pass after the move to `migration_keys/`.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests.

## How to test after spec1

```bash
migration-scan /path/to/any/angular-or-spring-repo
cat /path/to/repo/.migration/profile.json | jq '.modules, .generated, .diagnostics'
migration-scan /tmp/empty-dir; echo $?   # → 2
```

Expected: one summary line with `0` for all fact counts, `no framework`, a profile with
`modules[]` and empty fact sections.

## Implementation Notes (spec1)

- Docs: create the `docs/` page for the scanner (CLI, principles, profile schema with the
  "filled by" table). Each later spec adds its section to the same page. `CHANGELOG.md` entry
  per spec.

## Open Questions (spec1)

1. Monorepos with several frameworks: one profile with `modules[]` (as specified), or one
   profile per module root? One file keeps the agent command simple; per-module files keep
   matching per module trivial.
2. Should the profile be reusable across machines (paths relative to root, as specified) so a
   CI job can scan and attach it as an artifact?

## Estimate

~7 h: package split + key move + import guard 2 h; CLI, discovery, modules, profile model and
writer 4 h; fixtures and tests 1 h.

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
- A file over 2 MB is not read; a `*.min.js` or a JS file whose first line exceeds 1000
  characters is treated as generated. Both are counted in `diagnostics`.
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

## Profile schema

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
    { "path": ".", "manifests": ["package.json", "tsconfig.json"],
      "frameworks": [{ "name": "angular", "version": "19.2.0" }], "angular_projects": ["payments-ui"] }
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
| `framework`, `modules[].frameworks` | spec2 (Angular), spec6 (Spring Boot) |
| `modules[].angular_projects`, npm `dependencies`, npm / angular / tsconfig `config` | spec2 |
| `symbols`, `members`, `side_effect_imports` (TS/JS) | spec3, spec4 |
| `templates` | spec5 |
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

Each later 026 spec adds one module and registers it; the scan loop never changes.

- **Manifest readers** receive a module root and its manifest files, and return `dependencies`,
  `config`, `frameworks` and `diagnostics` fragments.
- **Source extractors** receive one file (path, bytes, module, `test` flag) and return per-file
  facts. They are pure functions of the file content, so spec9 can cache them and run them in a
  process pool.
- **Post-passes** run on the collected facts, before the profile is built (barrel resolution in
  spec4, own-package filtering in spec7).

See `migration_planner/scanner/contract.py`.

## Package layout and isolation

```text
migration_planner/            planner: runs in a service repo
  scanner/
    cli.py                    migration-scan
    discover.py               file discovery, classification, module roots
    profile.py                pydantic profile model, merge, atomic writer
    scan.py                   the one scan loop
    contract.py               extractor contract + registry
migration_keys/               pure key builders + Angular data (shared with ingestion)
  keys.py
  angular.py
```

`tests/scanner/test_isolation.py` guards the split: it fails if anything under `migration_planner/`
or `migration_keys/` imports `migration_oracle`, `neo4j`, `langchain*`, `httpx` or `socket`, and
it runs a scan with no `NEO4J_URI`, no `.env` and sockets blocked.

## Verifying a scan

```bash
migration-scan /path/to/any/repo
jq '.modules, .generated, .diagnostics' /path/to/repo/.migration/profile.json
migration-scan /tmp/empty-dir; echo $?    # → 2
```

After 026.1, every fact count is `0` and `framework` is `null` on any repository: the readers
and extractors arrive with specs 2–8.

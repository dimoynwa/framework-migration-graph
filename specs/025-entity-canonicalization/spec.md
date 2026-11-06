# Feature Specification: Canonical Graph Entities

**Feature Branch**: `025-entity-canonicalization`

**Created**: 2026-11-06

**Status**: Draft

**Scope**: Lightweight spec (no full SpecKit flow). Gives every `Class`, `ApplicationProperty`
and `Dependency` node one canonical identity. Validates Angular symbols against the published
public API.

**Depends on**: `024-dossier-entities` (`runs/json/*-entities.json` format, per-cluster entity
prompt).

**Enables**: a later service-relevance spec (matching rules to one service's code). That spec
needs entities whose names can be found in a codebase.

## Problem

Rules meet only through shared entity nodes, and the populator merges those nodes by raw `name`
(`MERGE (e:Class {name: $name})`, `populator.py:404`). The entity prompt asks for
"FQCN, dotted key, or groupId:artifactId" (`entities/prompt.py:92`). That works for Java, but
Angular has no FQCN, so the model improvises.

Measured on the Angular graph at `bolt://localhost:8003` (2026-11-06: 3 `Version`, 75
`MigrationRule`, 92 `Class`, 34 `ApplicationProperty`, 8 `Dependency`):

- **Three package spellings.** 11 of 92 `Class` names carry a package:
  `@angular/core InjectFlags`, `@angular/router:Router`, `@angular/core/rxjs-interop RxResourceOptions`.
  After stripping the package, 4 symbols exist twice (`Injector`, `InjectFlags`,
  `RedirectFunction`, `MaybeAsync`). Rules about the same symbol do not meet.
- **The `:` form breaks matching.** `mcp/matching.py` reads any name containing `:` as a Maven
  `groupId:artifactId`. So `@angular/router:Router` is matched against scanned dependencies,
  not classes.
- **Members have no kind.** `TestBed.get`, `TestBed.inject`, `provideCheckNoChangesConfig` and
  `provideExperimentalCheckNoChangesForDebug` exist both as `Class` and as
  `ApplicationProperty`.
- **Owner lost.** `exhaustive` and `interval` (options of `provideCheckNoChangesConfig`) and
  `optional`, `skipSelf` (fields of `InjectOptions`) are stored as bare names.
- **Wrong kind.** `in` and `void` (template expression operators) are `ApplicationProperty`
  nodes. `NG8115` (a compiler diagnostic) is a property. The rules are valid; the kinds are not.
- **Config file lost.** `engines.node` (`package.json`) and
  `angularCompilerOptions.extendedDiagnostics.checks.missingStructuralDirective` (`tsconfig.json`)
  do not record which file they belong to.
- **Nothing checks the names.** An invented or misspelt symbol is written like a real one.

Correction to an earlier note: `BreakingScope` is fine. Its key is `(scope, severity)`, not `name`.

## Goal

```
entities.json (LLM output, unchanged)
      │
      ▼
normalize (FR-2, code) ──▶ resolve + verify against API index (FR-3) ──▶ canonical entities
      │                                                                        │
      └──────────── audit runs/canonical/*.jsonl (FR-5) ◀──────────────────────┤
                                                                               ▼
                                               populate: MERGE on `key` (FR-4)
```

The normalizer and the verifier run at populate time. Existing `runs/json/*-entities.json`
files therefore become canonical without a new LLM run.

## Key Principles

- **Code before prompt.** A deterministic normalizer fixes existing artifacts and catches
  model drift. The prompt change (FR-6) only lowers how much the normalizer has to fix.
- **Ground truth over model memory.** A package is filled in from the framework's published API,
  never guessed.
- **Fail toward keeping.** An unverified entity is still written, marked `verified: false`.
  Nothing is dropped for failing verification.
- **Existing readers keep working.** `name` stays the identifier that scanners and MCP queries
  match on (`e.name IN $scanned_classes`). Only the merge identity moves to `key`.

## Non-Goals

- Changing which MCP tools exist or what they return. They only pick up the new node
  properties (FR-4) without being edited, except for the one compatibility check in FR-4.4.
- A Spring Boot / WildFly API index. Their names are already FQCNs and dotted keys, so for them
  the normalizer must be a no-op apart from computing `key` (AC-5). Spring metadata validation
  (`spring-configuration-metadata.json`, jar class index) is a follow-up.
- Rule-level deduplication (for example the `… (CHANGELOG.md 3)` titles from 024 FR-3.6).
- Service relevance and detect signatures.

---

## Requirements

### FR-1 Canonical entity model

Each affected entity gets these fields, derived by code from the LLM's `kind` / `name` / `role`
plus an optional LLM `package` (FR-6):

| Field | Meaning | Example |
|---|---|---|
| `kind` | `class` · `member` · `property` · `dependency` · `syntax` · `diagnostic` | `member` |
| `ecosystem` | `npm` · `maven` | `npm` |
| `package` | npm package / entry point, Maven `groupId:artifactId`, or empty | `@angular/core/testing` |
| `symbol` | exported symbol, FQCN, config key, or token | `TestBed` |
| `member` | method / field / option of `symbol`, or empty | `get` |
| `file` | config file, `property` only | `tsconfig.json` |
| `name` | **matchable** identifier, never contains `:` for class/member/property | `TestBed.get` |
| `key` | unique identity, used for `MERGE` | `npm:@angular/core/testing#TestBed.get` |
| `verified` | `true` · `false` · `ambiguous` · `unchecked` (maven: no API index yet) | `true` |

Key and name forms:

| kind | `key` | `name` |
|---|---|---|
| class (npm) | `npm:<package>#<symbol>` | `<symbol>` |
| member (npm) | `npm:<package>#<symbol>.<member>` | `<symbol>.<member>` |
| class (maven) | `maven:<FQCN>` | `<FQCN>` (unchanged) |
| property | `cfg:<file>#<dotted key>` (`file` = `application.properties` for Spring) | `<dotted key>` |
| dependency | `npm:<package>` · `maven:<groupId>:<artifactId>` | `<package>` · `<groupId>:<artifactId>` (unchanged) |
| syntax | `syntax:<framework>-template#<token>` | `<token>` |
| diagnostic | `diag:<code>` | `<code>` |

- An unresolved npm package gives `npm:?#<symbol>` with `verified: false`. A later resolution
  changes the key, so such nodes are re-merged on the next populate.
- `member` is stored with the `Class` label and `property`-like options with the
  `ApplicationProperty` label (FR-4), so existing class/property queries still see them.

### FR-2 Normalizer (deterministic)

`migration_oracle/pipeline/canonical/normalize.py`, pure functions, per framework profile.

1. **Clean.** Trim, strip backticks and quotes, trailing `()` and a leading `@` on decorators
   (`@Attribute` → `Attribute`, with `@` kept only in the audit).
2. **Split package.** For npm frameworks parse `<pkg> <sym>`, `<pkg>:<sym>`, `<pkg>#<sym>` and `<pkg>/<sym>`,
   where `<pkg>` starts with `@` or matches a known package of the profile → `package` + `symbol`.
3. **Split member.** `Owner.member` where `Owner` starts upper-case or is a known symbol (FR-3)
   → `kind: member`. This also applies when the LLM said `property`, so `TestBed.get` gets one
   identity.
4. **Owner for bare options.** A bare lower-case `property` name that is an identifier, not a
   known symbol and not a config key is a field of: the one `class` symbol of the rule whose
   published API lists it (FR-3 index), else the rule's **replacement** symbol, else its only
   `class` entity. `exhaustive` → `provideCheckNoChangesConfig.exhaustive`;
   `useNgZoneOnStable` → `provideExperimentalCheckNoChangesForDebug.useNgZoneOnStable` (the
   removed function, not its replacement). With no owner, or for non-identifiers such as
   `ng-reflect-*`, it stays bare with `verified: false`.
5. **Syntax and diagnostics.** LLM `kind: syntax` / `diagnostic` is kept. Names in the profile's token list (Angular: `in`, `void`,
   `typeof`, `as`, `let`, `@if`, `@for`, `@switch`, `@defer`, `@let`, …) → `syntax`.
   `^NG\d{4}$` → `diagnostic`.
6. **Config file.** Dotted keys by prefix → `file`: `engines.` / `peerDependencies.` →
   `package.json`, `angularCompilerOptions.` / `compilerOptions.` → `tsconfig.json`,
   `projects.` / `architect.` → `angular.json`. Unknown prefixes stay `file: ""` with
   `verified: false`.
7. **Spring Boot / WildFly profile.** Only computes `key`. `name` stays byte-for-byte as written,
   `verified` is `unchecked`.

Every rewrite is recorded with its rule (FR-5).

### FR-3 API index and verification (Angular)

- **Source.** Angular publishes its public API as golden files:
  `goldens/public-api/<entry-point>/index.api.md` in `angular/angular` (`index.md` before v19),
  for example `core/index.api.md`, `core/testing/index.api.md`, `core/rxjs-interop/index.api.md`,
  `router/index.api.md`. They are API Extractor reports: a ```` ```ts ```` block with
  `export class X {`, `export interface X<T> extends Y {`, `export function f(…)`,
  `export const X: Y;`, members indented by four spaces.
- **Fetch.** For a hop `from → to`, list the goldens of both version tags with one request,
  `git/trees/<tag>:goldens/public-api?recursive=1` (paths stay relative to the goldens root, so
  the entry point is kept), then read each file from `raw.githubusercontent.com`. Use
  `GITHUB_TOKEN` (021); populate runs pass no token, so the configured one is the default.
  Cache under `ARTIFACT_CACHE_DIR/api-index/angular/<version>.json`, keyed by a parser version.
- **Parse.**
  - Exported declarations (`class`, `abstract class`, `interface`, `function`, `const`, `type`,
    `enum`, `namespace`; optional `declare`) give the symbols of the entry point.
  - Members are the identifiers at brace depth 1 of the declaration's block. For a function
    that is the inline options object of its signature
    (`provideCheckNoChangesConfig(options: { exhaustive: false; })`). Overloads union.
  - Non-exported declarations become public through `export { NgForOf }`,
    `export { NgForOf as NgFor }`, `export { Location_2 as Location }`.
  - Re-exports of imported symbols (`import { DOCUMENT } from '@angular/core'` +
    `export { DOCUMENT }`) are skipped: the declaring package owns the symbol.
  - `export const TestBed: TestBedStatic;` adds the members of `TestBedStatic` to `TestBed`.
- **Resolve.**
  - LLM `package` given and in the found set → keep it, `verified: true`;
  - symbol found in exactly one entry point → fill `package`, `verified: true`;
  - several entry points → the one matching a `dependency` entity of the same rule, else the
    primary entry point (non-`…/primitives/…`, non-`…/testing`, or the single ancestor of the
    rest: `@angular/core` over `@angular/core/primitives/di`), else `verified: ambiguous`,
    package `?` (for example `VERSION`, or `DOCUMENT` across 19 → 20 where it moved packages);
  - not found in either version → `verified: false`;
  - member: verified when the owner resolves and the member appears in its block.
- **Partial and offline.** A version whose goldens cannot be loaded (for example a `to` tag
  that does not exist yet) is listed in `missing_versions` and the index is `partial`; it is
  still used, and misses are recorded as `verify:not-in-partial-index`. If no version loads,
  populate continues, every npm entity gets `verified: false`, and the summary records
  `api_index: unavailable`.
- `syntax`, `diagnostic` and `property` are not checked against the index. `property` is
  verified when its `file` is known.
- An existing `Version` node is skipped **before** canonicalization (no fetch, no audit),
  except with `--dry-run`.

### FR-4 Graph writes

1. **Merge identity.** `_write_affected_entity`, step-entity writes and `_replacement_pairs`
   `MERGE` / `MATCH` on `{key}` and `SET` `name`, `package`, `symbol`, `member`, `file`,
   `ecosystem`, `verified`.
2. **Labels.** `class`, `member` → `Class`. `property` → `ApplicationProperty`. `dependency` →
   `Dependency`. New `syntax` → `TemplateSyntax` with `AFFECTS_SYNTAX`. New `diagnostic` →
   `DiagnosticCode` with `AFFECTS_DIAGNOSTIC`. Version lifecycle edges (`REMOVES`, `INTRODUCES`,
   `DEPRECATES`) work for all labels.
3. **Constraints** (`graph/indexes.py`): replace `class_name`, `property_name` and
   `dependency_name` uniqueness with `*_key IS UNIQUE` plus a plain index on `name`. `name` is no
   longer unique: `VERSION` exists in several Angular entry points.
4. **Compatibility.** After canonicalization no `Class` or `ApplicationProperty` name contains
   `:`, so the `groupId:artifactId` heuristic in `mcp/matching.py` only sees real dependencies.
   The one MCP change is a test that asserts this.
5. `seed_deprecated_classes` merges on `maven:<FQCN>` keys.

### FR-5 Audit artifacts

- **`runs/canonical/<framework>-<from>-to-<to>-canonical.jsonl`**: one line per entity
  occurrence: `ruleId`, raw `kind` / `name`, canonical fields, the FR-2 / FR-3 steps that were
  applied, and `verified`.
- **`…-summary.json`**: counts per kind, % `verified: true`, `ambiguous`, `false`, the number of
  raw names that collapsed into one key, `api_index` status and versions.
- `--dry-run` writes both files without graph writes. That is the cheap way to review a hop.

### FR-6 Prompt naming rules

- `DOSSIER_ENTITY_PROMPT` gets a `{naming_rules}` block per framework profile (the same
  mechanism as `{subsystem_check}`).
- `AffectedEntity` gets an optional `package: str = ""`. Old JSON stays valid.
- Angular rules:
  - `name` is the bare exported symbol;
  - put the import path in `package`;
  - methods, fields and options are `Owner.member`;
  - template operators and block keywords use `kind: "syntax"`;
  - `NGxxxx` uses `kind: "diagnostic"`;
  - config keys are full dotted paths;
  - never put a package inside `name`.
- `kind` in the prompt grows to `class | member | property | dependency | syntax | diagnostic`.
- Bumps `DOSSIER_ENTITY_PROMPT_VERSION`, so the next entity run re-runs every cluster. This is
  shipped separately from FR-1–FR-5 and is not needed for them.

### FR-7 Rollout

1. Run populate with `--dry-run` on the Angular hops and review `runs/canonical/` (AC-6).
2. On the target DB, remove the `MigrationRule`, `MigrationStep`, `Class`,
   `ApplicationProperty` and `Dependency` nodes. Keep `Version`, `BreakingScope`,
   `MigrationContext`, `LifecycleAlert` and `OpenRewriteRecipe`.
3. Drop the old name constraints and create the key constraints (`graph/indexes.py` startup).
4. `scripts/populate_graph.py --all --force`, then `seed_deprecated_classes`.
5. Re-run the verification scripts and the MCP live probe on one Spring Boot and one Angular
   project.

All frameworks are rebuilt together, because entity nodes are shared across frameworks and a
partial rebuild would leave keyless nodes behind.

---

## Acceptance Criteria

**Unit**

1. **AC-1** Normalizer, from the real Angular cases:
   - `@angular/core InjectFlags`, `@angular/router:Router`,
     `@angular/core/rxjs-interop RxResourceOptions` → package + bare symbol;
   - `TestBed.get` as `class` and as `property` → the same `member` key;
   - `exhaustive` in the `provideCheckNoChangesConfig` rule → `provideCheckNoChangesConfig.exhaustive`;
   - `in`, `void` → `syntax`; `NG8115` → `diagnostic`;
   - `engines.node` → `cfg:package.json#engines.node`;
   - `@Attribute` → `Attribute`.
2. **AC-2** API index on a fixture golden file: single, multiple and missing entry points, LLM
   package kept or overridden, member check, removed-in-`to` symbol found via `from`.
3. **AC-3** Populate twice with the same input → no new nodes. Two rules naming `InjectFlags` and
   `@angular/core InjectFlags` share one node. `VERSION` from two entry points → two nodes.
4. **AC-4** Index fetch fails → populate succeeds, all npm entities `verified: false`, summary
   says `unavailable`.
5. **AC-5** Spring Boot `runs/json` files: every `name` is byte-for-byte unchanged and every
   `key` is `maven:` / `cfg:application.properties#`.

**Graph (after FR-7 on the 3 Angular hops)**

6. **AC-6**
   - no `Class` / `ApplicationProperty` name contains `:` or a space;
   - no node exists both as `Class` and as `ApplicationProperty` with the same `name`;
   - 0 keys collide after normalization (no two nodes for one symbol);
   - ≥ 80% of distinct npm `class` / `member` nodes are `verified: true`, and every `false` one
     is listed in the summary and checked manually (calibrated on the 2026-11-06 dry run, see
     Open Question 3);
   - every rule that had an entity anchor before still has at least one.
7. **AC-7** MCP live probe on one Spring Boot project: `analyze_upgrade_path` returns the same
   matched rules as before the rebuild.

## Implementation Notes

- New package `migration_oracle/pipeline/canonical/`:
  - `profiles.py` (per-framework packages, token lists, config prefixes)
  - `normalize.py` (FR-2)
  - `api_index.py` (FR-3 fetch, parse, cache)
  - `run.py` (canonicalize one batch, write FR-5 artifacts)
- `models/entities.py`: `EntityKind` gains `member`, `syntax`, `diagnostic`. `AffectedEntity`
  gains optional `package`. A separate `CanonicalEntity` model carries the FR-1 fields.
- `pipeline/populator.py`: `populate_graph` canonicalizes the batch first. `_entity_label` /
  `_edge_type` cover the new kinds. Writes go through `key`.
- `graph/indexes.py`: constraint swap (FR-4.3). `_EXPECTED_CONSTRAINTS` updated.
- `_paths.py`: `RUNS_CANONICAL` and its path helpers.
- Tests: `tests/pipeline/test_canonical_*.py`, golden-file fixture under `tests/fixtures/api-index/`.
- Docs: canonicalization phase in
  `docs/02-extraction-pipeline/export-extract-populate-framework-pipeline.md`, graph schema doc
  (new labels, `key`), `CHANGELOG.md`.

## Open Questions

1. What does the Angular codebase scan put in `scanned_classes` / `scanned_class_simple`: bare
   symbols, or `package` + symbol? If it has the import path, matching on `package` + `symbol`
   removes cross-package false hits (`VERSION`). Settle this before the service-relevance spec.
2. Should `TemplateSyntax` and `DiagnosticCode` be new labels (as specified) or properties on the
   rule? New labels keep FR-1 uniform and give the relevance spec something to detect. The
   downside is two more node types in the schema doc.
3. ~~Is a 90% verified rate (AC-6) realistic?~~ Measured 2026-11-06 on the 8 Angular hops
   (`--dry-run`): 86% of npm occurrences and 80% of distinct class/member keys are
   `verified: true`, 1 `ambiguous` (`DOCUMENT`, moved packages). The `false` ones are internal or
   non-public names (`EffectScheduler`, `PendingTasksInternal`, `@angular/compiler` AST classes,
   `BazelAndG3Options`), symbols new in 22.0.0 whose tag does not exist yet (`partial`), and
   LLM-invented members (`Route.guards`). AC-6 is set to 80%.

## Estimate

~2 days:

| Work | Effort |
|---|---|
| Canonical model, profiles, normalizer + AC-1 | 4 h |
| API index fetch / parse / cache + AC-2, AC-4 | 4 h |
| Populator on `key`, new labels, constraints + AC-3, AC-5 | 3 h |
| Audit artifacts, `--dry-run` review on Angular hops | 2 h |
| Rollout on the 8003 DB, AC-6 / AC-7, live probe | 2 h |
| Prompt naming rules (FR-6), shipped separately | 1 h |

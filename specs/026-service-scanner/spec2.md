# Feature Specification 026.2: npm Manifests, tsconfig, Angular Version

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Implemented (2026-11-06)

**Depends on**: spec1 (CLI, discovery, modules, profile writer, extractor contract).
Shared context (problem, principles, non-goals, profile schema): see `spec1.md`.

**Scope**: manifest readers for `package.json`, `package-lock.json`, `angular.json`,
`tsconfig*.json`, and the Angular version detector. No source parsing yet.

## Requirements

### FR-3 Framework detection (Angular part)

- **Angular module**: only a module whose `package.json` declares `@angular/core` in any
  dependency scope. A hoisted `node_modules/@angular/core` in a shared workspace lockfile does
  not make a sibling package (a Node `server`) Angular.
- **Angular version**, per Angular module:
  1. `package-lock.json` `packages["node_modules/@angular/core"].version`;
  2. else the declared `@angular/core` range kept as written (`"^19.2.0"`) and a normalized
     `19.2.0` (lowest version satisfying the range; `>1.2` → `1.3.0` as in npm).
- Result → `modules[].frameworks[] = {name: "angular", version, raw, source}`; the repo-level
  `framework` is chosen as in spec1 FR-3.

### FR-4 npm manifests

**`package.json`**
- `dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies` →
  `dependencies[]` with `{key: "npm:<name>", name, range, version, version_source, scope,
  module}`. `version` comes from `package-lock.json` when present (`version_source: lockfile`),
  else the lowest version the range allows (`range`), else `null`.
- **Lockfile lookup**: the module's own `package-lock.json`, else the nearest one in a parent
  directory up to the scan root (an npm workspace root need not be the scan root:
  `frontend/package-lock.json` serves `frontend/packages/ui`).
- Config keys (scalars only, values truncated to 200 chars): `engines.*`, `type`,
  `browserslist`, `overrides.*`, `resolutions.*`, `workspaces` →
  `cfg:package.json#<dotted path>`.
- The package `name` and `workspaces` package names are collected as **own packages**.
  `modules[].own_packages` lists each module's own names; source extractors get the repo-wide
  union (used by spec3 to skip own-code imports of any sibling package).

**`angular.json`**
- Every scalar leaf → `cfg:angular.json#<dotted path>`, with the project name replaced by `*`:
  `projects.*.architect.build.builder = "@angular-devkit/build-angular:application"`.
  The real project names are kept in `modules[].angular_projects`.
- Builders (`…architect.<target>.builder`) are also listed per target, because many rules are
  keyed on the builder.

**`tsconfig*.json`** (also needed to resolve imports in spec3 / spec4)
- JSON with comments and trailing commas is accepted. `extends` is followed inside the repo
  (an `extends` pointing into `node_modules` or outside the repo → diagnostic, not followed).
- `compilerOptions.paths` and `baseUrl` are stored on the module as the **effective path
  map**, for import resolution in spec3 / spec4.
- Scalar leaves of `compilerOptions.*` and `angularCompilerOptions.*` →
  `cfg:tsconfig.json#<dotted path>`. Values come from the effective config after `extends`.

## Acceptance Criteria

- **AC-8 npm manifests**: `package-lock.json` version beats the range; with no lockfile the
  range is kept as `raw` and normalized to the lowest satisfying version; `angular.json`
  project name normalized to `*` and real names in `angular_projects`; builders listed per
  target; `tsconfig` `extends` and comments / trailing commas; effective `paths` after
  `extends`; all four dependency scopes recorded with the right `scope`.
- **AC-8.2**: an npm workspace fixture (root + two packages) → three modules, workspace
  package names recorded as own packages, each module with its own dependencies.
- **AC-8.3**: a broken `package.json` → diagnostic, the scan continues and exits `0`.
- **AC-8.4** (review 2026-11-06):
  - a workspace with a hoisted `@angular/core` in the root lockfile → only the package that
    declares it is an Angular module;
  - `frontend/package-lock.json` gives the installed version to `frontend/packages/ui`;
  - a lockfile > 2 MB is read, not skipped;
  - `version_source` is `lockfile`, `range` or `null`;
  - the build target's `tsConfig` wins over later targets, whatever their names;
  - `>1` → `2.0.0`, `>1.2` → `1.3.0`, `>1.2.3` → `1.2.4`.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec1 in the default order) must still pass unchanged; a failing earlier test is a regression, not an outdated test.

## How to test after spec2

```bash
migration-scan /path/to/angular-service
jq '.framework, (.dependencies | length), [.config[].key] | unique' .migration/profile.json
```

Expected: `angular <version>` in the summary line, all declared npm dependencies with lockfile
versions, `cfg:angular.json#projects.*.architect.build.builder` present. Compare
`framework.version` with `npm ls @angular/core`.

## Implementation Notes

- Module: `migration_planner/scanner/npm_manifests.py`.
- Stdlib `json` plus a small comment / trailing-comma stripper for tsconfig (no new dependency).
- Range normalization: small own implementation for `^`, `~`, `>=`, exact and `x` ranges;
  anything else → `version: null` + diagnostic.

## Open Questions

1. `yarn.lock` / `pnpm-lock.yaml` for exact npm versions: needed if services use them.

## Estimate

~3.5 h: readers 3 h, fixtures and tests 0.5 h.

# Feature Specification 026.2: npm Manifests, tsconfig, Angular Version

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Draft

**Depends on**: spec1 (CLI, discovery, modules, profile writer, extractor contract).
Shared context (problem, principles, non-goals, profile schema): see `spec1.md`.

**Scope**: manifest readers for `package.json`, `package-lock.json`, `angular.json`,
`tsconfig*.json`, and the Angular version detector. No source parsing yet.

## Requirements

### FR-3 Framework detection (Angular part)

- **Angular version**, per module:
  1. `package-lock.json` `packages["node_modules/@angular/core"].version`;
  2. else `package.json` `dependencies["@angular/core"]` with its range kept as written
     (`"^19.2.0"`) and a normalized `19.2.0` (lowest version satisfying the range).
- Result → `modules[].frameworks[] = {name: "angular", version, raw, source}`; the repo-level
  `framework` is chosen as in spec1 FR-3.

### FR-4 npm manifests

**`package.json`**
- `dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies` →
  `dependencies[]` with `{key: "npm:<name>", name, range, version, scope, module}`. `version`
  comes from `package-lock.json` when present.
- Config keys (scalars only, values truncated to 200 chars): `engines.*`, `type`,
  `browserslist`, `overrides.*`, `resolutions.*`, `workspaces` →
  `cfg:package.json#<dotted path>`.
- `workspaces` package names are collected as **own packages** (used by spec3 to skip own-code
  imports).

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

# Feature Specification 026.5: Angular Templates + Angular Real-Service Check

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Draft

**Depends on**: spec3 (`@Component` detection for inline templates), spec4 (for the full
real-service check). Shared context: see `spec1.md`.

**Scope**: template syntax tokens from `.html` and inline templates. Closes the Angular track
with the real-service acceptance check.

## Requirements

### FR-6 Angular templates

- **Sources**: `*.html` files, and inline `template:` string / template literals of
  `@Component` (location = the line inside the `.ts` file).
- **Tokens**: the Angular token list from `migration_keys/` (moved from
  `pipeline/canonical/profiles.py` in spec1): `@if`, `@for`, `@switch`, `@defer`, `@let`,
  `@empty`, …. Matched lexically, block keywords at the start of a block. Expression tokens
  (`in`, `void`, `typeof`, `as`) are counted only inside bindings: `{{ … }}`, `[prop]="…"`,
  `(event)="…"`, `*dir="…"`, `@if (…)`, `@for (…)`.
- **Structural directives and pipes**: `*ngIf`, `*ngFor`, `*ngSwitchCase`, … are recorded as
  `syntax:angular-template#*ngFor`. Pipe names in bindings (`| async`, `| date:…`) as
  `syntax:angular-template#pipe:date`. `||` is not a pipe.
- HTML comments (`<!-- … -->`) are ignored.
- Output: `templates[]` with `{key, count, locations}`, bounded by `--max-locations`.
- `*.html` files that are not Angular templates (no module with an Angular framework) are not
  scanned.

## Acceptance Criteria

- **AC-4 Templates**: `.html` and inline template with `@if`, `@defer`, `*ngFor`,
  `{{ a in b }}`, `| date` → the expected keys. `in` in plain text outside a binding → not
  counted. `a || b` in a binding → no pipe. A token inside an HTML comment → not counted.
  Inline template location = the right line in the `.ts` file.
- **AC-11 (Angular half)** on one real Angular service of ≥ 1 000 source files:
  - completes in < 30 s cold on a laptop (warm timing is checked in spec9);
  - profile < 2 MB;
  - a manual spot check of 10 random import sites finds every external import recorded with
    the right key and line;
  - every 025 Angular entity key from `runs/canonical/` that the service really uses (found
    with `grep`) is in the profile. Every miss is explained in the report.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec4 in the default order) must still pass unchanged; a failing earlier test is a regression, not an outdated test.

## How to test after spec5

```bash
migration-scan /path/to/angular-service --force
jq '.templates[] | {key, count}' .migration/profile.json
grep -rn "@defer\|\*ngFor" src --include=*.html | wc -l   # compare with the counts
```

The AC-11 result (timings, size, spot-check table, missed 025 keys with reasons) is written to
`specs/026-service-scanner/ac11-angular.md`.

## Implementation Notes

- Module: `migration_planner/scanner/templates.py`. A small lexer, no HTML parser dependency.
- Inline templates come from the spec3 decorator pass (`template:` property of `@Component`).

## Estimate

~5.5 h: templates 3 h; fixtures and tests 1 h; AC-11 Angular 1.5 h.

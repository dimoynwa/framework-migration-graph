# Feature Specification 026.7: Java Sources

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Draft

**Depends on**: spec1 (extractor contract), spec6 (declared groupIds for FQCN usages).
Shared context: see `spec1.md`.

**Scope**: per-file extraction of external imports and their usages from `*.java`, plus the
own-package post-pass.

## Requirements

### FR-7 Java sources

Parsed with **tree-sitter-java**.

- **Own packages**: every `package x.y;` declared in the scanned sources. Imports whose package
  equals or starts with an own package are not recorded. This is a post-pass (spec1 contract),
  since the own-package set is only known after all files are read.
- **Imports**:
  - `import a.b.C;` → `maven:a.b.C`
  - `import a.b.C.Inner;` → `maven:a.b.C.Inner`
  - `import static a.b.C.m;` → member `maven:a.b.C.m`
  - `import a.b.*;` → `maven:a.b.*` in `wildcard_imports`. Simple names used in the file that
    are not otherwise imported (and not declared in the file or its own package) are listed
    under it, so a matcher can test `a.b.X`.
  - `import static a.b.C.*;` → `maven:a.b.C.*`
- **Usages** of an imported simple name `C` (all recorded at the usage site, keyed by FQCN):
  - type use (fields, parameters, `extends`, `implements`, generics, `new C(…)`, casts);
  - annotations `@C` and `@C(attr = …)` → the attribute names become members
    (`maven:…RequestMapping.method`); `@C("x")` → member `value`;
  - static / qualified calls and field reads `C.m(…)`, `C.FIELD` → member `maven:a.b.C.m`.
- **Fully qualified usages without import** (`org.x.Y.z()`, `@org.x.Ann`) are recorded when the
  qualified name starts with a dependency's groupId (spec6).
- Instance calls on variables are not resolved (Non-Goals, spec1).
- `src/test/java/**` → `test: true`.

## Acceptance Criteria

- **AC-5 Java**: single, nested, static, wildcard and static-wildcard imports; annotation with
  attributes; `C.m()`; own-package imports skipped; FQCN usage without import.
- **AC-5.2**: wildcard import with two used simple names → both listed under the wildcard
  entry; a name declared in the same file is not listed.
- **AC-5.3**: `@MockBean` in `src/test/java` → location with `test: true`.
- **AC-5.4**: a Java file with a syntax error → imports that parsed are still recorded,
  diagnostic added.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec6 in the default order) must still pass unchanged; a failing earlier test is a regression, not an outdated test.

## How to test after spec7

```bash
migration-scan /path/to/spring-service --force
jq '[.symbols[] | select(.key | startswith("maven:org.springframework"))] | length' .migration/profile.json
jq '.members[] | select(.key | test("RequestMapping"))' .migration/profile.json
grep -rn "^import org.springframework" src/main/java | shuf -n 10   # spot-check against the profile
```

## Implementation Notes

- Module: `migration_planner/scanner/java.py`.
- New dependency: `tree-sitter-java` (prebuilt wheel).

## Open Questions

1. Kotlin sources in Spring services: tree-sitter-kotlin exists. Is any target service Kotlin?

## Estimate

~5 h: Java sources 4 h; fixtures and tests 1 h.

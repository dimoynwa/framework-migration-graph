# Feature Specification 026.7: Java Sources

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Implemented (2026-11-07). AC-5, AC-5.2, AC-5.3 and AC-5.4 met.

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
  qualified name starts with a dependency's groupId (spec6) **or that groupId's parent**
  (`org.springframework.boot` → `org.springframework`). A parent needs at least two segments, and a
  parent that is, contains or lies under one of the repo's own groupIds is not used.
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

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec6 in the default order) must still pass. A failing earlier test that checks **behavior** is a regression, not an outdated test. A test that pins an internal detail (the exact contents of a registry, a private helper's shape) may be changed deliberately when this spec extends that detail; such a change is named in the spec's CHANGELOG entry.

## How to test after spec7

```bash
migration-scan /path/to/spring-service --force
jq '[.symbols[] | select(.key | startswith("maven:org.springframework"))] | length' .migration/profile.json
jq '.members[] | select(.key | test("RequestMapping"))' .migration/profile.json
grep -rn "^import org.springframework" src/main/java | shuf -n 10   # spot-check against the profile
```

## Implementation Notes

- Module: `migration_planner/scanner/java.py`. New dependency: `tree-sitter-java` (prebuilt
  wheel).

## Implementation record (2026-11-07)

- **Contract additions the spec needed.** `Usage.names` carries a wildcard entry's simple names,
  and `FileFacts.package_name` carries the `package x.y;` so the post-pass can find the Java
  files (`None` for every other language). `PostPassContext.files` became a mutable `dict`: the
  own-package filter must *remove* facts, so `scan()` now merges every file's facts **after** the
  post-passes — a post-pass may return a fragment (spec4's barrels) or replace a file's facts
  (this filter).
- **Decisions taken where the spec is silent.**
  - A statically imported **nested type** (`import static a.b.Outer.Inner`) is a symbol, not a
    member: it binds a type name.
  - A chain records the **first segment after the class**, the rule spec3 already uses, so
    `RequestMethod.GET.name()` is `maven:…RequestMethod.GET`.
  - Two wildcard packages both list a name neither import explains: without a classpath the
    scanner cannot tell which declares it, and a missing name would drop a rule that applies.
  - A simple name is only a wildcard candidate when it is capitalized, and `java.lang` types are
    never candidates (they are imported implicitly). A name the file's own package declares, or
    an own package the file imports with a wildcard declares, is dropped by the post-pass.
  - A statically imported name is a nested type when it is CamelCase (a capital first letter and
    a lower-case letter): `Entry` is a symbol at the import line too, `APPLICATION_JSON` and
    `assertEquals` stay members.
  - An annotation only a class wildcard can supply keeps its attributes: one member per
    attribute under every class wildcard of the file
    (`maven:…web.bind.annotation.RequestMapping.method`), the policy `names` follows. The
    post-pass drops the ones whose annotation an own package supplies, unless the file also
    imports that class explicitly. A qualified call `C.m()` on a wildcard-supplied `C` stays a
    name under the wildcard only.
- **The fixture.** `tests/fixtures/scanner/spring-java/`: main and test sources, a nested own-type
  import, both wildcard forms, a fully qualified usage with no import, and a file with a syntax
  error. 48 tests in `tests/scanner/test_java.py` at first, 59 after the review fixes.
- **Real-file check.** A realistic 78-line Spring service (constructor injection, `@Value`,
  `@PreAuthorize`, `ResponseEntity.status(…).build()`, a `Collectors` chain, a `static` constant
  import, `import …web.bind.annotation.*;` next to `import java.util.*;`): every external import
  recorded at its own line, `…RequestMapping.method` / `…RequestMapping.value` from the
  annotations, `MediaType.APPLICATION_JSON_VALUE` from the static import, and
  `ServletUriComponentsBuilder.fromCurrentRequest` / `Collectors.groupingBy` /
  `LoggerFactory.getLogger` from the qualified calls — zero diagnostics.
- **Regression.** Whole scanner suite plus the 025 key test (`tests/pipeline/test_shared_keys.py`):
  559 passed, 0 skipped; with `tests/pipeline/test_canonical_*.py` as well, 624 passed.

## Review fixes (2026-11-07)

Found when the implementation was verified on a realistic starter-only Spring service:

1. **Parent groupId.** A starter-only pom declares just `org.springframework.boot`, so
   `org.springframework.util.Assert.notNull(…)` with no import was lost. The parent groupId now
   counts as well (FR-7 above). `ModuleEnv.own_group_ids` is new, so the extractor can keep a
   parent away from the repo's own code; `ModuleEnv.group_ids` is unchanged (spec6 tests pin it).
2. **Annotation attributes under a wildcard** (`@RequestMapping(path = …)` with
   `import …annotation.*`) were not members at all. Now recorded, see the decision above.
3. **Own-wildcard names.** `Widget` from an own `import com.acme.x.sub.*` was listed under an
   external wildcard's `names`. The post-pass now drops the types of every own package the file
   imports with a wildcard.
4. **`import static a.b.Outer.Inner`** was a member at the import line and a symbol at its uses.
   Now a symbol at both.
5. **Comments in a name** (`import org.x /* c */ .Y;`) ended up in the key. Stripped. While at it,
   the `static` keyword is read from the parse tree: `import statics.Foo;` was read as a static
   import with the key `maven:s.Foo`.
6. The regression counts above were corrected.

After the fixes: 59 tests in `tests/scanner/test_java.py`; scanner suite plus
`test_shared_keys.py` 570 passed; plus `test_canonical_*.py` 635 passed, 0 skipped.

## Open Questions

1. Kotlin sources in Spring services: tree-sitter-kotlin exists. Is any target service Kotlin?

## Estimate

~5 h: Java sources 4 h; fixtures and tests 1 h.

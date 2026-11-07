# Feature Specification 026.8: Spring Configuration Files + Spring Real-Service Check

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Implemented (2026-11-07). AC-8a and the Spring half of AC-11 met; the AC-11 result
is in `ac11-spring.md`.

**Depends on**: spec1 (modules, profile writer), spec6 (Java module detection), spec7 (for the
full real-service check). Shared context: see `spec1.md`.

**Scope**: Spring `application*` / `bootstrap*` property files → canonical config keys, with
secret redaction. Closes the Java track with the real-service acceptance check.

## Requirements

### FR-8a Spring configuration files

Many Spring Boot rules are property renames or default changes (`spring.data.mongodb.*` →
`spring.mongodb.*`), so the property keys a service sets are part of its profile.

**Files**: `application*.properties`, `application*.yml`, `application*.yaml`,
`bootstrap*.properties`, `bootstrap*.yml`, `bootstrap*.yaml`, anywhere in a Java module that is
not skipped (spec1 FR-2): typically `src/main/resources`, `src/test/resources`, `config/`.
- The Spring profile comes from the file name: `application-prod.yml` → `profile: prod`;
  `application.yml` → `profile: default`.
- `test: true` for files under `src/test/`, Maven's `src/it/`, or a test source set
  `src/<name>Test/` (spec1 FR-1).
- `kind: application | bootstrap`. Bootstrap files are recorded under the same keys: rules name
  the property, not the file. Their presence is also listed in `modules[].spring_config_files`,
  since some rules are about bootstrap itself (it needs `spring-cloud-starter-bootstrap` since
  Spring Boot 2.4).

**Parsing**
- `.properties`: Java properties format: `=`, `:` or whitespace separators, `#` / `!` comments,
  `\` line continuation, `\uXXXX` escapes. Own small parser (no dependency).
- `.yml` / `.yaml`: `yaml.safe_load_all` (PyYAML). Multi-document files (`---`) are split; a
  document with `spring.config.activate.on-profile` (or legacy `spring.profiles`) gets that
  profile. Nested maps are flattened to dotted keys, lists to `key[0].sub`. Anchors and merge
  keys are resolved by the loader. An unparsable file → diagnostic, the scan continues.
  Line numbers for YAML keys come from the loader's node marks (compose step).

**Key normalization** (Spring relaxed binding, canonical form as in Spring's metadata):
- `camelCase` and `snake_case` segments → `kebab-case`, lower-case:
  `spring.data.mongodb.authenticationDatabase` → `spring.data.mongodb.authentication-database`.
- Segments **after** a map-valued prefix keep their case, because they are map keys, not property
  names: `logging.level.*`, `spring.jpa.properties.*`, `spring.kafka.properties.*`,
  `management.metrics.tags.*`, `spring.cloud.gateway.routes[*].metadata.*`. The list lives in
  `migration_keys/` and can be extended.
- The written form is kept as `raw_key` when it differs.
- Key: `cfg:application.properties#<canonical key>`, the format 025 uses for Spring Boot
  properties. The real file goes in `file`.

**Values and secrets**: property files often hold credentials, and the profile must be safe to
keep in CI artifacts (spec1 Open Question 2).
- A value is **redacted** (`"<redacted>"`) when the key's last segment matches
  `password|passwd|secret|token|credential|api-key|apikey|private-key|client-secret` or the value
  contains a URL with user info (`scheme://user:pass@`).
- Placeholders are kept as written, never resolved: `${DB_PASSWORD}` and `${PORT:8080}`.
- Other values: scalars only, truncated to 200 chars. Lists and maps are recorded as keys only.
- New CLI flag `--no-values` stores no values at all (applies to every `config[]` entry,
  including the npm / Maven / Gradle ones): `value` is `null`. The flag is added to the
  `inputs_hash` options (spec1 FR-9).

**Output**: `config[]` entries
`{key, raw_key?, value, file, module, profile, kind, test, line}` (all fields already exist in
the spec1 `ConfigFact` / `ConfigEntry` model). The same key in several files or
profiles gives one entry per occurrence, so a matcher can tell "set only in `test`" from
"set in production".

## Acceptance Criteria

- **AC-8a Spring config**:
  - `.properties` with `:` / whitespace separators, continuation lines and `\u` escapes;
  - multi-document YAML with `spring.config.activate.on-profile`, and `application-prod.yml` →
    `profile: prod`;
  - `authenticationDatabase` → `authentication-database`, while
    `logging.level.com.Foo.BarService` keeps its case;
  - `spring.datasource.password=s3cret`, `client-secret`, and
    `jdbc:postgresql://u:p@host/db` → `<redacted>`; `${DB_PASSWORD}` kept as written;
  - `bootstrap.yml` keys recorded with `kind: bootstrap` and listed in `spring_config_files`;
  - a file under `src/test/resources` → `test: true`; an unparsable YAML → diagnostic only;
  - `--no-values` → `value` is `null` in every `config[]` entry.
- **AC-11 (Spring half)** on one real Spring Boot service of ≥ 1 000 source files:
  - completes in < 30 s cold on a laptop (warm timing is checked in spec9);
  - profile < 2 MB;
  - a manual spot check of 10 random import sites finds every external import recorded with
    the right key and line;
  - every Spring Boot property key from the 3.5.0 → 4.0.0 and 4.0.0 → 4.1.0 rules that the
    service sets (found with `grep` in its config files) is in the profile under the same key;
  - `grep` of the profile for the service's known secrets finds none.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec7 in the default order) must still pass. A failing earlier test that checks **behavior** is a regression, not an outdated test. A test that pins an internal detail (the exact contents of a registry, a private helper's shape) may be changed deliberately when this spec extends that detail; such a change is named in the spec's CHANGELOG entry.

## How to test after spec8

```bash
migration-scan /path/to/spring-service --force
jq '[.config[] | select(.key | startswith("cfg:application.properties#"))] | length' .migration/profile.json
jq '.config[] | select(.value == "<redacted>") | .key' .migration/profile.json
grep -c "<known secret>" .migration/profile.json   # → 0
```

The AC-11 result (timings, size, spot-check table, property-key check, secret check) is written
to `specs/026-service-scanner/ac11-spring.md`.

## Implementation notes

- Module: `migration_planner/scanner/spring_config.py`; the map-prefix list and the redaction
  rules in `migration_keys/spring.py`, so 025 and 026 build the same key. `pyyaml` was already a
  project dependency.

## Implementation record (2026-11-07)

- **`--no-values` lives in the accumulator**, not in the Spring reader: the spec says it applies
  to *every* `config[]` entry, and a flag enforced per reader would leave npm and Maven values in
  the profile. `scan()` passes it to `FactAccumulator`, `inputs_hash` records it.
- **Decisions taken where the spec is silent.**
  - `modules[].spring_config_files` lists **every** Spring config file, not only the bootstrap
    ones: the spec names bootstrap because that is where a presence rule lives, but an
    `application.yml` is exactly as much a file a rule may ask about, and a list that silently
    omitted it would be harder to explain than a complete one.
  - An **empty** map or list is a key with `""`: the service *sets* it, and `null` would collide
    with "no value stored" (`--no-values`).
  - A properties line with no key (`=value`) is an `unparsed_property` diagnostic; a `key` with
    no separator and no value (`e.bare`) is a legitimate property with an empty value.
  - A YAML key's `line` is the key's own mark; a value reached through a `<<` merge carries the
    line it was really written on, not the merge site.
- **Regression.** No earlier test needed changing for this spec: `--no-values` defaults to off
  and the Spring reader only adds `config[]` entries, which the fixtures without Spring files do
  not produce. Counts are under "Review fixes".

## Review fixes (2026-11-07)

Found when the implementation was verified. Secret redaction beyond the FR-8a list (placeholder
defaults, `password=` inside a connection string, maps under a `*-secrets` key) was deliberately
**not** changed: the profile is generated output that is never committed.

1. **`spring.profiles.active` is not a document profile.** It was in the list of profile keys, so
   the default document of an `application.yml` that sets it was filed under the active profile.
   Only `spring.config.activate.on-profile` and the legacy `spring.profiles` (also as a list,
   `spring.profiles[0]`) set it now, as FR-8a says.
2. **The profile key is compared in canonical form**, so `onProfile` is `on-profile`.
3. **Multi-document `.properties`.** FR-8a only names YAML, but Boot 2.4+ splits a `.properties`
   file at `#---` / `!---` the same way; a document's `on-profile` now sets its profile.
4. **A comment line ending in `\`** joined the next line into the comment, losing a property.
   Java never continues a comment line; neither does the parser now.
5. **025 used the property name as the key.** The implementation note says 025 and 026 build the
   same key, but `_normalize_maven` wrote `cfg:application.properties#<name as written>`. It now
   applies `canonical_key` for Spring Boot (the `name` is unchanged, 025 FR-2.7).
6. **Only Java modules.** A module is Java when it has a Maven / Gradle build file, or when the repo
   has one and the module is `.` or not an npm package. An Angular module's `application.yml` is
   no longer Spring config. `ManifestContext.repo_has_java_build` carries the repo-wide answer.
7. **Over-redaction.** `token-uri`, `access-token-validity-seconds`, `secret-header-name` were
   `<redacted>`; a secret word followed by a qualifier (`NON_SECRET_SUFFIXES`) keeps its value.
8. `mypy` clean for the two new modules (`yaml` import as elsewhere in the repo, the leaf type).
9. **Counts.** `pytest tests/scanner tests/pipeline/test_shared_keys.py` → 641 passed, 0 skipped;
   with `tests/pipeline/test_canonical_*.py` → 706 passed. 70 tests in
   `tests/scanner/test_spring_config.py`. AC-11 re-run on the same service: identical `config[]`
   (`ac11-spring.md`).

10. **Test source sets.** `src/integrationTest/`, `src/componentTest/`, `src/acceptanceTest/`,
    `src/apiTest/` — every `src/<name>Test/` — and Maven's `src/it/` are test paths now (spec1
    FR-1 amended), for
    sources and config alike, and `--no-include-tests` drops them. The Spring reader uses the
    discovery rule (`is_test_path`) instead of its own copy. On `paysafe-wallet-kyc` the 38
    `config[]` entries of `src/integrationTest/resources/*` and the 27 Java files under
    `src/integrationTest/java` now carry `test: true`. Suite: 726 passed (with `src/it/`).

## Estimate

~6.5 h: Spring config (properties, YAML, relaxed binding, redaction) 4 h; fixtures and tests
1 h; AC-11 Spring 1.5 h.

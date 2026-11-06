# Feature Specification 026.8: Spring Configuration Files + Spring Real-Service Check

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Draft

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
- `test: true` for files under `src/test/`.
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

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec7 in the default order) must still pass unchanged; a failing earlier test is a regression, not an outdated test.

## How to test after spec8

```bash
migration-scan /path/to/spring-service --force
jq '[.config[] | select(.key | startswith("cfg:application.properties#"))] | length' .migration/profile.json
jq '.config[] | select(.value == "<redacted>") | .key' .migration/profile.json
grep -c "<known secret>" .migration/profile.json   # → 0
```

The AC-11 result (timings, size, spot-check table, property-key check, secret check) is written
to `specs/026-service-scanner/ac11-spring.md`.

## Implementation Notes

- Module: `migration_planner/scanner/spring_config.py`; map-prefix list and the redaction
  pattern in `migration_keys/`.
- Dependency: `pyyaml` (already a project dependency).

## Estimate

~6.5 h: Spring config (properties, YAML, relaxed binding, redaction) 4 h; fixtures and tests
1 h; AC-11 Spring 1.5 h.

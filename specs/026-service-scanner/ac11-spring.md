# AC-11 (Spring half) — real-service check

Spec: `specs/026-service-scanner/spec8.md` (026.8, FR-8a Spring config).
Run: 2026-11-07, macOS 25.6.0 (darwin arm64), CPython 3.12, `migration-scan` from this tree.

## Status

**Met on a real Paysafe Spring Boot service.** Timing, profile size, the 10-import-site spot
check, the property-key check and the secret check all pass. The service also exercises the
interesting shape of the requirement: it is a **Spring Cloud Config** service, so most of its
properties are in `bootstrap*.yml` and it has three test profile files.

## Service under test

| Property | Value |
|---|---|
| Repository | `/Users/dimo.drangov/DevelopmentTools/paysafe-wallet-kyc`, commit `e26f8946f` |
| Framework | `spring-boot 4.0.6` |
| Files scanned | 1 459 (1 447 `.java` + 7 Spring config files + build manifests) |
| Profile written to | `/tmp/ac11spring/profile.json` (`--out`), so the service work tree stayed untouched |
| Spring config files | `src/main/resources/{application,bootstrap,bootstrap-local}.yml`, `src/test/resources/application.yml`, `src/integrationTest/resources/{application-component-test,bootstrap-component-test,bootstrap-api-test}.yml` |

## Timings and size

| Run | Wall clock | `duration_ms` | Profile |
|---|---|---|---|
| cold (`--force`) | **2.99 s** | 2 077 | **1 927 163 B (1.84 MB)** |

- **< 30 s cold: passed** (3.0 s) on 1 447 Java sources.
- **< 2 MB: passed**, but only just (1.84 MB). The size is dominated by Java **usage sites**,
  not by config: 636 symbols × 643 members with up to 20 locations each. A service with more
  `--max-locations` or a larger API surface would cross 2 MB — that budget question belongs to
  spec9 (`--max-locations` default / timings), and is recorded there.
- Summary line: `scanned 1459 files · spring-boot 4.0.6 · 52 deps · 636 symbols · 643 members ·
  153 config · 0 template tokens · 0 diagnostics`.

## Property keys: every one the service sets is in the profile

Method: the profile's own `modules[].spring_config_files` lists the seven files; each was
independently flattened with `yaml.safe_load_all` in a script that shares nothing with the
scanner except `migration_keys.spring.canonical_key`, and every leaf was looked up in the
profile's `config[]`.

| Files | Distinct profile config keys | Leaf keys in the service | Missing from the profile |
|---|---|---|---|
| 7 | 98 | **153** | **0** |

- **153 / 153 leaf keys present.** The file count and the entry count agree (45 `application` +
  108 `bootstrap`), so no document, list item or nested map was dropped.
- Profiles came out correctly: `default` 79, `local` 36, `component-test` 26, `api-test` 12 —
  matching the file names, plus a multi-document `spring.config.activate.on-profile`.
- Relaxed binding spot checks: `spring.cloud.vault.token`, `hmac-secret-key` (from
  `hmacSecretKey`), `spring.cloud.gateway.routes[0].metadata.*` are canonical; nothing under a
  map-valued prefix was lower-cased.

### The 3.5.0 → 4.0.0 and 4.0.0 → 4.1.0 rules

The canonical rule files for those hops do not exist yet (`runs/canonical/spring-boot-3.5.0-to-4.0.0-canonical.jsonl`
is absent — that is 027 ingestion, not 026). Extraction of the dotted names from the filtered
change sets (`runs/nodes/spring-boot-{3.5.0-to-4.0.0,4.0.0-to-4.1.0}-changes_filtered.md`) gives
31 candidates; **`grep` of the service's config files for every one of them returns nothing** —
this service sets none of them, so there is nothing for the profile to miss. The key-format side
of the check is covered by the 153/153 result above. The profile key is built by the same
`canonical_key` / `cfg_key` pair 025 uses — since the spec8 review fixes; before them 025 kept a
property key as written, so only kebab-case rule text would have matched.

## Secrets

| Check | Result |
|---|---|
| Literal `spring.cloud.vault.token` values in 3 files (`token`, `token`, `s.ylMwqzrGb5wt`) | all 4 entries `"<redacted>"` |
| `hmacSecretKey` (`qwerty`) | `"<redacted>"`, **0** occurrences of `qwerty` in the profile |
| **`s.ylMwqzrGb5wt`** | **0** occurrences in the profile |
| `spring.datasource.password` style values | `"<redacted>"` |
| Placeholders (e.g. `${vault.token.runtime}`) | kept as written, never resolved |

The one apparent hit for the literal string `token` is the **key name**
`cfg:application.properties#spring.cloud.vault.token`, not a value.

## Import sites — 10 random

Sampled from the profile (seed 7), then checked against the source: the recorded line must be
that symbol's import of the FQCN, or a use of a name the file imports from it.

| # | File | Line | Recorded key | Line is |
|---|---|---|---|---|
| 1 | `SkrillCountryHttpClient.java` | 29 | `maven:lombok.RequiredArgsConstructor` | `@RequiredArgsConstructor` |
| 2 | `KycVerificationController.java` | 33 | `maven:jakarta.validation.constraints.Min` | the `import` |
| 3 | `EwKycServiceTest.java` | 44 | `maven:org.mockito.Mockito` | the `import` |
| 4 | `DocumentObfuscator.java` | 47 | `…consumer.event.CustomerObfuscationEvent` | a parameter type |
| 5 | `EwKycUserApiMapperTest.java` | 177 | `…customer.api.model.KycVerification` | a local's type |
| 6 | `EwAuthenticationServiceTest.java` | 33 | `…test.util.ReflectionTestUtils` | the `import` |
| 7 | `DocumentManagementController.java` | 20 | `…annotations.media.Schema` | the `import` |
| 8 | `CustomerHttpClientTest.java` | 112 | `maven:org.junit.jupiter.api.BeforeEach` | `@BeforeEach` |
| 9 | `DocumentBoController.java` | 20 | `…bind.annotation.RestController` | the `import` |
| 10 | `AppConfig.java` | 30 | `maven:com.paysafe.ss.logging.EnableOneplatformTracing` | `@EnableOneplatformTracing` |

**10 / 10** — every location is a site where the file really names that class (spec7 records
both the import site and each use site; spec1 FR-9 explains why the use sites matter for
instance calls a scanner cannot resolve).

## Re-run

```bash
S=/tmp/ac11spring; R=~/DevelopmentTools/paysafe-wallet-kyc
time python -m migration_planner.scanner.cli $R --out $S/profile.json --force
jq '[.config[] | select(.key | startswith("cfg:application.properties#"))] | length' $S/profile.json
jq -r '.config[] | select(.value == "<redacted>") | .key' $S/profile.json
jq -r '.modules[].spring_config_files[]' $S/profile.json
grep -c "s.ylMwqzrGb5wt" $S/profile.json      # → 0
```

## Regression

```
pytest tests/scanner tests/pipeline/test_shared_keys.py tests/pipeline/test_canonical_*.py
  → 706 passed, 0 skipped   (after the spec8 review fixes)
```

Re-run after the review fixes (same commit of the service): 2.60 s wall clock, 1 927 163 B,
153 config entries, the same profile split, and a `config[]` byte-identical to the first run —
the service has no `spring.profiles.active`, no `#---`, no comment ending in `\` and no
`token-uri`, so none of the fixes changes its facts.

Re-run after test source sets became tests (spec1 FR-1 amended): the 38 `config[]` entries from
`src/integrationTest/resources/*` and every location in the 27 `src/integrationTest/java` files
now carry `test: true`; keys, values and counts are unchanged (153 config, 636 symbols,
643 members), profile 1 926 428 B. Suite: 721 passed.

## spec9 — warm-scan timings (AC-11, 2026-11-07)

Spec: `specs/026-service-scanner/spec9.md` (026.9, FR-10 incremental cache). Same service
(`paysafe-wallet-kyc`, commit `e26f8946f`, 1 447 Java sources), clean git work tree, profile and
cache written outside it (`--out /tmp/s9real/p.json`).

| Run | Wall clock | `duration_ms` | Profile | Parsed |
|---|---|---|---|---|
| cold (`--force`) | **1.32 s** | 1 000 | 1 926 428 B (1.84 MB) | 1 448 |
| warm (no change) | **0.75 s** | — (`unchanged`) | unchanged, not rewritten | 0 |
| warm (2nd) | **0.64 s** | — (`unchanged`) | unchanged, not rewritten | 0 |

- **< 30 s cold: passed** (1.3 s, down from 2.99 s in the spec8 run because `--jobs` defaults to
  the CPU count now). **< 3 s warm: passed** (0.6–0.8 s).
- Warm cost is discovery, not parsing: `git ls-files` 0.11 s + cache load 0.23 s + one `stat` per
  file. Parsing is 0 files.

### Incremental and `--jobs` checks

| Check | Result |
|---|---|
| Re-scan, no change | `unchanged`, `parsed_files: 0`, `cached_files: 1448`, profile not rewritten |
| Edit one `.java` file | `parsed_files: 1`, `cached_files: 1447`; profile equal to a `--force` scan except `at` / `duration_ms` |
| `--jobs 1` vs `--jobs 8` (forced) | byte-identical profiles except `at` / `duration_ms`; 2.0 s vs 1.0 s reported duration |
| Corrupt cache | `cache_corrupt` diagnostic, full scan, same facts |

### Cache size

`scan-cache.json` is 6.6 MB for 1 448 Java files. The encoding stores no file path per fact (an
extractor only reports facts about the file it was given, so the path is restored from the entry
key); doing so took the cache from 14 MB to 6.6 MB. It sits next to the profile, which is
generated output and already `.gitignore`d — no new ignore rule.

```bash
S=/tmp/s9real; R=~/DevelopmentTools/paysafe-wallet-kyc
time migration-scan $R --out $S/p.json --force    # cold
time migration-scan $R --out $S/p.json            # → unchanged
migration-scan $R --out $S/p.json --json-summary | jq '{parsed_files, cached_files, unchanged}'
```

### Packaging (AC-10b on this tree)

`uv build --wheel`, then a fresh `uv venv` + `uv pip install migration_oracle-0.1.0-py3-none-any.whl[planner]`
→ 11 packages (`migration-oracle`, `pydantic`, `pyyaml`, `tree-sitter`, `tree-sitter-java`,
`tree-sitter-javascript`, `tree-sitter-typescript` and their dependencies). `migration-scan` ran on
`tests/fixtures/scanner/angular-app` (exit 0, `angular 19.2.4`), and `neo4j`, `langchain`,
`langchain_core`, `httpx`, `mcp`, `sentence_transformers`, `streamlit` were all
`ModuleNotFoundError`. Automatable version: `tests/scanner/test_packaging.py`.

### After the spec9 review fixes (2026-11-07)

`spawn` workers on macOS (no more `fork`), `concurrent.futures` pool, cache named per root.
Same commit, `--out /tmp/s9b/p.json`:

| Run | Wall clock |
|---|---|
| cold `--force` (default `--jobs`, 12 CPUs) | 2.2–3.1 s |
| cold `--force --jobs 1` | 2.8 s |
| warm, no change | 1.3 s, `unchanged`, `parsed_files: 0` |

`--jobs 1` and `--jobs 8` profiles byte-identical except `at` / `duration_ms`. On macOS the pool
now gains little over `--jobs 1` for this size (`spawn` imports the grammars per worker); both
budgets (< 30 s cold, < 3 s warm) still hold. The cache is `scan-cache-11ebf7f5c2a6.json` next to
the profile. Service work tree untouched.

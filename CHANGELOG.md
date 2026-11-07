# Changelog

## [026.9-service-scanner] — 2026-11-07

### New features

- **Incremental scans (FR-10).** `.migration/scan-cache.json` stores, per source file, its
  `(size, mtime_ns)`, content `sha256`, the module-environment digest, the extractor's identity
  and the extractor's per-file facts. A re-scan parses only files whose stat moved *and* whose
  content hash then differs; a file whose `(size, mtime_ns)` is unchanged is not even read. When
  the whole input set is unchanged the profile is not rewritten at all and stdout ends with
  `unchanged` (AC-9b). Manifests are always re-read, and post-passes (barrels, own packages) run
  every time on the cached + fresh facts, so an incremental profile is byte-identical to a
  `--force` one.
- **The module environment is part of the cache key.** A source's facts also depend on what the
  manifest readers learned about its module (own package names, the effective tsconfig path map,
  declared / owned groupIds, detected frameworks), none of which live in the file's bytes.
  Editing a `package.json` therefore invalidates that module's cached sources instead of leaving
  stale facts behind.
- **`--force`** ignores the cache and re-parses everything; **a scanner version or cache-schema
  mismatch** drops the cache whole; **a corrupt cache** is one `cache_corrupt` diagnostic plus a
  full scan — never a failed scan. The cache is written atomically (temp file + rename), and it
  sits next to the profile, so `--out /tmp/x/profile.json` leaves the service work tree untouched.
- **Parallel parsing (FR-10).** `--jobs N` (default: CPU count; `1` = in-process) parses source
  files in a process pool. The parent does discovery, manifest reading, hashing and cache
  decisions; a worker only runs extractors and returns the same JSON-ready encoding the cache
  uses. Results are keyed by path, so **`--jobs 1` and `--jobs 8` are byte-identical** (AC-9c).
  Under 32 pending files it parses in-process (a pool costs more than the work), and a pool that
  cannot start falls back to in-process parsing instead of failing.
- **Packaging (AC-10b).** The base dependencies are now exactly what the scanner needs —
  `pydantic`, `pyyaml`, `tree-sitter*` — and the same set is named `[planner]`. The ingestion
  stack (Neo4j, LangChain, embeddings, MCP, Streamlit) moved to `[ingest]`, which the dev group
  and the Dockerfile install (`uv sync --no-dev --extra ingest`). A fresh venv with
  `pip install '.[planner]'` runs `migration-scan` with no `neo4j` or `langchain*` installed.
- **Summary line** gained the cache counts: `… (0.4 s, 3 parsed)` when some facts were reused,
  `… unchanged` when nothing changed, and `parsed_files` / `cached_files` in `--json-summary`.

### Tests

- `tests/scanner/test_incremental.py` (24): the cache file and its location (`--out` elsewhere),
  the JSON round-trip of every fact kind, AC-9b (unchanged → nothing parsed and the profile is not
  rewritten; one edited file → one parse, profile equal to `--force`; a `touch` with no edit
  reuses the facts; a deleted file leaves the cache; a manifest edit invalidates the module; an
  option change rewrites; a corrupt cache → diagnostic + full scan; a foreign scanner version →
  silent full scan), AC-9c (`--jobs 1` vs `--jobs 8`), the in-process threshold, the pool fallback,
  and the CLI flags.
- `tests/scanner/test_packaging.py` (5): the `[planner]` / `[ingest]` split, the entry point, the
  wheel's packages, and — when a wheel can be built — AC-10b end to end in a throwaway venv.
- Whole scanner suite: **688 passed, 1 skipped** (spec1–spec8 all green), plus the 025 shared-key
  and canonicalization suites. The one skip is `test_packaging.py`'s wheel build, which needs
  `uv`; AC-10b was verified by hand instead — a fresh `python -m venv` with
  `pip install '.[planner]'` pulls only `pydantic`, `pyyaml` and the four `tree-sitter`
  distributions (no `neo4j`, `langchain*`, `mcp`, `streamlit`, `torch`), and `migration-scan`
  runs and scans a fixture in that venv. Earlier specs' tests: one assertion **added** to
  `test_cli.py::test_out_flag_writes_where_asked` (with `--out` outside the repo there is no
  `.migration/` to warn about in stderr); everything else is additive —
  `Summary.parsed_files` / `cached_files`, `scan(jobs=, force=, use_cache=)` and two new test
  modules.

### Review fixes

- **A worker that dies no longer hangs the scan.** The pool is `concurrent.futures` instead of
  `multiprocessing.Pool`, which waited forever for a task lost with a crashed worker. The batches
  that did not come back are re-parsed one file per process; the file that kills its worker again
  is an `extractor_crash` diagnostic with no facts, not cached.
- **`cache_corrupt` is a run diagnostic, not a profile fact.** It is printed on stderr and listed in
  `--json-summary` as `run_diagnostics`. Before, a profile written after a corrupt cache kept the
  diagnostic forever (the next scans were `unchanged`), while the summary said `0 diagnostics`.
- **`--force` always rewrites the profile**, so a stale profile can be regenerated.
- **`spawn` everywhere but Linux.** `fork` was chosen wherever it existed, macOS included, where it
  is unsafe once the parent has threads (68 `DeprecationWarning`s in the suite).
- **Cache per root.** With `--out` outside the repo the cache is `scan-cache-<root digest>.json`,
  and every cache records its root: two services sharing an output directory no longer evict each
  other. `CACHE_SCHEMA` → 2.
- **Racy stat.** A file whose mtime is within 2 s of the caching scan's start is re-hashed instead
  of trusted by `(size, mtime_ns)` alone.
- **`--jobs` default** is the usable CPU count (`os.process_cpu_count()` / affinity), not the
  host's.
- `environment_digest` covers every `ModuleEnv` field through `dataclasses.fields` (a new field can
  no longer be left out); `mypy` clean for `cache.py`, `parallel.py`, `scan.py`, `cli.py`; the
  install docs name the real distribution, `migration-oracle[planner]`; the `pyproject.toml`
  comments describe what `uv sync` and the Dockerfile really do.
- Tests pinning the old behavior, changed on purpose: `test_force_ignores_the_cache_and_re_parses_every_file`
  (now `written`, not `unchanged`), `test_a_corrupt_cache_is_a_diagnostic_and_a_full_scan`
  (`run_diagnostics`, not the profile), `test_the_cache_lives_next_to_an_out_path_outside_the_repo`
  (the root-digest name). Suite after the fixes: `tests/scanner` 688 passed and 1 skipped (the
  `uv`-dependent wheel build), 763 tests green across the scanner and the 025 suites. One
  user-visible consequence: the `.gitignore` hint is now printed only when something really
  lands in the scanned repo, so `--out` elsewhere is silent.

### AC-11 (timings)

| Service | Cold (`--force`) | Warm (no change) | Budget |
|---|---|---|---|
| `paysafe-wallet-kyc` (1 447 Java) | **1.3 s** | **0.6–0.8 s** | < 30 s / < 3 s |
| `paysafe-wac-web-login-fe` (709 TS) | **0.8 s** | **0.4 s** | < 30 s / < 3 s |

Warm cost is discovery plus a `stat` per file, not parsing. Cache size: 6.6 MB for the Spring
service (facts stored without a per-fact file path, restored from the entry key — that halving was
a review fix) and 1.5 MB for the Angular one. Results in `ac11-spring.md` / `ac11-angular.md`.

### Contract additions

- `migration_planner/scanner/cache.py`: `CACHE_NAME`, `CACHE_SCHEMA`, `CachedFile`, `ScanCache`,
  `encode_facts` / `decode_facts` (shared by the cache and the pool), `environment_digest`,
  `extractor_id`.
- `migration_planner/scanner/parallel.py`: `ParseJob`, `ParseOutcome`, `parse_file`,
  `parse_parallel`, `default_jobs`, `MIN_FILES_FOR_POOL`, `CHUNK_SIZE`.
- `scan(..., jobs=0, force=False, use_cache=True)`; `ScanResult.parsed_files` / `cached_files` /
  `cache_path`.
- `profile.atomic_write_text` — the atomic writer, now shared by the profile and the cache.
- `profile.inputs_hash_from_digests` — `inputs_hash` over stored digests, so an unread (cached)
  file still contributes what a full scan would compute.
- CLI: `--jobs N`, and `--force` now does something.

## [026.8-service-scanner] — 2026-11-07

### New features

- **Spring configuration (FR-8a).** `migration_planner/scanner/spring_config.py` turns every
  `application*` / `bootstrap*` file of a Java module into `config[]` facts. One entry per
  occurrence, never merged by key, so the same key in two profiles, modules or files stays two
  facts and a matcher can tell "set only in test" from "set in production" (AC-8a).
- **Canonical keys.** Every Spring property canonicalizes to `cfg:application.properties#…` —
  the one file name rules use (025 FR-2.6) — whichever file really holds it; `config[].file`
  keeps the real path. Relaxed binding turns `authenticationDatabase` into
  `authentication-database`, while a segment after a **map-valued prefix** keeps its case:
  `logging.level.com.Foo.BarService`, `spring.jpa.properties.*`, `spring.kafka.*.properties.*`,
  `management.metrics.tags.*`, `spring.cloud.gateway.routes[*].metadata.*` (AC-8a). The prefix
  list, `canonical_key`, `is_secret_key` and `redact_value` live in the new
  `migration_keys/spring.py`, which 025 imports too, so a rule's key and a service's key cannot
  drift.
- **Profiles, kinds, tests.** The profile comes from the file name (`application-prod.yml` →
  `prod`, else `default`) or from a YAML document's `spring.config.activate.on-profile` (and the
  legacy `spring.profiles`); `kind` is `application` or `bootstrap`; `src/test/` gives
  `test: true`. `modules[].spring_config_files` lists every such file of the module, bootstrap
  included, because some rules are about a file's presence (a `bootstrap.yml` needs
  `spring-cloud-starter-bootstrap` since Boot 2.4).
- **Java properties parser (no dependency).** `=`, `:` and whitespace separators, `#` / `!`
  comments, `\` continuation (a physical line joins the logical one, and its line number is the
  first physical line) and `\uXXXX` escapes. A line with no key is an `unparsed_property`
  diagnostic, never a silent drop.
- **YAML via PyYAML's compose step.** `line` is the key's own mark, not its document's. Nested
  maps flatten to `a.b.c`, lists to `key[0].sub`, anchors and `<<` merge keys are applied (a key
  written in the document wins), multi-document files split by `---`, an empty map or list is a
  key with an empty value, and an unparsable file is one `yaml_parse_error` while the module's
  other files are still read.
- **Secrets never reach the profile (FR-8a).** A value is `"<redacted>"` when the key's last
  segment names a credential (`password`, `passwd`, `secret`, `token`, `credential`, `api-key`,
  `apikey`, `private-key`, `client-secret`, …) or the value is a URL with user info
  (`jdbc:postgresql://user:pass@host/db`). A placeholder (`${DB_PASSWORD}`, `${PORT:8080}`) is
  kept exactly as written — a reference, never resolved. Other values are truncated to 200
  characters; lists and maps become keys only. A suffix is not a token:
  `app.tokens-per-second` is not a secret.
- **`--no-values` (FR-8a, FR-1, FR-9).** `scan(..., no_values=True)` and the CLI flag store no
  config value at all — `value` is `null` in **every** `config[]` entry, npm and Maven ones
  included, because the accumulator applies it rather than one reader. It is part of
  `inputs_hash`, so a re-scan with the flag is never reported `unchanged` (spec9).

### AC-11 (Spring half)

Run on `paysafe-wallet-kyc` (1 447 Java sources, Spring Boot 4.0.6, a Spring Cloud Config service
whose properties are mostly in `bootstrap*.yml`): 1 459 files in **2.99 s**, profile 1.84 MB,
**153 / 153** leaf property keys of the seven config files in the profile under the canonical key,
10 / 10 sampled import sites correct, and no literal secret in the profile. The one budget
finding: 1.84 MB is close to the 2 MB limit, and it is driven by Java usage locations, not
config — a `--max-locations` question for spec9. Written up in
`specs/026-service-scanner/ac11-spring.md`.

### Review fixes

- **`spring.profiles.active` no longer sets a document's profile.** It activates a profile; the
  default document of an `application.yml` that sets it stayed under `local` before.
- **The profile key is matched in canonical form** (`spring.config.activate.onProfile`), and the
  legacy `spring.profiles` also counts as a list (`spring.profiles[0]`).
- **Multi-document `.properties`**: `#---` / `!---` splits the file, each document with its own
  `spring.config.activate.on-profile`.
- **A comment line ending in `\`** no longer swallows the next property.
- **025 builds Spring Boot property keys with `canonical_key`**, so a rule's camelCase property and
  the service's kebab-case one share a key. The entity `name` is still byte-for-byte as written
  (025 FR-2.7). Canonical JSONL written before this change keeps the old key until it is
  regenerated.
- **Only Java modules** are read: an npm module's `application.yml` in a Java repo, or any in a repo
  with no Java build, is not Spring config. New `ManifestContext.repo_has_java_build`.
- **`token-uri` and friends keep their value**: a secret word followed by a qualifier such as
  `uri`, `url`, `seconds`, `name` is a setting about the secret (`NON_SECRET_SUFFIXES`).
- `mypy` clean for `spring_config.py` and `migration_keys/spring.py`.
- **Gradle test source sets are tests** (spec1 FR-1 amended): every `src/<name>Test/` —
  `src/integrationTest`, `src/componentTest`, `src/acceptanceTest`, `src/apiTest` — and Maven's
  `src/it/` (maven-failsafe / maven-invoker) give
  `test: true` for sources and config, and `--no-include-tests` drops them. The Spring reader now
  uses the discovery rule instead of its own `src/test` check.

### Never silent

- An unparsable YAML is one `yaml_parse_error` with the loader's problem and line; an unreadable
  file is an `unreadable_file`; a `.properties` line with no key is an `unparsed_property`.
  None of them fails a scan.

### Tests

- `tests/scanner/test_spring_config.py` (76 tests): AC-8a (one entry per occurrence, never merged by key; the canonical key with relaxed binding and the map-prefix exceptions that keep their case; profile from the file name and from `spring.config.activate.on-profile`; `bootstrap` kind; the `test` flag), the properties parser (three separators, `#` / `!` comments, `\` continuation with its first-physical-line number, `\uXXXX`), the YAML compose step (a key's own mark, indexed list entries, anchors, `<<` merge keys, `---` documents), the secret rules (credential words, userinfo URLs, `NON_SECRET_SUFFIXES`, a placeholder kept as written) and `--no-values` including its effect on `inputs_hash`.
- New fixture `tests/fixtures/scanner/spring-config/`: `application.properties`, `application-prod.yml`, `bootstrap.yml`, a `src/test/resources/application.yml` and a broken `config/application-broken.yml` for the `yaml_parse_error` case.
- Additive tests in two earlier specs' files for the amended FR-1: `test_discover.py` gains the `src/<name>Test/` and `src/it/` source sets with their negatives, `test_java.py` one Gradle `src/componentTest` case. No earlier assertion changed.
- Whole scanner suite passes: 652 passed in `tests/scanner`, 9 in `test_shared_keys.py` (incl. the new canonical-key test), 65 in the 025 canonicalization files — 726 passed, no spec1–spec7 regressions.
- CLI smoke on the fixture: 33 config entries under `cfg:application.properties#`, `spring.datasource.password` and a userinfo JDBC URL `<redacted>`, `app.tokens-per-second` not redacted, one `yaml_parse_error`; with `--no-values` the same 33 entries in the same order with `value: null` and a different `inputs_hash`.

### Contract additions

- `ManifestFacts.spring_config_files` — the module's `application*` / `bootstrap*` files,
  scan-root relative, reaching `modules[].spring_config_files`.
- `FactAccumulator(no_values=…)` — the scan-wide `--no-values` option; `scan()` and `cli.main`
  pass it through, and `inputs_hash` records it.
- `migration_keys/spring.py`: `SPRING_CONFIG_FILE`, `SPRING_MAP_PREFIXES`, `SECRET_WORDS`,
  `REDACTED`, `MAX_VALUE_LENGTH`, `canonical_key`, `is_secret_key`, `has_userinfo_url`,
  `redact_value`, `kebab`, `split_index`, `map_prefix_length`.
- `ManifestContext.repo_has_java_build: bool` — whether any module has a Maven / Gradle build file.
- `migration_keys.spring.NON_SECRET_SUFFIXES`.
- `migration_oracle/pipeline/canonical/normalize.py` keys a Spring Boot property with
  `canonical_key` (new test `test_shared_keys.py::test_a_spring_boot_property_key_is_in_canonical_form`).
- `migration_oracle/pipeline/canonical/profiles.py` takes its Spring config file from
  `migration_keys.spring.SPRING_CONFIG_FILE` (same value, one source).

## [026.7-service-scanner] — 2026-11-07

### New features

- **Java sources (FR-7).** `migration_planner/scanner/java.py` parses `*.java` with
  **tree-sitter-java** and fills `symbols[]`, `members[]` and `wildcard_imports[]`. Every import
  form becomes a fact keyed by FQCN: `import a.b.C` → `maven:a.b.C`, a nested type keeps its dots
  (`a.b.C.Inner`), `import static a.b.C.m` → `maven:a.b.C.m` in `members[]`, and
  `import a.b.*` / `import static a.b.C.*` → `maven:a.b.*` / `maven:a.b.C.*` in
  `wildcard_imports[]` (AC-5).
- **Usage sites.** A type in any position (field, parameter, `extends`, `implements`, generic
  argument, `new C(…)`, cast, `instanceof`, `throws`, `C.class`, `C::new`) is a symbol at the use
  site; `@C` and `@C(attr = …)` are a symbol plus one member per attribute (`@C("x")` is
  `maven:a.b.C.value`); `C.m(…)` and `C.FIELD` are members. A chain records the first segment
  after the class, so `RequestMethod.GET.name()` is `maven:…RequestMethod.GET` — the same rule as
  the TypeScript extractor. A statically imported name used bare (`assertEquals(…)`) is a member
  at the use site.
- **Fully qualified usages without an import** (`org.x.Y.z()`, `@org.x.Ann`, `org.x.Y`) are
  recorded when the name starts with a groupId the repo's builds declare (the `ModuleEnv.group_ids`
  handoff spec6 added), because that is how an external package is told from the service's own
  `com.acme.…` code.
- **A wildcard import lists the simple names it can supply** (AC-5.2). `import java.util.*` plus a
  used `Map` gives `{"key": "maven:java.util.*", "names": ["Map"]}`, so a matcher tests
  `java.util.Map`. A name the file declares itself, a name another import binds, a `java.lang`
  type (imported implicitly) and a name that is not capitalized (a variable, not a type) are not
  listed; the own-package post-pass also drops a name the file's own package declares. Names are
  unioned across the files that share the key.
- **Own packages are not facts.** `filter_own_packages` is a post-pass over every source's facts:
  an import of `com.acme.shop.…` from `com.acme.shop.web` is the repo's own code in another
  module, matched segment by segment so `com.acme.shop` owns `com.acme.shop.web.Controller` but
  not `com.acme.shopping.Cart`.
- **Test paths** (`src/test/java/**`) record `test: true` (AC-5.3).
- **`tree-sitter-java>=0.23`** is a new dependency (prebuilt wheels, no compiler).

### Never silent

- A partial parse keeps every fact that did parse and adds one `partial_parse_error` at the first
  error's line; a file where nothing parses is one `parse_error`. Neither fails the scan (AC-5.4).

### Tests

- `tests/scanner/test_java.py` (59 tests): AC-5 (every import form keyed by FQCN, nested types, `import static`, both wildcard shapes, usages in each position, the first-segment chain rule, annotation attributes), AC-5.2 (the `names` a wildcard supplies and the java.lang / own-declaration / other-import exclusions), AC-5.3 (`src/test/java/**` locations carry `test: true`), AC-5.4 (a partial parse keeps its facts plus one `partial_parse_error`), the fully qualified usage with no import against declared and parent groupIds, and the own-package filter matched segment by segment.
- New fixture `tests/fixtures/scanner/spring-java/`: a Maven Boot app whose main sources use named, nested, static and wildcard imports, a `src/test/java` file for the test flag, and `BrokenReport.java`, whose syntax error yields one `partial_parse_error` while its two imports still parse.
- Whole scanner suite passes: 562 passed in `tests/scanner`, 8 in `test_shared_keys.py`, 65 in the 025 canonicalization files — 635 passed, no spec1–spec6 regressions. `tree-sitter-java` 0.23.5 under the `tree-sitter>=0.25,<0.26` pin from spec5.

### Contract additions

- `Usage.names: tuple[str, ...]` — the simple names a wildcard import may supply (empty for every
  other section).
- `ModuleEnv.own_group_ids: tuple[str, ...]` — the repo's own groupIds, so the Java extractor
  can keep a parent groupId away from the repo's own code.
- `FileFacts.package_name: str | None` — the `package x.y;` of a `.java` file, `None` for every
  other language, which is how the own-package post-pass finds the Java files.
- `PostPassContext.files` is now a mutable `dict`: a post-pass may **replace** a file's facts to
  drop some, and `scan()` merges every file's facts only after the post-passes. A post-pass may
  still return a `FileFacts` fragment (how barrel resolution adds facts).
- `WildcardEntry` in the profile model (`UsageEntry` + `names`), and `FactAccumulator.wildcard_entries`
  now returns it.

### Review fixes

- **Parent groupIds.** A fully qualified usage with no import is also recorded under the parent of
  a declared groupId (`org.springframework.boot` → `org.springframework`), so a starter-only
  service keeps `org.springframework.util.Assert.notNull(…)`. A parent needs two segments and
  never reaches an own groupId; the scan now passes `ModuleEnv.own_group_ids` for that.
- **Annotation attributes under a wildcard import** are members
  (`maven:…web.bind.annotation.RequestMapping.method` with `import …annotation.*`), one per class
  wildcard of the file.
- **Own wildcard packages** no longer leak their type names (or those types' annotation
  attributes) into an external wildcard entry.
- **`import static a.b.Outer.Inner`** is a symbol at the import line, not a member.
- **Comments inside an import** are not part of the key, and `import statics.Foo;` is no longer
  read as a static import (`maven:s.Foo`).

### Changed test named per the spec's Regression rule

- `test_java.py::test_a_static_import_on_a_nested_type_is_a_symbol` now also asserts the symbol
  at the import line and no member (review fix 4).
- `test_maven_gradle.py::test_a_java_only_repo_gets_no_npm_or_template_facts` asserted
  `profile["symbols"] == []` for the Maven fixture. That was spec6's "no Java facts yet" state,
  which this spec deliberately changes: it now asserts no `npm:` symbol and no template, and that
  the fixture's `SpringApplication` import *is* a symbol.

## [026.6-service-scanner] — 2026-11-06

### New features

- **Maven reader (FR-8).** `migration_planner/scanner/maven.py` reads `pom.xml` with stdlib `xml.etree` (namespaces stripped; external entities never resolved, so a DOCTYPE cannot make a scan read a file). `<parent>`, `<dependencies>`, `<dependencyManagement>` and `<build><plugins>` / `<pluginManagement>` become `dependencies[]` facts keyed `maven:<groupId>:<artifactId>` with `kind: parent | dependency | bom | plugin` — one entry per `(key, module, scope, kind)`, so a BOM import and a dependency on the same artifact stay two facts (AC-1.5, AC-6).
- **Maven interpolation.** `${prop}` resolves from the pom's own `<properties>` over its in-repo parents', plus Maven's implicit `project.version` / `project.parent.version` / … Maven inherits first and interpolates the result, so a parent's `${project.version}` means the version of the module being built (the child's own, when it declares one). An unresolvable `${x}` keeps its raw text in `range`, is not claimed as a `version`, and produces one `unresolved_variable` diagnostic at the line that mentions it (AC-6).
- **Spring Boot version from Maven (FR-3).** `<parent>spring-boot-starter-parent` first, then a `spring-boot-dependencies` BOM import, walking the in-repo parent chain so a child that declares neither is still on its parent's version. `source` names the pom that really declares it (`app/pom.xml#parent`).
- **Properties as config keys.** `cfg:pom.xml#properties.java.version` for the pom and for every module that inherits the value — a rule about `java.version` applies to a child that inherits it just as much as to the parent that writes it. `file` names the declaring pom.
- **Gradle reader (FR-8).** `migration_planner/scanner/gradle.py` reads `build.gradle(.kts)`, `settings.gradle(.kts)`, `gradle/libs.versions.toml` (stdlib `tomllib`) and `gradle.properties` with a tolerant lexer — no Gradle execution and no Groovy / Kotlin parser. Supports `plugins { id 'x' version 'v' }`, `id("x") version "v"`, `id("x").version("v")`, `kotlin("jvm")`, `apply plugin:`, `alias(libs.plugins.x)`, string notation, Groovy / Kotlin map notation, `platform(…)` / `enforcedPlatform(…)` as `kind: bom`, catalog accessors with `version.ref`, and `dependencyManagement { imports { mavenBom … } }` including `SpringBootPlugin.BOM_COORDINATES`.
- **Gradle variables.** `ext { … }` (wherever written, `buildscript` included), `extra["…"]`, a Kotlin top-level `val x = "…"`, and `gradle.properties` of the module and of the repo root resolve `$var` / `${var}`; a self-referential `x = "$x"` re-export is skipped so the real value survives. An unresolved variable keeps its raw text and gives one `unresolved_variable` per name and file (AC-7).
- **Spring Boot version from Gradle (FR-3).** The plugin first — its version from the module, a catalog alias, or the Gradle root project's `plugins` / `pluginManagement` block when the module applies it unversioned — then a `spring-boot-dependencies` BOM on `platform(…)`. `apply false` publishes a version to the subprojects without putting the root project on Spring Boot.
- **Module roots from the build.** Maven `<modules>` and Gradle `settings.gradle` `include(…)` are module roots; a declared module with no manifest of its own is listed in `modules[]` (FR-3, AC-7).
- **Java build config keys.** `java { toolchain { languageVersion = … } }`, `jvmToolchain(21)`, `sourceCompatibility` and `targetCompatibility` become `cfg:build.gradle#java.toolchain.languageVersion` / `cfg:build.gradle#sourceCompatibility`. The key always names `build.gradle` / `build.gradle.kts` (the two names 025 / 027 know) while `config[].file` keeps the real subproject path.
- **groupIds for spec7.** Declared Maven groupIds reach source extractors as the new `ModuleEnv.group_ids` (repo-scoped, like `own_packages`), so spec7 can recognize a fully qualified `org.x.Y.z()` usage that has no import.

### Never silent

- A dependency-looking Gradle line the lexer cannot parse is an `unparsed_gradle` diagnostic (`add("implementation", "g:a:v")`), while `project(…)`, `files(…)` and `gradleApi()` — not external coordinates at all — are skipped without one.
- A broken pom is a `pom_parse_error`, a broken catalog a `version_catalog_parse_error`, an unknown catalog alias an `unresolved_catalog_entry`, and a self-referential parent chain a `pom_parent_cycle`. None of them fails a scan.
- An unresolved placeholder is never reported as a `version`: `version` stays `null`, `range` keeps the text as written, and the diagnostic says why. A profile must not claim a service builds with `${external.bom.version}`.

### Tests

- `tests/scanner/test_maven_gradle.py` (98 tests, 22 of them from the review below): every FR-3 source in both build systems
  (including inheritance and `apply false`), every FR-8 notation, property and variable
  resolution through a parent / `ext` / catalog / `gradle.properties`, both unresolved-value
  cases with their line numbers, module roots from `<modules>` and `include`, the config keys,
  the groupIds handoff, and truncation / broken-file cases that must not raise.
- New fixtures: `spring-maven/` (parent pom with the Boot BOM, two children) and `spring-gradle/`
  (Kotlin root with `apply false`, settings `pluginManagement`, catalog, `gradle.properties`,
  Groovy subproject, plain Kotlin subproject).
- Whole scanner suite passes: 511 passed in `tests/scanner` + `tests/pipeline/test_shared_keys.py`; the 025 key /
  canonicalization tests pass unchanged. Verified against three real-shaped build files (a
  Groovy build with Boot 2.7, a Spring Boot parent pom with Maven plugins, and a Kotlin DSL
  build with a top-level `val`), all with zero diagnostics and the correct Boot version.

### Review fixes

- **No placeholder is ever a framework or plugin version.** An unresolved Boot version (`${boot.version}` from outside the repo, `version "$bootV"` declared nowhere) gave `frameworks[].version = "${boot.version}"` and a `gradle-plugin:` fact with `version: "$bootV"`. Now `version` is empty, `raw` keeps the text, the search goes on to the next FR-3 source, and a plugin applied with no version anywhere is still Spring Boot with an empty `version`. The inherited Gradle fallback is resolved the same way, and its `source` names the declaring script (`settings.gradle.kts#pluginManagement`) instead of `gradle-root#plugins`.
- **Maven stays inside the scan root.** The `<relativePath>` branch (default `../pom.xml`) did not check it, so scanning `svc/` of a checkout read the parent above it. A `<relativePath>` that names a directory now finds its `pom.xml`.
- **Maven `groupId` / `artifactId` are interpolated.** `${project.groupId}` gave the key `maven:${project.groupId}:lib`; a groupId that stays unresolved is left out of `group_ids`.
- **Spring Initializr's `ext { set('x', '…') }`, `ext.x = '…'`, `project.ext.x` and `ext.set(…)`** declare variables; they were read as nothing and gave false `unresolved_variable` diagnostics.
- **A subproject's own `gradle.properties` overrides the root's** (it was the other way round).
- **Version catalog:** a `[plugins]` string entry is `"<id>:<version>"` (it was read as a Maven coordinate, losing the Boot version); `libs.bundles.x` expands to its libraries; an unknown library or bundle accessor and a `version.ref` to a missing version are `unresolved_catalog_entry` instead of silently dropped. A broken catalog stays one `version_catalog_parse_error`, not one more diagnostic per accessor.
- **`kotlin("stdlib")` and Groovy varargs** (`implementation 'g:a:1', 'g:b:2'`) are facts; they were dropped silently.
- **Boot version from a `buildscript` classpath (review decision).** `classpath "org.springframework.boot:spring-boot-gradle-plugin:X"` (and `io.spring.gradle:dependency-management-plugin`) is the version of the plugin a module then applies with `apply plugin:` — in the module's own build or through the root project, whose `ext` values a subproject now also sees. `source` is `build.gradle#buildscript`. The plugin artifact on the classpath does not count as "uses Spring Boot libraries", so a root that only puts it on the classpath is not on Boot.
- **The repo's own groupIds are not external (review decision).** New `ManifestFacts.own_group_ids`: Maven `<groupId>` of the pom and its in-repo parents (one inherited from an external parent is not owned), Gradle `group = …`. The readers leave them out of `group_ids`, and `scan()` subtracts every module's own groupIds repo-wide from `ModuleEnv.group_ids`, so a sibling dependency `com.acme:lib` no longer makes `com.acme.…` look external to spec7.
- **Docs:** the claim that a parent's `${project.version}` means the parent's version was wrong (the code already did what Maven does); docstrings, this entry and `service-scanner.md` now say what happens.

### Changed test named per the spec's Regression rule

- `test_npm_manifests.py::test_the_npm_reader_handles_every_npm_manifest_kind` pinned the registry to exactly the four npm kinds. The registry is an internal detail that spec6 extends, so it now asserts what the npm kinds map to (each is `read_npm_manifests`) instead of the set's exact contents.
- `test_maven_gradle.py::test_declared_group_ids_are_kept_for_spec7` and `::test_the_scan_passes_group_ids_to_the_module_environment` asserted that `com.acme` (the repo's own groupId) is in `group_ids`; by the review decision it is not, so they now assert the opposite and `own_group_ids`.
- `test_maven_gradle.py::test_a_subproject_inherits_the_root_plugin_version` pinned `source = "service/build.gradle#plugins(inherited)"`; `source` now names the declaring script, `settings.gradle.kts#pluginManagement`.
- `test_maven_gradle.py::test_a_property_that_refers_to_the_project_version_resolves`: only its docstring changed (it repeated the wrong `${project.version}` claim); the assertion is unchanged.

### Contract additions

- `ManifestFacts.module_roots`, `ManifestFacts.group_ids` (external only) and `ManifestFacts.own_group_ids`; `ModuleEnv.group_ids` (repo-wide, own groupIds removed). `scan()` folds declared module roots into `modules[]` and hands the groupIds to source extractors. `builtin.MANIFEST_READERS` now also registers the Maven and Gradle kinds.

## [026.5-service-scanner] — 2026-11-06

### New features

- **Angular template tokens (FR-6).** `migration_planner/scanner/templates.py` fills `templates[]` from the two places a template lives: `*.html` files and an inline `template:` / template literal of an `@Component`. Keys come from `migration_keys.angular.ANGULAR_SYNTAX_TOKENS`, the same list 025 canonicalizes a rule entity with, so a rule and a fact meet on `syntax:angular-template#…` without translation.
- **Block keywords (FR-6).** `@if`, `@for`, `@switch`, `@defer`, `@let`, `@else`, `@else if`, `@empty`, `@case`, `@placeholder`, `@error`, `@loading` are counted where they really are blocks: not inside a word, and carrying block syntax (a `(condition)` or a `{` body, or for `@let` a name and `=`). `@defer` in a sentence is text.
- **Expression tokens only in bindings.** `in`, `void`, `typeof`, `as`, `let` are counted in `{{ … }}`, `[prop]="…"`, `[(prop)]="…"`, `(event)="…"`, `*dir="…"`, a block condition and an interpolation inside any attribute (`title="{{ x | async }}"`). Prose between tags is never an expression, and string literals inside a binding are masked, so `[title]="'a in b'"` has no `in`.
- **Structural directives and pipes.** `*ngFor`, `*ngIf`, `*ngSwitchCase`, … are `syntax:angular-template#*ngFor`; a pipe in a binding is `syntax:angular-template#pipe:date`. `a || b` is a logical or, not a pipe, and `*ngFor`'s microsyntax (`let item of items`) is a binding, so its `let` is a token.
- **Inline templates keep their `.ts` location.** The spec3 decorator pass hands the string and its start line to the lexer, so a token inside a multi-line backtick template points at the line of the `.ts` file (AC-4), not at a line inside the string. A `\n` escape inside a quoted template starts a new *rendered* line while the file line stays correct.
- **Only real templates count.** A `*.html` file of a module with no Angular framework is not a template (FR-6), which needs the new `ModuleEnv.framework_names` the scan fills from the module's detected frameworks. An inline template only comes from `@Component` — `@Directive` or an own-code decorator with a `template` option is not one — and a template literal with `${…}` substitutions is skipped, because its rendered text is not static.
- HTML comments (`<!-- … -->`) are skipped whole, so a commented `@defer *ngFor in` contributes nothing.

### Fixes (review 2026-11-06)

- **A block after text on the same line was not counted.** `Save @if (loading) {…}` and the pluralization idiom `item@if (n > 1) {s}` gave no `@if`, because a letter before the `@` was read as "inside a word". Since Angular 17 an `@` before a block name always opens a block, so the block syntax after the keyword (`(`, `{`, `@let name =`) is now the only test; `a@for.com` is still not a block.
- **`ngNonBindable` content was scanned.** `<code ngNonBindable>{{ a | date }}</code>` recorded `pipe:date`; Angular does not compile that content, so it now yields nothing (the element's own attributes still do).
- **Any `@Component` with a `template` was read as Angular.** A Vue class component (`vue-property-decorator`) produced `syntax:angular-template#pipe:currency`. Only `@Component` from `@angular/core` (or an own-code barrel re-export) is scanned now.
- **`html` is in `builtin.SOURCE_EXTRACTORS`**; `EXTRA_SOURCE_EXTRACTORS` is gone. `test_ts.py::test_the_extractor_is_registered_for_every_language` and `test_ts_resolve.py::test_extractors_still_get_the_same_grammars` pinned the registry to exactly the TS grammars, an internal detail; they now assert behavior (every TS grammar maps to `extract_ts`). The Regression rule in spec1–spec9 now says such detail-pinning tests may change deliberately when named here.
- `test_a_template_through_a_barrel_import_is_scanned` gave the extractor no `paths` alias, so `@app/core` was an external package rather than the own barrel its docstring describes; it now sets `@app/*` and tests what it says.

### AC-11 on a real service (2026-11-06)

- **AC-11 run on `paysafe-wac-web-login-fe`** (Angular 20.3.27, 709 files): 1.35 s cold, 441 KB profile, 0 diagnostics; 10 / 10 random import sites and 1 443 / 1 443 single-line imports correct; every template count equals `grep`; 40 of the 43 025 Angular keys the service uses are in the profile, the 3 misses explained. Report: `specs/026-service-scanner/ac11-angular.md`; key check: `specs/026-service-scanner/ac11/keys025.py`.
- **Fixed: py-tree-sitter 0.26.0 segfaults the scan.** The first AC-11 run exited 139 on 22 of 631 TS / JS files. 0.24 / 0.25 are fine; `pyproject.toml` pins `tree-sitter>=0.25,<0.26` (lock: 0.25.2). `tests/scanner/test_ts_native_stability.py` reproduces the crash with a synthetic 813-line spec file in a subprocess and asserts the installed version.

### Tests

- `tests/scanner/test_templates.py` (66 tests): every AC-4 row, the block/binding gating (a keyword in prose or in an attribute value, `||` vs a pipe, a token inside a string literal and inside a comment), multi-line bindings and nested blocks at their own lines, the `(file, line)` site rule, the inline path (backtick, quoted, `${…}`, non-`@Component`, own-code decorator, a local class named `Component`), the Angular/non-Angular `.html` gate, the `test` flag, `--max-locations`, determinism and an unterminated `{{` that must not fail the scan.
- New fixtures: `angular-templates/` (every block keyword, `*ngFor`, `{{ in }}`, `| date`, `a || b`, prose with `in`, a leading comment full of tokens, an inline multi-line and a single-line template) and `node-html/` (a Node module whose `index.html` is full of template syntax and must stay empty).
- Whole scanner suite passes: 405 passed in `tests/scanner`, 73 in the 025 key and canonicalization files. The review fixes add AC-4.2 cases to `test_templates.py` (49 → 66 tests) and a new `tests/scanner/test_ts_native_stability.py` (2 tests, subprocess) for the tree-sitter pin.
- ~~`html` shipped as `builtin.EXTRA_SOURCE_EXTRACTORS` because two spec3 / spec4 tests pinned `SOURCE_EXTRACTORS` to the TS grammars.~~ Closed in the review fixes below.

### Verification on a real Angular app

`migration-scan` on `gothinkster/angular-realworld-example-app` (Angular 21.2.12, 66 files):
counts agree with `grep` exactly — `@if` 25 (18 in `.html` + 7 inline in `.ts`), `@for` 8 (5 + 3),
`| date` 3 (1 + 2) — and the stored locations match the `grep -n` line numbers, inline tokens
included. A synthetic 1 800-file Angular tree scans in 0.6 s with a 48 KB profile, well inside
the AC-11 budget of 30 s / 2 MB. The full AC-11 run needs a ≥ 1 000-file service, which is not
available in this workspace; see `specs/026-service-scanner/ac11-angular.md`.

## [026.4-service-scanner] — 2026-11-06

### New features

- **Barrels and aliases resolve to the external package (FR-5).** `migration_planner/scanner/ts_resolve.py` is the post-pass spec4 promised: it takes the own-code imports spec3 collected, follows them through barrels, `paths` aliases, `baseUrl` and workspace packages, and records the external key **at the original import site** — `import { inject } from '@app/core'` with `core/index.ts → export { inject } from '@angular/core'` gives `npm:@angular/core#inject` at the importing file, which is the line a matcher must search.
- **Chains are followed, not guessed.** `export { X } from '…'`, `export { X as Y } from '…'` (renames applied along the chain), `export * from '…'` and `export * as ns from '…'`. A name that ends in a local declaration is own code and is dropped silently; an `export *` of a package cannot be enumerated, so a name that reaches it belongs to that package.
- **Specifier → file.** Relative paths, `compilerOptions.paths` (longest pattern, targets in order, first existing wins), `baseUrl`, and workspace package names via their `package.json` `exports["."]` / `types` / `module` / `main`, else `index.*`. Every candidate is probed with `.ts`, `.tsx`, `.d.ts`, `.js`, `.jsx`, `.mjs`, `.cjs` and `/index.*`; a `.js` specifier also finds its `.ts` source (`NodeNext`).
- **Members follow the chain too.** `di.call(…)` after `export { inject as di }` becomes `npm:@angular/core#inject.call`; `core.inject(…)` and `@core.Component({ selector })` on a barrel namespace resolve per member. Own-code member accesses are now kept by spec3 (`FileFacts.own_member_bindings`, `OwnMember`) for this pass.
- **New contract seam for post-passes.** `PostPassContext` / `ResolutionEnv` / `OwnPackage` and a `PostPass` that returns a `FileFacts` fragment; `scan()` merges it like any extractor's output. The npm reader now reports each own package's directory and entry points (`ManifestFacts.own_package_sources`), which is what makes a workspace-package import resolvable.
- **Bounded, never silent.** A cycle gives `barrel_cycle`, a chain deeper than 10 gives `barrel_depth` (AC-2.3: depth 11), an own import with no file gives `unresolved_import`. An asset specifier (`./x.scss`, `./data.json`) is not a module and is skipped without a diagnostic. Results are memoized per `(file, exported name)`.

### Fixes

- **A give-up must not poison the memo.** Only a definitive resolution is cached: a `barrel_depth`/`barrel_cycle` result is a property of one entry point, so caching it would deny a shorter chain the same name. Covered by `test_a_short_chain_still_resolves_after_a_deep_one_gave_up`.
- **The same cycle was reported once per importer.** `barrel_cycle` / `barrel_depth` now dedupe per `(kind, file)`; the chains differ per entry point and a reader only needs the file.

### Fixes (review 2026-11-06)

- **Only the first own `export *` was searched.** A barrel with `export * from './a'; export * from './b'` (the Angular `public-api.ts` shape) stopped at `a` when it lacked the name, so everything behind `b` was lost. A file that does not export a name is now "not found" and the search moves on.
- **`import { X } from 'pkg'; export { X }` was treated as own code.** The export is now linked to its import and followed (a re-exported `import * as ns` becomes a namespace export).
- **A `paths` alias into `node_modules` dropped every import through it.** `"@angular/*": ["./node_modules/@angular/*"]` made `@angular/core` own code, so `Component`, `inject`, … vanished behind `unresolved_import`. Such aliases are redirects to an external package now (`migration_keys.specifiers.own_path_aliases`).
- **Several external `export *` attributed a name to the first one** (`map` → `npm:@angular/core#map`). With one external star the name is still attributed; with several it is reported as `ambiguous_export` and not recorded.
- **A `const` inside a function body shadowed `export *` names.** `local_declarations` now holds module-scope declarations only.
- **Inline `type` through a barrel** (`import { type Signal } from '@app/core'`) keeps `type_only` per name (`OwnImport.type_names`).
- **Workspace subpath exports** (`@demo/ui/testing` → `exports["./testing"]`, `"./*"` patterns) resolve (`OwnPackage.subpath_exports`).
- **`export * as rx from 'rxjs'`** re-exported through a barrel: `rx.filter()` gives `npm:rxjs#filter` at the access (was nothing).
- **A bundler query** (`./worker?worker`) no longer gives a false `unresolved_import`.
- Removed an unused `typing.Any` import in `contract.py`.

### Tests

- `tests/scanner/test_ts_resolve.py` (60 tests): AC-2 (the key at the import site, cycle → diagnostic, no crash), AC-2.2 (`export *`, rename chain, namespace import of a barrel, workspace package, `paths` alias with `*`, namespaced re-export, every probed extension, `.js` → `.ts`), AC-2.3 (local declaration dropped, depth 10 vs 11), the diagnostics, memoization, and the seam between spec3 and spec4.
- New fixture `tests/fixtures/scanner/ts-barrels/` with a core barrel, a barrel of a barrel, an `export *`, a rename, a namespace barrel import, a cycle, a 10/11-deep chain, a workspace package with an `exports` map and a `paths` alias with two targets.
- `tests/fixtures/scanner/ts-imports/` gained the targets its own imports name (`src/local.ts`, `src/app/shared.ts`, `packages/ui/`) and an `@demo/ui` `main`/`types`, so the spec3 fixture has no genuinely unresolved import.
- Whole scanner suite plus the 025 shared-key / canonicalization tests pass unchanged: 337 passed in `tests/scanner`, 73 passed in the 025 key and canonicalization files — 410 passed, no spec1 / spec2 / spec3 regressions.

## [026.3-service-scanner] — 2026-11-06

### New features

- **TypeScript / JavaScript extraction.** `migration_planner/scanner/ts.py` parses `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs` and `.cjs` with **tree-sitter** and fills `symbols[]`, `members[]` and `side_effect_imports[]`. Every FR-5 import form is handled: named, aliased (`B as C` keeps `npm:pkg#B`), default (`#default`), namespace, side-effect, `import type` and inline `type` (`type_only`), `export … from`, `export *`, `import('pkg')` / `require('pkg')` including destructuring, and `import x = require('pkg')`. The extractor is a pure function of the file's bytes, so spec9 can cache it and run it in a process pool.
- **Members.** `Local.member` for every identifier bound to an external import, first segment only (`A.b.c` → `A.b`). A namespace import resolves per name (`core.inject(…)` → `npm:@angular/core#inject`). A local declaration that shadows the name stops tracking in that scope — a parameter named `TestBed` is not the imported `TestBed`.
- **Decorators.** Every literal key of a decorator's first object argument is a member (`npm:@angular/core#Component.standalone`, `….changeDetection`). Angular rules are mostly about these options.
- **`migration_keys/specifiers.py`.** The import-specifier rules both sides need: `package_of_specifier` (`@angular/core/testing` is its own package, `rxjs/internal/x` and `lodash/fp.js` kept as written), `dependency_name`, `is_own_code` (relative, paths alias, workspace package), `is_node_builtin`, and `resolve_path_alias` for spec4. Pure string handling, no file system, no `migration_oracle`.
- **Spec4 inputs are already collected.** `FileFacts` gains typed `ExportBinding`, `OwnImport`, `star_exports`, `namespace_exports`, `local_declarations` and `own_import_bindings`, replacing the untyped `export_map` dict — so spec4 can follow a barrel without re-parsing anything.
- **`builtin.py` registry.** The shipped readers and extractors live in one list and are installed when the scanner package is imported, so `migration-scan` needs no setup step while `reset_registry()` stays a working escape hatch.

### Fixes

- **`reset_registry()` could not empty the registry.** `scan()` re-installed the built-in readers and extractors on every call, so nothing could opt out of them. Installation is now an import-time effect of `builtin`, never something `scan()` does inside a scan.
- **A `const` that shadows an import was not detected.** `const TestBed = local(); TestBed.get(x)` was attributed to the imported `TestBed`, because only the declaration node was checked and not the block that scopes it. Block-scoped declarations are now checked per enclosing block.
- **`require('pkg')` bound to a name looked shadowed by its own declaration.** The declarator that *creates* an import binding is now excluded from the shadow check, which had been silently dropping `const m = require('pkg'); m.thing()`.
- **`await import('pkg')` recorded nothing.** The `await_expression` wrapper between the call and its `variable_declarator` stopped the declarator lookup, so the binding (and the package fact) was lost.

### Fixes (review 2026-11-06)

- **`baseUrl` imports were recorded as npm packages.** With `baseUrl: "./src"`, `'app/core/core.service'` gave `npm:app/core/core.service#CoreService`. The scan now hands extractors the entries directly under `baseUrl` (`ModuleEnv.base_url_roots`), and such specifiers are own code; a declared dependency of the same name still wins.
- **Declared npm packages named like Node builtins were dropped.** `events`, `buffer`, `util`, `url`, `process` … are external when the repo declares them (`ModuleEnv.declared_dependencies`); `node:` is always a builtin.
- **Decorators added symbol locations.** `@Input()` twice gave `Input` a count of 3 while `inject` called twice stayed at 1. `symbols[].locations` are import sites only again (spec1 FR-9); decorators contribute members.
- **`export * from '<external>'` recorded nothing.** It is now the package-level symbol `npm:<pkg>`.
- **Inline `import { type T, V }`** marks only `T` as `type_only` (was neither); all-`type` specifiers make the whole import type-only.
- **`import x = require('pkg')`** (TypeScript) is recorded, with member tracking on `x`.
- **Decorator options**: shorthand keys (`{ selector }`), method keys and namespaced decorators (`@core.Component({…})`) now become members.
- **Package-level uses moved to `symbols`.** `import('pkg')` / `require('pkg')` were in `side_effect_imports`; that section now holds only `import 'pkg'`.
- **Deep file imports are kept as written** (`lodash/fp.js` → `npm:lodash/fp.js#…`, was folded to `npm:lodash`), as FR-5 says.
- Removed the unused `ts.register()`; registration lives in `builtin.py`.

### Tests

- `tests/scanner/test_ts.py` (62 tests) covers AC-1 (every FR-5 form, own code skipped, entry points and deep imports), AC-3 (members through named / aliased / namespace bindings, first-segment rule, four shadowing shapes, decorator keys), AC-3.2 (all six grammars incl. tsx/jsx syntax), parse errors and AC-3.3 (`count` exact, `files: 30`, 5 locations, `truncated`, test flags).
- `tests/scanner/test_specifiers.py` (40 tests) covers the shared specifier rules.
- New fixture `tests/fixtures/scanner/ts-imports/` puts every import form in one file, with a workspace package and a paths alias for the own-code cases. Verified against a real 709-file Angular service: 0.8 s, 361 symbols, 152 members, 0 diagnostics, no alias leakage.
- Whole scanner suite and the 025 shared-key / canonicalization tests pass: 348 passed (`tests/scanner` 275, `test_shared_keys.py` 8, the four `test_canonical_*.py` files 65), no regressions in the spec1 / spec2 tests.

## [026.2-service-scanner] — 2026-11-06

### New features

- **npm manifests.** `migration_planner/scanner/npm_manifests.py` reads `package.json`, `package-lock.json`, `angular.json` and `tsconfig*.json` in one pass per module. All four dependency scopes (`dependencies`, `devDependencies`, `peerDependencies`, `optionalDependencies`) become `dependencies[]` entries with the range exactly as written and the **installed** version from the lockfile, so `npm:@angular/core` says `range: "^19.2.0"` and `version: "19.2.4"`. A module with no lockfile of its own reads the nearest one in a parent directory, which is how an npm workspace is installed.
- **Config keys.** `package.json` `engines.*`, `type`, `browserslist`, `overrides.*`, `resolutions.*` and `workspaces` become `cfg:package.json#<dotted path>`, lists keeping their index. Every scalar leaf of `angular.json` becomes a key with the project name replaced by `*` — `cfg:angular.json#projects.*.architect.build.builder` — so one rule matches a repo with any number of projects, while the real names go to a new `modules[].angular_projects`. `tsconfig*.json` accepts comments and trailing commas, follows `extends` inside the repo, and emits `cfg:tsconfig.json#compilerOptions.*` / `angularCompilerOptions.*` from the **effective** config.
- **Angular version (FR-3).** `package-lock.json` beats the `package.json` range: the framework version is what the build installs, not what the manifest wishes for. With no lockfile the range is kept as `raw` and normalized to the **lowest** version it allows (`^19.2.0` → `19.2.0`, `~1.4` → `1.4.0`, `>=18` → `18.0.0`, `19.x` → `19.0.0`, a `||` union → its lowest alternative). `*`, `latest`, `workspace:*` and `file:` carry no floor and stay `null` without a diagnostic; anything else is `unsupported_range`.
- **Own packages.** A module's `package.json` `name` and its npm workspace package names are recorded in a new `modules[].own_packages` (per module) and handed to source extractors, as a repo-wide union, through the new `ModuleEnv`. That is the input spec3 needs to skip imports of the service's own code instead of recording them as external.
- **Effective path map.** `compilerOptions.paths` and `baseUrl` are resolved across `extends` into a `PathMap` on the module — `paths` as written, `paths_dir` the directory they are relative to (`baseUrl` when set, else the config file that declared them, which is TypeScript's own rule) — for import resolution in spec3 / spec4.
- **`builtin.py`.** The readers and extractors this package ships live in one registry list, so the scan loop still knows nothing about npm, Maven or Angular and a later spec only adds an entry.

### Fixes

- A `tsconfig` cycle or an `extends` pointing at `node_modules` used to be unresolvable; both are now diagnostics (`tsconfig_cycle`, `tsconfig_extends_outside_repo`) and the scan continues.
- A `package.json` dependency whose value is not a string is a diagnostic (`invalid_dependency`) instead of a silently missing entry.

### Fixes (review 2026-11-06)

- **A hoisted `@angular/core` made every workspace package Angular.** A module is now Angular only when its `package.json` declares `@angular/core`; the lockfile supplies the exact version.
- **A nested workspace root's lockfile was not found.** A module without its own `package-lock.json` now uses the nearest one in a parent directory up to the scan root (`frontend/package-lock.json` for `frontend/packages/ui`), not only the scan root's.
- **A `package-lock.json` over 2 MB was skipped**, so versions fell back to range floors. Manifests now have a 50 MB cap; the 2 MB cap applies to sources.
- **`modules[].own_packages` listed every package of the repo in every module**, a Maven module included. It now lists the module's own names; extractors still get the repo-wide union.
- **`dependencies[].version_source`** (`lockfile` | `range` | `null`) says whether `version` is installed or a range floor.
- The `tsconfig` of `angular.json` targets is chosen in declaration order (build first), not by file name.
- `>1` / `>1.2` normalize to `2.0.0` / `1.3.0` as in npm (was `1.0.1` / `1.2.1`).
- Removed the unused `npm_manifests.register()`; registration lives in `builtin.py`.

### Tests

- `tests/scanner/test_npm_manifests.py` (71 tests) covers AC-8 (lockfile beats range, all four scopes, `*`-normalized `angular.json` keys and per-target builders, comments / trailing commas / `extends`, effective paths), AC-8.2 (the npm workspace fixture → three modules, own packages, per-module dependencies) and AC-8.3 (a broken `package.json` → diagnostic, scan continues, exit `0`), plus the range normalizer and the JSONC stripper.
- Two new fixtures: `tests/fixtures/scanner/angular-app/` (lockfile, two Angular projects, three tsconfigs) and `tests/fixtures/scanner/npm-workspace/` (root lockfile, two package modules).
- The whole scanner suite and the 025 shared-key tests pass unchanged: 181 passed (`tests/scanner` 173, the 025 `test_shared_keys.py` 8), no regressions in the spec1 tests.

## [026.1-service-scanner] — 2026-11-06

### New features

- **`migration-scan`, the first part of the migration planner.** A new top-level package `migration_planner/` reads one service repository and writes `.migration/profile.json`: which files it scanned, how they group into modules, and the fact sections the later specs fill. It reads the service only — no graph, no LLM, no network — so it runs in a service repo with none of the ingestion dependencies installed. stderr carries a hint when `.migration/` is not in `.gitignore`; nothing is written to it. See [the scanner page](../docs/02-extraction-pipeline/service-scanner.md).
- **Discovery and modules.** Inside a git work tree files come from `git ls-files --cached --others --exclude-standard`; outside git the tree is walked and `.gitignore` is applied, so both modes give the same file set. `node_modules`, `.angular`, `.gradle`, `.git` and `.migration` are never entered, and `dist`, `build`, `target`, `out` outside `src/`; files over 2 MB and generated / minified JS are skipped and counted in `diagnostics`. Every manifest and source file belongs to its nearest module root (`package.json`, `pom.xml`, `build.gradle(.kts)`), and the repo-level `framework` is the one found in most modules, with ties listed in `diagnostics`.
- **Profile model and atomic writer.** The profile is pydantic (`Profile`, `ModuleEntry`, `SymbolEntry`, …) and is written through a temp file plus `rename`, so a crashed scan never leaves a half-written profile. Keys are sorted and lists are sorted, so two scans of an unchanged tree differ only in `generated.at`; `inputs_hash` changes when one byte changes. Every fact section that no spec fills yet is an empty list, so the schema is stable while specs 2–9 land.
- **Extractor contract.** `migration_planner/scanner/contract.py` defines the seam the later specs plug into: manifest readers (`dependencies`, `config`, `frameworks`, `diagnostics`), per-file source extractors (pure functions of the file content, so spec9 can cache and parallelize them) and post-passes. A reader or extractor that raises becomes a diagnostic; one bad file never fails a scan.
- **`migration_keys/`.** The canonical key builders (`npm_key`, `maven_key`, `cfg_key`, `syntax_key`, `diag_key`) and the Angular entry-point / template-token / config-prefix data moved out of `migration_oracle/pipeline/canonical/` into a dependency-free package that ingestion and the planner both import. 025 now reads them from there; no key or token changed.
- **Exit codes and summary.** `0` profile written, `1` usage error, `2` no supported manifest under `PATH`. stdout is one stable line (`scanned 4812 files · angular 19.2.0 · 61 deps · …`) with every count printed even when zero; `--json-summary` prints the same numbers as one JSON object. New entry point `migration-scan = "migration_planner.scanner.cli:main"`.

### Fixes (review 2026-11-06)

- **Java packages named `build` / `target` / `out` / `dist` were not scanned.** Those names are now skipped only outside a `src/` directory; `node_modules`, `.angular`, `.gradle`, `.git`, `.migration` are still skipped at any depth.
- **Files under no module root were dropped.** A root `tsconfig.json` or a shared `config/application.yml` next to `svc/pom.xml` now belongs to module `.`, which is listed in `modules[]` and reaches the manifest readers.
- **Walk mode ignored intermediate `.gitignore` files.** Every `.gitignore` from the root down to a file's directory now applies.
- **`config[]` merged entries by key only.** It now keeps one entry per occurrence `(key, module, file, profile, line)`, and `ConfigFact` / `ConfigEntry` carry `module`, `line`, `raw_key`, `profile`, `kind`, `test` for spec8.
- **`dependencies[]` merged a BOM and a dependency on the same artifact.** `kind` (`dependency | bom | parent | plugin`) is added and entries are unique per `(key, module, scope, kind)`.
- **`inputs_hash` ignored scan options.** `--max-locations` and `--include-tests` are now part of it, so spec9 cannot report `unchanged` after an option change.
- AC-9a now states the real contract (`generated.at` and `generated.duration_ms` differ between scans), and its test no longer contains a no-op assertion.

### Tests

- `tests/scanner/` (101 tests) covers the CLI contract, discovery in git and walk modes, skipped and generated files, modules, profile merge and bounds, determinism (`AC-9a`), the extractor contract, and isolation (`AC-10`): an AST guard fails if anything under `migration_planner/` or `migration_keys/` imports `migration_oracle`, `neo4j`, `langchain*`, `httpx` or `socket`, and a scan runs with no `NEO4J_URI`, no `.env` and sockets blocked.
- `tests/pipeline/test_shared_keys.py` guards `AC-1.4`: the 025 normalizer still produces byte-identical keys and uses the moved Angular data.

## [027-rule-signals] — 2026-11-06

### New features

- **Rule detection signals.** A new ingestion stage between canonicalization and the graph write classifies every rule by **how a service shows that the rule applies**: `symbol` (the code uses a named API), `config` (a config key is set), `dependency` (a package is declared), `syntax` (template syntax is used), `behavioral` (only code that relies on the old behaviour is affected) or `universal` (every service on the hop). System-1 picks the type and the feature tags; code decides what the planner can search for.
- **Feature tags.** Each rule also gets the features it needs (`ssr`, `hydration`, `zoneless`, `zone`, `animations`, `router`, `forms`, `http`, `i18n`, `service-worker`, `testbed`, `karma`, `ngmodule`, `elements`, `upgrade`, `cli-build` for Angular; starters for Spring Boot; subsystems for WildFly). The vocabulary lives in `migration_oracle/pipeline/signals/features.py` as plain data with **evidence keys** — the profile keys from which the planner can tell, without asking, that a service has the feature. So the planner can rule out whole groups and ask one question ("Do you use SSR?") instead of one per rule.
- **One System-1 request per rule.** A `signal` choice plus one `feature.<id>` `noul` per vocabulary entry, in a single body, so the state travels once per rule. Cached under `ARTIFACT_CACHE_DIR/signals/` by `SIGNAL_QUESTIONS_VERSION`, model, framework and state. The state contains the canonical keys, so a canonicalization change re-asks only the rules it affects. `--force-signals` ignores the cache.
- **Contract guard and floors.** The expensive mistake is excluding a rule that applies, so every uncertain rule falls back to `behavioral`: a type with no key to search for (a rule that names only its replacement, a `config` key with no known file, an unresolved `npm:?#X` package) becomes `behavioral` / `guard`; a type below `SIGNAL_SEARCHABLE_MIN_PROB` (0.70) or `universal` below `SIGNAL_UNIVERSAL_MIN_PROB` (0.60) becomes `behavioral` / `low_confidence`. Only `removed` and `mentioned` entities count — finding the *replacement* means the service has already migrated.
- **Deterministic shortcut.** A rule whose entities are all dependencies with `change_type: component_upgrade` is `dependency` by rule, without asking for the type; its features are still requested.
- **Graph properties.** `MigrationRule` gains `signal`, `signalConfidence`, `signalSource`, `signalKeys`, `features`, `signalQuestionsVersion`, `signalModel`, written in the same session as the rule. A rule without them is read by the planner as `behavioral`, so a missing classification never excludes anything.
- **`scripts/classify_signals.py`** backfills hops already in the graph: it reads `runs/json/*-entities.json`, canonicalizes, classifies, and `SET r += $props` on the matching `ruleId`. Sets only those properties, is idempotent, and reports `ruleId`s that are not in the graph.
- `--skip-signals` writes the rules without signal properties. `--dry-run` runs the stage and writes `runs/signals/` without touching the graph.
- New settings: `SIGNAL_STATE_MAX_CHARS` (4000), `SIGNAL_SEARCHABLE_MIN_PROB` (0.70), `SIGNAL_UNIVERSAL_MIN_PROB` (0.60), `SIGNAL_FEATURE_MIN_PROB` (0.50). The endpoint is the triage one (`TRIAGE_BASE_URL` / `TRIAGE_MODEL`); Nimble unset or unreachable logs once, writes no properties, and populate continues.
- `migration_oracle/pipeline/rule_ids.py` holds the `pipeline://{framework}/{version}/{title}` format, so populate and the backfill agree on the id.

## [025-entity-canonicalization] — 2026-11-06

### New features

- **Canonical entity identity.** Every affected entity gets one canonical identity before the graph write: `kind` (`class` · `member` · `property` · `dependency` · `syntax` · `diagnostic`), `ecosystem`, `package`, `symbol`, `member`, `file`, the matchable `name`, the merge `key`, and `verified`. Entity nodes now `MERGE` on `key`; `name` stays what scanners and MCP queries match on. Existing `runs/json/*-entities.json` files become canonical at populate time — no new LLM run is needed.
- **Deterministic normalizer** (`migration_oracle/pipeline/canonical/`): cleans backticks/quotes/`@`/trailing `()`, splits the three Angular package spellings (`@angular/core InjectFlags`, `@angular/router:Router`, `@angular/core/rxjs-interop RxResourceOptions`) into package + bare symbol, gives `TestBed.get` one `member` key whether the model said `class` or `property`, attaches bare options to their rule's replacement symbol (`exhaustive` → `provideCheckNoChangesConfig.exhaustive`), maps template operators (`in`, `void`, `@defer`, …) to new `TemplateSyntax` nodes and `NGxxxx` codes to new `DiagnosticCode` nodes, and files dotted config keys under their file (`engines.node` → `package.json`). Spring Boot / WildFly names stay byte-for-byte; only the key is computed.
- **Angular API verification.** For each hop the golden public-API files (`goldens/public-api/**/index.api.md` in `angular/angular`) are fetched at both version tags (GitHub token, cached under `ARTIFACT_CACHE_DIR/api-index/angular/<version>.json`) and each symbol is resolved to its entry point. Symbols found in several entry points pick the one matching a rule dependency, else stay `ambiguous` with `package: "?"`. Unverified entities are still written, marked `verified: false`; nothing is dropped. When the index cannot be fetched, populate continues with all npm entities unverified and the summary records `api_index: unavailable`.
- **Canonical audit artifacts.** `runs/canonical/<framework>-<from>-to-<to>-canonical.jsonl` holds one line per entity occurrence (raw kind/name, canonical fields, the applied normalization steps); `…-summary.json` counts per kind, verified percentages, collapsed raw names, and the `unverified_keys` manual-review list. `--dry-run` writes both without graph writes — the cheap way to review a hop.
- **Prompt naming rules.** `DOSSIER_ENTITY_PROMPT_VERSION` is 3: the Angular profile now asks for the bare exported symbol in `name`, the import path in the new optional `package` field, `Owner.member` for members, and `kind: "syntax" | "diagnostic"` where appropriate.

### Changed

- **Constraints.** The `class_name` / `property_name` / `dependency_name` uniqueness constraints are replaced by `*_key IS UNIQUE` constraints (plus new `template_syntax_key` and `diagnostic_code_key`); `name` gets plain indexes since it is no longer unique (`VERSION` exists in several Angular entry points). Startup drops the old name constraints automatically.
- `seed_deprecated_classes` and step-entity writes merge on `maven:<FQCN>` / canonical keys.
- After canonicalization no `Class` or `ApplicationProperty` name contains `:`, so the `groupId:artifactId` heuristic in `mcp/matching.py` only sees real dependencies. No MCP tool changed.

### Fixes (review 2026-11-06)

- **API index was always empty.** The golden parser expected `export declare` with two-space members, but the files are API Extractor reports (`export class X {`, four-space members). It now parses exported declarations, `export { X as Y }` aliases (`NgFor`, `Location`), the type of `export const TestBed: TestBedStatic`, and inline function option fields (`provideCheckNoChangesConfig.exhaustive`); re-exports of imported symbols are skipped. Test fixtures are real golden excerpts. On the 8 Angular hops verified npm occurrences go from 0% to 86%.
- **Golden listing was always empty.** The Contents API returns `type: "dir"`, not `"tree"`, and subtree paths lost their entry point. One `git/trees/<tag>:goldens/public-api?recursive=1` request replaces it; pre-v19 `index.md` goldens are accepted.
- **`GITHUB_TOKEN` was not used on populate**, so index fetches hit the 60/h anonymous limit.
- A missing tag no longer drops the whole hop: the index is `partial` and the summary lists `missing_versions`.
- `primitives/*` / `testing` entry points no longer make `Injector`, `InjectionToken`, `inject`, `Attribute` ambiguous.
- Bare options take their owner from the API index first (`useNgZoneOnStable` → `provideExperimentalCheckNoChangesForDebug`, not its replacement).
- `<pkg>#<sym>` is split; LLM `kind: syntax | diagnostic` is kept for tokens outside the profile list; non-identifiers such as `ng-reflect-*` get no owner.
- An existing `Version` node is skipped before canonicalization (no index fetch, no audit rewrite) unless `--dry-run`.
- Maven entities are `verified: "unchecked"` instead of an unchecked `"true"`.

## [Unreleased] — 2026-11-06

### New features

- **Version aliases.** `FROM`/`TO` accept `latest`, `latest-ga` (`latest-stable`), and `X.Y.Z-SNAPSHOT`. A snapshot resolves to the newest published build of that version (for example `4.2.0-SNAPSHOT → 4.2.0-RC2`); an unpublished line is an error. Aliases are resolved before artifact paths and `Version` nodes are named.

### Fixes

- **Minor hops read every covered release.** A Spring Boot minor hop used to read only the `to` release notes, so `4.0.0 → 4.1.0` lost everything from `4.1.0-M1 … RC1` and `4.1.0 → 4.1.2` lost `4.1.1`. It now reads all releases after `from` up to `to` on the target line, keeping duplicated rows once.
- **Stale raw files are re-extracted.** In hop-by-hop mode a raw file whose range or hop sections do not match the hop (old whole-range layout) is re-extracted instead of being reused.

## [024-dossier-entities] — 2026-11-05

### New features

- **Dossier entities.** When research is enabled, graph entities are built from the research dossiers instead of the filter LLM. An action gate drops rows whose dossier says `**Action:** none`, except `breaking`, `deprecation`, and `security`. Rows that share a pull request, commit, issue, or JIRA key are clustered, and each cluster gets one entity call. `runs/nodes/*_filtered.md` is rendered from those entities, so `filteredMdPath` is unchanged.
- `--entity-source dossier|filter` (env `ENTITY_SOURCE`). `filter`, research disabled, and `--skip-research` keep the previous filter-LLM path. `--entity-source dossier --skip-research` is an error.
- `--stop-after-clusters` writes `runs/clusters/` (gate decisions and cluster membership) and stops before any entity call. It does not need `MODEL_*`.
- Per-cluster entity cache under `ARTIFACT_CACHE_DIR/entities/`. A changed dossier re-runs only that cluster. `--force-llm` ignores the cache. Duplicate titles in one hop are suffixed with the source URL tail so distinct changes are not merged in the graph.
- **Research reuses `runs/research/*-research.jsonl`.** Before the row cache, each research row is looked up by `row_key` in the hop's existing JSONL. A line is used when it is not `error` and its `prompt_version` and `model` match the current `PROMPT_VERSION` and `RESEARCH_MODEL_ID`, so a hop whose JSONL is complete makes no research model calls even with an empty `ARTIFACT_CACHE_DIR`. Hand edits to a dossier's text are used. `--force-research` ignores the JSONL. The summary has a new `artifact_hits` count.
- `TRIAGE_DROP_MAX_ACTION_PROB` now defaults to `0.20` (was `0.10`).

### Fixes (review)

- A dossier run deletes `_filtered.md.input.sha256`, so switching back to `--entity-source filter` calls the filter LLM instead of reusing the rendered document.
- A hop with any failed entity cluster writes its artifacts but is not populated; the run exits 3 after the remaining hops. Previously the partial batch was populated and the missing rules could not be added later.
- GitHub `.patch` / `.diff` / `/files` / `/commits/<sha>` / `patch-diff` URLs are clustered with the plain pull, commit, or issue URL.
- The per-cluster cache key covers the triage category, statement, and source, not only the dossier text. `DOSSIER_ENTITY_PROMPT_VERSION` is 2.
- The cluster input puts `Triage:` under its `## Row n` heading; cluster splits and failures are no longer logged twice.

### Configuration

- `ENTITY_CONCURRENCY` (default 4), `CLUSTER_MAX_ROWS` (default 4), `CLUSTER_CONFIRM` (default `off`), `GATE_PROTECTED_CATEGORIES` (default `breaking,deprecation,security`).
- Dedicated entity model: `ENTITY_MODEL_PROVIDER` (`openai` | `deepseek`), `ENTITY_MODEL_ID`, `ENTITY_BASE_URL`, `ENTITY_API_KEY`, `ENTITY_OUTPUT_FORMAT`, `ENTITY_THINKING`, `ENTITY_REASONING_EFFORT`, `ENTITY_MAX_OUTPUT_TOKENS`, `ENTITY_TIMEOUT_SEC`. OpenAI uses strict `json_schema` structured output with `reasoning_effort`; DeepSeek uses `json_object` with thinking enabled. Unset `ENTITY_MODEL_ID` keeps `MODEL_*`.

## [023-per-change-research] — 2026-11-04

### New features

- **Default hop granularity is now `minor`**: `HOP_GRANULARITY` / `--hop-granularity` default to one hop per minor line (`19.0.0 → 19.1.0 → 19.2.0 → 20.0.0`) instead of every patch release. Pass `--hop-granularity patch` (or set `HOP_GRANULARITY=patch`) for the old behaviour.
- **Fetch-only research**: `TAVILY_API_KEY` is now optional. Without it research still runs when `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID` are set. The model gets only `fetch_url` and reads the row Sources and the pages they link to. With a key, prompt, tools and cache are unchanged. Fetch-only rows use their own cache key.
- **Per-change research** runs after the filter and before the entity LLM. A small tool-calling model reads each filtered row, searches with Tavily, and fetches the cited pages. It writes a fact dossier (`runs/research/*-research.jsonl`) and does not write migration steps. The entity prompt receives those dossiers as a Research appendix and is told to prefer cited facts over memory.
- Filtered tables gain a `Sources` column (comma-separated source URLs, or `N/A`). The entity step copies the first of those URLs into `source_url`. Older filtered files without the column still parse.
- Research stays off unless `RESEARCH_BASE_URL` and `RESEARCH_MODEL_ID` are set (`TAVILY_API_KEY` only enables `web_search`). `--skip-research` leaves the entity input unchanged. `--force-research` ignores the row cache. A row that times out, exceeds its tool budget, or returns invalid JSON is passed through to the entity step unchanged.
- An exhausted Tavily quota (HTTP 432, 433, 401, or 429 after three attempts) stops that hop with exit code 2. Finished rows stay cached, and a re-run continues from the rows that were not finished. Fetches to private, loopback, or link-local addresses are refused.
- Error dossiers are not cached, so a model or Tavily outage does not hide rows from later runs. The research cache is keyed per framework and hop (prompt version 2). Using the full tool budget now yields a dossier instead of an error. Raw statements are attached by issue/PR/commit links and skip Source URLs shared by many rows (`RESEARCH_SHARED_URL_MAX_ROWS`, `RESEARCH_RAW_CONTEXT_MAX_CHARS`). The per-section entity split skips summary sections.
- Prompt review: the filter's `Sources` column now lists the issue/PR/commit/JIRA links inside each statement instead of the shared release-notes page; the triage input column is `Impact score`; `Category` maps explicitly to sections; split filter parts keep the framework header and omit summaries. The research prompt documents every dossier field and the hop's version lines (`PROMPT_VERSION` 3), and a row's own Sources are always trusted. The entity prompt explains research blocks and fills `subsystem` / `cli_operation` only for WildFly.
- `--stop-after-research` stops a run after the research stage (no entity LLM, no graph writes).
- Research now runs right after triage, on every kept row, and before the filter LLM. The filter LLM writes the migration document from the kept rows plus a Research appendix (blocks tied to rows by Sources), and the entity LLM receives that document plus the research merged per document row. `--stop-after-research` stops before the filter LLM, so it needs no `MODEL_*`. `MODEL_ID` is now required and checked only for steps that call the main LLM; `langchain-openai` is a dependency for `MODEL_PROVIDER=openai`.
- Triage and research show a `tqdm` progress bar per hop on a terminal (stderr; `keep/drop/error` and `ok/not_found/error/cached` counts). Bars are off when output is not a TTY or with `TQDM_DISABLE=1`.

### Changed

- Research budgets: `RESEARCH_MAX_TOOL_CALLS` defaults to `12` (was `6`) and `RESEARCH_TIMEOUT_SEC` to `240` (was `120`). The per-request model timeout is now its own setting, `RESEARCH_MODEL_TIMEOUT_SEC` (`60`), so one hung completion no longer consumes the whole row budget.

## [022-system1-change-triage] — 2026-11-04

### New features

- **System-1 change triage** runs after extraction and before the filter LLM. A fast local classifier (`TRIAGE_BASE_URL` + `TRIAGE_MODEL`, contract `POST /v1/systemone`) labels every raw row. Only rows that are confidently noise are dropped; low confidence, errors, timeouts, and an unreachable endpoint keep the row. With triage off, the raw file and the filter input stay the historical 4-column table.
- Raw files gain triage columns and a `Triage:` summary line. `runs/triage/*-triage.jsonl` stores full probability distributions so `--retriage-from-cache` can retune thresholds without another model call. `--skip-triage` and `--force-triage` control the stage. Answers are cached by questions version, model, and state.
- The filter prompt uses `Category` and `Impact` when those columns are present, and splits an oversized kept table into category groups.
- `runs/nodes/*.md` follows the kept rows. A `*.input.sha256` file next to it records the filter input. When triage changes which rows are kept, the cached filtered Markdown and entities JSON are regenerated instead of being silently reused.

## [021-github-change-enrichment] — 2026-11-04

### New features

- Spring Boot GitHub release rows that cite an issue or pull request are enriched from the GitHub Issues API (title, cleaned body, labels, close reason) so later filter and entity steps see more than the one-line release note. A short backport or forward-port pointer is replaced with the original issue body, one level only.
- Angular release and changelog rows that cite a commit are enriched from the commit message (scope, body, breaking and deprecation footers, linked issue, schematic files). A row with only a pull or issue link uses the issue path. Requires `GITHUB_TOKEN`. Disable with `SPRING_BOOT_GITHUB_ENRICHMENT=false` or `ANGULAR_GITHUB_ENRICHMENT=false`. A primary rate-limit response stops further issue and commit fetches for the rest of the run without dropping the hop.

## [hop-granularity] — 2026-11-04

### New features

- **Configurable ingestion step size**: `export-extract-populate-framework` accepts `--hop-granularity patch|minor` (env `HOP_GRANULARITY`, default `patch`). `minor` collapses each minor line into one hop while keeping patch endpoints (`3.3.12 → 3.4.0 → 3.4.2`).
- **`--hop-by-hop` / `--no-hop-by-hop`** (env `HOP_BY_HOP`, default off): runs filter LLM, entity LLM, and graph population once per version hop, so each hop gets its own raw/filtered/entities artifacts and its own `Version` node carrying only that hop's rules. Cache resolution and `--skip-existing` apply per hop, so an interrupted range resumes at the first missing hop; `--output-*` overrides are rejected because paths are derived per hop.
- **Per-hop BOM diff** under `--hop-by-hop` (`BaseExtractor.extract_contexts(per_hop_range_metadata=True)`) — patch-level dependency and CVE movement was previously flattened into one range-level diff.
- **Prereleases are ordinary versions**: `4.1.0-RC1`, `4.1.0-M1`, `22.0.0-rc.2`, `20.0.0-next.3` and the JBoss `26.1.2.Final` spelling now parse. Prerelease `sortableVersion` sits below the GA release it precedes (`4.1.0-M1` → 4000901, `4.1.0-RC1` → 4000951, `4.1.0` → 4001000), so **GA integers are unchanged** and no backfill is required. New `Version` properties: `preRelease`, `preReleaseLabel`.
- **`scripts/run_spring_boot_patch_ingest.sh`**: GA-only patch-level Spring Boot ingestion by default (extract-only unless `full`), with `SPRING_INCLUDE_PRERELEASE=1` to include milestone/RC hops.

### Bug fixes

- `version_key()` ignored prerelease suffixes, so `4.1.0-M1`, `4.1.0-RC1` and `4.1.0` compared equal: discovery order decided hop sequences, and a range ending at `4.1.0-RC1` also swallowed the GA release.
- Spring Boot minor-line wiki pages (`Spring-Boot-{major}.{minor}-Release-Notes`) were attached to every hop that landed inside the line — measured 57 duplicated rows in each of the 13 hops of a 3.3.x range. They are now attached only to the hop that **enters** the line. `extract()` calls without a `hop_context` keep the previous behaviour.

## [013a-live-probe-fixes] — 2026-06-15

### Behavioural change (breaking for callers that persist rule_id)

- `analyze_upgrade_path`, `build_recipe_plan`, and `get_pending_steps` now return `rule_id` as the stable `MigrationRule.ruleId` property (`pipeline://…` for pipeline rules, `community://…` for community insights), falling back to `elementId(rule)` only when no `ruleId` property exists. Callers that persisted the previous element-ID-based `rule_id` must re-key their stored values.

### New features

- **Server build provenance**: `get_graph_schema` now includes a `server_build` block (`git_sha`, `branch`, `feature_tags`, `started_at`). Set `GIT_SHA`, `GIT_BRANCH`, `FEATURE_TAGS` env vars at deploy time.
- **`matched_entities`** added to `analyze_upgrade_path` rule objects (exact-string matching against scanned entities).
- **Recipe coverage diagnostic**: `build_recipe_plan` now returns `diagnostics.recipes_loaded` (bool) and `diagnostics.recipe_count` (int), making the zero-recipe state visible.
- **`context_id` parameter** added to `build_recipe_plan` (optional); when provided, version range is derived from the context's resolved `UPGRADES_FROM`/`UPGRADES_TO` bounds.
- **`reused`, `entityCount`, `droppedCount`** always present on `create_migration_context` response (both create and resume paths).
- **`solution` field** added to `search_migration_knowledge` hit objects.
- Community insights now receive a stable `ruleId` of the form `community://{framework}/{version}/{uuid}` at create time.

### Bug fixes

- Zombie context guard: if `create_migration_context` resumes a context whose `UPGRADES_FROM`/`UPGRADES_TO` edges point to wrong nodes, it deletes and re-creates the context.
- `search_migration_knowledge` hits now include `solution` field (was missing from serializer).
- `_ANALYZE_UPGRADE_PATH` Cypher now includes the package-prefix bridge for Dependency-only rules (matching scanned class FQCNs against dependency groupId prefix), consistent with `_GET_PENDING_STEPS`.
- `build_recipe_plan` entity matching now uses exact-string comparison (was using `.lower()`, diverging from how typed buckets are populated).

### Follow-up (FU-1 — out of scope)

- Community rule `ruleId` was previously not written at all by `submit_migration_insight`. Now set to `community://…` at create time. Existing community rules created before this release still have no `ruleId` and rely on the `coalesce(rule.ruleId, elementId(rule))` fallback, which remains rebuild-unstable for those nodes. Owner: TBD.

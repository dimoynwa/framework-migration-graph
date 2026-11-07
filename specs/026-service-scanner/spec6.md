# Feature Specification 026.6: Maven + Gradle Manifests, Spring Boot Version

**Feature Branch**: `026-service-scanner`

**Created**: 2026-11-06 (split from the single 026 spec)

**Status**: Implemented (2026-11-06), review fixes 2026-11-07. AC-6 and AC-7 met; both build
systems read without executing a build, and an unresolved value is never reported as a version
(framework, plugin or dependency). Decided in review: a `buildscript` classpath
`spring-boot-gradle-plugin:X` is the plugin's version (FR-3 source 3a), and the repo's own
groupIds are excluded from the groupIds handed to spec7.

**Depends on**: spec1 (modules, extractor contract, profile writer). Independent of spec2–spec5.
Shared context: see `spec1.md`.

**Scope**: manifest readers for `pom.xml`, `build.gradle(.kts)`, `settings.gradle(.kts)`,
`gradle/libs.versions.toml`, `gradle.properties`, and the Spring Boot version detector. No Java
source parsing yet (spec7).

## Requirements

### FR-3 Framework detection (Spring Boot part)

**Spring Boot version**, per module, first that applies:
1. Maven `<parent>` `org.springframework.boot:spring-boot-starter-parent`;
2. Maven BOM import `org.springframework.boot:spring-boot-dependencies` in
   `<dependencyManagement>`;
3. Gradle plugin `id 'org.springframework.boot' version 'X'`, or the same in a version catalog;
   a plugin applied without a version (`apply plugin:`) takes it from a `buildscript`
   `classpath "org.springframework.boot:spring-boot-gradle-plugin:X"` (decided in review);
4. Gradle `platform("org.springframework.boot:spring-boot-dependencies:X")`.

A child module with no own declaration inherits from its in-repo parent (Maven parent chain,
Gradle root project). Result → `modules[].frameworks[] = {name: "spring-boot", version, raw, source}`.

### FR-8 Java build manifests

**`pom.xml`** (stdlib `xml.etree`, namespaces stripped; external entities are not resolved)
- `<parent>`, `<dependencies>`, `<dependencyManagement>` (incl. `<scope>import</scope>` BOMs),
  `<build><plugins>` / `<pluginManagement>` → `dependencies[]` with
  `{key: "maven:<groupId>:<artifactId>", version, scope, kind: dependency|bom|parent|plugin, module}`.
  `kind` is already in the spec1 model; one entry per `(key, module, scope, kind)`, so the same
  artifact in `<dependencies>` and as an imported BOM gives two entries.
- `${prop}` is resolved from `<properties>` of the pom and its in-repo parents (by relative
  `<parent><relativePath>` or the parent directory), plus `${project.version}` /
  `${project.parent.version}`. Unresolved values keep the raw text and add a diagnostic.
- `<properties>` entries → `cfg:pom.xml#properties.<name>` (for example `java.version`).
- Multi-module: `<modules>` are followed; each module is a module root (spec1 FR-3).

**`build.gradle` / `build.gradle.kts`, `settings.gradle(.kts)`** (no Gradle execution; a
tolerant lexer for the common forms, not a Groovy / Kotlin parser)
- `plugins { id 'x' version 'v' }`, `id("x") version "v"`, `apply plugin: 'x'`,
  `alias(libs.plugins.x)` → `{key: "gradle-plugin:<id>", version, kind: plugin}`.
- Dependencies in any configuration (`implementation`, `api`, `compileOnly`, `runtimeOnly`,
  `testImplementation`, `annotationProcessor`, …):
  - string notation `'g:a:v'`, `"g:a"` → `maven:g:a`;
  - map notation `group: 'g', name: 'a', version: 'v'`;
  - `platform(…)` / `enforcedPlatform(…)` → `kind: bom`;
  - version catalog accessors `libs.spring.boot.starter.web` → resolved via
    `gradle/libs.versions.toml` (stdlib `tomllib`), including `version.ref`.
- `ext { springBootVersion = '…' }`, `extra["…"]` and `gradle.properties` resolve `$var` /
  `${var}`. Unresolved → raw text + diagnostic.
- `java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }`, `sourceCompatibility`
  → `cfg:build.gradle#java.toolchain.languageVersion`, `cfg:build.gradle#sourceCompatibility`.
- `settings.gradle` `include(...)` lists subprojects (module roots).
- A construct the lexer does not understand is skipped; a dependency-looking line it cannot
  parse → diagnostic `unparsed_gradle`.

**groupIds for spec7**: the set of declared groupIds per module is kept, so spec7 can recognize
fully qualified usages without import. The repo's own groupIds (every module's and in-repo
parent's Maven `<groupId>`, Gradle `group = …`) are excluded repo-wide (decided in review).

## Acceptance Criteria

- **AC-6 Maven**: parent, BOM import, `${prop}` from a parent pom, plugins, multi-module.
  Spring Boot version detected from parent and from a BOM. An unresolved `${x}` → raw text +
  diagnostic. `cfg:pom.xml#properties.java.version` recorded.
- **AC-7 Gradle**: Groovy and Kotlin DSL, string / map / `platform()` notation, version catalog
  with `version.ref`, `ext` and `gradle.properties` variables, an unresolved variable →
  diagnostic. Spring Boot version from the plugin, from a catalog plugin alias and from
  `platform(spring-boot-dependencies)`. `settings.gradle` `include` → module roots.
  Toolchain / `sourceCompatibility` config keys.

- **Regression**: after implementing this spec, run the whole suite `pytest tests/scanner/` (plus the 025 tests, which use `migration_keys/`), not only the new tests. Tests from every earlier spec already implemented (spec1–spec5 in the default order) must still pass. A failing earlier test that checks **behavior** is a regression, not an outdated test. A test that pins an internal detail (the exact contents of a registry, a private helper's shape) may be changed deliberately when this spec extends that detail; such a change is named in the spec's CHANGELOG entry.

## How to test after spec6

```bash
migration-scan /path/to/spring-service
jq '.framework, [.dependencies[] | {key, version, kind}]' .migration/profile.json
mvn help:effective-pom -q | grep spring-boot   # or ./gradlew dependencies — compare the Boot version
```

Expected: `spring-boot <version>` in the summary line, all declared dependencies, plugins and
BOMs, and every `unresolved_variable` explained by an actually external value.

## Implementation Notes

- Modules: `migration_planner/scanner/maven.py`, `migration_planner/scanner/gradle.py`.
- Stdlib only (`xml.etree`, `tomllib`, `re`).

## Estimate

~6 h: Maven + Gradle (+ catalog, variables) 5 h; fixtures and tests 1 h.

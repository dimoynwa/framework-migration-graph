# OpenRewrite Recipe Catalog

Common recipes with artifact coordinates and parameter schemas.

> Last updated: June 2026 from [docs.openrewrite.org/recipes](https://docs.openrewrite.org/recipes) and [latest module versions](https://docs.openrewrite.org/reference/latest-versions-of-every-openrewrite-module)

---

## Version resolution (read first)

| Build tool | How to specify recipe library version |
|------------|--------------------------------------|
| **Maven** (`-Drewrite.recipeArtifactCoordinates=`) | `LATEST` works |
| **Gradle init script** | **`LATEST` fails** — use one of the options below |

**Recommended for Gradle** — BOM + module (no version on the module):

```groovy
dependencies {
    rewrite(platform("org.openrewrite.recipe:rewrite-recipe-bom:latest.release"))
    rewrite("org.openrewrite.recipe:rewrite-jackson")  // version comes from BOM
}
```

**Alternative** — pin the release from Maven metadata:

```bash
curl -s "https://repo1.maven.org/maven2/org/openrewrite/recipe/<ARTIFACT>/maven-metadata.xml" \
  | grep -o '<release>[^<]*</release>' | sed 's/[<>/a-z]//g'
```

### Current releases (June 2026)

| Artifact | Latest | Used by sections |
|----------|--------|------------------|
| `rewrite-migrate-java` | 3.36.0 | Java Migration |
| `rewrite-spring` | 6.32.0 | Spring Boot / Security / Cloud |
| `rewrite-testing-frameworks` | 3.37.0 | Testing |
| `rewrite-jackson` | 1.24.0 | Jackson |
| `rewrite-quarkus` | 2.33.0 | Quarkus |
| `rewrite-micronaut` | 2.34.1 | Micronaut |
| `rewrite-hibernate` | 2.21.0 | Hibernate |
| `rewrite-apache` | 2.27.0 | Apache |

### Minimum artifact versions for newer recipes

If `rewriteDiscover` or `rewriteRun` reports `Recipe(s) not found`, the artifact is likely **too old** — bump to latest (or use the BOM).

| Recipe | Artifact | Minimum version | Notes |
|--------|----------|-----------------|-------|
| `org.openrewrite.java.jackson.UpgradeJackson_2_3` (+ all `UpgradeJackson_2_3_*` sub-recipes) | `rewrite-jackson` | **1.0.0** (use latest 1.x) | Absent from 0.x — only older recipes like `CodehausToFasterXml` |
| `org.openrewrite.java.spring.boot4.*` | `rewrite-spring` | **6.x** (use latest) | Boot 4 / modular starters / `@MockBean` replacements |
| `org.openrewrite.java.spring.cloud2024.*`, `cloud2025.*` | `rewrite-spring` | **6.x** (use latest) | Recent Spring Cloud release trains |
| `org.openrewrite.java.migrate.UpgradeToJava25` | `rewrite-migrate-java` | **3.x** (use latest) | Java 25 support added in recent 3.x releases |
| `org.openrewrite.quarkus.Quarkus3Migration` | `rewrite-quarkus` | **2.x** (use latest) | Quarkus 3 recipes live in 2.x line |
| `org.openrewrite.java.micronaut.Micronaut3to4Migration` | `rewrite-micronaut` | **2.x** (use latest) | Micronaut 4 migration |

Always verify with `./gradlew rewriteDiscover --init-script rewrite-init.gradle | grep <RecipeName>` before running.

---

## Java Migration

Artifact: `org.openrewrite.recipe:rewrite-migrate-java` (latest **3.36.0**)

| Recipe | Notes |
|--------|-------|
| `org.openrewrite.java.migrate.java8tojava11` | Migrate to Java 11 (composite) |
| `org.openrewrite.java.migrate.UpgradeToJava17` | Migrate to Java 17 (composite) |
| `org.openrewrite.java.migrate.UpgradeToJava21` | Migrate to Java 21 (composite) |
| `org.openrewrite.java.migrate.UpgradeToJava25` | Migrate to Java 25 (composite). Requires **rewrite-migrate-java 3.x+** |
| `org.openrewrite.java.migrate.UpgradeBuildToJava11` | Update build tool config only |
| `org.openrewrite.java.migrate.UpgradeBuildToJava17` | Update build tool config only |
| `org.openrewrite.java.migrate.UpgradeBuildToJava21` | Update build tool config only |
| `org.openrewrite.java.migrate.UpgradeBuildToJava25` | Update build tool config only (non-Kotlin) |
| `org.openrewrite.java.migrate.UpgradeBuildToJava24` | Update build tool config only (Kotlin pre-2.3) |
| `org.openrewrite.java.migrate.UpgradeJavaVersion` | Parameterized: `version` (e.g. `21`) |
| `org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta` | Javax → Jakarta EE 9 |
| `org.openrewrite.java.migrate.JavaBestPractices` | Java best practice modernizations |

---

## Spring Boot

Artifact: `org.openrewrite.recipe:rewrite-spring` (latest **6.32.0**)

### Spring Boot 2.x

| Recipe |
|--------|
| `org.openrewrite.java.spring.boot2.UpgradeSpringBoot_2_7` |
| `org.openrewrite.java.spring.boot2.SpringBoot2JUnit4to5Migration` |

### Spring Boot 3.x

| Recipe | Notes |
|--------|-------|
| `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_1` | |
| `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_2` | |
| `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_3` | |
| `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_0-community-edition` | Community edition |
| `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_4-community-edition` | Community edition |
| `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_5-community-edition` | Community edition |
| `org.openrewrite.java.spring.boot3.SpringBoot33BestPractices` | Best practices (3.3+) |
| `org.openrewrite.java.spring.boot3.EnableVirtualThreads` | Enable virtual threads (Java 21+) |

### Spring Security

| Recipe | Artifact |
|--------|----------|
| `org.openrewrite.java.spring.security5.*` | `rewrite-spring` |
| `org.openrewrite.java.spring.security6.*` | `rewrite-spring` |

### Spring Boot 4.x

| Recipe | Notes |
|--------|-------|
| `org.openrewrite.java.spring.boot4.UpgradeSpringBoot_4_0-community-edition` | **Full Spring Boot 3.x → 4.0 migration** (Community Edition, composite). Requires **rewrite-spring 6.x+** |
| `org.openrewrite.java.spring.boot4.SpringBootProperties_4_0` | Migrate Spring Boot properties to 4.0 |
| `org.openrewrite.java.spring.boot4.MigrateToModularStarters-community-edition` | Migrate to Spring Boot 4.0 modular starters (Community Edition). Requires **rewrite-spring 6.x+** |
| `org.openrewrite.java.spring.boot4.MigrateAutoConfigurePackages` | Migrate packages to modular starters |
| `org.openrewrite.java.spring.boot4.RenameDeprecatedStartersManagedVersions` | Rename deprecated Boot 4.0 starters |
| `org.openrewrite.java.spring.boot4.ReplaceMockBeanAndSpyBean` | Replace `@MockBean` and `@SpyBean` |

### Spring Cloud

| Recipe | Artifact | Notes |
|--------|----------|-------|
| `org.openrewrite.java.spring.cloud2022.*` | `rewrite-spring` | |
| `org.openrewrite.java.spring.cloud2023.*` | `rewrite-spring` | |
| `org.openrewrite.java.spring.cloud2024.*` | `rewrite-spring` | Requires **rewrite-spring 6.x+** |
| `org.openrewrite.java.spring.cloud2025.*` | `rewrite-spring` | Requires **rewrite-spring 6.x+** |

---

## Testing

Artifact: `org.openrewrite.recipe:rewrite-testing-frameworks` (latest **3.37.0**)

| Recipe |
|--------|
| `org.openrewrite.java.testing.junit5.JUnit4to5Migration` |
| `org.openrewrite.java.testing.mockito.Mockito1to4Migration` |
| `org.openrewrite.java.testing.mockito.MockitoJUnit4ToJUnit5` |

---

## Java Core (no external artifact needed)

These live in the core library — omit `recipeArtifactCoordinates` / `rewrite(...)` dependency.

| Recipe | Parameters |
|--------|-----------|
| `org.openrewrite.java.RemoveUnusedImports` | — |
| `org.openrewrite.java.format.AutoFormat` | — |
| `org.openrewrite.java.ChangePackage` | `oldPackageName`, `newPackageName`, `recursive` (optional bool) |
| `org.openrewrite.java.ChangeType` | `oldFullyQualifiedTypeName`, `newFullyQualifiedTypeName` |
| `org.openrewrite.java.ChangeMethodName` | `methodPattern`, `newMethodName` |
| `org.openrewrite.java.AddImport` | `type`, `staticMethod` (optional) |
| `org.openrewrite.java.RemoveAnnotation` | `annotationPattern` |
| `org.openrewrite.java.AddCommentToMethod` | `methodPattern`, `comment` |
| `org.openrewrite.java.OrderImports` | — |
| `org.openrewrite.java.UseStaticImport` | `methodPattern` |
| `org.openrewrite.java.ShortenFullyQualifiedTypeReferences` | — |
| `org.openrewrite.staticanalysis.CommonStaticAnalysis` | — |

---

## Maven-specific

All Maven recipes are in the core library — no `recipeArtifactCoordinates` needed.

| Recipe | Key Parameters |
|--------|----------------|
| `org.openrewrite.maven.UpgradeDependencyVersion` | `groupId`, `artifactId`, `newVersion` |
| `org.openrewrite.maven.RemoveDependency` | `groupId`, `artifactId`, `scope` (optional) |
| `org.openrewrite.maven.AddDependency` | `groupId`, `artifactId`, `version`, `scope` (optional) |
| `org.openrewrite.maven.ChangeDependencyGroupIdAndArtifactId` | `oldGroupId`, `oldArtifactId`, `newGroupId`, `newArtifactId` |
| `org.openrewrite.maven.RemoveManagedDependency` | `groupId`, `artifactId`, `scope` (optional) |
| `org.openrewrite.maven.ExcludeDependency` | `groupId`, `artifactId` |
| `org.openrewrite.maven.AddManagedDependency` | `groupId`, `artifactId`, `version`, `scope` (optional) |
| `org.openrewrite.maven.ChangeParentPom` | `oldGroupId`, `oldArtifactId`, `newGroupId`, `newArtifactId`, `newVersion` |
| `org.openrewrite.maven.UpdateMavenWrapper` | `wrapperVersion` (optional), `distributionVersion` (optional) |

---

## Gradle-specific

All Gradle recipes are in the core library — no `recipeArtifactCoordinates` needed.

| Recipe | Key Parameters |
|--------|----------------|
| `org.openrewrite.gradle.UpgradeDependencyVersion` | `groupId`, `artifactId`, `newVersion` |
| `org.openrewrite.gradle.AddDependency` | `groupId`, `artifactId`, `version`, `configuration` |
| `org.openrewrite.gradle.RemoveDependency` | `groupId`, `artifactId`, `configuration` (optional) |
| `org.openrewrite.gradle.ChangeDependencyGroupId` | `groupId`, `artifactId`, `newGroupId` |
| `org.openrewrite.gradle.UpdateGradleWrapper` | `version` (optional), `distribution` (optional) |
| `org.openrewrite.gradle.AddProperty` | `key`, `value`, `overwrite` (optional), `filePattern` (optional) |
| `org.openrewrite.gradle.search.FindGradleProject` | — |

---

## Quarkus

Artifact: `org.openrewrite.recipe:rewrite-quarkus` (latest **2.33.0**)

| Recipe | Notes |
|--------|-------|
| `org.openrewrite.quarkus.Quarkus1to1_13Migration` | |
| `org.openrewrite.quarkus.Quarkus2Migration` | |
| `org.openrewrite.quarkus.Quarkus3Migration` | Requires **rewrite-quarkus 2.x+** |

---

## Micronaut

Artifact: `org.openrewrite.recipe:rewrite-micronaut` (latest **2.34.1**)

| Recipe | Notes |
|--------|-------|
| `org.openrewrite.java.micronaut.Micronaut2to3Migration` | |
| `org.openrewrite.java.micronaut.Micronaut3to4Migration` | Requires **rewrite-micronaut 2.x+** |

---

## Hibernate

Artifact: `org.openrewrite.recipe:rewrite-hibernate` (latest **2.21.0**)

| Recipe |
|--------|
| `org.openrewrite.hibernate.MigrateToHibernate62` |
| `org.openrewrite.hibernate.MigrateToHibernate63` |
| `org.openrewrite.hibernate.validator.HibernateValidator_8_0` |

---

## Jackson

Artifact: `org.openrewrite.recipe:rewrite-jackson` (latest **1.24.0**)

| Build tool | Version |
|------------|---------|
| Maven | `LATEST` works in `-Drewrite.recipeArtifactCoordinates` |
| Gradle init script | Use **BOM** (`rewrite-recipe-bom:latest.release`) or pin a **1.x** release — literal `LATEST` fails resolution |

| Recipe | Notes |
|--------|-------|
| `org.openrewrite.java.jackson.UpgradeJackson_2_3` | **Full Jackson 2.x → 3.x migration** (composite). Requires **rewrite-jackson 1.x** (absent from 0.x). Modifies `build.gradle`/`pom.xml`. On Gradle + OpenAPI codegen projects, bypass compile deps — see `SKILL.md` ## Troubleshooting. |
| `org.openrewrite.java.jackson.UpgradeJackson_2_3_dependencies` | Upgrade Jackson 2.x Maven/Gradle dependencies to 3.x only. Requires **1.x** |
| `org.openrewrite.java.jackson.UpgradeJackson_2_3_packagechanges` | Rename packages from 2.x to 3.x only. Requires **1.x** |
| `org.openrewrite.java.jackson.UpgradeJackson_2_3_methodrenames` | Rename 2.x methods to 3.x equivalents. Requires **1.x** |
| `org.openrewrite.java.jackson.UpgradeJackson_2_3_typechanges` | Update 2.x types to 3.x. Requires **1.x** |
| `org.openrewrite.java.jackson.JacksonBestPractices` | Jackson best practices (available in older 0.x too) |
| `org.openrewrite.java.jackson.CodehausToFasterXml` | Migrate from legacy Jackson Codehaus to FasterXML (available in 0.x) |

---

## Apache

Artifact: `org.openrewrite.recipe:rewrite-apache` (latest **2.27.0**)

| Recipe | Notes |
|--------|-------|
| `org.openrewrite.apache.camel.*` | Apache Camel migrations |
| `org.openrewrite.apache.httpclient5.*` | HttpClient 4→5 |

---

## Finding a Recipe

If the recipe the user wants is not listed here:
1. Direct them to the catalog at https://docs.openrewrite.org/recipes
2. The artifact coordinates can be inferred from the recipe's package name (use BOM or latest release for Gradle):
   - `org.openrewrite.java.migrate.*` → `rewrite-migrate-java`
   - `org.openrewrite.java.spring.*` → `rewrite-spring`
   - `org.openrewrite.java.testing.*` → `rewrite-testing-frameworks`
   - `org.openrewrite.java.*` (other) → usually core (no extra artifact needed)
   - `org.openrewrite.maven.*` → core (no extra artifact needed)
   - `org.openrewrite.gradle.*` → core (no extra artifact needed)
   - `org.openrewrite.quarkus.*` → `rewrite-quarkus`
   - `org.openrewrite.java.micronaut.*` → `rewrite-micronaut`
   - `org.openrewrite.hibernate.*` → `rewrite-hibernate`
   - `org.openrewrite.java.jackson.*` → `rewrite-jackson` (**1.x** for `UpgradeJackson_2_3`)
   - `org.openrewrite.staticanalysis.*` → core (no extra artifact needed)
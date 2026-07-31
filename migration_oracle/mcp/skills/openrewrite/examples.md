# OpenRewrite Runner — Full Worked Examples

---

## Example 1: Upgrade to Java 21 (Maven, no parameters)

**User request**: "Run the OpenRewrite recipe to migrate my Maven project to Java 21."

**Build tool**: Maven  
**Recipe**: `org.openrewrite.java.migrate.UpgradeToJava21`  
**Artifact**: `org.openrewrite.recipe:rewrite-migrate-java:LATEST`  
**Parameters**: none

**Command**:
```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-migrate-java:LATEST \
  -Drewrite.activeRecipes=org.openrewrite.java.migrate.UpgradeToJava21
```

---

## Example 2: Rename a Package (Maven, parameterized)

**User request**: "Use OpenRewrite to rename the package `com.acme.old` to `com.acme.new` in my Maven project."

**Build tool**: Maven  
**Recipe**: `org.openrewrite.java.ChangePackage`  
**Artifact**: core (no external artifact)  
**Parameters**: `oldPackageName`, `newPackageName`

**Step 1 — Create `rewrite.yml` in project root**:
```yaml
---
type: specs.openrewrite.org/v1beta/recipe
name: com.yourorg.RenameAcmePackage
displayName: Rename com.acme.old to com.acme.new
recipeList:
  - org.openrewrite.java.ChangePackage:
      oldPackageName: com.acme.old
      newPackageName: com.acme.new
      recursive: true
```

**Step 2 — Run**:
```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.activeRecipes=com.yourorg.RenameAcmePackage
```

**Step 3 — Cleanup**:
```bash
rm rewrite.yml
git diff
```

---

## Example 3: JUnit 4 → 5 Migration (Gradle, no parameters)

**User request**: "Migrate my Gradle project from JUnit 4 to JUnit 5 using OpenRewrite."

**Build tool**: Gradle (Groovy DSL)  
**Recipe**: `org.openrewrite.java.spring.boot2.SpringBoot2JUnit4to5Migration`  
**Artifact**: `org.openrewrite.recipe:rewrite-spring:LATEST`

**Step 1 — Create `rewrite-init.gradle` next to the project**:
```groovy
initscript {
    repositories {
        maven { url "https://plugins.gradle.org/m2" }
    }
    dependencies {
        classpath("org.openrewrite:plugin:latest.release")
    }
}

rootProject {
    plugins.apply(org.openrewrite.gradle.RewritePlugin)
    dependencies {
        rewrite("org.openrewrite.recipe:rewrite-spring:latest.release")
    }

    afterEvaluate {
        if (repositories.isEmpty()) {
            repositories {
                mavenCentral()
            }
        }
    }
}
```

**Step 2 — Run**:
```bash
./gradlew rewriteRun \
  --init-script rewrite-init.gradle \
  -Drewrite.activeRecipe=org.openrewrite.java.spring.boot2.SpringBoot2JUnit4to5Migration
```

**Step 3 — Cleanup**:
```bash
rm rewrite-init.gradle
git diff
```

---

## Example 4: Change Dependency Version (Gradle Kotlin DSL, parameterized)

**User request**: "Use OpenRewrite on my Kotlin Gradle project to upgrade Guava to 32.0.1-jre."

**Build tool**: Gradle (Kotlin DSL — `build.gradle.kts`)  
**Recipe**: `org.openrewrite.gradle.UpgradeDependencyVersion`  
**Artifact**: core  
**Parameters**: `groupId`, `artifactId`, `newVersion`

**Step 1 — Create `rewrite-init.gradle.kts`**:
```kotlin
initscript {
    repositories {
        maven { url = uri("https://plugins.gradle.org/m2") }
    }
    dependencies {
        classpath("org.openrewrite:plugin:latest.release")
    }
}

rootProject {
    plugins.apply(org.openrewrite.gradle.RewritePlugin::class.java)

    afterEvaluate {
        if (repositories.isEmpty()) {
            repositories {
                mavenCentral()
            }
        }
    }
}
```

**Step 2 — Create `rewrite.yml` in project root**:
```yaml
---
type: specs.openrewrite.org/v1beta/recipe
name: com.yourorg.UpgradeGuava
displayName: Upgrade Guava to 32.0.1-jre
recipeList:
  - org.openrewrite.gradle.UpgradeDependencyVersion:
      groupId: com.google.guava
      artifactId: guava
      newVersion: 32.0.1-jre
```

**Step 3 — Run**:
```bash
./gradlew rewriteRun \
  --init-script rewrite-init.gradle.kts \
  -Drewrite.activeRecipe=com.yourorg.UpgradeGuava
```

**Step 4 — Cleanup**:
```bash
rm rewrite.yml rewrite-init.gradle.kts
git diff
```

---

## Example 5: Spring Boot 3 Migration (Maven, no parameters)

**User request**: "Run the Spring Boot 3.3 migration recipe on my Maven project."

**Build tool**: Maven  
**Recipe**: `org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_3`  
**Artifact**: `org.openrewrite.recipe:rewrite-spring:LATEST`

**Command**:
```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-spring:LATEST \
  -Drewrite.activeRecipes=org.openrewrite.java.spring.boot3.UpgradeSpringBoot_3_3
```

> This recipe is large. Add `-Dorg.gradle.jvmargs=-Xmx4G` (Gradle) or set `MAVEN_OPTS=-Xmx4g` (Maven) if you run out of memory.

---

## Example 6: Dry Run Preview (Maven)

**User request**: "Show me what OpenRewrite would change without actually modifying files."

```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:dryRun \
  -Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-migrate-java:LATEST \
  -Drewrite.activeRecipes=org.openrewrite.java.migrate.UpgradeToJava21
```

Review output in console. No files are modified.

---

## Example 7: Jackson 2 → 3 Migration (Gradle, codegen project)

**User request**: "Execute `UpgradeJackson_2_3` on my Gradle project."

**Build tool**: Gradle (Groovy DSL)  
**Recipe**: `org.openrewrite.java.jackson.UpgradeJackson_2_3`  
**Artifact:** `org.openrewrite.recipe:rewrite-jackson` via BOM, or pin `1.24.0` (requires **1.x** — absent from 0.x; do **not** use literal `LATEST` in Gradle)

**Problem 1 — path does not exist:** User path `/Users/me/paysafe-wallet-switch` was wrong; actual project at `/Users/me/DevelopmentTools/paysafe-wallet-switch`. Always verify with `find` or `test -d`.

**Problem 2 — compile chain blocks rewrite (no `skipCompile` flag):** OpenRewrite has **no `skipCompile` flag**. The plugin wires `rewriteRun` → `compileJava` for every source set. Project has OpenAPI codegen (`apiGen` → `generate*ApiClientCode`). Codegen failed with Jackson classpath mismatch before OpenRewrite ran. **Fix:** init-script `setDependsOn([])` — not an official API.

**Problem 3 — `LATEST` unresolved:** Gradle init script with `rewrite-jackson:LATEST` fails artifact resolution. Use BOM or pinned version.

**Problem 4 — recipe not found on old artifact:** `rewrite-jackson:0.20.0` loaded but reported `Recipe(s) not found: UpgradeJackson_2_3`. Fixed by bumping to `1.24.0`.

**Step 1 — Create `rewrite-init.gradle`** (BOM + compile-bypass workaround):

```groovy
initscript {
    repositories {
        maven { url "https://plugins.gradle.org/m2" }
    }
    dependencies {
        classpath("org.openrewrite:plugin:latest.release")
    }
}

rootProject {
    plugins.apply(org.openrewrite.gradle.RewritePlugin)
    dependencies {
        rewrite(platform("org.openrewrite.recipe:rewrite-recipe-bom:latest.release"))
        rewrite("org.openrewrite.recipe:rewrite-jackson")
    }

    afterEvaluate {
        if (repositories.isEmpty()) {
            repositories {
                mavenCentral()
            }
        }

        // No skipCompile flag exists — this is the workaround for codegen projects
        tasks.matching { it.name == "rewriteRun" || it.name == "rewriteDryRun" }.configureEach { rewriteTask ->
            rewriteTask.setDependsOn([])
        }
    }
}
```

**Step 2 — Verify recipe is available:**

```bash
./gradlew rewriteDiscover --init-script rewrite-init.gradle --no-daemon 2>&1 | grep -i UpgradeJackson
```

**Step 3 — Run:**

```bash
./gradlew rewriteRun \
  --init-script rewrite-init.gradle \
  -Drewrite.activeRecipe=org.openrewrite.java.jackson.UpgradeJackson_2_3 \
  -Dorg.gradle.jvmargs=-Xmx4G \
  --no-daemon
```

**Step 4 — Review and cleanup:**

```bash
git diff --stat          # expect source + build.gradle changes
rm rewrite-init.gradle
./gradlew build          # may still fail on codegen until plugin is upgraded
```

> The recipe also modifies `build.gradle` (dependency versions, Jackson BOM removals) — that is intentional, not init-script leakage.

---

## Tips

- **Always `git commit` or `git stash` your working tree before running** so you can easily review diffs or roll back.
- **`LATEST` versions**: Maven accepts `LATEST` in `-Drewrite.recipeArtifactCoordinates`. **Gradle init scripts must use BOM (`rewrite-recipe-bom:latest.release`) or pin a real version** — literal `LATEST` fails. See `recipe-catalog.md` for minimum artifact versions per recipe.
- **No `skipCompile` flag**: To bypass compile/codegen on Gradle, use init-script `setDependsOn([])` — not a documented OpenRewrite option.
- **Multi-module Maven**: Run from the root `pom.xml` directory; the plugin handles submodules automatically.
- **Multi-project Gradle**: The init script's `rootProject` block covers the root; subprojects may need additional handling via the `subprojects { }` block in the init script.
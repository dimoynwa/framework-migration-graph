---
name: openrewrite-runner
description: >
  Executes OpenRewrite recipes on Maven or Gradle projects WITHOUT permanently adding OpenRewrite
  as a project dependency. Supports parameterized recipes, custom artifact coordinates, and
  multi-module projects. Use this skill whenever the user wants to run, apply, or execute an
  OpenRewrite recipe on their project — even if they phrase it as "apply a migration", "run a
  refactoring", "use OpenRewrite to upgrade", "run a rewrite recipe", or "migrate my project
  with OpenRewrite". Also trigger when the user provides a recipe name like
  `org.openrewrite.java.migrate.UpgradeToJava21` or artifact coordinates like
  `org.openrewrite.recipe:rewrite-migrate-java:LATEST`. Always use this skill instead of
  guessing the command syntax from memory — the correct flags differ by build tool and whether
  the recipe is parameterized.
---

# OpenRewrite Runner

Runs OpenRewrite recipes on Maven or Gradle projects **without permanently modifying the build files**.

## Quick Decision Tree

```
Does the project use Maven or Gradle?
├── Maven  → See ## Maven Execution
└── Gradle → See ## Gradle Execution

Does the recipe need configuration parameters?
├── No  → Simple one-liner command (inline flags)
└── Yes → Must use rewrite.yml wrapper + inline flag pointing to it
```

---

## Step 1 — Gather Information

Before generating commands, determine:

1. **Build tool**: Look for `pom.xml` (Maven) or `build.gradle` / `build.gradle.kts` (Gradle).
2. **Recipe ID** (fully-qualified name, e.g. `org.openrewrite.java.migrate.UpgradeToJava21`).
3. **Artifact coordinates** (if the recipe is NOT in the OpenRewrite core library):
   - Format: `groupId:artifactId:version` e.g. `org.openrewrite.recipe:rewrite-migrate-java:LATEST`
   - If the user doesn't know, consult the recipe catalog reference: `references/recipe-catalog.md`
4. **Recipe parameters**: key-value pairs required by the recipe (e.g. `oldPackageName`, `newPackageName`).
5. **Working directory**: where to run the command (project root, or a module sub-directory).
6. **Verify the path exists** before running. If the user-supplied path is missing, search for the project:
   ```bash
   find ~ -maxdepth 5 -type d -name "<project-dir-name>" 2>/dev/null
   ```
   Tell the user which path you actually used.

If any of items 2–4 are unclear, ask the user before generating commands.

### Resolve recipe artifact versions (required for Gradle)

**Do not use `LATEST` in Gradle init scripts** — Gradle dependency resolution does not treat `LATEST` as a Maven version alias. It will fail with `Could not find org.openrewrite.recipe:<artifact>:LATEST`.

| Build tool | Version syntax |
|------------|----------------|
| Maven (`-Drewrite.recipeArtifactCoordinates=`) | `LATEST` works |
| Gradle init script (`rewrite("...")`) | **Use BOM or pin a real version** |

**Recommended for Gradle** — BOM + module (OpenRewrite's preferred approach):

```groovy
dependencies {
    rewrite(platform("org.openrewrite.recipe:rewrite-recipe-bom:latest.release"))
    rewrite("org.openrewrite.recipe:rewrite-jackson")  // version from BOM
}
```

**Alternative** — pin from Maven metadata:

```bash
curl -s "https://repo1.maven.org/maven2/org/openrewrite/recipe/<ARTIFACT>/maven-metadata.xml" \
  | grep -o '<release>[^<]*</release>' | sed 's/[<>/a-z]//g'
```

> **Recipe vs artifact version:** Newer recipes may only exist in newer artifact releases. Example: `UpgradeJackson_2_3` is in `rewrite-jackson` **1.x** but absent from **0.20.0**. See `references/recipe-catalog.md` → **Minimum artifact versions for newer recipes**.

**Verify the recipe is on the classpath before running:**

```bash
./gradlew rewriteDiscover --init-script rewrite-init.gradle --no-daemon 2>&1 | grep -i <keyword>
```

---

## Maven Execution

### No parameters, core library recipe

```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.activeRecipes=<RECIPE_ID>
```

### No parameters, external library recipe

```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.recipeArtifactCoordinates=<GROUP>:<ARTIFACT>:<VERSION> \
  -Drewrite.activeRecipes=<RECIPE_ID>
```

### Parameterized recipe (any library)

Parameterized recipes **require a `rewrite.yml` wrapper** — parameters cannot be passed inline with Maven for most recipes (the inline `-Drewrite.options=` approach is limited to single-recipe runs and fragile).

**1. Generate `rewrite.yml`** in the project root (Claude writes this file):

```yaml
---
type: specs.openrewrite.org/v1beta/recipe
name: com.yourorg.<DescriptiveName>
displayName: <Human readable name>
recipeList:
  - <RECIPE_ID>:
      <paramKey1>: <paramValue1>
      <paramKey2>: <paramValue2>
```

**2. Run with the wrapper recipe name**:

```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:run \
  -Drewrite.recipeArtifactCoordinates=<GROUP>:<ARTIFACT>:<VERSION> \
  -Drewrite.activeRecipes=com.yourorg.<DescriptiveName>
```

> Omit `-Drewrite.recipeArtifactCoordinates` if the recipe lives in the core library.

### Maven dry-run (preview without applying)

```bash
mvn -U org.openrewrite.maven:rewrite-maven-plugin:dryRun \
  -Drewrite.activeRecipes=<RECIPE_ID>
```

---

## Gradle Execution

Gradle uses an **init script** — a temporary file placed alongside the project (or anywhere on disk). The init script does **not** add OpenRewrite to the project's build permanently, but **recipes may still modify `build.gradle` / `pom.xml`** as part of their changes (e.g. dependency upgrades).

> ⚠️ If the project's `build.gradle` already has a `rewrite { }` block, the init script approach will conflict. Inform the user and fall back to the standard plugin configuration instead.

### Step A — Generate the init script

Claude generates the init script. File name: `rewrite-init.gradle` (Groovy DSL) or `rewrite-init.gradle.kts` (Kotlin DSL). Detect DSL from the project's existing build file extension.

**Groovy (`rewrite-init.gradle`)**:

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
        // Recommended: BOM + module (no version on module)
        rewrite(platform("org.openrewrite.recipe:rewrite-recipe-bom:latest.release"))
        rewrite("org.openrewrite.recipe:<ARTIFACT>")  // e.g. rewrite-jackson

        // Alternative: pin version directly (never use literal "LATEST")
        // rewrite("org.openrewrite.recipe:<ARTIFACT>:<VERSION>")
    }

    afterEvaluate {
        if (repositories.isEmpty()) {
            repositories {
                mavenCentral()
            }
        }

        // OPTIONAL — see ## Troubleshooting → "Gradle compile chain blocks rewriteRun"
        // There is NO skipCompile flag; this is the init-script workaround.
        tasks.matching { it.name == "rewriteRun" || it.name == "rewriteDryRun" }.configureEach { rewriteTask ->
            rewriteTask.setDependsOn([])
        }
    }
}
```

**Kotlin (`rewrite-init.gradle.kts`)**:

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
    dependencies {
        add("rewrite", platform("org.openrewrite.recipe:rewrite-recipe-bom:latest.release"))
        add("rewrite", "org.openrewrite.recipe:<ARTIFACT>")
    }

    afterEvaluate {
        if (repositories.isEmpty()) {
            repositories {
                mavenCentral()
            }
        }

        // OPTIONAL — see ## Troubleshooting → "Gradle compile chain blocks rewriteRun"
        // There is NO skipCompile flag; this is the init-script workaround.
        tasks.matching { it.name == "rewriteRun" || it.name == "rewriteDryRun" }.configureEach { rewriteTask ->
            rewriteTask.setDependsOn(emptyList())
        }
    }
}
```

> If the recipe is a **core library recipe** (no external artifact needed), remove the BOM/module lines.
> Never use literal `LATEST` as a Gradle version string — use BOM or a pinned release.

### Step B — Run the recipe

**No parameters**:

```bash
./gradlew rewriteRun \
  --init-script rewrite-init.gradle \
  -Drewrite.activeRecipe=<RECIPE_ID>
```

**Parameterized recipe** — create `rewrite.yml` first (same format as Maven above), then:

```bash
./gradlew rewriteRun \
  --init-script rewrite-init.gradle \
  -Drewrite.activeRecipe=com.yourorg.<DescriptiveName>
```

### Gradle dry-run (preview without applying)

```bash
./gradlew rewriteDryRun \
  --init-script rewrite-init.gradle \
  -Drewrite.activeRecipe=<RECIPE_ID>
```

Outputs a patch file at `build/reports/rewrite/rewrite.patch`. The user can inspect it with `git diff . build/reports/rewrite/rewrite.patch`.

### Memory tuning (large projects)

Large projects may require more heap. Add to the Gradle command:

```bash
-Dorg.gradle.jvmargs=-Xmx4G
```

---

## Parameterized Recipe: `rewrite.yml` Format

```yaml
---
type: specs.openrewrite.org/v1beta/recipe
name: com.yourorg.<DescriptiveName>
displayName: <Short label>
recipeList:
  - <RECIPE_ID>:
      <param1>: <value1>
      <param2>: <value2>
```

**Rules:**
- `name` must be unique — use `com.yourorg.` prefix + a descriptive suffix.
- Indentation under `<RECIPE_ID>:` uses **2 spaces**, not tabs.
- String values with special characters should be quoted.
- Place the file in the **project root** (same directory as `pom.xml` or `build.gradle`).
- Clean it up after the run if you don't want it committed.

---

## Cleanup After Run

After the recipe runs:

1. Review changes with `git diff`.
2. Delete `rewrite.yml` if it was only a temporary wrapper for parameterized execution.
3. Delete `rewrite-init.gradle` / `rewrite-init.gradle.kts` (Gradle only).
4. Build and test the project to confirm correctness.

> **Note:** The init-script approach does not add OpenRewrite to the project's build files, but **many recipes intentionally modify `build.gradle` / `pom.xml`** (e.g. `UpgradeJackson_2_3_Dependencies` updates dependency versions). That is expected recipe output, not plugin configuration leakage.

---

## Troubleshooting

Problems encountered in real runs — check these before giving up.

### Gradle: `Could not find ... :LATEST`

Gradle does not resolve `LATEST`. Pin the artifact version via Maven metadata (see **Resolve recipe artifact versions** above).

### Gradle: `Recipe(s) not found: <RECIPE_ID>`

1. **Artifact too old** — bump the recipe library version (e.g. `rewrite-jackson:0.20.0` → `1.24.0`).
2. **Recipe not on classpath** — confirm with `rewriteDiscover`.
3. **Wrong flag** — Gradle uses `-Drewrite.activeRecipe` (singular); Maven uses `-Drewrite.activeRecipes` (plural).

### Gradle compile chain blocks `rewriteRun`

**There is no `skipCompile` flag.** OpenRewrite's Gradle plugin does not expose `skipCompile`, `rewrite.skipCompile`, or `-Drewrite.skipCompile` — confirmed in the [Gradle plugin configuration](https://docs.openrewrite.org/reference/gradle-plugin-configuration) and `RewriteExtension` source. Do not tell users to pass a skipCompile flag; it does not exist.

Instead, the plugin **intentionally** wires `rewriteRun` / `rewriteDryRun` to depend on every Java source set's `compileJava` task (see `RewritePlugin.java`). That pulls in project-specific compile dependencies — including OpenAPI/codegen tasks hooked via `tasks.withType(JavaCompile) { dependsOn('apiGen') }`.

On projects where compilation triggers **code generation**, the build can fail **before OpenRewrite runs**.

**Symptom:** `./gradlew rewriteRun` executes `generate*` / `apiGen` tasks and fails with errors unrelated to OpenRewrite (e.g. Jackson classpath mismatch in a codegen plugin).

**Why partial workarounds fail:** Removing only the `compileJava` dependency is not enough — `compileTestJava` and other compile tasks still pull in the codegen chain.

**Fix (init-script workaround — not an official flag):** In the init script's `afterEvaluate`, clear all task dependencies on `rewriteRun` / `rewriteDryRun`:

```groovy
tasks.matching { it.name == "rewriteRun" || it.name == "rewriteDryRun" }.configureEach { rewriteTask ->
    rewriteTask.setDependsOn([])
}
```

OpenRewrite parses source files directly and resolves types from the dependency classpath — it does not need a successful Gradle compile. After the recipe finishes, run a full `./gradlew build` separately to surface any remaining compile/codegen issues.

### Codegen still broken after rewrite

OpenRewrite migrates **source code and build dependency declarations**. It does not upgrade **Gradle plugin classpaths** used at build time. If `generate*ApiClientCode` fails with Jackson 2/3 API errors, the OpenAPI/codegen plugin itself may need a version bump — that is separate from the rewrite.

### Mixed diffs from pre-existing changes

If the working tree already had uncommitted migration work, `git diff` will mix OpenRewrite output with prior edits. **Always `git stash` or commit before running** so the rewrite diff is reviewable.

### Large projects run out of memory

Add `-Dorg.gradle.jvmargs=-Xmx4G` (Gradle) or `MAVEN_OPTS=-Xmx4g` (Maven).

---

## Common Recipes & Their Coordinates

See `references/recipe-catalog.md` for a curated list of frequently used recipes with their artifact coordinates and parameter schemas.

---

## Full Worked Examples

See `references/examples.md` for complete end-to-end examples including:
- Java version migration (Maven + Gradle, parameterized)
- Spring Boot upgrade
- Package rename
- JUnit 4 → 5 migration
- Jackson 2 → 3 migration (Gradle codegen workaround)
# polyglot fixture

One tree that exercises spec 026.1 (skeleton, CLI, discovery, modules):

- `.` — npm module root (`package.json`, `tsconfig.json`) with a source file and a `*.spec.ts`
  test, so the `test: true` flag has something to point at.
- `backend/` — Maven module root (`pom.xml`) with a Java source and a Spring
  `application.yml`, which discovery classifies as `manifest:spring.config`.
- `tools/` — Gradle Kotlin DSL module root (`build.gradle.kts`) with a Java source.

No build outputs are committed; `build/`, `.gradle/`, `node_modules/` and `.migration/` are
ignored here so a stray IDE sync or a local scan cannot change the fixture between runs.

# Spring Boot 4.0.0 → 4.1.0 — Filtered Migration Guide

- **Framework:** `spring-boot`
- **Range:** `4.0.0` → `4.1.0-RC1`
- **Filtered:** 2026-06-05

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-46917 | Undertow support dropped | Undertow has been removed because it is not compatible with Servlet 6.1. Applications using Undertow must migrate to Tomcat or Jetty before upgrading to Spring Boot 4.x. |
| 2 | GH-47017 | Jersey support dropped (then restored) | Jersey was dropped in M3 for lack of JAX-RS 4 support, then restored in RC2 once Jersey added it. Verify your Jersey version supports JAX-RS 4 / Jakarta EE 11 before upgrading. |
| 3 | GH-45535 | Jackson 3 required; Jackson 2 deprecated | Spring Boot 4 requires Jackson 3 as the primary JSON library. Jackson 2 support ships in a deprecated `spring-boot-jackson2` compatibility module. If your code depends on Jackson 2 types, add `spring-boot-jackson2` as a transitional dependency and plan to migrate to Jackson 3 before Boot 4.3. |
| 4 | GH-47625, GH-47471 | Jackson annotation and class renames | Jackson-specific annotations and classes have been renamed: `JsonMapper` → `JacksonJsonMapper`, `SharedObjectMapper` → `SharedJsonMapper`, `Json*` annotations → `Jackson*`. Update all direct usages in application code. |
| 5 | GH-47327, GH-47328 | `spring.jackson.*` property renames | `spring.jackson.datetime.<feature>` moved to `spring.jackson.datatype.datetime.<feature>`; JsonMapper-specific properties renamed to be JSON-specific. Review and update all `spring.jackson.*` configuration properties. |
| 6 | GH-47178, GH-47101 | Kotlin Serialization auto-configuration introduced | Kotlin Serialization is now auto-configured; when both Kotlin Serialization and other JSON libraries are on the classpath, Boot 4 may choose Kotlin Serialization more aggressively. Ensure JSON library precedence is explicitly configured if mixed serializers are used. |
| 7 | GH-47666 | Embedded jar launch scripts removed | Support for embedded jar launch scripts has been removed. Remove any scripts embedded in your jar and use external launch mechanisms. |
| 8 | GH-45714 | `spring-boot-loader-classic` removed | The classic loader is gone. Applications relying on it must switch to the current spring-boot-loader. |
| 9 | GH-47378 | SQL and Reactor starters removed | `spring-boot-starter-sql` and `spring-boot-starter-reactor` have been removed (they were only transitive). Remove direct dependencies on them; declare explicit dependencies on the required modules instead. |
| 10 | GH-47662, GH-47661 | Spring Session MongoDB and Hazelcast support removed | Auto-configuration for Spring Session with MongoDB and Hazelcast has been removed. Applications using these session stores must implement their own configuration. |
| 11 | GH-47685 | REST Docs REST Assured integration removed | REST Assured integration removed until REST Assured supports Groovy 5. Remove test dependencies on `spring-restdocs-restassured` for now. |
| 12 | GH-47707 | Spring Pulsar Reactive support removed | Support for Spring Pulsar Reactive has been removed. Reactive Pulsar applications must use the non-reactive API or provide their own configuration. |
| 13 | GH-32883 | Auto-configurations made final with no public members | All auto-configuration classes are now `final` and have no public members. Any code that extends, overrides, or directly references internal members of auto-configuration classes will break at compile or runtime. Refactor to use supported extension points (`@Bean` overrides, customizers, etc.). |
| 14 | GH-47043 | `*DataProperties` renamed to `Data*Properties` | Data properties classes (e.g., `MongoDataProperties`) have been renamed to follow the `Data*Properties` pattern. Update any code that references these classes by name. |
| 15 | GH-47603 | `spring-boot-tx` module renamed | The `spring-boot-tx` module has been renamed to `spring-boot-transaction`. Update your dependency declarations. |
| 16 | GH-42948 | AOP starter renamed | `spring-boot-starter-aop` has been renamed to `spring-boot-starter-aspectj`. Update your build files. |
| 17 | GH-47050 | MongoDB properties renamed to use `mongodb` | All MongoDB-related properties now consistently use `spring.mongodb.*` (not `spring.mongo.*`). Audit and rename properties in all configuration files. |
| 18 | GH-47052 | `spring.mongodb.uuid-representation` renamed | Property `spring.mongodb.uuid-representation` has been renamed. Check the Spring Boot 4.0 migration guide for the new key. |
| 19 | GH-47044 | GridFs removed from `MongoConnectionDetails` | `GridFs` has been removed from `MongoConnectionDetails`. If you implement `MongoConnectionDetails`, remove any GridFS-related overrides. |
| 20 | GH-47333 | Spring Session properties renamed | Spring Session properties that depended on Spring Data have been renamed. Update `spring.session.*` properties per the migration guide. |
| 21 | GH-48201 | Error properties moved out of `server.*` | Error configuration properties are no longer under `server.error.*`; they have been moved to a general web namespace. Update all `server.error.*` references in `application.properties`/`application.yaml`. |
| 22 | GH-48175 | Tomcat and Jetty runtime modules converted to starters | `spring-boot-tomcat` and `spring-boot-jetty` are now starters. Update dependency declarations accordingly. |
| 23 | GH-48677 | `jetty-ee11-servlets` removed from `spring-boot-jetty` | The `org.eclipse.jetty.ee11:jetty-ee11-servlets` transitive dependency has been removed. If your app uses classes from it, add an explicit dependency. |
| 24 | GH-46309 | Spring Retry dependency management removed | Spring Boot no longer manages Spring Retry; `spring-core`'s built-in retry support is used instead. If you use Spring Retry directly, declare your own version in your build. |
| 25 | GH-47174 | Spring Authorization Server moved into Spring Security | Explicit dependency management for Spring Authorization Server has been removed; it is now part of Spring Security's dependency management. Remove any explicit Spring Authorization Server BOM or version overrides. |
| 26 | GH-48568 | Layertools jar mode removed | The deprecated `layertools` jar mode has been removed. Use the supported `extract` mode instead in your Docker/build pipeline. |
| 27 | GH-48489 | Deprecated Logback properties removed | Support for deprecated Logback configuration properties has been removed. Migrate to the current property names documented in Spring Boot 4.0 release notes. |

---

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-50188, GH-50190 | Default security misconfigured without `spring-boot-health` | When `spring-boot-actuator-autoconfigure` is present but `spring-boot-health` is not, the default security configuration is incorrect. Ensure `spring-boot-health` is on the classpath, or explicitly configure security rules. Fixed in 4.0.6 / 4.1.0-RC1. |
| 2 | GH-49854, GH-49988 | `PathPatternRequestMatcher.Builder` missing in `WebMvcTest` | Spring Security's `PathPatternRequestMatcher.Builder` is not auto-configured in `@WebMvcTest` with `spring-boot-security-test`. Add the missing bean configuration in tests or upgrade to the patched version. |
| 3 | GH-49507, GH-49511 | Forwarded headers security documentation | Forwarded headers in cloud deployments require explicit security configuration. Review and configure `server.forward-headers-strategy` per the security guidance added in 4.0.4/4.1.0-M3. |
| 4 | GH-49367, GH-49379 | Auth server config overridden by `Customizer<HttpSecurity>` | Auto-configuration was overriding authorization server configuration applied by `Customizer<HttpSecurity>` beans. This has been fixed; verify your authorization server `HttpSecurity` customizers still apply correctly after upgrade. |
| 5 | GH-48388 | Security matchers fail with `NoClassDefFoundError` in WAR | `WebServerNamespace` resolution can fail in traditional WAR deployments. Fixed in 4.0.1; ensure you apply that patch before deploying as WAR. |
| 6 | GH-50145 | gRPC CSRF property inverted | `GrpcDisableCsrfHttpConfigurer` was reading the inverse of `spring.grpc.server.security.csrf.enabled`. If you set this property, the CSRF disable logic was reversed. Fixed in 4.1.0-RC1; verify your gRPC security configuration after upgrade. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-47381 | Neo4j Java Driver 6.0.0 required | Spring Boot 4 requires Neo4j Java Driver 6.0.0+. Update your Neo4j driver dependency and review any API changes in the driver's changelog. |
| 2 | GH-43574 | Gradle minimum version raised to 8.14 | The minimum supported Gradle version is now 8.14. Projects on older Gradle versions must upgrade their build tooling. |
| 3 | GH-47433 | GraalVM baseline raised to 25 | Native image builds now require GraalVM 25+. Update your GraalVM installation if using native compilation. |
| 4 | GH-46061 | Elasticsearch auto-configures new `Rest5Client` | Spring Boot 4 auto-configures `Rest5Client` (Elasticsearch 9.x) instead of the legacy `RestClient`. Applications using the legacy client must update to the new API or add explicit configuration. |
| 5 | GH-48619 | jOOQ 3.20 with Java 21 requirement | jOOQ has been upgraded to 3.20 which requires Java 21. Update jOOQ usage and ensure your runtime is Java 21+. |
| 6 | GH-48076, GH-48262 | Kotlinx Serialization starters renamed | `spring-boot-starter-kotlin-serialization` has been renamed to `spring-boot-starter-kotlinx-serialization-json`. Update Kotlin Serialization starter dependency names in your build. |
| 7 | GH-49620 | `spring-boot-amqp` renamed to `spring-boot-rabbitmq` | The AMQP module has been renamed. Update dependency coordinates from `spring-boot-amqp` to `spring-boot-rabbitmq`. |
| 8 | GH-47232 | Foundational packages restructured | Core packages have been restructured to remove dependency on `org.springframework.boot`. Any code importing internal package paths may break. Review import statements against the new package layout. |
| 9 | GH-45328 | `spring-boot-persistence` module created | General persistence code has moved to a new `spring-boot-persistence` module. If you depend on persistence utilities from other modules, add `spring-boot-persistence` to your dependencies. |
| 10 | GH-47398 | HTTP client configuration properties rationalized | HTTP client configuration properties have been reorganized. Review `spring.http.client.*` properties and update as per the 4.0 migration guide. |
| 11 | GH-46233 | `spring-boot-autoconfigure-classic` module added | Classic auto-configuration has been split into a separate module. If you use Spring Boot 3.x-style auto-configuration patterns, check whether you need this dependency. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-48055 | `WebSecurityCustomizer` beans excluded by `WebMvcTest` | `WebSecurityCustomizer` beans are no longer loaded in `@WebMvcTest`. Add them explicitly to your slice test configuration if needed. |
| 2 | GH-47959, GH-47958, GH-47957, GH-47954 | Tracing/logging export properties renamed | `management.zipkin.tracing` → `management.tracing.export.zipkin`; `management.tracing.enabled` → `management.tracing.export.enabled`; `management.logging.export.*` properties renamed. Audit and update all observability-related properties. |
| 3 | GH-47029 | `ConditionalOnEnabledTracing` renamed | `ConditionalOnEnabledTracing` has been renamed to `ConditionalOnEnabledTracingExport`. Update any references in custom auto-configuration code. |
| 4 | GH-76 (spring.dao) | `spring.dao.exceptiontranslation.enabled` renamed | Property renamed to `spring.persistence.exceptiontranslation.enabled`. Update in all configuration files. |
| 5 | GH-47375 | SSL bundle config in `RedisConnectionDetails` rationalized | SSL bundle configuration in `RedisConnectionDetails` has changed. Review and update Redis SSL configuration if using SSL bundles. |
| 6 | GH-49047 | Spring gRPC server/client security support added | gRPC security configuration is now managed by Spring Boot. Review and migrate any custom gRPC security setup to the new auto-configuration. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-46925 | Micrometer module names include `micrometer` | Micrometer, observation, and tracing module names and packages have been renamed to include "micrometer". Update any explicit module references. |
| 2 | GH-22825 | Readiness/liveness probes enabled by default | Kubernetes readiness and liveness probe endpoints are now enabled by default. Review your Kubernetes deployment manifests and ensure probe configuration is correct. |
| 3 | GH-47387 | LiveReload disabled by default | LiveReload server is now disabled by default in DevTools. Set `spring.devtools.livereload.enabled=true` to re-enable. |
| 4 | GH-46592 | `logging.console.enabled` property introduced | Console logging can now be disabled via `logging.console.enabled=false`. No action required unless you relied on always-on console logging. |
| 5 | GH-73, GH-73 | `management.tracing.enabled` renamed | Property `management.tracing.enabled` is now `management.tracing.export.enabled`. Update configuration. |
| 6 | GH-46846 | Logback charset harmonized for console and file | Console and file logging charsets are now aligned. If you relied on different charsets between console and file appenders, review your Logback configuration. |
| 7 | GH-47220 | `SanitizableData.key` non-nullable | Passing `null` as a key to `SanitizableData` now throws an exception. Fix any code that passes null keys. |
| 8 | GH-46404 | `RestClient` uses virtual threads when enabled | `RestClient` backed by JDK HttpClient now uses the virtual thread executor when `spring.threads.virtual.enabled=true`. Test for correctness in high-concurrency scenarios. |
| 9 | GH-47470 | Jackson 3 compatibility property for Jackson 2 defaults | Set `spring.jackson.use-jackson2-defaults=true` to configure Jackson 3 to behave like Jackson 2. Useful for incremental migration; review all Jackson feature flags. |
| 10 | GH-46975 | Lettuce uses `MicrometerTracing` when available | When `micrometer-tracing` is on the classpath, Lettuce uses `MicrometerTracing` instead of `MicrometerCommandLatencyRecorder`. Verify Redis tracing output still meets expectations. |
| 11 | GH-47318 | Maven plugin excludes optional dependencies by default | The Spring Boot Maven plugin now excludes optional dependencies from the uber jar by default. Verify your jar contains all required runtime dependencies. |
| 12 | GH-49311, GH-49312 | `server.tomcat.max-part-count` default increased to 50 | The default for `server.tomcat.max-part-count` has increased from 10 to 50 to align with Tomcat and Spring Boot 3.x. No action required unless you had explicit tuning. |
| 13 | GH-47953 | `spring-boot-micrometer-tracing` split into Brave/OTel modules | The tracing module has been split into Brave-specific and OpenTelemetry-specific modules. Update tracing starter dependencies to the appropriate specific module. |
| 14 | GH-49043, GH-49044, GH-49045 | Spring gRPC client and server support added | Full gRPC client/server auto-configuration is new in 4.1. If you had a custom gRPC setup, review for conflicts with the new auto-configuration. |
| 15 | GH-48546 | Session cookie `SameSite` defaults to `Lax` | `DefaultCookieSerializer` now defaults `SameSite` to `Lax` (was null). Verify session cookie behavior in browser-based applications. |
| 16 | GH-49731, GH-49732 | External `application.properties` overrides ignored | A bug where properties in external `application.properties`/`application.yaml` were ignored has been fixed. Verify property loading order in your deployment. |
| 17 | GH-48880 | Missing `TransactionAutoConfiguration` with Kafka | `TransactionAutoConfiguration` was missing when using `spring-boot-starter-kafka`. Fixed in 4.0.2 / 4.1.0-M1; ensure Kafka transaction support is correctly configured after upgrade. |
| 18 | GH-48830, GH-48861 | `SessionAutoConfiguration` cookie serializer fix | `DefaultCookieSerializer` was created with a null `SameSite` value. Fixed; verify cookie configuration if using Spring Session. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-47256 | JUnit 4 integration deprecated | JUnit 4 support is deprecated. Migrate tests to JUnit 5. |
| 2 | GH-84, GH-86 | Jackson 2 support deprecated | Jackson 2 ships in deprecated `spring-boot-jackson2` module. Plan migration to Jackson 3 before Boot 4.3 when it will be removed. |
| 3 | GH-86, GH-87 | `EnvironmentPostProcessor` interface moved | `org.springframework.boot.env.EnvironmentPostProcessor` has been replaced by `org.springframework.boot.EnvironmentPostProcessor`. The old interface remains in deprecated form. Update imports to the new package. |
| 4 | GH-84 | `OperationMethod` constructor deprecated | The two-argument `OperationMethod(Method, OperationType)` constructor is deprecated; use the three-argument form with `Predicate<Parameter> optionalParameters`. |
| 5 | GH-48567 | Derby support deprecated | Apache Derby has been retired; Spring Boot's Derby support is now deprecated. Migrate to another supported database. |
| 6 | GH-48971 | LiveReload support deprecated for removal | LiveReload DevTools support is deprecated and will be removed in a future release. Remove reliance on LiveReload. |
| 7 | GH-49453, GH-49557 | OpenTelemetry `ZipkinSpanExporter` deprecated | OTel's `ZipkinSpanExporter` is deprecated and will be removed in Spring Boot 4.2. Migrate Zipkin tracing export to `management.tracing.export.zipkin.*` configuration. |
| 8 | GH-48350 | `RootUriTemplateHandler` deprecated | `RootUriTemplateHandler` is deprecated in favor of `DefaultUriBuilderFactory`. Update usages in tests and production code. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-46519 | API Versioning auto-configuration | Spring Framework's API Versioning is now auto-configured via `spring.web.apiversion.*` properties. Leverage this for versioned REST APIs without manual configuration. |
| 2 | GH-46782 | `@HttpServiceClient` scanning auto-configuration | HTTP Service clients annotated with `@HttpServiceClient` are now automatically scanned and configured. Simplifies declarative HTTP client setup. |
| 3 | GH-49043–49048 | Full Spring gRPC support (4.1) | Spring Boot 4.1 introduces auto-configuration for Spring gRPC server, client, health check, testing, and security. Use new starters `spring-boot-starter-grpc-server` / `spring-boot-starter-grpc-client`. |
| 4 | GH-48315 | SSL (LDAPS) support for embedded LDAP | Embedded LDAP server now supports SSL. Configure LDAPS for secure embedded LDAP in test or development scenarios. |
| 5 | GH-48513 | Spock framework support reinstated | Spock support returns now that it supports Groovy 5. Add the Spock test framework dependency to use it with Spring Boot 4.1. |
| 6 | GH-48033 | `ContextPropagatingTaskDecorator` auto-configuration | A property can now automatically register a `ContextPropagatingTaskDecorator` bean for trace context propagation across thread boundaries. |
| 7 | GH-49043, GH-49280 | Reusable default `TaskScheduler` configuration | A reusable default `TaskScheduler` configuration is provided. Review if your custom scheduler configuration conflicts with the new default. |
| 8 | GH-48599 | OTLP SSL bundle support | SSL bundles are now supported for OTLP metrics, traces, and logging export. Use `management.otlp.*.ssl-bundle` to configure mTLS for OTLP exporters. |
| 9 | GH-48957 | OTLP compression mode property | OTLP compression can now be configured via property. Set `management.otlp.*.compression` to `gzip` or `none`. |
| 10 | GH-15480 | `LazyConnectionDataSourceProxy` auto-configuration | Spring Boot 4.1 supports auto-configuring `LazyConnectionDataSourceProxy` for deferred DataSource connection acquisition. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 27 | Must fix before migrating. |
| 🟠 **Mandatory** | 23 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 26 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 10 | Optional but recommended to leverage. |

---

## 🚨 Most Critical Items for Migration

- **Jackson 3 is required; Jackson 2 is deprecated (GH-45535, GH-47625).** This is the single biggest migration effort: all Jackson 2 types, annotations, and property keys have changed. Add `spring-boot-jackson2` as a temporary compatibility shim, set `spring.jackson.use-jackson2-defaults=true` to reduce behavioral differences, then incrementally migrate code to Jackson 3 before Spring Boot 4.3 removes Jackson 2 entirely.

- **Undertow is removed (GH-46917).** Any application currently using Undertow as its embedded server cannot upgrade to Spring Boot 4 without switching to Tomcat or Jetty first. This must be done before starting the Boot 4 migration.

- **Auto-configurations are final with no public members (GH-32883).** Any application code that extends auto-configuration classes, overrides their methods, or accesses their internals will fail to compile or throw runtime errors. Audit all `@Configuration` or `@Import` usages that reference Spring Boot auto-configuration classes directly.

- **Widespread property renames across MongoDB, Spring Session, Jackson, and tracing (GH-47050, GH-47052, GH-47333, GH-47327, GH-47958, GH-47959).** A broad sweep of configuration property keys has changed in 4.0. Run a full search of your `application.properties`/`application.yaml` files against the [Spring Boot 4.0 migration guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) before deployment.

- **Default security misconfigured without `spring-boot-health` (GH-50188, GH-50190).** If your application uses Actuator without the `spring-boot-health` module, the security auto-configuration is incorrect and may expose endpoints unintentionally. Explicitly declare `spring-boot-health` as a dependency or configure security rules manually.

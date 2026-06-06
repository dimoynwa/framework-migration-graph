# Spring Boot 3.5.0 → 4.0.0 — Migration Filter Report

- **Framework:** `spring-boot`
- **Range:** `3.5.0` → `4.0.0`
- **Filtered:** 2026-06-05

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-45600 | Deprecated APIs removed in 4.0 | All APIs deprecated for removal in 3.x have been deleted. Audit your codebase for any usage of deprecated Spring Boot APIs before upgrading; compilation will fail at any call site. |
| 2 | GH-32883 | Auto-configurations made final; public members removed | Auto-configuration classes are now `final` and all public members (except constants) have been removed. Any code that subclasses, overrides, or imports members from auto-configuration classes will fail to compile. Replace with proper extension points (customizers, condition beans, etc.). |
| 3 | GH-45535 | Jackson 3 now required; Jackson 2 deprecated | Spring Boot 4.0 requires Jackson 3. Jackson 2 is still available via the optional `spring-boot-jackson2` compatibility module but ships in deprecated form. Update to Jackson 3 APIs, or add `spring-boot-jackson2` as a transitional dependency and plan removal. |
| 4 | GH-47017 | Jersey support dropped | Spring Boot 4.0 drops auto-configuration for Jersey (pending Jakarta EE 11 / JAX-RS 4 support). Applications using Jersey must migrate to Spring MVC or Spring WebFlux, or wait for Jersey's JAX-RS 4 release and re-add configuration manually. |
| 5 | GH-47662, GH-47661 | Spring Session MongoDB and Hazelcast removed | Auto-configuration support for Spring Session backed by MongoDB and Hazelcast has been removed. Switch to a supported session store (JDBC, Redis, or the new in-memory batch infrastructure). |
| 6 | GH-45714 | spring-boot-loader-classic support dropped | The `spring-boot-loader-classic` module is removed. Applications relying on the classic launcher must migrate to the current `spring-boot-loader`. |
| 7 | GH-47666 | Embedded jar launch scripts removed | Support for fully executable jar via embedded launch scripts has been removed. Use the OS-specific packaging plugins (RPM, DEB, or Docker) to create executable artifacts. |
| 8 | GH-46309 | Spring Retry dependency management removed | Dependency management for Spring Retry has been dropped in favour of Spring Framework's built-in retry support. If you rely on Spring Retry, declare it explicitly in your build. |
| 9 | GH-47174 | Spring Authorization Server removed from BOM | Explicit dependency management for Spring Authorization Server is removed because it is now included in the Spring Security BOM. Remove any explicit version overrides; the Spring Security-managed version will be used automatically. |
| 10 | GH-47378 | SQL and Reactor starters removed | `spring-boot-starter-sql` and `spring-boot-starter-reactor` have been removed as they were only pulled in transitively. Add the specific library starters you need directly. |
| 11 | GH-45713 | Wavefront support dropped | Auto-configuration for VMware Tanzu Observability (Wavefront) has been removed. Migrate to the OTLP exporter or another supported metrics backend. |
| 12 | GH-47685 | REST Docs REST Assured integration removed | Integration for REST Docs' REST Assured support is removed until REST Assured supports Groovy 5. If you rely on this, remain on Spring Boot 3.x or configure the integration manually. |
| 13 | GH-47232 | Foundational packages restructured | Core package layout has been restructured. If you import from `org.springframework.boot` packages other than the public API surfaces, verify your imports compile after the upgrade. |
| 14 | GH-42948 | spring-boot-starter-aop renamed to spring-boot-starter-aspectj | The `spring-boot-starter-aop` artifact has been renamed to `spring-boot-starter-aspectj`. Update your build files to use the new artifact ID. |
| 15 | GH-47603 | spring-boot-tx renamed to spring-boot-transaction | The `spring-boot-tx` module is renamed to `spring-boot-transaction`. Update any direct module dependencies. |
| 16 | GH-47050, GH-34954 | MongoDB config property prefixes changed | All MongoDB-related properties that previously used `spring.data.mongodb.*` or `spring.mongo.*` where the setting does not require Spring Data MongoDB are now under `spring.mongodb.*`. Rename all `spring.data.mongodb.*` and `spring.mongo.*` properties that map to driver/connection level settings to `spring.mongodb.*`. |
| 17 | GH-47103 | Spring Pulsar Reactive support removed | Auto-configuration for Spring Pulsar Reactive has been removed. Switch to the non-reactive Pulsar integration or configure the reactive client manually. |
| 18 | GH-47056 | spring-boot-starter-aop renamed | Rename `spring-boot-starter-aop` to `spring-boot-starter-aspectj` in all build descriptors. |

## 🟠 Mandatory Migrations — Security & CVE Fixes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-45848 | Cloud Foundry actuator CSRF protection | Write and delete operations on the Cloud Foundry actuator endpoint no longer work when Spring Security's CSRF protection is active. Review your CF actuator security configuration and explicitly allow the required operations or configure a CSRF token strategy. |
| 2 | GH-46133, GH-46134, GH-46135, GH-46136, GH-46137 | Security modules are now separate; dependency updates required | Spring Boot 4.0 splits security into discrete modules (`spring-boot-security`, `spring-boot-security-oauth2-client`, `spring-boot-security-oauth2-resource-server`, `spring-boot-security-oauth2-authorization-server`, `spring-boot-security-saml2`). If your BOM or starter resolved these transitively, add the relevant modules explicitly to avoid `ClassNotFoundException` at runtime. |

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-46216 | Spring Batch 6 migration | Spring Boot 4.0 migrates to Spring Batch 6, which includes API changes. Review the Spring Batch 6 migration guide; batch job configurations and `JobRepository` definitions may need to be updated. |
| 2 | GH-47381 | Neo4j Java Driver 6.0 required | The Neo4j support now requires Neo4j Java Driver 6.0.0. Review the Neo4j Driver 6.0 migration guide for API-level changes. |
| 3 | GH-46061 | Elasticsearch Rest5Client replaces RestClient | Auto-configuration now targets Elasticsearch's new `Rest5Client` instead of the legacy `RestClient`. Code that injects `RestClient` or `RestHighLevelClient` must be updated to use `Rest5Client` (or `ElasticsearchClient`). |
| 4 | GH-43574, GH-43573 | Minimum Gradle raised to 8.14; Gradle 9 supported | Spring Boot 4.0's build tooling requires Gradle 8.14 or later. Gradle 9 is now also supported. Upgrade your Gradle wrapper version before upgrading. |
| 5 | GH-47433 | GraalVM baseline raised to version 25 | Building Spring Boot native images now requires GraalVM 25. Update your GraalVM installation or native-image CI configuration. |
| 6 | GH-47250 | CycloneDX Gradle Plugin minimum 3.0.0 | If you generate SBOMs with the CycloneDX Gradle plugin, the minimum required version is now 3.0.0. Update the plugin version. |
| 7 | GH-47622 | spring-boot-parent module no longer published | `spring-boot-parent` is no longer published. If you used it for dependency management of internal/test dependencies, replace it with your own dependency management block. |

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-45848 | OAuth2 client web security auto-configuration split | `OAuth2ClientWebSecurityAutoConfiguration` now exclusively handles servlet OAuth2 client web security; `ReactiveOAuth2ClientWebSecurityAutoConfiguration` handles the reactive stack. Applications that relied on the previous merged behaviour must verify that the correct auto-configuration is active for their application type. |
| 2 | GH-48055 | WebSecurityCustomizer beans excluded in WebMvcTest | `WebSecurityCustomizer` beans are now excluded during `@WebMvcTest`. If your test relied on a `WebSecurityCustomizer` to relax security for slice tests, you need to include the customizer explicitly via `@Import` or move security setup into test-specific configuration. |
| 3 | GH-47813 | spring-boot-security no longer brings test dependencies | `spring-boot-security` no longer transitively includes test-scope security artifacts. Add `spring-security-test` explicitly to your test dependencies if your tests use `@WithMockUser` or `SecurityMockMvcRequestPostProcessors`. |

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-45872 | Tomcat 10.1.42 multipart limits introduced | Tomcat now enforces limits on part count and header size in `multipart/form-data` requests. If your application receives large multipart requests, configure `server.tomcat.max-part-count` and `server.tomcat.max-part-header-size` to appropriate values. |
| 2 | N/A | TaskExecutor bean name changed to `applicationTaskExecutor` only | Spring Boot no longer registers the `taskExecutor` alias. Code that qualifies the `Executor` by the name `taskExecutor` must be updated to use `applicationTaskExecutor`, or you must add the alias manually via a `BeanFactoryPostProcessor`. |
| 3 | N/A | `.enabled` properties now strictly boolean | Config properties that control feature enablement now only accept `true` or `false`. Non-`false` strings that were previously treated as `true` will now fail binding. Audit all `*.enabled` properties in your configuration. |
| 4 | N/A | Profile names restricted to alphanumeric, dash, underscore | Profile names may now only contain letters, digits, `-`, and `_`, and must not start or end with `-` or `_`. Rename any profiles with dots or special characters before upgrading. |
| 5 | N/A | Heapdump actuator endpoint defaults to `access=NONE` | The `heapdump` endpoint is no longer accessible by default even when exposed. You must explicitly set `management.endpoint.heapdump.access=READ_ONLY` (or similar) in addition to exposing the endpoint. |
| 6 | N/A | Redis: `spring.data.redis.database` ignored when URL set | When `spring.data.redis.url` is configured, the `spring.data.redis.database` property is ignored (URL takes precedence, defaulting to `0`). Remove conflicting `database` property or encode it in the URL. |
| 7 | N/A | Prometheus Pushgateway: new client library required | Pushing to Prometheus Pushgateway now requires `io.prometheus:prometheus-metrics-exporter-pushgateway` instead of `io.prometheus:simpleclient_pushgateway`. Replace the dependency and rename `management.prometheus.metrics.export.pushgateway.base-url` to `management.prometheus.metrics.export.pushgateway.address` (format: `host:port`). |
| 8 | N/A | Apache Pulsar client upgraded from 3.3.x to 4.0.x | The Pulsar client is now at the 4.0 LTS release (3.3.x is EOL). Review Apache Pulsar 4.0 migration notes for API changes. |
| 9 | N/A | Couchbase Capella SSL certificate no longer auto-picked | Capella's embedded certificate is no longer trusted automatically. If you use Capella, create an SSL bundle referencing the Capella certificate and configure `spring.couchbase.env.ssl.bundle`. |
| 10 | N/A | Bean conditions consider generics in `@Bean` return types | `@ConditionalOnMissingBean(Converter.class)` will now match only if no `Converter<?, ?>` bean exists with exactly matching generics. Change your condition annotations if you intend to match on the raw type. |
| 11 | N/A | GraphQL transport property paths renamed | `spring.graphql.path` → `spring.graphql.http.path`; `spring.graphql.sse.timeout` → `spring.graphql.http.sse.timeout`. Update all GraphQL configuration property keys. |
| 12 | N/A | Zipkin URLConnectionSender removed | Zipkin's `URLConnectionSender` is no longer supported. The auto-configured default is now `ZipkinHttpClientSender`. Ensure `spring-boot-starter-zipkin` is on the classpath. |
| 13 | N/A | management.server.accesslog.prefix renamed | Property is now `management.server.{server}.accesslog.prefix` where `{server}` is `jetty`, `tomcat`, or `undertow`. Update any log access configuration. |
| 14 | GH-47029 | ConditionalOnEnabledTracing renamed | `ConditionalOnEnabledTracing` is renamed to `ConditionalOnEnabledTracingExport` and the backing property `management.tracing.enabled` is renamed to `management.tracing.export.enabled`. Update any custom condition references and configuration. |
| 15 | GH-47958 | management.zipkin.tracing renamed | `management.zipkin.tracing.*` properties are renamed to `management.tracing.export.zipkin.*`. Update your Zipkin tracing configuration properties. |
| 16 | GH-47052, GH-34954 | spring.mongodb.uuid-representation renamed | The property is renamed to align with the new `spring.mongodb.*` prefix structure. Update all MongoDB UUID representation configuration. |
| 17 | GH-47333 | Spring Session properties that depend on Spring Data renamed | Session store properties tied to Spring Data have been renamed. Review and update `spring.session.*` configuration keys. |
| 18 | GH-47327, GH-47328 | Jackson datetime and JSON mapper property paths renamed | `spring.jackson.datetime.*` → `spring.jackson.datatype.datetime.*`; JSON mapper-specific properties renamed to make their JSON scope explicit. Audit and update all `spring.jackson.*` properties. |
| 19 | N/A | spring.dao.exceptiontranslation.enabled renamed | Property renamed to `spring.persistence.exceptiontranslation.enabled`. Update your configuration files. |
| 20 | GH-46406 | org.springframework.boot.autoconfigure.thread package moved | Package `org.springframework.boot.autoconfigure.thread` is moved to `org.springframework.boot.thread`. Update any direct package imports. |
| 21 | GH-47387 | LiveReload server disabled by default | The DevTools LiveReload server is now off by default. To re-enable: `spring.devtools.livereload.enabled=true`. |
| 22 | GH-22825 | Liveness and readiness probes enabled by default | Kubernetes liveness (`/actuator/health/liveness`) and readiness (`/actuator/health/readiness`) endpoints are enabled by default. Ensure these endpoints are not inadvertently exposed on non-Kubernetes deployments, or configure `management.endpoint.health.probes.enabled=false`. |
| 23 | GH-47267 | Bitnami Docker Compose support removed | Spring Boot no longer provides built-in support for Bitnami legacy Docker Compose images. Update your Docker Compose configuration to standard images. |
| 24 | GH-47175 | Tomcat and Jetty runtime modules changed to starters | `spring-boot-tomcat` and `spring-boot-jetty` are now starters rather than plain runtime modules. If you override these via `<exclusions>`, review your configuration — the artifact names may have changed. |
| 25 | GH-47959, GH-47957 | Tracing and logging export property naming overhauled | Export-enable properties are now `management.tracing.export.{name}.enabled` and `management.logging.export.{name}.enabled`. Rename all relevant management properties. |

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | 3.3.x deprecated APIs removed | Everything deprecated in Spring Boot 3.3 and marked for removal in 3.5 is deleted. Ensure you have already resolved all 3.3 deprecation warnings before attempting this upgrade. |
| 2 | N/A | micrometer.observations.annotations.enabled removed | The property `micrometer.observations.annotations.enabled` (deprecated in 3.2) has been deleted. Use `management.observations.annotations.enabled`. |
| 3 | N/A | spring.mvc.converters.preferred-json-mapper deprecated | Deprecated in favour of `spring.http.converters.preferred-json-mapper`. Update now; it will be removed in a future release. |
| 4 | N/A | spring.codec.* properties deprecated | `spring.codec.log-request-details` and `spring.codec.max-in-memory-size` are deprecated. Replace with `spring.http.codecs.log-request-details` and `spring.http.codecs.max-in-memory-size`. |
| 5 | N/A | SignalFX support deprecated | `management.metrics.export.signalfx.*` is deprecated, following upstream Micrometer deprecation. Migrate to an alternative metrics exporter before it is removed. |
| 6 | N/A | Groovy template `spring.groovy.template.configuration.*` deprecated | Properties under `spring.groovy.template.configuration.` are deprecated in favour of `spring.groovy.template.*` equivalents. Review the configuration changelog and rename. |
| 7 | GH-45493 | ANT_PATH_MATCHER deprecated | `MvcRequestMatcher.setPattern` using ant-style patterns is deprecated. Migrate to PathPattern-based matching. |
| 8 | GH-47256 | JUnit 4 integration deprecated | Spring Boot's JUnit 4 integration is deprecated in 4.0. Migrate tests to JUnit 5. |
| 9 | GH-47272 | Old EnvironmentPostProcessor interface deprecated | `org.springframework.boot.env.EnvironmentPostProcessor` is deprecated; use `org.springframework.boot.EnvironmentPostProcessor` (without the `.env` sub-package). Update all custom `EnvironmentPostProcessor` implementations. |
| 10 | GH-2013 | Jackson 2 support deprecated | The `spring-boot-jackson2` compatibility module is deprecated and intended only for transitional use. Plan complete migration to Jackson 3. |

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | GH-46519 | API Versioning auto-configuration | Spring Boot now auto-configures Spring Framework's new API versioning support. Configure via `spring.web.version.*` properties to enable versioned REST APIs without custom filter code. |
| 2 | GH-31337 | Declarative HTTP Service clients auto-configured | `@HttpExchange`-annotated interfaces can now be auto-configured as Spring beans. Define `HttpServiceClient` properties under `spring.http.serviceclient.*` to enable declarative clients without boilerplate `RestClient`/`WebClient` setup. |
| 3 | GH-46587 | JSpecify nullability annotations added throughout | Spring Boot's public API now carries JSpecify `@NonNull`/`@Nullable` annotations, improving IDE null-safety checks and Kotlin interop. No action required but your IDE will surface new null-safety warnings. |
| 4 | GH-22825 | Liveness and readiness probes enabled by default | In Spring Boot 4.0, these Kubernetes-aligned health probes are enabled by default. No manual configuration needed for Kubernetes deployments. |
| 5 | GH-46167 | Elasticsearch API key authentication | Authenticate to Elasticsearch using `spring.elasticsearch.api-key` without configuring username/password. |
| 6 | GH-46587, GH-47470 | Jackson 3 compatibility configuration property | Set `spring.jackson.jackson2-compat=true` to auto-configure Jackson 3 with defaults that maximize compatibility with Spring Boot 3's Jackson 2 behaviour, easing incremental migration. |
| 7 | GH-47641, GH-47942 | Jackson CBOR and XML data format auto-configuration | Spring Boot 4.0 adds auto-configuration for Jackson CBOR and XML data format modules. Add the respective Jackson data format dependency and the module will be detected automatically. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 18 | Must fix before migrating. |
| 🟠 **Mandatory** | 12 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 35 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 7 | Optional but recommended to leverage. |

## 🚨 Most Critical Items for Migration

- **Jackson 3 is now required (GH-45535):** Jackson 2 is deleted from the default classpath. Every Jackson 2 import (`com.fasterxml.jackson.databind.*`) must be updated to Jackson 3 equivalents, or you must add the temporary `spring-boot-jackson2` compatibility module and plan a follow-up migration. This is the highest-effort change for most applications.
- **All 3.x deprecated APIs removed (GH-45600):** Spring Boot 4.0 removes every API that was deprecated for removal. If you have not already addressed all deprecation warnings in your Spring Boot 3.x application, compilation will fail after upgrading. Resolve all deprecation warnings first.
- **Auto-configurations are final with no public members (GH-32883):** Any code that subclasses, imports, or calls methods on auto-configuration classes (which was never supported API but was sometimes done) will fail to compile. Identify and replace all such usages with the documented extension points.
- **Security is modularized — explicit dependencies required (GH-46133–GH-46137):** Spring Boot 4.0 splits security into multiple fine-grained modules. Applications that relied on transitive resolution of security artifacts via `spring-boot-starter-security` may encounter `ClassNotFoundException` at runtime for OAuth2, SAML2, or authorization-server features. Explicitly add the needed security starter modules.
- **MongoDB property namespace changed (GH-47050, GH-34954):** All driver-level MongoDB properties must move from `spring.data.mongodb.*` / `spring.mongo.*` to `spring.mongodb.*`. Missing this rename causes silent misconfiguration (properties are ignored) or startup failure when the binding is strict.

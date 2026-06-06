# Spring Boot — Filtered Migration Changes

- **Framework:** `spring-boot`
- **Range:** `3.3.0` → `3.4.0`
- **Generated:** 2026-06-05

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Prometheus Client 1.x metric name changes | Spring Boot 3.3 upgraded to Prometheus Client 1.x, which contains breaking changes including renamed exported metric names. The Prometheus Push Gateway is unsupported with the 1.x client. Action: If you use Prometheus metrics, audit your dashboards/alerts for renamed metrics. To stay on the 0.x client, replace `io.micrometer:micrometer-registry-prometheus` with `io.micrometer:micrometer-registry-prometheus-simpleclient` (the simpleclient auto-configuration is deprecated and will be removed in 3.5.0). |
| 2 | GH-35403 | Empty YAML maps now silently ignored | Empty maps in YAML configuration are now discarded, aligning YAML with properties-file behaviour. Any property previously relying on an empty YAML map to produce a non-null empty-map binding will now receive `null` or be absent. Audit your YAML files and replace empty maps with explicit values or remove the keys entirely. |
| 3 | GH-42934 | spring-boot-starter-aop removed from JPA/Integration starters | The transitive AOP starter dependency has been removed from `spring-boot-starter-data-jpa` and `spring-boot-starter-integration`. Applications that rely on AOP being on the classpath via these starters must now declare `spring-boot-starter-aop` explicitly. |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Flyway 10 modular database support | Spring Boot 3.3 upgrades to Flyway 10, which moved support for several databases into optional modules. If you use DB2, Derby, HSQLDB, Informix, PostgreSQL, Redshift, SAP HANA, Snowflake, or Sybase ASE, add the corresponding `flyway-database-*` artifact to your dependencies (e.g., `flyway-database-postgresql`). |
| 2 | N/A | Infinispan 15 — removal of -jakarta module aliases | Infinispan 15 raised its Jakarta EE baseline. Modules such as `infinispan-core-jakarta` no longer exist. Replace `-jakarta` variants with their standard equivalents (e.g., use `infinispan-core` instead of `infinispan-core-jakarta`). |
| 3 | GH-39068 | GraalVM Native Build Tools 0.10.x required | If you build native images with GraalVM, you must now use at least version 0.10.x of the Native Build Tools plugin. Maven users on the Spring Boot parent get this automatically; Gradle users must update the plugin version manually. |
| 4 | GH-45869 | Tomcat 10.1.42 multipart limits introduced (3.3.13) | The 3.3.13 patch bumps Tomcat to 10.1.42, which introduces default limits on part count and header size for `multipart/form-data` requests. Applications uploading many form parts may be rejected. Tune `server.tomcat.max-part-count` and `server.tomcat.max-part-header-size` as needed. |
| 5 | N/A | HtmlUnit 4.5 — changed coordinates and packages | HtmlUnit upgraded to 4.5: dependency coordinates changed from `net.sourceforge.htmlunit:htmlunit` to `org.htmlunit:htmlunit`, and package names changed from `com.gargoylesoftware.htmlunit.` to `org.htmlunit.`. Update your build files and import statements. |
| 6 | N/A | Selenium HtmlUnit 4.25 — changed coordinates | The Selenium HtmlUnit driver artifact changed from `org.seleniumhq.selenium:htmlunit-driver` to `org.seleniumhq.selenium:htmlunit3-driver`. Update your build configuration. |
| 7 | N/A | Gradle 7.5–8.3 no longer supported | Spring Boot 3.4 requires Gradle 7.6.4+ or Gradle 8.4+. Earlier Gradle versions are not supported. Update your Gradle wrapper accordingly. |
| 8 | N/A | Git Commit ID Maven Plugin upgraded to 8.0.x | The plugin's default date format changed to `yyyy-MM-dd'T'HH:mm:ssXXX`. Any tooling or code that parses the previous date format must be updated. |
| 9 | N/A | RestClient/RestTemplate HTTP client selection changed | Auto-configured `RestClient` and `RestTemplate` now prefer `JdkClientHttpRequestFactory` when no HTTP client library is present on the classpath (previously fell back to `SimpleClientHttpRequestFactory`). Apache HTTP Components also changed defaults for HTTP/1.1 TLS upgrades which can cause issues with Envoy/Istio proxies. Set `spring.http.client.factory` explicitly or use `ClientHttpRequestFactoryBuilder` to restore previous behaviour. |
| 10 | N/A | Cassandra driver coordinates changed | The Cassandra driver changed Maven coordinates from `com.datastax.oss` to `org.apache.cassandra`. Update your dependency declarations if you manage the Cassandra driver version explicitly. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | JWT resource server security properties added | Three new properties are now mandatory for JWT authority mapping: `spring.security.oauth2.resourceserver.jwt.authority-prefix`, `spring.security.oauth2.resourceserver.jwt.principal-claim-name`, and `spring.security.oauth2.resourceserver.jwt.authorities-claim-name`. Applications that previously relied on hard-coded defaults must configure these explicitly to preserve role mapping behaviour. |
| 2 | N/A | SAML2 NameID format property required | A new confirmed-mandatory property `spring.security.saml2.relyingparty.registration.*.name-id-format` must be set for SAML2 registrations that require a specific NameID format. |
| 3 | N/A | Security filter chain / Actuator health group path exposure | The default security configuration now exposes health groups mapped to additional paths. Custom `SecurityFilterChain` beans may inadvertently block or expose these paths. Both `EndpointRequest` classes now provide `toAdditionalPaths(…)` methods to match them. Review and adjust your `SecurityFilterChain` configuration. |
| 4 | N/A | Actuator endpoint access model replaced | `management.endpoints.enabled-by-default` and `management.endpoint.<id>.enabled` are deprecated and replaced by `management.endpoints.access.default`, `management.endpoint.<id>.access`, and `management.endpoints.access.max-permitted`. If endpoints become inaccessible after upgrading, set `management.endpoint.<id>.access` to `read-only` or `unrestricted`, or temporarily keep the legacy `enabled` property. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Bean Validation on @ConfigurationProperties now follows spec | Previously, nested properties inside a `@Validated @ConfigurationProperties` class were validated irrespective of `@Valid`. In 3.4, validation only cascades to fields annotated with `@Valid`. Add `@Valid` on nested property fields where you need cascaded validation. |
| 2 | N/A | @ConditionalOnBean/MissingBean behaviour with `annotation` attribute | When `annotation` is set on `@ConditionalOnBean` or `@ConditionalOnMissingBean`, the return type of the `@Bean` method is no longer used as a default type. Specify both `value` (the return type) and `annotation` explicitly if you relied on the old default. |
| 3 | N/A | Graceful shutdown enabled by default | Embedded web server (Jetty, Reactor Netty, Tomcat, Undertow) graceful shutdown is now enabled by default. To restore previous behaviour, set `server.shutdown=immediate`. |
| 4 | N/A | Default OCI image builder changed to jammy-java-tiny | The default Paketo buildpack builder for JVM OCI images changed from `paketobuildpacks/builder-jammy-base` to `paketobuildpacks/builder-jammy-java-tiny`. The tiny builder has no shell and a reduced set of system libraries. Applications needing a shell or additional system libraries must configure the builder explicitly. |
| 5 | N/A | Cassandra driver changed coordinates | Already listed under Major Component Upgrades; no further action needed beyond the dependency update. |
| 6 | GH-39606 | Git commit-id date format changed | The git-commit-id-maven-plugin date format changed to ISO-8601 (`yyyy-MM-dd'T'HH:mm:ssXXX`). Any downstream tooling parsing the old date format must be adapted. |
| 7 | N/A | Jetty JNDI removed from starter by default | `spring-boot-starter-jetty` no longer includes `jetty-jndi`. Applications that use JNDI with Jetty must add `org.eclipse.jetty:jetty-jndi` explicitly. |
| 8 | N/A | Configuration processor fails on superfluous metadata keys | The Spring Boot configuration processor now fails the build if `additional-spring-configuration-metadata.json` contains keys that are not declared in the source. Remove or correct any superfluous keys. |
| 9 | N/A | DynamicPropertyRegistry injection in @Bean deprecated | Injecting `DynamicPropertyRegistry` directly into a `@Bean` method is deprecated and now fails by default. Migrate to a separate `@Bean` method returning a `DynamicPropertyRegistrar`. To temporarily restore old behaviour, set `spring.testcontainers.dynamic-property-registry-injection=warn` or `allow`. |
| 10 | N/A | Netty native image — manual reachability metadata version required | Spring Boot 3.4.0 uses a Netty version not yet covered by the Native Build Tools' bundled GraalVM reachability metadata. Manually upgrade the reachability metadata version in your Maven or Gradle build. |
| 11 | GH-43202 | StructuredLoggingJsonProperties customizer type changed | `StructuredLoggingJsonProperties` customizer must now be a `Class` reference, not a `String`. Update any structured logging customizer configuration. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Zipkin HTTP client builder customizers renamed | `ZipkinRestTemplateBuilderCustomizer` and `ZipkinWebClientBuilderCustomizer` deprecated in favour of `ZipkinHttpClientBuilderCustomizer`. Migrate to the new interface. |
| 2 | N/A | jarmode=layertools commands superseded | `-Djarmode=layertools extract` and `-Djarmode=layertools list` are deprecated. Use `-Djarmode=tools extract --layers` and `-Djarmode=tools list-layers` respectively. Update CI scripts and Dockerfiles. The Gradle `layers.includeLayerTools` / Maven `<layers><enabled>` configuration is replaced by `includeTools` / `<includeTools>`. |
| 3 | GH-31768 | @ServletEndpoint / @ControllerEndpoint deprecated | `@ServletEndpoint`, `@ControllerEndpoint`, and `@RestControllerEndpoint` annotations for Actuator endpoints are deprecated. Migrate to the `@Endpoint` / `@ReadOperation` / `@WriteOperation` model. |
| 4 | N/A | Jersey / Micrometer observability migration required | Micrometer 1.13 deprecated Jersey support in favour of Jersey's `jersey-micrometer` module. Add `org.glassfish.jersey.ext:jersey-micrometer`. Replace `MetricsApplicationEventListener` with `ObservationApplicationEventListener` and migrate `JerseyTagsProvider` to `JerseyObservationConvention`. |
| 5 | N/A | Dropwizard Metrics dependency management removed | Spring Boot no longer manages Dropwizard Metrics versions. Applications depending directly on Dropwizard Metrics must specify the version in their build configuration. |
| 6 | N/A | @MockBean / @SpyBean deprecated in favour of Framework annotations | `@MockBean` and `@SpyBean` are deprecated in favour of Spring Framework's `@MockitoBean` and `@MockitoSpyBean`. Note that `@MockitoBean` is not supported on `@Configuration` classes; migrate to field annotations on test classes. |
| 7 | N/A | spring.gson.lenient replaced | `spring.gson.lenient` deprecated in favour of `spring.gson.strictness`. |
| 8 | N/A | WebJars locator-core deprecated | `org.webjars:webjars-locator-core` is deprecated; switch to `org.webjars:webjars-locator-lite` for faster startup and better asset resolution. |
| 9 | N/A | Actuator endpoint enable/disable model deprecated | `management.endpoints.enabled-by-default`, `management.endpoint.<id>.enabled`, and `enableByDefault` on `@Endpoint` are deprecated. Use the new access-model properties and `defaultAccess` attribute (see Security Configuration section). |
| 10 | N/A | Dynamic property registry injection deprecated | Injecting `DynamicPropertyRegistry` into `@Bean` methods is deprecated (see Behavioral Changes row 9). |
| 11 | N/A | OpenTelemetry auto-configuration classes renamed | `OpenTelemetryAutoConfiguration` deprecated in favour of `OpenTelemetryTracingAutoConfiguration`; `OtlpAutoConfiguration` deprecated in favour of `OtlpTracingAutoConfiguration`. Update any references in `spring.factories` / `AutoConfiguration.imports`. |
| 12 | N/A | OkHttp dependency management removed | Spring Boot no longer manages OkHttp. Applications using OkHttp must declare an explicit version. |
| 13 | N/A | Deprecations from Spring Boot 3.2 removed in 3.4 | All classes, methods, and properties deprecated in Spring Boot 3.2 and marked for removal in 3.4 have been removed. Ensure no deprecated 3.2 APIs are still in use before upgrading. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Structured logging support added | Native support for structured (JSON) logging via `logging.structured.*` properties. Allows machine-readable log output without external libraries. |
| 2 | N/A | OTLP logging and gRPC transport | Support added for exporting logs via OTLP (including gRPC transport). Enable with `management.logging.export.enabled` / `management.otlp.logging.export.enabled`. |
| 3 | N/A | Docker Compose service connection enhancements | Added service connection support for Redis Stack, Redis Stack Server, Grafana LGTM, Hazelcast, and `org.testcontainers.kafka.KafkaContainer`. |
| 4 | N/A | ClientHttpRequestFactoryBuilder API | New `ClientHttpRequestFactoryBuilder` API simplifies programmatic customisation of the HTTP client backing `RestClient` / `RestTemplate`. |
| 5 | N/A | spring.application.version property | New property `spring.application.version` exposes the application version (defaults to `Implementation-Version` from the manifest). |
| 6 | N/A | Liveness/Readiness probes auto-enabled on Cloud Foundry | Liveness and Readiness health probes are now automatically enabled when running on Cloud Foundry. No additional configuration is required. |
| 7 | N/A | SSL bundle support for Kafka in native images | Kafka's SSL configuration can now use SSL bundles in native images. Previously this caused a `ClassNotFoundException`. |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 3 | Must fix before migrating. |
| 🟠 **Mandatory** | 14 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 24 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 7 | Optional but recommended to leverage. |

---

## 🚨 Most Critical Items for Migration

- **Prometheus Client 1.x (Breaking):** Metric names have changed in the 1.x client. Dashboards, alerts, and any tooling querying Prometheus metrics must be reviewed and updated. If you need to stay on 0.x, swap `micrometer-registry-prometheus` for `micrometer-registry-prometheus-simpleclient` before the 3.5.0 deadline.
- **Flyway 10 modular dependencies (Mandatory):** If your application runs database migrations against PostgreSQL, DB2, HSQLDB, or any of the other now-separate Flyway modules, the corresponding `flyway-database-*` artifact must be added to your build. Missing this causes Flyway startup failures.
- **RestClient/RestTemplate HTTP client precedence change (Mandatory):** Applications without an explicit HTTP client library on the classpath will silently switch from `SimpleClientHttpRequestFactory` to `JdkClientHttpRequestFactory`, which has different behaviour for redirects, timeouts, and TLS. Apache HTTP Components also changed TLS upgrade defaults that affect Envoy/Istio setups.
- **JWT / Security property requirements (Mandatory):** Three OAuth2 JWT resource server properties and the SAML2 NameID format property are now required configuration. Omitting them may cause auth failures or default-role mismatches after upgrade.
- **Spring Boot 3.2 deprecation removals (Mandatory):** All APIs deprecated in 3.2 with a 3.4 removal marker are gone. Compile your project against 3.3 first with deprecation warnings enabled and resolve all of them before upgrading to 3.4.

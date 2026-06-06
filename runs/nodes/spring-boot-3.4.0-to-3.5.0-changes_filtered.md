# Spring Boot Migration Filter — 3.4.0 → 3.5.0

- **Framework:** `spring-boot`
- **Range:** `3.4.0` → `3.5.0`
- **Filtered:** 2026-06-05

---

## 🔴 Breaking Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Spring Boot 3.2 deprecated APIs removed | Classes, methods, and properties deprecated in Spring Boot 3.2 and marked for removal in 3.4 have been physically removed. Any code still calling these deprecated APIs will fail to compile or throw `NoClassDefFoundError`/`NoSuchMethodError` at runtime. Audit your codebase for Spring Boot 3.2 deprecation warnings and eliminate all usages before upgrading. |
| 2 | N/A | Gradle minimum version raised | Gradle 7.5, 8.0, 8.1, 8.2, and 8.3 are no longer supported. You must use Gradle 7.6.4+ or Gradle 8.4+. Upgrade your Gradle wrapper version before migrating. |

---

## 🟠 Mandatory Migrations — Security Configuration

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Security config: health groups on additional paths | The default Spring Security configuration now exposes health groups mapped to additional paths (e.g., liveness/readiness probes). Both `EndpointRequest` classes gained `toAdditionalPaths(…)` methods. If you have custom security rules restricting actuator access, review and update your `SecurityFilterChain` to account for these additional health probe paths, or use `EndpointRequest.toAdditionalPaths(…)` for proper matching. |
| 2 | N/A | Spring Security logout triggers audit event | An audit event (`AuditEvent`) is now published whenever a Spring Security logout occurs. If your application has `AuditEventRepository` configured or audit-based logic, review whether the new logout audit events affect behavior (e.g., unexpected event counts, storage load, or audit log noise). |

---

## 🟠 Mandatory Migrations — Major Component Upgrades

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | RestClient/RestTemplate: HTTP client selection changed | Auto-configured `RestClient` and `RestTemplate` now select the HTTP client implementation in this precedence order: Apache HTTP Components, Jetty Client, Reactor Netty, JDK HttpClient, Simple JDK `HttpURLConnection`. If no HTTP client library is on the classpath, `JdkClientHttpRequestFactory` will be used instead of the previous `SimpleClientHttpRequestFactory`. This can change TLS, redirect, and timeout behavior. Set `spring.http.client.factory` to a specific value (`http-components`, `jetty`, `reactor`, `jdk`, or `simple`) to pin the desired client explicitly. |
| 2 | N/A | Apache HTTP Components: TLS upgrade defaults changed | Apache HTTP Components changed defaults for HTTP/1.1 TLS upgrades in `HttpClient`. Applications using Envoy or Istio as proxies may encounter connectivity issues. To restore previous behavior, define an `HttpComponentsClientHttpRequestFactoryBuilder` bean and apply the appropriate `TlsStrategy` customization via `ClientHttpRequestFactoryBuilder.httpComponents()`. |
| 3 | N/A | HtmlUnit 4.5: coordinates and packages changed | HtmlUnit upgraded from `net.sourceforge.htmlunit:htmlunit` to `org.htmlunit:htmlunit`, with package names changed from `com.gargoylesoftware.htmlunit.*` to `org.htmlunit.*`. Update your `pom.xml` or `build.gradle` dependency coordinates and update all affected imports across your test code. |
| 4 | N/A | Selenium HtmlUnit: coordinates changed | Selenium HtmlUnit updated from `org.seleniumhq.selenium:htmlunit-driver` to `org.seleniumhq.selenium:htmlunit3-driver`. Update your build configuration accordingly. |
| 5 | N/A | OkHttp dependency management removed | Spring Boot no longer manages the OkHttp version. If your application directly or transitively depends on OkHttp, add an explicit `<dependencyManagement>` entry or `resolutionStrategy` in your build to pin a compatible OkHttp version. |
| 6 | GH-44280 | Guava dependency management removed (Prometheus upgrade) | The upgrade to Prometheus Client 1.3.6 removed Guava from Spring Boot's managed dependencies. If your project depends on Guava (directly or transitively via Prometheus), add an explicit Guava version to your dependency management. |

---

## 🟡 Behavioral Changes

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Bean Validation: @Valid required for nested cascade | `@ConfigurationProperties` classes annotated with `@Validated` no longer automatically cascade validation into nested properties. Validation now follows the Bean Validation specification: only properties whose field is annotated with `@Valid` will be validated recursively. Inspect all `@ConfigurationProperties` classes with Hibernate Validator constraints; add `@Valid` to fields where nested validation is required. |
| 2 | N/A | @ConditionalOnBean: annotation attribute now suppresses default type | When `@ConditionalOnBean` or `@ConditionalOnMissingBean` is used on a `@Bean` method and the `annotation` attribute is set, the default type inference from the method's return type is no longer applied. Previously the default was only suppressed when `name`, `type`, or `value` were set. To restore old behavior, explicitly specify `value` with the return type alongside `annotation`. |
| 3 | N/A | Graceful shutdown enabled by default | Graceful shutdown for embedded web servers (Jetty, Reactor Netty, Tomcat, Undertow) is now enabled by default (`server.shutdown=graceful`). In-flight requests are drained before shutdown completes. If you require immediate shutdown behavior (e.g., for tests or fast cycling environments), set `server.shutdown=immediate`. |
| 4 | GH-35403 | Empty YAML maps now ignored | Empty maps in YAML configuration files are now silently ignored, treating them as absent keys. This aligns YAML with `.properties` and system property formats. If you relied on an empty YAML map to reset or clear a property, you must now use an explicit null value or remove the key. |
| 5 | N/A | Paketo tiny builder is new default for OCI images | The default Cloud Native Buildpacks builder has changed from `paketobuildpacks/builder-jammy-base` to `paketobuildpacks/builder-jammy-java-tiny`. The tiny builder lacks a shell and includes fewer system libraries. Applications that require a shell-based start script or depend on specific system libraries may fail to build or run. Verify your application works with the tiny builder; switch the builder explicitly if necessary. |
| 6 | GH-44033 | Tomcat APR requires explicit config on Java 24+ | On Java 24 and above, the `server.tomcat.use-apr` property now defaults to `never`. If your application uses Tomcat's APR (Apache Portable Runtime) and runs on Java 24+, you must explicitly set `server.tomcat.use-apr=when-available` or `always`; otherwise APR will be disabled silently. |
| 7 | GH-45870 | Tomcat multipart limits introduced (Tomcat 10.1.42) | Tomcat 10.1.42 introduced default limits on `multipart/form-data` part count and header size. Applications that submit large multipart forms may encounter rejections. Tune `server.tomcat.max-part-count` and `server.tomcat.max-part-header-size` as needed to match your application's requirements. |

---

## 🟡 Deprecations

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | Actuator endpoint access model reworked | `management.endpoints.enabled-by-default` and `management.endpoint.<id>.enabled` are deprecated in favor of `management.endpoints.access.default` and `management.endpoint.<id>.access` (with values `none`, `read-only`, `unrestricted`). The `enableByDefault` attribute on `@Endpoint` is deprecated in favor of `defaultAccess`. Migrate your actuator configuration properties to the new access model; if endpoints go missing after upgrade, set `management.endpoint.<id>.access=unrestricted`. |
| 2 | N/A | DynamicPropertyRegistry injection in @Bean deprecated | Injecting `DynamicPropertyRegistry` directly into a `@Bean` method (Testcontainers pattern) is deprecated and now fails by default. Migrate to a separate `@Bean` method that returns a `DynamicPropertyRegistrar`, injecting the container explicitly. To temporarily restore old behavior, set `spring.testcontainers.dynamic-property-registry-injection=warn` or `allow`. |
| 3 | N/A | @MockBean and @SpyBean deprecated | `@MockBean` and `@SpyBean` are deprecated in favor of Spring Framework's `@MockitoBean` and `@MockitoSpyBean`. Note that `@MockitoBean` is not supported on `@Configuration` classes — you may need to move annotations to test class fields instead. Migrate all usages before the next major release removes the annotations. |
| 4 | N/A | WebJars locator-core deprecated | `org.webjars:webjars-locator-core` support is deprecated. Switch to `org.webjars:webjars-locator-lite` in your build for faster startup and continued support. Both are managed by Spring Boot. |
| 5 | N/A | OTLP tracing auto-configuration classes renamed | `OtlpAutoConfiguration` is deprecated in favor of `OtlpTracingAutoConfiguration`; `OpenTelemetryAutoConfiguration` is deprecated in favor of `OpenTelemetryTracingAutoConfiguration`; `OtlpTracingConnectionDetails#getUrl()` is deprecated in favor of `getUrl(Transport)`. Update any direct references to these classes in custom auto-configuration or conditional logic. |
| 6 | N/A | Logback ApplicationNameConverter renamed | `org.springframework.boot.logging.logback.ApplicationNameConverter` is deprecated in favor of `EnclosedInSquareBracketsConverter`. Update any custom Logback configuration that references the old converter class name. |
| 7 | N/A | spring.gson.lenient replaced by spring.gson.strictness | The property `spring.gson.lenient` is deprecated in favor of `spring.gson.strictness`. Replace `spring.gson.lenient=true` with `spring.gson.strictness=lenient` in your application properties. |
| 8 | N/A | EndpointExposure.CLOUD_FOUNDRY deprecated | `EndpointExposure.CLOUD_FOUNDRY` used with `@ConditionalOnAvailableEndpoint` is deprecated in favor of `EndpointExposure.WEB`. Update custom Cloud Foundry-specific actuator endpoint conditions to use `EndpointExposure.WEB`. |

---

## 🔵 Notable New Capabilities

| # | JIRA | Title | Impact |
| :--- | :--- | :--- | :--- |
| 1 | N/A | OTLP logging and gRPC transport support | OTLP logging is now supported, and logs can be shipped over gRPC transport. Use `management.otlp.logging.*` and `management.logging.export.enabled` properties to configure. No migration required; opt in if centralised log export is desired. |
| 2 | N/A | SSL bundles for JavaMailSender | TLS configuration for `JavaMailSender` can now use SSL bundles via `spring.mail.ssl.*` properties. Simplifies certificate management for mail connections; migrate from manual keystore configuration if applicable. |
| 3 | N/A | Liveness/Readiness auto-enabled on Cloud Foundry | Liveness and Readiness health probes are automatically enabled on Cloud Foundry platforms without additional configuration. No action required; verify probe endpoints behave as expected if deploying to Cloud Foundry. |
| 4 | N/A | ClientHttpRequestFactoryBuilder API | New `ClientHttpRequestFactoryBuilder` API provides a fluent builder to construct and customize HTTP client factories (Apache, Jetty, Reactor, JDK, Simple). Use this API when you need fine-grained customization of the HTTP client (e.g., to work around Envoy TLS issues or set per-client timeouts). |

---

## Summary by Priority

| Priority Level | Count | Description |
| :--- | :--- | :--- |
| 🔴 **Breaking** | 2 | Must fix before migrating. |
| 🟠 **Mandatory** | 8 | Security CVEs, component upgrades, security config. |
| 🟡 **Behavioral / Deprecation** | 15 | Assess impact and adjust accordingly. |
| 🔵 **New Capabilities** | 4 | Optional but recommended to leverage. |

---

## 🚨 Most Critical Items for Migration

- **Spring Boot 3.2 removals (Breaking):** All APIs deprecated in 3.2 are physically removed in 3.4. This is a hard compile and runtime break — scan your entire codebase for deprecation warnings from 3.2 and resolve them before attempting this upgrade.
- **RestClient/RestTemplate HTTP client selection (Mandatory):** The auto-configured HTTP client precedence has changed; applications without an explicit HTTP client on the classpath will silently switch from `SimpleClientHttpRequestFactory` to `JdkClientHttpRequestFactory`, with different TLS, redirect, and proxy behavior. Set `spring.http.client.factory` explicitly to avoid runtime surprises.
- **Apache HTTP Components TLS defaults (Mandatory):** Applications running behind Envoy or Istio sidecars may break due to changed HTTP/1.1 TLS upgrade behavior in Apache HttpClient. Test in a service-mesh environment and apply `ClientHttpRequestFactoryBuilder` customization if needed.
- **Bean Validation cascade (@Valid required) (Behavioral):** Nested `@ConfigurationProperties` validation silently stopped working unless `@Valid` is present. Configuration constraint violations in nested objects will no longer be reported, which could mask misconfiguration at startup.
- **Actuator endpoint access model (Deprecation becoming mandatory):** The `management.endpoints.enabled-by-default` and per-endpoint `.enabled` properties are deprecated with new replacement properties. Endpoints may become inaccessible if configuration is not migrated, since the new model applies `enabled-by-default` consistently regardless of `@ConditionalOnEnabledEndpoint`.
